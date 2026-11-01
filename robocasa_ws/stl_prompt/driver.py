"""Run all (prompt, task) evals, a few at a time, restartably. Meant to run inside `screen`.

Usage (from robocasa_ws/):
  python stl_prompt/driver.py --out eval_logs_stl [--variants nl,stl_nl,stl] [--tasks A,B|all]
                              [--episodes 10] [--slots 2] [--gpus 0,1]

Order: the first two variants interleaved task by task (nl, stl_nl, nl, stl_nl, ...), then the rest.
Each pair starts on the listed GPU with the most free memory, and only if at least --need-gb is free
(the GPUs are shared; a pair that started less than 3 min ago counts as using --need-gb already).
Otherwise the driver waits. A pair is done when <out>/<variant>/<task>/eval_info.json exists
and all its recordings are there; done pairs are skipped, so a restart picks up where it stopped. A pair
that fails or is incomplete is moved aside to <task>.incomplete-<time> and run again (up to --retries times).
After each eval the checker (monitor.py, rtamt venv) runs on that pair and writes check.txt next to it.
Every minute the driver logs free RAM and the RSS of each running eval.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parent
sys.path.insert(0, str(HERE))
from stl_spec import TASKS  # noqa: E402

RTAMT_PY = "/mnt/samsung_2tb/mingyue/stl_repos/.venv-rtamt/bin/python"


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def pair_dir(out: Path, v: str, t: str) -> Path:
    return out / v / t


def is_done(out: Path, v: str, t: str, n: int) -> bool:
    d = pair_dir(out, v, t)
    have = {p.name for p in (d / "traces").glob("*.json.gz")}
    return (d / "eval_info.json").exists() and all(f"{t}_ep{k}.json.gz" in have for k in range(n))


def mem_available_gb() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) / 2**20
    return float("nan")


def tree_rss_gb(pid: int) -> float:
    """RSS of a process and all its descendants."""
    kids: dict[int, list[int]] = {}
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                ppid = int((p / "stat").read_text().rsplit(")", 1)[1].split()[1])
            except (OSError, IndexError, ValueError):
                continue
            kids.setdefault(ppid, []).append(int(p.name))
    total, todo = 0, [pid]
    while todo:
        q = todo.pop()
        todo += kids.get(q, [])
        try:
            for line in Path(f"/proc/{q}/status").read_text().splitlines():
                if line.startswith("VmRSS"):
                    total += int(line.split()[1])
        except OSError:
            pass
    return total / 2**20


def gpu_free_gb(idx: str) -> float:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", idx],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip()) / 1024
    except ValueError:
        return 0.0


def queue(variants: list[str], tasks: list[str]) -> list[tuple[str, str]]:
    first, rest = variants[:2], variants[2:]
    q = [(v, t) for t in tasks for v in first]
    q += [(v, t) for v in rest for t in tasks]
    return q


def check_pair(out: Path, v: str, t: str):
    d = pair_dir(out, v, t)
    with open(d / "check.txt", "w") as f:
        subprocess.run([RTAMT_PY, str(HERE / "monitor.py"), "--no-write", str(d)], stdout=f,
                       stderr=subprocess.STDOUT, cwd=WS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="eval_logs_stl")
    ap.add_argument("--variants", default="nl,stl_nl,stl")
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--slots", type=int, default=2)
    ap.add_argument("--gpus", default="0,1")
    ap.add_argument("--need-gb", type=float, default=11.0, help="free GPU memory needed to start a pair")
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    variants = a.variants.split(",")
    tasks = list(TASKS) if a.tasks == "all" else a.tasks.split(",")
    gpus = a.gpus.split(",")
    pending = [p for p in queue(variants, tasks) if not is_done(out, *p, a.episodes)]
    log(f"driver start: {len(pending)} pairs to run, slots={a.slots}, gpus={gpus}, episodes={a.episodes}")
    running: dict[int, tuple[tuple[str, str], subprocess.Popen, float, str]] = {}
    tries: dict[tuple[str, str], int] = {}
    last_wait = 0.0
    failed: list[tuple[str, str]] = []
    last_mem = 0.0
    while pending or running:
        for slot in range(a.slots):
            if slot in running or not pending:
                continue
            # pick the GPU with the most free memory, minus what recently started pairs will still take
            free = {}
            for g in gpus:
                recent = sum(1 for (_, _, t0, gg) in running.values() if gg == g and time.time() - t0 < 180)
                free[g] = gpu_free_gb(g) - recent * a.need_gb
            gpu = max(free, key=free.get)
            if free[gpu] < a.need_gb:
                if time.time() - last_wait > 600:
                    last_wait = time.time()
                    log(f"waiting for GPU memory: free {', '.join(f'gpu{g} {f:.1f} GB' for g, f in free.items())}")
                break
            v, t = pending.pop(0)
            d = pair_dir(out, v, t)
            if d.exists() and any(d.iterdir()):
                stale = d.with_name(f"{t}.incomplete-{time.strftime('%Y%m%d-%H%M%S')}")
                shutil.move(str(d), str(stale))
                log(f"moved incomplete {d} -> {stale.name}")
            cmd = ["bash", str(HERE / "run_eval.sh"), v, t, gpu, str(a.episodes), str(out)]
            running[slot] = ((v, t), subprocess.Popen(cmd, cwd=WS), time.time(), gpu)
            log(f"slot {slot} gpu {gpu}: start {v} {t}")
        time.sleep(5)
        if time.time() - last_mem > 60:
            last_mem = time.time()
            rss = ", ".join(f"{p[0][0]}/{p[0][1]} {tree_rss_gb(p[1].pid):.1f} GB" for p in running.values())
            log(f"mem: available {mem_available_gb():.1f} GB; running: {rss}")
        for slot, ((v, t), proc, t0, _) in list(running.items()):
            if proc.poll() is None:
                continue
            del running[slot]
            ok = proc.returncode == 0 and is_done(out, v, t, a.episodes)
            log(f"slot {slot}: {v} {t} finished code={proc.returncode} ok={ok} in {(time.time() - t0) / 60:.1f} min")
            if ok:
                check_pair(out, v, t)
            elif tries.get((v, t), 0) < a.retries:
                tries[(v, t)] = tries.get((v, t), 0) + 1
                pending.insert(0, (v, t))
                log(f"retrying {v} {t} ({tries[(v, t)]}/{a.retries})")
            else:
                failed.append((v, t))
    log(f"driver done; failed pairs: {failed or 'none'}")
    if not failed:
        with open(out / "summary.md", "w") as f:
            dirs = [str(out / v) for v in variants if (out / v).exists()]
            subprocess.run([RTAMT_PY, str(HERE / "monitor.py"), *dirs], stdout=f, stderr=subprocess.STDOUT, cwd=WS)
        log(f"wrote {out / 'summary.md'}")


if __name__ == "__main__":
    main()
