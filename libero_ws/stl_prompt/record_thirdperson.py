"""record_cams.py, plus a fixed third-person camera that shows the whole workspace.

Same CLI and environment variables as launch_eval.py. Each video frame keeps the policy cameras
from record_cams.py as the top row and adds a `thirdperson` view underneath. The camera is added
to every scene but is not in the env's camera list, so the policy never receives it.
"""

import sys
from pathlib import Path

import numpy as np
from libero.libero.envs.bddl_base_domain import BDDLBaseDomain
from robosuite.utils.mjcf_utils import array_to_string, new_element
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))

import record_cams  # noqa: E402  (launch_eval patches, policy-camera tiles)
import lerobot.envs.libero as L  # noqa: E402

CAM = "thirdperson"
# 640x360 fits the default 640x480 offscreen buffer, so the policy cameras' render context is not rebuilt.
WIDTH, HEIGHT, FOVY = 640, 360, 50
# Front-left of the table, high enough to see the raised arm, the objects, and the table edges.
POS, TARGET = np.array([0.7, 0.8, 2.05]), np.array([-0.4, 0.0, 1.05])


def look_at(pos: np.ndarray, target: np.ndarray) -> np.ndarray:
    """MuJoCo (w, x, y, z) quaternion of a camera at pos looking at target with world z up."""
    forward = (target - pos) / np.linalg.norm(target - pos)
    right = np.cross(forward, [0, 0, 1])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    x, y, z, w = Rotation.from_matrix(np.stack([right, up, -forward], axis=1)).as_quat()
    return np.array([w, x, y, z])


def stack_rows(top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
    pad = top.shape[1] - bottom.shape[1]
    bottom = np.pad(bottom, ((0, 0), (pad // 2, pad - pad // 2), (0, 0)))
    return np.concatenate([top, bottom], axis=0)


_load_model = BDDLBaseDomain._load_model
_render = L.LiberoEnv.render


def load_model(self):
    _load_model(self)
    self.model.worldbody.append(
        new_element(
            tag="camera",
            name=CAM,
            mode="fixed",
            pos=array_to_string(POS),
            quat=array_to_string(look_at(POS, TARGET)),
            fovy=str(FOVY),
        )
    )


def render(self):
    top = _render(self)
    view = self._env.env.sim.render(width=WIDTH, height=HEIGHT, camera_name=CAM)[::-1]
    return stack_rows(top, record_cams._labelled(np.ascontiguousarray(view), CAM))


BDDLBaseDomain._load_model = load_model
L.LiberoEnv.render = render

if __name__ == "__main__":
    from lerobot.scripts.lerobot_eval import main

    sys.exit(main())
