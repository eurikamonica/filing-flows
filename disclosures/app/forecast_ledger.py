"""Forecast ledger for Rotation -> Next step: every published forecast frozen, then scored against what happened.

The site's forecast files are rebuilt every few hours, and their past origins are walk-forward backtests recomputed with
today's code. The ledger keeps what was actually published:

  freeze   the first time an origin (a quarter, a month or a week) appears as the LIVE forecast, its forecasts are written
           to ledger/<freq>.json on the rotation-history branch and never changed again (source "live", with the time and
           the code version that made them);
  seed     origins from before the ledger existed are filled once from the out-of-sample backtest rows, marked "backtest";
  resolve  when the target period has closed, each forecast gets the actual close and the gaps: forecast change vs actual
           change (points), whether the actual close fell inside the 80% range, whether the direction was right, and on
           the RRG the distance between the forecast next point and the actual one.

public/forecast-ledger.json is what the page reads: per origin a summary and per company the forecast and the outcome.

  python forecast_ledger.py --root hist [--sha <commit>]
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import chaos_forecast as CF

KEEP = {'q': 90, 'm': 240, 'w': 950}         # origins kept per frequency (everything since 2010)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _read(p, default):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def _write(p, obj, compact=True):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(CF.jsonable(obj), separators=(',', ':') if compact else None, indent=None if compact else 1),
                       encoding='utf-8')


# ------------------------------------------------------------------ freezing
def entries_from_chaos(doc):
    """{origin: {target, rows: {ticker: [close, price, lo80, hi80, rel_next, model]}}} from chaos-forecast*.json."""
    out = {}
    if not doc:
        return out
    jrel = doc['vars'].index('rel') if 'rel' in doc.get('vars', []) else None
    for t, rows in (doc.get('companies') or {}).items():
        for r in rows:
            o = doc['origins'][r[0]]
            if r[4] is None or r[5] is None:
                continue
            e = out.setdefault(o, {'target': doc['targets'][r[0]], 'rows': {}})
            e['rows'][t] = [r[4], r[5], r[6], r[7], r[1][jrel] if jrel is not None else None, r[8] if len(r) > 8 else 0]
    return out


def entries_from_rrg(doc):
    """{week: {target, rows: {line: [close, close_next, rel_logret, x, y, next_x, next_y, model]}}} from chaos-rrg.json."""
    out = {}
    if not doc:
        return out
    weeks = doc['weeks']
    for line, rows in (doc.get('lines') or {}).items():
        for r in rows:
            w = r[0]
            if w >= len(weeks):
                continue
            o = weeks[w]
            tgt = str(np.datetime64(o, 'D') + np.timedelta64(7, 'D'))
            e = out.setdefault(o, {'target': tgt, 'week': w, 'rows': {}})
            e['rows'][line] = [r[6], r[7], r[5], r[1], r[2], r[3], r[4], r[8] if len(r) > 8 else 0]
    return out


def freeze(ledger, entries, live_origin, sha, made_at):
    """Add the live origin once (never overwritten) and seed older origins once as backtest."""
    have = {e['origin']: e for e in ledger['origins']}
    added = []
    for o in sorted(entries):
        if o in have:
            e = have[o]
            if o == live_origin and e['source'] == 'live':      # companies that joined the live forecast later are added;
                new = {t: r for t, r in entries[o]['rows'].items() if t not in e['rows']}   # existing ones never change
                if new:
                    e['rows'].update(new); e['late'] = sorted(set(e.get('late', [])) | set(new))
            continue
        src = 'live' if o == live_origin else ('backtest' if not ledger.get('started') or o < ledger['started'] else None)
        if src is None:                       # an origin that appeared after the ledger began but was never live: skip
            continue
        e = entries[o]
        ledger['origins'].append({'origin': o, 'target': e['target'], 'source': src, 'made_at': made_at if src == 'live' else None,
                                  'code': sha if src == 'live' else None, 'rows': e['rows'], 'outcome': {}})
        added.append((o, src))
    if not ledger.get('started') and live_origin:
        ledger['started'] = live_origin
    ledger['origins'].sort(key=lambda e: e['origin'])
    return added


# ------------------------------------------------------------------ resolving
def _target_close(series, target_day, last_day):
    if series is None or np.datetime64(target_day) > np.datetime64(last_day):
        return np.nan
    v, _ = CF.close_at(series, target_day)
    return v


def resolve_calendar(ledger, closes, last_day):
    """Quarter / month: actual close at the target period's end (last Friday on or before it)."""
    for e in ledger['origins']:
        end = str(CF.cal_end(e['target']))
        if np.datetime64(end) > np.datetime64(last_day):
            continue                          # the target period has not closed yet
        for t, r in e['rows'].items():
            if t in e['outcome']:
                continue
            a = _target_close(closes.get(t), end, last_day)
            if np.isfinite(a):
                e['outcome'][t] = [round(float(a), 4)]
    return ledger


