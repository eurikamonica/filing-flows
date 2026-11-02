"""Move odds: what was in the company's filings around each day — the news next to "the days like it" (app/moves.py,
docs/moves-view.js).

For every valued company, its EDGAR filing list (data.sec.gov submissions: the recent filings and, back to the first day
of its price history, the older pages) is kept with each filing's form, date, acceptance time and 8-K items; the 8-Ks
filed around its biggest moves are read once each with app/events8k.py's parse_8k (the press release's headline and key
sentences, the topics: earnings, guidance raised or cut, a CEO change, a deal, an offering …), the most extreme days of the
largest companies first, a budget per run. The browser then shows, for each day like the one looked at, what the company
had filed that day or after the close the day before.

Store (branch research-paths):  cache/news/<cik>.json  {'cik', 'ticker', 'sub_at', 'filings': [[acc, form, date,
                                 'HH:MM' accepted (ET), items]], 'read': {acc: {h, q, t, g}}, 'tried': {acc: failures}}
Published:                      public/moves/n/<TICKER>.json  {'format', 'key', 'cik', 'events': [[date, 'HH:MM', form,
                                 items, headline, key sentences, topics, accession]]}, the filings within the price history

    python app/paths.py movenews --root P --universe val/public/index.json [--subs 300 --reads 250 --minutes 25]
"""
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json   # noqa: E402

FORMAT = 1
SUBMISSIONS = 'https://data.sec.gov/submissions/CIK{cik:010d}.json'
OLDER = 'https://data.sec.gov/submissions/{name}'
ARCHIVE = 'https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/'
REFRESH_DAYS = 7               # a company's filing list is asked again after a week
# the forms kept: what a reader would call news (insider forms 3/4/5, 144 and the like are left out)
# (prospectus supplements 424B2 / 424B3 are mostly structured notes and resales, a Form 25 mostly notes that matured: left
# out; one prospectus a day at most)
FORMS = {'8-K', '8-K/A', '6-K', '10-Q', '10-K', '10-K/A', '20-F', '40-F', 'S-1', 'S-3', 'S-4', 'F-1', 'F-3', 'F-4', '424B1', '424B4',
         '424B5', 'SC 13D', 'SC 13D/A', 'SC TO-T', 'SC TO-I', 'SC 14D9', 'DEFM14A', 'PREM14A', '15-12B',
         'NT 10-K', 'NT 10-Q', 'SCHEDULE 13D', 'SCHEDULE 13D/A'}
READ_ITEMS = {'1.01', '1.02', '1.03', '1.05', '2.01', '2.02', '2.03', '2.05', '2.06', '3.01', '3.02', '4.01', '4.02', '5.01', '5.02',
              '5.03', '7.01', '8.01'}
BIG = 10.0                     # an 8-K is read when it falls on (or just before) a day in the bottom or top 10% of one-day moves
PER_COMPANY = 6                # 8-Ks read per company per run (the round goes on with the next company)


def path(root, cik):
    return Path(root) / 'cache' / 'news' / f'{int(cik)}.json'


def load(root, cik):
    return read_json(path(root, cik), None) or {'cik': int(cik), 'filings': [], 'read': {}, 'tried': {}}


def _rows(block):
    """A submissions 'recent' block (or an older page) → [[acc, form, date, 'HH:MM', items]] of the forms kept."""
    out = []
    forms = block.get('form') or []
    for i, form in enumerate(forms):
        if form not in FORMS:
            continue
        acc = (block.get('accessionNumber') or [''] * (i + 1))[i]
        date = (block.get('filingDate') or [''] * (i + 1))[i]
        acc_t = str((block.get('acceptanceDateTime') or [''] * (i + 1))[i] or '')
        items = str((block.get('items') or [''] * (i + 1))[i] or '')
        if not acc or not date:
            continue
        if form.startswith('8-K') and items and set(items.split(',')) <= {'9.01'}:
            continue                                   # exhibits only
        hm = acc_t[11:16] if len(acc_t) >= 16 else ''
        out.append([acc, form, date, _et(acc_t) or hm, items])
    return out


