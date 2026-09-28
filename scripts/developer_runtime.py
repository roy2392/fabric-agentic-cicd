"""Constrained developer operations for the single authorized onboarding issue.

No general shell or filesystem tool is exposed to the model. These trusted
operations use only the developer's application identity and demo resources.
"""
import base64,html,json,os,re,subprocess,time,uuid
from pathlib import Path
from datetime import datetime,timezone,timedelta
from scripts.agent_auth import token_for
from scripts.ado_client import AdoClient
from scripts.settings import repo_url, project_url
from scripts.live_fabric import FabricClient
from scripts.onelake_files import OneLake
from scripts.pipeline_jobs import submit
ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT/'.runs/developer'

def manifest():return json.loads((ROOT/'config/live-resources.json').read_text())
def save(m):(ROOT/'config/live-resources.json').write_text(json.dumps(m,indent=2)+'\n')
def fabric():return FabricClient(token_for('developer','https://api.fabric.microsoft.com'))
def ado():return AdoClient(role='developer')
def git(args,cwd=None):
 env=os.environ.copy()
 for key in list(env):
  if key.startswith(('ANTHROPIC_','AZURE_','CLAUDE_')):env.pop(key,None)
 env.update(GIT_TERMINAL_PROMPT='0',GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='http.extraHeader',GIT_CONFIG_VALUE_0='AUTHORIZATION: bearer '+token_for('developer','499b84ac-1321-427f-aa17-267ca6975798'),GIT_CONFIG_KEY_1='credential.helper',GIT_CONFIG_VALUE_1='')
 r=subprocess.run(['git',*args],cwd=cwd,env=env,capture_output=True,text=True,timeout=120)
 if r.returncode:raise RuntimeError('Git operation failed: '+r.stderr[-800:])
 return r.stdout.strip()
def issue_comment(text):
 m=manifest();return ado().request('POST',f'fabric-agents/_apis/wit/workItems/{m["demo_work_item_id"]}/comments?api-version=7.1-preview.4',{'text':text})[2]
def context():
 m=manifest();a=ado();wi=a.get(f'fabric-agents/_apis/wit/workitems/{m["demo_work_item_id"]}?api-version=7.1')
 page=a.get(f'fabric-agents/_apis/wiki/wikis/{m["wiki_id"]}/pages?path=%2FPlatform%20runbook&includeContent=true&api-version=7.1')
 comments=a.get(f'fabric-agents/_apis/wit/workItems/{m["demo_work_item_id"]}/comments?api-version=7.1-preview.4').get('comments',[])
 return {'work_item':wi['fields'],'revision':wi['rev'],'comments':comments,'runbook':page['content'],'run':m.get('demo_run')}
def status(c,ws):
 for _ in range(30):
  code,_,result=c.request('GET',f'workspaces/{ws}/git/status')
  if code==200:return result
  time.sleep(10)
 raise RuntimeError('Git status pending')
