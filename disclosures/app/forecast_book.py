"""Forecast book: a generic ledger for any family of forecasts — frozen once, resolved once, scored honestly.

Every forecast the site publishes (an earnings-beat probability, an EPS estimate, an options-implied move, a post-earnings
drift …) is written here the first time it is shown and never changed again; when the outcome is known it is resolved
once. Scores are computed only from what was frozen before the outcome, so the track record cannot be improved after the
fact. (The Rotation ledger in forecast_ledger.py is the same idea for the rotation charts.)

    book = load(path)
    freeze(book, 'beat', 'AAPL:2026-09-30', asof='2026-11-01', forecast={'p': 0.81}, meta={'model': 'v1'})
    resolve(book, 'beat', 'AAPL:2026-09-30', {'y': 1})
    score_prob([(e['forecast']['p'], e['actual']['y']) for e in entries(book, 'beat', resolved=True)])
    save(path, book)

Intervals: conformal_halfwidth(residuals, 0.8) is the split-conformal quantile of past absolute errors (walk-forward:
only residuals of forecasts resolved before the new one), so an "80% range" covers about 80% of outcomes by construction.
"""
import datetime as dt
import json
import math
from pathlib import Path

VERSION = 1


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def load(path):
    try:
        book = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        book = {}
    book.setdefault('version', VERSION)
    book.setdefault('families', {})
    return book


def save(path, book):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(book, separators=(',', ':'), allow_nan=False, default=_jsonable), encoding='utf-8')
    tmp.replace(path)


def _jsonable(v):
    if hasattr(v, 'item'):
        return v.item()
    raise TypeError(f'not JSON serialisable: {type(v)}')


def freeze(book, family, key, asof, forecast, interval=None, meta=None, at=None):
    """Write a forecast the first time it is published; later calls for the same key change nothing. True when new."""
    fam = book['families'].setdefault(family, {})
    if key in fam:
        return False
    fam[key] = {'asof': asof, 'frozen_at': at or now(), 'forecast': _finite(forecast), 'interval': _finite(interval),
                'meta': meta or {}, 'actual': None, 'resolved_at': None}
    return True


def resolve(book, family, key, actual, at=None):
    """Record the outcome of a frozen forecast once. True when it was resolved now."""
    e = book['families'].get(family, {}).get(key)
    if not e or e.get('actual') is not None:
        return False
    e['actual'] = _finite(actual)
    e['resolved_at'] = at or now()
    return True


def get(book, family, key):
    return book['families'].get(family, {}).get(key)


def entries(book, family, resolved=None):
    """[(key, entry)] of a family, oldest frozen first; resolved=True / False filters on the outcome."""
    out = []
    for k, e in book['families'].get(family, {}).items():
        if resolved is None or (e.get('actual') is not None) == resolved:
            out.append((k, e))
    return sorted(out, key=lambda kv: (kv[1].get('frozen_at') or '', kv[0]))


def prune(book, family, keep):
    """Keep the newest `keep` entries of a family (resolved ones are the history; nothing unresolved is dropped first)."""
    fam = book['families'].get(family, {})
    if len(fam) <= keep:
        return 0
    order = sorted(fam.items(), key=lambda kv: (kv[1].get('actual') is None, kv[1].get('frozen_at') or ''))
    drop = [k for k, _ in order[:len(fam) - keep]]
    for k in drop:
        fam.pop(k, None)
    return len(drop)


