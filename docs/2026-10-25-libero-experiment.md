# LIBERO-spatial STL experiment

2026-10-25 · Status: **run complete** (300 episodes). Short answer: no. The rules in the prompt didn't make π0.5 follow them, and the deadline was met less often with them (96 → 90 → 84 of 100 episodes); see [Results](#results).

**Question:** if π0.5's prompt includes a timing rule and a "don't touch other objects" rule, does it follow them? Every LIBERO-spatial task runs with three prompts: the original instruction, the instruction plus the rules in English, and the rules as a raw STL formula. Every episode is checked against the same STL spec.

Earlier result ([libero_goal run](2026-10-25-stl-instructions.md)): adding "within 15 seconds" to the prompt did not change π0.5's timing. Expect the rules to mostly serve as a *check* here, not as steering.

## Spec

The same formula applies to all 10 tasks. `b` = `akita_black_bowl_1` (the target bowl), `p` = `plate_1`, and `O` = {`akita_black_bowl_2`, `cookies_1`, `glazed_rim_porcelain_ramekin_1`} (every movable object except `b` and `p`; the same in all 10 tasks).

$$
\varphi = \big(\neg\mathrm{On}(b,p)\ \mathbf U\ \mathrm{Grasp}(b)\big)
\ \land\ \mathbf F_{[0,9]}\mathbf G_{[0,2]}\mathrm{Rest}(b,p)
\ \land\ \bigwedge_{o\in O}\mathbf G_{[0,11]}\neg\mathrm{Disturbed}(o)
$$

In words:

- The bowl can't be on the plate before it has been grasped (picked up, not pushed).
- By 9 s the bowl is resting on the plate, and it keeps resting there for 2 s.
- During the first 11 s, no other object is moved more than 2 cm or tipped more than 10° (changed from "moved more than 5 cm" on 2026-10-26, decision 28).


| Predicate   | True when                                                                                             | Notes                                                                                                                                      |
| ----------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `On(b,p)`   | LIBERO's own goal check: the plate is below the bowl, they touch, and their xy distance is < 0.03 m   | LIBERO `check_ontop` (`libero/envs/object_states/base_object_states.py`)                                                                   |
| `Grasp(b)`  | both Panda finger pads touch the bowl                                                                 | robosuite `_check_grasp` (`robosuite/environments/manipulation/manipulation_env.py`). No lift height is required                           |
| `Rest(b,p)` | `On(b,p)`, and no gripper geom touches the bowl, and bowl speed < 0.01 m/s, and bowl spin < 0.1 rad/s | Uses contact, not "gripper open", because an open gripper can still touch the bowl. The thresholds are starting values, tuned in the pilot |
| `Moved(o)` | the center of `o` is > 0.05 m from where it was at t = 0 | **First version, replaced by `Disturbed(o)`** (decision 28); still reported in the CSV as `*_moved5`. Rotation is ignored. The plate and furniture (cabinet, drawers, stove) are not counted |
| `Disturbed(o)` | the center of `o` is > 0.02 m from where it was at t = 0, **or** its up-axis has tipped > 10° from its t = 0 direction | Added 2026-10-26 (decision 28). Used in φ for the first 11 s and in clean success for the whole episode. Spinning about the vertical (yaw) is ignored, since the bowls and the ramekin are round. The plate and furniture are not counted |


**Time:** 20 control steps per second. t = 0 is the first policy step, after LIBERO's 10 settle steps. Windows include both ends.


| Spec           | Steps                                      |
| -------------- | ------------------------------------------ |
| by 9 s         | the bowl lands at step ≤ 180               |
| rests for 2 s  | the landing step plus the next 40 steps    |
| first 11 s     | steps 0–220                                |
| episode length | 280 steps (14 s), no early stop on success |


**Checker form** (rtamt, discrete time, one sample per step). The run records `on`, `grasp` and gripper contact. Speed, spin, displacement and tilt are computed afterward from the recorded poses, so the thresholds can change without rerunning the robot.

