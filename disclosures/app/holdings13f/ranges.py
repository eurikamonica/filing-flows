"""How far back a 13F manager's history is read (config holdings).

    since         every manager, from its first reading: the recent quarters, every position
    watch_since   the watched funds (holdings.watch) and the listed managers: the 13F XML era began with 2013 Q2
    tiers         [[min reported value, max positions, since] …], first match wins, for the managers whose size an
                  earlier reading showed: the back-fill relay (app/backfill13f.py) reads them again from the deeper
                  date. The index giants (thousands of positions a quarter) stay at `since`: their old quarters would
                  be most of the storage and are the least looked at.

A manager's range never shrinks: a reading from a deeper date than the rule gives today is kept."""


def deep_ciks(cfg):
    """The CIKs read from watch_since."""
    if not cfg.get('watch_since'):
        return set()
    out = set()
    for key in ('watch', 'managers'):
        for m in cfg.get(key) or []:
            if str(m.get('cik') or '').strip().isdigit():
                out.add(str(int(m['cik'])))
    return out


def size_of(row):
    """(latest reported value in dollars, positions) of a manager row: a full row (snapshots with positions) or a lazy
    summary / catalog row (total_usd, position_count); (None, None) when unknown."""
    row = row or {}
    usd, n = row.get('total_usd'), row.get('position_count')
    snaps = row.get('snapshots') or []
    last = snaps[-1] if snaps and isinstance(snaps[-1], dict) else None
    if last:
        usd = last.get('total_usd', usd)
        n = len(last['positions']) if isinstance(last.get('positions'), list) else last.get('position_count', n)
    try:
        return (float(usd) if usd is not None else None), (int(n) if n is not None else None)
    except (TypeError, ValueError):
        return None, None


def target_since(cfg, cik, usd=None, positions=None, current=None):
    """The first filing date a manager's history is read from. usd / positions: its size from an earlier reading
    (unknown: the universe's `since`); current: the date of the reading on file, kept when it is deeper."""
    cik = str(int(cik))
    if cik in deep_ciks(cfg):
        s = cfg['watch_since']
    else:
        s = cfg['since']
        if usd is not None and positions is not None:
            for tier in cfg.get('tiers') or []:
                lo, hi, since = tier
                if usd >= float(lo) and positions <= int(hi) and since < s:
                    s = since
                    break
    if current and current < s:
        s = current
    return s
