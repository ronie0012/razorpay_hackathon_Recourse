# Five-minute submission demo script

Target runtime: **4:45**. Record at 1080p. Keep the persistent `TEST MODE · NO REAL MONEY` banner visible.

## 0:00–0:35 — Problem and thesis

“Failed-payment automation often optimizes conversion without asking whether recovery would have happened naturally. RECOURSE compares every intervention with `NO_ACTION`, challenges its own recommendation, and executes only when conservative incremental value and safety agree. Razorpay is in Test Mode and every evaluation case is synthetic.”

## 0:35–1:15 — Recovery Inbox

Choose **Reset judge demo**. Point out prioritized failed amount, conservative recoverable value, source labels, four seeded cases, and zero safety violations.

## 1:15–2:35 — Hero recovery

Open `pay_test_hero_001`. Show cited evidence, known unknowns, four future cards, natural-recovery baseline, cost, uncertainty, expected value, conservative value, challenger verdict, verifier counts, and policy guardrails. Execute the Standard Payment Link. If live Razorpay is unavailable, say “This is the signed fixture replay through the identical domain path,” and keep the fixture label visible. Expand the audit chain.

## 2:35–3:05 — Refusal

Return to the inbox and open `pay_test_low_value_001`. Show that the policy selects `NO_ACTION` because conservative value does not clear the threshold. Briefly mention the opt-out and uncertain-review cases.

## 3:05–3:40 — Decision Surgery

Return to the hero and open Decision Surgery. Change the amount to `5000`, recompute, and show the flip to `NO_ACTION`, the new decision hash, and `External adapters enabled: false`.

## 3:40–4:25 — Evaluation Lab

Open Evaluation Lab. State: “These are generated results on 60 frozen synthetic cases—not production uplift.” Show all four variants, 0/60 full-RECOURSE guardrail violations, calibration, regret, ablations, hashes, and the honest losing case.

## 4:25–4:45 — Architecture and close

Show `docs/architecture.md`. “Models diagnose and challenge; deterministic code verifies, values, and executes. RECOURSE recovers revenue only when it can defend the action.”

## Rehearsal checklist

- Run the one-command smoke test immediately before recording.
- Rehearse three times and record the durations here: `____`, `____`, `____`.
- Verify microphone, 1080p resolution, browser zoom, fixture/Test Mode labels, and final video audio.
- Open the uploaded video and repository in a signed-out window before submitting.
