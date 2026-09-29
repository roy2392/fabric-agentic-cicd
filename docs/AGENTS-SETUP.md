# Configure the real two-agent workflow

The portable Fabric deployer and the model/PR demonstration are separate entry points. Deployment requires no model subscription. The real agent loop requires Claude Code with an existing Azure Foundry Claude deployment and Codex CLI with a supported authenticated model. Install those CLIs from their official distributions on your runner/host.

## Operator setup

Use your own Azure DevOps organization/project, solution repository and project wiki. Configure a Git-managed authoring workspace on the selected capacity. Deploy the shared lakehouses/notebook/template there first using a separate target config, then connect it to your Azure DevOps solution repo and commit its Fabric definitions into `/fabric`. Fabric Git export supplies the platform logical IDs. Commit a root `EXPECTED_GIT_ITEMS` file containing the count of governed items. Create a `/Platform runbook` wiki page describing the shared framework and source onboarding scope.

This authoring workspace is distinct from the API-managed CD target. Once Git-connected, it must be updated through reviewed Git sync; `scripts.deploy` will refuse to push definitions to it directly.

Create two Entra applications with separate certificates. Register each service principal in Azure DevOps. The optional `scripts.create_agent_identities` helper creates certificate identities from your runtime manifest, but does not register them in Azure DevOps or grant access. Have an administrator review these grants:

| Identity | Grants | Explicit restrictions |
|---|---|---|
| Developer | Work-item read/edit, feature-branch contribution, wiki updates, PR creation; Fabric feature workspace lifecycle; use of the SELECT-only SQL and Git connections | Deny direct main contribution, force push and policy bypass; no SQL write/admin |
| Reviewer | Independent Git/wiki/work-item reads and PR comments/vote | No source writes, main writes, bypass, Fabric access or SQL access |
| Human operator | Required reviewer and merge authority | Never substituted by either model's vote |

Enable required Fabric service-principal/workspace creation/Git tenant settings only for the approved demo identities/group. If your Fabric and Azure DevOps regions require cross-geo export, have the tenant administrator approve the narrowly scoped setting. The repo never silently changes tenant switches.

Protect Azure DevOps main with two minimum reviewers, an explicit required reviewer list containing the reviewer identity and human operator, reset-on-source-push, and no agent bypass. `scripts.protect_main` creates these policies from the manifest when no matching policy already exists. Creating policies does not set Git security ACLs: configure and verify those separately.

Create a work item tagged `dev-agent` for the synthetic loyalty source. The demo intentionally starts with `member_id` as the stated key. Only after the actual primary-key failure should the human clarify `tenant_id + member_id`; the runtime accepts `KEY_CONFIRMATION {"primary_key_columns":["tenant_id","member_id"]}` only from `operator_ado_id`.

## Local runtime configuration

Copy `config/agents.example.json` to an ignored local path. Fill in your actual IDs, organization/project/repo names, work-item ID, configured developer-owned Fabric Git connection, SELECT-only SQL connection, and Foundry settings. The wiki repository normally uses `wikiMaster`; the bounded demo currently assumes this Azure DevOps project-wiki convention.

Place each role's `private.key` and `public.pem` in `.runs/identities/<role>/`, readable only by the local owner. Supply a reviewer-private checklist; customize `examples/reviewer-checklist.example.md` and keep the runtime version outside both source clones.

```bash
python -m scripts.configure_agents --config config/agents.local.json --reviewer-checklist /secure/path/checklist.md
python -m scripts.probe_agents developer
python -m scripts.probe_agents reviewer
python -m scripts.developer_dispatcher
# Run again when a real job finishes, a human clarification arrives, or review changes are requested.
python -m scripts.reviewer_dispatcher
```

The developer dispatcher is a one-shot event consumer, not an installed background service. Pending jobs and waiting-human states return without launching another model. The reviewer only reviews active PRs at pinned source/wiki revisions. Review findings feed the next developer turn; the human performs the merge.

Both agents must read the locked Fabric skill files before project tools. They can read further skill references through `read_fabric_skill`. Their normal shell/plugin execution remains disabled; loading skills through this bounded reader is deliberate and directly auditable.

## Retained scope

The adapters are intentionally specific to one synthetic loyalty onboarding issue at a time. They are not a generic autonomous data engineer, a hosted multi-user service, or an OS isolation boundary. Use a separate host/OS account for each role if required by your security model. Do not run the historical tenant-specific closeout scripts from another environment; those scripts are not part of the public distribution.

## Additional board work

For scoped local utilities and documentation tasks, use the [board assignment runner](BOARD-ASSIGNMENTS.md). It creates separate developer/reviewer cards and isolated clones, enforces the official skills gate, and runs developer tests in a macOS sandbox. These follow-up tasks do not mutate Fabric or replace live ingestion evidence.
