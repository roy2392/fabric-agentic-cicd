# Deployment guide

## Prerequisites owned by the deployer

1. Python 3.12, Git and Azure CLI; an active Fabric capacity in a supported region.
2. An identity allowed by your Fabric tenant settings, with permission to create the dedicated target (or access to an existing dedicated target), use the selected capacity, write items and OneLake files, and use the SQL connection.
3. SQL table `agent_demo.loyalty_members`, seeded from `demo/synthetic-source.sql`. A database administrator performs this once and grants the ingestion identity SELECT only on `agent_demo`. Keep source data frozen during demo execution.
4. A tested Fabric SQL connection using that ingestion identity. For private SQL, configure a VNet data gateway on a supported capacity/region and a private endpoint/DNS route. Tenant settings, gateway creation, source credentials and identity grants require your administrator; cloning a repo cannot supply them.

The example target IDs are deliberately invalid placeholders. Copy `deployment/target.example.json` into ignored `config/target.local.json` and replace every identity/resource value. A target contains no passwords or tokens. `onelake_host` must be the appropriate Fabric OneLake DFS host for your environment; this release supports commercial Azure, not sovereign-cloud endpoints.

## Optional private SQL infrastructure

`infra/main.bicep` provisions Entra-only Basic Azure SQL, a VNet, a delegated Fabric-gateway subnet, SQL private endpoint and private DNS. Public access stays disabled. It does not create a Fabric capacity or gateway, enable tenant settings, create source credentials, or change an existing SQL administrator.

Run against a new dedicated resource group after reviewing costs and your tenant policy:

```bash
az provider register --namespace Microsoft.PowerPlatform
az deployment group what-if --resource-group YOUR_DEMO_RG --template-file infra/main.bicep \
  --parameters prefix=YOUR_UNIQUE_PREFIX sqlAdminObjectId=YOUR_ADMIN_OBJECT_ID sqlAdminLogin=YOUR_ADMIN_NAME
az deployment group create --resource-group YOUR_DEMO_RG --template-file infra/main.bicep \
  --parameters prefix=YOUR_UNIQUE_PREFIX sqlAdminObjectId=YOUR_ADMIN_OBJECT_ID sqlAdminLogin=YOUR_ADMIN_NAME
```

The address space is `10.84.0.0/24`; change it before deployment if it overlaps your network. Seed SQL from an authorized private-network client. Never enable public SQL as a workaround for a policy restriction.

## Local deployment

Authenticate explicitly to your tenant, then run the README's plan/apply commands. `plan` is offline and has no cloud writes. `apply` verifies the capacity, SQL connection and target, discovers IDs, deploys definitions, and stages metadata. `--smoke` runs the pipeline once and checks every activity and row count. A deployment without `--smoke` is reported as deployed, not runtime-validated.

The main target must not be Git-connected. Use a different workspace for Git-integrated agent authoring. Existing unrelated items, mismatched capacity, unexpected metadata, active jobs, or an uncertain earlier submission stop the deployer instead of overwriting state.

## GitHub Actions with OIDC

Fork or use this template repository. Create an Environment such as `demo`, restrict it to main, and configure human reviewers. Create a dedicated Entra app/service principal and a federated credential with:

```json
{
  "name": "github-demo",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:YOUR_OWNER/YOUR_REPO:environment:demo",
  "audiences": ["api://AzureADTokenExchange"]
}
```

Grant this identity the Fabric permissions described above, scoped to the target and source connection. Do not grant it Azure DevOps reviewer, tenant-admin or SQL-administrator access. If an existing target is pre-provisioned, avoid granting workspace-creation rights.

Set these **Environment variables**, not secrets:

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | Deployment app client ID |
| `AZURE_TENANT_ID` | Fabric tenant ID |
| `FABRIC_TARGET_JSON` | Complete target JSON, matching the same tenant |

No Azure client secret is needed. In Actions, run **Deploy Fabric**, select the environment and leave the smoke check enabled. The workflow only deploys from main, repeats CI checks, uses the approved environment's OIDC identity, and uploads only deployment reports and operation journals. No raw token or credential folders are uploaded.

The Environment must be protected **before** federated trust is granted. Configure GitHub main branch protection to require the `verify` check, pull-request approval and no force pushes. Repository admins retain control over these protections.

References: [Azure OIDC setup](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect), [GitHub environment protection](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment).

## Failed or interrupted releases

Read `.runs/deploy/<workspace>.json` and `.runs/live-operations/*.json`, or their Actions artifact. Smoke submission state also lives in the configuration lakehouse under `Files/deployment/releases/<fingerprint>.json`. If it says submitting without a location, inspect the actual job history and reconcile that marker; do not erase it and resubmit blindly. Re-running the same completed fingerprint monitors its recorded job instead of creating a new job.

Definitions can be redeployed from an earlier reviewed source commit. That is **not** a data rollback. Preserve raw snapshots, Delta history and audit records; review any data recovery against later valid writes. The deployer does not delete cloud infrastructure on failure.
