"""Provision the two approved single-tenant, certificate-authenticated demo identities."""
import base64
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timedelta, timezone
import urllib.request
from fabric_agents.preflight import access_token, ReadClient, NoRedirect

ROOT=Path(__file__).resolve().parents[1]
from scripts.settings import load


def main():
    token,_=access_token(load()['tenant_id'],'https://graph.microsoft.com')
    c=ReadClient('https://graph.microsoft.com/v1.0/',token)
    def post(path,body):
        req=urllib.request.Request(c.safe_url(path),data=json.dumps(body).encode(),method='POST',
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=60) as r:
            data=r.read();return json.loads(data) if data else {}
    manifest_path=ROOT/'config/live-resources.json';m=json.loads(manifest_path.read_text())
    identities=m.setdefault('agents',{})
    for role in ['developer','reviewer']:
        name='fabric-agents-'+role
        folder=ROOT/'.runs/identities'/role;folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o700)
        apps=c.get('applications?$filter=displayName%20eq%20%27'+name+'%27')['value']
        if len(apps)>1: raise RuntimeError('Ambiguous app '+name)
        if apps:
            app=apps[0]
            if not (folder/'identity.pem').exists():
                raise RuntimeError('Existing app without this run certificate; reconcile manually')
        else:
            key=folder/'private.key';cert=folder/'public.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),
                '-out',str(cert),'-days','30','-subj','/CN='+name],check=True,capture_output=True)
            key.chmod(0o600)
            (folder/'identity.pem').write_bytes(key.read_bytes()+cert.read_bytes());(folder/'identity.pem').chmod(0o600)
            der=subprocess.run(['openssl','x509','-in',str(cert),'-outform','DER'],check=True,capture_output=True).stdout
            now=datetime.now(timezone.utc)
            app=post('applications',{'displayName':name,'signInAudience':'AzureADMyOrg','keyCredentials':[{
                'type':'AsymmetricX509Cert','usage':'Verify','key':base64.b64encode(der).decode(),
                'displayName':'30-day demo certificate','startDateTime':now.isoformat(),
                'endDateTime':(now+timedelta(days=29)).isoformat()}]})
        sps=c.get('servicePrincipals?$filter=appId%20eq%20%27'+app['appId']+'%27')['value']
        sp=sps[0] if sps else post('servicePrincipals',{'appId':app['appId']})
        identities[role]={'app_id':app['appId'],'application_object_id':app['id'],'object_id':sp['id']}
        manifest_path.write_text(json.dumps(m,indent=2)+'\n')
        print(role,identities[role],flush=True)

if __name__=='__main__': main()
