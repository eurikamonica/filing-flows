"""Investors (Disclosures → Investors, and the "Investments" view of each company page): which listed companies earn the
most on their investments, and what they bought — from their own filings and from what other companies say about them.

  The ranking   gains on investments over the last four quarters, from SEC XBRL frames (one request a quarter for all
                filers): DebtAndEquitySecuritiesGainLoss, else GainLossOnInvestments, else EquitySecuritiesFvNiGainLoss
                (realized and unrealized, as the income statement reports them), beside income from equity-method stakes
                (IncomeLossFromEquityMethodInvestments), other non-operating income and pre-tax income — the share of
                pre-tax income the gains made. Fourth quarters come from the annual frames (app/frames.py).
  What they own, for the largest gainers, each piece graded:
      A  its own 13F (positions in listed companies, value, shares, the change against the 13F before — the price gain on
         the shares held a quarter earlier = shares then × the change in price), and the Schedule 13D / 13G it filed
         (stakes above 5% in a listed company)
      B  its own 8-K press releases that announce an investment ("a $5 billion investment in Intel")
      C  other companies' filings that name it as an investor ("an investment from NVIDIA", "led by GV") — 8-K, S-1,
         10-K, 6-K, found with EDGAR full-text search; the investee is the company that filed
    Each piece keeps the sentence and the filing. Private companies appear when a filing names them (a 10-K or S-1 of a
    company that later listed, or the investor's own release); a stake no filing names stays unknown.

    python disclosures/app/investors.py collect --root inv --universe site/index.json --minutes 40
    python disclosures/app/investors.py build --root inv --universe site/index.json
writes public/index.json (the ranking), public/c/<cik>.json (one investor), public/status.json
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json  # noqa: E402
import frames as FR  # noqa: E402

GAINS = ['DebtAndEquitySecuritiesGainLoss', 'GainLossOnInvestments', 'EquitySecuritiesFvNiGainLoss']
OTHER = ['IncomeLossFromEquityMethodInvestments', 'OtherNonoperatingIncomeExpense', 'NonoperatingIncomeExpense',
         'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest']
QUARTERS = 9
TOP = 60                     # investors whose holdings are looked up
REFRESH_DAYS = 7
FTS = 'https://efts.sec.gov/LATEST/search-index'
SUBS = 'https://data.sec.gov/submissions/CIK{cik:010d}.json'
STAKE_FORMS = {'SC 13D', 'SC 13D/A', 'SC 13G', 'SC 13G/A', 'SCHEDULE 13D', 'SCHEDULE 13D/A', 'SCHEDULE 13G', 'SCHEDULE 13G/A'}
MANAGERS = {'6282', '6211', '6722', '6726', '6799', '6371'}   # their 13F is clients' money, not their own investments
NOT_INVESTOR = re.compile(r'(?i)\b(trust|etf|fund|bitcoin|ether|gold|silver|commodity|index|shares?\s+trust|ishares|spdr|proshares|grayscale)\b')
# venture arms and other names a company invests under
ARMS = {1652044: ['Google', 'GV', 'CapitalG', 'Google Ventures'], 1045810: ['NVentures'], 1108524: ['Salesforce Ventures'], 789019: ['M12', 'Microsoft Ventures'],
        1018724: ['Amazon Industrial Innovation Fund', 'Alexa Fund', 'Amazon.com'], 50863: ['Intel Capital'], 804328: ['Qualcomm Ventures'],
        1571996: ['Dell Technologies Capital'], 1326801: ['Meta'], 1341439: ['Oracle'], 1585521: ['Zoom Ventures'], 1543151: ['Uber'],
        320193: ['Apple'], 2488: ['AMD Ventures', 'AMD'], 858877: ['Cisco Investments'], 1067983: ['Berkshire'], 1065521: ['SoftBank', 'SoftBank Vision Fund']}
STRICT = re.compile(r'(?i)\binvest(?:ed|ment|ments|or|ors|ing)\b|\bstake\b|\bequity (?:interest|investment)\b|\bprivate placement\b|\b(?:funding|financing) round\b|'
                    r'\bseries [a-g]\b|\bpurchased? (?:of )?(?:\$[\d.,]+ (?:billion|million) (?:of|in) )?(?:shares|common stock|preferred)\b|\bwarrants? to purchase\b')
INVEST_SENT = re.compile(r'(?i)\binvest(?:ed|ment|ments|ing|s)?\b|\bstake\b|\bled by\b|\bparticipation (?:from|of)\b|\bbacked by\b|\bpurchase of [\w\s,]*shares\b')


def brand(name):
    s = re.sub(r'(?i)[,.]?\s*\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|n\.?v|s\.?a|/[a-z]{2,4}/?)\b\.?', '', name or '')
    s = re.sub(r'\s+', ' ', s).strip(' ,.&')
    return {'Alphabet': 'Alphabet', 'Amazon Com': 'Amazon', 'AMAZON COM': 'Amazon', 'Meta Platforms': 'Meta'}.get(s, s.title() if s.isupper() and len(s) > 4 else s)


class Sec:
    """SEC requests at a fair pace (SEC asks for at most ten a second); nothing kept on disk."""

    def __init__(self, interval=0.15):
        from backfill13f import SecGet
        self.g = SecGet(interval=interval)

    def get(self, url, immutable=False, sec=True):
        return self.g.get(url, immutable=immutable)

    def json(self, url, sec=True):
        return json.loads(self.get(url))


# ---------------------------------------------------------------- the ranking (frames)
def collect_frames(client, root):
    keep_c, keep_e = FR.CONCEPTS, getattr(FR, 'EXTRA', [])
    FR.CONCEPTS, FR.EXTRA = GAINS + OTHER, []
    try:
        return FR.collect(client, root, quarters=QUARTERS)
    finally:
        FR.CONCEPTS, FR.EXTRA = keep_c, keep_e


def ranking(root, universe):
    periods = FR.calendar_quarters(QUARTERS)
    last4 = periods[-4:]
    q = {c: FR.quarterly(root, c, periods) for c in GAINS + OTHER}
    cos = {str(int(c['cik'])): c for c in universe if c.get('cik')}
    rows = []
    for cik, co in cos.items():
        if NOT_INVESTOR.search(co.get('name') or '') or not co.get('ticker'):
            continue
        per, used = {}, set()
        for p in periods:
            for c in GAINS:                           # the first gains concept the company used that quarter
                v = q[c][p].get(cik)
                if v is not None:
                    per[p] = v
                    used.add(c)
                    break
        if not per:
            continue
        have = [p for p in last4 if p in per]
        if len(have) < 2:
            continue
        ttm = sum(per[p] for p in have)
        s = lambda c: sum(v for p in have if (v := q[c][p].get(cik)) is not None) if any(q[c][p].get(cik) is not None for p in have) else None  # noqa: E731
        pre = s(OTHER[3])
        rows.append({'cik': int(cik), 't': co.get('ticker'), 'name': co.get('name'), 'sector': co.get('sector'), 'sic': co.get('sic'),
                     'gains': ttm, 'quarters': len(have), 'concept': sorted(used)[0] if len(used) == 1 else 'mixed',
                     'eqm': s(OTHER[0]), 'other': s(OTHER[1]) if s(OTHER[1]) is not None else s(OTHER[2]), 'pretax': pre,
                     'share': ttm / pre if pre and pre > 0 else None, 'revenue': co.get('revenue'),
                     'series': [[p, round(per[p])] for p in periods if p in per]})
    rows.sort(key=lambda r: -r['gains'])
    return rows, last4


# ---------------------------------------------------------------- what they own
def stakes_filed(client, cik, subs, keep=12):
    """Schedule 13D / 13G the company filed as the holder: the subject company and the date, from the filing's header."""
    r = (subs.get('filings') or {}).get('recent') or {}
    out = []
    for i, form in enumerate(r.get('form') or []):
        if form not in STAKE_FORMS or len(out) >= keep:
            continue
        acc = r['accessionNumber'][i]
        url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/{acc}-index-headers.html'
        try:
            hdr = html.unescape(re.sub(r'<[^>]+>', ' ', client.get(url).decode('utf-8', 'replace')))
        except Exception:                           # noqa: BLE001
            continue
        subj = re.search(r'SUBJECT COMPANY:.*?COMPANY CONFORMED NAME:\s*(.+?)\s+CENTRAL INDEX KEY:\s*(\d+)', hdr, re.S)
        filer = re.search(r'FILED BY:.*?CENTRAL INDEX KEY:\s*(\d+)', hdr, re.S)
        if not subj or not filer or int(filer.group(1)) != int(cik) or int(subj.group(2)) == int(cik):
            continue
        out.append({'name': subj.group(1).strip(), 'cik': int(subj.group(2)), 'form': form, 'filed': r['filingDate'][i],
                    'url': f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/{acc}-index.html'})
    seen, uniq = set(), []
    for s in out:                                   # newest first; one per subject company
        if s['cik'] not in seen:
            seen.add(s['cik'])
            uniq.append(s)
    return uniq


def thirteen_f(client, cik):
    """The latest two 13F-HR: positions, and each one's change and price gain against the quarter before."""
    from holdings13f.build import filing_list, load_filing
    from holdings13f.core import aggregate
    since = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    try:
        _, fl = filing_list(client, cik, since)
    except Exception:                               # noqa: BLE001
        return None
    fl = [f for f in fl if f['form'] == '13F-HR'][-2:]
    if not fl:
        return None
    snaps = []
    for f in fl:
        try:
            snaps.append(load_filing(client, f))
        except Exception:                           # noqa: BLE001
            continue
    if not snaps:
        return None
    cur = aggregate([r for r in snaps[-1]['rows'] if r['put_call'] == 'NONE'])
    prev = {r['cusip']: r for r in aggregate([r for r in snaps[0]['rows'] if r['put_call'] == 'NONE'])} if len(snaps) > 1 else {}
    pos = []
    for r in cur[:40]:
        p = prev.get(r['cusip'])
        price = r['value_usd'] / r['shares'] if r['shares'] else None
        pprice = p['value_usd'] / p['shares'] if p and p['shares'] else None
        pos.append({'issuer': r['issuer'], 'cusip': r['cusip'], 'shares': r['shares'], 'usd': r['value_usd'], 'weight': round(r['weight'], 4),
                    'prev_shares': p['shares'] if p else 0, 'prev_usd': p['value_usd'] if p else 0,
                    'price_gain': round(p['shares'] * (price - pprice)) if p and price and pprice else None,
                    'status': 'new' if not p else 'added' if r['shares'] > p['shares'] * 1.001 else 'trimmed' if r['shares'] < p['shares'] * 0.999 else 'held'})
    gone = [{'issuer': p['issuer'], 'cusip': c, 'prev_usd': p['value_usd'], 'status': 'sold'} for c, p in prev.items() if c not in {r['cusip'] for r in cur}][:15]
    last = snaps[-1]
    return {'period': last['period'], 'filed': last['filed'], 'prev_period': snaps[0]['period'] if len(snaps) > 1 else None,
            'total': sum(r['value_usd'] for r in cur), 'positions': len(cur), 'top': pos, 'sold': gone, 'url': last.get('url')}


def fts(client, q, start, forms='8-K,S-1,424B4,10-K,10-Q,6-K,F-1,20-F', ciks=None):
    # a form with a slash (S-1/A) in the list empties the search
    url = f'{FTS}?q={quote(q)}&startdt={start}&enddt={dt.date.today().isoformat()}&forms={forms}' + (f'&ciks={int(ciks):010d}' if ciks else '')
    try:
        return (client.json(url).get('hits') or {}).get('hits') or []
    except Exception:                               # noqa: BLE001
        return []


def _doc_url(hit):
    adsh, fn = hit['_id'].split(':', 1)
    cik = int(((hit['_source'].get('ciks') or ['0'])[0]))
    return f'https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace("-", "")}/{fn}'


def sentence(client, url, names, cache):
    """The sentence of a filing that names the investor near an investment word."""
    if url in cache:
        return cache[url]
    try:
        t = client.get(url).decode('utf-8', 'replace')
    except Exception:                               # noqa: BLE001
        cache[url] = None
        return None
    t = html.unescape(re.sub(r'(?is)<(script|style)\b.*?</\1>|<[^>]+>', ' ', t))
    t = re.sub(r'\s+', ' ', t)
    best = None
    for s in re.split(r'(?<=[.;])\s+(?=[A-Z“"])', t):
        if not 30 < len(s) < 700:
            continue
        for n in names:
            for m in re.finditer(r'\b' + re.escape(n) + r'\b', s, re.I if len(n) > 3 else 0):
                near = s[max(0, m.start() - 140):m.end() + 140]
                if STRICT.search(near):
                    best = s.strip()
                    break
            if best:
                break
        if best:
            break
    if best:                                        # the exhibit's header that the text starts with ("EX-99.1 2 d36680dex991.htm EX-99.1 Exhibit 99.1")
        best = re.sub(r'^(?:EX-\d+(?:\.\d+)?\s+\d+\s+\S+\.html?\s+)?(?:EX-\d+(?:\.\d+)?\s+)*(?:Document\s+)?(?:Exhibit\s+\d+(?:\.\d+)?\s+)?', '', best)
    cache[url] = best[:500] if best else None
    return cache[url]


def named_by_others(client, cik, names, start, cache, limit=16):
    """Filings of other companies that name the company as an investor in them."""
    phr = []
    for n in names[:4]:
        phr += [f'"investment from {n}"', f'"investment by {n}"', f'"{n} invested"', f'"led by {n}"', f'"investment from {n}"',
                f'"strategic investment from {n}"', f'"{n} has invested"', f'"participation from {n}"']
    hits = fts(client, ' OR '.join(dict.fromkeys(phr)), start)
    out, seen = [], set()
    for h in hits:
        s = h['_source']
        filer = [int(x) for x in (s.get('ciks') or [])]
        if not filer or filer[0] == int(cik) or filer[0] in seen:
            continue
        seen.add(filer[0])
        url = _doc_url(h)
        if len(out) >= limit or len(cache) > 40:
            break
        q = sentence(client, url, names, cache)
        if not q:                                   # the phrase is not about an investment in the filer ("led by Google and Microsoft")
            continue
        dn = (s.get('display_names') or [''])[0]
        m = re.match(r'(.+?)\s+(?:\(([A-Z0-9.,\s-]+)\)\s+)?\(CIK', dn)
        out.append({'name': (m.group(1) if m else dn).strip(), 'tickers': (m.group(2) or '').replace(' ', '') if m else '', 'cik': filer[0],
                    'form': s.get('form'), 'filed': s.get('file_date'), 'url': url, 'q': q})
    return out


NAME_AFTER = re.compile(r'(?:invest(?:ed|ment|ing)?|stake|equity interest|shares)\s+(?:of\s+(?:up to\s+)?\$[\d.,]+\s*(?:billion|million)\s+|of approximately \$[\d.,]+\s*(?:billion|million)\s+)?in\s+'
                        r'((?:[A-Z][\w&.\-’\']*|AI|of|and|de)(?:\s+(?:[A-Z][\w&.\-’\']*|AI|of|and|de)){0,5})')
SKIP = re.compile(r'^(?:the|our|its|their|this|these|a|an|research|development|capital|growth|infrastructure|AI|technology|data|new|common|cash|fiscal|addition|connection)\b', re.I)


def own_announcements(client, cik, names, start, cache, limit=10):
    """The company's own 8-K releases that announce an investment in another company: the named company and the sentence."""
    hits = fts(client, '"strategic investment" OR "equity investment in" OR "invest up to" OR "to invest" OR "investment in"', start, forms='8-K', ciks=cik)
    out, seen = [], set()
    for h in hits[:30]:
        if len(out) >= limit:
            break
        url = _doc_url(h)
        q = sentence(client, url, names + ['we', 'We', 'the Company'], cache)
        if not q:
            continue
        m = NAME_AFTER.search(q)
        if not m:
            continue
        nm = m.group(1).strip(' .,')
        if SKIP.match(nm) or len(nm) < 3 or nm in seen:
            continue
        seen.add(nm)
        amt = re.search(r'\$\s?([\d.,]+)\s*(billion|million)', q)
        out.append({'name': nm, 'usd': float(amt.group(1).replace(',', '')) * (1e9 if amt.group(2) == 'billion' else 1e6) if amt else None,
                    'form': h['_source'].get('form'), 'filed': h['_source'].get('file_date'), 'url': url, 'q': q})
    return out


def evidence(client, row, years=5):
    cik = row['cik']
    names = [brand(row['name'])] + ARMS.get(cik, [])
    start = (dt.date.today() - dt.timedelta(days=365 * years)).isoformat()
    cache = {}
    try:
        subs = client.json(SUBS.format(cik=cik))
    except Exception:                               # noqa: BLE001
        subs = {}
    own_book = str(row.get('sic') or '') not in MANAGERS
    return {'at': now(), 'names': names, 'f13': thirteen_f(client, cik) if own_book else None, 'clients_13f': not own_book,
            'stakes': stakes_filed(client, cik, subs) if own_book else [],
            'others': named_by_others(client, cik, names, start, cache), 'own': own_announcements(client, cik, names, start, cache)}


def collect(root, universe_path, minutes=40, client=None, top=TOP):
    root = Path(root)
    t0 = time.monotonic()
    client = client or Sec()
    st = {'frames': collect_frames(client, root)}
    uni = read_json(universe_path, {}) or {}
    rows, _ = ranking(root, uni.get('companies') if isinstance(uni, dict) else uni)
    stale = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=REFRESH_DAYS)).isoformat()
    done = left = 0
    for r in rows[:top]:
        p = root / 'cache' / 'ev' / f"{r['cik']}.json"
        if (read_json(p, {}) or {}).get('at', '') > stale:
            continue
        if time.monotonic() - t0 > minutes * 60:
            left += 1
            continue
        try:
            write_json(p, evidence(client, r))
            done += 1
        except Exception as e:                      # noqa: BLE001 — one investor must not stop the rest
            print(f'investors {r["t"]}: {str(e)[:160]}', flush=True)
    st.update({'investors_read': done, 'left': left, 'seconds': round(time.monotonic() - t0)})
    return st


