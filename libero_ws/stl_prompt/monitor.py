"""Offline STL monitoring of LIBERO recordings written by launch_eval.py, using rtamt.

Usage (in the rtamt venv, not the pixi env):
  python monitor.py [options] <trace_dir> [<trace_dir> ...]

Each trace dir is <run>/<variant>/traces. The suite is read from the recordings.

libero_goal (spec kind "bddl"); per episode:
  task_rob  robustness of the task's STL spec at t=0 (>0 means satisfied)
  libero    LIBERO's own success flag (goal predicates true at some step)
  moved     movable objects not named in the spec that moved > 5 cm, from the
            side-effect spec  always(disp_<obj> < 0.05)
  clean     task spec satisfied and no other object moved
  F<=Ns     task spec with the outer deadline tightened to N seconds

libero_spatial (spec kind "bowl_on_plate", see stl_spec.BowlOnPlateSpec); per episode:
  task_success  LIBERO's success flag at any step (the standard benchmark number)
  grasp_first   (!On(b,p) U Grasp(b))
  deadline      F[0,9s] G[0,2s] Rest(b,p)
  no_move_<o>   G[0,11s] !Disturbed(o), and no_move = all of them
  undisturbed   G !Disturbed(o) for every o in O over the whole episode, where Disturbed(o) = centre moved
                > 2 cm from its start or up-axis tipped > 10 deg (yaw ignored)
  clean         task_success and undisturbed
  full_stl      grasp_first and deadline and no_move
  *_moved5      the first definitions, with Moved(o) = centre moved > 5 cm in the first 11 s, for comparison
plus diagnostics (first grasp, landing, rest start, longest rest, max displacement per object).
Every verdict is computed twice, by rtamt and by a plain-numpy check; any disagreement is reported.
Writes <run>/<variant>/episodes.csv and prints markdown summary tables.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import rtamt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stl_spec import BowlOnPlateSpec, Thresholds  # noqa: E402

HERE = Path(__file__).resolve().parent
OLD_GOAL_MOVABLE = ["akita_black_bowl_1", "cream_cheese_1", "wine_bottle_1", "plate_1"]  # libero_goal scene
DISP_LIMIT = 0.05  # metres, libero_goal side-effect check
DEADLINES_S = (5, 10)
HZ = 20


# ---------------------------------------------------------------- loading ----


def load_trace(path: Path, specs: dict | None) -> dict:
    """Read a recording and normalise it to the current format (2).

    Format 1 (the libero_goal run) had `atoms` (signals), `pos` (positions only,
    for every object state incl. regions) and `rtamt`, but no spec copy.
    """
    t = json.loads(path.read_text())
    t["file"] = path.name
    if t.get("format", 1) >= 2:
        return t
    spec = dict((specs or {}).get(t["suite"], {}).get(str(t["task_id"]), {}))
    spec.setdefault("kind", "bddl")
    spec.setdefault("movable", OLD_GOAL_MOVABLE)
    spec["rtamt"] = t["rtamt"]
    t["spec"] = spec
    t["signals"] = t.pop("atoms")
    t["objects"] = {name: {"pos": p} for name, p in t.pop("pos").items()}
    t["episode"] = int(path.stem.rsplit("_ep", 1)[1])
    t["format"] = 1
    return t


# ----------------------------------------------------------------- rtamt -----


def robustness(spec_str: str, signals: dict[str, list[float]]) -> float:
    """Robustness at t=0 of an rtamt discrete-time spec (one sample per step)."""
    spec = rtamt.StlDiscreteTimeSpecification()
    for name in signals:
        spec.declare_var(name, "float")
    spec.spec = spec_str
    spec.parse()
    n = len(next(iter(signals.values())))
    data = {"time": list(range(n)), **{k: [float(x) for x in v] for k, v in signals.items()}}
    out = spec.evaluate(data)
    return float(out[0][1])


def holds(spec_str: str, signals: dict[str, list[float]]) -> bool:
    used = {k: v for k, v in signals.items() if k in spec_str}
    return robustness(spec_str, used) > 0


# ------------------------------------------------------------ libero_goal ----


def check_goal(trace: dict) -> dict:
    spec = trace["spec"]
    task_rob = robustness(spec["rtamt"], trace["signals"])
    movable = spec["movable"]
    spec_objs = {o for sig in trace["signals"] for o in movable if o in sig}
    moved = []
    for obj in movable:
        if obj in spec_objs or obj not in trace["objects"]:
            continue
        p = trace["objects"][obj]["pos"]
        disp = [math.dist(q, p[0]) for q in p]
        if robustness(f"always(disp < {DISP_LIMIT})", {"disp": disp}) < 0:
            moved.append(obj.removesuffix("_1"))
    # Same task spec with a tighter outer deadline (5 s and 10 s instead of 15 s).
    deadline = {}
    for secs in DEADLINES_S:
        tight = spec["rtamt"].replace("eventually[0:300]", f"eventually[0:{secs * HZ}]", 1)
        deadline[secs] = robustness(tight, trace["signals"]) > 0
    return {
        "task_rob": task_rob,
        "stl_sat": task_rob > 0,
        "libero": any(trace["success"]),
        "moved": moved,
        "clean": task_rob > 0 and not moved,
        "deadline": deadline,
        "steps": len(trace["success"]),
    }


def report_goal(rows: list[dict]):
    by = defaultdict(list)
    for r in rows:
        by[(r["variant"], r["task"])].append(r)
    print(f"{'variant':9s} {'task':>4s}  {'STL sat':>7s}  {'LIBERO':>6s}  agree  {'clean':>6s} moved-other-objects")
    for (v, task), rs in sorted(by.items()):
        sat = sum(r["stl_sat"] for r in rs)
        lib = sum(r["libero"] for r in rs)
        agree = all(r["stl_sat"] == r["libero"] for r in rs)
        moved = sorted({m for r in rs for m in r["moved"]})
        clean = sum(r["clean"] for r in rs)
        print(f"{v:9s} {task:>4d}  {sat:>3d}/{len(rs):<3d}  {lib:>2d}/{len(rs):<3d}  {str(agree):5s}  {clean:>2d}/{len(rs):<3d} {', '.join(moved)}")
    print()
    cols = ["stl_sat", "libero", "clean"] + [f"F<={d}s" for d in DEADLINES_S]
    print(f"{'variant':9s} " + " ".join(f"{c:>9s}" for c in cols) + "   (n episodes)")
    for v in sorted({r["variant"] for r in rows}):
        rs = [r for r in rows if r["variant"] == v]
        vals = [sum(r["stl_sat"] for r in rs), sum(r["libero"] for r in rs), sum(r["clean"] for r in rs)]
        vals += [sum(r["deadline"][d] for r in rs) for d in DEADLINES_S]
        print(f"{v:9s} " + " ".join(f"{100 * x / len(rs):8.0f}%" for x in vals) + f"   ({len(rs)})")


# --------------------------------------------------------- libero_spatial ----


def bowl_spec(spec: dict) -> BowlOnPlateSpec:
    return BowlOnPlateSpec(
        bowl=spec["bowl"],
        plate=spec["plate"],
        others=tuple(spec["others"]),
        bowl_name=spec["bowl_name"],
        land_by_s=spec["land_by_s"],
        rest_s=spec["rest_s"],
        still_s=spec["still_s"],
    )


def _quat_angle(q1: np.ndarray, q0: np.ndarray) -> np.ndarray:
    """Rotation angle (rad) between unit quaternions (wxyz), row-wise.

    Uses atan2(|v|, |w|) of the relative rotation q1 * conj(q0); 2*arccos(q1.q0) is ill-conditioned
    near 0 and turns 1e-5 rounding of the recorded quaternions into ~0.2 rad/s of fake spin.
    """
    w0, v0 = q0[:, :1], -q0[:, 1:]  # conj(q0)
    w1, v1 = q1[:, :1], q1[:, 1:]
    w = w1 * w0 - np.sum(v1 * v0, axis=1, keepdims=True)
    v = w1 * v0 + w0 * v1 + np.cross(v1, v0)
    return 2.0 * np.arctan2(np.linalg.norm(v, axis=1), np.abs(w[:, 0]))


def _tilt_deg(quat: np.ndarray) -> np.ndarray:
    """Angle (degrees) between the body's up-axis at each sample and at t=0. Quaternions are wxyz."""
    w, x, y, z = np.asarray(quat, dtype=float).T
    up = np.c_[2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]
    up /= np.linalg.norm(up, axis=1, keepdims=True)
    return np.degrees(np.arccos(np.clip(up @ up[0], -1.0, 1.0)))


