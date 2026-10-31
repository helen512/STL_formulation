"""lerobot-eval on RoboCasa with a swapped prompt, no early stop and per-step STL recordings.

Same CLI as `lerobot-eval`. Extra settings come from environment variables:
  STL_VARIANT        which prompt to feed the policy: nl | stl_nl | stl (see stl_spec.make_prompts)
  STL_TRACE_DIR      where to write one recording per episode (<task>_ep<k>.json.gz; optional)
  STL_NO_EARLY_STOP  1 = never terminate on success, so every episode runs the task's full RoboCasa limit
                     (info["is_success"] is still reported each step, so LeRobot's success = goal at any step)
  STL_SEED0          seed of episode 0 (default 1000); the recording's episode = seed - STL_SEED0

LeRobot's RoboCasaEnv.step sets terminated = is_success and then calls self.reset() itself, which would
rebuild an unseeded kitchen mid-episode. So step() is replaced, not wrapped. reset() calls the original,
then builds the prompt from the episode's metadata and sets task_description, which lerobot-eval reads
on every step. Works with eval.batch_size=1 and eval.use_async_envs=false (same process).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lerobot.envs.robocasa as R  # noqa: E402

from recorder import Recorder, episode_names  # noqa: E402

VARIANT = os.environ.get("STL_VARIANT", "nl")
TRACE_DIR = Path(os.environ["STL_TRACE_DIR"]) if os.environ.get("STL_TRACE_DIR") else None
NO_EARLY_STOP = os.environ.get("STL_NO_EARLY_STOP", "0") == "1"
SEED0 = int(os.environ.get("STL_SEED0", "1000"))

_reset, _step, _close = R.RoboCasaEnv.reset, R.RoboCasaEnv.step, R.RoboCasaEnv.close


def _flush(self):
    rec = getattr(self, "_stl_rec", None)
    if rec is None or rec.trace is None:
        return
    ep = rec.trace["episode"]
    path = rec.write(TRACE_DIR, f"{self.task}_ep{ep}.json.gz") if TRACE_DIR else None
    rec.trace = None
    if path:
        print(f"[stl] wrote {path}", flush=True)


def reset(self, seed=None, **kwargs):
    out = _reset(self, seed=seed, **kwargs)
    _flush(self)
    env = self._env.env
    ep = episode_names(env, self.task)
    self.task_description = ep["prompts"][VARIANT]
    print(f"[stl] {self.task} seed={seed} variant={VARIANT} prompt={self.task_description!r}", flush=True)
    if not hasattr(self, "_stl_rec"):
        self._stl_rec = Recorder(self.task, VARIANT, {"seed0": SEED0, "no_early_stop": NO_EARLY_STOP})
    self._stl_rec.start(env, seed, self.task_description, ep["names"])
    self._stl_rec.trace["prompts"] = ep["prompts"]
    return out


def step(self, action):
    self._ensure_env()
    if action.ndim != 1:
        raise ValueError(f"Expected a 1-D action, got shape {action.shape}")
    raw_obs, reward, done, truncated, info = self._env.step(R.convert_action(action))
    is_success = bool(info.get("success", False))
    info.update({"task": self.task, "done": done, "is_success": is_success})
    observation = self._format_raw_obs(raw_obs)
    rec = getattr(self, "_stl_rec", None)
    if rec is not None and rec.trace is not None:
        rec.sample(is_success)
    if NO_EARLY_STOP:
        # RoboCasa's done is always False (ignore_done=True); success must not end the episode either.
        # LeRobot still stops at the task's horizon (lerobot_eval.py rollout max_steps).
        terminated = False
    else:
        terminated = done or is_success
        if terminated:
            info["final_info"] = {"task": self.task, "done": bool(done), "is_success": is_success}
            self.reset()
    return observation, reward, terminated, truncated, info


def close(self):
    _flush(self)
    return _close(self)


R.RoboCasaEnv.reset = reset
R.RoboCasaEnv.step = step
R.RoboCasaEnv.close = close

if __name__ == "__main__":
    from lerobot.scripts.lerobot_eval import main

    sys.exit(main())
