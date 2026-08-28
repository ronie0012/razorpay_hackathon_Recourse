# RECOURSE — Submission-Ready Build Plan

> Execution plan for turning the existing product blueprint into a polished Razorpay AI Buildathon submission using OpenRouter and Razorpay Test Mode.

**Project:** RECOURSE — Adversarial Counterfactual Revenue Recovery  
**Track:** 03 — AI Revenue Recovery  
**Primary specification:** [`RECOURSE_BUILDATHON_BLUEPRINT.md`](./RECOURSE_BUILDATHON_BLUEPRINT.md)  
**Current repository state (27 August 2026):** specification only; no application code, package manifests, Git repository, tests, data, models, or submission assets exist yet  
**Delivery model:** solo, local-first, demo-safe MVP  
**Recommended time box:** 48 focused hours, with feature freeze at hour 41  
**External services:** OpenRouter API and Razorpay Test Mode only  

---

## 1. Outcome and non-negotiable acceptance criteria

The submission is complete only when a reviewer can run the product from a clean clone, understand the thesis quickly, see a real or explicitly labeled fixture-equivalent Razorpay failure, inspect four counterfactual futures, and observe a deterministic policy either execute one safe Test Mode action or refuse.

The final build must prove all of the following:

- A `payment.failed` Razorpay Test Mode webhook, or a signed fixture with the same normalized contract, creates exactly one case.
- Every diagnosis claim references a valid evidence ID or is marked unknown.
- The system evaluates `NO_ACTION`, `RETRY_LATER`, `STANDARD_PAYMENT_LINK`, and `ONE_BOUNDED_NUDGE`.
- The value engine compares every intervention with natural recovery and computes conservative incremental net value in integer currency subunits.
- OpenRouter may diagnose and challenge, but cannot directly select or execute a Razorpay action.
- Deterministic code enforces evidence, consent, quiet hours, contact limits, attempt limits, uncertainty, positive-value, Test Mode, and duplicate-action gates.
- A Standard Payment Link can be created through Razorpay in Test Mode, with notifications and reminders disabled.
- Duplicate and out-of-order webhooks do not create duplicate cases, links, or state regressions.
- A low-value example ends in `NO_ACTION` and an uncertain example ends in `HUMAN_REVIEW` or `ABSTAIN`.
- Decision Surgery recomputes a cloned decision and never invokes an external provider.
- A frozen 60-case synthetic benchmark reports generated—not fabricated—value, regret, calibration, abstention, and guardrail metrics.
- The demo still works when OpenRouter or Razorpay is unavailable by using visible, integrity-checked fallbacks.
- The public repository contains no secrets, raw customer data, database files, placeholder results, or unverifiable claims.
- The five-minute video shows the complete judge journey and clearly labels Test Mode, fixtures, replays, and synthetic data.

### Definition of “best possible MVP”

For this submission, quality means a narrow product with convincing proof. Do not add live messaging, discounts, automatic charging, multi-tenancy, authentication systems, production deployment, or additional payment products until every acceptance criterion above passes.

---

## 2. Locked technical decisions

Make these choices at project start and change them only if a dependency is genuinely blocked.

| Area | Decision | Reason |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | Fast implementation, explicit contracts, easy model integration |
| Frontend | React, TypeScript, Vite, React Router, TanStack Query | Small, familiar SPA stack with good async-state handling |
| Styling | Tailwind CSS plus a small token file | Fast, consistent demo UI |
| Charts | Recharts | Enough for futures, calibration, and evaluation charts |
| Database | SQLite in WAL mode for the MVP | Zero-service clean-clone experience |
| Statistical models | scikit-learn preprocessing plus transparent per-arm logistic regression first | Reproducible and explainable; upgrade only if metrics justify it |
| Calibration | Per-arm Platt calibration; isotonic only if calibration sample size supports it | Robust on small synthetic data |
| LLM provider | OpenRouter through an internal `StructuredModel` adapter | One controlled integration point and easy deterministic fallback |
| LLM usage | Diagnosis and adversarial challenge only | Generative text stays outside the execution boundary |
| Razorpay usage | Test Mode Standard Payment Links and verified webhooks | Real bounded recovery action without live money |
| Background work | Synchronous request path plus bounded in-process job abstraction | Avoid queue infrastructure during the hackathon |
| Testing | pytest, Hypothesis, Vitest, Playwright | Covers math, invariants, contracts, UI, and end-to-end behavior |
| Package management | Python virtual environment with a committed lock; npm with committed `package-lock.json` | Reproducible clean clone |
| CI | GitHub Actions on Windows or Ubuntu, with no live-provider secrets required | Public, repeatable proof |

### Architecture boundary

```text
untrusted webhook / fixture
        ↓
signature + schema + idempotency
        ↓
canonical case and evidence pack
        ↓
OpenRouter diagnosis → schema validation → evidence-ID resolution
        ↓
four statistical future estimates
        ↓
deterministic value calculation
        ↓
OpenRouter challenge → schema validation → deterministic verification
        ↓
deterministic policy and state machine
        ↓
typed ActionCommand
        ↓
Razorpay Test Mode adapter OR simulated bounded action OR refusal
        ↓
outcome reducer, evaluation, and append-only audit trail
```

No OpenRouter response, browser request, or webhook field can reach the Razorpay adapter without being converted into a typed, policy-approved `ActionCommand`.

---

## 3. Target repository structure

Create this structure during Phase 0. Keep the existing blueprint and use this file as the execution checklist.

