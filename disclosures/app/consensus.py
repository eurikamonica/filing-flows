"""Market consensus: what analysts, prediction markets and our own model expect for each company — and how each did.

  collect
    markets   Polymarket (Gamma API: events tagged earnings / stocks / equities / tech …; CLOB price history) and Kalshi
              (company KPI series, earnings-call mention series, other company events), mapped to the site's tickers:
                beat      "Will X beat quarterly earnings?" — the strike is the Street EPS consensus at market creation
                above     "Will X close above $K end of …?" ladders → the market-implied price distribution
                mcap      "X's market cap end of …?" brackets → implied market cap, and price through the share count
                kpi       Kalshi company KPIs (deliveries, subscribers, headcount …) → the implied value of the metric
                mention   Kalshi "what will X say on the earnings call"
                other     CEO changes, acquisitions, products, bankruptcy …
              Closed beat markets: the price a day before the result, kept once (calibration of the crowd).
    analysts  Yahoo Finance consensus (quoteSummary): EPS and revenue estimates for this and next quarter / year with
              low, high and the number of analysts, the EPS trend over 90 days and revisions, price targets and
              ratings, next earnings date, estimate vs actual history; a dated snapshot is kept every day so the page
              can show how the consensus moved.
  build     public/: index.json, c/<cik>.json (company page), markets.json, calendar.json, calibration.json — with our
            own forecast (rotation history: the gravity model's next-quarter and next-month price and 80% range) beside
            the analysts and the markets.

    python app/consensus.py collect --root cons --site-index site/index.json --minutes 25
    python app/consensus.py build   --root cons --rotation rh/public
"""
import argparse
import datetime as dt
import http.cookiejar
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import read_json, write_json  # noqa: E402

GAMMA = 'https://gamma-api.polymarket.com'
CLOB = 'https://clob.polymarket.com'
KALSHI = 'https://api.elections.kalshi.com/trade-api/v2'
YQ = 'https://query2.finance.yahoo.com'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 FilingFlows/1.0'
BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'   # Yahoo refuses other agents
POLY_TAGS = ['earnings', 'stocks', 'equities', 'big-tech', 'tech', 'business', 'finance', 'ipos', 'market-cap', 'companies']
YAHOO_MODULES = 'earningsTrend,earningsHistory,calendarEvents,financialData,recommendationTrend,upgradeDowngradeHistory,earnings,defaultKeyStatistics'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


class Http:
    """Small HTTP client: cookie jar (Yahoo's crumb), per-host spacing, retries with back-off."""

    def __init__(self, spacing=None):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.spacing = spacing or {}
        self.last = {}
        self.calls = 0

    def get(self, url, headers=None, tries=3, timeout=40):
        host = urllib.parse.urlparse(url).hostname
        err = None
        for k in range(tries):
            wait = self.spacing.get(host, 0.25) - (time.monotonic() - self.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self.last[host] = time.monotonic()
            try:
                ua = BROWSER_UA if 'yahoo.com' in (host or '') else UA
                req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'application/json,text/plain,*/*', **(headers or {})})
                with self.op.open(req, timeout=timeout) as r:
                    self.calls += 1
                    return r.read()
            except urllib.error.HTTPError as e:
                err = f'HTTP {e.code}'
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(min(30, 3 * 2 ** k)); continue
                raise RuntimeError(err) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                err = str(e); time.sleep(2 * (k + 1))
        raise RuntimeError(err or 'request failed')

    def json(self, url, headers=None):
        return json.loads(self.get(url, headers))


# ------------------------------------------------------------------ company names → tickers
STOP = {'the', 'of', 'a', 'an', 'de', 'inc', 'corp', 'corporation', 'company', 'co', 'group', 'holdings', 'holding', 'ltd', 'plc', 'sa', 'nv', 'class', 'and',
        'international', 'technologies', 'technology', 'systems', 'global', 'financial', 'bancorp', 'energy', 'american', 'united',
        'first', 'general', 'national', 'new', 'resources', 'services', 'industries', 'brands', 'capital', 'trust', 'communications'}


def universe(site_index):
    ix = read_json(site_index, {}) if site_index else {}
    rows = {}
    for r in ix.get('companies', []):
        if r.get('cik') and r.get('ticker'):
            c = int(r['cik'])
            if c not in rows or (r.get('filed') or '') > (rows[c].get('filed') or ''):
                rows[c] = r
    out = [{'cik': c, 'ticker': r['ticker'].upper(), 'name': r.get('name'), 'sector': r.get('sector'), 'revenue': r.get('revenue') or r.get('rev') or 0}
           for c, r in rows.items()]
    out.sort(key=lambda r: -(r['revenue'] or 0))
    return out


AMBIGUOUS = {'super', 'micro', 'bank', 'home', 'data', 'real', 'life', 'star', 'gold', 'blue', 'green', 'pacific', 'royal', 'west', 'east',
             'north', 'south', 'city', 'state', 'park', 'open', 'world', 'live', 'best', 'next', 'smart', 'digital', 'health', 'care', 'power',
             'water', 'river', 'lake', 'mountain', 'summit', 'pioneer', 'eagle', 'liberty', 'freedom', 'victory', 'apex', 'prime', 'core', 'target',
             'match', 'block', 'square', 'circle', 'snap', 'chase', 'alpha', 'beta', 'delta', 'gamma', 'omega', 'sigma', 'vision', 'future', 'fortune',
             'premier', 'select', 'standard', 'oracle', 'shell', 'visa', 'ford', 'boeing', 'intel'} - {'oracle', 'visa', 'ford', 'boeing', 'intel', 'delta'}
ALIASES = {'GOOGL': ['google', 'alphabet', 'youtube', 'waymo'], 'META': ['facebook', 'instagram', 'whatsapp', 'meta'], 'MSTR': ['microstrategy', 'saylor'],
           'NVDA': ['nvidia'], 'AMZN': ['amazon', 'aws'], 'MSFT': ['microsoft'], 'AAPL': ['apple', 'iphone'], 'TSLA': ['tesla'], 'BRK.B': ['berkshire'],
           'JPM': ['jpmorgan'], 'GS': ['goldman'], 'DAL': ['delta air'], 'NFLX': ['netflix'], 'DIS': ['disney'], 'WMT': ['walmart']}


def name_tokens(name):
    return [x for x in re.findall(r'[a-z0-9]+', (name or '').lower().replace('’', '').replace("'", '').replace('&', ' ').replace('.com', ' ')) if x not in STOP]


