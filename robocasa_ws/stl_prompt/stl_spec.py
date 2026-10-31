"""STL specs and prompts for the RoboCasa365 atomic_seen tasks (docs/2026-10-31-robocasa-experiment.md).

Pure Python (no robocasa import), so it is shared by the simulator side (launch_eval.py, recorder.py)
and the checker (monitor.py, run in the rtamt venv).

One spec shape for all 18 tasks:

    phi = F[0,T] G Rest  &  AND_{o in O} G !Disturbed(o)

    Rest (P, pick-and-place) = Success & Still(o)
    Rest (F, fixture)        = Success & Released(part) & PartStill(part)
    Rest (N, navigation)     = Success & BaseStopped

T is 60% of the task's RoboCasa episode limit, in whole seconds. `G` without a window runs to the end
of the episode. Every verdict is computed from per-step recordings, so thresholds can change offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HZ = 20  # RoboCasa control frequency (steps per second)
DEADLINE_FRACTION = 0.6  # decision 18


@dataclass(frozen=True)
class TaskInfo:
    index: int  # row in the doc's task table
    kind: str  # "P" pick-and-place, "F" fixture, "N" navigation
    horizon: int  # RoboCasa episode limit in steps (dataset_registry horizon)

    @property
    def deadline_s(self) -> int:
        return round(DEADLINE_FRACTION * self.horizon / HZ)

    @property
    def deadline_step(self) -> int:
        return self.deadline_s * HZ


# RoboCasa's atomic_seen group, in registry order. Horizons are checked against the registry by test_prompts.py.
TASKS: dict[str, TaskInfo] = {
    name: TaskInfo(i, kind, h)
    for i, (name, kind, h) in enumerate(
        [
            ("CloseBlenderLid", "P", 600),
            ("CloseFridge", "F", 600),
            ("CloseToasterOvenDoor", "F", 300),
            ("CoffeeSetupMug", "P", 400),
            ("NavigateKitchen", "N", 300),
            ("OpenCabinet", "F", 700),
            ("OpenDrawer", "F", 500),
            ("OpenStandMixerHead", "F", 300),
            ("PickPlaceCounterToCabinet", "P", 500),
            ("PickPlaceCounterToStove", "P", 400),
            ("PickPlaceDrawerToCounter", "P", 500),
            ("PickPlaceSinkToCounter", "P", 600),
            ("PickPlaceToasterToCounter", "P", 400),
            ("SlideDishwasherRack", "F", 300),
            ("TurnOffStove", "F", 500),
            ("TurnOnElectricKettle", "F", 300),
            ("TurnOnMicrowave", "F", 300),
            ("TurnOnSinkFaucet", "F", 400),
        ]
    )
}


# ------------------------------------------------------------------ prompts ---


def _ident(words: str) -> str:
    """RoboCasa's words with spaces turned into `_` (the policy's tokenizer turns them back)."""
    return words.strip().replace(" ", "_")


def prompt_names(task: str, lang: str, obj_lang: str | None = None, cont_lang: str | None = None) -> dict:
    """Names used by the `stl` / `stl_nl` prompts, taken from RoboCasa's own words.

    P: obj, target, rel (in | on | under)
    F: part (goal predicate argument), released (released() argument), pred (closed | open | slid_in | ...),
       state (English word), pronoun (it | them)
    N: fixture
    obj_lang / cont_lang are RoboCasa's get_obj_lang("obj") / get_obj_lang("container") for the episode.
    """
    kind = TASKS[task].kind
    if kind == "P":
        rel, target = {
            "CloseBlenderLid": ("on", "blender"),
            "CoffeeSetupMug": ("under", "coffee dispenser"),
            "PickPlaceCounterToCabinet": ("in", "cabinet"),
            "PickPlaceCounterToStove": ("in", cont_lang),
            "PickPlaceDrawerToCounter": ("on", "counter"),
            "PickPlaceSinkToCounter": ("on", cont_lang),
            "PickPlaceToasterToCounter": ("on", "plate"),
        }[task]
        obj = {"CloseBlenderLid": "lid", "PickPlaceToasterToCounter": "toasted item"}.get(task, obj_lang)
        if obj is None or target is None:
            raise ValueError(f"{task}: object names missing (obj_lang={obj_lang!r}, cont_lang={cont_lang!r})")
        return {"obj": obj, "target": target, "rel": rel}
    if kind == "N":
        m = re.fullmatch(r"Navigate to the (.+)\.", lang)
        if not m:
            raise ValueError(f"{task}: unexpected instruction {lang!r}")
        return {"fixture": m.group(1)}
    # F
    if task in ("CloseFridge", "CloseToasterOvenDoor", "OpenCabinet", "OpenDrawer", "OpenStandMixerHead",
                "TurnOnSinkFaucet"):
        m = re.fullmatch(r"(Open|Close|Turn on) the (.+)\.", lang)
        if not m:
            raise ValueError(f"{task}: unexpected instruction {lang!r}")
        verb, part = m.groups()
        pred = {"Open": "open", "Close": "closed", "Turn on": "on"}[verb]
    elif task == "SlideDishwasherRack":
        m = re.fullmatch(r"Fully slide the (.+) (in|out)\.", lang)
        if not m:
            raise ValueError(f"{task}: unexpected instruction {lang!r}")
        part, direction = m.groups()
        pred = f"slid_{direction}"
    elif task == "TurnOffStove":
        m = re.fullmatch(r"Turn off the (.+ burner) of the stove\.", lang)
        if not m:
            raise ValueError(f"{task}: unexpected instruction {lang!r}")
        part, pred = m.group(1), "off"
    elif task == "TurnOnElectricKettle":
        part, pred = "electric kettle", "on"
    elif task == "TurnOnMicrowave":
        part, pred = "microwave", "on"
    else:
        raise KeyError(task)
    state = pred.removeprefix("slid_")
    return {
        "part": part,
        "released": "start button" if task == "TurnOnMicrowave" else part,
        "pred": pred,
        "state": state,
        "pronoun": "them" if re.search(r"\bdoors\b", lang) else "it",
    }


def stl_nl_suffix(task: str, names: dict) -> str:
    """Rule sentences appended word for word to RoboCasa's instruction (decision 24)."""
    info = TASKS[task]
    T = info.deadline_s
    if info.kind == "P":
        return f" Finish within {T} seconds, then let go and leave it there until the end. Do not move any other object."
    if info.kind == "F":
        return (f" Finish within {T} seconds, then let go and leave {names['pronoun']} {names['state']} until the end."
                " Do not move any other object.")
    return f" Arrive within {T} seconds and stay there until the end. Do not move any other object."


