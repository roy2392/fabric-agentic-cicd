"""Run or reconcile the registered source load; no generic execution target."""
import argparse,json
from scripts.developer_runtime import run_load,manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--source',required=True);args=p.parse_args()
 if args.workspace!=manifest()['demo_run']['workspace_id'] or args.source!='loyalty':p.error('Source or workspace outside demo run')
 print(json.dumps(run_load()))
