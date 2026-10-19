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
    indices   the market itself — S&P 500, Nasdaq-100, Dow, Russell 2000, VIX: every Polymarket market whose title names
              the index (or SPY / QQQ / DIA / IWM) and Kalshi's index series (daily / weekly / monthly / yearly ranges,
              above-below, yearly highs and lows, up for the day or the year, comparisons); daily closes of each index and
              its ETF (Yahoo chart API); the members (iShares IVV / IWM holdings, Nasdaq's Nasdaq-100 list, Wikipedia).
  build     public/: index.json, c/<cik>.json (company page), markets.json, calendar.json, calibration.json — with our
            own forecast (rotation history: the gravity model's next-quarter and next-month price and 80% range) beside
            the analysts and the markets; market.json and ix/<id>.json for the indices: the analysts' consensus added up
            from the members at their weights (target return, earnings growth, forward P/E, revisions, the season), the
            markets' implied levels and our model added up from the members.

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
POLY_TAGS = ['earnings', 'stocks', 'equities', 'big-tech', 'tech', 'business', 'finance', 'ipos', 'market-cap', 'companies', 'indicies', 'sp-500']
# The market: the indices, with the ETF that tracks each (Polymarket quotes some ladders in ETF dollars), how prediction-market
# titles and Kalshi series name them, and how the index weighs its companies (for the bottom-up analysts' consensus and our model).
INDICES = [
    {'id': 'spx', 'name': 'S&P 500', 'short': 'SPX', 'symbol': '^GSPC', 'etf': 'SPY', 'weighting': 'cap',
     'pat': r'S&P\s?500|\bSPX\b|\bSPY\b', 'etf_pat': r'\bSPY\b', 'kalshi': ('INX',)},
    {'id': 'ndx', 'name': 'Nasdaq-100', 'short': 'NDX', 'symbol': '^NDX', 'etf': 'QQQ', 'weighting': 'cap',
     'pat': r'Nasdaq[- ]?100|\bNDX\b|\bQQQ\b|Nasdaq Composite', 'etf_pat': r'\bQQQ\b', 'kalshi': ('NASDAQ100', 'NASDAQ', 'NDX')},
    {'id': 'dji', 'name': 'Dow Jones Industrial Average', 'short': 'DJIA', 'symbol': '^DJI', 'etf': 'DIA', 'weighting': 'price',
     'pat': r'Dow Jones|\bDJIA\b|\bDJI\b', 'etf_pat': r'\bDIA\b', 'kalshi': ('DJIA',)},
    {'id': 'rut', 'name': 'Russell 2000', 'short': 'RUT', 'symbol': '^RUT', 'etf': 'IWM', 'weighting': 'cap',
     'pat': r'Russell\s?2000|\bRUT\b|\bIWM\b', 'etf_pat': r'\bIWM\b', 'kalshi': ('RUT',)},
    {'id': 'vix', 'name': 'Cboe Volatility Index (VIX)', 'short': 'VIX', 'symbol': '^VIX', 'etf': None, 'weighting': None,
     'pat': r'\bVIX\b', 'etf_pat': None, 'kalshi': ('VIX',)},
]
DOW_FALLBACK = 'AAPL AMGN AMZN AXP BA CAT CRM CSCO CVX DIS GS HD HON IBM JNJ JPM KO MCD MMM MRK MSFT NKE NVDA PG SHW TRV UNH V VZ WMT'.split()
ISHARES = {'spx': 'https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund',
           'rut': 'https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund'}
WIKI = {'spx': 'List_of_S&P_500_companies', 'ndx': 'Nasdaq-100', 'dji': 'Dow_Jones_Industrial_Average'}
MEMBERS_OK = {'spx': (480, 520), 'ndx': (95, 110), 'dji': (28, 32), 'rut': (1500, 2100)}
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
                ua = BROWSER_UA if any(d in (host or '') for d in ('yahoo.com', 'nasdaq.com', 'ishares.com')) else UA
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
    """'$170', '$1.25T', '<$2.50T', '$2.50-$3.00T', '>$5T', '71% to 73%', '77%+', '-2% to 0%' → (low, high), T/B/M/K expanded."""
    t = (text or '').replace(',', '').replace('–', '-').replace('−', '-').replace('%', '')
    t = re.sub(r'\s+to\s+', '~', t)
    mult = lambda u: {'T': 1e12, 'B': 1e9, 'M': 1e6, 'K': 1e3}.get((u or '').upper(), 1)
    N = r'(-?\d+(?:\.\d+)?)'
    m = re.search(rf'\$?{N}\s*([TBMK])?\s*[~]\s*\$?{N}\s*([TBMK])?', t) or re.search(rf'\$?(\d+(?:\.\d+)?)\s*([TBMK])?\s*-\s*\$?(\d+(?:\.\d+)?)\s*([TBMK])?', t)
    if m:
        u2 = m.group(4) or m.group(2)
        return float(m.group(1)) * mult(m.group(2) or u2), float(m.group(3)) * mult(u2)
    m = re.search(rf'(<|less than|under|below)\s*\$?{N}\s*([TBMK])?', t, re.I)
    if m:
        return None, float(m.group(2)) * mult(m.group(3))
    m = re.search(rf'(>|more than|over|above|\+)\s*\$?{N}\s*([TBMK])?|\$?{N}\s*([TBMK])?\s*\+|\$?{N}\s*([TBMK])?\s*or (more|higher|above)', t, re.I)
    if m:
        g = [x for x in m.groups() if x]
        nums = [x for x in g if re.match(r'-?\d', x)]
        units = [x for x in g if re.match(r'^[TBMK]$', x, re.I)]
        return float(nums[0]) * mult(units[0] if units else None), None
    m = re.search(rf'\$?{N}\s*([TBMK])?', t)
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


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _lognormal_fit(ks, ps):
    """(mu, sigma) of the log-normal whose P(X > K) is closest to the ladder (probit regression on the strikes the market
    is not sure about), else None."""
    from statistics import NormalDist
    pts = [(math.log(k), NormalDist().inv_cdf(p)) for k, p in zip(ks, ps) if k and k > 0 and 0.02 < p < 0.98]
    if len(pts) >= 2:
        n = len(pts); mx = sum(x for x, _ in pts) / n; my = sum(y for _, y in pts) / n
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        if sxx > 0:
            b = sum((x - mx) * (y - my) for x, y in pts) / sxx
            if b < 0:
                sig = -1 / b
                return my * sig + mx, sig                          # y = (mu − ln K) / sigma
    if len(pts) == 1 and len(ks) >= 2 and ks[0] > 0:               # one uncertain strike: the ladder's span as ±2 sigma
        sig = max(math.log(ks[-1] / ks[0]) / 4, 0.002)
        x, y = pts[0]
        return x + y * sig, sig
    return None


def ladder_mean(ks, ps):
    """Expected value of a fitted ladder (ps = P(X > K) falling with K): the mass between two strikes at their middle,
    the tails below the first and above the last strike at the conditional means of the log-normal fitted to the ladder
    (or half a strike step out when no fit). Returns (mean, the share of the mass in the two tails)."""
    if len(ks) < 2:
        return None, None
    lo_mass, hi_mass = 1 - ps[0], ps[-1]
    step = (ks[-1] - ks[0]) / (len(ks) - 1)
    fit = _lognormal_fit(ks, ps)
    if fit and not (0 < fit[1] <= 2.5 and fit[0] + fit[1] ** 2 / 2 < 700):
        fit = None                                         # a flat or odd ladder: no believable log-normal tail
    below, above = ks[0] - step / 2, max(ks[-1] + step / 2, ks[-1])
    if fit:
        mu, sg = fit
        m = math.exp(mu + sg * sg / 2)
        if ks[0] > 0:
            z = (math.log(ks[0]) - mu) / sg
            d = _ncdf(z)
            if d > 1e-9:
                below = min(ks[0], max(0.0, m * _ncdf(z - sg) / d))
        z = (math.log(ks[-1]) - mu) / sg if ks[-1] > 0 else -1e9
        d = 1 - _ncdf(z)
        if d > 1e-9:
            above = max(ks[-1], min(m * (1 - _ncdf(z - sg)) / d, ks[-1] + 6 * step if step > 0 else ks[-1] * 1.5))
    mean = lo_mass * below + hi_mass * above
    for i in range(len(ks) - 1):
        mean += max(0.0, ps[i] - ps[i + 1]) * (ks[i] + ks[i + 1]) / 2
    return mean, lo_mass + hi_mass


def ladder_stats(points):
    """points: [(K, P(X > K))]. Monotone fit, then the implied 10/25/50/75/90% quantiles by linear interpolation and the
    expected value (ladder_mean)."""
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
    mean, tails = ladder_mean(ks, ps)
    return {'strikes': ks, 'p_above': [round(p, 4) for p in ps], 'q10': q(.1), 'q25': q(.25), 'median': q(.5), 'q75': q(.75), 'q90': q(.9),
            'mean': {'value': mean, 'tails': round(tails, 4)} if mean is not None else None}


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


def index_of(title):
    """The index a market is about (its title names it), else None. Comparisons go to the first index named."""
    hits = [(m.start(), ix) for ix in INDICES for m in [re.search(ix['pat'], title or '', re.I if ix['id'] != 'vix' else 0)] if m]
    return min(hits, key=lambda x: x[0])[1] if hits else None


def poly_kind(title):
    return ('beat' if re.search(r'beat quarterly earnings', title, re.I) else
            'above' if re.search(r'(close[sd]?|finish\w*)\b.*\babove', title, re.I) else
            'bracket' if re.search(r'close[sd]?\b.*\bat _|\bclose[sd]? at\b', title, re.I) else
            'hit' if re.search(r'what will .* hit\b', title, re.I) else
            'mcap' if re.search(r'market cap', title, re.I) else
            'updown' if re.search(r'up or down', title, re.I) else
            'metric' if re.search(r'\bQ[1-4]\b|\bfiscal\b|\bFY\d', title) and (re.search(r'above\s*_', title) or re.search(r'growth|ratio|margin|\(MBR\)|RPO', title, re.I)) else 'other')


def poly_ladder(kind, pts):
    """pts: [((low, high), P(yes))] of one event's contracts → the implied distribution: "above K" contracts as a ladder,
    brackets ('<$320', '$320-$325', '>$365') and market caps as buckets."""
    if kind == 'above':
        return ladder_stats([(s[0], p) for s, p in pts if s[0] is not None])
    return bracket_stats([((s[0] if s[0] != s[1] else None, s[1]) if s[0] != s[1] else (s[0], None), p) for s, p in pts])


NOT_A_COMPANY = re.compile(r'\b(crude oil|natural gas|gasoline|heating oil)\b|\b(gold|silver|copper|platinum) \((GC|SI|HG|PL|XAU|XAG)\)', re.I)


def poly_rows(e, base, title, ms):
    """Rows of one Polymarket event about a company or an index (base: source, ticker, url …), by the kind of market."""
    rows = []
    kind = base['kind']
    if kind == 'beat':
        for m in ms:
            slug = m.get('slug') or ''
            mm = re.search(r'-(gaap|nongaap)-eps-(\d{2})-(\d{2})-(\d{4})-(-?[\dpt]+)$', slug)
            strike = float(mm.group(5).replace('pt', '.')) if mm else None
            rows.append({**base, 'basis': mm.group(1) if mm else None, 'report_date': f'{mm.group(4)}-{mm.group(2)}-{mm.group(3)}' if mm else None,
                        'eps_strike': strike, 'p': poly_prob(m), 'resolved': poly_resolved(m), 'id': m.get('id'),
                        'token': (json.loads(m.get('clobTokenIds') or '[]') or [None])[0], 'market_end': m.get('endDate'),
                        'volume': _f(m.get('volume'))})
    elif kind in ('above', 'mcap', 'bracket'):
        pts, legs = [], []
        for m in ms:
            s = strike_of(m.get('groupItemTitle') or m.get('question'))
            if s:
                pts.append((s, poly_prob(m), poly_resolved(m)))
                legs.append([s[0], s[1], (json.loads(m.get('clobTokenIds') or '[]') or [None])[0]])
        st = poly_ladder(kind, [(s, p) for s, p, _ in pts])
        row = {**base, 'stats': None if e.get('closed') else st, 'n': len(pts)}
        if kind in ('above', 'bracket'):
            row['legs'] = legs                 # the strikes' CLOB tokens: the hourly history of a ladder (app/ladders.py)
        if e.get('closed'):
            row['actual'] = resolved_range(kind, pts)
        if st or row.get('actual'):
            rows.append(row)
        elif ms:                               # a single "above K?" contract: show it as it is
            rows.append({**base, 'kind': 'other', 'outcomes': [{'q': m.get('groupItemTitle') or m.get('question'), 'p': poly_prob(m), 'resolved': poly_resolved(m)} for m in ms[:12]]})
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
        rows.append(row)
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
        rows.append({**base, 'stats_high': hi, 'stats_low': lo,
                    'outcomes': [{'q': f'high ≥ {k:g}', 'p': p} for k, p in sorted(up.items())] + [{'q': f'low ≤ {k:g}', 'p': p} for k, p in sorted(down.items())]})
    else:
        outc = [{'q': m.get('groupItemTitle') or m.get('question'), 'p': poly_prob(m), 'resolved': poly_resolved(m)} for m in ms[:20]]
        extra = {'p': outc[0]['p'], 'resolved': outc[0]['resolved']} if kind == 'updown' and outc else {}
        rows.append({**base, 'outcomes': outc, **extra})
    return rows


def poly_scan(h, mapper, verbose=True, closed_pages=None):
    events, seen = [], set()
    for tag in POLY_TAGS:
        for closed, pages in (('false', 12 if tag == 'earnings' else 6),
                              ('true', closed_pages if closed_pages is not None else 6 if tag == 'earnings' else 2)):
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
        ms = e.get('markets') or []
        ix = index_of(title)
        if ix:                                 # the market itself: S&P 500, Nasdaq-100, Dow, Russell 2000, VIX
            kind = poly_kind(title)
            kind = 'other' if kind in ('beat', 'mcap', 'metric') else kind
            etf = bool(ix['etf_pat'] and re.search(ix['etf_pat'], title)) and not re.search(rf'\({ix["short"]}\)', title)
            base = {'source': 'polymarket', 'kind': kind, 'ticker': ix['short'], 'cik': None, 'index': ix['id'], 'points': not etf,
                    'underlying': ix['etf'] if etf else ix['short'], 'title': title, 'url': f'https://polymarket.com/event/{e.get("slug")}',
                    'end': (e.get('endDate') or '')[:10], 'closed': bool(e.get('closed')), 'volume': _f(e.get('volume')), 'liquidity': _f(e.get('liquidity'))}
            out += poly_rows(e, base, title, ms)
            continue
        if NOT_A_COMPANY.search(title):        # "WTI Crude Oil (WTI) closes above …" is oil, not W&T Offshore
            continue
        co = mapper.from_text(title, tags)
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
        kind = poly_kind(title)
        base = {'source': 'polymarket', 'kind': kind, 'ticker': co['ticker'], 'cik': co['cik'], 'title': title,
                'url': f'https://polymarket.com/event/{e.get("slug")}', 'end': (e.get('endDate') or '')[:10],
                'closed': bool(e.get('closed')), 'volume': _f(e.get('volume')), 'liquidity': _f(e.get('liquidity'))}
        out += poly_rows(e, base, title, ms)
    if verbose:
        print(f'polymarket: {len(events)} events, {sum(1 for r in out if not r.get("index"))} company markets, '
              f'{sum(1 for r in out if r.get("index"))} index markets', flush=True)
    return out


def kalshi_prob(m):
    b, a, l = _f(m.get('yes_bid_dollars')), _f(m.get('yes_ask_dollars')), _f(m.get('last_price_dollars'))
    if b is not None and a is not None and 0 < a and a - b <= 0.15:
        return (a + b) / 2
    return l if l else (b if b else None)


def kalshi_dist(ms):
    """Implied distribution of a Kalshi event: range buckets (with the open-ended tails as buckets) or an above/below ladder."""
    above, buckets = [], []
    for m in ms:
        st, lo, hi, p = m.get('strike_type'), _f(m.get('floor_strike')), _f(m.get('cap_strike')), kalshi_prob(m)
        if st == 'between' and lo is not None and hi is not None:
            buckets.append(((lo, hi), p))
        elif st in ('greater', 'greater_or_equal') and lo is not None:
            above.append((lo, p)); buckets.append(((lo, None), p))
        elif st in ('less', 'less_or_equal') and hi is not None:
            above.append((hi, None if p is None else 1 - p)); buckets.append(((None, hi), p))
    if any(lo is not None and hi is not None for (lo, hi), _ in buckets):
        return bracket_stats(buckets)
    return ladder_stats(above) if len(above) >= 2 else None


def kalshi_index_series(series):
    """(series, index) for Kalshi series about an index: ranges, above/below, highs and lows, up for the day / year,
    comparisons and constituent changes — not the hourly and 15-minute ones, nor the election-day specials."""
    out = []
    for s in series:
        t = (s.get('ticker') or '').upper()
        core = re.sub(r'^KX', '', t)
        if s.get('frequency') in ('hourly', 'fifteen_min') or re.search(r'(15M|EU|E)$', core) and not core.endswith('CLOSE'):
            continue
        for ix in INDICES:
            if any(core.startswith(k) for k in ix['kalshi']) and not (ix['id'] == 'ndx' and core.startswith('NASDAQ') and not core.startswith('NASDAQ100')
                                                                      and not re.match(r'NASDAQ(DUD|WUD)$', core)):
                out.append((s, ix))
                break
    return out


def kalshi_index_rows(e, s, ix):
    ms = e.get('markets') or []
    core = re.sub(r'^KX', '', (s.get('ticker') or '').upper())
    base = {'source': 'kalshi', 'ticker': ix['short'], 'cik': None, 'index': ix['id'], 'points': True, 'underlying': ix['short'],
            'title': e.get('title') or s.get('title'), 'subtitle': e.get('sub_title'), 'url': f'https://kalshi.com/markets/{(s.get("ticker") or "").lower()}',
            'end': (max((m.get('close_time') or '') for m in ms) if ms else '')[:10], 'closed': False,
            'volume': sum(_f(m.get('volume_fp')) or _f(m.get('volume')) or 0 for m in ms), 'series': s.get('ticker')}
    rows = [{'q': m.get('yes_sub_title') or m.get('subtitle') or m.get('title'), 'p': kalshi_prob(m), 'k': _f(m.get('floor_strike')) or _f(m.get('cap_strike'))} for m in ms]
    rows.sort(key=lambda r: (r['k'] is None, r['k'] or 0))
    strikes = [m for m in ms if m.get('strike_type') in ('greater', 'greater_or_equal', 'less', 'less_or_equal', 'between')]
    if re.search(r'MAX|MIN', core) and strikes:
        hi = 'MAX' in core
        pts = []
        for m in strikes:
            k = _f(m.get('floor_strike')) if m.get('strike_type', '').startswith('greater') else _f(m.get('cap_strike'))
            p = kalshi_prob(m)
            if k is None or p is None:
                continue
            if hi:
                pts.append((k, p if m['strike_type'].startswith('greater') else 1 - p))
            else:
                pts.append((k, 1 - p if m['strike_type'].startswith('less') else p))     # P(low > K)
        st = ladder_stats(pts)
        return [{**base, 'kind': 'hit', 'stats_high' if hi else 'stats_low': st,
                 'outcomes': [{'q': ('high ≥ ' if hi else 'low ≤ ') + f'{r["k"]:,.0f}', 'p': r['p']} for r in rows if r['k'] is not None][:24]}]
    if len(strikes) >= 2:
        st = kalshi_dist(strikes)
        kind = 'bracket' if any(m.get('strike_type') == 'between' for m in strikes) else 'above'
        if st:
            return [{**base, 'kind': kind, 'stats': st, 'n': len(strikes), 'outcomes': [{'q': r['q'], 'p': r['p']} for r in rows][:30]}]
    if len(ms) == 1 and re.search(r'POS|Z$|DUD$|WUD$|UP\b', core + ' ' + (e.get('title') or '').upper()):
        return [{**base, 'kind': 'updown', 'p': kalshi_prob(ms[0]), 'outcomes': [{'q': rows[0]['q'], 'p': rows[0]['p']}]}]
    return [{**base, 'kind': 'other', 'outcomes': sorted([{'q': r['q'], 'p': r['p']} for r in rows], key=lambda r: -(r['p'] or 0))[:30]}]


def kalshi_index_scan(h, root, minutes=4.0, verbose=True):
    t0 = time.time()
    pairs = kalshi_index_series(kalshi_series(h, root))
    out = []
    for s, ix in pairs:
        if time.time() - t0 > minutes * 60:
            break
        try:
            ev = h.json(f'{KALSHI}/events?series_ticker={s["ticker"]}&status=open&with_nested_markets=true&limit=20').get('events', [])
        except Exception as exc:
            print(f'  kalshi {s["ticker"]}: {exc}', flush=True); continue
        for e in ev:
            out += kalshi_index_rows(e, s, ix)
    if verbose:
        print(f'kalshi: {len(pairs)} index series, {len(out)} index events', flush=True)
    return out


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
                stats = kalshi_dist(ms)
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
        if m['kind'] != 'beat' or 'id' not in m:
            continue
        old = c.get(str(m['id']))
        if not m.get('closed') or m.get('resolved') is None or not m.get('token') \
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


# ------------------------------------------------------------------ the indices: levels and members
def mkey(m):
    return f'{m["source"]}:{m["kind"]}:{m["ticker"]}:{m["end"]}:{m.get("eps_strike") or ""}' + (f':{m.get("series") or m["url"]}' if m.get('index') else '')


def collect_index_prices(h, root):
    """Two years of daily closes for each index and its ETF (Yahoo chart API, unadjusted closes), kept between runs."""
    p = Path(root) / 'cache' / 'index_prices.json'
    c = read_json(p, {})
    for sym in [ix['symbol'] for ix in INDICES] + [ix['etf'] for ix in INDICES if ix['etf']]:
        try:
            d = h.json(f'{YQ}/v8/finance/chart/{urllib.parse.quote(sym)}?range=2y&interval=1d')
            r = d['chart']['result'][0]
            q = r['indicators']['quote'][0]['close']
            daily = [[dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(), round(v, 4)] for t, v in zip(r.get('timestamp') or [], q) if v is not None]
            meta = r.get('meta') or {}
            if daily:
                c[sym] = {'at': now(), 'price': meta.get('regularMarketPrice') or daily[-1][1],
                          'time': dt.datetime.fromtimestamp(meta['regularMarketTime'], dt.timezone.utc).isoformat() if meta.get('regularMarketTime') else None,
                          'daily': daily}
        except Exception as exc:
            print(f'  yahoo chart {sym}: {exc}', flush=True)
    write_json(p, c)
    return c


def parse_ishares(text):
    """iShares holdings CSV → [(ticker, weight %)] for the equity rows."""
    import csv, io
    lines = text.splitlines()
    i = next((k for k, l in enumerate(lines) if l.startswith('Ticker,')), None)
    if i is None:
        return []
    out = []
    for r in csv.DictReader(io.StringIO('\n'.join(lines[i:]))):
        t, w = (r.get('Ticker') or '').strip(), _f((r.get('Weight (%)') or '').replace(',', ''))
        if t and t != '-' and (r.get('Asset Class') or 'Equity').strip() == 'Equity' and w is not None and w > 0:
            out.append((t, w))
    return out


def wiki_symbols(wikitext):
    """Ticker templates in the constituents table of a Wikipedia article ({{NyseSymbol|MMM}}, {{nasdaq|AAPL}} …),
    before any 'changes' / 'former' section."""
    w = re.split(r'\n==+\s*(?:Selected changes|Recent changes|Changes|Former|Historical|See also|References)', wikitext, maxsplit=1, flags=re.I)[0]
    seen, out = set(), []
    for t in re.findall(r'\{\{\s*(?:nyse|nasdaq|bats|cboe)[a-z ]*\|\s*([A-Za-z][A-Za-z.\-]{0,6})\s*(?:\||\}\})', w, re.I):
        t = t.upper()
        if t not in seen:
            seen.add(t); out.append(t)
    if len(out) < 20:                          # tables that list tickers as plain cells: "| [[Apple Inc.]] || AAPL ||"
        for t in re.findall(r'^\|\s*\[\[[^\]]+\]\]\s*\|\|\s*([A-Z][A-Z.]{0,5})\s*(?:\|\||$)', w, re.M):
            if t not in seen:
                seen.add(t); out.append(t)
    return out


def wiki_html_symbols(html):
    """Tickers from the exchange links of a rendered Wikipedia article (tables transcluded from templates included),
    before a 'Selected changes' / 'Former' section."""
    html = re.split(r'id="(?:Selected_changes|Recent_changes|Former_components|Changes|See_also|References)', html, maxsplit=1)[0]
    seen, out = set(), []
    for a, b in re.findall(r'nyse\.com/quote/X[A-Z]{3}:([A-Za-z.\-]+)|nasdaq\.com/market-activity/stocks/([A-Za-z.\-]+)', html):
        t = (a or b).upper().rstrip('.')
        if t and t not in seen:
            seen.add(t); out.append(t)
    return out


DIAG = {}


def collect_constituents(h, root, max_age_days=6):
    """Members (and weights where the source has them) of each index: iShares holdings (S&P 500 through IVV, Russell 2000
    through IWM), Nasdaq's Nasdaq-100 list, Wikipedia's tables; each must have about the right number of members."""
    p = Path(root) / 'cache' / 'constituents.json'
    c = read_json(p, {})
    nowdt = dt.datetime.now(dt.timezone.utc)
    for ix in INDICES:
        i = ix['id']
        if i not in MEMBERS_OK:
            continue
        old = c.get(i) or {}
        if old.get('at') and (nowdt - dt.datetime.fromisoformat(old['at'])).days < max_age_days:
            continue
        lo, hi = MEMBERS_OK[i]
        got, src, errs = None, None, []
        tries = []
        if i in ISHARES:
            def ishares(i=i):
                for k in range(2):
                    txt = h.get(ISHARES[i], headers={'Accept': 'text/csv,*/*'}).decode('utf-8-sig', 'replace')
                    rows = parse_ishares(txt)
                    if rows:
                        return rows
                    print(f'  iShares {i}: no holdings table in {len(txt)} bytes: {txt[:160]!r}', flush=True)
                    DIAG[i] = f'{len(txt)} bytes, starts {txt[:100]!r}'
                    time.sleep(5)
                return []
            tries.append(('iShares ' + ('IVV' if i == 'spx' else 'IWM'), ishares))
        if i == 'ndx':
            def nasdaq():
                d = h.json('https://api.nasdaq.com/api/quote/list-type/nasdaq100')
                rows = (((d.get('data') or {}).get('data') or {}).get('rows')) or ((d.get('data') or {}).get('rows')) or []
                return [(r['symbol'].strip().upper(), None) for r in rows if r.get('symbol')]
            tries.append(('Nasdaq', nasdaq))
        if i in WIKI:
            api = f'https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(WIKI[i])}&format=json&formatversion=2'
            def wiki(api=api, i=i):
                html = h.json(api + '&prop=text')['parse']['text']
                got = wiki_html_symbols(html)
                if len(got) < 20:
                    k = html.find('MMM') if i == 'dji' else html.find('AAPL')
                    DIAG[i] = f'{len(html)} chars, ids {re.findall(r"<h2[^>]*id=.([A-Za-z_]+)", html)[:12]}, around ticker {html[max(0, k - 160):k + 40]!r}'
                return [(t, None) for t in got]
            tries.append(('Wikipedia', wiki))
            tries.append(('Wikipedia (wikitext)', lambda api=api: [(t, None) for t in wiki_symbols(h.json(api + '&prop=wikitext')['parse']['wikitext'])]))
        for name, fn in tries:
            try:
                rows = fn()
                if lo <= len(rows) <= hi:
                    got, src = rows, name
                    break
                errs.append(f'{name}: {len(rows)} members' + (f' ({DIAG.pop(i)})' if DIAG.get(i) else ''))
            except Exception as exc:
                errs.append(f'{name}: {str(exc)[:80]}')
        if got:
            c[i] = {'at': now(), 'source': src, 'members': got}
        else:
            if i == 'dji' and not old.get('members'):
                c[i] = {'at': None, 'source': 'built-in list (Nov 2024)', 'members': [(t, None) for t in DOW_FALLBACK]}
            c.setdefault(i, {})['errors'] = errs
            print(f'::warning::constituents {i}: ' + '; '.join(errs), flush=True)
    write_json(p, c)
    return c


def collect(root, site_index, minutes=25.0):
    root = Path(root)
    cos = universe(site_index)
    mapper = Mapper(cos)
    h = Http({'gamma-api.polymarket.com': 0.25, 'clob.polymarket.com': 0.25, 'api.elections.kalshi.com': 0.2, 'query2.finance.yahoo.com': 0.7,
              'fc.yahoo.com': 0.5, 'www.ishares.com': 2, 'api.nasdaq.com': 1, 'en.wikipedia.org': 1})
    t0 = time.time()
    poly = poly_scan(h, mapper)
    kal = kalshi_scan(h, root, mapper, minutes=6) + kalshi_index_scan(h, root, minutes=4)
    collect_index_prices(h, root)
    collect_constituents(h, root)
    cal = calibrate_closed(h, root, poly)
    hist_path = root / 'cache' / 'market_history.json'
    hist = read_json(hist_path, {})                     # daily snapshot of every company's market-implied figures
    today = now()[:10]
    for m in poly + kal:
        key = mkey(m)
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
        if not m.get('index'):
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
        prio = {'beat': 0, 'metric': 1, 'above': 2, 'bracket': 3, 'mcap': 4, 'hit': 5, 'kpi': 6, 'mention': 7, 'updown': 8, 'other': 9}
        live = sorted([m for m in by_t.get(t, []) if is_live(m, yday)], key=lambda m: (prio.get(m['kind'], 9), m['end'] or '9999'))
        live = [m for m in live if m['kind'] != 'other'] + [m for m in live if m['kind'] == 'other'][:15]   # leaderboards etc. stay a few
        done = sorted([m for m in by_t.get(t, []) if not is_live(m, yday) and (m['end'] or '') >= cutoff], key=lambda m: m['end'] or '', reverse=True)
        ms = live + done
        shares = a.get('shares')
        for m in ms:
            key = mkey(m)
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
    ixs = build_indices(root, recs, mk, mhist, ours, pledger, by_t, rot)
    recent = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    write_json(pub / 'markets.json', {'generated_at': now(), 'rows': _clean([{k: m.get(k) for k in ('source', 'kind', 'ticker', 'cik', 'title', 'subtitle', 'url', 'end', 'closed',
                                                                                                     'volume', 'p', 'eps_strike', 'report_date', 'basis', 'resolved', 'n', 'implied_price', 'implied_bounds', 'unit',
                                                                                                     'index', 'points', 'underlying')}
                                                                           | {'median': ((m.get('stats') or {}).get('median') or {}).get('value'),
                                                                              'top': (m.get('outcomes') or [])[:3],
                                                                              'high': ((m.get('stats_high') or {}).get('median') or {}).get('value'),
                                                                              'low': ((m.get('stats_low') or {}).get('median') or {}).get('value')}
                                                                           for m in mk if is_live(m, yday) or (m['end'] or '') >= recent])})
    write_json(pub / 'calibration.json', _clean({**calibration(calib), 'price': {k: v for k, v in pledger.items() if k != 'rows'},
                                                'price_rows': pledger['rows'][:150]}))
    st = read_json(root / 'state.json', {})
    write_json(pub / 'status.json', {'built_at': now(), 'companies': len(index), 'markets': len(mk), 'calendar': len(cal_rows),
                                     'analysts': st.get('analysts_summary'), 'indices': ixs})
    if verbose:
        print(f'consensus build: {len(index)} companies, {len(mk)} markets, {len(cal_rows)} upcoming reports', flush=True)
    return {'companies': len(index), 'markets': len(mk)}


def _norm(t):
    return re.sub(r'[^A-Z0-9]', '', (t or '').upper())


def _close_on(daily, day):
    """The last close on or before a date."""
    v = None
    for d, c in daily or []:
        if d > day:
            break
        v = c
    return v


def _weekly(daily, n=110):
    """Friday (last trading day of each week) closes from daily closes."""
    wk = {}
    for d, c in daily or []:
        y, w, _ = dt.date.fromisoformat(d).isocalendar()
        wk[(y, w)] = (d, c)
    return [list(v) for _, v in sorted(wk.items())][-n:]


def bottom_up(members, recs_n, weighting, beat_p=None, today=None):
    """The analysts' consensus of an index added up from its companies (each at its weight): the price-target return,
    the low and high targets, earnings growth (index earnings = Σ shares × EPS), forward P/E, the mean rating, how many
    companies had their estimates raised or cut in 30 days, the reporting season so far and the reports coming up."""
    today = today or dt.date.today().isoformat()
    rows = []
    for t, w in members:
        rec = recs_n.get(_norm(t)) or {}
        a = rec.get('analysts') or {}
        price, shares = a.get('price'), a.get('shares')
        cap = price * shares if price and shares else None
        wt = w if w is not None else (price if weighting == 'price' else cap)
        rows.append({'t': rec.get('ticker') or t, 'cik': rec.get('cik'), 'name': rec.get('name'), 'w': wt, 'a': a, 'rec': rec, 'price': price, 'shares': shares, 'cap': cap})
    tot = sum(r['w'] for r in rows if r['w'])
    if not tot:
        return None, rows
    for r in rows:
        r['w'] = (r['w'] or 0) / tot
    T = [r for r in rows if r['w'] and r['price'] and (r['a'].get('targets') or {}).get('mean')]
    wT = sum(r['w'] for r in T)
    clip = lambda v: max(-0.6, min(1.0, v))     # one company's target at most +100% / −60%: thinly covered small caps carry outliers
    agg = lambda key: sum(r['w'] * clip((r['a']['targets'].get(key) or r['a']['targets']['mean']) / r['price'] - 1) for r in T) / wT if wT else None
    per = lambda r, p: next((x for x in r['a'].get('periods') or [] if x['period'] == p), {})
    E0 = E1 = Ep = C = 0.0
    nE = 0
    for r in rows:
        y0, y1 = (per(r, '0y').get('eps') or {}), (per(r, '+1y').get('eps') or {})
        if r['shares'] and r['cap'] and (y0.get('avg') or 0) > 0 and (y1.get('avg') or 0) > 0 and (y0.get('yearAgoEps') or 0) > 0 \
                and 0.25 < y0['avg'] / y0['yearAgoEps'] < 4 and 0.25 < y1['avg'] / y0['avg'] < 4:     # profitable both years, no per-share breaks
            E0 += r['shares'] * y0['avg']; E1 += r['shares'] * y1['avg']; Ep += r['shares'] * y0['yearAgoEps']; C += r['cap']; nE += 1
    R = [r for r in rows if r['w'] and (r['a'].get('rating') or {}).get('mean')]
    wR = sum(r['w'] for r in R)
    up = dn = 0; wu = wd = 0.0
    for r in rows:
        tr = per(r, '0y').get('eps_trend') or {}
        if tr.get('current') is not None and tr.get('30daysAgo'):
            ch = tr['current'] / tr['30daysAgo'] - 1
            if ch > 0.001:
                up += 1; wu += r['w']
            elif ch < -0.001:
                dn += 1; wd += r['w']
    since = (dt.date.fromisoformat(today) - dt.timedelta(days=45)).isoformat()
    season = []
    for r in rows:
        for x in (r['rec'].get('surprises_all') or r['a'].get('surprises') or []):
            if (x.get('reported') or '') >= since and x.get('surprise') is not None:
                season.append({'t': r['t'], 'w': r['w'], 'surprise': x['surprise'], 'reported': x['reported']})
    soon = (dt.date.fromisoformat(today) + dt.timedelta(days=7)).isoformat()
    coming = []
    for r in rows:
        nx = r['a'].get('next_earnings') or {}
        if nx.get('date') and today <= nx['date'] <= soon:
            q0 = per(r, '0q').get('eps') or {}
            coming.append({'ticker': r['t'], 'cik': r['cik'], 'name': r['name'], 'date': nx['date'], 'weight': r['w'], 'eps': q0.get('avg'),
                           'beat_prob': (beat_p or {}).get(r['t'])})
    coming.sort(key=lambda x: -x['weight'])
    sur = sorted(x['surprise'] for x in season)
    out = {'members': len(members), 'matched': sum(1 for r in rows if r['a']), 'weighting': weighting,
           'target_ret': agg('mean'), 'target_low_ret': agg('low'), 'target_high_ret': agg('high'), 'target_coverage': wT, 'target_n': len(T),
           'eps_growth_this_fy': E0 / Ep - 1 if Ep > 0 else None, 'eps_growth_next_fy': E1 / E0 - 1 if E0 > 0 else None,
           'fwd_pe': C / E1 if E1 > 0 else None, 'pe_this_fy': C / E0 if E0 > 0 else None, 'eps_n': nE,
           'rating_mean': sum(r['w'] * r['a']['rating']['mean'] for r in R) / wR if wR else None,
           'revisions_30d': {'up': up, 'down': dn, 'w_up': wu, 'w_down': wd},
           'season': {'reported': len(season), 'beat': sum(1 for x in season if x['surprise'] > 0), 'w_reported': sum(x['w'] for x in season),
                      'median_surprise': sur[len(sur) // 2] if sur else None},
           'coming': coming[:15]}
    return out, rows


def weekly_vol(rot, ticker, weeks=52):
    """Standard deviation of weekly log returns over the last year (rotation history closes)."""
    pts = prices(rot, ticker, weeks + 1)
    r = [math.log(b[1] / a[1]) for a, b in zip(pts, pts[1:]) if a[1] and b[1] and a[1] > 0 and b[1] > 0]
    if len(r) < 26:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def diversification(rot, rows, etf):
    """How much smaller the index's weekly swings were over the past year than its members' (weighted): σ(index) ÷ Σ w σ."""
    if not rot or not etf:
        return None
    sp = weekly_vol(rot, etf)
    top = sorted([r for r in rows if r['w']], key=lambda r: -r['w'])[:150]
    num_, den = 0.0, 0.0
    for r in top:
        v = weekly_vol(rot, r['t'])
        if v:
            num_ += r['w'] * v; den += r['w']
    if not sp or not den:
        return None
    return max(0.15, min(1.0, sp / (num_ / den)))


def bottom_up_ours(rows, ours_n, div=None):
    """Our model for an index: each company's forecast return from the forecast's base date, at its weight, over the
    companies the model forecasts. The 80% range adds the companies' ranges, narrowed by the diversification ratio (the
    index swung less than its members over the past year); without it, as if they all moved together."""
    out = {}
    for r in rows:
        for f in ours_n.get(_norm(r['t'])) or []:
            if not r['w'] or not f.get('close_then') or f.get('price') is None:
                continue
            o = out.setdefault(f['horizon'], {'horizon': f['horizon'], 'date': f['date'], 'from': f['from'], 'model': f['model'], 'w': 0.0, 'ret': 0.0, 'lo': 0.0, 'hi': 0.0, 'n': 0})
            o['w'] += r['w']; o['n'] += 1
            o['ret'] += r['w'] * (f['price'] / f['close_then'] - 1)
            o['lo'] += r['w'] * ((f.get('lo80') or f['price']) / f['close_then'] - 1)
            o['hi'] += r['w'] * ((f.get('hi80') or f['price']) / f['close_then'] - 1)
            r.setdefault('ours', {})[f['horizon']] = f['price'] / f['close_then'] - 1
    for o in out.values():
        for k in ('ret', 'lo', 'hi'):
            o[k] = o[k] / o['w'] if o['w'] else None
        if div and o['ret'] is not None:
            o['lo'] = o['ret'] + div * (o['lo'] - o['ret']); o['hi'] = o['ret'] + div * (o['hi'] - o['ret'])
        o['diversification'] = div
    return out


def build_indices(root, recs, mk, mhist, ours, pledger, by_t, rot=None):
    """public/market.json (every index side by side) and public/ix/<id>.json (one index): level history, the analysts'
    consensus added up from the members, every prediction market about the index, our model added up from the members."""
    root = Path(root); pub = root / 'public'
    (pub / 'ix').mkdir(parents=True, exist_ok=True)
    px = read_json(root / 'cache' / 'index_prices.json', {})
    cons = read_json(root / 'cache' / 'constituents.json', {})
    hist_p = root / 'cache' / 'index_history.json'
    H = read_json(hist_p, {})
    today = dt.date.today().isoformat()
    yday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    recs_n = {_norm(t): r for t, r in recs.items()}
    ours_n = {_norm(t): v for t, v in ours.items()}
    beat_p = {t: m['p'] for t, ms in by_t.items() for m in ms if m['kind'] == 'beat' and not m['closed'] and (m.get('report_date') or '9999') >= today}
    overview, summary = [], {}
    for ix in INDICES:
        i = ix['id']
        P = px.get(ix['symbol']) or {}
        daily = P.get('daily') or []
        level = P.get('price') or (daily[-1][1] if daily else None)
        E = px.get(ix['etf']) if ix['etf'] else None
        ratio = level / E['price'] if level and E and E.get('price') else None
        ms = [m for m in mk if m.get('index') == i]
        live = sorted([m for m in ms if is_live(m, yday)], key=lambda m: (m['end'] or '9999', m['kind'] != 'above'))
        done = sorted([m for m in ms if not is_live(m, yday) and (m['end'] or '') >= (dt.date.today() - dt.timedelta(days=60)).isoformat()],
                      key=lambda m: m['end'] or '', reverse=True)[:40]
        for m in live + done:
            m['history'] = sorted(mhist.get(mkey(m), {}).items())[-120:]
            st = m.get('stats') or {}
            f = 1.0 if m.get('points', True) else ratio
            if st and f and m['kind'] in ('above', 'bracket'):
                m['implied_price'] = {k: (st.get(k) or {}).get('value') * f if (st.get(k) or {}).get('value') is not None else None for k in ('q10', 'q25', 'median', 'q75', 'q90')}
                m['implied_bounds'] = {k: (st.get(k) or {}).get('bound') for k in ('q10', 'median', 'q90')}
        mem = (cons.get(i) or {}).get('members') or []
        if i == 'rut' and not mem:                             # no list this week: the companies ranked 1,001–3,000 by market value stand in
            by_cap = sorted([r for r in recs.values() if (r.get('analysts') or {}).get('price') and (r.get('analysts') or {}).get('shares')],
                            key=lambda r: -r['analysts']['price'] * r['analysts']['shares'])
            mem = [(r['ticker'], None) for r in by_cap[1000:3000]]
            cons.setdefault(i, {})['source'] = 'the companies ranked 1,001–3,000 by market value on file, as the Russell 2000 is built (no holdings list this week)'
        if i == 'spx' and not mem:                             # no list this week: the 500 largest companies on file stand in
            big = sorted([r for r in recs.values() if (r.get('analysts') or {}).get('price') and (r.get('analysts') or {}).get('shares')],
                         key=lambda r: -r['analysts']['price'] * r['analysts']['shares'])[:500]
            mem = [(r['ticker'], None) for r in big]
            cons.setdefault(i, {})['source'] = 'the 500 largest companies on file (no constituent list this week)'
        bu, rows = (bottom_up(mem, recs_n, ix['weighting'], beat_p, today) if mem and ix['weighting'] else (None, []))
        div = diversification(rot, rows, ix['etf']) if rows else None
        our = bottom_up_ours(rows, ours_n, div) if rows else {}
        ours_doc = []
        for o in our.values():
            l0 = _close_on(daily, o['from'])
            if l0 and o['ret'] is not None:
                ours_doc.append({'horizon': o['horizon'], 'date': o['date'], 'from': o['from'], 'close_then': l0, 'price': l0 * (1 + o['ret']),
                                 'lo80': l0 * (1 + o['lo']), 'hi80': l0 * (1 + o['hi']), 'ret': o['ret'], 'coverage': o['w'], 'n': o['n'],
                                 'model': 'bottom-up ' + o['model'], 'diversification': o.get('diversification')})
        ours_doc.sort(key=lambda o: o['date'])
        targets = {}
        if bu and bu['target_ret'] is not None and level:
            targets = {'mean': level * (1 + bu['target_ret']), 'low': level * (1 + bu['target_low_ret']), 'high': level * (1 + bu['target_high_ret']), 'n': bu['target_n']}
        top = sorted([r for r in rows if r['w']], key=lambda r: -r['w'])[:20]
        contrib = [{'ticker': r['t'], 'cik': r['cik'], 'name': r['name'], 'weight': r['w'], 'price': r['price'],
                    'target_ret': (r['a']['targets']['mean'] / r['price'] - 1) if r['price'] and (r['a'].get('targets') or {}).get('mean') else None,
                    'ours_q': (r.get('ours') or {}).get('next quarter'), 'ours_m': (r.get('ours') or {}).get('next month'),
                    'next_earnings': (r['a'].get('next_earnings') or {}).get('date'), 'beat_prob': beat_p.get(r['t'])} for r in top]
        pm = [m for m in live if m.get('implied_price') and m['implied_price'].get('median') and (m['end'] or '') >= (dt.date.today() + dt.timedelta(days=5)).isoformat()]
        unb = lambda m: not any((m.get('implied_bounds') or {}).values())
        pm_pick = min(pm, key=lambda m: (m['end'], not unb(m), m['kind'] != 'bracket')) if pm else None
        pm_far = max(pm, key=lambda m: (m['end'], unb(m), m['kind'] == 'bracket', len((m.get('stats') or {}).get('buckets') or []))) if pm else None
        ud = [m for m in live if m['kind'] == 'updown' and m.get('p') is not None]
        ud_pick = min(ud, key=lambda m: (m['end'] or '9999')) if ud else None
        oq = next((o for o in ours_doc if o['horizon'] == 'next quarter'), None)
        H.setdefault(i, {})[today] = [_r(level, 2), _r(targets.get('mean'), 2), _r(oq['price'], 2) if oq else None,
                                      _r(pm_far['implied_price']['median'], 2) if pm_far else None, pm_far['end'] if pm_far else None]
        H[i] = dict(sorted(H[i].items())[-500:])
        doc = {'id': i, 'name': ix['name'], 'short': ix['short'], 'symbol': ix['symbol'], 'etf': ix['etf'], 'ratio': ratio, 'unit': 'pts',
               'level': level, 'as_of': (P.get('time') or P.get('at') or '')[:10] or None, 'generated_at': now(),
               'prices': _weekly(daily), 'analysts': {'price': level, 'targets': targets, 'as_of': (P.get('time') or '')[:10] or None},
               'bottom_up': bu, 'members_source': (cons.get(i) or {}).get('source'), 'members_errors': (cons.get(i) or {}).get('errors'),
               'contributors': contrib, 'ours': ours_doc, 'markets': (live + done)[:80],
               'history_fields': ['level', 'analysts_target', 'ours_next_quarter', 'market_far_median', 'market_far_date'],
               'history': sorted(H[i].items()), 'price_track': [r for r in pledger['rows'] if r['ticker'] == ix['short']][:30]}
        write_json(pub / 'ix' / f'{i}.json', _clean(doc))
        wk = _weekly(daily, 60)
        y0 = _close_on(daily, f'{today[:4]}-01-01') if daily else None
        chg = lambda a, b: (a / b - 1) if a and b else None
        overview.append({'id': i, 'name': ix['name'], 'short': ix['short'], 'etf': ix['etf'], 'level': level, 'as_of': doc['as_of'],
                         'chg_1w': chg(level, wk[-2][1]) if len(wk) > 1 else None, 'chg_ytd': chg(level, y0),
                         'target': targets.get('mean'), 'target_ret': bu and bu['target_ret'], 'target_coverage': bu and bu['target_coverage'],
                         'eps_growth_next_fy': bu and bu['eps_growth_next_fy'], 'fwd_pe': bu and bu['fwd_pe'],
                         'pm_near': {'median': pm_pick['implied_price']['median'], 'q10': pm_pick['implied_price']['q10'], 'q90': pm_pick['implied_price']['q90'],
                                     'end': pm_pick['end'], 'source': pm_pick['source'], 'title': pm_pick['title']} if pm_pick else None,
                         'pm_far': {'median': pm_far['implied_price']['median'], 'q10': pm_far['implied_price']['q10'], 'q90': pm_far['implied_price']['q90'],
                                    'end': pm_far['end'], 'source': pm_far['source'], 'title': pm_far['title']} if pm_far and pm_far is not pm_pick else None,
                         'pm_up': {'p': ud_pick['p'], 'end': ud_pick['end'], 'title': ud_pick['title'], 'source': ud_pick['source']} if ud_pick else None,
                         'ours': [{k: o[k] for k in ('horizon', 'date', 'price', 'lo80', 'hi80', 'ret', 'coverage', 'close_then', 'from')} for o in ours_doc],
                         'markets': len(live), 'spark': [w[1] for w in wk[-26:]]})
        summary[i] = {'level': _r(level, 2), 'markets': len(live), 'members': len(mem), 'source': (cons.get(i) or {}).get('source'),
                      'ours': len(ours_doc), 'target': _r(targets.get('mean'), 2)}
    write_json(hist_p, H)
    write_json(pub / 'market.json', _clean({'generated_at': now(), 'indices': overview}))
    return summary


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
