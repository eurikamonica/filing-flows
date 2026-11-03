"""Earnings fast lane: S&P 500 and Nasdaq-100 results on the site minutes after the SEC accepts the 8-K.

The full scan reads every new filing, then rebuilds and publishes the whole site: about an hour from an earnings
release to its page in earnings season (Apple, Nov 2 2026: accepted 16:30, live 17:33). This lane does one thing:

  watch   polls EDGAR's live 8-K feed (every 15 s in the busy hours, 45 s otherwise) for an Item 2.02 of an index
          member; on a hit it claims the filings (claimed.json on the branch "fastlane") and stops, so the workflow
          builds them while the next watcher is already running (.github/workflows/earnings-fast.yml)
  build   reads each release with the regular reader (build.process_filing) into a store that holds only that
          company's record (from the branch "data"), and draws its files with the regular renderer (build.render)
  patch   puts them into the last published site: data/c/<cik>.json, its row in data/index.json and its page
          c/<slug>/; and into the overlay (overlay/<cik>.json on the branch "fastlane")
  apply   (scan.yml) lays the overlay onto the site a full scan builds, for each company whose overlay quarter is newer
          than the scan's own, so a scan that started before the release does not take the page back. Once the scan
          has read the filing itself the overlay entry is no longer used; entries expire after five days.

Nothing here writes the data store: the full scan reads the same filing through its own queue, as before.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include"
        "&start=0&count=100&output=atom")
SITE = os.environ.get("SITE_URL") or "https://filing-flows.com"
INDEXES = ("sp500", "ndx")
KEEP_DAYS = 5                     # overlay entries older than this are left out: the full scan has read them by then
BUSY = ((6 * 60, 9 * 60 + 45), (15 * 60 + 55, 18 * 60 + 30))      # ET minutes: most releases come out in these
OPEN = (6 * 60, 22 * 60)                                          # EDGAR accepts filings 6:00-22:00 ET


def now_et():
    return dt.datetime.now(ET)


def in_window(t=None, busy=False):
    t = t or now_et()
    if t.weekday() >= 5:
        return False
    m = t.hour * 60 + t.minute
    return any(a <= m < b for a, b in (BUSY if busy else (OPEN,)))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


# ---------------------------------------------------------------- who is watched
def members(members_json, tickers_json):
    """CIKs of the S&P 500 and Nasdaq-100 members: tickers from the hub's index-membership file (the ETFs' holdings,
    disclosures/data/etf/members.json), CIKs from SEC's ticker list."""
    rows = (members_json or {}).get("rows") or {}
    want = {t.upper() for t, r in rows.items() if set(r.get("now") or []) & set(INDEXES)}
    cik_of = {}
    for v in (tickers_json or {}).values():
        cik_of.setdefault(str(v.get("ticker", "")).upper(), int(v["cik_str"]))
    out = {}
    for t in sorted(want):
        k = cik_of.get(t) or cik_of.get(t.replace(".", "-")) or cik_of.get(t.replace("-", "."))
        if k:
            out[k] = t
    return out


# ---------------------------------------------------------------- the feed
ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S)


def parse_feed(xml):
    """EDGAR's live 8-K feed → [{"cik", "accn", "items", "updated", "name"}] (newest first)."""
    out = []
    for e in ENTRY.findall(xml or ""):
        title = html.unescape(re.search(r"<title>(.*?)</title>", e, re.S).group(1)) if "<title>" in e else ""
        m = re.search(r"\((\d{10})\)\s*\((Filer|Subject|Reporting)", title)
        a = re.search(r"accession-number=(\d{10}-\d{2}-\d{6})", e)
        if not m or not a:
            continue
        summ = html.unescape(re.search(r"<summary[^>]*>(.*?)</summary>", e, re.S).group(1)) if "<summary" in e else ""
        upd = re.search(r"<updated>(.*?)</updated>", e)
        form = re.search(r'term="([^"]+)"', e)
        out.append({"cik": int(m.group(1)), "accn": a.group(1), "role": m.group(2),
                    "items": re.findall(r"Item (\d+\.\d+)", summ), "updated": upd.group(1) if upd else "",
                    "form": form.group(1) if form else "8-K", "name": re.sub(r"\s*\(\d{10}\).*$", "", title).replace("8-K - ", "")})
    return out


