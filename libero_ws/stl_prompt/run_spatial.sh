#!/usr/bin/env bash
# One libero_spatial STL eval: π0.5, one prompt variant, fixed-length episodes, per-step recordings.
#
# Usage (from libero_ws/):  stl_prompt/run_spatial.sh <variant> <gpu> <n_episodes_per_task> <out_root>
#   e.g. stl_prompt/run_spatial.sh nl 0 10 eval_logs_stl_spatial
# Writes <out_root>/<variant>/{eval_info.json,videos/,traces/} and <out_root>/<variant>.log.
set -euo pipefail
VARIANT=$1 GPU=$2 N=$3 OUT=$4
mkdir -p "$OUT"
CUDA_VISIBLE_DEVICES=$GPU MUJOCO_GL=egl \
STL_SPECS=stl_prompt/specs.json STL_VARIANT="$VARIANT" STL_NO_EARLY_STOP=1 \
STL_TRACE_DIR="$OUT/$VARIANT/traces" \
pixi run python stl_prompt/launch_eval.py \
  --policy.path=lerobot/pi05_libero_finetuned_v044 --env.type=libero --env.task=libero_spatial \
  --eval.batch_size=1 --eval.n_episodes="$N" --policy.n_action_steps=10 \
  --env.max_parallel_tasks=1 --seed=1000 --output_dir="$OUT/$VARIANT" \
  > "$OUT/$VARIANT.log" 2>&1
