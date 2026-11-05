"""Out-of-sample forecast histories, kept so that forecasts from different models can be combined and tested together
(app/opportunity_scan.py): each model writes one matrix of its walk-forward forecasts — every week predicted only from the
years before it, this week's included — for every name, as float16, beside its tickers and week-ending dates.

  save(path, tickers, dates, X, meta)   X: names × weeks (NaN where the model said nothing)
  load(path) → {'tickers': [...], 'dates': datetime64[D] array, 'X': float32 names × weeks, 'meta': {...}} or None

Kept under hist/cache/oos/ on the rotation-history branch (not published).
"""
import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import numpy as np


def save(path, tickers, dates, X, meta=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    X = np.asarray(X, dtype=np.float32)
    days = np.asarray(dates).astype('datetime64[D]').astype(np.int64)
    m = dict(meta or {})
    m.setdefault('saved_at', dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'))
    tmp = path.with_name(path.stem + '.tmp.npz')
    np.savez_compressed(tmp, tickers=np.array([str(t) for t in tickers]), days=days, X=np.clip(X, -6e4, 6e4).astype(np.float16),
                        meta=np.array(json.dumps(m)))
    tmp.replace(path)
    return path


def load(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        with np.load(io.BytesIO(path.read_bytes()), allow_pickle=False) as z:        # read whole: a torn file leaves no handle open
            return {'tickers': [str(t) for t in z['tickers']], 'dates': z['days'].astype('datetime64[D]'),
                    'X': z['X'].astype(np.float32), 'meta': json.loads(str(z['meta']))}
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):      # a torn or foreign file: as if none
        return None
