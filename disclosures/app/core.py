"""Public disclosure collection. Python 3.12+, standard library only."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

VERSION = '4.1.0'

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def number(v):
    if v is None or str(v).strip() in ('', 'NA', 'N/A', 'null', '--'):
        return None
    f = float(str(v).replace(',', ''))
    return f if math.isfinite(f) else None

def ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None

def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def read_json(path, default):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default

HOSTS = ('publicreporting.cftc.gov', 'api.fdic.gov', 'data.sec.gov', 'www.sec.gov', 'disclosures-clerk.house.gov',
         # officials' disclosures (state and Canada) and price sources, added in 4.1
         'ethics.ny.gov', 'public.ethics.ny.gov', 'form700search.fppc.ca.gov',
         'prciec-rpccie.parl.gc.ca', 'ciec-ccie.parl.gc.ca', 'www.ethicscanada.ca', 'ethicscanada.ca', 'www.ethiquecanada.ca',
         'www.sedi.ca', 'sedi.ca',
         'stooq.com', 'api.openfigi.com', 'query1.finance.yahoo.com', 'query2.finance.yahoo.com')

class BlockedError(RuntimeError):
    """The source answered with a bot-protection / challenge page instead of data."""

class Client:
    def __init__(self, root, options):
        self.root = Path(root)
        self.options = options
        self.last = 0
        self.manifest = []
        import http.cookiejar
        from urllib.request import build_opener, install_opener, HTTPCookieProcessor
        self.jar = http.cookiejar.CookieJar()          # session cookies some portals need between two requests
        install_opener(build_opener(HTTPCookieProcessor(self.jar)))
        self.hosts = tuple(HOSTS) + tuple(options.get('extra_hosts', []))

    def headers_for(self, host, sec):
        headers = {'User-Agent': (os.environ.get('SEC_USER_AGENT') or self.options.get('sec_user_agent') or 'DisclosureLab/1.1 public-data-reader'), 'Accept': '*/*'}
        if sec:
            ua = (os.environ.get('SEC_USER_AGENT') or self.options.get('sec_user_agent', '')).strip()
            if '@' not in ua or 'example.com' in ua:
                raise ValueError('Set SEC_USER_AGENT to project name + your real contact email')
            headers['User-Agent'] = ua
        if host == 'api.fdic.gov' and os.environ.get('FDIC_API_KEY'):
            headers['X-Api-Key'] = os.environ['FDIC_API_KEY']
        if host == 'publicreporting.cftc.gov' and os.environ.get('CFTC_APP_TOKEN'):
            headers['X-App-Token'] = os.environ['CFTC_APP_TOKEN']
        if host == 'api.openfigi.com' and os.environ.get('OPENFIGI_API_KEY'):
            headers['X-OPENFIGI-APIKEY'] = os.environ['OPENFIGI_API_KEY']
        if host in ('www.sedi.ca', 'sedi.ca', 'ethics.ny.gov', 'public.ethics.ny.gov', 'form700search.fppc.ca.gov', 'prciec-rpccie.parl.gc.ca', 'ciec-ccie.parl.gc.ca', 'www.ethicscanada.ca', 'ethicscanada.ca', 'stooq.com', 'query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
            # Portals built for browsers; the contact address stays in the UA string.
            headers['User-Agent'] = 'Mozilla/5.0 (compatible; FilingFlows disclosure reader; ' + headers['User-Agent'] + ')'
            headers['Accept'] = 'text/html,application/xhtml+xml,application/json;q=0.9,application/pdf;q=0.9,*/*;q=0.8'
            headers['Accept-Language'] = 'en-US,en;q=0.9,fr-CA;q=0.5'
        return headers

    def request(self, url, sec=False, data=None, headers=None, allow_block=False):
        """GET (or POST when data is given). Returns (bytes, final_url, content_type)."""
        host = urlparse(url).hostname
        if host not in self.hosts:
            raise ValueError('Unapproved data host')
        hdrs = self.headers_for(host, sec)
        hdrs.update(headers or {})
        last_error = 'Request failed'
        for attempt in range(self.options.get('retries', 3)):
            time.sleep(max(0, self.options.get('min_interval_seconds', .55) - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                with urlopen(Request(url, data=data, headers=hdrs, method='POST' if data is not None else 'GET'), timeout=self.options.get('timeout', 40)) as res:
                    final = res.url
                    if urlparse(final).hostname not in self.hosts:
                        if allow_block:
                            raise BlockedError('Redirected to a challenge/bot-protection page at ' + str(urlparse(final).hostname))
                        raise ValueError('Unexpected redirect host')
                    limit = self.options.get('max_response_mb', 80) * 1024 * 1024
                    body = res.read(limit + 1)
                    if len(body) > limit:
                        raise ValueError('Response exceeds configured size; not marked complete')
                    ctype = str(res.headers.get('content-type', '') or '')
                digest = hashlib.sha256(body).hexdigest()
                path = self.root / 'raw' / digest[:2] / (digest + '.bin')
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(body)
                self.manifest.append({'source_url': url, 'sha256': digest,
                                      'fetched_at': now(), 'path': str(path.relative_to(self.root)), 'bytes': len(body)})
                return body, final, ctype
            except BlockedError:
                raise
            except HTTPError as exc:
                last_error = f'HTTP {exc.code} from {host}'
                if exc.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(last_error) from None
                wait = exc.headers.get('Retry-After', '')
                time.sleep(min(30, int(wait) if wait.isdigit() else 2 ** (attempt + 1)))
            except (URLError, TimeoutError, OSError):
                last_error = f'Network/timeout error from {host}'
                time.sleep(2 ** attempt)
        raise RuntimeError(last_error)

    def get(self, url, sec=False, headers=None, allow_block=False):
        return self.request(url, sec=sec, headers=headers, allow_block=allow_block)[0]

    def json(self, url, sec=False):
        return json.loads(self.get(url, sec=sec))

    def post_json(self, url, payload, headers=None):
        body = self.request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*', 'X-Requested-With': 'XMLHttpRequest', **(headers or {})})[0]
        try:
            parsed = json.loads(body)
        except ValueError as exc:
            text = re.sub(r'\s+', ' ', body.decode('utf-8', 'replace'))[:240]
            raise ValueError(f'Non-JSON answer from {urlparse(url).hostname}: {exc} · body starts: {text!r}') from None
        if isinstance(parsed, str):   # some portals double-encode their JSON
            parsed = json.loads(parsed)
        return parsed

COT_FIELDS = {
    'disaggregated': {
        'Producer / Merchant': ('prod_merc_positions_long','prod_merc_positions_short'),
        'Swap dealers': ('swap_positions_long_all','swap__positions_short_all'),
        'Managed money': ('m_money_positions_long_all','m_money_positions_short_all'),
        'Other reportables': ('other_rept_positions_long','other_rept_positions_short'),
        'Nonreportables': ('nonrept_positions_long_all','nonrept_positions_short_all')},
    'tff': {
        'Dealer / Intermediary': ('dealer_positions_long_all','dealer_positions_short_all'),
        'Asset managers': ('asset_mgr_positions_long','asset_mgr_positions_short'),
        'Leveraged funds': ('lev_money_positions_long','lev_money_positions_short'),
        'Other reportables': ('other_rept_positions_long','other_rept_positions_short'),
        'Nonreportables': ('nonrept_positions_long_all','nonrept_positions_short_all')}
}

def normalize_cot(records, dataset, family):
    out = []
    for r in records:
        day = r['report_date_as_yyyy_mm_dd'][:10]
        for group, (lf, sf) in COT_FIELDS[family].items():
            if lf not in r or sf not in r:
                raise ValueError(f'COT schema missing fields {lf}/{sf}; check official schema')
            long, short = number(r[lf]), number(r[sf])
            out.append({'dataset': dataset, 'family': family, 'code': r['cftc_contract_market_code'],
                        'market': r['market_and_exchange_names'], 'date': day, 'group': group,
                        'long': long, 'short': short, 'net': long-short if long is not None and short is not None else None,
                        'open_interest': number(r.get('open_interest_all')),
                        'source_url': f'https://publicreporting.cftc.gov/d/{dataset}'})
    groups = {}
    for row in sorted(out, key=lambda x: x['date']):
        history = groups.setdefault((row['dataset'], row['code'], row['group']), [])
        previous = history[-1] if history else None
        delta = None
        if previous and row['net'] is not None and previous['net'] is not None:
            if (dt.date.fromisoformat(row['date']) - dt.date.fromisoformat(previous['date'])).days == 7:
                delta = row['net'] - previous['net']
        row['weekly_change'] = delta
        history.append(row)
        window = [x['net'] for x in history[-52:]]
        row['index_52_observations'] = (100 * (row['net'] - min(window)) / (max(window)-min(window))
            if len(window) == 52 and all(x is not None for x in window) and max(window) != min(window) else None)
    return out

def collect_cot(client, cfg, old, revalidate=False):
    all_rows = []
    for ds in cfg['datasets']:
        if ds['family'] not in COT_FIELDS or not re.fullmatch(r'[a-z0-9]{4}-[a-z0-9]{4}', ds['id']):
            raise ValueError('Invalid COT dataset')
        dt.date.fromisoformat(cfg['since'])
        codes = ds['codes']
        if not codes or not all(re.fullmatch(r'[A-Za-z0-9+]+', c) for c in codes):
            raise ValueError('Invalid CFTC contract codes')
        code_text = ','.join("'"+c+"'" for c in codes)
        records = []
        offset = 0
        while True:
            params = {'$where': f"report_date_as_yyyy_mm_dd >= '{cfg['since']}T00:00:00' AND cftc_contract_market_code in ({code_text})",
                      '$order': 'report_date_as_yyyy_mm_dd,cftc_contract_market_code', '$limit': 1000, '$offset': offset}
            page = client.json(f"https://publicreporting.cftc.gov/resource/{ds['id']}.json?"+urlencode(params))
            if not isinstance(page, list):
                raise ValueError('Unexpected COT response')
            records.extend(page)
            if len(page) < 1000:
                break
            offset += 1000
            if offset > 500000:
                raise ValueError('COT safety limit; narrow configuration')
        found = {r['cftc_contract_market_code'] for r in records}
        if set(codes) - found:
            raise ValueError('COT returned no rows for codes: '+ ','.join(sorted(set(codes)-found)))
        unique = {(r['cftc_contract_market_code'],r['report_date_as_yyyy_mm_dd']):r for r in records}
        all_rows.extend(normalize_cot(list(unique.values()), ds['id'], ds['family']))
    return {'rows': all_rows, 'coverage': 'Configured markets; futures only; full refresh of configured date range'}

def normalize_banks(records):
    out = []
    for r in records:
        rawday = str(r['REPDTE'])[:8]
        day = dt.datetime.strptime(rawday, '%Y%m%d').date()
        out.append({'cert': int(r['CERT']), 'name': r['NAME'], 'date': day.isoformat(),
                    'assets': number(r.get('ASSET')), 'deposits': number(r.get('DEP')),
                    'loans_net': number(r.get('LNLSNET')), 'equity': number(r.get('EQ')),
                    'net_income_ytd': number(r.get('NETINC')), 'roa': number(r.get('ROA')), 'roe': number(r.get('ROE')),
                    'source_url': f"https://banks.data.fdic.gov/bankfind-suite/bankfind/details/{int(r['CERT'])}"})
    by_key = {(r['cert'], r['date']): r for r in out}
    out = sorted(by_key.values(), key=lambda x:(x['cert'], x['date']))
    for row in out:
        date = dt.date.fromisoformat(row['date'])
        prev = date.replace(day=1, month=date.month-2) - dt.timedelta(days=1)
        prior = by_key.get((row['cert'],prev.isoformat())) if prev else None
        ytd = row['net_income_ytd']
        row['net_income_quarter'] = (ytd if date.month == 3 else ytd-prior['net_income_ytd']
            if ytd is not None and prior and prior['net_income_ytd'] is not None else None)
        row['loan_deposit_ratio'] = ratio(row['loans_net'], row['deposits'])
        row['equity_asset_ratio'] = ratio(row['equity'], row['assets'])
        row['assets_qoq'] = ratio(row['assets']-prior['assets'], prior['assets']) if prior and row['assets'] is not None and prior['assets'] is not None else None
    return out

def collect_banks(client, cfg, old, revalidate=False):
    dt.datetime.strptime(cfg['since'], '%Y%m%d')
    rows = []
    for cert in cfg['certs']:
        cert = int(cert)
        offset = 0
        bank_rows = []
        while True:
            params = {'filters': f"CERT:{cert} AND REPDTE:[{cfg['since']} TO *]",
                      'fields': 'CERT,NAME,REPDTE,ASSET,DEP,LNLSNET,EQ,NETINC,ROA,ROE',
                      'sort_by': 'REPDTE', 'sort_order': 'ASC', 'limit': 1000, 'offset': offset, 'format': 'json'}
            payload = client.json('https://api.fdic.gov/banks/financials?'+urlencode(params))
            page = payload['data']
            bank_rows.extend(x['data'] for x in page)
            if len(page) < 1000:
                break
            offset += 1000
            if offset > 500000:
                raise ValueError('FDIC safety limit')
        if not bank_rows:
            raise ValueError(f'No FDIC financials for CERT {cert}')
        rows.extend(bank_rows)
    return {'rows': normalize_banks(rows), 'unit': 'USD thousands',
            'coverage': 'FDIC BankFind selected Call Report-derived financials; bank entities, not listed holding companies'}

def localname(tag):
    return tag.split('}')[-1]

def parse_xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('DTD/entities are not allowed')
    return ET.fromstring(data)

def text_of(node, key, direct=False):
    if node is None:
        return ''
    for el in list(node) if direct else node.iter():
        if localname(el.tag) == key:
            return ''.join(el.itertext()).strip()
    return ''

def all_text(node, key):
    return [''.join(el.itertext()).strip() for el in node.iter() if localname(el.tag) == key]

def leaves(node):
    result = {}
    for el in node.iter():
        if not list(el):
            result.setdefault(localname(el.tag), []).append((el.text or '').strip())
    return result

def parse_npx(data, source_url):
    root = parse_xml(data)
    if localname(root.tag) != 'proxyVoteTable':
        return None
    rows = []
    for i, table in enumerate(el for el in root.iter() if localname(el.tag) == 'proxyTable'):
        rawdate = text_of(table, 'meetingDate', True)
        try:
            date = dt.datetime.strptime(rawdate, '%m/%d/%Y').date().isoformat()
        except ValueError:
            date = rawdate
        votes = []
        for v in (el for el in table.iter() if localname(el.tag) == 'voteRecord'):
            votes.append({'how': text_of(v,'howVoted'), 'shares': number(text_of(v,'sharesVoted')),
                          'management_alignment': text_of(v,'managementRecommendation')})
        rows.append({'id': hashlib.sha256((source_url+'#'+str(i)).encode()).hexdigest()[:24],
                     'issuer': text_of(table,'issuerName', True), 'cusip': text_of(table,'cusip', True),
                     'isin': text_of(table,'isin', True), 'meeting_date': date,
                     'description': text_of(table,'voteDescription', True),
                     'categories': all_text(table,'categoryType'),
                     'shares_voted': number(text_of(table,'sharesVoted', True)),
                     'shares_on_loan': number(text_of(table,'sharesOnLoan', True)), 'votes': votes,
                     'series_ids': all_text(table,'seriesId'), 'manager_numbers': all_text(table,'managerNumber'),
                     'other_info': text_of(table,'otherInfo'), 'raw_fields': leaves(table), 'source_url': source_url})
    return rows

def filing_rows(columns):
    count = len(columns.get('accessionNumber', []))
    return [{k:(v[i] if i < len(v) else '') for k,v in columns.items() if isinstance(v,list)} for i in range(count)]

def discover_npx(client, cik, since):
    data = client.json(f'https://data.sec.gov/submissions/CIK{cik}.json', sec=True)
    rows = filing_rows(data['filings']['recent'])
    for part in data['filings'].get('files', []):
        if part.get('filingTo','9999') < since:
            continue
        name = part['name']
        if not re.fullmatch(r'CIK\d+-submissions-\d+\.json', name):
            raise ValueError('Unexpected SEC history filename')
        rows.extend(filing_rows(client.json('https://data.sec.gov/submissions/'+name, sec=True)))
    rows = [r for r in rows if r.get('form') in ('N-PX','N-PX/A') and r.get('filingDate','') >= since]
    unique = {r['accessionNumber']:r for r in rows}
    return data.get('name',cik), sorted(unique.values(), key=lambda r:(r['filingDate'],r['accessionNumber']), reverse=True)

def download_npx(client, cik, name, f):
    acc = f['accessionNumber']
    if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', acc):
        raise ValueError('Unexpected accession number')
    base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/'
    index = client.json(base+'index.json', sec=True)
    result = {'accession': acc, 'cik': cik, 'filer': name, 'form': f['form'],
              'filing_date': f['filingDate'], 'accepted_at': f.get('acceptanceDateTime',''),
              'report_date': f.get('reportDate',''), 'is_amendment': f['form'].endswith('/A'),
              'source_url': base+acc+'-index.htm', 'first_seen_at': now(), 'fetched_at': now(),
              'votes': [], 'documents': [], 'cover_fields': {}}
    recognized = 0
    for item in index['directory']['item']:
        filename = item['name']
        if not filename.lower().endswith('.xml') or filename.startswith('/') or '..' in filename or '/' in filename:
            continue
        url = base+quote(filename)
        raw = client.get(url, sec=True)
        parsed = parse_npx(raw, url)
        result['documents'].append({'url':url, 'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)})
        if parsed is not None:
            recognized += 1
            result['votes'].extend(parsed)
        else:
            root = parse_xml(raw)
            if localname(root.tag) == 'edgarSubmission':
                # Publish only useful report metadata, not contact details.
                for tag in ('reportType','registrantType','periodOfReport','amendmentType','amendmentNo','confidentialTreatment','explanatoryNotes'):
                    result['cover_fields'][tag] = text_of(root,tag)
    result['parse_status'] = 'parsed' if recognized else 'no_structured_vote_table'
    result['coverage_note'] = ('Structured XML table(s) parsed; confidential/omitted records may exist' if recognized else
                               'No supported XML vote table. Could be notice/no-vote/legacy HTML; inspect original. Not zero holdings.')
    return result

def collect_npx(client, cfg, old, revalidate=False):
    dt.date.fromisoformat(cfg['since'])
    previous = {f['accession']:f for f in old.get('filings', [])}
    result, errors, coverage = [], [], []
    cap = int(cfg.get('max_filings_per_cik',30))
    if cap < 1:
        raise ValueError('max_filings_per_cik must be positive')
    for value in cfg['ciks']:
        cik = str(value).zfill(10)
        if not re.fullmatch(r'\d{10}', cik):
            raise ValueError('CIK must be numeric, <=10 digits')
        try:
            name, found = discover_npx(client,cik,cfg['since'])
        except Exception as exc:
            result.extend(f for f in previous.values() if f['cik'] == cik)
            errors.append(f'CIK {cik}: {exc}')
            continue
        coverage.append({'cik':cik, 'discovered':len(found), 'selected':min(cap,len(found)), 'truncated':len(found)>cap})
        for filing in found[:cap]:
            acc = filing['accessionNumber']
            cached = previous.get(acc)
            if cached and cached.get('parse_status') == 'parsed' and not revalidate:
                result.append(cached)
                continue
            try:
                record = download_npx(client,cik,name,filing)
                if cached:
                    record['first_seen_at'] = cached.get('first_seen_at', record['first_seen_at'])
                result.append(record)
            except Exception as exc:
                errors.append(f'{acc}: {exc}')
                if cached:
                    record = dict(cached)
                    record['refresh_error'] = str(exc)
                    result.append(record)
                else:
                    result.append({'accession':acc,'cik':cik,'filer':name,'form':filing['form'],
                                   'filing_date':filing['filingDate'],'report_date':filing.get('reportDate',''),
                                   'is_amendment':filing['form'].endswith('/A'),'parse_status':'failed',
                                   'coverage_note':str(exc),'votes':[],
                                   'source_url':f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/{acc}-index.htm'})
    return {'filings': result, 'coverage': coverage, 'errors': errors,
            'status': 'partial' if errors or any(x['truncated'] for x in coverage) else 'ok'}

def refresh_module(old, runner, client, cfg, revalidate=False):
    attempted = now()
    try:
        fresh = runner(client,cfg,old,revalidate)
        status = fresh.pop('status','ok')
        return {**fresh, 'status':status,'last_attempt':attempted,'updated_at':now(), 'error':None}
    except Exception as exc:
        return {**old, 'status':'error','last_attempt':attempted,'error':str(exc),
                'updated_at':old.get('updated_at')}

def publish(path, data):
    path = Path(path)
    write_json(path/'live.json',data)
    # External JS data allows offline double-click without browser file:// fetch restrictions.
    payload = json.dumps(data,ensure_ascii=False,allow_nan=False).replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    tmp = path/'live.js.tmp'
    tmp.write_text('window.DISCLOSURE_LIVE = '+payload+';\n',encoding='utf-8')
    tmp.replace(path/'live.js')
