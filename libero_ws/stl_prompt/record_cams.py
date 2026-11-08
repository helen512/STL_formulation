"""launch_eval.py, but each eval video frame shows every camera the policy gets.

Same CLI and environment variables as launch_eval.py. The cameras are side by side, each under a
label, in the orientation and resolution the policy receives them: rotated 180 degrees as
LiberoProcessorStep does, before pi0.5 resizes them to 224x224.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import launch_eval  # noqa: E402, F401  (prompt swap, no early stop, recordings)
import lerobot.envs.libero as L  # noqa: E402

LABEL_H = 24
SHORT = {"agentview_image": "agentview", "robot0_eye_in_hand_image": "eye_in_hand"}


def _labelled(img: np.ndarray, text: str) -> np.ndarray:
    strip = np.zeros((LABEL_H, img.shape[1], 3), np.uint8)
    cv2.putText(strip, text, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return np.concatenate([strip, img], axis=0)


def render(self):
    self._ensure_env()
    pixels = self._format_raw_obs(self._env.env._get_observations())["pixels"]
    raw_name = {v: k for k, v in self.camera_name_mapping.items()}
    tiles = [
        _labelled(np.ascontiguousarray(img[::-1, ::-1]), f"{key} = {SHORT.get(raw_name[key], raw_name[key])}")
        for key, img in pixels.items()
    ]
    return np.concatenate(tiles, axis=1)


L.LiberoEnv.render = render

if __name__ == "__main__":
    from lerobot.scripts.lerobot_eval import main

    sys.exit(main())
