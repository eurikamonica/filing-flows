"""TEMPORARY (removed before merge): fetch real samples of every source the debt module will parse, so the parsers are
written against real documents. Output: <out>/<TICKER>/... plus rates/ and fdic/."""
import gzip, json, re, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import Client, read_json  # noqa: E402

TICKERS = {'AAPL': 320193, 'F': 37996, 'T': 732717, 'ORCL': 1341439, 'MSTR': 1050446, 'CCL': 815097, 'BA': 12927,
           'JPM': 19617, 'CVNA': 1690820, 'PCG': 1004980, 'TSLA': 1318605, 'AAL': 6201}
FRED = ['SOFR', 'DGS1MO', 'DGS3MO', 'DGS6MO', 'DGS1', 'DGS2', 'DGS5', 'DGS7', 'DGS10', 'DGS30', 'DCPN30', 'DCPF30',
        'RIFSPPNA2P2D30NB', 'DAAA', 'DBAA', 'DPRIME', 'BAMLC0A0CM', 'BAMLH0A0HYM2', 'BAMLC0A4CBBB', 'BAMLH0A1HYBB',
        'BAMLH0A2HYB', 'BAMLH0A3HYC', 'BAMLC0A1CAAA', 'BAMLC0A2CAA', 'BAMLC0A3CA', 'MORTGAGE30US', 'TERMCBAUTO48NS',
        'IR3TCD01USM156N', 'RIFSPPFAAD30NB']


def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    cfg = read_json(Path(__file__).resolve().parents[1] / 'config' / 'settings.json', {})
    http = cfg.get('http', {})
    c = Client(tempfile.mkdtemp(), {**http, 'extra_hosts': ['efts.sec.gov', 'fred.stlouisfed.org', 'banks.data.fdic.gov', 'www.fdic.gov'],
                                    'host_intervals': {'data.sec.gov': 0.15, 'www.sec.gov': 0.15, 'efts.sec.gov': 0.3}, 'timeout': 60})
    log = []

    def save(p, body):
        p = out / p; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body if isinstance(body, bytes) else body.encode('utf-8'))

    def get(url, sec=True, limit=None):
        try:
            b = c.get(url, sec=sec)
            log.append(f'ok {len(b)} {url}')
            return b[:limit] if limit else b
        except Exception as exc:
            log.append(f'FAIL {type(exc).__name__} {exc} {url}')
            return None

    for t, cik in TICKERS.items():
        c10 = f'{cik:010d}'
        sub = get(f'https://data.sec.gov/submissions/CIK{c10}.json')
        if sub:
            save(f'{t}/submissions.json', sub)
        cf = get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{c10}.json')
        if cf:
            save(f'{t}/companyfacts.json.gz', gzip.compress(cf))
        if not sub:
            continue
        r = json.loads(sub)['filings']['recent']
        rows = list(zip(r['form'], r['accessionNumber'], r['primaryDocument'], r['filingDate'], r.get('items', [''] * len(r['form'])),
                        r.get('primaryDocDescription', [''] * len(r['form']))))
        tenk = next((x for x in rows if x[0] == '10-K'), None)
        if tenk:
            acc = tenk[1].replace('-', '')
            idx = get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json')
            if idx:
                save(f'{t}/10k_index.json', idx)
                names = [i['name'] for i in json.loads(idx)['directory']['item']]
                inst = [n for n in names if n.endswith('_htm.xml')] or [n for n in names if n.endswith('.xml') and not re.search(r'_(cal|def|lab|pre)\.xml$|FilingSummary', n)]
                for n in inst[:1] + [n for n in names if n.endswith('_lab.xml')][:1]:
                    b = get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{n}')
                    if b:
                        save(f'{t}/10k/{n}', b)
        for form, cap in (('FWP', 4), ('424B2', 2), ('424B5', 2)):
            for x in [x for x in rows if x[0] == form][:cap]:
                b = get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{x[1].replace("-", "")}/{x[2]}', limit=400000)
                if b:
                    save(f'{t}/{form}_{x[3]}_{x[2]}', b)
        hits = get(f'https://efts.sec.gov/LATEST/search-index?q=%22credit%20agreement%22&forms=8-K,10-K,10-Q&ciks={c10}', sec=True)
        if hits:
            save(f'{t}/efts_credit.json', hits)
            try:
                hh = json.loads(hits)['hits']['hits']
                ex = [h for h in hh if str(h['_source'].get('file_type', '')).upper().startswith('EX-10')]
                ex.sort(key=lambda h: h['_source'].get('file_date', ''), reverse=True)
                for h in ex[:1]:
                    acc_, fn = h['_id'].split(':')
                    b = get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc_.replace("-", "")}/{fn}', limit=3000000)
                    if b:
                        save(f'{t}/credit_agreement_{fn}', b)
            except Exception as exc:
                log.append(f'efts parse {exc}')
        hits = get(f'https://efts.sec.gov/LATEST/search-index?q=%22pricing%20term%20sheet%22&forms=FWP&ciks={c10}', sec=True)
        if hits:
            save(f'{t}/efts_fwp.json', hits)
    for s in FRED:
        b = get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}', sec=False)
        if b:
            save(f'rates/{s}.csv', b)
    for url, name in (('https://banks.data.fdic.gov/docs/risview_properties.yaml', 'risview_properties.yaml'),
                      ('https://api.fdic.gov/banks/institutions?filters=NAMEHCR:%22JPMORGAN%20CHASE%20%26%20CO%22&fields=CERT,NAME,NAMEHCR,RSSDHCR,ASSET,ACTIVE&limit=20', 'inst_jpm.json'),
                      ('https://api.fdic.gov/banks/financials?filters=CERT:628&fields=CERT,REPDTE,DEP,DEPDOM,EINTEXP,EDEPDOM,INTEXPY,NIMY,INTINCY,NTRTMLGJ,NTRTMMED,NTRSMMDA,BRO,COREDEP,DEPINS,DEPUNA,NTR,NTRTIME&sort_by=REPDTE&sort_order=DESC&limit=8', 'fin_628.json'),
                      ('https://www.fdic.gov/national-rates-and-rate-caps', 'national_rates.html')):
        b = get(url, sec=False)
        if b:
            save(f'fdic/{name}', b)
    save('log.txt', '\n'.join(log))
    print('\n'.join(log[-40:]))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'probe')
