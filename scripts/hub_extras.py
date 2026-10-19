"""Build-time extras over the finished site (_site with data/ and the staged Disclosure Hub in disclosures/):

- data/search.json — what the site's global search (web/search.js, Ctrl/⌘ K) finds beyond companies: 13F managers the
  hub reads, officials with trades on file, ETFs; plus the tickers that have their own feed
- feeds/*.xml — Atom feeds: the latest filings on the site, and the hub's insider trades, 8-K events and officials'
  trades; feeds/c/<TICKER>.xml for the largest companies (their filings and every disclosure the hub joins to them)

    python scripts/hub_extras.py --site _site [--site-url https://filing-flows.com/] [--companies 300]

Without a staged hub (a local build) it reads the repository's disclosures/docs/data instead. Never fails the build:
a missing input leaves its part out.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
REPO_HUB = ROOT / "disclosures" / "docs" / "data"


def read(path, default=None):
    try:
        p = Path(path)
        if p.suffix == ".gz":
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm(t):
    t = re.sub(r"[./\s]+", "-", str(t or "").strip().upper())
    return t if re.fullmatch(r"[A-Z0-9-]{1,10}", t) else ""


def unhtml(s):
    return re.sub(r"&(amp|lt|gt|quot|#39);", lambda m: {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "#39": "'"}[m.group(1)], str(s or ""))


# ---------------------------------------------------------------- the search index
def search_index(hub, companies):
    """managers [cik, filer name, label, positions], officials [name, chamber, trades], etfs [symbol, name, aum]."""
    labels = {str(f.get("cik")): f.get("name") for f in (read(hub / "market" / "watchlist.json", {}) or {}).get("funds", [])}
    managers = []
    for m in read(hub / "catalogs" / "holdings.json", []) or []:
        if m.get("processed") and m.get("cik"):
            cik = str(m["cik"])
            managers.append([cik, m.get("name") or cik, labels.get(cik) or "", int(m.get("filing_count") or 0)])
    for cik, lab in labels.items():                                # the watched funds are always findable
        if lab and not any(r[0] == cik for r in managers):
            managers.append([cik, lab, lab, 0])
    managers.sort(key=lambda r: (not r[2], -r[3], r[1]))
    people = {}
    for t in (read(hub / "market" / "officials-trades.json", {}) or {}).get("trades", []):
        p = (t.get("person") or "").strip()
        if p:
            r = people.setdefault(p, [p, t.get("jurisdiction") or "", 0])
            r[2] += 1
    officials = sorted(people.values(), key=lambda r: -r[2])
    etfs = []
    ix = read(hub / "etf" / "index.json", {}) or {}
    F = ix.get("fields") or []
    if "symbol" in F:
        si, ni, ai = F.index("symbol"), (F.index("name") if "name" in F else None), (F.index("aum") if "aum" in F else None)
        for r in ix.get("rows") or []:
            if r[si]:
                etfs.append([r[si], r[ni] if ni is not None else "", round(r[ai] or 0) if ai is not None and isinstance(r[ai], (int, float)) else 0])
        etfs.sort(key=lambda r: -r[2])
    return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "managers": managers, "officials": officials, "etfs": etfs}


# ---------------------------------------------------------------- Atom feeds
def atom(title, self_url, site_url, entries, subtitle=""):
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">', f"<title>{escape(title)}</title>",
           f'<link rel="self" href="{escape(self_url)}"/>', f'<link href="{escape(site_url)}"/>', f"<id>{escape(self_url)}</id>", f"<updated>{now}</updated>",
           "<author><name>Filing Flows</name></author>"]
    if subtitle:
        out.append(f"<subtitle>{escape(subtitle)}</subtitle>")
    for e in entries:
        when = (e.get("date") or now)[:10] + "T00:00:00Z" if len(e.get("date") or "") <= 10 else e["date"]
        link = e.get("link") or site_url
        eid = str(e.get("id") or "") or link + "#" + hashlib.sha1(e["title"].encode()).hexdigest()[:12]
        if not re.match(r"https?://|urn:", eid):
            eid = "urn:filing-flows:" + re.sub(r"[^A-Za-z0-9:._-]+", "-", eid)[:120]
        out += ["<entry>", f"<title>{escape(e['title'])}</title>", f'<link href="{escape(link)}"/>', f"<id>{escape(eid)}</id>",
                f"<updated>{escape(when)}</updated>", f"<summary>{escape(e.get('summary') or '')}</summary>", "</entry>"]
    out.append("</feed>")
    return "\n".join(out) + "\n"


def money(v):
    if not isinstance(v, (int, float)):
        return ""
    a, s = abs(v), "−" if v < 0 else ""
    return f"{s}${a / 1e12:.2f}T" if a >= 1e12 else f"{s}${a / 1e9:.1f}B" if a >= 1e9 else f"{s}${a / 1e6:.1f}M" if a >= 1e6 else f"{s}${a:,.0f}"


def filing_entries(companies, site_url, limit=60):
    rows = sorted((c for c in companies if c.get("filed")), key=lambda c: (c["filed"], c.get("revenue") or 0), reverse=True)[:limit]
    return [{"date": c["filed"], "title": f"{c.get('ticker') or c['cik']} — {unhtml(c['name'])}: {c.get('form')} {unhtml(c.get('label') or '')}",
             "summary": ", ".join(x for x in [f"revenue {c['rev']}" if c.get("rev") else "", f"{c['yoy']:+.0f}% Y/Y" if isinstance(c.get("yoy"), (int, float)) else "",
                                             f"operating margin {c['om']:.1f}%" if isinstance(c.get("om"), (int, float)) else ""] if x),
             "link": f"{site_url}#c-{c['cik']}-{c.get('end')}", "id": f"{site_url}#c-{c['cik']}-{c.get('end')}-{c.get('form')}"} for c in rows]


def insider_entries(hub, site_url, limit=60):
    d = read(hub / "market" / "insiders.json", {}) or {}
    out = []
    for t in (d.get("latest") or [])[:limit]:
        verb = "bought" if t.get("code") == "P" else "sold" if t.get("code") == "S" else "traded"
        price = f" at ${t['price']:,.2f}" if isinstance(t.get("price"), (int, float)) else ""
        out.append({"date": t.get("date"), "title": f"{t.get('ticker') or t.get('issuer')}: {t.get('insider')} ({t.get('title') or t.get('role')}) {verb} {t.get('shares') or 0:,.0f} shares{price}",
                    "summary": ", ".join(x for x in [money(t.get("value")), "10b5-1 plan" if t.get("plan_10b5_1") else "", f"Form 4 {t.get('accession')}"] if x),
                    "link": t.get("url") or f"{site_url}disclosures/#insiders", "id": f"{t.get('accession')}:{t.get('date')}:{t.get('shares')}"})
    return out


def events_entries(hub, site_url, limit=60):
    d = read(hub / "market" / "events8k.json", {}) or {}
    rows = sorted(d.get("rows") or [], key=lambda r: r.get("accepted") or r.get("filed") or "", reverse=True)[:limit]
    return [{"date": r.get("filed"), "title": f"{r.get('ticker') or r.get('company')}: 8-K — {r.get('label') or ', '.join(r.get('items') or [])}",
             "summary": (r.get("headline") or r.get("quote") or "")[:400], "link": r.get("url") or f"{site_url}disclosures/#events", "id": r.get("accession")} for r in rows]


def officials_entries(hub, site_url, limit=60):
    d = read(hub / "market" / "officials-trades.json", {}) or {}
    rows = sorted(d.get("trades") or [], key=lambda t: (t.get("filed_date") or "", t.get("date") or ""), reverse=True)[:limit]
    amt = lambda t: (f"${t['amount_min']:,.0f}–${t['amount_max']:,.0f}" if t.get("amount_max") else f"over ${t['amount_min'] - 1:,.0f}" if t.get("amount_min") else "amount not disclosed")
    return [{"date": t.get("filed_date") or t.get("date"), "title": f"{t.get('person')}: {t.get('type')} {t.get('ticker_canon') or t.get('ticker') or ''} ({amt(t)})".strip(),
             "summary": f"Traded {t.get('date')}, reported {t.get('filed_date')} · {t.get('jurisdiction')}", "link": t.get("source_url") or f"{site_url}disclosures/#trades",
             "id": f"{t.get('report_id')}:{t.get('date')}:{t.get('ticker')}:{t.get('type')}:{t.get('amount_min')}"} for t in rows]


def company_entries(c, site_url, holders):
    """One company's feed: its filings on the site and the hub's per-ticker disclosures."""
    out = [{"date": c["filed"], "title": f"{c.get('form')} {unhtml(c.get('label') or '')} filed", "link": f"{site_url}#c-{c['cik']}-{c.get('end')}",
            "summary": f"revenue {c.get('rev') or '—'}", "id": f"{site_url}#c-{c['cik']}-{c.get('end')}-{c.get('form')}"}] if c.get("filed") else []
    H = holders or {}
    for e in H.get("events8k") or []:
        out.append({"date": e.get("filed"), "title": f"8-K — {e.get('label') or ', '.join(e.get('items') or [])}", "summary": (e.get("headline") or e.get("quote") or "")[:300],
                    "link": e.get("url") or site_url, "id": e.get("accession") or e.get("url")})
    for x in H.get("insiders") or []:
        verb = "bought" if x.get("code") == "P" else "sold"
        out.append({"date": x.get("date"), "title": f"Insider: {x.get('insider')} ({x.get('title') or x.get('role')}) {verb} {x.get('shares') or 0:,.0f} shares",
                    "summary": money(x.get("value")), "link": x.get("url") or site_url, "id": f"{x.get('url')}:{x.get('date')}:{x.get('shares')}"})
    for o in H.get("officials") or []:
        out.append({"date": o.get("date"), "title": f"Official: {o.get('person')} — {o.get('transaction_type') or o.get('kind')}",
                    "summary": f"reported {o.get('filed_date')}", "link": o.get("source_url") or site_url, "id": f"{o.get('source_url')}:{o.get('date')}:{o.get('person')}"})
    for s in H.get("stakes") or []:
        out.append({"date": s.get("filed"), "title": f"Schedule {s.get('form')}: {s.get('holder') or s.get('filer')}", "summary": s.get("label") or "",
                    "link": s.get("url") or site_url, "id": s.get("url")})
    out = [e for e in out if e.get("date")]
    out.sort(key=lambda e: e["date"], reverse=True)
    return out[:50]


def build(site, site_url="https://filing-flows.com/", n_companies=300, hub=None):
    site = Path(site)
    site_url = site_url.rstrip("/") + "/"
    hub = Path(hub) if hub else (site / "disclosures" / "data" if (site / "disclosures" / "data").is_dir() else REPO_HUB)
    ix = read(site / "data" / "index.json", {}) or {}
    companies = ix.get("companies") if isinstance(ix, dict) else (ix or [])
    companies = companies or []
    sx = search_index(hub, companies)
    feeds = site / "feeds"
    (feeds / "c").mkdir(parents=True, exist_ok=True)
    made = {}
    for name, title, entries in (("filings", "Filing Flows — latest earnings filings", filing_entries(companies, site_url)),
                                 ("insiders", "Filing Flows — insider trades (Form 4)", insider_entries(hub, site_url)),
                                 ("8k", "Filing Flows — material 8-K events", events_entries(hub, site_url)),
                                 ("officials", "Filing Flows — officials' trades (House, Senate)", officials_entries(hub, site_url))):
        (feeds / f"{name}.xml").write_text(atom(title, f"{site_url}feeds/{name}.xml", site_url, entries), encoding="utf-8")
        made[name] = len(entries)
    have = []
    for c in sorted((c for c in companies if c.get("ticker")), key=lambda c: -(c.get("revenue") or 0))[:n_companies]:
        t = norm(c["ticker"])
        if not t:
            continue
        H = read(hub / "holders" / f"{t}.json") or read(site / "disclosures" / "data" / "holders" / f"{t}.json")
        (feeds / "c" / f"{t}.xml").write_text(atom(f"{c['ticker']} — {unhtml(c['name'])} on Filing Flows", f"{site_url}feeds/c/{t}.xml", f"{site_url}#c-{c['cik']}",
                                                    company_entries(c, site_url, H), subtitle="Earnings filings and every disclosure joined to this company"), encoding="utf-8")
        have.append(t)
    sx["feeds"] = have
    (site / "data").mkdir(parents=True, exist_ok=True)
    (site / "data" / "search.json").write_text(json.dumps(sx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"managers": len(sx["managers"]), "officials": len(sx["officials"]), "etfs": len(sx["etfs"]), "feeds": made, "company_feeds": len(have)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default="_site")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL") or "https://filing-flows.com/")
    ap.add_argument("--companies", type=int, default=300, help="companies with their own feed (largest by revenue)")
    a = ap.parse_args()
    try:
        r = build(a.site, a.site_url or "https://filing-flows.com/", a.companies)
        print(f"::notice::search index: {r['managers']} managers, {r['officials']} officials, {r['etfs']} ETFs · feeds {r['feeds']} · {r['company_feeds']} company feeds")
    except Exception as err:                                       # noqa: BLE001 — extras never fail the site
        print(f"::warning::search index / feeds not written ({str(err)[:200]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
