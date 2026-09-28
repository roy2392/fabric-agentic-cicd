import json

from fabric_agents.cli import main
from fabric_agents.contracts import ROOT, load


def test_cli_run_local_and_failed_validation(tmp_path, capsys):
    args = ["run-local", "--metadata", str(ROOT / "examples/loyalty/metadata.json"),
            "--snapshot", str(ROOT / "examples/loyalty/snapshot-1.json"),
            "--observed-at", "2026-01-01T00:00:00Z", "--output", str(tmp_path)]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert load(result["evidence"])["status"] == "passed"
    bad = load(ROOT / "examples/loyalty/snapshot-1.json")
    bad["point_events"].pop()
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    args[4] = str(tmp_path / "bad.json")
    args[6] = "2026-01-02T00:00:00Z"
    assert main(args) == 1


def test_preflight_missing_targets_fails_before_auth(tmp_path, capsys, monkeypatch):
    (tmp_path / "empty.json").write_text("{}")
    monkeypatch.setattr("fabric_agents.preflight.access_token", lambda *a: (_ for _ in ()).throw(AssertionError("Must not request a token")))
    assert main(["preflight", "--config", str(tmp_path / "empty.json")]) == 2
    assert "nonempty" in capsys.readouterr().err
