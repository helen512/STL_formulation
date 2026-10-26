"""Write STL specs + prompt variants for LIBERO tasks to JSON.

Usage (in the pixi env, which has LIBERO): python stl_prompt/make_specs.py stl_prompt/specs.json

libero_goal (kind "bddl"): one AST formula per task; prompt variants
  nl        original LIBERO instruction (baseline)
  stl_nl    STL translated to English with templates (stl_spec.to_english)
  stl       raw STL text with readable object names
  stl_bddl  raw STL text with BDDL object ids, i.e. the spec exactly as the simulator sees it

libero_spatial (kind "bowl_on_plate"): the same spec for all 10 tasks (stl_spec.BowlOnPlateSpec); prompts
  nl        original LIBERO instruction (baseline)
  stl_nl    nl + one fixed English rule sentence
  stl       raw STL, bowl named by its location

Every task also lists the movable objects of its scene (the BDDL `:objects`),
which is what launch_eval.py records and monitor.py checks for side effects.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stl_spec import HZ, And, Atom, BowlOnPlateSpec, F, objects, unique_atoms  # noqa: E402

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

SPATIAL_BOWL = "akita_black_bowl_1"
SPATIAL_PLATE = "plate_1"
SPATIAL_NL = re.compile(r"^pick up the black bowl (.+) and place it on the plate$")


def bddl_info(suite_name: str) -> dict[int, dict]:
    """Per task: LIBERO's instruction, the BDDL :objects (movable) and the BDDL goal atoms."""
    from libero.libero import benchmark, get_libero_path

    suite = benchmark.get_benchmark_dict()[suite_name]()
    out = {}
    for tid, task in enumerate(suite.tasks):
        path = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)
        text = Path(path).read_text()
        block = re.search(r"\(:objects(.*?)\)", text, re.S).group(1)
        movable = []
        for line in block.strip().splitlines():
            names, _, _type = line.partition(" - ")
            movable += names.split()
        goal = re.search(r"\(:goal(.*)\)\s*\)\s*$", text, re.S).group(1)
        atoms = [[p.lower(), *args.split()] for p, args in re.findall(r"\((\w+)\s+([\w ]+)\)", goal)]
        out[tid] = {"language": task.language, "movable": movable, "goal": atoms, "bddl": path}
    return out


def bddl_stl(phi) -> str:
    """Raw STL with BDDL ids instead of readable names."""
    s = phi.to_stl()
    for a in unique_atoms(phi):
        s = s.replace(a.to_stl(), f"{a.pred}({', '.join(a.args)})")
    return s


def build_goal(info: dict[int, dict]) -> dict:
    out = {}
    for tid, (nl, phi) in LIBERO_GOAL.items():
        assert info[tid]["language"] == nl, (tid, info[tid]["language"], nl)
        out[str(tid)] = {
            "kind": "bddl",
            "rtamt": phi.to_rtamt(),
            "atoms": {a.signal: [a.pred, *a.args] for a in unique_atoms(phi)},
            "objects": objects(phi),
            "movable": info[tid]["movable"],
            "prompts": {
                "nl": nl,
                "stl_nl": phi.to_english(),
                "stl": phi.to_stl(),
                "stl_bddl": bddl_stl(phi),
            },
        }
    return out


def spatial_spec(nl: str, movable: list[str]) -> BowlOnPlateSpec:
    m = SPATIAL_NL.match(nl)
    assert m, f"unexpected libero_spatial instruction: {nl!r}"
    location = [w for w in m.group(1).split() if w != "the"]
    others = tuple(o for o in movable if o not in (SPATIAL_BOWL, SPATIAL_PLATE))
    return BowlOnPlateSpec(
        bowl=SPATIAL_BOWL, plate=SPATIAL_PLATE, others=others, bowl_name="_".join(["black_bowl", *location])
    )


def build_spatial(info: dict[int, dict]) -> dict:
    out = {}
    for tid, t in info.items():
        # The spec assumes LIBERO's goal is exactly On(bowl_1, plate_1).
        assert t["goal"] == [["on", SPATIAL_BOWL, SPATIAL_PLATE]], (tid, t["goal"])
        spec = spatial_spec(t["language"], t["movable"])
        out[str(tid)] = {
            "kind": "bowl_on_plate",
            "bowl": spec.bowl,
            "plate": spec.plate,
            "others": list(spec.others),
            "bowl_name": spec.bowl_name,
            "land_by_s": spec.land_by_s,
            "rest_s": spec.rest_s,
            "still_s": spec.still_s,
            "movable": t["movable"],
            "rtamt": spec.to_rtamt(),  # with default thresholds; monitor.py rebuilds it with its own
            "prompts": {
                "nl": t["language"],
                "stl_nl": t["language"] + spec.stl_nl_suffix(),
                "stl": spec.to_stl(),
            },
        }
    return out


def build():
    return {
        "hz": HZ,
        "libero_goal": build_goal(bddl_info("libero_goal")),
        "libero_spatial": build_spatial(bddl_info("libero_spatial")),
    }


if __name__ == "__main__":
    specs = build()
    Path(sys.argv[1]).write_text(json.dumps(specs, indent=1))
    for suite in ("libero_goal", "libero_spatial"):
        print(f"== {suite}")
        for tid, e in specs[suite].items():
            print(f"[{tid}] movable={e['movable']}")
            for k, v in e["prompts"].items():
                print(f"   {k:9s} {v}")
            print(f"   {'rtamt':9s} {e['rtamt']}")