def resolve_rrg(ledger, public, last_day, n=14):
    """Week: actual close next week and the actual next RRG point (the chart's formula)."""
    D = json.loads((Path(public) / 'rrg.json').read_text(encoding='utf-8'))
    grid0 = np.datetime64(D['start'])
    W = int((np.datetime64(D['weeks']) - grid0).astype(int) // 7) + 1

    def full(ent):
        a = np.full(W, np.nan); o = int((np.datetime64(ent['start']) - grid0).astype(int) // 7)
        c = np.array([np.nan if v is None else v for v in ent['c']], float); a[o:o + len(c)] = c[:W - o]; return a
    bench = full(D['bench'])
    lines = {s['id']: s for s in D['series']}
    cache = {}

    def series(line):
        if line in cache:
            return cache[line]
        ent = lines.get(line)
        if ent is None:
            p = Path(public) / 't' / f'{line}.json'
            ent = _read(p, None)
        if not ent:
            cache[line] = None; return None
        c = full(ent)
        with np.errstate(all='ignore'):
            rs = np.where((bench > 0) & np.isfinite(c), 100 * c / bench, np.nan)
        S = CF.rrg_series(rs, n)
        cache[line] = (c, S)
        return cache[line]
    for e in ledger['origins']:
        k = int((np.datetime64(e['origin']) - grid0).astype(int) // 7) + 1
        if k >= W:
            continue
        for line, r in e['rows'].items():
            if line in e['outcome']:
                continue
            s = series(line)
            if s is None:
                continue
            c, S = s
            if np.isfinite(c[k]) and np.isfinite(S['x'][k]) and np.isfinite(S['y'][k]):
                with np.errstate(all='ignore'):
                    rel = float(np.log((c[k] / bench[k]) / (c[k - 1] / bench[k - 1])))
                e['outcome'][line] = [round(float(c[k]), 4), round(float(S['x'][k]), 3), round(float(S['y'][k]), 3), round(rel, 5)]
    return ledger


# ------------------------------------------------------------------ scoring
def _relative_hit(fc, ac):
    """Share of companies put on the right side of the median: a forecast above the origin's median forecast with an
    actual change above the median actual change, or both below. Unlike the direction hit it does not reward a model
    for calling 'up' in a rising market."""
    fc, ac = np.asarray(fc, float), np.asarray(ac, float)
    if len(fc) < 8:
        return None
    sf, sa = np.sign(fc - np.median(fc)), np.sign(ac - np.median(ac))
    ok = (sf != 0) & (sa != 0)
    return float(np.mean(sf[ok] == sa[ok])) if ok.any() else None


def score_calendar(e):
    """Per company: forecast change %, actual change %, gap (points), inside the 80% range, direction right."""
    rows, fc, ac = {}, [], []
    for t, r in e['rows'].items():
        close, price, lo, hi = r[0], r[1], r[2], r[3]
        o = e['outcome'].get(t)
        if not o or not close:
            continue
        a = o[0]; f_chg = 100 * (price / close - 1); a_chg = 100 * (a / close - 1)
        inside = (lo is not None and hi is not None and lo <= a <= hi)
        rows[t] = [round(f_chg, 2), round(a_chg, 2), round(a_chg - f_chg, 2), bool(inside), bool(np.sign(f_chg) == np.sign(a_chg))]
        fc.append(f_chg); ac.append(a_chg)
    s = {'n': len(e['rows']), 'resolved': len(rows)}
    if rows:
        s['relative_hit'] = _relative_hit(fc, ac)
        s.update(direction_hit=float(np.mean([x[4] for x in rows.values()])), share_up=float(np.mean(np.array(ac) > 0)),
                 inside80=float(np.mean([x[3] for x in rows.values()])), mean_abs_gap=float(np.mean([abs(x[2]) for x in rows.values()])),
                 median_abs_gap=float(np.median([abs(x[2]) for x in rows.values()])),
                 ic=CF.spearman(np.array(fc), np.array(ac)) if len(fc) >= 8 else None,
                 mean_forecast=float(np.mean(fc)), mean_actual=float(np.mean(ac)))
    return rows, s


def score_rrg(e):
    rows, fc, ac = {}, [], []
    for t, r in e['rows'].items():
        o = e['outcome'].get(t)
        if not o:
            continue
        close, close_next, rel_f, x, y, nx, ny = r[:7]
        a_close, ax, ay, rel_a = o
        gap_pts = math.hypot(ax - nx, ay - ny); step_a = (ax - x, ay - y); step_f = (nx - x, ny - y)
        cos = (step_a[0] * step_f[0] + step_a[1] * step_f[1]) / (math.hypot(*step_a) * math.hypot(*step_f) + 1e-12)
        rows[t] = [round(100 * rel_f, 3), round(100 * rel_a, 3), round(100 * (rel_a - rel_f), 3), round(gap_pts, 3), bool(cos > 0), bool(np.sign(rel_f) == np.sign(rel_a))]
        fc.append(rel_f); ac.append(rel_a)
    s = {'n': len(e['rows']), 'resolved': len(rows)}
    if rows:
        s['relative_hit'] = _relative_hit(fc, ac)
        s.update(step_hit=float(np.mean([x[4] for x in rows.values()])), direction_hit=float(np.mean([x[5] for x in rows.values()])),
                 mean_point_gap=float(np.mean([x[3] for x in rows.values()])), mean_abs_gap=float(np.mean([abs(x[2]) for x in rows.values()])),
                 ic=CF.spearman(np.array(fc), np.array(ac)) if len(fc) >= 8 else None)
    return rows, s


# ------------------------------------------------------------------ the run
def update(root, sha=None, verbose=True):
    root = Path(root); public = root / 'public'; led = root / 'ledger'
    made_at = _now()
    q = _read(public / 'chaos-forecast.json', None); m = _read(public / 'chaos-forecast-monthly.json', None); w = _read(public / 'chaos-rrg.json', None)
    rrg = _read(public / 'rrg.json', {})
    last_day = rrg.get('weeks') or str(dt.date.today())
    tick = sorted(set((q or {}).get('companies', {})) | set((m or {}).get('companies', {})))
    closes = CF.weekly_closes(public / 't', tick)
    out = {'generated_at': made_at, 'last_week': last_day, 'freqs': {}}
    for freq, doc, entries_fn in (('q', q, entries_from_chaos), ('m', m, entries_from_chaos), ('w', w, entries_from_rrg)):
        if not doc:
            continue
        ledger = _read(led / f'{freq}.json', {'freq': freq, 'origins': []})
        entries = entries_fn(doc)
        live = (doc['origins'][-1] if freq != 'w' else max(entries) if entries else None)
        added = freeze(ledger, entries, live, sha, made_at)
        if freq == 'w':
            resolve_rrg(ledger, public, last_day)
        else:
            resolve_calendar(ledger, closes, last_day)
        ledger['origins'] = ledger['origins'][-KEEP[freq]:]
        _write(led / f'{freq}.json', ledger)
        idx, det = [], {}
        for e in ledger['origins']:
            rows, s = (score_rrg if freq == 'w' else score_calendar)(e)
            idx.append({'origin': e['origin'], 'target': e['target'], 'source': e['source'], 'made_at': e.get('made_at'),
                        'code': (e.get('code') or '')[:12] or None, 'late': len(e.get('late', [])), 'summary': s})
            ng, na = (6, 3) if freq == 'w' else (5, 1)
            det[e['origin']] = {t: list(r) + (rows.get(t) or [None] * ng) + (e['outcome'].get(t) or [None] * na)[:na]
                                for t, r in e['rows'].items()}
        ff = (['close', 'close_next', 'rel_logret', 'x', 'y', 'next_x', 'next_y', 'model'] if freq == 'w'
              else ['close', 'price', 'lo80', 'hi80', 'rel_next', 'model'])
        gf = (['forecast_rel_pct', 'actual_rel_pct', 'gap_pts', 'point_gap', 'step_right', 'direction_right'] if freq == 'w'
              else ['forecast_change_pct', 'actual_change_pct', 'gap_pts', 'inside80', 'direction_right'])
        out['freqs'][freq] = {'started': ledger.get('started'), 'origins': idx, 'file': f'forecast-ledger-{freq}.json',
                              '_ids': {t for e in ledger['origins'] for t in e['rows']}}
        _write(public / f'forecast-ledger-{freq}.json', {'freq': freq, 'generated_at': made_at,
               'fields': ff + gf + (['actual_close', 'actual_x', 'actual_y'] if freq == 'w' else ['actual_close']), 'n_forecast': len(ff), 'n_gap': len(gf), 'rows': det})
        if verbose:
            print(f'ledger {freq}: {len(ledger["origins"])} origins, added {added[-3:] if added else "none"}; live {live}', flush=True)
    meta, ids = {}, set()
    for f in out['freqs'].values():
        ids |= set(f.pop('_ids', ()))
    for sr in rrg.get('series') or []:
        meta[sr['id']] = [sr['name'], sr.get('sector') or '', sr.get('group') or '']
    for t, mt in (rrg.get('tickers') or {}).items():
        if t in ids and t not in meta:
            meta[t] = [mt.get('n') or t, mt.get('s') or '', 'company']
    out['meta'] = {k: v for k, v in meta.items() if k in ids}
    out['sectors'] = {sr['sector']: sr['name'].split(' · ')[0] for sr in rrg.get('series') or [] if sr.get('group') == 'site-sector'}
    out['note'] = ('Every forecast the page published, kept as it was. "live" origins were frozen the first time they were the newest '
                   'forecast (with the time and code version); "backtest" origins predate the ledger and are the out-of-sample '
                   'walk-forward forecasts made with the data public at the time. Gaps: actual change minus forecast change, in '
                   'percentage points; inside80: the actual close fell inside the 80% range; on the RRG, the distance between the '
                   'forecast next point and the actual one.')
    _write(public / 'forecast-ledger.json', out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='hist')
    ap.add_argument('--sha', default=None)
    a = ap.parse_args()
    update(a.root, a.sha)


if __name__ == '__main__':
    main()
