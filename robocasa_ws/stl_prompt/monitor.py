"""Offline STL checking of RoboCasa recordings (written by launch_eval.py or idle_check.py), using rtamt.

Usage (in the rtamt venv, not the pixi env):
  python monitor.py [options] <dir> [<dir> ...]

Each <dir> is searched recursively for *.json.gz recordings, e.g. eval_logs_stl/nl (one subfolder per
task). Writes <dir>/episodes.csv (one row per episode) and prints markdown tables.

Per episode (see stl_spec.py and docs/2026-10-31-robocasa-experiment.md):
  task_success  RoboCasa's _check_success() at any step (the benchmark number)
  deadline      F[0,T] G Rest: done and at rest by T, and still at rest at the last step
  undisturbed   G !Disturbed(o) for every o in O over the whole episode, where Disturbed(o) = centre moved
                > 2 cm from its reference pose, or rotated > 10 deg about any axis since then. The reference is
                the pose once o has settled (still for 10 samples; at most 2 s in, and before the gripper first
                touches it), because some objects are still rolling at t=0 (idle check). --ref t0 uses t=0.
  clean         task_success and undisturbed
  full_stl      deadline and undisturbed (= all of phi)
plus diagnostics (first success, rest start, longest rest, first grasp by both definitions, pushed_in,
bumped, largest displacement / rotation of every o in O, fixture_changed, LIBERO's tilt-only Disturbed)
and the cause of each deadline failure. Every verdict is computed twice, by rtamt and by plain numpy;
any disagreement is reported.

--idle checks idle-robot recordings instead: no success, no Disturbed, no fixture_changed expected.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stl_spec import (  # noqa: E402
    HZ, SIG_BASE_SPEED, SIG_BASE_TURN, SIG_CONTACT, SIG_FAR, SIG_JVEL, SIG_SPEED, SIG_SPIN, SIG_SUCCESS, TASKS,
    TaskSpec, Thresholds, sig_disp, sig_rot,
)

VARIANT_ORDER = ["nl", "stl_nl", "stl", "idle"]
METRICS = [("task_success", "Task success"), ("deadline", "Deadline met"), ("clean", "Clean success"),
           ("full_stl", "Full STL")]


# ---------------------------------------------------------------- loading ----


def load_trace(path: Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        t = json.load(f)
    t["file"] = str(path)
    return t


def find_traces(d: Path) -> list[Path]:
    def key(p: Path):
        stem = p.name.split(".")[0]
        task, ep = stem.rsplit("_ep", 1)
        return (TASKS[task].index if task in TASKS else 99, task, int(ep))

    return sorted(d.rglob("*.json.gz"), key=key)


def spec_of(t: dict) -> TaskSpec:
    return TaskSpec(task=t["task"], others=tuple(t["others"]), microwave=t["task"] == "TurnOnMicrowave")


# --------------------------------------------------------------- geometry ----


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise Hamilton product of wxyz quaternions."""
    w1, x1, y1, z1 = a.T
    w2, x2, y2, z2 = b.T
    return np.c_[w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                 w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2]


def quat_conj(q: np.ndarray) -> np.ndarray:
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def rot_angle(q1: np.ndarray, q0: np.ndarray) -> np.ndarray:
    """Rotation angle (rad) from q0 to q1, row-wise (wxyz). atan2 form: well-conditioned near 0."""
    r = quat_mul(q1, quat_conj(q0))
    return 2.0 * np.arctan2(np.linalg.norm(r[:, 1:], axis=1), np.abs(r[:, 0]))


