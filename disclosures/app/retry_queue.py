"""Durable, bounded-rate retries. A failure is never marked as a completed filing."""
import datetime as dt
from pathlib import Path
from core import read_json, write_json, now


class RetryQueue:
    def __init__(self, directory):
        self.path = Path(directory) / 'retry.json'
        self.rows = read_json(self.path, {})

    def due(self, key):
        return (self.rows.get(key, {}).get('next_retry_at') or '') <= now()

    def failed(self, key, exc):
        row = self.rows.get(key, {})
        count = int(row.get('attempts', 0)) + 1
        message = str(exc)[:300]
        blocked = '403' in message or '429' in message
        minutes = min(1440, (60 if blocked else 15) * 2 ** min(count - 1, 7))
        self.rows[key] = {'attempts': count, 'last_attempt': now(), 'error': message,
                          'next_retry_at': (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).isoformat()}

    def succeeded(self, key):
        self.rows.pop(key, None)

    def save(self):
        write_json(self.path, self.rows)

    def summary(self):
        return {'failed_queue': len(self.rows),
                'next_retry_at': min((r['next_retry_at'] for r in self.rows.values()), default=None),
                'error_samples': [dict(key=k, **v) for k, v in list(self.rows.items())[:5]]}
