"""House report discovery + local PDF/OCR extraction + source-bound reviewed records.
Candidates are never automatically promoted to disclosed holdings or transactions.
"""
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urljoin
import zipfile
from core import now, read_json, write_json

ROOT=Path(__file__).resolve().parents[1]
HOUSE='https://disclosures-clerk.house.gov'
REVIEW_FIELDS=['id','report_id','source_sha256','page','kind','asset','ticker','owner','transaction_type','transaction_date','amount_min','amount_max','valuation_date','valuation_basis','reviewer','reviewed_at','notes']
RANGE=re.compile(r'(?:(Over|More than)\s+)?\$\s*([\d,]+)(?:\s*[-–]\s*\$?\s*([\d,]+))?',re.I)

def safe_local(value):
    p=(ROOT/value).resolve()
    if not p.is_relative_to(ROOT):raise ValueError('Local path must stay inside the project')
    return p

def parse_amount(text):
    m=RANGE.fullmatch(text.strip())
    if not m:raise ValueError('Not a recognized disclosure amount')
    low=int(m[2].replace(',',''))
    high=int(m[3].replace(',','')) if m[3] else None
    if m[1] and high is None:low+=1
    if high is not None and high<low:raise ValueError('Reversed amount interval')
    return low,high

def positioned_ranges(words):
    """Match bounds within the same visual column, avoiding adjacent income columns."""
    result=[]
    for i,w in enumerate(words):
        token=w['text'].strip();height=max(1,float(w['bottom'])-float(w['top']))
        if not re.fullmatch(r'\$[\d,]+',token):continue
        low=int(token[1:].replace(',',''))
        previous=words[i-1] if i else None
        if previous and previous['text'].lower() in ('over','than') and abs(previous['top']-w['top'])<height/2:
            result.append({'amount_text':'Over '+token,'amount_min':low+1,'amount_max':None,'top':w['top']});continue
        hyphens=[n for n in words[i+1:i+4] if n['text'] in ('-','–') and abs(n['top']-w['top'])<height/2 and 0<=n['x0']-w['x1']<height*2]
        if not hyphens:continue
        dash=hyphens[0]
        choices=[]
        for n in words:
            if not re.fullmatch(r'\$?[\d,]+',n['text']):continue
            same=abs(n['top']-w['top'])<height/2 and 0<=n['x0']-dash['x1']<height*2
            below=height/2<n['top']-w['top']<height*2.6 and abs(n['x0']-w['x0'])<height*2
            if same or below:choices.append(n)
        if not choices:continue
        n=min(choices,key=lambda n:(abs(n['top']-w['top']),abs(n['x0']-w['x0'])))
        high=int(n['text'].replace('$','').replace(',',''))
        if high<low:continue
        result.append({'amount_text':token+' - $'+format(high,','),'amount_min':low,'amount_max':high,'top':w['top']})
    return result

def extract_pdf(path,options,force_ocr=False):
    import pdfplumber
    result=[]
    with pdfplumber.open(path) as pdf:
        cap=int(options.get('max_pdf_pages',100))
        if len(pdf.pages)>cap:raise ValueError(f'PDF has {len(pdf.pages)} pages; limit is {cap}; no silent truncation')
        for i,page in enumerate(pdf.pages,1):
            text=(page.extract_text(layout=False) or '').replace('\x00','')
            positioned=page.extract_words()
            method='text';confidence=None
            if force_ocr or len(re.sub(r'\s','',text))<60:
                if not shutil.which('pdftoppm') or not shutil.which('tesseract'):
                    raise RuntimeError('OCR needs Poppler pdftoppm and Tesseract on PATH')
                with tempfile.TemporaryDirectory() as tmp:
                    prefix=str(Path(tmp)/'page')
                    subprocess.run(['pdftoppm','-f',str(i),'-l',str(i),'-singlefile','-r',str(int(options.get('ocr_dpi',200))),'-png',str(path),prefix],check=True,capture_output=True,timeout=120)
                    raw=subprocess.run(['tesseract',prefix+'.png','stdout','-l','eng','--psm','6','tsv'],check=True,capture_output=True,timeout=120).stdout.decode('utf-8')
                    words=list(csv.DictReader(io.StringIO(raw),delimiter='\t'))
                    lines={};confs=[]
                    for w in words:
                        if not w.get('text','').strip():continue
                        key=(w['block_num'],w['par_num'],w['line_num'])
                        lines.setdefault(key,[]).append(w['text'])
                        conf=float(w.get('conf','-1'))
                        if conf>=0:confs.append(conf)
                    text='\n'.join(' '.join(v)for v in lines.values())
                    positioned=[{'text':w['text'],'x0':float(w['left']),'x1':float(w['left'])+float(w['width']),'top':float(w['top']),'bottom':float(w['top'])+float(w['height'])}for w in words if w.get('text','').strip()]
                    confidence=sum(confs)/len(confs) if confs else None
                    method='ocr'
            ranges=positioned_ranges(positioned)
            for item in ranges:
                near=[w['text']for w in positioned if abs(w['top']-item['top'])<40*(int(options.get('ocr_dpi',200))/72 if method=='ocr' else 1)]
                item['excerpt']=' '.join(near).replace('\x00','')
            result.append({'page':i,'method':method,'mean_word_confidence':confidence,'text':text,'money_ranges':ranges})
    return result

