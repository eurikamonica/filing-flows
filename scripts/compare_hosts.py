"""Compare two hosts of the same static site, page by page: the one serving the domain now (GitHub Pages) and a new
server reached by its IP address before the domain points to it (deploy/README.md, "Test before the switch").

    python scripts/compare_hosts.py --old https://filing-flows.com --new-ip 203.0.113.5 --sample 300

Every request goes to both sides without following redirects. The new side is asked with the site's name in the
Host header (and as the TLS name): HTTPS when it answers there (live / origin mode), plain HTTP otherwise (staging).
Compared per address: status code, redirect target (as a path on the site, so an absolute and a relative Location
match), content type and the body's SHA-256. The addresses: a fixed list of the rules that matter for search
engines (directory without its slash, /page without .html, a missing page, www, robots.txt, sitemaps, the IndexNow
key file …) plus a random sample of every sitemap's pages. A body that differs is usually a build published on one
side a minute before the other; the report lists them, and statuses or redirects that differ are what to fix.
Only the Python standard library; the summary also goes to the run's page ($GITHUB_STEP_SUMMARY).
"""
import argparse
import concurrent.futures as cf
import hashlib
import http.client
import json
import os
import random
import re
import socket
import ssl
import sys
import time
from urllib.parse import urljoin, urlsplit

UA = "FilingFlows-HostCompare/1.0"
FIXED = ["/", "/index.html", "/robots.txt", "/sitemap-index.xml", "/sitemap.xml", "/c/amzn", "/c/amzn/",
         "/c/amzn?ref=compare", "/c/amzn/index.html", "/zh/", "/zh", "/m/", "/o/", "/disclosures/", "/disclosures",
         "/CNAME", "/.nojekyll", "/ff-compare-no-such-page", "/c/ff-compare-no-such-company/",
         "/ff-compare-no-such-file.json"]


def fetch(scheme, connect_host, port, host, path, insecure, timeout=20, method="GET"):
    """(status, headers{lower: value}, body) of one request, no redirects followed; status 0 when no answer."""
    try:
        if scheme == "https":
            ctx = ssl.create_default_context()
            if insecure:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            sock = socket.create_connection((connect_host, port), timeout=timeout)
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
            conn.sock = ctx.wrap_socket(sock, server_hostname=host)
        else:
            conn = http.client.HTTPConnection(connect_host, port, timeout=timeout)
        conn.request(method, path, headers={"Host": host, "User-Agent": UA, "Accept-Encoding": "identity"})
        r = conn.getresponse()
        body = r.read(32 * 1024 * 1024)
        headers = {k.lower(): v for k, v in r.getheaders()}
        conn.close()
        return r.status, headers, body
    except (OSError, http.client.HTTPException, ssl.SSLError) as err:
        return 0, {"error": f"{type(err).__name__}: {str(err)[:120]}"}, b""


class Side:
    def __init__(self, name, scheme, connect_host, port, host, insecure):
        self.name, self.scheme, self.connect_host, self.port, self.host, self.insecure = \
            name, scheme, connect_host, port, host, insecure

    def get(self, path, host=None, method="GET"):
        # the old side reaches another name (www) through that name's own DNS record; the new one by its address
        connect = host if (host and self.name == "old") else self.connect_host
        return fetch(self.scheme, connect, self.port, host or self.host, path, self.insecure, method=method)

    def __repr__(self):
        return f"{self.scheme}://{self.connect_host}:{self.port} (Host: {self.host})"


def old_side(url):
    u = urlsplit(url)
    return Side("old", u.scheme, u.hostname, u.port or (443 if u.scheme == "https" else 80), u.hostname, False)


def new_side(ip, host, scheme="auto"):
    """The new server by address: HTTPS with the site's name when it answers there, else plain HTTP."""
    if scheme in ("auto", "https"):
        st, h, _ = fetch("https", ip, 443, host, "/robots.txt", True, timeout=10)
        if st or scheme == "https":
            return Side("new", "https", ip, 443, host, True)
    return Side("new", "http", ip, 80, host, True)


def norm_location(loc, side_host, site_host):
    """A redirect target as a path on the site (absolute and relative forms compare equal); other hosts as is."""
    if not loc:
        return None
    u = urlsplit(urljoin(f"https://{side_host}/", loc))
    if u.hostname in (site_host, side_host):
        return (u.path or "/") + (f"?{u.query}" if u.query else "")
    return f"{u.scheme}://{u.hostname}{u.path}" + (f"?{u.query}" if u.query else "")


def summary(st, h, body, side_host, site_host):
    return {"status": st, "location": norm_location(h.get("location"), side_host, site_host),
            "type": (h.get("content-type") or "").split(";")[0].strip().lower() or None,
            "sha256": hashlib.sha256(body).hexdigest() if st == 200 else None, "bytes": len(body),
            "error": h.get("error")}


def compare_one(old, new, path, site_host, host=None):
    a = summary(*old.get(path, host=host), host or old.host, site_host)
    b = summary(*new.get(path, host=host), host or new.host, site_host)
    diffs = [k for k in ("status", "location", "type") if a[k] != b[k]]
    if not diffs and a["sha256"] != b["sha256"]:
        diffs = ["body"]
    return {"path": path, "host": host or site_host, "old": a, "new": b, "diff": diffs}


LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def sitemap_paths(old, site_host, limit_maps=200):
    """Every page listed in the sitemaps of the live site (sitemap-index.xml, else sitemap.xml)."""
    maps, pages, seen = [], [], set()
    for start in ("/sitemap-index.xml", "/sitemap.xml"):
        st, _, body = old.get(start)
        if st == 200:
            maps.append(start)
            break
    while maps and len(seen) < limit_maps:
        m = maps.pop(0)
        if m in seen:
            continue
        seen.add(m)
        st, _, body = old.get(m)
        if st != 200:
            continue
        text = body.decode("utf-8", "replace")
        for loc in LOC.findall(text):
            u = urlsplit(loc)
            if u.hostname and u.hostname not in (site_host, "www." + site_host):
                continue
            p = (u.path or "/") + (f"?{u.query}" if u.query else "")
            (maps if "<sitemapindex" in text else pages).append(p)
    return pages, sorted(seen)


def extensionless(paths):
    """/x/page.html → /x/page (GitHub Pages answers both); a few of them."""
    out = [p[:-5] for p in paths if p.endswith(".html") and not p.endswith("/index.html")]
    return out[:10]


def indexnow_key(root):
    try:
        with open(os.path.join(root, "config", "indexnow.json"), encoding="utf-8") as f:
            return json.load(f).get("key")
    except (OSError, ValueError):
        return None


def run(old, new, site_host, sample, seed, workers=8):
    pages, maps = sitemap_paths(old, site_host)
    rnd = random.Random(seed)
    picked = rnd.sample(pages, min(sample, len(pages))) if pages else []
    fixed = list(FIXED)
    key = os.environ.get("INDEXNOW_KEY") or indexnow_key(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if key:
        fixed.append(f"/{key}.txt")
    fixed += maps[:20] + extensionless(picked)
    jobs = [(p, None) for p in dict.fromkeys(fixed + picked)]
    jobs += [("/", "www." + site_host), ("/c/amzn/?ref=compare", "www." + site_host)]
    with cf.ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(lambda j: compare_one(old, new, j[0], site_host, j[1]), jobs))
    return {"old": repr(old), "new": repr(new), "site": site_host, "sitemap_pages": len(pages), "sitemaps": len(maps),
            "checked": len(rows), "rows": rows, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def report_md(r):
    rows = r["rows"]
    serious = [x for x in rows if set(x["diff"]) & {"status", "location", "type"}]
    body = [x for x in rows if x["diff"] == ["body"]]
    same = len(rows) - len(serious) - len(body)
    out = [f"## Old host vs new server ({r['at']})", "",
           f"Old: `{r['old']}` · New: `{r['new']}` · {r['sitemap_pages']:,} pages in {r['sitemaps']} sitemaps, "
           f"{r['checked']} addresses checked", "",
           f"- **{same}** identical (status, redirect, type and content)",
           f"- **{len(serious)}** with a different status, redirect or type" + (" ← fix these" if serious else ""),
           f"- **{len(body)}** with the same status but different content (usually a build published a minute "
           "apart on the two sides)", ""]

    def cell(s):
        if s["status"] == 0:
            return f"no answer ({s['error']})"
        t = str(s["status"])
        if s["location"]:
            t += f" → `{s['location']}`"
        if s["type"]:
            t += f" · {s['type']}"
        return t

    if serious:
        out += ["| Address | Old | New |", "|---|---|---|"]
        for x in serious[:60]:
            host = "" if x["host"] == r["site"] else f" (Host {x['host']})"
            out.append(f"| `{x['path']}`{host} | {cell(x['old'])} | {cell(x['new'])} |")
        out.append("")
    if body:
        out += ["Different content: " + ", ".join(f"`{x['path']}`" for x in body[:30])
                + (" …" if len(body) > 30 else ""), ""]
    out += ["<details><summary>The fixed checks</summary>", "", "| Address | Old | New |", "|---|---|---|"]
    for x in rows:
        if x["path"] in FIXED or x["host"] != r["site"]:
            host = "" if x["host"] == r["site"] else f" (Host {x['host']})"
            out.append(f"| `{x['path']}`{host} | {cell(x['old'])} | {cell(x['new'])} |")
    out += ["", "</details>", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old", default="https://filing-flows.com", help="the site as served now")
    ap.add_argument("--new-ip", required=True, help="the new server's address")
    ap.add_argument("--new-scheme", default="auto", choices=["auto", "https", "http"])
    ap.add_argument("--host", help="the site's name (default: the host of --old)")
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="compare-hosts.json")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a status, redirect or type differs")
    a = ap.parse_args(argv)
    old = old_side(a.old)
    site_host = a.host or old.host
    new = new_side(a.new_ip, site_host, a.new_scheme)
    r = run(old, new, site_host, a.sample, a.seed if a.seed is not None else int(time.time()) // 86400)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)
    md = report_md(r)
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    serious = [x for x in r["rows"] if set(x["diff"]) & {"status", "location", "type"}]
    return 1 if (a.strict and serious) else 0


if __name__ == "__main__":
    sys.exit(main())