```text
Razorpay_hackatohn/
├─ README.md
├─ PLAN.md                              # authoritative blueprint copy
├─ SUBMISSION_BUILD_PLAN.md             # this execution plan
├─ LICENSE
├─ SECURITY.md
├─ .env.example
├─ .gitignore
├─ pyproject.toml                       # shared tooling, or API-local equivalent
├─ package.json                         # optional root task runner
├─ apps/
│  ├─ api/
│  │  ├─ alembic.ini
│  │  ├─ migrations/
│  │  ├─ src/recourse/
│  │  │  ├─ main.py
│  │  │  ├─ config.py
│  │  │  ├─ api/
│  │  │  ├─ domain/
│  │  │  ├─ ingest/
│  │  │  ├─ evidence/
│  │  │  ├─ agents/
│  │  │  │  ├─ provider.py
│  │  │  │  ├─ openrouter.py
│  │  │  │  ├─ diagnose.py
│  │  │  │  ├─ challenge.py
│  │  │  │  └─ fallbacks.py
│  │  │  ├─ simulator/
│  │  │  ├─ verifier/
│  │  │  ├─ execution/
│  │  │  │  ├─ commands.py
│  │  │  │  └─ razorpay.py
│  │  │  ├─ evaluation/
│  │  │  ├─ persistence/
│  │  │  └─ observability/
│  │  └─ tests/
│  └─ web/
│     ├─ src/
│     │  ├─ pages/
│     │  ├─ components/
│     │  ├─ charts/
│     │  ├─ api/
│     │  └─ types/
│     └─ tests/
├─ data/
│  ├─ generator/
│  ├─ fixtures/
│  ├─ frozen/
│  └─ data_card.md
├─ models/
│  ├─ artifacts/
│  └─ manifests/
├─ prompts/
│  ├─ diagnose-v1.txt
│  ├─ challenge-v1.txt
│  └─ schemas/
├─ evals/
│  ├─ baselines.py
│  ├─ metrics.py
│  ├─ run.py
│  └─ results/
├─ scripts/
│  ├─ bootstrap.ps1
│  ├─ seed.py
│  ├─ train.py
│  ├─ evaluate.py
│  ├─ smoke.py
│  ├─ demo_reset.py
│  └─ verify_replay.py
├─ docs/
│  ├─ architecture.md
│  ├─ demo-script.md
│  ├─ model-card.md
│  ├─ evaluation-report.md
│  └─ screenshots/
└─ .github/workflows/ci.yml
```

---

## 4. Credentials and environment setup

### 4.1 Secret-handling rules

- Put actual values only in `.env`; never commit that file.
- Commit `.env.example` with obvious placeholders.
- Never expose `OPENROUTER_API_KEY`, `RAZORPAY_KEY_SECRET`, webhook secrets, or audit secrets to Vite or any `VITE_*` variable.
- The browser may receive the Razorpay Test Mode key ID only when needed for Checkout; it must never receive the key secret.
- Redact authorization headers, webhook signatures, customer contact data, raw LLM output, and raw provider payloads from logs.
- Run a secret scanner before the first push and against full Git history before submission.
- If a key appears in a screenshot, terminal recording, commit, or log, rotate it before submission.

### 4.2 `.env.example` contract

```dotenv
# Application
APP_ENV=development
APP_BASE_URL=http://localhost:5173
API_BASE_URL=http://localhost:8000
DATABASE_URL=sqlite:///./work/recourse.db
DEMO_MODE=true
LOG_LEVEL=INFO
TIMEZONE=Asia/Kolkata

# OpenRouter — server-side only
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=replace_me
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_APP_URL=http://localhost:5173
OPENROUTER_APP_NAME=RECOURSE
DIAGNOSIS_MODEL=replace_with_pinned_model_slug
CHALLENGER_MODEL=replace_with_pinned_model_slug
MODEL_TIMEOUT_SECONDS=8
MODEL_MAX_TRANSPORT_RETRIES=1
MODEL_MAX_SCHEMA_REPAIRS=1
MODEL_TEMPERATURE=0
MODEL_MAX_OUTPUT_TOKENS=800

# Razorpay — Test Mode only
RAZORPAY_KEY_ID=rzp_test_replace_me
RAZORPAY_KEY_SECRET=replace_me
RAZORPAY_WEBHOOK_SECRET=replace_me
RAZORPAY_API_BASE_URL=https://api.razorpay.com
RAZORPAY_REQUIRE_TEST_KEY=true

# Policy
POLICY_VERSION=policy-v1
MIN_EVIDENCE_QUALITY=0.70
MIN_VALUE_CONFIDENCE=0.80
MIN_CONSERVATIVE_INV_SUBUNITS=1000
MAX_INTERVAL_WIDTH=0.35
MAX_INTERVENTIONS_PER_CASE=1
MAX_CONTACTS_7D=2
QUIET_HOURS_START=21:00
QUIET_HOURS_END=09:00
PAYMENT_LINK_TTL_HOURS=24

# Integrity
FIXTURE_SIGNING_SECRET=replace_me
AUDIT_CHAIN_SECRET=replace_me
CUSTOMER_REF_HMAC_SECRET=replace_me
FROZEN_SEED=20260826
```

### 4.3 Startup validation

The API must refuse to start, or explicitly disable the relevant adapter, when:

- `MODEL_PROVIDER=openrouter` but the OpenRouter key or pinned model slug is missing;
- an enabled Razorpay flow has missing credentials;
- `RAZORPAY_REQUIRE_TEST_KEY=true` and `RAZORPAY_KEY_ID` does not begin with `rzp_test_`;
- secrets still equal documented placeholder values outside local fixture mode;
- a database migration is pending;
- a statistical model manifest, feature list, or artifact hash is invalid;
- production mode is requested while `DEMO_MODE=true` or fixture signing is enabled.

