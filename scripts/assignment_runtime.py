"""Scoped board assignments: isolated clones, local sandbox checks, independent review.

No Fabric mutations, general shell, merge or policy tools are exposed.
"""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
from scripts.settings import load,repo_url,project_url
from scripts.ado_client import AdoClient
from scripts.agent_auth import token_for
from scripts.wiki_context import WikiSession
from scripts.board_policy import eligible, requirements_hash, validate_plan
ROOT=Path(__file__).resolve().parents[1]
def pr_description(summary,head,output):
 return summary[:2000]+'\n\nValidated source: '+head+'\nScope: local utility/docs checks only; no new Fabric execution.\nChecks:\n```\n'+output[-1100:]+'\n```\nFull check output is recorded on the linked work item and in the revision-bound review evidence. Human merge remains required.'

class Assignment:
 def __init__(self,issue,role):
  if role not in ('developer','reviewer'):raise ValueError('Unknown role')
  if type(issue) is not int or issue<1:raise ValueError('Invalid issue')
  self.role=role;self.folder=ROOT/'.runs/assignments'/str(issue)
  self.task=json.loads((self.folder/'task.json').read_text());assert self.task['id']==issue
  self.home=self.folder/role;self.home.mkdir(exist_ok=True);self.clone=self.home/'solution'
  self.m=load();self.base='fabric-agents/_apis/git/repositories/'+self.m['repository_id']
 def wiki_session(self):
  if not hasattr(self,'_wiki'):
   self._wiki=WikiSession(self.ado(),self.m['wiki_id'],self.role,self.home)
  return self._wiki
 def wiki_catalog(self):return self.wiki_session().catalog()
 def read_wiki_page(self,path):return self.wiki_session().read_page(path)
 def wiki_ready(self,check_current=False):return self.wiki_session().require_ready(check_current)
 def ado(self):return AdoClient(role=self.role)
 def git(self,*args):
  env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':str(self.home),'GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_COUNT':'2','GIT_CONFIG_KEY_0':'http.extraHeader','GIT_CONFIG_VALUE_0':'AUTHORIZATION: bearer '+token_for(self.role,'499b84ac-1321-427f-aa17-267ca6975798'),'GIT_CONFIG_KEY_1':'credential.helper','GIT_CONFIG_VALUE_1':''}
  p=subprocess.run(['git',*args],cwd=self.clone if self.clone.exists() else self.home,env=env,capture_output=True,text=True,timeout=120)
  if p.returncode:raise RuntimeError('Git failed: '+p.stderr[-800:])
  return p.stdout.strip()
 def state(self):
  p=self.folder/'state.json';return json.loads(p.read_text()) if p.exists() else {}
 def save(self,s):(self.folder/'state.json').write_text(json.dumps(s,indent=2))
 def comment(self,text,review=False):return self.ado().request('POST',f'fabric-agents/_apis/wit/workItems/{self.task["review_id"] if review else self.task["id"]}/comments?api-version=7.1-preview.4',{'text':text})[2]
 def require_active(self):
  if not self.task.get('automatic'):return
  fields=self.ado().get(f'fabric-agents/_apis/wit/workitems/{self.task["id"]}?api-version=7.1')['fields']
  if not eligible(fields,self.m['operator_ado_id']) or requirements_hash(fields)!=self.task['requirements_hash']:
   raise RuntimeError('Issue paused, closed, untagged or requirements changed; operator reconciliation required')
  if (self.folder/'clarification.json').exists():raise RuntimeError('Assignment is awaiting human clarification')
 def plan_assignment(self,files,tests,min_tests):
  if self.role!='developer' or not self.task.get('automatic'):raise ValueError('Automatic developer assignment only')
  self.wiki_ready();self.require_active();plan=validate_plan(files,tests,min_tests)
  if self.task['files']:raise ValueError('Plan already fixed; do not expand scope')
  if not self.clone.exists():raise ValueError('Read assignment and inspect repository first')
  for name in files:self.path(name)
  self.task.update(plan);(self.folder/'task.json').write_text(json.dumps(self.task,indent=2))
  self.comment('AGENT_PLAN '+json.dumps(plan)+'; independent review and human merge required.')
  return self.task
 def request_clarification(self,question):
  if self.role!='developer' or not self.task.get('automatic'):raise ValueError('Automatic developer only')
  if not isinstance(question,str) or not 20<=len(question)<=2000:raise ValueError('Explain the missing requirement or unsupported scope')
  self.require_active()
  (self.folder/'clarification.json').write_text(json.dumps({'question':question}))
  self.comment('AGENT_WAITING_INPUT: '+question)
  return {'status':'waiting_for_human','question':question}
 def context(self):
  self.require_active()
  a=self.ado();wi=a.get(f'fabric-agents/_apis/wit/workitems/{self.task["id"]}?api-version=7.1')
  if wi['fields']['System.State']=='Done':raise RuntimeError('Assignment is closed')
  if not self.clone.exists():self.git('clone',repo_url(),str(self.clone))
  self.git('fetch','origin')
  s=self.state()
  if self.role=='developer':
   if self.git('branch','--show-current')!=self.task['branch']:
    if self.git('status','--porcelain'):raise RuntimeError('Preserve dirty clone')
    refs=self.git('branch','-r')
    if 'origin/'+self.task['branch'] in refs:self.git('checkout','-b',self.task['branch'],'origin/'+self.task['branch'])
    else:self.git('checkout','-b',self.task['branch'],'origin/main')
   if not s.get('base'):s['base']=self.git('rev-parse','origin/main');self.save(s)
   result={'assignment':self.task,'work_item':wi['fields'],'base':s['base'],'files':self.git('ls-files').splitlines(),'state':s}
  else:
   if not s.get('pr_id'):raise RuntimeError('No published PR')
   pr=a.get(self.base+f'/pullrequests/{s["pr_id"]}?api-version=7.1')
   if pr['status']!='active':raise RuntimeError('PR is not active')
   if self.git('status','--porcelain'):raise RuntimeError('Preserve dirty reviewer clone')
   head=pr['lastMergeSourceCommit']['commitId'];target=pr['lastMergeTargetCommit']['commitId'];self.git('checkout','--detach',head)
   pinned={'head':head,'target':target,'pr_id':s['pr_id']};(self.home/'review-state.json').write_text(json.dumps(pinned))
   result={'assignment':self.task,'pr':pr,'pinned':pinned,'files':self.git('ls-tree','-r','--name-only',head).splitlines(),'diff':self.git('diff',target+'...'+head),'validation':s.get('validation'),'private_checklist':(ROOT/'.runs/reviewer-private/checklist.md').read_text(),'scope_note':'Only local utilities/docs are changed. Do not require a new Fabric run for these files. Verify tests are local, fixtures labeled, claims honest, and no fabric/ configuration or policies changed. Apply relevant private checklist requirements without publishing checklist text.'}
  if s.get('pr_id'):result['threads']=a.get(self.base+f'/pullrequests/{s["pr_id"]}/threads?api-version=7.1')['value']
  result['wiki']=self.wiki_catalog()
  return result
 def path(self,path,write=False):
  if not isinstance(path,str) or not path or '\\' in path or Path(path).is_absolute() or '..' in Path(path).parts:raise ValueError('Unsafe path')
  if write and (self.role!='developer' or path not in self.task['files']):raise ValueError('File outside assigned write scope')
  p=self.clone/path
  if not p.resolve().is_relative_to(self.clone.resolve()) or p.is_symlink():raise ValueError('Path escapes clone')
  return p
 def read_file(self,path):
  p=self.path(path)
  if path not in self.git('ls-files').splitlines() and path not in self.task['files']:raise ValueError('Only tracked/assigned files')
  if p.stat().st_size>160000:raise ValueError('Read limit')
  return {'path':path,'content':p.read_text()}
 def write_file(self,path,content):
  self.wiki_ready();self.require_active()
  p=self.path(path,True)
  if not isinstance(content,str) or len(content.encode())>100000:raise ValueError('Write limit')
  if '\x00' in content:raise ValueError('Text files only')
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
  return {'path':path,'bytes':len(content.encode()),'sha256':hashlib.sha256(content.encode()).hexdigest()}
 def snapshot(self):
  return {name:hashlib.sha256(self.path(name).read_bytes()).hexdigest() for name in self.task['files']}
 def changes(self):
  s=self.state();tracked=set(self.git('diff','--name-only',s['base']).splitlines());untracked=set(self.git('ls-files','--others','--exclude-standard').splitlines());all_changes=tracked|untracked
  if not all_changes.issubset(set(self.task['files'])):raise RuntimeError('Change outside assignment: '+str(all_changes-set(self.task['files'])))
  for name in all_changes:self.path(name,True)
  return sorted(all_changes)
 def run_checks(self):
  if self.role!='developer':raise ValueError('Reviewer cannot execute code')
  self.wiki_ready();self.require_active()
  if not self.task['files']:raise RuntimeError('Plan exact files before writing or checking')
  self.changes();before=self.snapshot();report={'scope':'local tests only; no Fabric execution','file_hashes':before,'wiki_context':self.wiki_ready(True)}
  if self.task['tests']:
   if sys.platform!='darwin':raise RuntimeError('This operator runner requires macOS sandbox-exec; fail closed elsewhere')
   scratch=self.home/'scratch';scratch.mkdir(exist_ok=True)
   exceptions=[str(Path(sys.prefix).resolve()),str(self.clone.resolve()),str(scratch.resolve())]
   profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read-data (require-all (require-any (subpath '+json.dumps(str(Path.home()))+') (subpath "/private/var/folders") (subpath "/private/tmp")) '+''.join('(require-not (subpath '+json.dumps(p)+')) ' for p in exceptions)+'))\n(deny file-write* (require-not (subpath '+json.dumps(str(scratch.resolve()))+')))\n(deny mach-lookup (global-name "com.apple.securityd") (global-name "com.apple.SecurityServer"))\n'
   sb=self.home/'checks.sb';sb.write_text(profile)
   runner='import sys,unittest;sys.path.insert(0,'+repr(str(self.clone))+');s=unittest.defaultTestLoader.discover('+repr(str(self.clone/'tests'))+',pattern='+repr(self.task['tests'])+');n=s.countTestCases();print("TEST_COUNT="+str(n));r=unittest.TextTestRunner(verbosity=2).run(s);sys.exit(0 if r.wasSuccessful() and not r.skipped and n>='+str(self.task['min_tests'])+' else 1)'
   env={'PATH':'/usr/bin:/bin','HOME':str(scratch),'TMPDIR':str(scratch),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
   p=subprocess.run(['/usr/bin/sandbox-exec','-f',str(sb),sys.executable,'-B','-I','-c',runner],cwd=self.clone,env=env,capture_output=True,text=True,timeout=90)
   report.update(exit_code=p.returncode,output=(p.stdout+p.stderr)[-18000:],runner='macOS sandbox: no network; home/temp data restricted to clone and runtime; scratch writes only')
  else:
   content='\n'.join(self.path(x).read_text() for x in self.task['files']);topics=() if self.task.get('automatic') else ('PRIMARY_KEY_INVALID','SOURCE_RAW_COUNT_MISMATCH','SCHEMA_DRIFT','SELECT','merge','historical');missing=[x for x in topics if x.casefold() not in content.casefold()]
   missing += ['Substantive Markdown required: '+x for x in self.task['files'] if len(self.path(x).read_text().strip())<120 or not self.path(x).read_text().lstrip().startswith('#')]
   broken=[]
   for name in self.task['files']:
    for link in re.findall(r'\]\(([^)]+)\)',self.path(name).read_text()):
     if not re.match(r'https?://|#',link) and not (self.path(name).parent/link.split('#')[0]).exists():broken.append(link)
   report.update(exit_code=1 if missing or broken else 0,output=json.dumps({'missing_topics':missing,'broken_relative_links':broken}),runner='Documentation structure/link check; correctness requires independent review')
  if before!=self.snapshot():raise RuntimeError('Files changed during checks')
  (self.home/'validation.json').write_text(json.dumps(report,indent=2));return report
 def publish_pr(self,summary):
  if self.role!='developer':raise ValueError('Developer only')
  self.wiki_ready();self.require_active()
  if not self.task['files']:raise RuntimeError('Plan required')
  if not isinstance(summary,str) or not 80<len(summary)<12000:raise ValueError('Substantive summary required')
  self.changes();report=json.loads((self.home/'validation.json').read_text())
  if report['exit_code']!=0 or report['file_hashes']!=self.snapshot():raise RuntimeError('Fresh passing checks required')
  wiki=self.wiki_ready(True)
  if report.get('wiki_context',{}).get('wiki_commit')!=wiki['wiki_commit']:raise RuntimeError('Validation used different wiki revision; rerun checks')
  self.git('add','--',*self.task['files'])
  if self.git('diff','--cached','--name-only'):self.git('-c','user.name=fabric-agents-developer','-c','user.email=fabric-agents-developer@demo.invalid','commit','-m',f'wi-{self.task["id"]}: '+self.task['title'])
  head=self.git('rev-parse','HEAD');self.git('push','-u','origin',self.task['branch'])
  s=self.state();a=self.ado();description=pr_description(summary,head,report['output'])+'\nWiki context: '+wiki['wiki_commit']
  if s.get('pr_id'):pr=a.request('PATCH',self.base+f'/pullrequests/{s["pr_id"]}?api-version=7.1',{'description':description})[2]
  else:
   matches=[p for p in a.get(self.base+'/pullrequests?searchCriteria.status=active&api-version=7.1')['value'] if p['sourceRefName']=='refs/heads/'+self.task['branch']]
   pr=matches[0] if matches else a.request('POST',self.base+'/pullrequests?api-version=7.1',{'sourceRefName':'refs/heads/'+self.task['branch'],'targetRefName':'refs/heads/main','title':f'wi-{self.task["id"]}: '+self.task['title'],'description':description,'reviewers':[{'id':self.m['agents']['reviewer']['ado_id'],'isRequired':True},{'id':self.m['operator_ado_id'],'isRequired':True}],'workItemRefs':[{'id':str(self.task['id'])}]})[2]
  s.update(pr_id=pr['pullRequestId'],head=head,validation={**report,'source_commit':head});self.save(s)
  self.comment('CLAUDE_IMPLEMENTATION_READY '+json.dumps({'source_commit':head,'pr':repo_url()+'/pullrequest/'+str(s['pr_id']),'validation':report['output'],'scope':report['scope'],'wiki_context':wiki}))
  return {'pr_id':s['pr_id'],'source_commit':head,'url':repo_url()+'/pullrequest/'+str(s['pr_id'])}
 def submit_review(self,source_commit,verdict,body):
  wiki=self.wiki_ready(True)
  developer_wiki=self.state().get('validation',{}).get('wiki_context',{}).get('wiki_commit')
  if developer_wiki and developer_wiki!=wiki['wiki_commit']:raise RuntimeError('Developer and reviewer wiki revisions differ; operator reconciliation required')
  self.require_active()
  if self.role!='reviewer' or verdict not in ('approve','changes_requested'):raise ValueError('Review scope')
  if not isinstance(body,str) or not 100<len(body)<20000:raise ValueError('Substantive evidence required')
  pinned=json.loads((self.home/'review-state.json').read_text());a=self.ado();base=self.base+f'/pullrequests/{pinned["pr_id"]}'
  pr=a.get(base+'?api-version=7.1')
  if pr['status']!='active' or source_commit!=pinned['head'] or pr['lastMergeSourceCommit']['commitId']!=source_commit or pr['lastMergeTargetCommit']['commitId']!=pinned['target']:raise RuntimeError('Review revision changed')
  if not any(x['id']==self.m['operator_ado_id'] and x.get('isRequired') for x in pr['reviewers']):raise RuntimeError('Human reviewer requirement missing')
  a.request('POST',base+'/threads?api-version=7.1',{'comments':[{'content':'Independent Codex review of '+source_commit+'\nWiki context: '+wiki['wiki_commit']+'\n\n'+body,'commentType':1}],'status':2 if verdict=='approve' else 1})
  vote=a.request('PUT',base+'/reviewers/'+self.m['agents']['reviewer']['ado_id']+'?api-version=7.1',{'id':self.m['agents']['reviewer']['ado_id'],'vote':10 if verdict=='approve' else -5,'isRequired':True})[2]
  if not vote.get('isRequired'):raise RuntimeError('Reviewer must remain required')
  receipt={'source_commit':source_commit,'target_commit':pinned['target'],'verdict':verdict,'pr_id':pinned['pr_id'],'body':body,'wiki_context':wiki}
  (self.home/f'review-{source_commit}-{time.time_ns()}.json').write_text(json.dumps(receipt,indent=2))
  if verdict=='approve':
   for t in a.get(base+'/threads?api-version=7.1')['value']:
    cs=t.get('comments',[])
    if t.get('status')=='active' and cs and cs[0].get('author',{}).get('id')==self.m['agents']['reviewer']['ado_id'] and cs[0].get('content','').startswith('Independent Codex review of '):a.request('PATCH',base+'/threads/'+str(t['id'])+'?api-version=7.1',{'status':2})
  return receipt
