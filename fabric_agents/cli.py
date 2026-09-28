import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .contracts import ROOT, ContractError, load, metadata, revision
from .preflight import PreflightError, doctor, inspect
from .state import StateError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fabric engineering agents: local foundation and read-only discovery")
    subs = parser.add_subparsers(dest="command", required=True)
    demo = subs.add_parser("demo", help="Run real local Parquet/Delta acceptance scenario; no models or cloud calls")
    demo.add_argument("--output", type=Path)
    subs.add_parser("doctor", help="Discover local CLI availability without authentication")
    check = subs.add_parser("validate-metadata")
    check.add_argument("path", type=Path)
    preflight = subs.add_parser("preflight", help="Explicitly targeted read-only Fabric and Azure DevOps discovery")
    preflight.add_argument("--config", type=Path, required=True)
    local = subs.add_parser("run-local", help="Ingest a complete synthetic snapshot into a reusable local dataset")
    local.add_argument("--metadata", type=Path, required=True)
    local.add_argument("--snapshot", type=Path, required=True)
    local.add_argument("--observed-at", required=True)
    local.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import run
            output = args.output or Path(".runs") / datetime.now(timezone.utc).strftime("demo-%Y%m%dT%H%M%S%fZ")
            result = run(output)
        elif args.command == "run-local":
            from .engine import LocalEngine
            config = metadata(load(args.metadata))
            standards = load(ROOT / "standards/platform.json")
            result = LocalEngine(args.output / "data").execute(config, load(args.snapshot), args.observed_at,
                     "manual-local-run", revision(config, standards), standards)
            evidence_dir = args.output / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            artifact = evidence_dir / f"{result['run_id']}.json"
            artifact.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps({"status": result["status"], "evidence": str(artifact.resolve()), "evidence_kind": result["evidence_kind"]}, indent=2))
            return 0 if result["status"] == "passed" else 1
        elif args.command == "doctor":
            result = doctor()
        elif args.command == "validate-metadata":
            metadata(load(args.path))
            result = {"valid": True}
        else:
            result = inspect(load(args.config))
        print(json.dumps(result, indent=2))
        return 0
    except (ContractError, PreflightError, StateError, FileExistsError, FileNotFoundError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
