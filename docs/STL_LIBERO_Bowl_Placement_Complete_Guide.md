# Signal Temporal Logic (STL): Complete Guide with a LIBERO Bowl-Placement Example

**Purpose:** A standalone reference on the notation, formal semantics, quantitative robustness, physical predicates, design choices, and practical monitoring of STL for robotic manipulation.

**Running task:** “Pick up the black bowl between the plate and the ramekin and place it on the plate.”

**Key example** (all time bounds are **illustrative choices**, not constraints supplied by LIBERO):

$$
\boxed{\begin{aligned}
\varphi ={}& \mathbf F_{[0,10]}\left(
    \operatorname{Grasp}(b)\;\land\;
    \mathbf F_{[0,18]}\mathbf G_{[0,2]}\operatorname{Placed}(b,p)
\right)\\
&\land\;\mathbf G_{[0,30]}\operatorname{Safe}.
\end{aligned}}
$$

In ordinary English: **At some time during the first 10 seconds, the correct bowl is grasped; starting from that grasp time, there is a time within the next 18 seconds when the bowl is successfully placed on the plate and remains placed continuously for 2 seconds. The safety condition must hold throughout the entire first 30 seconds.**

---

## Contents

1. [What STL is and why robotics uses it](#1-what-stl-is-and-why-robotics-uses-it)
2. [The trajectory or signal that STL evaluates](#2-the-trajectory-or-signal-that-stl-evaluates)
3. [STL syntax: every logical and temporal operator](#3-stl-syntax-every-logical-and-temporal-operator)
4. [Boolean satisfaction semantics](#4-boolean-satisfaction-semantics)
5. [Every term of the example formula explained](#5-every-term-of-the-example-formula-explained)
6. [A timeline and an exact interpretation of nested bounds](#6-a-timeline-and-an-exact-interpretation-of-nested-bounds)
7. [How to convert natural language to verifiable predicates](#7-how-to-convert-natural-language-to-verifiable-predicates)
8. [How to define Grasp, Placed, Safe and target identification](#8-how-to-define-grasp-placed-safe-and-target-identification)
9. [Quantitative robustness: not just true or false](#9-quantitative-robustness-not-just-true-or-false)
10. [Step-by-step positive and negative examples](#10-step-by-step-positive-and-negative-examples)
11. [Stronger and alternative STL formulations](#11-stronger-and-alternative-stl-formulations)
12. [Uncertainty and selection of thresholds](#12-uncertainty-and-selection-of-thresholds)
13. [Continuous vs. discrete time, sampling, and monitoring horizon](#13-continuous-vs-discrete-time-sampling-and-monitoring-horizon)
14. [A working NumPy monitor for the exact sample formula](#14-a-working-numpy-monitor-for-the-exact-sample-formula)
15. [Using an STL library (RTAMT)](#15-using-an-stl-library-rtamt)
16. [LIBERO / MuJoCo / π0.5 evaluation pipeline](#16-libero--mujoco--π05-evaluation-pipeline)
17. [Common errors and research limitations](#17-common-errors-and-research-limitations)
18. [Notation glossary](#18-notation-glossary)
19. [Suggested literature and code](#19-suggested-literature-and-code)

---

## 1. What STL is and why robotics uses it

**Signal Temporal Logic (STL)** is a formal language used to describe how numerical measurements and events should evolve **over time**. An STL formula can constrain:

- **What** should be true: e.g. a bowl is inside the plate boundary.
- **When** it must be true: e.g. before 28 seconds.
- **For how long** it must remain true: e.g. continuously for 2 seconds.
- **In what order** things should happen: e.g. first grasp, then place.
- **What must never happen**: e.g. an unsafe collision during the episode.

STL differs from checking a single final state. The final state alone cannot determine whether the robot grasped the correct object, exceeded a collision limit mid-trajectory, dropped the bowl, or temporarily achieved an unstable placement.

**STL is a specification language, not a robot controller by itself.** To verify an STL formula, a monitor consumes a trajectory plus meaningful, measurable predicates. A robot policy (such as π0.5) can be evaluated independently against that specification.

STL is related to **LTL** (Linear Temporal Logic) and **MTL** (Metric Temporal Logic): STL specializes temporal reasoning to real-valued signals. Bounded operators such as $\mathbf F_{[0,10]}$ explicitly specify time intervals.

## 2. The trajectory or signal that STL evaluates

Let the physical or simulated system state be

$$
 x(t)\in\mathbb R^n,\qquad t\in[0,T].
$$

- $x$ = system **state vector** (robot pose, object poses, gripper state, velocity, contacts, etc.).
- $t$ = current time.
- $T$ = trajectory/episode length in seconds.
- $n$ = number of continuous state variables.
- $x(t)$ = value of all state variables at instant $t$.

Not everything is naturally a real number. A contact or holding state can be represented as a Boolean observation or encoded numerically (e.g. $+1$ for true and $-1$ for false). The monitor must know how each input is defined.

An **execution trace**, **trajectory**, or **signal** is the time-indexed sequence $x(\cdot)$, often logged as

$$
\tau = [(t_0,x_0),(t_1,x_1),\ldots,(t_N,x_N)].
$$

In continuous-time STL, time is real-valued. In simulation, one often evaluates a **sampled approximation** at $t_k=k\Delta t$ with timestep $\Delta t$.

A specification is evaluated at an **evaluation time**, usually $t=0$:

$$
(x,0)\models\varphi.
$$

The symbol $\models$ is read as **“satisfies.”** The preceding expression says: “The trajectory $x$ satisfies the STL formula $\varphi$ when the formula is interpreted starting at time 0.”

## 3. STL syntax: every logical and temporal operator

### 3.1 Atomic predicate

An **atomic predicate** is the smallest testable statement, typically constructed from an inequality:

$$
\mu_h(t) := [h(x(t))\ge0],
$$

where:

- $\mu_h$ = named Boolean predicate;
- $h$ = real-valued function of state;
- $[\cdot]$ = Boolean truth value of the enclosed comparison;
- $\ge$ = greater than or equal to.

Example:

$$
 h_{\mathrm{inside}}(x(t))=R_p-r_b-m-d_{xy}(t),
 \qquad\mu_{\mathrm{inside}}(t):=[h_{\mathrm{inside}}\ge0].
$$

The predicate is true exactly when the bowl's support footprint fits within the assumed circular usable plate region, with an extra margin (under the geometric assumptions explained below).

### 3.2 Formula grammar

A common core of STL is

$$
\varphi ::= \top\mid \mu\mid \neg\varphi\mid
(\varphi_1\land\varphi_2)\mid
(\varphi_1\;\mathbf U_I\;\varphi_2).
$$

- $::=$ = “can be formed as” (a grammar definition).
- $\varphi$ = an arbitrary STL formula.
- $\mu$ = an atomic predicate.
- $\top$ = always true; $\bot$ = always false.
- $I=[a,b]$ = a time interval, normally $0\le a\le b$.
- $\mathbf U_I$ = time-bounded **until** operator.
- $\neg$ = not; $\land$ = and.

Many texts present $\mathbf F$ and $\mathbf G$ as additional primitive operators; they can also be defined using **until** and negation.

### 3.3 Operator reference

| Symbol | Spoken name | Exact informal meaning | Example |
|---|---|---|---|
| $\top$ | True | Always satisfied | $\top$ |
| $\bot$ | False | Never satisfied | $\bot$ |
| $\neg\phi$ | NOT | $\phi$ is false | $\neg\operatorname{Holding}$ |
| $\phi\land\psi$ | AND | Both hold at the evaluation time | $\operatorname{Contact}\land\operatorname{Stable}$ |
| $\phi\lor\psi$ | OR | At least one holds | $\operatorname{Left}\lor\operatorname{Right}$ |
| $\phi\rightarrow\psi$ | IMPLIES | If $\phi$ then $\psi$ (Boolean implication) | $\operatorname{Released}\rightarrow\operatorname{Supported}$ |
| $\mathbf F_{[a,b]}\phi$ | Eventually / finally | $\phi$ holds at **some** time between $a$ and $b$ seconds from **now** | $\mathbf F_{[0,10]}\operatorname{Grasp}$ |
| $\mathbf G_{[a,b]}\phi$ | Always / globally | $\phi$ holds at **every** time between $a$ and $b$ seconds from **now** | $\mathbf G_{[0,2]}\operatorname{Stable}$ |
| $\phi\;\mathbf U_{[a,b]}\;\psi$ | Until | $\phi$ remains true from now until some time in the interval when $\psi$ becomes true | $\operatorname{Clear}\;\mathbf U_{[0,10]}\;\operatorname{Goal}$ |
| $\mathbf F_{[0,\infty)}\phi$ | Unbounded eventually | $\phi$ occurs at some future time (may not be decidable from finite data) | “Eventually complete” |
| $\mathbf G_{[0,\infty)}\phi$ | Unbounded always | $\phi$ remains true forever | “Never collide” |

**Derivations:**

$$
\mathbf F_I\phi\equiv \top\;\mathbf U_I\;\phi,
\qquad
\mathbf G_I\phi\equiv\neg\mathbf F_I\neg\phi.
$$

**Notation variations:** $\Diamond_I$ = $\mathbf F_I$; $\Box_I$ = $\mathbf G_I$. In some books, $U$ is written $\mathcal U$.

**Important:** $\mathbf F_{[a,b]}\phi$ does **not** mean $\phi$ is true for the entire interval. That is the role of $\mathbf G_{[a,b]}\phi$.

## 4. Boolean satisfaction semantics

Formally define $(x,t)\models\phi$ recursively:

**Atomic predicate:**

$$
(x,t)\models\mu_h\iff h(x(t))\ge0.
$$

**Negation:**

$$
(x,t)\models\neg\phi\iff (x,t)\not\models\phi.
$$

**Conjunction:**

$$
(x,t)\models\phi\land\psi
\iff (x,t)\models\phi\ \text{and}\ (x,t)\models\psi.
$$

**Eventually:**

$$
(x,t)\models\mathbf F_{[a,b]}\phi
\iff\exists t'\in[t+a,t+b]:(x,t')\models\phi.
$$

The quantifier $\exists$ means **“there exists at least one.”**

**Always:**

$$
(x,t)\models\mathbf G_{[a,b]}\phi
\iff\forall t'\in[t+a,t+b]:(x,t')\models\phi.
$$

The quantifier $\forall$ means **“for every.”**

**Until (standard strong-until interpretation):**

$$
\begin{aligned}
(x,t)\models\phi\,\mathbf U_{[a,b]}\,\psi
\iff\;&\exists t'\in[t+a,t+b]\ \text{such that}\\
&(x,t')\models\psi\quad\text{and}\\
&\forall s\in[t,t'):\ (x,s)\models\phi.
\end{aligned}
$$

$\psi$ must eventually happen in the specified interval; $\phi$ holds continuously **before** that witness time $t'$. The endpoint convention may differ in individual presentations; use the exact convention of the selected monitor.

### 4.1 Relative time is fundamental

STL temporal bounds are **relative to the time at which the operator is evaluated**. Consider:

$$
\mathbf F_{[0,10]}\left(A\land\mathbf F_{[0,18]}B\right).
$$

If $A$ becomes true at $t=7$, then $B$ may become true at any time in $[7,25]$. The inner 18-second clock is anchored at 7 seconds, not at the episode start.

## 5. Every term of the example formula explained

The specification is

$$
\boxed{
\varphi=
\underbrace{\mathbf F_{[0,10]}
\left(
\underbrace{\operatorname{Grasp}(b)}_{\text{correct bowl grasped}}
\land
\underbrace{\mathbf F_{[0,18]}
\mathbf G_{[0,2]}
\operatorname{Placed}(b,p)}_{\text{eventual sustained placement}}
\right)}_{\varphi_{\mathrm{task}}}
\ \land\ 
\underbrace{\mathbf G_{[0,30]}\operatorname{Safe}}_{\varphi_{\mathrm{safety}}}
}
$$

| Term | Precise definition in this example |
|---|---|
| $\varphi$ (phi) | The **entire** required STL property. A trajectory succeeds only if both its task and safety components are satisfied. |
| $:=$ or $=$ | “Is defined as / equals.” |
| $b$ | The **particular** black bowl identified as being between the plate and ramekin in the initial scene. It must be tracked by identity. |
| $p$ | The plate that is the intended placement target. |
| $\operatorname{Grasp}(b)$ | A verifiable Boolean predicate true when the gripper is actually grasping bowl $b$ (not merely near it). |
| $\operatorname{Placed}(b,p)$ | A compound Boolean predicate describing correct, supported, sufficiently stable, released placement of bowl $b$ on plate $p$. |
| $\operatorname{Safe}$ | A scene- and task-specific Boolean predicate indicating relevant safety constraints are currently satisfied. |
| $\mathbf F$ | **Eventually**, i.e., at least one future witness time must exist. |
| $\mathbf G$ | **Always**, i.e., the property must hold at every time in the specified window. |
| $[0,10]$ | Window from **now** to 10 seconds later, inclusive (under closed-interval semantics). |
| $[0,18]$ | Window from the **chosen grasp witness time** to 18 seconds after it. |
| $[0,2]$ | Window starting at the **chosen placement witness time** and ending 2 seconds later. |
| $[0,30]$ | Absolute episode-relative window 0–30 seconds because the top-level $\mathbf G$ is evaluated at $t=0$. |
| $\land$ | Logical **and**; both clauses must hold. |
| Parentheses $(\cdots)$ | Determine which subformula the outer eventually operator applies to; crucial for temporal nesting. |
| $\varphi_{\mathrm{task}}$ | Subformula for successfully performing the manipulation. |
| $\varphi_{\mathrm{safety}}$ | Subformula for observing the safety condition throughout the evaluation interval. |

More formally, define a **grasp witness** $t_g$ and a **placement-start witness** $t_p$ (both *existentially* chosen by the STL semantics). Then $(x,0)\models\varphi$ if and only if:

$$
\begin{gathered}
\exists t_g\in[0,10],\qquad
\operatorname{Grasp}(b,t_g)=\mathrm{True},\\
\exists t_p\in[t_g,t_g+18],\\
\forall s\in[t_p,t_p+2]:\ \operatorname{Placed}(b,p,s)=\mathrm{True},\\
\forall s\in[0,30]:\ \operatorname{Safe}(s)=\mathrm{True}.
\end{gathered}
$$

**Crucial distinction:** The formula requires grasping at some moment **before or at** the onset of a stable placement interval. It does **not** require maintaining the grasp until placement (indeed that would conflict with “released”), and it does **not** require the bowl to remain placed after the selected 2-second interval unless separately specified.

## 6. A timeline and an exact interpretation of nested bounds

### 6.1 One satisfying trajectory

Assume:

- $t_g=7\,\mathrm s$: target bowl is grasped.
- $t_p=20\,\mathrm s$: the first moment of the chosen continuously successful placement.
- $[20,22]\,\mathrm s$: placement remains valid.
- $[0,30]\,\mathrm s$: safety never violated.

Then:

$$
7\in[0,10],\quad 20\in[7,25],\quad
\operatorname{Placed}\text{ holds on }[20,22].
$$

Therefore $\varphi$ is satisfied.

```text
seconds   0       7      10              20  22      30
          |-------|-------|---------------|---|-------|
Grasp     ....... [TRUE] ..............................
Placed    .................... TRUE ===================
Selected placement hold:                  [20--22]
Safe      [================ always true ==============]
          |<-- outer F[0,10] -->|
                  |<------ inner F[0,18] ------>|
```

### 6.2 What is the latest possible success?

A witness at $t_g=10$ allows the placement witness as late as $t_p=28$, and holding through $t_p+2=30$:

$$
10+18+2=30\,\mathrm s.
$$

This is the **future observation horizon** of the task subformula. The overall formula's horizon is also 30 seconds because of the safety clause.

### 6.3 Different meanings that should not be conflated

- “Place within 18 seconds **after grasp**”: $\mathbf F_{[0,10]}(\operatorname{Grasp}\land\mathbf F_{[0,18]}\cdots)$.
- “Place within 18 seconds **of episode start**”: $\mathbf F_{[0,18]}\operatorname{Placed}$ (with ordering added separately if needed).
- “Keep placed **until episode end**”: one possible explicit form is $\mathbf F_{[0,28]}\mathbf G_{[0,2]}\operatorname{Placed}\ \land\ \mathbf G_{[28,30]}\operatorname{Placed}$; note this imposes an extra absolute-time requirement and differs from merely holding for any 2 seconds.

## 7. How to convert natural language to verifiable predicates

Original NL:

> Pick up the black bowl between the plate and the ramekin and place it on the plate.

A good translation distinguishes **reference resolution**, **task progress**, **terminal success**, and **safety**:

| NL phrase | Formal meaning | Measurements needed |
|---|---|---|
| “the black bowl between the plate and the ramekin” | Identify which of several similar bowls is target $b$ **at initial time** | Object identities, types, initial positions, plate/ramekin locations |
| “pick up” | Robot obtains a legitimate grasp on bowl $b$ | Gripper contacts, attachment state or other supported grasp signals, bowl motion |
| “place it on the plate” | Bowl $b$ becomes geometrically supported by plate $p$, has appropriate contact, is released and stable | Bowl/plate geometry, transforms, contact information, velocity, gripper state |
| Implicit “do not break or collide unsafely” | Relevant hazards are avoided | Clearance, contacts, forces, velocities and task-specific rules |
| Timing (not stated in NL) | Deadlines, settling time, duration | Experiment horizon, physical dynamics, policy limits, design requirements |

**Do not treat an inferred deadline or safety margin as though it were explicitly supplied by the user's instruction.** Annotate every parameter with its provenance (language, scene geometry, dynamics, uncertainty, experimental protocol, or designer assumption).

## 8. How to define Grasp, Placed, Safe and target identification

### 8.1 Geometry and terminology

Let:

- $q_b(t)=(x_b(t),y_b(t),z_b(t))$: bowl reference position.
- $q_p(t)=(x_p(t),y_p(t),z_p(t))$: plate reference position.
- $c_b(t)=(x_{b,c}(t),y_{b,c}(t))$: **bowl support-footprint center** in the horizontal plane.
- $c_p(t)=(x_{p,c}(t),y_{p,c}(t))$: plate usable-region center in the same frame.
- $R_p$: radius of a circular **usable support region** on the plate.
- $r_b$: radius of the bowl's **actual supporting foot** (not necessarily its wide top rim).
- $m$: additional placement margin.
- $d_{xy}(t)=\|c_b(t)-c_p(t)\|_2$: horizontal Euclidean distance.
- $z_b^{\rm bottom}(t)$: height of the bowl's support foot at the relevant contact point.
- $z_p^{\rm surface}(t)$: plate supporting surface height at the relevant location.
- $v_b(t)$: bowl linear velocity.
- $\omega_b(t)$: bowl angular velocity.
- $\operatorname{Contact}(b,p,t)$: bowl-plate contact predicate.
- $\operatorname{Holding}(r,b,t)$: robot $r$ is holding bowl $b$.

**Coordinate-frame requirement:** bowl and plate coordinates must be in the **same** world or tabletop frame. For tilted plates, project to the plate's own support plane rather than assuming world XY.

### 8.2 Spatial containment for an approximately circular plate

$$
\begin{aligned}
 d_{xy}(t)&=\sqrt{(x_{b,c}(t)-x_{p,c}(t))^2+
                         (y_{b,c}(t)-y_{p,c}(t))^2},\\
 d_{\rm allowed}&=R_p-r_b-m,\\
 \operatorname{Inside}(b,p,t)&:=
 [d_{\rm allowed}\ge0]\land[d_{xy}(t)\le d_{\rm allowed}].
\end{aligned}
$$

If $d_{\rm allowed}<0$, the specified bowl foot cannot fit in the usable circular region under this model.

Example **invented dimensions for illustration**:

$$
R_p=0.11\,\mathrm m,\quad r_b=0.05\,\mathrm m,
\quad m=0.01\,\mathrm m,
$$

$$
 d_{\rm allowed}=0.05\,\mathrm m.
$$

So a projected bowl-foot center within **5 cm** of the plate's usable-region center meets this geometric test. These are **not measured LIBERO dimensions**.

**Stronger irregular-shape version:**

$$
\operatorname{Footprint}(b,t)\subseteq
  \operatorname{Erode}(\operatorname{UsableSurface}(p,t),m).
$$

- $\operatorname{Footprint}(b,t)$ = 2D region corresponding to the bowl's actual supporting base projected onto the plate.
- $\operatorname{UsableSurface}(p,t)$ = usable plate support polygon (not necessarily the full visual silhouette).
- $\operatorname{Erode}(A,m)$ = region obtained by shrinking set $A$ inward by margin $m$.
- $\subseteq$ = set containment: **the entire foot** is inside the valid support area.

For true static stability, footprint containment and contact alone may be insufficient. The gravity line through the center of mass should fall inside the **effective support polygon**, and the contact forces/friction must support equilibrium. A simple center-distance check is therefore a **proxy**, not a general proof of stability.

### 8.3 Surface-height condition

$$
\operatorname{AtHeight}(b,p,t):=
\left[\left|z_b^{\rm bottom}(t)-z_p^{\rm surface}(t)\right|
\le\epsilon_z\right].
$$

- $|\cdot|$ = absolute value.
- $\epsilon_z$ = permitted difference in vertical height; example $0.005\,\mathrm m$ (5 mm).

Contact geometry and height conventions must agree. A deep or curved plate may require a local surface function $z_p^{\rm surface}(u,v)$ rather than one constant height.

### 8.4 Bowl velocity and release

$$
\operatorname{Stable}(b,t):=
 [\|v_b(t)\|_2\le v_{\max}]
 \land[\|\omega_b(t)\|_2\le\omega_{\max}].
$$

$$
\operatorname{Released}(b,t):=
 \neg\operatorname{Holding}(r,b,t).
$$

- $v_{\max}$ = maximum permitted linear speed, in m/s.
- $\omega_{\max}$ = maximum permitted angular speed, in rad/s.
- $\|\cdot\|_2$ = Euclidean vector norm.

Monitoring these conditions over a 2-second window offers an **operational settling test**. It is not a mathematical guarantee that the bowl will never fall later.

### 8.5 Complete terminal placement predicate

$$
\boxed{\begin{aligned}
\operatorname{Placed}(b,p,t):={}&
\operatorname{Inside}(b,p,t)\\
&\land\operatorname{AtHeight}(b,p,t)\\
&\land\operatorname{Contact}(b,p,t)\\
&\land\operatorname{Stable}(b,t)\\
&\land\operatorname{Released}(b,t).
\end{aligned}}
$$

It is evaluated at one time instant $t$. Temporal logic then requires it to hold for a duration.

### 8.6 A robust definition of Grasp

Possible simulator-grounded definition:

$$
\operatorname{Grasp}(b,t):=
\operatorname{GripperContact}(b,t)
\land\operatorname{GraspConstraintActive}(b,t)
\land\neg\operatorname{GripperOpen}(t).
$$

This is a **suggested implementation contract**, not a statement that LIBERO exposes these exact API names. Some simulators implement grasp without an explicit attachment/constraint signal; in that case, require suitable opposing contacts, relative motion consistency, or a proven grasp-state estimator. Mere proximity is **not enough**.

### 8.7 A scene-specific safety predicate

The most useful safety constraint is defined **relative to allowed task contacts**:

$$
\operatorname{Safe}(t):=
\operatorname{NoForbiddenContact}(t)
\land\operatorname{JointLimitsOK}(t)
\land\operatorname{ForceLimitsOK}(t).
$$

Possible refinements include clearances to a ramekin, avoiding table-edge crossings, and avoiding excessive contact forces. Crucially, **bowl-plate contact is required** and gripper-bowl contact is necessary during grasping. A global `NoCollision` rule would make the task contradictory.

### 8.8 Resolve “between the plate and the ramekin” at time 0

Let $a$ and $c$ be the plate and ramekin centers, and $q$ a candidate black-bowl center, all in the initial tabletop frame.

$$
\lambda=\frac{(q-c)^\top(a-c)}{\|a-c\|_2^2},\qquad
q_{\rm proj}=c+\lambda(a-c),\qquad
 d_\perp=\|q-q_{\rm proj}\|_2.
$$

An approximate “between” predicate is:

$$
\operatorname{Between}(q,a,c):=
  [0<\lambda<1]\land[d_\perp\le\delta],
$$

where $\delta$ is the tolerated lateral deviation. Assume $\|a-c\|>0$.

This predicate is primarily **for initial object identification**. Do not force it to remain true while the bowl moves away. If several bowls satisfy the geometric relation, require stronger disambiguation.

## 9. Quantitative robustness: not just true or false

A Boolean monitor returns `satisfied` or `violated`. **STL robustness** assigns a real-valued score $\rho(x,\phi,t)$:

- $\rho>0$: specification satisfied with positive numerical margin (for the usual sign convention).
- $\rho<0$: specification violated.
- $\rho=0$: on the boundary; strict/non-strict predicates and numerical conventions matter.

For an inequality $h(x(t))\ge0$, use

$$
\rho(x,\mu_h,t)=h(x(t)).
$$

For the plate region:

$$
\boxed{\rho_{\rm inside}(t)=(R_p-r_b-m)-d_{xy}(t).}
$$

With $d_{\rm allowed}=0.05\,\mathrm m$:

| Distance $d_{xy}$ | Robustness $\rho_{\rm inside}$ | Interpretation |
|---|---|---|
| 0.02 m | +0.03 m | 3 cm inside the permitted center region |
| 0.05 m | 0 m | Right at threshold |
| 0.07 m | -0.02 m | 2 cm beyond the permitted center region |

### 9.1 Robustness of Boolean operators

$$
\begin{aligned}
\rho(x,\neg\phi,t)&=-\rho(x,\phi,t),\\
\rho(x,\phi\land\psi,t)&=\min\{\rho(x,\phi,t),\rho(x,\psi,t)\},\\
\rho(x,\phi\lor\psi,t)&=\max\{\rho(x,\phi,t),\rho(x,\psi,t)\}.
\end{aligned}
$$

A conjunction has the robustness of its **weakest** requirement; a disjunction takes the **best** branch.

### 9.2 Robustness of temporal operators

$$
\boxed{\rho(x,\mathbf F_{[a,b]}\phi,t)=
\sup_{s\in[t+a,t+b]}\rho(x,\phi,s)}
$$

$$
\boxed{\rho(x,\mathbf G_{[a,b]}\phi,t)=
\inf_{s\in[t+a,t+b]}\rho(x,\phi,s)}
$$

- $\sup$ = supremum, similar to a maximum over a continuous interval.
- $\inf$ = infimum, similar to a minimum over a continuous interval.
- For a finite sampled trace, replace them with `max` and `min` over the relevant samples.

For until:

$$
\rho(x,\phi\;\mathbf U_{[a,b]}\;\psi,t)=
\sup_{s\in[t+a,t+b]}
\min\left(
\rho(x,\psi,s),\inf_{u\in[t,s)}\rho(x,\phi,u)
\right),
$$

using the convention $\inf\emptyset=+\infty$ for an empty prefix. Some sources include the endpoint $s$ inside the prefix; implement the convention consistently with the chosen library and formula.

### 9.3 Robustness of the *full* task formula

For conciseness write

$$
\begin{aligned}
 g(t)&=\rho(x,\operatorname{Grasp}(b),t),\\
 p(t)&=\rho(x,\operatorname{Placed}(b,p),t),\\
 s(t)&=\rho(x,\operatorname{Safe},t).
\end{aligned}
$$

Then the full example has robustness

$$
\boxed{\begin{aligned}
\rho(x,\varphi,0)=\min\Bigg\{&
\sup_{t_g\in[0,10]}
\min\left[
 g(t_g),
 \sup_{t_p\in[t_g,t_g+18]}
 \inf_{u\in[t_p,t_p+2]}p(u)
\right],\\
&\inf_{v\in[0,30]}s(v)
\Bigg\}.
\end{aligned}}
$$

This is a direct mathematical decomposition of the example. It gives a concrete dynamic-programming / temporal-monitoring target.

**Dimensional caution:** Combining raw spatial margins in **metres**, velocity margins in **m/s**, angular margins in **rad/s**, and ad hoc Boolean scores with `min` is mathematically allowed only after a numerical encoding choice; the resulting magnitude is **not automatically a physical distance**. For cross-predicate comparison, normalize each margin by a meaningful scale and explicitly document the convention. An arbitrary robustness score is not a calibrated probability of success.

## 10. Step-by-step positive and negative examples

| Case | Grasp $t_g$ | Selected placement starts $t_p$ | Placed holds continuously | Safe on $[0,30]$? | Result |
|---|---:|---:|---|---|---|
| A | 7 s | 20 s | 20–22 s | Yes | **Pass** |
| B | 11 s | 16 s | 16–18 s | Yes | **Fail** (no eligible grasp in first 10 s) |
| C | 7 s | 26 s | 26–28 s | Yes | **Fail for this witness** ($26>7+18$); could still pass if another eligible grasp time exists |
| D | 7 s | 20 s | 20–21 s only | Yes | **Fail** (no full 2-second hold, assuming no later valid interval) |
| E | 7 s | 20 s | 20–22 s | No: unsafe event at 9 s | **Fail** |
| F | 10 s | 28 s | 28–30 s | Yes | **Pass** (right at closed bounds) |

**Illustrative robustness:** If placement's minimum normalized margin over $[20,22]$ is $0.15$, the grasp margin is $0.70$, and the minimum safety margin over the episode is $0.08$, then the selected branch has task robustness $\min(0.70,0.15)=0.15$ and full robustness $\min(0.15,0.08)=0.08$, provided no other grasp/placement choice gives a higher result. (These are synthetic, dimensionless numbers.)

## 11. Stronger and alternative STL formulations

### 11.1 Simplest success-only requirement

$$
\varphi_1=\mathbf F_{[0,28]}\mathbf G_{[0,2]}\operatorname{Placed}(b,p).
$$

This requires a 2-second successful placement window by 30 seconds; it does **not** explicitly require detecting a prior grasp or enforce safety.

### 11.2 Task success plus continuous safety

$$
\varphi_2=\mathbf F_{[0,28]}\mathbf G_{[0,2]}\operatorname{Placed}(b,p)
\land\mathbf G_{[0,30]}\operatorname{Safe}.
$$

A useful simpler baseline for comparing verifiers.

### 11.3 Explicit grasp-before-placement with relative deadline

$$
\varphi_3=\mathbf F_{[0,10]}\left(
\operatorname{Grasp}(b)\land
\mathbf F_{[0,18]}\mathbf G_{[0,2]}\operatorname{Placed}(b,p)
\right)\land\mathbf G_{[0,30]}\operatorname{Safe}.
$$

This is the original running example.

### 11.4 Require target grounding in the initial state

$$
\varphi_4=
\operatorname{BlackBowl}(b,0)
\land\operatorname{Between}(b,p,r,0)
\land\varphi_3,
$$

where $r$ is the ramekin. This is only appropriate if the scene metadata and initial grounding support those claims.

### 11.5 Require a final end-state condition

If success must persist **through episode end**, add

$$
\varphi_{\rm final}=\varphi_3\land\mathbf G_{[28,30]}\operatorname{Placed}(b,p).
$$

This still does not require continuous placement from the *first* achievement time through the end. To express that stronger causal condition one can use an appropriately defined event predicate (e.g. `FinalRelease`) and temporal operators with a carefully chosen horizon or monitor state.

### 11.6 A reactive safety property

$$
\varphi_{\rm clear}=\mathbf G_{[0,30]}
\left(\operatorname{ApproachingObstacle}\rightarrow
\operatorname{SpeedBelowLimit}\right).
$$

This says that *whenever* the approach condition holds, speed must already be below a threshold. It differs from “slow down eventually after approaching,” which needs nested $\mathbf F$.

### 11.7 “Until” as a distinct pattern

$$
\operatorname{MaintainClearance}
\;\mathbf U_{[0,12]}\;
\operatorname{Grasp}(b).
$$

Clearance must hold from the evaluation time up until a successful grasp within 12 seconds. The exact clearance predicate must allow intended contact with the **target** bowl; otherwise the spec may be impossible.

## 12. Uncertainty and selection of thresholds

A true-geometry margin can be improved by accounting for imperfect state estimation.

Let $\hat c_b,\hat c_p$ be estimated centers, and $\hat d=\|\hat c_b-\hat c_p\|$. Define:

$$
 m=m_{\rm physical}+m_{\rm uncertainty}.
$$

One simple **heuristic** is

$$
 m_{\rm uncertainty}=k\sigma_{\rm relative},
$$

where $\sigma_{\rm relative}$ is a characteristic relative-position uncertainty and $k$ controls conservatism. Do **not** present this alone as a formally established probability guarantee.

A more principled formulation under a justified error bound $\|e_{\rm relative}\|\le\epsilon$ is

$$
 \hat d+\epsilon\le R_p-r_b-m_{\rm physical}.
$$

By the triangle inequality, this is sufficient for the **true** center distance to satisfy the geometric limit. If the error is random, a chance constraint such as

$$
\Pr\big(d_{xy}\le R_p-r_b-m_{\rm physical}\big)\ge1-\alpha
$$

requires an explicit distribution or calibrated probabilistic bound.

| Parameter | What it controls | Good source of its value |
|---|---|---|
| $R_p$ | Usable plate support radius | Collision mesh / fitted surface polygon |
| $r_b$ | Bowl support-foot radius | Collision geometry and orientation |
| $m_{\rm physical}$ | Clearance to unstable support boundary | Object geometry + grasp/placement stability experiments |
| $\epsilon_z$ | Vertical surface fit | Collision tolerance / sensor resolution |
| $v_{\max},\omega_{\max}$ | Settled-motion threshold | Physical dynamics and repeated rollout data |
| $[0,10]$ | Latest eligible grasp time | Horizon budget or experimental specification |
| $[0,18]$ | Relative post-grasp task deadline | Feasible reach/motion times, controller bandwidth, policy budget |
| $[0,2]$ | Continuous confirmation time | Settling-time analysis and evaluation protocol |
| $\operatorname{Safe}$ | Forbidden and permitted events | Task hazards, scene configuration, robot limits |

An attractive research output is a **parameterized STL template**, often related to *parametric STL* (PSTL):

$$
\varphi_\theta,\quad
\theta=(T_g,T_{gp},T_s,m,\epsilon_z,v_{\max},\dots).
$$

The task is then to infer $\theta$ from language, geometry, dynamics, and uncertainty without introducing impossible or semantically unjustified constraints.

## 13. Continuous vs. discrete time, sampling, and monitoring horizon

### Continuous vs. discrete time

- **Continuous time:** $t\in\mathbb R_{\ge0}$; $\mathbf G$ truly means *every instant* in the interval.
- **Discrete time:** $t_k=k\Delta t$; the sample monitor checks all **observed samples** in the interval.

A discrete-time monitor does not automatically prove what happened **between samples**. High-speed collisions or brief instability could be missed. Higher sampling frequency, bounded system dynamics, conservative interpolation, or a validated continuous-time method may be required.

### Sampling conversion example

At $\Delta t=0.1\,\mathrm s$ (10 Hz), with aligned endpoints:

$$
\begin{aligned}
[0,10]\,\mathrm s &\longleftrightarrow 0\dots100\ \text{sample offsets},\\
[0,18]\,\mathrm s &\longleftrightarrow 0\dots180,\\
[0,2]\,\mathrm s &\longleftrightarrow 0\dots20,\\
[0,30]\,\mathrm s &\longleftrightarrow 0\dots300.
\end{aligned}
$$

Because these are **closed intervals**, a 2-second hold at 10 Hz comprises 21 sampled instants (0, 0.1, …, 2.0), not 20.

### Future horizon / temporal depth

A recursive upper-bound horizon calculation (for future-only bounded STL) is:

$$
\begin{aligned}
H(\mu)&=0,\\
H(\neg\phi)&=H(\phi),\\
H(\phi\land\psi)&=\max(H(\phi),H(\psi)),\\
H(\mathbf F_{[a,b]}\phi)&=b+H(\phi),\\
H(\mathbf G_{[a,b]}\phi)&=b+H(\phi).
\end{aligned}
$$

The example's task horizon is $10+18+2=30$ seconds, and the safety horizon is $30$ seconds. Thus a **complete** offline evaluation starting at 0 needs data through $t=30$.

**Online interpretation:** A future-time formula cannot generally be fully determined until enough data has arrived. A sound online monitor may report **pending / inconclusive** until it has observed the required horizon (although some violations or satisfactions can sometimes be established early).

**Early episode termination:** If a LIBERO episode ends at 23 seconds, it is incorrect to silently interpret an unevaluated $\mathbf G_{[0,30]}$ as satisfied. Choose and document one protocol: extend observation to 30 seconds, evaluate a deliberately shortened horizon, or return **inconclusive** for requirements needing missing data.

## 14. A working NumPy monitor for the exact sample formula

This example checks the **sampled Boolean interpretation** of the exact nested formula. It expects precomputed Boolean signals from your LIBERO / MuJoCo state extraction. It does **not** infer contact or pose from images.

```python
import numpy as np


def verify_bowl_stl(grasp, placed, safe, dt=0.1):
    """Check at t=0:

      F[0,10] (Grasp AND F[0,18] G[0,2] Placed)
      AND G[0,30] Safe.

    All input arrays must be sampled at times 0, dt, 2*dt, ...
    with an inclusive sample at t=30. This is *sampled* STL, not
    a guarantee over unobserved continuous time.
    """
    grasp = np.asarray(grasp, dtype=bool)
    placed = np.asarray(placed, dtype=bool)
    safe = np.asarray(safe, dtype=bool)

    # All timing bounds must align exactly to the sample grid.
    def samples(seconds):
        n = int(round(seconds / dt))
        if not np.isclose(n * dt, seconds):
            raise ValueError("Time bound is not aligned to dt")
        return n

    latest_grasp = samples(10.0)
    post_grasp_window = samples(18.0)
    holding_window = samples(2.0)
    horizon = samples(30.0)

    if min(len(grasp), len(placed), len(safe)) < horizon + 1:
        raise ValueError("Need complete observations through t=30 s")

    # G[0,30] Safe: safe at EVERY sample 0..300.
    safety_pass = bool(np.all(safe[:horizon + 1]))

    task_pass = False
    witness = None

    # F[0,10]: find an eligible grasp witness j.
    for j in range(latest_grasp + 1):
        if not grasp[j]:
            continue

        # F[0,18] from that grasp time: find placement witness k.
        last_start = min(j + post_grasp_window,
                         horizon - holding_window)
        for k in range(j, last_start + 1):
            # G[0,2]: placed at every sample k..k+20.
            if np.all(placed[k:k + holding_window + 1]):
                task_pass = True
                witness = {
                    "grasp_time_s": round(j * dt, 6),
                    "placement_start_s": round(k * dt, 6),
                    "placement_end_s": round((k + holding_window) * dt, 6),
                }
                break
        if task_pass:
            break

    return {
        "satisfied": task_pass and safety_pass,
        "task_pass": task_pass,
        "safety_pass": safety_pass,
        "witness": witness,
    }


if __name__ == "__main__":
    dt = 0.1
    time = np.arange(301) * dt
    grasp = np.zeros(len(time), dtype=bool)
    placed = np.zeros(len(time), dtype=bool)
    safe = np.ones(len(time), dtype=bool)

    grasp[70:73] = True         # 7.0--7.2 seconds
    placed[200:231] = True     # 20.0--23.0 seconds

    print(verify_bowl_stl(grasp, placed, safe, dt))
    # Expected: satisfied=True, grasp_time_s=7.0,
    # placement_start_s=20.0, placement_end_s=22.0

    safe[90] = False            # unsafe event at t=9.0 s
    print(verify_bowl_stl(grasp, placed, safe, dt))
    # Expected: task_pass=True, safety_pass=False,
    # satisfied=False
```

**Implementation note:** This is a brute-force existence check, suitable for unit tests and demonstrations. For long trajectories, nested formulas, complex real-valued robustness, or true online monitoring, use a dedicated STL monitor rather than hand-maintaining nested loops.

### From MuJoCo state to input arrays

On each simulation step:

```python
# Conceptual integration sketch -- these are adapter function names,
# not actual LIBERO APIs.
state = extract_ground_truth_state(env)
gr = target_bowl_is_grasped(state)
pl = target_bowl_is_placed(state)     # geometry + contact + stability + release
sf = scene_safety_predicate(state)

log_time.append(state.time)
log_grasp.append(gr)
log_placed.append(pl)
log_safe.append(sf)
```

Use timestamps from the **simulator clock**, not inference wall-clock time, and match the logging cadence to the monitor's assumed sampling interval.

## 15. Using an STL library (RTAMT)

**RTAMT** supports robust online and offline STL monitoring. Official source and syntax documentation:

- https://github.com/nickovic/rtamt
- https://pypi.org/project/rtamt/

Example using dimensionless **signed margins** as inputs rather than Boolean flags (check your installed library's exact API and time-unit settings):

```python
import rtamt

spec = rtamt.StlDiscreteTimeSpecification()
spec.declare_var('grasp_margin', 'float')
spec.declare_var('placed_margin', 'float')
spec.declare_var('safe_margin', 'float')
spec.set_sampling_period(100, 'ms', 0.1)
spec.unit = 's'

spec.spec = (
    'eventually[0:10] ('
    '  (grasp_margin >= 0) and '
    '  eventually[0:18] (always[0:2] (placed_margin >= 0))'
    ') and always[0:30] (safe_margin >= 0)'
)
spec.parse()

# Then feed time-stamped samples with the supported monitor API,
# or use the appropriate offline evaluation method.
```

**Important:** The `grasp_margin`, `placed_margin`, and `safe_margin` signals must be **computed before** passing them to the STL monitor. RTAMT cannot infer an object's support polygon, valid contact pairs, or which black bowl was intended from the STL string alone.

RTAMT's API and supported modes can evolve; the full official example in its README is the source of truth. Some modes handle bounded-future formulas with **monitoring delay**; instantaneous output at time $t$ need not already report the final result of a property that references future times.

## 16. LIBERO / MuJoCo / π0.5 evaluation pipeline

A clean experimental pipeline:

```text
Natural-language instruction
  "Pick up the black bowl between the plate and the ramekin
   and place it on the plate"
           |
           v
Scene grounding + task semantics
  - bowl identity b (target, not distractor)
  - support object p (plate)
  - initial spatial relation between bowl, plate, ramekin
           |
           v
Predicate synthesis / parameter estimation
  - Inside(b,p) with geometry-derived margin
  - Contact(b,p), AtHeight(b,p)
  - Stable(b), Released(b), Grasp(b)
  - Safe (task-relevant hazards only)
           |
           v
STL synthesis
  - select sequence structure F(Grasp AND F G Placed)
  - choose temporal bounds and justify their provenance
           |
           v
LIBERO rollout with π0.5
  - π0.5 consumes usual policy observations + NL instruction
  - simulator separately logs privileged poses/contact/velocities
           |
           v
Independent STL monitor
  - Boolean satisfied / violated / incomplete
  - optional quantitative robustness score
  - witness times + violation locations
           |
           v
Compare against LIBERO's native task-success check
  - Where do the two notions of success disagree and why?
```

Recommended per-episode record:

| Logged field | Why |
|---|---|
| Task ID, BDDL/task file identifier, object IDs | Reproducible grounding and comparison |
| Full NL instruction | Test semantic preservation |
| Episode seed, initial state, simulator timestep | Reproducibility |
| All poses, orientations, velocities | Evaluate geometric and dynamic predicates |
| Contact pair IDs + normal/contact force if available | Verify physically meaningful contact and safety |
| Gripper state and grasp result | Verify pickup and release |
| Each atomic predicate and signed margin at every timestamp | Debug synthesized specifications |
| STL formula, thresholds, units, data provenance | Avoid untraceable hard-coded constants |
| Task satisfaction, safety satisfaction, STL robustness | Separate task success from safety |
| LIBERO native success Boolean | Quantify agreement and disagreement |

**Baseline experiment design:**

1. **Native LIBERO criterion:** official task success signal.
2. **Geometry-only criterion:** bowl base inside usable plate region.
3. **Physical placement criterion:** geometry + contact + release + stability.
4. **Full STL criterion:** physical placement + sequence + temporal bounds + safety.
5. **Uncertainty-aware STL criterion:** full criterion with justified uncertainty margins.

This isolates how much each formalization choice changes measured success. A synthesized specification should not be assumed “better” merely because it is stricter: unnecessary conditions may reject behavior that genuinely satisfies the user's instruction.

## 17. Common errors and research limitations

1. **Confusing $\mathbf F$ and $\mathbf G$.** “Eventually placed” is not “stays placed for 2 seconds.”
2. **Treating nested time intervals as absolute.** An inner $\mathbf F_{[0,18]}$ starts at its parent's chosen evaluation time.
3. **Using only center distance.** XY proximity does not establish actual support, contact, non-overhang, stability, or release.
4. **Confusing object body center with support-foot center.** For asymmetrical geometry the distinction can be large.
5. **Defining `Safe` too broadly.** Not all contact is unsafe in manipulation; some contacts are essential.
6. **Using a generic `Holding` signal for multiple bowls.** Make target identity explicit, including during tracking and grasp verification.
7. **Claiming continuous-time proof from sparse sampled data.** A transient violation can occur between samples.
8. **Using arbitrary numerical margins as probabilities.** Quantitative robustness is a signed score, not necessarily a calibrated likelihood.
9. **Ignoring incomplete traces.** If the formula horizon exceeds available data, return incomplete or use a documented finite-trace convention.
10. **Overfitting thresholds to native LIBERO success.** A physically meaningful constraint should be validated independently; otherwise the STL formulation simply mimics the benchmark.
11. **Requiring an arbitrary grasp action when only the terminal state is semantically necessary.** Some success definitions are intentionally agnostic to how placement was achieved. Distinguish task semantics from extra procedural constraints.
12. **Inventing timing or physical parameters.** Every threshold requires an origin and validation procedure.
13. **Forgetting hardware differences.** A simulator contact predicate may not translate to a deployed robot without tactile sensing or reliable state estimation.
14. **Equating “verified trajectory” with “verified system.”** Checking one observed rollout does not prove that all rollouts of a stochastic π0.5 policy are safe.

### What STL verification actually guarantees

Given a **trusted signal**, **correct predicate implementations**, a **specific formula**, and a **sound monitor** for the selected time semantics, a completed monitor can determine whether the **observed execution** satisfied that specification. It does *not* by itself prove that the user instruction was understood correctly, that the scene geometry is accurate, that estimated states have bounded error, or that future trajectories will also satisfy the formula.

## 18. Notation glossary

| Symbol | Name | Meaning / units |
|---|---|---|
| STL | Signal Temporal Logic | Temporal logic over measured signals |
| $x(t)$ | System signal / state | Real-valued state at time $t$ |
| $t$ | Time | Seconds unless noted |
| $T$ | End time / trace length | Seconds |
| $\Delta t$ | Sampling interval | Seconds / sample |
| $\tau$ | Execution trajectory | Ordered time-state samples |
| $\mu$ | Atomic proposition | Basic truth-valued predicate |
| $h(x)$ | Predicate function | Real-valued expression; often $\mu=[h\ge0]$ |
| $\phi,\psi,\varphi$ | STL formulas | Boolean/temporal properties |
| $\top,\bot$ | True, false | Logical constants |
| $\neg$ | NOT | Negation |
| $\land$ | AND | Conjunction |
| $\lor$ | OR | Disjunction |
| $\rightarrow$ | IMPLIES | Material implication |
| $\mathbf F_I,\Diamond_I$ | Eventually | True at least once in future interval $I$ |
| $\mathbf G_I,\Box_I$ | Always | True throughout interval $I$ |
| $\mathbf U_I$ | Until | First property holds until second happens within $I$ |
| $I=[a,b]$ | Relative time interval | Start and end offsets in seconds |
| $\exists$ | Exists | At least one witness |
| $\forall$ | For all | Every point in set/interval |
| $\models$ | Satisfaction relation | “Trajectory at time satisfies formula” |
| $\not\models$ | Non-satisfaction | Formula is not satisfied |
| $\equiv$ | Logical equivalence | Two formulas have same meaning |
| $\rho(x,\phi,t)$ | Robustness | Signed quantitative satisfaction |
| $\min,\max$ | Minimum, maximum | Worst/best sampled value |
| $\inf,\sup$ | Infimum, supremum | Continuous-time analogue of min/max |
| $b$ | Target bowl object | Object identity, not a number |
| $p$ | Plate object | Object identity |
| $r$ | Ramekin object | Object identity |
| $q_b,q_p$ | Object positions | Usually metres |
| $c_b,c_p$ | Support-region/foot centers | Metres, common coordinate frame |
| $d_{xy}$ | Center separation in support plane | Metres |
| $R_p$ | Usable plate radius | Metres |
| $r_b$ | Bowl supporting-foot radius | Metres |
| $m$ | Geometric margin | Metres |
| $z_b^{\rm bottom}$ | Bowl foot height | Metres |
| $z_p^{\rm surface}$ | Plate support height | Metres |
| $\epsilon_z$ | Height tolerance | Metres |
| $v_b$ | Bowl linear velocity | Metres per second |
| $\omega_b$ | Bowl angular velocity | Radians per second |
| $v_{\max}$ | Allowed linear velocity | Metres per second |
| $\omega_{\max}$ | Allowed angular velocity | Radians per second |
| $\|\cdot\|_2$ | Euclidean norm | Length/magnitude of vector |
| $|\cdot|$ | Absolute value | Magnitude of scalar |
| $\subseteq$ | Set inclusion | Whole footprint lies inside valid support region |
| $\lambda$ | Segment projection parameter | Unitless |
| $\delta$ | “Between” lateral tolerance | Metres |
| $\alpha$ | Allowed violation probability | Unitless; only under a probabilistic model |
| $\theta$ | Specification parameters | Collection of time/geometry/safety thresholds |

## 19. Suggested literature and code

1. **Oded Maler and Dejan Nickovic (2004), “Monitoring Temporal Properties of Continuous Signals.”** Foundational STL monitoring paper. DOI: https://doi.org/10.1007/978-3-540-30206-3_12 ; free text: https://citeseerx.ist.psu.edu/document?doi=d7871c349ef0c2f8f22faa44b9f907340a426470&repid=rep1&type=pdf
2. **Alexandre Donzé and Oded Maler (2010), “Robust Satisfaction of Temporal Logic over Real-Valued Signals.”** Classic robustness semantics reference. https://doi.org/10.1007/978-3-642-15297-9_9
3. **Vasumathi Raman et al., “Model Predictive Control with Signal Temporal Logic Specifications.”** Concrete connection between STL and control, including quantitative semantics. https://people.eecs.berkeley.edu/~sseshia/pubdir/hscc15-mpcstl.pdf
4. **RTAMT — STL monitoring code and practical syntax.** https://github.com/nickovic/rtamt
5. **LIBERO — robot learning benchmark source.** https://github.com/Lifelong-Robot-Learning/LIBERO
6. **LIBERO suite mapping (NL strings and task files).** https://github.com/Lifelong-Robot-Learning/LIBERO/blob/master/libero/libero/benchmark/libero_suite_task_map.py
7. **LIBERO BDDL task specifications.** https://github.com/Lifelong-Robot-Learning/LIBERO/tree/master/libero/libero/bddl_files

---

## Final summary

The translation workflow is:

$$
\underbrace{\text{NL + scene + dynamics + uncertainty}}_{\text{semantic and physical information}}
\;\longrightarrow\;
\underbrace{\text{grounded measurable predicates}}_{\text{what is true at each time}}
\;\longrightarrow\;
\underbrace{\varphi_\theta}_{\text{what must happen and when}}
\;\longrightarrow\;
\underbrace{(\text{Boolean satisfaction},\ \rho)}_{\text{trace verification}}.
$$

**Core point:** STL supplies precise **temporal structure**. Geometry, contact mechanics, perception, object tracking, and uncertainty provide the meaning of the **atomic predicates**. The research challenge in NL-to-STL synthesis is designing both parts so the resulting property is physically meaningful, faithful to user intent, and independently verifiable.
