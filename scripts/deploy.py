"""Portable Fabric release deployment. One writer: refuses Git-connected targets."""
import argparse,base64,hashlib,json,re,time
from pathlib import Path
from uuid import UUID
from datetime import datetime,timedelta,timezone
from scripts.live_fabric import FabricClient
from scripts.onelake_files import OneLake
from scripts.deploy_pipeline_template import build
from scripts.pipeline_jobs import submit
from scripts.skill_registry import verify
from fabric_agents.preflight import access_token
ROOT=Path(__file__).resolve().parents[1]
METADATA=[{'dataset_name':'loyalty_members','source_schema':'agent_demo','source_table':'loyalty_members','primary_key_columns':['tenant_id','member_id'],'watermark_column':'updated_at'}]
def validate(config):
    required={'tenant_id','capacity_id','workspace_name','sql_database','sql_ingestion_connection_id','onelake_host','source_frozen','expected_source_rows'}
    if set(config)!=required:raise ValueError('Target config must contain exactly: '+', '.join(sorted(required)))
    for key in ('tenant_id','capacity_id','sql_ingestion_connection_id'):UUID(config[key])
    for key in ('workspace_name','sql_database'):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,62}',config[key]):raise ValueError('Unsafe '+key)
    if not re.fullmatch(r'(?:[a-z0-9-]+-)?onelake\.dfs\.fabric\.microsoft\.com',config['onelake_host']):raise ValueError('Invalid OneLake host')
    if config['source_frozen'] is not True:raise ValueError('This full-snapshot demo requires a frozen source during copy/count')
    if type(config['expected_source_rows']) is not int or not 0<config['expected_source_rows']<=10000:raise ValueError('Invalid source row limit')
    return config

def notebook(m):
    def cell(code,tags=None):return {'cell_type':'code','execution_count':None,'outputs':[],'metadata':{'tags':tags or []},'source':code.splitlines(keepends=True)}
    return {'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'synapse_pyspark','display_name':'Synapse PySpark'},'language_info':{'name':'python'},'dependencies':{'lakehouse':{'default_lakehouse':m['bronze_lakehouse_id'],'default_lakehouse_name':'bronze','default_lakehouse_workspace_id':m['workspace_id']}}},'cells':[cell('source_system = ""\nrun_timestamp = ""\naudit_counts_json = "{}"\n',['parameters']),cell((ROOT/'platform/bronze_loader.py').read_text())]}

def fingerprint(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True).encode()+(ROOT/'platform/bronze_loader.py').read_bytes()+(ROOT/'scripts/deploy_pipeline_template.py').read_bytes()+(ROOT/'skills.lock.json').read_bytes()+(ROOT/'scripts/deploy.py').read_bytes()).hexdigest()

def plan(config):
    validate(config);lock=verify()
    return {'workspace':config['workspace_name'],'capacity_id':config['capacity_id'],'skills_commit':lock['commit'],'release_fingerprint':fingerprint(config),'items':[{'name':'configuration','type':'Lakehouse'},{'name':'bronze','type':'Lakehouse'},{'name':'bronze_loader','type':'Notebook'},{'name':'pl_ingest_template_bronze','type':'DataPipeline'},{'name':'pl_ingest_loyalty_bronze','type':'DataPipeline'}],'source':METADATA,'mode':'API deployment to an unconnected dedicated target; never overwrite a Git workspace','prerequisites':['Active Fabric capacity and authorized deployment identity','Tested SELECT-only Fabric SQL connection','Frozen agent_demo.loyalty_members SQL source','Service-principal Fabric tenant settings when using OIDC'],'creates_azure_capacity_or_sql':False}

