"""record_cams.py, plus a fixed third-person camera that shows the whole workspace.

Same CLI and environment variables as launch_eval.py. Each video frame keeps the policy cameras
from record_cams.py as the top row and adds a `thirdperson` view underneath. The camera is added
to every kitchen but is not in RoboCasaGymEnv's camera list, so the policy never receives it.

Kitchen layouts differ per episode, so the camera is placed at reset and then stays fixed:
- Navigation tasks: high above the room, looking across the route from the robot's start to the
  target fixture, from the side nearer the room center.
- Other tasks: over the robot's shoulder, looking at the robot and the counter in front of it.
The distance is the smallest that keeps every point of interest in the image.
"""

import sys
from pathlib import Path

import numpy as np
import robocasa.utils.camera_utils as CamUtils
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))

import record_cams  # noqa: E402  (launch_eval patches, policy-camera tiles)
import lerobot.envs.robocasa as R  # noqa: E402

CAM = "thirdperson"
# 640x360 fits the default 640x480 offscreen buffer, so the policy cameras' render context is not rebuilt.
WIDTH, HEIGHT, FOVY = 640, 360, 60
NAV_ELEVATION, MANIP_ELEVATION = 65, 45
MANIP_SIDE_ANGLE = 35  # degrees the over-the-shoulder view is turned off the robot's heading


def fit_camera(points: np.ndarray, heading: np.ndarray, elevation_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Pose (pos, wxyz quat) looking along the horizontal heading, tilted down, with every point in view."""
    center = (points.min(0) + points.max(0)) / 2
    el = np.deg2rad(elevation_deg)
    view = np.array([heading[0] * np.cos(el), heading[1] * np.cos(el), -np.sin(el)])
    right = np.cross(view, [0, 0, 1])
    right /= np.linalg.norm(right)
    up = np.cross(right, view)
    tan_v = np.tan(np.deg2rad(FOVY) / 2)
    tan_h = tan_v * WIDTH / HEIGHT
    rel = points - center
    dist = max(
        (np.abs(rel @ right) / tan_h - rel @ view).max(),
        (np.abs(rel @ up) / tan_v - rel @ view).max(),
    )
    x, y, z, w = Rotation.from_matrix(np.stack([right, up, -view], axis=1)).as_quat()
    return center - dist * view, np.array([w, x, y, z])


def boxes(xys: list[np.ndarray], margin: float, z_lo: float, z_hi: float) -> np.ndarray:
    """Corners of a margin-wide box around each xy point, from z_lo to z_hi."""
    return np.array(
        [[x + dx, y + dy, z] for x, y in xys for dx in (-margin, margin) for dy in (-margin, margin) for z in (z_lo, z_hi)]
    )


def room_center(kitchen) -> np.ndarray:
    floors = [f for n, f in kitchen.fixtures.items() if type(f).__name__ == "Floor" and "backing" not in n]
    lo = np.min([np.asarray(f.pos[:2]) - f.size[:2] for f in floors], axis=0)
    hi = np.max([np.asarray(f.pos[:2]) + f.size[:2] for f in floors], axis=0)
    return (lo + hi) / 2


def rotate(v: np.ndarray, deg: float) -> np.ndarray:
    a = np.deg2rad(deg)
    return np.array([np.cos(a) * v[0] - np.sin(a) * v[1], np.sin(a) * v[0] + np.cos(a) * v[1]])


def thirdperson_pose(kitchen) -> tuple[np.ndarray, np.ndarray]:
    sim = kitchen.sim
    bid = sim.model.body_name2id("mobilebase0_base")
    base = sim.data.body_xpos[bid][:2].copy()
    fwd = sim.data.body_xmat[bid].reshape(3, 3)[:2, 0]
    fwd /= np.linalg.norm(fwd)
    room = room_center(kitchen)

    if hasattr(kitchen, "target_pos"):
        xys = [base, np.asarray(kitchen.target_pos[:2]), np.asarray(kitchen.target_fixture.pos[:2])]
        route = (xys[1] - base) / np.linalg.norm(xys[1] - base)
        heading = rotate(route, 90)
        if np.dot(np.mean(xys, axis=0) - room, heading) < 0:
            heading = -heading
        return fit_camera(boxes(xys, 0.5, 0.0, 1.5), heading, NAV_ELEVATION)

    work = base + 0.8 * fwd
    center = (base + work) / 2
    heading = min(
        (rotate(fwd, MANIP_SIDE_ANGLE), rotate(fwd, -MANIP_SIDE_ANGLE)),
        key=lambda h: np.linalg.norm(center - h - room),
    )
    return fit_camera(boxes([base, work], 0.6, 0.0, 1.4), heading, MANIP_ELEVATION)


_get_robot_cam_configs = CamUtils.get_robot_cam_configs
_reset = R.RoboCasaEnv.reset
_render = R.RoboCasaEnv.render


def get_robot_cam_configs(robot, use_cotraining_cameras=False):
    configs = _get_robot_cam_configs(robot, use_cotraining_cameras=use_cotraining_cameras)
    configs[CAM] = dict(pos=[0, 0, 3], quat=[1, 0, 0, 0], camera_attribs=dict(fovy=str(FOVY)))
    return configs


def reset(self, seed=None, **kwargs):
    out = _reset(self, seed=seed, **kwargs)
    kitchen = self._env.env
    sim = kitchen.sim
    cid = sim.model.camera_name2id(CAM)
    pos, quat = thirdperson_pose(kitchen)
    sim.model.cam_pos[cid] = pos
    sim.model.cam_quat[cid] = quat
    # Write the world pose too, so the first frame is right without an extra mj_forward on the physics.
    sim.data.cam_xpos[cid] = pos
    sim.data.cam_xmat[cid] = Rotation.from_quat(np.roll(quat, -1)).as_matrix().ravel()
    return out


def render(self):
    top = _render(self)
    view = self._env.env.sim.render(width=WIDTH, height=HEIGHT, camera_name=CAM)[::-1]
    bottom = record_cams._labelled(np.ascontiguousarray(view), CAM)
    pad = top.shape[1] - bottom.shape[1]
    bottom = np.pad(bottom, ((0, 0), (pad // 2, pad - pad // 2), (0, 0)))
    return np.concatenate([top, bottom], axis=0)


CamUtils.get_robot_cam_configs = get_robot_cam_configs
R.RoboCasaEnv.reset = reset
R.RoboCasaEnv.render = render

if __name__ == "__main__":
    from lerobot.scripts.lerobot_eval import main

    sys.exit(main())
