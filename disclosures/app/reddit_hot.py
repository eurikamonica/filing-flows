"""Reddit's hottest stock right now (4.15): the investing subreddits read every half hour, the hottest ticker as a cashtag.

Each run reads the hot and new listings of r/wallstreetbets, r/stocks, r/investing, r/StockMarket, r/options and
r/pennystocks (100 threads each) — through Reddit's OAuth API with REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET (a free
"script" app), else the public JSON listing. Reddit refuses some cloud servers; then ApeWisdom's free count of ticker
mentions across those subreddits over 24 hours is used instead (counts and ranks, no thread titles).

Tickers in a thread: $CASHTAGS always (when listed); bare upper-case words only when they are a listed ticker (SEC
company tickers) and not a common word or trading slang ("ALL", "CEO", "YOLO", "DD", "CALLS", "DTE" …), in the title and
the first lines of the text. ETFs, ETNs and trusts (SPY, GLD, IBIT …) are left out: the page asks for a stock.
Heat of a ticker = Σ over its threads of (√upvotes + 2·√comments + 1) × recency (half-life 12 hours) — fresh threads
with real engagement count most. Mentions: threads naming it in the last 24 hours, against the 24 hours before.

Cache:   cache/reddit/state.json (three days of half-hourly leaders, the threads seen in the last 48 hours)
Publish: market/reddit.json — the hottest ticker ($CASHTAG) with its threads, the top 30, and the leaders over the day.
Used by: Disclosures → All flows (the banner, with what insiders, 13F managers and officials are doing in it) and the X
posts (pipeline/engage.py kind "reddit_hot").
"""
import base64
import datetime as dt
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core import now, read_json, write_json

SUBS = ['wallstreetbets', 'stocks', 'investing', 'StockMarket', 'options', 'pennystocks']
UA = os.environ.get('REDDIT_USER_AGENT') or 'FilingFlows/1.0 (public disclosures research; by u/filingflows)'
APEWISDOM = 'https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}'
HALF_LIFE_H = 12.0
IGNORE = set("""
A I AI ALL AM AN AND ANY ARE AS AT BE BIG BEST BUY BY CAN CASH CEO CFO COO CTO DD DO DOW EPS ETF EV EVER FAST FED FOMC FOR
FUN GDP GO GOOD HAS HE HOLD HUGE IMO IN IPO IS IT ITS JOB LOL LOVE LOW HIGH MAN ME MOVE MY NEW NEXT NO NOW OF OK ON ONE OP
OPEN OR OUT PE PLAY PM PT PUMP PUT PUTS CALL CALLS RE REAL RUN SAVE SEC SEE SELL SO TECH TL DR TO TRUE TWO UK UP US USA
WELL WORK WSB YOLO YOU YTD ATH CPI PPI Q QQQ SPY VOO VTI IRA ROTH ER DCA EOD ITM OTM IV DTE FD FDS RH OG GG FOMO FUD HODL
LMAO WTF TLDR IRS USD EU EUR GBP CAD JPY CNY ESG AGI API CEOS AMA NFT CBS NBC CNN BBC TV PC PR HR IR VC PE LLC INC
GAIN LOSS RIP BRO MOON BEAR BULL BAG BAGS TOP DIP RED GREEN GOLD OIL GAS BTC ETH SOL XRP DOGE ARE WAS WERE HIS HER HIM
SHE THEY THEM WHO WHY HOW WHAT WHEN WHERE THIS THAT THESE THOSE WITH FROM INTO ONTO OVER UNDER JUST ONLY ALSO VERY MUCH
MORE MOST LESS LEAST SOME MANY FEW EACH BOTH EITHER NEITHER OWN SAME OTHER SUCH NOT YES AGO AGE AIR ARM ART BAD BIT BOX
CAR CAT DOG EAR EAT EGG END EYE FAR FIT FLY FUND GUY HOT ICE INFO KEY KID LAB LAW LET LIE MAP MAX MIN MIX MOM NET NICE NUT
OLD PAY PER POP PRO RAW RAY ROI SAFE SALE SAY SIX SKY SUN TAX TEN TOO TRY USE VIA WAR WAY WIN WOW ZERO LIFE LIVE LONG
SHORT RATE RATES TRADE NEWS HELP POST EDIT LINK FREE PLAN TIME YEAR WEEK DAY DAYS BACK CARE DEAL DUE EASY FACT FAIL FEEL
FIND FIRE FORM GAME GOES HAND HARD HEAR HOME HOPE IDEA KEEP KIND LAST LATE LEFT LINE LOOK LOST MAKE MEAN MIND MISS NEED
NONE ONCE PAID PART PICK PLUS RISK ROLL SAID SEEN SEND SIDE SIGN SITE SIZE SOON STAY STEP STOP SURE TAKE TALK TELL THEN
TURN VIEW WAIT WALK WANT WEAR WIDE WILD WISH WORD YEAH ZONE
""".split())


