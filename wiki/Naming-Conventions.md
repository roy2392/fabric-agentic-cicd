# Naming Conventions

| Artifact | Pattern | Loyalty example |
|---|---|---|
| Source system | lowercase identifier | `loyalty` |
| Source configuration | `configuration/<source>/<source>.json` | `configuration/loyalty/loyalty.json` |
| Source pipeline | `pl_ingest_<source>_bronze` | `pl_ingest_loyalty_bronze` |
| Bronze table | `<source>.<dataset>` | `loyalty.loyalty_members` |
| Raw snapshot directory | `Files/raw/<source>/<dataset>/<run_timestamp>/` | Timestamp-specific loyalty snapshot |
| Feature branch | `codex/wi-<id>-<purpose>` | Automatic lane uses `codex/wi-<id>-automatic` |
| Board dispatch tag | exact `dev-agent` token | `dev-agent` |
| Pause tag | `agent-paused` | Prevents further automatic work |
| Review task tag | `review-agent` | Assigned to the independent reviewer |
| Human merge marker | `ready-for-human-merge` | Parent remains Doing until merge is observed |

Source identifiers follow the metadata identifier rules. Reserve `_meta_` column names for the loader. A cloned Fabric pipeline needs a new logical ID; renaming the display name alone is insufficient. Never reuse an old feature workspace ID as if it were a current deployment target.

Wiki source filenames use hyphens for spaces and directories for child pages. The source/table hierarchy is `Table-Inventory/loyalty/loyalty_members.md`. Keep the flat legacy pages as historical evidence and compatibility links.
