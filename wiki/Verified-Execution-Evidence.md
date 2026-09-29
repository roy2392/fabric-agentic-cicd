# Verified Execution Evidence

## Evidence levels

| Evidence | Establishes | Does not establish |
|---|---|---|
| Source tests | Behavior exercised in that test runtime | Live Fabric execution |
| Documentation/link check | Structure and resolvable checked links | Operational correctness |
| Model session and tool receipts | A real session and text/tool delivery | Model understanding or perfect review |
| PR approval | Reviewer verdict on recorded revisions | Human merge or deployment |
| Git synchronization | Definitions match recorded commit when checked | Successful data load |
| Pipeline/notebook job and reconciliation | Actual execution and measured counts for that run | Present resource health or future runs |

## Original onboarding evidence

The preserved [Platform runbook](/Platform-runbook), [Demo inventory](/Demo-inventory), [Loyalty source](/Loyalty-source) and [Loyalty members](/Loyalty-members) record the 28 September 2026 pilot, including job IDs, source commit, permission checks and corrections. They remain historical evidence and compatibility pages. Consult current deployment configuration before operating any resource mentioned there.

The original full loyalty pipeline reported three source/raw/current/history rows. Independent isolated Spark validation exercised a changed row and unchanged replay, giving current/history `3/3 → 3/4 → 3/4`. That isolated result is not an end-to-end SQL-change test. Copy consistency reported `NotVerified`; separate reconciliation is the supporting evidence.

## Recording new evidence

For Fabric work, record source commit, selected workspace and item IDs, job and activity results, notebook exit values and audit reconciliation. For local board assignments, record source and target commits, actual check output, wiki commit and page hashes, and the independent review verdict. Add explicit limitations; never copy prior successful run IDs into a new run's result.

The public repository contains portable source, CI and deployment instructions. Private execution receipts remain on the operator host. New context-enabled sessions should reference their issue/PR and pinned wiki revision in their published summaries.