COMMON = set("""about above access action active advance after agent alliance alpha america american angel apex apple applied arena array atlas audio auto avenue award balance banner basic beacon beyond black blade blue board bold boost border bridge bright broad brother build bureau cable camden canyon capital carbon cardinal career carrier cascade castle center central century champion change charter cheap chief choice cinema circle citizen civic class clean clear clever climb cloud coast colony comfort command common compass concord connect contract copper corner cosmos country cover craft create credit crest crown crystal cycle daily dance dawn decision delta design diamond direct discovery dollar domain double dream drive dynamic eagle early earth echo edge element elite empire energy engine enterprise equity essential evolve exact excel express falcon family federal fidelity field final first flag fleet flex flight float focus force forest forge fortune forward foundation frame franklin freedom fresh front frontier fusion galaxy game garden gateway general genesis giant glacier global golden grand granite graphic gravity great green group growth guard guide harbor harmony harvest haven heart heritage hero highland horizon house hunter idea image impact independence index infinity inland insight integrity interactive iron island jet journey jupiter key kind king knight label land landmark laser launch leader legacy level liberty light lincoln link lion live local logic lumen lunar magnet main major maple marathon mark market marvel matrix maximum medical mercury merit meridian metro middle millennium mission model modern moment monarch monument motion motor mountain national native natural navigator network north nova oasis ocean office omega online open optimum orbit origin pacific palm paragon park partner patriot peak penn people phoenix pilot pinnacle pioneer planet platinum plus point polar portal power precision premier presidio price prime pro progress prospect public pulse pure quantum quest radiant rally range rapid ready realty regal regency reliance republic reserve resolute river rock rocket royal safe saga scale science score scout select sentinel service shield shift signal silver simple sky smart solar solid sound source south sovereign spark spectrum spirit spring square standard star state sterling stone strategy street strong summit sun superior supreme surge swift symbol synergy system talent target teach terra thunder tide titan total tower trade trail transit trend trinity triumph true trust union unity universal urban valley value vanguard vector velocity venture vertex victory view vintage vision vista vital voyager watch water wave wealth west wild wind wing winner wise wonder world yield zenith alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota mississippi missouri montana nebraska nevada hampshire jersey mexico york carolina dakota ohio oklahoma oregon pennsylvania rhode tennessee texas utah vermont virginia washington wisconsin wyoming canada china japan india brazil germany france britain europe israel korea taiwan russia ukraine iran africa asia australia january february march april june july august september october november december monday friday weekend bitcoin ethereum solana dogecoin ripple crypto election president congress senate court trump musk elon openai anthropic xai""".split())
ALIASES = {'GOOGL': ['google', 'alphabet', 'youtube', 'waymo'], 'META': ['facebook', 'instagram', 'whatsapp', 'meta'], 'MSTR': ['microstrategy', 'saylor'],
           'NVDA': ['nvidia'], 'AMZN': ['amazon', 'aws'], 'MSFT': ['microsoft'], 'AAPL': ['apple', 'iphone'], 'TSLA': ['tesla'], 'BRK.B': ['berkshire'],
           'JPM': ['jpmorgan'], 'GS': ['goldman'], 'DAL': ['delta air'], 'NFLX': ['netflix'], 'DIS': ['disney'], 'WMT': ['walmart'], 'AI': ['c3'],
           'CRM': ['salesforce'], 'PM': ['zyn', 'philip morris'], 'TROW': ['t. rowe', 'rowe price'], 'SCHW': ['schwab'], 'ORCL': ['oracle'],
           'INTC': ['intel'], 'AXP': ['american express', 'amex'], 'T': ['at&t'], 'TMUS': ['t-mobile'], 'ALK': ['alaska airlines'], 'BA': ['boeing'], 'F': ['ford motor'], 'V': ['visa inc'], 'TGT': ['target corp', 'target'], 'SPGI': ['s&p global']}


def name_tokens(name):
    return [x for x in re.findall(r'[a-z0-9]+', (name or '').lower().replace('’', '').replace("'", '').replace('&', ' ').replace('.com', ' ')) if x not in STOP]


def _words(title):
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9&.']*", (title or '').replace('’', "'"))


def _toks(text):
    return re.findall(r'[a-z0-9]+', (text or '').lower().replace('’', '').replace("'", ''))


class Mapper:
    """Site company for a market. In order: a (TICKER) in the title that the title also names; a ticker tag the title names;
    a curated alias; two consecutive words of the company name; one distinctive capitalised name word (not an everyday word)."""

    def __init__(self, cos, name_top=1500):
        self.by_t = {}
        for c in cos:
            for k in {c['ticker'], c['ticker'].replace('-', '.'), c['ticker'].replace('.', '-'), c['ticker'].replace('.', '').replace('-', '')}:
                self.by_t.setdefault(k, c)
        self.tokens = {}
        one, two = {}, {}
        for i, c in enumerate(cos):
            w = name_tokens(c.get('name'))
            self.tokens[c['cik']] = {x for x in w if len(x) >= 3 and x not in AMBIGUOUS} | {a for a in ALIASES.get(c['ticker'], []) if ' ' not in a}
            if i >= name_top or not w:
                continue
            if len(w[0]) >= 4 and w[0] not in AMBIGUOUS and w[0] not in COMMON and not w[0].isdigit():
                one.setdefault(w[0], []).append(c)
            if len(w) > 1 and len(w[0]) >= 3 and len(w[1]) >= 3:
                two.setdefault(w[0] + ' ' + w[1], []).append(c)
        self.one = {k: v[0] for k, v in one.items() if len(v) == 1}
        self.two = {k: v[0] for k, v in two.items() if len(v) == 1}
        self.alias = {}
        for t, al in ALIASES.items():
            if self.by_t.get(t):
                for a in al:
                    self.alias[a] = self.by_t[t]
        self.names = {**self.one, **self.two, **self.alias}

    def ticker(self, t):
        return self.by_t.get((t or '').upper())

    def mentions(self, c, title):
        low = (title or '').lower().replace('’', "'")
        toks = set(_toks(title))
        return bool(self.tokens.get(c['cik'], set()) & toks) or any(' ' in a and a in low for a in ALIASES.get(c['ticker'], []))

    def by_name(self, title):
        low = (title or '').lower().replace('’', "'")
        for a, c in self.alias.items():
            if re.search(rf'(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])', low):
                return c
        words = [x for x in _words(title) if re.sub(r"[^a-z0-9]", '', x.lower().replace("'", '')) not in STOP]
        toks = [re.sub(r"[^a-z0-9]", '', x.lower().replace("'", '')) for x in words]
        for i in range(len(toks) - 1):
            k = toks[i] + ' ' + toks[i + 1]
            if k in self.two:
                return self.two[k]
        for wd, k in zip(words, toks):
            if k in self.one and wd[:1].isupper():
                return self.one[k]
        return None

    def from_text(self, title, tags=()):
        for m in re.finditer(r'\(([A-Z][A-Z.\-]{0,5})\)', title or ''):
            c = self.ticker(m.group(1))
            if not c:
                continue
            before = _words(title[:m.start()])
            prev = before[-1] if before else ''
            rest = title[:m.start()] + ' ' + title[m.end():]
            if self.mentions(c, title) or re.search(rf'(?<![A-Za-z]){re.escape(m.group(1))}(?![A-Za-z])', rest) \
                    or (prev[:1].isupper() and prev[:1] == m.group(1)[:1] and prev.lower().strip("'s") not in COMMON | AMBIGUOUS):
                return c
        for tg in tags or ():
            c = self.ticker(tg)
            if c and self.mentions(c, title):
                return c
        return self.by_name(title)


# ------------------------------------------------------------------ prediction markets
def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def poly_prob(m):
    """Yes probability: bid/ask midpoint when the book is tight, else the last trade / outcome price."""
    bb, ba = _f(m.get('bestBid')), _f(m.get('bestAsk'))
    if bb is not None and ba is not None and 0 <= bb <= ba <= 1 and ba - bb <= 0.15:
        return (bb + ba) / 2
    try:
        op = json.loads(m.get('outcomePrices') or '[]')
        if op:
            return _f(op[0])
    except (ValueError, TypeError):
        pass
    return _f(m.get('lastTradePrice'))


