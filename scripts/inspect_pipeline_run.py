"""Collect actual Fabric job and activity output, without resubmitting a job."""
import json,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from scripts.live_fabric import FabricClient
from fabric_agents.preflight import access_token
ROOT=Path(__file__).resolve().parents[1]
def main(key):
 if '/' in key or '..' in key:raise ValueError('Invalid key')
 m=json.loads((ROOT/'config/live-resources.json').read_text());t,_=access_token(m['tenant_id'],'https://api.fabric.microsoft.com');c=FabricClient(t)
 j=json.loads((ROOT/'.runs/live-operations'/f'{key}.json').read_text());job=c.get(j['location']);print('Job',job['id'],job['status'],job.get('failureReason'),flush=True)
 now=datetime.now(timezone.utc)
 _,_,activities=c.request('POST',f'workspaces/{m["workspace_id"]}/datapipelines/pipelineruns/{job["id"]}/queryactivityruns',{'lastUpdatedAfter':(now-timedelta(days=1)).isoformat(),'lastUpdatedBefore':(now+timedelta(days=1)).isoformat()})
 result={'job':job,'activities':activities};(ROOT/'.runs/live-evidence'/f'{key}.json').write_text(json.dumps(result,indent=2))
 for activity in activities.get('value',[]):
  print(activity['activityName'], activity['status'])
  if activity.get('status')=='Failed':
   print(str(activity.get('error',{}).get('message',''))[:1800])
  output=activity.get('output') or {}
  if output.get('result',{}).get('exitValue'):print(output['result']['exitValue'])
  if output.get('resultSets'):print(json.dumps(output['resultSets']))
if __name__=='__main__':main(sys.argv[1])
