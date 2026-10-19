"""Smart money (4.14): who has been right before, and what they are buying and selling now.

Four groups of disclosed decision makers, each trade scored by what the stock did next:
  f13   13F managers      quarter-over-quarter position changes of every processed manager (cache/holdings); decided
                          by the quarter end, public at the filing date
  etf   active ETFs       quarter-over-quarter share changes in each actively managed ETF's N-PORT portfolio, net of the
                          fund's own creations and redemptions (the median change of the lines it kept); etf-history's
                          cache/nport_active (app/etf.py)
  ins   insiders          Form 4 open-market purchases (P) and sales (S) by officers, directors and 10% owners: SEC's
                          insider transaction data sets (one per quarter, the last 13) plus the Hub's recent Form 4 cache
  gov   officials         US House and Senate periodic transaction reports (stocks only; market.officials_trades)

A trade's score: the stock's return less SPY's from the decision date over H = 63 trading days (about three months; 126
days is kept too). A buy is right when the stock beat SPY, a sale when it lagged it — sales are scored like buys. The
trade's alpha is direction × excess return; "follow" is the same measured from the day after the disclosure, which is
what someone copying it could have had.

An actor's weighted accuracy, per side (buys, sales) and overall:
  each trade weighs w = conviction × |excess return| (excess capped at ±100%; trades in the same stock on the same side
  within a month are one decision, weighing their average), conviction = √(size / the actor's median
  size), between 0.25 and 3 — size is the share of the portfolio for 13F and ETFs, dollars for insiders, the midpoint of
  the disclosed range for officials
  accuracy = Σ w·[right] / Σ w: the share of the absolute excess return that was on the right side
  shrunk toward the group's base rate p0 (that group and side, all actors): with n_eff = (Σw)² / Σw²,
  p = (accuracy · n_eff + p0 · k) / (n_eff + k), k = 8 — a new or little-tested actor starts at the group's rate
  skill weight L = ln(p / (1 − p)): the weight of an independent voter in a log-odds sum (negative when they have been
  wrong more often than right, so their trades count against the side they took)
A stock's score now: each actor's net trade in the window (13F and ETFs: their latest quarter on file; insiders and
officials: 90 days) is a vote d·c·L (d = +1 net buyer / −1 net seller, c = conviction of the net size, at most 3, L for the
side taken). Z = Σ d·c·L; smart net score S = 100 · Z / (Σ c·|L| + λ), λ = 1, from −100 (skilled net selling) to +100
(skilled net buying); the raw net score 100 · Σ d·c / Σ c counts everyone alike.
Backtest (walk-forward): at each month end T, the skills come only from trades whose outcome was known by T and the votes
only from trades public by T; the score is then compared with each stock's excess return over the next 63 trading days —
hit rate, |S|-weighted hit rate, the excess return by score bucket, the rank correlation (IC), for the smart and the raw
score, per group and all together.

    python app/smart.py run --root smart --hub disclosures/docs/data --etf etf [--minutes 30] [--offline]
"""
import argparse
import datetime as dt
import gzip
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import read_json, write_json  # noqa: E402
import market as MK  # noqa: E402
from prices import parse_yahoo  # noqa: E402

GROUPS = ['f13', 'etf', 'ins', 'gov']
LABEL = {'f13': '13F managers', 'etf': 'Active ETFs', 'ins': 'Insiders (Form 4)', 'gov': 'Officials (Congress)',
         'plan': 'Insiders\' 10b5-1 plan trades'}
