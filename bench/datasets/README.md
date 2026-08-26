# Publication benchmark datasets

Raw snapshots are intentionally ignored because they are large. The benchmark
manifest records their hashes and derives small, pinned workload manifests.

- ShareGPT: `anon8231489123/ShareGPT_Vicuna_unfiltered` at revision
  `192ab2185289094fc556ec8ce5ce1e8e587154ca`.
- LongBench v2: `THUDM/LongBench-v2` at revision
  `2b48e494f2c7a2f0af81aae178e05c7e1dde0fe9`.
- IFEval: `google-research/google-research` input data at commit
  `26d8ccdab6fec61b5c83ad6327ea8bda9e580288`.

Use `publication_bench.py fetch` to download and verify them.
