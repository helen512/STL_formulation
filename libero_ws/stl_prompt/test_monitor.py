"""Tests for monitor.py on hand-made recordings, plus checks against the saved runs.

Run in the rtamt venv:  python stl_prompt/test_monitor.py   (pytest also works if installed)

Each hand-made recording is a 281-sample libero_spatial episode built from a
"clean" baseline that passes every part of phi; each test breaks or bends one
part and checks the verdict of rtamt AND of the numpy re-implementation.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import monitor  # noqa: E402
from stl_spec import BowlOnPlateSpec, Thresholds  # noqa: E402

N = 281  # 280 steps + the reset sample
BOWL, PLATE = "akita_black_bowl_1", "plate_1"
OTHERS = ("akita_black_bowl_2", "cookies_1", "glazed_rim_porcelain_ramekin_1")
SPEC = {
    "kind": "bowl_on_plate", "bowl": BOWL, "plate": PLATE, "others": list(OTHERS),
    "bowl_name": "black_bowl_test", "land_by_s": 9.0, "rest_s": 2.0, "still_s": 11.0,
    "movable": [BOWL, *OTHERS, PLATE],
}
S = monitor.bowl_spec(SPEC)
TH = Thresholds()


def make(grasp=(40, 100), on_from=100, contact=(35, 110), still_from=110, jitter=0.002):
    """A recording: grasped on steps [grasp), on the plate from `on_from`, gripper touching on [contact),
    bowl moving fast until `still_from` and then still (speed/spin = jitter)."""
    rng = np.random.default_rng(0)
    t = np.arange(N)
    on = (t >= on_from) if on_from is not None else np.zeros(N, bool)
    g = (t >= grasp[0]) & (t < grasp[1]) if grasp else np.zeros(N, bool)
    c = (t >= contact[0]) & (t < contact[1]) if contact else np.zeros(N, bool)
    lin = np.zeros((N, 3))
    ang = np.zeros((N, 3))
    lin[:, 0] = np.where(t < still_from, 0.2, jitter * rng.random(N))
    ang[:, 2] = np.where(t < still_from, 1.0, jitter * rng.random(N))
    objs = {}
    for name in SPEC["movable"]:
        objs[name] = {"pos": [[0.1, 0.2, 0.9]] * N, "quat": [[1, 0, 0, 0]] * N,
                      "linvel": [[0, 0, 0]] * N, "angvel": [[0, 0, 0]] * N}
    objs[BOWL] = {"pos": [[0.1, 0.2, 0.9]] * N, "quat": [[1, 0, 0, 0]] * N,
                  "linvel": lin.tolist(), "angvel": ang.tolist()}
    return {
        "format": 2, "suite": "libero_spatial", "task_id": 0, "variant": "test", "prompt": "", "episode": 0,
        "hz": 20, "spec": SPEC,
        "signals": {S.sig_on: on.astype(float).tolist(), S.sig_grasp: g.astype(float).tolist(),
                    S.sig_contact: c.astype(float).tolist()},
        "objects": objs,
        "success": on.tolist(),
    }


def move(trace, obj, at, dist=0.06):
    """Displace `obj` by `dist` metres along x from step `at` on."""
    tr = copy.deepcopy(trace)
    p = np.asarray(tr["objects"][obj]["pos"])
    p[at:, 0] += dist
    tr["objects"][obj]["pos"] = p.tolist()
    return tr


def verdict(trace, th=TH):
    r = monitor.check_spatial(trace, th)
    assert r["rtamt_eq_numpy"], "rtamt and numpy disagree"
    return r


# ---------------------------------------------------------------- baseline ---


def test_baseline_passes_everything():
    r = verdict(make())
    assert r["task_success"] and r["grasp_first"] and r["deadline"] and r["no_move"]
    assert r["clean"] and r["full_stl"]
    assert r["first_grasp_s"] == 2.0 and r["landing_s"] == 5.0 and r["rest_start_s"] == 5.5
    assert r["longest_rest_s"] == round((N - 110) / 20, 2)


# ------------------------------------------------- (!On U Grasp) ---------------


def test_grasp_first_fails_when_pushed_onto_plate():
    r = verdict(make(grasp=None, contact=(35, 110)))  # never grasped, still lands
    assert r["task_success"] and not r["grasp_first"] and not r["full_stl"]
    assert r["clean"]  # clean success does not include the grasp rule


def test_grasp_first_fails_when_on_one_step_before_grasp():
    r = verdict(make(grasp=(100, 120), on_from=99, contact=(95, 120), still_from=120))
    assert not r["grasp_first"]


def test_grasp_first_passes_when_grasp_and_on_same_step():
    r = verdict(make(grasp=(100, 120), on_from=100, contact=(95, 120), still_from=120))
    assert r["grasp_first"]


def test_grasp_first_passes_with_a_regrasp_after_landing():
    # grasp, land, touch it again later: only the first grasp matters
    tr = make()
    g = np.asarray(tr["signals"][S.sig_grasp])
    g[200:210] = 1
    tr["signals"][S.sig_grasp] = g.tolist()
    assert verdict(tr)["grasp_first"]


# ------------------------------------------------- F[0,9] G[0,2] Rest ----------


def test_deadline_passes_at_last_allowed_step():
    # rest from step 180 to 220 inclusive -> passes
    r = verdict(make(grasp=(40, 170), on_from=170, contact=(35, 180), still_from=180))
    assert r["deadline"] and r["rest_start_s"] == 9.0


def test_deadline_fails_one_step_late():
    r = verdict(make(grasp=(40, 170), on_from=170, contact=(35, 181), still_from=181))
    assert not r["deadline"] and r["task_success"] and not r["full_stl"]
    assert r["rest_start_s"] == 9.05


def test_deadline_needs_41_samples_of_rest():
    tr = make()
    on = np.asarray(tr["signals"][S.sig_on])
    on[110 + 41:] = 0  # rests on samples 110..150 (41 samples = 2 s), then leaves the plate
    tr["signals"][S.sig_on] = on.tolist()
    assert verdict(tr)["deadline"]
    on[110 + 40] = 0  # only 110..149 (40 samples)
    tr["signals"][S.sig_on] = on.tolist()
    assert not verdict(tr)["deadline"]


def test_deadline_fails_while_gripper_still_touches():
    r = verdict(make(contact=(35, 280)))  # gripper never lets go
    assert r["task_success"] and not r["deadline"]


def test_deadline_fails_when_bowl_keeps_moving():
    r = verdict(make(jitter=0.05))  # 0-5 cm/s jitter > 1 cm/s
    assert not r["deadline"]
    assert verdict(make(jitter=0.05), Thresholds(rest_speed=0.06, rest_spin=0.06))["deadline"]


def test_deadline_fails_when_bowl_spins():
    tr = make()
    ang = np.asarray(tr["objects"][BOWL]["angvel"])
    ang[:, 2] = 0.2  # 0.2 rad/s everywhere
    tr["objects"][BOWL]["angvel"] = ang.tolist()
    assert not verdict(tr)["deadline"]


def test_deadline_fails_when_never_on_plate():
    r = verdict(make(on_from=None))
    assert not r["task_success"] and not r["deadline"] and r["landing_s"] is None


# ------------------------------------------------- G[0,11] !Moved(o) -----------


def test_no_move_fails_for_each_object():
    for o in OTHERS:
        r = verdict(move(make(), o, at=150))
        assert not r[f"no_move_{o}"] and not r["no_move"] and not r["clean"] and not r["full_stl"]
        assert r["task_success"] and r["deadline"]
        assert all(r[f"no_move_{x}"] for x in OTHERS if x != o)
        assert r[f"max_disp_{o}"] == 0.06


def test_no_move_window_ends_at_step_220():
    assert verdict(move(make(), "cookies_1", at=221))["no_move"]
    assert not verdict(move(make(), "cookies_1", at=220))["no_move"]


def test_no_move_threshold():
    assert verdict(move(make(), "cookies_1", at=50, dist=0.049))["no_move"]
    assert not verdict(move(make(), "cookies_1", at=50, dist=0.051))["no_move"]


def test_plate_moving_is_ignored():
    assert verdict(move(make(), PLATE, at=100, dist=0.2))["no_move"]


# ------------------------------------------------- velocity from poses ---------


def test_pose_velocities():
    tr = make()
    pos = np.asarray(tr["objects"][BOWL]["pos"])
    pos[:110, 0] += np.arange(110) * 0.01  # 1 cm per step = 0.2 m/s until step 110, then still
    pos[110:, 0] = pos[109, 0]
    tr["objects"][BOWL]["pos"] = pos.tolist()
    sig = monitor.derive_signals(tr, S, vel="pose")
    assert np.allclose(sig[S.sig_speed][1:110], 0.2) and np.allclose(sig[S.sig_speed][110:], 0)
    r = monitor.check_spatial(tr, TH, vel="pose")
    assert r["deadline"] and r["rest_start_s"] == 5.5 and r["rtamt_eq_numpy"]


def test_pose_spin_is_robust_to_rounding():
    # a still bowl at an arbitrary orientation, quaternion rounded to 5 decimals like the recordings
    q = np.array([0.7071, 0.0123, -0.7066, 0.0201])
    q = np.round(q / np.linalg.norm(q), 5)
    qs = np.tile(q, (N, 1)) + np.round(np.random.default_rng(1).normal(0, 3e-6, (N, 4)), 5)
    assert (monitor._quat_angle(qs[1:], qs[:-1]) * 20).max() < 0.01
    a = np.arange(4) * 0.05  # 0.05 rad per step about z = 1 rad/s
    q = np.c_[np.cos(a / 2), 0 * a, 0 * a, np.sin(a / 2)]
    assert np.allclose(monitor._quat_angle(q[1:], q[:-1]) * 20, 1.0)


# ------------------------------------------------- rtamt formula text ----------


def test_rtamt_text_matches_doc_checker_form():
    sp = BowlOnPlateSpec(bowl="b", plate="p", others=("o1",), bowl_name="x")
    assert sp.to_rtamt() == (
        "((on_b_p < 0.5) until (grasp_b > 0.5))"
        " and (eventually[0:180](always[0:40]((on_b_p > 0.5) and (gripper_contact_b < 0.5)"
        " and (speed_b < 0.01) and (spin_b < 0.1))))"
        " and (always[0:220](disp_o1 < 0.05))"
    )


# ------------------------------------------------- saved files -----------------

DOC = HERE.parent.parent / "docs" / "2026-10-25-libero-experiment.md"
GOAL_LOGS = HERE.parent / "eval_logs_stl"


def test_spatial_prompts_match_doc_table():
    specs = json.loads((HERE / "specs.json").read_text())["libero_spatial"]
    rows = [l for l in DOC.read_text().splitlines() if re.match(r"^\| \d \| pick up", l)]
    assert len(rows) == 10
    for l in rows:
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        p = specs[c[0]]["prompts"]
        assert (p["nl"], p["stl_nl"], p["stl"]) == (c[1], c[2], c[3].strip("`")), c[0]
        assert specs[c[0]]["others"] == list(OTHERS)


def test_goal_recordings_reproduce_old_report():
    if not GOAL_LOGS.exists():
        print("  (skipped: no libero_goal recordings)")
        return
    specs = json.loads((HERE / "specs.json").read_text())
    dirs = [str(GOAL_LOGS / v / "traces") for v in ("nl", "stl_nl", "stl", "stl_bddl")]
    rows = monitor.run(dirs, specs, TH, "sim", write=False)
    rate = {v: 100 * np.mean([r["stl_sat"] for r in rows if r["variant"] == v]) for v in ("nl", "stl_nl", "stl", "stl_bddl")}
    assert rate == {"nl": 94, "stl_nl": 92, "stl": 84, "stl_bddl": 70}, rate
    old = {(r["variant"], r["file"]): r for r in json.loads((GOAL_LOGS / "monitor_summary.json").read_text())}
    assert len(old) == len(rows) == 200
    for r in rows:
        o = old[(r["variant"], r["file"])]
        for k in ("task_rob", "stl_sat", "libero", "moved", "clean", "steps"):
            assert r[k] == o[k], (r["file"], k)
        assert {str(a): b for a, b in r["deadline"].items()} == o["deadline"], r["file"]


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
