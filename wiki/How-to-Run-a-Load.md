# How to Run a Load

This procedure applies to an explicitly authorized Fabric execution. Adding `dev-agent` to a documentation issue does not grant that execution authority.

## Before starting

1. Select the declared environment configuration. Confirm the intended tenant, workspace, capacity, source connection and repository revision. Do not substitute the CLI's default subscription.
2. Verify the official skills lock and read the Git and Spark skills plus their required shared/mode references.
3. Read [metadata rules](/Metadata-Schema-Reference) and the [source page](/Table-Inventory/loyalty).
4. Confirm capacity and gateway availability without silently changing billing or network settings.
5. Confirm the metadata bytes staged in the configuration lakehouse match the reviewed source commit.
6. Resolve any existing job before submitting another. Keep the synthetic source unchanged during copy and count.

## Execute and observe

Use the authorized onboarding/deployment entry point configured for this environment. Record the selected source commit, workspace ID and pipeline item ID before starting. Capture the returned job ID, poll that job to a terminal state, and retain activity results and the notebook's actual exit value. A successful request to create a job is not a successful load.

For Git synchronization, read current Git status, pass the current workspace head, serialize changes, follow long-running operation polling and verify the resulting head and changes. Do not treat a successful API submission as proof of synchronization.

## Reconcile

| Check | Expected relation |
|---|---|
| Frozen source count vs raw rows | Equal |
| Raw rows vs distinct composite keys | Equal, with no null key components |
| Current bronze rows vs accepted raw snapshot | Equal after successful processing |
| History count | At least current count; obtain from notebook result or target query |
| Replay of unchanged snapshot | No additional history rows |

The initial synthetic seed has three rows, but three is historical fixture data, not a permanent expected production count. Built-in copy consistency marked `NotVerified` is not a passing consistency check. Use separately captured reconciliation evidence.

## Closeout

Link the exact run evidence to the work item and PR. The reviewer assesses the exact source/target revisions. After a human merges, the operator verifies the merge commit, performs the authorized main synchronization and validates the result before retiring registered feature resources. Preserve raw, audit and failed-run evidence.
