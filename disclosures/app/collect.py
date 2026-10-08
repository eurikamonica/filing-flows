import argparse
import json
from pathlib import Path
from core import Client, read_json, now, publish, refresh_module, collect_cot, collect_banks, collect_npx, write_json, VERSION

from holdings import collect_holdings
from expanded import collect_cot_expanded, collect_banks_expanded, collect_npx_expanded
from congress import collect_congress
from shards import hydrate, hydrate_catalogs, publish_shards

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description='Collect official public disclosures; demo never substitutes for real data')
    parser.add_argument('--only',choices=['all','cot','banks','npx','holdings','congress','markets'],default='all')
    parser.add_argument('--config',type=Path,default=ROOT/'config/settings.json')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/data')
    parser.add_argument('--storage',type=Path,default=ROOT/'storage')
    parser.add_argument('--revalidate',action='store_true',help='Re-download already parsed N-PX documents')
    parser.add_argument('--batch-size',type=int,help='Override the manager/PDF batch size for this run')
    parser.add_argument('--manager-cik',help='Process this SEC CIK instead of the rotating batch')
    parser.add_argument('--report-id',help='Process this discovered House report instead of the rotating batch')
    parser.add_argument('--bank-cert',help='Prioritize one FDIC certificate')
    parser.add_argument('--market-id',help='Prioritize one dataset-code from the COT directory')
    args = parser.parse_args()
    cfg = read_json(args.config,{})
    data = read_json(args.output/'live.json', {'version':VERSION,'mode':'official','modules':{}})
    data=hydrate_catalogs(args.output,data)
    if 'holdings' in data['modules']:data['modules']['holdings']['discovery']=read_json(args.output/'discovery-state.json',data['modules']['holdings'].get('discovery',{}))
    if 'npx'in data['modules']:data['modules']['npx'].update(read_json(args.output/'npx-queue-state.json',{}))
    data['version'] = VERSION
    client = Client(args.storage,cfg.get('http',{}))
    failed = False
    for key,func in [('holdings',collect_holdings),('congress',collect_congress),('cot',collect_cot_expanded),('banks',collect_banks_expanded),('npx',collect_npx_expanded)]:
        if args.only not in ('all',key) and not (args.only=='markets' and key in ('cot','banks','npx')):
            continue
        print('Collecting '+key,flush=True)
        options={**cfg[key],'_data_root':str(args.output)}
        if key in ('holdings','npx') and args.manager_cik:options['priority_cik']=args.manager_cik
        if key=='congress' and args.report_id:options['priority_report_id']=args.report_id
        if key=='banks' and args.bank_cert:options['priority_id']=str(int(args.bank_cert))
        if key=='cot' and args.market_id:options['priority_id']=args.market_id
        if args.batch_size is not None:options['batch_size']=args.batch_size
        result = refresh_module(data['modules'].get(key,{}),func,client,options,args.revalidate)
        data['modules'][key] = result
        if key=='npx' and 'holdings' in data['modules']:data['modules']['holdings']['discovery']=read_json(args.output/'discovery-state.json',{})
        failed |= result['status'] != 'ok'
        print(key+': '+result['status']+((' — '+result['error']) if result.get('error') else ''),flush=True)
        data['generated_at'] = now()
        publish_shards(args.output,data)
    write_json(args.storage/'last-run-manifest.json',client.manifest)
    if failed:
        print('One or more sources failed/partial. Previous valid data retained; inspect source status.')
    return 1 if failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
