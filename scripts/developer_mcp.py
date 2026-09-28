"""Stdio MCP surface exposing only the authorized demo operations."""
import contextlib,io,json,os,sys,traceback
from scripts import developer_runtime as runtime
for key in list(os.environ):
 if key.startswith(('ANTHROPIC_','CLAUDE_','AZURE_')):os.environ.pop(key,None)
from scripts.skill_registry import SkillSession
SKILLS=SkillSession('developer')
TOOLS={
 'fabric_skill_catalog':('List the pinned Microsoft Fabric skill resources and mandatory reads.',{},SKILLS.catalog),
 'read_fabric_skill':('Read a complete, integrity-checked upstream Fabric skill resource.',{'path':{'type':'string'}},SKILLS.read_resource),
 'fabric_skills_ready':('Verify the current session has read every required Fabric skill.',{},SKILLS.require_ready),
 'read_developer_file':('Read tracked files from the assigned solution or wiki clone; no arbitrary filesystem access.',{'repository':{'type':'string','enum':['solution','wiki']},'path':{'type':'string'}},runtime.read_developer_file),
 'revise_source_wiki':('Correct only source, table and inventory wiki pages after actual review, and repin the PR wiki revision. Preserve the tested solution commit.',{'source_page':{'type':'string'},'table_page':{'type':'string'},'inventory_page':{'type':'string'}},runtime.revise_source_wiki),
 'read_pr_feedback':('Read only the assigned demo PR and reviewer threads.',{},lambda **kw:runtime.read_pr_feedback()),
 'reply_to_review':('Respond with correction evidence on the assigned reviewer thread; does not resolve or approve it.',{'thread_id':{'type':'integer'},'response':{'type':'string'}},runtime.reply_to_review),
 'fix_timestamp_precision':('For the verified missing-raw-path failure only, correct the source clone timestamp to stable whole-second UTC; preserve shared platform items.',{},lambda **kw:runtime.fix_timestamp_precision()),
 'publish_review':('After verified successful execution, publish source documentation and revision-matched evidence, then open a PR requiring independent and human review.',{'summary':{'type':'string'}},runtime.publish_review),
 'read_task':('Read the assigned Azure DevOps issue, current revision and platform wiki.',{},lambda **kw:runtime.context()),
 'branch_out':('Create or reconcile the assigned feature branch/workspace and refresh independent developer solution/wiki clones.',{},lambda **kw:runtime.branch_out()),
 'apply_onboarding':('Author and push source metadata plus a fresh pipeline clone and item-count guard. Keys must match the issue; never silently correct a stated key.',{'metadata':{'type':'array','items':{'type':'object'}}},runtime.apply_onboarding),
 'sync_workspace':('Synchronize only the assigned feature workspace to its exact pushed revision.',{},lambda **kw:runtime.sync_workspace()),
 'run_load':('Stage validated metadata and submit or reconcile the source load. Returns actual current job state. A pending result is not success.',{},lambda **kw:runtime.run_load()),
 'job_result':('Read actual pipeline and notebook evidence for the registered job. If still pending, conclude this session as pending rather than repeatedly polling.',{},lambda **kw:runtime.job_result()),
 'request_clarification':('Post actual PRIMARY_KEY_INVALID evidence to the assigned issue and tag waiting-input. Requires a real failed job.',{'question':{'type':'string'}},runtime.request_clarification),
}
def handle(req):
 method=req.get('method');params=req.get('params',{})
 if method=='initialize':return {'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'fabric-demo-developer','version':'0.1'}}
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
