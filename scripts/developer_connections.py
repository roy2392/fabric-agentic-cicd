"""Connect the approved developer identity to its own ADO Git credential."""
import json,os,urllib.request
from datetime import datetime,timedelta,timezone
from pathlib import Path
from fabric_agents.preflight import access_token,ReadClient,NoRedirect
from scripts.agent_auth import token_for
from scripts.settings import repo_url
from scripts.live_fabric import FabricClient
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=ROOT/'config/live-resources.json';m=json.loads(p.read_text());dev=m['agents']['developer']
 secret_path=ROOT/'.runs/identities/developer/git-credential.json'
 if not secret_path.exists():
  t,_=access_token(m['tenant_id'],'https://graph.microsoft.com');g=ReadClient('https://graph.microsoft.com/v1.0/',t)
  if g.get('applications/'+dev['application_object_id']+'?$select=passwordCredentials')['passwordCredentials']:raise RuntimeError('Existing secret without local journal; reconcile')
  body={'passwordCredential':{'displayName':'7-day demo Fabric Git connection','endDateTime':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()}}
  req=urllib.request.Request(g.safe_url('applications/'+dev['application_object_id']+'/addPassword'),data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'},method='POST')
  with urllib.request.build_opener(NoRedirect()).open(req,timeout=60) as r:credential=json.load(r)
  with os.fdopen(os.open(secret_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(credential,f)
 c=FabricClient(token_for('developer','https://api.fabric.microsoft.com'))
 matches=[x for x in c.list_fabric('connections') if x.get('displayName')=='fabric-agents-developer-git']
 if len(matches)>1:raise RuntimeError('Ambiguous connection')
 if matches:connection=matches[0]
 else:
  secret=json.loads(secret_path.read_text())['secretText']
  _,_,connection=c.request('POST','connections',{'displayName':'fabric-agents-developer-git','connectivityType':'ShareableCloud','connectionDetails':{'type':'AzureDevOpsSourceControl','creationMethod':'AzureDevOpsSourceControl.Contents','parameters':[{'dataType':'Text','name':'url','value':repo_url()+'/'}]},'credentialDetails':{'credentials':{'credentialType':'ServicePrincipal','tenantId':m['tenant_id'],'servicePrincipalClientId':dev['app_id'],'servicePrincipalSecret':secret}}})
 m['developer_git_connection_id']=connection['id'];p.write_text(json.dumps(m,indent=2)+'\n');print('Developer-owned Git connection',connection['id'])
 t,_=access_token(m['tenant_id'],'https://api.fabric.microsoft.com');operator=FabricClient(t)
 roles=operator.list_fabric('connections/'+m['sql_ingestion_connection_id']+'/roleAssignments')
 if not any(x.get('principal',{}).get('id')==dev['object_id'] for x in roles):
  operator.request('POST','connections/'+m['sql_ingestion_connection_id']+'/roleAssignments',{'principal':{'id':dev['object_id'],'type':'ServicePrincipal'},'role':'User'})
 print('Developer may use SELECT-only SQL connection; setup connection remains retired')
if __name__=='__main__':main()
