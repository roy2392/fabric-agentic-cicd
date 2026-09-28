import json

import pytest

from scripts import live_fabric, pipeline_jobs


def test_operation_uses_canonical_host_for_regional_location(tmp_path, monkeypatch):
    monkeypatch.setattr(live_fabric, 'ROOT', tmp_path)
    operation_id = 'cdcff5bd-a28f-4e52-b2d4-1bf58e540bf9'
    calls = []
    client = live_fabric.FabricClient('test-token')

    def request(method, path, body=None):
        calls.append((method, path))
        if method == 'POST':
            return 202, {'x-ms-operation-id': operation_id,
                         'Location': 'https://regional.example/operation'}, {}
        return 200, {}, {'status': 'Succeeded'}

    monkeypatch.setattr(client, 'request', request)
    assert client.operation('test', 'workspaces', {}, fetch_result=False) == {}
    assert calls == [('POST', 'workspaces'), ('GET', 'operations/' + operation_id)]
    client.operation('test', 'workspaces', {}, fetch_result=False)
    assert len(calls) == 2


def test_uncertain_post_is_not_repeated(tmp_path, monkeypatch):
    monkeypatch.setattr(live_fabric, 'ROOT', tmp_path)
    directory = tmp_path / '.runs/live-operations'
    directory.mkdir(parents=True)
    (directory / 'pending.json').write_text(json.dumps({'state': 'submitting'}))
    client = live_fabric.FabricClient('test-token')
    monkeypatch.setattr(client, 'request', lambda *args: pytest.fail('Unexpected network request'))
    with pytest.raises(RuntimeError, match='reconcile'):
        client.operation('pending', 'workspaces', {})


def test_duplicate_pipeline_submission_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_jobs, 'ROOT', tmp_path)
    directory = tmp_path / '.runs/live-operations'
    directory.mkdir(parents=True)
    (directory / 'job.json').write_text('{"state":"submitting"}')
    with pytest.raises(RuntimeError, match='reconcile'):
        pipeline_jobs.submit(None, 'workspace', 'item', 'job')