# ---------------------------------------------------------------- build
def _norm(s):
    return re.sub(r'[^a-z0-9]', '', re.sub(r'(?i)\b(inc|corp|corporation|co|ltd|plc|holdings?|group|class [a-c]|com|new|the)\b', '', s or '').lower())


def build(root, universe_path, out=None):
    root = Path(root)
    out = Path(out or root / 'public')
    uni = read_json(universe_path, {}) or {}
    cos = uni.get('companies') if isinstance(uni, dict) else uni
    rows, last4 = ranking(root, cos or [])
    by_cik = {int(c['cik']): c for c in cos or [] if c.get('cik')}
    by_name = {}
    for c in cos or []:
        if c.get('ticker'):
            by_name.setdefault(_norm(c.get('name')), c)
    (out / 'c').mkdir(parents=True, exist_ok=True)
    idx = []
    for i, r in enumerate(rows):
        ev = read_json(root / 'cache' / 'ev' / f"{r['cik']}.json", {}) if i < TOP * 2 else {}
        holds = []                                  # one list, the strongest evidence first
        f13 = (ev or {}).get('f13') if str(r.get('sic') or '') not in MANAGERS else None
        for p in (f13 or {}).get('top') or []:
            c = by_name.get(_norm(p['issuer']))
            holds.append({'name': p['issuer'], 't': (c or {}).get('ticker'), 'cik': (c or {}).get('cik'), 'grade': 'A', 'how': '13F position',
                          'usd': p['usd'], 'status': p['status'], 'price_gain': p.get('price_gain'), 'date': f13['period'], 'url': f13.get('url')})
        for s in (ev or {}).get('stakes') or []:
            c = by_cik.get(s['cik'])
            holds.append({'name': s['name'], 't': (c or {}).get('ticker'), 'cik': s['cik'], 'grade': 'A', 'how': f"{s['form']} (over 5% of the company)",
                          'date': s['filed'], 'url': s['url']})
        for s in (ev or {}).get('own') or []:
            c = by_name.get(_norm(s['name']))
            holds.append({'name': s['name'], 't': (c or {}).get('ticker'), 'cik': (c or {}).get('cik'), 'grade': 'B', 'how': 'its own release announces it',
                          'usd': s.get('usd'), 'date': s['filed'], 'url': s['url'], 'q': s.get('q')})
        for s in (ev or {}).get('others') or []:
            c = by_cik.get(s['cik'])
            holds.append({'name': (c or {}).get('name') or s['name'], 't': (c or {}).get('ticker') or (s.get('tickers') or '').split(',')[0] or None, 'cik': s['cik'],
                          'grade': 'C', 'how': f"named as an investor in its {s['form']}", 'date': s['filed'], 'url': s['url'], 'q': s.get('q')})
        merged, seen = [], {}
        for h in holds:                             # the same company from several sources: one row, every source kept
            k = h.get('cik') or _norm(h['name'])
            if k in seen:
                m = merged[seen[k]]
                m['also'] = (m.get('also') or []) + [{x: h.get(x) for x in ('grade', 'how', 'date', 'url', 'q')}]
                continue
            seen[k] = len(merged)
            merged.append(h)
        doc = {**r, 'names': (ev or {}).get('names'), 'f13': {k: v for k, v in (f13 or {}).items() if k != 'top'} if f13 else None,
               'sold': (f13 or {}).get('sold') or [], 'holdings': merged, 'manager': str(r.get('sic') or '') in MANAGERS, 'read_at': (ev or {}).get('at'), 'periods': last4, 'generated_at': now()}
        if ev or i < 300:
            write_json(out / 'c' / f"{r['cik']}.json", doc)
        top = max((h for h in merged if h.get('price_gain')), key=lambda h: h['price_gain'], default=None)
        idx.append([r['cik'], r['t'], r['name'], r['sector'], round(r['gains']), r['quarters'], r['concept'], r['eqm'] and round(r['eqm']),
                    r['other'] and round(r['other']), r['pretax'] and round(r['pretax']), r['share'] and round(r['share'], 4),
                    len(merged), (top or {}).get('name'), (top or {}).get('price_gain'), [h['name'] for h in merged[:5]], bool(ev)])
    fields = ['cik', 't', 'name', 'sector', 'gains', 'quarters', 'concept', 'eqm', 'other', 'pretax', 'share', 'n_holdings', 'top_gainer', 'top_gain', 'holdings', 'read']
    write_json(out / 'index.json', {'generated_at': now(), 'periods': last4, 'fields': fields, 'rows': idx[:1500],
                                    'losers': [x for x in idx if x[4] < 0][-60:][::-1]})
    st = {'built_at': now(), 'ranked': len(rows), 'read': sum(1 for x in idx if x[-1]), 'periods': last4}
    write_json(out / 'status.json', st)
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--universe', required=True)
    c.add_argument('--minutes', type=float, default=40)
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--universe', required=True)
    a = ap.parse_args()
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.universe, a.minutes)), flush=True)
    else:
        print(json.dumps(build(a.root, a.universe)), flush=True)


if __name__ == '__main__':
    main()
