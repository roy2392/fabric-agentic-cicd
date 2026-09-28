"""Deploy and submit demo pipelines with durable submission records."""
import base64,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def deploy(client,workspace,name,content):
 if not re.fullmatch('[a-zA-Z][a-zA-Z0-9_]*',name):raise ValueError('Invalid name')
 matches=[x for x in client.list_fabric(f'workspaces/{workspace}/items') if x['displayName']==name]
 if len(matches)>1:raise RuntimeError('Ambiguous pipeline')
 definition={'parts':[{'path':'pipeline-content.json','payloadType':'InlineBase64','payload':base64.b64encode(json.dumps(content).encode()).decode()}]}
 if matches:return matches[0]
 return client.operation('create-'+name,f'workspaces/{workspace}/items',{'displayName':name,'type':'DataPipeline','definition':definition})
def submit(client,workspace,item,key,body=None):
 if not re.fullmatch('[a-zA-Z0-9_-]+',key):raise ValueError('Invalid journal key')
 path=ROOT/'.runs/live-operations'/f'{key}.json'
 if path.exists():raise RuntimeError('Submission already recorded; reconcile instead of resubmitting')
 path.write_text(json.dumps({'state':'submitting','item_id':item}))
 status,headers,_=client.request('POST',f'workspaces/{workspace}/items/{item}/jobs/instances?jobType=Pipeline',body or {})
 location={k.lower():v for k,v in headers.items()}.get('location')
 if not location:raise RuntimeError('Missing job location; reconcile before retry')
 client.safe_url(location);path.write_text(json.dumps({'state':'submitted','location':location,'status':status},indent=2))
 print('Submitted',key,location,flush=True)
