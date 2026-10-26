# STL instructions for LIBERO: repo survey and first π0.5 test

2026-10-25. Question: which Signal Temporal Logic (STL) repo can we use to give LIBERO tasks as instructions, either the STL formula itself or STL translated to natural language?

## Summary

- **Use STL → template English as the π0.5 prompt, and rtamt to parse and monitor the STL.** On `libero_goal` (10 tasks × 5 episodes), template English scored **92%**, against **94%** for LIBERO's own instructions. That is one episode apart, within noise.
- **Raw STL as the prompt partly works, but for the wrong reason.** Readable names (`F[0,15] on(black_bowl, plate)`) scored **84%**. BDDL ids (`F[0,15] on(akita_black_bowl_1, plate_1)`) scored **70%**. π0.5 matches keywords: when it fails, it confidently does a *different* LIBERO task that shares the nouns.
- **No repo translates an arbitrary STL formula to English.** Every trained model in these repos goes NL → STL. I wrote a small template translator for LIBERO's predicates: `libero_ws/stl_prompt/stl_spec.py`.
- **rtamt (git HEAD) is the only usable STL library that both parses formula strings and gives a clean formula tree.** It handles parsing and both offline and per-step monitoring, and its tree can be walked to render English. Its robustness verdicts matched LIBERO's success flag on all 200 episodes.
- **Don't expect π0.5 to follow the temporal parts.** LIBERO's instructions contain no deadlines, "until" or "do not", and adding "within 15 seconds" didn't change its timing. Today STL is useful for *specifying and checking* behaviour, not for *steering* the policy. Making the policy follow STL needs fine-tuning, which is what Logic-VLA (below) does on π0.5.
- **Setup bug found:** `~/.libero/config.yaml` still points at the deleted root `.pixi` env, so LIBERO evals from `libero_ws` can't find the BDDL files. Fix is under [Issues found](#issues-found).

## How a prompt reaches π0.5 in LeRobot

- `lerobot/envs/libero.py` sets `LiberoEnv.task_description = task.language`.
- `lerobot/scripts/lerobot_eval.py` copies it into `observation["task"]` on every step.
- Swapping the instruction therefore only needs a patch to `task_description`. `stl_prompt/launch_eval.py` does this (with `eval.batch_size=1`, which uses a SyncVectorEnv in the same process).

LIBERO's success test is a conjunction of BDDL predicates, checked at every step. These are the natural STL atoms:

| Suite | Goal predicates (from the BDDL files) |
| --- | --- |
| libero_spatial | `on(akita_black_bowl_1, plate_1)` for all 10 tasks |
| libero_object | `in(<object>, basket_1_contain_region)` |
| libero_goal | `open`, `on`, `in`, `turnon` over one shared scene, so the prompt decides the task |
| libero_10 | two or three predicates per task, e.g. `turnon(flat_stove_1) & on(moka_pot_1, flat_stove_1_cook_region)` |

- Predicates are available in the simulator as `env._env.env._eval_predicate([...])`, and object poses as `object_states_dict[name].get_geom_state()`.
- BDDL has no order, deadline or "keep away" constraint. Those are exactly what STL adds.
- LIBERO runs at 20 Hz. LeRobot caps `libero_goal` at 300 steps (15 s).

## Repos surveyed

All shallow-cloned to `/mnt/samsung_2tb/mingyue/stl_repos/`. Unless marked, tests ran in Python 3.12 with numpy 2.2.6, the same versions as the LIBERO env.

### Parse / monitor STL

| Repo | Last commit | License | Parses STL strings | Formula tree for NL | Install + test on py3.12 / numpy 2.2.6 | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **rtamt** (nickovic) | 2026-09-20 | BSD-3 | **Yes** (`always[0:300]`, `eventually`, `until`, past-time ops, …) | **Yes**: typed tree with intervals, visitor class, re-parseable `node.name` | OK; all robustness signs correct | **Use this** (git HEAD `3db5a4e`) |
| stlpy (vincekurtz) | 2025-06-13 | MIT | No (Python API) | Weak (G/F/U expanded into and/or) | OK; needs traces padded to the full window | Planning (MILP), not monitoring |
| stlcg++ (UW-CTRL) | 2025-04-14 | **no LICENSE** | No | Good | OK with LIBERO's torch 2.7.1; GPU, vmap, gradients | Later, for batched or differentiable losses; use `padding="last"` |
| stljax (UW-CTRL) | 2026-03-25 | BSD-2 | No | Good | OK (jax CPU) | Same role as stlcg++, in JAX |
| stlcg (StanfordASL) | 2021-11-05 | MIT | No | OK | Breaks on numpy 2 (`np.Inf`), needs IPython | Dead |
| py-signal-temporal-logic (mvcisback) | 2022-09-24 | MIT | Yes | Poor (rewrites F/U, renames predicates) | OK but ~3.5 s per trace | Avoid |
| signal-temporal-logic (anand-bala) | 2023-10-13 (archived) | MIT | C++ only | — | **Fails** (py ≤ 3.8 wheels only, C++ build error) | Avoid |

