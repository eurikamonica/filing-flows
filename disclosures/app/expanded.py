"""Catalog discovery and independent bounded queues for COT, FDIC and N-PX."""
import datetime as dt
from urllib.parse import urlencode
from core import (now,read_json,collect_cot,collect_banks,discover_npx,download_npx,COT_FIELDS)
from discovery import select_batch,discover_sec
from pathlib import Path
import re


def recent(stamp,hours):
    if not stamp:return False
    return (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(stamp)).total_seconds()<hours*3600


def migrate_series(old,kind):
    previous={str(r['id']):dict(r) for r in old.get('series',[])}
    for row in old.get('rows',[]):
        ident=str(row['cert']) if kind=='banks' else row['dataset']+'-'+row['code']
        seed={'id':ident,'rows':[],'last_success':old.get('updated_at'),'last_attempt':old.get('updated_at')}
        if kind=='banks':seed.update(cert=row['cert'],name=row['name'])
        else:seed.update(dataset=row['dataset'],code=row['code'],family=row['family'],name=row['market'])
        previous.setdefault(ident,seed)['rows'].append(row)
    return previous


def discover_banks(client,cfg):
    rows=[];offset=0;expected=None
    while True:
        params={'fields':'CERT,NAME,ACTIVE,STALP,CITY','limit':1000,'offset':offset,'sort_by':'CERT','sort_order':'ASC','format':'json'}
        if cfg.get('active_only',True):params['filters']='ACTIVE:1'
        payload=client.json('https://api.fdic.gov/banks/institutions?'+urlencode(params))
        page=payload['data']
        total=payload.get('meta',{}).get('total')
        if expected is None:expected=total
        elif total is not None and total!=expected:raise ValueError('FDIC directory changed during pagination; retry discovery')
        if not isinstance(page,list):raise ValueError('Invalid FDIC directory response')
        for item in page:
            r=item['data'];cert=int(r['CERT'])
            rows.append({'id':str(cert),'cert':cert,'name':r['NAME'],'active':r.get('ACTIVE'),'state':r.get('STALP',''),'city':r.get('CITY','')})
        if len(page)<1000:break
        offset+=1000
        if offset>100000:raise ValueError('FDIC directory pagination safety limit')
    if not rows:raise ValueError('Empty FDIC directory; prior catalog retained')
    if expected is not None and len(rows)!=int(expected):raise ValueError('Incomplete FDIC directory pagination')
    dedup={r['id']:r for r in rows}
    if len(dedup)!=len(rows):raise ValueError('Unstable FDIC pagination: duplicate CERTs; retry discovery')
    return list(dedup.values())


def discover_cot(client,cfg):
    found={}
    for ds in cfg['datasets']:
        if ds['family']not in COT_FIELDS or not re.fullmatch(r'[a-z0-9]{4}-[a-z0-9]{4}',ds['id']):raise ValueError('Invalid COT dataset')
        offset=0
        while True:
            params={'$select':'cftc_contract_market_code,market_and_exchange_names,max(report_date_as_yyyy_mm_dd) as latest_report',
                    '$where':f"report_date_as_yyyy_mm_dd >= '{dt.date.fromisoformat(cfg['since']).isoformat()}T00:00:00'",
                    '$group':'cftc_contract_market_code,market_and_exchange_names','$order':'cftc_contract_market_code,market_and_exchange_names','$limit':1000,'$offset':offset}
            page=client.json(f"https://publicreporting.cftc.gov/resource/{ds['id']}.json?"+urlencode(params))
            if not isinstance(page,list):raise ValueError('Invalid CFTC directory response')
            for r in page:
                code=r['cftc_contract_market_code']
                if not re.fullmatch(r'[A-Za-z0-9+]+',code):raise ValueError('Invalid CFTC market code')
                ident=ds['id']+'-'+code
                entry={'id':ident,'dataset':ds['id'],'family':ds['family'],'code':code,'name':r['market_and_exchange_names'],'latest_report':r['latest_report'][:10]}
                if ident not in found or entry['latest_report']>found[ident]['latest_report']:found[ident]=entry
            if len(page)<1000:break
            offset+=1000
            if offset>100000:raise ValueError('CFTC directory pagination safety limit')
    if not found:raise ValueError('Empty CFTC directory; prior catalog retained')
    return list(found.values())