def branch_out():
 m=manifest();wi=m['demo_work_item_id'];branch=f'codex/wi-{wi}-loyalty';a=ado();c=fabric();base=f'fabric-agents/_apis/git/repositories/{m["repository_id"]}/'
 refs=a.get(base+'refs?filter=heads/&api-version=7.1')['value'];heads={x['name']:x['objectId'] for x in refs}
 if 'refs/heads/'+branch not in heads:
  result=a.request('POST',base+'refs?api-version=7.1',[{'name':'refs/heads/'+branch,'oldObjectId':'0'*40,'newObjectId':heads['refs/heads/main']}])[2]
  if not result['value'][0]['success']:raise RuntimeError('Feature branch creation failed')
 name=f'fabric-agents-wi-{wi}'
 matches=[x for x in c.list_fabric('workspaces') if x['displayName']==name]
 if len(matches)>1:raise RuntimeError('Ambiguous feature workspace')
 ws=matches[0] if matches else c.operation(f'wi-{wi}-workspace','workspaces',{'displayName':name,'capacityId':m['capacity_id'],'description':f'Dedicated synthetic onboarding for fabric-agents issue {wi}'})
 if c.get('workspaces/'+ws['id']).get('capacityId')!=m['capacity_id']:raise RuntimeError('Unexpected feature capacity')
 roles=c.list_fabric('workspaces/'+ws['id']+'/roleAssignments')
 if not any(x.get('principal',{}).get('id')==m['operator_object_id'] for x in roles):c.request('POST','workspaces/'+ws['id']+'/roleAssignments',{'principal':{'id':m['operator_object_id'],'type':'User'},'role':'Admin'})
 if not m.get('demo_run'):
  m['demo_run']={'work_item_id':wi,'branch':branch,'workspace_id':ws['id'],'workspace_name':name};save(m)
  issue_comment('FABRIC_AGENT_STATE '+json.dumps(m['demo_run']))
 elif m['demo_run']['workspace_id']!=ws['id']:raise RuntimeError('Feature registry mismatch')
 connection=c.get(f'workspaces/{ws["id"]}/git/connection')
 if connection.get('gitConnectionState')=='NotConnected':
  c.request('POST',f'workspaces/{ws["id"]}/git/connect',{'gitProviderDetails':{'gitProviderType':'AzureDevOps','organizationName':m['ado_organization'],'projectName':m['ado_project'],'repositoryName':m['ado_repository'],'branchName':branch,'directoryName':'/fabric'},'myGitCredentials':{'source':'ConfiguredConnection','connectionId':m['developer_git_connection_id']}})
 connection=c.get(f'workspaces/{ws["id"]}/git/connection')
 if connection.get('gitProviderDetails',{}).get('branchName')!=branch:raise RuntimeError('Unexpected Git branch')
 c.operation(f'wi-{wi}-initialize',f'workspaces/{ws["id"]}/git/initializeConnection',{'initializationStrategy':'PreferRemote'})
 sync_workspace()
 HOME.mkdir(parents=True,exist_ok=True)
 for folder,url in [('solution',repo_url()),('wiki',repo_url(wiki=True))]:
  path=HOME/folder
  if not path.exists():git(['clone',url,str(path)])
  if folder=='solution':git(['checkout',branch],path)
  if git(['status','--porcelain'],path):raise RuntimeError('Preserve dirty role clone before refresh')
  git(['pull','--ff-only'],path)
 return {'branch':branch,'workspace':ws['id'],'files':git(['ls-files'],HOME/'solution').splitlines()}
def sync_workspace():
 m=manifest();r=m['demo_run'];c=fabric();s=status(c,r['workspace_id'])
 if any(x.get('workspaceChange') for x in s.get('changes',[])):
  s=reconcile_serialization(c,m,s)
 if s.get('workspaceHead')!=s['remoteCommitHash'] or s.get('changes'):
  c.operation('sync-'+r['workspace_id']+'-'+s['remoteCommitHash'],f'workspaces/{r["workspace_id"]}/git/updateFromGit',{'workspaceHead':s.get('workspaceHead'),'remoteCommitHash':s['remoteCommitHash'],'options':{'allowOverrideItems':True}},fetch_result=False)
 s=status(c,r['workspace_id'])
 if any(x.get('workspaceChange') for x in s.get('changes',[])):
  s=reconcile_serialization(c,m,s)
 if s.get('changes') or s.get('workspaceHead')!=s['remoteCommitHash']:raise RuntimeError('Workspace sync is not complete')
 return {'commit':s['remoteCommitHash'],'items':[{'id':x['id'],'name':x['displayName'],'type':x['type']} for x in c.list_fabric(f'workspaces/{r["workspace_id"]}/items')]}