def poly_resolved(m):
    if not m.get('closed'):
        return None
    try:
        op = [float(x) for x in json.loads(m.get('outcomePrices') or '[]')]
    except (ValueError, TypeError):
        return None
    if len(op) >= 2 and max(op) >= 0.99:
        return op[0] >= 0.99
    return None


def strike_of(text):
    """'$170', '170', '$1.25T', '<$2.50T', '$2.50-$3.00T', '>$5T' → (low, high) in units (T/B expanded)."""
    t = (text or '').replace(',', '').replace('–', '-')
    mult = lambda u: {'T': 1e12, 'B': 1e9, 'M': 1e6, 'K': 1e3}.get((u or '').upper(), 1)
    m = re.search(r'\$?(\d+(?:\.\d+)?)\s*([TBMK])?\s*-\s*\$?(\d+(?:\.\d+)?)\s*([TBMK])?', t)
    if m:
        u2 = m.group(4) or m.group(2)
        return float(m.group(1)) * mult(m.group(2) or u2), float(m.group(3)) * mult(u2)
    m = re.search(r'(<|less than|under|below)\s*\$?(\d+(?:\.\d+)?)\s*([TBMK])?', t, re.I)
    if m:
        return None, float(m.group(2)) * mult(m.group(3))
    m = re.search(r'(>|more than|over|above|\+)\s*\$?(\d+(?:\.\d+)?)\s*([TBMK])?|\$?(\d+(?:\.\d+)?)\s*([TBMK])?\s*\+|\$?(\d+(?:\.\d+)?)\s*([TBMK])?\s*or (more|higher|above)', t, re.I)
    if m:
        g = [x for x in m.groups() if x]
        nums = [x for x in g if re.match(r'\d', x)]
        units = [x for x in g if re.match(r'^[TBMK]$', x, re.I)]
        return float(nums[0]) * mult(units[0] if units else None), None
    m = re.search(r'\$?(\d+(?:\.\d+)?)\s*([TBMK])?', t)
    if m:
        v = float(m.group(1)) * mult(m.group(2))
        return v, v
    return None


def isotonic_decreasing(ps):
    """Pool-adjacent-violators: the closest non-increasing sequence (probabilities of 'above K' must fall with K)."""
    blocks = []
    for p in ps:
        blocks.append([p, 1])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            v2, n2 = blocks.pop(); v1, n1 = blocks.pop()
            blocks.append([(v1 * n1 + v2 * n2) / (n1 + n2), n1 + n2])
    out = []
    for v, n in blocks:
        out += [v] * n
    return out


def ladder_stats(points):
    """points: [(K, P(X > K))]. Monotone fit, then the implied 10/25/50/75/90% quantiles by linear interpolation."""
    pts = sorted((k, p) for k, p in points if k is not None and p is not None)
    if len(pts) < 2:
        return None
    ks = [k for k, _ in pts]
    ps = [min(1, max(0, p)) for p in isotonic_decreasing([p for _, p in pts])]

    def q(level):                           # K with P(X > K) = 1 - level
        target = 1 - level
        if ps[0] <= target:
            return {'value': ks[0], 'bound': 'below'}
        if ps[-1] >= target:
            return {'value': ks[-1], 'bound': 'above'}
        for i in range(len(ks) - 1):
            if ps[i] >= target >= ps[i + 1]:
                w = (ps[i] - target) / ((ps[i] - ps[i + 1]) or 1)
                return {'value': ks[i] + w * (ks[i + 1] - ks[i]), 'bound': None}
    return {'strikes': ks, 'p_above': [round(p, 4) for p in ps], 'q10': q(.1), 'q25': q(.25), 'median': q(.5), 'q75': q(.75), 'q90': q(.9)}


def bracket_stats(buckets):
    """buckets: [((low, high), p)] → normalised distribution, then a ladder of P(X > edge)."""
    b = [((lo, hi), p) for (lo, hi), p in buckets if p is not None]
    tot = sum(p for _, p in b)
    if len(b) < 2 or tot <= 0:
        return None
    b = sorted(b, key=lambda x: (x[0][0] if x[0][0] is not None else -1e30))
    edges, cum = [], 0.0
    for (lo, hi), p in b:
        cum += p / tot
        if hi is not None:
            edges.append((hi, max(0.0, 1 - cum)))
    st = ladder_stats(edges)
    if st:
        st['buckets'] = [[lo, hi, round(p / tot, 4)] for (lo, hi), p in b]
        st['overround'] = round(tot, 3)
    return st


def resolved_range(kind, pts):
    """Where the price (or market cap) actually ended, from how a closed ladder / bracket set resolved: (low, high)."""
    if kind == 'above':
        yes = [s[0] for s, _, r in pts if r is True and s[0] is not None]
        no = [s[0] for s, _, r in pts if r is False and s[0] is not None]
        if not yes and not no:
            return None
        return [max(yes) if yes else None, min(no) if no else None]
    won = [s for s, _, r in pts if r is True]
    if len(won) == 1:
        lo, hi = won[0]
        return [lo, hi] if lo != hi else [lo, None]
    return None


def update_price_ledger(root, markets, today):
    """Freeze the last market-implied view of every price / market-cap ladder before its date, then score it once it resolves."""
    p = Path(root) / 'cache' / 'price_ledger.json'
    L = read_json(p, {})
    for m in markets:
        if m.get('source') != 'polymarket' or m['kind'] not in ('above', 'bracket', 'mcap', 'metric'):
            continue
        key = m['url']
        st = m.get('stats') or {}
        if not m['closed'] and st and (m['end'] or '') >= today:
            L[key] = {**L.get(key, {}), 'ticker': m['ticker'], 'cik': m['cik'], 'kind': m['kind'], 'title': m['title'], 'end': m['end'], 'unit': m.get('unit'),
                      'median': (st.get('median') or {}).get('value'), 'q10': (st.get('q10') or {}).get('value'), 'q90': (st.get('q90') or {}).get('value'),
                      'as_of': today}
        elif m['closed'] and key in L and m.get('actual') and not L[key].get('actual'):
            L[key]['actual'] = m['actual']
    write_json(p, L)
    return L


def score_price_ledger(L):
    rows = []
    for key, v in L.items():
        a = v.get('actual')
        if not a or v.get('median') is None:
            continue
        lo, hi = a
        mid = (lo + hi) / 2 if lo is not None and hi is not None else (lo if lo is not None else hi)
        inside = None
        if v.get('q10') is not None and v.get('q90') is not None:
            inside = (hi is None or hi >= v['q10']) and (lo is None or lo <= v['q90'])
        rows.append({**v, 'url': key, 'actual_mid': mid, 'err_pct': (v['median'] / mid - 1) * 100 if mid else None, 'inside80': inside})
    rows.sort(key=lambda r: r['end'], reverse=True)
    errs = [abs(r['err_pct']) for r in rows if r['err_pct'] is not None]
    ins = [r['inside80'] for r in rows if r['inside80'] is not None]
    return {'n': len(rows), 'mean_abs_err_pct': sum(errs) / len(errs) if errs else None, 'inside80': sum(ins) / len(ins) if ins else None, 'rows': rows[:400]}


