#!/usr/bin/env bash
# Run one isolated, paired publication-benchmark phase and always restore
# production vLLM/Hermes state.  Usage: run_publication_phase.sh serving
set -euo pipefail

PHASE="${1:-}"
case "$PHASE" in
  serving) WORKLOADS=(code sharegpt) ;;
  longbench) WORKLOADS=(longbench_32k longbench_64k) ;;
  ifeval) WORKLOADS=(ifeval) ;;
  *) echo "usage: $0 {serving|longbench|ifeval}" >&2; exit 2 ;;
esac

BENCH_DIR="/home/sean/releases/vllm-sm12x-nvfp4-dflash2/bench"
PROD_DIR="/mnt/d/CODEX WORKSPACE/release-dflash2"
PROD_COMPOSE="$PROD_DIR/compose.yaml"
PROD_ENV="$PROD_DIR/.env"
BASELINE_COMPOSE="$BENCH_DIR/compose.baseline.yaml"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-${PHASE}"
RUN_DIR="$BENCH_DIR/results/$RUN_ID"
MODEL="qwen3.8-27b-nvfp4-dflash2"
BASE_URL="http://127.0.0.1:18089"
HERMES_WAS_ACTIVE="$(systemctl --user is-active hermes-gateway.service || true)"
VISION_WAS_RUNNING="$(docker inspect -f '{{.State.Running}}' qwen38-dflash2-vision 2>/dev/null || true)"
RESTORED=0

mkdir -p "$RUN_DIR"

restore() {
  local exit_code="$?"
  if (( RESTORED )); then
    exit "$exit_code"
  fi
  set +e
  docker compose -f "$PROD_COMPOSE" --env-file "$PROD_ENV" up -d --force-recreate server >/dev/null 2>&1
  if [[ "$VISION_WAS_RUNNING" == "true" ]]; then
    docker compose -f "$PROD_COMPOSE" --env-file "$PROD_ENV" up -d vision >/dev/null 2>&1
  fi
  for _ in $(seq 1 180); do
    curl -fsS "$BASE_URL/health" >/dev/null && break
    sleep 2
  done
  if [[ "$HERMES_WAS_ACTIVE" == "active" ]]; then
    systemctl --user start hermes-gateway.service >/dev/null 2>&1
  fi
  jq -n \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg restored_health "$(curl -fsS "$BASE_URL/health" >/dev/null 2>&1 && echo ok || echo failed)" \
    --arg hermes "$(systemctl --user is-active hermes-gateway.service || true)" \
    --arg vision "$(docker inspect -f '{{.State.Running}}' qwen38-dflash2-vision 2>/dev/null || true)" \
    '{timestamp:$timestamp,health:$restored_health,hermes:$hermes,vision:$vision}' > "$RUN_DIR/RESTORATION.json"
  RESTORED=1
  exit "$exit_code"
}
trap restore EXIT INT TERM

start_mode() {
  local mode="$1"
  docker compose -f "$PROD_COMPOSE" --env-file "$PROD_ENV" stop vision >/dev/null 2>&1 || true
  if [[ "$mode" == "dflash" ]]; then
    docker compose -f "$PROD_COMPOSE" --env-file "$PROD_ENV" up -d --force-recreate server
  else
    docker compose -f "$PROD_COMPOSE" -f "$BASELINE_COMPOSE" --env-file "$PROD_ENV" up -d --force-recreate server
  fi
  for _ in $(seq 1 180); do
    curl -fsS "$BASE_URL/health" >/dev/null && return 0
    sleep 2
  done
  echo "server failed to become healthy for mode $mode" >&2
  return 1
}

capture_config() {
  local mode="$1" rep_index="$2"
  docker inspect qwen38-dflash2-server | jq 'map(.Config.Env |= map(if test("^[^=]*(TOKEN|KEY|SECRET|PASSWORD)="; "i") then sub("=.*"; "=<redacted>") else . end))' > "$RUN_DIR/container-${mode}-r${rep_index}.json"
  if [[ "$mode" == "dflash" ]]; then
    docker compose -f "$PROD_COMPOSE" --env-file "$PROD_ENV" config --format json | jq '.services.server.environment |= with_entries(if (.key | test("TOKEN|KEY|SECRET|PASSWORD"; "i")) then .value = "<redacted>" else . end)' > "$RUN_DIR/compose-${mode}-r${rep_index}.json"
  else
    docker compose -f "$PROD_COMPOSE" -f "$BASELINE_COMPOSE" --env-file "$PROD_ENV" config --format json | jq '.services.server.environment |= with_entries(if (.key | test("TOKEN|KEY|SECRET|PASSWORD"; "i")) then .value = "<redacted>" else . end)' > "$RUN_DIR/compose-${mode}-r${rep_index}.json"
  fi
}

run_mode() {
  local mode="$1" rep_index="$2"
  start_mode "$mode"
  capture_config "$mode" "$rep_index"
  python3 "$BENCH_DIR/publication_bench.py" preflight --base-url "$BASE_URL" --model "$MODEL" --run-dir "$RUN_DIR/preflight-${mode}-r${rep_index}"
  for workload in "${WORKLOADS[@]}"; do
    for thinking in off on; do
      for concurrency in 1 2 4; do
        python3 "$BENCH_DIR/publication_bench.py" run \
          --base-url "$BASE_URL" --model "$MODEL" --run-dir "$RUN_DIR" \
          --workload "$BENCH_DIR/datasets/pinned/${workload}.jsonl" \
          --mode "$mode" --thinking "$thinking" --concurrency "$concurrency" --repeat "$rep_index"
      done
    done
  done
}

docker inspect qwen38-dflash2-server | jq 'map(.Config.Env |= map(if test("^[^=]*(TOKEN|KEY|SECRET|PASSWORD)="; "i") then sub("=.*"; "=<redacted>") else . end))' > "$RUN_DIR/production-container-before.json"
systemctl --user stop hermes-gateway.service

# Alternate paired mode order to reduce monotonic thermal/time drift.
for run_repeat in 0 1 2; do
  if [[ "$run_repeat" == "1" ]]; then
    run_mode baseline "$run_repeat"
    run_mode dflash "$run_repeat"
  else
    run_mode dflash "$run_repeat"
    run_mode baseline "$run_repeat"
  fi
done

python3 "$BENCH_DIR/publication_bench.py" verify --run-dir "$RUN_DIR"
restore
