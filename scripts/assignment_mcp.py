"""Stdio tools for one assigned issue and one fixed role."""
import contextlib,io,json,os,sys
from scripts.assignment_runtime import Assignment
from scripts.skill_registry import SkillSession
role=sys.argv[2];runtime=Assignment(int(sys.argv[1]),role);skills=SkillSession(role)
for k in list(os.environ):
 if k.startswith(('ANTHROPIC_','CLAUDE_','AZURE_')):os.environ.pop(k,None)
T={
 'fabric_skill_catalog':('Read pinned skill catalog',{},skills.catalog),
 'read_fabric_skill':('Read complete pinned upstream resource',{'path':{'type':'string'}},skills.read_resource),
 'fabric_skills_ready':('Verify required skill reads',{},skills.require_ready),
 'read_assignment':('Read assigned board task and prepare role-specific clone; reviewer pins exact PR revision',{},runtime.context),
 'read_file':('Read a tracked or assigned file in this role clone',{'path':{'type':'string'}},runtime.read_file)}
if role=='developer':T.update({
 'plan_assignment':('For a new automatic issue, lock one to eight exact utility/test/docs paths before writes; tests=null for documentation only',{'files':{'type':'array','items':{'type':'string'}},'tests':{'type':['string','null']},'min_tests':{'type':'integer'}},runtime.plan_assignment),
 'request_clarification':('Stop an automatic assignment and ask the human for missing requirements or unsupported scope',{'question':{'type':'string'}},runtime.request_clarification),
 'write_file':('Write only an explicitly assigned file',{'path':{'type':'string'},'content':{'type':'string'}},runtime.write_file),
 'run_checks':('Run fixed local checks in a network-denied filesystem sandbox; no cloud execution',{},runtime.run_checks),
 'publish_pr':('Commit and push assigned files after fresh checks; publish evidence and require human/independent reviewers',{'summary':{'type':'string'}},runtime.publish_pr)})
else:T['submit_review']=('Publish exact-revision independent review; no merge',{'source_commit':{'type':'string'},'verdict':{'type':'string','enum':['approve','changes_requested']},'body':{'type':'string'}},runtime.submit_review)
for line in sys.stdin:
 req={}
 try:
  req=json.loads(line)
  if 'id' not in req:continue
  method=req['method'];params=req.get('params',{})
  if method=='initialize':result={'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'scoped-board-assignment','version':'1.0'}}
  elif method=='ping':result={}
  elif method=='tools/list':result={'tools':[{'name':n,'description':d,'inputSchema':{'type':'object','properties':p,'required':list(p),'additionalProperties':False}} for n,(d,p,f) in T.items()]}
  elif method=='tools/call':
   try:
    n=params['name']
    if n not in T:raise ValueError('Tool outside role scope')
    if n not in ('fabric_skill_catalog','read_fabric_skill','fabric_skills_ready'):skills.require_ready()
    with contextlib.redirect_stdout(io.StringIO()):value=T[n][2](**params.get('arguments',{}))
    result={'content':[{'type':'text','text':json.dumps(value)}]}
   except Exception as e:result={'isError':True,'content':[{'type':'text','text':str(e)}]}
  else:raise ValueError('Unsupported method')
  response={'jsonrpc':'2.0','id':req['id'],'result':result}
 except Exception as e:response={'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32603,'message':str(e)}}
 print(json.dumps(response),flush=True)