def stl_prompt(task: str, names: dict) -> str:
    """Raw-STL prompt: ASCII, times in seconds, RoboCasa's words with `_` for spaces."""
    info = TASKS[task]
    T = info.deadline_s
    others = "G !moved(other_objects)"
    if info.kind == "P":
        return f"F[0,{T}] G resting_{names['rel']}({_ident(names['obj'])}, {_ident(names['target'])}) & {others}"
    if info.kind == "F":
        return (f"F[0,{T}] G ({names['pred']}({_ident(names['part'])}) & released({_ident(names['released'])}))"
                f" & {others}")
    return f"F[0,{T}] G (at({_ident(names['fixture'])}) & stopped(robot)) & {others}"


def make_prompts(task: str, lang: str, obj_lang: str | None = None, cont_lang: str | None = None) -> dict:
    """The three prompts of one episode: nl (RoboCasa's instruction), stl_nl (+ rules), stl (raw STL)."""
    names = prompt_names(task, lang, obj_lang, cont_lang)
    return {"nl": lang, "stl_nl": lang + stl_nl_suffix(task, names), "stl": stl_prompt(task, names)}


# --------------------------------------------------------------------- spec ---


@dataclass(frozen=True)
class Thresholds:
    """Starting values from decision 25; tuned in the idle check and the pilot."""

    still_speed: float = 0.01  # m/s, Still(o)
    still_spin: float = 0.25  # rad/s, Still(o)
    part_still: float = 0.01  # rad/s (hinge, knob) or m/s (slide), PartStill(part)
    base_speed: float = 0.02  # m/s, BaseStopped
    base_turn: float = 0.05  # rad/s, BaseStopped
    disturb_disp: float = 0.02  # m, Disturbed(o)
    disturb_rot: float = 10.0  # degrees about any axis, Disturbed(o)
    disturb_tilt: float = 10.0  # degrees, LIBERO's tilt-only Disturbed (diagnostic)
    fixture_changed: float = 0.2  # rad or m, another fixture joint moved from its t=0 value (diagnostic;
    #   raised from 0.02 after the idle check, where free knobs, the kettle switch and a dishwasher door drifted 0.02-0.15)
    grasp_lift: float = 0.02  # m, GraspLift(o) (diagnostic)


