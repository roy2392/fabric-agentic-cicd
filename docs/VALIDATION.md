# Validation record

## Portable release

- Official Microsoft skills pinned to commit `6c11ad58c25992e5d1435ce7cd80d217d5598a31`; file hashes and upstream license preserved.
- Real Claude developer and Codex reviewer acceptance sessions both read all six required resources, followed relevant upstream references, and passed their session readiness check. These sessions were read-only and had no Fabric or PR mutation tools.
- Local regression suite: 73 tests passed, including actual stdio-MCP rejection before skills are read, separate-session read gates, target/config validation, tenant routing, timestamp precision and existing workflow protections.
- Private SQL/network Bicep compiled successfully. Compilation is not an Azure deployment.
- Portable deployment completed in a fresh isolated workspace on 2026-09-28: all seven activities succeeded; source, raw, current and history counts were all 3. The deployed notebook reported Succeeded. This ran from the local deployment CLI using operator authentication.
- GitHub workflow results are recorded after completion; local deployment does not prove GitHub OIDC deployment.

## Historical demo

The prior Azure DevOps/Fabric run completed a real primary-key clarification, successful feature run, organic independent review corrections, human merge, main sync/run and independent Delta/audit readback. A separate live Spark test verified history counts 3→4→4 across initial/change/replay snapshots. That test used staged synthetic raw data, not changed SQL extraction.

The earlier video is historical evidence. It predates direct skill loading in both model runtimes and this GitHub distribution. No claim is made that the earlier PR was reviewed using the new skill gate.
