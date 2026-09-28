# Proposed GitHub deployment trust for this installation

Repository: `roy2392/fabric-agentic-cicd` (public source; no credentials or original tenant runtime data).

Environment: `demo`, restricted to the protected main branch and requiring the repository owner to approve deployments. The workflow cannot deploy PR code.

Use the existing developer application identity for this demo installation; its existing cloud/ADO permissions are unchanged except adding Contributor on the new dedicated `fabric-agentic-cicd-release-validation` workspace. Its existing SELECT-only source connection remains in use. No SQL administrator or tenant administrator access is granted.

Add one Entra federated credential:

- Issuer: `https://token.actions.githubusercontent.com`
- Subject: `repo:roy2392@66874965/fabric-agentic-cicd@1393510650:environment:demo`
- Audience: `api://AzureADTokenExchange`

This permits an approved deployment job in that exact GitHub environment to obtain short-lived tokens as the existing developer identity. No private key, password or client secret is uploaded to GitHub. Repository/environment protection must exist before trust is created. The trust can be revoked by deleting this one federated credential.

Environment variables contain only the client ID, tenant ID, and target resource configuration. The proposed change needs operator approval before execution because it gives GitHub Actions a new path to use the cloud identity. Other deployers should use a dedicated deployment identity, as described in DEPLOYMENT.md, instead of reusing an agent identity.

The immutable subject above was read from the GitHub OIDC customization API and confirmed by the deployment assertion. It identifies the same approved repository and environment.
