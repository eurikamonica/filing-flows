"""Market-wide public IPO/registration discovery, durable queue and analysis pages.
Discovery commits before document work. No issuer/ticker allowlist. Public records
only: confidential drafts cannot be discovered before SEC publishes them.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from . import ipo, sec

REGISTRATION = {'S-1','S-1/A','F-1','F-1/A','S-11','S-11/A'}
PROSPECTUS = {'424B1','424B3','424B4','424B5'}
DRAFT = {'DRS','DRS/A'}
LIFECYCLE = {'EFFECT','RW','RW/A'}
FORMS = REGISTRATION | PROSPECTUS | DRAFT | LIFECYCLE
FEEDS = ('S-1','F-1','S-11','424B1','424B3','424B4','424B5','DRS','EFFECT','RW')
PARSER_VERSION = 1
ACC = re.compile(r'\d{10}-\d{2}-\d{6}')


_last_request = 0.0


def get(url):
    """One bounded, rate-limited request; failures retry in the durable next run."""
    global _last_request
    if sec.FIXTURES:
        return sec.get(url)
    if not sec.UA or '@' not in sec.UA:
        raise ValueError('SEC_USER_AGENT with accurate project contact email is required')
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in ('www.sec.gov','data.sec.gov'):
        raise ValueError('SEC source URL required')
    time.sleep(max(0,0.5-(time.monotonic()-_last_request)))
    _last_request=time.monotonic()
    r=sec._session.get(url,headers={'User-Agent':sec.UA,'Accept-Encoding':'gzip, deflate'},timeout=(5,20))
    r.raise_for_status()
    return r.text


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def connect(root):
    Path(root).mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(Path(root)/'ipo.sqlite');db.row_factory=sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS filings (
      accession TEXT PRIMARY KEY, cik INTEGER NOT NULL, name TEXT NOT NULL,
      form TEXT NOT NULL, filed TEXT NOT NULL, accepted TEXT, index_url TEXT NOT NULL,
      source_url TEXT, file_number TEXT, discovered_at TEXT NOT NULL, discovery_source TEXT,
      state TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
      next_retry TEXT, last_attempt TEXT, last_success TEXT, error TEXT,
      classification TEXT NOT NULL DEFAULT 'unclassified', parser_version INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS filings_company ON filings(cik,filed);
    CREATE INDEX IF NOT EXISTS filings_queue ON filings(state,next_retry);
    CREATE TABLE IF NOT EXISTS sources (url TEXT PRIMARY KEY, kind TEXT, period TEXT,
      last_attempt TEXT, last_success TEXT, state TEXT, count INTEGER, error TEXT);
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    ''');return db


def setting(db,key,default=None):
    row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default


def setmeta(db,key,value):
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,json.dumps(value)));db.commit()


def index_url(cik,acc):
    return sec.filing_base(cik,acc)+'/'+acc+'-index.html'


def atom(text):
    root=ET.fromstring(text)
    if root.tag.split('}')[-1]!='feed': raise ValueError('Not an Atom feed')
    out=[]
    for entry in root.findall('{*}entry'):
        title=entry.findtext('{*}title',''); category=entry.find('{*}category')
        form=category.get('term','').strip() if category is not None else title.split(' - ')[0]
        cik=re.search(r'\((\d{1,10})\)',title)
        raw=ET.tostring(entry,encoding='unicode'); acc=ACC.search(raw)
        if form not in FORMS or not cik or not acc: continue
        name=re.sub(r'\s*\(\d{1,10}\).*','',title.partition(' - ')[2]).strip() or 'CIK '+cik[1]
        summary=BeautifulSoup(entry.findtext('{*}summary',''),'lxml').get_text(' ',strip=True)
        filed=re.search(r'Filed:\s*(\d{4}-\d{2}-\d{2})',summary)
        updated=entry.findtext('{*}updated','')
        out.append(dict(cik=int(cik[1]),name=name,form=form,accession=acc[0],filed=filed[1] if filed else updated[:10],
                        index_url=index_url(int(cik[1]),acc[0])))
    return out,len(root.findall('{*}entry'))


def master(text):
    if 'CIK|Company Name|Form Type|Date Filed|Filename' not in text:
        raise ValueError('Not a SEC master index')
    out=[]
    for line in text.splitlines():
        p=line.split('|')
        if len(p)!=5 or p[2] not in FORMS or not p[0].strip().isdigit(): continue
        acc=ACC.search(p[4])
        if not acc or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',p[3]):continue
        out.append(dict(cik=int(p[0]),name=p[1],form=p[2],filed=p[3],accession=acc[0],index_url=index_url(int(p[0]),acc[0])))
    return out


def remember(db,rows,source,now):
    before=db.total_changes
    for r in rows:
        if not ACC.fullmatch(r['accession']) or not r['filed']:continue
        db.execute('''INSERT OR IGNORE INTO filings(accession,cik,name,form,filed,index_url,discovered_at,discovery_source)
                      VALUES (:accession,:cik,:name,:form,:filed,:index_url,:discovered_at,:discovery_source)''',
                   dict(r,discovered_at=now,discovery_source=source))
    db.commit();return db.total_changes-before


def record_source(db,url,kind,period,state,count=0,error=None):
    now=utcnow();old=db.execute('SELECT last_success FROM sources WHERE url=?',(url,)).fetchone()
    db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?)',
               (url,kind,period,now,now if state=='ok' else old[0] if old else None,state,count,error))
    db.commit()


def fetch_index(db,url,kind,period,reader):
    try:
        parsed=reader(get(url));rows=parsed[0] if isinstance(parsed,tuple) else parsed
        remember(db,rows,url,utcnow());record_source(db,url,kind,period,'ok',len(rows))
        return parsed
    except (Exception,SystemExit) as e:
        record_source(db,url,kind,period,'failed',error=str(e)[:240]);return None


def quarters(start,end):
    y,q=start.year,(start.month-1)//3+1
    while (y,q)<=(end.year,(end.month-1)//3+1):
        yield y,q
        y,q=(y+1,1) if q==4 else (y,q+1)


def discover(db,backfill_from='2024-01-01',quarter_batch=2,feed_pages=3,deadline=None):
    now=utcnow();today=dt.datetime.now(ZoneInfo('America/New_York')).date()
    cutoff=dt.date.fromisoformat(backfill_from)
    if cutoff>today or cutoff.year<1994: raise ValueError('Backfill start must be between 1994 and today')
    prior=setting(db,'coverage_start')
    if prior and prior<backfill_from: cutoff=dt.date.fromisoformat(prior)
    setmeta(db,'coverage_start',cutoff.isoformat());setmeta(db,'discovery_attempt',now)
    started=time.monotonic()
    remaining=max(0,deadline-started) if deadline is not None else 240
    feed_deadline=started+remaining*0.5
    daily_deadline=started+remaining*0.75
    expired=lambda: deadline is not None and time.monotonic()>deadline
    feed_complete=True
    for form in FEEDS:
        if time.monotonic()>feed_deadline:feed_complete=False;break
        for page in range(feed_pages):
            url=sec.current_feed_url(form,start=page*100,count=100)
            got=fetch_index(db,url,'feed',form,atom)
            if got is None:feed_complete=False;break
            rows,total=got
            if total<100:break
            if page==feed_pages-1:
                feed_complete=False;record_source(db,url,'feed',form,'truncated',len(rows),'Page cap reached; quarterly/daily reconciliation required')
            if time.monotonic()>feed_deadline:feed_complete=False;break
    if feed_complete:setmeta(db,'feed_last_success',utcnow())
    setmeta(db,'feed_state','ok' if feed_complete else 'partial_or_failed')
    # Daily repair for recent filings: never treat a missing/nonpublished index as a successful scan.
    for n in range(1,8):
        if time.monotonic()>daily_deadline:break
        day=today-dt.timedelta(days=n)
        if day.weekday()>4:continue
        q=(day.month-1)//3+1
        url=f'https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{q}/master.{day:%Y%m%d}.idx'
        row=db.execute('SELECT state FROM sources WHERE url=?',(url,)).fetchone()
        if row and row[0]=='ok':continue
        fetch_index(db,url,'daily',day.isoformat(),master)
    # Market-wide historical catch-up, newest quarters first; completed historical quarters need no repeat download.
    attempted=0
    for y,q in reversed(list(quarters(cutoff,today))):
        if expired() or attempted>=quarter_batch:break
        period=f'{y}-Q{q}';url=f'https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{q}/master.idx'
        old=db.execute('SELECT state,last_success FROM sources WHERE url=?',(url,)).fetchone()
        current=(y,q)==(today.year,(today.month-1)//3+1)
        if old and old['state']=='ok' and (not current or (dt.datetime.fromisoformat(now)-dt.datetime.fromisoformat(old['last_success'])).total_seconds()<21600):continue
        fetch_index(db,url,'quarter',period,master);attempted+=1
    setmeta(db,'discovery_completed',utcnow())


def safe_document(url,cik,accession):
    p=urlparse(url)
    return p.scheme=='https' and p.netloc=='www.sec.gov' and p.path.startswith('/Archives/edgar/data/'+str(int(cik))+'/'+accession.replace('-','')+'/') and not p.query and not p.fragment


def resolve_document(row):
    html=get(row['index_url']);soup=BeautifulSoup(html,'lxml')
    primary=None
    for tr in soup.select('table.tableFile tr'):
        cells=tr.find_all('td')
        if len(cells)<4 or cells[3].get_text(strip=True)!=row['form']:continue
        a=cells[2].find('a',href=True)
        if not a:continue
        url=urljoin('https://www.sec.gov',a['href'])
        parsed=urlparse(url)
        if parsed.path in ('/ixviewer/doc/action','/ix','/ixviewer/ix.html'):
            doc=parse_qs(parsed.query).get('doc',[''])[0];url=urljoin('https://www.sec.gov',doc)
        if safe_document(url,row['cik'],row['accession']): primary=url;break
    if not primary:raise ValueError('Matching primary document not found on SEC index')
    text=soup.get_text(' ',strip=True)
    file_number=re.search(r'\b(?:333|001|000)-\d{3,9}\b',text)
    accepted=re.search(r'Accepted\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',text)
    stamp=dt.datetime.fromisoformat(accepted[1]).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(dt.timezone.utc).isoformat() if accepted else None
    return primary,file_number[0] if file_number else None,stamp


def narrative(html):
    soup=BeautifulSoup(html,'lxml')
    for tag in soup(['script','style']):tag.decompose()
    text=' '.join(soup.stripped_strings)
    intro=text[:35000]
    initial=bool(re.search(r'\b(?:this is (?:an?|the)|our|the proposed) initial public offering\b',intro,re.I))
    resale=bool(re.search(r'\b(?:resale|resell)\b',intro,re.I) and re.search(r'selling (?:stock|share)holders',intro,re.I))
    kind='ipo_language_identified' if initial else 'resale_language_identified' if resale else 'registration_unclassified'
    sections=[]
    for label in ('Prospectus Summary','Use of Proceeds','Risk Factors','Dilution','Principal Stockholders','Principal Shareholders','Dividend Policy'):
        # TOC entries are short. Prefer heading elements with substantive following prose.
        candidates=[]
        for el in soup.find_all(['h1','h2','h3','h4','p','div','b','strong','span']):
            if len(el.get_text(' ',strip=True))>100:continue
            if el.get_text(' ',strip=True).strip(' :').casefold()!=label.casefold():continue
            chunks=[]
            for nxt in el.next_elements:
                if isinstance(nxt,str):
                    s=str(nxt).strip()
                    if s:chunks.append(s)
                if sum(map(len,chunks))>1000:break
            excerpt=' '.join(chunks)
            if len(excerpt)>250 and not re.search(r'\.{4,}',excerpt) and not ('Table of Contents' in excerpt[:180]):candidates.append(excerpt)
        if candidates:
            # Prefer explanatory text over TOC navigation.
            chosen=max(candidates,key=lambda x:len(re.findall(r'\b(?:we|our|proceeds|risk|shares|offering)\b',x,re.I)))
            sections.append({'title':label,'excerpt':chosen[:900],'status':'source_excerpt_not_model_conclusion'})
    # Preserve table headers/units rather than guessing period mappings from untagged filings.
    tables=[]
    for i,t in enumerate(soup.find_all('table')):
        txt=t.get_text(' ',strip=True)
        if len(txt)<80 or len(txt)>60000:continue
        if not (re.search(r'\b(revenue|sales|net (?:income|loss)|cash flows|operating activities)\b',txt,re.I) and re.search(r'20\d{2}',txt)):continue
        rows=[]
        for tr in t.find_all('tr')[:55]:
            cells=[c.get_text(' ',strip=True)[:200] for c in tr.find_all(['td','th'],recursive=False)]
            if any(cells):rows.append(cells[:28])
        if len(rows)<3:continue
        tables.append({'table_index':i,'rows':rows,'status':'unmapped_source_table','note':'Original columns retained; periods and scale require review before modeling.'})
        if len(tables)==8:break
    return kind,sections,tables


def analyze(html,meta):
    kind,sections,tables=narrative(html)
    try:
        doc=ipo.parse(html,meta);state='parsed'
    except (ValueError,IndexError,KeyError,OverflowError) as exc:
        doc={**meta,'periods':[],'method':'source_tables_and_sections','document_sha256':hashlib.sha256(html.encode()).hexdigest(),
             'limitations':['Financial statement period/unit mapping requires review; no unsupported numerical chart is drawn.'], 'parse_error':str(exc)[:240]}
        state='needs_review'
    doc.update(classification=kind,sections=sections,source_tables=tables,analysis_state=state,parser_version=PARSER_VERSION)
    return doc


def process(db,root,batch=30,deadline=None,retry_review=False):
    now=utcnow()
    if retry_review:
        db.execute("UPDATE filings SET state='queued' WHERE state='needs_review'");db.commit()
    # Four newest jobs for every one oldest job keep both live monitoring and history progressing.
    query="""SELECT * FROM filings WHERE state='queued' OR (state='download_failed' AND (next_retry IS NULL OR next_retry<=?))
             OR (state='needs_review' AND parser_version<?)"""
    newest=db.execute(query+' ORDER BY filed DESC,accession DESC LIMIT ?',(now,PARSER_VERSION,batch)).fetchall()
    oldest=db.execute(query+' ORDER BY filed,accession LIMIT ?',(now,PARSER_VERSION,max(1,batch//5))).fetchall()
    jobs={r['accession']:r for r in [*oldest,*newest]}
    ordered=list(jobs.values())[:batch]
    for r in ordered:
        if deadline is not None and time.monotonic()>deadline:break
        row=dict(r);acc=row['accession'];attempt=row['attempts']+1;now=utcnow()
        db.execute('UPDATE filings SET attempts=?,last_attempt=? WHERE accession=?',(attempt,now,acc));db.commit()
        try:
            url,file_number,accepted=resolve_document(row)
            meta={k:row[k] for k in ('cik','name','form','filed','accession')}
            meta.update(source_url=url,file_number=file_number,accepted=accepted)
            html=get(url)
            doc=analyze(html,meta)
            if row['form'] in LIFECYCLE:
                doc.update(classification='lifecycle_document',analysis_state='document_only')
            ipo.write(Path(root)/'analyses'/f'{acc}.json',doc)
            db.execute('''UPDATE filings SET source_url=?,file_number=?,accepted=?,state=?,classification=?,last_success=?,error=?,next_retry=NULL,parser_version=? WHERE accession=?''',
                       (url,file_number,accepted,doc['analysis_state'],doc['classification'],utcnow(),doc.get('parse_error'),PARSER_VERSION,acc))
        except (Exception,SystemExit) as exc:
            retry=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=min(1440,5*2**min(attempt,8)))).isoformat(timespec='seconds')
            db.execute("UPDATE filings SET state='download_failed',error=?,next_retry=? WHERE accession=?",(str(exc)[:250],retry,acc))
        db.commit()


def seed(db,root):
    for path in ipo.SEEDS.glob('*.json'):
        doc=json.loads(path.read_text());r={k:doc[k] for k in ('cik','name','form','filed','accession')}
        r['index_url']=index_url(r['cik'],r['accession']);remember(db,[r],'bundled_verified_filing',utcnow())
        target=Path(root)/'analyses'/f"{r['accession']}.json"
        if not target.exists():
            doc.update(analysis_state='parsed',classification='ipo_language_identified',parser_version=PARSER_VERSION)
            ipo.write(target,doc)
            db.execute("UPDATE filings SET state='parsed',source_url=?,classification='ipo_language_identified',parser_version=? WHERE accession=?",(doc['source_url'],PARSER_VERSION,r['accession']))
    db.commit()


def public_row(r):
    keys=('accession','cik','name','form','filed','accepted','index_url','source_url','file_number','discovered_at','state','last_attempt','last_success','error','classification')
    return {k:r[k] for k in keys}


def publish(db,root,out):
    out=Path(out);now=utcnow();all_rows=db.execute('SELECT * FROM filings ORDER BY filed DESC,accession DESC').fetchall()
    by={}
    for r in all_rows:by.setdefault(r['cik'],[]).append(public_row(r))
    companies=[]
    for cik,rows in by.items():
        # EFFECT/RW only annotate the same SEC file number; unrelated offerings never change an IPO's state.
        registrations=[r for r in rows if r['form'] in REGISTRATION|PROSPECTUS|DRAFT]
        if not registrations:continue
        latest=registrations[0];chosen=None
        for r in rows:
            p=Path(root)/'analyses'/f"{r['accession']}.json"
            if p.exists():
                doc=json.loads(p.read_text());ipo.write(out/'filings'/f"{r['accession']}.json",{**doc,'filings':rows,'latest_discovered':latest,'generated_at':now})
                if chosen is None and r['form'] not in LIFECYCLE and doc.get('periods'):chosen=doc
        if chosen is None:
            p=Path(root)/'analyses'/f"{latest['accession']}.json"
            chosen=json.loads(p.read_text()) if p.exists() else {**latest,'periods':[],'method':'metadata_only','limitations':['Document analysis is queued.']}
        related=[r for r in rows if latest['file_number'] and r['file_number']==latest['file_number']]
        lifecycle=next((r['form'] for r in related if r['form'] in LIFECYCLE),None)
        d={**chosen,'filings':rows,'latest_discovered':latest,'lifecycle':lifecycle,'generated_at':now,
           'scan':{'state':latest['state'],'last_attempt':latest['last_attempt'],'last_success':latest['last_success']}}
        ipo.write(out/f'{cik}.json',d)
        companies.append({**latest,'filing_count':len(rows),'parsed_periods':len(chosen.get('periods',[])),
                          'analysis_accession':chosen['accession'],'lifecycle':lifecycle})
    sources=[dict(r) for r in db.execute('SELECT * FROM sources ORDER BY url')]
    start=setting(db,'coverage_start','2024-01-01');today=dt.datetime.now(ZoneInfo('America/New_York')).date()
    wanted={f'{y}-Q{q}' for y,q in quarters(dt.date.fromisoformat(start),today)}
    completed={r['period'] for r in sources if r['kind']=='quarter' and r['state']=='ok'}
    states={r['state']:r['n'] for r in db.execute('SELECT state,count(*) n FROM filings GROUP BY state')}
    status={'generated_at':now,'last_attempt':setting(db,'discovery_attempt'),'last_discovery_completed':setting(db,'discovery_completed'),
            'feed_last_success':setting(db,'feed_last_success'),'feed_state':setting(db,'feed_state','not_run'),
            'coverage_start':start,'quarters_total':len(wanted),'quarters_completed':len(wanted&completed),
            'backfill_pending':sorted(wanted-completed),'issuer_count':len(companies),'filing_count':len(all_rows),
            'states':states,'target_interval_seconds':300,'sources':sources,
            'scope':'US SEC public registration/prospectus market; registration forms are not all IPOs. Confidential drafts unavailable.'}
    generation=hashlib.sha256(json.dumps([(r['accession'],r['state'],r['last_success']) for r in all_rows]).encode()).hexdigest()[:20]
    status['generation']=generation
    index={'generated_at':now,'generation':generation,'companies':companies,'latest_filings':[public_row(r) for r in all_rows[:300]],'status':status,'scope':status['scope']}
    ipo.write(out/'index.json',index);ipo.write(out/'status.json',status)
    return status


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--out');ap.add_argument('--discover',action='store_true')
    ap.add_argument('--backfill-from',default='2024-01-01');ap.add_argument('--quarter-batch',type=int,default=2);ap.add_argument('--batch',type=int,default=30)
    ap.add_argument('--minutes',type=float,default=3);ap.add_argument('--retry-review',action='store_true')
    a=ap.parse_args();db=connect(a.root);seed(db,a.root);out=a.out or str(Path(a.root)/'public');deadline=time.monotonic()+a.minutes*60
    # Always publish discovered records even when later processing fails or reaches its time budget.
    try:
        if a.discover:discover(db,a.backfill_from,a.quarter_batch,deadline=time.monotonic()+a.minutes*60*.5)
        publish(db,a.root,out)
        if a.discover:process(db,a.root,a.batch,deadline,a.retry_review)
    finally:
        result=publish(db,a.root,out);db.close()
        print(json.dumps({k:result[k] for k in ('issuer_count','filing_count','quarters_completed','quarters_total','feed_state','states')}))


if __name__=='__main__':main()
