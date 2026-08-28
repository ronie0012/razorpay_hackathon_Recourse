# Security and hardening notes

## Execution boundary

OpenRouter can return diagnosis and challenge JSON only. Schema validation, evidence-ID resolution, stored-fact verification, deterministic policy, signed commands, Test Mode checks, and database uniqueness all run before an adapter can execute. Decision Surgery sets external adapters to false and does not persist or execute its cloned decision.

## Provider safety

- The Razorpay adapter accepts only key IDs beginning with `rzp_test_`; there is no live-key override.
- Razorpay and fixture webhooks use different secrets and routes.
- Signatures are computed over the untouched request body and compared in constant time.
- Payment Links preserve amount/currency, disable notifications and reminders, and use one stable reference per decision.
- Ambiguous creates reconcile by reference instead of blindly retrying.
- Duplicate and reversed outcome events cannot regress `RECOVERED` or count recovery twice.

## Generated checks

`scripts/harden.py` verifies model and evaluation hashes, scans source for credential shapes and unfinished markers, checks project dependency presence, records shared Python-environment consistency, and validates npm lock integrity. The current npm advisory result contains zero vulnerabilities at every severity and is saved in `evals/results/npm-audit.json`.

The shared host reports an unrelated `pandas-ta`/NumPy constraint through `pip check`; `pandas-ta` is not a RECOURSE dependency. The project dependency set is present and versioned in the hardening report. A clean project virtual environment remains the authoritative packaging check.

## Data limitations

All judge cases and the frozen benchmark are synthetic. Customer references are HMAC pseudonyms, secrets and raw model output are excluded from telemetry, and evaluation-only potential outcomes cannot be imported by application inference code.
