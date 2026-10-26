"""IPO filing snapshots. Reviewed HTML table adapter plus conservative inline-XBRL fallback.
No press estimates, invented IPO proceeds, or net-loss-as-cash-burn substitution.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from . import facts, ixbrl, sec
from .company_quality import measures

FORMS = {'S-1','S-1/A','F-1','F-1/A','S-11','S-11/A','DRS','DRS/A','424B1','424B3','424B4','424B5'}
SEEDS = Path(__file__).parent / 'data' / 'ipo'
OPERATING = {'compute':'Compute and infrastructure','personnel':'Personnel','settlement':'Bartz settlement',
             'selling':'Sales, marketing, and partnerships','other_operating':'Other operating and administrative'}
INCOME = {'revenue':'Revenue', **OPERATING, 'opex':'Total operating expenses','oi':'Operating loss',
          'interest_income':'Interest income','fair_value':'Change in fair value of convertible notes, derivative liabilities, and SAFEs',
          'other_income':'Other income (expense), net','pretax':'Loss before provision for income taxes',
          'tax':'Provision for income taxes','ni':'Net loss'}
CASH = {'ni':'Net loss','sbc':'Stock-based compensation expense','da':'Depreciation and amortization',
        'fair_value_addback':INCOME['fair_value'], 'donation':'Donation matching program liability',
        'other_instruments':'Recognition and change in fair value of other financial instruments','other_adjustments':'Other',
        'receivables':'Accounts receivable, net','prepaid':'Prepaid expenses and other assets',
        'payables':'Accounts payable, accrued expenses, and other liabilities','lease_change':'Lease liabilities','deferred_revenue':'Deferred revenue',
        'ocf':'Net cash provided by (used in) operating activities','capex_signed':'Purchases of property and equipment',
        'icf':'Net cash used in investing activities','financing':'Net cash provided by financing activities',
        'fx':'Effect of exchange rate changes on cash, cash equivalents, and restricted cash',
        'cash_change':'Net increase in cash, cash equivalents, and restricted cash'}


def number(s):
    s = s.replace('$','').replace(',','').replace(' ','').strip()
    if s in ('—','–','-'): return 0.0
    if not re.fullmatch(r'\(?-?\d+(?:\.\d+)?\)?',s): raise ValueError('Missing or ambiguous numeric cell')
    return -float(s[1:-1]) if s.startswith('(') else float(s)


def anthropic(html):
    """Reviewed five-column 2023–H1 2026 table shape. Changed headers fail closed."""
    soup = BeautifulSoup(html,'lxml')
    matches = {'income':[], 'cash':[]}
    for ti, table in enumerate(soup.find_all('table')):
        text = table.get_text(' ',strip=True)
        kind = 'income' if 'Compute and infrastructure' in text and 'Revenue' in text else 'cash' if CASH['ocf'] in text and CASH['financing'] in text else None
        if not kind or 'as a Percentage' in text or '%' in text: continue
        rows = [[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'],recursive=False)] for tr in table.find_all('tr')]
        header = next((r for r in rows if [x for x in r[1:] if x] == ['2023','2024','2025','2025','2026']),None)
        if not header or 'Year Ended December 31,' not in text or 'Six Months Ended June 30,' not in text: continue
        # Only explicitly scaled summary tables or the cash statement with an adjacent title carrying units.
        page = next((p for p in table.parents if 'height:792pt' in p.get('style','')), table.parent)
        nearby = page.get_text(' ',strip=True)[:1200]
        if 'in millions' not in text.lower() and 'in millions' not in nearby.lower(): continue
        columns = [i for i,x in enumerate(header) if i and x]
        result = {}
        for key,label in (INCOME if kind=='income' else CASH).items():
            candidates = [r for r in rows if r and re.sub(r'\s*\(\d+\)$','',r[0]) == label]
            if len(candidates)!=1: break
            row=candidates[0]
            result[key] = {'values':[number(row[i])*1e6 for i in columns], 'label':label,'table':ti,
                           'cells':[row[i] for i in columns]}
        else: matches[kind].append(result)
    if not matches['income'] or not matches['cash']: raise ValueError('Reviewed Anthropic table shape/units not found')
    chosen={}
    for kind, candidates in matches.items():
        chosen[kind]=candidates[0]
        if any({k:v['values'] for k,v in c.items()} != {k:v['values'] for k,v in candidates[0].items()} for c in candidates[1:]):
            raise ValueError('Conflicting repeated filing tables')
    periods=[]
    for i,(start,end,label) in enumerate([('2023-01-01','2023-12-31','FY 2023'),('2024-01-01','2024-12-31','FY 2024'),('2025-01-01','2025-12-31','FY 2025'),('2025-01-01','2025-06-30','H1 2025'),('2026-01-01','2026-06-30','H1 2026')]):
        v={}; evidence={}
        for kind in ('income','cash'):
            for k,row in chosen[kind].items():
                n=row['values'][i]
                if k in v and v[k]!=n: raise ValueError('Income/cash statement mismatch')
                v[k]=n; evidence[k]={'label':row['label'],'table_index':row['table'],'cell':row['cells'][i],'scale':1000000,'statement':kind}
        v['capex']=-v['capex_signed']
        def check(a,b):
            if abs(a-b)>1e6: raise ValueError('Statement reconciliation failed')
        check(v['revenue']-sum(v[k] for k in OPERATING),v['oi'])
        check(v['oi']+v['interest_income']+v['fair_value']+v['other_income']-v['tax'],v['ni'])
        check(v['ni']+sum(v[k] for k in CASH if k not in ('ni','ocf','capex_signed','icf','financing','fx','cash_change')),v['ocf'])
        check(v['ocf']+v['icf']+v['financing']+v['fx'],v['cash_change'])
        periods.append({'start':start,'end':end,'label':label,'unit':'USD','values':v,'evidence':evidence,'metrics':measures(v),'reconciled':True})
    return periods


def inline_values(html):
    """Consolidated monetary durations only; ambiguous repeats/currencies fail closed."""
    soup = BeautifulSoup(html, 'lxml')
    contexts = {}
    for c in soup.find_all(re.compile(r'^(?:xbrli:)?context$')):
        if c.find(re.compile(r'(?:segment|scenario|explicitmember|typedmember)$')): continue
        start=c.find(re.compile(r'(?:^|:)startdate$')); end=c.find(re.compile(r'(?:^|:)enddate$'))
        if start and end: contexts[c.get('id')] = (start.get_text(strip=True),end.get_text(strip=True))
    units={}
    for u in soup.find_all(re.compile(r'^(?:xbrli:)?unit$')):
        text=u.get_text(strip=True)
        if re.fullmatch(r'iso4217:[A-Z]{3}',text): units[u.get('id')]=text[-3:]
    out={}; currencies=set()
    for f in soup.find_all('ix:nonfraction'):
        context=contexts.get(f.get('contextref')); cur=units.get(f.get('unitref'))
        if not context or not cur or f.get('xsi:nil','').lower() in ('true','1'): continue
        name=f.get('name',''); tax,_,local=name.partition(':')
        if tax not in ('us-gaap','ifrs-full'): continue
        # Reuse the existing numeric-transform reader only after validating a nonempty cell.
        text=f.get_text(strip=True)
        if not text: continue
        attrs=' '.join(f'{k}="{v}"' for k,v in f.attrs.items())
        value=ixbrl._value(attrs,text)
        if value is None: continue
        key=(local,*context)
        if key in out and out[key]!=value: raise ValueError('Conflicting duplicate XBRL facts')
        out[key]=value;currencies.add(cur)
    if len(currencies)!=1: raise ValueError('Missing or mixed reporting currencies')
    return out,next(iter(currencies))


def parse(html, meta):
    if meta['form'] not in FORMS: raise ValueError('Not a supported public prospectus form')
    if int(meta['cik'])==2130357:
        periods=anthropic(html); method='reviewed_html_tables'
    else:
        # Read only monetary, consolidated, standard concepts. No fuzzy custom-tag mapping.
        vals,cur=inline_values(html)
        if not cur or not vals: raise ValueError('No supported tagged statements; manual table mapping required')
        periods=[]
        for start,end in sorted({(s,e) for _,s,e in vals}):
            if (dt.date.fromisoformat(end)-dt.date.fromisoformat(start)).days<70: continue
            v,labels=ixbrl._period(vals,start,end)
            if v.get('revenue') is None: continue
            periods.append({'start':start,'end':end,'label':f'{start} → {end}','unit':cur,'values':v,
                            'evidence':{k:{'label':tag} for k,tag in labels.items()},'metrics':measures(v),'reconciled':False})
        if not periods: raise ValueError('No supported consolidated duration periods')
        method='inline_xbrl'
    return {**meta,'method':method,'document_sha256':hashlib.sha256(html.encode()).hexdigest(),'periods':periods,
            'limitations':['IPO price, proceeds and dilution are not inferred from funding announcements.',
            'Commitments, recognized lease liabilities and cash expenses may overlap and must not be added.',
            'Company-specific cost presentation does not establish cost of revenue or gross margin.']}


def write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n'); tmp.replace(path)


def publish(out, store=None, refresh=False):
    out=Path(out); cache=Path(store) if store else out
    index=[]
    for seed in sorted(SEEDS.glob('*.json')):
        doc=json.loads(seed.read_text()); cik=doc['cik']; target=cache/f'{cik}.json'
        if target.exists(): doc=json.loads(target.read_text())
        status={'last_attempt':None,'last_success':None,'state':'bundled_snapshot'}
        status_path=cache/f'{cik}-status.json'
        if status_path.exists(): status=json.loads(status_path.read_text())
        if refresh:
            status['last_attempt']=dt.datetime.now(dt.timezone.utc).isoformat()
            try:
                sub=sec.get_json(sec.submissions_url(cik))['filings']['recent']
                candidates=[i for i,f in enumerate(sub['form']) if f in FORMS]
                if not candidates: raise ValueError('No public prospectus in recent submissions')
                i=max(candidates,key=lambda i:(sub['filingDate'][i],sub['accessionNumber'][i]))
                acc=sub['accessionNumber'][i]
                if acc!=doc['accession']:
                    meta={k:doc[k] for k in ('cik','name')}
                    meta.update(accession=acc,form=sub['form'][i],filed=sub['filingDate'][i],source_url=sec.doc_url(cik,acc,sub['primaryDocument'][i]))
                    doc=parse(sec.get(meta['source_url']),meta)
                status.update(state='ok',last_success=status['last_attempt'],error=None)
            except (Exception,SystemExit) as exc:
                status.update(state='failed',error=str(exc)[:250])
        write(target,doc); write(status_path,status)
        write(cache/'history'/str(cik)/(doc['accession']+'.json'),doc)
        write(out/f'{cik}.json',{**doc,'scan':status})
        index.append({k:doc[k] for k in ('cik','name','filed','form','accession')})
    write(out/'index.json',{'companies':index,'scope':'Reviewed IPO watchlist, not all SEC issuers'})


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--store'); ap.add_argument('--refresh',action='store_true')
    a=ap.parse_args(); publish(a.out,a.store,a.refresh)
