"""Move odds: the news headlines around each move — beside the company's own filings (app/move_news.py), what the press
wrote. For every valued company (and the market, SPY, in its own words) Google News's search feed is asked for the
headlines that name it over a window of days: the last week (the market and the 300 largest companies, every day), a
month at a time back over the last three years (newest first), and the two days around each of its biggest moves since
2008 (the bottom and top 10% of its days, the most extreme first). A window that comes back full (the feed gives 100 at
most) is split in two and asked again, down to two days. Each headline is put on the trading day it could move — its
own day when published before the 16:00 New York close, else the next — and only the headline, its source, its time and
the link are kept, never the article.

A headline is kept when it names the company (its ticker or the distinctive words of its name) and is not one of the
automatic "fund X bought / sold shares of …" notes made from 13F filings; reputable sources and headlines about a move
(falls, beats, guidance, a deal …) first, investing listicles last, eight a day at most.

Store (branch research-paths):  cache/headlines/<TICKER>.json  {'ticker', 'name', 'q': the words searched,
                                 'days': {trading day: [[published (UTC ISO), source, title, link], …]},
                                 'windows': [[from, to, fetched (UTC ISO), headlines the feed gave]]}
Published (by move_news.publish): public/moves/n/<TICKER>.json  'headlines': [[trading day, date, 'HH:MM' New York time
                                 or '' (the feed dates some only), source, title, link]] (most telling first each day),
                                 'checked': [the trading days fully searched]

    python app/paths.py moveheadlines --root P --universe val/public/index.json [--queries 550 --minutes 15]
"""
import datetime as dt
import email.utils
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from core import read_json, write_json

FEED = 'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en'
HOST = 'news.google.com'
PER_DAY = 8
PER_COMPANY = 6                # windows searched per company per round (the round goes on with the next company)
RECENT_TOP = 300               # the last week every day: the market and the largest companies
RECENT_DAYS = 7                # calendar days in the recent window
MONTHS = 36                    # a month at a time, back over the last three years
FULL = 95                      # a window this full is split in two (the feed gives 100 at most)
FROM = '2008-01-01'            # the biggest moves back to here (the archive thins out before)
MARKET = {'SPY': ('the market', '"stock market" OR "Wall Street" OR "S&P 500" OR "Dow Jones" OR "Nasdaq"')}
TOP = ('reuters', 'bloomberg', 'wall street journal', 'wsj', 'financial times', 'ft.com', 'cnbc', "barron's", 'barrons', 'associated press', 'ap news',
       'marketwatch', 'yahoo finance', 'the new york times', 'new york times', 'investor\'s business daily', 'forbes', 'business insider', 'fortune', 'axios',
       'the information', 'techcrunch', 'the verge', 'cnn', 'bbc', 'the economist', 'nikkei', 'fierce', 'stat', 'endpoints', 'biospace', 'politico')
OK_SOURCES = ('seeking alpha', 'the motley fool', 'benzinga', 'investopedia', 'zacks', 'thestreet', 'kiplinger', 'morningstar', 'globe newswire',
              'pr newswire', 'business wire', 'sec.gov')
DENY = ('marketbeat', 'defense world', 'etf daily news', 'the lincolnian online', 'ticker report', 'the cerbat gem', 'modern readers', 'dakota financial news',
        'zolmax', 'transcript daily', 'wkrb news', 'the markets daily', 'american banking news', 'stock observer', 'daily political', 'watchlist news',
        'the enterprise leader', 'baseball news source', 'thecerbatgem', 'tickerreport', 'com-unik', 'mayfield recorder', 'kiwi news', 'tech news', 'flbc news')
# the automatic notes made from 13F filings and insider forms ("XYZ Capital Buys 1,200 Shares of Apple Inc.")
AUTO = re.compile(r'\b(shares?|stake|position|holdings?)\s+(sold|bought|acquired|purchased|raised|lowered|trimmed|reduced|boosted|lifted|increased|decreased|cut|grown)\s+by\b'
                  r'|\b(acquires?|buys?|sells?|trims?|lowers?|raises?|boosts?|lifts?|cuts?|reduces?|increases?|decreases?|grows?|takes?)\s+(a\s+)?(new\s+)?(\$[\d.,]+\s*[mk]?\w*\s+)?'
                  r'(shares?|stake|position|holdings?)\s+(in|of)\b|\b\d[\d,]*\s+shares\s+of\b', re.I)
