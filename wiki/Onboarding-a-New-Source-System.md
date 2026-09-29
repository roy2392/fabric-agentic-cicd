# Onboarding a New Source System

## Required work item context

Describe the source purpose, schema/table names, confirmed key columns, timestamp semantics, target dataset names and acceptance criteria. State whether deletes, schema changes or scale exceed the demo framework. Include approved connection references but never credentials. If a key is unknown, request clarification before implementing it.

## Implementation checklist

1. Read the platform architecture, ingestion contract, metadata schema and source inventory at a pinned wiki revision.
2. Establish the authorized feature scope and baseline solution commit.
3. Add the source metadata JSON with confirmed keys.
4. Clone the pipeline template with a fresh logical ID; set `source_system` and preserve sequential execution and concurrency one.
5. Verify dependency references and the explicitly selected connection. Do not rewrite shared platform items as an incidental onboarding change.
6. Stage exact configuration bytes and run the authorized feature pipeline.
7. Capture source/raw/key/current counts, notebook history count, job IDs and any failed attempts.
8. Add a source overview and child table pages describing real columns, keys, semantics, raw and target paths, and limitations.
9. Publish the feature PR, allow independent review, correct real findings, and wait for human merge.
10. Verify authorized main deployment and close the work item with evidence.

## Supported boundary

The automatic tagged-board lane currently permits bounded local utilities and documentation only. A request that needs Fabric item edits, infrastructure, new credentials, dependencies or live execution must stop for operator clarification and use the separately authorized onboarding workflow. Do not make an unsupported task appear complete by implementing only a small subset.

Use [loyalty](/Table-Inventory/loyalty) as the real example. The original single-column key failure demonstrates why domain context and a human answer belong in the workflow.
