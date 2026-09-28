"""Strict contracts shared by the runner and review gate."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent / "resources"


class ContractError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def validate(value, schema_name):
    validator = Draft202012Validator(load(ROOT / "contracts" / f"{schema_name}.json"))
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        raise ContractError("; ".join(f"{'.'.join(map(str, e.path)) or '$'}: {e.message}" for e in errors))
    return value


def metadata(value):
    validate(value, "metadata")
    names = set()
    for table in value["tables"]:
        if table["name"] in names:
            raise ContractError("Duplicate table name")
        names.add(table["name"])
        if not set(table["primary_key"]) <= set(table["columns"]):
            raise ContractError("Primary key must reference declared columns")
    expected_columns = {
        "tiers": {"tier_id": "integer", "name": "string"},
        "members": {"member_id": "integer", "name": "string", "tier_id": "integer"},
        "point_events": {"member_id": "integer", "event_seq": "integer", "points": "integer"},
    }
    if {t["name"]: t["columns"] for t in value["tables"]} != expected_columns:
        raise ContractError("This pilot supports exactly the declared synthetic loyalty tables and columns")
    return value


def instant(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timezone required")
        return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, AttributeError) as exc:
        raise ContractError("A timezone-qualified ISO timestamp is required") from exc


def revision(config, standards):
    # This is a local content digest, deliberately not represented as a Git SHA.
    code = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).resolve().parent.glob("*.py"))}
    schemas = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "contracts").glob("*.json"))}
    return digest({"metadata": config, "standards": standards, "code": code, "schemas": schemas})
