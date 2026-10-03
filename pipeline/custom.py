"""Readers' own requests, answered from SEC data in GitHub Actions (the browser cannot call SEC: no CORS, and SEC asks
for a User-Agent with a contact address).

* Compare any two periods: two quarters (or two fiscal years) of one company drawn as one comparison Sankey, the first
  period against the second. The result goes back to the reader's row in Supabase (table chart_requests) and the
  company page draws it.
* Build a company the site does not have yet (from the site's search): its default history is queued for the next
  scan (table company_requests); the scan workflow claims the requests and marks them done once the company is in.

    python -m pipeline.custom charts                         # answer waiting comparison requests
    python -m pipeline.custom claim-companies --out ciks.txt # CIKs to build in this scan (one per line)
    python -m pipeline.custom finish-companies --site _site  # mark the ones now on the site as done
    python -m pipeline.custom has-companies                  # exit 0 when a company request is waiting

Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY (secret key), SEC_USER_AGENT.
"""
import argparse
import datetime as dt
import os
import re
import sys

from . import build, dims, facts, sec
from .notify import Supa, setting

MAX_CHARTS_PER_RUN = 40
MAX_COMPANIES_PER_SCAN = 25      # readers' new companies per scan, all readers together; the rest wait for the next scan
STALE_MINUTES = 20


# ------------------------------------------------------------------ one period of one company
def _filings(cik, sub):
    """All 10-Q/10-K rows the company has filed: the recent list, then the older pages SEC splits off."""
    rows = [r for r in build.recent_rows(sub)]
    yield from rows
    for f in (sub.get("filings", {}).get("files") or [])[:4]:
        try:
            older = sec.get_json(f"https://data.sec.gov/submissions/{f['name']}")
        except Exception:
            return
        keys = list(older.keys())
        n = len(older.get("accessionNumber", []))
        for i in range(n):
            yield {k: older[k][i] for k in keys}


def find_filing(cik, sub, end, kind):
    """The 10-Q (or 10-K) that reported the period ending `end`."""
    want = ("10-K",) if kind == "fy" else ("10-Q", "10-K")
    for r in _filings(cik, sub):
        if r.get("reportDate") == end and r.get("form") in want:
            return r
    return None


def _breakdown(cik, accn, end, kind):
    """Revenue lines (axis -> member -> (label, value)) from the filing's own XBRL instance, or None."""
    try:
        inst, lab = dims.find_files(cik, accn)
        if not inst:
            return None
        labels = dims.parse_labels(sec.get(lab)) if lab else {}
        dfx = dims.parse_instance(sec.get(inst), labels)
        return dfx
    except Exception as e:
        print(f"  breakdown skipped for {cik} {accn}: {e}", file=sys.stderr)
        return None


def period(cik, fx, sub, profile, end, kind):
    """Figures for one quarter (kind 'q') or fiscal year ('fy') in the store's quarter format."""
    annual = kind == "fy"
    raw = facts.extract(fx, end, annual=annual)
    if not raw or not raw.get("revenue") or (raw.get("ni") is None and raw.get("pl") is None):
        raise ValueError(f"SEC has no {'full-year' if annual else 'quarterly'} revenue and net income for {end}")
    fye = profile.get("fye") or "1231"
    label = facts.fiscal_year_label(end, fye)[0] if annual else facts.fiscal_label(end, fye)[0]
    row = find_filing(cik, sub, end, kind)
    out = {"end": end, "label": label, "raw": raw, "form": (row or {}).get("form") or ("10-K" if annual else "10-Q"),
           "filed": (row or {}).get("filingDate"), "accn": (row or {}).get("accessionNumber"), "cal": facts.calendar_quarter(end)}
    if row:
        out["doc_url"] = sec.doc_url(cik, row["accessionNumber"], row["primaryDocument"]) if row.get("primaryDocument") else None
        out["index_url"] = sec.filing_base(cik, row["accessionNumber"]) + f"/{row['accessionNumber']}-index.htm"
    return out


def _member_values(dfx, end, kind):
    return dims.year_values(dfx, end) if kind == "fy" else dims.member_values(dfx, end)


def _capex_src(fx, raw, end, kind):
    concept = facts.source(fx, "capex", end, annual=kind == "fy") if raw.get("capex") is not None else None
    return {"concept": "us-gaap:" + concept, "label": (fx.get("__labels__") or {}).get(concept), "how": "xbrl"} \
        if concept else None


