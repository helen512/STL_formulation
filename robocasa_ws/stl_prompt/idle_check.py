"""Idle-robot check (plan step 4): zero actions, no policy, cameras off.

Builds every (task, seed) scene the way LeRobot does (RoboCasaGymEnv, split=pretrain, objaverse + lightwheel,
reset(seed)), applies LeRobot's zero action for the task's full horizon, and writes the same recordings as
launch_eval.py. Check them with monitor.py --idle.

Usage (from robocasa_ws/):
  pixi run python stl_prompt/idle_check.py --out eval_logs_stl/idle [--tasks A,B] [--seeds 1000-1009] [--workers 4]
Without --one, it starts one subprocess per task (at most --workers at a time).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from stl_spec import TASKS  # noqa: E402

OBJ_REGISTRIES = ("objaverse", "lightwheel")


def make_env(task: str, cameras: bool = False):
    import robocasa.wrappers.gym_wrapper as GW

    if not cameras:
        orig = GW.create_env

        def create_env(*a, **kw):
            return orig(*a, camera_names=[], **kw)

        GW.create_env = create_env
    try:
        return GW.RoboCasaGymEnv(env_name=task, camera_widths=256, camera_heights=256, split="pretrain",
                                 obj_registries=OBJ_REGISTRIES, enable_render=cameras)
    finally:
        if not cameras:
            GW.create_env = orig


def run_task(task: str, seeds: list[int], out: Path, cameras: bool = False):
    import numpy as np
    from lerobot.envs.robocasa import convert_action

    from recorder import Recorder, episode_names

    g = make_env(task, cameras)
    rec = Recorder(task, "idle", {"seed0": 1000, "cameras": cameras})
    zero = np.zeros(12, dtype=np.float32)
    for seed in seeds:
        t0 = time.time()
        g.reset(seed=seed)
        ep = episode_names(g.env, task)
        rec.start(g.env, seed, ep["lang"], ep["names"])
        rec.trace["prompts"] = ep["prompts"]
        t1 = time.time()
        for _ in range(TASKS[task].horizon):
            _, _, _, _, info = g.step(convert_action(zero))
            rec.sample(bool(info["success"]))
        t2 = time.time()
        path = rec.write(out, f"{task}_ep{seed - 1000}.json.gz")
        print(f"[idle] {task} seed={seed} reset={t1 - t0:.1f}s steps={t2 - t1:.1f}s -> {path}", flush=True)
    g.close()


def parse_seeds(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--seeds", default="1000-1009")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cameras", action="store_true", help="render the cameras as in the eval (slower)")
    ap.add_argument("--one", action="store_true", help="run the tasks in this process")
    a = ap.parse_args()
    out = Path(a.out)
    tasks = a.tasks.split(",")
    seeds = parse_seeds(a.seeds)
    if a.one:
        for t in tasks:
            run_task(t, seeds, out, a.cameras)
        return
    out.mkdir(parents=True, exist_ok=True)
    procs: list[tuple[str, subprocess.Popen]] = []
    pending = list(tasks)
    failed = []
    while pending or procs:
        while pending and len(procs) < a.workers:
            t = pending.pop(0)
            cmd = [sys.executable, __file__, "--one", "--out", str(out), "--tasks", t, "--seeds", a.seeds]
            if a.cameras:
                cmd.append("--cameras")
            log = open(out / f"{t}.log", "w")
            procs.append((t, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())))
        time.sleep(2)
        for t, p in list(procs):
            if p.poll() is not None:
                procs.remove((t, p))
                print(f"[idle] {t} finished with code {p.returncode}", flush=True)
                if p.returncode:
                    failed.append(t)
    print(f"[idle] done; failed: {failed or 'none'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