def derive_signals(
    trace: dict, s: BowlOnPlateSpec, vel: str = "sim", grasp_lift: float | None = None
) -> dict[str, np.ndarray]:
    """All rtamt signals of the spec: recorded 0/1 signals plus speed, spin, displacement and tilt.

    vel="sim":  speed/spin are the simulator's body velocities at each sample.
    vel="pose": speed/spin are finite differences of the recorded poses over one step (0.05 s).
    grasp_lift: if set, Grasp(b) is replaced by "a gripper geom touches the bowl and the bowl is more than
                grasp_lift metres above its t=0 height" instead of robosuite's both-finger-pads check.
    """
    hz = trace.get("hz", HZ)
    sig = {k: np.asarray(trace["signals"][k], dtype=float) for k in (s.sig_on, s.sig_grasp, s.sig_contact)}
    bowl = trace["objects"][s.bowl]
    if grasp_lift is not None:
        z = np.asarray(bowl["pos"])[:, 2]
        sig[s.sig_grasp] = ((sig[s.sig_contact] > 0.5) & (z - z[0] > grasp_lift)).astype(float)
    if vel == "sim":
        speed = np.linalg.norm(np.asarray(bowl["linvel"]), axis=1)
        spin = np.linalg.norm(np.asarray(bowl["angvel"]), axis=1)
    elif vel == "pose":
        pos, quat = np.asarray(bowl["pos"]), np.asarray(bowl["quat"])
        speed = np.r_[0.0, np.linalg.norm(np.diff(pos, axis=0), axis=1) * hz]
        spin = np.r_[0.0, _quat_angle(quat[1:], quat[:-1]) * hz]
    else:
        raise ValueError(vel)
    sig[s.sig_speed] = speed
    sig[s.sig_spin] = spin
    for o in s.others:
        p = np.asarray(trace["objects"][o]["pos"])
        sig[s.sig_disp(o)] = np.linalg.norm(p - p[0], axis=1)
        sig[s.sig_tilt(o)] = _tilt_deg(trace["objects"][o]["quat"])
    return sig