The health response must expose capability flags without exposing secrets: database ready, OpenRouter configured, Razorpay Test Mode configured, model artifacts verified, and fixture mode enabled.

---

## 5. OpenRouter implementation plan

OpenRouter is a support component, not the decision-maker. Implement it behind one adapter so model choice and provider behavior cannot leak into the domain or policy layers.

### 5.1 Provider contract

Define an async interface similar to:

```python
class StructuredModel(Protocol):
    async def generate(
        self,
        *,
        schema: dict,
        system_prompt: str,
        input_json: dict,
        timeout_seconds: float,
        request_id: str,
        purpose: Literal["diagnosis", "challenge"],
    ) -> StructuredModelResult: ...
```

`StructuredModelResult` should contain only validated content and operational metadata: provider, exact model slug returned, prompt version, schema version, latency, token usage when available, request ID, fallback status, and a SHA-256 response hash. Do not store hidden reasoning.

### 5.2 Request behavior

- Call OpenRouter only from the backend.
- Use the OpenAI-compatible API under the configured `OPENROUTER_BASE_URL`.
- Prefer a model that currently supports structured outputs and pin its exact model slug in configuration; do not silently use a changing `:free`, `:latest`, or auto-routed model for the recorded evaluation.
- Request JSON Schema structured output when the selected model supports it.
- Set temperature to zero and use small explicit token limits.
- Send only the minimized evidence pack, taxonomy, allowed evidence IDs, and task instructions.
- Attach an internal request ID so audit records can correlate the operation without storing credentials.
- Include the optional application attribution headers only from server configuration.
- Use an eight-second hard deadline for the complete call.
- Retry at most once, and only for a transport error or documented transient status. Use bounded jitter; do not retry schema or policy failures as transport failures.
- Permit at most one schema-repair request. The repair receives the schema error, never new evidence.
- Validate with Pydantic using `extra="forbid"`, enum constraints, bounded list sizes, and probability ranges.
- Resolve every returned evidence ID against the frozen evidence pack.
- Reject out-of-taxonomy diagnoses, unsupported claims, unknown evidence IDs, injected instructions, or prose outside the schema.

### 5.3 Diagnosis task

Input:

- normalized failure fields;
- evidence items containing ID, type, value, source, and timestamp;
- allowed diagnosis taxonomy;
- explicit list of unknown fields;
- prompt and schema version.

Output:

- up to three ranked hypotheses;
- confidence per hypothesis in `[0, 1]`;
- supporting and contradicting evidence IDs;
- unknowns;
- an evidence-quality assessment;
- no proposed payment action.

Fallback: deterministic mapping from Razorpay failure code, source, step, reason, method, and attempt count. Display `Rule-based fallback` in the UI and audit the provider failure reason.

### 5.4 Challenger task

Input:

- selected proposed action;
- value calculation and uncertainty;
- verified evidence only;
- paid/link/contact/attempt states;
- policy limits;
- allowed challenge reason codes.

Output:

- strongest evidence-bound objection;
- cited evidence IDs;
- missing checks;
- severity;
- recommendation limited to `ALLOW_REVIEW`, `BLOCK`, or `REQUEST_HUMAN_REVIEW`.

The recommendation is advisory. Deterministic verification and policy code makes the final decision.

Fallback: a mandatory deterministic checklist covering already paid, existing link, Test Mode, evidence quality, consent, opt-out, quiet hours, contact budget, attempt budget, uncertainty, positive conservative value, provider health, and command idempotency.

### 5.5 Model selection gate

Before freezing the model:

1. Shortlist two compact models available through OpenRouter that advertise structured-output support.
2. Run the same 20 development fixtures five times per model.
3. Measure valid-schema rate, evidence-ID validity, taxonomy validity, p50/p95 latency, token cost, and fallback rate.
4. Reject any candidate with less than 99% post-repair schema validity or any unresolved fabricated evidence ID.
5. Choose one primary pinned model and use the deterministic fallback—not an untested second provider—as the demo safety path.
6. Record the exact slug, evaluation date, prompt hashes, and results in `docs/model-card.md`.
7. Freeze the slugs before the final benchmark and video; model changes invalidate final LLM-related results.

### 5.6 OpenRouter-specific tests

- authorization header and attribution headers are formed server-side;
- key never appears in logs, API responses, snapshots, or frontend bundles;
- timeout triggers deterministic fallback;
- 401 disables LLM calls and returns a clear configuration error;
- 402/credit exhaustion triggers fallback and an operator-visible status;
- 429 and transient 5xx receive no more than one bounded retry;
- invalid JSON and schema violations receive no more than one repair attempt;
- unknown evidence IDs are rejected even when JSON is otherwise valid;
- returned model slug and token usage are audited when present;
- cache key includes full evidence hash, model slug, prompt hash, schema hash, and generation settings;
- cached content is revalidated before use;
- prompt injection inside a webhook field is treated as data and cannot change instructions or tools;
- network-offline mode completes the judge flow with visible fallback labels.

### 5.7 Cost control

- Keep diagnosis and challenge contexts small and purpose-specific.
- Do not send full webhook payloads, audit history, model artifacts, or hidden potential outcomes.
- Cache validated outputs only by immutable input and version hashes.
- Store per-call input/output token counts and estimated cost if available, but do not make cost estimates an execution gate unless the calculation is deterministic and documented.
- Add a per-analysis ceiling of two normal LLM calls plus one possible repair for each task.
- Seed the demo cases and precompute verified replay artifacts so rehearsals do not consume unnecessary credits.

