from pathlib import Path

from recourse.modeling.artifacts import train_models
FROZEN_SEED = 20260826


root = Path(__file__).resolve().parents[1]
manifest = train_models(root / "data" / "frozen" / "train_logged.jsonl", root / "models" / "artifacts", FROZEN_SEED)
print(f"Trained {len(manifest['arms'])} calibrated arm models and one single-model baseline.")
