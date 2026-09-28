"""Read/review-only tools, separate clones and reviewer cloud identity."""
import json,os,subprocess,time,urllib.parse
from pathlib import Path
from scripts.agent_auth import token_for
from scripts.ado_client import AdoClient
from scripts.settings import repo_url, project_url
ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT/'.runs/reviewer'
def manifest():return json.loads((ROOT/'config/live-resources.json').read_text())
def ado():return AdoClient(role='reviewer')
def git(args,cwd):
 env={k:v for k,v in os.environ.items() if not k.startswith(('AZURE_','CLAUDE_','ANTHROPIC_'))}
 env.update(GIT_TERMINAL_PROMPT='0',GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='http.extraHeader',GIT_CONFIG_VALUE_0='AUTHORIZATION: bearer '+token_for('reviewer','499b84ac-1321-427f-aa17-267ca6975798'),GIT_CONFIG_KEY_1='credential.helper',GIT_CONFIG_VALUE_1='')
 p=subprocess.run(['git',*args],cwd=cwd,env=env,capture_output=True,text=True,timeout=120)
 if p.returncode:raise RuntimeError('Reviewer Git read failed: '+p.stderr[-500:])
 return p.stdout

def context():
 m=manifest();r=m['demo_run'];a=ado();base=f'fabric-agents/_apis/git/repositories/{m["repository_id"]}/pullrequests/{r["pull_request_id"]}'
 pr=a.get(base+'?api-version=7.1')
 if pr['status']!='active':raise RuntimeError('PR is not active')
 HOME.mkdir(parents=True,exist_ok=True)
 for name,repo in [('solution','fabric-agents'),('wiki','fabric-agents.wiki')]:
  path=HOME/name
  if not path.exists():git(['clone',repo_url(wiki=name=='wiki'),str(path)],ROOT)
  if git(['status','--porcelain'],path).strip():raise RuntimeError('Preserve dirty reviewer clone')
  git(['fetch','origin'],path)
 source=pr['lastMergeSourceCommit']['commitId'];target=pr['lastMergeTargetCommit']['commitId']
 git(['checkout','--detach',source],HOME/'solution');git(['checkout','--detach','origin/wikiMaster'],HOME/'wiki')
 wiki_commit=git(['rev-parse','HEAD'],HOME/'wiki').strip()
 iterations=a.get(base+'/iterations?api-version=7.1')['value']
 state={'source_commit':source,'target_commit':target,'iteration':max(x['id'] for x in iterations),'pr_id':pr['pullRequestId'],'wiki_commit':wiki_commit}
 (HOME/'review-state.json').write_text(json.dumps(state))
 return {'state':state,'pr':pr,'branch_policies':a.get('fabric-agents/_apis/policy/configurations?api-version=7.1')['value'],'policy_evaluations':a.get('fabric-agents/_apis/policy/evaluations?artifactId='+urllib.parse.quote('vstfs:///CodeReview/CodeReviewId/'+m['ado_project_id']+'/'+str(pr['pullRequestId']),safe='')+'&api-version=7.1-preview.1'),'threads':a.get(base+'/threads?api-version=7.1')['value'],'diff':git(['diff',target+'...'+source],HOME/'solution'),'solution_files':git(['ls-tree','-r','--name-only',source],HOME/'solution').splitlines(),'wiki_files':git(['ls-tree','-r','--name-only',wiki_commit],HOME/'wiki').splitlines(),'work_item':a.get(f'fabric-agents/_apis/wit/workitems/{m["demo_work_item_id"]}?api-version=7.1'),'comments':a.get(f'fabric-agents/_apis/wit/workitems/{m["demo_work_item_id"]}/comments?api-version=7.1-preview.4'),'private_checklist':(ROOT/'.runs/reviewer-private/checklist.md').read_text()}

def read_file(repository,path):
 if repository not in ('solution','wiki'):raise ValueError('Unknown repository')
 state=json.loads((HOME/'review-state.json').read_text());commit=state['source_commit' if repository=='solution' else 'wiki_commit']
 tracked=git(['ls-tree','-r','--name-only',commit],HOME/repository).splitlines()
 if path not in tracked:raise ValueError('Only tracked files at the review revision may be read')
 value=git(['show',commit+':'+path],HOME/repository)
 if len(value)>200000:raise ValueError('File exceeds bounded review size')
 return {'path':path,'commit':commit,'content':value}

def submit_review(source_commit,verdict,body):
 if verdict not in ('approve','changes_requested'):raise ValueError('Invalid verdict')
 if not isinstance(body,str) or not 50<len(body)<20000:raise ValueError('Evidence and rationale required')
 m=manifest();state=json.loads((HOME/'review-state.json').read_text());a=ado();base=f'fabric-agents/_apis/git/repositories/{m["repository_id"]}/pullrequests/{state["pr_id"]}'
 pr=a.get(base+'?api-version=7.1');iterations=a.get(base+'/iterations?api-version=7.1')['value']
 if pr['status']!='active' or source_commit!=state['source_commit'] or pr['lastMergeSourceCommit']['commitId']!=source_commit or max(x['id'] for x in iterations)!=state['iteration']:raise RuntimeError('PR changed; refresh and review again')
 wiki_refs=a.get(f'fabric-agents/_apis/git/repositories/{m["wiki_id"]}/refs?filter=heads/wikiMaster&api-version=7.1')['value']
 if not any(x['name']=='refs/heads/wikiMaster' and x['objectId']==state['wiki_commit'] for x in wiki_refs):raise RuntimeError('Wiki changed; refresh and review again')
 thread=a.request('POST',base+'/threads?api-version=7.1',{'comments':[{'parentCommentId':0,'content':'Independent Codex review of '+source_commit+'\n\n'+body,'commentType':1}],'status':2 if verdict=='approve' else 1})[2]
 reviewer=a.request('PUT',base+'/reviewers/'+m['agents']['reviewer']['ado_id']+'?api-version=7.1',{'id':m['agents']['reviewer']['ado_id'],'vote':10 if verdict=='approve' else -5,'isRequired':True})[2]
 if not reviewer.get('isRequired'):raise RuntimeError('Required reviewer flag was not preserved')
 if verdict=='approve':
  for prior in a.get(base+'/threads?api-version=7.1')['value']:
   comments=prior.get('comments',[])
   if prior.get('status')=='active' and comments and comments[0].get('author',{}).get('id')==m['agents']['reviewer']['ado_id'] and comments[0].get('content','').startswith('Independent Codex review of '):
    a.request('PATCH',base+'/threads/'+str(prior['id'])+'?api-version=7.1',{'status':2})
 result={**state,'verdict':verdict,'thread_id':thread['id'],'vote':reviewer['vote']}
 (HOME/f'review-{source_commit}-{state["wiki_commit"]}-{time.time_ns()}.json').write_text(json.dumps(result,indent=2))
 return result
