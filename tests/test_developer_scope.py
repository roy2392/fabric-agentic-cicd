import pytest
import base64
import json
from scripts import developer_runtime
from scripts.developer_runtime import validate_metadata

def metadata(**updates):
    value={'dataset_name':'loyalty_members','source_schema':'agent_demo','source_table':'loyalty_members','primary_key_columns':['member_id'],'watermark_column':'updated_at'}
    value.update(updates)
    return [value]

def test_stated_key_is_preserved_until_real_validation():
    assert validate_metadata(metadata())[0]['primary_key_columns']==['member_id']

@pytest.mark.parametrize('changes',[
    {'source_table':'other_customer_table'},
    {'source_schema':'dbo'},
    {'source_table':"loyalty_members]; DROP TABLE agent_demo.loyalty_members;--"},
    {'primary_key_columns':['member_id','member_id']},
    {'primary_key_columns':[]},
    {'credential':'should-not-be-in-metadata'},
])
def test_source_tool_rejects_scope_and_query_injection(changes):
    with pytest.raises(ValueError):validate_metadata(metadata(**changes))

def test_serialization_reconciliation_rejects_behavior_change(tmp_path, monkeypatch):
    monkeypatch.setattr(developer_runtime, 'HOME', tmp_path)
    monkeypatch.setattr(developer_runtime, 'git', lambda *args: '')
    folder=tmp_path/'solution/fabric/pl_ingest_loyalty_bronze.DataPipeline'
    folder.mkdir(parents=True)
    (folder/'pipeline-content.json').write_text('{"properties":{"query":"SELECT 1"}}')
    class Client:
        def operation(self,key,path,body):
            assert path.endswith('/getDefinition')
            return {'definition':{'parts':[{'path':'pipeline-content.json','payload':base64.b64encode(b'{"properties":{"query":"DELETE FROM source"}}').decode()}]}}
        def list_fabric(self,path):return []
    state={'workspaceHead':'same','remoteCommitHash':'same','changes':[{'workspaceChange':'Modified','remoteChange':None,'itemMetadata':{'displayName':'pl_ingest_loyalty_bronze','itemIdentifier':{'objectId':'pipeline'}}}]}
    with pytest.raises(RuntimeError,match='Semantic workspace change'):
        developer_runtime.reconcile_serialization(Client(),{'demo_run':{'workspace_id':'workspace'}},state)

def test_serialization_reconciliation_never_accepts_shared_item_edit():
    state={'workspaceHead':'same','remoteCommitHash':'same','changes':[{'workspaceChange':'Modified','itemMetadata':{'displayName':'bronze_loader'}}]}
    with pytest.raises(RuntimeError,match='Unexpected workspace edits'):
        developer_runtime.reconcile_serialization(None,{'demo_run':{'workspace_id':'workspace'}},state)

def test_agent_cannot_authorize_its_own_key_change(monkeypatch):
    monkeypatch.setattr(developer_runtime,'manifest',lambda:{'demo_work_item_id':1,'operator_ado_id':'human'})
    class Client:
        def get(self,path):return {'comments':[{'id':1,'createdBy':{'id':'developer'},'text':'KEY_CONFIRMATION {&quot;primary_key_columns&quot;:[&quot;tenant_id&quot;,&quot;member_id&quot;]}'}]}
    monkeypatch.setattr(developer_runtime,'ado',lambda:Client())
    assert developer_runtime.approved_keys()==['member_id']

def test_verified_human_comment_authorizes_key_change(monkeypatch):
    monkeypatch.setattr(developer_runtime,'manifest',lambda:{'demo_work_item_id':1,'operator_ado_id':'human'})
    class Client:
        def get(self,path):return {'comments':[{'id':1,'createdBy':{'id':'human'},'text':'KEY_CONFIRMATION {&quot;primary_key_columns&quot;:[&quot;tenant_id&quot;,&quot;member_id&quot;]}'}]}
    monkeypatch.setattr(developer_runtime,'ado',lambda:Client())
    assert developer_runtime.approved_keys()==['tenant_id','member_id']
