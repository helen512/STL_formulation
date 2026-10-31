"""Tests for monitor.py on hand-made RoboCasa recordings (plan step 3).

Run in the rtamt venv:  python stl_prompt/test_monitor.py   (pytest also works if installed)

Each recording is built from a clean baseline that passes every part of phi; each test bends one part
and checks the verdict of rtamt AND of the numpy re-implementation (they must agree on every test).
One baseline per spec type: P (PickPlaceCounterToCabinet), F (CloseFridge), F with the microwave's
distance-based Released (TurnOnMicrowave), N (NavigateKitchen), plus OpenDrawer for the drawer frame.
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import monitor  # noqa: E402
from stl_spec import TASKS, Thresholds  # noqa: E402

TH = Thresholds()


def quat_z(deg: float) -> list[float]:
    a = math.radians(deg) / 2
    return [math.cos(a), 0.0, 0.0, math.sin(a)]


def quat_x(deg: float) -> list[float]:
    a = math.radians(deg) / 2
    return [math.cos(a), math.sin(a), 0.0, 0.0]


def obj_track(n: int, pos=(1.0, 2.0, 0.9)) -> dict:
    return {"pos": [list(pos)] * n, "quat": [[1.0, 0.0, 0.0, 0.0]] * n, "linvel": [[0.0, 0.0, 0.0]] * n,
            "angvel": [[0.0, 0.0, 0.0]] * n}


def make(task: str, done_at: int | None | str = "auto", others=("distr_a", "distr_b"), moving_until: int | None = None):
    """A recording of `task`: success from `done_at` (default: 100 steps before the deadline) to the end; the
    target object / part / base moves fast until `moving_until` (default done_at + 10) and is still afterwards;
    nothing touches anything after done_at."""
    info = TASKS[task]
    if done_at == "auto":
        done_at = info.deadline_step - 100
    n = info.horizon + 1
    t = np.arange(n)
    if moving_until is None:
        moving_until = (done_at or 0) + 10
    success = (t >= done_at) if done_at is not None else np.zeros(n, bool)
    moving = t < moving_until
    tr = {
        "format": "robocasa-1", "task": task, "kind": info.kind, "variant": "test", "seed": 1000, "episode": 0,
        "hz": 20, "horizon": info.horizon, "prompt": "", "others": list(others), "target": None,
        "goal_joints": [], "frames_of": {}, "frames": {}, "joint_names": ["other_door_joint"],
        "joints": [[0.0]] * n, "goal_qvel": {}, "success": success.tolist(), "success_parts": {},
        "objects": {o: obj_track(n) for o in others},
        "contact": {"gripper": {o: [False] * n for o in others}, "pads": {o: [False] * n for o in others},
                    "part_gripper": [False] * n, "part_robot": [False] * n},
        "base": obj_track(n, (0.0, 0.0, 0.0)),
    }
    if info.kind == "P":
        tr["target"] = "obj"
        o = obj_track(n)
        o["linvel"] = [[0.2, 0, 0] if m else [0.001, 0, 0] for m in moving]
        o["angvel"] = [[0, 0, 1.0] if m else [0, 0, 0.01] for m in moving]
        z = np.where((t >= 50) & (t < (done_at or n)), 1.0, 0.9)  # lifted from step 50 until placed
        o["pos"] = [[1.0, 2.0, float(zz)] for zz in z]
        tr["objects"]["obj"] = o
        touch = (t >= 40) & (t < (done_at or n) - 5)
        tr["contact"]["gripper"]["obj"] = touch.tolist()
        tr["contact"]["pads"]["obj"] = touch.tolist()
        tr["success_parts"] = {"in_cabinet": ((t >= (done_at or n) - 5)).tolist(), "gripper_far": (~touch).tolist()}
    elif info.kind == "F":
        tr["goal_joints"] = ["door_joint"]
        tr["goal_qvel"] = {"door_joint": [0.5 if m else 0.001 for m in moving]}
        tr["contact"]["part_gripper"] = ((t >= 100) & (t < (done_at or n))).tolist()
        tr["contact"]["part_robot"] = tr["contact"]["part_gripper"]
        if task == "TurnOnMicrowave":
            tr["goal_joints"], tr["goal_qvel"] = [], {}
            far = ~((t >= 100) & (t < (done_at or n)))
            tr["success_parts"] = {"turned_on": (t >= (done_at or n) - 5).tolist(), "gripper_far": far.tolist()}
    else:
        tr["base"]["linvel"] = [[0.3, 0, 0] if m else [0.001, 0, 0] for m in moving]
        tr["base"]["angvel"] = [[0, 0, 0.5] if m else [0, 0, 0.001] for m in moving]
    return tr


def setv(tr, path, k, value):
    """Set tr[path...][k] = value (path is a tuple of keys)."""
    tr = copy.deepcopy(tr)
    x = tr
    for p in path[:-1]:
        x = x[p]
    lst = list(x[path[-1]])
    if isinstance(k, slice):
        for i in range(*k.indices(len(lst))):
            lst[i] = value
    else:
        lst[k] = value
    x[path[-1]] = lst
    return tr


def move(tr, obj, at, dx=0.0, quat=None):
    """From step `at` on, shift `obj` by dx metres along x and/or set its orientation."""
    tr = copy.deepcopy(tr)
    o = tr["objects"][obj]
    p = np.asarray(o["pos"], dtype=float)
    p[at:, 0] += dx
    o["pos"] = p.tolist()
    if quat is not None:
        o["quat"] = o["quat"][:at] + [quat] * (len(o["quat"]) - at)
    return tr


def verdict(tr, th=TH):
    r = monitor.check(tr, th)
    assert r["rtamt_eq_numpy"], "rtamt and numpy disagree"
    return r


D_P = TASKS["PickPlaceCounterToCabinet"].deadline_step  # 300
D_F = TASKS["CloseFridge"].deadline_step  # 360
D_N = TASKS["NavigateKitchen"].deadline_step  # 180
D_M = TASKS["TurnOnMicrowave"].deadline_step  # 180


# ------------------------------------------------------------------ P -------


def P(**kw):
    return make("PickPlaceCounterToCabinet", **kw)


def test_deadlines_are_60_percent_of_the_limit():
    got = {k: (v.horizon, v.deadline_s, v.deadline_step) for k, v in TASKS.items()}
    assert got["CloseBlenderLid"] == (600, 18, 360)
    assert got["CloseToasterOvenDoor"] == (300, 9, 180)
    assert got["CoffeeSetupMug"] == (400, 12, 240)
    assert got["OpenDrawer"] == (500, 15, 300)
    assert got["OpenCabinet"] == (700, 21, 420)
    assert len(TASKS) == 18 and sum(v.kind == "P" for v in TASKS.values()) == 7


def test_P_baseline_passes_everything():
    r = verdict(P())
    assert r["task_success"] and r["deadline"] and r["undisturbed"] and r["clean"] and r["full_stl"]
    assert r["first_success_s"] == 10.0 and r["rest_start_s"] == 10.5 and r["deadline_cause"] is None
    assert r["steps"] == 500 and not r["pushed_in"] and r["first_grasp_lift_s"] == 2.5


def test_P_rest_starting_at_the_deadline_step_passes_one_later_fails():
    r = verdict(P(done_at=D_P - 5, moving_until=D_P))
    assert r["deadline"] and r["rest_start_s"] == D_P / 20
    r = verdict(P(done_at=D_P - 5, moving_until=D_P + 1))
    assert not r["deadline"] and r["task_success"] and r["deadline_cause"] == "done by T, settled only after T"


def test_P_success_first_after_deadline():
    r = verdict(P(done_at=D_P + 1))
    assert r["task_success"] and not r["deadline"] and r["deadline_cause"] == "first done after T"


def test_P_never_done():
    r = verdict(P(done_at=None))
    assert not r["task_success"] and not r["deadline"] and not r["clean"] and r["deadline_cause"] == "never done"


def test_P_rest_breaking_on_the_last_sample_fails():
    tr = P()
    r = verdict(setv(setv(tr, ("success",), -1, False), ("success_parts", "in_cabinet"), -1, False))
    assert not r["deadline"] and r["task_success"] and r["deadline_cause"] == "done by T, undone at the end"
    r = verdict(setv(tr, ("objects", "obj", "linvel"), -1, [0.0101, 0, 0]))
    assert not r["deadline"] and r["deadline_cause"] == "done by T, still moving at the end"


def test_P_gripper_near_at_the_end_is_classified_as_gripper():
    tr = setv(P(), ("success",), slice(450, None), False)
    tr = setv(tr, ("success_parts", "gripper_far"), slice(450, None), False)
    r = verdict(tr)
    assert not r["deadline"] and r["deadline_cause"] == "done by T, gripper near / touching at the end"


def test_P_still_speed_and_spin_limits():
    tr = P()
    assert verdict(setv(tr, ("objects", "obj", "linvel"), 400, [0.0099, 0, 0]))["deadline"]
    assert not verdict(setv(tr, ("objects", "obj", "linvel"), 400, [0.0101, 0, 0]))["deadline"]
    assert verdict(setv(tr, ("objects", "obj", "angvel"), 400, [0, 0.249, 0]))["deadline"]
    r = verdict(setv(tr, ("objects", "obj", "angvel"), 400, [0, 0.251, 0]))
    assert not r["deadline"] and r["deadline_cause"] == "done by T, settled only after T"


def test_P_undone_and_redone_after_deadline():
    tr = setv(P(), ("success",), slice(350, 360), False)
    tr = setv(tr, ("success_parts", "in_cabinet"), slice(350, 360), False)
    r = verdict(tr)
    assert not r["deadline"] and r["deadline_cause"] == "done by T, undone, redone after T"


def test_P_pushed_in_when_placed_before_any_lift():
    tr = P()
    tr["objects"]["obj"]["pos"] = [[1.0, 2.0, 0.9]] * len(tr["success"])  # never lifted
    r = verdict(tr)
    assert r["pushed_in"] and r["first_grasp_lift_s"] is None and r["deadline"]  # pushing in still counts


# ------------------------------------------------------------- Disturbed ----


def test_disturbed_displacement_limit_2cm():
    assert verdict(move(P(), "distr_a", 100, dx=0.0199))["undisturbed"]
    r = verdict(move(P(), "distr_a", 100, dx=0.0201))
    assert not r["undisturbed"] and not r["clean"] and not r["full_stl"] and r["deadline"] and r["task_success"]
    assert r["disturbed_objects"] == "distr_a" and r["first_disturbed_s"] == 5.0


def test_disturbed_rotation_limit_10deg_about_any_axis():
    assert verdict(move(P(), "distr_b", 100, quat=quat_x(9.9)))["undisturbed"]
    assert not verdict(move(P(), "distr_b", 100, quat=quat_x(10.1)))["undisturbed"]
    # spinning about the vertical counts (unlike LIBERO), but LIBERO's tilt-only check ignores it
    r = verdict(move(P(), "distr_b", 100, quat=quat_z(30)))
    assert not r["undisturbed"] and r["undisturbed_tilt_only"] and r["max_rot_deg_distr_b"] == 30.0


def test_disturbed_on_the_last_sample_and_moved_back_both_count():
    assert not verdict(move(P(), "distr_a", 500, dx=0.05))["undisturbed"]
    tr = move(P(), "distr_a", 100, dx=0.05)
    tr = move(tr, "distr_a", 120, dx=-0.05)  # moved and put back
    assert not verdict(tr)["undisturbed"]


def rolling(tr, obj, until, dx=0.03, deg=40.0):
    """`obj` rolls dx metres / deg degrees during steps 0..until (fast), then is still for good."""
    tr = copy.deepcopy(tr)
    o, n = tr["objects"][obj], len(tr["success"])
    for k in range(n):
        f = min(k / until, 1.0)
        o["pos"][k] = [1.0 + dx * f, 2.0, 0.9]
        o["quat"][k] = quat_x(deg * f)
        o["linvel"][k] = [0.05, 0, 0] if k < until else [0.0, 0, 0]
        o["angvel"][k] = [1.0, 0, 0] if k < until else [0.0, 0, 0]
    return tr


def test_settling_at_t0_is_not_counted_with_the_settled_reference():
    tr = rolling(P(), "distr_a", until=24)
    assert verdict(tr)["undisturbed"]  # default: settled reference
    r = monitor.check(tr, TH, ref="t0")
    assert r["rtamt_eq_numpy"] and not r["undisturbed"]
    assert monitor.ref_index(tr, "distr_a", "settle", TH) == 24
    # a move after settling still counts, measured from the settled pose
    assert not verdict(move(tr, "distr_a", 200, dx=0.0201))["undisturbed"]
    assert verdict(move(tr, "distr_a", 200, dx=0.0199))["undisturbed"]


def test_settled_reference_is_capped_at_2s_and_at_first_gripper_contact():
    tr = rolling(P(), "distr_a", until=100)  # never settles within 2 s: reference at step 40
    assert monitor.ref_index(tr, "distr_a", "settle", TH) == 40
    assert not verdict(tr)["undisturbed"]  # it rolls on after 2 s
    tr = rolling(P(), "distr_a", until=24)
    tr = setv(tr, ("contact", "gripper", "distr_a"), 10, True)  # touched while still rolling
    assert monitor.ref_index(tr, "distr_a", "settle", TH) == 10


def test_no_others_means_undisturbed():
    r = verdict(P(others=()))
    assert r["undisturbed"] and r["clean"] and r["full_stl"] and r["n_others"] == 0


def test_target_and_unlisted_objects_are_not_checked():
    tr = P()
    tr["objects"]["container"] = obj_track(len(tr["success"]))
    tr = move(tr, "container", 100, dx=0.3)  # not in O (e.g. the receptacle)
    tr = move(tr, "obj", 100, dx=0.3)  # the target itself
    assert verdict(tr)["undisturbed"]


def test_fixture_changed_is_a_diagnostic_only():
    tr = P()
    tr["joints"] = [[0.0]] * 200 + [[0.19]] * (len(tr["success"]) - 200)
    assert not verdict(tr)["fixture_changed"]
    tr["joints"] = [[0.0]] * 200 + [[0.21]] * (len(tr["success"]) - 200)
    r = verdict(tr)
    assert r["fixture_changed"] and r["full_stl"] and r["fixture_changed_joints"] == "other_door_joint:0.21"


# ------------------------------------------------------------------ F -------


def F(**kw):
    return make("CloseFridge", **kw)


def test_F_baseline_passes_everything():
    r = verdict(F())
    assert r["deadline"] and r["full_stl"] and not r["bumped"] and r["first_part_contact_s"] == 5.0


def test_F_rest_at_deadline_step_passes_one_later_fails():
    assert verdict(F(done_at=D_F - 5, moving_until=D_F))["deadline"]
    assert not verdict(F(done_at=D_F - 5, moving_until=D_F + 1))["deadline"]


def test_F_touching_the_part_breaks_rest():
    r = verdict(setv(F(), ("contact", "part_gripper"), -1, True))
    assert not r["deadline"] and r["deadline_cause"] == "done by T, gripper near / touching at the end"
    r = verdict(setv(F(), ("contact", "part_gripper"), slice(370, 380), True))
    assert not r["deadline"] and r["deadline_cause"] == "done by T, gripper near / touching until after T"
    # touching only before the deadline, once rest has already started later, is fine
    assert verdict(setv(F(), ("contact", "part_gripper"), slice(300, 350), True))["deadline"]


def test_F_part_still_limit():
    assert verdict(setv(F(), ("goal_qvel", "door_joint"), 500, 0.0099))["deadline"]
    assert verdict(setv(F(), ("goal_qvel", "door_joint"), 500, -0.0099))["deadline"]
    assert not verdict(setv(F(), ("goal_qvel", "door_joint"), 500, -0.0101))["deadline"]


def test_F_max_over_several_goal_joints():
    tr = F()
    tr["goal_joints"].append("door2_joint")
    tr["goal_qvel"]["door2_joint"] = [0.0] * 500 + [0.02] + [0.0] * (len(tr["success"]) - 501)
    assert not verdict(tr)["deadline"]


def test_F_bumped_when_done_before_gripper_contact():
    tr = F()
    tr["contact"]["part_gripper"] = [False] * len(tr["success"])  # done by the arm or the base
    r = verdict(tr)
    assert r["bumped"] and r["deadline"]


def test_F_goal_undone_at_the_end():
    r = verdict(setv(F(), ("success",), slice(590, None), False))
    assert not r["deadline"] and r["deadline_cause"] == "done by T, undone at the end"


def test_F_microwave_uses_gripper_far_not_contact():
    tr = make("TurnOnMicrowave", others=("obj",))
    r = verdict(tr)
    assert r["deadline"] and r["full_stl"]
    tr2 = setv(tr, ("success_parts", "gripper_far"), -1, False)
    tr2 = setv(tr2, ("success",), -1, False)  # RoboCasa's success includes gripper_far
    r = verdict(tr2)
    assert not r["deadline"] and r["deadline_cause"] == "done by T, gripper near / touching at the end"
    # touching the button geom alone doesn't matter once the gripper is far (it can't be, but check the wiring)
    assert verdict(setv(tr, ("contact", "part_gripper"), -1, True))["deadline"]
    assert verdict(make("TurnOnMicrowave", done_at=D_M - 5, moving_until=D_M, others=()))["deadline"]
    assert not verdict(make("TurnOnMicrowave", done_at=D_M + 1, others=()))["deadline"]


# ------------------------------------------------------------------ N -------


def N(**kw):
    return make("NavigateKitchen", others=(), **kw)


def test_N_baseline_and_deadline_boundary():
    assert verdict(N())["full_stl"]
    assert verdict(N(done_at=D_N - 5, moving_until=D_N))["deadline"]
    r = verdict(N(done_at=D_N - 5, moving_until=D_N + 1))
    assert not r["deadline"] and r["deadline_cause"] == "done by T, settled only after T"


def test_N_base_speed_and_turn_limits():
    assert verdict(setv(N(), ("base", "linvel"), 250, [0.0199, 0, 0]))["deadline"]
    assert not verdict(setv(N(), ("base", "linvel"), 250, [0.0201, 0, 0]))["deadline"]
    assert verdict(setv(N(), ("base", "angvel"), 250, [0, 0, 0.049]))["deadline"]
    assert not verdict(setv(N(), ("base", "angvel"), 250, [0, 0, 0.051]))["deadline"]


# ---------------------------------------------------------- drawer frame ----


def drawer_trace(slide=0.3, slip=0.0, yaw=37.0):
    """OpenDrawer: the drawer (rotated by `yaw` about z) slides out `slide` m along its own -y between
    steps 100-200; the utensil inside moves with it, plus `slip` m along the drawer's x."""
    tr = make("OpenDrawer", others=("drawer_obj", "distr_counter_1"))
    n = len(tr["success"])
    frac = np.clip((np.arange(n) - 100) / 100, 0, 1)[:, None]
    q = np.asarray(quat_z(yaw))
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    ex, ey = np.array([c, s, 0.0]), np.array([-s, c, 0.0])  # drawer axes in the world
    fpos = np.array([2.0, 1.0, 0.8]) - frac * slide * ey
    tr["frames"] = {"drawer_box": {"pos": fpos.tolist(), "quat": [q.tolist()] * n}}
    tr["frames_of"] = {"drawer_obj": "drawer_box"}
    opos = fpos + 0.1 * ex + frac * slip * ex
    tr["objects"]["drawer_obj"] = {"pos": opos.tolist(), "quat": [quat_z(yaw + 5)] * n,
                                   "linvel": [[0, 0, 0]] * n, "angvel": [[0, 0, 0]] * n}
    return tr


