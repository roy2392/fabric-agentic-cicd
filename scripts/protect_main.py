"""Approved human-and-reviewer merge gate for the demo repository."""
import json
from pathlib import Path
from scripts.ado_client import AdoClient
from fabric_agents.preflight import access_token
ROOT=Path(__file__).resolve().parents[1]
def main():
 m=json.loads((ROOT/'config/live-resources.json').read_text());t,_=access_token(m['tenant_id'],'499b84ac-1321-427f-aa17-267ca6975798');a=AdoClient(t)
 types=a.get('fabric-agents/_apis/policy/types?api-version=7.1')['value'];ids={x['displayName']:x['id'] for x in types}
 scope=[{'repositoryId':m['repository_id'],'refName':'refs/heads/main','matchKind':'Exact'}]
 configs=[{'isEnabled':True,'isBlocking':True,'type':{'id':ids['Minimum number of reviewers']},'settings':{'scope':scope,'minimumApproverCount':2,'creatorVoteCounts':False,'allowDownvotes':False,'resetOnSourcePush':True,'blockLastPusherVote':True}},
 {'isEnabled':True,'isBlocking':True,'type':{'id':ids['Required reviewers']},'settings':{'scope':scope,'requiredReviewerIds':[m['agents']['reviewer']['ado_id'],m['operator_ado_id']],'filenamePatterns':[],'addedFilesOnly':False,'message':'Independent Codex review and the human operator human approval are required.'}}]
 existing=a.get('fabric-agents/_apis/policy/configurations?api-version=7.1')['value']
 for config in configs:
  matches=[x for x in existing if x['type']['id']==config['type']['id'] and x.get('settings',{}).get('scope')==scope]
  if matches:raise RuntimeError('Existing main policy requires review before modification')
  _,_,r=a.request('POST','fabric-agents/_apis/policy/configurations?api-version=7.1',config);print('Policy',r['id'],r['type']['displayName'])
if __name__=='__main__':main()
