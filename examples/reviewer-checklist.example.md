# Reviewer-only runtime checklist template

Copy this template outside the source clones before customizing. The bounded developer tool cannot read the runtime copy. This public example itself is not confidential.

1. Source changes are restricted to the assigned work item and approved dataset.
2. Primary keys match an authenticated human requirement or clarification.
3. SQL extraction uses the approved read-only connection and explicit source scope.
4. Snapshot consistency assumptions and row-count limits are stated accurately.
5. Target lakehouse/notebook bindings resolve to the intended feature workspace.
6. Metadata, item inventory and count guards agree with the actual definitions.
7. Jobs are journaled and pending/uncertain submissions do not trigger duplicates.
8. Evidence matches the exact source revision and successful notebook audit attempt.
9. Current-row uniqueness and SCD2 interval/replay semantics are supported by evidence.
10. Wiki source/table/inventory pages describe the implemented behavior and limitations.
11. Recovery preserves later valid changes, raw snapshots, history and audit evidence.
12. Main policies preserve independent review plus human approval and prohibit agent bypass.