def rest_mask(sig: dict[str, np.ndarray], s: BowlOnPlateSpec, th: Thresholds) -> np.ndarray:
    return (
        (sig[s.sig_on] > 0.5)
        & (sig[s.sig_contact] < 0.5)
        & (sig[s.sig_speed] < th.rest_speed)
        & (sig[s.sig_spin] < th.rest_spin)
    )


def _first(mask: np.ndarray) -> int | None:
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def _window_starts(mask: np.ndarray, length: int) -> np.ndarray:
    """Bool per t: mask holds on every sample t..t+length (inclusive). False where the window runs off the end."""
    n = len(mask)
    out = np.zeros(n, dtype=bool)
    for t in range(n - length):
        out[t] = mask[t : t + length + 1].all()
    return out


def _longest_run(mask: np.ndarray) -> int:
    best = run = 0
    for v in mask:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def python_parts(sig: dict[str, np.ndarray], s: BowlOnPlateSpec, th: Thresholds) -> dict[str, bool]:
    """The same verdicts as parts_rtamt, written out directly with numpy."""
    on, grasp = sig[s.sig_on] > 0.5, sig[s.sig_grasp] > 0.5
    g = _first(grasp)
    out = {"grasp_first": g is not None and not on[:g].any()}
    starts = _window_starts(rest_mask(sig, s, th), s.rest_for)
    out["deadline"] = bool(starts[: s.land_by + 1].any())
    for o in s.others:
        w = slice(0, s.still_for + 1)
        out[f"no_move_{o}"] = bool(((sig[s.sig_disp(o)][w] < th.disturb_disp) & (sig[s.sig_tilt(o)][w] < th.disturb_tilt)).all())
    return out


