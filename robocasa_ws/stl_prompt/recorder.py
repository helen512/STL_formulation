"""Per-step recordings of a RoboCasa kitchen episode, for offline STL checking (monitor.py).

Used by launch_eval.py (π0.5 runs) and idle_check.py (zero actions). One recording holds, for every
env step (sample 0 = after reset and RoboCasa's settle steps, sample k = after k actions):

  objects        pos, quat (wxyz), linvel, angvel (world frame) of every free body: RoboCasa's objects
                 under their object names ("obj", "distr_counter_1", ...), plus free fixture parts such as
                 the blender lid ("blender_lid")
  frames         pos, quat of bodies that objects in O are measured against (OpenDrawer: the drawer box)
  joints         qpos of every fixture joint (hinge / slide; robot and free joints excluded)
  goal_qvel      qvel of the task's goal joints (F tasks)
  success        RoboCasa's _check_success(); success_parts: each part of it (task-specific)
  contact        per free body: any gripper geom touches it (gripper), both finger pads touch it (pads);
                 the task's moving part: gripper touches it (part_gripper), any robot geom touches it (part_robot)
  grip_site      position of the gripper's grip site
  base           pos, quat, linvel, angvel of the mobile base

Every reset rebuilds the MuJoCo model, so all handles are looked up again in start().
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np

import robocasa.utils.object_utils as OU
import robosuite.utils.transform_utils as T

from stl_spec import TASKS, make_prompts, prompt_names

FORMAT = "robocasa-1"
ROBOT_PREFIXES = ("robot0_", "mobilebase0_", "gripper0_")
BASE_BODY = "mobilebase0_base"
# Objects in O that sit in a moving part and are measured in that part's frame (decision 21).
PART_FRAME_OBJECTS = {"OpenDrawer": ("drawer_obj",)}


def _r(xs, nd=5):
    return [round(float(v), nd) for v in xs]


def _subtree(model, root: int) -> set[int]:
    """Body ids of `root` and all its descendants."""
    out = set()
    for b in range(model.nbody):
        a = b
        while a > 0 and a != root:
            a = model.body_parentid[a]
        if a == root:
            out.add(b)
    return out


# ------------------------------------------------------------- task wiring ---


def goal_joints(env, task: str) -> list[str]:
    """Joints whose state RoboCasa's success check reads (F tasks)."""
    if task == "CloseFridge":
        return list(env.fxtr._fridge_door_joint_names)  # Fridge.is_closed(compartment="fridge")
    if task in ("OpenCabinet",):
        return list(env.fxtr.door_joint_names)
    if task == "CloseToasterOvenDoor":
        return list(env.toaster_oven.door_joint_names)
    if task == "OpenDrawer":
        return list(env.drawer.door_joint_names)
    if task == "OpenStandMixerHead":
        return [env.stand_mixer._joint_names["head"]]
    if task == "SlideDishwasherRack":
        return [env.dishwasher._joint_names["rack"]]
    if task == "TurnOffStove":
        return [f"{env.stove.naming_prefix}knob_{env.knob}_joint"]
    if task == "TurnOnElectricKettle":
        return [env.electric_kettle._joint_names["switch"]]
    if task == "TurnOnSinkFaucet":
        return [f"{env.sink.naming_prefix}handle_joint"]
    return []  # P, N, TurnOnMicrowave (the button has no joint)


def success_parts(env, task: str) -> dict[str, bool]:
    """Each conjunct of RoboCasa's _check_success() (only for tasks where it has more than one)."""
    if task == "CloseBlenderLid":
        lid = f"{env.blender.blender_lid.name}_main"
        return {"lid_on": bool(env.blender.get_state()["lid_on_blender"]),
                "gripper_far": bool(OU.gripper_fxtr_far(env, lid, th=0.15))}
    if task == "CoffeeSetupMug":
        return {"under_dispenser": bool(env.coffee_machine.check_receptacle_placement_for_pouring(env, "obj")),
                "gripper_far": bool(OU.gripper_obj_far(env))}
    if task == "PickPlaceCounterToCabinet":
        return {"in_cabinet": bool(OU.obj_inside_of(env, "obj", env.cab)), "gripper_far": bool(OU.gripper_obj_far(env))}
    if task == "PickPlaceCounterToStove":
        return {"in_pan": bool(OU.check_obj_in_receptacle(env, "obj", "container", th=0.07)),
                "gripper_far": bool(OU.gripper_obj_far(env))}
    if task == "PickPlaceDrawerToCounter":
        return {"on_counter": bool(OU.check_obj_any_counter_contact(env, "obj")),
                "gripper_far": bool(OU.gripper_obj_far(env, "obj"))}
    if task == "PickPlaceSinkToCounter":
        return {"on_plate": bool(OU.check_obj_in_receptacle(env, "obj", "container")),
                "plate_on_counter": bool(env.check_contact(env.objects["container"], env.counter)),
                "gripper_far": bool(OU.gripper_obj_far(env))}
    if task == "PickPlaceToasterToCounter":
        return {"on_plate": bool(OU.check_obj_in_receptacle(env, "obj", "plate")),
                "gripper_far": bool(OU.gripper_obj_far(env))}
    if task == "TurnOnMicrowave":
        return {"turned_on": bool(env.microwave.get_state()["turned_on"]),
                "gripper_far": bool(env.microwave.gripper_button_far(env, button="start_button"))}
    if task == "NavigateKitchen":
        bid = env.sim.model.body_name2id(BASE_BODY)
        pos = np.array(env.sim.data.body_xpos[bid])
        yaw = T.mat2euler(np.array(env.sim.data.body_xmat[bid]).reshape((3, 3)))[2]  # as in _check_success
        return {"at_pos": bool(np.linalg.norm(env.target_pos[:2] - pos[:2]) <= 0.20),
                "at_heading": bool(np.cos(env.target_ori[2] - yaw) >= 0.98)}
    return {}


