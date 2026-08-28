import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from evals.metrics import compute_variant_metrics
from recourse.modeling.artifacts import ModelRegistry, train_models
from data.generator.generate import FAMILY_COUNTS, FROZEN_SEED, generate_datasets, jsonl_bytes
from recourse.modeling.artifacts import read_jsonl, validate_training_row
from recourse.modeling.features import ACTIONS, FEATURE_COLUMNS


ROOT = Path(__file__).resolve().parents[3]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generator_is_stable_and_frozen_composition_is_exact():
    train_a, eval_a = generate_datasets()
    train_b, eval_b = generate_datasets()
    assert jsonl_bytes(train_a) == jsonl_bytes(train_b)
    assert jsonl_bytes(eval_a) == jsonl_bytes(eval_b)
    assert len(train_a) == 2000
    assert len(eval_a) == 60
    assert Counter(row["evaluation"]["case_family"] for row in eval_a) == FAMILY_COUNTS
    checksums = json.loads((ROOT / "data" / "checksums.json").read_text(encoding="utf-8"))
    assert file_hash(ROOT / "data" / "frozen" / "train_logged.jsonl") == checksums["train_logged_sha256"]
    assert file_hash(ROOT / "data" / "frozen" / "eval_potential_outcomes.jsonl") == checksums["eval_potential_outcomes_sha256"]


def test_training_rows_have_no_hidden_or_post_decision_data():
    rows = read_jsonl(ROOT / "data" / "frozen" / "train_logged.jsonl")
    for row in rows:
        validate_training_row(row)
        assert set(FEATURE_COLUMNS) <= row.keys()
        assert "case_family" not in row
        assert "arm_outcomes" not in row
    recourse_sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "apps" / "api" / "src" / "recourse").rglob("*.py"))
    assert "eval_potential_outcomes.jsonl" not in recourse_sources
    assert "from evals" not in recourse_sources


def test_artifacts_verify_and_predictions_have_valid_bounds():
    registry = ModelRegistry(ROOT / "models" / "artifacts")
    context = read_jsonl(ROOT / "data" / "frozen" / "eval_potential_outcomes.jsonl")[0]["context"]
    predictions = registry.predict_all(context)
    assert set(predictions) == set(ACTIONS)
    for point, lower, upper in predictions.values():
        assert 0 <= lower <= point <= upper <= 1
    with pytest.raises(ValueError, match="required inference features missing"):
        registry.predict_all({key: value for key, value in context.items() if key != FEATURE_COLUMNS[0]})


def test_retraining_is_artifact_hash_stable(tmp_path):
    regenerated = train_models(ROOT / "data" / "frozen" / "train_logged.jsonl", tmp_path, FROZEN_SEED)
    committed = json.loads((ROOT / "models" / "artifacts" / "manifest.json").read_text(encoding="utf-8"))
    assert {action: regenerated["arms"][action]["semantic_sha256"] for action in ACTIONS} == {
        action: committed["arms"][action]["semantic_sha256"] for action in ACTIONS
    }
    assert regenerated["single_model"]["semantic_sha256"] == committed["single_model"]["semantic_sha256"]


def test_evaluation_metrics_recompute_from_all_per_case_rows():
    report = json.loads((ROOT / "evals" / "results" / "development-evaluation.json").read_text(encoding="utf-8"))
    rows = read_jsonl(ROOT / "evals" / "results" / "development-per-case.jsonl")
    assert report["case_count"] == 60
    assert report["actions"] == ACTIONS
    assert len(rows) == 60 * 4
    seeds = {"rules": FROZEN_SEED, "single_model": FROZEN_SEED + 1, "full_recourse": FROZEN_SEED + 2, "oracle": FROZEN_SEED + 3}
    for variant, seed in seeds.items():
        variant_rows = [row for row in rows if row["variant"] == variant]
        assert compute_variant_metrics(variant_rows, seed) == report["variants"][variant]
    assert report["variants"]["full_recourse"]["guardrail_violation_count"] == 0
    assert report["variants"]["full_recourse"]["review_count"] == 5


def test_hash_verification_rejects_tampered_artifact(tmp_path):
    source = ROOT / "models" / "artifacts"
    copied = tmp_path / "artifacts"
    shutil.copytree(source, copied)
    target = copied / "arm-no_action.joblib"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        ModelRegistry(copied)