# ------------------------------------------------------------------ the comparison chart
def comparison(cik, kind, a_end, b_end):
    """Chart payload of period A with its comparison view set to period B (same shape as a quarter on the site)."""
    if kind not in ("q", "fy"):
        raise ValueError("kind must be q or fy")
    if a_end == b_end:
        raise ValueError("pick two different periods")
    sub = build.submissions(cik)
    profile = build.profile_of(sub)
    fx = build.companyfacts(cik)
    A = period(cik, fx, sub, profile, a_end, kind)
    B = period(cik, fx, sub, profile, b_end, kind)

    ls = lines_a = lines_b = None                       # revenue lines, when both filings break revenue down the same way
    if A.get("accn"):
        dfx_a = _breakdown(cik, A["accn"], a_end, kind)
        if dfx_a:
            mv = _member_values(dfx_a, a_end, kind)
            ls = dims.revenue_lines(mv, A["raw"]["revenue"])
            if ls:
                ids = [l["id"] for l in ls["leaves"]] + [g["id"] for g in ls["groups"]]
                lines_a = {m: mv[ls["axis"]][m][1] for m in ids if m in mv.get(ls["axis"], {})}
                pv = _member_values(dfx_a, b_end, kind).get(ls["axis"], {})          # B inside A's filing (a comparative)
                if not all(l["id"] in pv for l in ls["leaves"]) and B.get("accn"):
                    dfx_b = _breakdown(cik, B["accn"], b_end, kind)
                    pv = _member_values(dfx_b, b_end, kind).get(ls["axis"], {}) if dfx_b else {}
                lines_b = {m: pv[m][1] for m in ids if m in pv} or None

    c = {"profile": profile, "quarters": {a_end: {"label": A["label"]}, b_end: {"label": B["label"]}}}
    q = {"end": a_end, "label": A["label"], "cal": A["cal"], "form": A["form"], "filed": A["filed"] or "",
         "doc_url": A.get("doc_url"), "index_url": A.get("index_url"), "raw": A["raw"],
         "q1_end": b_end, "raw_q1": B["raw"], "py_end": None, "raw_py": None,
         "lines_struct": ls, "lines": lines_a, "lines_q1": lines_b, "lines_py": None, "notes": {},
         "capex_src": _capex_src(fx, A["raw"], a_end, kind)}
    pl = build.quarter_payload(c, q, None)
    if not pl:
        raise ValueError("the figures for these periods do not add up to a chart")
    pl.pop("_N", None)
    a, b = A["label"], B["label"]
    for n in pl["nodes"]:                               # "Y/Y — · Q/Q +4%" means "vs B +4%" here
        for ln in n.get("lines") or []:
            if ln[0] == "mut" and " · Q/Q " in ln[1]:
                ln[1] = f"vs {b} " + ln[1].split(" · Q/Q ", 1)[1]
        n.pop("y", None)
        n.pop("cmp_y", None)
    for l in pl["links"]:
        l.pop("y", None)
    swap = lambda t: (t.replace("the previous quarter's", f"{b}'s").replace("the previous quarter", b)
                      .replace("previous quarter", b).replace("The quarter ended", "The year ended" if kind == "fy" else "The quarter ended"))
    pl["analysis"] = [swap(x) for x in pl["analysis"]]
    if pl.get("compare"):
        pl["compare"]["bullets"] = [swap(x) for x in pl["compare"]["bullets"]]
    pl["compare_y"] = None
    pl["period"] = kind
    pl["custom"] = {"a": a_end, "b": b_end, "a_label": a, "b_label": b, "kind": kind, "b_filed": B.get("filed"),
                    "b_index_url": B.get("index_url")}
    span = "Fiscal year" if kind == "fy" else "Quarter"
    pl["subtitle"] = (f"{span} ended {build._date(a_end)} ({a}) compared with {build._date(b_end)} ({b}) · GAAP")
    pl["footer"] = [f"Source: SEC EDGAR XBRL data ({A['form']} filed {A['filed'] or 'n/a'}; {B['form']} filed {B.get('filed') or 'n/a'}). "
                    f"Drawn on request: {a} against {b}. Percentages show each item’s share of the node it splits from or flows into. "
                    "n/m = not meaningful (a comparison period was ≤ 0 or changed sign)."]
    if kind == "q":
        pl["footer"].append("Fourth quarters and cash flows are derived as year-to-date minus the prior year-to-date. "
                            "Working capital &amp; other is the residual between operating cash flow and the listed items.")
    pl["x_thread"] = []
    return pl


# ------------------------------------------------------------------ the queues in Supabase
def _now():
    return dt.datetime.now(dt.timezone.utc)


def claim(supa, table, now, done_status="working"):
    stamp = now.isoformat()
    got = supa.update(table, {"status": "eq.pending"}, {"status": done_status, "claimed_at": stamp})
    stale = (now - dt.timedelta(minutes=STALE_MINUTES)).isoformat()
    got += supa.update(table, {"status": f"eq.{done_status}", "claimed_at": f"lt.{stale}"}, {"claimed_at": stamp})
    return sorted(got, key=lambda r: (r.get("created_at") or "", r["id"]))


