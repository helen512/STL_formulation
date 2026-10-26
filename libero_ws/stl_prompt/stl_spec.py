"""Small STL AST for LIBERO task specs.

One formula object gives three views:
  - to_rtamt():  rtamt discrete-time syntax, bounds in env steps (20 Hz), used for monitoring
  - to_stl():    compact STL text, bounds in seconds, used as a raw-STL prompt
  - to_english(): template English in LIBERO's imperative style, used as an STL->NL prompt

Atoms are LIBERO BDDL predicates (on, in, open, close, turnon, turnoff), so the
simulator can evaluate them each step with `env._eval_predicate`.

The libero_spatial "bowl on plate" spec (BowlOnPlateSpec, at the bottom) uses
non-BDDL predicates (grasp, rest, moved), so it is written as rtamt text directly.
"""

from __future__ import annotations

from dataclasses import dataclass

HZ = 20  # LIBERO control frequency (steps per second)

# BDDL object/region name -> readable name used in prompts.
NAMES = {
    "akita_black_bowl_1": "black bowl",
    "plate_1": "plate",
    "plate_2": "right plate",
    "flat_stove_1": "stove",
    "flat_stove_1_cook_region": "stove",
    "main_table_stove_front_region": "front of the stove",
    "wooden_cabinet_1_top_side": "top of the cabinet",
    "wooden_cabinet_1_top_region": "top drawer",
    "wooden_cabinet_1_middle_region": "middle drawer",
    "wooden_cabinet_1_bottom_region": "bottom drawer",
    "white_cabinet_1_bottom_region": "bottom drawer",
    "wine_bottle_1": "wine bottle",
    "wine_rack_1_top_region": "wine rack",
    "cream_cheese_1": "cream cheese",
    "alphabet_soup_1": "alphabet soup",
    "tomato_sauce_1": "tomato sauce",
    "butter_1": "butter",
    "basket_1_contain_region": "basket",
    "moka_pot_1": "moka pot",
    "moka_pot_2": "second moka pot",
    "microwave_1": "microwave",
    "microwave_1_heating_region": "microwave",
    "white_yellow_mug_1": "yellow and white mug",
    "porcelain_mug_1": "white mug",
}

# Imperative ("do it") and declarative ("it holds") templates per predicate.
DO = {
    "on": "put the {0} on the {1}",
    "in": "put the {0} in the {1}",
    "open": "open the {0}",
    "close": "close the {0}",
    "turnon": "turn on the {0}",
    "turnoff": "turn off the {0}",
}
IS = {
    "on": "the {0} is on the {1}",
    "in": "the {0} is in the {1}",
    "open": "the {0} is open",
    "close": "the {0} is closed",
    "turnon": "the {0} is on",
    "turnoff": "the {0} is off",
}


def _secs(steps: int) -> str:
    s = steps / HZ
    return f"{s:g}"


def _bound(iv: tuple[int, int] | None) -> str:
    return "" if iv is None else f"[{_secs(iv[0])},{_secs(iv[1])}]"


def _rt_bound(iv: tuple[int, int] | None) -> str:
    return "" if iv is None else f"[{iv[0]}:{iv[1]}]"


def _within(iv: tuple[int, int] | None) -> str:
    if iv is None:
        return ""
    a, b = iv
    if a == 0:
        return f" within {_secs(b)} seconds"
    return f" between {_secs(a)} and {_secs(b)} seconds"


class Formula:
    def atoms(self) -> list["Atom"]:
        raise NotImplementedError

    def __and__(self, other: "Formula") -> "And":
        return And(self, other)

    def __invert__(self) -> "Not":
        return Not(self)


@dataclass(frozen=True)
class Atom(Formula):
    pred: str
    args: tuple[str, ...]

    def __init__(self, pred: str, *args: str):
        object.__setattr__(self, "pred", pred)
        object.__setattr__(self, "args", tuple(args))

    @property
    def names(self) -> list[str]:
        return [NAMES.get(a, a.replace("_", " ")) for a in self.args]

    @property
    def signal(self) -> str:
        # rtamt variable name; one 0/1 signal per atom
        return "_".join([self.pred, *self.args])

    def atoms(self):
        return [self]

    def to_rtamt(self):
        return f"({self.signal} > 0.5)"

    def to_stl(self):
        return f"{self.pred}({', '.join(n.replace(' ', '_') for n in self.names)})"

    def do(self):
        return DO[self.pred].format(*self.names)

    def holds(self):
        return IS[self.pred].format(*self.names)

    def to_english(self):
        return f"make sure {self.holds()}"