def poly_scan(h, mapper, verbose=True):
    events, seen = [], set()
    for tag in POLY_TAGS:
        for closed, pages in (('false', 12 if tag == 'earnings' else 6), ('true', 6 if tag == 'earnings' else 2)):
            for pg in range(pages):          # the Gamma API returns at most 100 events a page
                url = f'{GAMMA}/events?tag_slug={tag}&closed={closed}&limit=100&offset={100 * pg}' + ('&order=endDate&ascending=false' if closed == 'true' else '')
                try:
                    ev = h.json(url)
                except Exception as exc:
                    print(f'  polymarket {tag}: {exc}', flush=True); break
                for e in ev:
                    if e.get('id') not in seen:
                        seen.add(e.get('id')); events.append(e)
                if len(ev) < 100:
                    break
    out = []
    for e in events:
        tags = [t.get('slug') for t in e.get('tags') or [] if t.get('slug')]
        title = e.get('title') or ''
        co = mapper.from_text(title, tags)
        ms = e.get('markets') or []
        if not co:                             # "Which companies will be acquired …", "Largest company end of …": one row per company named
            for m in ms:
                g = m.get('groupItemTitle') or ''
                c2 = mapper.from_text(g)
                if c2 and (m.get('active') or e.get('closed')):
                    out.append({'source': 'polymarket', 'kind': 'other', 'ticker': c2['ticker'], 'cik': c2['cik'], 'title': title,
                                'url': f'https://polymarket.com/event/{e.get("slug")}', 'end': (m.get('endDate') or e.get('endDate') or '')[:10],
                                'closed': bool(m.get('closed') or e.get('closed')), 'volume': _f(m.get('volume')),
                                'outcomes': [{'q': g, 'p': poly_prob(m), 'resolved': poly_resolved(m)}]})
            continue
        kind = ('beat' if re.search(r'beat quarterly earnings', title, re.I) else
                'above' if re.search(r'(close[sd]?|finish\w*)\b.*\babove', title, re.I) else
                'bracket' if re.search(r'close[sd]?\b.*\bat _', title, re.I) else
                'hit' if re.search(r'what will .* hit\b', title, re.I) else
                'mcap' if re.search(r'market cap', title, re.I) else
                'updown' if re.search(r'up or down', title, re.I) else
                'metric' if re.search(r'\bQ[1-4]\b|\bfiscal\b|\bFY\d', title) and (re.search(r'above\s*_', title) or re.search(r'growth|ratio|margin|\(MBR\)|RPO', title, re.I)) else 'other')
        base = {'source': 'polymarket', 'kind': kind, 'ticker': co['ticker'], 'cik': co['cik'], 'title': title,
                'url': f'https://polymarket.com/event/{e.get("slug")}', 'end': (e.get('endDate') or '')[:10],
                'closed': bool(e.get('closed')), 'volume': _f(e.get('volume')), 'liquidity': _f(e.get('liquidity'))}
        if kind == 'beat':
            for m in ms:
                slug = m.get('slug') or ''
                mm = re.search(r'-(gaap|nongaap)-eps-(\d{2})-(\d{2})-(\d{4})-(-?[\dpt]+)$', slug)
                strike = float(mm.group(5).replace('pt', '.')) if mm else None
                out.append({**base, 'basis': mm.group(1) if mm else None, 'report_date': f'{mm.group(4)}-{mm.group(2)}-{mm.group(3)}' if mm else None,
                            'eps_strike': strike, 'p': poly_prob(m), 'resolved': poly_resolved(m), 'id': m.get('id'),
                            'token': (json.loads(m.get('clobTokenIds') or '[]') or [None])[0], 'market_end': m.get('endDate'),
                            'volume': _f(m.get('volume'))})
        elif kind in ('above', 'mcap', 'bracket'):
            pts = []
            for m in ms:
                s = strike_of(m.get('groupItemTitle') or m.get('question'))
                if s:
                    pts.append((s, poly_prob(m), poly_resolved(m)))
            if kind == 'above':
                st = ladder_stats([(s[0], p) for s, p, _ in pts if s[0] is not None])
            elif kind == 'bracket':
                st = bracket_stats([((s[0] if s[0] != s[1] else None, s[1]) if s[0] != s[1] else (s[0], None), p) for s, p, _ in pts])
            else:
                st = bracket_stats([((s[0] if s[0] != s[1] else None, s[1]) if s[0] != s[1] else (s[0], None), p) for s, p, _ in pts])
            row = {**base, 'stats': None if e.get('closed') else st, 'n': len(pts)}
            if e.get('closed'):
                row['actual'] = resolved_range(kind, pts)
            if st or row.get('actual'):
                out.append(row)
        elif kind == 'metric':
            pts = []
            for m in ms:
                if m.get('closed') and not e.get('closed'):
                    continue
                g = m.get('groupItemTitle') or ''
                k = strike_of(g)
                if k:
                    pts.append((k, poly_prob(m), poly_resolved(m), g))
            sample = next((g for *_, g in pts if g), '')
            unit = '$' if '$' in sample else '%' if '%' in sample else (re.sub(r'[\d.,<>$+\-–\s]+', ' ', sample).strip()[:12] or '')
            ranged = any(k[0] != k[1] for k, *_ in pts)
            st = (bracket_stats([((k[0] if k[0] != k[1] else None, k[1]) if k[0] != k[1] else (k[0], None), p) for k, p, _, _ in pts]) if ranged
                  else ladder_stats([(k[0], p) for k, p, _, _ in pts]))
            row = {**base, 'stats': None if e.get('closed') else st, 'unit': unit,
                   'outcomes': [{'q': g, 'p': p, 'resolved': r} for k, p, r, g in sorted(pts, key=lambda x: x[0][0] if x[0][0] is not None else -1e30)][:16]}
            if e.get('closed'):
                row['actual'] = resolved_range('above' if not ranged else 'bracket', [(k, p, r) for k, p, r, _ in pts])
            out.append(row)
        elif kind == 'hit':
            up, down = {}, {}
            for m in ms:
                if m.get('closed') and not e.get('closed'):
                    continue                       # a strike already touched / settled inside a live month
                g = m.get('groupItemTitle') or ''
                k = strike_of(g)
                if not k or k[0] is None:
                    continue
                (up if '↑' in g or 'HIGH' in (m.get('question') or '') else down)[k[0]] = poly_prob(m)
            hi = ladder_stats(list(up.items()))                                   # P(month high ≥ K)
            lo = ladder_stats([(k, None if p is None else 1 - p) for k, p in down.items()])   # P(month low > K)
            out.append({**base, 'stats_high': hi, 'stats_low': lo,
                        'outcomes': [{'q': f'high ≥ {k:g}', 'p': p} for k, p in sorted(up.items())] + [{'q': f'low ≤ {k:g}', 'p': p} for k, p in sorted(down.items())]})
        else:
            rows = [{'q': m.get('groupItemTitle') or m.get('question'), 'p': poly_prob(m), 'resolved': poly_resolved(m)} for m in ms[:20]]
            extra = {'p': rows[0]['p'], 'resolved': rows[0]['resolved']} if kind == 'updown' and rows else {}
            out.append({**base, 'outcomes': rows, **extra})
    if verbose:
        print(f'polymarket: {len(events)} events, {len(out)} company markets', flush=True)
    return out


def kalshi_prob(m):
    b, a, l = _f(m.get('yes_bid_dollars')), _f(m.get('yes_ask_dollars')), _f(m.get('last_price_dollars'))
    if b is not None and a is not None and 0 < a and a - b <= 0.15:
        return (a + b) / 2
    return l if l else (b if b else None)


