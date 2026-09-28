"""Durable local orchestration with atomic claims and fencing on lease takeover."""

import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

from .contracts import canonical

EDGES = {
    "READY": {"PREPARING"},
    "PREPARING": {"DEVELOPING"},
    "DEVELOPING": {"VALIDATING"},
    "VALIDATING": {"WAITING_FOR_INPUT", "PR_OPEN"},
    "WAITING_FOR_INPUT": {"DEVELOPING"},
    "PR_OPEN": {"REVIEWING"},
    "REVIEWING": {"CHANGES_REQUESTED", "READY_FOR_HUMAN"},
    "CHANGES_REQUESTED": {"DEVELOPING"},
    "READY_FOR_HUMAN": set(),
    "FAILED": set(), "CANCELLED": set(),
}


class StateError(RuntimeError):
    pass


class Store:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with closing(self.connect()) as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, event_key TEXT UNIQUE NOT NULL,
                    revision TEXT NOT NULL, state TEXT NOT NULL,
                    owner TEXT, fence INTEGER NOT NULL DEFAULT 0,
                    lease_until REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, job_id TEXT NOT NULL,
                    state TEXT NOT NULL, detail TEXT NOT NULL, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence (
                    run_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                    revision TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS validation_attempts (
                    id INTEGER PRIMARY KEY, job_id TEXT NOT NULL,
                    revision TEXT NOT NULL, run_id TEXT);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def enqueue(self, event_key, revision):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE event_key=?", (event_key,)).fetchone()
            if row:
                if row["revision"] != revision:
                    raise StateError("Duplicate event key has a different revision")
                return row["id"]
            job_id = str(uuid.uuid4())
            db.execute("INSERT INTO jobs(id,event_key,revision,state) VALUES(?,?,?,'READY')", (job_id, event_key, revision))
            self._event(db, job_id, "READY", {"event_key": event_key})
            return job_id

    def _event(self, db, job_id, state, detail):
        db.execute("INSERT INTO events(job_id,state,detail,at) VALUES(?,?,?,?)", (job_id, state, canonical(detail), self.clock()))

    def claim(self, job_id, owner, ttl=60):
        if not owner or ttl <= 0:
            raise StateError("Valid owner and positive TTL required")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["state"] in {"FAILED", "CANCELLED"}:
                raise StateError("Job cannot be claimed")
            if row["lease_until"] > self.clock():
                raise StateError("Job is already leased")
            fence = row["fence"] + 1
            db.execute("UPDATE jobs SET owner=?,fence=?,lease_until=? WHERE id=?", (owner, fence, self.clock() + ttl, job_id))
            return fence

    def _owned(self, db, job_id, owner, fence):
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["owner"] != owner or row["fence"] != fence or row["lease_until"] <= self.clock():
            raise StateError("Lease expired or worker fenced out")
        return row

    def renew(self, job_id, owner, fence, ttl=60):
        if ttl <= 0:
            raise StateError("Positive TTL required")
        with self.transaction() as db:
            self._owned(db, job_id, owner, fence)
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (self.clock() + ttl, job_id))

    def transition(self, job_id, owner, fence, target, detail=None):
        with self.transaction() as db:
            row = self._owned(db, job_id, owner, fence)
            allowed = EDGES[row["state"]] | {"FAILED", "CANCELLED"}
            if row["state"] in {"FAILED", "CANCELLED", "READY_FOR_HUMAN"} or target not in allowed:
                raise StateError(f"Illegal transition: {row['state']} -> {target}")
            if target == "READY_FOR_HUMAN":
                raise StateError("Use the evidence-backed review gate")
            db.execute("UPDATE jobs SET state=? WHERE id=?", (target, job_id))
            self._event(db, job_id, target, detail or {})

    def revise(self, job_id, owner, fence, revision):
        with self.transaction() as db:
            row = self._owned(db, job_id, owner, fence)
            if row["state"] not in {"WAITING_FOR_INPUT", "CHANGES_REQUESTED", "READY_FOR_HUMAN", "DEVELOPING"}:
                raise StateError("Revision change not allowed in this state")
            db.execute("UPDATE jobs SET revision=?,state='DEVELOPING' WHERE id=?", (revision, job_id))
            self._event(db, job_id, "DEVELOPING", {"revision": revision, "previous_evidence_invalidated": True})

    def get(self, job_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise StateError("Unknown job")
            return dict(row)

    def history(self, job_id):
        with closing(self.connect()) as db:
            return [{**dict(row), "detail": json.loads(row["detail"])} for row in db.execute("SELECT * FROM events WHERE job_id=? ORDER BY seq", (job_id,))]
