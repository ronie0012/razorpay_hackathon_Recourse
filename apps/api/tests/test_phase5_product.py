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
