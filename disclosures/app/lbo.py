"""Buyouts (Disclosures → Buyouts, and the "LBO & takeover" view of each company page): what a private buyer could pay,
what history says about who gets bought, and what is being said now.

  inputs     per company, the trailing figures an LBO needs (research/valuation c/<cik>.json: price, shares, debt, cash,
             claims, EBITDA, revenue, capex, D&A, tax rate, growth) and the debt market (debt/rates.json: SOFR and the
             high-yield B spread). The model itself is disclosures/docs/lbo-model.js — the same code in the browser
             (sliders) and in the board (disclosures/app/lbo_board.cjs): IRR at today's price plus a premium, and the most a
             buyer could pay for a 20% IRR.
  history    every merger proxy (DEFM14A), target's tender-offer response (SC 14D9) and going-private statement (SC 13E3)
             on EDGAR since 2011 (the quarterly form indexes), against the SEC's XBRL figures of every company the year
             before (annual frames: size, EBITDA yield, leverage, margins, cash flow, growth). A logistic model of "was it
             bought within a year", tested out of time; the event rates by decile of each figure; the premiums the merger
             proxies state ("a premium of approximately 31% over the closing price …"), read a batch at a time.
  rumors     news headlines about sales, take-private offers and talks (Google News search, headline + source + link
             only), the 8-Ks that speak of strategic alternatives, unsolicited or non-binding proposals and special
             committees, Schedule 13D purposes that talk of a sale or a proposal, and announced deals (research/filings).

Kept on the branch "research-lbo" (one commit, force-pushed) by .github/workflows/research-lbo.yml; scan.yml publishes
public/ at disclosures/data/research/lbo/.

    python disclosures/app/lbo.py collect --root rl --site-index site/index.json --minutes 40
    python disclosures/app/lbo.py build --root rl --site-index site/index.json --valuation val/public --site-data sd
"""
import argparse
import datetime as dt
import gzip
import html
import json
import math
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json  # noqa: E402
import outside as OUT  # noqa: E402            names, matching, http

SEC_UA = os.environ.get('SEC_USER_AGENT', '').strip() or 'Filing Flows filingflows@gmail.com'
FIRST_YEAR = 2011
DEAL_FORMS = {'DEFM14A': 'merger', 'SC 14D9': 'tender', 'SC 13E3': 'private'}
SKIP_KINDS = {'bank', 'insurer', 'reit'}


def sec_get(url, timeout=120):
    time.sleep(0.12)                                    # the SEC asks for at most ten requests a second
    return OUT.get(url, headers={'User-Agent': SEC_UA, 'Accept-Encoding': 'identity'}, timeout=timeout)


def rgz(p, default):
    try:
        with gzip.open(p, 'rt') as f:
            return json.load(f)
    except Exception:
        return default


def wgz(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, 'wt') as f:
        json.dump(obj, f, separators=(',', ':'))