def quat_rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate vectors v by quaternions q, row-wise."""
    qv = np.c_[np.zeros(len(v)), v]
    return quat_mul(quat_mul(q, qv), quat_conj(q))[:, 1:]


def tilt_deg(quat: np.ndarray) -> np.ndarray:
    """Angle (deg) between the body's up-axis at each sample and at t=0 (LIBERO's tilt; yaw ignored)."""
    up = quat_rotate(quat, np.tile([0.0, 0.0, 1.0], (len(quat), 1)))
    up /= np.linalg.norm(up, axis=1, keepdims=True)
    return np.degrees(np.arccos(np.clip(up @ up[0], -1.0, 1.0)))


def object_pose(t: dict, o: str) -> tuple[np.ndarray, np.ndarray]:
    """Position and orientation of object o, in its part's frame if it has one (OpenDrawer: the drawer)."""
    pos = np.asarray(t["objects"][o]["pos"], dtype=float)
    quat = np.asarray(t["objects"][o]["quat"], dtype=float)
    frame = t.get("frames_of", {}).get(o)
    if frame:
        fp = np.asarray(t["frames"][frame]["pos"], dtype=float)
        fq = np.asarray(t["frames"][frame]["quat"], dtype=float)
        pos = quat_rotate(quat_conj(fq), pos - fp)
        quat = quat_mul(quat_conj(fq), quat)
    return pos, quat


# ---------------------------------------------------------------- signals ----


def derive_signals(t: dict, s: TaskSpec, vel: str = "sim", ref: str = "settle",
                   th: Thresholds = Thresholds()) -> dict[str, np.ndarray]:
    """All rtamt signals of the task's spec."""
    hz = t.get("hz", HZ)
    n = len(t["success"])
    sig = {SIG_SUCCESS: np.asarray(t["success"], dtype=float)}
    if s.kind == "P":
        o = t["objects"][t["target"]]
        if vel == "sim":
            sig[SIG_SPEED] = np.linalg.norm(np.asarray(o["linvel"]), axis=1)
            sig[SIG_SPIN] = np.linalg.norm(np.asarray(o["angvel"]), axis=1)
        else:
            pos, quat = np.asarray(o["pos"]), np.asarray(o["quat"])
            sig[SIG_SPEED] = np.r_[0.0, np.linalg.norm(np.diff(pos, axis=0), axis=1) * hz]
            sig[SIG_SPIN] = np.r_[0.0, rot_angle(quat[1:], quat[:-1]) * hz]
    elif s.kind == "F":
        sig[SIG_CONTACT] = np.asarray(t["contact"]["part_gripper"], dtype=float)
        if vel == "sim":
            qv = [np.abs(np.asarray(v, dtype=float)) for v in t["goal_qvel"].values()]
        else:  # finite differences of the recorded joint positions
            q = np.asarray(t["joints"], dtype=float)
            idx = [t["joint_names"].index(j) for j in t["goal_joints"]]
            qv = [np.r_[0.0, np.abs(np.diff(q[:, i])) * hz] for i in idx]
        sig[SIG_JVEL] = np.max(qv, axis=0) if qv else np.zeros(n)
        if s.microwave:
            sig[SIG_FAR] = np.asarray(t["success_parts"]["gripper_far"], dtype=float)
    else:
        sig[SIG_BASE_SPEED] = np.linalg.norm(np.asarray(t["base"]["linvel"]), axis=1)
        sig[SIG_BASE_TURN] = np.linalg.norm(np.asarray(t["base"]["angvel"]), axis=1)
    for o in s.others:
        pos, quat = object_pose(t, o)
        k = ref_index(t, o, ref, th)
        sig[sig_disp(o)] = np.linalg.norm(pos - pos[k], axis=1)
        sig[sig_rot(o)] = np.degrees(rot_angle(quat, np.tile(quat[k], (n, 1))))
        if k:
            sig[sig_disp(o)][:k] = 0.0  # settling before the reference sample isn't counted
            sig[sig_rot(o)][:k] = 0.0
    return sig


SETTLE_RUN = 10  # samples the object must be still for
SETTLE_MAX = 40  # latest reference sample (2 s)


def ref_index(t: dict, o: str, ref: str, th: Thresholds) -> int:
    """Sample whose pose Disturbed(o) is measured from.

    ref="t0": sample 0. ref="settle": the first sample from which o is Still for SETTLE_RUN samples, but no
    later than SETTLE_MAX or the gripper's first contact with o (objects can still be rolling at t=0)."""
    if ref == "t0":
        return 0
    lin = np.linalg.norm(np.asarray(t["objects"][o]["linvel"]), axis=1)
    ang = np.linalg.norm(np.asarray(t["objects"][o]["angvel"]), axis=1)
    still = (lin < th.still_speed) & (ang < th.still_spin)
    cap = SETTLE_MAX
    touch = first(np.asarray(t["contact"]["gripper"].get(o, []), dtype=bool))
    if touch is not None:
        cap = min(cap, touch)
    for k in range(cap + 1):
        if still[k : k + SETTLE_RUN].all():
            return k
    return cap