def python_undisturbed(sig: dict[str, np.ndarray], s: BowlOnPlateSpec, th: Thresholds) -> dict[str, bool]:
    """The same verdicts as undisturbed_rtamt, written out directly with numpy."""
    return {
        f"undisturbed_{o}": bool(((sig[s.sig_disp(o)] < th.disturb_disp) & (sig[s.sig_tilt(o)] < th.disturb_tilt)).all())
        for o in s.others
    }


def check_spatial(trace: dict, th: Thresholds, vel: str = "sim", grasp_lift: float | None = None) -> dict:
    s = bowl_spec(trace["spec"])
    hz = trace.get("hz", HZ)
    sig = derive_signals(trace, s, vel, grasp_lift)
    lists = {k: v.tolist() for k, v in sig.items()}
    parts = {name: holds(f, lists) for name, f in s.parts_rtamt(th).items()}
    py = python_parts(sig, s, th)
    undist = {name: holds(f, lists) for name, f in s.undisturbed_rtamt(th).items()}
    py_undist = python_undisturbed(sig, s, th)
    no_move = all(parts[f"no_move_{o}"] for o in s.others)
    no_move_moved5 = all(bool((sig[s.sig_disp(o)][: s.still_for + 1] < th.moved_disp).all()) for o in s.others)
    undisturbed = all(undist.values())
    disturbed = np.zeros(len(trace["success"]), dtype=bool)
    for o in s.others:
        disturbed |= (sig[s.sig_disp(o)] >= th.disturb_disp) | (sig[s.sig_tilt(o)] >= th.disturb_tilt)
    task_success = any(trace["success"])
    rest = rest_mask(sig, s, th)
    starts = _window_starts(rest, s.rest_for)

    def secs(step):
        return None if step is None else round(step / hz, 2)

    row = {
        "task_success": task_success,
        "grasp_first": parts["grasp_first"],
        "deadline": parts["deadline"],
        "no_move": no_move,
        "undisturbed": undisturbed,
        "clean": task_success and undisturbed,
        "full_stl": parts["grasp_first"] and parts["deadline"] and no_move,
        # The first definitions (Moved = centre > 5 cm, first 11 s), for comparison.
        "no_move_moved5": no_move_moved5,
        "clean_moved5": task_success and no_move_moved5,
        "full_stl_moved5": parts["grasp_first"] and parts["deadline"] and no_move_moved5,
        **{k: v for k, v in parts.items() if k.startswith("no_move_")},
        **undist,
        "first_grasp_s": secs(_first(sig[s.sig_grasp] > 0.5)),
        "landing_s": secs(_first(sig[s.sig_on] > 0.5)),
        "rest_start_s": secs(_first(starts)),
        "longest_rest_s": round(_longest_run(rest) / hz, 2),
        **{f"max_disp_{o}": round(float(sig[s.sig_disp(o)][: s.still_for + 1].max()), 4) for o in s.others},
        "first_disturbed_s": secs(_first(disturbed)),
        **{f"max_disp_all_{o}": round(float(sig[s.sig_disp(o)].max()), 4) for o in s.others},
        **{f"max_tilt_deg_{o}": round(float(sig[s.sig_tilt(o)].max()), 1) for o in s.others},
        "steps": len(trace["success"]),
        # Consistency checks: rtamt vs numpy, and LIBERO's flag vs the recorded On signal.
        "rtamt_eq_numpy": parts == py and undist == py_undist,
        "libero_eq_on": task_success == bool((sig[s.sig_on] > 0.5).any()),
    }
    return row


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


SPATIAL_METRICS = [
    ("task_success", "Task success"),
    ("deadline", "Deadline met"),
    ("clean", "Clean success"),
    ("full_stl", "Full STL"),
]
VARIANT_ORDER = ["nl", "stl_nl", "stl", "stl_bddl"]


def _vkey(v: str):
    return (VARIANT_ORDER.index(v) if v in VARIANT_ORDER else len(VARIANT_ORDER), v)


