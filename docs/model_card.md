# RECOURSE model card

## Intended use

The models rank four bounded recovery actions for synthetic or Razorpay Test Mode payment failures: `NO_ACTION`, `RETRY_LATER`, `STANDARD_PAYMENT_LINK`, and `ONE_BOUNDED_NUDGE`. They are decision support for a demo-safe policy, not authorization to charge, contact, or infer sensitive traits.

## Statistical models

One transparent logistic model is trained per action with clipped inverse-propensity weights. Each arm is calibrated separately and returns a point probability plus an uncertainty interval. A single-success-model baseline and rules baseline are retained for comparison. The frozen evaluator alone can access potential outcomes.

- Dataset seed: `20260826`
- Training rows: 2,000 logged synthetic cases
- Frozen evaluation rows: 60 cases
- Features: 29 pre-decision operational fields
- Artifact manifest: `models/artifacts/manifest.json`
- Calibration: per-arm logistic calibration

## Generative models

OpenRouter is used only for structured diagnosis and adversarial challenge. The live-validated pinned slug is `liquid/lfm-2.5-2.6b:free`. Both calls use temperature zero, versioned prompts and schemas, bounded tokens, one repair attempt, evidence-ID validation, and deterministic fallbacks. The model cannot choose or execute an action.

## Evaluation

The final synthetic benchmark reports value, costs, ROI, regret, calibration, `NO_ACTION` confusion counts, review/abstain rates, guardrail violations, artifact completeness, and latency with denominators. Full RECOURSE currently records 0/60 guardrail violations and a 0.1926 macro Brier score. See `evals/results/final-evaluation.md`.

## Limitations

- All training and evaluation data are synthetic; results are not production uplift claims.
- Hidden potential outcomes make the oracle evaluator-only and unavailable in deployment.
- Calibration and policy thresholds require revalidation before any production use.
- Provider health, issuer state, and customer intent are deliberately treated as unknown unless explicitly observed.
- The system supports INR Test Mode demonstration, not production money movement.
