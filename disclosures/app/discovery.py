"""SEC index discovery. Discovery is distinct from document processing."""
import datetime as dt
import re
from core import now


def parse_master(raw, since):
    decoded=raw.decode('latin-1')
    if 'CIK|Company Name|Form Type|Date Filed|Filename' not in decoded:raise ValueError('SEC index header missing; refusing to replace catalog')
    result={}
    for line in decoded.splitlines():
        parts=line.split('|')
        if len(parts)!=5 or not parts[0].isdigit():continue
        cik,name,form,date,path=parts
        if date<since or form not in ('13F-HR','13F-HR/A','13F-NT','13F-NT/A','N-PX','N-PX/A'):continue
        if not re.fullmatch(r'edgar/data/\d+/[\d-]+\.txt',path):continue
        kind='holdings' if form.startswith('13F') else 'npx'
        key=kind+':'+str(int(cik))
        row=result.setdefault(key,{'cik':str(int(cik)),'name':name,'kind':kind,'latest_filing':date,'filing_count':0})
        row['filing_count']+=1
        row['latest_filing']=max(row['latest_filing'],date)
    return list(result.values())


def discover_sec(client,cfg,old):
    since=cfg.get('discovery_since',cfg['since'])
    start=dt.date.fromisoformat(since);today=dt.datetime.now(dt.timezone.utc).date()
    indices=dict(old.get('indices',{}));errors=[]
    for year in range(start.year,today.year+1):
        for q in range(1,5):
            if (year,q)<(start.year,(start.month-1)//3+1) or (year,q)>(today.year,(today.month-1)//3+1):continue
            key=f'{year}/QTR{q}';prior=indices.get(key,{})
            # Retain historical catalogs; monthly reconciliation catches corrections.
            age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(prior['checked_at'])).total_seconds() if prior.get('checked_at') else float('inf')
            active=(year,q)==(today.year,(today.month-1)//3+1)
            if age<(3600 if active else 86400*30) and prior.get('since')==since:continue
            url=f'https://www.sec.gov/Archives/edgar/full-index/{key}/master.idx'
            try:indices[key]={'rows':parse_master(client.get(url,sec=True),since),'checked_at':now(),'since':since,'source_url':url}
            except Exception as exc:errors.append({'index':key,'error':str(exc)})
    merged={}
    for index in indices.values():
        if index.get('since')!=since:continue
        for row in index['rows']:
            key=row['kind']+':'+row['cik']
            if key not in merged:merged[key]=dict(row)
            else:
                merged[key]['filing_count']+=row['filing_count']
                merged[key]['latest_filing']=max(merged[key]['latest_filing'],row['latest_filing'])
    return {'indices':indices,'directory':sorted(merged.values(),key=lambda x:x['name'].casefold()),'errors':errors,'since':since,'checked_at':now()}


def select_batch(items,previous,budget,id_key,refresh_hours=24,revalidate=False):
    """Fair durable queue: reserve refresh slots, back off errors, avoid starvation."""
    if budget<1:raise ValueError('batch_size must be positive')
    current=dt.datetime.now(dt.timezone.utc);fresh=[];due=[]
    for item in items:
        key=str(item[id_key]);old=previous.get(key,{})
        last=old.get('last_attempt') or old.get('last_success')
        age=(current-dt.datetime.fromisoformat(last)).total_seconds()/3600 if last else float('inf')
        if old.get('error') and age<1:continue
        if not old.get('last_success'):fresh.append(item)
        elif revalidate or age>=refresh_hours:due.append(item)
    fresh.sort(key=lambda x:(previous.get(str(x[id_key]),{}).get('last_attempt',''),str(x[id_key])))
    due.sort(key=lambda x:previous.get(str(x[id_key]),{}).get('last_attempt') or previous.get(str(x[id_key]),{}).get('last_success',''))
    reserve=min(len(due),max(1,budget//4))
    selected=due[:reserve]+fresh[:budget-reserve]
    selected+=due[reserve:reserve+budget-len(selected)]
    return selected
