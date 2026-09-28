"""Fail CI on private payloads, unpinned skills/actions, or unsafe workflow triggers."""
import json,re,subprocess
from pathlib import Path
from scripts.skill_registry import verify
ROOT=Path(__file__).resolve().parents[1]
def main():
 verify()
 files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
 for name in filter(None,files):
  p=ROOT/name
  if name.startswith(('.runs/','.venv/')) or name=='config/live-resources.json' or p.suffix in ('.key','.pem','.pfx'):raise RuntimeError('Private runtime material tracked: '+name)
  if name.startswith('vendor/'):continue
  try:text=p.read_text()
  except UnicodeDecodeError:raise RuntimeError('Unexpected binary in source release: '+name)
  markers=('dev.azure.com/'+'roeyzalta','MngEnv'+'MCAP','/Users/'+'roeyzalta','b2g-care-'+'foundry')
  if any(x in text for x in markers):raise RuntimeError('Environment-specific content: '+name)
  if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',text):raise RuntimeError('Private key found: '+name)
  if re.search(r'gh[pousr]_[A-Za-z0-9]{30,}',text):raise RuntimeError('GitHub credential found: '+name)
 for p in (ROOT/'.github/workflows').glob('*.yml'):
  text=p.read_text()
  if 'pull_request_target:' in text:raise RuntimeError('Privileged PR workflow is prohibited')
  for value in re.findall(r'uses:\s*([^\s#]+)',text):
   if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}',value):raise RuntimeError('Unpinned action: '+value)
 print('Release source, pinned skills and workflow checks passed')
if __name__=='__main__':main()
