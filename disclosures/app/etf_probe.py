"""TEMPORARY probe (removed before merge): samples of every source the ETF tool reads, pushed to a scratch branch."""
import csv, io, json, os, re, sys, time, zipfile, urllib.request, urllib.parse, http.cookiejar
from pathlib import Path
OUT = Path('probe'); OUT.mkdir(exist_ok=True)
SEC_UA = os.environ.get('SEC_USER_AGENT') or 'Filing Flows research filingflows@gmail.com'
BROWSER = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
LOG = open(OUT / 'log.txt', 'w')
def log(*a):
    s = ' '.join(str(x) for x in a); print(s, flush=True); LOG.write(s + '\n'); LOG.flush()
def get(url, ua=None, to=120, dest=None):
    ua = ua or (SEC_UA if 'sec.gov' in url else BROWSER)
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': '*/*', 'Accept-Encoding': 'identity'})
    t0 = time.time()
    try:
        with op.open(req, timeout=to) as r:
            if dest:
                with open(dest, 'wb') as f:
                    n = 0
                    while True:
                        b = r.read(1 << 20)
                        if not b: break
                        f.write(b); n += len(b)
                log('ok', n, f'{time.time()-t0:.0f}s', url); return dest
            b = r.read(); log('ok', len(b), url); return b
    except Exception as e:
        log('FAIL', type(e).__name__, str(e)[:200], url); return None
    finally:
        time.sleep(0.25)
def save(name, b):
    if b is not None: (OUT / name).write_bytes(b if isinstance(b, bytes) else b.encode())

SAMPLE = ['IVV', 'VOO', 'XLK', 'ARKK', 'AGG', 'TQQQ', 'SCHD', 'SPY', 'QQQ', 'GLD', 'IBIT', 'JEPI', 'VTI', 'BND']
# 1. listings
for u, n in [('https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt', 'nasdaqtraded.txt'),
             ('https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt', 'otherlisted.txt'),
             ('https://www.sec.gov/files/company_tickers_mf.json', 'company_tickers_mf.json'),
             ('https://www.sec.gov/files/company_tickers_exchange.json', 'company_tickers_exchange.json')]:
    save(n, get(u))
mf = json.loads((OUT / 'company_tickers_mf.json').read_text()) if (OUT / 'company_tickers_mf.json').exists() else {'data': []}
F = mf.get('fields'); rows = [dict(zip(F, r)) for r in mf.get('data', [])]
samp = {r['symbol']: r for r in rows if r['symbol'] in SAMPLE}
log('mf rows', len(rows), json.dumps(samp))
series = {r['seriesId'] for r in samp.values()}
ciks = {str(r['cik']) for r in samp.values()}
# 2. dataset listing pages → zip links
pages = {'nport': ['https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets', 'https://www.sec.gov/dera/data/form-n-port-data-sets'],
         'ncen': ['https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets', 'https://www.sec.gov/dera/data/form-n-cen-data-sets'],
         'rr': ['https://www.sec.gov/data-research/sec-markets-data/mutual-fund-prospectus-riskreturn-summary-data-sets',
                'https://www.sec.gov/dera/data/mutual-fund-prospectus-risk-return-summary-data-sets'],
         'series': ['https://www.sec.gov/data-research/sec-markets-data/investment-company-series-class-information',
                    'https://www.sec.gov/open/datasets-investment_company.html', 'https://www.sec.gov/about/opendatasetsshtmlinvestment_company']}
links = {}
for k, us in pages.items():
    for u in us:
        b = get(u)
        if b:
            save(f'page_{k}.html', b)
            ls = sorted(set(re.findall(r'href="([^"]+\.(?:zip|csv|xml|xlsx))"', b.decode('utf-8', 'replace'), re.I)))
            links[k] = [urllib.parse.urljoin(u, l) for l in ls]
            log(k, len(ls), ls[:6], ls[-6:])
            break
json.dump(links, open(OUT / 'links.json', 'w'), indent=1)

def latest(ls, pat):
    c = [l for l in ls if re.search(pat, l, re.I)]
    return sorted(c)[-1] if c else None

def zip_sample(name, url, key_filter):
    if not url: log('no url for', name); return
    p = Path('/tmp') / (name + '.zip')
    if not get(url, to=1800, dest=p): return
    z = zipfile.ZipFile(p)
    info = []
    for zi in z.infolist():
        info.append([zi.filename, zi.file_size, zi.compress_size])
    log(name, 'members', json.dumps(info))
    d = OUT / name; d.mkdir(exist_ok=True)
    for zi in z.infolist():
        if zi.is_dir(): continue
        with z.open(zi) as f:
            t = io.TextIOWrapper(f, encoding='utf-8', errors='replace', newline='')
            head = t.readline(); sep = '\t' if '\t' in head else ','
            cols = head.rstrip('\r\n').split(sep)
            first, keep, n = [], [], 0
            for line in t:
                n += 1
                if n <= 25: first.append(line)
                if key_filter(cols, line, sep) and len(keep) < 4000: keep.append(line)
            (d / (Path(zi.filename).name + '.head')).write_text(head + ''.join(first))
            (d / (Path(zi.filename).name + '.sample')).write_text(head + ''.join(keep))
            log(name, zi.filename, 'rows', n, 'kept', len(keep), 'cols', cols)

def by_keys(keys):
    keys = set(keys)
    def f(cols, line, sep):
        return any(k in line for k in keys)
    return f

# 3. N-CEN (smaller, first), RR, series-class, then N-PORT (big)
zip_sample('ncen', latest(links.get('ncen', []), r'ncen.*\.zip$|\.zip$'), by_keys(series | ciks))
zip_sample('rr', latest(links.get('rr', []), r'\.zip$'), by_keys(series | ciks))
sc = latest(links.get('series', []), r'\.csv$') or latest(links.get('series', []), r'\.(xml|xlsx)$')
if sc: save('series_class' + Path(sc).suffix, get(sc))
# N-PORT: keep the accessions of the sample series
acc = set()
def nport_filter(cols, line, sep):
    if 'SERIES_ID' in cols:
        parts = line.split(sep)
        i = cols.index('SERIES_ID')
        if i < len(parts) and parts[i] in series:
            acc.add(parts[0]); return True
        return False
    return bool(acc) and line.split(sep, 1)[0] in acc
zip_sample('nport', latest(links.get('nport', []), r'\.zip$'), nport_filter)
# 4. EDGAR filings of the sample registrants: forms and one of each document
for cik in sorted(ciks)[:6]:
    b = get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json')
    if not b: continue
    s = json.loads(b); r = s['filings']['recent']
    forms = {}
    for i, fm in enumerate(r['form']):
        forms.setdefault(fm, []).append((r['accessionNumber'][i], r['filingDate'][i], r['primaryDocument'][i]))
    log('cik', cik, s.get('name'), {k: len(v) for k, v in forms.items()})
    for fm in ('497K', 'N-CSR', 'N-CEN', 'NPORT-P', '485BPOS', '10-K', 'S-1', '424B3'):
        if fm in forms:
            a, d, doc = forms[fm][0]
            base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a.replace("-", "")}'
            idx = get(base + '/index.json')
            if idx: save(f'idx_{cik}_{fm}.json', idx)
            if doc and fm in ('497K', 'N-CEN', 'NPORT-P', 'N-CSR'):
                b2 = get(f'{base}/{doc}')
                if b2: save(f'doc_{cik}_{fm}_{doc.replace("/", "_")[:60]}', b2[:3_000_000])
# 5. Yahoo: crumb + fund modules + chart
get('https://fc.yahoo.com'); crumb = get('https://query2.finance.yahoo.com/v1/test/getcrumb')
crumb = crumb.decode().strip() if crumb else ''
for t in ('SPY', 'GLD', 'ARKK', 'AGG', 'IBIT'):
    save(f'yahoo_{t}.json', get(f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{t}?modules=price,summaryDetail,defaultKeyStatistics,fundProfile,topHoldings,fundPerformance,assetProfile&crumb={urllib.parse.quote(crumb)}'))
save('yahoo_chart_SPY.json', get('https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=5y&interval=1wk&events=div'))
# 6. iShares / Vanguard / SSGA issuer files (holdings with weights)
save('ishares_IVV.csv', get('https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund'))
save('ssga_spy.xlsx', get('https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx'))
log('done')
