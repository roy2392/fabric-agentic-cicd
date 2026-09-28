"""Bounded local full-snapshot ingestion using real Parquet and Delta files.

Not the Fabric runtime. Table commits are atomic, a multi-table batch is not.
A failed/interrupted batch can be rerun under the same snapshot and timestamp.
"""

import fcntl
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from deltalake import DeltaTable, write_deltalake

from .contracts import ContractError, canonical, digest, instant, metadata, validate

META = {"_valid_from", "_valid_to", "_is_current", "_record_hash"}


def check(name, expected, actual):
    return {"name": name, "passed": actual == expected, "expected": expected, "actual": actual}


def key(row, columns):
    return tuple(row[c] for c in columns)


def arrow_schema(columns, history=False):
    fields = [pa.field(k, pa.int64() if v == "integer" else pa.string(), nullable=False) for k, v in columns.items()]
    if history:
        fields += [pa.field("_valid_from", pa.string(), False), pa.field("_valid_to", pa.string()),
                   pa.field("_is_current", pa.bool_(), False), pa.field("_record_hash", pa.string(), False)]
    return pa.schema(fields)


def scd_invariants(rows, keys):
    grouped = {}
    for row in rows:
        grouped.setdefault(key(row, keys), []).append(row)
    for history in grouped.values():
        history.sort(key=lambda r: r["_valid_from"])
        if sum(r["_is_current"] for r in history) != 1 or not history[-1]["_is_current"]:
            return False
        for i, row in enumerate(history):
            if row["_is_current"] != (row["_valid_to"] is None):
                return False
            if row["_valid_to"] is not None and row["_valid_from"] >= row["_valid_to"]:
                return False
            if i and (history[i - 1]["_valid_to"] is None or history[i - 1]["_valid_to"] > row["_valid_from"]):
                return False
    return True


