"""Operator bootstrap helpers; every asynchronous operation is journaled."""
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from uuid import UUID

from fabric_agents.preflight import ReadClient, NoRedirect, access_token

ROOT = Path(__file__).resolve().parents[1]


class FabricClient(ReadClient):
    def __init__(self, token):
        super().__init__('https://api.fabric.microsoft.com/v1/', token)

    def request(self, method, path, body=None):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
                   'x-ms-fabric-skill': 'spark-cli'}
        request = urllib.request.Request(self.safe_url(path), headers=headers, method=method,
                   data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as r:
                raw = r.read()
                return r.status, dict(r.headers), json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            try: detail = json.load(e)
            except ValueError: detail = {}
            raise RuntimeError(f'Fabric HTTP {e.code}: {detail.get("errorCode", "unknown")}') from None

    def operation(self, key, path, body, *, fetch_result=True):
        journal = ROOT / '.runs/live-operations'
        journal.mkdir(parents=True, exist_ok=True)
        record = journal / (key + '.json')
        if record.exists():
            saved = json.loads(record.read_text())
            if saved.get('complete'): return saved['result']
            location = saved.get('location')
            if not location:
                raise RuntimeError('Uncertain POST outcome; reconcile resource before retrying: ' + key)
        else:
            record.write_text(json.dumps({'path': path, 'state': 'submitting'}))
            status, headers, result = self.request('POST', path, body)
            headers = {k.lower(): v for k, v in headers.items()}
            if status != 202:
                record.write_text(json.dumps({'complete': True, 'result': result}))
                return result
            operation_id = headers.get('x-ms-operation-id')
            location = ('operations/' + str(UUID(operation_id))) if operation_id else headers.get('location')
            if not location: raise RuntimeError('202 without operation location')
            self.safe_url(location)
            record.write_text(json.dumps({'path': path, 'location': location, 'state': 'pending'}))
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            _, _, state = self.request('GET', location)
            if state.get('status') == 'Succeeded':
                result = {}
                if fetch_result:
                    _, _, result = self.request('GET', location.rstrip('/') + '/result')
                record.write_text(json.dumps({'complete': True, 'result': result, 'operation': location}))
                return result
            if state.get('status') in ('Failed', 'Cancelled'):
                raise RuntimeError('Operation ended: ' + state['status'])
            time.sleep(10)
        raise RuntimeError('Operation still pending; journal saved for continuation')


def bootstrap_lakehouses():
    manifest_path = ROOT / 'config/live-resources.json'
    m = json.loads(manifest_path.read_text())
    token, _ = access_token(m['tenant_id'], 'https://api.fabric.microsoft.com')
    client = FabricClient(token)
    ws = m['workspace_id']
    if client.get(f'workspaces/{ws}').get('capacityId') != m['capacity_id']:
        raise RuntimeError('Workspace moved to unexpected capacity')
    for name in ('configuration', 'bronze'):
        matches = [x for x in client.list_fabric(f'workspaces/{ws}/lakehouses') if x['displayName'] == name]
        if len(matches) > 1: raise RuntimeError('Ambiguous lakehouse')
        item = matches[0] if matches else client.operation('create-' + name, f'workspaces/{ws}/lakehouses',
                  {'displayName': name, 'creationPayload': {'enableSchemas': True}})
        m[name + '_lakehouse_id'] = item['id']
        manifest_path.write_text(json.dumps(m, indent=2) + '\n')
        print(name, item['id'], flush=True)


if __name__ == '__main__':
    bootstrap_lakehouses()
