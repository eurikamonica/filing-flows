"""13F history back-fill, run by its own relaying workflow (.github/workflows/holdings-backfill.yml).

The regular collector (collect.py --only holdings, every 15 minutes, in the shared run slot) takes 8 managers a run and
refreshes the ones it already has; at that pace SEC's list of ~12,000 13F filers takes weeks. This worker only takes
managers no run has processed yet, as many as fit in a time budget at a steady ~6–7 SEC requests a second (SEC's
fair-access limit is 10), and writes exactly the files the collector writes for a manager:

    cache/holdings/<cik>.json.gz                 the full parsed history (filings, snapshots, changes)
    shards/holdings/<cik>.json                   the public summary with one row per quarter
    shards/holdings/<cik>-<period>.json          each quarter's positions

plus holdings-backfill.json: the summary row of every manager it finished (the collector merges these into live.json on
its next run, so the catalog, the holders index and the market views pick them up) and its own attempts / back-off.
It never writes live.json or the catalog, so it can run beside the collector without either overwriting the other.

    python app/backfill13f.py --data docs/data --minutes 33
"""
import argparse
import datetime as dt
import gzip
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import read_json, write_json, now  # noqa: E402
from shards import compact_write, safe_path  # noqa: E402
from holdings13f.build import filing_list, load_filing  # noqa: E402
from holdings13f.core import resolve, compare  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATE = 'holdings-backfill.json'


class Blocked(RuntimeError):
    """SEC answered 403: its fair-access block. The run stops (and the relay waits) instead of going on."""


class SecGet:
    """SEC fetches at a fixed pace (one request every `interval` seconds across all hosts), with retries and back-off.
    Nothing is stored on disk (the collector's Client keeps every raw response; a back-fill would fill the runner)."""

    def __init__(self, interval=0.15, max_mb=160, timeout=60):
        ua = (os.environ.get('SEC_USER_AGENT') or '').strip()
        if '@' not in ua or 'example.com' in ua:
            raise SystemExit('Set SEC_USER_AGENT to the project name + a real contact e-mail (SEC requires it)')
        self.ua, self.interval, self.max_bytes, self.timeout = ua, interval, max_mb << 20, timeout
        self.last, self.calls, self.bytes = 0.0, 0, 0

    def get(self, url, immutable=False):
        err = 'request failed'
        for attempt in range(4):
            wait = self.interval - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                with urlopen(Request(url, headers={'User-Agent': self.ua, 'Accept': '*/*', 'Accept-Encoding': 'identity'}), timeout=self.timeout) as r:
                    body = r.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise ValueError(f'response over {self.max_bytes >> 20} MB')
                self.calls += 1
                self.bytes += len(body)
                return body
            except HTTPError as exc:
                err = f'HTTP {exc.code}'
                if exc.code == 403:                      # SEC's rate block: back off hard, then give up on this run
                    time.sleep(60)
                    raise Blocked('HTTP 403 from SEC (rate limit?)') from None
                if exc.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(err) from None
                time.sleep(min(30, 3 * 2 ** attempt))
            except (URLError, TimeoutError, OSError) as exc:
                err = f'network: {exc}'
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(err)

    def json(self, url, immutable=False):
        return json.loads(self.get(url))


def pending(catalog, state, shard=None, now_iso=None):
    """Managers on SEC's 13F list that no run has processed (catalog 'processed' false, not finished here), largest
    filing history and most recent filers first; managers that failed wait out their back-off."""
    done = set(state.get('managers', {}))
    att = state.get('attempts', {})
    now_iso = now_iso or now()
    rows = []
    for r in catalog:
        if r.get('kind', 'holdings') != 'holdings' or r.get('processed'):
            continue
        c = str(int(r['cik']))
        if c in done:
            continue
        a = att.get(c, {})
        if a.get('retry_after') and a['retry_after'] > now_iso:
            continue
        if shard and int(c) % shard[1] != shard[0]:
            continue
        rows.append(r)
    rows.sort(key=lambda r: (str(r.get('latest_filing') or ''), int(r.get('filing_count') or 0)), reverse=True)
    return rows


def process(sec, cik, label, since, as_of=None):
    """One manager, exactly as holdings.collect_holdings builds it."""
    name, metas = filing_list(sec, cik, since)
    filings, notices = [], []
    for meta in metas:
        if as_of and meta['filed'] > as_of:
            continue
        if meta['form'].startswith('13F-NT'):
            notices.append(meta)
            continue
        filings.append(load_filing(sec, meta))
    snapshots = resolve(filings, as_of)
    for i, s in enumerate(snapshots):
        s['changes'] = compare(snapshots[i - 1], s) if i else []
        s['baseline_period'] = snapshots[i - 1]['period'] if i else None
    return {'cik': str(int(cik)), 'name': name, 'label': label or name, 'since': since, 'as_of': as_of, 'filings': filings,
            'snapshots': snapshots, 'notices': notices, 'last_success': now(), 'stale': False}


