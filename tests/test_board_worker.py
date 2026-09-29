import copy
import json
from pathlib import Path

import pytest

from scripts.board_policy import eligible, next_action, requirements_hash, validate_plan
from scripts.board_worker import Worker, read, save
from scripts.assignment_runtime import Assignment


def issue():
    return {'id': 12, 'rev': 2, 'fields': {'System.WorkItemType': 'Issue', 'System.State': 'To Do',
        'System.Tags': 'Demo; dev-agent', 'System.CreatedBy': {'id': 'human'},
        'System.Title': 'Document a utility', 'System.Description': 'Write useful documentation.'}}


def pr():
    return {'pullRequestId': 8, 'status': 'active', 'lastMergeSourceCommit': {'commitId': 'source'},
        'lastMergeTargetCommit': {'commitId': 'target'}, 'reviewers': [
            {'id': 'human', 'isRequired': True, 'vote': 0},
            {'id': 'reviewer', 'isRequired': True, 'vote': 10}]}


def receipt():
    return {'pr_id': 8, 'source_commit': 'source', 'target_commit': 'target', 'verdict': 'approve'}


def test_exact_tag_and_trusted_owner():
    fields = issue()['fields']
    assert eligible(fields, 'human')
    for key, value in [('System.Tags', 'not-dev-agent'), ('System.Tags', 'dev-agent; agent-paused'),
                       ('System.State', 'Done'), ('System.WorkItemType', 'Task'),
                       ('System.CreatedBy', {'id': 'other'})]:
        assert not eligible({**fields, key: value}, 'human')


@pytest.mark.parametrize('files', [['../docs/x.md'], ['docs/../../x.md'], ['scripts/x.py'],
    ['.github/workflows/x.yml'], ['docs/AGENTS.md'], ['docs/CLAUDE.md'], ['docs/x.md', 'docs/x.md'],
    ['tests/__init__.py'], ['docs/x.md\n'], ['demo_tools/__init__.py'], []])
def test_reject_plan_escape(files):
    with pytest.raises(ValueError): validate_plan(files, None, 0)


def test_python_requires_real_test_scope():
    for tests, count in [(None, 0), ('*.py', 3), ('test_other.py', 3), ('test_x.py', True), ('test_x.py', 0)]:
        with pytest.raises(ValueError): validate_plan(['demo_tools/x.py', 'tests/test_x.py'], tests, count)
    assert validate_plan(['demo_tools/x.py', 'tests/test_x.py'], 'test_x.py', 3)['min_tests'] == 3
    assert validate_plan(['docs/example.md'], None, 0)['tests'] is None


def test_status_or_tag_change_does_not_change_requirements():
    fields = issue()['fields']
    assert requirements_hash(fields) == requirements_hash({**fields, 'System.State': 'Doing'})
    assert requirements_hash(fields) != requirements_hash({**fields, 'System.Description': 'Changed'})


def test_review_requires_both_exact_revisions_and_pr():
    for field in ('source_commit', 'target_commit', 'pr_id'):
        stale = {**receipt(), field: 'stale'}
        assert next_action({}, pr(), stale, 'reviewer', 'human') == 'reviewer'
    assert next_action({}, pr(), receipt(), 'reviewer', 'human') == 'human_merge'


def test_real_vote_and_human_gate_required():
    changed = pr(); changed['reviewers'][1]['vote'] = 0
    assert next_action({}, changed, receipt(), 'reviewer', 'human') == 'vote_changed'
    changed['reviewers'][0]['isRequired'] = False
    assert next_action({}, changed, receipt(), 'reviewer', 'human') == 'missing_gate'


