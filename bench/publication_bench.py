#!/usr/bin/env python3
"""Reproducible streaming client for the DFlash publication benchmark.

This program deliberately owns only benchmark artifacts. Server lifecycle is
handled by the paired shell wrapper so the runner can be tested against any
OpenAI-compatible endpoint without mutating production state.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


BENCH_DIR = Path(__file__).resolve().parent
PINNED_DIR = BENCH_DIR / "datasets" / "pinned"
METRIC_NAMES = (
    "vllm:prompt_tokens_total",
    "vllm:generation_tokens_total",
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
    "vllm:prefix_cache_hits_total",
    "vllm:prefix_cache_queries_total",
)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def api_json(base_url: str, path: str, payload: dict | None = None, timeout: int = 30) -> Any:
    body = None if payload is None else stable_json(payload).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def prometheus_snapshot(base_url: str) -> dict[str, float]:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/metrics", timeout=30) as response:
        lines = response.read().decode("utf-8", errors="replace").splitlines()
    values: dict[str, float] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        try:
            key, value = line.rsplit(" ", 1)
            values[key] = float(value)
        except ValueError:
            continue
    return values


def select_metrics(snapshot: dict[str, float]) -> dict[str, float]:
    selected: dict[str, float] = {}
    for key, value in snapshot.items():
        bare = key.split("{", 1)[0]
        if bare in METRIC_NAMES:
            selected[key] = value
    return selected


def metric_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    keys = sorted(set(before) | set(after))
    return {key: after.get(key, 0.0) - before.get(key, 0.0) for key in keys}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize_values(values: list[float]) -> dict[str, float | None]:
    return {
        "count": len(values),
        "mean": statistics.fmean(values) if values else None,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
    }


def tokenize_count(base_url: str, model: str, text: str) -> int | None:
    if not text:
        return 0
    try:
        payload = api_json(base_url, "/tokenize", {"model": model, "prompt": text, "add_special_tokens": False})
        return int(payload["count"])
    except Exception:
        return None


def request_stream(
    base_url: str,
    model: str,
    sample: dict,
    thinking: bool,
    run_label: str,
    retry_index: int,
    timeout: int,
) -> dict:
    request_id = f"pubbench-{run_label}-{sample['id']}-{retry_index}-{uuid.uuid4().hex[:12]}"
    payload = {
        "model": model,
        "messages": sample["messages"],
        "temperature": 0.6,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_completion_tokens": sample["max_completion_tokens"],
        "chat_template_kwargs": {"enable_thinking": thinking, "reasoning_effort": "medium"},
    }
    started_wall, started = utc_now(), time.perf_counter_ns()
    record: dict[str, Any] = {
        "schema_version": 1,
        "request_id": request_id,
        "item_id": sample["id"],
        "workload": sample["workload"],
        "started_at": started_wall,
        "prompt_hash": sha256_bytes(stable_json(payload["messages"]).encode()),
        "request": {
            "model": model,
            "temperature": payload["temperature"],
            "max_completion_tokens": payload["max_completion_tokens"],
            "thinking": thinking,
        },
        "retry_index": retry_index,
        "status": "error",
        "finish_reason": None,
        "usage": None,
        "visible_text": "",
        "reasoning_text": "",
        "chunk_timestamps_ms": [],
        "ttft_ms": None,
        "itl_ms": [],
        "e2e_ms": None,
        "error": None,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=stable_json(payload).encode(),
        headers={"Content-Type": "application/json", "X-Request-Id": request_id},
    )
    first_token_ns: int | None = None
    prior_token_ns: int | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            record["http_status"] = response.status
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                event = line[6:]
                if event == "[DONE]":
                    continue
                chunk = json.loads(event)
                now = time.perf_counter_ns()
                choices = chunk.get("choices") or []
                if choices:
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    visible = delta.get("content") or ""
                    reasoning = delta.get("reasoning") or delta.get("reasoning_content") or ""
                    if visible or reasoning:
                        if first_token_ns is None:
                            first_token_ns = now
                            record["ttft_ms"] = (now - started) / 1_000_000
                        if prior_token_ns is not None:
                            record["itl_ms"].append((now - prior_token_ns) / 1_000_000)
                        prior_token_ns = now
                        record["chunk_timestamps_ms"].append((now - started) / 1_000_000)
                        record["visible_text"] += visible
                        record["reasoning_text"] += reasoning
                    if choice.get("finish_reason") is not None:
                        record["finish_reason"] = choice["finish_reason"]
                if chunk.get("usage") is not None:
                    record["usage"] = chunk["usage"]
        record["status"] = "ok"
    except urllib.error.HTTPError as error:
        record["http_status"] = error.code
        record["error"] = error.read().decode("utf-8", errors="replace")[:4000]
    except Exception as error:  # Keep failed attempts as evidence, never silently discard.
        record["error"] = f"{type(error).__name__}: {error}"
    finally:
        record["e2e_ms"] = (time.perf_counter_ns() - started) / 1_000_000
        record["completed_at"] = utc_now()
    return record


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def redacted_container_state() -> dict[str, Any]:
    command = ["docker", "inspect", "qwen38-dflash2-server"]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        return {"error": completed.stderr.strip(), "command": command}
    item = json.loads(completed.stdout)[0]
    env = []
    for entry in item.get("Config", {}).get("Env", []):
        name, _, value = entry.partition("=")
        if any(token in name.upper() for token in ("TOKEN", "KEY", "SECRET", "PASSWORD")):
            value = f"<redacted-sha256:{sha256_bytes(value.encode())[:12]}>"
        env.append(f"{name}={value}")
    return {
        "image": item.get("Config", {}).get("Image"),
        "command": item.get("Config", {}).get("Cmd"),
        "entrypoint": item.get("Config", {}).get("Entrypoint"),
        "env": env,
        "mounts": [{key: mount.get(key) for key in ("Type", "Source", "Destination", "RW")} for mount in item.get("Mounts", [])],
        "labels": item.get("Config", {}).get("Labels", {}),
    }


def command_preflight(args: argparse.Namespace) -> int:
    manifest_path = PINNED_DIR / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("pinned workload manifest missing; run prepare_publication_workloads.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected in manifest["workloads"].items():
        actual = sha256_path(PINNED_DIR / name)
        if actual != expected["sha256"]:
            raise SystemExit(f"workload hash mismatch: {name}")
    models = api_json(args.base_url, "/v1/models")
    # vLLM's health endpoint may intentionally return an empty body; the HTTP
    # status is the health evidence, rather than assuming it is reachable.
    health = {"status": "http-ok", "checked_at": utc_now()}
    try:
        with urllib.request.urlopen(f"{args.base_url.rstrip('/')}/health", timeout=15) as response:
            health["http_status"] = response.status
    except urllib.error.HTTPError as exc:
        health = {"status": "http-error", "http_status": exc.code, "checked_at": utc_now()}
    except urllib.error.URLError as exc:
        health = {"status": "connection-error", "error": str(exc.reason), "checked_at": utc_now()}
    if health.get("http_status") != 200:
        raise SystemExit(f"server health check failed: {health}")
    snapshot = select_metrics(prometheus_snapshot(args.base_url))
    output = Path(args.run_dir)
    output.mkdir(parents=True, exist_ok=True)
    preflight = {
        "timestamp": utc_now(),
        "manifest": manifest,
        "models": models,
        "health": health,
        "metrics": snapshot,
        "container": redacted_container_state(),
        "base_url": args.base_url,
    }
    write_json(output / "preflight.json", preflight)
    print(output / "preflight.json")
    return 0


def command_run(args: argparse.Namespace) -> int:
    workload_path = Path(args.workload)
    samples = load_jsonl(workload_path)
    if args.limit:
        samples = samples[: args.limit]
    if not samples:
        raise SystemExit("no workload samples selected")
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    # Workload is part of the filename and request ID namespace.  A serving
    # phase runs code and ShareGPT with the same matrix coordinates, so omitting
    # it would overwrite raw evidence from the first workload.
    run_label = f"{samples[0]['workload']}-{args.mode}-{args.thinking}-c{args.concurrency}-r{args.repeat}"
    # Warm-up is deliberately isolated from snapshots and raw evidence.
    request_stream(args.base_url, args.model, samples[0], args.thinking == "on", f"warmup-{run_label}", 0, args.timeout)
    before = select_metrics(prometheus_snapshot(args.base_url))
    batch_start = time.perf_counter_ns()
    records: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(request_stream, args.base_url, args.model, sample, args.thinking == "on", run_label, 0, args.timeout)
            for sample in samples
        ]
        for future in concurrent.futures.as_completed(futures):
            records.append(future.result())
    batch_e2e_ms = (time.perf_counter_ns() - batch_start) / 1_000_000
    after = select_metrics(prometheus_snapshot(args.base_url))
    # Tokenize output after the measured snapshot. This does not affect generation counters.
    for record in records:
        record["visible_tokens"] = tokenize_count(args.base_url, args.model, record["visible_text"])
        record["reasoning_tokens"] = tokenize_count(args.base_url, args.model, record["reasoning_text"])
        record["token_count_source"] = "server_tokenize_after_metrics_snapshot"
    records.sort(key=lambda record: record["item_id"])
    raw_path = run_dir / f"{run_label}.jsonl"
    with raw_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(stable_json(record) + "\n")
    successful = [record for record in records if record["status"] == "ok"]
    completion_tokens = [int((record.get("usage") or {}).get("completion_tokens") or 0) for record in successful]
    prompt_tokens = [int((record.get("usage") or {}).get("prompt_tokens") or 0) for record in successful]
    e2e = [float(record["e2e_ms"]) for record in successful if record["e2e_ms"] is not None]
    ttft = [float(record["ttft_ms"]) for record in successful if record["ttft_ms"] is not None]
    itl = [value for record in successful for value in record["itl_ms"]]
    visible = [record["visible_tokens"] for record in successful if record["visible_tokens"] is not None]
    reasoning = [record["reasoning_tokens"] for record in successful if record["reasoning_tokens"] is not None]
    summary = {
        "schema_version": 1,
        "run_label": run_label,
        "workload": samples[0]["workload"],
        "workload_hash": sha256_path(workload_path),
        "mode": args.mode,
        "thinking": args.thinking,
        "concurrency": args.concurrency,
        "repeat": args.repeat,
        "sample_count": len(samples),
        "success_count": len(successful),
        "error_count": len(records) - len(successful),
        "raw_path": raw_path.name,
        "batch_e2e_ms": batch_e2e_ms,
        "metrics_before": before,
        "metrics_after": after,
        "metrics_delta": metric_delta(before, after),
        "completion_tokens": sum(completion_tokens),
        "prompt_tokens": sum(prompt_tokens),
        "visible_tokens": sum(visible) if len(visible) == len(successful) else None,
        "reasoning_tokens": sum(reasoning) if len(reasoning) == len(successful) else None,
        "completion_throughput_tok_s": sum(completion_tokens) / (batch_e2e_ms / 1000) if batch_e2e_ms else None,
        "total_throughput_tok_s": (sum(completion_tokens) + sum(prompt_tokens)) / (batch_e2e_ms / 1000) if batch_e2e_ms else None,
        "latency_ms": {"e2e": summarize_values(e2e), "ttft": summarize_values(ttft), "itl": summarize_values(itl)},
        "finish_reasons": dict(Counter(record["finish_reason"] or "missing" for record in records)),
    }
    write_json(run_dir / f"{run_label}.summary.json", summary)
    print(run_dir / f"{run_label}.summary.json")
    return 0 if len(successful) == len(records) else 2


def command_verify(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    raw_files = sorted(run_dir.glob("*.jsonl"))
    if not raw_files:
        failures.append("no raw JSONL files")
    request_ids: set[str] = set()
    for path in raw_files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            row = json.loads(line)
            for field in ("request_id", "item_id", "status", "finish_reason", "usage", "e2e_ms", "ttft_ms"):
                if field not in row:
                    failures.append(f"{path.name}:{number} missing {field}")
            if row.get("request_id") in request_ids:
                failures.append(f"duplicate request_id {row['request_id']}")
            request_ids.add(row.get("request_id"))
            if row.get("status") == "ok" and not row.get("usage"):
                failures.append(f"{path.name}:{number} successful response missing usage")
    result = {"timestamp": utc_now(), "raw_files": [path.name for path in raw_files], "request_ids": len(request_ids), "failures": failures}
    write_json(run_dir / "verification.json", result)
    print(run_dir / "verification.json")
    return 0 if not failures else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base-url", default="http://127.0.0.1:18089")
    common.add_argument("--model", default="qwen3.8-27b-nvfp4-dflash2")
    common.add_argument("--run-dir", required=True)
    preflight = subparsers.add_parser("preflight", parents=[common])
    preflight.set_defaults(func=command_preflight)
    run = subparsers.add_parser("run", parents=[common])
    run.add_argument("--workload", required=True)
    run.add_argument("--mode", choices=("dflash", "baseline"), required=True)
    run.add_argument("--thinking", choices=("off", "on"), required=True)
    run.add_argument("--concurrency", type=int, choices=(1, 2, 4), required=True)
    run.add_argument("--repeat", type=int, choices=(0, 1, 2), required=True)
    run.add_argument("--limit", type=int)
    run.add_argument("--timeout", type=int, default=600)
    run.set_defaults(func=command_run)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--run-dir", required=True)
    verify.set_defaults(func=command_verify)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