@dataclass(frozen=True)
class Not(Formula):
    x: Formula

    def atoms(self):
        return self.x.atoms()

    def to_rtamt(self):
        return f"not({self.x.to_rtamt()})"

    def to_stl(self):
        return f"!{self.x.to_stl()}"

    def to_english(self):
        if isinstance(self.x, Atom):
            return f"make sure it is not the case that {self.x.holds()}"
        return f"do not ({self.x.to_english()})"


@dataclass(frozen=True)
class And(Formula):
    a: Formula
    b: Formula

    def atoms(self):
        return self.a.atoms() + self.b.atoms()

    def to_rtamt(self):
        return f"({self.a.to_rtamt()}) and ({self.b.to_rtamt()})"

    def to_stl(self):
        return f"({self.a.to_stl()} & {self.b.to_stl()})"

    def to_english(self):
        return f"{self.a.to_english()} and {self.b.to_english()}"


@dataclass(frozen=True)
class F(Formula):
    """Eventually."""

    x: Formula
    iv: tuple[int, int] | None = None

    def atoms(self):
        return self.x.atoms()

    def to_rtamt(self):
        return f"eventually{_rt_bound(self.iv)}({self.x.to_rtamt()})"

    def to_stl(self):
        return f"F{_bound(self.iv)} {self.x.to_stl()}"

    def to_english(self):
        x = self.x
        if isinstance(x, Atom):
            return f"{x.do()}{_within(self.iv)}"
        # F(p & F q)  ->  "p, then q"
        if isinstance(x, And) and isinstance(x.a, Atom) and isinstance(x.b, F) and isinstance(x.b.x, Atom):
            return f"{x.a.do()}, then {x.b.x.do()}{_within(self.iv)}"
        # F(p & q)  ->  "p and q"
        if isinstance(x, And) and isinstance(x.a, Atom) and isinstance(x.b, Atom):
            return f"{x.a.do()} and {x.b.do()}{_within(self.iv)}"
        return f"eventually{_within(self.iv)}, {x.to_english()}"


@dataclass(frozen=True)
class G(Formula):
    """Always."""

    x: Formula
    iv: tuple[int, int] | None = None

    def atoms(self):
        return self.x.atoms()

    def to_rtamt(self):
        return f"always{_rt_bound(self.iv)}({self.x.to_rtamt()})"

    def to_stl(self):
        return f"G{_bound(self.iv)} {self.x.to_stl()}"

    def to_english(self):
        if isinstance(self.x, Not) and isinstance(self.x.x, Atom):
            return f"do not {self.x.x.do()}"
        if isinstance(self.x, Atom):
            return f"make sure {self.x.holds()} the whole time"
        return f"at all times{_within(self.iv)}, {self.x.to_english()}"


@dataclass(frozen=True)
class U(Formula):
    """a until b."""

    a: Formula
    b: Formula
    iv: tuple[int, int] | None = None

    def atoms(self):
        return self.a.atoms() + self.b.atoms()

    def to_rtamt(self):
        return f"({self.a.to_rtamt()}) until{_rt_bound(self.iv)} ({self.b.to_rtamt()})"

    def to_stl(self):
        return f"({self.a.to_stl()} U{_bound(self.iv)} {self.b.to_stl()})"

    def to_english(self):
        # !p U q  ->  "do not p until you have q"
        if isinstance(self.a, Not) and isinstance(self.a.x, Atom) and isinstance(self.b, Atom):
            return f"{self.b.do()}{_within(self.iv)} before you {self.a.x.do()}"
        return f"{self.a.to_english()} until {self.b.to_english()}{_within(self.iv)}"


def unique_atoms(phi: Formula) -> list[Atom]:
    seen: dict[str, Atom] = {}
    for a in phi.atoms():
        seen.setdefault(a.signal, a)
    return list(seen.values())


def objects(phi: Formula) -> list[str]:
    out: list[str] = []
    for a in unique_atoms(phi):
        for o in a.args:
            if o not in out:
                out.append(o)
    return out


