import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from pipeline import ipo_market as M

ACC='0001234567-26-000001'
ACC2='0001234567-26-000002'

def row(acc=ACC,form='S-1',filed='2026-10-01'):
    return dict(accession=acc,cik=1234567,name='Example <Inc>',form=form,filed=filed,index_url=M.index_url(1234567,acc))

def index(form='S-1',file_number='333-123456'):
    return f'''<div>Accepted</div><div>2026-10-01 09:00:00</div><div>File No. {file_number}</div><table class="tableFile"><tr><td>1</td><td>registration</td><td><a href="/Archives/edgar/data/1234567/{ACC.replace('-','')}/filing.htm">filing.htm</a></td><td>{form}</td></tr></table>'''

MASTER=f'''Description: Master Index\nCIK|Company Name|Form Type|Date Filed|Filename\n1234567|Example Inc|S-1|2026-10-01|edgar/data/1234567/{ACC}.txt\n9876543|Another|F-1/A|2026-10-02|edgar/data/9876543/0001234567-26-000003.txt\n1234567|Example Inc|10-K|2026-10-01|edgar/data/1234567/{ACC2}.txt'''
ATOM=f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>S-1 - Example Inc (0001234567) (Filer)</title><category term="S-1"/><id>urn:tag:sec.gov:accession-number={ACC}</id><updated>2026-10-01T09:00:00-04:00</updated><summary>&lt;b&gt;Filed:&lt;/b&gt; 2026-10-01</summary></entry></feed>'''

def test_market_not_issuer_allowlist_and_dedup(tmp_path):
    db=M.connect(tmp_path);rows=M.master(MASTER)
    assert len(rows)==2 and rows[1]['cik']==9876543
    assert M.remember(db,rows,'quarter',M.utcnow())==2
    assert M.remember(db,rows,'daily',M.utcnow())==0
    entries,total=M.atom(ATOM);assert total==1 and entries[0]['filed']=='2026-10-01'
    assert entries[0]['name']=='Example Inc'
    assert M.remember(db,entries,'feed',M.utcnow())==0
    assert len(db.execute('SELECT * FROM filings').fetchall())==2
    with pytest.raises(ValueError):M.master('<html>Access denied</html>')
    with pytest.raises(ValueError):M.atom('<html>Access denied</html>')


def test_resolve_primary_not_exhibit_and_file_number():
    with patch.object(M,'get',return_value=index()):
        u,n,a=M.resolve_document(row())
    assert u.endswith('/filing.htm') and n=='333-123456'
    assert a=='2026-10-01T13:00:00+00:00'
    assert not M.safe_document('https://evil.com/filing.htm',1234567,ACC)
    assert not M.safe_document(u.replace('/1234567/','/1234568/'),1234567,ACC)
    with patch.object(M,'get',return_value=index('EX-99')):
        with pytest.raises(ValueError):M.resolve_document(row())


def test_daily_index_header_and_compact_dates(tmp_path):
    daily=MASTER.replace('Filename','File Name').replace('2026-10-01','20261001').replace('2026-10-02','20261002')
    rows=M.master(daily)
    assert rows==M.master(MASTER)
    db=M.connect(tmp_path)
    assert M.remember(db,rows,'daily',M.utcnow())==2
    assert M.remember(db,M.master(MASTER),'quarter',M.utcnow())==0
    assert M.master(daily.replace('20261001','20260230'))==rows[1:]


def test_download_failure_persists_discovery_and_retry(tmp_path):
    db=M.connect(tmp_path);M.remember(db,[row()],'feed',M.utcnow())
    with patch.object(M,'get',side_effect=RuntimeError('SEC unavailable')):M.process(db,tmp_path,1)
    r=dict(db.execute('SELECT * FROM filings').fetchone())
    assert r['state']=='download_failed' and r['attempts']==1 and r['next_retry']
    s=M.publish(db,tmp_path,tmp_path/'public')
    d=json.loads((tmp_path/'public/1234567.json').read_text())
    assert d['periods']==[] and d['latest_discovered']['accession']==ACC
    assert s['states']['download_failed']==1
    with patch.object(M,'get',side_effect=AssertionError('not due')):M.process(db,tmp_path,1)
    assert db.execute('SELECT attempts FROM filings').fetchone()[0]==1


def test_no_tags_still_has_analysis_page(tmp_path):
    db=M.connect(tmp_path);M.remember(db,[row()],'feed',M.utcnow())
    text='''<h1>This is our company</h1><p>This is an initial public offering of our common stock.</p><h2>Use of Proceeds</h2><p>We intend to use the proceeds for working capital and general corporate purposes. '''+('Our business requires capital and the offering is subject to risk. '*12)+'''</p><table><tr><td>Revenue in USD millions</td><td>2025</td><td>2024</td></tr><tr><td>Revenue</td><td>100</td><td>80</td></tr><tr><td>Net loss</td><td>(10)</td><td>(20)</td></tr><tr><td>Operating activities and other statement lines subject to verification</td><td>5</td><td>6</td></tr></table>'''
    with patch.object(M,'get',side_effect=[index(),text]):M.process(db,tmp_path,1)
    M.publish(db,tmp_path,tmp_path/'public');d=json.loads((tmp_path/'public/1234567.json').read_text())
    assert d['classification']=='ipo_language_identified'
    assert d['periods']==[] and d['analysis_state']=='needs_review'
    assert d['sections'] and d['source_tables']
    assert (tmp_path/'public/filings'/f'{ACC}.json').exists()


def test_new_unparsed_filing_does_not_erase_old_financials(tmp_path):
    db=M.connect(tmp_path);M.remember(db,[row(),row(ACC2,'S-1/A','2026-10-20')],'feed',M.utcnow())
    d={**row(),'source_url':M.sec.filing_base(1234567,ACC)+'/x.htm','periods':[{'label':'FY 2025','values':{'revenue':100}}]}
    M.ipo.write(tmp_path/'analyses'/f'{ACC}.json',d)
    db.execute("UPDATE filings SET state='parsed' WHERE accession=?",(ACC,));db.commit()
    M.publish(db,tmp_path,tmp_path/'public');d=json.loads((tmp_path/'public/1234567.json').read_text())
    assert d['accession']==ACC and d['latest_discovered']['accession']==ACC2
    assert len(d['filings'])==2 and d['periods']


def test_lifecycle_requires_same_sec_file_number(tmp_path):
    db=M.connect(tmp_path);M.remember(db,[row(),row(ACC2,'EFFECT','2026-10-20')],'feed',M.utcnow())
    db.execute("UPDATE filings SET file_number='333-111111' WHERE accession=?",(ACC,))
    db.execute("UPDATE filings SET file_number='333-222222' WHERE accession=?",(ACC2,));db.commit()
    M.publish(db,tmp_path,tmp_path/'public')
    assert json.loads((tmp_path/'public/1234567.json').read_text())['lifecycle'] is None
    db.execute("UPDATE filings SET file_number='333-111111' WHERE accession=?",(ACC2,));db.commit()
    M.publish(db,tmp_path,tmp_path/'public')
    assert json.loads((tmp_path/'public/1234567.json').read_text())['lifecycle']=='EFFECT'


def test_source_failure_not_success(tmp_path):
    db=M.connect(tmp_path)
    with patch.object(M,'get',return_value='403 denied'):assert M.fetch_index(db,'u','quarter','2026-Q4',M.master) is None
    r=dict(db.execute('SELECT * FROM sources').fetchone());assert r['state']=='failed' and r['last_success'] is None
    with patch.object(M,'get',return_value=MASTER):assert len(M.fetch_index(db,'u','quarter','2026-Q4',M.master))==2
    r=dict(db.execute('SELECT * FROM sources').fetchone());assert r['state']=='ok' and r['last_success']


def test_discovery_backfill_and_resume(tmp_path):
    db=M.connect(tmp_path)
    def response(url):return ATOM if 'getcurrent' in url else MASTER
    with patch.object(M,'get',side_effect=response):M.discover(db,'2024-01-01',quarter_batch=2)
    assert len(db.execute("SELECT * FROM sources WHERE kind='quarter' AND state='ok'").fetchall())==2
    with patch.object(M,'get',side_effect=response):M.discover(db,'2024-01-01',quarter_batch=2)
    assert len(db.execute("SELECT * FROM sources WHERE kind='quarter' AND state='ok'").fetchall())==4
    assert M.setting(db,'feed_state')=='ok'
    with pytest.raises(ValueError):M.discover(db,'1900-01-01')


def test_resale_language_is_not_initial_offering():
    kind,_,_=M.narrative('<p>This prospectus relates to the resale of shares by selling stockholders. This is not an initial public offering.</p>')
    assert kind=='resale_language_identified'


def test_generic_prospectus_form_supported():
    html='''<xbrli:context id="c"><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit><ix:nonFraction name="us-gaap:Revenues" contextRef="c" unitRef="u" scale="6">100</ix:nonFraction>'''
    d=M.analyze(html,row(form='S-11'))
    assert d['analysis_state']=='parsed' and d['periods'][0]['values']['revenue']==100e6


PROSPECTUS='''<p>This is our initial public offering. We intend to list our common stock on the Nasdaq Global Market under the
symbol “EXMP.”</p><p><a href="#s">Prospectus Summary</a> <a href="#r">Risk Factors</a> <a href="#u">Use of Proceeds</a>
<a href="#m">Management’s Discussion and Analysis of Financial Condition and Results of Operations</a></p>
<p id="s"><b>PROSPECTUS SUMMARY</b></p><p>'''+('We make example products for customers around the world. '*8)+'''</p>
<p id="r"><b>RISK FACTORS</b></p><p><b>Risks Related to Our Business</b></p><p><b><i>We have a history of losses and may not
achieve or maintain profitability in the future.</i></b></p><p>'''+('Our losses could continue for the foreseeable future. '*8)+'''</p>
<p id="u"><b>USE OF PROCEEDS</b></p><p>'''+('We intend to use the net proceeds for working capital and general corporate purposes. '*5)+'''</p>
<p id="m"><b>MANAGEMENT’S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS</b></p><p>'''+('We discuss our results below. '*10)+'</p>'


def test_prospectus_reading_written_and_published(tmp_path):
    db=M.connect(tmp_path);M.remember(db,[row()],'feed',M.utcnow())
    with patch.object(M,'get',side_effect=[index(),PROSPECTUS]):M.process(db,tmp_path,1)
    rd=json.loads(M.reader_path(tmp_path,ACC).read_text())
    assert rd['accession']==ACC and rd['cover']['symbol']=='EXMP'
    assert [s['title'] for s in rd['sections']][:2]==['Prospectus Summary','Risk Factors']
    M.publish(db,tmp_path,tmp_path/'public')
    d=json.loads((tmp_path/'public/1234567.json').read_text())
    assert d['reader']['path']==f'reader/{ACC}.json' and d['reader']['cover']['symbol']=='EXMP' and d['reader']['risks']==1
    assert json.loads((tmp_path/'public/reader'/f'{ACC}.json').read_text())['sections']
    i=json.loads((tmp_path/'public/index.json').read_text())
    assert i['companies'][0]['symbol']=='EXMP'


def test_older_prospectuses_are_read_a_few_per_run(tmp_path):
    db=M.connect(tmp_path);M.remember(db,[row(),row(ACC2,'S-1/A','2026-10-20')],'feed',M.utcnow())
    db.execute("UPDATE filings SET classification='ipo_language_identified',state='needs_review',source_url=?",
               (M.sec.filing_base(1234567,ACC)+'/x.htm',));db.commit()
    with patch.object(M,'get',return_value=PROSPECTUS) as g:
        assert M.refresh_readers(db,tmp_path,limit=1)==1
    assert g.call_count==1 and M.reader_path(tmp_path,ACC2).exists() and not M.reader_path(tmp_path,ACC).exists()
    with patch.object(M,'get',side_effect=RuntimeError('SEC unavailable')):
        M.refresh_readers(db,tmp_path,limit=3)                     # a failed download is retried next run
    assert not M.reader_path(tmp_path,ACC).exists()
    with patch.object(M,'get',return_value=PROSPECTUS):M.refresh_readers(db,tmp_path,limit=3)
    with patch.object(M,'get',side_effect=AssertionError('already read')):
        assert M.refresh_readers(db,tmp_path,limit=3)==0


def test_parsed_periods_get_standard_sankeys(tmp_path):
    db=M.connect(tmp_path);M.seed(db,tmp_path);M.publish(db,tmp_path,tmp_path/'public')
    d=json.loads((tmp_path/'public/2130357.json').read_text())
    c=d['charts']
    assert c['default']=='2026-01-01_2026-06-30' and len(c['periods'])==5
    h1=c['periods'][0]
    assert h1['label']=='H1 2026' and h1['vs']=='H1 2025' and h1['nodes'] and h1['analysis']
    row0=next(r for r in json.loads((tmp_path/'public/index.json').read_text())['companies'] if r['cik']==2130357)
    assert row0['headline']['label']=='H1 2026' and row0['headline']['rev_fmt']=='$16.3B'
