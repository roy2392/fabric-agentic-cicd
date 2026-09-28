# Fabric agentic CI/CD

A portable Microsoft Fabric bronze-ingestion demo with a Claude developer, independent Codex reviewer, and human merge authority. All three operator/developer/reviewer runtimes use the same pinned [Microsoft Fabric skills](https://github.com/microsoft/skills-for-fabric) source.

The GitHub repository owns the application, deployment code, CI and skill lock. The optional two-agent work-item/PR loop uses an Azure DevOps project supplied by the deployer. You do not need the original author's tenant or credentials.

## Quick start: no cloud credentials

Requires Python 3.12 and Git. Linux and macOS are supported for tests and deployment; Claude Code/Codex must be installed for model sessions.

```bash
git clone https://github.com/roy2392/fabric-agentic-cicd.git
cd fabric-agentic-cicd
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock cryptography==46.0.5
python -m scripts.skill_registry --verify
python -m pytest -q
python -m fabric_agents.cli demo --output .runs/my-demo
python -m scripts.deploy plan --config deployment/target.example.json
```

The local harness is deterministic and uses scripted ticket/review events. It is not proof of real model execution or a live Fabric deployment.

## Deploy to your Fabric tenant

Bring an active Fabric capacity, an authorized Azure CLI/OIDC identity, a tested SELECT-only SQL connection, and the synthetic table from `demo/synthetic-source.sql`. The source must remain frozen during the separate copy/count statements. The private SQL/network infrastructure template is optional; it creates billable resources and requires an explicit operator deployment.

```bash
cp deployment/target.example.json config/target.local.json
# Replace the example GUIDs, database and workspace name with your own values.
az login --tenant YOUR_TENANT_ID --allow-no-subscriptions
python -m scripts.deploy plan --config config/target.local.json
python -m scripts.deploy apply --config config/target.local.json --smoke
```

The deployer creates/reconciles two schema-enabled lakehouses, the shared notebook, the template pipeline and a loyalty pipeline. IDs are discovered and bound in the target. It stages composite-key metadata and, with `--smoke`, requires seven successful activities and the expected source/raw/current counts. Submission markers in OneLake prevent a fresh CI runner from blindly resubmitting an uncertain run.

Use a dedicated target. Deployment rejects unrelated items and Git-connected workspaces: a target must have one authoritative writer. Deployment does not delete data, grant tenant permissions, create paid capacity, disable networking policy, or seed SQL implicitly.

- [Complete deployment and GitHub Actions setup](docs/DEPLOYMENT.md)
- [Configure and run the two real agents](docs/AGENTS-SETUP.md)
- [Architecture and boundaries](ARCHITECTURE.md)
- [Validation evidence and limitations](docs/VALIDATION.md)

## CI/CD

`CI` runs on every PR and push to main: pinned skill integrity, release/privacy checks, regression tests, Bicep compilation, a deployment plan and the local workflow harness. Dependencies and GitHub Actions versions are pinned.

`Deploy Fabric` is manually dispatched from main into a GitHub Environment. It reruns tests, authenticates with Azure OIDC, deploys the exact checked-out revision, validates the pipeline, and preserves the deployment evidence and operation journals. Configure required reviewers on the environment and branch protection before enabling cloud access. See the deployment guide for the exact variables and federated subject.

A workflow file is not a configured cloud identity. Each fork must configure its own environment and OIDC trust; the repository contains no reusable credentials.

## Direct use of the official skill repository

`vendor/skills-for-fabric` contains unmodified upstream skills and common references from commit `6c11ad58c25992e5d1435ce7cd80d217d5598a31`, with its MIT license. Every file is hashed in `skills.lock.json`.

The operator follows `AGENTS.md`. Both agent MCP servers expose a read-only skill catalog and file reader and block all project tools until that session has read the required upstream resources. Receipts record the role, upstream commit, file hash and timestamp. Referenced mode files remain available. Skills do not expand identity or tool permissions.

```bash
python -m scripts.probe_agents developer
python -m scripts.probe_agents reviewer
```

These real-model acceptance probes only read skills; they cannot mutate Fabric, source or PRs. They require configured Claude Foundry/Codex authentication. Agent execution and deployment are separate proof layers.

## Scope and limitations

This is a synthetic full-snapshot demo, capped at 10,000 rows. Watermark metadata is recorded but incremental SQL extraction is not implemented. The shared notebook rejects unsupported deletions, schema drift and out-of-order snapshots; consult the code before extending it. Both local model runtimes share an OS account; the separation demonstrated here is in tools and cloud identities, not an OS security boundary.

The original narrated demo preceded this portable skills/CI upgrade. It is historical evidence, not proof that these new workflows ran. Current validation is recorded separately in `docs/VALIDATION.md`.

Credentials, local target manifests, private reviewer checklists, generated definitions, recordings and raw `.runs/` data are excluded from Git. See [SECURITY.md](SECURITY.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