# ------------------------------------------------------------------ rtamt ----


def robustness(spec_str: str, signals: dict[str, np.ndarray]) -> float:
    """Robustness at t=0 of an rtamt discrete-time spec (one sample per step)."""
    import rtamt

    spec = rtamt.StlDiscreteTimeSpecification()
    used = {k: v for k, v in signals.items() if k in spec_str}
    for name in used:
        spec.declare_var(name, "float")
    spec.spec = spec_str
    spec.parse()
    n = len(next(iter(used.values())))
    data = {"time": list(range(n)), **{k: [float(x) for x in v] for k, v in used.items()}}
    return float(spec.evaluate(data)[0][1])


def holds(spec_str: str, signals: dict[str, np.ndarray]) -> bool:
    return robustness(spec_str, signals) > 0


# ------------------------------------------------------------------ numpy ----


def term_masks(sig: dict, s: TaskSpec, th: Thresholds) -> dict[str, np.ndarray]:
    return {name: (sig[k] > b) if op == ">" else (sig[k] < b) for name, k, op, b in s.rest_terms(th)}


def rest_mask(sig: dict, s: TaskSpec, th: Thresholds) -> np.ndarray:
    return np.logical_and.reduce(list(term_masks(sig, s, th).values()))


def until_end_starts(mask: np.ndarray) -> np.ndarray:
    """Bool per t: mask holds on every sample from t to the end of the episode."""
    return np.flip(np.logical_and.accumulate(np.flip(mask)))


def first(mask) -> int | None:
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def longest_run(mask: np.ndarray) -> int:
    best = run = 0
    for v in mask:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def undisturbed_mask(sig: dict, o: str, th: Thresholds) -> np.ndarray:
    return (sig[sig_disp(o)] < th.disturb_disp) & (sig[sig_rot(o)] < th.disturb_rot)


def python_parts(sig: dict, s: TaskSpec, th: Thresholds) -> dict[str, bool]:
    out = {"deadline": bool(until_end_starts(rest_mask(sig, s, th))[: s.deadline + 1].any())}
    for o in s.others:
        out[f"undisturbed_{o}"] = bool(undisturbed_mask(sig, o, th).all())
    return out


# -------------------------------------------------------------- diagnosis ----

GOAL, GRIP, MOTION = "goal", "gripper", "motion"


def failing_reason(t: dict, s: TaskSpec, masks: dict[str, np.ndarray], k: int) -> str:
    """Why Rest fails at step k: the goal itself (goal), the gripper (near / touching), or motion."""
    if not masks["success"][k]:
        parts = t.get("success_parts", {})
        if s.kind == "P" and parts:
            placed = all(v[k] for name, v in parts.items() if name != "gripper_far")
            return GRIP if placed else GOAL
        if s.microwave:
            return GOAL if not parts["turned_on"][k] else GRIP
        return GOAL
    if "released" in masks and not masks["released"][k]:
        return GRIP
    return MOTION


CAUSE_LABEL = {
    "never": "never done",
    "late": "first done after T",
    ("end", GOAL): "done by T, undone at the end",
    ("end", GRIP): "done by T, gripper near / touching at the end",
    ("end", MOTION): "done by T, still moving at the end",
    ("after", GOAL): "done by T, undone, redone after T",
    ("after", GRIP): "done by T, gripper near / touching until after T",
    ("after", MOTION): "done by T, settled only after T",
}


def deadline_cause(t: dict, s: TaskSpec, sig: dict, th: Thresholds) -> str | None:
    masks = term_masks(sig, s, th)
    rest = np.logical_and.reduce(list(masks.values()))
    starts = until_end_starts(rest)
    if starts[: s.deadline + 1].any():
        return None
    f = first(masks["success"])
    if f is None:
        return CAUSE_LABEL["never"]
    if f > s.deadline:
        return CAUSE_LABEL["late"]
    r = first(starts)
    if r is None:
        return CAUSE_LABEL[("end", failing_reason(t, s, masks, len(rest) - 1))]
    return CAUSE_LABEL[("after", failing_reason(t, s, masks, r - 1))]


