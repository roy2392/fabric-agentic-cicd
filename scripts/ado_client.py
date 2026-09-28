"""Azure DevOps calls pinned to the demo organization."""
import json,urllib.request,urllib.error
from fabric_agents.preflight import ReadClient,NoRedirect
from scripts.agent_auth import token_for
from scripts.settings import ado_root, ado_project_path
class AdoClient(ReadClient):
 def __init__(self,token=None,role='developer'):
  super().__init__(ado_root(),token or token_for(role,'499b84ac-1321-427f-aa17-267ca6975798'))
 def safe_url(self,path):
  if path.startswith('fabric-agents/'):
   path=ado_project_path()+'/'+path[len('fabric-agents/'):]
  return super().safe_url(path)
 def request(self,method,path,body=None,content_type='application/json',extra=None):
  request=urllib.request.Request(self.safe_url(path),data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Authorization':'Bearer '+self.token,'Content-Type':content_type,**(extra or {})})
  try:
   with urllib.request.build_opener(NoRedirect()).open(request,timeout=60) as response:
    raw=response.read();return response.status,dict(response.headers),json.loads(raw) if raw else {}
  except urllib.error.HTTPError as e:
   try:message=json.load(e).get('message','')
   except ValueError:message=''
   raise RuntimeError(f'Azure DevOps HTTP {e.code}: {message[:700]}') from None
