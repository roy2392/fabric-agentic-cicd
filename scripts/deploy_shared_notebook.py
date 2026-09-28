"""Operator bootstrap of the shared loader, prior to protected agent work."""
import base64
import json
import hashlib
from pathlib import Path
from fabric_agents.preflight import access_token
from scripts.live_fabric import FabricClient

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = ROOT / 'config/live-resources.json'
    m = json.loads(manifest.read_text())
    def cell(source, tags=None):
        return {'cell_type': 'code', 'execution_count': None, 'outputs': [],
                'metadata': {'tags': tags or []}, 'source': source.splitlines(keepends=True)}
    notebook = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {
        'kernelspec': {'name': 'synapse_pyspark', 'display_name': 'Synapse PySpark'},
        'language_info': {'name': 'python'},
        'dependencies': {'lakehouse': {'default_lakehouse': m['bronze_lakehouse_id'],
            'default_lakehouse_name': 'bronze', 'default_lakehouse_workspace_id': m['workspace_id']}}},
        'cells': [cell('source_system = ""\nrun_timestamp = ""\naudit_counts_json = "{}"\n', ['parameters']),
                  cell((ROOT / 'platform/bronze_loader.py').read_text())]}
    out = ROOT / 'platform/bronze_loader.ipynb'
    out.write_text(json.dumps(notebook, indent=2) + '\n')
    token, _ = access_token(m['tenant_id'], 'https://api.fabric.microsoft.com')
    c = FabricClient(token)
    matches = [x for x in c.list_fabric(f"workspaces/{m['workspace_id']}/items")
               if x['displayName'] == 'bronze_loader' and x['type'] == 'Notebook']
    if len(matches) > 1: raise RuntimeError('Ambiguous shared notebook')
    if matches:
        item = matches[0]
        c.operation('update-bronze-loader-' + hashlib.sha256(out.read_bytes()).hexdigest()[:12],
            f"workspaces/{m['workspace_id']}/items/{item['id']}/updateDefinition", {
            'definition': {'format': 'ipynb', 'parts': [{'path': 'notebook-content.ipynb',
                'payloadType': 'InlineBase64', 'payload': base64.b64encode(out.read_bytes()).decode()}]}},
            fetch_result=False)
    else:
        item = c.operation('create-bronze-loader', f"workspaces/{m['workspace_id']}/items", {
            'displayName': 'bronze_loader', 'type': 'Notebook',
            'description': 'Shared metadata-driven SCD2 bronze loader. Runtime validation pending.',
            'definition': {'format': 'ipynb', 'parts': [{'path': 'notebook-content.ipynb',
                'payloadType': 'InlineBase64', 'payload': base64.b64encode(out.read_bytes()).decode()}]}})
    m['bronze_loader_notebook_id'] = item['id']
    manifest.write_text(json.dumps(m, indent=2) + '\n')
    print('Shared notebook', item['id'], flush=True)


if __name__ == '__main__': main()
