"""lerobot-eval on LIBERO with a swapped prompt and per-step STL recordings.

Same CLI as `lerobot-eval`. Extra settings come from environment variables:
  STL_SPECS          JSON written by make_specs.py
  STL_VARIANT        which prompt to feed the policy (a key of the task's "prompts", e.g. nl | stl_nl | stl)
  STL_TRACE_DIR      where to write one JSON recording per episode (optional)
  STL_NO_EARLY_STOP  1 = never terminate on success, so every episode runs the suite's full length
                     (info["is_success"] is still reported each step, so LeRobot's success = goal at any step)

Each recording holds, at every env step (sample 0 = after LIBERO's settle steps, sample k = after k actions):
  signals   0/1 values evaluated in the simulator
              kind "bddl"          one per BDDL atom of the task's spec
              kind "bowl_on_plate" on(bowl, plate) [LIBERO check_ontop], grasp(bowl) [robosuite _check_grasp],
                                   gripper_contact(bowl) [any gripper geom touches the bowl]
  objects   pos, quat (wxyz), linvel, angvel (world frame) of every movable BDDL object
  success   LIBERO's success flag
so specs can be monitored offline (monitor.py) without re-running the policy.

Works with eval.batch_size=1 (SyncVectorEnv, same process). With async envs the
patch would have to run inside each worker.
"""

import json
import os
import sys
from pathlib import Path

import lerobot.envs.libero as L

SPECS = json.loads(Path(os.environ["STL_SPECS"]).read_text())
VARIANT = os.environ.get("STL_VARIANT", "nl")
TRACE_DIR = Path(os.environ["STL_TRACE_DIR"]) if os.environ.get("STL_TRACE_DIR") else None
NO_EARLY_STOP = os.environ.get("STL_NO_EARLY_STOP", "0") == "1"

_init, _reset, _step, _close = (
    L.LiberoEnv.__init__,
    L.LiberoEnv.reset,
    L.LiberoEnv.step,
    L.LiberoEnv.close,
)


def _r(xs, nd=5):
    return [round(float(v), nd) for v in xs]


def __init__(self, *args, **kwargs):
    _init(self, *args, **kwargs)
    self._stl_suite = kwargs["task_suite_name"]
    self._stl = SPECS.get(self._stl_suite, {}).get(str(self.task_id))
    self._stl_trace = None
    self._stl_episode = 0
    if self._stl is not None:
        self._stl_orig_prompt = self.task_description
        self.task_description = self._stl["prompts"][VARIANT]
        print(f"[stl] {self._stl_suite}/{self.task_id} variant={VARIANT} prompt={self.task_description!r}", flush=True)


def _signals(self) -> dict[str, bool]:
    inner = self._env.env
    spec = self._stl
    if spec["kind"] == "bddl":
        return {sig: bool(inner._eval_predicate(pred)) for sig, pred in spec["atoms"].items()}
    if spec["kind"] == "bowl_on_plate":
        b, p = spec["bowl"], spec["plate"]
        gripper = inner.robots[0].gripper
        bowl = inner.get_object(b)
        return {
            f"on_{b}_{p}": bool(inner._eval_predicate(["on", b, p])),
            f"grasp_{b}": bool(inner._check_grasp(gripper=gripper, object_geoms=bowl)),
            f"gripper_contact_{b}": bool(inner.check_contact(gripper, bowl)),
        }
    raise ValueError(f"unknown spec kind {spec['kind']!r}")


def _sample(self, success: bool):
    inner = self._env.env
    t = self._stl_trace
    for sig, v in _signals(self).items():
        t["signals"].setdefault(sig, []).append(float(v))
    data = inner.sim.data
    for name in self._stl["movable"]:
        body = inner.sim.model.body_id2name(inner.obj_body_id[name])
        o = t["objects"].setdefault(name, {"pos": [], "quat": [], "linvel": [], "angvel": []})
        o["pos"].append(_r(data.get_body_xpos(body)))
        o["quat"].append(_r(data.get_body_xquat(body)))
        o["linvel"].append(_r(data.get_body_xvelp(body)))
        o["angvel"].append(_r(data.get_body_xvelr(body)))
    t["success"].append(bool(success))


def _flush(self):
    t = self._stl_trace
    self._stl_trace = None
    # A trace with only the reset sample is a reset that was never stepped; skip it.
    if t is None or TRACE_DIR is None or len(t["success"]) < 2:
        return
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{self._stl_suite}_{self.task_id}_ep{self._stl_episode}.json"
    t["episode"] = self._stl_episode
    (TRACE_DIR / name).write_text(json.dumps(t))
    self._stl_episode += 1


def reset(self, *args, **kwargs):
    init_state_id = self.init_state_id
    out = _reset(self, *args, **kwargs)
    if self._stl is not None:
        _flush(self)
        n_init = len(self._init_states) if self._init_states is not None else None
        self._stl_trace = {
            "format": 2,
            "suite": self._stl_suite,
            "task_id": self.task_id,
            "variant": VARIANT,
            "prompt": self.task_description,
            "orig_prompt": self._stl_orig_prompt,
            "init_state": init_state_id % n_init if n_init else None,
            "seed": kwargs.get("seed"),
            "hz": SPECS["hz"],
            "no_early_stop": NO_EARLY_STOP,
            "spec": self._stl,
            "signals": {},
            "objects": {},
            "success": [],
        }
        _sample(self, False)
    return out


def step(self, action):
    obs, reward, terminated, truncated, info = _step(self, action)
    if self._stl_trace is not None:
        _sample(self, info["is_success"])
    if NO_EARLY_STOP:
        # LIBERO's step() sets done = success (bddl_base_domain.py), so neither may end the episode.
        # LeRobot still stops at the suite's max steps; robosuite's 1000-step horizon is never reached.
        terminated = False
    return obs, reward, terminated, truncated, info


def close(self):
    if getattr(self, "_stl", None) is not None:
        _flush(self)
    return _close(self)


L.LiberoEnv.__init__ = __init__
L.LiberoEnv.reset = reset
L.LiberoEnv.step = step
L.LiberoEnv.close = close

if __name__ == "__main__":
    from lerobot.scripts.lerobot_eval import main

    sys.exit(main())