rtamt caveats:
- **Use git HEAD, not PyPI 0.4.10.** On PyPI, the per-step `update()` monitor gives wrong values for `and` of sub-formulas with different horizons. Offline `evaluate()` is fine in both.
- **Keep it out of the pixi env.** rtamt pins `antlr4-python3-runtime==4.7`, while LIBERO's hydra/omegaconf need 4.9.3. rtamt still works on 4.9.3, printing a version-mismatch warning, but keeping it in its own venv avoids the conflict. Python must be < 3.13.
- **Online verdicts are delayed.** For per-step use, a future-time spec only produces a verdict after its time horizon (300 steps for `eventually[0:300]`), so rewrite it in past time (`historically`, `once`).
- **Truncated traces are padded.** At the end of a trace, `G` counts missing steps as satisfied and `F` as violated. Keep time windows inside the episode.

### Translate between NL and STL

| Repo | Last commit | License | Direction | Method | Usable for LIBERO? |
| --- | --- | --- | --- | --- | --- |
| NL2TL (yongchao98) | 2024-04-01 | none (README: commercial use only by permission) | NL → STL (T5); STL → NL only as a GPT-3 few-shot prompt used to build their dataset | T5-base, GPT-3 | Its STL → NL prompt (`dataset_creation_GPT3/framework1.py:186`) can be reused with any LLM. Data: ~39k "lifted" pairs on Google Drive, generic domains |
| DeepSTL (JieHE-2020) | 2022-05-02 | MIT | Grammar sampler writes random STL and English *together*; models go NL → STL | Rules + seq2seq | No: it can't take *your* formula, and its phrasing is signal-threshold style |
| AutoTAMP (yongchao98) | 2024-09-26 | MIT | NL → STL | GPT-4 prompts + Gurobi planner | No (needs OpenAI and Gurobi; 2D planning) |
| nl2spec (realChrisHahn2) | 2023-08-29 | MIT | NL → LTL (STL is a 2-example proof of concept) | Cloud LLMs | No |
| TeLoGraF (mengyuest) | 2025-07-14 | none | STL → plans, no NL | Graph encoder + flow matching | No for translation. Its STL families (reach, sequence, avoid, until) are good templates, and Logic-VLA's STL encoder is built on it |
| Lang2LTL (h2r) | 2025-03-26 | MIT | NL → LTL (no time bounds) | GPT-4 + T5 | No (navigation LTL). Clone deleted (2.9 GB of results) |
| STL-DivEn (ACL Findings 2025, 16k NL-STL pairs) | — | — | — | — | GitHub repo is gone (404); not found on HF, figshare or Zenodo |

### Papers that combine STL with VLAs (no code yet)

