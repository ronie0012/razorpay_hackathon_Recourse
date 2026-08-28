# Final Frozen Evaluation

**DEVELOPMENT OUTPUT — SYNTHETIC FROZEN BENCHMARK**

These generated results validate the synthetic evaluation pipeline. They are not claims of production uplift.

| Variant | Cases | Incremental net value (subunits) | Mean regret | Macro Brier | Review rate | Violations |
|---|---:|---:|---:|---:|---:|---:|
| Rules | 60 | 6090621 | 123802.5667 | N/A | 0.00% | 0 |
| Single model | 60 | 0 | 225312.9167 | 0.1953632858 | 0.00% | 0 |
| Full RECOURSE | 60 | 6347272 | 119525.05 | 0.1926379824 | 8.33% | 0 |
| Oracle | 60 | 13518775 | 0 | N/A | 0.00% | 0 |

## Integrity

- Frozen dataset SHA-256: `84d827c599b5e9ed7645777b1c6c7a8be4725339fc226b32de14c48e38397558`
- Model manifest SHA-256: `23c07c392f86dbe85eb7d5681d4f3ccf35188b0ee004139bdfe2f44daf508cb3`
- Policy SHA-256: `c59492acca56f23043a80971d1a235808d018cdf317e98db27e78f7e8a3203fa`
- Per-case artifact SHA-256: `a271005628cb168feda5f8ae534b1509dddf8b6328cbcb42cc15a54fc8d0c099`

The JSON report contains denominators, per-arm Brier scores, reliability-bin counts, regret distribution, seeded bootstrap intervals, and no-action confusion counts.

## Honest failure analysis

Case `case_syn_002014` incurred 863372 subunits of regret because the policy selected `STANDARD_PAYMENT_LINK` while the evaluator-only oracle selected `RETRY_LATER`.
