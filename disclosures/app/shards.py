"""Small public catalog, per-quarter payloads, compressed collector cache."""
from pathlib import Path
from core import read_json, write_json, publish
import re,json,gzip


def safe_path(root,relative):
    if not re.fullmatch(r'shards/(holdings|congress|cot|banks|npx)/[A-Za-z0-9_+-]+\.json',relative):raise ValueError('Invalid shard path')
    return Path(root)/relative


def load_manager(root,row):
    if not row.get('cache'):return row
    if not re.fullmatch(r'cache/holdings/\d+\.json\.gz',row['cache']):raise ValueError('Invalid cache path')
    with gzip.open(Path(root)/row['cache'],'rt',encoding='utf-8')as f:return json.load(f)


def hydrate(root,data):
    """Explicit full hydration for migration/tests, not routine collection."""
    for key,field in [('holdings','managers'),('congress','reports')]:
        rows=data.get('modules',{}).get(key,{}).get(field,[])
        for i,row in enumerate(rows):
            if key=='holdings' and row.get('cache'):rows[i]=load_manager(root,row)
            elif row.get('shard'):
                payload=read_json(safe_path(root,row['shard']),None)
                if payload is None:raise ValueError('Missing shard: '+row['shard'])
                rows[i]=payload
    return data


def compact_write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');tmp.replace(path)


def hydrate_catalogs(root,data):
    for key,module in data.get('modules',{}).items():
        path=module.get('directory_shard')
        if not path:continue
        if path!=f'catalogs/{key}.json' or key not in ('holdings','congress','cot','banks','npx'):raise ValueError('Invalid catalog path')
        rows=read_json(Path(root)/path,None)
        if not isinstance(rows,list):raise ValueError('Missing or invalid catalog: '+path)
        module['directory']=rows
    return data


def publish_shards(root,data):
    out={**data,'modules':{k:dict(v)for k,v in data.get('modules',{}).items()}}
    for key,field,ident in [('holdings','managers','cik'),('congress','reports','report_id')]:
        module=out['modules'].get(key,{});summaries=[]
        for row in module.get(field,[]):
            # Already published rows stay lazy, so full-market runs do not hydrate every history.
            if row.get('shard') and ('snapshots' not in row if key=='holdings' else 'candidates' not in row):
                summaries.append(row);continue
            path=f"shards/{key}/{row[ident]}.json"
            summary={k:v for k,v in row.items() if k not in ('filings','snapshots','candidates','_loaded','shard','cache')}
            if key=='holdings':
                cache=f"cache/holdings/{row[ident]}.json.gz";target=Path(root)/cache;target.parent.mkdir(parents=True,exist_ok=True)
                with gzip.open(target.with_suffix('.tmp'),'wt',encoding='utf-8')as f:json.dump(row,f,separators=(',',':'),ensure_ascii=False,allow_nan=False)
                target.with_suffix('.tmp').replace(target)
                snaps=row.get('snapshots',[]);last=snaps[-1] if snaps else {}
                public_snaps=[]
                for snap in snaps:
                    positions_path=f"shards/holdings/{row[ident]}-{snap['period']}.json"
                    compact_write(safe_path(root,positions_path),snap['positions'])
                    public_snaps.append({**{k:v for k,v in snap.items() if k not in ('positions','changes')},'positions_shard':positions_path})
                compact_write(safe_path(root,path),{**summary,'snapshots':public_snaps})
                summary.update(period_count=len(snaps),latest_period=last.get('period'),position_count=len(last.get('positions',[])),total_usd=last.get('total_usd'),cache=cache)
            else:
                compact_write(safe_path(root,path),row)
                summary['candidate_count']=len(row.get('candidates',[]))
            summary['shard']=path;summaries.append(summary)
        module[field]=summaries
        if key=='holdings' and 'discovery' in module:
            module['npx_directory']=[r for r in module['discovery'].get('directory',[]) if r['kind']=='npx']
            write_json(Path(root)/'discovery-state.json',module.pop('discovery'))
    for key in ('cot','banks'):
        module=out['modules'].get(key,{})
        if 'series'not in module:continue
        summaries=[]
        for row in module['series']:
            if row.get('shard') and 'rows'not in row:summaries.append(row);continue
            path=f"shards/{key}/{row['id']}.json"
            compact_write(safe_path(root,path),row)
            rows=row.get('rows',[])
            summaries.append({**{k:v for k,v in row.items()if k!='rows'},'shard':path,'row_count':len(rows),'latest_date':max((r['date']for r in rows),default=None)})
        module['series']=summaries
        module.pop('rows',None)
    module=out['modules'].get('npx',{})
    summaries=[]
    for filing in module.get('filings',[]):
        if filing.get('shard') and 'votes'not in filing:summaries.append(filing);continue
        acc=filing['accession'];votes=filing.get('votes',[])
        # Chunk public vote records to avoid one huge payload or an unbounded browser load.
        chunks=[]
        for i in range(0,len(votes),1000):
            path=f"shards/npx/{acc}-{i//1000:05d}.json";compact_write(safe_path(root,path),votes[i:i+1000]);chunks.append(path)
        header={k:v for k,v in filing.items()if k not in ('votes','shard','vote_chunks')}
        path=f"shards/npx/{acc}.json";compact_write(safe_path(root,path),{**header,'vote_chunks':chunks,'vote_count':len(votes)})
        summaries.append({**header,'shard':path,'vote_count':len(votes)})
    module['filings']=summaries
    if 'filing_directory'in module or 'filer_attempts'in module:
        write_json(Path(root)/'npx-queue-state.json',{k:module.get(k,{})for k in ('filing_directory','filer_attempts','document_attempts')})
        for k in ('filing_directory','filer_attempts','document_attempts'):module.pop(k,None)
    for key,module in out['modules'].items():
        if isinstance(module.get('directory'),list):
            path=f'catalogs/{key}.json';compact_write(Path(root)/path,module.pop('directory'));module['directory_shard']=path
    if out['modules'].get('npx',{}).get('directory_shard'):
        out['modules'].get('holdings',{}).pop('npx_directory',None)
    publish(root,out)
