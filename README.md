# LeRobot LIBERO

Shared environment for running [LeRobot](https://github.com/huggingface/lerobot) with the LIBERO benchmark, including the π0.5 checkpoint.

The environment is managed with [Pixi](https://pixi.sh). Dependencies are pinned in `pixi.toml` and `pixi.lock`, so everyone who clones this repo gets the same setup. The full install needs about **14 GB** of disk.

## Requirements

- Linux x86_64 (`linux-64`)
- An NVIDIA GPU. PyTorch is pinned to the CUDA 11.8 wheels (`torch==2.7.1`, `torchvision==0.22.1`)
- [Pixi](https://pixi.sh) installed

## Setup

Install Pixi if you do not already have it:

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

Open a new shell so `pixi` is on your `PATH`, then from this repository:

```bash
pixi install
```

That installs Python 3.12 and `lerobot` with the `libero`, `pi`, and `evaluation` extras, plus the CUDA 11.8 PyTorch build from the lockfile.

Check that PyTorch sees the GPU:

```bash
pixi run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

`torch.cuda.is_available()` should print `True`. Confirm the eval entrypoint is available:

```bash
pixi run lerobot-eval --help
```

## Hugging Face access

The π0.5 policy loads [PaliGemma](https://huggingface.co/google/paligemma-3b-pt-224). Before the first eval:

1. Create a [Hugging Face](https://huggingface.co) account.
2. Request access to [google/paligemma-3b-pt-224](https://huggingface.co/google/paligemma-3b-pt-224).
3. Log in from this environment:

```bash
pixi run hf auth login
```

## Run an evaluation

One LIBERO Spatial episode with the finetuned π0.5 policy. Results are written to `./eval_logs`.

```bash
pixi run lerobot-eval \
  --policy.path=lerobot/pi05_libero_finetuned_v044 \
  --env.type=libero \
  --env.task=libero_spatial \
  --eval.batch_size=1 \
  --eval.n_episodes=1 \
  --policy.n_action_steps=10 \
  --env.max_parallel_tasks=1 \
  --output_dir=./eval_logs
```