---

## 6. Razorpay Test Mode implementation plan

### 6.1 Safety contract

- Accept only `rzp_test_` key IDs when the Razorpay adapter is enabled.
- Never support a live-key override in the MVP.
- Display a persistent `RAZORPAY TEST MODE — NO REAL MONEY` banner on applicable screens.
- Create Standard Payment Links only; do not promise Test Mode UPI Payment Links.
- Disable `notify` and reminders in provider requests.
- Create at most one active recovery link per case.
- Use the original currency and amount; do not add discounts, fees, instalments, or amount changes.
- Do not automatically charge a stored payment method.

### 6.2 Webhook gateway

Implement `POST /api/v1/webhooks/razorpay` with the following order:

1. Read and retain the raw request body.
2. Validate the Razorpay signature against the raw body using constant-time comparison.
3. Reject missing or invalid signatures with `401`; persist no domain event.
4. Parse JSON only after signature validation.
5. Validate the event envelope and the event-specific fields required by the normalizer.
6. Insert the provider event ID under a unique constraint.
7. Treat duplicate IDs as acknowledged no-ops.
8. Store a redacted, hashed event representation and normalized event.
9. Reduce state using provider event time and explicit state precedence.
10. Queue or run idempotent analysis after the database transaction commits.

Provide a separate signed fixture route or CLI replay path. Fixture signatures must use `FIXTURE_SIGNING_SECRET`, and the UI must display `FIXTURE REPLAY`; never accept fixture signatures on the Razorpay webhook route.

### 6.3 Payment Link execution

The policy produces an immutable `ActionCommand` containing case ID, decision ID, action, amount subunits, currency, expiry, reason codes, policy version, and `sha256(case_id|decision_id|action)` idempotency key.

The adapter must:

- recheck Test Mode, current payment state, current decision state, and absence of an active link inside a transaction;
- persist an execution row in `PENDING_PROVIDER` before the network request;
- construct a stable merchant reference containing the case and decision IDs;
- create the Standard Payment Link with notifications/reminders disabled and a 24-hour expiry;
- store only necessary provider identifiers and a redacted response hash;
- transition to `LINK_ISSUED` once reconciled;
- on an ambiguous timeout, mark `RECONCILING` and query by stable reference instead of blindly creating another link;
- ignore duplicate execution requests using database uniqueness constraints;
- record success, refusal, error, and reconciliation events in the audit chain.

### 6.4 Outcome handling

- Handle at least `payment_link.paid`, cancelled, and expired outcomes, plus `payment.captured` only if used by the implemented flow.
- Verify ownership by reference/notes before associating an outcome with a case.
- A paid terminal state outranks pending, issued, expired, and cancelled states when event time and provider facts prove payment.
- A late non-terminal event must never regress `RECOVERED`.
- Count recovery exactly once.
- Clearly separate observed recovered amount from estimated incremental recovered amount.

### 6.5 Razorpay tests

- valid and invalid HMAC fixtures;
- raw-body signature validation unaffected by JSON formatting;
- duplicate provider event returns success without new rows;
- malformed and unknown events fail safely;
- provider 400, 401, 429, 500, malformed response, and timeout are handled explicitly;
- executing the same decision twice creates no second link;
- ambiguous timeout reconciles by reference;
- paid before issued and issued before paid converge on the same terminal state;
- non-Test key disables adapter startup;
- provider request keeps notifications/reminders disabled;
- fixture and provider webhook secrets cannot be interchanged.

---

## 7. Phased 48-hour implementation schedule

Work on the vertical slice first. Every phase ends with a runnable, testable gate; do not continue merely because the checklist items were typed.

### Phase 0 — Contract, repository, and tooling (H0–H2)

**Build**

- Initialize Git and create the directory structure.
- Copy the existing blueprint to `PLAN.md`; retain `RECOURSE_BUILDATHON_BLUEPRINT.md` for provenance.
- Add `.gitignore`, `.env.example`, `LICENSE`, `SECURITY.md`, and a concise README skeleton.
- Scaffold FastAPI, React/Vite/TypeScript, formatting, linting, type checking, pytest, Vitest, and CI.
- Add dependency lockfiles.
- Freeze action enums, states, reason-code enums, default policy values, and 60-case benchmark family counts.
- Create an issue/checklist item for every phase exit gate and final acceptance criterion.
- Add a `docs/decisions.md` entry recording OpenRouter and Razorpay Test Mode constraints.

**Tests/proof**

- Backend and frontend install from a clean local directory.
- `/health/live` returns success.
- Frontend build renders a shell page.
- CI runs without provider credentials.

**Exit gate**

There is no unresolved decision capable of changing the action set, database identity strategy, core formula, public API, evaluation split, or safety boundary.

### Phase 1 — Deterministic domain vertical slice (H2–H8)

**Build**

- Implement Pydantic domain models from the blueprint: case, evidence, diagnosis, future estimate, challenge, decision, action command, and audit event.
- Create SQLite schema and first Alembic migration with unique constraints for provider events, decisions, and executions.
- Implement state machine and explicit terminal precedence.
- Implement currency-safe uplift, conservative uplift, costs, INV, tie-breaking, and policy selection.
- Implement deterministic guardrails and typed reason codes.
- Build signed fixture ingestion, normalization, evidence-pack generation, and audit hash chaining.
- Expose case list, case detail, analyze, execute-shaped no-op, audit, and health endpoints.
- Render one hero case in a basic Case Workbench using real API data.