# the flows pages (public/combined/) also count insiders' pre-arranged 10b5-1 plan trades, as a group of their own: dollars
# that moved, not decisions taken that day, so they never enter the skill scores
CGROUPS = GROUPS + ['plan']
H, H2 = 63, 126
K_PRIOR = 8.0
LAMBDA = 1.0
WINDOW = 90               # days: insiders and officials
QWINDOW = 140             # days: the latest 13F / N-PORT quarter still counts this long after its end
MIN_DW = 0.001            # 13F / ETF: a change must move at least 0.1% of the portfolio
MIN_TRIM = 0.02           # ... and at least 2% of the position
F13_VERSION = 3                                            # 3: share change and dollars per change (combined flows)
INS_PAGE = 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets'
INS_KEEP = 13
MIN_INS_USD = 10_000      # smaller Form 4 trades (plan purchases of a few shares) are noise for this purpose
YAHOO = 'https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=5y&interval=1d'
BROWSER = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
SEC_UA = os.environ.get('SEC_USER_AGENT') or 'Filing Flows research filingflows@gmail.com'
NICE = (2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 15, 1 / 20, 1 / 25, 1 / 30, 1 / 40, 1 / 50, 3 / 2, 2 / 3)
MON = {m: i + 1 for i, m in enumerate(['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])}
BAD_TICKERS = {'', 'NONE', 'NA', 'N-A', 'NULL', 'NOTICKER', 'NO'}


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def log(*a):
    print(*a, flush=True)


def ordinal(day):
    return dt.date.fromisoformat(day).toordinal()


def iso(o):
    return dt.date.fromordinal(int(o)).isoformat()


def _f(v):
    try:
        x = float(str(v).replace(',', '').strip())
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def dmy(s):
    """'15-SEP-2026' (DERA) or '2026-09-15' → '2026-09-15'."""
    s = (s or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s[:10]):
        return s[:10]
    m = re.fullmatch(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', s)
    if not m or m.group(2).upper() not in MON:
        return ''
    try:
        return dt.date(int(m.group(3)), MON[m.group(2).upper()], int(m.group(1))).isoformat()
    except ValueError:
        return ''


def norm_name(s):
    return re.sub(r'[^A-Z0-9]+', ' ', (s or '').upper()).strip()


def tick(t):
    """A listed-ticker spelling (BRK.B → BRK-B) or '' — the first of several, never placeholders."""
    t = re.split(r'[,;/\s]+', (t or '').strip().upper())[0] if t else ''
    t = MK.canon(t)
    return '' if t in BAD_TICKERS else t


def save_gz(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        json.dump(obj, f, separators=(',', ':'))
    tmp.replace(path)


def load_gz(path, default=None):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def wj(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def tsv(z, name):
    import csv
    import io
    csv.field_size_limit(1 << 30)
    m = next((n for n in z.namelist() if n.split('/')[-1].upper() == name.upper()), None)
    if not m:
        return
    with z.open(m) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8', errors='replace', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE)


def fnv(s):
    """FNV-1a (32 bit) of the UTF-8 bytes — the actor bucket, computed the same way by docs/smart.js."""
    h = 0x811c9dc5
    for b in s.encode('utf-8'):
        h = ((h ^ b) * 0x01000193) & 0xffffffff
    return h


def bucket(actor_id):
    return f'{fnv(actor_id) % 128:02x}'


def snap_split(r, value_ratio):
    """k when a quantity ratio r with an unchanged value (0.6–1.6×) is a stock split / reverse split, else 1."""
    if not r or not value_ratio or not (r >= 1.8 or r <= 0.56) or not 0.6 <= value_ratio <= 1.6:
        return 1
    k = min(NICE, key=lambda x: abs(r / x - 1))
    return k if abs(r / k - 1) <= 0.12 else 1


# ------------------------------------------------------------------ 13F
def f13_events_of(m, skip_cusips=frozenset()):
    """One manager's cached 13F history → [[cusip, period, filed, dw, flag, shares, usd]] for each common-share change
    between two consecutive quarters that moved at least MIN_DW of the portfolio (dw > 0 bought, < 0 sold; flag n = new,
    x = exit; shares = the split-adjusted change; usd = shares × the price the filing implies).
    Splits: a nice quantity ratio with an unchanged value is adjusted, not a trade."""
    out = []
    for s in m.get('snapshots', []):
        period = s.get('period') or ''
        if not s.get('complete') or s.get('confidential') or not period:
            continue
        if s.get('baseline_period') != MK._prev_q(period):           # changes over two quarters or more: not one decision
            continue
        tot = s.get('total_usd') or 0
        if tot <= 0:
            continue
        filed = (s.get('filed') or s.get('available_at') or '')[:10]
        for c in s.get('changes', []):
            if c.get('put_call') != 'NONE' or c.get('share_type') != 'SH' or c.get('status') not in ('INCREASE', 'DECREASE', 'NEW', 'EXIT'):
                continue
            cusip = c.get('cusip') or ''
            if not cusip or cusip in skip_cusips:
                continue
            sh, pr = c.get('shares') or 0, c.get('prior_shares') or 0
            v, pv = c.get('value_usd') or 0, c.get('prior_value_usd') or 0
            if sh < 0 or pr < 0 or (not sh and not pr):
                continue
            k = snap_split(sh / pr, v / pv if pv else None) if sh and pr else 1
            d = sh - pr * k
            if not d or (pr and abs(d) / (pr * k) < MIN_TRIM):
                continue
            price = v / sh if sh and v > 0 else (pv / pr / k if pr and pv > 0 else None)
            if not price:
                continue
            dw = d * price / tot
            if abs(dw) < MIN_DW or abs(dw) > 1.5:
                continue
            out.append([cusip, period, filed, round(dw, 5), 'n' if not pr else 'x' if not sh else '', round(d, 2), round(d * price)])
    return out


class GitBlobs:
    """The files of a directory as git blobs: their shas from the tree (no checkout needed), a batched fetch of the blobs
    a partial clone lacks, and a cat-file reader — so the workflow never checks out the thousands of 13F manager files,
    and only the ones that changed since the last run are downloaded and read."""

    def __init__(self, directory):
        self.dir = Path(directory).absolute()
        self.top, self.cat = None, None
        here = self.dir
        while not here.exists() and here != here.parent:      # a sparse checkout may not have the directory at all
            here = here.parent
        try:
            self.top = subprocess.run(['git', '-C', str(here), 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=60).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            self.top = None

    def listing(self):
        """{file name: blob sha} of the directory at HEAD ({} without git)."""
        if not self.top:
            return {}
        rel = os.path.relpath(self.dir, self.top)
        try:
            res = subprocess.run(['git', '-C', self.top, 'ls-tree', '-r', 'HEAD', '--', rel + '/'], capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            return {}
        out = {}
        for line in res.stdout.splitlines():
            meta, _, path = line.partition('\t')
            parts = meta.split()
            if len(parts) == 3 and parts[1] == 'blob':
                out[path.rsplit('/', 1)[-1]] = parts[2]
        return out

    def prefetch(self, shas):
        """One batched fetch of the blobs a blob-less partial clone does not have yet (a no-op in a full clone)."""
        if not self.top or not shas:
            return
        have = subprocess.run(['git', '-C', self.top, 'cat-file', '--batch-check'], input='\n'.join(shas) + '\n', capture_output=True, text=True,
                              env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'}).stdout
        missing = [line.split()[0] for line in have.splitlines() if line.endswith(' missing')]
        for i in range(0, len(missing), 5000):
            subprocess.run(['git', '-C', self.top, '-c', 'fetch.negotiationAlgorithm=noop', 'fetch', 'origin', '--no-tags', '--no-write-fetch-head',
                            '--recurse-submodules=no', '--filter=blob:none', '--stdin'], input='\n'.join(missing[i:i + 5000]) + '\n', text=True,
                           capture_output=True, timeout=1800)

    def read(self, sha):
        if self.cat is None:
            self.cat = subprocess.Popen(['git', '-C', self.top, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.cat.stdin.write((sha + '\n').encode())
        self.cat.stdin.flush()
        head = self.cat.stdout.readline().decode().split()
        if len(head) < 3 or head[1] != 'blob':
            return None
        data = self.cat.stdout.read(int(head[2]))
        self.cat.stdout.read(1)
        return data

    def close(self):
        if self.cat:
            self.cat.stdin.close()
            self.cat.wait(timeout=60)
            self.cat = None


def update_f13(root, hub, universe, minutes=None):
    """Read the managers whose files changed (blob sha) or are new into cache/f13.json.gz; drop managers no longer on
    file. Files are read from disk when checked out, else straight from git."""
    root, hub = Path(root), Path(hub)
    path = root / 'cache' / 'f13.json.gz'
    cache = load_gz(path, {}) or {}
    if cache.get('v') != F13_VERSION:
        cache = {'v': F13_VERSION, 'managers': {}}
    have = cache['managers']
    hdir = hub / 'cache' / 'holdings'
    git = GitBlobs(hdir)
    shas = git.listing()
    on_disk = {p.name: p for p in hdir.glob('*.json.gz')}
    names = sorted(n for n in (set(shas) | set(on_disk)) if n.endswith('.json.gz'))

    def stamp(n):
        if n in shas:
            return shas[n]
        st = on_disk[n].stat()
        return f'{st.st_size}-{int(st.st_mtime)}'

    todo = [n for n in names if (have.get(n[:-8]) or {}).get('sha') != stamp(n)]
    t0, read, errors = time.time(), 0, 0
    git.prefetch([shas[n] for n in todo if n not in on_disk and n in shas])
    fetched = round(time.time() - t0)
    funds = frozenset(c for c, t in universe.cusip_type.items() if t in MK.FUND_TYPES)
    for n in todo:
        if minutes and time.time() - t0 > minutes * 60:
            break
        try:
            raw = on_disk[n].read_bytes() if n in on_disk else git.read(shas[n])
            m = json.loads(gzip.decompress(raw)) if raw else None
        except (OSError, ValueError, EOFError):
            m = None
        if not m:
            errors += 1
            continue
        cik = n[:-8]
        have[cik] = {'sha': stamp(n), 'name': (m.get('label') or m.get('name') or cik)[:90], 'ev': f13_events_of(m, funds)}
        read += 1
        if read % 500 == 0:
            log(f'  13F: {read} of {len(todo)} managers read ({time.time() - t0:.0f}s)')
    git.close()
    if shas:                                               # a full listing: managers whose files are gone leave too
        listed = {n[:-8] for n in shas if n.endswith('.json.gz')}
        for cik in [c for c in have if c not in listed]:
            del have[cik]
    save_gz(path, cache)
    return {'managers': len(have), 'changed': len(todo), 'read': read, 'left': max(0, len(todo) - read - errors), 'errors': errors,
            'events': sum(len(v['ev']) for v in have.values()), 'fetch_seconds': fetched, 'seconds': round(time.time() - t0)}


# ------------------------------------------------------------------ insiders (SEC insider transaction data sets)
def role_of(rel, title):
    rel, title = (rel or '').upper(), (title or '').strip()
    t = title.upper()
    if 'OFFICER' in rel or title:
        for k, v in (('CHIEF EXECUTIVE', 'CEO'), ('CEO', 'CEO'), ('CHIEF FINANCIAL', 'CFO'), ('CFO', 'CFO'), ('PRESIDENT', 'President'),
                     ('CHIEF OPERATING', 'COO'), ('COO', 'COO'), ('CHAIR', 'Chair')):
            if k in t:
                return v
        if 'OFFICER' in rel:
            return 'Officer'
    if 'DIRECTOR' in rel:
        return 'Director'
    if 'TENPERCENT' in rel.replace(' ', '').replace('%', 'PERCENT') or '10' in rel:
        return '10% owner'
    return 'Other'


def process_form345(zpath):
    """One quarterly insider transactions set → trades: open-market purchases (P) and sales (S) on original Form 4s,
    one row per filing, day and direction (a sale reported line by line at several prices is one trade):
    [owner cik, owner name, role, ticker, issuer cik, issuer, date, filed, d, shares, value, 10b5-1 plan]."""
    z = zipfile.ZipFile(zpath)
    sub = {}
    for r in tsv(z, 'SUBMISSION.tsv'):
        if (r.get('DOCUMENT_TYPE') or '').strip() != '4':
            continue
        plan = (r.get('AFF10B5ONE') or '').strip().upper() in ('1', 'Y', 'TRUE', 'X')
        sub[r['ACCESSION_NUMBER']] = (dmy(r.get('FILING_DATE')), (r.get('ISSUERCIK') or '').lstrip('0'), (r.get('ISSUERNAME') or '').strip()[:60],
                                      tick(r.get('ISSUERTRADINGSYMBOL')), plan)
    own = {}
    for r in tsv(z, 'REPORTINGOWNER.tsv'):
        a = r['ACCESSION_NUMBER']
        if a in sub and a not in own:                       # joint filers report one trade: the first owner listed
            own[a] = ((r.get('RPTOWNERCIK') or '').lstrip('0'), (r.get('RPTOWNERNAME') or '').strip()[:80],
                      role_of(r.get('RPTOWNER_RELATIONSHIP'), r.get('RPTOWNER_TITLE')))
    agg = {}
    for r in tsv(z, 'NONDERIV_TRANS.tsv'):
        code = (r.get('TRANS_CODE') or '').strip().upper()
        a = r.get('ACCESSION_NUMBER')
        if code not in ('P', 'S') or a not in sub or a not in own:
            continue
        day, sh, px = dmy(r.get('TRANS_DATE')), _f(r.get('TRANS_SHARES')), _f(r.get('TRANS_PRICEPERSHARE'))
        if not day or not sh or not px or sh <= 0 or px <= 0:
            continue
        x = agg.setdefault((a, day, code), [0.0, 0.0])
        x[0] += sh
        x[1] += sh * px
    rows = []
    for (a, day, code), (sh, val) in agg.items():
        filed, icik, iname, tk, plan = sub[a]
        ocik, oname, role = own[a]
        if not tk or not oname or val < 1000:
            continue
        rows.append([ocik, oname, role, tk, icik, iname, day, filed or day, 1 if code == 'P' else -1, round(sh, 2), round(val), int(plan)])
    rows.sort(key=lambda r: (r[6], r[3], r[1]))
    return rows


def ins_links(html_text):
    links = re.findall(r'href="([^"]*?(\d{4})q([1-4])_form345\.zip)"', html_text, re.I)
    out = {}
    for href, y, q in links:
        url = href if href.startswith('http') else 'https://www.sec.gov' + href
        out[f'{y}q{q}'] = url
    return dict(sorted(out.items()))


def http_get(url, ua, timeout=120):
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def collect_insiders(root, tmp=None):
    """Download and process the insider transaction sets not processed yet (the newest INS_KEEP quarters)."""
    root = Path(root)
    d = root / 'cache' / 'ins'
    d.mkdir(parents=True, exist_ok=True)
    links = ins_links(http_get(INS_PAGE, SEC_UA, 60).decode('utf-8', 'replace'))
    keep = list(links)[-INS_KEEP:]
    rep = {}
    for q in reversed(keep):
        out = d / f'{q}.json.gz'
        if out.exists():
            continue
        t0 = time.time()
        zp = Path(tmp or '/tmp') / f'{q}_form345.zip'
        try:
            zp.write_bytes(http_get(links[q], SEC_UA, 600))
            rows = process_form345(zp)
            save_gz(out, {'quarter': q, 'source': links[q], 'at': now(), 'rows': rows})
            rep[q] = [len(rows), round(time.time() - t0)]
            log(f'insiders {q}: {len(rows)} trades in {time.time() - t0:.0f}s')
        except Exception as exc:
            log(f'::warning::insiders {q}: {exc}')
            rep[q] = str(exc)[:160]
        finally:
            zp.unlink(missing_ok=True)
        time.sleep(0.5)
    for p in d.glob('*.json.gz'):
        if p.name[:-8] not in keep:
            p.unlink()
    return rep


def quarter_end(q):
    y, n = int(q[:4]), int(q[5])
    return (dt.date(y + (n == 4), 1 if n == 4 else 3 * n + 1, 1) - dt.timedelta(days=1)).isoformat()


# ------------------------------------------------------------------ prices
def price_file(ticker):
    return re.sub(r'[^A-Za-z0-9-]', '_', ticker.upper()) + '.json.gz'


class Prices:
    """Daily closes per ticker: the Hub's price cache, topped up into this branch's cache/prices for tickers it lacks."""

    def __init__(self, root, hub):
        self.root, self.hub = Path(root), Path(hub) if hub else None
        self.dir = self.root / 'cache' / 'prices'
        self.dir.mkdir(parents=True, exist_ok=True)
        self.series = {}
        self.missing = read_json(self.dir / '_missing.json', {}) or {}
        self.fetched, self.errors = 0, []

    def _load(self, path):
        d = load_gz(path)
        if not d or not d.get('rows'):
            return None
        rows = [r for r in d['rows'] if r and r[1] and r[1] > 0]
        if len(rows) < 5:
            return None
        return (np.array([ordinal(r[0]) for r in rows], dtype=np.int32), np.array([float(r[1]) for r in rows]), d.get('fetched_at') or '')

    def load(self, tickers):
        for t in tickers:
            if t in self.series:
                continue
            best = None
            for base in ([self.hub / 'cache' / 'prices'] if self.hub else []) + [self.dir]:
                p = base / price_file(t)
                if p.exists():
                    s = self._load(p)
                    if s and (best is None or s[0][-1] > best[0][-1]):
                        best = s
            self.series[t] = best
        return self

    def get(self, t):
        s = self.series.get(t)
        return (s[0], s[1]) if s else None

    def top_up(self, tickers, minutes=10.0, workers=6, refresh_days=6):
        """Fetch daily closes (5 years) from Yahoo for tickers with no series or a stale one, until the time budget."""
        today = dt.date.today().toordinal()
        todo = []
        for t in tickers:
            s = self.series.get(t)
            if s and today - s[0][-1] <= 5:
                continue
            own = self.dir / price_file(t)
            if own.exists() and s and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(s[2] or '2000-01-01T00:00:00+00:00')).days < refresh_days:
                continue
            miss = self.missing.get(t)
            if miss and (dt.date.today() - dt.date.fromisoformat(miss)).days < 30:
                continue
            todo.append(t)
        t0, blocked = time.time(), [0]

        def one(t):
            if time.time() - t0 > minutes * 60 or blocked[0] >= 25:
                return t, None, 'budget'
            try:
                req = urllib.request.Request(YAHOO.format(symbol=t), headers={'User-Agent': BROWSER, 'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=30) as r:
                    payload = json.loads(r.read().decode('utf-8'))
                return t, parse_yahoo(payload, '2021-01-01'), None
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    blocked[0] += 1
                    time.sleep(5)
                return t, None, f'HTTP {exc.code}'
            except Exception as exc:
                return t, None, str(exc)[:80]

        got = 0
        with ThreadPoolExecutor(workers) as pool:
            for t, rows, err in pool.map(one, todo):
                if err == 'budget':
                    continue
                self.fetched += 1
                if rows:
                    save_gz(self.dir / price_file(t), {'ticker': t, 'source': 'yahoo', 'fetched_at': now(), 'rows': [[r[0], round(r[1], 4)] for r in rows]})
                    self.series.pop(t, None)
                    self.load([t])
                    got += 1
                    self.missing.pop(t, None)
                elif err and (err.startswith('HTTP 404') or 'No chart result' in err or 'No daily rows' in err):
                    self.missing[t] = dt.date.today().isoformat()
                elif err:
                    self.errors.append(f'{t}: {err}')
        write_json(self.dir / '_missing.json', self.missing)
        return {'wanted': len(todo), 'fetched': self.fetched, 'saved': got, 'rate_limited': blocked[0], 'errors': self.errors[:20]}


# ------------------------------------------------------------------ events
class Events:
    """Every trade of every group as columns (numpy), with the actors and tickers they point to."""

    def __init__(self):
        self.actors, self.aidx = [], {}
        self.tickers, self.tidx = [], {}
        self.cols = defaultdict(list)
        self.plan = []                                      # (ticker, day, direction, dollars, owner key, owner name)

    def actor(self, aid, name, group, sub=''):
        i = self.aidx.get(aid)
        if i is None:
            i = self.aidx[aid] = len(self.actors)
            self.actors.append({'id': aid, 'name': name, 'g': group, 'sub': sub})
        elif sub and not self.actors[i]['sub']:
            self.actors[i]['sub'] = sub
        return i

    def add(self, a, ticker, day, known, d, size, ref='', usd=None, shares=None):
        if not ticker or not day:
            return
        ti = self.tidx.get(ticker)
        if ti is None:
            ti = self.tidx[ticker] = len(self.tickers)
            self.tickers.append(ticker)
        c = self.cols
        c['a'].append(a)
        c['t'].append(ti)
        c['day'].append(ordinal(day))
        c['known'].append(ordinal(known) if known else ordinal(day) + 3)
        c['d'].append(1 if d > 0 else -1)
        c['size'].append(abs(size or 0.0))
        c['ref'].append(ref)
        c['usd'].append(abs(usd) if usd else np.nan)       # dollars traded (13F: refined from daily closes in fill_usd)
        c['sh'].append(abs(shares) if shares else np.nan)

    def freeze(self):
        c = self.cols
        self.a = np.array(c['a'], dtype=np.int32)
        self.t = np.array(c['t'], dtype=np.int32)
        self.day = np.array(c['day'], dtype=np.int32)
        self.known = np.maximum(np.array(c['known'], dtype=np.int32), self.day)
        self.d = np.array(c['d'], dtype=np.int8)
        self.size = np.array(c['size'], dtype=np.float64)
        self.usd = np.array(c['usd'], dtype=np.float64)
        self.sh = np.array(c['sh'], dtype=np.float64)
        self.ref = c['ref']
        self.ag = np.array([GROUPS.index(x['g']) for x in self.actors], dtype=np.int8)
        self.g = self.ag[self.a] if len(self.a) else np.zeros(0, np.int8)
        self.n = len(self.a)
        del self.cols
        return self.convictions()

    def convictions(self):
        """conviction: √(size / the actor's median size), 0.25–3."""
        med = np.ones(len(self.actors))
        if self.n:
            order = np.lexsort((self.size, self.a))
            a_sorted = self.a[order]
            starts = np.r_[0, np.flatnonzero(np.diff(a_sorted)) + 1]
            ends = np.r_[starts[1:], len(a_sorted)]
            for s, e in zip(starts, ends):
                vals = self.size[order[s:e]]
                m = vals[(e - s) // 2]
                med[a_sorted[s]] = m if m > 0 else 1.0
        self.c = np.clip(np.sqrt(np.where(self.size > 0, self.size, 0) / med[self.a]), 0.25, 3.0) if self.n else np.zeros(0)
        return self


def sec_ciks(hub):
    """SEC's company tickers as {cik: [tickers]} and {ticker: cik} (the Hub's weekly cache)."""
    by_cik, by_t = defaultdict(list), {}
    for r in (read_json(Path(hub) / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []):
        t, c = tick(r.get('ticker')), str(r.get('cik') or '').lstrip('0')
        if t and c:
            by_cik[c].append(t)
            by_t.setdefault(t, c)
    return by_cik, by_t


def issuer_ticker(icik, tk, ciks):
    """The ticker a Form 4 is about: the filer's own symbol when SEC lists it for that issuer, SEC's first ticker for the
    issuer otherwise; a symbol SEC gives to another company is dropped (a typo or a stale ticker)."""
    by_cik, by_t = ciks
    icik = (icik or '').lstrip('0')
    if icik and by_cik.get(icik):
        return tk if tk in by_cik[icik] else by_cik[icik][0]
    if tk and by_t.get(tk) and icik and by_t[tk] != icik:
        return ''
    return tk


def fix_insider_usd(E, P):
    """Form 4 dollars against the market: a price more than 3× away from that day's close is a filing error (a price
    typed in the shares box, cents for dollars …) — the shares × the close is used instead; with no close, a price over
    $10,000 a share drops the dollar value. Returns how many trades were corrected."""
    idx = np.flatnonzero((E.g == 2) & ~np.isnan(E.sh) & (E.sh > 0))
    if not len(idx):
        return 0
    idx = idx[np.argsort(E.t[idx], kind='stable')]
    ts = E.t[idx]
    starts = np.r_[0, np.flatnonzero(np.diff(ts)) + 1]
    ends = np.r_[starts[1:], len(idx)]
    fixed = 0
    for s0, e0 in zip(starts, ends):
        ii = idx[s0:e0]
        px = E.usd[ii] / E.sh[ii]
        ser = P.get(E.tickers[ts[s0]])
        close = np.full(len(ii), np.nan)
        if ser is not None:
            days, cl = ser
            i0 = np.searchsorted(days, E.day[ii], 'right') - 1
            ok = (i0 >= 0) & (E.day[ii] - days[np.maximum(i0, 0)] <= 7)
            close[ok] = cl[np.maximum(i0, 0)[ok]]
        ratio = px / close
        bad = ~np.isnan(close) & ((ratio > 3) | (ratio < 1 / 3))
        E.usd[ii[bad]] = E.sh[ii[bad]] * close[bad]
        nob = np.isnan(close) & (px > 10_000)
        E.usd[ii[nob]] = np.nan
        fixed += int(bad.sum() + nob.sum())
    m = E.g == 2
    E.size[m] = np.nan_to_num(E.usd[m])
    E.convictions()
    return fixed


def build_events(root, hub, etf_root, universe, log_stats):
    """All four groups' trades → Events."""
    E = Events()
    root, hub = Path(root), Path(hub)
    # 13F
    cache = load_gz(root / 'cache' / 'f13.json.gz', {}) or {}
    n13 = 0
    for cik, m in (cache.get('managers') or {}).items():
        a = None
        for ev in m['ev']:
            cusip, period, filed, dw, flag = ev[:5]
            t = universe.cusip_ticker.get(cusip)
            if not t:
                continue
            if a is None:
                a = E.actor('f:' + cik, m['name'], 'f13')
            E.add(a, t, period, filed or None, dw, abs(dw), flag, usd=ev[6] if len(ev) > 6 else None, shares=ev[5] if len(ev) > 5 else None)
            n13 += 1
    # active ETFs
    netf = 0
    if etf_root:
        netf = add_etf_events(E, Path(etf_root), universe)
    # insiders: the data sets, then the Hub's Form 4 cache after the newest set's quarter
    ciks = sec_ciks(hub)
    nins, last_q = 0, ''
    seen = set()
    for p in sorted((root / 'cache' / 'ins').glob('*.json.gz')):
        d = load_gz(p, {}) or {}
        last_q = max(last_q, d.get('quarter') or p.name[:6])
        for ocik, oname, role, tk, icik, iname, day, filed, dd, sh, val, plan in d.get('rows', []):
            if plan:                                       # pre-arranged 10b5-1 trades are not decisions made then: flows only
                tk = issuer_ticker(icik, tk, ciks)
                key = ('plan', norm_name(oname), tk, day, dd)
                if tk and val and key not in seen:
                    seen.add(key)
                    E.plan.append((tk, ordinal(day), dd, float(val), norm_name(oname), oname))
                continue
            if val < MIN_INS_USD:                          # tiny ones are noise
                continue
            tk = issuer_ticker(icik, tk, ciks)
            if not tk:
                continue
            key = (norm_name(oname), tk, day, dd)
            if key in seen:
                continue
            seen.add(key)
            a = E.actor('i:' + norm_name(oname), oname, 'ins', role)
            E.add(a, tk, day, filed, dd, val, iname, usd=val, shares=sh)
            nins += 1
    cut = quarter_end(last_q) if last_q else '0000'
    for r in load_gz(hub / 'cache' / 'insiders' / 'trades.json.gz', []) or []:
        if (r.get('date') or '') <= cut or r.get('code') not in ('P', 'S'):
            continue
        if r.get('plan_10b5_1'):
            tk = issuer_ticker(str(r.get('issuer_cik') or ''), tick(r.get('ticker')), ciks)
            key = ('plan', norm_name(r.get('insider') or ''), tk, r['date'], 1 if r['code'] == 'P' else -1)
            if tk and r.get('insider') and r.get('value') and key not in seen:
                seen.add(key)
                E.plan.append((tk, ordinal(r['date']), key[4], float(r['value']), key[1], r['insider']))
            continue
        tk = issuer_ticker(str(r.get('issuer_cik') or ''), tick(r.get('ticker')), ciks)
        if not tk or not r.get('insider') or (r.get('value') or 0) < MIN_INS_USD:
            continue
        key = (norm_name(r['insider']), tk, r['date'], 1 if r['code'] == 'P' else -1)
        if key in seen:
            continue
        seen.add(key)
        a = E.actor('i:' + norm_name(r['insider']), r['insider'], 'ins', r.get('title') or r.get('role') or '')
        day = r['date']
        E.add(a, tk, day, (dt.date.fromisoformat(day) + dt.timedelta(days=3)).isoformat(), key[3], r.get('value') or 0, (r.get('issuer') or '')[:60],
              usd=r.get('value') or 0, shares=r.get('shares'))
        nins += 1
    # officials
    ngov = 0
    try:
        trades, _ = MK.officials_trades(hub, universe)
    except Exception as exc:
        trades = []
        log_stats.setdefault('errors', []).append(f'officials: {exc}')
    for t in trades:
        kind = t.get('type')
        if kind not in ('purchase', 'sale', 'partial sale') or t.get('ticker_status') != 'listed' or t.get('asset_type') not in ('ST', '', None):
            continue
        tk = tick(t.get('ticker_canon') or t.get('ticker'))
        if not tk or not t.get('person') or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', t.get('date') or ''):
            continue
        lo, hi = t.get('amount_min') or 0, t.get('amount_max') or t.get('amount_min') or 0
        a = E.actor('g:' + norm_name(t['person']), t['person'], 'gov', t.get('jurisdiction') or '')
        known = t.get('filed_date') or t.get('notified') or None
        E.add(a, tk, t['date'], known if known and re.fullmatch(r'\d{4}-\d{2}-\d{2}', known) else None, 1 if kind == 'purchase' else -1, (lo + hi) / 2, t.get('owner') or '',
              usd=(lo + hi) / 2)
        ngov += 1
    log_stats['events'] = {'f13': n13, 'etf': netf, 'ins': nins, 'gov': ngov}
    log(f'events: {log_stats["events"]}')
    return E.freeze()


def add_etf_events(E, etf_root, universe):
    """Active ETFs' quarter-over-quarter share changes (etf-history cache/nport_active), net of the fund's own scaling."""
    sym = {}
    idx = read_json(etf_root / 'public' / 'index.json', {}) or {}
    F = idx.get('fields') or []
    if 'series' in F and 'symbol' in F:
        si, yi = F.index('series'), F.index('symbol')
        for r in idx.get('rows') or []:
            if r[si]:
                sym.setdefault(r[si], r[yi])
    snaps = defaultdict(dict)
    for p in sorted((etf_root / 'cache' / 'nport_active').glob('*.json.gz')):
        for s, rec in ((load_gz(p, {}) or {}).get('funds') or {}).items():
            if rec.get('date') and rec.get('pos'):
                snaps[s][rec['date']] = rec
    n = 0
    for s, by_date in snaps.items():
        dates = sorted(by_date)
        a = None
        for d0, d1 in zip(dates, dates[1:]):
            gap = (dt.date.fromisoformat(d1) - dt.date.fromisoformat(d0)).days
            if not 45 <= gap <= 125:
                continue
            r0, r1 = by_date[d0], by_date[d1]
            na = r1.get('na') or 0
            if na <= 0:
                continue
            p0 = {(x[1] or x[0]): x for x in r0['pos']}
            p1 = {(x[1] or x[0]): x for x in r1['pos']}
            ratios = sorted(p1[k][2] / p0[k][2] for k in p0.keys() & p1.keys() if p0[k][2] > 0 and p1[k][2] > 0)
            g = ratios[len(ratios) // 2] if len(ratios) >= 5 else 1.0
            if not 0.2 <= g <= 5:
                g = 1.0
            for k in p0.keys() | p1.keys():
                x0, x1 = p0.get(k), p1.get(k)
                b1 = x1[2] if x1 else 0.0
                b0 = x0[2] * g if x0 else 0.0
                if x0 and x1 and b0 > 0 and b1 > 0:
                    vr = (x1[3] / x0[3] / g) if x0[3] else None
                    b0 *= snap_split(b1 / b0, vr)
                dlt = b1 - b0
                if not dlt or abs(dlt) / max(b0, b1) < MIN_TRIM:
                    continue
                px = (x1[3] / x1[2]) if x1 and x1[2] and x1[3] else ((x0[3] / x0[2]) if x0 and x0[2] and x0[3] else None)
                if not px or px <= 0:
                    continue
                dw = dlt * px / na
                if abs(dw) < MIN_DW or abs(dw) > 1.5:
                    continue
                x = x1 or x0
                t = tick(x[0]) if x[0] else ''
                if not t or not universe.known(t):
                    t = universe.cusip_ticker.get(x[1] or '') or t
                if not t:
                    continue
                if a is None:
                    a = E.actor('e:' + s, (sym.get(s) + ' · ' if sym.get(s) else '') + (r1.get('name') or s)[:70], 'etf', sym.get(s) or '')
                E.add(a, t, d1, r1.get('filed') or None, dw, abs(dw), 'n' if not x0 else 'x' if not x1 else '', usd=dlt * px, shares=dlt)
                n += 1
    return n


# ------------------------------------------------------------------ outcomes
def outcomes(E, P, spy, today=None):
    """Excess return over SPY after each trade: at H and H2 trading days from the decision date, and at H from the day
    after the disclosure (follow). end = the day the H outcome is known (inf while pending or unscorable)."""
    n = E.n
    ex, ex2, fol = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    end = np.full(n, np.iinfo(np.int32).max, dtype=np.int64)
    pdate = np.full(n, 0, dtype=np.int32)
    sd, sc = spy
    today = today or dt.date.today().toordinal()
    order = np.argsort(E.t, kind='stable')
    ts = E.t[order]
    starts = np.r_[0, np.flatnonzero(np.diff(ts)) + 1] if n else np.zeros(0, int)
    ends = np.r_[starts[1:], n] if n else np.zeros(0, int)

    def spy_ret(d0, d1):
        j0 = np.searchsorted(sd, d0, 'right') - 1
        j1 = np.searchsorted(sd, d1, 'right') - 1
        ok = (j0 >= 0) & (j1 >= 0)
        r = np.full(len(d0), np.nan)
        r[ok] = sc[j1[ok]] / sc[j0[ok]] - 1
        return r

    for s, e in zip(starts, ends):
        idx = order[s:e]
        ser = P.get(E.tickers[ts[s]])
        if ser is None:
            continue
        days, cl = ser
        L = len(days)
        i0 = np.searchsorted(days, E.day[idx], 'right') - 1
        ok = (i0 >= 0) & (E.day[idx] - days[np.maximum(i0, 0)] <= 7)
        i0c = np.maximum(i0, 0)
        pdate[idx[ok]] = days[i0c[ok]]
        for hh, out, is_main in ((H, ex, True), (H2, ex2, False)):
            i1 = i0c + hh
            good = ok & (i1 < L)
            if good.any():
                gi = idx[good]
                r = cl[i1[good]] / cl[i0c[good]] - 1
                out[gi] = r - spy_ret(days[i0c[good]], days[i1[good]])
                if is_main:
                    end[gi] = days[i1[good]]
        f0 = np.searchsorted(days, E.known[idx], 'right')     # the first close after the disclosure
        f1 = f0 + H
        good = (f0 < L) & (f1 < L) & ok
        if good.any():
            gi = idx[good]
            fol[gi] = cl[f1[good]] / cl[f0[good]] - 1 - spy_ret(days[f0[good]], days[f1[good]])
    stale = np.isnan(ex) & (pdate > 0)
    return {'ex': ex, 'ex2': ex2, 'fol': fol, 'end': end, 'priced': pdate > 0, 'pending': stale}


# ------------------------------------------------------------------ skill
def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def skills(E, O, mask, u=0.5, k=K_PRIOR):
    """Per actor: weighted accuracy, the shrunk posterior p and the skill weight L for buys, sales and both, from the
    trades in mask (outcome known). u is the reference — the weighted rate at which any stock beat SPY over the same
    kind of window (most stocks lag the index, so a random buy is right less than half the time and a random sale more):
    L(buy) = logit(p) − logit(u), L(sale) = logit(p) − logit(1 − u), so a random picker weighs zero, a group whose trades
    beat random picks starts above zero, and an actor who has been wrong more than random counts against their side.
    One decision, not twenty: an actor's trades in the same stock on the same side within a month (an insider selling
    a little every day) are one decision for the accuracy and the evidence — their weight is the average of the trades',
    their rightness the weighted share — while the hit rate and alpha still count every trade."""
    na = len(E.actors)
    m = mask & ~np.isnan(O['ex'])
    a, d, g, t, day = E.a[m].astype(np.int64), E.d[m], E.g[m].astype(np.int64), E.t[m].astype(np.int64), E.day[m].astype(np.int64)
    exv = np.clip(O['ex'][m], -1, 1)
    w = E.c[m] * np.abs(exv)
    right = (d * exv > 0).astype(float)
    side = (d < 0).astype(np.int64)
    # decisions: (actor, stock, side, 30-day block)
    ckey = ((a * max(1, len(E.tickers)) + t) * 2 + side) * 40000 + day // 30
    uniq, inv = np.unique(ckey, return_inverse=True) if len(ckey) else (np.zeros(0, np.int64), np.zeros(0, np.int64))
    nc = len(uniq)
    cnt = np.bincount(inv, None, nc)
    cw = np.bincount(inv, w, nc)
    cwr = np.bincount(inv, w * right, nc)
    Wc = cw / np.maximum(cnt, 1)                           # the decision's weight: the average trade's
    Rc = np.where(cw > 0, cwr / np.where(cw > 0, cw, 1), 0.0)
    first = np.zeros(nc, dtype=np.int64)
    if nc:
        first[inv[::-1]] = np.arange(len(inv))[::-1]       # any trade of the decision: actor, side and group agree
    ca, cs, cg = a[first], side[first], g[first]
    out = {}
    gsize = len(GROUPS)
    ag = E.ag.astype(np.int64)
    for name, size, gs, key_t, key_c, gkey_c in (('side', na * 2, gsize * 2, a * 2 + side, ca * 2 + cs, cg * 2 + cs),
                                                 ('all', na, gsize, a, ca, cg)):
        N = np.bincount(key_t, None, size)
        Nr = np.bincount(key_t, right, size)
        A = np.bincount(key_t, d * exv, size)
        W = np.bincount(key_c, Wc, size)
        Wr = np.bincount(key_c, Wc * Rc, size)
        W2 = np.bincount(key_c, Wc * Wc, size)
        D = np.bincount(key_c, None, size)
        GW = np.bincount(gkey_c, Wc, gs)
        GWr = np.bincount(gkey_c, Wc * Rc, gs)
        ref = np.tile([u, 1 - u], gsize) if name == 'side' else np.full(gsize, 0.5)
        p0 = np.clip(np.where(GW > 0, GWr / np.where(GW > 0, GW, 1), ref), 0.3, 0.7)
        prior = p0[np.repeat(ag, 2) * 2 + np.tile([0, 1], na)] if name == 'side' else p0[ag]
        acc = np.where(W > 0, Wr / np.where(W > 0, W, 1), np.nan)
        neff = np.where(W2 > 0, W * W / np.where(W2 > 0, W2, 1), 0.0)
        p = (np.nan_to_num(acc, nan=0.5) * neff + prior * k) / (neff + k)
        out[name] = {'n': N, 'nr': Nr, 'decisions': D, 'acc': acc, 'neff': neff, 'p': p, 'alpha': np.where(N > 0, A / np.maximum(N, 1), np.nan), 'p0': p0}
    sd = out['side']
    sd['L'] = np.clip(logit(sd['p']) - logit(np.tile([u, 1 - u], na)), -2.5, 2.5)
    Ls, ne = sd['L'].reshape(na, 2), sd['neff'].reshape(na, 2)
    out['all']['L'] = np.where(ne.sum(1) > 0, (Ls * ne).sum(1) / np.maximum(ne.sum(1), 1e-9), Ls.mean(1))   # the sides, by evidence
    out['L_side'] = Ls
    out['u'] = u
    return out


def ref_rate(fwd, dates, T=None):
    """The weighted share of stock-windows that beat SPY (|excess|-weighted, like the accuracy), from the month-end
    windows whose outcome was known by T (all of them when T is None)."""
    if fwd is None or not fwd.size:
        return 0.5
    cols = [j for j, d in enumerate(dates) if T is None or d + 92 <= T]
    if not cols:
        return 0.5
    f = np.clip(fwd[:, cols], -1, 1)
    f = f[~np.isnan(f)]
    if len(f) < 200:
        return 0.5
    w = np.abs(f)
    return float(np.clip((w * (f > 0)).sum() / w.sum(), 0.3, 0.7))


def votes(E, T, Lside, groups=None):
    """Each actor's net trade per stock in the window ending at T (public by T) → per-ticker sums for the smart and raw
    scores, overall and per group. Returns dict of arrays over E.tickers plus the vote rows."""
    nt = len(E.tickers)
    q = (E.g <= 1)                                         # f13, etf: quarterly portfolios
    sel = (E.known <= T) & (E.day <= T) & np.where(q, E.day >= T - QWINDOW, E.day > T - WINDOW)
    if groups is not None:
        sel &= np.isin(E.g, groups)
    idx = np.flatnonzero(sel)
    if not len(idx):
        return None
    qi = idx[q[idx]]
    if len(qi):                                            # only each manager's / fund's latest quarter
        latest = np.full(len(E.actors), -1, dtype=np.int64)
        np.maximum.at(latest, E.a[qi], E.day[qi])
        keep = ~q[idx] | (E.day[idx] == latest[E.a[idx]])
        idx = idx[keep]
    key = E.a[idx].astype(np.int64) * nt + E.t[idx]
    uniq, inv = np.unique(key, return_inverse=True)
    net = np.bincount(inv, E.d[idx] * E.c[idx], len(uniq))
    last = np.zeros(len(uniq), dtype=np.int64)
    np.maximum.at(last, inv, E.day[idx])
    va, vt = (uniq // nt).astype(np.int64), (uniq % nt).astype(np.int64)
    dv = np.sign(net)
    nz = dv != 0
    va, vt, dv, net, last = va[nz], vt[nz], dv[nz], net[nz], last[nz]
    cv = np.minimum(np.abs(net), 3.0)
    Lv = Lside[va, (dv < 0).astype(int)]
    vg = E.ag.astype(np.int64)[va]
    res = {'rows': (va, vt, dv, cv, Lv, last, vg)}
    for gi, gname in [(None, 'all')] + list(enumerate(GROUPS)):
        mk = np.ones(len(va), bool) if gi is None else (vg == gi)
        Z = np.bincount(vt[mk], dv[mk] * cv[mk] * Lv[mk], nt)
        D = np.bincount(vt[mk], cv[mk] * np.abs(Lv[mk]), nt)
        R = np.bincount(vt[mk], dv[mk] * cv[mk], nt)
        C = np.bincount(vt[mk], cv[mk], nt)
        cnt = np.bincount(vt[mk], None, nt)
        res[gname] = {'S': np.where(cnt > 0, 100 * Z / (D + LAMBDA), np.nan), 'raw': np.where(C > 0, 100 * R / np.where(C > 0, C, 1), np.nan), 'Z': Z, 'n': cnt}
    return res


def fill_usd(E, P):
    """13F dollars from daily closes: |share change| × the close at the quarter end. The price the filing implies stays
    as the fallback (a few filers still report values in thousands)."""
    idx = np.flatnonzero((E.g == 0) & ~np.isnan(E.sh))
    if not len(idx):
        return 0
    idx = idx[np.argsort(E.t[idx], kind='stable')]
    ts = E.t[idx]
    starts = np.r_[0, np.flatnonzero(np.diff(ts)) + 1]
    ends = np.r_[starts[1:], len(idx)]
    n = 0
    for s0, e0 in zip(starts, ends):
        ser = P.get(E.tickers[ts[s0]])
        if ser is None:
            continue
        days, cl = ser
        ii = idx[s0:e0]
        i0 = np.searchsorted(days, E.day[ii], 'right') - 1
        ok = (i0 >= 0) & (E.day[ii] - days[np.maximum(i0, 0)] <= 7)
        E.usd[ii[ok]] = E.sh[ii[ok]] * cl[np.maximum(i0, 0)[ok]]
        n += int(ok.sum())
    return n


def net_by_actor(E, idx, Lside=None, by_dollars=True):
    """The trades idx netted per actor and stock: (actor, ticker, side, conviction, skill weight on that side, last day,
    group, net dollars, gross dollars, trades). The side is the sign of the net dollars where dollars are known (a buyer
    of $300k who sold $600k is a net seller), else of the conviction-weighted net."""
    nt = len(E.tickers)
    key = E.a[idx].astype(np.int64) * nt + E.t[idx]
    uniq, inv = np.unique(key, return_inverse=True)
    m = len(uniq)
    net = np.bincount(inv, E.d[idx] * E.c[idx], m)
    usd = np.nan_to_num(E.usd[idx])
    unet = np.bincount(inv, E.d[idx] * usd, m)
    ugross = np.bincount(inv, usd, m)
    cnt = np.bincount(inv, None, m)
    last = np.zeros(m, dtype=np.int64)
    np.maximum.at(last, inv, E.day[idx])
    va, vt = (uniq // nt).astype(np.int64), (uniq % nt).astype(np.int64)
    dv = np.where(ugross > 0, np.sign(unet), np.sign(net)) if by_dollars else np.sign(net)
    dv = np.where(dv == 0, np.sign(net), dv)
    nz = dv != 0
    va, vt, dv, net, last, unet, ugross, cnt = va[nz], vt[nz], dv[nz], net[nz], last[nz], unet[nz], ugross[nz], cnt[nz]
    cv = np.minimum(np.abs(net), 3.0)
    Lv = Lside[va, (dv < 0).astype(int)] if Lside is not None else np.zeros(len(va))
    return va, vt, dv, cv, Lv, last, E.ag.astype(np.int64)[va], unet, ugross, cnt


def qname(d):
    return f'Q{(d.month - 1) // 3 + 1} {d.year}'


def combined_periods(today):
    """The windows of the All flows page: the quarter whose 13F / N-PORT reports are arriving now ("this quarter's
    filings"), the one before, both, and the calendar quarter so far (insiders and officials only — fund reports for it
    come after it ends)."""
    t = dt.date.fromordinal(today)
    qs = dt.date(t.year, 3 * ((t.month - 1) // 3) + 1, 1)
    p_end = qs - dt.timedelta(days=1)
    p_start = dt.date(p_end.year, 3 * ((p_end.month - 1) // 3) + 1, 1)
    pp_end = p_start - dt.timedelta(days=1)
    pp_start = dt.date(pp_end.year, 3 * ((pp_end.month - 1) // 3) + 1, 1)
    md = lambda d: f'{d:%b} {d.day}'
    return [
        {'key': 'prev', 'label': f'{qname(p_start)} — this quarter\'s filings ({p_start:%b}–{p_end:%b})', 'start': p_start.isoformat(), 'end': p_end.isoformat(),
         'note': f'13F reports for {qname(p_start)} are due by {(p_end + dt.timedelta(days=45)):%b} {(p_end + dt.timedelta(days=45)).day}; until then only the early filers are in.'},
        {'key': 'prev2', 'label': f'{qname(pp_start)} ({pp_start:%b}–{pp_end:%b})', 'start': pp_start.isoformat(), 'end': pp_end.isoformat(), 'note': ''},
        {'key': 'both', 'label': f'{qname(pp_start)} + {qname(p_start)} ({pp_start:%b}–{p_end:%b})', 'start': pp_start.isoformat(), 'end': p_end.isoformat(),
         'note': 'Each actor\'s trades over both quarters, netted.'},
        {'key': 'qtd', 'label': f'{qname(qs)} to date ({md(qs)} – {md(t)})', 'start': qs.isoformat(), 'end': t.isoformat(),
         'note': f'Insiders (the Form 4s read so far; SEC\'s full quarterly set comes after the quarter) and officials only: 13F and N-PORT reports for {qname(qs)} come after it ends.'},
        {'key': 'd90', 'label': f'Last 90 days ({md(t - dt.timedelta(days=90))} – {md(t)})', 'start': (t - dt.timedelta(days=90)).isoformat(), 'end': t.isoformat(),
         'note': '13F managers and ETFs count with the quarter ends inside these 90 days.'},
        {'key': 'ytd', 'label': f'{pp_end.year} full quarters to date (Jan – {pp_end:%b})', 'start': dt.date(pp_end.year, 1, 1).isoformat(),
         'end': pp_end.isoformat(), 'note': 'Every quarter of the year whose 13F reports are all in.'},
        {'key': 'ytdn', 'label': f'{pp_end.year} to date, including {qname(p_start)}\'s filings so far (Jan 1 – {md(t)})',
         'start': dt.date(pp_end.year, 1, 1).isoformat(), 'end': t.isoformat(),
         'note': f'The year so far: {qname(p_start)} 13F reports are still arriving (early filers only), {qname(qs)} counts insiders and officials.'},
    ]


CF = ['ticker', 'name', 'S', 'raw'] + [f'{g}_{k}' for g in CGROUPS for k in ('b', 's', 'usd')] + ['actors', 'groups_buy', 'groups_sell', 'S_now']


def plan_window(E, lo, hi):
    """Insiders' 10b5-1 plan trades inside a window: per ticker {owner: net dollars} (each owner netted once)."""
    by = {}
    for tk, day, d, usd, okey, oname in getattr(E, 'plan', []):
        if lo <= day <= hi:
            o = by.setdefault(tk, {}).setdefault(okey, [oname, 0.0, 0.0, 0])
            o[1] += d * usd
            o[2] += usd
            o[3] += 1
    return by


def publish_combined(pub, E, sk, V, universe, today):
    """public/combined/: for each window, every stock with each group's buyers, sellers and net dollars side by side, how
    many groups were net buyers and net sellers, the smart score inside the window, and each group's most active names."""
    out_dir = pub / 'combined'
    if out_dir.exists():
        for p in out_dir.glob('*.json'):
            p.unlink()
    Lside = sk['L_side']
    nt = len(E.tickers)
    S_now = V['all']['S'] if V else np.full(nt, np.nan)
    index = {'generated_at': now(), 'fields': CF, 'groups': CGROUPS, 'labels': LABEL, 'periods': []}
    for per in combined_periods(today):
        lo, hi = ordinal(per['start']), ordinal(per['end'])
        idx = np.flatnonzero((E.day >= lo) & (E.day <= hi) & (E.known <= today))
        stats = {g: {'actors': 0, 'trades': 0, 'usd_buy': 0.0, 'usd_sell': 0.0} for g in CGROUPS}
        plan = plan_window(E, lo, min(hi, today))
        pnet = [o[1] for owners in plan.values() for o in owners.values()]
        stats['plan'] = {'actors': len({k for owners in plan.values() for k in owners}), 'trades': sum(o[3] for owners in plan.values() for o in owners.values()),
                         'usd_buy': round(sum(v for v in pnet if v > 0)), 'usd_sell': round(-sum(v for v in pnet if v < 0)), 'stocks': len(plan)}
        if not len(idx) and not plan:
            index['periods'].append({**per, 'stocks': 0, 'groups': stats})
            wj(out_dir / f"{per['key']}.json", {'key': per['key'], 'fields': CF, 'rows': [], 'actors': {}})
            continue
        if len(idx):
            va, vt, dv, cv, Lv, last, vg, unet, ugross, cnt = net_by_actor(E, idx, Lside)
        else:                                              # plan trades only in this window
            z = np.zeros(0, dtype=np.int64)
            va, vt, vg, last = z, z, z, z
            dv, cv, Lv, unet, ugross, cnt = (np.zeros(0) for _ in range(6))
        per_t = {}
        Z = np.bincount(vt, dv * cv * Lv, nt)
        D = np.bincount(vt, cv * np.abs(Lv), nt)
        R = np.bincount(vt, dv * cv, nt)
        C = np.bincount(vt, cv, nt)
        tot = np.bincount(vt, None, nt)
        cols = {}
        for gi, g in enumerate(GROUPS):
            mk = vg == gi
            cols[g] = (np.bincount(vt[mk], (dv[mk] > 0).astype(float), nt), np.bincount(vt[mk], (dv[mk] < 0).astype(float), nt),
                       np.bincount(vt[mk], unet[mk], nt))
            stats[g] = {'actors': int(len(np.unique(va[mk]))), 'trades': int(cnt[mk].sum()), 'usd_buy': round(float(unet[mk][unet[mk] > 0].sum())),
                        'usd_sell': round(float(-unet[mk][unet[mk] < 0].sum())), 'stocks': int(len(np.unique(vt[mk])))}
        lastd = np.zeros(nt, dtype=np.int64)
        np.maximum.at(lastd, vt, last)
        rows = []

        def plan_cols(t):
            owners = plan.get(t) or {}
            return [sum(1 for o in owners.values() if o[1] > 0), sum(1 for o in owners.values() if o[1] < 0), round(sum(o[1] for o in owners.values()))]
        for ti in np.flatnonzero(tot > 0):
            t = E.tickers[ti]
            row = [t, universe.name(t)[:48], r4(100 * Z[ti] / (D[ti] + LAMBDA), 1), r4(100 * R[ti] / C[ti], 1) if C[ti] else None]
            gb = gs = 0
            for g in GROUPS:
                b, s_, u = cols[g][0][ti], cols[g][1][ti], cols[g][2][ti]
                row += [int(b), int(s_), round(float(u))]
                if b or s_:
                    direction = np.sign(b - s_) or np.sign(u)
                    gb += direction > 0
                    gs += direction < 0
            row += plan_cols(t)                            # plan trades: dollars only, not a group's vote
            row += [int(tot[ti]), int(gb), int(gs), r4(S_now[ti], 1)]
            rows.append(row)
        have = {r[0] for r in rows}
        for t in plan:                                     # stocks with plan trades and nothing else in the window
            if t not in have:
                ti = E.tidx.get(t)
                rows.append([t, universe.name(t)[:48], None, None] + [0, 0, 0] * len(GROUPS) + plan_cols(t)
                            + [0, 0, 0, r4(S_now[ti], 1) if ti is not None else None])
        rows.sort(key=lambda r: -abs(sum(r[6 + 3 * k] for k in range(len(CGROUPS)))))
        # the most active names of each group: gross dollars traded in the window
        actors = {}
        for gi, g in enumerate(GROUPS):
            mk = np.flatnonzero(vg == gi)
            if not len(mk):
                continue
            ua, inv = np.unique(va[mk], return_inverse=True)
            gross = np.bincount(inv, ugross[mk], len(ua))
            netu = np.bincount(inv, unet[mk], len(ua))
            ntr = np.bincount(inv, cnt[mk], len(ua))
            nst = np.bincount(inv, None, len(ua))
            order = np.argsort(-gross)[:30]
            lst = []
            for j in order:
                ai = int(ua[j])
                mine = mk[inv == j]
                tops = sorted(mine, key=lambda k: -abs(unet[k]))[:4]
                lst.append([E.actors[ai]['id'], E.actors[ai]['name'], E.actors[ai]['sub'], round(float(gross[j])), round(float(netu[j])), int(ntr[j]), int(nst[j]),
                            r4(sk['all']['p'][ai]), r4(sk['all']['L'][ai], 2), int(sk['all']['decisions'][ai]),
                            [[E.tickers[vt[k]], int(dv[k]), round(float(unet[k]))] for k in tops]])
            actors[g] = lst
        if plan:                                           # the largest plan traders: gross dollars in the window
            flat = sorted(((okey, o, t) for t, owners in plan.items() for okey, o in owners.items()), key=lambda x: -x[1][2])
            by_owner = {}
            for okey, o, t in flat:
                a = by_owner.setdefault(okey, {'name': o[0], 'gross': 0.0, 'net': 0.0, 'trades': 0, 'top': []})
                a['gross'] += o[2]; a['net'] += o[1]; a['trades'] += o[3]
                if len(a['top']) < 4:
                    a['top'].append([t, 1 if o[1] > 0 else -1, round(o[1])])
            actors['plan'] = [['p:' + k, a['name'], 'insider · 10b5-1 plan', round(a['gross']), round(a['net']), a['trades'], len(a['top']),
                               None, None, 0, a['top']] for k, a in sorted(by_owner.items(), key=lambda x: -x[1]['gross'])[:30]]
        wj(out_dir / f"{per['key']}.json", {'key': per['key'], 'fields': CF, 'rows': rows,
                                             'actor_fields': ['id', 'name', 'sub', 'gross', 'net', 'trades', 'stocks', 'p', 'L', 'decisions', 'top'], 'actors': actors})
        index['periods'].append({**per, 'stocks': len(rows), 'groups': stats})
    wj(out_dir / 'index.json', index)
    return len(index['periods'])


# ------------------------------------------------------------------ backtest
BUCKETS = [(-101, -50, '−100 to −50'), (-50, -20, '−50 to −20'), (-20, 20, '−20 to +20'), (20, 50, '+20 to +50'), (50, 101, '+50 to +100')]


def month_ends(first, last):
    out = []
    y, m = first.year, first.month
    while True:
        e = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        if e > last:
            break
        if e >= first:
            out.append(e.toordinal())
        y, m = y + (m == 12), m % 12 + 1
    return out


def forward(P, tickers, dates, spy):
    """fwd[ticker, date]: the stock's excess return over SPY from the close on or before each date over H trading days."""
    sd, sc = spy
    D = np.array(dates, dtype=np.int64)
    j0 = np.searchsorted(sd, D, 'right') - 1
    out = np.full((len(tickers), len(D)), np.nan)
    for i, t in enumerate(tickers):
        s = P.get(t)
        if s is None:
            continue
        days, cl = s
        i0 = np.searchsorted(days, D, 'right') - 1
        i1 = i0 + H
        ok = (i0 >= 0) & (i1 < len(days)) & (j0 >= 0)
        ok &= D - days[np.maximum(i0, 0)] <= 7
        if not ok.any():
            continue
        e1 = days[np.minimum(i1, len(days) - 1)]
        k1 = np.searchsorted(sd, e1, 'right') - 1
        r = cl[np.minimum(i1, len(days) - 1)] / cl[np.maximum(i0, 0)] - 1
        rs = sc[np.maximum(k1, 0)] / sc[np.maximum(j0, 0)] - 1
        out[i, ok] = (r - rs)[ok]
    return out


def metrics(scores, fwd, dates_idx, rel=None, threshold=10):
    """Of (score, forward excess over SPY) pairs: the hit rate and |score|-weighted hit rate against the typical stock
    (rel: excess less that month's median — most stocks lag SPY, so a sign test against SPY alone would favour sales),
    the excess over SPY by score bucket, the rank correlation (IC) and the long-short spread per month."""
    rel = fwd if rel is None else rel
    ok = ~np.isnan(scores) & ~np.isnan(fwd) & (np.abs(scores) >= threshold)
    s, f, di, fr = scores[ok], np.clip(fwd[ok], -1, 1), dates_idx[ok], rel[ok]   # a few +1,000% stocks would swamp the averages
    if len(s) < 20:
        return {'n': int(len(s))}
    hit = (np.sign(s) == np.sign(fr))
    out = {'n': int(len(s)), 'hit': round(float(hit.mean()), 4), 'whit': round(float((np.abs(s) * hit).sum() / np.abs(s).sum()), 4)}
    b = []
    for lo, hi, lab in BUCKETS:
        m = (s >= lo) & (s < hi)
        if m.sum():
            b.append([lab, int(m.sum()), round(float(np.mean(f[m])), 5), round(float(np.mean(f[m] > 0)), 4), round(float(np.mean(fr[m] > 0)), 4)])
        else:
            b.append([lab, 0, None, None, None])
    out['buckets'] = b
    ics, spreads = [], []
    for u in np.unique(di):
        m = di == u
        if m.sum() >= 20:
            ics.append(spearman(s[m], f[m]))
        hi_, lo_ = f[m & (s >= 20)], f[m & (s <= -20)]
        if len(hi_) >= 5 and len(lo_) >= 5:
            spreads.append(hi_.mean() - lo_.mean())
    ics = [x for x in ics if x is not None and math.isfinite(x)]
    if ics:
        out['ic'] = round(float(np.mean(ics)), 4)
        out['ic_t'] = round(float(np.mean(ics) / (np.std(ics) / math.sqrt(len(ics)))), 2) if len(ics) > 2 and np.std(ics) > 0 else None
        out['ic_dates'] = len(ics)
    if spreads:
        out['spread'] = round(float(np.mean(spreads)), 5)
        out['spread_dates'] = len(spreads)
    return out


def spearman(x, y):
    if len(x) < 3:
        return None
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def backtest(E, O, P, spy, today):
    """Walk-forward month-end scores and what followed. Returns (summary, per-ticker history, calibration)."""
    sd = spy[0]
    if not E.n:
        return {}, {}, {}, 0.5
    last_ok = sd[-1 - H] if len(sd) > H + 1 else sd[0]
    first_known = int(np.min(E.known)) if E.n else today
    start = dt.date.fromordinal(max(first_known + 120, ordinal('2023-06-30')))
    dates = month_ends(start, dt.date.fromordinal(int(last_ok)))
    hist_dates = month_ends(start, dt.date.fromordinal(today))
    if not hist_dates:
        return {}, {}, {}, 0.5
    fwd = forward(P, E.tickers, dates, spy) if dates else np.zeros((len(E.tickers), 0))
    keys = ['all'] + GROUPS
    coll = {k: {'smart': [], 'raw': [], 'fwd': [], 'rel': [], 'di': []} for k in keys}
    hist = defaultdict(list)
    for j, T in enumerate(hist_dates):
        sk = skills(E, O, (O['end'] <= T) & (E.known <= T), u=ref_rate(fwd, dates, T))
        V = votes(E, T, sk['L_side'])
        if V is None:
            continue
        S, R, N = V['all']['S'], V['all']['raw'], V['all']['n']
        for ti in np.flatnonzero(N > 0):
            hist[ti].append([iso(T), round(float(S[ti]), 1), round(float(R[ti]), 1), int(N[ti])])
        if j >= len(dates):
            continue
        f = fwd[:, j]
        if np.isnan(f).all():
            continue
        fr = f - np.nanmedian(f)
        for k in keys:
            s_, r_ = V[k]['S'], V[k]['raw']
            m = ~np.isnan(s_) & ~np.isnan(f)
            coll[k]['smart'].append(s_[m]); coll[k]['raw'].append(r_[m]); coll[k]['fwd'].append(f[m]); coll[k]['rel'].append(fr[m]); coll[k]['di'].append(np.full(m.sum(), j))
    u = ref_rate(fwd, dates)
    summary = {'dates': [iso(d) for d in dates], 'horizon': H, 'reference': round(u, 4)}
    calib = {}
    for k in keys:
        if not coll[k]['fwd']:
            continue
        s_ = np.concatenate(coll[k]['smart']); r_ = np.concatenate(coll[k]['raw']); f_ = np.concatenate(coll[k]['fwd'])
        fr_ = np.concatenate(coll[k]['rel']); d_ = np.concatenate(coll[k]['di'])
        summary[k] = {'smart': metrics(s_, f_, d_, fr_), 'raw': metrics(r_, f_, d_, fr_)}
        calib[k] = summary[k]['smart'].get('buckets')
    return summary, hist, calib, u


# ------------------------------------------------------------------ publish
def r4(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def build(root, hub, etf_root=None, minutes=None, offline=False, today=None):
    root, hub = Path(root), Path(hub)
    t0 = time.time()
    st = {'started': now(), 'errors': []}
    universe = MK.Universe(hub)
    log('13F managers …')
    st['f13'] = update_f13(root, hub, universe, minutes=(minutes or 60) * 0.5 if minutes else None)
    log(f"  {st['f13']}")
    E = build_events(root, hub, etf_root, universe, st)
    P = Prices(root, hub).load(E.tickers + ['SPY'])
    if not offline:
        recent = dt.date.today().toordinal() - 3 * 365
        want = sorted({E.tickers[t] for t in np.unique(E.t[E.day >= recent])}) if E.n else []
        budget = max(2.0, (minutes or 20) - (time.time() - t0) / 60 - 8) if minutes else 10.0
        st['prices'] = P.top_up(want, minutes=min(budget, 25.0))
        log(f"prices: {st['prices']}")
    st['usd_from_closes'] = fill_usd(E, P)
    st['insider_prices_fixed'] = fix_insider_usd(E, P)
    spy = P.get('SPY')
    if spy is None:
        raise RuntimeError('no SPY prices: the benchmark is missing')
    today = today or dt.date.today().toordinal()
    O = outcomes(E, P, spy, today)
    log(f'outcomes: {int((~np.isnan(O["ex"])).sum())} scored of {E.n} ({time.time() - t0:.0f}s)')
    summary, hist, calib, u = backtest(E, O, P, spy, today)
    log(f'backtest: {len(summary.get("dates", []))} month ends, reference {u:.3f} ({time.time() - t0:.0f}s)')
    sk = skills(E, O, O['end'] <= today, u=u)
    V = votes(E, today, sk['L_side'])
    publish(root, hub, E, O, sk, V, summary, hist, calib, universe, st, today)
    st['combined_periods'] = publish_combined(root / 'public', E, sk, V, universe, today)
    st['seconds'] = round(time.time() - t0)
    st['finished'] = now()
    wj(root / 'public' / 'status.json', st)
    write_json(root / 'state.json', st)
    log(f'done in {st["seconds"]}s')
    return st


def bucket_of(calib, s):
    if s is None or not calib:
        return None
    for (lo, hi, lab), row in zip(BUCKETS, calib):
        if lo <= s < hi:
            return row
    return None


def publish(root, hub, E, O, sk, V, summary, hist, calib, universe, st, today):
    pub = root / 'public'
    for sub in ('t', 'a'):                                 # rebuilt in full: stocks and actors that dropped out leave no stale file
        d = pub / sub
        if d.exists():
            for p in d.rglob('*.json'):
                p.unlink()
    na = len(E.actors)
    side, alls = sk['side'], sk['all']
    sp = {k: v.reshape(na, 2) if v.ndim == 1 and len(v) == na * 2 else v for k, v in side.items() if k != 'p0'}
    exm = O['ex']
    # per-actor last trade and follow alpha
    last = np.zeros(na, dtype=np.int64)
    if E.n:
        np.maximum.at(last, E.a, E.day)
    fol_sum = np.bincount(E.a, np.where(np.isnan(O['fol']), 0, E.d * np.clip(np.nan_to_num(O['fol']), -1, 1)), na)
    fol_n = np.bincount(E.a, (~np.isnan(O['fol'])).astype(float), na)
    total_n = np.bincount(E.a, None, na)

    def stats(i):
        return {'n': int(total_n[i]), 'scored': int(alls['n'][i]), 'decisions': int(alls['decisions'][i]), 'hit': r4(alls['nr'][i] / alls['n'][i]) if alls['n'][i] else None,
                'acc': r4(alls['acc'][i]), 'p': r4(alls['p'][i]), 'L': r4(alls['L'][i], 3), 'neff': r4(alls['neff'][i], 1),
                'alpha': r4(alls['alpha'][i], 5), 'follow': r4(fol_sum[i] / fol_n[i], 5) if fol_n[i] else None,
                'buy': {'n': int(sp['n'][i, 0]), 'hit': r4(sp['nr'][i, 0] / sp['n'][i, 0]) if sp['n'][i, 0] else None, 'acc': r4(sp['acc'][i, 0]), 'p': r4(sp['p'][i, 0]), 'L': r4(sp['L'][i, 0], 3), 'alpha': r4(sp['alpha'][i, 0], 5)},
                'sell': {'n': int(sp['n'][i, 1]), 'hit': r4(sp['nr'][i, 1] / sp['n'][i, 1]) if sp['n'][i, 1] else None, 'acc': r4(sp['acc'][i, 1]), 'p': r4(sp['p'][i, 1]), 'L': r4(sp['L'][i, 1], 3), 'alpha': r4(sp['alpha'][i, 1], 5)},
                'last': iso(last[i]) if last[i] else None}
    # leaderboards
    LF = ['id', 'name', 'sub', 'n', 'scored', 'hit', 'acc', 'p', 'L', 'buy_n', 'buy_p', 'sell_n', 'sell_p', 'alpha', 'follow', 'last', 'decisions']
    leaders, worst, counts = {}, {}, {}
    ag = E.ag.astype(np.int64)
    for gi, g in enumerate(GROUPS):
        ids = np.flatnonzero((ag == gi) & (alls['decisions'] >= 5))     # a record: five separate decisions scored
        rows = []
        for i in ids:
            s = stats(i)
            rows.append([E.actors[i]['id'], E.actors[i]['name'], E.actors[i]['sub'], s['n'], s['scored'], s['hit'], s['acc'], s['p'], s['L'],
                         s['buy']['n'], s['buy']['p'], s['sell']['n'], s['sell']['p'], s['alpha'], s['follow'], s['last'], s['decisions']])
        rows.sort(key=lambda r: -(r[8] or 0))                   # by skill weight: edge over a random pick, by evidence
        leaders[g] = rows[:250]
        worst[g] = sorted(rows, key=lambda r: (r[8] or 0))[:40]
        gm = E.g == gi
        counts[g] = {'actors': int((ag == gi).sum()), 'trades': int(gm.sum()), 'scored': int((gm & ~np.isnan(exm)).sum()),
                     'priced': int((gm & O['priced']).sum()), 'pending': int((gm & O['pending']).sum()),
                     'base_buy': r4(side['p0'][gi * 2]), 'base_sell': r4(side['p0'][gi * 2 + 1]), 'ranked': int(len(ids)),
                     'ref_buy': r4(sk['u']), 'ref_sell': r4(1 - sk['u'])}
    # stocks now
    stocks, by_ticker_votes = [], defaultdict(list)
    if V:
        va, vt, dv, cv, Lv, vlast, vg = V['rows']
        for k in range(len(va)):
            by_ticker_votes[int(vt[k])].append(k)
        for ti in np.flatnonzero(V['all']['n'] > 0):
            t = E.tickers[ti]
            ks = by_ticker_votes[ti]
            buyers = sum(1 for k in ks if dv[k] > 0 and Lv[k] > 0.05)
            sellers = sum(1 for k in ks if dv[k] < 0 and Lv[k] > 0.05)
            row = [t, universe.name(t)[:50], r4(V['all']['S'][ti], 1), r4(V['all']['raw'][ti], 1)] + \
                  [r4(V[g]['S'][ti], 1) for g in GROUPS] + [int(V['all']['n'][ti]), buyers, sellers, r4(V['all']['Z'][ti], 3), iso(max(vlast[k] for k in ks))]
            stocks.append(row)
        stocks.sort(key=lambda r: -(r[2] or 0))
    SF = ['ticker', 'name', 'S', 'raw'] + ['S_' + g for g in GROUPS] + ['votes', 'skilled_buyers', 'skilled_sellers', 'Z', 'last']
    idx = {'generated_at': now(), 'horizon_days': H, 'k_prior': K_PRIOR, 'lambda': LAMBDA, 'window_days': WINDOW, 'quarter_window_days': QWINDOW,
           'groups': GROUPS, 'labels': LABEL, 'counts': counts, 'backtest': summary, 'calibration': calib,
           'leader_fields': LF, 'leaders': leaders, 'worst': worst, 'stock_fields': SF, 'stocks': stocks,
           'note': ('Each disclosed trade is scored by the stock\'s return less SPY\'s over the next 63 trading days from the decision date; '
                    'buys are right when the stock beat SPY, sales when it lagged. Accuracy weighs each trade by its conviction and the size of '
                    'the move, and is shrunk toward the group\'s base rate until an actor has a record. Disclosures arrive late (13F up to 45 days '
                    'after the quarter, officials up to 45 days after the trade), and past accuracy does not promise future accuracy. '
                    'Not investment advice.')}
    wj(pub / 'index.json', idx)
    # per stock
    recent = today - 400
    tk_events = defaultdict(list)
    for i in np.flatnonzero(E.day >= recent):
        tk_events[int(E.t[i])].append(int(i))
    wrote_t = 0
    for ti in set(tk_events) | set(by_ticker_votes) | set(hist):
        t = E.tickers[ti]
        vs = []
        if V:
            va, vt, dv, cv, Lv, vlast, vg = V['rows']
            for k in by_ticker_votes.get(ti, []):
                i = int(va[k])
                side_i = 0 if dv[k] > 0 else 1
                vs.append([E.actors[i]['id'], E.actors[i]['name'], E.actors[i]['g'], E.actors[i]['sub'], int(dv[k]), r4(cv[k], 2), r4(Lv[k], 3),
                           r4(sp['p'][i, side_i]), int(sp['n'][i, side_i]), iso(vlast[k])])
            vs.sort(key=lambda v: -abs((v[4] or 0) * (v[5] or 0) * (v[6] or 0)))
        evs = sorted(tk_events.get(ti, []), key=lambda i: -E.day[i])[:100]
        now_row = None
        if V and V['all']['n'][ti] > 0:
            S = r4(V['all']['S'][ti], 1)
            now_row = {'S': S, 'raw': r4(V['all']['raw'][ti], 1), 'Z': r4(V['all']['Z'][ti], 3), 'n': int(V['all']['n'][ti]),
                       'buyers': sum(1 for v in vs if v[4] > 0), 'sellers': sum(1 for v in vs if v[4] < 0),
                       'groups': {g: {'S': r4(V[g]['S'][ti], 1), 'raw': r4(V[g]['raw'][ti], 1), 'n': int(V[g]['n'][ti])} for g in GROUPS if V[g]['n'][ti] > 0},
                       'history_bucket': bucket_of(calib.get('all'), S)}
        wj(pub / 't' / (re.sub(r'[^A-Za-z0-9-]', '_', t) + '.json'), {
            'ticker': t, 'name': universe.name(t), 'generated_at': idx['generated_at'], 'now': now_row, 'votes': vs[:100], 'more_votes': max(0, len(vs) - 100),
            'history': hist.get(ti, []),
            'trade_fields': ['date', 'actor', 'name', 'group', 'd', 'size', 'ex', 'ex2', 'follow', 'known'],
            'trades': [[iso(E.day[i]), E.actors[E.a[i]]['id'], E.actors[E.a[i]]['name'], E.actors[E.a[i]]['g'], int(E.d[i]), r4(E.size[i], 5),
                        r4(O['ex'][i]), r4(O['ex2'][i]), r4(O['fol'][i]), iso(E.known[i])] for i in evs]})
        wrote_t += 1
    # per actor, in buckets
    by_actor = defaultdict(list)
    for i in range(E.n):
        by_actor[int(E.a[i])].append(i)
    buckets = defaultdict(dict)
    for ai, evs in by_actor.items():
        x = E.actors[ai]
        evs.sort(key=lambda i: -E.day[i])
        cap = 80 if x['g'] in ('f13', 'etf') else 150           # funds trade often: their newest 80 (the stats cover all)
        rows = []
        for i in evs[:cap]:
            ex = O['ex'][i]
            rows.append([iso(E.day[i]), E.tickers[E.t[i]], int(E.d[i]), r4(E.size[i], 5), r4(E.c[i], 2), r4(ex), r4(O['ex2'][i]), r4(O['fol'][i]),
                         None if np.isnan(ex) else int(E.d[i] * ex > 0), iso(E.known[i]), E.ref[i]])
        buckets[(x['g'], bucket(x['id']))][x['id']] = {'name': x['name'], 'g': x['g'], 'sub': x['sub'], 'stats': stats(ai), 'more': max(0, len(evs) - cap),
                                                        'trades': rows}
    for (g, b), obj in buckets.items():
        wj(pub / 'a' / g / f'{b}.json', {'fields': ['date', 'ticker', 'd', 'size', 'conviction', 'ex', 'ex2', 'follow', 'right', 'known', 'ref'], 'actors': obj})
    directory = sorted(([x['id'], x['name'], x['sub'], int(total_n[i]), int(alls['n'][i]), r4(alls['L'][i], 2)] for i, x in enumerate(E.actors) if total_n[i]),
                       key=lambda r: (-r[4], -r[3]))
    wj(pub / 'actors.json', {'fields': ['id', 'name', 'sub', 'n', 'scored', 'L'], 'rows': directory})
    st['public'] = {'stocks': len(stocks), 'stock_files': wrote_t, 'actors': na, 'actor_files': len(buckets),
                    'counts': counts, 'backtest_all': (summary.get('all') or {}).get('smart', {}).get('whit')}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--root', required=True)
    r.add_argument('--hub', required=True)
    r.add_argument('--etf', default=None, help='a checkout of the etf-history branch (cache/nport_active, public/index.json)')
    r.add_argument('--minutes', type=float, default=30)
    r.add_argument('--offline', action='store_true')
    a = ap.parse_args()
    root = Path(a.root)
    if not a.offline:
        try:
            st = collect_insiders(root)
            log(f'insider sets: {st}')
        except Exception as exc:
            log(f'::warning::insider data sets: {exc}')
    build(root, a.hub, a.etf, minutes=a.minutes, offline=a.offline)


if __name__ == '__main__':
    main()
