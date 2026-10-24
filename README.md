# LeRobot LIBERO

Environments for running [LeRobot](https://github.com/huggingface/lerobot) with the LIBERO benchmark and [RoboCasa365](https://robocasa.ai), including π0.5 checkpoints for both.

The two simulators need conflicting packages, so each one has its own [Pixi](https://pixi.sh) workspace:

| Folder | Simulator | robosuite | MuJoCo | numpy |
| --- | --- | --- | --- | --- |
| `libero_ws/` | LIBERO (`hf-libero`) | 1.4.0 | 3.8.1 | 2.2.6 |
| `robocasa_ws/` | RoboCasa365 | 1.5.2 (checkout) | 3.3.1 | 2.2.5 |

Each folder has its own `pixi.toml` and `pixi.lock`. Run `pixi` commands from inside the folder and Pixi picks that workspace's environment, so no `--environment` or `--manifest-path` flag is needed. The LIBERO environment takes about **7.5 GB** of disk and the RoboCasa environment about **6.7 GB**, plus about **5.4 GB** for the RoboCasa checkouts and kitchen assets.

## Requirements

- Linux x86_64 (`linux-64`)
- An NVIDIA GPU. Both workspaces pin PyTorch to the CUDA 11.8 wheels (`torch==2.7.1`, `torchvision==0.22.1`)
- [Pixi](https://pixi.sh) installed

Install Pixi if you do not already have it, then open a new shell so `pixi` is on your `PATH`:

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

## Hugging Face access

The π0.5 policy loads [PaliGemma](https://huggingface.co/google/paligemma-3b-pt-224). Before the first eval:

1. Create a [Hugging Face](https://huggingface.co) account.
2. Request access to [google/paligemma-3b-pt-224](https://huggingface.co/google/paligemma-3b-pt-224).
3. Log in from either workspace. The token is stored in `~/.cache/huggingface`, so both workspaces use it:

```bash
cd libero_ws
pixi run hf auth login
```

## LIBERO

```bash
cd libero_ws
pixi install
```

That installs Python 3.12 and `lerobot` with the `libero`, `pi`, and `evaluation` extras, plus the CUDA 11.8 PyTorch build from the lockfile. Check that PyTorch sees the GPU:

```bash
pixi run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

### Run an evaluation

One LIBERO Spatial episode per task (10 tasks) with the finetuned π0.5 policy. Add `--env.task_ids='[0]'` to run only the first task. Results are written to `libero_ws/eval_logs`.

```bash
cd libero_ws
MUJOCO_GL=egl pixi run lerobot-eval \
  --policy.path=lerobot/pi05_libero_finetuned_v044 \
  --env.type=libero \
  --env.task=libero_spatial \
  --eval.batch_size=1 \
  --eval.n_episodes=1 \
  --policy.n_action_steps=10 \
  --env.max_parallel_tasks=1 \
  --output_dir=./eval_logs
```

## RoboCasa365

RoboCasa365 is not a LeRobot extra. It needs `robosuite>=1.5.2`, `mujoco==3.3.1`, and `numpy==2.2.5`, while LIBERO's `hf-libero` needs `robosuite==1.4.0`, so it lives in `robocasa_ws/`. That workspace installs `lerobot` with only the `pi` and `evaluation` extras and adds the `robosuite` and `robocasa` checkouts as editable path dependencies.

RoboCasa's `setup.py` pins `lerobot==0.3.3`, and its `tianshou==0.4.10` dependency pins `protobuf~=3.19`. The `[pypi-options.dependency-overrides]` table in `robocasa_ws/pixi.toml` replaces both pins. `tianshou` is only used by RoboCasa's speed benchmark script.

The checkouts are the revisions LeRobot 0.6.1 uses for its RoboCasa benchmark image:

- `robocasa` `56e355ccc64389dfc1b8a61a33b9127b975ba681`
- `robosuite` `aaa8b9b214ce8e77e82926d677b4d61d55e577ab`

Clone them before `pixi install`, because the manifest points at those paths:

```bash
cd robocasa_ws
mkdir -p third_party
git clone --filter=blob:none https://github.com/robocasa/robocasa.git third_party/robocasa
git -C third_party/robocasa checkout 56e355ccc64389dfc1b8a61a33b9127b975ba681
git clone --filter=blob:none https://github.com/ARISE-Initiative/robosuite.git third_party/robosuite
git -C third_party/robosuite checkout aaa8b9b214ce8e77e82926d677b4d61d55e577ab

pixi install
```

Create the macro files, then download the lightwheel kitchen assets (textures, generative textures, fixtures, and objects). The download prompt expects `y`. This is enough for LeRobot's default `--env.obj_registries=lightwheel`. The objaverse and aigen packs are optional and much larger.

```bash
pixi run python -m robocasa.scripts.setup_macros
pixi run python third_party/robosuite/robosuite/scripts/setup_macros.py
printf 'y\n' | pixi run python -m robocasa.scripts.download_kitchen_assets \
  --type tex tex_generative fixtures_lw objs_lw
```

The workspace sets `MUJOCO_GL=egl` on activation, so headless rendering works without exporting it.

### Run one π0.5 episode

One `CloseFridge` episode with [`lerobot/pi05_robocasa`](https://huggingface.co/lerobot/pi05_robocasa). The checkpoint already uses RoboCasa's camera names (`robot0_agentview_left`, `robot0_eye_in_hand`, `robot0_agentview_right`), a 16-dim state, and 12-dim actions, so no `--rename_map` is required. `CloseFridge` runs for 600 environment steps. Results are written to `robocasa_ws/eval_logs`.

```bash
cd robocasa_ws
pixi run lerobot-eval \
  --policy.path=lerobot/pi05_robocasa \
  --env.type=robocasa \
  --env.task=CloseFridge \
  --eval.batch_size=1 \
  --eval.n_episodes=1 \
  --eval.use_async_envs=false \
  --policy.device=cuda \
  --policy.compile_model=false \
  --env.max_parallel_tasks=1 \
  --output_dir=./eval_logs
```
