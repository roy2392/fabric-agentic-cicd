# Ingestion Framework Guide

## Shared contract

The platform owns the configuration lakehouse, bronze lakehouse, `bronze_loader` notebook and `pl_ingest_template_bronze` pipeline. A source onboarding change adds source metadata and a pipeline cloned from the template with a fresh logical ID. It does not rewrite the shared lakehouses or notebook. Keep pipeline concurrency at one and dataset iteration sequential.

1. Stamp one UTC run timestamp.
2. Read the source's metadata array from the configuration lakehouse.
3. Copy each complete source table to snappy Parquet under `Files/raw/<source>/<dataset>/<run_timestamp>/` in bronze.
4. Obtain the source row count using a separate `COUNT_BIG(*)` statement.
5. Pass expected counts and the same timestamp to the notebook.
6. Validate identifiers, row counts, schema and keys before writing history.
7. Apply SCD2 changes and record the attempt in `audit.load_runs`.

## SCD2 behavior

The target is one Delta table at `Tables/<source>/<dataset>`. Current and historical versions are in the same table. A business key hash identifies the entity; a hash over sorted business columns detects changes. A changed entity closes its previous interval and inserts a new current version in one Delta merge. An unchanged replay does not append another history version.

| Scenario | Expected behavior |
|---|---|
| First complete snapshot | Insert one current row per valid business key |
| New key | Insert a current row |
| Changed business values | Close old version and insert the replacement |
| Identical replay | Preserve existing history count |
| Missing previously current key | Fail: deletion semantics are not implemented |
| Unexpected column names or types | Fail schema validation; do not silently evolve |
| Conflicting or out-of-order changed snapshot | Fail rather than rewriting history |
| More than 10,000 source rows | Fail the explicit demo limit |

Nullability relaxation alone is permitted where the loader's schema comparison allows it. This is a bounded demonstration, not a general production CDC framework.

## Evidence fields

Audit records include attempt ID, source, dataset, run timestamp, status, source count, raw count, distinct-key count, current count and error. **There is no `history_count` column in `audit.load_runs`.** History count is returned by notebook exit results and can be computed from the target table.

Preflight failures before dataset processing may produce a failed job without an audit row. Preserve the actual error. See [Recovery](/Troubleshooting-and-Recovery) and [Evidence](/Verified-Execution-Evidence).
