import copy

import pyarrow.parquet as pq
import pytest
from deltalake import DeltaTable

from fabric_agents import engine
from fabric_agents.contracts import ContractError, metadata, revision
from fabric_agents.engine import LocalEngine


def run(root, config, snapshot, standards, when="2026-01-01T00:00:00Z"):
    return LocalEngine(root).execute(config, snapshot, when, "job", revision(config, standards), standards)


def test_physical_parquet_delta_and_scd2(tmp_path, config, snapshot, updated, standards):
    first = run(tmp_path, config, snapshot, standards)
    assert first["status"] == "passed"
    for table in first["tables"]:
        assert pq.read_table(table["raw_file"]).num_rows == len(snapshot[table["name"]])
        assert DeltaTable(table["delta_path"]).version() == 0
    second = run(tmp_path, config, updated, standards, "2026-01-02T00:00:00Z")
    assert second["status"] == "passed"
    members = DeltaTable(str(tmp_path / "bronze/members")).to_pyarrow_table().to_pylist()
    old = [r for r in members if r["member_id"] == 1]
    assert len(old) == 2
    assert sum(r["_is_current"] for r in old) == 1
    assert [r for r in old if not r["_is_current"]][0]["_valid_to"] == [r for r in old if r["_is_current"]][0]["_valid_from"]
    rerun = run(tmp_path, config, updated, standards, "2026-01-02T00:00:00Z")
    assert rerun["tables"] == second["tables"]


def test_duplicate_keys_write_nothing(tmp_path, config, snapshot, standards):
    config["tables"][2]["primary_key"] = ["member_id"]
    evidence = run(tmp_path, config, snapshot, standards)
    assert evidence["status"] == "failed"
    assert any(c["name"] == "point_events.primary_key_unique" and not c["passed"] for c in evidence["checks"])
    assert not (tmp_path / "bronze").exists()
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize("mutation", [
    lambda data: data["members"][0].update(member_id=None),
    lambda data: data["members"][0].update(member_id=True),
    lambda data: data["members"][0].update(member_id=2**80),
    lambda data: data["members"][0].update(extra="drift"),
    lambda data: data["members"][0].update(tier_id=999),
    lambda data: data["point_events"][0].update(member_id=999),
    lambda data: data.pop("members"),
])
def test_invalid_source_fails_before_writes(tmp_path, config, snapshot, standards, mutation):
    mutation(snapshot)
    assert run(tmp_path, config, snapshot, standards)["status"] == "failed"
    assert not (tmp_path / "bronze").exists()


def test_deletes_and_late_or_replaced_snapshot_rejected(tmp_path, config, snapshot, updated, standards):
    run(tmp_path, config, snapshot, standards)
    deleted = copy.deepcopy(snapshot)
    deleted["point_events"].pop()
    assert run(tmp_path, config, deleted, standards, "2026-01-02T00:00:00Z")["status"] == "failed"
    assert run(tmp_path, config, snapshot, standards, "2025-12-31T00:00:00Z")["status"] == "failed"
    assert run(tmp_path, config, updated, standards)["status"] == "failed"
    assert DeltaTable(str(tmp_path / "bronze/point_events")).version() == 0


def test_row_limit(tmp_path, config, snapshot, standards):
    standards["max_local_rows_per_table"] = 1
    assert run(tmp_path, config, snapshot, standards)["status"] == "failed"


def test_timezone_normalized_and_naive_rejected(tmp_path, config, snapshot, standards):
    first = run(tmp_path, config, snapshot, standards, "2026-01-01T02:00:00+02:00")
    second = run(tmp_path, config, snapshot, standards)
    assert first["observed_at"] == second["observed_at"]
    assert second["status"] == "passed"
    with pytest.raises(ContractError):
        run(tmp_path, config, snapshot, standards, "2026-01-01")


def test_interrupted_batch_recovers_only_exact_request(tmp_path, config, snapshot, updated, standards, monkeypatch):
    original = engine.write_deltalake
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 2:
            raise OSError("injected interruption")
        original(*args, **kwargs)

    monkeypatch.setattr(engine, "write_deltalake", interrupted)
    with pytest.raises(OSError):
        run(tmp_path, config, snapshot, standards)
    assert (tmp_path / "pending-batch.json").exists()
    monkeypatch.setattr(engine, "write_deltalake", original)
    assert run(tmp_path, config, updated, standards, "2026-01-02T00:00:00Z")["status"] == "failed"
    recovered = run(tmp_path, config, snapshot, standards)
    assert recovered["status"] == "passed"
    assert all(t["delta_version"] == 0 for t in recovered["tables"])
    assert not (tmp_path / "pending-batch.json").exists()


@pytest.mark.parametrize("bad_name", ["../escape", "a/b", "members;DROP TABLE x", "_metadata"])
def test_unsafe_identifiers_rejected(config, bad_name):
    config["tables"][0]["name"] = bad_name
    with pytest.raises(ContractError):
        metadata(config)


def test_unsupported_modes_and_columns_rejected(config):
    config["tables"][0]["load_mode"] = "incremental"
    with pytest.raises(ContractError):
        metadata(config)