def roles(env, task: str) -> dict:
    """Target object, receptacle, source container and the others O (decision 21)."""
    kind = TASKS[task].kind
    objs = list(env.objects)
    target = receptacle = source = None
    if task == "CloseBlenderLid":
        target = "blender_lid"
    elif kind == "P":
        target = "obj"
        receptacle = {"PickPlaceCounterToStove": "container", "PickPlaceSinkToCounter": "container",
                      "PickPlaceToasterToCounter": "plate"}.get(task)
        source = "obj_container" if "obj_container" in objs else None
    others = [o for o in objs if o not in (target, receptacle, source)]
    return {"target": target, "receptacle": receptacle, "source": source, "others": others}


def episode_names(env, task: str) -> dict:
    lang = env.get_ep_meta()["lang"]
    obj_lang = env.get_obj_lang("obj") if "obj" in env.objects else None
    cont_lang = env.get_obj_lang(obj_name="container") if "container" in env.objects else None
    return {"lang": lang, "obj_lang": obj_lang, "cont_lang": cont_lang,
            "names": prompt_names(task, lang, obj_lang, cont_lang),
            "prompts": make_prompts(task, lang, obj_lang, cont_lang)}


# ---------------------------------------------------------------- recorder ---


class Recorder:
    def __init__(self, task: str, variant: str, meta: dict | None = None):
        self.task = task
        self.variant = variant
        self.meta = meta or {}
        self.trace: dict | None = None

    # -- setup after each reset
    def start(self, env, seed: int | None, prompt: str, names: dict) -> dict:
        m, d = env.sim.model, env.sim.data
        self.env = env
        r = roles(env, self.task)

        # free bodies, keyed by RoboCasa object name
        body_key = {env.obj_body_id[o.name]: k for k, o in env.objects.items()}
        if self.task == "CloseBlenderLid":
            body_key[m.body_name2id(f"{env.blender.blender_lid.name}_main")] = "blender_lid"
        self.free = {}
        for j in range(m.njnt):
            if m.jnt_type[j] == 0:
                b = int(m.jnt_bodyid[j])
                self.free[body_key.get(b, m.body_id2name(b))] = b
        self.free_sub = {k: _subtree(m, b) for k, b in self.free.items()}

        # fixture joints
        self.joint_names, self.joint_adr = [], []
        for j in range(m.njnt):
            n = m.joint_id2name(j)
            if m.jnt_type[j] in (2, 3) and n and not n.startswith(ROBOT_PREFIXES):
                self.joint_names.append(n)
                self.joint_adr.append(int(m.jnt_qposadr[j]))
        self.goal = goal_joints(env, self.task)
        self.goal_dof = [int(m.jnt_dofadr[m.joint_name2id(n)]) for n in self.goal]

        # moving part: every geom under the goal joints' bodies; for the microwave, the start-button geom
        # (it sits on the microwave's main body and has no joint)
        part = set()
        for n in self.goal:
            part |= _subtree(m, int(m.jnt_bodyid[m.joint_name2id(n)]))
        self.part_geoms = {i for i in range(m.ngeom) if int(m.geom_bodyid[i]) in part}
        if self.task == "TurnOnMicrowave":
            self.part_geoms = {m.geom_name2id(f"{env.microwave.naming_prefix}start_button")}

        # frames for objects measured inside a moving part
        self.frames = {}
        for o in PART_FRAME_OBJECTS.get(self.task, ()):
            if o in r["others"] and self.goal:
                self.frames[o] = m.body_id2name(int(m.jnt_bodyid[m.joint_name2id(self.goal[0])]))

        g = env.robots[0].gripper["right"]
        self.g_geoms = {m.geom_name2id(n) for n in g.contact_geoms}
        self.lpad = {m.geom_name2id(n) for n in g.important_geoms["left_fingerpad"]}
        self.rpad = {m.geom_name2id(n) for n in g.important_geoms["right_fingerpad"]}
        self.robot_geoms = {i for i in range(m.ngeom)
                            if (m.body_id2name(int(m.geom_bodyid[i])) or "").startswith(ROBOT_PREFIXES)}
        self.site = env.robots[0].eef_site_id["right"]
        self.base = m.body_name2id(BASE_BODY)

        ep_meta = env.get_ep_meta()
        info = TASKS[self.task]
        self.trace = {
            "format": FORMAT,
            "task": self.task,
            "kind": info.kind,
            "variant": self.variant,
            "seed": seed,
            "episode": None if seed is None else seed - self.meta.get("seed0", 1000),
            "hz": 20,
            "horizon": info.horizon,
            "deadline_s": info.deadline_s,
            "prompt": prompt,
            "orig_prompt": ep_meta["lang"],
            "names": names,
            "layout_id": ep_meta.get("layout_id"),
            "style_id": ep_meta.get("style_id"),
            "object_models": {c["name"]: c.get("info", {}).get("mjcf_path") for c in ep_meta.get("object_cfgs", [])},
            "fixture_refs": {k: str(v) for k, v in ep_meta.get("fixture_refs", {}).items()},
            "extra_meta": {k: ep_meta[k] for k in ("should_pull", "task_refs") if k in ep_meta},
            **r,
            "goal_joints": self.goal,
            "part_bodies": sorted({m.body_id2name(int(m.geom_bodyid[i])) for i in self.part_geoms}),
            "part_geoms": len(self.part_geoms),
            "frames_of": self.frames,
            "joint_names": self.joint_names,
            "objects": {k: {"pos": [], "quat": [], "linvel": [], "angvel": []} for k in self.free},
            "frames": {b: {"pos": [], "quat": []} for b in set(self.frames.values())},
            "joints": [],
            "goal_qvel": {n: [] for n in self.goal},
            "success": [],
            "success_parts": {},
            "contact": {"gripper": {k: [] for k in self.free}, "pads": {k: [] for k in self.free},
                        "part_gripper": [], "part_robot": []},
            "grip_site": [],
            "base": {"pos": [], "quat": [], "linvel": [], "angvel": []},
            **self.meta,
        }
        self.sample(bool(env._check_success()))
        return self.trace

    # -- one sample per env step
    def sample(self, success: bool):
        env, t = self.env, self.trace
        m, d = env.sim.model, env.sim.data
        for k, b in self.free.items():
            o = t["objects"][k]
            name = m.body_id2name(b)
            o["pos"].append(_r(d.xpos[b]))
            o["quat"].append(_r(d.xquat[b]))
            o["linvel"].append(_r(d.get_body_xvelp(name)))
            o["angvel"].append(_r(d.get_body_xvelr(name)))
        for body, f in t["frames"].items():
            b = m.body_name2id(body)
            f["pos"].append(_r(d.xpos[b]))
            f["quat"].append(_r(d.xquat[b]))
        t["joints"].append(_r(d.qpos[self.joint_adr]))
        for n, dof in zip(self.goal, self.goal_dof):
            t["goal_qvel"][n].append(round(float(d.qvel[dof]), 5))
        t["success"].append(bool(success))
        for k, v in success_parts(env, self.task).items():
            t["success_parts"].setdefault(k, []).append(bool(v))

        # contacts: bodies touched by any gripper geom / by each finger pad / by any robot geom
        g_bodies, l_bodies, r_bodies = set(), set(), set()
        g_touch, robot_touch = set(), set()  # geoms touched by the gripper / by any robot geom
        bodyid = m.geom_bodyid
        n = d.ncon
        g1, g2 = d.contact.geom1[:n].tolist(), d.contact.geom2[:n].tolist()
        for a, b in zip(g1 + g2, g2 + g1):
            if a in self.robot_geoms and b not in self.robot_geoms:
                ob = int(bodyid[b])
                robot_touch.add(b)
                if a in self.g_geoms:
                    g_bodies.add(ob)
                    g_touch.add(b)
                if a in self.lpad:
                    l_bodies.add(ob)
                if a in self.rpad:
                    r_bodies.add(ob)
        for k, sub in self.free_sub.items():
            t["contact"]["gripper"][k].append(bool(sub & g_bodies))
            t["contact"]["pads"][k].append(bool(sub & l_bodies) and bool(sub & r_bodies))
        t["contact"]["part_gripper"].append(bool(self.part_geoms & g_touch))
        t["contact"]["part_robot"].append(bool(self.part_geoms & robot_touch))

        t["grip_site"].append(_r(d.site_xpos[self.site]))
        base = t["base"]
        base["pos"].append(_r(d.xpos[self.base]))
        base["quat"].append(_r(d.xquat[self.base]))
        base["linvel"].append(_r(d.get_body_xvelp(BASE_BODY)))
        base["angvel"].append(_r(d.get_body_xvelr(BASE_BODY)))

    def write(self, out_dir: Path, name: str) -> Path | None:
        t, self.trace = self.trace, None
        # A trace with only the reset sample is a reset that was never stepped; skip it.
        if t is None or len(t["success"]) < 2:
            return None
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / name
        with gzip.open(path, "wt") as f:
            json.dump(t, f)
        return path
