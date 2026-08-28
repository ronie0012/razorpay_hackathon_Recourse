# Live provider validation

Validated on 2026-08-27/28 using only provider Test Mode and sanitized artifacts.

## OpenRouter

- Model: `liquid/lfm-2.5-2.6b:free`
- Schema and evidence gate: passed
- Fallback used: no
- Resolved evidence references: 2
- Raw model output and credentials persisted: no

Machine-readable proof: `evals/results/live-openrouter-validation.json`.

## Razorpay

- Mode: Razorpay Test Mode; no real money moved
- Payment Link: `plink_TUrnotNBGf6Je8`
- Amount: INR 4,999.00
- Notifications and reminders: disabled
- Failure path: provider rejected an international test card before payment
- Success path: domestic Test Mode card completed through the mock OTP flow
- Successful Test Mode payment: `pay_TV6cNjT4R03WHw`
- Provider GET status: `paid`
- Local terminal state after reconciliation: `RECOVERED`
- Provider-delivered webhook claimed: no

The local outcome proof is signed and reduced only after the live provider GET reports `paid`. It proves provider reconciliation and state-machine behavior, but it is not represented as a provider-delivered webhook.

Machine-readable proof: `evals/results/live-razorpay-validation.json`.