# Signal names (rtamt variables).
SIG_SUCCESS = "success"
SIG_SPEED, SIG_SPIN = "speed_obj", "spin_obj"  # P: target object
SIG_CONTACT, SIG_JVEL, SIG_FAR = "gripper_contact_part", "jvel_part", "released_far"  # F
SIG_BASE_SPEED, SIG_BASE_TURN = "base_speed", "base_turn"  # N


def sig_disp(o: str) -> str:
    return f"disp_{o}"


def sig_rot(o: str) -> str:
    return f"rot_{o}"


@dataclass(frozen=True)
class TaskSpec:
    task: str
    others: tuple[str, ...]  # O: free objects that must not be disturbed
    microwave: bool = False  # F spec whose Released is RoboCasa's "gripper > 0.15 m from the button"

    @property
    def info(self) -> TaskInfo:
        return TASKS[self.task]

    @property
    def kind(self) -> str:
        return self.info.kind

    @property
    def deadline(self) -> int:
        return self.info.deadline_step

    def rest_terms(self, th: Thresholds) -> list[tuple[str, str, str, float]]:
        """Rest as a conjunction of (name, signal, op, bound) terms; `op` is '>' or '<'."""
        terms = [("success", SIG_SUCCESS, ">", 0.5)]
        if self.kind == "P":
            terms += [("speed", SIG_SPEED, "<", th.still_speed), ("spin", SIG_SPIN, "<", th.still_spin)]
        elif self.kind == "F" and self.microwave:
            terms += [("released", SIG_FAR, ">", 0.5)]
        elif self.kind == "F":
            terms += [("released", SIG_CONTACT, "<", 0.5), ("part_still", SIG_JVEL, "<", th.part_still)]
        else:
            terms += [("base_speed", SIG_BASE_SPEED, "<", th.base_speed),
                      ("base_turn", SIG_BASE_TURN, "<", th.base_turn)]
        return terms

    def rest_rtamt(self, th: Thresholds) -> str:
        return " and ".join(f"({sig} {op} {b:g})" for _, sig, op, b in self.rest_terms(th))

    def deadline_rtamt(self, th: Thresholds) -> str:
        return f"eventually[0:{self.deadline}](always({self.rest_rtamt(th)}))"

    def undisturbed_rtamt(self, th: Thresholds) -> dict[str, str]:
        """G !Disturbed(o) over the whole episode, one formula per o in O."""
        return {
            o: f"always(({sig_disp(o)} < {th.disturb_disp:g}) and ({sig_rot(o)} < {th.disturb_rot:g}))"
            for o in self.others
        }

    def to_rtamt(self, th: Thresholds = Thresholds()) -> str:
        parts = [self.deadline_rtamt(th), *self.undisturbed_rtamt(th).values()]
        return " and ".join(f"({p})" for p in parts)

    @property
    def signals(self) -> list[str]:
        sigs = [sig for _, sig, _, _ in self.rest_terms(Thresholds())]
        return sigs + [sig_disp(o) for o in self.others] + [sig_rot(o) for o in self.others]