def process_charts(supa, now=None, limit=MAX_CHARTS_PER_RUN):
    """Draw the comparisons readers asked for; returns how many were answered."""
    rows = claim(supa, "chart_requests", now or _now())[:limit]
    done = 0
    for r in rows:
        try:
            pl = comparison(int(r["cik"]), r.get("kind") or "q", str(r["a_end"])[:10], str(r["b_end"])[:10])
            supa.update("chart_requests", {"id": f"eq.{r['id']}"},
                        {"status": "done", "result": pl, "error": None, "done_at": _now().isoformat()})
            done += 1
            print(f"drew {r['cik']} {r['a_end']} vs {r['b_end']} ({r.get('kind') or 'q'})")
        except SystemExit:                               # SEC refused us (User-Agent): try again next run
            supa.update("chart_requests", {"id": f"eq.{r['id']}"}, {"status": "pending", "claimed_at": None})
            raise
        except Exception as e:
            msg = str(e)[:300] or e.__class__.__name__
            supa.update("chart_requests", {"id": f"eq.{r['id']}"}, {"status": "failed", "error": msg, "done_at": _now().isoformat()})
            print(f"::warning::comparison {r['cik']} {r['a_end']} vs {r['b_end']} failed: {msg}")
    return done


def claim_companies(supa, now=None, limit=MAX_COMPANIES_PER_SCAN):
    """Companies to build in this scan: ones a stopped scan left behind, then the oldest requests, at most `limit`
    companies in all (however many readers ask, one scan never takes on more)."""
    now = now or _now()
    stamp = now.isoformat()
    stale = (now - dt.timedelta(minutes=STALE_MINUTES)).isoformat()
    again = supa.update("company_requests", {"status": "eq.queued", "claimed_at": f"lt.{stale}"}, {"claimed_at": stamp})
    ciks = {int(r["cik"]) for r in again}
    waiting = supa.select("company_requests", {"select": "id,cik,created_at", "status": "eq.pending", "order": "created_at.asc"})
    take = []
    for r in sorted(waiting, key=lambda r: (r.get("created_at") or "", r["id"])):
        c = int(r["cik"])
        if c in ciks or len(ciks) < limit:
            ciks.add(c)
            take.append(r["id"])
    if take:
        supa.update("company_requests", {"id": f"in.({','.join(map(str, take))})", "status": "eq.pending"},
                    {"status": "queued", "claimed_at": stamp})
    if len(waiting) > len(take):
        print(f"{len(waiting) - len(take)} company requests wait for the next scan (at most {limit} companies per scan)")
    return sorted(ciks)


def finish_companies(supa, site):
    """Requests for companies that are on the site now are done; the rest stay queued for the next scan."""
    rows = supa.select("company_requests", {"select": "id,cik,created_at", "status": "eq.queued"})
    ok = [r["id"] for r in rows if os.path.exists(os.path.join(site, "data", "c", f"{int(r['cik'])}.json"))]
    if ok:
        supa.update("company_requests", {"id": f"in.({','.join(map(str, ok))})"},
                    {"status": "done", "done_at": _now().isoformat()})
    old = [r["id"] for r in rows if r["id"] not in ok and r.get("created_at")
           and dt.datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")) < _now() - dt.timedelta(hours=6)]
    if old:                                                     # no 10-Q/10-K with figures to draw, after several scans
        supa.update("company_requests", {"id": f"in.({','.join(map(str, old))})"},
                    {"status": "failed", "error": "no 10-Q or 10-K with revenue and net income in SEC's XBRL data",
                     "done_at": _now().isoformat()})
    print(f"company requests: {len(ok)} done, {len(old)} given up, {len(rows) - len(ok) - len(old)} still building")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["charts", "claim-companies", "finish-companies", "has-companies"])
    ap.add_argument("--out", default="build-ciks.txt")
    ap.add_argument("--site", default="_site")
    args = ap.parse_args()
    url, key = setting("SUPABASE_URL", url=True), setting("SUPABASE_SERVICE_KEY")
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set: reader requests are off.")
        if args.cmd == "claim-companies":
            open(args.out, "w").close()
        sys.exit(1 if args.cmd == "has-companies" else 0)
    supa = Supa(url, key)
    if args.cmd == "charts" and "@" not in os.environ.get("SEC_USER_AGENT", "") and not os.environ.get("SEC_FIXTURES"):
        print("::warning::SEC_USER_AGENT is not set for this workflow: comparisons wait until it is.")
        sys.exit(0)
    try:
        if args.cmd == "charts":
            process_charts(supa)
        elif args.cmd == "claim-companies":
            ciks = claim_companies(supa)
            open(args.out, "w").write("".join(f"{c}\n" for c in ciks))
            print(f"{len(ciks)} companies to build: {', '.join(map(str, ciks)) or 'none'}")
        elif args.cmd == "finish-companies":
            finish_companies(supa, args.site)
        else:
            n = len(supa.select("company_requests", {"select": "id", "status": "eq.pending"}))
            print(f"{n} company requests waiting")
            sys.exit(0 if n else 1)
    except RuntimeError as e:                      # a missing table (schema.sql not run again yet) must not break the run
        print(f"::warning::reader requests skipped: {e}")
        if args.cmd == "claim-companies":
            open(args.out, "w").close()
        sys.exit(1 if args.cmd == "has-companies" else 0)


if __name__ == "__main__":
    main()