def reconcile_serialization(c,m,s):
 """Commit only a proven equivalent import; never discard workspace edits."""
 r=m['demo_run'];w=r['workspace_id'];root=HOME/'solution';changes=s.get('changes',[])
 if (s.get('workspaceHead')!=s.get('remoteCommitHash') or len(changes)!=1 or
     changes[0].get('remoteChange') or changes[0]['itemMetadata']['displayName']!='pl_ingest_loyalty_bronze' or
     not root.exists() or git(['status','--porcelain'],root)):
  raise RuntimeError('Unexpected workspace edits; do not overwrite')
 identifier=changes[0]['itemMetadata']['itemIdentifier'];source=json.loads((root/'fabric/pl_ingest_loyalty_bronze.DataPipeline/pipeline-content.json').read_text())
 result=c.operation('inspect-'+w+'-'+s['workspaceHead'],f'workspaces/{w}/items/{identifier["objectId"]}/getDefinition',{})
 parts=[p for p in result['definition']['parts'] if p['path']=='pipeline-content.json']
 if len(parts)!=1:raise RuntimeError('Missing pipeline definition')
 actual=json.loads(base64.b64decode(parts[0]['payload']));mapping={w:'00000000-0000-0000-0000-000000000000'}
 for item in c.list_fabric(f'workspaces/{w}/items'):
  for path in (root/'fabric').glob('*/.platform'):
   platform=json.loads(path.read_text())
   if platform['metadata']['displayName']==item['displayName'] and platform['metadata']['type']==item['type']:
    mapping[item['id']]=platform['config']['logicalId']
 def normalize(value):
  if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
  if isinstance(value,list):return [normalize(v) for v in value]
  return mapping.get(value,value) if isinstance(value,str) else value
 if normalize(actual)!=source:raise RuntimeError('Semantic workspace change requires operator review')
 c.operation('normalize-'+w+'-'+s['workspaceHead'],f'workspaces/{w}/git/commitToGit',{'mode':'Selective','workspaceHead':s['workspaceHead'],'items':[identifier],'comment':'Normalize equivalent imported pipeline serialization'},fetch_result=False)
 git(['pull','--ff-only'],root)
 if json.loads((root/'fabric/pl_ingest_loyalty_bronze.DataPipeline/pipeline-content.json').read_text())!=source:raise RuntimeError('Canonical commit changed pipeline behavior')
 return status(c,w)
def validate_metadata(metadata):
 if not isinstance(metadata,list) or len(metadata)!=1:raise ValueError('Demo scope is one source table')
 spec=metadata[0]
 if set(spec)!={'dataset_name','source_schema','source_table','primary_key_columns','watermark_column'}:raise ValueError('Metadata fields differ from contract')
 if (spec['dataset_name'],spec['source_schema'],spec['source_table'],spec['watermark_column'])!=('loyalty_members','agent_demo','loyalty_members','updated_at'):raise ValueError('Outside authorized synthetic source')
 keys=spec['primary_key_columns']
 if not isinstance(keys,list) or not keys or len(set(keys))!=len(keys) or any(k not in ('tenant_id','member_id','member_name','tier','updated_at') for k in keys):raise ValueError('Invalid declared keys')
 return metadata
def approved_keys():
 """The staged requirement changes only after a verified operator comment."""
 m=manifest();comments=ado().get(f'fabric-agents/_apis/wit/workItems/{m["demo_work_item_id"]}/comments?api-version=7.1-preview.4').get('comments',[])
 approved=['member_id']
 for comment in sorted(comments,key=lambda x:x['id']):
  text=html.unescape(comment.get('text',''))
  if comment.get('createdBy',{}).get('id')==m['operator_ado_id'] and text.startswith('KEY_CONFIRMATION '):
   approved=json.loads(text.removeprefix('KEY_CONFIRMATION '))['primary_key_columns']
 return approved
