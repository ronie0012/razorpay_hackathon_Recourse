import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from data.generator.generate import FROZEN_SEED, TRAIN_SIZE, write_datasets  # noqa: E402


checksums = write_datasets(root, FROZEN_SEED, TRAIN_SIZE)
print(f"Generated {checksums['train_rows']} logged rows and {checksums['evaluation_rows']} frozen evaluation rows.")
print(f"Training SHA-256: {checksums['train_logged_sha256']}")
print(f"Evaluation SHA-256: {checksums['eval_potential_outcomes_sha256']}")
