from fabric_agents.contracts import load
from fabric_agents.demo import run


def test_full_scripted_acceptance(tmp_path):
    result = run(tmp_path / "demo")
    report = load(result["details"])
    assert report["primary_key_failure_caught"]
    assert report["review_concurrency_failure_caught"]
    assert report["rerun_created_no_delta_versions"]
    assert not report["ai_agents_invoked"]
    assert not report["external_services_called"]
    assert report["final_state"] == "READY_FOR_HUMAN"
    assert {t["name"]: (t["current_rows"], t["history_rows"]) for t in report["data"]} == {
        "members": (3, 4), "point_events": (4, 4), "tiers": (2, 2)}
