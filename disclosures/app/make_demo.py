"""Rebuild explicitly fictional demo data; never writes the official snapshot."""
import datetime as dt
import json
import math
from pathlib import Path
from core import normalize_cot, normalize_banks, now
ROOT=Path(__file__).resolve().parents[1]

def main():
    cot=[]
    for i in range(65):
        day=(dt.date(2025,1,7)+dt.timedelta(weeks=i)).isoformat()
        for code,market,base in [('DEMO1','DEMO · Fictional gold futures',140000),('DEMO2','DEMO · Fictional crude futures',220000)]:
            r={'report_date_as_yyyy_mm_dd':day,'cftc_contract_market_code':code,'market_and_exchange_names':market,'open_interest_all':base*3}
            for j,(lf,sf) in enumerate(__import__('core').COT_FIELDS['disaggregated'].values()):
                r[lf]=int(base*(.6+.2*math.sin(i/8+j)))
                r[sf]=int(base*(.5+.18*math.cos(i/9+j)))
            cot.append(r)
    cot=normalize_cot(cot,'demo-data','disaggregated')
    for r in cot:r['source_url']=''
    banks=[]
    for cert,name,mult in [(900001,'DEMO · Harbor Example Bank',1),(900002,'DEMO · Cedar Example Bank',.65)]:
        for year in range(2023,2026):
            ytd=0
            for q,(month,day) in enumerate([(3,31),(6,30),(9,30),(12,31)],1):
                i=(year-2023)*4+q
                ytd+=int((1400000+i*25000)*mult)
                banks.append({'CERT':cert,'NAME':name,'REPDTE':f'{year}{month:02}{day:02}',
                              'ASSET':int((320000000+i*3000000)*mult),'DEP':int((220000000+i*2000000)*mult),
                              'LNLSNET':int((150000000+i*900000)*mult),'EQ':int((29000000+i*700000)*mult),
                              'NETINC':ytd,'ROA':1.4,'ROE':12.3})
    banks=normalize_banks(banks)
    for r in banks:r['source_url']=''
    filings=[]
    for yr in [2024,2025]:
        rows=[]
        for i in range(35):
            how=['FOR','AGAINST','ABSTAIN','FOR','1 YEAR'][i%5]
            rows.append({'id':f'demo-{yr}-{i}','issuer':['DEMO Example Energy','DEMO Example Technology','DEMO Example Retail'][i%3],
                         'cusip':f'DEMO{i%3}','isin':'','meeting_date':f'{yr}-05-{i%28+1:02}',
                         'description':['Fictional say-on-pay vote','Fictional director election','Fictional shareholder proposal'][i%3],
                         'categories':['DEMO CATEGORY'],'shares_voted':10000+i*200,'shares_on_loan':500 if i%4==0 else 0,
                         'votes':[{'how':how,'shares':10000+i*200,'management_alignment':'AGAINST' if i%5==1 else 'FOR'}],
                         'series_ids':['DEMO SERIES'],'manager_numbers':[],'source_url':'','raw_fields':{}})
        filings.append({'accession':f'DEMO-{yr}','cik':'DEMO','filer':'DEMO · Example Investment Manager',
                        'form':'N-PX','report_date':f'{yr}-06-30','filing_date':f'{yr}-08-20','is_amendment':False,
                        'parse_status':'demo','source_url':'','coverage_note':'Fictional demo records only','votes':rows})
    from holdings13f.build import demo as holdings_demo
    stamp=now()
    modules={'cot':{'rows':cot},'banks':{'rows':banks},'npx':{'filings':filings},'holdings':{'managers':holdings_demo()},'congress':{'reports':[],'records':[],'coverage_note':'Fictional demonstration only'}}
    from demo_congress import congress_demo
    modules['congress']=congress_demo()
    for m in modules.values():m.update(status='demo',updated_at=stamp,last_attempt=stamp,coverage='Fictional demonstration only')
    payload={'mode':'demo','generated_at':stamp,'modules':modules}
    (ROOT/'docs/data/demo.js').write_text('window.DISCLOSURE_DEMO = '+json.dumps(payload,ensure_ascii=False)+';\n',encoding='utf-8')

if __name__=='__main__':main()