# ---------------------------------------------------------------------------
# libero_spatial: one fixed "bowl on plate" spec, the same for all 10 tasks.
#
#   phi = (!On(b,p) U Grasp(b))                      grasp before it lands
#       & F[0,9s] G[0,2s] Rest(b,p)                  lands by 9 s, rests 2 s
#       & AND_{o in O} G[0,11s] !Moved(o)            nothing else moves for 11 s
#
# The predicates are not BDDL atoms, so this spec is written directly as rtamt
# text over recorded/derived signals instead of through the AST above.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    rest_speed: float = 0.01  # m/s, bowl linear speed while resting
    rest_spin: float = 0.1  # rad/s, bowl angular speed while resting
    moved_disp: float = 0.05  # m, displacement from the t=0 position that counts as "moved"


@dataclass(frozen=True)
class BowlOnPlateSpec:
    bowl: str  # BDDL id of the target bowl
    plate: str  # BDDL id of the plate
    others: tuple[str, ...]  # movable objects that must not move
    bowl_name: str  # readable name used in the raw-STL prompt, e.g. black_bowl_on_stove
    land_by_s: float = 9.0
    rest_s: float = 2.0
    still_s: float = 11.0

    # Signal names (rtamt variables). The first three are recorded in the sim;
    # speed, spin and disp are derived offline from the recorded object states.
    @property
    def sig_on(self) -> str:
        return f"on_{self.bowl}_{self.plate}"

    @property
    def sig_grasp(self) -> str:
        return f"grasp_{self.bowl}"

    @property
    def sig_contact(self) -> str:
        return f"gripper_contact_{self.bowl}"

    @property
    def sig_speed(self) -> str:
        return f"speed_{self.bowl}"

    @property
    def sig_spin(self) -> str:
        return f"spin_{self.bowl}"

    @staticmethod
    def sig_disp(obj: str) -> str:
        return f"disp_{obj}"

    @property
    def signals(self) -> list[str]:
        return [self.sig_on, self.sig_grasp, self.sig_contact, self.sig_speed, self.sig_spin] + [
            self.sig_disp(o) for o in self.others
        ]

    # Windows in env steps, both ends included.
    @property
    def land_by(self) -> int:
        return round(self.land_by_s * HZ)

    @property
    def rest_for(self) -> int:
        return round(self.rest_s * HZ)

    @property
    def still_for(self) -> int:
        return round(self.still_s * HZ)

    def rest_rtamt(self, th: Thresholds) -> str:
        return (
            f"({self.sig_on} > 0.5) and ({self.sig_contact} < 0.5)"
            f" and ({self.sig_speed} < {th.rest_speed:g}) and ({self.sig_spin} < {th.rest_spin:g})"
        )

    def parts_rtamt(self, th: Thresholds = Thresholds()) -> dict[str, str]:
        """rtamt text of each conjunct of phi; one `no_move_<obj>` part per object in O."""
        parts = {
            "grasp_first": f"({self.sig_on} < 0.5) until ({self.sig_grasp} > 0.5)",
            "deadline": f"eventually[0:{self.land_by}](always[0:{self.rest_for}]({self.rest_rtamt(th)}))",
        }
        for o in self.others:
            parts[f"no_move_{o}"] = f"always[0:{self.still_for}]({self.sig_disp(o)} < {th.moved_disp:g})"
        return parts

    def to_rtamt(self, th: Thresholds = Thresholds()) -> str:
        return " and ".join(f"({p})" for p in self.parts_rtamt(th).values())

    def to_stl(self) -> str:
        """Raw-STL prompt: ASCII, seconds, bowl named by its location, other objects grouped."""
        b = self.bowl_name
        return (
            f"(!on({b}, plate) U grasped({b})) & F[0,{self.land_by_s:g}] G[0,{self.rest_s:g}] resting_on({b}, plate)"
            f" & G[0,{self.still_s:g}] !moved(other_objects)"
        )

    def stl_nl_suffix(self) -> str:
        """Rule sentence appended word for word to the original instruction."""
        return (
            f" within {self.land_by_s:g} seconds, then release it and leave it resting on the plate"
            f" for {self.rest_s:g} seconds. do not move any other object during the first {self.still_s:g} seconds."
        )
