import argparse
import json
from pathlib import Path
from core import Client, read_json, now, publish, refresh_module, collect_cot, collect_banks, collect_npx, write_json, VERSION

from holdings import collect_holdings
from expanded import collect_cot_expanded, collect_banks_expanded, collect_npx_expanded
from congress import collect_congress
from prices import apply_prices
from shards import hydrate, hydrate_catalogs, publish_shards
import market
import insiders
import frames
import options as option_chains

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description='Collect official public disclosures; demo never substitutes for real data')
    parser.add_argument('--only',choices=['all','cot','banks','npx','holdings','congress','markets','prices','market','insiders','options'],default='all')
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
    # Officials' newest transaction reports ride along with every 13F run: the 13F schedule fills the shared run slot,
    # so the hourly officials run is often superseded; this quick House-only pass keeps the trades current.
    if args.only=='holdings' and cfg.get('congress',{}).get('quick_house_batch',12):
        print('Collecting congress (quick House pass)',flush=True)
        quick={**cfg['congress'],'_data_root':str(args.output),'quick_house':True,'batch_shares':{'US House':int(cfg['congress'].get('quick_house_batch',12))},
               'batch_size':int(cfg['congress'].get('quick_house_batch',12))}
        try:
            result=refresh_module(data['modules'].get('congress',{}),collect_congress,client,quick,False)
            data['modules']['congress']=result
            print('congress (quick): '+result['status']+((' — '+result['error']) if result.get('error') else ''),flush=True)
            data['generated_at']=now()
            publish_shards(args.output,data)
        except Exception as exc:
            print('congress (quick): error — '+str(exc),flush=True)
    # 4.1: optional price-based cost estimates, refreshed with 13F and officials' runs or on demand.
    if cfg.get('prices',{}).get('enabled') and args.only in ('all','prices','holdings','congress'):
        print('Collecting prices',flush=True)
        try:
            data['modules']['prices']=apply_prices(data,client,cfg['prices'],args.output)
        except Exception as exc:
            data['modules']['prices']={**data['modules'].get('prices',{}),'status':'error','error':str(exc),'last_attempt':now()}
        failed|=data['modules']['prices']['status']!='ok'
        print('prices: '+data['modules']['prices']['status']+((' — '+data['modules']['prices']['error']) if data['modules']['prices'].get('error') else ''),flush=True)
        data['generated_at']=now()
        publish_shards(args.output,data)
    # 4.4: Form 4 insider trades (the newest filings each run) and their published summary
    if args.only in ('all','insiders'):
        print('Collecting insiders',flush=True)
        try:
            r=insiders.collect(client,args.output,cfg.get('insiders',{}))
            insiders.publish(args.output,args.output/'market')
            print('insiders: '+json.dumps(r),flush=True)
            data['modules']['insiders']={**r,'last_attempt':now()}
            write_json(args.output/'insiders-status.json',data['modules']['insiders'])
        except Exception as exc:
            print('insiders: error — '+str(exc),flush=True)
    # 4.5: option chains (CBOE delayed quotes) once a day after the close
    if args.only in ('all','options'):
        print('Collecting option chains',flush=True)
        try:
            print('options: '+json.dumps(option_chains.collect(client,args.output,cfg.get("options",{}))),flush=True)
        except Exception as exc:
            print('options: error — '+str(exc),flush=True)
    # 4.4: SEC XBRL frames (21 quarters and the annual frames of revenue, operating income, gross profit and net income
    # for every filer) for the rotation charts; cached quarters are never fetched again, so the daily options run keeps them fresh
    if args.only in ('all','market','options'):
        print('Collecting XBRL frames',flush=True)
        try:
            print('frames: '+json.dumps(frames.collect(client,args.output,int(cfg.get('frames',{}).get('quarters',21)))),flush=True)
        except Exception as exc:
            print('frames: error — '+str(exc),flush=True)
    # 4.3: market-wide views (13F flows, officials' trades, signals) from the caches; at most every few hours unless asked for
    if args.only in ('all','holdings','congress','prices','market','insiders'):
        print('Building market views',flush=True)
        try:
            r=market.publish(args.output,client=client,min_interval_hours=float(cfg.get('market',{}).get('min_interval_hours',3)),
                             force=args.only=='market')
            print('market: '+json.dumps(r),flush=True)
        except Exception as exc:
            print('market: error — '+str(exc),flush=True)
    write_json(args.storage/'last-run-manifest.json',client.manifest)
    if failed:
        print('One or more sources failed/partial. Previous valid data retained; inspect source status.')
    return 1 if failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
