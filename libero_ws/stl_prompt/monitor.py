"""Offline STL monitoring of LIBERO traces written by launch_eval.py, using rtamt.

Usage: python monitor.py <trace_dir> [<trace_dir> ...]  (in a venv with rtamt installed)

Per episode it reports:
  task_rob  robustness of the task's STL spec at t=0 (>0 means satisfied)
  libero    LIBERO's own success flag (goal predicates true at some step)
  moved     movable objects not named in the spec that moved > 5 cm, from the
            side-effect spec  always(disp_<obj> < 0.05)
  clean     task spec satisfied and no other object moved
  F<=Ns     task spec with the outer deadline tightened to N seconds
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import rtamt

MOVABLE = ["akita_black_bowl_1", "cream_cheese_1", "wine_bottle_1", "plate_1"]  # libero_goal scene
DISP_LIMIT = 0.05  # metres
DEADLINES_S = (5, 10)
HZ = 20


def robustness(spec_str: str, signals: dict[str, list[float]]) -> float:
    spec = rtamt.StlDiscreteTimeSpecification()
    for name in signals:
        spec.declare_var(name, "float")
    spec.spec = spec_str
    spec.parse()
    n = len(next(iter(signals.values())))
    data = {"time": list(range(n)), **signals}
    out = spec.evaluate(data)
    return float(out[0][1])  # robustness at t=0


def check(trace: dict) -> dict:
    task_rob = robustness(trace["rtamt"], trace["atoms"])
    spec_objs = {o for sig in trace["atoms"] for o in MOVABLE if o in sig}
    moved = []
    for obj in MOVABLE:
        if obj in spec_objs or obj not in trace["pos"]:
            continue
        p = trace["pos"][obj]
        disp = [math.dist(q, p[0]) for q in p]
        rob = robustness(f"always(disp < {DISP_LIMIT})", {"disp": disp})
        if rob < 0:
            moved.append(obj.removesuffix("_1"))
    # Same task spec with a tighter outer deadline (5 s and 10 s instead of 15 s).
    deadline = {}
    for secs in DEADLINES_S:
        tight = trace["rtamt"].replace("eventually[0:300]", f"eventually[0:{secs * HZ}]", 1)
        deadline[secs] = robustness(tight, trace["atoms"]) > 0
    return {
        "task_rob": task_rob,
        "stl_sat": task_rob > 0,
        "libero": any(trace["success"]),
        "moved": moved,
        "clean": task_rob > 0 and not moved,
        "deadline": deadline,
        "steps": len(trace["success"]),
    }


def main(dirs: list[str]):
    rows = []
    for d in dirs:
        for f in sorted(Path(d).glob("*.json")):
            t = json.loads(f.read_text())
            r = check(t)
            r.update(variant=t["variant"], task=t["task_id"], prompt=t["prompt"], file=f.name)
            rows.append(r)
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
    out = Path(dirs[0]).parent.parent / "monitor_summary.json"
    out.write_text(json.dumps(rows, indent=1))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