def hits(entries, watched, claimed):
    """Earnings releases (8-K Item 2.02, not an amendment) of watched companies not claimed yet."""
    out, seen = [], set()
    for e in entries:
        if e["form"] != "8-K" or "2.02" not in e["items"] or e["cik"] not in watched:
            continue
        if e["accn"] in claimed or e["accn"] in seen:
            continue
        seen.add(e["accn"])
        out.append(dict(e, ticker=watched[e["cik"]]))
    return out


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def stamp_now():
    return utcnow().isoformat(timespec="seconds") + "Z"


def taken_back(lane, claimed, live, now=None, hours=3, settle_min=15, again_min=20):
    """Overlay entries of the last few hours that the live site does not show: a full scan's deploy that was already
    under way when the fast lane published put its own, older copy over it. They are published again (re = True)
    — after the CDN has had time to show the fast lane's copy, and at most every again_min minutes each."""
    now = now or utcnow()
    out = []
    for e in entries(lane, days=hours / 24, now=now):
        m = e["meta"]
        at = dt.datetime.fromisoformat(m["at"].rstrip("Z"))
        re_at = (claimed.get(m["accn"]) or {}).get("re")
        if now - at < dt.timedelta(minutes=settle_min):
            continue
        if re_at and now - dt.datetime.fromisoformat(re_at.rstrip("Z")) < dt.timedelta(minutes=again_min):
            continue
        site_c = live(int(m["cik"]))
        if site_c is not None and newer(e, site_c):
            out.append({"cik": int(m["cik"]), "accn": m["accn"], "ticker": m["ticker"], "items": ["2.02"], "form": "8-K",
                        "re": True})
    return out


