# Evidence — all-NVFP4 DFlash2 release (RTX 5090 / SM120)

Compiled 2026-08-25 from the validated production runs. Source of record:
GBrain `vllm/2026-08-21-qwen38-dflash2-nvfp4-release-plan`,
`sessions/2026-08-24-dflash2-capacity-k7-production-promotion`,
`sessions/2026-08-24-dflash2-drafter-parity-radixark`,
`bench/2026-08-25-coding-benchmark-c1-vs-c4-dflash2-k7`.

## What makes this build unique

No public container, repo, or blog ships a working **NVFP4 weights + NVFP4
draft + NVFP4 KV + DFlash2 + concurrency** stack on a 5090. The universal
pattern is NVFP4 weights + FP8 KV; the DFlash2 draft is usually BF16 or
W8A16. This release is the all-NVFP4 4/4 artifact, with the drafter
itself NVFP4 (W4A16, group-16, compressed-tensors `nvfp4-pack-quantized`).

## Overlay contents (51 files, Python-only, +2826/−217 vs v0.27.1)

| Area | Files | What it does |
|---|---|---|
| DFlash2 core | `vllm/model_executor/models/qwen3_dflash2.py`, `vllm/v1/worker/gpu/spec_decode/dflash2/speculator.py` | block-diffusion drafter (5 Qwen3-style layers, local conv, candidate path selector), K7 verification |
| FlashInfer NVFP4 | `vllm/v1/attention/backends/flashinfer.py` (+599) | non-causal NVFP4 paged-prefill via fa2 backend, XQA dedicated stream, #4346 integration |
| GDN/ReplaySSM | `vllm/model_executor/layers/mamba/*`, `vllm/v1/attention/backends/gdn_attn.py` | GDN speculative ReplaySSM half, active-width fix, page-padding guard |
| Mixed cache layout | `vllm/v1/kv_cache_interface.py`, `vllm/config/cache.py` | per-attention-group KV dtype/layout (NVFP4 target + NVFP4 draft) |
| Runtime-K | `vllm/config/speculative.py`, `vllm/v1/worker/gpu/spec_decode/*` | dynamic-K schedule, exact-shape candidate selection, per-K graph dispatch |
| Fused-KV dequant | `vllm/model_executor/models/qwen3_dflash.py` | quantized-drafter fused-KV fallback (#51581 class) |

## Verified measurements (RTX 5090, SM120, K7, maxseq4, 8 GiB NVFP4 KV)

| Item | Value | Source |
|---|---|---|
| KV pool @ 8 GiB pin, 262K boot | 325,139 tokens | production promotion (2026-08-24) |
| c1 decode (techprose, 1024 tok) | 107.86 tok/s (autotune-on) | `evidence/runtime-k/mtp-no-rebuild-20260824/` |
| c4 aggregate (techprose) | 405.53 tok/s | same |
| c4 coding workload (3 legacy prompts + C++ lane) | 349.2 aggregate median, 2.31x vs c1 151.2 | `bench/2026-08-25-coding-benchmark-c1-vs-c4-dflash2-k7` |
| 4-lane 4,096-token soak | 368.51 aggregate, all streams completed, Running=4 Waiting=0 | production promotion |
| Draft acceptance (K7) | 5.2–5.8 mean accepted length, ~61% accept rate | coding benchmark |
| NIAH | 184,024-token needle recovered exactly | production promotion |
| Greedy determinism | PASS (canary `19×23 → 437`) | production promotion |
| Tools / structured output | 10/10, JSON-schema PASS | 2026-08-21 acceptance gates |
| Vision (CPU sidecar) | short/long probes PASS; multi-image 6/6 | 2026-08-21 gates |
| Restarts / OOM | 0 / 0 | production promotion |

## Gate results — release candidate

- Focused source tests: 23/23 PASS (2026-08-21); 60/60 spec-decode tests
  (runtime-K, 2026-08-23).
- Greedy determinism PASS; canary 437.
- NIAH PASS at 30,683 and 184,024 prompt tokens.
- Tools 10/10; JSON-schema structured output PASS.
- Vision short/long probes PASS.
- NVFP4 target/draft cache and FlashInfer XQA confirmed in live logs.

## Rollback

Stop the DFlash2 Compose project (`./stop.sh`) and start the unchanged
pinned MTP project (`vllm-sm120-nvfp4-mtp` on :18079). Both repos, images,
model caches, and configs remain installed; only one 27B GPU server runs
at a time on a 32 GiB card.
