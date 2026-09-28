"""Credential-free read-only smoke surface for real agent skill consumption."""
import json,sys
from scripts.skill_registry import SkillSession
s=SkillSession(sys.argv[1])
for line in sys.stdin:
    req=json.loads(line)
    if 'id' not in req:continue
    method=req['method'];p=req.get('params',{})
    try:
        if method=='initialize':result={'protocolVersion':p.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'fabric-skills-probe','version':'1'}}
        elif method=='tools/list':result={'tools':[{'name':name,'description':desc,'inputSchema':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}} for name,desc,props in [('fabric_skill_catalog','List pinned upstream skills and required reads',{}),('read_fabric_skill','Read a complete integrity-checked upstream resource',{'path':{'type':'string'}}),('fabric_skills_ready','Require every mandatory skill read',{})]]}
        elif method=='tools/call':
            name=p['name'];args=p.get('arguments',{})
            result={'content':[{'type':'text','text':json.dumps({'fabric_skill_catalog':s.catalog,'read_fabric_skill':s.read_resource,'fabric_skills_ready':s.require_ready}[name](**args))}]}
        elif method=='ping':result={}
        else:raise ValueError('Unsupported method')
        response={'jsonrpc':'2.0','id':req['id'],'result':result}
    except Exception as e:response={'jsonrpc':'2.0','id':req['id'],'error':{'code':-32603,'message':str(e)}}
    print(json.dumps(response),flush=True)