SUFFIX = re.compile(r'[,.]?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|l\.p|n\.?v|s\.?a|ag|se|holdings?|group|the)\.?$', re.I)
# what a headline says about a move ranks it up; investing listicles rank it down
MOVE = re.compile(r'\b(falls?|fell|drops?|dropped|plunges?|plunged|plummets?|tumbles?|sinks?|sank|slides?|slumps?|craters?|sheds?|jumps?|jumped|soars?|soared|surges?|surged|'
                  r'rall(y|ies|ied)|rises?|rose|gains?|climbs?|spikes?|beats?|miss(es)?|missed|earnings|results|forecast|guidance|outlook|downgrade[sd]?|upgrade[sd]?|'
                  r'price target|lawsuit|probe|investigation|fda|approval|approves?|recall|acquir\w*|deal|merger|buyout|takeover|layoffs?|ceo|resigns?|bankrupt\w*|'
                  r'offering|dividend|split|record|selloff|sell-off|halted?|why .* (stock|shares))\b', re.I)
FLUFF = re.compile(r"here'?s how much|if you had invested|\bwould be worth\b|better (growth|dividend|value)? ?stock|buy or sell|should you buy|"
                   r'\b\d+ (reasons|stocks|things)\b|millionaire|retire|forever|no-brainer|top \d+', re.I)
GENERIC = {'the', 'american', 'first', 'general', 'united', 'national', 'international', 'global', 'new', 'western', 'eastern', 'southern', 'northern',
           'royal', 'central', 'pacific', 'atlantic', 'capital', 'community', 'federal', 'great', 'old', 'texas', 'us', 'u.s.'}


def path(root, ticker):
    return Path(root) / 'cache' / 'headlines' / f'{ticker}.json'


def short_name(name):
    """'HALOZYME THERAPEUTICS, INC.' → 'Halozyme Therapeutics'; 'Apple Inc.' → 'Apple'."""
    s = re.sub(r'\s*\(.*?\)\s*', ' ', str(name or '')).strip().rstrip('.')
    s = re.sub(r'/[A-Z]{2,3}/?$', '', s).strip()                 # SEC's state tags: 'ACME CORP /DE/'
    for _ in range(4):
        s2 = SUFFIX.sub('', s).strip().rstrip(',')
        if s2 == s:
            break
        s = s2
    if s.isupper():
        s = ' '.join(w if len(w) <= 3 and w not in ('THE', 'AND') else w.capitalize() for w in s.split())
    return s


def keys_of(name, ticker):
    """The words a headline must contain to be about the company: the ticker (as a word) or the distinctive start of
    its name (two words when the first is generic)."""
    words = [w for w in re.split(r'\s+', short_name(name)) if w]
    k = []
    if words:
        k.append(' '.join(words[:2]) if words[0].lower() in GENERIC and len(words) > 1 else words[0])
    return [x for x in k if len(x) >= 3], ticker


def words(name, ticker):
    if ticker in MARKET:
        return MARKET[ticker][1]
    nm = short_name(name)
    return f'"{nm}" OR "{ticker} stock" OR "({ticker})"' if nm else f'"{ticker}"'


def query(name, ticker, a, b=None):
    """The search for headlines published from day a to day b (the day before a and b when one day is given)."""
    if b is None:
        d = dt.date.fromisoformat(a)
        a, b = (d - dt.timedelta(days=1)).isoformat(), a
    hi = dt.date.fromisoformat(b) + dt.timedelta(days=1)
    return f'({words(name, ticker)}) after:{a} before:{hi.isoformat()}'


def _text(s):
    return html.unescape(re.sub(r'<[^>]+>', ' ', s or '')).strip()


def parse(body):
    """The feed's items → [[published (UTC ISO), source, title, link]]."""
    out = []
    root = ET.fromstring(body)
    for it in root.iter('item'):
        title = _text(it.findtext('title'))
        src_el = it.find('source')
        src = _text(src_el.text if src_el is not None else '')
        if src and title.endswith(' - ' + src):
            title = title[: -len(src) - 3].strip()
        try:
            when = email.utils.parsedate_to_datetime(it.findtext('pubDate') or '').astimezone(dt.timezone.utc)
        except (TypeError, ValueError):
            continue
        link = (it.findtext('link') or '').strip()
        if title and link.startswith('https://'):
            out.append([when.strftime('%Y-%m-%dT%H:%MZ'), src, title[:240], link])
    return out


def about(name, ticker):
    """A test: does a title name the company (the market: any title)?"""
    if ticker in MARKET:
        return lambda t: True
    names, tk = keys_of(name, ticker)
    tick = re.compile(r'\b' + re.escape(tk) + r'\b')
    nam = re.compile(r'\b(' + '|'.join(re.escape(n) for n in names) + r')\b', re.I) if names else None
    return lambda t: bool(tick.search(t) or (nam and nam.search(t)))


def rank(src, title):
    s = src.lower()
    tier = 0 if any(x in s for x in TOP) else 1 if any(x in s for x in OK_SOURCES) else 2
    return (6 if FLUFF.search(title) else 0) + 2 * tier + (0 if MOVE.search(title) else 1)


