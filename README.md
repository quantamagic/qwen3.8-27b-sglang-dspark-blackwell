# vLLM All-NVFP4 DFlash2 for Blackwell (SM120 / SM121)

Community vLLM build for a single Blackwell GPU: ModelOpt **NVFP4 target
weights**, **NVFP4 DFlash2 draft weights**, **NVFP4 KV cache**, and **DFlash2
K=7 block-diffusion speculative decoding** — 262K context, four concurrent
streams, tool calling, and an optional CPU-offloaded vision sidecar.

> This is not an official vLLM or NVIDIA image. It is a pinned community
> overlay on vLLM v0.27.1, validated on an RTX 5090 (SM120, 32 GB). The SM121
> (DGX Spark / GB10) build ships under the same contract; see
> [SM121 notes](#sm121--dgx-spark--gb10).

## What makes this stack different

- **All-NVFP4, end to end.** Target weights, DFlash2 draft weights, and the KV
  cache are all NVFP4. No public 5090 recipe ships 4-of-4 (NVFP4 weights +
  NVFP4 KV + DFlash2 + concurrency); the universal pattern is NVFP4 weights +
  FP8 KV.
- **DFlash2 K7 speculative decoding.** A 5-layer block-diffusion drafter
  (1.92B) proposes 7 tokens per verification step (8 target query tokens),
  with FULL_AND_PIECEWISE CUDA graphs `[8,16,24,32]` and an eager drafter
  that avoids integrated XQA graph interference. Measured ~61% draft
  acceptance and ~2.3x aggregate throughput vs. the legacy c3 profile.
- **Capacity-first profile.** Explicit 8 GiB NVFP4 KV pin → 325,139-token
  pool at 262K max context, BF16 GDN/SSM state, prefix caching, priority
  scheduling, chunked prefill.
- **Optional CPU vision sidecar.** The GPU server stays text +
  embedding-capable; a 4-CPU / 6 GB sidecar runs the 460M-param vision tower
  and proxies image requests. Off by default (`--profile vision`).

## Deploy in two commands

Prerequisites: Linux or WSL2, an RTX 5090 (SM120) or DGX Spark/GB10 (SM121),
a working NVIDIA driver, [Docker Engine with the Compose
plugin](https://docs.docker.com/engine/install/), and the [NVIDIA Container
Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Allow roughly 30 GB of downloads for the ~9 GB runtime image, the 20.6 GB
target checkpoint, and the 1.3 GB draft model.

```bash
git clone https://github.com/seanyourhighness/vllm-sm12x-nvfp4-dflash2.git
cd vllm-sm12x-nvfp4-dflash2 && ./start.sh
```

`start.sh` checks the GPU/SM, VRAM, Docker/Compose, disk space, and ports;
pulls the pinned runtime; downloads the exact pinned target and draft
checkpoints into Docker named volumes; starts vLLM; waits for health; and
sends a real chat completion (deterministic canary: `19×23 → 437`).

To include the optional CPU vision sidecar:

```bash
./start.sh --vision
```

On hosts with more than one GPU, set `GPU_DEVICE` in `.env` to the
Blackwell card's index or UUID (default `0`). `start.sh` probes only that
device and the compose stack exposes only that device to the container
(`NVIDIA_VISIBLE_DEVICES`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`), so an older
second card cannot interfere with device selection or enumeration.

Endpoints after startup:

- OpenAI-compatible vLLM API: `http://127.0.0.1:18089/v1`
- Vision-capable proxy (with `--vision`): `http://127.0.0.1:8016/v1`
- Served model: `qwen3.8-27b-nvfp4-dflash2`

First startup is dominated by the two downloads and CUDA/FlashInfer warmup.
Subsequent starts reuse the Docker image and the named model caches.

## Exact pinned stack

| Component | Pinned artifact |
|---|---|
| Runtime | `ghcr.io/seanyourhighness/vllm-sm12x-nvfp4-dflash2` (digest in `.env.example`; validated local tag `local-v0271-dflash2-capacity-k7-20260824`, image id `sha256:06f0c21d…`) |
| Target model + revision | [`gittensor-model-hub/Qwen3.8-27B-NVFP4-RTX5090@69274a0`](https://huggingface.co/gittensor-model-hub/Qwen3.8-27B-NVFP4-RTX5090/tree/69274a0d8dff5dd35bcee8290612f71e03b6e981) |
| Draft model | [`seanyourhighness/Qwen3.8-27B-DFlash2-NVFP4`](https://huggingface.co/seanyourhighness/Qwen3.8-27B-DFlash2-NVFP4) (`model.safetensors` sha256 `db19f849…`) |
| vLLM base | [v0.27.1 commit `6e448d0ea`](https://github.com/vllm-project/vllm/commit/6e448d0ea9bf3d88d898b65449ca6dc2aec170ac) |
| FlashInfer | 0.6.16.post3 (git `9dc1b24`), with [PR #4346](https://github.com/flashinfer-ai/flashinfer/pull/4346) SM120 NVFP4 paged-prefill backport |
| Overlay | [`0001-v0271-sm12x-dflash2-nvfp4.patch`](0001-v0271-sm12x-dflash2-nvfp4.patch) (51 files, Python-only; `sha256:248adb62…`) |
| Chat template | [`chat-template.jinja`](chat-template.jinja) (`sha256:398edf5b…`) |
| Checksums | [`SHA256SUMS`](SHA256SUMS) |

The image and models are pinned by immutable digests/revisions, not floating
tags. Compose passes the pinned model revision to vLLM and mounts the
shipped release template with `--chat-template`; this intentionally
overrides the different template bundled with the model. Model weights are
not redistributed in the runtime image.

## Common operations

```bash
./status.sh                 # containers, health, GPU, and model-cache status
./verify.sh --smoke         # health + model routing + deterministic canary
./verify.sh --full          # + long-decode determinism, NIAH, tool calling
./stop.sh                   # stop + remove containers (volumes kept)
./stop.sh --purge-cache     # also remove the named model/vllm/draft caches
```

## Validated runtime profile (the "everything we run" defaults)

| Knob | Value |
|---|---|
| Speculative config | `{"method":"dflash","model":"/models/draft","num_speculative_tokens":7,"kv_cache_dtype":"nvfp4"}` |
| Target KV cache | NVFP4, explicit 8 GiB pin (`8589934592` bytes) → 325,139-token pool |
| GDN/SSM state | `bfloat16` |
| Max model len | 262,144 |
| Max concurrent seqs | 4 (capacity-first; ~81K cached tokens/lane at full load) |
| Max batched tokens | 4,096 |
| CUDA graphs | `FULL_AND_PIECEWISE`, capture sizes `[8,16,24,32]` (K7 → 8-token verifier queries) |
| Drafter | forced eager (`VLLM_DFLASH_FORCE_EAGER=1`) — avoids integrated XQA graph interference |
| Target XQA | dedicated CUDA stream (`VLLM_XQA_DEDICATED_STREAM=1`) |
| FlashInfer autotune | enabled (loaded from the persisted autotune cache at boot) |
| Scheduling | priority + prefix caching + chunked prefill, long-prefill threshold 2048 |
| Sampling | temperature 0.6 override, thinking enabled (medium effort) |
| Tooling | `--enable-auto-tool-choice --tool-call-parser qwen3_coder` |

Measured on the RTX 5090 (SM120): c1 ≈ 108–151 tok/s, c4 aggregate median
≈ 349 tok/s (2.31x vs. c1), ~61% draft acceptance at K7, zero restarts,
zero OOM. See [EVIDENCE.md](EVIDENCE.md).

## SM121 (DGX Spark / GB10)

The same source + patch contract builds for `linux/arm64` with
`torch_cuda_arch_list=12.1`:

```bash
SPARK=1 ./build.sh          # native build on the Spark (fast path)
```

The SM121 build is **not yet natively validated** (no SM121 hardware was
available at release time); the SM120 artifact is the validated release.
The multi-arch tag will not be promoted until the SM121 build passes the
full correctness matrix (greedy determinism, NIAH, tools, vision, c4 soak)
natively on a GB10.

## Rollback / coexistence

This release coexists with the MTP release (`vllm-sm120-nvfp4-mtp`) as a
blue/green alternative: separate repo, image, Compose project
(`qwen38-dflash2`), container names, ports (18089/8016 vs. 18079/8006), and
model cache volumes. Only one 27B GPU server runs at a time on a single
32 GiB card. Rollback: `./stop.sh`, then start the unchanged pinned MTP
project.
