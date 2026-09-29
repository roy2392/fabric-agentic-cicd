# loyalty

Synthetic multi-tenant loyalty membership data used to demonstrate metadata-driven bronze ingestion, ambiguity handling, independent review and human-controlled release.

| Fact | Value |
|---|---|
| Source type | Azure SQL Database |
| Source schema | `agent_demo` |
| Source object | `agent_demo.loyalty_members` |
| Configuration | `configuration/loyalty/loyalty.json` |
| Pipeline | `pl_ingest_loyalty_bronze` |
| Shared loader | `bronze_loader` |
| Bronze schema | `loyalty` in the bronze lakehouse |
| Connection | Environment-owned SQL connection; original load used Entra service principal and VNet gateway |
| Extraction | Full snapshot; no watermark predicate |
| Watermark metadata | `updated_at` (`datetime2`) |
| Key | Ordered composite `tenant_id`, `member_id`, confirmed by the human |

Connection credentials are not part of source metadata or this wiki. The selected environment's private manifest owns bindings. Direct desktop SQL connectivity is a separate operator path; historical private-gateway execution does not describe every current firewall setting.

## Tables

| Dataset | Source | Key | Watermark | Detail |
|---|---|---|---|---|
| loyalty_members | `agent_demo.loyalty_members` | `tenant_id` + `member_id` | `updated_at` | [Columns, queries and history](/Table-Inventory/loyalty/loyalty_members) |

The seed deliberately contains `member_id=1` in two tenants. Treating that column alone as the business key fails uniqueness validation. The confirmed composite key preserves both entities.

Read the preserved [Loyalty source evidence](/Loyalty-source) for the original run and correction history. Do not reuse retired feature resources merely because their identifiers remain in that evidence.