def apply(config,smoke=False):
    specification=plan(config);token,claims=access_token(config['tenant_id'],'https://api.fabric.microsoft.com');client=FabricClient(token)
    capacities=client.list_fabric('capacities');capacity=next((x for x in capacities if x['id']==config['capacity_id']),None)
    if not capacity or capacity.get('state')!='Active':raise RuntimeError('Configured capacity is not visible and Active')
    connection=client.get('connections/'+config['sql_ingestion_connection_id'])
    if connection.get('connectionDetails',{}).get('type')!='SQL':raise RuntimeError('Configured connection is not SQL')
    matches=[x for x in client.list_fabric('workspaces') if x['displayName']==config['workspace_name']]
    if len(matches)>1:raise RuntimeError('Ambiguous workspace name')
    w=matches[0] if matches else client.operation('release-workspace-'+hashlib.sha256(config['workspace_name'].encode()).hexdigest()[:12],'workspaces',{'displayName':config['workspace_name'],'capacityId':config['capacity_id'],'description':'Dedicated target managed by fabric-agentic-cicd deployment.'})
    if w.get('capacityId')!=config['capacity_id']:raise RuntimeError('Target capacity mismatch')
    ws=w['id'];git=client.get(f'workspaces/{ws}/git/connection')
    if git.get('gitConnectionState')!='NotConnected':raise RuntimeError('Refusing API writes to a Git-connected workspace; deploy through its reviewed Git workflow')
    items=client.list_fabric(f'workspaces/{ws}/items');expected={(i['name'],i['type']) for i in specification['items']}
    if any((i['displayName'],i['type']) not in expected for i in items if i['type']!='SQLEndpoint'):raise RuntimeError('Target contains unrelated items')
    m={**config,'workspace_id':ws};release=specification['release_fingerprint'][:16]
    def find(name,kind):
        found=[i for i in client.list_fabric(f'workspaces/{ws}/items') if i['displayName']==name and i['type']==kind]
        if len(found)>1:raise RuntimeError('Ambiguous item '+name)
        return found[0] if found else None
    for name in ('configuration','bronze'):
        item=find(name,'Lakehouse') or client.operation('release-'+ws+'-'+name,f'workspaces/{ws}/lakehouses',{'displayName':name,'creationPayload':{'enableSchemas':True}})
        m[name+'_lakehouse_id']=item['id']
    def upsert(name,kind,definition):
        item=find(name,kind)
        if item:
            jobs=client.list_fabric(f'workspaces/{ws}/items/{item["id"]}/jobs/instances')
            if any(j['status'] not in ('Completed','Failed','Cancelled','Deduped') for j in jobs):raise RuntimeError('Active job blocks definition update')
            client.operation('release-'+ws+'-'+name+'-'+release,f'workspaces/{ws}/items/{item["id"]}/updateDefinition',{'definition':definition},fetch_result=False)
        else:item=client.operation('release-create-'+ws+'-'+name,f'workspaces/{ws}/items',{'displayName':name,'type':kind,'definition':definition})
        return item['id']
    def definition(path,content,fmt=None):
        d={'parts':[{'path':path,'payloadType':'InlineBase64','payload':base64.b64encode(json.dumps(content).encode()).decode()}]}
        if fmt:d['format']=fmt
        return d
    m['bronze_loader_notebook_id']=upsert('bronze_loader','Notebook',definition('notebook-content.ipynb',notebook(m),'ipynb'))
    template=build(m);m['pipeline_template_id']=upsert('pl_ingest_template_bronze','DataPipeline',definition('pipeline-content.json',template))
    template['properties']['parameters']['source_system']['defaultValue']='loyalty'
    pipeline=upsert('pl_ingest_loyalty_bronze','DataPipeline',definition('pipeline-content.json',template))
    storage=access_token(config['tenant_id'],'https://storage.azure.com')[0];lake=OneLake(storage,ws,m['configuration_lakehouse_id'],host=config['onelake_host'])
    lake.create('configuration/loyalty/loyalty.json',(json.dumps(METADATA,indent=2)+'\n').encode())
    output={**specification,'workspace_id':ws,'pipeline_id':pipeline,'status':'Deployed; execution not requested','identity':claims,'items':client.list_fabric(f'workspaces/{ws}/items')}
    folder=ROOT/'.runs/deploy';folder.mkdir(parents=True,exist_ok=True)
    result_path=folder/(config['workspace_name']+'.json');result_path.write_text(json.dumps(output,indent=2))
    if smoke:
        key='release-smoke-'+ws+'-'+release;journal=ROOT/'.runs/live-operations'/f'{key}.json'
        import urllib.error
        remote_path='deployment/releases/'+release+'.json'
        try:remote=json.loads(lake.request('GET',remote_path))
        except urllib.error.HTTPError as e:
            if e.code!=404:raise
            remote=None
        if remote and remote.get('release_fingerprint')!=specification['release_fingerprint']:raise RuntimeError('Remote release state mismatch')
        if remote and not remote.get('location'):raise RuntimeError('Uncertain prior submission; reconcile the remote release marker before retry')
        if not remote:
            recent=client.list_fabric(f'workspaces/{ws}/items/{pipeline}/jobs/instances')
            now=datetime.now(timezone.utc)
            for job in recent:
                started=job.get('startTimeUtc')
                if started and (now-datetime.fromisoformat(started.replace('Z','+00:00')).replace(tzinfo=timezone.utc)).total_seconds()<300:raise RuntimeError('Recent job requires reconciliation before another smoke run')
            marker={'state':'submitting','release_fingerprint':specification['release_fingerprint']}
            marker_bytes=json.dumps(marker).encode();lake.create(remote_path,marker_bytes)
            submit(client,ws,pipeline,key)
            saved=json.loads(journal.read_text());remote={**marker,**saved}
            lake.replace(remote_path,marker_bytes,json.dumps(remote).encode())
        saved=remote
        if not saved.get('location'):raise RuntimeError('Uncertain submission; reconcile without re-POST')
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            job=client.get(saved['location'])
            if job['status'] in ('Completed','Failed','Cancelled'):break
            time.sleep(20)
        else:raise RuntimeError('Job still pending; journal preserved')
        now=datetime.now(timezone.utc);_,_,activities=client.request('POST',f'workspaces/{ws}/datapipelines/pipelineruns/{job["id"]}/queryactivityruns',{'lastUpdatedAfter':(now-timedelta(days=1)).isoformat(),'lastUpdatedBefore':(now+timedelta(days=1)).isoformat()})
        output.update(job=job,activities=activities,status='Validation failed');result_path.write_text(json.dumps(output,indent=2))
        if job['status']!='Completed' or len(activities.get('value',[]))!=7 or any(x['status']!='Succeeded' for x in activities['value']):raise RuntimeError('Live deployment validation failed; inspect saved evidence')
        execution=json.loads(next(x for x in activities['value'] if x['activityName']=='LoadBronze')['output']['result']['exitValue'])
        if any(d[k]!=config['expected_source_rows'] for d in execution['datasets'] for k in ('source_count','raw_count','current_count')):raise RuntimeError('Live row-count mismatch')
        output['status']='Live pipeline validation passed';output['notebook_result']=execution;result_path.write_text(json.dumps(output,indent=2))
        lake.replace(remote_path,json.dumps(remote).encode(),json.dumps({**remote,'state':'completed','job_id':job['id']}).encode())
    print(json.dumps({'status':output['status'],'workspace_id':ws,'evidence':str(result_path)},indent=2))
    return output

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['plan','apply']);p.add_argument('--config',required=True);p.add_argument('--smoke',action='store_true');a=p.parse_args();c=json.loads(Path(a.config).read_text())
    if a.command=='plan':print(json.dumps(plan(c),indent=2))
    else:apply(c,a.smoke)
if __name__=='__main__':main()