def test_crashes_and_budget_cannot_replay():
    assert next_action({'running': 'developer'}, None, None, 'reviewer', 'human') == 'blocked'
    assert next_action({'blocked': 'timeout'}, None, None, 'reviewer', 'human') == 'blocked'
    assert next_action({'actions': 1}, None, None, 'reviewer', 'human') == 'missing_pr'
    assert next_action({'actions': 8}, pr(), None, 'reviewer', 'human') == 'limit'
    findings = {**receipt(), 'verdict': 'changes_requested'}
    assert next_action({'developer_runs': 4}, pr(), findings, 'reviewer', 'human') == 'limit'
    assert next_action({'developer_runs': 1}, pr(), findings, 'reviewer', 'human') == 'developer'


def test_only_actual_merge_completes():
    completed = {**pr(), 'status': 'completed'}
    assert next_action({}, completed, receipt(), 'reviewer', 'human') == 'blocked'
    completed['lastMergeCommit'] = {'commitId': 'merge'}
    assert next_action({}, completed, receipt(), 'reviewer', 'human') == 'merged'
    assert next_action({}, {**pr(), 'status': 'abandoned'}, receipt(), 'reviewer', 'human') == 'abandoned'


class FakeAdo:
    def __init__(self):
        self.items = {12: issue()}; self.calls = []
    def safe_url(self, path): return 'https://dev.azure.com/example/' + path
    def get(self, path):
        return copy.deepcopy(self.items[int(path.split('workitems/')[1].split('?')[0])])
    def request(self, method, path, body, **kwargs):
        self.calls.append((method, path, body))
        if method == 'PATCH':
            item = self.items[int(path.split('workitems/')[1].split('?')[0])]
            assert body[0] == {'op': 'test', 'path': '/rev', 'value': item['rev']}
            for op in body[1:]: item['fields'][op['path'].split('/fields/')[1]] = op['value']
            item['rev'] += 1
            return 200, {}, copy.deepcopy(item)
        if '/$Task?' in path:
            self.items[13] = {'id': 13, 'rev': 1, 'fields': {'System.State': 'To Do'}}
            return 200, {}, self.items[13]
        return 200, {}, {}


def worker(tmp_path):
    return Worker(FakeAdo(), {'repository_id': 'repo', 'tenant_id': 'tenant', 'operator_ado_id': 'human',
        'agents': {'developer': {'object_id': 'dev'}, 'reviewer': {'object_id': 'rev', 'ado_id': 'reviewer'}}}, tmp_path)


def test_register_is_idempotent_and_keeps_gate_metadata(tmp_path):
    w = worker(tmp_path)
    folder = w.register(issue()); count = len(w.a.calls)
    w.register(issue())
    assert len(w.a.calls) == count
    task = read(folder / 'task.json')
    assert task['files'] == [] and task['automatic'] and task['review_id'] == 13
    assert w.a.items[12]['fields']['System.State'] == 'Doing'


def test_interrupted_registration_is_not_replayed(tmp_path):
    w = worker(tmp_path)
    save(w.assignments / '12/worker.json', {'registration': 'claimed'})
    with pytest.raises(RuntimeError, match='reconciliation'): w.register(issue())
    assert not w.a.calls


def test_existing_manual_assignment_not_adopted(tmp_path):
    w = worker(tmp_path)
    save(w.assignments / '12/task.json', {'id': 12, 'files': ['docs/legacy.md']})
    assert w.process(issue()) is None
    assert not w.a.calls


def test_worker_stops_requirements_change_and_does_not_repeat_notice(tmp_path):
    w = worker(tmp_path); w.register(issue())
    changed = issue(); changed['fields']['System.Description'] = 'New scope'
    result = w.process(changed)
    assert result['status'] == 'blocked'
    count = len(w.a.calls)
    assert w.process(changed) is None
    assert len(w.a.calls) == count


def test_runtime_rechecks_removal_and_edited_requirements(tmp_path):
    w = worker(tmp_path); folder = w.register(issue())
    a = Assignment.__new__(Assignment)
    a.task = read(folder / 'task.json'); a.m = w.m; a.folder = folder; a.ado = lambda: w.a
    a.require_active()
    w.a.items[12]['fields']['System.Tags'] = ''
    with pytest.raises(RuntimeError, match='paused'): a.require_active()
    w.a.items[12]['fields']['System.Tags'] = 'dev-agent'
    w.a.items[12]['fields']['System.Description'] = 'Changed'
    with pytest.raises(RuntimeError, match='requirements changed'): a.require_active()


