# Agent Workflow and Context

## What starts automatically

Create an Issue with clear, bounded acceptance criteria in To Do or Doing, using the configured human operator account. Add the exact tag `dev-agent`. A scheduled poll can then claim it. Tags such as `not-dev-agent` do not match; `agent-paused` prevents further work. The current heartbeat checks every five minutes while its Mac/Codex host is available. Tagging is a polling trigger, not an instantaneous webhook.

The worker claims the parent, creates a child review task, dispatches real Claude Code through the configured Azure Foundry deployment, then dispatches a separate real Codex CLI reviewer when a validated PR revision is ready. The reviewer is queued until its session actually starts. The board state alone is not proof a model is currently running.

## Required context sequence for both roles

1. Read the pinned official Fabric skills catalog and every required skill resource.
2. Read the actual assignment and source/review revision.
3. Pin `wikiMaster` with `wiki_catalog`.
4. Read every catalogued page using `read_wiki_page`.
5. Verify `wiki_context_ready` before planning, writing, checks or submitting a verdict.
6. Cite the relevant page and wiki commit in implementation/review evidence.

Each MCP process owns a fresh read set. Receipts from another role or an earlier process cannot unlock it. Pages are fetched from a Git commit, not whichever version happens to be current during each call. Missing pages fail closed. Publishing or reviewing checks that the wiki head has not moved. A reviewer must use the developer validation's wiki revision when that validation has a wiki receipt. A mismatch stops for operator reconciliation.

These receipts establish what full text was delivered through tools. They do not prove comprehension, compliance or the quality of the model's reasoning. That still requires review of the resulting work and evidence.

## Where to observe work

| Surface | What it shows |
|---|---|
| Parent issue discussion | Claim, agent plan, clarification, implementation and human gate |
| Child review task | Queued/Doing/Done review lifecycle |
| PR commits and discussion | Actual source changes, exact-revision reviewer findings and vote |
| Private local `.runs/assignments/<issue>/<role>/` | Session logs, validation and wiki page-read receipts |
| Worker journal | Durable dispatch state; not a public artifact |

An approval stays separate from a merge. The parent remains Doing with `ready-for-human-merge` until a completed PR is observed. Neither agent may merge, bypass protection or change permissions.

## Recovery and migration

If requirements change after claim, an agent asks for clarification, a process times out, or wiki context changes during work, stop and reconcile; do not reset the journal to force another run. Earlier historical PRs may have reviewer approval without wiki-read evidence. Do not rewrite their receipts or retroactively claim they passed this newer gate.
