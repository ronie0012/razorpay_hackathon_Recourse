def test_reset_twice_seeds_four_judge_cases_without_duplicates(client):
    first = client.post("/api/v1/demo/reset")
    second = client.post("/api/v1/demo/reset")
    assert first.status_code == second.status_code == 200
    assert first.json()["count"] == second.json()["count"] == 4
    cases = client.get("/api/v1/cases").json()
    assert len(cases) == 4
    by_payment = {case["payment_id"]: case for case in cases}
    assert by_payment["pay_test_low_value_001"]["state"] == "NO_ACTION"
    assert by_payment["pay_test_uncertain_001"]["state"] == "HUMAN_REVIEW"
    assert all(case["recoverable_value_subunits"] is not None for case in cases)
    assert cases == sorted(cases, key=lambda item: (item["priority_score"], item["amount_subunits"]), reverse=True)


def test_decision_surgery_flips_hero_without_external_adapters(client):
    reset = client.post("/api/v1/demo/reset").json()
    hero_id = reset["case_ids"][0]
    result = client.post(f"/api/v1/cases/{hero_id}/surgery", json={"amount_subunits": 5000}).json()
    assert result["before"]["status"] == "ACTION_READY"
    assert result["after"]["status"] == "NO_ACTION"
    assert result["external_adapters_enabled"] is False
    assert result["simulation_only"] is True
    assert result["original_input_hash"] != result["cloned_input_hash"]
    assert len(result["decision_hash"]) == 64


def test_evaluation_lab_is_backed_by_final_generated_artifact(client):
    report = client.get("/api/v1/evaluation")
    assert report.status_code == 200
    body = report.json()
    assert body["artifact_file"] == "final-evaluation.json"
    assert body["case_count"] == 60
    assert set(body["variants"]) == {"rules", "single_model", "full_recourse", "oracle"}
    assert body["variants"]["full_recourse"]["guardrail_evaluation_count"] == 60
    assert body["failure_analysis"]["regret_subunits"] > 0


def test_guided_journey_runs_fresh_failure_to_signed_recovery(client):
    first = client.post("/api/v1/demo/journeys/failure")
    second = client.post("/api/v1/demo/journeys/failure")
    assert first.status_code == second.status_code == 200
    started = first.json()
    assert started["case_id"] != second.json()["case_id"]
    assert started["mode_label"] == "SIGNED GUIDED DEMO — NO REAL MONEY"

    case_id = started["case_id"]
    detail = client.get(f"/api/v1/cases/{case_id}").json()
    assert detail["state"] == "NORMALIZED"
    assert detail["case"]["order_id"] == started["order_id"]
    assert detail["case"]["source"] == "fixture"

    analysis = client.post(f"/api/v1/cases/{case_id}/analyze")
    assert analysis.status_code == 200
    assert analysis.json()["decision"]["selected_action"] == "STANDARD_PAYMENT_LINK"
    assert client.post(f"/api/v1/cases/{case_id}/execute").json()["executed"] is True

    execution = client.get(f"/api/v1/cases/{case_id}/execution").json()
    assert execution["issued"] is True
    assert execution["action"] == "STANDARD_PAYMENT_LINK"
    recovered = client.post(f"/api/v1/demo/journeys/{case_id}/paid").json()
    assert recovered["state"] == "RECOVERED"
    duplicate = client.post(f"/api/v1/demo/journeys/{case_id}/paid").json()
    assert duplicate["created"] is False
    assert client.get(f"/api/v1/cases/{case_id}").json()["state"] == "RECOVERED"