def test_tag_removal_uses_replace_not_add(tmp_path):
    w = worker(tmp_path)
    w.patch(issue(), {'System.Tags': 'dev-agent'})
    assert w.a.calls[-1][2][1]['op'] == 'replace'


def test_full_lifecycle_and_repeated_polls(tmp_path, monkeypatch):
    from types import SimpleNamespace
    w = worker(tmp_path); remote = pr(); calls = []
    original_get = w.a.get
    w.a.get = lambda path: copy.deepcopy(remote) if '/pullrequests/' in path else original_get(path)
    folder = w.assignments / '12'

    def run(command, **kwargs):
        role = command[4]; calls.append(role)
        if role == 'developer':
            save(folder / 'state.json', {'pr_id': 8, 'head': 'source', 'validation': {'source_commit': 'source'}})
        else:
            save(folder / 'reviewer/review-source-1.json', receipt())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr('scripts.board_worker.subprocess.run', run)
    monkeypatch.setattr('scripts.board_worker.repo_url', lambda: 'https://example.invalid/repo')
    assert w.process(w.item(12))['status'] == 'developer_finished'
    assert w.item(13)['fields']['System.State'] == 'To Do'
    assert w.process(w.item(12))['status'] == 'reviewer_finished'
    assert w.process(w.item(12))['status'] == 'human_merge'
    assert w.process(w.item(12)) is None
    assert calls == ['developer', 'reviewer']
    assert w.item(12)['fields']['System.State'] == 'Doing'
    assert w.item(13)['fields']['System.State'] == 'Done'
    remote.update(status='completed', lastMergeCommit={'commitId': 'merge'})
    assert w.process(w.item(12))['status'] == 'merged'
    assert w.item(12)['fields']['System.State'] == 'Done'
    assert 'ready-for-human-merge' not in w.item(12)['fields']['System.Tags']
    assert w.process(w.item(12)) is None


def test_target_change_reopens_review_and_drops_ready_tag(tmp_path, monkeypatch):
    from types import SimpleNamespace
    w = worker(tmp_path); folder = w.register(issue())
    w.a.items[12]['fields']['System.Tags'] += '; ready-for-human-merge'
    w.a.items[13]['fields']['System.State'] = 'Done'
    save(folder / 'state.json', {'pr_id': 8, 'head': 'source', 'validation': {'source_commit': 'source'}})
    save(folder / 'reviewer/review-source-1.json', receipt())
    remote = pr(); remote['lastMergeTargetCommit']['commitId'] = 'new_target'
    original_get = w.a.get
    w.a.get = lambda path: copy.deepcopy(remote) if '/pullrequests/' in path else original_get(path)
    invoked = []
    def run(command, **kwargs):
        invoked.append(command[4])
        save(folder / 'reviewer/review-source-2.json', {**receipt(), 'target_commit': 'new_target'})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('scripts.board_worker.subprocess.run', run)
    assert w.process(w.item(12))['status'] == 'reviewer_finished'
    assert invoked == ['reviewer']
    assert w.item(13)['fields']['System.State'] == 'Doing'
    assert 'ready-for-human-merge' not in w.item(12)['fields']['System.Tags']


def test_unexpected_push_cannot_inherit_ready_approval(tmp_path):
    w = worker(tmp_path); folder = w.register(issue())
    save(folder / 'state.json', {'pr_id': 8, 'head': 'old', 'validation': {'source_commit': 'old'}})
    save(folder / 'reviewer/review-source-1.json', receipt())
    original_get = w.a.get
    w.a.get = lambda path: pr() if '/pullrequests/' in path else original_get(path)
    assert w.process(w.item(12))['status'] == 'blocked'
    assert w.item(13)['fields']['System.State'] != 'Done'
