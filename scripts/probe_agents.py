"""Run actual model sessions against only the pinned skill reader; no cloud mutation tools."""
import argparse,json,os,subprocess,sys,tomllib
from pathlib import Path
from scripts.skill_registry import prompt
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['developer','reviewer']);a=p.parse_args();role=a.role
    out=ROOT/'.runs/skill-probes';out.mkdir(parents=True,exist_ok=True)
    instruction=prompt()+'This is a read-only acceptance check. After all required reads, call fabric_skills_ready. Explain three concrete rules you will apply to the pipeline: exact sync evidence, avoiding duplicate jobs, and correct OneLake bindings. Cite the upstream resource paths and commit. Do not claim cloud execution or perform any mutation.'
    if role=='developer':
        config={'mcpServers':{'demo':{'command':sys.executable,'args':['-m','scripts.skills_probe_mcp',role],'env':{'PYTHONPATH':str(ROOT)}}}}
        path=out/'developer-mcp.json';path.write_text(json.dumps(config))
        cmd=[sys.executable,'-m','scripts.claude_foundry','--bare','-p','--tools','','--strict-mcp-config','--mcp-config',str(path),'--allowedTools','mcp__demo__*','--permission-mode','dontAsk','--disable-slash-commands','--no-session-persistence','--max-budget-usd','10','--output-format','json',instruction]
    else:
        binary=ROOT/'.runs/codex-cli/node_modules/.bin/codex';cmd=[str(binary) if binary.exists() else 'codex','exec','--ephemeral','--skip-git-repo-check','--sandbox','read-only','--json','-C',str(out)]
        for f in ('shell_tool','unified_exec','apps','plugins','browser_use','browser_use_external','computer_use','in_app_browser','memories','multi_agent','multi_agent_v2','hooks','image_generation','workspace_dependencies','chronicle'):cmd+=['--disable',f]
        config_path=Path.home()/'.codex/config.toml'
        if config_path.exists():
            for name in tomllib.loads(config_path.read_text()).get('mcp_servers',{}):cmd+=['-c',f'mcp_servers.{name}.enabled=false']
        options={'mcp_servers.skills.command':sys.executable,'mcp_servers.skills.args':['-m','scripts.skills_probe_mcp',role],'mcp_servers.skills.env':{'PYTHONPATH':str(ROOT)},'mcp_servers.skills.default_tools_approval_mode':'approve','web_search':'disabled'}
        for k,v in options.items():cmd+=['-c',k+'='+('{' + ','.join(x+'='+json.dumps(y) for x,y in v.items())+'}' if isinstance(v,dict) else json.dumps(v))]
        cmd+=[instruction]
    with (out/(role+'.jsonl')).open('w') as stdout,(out/(role+'.stderr')).open('w') as stderr:
        r=subprocess.run(cmd,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=900)
    print(role,'process exit',r.returncode)
    raise SystemExit(r.returncode)
if __name__=='__main__':main()
