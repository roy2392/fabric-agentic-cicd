# loyalty_members

One source row represents a member within a tenant. Member IDs are not globally unique. The source DDL is versioned in `demo/synthetic-source.sql`; the original seed contains three entirely synthetic rows.

## Source columns

| Column | SQL type | Nullable | Meaning |
|---|---|---|---|
| `tenant_id` | `nvarchar(20)` | No | Tenant namespace; first key component |
| `member_id` | `int` | No | Member identifier within tenant; second key component |
| `member_name` | `nvarchar(100)` | No | Synthetic member display name |
| `tier` | `nvarchar(20)` | No | Loyalty tier |
| `updated_at` | `datetime2` | No | Source update timestamp; descriptive watermark |

Primary key constraint: `(tenant_id, member_id)`. The bronze table retains the source fields and adds:

| Column | Meaning |
|---|---|
| `_meta_key` | SHA-256 of JSON struct containing the ordered key columns |
| `_meta_hash` | SHA-256 of JSON struct over sorted business columns |
| `_meta_valid_from` | Start of version validity |
| `_meta_valid_to` | End of validity; null for the current version |
| `_meta_is_current` | True for the current version |
| `_meta_run_timestamp` | Timestamp of the snapshot that inserted the version |

## Storage

Raw: `Files/raw/loyalty/loyalty_members/<run_timestamp>/` in bronze. Target: `Tables/loyalty/loyalty_members`. Audit: `audit.load_runs`.

## Read-only query examples

Run the first query against the source database:

```sql
SELECT tenant_id, member_id, member_name, tier, updated_at
FROM agent_demo.loyalty_members
ORDER BY tenant_id, member_id;
```

Run these examples in Spark SQL with the bronze lakehouse selected:

```sql
SELECT * FROM loyalty.loyalty_members WHERE _meta_is_current = true;
SELECT COUNT(*) AS history_count FROM loyalty.loyalty_members;
SELECT tenant_id, member_id, COUNT(*) AS current_versions
FROM loyalty.loyalty_members WHERE _meta_is_current = true
GROUP BY tenant_id, member_id HAVING COUNT(*) <> 1;
```

For a point in time, use `_meta_valid_from <= <timestamp>` and `(_meta_valid_to IS NULL OR _meta_valid_to > <timestamp>)`. Do not use the insertion run timestamp to delete a failed attempt: closing an older version does not change its original insertion timestamp.

## Expected fixture transitions

A baseline gives current/history `3/3`. Changing one member in an isolated validation gives `3/4`; replaying the unchanged snapshot remains `3/4`. These are historical test expectations, not fresh measurements. The isolated changed-row proof is not proof of an end-to-end changed SQL source load. See [execution evidence](/Verified-Execution-Evidence).