def report_spatial(rows: list[dict], specs: dict | None):
    variants = sorted({r["variant"] for r in rows}, key=_vkey)
    tasks = sorted({r["task"] for r in rows})

    def pct(k, n):
        lo, hi = wilson(k, n)
        return f"{k}/{n} [{100 * lo:.0f}–{100 * hi:.0f}%]"

    print("**Summary** (episodes that passed / episodes run; 95% Wilson range of the pass rate in brackets)\n")
    print("| Prompt | " + " | ".join(label for _, label in SPATIAL_METRICS) + " |")
    print("| --- | " + " | ".join("---" for _ in SPATIAL_METRICS) + " |")
    for v in variants:
        rs = [r for r in rows if r["variant"] == v]
        cells = [pct(sum(r[m] for r in rs), len(rs)) for m, _ in SPATIAL_METRICS]
        print(f"| `{v}` | " + " | ".join(cells) + " |")

    print("\n**Parts of φ and diagnostics** (counts; times are medians over episodes where the event happened)\n")
    print("| Prompt | grasp first | deadline | no move (all O) | " + " | ".join(
        f"{o} still" for o in sorted({k[12:] for r in rows for k in r if k.startswith("undisturbed_")})) +
        " | first grasp s | landing s | longest rest s |")
    others = sorted({k[12:] for r in rows for k in r if k.startswith("undisturbed_")})
    print("| --- " * (7 + len(others)) + "|")
    for v in variants:
        rs = [r for r in rows if r["variant"] == v]
        n = len(rs)

        def med(key):
            xs = [r[key] for r in rs if r[key] is not None]
            return f"{np.median(xs):.2f} ({len(xs)})" if xs else "–"

        cells = [f"{sum(r['grasp_first'] for r in rs)}/{n}", f"{sum(r['deadline'] for r in rs)}/{n}",
                 f"{sum(r['no_move'] for r in rs)}/{n}"]
        cells += [f"{sum(r[f'no_move_{o}'] for r in rs)}/{n}" for o in others]
        cells += [med("first_grasp_s"), med("landing_s"), med("longest_rest_s")]
        print(f"| `{v}` | " + " | ".join(cells) + " |")

    print("\n**Other objects** (episodes where it was never disturbed: moved < 2 cm and tipped < 10° for the whole"
          " episode; \"old\" = the first Moved check, centre moved < 5 cm in the first 11 s)\n")
    print("| Prompt | undisturbed (all O) | " + " | ".join(f"{o} undisturbed" for o in others)
          + " | old: no move (all O) | clean success | clean success (old) | full STL | full STL (old) |")
    print("| --- " * (7 + len(others)) + "|")
    for v in variants:
        rs = [r for r in rows if r["variant"] == v]
        n = len(rs)
        cells = [f"{sum(r['undisturbed'] for r in rs)}/{n}"]
        cells += [f"{sum(r[f'undisturbed_{o}'] for r in rs)}/{n}" for o in others]
        cells += [f"{sum(r['no_move_moved5'] for r in rs)}/{n}", f"{sum(r['clean'] for r in rs)}/{n}",
                  f"{sum(r['clean_moved5'] for r in rs)}/{n}", f"{sum(r['full_stl'] for r in rs)}/{n}",
                  f"{sum(r['full_stl_moved5'] for r in rs)}/{n}"]
        print(f"| `{v}` | " + " | ".join(cells) + " |")

    for metric, label in SPATIAL_METRICS:
        print(f"\n**Per task: {label.lower()}** (out of n per cell)\n")
        print("| # | " + " | ".join(f"`{v}`" for v in variants) + " |")
        print("| --- | " + " | ".join("---" for _ in variants) + " |")
        for t in tasks:
            cells = []
            for v in variants:
                rs = [r for r in rows if r["variant"] == v and r["task"] == t]
                cells.append(f"{sum(r[metric] for r in rs)}/{len(rs)}" if rs else "–")
            print(f"| {t} | " + " | ".join(cells) + " |")

    lengths = sorted({r["steps"] for r in rows})
    print(f"\nrecorded samples per episode: {lengths}" + ("" if lengths == [281] else "  WARNING: expected 281 (reset + 280 steps)"))
    bad = [r for r in rows if not r["rtamt_eq_numpy"]]
    lib = [r for r in rows if not r["libero_eq_on"]]
    print(f"\nconsistency: rtamt == numpy in {len(rows) - len(bad)}/{len(rows)} episodes; "
          f"LIBERO success == any(On) in {len(rows) - len(lib)}/{len(rows)}")
    for r in bad + lib:
        print(f"  MISMATCH {r['variant']} task {r['task']} ep {r['episode']}: "
              f"rtamt_eq_numpy={r['rtamt_eq_numpy']} libero_eq_on={r['libero_eq_on']}")


