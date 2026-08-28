from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from recourse.main import app

ROOT = Path(__file__).resolve().parents[1]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*, reset: bool, fixture_flow: bool, verify_audit: bool, verify_eval: bool) -> dict:
    with TestClient(app) as client:
        assert client.get("/health/live").json()["status"] == "ok"
        ready = client.get("/health/ready").json()
        assert ready["database"] == "ok"
        if reset:
            seeded = client.post("/api/v1/demo/reset").json()
            assert seeded["reset"] is True and seeded["count"] == 4
            case_id = seeded["case_ids"][0]
        else:
            injected = client.post("/api/v1/demo/webhooks/hero-payment-failed").json()
            case_id = injected["case_id"]

        analysis = client.post(f"/api/v1/cases/{case_id}/analyze").json()
        assert len(analysis["futures"]) == 4
        assert analysis["decision"]["selected_action"] == "STANDARD_PAYMENT_LINK"
        surgery = client.post(f"/api/v1/cases/{case_id}/surgery", json={"amount_subunits": 5000}).json()
        assert surgery["after"]["status"] == "NO_ACTION"
        assert surgery["external_adapters_enabled"] is False

        if fixture_flow:
            execution = client.post(f"/api/v1/cases/{case_id}/execute").json()
            assert execution.get("state") == "LINK_ISSUED" or execution["reason"] == "DUPLICATE_ACTION"
            paid = client.post("/api/v1/demo/webhooks/hero-payment-link-paid").json()
            duplicate = client.post("/api/v1/demo/webhooks/hero-payment-link-paid").json()
            assert paid["state"] == duplicate["state"] == "RECOVERED"
            assert duplicate["created"] is False

        if verify_audit:
            audit = client.get(f"/api/v1/cases/{case_id}/audit").json()
            assert [row["sequence"] for row in audit] == list(range(1, len(audit) + 1))
            replay = client.get(f"/api/v1/cases/{case_id}/replay").json()
            assert replay["chain_valid"] is True and replay["event_count"] == len(audit)

        if verify_eval:
            evaluation = client.get("/api/v1/evaluation").json()
            assert evaluation["case_count"] == 60 and evaluation["artifact_file"] == "final-evaluation.json"
            per_case = ROOT / "evals" / "results" / "final-per-case.jsonl"
            assert evaluation["per_case_sha256"] == file_sha(per_case)

        return {"case_id": case_id, "decision": analysis["decision"]["selected_action"],
                "state": client.get(f"/api/v1/cases/{case_id}").json()["state"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the complete submission smoke contract")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--fixture-flow", action="store_true")
    parser.add_argument("--verify-audit", action="store_true")
    parser.add_argument("--verify-eval", action="store_true")
    args = parser.parse_args()
    selected = any(vars(args).values())
    result = run(
        reset=args.reset or not selected, fixture_flow=args.fixture_flow or not selected,
        verify_audit=args.verify_audit or not selected, verify_eval=args.verify_eval or not selected,
    )
    print(json.dumps({"status": "passed", **result}, indent=2))
