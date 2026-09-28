# Additional board assignments

The original dispatcher intentionally serves one Fabric onboarding issue. A separate assignment runner handles three follow-up demo tasks: metadata preflight, recorded-run reporting, and an operator recovery/meeting playbook. These change only local utility, test and documentation files in the deployer's Azure DevOps solution repository. They do not deploy Fabric items or alter SQL data.

## Run

Configure the two identities and Foundry authentication using [AGENTS-SETUP.md](AGENTS-SETUP.md). With operator Azure CLI authentication selected, explicitly create the board entries:

```bash
python -m scripts.create_demo_assignments
```

This creates three developer Issues and three child reviewer Tasks, assigning the corresponding service-principal identities. It registers each generated issue ID, branch and exact allowed file list under ignored `.runs/assignments/<issue>/task.json`. Read those IDs from the command output. The operator moves active board cards to Doing; the runner does not claim completed work from a tag.

```bash
python -m scripts.assignment_dispatcher ISSUE_ID developer
python -m scripts.assignment_dispatcher ISSUE_ID reviewer
# Only after actual reviewer findings or another concrete state change:
python -m scripts.assignment_dispatcher ISSUE_ID developer --reason "Address the current independent review findings"
python -m scripts.assignment_dispatcher ISSUE_ID reviewer --reason "Review the corrected source revision"
```

Use one running process per role and issue. Separate issues have isolated clones and can run concurrently. Inspect the state, validation reports, session logs and actual PR between iterations. The runner is single-shot; no unattended polling loop or schedule is installed. Stop at three correction cycles and ask the human if requirements remain disputed.

## Controls and proof

- All model sessions use the same locked upstream skills and per-session read gate.
- Developer writes are limited to the registered files. No Fabric, arbitrary shell, merge or policy tool is exposed.
- Tests use a fixed unittest command under macOS `sandbox-exec`: network blocked, home/temp data restricted to the assigned clone/runtime/scratch, writes restricted to scratch, and credential-service lookups denied. The current test executor fails closed on other operating systems; the general deployment CLI remains cross-platform.
- Passing test evidence is bound to file hashes and the published source commit. Changed files require fresh checks before publication.
- The reviewer reads a separate clone pinned to the PR source/target, sees the relevant private checklist and recorded local evidence, and cannot execute tests or change code. It posts a real verdict using the reviewer identity.
- Both the reviewer and human remain required on each PR. The operator verifies the recorded approval and completes the child review task; the developer Issue stays open until the human merges and the operator verifies closure.
- Utility tests and synthetic fixtures are not live Fabric runs. Historical live pipeline evidence remains a separate proof layer.

The local dispatcher and identities still share an OS user. The test subprocess restrictions do not turn the complete multi-process system into a separate-machine security boundary. Do not store credentials in assigned source files or expose this local MCP server as a network service.
