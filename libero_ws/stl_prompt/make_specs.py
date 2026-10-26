"""Write STL specs + prompt variants for LIBERO tasks to JSON.

Usage: python stl_prompt/make_specs.py stl_prompt/specs.json

Prompt variants per task:
  nl        original LIBERO instruction (baseline)
  stl_nl    STL translated to English with templates (stl_spec.to_english)
  stl       raw STL text with readable object names
  stl_bddl  raw STL text with BDDL object ids, i.e. the spec exactly as the simulator sees it
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stl_spec import HZ, And, Atom, F, objects, unique_atoms  # noqa: E402

T_GOAL = 300  # LeRobot's libero_goal episode cap (15 s at 20 Hz)

LIBERO_GOAL = {
    0: ("open the middle drawer of the cabinet", F(Atom("open", "wooden_cabinet_1_middle_region"), (0, T_GOAL))),
    1: ("put the bowl on the stove", F(Atom("on", "akita_black_bowl_1", "flat_stove_1_cook_region"), (0, T_GOAL))),
    2: ("put the wine bottle on top of the cabinet", F(Atom("on", "wine_bottle_1", "wooden_cabinet_1_top_side"), (0, T_GOAL))),
    3: (
        "open the top drawer and put the bowl inside",
        F(
            And(
                Atom("open", "wooden_cabinet_1_top_region"),
                F(Atom("in", "akita_black_bowl_1", "wooden_cabinet_1_top_region"), (0, T_GOAL)),
            ),
            (0, T_GOAL),
        ),
    ),
    4: ("put the bowl on top of the cabinet", F(Atom("on", "akita_black_bowl_1", "wooden_cabinet_1_top_side"), (0, T_GOAL))),
    5: ("push the plate to the front of the stove", F(Atom("on", "plate_1", "main_table_stove_front_region"), (0, T_GOAL))),
    6: ("put the cream cheese in the bowl", F(Atom("on", "cream_cheese_1", "akita_black_bowl_1"), (0, T_GOAL))),
    7: ("turn on the stove", F(Atom("turnon", "flat_stove_1"), (0, T_GOAL))),
    8: ("put the bowl on the plate", F(Atom("on", "akita_black_bowl_1", "plate_1"), (0, T_GOAL))),
    9: ("put the wine bottle on the rack", F(Atom("on", "wine_bottle_1", "wine_rack_1_top_region"), (0, T_GOAL))),
}


def bddl_stl(phi) -> str:
    """Raw STL with BDDL ids instead of readable names."""
    s = phi.to_stl()
    for a in unique_atoms(phi):
        s = s.replace(a.to_stl(), f"{a.pred}({', '.join(a.args)})")
    return s


def build():
    out = {"hz": HZ, "libero_goal": {}}
    for tid, (nl, phi) in LIBERO_GOAL.items():
        out["libero_goal"][str(tid)] = {
            "rtamt": phi.to_rtamt(),
            "atoms": {a.signal: [a.pred, *a.args] for a in unique_atoms(phi)},
            "objects": objects(phi),
            "prompts": {
                "nl": nl,
                "stl_nl": phi.to_english(),
                "stl": phi.to_stl(),
                "stl_bddl": bddl_stl(phi),
            },
        }
    return out


if __name__ == "__main__":
    specs = build()
    Path(sys.argv[1]).write_text(json.dumps(specs, indent=1))
    for tid, e in specs["libero_goal"].items():
        print(f"[{tid}]")
        for k, v in e["prompts"].items():
            print(f"   {k:9s} {v}")
        print(f"   {'rtamt':9s} {e['rtamt']}")