FUND = re.compile(r'\bETF\b|\bETN\b|SPDR|ISHARES|PROSHARES|DIREXION|VANGUARD|INVESCO QQQ|SELECT SECTOR|\bFUND\b|GRAYSCALE|'
                  r'(GOLD|SILVER|BITCOIN|ETHER(EUM)?|OIL|COMMODITY|INDEX)\b.*\bTRUST\b|\bTRUST\b.*\b(GOLD|SILVER|BITCOIN|ETHER(EUM)?|OIL)\b', re.I)


def is_fund(name):
    """ETFs, ETNs and trusts (SPY, GLD, IBIT …): a market, not a stock topic — left out of the ranking."""
    return bool(FUND.search(name or ''))


def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def listed_tickers(root):
    """{ticker: name} of SEC's company tickers (the Hub's weekly cache), dots as dashes like the rest of the Hub."""
    out = {}
    for r in (read_json(Path(root) / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []):
        t = str(r.get('ticker') or '').upper().replace('.', '-')
        if re.fullmatch(r'[A-Z][A-Z0-9-]{0,6}', t):
            out.setdefault(t, r.get('title') or '')
    return out


def tickers_in(text, known, cashtags_only_text=''):
    """The listed tickers a thread names: $CASHTAGS anywhere; bare upper-case words (2–5 letters) in the title only when
    they are listed and not common words."""
    found = set()
    for m in re.finditer(r'\$([A-Za-z]{1,5}(?:\.[A-Za-z])?)\b', text + ' ' + cashtags_only_text):
        t = m.group(1).upper().replace('.', '-')
        if t in known:
            found.add(t)
    for m in re.finditer(r'(?<![$\w])([A-Z]{2,5})(?![\w$])', text):
        t = m.group(1)
        if t in known and t not in IGNORE:
            found.add(t)
    return found


# ------------------------------------------------------------------ reading Reddit
def _get(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def oauth_token():
    cid, sec = os.environ.get('REDDIT_CLIENT_ID'), os.environ.get('REDDIT_CLIENT_SECRET')
    if not (cid and sec):
        return None
    req = urllib.request.Request('https://www.reddit.com/api/v1/access_token', data=b'grant_type=client_credentials',
                                 headers={'User-Agent': UA, 'Authorization': 'Basic ' + base64.b64encode(f'{cid}:{sec}'.encode()).decode(),
                                          'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8')).get('access_token')


def listing(sub, kind, token=None, limit=100):
    """One subreddit listing → [{sub, title, text, score, comments, created, url, flair}] (stickied threads left out)."""
    q = urllib.parse.urlencode({'limit': limit, 'raw_json': 1})
    if token:
        url, headers = f'https://oauth.reddit.com/r/{sub}/{kind}?{q}', {'User-Agent': UA, 'Authorization': f'Bearer {token}'}
    else:
        url, headers = f'https://www.reddit.com/r/{sub}/{kind}.json?{q}', {'User-Agent': UA, 'Accept': 'application/json'}
    last = None
    for attempt in range(3):
        try:
            d = _get(url, headers)
            break
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                time.sleep(4 * (attempt + 1))
                continue
            raise
    else:
        raise last
    out = []
    for ch in (d.get('data') or {}).get('children') or []:
        x = ch.get('data') or {}
        if x.get('stickied') or x.get('pinned'):
            continue
        out.append({'sub': sub, 'id': x.get('id') or '', 'title': (x.get('title') or '').strip(), 'text': (x.get('selftext') or '')[:600],
                    'score': _num(x.get('score')), 'comments': _num(x.get('num_comments')), 'created': float(x.get('created_utc') or 0),
                    'url': 'https://www.reddit.com' + (x.get('permalink') or ''), 'flair': x.get('link_flair_text') or ''})
    return out


def read_reddit(subs=SUBS):
    """Every thread of the hot and new listings, deduplicated; (threads, source, errors)."""
    errors, token = [], None
    try:
        token = oauth_token()
    except Exception as exc:
        errors.append(f'oauth: {exc}')
    threads, seen = [], set()
    for sub in subs:
        for kind in ('hot', 'new'):
            try:
                for t in listing(sub, kind, token):
                    if t['id'] and t['id'] not in seen:
                        seen.add(t['id'])
                        threads.append(t)
            except Exception as exc:
                errors.append(f'r/{sub}/{kind}: {str(exc)[:100]}')
            if not token:
                time.sleep(1.2)
    return threads, ('reddit-oauth' if token else 'reddit'), errors


def apewisdom(known, pages=2):
    """ApeWisdom's 24-hour mention counts across the investing subreddits → rows like heat() gives (no threads)."""
    rows, seen = [], set()
    for page in range(1, pages + 1):
        d = _get(APEWISDOM.format(page=page), {'User-Agent': UA, 'Accept': 'application/json'})
        for x in d.get('results') or []:
            t = str(x.get('ticker') or '').upper().replace('.', '-')
            if t not in known or t in seen or t in IGNORE or is_fund(known.get(t)):    # its counts include slang ("DTE") and funds
                continue
            seen.add(t)
            m, m0 = _num(x.get('mentions')), _num(x.get('mentions_24h_ago'))
            rows.append({'ticker': t, 'heat': round(m + _num(x.get('upvotes')) / 10, 1), 'mentions': m, 'mentions_prev': m0,
                         'rank_prev': _num(x.get('rank_24h_ago'), None), 'threads': []})
    rows.sort(key=lambda r: -r['heat'])
    return rows


# ------------------------------------------------------------------ heat
def heat(threads, known, now_ts=None):
    """[{ticker, heat, mentions, mentions_prev, threads}] from the threads (newest two days)."""
    now_ts = now_ts or time.time()
    agg = {}
    for t in threads:
        age_h = max(0.0, (now_ts - t['created']) / 3600)
        if age_h > 48:
            continue
        w = (math.sqrt(max(t['score'], 0)) + 2 * math.sqrt(max(t['comments'], 0)) + 1) * 0.5 ** (age_h / HALF_LIFE_H)
        for tk in tickers_in(t['title'], known, t.get('text') or ''):
            a = agg.setdefault(tk, {'ticker': tk, 'heat': 0.0, 'mentions': 0, 'mentions_prev': 0, 'threads': []})
            a['heat'] += w
            if age_h <= 24:
                a['mentions'] += 1
            else:
                a['mentions_prev'] += 1
            a['threads'].append({**t, 'w': w})
    rows = sorted(agg.values(), key=lambda a: -a['heat'])
    for a in rows:
        a['heat'] = round(a['heat'], 1)
        a['threads'] = [{k: th[k] for k in ('sub', 'title', 'score', 'comments', 'url', 'created', 'flair')}
                        for th in sorted(a['threads'], key=lambda th: -th['w'])[:5]]
    return rows


def collect(client, root, cfg=None):
    """Read Reddit (or ApeWisdom), rank the tickers, keep the leaders' history; the result goes to publish()."""
    cfg = cfg or {}
    root = Path(root)
    cdir = root / 'cache' / 'reddit'
    known = listed_tickers(root)
    if not known:
        raise RuntimeError('no SEC ticker list in cache/prices/sec-tickers.json')
    threads, source, errors = read_reddit(cfg.get('subreddits') or SUBS)
    rows = [r for r in heat(threads, known) if not is_fund(known.get(r['ticker']))] if threads else []
    if not rows:
        try:
            rows, source = apewisdom(known), 'apewisdom'
        except Exception as exc:
            errors.append(f'apewisdom: {str(exc)[:100]}')
    if not rows:
        raise RuntimeError('; '.join(errors)[:300] or 'no tickers found')
    for r in rows:
        r['name'] = known.get(r['ticker'], '')
    state = read_json(cdir / 'state.json', {}) or {}
    stamp = now()
    hist = [h for h in state.get('leaders', []) if h[0] >= (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()]
    hist.append([stamp, rows[0]['ticker'], rows[0]['heat'], [r['ticker'] for r in rows[:5]]])
    write_json(cdir / 'state.json', {'leaders': hist[-150:], 'updated_at': stamp})
    write_json(cdir / 'latest.json', {'generated_at': stamp, 'source': source, 'threads_read': len(threads),
                                      'subreddits': cfg.get('subreddits') or SUBS, 'errors': errors[:10], 'rows': rows[:30]})
    return {'status': 'ok' if source != 'apewisdom' else 'partial', 'source': source, 'threads': len(threads), 'tickers': len(rows),
            'hottest': rows[0]['ticker'], 'errors': errors[:5], 'updated_at': stamp}


def publish(root, market_dir):
    root = Path(root)
    latest = read_json(root / 'cache' / 'reddit' / 'latest.json', {}) or {}
    rows = latest.get('rows') or []
    if not rows:
        return None
    state = read_json(root / 'cache' / 'reddit' / 'state.json', {}) or {}
    lead = rows[0]
    hist = state.get('leaders', [])
    since = None                                          # how long the leader has been on top (consecutive runs)
    for h in reversed(hist):
        if h[1] != lead['ticker']:
            break
        since = h[0]
    out = {'generated_at': latest.get('generated_at'), 'source': latest.get('source'), 'threads_read': latest.get('threads_read'),
           'subreddits': latest.get('subreddits'), 'errors': latest.get('errors') or [],
           'hottest': {**lead, 'cashtag': '$' + lead['ticker'].replace('-', '.'), 'leading_since': since},
           'rows': rows, 'leaders': [[h[0], h[1], h[2]] for h in hist[-96:]],
           'note': ('The tickers people are posting about on investing subreddits right now — hot and new threads, weighted by '
                    'upvotes, comments and freshness. Popularity on Reddit is not a recommendation and says nothing about value.')}
    write_json(Path(market_dir) / 'reddit.json', out)
    return {'hottest': out['hottest']['cashtag'], 'rows': len(rows)}
