# Changelog — vllm-sm12x-nvfp4-dflash2

## v0.27.1-sm12x-dflash2.1 (2026-08-25)

First public release of the all-NVFP4 DFlash2 stack.

### What ships
- `0001-v0271-sm12x-dflash2-nvfp4.patch` — 51-file Python-only overlay on
  vLLM v0.27.1 (commit `6e448d0ea`): DFlash2 backport (upstream PR #52816
  final merge), r0b0tlab SM121 safety deltas, NVFP4 non-causal prefill via
  the fa2 backend, fused-KV dequant fallback (#51581 class), mixed
  cache-dtype layout, target RoPE layout copy, non-causal CUDA-graph
  metadata, GDN ReplaySSM speculative half, Mamba page-padding guard,
  runtime-K + GDN active-width fixes, and the FlashInfer #4346 NVFP4
  paged-prefill integration.
- `compose.yaml` — server + optional CPU vision sidecar (profile `vision`),
  one-shot cache/draft initializers, localhost-only bindings, healthchecks,
  restart policy, 8 GiB shared memory, UID 2000 runtime, named model caches.
- `start.sh` / `stop.sh` / `status.sh` / `verify.sh` — preflight (GPU/SM
  12.0/12.1, VRAM, Docker, disk), pinned-image pull, readiness wait, and
  real chat smoke (deterministic canary `19×23 → 437`).
- `build.sh` — reproducible SM120 (x86_64, arch 12.0) and SM121
  (aarch64, arch 12.1, `SPARK=1`) build of the official vLLM Dockerfile
  with the overlay applied; `--push` for GHCR.
- `bench/` — long-decode corruption gate (v2), spec-decode gate (tools,
  non-repetition, K7 acceptance), vision gate, c8 concurrency proof.
- `Dockerfile.release-metadata` — OCI provenance labels (filled at publish).

### Validated runtime (RTX 5090 / SM120)
- NVFP4 target + NVFP4 draft + NVFP4 KV, DFlash2 K7, BF16 GDN/SSM state,
  8 GiB KV pin → 325,139-token pool, 262K context, max 4 concurrent seqs.
- Greedy determinism PASS; canary 437; NIAH at 184,024 tokens PASS;
  tools 10/10; JSON-schema structured output PASS; vision short/long
  probes PASS; c4 4,096-token soak 368.51 aggregate tok/s (all four
  streams completed, Running=4, Waiting=0); zero restarts, zero OOM.

### Not yet validated
- SM121/aarch64 native build (recipe ships; no GB10 hardware at release
  time). The multi-arch tag is withheld until the SM121 build passes the
  full correctness matrix natively.
