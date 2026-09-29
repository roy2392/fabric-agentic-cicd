# Metadata Schema Reference

Git path: `configuration/<source>/<source>.json`. The authorized execution path stages the exact bytes under `Files/configuration/<source>/<source>.json` in the configuration lakehouse.

The document must be a nonempty JSON array. Each dataset name is unique within the source.

| Field | Type | Meaning |
|---|---|---|
| `dataset_name` | string | Bronze table name within the source schema |
| `source_schema` | string | SQL source schema |
| `source_table` | string | SQL source table |
| `primary_key_columns` | nonempty array of strings | Ordered, explicitly confirmed business key |
| `watermark_column` | string | Documented change timestamp; not an incremental filter |

Identifiers begin with a letter, contain only letters, digits or underscores and have at most 64 characters. Validate before constructing query expressions. Do not put SQL fragments, passwords, tokens or connection strings into metadata.

## Valid loyalty configuration

```json
[
  {
    "dataset_name": "loyalty_members",
    "source_schema": "agent_demo",
    "source_table": "loyalty_members",
    "primary_key_columns": ["tenant_id", "member_id"],
    "watermark_column": "updated_at"
  }
]
```

The source system is `loyalty`, so this belongs in `configuration/loyalty/loyalty.json`. The target is `loyalty.loyalty_members`. The source query loads a full snapshot from `agent_demo.loyalty_members`.

## Validation examples

| Input | Result |
|---|---|
| Empty array | Reject: no datasets |
| Duplicate dataset names | Reject: ambiguous target |
| Empty key array | Reject: undefined entity identity |
| Identifier `members; DROP TABLE x` | Reject before SQL evaluation |
| Key `["member_id"]` for the seeded loyalty rows | Metadata can be structurally valid but row validation fails: member 1 exists in two tenants |
| Composite key `["tenant_id", "member_id"]` | Matches the human-confirmed source key |

Structural validation is distinct from executing a load or proving uniqueness in the actual source. Never infer a replacement key after a failure; ask the human through the work item.
