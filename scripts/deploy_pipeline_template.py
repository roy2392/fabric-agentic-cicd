"""The shared source-onboarding template: metadata, Copy, counts, bronze loader."""
import json
from pathlib import Path
from scripts.live_fabric import FabricClient
from scripts.pipeline_jobs import deploy
from fabric_agents.preflight import access_token
ROOT=Path(__file__).resolve().parents[1]
def expression(value):return {'value':value,'type':'Expression'}
def build(m):
 ws=m['workspace_id']; conn=m['sql_ingestion_connection_id']
 def lh(item,kind,properties):
  return {'type':kind,'schema':[],'linkedService':{'name':item,'properties':{'type':'Lakehouse','typeProperties':{'workspaceId':ws,'artifactId':m[item+'_lakehouse_id'],'rootFolder':'Files'}}},'typeProperties':properties}
 def sql_dataset():return {'type':'SqlServerTable','schema':[],'typeProperties':{'database':m['sql_database']},'externalReferences':{'connection':conn}}
 def activity(name,kind,props,after=None):
  return {'name':name,'type':kind,'dependsOn':[{'activity':after,'dependencyConditions':['Succeeded']}] if after else [],'policy':{'timeout':'0.00:20:00','retry':0},'typeProperties':props}
 metadata=activity('ReadMetadata','Lookup',{'source':{'type':'JsonSource','storeSettings':{'type':'LakehouseReadSettings','recursive':False},'formatSettings':{'type':'JsonReadSettings'}},'datasetSettings':lh('configuration','Json',{'location':{'type':'LakehouseLocation','folderPath':expression("@concat('configuration/',pipeline().parameters.source_system)"),'fileName':expression("@concat(pipeline().parameters.source_system,'.json')")}}),'firstRowOnly':False},'StampRun')
 copy=activity('CopyDataset','Copy',{'source':{'type':'SqlServerSource','sqlReaderQuery':expression("@concat('SELECT * FROM [',item().source_schema,'].[',item().source_table,']')"),'queryTimeout':'00:05:00','partitionOption':'None','datasetSettings':sql_dataset()},'sink':{'type':'ParquetSink','storeSettings':{'type':'LakehouseWriteSettings'},'formatSettings':{'type':'ParquetWriteSettings'},'datasetSettings':lh('bronze','Parquet',{'location':{'type':'LakehouseLocation','folderPath':expression("@concat('raw/',pipeline().parameters.source_system,'/',item().dataset_name,'/',variables('run_timestamp'))"),'fileName':'snapshot.parquet'},'compressionCodec':'snappy'})},'enableStaging':False,'parallelCopies':1,'translator':{'type':'TabularTranslator','typeConversion':True,'typeConversionSettings':{'allowDataTruncation':False,'treatBooleanAsNumber':False}}})
 count=activity('CountSource','Lookup',{'source':{'type':'SqlServerSource','sqlReaderQuery':expression("@concat('SELECT COUNT_BIG(*) AS source_count FROM [',item().source_schema,'].[',item().source_table,']')"),'queryTimeout':'00:05:00','partitionOption':'None'},'datasetSettings':sql_dataset(),'firstRowOnly':True},'CopyDataset')
 append=activity('AccumulateCounts','AppendVariable',{'variableName':'count_fragments','value':expression('@concat(\'"\',item().dataset_name,\'":\',string(activity(\'CountSource\').output.firstRow.source_count))')},'CountSource');append.pop('policy')
 each=activity('ForEachDataset','ForEach',{'items':expression("@activity('ReadMetadata').output.value"),'isSequential':True,'activities':[copy,count,append]},'ReadMetadata');each.pop('policy')
 stamp=activity('StampRun','SetVariable',{'variableName':'run_timestamp','value':expression("@formatDateTime(if(empty(pipeline().parameters.run_timestamp),utcNow(),pipeline().parameters.run_timestamp),'yyyy-MM-ddTHH:mm:ssZ')")});stamp.pop('policy')
 notebook=activity('LoadBronze','TridentNotebook',{'workspaceId':ws,'notebookId':m['bronze_loader_notebook_id'],'parameters':{'source_system':{'value':expression('@pipeline().parameters.source_system'),'type':'string'},'run_timestamp':{'value':expression("@variables('run_timestamp')"),'type':'string'},'audit_counts_json':{'value':expression("@concat('{',join(variables('count_fragments'),','),'}')"),'type':'string'}}},'ForEachDataset')
 return {'properties':{'concurrency':1,'parameters':{'source_system':{'type':'string','defaultValue':'template'},'run_timestamp':{'type':'string','defaultValue':''}},'variables':{'run_timestamp':{'type':'String'},'count_fragments':{'type':'Array','defaultValue':[]}},'activities':[stamp,metadata,each,notebook]}}
def main():
 p=ROOT/'config/live-resources.json';m=json.loads(p.read_text());content=build(m)
 (ROOT/'platform/pipeline-template.json').write_text(json.dumps(content,indent=2)+'\n')
 t,_=access_token(m['tenant_id'],'https://api.fabric.microsoft.com');c=FabricClient(t)
 item=deploy(c,m['workspace_id'],'pl_ingest_template_bronze',content);m['pipeline_template_id']=item['id'];p.write_text(json.dumps(m,indent=2)+'\n');print('Shared template',item['id'])
if __name__=='__main__':main()
