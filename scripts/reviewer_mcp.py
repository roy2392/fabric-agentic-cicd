"""Stdio MCP surface exposing only the authorized demo operations."""
import contextlib,io,json,os,sys,traceback
from scripts import reviewer_runtime as runtime
for key in list(os.environ):
 if key.startswith(('ANTHROPIC_','CLAUDE_','AZURE_')):os.environ.pop(key,None)
from scripts.skill_registry import SkillSession
SKILLS=SkillSession('reviewer')
TOOLS={
 'fabric_skill_catalog':('List the pinned Microsoft Fabric skill resources and mandatory reads.',{},SKILLS.catalog),
 'read_fabric_skill':('Read a complete, integrity-checked upstream Fabric skill resource.',{'path':{'type':'string'}},SKILLS.read_resource),
 'fabric_skills_ready':('Verify the current session has read every required Fabric skill.',{},SKILLS.require_ready),
 'read_review_context':('Refresh independent reviewer clones and read the exact PR diff, issue, evidence, wiki inventory and private checklist.',{},lambda **kw:runtime.context()),
 'read_review_file':('Read a tracked solution or wiki file pinned to the recorded review revision.',{'repository':{'type':'string','enum':['solution','wiki']},'path':{'type':'string'}},runtime.read_file),
 'submit_review':('Post an evidence-based review and vote as the reviewer identity; rejects a changed PR revision. Cannot merge.',{'source_commit':{'type':'string'},'verdict':{'type':'string','enum':['approve','changes_requested']},'body':{'type':'string'}},runtime.submit_review),
}

def handle(req):
 method=req.get('method');params=req.get('params',{})
 if method=='initialize':return {'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'fabric-demo-reviewer','version':'0.1'}}
 if method=='ping':return {}
 if method=='tools/list':return {'tools':[{'name':name,'description':desc,'inputSchema':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}} for name,(desc,props,_) in TOOLS.items()]}
 if method=='tools/call':
  name=params['name']
  if name not in TOOLS:raise ValueError('Tool outside role scope')
  try:
   if name not in ('fabric_skill_catalog','read_fabric_skill','fabric_skills_ready'):SKILLS.require_ready()
   with contextlib.redirect_stdout(io.StringIO()):result=TOOLS[name][2](**params.get('arguments',{}))
   return {'content':[{'type':'text','text':json.dumps(result,default=str)}]}
  except Exception as e:return {'isError':True,'content':[{'type':'text','text':str(e)}]}
 raise ValueError('Unsupported MCP method')
for line in sys.stdin:
 try:
  req=json.loads(line)
  if 'id' not in req:continue
  result=handle(req);response={'jsonrpc':'2.0','id':req['id'],'result':result}
 except Exception as e:response={'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32603,'message':str(e)}}
 print(json.dumps(response),flush=True)