```
((on_b_p < 0.5) until (grasp_b > 0.5))
and eventually[0:180](always[0:40](
      (on_b_p > 0.5) and (gripper_contact_b < 0.5) and (speed_b < 0.01) and (spin_b < 0.1)))
and always[0:220](
      (disp_akita_black_bowl_2 < 0.02) and (tilt_akita_black_bowl_2 < 10)
      and (disp_cookies_1 < 0.02) and (tilt_cookies_1 < 10)
      and (disp_glazed_rim_porcelain_ramekin_1 < 0.02) and (tilt_glazed_rim_porcelain_ramekin_1 < 10))
```



## Prompts

- `nl`: the suite's instruction, word for word. It comes from the task file name and is all lowercase.
- `stl_nl`: `nl` +  `within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.`
- `stl`: `(!on(B, plate) U grasped(B)) & F[0,9] G[0,2] resting_on(B, plate) & G[0,11] !moved(other_objects)`
  - `B` names the bowl by its location: `black_bowl_` + the instruction's location words, without "the".
  - Times are in seconds.
  - `other_objects` is the set `O`. The checker tests each object separately.

π0.5 replaces `_` with spaces before tokenizing, so the policy reads e.g. `on(black bowl on stove, plate)`. The longest full prompts (task text plus π0.5's state text) are 62 tokens for `nl`, 95 for `stl_nl` and 109 for `stl`, all under π0.5's 200-token limit, so nothing is cut off.

`#` is LIBERO's task id (0-based).


| #   | `nl` (original)                                                                          | `stl_nl` (original + rules)                                                                                                                                                                                                           | `stl` (raw STL)                                                                                                                                                                                                                | Other objects `O`                                                                      |
| --- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| 0   | pick up the black bowl between the plate and the ramekin and place it on the plate       | pick up the black bowl between the plate and the ramekin and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.       | `(!on(black_bowl_between_plate_and_ramekin, plate) U grasped(black_bowl_between_plate_and_ramekin)) & F[0,9] G[0,2] resting_on(black_bowl_between_plate_and_ramekin, plate) & G[0,11] !moved(other_objects)`                   | `akita_black_bowl_2`, `cookies_1`, `glazed_rim_porcelain_ramekin_1`                    |
| 1   | pick up the black bowl next to the ramekin and place it on the plate                     | pick up the black bowl next to the ramekin and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                     | `(!on(black_bowl_next_to_ramekin, plate) U grasped(black_bowl_next_to_ramekin)) & F[0,9] G[0,2] resting_on(black_bowl_next_to_ramekin, plate) & G[0,11] !moved(other_objects)`                                                 | same 3                                                                                 |
| 2   | pick up the black bowl from table center and place it on the plate                       | pick up the black bowl from table center and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                       | `(!on(black_bowl_from_table_center, plate) U grasped(black_bowl_from_table_center)) & F[0,9] G[0,2] resting_on(black_bowl_from_table_center, plate) & G[0,11] !moved(other_objects)`                                           | same 3                                                                                 |
| 3   | pick up the black bowl on the cookie box and place it on the plate                       | pick up the black bowl on the cookie box and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                       | `(!on(black_bowl_on_cookie_box, plate) U grasped(black_bowl_on_cookie_box)) & F[0,9] G[0,2] resting_on(black_bowl_on_cookie_box, plate) & G[0,11] !moved(other_objects)`                                                       | same 3. The bowl starts on `cookies_1`, so lifting it may nudge the box                |
| 4   | pick up the black bowl in the top drawer of the wooden cabinet and place it on the plate | pick up the black bowl in the top drawer of the wooden cabinet and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds. | `(!on(black_bowl_in_top_drawer_of_wooden_cabinet, plate) U grasped(black_bowl_in_top_drawer_of_wooden_cabinet)) & F[0,9] G[0,2] resting_on(black_bowl_in_top_drawer_of_wooden_cabinet, plate) & G[0,11] !moved(other_objects)` | same 3. The bowl starts in the open top drawer (furniture, not checked)                |
| 5   | pick up the black bowl on the ramekin and place it on the plate                          | pick up the black bowl on the ramekin and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                          | `(!on(black_bowl_on_ramekin, plate) U grasped(black_bowl_on_ramekin)) & F[0,9] G[0,2] resting_on(black_bowl_on_ramekin, plate) & G[0,11] !moved(other_objects)`                                                                | same 3. The bowl starts on the ramekin, and `akita_black_bowl_2` starts on `cookies_1` |
| 6   | pick up the black bowl next to the cookie box and place it on the plate                  | pick up the black bowl next to the cookie box and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                  | `(!on(black_bowl_next_to_cookie_box, plate) U grasped(black_bowl_next_to_cookie_box)) & F[0,9] G[0,2] resting_on(black_bowl_next_to_cookie_box, plate) & G[0,11] !moved(other_objects)`                                        | same 3                                                                                 |
| 7   | pick up the black bowl on the stove and place it on the plate                            | pick up the black bowl on the stove and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                            | `(!on(black_bowl_on_stove, plate) U grasped(black_bowl_on_stove)) & F[0,9] G[0,2] resting_on(black_bowl_on_stove, plate) & G[0,11] !moved(other_objects)`                                                                      | same 3                                                                                 |
| 8   | pick up the black bowl next to the plate and place it on the plate                       | pick up the black bowl next to the plate and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                       | `(!on(black_bowl_next_to_plate, plate) U grasped(black_bowl_next_to_plate)) & F[0,9] G[0,2] resting_on(black_bowl_next_to_plate, plate) & G[0,11] !moved(other_objects)`                                                       | same 3                                                                                 |
| 9   | pick up the black bowl on the wooden cabinet and place it on the plate                   | pick up the black bowl on the wooden cabinet and place it on the plate within 9 seconds, then release it and leave it resting on the plate for 2 seconds. do not move any other object during the first 11 seconds.                   | `(!on(black_bowl_on_wooden_cabinet, plate) U grasped(black_bowl_on_wooden_cabinet)) & F[0,9] G[0,2] resting_on(black_bowl_on_wooden_cabinet, plate) & G[0,11] !moved(other_objects)`                                           | same 3                                                                                 |




## Metrics


| Metric            | Passes when                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| **Task success**  | LIBERO's `On(b,p)` is true at any step of the 14 s episode. This is the standard benchmark number |
| **Deadline met**  | `F[0,9] G[0,2] Rest(b,p)`                                                                         |
| **Clean success** | task success, and `G ¬Disturbed(o)` over the whole 14 s episode for every `o` in `O` (decision 28) |
| **Full STL**      | all of φ                                                                                          |


Every clean success is a task success, and every full STL pass is a task success. Full STL and clean success don't quite nest: φ checks `Disturbed` for the first 11 s, while clean success checks it for the whole 14 s episode. Deadline met is reported on its own.

For each episode the checker also records diagnostics: the first grasp time, the landing time, the longest resting stretch, and the largest displacement of each object in `O`.

## Run setup

- **Policy:** π0.5 `lerobot/pi05_libero_finetuned_v044`, `--policy.n_action_steps=10` (re-plans every 0.5 s).
- **Episodes:** 10 tasks × 10 episodes × 3 prompts = 300. Under every prompt, episode k uses LIBERO starting state k (k = 0–9), with `eval.batch_size=1`.
- **No early stop:** every episode runs 280 steps. A patch to `LiberoEnv.step` returns `terminated=False` and keeps `info["is_success"]`. (LIBERO's own `done` flag is its success check, so it can't be passed through either; see the pilot notes.)
- **Seeds:** each prompt is a separate `lerobot-eval` run with seed 1000. Every episode is the same length, so the three prompts should get the same policy noise.
- **Parallel runs:** two at a time, one per GPU. Four at once ran out of RAM before.
- **Recorded every step:**
  - position, orientation, linear and angular velocity of every movable object
  - `On(b,p)` and `Grasp(b)`
  - gripper–bowl contact
- **Video:** one mp4 per episode.
- **Code:** extend `libero_ws/stl_prompt/` (`launch_eval.py`, `make_specs.py`, `stl_spec.py`, `monitor.py`) to handle both suites. Object lists come from the task files instead of being hard-coded.
- **Checker:** rtamt from `/mnt/samsung_2tb/mingyue/stl_repos/.venv-rtamt`, run on the recordings after each eval. It is kept out of the pixi env because of an antlr version conflict.
- **Output:** `libero_ws/eval_logs_stl_spatial/{nl,stl_nl,stl}/` holds the recordings, videos, `eval_info.json` and a per-episode CSV with every pass/fail and diagnostic.



## Steps

- [x] 1. Commit `libero_ws/stl_prompt/` and `docs/` to git, without the eval logs.
- [x] 2. Extend `stl_prompt/` for libero_spatial.
- [x] 3. Re-check the saved libero_goal recordings with the new code. It must reproduce nl 94%, stl_nl 92%, stl 84% and stl_bddl 70%.
- [x] 4. Test the checker on hand-made recordings: for each part of φ, one that passes and one that fails.
- [x] 5. Pilot: 1 episode per task with the `nl` prompt. Compare the checker's verdicts with the videos, and tune the `Rest` thresholds.
- [x] 6. Review the pilot before the full run.
- [x] 7. Full 300-episode run.
- [x] 8. Fill in the results below.



## Checks before the run (steps 1–6)

- **Code** (branch `libero-spatial-stl`): `libero_ws/stl_prompt/`
  - `stl_spec.py`: `BowlOnPlateSpec`, the spec above as rtamt text plus the `stl` / `stl_nl` prompt text.
  - `make_specs.py`: specs for both suites; movable objects come from each task's BDDL `:objects`.
  - `launch_eval.py`: prompt swap, no-early-stop patch, per-step recordings.
  - `monitor.py`: the checker; writes `episodes.csv` and the tables below.
  - `test_monitor.py`: the tests.
  - `run_spatial.sh`: the eval command.
- **Prompts:** all 30 generated prompts equal the table above word for word (checked by a test).
- **libero_goal re-check:** the new checker gives nl 94%, stl_nl 92%, stl 84%, stl_bddl 70%, and matches the old per-episode results on all 200 episodes in every field.
- **Hand-made recordings:** 21 tests, all passing. For each part of φ there is a pass and a fail case, plus the boundaries: landing at step 180 passes and 181 fails; 41 resting samples pass and 40 fail; a move at step 220 fails and at 221 passes; 0.049 m passes and 0.051 m fails; the plate moving is ignored. (These were the checks before the run. After decision 28 the suite has 29 tests, including the 2 cm / 10° boundaries for `Disturbed`.)
  - Each verdict is computed twice, by rtamt and by plain numpy, and the checker flags any episode where they differ. Shifting any window by one step makes the tests fail.
  - rtamt's `until` here means "not on the plate at any step *before* the first grasp". Grasp and landing in the same step passes.
- **Pilot** (10 episodes, `nl`, `eval_logs_stl_spatial_pilot/`): all 10 passed every part. rtamt = numpy and LIBERO's flag = any(`On`) in 10/10.
  - **Verdicts match the videos.** In task 4 the fingers tap the bowl several times after letting go (steps 154–167, `On` flickers off twice), and in task 0 the gripper comes back down onto the bowl at step 128. The checker sees both as gripper contact, so the first full 2 s rest starts late (8.55 s and 6.7 s), not right after landing.
  - `Rest` **thresholds kept at 0.01 m/s and 0.1 rad/s.** Right after release the bowl wobbles for under 0.4 s at ≥ 0.015 m/s and ≥ 0.3 rad/s. Once settled it is below 0.0002 m/s, and spin peaks at 0.077 rad/s during slow rocking in 2 of 10 episodes. Deadline verdicts were the same (10/10) for every threshold pair from 0.005 / 0.05 to 0.05 / 0.5; the rest start moved by at most 0.25 s.
  - **Speed and spin come from the simulator's body velocities** (recorded each step). Finite differences of the recorded poses (`monitor.py --vel pose`) give the same verdicts, with rest starts within 0.05 s.
- **Bugs found and fixed during the pilot:**
  - LIBERO's `step()` returns `done = success` (`libero/envs/bddl_base_domain.py:809`), so the first version of the patch, which passed `done` through, still stopped episodes at success. The patch now always returns `terminated=False`, and the checker warns if any recording isn't 281 samples.
  - Spin from poses first used `2·arccos(q₁·q₀)`, which turns the 5-decimal rounding of the recorded quaternions into about 0.2 rad/s of fake spin. It now uses `atan2`, and there is a test for it.



## Results

Run on 2026-10-25: 300 episodes, all 280 steps long, one video each. Outputs are in `libero_ws/eval_logs_stl_spatial/`. The checker's task success equals `lerobot-eval`'s own `pc_success` for all three prompts. rtamt and the numpy re-check agree on 300/300 episodes, and LIBERO's success flag equals "`On(b,p)` at some step" on 300/300.

**Summary** (episodes that passed / episodes run; 95% Wilson range of the pass rate in brackets)


| Prompt   | Task success    | Deadline met    | Clean success   | Full STL        |
| -------- | --------------- | --------------- | --------------- | --------------- |
| `nl`     | 97/100 [92–99%] | 96/100 [90–98%] | 88/100 [80–93%] | 87/100 [79–92%] |
| `stl_nl` | 98/100 [93–99%] | 90/100 [83–94%] | 86/100 [78–91%] | 76/100 [67–83%] |
| `stl`    | 96/100 [90–98%] | 84/100 [76–90%] | 87/100 [79–92%] | 75/100 [66–82%] |


With `Grasp` = "gripper touches the bowl and the bowl is > 2 cm above its start" instead of "both finger pads touch" (see below), Full STL is 87/100, **79/100** and **76/100**. The other columns don't change.

Clean success and Full STL use `Disturbed(o)` (decision 28). With the first check (`Moved` > 5 cm in the first 11 s), clean success was 96/100, 97/100 and 96/100, and Full STL 95/100, 86/100 and 83/100; that check missed most disturbances (see below).

**What the numbers say**

- **The rules didn't make π0.5 follow them. The deadline rule was met *less* often with the rules in the prompt:** 96 → 90 → 84 of 100 episodes.
  - Paired by starting state, `stl` failed the deadline in 12 episodes that `nl` passed and passed none that `nl` failed (exact McNemar p = 0.0005).
  - For `stl_nl` it was 10 against 4 (p = 0.18, within noise).
- **It isn't slower.** Median landing time is 5.0 s (`nl`), 5.1 s (`stl_nl`) and 5.05 s (`stl`); the bowl landed by 9 s in 96, 97 and 94 episodes. As in the libero_goal run, the time words didn't change the timing.
- **The extra failures come from touching the bowl again after placing it.** The bowl lands in time, but the gripper goes back down onto it, so no 2 s rest fits before 9 s. This happens in 0 deadline failures under `nl`, 6 under `stl_nl` and 8 under `stl`. Counting all episodes, the gripper touched the resting bowl again within the first 11 s in 20 (`nl`), 23 (`stl_nl`) and 36 (`stl`). Task 0 has 4 of these under each rule prompt. So the prompt that says "release it and leave it resting" gets more re-touching, not less.
- **Task success is unchanged within noise** (97 / 98 / 96%). Task 5 (bowl on the ramekin, second bowl on the cookie box) is the hardest under every prompt.
- **Disturbing other objects is common in two tasks, under every prompt.** With `Disturbed(o)` (moved > 2 cm or tipped > 10°, whole episode), another object was disturbed in 11, 12 and 12 of 100 episodes. Nearly all are in two tasks:
  - **Task 5** (second bowl on the cookie box): clean success is 2, 1 and 3 out of 10. After placing the target bowl, the robot often goes back to the second bowl. It tips it (10–63°) or picks it up and carries it toward the plate, in some episodes stacking it on the target bowl. The disturbance starts between 4 and 12 s. Videos checked: `stl_nl` episodes 0, 1 and 4, `nl` episode 6.
  - **Task 6** (bowl next to the cookie box): 7 out of 10 under each prompt. At 2.7–3.0 s, while the robot grasps the bowl, the cookie box tips up 29–41° on one edge for about 0.3 s, raised up to 2.4 cm, then falls back where it was. In one `stl` episode it slid 2 cm instead. It happens in starting states 1, 4 and 9 under every prompt (`stl`: 1, 2 and 9), so it depends on the layout, not the prompt. In the video the box is hidden behind the gripper at that moment, so this rests on the recorded pose.
  - The rule prompts don't reduce this (88, 86 and 87 clean successes), so π0.5 isn't following "do not move any other object".
  - `stl` task 7 episode 7 is a wrong-object failure: the robot put the **ramekin** on the plate and left the bowl on the stove. This is the keyword matching seen with raw STL in the libero_goal run. `stl` task 8 episode 4 lifted the cookie box 11 cm after 11 s.
  - The first `Moved` check (> 5 cm, first 11 s) caught only 1 of these per prompt. It ignores rotation (a bowl tipped 54° in place moves its center 2 cm), and most pick-ups finish after 11 s.
  - With `Disturbed` in φ, the Full STL gap between the prompts widens: 87 → 76 → 75 of 100 (it was 95 → 86 → 83 with `Moved`). Task 5 passes the full spec in only 1, 0 and 2 of 10 episodes.
- **"Grasp before it's on the plate" fails mostly because the** `Grasp` **check is too strict, not because of pushing.** Of the 3 + 3 rule-prompt episodes that fail this part with the bowl on the plate:
  - In all 3 under `stl_nl`, and in 2 under `stl` (task 0 ep 9, task 5 ep 8), the bowl was lifted 10–17 cm and carried, but both finger pads never touched it at the same time. Videos checked for `stl_nl` task 1 ep 7.
  - In `stl` task 8 ep 4 the pads first touched together only after landing, though the bowl had been lifted before.
  - The lift-based definition passes all six and changes no other verdict (at 2 cm; 1 cm also flips `nl` task 4 ep 2, which was never picked up). The only real "never grasped" episodes also never reached the plate.

**Per task: task success** (out of 10)


| #   | Bowl                                    | `nl` | `stl_nl` | `stl` |
| --- | --------------------------------------- | ---- | -------- | ----- |
| 0   | between the plate and the ramekin       | 10   | 10       | 10    |
| 1   | next to the ramekin                     | 10   | 10       | 10    |
| 2   | from table center                       | 10   | 10       | 10    |
| 3   | on the cookie box                       | 10   | 10       | 10    |
| 4   | in the top drawer of the wooden cabinet | 9    | 10       | 10    |
| 5   | on the ramekin                          | 8    | 10       | 7     |
| 6   | next to the cookie box                  | 10   | 10       | 10    |
| 7   | on the stove                            | 10   | 10       | 9     |
| 8   | next to the plate                       | 10   | 10       | 10    |
| 9   | on the wooden cabinet                   | 10   | 8        | 10    |


**Per task: clean success** (out of 10; the bowl is on the plate at some step *and* no other object was disturbed during the episode)


| # | Bowl                                    | `nl` | `stl_nl` | `stl` |
| - | --------------------------------------- | ---- | -------- | ----- |
| 0 | between the plate and the ramekin       | 10   | 10       | 10    |
| 1 | next to the ramekin                     | 10   | 10       | 10    |
| 2 | from table center                       | 10   | 10       | 9     |
| 3 | on the cookie box                       | 10   | 10       | 10    |
| 4 | in the top drawer of the wooden cabinet | 9    | 10       | 10    |
| 5 | on the ramekin                          | 2    | 1        | 3     |
| 6 | next to the cookie box                  | 7    | 7        | 7     |
| 7 | on the stove                            | 10   | 10       | 9     |
| 8 | next to the plate                       | 10   | 10       | 9     |
| 9 | on the wooden cabinet                   | 10   | 8        | 10    |

Which objects were disturbed (episodes out of 100):

| Object | `nl` | `stl_nl` | `stl` |
| --- | --- | --- | --- |
| second bowl (`akita_black_bowl_2`) | 8 | 9 | 7 |
| cookie box (`cookies_1`) | 4 | 4 | 6 |
| ramekin | 0 | 0 | 1 |

The per-episode CSV (`episodes.csv`) has `undisturbed_<object>`, `first_disturbed_s`, `max_disp_all_<object>` and `max_tilt_deg_<object>` for every episode, and `clean_moved5` for the first definition.


**Per task: deadline met / full STL** (out of 10)


| #   | `nl`    | `stl_nl` | `stl`   |
| --- | ------- | -------- | ------- |
| 0   | 10 / 10 | 6 / 6    | 6 / 6   |
| 1   | 10 / 10 | 10 / 9   | 9 / 9   |
| 2   | 10 / 10 | 10 / 10  | 8 / 7   |
| 3   | 10 / 10 | 9 / 8    | 10 / 10 |
| 4   | 9 / 9   | 10 / 10  | 8 / 8   |
| 5   | 7 / 1   | 9 / 0    | 6 / 2   |
| 6   | 10 / 7  | 10 / 7   | 10 / 7  |
| 7   | 10 / 10 | 8 / 8    | 8 / 8   |
| 8   | 10 / 10 | 10 / 10  | 10 / 9  |
| 9   | 10 / 10 | 8 / 8    | 9 / 9   |


**Why each deadline failure happened**


| Cause                                    | `nl`  | `stl_nl` | `stl`  |
| ---------------------------------------- | ----- | -------- | ------ |
| landed in time, gripper touched it again | 0     | 6        | 8      |
| landed in time, knocked off and back on  | 0     | 1        | 2      |
| landed after 9 s                         | 1     | 1        | 2      |
| never on the plate                       | 3     | 2        | 4      |
| **total**                                | **4** | **10**   | **16** |


**Limits**

- One policy (π0.5) and one seed per prompt; 10 starting states per task.
- `Grasp` as agreed (both finger pads) misses carried bowls; the lift-based number is a check made after the run, not part of the agreed spec.
- Different prompts make the trajectories diverge, so sharing a seed doesn't make the noise identical after the first step. The pairing above is by starting state.

**Reproduce** (from `libero_ws/`)

```bash
pixi run python stl_prompt/make_specs.py stl_prompt/specs.json
stl_prompt/run_spatial.sh nl 0 10 eval_logs_stl_spatial      # likewise stl_nl, stl; two at a time
R=/mnt/samsung_2tb/mingyue/stl_repos/.venv-rtamt/bin/python
$R stl_prompt/test_monitor.py
$R stl_prompt/monitor.py eval_logs_stl_spatial/{nl,stl_nl,stl}/traces                     # -> */episodes.csv + tables
$R stl_prompt/monitor.py --grasp-lift 0.02 eval_logs_stl_spatial/{nl,stl_nl,stl}/traces   # lift-based Grasp
```



## Decisions

Agreed in a review session on 2026-10-25.

1. **Same policy and same spec for all three prompts.** No retraining; the `nl` prompt is scored on rules it never sees. Any difference then comes from the prompt.
2. **The English timing numbers are the ones used.** In the draft formula the windows added up to 27 s (10 + 15 + 2), which didn't match the English and doesn't fit a 14 s episode. The clock starts at the first policy action.
3. **Fixed deadlines instead of nested windows.** "Not on the plate until grasped" keeps the meaning of "pick it up, don't push it" without giving the grasp its own deadline.
4. `Rest` **thresholds are not zero.** The simulation always jitters a little, so exactly zero velocity would never be reached.
5. `Grasp` **= both finger pads in contact.** No lift height is required.
6. **"Moved" = more than 0.05 m from the start.** (Replaced by decision 28.) It covers every movable object except the bowl and the plate. Rotation is ignored, and furniture isn't counted. The plate is left out because placing the bowl can nudge it.
7. **Record everything and check afterward.** A threshold can change without rerunning the robot.
8. **Checker output is pass/fail per part plus diagnostics.** There is no robustness score. One can be added later from the recordings.
9. **Four metrics,** reported in a summary table and a per-task table.
10. **Fixed-length episodes with no early stop.** Otherwise the 2 s rest could never be checked.
11. **The same starting states 0–9 for every prompt.**
12. `stl_nl` **keeps the original instruction word for word** and adds one fixed rule sentence. The only difference from `nl` is then the rules.
13. **The** `stl` **prompt uses ASCII and seconds, and names the bowl by its location.** Each scene has two black bowls, so a plain `black_bowl` wouldn't say which one. The other objects are grouped to keep the prompt short.
14. **One mp4 per episode,** to check verdicts by eye.
15. **Test before the full run:** hand-made recordings first, then a 10-episode pilot.
16. **Tables go in this doc.** The per-episode CSV goes next to the recordings.
17. **π0.5 is the policy.** It's the only LIBERO checkpoint available locally. It re-plans every 10 steps, as in the earlier runs.
18. **280-step episodes (14 s).** Task success counts the whole episode, so it's comparable to standard LIBERO numbers. The STL counts the first 11 s.
19. **Extend the existing** `stl_prompt/` **scripts** instead of starting a new folder.
20. **Commit the code and docs before changing them.** Until now they weren't in git.
21. **rtamt is the checker,** as in the libero_goal run.
22. **One eval per prompt, all with seed 1000,** two at a time.
23. **Seconds convert to steps as 180, +40 and 0–220,** with both ends included.
24. **The prompts are named** `nl`**,** `stl_nl` **and** `stl`**.** Output goes to `libero_ws/eval_logs_stl_spatial/`.
25. **Check libero_goal again after the scripts change.** The numbers must match the earlier report.
26. **This doc layout:** the agreed spec on top, and the draft kept below.
27. **95% ranges in the summary table only.** With 10 episodes per task, the ranges would be too wide to be useful.
28. **(Added 2026-10-26, after the run.) `Disturbed(o)` replaces `Moved(o)` in φ (first 11 s) and in clean success (whole episode).** `Disturbed(o)`: moved > 2 cm or tipped > 10° from the start. The first `Moved` check (> 5 cm, first 11 s) missed objects that were tipped in place or picked up after 11 s. Thresholds were chosen from all 900 object-episodes: undisturbed objects stay below 1 mm and 6.2° tilt, and every flagged case was checked against the recordings. Task 5 cases were also checked in videos; in task 6 the box is hidden behind the gripper. φ switched to `Disturbed` as well, for its first 11 s (agreed 2026-10-26). The first versions are still in the CSV as `no_move_moved5`, `clean_moved5` and `full_stl_moved5`.



## Original draft

The plan as first written, kept word for word.

> libero-spatial NL task: Pick up the black bowl between the plate and the ramekin and place it on the plate
>
> NL task with STL information: Pick up the black bowl between the plate and the ramekin; place the bowl on the plate and remains placed continuously for 2 seconds. finish the task with in 9s. Do not move other irralevent object entire first 11 seconds. (can make proper changes, make the wording clear)
>
> $$
> \boxed{\begin{aligned}
> \varphi ={}& \mathbf F_{[0,10]}\left(
>     \operatorname{Grasp}(b)\land
>     \mathbf F_{[0,15]}\mathbf G_{[0,2]}\operatorname{Placed}(b,p)
> \right)
> &\land\mathbf G_{[0,27]}\operatorname{displacement of other object = 0 }.
> \end{aligned}}
> $$
>
> where placed use the given predicate in LIBERO env
>
> do not move irrelevant object, disp < 0.05
>
> add addtional predicate for the remains places: gripper is open/object is being released (not in contact of gripper), the release object speed, anguler velocity is within a certain small value or zero.
>
> task:
>
> - for each libero- spatial task, create the corresponding NL task with STL information, and raw stl with readable names for each task, put in a table in this file
> - add corresponding monitor scripts for STL satisfies checking
> - evel 10 episode for each task, with original NL, NL task with STL information, raw stl with readable names
> - matrix with task success, clean success, time deadline reach
> - per task success

