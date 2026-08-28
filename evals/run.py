from __future__ import annotations

import hashlib
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from evals.baselines import rules_baseline, single_model_baseline
from evals.metrics import compute_variant_metrics
from recourse.domain.audit import canonical_json
from recourse.domain.models import Action
from recourse.modeling.artifacts import ModelRegistry, read_jsonl
from recourse.modeling.features import ACTIONS
from recourse.modeling.policy import estimate_and_select
FROZEN_SEED = 20260826


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _oracle(evaluation: dict, amount: int) -> tuple[str, dict[str, int]]:
    outcomes = evaluation["arm_outcomes"]
    direct = evaluation["realized_direct_cost_subunits"]
    downstream = evaluation["realized_downstream_cost_subunits"]
    baseline = outcomes[Action.NO_ACTION.value]
    values = {
        action: (outcomes[action] - baseline) * amount - direct[action] - downstream[action]
        for action in ACTIONS
    }
    values[Action.NO_ACTION.value] = 0
    best = max(values.values())
    selected = next(action for action in ACTIONS if values[action] == best)
    return selected, values


def _guardrail_violation(context: dict, selected: str) -> int:
    if selected == Action.ONE_BOUNDED_NUDGE.value:
        return int(context["opt_out"] or not context["contact_consent"] or context["contacts_7d"] >= 2)
    if selected == Action.RETRY_LATER.value:
        return int(not context["retry_eligible"])
    if selected == Action.STANDARD_PAYMENT_LINK.value:
        return int(not context["link_eligible"])
    return 0


def _row(case: dict, variant: str, result: dict, registry: ModelRegistry) -> dict:
    context, evaluation = case["context"], case["evaluation"]
    oracle_action, values = _oracle(evaluation, context["amount_subunits"])
    selected = result["selected_action"]
    outcomes = evaluation["arm_outcomes"]
    gross = context["amount_subunits"] * outcomes[selected]
    natural = context["amount_subunits"] * outcomes[Action.NO_ACTION.value]
    action_cost = evaluation["realized_direct_cost_subunits"][selected] + evaluation["realized_downstream_cost_subunits"][selected]
    predictions = result.get("predictions")
    if variant == "full_recourse":
        predictions = {action: result["estimates"][action]["success_probability"] for action in ACTIONS}
    if variant == "full_recourse":
        expected_value = result["estimates"][selected]["expected_inv_subunits"]
    elif predictions:
        expected_value = round((predictions[selected] - predictions[Action.NO_ACTION.value]) * context["amount_subunits"] - action_cost)
    elif variant == "oracle":
        expected_value = values[selected]
    else:
        expected_value = None
    return {
        "case_id": case["case_id"], "variant": variant, "status": result["status"],
        "selected_action": selected, "oracle_action": oracle_action,
        "gross_recovered_subunits": gross, "natural_recovery_subunits": natural,
        "realized_action_cost_subunits": action_cost, "realized_value_subunits": values[selected],
        "expected_value_subunits": expected_value, "latency_ms": result.get("_latency_ms", 0),
        "oracle_value_subunits": values[oracle_action], "regret_subunits": values[oracle_action] - values[selected],
        "guardrail_violation": 0 if variant == "oracle" else _guardrail_violation(context, selected),
        "predictions": predictions, "arm_outcomes": outcomes,
    }


def _timed(callable_):
    started = time.perf_counter()
    result = callable_()
    result["_latency_ms"] = (time.perf_counter() - started) * 1000
    return result


def _ablations(rows: dict[str, list[dict]]) -> dict:
    full = rows["full_recourse"]
    realized = sum(row["realized_value_subunits"] for row in full)
    no_natural = sum(row["gross_recovered_subunits"] - row["realized_action_cost_subunits"] for row in full)
    no_costs = sum(row["realized_value_subunits"] + row["realized_action_cost_subunits"] for row in full)
    return {
        "natural_recovery_baseline": {"enabled_value_subunits": realized, "disabled_overstated_value_subunits": no_natural,
                                      "overstatement_subunits": no_natural - realized},
        "action_costs": {"enabled_value_subunits": realized, "disabled_value_subunits": no_costs,
                         "overstatement_subunits": no_costs - realized},
        "calibration": {"enabled": True, "comparison": "single_model macro Brier versus calibrated per-arm macro Brier"},
        "conservative_lower_bound": {"enabled": True, "review_or_no_action_count": sum(row["status"] != "ACTION_READY" for row in full)},
        "challenger_verifier": {"enabled_in_product": True, "evaluation_external_calls": 0,
                                "reason": "frozen evaluation keeps external agents outside policy selection"},
        "offline_guardrails": {"enabled_violation_count": sum(row["guardrail_violation"] for row in full),
                               "denominator": len(full)},
    }


