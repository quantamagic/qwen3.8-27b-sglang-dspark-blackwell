#!/usr/bin/env bash
# status.sh — show containers, health, GPU, and model-cache status.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
[[ -f .env ]] || cp .env.example .env
set -a
# shellcheck disable=SC1091
source .env
set +a

docker compose -f compose.yaml ps
echo
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
echo
for vol in vllm-sm12x-qwen38-dflash2-model-cache \
           vllm-sm12x-qwen38-dflash2-vllm-cache \
           vllm-sm12x-qwen38-dflash2-draft-cache; do
  docker volume inspect "$vol" --format "$vol: {{.Mountpoint}}" 2>/dev/null || echo "$vol: not created"
done