def write_csv(rows: list[dict], path: Path):
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (int(v) if isinstance(v, bool) else v) for k, v in r.items()})


# ------------------------------------------------------------------- main ----


def run(
    dirs: list[str], specs: dict | None, th: Thresholds, vel: str, write: bool = True, grasp_lift: float | None = None
) -> list[dict]:
    rows = []
    for d in dirs:
        d_rows = []
        for f in sorted(Path(d).glob("*.json"), key=lambda p: (p.stem.rsplit("_ep", 1)[0], int(p.stem.rsplit("_ep", 1)[1]))):
            t = load_trace(f, specs)
            kind = t["spec"]["kind"]
            if kind == "bddl":
                r = check_goal(t)
            elif kind == "bowl_on_plate":
                r = check_spatial(t, th, vel, grasp_lift)
            else:
                raise ValueError(f"{f}: unknown spec kind {kind!r}")
            meta = dict(suite=t["suite"], kind=kind, variant=t["variant"], task=t["task_id"],
                        episode=t["episode"], init_state=t.get("init_state"), prompt=t["prompt"], file=f.name)
            d_rows.append({**meta, **r})
        if write and d_rows and d_rows[0]["kind"] == "bowl_on_plate":
            out = Path(d).parent / ("episodes.csv" if grasp_lift is None else f"episodes_grasp_lift_{grasp_lift:g}.csv")
            write_csv(d_rows, out)
            print(f"wrote {out} ({len(d_rows)} episodes)")
        rows += d_rows
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", help="trace directories")
    ap.add_argument("--specs", default=str(HERE / "specs.json"), help="specs.json (needed for format-1 recordings)")
    ap.add_argument("--rest-speed", type=float, default=Thresholds.rest_speed, help="m/s")
    ap.add_argument("--rest-spin", type=float, default=Thresholds.rest_spin, help="rad/s")
    ap.add_argument("--moved-disp", type=float, default=Thresholds.moved_disp, help="m")
    ap.add_argument("--vel", choices=["sim", "pose"], default="sim", help="bowl speed/spin source")
    ap.add_argument("--disturb-disp", type=float, default=Thresholds.disturb_disp, help="m, Disturbed(o) displacement")
    ap.add_argument("--disturb-tilt", type=float, default=Thresholds.disturb_tilt, help="degrees, Disturbed(o) tilt")
    ap.add_argument("--grasp-lift", type=float, default=None,
                    help="m; if set, Grasp = gripper contact and bowl lifted more than this (default: both finger pads)")
    ap.add_argument("--json-out", help="also write all per-episode rows to this JSON file")
    ap.add_argument("--no-write", action="store_true", help="do not write episodes.csv files")
    a = ap.parse_args(argv)
    specs = json.loads(Path(a.specs).read_text()) if a.specs and Path(a.specs).exists() else None
    th = Thresholds(rest_speed=a.rest_speed, rest_spin=a.rest_spin, moved_disp=a.moved_disp,
                    disturb_disp=a.disturb_disp, disturb_tilt=a.disturb_tilt)
    rows = run(a.dirs, specs, th, a.vel, write=not a.no_write, grasp_lift=a.grasp_lift)
    goal = [r for r in rows if r["kind"] == "bddl"]
    spatial = [r for r in rows if r["kind"] == "bowl_on_plate"]
    if goal:
        report_goal(goal)
    if spatial:
        grasp = "both finger pads" if a.grasp_lift is None else f"gripper contact + lifted > {a.grasp_lift:g} m"
        print(f"\nthresholds: {th}  velocities: {a.vel}  grasp: {grasp}\n")
        report_spatial(spatial, specs)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(rows, indent=1))
        print(f"\nwrote {a.json_out}")
    return rows


if __name__ == "__main__":
    main()