def _et(acc_t):
    """EDGAR's acceptance time ('2026-10-29T20:01:44.000Z', UTC) → 'HH:MM' in New York time (EST/EDT by the US rule)."""
    try:
        t = dt.datetime.strptime(acc_t[:19], '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return ''
    y = t.year
    mar = dt.datetime(y, 3, 8) + dt.timedelta(days=(6 - dt.datetime(y, 3, 8).weekday()) % 7)      # second Sunday of March
    nov = dt.datetime(y, 11, 1) + dt.timedelta(days=(6 - dt.datetime(y, 11, 1).weekday()) % 7)    # first Sunday of November
    dst = mar.replace(hour=7) <= t < nov.replace(hour=6)
    return (t - dt.timedelta(hours=4 if dst else 5)).strftime('%H:%M')


def submissions(client, cik, since):
    """The company's filings kept, back to `since` (the recent block, then older pages until they reach it)."""
    sub = client.json(SUBMISSIONS.format(cik=int(cik)), sec=True)
    f = sub.get('filings') or {}
    rows = _rows(f.get('recent') or {})
    for page in f.get('files') or []:
        if (page.get('filingTo') or '9999') < since:
            continue
        try:
            rows += _rows(client.json(OLDER.format(name=page['name']), sec=True))
        except Exception as exc:                                    # noqa: BLE001
            print(f'move news {cik}: older filings {page.get("name")}: {exc}', flush=True)
    seen, day, out = set(), set(), []
    for r in sorted(rows, key=lambda r: (r[2], r[3], r[0]), reverse=True):
        if r[0] in seen or r[2] < since:
            continue
        fam = (r[2], r[1][:4]) if r[1].startswith(('424B', 'S-', 'F-', '6-K')) else None
        if fam and fam in day:
            continue                                   # one prospectus (or 6-K) a day is enough to say there was one
        seen.add(r[0])
        if fam:
            day.add(fam)
        out.append(r)
    return out


def trading_day(days, date, hm):
    """The index of the trading day a filing could move: its own day when filed before the close (16:00 New York time),
    else the next trading day; −1 when it falls after the last day on file."""
    import bisect
    k = bisect.bisect_left(days, date)
    if k < len(days) and days[k] == date and hm and hm >= '16:00':
        k += 1
    return k if k < len(days) else -1


def big_days(days, closes):
    """{trading-day index: how far out its one-day move is (0–50 percentile points from the middle)} for the days in the
    bottom or top BIG% of the asset's one-day moves."""
    r = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    order = sorted(range(len(r)), key=lambda i: r[i])
    n = len(r)
    out = {}
    for rank, i in enumerate(order):
        p = 100 * (rank + 0.5) / n
        far = 50 - min(p, 100 - p)
        if p <= BIG or p >= 100 - BIG:
            out[i + 1] = far
    return out


def to_read(doc, days, closes):
    """The 8-Ks to read, most extreme day first: on a big-move day (or filed the trading day before it), not read yet."""
    if len(days) < 30:
        return []
    big = big_days(days, closes)
    cand = []
    for acc, form, date, hm, items in doc.get('filings') or []:
        if not form.startswith('8-K') or acc in doc.get('read', {}) or (doc.get('tried') or {}).get(acc, 0) >= 3:
            continue
        if items and not (set(items.split(',')) & READ_ITEMS):
            continue
        k = trading_day(days, date, hm)
        if k < 0:
            continue
        far = big.get(k, -1)
        earnings = '2.02' in items
        if far < 0 and not earnings:
            continue
        cand.append((-(far if far >= 0 else 0) - (5 if earnings else 0), date, acc))
    cand.sort(key=lambda x: x[1], reverse=True)       # the newest first among equally extreme days
    cand.sort(key=lambda x: x[0])
    return [acc for _, _, acc in cand]


def read_8k(client, cik, acc):
    """One 8-K → {h: headline, q: key sentences, t: topics, g: guidance label} (app/events8k.py parse_8k)."""
    import events8k as E
    folder = ARCHIVE.format(cik=int(cik), folder=acc.replace('-', ''))
    txt = client.get(folder + acc + '.txt', sec=True).decode('utf-8', 'replace')
    row = E.parse_8k(txt, acc, folder)
    out = {'h': (row.get('headline') or '')[:200], 'q': (row.get('quote') or '')[:360], 't': row.get('topics') or []}
    if row.get('guidance'):
        out['g'] = row['guidance']
    return out


def refresh(client, root, comps, bars_of, subs=300, reads=250, minutes=25.0, today=None):
    """Brings the filing lists up to date (the stalest first, `subs` per run) and reads up to `reads` 8-Ks (round by
    company, largest first, the most extreme days first). comps: [{'t', 'cik'}] largest first; bars_of(ticker) → (days,
    closes) or None."""
    t0 = time.monotonic()
    today = today or dt.date.today()
    stale = (today - dt.timedelta(days=REFRESH_DAYS)).isoformat()
    done = {'lists': 0, 'read': 0, 'errors': 0, 'companies': 0}
    out_of_time = lambda: time.monotonic() - t0 > minutes * 60        # noqa: E731
    comps = [c for c in comps if c.get('cik')]
    # 1. the filing lists, the stalest first
    order = sorted(comps, key=lambda c: (load(root, c['cik']).get('sub_at') or ''))
    for c in order:
        if done['lists'] >= subs or out_of_time() or done['errors'] > 20:
            break
        doc = load(root, c['cik'])
        if (doc.get('sub_at') or '') >= stale:
            continue
        b = bars_of(c['t'])
        since = b[0][0] if b and b[0] else (today - dt.timedelta(days=3650)).isoformat()
        try:
            doc['filings'] = submissions(client, c['cik'], since)
            doc.update(ticker=c['t'], sub_at=today.isoformat())
            write_json(path(root, c['cik']), doc)
            done['lists'] += 1
        except Exception as exc:                                    # noqa: BLE001
            done['errors'] += 1
            print(f'move news {c["t"]}: filing list: {exc}', flush=True)
    # 2. the 8-Ks around the big moves, a few per company per round
    queue = []
    for c in comps:
        doc = load(root, c['cik'])
        b = bars_of(c['t'])
        if not doc.get('filings') or not b:
            continue
        accs = to_read(doc, b[0], b[1])
        if accs:
            queue.append((c, accs))
    while queue and done['read'] < reads and not out_of_time() and done['errors'] <= 40:
        nxt = []
        for c, accs in queue:
            if done['read'] >= reads or out_of_time():
                break
            doc = load(root, c['cik'])
            for acc in accs[:PER_COMPANY]:
                if done['read'] >= reads or out_of_time():
                    break
                try:
                    doc.setdefault('read', {})[acc] = read_8k(client, c['cik'], acc)
                    done['read'] += 1
                except Exception as exc:                            # noqa: BLE001
                    done['errors'] += 1
                    doc.setdefault('tried', {})[acc] = (doc.get('tried') or {}).get(acc, 0) + 1
                    print(f'move news {c["t"]} {acc}: {exc}', flush=True)
            write_json(path(root, c['cik']), doc)
            if accs[PER_COMPANY:]:
                nxt.append((c, accs[PER_COMPANY:]))
        queue = nxt
    done['companies'] = sum(1 for c in comps if path(root, c['cik']).exists())
    done['waiting'] = sum(len(a) for _, a in queue)
    done['seconds'] = round(time.monotonic() - t0, 1)
    return done


def publish(root, comps, bars_of, market=('SPY',)):
    """public/moves/n/<TICKER>.json for every company with its filing list or headlines on file (and the market's
    headlines): the filings and the news headlines (app/move_headlines.py) within its price history."""
    import move_headlines as MH
    out = Path(root) / 'public' / 'moves' / 'n'
    out.mkdir(parents=True, exist_ok=True)
    written = set()
    for c in [{'t': m} for m in market] + list(comps):
        b = bars_of(c['t'])
        if not b or not b[0]:
            continue
        d0 = b[0][0]
        doc = read_json(path(root, c['cik']), None) if c.get('cik') else None
        ev = []
        for acc, form, date, hm, items in (doc or {}).get('filings') or []:
            if date < d0:
                continue
            r = (doc.get('read') or {}).get(acc) or {}
            ev.append([date, hm, form, items, r.get('h') or '', r.get('q') or '', r.get('t') or [], acc] + ([r['g']] if r.get('g') else []))
        heads, checked = MH.published(root, c['t'], b[0])
        if not ev and not checked:
            continue
        name = f"{c['t']}.json"
        body = {'format': FORMAT, 'key': c['t'], 'generated_at': now(), 'events': ev, 'headlines': heads, 'checked': checked}
        if c.get('cik'):
            body['cik'] = int(c['cik'])
        (out / name).write_text(json.dumps(body, separators=(',', ':')))
        written.add(name)
    for p in out.glob('*.json'):
        if p.name not in written:
            p.unlink()
    return len(written)