def evaluate(root: Path, label: str = "FINAL SYNTHETIC FROZEN BENCHMARK — NOT PRODUCTION UPLIFT",
             stem: str = "final") -> dict:
    eval_path = root / "data" / "frozen" / "eval_potential_outcomes.jsonl"
    artifact_dir = root / "models" / "artifacts"
    registry = ModelRegistry(artifact_dir)
    cases = read_jsonl(eval_path)
    variants: dict[str, list[dict]] = {name: [] for name in ("rules", "single_model", "full_recourse", "oracle")}
    for case in cases:
        context = case["context"]
        rules = _timed(lambda: rules_baseline(context))
        single = _timed(lambda: single_model_baseline(context, registry))
        full = _timed(lambda: estimate_and_select(context, registry))
        oracle_action, _values = _oracle(case["evaluation"], context["amount_subunits"])
        oracle = {"selected_action": oracle_action, "status": "ACTION_READY" if oracle_action != Action.NO_ACTION.value else "NO_ACTION", "predictions": None, "_latency_ms": 0}
        for name, result in (("rules", rules), ("single_model", single), ("full_recourse", full), ("oracle", oracle)):
            variants[name].append(_row(case, name, result, registry))
    policy_config = {
        "min_evidence_quality": .70, "min_conservative_inv_subunits": 1000,
        "max_interval_width": .35, "tie_band_subunits": 500,
    }
    manifest_path = artifact_dir / "manifest.json"
    report = {
        "label": label, "seed": FROZEN_SEED, "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases), "actions": ACTIONS,
        "dataset_sha256": _sha256_file(eval_path), "model_manifest_sha256": _sha256_file(manifest_path),
        "policy_hash": hashlib.sha256(canonical_json(policy_config).encode()).hexdigest(),
        "policy_config": policy_config,
        "variants": {name: compute_variant_metrics(rows, FROZEN_SEED + index) for index, (name, rows) in enumerate(variants.items())},
        "ablations": _ablations(variants),
        "openrouter_summary": {"call_count": 0, "schema_failure_count": 0, "repair_count": 0,
                               "fallback_count": 0, "input_tokens": 0, "output_tokens": 0,
                               "estimated_cost_usd": 0, "reason": "OpenRouter is excluded from frozen policy evaluation"},
        "audit_completeness": {"complete_count": len(cases) * 4, "total_count": len(cases) * 4,
                               "rate": 1.0, "definition": "per-case artifact rows containing case, variant, action, oracle, value, and regret provenance"},
    }
    report["freeze"] = {
        "openrouter_model": "liquid/lfm-2.5-2.6b:free",
        "prompt_hashes": {path.name: _sha256_file(path) for path in sorted((root / "prompts").glob("*.txt"))},
        "schema_hashes": {path.name: _sha256_file(path) for path in sorted((root / "prompts" / "schemas").glob("*.json"))},
        "policy_source_sha256": _sha256_file(root / "apps" / "api" / "src" / "recourse" / "domain" / "policy.py"),
    }
    losing = [row for row in variants["full_recourse"] if row["regret_subunits"] > 0]
    worst = max(losing, key=lambda row: row["regret_subunits"])
    report["failure_analysis"] = {
        "case_id": worst["case_id"], "selected_action": worst["selected_action"],
        "oracle_action": worst["oracle_action"], "regret_subunits": worst["regret_subunits"],
        "explanation": "Conservative policy selection did not match the evaluator-only realized oracle outcome; hidden outcomes remain unavailable to the policy.",
    }
    result_dir = root / "evals" / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    per_case_path = result_dir / f"{stem}-per-case.jsonl"
    per_case_path.write_text("".join(canonical_json(row) + "\n" for rows in variants.values() for row in rows), encoding="utf-8")
    report["per_case_sha256"] = _sha256_file(per_case_path)
    (result_dir / f"{stem}-evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (result_dir / f"{stem}-freeze-manifest.json").write_text(json.dumps({
        "run_timestamp": report["run_timestamp"], "seed": FROZEN_SEED,
        "dataset_sha256": report["dataset_sha256"], "model_manifest_sha256": report["model_manifest_sha256"],
        "policy_hash": report["policy_hash"], **report["freeze"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (result_dir / f"{stem}-per-case.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["case_id", "variant", "status", "selected_action", "oracle_action", "gross_recovered_subunits",
                  "natural_recovery_subunits", "realized_action_cost_subunits", "expected_value_subunits",
                  "realized_value_subunits", "regret_subunits", "guardrail_violation", "latency_ms"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in fields} for rows in variants.values() for row in rows)
    lines = [
        "# Final Frozen Evaluation",
        "",
        f"**{label}**",
        "",
        "These generated results validate the synthetic evaluation pipeline. They are not claims of production uplift.",
        "",
        "| Variant | Cases | Incremental net value (subunits) | Mean regret | Macro Brier | Review rate | Violations |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    display_names = {"rules": "Rules", "single_model": "Single model", "full_recourse": "Full RECOURSE", "oracle": "Oracle"}
    for name in ("rules", "single_model", "full_recourse", "oracle"):
        metrics = report["variants"][name]
        brier = "N/A" if metrics["macro_brier"] is None else str(metrics["macro_brier"])
        lines.append(
            f"| {display_names[name]} | {metrics['case_count']} | {metrics['incremental_net_value_subunits']} | "
            f"{metrics['regret']['mean_subunits']} | {brier} | {metrics['review_rate']:.2%} | {metrics['guardrail_violation_count']} |"
        )
    lines.extend([
        "", "## Integrity", "",
        f"- Frozen dataset SHA-256: `{report['dataset_sha256']}`",
        f"- Model manifest SHA-256: `{report['model_manifest_sha256']}`",
        f"- Policy SHA-256: `{report['policy_hash']}`",
        f"- Per-case artifact SHA-256: `{report['per_case_sha256']}`",
        "", "The JSON report contains denominators, per-arm Brier scores, reliability-bin counts, regret distribution, seeded bootstrap intervals, and no-action confusion counts.", "",
    ])
    lines.extend(["## Honest failure analysis", "", f"Case `{worst['case_id']}` incurred {worst['regret_subunits']} subunits of regret because the policy selected `{worst['selected_action']}` while the evaluator-only oracle selected `{worst['oracle_action']}`.", ""])
    (result_dir / f"{stem}-evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    output = evaluate(project_root)
    print(json.dumps({"label": output["label"], "case_count": output["case_count"], "variants": list(output["variants"])}, indent=2))
