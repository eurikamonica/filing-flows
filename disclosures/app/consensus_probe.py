"""TEMPORARY (removed before merge): real samples of the consensus sources (Yahoo quoteSummary with crumb; Nasdaq)."""
import http.cookiejar, json, sys, time, urllib.request
from pathlib import Path
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
out = Path(sys.argv[1] if len(sys.argv) > 1 else 'probe'); out.mkdir(parents=True, exist_ok=True)
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
log = []
def get(url, hdr=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9', **(hdr or {})})
    try:
        with op.open(req, timeout=30) as r:
            b = r.read(); log.append(f'ok {r.status} {len(b)} {url}'); return b
    except urllib.error.HTTPError as e:
        b = e.read(); log.append(f'HTTP {e.code} {len(b)} {url} {b[:150]!r}'); return None
    except Exception as e:
        log.append(f'ERR {type(e).__name__} {e} {url}'); return None
get('https://fc.yahoo.com/')
get('https://finance.yahoo.com/quote/AAPL/')
crumb = (get('https://query2.finance.yahoo.com/v1/test/getcrumb') or b'').decode().strip()
log.append(f'crumb={crumb!r} cookies={[c.name for c in jar]}')
MODS = 'financialData,earningsTrend,earningsHistory,recommendationTrend,upgradeDowngradeHistory,calendarEvents,earnings,price,defaultKeyStatistics,summaryDetail'
for t in ['AAPL', 'MSFT', 'JPM', 'XOM', 'CVNA', 'BRK-B', 'MSTR']:
    b = get(f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{t}?modules={MODS}&crumb={crumb}')
    if b: (out / f'yahoo_{t}.json').write_bytes(b)
    time.sleep(1)
for t in ['AAPL', 'XOM']:
    for ep in ['analyst/{t}/earnings-forecast', 'analyst/{t}/targetprice', 'analyst/{t}/estimate-momentum', 'company/{t}/earnings-surprise', 'analyst/{t}/earnings-date', 'analyst/{t}/ratings']:
        u = 'https://api.nasdaq.com/api/' + ep.format(t=t)
        b = get(u, {'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'})
        if b: (out / f'nasdaq_{t}_{ep.split("/")[-1]}.json').write_bytes(b)
        time.sleep(0.7)
(out / 'log.txt').write_text('\n'.join(log))
print('\n'.join(log))