- **STeP** ([arXiv 2607.18580](https://arxiv.org/abs/2607.18580)) works on LIBERO and LIBERO-PRO, and introduces **LIBERO-Constrained**: 49 task–constraint instances covering spatial, logical and temporal constraints. A VLM (GPT-5.4) writes the STL, and an RRT + MPC controller executes it. π0.5 and others are only baselines. No code or data link yet; the paper says the task specs are on a project page. **LIBERO-Constrained is the benchmark to watch** for this line of work.
- **Logic-VLA** ([arXiv 2608.20556](https://arxiv.org/abs/2608.20556)) fine-tunes **π0.5** to take STL. Its baseline appends the STL text to the instruction; the main method uses a graph STL encoder based on TeLoGraF, and rtamt labels the rollouts.
  - Results on seen formulas: text-STL SFT reaches 66.5% STL satisfaction, the encoder 82.0%.
  - The domain is drone navigation, not LIBERO, and no code is released.
  - The HF account `Celina717` has π0.5 LoRA checkpoints and LeRobot datasets named `stl_prompt_sft` / `stl_encoder_sft`. It probably belongs to the first author, but the paper doesn't link it.

## Experiment: π0.5 on libero_goal with four prompt variants

Setup:
- Policy and suite: `lerobot/pi05_libero_finetuned_v044` on `libero_goal`, all 10 tasks × 5 episodes, LeRobot's fixed initial states, `n_action_steps=10`.
- One STL spec per task. Mostly `F[0,15s] goal`; task 3 is the ordering `F(open(top_drawer) & F in(bowl, top_drawer))`.
- Each spec is rendered three ways, so every prompt carries the same spec:

| Variant | Task 3 prompt | Task 5 prompt |
| --- | --- | --- |
| `nl` (LIBERO baseline) | open the top drawer and put the bowl inside | push the plate to the front of the stove |
| `stl_nl` (template English) | open the top drawer, then put the black bowl in the top drawer within 15 seconds | put the plate on the front of the stove within 15 seconds |
| `stl` (raw, readable names) | `F[0,15] (open(top_drawer) & F[0,15] in(black_bowl, top_drawer))` | `F[0,15] on(plate, front_of_the_stove)` |
| `stl_bddl` (raw, BDDL ids) | `F[0,15] (open(wooden_cabinet_1_top_region) & F[0,15] in(akita_black_bowl_1, wooden_cabinet_1_top_region))` | `F[0,15] on(plate_1, main_table_stove_front_region)` |

Each episode logs the spec's atoms and all object positions at every step. rtamt then checks:
- the task spec;
- the same spec with 5 s and 10 s deadlines;
- a side-effect spec `G(disp(obj) < 5 cm)` for each movable object the task doesn't mention ("clean" = task satisfied and nothing else moved).

### Results (50 episodes per variant)

| Variant | Task success (rtamt = LIBERO) | Clean success | Goal within 5 s | Goal within 10 s |
| --- | --- | --- | --- | --- |
| `nl` (baseline) | **94%** | 94% | 64% | 94% |
| `stl_nl` (template English) | **92%** | 90% | 68% | 92% |
| `stl` (raw, readable names) | **84%** | 84% | 60% | 82% |
| `stl_bddl` (raw, BDDL ids) | **70%** | 70% | 46% | 66% |

STL satisfaction from rtamt equalled LIBERO's success flag in all 200 episodes, as expected, since `F goal` is LIBERO's success test. That checks the trace → rtamt pipeline end to end.

Per task (successes out of 5):

| Task | `nl` | `stl_nl` | `stl` | `stl_bddl` |
| --- | --- | --- | --- | --- |
| 0 open the middle drawer | 4 | 4 | 5 | 3 |
| 1 bowl on the stove | 5 | 5 | 5 | 5 |
| 2 wine bottle on top of the cabinet | 4 | 4 | 4 | 3 |
| 3 open top drawer, then bowl inside | 5 | 5 | 5 | **0** |
| 4 bowl on top of the cabinet | 5 | 5 | 5 | 5 |
| 5 push the plate to the front of the stove | 5 | 3 | **0** | **0** |
| 6 cream cheese in the bowl | 5 | 5 | 3 | 4 |
| 7 turn on the stove | 4 | 5 | 5 | 5 |
| 8 bowl on the plate | 5 | 5 | 5 | 5 |
| 9 wine bottle on the rack | 5 | 5 | 5 | 5 |
| **Total** | **47/50** | **46/50** | **42/50** | **35/50** |

What the failures show:
- **Raw STL is followed by keyword matching.**
  - Under `stl_bddl`, task 3 failed 5/5. The drawer never opened; in 4 of the 5 episodes the robot put the bowl *on top of* the cabinet, which is task 4's goal.
  - Under both raw variants, task 5 (`F[0,15] on(plate, front_of_the_stove)`) failed 5/5. The plate never moved. Instead the robot put the **bowl** on the plate (task 8's goal) or on the stove (task 1's goal), nudged the cream cheese, or did nothing.
  - The side-effect monitor flagged these wrong-object episodes automatically.
- **Template English matches the baseline except on task 5.** There my template changed LIBERO's verb: "push the plate to the front of the stove" became "put the plate on the front of the stove". It scored 3/5 against 5/5, and both failures put the bowl on the plate. Adding a `push` template, or keeping the LIBERO verb per task, should close that gap.
- **The side-effect check catches things LIBERO's success flag doesn't.** One `stl_nl` episode on task 5 counted as a LIBERO success while the cream cheese was also moved.
- **Deadlines are measured, not followed.** Adding "within 15 seconds" didn't change timing: 64% (`nl`) vs 68% (`stl_nl`) of episodes reached the goal within 5 s. π0.5 never saw time phrases in training. Whether a tight deadline *in the prompt* would change anything is untested; I don't expect it to without fine-tuning.

## Recommendation

1. **Prompt route for π0.5 as it is today: STL → template English.**
   - Use `stl_spec.py`'s `to_english()`, or an rtamt-visitor version of it if specs arrive as strings.
   - For goals, keep LIBERO's wording ("put X on Y", "open the X", "turn on the X"). Don't expect π0.5 to obey temporal or negation clauses.
2. **Always monitor with rtamt.** It's the only way to know whether ordering, deadlines and safety were met, since LIBERO's success flag only checks the final goal.
3. **To make STL steer the policy, fine-tune.** Following Logic-VLA's recipe:
   - Generate STL variants of LIBERO tasks: ordering for libero_10, keep-out and dwell constraints, and STeP-style constraint families.
   - Label rollouts with rtamt.
   - SFT π0.5 with STL text, or with an STL encoder, appended to the prompt.
4. **For NL → STL** (turning existing LIBERO tasks into specs), read the BDDL goal directly rather than using a learned translator. If you need more varied English later, use NL2TL's STL → NL few-shot prompt with an LLM, and round-trip check its output.

## Issues found

- **`~/.libero/config.yaml` points at `/mnt/samsung_2tb/mingyue/lerobot-libero/.pixi/...`,** which was deleted in the workspace split. `get_libero_path("bddl_files")` and the init-state paths then fail, e.g. `FileNotFoundError: …/lerobot-libero/.pixi/envs/default/…/bddl_files/libero_spatial/…bddl`. I did not change it; all runs here used `LIBERO_CONFIG_PATH` with a corrected copy. Fix:

  ```bash
  sed -i 's#/lerobot-libero/.pixi/#/lerobot-libero/libero_ws/.pixi/#' ~/.libero/config.yaml
  ```

- **The root disk (`/`) was full** (1.7 GB free). **Fixed the same day:** the caches were moved to the 2 TB disk, leaving 27 GB free.
  - Hugging Face → `/mnt/samsung_2tb/mingyue/huggingface`; pixi/rattler → `/mnt/samsung_2tb/mingyue/pixi-cache`; everything else → `/mnt/samsung_2tb/mingyue/cache`.
  - Symlinks stay at the old `~/.cache/*` paths, since LIBERO hard-codes `~/.cache/libero`.
  - The top of `~/.bashrc` now sets `XDG_CACHE_HOME`, `HF_HOME`, `PIXI_CACHE_DIR` and `TMPDIR=/mnt/samsung_2tb/mingyue/tmp`.
- **Four π0.5 evals at once ran out of host RAM.** The machine has 62 GB and no swap; one run was killed (exit 137) while loading. Run at most two or three at a time.

## Files and how to reproduce

Files:
- `libero_ws/stl_prompt/stl_spec.py`: STL tree with three renderings: rtamt syntax, raw STL text, template English.
- `libero_ws/stl_prompt/make_specs.py`: libero_goal specs and prompt variants → `specs.json`.
- `libero_ws/stl_prompt/launch_eval.py`: `lerobot-eval` with the prompt swapped (`STL_VARIANT`) and per-step atom/pose traces (`STL_TRACE_DIR`).
- `libero_ws/stl_prompt/monitor.py`: rtamt checks on the traces.
- `libero_ws/eval_logs_stl/<variant>/`: eval output, videos and per-episode traces (33 MB total). Per-episode monitor results are in `libero_ws/eval_logs_stl/monitor_summary.json`.
- `/mnt/samsung_2tb/mingyue/stl_repos/`: the clones. `_survey/` holds the library test scripts and outputs and the NL2TL data dump; `.venv-rtamt/` is the rtamt venv.

Steps:

```bash
cd libero_ws
pixi run python stl_prompt/make_specs.py stl_prompt/specs.json

# one variant (nl | stl_nl | stl | stl_bddl); needs the LIBERO config fix above
CUDA_VISIBLE_DEVICES=0 MUJOCO_GL=egl STL_SPECS=stl_prompt/specs.json STL_VARIANT=stl_nl \
STL_TRACE_DIR=eval_logs_stl/stl_nl/traces pixi run python stl_prompt/launch_eval.py \
  --policy.path=lerobot/pi05_libero_finetuned_v044 --env.type=libero --env.task=libero_goal \
  --eval.batch_size=1 --eval.n_episodes=5 --policy.n_action_steps=10 \
  --env.max_parallel_tasks=1 --output_dir=eval_logs_stl/stl_nl

# monitor (rtamt venv; recreate with:
#   python3.12 -m venv .venv-rtamt && .venv-rtamt/bin/pip install numpy==2.2.6 \
#   "rtamt @ git+https://github.com/nickovic/rtamt@3db5a4e93e3152ea991be506a4d646e42f47ca20")
/mnt/samsung_2tb/mingyue/stl_repos/.venv-rtamt/bin/python stl_prompt/monitor.py \
  eval_logs_stl/nl/traces eval_logs_stl/stl_nl/traces eval_logs_stl/stl/traces eval_logs_stl/stl_bddl/traces
```

Limits of this test:
- 5 episodes per task, so each per-task cell is noisy.
- One suite (`libero_goal`), and only `F` and one ordering spec.
- None of the constraint-heavy specs (avoid / until / dwell) were given to the policy. They were only tried on synthetic traces in the library tests.