def kalshi_series(h, root, max_age_days=7):
    p = Path(root) / 'cache' / 'kalshi_series.json'
    c = read_json(p, {})
    if c.get('at') and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(c['at'])).days < max_age_days:
        return c['series']
    keep = []
    for cat in ('Companies', 'Financials', 'Mentions'):
        try:
            S = h.json(f'{KALSHI}/series?category={cat}&limit=1000').get('series', [])
        except Exception as exc:
            print(f'  kalshi series {cat}: {exc}', flush=True); continue
        keep += [{k: s.get(k) for k in ('ticker', 'title', 'category', 'tags', 'frequency')} for s in S]
    write_json(p, {'at': now(), 'series': keep})
    return keep


def kalshi_company(series, mapper):
    """(series, company) for series about a site company: the ticker inside the series ticker, else the name."""
    out = []
    for s in series:
        t = s['ticker'] or ''
        core = re.sub(r'^KX', '', t)
        mention = core.startswith('EARNINGSMENTION')
        core = core.replace('EARNINGSMENTION', '')
        co = mapper.ticker(core) or (mapper.ticker(core[:-1]) if len(core) > 2 else None) or (mapper.ticker(core[:-2]) if len(core) > 3 and core[-2:] in ('CC', 'FT', 'KP') else None)
        if co and not mapper.mentions(co, s['title'] or ''):
            co = None                          # KXETH is ether, not Ethan Allen: the title has to name the company
        if not co:
            co = mapper.from_text(re.sub(r'(?i)\b(kpi|annual|quarter|earnings|call|mention|credit card spend|foot traffic|app downloads?)\b', ' ', s['title'] or ''))
        if co and (mention or s.get('category') in ('Companies', 'Financials')):
            out.append((s, co, 'mention' if mention else 'kpi' if re.search(r'KPI|metric', ' '.join((s.get('tags') or [])) + ' ' + (s['title'] or ''), re.I) else 'other'))
    return out


def kalshi_scan(h, root, mapper, minutes=6.0, verbose=True):
    t0 = time.time()
    series = kalshi_series(h, root)
    pairs = kalshi_company(series, mapper)
    out = []
    for s, co, kind in pairs:
        if time.time() - t0 > minutes * 60:
            break
        try:
            ev = h.json(f'{KALSHI}/events?series_ticker={s["ticker"]}&status=open&with_nested_markets=true&limit=50').get('events', [])
        except Exception as exc:
            print(f'  kalshi {s["ticker"]}: {exc}', flush=True); continue
        for e in ev:
            ms = e.get('markets') or []
            kind_e = 'kpi' if kind == 'other' and any(m.get('strike_type') in ('greater', 'greater_or_equal', 'less', 'less_or_equal', 'between') for m in ms) else kind
            base = {'source': 'kalshi', 'kind': kind_e, 'ticker': co['ticker'], 'cik': co['cik'], 'title': e.get('title'), 'subtitle': e.get('sub_title'),
                    'url': f'https://kalshi.com/markets/{s["ticker"].lower()}', 'end': (max((m.get('close_time') or '') for m in ms) if ms else '')[:10],
                    'closed': False, 'volume': sum(_f(m.get('volume_fp')) or 0 for m in ms)}
            if kind_e == 'kpi':
                above, buckets = [], []
                for m in ms:
                    st, lo, hi, p = m.get('strike_type'), _f(m.get('floor_strike')), _f(m.get('cap_strike')), kalshi_prob(m)
                    if st in ('greater', 'greater_or_equal') and lo is not None:
                        above.append((lo, p))
                    elif st in ('less', 'less_or_equal') and hi is not None:
                        above.append((hi, None if p is None else 1 - p))
                    elif st == 'between':
                        buckets.append(((lo, hi), p))
                stats = ladder_stats(above) if len(above) >= 2 else bracket_stats(buckets) if buckets else None
                rows = [{'q': m.get('yes_sub_title') or m.get('subtitle') or m.get('title'), 'p': kalshi_prob(m)} for m in ms[:24]]
                out.append({**base, 'stats': stats, 'outcomes': rows})
            else:
                rows = sorted([{'q': m.get('yes_sub_title') or m.get('title'), 'p': kalshi_prob(m)} for m in ms], key=lambda r: -(r['p'] or 0))[:30]
                out.append({**base, 'outcomes': rows})
    if verbose:
        print(f'kalshi: {len(pairs)} company series, {len(out)} events', flush=True)
    return out


def calibrate_closed(h, root, markets, budget=150):
    """For closed beat markets: the Yes price one day before the market's end (from the CLOB history), kept once."""
    p = Path(root) / 'cache' / 'poly_closed.json'
    c = read_json(p, {})
    new = 0
    for m in markets:
        old = c.get(str(m['id']))
        if m['kind'] != 'beat' or not m.get('closed') or m.get('resolved') is None or not m.get('token') \
                or (old and (old.get('p_day_before') is not None or (old.get('tries') or 1) >= 3)):
            continue
        if new >= budget:
            break
        pre = None
        try:
            end = dt.datetime.fromisoformat((m.get('market_end') or m['end'] + 'T20:00:00Z').replace('Z', '+00:00'))
            if m.get('report_date'):                     # the report comes before the market's end: cut a day before the report
                end = min(end, dt.datetime.fromisoformat(m['report_date'] + 'T12:00:00+00:00'))
            cut = int((end - dt.timedelta(hours=24)).timestamp())
            for q in (f'startTs={cut - 6 * 86400}&endTs={cut}&fidelity=60', 'interval=max&fidelity=60', 'interval=1m&fidelity=60'):
                hist = h.json(f'{CLOB}/prices-history?market={m["token"]}&{q}').get('history', [])
                before = [x for x in hist if x.get('t', 0) <= cut and x.get('p') is not None]
                if before:
                    pre = float(before[-1]['p'])
                    break
        except Exception:
            pre = None
        c[str(m['id'])] = {'ticker': m['ticker'], 'report_date': m.get('report_date'), 'p_day_before': pre, 'yes': m['resolved'],
                           'eps_strike': m.get('eps_strike'), 'basis': m.get('basis'), 'tries': (old.get('tries') or 1) + 1 if old else 1}
        new += 1
    write_json(p, c)
    return c


# ------------------------------------------------------------------ analysts (Yahoo Finance)
def raw(v):
    return v.get('raw') if isinstance(v, dict) else (v if isinstance(v, (int, float)) else None)


