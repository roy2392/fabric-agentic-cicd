"""Local controller: trusted evidence registry and deterministic review checks.

This shares the user's OS trust boundary. It is NOT an authenticated tool server
and must not be exposed to autonomous workers with cloud credentials.
"""

import json
from pathlib import Path

from .contracts import canonical, digest, metadata, revision, validate
from .engine import LocalEngine
from .state import StateError


class Controller:
    def __init__(self, store, root, standards):
        self.store = store
        self.root = Path(root).resolve()
        self.standards = standards

    def run_validation(self, job_id, owner, fence, config, snapshot, observed_at):
        metadata(config)
        expected_revision = revision(config, self.standards)
        # Persist intent first. If the process crashes, a previous successful
        # run must not become eligible for review again.
        with self.store.transaction() as db:
            job = self.store._owned(db, job_id, owner, fence)
            if job["state"] != "VALIDATING" or job["revision"] != expected_revision:
                raise StateError("Validation requires the current registered revision")
            attempt = db.execute("INSERT INTO validation_attempts(job_id,revision) VALUES(?,?)", (job_id, expected_revision)).lastrowid
        # One local dispatcher; holding this write transaction serializes local
        # registration and prevents lease takeover mid-validation.
        with self.store.transaction() as db:
            job = self.store._owned(db, job_id, owner, fence)
            if job["state"] != "VALIDATING" or job["revision"] != expected_revision:
                raise StateError("Validation requires the current registered revision")
            evidence = LocalEngine(self.root / job_id / "data").execute(
                config, snapshot, observed_at, job_id, expected_revision, self.standards)
            self.store._owned(db, job_id, owner, fence)
            payload = canonical(evidence)
            db.execute("INSERT INTO evidence VALUES(?,?,?,?,?)", (evidence["run_id"], job_id, expected_revision, digest(evidence), payload))
            db.execute("UPDATE validation_attempts SET run_id=? WHERE id=?", (evidence["run_id"], attempt))
            target = self.root / job_id / "evidence" / f"{evidence['run_id']}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(evidence, indent=2) + "\n")
            return evidence

    def review(self, job_id, owner, fence, config, run_id):
        """Deterministic local gate; never an AI vote or a production approval."""
        with self.store.transaction() as db:
            job = self.store._owned(db, job_id, owner, fence)
            if job["state"] != "REVIEWING":
                raise StateError("Job must be reviewing")
            if revision(config, self.standards) != job["revision"]:
                raise StateError("Review configuration does not match current revision")
            row = db.execute("SELECT * FROM evidence WHERE run_id=? AND job_id=?", (run_id, job_id)).fetchone()
            if not row:
                raise StateError("Evidence is not registered by this controller")
            attempt = db.execute("SELECT run_id FROM validation_attempts WHERE job_id=? AND revision=? ORDER BY id DESC LIMIT 1", (job_id, job["revision"])).fetchone()
            if not attempt or attempt["run_id"] != run_id:
                raise StateError("Most recent validation attempt is incomplete or different")
            latest = db.execute("SELECT run_id FROM evidence WHERE job_id=? AND revision=? ORDER BY rowid DESC LIMIT 1", (job_id, job["revision"])).fetchone()
            if not latest or latest["run_id"] != run_id:
                raise StateError("Only the most recent validation can be reviewed")
            evidence = validate(json.loads(row["payload"]), "evidence")
            if digest(evidence) != row["digest"] or evidence["revision"] != job["revision"] or evidence["standards_hash"] != digest(self.standards):
                raise StateError("Stale or corrupted evidence")
            findings = []
            if evidence["status"] != "passed" or not all(c["passed"] for c in evidence["checks"]):
                findings.append("Runtime validation did not pass")
            if config["pipeline_concurrency"] != self.standards["pipeline_concurrency"]:
                findings.append("Set pipeline_concurrency to 1, per shared platform standards")
            state = "CHANGES_REQUESTED" if findings else "READY_FOR_HUMAN"
            if findings:
                cycles = db.execute("SELECT count(*) FROM events WHERE job_id=? AND state='CHANGES_REQUESTED'", (job_id,)).fetchone()[0]
                if cycles + 1 >= self.standards["max_review_cycles"]:
                    state = "WAITING_FOR_INPUT"
                    findings.append("Review cycle limit reached; human resolution required")
            db.execute("UPDATE jobs SET state=? WHERE id=?", (state, job_id))
            result = {"state": state, "findings": findings, "review_kind": "deterministic_local_gate", "run_id": run_id,
                      "revision": job["revision"], "live_merge_eligible": False}
            self.store._event(db, job_id, state, result)
            return result