def apply_onboarding(metadata):
 metadata=validate_metadata(metadata);m=manifest();r=m['demo_run'];root=HOME/'solution'
 if metadata[0]['primary_key_columns']!=approved_keys():raise RuntimeError('Key change requires a verified human confirmation on the work item')
 if git(['branch','--show-current'],root)!=r['branch']:raise RuntimeError('Not on assigned feature branch')
 if git(['status','--porcelain'],root):raise RuntimeError('Existing local changes must be reconciled')
 templates=list((root/'fabric').glob('*.DataPipeline/.platform'))
 selected=[p for p in templates if json.loads(p.read_text())['metadata']['displayName']=='pl_ingest_template_bronze']
 if len(selected)!=1:raise RuntimeError('Missing or ambiguous template')
 original=selected[0].parent;target=root/'fabric/pl_ingest_loyalty_bronze.DataPipeline'
 target.mkdir(exist_ok=True)
 platform=json.loads(selected[0].read_text());platform['metadata']['displayName']='pl_ingest_loyalty_bronze'
 if (target/'.platform').exists():platform['config']['logicalId']=json.loads((target/'.platform').read_text())['config']['logicalId']
 else:platform['config']['logicalId']=str(uuid.uuid4())
 content=json.loads((original/'pipeline-content.json').read_text());content['properties']['parameters']['source_system']['defaultValue']='loyalty'
 if not (target/'.platform').exists():
  (target/'.platform').write_text(json.dumps(platform,indent=2)+'\n');(target/'pipeline-content.json').write_text(json.dumps(content,indent=2)+'\n')
 path=root/'configuration/loyalty/loyalty.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(metadata,indent=2)+'\n');(root/'EXPECTED_GIT_ITEMS').write_text('5\n')
 allowed={'EXPECTED_GIT_ITEMS','configuration/loyalty/loyalty.json','fabric/pl_ingest_loyalty_bronze.DataPipeline/.platform','fabric/pl_ingest_loyalty_bronze.DataPipeline/pipeline-content.json'}
 git(['add','--',*sorted(allowed)],root)
 changed=set(git(['diff','--cached','--name-only'],root).splitlines())
 if not changed or not changed<=allowed:raise RuntimeError('Unexpected or empty onboarding diff')
 git(['-c','user.name=fabric-agents-developer','-c','user.email=fabric-agents-developer@demo.invalid','commit','-m',f'wi-{m["demo_work_item_id"]}: onboard loyalty source metadata and pipeline'],root)
 git(['push','origin',r['branch']],root);head=git(['rev-parse','HEAD'],root)
 issue_comment('Developer pushed onboarding revision '+head+' on '+r['branch'])
 return {'commit':head,'changed_files':sorted(changed),'declared_keys':metadata[0]['primary_key_columns']}
def run_load():
 m=manifest();r=m['demo_run'];root=HOME/'solution';c=fabric();s=status(c,r['workspace_id']);head=git(['rev-parse','HEAD'],root)
 if s['workspaceHead']!=head or s.get('changes'):raise RuntimeError('Push and sync exact source revision first')
 items=c.list_fabric(f'workspaces/{r["workspace_id"]}/items');expected=int((root/'EXPECTED_GIT_ITEMS').read_text())
 governed=[x for x in items if x['type'] in ('Lakehouse','Notebook','DataPipeline')]
 if len(governed)!=expected:raise RuntimeError('Git item-count guard failed')
 def item(name):
  matches=[x for x in governed if x['displayName']==name]
  if len(matches)!=1:raise RuntimeError('Missing or ambiguous '+name)
  return matches[0]['id']
 raw=(root/'configuration/loyalty/loyalty.json').read_bytes();validate_metadata(json.loads(raw))
 lake=OneLake(token_for('developer','https://storage.azure.com'),r['workspace_id'],item('configuration'))
 if json.loads(raw)[0]['primary_key_columns']!=approved_keys():raise RuntimeError('Staged keys lack human authorization')
 previous=r.get('source_commit')
 if previous and previous!=head:
  prior=git(['show',previous+':configuration/loyalty/loyalty.json'],root)+'\n'
  lake.replace('configuration/loyalty/loyalty.json',prior.encode(),raw)
 else:lake.create('configuration/loyalty/loyalty.json',raw)
 key='wi-'+str(m['demo_work_item_id'])+'-'+head[:12]
 journal=ROOT/'.runs/live-operations'/f'{key}.json'
 if not journal.exists():submit(c,r['workspace_id'],item('pl_ingest_loyalty_bronze'),key)
 j=json.loads(journal.read_text())
 if not j.get('location'):raise RuntimeError('Uncertain job submission; reconcile manually')
 m=manifest();m['demo_run']['job_key']=key;m['demo_run']['source_commit']=head;save(m)
 issue_comment('FABRIC_AGENT_JOB '+json.dumps({'source_commit':head,'workspace_id':r['workspace_id'],'job_location':j['location']}))
 return job_result()