def write_manager(root, row):
    """The files publish_shards writes for a processed manager; returns its lazy summary row for live.json."""
    root = Path(root)
    cik = row['cik']
    cache = f'cache/holdings/{cik}.json.gz'
    target = root / cache
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(target.with_suffix('.tmp'), 'wt', encoding='utf-8') as f:
        json.dump(row, f, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    target.with_suffix('.tmp').replace(target)
    snaps = row.get('snapshots', [])
    last = snaps[-1] if snaps else {}
    public = []
    for snap in snaps:
        p = f'shards/holdings/{cik}-{snap["period"]}.json'
        compact_write(safe_path(root, p), snap['positions'])
        public.append({**{k: v for k, v in snap.items() if k not in ('positions', 'changes')}, 'positions_shard': p})
    summary = {k: v for k, v in row.items() if k not in ('filings', 'snapshots', 'candidates', '_loaded', 'shard', 'cache')}
    path = f'shards/holdings/{cik}.json'
    compact_write(safe_path(root, path), {**summary, 'snapshots': public})
    summary.update(period_count=len(snaps), latest_period=last.get('period'), position_count=len(last.get('positions', [])),
                   total_usd=last.get('total_usd'), cache=cache, shard=path, backfill=True)
    return summary


def run(data, cfg, minutes=33.0, interval=0.15, shard=None, sec=None, limit=None):
    data = Path(data)
    t0 = time.time()
    catalog = read_json(data / 'catalogs' / 'holdings.json', [])
    state = read_json(data / STATE, {}) or {}
    since, as_of = cfg['since'], cfg.get('as_of')
    if state.get('since') != since or state.get('as_of') != as_of:  # another history range: start over, never mix
        state = {'since': since, 'as_of': as_of, 'managers': {}, 'attempts': {}, 'runs': []}
    state.setdefault('managers', {})
    state.setdefault('attempts', {})
    todo = pending(catalog, state, shard)
    sec = sec or SecGet(interval)
    done = errors = 0
    blocked = None
    for r in todo:
        if time.time() - t0 > minutes * 60 or (limit and done + errors >= limit):
            break
        cik = str(int(r['cik']))
        a = state['attempts'].setdefault(cik, {})
        a['last_attempt'] = now()
        try:
            row = process(sec, cik, r.get('name'), since, as_of)
            state['managers'][cik] = write_manager(data, row)
            a.update(last_success=row['last_success'], error=None, fails=0, retry_after=None)
            done += 1
        except Exception as exc:                 # a parse error's text can contain "403" too: only Blocked stops the run
            errors += 1
            a['error'] = str(exc)[:200]
            a['fails'] = int(a.get('fails') or 0) + 1
            a['retry_after'] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=min(168, 6 * 2 ** a['fails']))).isoformat(timespec='seconds')
            if isinstance(exc, Blocked) or isinstance(exc.__cause__, Blocked):
                blocked = str(exc)
                break
        if (done + errors) % 25 == 0:
            write_json(data / STATE, state)
    left = len(pending(catalog, state, shard))
    stats = {'at': now(), 'minutes': round((time.time() - t0) / 60, 1), 'managers': done, 'errors': errors, 'requests': sec.calls,
             'megabytes': round(sec.bytes / 1e6, 1), 'remaining': left, 'blocked': blocked}
    state['runs'] = (state.get('runs') or [])[-49:] + [stats]
    state['updated_at'] = now()
    write_json(data / STATE, state)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--data', default=str(ROOT / 'docs' / 'data'))
    ap.add_argument('--config', default=str(ROOT / 'config' / 'settings.json'))
    ap.add_argument('--minutes', type=float, default=33)
    ap.add_argument('--interval', type=float, default=0.15, help='seconds between SEC requests (0.15 ≈ 6.7 a second; SEC allows 10)')
    ap.add_argument('--shard', default=None, help='k/N: only managers with CIK mod N = k (parallel jobs share the SEC budget)')
    ap.add_argument('--limit', type=int, default=None)
    a = ap.parse_args()
    cfg = read_json(a.config, {}).get('holdings', {})
    shard = tuple(int(x) for x in a.shard.split('/')) if a.shard else None
    stats = run(a.data, cfg, a.minutes, a.interval, shard, limit=a.limit)
    print(json.dumps(stats), flush=True)
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write(f"remaining={stats['remaining']}\nmanagers={stats['managers']}\nblocked={'yes' if stats['blocked'] else 'no'}\n")


if __name__ == '__main__':
    main()