def parse_yahoo(body):
    r = (body.get('quoteSummary') or {}).get('result') or []
    if not r:
        return None
    d = r[0]
    out = {'as_of': now()[:10]}
    fd = d.get('financialData') or {}
    out['price'] = raw(fd.get('currentPrice'))
    out['targets'] = {k: raw(fd.get(f'target{k.title()}Price')) for k in ('mean', 'median', 'high', 'low')}
    out['targets']['n'] = raw(fd.get('numberOfAnalystOpinions'))
    out['rating'] = {'mean': raw(fd.get('recommendationMean')), 'key': fd.get('recommendationKey')}
    rt = (d.get('recommendationTrend') or {}).get('trend') or []
    out['rating']['trend'] = [[t.get('period'), t.get('strongBuy'), t.get('buy'), t.get('hold'), t.get('sell'), t.get('strongSell')] for t in rt]
    per = []
    for t in (d.get('earningsTrend') or {}).get('trend') or []:
        e, rv, tr, rvs = t.get('earningsEstimate') or {}, t.get('revenueEstimate') or {}, t.get('epsTrend') or {}, t.get('epsRevisions') or {}
        per.append({'period': t.get('period'), 'end': t.get('endDate'),
                    'eps': {k: raw(e.get(k)) for k in ('avg', 'low', 'high', 'yearAgoEps', 'numberOfAnalysts', 'growth')},
                    'rev': {k: raw(rv.get(k)) for k in ('avg', 'low', 'high', 'yearAgoRevenue', 'numberOfAnalysts', 'growth')},
                    'eps_trend': {k: raw(tr.get(k)) for k in ('current', '7daysAgo', '30daysAgo', '60daysAgo', '90daysAgo')},
                    'revisions': {k: raw(rvs.get(k)) for k in ('upLast7days', 'upLast30days', 'downLast7Days', 'downLast30days')}})
    out['periods'] = [p for p in per if p['period'] in ('0q', '+1q', '0y', '+1y')]
    ce = ((d.get('calendarEvents') or {}).get('earnings') or {})
    ed = ce.get('earningsDate') or []
    out['next_earnings'] = {'date': (ed[0].get('fmt') if ed and isinstance(ed[0], dict) else None), 'estimate': ce.get('isEarningsDateEstimate'),
                            'eps_avg': raw(ce.get('earningsAverage')), 'rev_avg': raw(ce.get('revenueAverage'))}
    hist = {}
    for x in ((d.get('earnings') or {}).get('earningsChart') or {}).get('quarterly') or []:
        q = (x.get('periodEndDate') or {}).get('fmt')
        if q:
            hist[q] = {'quarter': q, 'reported': (x.get('reportedDate') or {}).get('fmt'), 'eps_est': raw(x.get('estimate')), 'eps_act': raw(x.get('actual'))}
    for x in (d.get('earningsHistory') or {}).get('history') or []:
        q = (x.get('quarter') or {}).get('fmt')
        if q:
            hist.setdefault(q, {'quarter': q})
            hist[q].update({k: v for k, v in {'eps_est': raw(x.get('epsEstimate')), 'eps_act': raw(x.get('epsActual'))}.items() if v is not None})
    for v in hist.values():
        if v.get('eps_est') not in (None, 0) and v.get('eps_act') is not None:
            v['surprise'] = (v['eps_act'] - v['eps_est']) / abs(v['eps_est'])
    out['surprises'] = sorted(hist.values(), key=lambda v: v['quarter'])
    rev = []
    for x in ((d.get('earnings') or {}).get('financialsChart') or {}).get('quarterly') or []:
        rev.append({'date': x.get('date'), 'revenue': raw(x.get('revenue')), 'earnings': raw(x.get('earnings'))})
    out['revenue_history'] = rev
    up = (d.get('upgradeDowngradeHistory') or {}).get('history') or []
    out['actions'] = [{'date': dt.datetime.fromtimestamp(x.get('epochGradeDate', 0), dt.timezone.utc).date().isoformat(), 'firm': x.get('firm'),
                       'to': x.get('toGrade'), 'from': x.get('fromGrade'), 'action': x.get('action'), 'target': x.get('currentPriceTarget') or None,
                       'prior': x.get('priorPriceTarget') or None, 'target_action': x.get('priceTargetAction')} for x in up[:15]]
    ks = d.get('defaultKeyStatistics') or {}
    out['shares'] = raw(ks.get('impliedSharesOutstanding')) or raw(ks.get('sharesOutstanding'))
    return out


def yahoo_crumb(h):
    err = None
    for cookie_url, crumb_url in (('https://fc.yahoo.com', f'{YQ}/v1/test/getcrumb'),
                                  ('https://finance.yahoo.com/', 'https://query1.finance.yahoo.com/v1/test/getcrumb')):
        try:
            h.get(cookie_url, tries=1)
        except Exception:
            pass                                          # a 404 that still sets the cookie
        try:
            c = h.get(crumb_url).decode().strip()
            if c and '<' not in c and len(c) < 40:
                return c
            err = f'bad crumb {c[:40]!r}'
        except Exception as exc:
            err = str(exc)
    raise RuntimeError(err or 'no crumb')


def collect_analysts(h, root, cos, minutes=20.0, refresh_hours=20):
    root = Path(root); t0 = time.time()
    st = read_json(root / 'state.json', {}) or {}
    S = st.setdefault('analysts', {})
    try:
        crumb = yahoo_crumb(h)
    except Exception as exc:
        print('::warning::yahoo crumb failed:', exc, flush=True)
        st['analysts_summary'] = {**(st.get('analysts_summary') or {}), 'companies': len(cos), 'this_run': 0, 'error': f'crumb: {exc}', 'at': now()}
        write_json(root / 'state.json', st)
        return st['analysts_summary']
    nowdt = dt.datetime.now(dt.timezone.utc)

    def due(c):
        s = S.get(str(c['cik'])) or {}
        if s.get('retry_after') and s['retry_after'] > now():
            return None
        if not s.get('at'):
            return (0, -(c['revenue'] or 0))
        age = (nowdt - dt.datetime.fromisoformat(s['at'])).total_seconds() / 3600
        return (1, -age) if age >= refresh_hours else None

    keyed = [(due(c), c) for c in cos]
    order = [c for d, c in sorted([x for x in keyed if x[0] is not None], key=lambda x: x[0])]
    done = errs = 0
    for c in order:
        if time.time() - t0 > minutes * 60:
            break
        s = S.setdefault(str(c['cik']), {})
        sym = c['ticker'].replace('.', '-')
        try:
            body = h.json(f'{YQ}/v10/finance/quoteSummary/{urllib.parse.quote(sym)}?modules={YAHOO_MODULES}&crumb={urllib.parse.quote(crumb)}')
            a = parse_yahoo(body)
            p = root / 'companies' / f'{c["cik"]}.json'
            rec = read_json(p, {}) or {}
            rec.update({'cik': c['cik'], 'ticker': c['ticker'], 'name': c.get('name'), 'sector': c.get('sector')})
            if a:
                rec['analysts'] = a
                snaps = rec.setdefault('snapshots', {})
                q0 = next((x for x in a['periods'] if x['period'] == '0q'), {})
                y0 = next((x for x in a['periods'] if x['period'] == '0y'), {})
                snaps[a['as_of']] = [q0.get('end'), (q0.get('eps') or {}).get('avg'), (q0.get('rev') or {}).get('avg'), (y0.get('eps') or {}).get('avg'),
                                     (y0.get('rev') or {}).get('avg'), a['targets'].get('mean'), a['rating'].get('mean'), a.get('price')]
                for k in sorted(snaps)[:-500]:
                    snaps.pop(k)
                old = {v['quarter']: v for v in rec.get('surprises_all', [])}
                for v in a['surprises']:
                    old[v['quarter']] = {**old.get(v['quarter'], {}), **v}
                rec['surprises_all'] = sorted(old.values(), key=lambda v: v['quarter'])
            write_json(p, rec)
            s.update(at=now(), fails=0, error=None, retry_after=None)
            done += 1
        except Exception as exc:
            errs += 1
            s['fails'] = (s.get('fails') or 0) + 1
            s['error'] = str(exc)[:160]
            s['retry_after'] = (nowdt + dt.timedelta(hours=min(72, 6 * 2 ** s['fails']))).isoformat(timespec='seconds')
            if 'HTTP 401' in str(exc) or 'HTTP 403' in str(exc):
                try:
                    crumb = yahoo_crumb(h)
                except Exception:
                    break
        if done % 50 == 0:
            write_json(root / 'state.json', st)
    st['analysts_summary'] = {'companies': len(cos), 'on_file': sum(1 for c in cos if (S.get(str(c['cik'])) or {}).get('at')), 'this_run': done,
                              'errors': errs, 'at': now()}
    write_json(root / 'state.json', st)
    return st['analysts_summary']


