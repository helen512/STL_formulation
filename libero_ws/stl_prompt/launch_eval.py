"""lerobot-eval on LIBERO with a swapped prompt and per-step STL atom traces.

Same CLI as `lerobot-eval`. Extra settings come from environment variables:
  STL_SPECS      JSON written by make_specs.py
  STL_VARIANT    which prompt to feed the policy: nl | stl_nl | stl | stl_bddl
  STL_TRACE_DIR  where to write one JSON trace per episode (optional)

Each trace holds the 0/1 value of every atom in the task's STL spec at every
env step, plus the xyz of every object in the scene, so specs can be monitored
offline (monitor.py) without re-running the policy.

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

_init, _reset, _step, _close = (
    L.LiberoEnv.__init__,
    L.LiberoEnv.reset,
    L.LiberoEnv.step,
    L.LiberoEnv.close,
)


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


def _sample(self, success: bool):
    inner = self._env.env
    t = self._stl_trace
    for sig, pred in self._stl["atoms"].items():
        t["atoms"][sig].append(float(bool(inner._eval_predicate(pred))))
    for name, st in inner.object_states_dict.items():
        t["pos"].setdefault(name, []).append([round(float(v), 4) for v in st.get_geom_state()["pos"]])
    t["success"].append(bool(success))


def _flush(self):
    t = self._stl_trace
    self._stl_trace = None
    if t is None or TRACE_DIR is None or not t["success"]:
        return
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{self._stl_suite}_{self.task_id}_ep{self._stl_episode}.json"
    (TRACE_DIR / name).write_text(json.dumps(t))
    self._stl_episode += 1


def reset(self, *args, **kwargs):
    out = _reset(self, *args, **kwargs)
    if self._stl is not None:
        _flush(self)
        self._stl_trace = {
            "suite": self._stl_suite,
            "task_id": self.task_id,
            "variant": VARIANT,
            "prompt": self.task_description,
            "orig_prompt": self._stl_orig_prompt,
            "rtamt": self._stl["rtamt"],
            "atoms": {sig: [] for sig in self._stl["atoms"]},
            "pos": {},
            "success": [],
        }
        _sample(self, False)
    return out


def step(self, action):
    out = _step(self, action)
    if self._stl_trace is not None:
        _sample(self, out[4]["is_success"])
    return out


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