def _finite(v):
    if v is None:
        return None
    if isinstance(v, dict):
        return {k: _finite(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_finite(x) for x in v]
    if hasattr(v, 'item'):
        v = v.item()
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    return v


# ------------------------------------------------------------------ scores
def score_prob(pairs, bins=10):
    """Probability forecasts [(p, y)] with y in {0, 1}: Brier score, the Brier of always forecasting the base rate, hit
    rate (p ≥ 0.5 called "yes"), log loss and calibration bins [[low, high, mean forecast, observed frequency, n]]."""
    pairs = [(min(1.0, max(0.0, float(p))), 1 if y else 0) for p, y in pairs if p is not None and y is not None]
    n = len(pairs)
    if not n:
        return {'n': 0, 'brier': None, 'brier_base_rate': None, 'base_rate': None, 'hit_rate': None, 'log_loss': None, 'bins': []}
    base = sum(y for _, y in pairs) / n
    brier = sum((p - y) ** 2 for p, y in pairs) / n
    brier0 = sum((base - y) ** 2 for _, y in pairs) / n
    hit = sum(1 for p, y in pairs if (p >= 0.5) == bool(y)) / n
    eps = 1e-6
    ll = -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for p, y in pairs) / n
    out_bins = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        sel = [(p, y) for p, y in pairs if lo <= p < hi or (i == bins - 1 and p == 1.0)]
        if sel:
            out_bins.append([round(lo, 3), round(hi, 3), round(sum(p for p, _ in sel) / len(sel), 4),
                             round(sum(y for _, y in sel) / len(sel), 4), len(sel)])
    return {'n': n, 'brier': round(brier, 5), 'brier_base_rate': round(brier0, 5), 'base_rate': round(base, 4),
            'hit_rate': round(hit, 4), 'log_loss': round(ll, 5), 'bins': out_bins,
            'skill': round(1 - brier / brier0, 4) if brier0 > 0 else None}


def score_point(pairs):
    """Point forecasts [(forecast, actual)]: mean absolute error, RMSE, mean bias (forecast − actual) and the median
    absolute percentage error (only where the actual is not near zero)."""
    pairs = [(float(f), float(a)) for f, a in pairs if f is not None and a is not None]
    n = len(pairs)
    if not n:
        return {'n': 0, 'mae': None, 'rmse': None, 'bias': None, 'mdape': None}
    err = [f - a for f, a in pairs]
    ape = sorted(abs(f - a) / abs(a) for f, a in pairs if abs(a) > 1e-9)
    return {'n': n, 'mae': round(sum(abs(e) for e in err) / n, 6), 'rmse': round(math.sqrt(sum(e * e for e in err) / n), 6),
            'bias': round(sum(err) / n, 6), 'mdape': round(ape[len(ape) // 2], 5) if ape else None}


def head_to_head(rows):
    """[(forecast A, forecast B, actual)] → how often A was closer than B (ties split), and both MAEs."""
    rows = [(float(a), float(b), float(y)) for a, b, y in rows if a is not None and b is not None and y is not None]
    if not rows:
        return {'n': 0, 'a_closer': None, 'mae_a': None, 'mae_b': None}
    win = sum(1.0 if abs(a - y) < abs(b - y) else 0.5 if abs(a - y) == abs(b - y) else 0.0 for a, b, y in rows)
    return {'n': len(rows), 'a_closer': round(win / len(rows), 4), 'mae_a': round(sum(abs(a - y) for a, _, y in rows) / len(rows), 6),
            'mae_b': round(sum(abs(b - y) for _, b, y in rows) / len(rows), 6)}


def conformal_halfwidth(residuals, coverage=0.8):
    """Split-conformal half-width: the ceil((n+1)·coverage)-th smallest absolute residual (None with fewer than 10)."""
    r = sorted(abs(float(x)) for x in residuals if x is not None and math.isfinite(float(x)))
    n = len(r)
    if n < 10:
        return None
    k = min(n - 1, max(0, math.ceil((n + 1) * coverage) - 1))
    return r[k]


def coverage(rows):
    """[(low, high, actual)] → share of outcomes inside the range."""
    rows = [(lo, hi, y) for lo, hi, y in rows if lo is not None and hi is not None and y is not None]
    return round(sum(1 for lo, hi, y in rows if lo <= y <= hi) / len(rows), 4) if rows else None