class LocalEngine:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def execute(self, config, snapshot, observed_at, job_id, revision, standards):
        metadata(config)
        observed_at = instant(observed_at)
        with (self.root / ".writer.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._execute(config, snapshot, observed_at, job_id, revision, standards)

    def _execute(self, config, snapshot, observed_at, job_id, revision, standards):
        checks, tables, plans = [], [], []
        evidence = {
            "version": 1, "run_id": str(uuid.uuid4()), "job_id": job_id,
            "evidence_kind": "local_delta_execution", "revision": revision,
            "standards_hash": digest(standards), "snapshot_hash": digest(snapshot),
            "observed_at": observed_at, "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed", "checks": checks, "tables": tables, "fabric_run_id": None,
        }
        if not isinstance(snapshot, dict):
            raise ContractError("Snapshot must be an object")
        checks.append(check("source.tables", sorted(t["name"] for t in config["tables"]), sorted(snapshot)))
        contract_hash = digest(config["tables"])
        intent = {"contract_hash": contract_hash, "snapshot_hash": digest(snapshot), "observed_at": observed_at}
        pending_path = self.root / "pending-batch.json"
        if pending_path.exists():
            checks.append(check("recovery.same_pending_batch", json.loads(pending_path.read_text()), intent))
        ledger_path = self.root / "snapshot-ledger.json"
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else None
        if ledger:
            checks.append(check("contract.unchanged", ledger["contract_hash"], contract_hash))
            checks.append(check("snapshot.monotonic", True, observed_at >= ledger["observed_at"]))
            checks.append(check("snapshot.same_time_same_content", True,
                                observed_at != ledger["observed_at"] or digest(snapshot) == ledger["snapshot_hash"]))
        valid_source = True
        for spec in config["tables"]:
            name, columns, keys = spec["name"], spec["columns"], spec["primary_key"]
            rows = snapshot.get(name)
            shape_ok = isinstance(rows, list) and len(rows) <= standards["max_local_rows_per_table"]
            if shape_ok:
                shape_ok = all(isinstance(r, dict) and set(r) == set(columns) and all(
                    (type(r[c]) is int and -(2**63) <= r[c] < 2**63) if kind == "integer" else type(r[c]) is str
                    for c, kind in columns.items()) for r in rows)
            checks.append(check(f"{name}.schema_and_non_null", True, shape_ok))
            if not shape_ok:
                valid_source = False
                continue
            unique = len({key(r, keys) for r in rows}) == len(rows)
            checks.append(check(f"{name}.primary_key_unique", True, unique))
            valid_source = valid_source and unique
        if valid_source and {"tiers", "members", "point_events"} <= set(snapshot):
            tiers = {r["tier_id"] for r in snapshot["tiers"]}
            members = {r["member_id"] for r in snapshot["members"]}
            checks.append(check("members.tier_reference", True, all(r["tier_id"] in tiers for r in snapshot["members"])))
            checks.append(check("point_events.member_reference", True, all(r["member_id"] in members for r in snapshot["point_events"])))
        if not all(c["passed"] for c in checks):
            return validate(evidence, "evidence")
        # Compute and validate ALL table plans before writing any data.
        for spec in config["tables"]:
            name, keys = spec["name"], spec["primary_key"]
            rows = snapshot[name]
            path = self.root / "bronze" / name
            exists = DeltaTable.is_deltatable(str(path))
            old = DeltaTable(str(path)).to_pyarrow_table().to_pylist() if exists else []
            checks.append(check(f"{name}.existing_scd2", True, scd_invariants(old, keys)))
            current = {key(r, keys): r for r in old if r["_is_current"]}
            incoming = {key(r, keys): r for r in rows}
            checks.append(check(f"{name}.no_implicit_deletes", 0, len(set(current) - set(incoming))))
            history = [dict(r) for r in old]
            changed = False
            for pk, row in incoming.items():
                record_hash = digest(row)
                previous = current.get(pk)
                if previous and previous["_record_hash"] == record_hash:
                    continue
                if previous:
                    checks.append(check(f"{name}.update_time_advances", True, observed_at > previous["_valid_from"]))
                    for h in history:
                        if key(h, keys) == pk and h["_is_current"]:
                            h.update(_is_current=False, _valid_to=observed_at)
                history.append({**row, "_record_hash": record_hash, "_valid_from": observed_at, "_valid_to": None, "_is_current": True})
                changed = True
            checks.append(check(f"{name}.planned_scd2", True, scd_invariants(history, keys)))
            plans.append((spec, rows, path, history, changed or not exists))
        if not all(c["passed"] for c in checks):
            return validate(evidence, "evidence")
        intent_tmp = pending_path.with_suffix(".tmp")
        intent_tmp.write_text(canonical(intent))
        intent_tmp.replace(pending_path)
        for spec, rows, path, history, changed in plans:
            name = spec["name"]
            raw = self.root / "raw" / digest(snapshot) / f"{name}.parquet"
            raw.parent.mkdir(parents=True, exist_ok=True)
            if not raw.exists():
                raw_tmp = raw.with_suffix(".tmp")
                pq.write_table(pa.Table.from_pylist(rows, schema=arrow_schema(spec["columns"])), raw_tmp)
                raw_tmp.replace(raw)
            raw_rows = pq.read_table(raw).to_pylist()
            raw_check = check(f"{name}.raw_readback", digest(sorted(canonical(r) for r in rows)),
                              digest(sorted(canonical(r) for r in raw_rows)))
            checks.append(raw_check)
            if not raw_check["passed"]:
                return validate(evidence, "evidence")
            if changed:
                write_deltalake(str(path), pa.Table.from_pylist(history, schema=arrow_schema(spec["columns"], True)), mode="overwrite")
            delta = DeltaTable(str(path))
            actual = delta.to_pyarrow_table().to_pylist()
            current = [{k: v for k, v in r.items() if k not in META} for r in actual if r["_is_current"]]
            checks.append(check(f"{name}.source_target_reconciliation", sorted(canonical(r) for r in rows), sorted(canonical(r) for r in current)))
            # Evidence retains counts/digests, not source rows.
            checks[-1]["expected"] = digest(sorted(canonical(r) for r in rows))
            checks[-1]["actual"] = digest(sorted(canonical(r) for r in current))
            checks.append(check(f"{name}.scd2_readback", True, scd_invariants(actual, spec["primary_key"])))
            tables.append({"name": name, "raw_file": str(raw), "delta_path": str(path), "delta_version": delta.version(),
                           "current_rows": len(current), "history_rows": len(actual)})
        if all(c["passed"] for c in checks):
            evidence["status"] = "passed"
            tmp = ledger_path.with_suffix(".tmp")
            tmp.write_text(canonical({"contract_hash": contract_hash, "snapshot_hash": digest(snapshot), "observed_at": observed_at}))
            tmp.replace(ledger_path)
            pending_path.unlink()
        return validate(evidence, "evidence")