def placement_mask(t: dict, s: TaskSpec) -> np.ndarray:
    """P: the placement part of RoboCasa's success (everything except the gripper-far check)."""
    parts = {k: v for k, v in t.get("success_parts", {}).items() if k != "gripper_far"}
    if not parts:
        return np.asarray(t["success"], dtype=bool)
    return np.logical_and.reduce([np.asarray(v, dtype=bool) for v in parts.values()])


def fixture_changes(t: dict, th: Thresholds) -> dict[str, float]:
    """Largest |qpos - qpos(t=0)| of every fixture joint that isn't a goal joint, above the threshold."""
    q = np.asarray(t["joints"], dtype=float)
    dq = np.abs(q - q[0]).max(axis=0)
    goal = set(t.get("goal_joints", []))
    return {n: round(float(v), 4) for n, v in zip(t["joint_names"], dq) if n not in goal and v > th.fixture_changed}


# ------------------------------------------------------------------ check ----


def check(t: dict, th: Thresholds, vel: str = "sim", ref: str = "settle") -> dict:
    s = spec_of(t)
    hz = t.get("hz", HZ)
    sig = derive_signals(t, s, vel, ref, th)
    rt = {"deadline": holds(s.deadline_rtamt(th), sig)}
    rt.update({f"undisturbed_{o}": holds(f, sig) for o, f in s.undisturbed_rtamt(th).items()})
    py = python_parts(sig, s, th)
    undisturbed = all(rt[f"undisturbed_{o}"] for o in s.others)
    task_success = any(t["success"])
    masks = term_masks(sig, s, th)
    rest = np.logical_and.reduce(list(masks.values()))
    n = len(rest)

    def secs(step):
        return None if step is None else round(step / hz, 2)

    disturbed_any = np.zeros(n, dtype=bool)
    for o in s.others:
        disturbed_any |= ~undisturbed_mask(sig, o, th)
    tilt_ok = {}
    for o in s.others:
        pos, quat = object_pose(t, o)
        k = ref_index(t, o, ref, th)
        tilt = tilt_deg(quat[k:])
        tilt_ok[o] = bool(((sig[sig_disp(o)][k:] < th.disturb_disp) & (tilt < th.disturb_tilt)).all())

    first_success = first(masks["success"])
    row = {
        "task_success": task_success,
        "deadline": rt["deadline"],
        "undisturbed": undisturbed,
        "clean": task_success and undisturbed,
        "full_stl": rt["deadline"] and undisturbed,
        "deadline_cause": deadline_cause(t, s, sig, th),
        "first_success_s": secs(first_success),
        "rest_start_s": secs(first(until_end_starts(rest))),
        "longest_rest_s": round(longest_run(rest) / hz, 2),
        "success_at_end": bool(t["success"][-1]),
        "n_others": len(s.others),
        "disturbed_objects": " ".join(o for o in s.others if not rt[f"undisturbed_{o}"]),
        "first_disturbed_s": secs(first(disturbed_any)),
        "undisturbed_tilt_only": all(tilt_ok.values()),
    }
    # grasp and how the goal was reached (diagnostics only, decision 26)
    tgt = t.get("target")
    if s.kind == "P" and tgt:
        z = np.asarray(t["objects"][tgt]["pos"])[:, 2]
        touch = np.asarray(t["contact"]["gripper"][tgt], dtype=bool)
        grasp_lift = touch & (z - z[0] > th.grasp_lift)
        g = first(grasp_lift)
        placed = first(placement_mask(t, s))
        row["first_grasp_lift_s"] = secs(g)
        row["first_grasp_pads_s"] = secs(first(np.asarray(t["contact"]["pads"][tgt], dtype=bool)))
        row["first_placed_s"] = secs(placed)
        row["pushed_in"] = placed is not None and (g is None or placed < g)
    if s.kind == "F":
        pc = first(np.asarray(t["contact"]["part_gripper"], dtype=bool))
        row["first_part_contact_s"] = secs(pc)
        row["first_part_robot_contact_s"] = secs(first(np.asarray(t["contact"]["part_robot"], dtype=bool)))
        row["bumped"] = first_success is not None and (pc is None or first_success < pc)
    fc = fixture_changes(t, th)
    row["fixture_changed"] = bool(fc)
    row["fixture_changed_joints"] = " ".join(f"{k}:{v}" for k, v in fc.items())
    for o in s.others:
        row[f"undisturbed_{o}"] = rt[f"undisturbed_{o}"]
        row[f"max_disp_{o}"] = round(float(sig[sig_disp(o)].max()), 4)
        row[f"max_rot_deg_{o}"] = round(float(sig[sig_rot(o)].max()), 1)
    row["steps"] = n - 1
    row["rtamt_eq_numpy"] = rt == py
    return row