def job_result():
 m=manifest();r=m['demo_run'];key=r['job_key'];j=json.loads((ROOT/'.runs/live-operations'/f'{key}.json').read_text());c=fabric();job=c.get(j['location'])
 now=datetime.now(timezone.utc);_,_,activities=c.request('POST',f'workspaces/{r["workspace_id"]}/datapipelines/pipelineruns/{job["id"]}/queryactivityruns',{'lastUpdatedAfter':(now-timedelta(days=1)).isoformat(),'lastUpdatedBefore':(now+timedelta(days=1)).isoformat()})
 proof={'source_commit':r['source_commit'],'workspace_id':r['workspace_id'],'job':job,'activities':activities};(ROOT/'.runs/live-evidence'/f'{key}.json').write_text(json.dumps(proof,indent=2))
 return {'source_commit':r['source_commit'],'job_id':job['id'],'status':job['status'],'activities':[{'name':x['activityName'],'status':x['status'],'output':x.get('output'),'error':x.get('error')} for x in activities.get('value',[])]}
def request_clarification(question):
 m=manifest();proof=job_result();text=json.dumps(proof)
 if proof['status']!='Failed' or 'PRIMARY_KEY_INVALID' not in text:raise RuntimeError('Actual primary-key failure evidence required')
 if not isinstance(question,str) or not 10<len(question)<2000:raise ValueError('Question required')
 issue_comment(question+'\n\nVerified job: '+proof['job_id']+'\nSource commit: '+proof['source_commit']+'\n\n'+text[:18000])
 a=ado();wi=a.get(f'fabric-agents/_apis/wit/workitems/{m["demo_work_item_id"]}?api-version=7.1');tags={x.strip() for x in wi['fields'].get('System.Tags','').split(';') if x.strip()};tags.add('waiting-input')
 a.request('PATCH',f'fabric-agents/_apis/wit/workitems/{m["demo_work_item_id"]}?api-version=7.1',[{'op':'test','path':'/rev','value':wi['rev']},{'op':'add','path':'/fields/System.Tags','value':'; '.join(sorted(tags))}],content_type='application/json-patch+json')
 return {'status':'waiting-input','work_item_id':m['demo_work_item_id'],'question':question}

