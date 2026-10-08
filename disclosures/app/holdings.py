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
    history={key:{**m,**attempts.get(key,{})} for key,m in old_managers.items()}
    history.update({key:value for key,value in attempts.items() if key not in history})
    target=cfg.get('priority_cik')
    if target:items.setdefault(str(int(target)),{'cik':str(int(target)),'name':'CIK '+str(int(target))})
    work=[items[str(int(target))]] if target else list(items.values())
    selected=select_batch(work,history,int(cfg.get('batch_size',8)),'cik',cfg.get('refresh_hours',24),revalidate)
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
                             'notices':notices,'last_success':now(),'stale':False}
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
