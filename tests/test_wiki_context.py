import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import pytest
from scripts.wiki_context import WikiSession, REQUIRED
from scripts.assignment_runtime import Assignment
from scripts.publish_wiki import source_files

class Wiki:
    head = 'a' * 40
    def __init__(self): self.queries = []; self.content = '# Handbook\nActual context'
    def get(self, path):
        self.queries.append(path)
        if '/refs?' in path:
            return {'value': [{'name': 'refs/heads/wikiMaster', 'objectId': self.head}]}
        query = parse_qs(urlsplit(path).query)
        assert query['versionDescriptor.versionType'] == ['commit']
        assert query['versionDescriptor.version'] == ['a' * 40]
        return {'content': self.content}

def session(tmp_path, role='developer', client=None):
    return WikiSession(client or Wiki(), 'wiki-repo', role, tmp_path)

def complete(s):
    for page in REQUIRED: s.read_page(page)

def test_fresh_process_and_role_cannot_reuse_receipts(tmp_path):
    s = session(tmp_path); complete(s)
    assert len(s.require_ready()['pages']) == len(REQUIRED)
    for role in ('developer', 'reviewer'):
        with pytest.raises(RuntimeError, match='Read required'): session(tmp_path, role).require_ready()

def test_pinned_reads_and_changed_head_stop_publication(tmp_path):
    client = Wiki(); s = session(tmp_path, client=client)
    s.catalog(); client.head = 'b' * 40
    complete(s)  # All content requests still use the original immutable revision.
    with pytest.raises(RuntimeError, match='Wiki changed'): s.require_ready(True)

def test_missing_page_does_not_unlock(tmp_path):
    s = session(tmp_path)
    for page in REQUIRED[:-1]: s.read_page(page)
    with pytest.raises(RuntimeError, match=REQUIRED[-1]): s.require_ready()

@pytest.mark.parametrize('path', ['../secret', '/Home.md', '.git/config', 'Other.md'])
def test_unknown_paths_rejected_without_network(tmp_path, path):
    client = Wiki(); s = session(tmp_path, client=client)
    with pytest.raises(ValueError): s.read_page(path)
    assert not client.queries

@pytest.mark.parametrize('content', [None, '', 'x' * 160001])
def test_bad_content_does_not_count_as_read(tmp_path, content):
    client = Wiki(); client.content = content; s = session(tmp_path, client=client)
    with pytest.raises(ValueError): s.read_page(REQUIRED[0])
    assert not s.read

def test_receipt_contains_hash_not_page_text(tmp_path):
    s = session(tmp_path); result = s.read_page(REQUIRED[0])
    receipt = json.loads(next(tmp_path.glob('wiki-reads-*')).read_text())
    assert receipt['sha256'] == result['sha256']
    assert receipt['wiki_commit'] == 'a' * 40
    assert 'content' not in receipt

def test_assignment_mutations_enforce_gate_before_side_effects(tmp_path):
    a = Assignment.__new__(Assignment); a.role = 'developer'; a.task = {'automatic': True}; a._wiki = session(tmp_path)
    for call in (lambda: a.plan_assignment(['docs/a.md'], None, 0),
                 lambda: a.write_file('docs/a.md', 'text'), a.run_checks,
                 lambda: a.publish_pr('summary'), lambda: a.submit_review('head', 'approve', 'review')):
        with pytest.raises(RuntimeError, match='Read required'): call()

def test_handbook_complete_and_links_resolve():
    import re
    files = source_files()
    legacy = {'Platform-runbook', 'Demo-inventory', 'Loyalty-source', 'Loyalty-members'}
    targets = {name[:-3] for name in files if name.endswith('.md')} | legacy
    for name, content in files.items():
        if name.endswith('.md'):
            assert content.startswith('# ')
            for link in re.findall(r'\]\(/([^)#]+)', content): assert link in targets, (name, link)
    assert 'history_count' in files['Ingestion-Framework-Guide.md']

def test_published_metadata_example_passes_real_validation():
    import re
    from scripts.developer_runtime import validate_metadata
    text = source_files()['Metadata-Schema-Reference.md']
    example = re.search(r'```json\n(.*?)\n```', text, re.S).group(1)
    assert validate_metadata(json.loads(example))[0]['primary_key_columns'] == ['tenant_id', 'member_id']
