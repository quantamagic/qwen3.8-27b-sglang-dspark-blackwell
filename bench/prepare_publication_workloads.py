#!/usr/bin/env python3
"""Create deterministic, small workload manifests from pinned raw snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CODE_PROMPTS = [
    "Implement an LRU cache in Python with O(1) get and put. Return only code.",
    "Write a TypeScript function that validates a webhook signature using HMAC-SHA256 and timing-safe comparison. Return only code.",
    "Implement a Go worker pool with context cancellation, bounded concurrency, and ordered result collection. Return only code.",
    "Write a Rust parser for a simple key=value configuration format, with useful error messages. Return only code.",
    "Implement a Python async retry helper with exponential backoff, jitter, and a retryable exception predicate. Return only code.",
    "Write a SQL migration and a PostgreSQL query for idempotent event ingestion using a unique event id. Return only code.",
]


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def code_rows() -> list[dict]:
    return [
        {
            "id": f"code-{index:02d}",
            "workload": "code",
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": 1024,
        }
        for index, prompt in enumerate(CODE_PROMPTS, start=1)
    ]


def sharegpt_rows(source: Path, limit: int) -> list[dict]:
    data = json.loads(source.read_text(encoding="utf-8"))
    candidates = []
    for item in data:
        turns = item.get("conversations", [])
        if len(turns) < 2 or turns[0].get("from") != "human" or turns[1].get("from") != "gpt":
            continue
        prompt, reference = turns[0].get("value", ""), turns[1].get("value", "")
        if 200 <= len(prompt) <= 8000 and 1000 <= len(reference) <= 6000:
            candidates.append((item["id"], prompt, reference))
    if len(candidates) < limit:
        raise ValueError(f"only {len(candidates)} ShareGPT candidates; expected {limit}")
    rows = []
    stride = max(1, len(candidates) // limit)
    for index in range(limit):
        item_id, prompt, reference = candidates[index * stride]
        rows.append(
            {
                "id": f"sharegpt-{index:03d}-{item_id}",
                "source_id": item_id,
                "workload": "sharegpt",
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": min(1024, max(256, len(reference) // 3)),
                "reference_chars": len(reference),
            }
        )
    return rows


def longbench_rows(source: Path, label: str, lower: int, upper: int, limit: int) -> list[dict]:
    data = json.loads(source.read_text(encoding="utf-8"))
    candidates = [item for item in data if lower <= len(item["context"]) < upper]
    by_domain: dict[str, list[dict]] = {}
    for item in candidates:
        by_domain.setdefault(item["domain"], []).append(item)
    rows = []
    domains = sorted(by_domain)
    while domains and len(rows) < limit:
        next_domains = []
        for domain in domains:
            if len(rows) >= limit:
                break
            item = by_domain[domain].pop(0)
            choices = "\n".join(
                f"{letter}. {item[f'choice_{letter}']}" for letter in "ABCD"
            )
            prompt = (
                "Read the context and answer the multiple-choice question. "
                "Reply with only A, B, C, or D.\n\n"
                f"CONTEXT:\n{item['context']}\n\nQUESTION:\n{item['question']}\n\nCHOICES:\n{choices}\n\nANSWER:"
            )
            rows.append(
                {
                    "id": f"longbench-{label}-{item['_id']}",
                    "source_id": item["_id"],
                    "workload": f"longbench_{label}",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_completion_tokens": 32,
                    "expected_answer": item["answer"],
                    "domain": item["domain"],
                    "context_chars": len(item["context"]),
                }
            )
            if by_domain[domain]:
                next_domains.append(domain)
        domains = next_domains
    if len(rows) != limit:
        raise ValueError(f"only selected {len(rows)} {label} LongBench rows; expected {limit}")
    return rows


def ifeval_rows(source: Path) -> list[dict]:
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        rows.append(
            {
                "id": f"ifeval-{item['key']}",
                "source_id": item["key"],
                "workload": "ifeval",
                "messages": [{"role": "user", "content": item["prompt"]}],
                "max_completion_tokens": 2048,
                "instruction_id_list": item["instruction_id_list"],
                "kwargs": item["kwargs"],
            }
        )
    return rows


def main() -> None:
    bench_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=bench_dir / "datasets/raw")
    parser.add_argument("--output-dir", type=Path, default=bench_dir / "datasets/pinned")
    parser.add_argument("--sharegpt-count", type=int, default=48)
    parser.add_argument("--longbench-count", type=int, default=24)
    args = parser.parse_args()
    raw = args.raw_dir
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    sources = {
        "sharegpt": raw / "sharegpt.json",
        "longbench_v2": raw / "longbench_v2.json",
        "ifeval": raw / "ifeval_input.jsonl",
    }
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        raise SystemExit(f"missing pinned raw snapshots: {', '.join(missing)}")
    workloads = {
        "code.jsonl": code_rows(),
        "sharegpt.jsonl": sharegpt_rows(sources["sharegpt"], args.sharegpt_count),
        "longbench_32k.jsonl": longbench_rows(sources["longbench_v2"], "32k", 80_000, 160_000, args.longbench_count),
        "longbench_64k.jsonl": longbench_rows(sources["longbench_v2"], "64k", 160_000, 300_000, args.longbench_count),
        "ifeval.jsonl": ifeval_rows(sources["ifeval"]),
    }
    for name, rows in workloads.items():
        write_jsonl(output / name, rows)
    manifest = {
        "schema_version": 1,
        "source_sha256": {name: digest(path) for name, path in sources.items()},
        "workloads": {
            name: {"count": len(rows), "sha256": digest(output / name)}
            for name, rows in workloads.items()
        },
        "longbench_character_windows": {"32k": [80_000, 160_000], "64k": [160_000, 300_000]},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