def collect(root, site_index, minutes=25.0):
    root = Path(root)
    cos = universe(site_index)
    mapper = Mapper(cos)
    h = Http({'gamma-api.polymarket.com': 0.25, 'clob.polymarket.com': 0.25, 'api.elections.kalshi.com': 0.2, 'query2.finance.yahoo.com': 0.7,
              'fc.yahoo.com': 0.5})
    t0 = time.time()
    poly = poly_scan(h, mapper)
    kal = kalshi_scan(h, root, mapper, minutes=6)
    cal = calibrate_closed(h, root, poly)
    hist_path = root / 'cache' / 'market_history.json'
    hist = read_json(hist_path, {})                     # daily snapshot of every company's market-implied figures
    today = now()[:10]
    for m in poly + kal:
        key = f'{m["source"]}:{m["kind"]}:{m["ticker"]}:{m["end"]}:{m.get("eps_strike") or ""}'
        val = m.get('p') if m['kind'] == 'beat' else ((m.get('stats') or {}).get('median') or {}).get('value')
        if val is not None and not m.get('closed'):
            hist.setdefault(key, {})[today] = round(val, 4)
    for k in list(hist):
        if len(hist[k]) > 400:
            hist[k] = dict(sorted(hist[k].items())[-400:])
    write_json(hist_path, hist)
    write_json(root / 'cache' / 'markets_now.json', {'at': now(), 'markets': poly + kal})
    update_price_ledger(root, poly, today)
    left = max(3.0, minutes - (time.time() - t0) / 60)
    an = collect_analysts(h, root, cos, minutes=left)
    return {'polymarket': len(poly), 'kalshi': len(kal), 'calibration_markets': len(cal), 'analysts': an, 'requests': h.calls}


# ------------------------------------------------------------------ build
def cal_end(c):
    if c.startswith('CY'):
        y, q = int(c[2:6]), int(c[-1]); m = 3 * q
    else:
        y, m = int(c[:4]), int(c[5:7])
    return (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()


def our_forecasts(rot):
    """{ticker: [{horizon, date, price, lo80, hi80, model}]} from the rotation history's live forecasts."""
    out = {}
    if not rot:
        return out
    for name, label in (('chaos-forecast.json', 'next quarter'), ('chaos-forecast-monthly.json', 'next month')):
        d = read_json(Path(rot) / name, None)
        if not d:
            continue
        live = len(d['origins']) - 1
        for t, rows in (d.get('companies') or {}).items():
            r = next((r for r in rows if r[0] == live), None)
            if r and r[5] is not None:
                out.setdefault(t, []).append({'horizon': label, 'date': cal_end(d['targets'][live]), 'from': cal_end(d['origins'][live]),
                                              'price': r[5], 'lo80': r[6], 'hi80': r[7], 'close_then': r[4],
                                              'model': 'gravity + tidal' if (len(r) > 8 and r[8] == 1) else 'analogues'})
    return out


def prices(rot, ticker, weeks=110):
    if not rot:
        return []
    p = Path(rot) / 't' / f'{ticker.replace(".", "-")}.json'
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding='utf-8'))
    s = dt.date.fromisoformat(d['start'])
    pts = [((s + dt.timedelta(days=7 * i)).isoformat(), v) for i, v in enumerate(d['c']) if v is not None]
    return pts[-weeks:]


def implied_price(m, shares):
    st = m.get('stats') or {}
    if m['kind'] in ('above', 'bracket'):
        return {k: (st.get(k) or {}).get('value') for k in ('q10', 'q25', 'median', 'q75', 'q90')}, {k: (st.get(k) or {}).get('bound') for k in ('q10', 'median', 'q90')}
    if m['kind'] == 'mcap' and shares:
        return {k: ((st.get(k) or {}).get('value') or 0) / shares if (st.get(k) or {}).get('value') else None for k in ('q10', 'q25', 'median', 'q75', 'q90')}, {k: (st.get(k) or {}).get('bound') for k in ('q10', 'median', 'q90')}
    return None, None


