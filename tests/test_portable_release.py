import json,subprocess,sys
from pathlib import Path
import pytest
from scripts.deploy import validate,plan,build
from scripts.skill_registry import SkillSession,REQUIRED,verify
from scripts.ado_client import AdoClient
ROOT=Path(__file__).resolve().parents[1]
def config():return json.loads((ROOT/'deployment/target.example.json').read_text())
@pytest.mark.parametrize('field,value',[('tenant_id','default'),('onelake_host','evil.example'),('onelake_host','onelake.dfs.fabric.microsoft.com.evil.example'),('source_frozen',False),('expected_source_rows',True),('workspace_name','../other')])
def test_target_rejects_unsafe_or_implicit_values(field,value):
 c=config();c[field]=value
 with pytest.raises((ValueError,TypeError)):validate(c)
def test_deploy_plan_does_not_authenticate(monkeypatch):
 import scripts.deploy as d
 monkeypatch.setattr(d,'access_token',lambda *args:pytest.fail('A plan must not acquire credentials'))
 assert len(plan(config())['items'])==5

def test_skill_gate_requires_reads_and_rejects_traversal():
 s=SkillSession('reviewer')
 with pytest.raises(RuntimeError,match='Read the pinned'):s.require_ready()
 with pytest.raises(ValueError):s.read_resource('../../config/live-resources.json')
 for path in REQUIRED:s.read_resource(path)
 assert s.require_ready()['commit']==verify()['commit']
 # A new model process cannot reuse another process's readiness.
 with pytest.raises(RuntimeError):SkillSession('reviewer').require_ready()

def test_actual_mcp_rejects_work_before_skills():
 for role,tool in [('developer','read_task'),('reviewer','read_review_context')]:
  req={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':tool,'arguments':{}}}
  p=subprocess.run([sys.executable,'-m','scripts.'+role+'_mcp'],input=json.dumps(req)+'\n',capture_output=True,text=True,check=True,cwd=ROOT)
  result=json.loads(p.stdout)['result']
  assert result['isError'] and 'Read the pinned' in result['content'][0]['text']

def test_ado_targets_configured_project_and_rejects_other_host(tmp_path,monkeypatch):
 p=tmp_path/'settings.json';p.write_text(json.dumps({'ado_organization':'example-org','ado_project':'Data Team','ado_repository':'solution'}));monkeypatch.setenv('FABRIC_AGENTS_MANIFEST',str(p))
 c=AdoClient('test-token')
 assert c.safe_url('fabric-agents/_apis/git')=='https://dev.azure.com/example-org/Data%20Team/_apis/git'
 with pytest.raises(Exception):c.safe_url('https://dev.azure.com/another-org/_apis/git')

def test_generated_pipeline_has_portable_bindings_and_fixed_timestamp():
 m={'workspace_id':'target-workspace','configuration_lakehouse_id':'config-lake','bronze_lakehouse_id':'bronze-lake','bronze_loader_notebook_id':'target-notebook','sql_ingestion_connection_id':'sql-connection','sql_database':'source-db'}
 p=build(m);activities=p['properties']['activities']
 assert activities[0]['typeProperties']['value']['value'].endswith("'yyyy-MM-ddTHH:mm:ssZ')")
 notebook=next(a for a in activities if a['name']=='LoadBronze')
 assert notebook['typeProperties']['workspaceId']=='target-workspace'
 assert notebook['typeProperties']['notebookId']=='target-notebook'
 assert p['properties']['concurrency']==1
