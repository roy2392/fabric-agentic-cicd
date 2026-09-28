"""Operator-only synthetic SQL bootstrap through the private Fabric gateway."""
import base64,json,uuid
from pathlib import Path
from scripts.live_fabric import FabricClient
from fabric_agents.preflight import access_token
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=ROOT/'config/live-resources.json';m=json.loads(p.read_text())
 t,_=access_token(m['tenant_id'],'https://api.fabric.microsoft.com');c=FabricClient(t)
 sid='0x'+uuid.UUID(m['sql_identities']['ingestion']['app_id']).bytes_le.hex()
 sql=(ROOT/'demo/synthetic-source.sql').read_text()+f"\nIF DATABASE_PRINCIPAL_ID('fabric-agents-sql-ingestion') IS NULL CREATE USER [fabric-agents-sql-ingestion] WITH SID = {sid}, TYPE = E;\nGRANT SELECT ON SCHEMA::agent_demo TO [fabric-agents-sql-ingestion];\nSELECT COUNT(*) AS source_rows FROM agent_demo.loyalty_members;"
 content={'properties':{'activities':[{'name':'SeedSyntheticLoyalty','type':'Script','dependsOn':[],
  'policy':{'timeout':'0.00:10:00','retry':0,'secureInput':False,'secureOutput':False},
  'typeProperties':{'scripts':[{'type':'Query','text':sql}],'scriptBlockExecutionTimeout':'00:05:00'},
  'externalReferences':{'connection':m['sql_setup_connection_id']}}]}}
 name='operator_sql_setup';ws=m['workspace_id']
 matches=[x for x in c.list_fabric(f'workspaces/{ws}/items') if x['displayName']==name]
 if len(matches)>1:raise RuntimeError('Ambiguous pipeline')
 item=matches[0] if matches else c.operation('create-sql-setup-pipeline',f'workspaces/{ws}/items',{
  'displayName':name,'type':'DataPipeline','definition':{'parts':[{'path':'pipeline-content.json','payloadType':'InlineBase64','payload':base64.b64encode(json.dumps(content).encode()).decode()}]}})
 m['sql_setup_pipeline_id']=item['id'];p.write_text(json.dumps(m,indent=2)+'\n')
 journal=ROOT/'.runs/live-operations/sql-seed-job.json'
 if journal.exists(): print('Existing SQL job journal; reconcile instead of submitting again');return
 journal.write_text(json.dumps({'state':'submitting','item_id':item['id']}))
 status,headers,result=c.request('POST',f'workspaces/{ws}/items/{item["id"]}/jobs/instances?jobType=Pipeline',{})
 h={k.lower():v for k,v in headers.items()}
 location=h.get('location','');c.safe_url(location)
 journal.write_text(json.dumps({'state':'submitted','location':location,'status':status},indent=2))
 print('SQL seed job submitted',location,flush=True)
if __name__=='__main__':main()
