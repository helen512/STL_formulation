Get Lerobot setup, Lerobot have, LIBERO env, pi0.5, other VLA checkpoint, and RoboCasa365
I am using pixi for env setup, if using conda or uv, let chatgpt convert the command (I suggest using pixi, convenient when later we use shared repo)

Whole setup need around 14GB storage


pixi init lerobot-libero -c conda-forge -p linux-64
cd lerobot-libero
pixi add "python=3.12"
pixi add --pypi "lerobot[libero,pi,evaluation]"

pixi run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"

pixi run lerobot-eval --help

before run the following, register huggingface account
request access in https://huggingface.co/google/paligemma-3b-pt-224?utm
pixi run hf auth login



pixi run lerobot-eval \
  --policy.path=lerobot/pi05_libero_finetuned_v044 \
  --env.type=libero \
  --env.task=libero_spatial \
  --eval.batch_size=1 \
  --eval.n_episodes=1 \
  --policy.n_action_steps=10 \
  --env.max_parallel_tasks=1 \
  --output_dir=./eval_logs
