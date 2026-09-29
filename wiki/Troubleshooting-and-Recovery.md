# Troubleshooting and Recovery

| Symptom | Interpretation | Next action |
|---|---|---|
| Issue not picked up | Wrong type/state/creator/tag, paused issue, unavailable host or poll not due | Verify eligibility and host; inspect worker evidence before dispatching again |
| Review still queued | No validated developer PR ready yet | Inspect parent discussion and developer result |
| `PRIMARY_KEY_INVALID` | Null or duplicate declared key | Record counts and safe duplicate sample, ask human, stop |
| `SOURCE_RAW_COUNT_MISMATCH` | Copy/count disagree | Freeze source and inspect the exact copy/count job; preserve failed evidence |
| `SCHEMA_DRIFT` | Target and incoming business schema differ | Review intended migration; never silently alter shared platform |
| Missing audit row | Failure may have preceded dataset processing | Inspect actual job and activity errors |
| Wiki-read gate failure | Required text was not delivered in this process | Read all required pinned pages; do not reuse another process's receipt |
| Wiki revision changed | Documentation moved during implementation/review | Stop for operator reconciliation; do not approve against mixed context |
| Interrupted model process | Remote work may have happened | Check process, branch, PR and journal before any explicit retry |
| Human merge gate | Agent review completed but release decision pending | Human reviews and merges; keep protection intact |

## Delta recovery

Preserve raw snapshots, audit rows and failed jobs. Scope recovery to the recorded table and run. Inspect pre/post-write Delta versions and whether later valid writes occurred. Restore only an operator-approved version when its files remain available and the effect on later writes is understood; otherwise stop for a repair plan.

Deleting rows solely by `_meta_run_timestamp` is not a complete rollback. A merge can close an older row while retaining that row's original insertion timestamp. Blind deletion can lose the replacement without reopening its predecessor.

## Safe evidence handling

Do not publish private model logs, reviewer checklist text, credentials, tenant exports or deployment state. Link authorized work item and PR evidence instead. A retained branch or historical job ID is useful evidence, but is not proof that a live workspace still exists or the current capacity is active.
