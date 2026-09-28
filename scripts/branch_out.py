"""Developer CLI for the registered demo issue only."""
import argparse,json
from scripts.developer_runtime import branch_out,manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--work-item',type=int,required=True);args=p.parse_args()
 if args.work_item!=manifest()['demo_work_item_id']:p.error('Only the registered demo issue is authorized')
 print(json.dumps(branch_out()))
