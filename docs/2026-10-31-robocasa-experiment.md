# RoboCasa365 atomic-task STL experiment

2026-10-31 · Status: **full run stopped early on request, after 2 of 54 (prompt, task) pairs** (CloseBlenderLid under `nl` and `stl_nl`, 20 episodes); see [Results](#results). Checks and pilot (steps 1–6) are done. The pilot found three bugs that made π0.5 fail every task and broke seed pairing; all are fixed (see [Bugs found and fixed](#bugs-found-and-fixed)).

**Question:** if π0.5's prompt includes a deadline, a "let go and leave it" rule and a "don't move other objects" rule, does it follow them? This repeats the [LIBERO-spatial run](2026-10-25-libero-experiment.md) on RoboCasa365. All 18 `atomic_seen` tasks run with three prompts: the original instruction, the instruction plus the rules in English, and the rules as a raw STL formula. Every episode is checked against the same STL spec for its task.

Earlier results: in LIBERO-spatial the rules in English didn't change how often they were met (74 vs 72 of 100), and raw STL made it worse (48). Expect the rules to serve mostly as a *check* here, not as steering.

## Tasks

The 18 tasks are RoboCasa's `atomic_seen` group (`robocasa/utils/dataset_registry.py`). Each runs for its own RoboCasa episode limit. The deadline T is 60% of that limit (decision 18). Each task is one of three types:

- **P** (pick-and-place): an object has to end up somewhere.
- **F** (fixture): a door, drawer, rack, head, knob, lever, button or handle has to end up in a state.
- **N** (navigation): the robot base has to reach a spot.

| # | Task | Type | Limit (steps / s) | T (s) | RoboCasa's success check (the goal) | Others `O` |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | CloseBlenderLid | P | 600 / 30 | 18 | `LidOn(lid)` ∧ gripper > 0.15 m from the lid | none |
| 1 | CloseFridge | F | 600 / 30 | 18 | `Closed(fridge)` | 1 item on a fridge shelf, 1–3 counter items |
| 2 | CloseToasterOvenDoor | F | 300 / 15 | 9 | `Closed(toaster oven door)` | none |
| 3 | CoffeeSetupMug | P | 400 / 20 | 12 | `UnderDispenser(mug)` ∧ `GripperFar(mug)` | none |
| 4 | NavigateKitchen | N | 300 / 15 | 9 | `At(target)` | none |
| 5 | OpenCabinet | F | 700 / 35 | 21 | `Open(cabinet)` (every door) | 1 item inside the cabinet, 1–3 counter items |
| 6 | OpenDrawer | F | 500 / 25 | 15 | `Open(drawer)` | 1 utensil inside the drawer (measured in the drawer's frame), 1–3 counter items |
| 7 | OpenStandMixerHead | F | 300 / 15 | 9 | `Open(mixer head)` | none |
| 8 | PickPlaceCounterToCabinet | P | 500 / 25 | 15 | `InCabinet(o)` ∧ `GripperFar(o)` | 1 counter item, 1 item already inside the target cabinet |
| 9 | PickPlaceCounterToStove | P | 400 / 20 | 12 | `InPan(o)` ∧ `GripperFar(o)` | none (the pan is the target receptacle, the plate the food starts on is the source container) |
| 10 | PickPlaceDrawerToCounter | P | 500 / 25 | 15 | `OnCounter(o)` ∧ `GripperFar(o)` | 1 counter item |
| 11 | PickPlaceSinkToCounter | P | 600 / 30 | 18 | `OnPlate(o)` ∧ plate touches the counter ∧ `GripperFar(o)` | 1 counter item (the plate is the target receptacle) |
| 12 | PickPlaceToasterToCounter | P | 400 / 20 | 12 | `OnPlate(o)` ∧ `GripperFar(o)` | none (the plate is the target receptacle) |
| 13 | SlideDishwasherRack | F | 300 / 15 | 9 | `SlidOut(rack)` or `SlidIn(rack)`, chosen at random per seed | none |
| 14 | TurnOffStove | F | 500 / 25 | 15 | `Off(burner)` | the pot or pan on a burner |
| 15 | TurnOnElectricKettle | F | 300 / 15 | 9 | `On(kettle)` | none |
| 16 | TurnOnMicrowave | F | 300 / 15 | 9 | `On(microwave)` ∧ gripper > 0.15 m from the start button | the item on the turntable (and its plate, if one is sampled) |
| 17 | TurnOnSinkFaucet | F | 400 / 20 | 12 | `On(faucet)` | 1–3 counter items, 1 item in the sink |

`O` is every free object in the scene except the target object, the target receptacle and the source container (decision 21). 9 tasks have no other objects. Their prompts still say "do not move any other object", and the clause is always true for them.

## Spec

The same shape applies to all 18 tasks:

$$
\varphi = \mathbf F_{[0,T]}\,\mathbf G\,\mathrm{Rest}
\ \land\ \bigwedge_{o\in O}\mathbf G\,\neg\mathrm{Disturbed}(o)
$$

In words:

- By T seconds the task is done and at rest, and it stays that way until the end of the episode. `G` without a window means "from then until the end".
- During the whole episode, no other object is moved more than 2 cm or rotated more than 10°.

There is no "not placed until grasped" part (decision 20): sliding or pushing the object into place counts. `Rest` depends on the task type:

| Type | `Rest` = | Meaning |
| --- | --- | --- |
| P | `Success` ∧ `Still(o)` | RoboCasa's own success check holds, which already needs the gripper > 0.25 m away (0.15 m for the blender lid), and the object is still |
| F | `Success` ∧ `Released(part)` ∧ `PartStill(part)` | RoboCasa's success holds, no gripper part touches the moving part, and the part's joint is still. RoboCasa doesn't require letting go for these tasks, except the microwave |
| N | `Success` ∧ `BaseStopped` | the base is at the target pose and has stopped |

Every `Rest` implies task success at that step, so every "deadline met" is a task success and every Full STL pass is a clean success.

## Predicates

**Goal checks.** These are RoboCasa's own, called through each task's `_check_success()` and recorded every step. Paths are relative to `robocasa_ws/third_party/robocasa/robocasa/`.

| Predicate | True when | Source | Task |
| --- | --- | --- | --- |
| `LidOn(lid)` | the lid is < 0.04 m from its closed pose on the blender, with roll and pitch < 7° | `Blender.get_state()["lid_on_blender"]` (`models/fixtures/blender.py:36`) | CloseBlenderLid |
| `InCabinet(o)` | all 8 corners of `o`'s bounding box are inside the cabinet's interior, with 0.05 m slack | `OU.obj_inside_of` (`utils/object_utils.py:14`) | PickPlaceCounterToCabinet |
| `InPan(o)` | `o` touches the pan, and their centers are < 0.07 m apart in xy. The pan doesn't have to stay on the stove | `OU.check_obj_in_receptacle(th=0.07)` (`utils/object_utils.py:587`) | PickPlaceCounterToStove |
| `OnCounter(o)` | `o` touches any counter (not only the one next to the drawer). No upright check | `OU.check_obj_any_counter_contact` (`utils/object_utils.py:632`) | PickPlaceDrawerToCounter |
| `OnPlate(o)` | `o` touches the plate, and their centers are < 0.7 × the plate's xy radius apart. In SinkToCounter the plate must also touch the counter next to the sink | `OU.check_obj_in_receptacle` | PickPlaceSinkToCounter, PickPlaceToasterToCounter |
| `UnderDispenser(mug)` | the mug's center is < 0.04 m (xy) and < 0.10 m (height) from the machine's `receptacle_place_site`. No contact or upright check, so a tipped mug counts | `CoffeeMachine.check_receptacle_placement_for_pouring` (`models/fixtures/coffee_machine.py:95`) | CoffeeSetupMug |
| `GripperFar(o)` | the grip site is > 0.25 m from `o`'s center (blender lid: > 0.15 m) | `OU.gripper_obj_far` (`utils/object_utils.py:645`), `OU.gripper_fxtr_far` (`:655`) | part of RoboCasa's success in all P tasks |
| `Closed(fridge)` | every fridge door joint is ≤ 0.5% of its range (about 0.45°). French-door fridges need both doors closed | `Fridge.is_closed` (`models/fixtures/fridge.py:214`) | CloseFridge |
| `Closed(toaster oven door)` | the door joint is ≤ 0.5% of its range. RoboCasa snaps it shut once it is below 1% | `Fixture.is_closed` (`models/fixtures/fixture.py:723`); snap in `toaster_oven.py:233` | CloseToasterOvenDoor |
| `Open(cabinet)` | every door hinge is ≥ 90% of its range (≥ 81°). A double cabinet needs both doors | `Fixture.is_open` (`models/fixtures/fixture.py:712`) | OpenCabinet |
| `Open(drawer)` | the drawer is pulled out ≥ 0.95 × 0.55 × its depth (about 0.31 m for a 0.6 m drawer) | `Drawer.get_door_state` (`models/fixtures/cabinets.py:1061`) | OpenDrawer |
| `SlidOut(rack)` / `SlidIn(rack)` | the top rack's joint is ≥ 95% / ≤ 5% of its range. "Out" starts at 50%, "in" at 100% | `Dishwasher.get_state()["rack"]` (`models/fixtures/dishwasher.py:54`) | SlideDishwasherRack |
| `Open(mixer head)` | the head joint is > 99% of its range (> 1.555 rad) | `StandMixer.get_state()["head"]` (`models/fixtures/stand_mixer.py:75`) | OpenStandMixerHead |
| `Off(burner)` | the target knob's angle (mod 2π) is < 0.35 rad or > 2π − 0.35. It is recomputed every step, so the burner can be turned back on | `Stove.is_burner_on` (`models/fixtures/stove.py:185`) | TurnOffStove |
| `On(kettle)` | a flag set once the switch reaches 95% of its travel. RoboCasa then holds the lever down for 500 steps, longer than the 300-step episode | `ElectricKettle.get_state()["turned_on"]` (`models/fixtures/electric_kettle.py:158`) | TurnOnElectricKettle |
| `On(microwave)` | a flag set when a gripper part touches the start button while the door is closed, and cleared by the stop button or by opening the door. The arm touching the button doesn't count | `Microwave.update_state` (`models/fixtures/microwave.py:66`); distance check `gripper_button_far` (`:92`) | TurnOnMicrowave |
| `On(faucet)` | the handle angle (mod 2π) is between 0.40 rad and π. It is recomputed every step | `Sink.get_handle_state` (`models/fixtures/sink.py:142`) | TurnOnSinkFaucet |
| `At(target)` | the robot base is within 0.20 m (xy) of the pose in front of the target fixture, with heading within 11.5° (cos ≥ 0.98) | `NavigateKitchen._check_success` (`environments/kitchen/atomic/kitchen_navigate.py:124`) | NavigateKitchen |

**Added monitors** (RoboCasa has no equivalent). The thresholds are starting values (decision 25), tuned in the idle check and the pilot. Everything is recorded, so they can change later without rerunning the robot.

| Predicate | True when | Notes |
| --- | --- | --- |
| `Still(o)` | `o`'s speed < 0.01 m/s and spin < 0.25 rad/s | From the simulator's body velocities. Spin is 0.25 rather than LIBERO's 0.1: in LIBERO, 0.1 flagged exactly 2 single rocking glitches, and 0.25 passed exactly those |
| `Released(part)` | no gripper geom (hand, both fingers, both pads) touches any geom of the moving part | The moving part is everything under the goal joint's body: the door, drawer box, rack, head, knob, lever or handle. The fixture's housing doesn't count. For the microwave, `Released` is RoboCasa's own "gripper > 0.15 m from the start button" |
| `PartStill(part)` | every goal joint moves < 0.01 rad/s (hinge, knob) or < 0.01 m/s (slide) | Not used for the microwave, whose button has no joint |
| `BaseStopped` | the base's speed is < 0.02 m/s and it turns < 0.05 rad/s | NavigateKitchen only |
| `Disturbed(o)` | `o`'s center is > 0.02 m from its reference pose, **or** `o` has rotated > 10° about any axis since then. The reference is `o`'s pose once it has settled: the first step from which it is `Still` for 10 steps, but no later than 2 s or the gripper's first touch (decision 27) | Rotation about any axis, unlike LIBERO, which ignored spinning about the vertical because its bowls were round. RoboCasa's objects mostly aren't. The utensil inside the drawer in OpenDrawer is measured in the drawer's frame, so opening the drawer doesn't flag it. Fixtures aren't counted. Measuring from t = 0 instead (`monitor.py --ref t0`) flagged 3 of 180 idle scenes, where a round object was still rolling |

**Diagnostics only.** These go in the CSV and aren't part of φ or any metric:

| Column | Meaning |
| --- | --- |
| `GraspLift(o)` | a gripper geom touches `o`, and `o` is > 0.02 m above its start. Gives the first-grasp time |
| `GraspPads(o)` | both finger pads touch `o` (robosuite `_check_grasp`, `robosuite/environments/manipulation/manipulation_env.py:331`) |
| `pushed_in` (P) | the goal placement was first reached before any `GraspLift`, i.e. slid or pushed in |
| `bumped` (F) | the goal was first reached before any gripper contact with the part, i.e. done by the arm or base |
| `fixture_changed` | another fixture's joint (door, drawer, knob, button, …) moved more than 0.2 rad or 0.2 m from its t = 0 value (decision 28) |
| `disturbed_tilt_only` | LIBERO's `Disturbed`: 2 cm or tilt > 10°, with spin about the vertical ignored |

**Time:** 20 control steps per second. t = 0 is the first policy step, after RoboCasa's 10 settle steps. Windows include both ends. Recordings have one sample per step, from step 0 to the episode limit H.

| Limit H | T | Deadline (landing step ≤) | Rest holds through | Tasks |
| --- | --- | --- | --- | --- |
| 300 (15 s) | 9 s | 180 | step 300 | CloseToasterOvenDoor, NavigateKitchen, OpenStandMixerHead, SlideDishwasherRack, TurnOnElectricKettle, TurnOnMicrowave |
| 400 (20 s) | 12 s | 240 | step 400 | CoffeeSetupMug, PickPlaceCounterToStove, PickPlaceToasterToCounter, TurnOnSinkFaucet |
| 500 (25 s) | 15 s | 300 | step 500 | OpenDrawer, PickPlaceCounterToCabinet, PickPlaceDrawerToCounter, TurnOffStove |
| 600 (30 s) | 18 s | 360 | step 600 | CloseBlenderLid, CloseFridge, PickPlaceSinkToCounter |
| 700 (35 s) | 21 s | 420 | step 700 | OpenCabinet |

No episode stops early on success.

**Checker form** (rtamt, discrete time, one sample per step). `success` is RoboCasa's `_check_success()` at that step. Examples:

```
# P, PickPlaceCounterToCabinet (deadline step 300)
eventually[0:300](always((success > 0.5) and (speed_obj < 0.01) and (spin_obj < 0.25)))
and always((disp_distr_counter < 0.02) and (rot_distr_counter < 10)
       and (disp_distr_cab < 0.02) and (rot_distr_cab < 10))

# F, CloseFridge (deadline step 360); jvel = largest |joint speed| over the goal joints
eventually[0:360](always((success > 0.5) and (gripper_contact_part < 0.5) and (jvel_part < 0.01)))
and always((disp_door_obj < 0.02) and (rot_door_obj < 10) and ...)

# N, NavigateKitchen (deadline step 180); O is empty, so there is no Disturbed part
eventually[0:180](always((success > 0.5) and (base_speed < 0.02) and (base_yaw_rate < 0.05)))
```

As in LIBERO, each verdict is also computed in plain numpy, and the checker flags any episode where the two disagree.

## Prompts

- `nl`: RoboCasa's instruction (`ep_meta["lang"]`), word for word. It changes per episode for most tasks (the object, the drawer side, door vs doors, the burner, the target fixture, rack in or out). The exact prompt is logged for every episode.
- `stl_nl`: `nl` followed by the rule sentences for its type (decision 24):
  - P: ` Finish within {T} seconds, then let go and leave it there until the end. Do not move any other object.`
  - F: ` Finish within {T} seconds, then let go and leave it {state} until the end. Do not move any other object.` `{state}` is closed, open, in, out, off or on; "it" becomes "them" when the instruction says "doors".
  - N: ` Arrive within {T} seconds and stay there until the end. Do not move any other object.`
- `stl`, with times in seconds and ASCII only:
  - P: `F[0,{T}] G resting_{rel}({obj}, {target}) & G !moved(other_objects)`, where `rel` is in, on or under.
  - F: `F[0,{T}] G ({state}({part}) & released({part})) & G !moved(other_objects)`. The microwave uses `released(start_button)`.
  - N: `F[0,{T}] G (at({fixture}) & stopped(robot)) & G !moved(other_objects)`
  - Names are RoboCasa's own words from the instruction, with spaces turned into `_`, e.g. `cream_cheese_stick`. `other_objects` is the set `O`, and the checker tests each object separately.
  - `G !moved(other_objects)` is in every prompt, including the 9 tasks where `O` is empty (decision 21).

The prompts end in a period, so the rules follow as new sentences. In LIBERO, whose instructions have no period, they were appended to the sentence.

π0.5's text input is `Task: {prompt}, State: {16 numbers};\nAction: `, cut at 200 tokens, with `_` replaced by spaces. About 125 tokens are left for the prompt. Truncation cuts the state and the `Action:` suffix without any warning, so a test checks the length of every prompt.

Example prompts for episode 0 (seed 1000, pretrain kitchens). `#` is the row in [Tasks](#tasks).

| # | Task | `nl` (original) | `stl_nl` (original + rules) | `stl` (raw STL) |
| --- | --- | --- | --- | --- |
| 0 | CloseBlenderLid | Close the lid blender by securely placing the lid on top. | Close the lid blender by securely placing the lid on top. Finish within 18 seconds, then let go and leave it there until the end. Do not move any other object. | `F[0,18] G resting_on(lid, blender) & G !moved(other_objects)` |
| 1 | CloseFridge | Close the fridge door. | Close the fridge door. Finish within 18 seconds, then let go and leave it closed until the end. Do not move any other object. | `F[0,18] G (closed(fridge_door) & released(fridge_door)) & G !moved(other_objects)` |
| 2 | CloseToasterOvenDoor | Close the toaster oven door. | Close the toaster oven door. Finish within 9 seconds, then let go and leave it closed until the end. Do not move any other object. | `F[0,9] G (closed(toaster_oven_door) & released(toaster_oven_door)) & G !moved(other_objects)` |
| 3 | CoffeeSetupMug | Pick the mug from the counter and place it under the coffee machine dispenser. | Pick the mug from the counter and place it under the coffee machine dispenser. Finish within 12 seconds, then let go and leave it there until the end. Do not move any other object. | `F[0,12] G resting_under(mug, coffee_dispenser) & G !moved(other_objects)` |
| 4 | NavigateKitchen | Navigate to the fridge. | Navigate to the fridge. Arrive within 9 seconds and stay there until the end. Do not move any other object. | `F[0,9] G (at(fridge) & stopped(robot)) & G !moved(other_objects)` |
| 5 | OpenCabinet | Open the cabinet doors. | Open the cabinet doors. Finish within 21 seconds, then let go and leave them open until the end. Do not move any other object. | `F[0,21] G (open(cabinet_doors) & released(cabinet_doors)) & G !moved(other_objects)` |
| 6 | OpenDrawer | Open the left drawer. | Open the left drawer. Finish within 15 seconds, then let go and leave it open until the end. Do not move any other object. | `F[0,15] G (open(left_drawer) & released(left_drawer)) & G !moved(other_objects)` |
| 7 | OpenStandMixerHead | Open the stand mixer head. | Open the stand mixer head. Finish within 9 seconds, then let go and leave it open until the end. Do not move any other object. | `F[0,9] G (open(stand_mixer_head) & released(stand_mixer_head)) & G !moved(other_objects)` |
| 8 | PickPlaceCounterToCabinet | Pick the tomato from the counter and place it in the cabinet. | Pick the tomato from the counter and place it in the cabinet. Finish within 15 seconds, then let go and leave it there until the end. Do not move any other object. | `F[0,15] G resting_in(tomato, cabinet) & G !moved(other_objects)` |
| 9 | PickPlaceCounterToStove | Pick the egg from the plate and place it in the pan. | Pick the egg from the plate and place it in the pan. Finish within 12 seconds, then let go and leave it there until the end. Do not move any other object. | `F[0,12] G resting_in(egg, pan) & G !moved(other_objects)` |
| 10 | PickPlaceDrawerToCounter | Pick the ladle from the drawer and place it on the counter. | Pick the ladle from the drawer and place it on the counter. Finish within 15 seconds, then let go and leave it there until the end. Do not move any other object. | `F[0,15] G resting_on(ladle, counter) & G !moved(other_objects)` |
| 11 | PickPlaceSinkToCounter | Pick the milk from the sink and place it on the plate located on the counter. | Pick the milk from the sink and place it on the plate located on the counter. Finish within 18 seconds, then let go and leave it there until the end. Do not move any other object. | `F[0,18] G resting_on(milk, plate) & G !moved(other_objects)` |
| 12 | PickPlaceToasterToCounter | Place the toasted item on a plate. | Place the toasted item on a plate. Finish within 12 seconds, then let go and leave it there until the end. Do not move any other object. | `F[0,12] G resting_on(toasted_item, plate) & G !moved(other_objects)` |
| 13 | SlideDishwasherRack | Fully slide the top dishwasher rack in. | Fully slide the top dishwasher rack in. Finish within 9 seconds, then let go and leave it in until the end. Do not move any other object. | `F[0,9] G (slid_in(top_dishwasher_rack) & released(top_dishwasher_rack)) & G !moved(other_objects)` |
| 14 | TurnOffStove | Turn off the front left burner of the stove. | Turn off the front left burner of the stove. Finish within 15 seconds, then let go and leave it off until the end. Do not move any other object. | `F[0,15] G (off(front_left_burner) & released(front_left_burner)) & G !moved(other_objects)` |
| 15 | TurnOnElectricKettle | Press down the lever to turn on the electric kettle. | Press down the lever to turn on the electric kettle. Finish within 9 seconds, then let go and leave it on until the end. Do not move any other object. | `F[0,9] G (on(electric_kettle) & released(electric_kettle)) & G !moved(other_objects)` |
| 16 | TurnOnMicrowave | Press the start button on the microwave. | Press the start button on the microwave. Finish within 9 seconds, then let go and leave it on until the end. Do not move any other object. | `F[0,9] G (on(microwave) & released(start_button)) & G !moved(other_objects)` |
| 17 | TurnOnSinkFaucet | Turn on the sink faucet. | Turn on the sink faucet. Finish within 12 seconds, then let go and leave it on until the end. Do not move any other object. | `F[0,12] G (on(sink_faucet) & released(sink_faucet)) & G !moved(other_objects)` |

## Metrics

The same four metrics as LIBERO (decision 11):

| Metric | Passes when |
| --- | --- |
| **Task success** | RoboCasa's `_check_success()` is true at any step of the episode. This is RoboCasa's standard number, but here it is measured on the pretrain kitchens, not the benchmark's target kitchens (decision 15) |
| **Deadline met** | `F[0,T] G Rest`: done and at rest by T, and still at rest at the last step |
| **Clean success** | task success, and `G ¬Disturbed(o)` over the whole episode for every `o` in `O` |
| **Full STL** | all of φ, i.e. deadline met and no other object disturbed |

The metrics nest: every deadline met is a task success, and every Full STL pass is a clean success, so Full STL = deadline met ∧ clean success. For the 9 tasks with empty `O`, clean success equals task success, and Full STL equals deadline met.

**Tables,** as in the LIBERO doc:

- a summary per prompt, with 95% Wilson ranges (summary only);
- per-task task success, clean success and deadline met / Full STL;
- paired comparisons between prompts by seed (exact McNemar);
- why each deadline failure happened;
- which objects were disturbed.

Per episode the CSV also records:

- first success time, rest start and longest rest;
- first grasp time (both definitions), `pushed_in` and `bumped`;
- largest displacement and rotation of every object in `O`;
- `fixture_changed`;
- the exact prompt.

## Run setup

- **Policy:** π0.5 `lerobot/pi05_robocasa`, `n_action_steps=50` (its default, which LeRobot's RoboCasa docs also use). It re-plans every 2.5 s. Every episode length is a multiple of 50, so with no early stop every episode makes the same number of policy calls under every prompt.
  - `--policy.compile_model=false`. With the checkpoint's default torch.compile, MuJoCo's camera images in the same process come back scrambled after the first frame (found in the pilot).
  - **State and action layout.** The checkpoint was trained on the RoboCasa365 dataset layout, not the one LeRobot 0.6.1's `RoboCasaEnv` uses. `launch_eval.py` converts both (`STL_IO_ORDER=dataset`):
    - state: `ee_pos_rel(3), ee_quat_rel(4), base_pos(3), base_quat(4), gripper(2)` (LeRobot puts the base first);
    - action: `ee_pos(3), ee_rot(3), gripper(1), base_motion(4), control_mode(1)` (LeRobot reads `base_motion, control_mode, ee_pos, ee_rot, gripper`).

    The checkpoint's normalization stats show this: state dims 7–9 have z = 0.70 m with std 0.002 (base position) and dims 10–11 are always 0 (base quaternion x, y); action dims 6 and 11 are ±1 switches (gripper, control mode) and dim 10 is always 0 (torso).
- **Simulator:** RoboCasa365 `56e355cc`, robosuite `aaa8b9b2`.
  - `--env.split=pretrain`: layouts 11–60 × styles 11–60 with the pretrain object instances, chosen because these scenes are familiar to the checkpoint.
  - Object registries `("objaverse", "lightwheel")` (LeRobot's `env.obj_registries`; its default is lightwheel only). This is RoboCasa's upstream default. The objaverse pack (6.2 GB) was downloaded on 2026-10-31 to `robocasa_ws/third_party/robocasa/robocasa/models/assets/objects/objaverse/`.
- **Episodes:** 18 tasks × 10 episodes × 3 prompts = 540. Under every prompt, episode k resets with seed 1000 + k (k = 0–9). The same seed rebuilds the identical scene (see the checks below), so prompts are paired by seed.
- **No early stop:** every episode runs to its task's limit. LeRobot's `RoboCasaEnv.step` sets `terminated = is_success` and then calls `self.reset()` itself, which rebuilds a seed-0 kitchen in the middle of the episode. The patch therefore **replaces** `step` instead of wrapping it: it returns `terminated=False` and keeps `info["is_success"]`. (The LIBERO patch wrapped `step`, which won't work here.)
- **Prompt swap:** a wrapper on `RoboCasaEnv.reset` calls the original, builds the prompt from `get_ep_meta()` (object and fixture names), and sets `task_description`. `lerobot-eval` reads it on every step.
- **Seeds:** one `lerobot-eval` per (prompt, task), with `--seed=1000`, `eval.batch_size=1` and `eval.use_async_envs=false`. Each process starts the torch RNG fresh, so episode k gets the same policy noise under every prompt until the trajectories diverge.
- **Screen:** one driver script runs in the `screen` session `robocasa_stl`, so a disconnect doesn't stop the run.
  - It runs two evals at a time, one per GPU: `nl` and `stl_nl` first, then `stl`.
  - It skips (prompt, task) pairs that are already finished, so a restart picks up where it stopped.
  - Logs go to files.
  - The pilot measures RAM to see whether three fit (62 GB, no swap; the environment alone is about 6.7 GB).
- **Recorded every step:**
  - pose and linear/angular velocity of every free object, including the blender lid;
  - position and velocity of every fixture joint;
  - RoboCasa's success and each of its parts;
  - gripper contact with the target object or part, and finger-pad contacts;
  - grip-site position;
  - base pose and velocity.

  Every reset rebuilds the MuJoCo model, so sim handles are looked up again after each reset.
- **Video:** one mp4 per episode.
- **Code:** a new `robocasa_ws/stl_prompt/` with `launch_eval.py`, `make_specs.py`, `stl_spec.py`, `monitor.py`, `test_monitor.py`, the run script and the screen driver. `libero_ws/stl_prompt/` is not changed, so the LIBERO numbers stay reproducible.
- **Checker:** rtamt from `/mnt/samsung_2tb/mingyue/stl_repos/.venv-rtamt`, run on the recordings after each eval, with a numpy re-check of every verdict.
- **Output:** `robocasa_ws/eval_logs_stl/{nl,stl_nl,stl}/<task>/` holds the recordings, videos and `eval_info.json`. `robocasa_ws/eval_logs_stl/{nl,stl_nl,stl}/episodes.csv` has one row per episode, with every pass/fail, diagnostic and the exact prompt.
- **Time:** about 79,000 steps per prompt. At about 75 ms per step (the earlier CloseFridge run), plus 6–9 s per reset and a policy load per (prompt, task), that is about 2–2.5 h per prompt, or about 5 h for all three at two at a time.

## Steps

- [x] 1. Commit the pending LIBERO changes (decisions 28 and 29 there) on `libero-spatial-stl`, then start the branch `robocasa-stl` from that commit.
- [x] 2. Write `robocasa_ws/stl_prompt/`.
- [x] 3. Test the checker on hand-made recordings. For each spec type there is a passing and a failing case for each part, plus the boundaries:
  - landing at the deadline step passes, one step later fails;
  - a rest that breaks on the last sample fails;
  - 2 cm and 10° for `Disturbed`, and the speed limits for objects, joints and the base;
  - the drawer-frame measurement in OpenDrawer.

  A test also checks that all 540 prompts match the templates and fit π0.5's token budget.
- [x] 4. **Idle-robot check:** zero actions, no policy, cameras off, all 18 tasks × seeds 1000–1009. Expect no task success, no `Disturbed` flag and no `fixture_changed`. Objects can still be moving at t = 0, and two fixtures move on their own near their limits. If anything drifts past a threshold, stop and review.
- [x] 5. **Pilot:** 1 episode per task with `nl` (18 episodes).
  - Compare the checker's verdicts with the videos and tune the thresholds.
  - Check that `ep_meta` and the start poses match across prompts.
  - Measure RAM.
  - If success is near zero on most tasks, review before the full run.
- [x] 6. Review the pilot before the full run.
- [ ] 7. Full 540-episode run in `screen`. **Stopped at 20:10 on 2026-10-31 on request, after 2 of 54 pairs** (see [Results](#results)).
- [ ] 8. Fill in the results below. Partial: only the finished pairs are recorded.

## Checks before the run (steps 1–5)

- **Code** (branch `robocasa-stl`, from `54703de`, which commits the pending LIBERO changes): `robocasa_ws/stl_prompt/`
  - `stl_spec.py`: task table, deadlines, prompt templates, the spec as rtamt text.
  - `recorder.py`: per-step recordings (and the scene-determinism patch).
  - `launch_eval.py`: prompt swap, no-early-stop `step`, state/action layout, recordings.
  - `idle_check.py`: zero-action runs with cameras off.
  - `monitor.py`: the checker; writes `episodes.csv` and the tables.
  - `test_monitor.py` (rtamt venv), `test_prompts.py` (pixi env): the tests.
  - `run_eval.sh`: one (prompt, task) eval. `driver.py`: the restartable `screen` driver. `make_specs.py` → `specs.json`.
- **Hand-made recordings:** 32 tests, all passing; rtamt and numpy agree on every one. For P, F (including the microwave's distance-based `Released`) and N:
  - a rest starting at the deadline step passes, one step later fails;
  - a rest that breaks on the last sample fails;
  - `Still` 0.0099/0.0101 m/s and 0.249/0.251 rad/s, `PartStill` ±0.0099/0.0101, `BaseStopped` 0.0199/0.0201 m/s and 0.049/0.051 rad/s;
  - `Disturbed` at 0.0199/0.0201 m and 9.9°/10.1°, spin about the vertical counts, moved-and-put-back counts;
  - the OpenDrawer utensil in a rotated, sliding drawer frame (0.0199/0.0201 m slip), and the settled reference (capped at 2 s and at the first gripper touch);
  - each deadline-failure cause.
- **Prompts:** all 540 prompts (180 recorded scenes × 3) match the templates, use RoboCasa's own words and are ASCII. The longest full π0.5 inputs are 91 (`nl`), 116 (`stl_nl`) and 105 (`stl`) tokens of 200. The seed-1000 prompts equal the [example table](#prompts) in all 18 rows. Task list and limits match RoboCasa's registry.
- **Idle-robot check** (`eval_logs_stl/idle/`, 180 scenes, zero actions, cameras off; turning the cameras off changes neither the scene nor the trajectory):
  - no task success; rtamt = numpy on 180/180;
  - **3 scenes flagged `Disturbed` with t = 0 as the reference**: a round object (onion, corn, bell pepper) was still rolling at t = 0 and settled within 1.2 s, after moving up to 2.3 cm and 44°. With the settled reference (decision 27) none is flagged; the largest remaining drift is 5.6 mm and 9.1° (the OpenDrawer utensil);
  - **joints that move on their own:** free speed knobs on the mixer and blender (up to 0.15 rad), the kettle switch (0.10), a dishwasher door (0.06), coffee-machine levers (≤ 0.03), and in 2 PickPlaceCounterToCabinet scenes an open cabinet door that swings 0.67 rad. With the 0.2 threshold (decision 28) only that door is flagged.
- **Pilot** (`eval_logs_stl_pilot/`, `nl`, seed 1000, 18 episodes; 2.5–3 min per task, mostly startup):
  - **First attempt: 0/18 task success** (`eval_logs_stl_pilot_compiled/`). The robot drove around the kitchen. See bugs 1 and 2 in [Bugs found and fixed](#bugs-found-and-fixed). An aborted second attempt with only the first fix is in `eval_logs_stl_pilot_compileoff_wrongorder/`.
  - **With both fixes: 7/18 task success**, deadline met 3/18, clean success 6/18, Full STL 3/18. The robot now stays put for tabletop tasks, reaches, grasps and pushes.
  - Successes: CloseFridge, OpenCabinet, OpenDrawer, OpenStandMixerHead, PickPlaceCounterToCabinet, PickPlaceDrawerToCounter, SlideDishwasherRack.
  - **Verdicts match the recordings and videos:** CloseFridge was closed at 9.75 s but the gripper rested on the door from 16.15 s to the end; SlideDishwasherRack was done at 7.6 s and touched again at 14.45–15.05 s; OpenCabinet and PickPlaceDrawerToCounter succeeded after the deadline (25.1 s and 24.0 s); in OpenCabinet the boxed drink inside tipped 11.9° in the last second as the hand reached in; in TurnOnSinkFaucet the arm knocked two counter items (13.6 cm, 118°).
  - Thresholds kept: successful P rests start within 0.25 s of success, and no F rest failed on `PartStill` alone.
  - Consistency: 18/18 episodes run the full limit, rtamt = numpy, LeRobot's success = any(`success`). The 18 seed-1000 scenes equal the idle check's.
  - **RAM:** each eval peaks at about 14 GB, and free memory dropped to 13.6 GB with two running, so the full run uses two at a time.
  - **Expected time:** about 40 s per episode plus about 1.5 min of startup per (prompt, task): about 8–9 min per pair, 54 pairs two at a time, about 4 h.

## Bugs found and fixed

Found during steps 2–5, before the full run. Bugs 1–3 would have invalidated the results; the full run uses the fixed code (commits `9fcf9d1`, `85c65d9`).

| # | Bug | Symptom | Cause | Fix |
| --- | --- | --- | --- | --- |
| 1 | **Scrambled camera images** | First pilot: 0/18 task success; after the first frame the videos show tiled copies, noise or black. Also with one eval alone and with empty GPUs | The checkpoint's config sets `compile_model: true`. With torch.compile in the same process, MuJoCo's EGL camera renders come back corrupted. Without the policy, or with plain CUDA work in the process, the images are clean | `run_eval.sh` passes `--policy.compile_model=false`. Videos checked clean afterwards |
| 2 | **State and action vectors in the wrong order** | With clean images the robot still drove away from the counter in tabletop tasks; the gripper never got closer to the target | LeRobot 0.6.1's `RoboCasaEnv` builds the state as `base_pos, base_quat, ee_pos_rel, ee_quat_rel, gripper` and reads actions as `base_motion, control_mode, ee_pos, ee_rot, gripper`. The checkpoint was trained on the RoboCasa365 dataset layout `ee_pos_rel, ee_quat_rel, base_pos, base_quat, gripper` / `ee_pos, ee_rot, gripper, base_motion, control_mode`, as its normalization stats show (state dims 7–9: z = 0.70 m with std 0.002; dims 10–11 always 0; action dims 6 and 11 are ±1 switches, dim 10 always 0). Arm commands went to the base | `launch_eval.py` converts both (`STL_IO_ORDER=dataset`, the default). Afterwards the base stays put, the gripper reaches the mug (3.5 cm) and grasps it, and the pilot succeeds on 7/18 |
| 3 | **Same seed, different scene** | TurnOnSinkFaucet seed 1000 placed its counter objects 0.9 m apart in two runs; repeated builds differed in about 1 of 4 processes, also with `PYTHONHASHSEED=0` | RoboCasa's counter-region sampler dedupes candidate counter tops with `list(set(valid_geoms))` (`models/fixtures/counter.py:813`). The XML elements hash by memory address, so the order, and the region the seeded RNG picks, changes between processes. This breaks pairing prompts by seed | `recorder.py` shadows `set` in that module with an order-preserving dedupe (its only bare `set()` call), leaving the RoboCasa checkout unchanged. 3 processes × 3 tasks × 3 seeds then match exactly. `monitor.py` now checks that every (task, seed) has the same scene under every prompt. The idle check was re-run with the fix |
| 4 | Microwave "part" was the whole microwave | `part_gripper` for TurnOnMicrowave would count any touch of the microwave housing | The start button is a geom on the microwave's main body, not a body of its own | Part contact is tracked per geom; for the microwave it is the start-button geom only. Found in the first smoke test, before any run |
| 5 | Settling objects counted as disturbed | Idle check: 3 of 180 scenes flagged `Disturbed` with no robot motion | Round objects still rolling at t = 0 | Measured from the settled pose (decision 27) |
| 6 | Idle joints tripped `fixture_changed` | 13 of 180 idle scenes flagged | Free knobs, the kettle switch, a dishwasher door and coffee-machine levers drift on their own | Threshold 0.2 (decision 28). Diagnostic only |

Bugs 5 and 6 are checker changes and need no rerun; the robot runs are unaffected.

## Checks done while planning

- **Seeding:** episode k resets with seed 1000 + k (`lerobot_eval.py:531` → `RoboCasaEnv.reset` → `RoboCasaGymEnv.reset`, which sets `env.rng`).
  - Two separate processes reset with seed 1000 matched in every field: layout, style, instruction, object types and model files, robot base pose, the full `qpos`, all three camera images, and the state vector.
  - They still matched after 20 identical actions.
  - **Not quite:** the pilot found that RoboCasa's counter-region sampler dedupes candidate counter tops with `list(set(...))` over XML elements (`models/fixtures/counter.py:813`), whose order follows memory addresses. In about 1 of 4 processes TurnOnSinkFaucet seed 1000 put its counter objects on the other side of the sink. `recorder.py` makes that dedupe order-preserving (it shadows `set` in that module, whose only bare `set()` call this is). With the patch, 3 processes gave identical scenes for 3 tasks × 3 seeds. `monitor.py` also checks every (task, seed) for the same scene under every prompt.
  - The global numpy RNG doesn't affect the scene. The policy noise comes from the torch RNG.
- **Object packs:** with only the lightwheel pack, 5 tasks couldn't build:
  - CoffeeSetupMug, PickPlaceCounterToStove, PickPlaceSinkToCounter and PickPlaceToasterToCounter on every seed;
  - TurnOnMicrowave on 8 of 12 seeds.

  Mugs, pans and plates exist only in the objaverse and aigen packs. Ethan's RoboCasa copy is in owner-only folders (`/home/ethan`, `/mnt/ares_2tb/Ethan`), so we downloaded our own objaverse pack.
- **Pretrain scenes:** with `("objaverse", "lightwheel")`, all 180 pretrain scenes (18 tasks × seeds 1000–1009) build, and none is already solved at t = 0.
  - Each seed gives a different kitchen. Seed 1000 is layout 21 / style 20 for most tasks.
  - Most tasks share the same kitchen for a given seed.
- **Speed:**
  - A reset takes 6–9 s, because the model is rebuilt every episode.
  - An environment step takes about 41 ms with three 256×256 cameras.
  - The earlier 1-episode CloseFridge run took 57 s for 600 steps, including startup.
- **Early stop:**
  - RoboCasa's `done` is always False (`ignore_done=True`), so LeRobot's `terminated` is just `is_success`.
  - `is_success` is RoboCasa's `_check_success()` after every step (`wrappers/gym_wrapper.py:334`).
  - The episode cap is the registry limit (`lerobot_eval.py:263`).

## Notes from the code survey

Behaviors to keep in mind when reading the pilot and the results:

- **Latched vs live goals:**
  - The kettle and microwave "on" states are latched flags.
  - The stove knob, faucet handle, every door, drawer and rack, and the navigation pose are recomputed every step, so the robot can undo them.
- **Fixtures that move on their own:**
  - The toaster-oven door creeps shut when it is nearly closed.
  - The mixer head falls open when it is nearly up.
  - Cabinet doors swing freely, with damping only.
  - Fridge doors, drawers and the dishwasher rack stay where they are left.
- **Loose success checks:**
  - CoffeeSetupMug has no upright or contact check.
  - PickPlaceDrawerToCounter counts contact with any counter.
  - PickPlaceCounterToStove doesn't require the pan to stay on the stove.
  - CloseFridge needs the door within about 0.45° of closed.
- **Who can trigger what:** any robot link can press the kettle lever, turn the faucet handle or turn a knob. Only gripper parts count for the microwave button.
- **Objects at t = 0:** objects can still be moving after the 10 settle steps; up to 3.5 mm/s and 0.15 rad/s were seen.
- **Drawer joints:** the generic `Fixture.get_joint_state` uses the wrong range for drawers. Use `Drawer.get_door_state`.
- **Scenes without others:** CloseToasterOvenDoor, SlideDishwasherRack, OpenStandMixerHead, TurnOnElectricKettle and NavigateKitchen have no free objects at all. CloseBlenderLid's only free body is the lid, which is a fixture.
- **NavigateKitchen start:** the robot starts 2.8–4.5 m from the target, facing away from it.

## Differences from the LIBERO-spatial run

- 18 different tasks with three spec types, instead of one formula for 10 tasks.
- A deadline per task, 60% of its limit, instead of a fixed 9 s.
- No "not on the plate until grasped" part.
- The prompts say "until the end", which is what's checked. LIBERO's prompts said 2 s while the checker required the rest to last to the end.
- `Disturbed` covers the whole episode in φ as well as in clean success, and counts rotation about any axis.
- `Rest` spin limit 0.25 rad/s instead of 0.1.
- `n_action_steps=50` instead of 10.
- The prompts change per episode, because RoboCasa samples the object or fixture per seed.
- One `lerobot-eval` per (prompt, task) instead of one per prompt.

## Results

**Partial run, stopped on request.** The full run started at 19:48 on 2026-10-31 and was stopped at about 20:10. Finished: **CloseBlenderLid under `nl` and `stl_nl`**, 10 episodes each (seeds 1000–1009). Nothing else finished:

- CloseFridge under `nl` failed three times with CUDA out-of-memory, and under `stl_nl` it was stopped mid-run. Another user's eval jobs took 20–21 GB on one GPU and 12–20 GB on the other, and kept launching new ones. The driver now waits for 11 GB of free GPU memory and retries up to 3 times (`afb96a4`). The CUDA device numbering now matches `nvidia-smi` (`d85af22`); before that it didn't, so the driver checked one GPU and launched on the other. The failed attempts' logs are in `eval_logs_stl/{nl,stl_nl}/CloseFridge*/eval.log`; none wrote a recording.
- `stl` never started, and the other 16 tasks never started under any prompt.

Outputs: `robocasa_ws/eval_logs_stl/{nl,stl_nl}/CloseBlenderLid/` (recordings, videos, `eval_info.json`), `eval_logs_stl/{nl,stl_nl}/episodes.csv`, `eval_logs_stl/driver.log`. Consistency: 20/20 episodes ran the full 600 steps; rtamt = numpy on 20/20; LeRobot's success = any(`success`) on 20/20; the same seed gave the same scene under both prompts on 10/10 seeds.

**CloseBlenderLid** (P, limit 30 s, deadline T = 18 s; O is empty, so clean success = task success and Full STL = deadline met)

| Prompt | Task success | Deadline met | Clean success | Full STL |
| --- | --- | --- | --- | --- |
| `nl` | 2/10 [6–51%] | 0/10 [0–28%] | 2/10 [6–51%] | 0/10 [0–28%] |
| `stl_nl` | 1/10 [2–40%] | 0/10 [0–28%] | 1/10 [2–40%] | 0/10 [0–28%] |

(95% Wilson range in brackets.)

- **No episode met the deadline under either prompt.** All three successes came after 18 s: `nl` seeds 1002 (18.6 s) and 1004 (27.4 s), `stl_nl` seed 1007 (27.45 s). Each then stayed at rest to the end.
- **Paired by seed,** `stl_nl` vs `nl` task success is 1 gained against 2 lost (exact McNemar p = 1). Ten episodes of one task can't show a difference either way.
- **Deadline failures:** `nl` 8 never done, 2 done after T; `stl_nl` 9 never done, 1 done after T.
- **The lid is often placed but RoboCasa's success never fires.** The lid was on the blender at some point (`lid_on` part) in 2 `nl` and 4 `stl_nl` episodes. Both `nl` ones succeeded; in 3 `stl_nl` ones success never followed (seeds 1002, 1004, 1005, with the lid on for 1.2–4.8 s). RoboCasa also needs the gripper > 0.15 m from the lid, while it is still on and upright. The first lift came at 7.9–27.3 s; 4 `nl` and 3 `stl_nl` episodes never lifted the lid. No episode pushed the lid in without lifting it.
- Not comparable to the pilot's CloseBlenderLid (0/1), and too few episodes to say anything about the rule prompts.

**Not recorded:** the other 17 tasks, and the `stl` prompt.

## Decisions

Agreed in a review session on 2026-10-31.

1. **Follow the LIBERO-spatial design** where nothing below says otherwise. The same policy and the same spec apply to all three prompts. Everything is recorded and checked afterward, with pass/fail per part plus diagnostics and no robustness score.
2. **All 18 `atomic_seen` tasks,** including NavigateKitchen with its reduced spec.
3. **Each task runs for its own RoboCasa limit** (300–700 steps), with no early stop on success.
4. **The prompts say exactly what is checked:** "until the end", with no 2 s rest.
5. **`Disturbed` is checked over the whole episode,** in φ and in clean success.
6. **Grasp,** where it is recorded, means a gripper part touches the object and the object is > 2 cm above its start. The both-pads check is recorded too. Since decision 20, grasp is a diagnostic only.
7. **Pair by seed.** Episode k uses seed 1000 + k under every prompt. Checked: the same seed gives the same scene.
8. **New code in `robocasa_ws/stl_prompt/`.** The LIBERO code is not changed.
9. **Commit the pending LIBERO changes first,** then branch `robocasa-stl`.
10. **One `screen` session with a driver.** One `lerobot-eval` per (prompt, task), two at a time (one per GPU), restartable, logging to files.
11. **The same four metrics and the same tables as LIBERO.**
12. **Test before the full run:** hand-made recordings, then the idle-robot check, then a pilot of 18 episodes, then a review.
13. **This doc layout,** with the brief kept word for word at the bottom.
14. **Object registries `("objaverse", "lightwheel")`.** We downloaded the objaverse pack ourselves. Without it 5 tasks can't build, and Ethan's copy isn't readable.
15. **`split=pretrain`,** so the kitchens and objects are familiar to the checkpoint. The task-success numbers are therefore not comparable to LeRobot's `atomic_seen` benchmark, which uses the target kitchens.
16. **10 episodes per task.**
17. **`n_action_steps=50`,** the checkpoint's default.
18. **The deadline T is 60% of the task's limit,** rounded to whole seconds. It is fixed before the run and doesn't depend on how the policy does. The limits are about twice the average human demo, so T is about 1.2× demo time.
19. **Three `Rest` types (P, F, N),** with RoboCasa's own success check as the goal in each. Every `Rest` implies task success.
20. **No "not done until grasped" part for any task.** Sliding and pushing into place both count. Grasp, push and bump are recorded as diagnostics only.
21. **Others `O`** = every free object except the target object, the target receptacle and the source container.
    - An object inside a moving part is measured relative to that part.
    - Fixtures aren't in φ, but their joints are recorded.
    - The "do not move any other object" sentence and `G !moved(other_objects)` are in every prompt, even when `O` is empty.
    - In TurnOnMicrowave, the item and its plate count as others.
22. **Idle-robot check** with zero actions on all 180 scenes before the pilot.
23. **Output in `robocasa_ws/eval_logs_stl/{nl,stl_nl,stl}/<task>/`,** with one `episodes.csv` per prompt.
24. **The prompt templates and names in [Prompts](#prompts).**
25. **The starting thresholds in [Predicates](#predicates):**
    - `Still`: 0.01 m/s and 0.25 rad/s;
    - `PartStill`: 0.01 rad/s or m/s;
    - `BaseStopped`: 0.02 m/s and 0.05 rad/s;
    - `Disturbed`: 2 cm or 10° about any axis;
    - `Released`: no gripper contact with the moving part.
26. **Grasp, `pushed_in`, `bumped` and `fixture_changed` are CSV columns only.**
27. **(Added after the idle check.) `Disturbed(o)` is measured from `o`'s settled pose,** not its pose at t = 0: the first step from which `o` is `Still` for 10 steps, no later than 2 s or the gripper's first touch. Some round objects are still rolling at t = 0.
28. **(Added after the idle check.) `fixture_changed` uses 0.2 rad or 0.2 m,** not 0.02. Free knobs, the kettle switch and a dishwasher door drift 0.02–0.15 with an idle robot. A freely swinging open cabinet door (0.67 rad) is still flagged.

## Original draft

The brief as first written, kept word for word.

> follow the 2026-10-25-libero-experiment.md. Use 18 automic seen task in robocasa,  each task with 3 different prompt, the orignal NL instruction, STL-NL and STL. each task run 10 episode
>
> run the task with screen, so disconnect with the machine will not affect the task running
>
> list the all the predicates used in the task, and their judgement condition in a table.
>
> assign resonnalble time for STL formuation, and add addtional conditions, like disturbed, rest follow 2026-10-25-libero-experiment.md in STL, and STL-NL. add monitor corresponding these predicate if the env itself does not have.
>
> provide same matrix as in 2026-10-25-libero-experiment.md.