def public_excerpt(text):
    # Minimize residential address details in the public review preview.
    return re.sub(r"\b\d{1,6}\s+[A-Za-z][A-Za-z0-9 .'-]{0,65}\s+-\s+Home\b", '[Residential address omitted] - Home', text)

def make_candidates(pages,report_id,digest):
    result=[]
    for p in pages:
        text=p['text']
        candidates=p.get('money_ranges')
        if candidates is None:
            candidates=[]
            for m in RANGE.finditer(text):
                if not m[1] and not m[3]:continue
                try:low,high=parse_amount(m[0])
                except ValueError:continue
                candidates.append({'amount_min':low,'amount_max':high,'amount_text':m[0],'excerpt':text[max(0,m.start()-240):min(len(text),m.end()+200)]})
        for i,candidate in enumerate(candidates):
            low,high=candidate['amount_min'],candidate['amount_max']
            excerpt=candidate['excerpt']
            result.append({'id':hashlib.sha256(f'{report_id}|{digest}|{p["page"]}|{i}'.encode()).hexdigest()[:24],
                           'report_id':report_id,'source_sha256':digest,'page':p['page'],'kind':'unclassified',
                           'asset':'','ticker':'','owner':'','transaction_type':'','transaction_date':'',
                           'amount_min':low,'amount_max':high,'valuation_date':'','valuation_basis':'',
                           'reviewer':'','reviewed_at':'','notes':'','amount_text':candidate['amount_text'],
                           'method':p['method'],'mean_word_confidence':p['mean_word_confidence'],
                           'excerpt':public_excerpt(excerpt),'review_status':'needs_review'})
    return result

def read_house_index(data,year):
    with zipfile.ZipFile(io.BytesIO(data))as z:
        names=[n for n in z.namelist()if n.lower()==f'{year}fd.txt']
        if len(names)!=1:raise ValueError('Missing expected House index TXT')
        if z.getinfo(names[0]).file_size>30*1024*1024:raise ValueError('Oversized index')
        text=z.read(names[0]).decode('utf-8-sig')
    rows=list(csv.DictReader(io.StringIO(text),delimiter='\t'))
    if rows and not {'DocID','First','Last','Year','FilingType','FilingDate'}.issubset(rows[0]):raise ValueError('House index schema changed')
    return rows

def house_meta(row):
    doc=str(row['DocID']);year=str(row['Year'])
    if not doc.isdigit() or not re.fullmatch(r'\d{4}',year):raise ValueError('Invalid House report identifier')
    typ=row['FilingType']
    if typ not in ('P','O'):raise ValueError('Unsupported House filing code; import this report explicitly')
    route='ptr-pdfs' if typ=='P' else 'financial-pdfs'
    return {'report_id':'house-'+doc,'person':' '.join(x for x in [row['First'],row['Last'],row.get('Suffix','')]if x),
            'jurisdiction':'US House','office':row.get('StateDst',''),'index_year':int(year),
            'report_type':'PTR' if typ=='P' else 'Annual','filing_type_code':typ,
            'filed_date':dt.datetime.strptime(row['FilingDate'],'%m/%d/%Y').date().isoformat() if row.get('FilingDate','').strip() else '',
            'source_url':f'{HOUSE}/public_disc/{route}/{year}/{doc}.pdf'}