# ---------------------------------------------------------------- reports ----


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value (binomial test on the discordant pairs)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def _vkey(v: str):
    return (VARIANT_ORDER.index(v) if v in VARIANT_ORDER else len(VARIANT_ORDER), v)


def _tkey(task: str):
    return TASKS[task].index if task in TASKS else 99


def report(rows: list[dict]):
    variants = sorted({r["variant"] for r in rows}, key=_vkey)
    tasks = sorted({r["task"] for r in rows}, key=_tkey)

    def sel(v=None, task=None):
        return [r for r in rows if (v is None or r["variant"] == v) and (task is None or r["task"] == task)]

    print("**Summary** (episodes that passed / episodes run; 95% Wilson range of the pass rate in brackets)\n")
    print("| Prompt | " + " | ".join(label for _, label in METRICS) + " |")
    print("| --- " * (len(METRICS) + 1) + "|")
    for v in variants:
        rs = sel(v)
        cells = []
        for m, _ in METRICS:
            k, n = sum(r[m] for r in rs), len(rs)
            lo, hi = wilson(k, n)
            cells.append(f"{k}/{n} [{100 * lo:.0f}–{100 * hi:.0f}%]")
        print(f"| `{v}` | " + " | ".join(cells) + " |")

    print("\n**Per task** (out of the episodes run; cells are `" + "` / `".join(variants) + "`)\n")
    print("| # | Task | Type | Task success | Clean success | Deadline met / Full STL |")
    print("| --- | --- | --- | --- | --- | --- |")
    for task in tasks:
        info = TASKS[task]

        def cell(m):
            return " / ".join(str(sum(r[m] for r in sel(v, task))) for v in variants)

        dl = " · ".join(f"{sum(r['deadline'] for r in sel(v, task))} / {sum(r['full_stl'] for r in sel(v, task))}"
                        for v in variants)
        print(f"| {info.index} | {task} | {info.kind} | {cell('task_success')} | {cell('clean')} | {dl} |")

    if len(variants) > 1:
        print("\n**Paired by seed** (exact McNemar; gained = passes with the second prompt only, lost = the first only)\n")
        print("| Comparison | Metric | gained | lost | p |")
        print("| --- | --- | --- | --- | --- |")
        by = {(r["variant"], r["task"], r["seed"]): r for r in rows}
        for a, b in [("nl", "stl_nl"), ("nl", "stl"), ("stl_nl", "stl")]:
            if a not in variants or b not in variants:
                continue
            keys = [(task, seed) for (v, task, seed) in by if v == a and (b, task, seed) in by]
            for m, label in METRICS:
                gained = sum(1 for k in keys if by[(b, *k)][m] and not by[(a, *k)][m])
                lost = sum(1 for k in keys if by[(a, *k)][m] and not by[(b, *k)][m])
                print(f"| `{b}` vs `{a}` | {label} | {gained} | {lost} | {mcnemar_p(gained, lost):.2g} |")

    print("\n**Why each deadline failure happened**\n")
    causes = sorted({r["deadline_cause"] for r in rows if r["deadline_cause"]})
    print("| Cause | " + " | ".join(f"`{v}`" for v in variants) + " |")
    print("| --- " * (len(variants) + 1) + "|")
    for c in causes:
        print(f"| {c} | " + " | ".join(str(sum(r["deadline_cause"] == c for r in sel(v))) for v in variants) + " |")
    print("| **total** | " + " | ".join(f"**{sum(not r['deadline'] for r in sel(v))}**" for v in variants) + " |")

    print("\n**Other objects disturbed** (episodes with at least one o in O disturbed; tasks with O non-empty)\n")
    print("| Task | " + " | ".join(f"`{v}`" for v in variants) + " | objects (all prompts) |")
    print("| --- " * (len(variants) + 2) + "|")
    for task in tasks:
        if not any(r["n_others"] for r in sel(task=task)):
            continue
        cells = [f"{sum(not r['undisturbed'] for r in sel(v, task))}/{len(sel(v, task))}" for v in variants]
        objs = Counter(o for r in sel(task=task) for o in r["disturbed_objects"].split())
        print(f"| {task} | " + " | ".join(cells) + " | " + ", ".join(f"{o} ×{k}" for o, k in objs.most_common()) + " |")

    print("\n**Diagnostics** (counts)\n")
    print("| Prompt | pushed in (P) | bumped (F) | fixture changed | tilt-only undisturbed | success at end |")
    print("| --- | --- | --- | --- | --- | --- |")
    for v in variants:
        rs = sel(v)
        p = [r for r in rs if "pushed_in" in r]
        f = [r for r in rs if "bumped" in r]
        print(f"| `{v}` | {sum(r['pushed_in'] for r in p)}/{len(p)} | {sum(r['bumped'] for r in f)}/{len(f)} | "
              f"{sum(r['fixture_changed'] for r in rs)}/{len(rs)} | {sum(r['undisturbed_tilt_only'] for r in rs)}/{len(rs)}"
              f" | {sum(r['success_at_end'] for r in rs)}/{len(rs)} |")
    consistency(rows)


