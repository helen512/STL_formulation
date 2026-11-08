#!/usr/bin/env bash
# Records the NL-prompt episodes with the policy cameras plus the third-person camera.
set -u
ROOT=/mnt/samsung_2tb/mingyue/lerobot-libero
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 MUJOCO_GL=egl STL_VARIANT=nl STL_NO_EARLY_STOP=1

cd "$ROOT/libero_ws"
D=eval_logs_thirdperson/nl
mkdir -p "$D"
STL_SPECS=stl_prompt/specs.json STL_TRACE_DIR="$D/traces" pixi run python stl_prompt/record_thirdperson.py \
  --policy.path=lerobot/pi05_libero_finetuned_v044 --env.type=libero --env.task=libero_spatial '--env.task_ids=[1]' \
  --eval.batch_size=1 --eval.n_episodes=1 --policy.n_action_steps=10 --env.max_parallel_tasks=1 --seed=1000 \
  --output_dir="$D" > eval_logs_thirdperson/nl.log 2>&1
echo "libero_spatial_1 exit $?"

cd "$ROOT/robocasa_ws"
robocasa() {  # task, output dir, n_episodes, seed
  mkdir -p "$2"
  STL_TRACE_DIR="$2/traces" STL_SEED0=1000 pixi run python stl_prompt/record_thirdperson.py \
    --policy.path=lerobot/pi05_robocasa --policy.n_action_steps=50 --policy.compile_model=false \
    --env.type=robocasa --env.task="$1" --env.split=pretrain '--env.obj_registries=["objaverse","lightwheel"]' \
    --eval.batch_size=1 --eval.n_episodes="$3" --eval.use_async_envs=false --seed="$4" \
    --output_dir="$2" > "$2/eval.log" 2>&1
  echo "$1 $2 exit $?"
}
robocasa NavigateKitchen eval_logs_thirdperson/nl/NavigateKitchen 1 1000
robocasa TurnOnElectricKettle eval_logs_thirdperson/nl/TurnOnElectricKettle 1 1000
D=eval_logs_thirdperson/nl/NavigateKitchen_ep1-3
robocasa NavigateKitchen "$D" 3 1001

# LeRobot numbers videos from 0 within a run; seeds 1001-1003 are episodes 1-3.
V=$D/videos/NavigateKitchen_0
mv "$V/eval_episode_2.mp4" "$V/eval_episode_3.mp4" && mv "$V/eval_episode_1.mp4" "$V/eval_episode_2.mp4" \
  && mv "$V/eval_episode_0.mp4" "$V/eval_episode_1.mp4" \
  && sed -i -e 's/eval_episode_2\.mp4/eval_episode_3.mp4/g' -e 's/eval_episode_1\.mp4/eval_episode_2.mp4/g' \
    -e 's/eval_episode_0\.mp4/eval_episode_1.mp4/g' "$D/eval_info.json"
echo "rename exit $?"