**Tests/proof**

- Unit tests cover rounding, all formulas, tie-breaking, and state transitions.
- Hypothesis tests enforce monotonic cost/value properties and one-execution invariants.
- Invalid signatures and schemas create no case.
- Duplicate fixture event is a no-op.
- Every displayed number is recomputable from persisted input fields.

**Exit gate**

One signed fixture travels from ingest through four deterministic future placeholders, value policy, refusal or Payment-Link-shaped command, and audit rendering without any external API.

### Phase 2 — Synthetic data, models, and frozen evaluation (H8–H15)

**Build**

- Implement a seeded data generator with complete potential outcomes retained only in the evaluator.
- Generate a logged training dataset with action propensities and a separate 60-case final frozen set.
- Write `data/data_card.md` describing assumptions, coefficients, limitations, splits, and seed.
- Implement three baselines: rules, single success model, and full per-arm policy; implement evaluator-only oracle.
- Train one transparent model per action with clipped inverse-propensity sample weights.
- Calibrate every arm separately and compute uncertainty intervals.
- Save preprocessing, estimator, calibration, features, library versions, training hash, and metrics in manifests.
- Implement leakage guards that reject evaluation-only columns and post-decision timestamps.
- Produce the first evaluation artifact, but label it development output until policy freeze.

**Tests/proof**

- Same seed produces stable content and hashes.
- Training code cannot import or access frozen potential outcomes.
- All probabilities and intervals are valid.
- Metrics recompute from per-case output.
- Evaluation reports all 60 cases and all four actions.

**Exit gate**

The statistical layer produces calibrated four-arm estimates and conservative values without access to hidden final outcomes; artifact hashes verify on load.

### Phase 3 — OpenRouter agents and independent verification (H15–H21)

**Build**

- Implement `StructuredModel`, the OpenRouter adapter, configuration, timeouts, retry policy, and redacted telemetry.
- Version diagnosis and challenge prompts and JSON schemas.
- Implement deterministic diagnosis and challenge fallbacks first.
- Add diagnosis call, schema validation, taxonomy enforcement, evidence-ID resolution, and unknown handling.
- Add challenger call and deterministic verification of every cited fact.
- Ensure explanations are templates populated from verified stored fields, not free-form model claims.
- Add prompt/model/schema/input hashes to audit records.
- Run the model-selection gate and pin the chosen OpenRouter slug.

**Tests/proof**

- Prompt-injection fixtures cannot alter allowed schema, action set, or tool behavior.
- Fabricated evidence IDs and unsupported diagnoses are rejected.
- Provider timeout, bad JSON, rate limit, and missing credits fall back safely.
- OpenRouter never receives hidden potential outcomes or secrets.
- OpenRouter cannot invoke the execution adapter.

**Exit gate**

Live OpenRouter responses pass schemas and evidence checks; disconnecting the network yields a complete, visibly labeled deterministic path with no unsafe allow.

### Phase 4 — Real Razorpay Test Mode loop (H21–H28)

**Build**

- Implement the Razorpay webhook gateway using raw-body signature verification.
- Normalize `payment.failed` into the canonical case and evidence model.
- Add event dedupe and out-of-order reducer logic.
- Implement Razorpay Test Mode Checkout/Order only as necessary to reliably create a demo failure.
- Implement the Standard Payment Link adapter, reference reconciliation, and one-link-per-case uniqueness.
- Handle `payment_link.paid`, expiry, and cancellation outcomes.
- Create official-shaped signed fixtures for offline demo and automated tests.
- Add persistent Test Mode/fixture/replay labels.

**Tests/proof**

- Complete a real Test Mode failure-to-link-to-paid flow.
- Repeat the flow twice and confirm no duplicate side effects.
- Replay every webhook twice and in reversed order.
- Test ambiguous provider timeout and recovery by stable reference.
- Confirm no live-looking key can enable the adapter.

**Exit gate**

A real Test Mode failure becomes a case, produces a policy-approved Standard Payment Link, receives a paid webhook, and ends in `RECOVERED` exactly once. A verified fixture replay proves the same domain path offline.

### Phase 5 — Judge-facing product surfaces (H28–H35)

**Build**

- Recovery Inbox with prioritized failed amount, recoverable value, status, data-source labels, and seeded judge cases.
- Case Workbench with evidence, diagnosis citations, four future cards, baseline/uplift/cost/uncertainty/INV, challenge, verifier, policy reasons, action control, and audit drawer.
- Decision Surgery with cloned input, allowed mutations, before/after diff, new decision hash, and hard-disabled external adapters.
- Evaluation Lab populated exclusively from generated result artifacts.
- Loading, empty, fallback, invalid-state, provider-down, and reconciliation states.
- Accessible focus, contrast, keyboard navigation, clear currency formatting, and responsive layout at 1280×720 and 1366×768.

**Tests/proof**

- Playwright covers hero recovery, low-value `NO_ACTION`, opt-out block, uncertain review, surgery flip, evaluation metadata, and replay labels.
- Screenshot tests cover all four routes at the demo viewport.
- No workflow needs the developer console or manual database edits.

**Exit gate**

The entire five-minute judge journey works from the UI after one reset command, including provider fallback states.

### Phase 6 — Final evaluation and hardening (H35–H41)

**Build/run**

