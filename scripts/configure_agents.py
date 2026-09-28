"""Validate operator-supplied settings and create local bounded MCP configuration."""
import argparse,json,os,sys
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--reviewer-checklist',required=True);a=p.parse_args()
 m=json.loads(Path(a.config).read_text())
 for key in ('tenant_id','capacity_id','workspace_id','ado_project_id','repository_id','wiki_id','operator_object_id','operator_ado_id','developer_git_connection_id','sql_ingestion_connection_id'):UUID(m[key])
 for role in ('developer','reviewer'):
  for key in ('app_id','object_id','ado_id'):UUID(m['agents'][role][key])
  folder=ROOT/'.runs/identities'/role
  if not all((folder/x).exists() for x in ('private.key','public.pem')):raise RuntimeError('Supply role certificate files under '+str(folder))
 if m['agents']['developer']['app_id']==m['agents']['reviewer']['app_id']:raise ValueError('Agent identities must differ')
 if type(m['demo_work_item_id']) is not int or m['demo_work_item_id']<1:raise ValueError('Invalid work item')
 target=ROOT/'config/live-resources.json'
 if target.exists() and json.loads(target.read_text())!=m:raise RuntimeError('Existing runtime configuration differs; preserve it before reconfiguration')
 target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(m,indent=2)+'\n');target.chmod(0o600)
 for role in ('developer','reviewer'):(ROOT/'.runs'/role).mkdir(parents=True,exist_ok=True)
 for name in ('live-evidence','live-operations','reviewer-private'):(ROOT/'.runs'/name).mkdir(parents=True,exist_ok=True)
 checklist=ROOT/'.runs/reviewer-private/checklist.md'
 if not checklist.exists():checklist.write_text(Path(a.reviewer_checklist).read_text());checklist.chmod(0o600)
 config={'mcpServers':{'demo':{'command':sys.executable,'args':['-m','scripts.developer_mcp'],'env':{'PYTHONPATH':str(ROOT)}}}}
 (ROOT/'.runs/developer/mcp.json').write_text(json.dumps(config,indent=2))
 print('Local agent settings ready. Verify tenant/ADO permissions before dispatch; no permissions were granted.')
if __name__=='__main__':main()