def collect_series(client,cfg,old,kind,revalidate=False):
    previous=migrate_series(old,kind);errors=[]
    catalog=list(old.get('directory',[]));checked=old.get('directory_checked_at')
    signature={k:cfg.get(k)for k in ('since','active_only','datasets','discover_all')}
    if not cfg.get('discover_all',True):catalog=[];checked=now()
    elif not catalog or old.get('directory_signature')!=signature or not recent(checked,cfg.get('discovery_hours',24)):
        try:
            catalog=(discover_banks if kind=='banks' else discover_cot)(client,cfg);checked=now()
        except Exception as exc:errors.append({'stage':'discovery','error':str(exc)})
    entries={r['id']:dict(r)for r in catalog}
    # Keep prior successful records available even if a market/bank leaves the current catalog.
    for ident,r in previous.items():entries.setdefault(ident,{k:v for k,v in r.items()if k in ('id','cert','name','dataset','code','family')})
    if kind=='banks':
        for cert in cfg.get('certs',[]):entries.setdefault(str(int(cert)),{'id':str(int(cert)),'cert':int(cert),'name':'FDIC '+str(cert)})
    else:
        for ds in cfg['datasets']:
            for code in ds.get('codes',[]):entries.setdefault(ds['id']+'-'+code,{'id':ds['id']+'-'+code,'dataset':ds['id'],'family':ds['family'],'code':code,'name':code})
    attempts=dict(old.get('attempts',{}));history={k:{**r,**attempts.get(k,{})}for k,r in previous.items()}
    history.update({k:r for k,r in attempts.items()if k not in history})
    target=cfg.get('priority_id')
    if target and target not in entries:
        if kind=='banks' and str(target).isdigit():entries[target]={'id':target,'cert':int(target),'name':'FDIC '+target}
        else:raise ValueError('Priority market not found in discovered catalog')
    work=[entries[target]]if target else list(entries.values())
    selected=select_batch(work,history,int(cfg.get('batch_size',10)),'id',cfg.get('refresh_hours',168),revalidate)
    for item in selected:
        print(f"  {kind}: {item['id']} {item.get('name','')}",flush=True)
        ident=item['id'];attempts[ident]={'last_attempt':now()}
        try:
            if kind=='banks':result=collect_banks(client,{**cfg,'certs':[item['cert']]},{},revalidate)
            else:result=collect_cot(client,{**cfg,'datasets':[{'id':item['dataset'],'family':item['family'],'codes':[item['code']]}]},{},revalidate)
            previous[ident]={**item,'rows':result['rows'],'since':cfg['since'],'last_success':now(),'last_attempt':now(),'stale':False}
            attempts[ident]['last_success']=now()
        except Exception as exc:
            attempts[ident]['error']=str(exc);errors.append({'id':ident,'error':str(exc)})
            if ident in previous:previous[ident]={**previous[ident],'stale':True}
    directory=[{**r,'processed':r['id'] in previous,'error':attempts.get(r['id'],{}).get('error')}for r in entries.values()]
    return {'series':list(previous.values()),'directory':directory,'directory_checked_at':checked,'directory_signature':signature,'attempts':attempts,'errors':errors,
            'counts':{'discovered':len(entries),'processed':len(previous),'pending':sum(not r['processed']for r in directory),'attempted_this_run':len(selected)},
            'unit':'USD thousands'if kind=='banks'else'contracts','status':'partial'if errors else'ok',
            'coverage':('FDIC '+('active institutions' if cfg.get('active_only',True)else'all returned institutions')+' plus retained/explicit banks; historical coverage starts '+cfg['since'] if kind=='banks'else'All discovered markets in configured Disaggregated/TFF futures-only datasets since '+cfg['since']+'. Legacy, combined and supplemental datasets are not included.')}


def collect_banks_expanded(client,cfg,old,revalidate=False):return collect_series(client,cfg,old,'banks',revalidate)
def collect_cot_expanded(client,cfg,old,revalidate=False):return collect_series(client,cfg,old,'cot',revalidate)


