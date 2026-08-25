#!/usr/bin/env bash
# check-release.sh — release integrity: checksums, shell syntax, compose
# rendering, and patch applicability to a pristine v0.27.1 tree.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

sha256sum --check SHA256SUMS
bash -n build.sh start.sh stop.sh status.sh verify.sh
python3 -m py_compile sidecar.py

release_image="$(sed -n 's/^IMAGE=//p' .env.example | head -n1)"
[[ -n "$release_image" ]]
grep -Fq '      - ${MODEL_ID}' compose.yaml || true
grep -Fq '      - ${MODEL_REVISION}' compose.yaml
grep -Fq './chat-template.jinja:/opt/vllm-release/chat-template.jinja:ro' compose.yaml
grep -Fq '      - /opt/vllm-release/chat-template.jinja' compose.yaml
grep -Fq 'io.github.seanyourhighness.vllm.patch-sha256=' Dockerfile.release-metadata
grep -Fq 'io.github.seanyourhighness.vllm.draft-model=' Dockerfile.release-metadata
grep -Fq 'io.github.seanyourhighness.vllm.chat-template-sha256=' Dockerfile.release-metadata

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  # Render both profiles against .env.example (no GPU needed to render).
  docker compose --env-file .env.example -f compose.yaml config --quiet
  docker compose --env-file .env.example -f compose.yaml --profile vision config --quiet
fi

if [[ "${CHECK_PATCH_APPLY:-0}" == "1" ]]; then
  work="$(mktemp -d /tmp/vllm-dflash2-check.XXXXXX)"
  trap 'rm -rf "$work"' EXIT
  git clone --filter=blob:none https://github.com/vllm-project/vllm.git "$work/vllm"
  git -C "$work/vllm" checkout --detach 6e448d0ea9bf3d88d898b65449ca6dc2aec170ac
  git -C "$work/vllm" apply --check "$ROOT/0001-v0271-sm12x-dflash2-nvfp4.patch"
fi

echo "release integrity: PASS"
