# Security boundaries

Do not commit `.runs/`, live manifests, private keys, access tokens, SQL connection credentials or private reviewer checklists. CI checks tracked files and refuses these categories. It does not replace a dedicated secret scanner or code review.

For GitHub deployment, use OIDC scoped to one repository and protected Environment, with no broad branch wildcard. Restrict deployment to main, require environment reviewers, and grant the deployment service principal access only to its dedicated Fabric target and SELECT-only source connection. Never use a tenant Global Administrator identity in Actions.

PR checks use read-only GitHub permissions and no cloud identity. Do not change them to `pull_request_target` or execute untrusted PR code with deployment credentials. Deployment uses the checked-out main commit and environment configuration, not arbitrary workflow input shell text.

Reviewers have no Fabric token audience or execution tool. Skills are reference material and cannot override those restrictions. Processes share the host OS account: use separate OS identities or containers when stronger local isolation is required.

A source snapshot must be frozen during the demo copy/count pair. Validation catches primary-key and count problems but does not provide a transactional cross-statement source snapshot. Credentials created by the optional setup scripts expire; rotate deliberately and never reopen retired setup access automatically.
