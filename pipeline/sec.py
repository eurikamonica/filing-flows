"""SEC EDGAR client: polite (User-Agent, <=8 req/s), retrying, with an offline fixture mode for tests."""
import json
import os
import re
import time
import hashlib

import requests

UA = os.environ.get("SEC_USER_AGENT", "").strip()
FIXTURES = os.environ.get("SEC_FIXTURES", "").strip()
MIN_INTERVAL = 1 / 8.0          # SEC fair-access limit is 10 requests/second
_last = [0.0]
_session = requests.Session()


class NotFound(Exception):
    pass


def _fixture_path(url):
    name = re.sub(r"^https?://", "", url)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if len(name) > 180:
        name = name[:120] + "_" + hashlib.sha1(url.encode()).hexdigest()[:16]
    return os.path.join(FIXTURES, name)


def get(url, binary=False):
    """GET a SEC URL and return text (or bytes). Raises NotFound on 404."""
    if FIXTURES:
        path = _fixture_path(url)
        if not os.path.exists(path):
            raise NotFound(url)
        with open(path, "rb") as f:
            data = f.read()
        return data if binary else data.decode("utf-8", "replace")
    if not UA or "@" not in UA:
        raise SystemExit("Set SEC_USER_AGENT to 'Your Name your@email.com' (required by SEC fair-access rules).")
    for attempt in range(5):
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = _session.get(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 404:
            raise NotFound(url)
        if r.status_code in (429, 503) or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.content if binary else r.text
    raise RuntimeError(f"SEC request kept failing: {url}")


def get_json(url):
    return json.loads(get(url))


def cik10(cik):
    return str(int(cik)).zfill(10)


def submissions_url(cik):
    return f"https://data.sec.gov/submissions/CIK{cik10(cik)}.json"


def companyfacts_url(cik):
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10(cik)}.json"


def filing_base(cik, accn):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}"


def filing_index_url(cik, accn):
    return filing_base(cik, accn) + "/index.json"


def doc_url(cik, accn, name):
    return f"{filing_base(cik, accn)}/{name}"


def current_feed_url(form, start=0, count=100):
    return ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
            f"&type={form}&company=&dateb=&owner=include&start={start}&count={count}&output=atom")


def daily_index_url(day):
    q = (day.month - 1) // 3 + 1
    return f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{q}/form.{day:%Y%m%d}.idx"
