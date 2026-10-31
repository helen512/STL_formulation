#!/usr/bin/env bash
# One RoboCasa STL eval: π0.5, one prompt variant, one task, fixed-length episodes, per-step recordings.
#
# Usage (from robocasa_ws/):  stl_prompt/run_eval.sh <variant> <task> <gpu> <n_episodes> <out_root>
#   e.g. stl_prompt/run_eval.sh nl CloseFridge 0 10 eval_logs_stl
# Writes <out_root>/<variant>/<task>/{eval_info.json,videos/,traces/,eval.log}.
# Episode k resets with seed 1000 + k (lerobot-eval --seed=1000, batch size 1).
set -euo pipefail
VARIANT=$1 TASK=$2 GPU=$3 N=$4 OUT=$5
D="$OUT/$VARIANT/$TASK"
mkdir -p "$D"
CUDA_VISIBLE_DEVICES=$GPU MUJOCO_GL=egl \
STL_VARIANT="$VARIANT" STL_NO_EARLY_STOP=1 STL_TRACE_DIR="$D/traces" STL_SEED0=1000 \
pixi run python stl_prompt/launch_eval.py \
  --policy.path=lerobot/pi05_robocasa --policy.n_action_steps=50 \
  --env.type=robocasa --env.task="$TASK" --env.split=pretrain '--env.obj_registries=["objaverse","lightwheel"]' \
  --eval.batch_size=1 --eval.n_episodes="$N" --eval.use_async_envs=false \
  --seed=1000 --output_dir="$D" \
  > "$D/eval.log" 2>&1
