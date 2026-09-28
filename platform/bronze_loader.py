# Shared Fabric notebook body. Parameters are supplied by the pipeline.
import json
import re
from datetime import datetime, timezone
from functools import reduce
from uuid import UUID, uuid4
from urllib.parse import urlsplit

import notebookutils
from delta.tables import DeltaTable
from pyspark.sql import functions as F
import requests


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value):
        raise ValueError('Invalid dataset/column identifier')
    return value


identifier(source_system)
instant = datetime.fromisoformat(run_timestamp.replace('Z', '+00:00'))
if instant.tzinfo is None:
    raise ValueError('run_timestamp must include timezone')
instant = instant.astimezone(timezone.utc).replace(tzinfo=None)
if '/' in run_timestamp or '\\' in run_timestamp:
    raise ValueError('Unsafe run path')
expected = json.loads(audit_counts_json)
context = notebookutils.runtime.context
workspace_id = str(UUID(context['currentWorkspaceId']))
configured_endpoint = notebookutils.conf.get('trident.onelake.endpoint')
endpoint_uri = urlsplit(configured_endpoint if '://' in configured_endpoint else 'https://' + configured_endpoint)
endpoint = endpoint_uri.hostname
if (endpoint_uri.scheme != 'https' or not endpoint or
        not endpoint.endswith('.fabric.microsoft.com') or endpoint_uri.username or
        endpoint_uri.port or endpoint_uri.path not in ('', '/')):
    raise ValueError('Unexpected OneLake endpoint')
headers = {'Authorization': 'Bearer ' + notebookutils.credentials.getToken('pbi'),
           'x-ms-fabric-skill': 'spark-cli'}
url = f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/lakehouses'
items = []
while url:
    if not url.startswith('https://api.fabric.microsoft.com/v1/'):
        raise ValueError('Unexpected continuation origin')
    response = requests.get(url, headers=headers, timeout=30, allow_redirects=False)
    response.raise_for_status()
    page = response.json()
    items.extend(page.get('value', []))
    url = page.get('continuationUri')


def lakehouse_path(name):
    found = [x for x in items if x['displayName'] == name]
    if len(found) != 1:
        raise ValueError('Missing or ambiguous lakehouse: ' + name)
    return f'abfss://{workspace_id}@{endpoint}/{UUID(found[0]["id"])}'


config_root = lakehouse_path('configuration')
bronze_root = lakehouse_path('bronze')
metadata = json.loads(notebookutils.fs.head(
    f'{config_root}/Files/configuration/{source_system}/{source_system}.json', 1024 * 1024))
if not isinstance(metadata, list) or not metadata:
    raise ValueError('Metadata must be a nonempty dataset list')
if len({x['dataset_name'] for x in metadata}) != len(metadata):
    raise ValueError('Duplicate dataset name')
if set(expected) != {x['dataset_name'] for x in metadata}:
    raise ValueError('Audit counts must cover exactly the configured datasets')