def keep(items, name, ticker, a, b=None, limit=None):
    """The headlines about the company published from day a to day b (one day given: that day and the day before, eight
    at most), without the automatic notes and junk sources, most telling first."""
    if b is None:
        d = dt.date.fromisoformat(a)
        a, b, limit = (d - dt.timedelta(days=1)).isoformat(), a, limit or PER_DAY
    ok_title = about(name, ticker)
    lo, hi = (dt.date.fromisoformat(a) - dt.timedelta(days=1)).isoformat(), (dt.date.fromisoformat(b) + dt.timedelta(days=1)).isoformat()
    seen, out = set(), []
    for when, src, title, link in items:
        if any(x in src.lower() for x in DENY) or AUTO.search(title) or not ok_title(title):
            continue
        if not (lo <= when[:10] <= hi):                                     # the feed's days are loose: a day either side
            continue
        k = re.sub(r'\W+', ' ', title.lower()).strip()[:90]
        if k in seen:
            continue
        seen.add(k)
        out.append((rank(src, title), when, [when, src, title, link]))
    out.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in (out[:limit] if limit else out)]


def trading_day(days, when):
    """The trading day a headline could move: its own day before the 16:00 close (or dated only), else the next one;
    None past the last day on file."""
    import bisect
    day, hm = _et(when)
    k = bisect.bisect_left(days, day)
    if k < len(days) and days[k] == day and hm and hm >= '16:00':
        k += 1
    return days[k] if k < len(days) else None


def merge(doc, items, days):
    """The headlines put on their trading days with the ones on file, eight a day, most telling first."""
    by = doc.setdefault('days', {})
    for it in items:
        d = trading_day(days, it[0])
        if d is None:
            continue
        cur = by.setdefault(d, [])
        k = re.sub(r'\W+', ' ', it[2].lower()).strip()[:90]
        if any(re.sub(r'\W+', ' ', x[2].lower()).strip()[:90] == k for x in cur):
            continue
        cur.append(it)
        cur.sort(key=lambda x: (rank(x[1], x[2]), x[0]))
        del cur[PER_DAY:]


