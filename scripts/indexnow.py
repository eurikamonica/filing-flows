"""IndexNow: tell Bing, Yandex, Naver, Seznam and Yep which pages are new or changed, right after a deploy.
(Google does not take part in IndexNow; it reads sitemap.xml, submitted once in Search Console.)

    python scripts/indexnow.py key --out _site              # build: write <key>.txt at the site root (build_site.py calls write_key)
    python scripts/indexnow.py submit --site-url https://filing-flows.com --state .indexnow/state.json

submit reads the live sitemap.xml and sitemap-people.xml, compares them with the snapshot of the last successful
submission (url -> lastmod), and posts the pages that are new, changed or gone. No snapshot yet: every page once.
The snapshot is rewritten only when the search engines accepted the list (200/202), so a failed run is retried by
the next scan. It never fails the site: every problem is a warning and exit code 0.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config", "indexnow.json")
SITEMAPS = ("sitemap.xml", "sitemap-people.xml", "sitemap-topics.xml", "sitemap-quarters.xml", "sitemap-periods.xml", "sitemap-metrics.xml", "sitemap-daily.xml", "sitemap-compare.xml", "sitemap-zh.xml", "sitemap-es.xml", "sitemap-fr.xml", "sitemap-hub.xml", "sitemap-cashflow.xml")
BATCH = 10000                      # the protocol's limit per request
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
UA = "FilingFlows-IndexNow/1.0 (+https://filing-flows.com/)"


def config():
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    key = (os.environ.get("INDEXNOW_KEY") or cfg.get("key") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):
        key = ""
    return key, cfg.get("endpoint") or "https://api.indexnow.org/indexnow"


def resend_round():
    try:
        return str(json.load(open(CONFIG, encoding="utf-8")).get("resend_all") or "")
    except (OSError, ValueError):
        return ""


def write_key(out_dir):
    """The key file the search engines fetch to check the submission is ours: /<key>.txt holding the key."""
    key, _ = config()
    if key:
        with open(os.path.join(out_dir, f"{key}.txt"), "w", encoding="utf-8") as f:
            f.write(key)
    return key


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_sitemap(xml_bytes):
    """{url: lastmod or ''} from one sitemap."""
    out = {}
    for u in ET.fromstring(xml_bytes).iter(f"{NS}url"):
        loc = (u.findtext(f"{NS}loc") or "").strip()
        if loc:
            out[loc] = (u.findtext(f"{NS}lastmod") or "").strip()
    return out


def changes(now, before):
    """Pages to submit: new or with a different lastmod, plus pages that are gone (so they drop out of the index).
    No earlier snapshot: everything."""
    if before is None:
        return sorted(now)
    return sorted([u for u, m in now.items() if before.get(u) != m] + [u for u in before if u not in now])


def post(endpoint, host, key, urls, timeout=60):
    body = json.dumps({"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt", "urlList": urls}).encode()
    req = urllib.request.Request(endpoint, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, ""
    except urllib.error.HTTPError as err:
        return err.code, err.read()[:300].decode("utf-8", "replace")


MEANING = {400: "bad request (format)", 403: "key not valid (key file missing or different)",
           422: "pages not on this host, or the key does not match", 429: "too many requests (seen as spam): wait"}


def output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{name}={value}\n")


def submit(base, state_path, endpoint=None, fetch=get, send=post):
    """Returns the number of pages submitted (0: nothing to do or not accepted); writes the snapshot on success."""
    base = base.strip().rstrip("/")
    key, default_endpoint = config()
    endpoint = endpoint or default_endpoint
    host = re.sub(r"^https?://", "", base).split("/")[0]
    if not key or not host:
        print("::warning::IndexNow: no key or no site address; nothing sent")
        return 0
    stamp = int(time.time())
    now = {}
    for name in SITEMAPS:
        try:
            now.update(parse_sitemap(fetch(f"{base}/{name}?v={stamp}")))
        except Exception as err:  # noqa: BLE001
            if name == "sitemap.xml":
                print(f"::warning::IndexNow: {name} could not be read ({str(err)[:120]}); nothing sent")
                return 0
            print(f"IndexNow: {name} not read ({str(err)[:120]})")
    now = {u: m for u, m in now.items() if re.sub(r"^https?://", "", u).split("/")[0] == host}
    try:
        before = json.load(open(state_path, encoding="utf-8"))
    except (OSError, ValueError):
        before = None
    rnd = resend_round()                    # config "resend_all": change it to send every page once more
    if before is not None and before.pop("_round", "") != rnd:
        before = None
    todo = changes(now, before)
    print(f"IndexNow: {len(now)} pages in the sitemaps; "
          + ("no earlier submission, sending all" if before is None else f"{len(todo)} new, changed or gone since the last one"))
    if not todo:
        return 0
    try:                                    # the search engines fetch this file to check the key; it must be live
        live = fetch(f"{base}/{key}.txt?v={stamp}").decode("utf-8", "replace").strip()
    except Exception as err:  # noqa: BLE001
        live = f"({str(err)[:80]})"
    if live != key:
        print(f"::warning::IndexNow: {base}/{key}.txt is not live yet ({live[:80]}); trying again next scan")
        return 0
    for i in range(0, len(todo), BATCH):
        status, text = send(endpoint, host, key, todo[i:i + BATCH])
        if status not in (200, 202):
            print(f"::warning::IndexNow: HTTP {status} {MEANING.get(status, '')} {text}".rstrip())
            return 0
        print(f"IndexNow: {len(todo[i:i + BATCH])} pages accepted (HTTP {status}"
              + (", key check pending" if status == 202 else "") + ")")
    os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(dict(now, _round=rnd), f, separators=(",", ":"))
    output("saved", "true")
    return len(todo)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("key", help="write <key>.txt into the built site")
    k.add_argument("--out", default="_site")
    s = sub.add_parser("submit", help="send new and changed pages after a deploy")
    s.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    s.add_argument("--state", default=".indexnow/state.json")
    s.add_argument("--endpoint", default=None)
    a = ap.parse_args()
    if a.cmd == "key":
        print(f"IndexNow key file: {'written' if write_key(a.out) else 'no key configured'}")
    else:
        try:
            submit(a.site_url, a.state, a.endpoint)
        except Exception as err:  # noqa: BLE001 — never fails the site
            print(f"::warning::IndexNow: {str(err)[:200]}")
    sys.exit(0)