# ---------------------------------------------------------------- EDGAR form indexes: the deals since 2011
def quarters(today):
    return [(y, q) for y in range(FIRST_YEAR, today.year + 1) for q in range(1, 5) if (y, q) <= (today.year, (today.month - 1) // 3 + 1)]


def parse_form_index(text):
    """[[form, cik, name, date, path]] for the deal forms in a quarter's form.idx."""
    out = []
    for line in text.splitlines():
        for f in DEAL_FORMS:
            if line.startswith(f + ' ') and not line.startswith(f + '/'):
                rest = line[len(f):].strip()
                m = re.match(r'(.+?)\s{2,}(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\S+)', rest)
                if m:
                    out.append([f, int(m[2]), m[1].strip(), m[3], m[4]])
    return out


def fetch_indexes(root, today, fetch=None):
    """cache/index/<YYYY>Q<q>.json: past quarters once, the current one every run."""
    fetch = fetch or (lambda u: sec_get(u).decode('latin-1'))
    n = 0
    cur = (today.year, (today.month - 1) // 3 + 1)
    for y, q in quarters(today):
        p = Path(root) / 'cache' / 'index' / f'{y}Q{q}.json'
        if p.exists() and (y, q) != cur:
            continue
        try:
            rows = parse_form_index(fetch(f'https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{q}/form.idx'))
        except Exception as e:  # noqa: BLE001
            print(f'form index {y}Q{q}: {e}', flush=True)
            continue
        write_json(p, rows)
        n += 1
    return n


def events(root):
    """{cik: [(date, kind, form, path)]} oldest first — every deal filing on record per company."""
    out = {}
    for p in sorted((Path(root) / 'cache' / 'index').glob('*.json')):
        for f, cik, name, date, path in read_json(p, []) or []:
            out.setdefault(cik, []).append((date, DEAL_FORMS[f], f, path))
    for v in out.values():
        v.sort()
    return out


# ---------------------------------------------------------------- XBRL annual frames: every company's figures by year
FRAMES = {
    'revenue': [('us-gaap', 'Revenues'), ('us-gaap', 'RevenueFromContractWithCustomerExcludingAssessedTax'), ('us-gaap', 'SalesRevenueNet')],
    'oi': [('us-gaap', 'OperatingIncomeLoss')],
    'da': [('us-gaap', 'DepreciationDepletionAndAmortization'), ('us-gaap', 'DepreciationAndAmortization'), ('us-gaap', 'DepreciationAmortizationAndAccretionNet')],
    'ocf': [('us-gaap', 'NetCashProvidedByUsedInOperatingActivities')],
    'capex': [('us-gaap', 'PaymentsToAcquirePropertyPlantAndEquipment')],
    'debt': [('us-gaap', 'LongTermDebt'), ('us-gaap', 'LongTermDebtNoncurrent')],
    'cash': [('us-gaap', 'CashAndCashEquivalentsAtCarryingValue')],
    'float': [('dei', 'EntityPublicFloat')],
}
INSTANT = {'debt', 'cash'}


def frame_period(key, year):
    return f'CY{year}Q2I' if key == 'float' else f'CY{year}Q4I' if key in INSTANT else f'CY{year}'


def fetch_frames(root, today, budget_s, fetch=None):
    """cache/frames/<key>-<year>.json.gz {cik: value}: every year since FIRST_YEAR, the latest two refreshed monthly."""
    fetch = fetch or (lambda u: json.loads(sec_get(u, timeout=180)))
    t0, n = time.time(), 0
    for year in range(FIRST_YEAR, today.year):
        for key, tags in FRAMES.items():
            p = Path(root) / 'cache' / 'frames' / f'{key}-{year}.json.gz'
            old = rgz(p, None)
            if old and (year < today.year - 2 or (old.get('_at') or '') >= (today - dt.timedelta(days=30)).isoformat()):
                continue
            if time.time() - t0 > budget_s:
                return n
            vals = {}
            for ns, tag in tags:                                     # the first tag a company reports wins
                try:
                    d = fetch(f'https://data.sec.gov/api/xbrl/frames/{ns}/{tag}/USD/{frame_period(key, year)}.json')
                except Exception as e:  # noqa: BLE001
                    if '404' not in str(e):
                        print(f'frames {tag} {year}: {e}', flush=True)
                    continue
                for r in d.get('data') or []:
                    vals.setdefault(str(r['cik']), r['val'])
            wgz(p, {'_at': today.isoformat(), **vals})
            n += 1
    return n


def year_figures(root, year):
    out = {}
    for key in FRAMES:
        d = rgz(Path(root) / 'cache' / 'frames' / f'{key}-{year}.json.gz', {}) or {}
        for cik, v in d.items():
            if cik != '_at':
                out.setdefault(cik, {})[key] = v
    return out


FEATURES = ['size', 'ebitda_yield', 'net_lev', 'fcf_margin', 'ebitda_margin', 'growth', 'capex_int']
FEATURE_NAMES = {'size': 'Size (log enterprise value)', 'ebitda_yield': 'EBITDA / enterprise value', 'net_lev': 'Net debt / EBITDA',
                 'fcf_margin': 'Free cash flow / revenue', 'ebitda_margin': 'EBITDA margin', 'growth': 'Revenue growth',
                 'capex_int': 'Capex / revenue'}


def clip(v, lo, hi):
    return None if v is None or not math.isfinite(v) else max(lo, min(hi, v))


def features(f, prev=None):
    """The model's figures from one year's frames (or from the trailing inputs for today): None if not enough."""
    rev, oi, fl = f.get('revenue'), f.get('oi'), f.get('float')
    if not rev or rev < 2e7 or oi is None or not fl or fl < 2e7:
        return None
    ebitda = oi + (f.get('da') or 0)
    debt, cash = f.get('debt') or 0, f.get('cash') or 0
    ev = fl + debt - cash
    if ev <= 0:
        return None
    fcf = (f['ocf'] - (f.get('capex') or 0)) if f.get('ocf') is not None else None
    g = (rev / prev['revenue'] - 1) if prev and prev.get('revenue') else None
    return {'size': math.log10(ev), 'ebitda_yield': clip(ebitda / ev, -0.5, 0.5),
            'net_lev': clip((debt - cash) / ebitda, -5, 10) if ebitda > 0 else 10.0,
            'fcf_margin': clip(fcf / rev, -1, 0.6) if fcf is not None else None, 'ebitda_margin': clip(ebitda / rev, -1, 0.8),
            'growth': clip(g, -0.5, 1.0), 'capex_int': clip(f['capex'] / rev, 0, 0.6) if f.get('capex') is not None else None}


def label(evs, fy_end_year, kinds):
    """Bought within the year after the annual report: a deal filing from April of the next year to March the year after."""
    lo, hi = f'{fy_end_year + 1}-04-01', f'{fy_end_year + 2}-03-31'
    return int(any(lo <= d <= hi and k in kinds for d, k, _, _ in evs or []))


def present(root, year):
    """CIKs with an annual report for the year (revenue or operating income in the frames)."""
    out = set()
    for key in ('revenue', 'oi'):
        d = rgz(Path(root) / 'cache' / 'frames' / f'{key}-{year}.json.gz', {}) or {}
        out |= {k for k in d if k != '_at'}
    return out


def sample(root, today):
    """[(year, cik, features, acquired, private)] for every company-year with figures and a full year after it. A deal
    filing counts only if the company then stopped reporting (when those years are on file): an acquirer whose own
    shareholders vote files a merger proxy too, and it goes on reporting."""
    ev = events(root)
    rows = []
    last = today.year - 2                                      # a label needs the whole following year
    have = {y for y in range(FIRST_YEAR, today.year) if (Path(root) / 'cache' / 'frames' / f'oi-{y}.json.gz').exists()}
    later = {y: present(root, y) for y in have}
    prev = year_figures(root, FIRST_YEAR)
    for y in range(FIRST_YEAR + 1, last + 1):
        cur = year_figures(root, y)
        gone = later.get(y + 3)                                  # still reporting three years on: not bought
        for cik, f in cur.items():
            x = features(f, prev.get(cik))
            if not x:
                continue
            e = ev.get(int(cik))
            a, p = label(e, y, {'merger', 'tender', 'private'}), label(e, y, {'private'})
            if gone is not None and cik in gone:
                a = p = 0
            rows.append((y, int(cik), x, a, p))
        prev = cur
    return rows


# ---------------------------------------------------------------- logistic regression (numpy), out-of-time test
def design(rows, stats=None):
    """One column per quintile of each figure (the middle one left out) and one for "missing": odds that rise at both
    ends — small companies and large, loss-makers and cash machines — are not forced onto a line."""
    import numpy as np
    X = np.array([[r[2].get(k) if r[2].get(k) is not None else np.nan for k in FEATURES] for r in rows], dtype=float)
    if stats is None:
        cuts = [np.nanquantile(X[:, j], [0.2, 0.4, 0.6, 0.8]).tolist() for j in range(len(FEATURES))]
    else:
        cuts = stats['cuts']
    cols = [np.ones(len(rows))]
    for j in range(len(FEATURES)):
        x = X[:, j]
        b = np.searchsorted(np.array(cuts[j]), np.where(np.isnan(x), -np.inf, x), side='right')
        for q in (0, 1, 3, 4):
            cols.append(((b == q) & ~np.isnan(x)).astype(float))
        cols.append(np.isnan(x).astype(float))
    return np.vstack(cols).T, {'cuts': [[float(v) for v in c] for c in cuts]}


COLS = ['intercept'] + [f'{k}:{q}' for k in FEATURES for q in ('q1', 'q2', 'q4', 'q5', 'na')]


def fit_logit(X, y, l2=1.0, iters=30):
    import numpy as np
    w = np.zeros(X.shape[1])
    R = l2 * np.eye(X.shape[1])
    R[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        H = X.T @ (X * (p * (1 - p))[:, None]) + R
        g = X.T @ (p - y) + R @ w
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def auc(p, y):
    import numpy as np
    order = np.argsort(p)
    r = np.empty(len(p))
    r[order] = np.arange(1, len(p) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else None


def history_model(rows, target=3, split_year=None):
    """Fit on the years before split_year, test on the rest (AUC, lift of the top decile); then refit on every year."""
    import numpy as np
    if len(rows) < 500:
        return None
    years = sorted({r[0] for r in rows})
    split_year = split_year or years[-3]
    tr = [r for r in rows if r[0] < split_year]
    te = [r for r in rows if r[0] >= split_year]
    Xtr, st = design(tr)
    ytr = np.array([r[target] for r in tr], float)
    w = fit_logit(Xtr, ytr)
    out = {'train_years': [years[0], split_year - 1], 'test_years': [split_year, years[-1]], 'n': len(rows), 'events': int(sum(r[target] for r in rows))}
    if te:
        Xte, _ = design(te, st)
        yte = np.array([r[target] for r in te], float)
        pte = 1 / (1 + np.exp(-Xte @ w))
        cut = np.quantile(pte, 0.9)
        top = yte[pte >= cut]
        out.update({'auc_test': auc(pte, yte), 'base_test': float(yte.mean()), 'top_decile_rate': float(top.mean()) if len(top) else None})
    X, st = design(rows)
    y = np.array([r[target] for r in rows], float)
    w = fit_logit(X, y)
    p = 1 / (1 + np.exp(-X @ w))
    dec = np.quantile(p, np.linspace(0, 1, 11))
    out.update({'coef': dict(zip(COLS, [round(float(v), 4) for v in w])), 'stats': st,
                'base': float(y.mean()), 'deciles': [round(float(v), 6) for v in dec],
                'auc_in': auc(p, y)})
    return out


def score(model, x):
    import numpy as np
    X, _ = design([(0, 0, x, 0, 0)], model['stats'])
    w = np.array([model['coef'][k] for k in COLS])
    p = float(1 / (1 + np.exp(-X @ w))[0])
    dec = model['deciles']
    pct = sum(1 for d in dec[1:-1] if p > d) * 10              # the decile among company-years of the past
    contrib = {}
    for i, c in enumerate(COLS[1:], 1):                         # each figure's push on the odds (log-odds against its middle quintile)
        k = c.split(':')[0]
        if x.get(k) is not None and X[0, i]:
            contrib[k] = contrib.get(k, 0) + round(float(w[i]), 3)
    return {'p': round(p, 5), 'decile': pct // 10 + 1, 'lift': round(p / model['base'], 2) if model['base'] else None,
            'drivers': sorted(contrib.items(), key=lambda kv: -abs(kv[1]))[:4]}


def lift_tables(rows, target=3):
    """Per figure: the event rate by quintile of the figure (all company-years pooled)."""
    out = {}
    for k in FEATURES:
        vals = sorted((r[2][k], r[target]) for r in rows if r[2].get(k) is not None)
        if len(vals) < 500:
            continue
        n = len(vals)
        q = []
        for i in range(5):
            part = vals[i * n // 5:(i + 1) * n // 5]
            q.append([round(part[0][0], 4), round(part[-1][0], 4), round(sum(v[1] for v in part) / len(part), 5)])
        out[k] = q
    return out


# ---------------------------------------------------------------- premiums the merger proxies state
PREMIUM = re.compile(r'(?i)(?:represents?|representing|reflects?|reflecting|constitutes?|implies|implied|a)\s+(?:an?\s+)?(?:approximate\s+|total\s+)?premium\s+of\s+'
                     r'(?:approximately\s+|about\s+|roughly\s+)?(\d{1,3}(?:\.\d+)?)\s?%\s+(?:over|to|above|relative to|compared to|based on)\s+(?:the\s+)?([^.;,]{0,160})')
CASH_PS = re.compile(r'(?i)\$\s?(\d{1,4}(?:\.\d{1,4})?)\s+(?:per share\s+)?in cash(?:,)?\s+(?:per share|without interest|for each)')


def premiums_of(text):
    """[(pct, basis)] of a proxy's text: 'unaffected' or 'closing price on the last trading day …' mentions first."""
    out = []
    for m in PREMIUM.finditer(text):
        pct = float(m[1])
        if 0 < pct <= 300:
            basis = re.sub(r'\s+', ' ', m[2]).strip()
            out.append((pct, basis[:120]))
    rank = lambda b: 0 if re.search(r'(?i)unaffected', b) else 1 if re.search(r'(?i)closing|last (?:full )?trading day', b) else 2   # noqa: E731
    return sorted(out, key=lambda x: rank(x[1]))


def proxy_doc(cik, path, fetch=None):
    """The proxy's main document text: the filing index → its largest .htm."""
    fetch = fetch or sec_get
    acc = path.rsplit('/', 1)[1].replace('.txt', '')
    folder = f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-", "")}/'
    idx = json.loads(fetch(folder + 'index.json'))
    docs = [x for x in (idx.get('directory') or {}).get('item') or [] if re.search(r'\.html?$', x.get('name', ''), re.I)]
    if not docs:
        return None, None
    main = max(docs, key=lambda x: int(x.get('size') or 0))
    raw = fetch(folder + main['name']).decode('utf-8', 'replace')
    txt = html.unescape(re.sub(r'<[^>]+>', ' ', raw))
    return re.sub(r'\s+', ' ', txt), folder + main['name']


def fetch_premiums(root, universe_ciks, budget_s, fetch=None):
    """cache/premiums.json {accession: {cik, date, form, premium, basis, cash, url}}: proxies of listed companies' deals,
    newest first, within the budget."""
    p = Path(root) / 'cache' / 'premiums.json'
    have = read_json(p, {}) or {}
    todo = []
    for cik, evs in events(root).items():
        if universe_ciks and cik not in universe_ciks:
            continue
        for date, kind, form, path in evs:
            acc = path.rsplit('/', 1)[1].replace('.txt', '')
            if form in ('DEFM14A', 'SC 14D9') and acc not in have and date >= '2014-01-01':
                todo.append((date, cik, form, path, acc))
    todo.sort(reverse=True)
    t0, n = time.time(), 0
    for date, cik, form, path, acc in todo:
        if time.time() - t0 > budget_s:
            break
        try:
            txt, url = proxy_doc(cik, path, fetch)
        except Exception as e:  # noqa: BLE001
            have[acc] = {'cik': cik, 'date': date, 'form': form, 'error': str(e)[:80]}
            continue
        prem = premiums_of(txt or '')
        cash = CASH_PS.search(txt or '')
        have[acc] = {'cik': cik, 'date': date, 'form': form, 'url': url, **({'premium': prem[0][0], 'basis': prem[0][1]} if prem else {}),
                     **({'cash': float(cash[1])} if cash else {})}
        n += 1
        if n % 25 == 0:
            write_json(p, have)
    write_json(p, have)
    return {'read': n, 'waiting': max(0, len(todo) - n), 'on_file': len(have)}


# ---------------------------------------------------------------- rumors: news headlines, 8-Ks, 13Ds, announced deals
NEWS_QUERIES = ['"exploring a sale"', '"explore a sale"', '"strategic alternatives"', '"take-private"', '"take private" offer', '"buyout talks"',
                '"acquisition talks"', '"takeover approach"', '"takeover bid"', '"unsolicited proposal"', '"non-binding proposal"', '"go-private"',
                '"weighing a sale"', '"considering a sale"', '"working with advisers" sale', '"received takeover interest"']
RUMOR = re.compile(r'(?i)\b(?:explor\w+ (?:a |the |potential )?(?:sale|strategic)|strategic alternatives|take[- ]private|go(?:ing)?[- ]private|buyout|'
                   r'takeover|acquisition talks|merger talks|in talks|approach(?:ed)?|unsolicited|non-binding (?:proposal|offer|indication)|'
                   r'considering (?:a )?sale|weigh\w* (?:a )?sale|bid for|offer for|proposal to acquire|special committee|tender offer|to acquire)\b')
FILING_RUMOR = re.compile(r'(?i)strategic alternatives|unsolicited (?:proposal|offer|indication)|non-binding (?:proposal|offer|indication of interest)|'
                          r'special committee|explor\w+ (?:a |the |potential )?(?:sale|strategic transaction)|go(?:ing)?[- ]private|take (?:the company )?private|'
                          r'proposal to acquire|acquire all (?:of the )?(?:outstanding|remaining)')
PURPOSE_RUMOR = re.compile(r'(?i)proposal to acquire|acquire (?:all|the remaining)|going[- ]private|take the (?:issuer|company) private|strategic alternatives|'
                           r'sale of the (?:issuer|company)|explor\w+ (?:a |the )?sale|business combination|merger|tender offer|engag\w+ .{0,60}(?:sale|strategic)')
BUYER = re.compile(r'\b(?:to buy|to acquire|buys|acquires|acquiring|in talks to buy|in talks to acquire|bid for|offer for|makes? (?:a )?(?:bid|offer|approach)|approach(?:es|ed)? (?!by)|agrees? to buy|nears? deal (?:to|for))\b')
TARGET = re.compile(r'\b(?:to be acquired|acquired by|sale to|sells? (?:itself|to)|go(?:es|ing)? private|take[- ]private|receives?|gets?|explor\w+ (?:a )?sale|bid from|offer from|approach from|weighs? sale|considers? sale)\b')
RISKY = OUT.COMMON | {'target', 'apple', 'block', 'visa', 'gap', 'ball', 'crown', 'match', 'snap', 'square', 'carrier', 'sleep', 'shell', 'chase',
                      'twilio', 'amazon', 'ford', 'meta', 'oracle', 'unity', 'fidelity', 'progressive', 'regions', 'equity', 'energy', 'insight',
                      'outlook', 'people', 'select', 'strategic', 'global', 'focus', 'vital', 'option', 'bright', 'clear', 'value', 'merit',
                      'trust', 'pulse', 'signal', 'beacon', 'anchor', 'stride', 'marathon', 'mosaic', 'compass'}


def gnews(query, fetch=None):
    fetch = fetch or (lambda u: OUT.get(u, timeout=40).decode('utf-8', 'replace'))
    x = fetch('https://news.google.com/rss/search?q=' + OUT.urllib.parse.quote(query + ' when:14d') + '&hl=en-US&gl=US&ceid=US:en')
    out = []
    for it in re.findall(r'<item>(.*?)</item>', x, re.S):
        t = re.search(r'<title>(.*?)</title>', it, re.S)
        lk = re.search(r'<link>(.*?)</link>', it, re.S)
        d = re.search(r'<pubDate>(.*?)</pubDate>', it)
        s = re.search(r'<source[^>]*>(.*?)</source>', it, re.S)
        if not t:
            continue
        title = html.unescape(re.sub(r'<!\[CDATA\[|\]\]>', '', t[1])).strip()
        src = html.unescape(s[1]).strip() if s else ''
        if src and title.endswith(' - ' + src):
            title = title[:-len(src) - 3]
        try:
            date = dt.datetime.strptime(d[1][5:16], '%d %b %Y').date().isoformat() if d else None
        except ValueError:
            date = None
        out.append({'title': title, 'source': src, 'date': date, 'url': html.unescape(lk[1]).strip() if lk else ''})
    return out


def headline_matcher(companies):
    """A headline → company: a ticker in parentheses ('(LITE)', '(NYSE: WEN)'), else a company's distinctive name as whole
    words — at least five letters, not an ordinary word, two words when it is one ('Target', 'Block' never alone)."""
    by_t = {c['ticker']: c for c in companies}
    names = {}
    for c in sorted(companies, key=lambda c: -(c['revenue'] or 0)):
        for k in {c.get('core') or '', OUT.norm(c['display'])}:
            k = k.strip()
            if not k or len(k.replace(' ', '')) < 5 or k in RISKY or (' ' not in k and k in OUT.EPA_STOP):
                continue
            names.setdefault(k, c)
    order = sorted(names, key=len, reverse=True)

    def find(title):
        """(company, role): role 'buyer' when the headline has it buying ('Marvell in talks to buy …', 'DoorDash to acquire …')."""
        s = ' ' + OUT.norm(title) + ' '
        for m in re.finditer(r'\((?:(?:NYSE|NASDAQ|Nasdaq|NYSE American|OTC)\s*:\s*)?([A-Z]{1,5}(?:[.-][A-Z])?)\)', title or ''):
            if m[1] in by_t:
                c = by_t[m[1]]
                return c, role(s, OUT.norm(title[:m.start()]).split()[-1:] or [''])
        for k in order:
            if ' ' + k + ' ' in s:
                return names[k], role(s, k.split()[-1:])
        return None, None

    def role(s, last):
        i = s.find(' ' + last[0] + ' ') if last and last[0] else -1
        after = s[i:i + 70] if i >= 0 else ''
        return 'buyer' if BUYER.search(after) and not TARGET.search(after) else 'target'
    return find


def collect_news(root, today, fetch=None):
    p = Path(root) / 'cache' / 'news.json'
    have = read_json(p, []) or []
    seen = {h['url'] for h in have}
    n = 0
    for q in NEWS_QUERIES:
        try:
            for it in gnews(q, fetch):
                if it['url'] and it['url'] not in seen and RUMOR.search(it['title']):
                    seen.add(it['url'])
                    have.append({**it, 'query': q})
                    n += 1
        except Exception as e:  # noqa: BLE001
            print(f'news {q}: {e}', flush=True)
        time.sleep(1.0)
    keep = (today - dt.timedelta(days=365)).isoformat()
    have = [h for h in have if (h.get('date') or '9') >= keep]
    write_json(p, have)
    return {'new': n, 'on_file': len(have)}


def rumor_items(root, companies, site_data, today):
    """{cik: [{date, kind, text, source, url}]} newest first: headlines, 8-Ks, 13Ds and announced deals."""
    find = headline_matcher(companies)
    by_cik = {c['cik']: c for c in companies}
    by_t = {c['ticker']: c for c in companies}
    out = {}

    def add(cik, item):
        if cik in by_cik:
            out.setdefault(cik, []).append(item)
    seen_titles = set()
    for h in read_json(Path(root) / 'cache' / 'news.json', []) or []:
        c, rl = find(h['title'])
        key = (c and c['cik'], re.sub(r'\W+', '', h['title'].lower())[:60])
        if c and key not in seen_titles:
            seen_titles.add(key)
            add(c['cik'], {'date': h.get('date'), 'kind': 'news', 'text': h['title'], 'source': h.get('source'), 'url': h.get('url'),
                           **({'role': 'buyer'} if rl == 'buyer' else {})})
    sd = Path(site_data) if site_data else None
    ev = read_json(sd / 'events8k.json', {}) if sd else {}
    for r in (ev or {}).get('rows') or []:
        txt = ' '.join(filter(None, [r.get('headline'), r.get('quote')]))
        m = FILING_RUMOR.search(txt)
        c = by_t.get(r.get('ticker'))
        if c and (m or 'deal' in (r.get('topics') or [])):
            buyer = not m and re.search(r'(?i)\bto acquire\b|\bacquires\b|completed? (?:the |its )?acquisition of|agreed to acquire', txt) and \
                not re.search(r'(?i)to be acquired|acquired by|will be acquired', txt)
            add(c['cik'], {'date': r.get('filed'), 'kind': '8-K' if m else '8-K deal', 'text': (r.get('headline') or r.get('quote') or '')[:240],
                           'match': m.group(0) if m else 'deal', 'source': 'SEC 8-K', 'url': r.get('url'), **({'role': 'buyer'} if buyer else {})})
    st = read_json(sd / 'stakes.json', {}) if sd else {}
    for r in (st or {}).get('rows') or (st or {}).get('latest') or (st if isinstance(st, list) else []):
        purpose = r.get('purpose') or ''
        if not str(r.get('form', '')).startswith('13D'):
            continue
        m = PURPOSE_RUMOR.search(purpose)
        cik = int(r.get('issuer_cik') or 0)
        if m and cik in by_cik:
            add(cik, {'date': r.get('filed'), 'kind': '13D', 'text': f"{r.get('filer') or r.get('person') or 'A holder'} ({r.get('percent') or '?'}%): {purpose[:220]}",
                      'match': m.group(0), 'source': 'SEC 13D', 'url': r.get('url')})
    deals = read_json(sd / 'deals.json', {}) if sd else {}
    for d in (deals or {}).get('deals') or []:
        c = by_t.get(d.get('target_ticker')) or by_cik.get(int(d.get('target_cik') or 0))
        if c:
            add(c['cik'], {'date': d.get('announced') or d.get('filed'), 'kind': 'deal', 'source': 'SEC',
                           'text': f"Agreed sale{(' to ' + d['acquirer']) if d.get('acquirer') else ''}{(' at $' + str(d['cash']) + ' cash a share') if d.get('cash') else ''}"
                                   f"{(' · ' + d['status']) if d.get('status') else ''}", 'url': ((d.get('docs') or [{}])[0]).get('url'),
                           'status': d.get('status'), 'cash': d.get('cash')})
    for cik, ev13 in events(root).items():                     # going-private statements and merger proxies of the last year
        for date, kind, form, path in ev13:
            if date >= (today - dt.timedelta(days=365)).isoformat():
                add(cik, {'date': date, 'kind': form, 'source': 'SEC', 'text': {'SC 13E3': 'Going-private statement (Schedule 13E-3)', 'DEFM14A': 'Merger proxy (DEFM14A)',
                                                                                 'SC 14D9': 'Response to a tender offer (Schedule 14D-9)'}[form],
                          'url': 'https://www.sec.gov/Archives/' + path})
    for cik in out:
        out[cik].sort(key=lambda x: x.get('date') or '', reverse=True)
    return out


WEIGHT = {'deal': 5, 'SC 13E3': 5, 'DEFM14A': 5, 'SC 14D9': 5, '8-K': 3, '13D': 2.5, 'news': 1.5, '8-K deal': 1}


def rumor_score(items, today):
    """Recency-weighted: each item's weight halves every 45 days; news counted once per day."""
    s, days = 0.0, set()
    for it in items:
        try:
            age = (today - dt.date.fromisoformat((it.get('date') or '')[:10])).days
        except ValueError:
            continue
        if age < 0 or age > 365:
            continue
        if it['kind'] == 'news':
            if (it['date'], it.get('role')) in days:
                continue
            days.add((it['date'], it.get('role')))
        s += WEIGHT.get(it['kind'], 1) * (0.2 if it.get('role') == 'buyer' else 1) * 0.5 ** (age / 45)
    return round(s, 2)


# ---------------------------------------------------------------- inputs for the LBO model
def lbo_inputs(v):
    """The figures the model needs from a valuation file (research/valuation c/<cik>.json), or None."""
    if not v or v.get('kind') in SKIP_KINDS:
        return None
    i = v.get('inputs') or {}
    need = ('revenue', 'ebitda', 'shares', 'price')
    price = v.get('price') or i.get('price')
    if price is None or any(i.get(k) is None for k in need if k != 'price'):
        return None
    keep = ('revenue', 'oi', 'ebitda', 'da', 'capex', 'interest', 'tax_rate', 'shares', 'debt', 'cash', 'claims', 'mcap', 'ev', 'g0')
    out = {k: i.get(k) for k in keep if i.get(k) is not None}
    out['price'] = price
    out['price_date'] = v.get('price_date')
    return out


def rates_of(site_data):
    """The debt market for a new buyout loan: SOFR (or the 3-month bill) and the high-yield B option-adjusted spread, %."""
    d = read_json(Path(site_data) / 'rates.json', {}) if site_data else {}
    s = (d or {}).get('series') or {}
    last = lambda k: ((s.get(k) or {}).get('last') or [None, None])[1]   # noqa: E731
    base = last('SOFR') or last('DGS3MO') or 4.0
    spread = last('BAMLH0A2HYB') or 3.5
    return {'base': round(float(base), 3), 'spread_b': round(float(spread), 3), 'spread_bb': last('BAMLH0A1HYBB'), 'treasury_10y': last('DGS10'),
            'as_of': ((s.get('SOFR') or {}).get('last') or [None])[0]}


# ---------------------------------------------------------------- collect and build
def collect(root, site_index, minutes=40, today=None, only=None):
    root = Path(root)
    today = today or dt.date.today()
    t0 = time.time()
    left = lambda: minutes * 60 - (time.time() - t0)      # noqa: E731
    res = {}

    def run(name, fn):
        if only and name not in only:
            return
        try:
            res[name] = fn()
        except Exception as e:  # noqa: BLE001
            res[name] = {'error': str(e)[:200]}
            print(f'{name}: {e}', flush=True)
    run('indexes', lambda: fetch_indexes(root, today))
    run('frames', lambda: fetch_frames(root, today, budget_s=max(60, left() * 0.5)))
    run('news', lambda: collect_news(root, today))
    comps = OUT.universe(site_index)
    run('premiums', lambda: fetch_premiums(root, None, budget_s=max(30, left() - 60)))
    st = read_json(root / 'state.json', {}) or {}
    st['last_collect'] = {'at': now(), 'seconds': round(time.time() - t0), 'companies': len(comps), **res}
    write_json(root / 'state.json', st)
    return st['last_collect']


def build(root, site_index, valuation=None, site_data=None, today=None):
    root = Path(root)
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today()
    comps = OUT.universe(site_index)
    by_cik = {c['cik']: c for c in comps}
    # history
    rows = sample(root, today)
    models = {}
    if rows:
        models = {'acquired': history_model(rows, 3), 'private': history_model(rows, 4)}
    lifts = lift_tables(rows, 3) if rows else {}
    by_year = {}
    for r in rows:
        b = by_year.setdefault(r[0], [0, 0, 0])
        b[0] += 1
        b[1] += r[3]
        b[2] += r[4]
    ev = events(root)
    prem = read_json(root / 'cache' / 'premiums.json', {}) or {}
    pr = [x for x in prem.values() if x.get('premium') is not None]
    pyear = {}
    for x in pr:
        pyear.setdefault(x['date'][:4], []).append(x['premium'])
    med = lambda L: sorted(L)[len(L) // 2] if L else None      # noqa: E731
    q = lambda L, f: sorted(L)[int(f * (len(L) - 1))] if L else None   # noqa: E731
    allp = [x['premium'] for x in pr]
    sec_of = {c['cik']: c['sector'] for c in comps}
    psec = {}
    for x in pr:
        psec.setdefault(sec_of.get(x['cik'], 'other'), []).append(x['premium'])
    recent = []
    for acc, x in sorted(prem.items(), key=lambda kv: kv[1].get('date') or '', reverse=True):
        if x.get('premium') is None:
            continue
        c = by_cik.get(x['cik'])
        recent.append([x['date'], x['cik'], c['ticker'] if c else None, (c or {}).get('name') or '', x['form'], x['premium'], x.get('basis'), x.get('cash'), x.get('url'),
                       int(any(k == 'private' for _, k, _, _ in ev.get(x['cik']) or []))])
    history = {'generated_at': now(), 'models': models, 'features': FEATURE_NAMES, 'lifts': lifts,
               'by_year': sorted([[y, *v] for y, v in by_year.items()]),
               'premiums': {'n': len(allp), 'median': med(allp), 'p25': q(allp, 0.25), 'p75': q(allp, 0.75),
                            'by_year': sorted([[y, len(v), med(v)] for y, v in pyear.items()]),
                            'by_sector': sorted([[s, len(v), med(v), q(v, 0.25), q(v, 0.75)] for s, v in psec.items() if len(v) >= 5], key=lambda r: -r[1])},
               'recent': recent[:300],
               'note': ('A company-year is "bought" when a merger proxy (DEFM14A), a response to a tender offer (SC 14D-9) or a going-private '
                        'statement (SC 13E-3) of the company was filed from April of the next year to March the year after; "taken private" '
                        'counts the going-private statements only (management buyouts and buyers with insiders; many private-equity deals '
                        'file none, so it undercounts). Figures from the SEC\'s XBRL frames of the fiscal year; size from the public float.')}
    write_json(pub / 'history.json', history)
    # today: inputs, history score, rumors, per company
    rates = rates_of(site_data)
    latest = max((y for y in range(FIRST_YEAR, today.year) if (root / 'cache' / 'frames' / f'oi-{y}.json.gz').exists()), default=None)
    cur, prev = (year_figures(root, latest), year_figures(root, latest - 1)) if latest else ({}, {})
    rum = rumor_items(root, comps, site_data, today)
    index = []
    vdir = Path(valuation) / 'c' if valuation else None
    for c in comps:
        v = read_json(vdir / f"{c['cik']}.json", None) if vdir else None
        inp = lbo_inputs(v)
        x = None
        f = cur.get(str(c['cik']))
        if f:
            f = dict(f)
            if v and (v.get('inputs') or {}).get('mcap'):
                f['float'] = v['inputs']['mcap']                 # today's market value, not last year's float
            x = features(f, prev.get(str(c['cik'])))
        hs = {k: score(m, x) for k, m in models.items() if m and x} if x else {}
        items = rum.get(c['cik'], [])[:40]
        if not inp and not hs and not items:
            continue
        rs = rumor_score(items, today)
        doc = {'cik': c['cik'], 'ticker': c['ticker'], 'name': c['name'], 'sector': c['sector'], 'kind': (v or {}).get('kind'), 'generated_at': now(),
               'inputs': inp, 'rates': rates, 'history': {**hs, 'features': x, 'year': latest} if hs else None, 'rumors': items, 'rumor_score': rs,
               'deals_on_record': [[d, k, f_] for d, k, f_, _ in (ev.get(c['cik']) or [])][-12:]}
        write_json(pub / 'c' / f"{c['cik']}.json", doc)
        a, p_ = hs.get('acquired') or {}, hs.get('private') or {}
        index.append([c['cik'], c['ticker'], c['name'], c['sector'], inp, a.get('p'), a.get('decile'), p_.get('p'), rs,
                      (items[0]['date'] if items else None), (items[0]['kind'] if items else None), (items[0]['text'][:140] if items else None),
                      c['revenue'] or None])
    fields = ['cik', 'ticker', 'name', 'sector', 'inputs', 'p_acquired', 'decile', 'p_private', 'rumor', 'rumor_date', 'rumor_kind', 'rumor_text', 'revenue']
    write_json(pub / 'index.json', {'generated_at': now(), 'fields': fields, 'rates': rates, 'rows': index})
    feed = []
    for cik, items in rum.items():
        c = by_cik[cik]
        for it in items[:8]:
            feed.append([it.get('date'), c['ticker'], cik, it['kind'], it['text'][:220], it.get('source'), it.get('url'), it.get('role')])
    write_json(pub / 'rumors.json', {'generated_at': now(), 'rows': sorted(feed, key=lambda r: r[0] or '', reverse=True)[:600]})
    st = read_json(root / 'state.json', {}) or {}
    a = (models.get('acquired') or {})
    status = {'built_at': now(), 'companies': len(index), 'with_inputs': sum(1 for r in index if r[4]), 'with_history': sum(1 for r in index if r[5] is not None),
              'with_rumors': sum(1 for r in index if r[8]), 'history_rows': len(rows), 'history_events': a.get('events'), 'auc_test': a.get('auc_test'),
              'premiums': len(allp), 'last_collect': st.get('last_collect')}
    write_json(pub / 'status.json', status)
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--site-index', required=True)
    c.add_argument('--minutes', type=float, default=40)
    c.add_argument('--only', default='', help='comma-separated: indexes,frames,news,premiums')
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--site-index', required=True)
    b.add_argument('--valuation', default=None, help='research-valuation public/ (c/<cik>.json)')
    b.add_argument('--site-data', default=None, help='a folder with events8k.json, stakes.json, deals.json, rates.json')
    a = ap.parse_args()
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.site_index, a.minutes, only=set(filter(None, a.only.split(','))) or None)), flush=True)
    else:
        print(json.dumps(build(a.root, a.site_index, a.valuation, a.site_data)), flush=True)


if __name__ == '__main__':
    main()
