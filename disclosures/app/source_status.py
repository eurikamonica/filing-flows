"""Small independent source health files; attempts and successful observations are distinct."""
from pathlib import Path
from core import now, read_json, write_json


def _plausible(day):
    """A filing date that can be one: not after tomorrow (a report typed 3013-06-14 would head every later status)."""
    import datetime as dt
    return bool(day) and day <= (dt.date.today() + dt.timedelta(days=1)).isoformat()


def latest_filing(result):
    dates = []
    def visit(value):
        if isinstance(value, dict):
            for key, val in value.items():
                if key in ('filed', 'filed_date', 'filing_date', 'latest_filing', 'newest_ptr_filed', 'latest_filing_date') and isinstance(val, str):
                    if len(val) >= 10 and val[4:5] == '-' and _plausible(val[:10]): dates.append(val[:10])
                elif key in ('managers', 'reports', 'records', 'filings', 'directory', 'rows'):
                    visit(val)
        elif isinstance(value, list):
            for row in value: visit(row)
    visit(result)
    return max(dates, default=None)


def record(root, key, result, attempted=None):
    path = Path(root) / f'{key}-status.json'
    previous = read_json(path, {})
    status = result.get('status', 'unknown')
    errors = result.get('errors')
    if status == 'ok' and errors:
        status = 'partial'
    # a poll skipped says why (a string: 'searched recently', 'access cooldown') or status 'skipped'; a count of the items a
    # run left out (news: {'law firm': 6, 'not English': 12}) is no skipped poll — it kept the news source stale for days
    sk = result.get('skipped')
    skipped = status == 'skipped' or sk is True or (isinstance(sk, str) and bool(sk))
    completed = result.get('updated_at') or now()
    out = {k: v for k, v in result.items() if k in (
        'status', 'error', 'errors', 'error_samples', 'read', 'found', 'waiting', 'failed_queue',
        'next_retry_at', 'blocked', 'skipped', 'published', 'counts', 'on_file', 'trades', 'added',
        'newest', 'available', 'index_days', 'underlyings', 'fetched', 'reparse_left', 'cursor', 'paper', 'guidance_history')}
    out.update(status=status, last_attempt=attempted or now(),
               last_success=previous.get('last_success'),
               last_partial_success=previous.get('last_partial_success'),
               updated_at=previous.get('updated_at'),
               latest_filing_date=max(latest_filing(result) or '', previous.get('latest_filing_date') if _plausible(previous.get('latest_filing_date')) else '') or None)
    if not skipped and status == 'ok':
        out.update(last_success=completed, updated_at=completed)
    elif not skipped and status == 'partial':
        out.update(last_partial_success=completed, updated_at=completed)
    # A skipped poll cannot clear a previous access error or pretend to be a success.
    # (A cooldown that reports the source as blocked by its own access check says so instead.)
    if skipped and previous.get('status') in ('error', 'partial') and status != 'blocked':
        out['status'] = previous['status']
        out['error'] = result.get('error') or previous.get('error')
    write_json(path, out)
    return out
