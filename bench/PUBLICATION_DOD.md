# Definition of Done

- Preflight produces a manifest with verified SHA-256 hashes, pinned item IDs/counts and seeds, model/tokenizer/software/hardware provenance, and redacted resolved server configurations.
- Every required DFlash/baseline matrix cell has three measured repeats at concurrency 1, 2, and 4, with thinking off/on where applicable; failures and omissions remain visible.
- Every request has a schema-valid raw record containing a unique request ID, stable item ID, prompt/config hash, status/retry lineage, finish reason, visible/reasoning token counts, TTFT, TPOT, ITL, E2E, and raw response.
- Summaries recompute prompt/visible/reasoning/combined/total throughput, latency distributions and confidence intervals, reliability, speculative acceptance, prefix-cache deltas, and paired DFlash effects from raw evidence.
- Pinned LongBench v2 32K/64K and IFEval evaluator outputs reproduce the accuracy values in the report.
- Evidence proves paired server configurations differ only in speculative mode and that no unrelated Hermes requests entered measured intervals.
- Independent verification passes schema, hash, cardinality, pairing, counter arithmetic, raw-to-summary, evaluator-to-report, and report-consistency checks.
- The original production service, routing, command/configuration, health, and smoke completion are restored and recorded even after interruption or failure.