def consistency(rows: list[dict]):
    bad_len = [r for r in rows if r["steps"] != TASKS[r["task"]].horizon]
    bad = [r for r in rows if not r["rtamt_eq_numpy"]]
    lr = [r for r in rows if r.get("lerobot_success") is not None]
    bad_lr = [r for r in lr if r["lerobot_success"] != r["task_success"]]
    print(f"\nconsistency: steps == task limit in {len(rows) - len(bad_len)}/{len(rows)}; rtamt == numpy in "
          f"{len(rows) - len(bad)}/{len(rows)}; lerobot-eval success == any(success) in {len(lr) - len(bad_lr)}/{len(lr)}")
    for r in bad_len + bad + bad_lr:
        print(f"  MISMATCH {r['variant']} {r['task']} ep {r['episode']}: steps={r['steps']} "
              f"rtamt_eq_numpy={r['rtamt_eq_numpy']} lerobot={r.get('lerobot_success')} ours={r['task_success']}")


def report_idle(rows: list[dict], traces: dict[str, dict], th: Thresholds):
    """Idle-robot check: nothing should succeed, be disturbed, or change."""
    print("**Idle-robot check** (zero actions; expect no success, no Disturbed, no fixture_changed)\n")
    print("| # | Task | episodes | success | disturbed | fixture changed | max disp m (object) | max rot ° (object) |"
          " max joint drift (joint) | max |v| of O at t=0 m/s, rad/s |")
    print("| --- " * 10 + "|")
    for task in sorted({r["task"] for r in rows}, key=_tkey):
        rs = [r for r in rows if r["task"] == task]
        disp = max(((r[k], k[9:]) for r in rs for k in r if k.startswith("max_disp_")), default=(0, "–"))
        rot = max(((r[k], k[12:]) for r in rs for k in r if k.startswith("max_rot_deg_")), default=(0, "–"))
        drift, lin0, ang0 = (0.0, "–"), 0.0, 0.0
        for r in rs:
            t = traces[r["file"]]
            q = np.asarray(t["joints"], dtype=float)
            dq = np.abs(q - q[0]).max(axis=0)
            if len(dq) and dq.max() > drift[0]:
                drift = (float(dq.max()), t["joint_names"][int(dq.argmax())])
            for o in t["others"]:
                lin0 = max(lin0, float(np.linalg.norm(t["objects"][o]["linvel"][0])))
                ang0 = max(ang0, float(np.linalg.norm(t["objects"][o]["angvel"][0])))
        print(f"| {TASKS[task].index} | {task} | {len(rs)} | {sum(r['task_success'] for r in rs)} | "
              f"{sum(not r['undisturbed'] for r in rs)} | {sum(r['fixture_changed'] for r in rs)} | "
              f"{disp[0]:.4f} ({disp[1]}) | {rot[0]:.2f} ({rot[1]}) | {drift[0]:.4f} ({drift[1]}) | {lin0:.4f}, {ang0:.3f} |")
    flagged = [r for r in rows if r["task_success"] or not r["undisturbed"] or r["fixture_changed"]]
    print(f"\nflagged episodes: {len(flagged)}")
    for r in flagged:
        print(f"  {r['task']} ep {r['episode']}: success={r['task_success']} disturbed='{r['disturbed_objects']}' "
              f"fixture_changed='{r['fixture_changed_joints']}'")
    consistency(rows)


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


