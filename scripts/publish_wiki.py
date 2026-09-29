"""Plan or publish the portable handbook as one non-forced wiki Git commit.

Uses the configured project and existing developer identity. Preserves legacy
pages. Refuses dirty clones and stale expected heads; never changes permissions.
"""
import argparse
import os
import subprocess
from pathlib import Path
from scripts.agent_auth import token_for
from scripts.settings import repo_url
from scripts.wiki_context import REQUIRED

ROOT = Path(__file__).resolve().parents[1]

def source_files():
    root = ROOT / 'wiki'
    files = {str(p.relative_to(root)): p.read_text() for p in root.rglob('*') if p.is_file()}
    if not set(REQUIRED).issubset(files):
        raise RuntimeError('Handbook is missing required context pages')
    if any(not (name.endswith('.md') or Path(name).name == '.order') for name in files):
        raise RuntimeError('Unexpected handbook artifact')
    return files

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--expected-head')
    args = parser.parse_args()
    files = source_files()
    if not args.publish:
        print('\n'.join(sorted(files)))
        return
    if not args.expected_head:
        parser.error('--publish requires --expected-head from the current wiki branch')
    folder = ROOT / '.runs/wiki-publication'
    folder.mkdir(parents=True, exist_ok=True)
    clone = folder / 'repository'
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(folder),
           'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_CONFIG_COUNT': '2', 'GIT_CONFIG_KEY_0': 'http.extraHeader',
           'GIT_CONFIG_VALUE_0': 'AUTHORIZATION: bearer ' + token_for('developer', '499b84ac-1321-427f-aa17-267ca6975798'),
           'GIT_CONFIG_KEY_1': 'credential.helper', 'GIT_CONFIG_VALUE_1': ''}
    def git(*params):
        proc = subprocess.run(['git', *params], cwd=folder, env=env, capture_output=True, text=True, timeout=120)
        if proc.returncode:
            raise RuntimeError('Wiki Git operation failed: ' + proc.stderr[-600:])
        return proc.stdout.strip()
    if not clone.exists():
        git('clone', '--branch', 'wikiMaster', repo_url(wiki=True), str(clone))
    if git('-C', str(clone), 'status', '--porcelain'):
        raise RuntimeError('Preserve dirty wiki publication clone')
    git('-C', str(clone), 'fetch', 'origin', 'wikiMaster')
    actual = git('-C', str(clone), 'rev-parse', 'origin/wikiMaster')
    if actual != args.expected_head:
        raise RuntimeError('Wiki moved; inspect changes and plan again')
    git('-C', str(clone), 'checkout', '--detach', actual)
    for name, content in files.items():
        path = clone / name
        if not path.resolve().is_relative_to(clone.resolve()) or path.is_symlink():
            raise RuntimeError('Unsafe wiki target')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git('-C', str(clone), 'add', '--', *sorted(files))
    if git('-C', str(clone), 'diff', '--cached', '--name-only'):
        git('-C', str(clone), '-c', 'user.name=fabric-agents-developer', '-c',
            'user.email=fabric-agents-developer@demo.invalid', 'commit', '-m', 'Publish platform handbook and agent context contract')
        # Never force: a concurrent wiki publication fails instead of overwriting it.
        git('-C', str(clone), 'push', 'origin', 'HEAD:refs/heads/wikiMaster')
    head = git('-C', str(clone), 'rev-parse', 'HEAD')
    remote = git('-C', str(clone), 'ls-remote', 'origin', 'refs/heads/wikiMaster').split()[0]
    if head != remote:
        raise RuntimeError('Published wiki verification failed')
    print('Published and verified wiki commit ' + head)

if __name__ == '__main__':
    main()