def build(root, rot=None, verbose=True):
    root = Path(root); pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    mk = read_json(root / 'cache' / 'markets_now.json', {}).get('markets', [])
    mhist = read_json(root / 'cache' / 'market_history.json', {})
    calib = read_json(root / 'cache' / 'poly_closed.json', {})
    ours = our_forecasts(rot)
    pledger = score_price_ledger(read_json(root / 'cache' / 'price_ledger.json', {}))
    by_t = {}
    for m in mk:
        by_t.setdefault(m['ticker'], []).append(m)
    recs = {}
    for p in (root / 'companies').glob('*.json'):
        r = read_json(p, {})
        if r.get('ticker'):
            recs[r['ticker']] = r
    for t, ms in by_t.items():                           # companies with markets but no analyst record yet
        if t not in recs:
            recs[t] = {'cik': ms[0]['cik'], 'ticker': t}
    index, cal_rows = [], []
    today = dt.date.today().isoformat()
    yday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    for t, rec in recs.items():
        a = rec.get('analysts') or {}
        cutoff = (dt.date.today() - dt.timedelta(days=120)).isoformat()
        live = sorted([m for m in by_t.get(t, []) if is_live(m, yday)], key=lambda m: m['end'] or '9999')
        done = sorted([m for m in by_t.get(t, []) if not is_live(m, yday) and (m['end'] or '') >= cutoff], key=lambda m: m['end'] or '', reverse=True)
        ms = live + done
        shares = a.get('shares')
        for m in ms:
            key = f'{m["source"]}:{m["kind"]}:{m["ticker"]}:{m["end"]}:{m.get("eps_strike") or ""}'
            m['history'] = sorted(mhist.get(key, {}).items())[-120:]
            ip, bounds = implied_price(m, shares)
            if ip:
                m['implied_price'], m['implied_bounds'] = ip, bounds
        beat = next((m for m in ms if m['kind'] == 'beat' and not m['closed'] and (m.get('report_date') or '9999') >= today), None)
        price_mkts = [m for m in ms if m.get('implied_price') and not m['closed'] and (m['end'] or '') >= today]
        soon = (dt.date.today() + dt.timedelta(days=5)).isoformat()
        pm_price = (min(price_mkts, key=lambda m: (m['end'] < soon, m['kind'] != 'above', m['end'])) if price_mkts else None)
        q0 = next((x for x in a.get('periods', []) if x['period'] == '0q'), {})
        tr = q0.get('eps_trend') or {}
        rev30 = (tr['current'] / tr['30daysAgo'] - 1) if tr.get('current') is not None and tr.get('30daysAgo') not in (None, 0) else None
        surp = rec.get('surprises_all') or a.get('surprises') or []
        beats = [s for s in surp if s.get('surprise') is not None][-8:]
        beat_rate = sum(1 for s in beats if s['surprise'] > 0) / len(beats) if beats else None
        ourf = ours.get(t) or ours.get(t.replace('.', '-')) or []
        px = prices(rot, t)
        doc = {'cik': rec.get('cik'), 'ticker': t, 'name': rec.get('name'), 'sector': rec.get('sector'), 'generated_at': now(),
               'analysts': a, 'snapshot_fields': ['quarter_end', 'eps_q', 'rev_q', 'eps_y', 'rev_y', 'target_mean', 'rating_mean', 'price'],
               'snapshots': sorted((rec.get('snapshots') or {}).items())[-400:], 'surprises': surp[-24:], 'beat_rate': beat_rate,
               'markets': ms[:60], 'ours': ourf, 'prices': px,
               'calibration': [v for v in calib.values() if v.get('ticker') == t][-12:],
               'price_track': [r for r in pledger['rows'] if r['ticker'] == t][:24]}
        if rec.get('cik'):
            write_json(pub / 'c' / f'{rec["cik"]}.json', _clean(doc))
        nxt = a.get('next_earnings') or {}
        index.append([rec.get('cik'), t, rec.get('name'), rec.get('sector'), a.get('price') or (px[-1][1] if px else None),
                      nxt.get('date'), _r((q0.get('eps') or {}).get('avg'), 4), (q0.get('eps') or {}).get('numberOfAnalysts'), _r((q0.get('rev') or {}).get('avg')),
                      _r(rev30, 4), _r((a.get('targets') or {}).get('mean'), 2), _r((a.get('rating') or {}).get('mean'), 2),
                      _r(beat['p'], 3) if beat else None, beat.get('eps_strike') if beat else None, beat.get('report_date') if beat else None,
                      _r((pm_price or {}).get('implied_price', {}).get('median'), 2) if pm_price else None, pm_price['end'] if pm_price else None,
                      _r(ourf[0]['price'], 2) if ourf else None, ourf[0]['date'] if ourf else None, _r(beat_rate, 2),
                      len([m for m in ms if m['source'] == 'polymarket' and not m['closed']]), len([m for m in ms if m['source'] == 'kalshi'])])
        if nxt.get('date') and today <= nxt['date'] <= (dt.date.today() + dt.timedelta(days=45)).isoformat():
            cal_rows.append({'date': nxt['date'], 'ticker': t, 'cik': rec.get('cik'), 'name': rec.get('name'), 'eps': (q0.get('eps') or {}).get('avg'),
                             'eps_low': (q0.get('eps') or {}).get('low'), 'eps_high': (q0.get('eps') or {}).get('high'), 'n': (q0.get('eps') or {}).get('numberOfAnalysts'),
                             'rev': (q0.get('rev') or {}).get('avg'), 'eps_rev_30d': rev30, 'beat_prob': beat['p'] if beat else None,
                             'pm_strike': beat.get('eps_strike') if beat else None, 'beat_rate': beat_rate, 'estimated_date': nxt.get('estimate')})
    write_json(pub / 'index.json', {'generated_at': now(), 'fields': ['cik', 'ticker', 'name', 'sector', 'price', 'next_earnings', 'eps_q', 'eps_q_n', 'rev_q',
                                                                    'eps_rev_30d', 'target_mean', 'rating_mean', 'pm_beat_prob', 'pm_eps_strike', 'pm_report_date',
                                                                    'pm_implied_price', 'pm_price_date', 'our_price', 'our_date', 'beat_rate', 'poly_markets', 'kalshi_events'],
                                    'rows': [_clean(r) for r in index]})
    write_json(pub / 'calendar.json', {'generated_at': now(), 'rows': _clean(sorted(cal_rows, key=lambda r: (r['date'], r['ticker'])))})
    recent = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    write_json(pub / 'markets.json', {'generated_at': now(), 'rows': _clean([{k: m.get(k) for k in ('source', 'kind', 'ticker', 'cik', 'title', 'subtitle', 'url', 'end', 'closed',
                                                                                                     'volume', 'p', 'eps_strike', 'report_date', 'basis', 'resolved', 'n', 'implied_price', 'implied_bounds', 'unit')}
                                                                           | {'median': ((m.get('stats') or {}).get('median') or {}).get('value'),
                                                                              'top': (m.get('outcomes') or [])[:3],
                                                                              'high': ((m.get('stats_high') or {}).get('median') or {}).get('value'),
                                                                              'low': ((m.get('stats_low') or {}).get('median') or {}).get('value')}
                                                                           for m in mk if is_live(m, yday) or (m['end'] or '') >= recent])})
    write_json(pub / 'calibration.json', _clean({**calibration(calib), 'price': {k: v for k, v in pledger.items() if k != 'rows'},
                                                'price_rows': pledger['rows'][:150]}))
    st = read_json(root / 'state.json', {})
    write_json(pub / 'status.json', {'built_at': now(), 'companies': len(index), 'markets': len(mk), 'calendar': len(cal_rows),
                                     'analysts': st.get('analysts_summary')})
    if verbose:
        print(f'consensus build: {len(index)} companies, {len(mk)} markets, {len(cal_rows)} upcoming reports', flush=True)
    return {'companies': len(index), 'markets': len(mk)}


def is_live(m, yday):
    """Open and not past its date (a market waiting for resolution after its date counts as done)."""
    return not m['closed'] and (not m.get('end') or m['end'] >= yday)


def calibration(c):
    rows = [v for v in c.values() if v.get('p_day_before') is not None and v.get('yes') is not None]
    if not rows:
        return {'n': 0}
    brier = sum((v['p_day_before'] - (1 if v['yes'] else 0)) ** 2 for v in rows) / len(rows)
    base = sum(1 for v in rows if v['yes']) / len(rows)
    bins = []
    for lo in [0, .1, .2, .3, .4, .5, .6, .7, .8, .9]:
        b = [v for v in rows if lo <= v['p_day_before'] < lo + .1 or (lo == .9 and v['p_day_before'] == 1)]
        if b:
            bins.append([round(lo + .05, 2), round(sum(v['p_day_before'] for v in b) / len(b), 3), round(sum(1 for v in b if v['yes']) / len(b), 3), len(b)])
    hits = sum(1 for v in rows if (v['p_day_before'] >= .5) == v['yes']) / len(rows)
    return {'n': len(rows), 'brier': brier, 'brier_base_rate': base * (1 - base), 'base_rate': base, 'hit_rate': hits, 'bins': bins,
            'note': 'Polymarket "beat quarterly earnings" markets: the Yes price 24 hours before the market closed vs the result. '
                    'A forecast that always said the base rate would score the base-rate Brier.'}


def _r(v, d=0):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return round(v, d) if d else round(v)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 6)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['collect', 'build'])
    ap.add_argument('--root', default='cons')
    ap.add_argument('--site-index', default=None)
    ap.add_argument('--minutes', type=float, default=25)
    ap.add_argument('--rotation', default=None, help='public/ of the rotation-history branch (our forecasts, weekly closes)')
    a = ap.parse_args()
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.site_index, a.minutes)), flush=True)
    else:
        print(json.dumps(build(a.root, a.rotation)), flush=True)


if __name__ == '__main__':
    main()