def covered(doc):
    """[(from, to)] of the windows searched to the end: not full, or two days at most."""
    out = []
    for a, b, _, n in doc.get('windows') or []:
        if n < FULL or (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days <= 1:
            out.append((a, b))
    return out


def checked_days(doc, days):
    import bisect
    out = set()
    for a, b in covered(doc):
        i, j = bisect.bisect_left(days, a), bisect.bisect_right(days, b)
        out.update(days[i:j])
    return out


def months_back(today, n=MONTHS):
    """[(first, last)] of the last n calendar months, the current one first (to today)."""
    out, y, m = [], today.year, today.month
    for _ in range(n):
        a = dt.date(y, m, 1)
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        out.append((a.isoformat(), min(nxt - dt.timedelta(days=1), today).isoformat()))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out


def wanted(doc, days, closes, today, recent=True):
    """The windows to search for one company, most wanted first: the last week (again each day), the last twelve months
    a month at a time, the two days around each of its biggest moves since FROM (the most extreme first), then the
    months back to three years; none already searched to the end."""
    import move_news as MN
    done = {(a, b) for a, b, *_ in doc.get('windows') or []}
    seen = checked_days(doc, days)
    out = []
    if recent and days:
        lo = (today - dt.timedelta(days=RECENT_DAYS - 1)).isoformat()
        last = max((w[2] for w in doc.get('windows') or [] if w[1] >= today.isoformat() and w[0] <= lo), default='')
        if last[:10] < today.isoformat():
            out.append((lo, today.isoformat()))
    first = days[0] if days else today.isoformat()
    months = [m for m in months_back(today) if m[1] >= first]
    fresh = lambda a, b: (a, b) not in done and not all(d in seen for d in days if a <= d <= b)   # noqa: E731
    out += [m for m in months[:12] if fresh(*m)]
    if len(days) > 30:
        big = sorted(MN.big_days(days, closes).items(), key=lambda kv: (-kv[1], days[kv[0]]))
        for k, _ in big:
            d = days[k]
            if d >= FROM and d not in seen:
                a = (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()
                if (a, d) not in done:
                    out.append((a, d))
    out += [m for m in months[12:] if fresh(*m)]
    return out


def refresh(client, root, comps, bars_of, queries=400, minutes=15.0, today=None, market=('SPY',)):
    """Searches up to `queries` days (round by company, the market and the largest companies first). comps:
    [{'t', 'name'}] largest first; bars_of(ticker) → (days, closes) or None."""
    t0 = time.monotonic()
    today = today or dt.date.today()
    done = {'searched': 0, 'headlines': 0, 'errors': 0, 'blocked': False}
    out_of_time = lambda: time.monotonic() - t0 > minutes * 60          # noqa: E731
    who = [{'t': m, 'name': MARKET[m][0]} for m in market if m in MARKET] + [c for c in comps if c.get('t')]
    queue = []
    for i, c in enumerate(who):
        b = bars_of(c['t'])
        if not b or not b[0]:
            continue
        doc = read_json(path(root, c['t']), None) or {'ticker': c['t'], 'days': {}, 'windows': []}
        ds = wanted(doc, b[0], b[1], today, recent=i < RECENT_TOP)
        if ds:
            queue.append((c, ds))
    hdr = {'User-Agent': 'Mozilla/5.0 (compatible; FilingFlows move-odds headlines; +https://github.com/eurikamonica/filing-flows)',
           'Accept': 'application/rss+xml, application/xml;q=0.9, */*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9'}
    fails = 0
    while queue and done['searched'] < queries and not out_of_time() and not done['blocked']:
        nxt = []
        for c, ws in queue:
            if done['searched'] >= queries or out_of_time() or done['blocked']:
                break
            doc = read_json(path(root, c['t']), None) or {'ticker': c['t'], 'days': {}, 'windows': []}
            doc.update(ticker=c['t'], name=c.get('name'))
            b = bars_of(c['t'])
            n = 0
            while ws and n < PER_COMPANY and done['searched'] < queries and not out_of_time():
                a, z = ws.pop(0)
                q = query(c.get('name'), c['t'], a, z)
                try:
                    raw = parse(client.get(FEED.format(q=quote(q)), headers=hdr))
                except Exception as exc:                                  # noqa: BLE001
                    done['errors'] += 1
                    fails += 1
                    print(f'move headlines {c["t"]} {a}…{z}: {str(exc)[:160]}', flush=True)
                    if fails >= 5 or '429' in str(exc) or '403' in str(exc):
                        done['blocked'] = True                            # asked to slow down: stop for this run
                        break
                    continue
                fails = 0
                n += 1
                done['searched'] += 1
                items = keep(raw, c.get('name'), c['t'], a, z)
                merge(doc, items, b[0])
                done['headlines'] += len(items)
                doc.setdefault('windows', [])
                doc['windows'] = [w for w in doc['windows'] if (w[0], w[1]) != (a, z)] + [[a, z, dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), len(raw)]]
                doc['q'] = words(c.get('name'), c['t'])
                span = (dt.date.fromisoformat(z) - dt.date.fromisoformat(a)).days
                if len(raw) >= FULL and span > 1:                         # full: the two halves, next
                    mid = (dt.date.fromisoformat(a) + dt.timedelta(days=span // 2)).isoformat()
                    ws[:0] = [(a, mid), ((dt.date.fromisoformat(mid) + dt.timedelta(days=1)).isoformat(), z)]
                    done['split'] = done.get('split', 0) + 1
            write_json(path(root, c['t']), doc)
            if ws:
                nxt.append((c, ws))
        queue = nxt
    done['waiting'] = sum(len(w) for _, w in queue)
    done['seconds'] = round(time.monotonic() - t0, 1)
    return done


def _et(utc_iso):
    """'2026-10-29T20:15Z' → ('2026-10-29', '16:15') in New York time; a headline the feed dates only (midnight on the
    US west coast: 07:00 or 08:00 UTC) keeps its date and no time."""
    if utc_iso[11:16] in ('07:00', '08:00'):
        d = dt.date.fromisoformat(utc_iso[:10])
        return d.isoformat(), ''
    import move_news as MN
    t = dt.datetime.strptime(utc_iso[:16], '%Y-%m-%dT%H:%M')
    hm = MN._et(t.strftime('%Y-%m-%dT%H:%M:%S'))
    off = 4 if (t - dt.timedelta(hours=4)).strftime('%H:%M') == hm else 5
    local = t - dt.timedelta(hours=off)
    return local.strftime('%Y-%m-%d'), local.strftime('%H:%M')


def published(root, ticker, days):
    """The headlines on file for one ticker, for its n/ file: ([[trading day, date, 'HH:MM' ET (or '' when the feed gives
    the date only), source, title, link]], [trading days searched to the end]) within its trading days."""
    doc = read_json(path(root, ticker), None)
    if not doc or not days:
        return [], []
    rows = []
    for d, items in sorted((doc.get('days') or {}).items()):
        if d < days[0]:
            continue
        for when, src, title, link in items:
            day, hm = _et(when)
            rows.append([d, day, hm, src, title, link])
    return rows, sorted(checked_days(doc, days))
