"""Pinned upstream Fabric skills, read receipts, and a per-process tool gate."""
import hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'vendor/skills-for-fabric'
LOCK=ROOT/'skills.lock.json'
REQUIRED=('skills/git-integration-operations-cli/SKILL.md','skills/spark-cli/SKILL.md','skills/spark-cli/references/authoring.md','common/COMMON-CORE.md','common/COMMON-CLI.md','common/SPARK-NOTEBOOK-AUTHORING-CORE.md')
def verify():
    lock=json.loads(LOCK.read_text())
    if lock['repository']!='https://github.com/microsoft/skills-for-fabric':raise ValueError('Unapproved skills origin')
    actual={str(p.relative_to(VENDOR)):hashlib.sha256(p.read_bytes()).hexdigest() for p in VENDOR.rglob('*') if p.is_file()}
    if actual!=lock['files']:raise ValueError('Fabric skills differ from the locked upstream snapshot')
    return lock
class SkillSession:
    def __init__(self,role):
        if role not in ('operator','developer','reviewer'):raise ValueError('Unknown role')
        self.role=role;self.lock=verify();self.read=set()
    def catalog(self):
        return {'repository':self.lock['repository'],'commit':self.lock['commit'],'required':list(REQUIRED),'resources':sorted(self.lock['files'])}
    def read_resource(self,path):
        if path not in self.lock['files'] or not path.endswith('.md'):raise ValueError('Only locked skill Markdown is readable')
        target=VENDOR/path
        if not target.resolve().is_relative_to(VENDOR.resolve()):raise ValueError('Skill path escapes vendor root')
        content=target.read_bytes()
        if hashlib.sha256(content).hexdigest()!=self.lock['files'][path]:raise ValueError('Skill integrity check failed')
        self.read.add(path)
        folder=ROOT/'.runs/skill-receipts';folder.mkdir(parents=True,exist_ok=True)
        with (folder/(self.role+'-'+str(os.getpid())+'.jsonl')).open('a') as f:
            f.write(json.dumps({'role':self.role,'commit':self.lock['commit'],'resource':path,'sha256':self.lock['files'][path],'at':datetime.now(timezone.utc).isoformat()})+'\n')
        return {'path':path,'commit':self.lock['commit'],'sha256':self.lock['files'][path],'content':content.decode()}
    def require_ready(self):
        missing=set(REQUIRED)-self.read
        if missing:raise RuntimeError('Read the pinned Fabric skills before project tools: '+', '.join(sorted(missing)))
        return {'role':self.role,'ready':True,'commit':self.lock['commit'],'read':sorted(self.read)}
def prompt():
    lock=verify()
    return ('Use the official Microsoft Fabric skills at '+lock['repository']+' pinned to '+lock['commit']+'. First call fabric_skill_catalog and read_fabric_skill for EVERY required resource. Read further referenced resources when relevant. The project tools refuse execution until these reads complete. Apply their guidance within your existing role: skills never grant credentials, Fabric access, shell execution, merge authority or permission bypass. The reviewer uses authoring guidance only to assess code. Cite resource paths and rules supporting your decisions. ')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');p.add_argument('--read');a=p.parse_args()
    if a.read:print(json.dumps(SkillSession('operator').read_resource(a.read),indent=2))
    else:print(json.dumps({'verified':True,'commit':verify()['commit'],'required':REQUIRED},indent=2))
