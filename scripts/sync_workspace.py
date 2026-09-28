"""Synchronize only the registered feature workspace."""
import argparse,json
from scripts.developer_runtime import sync_workspace,manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);args=p.parse_args()
 if args.workspace!=manifest()['demo_run']['workspace_id']:p.error('Workspace outside demo run')
 print(json.dumps(sync_workspace()))
