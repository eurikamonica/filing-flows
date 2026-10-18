"""TEMPORARY (removed before merge): samples of Polymarket, Kalshi, Yahoo and Nasdaq consensus data."""
import http.cookiejar, json, sys, time, urllib.request, urllib.parse
from pathlib import Path
out = Path(sys.argv[1] if len(sys.argv) > 1 else 'probe'); out.mkdir(parents=True, exist_ok=True)
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
log = []
def get(url, name=None, hdr=None, limit=None):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*', **(hdr or {})})
        with op.open(req, timeout=40) as r:
            b = r.read()
        log.append(f'ok {len(b)} {url}')
        if name:
            (out / name).parent.mkdir(parents=True, exist_ok=True); (out / name).write_bytes(b[:limit] if limit else b)
        return b
    except Exception as e:
        log.append(f'FAIL {type(e).__name__} {e} {url}'); return None
    finally:
        time.sleep(0.4)
G = 'https://gamma-api.polymarket.com'
get(f'{G}/tags?limit=1000', 'poly/tags.json')
for tag in ['earnings', 'stocks', 'companies', 'business', 'tech', 'big-tech', 'nvidia', 'tesla', 'apple', 'ipos', 'finance', 'economy']:
    get(f'{G}/events?tag_slug={tag}&closed=false&limit=200', f'poly/events_{tag}_open.json')
    get(f'{G}/events?tag_slug={tag}&closed=true&limit=200&order=endDate&ascending=false', f'poly/events_{tag}_closed.json')
for q in ['earnings', 'beat earnings', 'NVIDIA', 'Tesla', 'Apple', 'stock price', 'close above', 'revenue', 'EPS']:
    get(f'{G}/public-search?q={urllib.parse.quote(q)}&limit_per_type=50', f'poly/search_{q.replace(" ","_")}.json')
b = get(f'{G}/markets?tag_slug=earnings&closed=false&limit=50', 'poly/markets_earnings.json')
try:
    m = json.loads(b)[0]; tok = json.loads(m['clobTokenIds'])[0]
    get(f'https://clob.polymarket.com/prices-history?market={tok}&interval=max&fidelity=60', 'poly/history_sample.json')
    get(f'https://clob.polymarket.com/midpoint?token_id={tok}', 'poly/midpoint_sample.json')
except Exception as e:
    log.append(f'poly sample {e}')
K = 'https://api.elections.kalshi.com/trade-api/v2'
get(f'{K}/series?limit=1000', 'kalshi/series.json')
for cat in ['Companies', 'Financials', 'Economics', 'Tech']:
    get(f'{K}/series?category={cat}&limit=1000', f'kalshi/series_{cat}.json')
get(f'{K}/events?status=open&limit=200&with_nested_markets=true', 'kalshi/events_open.json')
cur = ''
for i in range(6):
    b = get(f'{K}/events?status=open&limit=200&with_nested_markets=false' + (f'&cursor={cur}' if cur else ''), f'kalshi/events_page{i}.json')
    try:
        cur = json.loads(b).get('cursor') or ''
    except Exception:
        cur = ''
    if not cur:
        break
get(f'{K}/markets?limit=200&status=open', 'kalshi/markets_open.json')
# Yahoo: cookie + crumb, then quoteSummary
get('https://fc.yahoo.com', None)
crumb = get('https://query2.finance.yahoo.com/v1/test/getcrumb', 'yahoo/crumb.txt')
c = crumb.decode() if crumb else ''
mods = 'earningsTrend,earningsHistory,calendarEvents,financialData,recommendationTrend,upgradeDowngradeHistory,earnings,defaultKeyStatistics'
for t in ['AAPL', 'NVDA', 'TSLA', 'JPM', 'XOM', 'SMCI']:
    get(f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{t}?modules={mods}&crumb={urllib.parse.quote(c)}', f'yahoo/{t}.json')
get('https://query1.finance.yahoo.com/v1/finance/calendar/earnings?date=2026-10-20', 'yahoo/calendar.json')
for t in ['AAPL', 'NVDA']:
    get(f'https://api.nasdaq.com/api/analyst/{t}/earnings-forecast', f'nasdaq/{t}_forecast.json', {'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'})
    get(f'https://api.nasdaq.com/api/analyst/{t}/estimate-momentum', f'nasdaq/{t}_momentum.json', {'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'})
get('https://api.nasdaq.com/api/calendar/earnings?date=2026-10-20', 'nasdaq/calendar.json', {'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'})
(out / 'log.txt').write_text('\n'.join(log)); print('\n'.join(log))
