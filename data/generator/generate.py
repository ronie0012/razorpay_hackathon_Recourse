from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from recourse.domain.audit import canonical_json
from recourse.domain.models import Action
from recourse.modeling.features import ACTIONS, CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES, action_costs

GENERATOR_VERSION = "synthetic-dgp-v1"
FROZEN_SEED = 20260826
TRAIN_SIZE = 2000
FAMILY_COUNTS = {
    "retry_recoverable": 20,
    "method_friction": 15,
    "negative_value": 10,
    "nudge_responsive": 10,
    "uncertain": 5,
}
FORBIDDEN_TOKENS = ("oracle", "potential", "future")
FORBIDDEN_FIELDS = {"case_family", "arm_outcomes", "arm_probabilities", "realized_outcomes"}


def _stable_uniform(seed: int, *parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, (seed, *parts))).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def _choose(rng: random.Random, values: list[Any], weights: list[float] | None = None):
    return rng.choices(values, weights=weights, k=1)[0]


def _context(rng: random.Random, case_id: str, family: str, index: int) -> dict[str, Any]:
    profiles = {
        "retry_recoverable": ("card", "incorrect_otp", "payment_authentication", "soft", 1),
        "method_friction": ("card", "instrument_not_supported", "payment_method", "friction", 1),
        "negative_value": ("card", "customer_cancelled", "payment_authentication", "low_intent", 1),
        "nudge_responsive": ("upi", "payment_timed_out", "payment_confirmation", "soft", 1),
        "uncertain": ("unknown", "unknown", "unknown", "unknown", 2),
    }
    method, reason, step, issuer, attempts = profiles[family]
    low_value = family == "negative_value"
    amount = rng.randint(500, 12_000) if low_value else rng.randint(25_000, 900_000)
    decision_at = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(minutes=index * 7)
    contacts = rng.randint(0, 1) if family == "nudge_responsive" else rng.randint(0, 3)
    consent = family == "nudge_responsive" or rng.random() > .18
    opt_out = family == "negative_value" and rng.random() < .25
    conflicting = family == "uncertain"
    completeness = rng.uniform(.35, .64) if conflicting else rng.uniform(.78, .99)
    return {
        "row_id": "syn_" + hashlib.sha256(case_id.encode()).hexdigest()[:20],
        "decision_at": decision_at.isoformat(),
        "feature_available_at": (decision_at - timedelta(seconds=2)).isoformat(),
        "amount_subunits": amount,
        "method": method,
        "attempt_count": attempts,
        "hour": decision_at.hour,
        "day_of_week": decision_at.weekday(),
        "failure_code": "BAD_REQUEST_ERROR" if issuer != "unknown" else "UNKNOWN_ERROR",
        "failure_source": "customer" if family in {"retry_recoverable", "negative_value"} else "gateway",
        "failure_step": step,
        "failure_reason": reason,
        "merchant_category": _choose(rng, ["retail", "services", "digital_goods", "travel"]),
        "recovery_bucket": _choose(rng, ["low", "medium", "high"], [2, 5, 3]),
        "configured_methods": _choose(rng, ["card_upi", "card_netbanking", "all_standard"]),
        "prior_failures": rng.randint(0, 4),
        "prior_recoveries": rng.randint(0, 3),
        "contacts_7d": contacts,
        "opt_out": opt_out,
        "contact_consent": consent,
        "checkout_duration_bucket": _choose(rng, ["short", "medium", "long"]),
        "method_switches": rng.randint(0, 3) if family == "method_friction" else rng.randint(0, 1),
        "last_interaction_age_bucket": _choose(rng, ["fresh", "recent", "stale"]),
        "friction_signal": "high" if family in {"method_friction", "nudge_responsive"} else "low",
        "network_degradation": "high" if family == "retry_recoverable" and rng.random() < .45 else "none",
        "issuer_response_family": issuer,
        "evidence_completeness": round(completeness, 6),
        "conflicting_signal": conflicting,
        "alternate_method_available": family == "method_friction" or rng.random() > .25,
        "retry_eligible": attempts < 2 and family != "negative_value",
        "link_eligible": True,
        "nudge_eligible": consent and not opt_out and contacts < 2,
    }


def _probabilities(context: dict[str, Any], family: str) -> dict[str, float]:
    amount_rupees = context["amount_subunits"] / 100
    history = .18 * context["prior_recoveries"] - .10 * context["prior_failures"]
    intent = .45 if context["last_interaction_age_bucket"] == "fresh" else (-.35 if family == "negative_value" else 0)
    amount_effect = -.18 if amount_rupees > 5000 else .12
    base_logit = -1.45 + history + intent + amount_effect
    shifts = {
        Action.NO_ACTION.value: 0,
        Action.RETRY_LATER.value: 1.45 * (family == "retry_recoverable") - .9 * (context["attempt_count"] >= 2),
        Action.STANDARD_PAYMENT_LINK.value: 1.65 * (family == "method_friction") + .45 * context["alternate_method_available"] - .7 * (family == "negative_value"),
        Action.ONE_BOUNDED_NUDGE.value: 1.35 * (family == "nudge_responsive") - 1.1 * (context["contacts_7d"] >= 2) - 1.5 * context["opt_out"],
    }
    return {action: round(min(.97, max(.02, _sigmoid(base_logit + shift))), 8) for action, shift in shifts.items()}


