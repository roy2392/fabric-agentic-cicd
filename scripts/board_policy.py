"""Pure, fail-closed policy for the local tagged-issue worker."""
import hashlib
import json
import re


def tags(fields):
    return {x.strip().casefold() for x in fields.get('System.Tags', '').split(';') if x.strip()}


def eligible(fields, owner):
    return (fields.get('System.WorkItemType') == 'Issue'
            and fields.get('System.State') in ('To Do', 'Doing')
            and 'dev-agent' in tags(fields)
            and 'agent-paused' not in tags(fields)
            and fields.get('System.CreatedBy', {}).get('id') == owner)


def requirements_hash(fields):
    content = [fields.get('System.Title', ''), fields.get('System.Description', '')]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()


def validate_plan(files, tests, min_tests):
    if not isinstance(files, list) or not 1 <= len(files) <= 8:
        raise ValueError('Choose one to eight exact files')
    if any(not isinstance(p, str) or not re.fullmatch(
            r'(?:docs/[A-Za-z0-9_-]+\.md|demo_tools/[a-z][a-z0-9_]*\.py|tests/test_[a-z0-9_]+\.py)', p)
           for p in files) or len(set(files)) != len(files):
        raise ValueError('Only flat docs/*.md, demo_tools/*.py and tests/test_*.py paths are permitted')
    if any(p.casefold().split('/')[-1] in ('agents.md', 'claude.md', 'skill.md') for p in files):
        raise ValueError('Agent instructions are outside automatic scope')
    code = any(p.endswith('.py') for p in files)
    if code:
        if not isinstance(tests, str) or not re.fullmatch(r'test_[a-z0-9_]+\.py', tests) or 'tests/'+tests not in files:
            raise ValueError('Python changes require an assigned unittest file')
        if type(min_tests) is not int or not 3 <= min_tests <= 100:
            raise ValueError('Require at least three meaningful tests')
    elif tests is not None or min_tests != 0:
        raise ValueError('Documentation-only plans use tests=null and min_tests=0')
    return {'files': files, 'tests': tests, 'min_tests': min_tests}


def next_action(worker, pr, receipt, reviewer_id, owner_id):
    """No model invocation is retried implicitly after a crash or uncertain exit."""
    if worker.get('blocked') or worker.get('running'):
        return 'blocked'
    if pr is None:
        return 'developer' if not worker.get('actions') else 'missing_pr'
    if pr['status'] == 'completed':
        return 'merged' if pr.get('lastMergeCommit', {}).get('commitId') else 'blocked'
    if pr['status'] != 'active':
        return 'abandoned'
    required = {x['id'] for x in pr.get('reviewers', []) if x.get('isRequired')}
    if not {reviewer_id, owner_id}.issubset(required):
        return 'missing_gate'
    head = pr['lastMergeSourceCommit']['commitId']
    target = pr['lastMergeTargetCommit']['commitId']
    if not receipt or (receipt.get('source_commit'), receipt.get('target_commit'), receipt.get('pr_id')) != (head, target, pr['pullRequestId']):
        return 'reviewer' if worker.get('actions', 0) < 8 else 'limit'
    vote = next(x.get('vote', 0) for x in pr['reviewers'] if x['id'] == reviewer_id)
    if receipt['verdict'] == 'approve':
        return 'human_merge' if vote == 10 else 'vote_changed'
    if receipt['verdict'] == 'changes_requested':
        return 'developer' if worker.get('developer_runs', 0) < 4 and worker.get('actions', 0) < 8 else 'limit'
    return 'blocked'