- Freeze policy configuration, prompts, OpenRouter model slugs, model artifacts, and dataset hashes.
- Run rules, single-model, full RECOURSE, and oracle on the frozen 60 cases.
- Generate per-case JSON/CSV and aggregate report with denominators.
- Run ablations for no-action uplift, costs, calibration, conservative lower bound, challenger/verifier, and offline guardrails.
- Document at least one case where RECOURSE loses to a baseline or oracle.
- Run unit, property, contract, integration, evaluation, frontend, and end-to-end suites.
- Test OpenRouter offline, Razorpay offline, delayed webhook, duplicate webhook, out-of-order webhook, and reset-twice behavior.
- Run secret, dependency, and placeholder scans.
- Verify audit chains and replay hashes.

**Required final metrics**

- gross recovered amount;
- natural recovery amount;
- incremental recovered amount;
- expected and realized incremental net value;
- action costs and ROI;
- mean, median, p90, and total regret;
- oracle-match rate;
- Brier score and reliability bins with counts per arm;
- `NO_ACTION` precision/recall with confusion counts;
- review and abstain rate;
- guardrail violations with numerator and denominator;
- audit completeness;
- median/p95 latency by stage;
- OpenRouter schema failure, repair, fallback, token, and cost summaries.

**Exit gate**

All artifacts contain actual output, seed, run timestamp, dataset/model/prompt/policy hashes, versions, and denominators. There are no `TODO`, `GENERATE`, placeholder hashes, fabricated numbers, or unexplained policy violations.

**Feature freeze begins at H41.** After this point, accept only bug fixes, documentation corrections, and submission packaging.

### Phase 7 — Submission packaging and rehearsal (H41–H48)

**Repository**

- Replace README skeleton with problem, thesis, 60-second quick start, architecture, setup, demo cases, generated results, safety, limitations, and links to documents.
- Complete architecture, model card, data card, evaluation report, security note, and license.
- Add legible screenshots with Test Mode/synthetic labels visible.
- Verify Mermaid diagrams render on the repository host.
- Run setup from a genuinely fresh clone and a new database.
- Confirm the public repository opens in a signed-out browser.
- Record the final commit SHA and artifact hashes.

**Video**

- Use a fixed five-minute script.
- Rehearse at least three times and target 4:40–4:50.
- Record at 1080p with browser zoom adjusted for legibility.
- Show: inbox → hero Test Mode recovery → low-value `NO_ACTION` → Decision Surgery → frozen Evaluation Lab → architecture → closing line.
- Say aloud that Razorpay is in Test Mode and evaluation data is synthetic.
- Keep a verified replay ready but label it honestly if used.
- Test the uploaded video link while signed out.

**Form and integrity**

- Recheck the live official event page for the current deadline, eligibility, track labels, required fields, public-link rules, and video-duration rule.
- Verify repository URL, video URL, architecture link, contact details, and institution details.
- Confirm the video corresponds to the recorded commit.
- Run full-history secret scanning after the final push.
- Capture the submission confirmation.

**Exit gate**

An unfamiliar reviewer can clone, configure, seed, run, and understand the system without private instructions, and every submitted link works while signed out.

---

## 8. Critical path and dependency order

```text
contracts + state machine + formulas
          ↓
fixture vertical slice + database + audit
          ↓
synthetic generator + frozen split + four-arm estimates
          ↓
deterministic policy and commands
          ↓
OpenRouter diagnosis/challenge + verification
          ↓
Razorpay webhook + Payment Link + outcome reducer
          ↓
judge-facing UI + Decision Surgery + Evaluation Lab
          ↓
final frozen run + hardening
          ↓
README + video + public submission
```

Do not begin UI polish before the deterministic fixture flow works. Do not integrate Razorpay before command idempotency and state transitions are tested. Do not run final evaluation before policy, data, prompts, and model slugs are frozen. Do not record the video before reset and offline fallbacks have passed.

---

## 9. API delivery checklist

Implement and document these minimum endpoints under `/api/v1`:

| Method | Route | Purpose | Key safety/idempotency requirement |
|---|---|---|---|
| `POST` | `/webhooks/razorpay` | Receive verified provider events | Raw-body HMAC, unique provider event ID |
| `POST` | `/fixtures/replay` | Replay signed demo fixture | Demo-only, separate secret, prominent label |
| `GET` | `/cases` | Recovery inbox data | Stable filters and pagination |
| `GET` | `/cases/{case_id}` | Full workbench | Evidence, futures, decision, source labels |
| `POST` | `/cases/{case_id}/analyze` | Run diagnosis through policy | Lock on case plus immutable input hash |
| `POST` | `/cases/{case_id}/execute` | Execute approved command | Decision-state and idempotency checks |
| `GET` | `/cases/{case_id}/audit` | Inspect audit chain | Integrity status included |
| `POST` | `/cases/{case_id}/surgery` | Clone, mutate, recompute | External adapters hard-disabled |
| `GET` | `/evaluation/latest` | Read final generated metrics | Return run and artifact hashes |
| `GET` | `/health/live` | Process liveness | No provider dependency |
| `GET` | `/health/ready` | Capability readiness | Sanitized dependency and artifact states |

Use a consistent error envelope with code, message, retryability, request ID, and safe details. Invalid state transitions return `409` and make no change.

---

## 10. Testing matrix and CI gates

### 10.1 Required test layers

| Layer | Minimum proof |
|---|---|
| Unit | Formulas, currency rounding, policy gates, reason codes, state transitions, evidence resolution, hashes |
| Property | Monotonic INV, bounded probabilities, opt-out never enables contact, one execution, surgery no side effects |
| Contract | Razorpay event shapes, provider errors, OpenRouter schema failures, OpenAPI snapshot |
| Integration | Failure-to-decision, link-to-paid, fallback behavior, reconciliation, migrations, reset idempotency |
| Evaluation | Frozen hash, no leakage, 60 terminal decisions, reproducible metrics, explicit denominators |
| Frontend | Component states, currency, labels, accessible actions, API error handling |
| End-to-end | Hero, no-action, opt-out, uncertainty, surgery, evaluation, offline replay |
| Security | Secret scan, dependency scan, invalid HMAC, log redaction, frontend bundle scan |

