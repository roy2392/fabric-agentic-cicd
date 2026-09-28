"""Environment-owned settings. Never infer a tenant or subscription."""
import json, os, re
from pathlib import Path
from urllib.parse import quote
ROOT = Path(__file__).resolve().parents[1]
def manifest_path():
    return Path(os.environ.get('FABRIC_AGENTS_MANIFEST', ROOT / 'config/live-resources.json'))
def load():
    value=json.loads(manifest_path().read_text())
    for key in ('ado_organization','ado_project','ado_repository'):
        if key in value and (not isinstance(value[key],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_. -]{0,100}',value[key])):
            raise ValueError('Invalid setting: '+key)
    return value
def ado_root():return 'https://dev.azure.com/'+quote(load()['ado_organization'],safe='')+'/'
def ado_project_path():return quote(load()['ado_project'],safe='')
def repo_url(wiki=False):
    m=load();name=m.get('ado_wiki_repository',m['ado_project']+'.wiki') if wiki else m['ado_repository']
    return ado_root()+ado_project_path()+'/_git/'+quote(name,safe='')
def project_url():return ado_root()+ado_project_path()
