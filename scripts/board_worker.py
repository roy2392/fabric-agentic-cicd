"""One serialized board poll, at most one real model session; never merges PRs.

Schedule this command on the configured Mac. Durable claims are written before
side effects: uncertain submissions and interrupted model runs require an
operator to reconcile, never an automatic retry.
"""
import argparse
import fcntl
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from scripts.ado_client import AdoClient
from scripts.board_policy import eligible, next_action, requirements_hash, tags
from scripts.settings import load, repo_url
from scripts.skill_registry import verify

ROOT = Path(__file__).resolve().parents[1]
WIT = 'fabric-agents/_apis/wit/workitems/'


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else ({} if default is None else default)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


class Worker:
    def __init__(self, client, manifest, root=ROOT):
        self.a, self.m, self.root = client, manifest, root
        self.assignments = root / '.runs/assignments'
        self.base = 'fabric-agents/_apis/git/repositories/' + manifest['repository_id']

    def item(self, issue):
        return self.a.get(WIT + str(issue) + '?$expand=relations&api-version=7.1')

    def patch(self, item, fields):
        operations = [{'op': 'test', 'path': '/rev', 'value': item['rev']}]
        operations += [{'op': 'replace' if key == 'System.Tags' and key in item['fields'] else 'add',
                        'path': '/fields/' + key, 'value': value} for key, value in fields.items()]
        return self.a.request('PATCH', WIT + str(item['id']) + '?api-version=7.1', operations,
                              content_type='application/json-patch+json')[2]

    def comment(self, issue, text):
        self.a.request('POST', WIT + str(issue) + '/comments?api-version=7.1-preview.4',
                       {'text': html.escape(text)})

    def announce(self, folder, status, message):
        state = read(folder / 'worker.json')
        if state.get('notice') == status:
            return
        # Persist before posting. Lost notifications are safer than duplicate submissions.
        state['notice'] = status
        save(folder / 'worker.json', state)
        self.comment(int(folder.name), 'BOARD_AGENT ' + status + ': ' + message)

    def blocked(self, folder, reason):
        state = read(folder / 'worker.json')
        state['blocked'] = reason
        save(folder / 'worker.json', state)
        item = self.item(int(folder.name))
        updated_tags = tags(item['fields']) - {'ready-for-human-merge'} | {'agent-blocked'}
        self.patch(item, {'System.Tags': '; '.join(sorted(updated_tags))})
        self.announce(folder, 'blocked:' + reason, reason + ' An operator must reconcile this issue before resuming.')
        return {'issue': int(folder.name), 'status': 'blocked', 'reason': reason}

    def register(self, item):
        issue, fields = item['id'], item['fields']
        folder = self.assignments / str(issue)
        if (folder / 'task.json').exists():
            return folder
        if (folder / 'worker.json').exists():
            raise RuntimeError('Interrupted registration requires operator reconciliation for issue ' + str(issue))
        save(folder / 'worker.json', {'registration': 'claimed', 'actions': 0, 'developer_runs': 0})
        # A revision test prevents claiming a concurrently edited or closed issue.
        self.patch(item, {'System.State': 'Doing',
                          'System.AssignedTo': self.m['tenant_id'] + '\\' + self.m['agents']['developer']['object_id']})
        operations = [{'op': 'add', 'path': '/fields/' + key, 'value': value} for key, value in {
            'System.Title': 'Independent Codex review: Issue ' + str(issue),
            'System.Description': 'Review the exact source and target revision. Keep the private checklist private. No execution, edits or merge.',
            'System.Tags': 'review-agent',
            'System.AssignedTo': self.m['tenant_id'] + '\\' + self.m['agents']['reviewer']['object_id'],
        }.items()]
        operations.append({'op': 'add', 'path': '/relations/-', 'value': {
            'rel': 'System.LinkTypes.Hierarchy-Reverse', 'url': self.a.safe_url(WIT + str(issue))}})
        review = self.a.request('POST', WIT + '$Task?api-version=7.1', operations,
                                content_type='application/json-patch+json')[2]
        task = {'id': issue, 'review_id': review['id'], 'title': fields['System.Title'],
                'slug': 'automatic', 'brief': fields.get('System.Description', ''),
                'files': [], 'tests': None, 'min_tests': 0, 'automatic': True,
                'requirements_hash': requirements_hash(fields), 'branch': 'codex/wi-' + str(issue) + '-automatic'}
        save(folder / 'task.json', task)
        save(folder / 'worker.json', {'registration': 'ready', 'actions': 0, 'developer_runs': 0})
        self.announce(folder, 'queued', 'Picked up dev-agent. Claude will plan scoped utility/docs files, implement and publish a PR; Codex reviews independently. Human merge remains required.')
        return folder

    def receipt(self, folder, pr):
        if not pr:
            return None
        receipts = sorted((folder / 'reviewer').glob('review-' + pr['lastMergeSourceCommit']['commitId'] + '-*.json'))
        return read(receipts[-1]) if receipts else None

    def process(self, item):
        issue = item['id']
        folder = self.assignments / str(issue)
        task = read(folder / 'task.json')
        if read(folder / 'worker.json').get('blocked'):
            return None
        # Never adopt legacy/manual assignments, even if they carry dev-agent.
        if task and not task.get('automatic'):
            return None
        if not eligible(item['fields'], self.m['operator_ado_id']):
            return None
        try:
            folder = self.register(item)
        except RuntimeError:
            return self.blocked(folder, 'Registration failed or was interrupted; verify child tasks and permissions before retry')
        task = read(folder / 'task.json')
        state = read(folder / 'worker.json')
        if state.get('blocked'):
            return None
        if requirements_hash(item['fields']) != task['requirements_hash']:
            return self.blocked(folder, 'Requirements changed after pickup')
        if state.get('running'):
            return self.blocked(folder, 'Previous model invocation was interrupted; inspect logs and PR before retry')
        if (folder / 'clarification.json').exists():
            return self.blocked(folder, 'Claude requested clarification; see the issue discussion')
        published = read(folder / 'state.json')
        pr = self.a.get(self.base + '/pullrequests/' + str(published['pr_id']) + '?api-version=7.1') if published.get('pr_id') else None
        if pr and pr['status'] == 'active' and (pr['lastMergeSourceCommit']['commitId'] != published.get('head') or published.get('validation', {}).get('source_commit') != published.get('head')):
            return self.blocked(folder, 'Published PR changed outside the validated agent revision')
        action = next_action(state, pr, self.receipt(folder, pr), self.m['agents']['reviewer']['ado_id'], self.m['operator_ado_id'])
        if action == 'merged':
            self.patch(self.item(issue), {'System.State': 'Done', 'System.Tags': '; '.join(sorted(tags(item['fields']) - {'ready-for-human-merge', 'agent-blocked'}))})
            self.announce(folder, 'merged', 'Human merge verified: ' + pr['lastMergeCommit']['commitId'] + '. Issue completed. No Fabric deployment was performed by this worker.')
            return {'issue': issue, 'status': 'merged'}
        if action == 'human_merge':
            # Revision-bound receipt plus required reviewer vote, not a model exit code.
            review = self.item(task['review_id'])
            if review['fields']['System.State'] != 'Done':
                self.patch(review, {'System.State': 'Done'})
            current = self.item(issue)
            if 'ready-for-human-merge' not in tags(current['fields']):
                self.patch(current, {'System.Tags': '; '.join(sorted(tags(current['fields']) | {'ready-for-human-merge'}))})
            head = pr['lastMergeSourceCommit']['commitId']
            notice = 'human_merge:' + head + ':' + pr['lastMergeTargetCommit']['commitId']
            if state.get('notice') == notice:
                return None
            self.announce(folder, notice, 'Independent Codex approval verified. Please review and merge ' + repo_url() + '/pullrequest/' + str(pr['pullRequestId']))
            return {'issue': issue, 'status': 'human_merge', 'pr': pr['pullRequestId'], 'head': head}
        if action not in ('developer', 'reviewer'):
            return self.blocked(folder, action)
        # Re-read immediately before spending model budget; tool writes also recheck.
        latest = self.item(issue)
        if not eligible(latest['fields'], self.m['operator_ado_id']):
            return None
        if requirements_hash(latest['fields']) != task['requirements_hash']:
            return self.blocked(folder, 'Requirements changed before dispatch')
        review = self.item(task['review_id'])
        if review['fields']['System.State'] != 'Doing':
            self.patch(review, {'System.State': 'Doing'})
        if 'ready-for-human-merge' in tags(latest['fields']):
            self.patch(latest, {'System.Tags': '; '.join(sorted(tags(latest['fields']) - {'ready-for-human-merge'}))})
        state['running'] = action
        state['actions'] = state.get('actions', 0) + 1
        state['developer_runs'] = state.get('developer_runs', 0) + (action == 'developer')
        state['started_at'] = time.time()
        save(folder / 'worker.json', state)
        self.announce(folder, action + ':' + str(state['actions']), ('Claude implementation/correction' if action == 'developer' else 'Independent Codex review') + ' started automatically.')
        log = folder / ('worker-action-' + str(state['actions']) + '.log')
        try:
            with log.open('w') as output:
                result = subprocess.run([sys.executable, '-m', 'scripts.assignment_dispatcher', str(issue), action,
                    '--reason', 'Automatic board pickup. Address current independent PR findings if present; preserve human merge.'],
                    cwd=self.root, stdout=output, stderr=subprocess.STDOUT, timeout=1250)
            state = read(folder / 'worker.json')
            state.pop('running', None)
            state['last_exit_code'] = result.returncode
            save(folder / 'worker.json', state)
            if result.returncode:
                return self.blocked(folder, 'Model process failed; inspect private session logs')
            if (folder / 'clarification.json').exists():
                return self.blocked(folder, 'Claude requested clarification; see issue discussion')
            after = read(folder / 'state.json')
            if action == 'developer' and (not after.get('pr_id') or (pr and after.get('head') == published.get('head'))):
                return self.blocked(folder, 'Developer exited without publishing a new validated revision')
            if action == 'reviewer':
                fresh = self.a.get(self.base + '/pullrequests/' + str(after['pr_id']) + '?api-version=7.1')
                receipt = self.receipt(folder, fresh)
                if not receipt or receipt.get('target_commit') != fresh['lastMergeTargetCommit']['commitId']:
                    return self.blocked(folder, 'Reviewer exited without a current revision-bound verdict')
            return {'issue': issue, 'status': action + '_finished', 'pr': after.get('pr_id')}
        except (subprocess.TimeoutExpired, OSError):
            # Keep running marker: a child may still exist. Never automatically replay.
            return self.blocked(folder, 'Invocation interrupted or timed out; reconcile process and remote state')

    def tick(self):
        result = self.a.request('POST', 'fabric-agents/_apis/wit/wiql?api-version=7.1', {'query':
            "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project "
            "AND [System.WorkItemType] = 'Issue' AND [System.State] <> 'Done' "
            "AND [System.Tags] CONTAINS 'dev-agent' ORDER BY [System.Id] ASC"})[2]
        for entry in result.get('workItems', []):
            outcome = self.process(self.item(entry['id']))
            if outcome:
                return outcome
        return {'status': 'idle'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', required=True)
    parser.parse_args()
    verify()
    folder = ROOT / '.runs/board-worker'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'busy'}))
            return
        # The existing developer SP already has board write access; no owner token
        # or extra cloud role is granted to the scheduled controller.
        outcome = Worker(AdoClient(role='developer'), load()).tick()
        save(folder / 'last-poll.json', {'at': time.time(), **outcome})
        print(json.dumps(outcome), flush=True)


if __name__ == '__main__':
    main()