### 10.2 CI order

```text
format and lint
→ Python and TypeScript type checks
→ unit and property tests
→ contract and integration tests
→ frontend unit tests
→ frozen fixture smoke test
→ evaluation integrity checks
→ secret and dependency scans
→ production frontend build
```

CI must not use real OpenRouter or Razorpay credentials. Provider contract tests use recorded, redacted fixtures or local mocks. Live-provider smoke tests are manual before recording and submission.

### 10.3 One-command smoke test contract

Target command:

```powershell
python ./scripts/smoke.py --reset --fixture-flow --verify-audit --verify-eval
```

It must verify readiness, migration, seed, signed failed fixture, diagnosis/fallback, four futures, deterministic decision, surgery, duplicate no-op, paid fixture, terminal outcome, audit chain, frozen results, hashes, and absence of placeholders.

---

## 11. Demo data and fixed judge cases

Seed and label at least these cases:

| Case | Intended proof | Required outcome |
|---|---|---|
| Hero | Method friction/high-value payment where a Standard Payment Link has positive conservative INV | Approved Test Mode link, then `RECOVERED` |
| Low value | ₹199 or similarly small case where costs exceed uplift | `NO_ACTION` with transparent math |
| Opt-out | Link/nudge may appear valuable, but contact permission is absent or opt-out is true | Nudge blocked; safe alternative or refusal |
| Uncertain | Weak/conflicting evidence or wide interval | `HUMAN_REVIEW` or `ABSTAIN` |
| Duplicate | Same failure and paid events delivered repeatedly | One case, one command, one outcome |
| Out-of-order | Paid/issued events replayed in reverse | Stable `RECOVERED` terminal state |

Every case must display its source as one of `RAZORPAY TEST MODE`, `SIGNED FIXTURE`, `VERIFIED REPLAY`, or `SYNTHETIC EVALUATION`.

---

## 12. UI quality checklist

- The first screen explains the product in one sentence and shows failed amount versus estimated recoverable incremental value.
- The selected action is not presented without the `NO_ACTION` baseline beside it.
- Every future card shows probability, lower/upper interval, uplift, direct cost, downstream cost, and conservative INV.
- The decision panel shows deterministic reason codes and the challenge/verifier result separately.
- Evidence citations are clickable and scroll to the exact evidence item.
- Unknowns and fallbacks are visible, not hidden in tooltips.
- Test Mode, fixture, replay, and synthetic badges use both text and color.
- The execute button is disabled unless the latest decision is executable and still current.
- Reconciliation has its own state; the UI never invites a second click during an ambiguous provider request.
- Decision Surgery has an unmistakable `NO EXTERNAL SIDE EFFECTS` banner.
- Evaluation charts include counts and denominators, not only curves or percentages.
- Error screens say what was preserved and whether retry is safe.
- The main judge flow is legible at 1366×768 without horizontal scrolling.

---

## 13. Observability and audit requirements

For every stage, record request/correlation ID, case ID, input hash, output hash, version, start/end time, duration, status, and safe error code.

Additional fields:

- diagnosis: provider, exact OpenRouter model slug returned, prompt/schema versions, token counts, repair/fallback status;
- models: model/preprocessor/calibrator hashes and feature-manifest version;
- policy: policy version, all gate results, chosen action, rejected actions, values, and reason codes;
- execution: command hash, idempotency key, provider reference, reconciliation status, and redacted response hash;
- webhook: provider event identity, signature-valid flag, dedupe result, event time, normalized hash;
- surgery: parent decision ID, mutation diff, recomputed hashes, and proof external adapters were disabled;
- evaluation: dataset/policy/model/prompt hashes, seed, code commit, and output artifact hash.

Hash chaining is an integrity check, not a blockchain and not proof against a malicious database administrator. Describe it as append-only and tamper-evident within the application model.

---

## 14. Risk-driven fallback plan

| Risk | Prevention | Demo fallback | Never do |
|---|---|---|---|
| OpenRouter timeout/outage | Hard timeout, small prompts, preflight check | Deterministic diagnosis/challenge with badge | Invent a live response |
| OpenRouter credit exhaustion | Budget tracking and precomputed demo cases | Verified replay or fallback | Put key in browser |
| Invalid model JSON | JSON Schema, Pydantic, one repair | Deterministic fallback/abstain | Parse prose heuristically into an action |
| Razorpay API outage | Manual preflight and stable references | Verified replay | Pretend a fixture is live |
| Delayed webhook | Idempotent reducer and one status reconciliation | Verified paid replay | Create a second link |
| Link quota/rehearsal clutter | Track/reuse demo references and reset local state safely | Existing verified Test Mode trace | Delete arbitrary provider resources |
| Model artifact failure | Hash verification at readiness | `ABSTAIN` or verified replay | Use unverified probabilities |
| Frozen data leakage | Separate module and schema, leakage tests | Stop evaluation and fix | Report contaminated metrics |
| Weak metrics | Development diagnostics before freeze | Report honestly and emphasize safety proof | Tune on final oracle outcomes |
| Video overrun | Fixed script and three rehearsals | Cut animations/details | Cut `NO_ACTION`, safety, or disclosure |
| Secret exposure | `.gitignore`, redaction, scanning | Rotate key and rewrite only with deliberate review | Submit exposed credentials |