def process_document(raw,meta,client,options,force_ocr=False):
    if not raw.startswith(b'%PDF'):raise ValueError('Source did not return a PDF')
    digest=hashlib.sha256(raw).hexdigest()
    folder=client.root/'congress';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(digest+'.pdf');path.write_bytes(raw)
    pages=extract_pdf(path,options,force_ocr)
    write_json(folder/(digest+'.pages.json'),pages)
    return {**meta,'source_sha256':digest,'first_seen_at':now(),'extracted_at':now(),
            'page_count':len(pages),'page_methods':[{'page':p['page'],'method':p['method'],'mean_word_confidence':p['mean_word_confidence']}for p in pages],
            'candidates':make_candidates(pages,meta['report_id'],digest),'status':'extracted','stale':False}

def load_reviewed(path,reports):
    if not path.exists():return [],[]
    lookup={r['report_id']:r for r in reports}
    records,errors,seen=[],[],set()
    with path.open(encoding='utf-8-sig',newline='')as stream:
        for i,row in enumerate(csv.DictReader(stream),2):
            try:
                if not row.get('id') or row['id']in seen:raise ValueError('Missing or duplicate record ID')
                seen.add(row['id']);report=lookup[row['report_id']]
                if report.get('source_sha256')!=row['source_sha256']:raise ValueError('Source hash mismatch: re-review changed document')
                page=int(row['page'])
                if not 1<=page<=report['page_count']:raise ValueError('Invalid page')
                if row['kind']not in ('asset','transaction'):raise ValueError('kind must be asset or transaction')
                if not row['asset'].strip()or not row['reviewer'].strip():raise ValueError('Asset and reviewer required')
                dt.date.fromisoformat(row['reviewed_at'])
                low=int(row['amount_min']);high=int(row['amount_max'])if row.get('amount_max')else None
                if low<0 or(high is not None and high<low):raise ValueError('Invalid interval')
                if row['kind']=='transaction':
                    dt.date.fromisoformat(row['transaction_date'])
                    if row['transaction_type'] not in ('purchase','sale','exchange','other'):raise ValueError('Invalid transaction type')
                elif not row['valuation_basis'].strip():raise ValueError('Assets need valuation_basis')
                if row.get('valuation_date'):dt.date.fromisoformat(row['valuation_date'])
                records.append({**row,'page':page,'amount_min':low,'amount_max':high,
                                'person':report['person'],'jurisdiction':report['jurisdiction'],
                                'report_type':report['report_type'],'filed_date':report['filed_date'],
                                'source_url':report['source_url'],'report_stale':report.get('stale',False),
                                'review_status':'reviewed'})
            except Exception as exc:errors.append(f'Review CSV line {i}: {exc}')
    return records,errors