def test_drawer_object_measured_in_the_drawer_frame():
    r = verdict(drawer_trace())
    assert r["undisturbed"] and r["max_disp_drawer_obj"] < 1e-6 and r["max_rot_deg_drawer_obj"] < 1e-6
    r = verdict(drawer_trace(slip=0.0201))
    assert not r["undisturbed"] and r["disturbed_objects"] == "drawer_obj"
    assert verdict(drawer_trace(slip=0.0199))["undisturbed"]
    # without the frame, opening the drawer would flag the utensil
    tr = drawer_trace()
    tr["frames_of"] = {}
    assert not verdict(tr)["undisturbed"]


# ------------------------------------------------------------ STL syntax ----


def test_rtamt_text_matches_the_doc():
    s = monitor.spec_of(P())
    assert s.deadline_rtamt(TH) == ("eventually[0:300](always((success > 0.5) and (speed_obj < 0.01)"
                                    " and (spin_obj < 0.25)))")
    s = monitor.spec_of(F())
    assert s.deadline_rtamt(TH) == ("eventually[0:360](always((success > 0.5) and (gripper_contact_part < 0.5)"
                                    " and (jvel_part < 0.01)))")
    s = monitor.spec_of(N())
    assert s.to_rtamt(TH) == ("(eventually[0:180](always((success > 0.5) and (base_speed < 0.02)"
                              " and (base_turn < 0.05))))")
    assert monitor.spec_of(P()).undisturbed_rtamt(TH)["distr_a"] == "always((disp_distr_a < 0.02) and (rot_distr_a < 10))"


def test_mcnemar_and_wilson():
    assert monitor.mcnemar_p(10, 34) < 0.001 and abs(monitor.mcnemar_p(12, 10) - 0.83) < 0.01
    lo, hi = monitor.wilson(72, 100)
    assert round(100 * lo) == 63 and round(100 * hi) == 80


def test_quaternion_helpers():
    q0 = np.array([[1.0, 0, 0, 0]])
    assert abs(math.degrees(monitor.rot_angle(np.array([quat_x(25)]), q0)[0]) - 25) < 1e-9
    v = monitor.quat_rotate(np.array([quat_z(90)]), np.array([[1.0, 0, 0]]))
    assert np.allclose(v, [[0, 1, 0]])
    # 1e-5 rounding of a still quaternion must not look like spin
    q = np.array([[0.70711, 0.0, 0.0, 0.70711], [0.70710, 0.0, 0.0, 0.70711]])
    assert monitor.rot_angle(q[1:], q[:1])[0] * 20 < 0.001


# ------------------------------------------------------------------ main ----

if __name__ == "__main__":
    tests = [(k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