def _behavior_policy(family: str, context: dict[str, Any]) -> dict[str, float]:
    weights = {
        Action.NO_ACTION.value: 1.3,
        Action.RETRY_LATER.value: 3.2 if family == "retry_recoverable" else 1,
        Action.STANDARD_PAYMENT_LINK.value: 3.0 if family == "method_friction" else 1.2,
        Action.ONE_BOUNDED_NUDGE.value: 2.5 if family == "nudge_responsive" and context["nudge_eligible"] else .55,
    }
    total = sum(weights.values())
    return {action: weight / total for action, weight in weights.items()}


def _sample_action(seed: int, case_id: str, propensities: dict[str, float]) -> str:
    draw = _stable_uniform(seed, case_id, "behavior")
    cumulative = 0.0
    for action in ACTIONS:
        cumulative += propensities[action]
        if draw <= cumulative:
            return action
    return ACTIONS[-1]


def generate_case(seed: int, index: int, family: str) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = f"case_syn_{index:06d}"
    rng = random.Random(int(hashlib.sha256(f"{seed}|{case_id}".encode()).hexdigest()[:16], 16))
    context = _context(rng, case_id, family, index)
    probabilities = _probabilities(context, family)
    outcomes = {action: int(_stable_uniform(seed, case_id, action, "outcome") < probabilities[action]) for action in ACTIONS}
    direct_costs, downstream_costs = action_costs(context)
    propensities = _behavior_policy(family, context)
    logged_action = _sample_action(seed, case_id, propensities)
    training = {
        **context,
        "logged_action": logged_action,
        "propensity": round(propensities[logged_action], 10),
        "observed_outcome": outcomes[logged_action],
    }
    evaluator = {
        "case_id": case_id,
        "context": context,
        "evaluation": {
            "case_family": family,
            "arm_probabilities": probabilities,
            "arm_outcomes": outcomes,
            "realized_direct_cost_subunits": direct_costs,
            "realized_downstream_cost_subunits": downstream_costs,
        },
    }
    return training, evaluator


def _training_families(rng: random.Random, count: int) -> list[str]:
    names = list(FAMILY_COUNTS)
    weights = list(FAMILY_COUNTS.values())
    return rng.choices(names, weights=weights, k=count)


def generate_datasets(seed: int = FROZEN_SEED, train_size: int = TRAIN_SIZE) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    training = [generate_case(seed, index, family)[0] for index, family in enumerate(_training_families(rng, train_size))]
    families = [family for family, count in FAMILY_COUNTS.items() for _ in range(count)]
    evaluation = [generate_case(seed, train_size + index, family)[1] for index, family in enumerate(families)]
    return training, evaluation


def jsonl_bytes(rows: Iterable[dict]) -> bytes:
    return ("".join(canonical_json(row) + "\n" for row in rows)).encode()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_datasets(root: Path, seed: int = FROZEN_SEED, train_size: int = TRAIN_SIZE) -> dict[str, str]:
    training, evaluation = generate_datasets(seed, train_size)
    train_path = root / "data" / "frozen" / "train_logged.jsonl"
    eval_path = root / "data" / "frozen" / "eval_potential_outcomes.jsonl"
    train_path.parent.mkdir(parents=True, exist_ok=True)
    payloads = {train_path: jsonl_bytes(training), eval_path: jsonl_bytes(evaluation)}
    for path, content in payloads.items():
        path.write_bytes(content)
    checksums = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "train_rows": len(training),
        "evaluation_rows": len(evaluation),
        "train_logged_sha256": sha256_bytes(payloads[train_path]),
        "eval_potential_outcomes_sha256": sha256_bytes(payloads[eval_path]),
        "evaluation_family_counts": dict(Counter(row["evaluation"]["case_family"] for row in evaluation)),
    }
    (root / "data" / "checksums.json").write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return checksums


def validate_training_row(row: dict[str, Any]) -> None:
    forbidden = [
        key for key in row
        if key in FORBIDDEN_FIELDS or any(token in key.lower() for token in FORBIDDEN_TOKENS)
        or ("outcome" in key.lower() and key != "observed_outcome")
    ]
    if forbidden:
        raise ValueError(f"evaluation-only fields found in training row: {forbidden}")
    missing = sorted(set(FEATURE_COLUMNS) - row.keys())
    if missing:
        raise ValueError(f"required features missing: {missing}")
    if datetime.fromisoformat(row["feature_available_at"]) > datetime.fromisoformat(row["decision_at"]):
        raise ValueError("feature became available after decision_at")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
