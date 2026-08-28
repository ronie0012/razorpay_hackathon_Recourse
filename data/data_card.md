# RECOURSE Synthetic Benchmark Data Card

**Label:** SYNTHETIC FROZEN BENCHMARK  
**Generator:** `synthetic-dgp-v1`  
**Frozen seed:** `20260826`

## Purpose and permitted claims

This benchmark tests whether the implementation can learn and evaluate a bounded recovery policy when complete synthetic potential outcomes are available to an evaluator. It proves implementation and evaluation mechanics only. It is not customer data and is not evidence of production causal uplift, merchant revenue, or customer behavior.

## Splits

- `train_logged.jsonl`: 2,000 contexts. Each row exposes one behavior-policy action, its propensity, and its observed binary outcome.
- `eval_potential_outcomes.jsonl`: exactly 60 evaluator-only cases containing every arm outcome. Application and model-training modules never import this file.
- Frozen composition: 20 retry-recoverable, 15 method-friction, 10 negative-value, 10 nudge-responsive, and 5 uncertain/contradictory cases.

## Observable features

The model receives bounded payment, merchant-bucket, pseudonymous history, session, synthetic network, and governance fields listed in the model manifest. It receives no protected attributes, exact location, free-form personal data, family labels, oracle actions, unlogged outcomes, or post-decision fields.

## Data-generating assumptions

Natural recovery starts from a documented logit using amount band, synthetic intent, and pseudonymous recovery/failure history. Arm shifts are benchmark assumptions:

- retry: `+1.45` for retry-recoverable failures and `-0.90` when attempts are exhausted;
- Standard Payment Link: `+1.65` for method friction, `+0.45` when an alternate method exists, and `-0.70` for low-intent cases;
- bounded nudge: `+1.35` for nudge-responsive cases, `-1.10` under contact saturation, and `-1.50` after opt-out.

Each `(seed, case_id, arm)` uses a stable SHA-256-derived uniform draw. Logged actions come from a deliberately biased behavior policy. Training uses inverse-propensity weights capped at 10.

## Costs and uncertainty

Direct action costs are 0, 600, 3,800, and 1,600 currency subunits for no action, retry, Payment Link, and nudge. Downstream costs are documented generator proxies, including a contact-saturation penalty for nudges. Each calibrated point estimate receives a fixed ±0.10 Phase 2 uncertainty margin; execution uses the lower action bound minus the upper no-action bound. This approximation must be replaced or justified before production use.

## Leakage controls

- Feature availability timestamps must not exceed `decision_at`.
- Training rows are rejected when field names contain evaluator-only tokens.
- Stable row IDs are hashes and encode neither family nor oracle action.
- Training accepts only the logged dataset path; evaluator-only imports live under `evals/`.
- Dataset, model, per-case, and policy hashes are recorded before metrics are produced.

## Limitations

The coefficient choices, costs, behavior policy, and outcomes are synthetic. The frozen set has only 60 cases. Metrics therefore demonstrate reproducibility and policy mechanics, not statistical significance or deployable commercial impact. Results must remain labeled development output until the policy is formally frozen.

