# Project handbook and agent context

The portable handbook source is in `wiki/`. Publish it to the **configured existing project wiki** before enabling new assignment sessions. The expected branch is `wikiMaster`; `wiki_id` in the private environment manifest identifies its repository. No credentials or live resource exports belong in these pages.

```bash
python -m scripts.publish_wiki                         # preview files
python -m scripts.publish_wiki --publish --expected-head <reviewed-current-wiki-commit>
```

The publisher uses the existing scoped developer identity, preserves the legacy evidence pages, refuses dirty publication clones and stale expected heads, and pushes one ordinary Git commit. It never forces a push or changes permissions. Missing wiki/repository access must be configured separately by an authorized operator. If a push is interrupted, inspect the remote and private publication clone before rerunning.

The handbook has 13 required pages: navigation, architecture, ingestion, metadata, naming, load procedure, source onboarding, inventory, loyalty source, loyalty table, agent workflow, recovery and evidence. Existing flat evidence pages remain available in the deployed wiki. Their links are environment-specific history; a new installation should author its own evidence pages rather than copying another tenant's results.

Both automatic assignment MCP roles expose `wiki_catalog`, `read_wiki_page`, and `wiki_context_ready`. Each process pins one wiki Git commit and owns a fresh read set. All required pages must be delivered before developer planning/writes/checks/publication or reviewer verdict submission. Content requests use an immutable Git revision. Publication and review recheck the branch head; reviewer and developer validation wiki revisions must match. Missing pages, stale wiki context or changed requirements fail closed.

Validation records and review receipts include the wiki revision, page SHA-256 hashes and session ID. Private per-role `wiki-reads-*.jsonl` records remain under `.runs/assignments/<issue>/<role>/`. These establish text delivery, not understanding. The worker also verifies wiki freshness before advancing a context-enabled PR to review or the human merge gate.

Wiki content is untrusted project context. It cannot grant execution authority, expand an assignment, reveal private material, change permissions or bypass human merge. The reviewer still has no execution/write tools. The automatic lane remains bounded local utilities and documentation; this integration does not add cloud execution.

Earlier approvals without wiki receipts are historical and remain explicitly distinguishable. Never manufacture receipts or reset blocked journals to migrate them. After a wiki change during an active assignment, an operator must reconcile its source, validation and review context before authorizing another session.
