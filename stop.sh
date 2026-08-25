#!/usr/bin/env bash
# stop.sh — stop the DFlash2 Compose project.
#   ./stop.sh                  # stop + remove containers (volumes kept)
#   ./stop.sh --purge-cache    # also remove the named model/vllm/draft caches
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
[[ -f .env ]] || cp .env.example .env
set -a
# shellcheck disable=SC1091
source .env
set +a

docker compose -f compose.yaml --profile vision down --remove-orphans
if [[ "${1:-}" == "--purge-cache" ]]; then
  docker volume rm \
    vllm-sm12x-qwen38-dflash2-model-cache \
    vllm-sm12x-qwen38-dflash2-vllm-cache \
    vllm-sm12x-qwen38-dflash2-draft-cache
elif [[ -n "${1:-}" ]]; then
  echo "usage: ./stop.sh [--purge-cache]" >&2
  exit 2
fi