---

## 15. Submission artifact checklist

### Code and setup

- [ ] Public repository is accessible while signed out.
- [ ] Clean clone installs and starts using README commands.
- [ ] Dependency lockfiles are committed.
- [ ] `.env.example` documents OpenRouter and Razorpay Test Mode variables.
- [ ] No secret or raw customer/provider payload is committed.
- [ ] CI is green at the submitted commit.
- [ ] One-command fixture smoke test passes.
- [ ] License and `SECURITY.md` are present.

### Product proof

- [ ] Real Razorpay Test Mode loop works or verified replay is clearly available.
- [ ] `NO_ACTION`, opt-out, uncertainty, duplicate, and out-of-order cases pass.
- [ ] OpenRouter diagnosis and challenge cite valid evidence.
- [ ] OpenRouter outage produces a safe, labeled fallback.
- [ ] Decision Surgery has no external side effects.
- [ ] Audit-chain verification passes.
- [ ] All source-mode labels are visible.

### Evaluation proof

- [ ] Frozen set contains exactly 60 cases with declared family counts.
- [ ] Dataset, model, prompt, policy, code, and result hashes are recorded.
- [ ] Rules, single-model, full, and oracle results are generated.
- [ ] Expected and realized values are separate.
- [ ] Calibration tables include bin counts.
- [ ] Regret and `NO_ACTION` confusion counts are included.
- [ ] Guardrail violations show numerator and denominator.
- [ ] One honest failure analysis is documented.
- [ ] No placeholder text or invented result remains.

### Documentation and video

- [ ] README communicates the thesis in the first screenful.
- [ ] Architecture diagram renders.
- [ ] Data card, model card, evaluation report, security note, and demo script are complete.
- [ ] Screenshots are legible and correctly labeled.
- [ ] Video is no longer than the current official limit.
- [ ] Test Mode and synthetic-data limitations are spoken and visible.
- [ ] Video link opens signed out.
- [ ] Video matches the recorded commit.

### Final form

- [ ] Current official deadline and eligibility were rechecked on submission day.
- [ ] Correct track is selected.
- [ ] Name, contact, institution, repository, video, and architecture links are correct.
- [ ] Final commit SHA and evaluation hash are saved in submission notes.
- [ ] Submission confirmation is captured.

---

## 16. Scope cuts if behind schedule

Cut in this order:

1. Live OpenRouter challenger; retain the deterministic adversarial checklist.
2. Decorative animation and nonessential charts.
3. Secondary OpenRouter model experiments after one model is pinned.
4. Isotonic calibration or doubly robust estimation; retain transparent calibrated per-arm learners.
5. Hosted deployment; retain a reliable local demo, video, and clean-clone instructions.
6. Optional PDF export or advanced audit visualization.

Never cut:

- the four actions and visible `NO_ACTION` baseline;
- incremental net value and conservative execution rule;
- deterministic safety gates;
- Razorpay Test Mode Standard Payment Link or its verified fallback trace;
- duplicate/out-of-order handling;
- frozen 60-case evaluation and honest metrics;
- audit trail and evidence verification;
- Decision Surgery;
- Test Mode/synthetic/fallback disclosures;
- clean-clone and five-minute-video verification.

---

## 17. Immediate first work session

Complete these in order before expanding scope:

1. Initialize Git and create `PLAN.md` from the existing blueprint.
2. Scaffold `apps/api`, `apps/web`, tests, scripts, CI, and documentation folders.
3. Add `.gitignore` and `.env.example` before entering either API key.
4. Implement domain enums, the integer-subunit value formula, and property tests.
5. Implement the state machine, unique execution constraint, and audit hashing.
6. Add one signed failed-payment fixture and one paid-link fixture.
7. Render one workbench response from the backend.
8. Run the Phase 1 fixture vertically before starting OpenRouter or Razorpay integrations.

The first integration credential to configure should be OpenRouter only after its adapter and log redaction tests exist. Configure Razorpay keys only after raw-body signature verification, idempotency constraints, and the Test Mode key guard are implemented.

---

## 18. Official references to recheck during implementation

These are implementation references, not permission to weaken the local safety contract:

- [OpenRouter API overview](https://openrouter.ai/docs/api-reference/overview)
- [OpenRouter structured outputs](https://openrouter.ai/docs/features/structured-outputs)
- [OpenRouter model catalog](https://openrouter.ai/models)
- [Razorpay Create a Standard Payment Link](https://razorpay.com/docs/api/payments/payment-links/create-standard/)
- [Razorpay webhook validation and testing](https://razorpay.com/docs/webhooks/validate-test/)
- [Razorpay Payment Link webhook events](https://razorpay.com/docs/webhooks/payment-links/)
- [Razorpay Standard Checkout Test Mode integration](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/)
- [Razorpay AI Buildathon](https://razorpay.com/buildathon/)

Because provider features, model availability, limits, event rules, and submission requirements can change, recheck these pages when implementing the adapter and again on submission day. Pin every choice that affects reproducibility in code or an artifact manifest.

---

## Final execution rule

If a task does not strengthen this proof, defer it:

```text
evidence-bound diagnosis
→ four counterfactual futures
→ conservative incremental net value
→ adversarial challenge and independent verification
→ deterministic bounded action or refusal
→ Razorpay Test Mode outcome
→ honest frozen evaluation and replayable audit
```

The project wins on trustworthy decision quality, measurable incremental value, and demo reliability—not on feature count.
