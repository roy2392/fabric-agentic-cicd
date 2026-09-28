"""Explicit operator command to register the three meeting demo assignments."""
import json,html
from pathlib import Path
from scripts.settings import load
from scripts.ado_client import AdoClient
from fabric_agents.preflight import access_token

def main():
 root=Path(__file__).resolve().parents[1];(root/'.runs/assignments').mkdir(parents=True,exist_ok=True);m=load();a=AdoClient(access_token(m['tenant_id'],'499b84ac-1321-427f-aa17-267ca6975798')[0])
 items=[
  {'slug':'metadata-preflight','title':'Add fail-fast validation for loyalty source metadata','files':['demo_tools/metadata_preflight.py','tests/test_metadata_preflight.py','docs/metadata-preflight.md'], 'tests':'test_metadata_preflight.py','brief':'''Implement a standard-library-only pure Python function validate_metadata(value) returning a list of actionable error strings (empty list means valid). Match the current configuration/loyalty/loyalty.json dataset-list contract: dataset_name, source_schema, source_table, primary_key_columns, watermark_column. Reject non-list/empty inputs, non-object entries, missing/unknown fields, unsafe identifiers, duplicate dataset names, empty or duplicate key columns, invalid key types and invalid watermark. Identifiers must match [A-Za-z][A-Za-z0-9_]{0,63}. Preserve the composite tenant_id + member_id key: never infer a replacement. Do not modify inputs. Add at least 10 unittest cases including the real valid metadata and malformed cases. Document offline usage and limits: it does not prove source uniqueness or Fabric readiness. No new dependencies or network/filesystem actions in the implementation. Only the three assigned files may change.''', 'min_tests':10},
  {'slug':'run-evidence','title':'Build an honest pipeline evidence summary with failure gates','files':['demo_tools/run_evidence.py','tests/test_run_evidence.py','docs/run-evidence.md'], 'tests':'test_run_evidence.py','brief':'''Implement pure stdlib Python functions evaluate_evidence(report) and render_markdown(report). Contract: report={job:{status},activities:[{name,status}],datasets:[{dataset,source_count,raw_count,current_count,history_count,status}]}. Evaluate to a dict containing status ('Passed' or 'Failed') and reasons (list of actionable strings). Require job Completed, exactly seven distinct named activities each Succeeded, at least one uniquely named dataset each Succeeded, integer counts (not booleans) >=0 with source=raw=current and history>=current. Reject malformed/missing values fail-closed without uncaught exceptions. Markdown must display per-activity and per-dataset evidence, safely escape untrusted Markdown/HTML, and prominently state recorded evidence is not a fresh Fabric execution. Include at least 10 unittest cases with passing synthetic fixtures, running/failed jobs, duplicate or missing activities, mismatched counts, boolean counts and injection-like labels. Document limitations: seven successful activities alone does not establish pipeline identity or freshness; callers must bind revision/job provenance. No new dependencies or network/filesystem actions. Only the three assigned files may change.''', 'min_tests':10},
  {'slug':'recovery-playbook','title':'Author the operator recovery and meeting walkthrough playbook','files':['docs/operator-recovery.md','docs/meeting-walkthrough.md'], 'tests':None,'brief':'''Write two practical, repository-grounded Markdown documents. operator-recovery.md must cover PRIMARY_KEY_INVALID (human clarification), SOURCE_RAW_COUNT_MISMATCH, SCHEMA_DRIFT, uncertain submission/journal reconciliation, stale Git heads and replay/out-of-order snapshots. For each explain observed signal, read-only investigation, stop condition, authorized recovery and proof to retain. No destructive commands, fabricated run IDs, automatic resubmission, permission bypass or claims that code rollback undoes Delta data. Include at least three read-only SELECT queries against actual schema/table/columns from bronze_loader.Notebook for audit status and current/history/key checks; clearly mark placeholders where needed. meeting-walkthrough.md must provide an 8-minute sequence covering board assignment, official skill reads, Claude change, real test evidence, independent Codex review, and the human merge gate. Label which proof is historical live, current local tests, model reads, or planned; do not claim these documentation changes ran a new Fabric job. Link to the existing platform runbook and source metadata using valid relative paths. Only the two assigned files may change.''','min_tests':0}
 ]
 q=a.request('POST','fabric-agents/_apis/wit/wiql?api-version=7.1',{'query':'SELECT [System.Id], [System.Title] FROM WorkItems WHERE [System.TeamProject] = @project'})[2]
 existing={}
 if q['workItems']:
  for x in a.get('fabric-agents/_apis/wit/workitems?ids='+','.join(str(x['id']) for x in q['workItems'])+'&api-version=7.1')['value']:existing[x['fields']['System.Title']]=x['id']
 def create(kind,title,desc,role,parent=None):
  if title in existing:return existing[title]
  fields={'System.Title':title,'System.Description':'<p>'+html.escape(desc).replace('\n','<br>')+'</p>','System.Tags':'demo; meeting-showcase; '+('dev-agent' if role=='developer' else 'review-agent'),'System.AssignedTo':m['tenant_id']+'\\'+m['agents'][role]['object_id']}
  patch=[{'op':'add','path':'/fields/'+k,'value':v} for k,v in fields.items()]
  if parent:patch.append({'op':'add','path':'/relations/-','value':{'rel':'System.LinkTypes.Hierarchy-Reverse','url':a.safe_url('fabric-agents/_apis/wit/workItems/'+str(parent))}})
  try:return a.request('POST','fabric-agents/_apis/wit/workitems/$'+kind+'?api-version=7.1',patch,content_type='application/json-patch+json')[2]['id']
  except RuntimeError:
   raise
 for task in items:
  task['id']=create('Issue',task['title'],task['brief'],'developer')
  task['review_id']=create('Task','Independent Codex review: '+task['slug'],'Review the exact PR revision for Issue '+str(task['id'])+'. Read pinned Microsoft Fabric skills. Inspect implementation, tests, evidence, scope and documentation; publish concrete findings or approval. No source edits, Fabric execution or merge. These assignments change only local utility/docs files, so new Fabric execution is not an acceptance criterion. Keep the private checklist private. Mark this review task Done only after a recorded approval; parent issue waits for human merge.','reviewer',task['id'])
  task['branch']='codex/wi-'+str(task['id'])+'-'+task['slug']
  (root/'.runs/assignments'/str(task['id'])).mkdir(exist_ok=True)
  (root/'.runs/assignments'/str(task['id'])/'task.json').write_text(json.dumps(task,indent=2))
  print({k:task[k] for k in ('id','review_id','title','branch')},flush=True)

if __name__=="__main__":main()