def collect_congress(client,cfg,old,revalidate=False):
    from discovery import select_batch
    previous={r['report_id']:r for r in old.get('reports',[])}
    result=dict(previous);errors=[];coverage=[];catalog={};discovery_failed=False
    try:
        html=client.get(HOUSE+'/FinancialDisclosure/ViewReport').decode('utf-8')
        links=[urljoin(HOUSE,x)for x in re.findall(r'href=["\']([^"\']+)["\']',html)]
        years=cfg['years']
        if cfg.get('auto_current_year',True):years=sorted(set(years+[dt.datetime.now(dt.timezone.utc).year]))
        for year in years:
            try:
                match=[u for u in links if u.lower().endswith(f'/{int(year)}fd.zip')]
                if len(match)!=1:raise ValueError(f'Official annual index unavailable for {year}')
                rows=read_house_index(client.get(match[0]),year)
                allowed={s.casefold()for s in cfg.get('last_names',[])}
                matched=[r for r in rows if not allowed or r['Last'].casefold()in allowed]
                supported=[r for r in matched if r['FilingType']in ('O','P')]
                unsupported=[r for r in matched if r['FilingType']not in ('O','P')]
                coverage.append({'year':year,'matched':len(matched),'supported':len(supported),
                                 'unsupported_count':len(unsupported),'unsupported_filing_codes':sorted({r['FilingType']for r in unsupported}),'truncated':False})
                for row in matched:
                    if row['FilingType']in ('O','P'):meta=house_meta(row)
                    else:
                        meta={'report_id':'house-'+str(row['DocID']),'person':' '.join([row['First'],row['Last']]),'jurisdiction':'US House','office':row.get('StateDst',''),'index_year':int(year),'report_type':'Unsupported '+row['FilingType'],'filed_date':dt.datetime.strptime(row['FilingDate'],'%m/%d/%Y').date().isoformat() if row.get('FilingDate','').strip() else '','source_url':HOUSE+'/FinancialDisclosure/ViewSearch','status':'unsupported'}
                    catalog[meta['report_id']]=meta
            except Exception as exc:
                discovery_failed=True;errors.append(f'House index {year}: {exc}')
                catalog.update({r['report_id']:r for r in old.get('directory',[]) if r.get('index_year')==year})
    except Exception as exc:
        discovery_failed=True;errors.append('House discovery: '+str(exc));catalog={r['report_id']:r for r in old.get('directory',[])}
    history={k:{**r,'last_success':r.get('extracted_at',r.get('first_seen_at')) if r.get('source_sha256') else None} for k,r in previous.items()}
    target=cfg.get('priority_report_id')
    if target and target not in catalog:raise ValueError('Requested report ID not found in selected House years')
    selected=select_batch([r for r in catalog.values() if r.get('status')!='unsupported' and (not target or r['report_id']==target)],history,int(cfg.get('batch_size',30)),'report_id',cfg.get('refresh_hours',168),revalidate)
    for meta in selected:
        rid=meta['report_id'];prior=previous.get(rid)
        try:
            if prior and prior.get('shard'):
                from shards import safe_path
                prior=read_json(safe_path(cfg['_data_root'],prior['shard']),prior)
            record=process_document(client.get(meta['source_url']),meta,client,cfg)
            record['last_attempt']=now();record['extracted_at']=now()
            if prior:record['first_seen_at']=prior.get('first_seen_at',record['first_seen_at'])
            result[rid]=record
        except Exception as exc:
            errors.append(f'{rid}: {exc}')
            result[rid]={**(prior or meta),'last_attempt':now(),'stale':True,'status':'error','error':str(exc),'candidates':(prior or{}).get('candidates',[])}
    reports=list(result.values())
    # Explicit imports support Senate/state/local PDFs after their access process.
    for item in read_json(safe_local(cfg.get('imports_manifest','config/imports.json')),[]):
        try:
            meta={k:item[k]for k in ('report_id','person','jurisdiction','report_type','filed_date','source_url')}
            dt.date.fromisoformat(meta['filed_date'])
            if meta['report_id'] in catalog:raise ValueError('Import conflicts with House report ID')
            raw=safe_local(item['path']).read_bytes()
            prior=previous.get(meta['report_id']);digest=hashlib.sha256(raw).hexdigest()
            if prior and prior.get('source_sha256')==digest and not revalidate:record=prior
            else:record=process_document(raw,meta,client,cfg,item.get('force_ocr',False))
            reports=[r for r in reports if r['report_id']!=meta['report_id']]+[record]
        except Exception as exc:errors.append('Import: '+str(exc))
    for report in reports:
        for candidate in report.get('candidates',[]):candidate['excerpt']=public_excerpt(candidate['excerpt'])
    reviewed,review_errors=load_reviewed(safe_local(cfg.get('reviewed_file','config/reviewed-disclosures.csv')),reports)
    errors.extend(review_errors)
    directory=[{**r,'status':result.get(r['report_id'],{}).get('status',r.get('status','pending'))} for r in catalog.values()]
    return {'reports':reports,'records':reviewed,'errors':errors,'coverage':coverage,'directory':directory,
            'counts':{'discovered_reports':len(directory),'discovered_filer_names':len({(r['person'],r.get('office','')) for r in directory}),'extracted_reports':sum(bool(r.get('source_sha256')) for r in reports),'pending_reports':sum(r['status']=='pending' for r in directory),'unsupported_reports':sum(r['status']=='unsupported' for r in directory),'reviewed_records':len(reviewed),'attempted_this_run':len(selected)},
            'status':'partial' if errors else 'ok',
            'coverage_note':'All names in selected House index years (includes candidates/former members); names are not verified unique person IDs. Annual/PTR PDF processing continues in batches. Senate/state/local imports only. Reviewed excerpts are partial, not current portfolios.'}
