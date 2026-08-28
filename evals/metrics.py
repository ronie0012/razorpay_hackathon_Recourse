from __future__ import annotations

import math
import random
from statistics import mean, median
from typing import Any

from recourse.domain.models import Action
from recourse.modeling.features import ACTIONS


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def reliability_bins(predictions: list[float], outcomes: list[int], count: int = 5) -> list[dict[str, Any]]:
    result = []
    for index in range(count):
        low, high = index / count, (index + 1) / count
        members = [i for i, value in enumerate(predictions) if value >= low and (value < high or index == count - 1)]
        result.append({
            "bin": index, "lower": low, "upper": high, "count": len(members),
            "mean_prediction": round(mean(predictions[i] for i in members), 10) if members else None,
            "observed_frequency": round(mean(outcomes[i] for i in members), 10) if members else None,
        })
    return result


def bootstrap_interval(values: list[int], seed: int, repetitions: int = 500) -> dict[str, Any]:
    rng = random.Random(seed)
    totals = [sum(values[rng.randrange(len(values))] for _ in values) for _ in range(repetitions)]
    return {
        "method": "seeded percentile bootstrap", "repetitions": repetitions,
        "lower_95": round(percentile(totals, .025), 2), "upper_95": round(percentile(totals, .975), 2),
    }


def compute_variant_metrics(rows: list[dict], seed: int) -> dict[str, Any]:
    realized = [row["realized_value_subunits"] for row in rows]
    regret = [row["regret_subunits"] for row in rows]
    gross = sum(row["gross_recovered_subunits"] for row in rows)
    natural = sum(row["natural_recovery_subunits"] for row in rows)
    action_cost = sum(row["realized_action_cost_subunits"] for row in rows)
    chosen_no_action = [row["selected_action"] == Action.NO_ACTION.value for row in rows]
    oracle_no_action = [row["oracle_action"] == Action.NO_ACTION.value for row in rows]
    tp = sum(chosen and oracle for chosen, oracle in zip(chosen_no_action, oracle_no_action))
    fp = sum(chosen and not oracle for chosen, oracle in zip(chosen_no_action, oracle_no_action))
    fn = sum(not chosen and oracle for chosen, oracle in zip(chosen_no_action, oracle_no_action))
    tn = sum(not chosen and not oracle for chosen, oracle in zip(chosen_no_action, oracle_no_action))
    expected = [row["expected_value_subunits"] for row in rows if row.get("expected_value_subunits") is not None]
    latencies = [float(row.get("latency_ms", 0)) for row in rows]
    required = {"case_id", "variant", "selected_action", "oracle_action", "realized_value_subunits", "regret_subunits"}
    complete = sum(required <= set(row) for row in rows)
    metrics: dict[str, Any] = {
        "case_count": len(rows),
        "gross_recovered_subunits": gross,
        "natural_recovery_subunits": natural,
        "incremental_recovered_subunits": gross - natural,
        "incremental_net_value_subunits": sum(realized),
        "realized_incremental_net_value_subunits": sum(realized),
        "expected_incremental_net_value_subunits": sum(expected) if expected else None,
        "expected_value_case_count": len(expected),
        "mean_incremental_net_value_subunits": round(mean(realized), 4),
        "total_action_cost_subunits": action_cost,
        "recovery_roi": round((gross - natural) / max(action_cost, 1), 8),
        "regret": {
            "mean_subunits": round(mean(regret), 4), "median_subunits": round(median(regret), 4),
            "p90_subunits": round(percentile(regret, .9), 4), "total_subunits": sum(regret),
            "oracle_match_count": sum(row["selected_action"] == row["oracle_action"] for row in rows),
            "oracle_match_rate": round(sum(row["selected_action"] == row["oracle_action"] for row in rows) / len(rows), 8),
        },
        "no_action": {
            "true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn,
            "precision": round(tp / max(tp + fp, 1), 8), "recall": round(tp / max(tp + fn, 1), 8),
        },
        "review_count": sum(row["status"] in {"HUMAN_REVIEW", "ABSTAIN"} for row in rows),
        "review_rate": round(sum(row["status"] in {"HUMAN_REVIEW", "ABSTAIN"} for row in rows) / len(rows), 8),
        "automatic_action_count": sum(row["selected_action"] != Action.NO_ACTION.value for row in rows),
        "guardrail_violation_count": sum(row["guardrail_violation"] for row in rows),
        "guardrail_evaluation_count": len(rows),
        "guardrail_violation_rate": round(sum(row["guardrail_violation"] for row in rows) / len(rows), 8),
        "abstain_count": sum(row["status"] == "ABSTAIN" for row in rows),
        "abstain_rate": round(sum(row["status"] == "ABSTAIN" for row in rows) / len(rows), 8),
        "artifact_completeness": {"complete_count": complete, "total_count": len(rows), "rate": round(complete / len(rows), 8)},
        "latency_ms": {"median": round(median(latencies), 6), "p95": round(percentile(latencies, .95), 6), "count": len(latencies)},
        "incremental_net_value_interval": bootstrap_interval(realized, seed),
    }
    prediction_rows = [row for row in rows if row.get("predictions")]
    if prediction_rows:
        brier = {}
        bins = {}
        for action in ACTIONS:
            predictions = [float(row["predictions"][action]) for row in prediction_rows]
            outcomes = [int(row["arm_outcomes"][action]) for row in prediction_rows]
            brier[action] = round(mean((p - y) ** 2 for p, y in zip(predictions, outcomes)), 10)
            bins[action] = reliability_bins(predictions, outcomes)
        metrics["brier_by_arm"] = brier
        metrics["macro_brier"] = round(mean(brier.values()), 10)
        metrics["reliability_bins"] = bins
    else:
        metrics["brier_by_arm"] = None
        metrics["macro_brier"] = None
        metrics["reliability_bins"] = None
    return metrics
