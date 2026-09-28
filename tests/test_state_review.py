from concurrent.futures import ThreadPoolExecutor

import pytest

from fabric_agents.contracts import revision
from fabric_agents.controller import Controller
from fabric_agents.state import StateError, Store


def test_restart_deduplication_and_revision_collision(tmp_path):
    path = tmp_path / "state.sqlite"
    first = Store(path).enqueue("event", "r1")
    assert Store(path).enqueue("event", "r1") == first
    with pytest.raises(StateError):
        Store(path).enqueue("event", "r2")


def test_concurrent_claim_has_one_winner(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    job = store.enqueue("event", "r1")

    def claim(owner):
        try:
            return store.claim(job, owner)
        except StateError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["a", "b"]))
    assert len([r for r in results if r is not None]) == 1


def test_expired_worker_fenced_out(tmp_path):
    clock = [0]
    store = Store(tmp_path / "state.sqlite", clock=lambda: clock[0])
    job = store.enqueue("event", "r1")
    first = store.claim(job, "a", ttl=10)
    clock[0] = 11
    second = store.claim(job, "b", ttl=10)
    assert second > first
    with pytest.raises(StateError):
        store.transition(job, "a", first, "PREPARING")
    with pytest.raises(StateError):
        store.renew(job, "a", first)
    store.transition(job, "b", second, "PREPARING")


def setup_review(tmp_path, config, snapshot, standards):
    store = Store(tmp_path / "state.sqlite")
    job = store.enqueue("event", revision(config, standards))
    fence = store.claim(job, "worker", ttl=600)
    for state in ["PREPARING", "DEVELOPING", "VALIDATING"]:
        store.transition(job, "worker", fence, state)
    controller = Controller(store, tmp_path / "jobs", standards)
    evidence = controller.run_validation(job, "worker", fence, config, snapshot, "2026-01-01T00:00:00Z")
    return store, job, fence, controller, evidence


def begin_review(store, job, fence):
    for state in ["PR_OPEN", "REVIEWING"]:
        store.transition(job, "worker", fence, state)


def test_gate_blocks_direct_approval_and_merge(tmp_path, config, snapshot, standards):
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    begin_review(store, job, fence)
    with pytest.raises(StateError):
        store.transition(job, "worker", fence, "READY_FOR_HUMAN")
    result = controller.review(job, "worker", fence, config, evidence["run_id"])
    assert result["state"] == "READY_FOR_HUMAN" and not result["live_merge_eligible"]
    with pytest.raises(StateError):
        store.transition(job, "worker", fence, "MERGED")


def test_unknown_and_stale_evidence_rejected(tmp_path, config, snapshot, standards):
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    begin_review(store, job, fence)
    with pytest.raises(StateError):
        controller.review(job, "worker", fence, config, "forged-run")
    controller.review(job, "worker", fence, config, evidence["run_id"])
    config["pipeline_concurrency"] = None
    store.revise(job, "worker", fence, revision(config, standards))
    store.transition(job, "worker", fence, "VALIDATING")
    controller.run_validation(job, "worker", fence, config, snapshot, "2026-01-01T00:00:00Z")
    begin_review(store, job, fence)
    with pytest.raises(StateError):
        controller.review(job, "worker", fence, config, evidence["run_id"])


def test_most_recent_failure_invalidates_old_success(tmp_path, config, snapshot, standards):
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    snapshot["members"][0]["member_id"] = None
    failed = controller.run_validation(job, "worker", fence, config, snapshot, "2026-01-02T00:00:00Z")
    begin_review(store, job, fence)
    with pytest.raises(StateError, match="[Mm]ost recent"):
        controller.review(job, "worker", fence, config, evidence["run_id"])
    assert controller.review(job, "worker", fence, config, failed["run_id"])["state"] == "CHANGES_REQUESTED"


def test_concurrency_finding(tmp_path, config, snapshot, standards):
    config["pipeline_concurrency"] = None
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    begin_review(store, job, fence)
    result = controller.review(job, "worker", fence, config, evidence["run_id"])
    assert result["state"] == "CHANGES_REQUESTED"
    assert "pipeline_concurrency" in result["findings"][0]


def test_evidence_export_not_authority(tmp_path, config, snapshot, standards):
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    export = tmp_path / "jobs" / job / "evidence" / f"{evidence['run_id']}.json"
    export.write_text('{"status":"forged"}')
    begin_review(store, job, fence)
    assert controller.review(job, "worker", fence, config, evidence["run_id"])["state"] == "READY_FOR_HUMAN"


def test_review_limit_requires_human_input(tmp_path, config, snapshot, standards):
    config["pipeline_concurrency"] = None
    standards["max_review_cycles"] = 2
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    begin_review(store, job, fence)
    assert controller.review(job, "worker", fence, config, evidence["run_id"])["state"] == "CHANGES_REQUESTED"
    store.revise(job, "worker", fence, revision(config, standards))
    store.transition(job, "worker", fence, "VALIDATING")
    new = controller.run_validation(job, "worker", fence, config, snapshot, "2026-01-01T00:00:00Z")
    begin_review(store, job, fence)
    assert controller.review(job, "worker", fence, config, new["run_id"])["state"] == "WAITING_FOR_INPUT"


def test_old_evidence_with_no_validation_for_new_revision_rejected(tmp_path, config, snapshot, standards):
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    begin_review(store, job, fence)
    controller.review(job, "worker", fence, config, evidence["run_id"])
    config["pipeline_concurrency"] = None
    store.revise(job, "worker", fence, revision(config, standards))
    store.transition(job, "worker", fence, "VALIDATING")
    begin_review(store, job, fence)
    with pytest.raises(StateError):
        controller.review(job, "worker", fence, config, evidence["run_id"])


def test_crashed_validation_cannot_reuse_old_success(tmp_path, config, snapshot, standards, monkeypatch):
    store, job, fence, controller, evidence = setup_review(tmp_path, config, snapshot, standards)
    def crash(*args, **kwargs):
        raise OSError("injected process failure")
    monkeypatch.setattr("fabric_agents.controller.LocalEngine.execute", crash)
    with pytest.raises(OSError):
        controller.run_validation(job, "worker", fence, config, snapshot, "2026-01-02T00:00:00Z")
    begin_review(store, job, fence)
    with pytest.raises(StateError, match="incomplete"):
        controller.review(job, "worker", fence, config, evidence["run_id"])