def publish_review(summary):
 """Publish exact successful evidence, source wiki page, then a human-gated PR."""
 if not isinstance(summary,str) or not 30<len(summary)<6000:raise ValueError('A concise source runbook is required')
 m=manifest();r=m['demo_run'];proof=job_result();head=git(['rev-parse','HEAD'],HOME/'solution')
 if proof['status']!='Completed' or head!=proof['source_commit']:raise RuntimeError('Successful revision-matched load required')
 if any(x['status']!='Succeeded' for x in proof['activities']):raise RuntimeError('Every recorded activity must succeed')
 if git(['status','--porcelain'],HOME/'solution'):raise RuntimeError('Dirty source clone')
 a=ado();base=f'fabric-agents/_apis/git/repositories/{m["repository_id"]}/'
 refs=a.get(base+'refs?filter=heads/'+r['branch']+'&api-version=7.1')['value']
 if len(refs)!=1 or refs[0]['objectId']!=head:raise RuntimeError('Remote revision changed')
 evidence='Verified load at '+head+'\n\n'+json.dumps(proof,indent=2)
 issue_comment(evidence)
 wiki=HOME/'wiki';git(['pull','--ff-only'],wiki)
 if git(['status','--porcelain'],wiki):raise RuntimeError('Dirty wiki clone')
 page=wiki/'Loyalty-source.md'
 page.write_text('# Loyalty source\n\n'+summary+'\n\n## Verified execution\n\nSource commit: `'+head+'`\n\nWorkspace: `'+r['workspace_id']+'`\n\nJob: `'+proof['job_id']+'`\n\nStatus: Completed. Full evidence is attached to [Issue 1]('+project_url()+'/_workitems/edit/'+str(m['demo_work_item_id'])+').\n\nThis page is a direct wiki commit under the developer identity. Main merge remains gated by independent review and the human operator.\n')
 git(['add','--','Loyalty-source.md'],wiki)
 if git(['diff','--cached','--name-only'],wiki):
  git(['-c','user.name=fabric-agents-developer','-c','user.email=fabric-agents-developer@demo.invalid','commit','-m','Document verified loyalty onboarding'],wiki);git(['push','origin','HEAD'],wiki)
 wiki_head=git(['rev-parse','HEAD'],wiki)
 existing=a.get(base+'pullrequests?searchCriteria.status=active&api-version=7.1')['value']
 matches=[x for x in existing if x['sourceRefName']=='refs/heads/'+r['branch']]
 if len(matches)>1:raise RuntimeError('Ambiguous active PR')
 description='Onboard the synthetic loyalty source with the human-confirmed composite key tenant_id + member_id. The cloned pipeline uses the shared bronze framework.\n\nVerified source revision: '+head+'\nFabric workspace: '+r['workspace_id']+'\nCompleted job: '+proof['job_id']+'\n\nIssue and full activity evidence: '+project_url()+'/_workitems/edit/'+str(m['demo_work_item_id'])+'\nWiki revision: '+wiki_head+'\n\nIndependent reviewer and the human operator approval are required. No merge or cleanup has happened.'
 pr=matches[0] if matches else a.request('POST',base+'pullrequests?api-version=7.1',{'sourceRefName':'refs/heads/'+r['branch'],'targetRefName':'refs/heads/main','title':'Onboard loyalty bronze with tenant-scoped composite key','description':description,'reviewers':[{'id':m['agents']['reviewer']['ado_id']},{'id':m['operator_ado_id']}],'workItemRefs':[{'id':str(m['demo_work_item_id'])}]})[2]
 m=manifest();m['demo_run']['pull_request_id']=pr['pullRequestId'];m['demo_run']['wiki_commit']=wiki_head;save(m)
 return {'pull_request_id':pr['pullRequestId'],'url':repo_url()+'/pullrequest/'+str(pr['pullRequestId']),'source_commit':head,'wiki_commit':wiki_head}

def fix_timestamp_precision():
 """Narrow clone-only correction for verified Fabric timestamp coercion."""
 proof=job_result()
 if proof['status']!='Failed' or 'PATH_NOT_FOUND' not in json.dumps(proof):raise RuntimeError('Verified missing-path failure required')
 m=manifest();root=HOME/'solution';path=root/'fabric/pl_ingest_loyalty_bronze.DataPipeline/pipeline-content.json'
 if git(['status','--porcelain'],root):raise RuntimeError('Preserve dirty clone')
 content=json.loads(path.read_text());stamp=next(x for x in content['properties']['activities'] if x['name']=='StampRun')
 stamp['typeProperties']['value']['value']="@formatDateTime(if(empty(pipeline().parameters.run_timestamp),utcNow(),pipeline().parameters.run_timestamp),'yyyy-MM-ddTHH:mm:ssZ')"
 path.write_text(json.dumps(content,indent=2)+'\n')
 git(['add','--',str(path.relative_to(root))],root)
 git(['-c','user.name=fabric-agents-developer','-c','user.email=fabric-agents-developer@demo.invalid','commit','-m','Fix clone timestamp precision across Copy and Notebook'],root)
 git(['push','origin',m['demo_run']['branch']],root)
 head=git(['rev-parse','HEAD'],root);issue_comment('Corrected source pipeline timestamp precision at '+head+'. Copy wrote .220Z while Notebook received .22Z; whole-second UTC formatting removes that ambiguity. Shared template and notebook unchanged. Previous failed job retained: '+proof['job_id'])
 return {'source_commit':head,'timestamp_resolution':'one second','scope':'loyalty pipeline only'}