def _live_company(cik):
    import requests
    try:
        r = requests.get(f"{SITE}/data/c/{int(cik)}.json", params={"t": int(time.time() // 60)}, timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _pull(lane):
    import subprocess
    if os.path.isdir(os.path.join(lane, ".git")):
        subprocess.run(["git", "-C", lane, "pull", "--quiet", "--rebase", "origin", "fastlane"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def watch(args):
    """Poll the feed until a hit (then write it and stop) or until the time is up. Exit code 0 either way."""
    from . import sec
    watched = members(sec_json_or(args.members, f"{SITE}/disclosures/data/etf/members.json"),
                      sec.get_json("https://www.sec.gov/files/company_tickers.json"))
    print(f"watching {len(watched)} S&P 500 / Nasdaq-100 companies")
    claimed = load(os.path.join(args.lane, "claimed.json"), {})
    t_end = time.time() + 60 * args.minutes
    next_check = time.time() + 60
    while time.time() < t_end:
        if not in_window():
            print("outside EDGAR's hours: the watcher stops")
            break
        try:
            found = hits(parse_feed(sec.get(FEED)), watched, claimed)
        except Exception as e:                                   # one failed poll: try again on the next
            print(f"::warning::feed not read: {e}")
            found = []
        if not found and time.time() >= next_check:              # pages a full scan's deploy took back
            next_check = time.time() + args.check
            _pull(args.lane)
            claimed.update(load(os.path.join(args.lane, "claimed.json"), {}))
            found = taken_back(args.lane, claimed, _live_company)
            if found:
                print("taken back by a full scan's deploy, published again: " + ", ".join(h["ticker"] for h in found))
        if found and not found[0].get("re"):
            time.sleep(args.gather)                              # releases often come in bunches at :00 and :30
            try:
                found = hits(parse_feed(sec.get(FEED)), watched, claimed) or found
            except Exception:
                pass
        if found:
            stamp = stamp_now()
            _pull(args.lane)
            for k, v in load(os.path.join(args.lane, "claimed.json"), {}).items():
                claimed.setdefault(k, v)
            for h in found:
                claimed[h["accn"]] = dict(claimed.get(h["accn"]) or {}, cik=h["cik"], ticker=h["ticker"],
                                          **({"re": stamp} if h.get("re") else {"t": stamp}))
            cut = (utcnow() - dt.timedelta(days=7)).isoformat()
            save(os.path.join(args.lane, "claimed.json"), {k: v for k, v in claimed.items() if (v.get("t") or v.get("re") or "") >= cut})
            save(args.out, found)
            print("hit: " + ", ".join(f"{h['ticker']} {h['accn']}" for h in found))
            return 0
        time.sleep(args.every_busy if in_window(busy=True) else args.every)
    save(args.out, [])
    return 0


def sec_json_or(path, url):
    if path and os.path.exists(path):
        return load(path, {})
    import requests
    r = requests.get(url, timeout=60, headers={"User-Agent": "filing-flows fast lane"})
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- build
def _quiet_render_extras(B):
    """The renderer also builds sector totals, supply chains, industry flows … from every company in the store; with
    one company those are empty and only cost time."""
    import importlib
    for name in ("chains", "gamma"):
        mod = getattr(B, name, None)
        if mod is not None:
            setattr(mod, "build", lambda *a, **k: None)
    for name in ("custnet", "investments", "ioflow", "ioflow_beta", "hier"):
        try:
            mod = importlib.import_module(f"pipeline.{name}")
            setattr(mod, "build", lambda *a, **k: None)
        except Exception:
            pass


def build(args):
    """Each hit read into the store (one record per company) and drawn into args.out (data/c/<cik>.json, rows.json)."""
    from . import build as B
    _quiet_render_extras(B)
    found = load(args.hits, [])
    store = B.Store(args.store)
    B.EPS_ROOT[0] = None                                       # the EPS series stay with the full scan's store
    stars = B.starred_ciks()
    done = []
    for h in found:
        cik, accn = int(h["cik"]), h["accn"]
        t_end = time.time() + 60 * args.wait
        while True:
            B._sub.pop(cik, None)                                # the filing reaches submissions a minute or two late
            try:
                end = B.process_filing(store, cik, accn, "8-K", starred=cik in stars)
                print(f"{h['ticker']}: {accn} read, quarter ending {end}")
                done.append(dict(h, end=end))
                break
            except B.Pending as e:
                if time.time() > t_end:
                    print(f"::warning::{h['ticker']} {accn}: still pending after {args.wait} min ({e}); the full scan reads it")
                    break
                time.sleep(15)
            except B.NotApplicable as e:
                print(f"{h['ticker']} {accn}: not drawn ({e}); the full scan decides")
                break
            except Exception as e:
                print(f"::warning::{h['ticker']} {accn}: {e}")
                break
    if not done:
        save(os.path.join(args.out, "done.json"), [])
        return 0
    B.render(store, os.path.join(args.out, "data"), stars)
    ix = load(os.path.join(args.out, "data", "index.json"), {})
    rows = {r["cik"]: r for r in ix.get("companies") or []}
    ok = []
    for h in done:
        r = rows.get(int(h["cik"]))
        c = load(os.path.join(args.out, "data", "c", f"{int(h['cik'])}.json"), None)
        if not r or not c or not (c.get("quarters") or [{}])[0].get("form") == "8-K":
            print(f"::warning::{h['ticker']}: nothing new to publish")
            continue
        ok.append({"cik": int(h["cik"]), "accn": h["accn"], "ticker": h["ticker"], "end": r["end"], "filed": r["filed"],
                   "label": r["label"], "row": r})
    save(os.path.join(args.out, "done.json"), ok)
    print(f"built {len(ok)}: " + ", ".join(f"{x['ticker']} {x['label']}" for x in ok))
    return 0


# ---------------------------------------------------------------- the site and the overlay
def _accn_of(q):
    m = re.search(r"/(\d{18})/", (q or {}).get("index_url") or (q or {}).get("doc_url") or "")
    return f"{m.group(1)[:10]}-{m.group(1)[10:12]}-{m.group(1)[12:]}" if m else None


def newer(entry, site_c):
    """Is the overlay's quarter newer than the one the site draws for the company?"""
    q = ((site_c or {}).get("quarters") or [None])[0]
    if not q:
        return True
    end = entry["meta"]["end"]
    if (q.get("end") or "") > end:
        return False
    if (q.get("end") or "") == end:
        return q.get("form") == "8-K" and _accn_of(q) != entry["meta"]["accn"]
    return True


def put(data_dir, entry):
    """The overlay entry into a site's data: its company file and its row in index.json (newest filings first)."""
    cik = int(entry["meta"]["cik"])
    save(os.path.join(data_dir, "c", f"{cik}.json"), entry["company"])
    p = os.path.join(data_dir, "index.json")
    ix = load(p, {"companies": []})
    rows = [r for r in ix.get("companies") or [] if int(r.get("cik", 0)) != cik] + [entry["row"]]
    ix["companies"] = sorted(rows, key=lambda x: (x.get("filed") or "", x.get("cik") or 0), reverse=True)
    save(p, ix)


def entries(lane, days=KEEP_DAYS, now=None):
    d = os.path.join(lane, "overlay")
    cut = ((now or utcnow()) - dt.timedelta(days=days)).isoformat()
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        e = load(os.path.join(d, f), None) if f.endswith(".json") else None
        if e and e.get("meta", {}).get("at", "") >= cut:
            out.append(e)
    return out


def patch(args):
    """The built companies into the published site (args.site) and the overlay (args.lane); their pages rewritten."""
    done = load(os.path.join(args.built, "done.json"), [])
    if not done:
        print("nothing to patch")
        return 0
    stamp = stamp_now()
    data = os.path.join(args.site, "data")
    put_ciks = []
    for d in done:
        cik = int(d["cik"])
        company = load(os.path.join(args.built, "data", "c", f"{cik}.json"), None)
        entry = {"meta": {"cik": cik, "accn": d["accn"], "ticker": d["ticker"], "end": d["end"], "filed": d["filed"],
                          "label": d["label"], "at": stamp}, "company": company, "row": d["row"]}
        save(os.path.join(args.lane, "overlay", f"{cik}.json"), entry)
        if newer(entry, load(os.path.join(data, "c", f"{cik}.json"), None)):
            put(data, entry)
            put_ciks.append(cik)
    pages(args.site, put_ciks, args.base)
    print(f"patched {len(put_ciks)} companies into the site: " + ", ".join(str(c) for c in put_ciks))
    return 0


def pages(site, ciks, base):
    """Rewrite the static pages (c/<slug>/) of these companies with the regular page writer (scripts/seo.py)."""
    if not ciks or not base:
        return 0
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import seo
    ctx = seo.page_context(os.path.join(site, "data"), base.rstrip("/"))
    n = 0
    for cik in ciks:
        if seo.write_company(ctx, os.path.join(site, "data"), site, base.rstrip("/"), int(cik)):
            n += 1
    return n


def apply(args):
    """(scan.yml) The overlay onto the site the scan built: companies whose fast-lane quarter is newer than the scan's."""
    data = args.data
    used = []
    for e in entries(args.lane):
        cik = int(e["meta"]["cik"])
        if newer(e, load(os.path.join(data, "c", f"{cik}.json"), None)):
            put(data, e)
            used.append(cik)
            print(f"fast lane: {e['meta']['ticker']} {e['meta']['label']} ({e['meta']['accn']}) laid over the scan's data")
    if args.pages and used:
        pages(os.path.dirname(os.path.abspath(data.rstrip("/"))), used, args.pages)
    print(f"fast lane overlay: {len(used)} used")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch")
    w.add_argument("--lane", default="lane")
    w.add_argument("--out", default="hits.json")
    w.add_argument("--members", default=None, help="a local copy of disclosures/data/etf/members.json")
    w.add_argument("--minutes", type=float, default=50)
    w.add_argument("--every", type=float, default=45)
    w.add_argument("--every-busy", type=float, default=15)
    w.add_argument("--gather", type=float, default=20)
    w.add_argument("--check", type=float, default=300, help="seconds between checks of the live site (taken_back)")
    b = sub.add_parser("build")
    b.add_argument("--hits", default="hits.json")
    b.add_argument("--store", default="store")
    b.add_argument("--out", default="fast")
    b.add_argument("--wait", type=float, default=5, help="minutes to wait for a filing to reach SEC's submissions")
    p = sub.add_parser("patch")
    p.add_argument("--built", default="fast")
    p.add_argument("--site", default="_site")
    p.add_argument("--lane", default="lane")
    p.add_argument("--base", default=SITE)
    a = sub.add_parser("apply")
    a.add_argument("--data", default="_site/data")
    a.add_argument("--lane", default="lane")
    a.add_argument("--pages", default="", help="the site's URL: also rewrite these companies' pages (c/<slug>/)")
    args = ap.parse_args(argv)
    return {"watch": watch, "build": build, "patch": patch, "apply": apply}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
