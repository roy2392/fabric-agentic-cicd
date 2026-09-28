"""Scripted acceptance scenario, not a simulated claim of agent activity."""

import copy
import json
from pathlib import Path

from .contracts import ROOT, load, revision
from .controller import Controller
from .state import Store


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    standards = load(ROOT / "standards/platform.json")
    config = load(ROOT / "examples/loyalty/metadata.json")
    first = load(ROOT / "examples/loyalty/snapshot-1.json")
    second = load(ROOT / "examples/loyalty/snapshot-2.json")
    store = Store(output / "state.sqlite")
    controller = Controller(store, output / "jobs", standards)
    bad = copy.deepcopy(config)
    bad["tables"][2]["primary_key"] = ["member_id"]
    bad["pipeline_concurrency"] = None
    job = store.enqueue("local-demo:loyalty:ticket-1:revision-1:developer", revision(bad, standards))
    duplicate = store.enqueue("local-demo:loyalty:ticket-1:revision-1:developer", revision(bad, standards))
    owner = "local-scripted-controller"
    fence = store.claim(job, owner, ttl=600)

    def step(target, detail=None):
        store.transition(job, owner, fence, target, detail)

    def execute(meta, data, timestamp):
        step("VALIDATING")
        return controller.run_validation(job, owner, fence, meta, data, timestamp)

    def review(meta, evidence):
        step("PR_OPEN", {"external_pr_created": False})
        step("REVIEWING")
        return controller.review(job, owner, fence, meta, evidence["run_id"])

    step("PREPARING", {"workspace_kind": "local_directory", "fabric_workspace_created": False})
    step("DEVELOPING")
    failed = execute(bad, first, "2026-01-01T00:00:00Z")
    assert failed["status"] == "failed", "Seeded primary key defect must fail"
    step("WAITING_FOR_INPUT", {"reason": "point_events requires member_id + event_seq", "reply_kind": "scripted_fixture"})
    corrected = copy.deepcopy(config)
    corrected["pipeline_concurrency"] = None
    store.revise(job, owner, fence, revision(corrected, standards))
    loaded = execute(corrected, first, "2026-01-01T00:00:00Z")
    requested = review(corrected, loaded)
    assert requested["state"] == "CHANGES_REQUESTED", "Concurrency omission must block review"
    store.revise(job, owner, fence, revision(config, standards))
    corrected_run = execute(config, first, "2026-01-01T00:00:00Z")
    # Continue validation under the same lease/revision to verify changed source
    # and a repeat of the exact same batch before the final review.
    updated = controller.run_validation(job, owner, fence, config, second, "2026-01-02T00:00:00Z")
    rerun = controller.run_validation(job, owner, fence, config, second, "2026-01-02T00:00:00Z")
    versions = lambda evidence: {t["name"]: t["delta_version"] for t in evidence["tables"]}
    assert versions(updated) == versions(rerun), "Idempotent rerun must not add Delta versions"
    decision = review(config, rerun)
    assert decision["state"] == "READY_FOR_HUMAN"
    report = {
        "scenario": "deterministic_local_acceptance", "job_id": job,
        "external_services_called": False, "ai_agents_invoked": False,
        "duplicate_event_deduplicated": duplicate == job,
        "primary_key_failure_caught": failed["status"] == "failed",
        "review_concurrency_failure_caught": requested["state"] == "CHANGES_REQUESTED",
        "rerun_created_no_delta_versions": versions(updated) == versions(rerun),
        "final_state": store.get(job)["state"], "live_merge_eligible": False,
        "data": rerun["tables"], "review": decision,
        "runs": [{"run_id": e["run_id"], "status": e["status"], "evidence_kind": e["evidence_kind"]}
                 for e in (failed, loaded, corrected_run, updated, rerun)],
        "history": store.history(job),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Local acceptance run", "", "Actual Parquet and Delta writes. Scripted feedback, with no model, Azure DevOps or Fabric calls.", "",
             "| Check | Result |", "|---|---|"]
    for field in ("duplicate_event_deduplicated", "primary_key_failure_caught", "review_concurrency_failure_caught", "rerun_created_no_delta_versions"):
        lines.append(f"| {field.replace('_', ' ')} | {'PASS' if report[field] else 'FAIL'} |")
    lines += ["", "| Table | Current rows | History rows | Delta version |", "|---|---:|---:|---:|"]
    for table in report["data"]:
        lines.append(f"| {table['name']} | {table['current_rows']} | {table['history_rows']} | {table['delta_version']} |")
    lines += ["", "Final state: READY_FOR_HUMAN (local only; never eligible for live merge).", "", "See report.json for all evidence IDs and state transitions."]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return {"report": str(output / "report.md"), "details": str(output / "report.json"),
            "final_state": report["final_state"], "ai_agents_invoked": False, "live_merge_eligible": False}