def collect_npx_expanded(client,cfg,old,revalidate=False):
    root=Path(cfg['_data_root']);shared=read_json(root/'discovery-state.json',{})
    discovery=discover_sec(client,{**cfg,'discovery_since':cfg.get('discovery_since','2025-01-01')},shared) if cfg.get('discover_all',True) else {**shared,'errors':[]}
    # Updated catalog also remains useful to the 13F collector.
    from core import write_json
    write_json(root/'discovery-state.json',discovery)
    catalog={r['cik']:dict(r)for r in discovery.get('directory',[])if r['kind']=='npx'} if cfg.get('discover_all',True) else {}
    for cik in cfg.get('ciks',[]):catalog.setdefault(str(int(cik)),{'cik':str(int(cik)),'name':'CIK '+str(int(cik))})
    for filing in old.get('filings',[]):catalog.setdefault(str(int(filing['cik'])),{'cik':str(int(filing['cik'])),'name':filing['filer']})
    target=str(int(cfg['priority_cik'])) if cfg.get('priority_cik') else None
    if target:catalog.setdefault(target,{'cik':target,'name':'CIK '+target})
    attempts=dict(old.get('filer_attempts',{}));errors=list(discovery.get('errors',[]))
    previous={f['accession']:dict(f)for f in old.get('filings',[])}
    filings=dict(old.get('filing_directory',{}))
    for acc,f in previous.items():filings.setdefault(acc,{'accession':acc,'accessionNumber':acc,'cik':f['cik'],'filer':f['filer'],'form':f['form'],'filingDate':f['filing_date'],'reportDate':f.get('report_date','')})
    selected=select_batch([catalog[target]]if target else list(catalog.values()),attempts,int(cfg.get('batch_size',4)),'cik',cfg.get('refresh_hours',168),revalidate)
    for item in selected:
        cik=item['cik'];print('  N-PX filer '+cik,flush=True);attempts[cik]={'last_attempt':now()}
        try:
            name,found=discover_npx(client,cik.zfill(10),cfg['since'])
            for f in found:filings[f['accessionNumber']]={**f,'accession':f['accessionNumber'],'cik':cik.zfill(10),'filer':name}
            attempts[cik].update(last_success=now(),filings_found=len(found));catalog[cik]['name']=name
        except Exception as exc:attempts[cik]['error']=str(exc);errors.append({'cik':cik,'error':str(exc)})
    file_attempts=dict(old.get('document_attempts',{}))
    history={k:{'last_success':v.get('fetched_at') if v.get('parse_status')!='failed'else None,**file_attempts.get(k,{})}for k,v in previous.items()}
    history.update({k:v for k,v in file_attempts.items()if k not in history})
    docs=select_batch([f for f in filings.values()if not target or int(f['cik'])==int(target)],history,int(cfg.get('document_batch_size',12)),'accession',876000,revalidate)
    for meta in docs:
        acc=meta['accession'];print('  N-PX document '+acc,flush=True);file_attempts[acc]={'last_attempt':now()}
        try:
            record=download_npx(client,meta['cik'],meta['filer'],meta)
            if acc in previous:record['first_seen_at']=previous[acc].get('first_seen_at',record['first_seen_at'])
            previous[acc]=record;file_attempts[acc]['last_success']=now()
        except Exception as exc:
            file_attempts[acc]['error']=str(exc);errors.append({'accession':acc,'error':str(exc)})
            if acc in previous:previous[acc]={**previous[acc],'refresh_error':str(exc)}
    available_ciks={str(int(f['cik']))for f in previous.values()}
    directory=[{**r,'processed':r['cik']in available_ciks,'scanned':bool(attempts.get(r['cik'],{}).get('last_success')),'error':attempts.get(r['cik'],{}).get('error')}for r in catalog.values()]
    return {'filings':list(previous.values()),'directory':directory,'filer_attempts':attempts,'document_attempts':file_attempts,'filing_directory':filings,'errors':errors,
            'counts':{'discovered_filers':len(catalog),'scanned_filers':sum(r['scanned']for r in directory),'available_filers':len(available_ciks),'pending_filers':sum(not r['scanned']for r in directory),'discovered_filings':len(filings),'downloaded_filings':len(previous),'pending_filings':sum(acc not in previous for acc in filings),'filers_attempted_this_run':len(selected),'documents_attempted_this_run':len(docs)},
            'status':'partial'if errors else'ok','coverage':'SEC N-PX filer discovery since '+discovery.get('since',cfg.get('discovery_since',cfg['since']))+'; filing histories since '+cfg['since']+'. Incremental filer and document queues. Notice/no-vote/legacy files are not inferred to contain zero holdings.'}