attempt_id = str(uuid4())
spark.conf.set('spark.sql.session.timeZone', 'UTC')
spark.sql('CREATE SCHEMA IF NOT EXISTS audit')
spark.sql('CREATE SCHEMA IF NOT EXISTS ' + identifier(source_system))
audit_path = f'{bronze_root}/Tables/audit/load_runs'
results = []
for spec in metadata:
    dataset = identifier(spec['dataset_name'])
    keys = spec['primary_key_columns']
    if not keys or len(set(keys)) != len(keys):
        raise ValueError('Missing or duplicate primary-key columns')
    for key in keys: identifier(key)
    target_path = f'{bronze_root}/Tables/{source_system}/{dataset}'
    raw_path = f'{bronze_root}/Files/raw/{source_system}/{dataset}/{run_timestamp}'
    row_count = distinct_count = current_count = -1
    status = 'Failed'
    failure = None
    try:
        incoming = spark.read.parquet(raw_path).cache()
        if any(c.startswith('_meta_') for c in incoming.columns):
            raise ValueError('Source uses reserved metadata columns')
        if not set(keys).issubset(incoming.columns):
            raise ValueError('Primary-key column absent from raw data')
        row_count = incoming.count()
        if row_count > 10000:
            raise ValueError('Demo safety limit is 10000 rows per dataset')
        distinct_count = incoming.select(*keys).distinct().count()
        null_keys = incoming.filter(reduce(lambda a,b: a | b, [F.col(k).isNull() for k in keys])).count()
        if distinct_count != row_count or null_keys:
            duplicates = incoming.groupBy(*keys).count().filter('count > 1').limit(3).toJSON().collect()
            raise ValueError(json.dumps({'code':'PRIMARY_KEY_INVALID','rows':row_count,
                'distinct_keys':distinct_count,'null_keys':null_keys,'duplicate_sample':duplicates}))
        if type(expected[dataset]) is not int or expected[dataset] != row_count:
            raise ValueError('SOURCE_RAW_COUNT_MISMATCH')
        source_columns = sorted(incoming.columns)
        incoming = incoming.withColumn('_meta_key',F.sha2(F.to_json(F.struct(*[F.col(k) for k in keys])),256))
        incoming = incoming.withColumn('_meta_hash',F.sha2(F.to_json(F.struct(*[F.col(k) for k in source_columns])),256))
        enriched = (incoming.withColumn('_meta_valid_from',F.lit(instant).cast('timestamp'))
                    .withColumn('_meta_valid_to',F.lit(None).cast('timestamp'))
                    .withColumn('_meta_is_current',F.lit(True))
                    .withColumn('_meta_run_timestamp',F.lit(run_timestamp)))
        if not DeltaTable.isDeltaTable(spark,target_path):
            enriched.write.format('delta').mode('errorifexists').save(target_path)
        else:
            existing = spark.read.format('delta').load(target_path)
            if existing.schema != enriched.schema:
                # Compare business field types; Delta may relax nullability.
                if [(f.name,f.dataType) for f in existing.schema] != [(f.name,f.dataType) for f in enriched.schema]:
                    raise ValueError('SCHEMA_DRIFT')
            current = existing.filter('_meta_is_current')
            if current.groupBy('_meta_key').count().filter('count > 1').limit(1).count():
                raise ValueError('Existing history contains multiple current rows')
            if current.join(enriched,'_meta_key','left_anti').limit(1).count():
                raise ValueError('Full-snapshot deletions require an explicit contract')
            changes = enriched.alias('s').join(current.alias('t'),'_meta_key','inner').filter(F.col('s._meta_hash') != F.col('t._meta_hash'))
            if changes.filter(F.col('t._meta_valid_from') >= F.lit(instant)).limit(1).count():
                raise ValueError('OUT_OF_ORDER_OR_CONFLICTING_SNAPSHOT')
            insert_changes = changes.select('s.*').withColumn('_merge_key',F.lit(None).cast('string'))
            staged = enriched.withColumn('_merge_key',F.col('_meta_key')).unionByName(insert_changes)
            insert_values = {c:'s.`'+c+'`' for c in enriched.columns}
            (DeltaTable.forPath(spark,target_path).alias('t')
             .merge(staged.alias('s'),'t._meta_key = s._merge_key AND t._meta_is_current = true')
             .whenMatchedUpdate(condition='t._meta_hash <> s._meta_hash',set={
                 '_meta_is_current':'false','_meta_valid_to':'s._meta_valid_from'})
             .whenNotMatchedInsert(values=insert_values).execute())
        loaded = spark.read.format('delta').load(target_path)
        current = loaded.filter('_meta_is_current')
        current_count = current.count()
        if current_count != row_count or current.select(*keys).distinct().count() != row_count:
            raise ValueError('BRONZE_COUNT_OR_KEY_MISMATCH')
        if current.select(*source_columns).exceptAll(incoming.select(*source_columns)).limit(1).count():
            raise ValueError('BRONZE_CONTENT_MISMATCH')
        spark.sql(f"CREATE TABLE IF NOT EXISTS `{source_system}`.`{dataset}` USING DELTA LOCATION '{target_path}'")
        status = 'Succeeded'
        results.append({'dataset':dataset,'source_count':expected[dataset],'raw_count':row_count,
                        'current_count':current_count,'history_count':loaded.count(),'status':status})
    except Exception as exc:
        failure = exc
    finally:
        audit = spark.createDataFrame([(attempt_id,source_system,dataset,run_timestamp,status,
                  expected[dataset],row_count,distinct_count,current_count,str(failure)[:2000] if failure else '')],
                  'attempt_id string, source_system string, dataset_name string, run_timestamp string, status string, source_count long, raw_count long, distinct_key_count long, current_count long, error string')
        audit.write.format('delta').mode('append').save(audit_path)
        spark.sql(f"CREATE TABLE IF NOT EXISTS audit.load_runs USING DELTA LOCATION '{audit_path}'")
    if failure:
        raise failure
notebookutils.notebook.exit(json.dumps({'status':'Succeeded','attempt_id':attempt_id,'datasets':results}))