def lerobot_successes(trace_path: Path) -> list[bool] | None:
    """Per-episode successes from lerobot-eval's eval_info.json next to the traces folder, if any."""
    for d in (trace_path.parent.parent, trace_path.parent):
        f = d / "eval_info.json"
        if f.exists():
            info = json.loads(f.read_text())
            return [bool(x) for x in info["per_task"][0]["metrics"]["successes"]]
    return None


# ------------------------------------------------------------------- main ----


def run(dirs: list[str], th: Thresholds, vel: str = "sim", write: bool = True, keep: bool = False,
        ref: str = "settle"):
    rows, traces = [], {}
    for d in dirs:
        d_rows = []
        lr_cache: dict[Path, list[bool] | None] = {}
        for p in find_traces(Path(d)):
            t = load_trace(p)
            r = check(t, th, vel, ref)
            if p.parent not in lr_cache:
                lr_cache[p.parent] = lerobot_successes(p)
            lr = lr_cache[p.parent]
            ep = t["episode"]
            meta = dict(task=t["task"], kind=t["kind"], variant=t["variant"], seed=t["seed"], episode=ep,
                        layout=t.get("layout_id"), style=t.get("style_id"),
                        lerobot_success=lr[ep] if lr is not None and ep is not None and ep < len(lr) else None,
                        prompt=t["prompt"], file=str(p))
            d_rows.append({**meta, **r})
            if keep:
                traces[str(p)] = t
        if write and d_rows:
            out = Path(d) / "episodes.csv"
            write_csv(d_rows, out)
            print(f"wrote {out} ({len(d_rows)} episodes)")
        rows += d_rows
    return rows, traces


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+")
    d = Thresholds()
    for f in d.__dataclass_fields__:
        ap.add_argument(f"--{f.replace('_', '-')}", type=float, default=getattr(d, f))
    ap.add_argument("--vel", choices=["sim", "pose"], default="sim",
                    help="speeds from the simulator's velocities (sim) or from differences of recorded poses (pose)")
    ap.add_argument("--ref", choices=["t0", "settle"], default="settle",
                    help="Disturbed(o) measured from the pose at t=0, or once o has settled (see ref_index)")
    ap.add_argument("--idle", action="store_true", help="report as an idle-robot check")
    ap.add_argument("--no-write", action="store_true", help="do not write episodes.csv")
    ap.add_argument("--json-out", help="also write all rows to this JSON file")
    a = ap.parse_args(argv)
    th = Thresholds(**{f: getattr(a, f) for f in d.__dataclass_fields__})
    rows, traces = run(a.dirs, th, a.vel, write=not a.no_write, keep=a.idle, ref=a.ref)
    print(f"\nthresholds: {th}  velocities: {a.vel}  Disturbed reference: {a.ref}\n")
    if a.idle:
        report_idle(rows, traces, th)
    else:
        report(rows)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(rows, indent=1, default=str))
    return rows


if __name__ == "__main__":
    main()
