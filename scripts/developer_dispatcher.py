"""Single-shot developer dispatcher; ADO comments/tags and jobs are authoritative.

Call repeatedly from an operator loop. Pending jobs and waiting-human states
return without invoking the model. No background schedule is installed.
"""
import argparse,hashlib,html,json,os,subprocess,sys
from pathlib import Path
from scripts import developer_runtime as runtime
from scripts.skill_registry import prompt as skill_prompt
ROOT=Path(__file__).resolve().parents[1]
def main():
 m=runtime.manifest();a=runtime.ado();wi=a.get(f'fabric-agents/_apis/wit/workitems/{m["demo_work_item_id"]}?api-version=7.1')
 comments=a.get(f'fabric-agents/_apis/wit/workItems/{m["demo_work_item_id"]}/comments?api-version=7.1-preview.4').get('comments',[])
 tags={x.strip() for x in wi['fields'].get('System.Tags','').split(';')}
 if 'dev-agent' not in tags:return print('No assigned work')
 last_question=max((x['id'] for x in comments if x.get('createdBy',{}).get('id')==m['agents']['developer']['ado_id'] and 'Verified job:' in x.get('text','')),default=0)
 human=[x for x in comments if x['id']>last_question and x.get('createdBy',{}).get('id')==m['operator_ado_id'] and html.unescape(x.get('text','')).startswith('KEY_CONFIRMATION ')]
 human=[x for x in human if not any(c.get('text','')=='FABRIC_AGENT_DISPATCH human-comment:'+str(x['id']) for c in comments)]
 if last_question and human:
  reply=max(human,key=lambda x:x['id'])
  trigger='human-comment:'+str(reply['id'])
  keys=runtime.approved_keys()
  task='Read the task and human KEY_CONFIRMATION. The authorized primary_key_columns are '+json.dumps(keys)+'. Use branch_out to refresh existing clones, apply_onboarding with only that metadata correction, sync_workspace, then run_load. Preserve the existing pipeline and shared framework. Stop if the job is pending. Report actual evidence; do not merge or claim review.'
 elif 'waiting-input' in tags:
  return print('Waiting for human clarification; no model call')
 elif m.get('demo_run',{}).get('pull_request_id'):
  feedback=runtime.read_pr_feedback()
  if feedback['pr']['status']!='active':return print('PR is not active; operator closeout owns the next stage')
  reviewer=m['agents']['reviewer']['ado_id']
  votes=[x.get('vote',0) for x in feedback['pr'].get('reviewers',[]) if x['id']==reviewer]
  if votes and votes[0]==10:return print('Independent reviewer approved; awaiting human merge, no model call')
  findings=[(t,c) for t in feedback['threads'] if t.get('status')=='active' for c in t.get('comments',[]) if c.get('author',{}).get('id')==reviewer]
  if not findings:return print('Awaiting independent review; no model call')
  thread,comment=max(findings,key=lambda pair:(pair[0]['id'],pair[1]['id']))
  trigger='review:'+str(thread['id'])+':'+str(comment['id'])
  task='Read the task and read_pr_feedback. Address the actual reviewer findings using only the supported bounded tools. Preserve shared platform items and the human-confirmed key. Refresh clones before changes; a new solution commit requires sync_workspace and successful run_load before republishing evidence. For wiki-only corrections preserve the tested source revision. Respond to reviewer thread '+str(thread['id'])+' with actual correction evidence via reply_to_review. Never resolve the reviewer thread, approve your own work, merge, or invent a correction when a required tool is unavailable.'
 elif m.get('demo_run',{}).get('job_key'):
  proof=runtime.job_result()
  if proof['status'] not in ('Failed','Completed','Cancelled'):return print('Job pending; no model call')
  trigger='job:'+proof['job_id']+':'+proof['status']
  task='Read the assigned task and job_result. If actual PRIMARY_KEY_INVALID evidence is present, post a clear question to the human using request_clarification, including the row and distinct-key counts from the evidence. Do not fix a supplied key on your own. If actual PATH_NOT_FOUND occurs, the operator has verified that Copy wrote .220Z while Notebook received .22Z: call branch_out, fix_timestamp_precision, sync_workspace and run_load, then stop if pending. If successful, call publish_review with a concise source runbook documenting composite keys, full snapshot semantics, the frozen synthetic source during copy/count, source/table inventory, expected five governed items, unchanged replay and SCD2 limitations, and run-scoped rollback. Then report verified results. Do not claim review or merge has happened.'
 else:
  trigger='issue:'+str(wi['id'])+':'+str(wi['rev'])
  task='Read the task, branch_out, apply_onboarding preserving the key supplied in the work item, sync_workspace and run_load. If pending, stop this session. On actual PRIMARY_KEY_INVALID failure request human clarification and stop. Do not infer a corrected key, merge or invent evidence.'
 marker='FABRIC_AGENT_DISPATCH '+trigger
 if any(x.get('text','').startswith(marker) for x in comments):return print('Trigger already dispatched; reconcile result before retry')
 if trigger.startswith('human-comment:') and 'waiting-input' in tags:
  tags.remove('waiting-input')
  a.request('PATCH',f'fabric-agents/_apis/wit/workitems/{wi["id"]}?api-version=7.1',[{'op':'test','path':'/rev','value':wi['rev']},{'op':'replace','path':'/fields/System.Tags','value':'; '.join(sorted(tags))}],content_type='application/json-patch+json')
 runtime.issue_comment(marker)
 key=hashlib.sha256(trigger.encode()).hexdigest()[:16];out=ROOT/'.runs/developer'/f'dispatch-{key}.json'
 task=skill_prompt()+task
 command=[sys.executable,'-m','scripts.claude_foundry','--bare','-p','--tools','','--strict-mcp-config','--mcp-config',str(ROOT/'.runs/developer/mcp.json'),'--allowedTools','mcp__demo__*','--permission-mode','dontAsk','--disable-slash-commands','--no-session-persistence','--max-budget-usd','10','--output-format','json',task]
 with out.open('w') as f:result=subprocess.run(command,cwd=ROOT,stdout=f,timeout=1200)
 runtime.issue_comment('FABRIC_AGENT_DISPATCH_RESULT '+json.dumps({'trigger':trigger,'exit_code':result.returncode,'local_evidence':out.name}))
 print('Dispatched',trigger,'exit',result.returncode,'evidence',out.name)
if __name__=='__main__':main()
