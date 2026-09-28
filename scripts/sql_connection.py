"""Create a tested private SQL connection without exposing credentials."""
import json,sys
from pathlib import Path
from fabric_agents.preflight import access_token
from scripts.live_fabric import FabricClient
ROOT=Path(__file__).resolve().parents[1]
def main(role):
 if role not in ('setup','ingestion'): raise ValueError('Unknown role')
 p=ROOT/'config/live-resources.json';m=json.loads(p.read_text())
 t,_=access_token(m['tenant_id'],'https://api.fabric.microsoft.com');c=FabricClient(t)
 name='fabric-agents-sql-'+role
 matches=[x for x in c.list_fabric('connections') if x.get('displayName')==name]
 if len(matches)>1:raise RuntimeError('Ambiguous connection')
 if matches:result=matches[0]
 else:
  secret=json.loads((ROOT/'.runs/sql-identities'/f'{role}.json').read_text())['secretText']
  body={'connectivityType':'VirtualNetworkGateway','gatewayId':m['gateway_id'],'displayName':name,
   'connectionDetails':{'type':'SQL','creationMethod':'SQL','parameters':[
    {'dataType':'Text','name':'server','value':m['sql_server']+'.database.windows.net'},
    {'dataType':'Text','name':'database','value':m['sql_database']}]},
   'privacyLevel':'Organizational','credentialDetails':{'singleSignOnType':'None','connectionEncryption':'Encrypted','skipTestConnection':False,
    'credentials':{'credentialType':'ServicePrincipal','tenantId':m['tenant_id'],
     'servicePrincipalClientId':m['sql_identities'][role]['app_id'],'servicePrincipalSecret':secret}}}
  _,_,result=c.request('POST','connections',body)
 if result['gatewayId']!=m['gateway_id']:raise RuntimeError('Unexpected gateway')
 m['sql_'+role+'_connection_id']=result['id'];p.write_text(json.dumps(m,indent=2)+'\n')
 (ROOT/'.runs/live-evidence'/f'sql-{role}-connection.json').write_text(json.dumps(result,indent=2))
 print(role,'connection',result['id'],'test skipped:',result['credentialDetails'].get('skipTestConnection'),flush=True)
if __name__=='__main__':main(sys.argv[1])
