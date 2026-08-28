import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from evals.run import evaluate  # noqa: E402


report = evaluate(root)
print(f"{report['label']}: {report['case_count']} cases, {len(report['actions'])} actions, {len(report['variants'])} variants.")