def read_pr_feedback():
 m=manifest();r=m['demo_run'];base=f'fabric-agents/_apis/git/repositories/{m["repository_id"]}/pullrequests/{r["pull_request_id"]}'
 a=ado();return {'pr':a.get(base+'?api-version=7.1'),'threads':a.get(base+'/threads?api-version=7.1')['value']}

def reply_to_review(thread_id,response):
 if not isinstance(response,str) or not 20<len(response)<6000:raise ValueError('Evidence-based response required')
 m=manifest();r=m['demo_run'];base=f'fabric-agents/_apis/git/repositories/{m["repository_id"]}/pullrequests/{r["pull_request_id"]}'
 thread=ado().get(base+f'/threads/{int(thread_id)}?api-version=7.1')
 if not any(x.get('author',{}).get('id')==m['agents']['reviewer']['ado_id'] for x in thread.get('comments',[])):raise ValueError('Only assigned reviewer threads may receive this response')
 result=ado().request('POST',base+f'/threads/{int(thread_id)}/comments?api-version=7.1',{'content':response,'parentCommentId':0,'commentType':1})[2]
 return {'thread_id':thread_id,'comment_id':result['id']}

def read_developer_file(repository,path):
 if repository not in ('solution','wiki'):raise ValueError('Unknown assigned clone')
 root=HOME/repository
 if path not in git(['ls-files'],root).splitlines():raise ValueError('Only tracked files in assigned clones may be read')
 text=git(['show','HEAD:'+path],root)
 if len(text)>200000:raise ValueError('File exceeds read limit')
 return {'repository':repository,'path':path,'content':text}

def revise_source_wiki(source_page,table_page,inventory_page):
 """Correct only the demo source/table/inventory wiki pages after review."""
 pages={'Loyalty-source.md':source_page,'Loyalty-members.md':table_page,'Demo-inventory.md':inventory_page}
 if any(not isinstance(x,str) or not 100<len(x)<18000 for x in pages.values()):raise ValueError('Complete bounded Markdown pages required')
 m=manifest();r=m['demo_run'];wiki=HOME/'wiki';git(['pull','--ff-only'],wiki)
 if git(['status','--porcelain'],wiki):raise RuntimeError('Preserve dirty wiki clone')
 for name,content in pages.items():(wiki/name).write_text(content.rstrip()+'\n')
 git(['add','--',*pages],wiki)
 changed=git(['diff','--cached','--name-only'],wiki).splitlines()
 if not changed or not set(changed)<=set(pages):raise RuntimeError('Unexpected or empty wiki correction')
 git(['-c','user.name=fabric-agents-developer','-c','user.email=fabric-agents-developer@demo.invalid','commit','-m','Correct reviewed SCD2 semantics, recovery and demo inventory'],wiki);git(['push','origin','HEAD'],wiki)
 head=git(['rev-parse','HEAD'],wiki);a=ado();base=f'fabric-agents/_apis/git/repositories/{m["repository_id"]}/pullrequests/{r["pull_request_id"]}?api-version=7.1';pr=a.get(base)
 description=pr['description'].replace('Wiki revision: '+r['wiki_commit'],'Wiki revision: '+head)
 a.request('PATCH',base,{'description':description})
 m=manifest();m['demo_run']['wiki_commit']=head;save(m)
 return {'wiki_commit':head,'changed_pages':changed,'source_commit_unchanged':r['source_commit']}
