-- Dedicated demo schema only. Execute against the explicitly selected demo database.
-- Staged trap: member_id alone is not unique across tenants.
IF SCHEMA_ID('agent_demo') IS NULL EXEC('CREATE SCHEMA agent_demo');
IF OBJECT_ID('agent_demo.loyalty_members') IS NULL
BEGIN
 CREATE TABLE agent_demo.loyalty_members (
  tenant_id nvarchar(20) NOT NULL,
  member_id int NOT NULL,
  member_name nvarchar(100) NOT NULL,
  tier nvarchar(20) NOT NULL,
  updated_at datetime2 NOT NULL,
  CONSTRAINT PK_agent_demo_members PRIMARY KEY (tenant_id, member_id)
 );
 INSERT INTO agent_demo.loyalty_members VALUES
 ('north',1,'Avery','Silver','2026-09-01T00:00:00'),
 ('south',1,'Jordan','Gold','2026-09-01T00:00:00'),
 ('north',2,'Morgan','Bronze','2026-09-01T00:00:00');
END;
-- Second snapshot (run only after baseline success):
-- UPDATE agent_demo.loyalty_members SET tier='Gold',updated_at='2026-09-02T00:00:00'
-- WHERE tenant_id='north' AND member_id=1;
