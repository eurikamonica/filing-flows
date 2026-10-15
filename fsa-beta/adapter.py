"""Read-only adapter for an exported Filing Flows company JSON. ChatGPT (OpenAI).
No import from production code; no writes to the source path.
"""
import argparse
import datetime as dt
import json
from pathlib import Path


def convert(company):
    profile=company.get('profile',{})
    quarters=company.get('quarters',[])
    if isinstance(quarters,dict):quarters=list(quarters.values())
    rows=sorted(quarters,key=lambda q:q.get('end',''))[-8:]
    periods=[];sources={};notes=[]
    for q in rows:
        end=q.get('end')
        if not end:continue
        raw=q.get('raw') or {}
        headline=q.get('headline') or {}
        values={}
        sid='filing-'+end
        sources[sid]={'url':q.get('doc_url') or q.get('index_url',''),
                      'excerpt':'Imported from existing Filing Flows export; verify the underlying filing.',
                      'accession':q.get('accn') or q.get('accession','')}
        for target,r,h in [('revenue','revenue','revenue'),('net_income','ni','ni'),('ocf','ocf','ocf'),('operating_income','oi','oi'),('capex','capex','capex')]:
            value=raw.get(r,headline.get(h))
            if isinstance(value,(int,float)) and not isinstance(value,bool):values[target]={'value':value,'source_ids':[sid]}
        start=q.get('start')
        if not start:
            # Never silently invent a duration. User must complete actual filing dates.
            start=None;notes.append(end+': supply the actual quarter start before analysis')
        periods.append({'label':q.get('label',end),'kind':'quarter','start':start,'end':end,'values':values,'reserves':[]})
    return {'schema_version':1,'author':'ChatGPT (OpenAI)','company':profile.get('name','Imported company'),
            'currency':'USD','unit':'USD','demo':False,'sources':sources,'periods':periods,
            'import_notes':notes+['Reserve rollforwards, balance sheet classifications and operating tax assumptions require separate sourced input.']}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('output');args=ap.parse_args()
    if Path(args.source).resolve()==Path(args.output).resolve():raise SystemExit('Output must differ from source')
    if Path(args.output).exists():raise SystemExit('Output already exists; choose a new path')
    result=convert(json.loads(Path(args.source).read_text(encoding='utf-8')))
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Draft imported. Complete missing dates and evidence before analysis.')
