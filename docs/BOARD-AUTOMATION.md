# Automatic board assignments

Create an Azure DevOps **Issue**, describe the desired result and acceptance criteria, leave it in **To Do**, and add **`dev-agent`**. The configured local worker polls the board and picks it up. The Issue must be created by the operator identity in the local manifest. A tag is an opt-in to this bounded workflow, not permission for arbitrary cloud actions.

## What happens

1. The worker claims the Issue, assigns the developer identity, moves it to Doing and creates a child review Task.
2. Real Claude reads the pinned Microsoft Fabric skills, inspects the repository, and locks an exact file plan before writing. Python changes require meaningful tests.
3. Claude runs the sandboxed checks, pushes a feature branch and opens an Azure DevOps PR with both the human and independent reviewer required.
4. Real Codex reads the skills and independently reviews the exact source and target revisions. Findings trigger a fresh Claude correction, fresh checks and another independent review.
5. A current recorded approval plus the required reviewer's actual approving vote completes the child Task and adds `ready-for-human-merge` to the Issue. **You review and merge.**
6. A later poll verifies the completed PR and merge commit before moving the Issue to Done. The feature branch is retained as evidence.

Each command invocation runs at most one model session. A heartbeat can invoke it again after a completed session to advance the next stage, with at most eight invocations per heartbeat. New issues do not interrupt a model already running. The queue processes older eligible issues first.

## Supported scope

The automatic developer can change one to eight exact files, restricted to flat paths:

- `demo_tools/*.py`: pure standard-library utilities.
- `tests/test_*.py`: unittest tests, at least three meaningful cases for Python changes.
- `docs/*.md`: documentation, excluding agent instruction files.

It has no general shell, infrastructure, secret, dependency-install, SQL, Fabric execution, policy or merge tool. Requests needing those capabilities, or unclear requirements, must stop for human clarification. Tagging a new Fabric ingestion request does **not** automatically authorize a deployment. Use the separately approved Fabric onboarding workflow for that scope.

Example Issue:

> Add a pure helper that checks whether an Azure DevOps tags string contains the exact `dev-agent` tag and lacks `agent-paused`. Handle whitespace, case, malformed values and substring lookalikes. Add unittest coverage and usage documentation. No network calls or cloud changes.

## Local schedule and prerequisites

Configure the identities, private review checklist, Foundry Claude authentication and Codex authentication using [AGENTS-SETUP.md](AGENTS-SETUP.md). The controller uses the existing developer service principal for board operations; it does not need the human's token. The creator allowlist comes from `operator_ado_id` in the ignored live manifest.

Before enabling the worker, the operator must create the project tag names `dev-agent`, `review-agent`, `agent-paused`, `agent-blocked`, and `ready-for-human-merge` once (for example, add and remove them on a setup Issue). The scoped agent can reuse existing tags but is not granted permission to create new tag names. Verify it can create child Tasks and assign both existing agent identities.

```bash
python -m scripts.board_worker --once
```

For Codex desktop, create a recurring **thread heartbeat** that runs this command in the configured checkout every five minutes. The heartbeat should report only a new review/merge gate, completion, failure or need for user input, and stay quiet when the worker reports idle/busy or unchanged state. Schedule registration is a local app operation, not a repository credential or a GitHub workflow. Cloning this repository does not install a watcher automatically.

The Mac must be awake, the app scheduler available, network reachable, and both model authentications valid. This is local polling, not an Azure DevOps webhook or a continuously hosted cloud service. The test executor currently requires macOS. GitHub CI validates this worker's tests and release hygiene; GitHub Actions does not receive the local agent credentials or run this board loop.

## Stop and recovery

Remove `dev-agent` or add `agent-paused` to stop future actions. The runtime checks these fields and the captured requirements before writes, tests, publication and review. A request already in flight can finish; the tag is not a remote cancellation mechanism. Re-adding the tag resumes a clean paused item. Editing its title/description after pickup instead blocks it for reconciliation, so an old plan cannot silently implement new requirements.

At most four Claude sessions (initial plus three corrections) and eight total model sessions are allowed per issue. Each Claude session has a $10 SDK budget limit; this is not an Azure billing guarantee or a budget for Codex. A failed, timed-out or interrupted session is never blindly retried. An abandoned PR, removed reviewer gate, unexpected pushed head or changed reviewer vote also stops the workflow.

`agent-blocked` and an Issue comment identify required intervention. Inspect the ignored `.runs/assignments/<id>/` task, worker state, model logs, validation and revision-bound review receipts, then compare them with the actual PR. Before a retry, confirm no old process is alive and reconcile remote publication/review; preserve evidence and counters. There is deliberately no automatic reset command. Ask the operator to repair the captured plan/state after clarification, or create a fresh Issue for materially different requirements. Do not delete journals to force a replay.

An OS file lock serializes local polls. Durable claims precede registration/model execution; a crash may require reconciliation rather than automatic recovery. The lock does not coordinate two different Macs: deploy exactly one controller per board/repository. Private logs, certificates and live manifests stay under ignored local paths and must never be pushed.

## Evidence

Board comments record pickup, file plan, model starts, test evidence, review and merge verification. Approval is bound to both source and target commits; a target change requires another review. Unit tests and synthetic fixtures prove local behavior only. Neither a tagged Issue, successful process exit nor this worker's completion proves a new Fabric pipeline run.
