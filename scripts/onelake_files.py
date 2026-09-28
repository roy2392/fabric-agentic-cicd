"""Small, explicit OneLake file transfers for demo metadata and evidence."""
import re
import urllib.request,urllib.error,urllib.parse
from uuid import UUID
from fabric_agents.preflight import NoRedirect
class OneLake:
 def __init__(self,token,workspace,item,host="onelake.dfs.fabric.microsoft.com"):
  if not re.fullmatch(r"(?:[a-z0-9-]+-)?onelake\.dfs\.fabric\.microsoft\.com",host):raise ValueError("Invalid OneLake host")
  self.base=f'https://{host}/{UUID(workspace)}/{UUID(item)}/Files/'
  self.token=token
 def request(self,method,path,query='',body=None,extra=None,return_headers=False):
  if path.startswith('/') or any(x in ('..','') for x in path.split('/')):raise ValueError('Unsafe relative file path')
  url=self.base+urllib.parse.quote(path,safe='/')+query
  headers={'Authorization':'Bearer '+self.token,'x-ms-version':'2021-06-08',**(extra or {})}
  req=urllib.request.Request(url,data=body,method=method,headers=headers)
  with urllib.request.build_opener(NoRedirect()).open(req,timeout=60) as r:
   content=r.read()
   return (content,dict(r.headers)) if return_headers else content
 def create(self,path,body):
  try:
   existing=self.request('GET',path)
   if existing!=body:raise RuntimeError('Existing file differs; explicit update required')
   return
  except urllib.error.HTTPError as e:
   if e.code!=404:raise
  self.request('PUT',path,'?resource=file',b'',{'If-None-Match':'*'})
  self.request('PATCH',path,'?action=append&position=0',body)
  self.request('PATCH',path,f'?action=flush&position={len(body)}',b'')
  if self.request('GET',path)!=body:raise RuntimeError('Upload verification failed')
 def replace(self,path,expected,body):
  current,headers=self.request('GET',path,return_headers=True)
  if current==body:return
  if current!=expected:raise RuntimeError('Metadata changed outside the recorded revision')
  etag={k.lower():v for k,v in headers.items()}.get('etag')
  if not etag:raise RuntimeError('Missing metadata concurrency token')
  self.request('PUT',path,'?resource=file',b'',{'If-Match':etag})
  self.request('PATCH',path,'?action=append&position=0',body)
  self.request('PATCH',path,f'?action=flush&position={len(body)}',b'')
  if self.request('GET',path)!=body:raise RuntimeError('Updated metadata verification failed')
