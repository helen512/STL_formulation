"""Write specs.json: the static part of every task's spec (type, limit, deadline, rtamt with default thresholds,
prompt templates). The per-episode parts (object names, the others O) are only known after RoboCasa builds
the scene, so launch_eval.py / idle_check.py record them in each episode's recording.

Usage (either env):  python stl_prompt/make_specs.py stl_prompt/specs.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stl_spec import HZ, TASKS, TaskSpec, Thresholds, make_prompts  # noqa: E402

# Instruction shapes used only to show the templates (O written as {O}).
EXAMPLE = {
    "CloseBlenderLid": ("Close the lid blender by securely placing the lid on top.", None, None),
    "CloseFridge": ("Close the fridge door.", None, None),
    "CloseToasterOvenDoor": ("Close the toaster oven door.", None, None),
    "CoffeeSetupMug": ("Pick the {obj} from the counter and place it under the coffee machine dispenser.", "{obj}", None),
    "NavigateKitchen": ("Navigate to the {fixture}.", None, None),
    "OpenCabinet": ("Open the cabinet doors.", None, None),
    "OpenDrawer": ("Open the {side} drawer.", None, None),
    "OpenStandMixerHead": ("Open the stand mixer head.", None, None),
    "PickPlaceCounterToCabinet": ("Pick the {obj} from the counter and place it in the cabinet.", "{obj}", None),
    "PickPlaceCounterToStove": ("Pick the {obj} from the plate and place it in the {container}.", "{obj}", "{container}"),
    "PickPlaceDrawerToCounter": ("Pick the {obj} from the drawer and place it on the counter.", "{obj}", None),
    "PickPlaceSinkToCounter": ("Pick the {obj} from the sink and place it on the {container} located on the counter.",
                               "{obj}", "{container}"),
    "PickPlaceToasterToCounter": ("Place the toasted item on a plate.", None, None),
    "SlideDishwasherRack": ("Fully slide the top dishwasher rack {in_out}.", None, None),
    "TurnOffStove": ("Turn off the {location} burner of the stove.", None, None),
    "TurnOnElectricKettle": ("Press down the lever to turn on the electric kettle.", None, None),
    "TurnOnMicrowave": ("Press the start button on the microwave.", None, None),
    "TurnOnSinkFaucet": ("Turn on the sink faucet.", None, None),
}


def build() -> dict:
    out = {"hz": HZ, "deadline_fraction": 0.6, "thresholds": Thresholds().__dict__, "tasks": {}}
    for task, info in TASKS.items():
        lang, obj, cont = EXAMPLE[task]
        if task == "SlideDishwasherRack":
            lang = lang.replace("{in_out}", "in")
        prompts = make_prompts(task, lang, obj, cont)
        out["tasks"][task] = {
            "index": info.index,
            "kind": info.kind,
            "horizon": info.horizon,
            "deadline_s": info.deadline_s,
            "deadline_step": info.deadline_step,
            "rtamt_with_O": TaskSpec(task, others=("O",), microwave=task == "TurnOnMicrowave").to_rtamt(),
            "prompt_templates": prompts,
        }
    return out


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("specs.json"))
    path.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {path}")
