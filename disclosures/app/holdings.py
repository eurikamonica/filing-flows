"""13F adapter, retaining parsed filings in the published snapshot for durable reuse."""
from core import now
from shards import load_manager
from discovery import discover_sec, select_batch
from holdings13f.build import filing_list, load_filing
from holdings13f.core import resolve, compare

class SECAdapter:
    def __init__(self, client): self.client=client
    def get(self,url,immutable=False): return self.client.get(url,sec=True)
    def json(self,url,immutable=False): return self.client.json(url,sec=True)

def collect_holdings(client,cfg,old,revalidate=False):
    adapter=SECAdapter(client)
    old_managers={str(int(m['cik'])):m for m in old.get('managers',[])}
    discovery=discover_sec(client,cfg,old.get('discovery',{})) if cfg.get('discover_all') else old.get('discovery',{})
    items={r['cik']:r for r in discovery.get('directory',[]) if r['kind']=='holdings'}
    items.update({str(int(r['cik'])):r for r in cfg.get('managers',[])})
    managers=dict(old_managers);errors=list(discovery.get('errors',[]))
    attempts=dict(old.get('attempts',{}))
    # managers the 13F back-fill workflow finished (app/backfill13f.py, holdings-backfill.json): lazy rows, merged once
    from core import read_json
    import os as _os
    bf=read_json(_os.path.join(cfg.get('_data_root',''),'holdings-backfill.json'),{}) or {}
    if bf.get('since')==cfg['since'] and bf.get('as_of')==cfg.get('as_of'):
        for key,row in (bf.get('managers') or {}).items():
            if key not in old_managers or (old_managers[key].get('last_success') or '')<(row.get('last_success') or ''):
                old_managers[key]=row;managers[key]=row
                attempts[key]={**attempts.get(key,{}),'last_attempt':row.get('last_success'),'last_success':row.get('last_success'),'error':None}
    history={key:{**m,**attempts.get(key,{})} for key,m in old_managers.items()}
    history.update({key:value for key,value in attempts.items() if key not in history})
    target=cfg.get('priority_cik')
    if target:items.setdefault(str(int(target)),{'cik':str(int(target)),'name':'CIK '+str(int(target))})
    work=[items[str(int(target))]] if target else list(items.values())
    import datetime as _dt
    live_bf=(bf.get('updated_at') or '')>(_dt.datetime.now(_dt.timezone.utc)-_dt.timedelta(hours=6)).isoformat()
    if not target and cfg.get('backfill_separately') and live_bf:   # new managers are the (running) back-fill's: this run refreshes
        mine={str(int(r['cik'])) for r in cfg.get('managers',[])}
        work=[x for x in work if str(int(x['cik'])) in old_managers or str(int(x['cik'])) in mine]
    selected=select_batch(work,history,int(cfg.get('batch_size',8)),'cik',cfg.get('refresh_hours',24),revalidate)
    # 4.4 watched funds (config holdings.watch): processed first, and re-checked every few hours so a new 13F is picked
    # up the day it is filed (market.py writes their changes to market/watchlist.json for the X alerts)
    if not target:
        import datetime as _dt
        due=(_dt.datetime.now(_dt.timezone.utc)-_dt.timedelta(hours=float(cfg.get('watch_refresh_hours',6)))).isoformat()
        hot=[]
        for w in cfg.get('watch',[]):
            c=str(int(w['cik']))
            items.setdefault(c,{'cik':c,'name':w.get('name') or 'CIK '+c})
            if c not in old_managers or (attempts.get(c,{}).get('last_attempt') or '')<due:
                hot.append(items[c])
        hot=hot[:max(2,int(cfg.get('batch_size',8))//2)]
        selected=hot+[x for x in selected if str(int(x['cik'])) not in {str(int(h['cik'])) for h in hot}][:max(0,int(cfg.get('batch_size',8))-len(hot))]
    # Newly indexed filings take priority even when the usual 24-hour refresh is not due.
    # Preserve at least half the batch for the existing fair queue; never bypass error backoff.
    def new_filing_priority(row):
        cik=str(int(row['cik']))
        prior=old_managers.get(cik)
        if not prior:
            return False
        failed=attempts.get(cik,{})
        if failed.get('error') and failed.get('last_attempt'):
            try:
                last=_dt.datetime.fromisoformat(failed['last_attempt'])
                if (_dt.datetime.now(_dt.timezone.utc)-last).total_seconds()<3600:
                    return False
            except (ValueError,TypeError):
                pass
        known=prior.get('discovered_filing_count')
        if known is not None and int(row.get('filing_count') or 0)>int(known):
            return True
        return (row.get('latest_filing') or '')>(prior.get('last_success') or '')[:10]
    if not target:
        urgent=sorted((r for r in work if new_filing_priority(r)),
                      key=lambda r:(r.get('latest_filing') or '',int(r.get('filing_count') or 0)),reverse=True)
        budget=max(1,int(cfg.get('batch_size',8)))
        seen=set()
        prioritized=[]
        for row in urgent[:max(1,budget//2)]+selected:
            key=str(int(row['cik']))
            if key not in seen and len(prioritized)<budget:
                prioritized.append(row)
                seen.add(key)
        selected=prioritized
    for item in selected:
        cik=str(int(item['cik']))
        cached=old_managers.get(cik,{})
        attempts[cik]={'last_attempt':now()}
        # Refuse to mix a previous as-of/range build with another request.
        if cached.get('since') != cfg['since'] or cached.get('as_of') != cfg.get('as_of'):
            cached={}
        try:
            if cached.get('cache'):cached=load_manager(cfg['_data_root'],cached)
            name,metas=filing_list(adapter,cik,cfg['since'])
            prior={f['accession']:f for f in cached.get('filings',[])}
            filings,notices=[],[]
            for meta in metas:
                if cfg.get('as_of') and meta['filed']>cfg['as_of']:continue
                if meta['form'].startswith('13F-NT'):
                    notices.append(meta);continue
                filing=prior.get(meta['accession']) if not revalidate else None
                if filing is None:filing=load_filing(adapter,meta)
                filings.append(filing)
            snapshots=resolve(filings,cfg.get('as_of'))
            for i,s in enumerate(snapshots):
                s['changes']=compare(snapshots[i-1],s) if i else []
                s['baseline_period']=snapshots[i-1]['period'] if i else None
            managers[cik]={'cik':cik,'name':name,'label':item.get('name',name),'since':cfg['since'],
                             'as_of':cfg.get('as_of'),'filings':filings,'snapshots':snapshots,
                             'notices':notices,'last_success':now(),'stale':False,
                             'discovered_filing_count':item.get('filing_count')}
            attempts[cik]['last_success']=now()
        except Exception as exc:
            errors.append({'cik':cik,'error':str(exc)})
            attempts[cik]['error']=str(exc)
            if cached:managers[cik]={**cached,'stale':True}
    directory=[{**r,'processed':r['cik'] in managers,'last_attempt':attempts.get(r['cik'],{}).get('last_attempt'),'error':attempts.get(r['cik'],{}).get('error')} for r in items.values()]
    return {'managers':list(managers.values()),'directory':directory,'discovery':discovery,'attempts':attempts,
            'errors':errors,'status':'partial' if errors else 'ok',
            'counts':{'discovered_managers':len(items),'processed_managers':len(managers),'pending_managers':sum(not r['processed'] for r in directory),'attempted_this_run':len(selected)},
            'coverage':'SEC index discovery since '+cfg['since']+'; processing continues in batches. Indexes may lag publication. Public 13F positions are not real-time portfolios.'}
