from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import Pipeline

from recourse.domain.models import Action
from recourse.modeling.features import ACTIONS, FEATURE_COLUMNS

FROZEN_SEED = 20260826
FORBIDDEN_TOKENS = ("oracle", "potential", "future")
FORBIDDEN_FIELDS = {"case_family", "arm_outcomes", "arm_probabilities", "realized_outcomes"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


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
    from datetime import datetime
    if datetime.fromisoformat(row["feature_available_at"]) > datetime.fromisoformat(row["decision_at"]):
        raise ValueError("feature became available after decision_at")

ARTIFACT_VERSION = "per-arm-logistic-platt-v1"
UNCERTAINTY_MARGIN = 0.10


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _semantic_sha256(model: CalibratedBinaryModel) -> str:
    estimator = model.pipeline.named_steps["model"]
    vectorizer = model.pipeline.named_steps["vectorizer"]
    payload = {
        "feature_names": model.feature_names,
        "uncertainty_margin": model.uncertainty_margin,
        "vocabulary": sorted(vectorizer.vocabulary_.items()),
        "estimator_classes": estimator.classes_.tolist(),
        "estimator_coef": estimator.coef_.tolist(),
        "estimator_intercept": estimator.intercept_.tolist(),
        "calibrator_classes": model.calibrator.classes_.tolist(),
        "calibrator_coef": model.calibrator.coef_.tolist(),
        "calibrator_intercept": model.calibrator.intercept_.tolist(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _features(row: dict[str, Any], candidate_action: str | None = None) -> dict[str, Any]:
    result = {name: row[name] for name in FEATURE_COLUMNS}
    if candidate_action is not None:
        result["candidate_action"] = candidate_action
    return result


def _split(rows: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    train, calibration = [], []
    for row in rows:
        bucket = int(hashlib.sha256(f"{row['row_id']}|calibration".encode()).hexdigest()[:8], 16) % 5
        (calibration if bucket == 0 else train).append(row)
    if not train or not calibration:
        raise ValueError("deterministic train/calibration split is empty")
    return train, calibration


def _weights(rows: list[dict]) -> np.ndarray:
    return np.asarray([min(1 / float(row["propensity"]), 10.0) for row in rows], dtype=float)


def _effective_sample_size(weights: np.ndarray) -> float:
    return float(weights.sum() ** 2 / np.square(weights).sum())


def _base_pipeline(seed: int) -> Pipeline:
    return Pipeline([
        ("vectorizer", DictVectorizer(sparse=True, sort=True)),
        ("model", LogisticRegression(max_iter=1000, random_state=seed, solver="liblinear")),
    ])


@dataclass
class CalibratedBinaryModel:
    pipeline: Pipeline
    calibrator: LogisticRegression
    feature_names: list[str]
    uncertainty_margin: float = UNCERTAINTY_MARGIN

    def predict(self, context: dict[str, Any], candidate_action: str | None = None) -> tuple[float, float, float]:
        missing = sorted(set(self.feature_names) - context.keys())
        if missing:
            raise ValueError(f"required inference features missing: {missing}")
        features = {name: context[name] for name in self.feature_names}
        if candidate_action is not None:
            features["candidate_action"] = candidate_action
        raw = float(self.pipeline.predict_proba([features])[0, 1])
        point = float(self.calibrator.predict_proba(np.asarray([[raw]]))[0, 1])
        return point, max(0.0, point - self.uncertainty_margin), min(1.0, point + self.uncertainty_margin)


def _reliability(predictions: np.ndarray, outcomes: np.ndarray, bins: int = 5) -> list[dict[str, Any]]:
    result = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        mask = (predictions >= low) & ((predictions < high) if index < bins - 1 else (predictions <= high))
        count = int(mask.sum())
        if not count:
            result.append({"bin": index, "count": 0, "mean_prediction": None, "observed_frequency": None})
            continue
        result.append({
            "bin": index, "count": count,
            "mean_prediction": round(float(predictions[mask].mean()), 8),
            "observed_frequency": round(float(outcomes[mask].mean()), 8),
        })
    return result


def _fit(rows: list[dict], seed: int, *, include_action: bool = False) -> tuple[CalibratedBinaryModel, dict]:
    train, calibration = _split(rows)
    train_x = [_features(row, row["logged_action"] if include_action else None) for row in train]
    train_y = np.asarray([row["observed_outcome"] for row in train], dtype=int)
    weights = _weights(train)
    if len(set(train_y.tolist())) < 2:
        raise ValueError("training partition must contain both outcome classes")
    pipeline = _base_pipeline(seed)
    pipeline.fit(train_x, train_y, model__sample_weight=weights)
    calibration_x = [_features(row, row["logged_action"] if include_action else None) for row in calibration]
    calibration_y = np.asarray([row["observed_outcome"] for row in calibration], dtype=int)
    if len(set(calibration_y.tolist())) < 2:
        raise ValueError("calibration partition must contain both outcome classes")
    raw = pipeline.predict_proba(calibration_x)[:, 1]
    calibrator = LogisticRegression(random_state=seed, solver="liblinear")
    calibrator.fit(raw.reshape(-1, 1), calibration_y, sample_weight=_weights(calibration))
    calibrated = calibrator.predict_proba(raw.reshape(-1, 1))[:, 1]
    model = CalibratedBinaryModel(pipeline, calibrator, list(FEATURE_COLUMNS))
    metrics = {
        "training_rows": len(train),
        "calibration_rows": len(calibration),
        "brier_score": round(float(brier_score_loss(calibration_y, calibrated)), 10),
        "effective_sample_size": round(_effective_sample_size(weights), 4),
        "max_inverse_propensity_weight": round(float(weights.max()), 6),
        "reliability_bins": _reliability(calibrated, calibration_y),
    }
    return model, metrics


def train_models(train_path: Path, artifact_dir: Path, seed: int = FROZEN_SEED) -> dict[str, Any]:
    rows = read_jsonl(train_path)
    for row in rows:
        validate_training_row(row)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Any] = {}
    for action in ACTIONS:
        arm_rows = [row for row in rows if row["logged_action"] == action]
        model, metrics = _fit(arm_rows, seed)
        filename = f"arm-{action.lower()}.joblib"
        path = artifact_dir / filename
        joblib.dump(model, path, compress=3)
        artifacts[action] = {"file": filename, "sha256": _sha256_file(path), "semantic_sha256": _semantic_sha256(model), "metrics": metrics}
    single_model, single_metrics = _fit(rows, seed, include_action=True)
    single_path = artifact_dir / "single-success-model.joblib"
    joblib.dump(single_model, single_path, compress=3)
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "seed": seed,
        "training_file": train_path.name,
        "training_sha256": _sha256_file(train_path),
        "feature_columns": FEATURE_COLUMNS,
        "evaluation_data_used": False,
        "weighting": {"method": "inverse_propensity", "cap": 10.0},
        "calibration": {"method": "per-arm Platt", "split": "stable row hash modulo 5", "uncertainty_margin": UNCERTAINTY_MARGIN},
        "library_versions": {
            "python": platform.python_version(), "numpy": np.__version__,
            "scikit_learn": sklearn.__version__, "joblib": joblib.__version__,
        },
        "arms": artifacts,
        "single_model": {"file": single_path.name, "sha256": _sha256_file(single_path), "semantic_sha256": _semantic_sha256(single_model), "metrics": single_metrics},
    }
    manifest_path = artifact_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


class ModelRegistry:
    def __init__(self, artifact_dir: Path):
        self.artifact_dir = artifact_dir
        self.manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
        self.arms: dict[str, CalibratedBinaryModel] = {}
        for action, metadata in self.manifest["arms"].items():
            path = artifact_dir / metadata["file"]
            if _sha256_file(path) != metadata["sha256"]:
                raise ValueError(f"artifact hash mismatch for {action}")
            self.arms[action] = joblib.load(path)
        single_meta = self.manifest["single_model"]
        single_path = artifact_dir / single_meta["file"]
        if _sha256_file(single_path) != single_meta["sha256"]:
            raise ValueError("artifact hash mismatch for single success model")
        self.single: CalibratedBinaryModel = joblib.load(single_path)

    def predict_all(self, context: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
        return {action: self.arms[action].predict(context) for action in ACTIONS}

    def predict_single_all(self, context: dict[str, Any]) -> dict[str, float]:
        return {action: self.single.predict(context, candidate_action=action)[0] for action in ACTIONS}
