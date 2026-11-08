"""launch_eval.py, but each eval video frame shows every camera the policy gets.

Same CLI and environment variables as launch_eval.py. The cameras are side by side, each under a
label, exactly as the policy receives them: flipped upright by RoboCasaGymEnv, before pi0.5
resizes them to 224x224.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import launch_eval  # noqa: E402, F401  (prompt swap, I/O layout, no early stop, recordings)
import lerobot.envs.robocasa as R  # noqa: E402

LABEL_H = 24

_format_raw_obs = R.RoboCasaEnv._format_raw_obs


def _labelled(img: np.ndarray, text: str) -> np.ndarray:
    strip = np.zeros((LABEL_H, img.shape[1], 3), np.uint8)
    cv2.putText(strip, text, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return np.concatenate([strip, img], axis=0)


def format_raw_obs(self, raw_obs):
    obs = _format_raw_obs(self, raw_obs)
    self._cam_frames = obs["pixels"]
    return obs


def render(self):
    tiles = [_labelled(np.ascontiguousarray(img), cam.removeprefix("robot0_")) for cam, img in self._cam_frames.items()]
    return np.concatenate(tiles, axis=1)


R.RoboCasaEnv._format_raw_obs = format_raw_obs
R.RoboCasaEnv.render = render

if __name__ == "__main__":
    from lerobot.scripts.lerobot_eval import main

    sys.exit(main())
