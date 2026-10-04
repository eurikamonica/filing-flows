"""Orchestrates a run: scan EDGAR, process new filings into the store, then render the website data.

    python -m pipeline.build run    --store store --out site/data [--backfill-days N] [--max-filings N]
    python -m pipeline.build render --store store --out site/data
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import traceback

from . import analysis, dims, facts, release, scan, sec, sectors, social, sources, text
from .model import normalize
from .sankey import NOTE_KEYS, Fmt, build as build_spec

KEEP_QUARTERS = 7          # per company: the last five 10-Q quarters and the fourth quarters of the last two 10-Ks
KEEP_YEARS = 2             # full-year charts from the last two 10-Ks
KEEP_STARRED = 8           # multi-quarter history for starred companies
KEEP_STARRED_YEARS = 3
HISTORY_Q, HISTORY_K = 5, 2  # filings fetched when a company first appears: its last five 10-Qs and two 10-Ks
HISTORY_VERSION = 2          # bump to fetch the default history again for every company
BACKFILL_PER_RUN = 25        # companies stored before HISTORY_VERSION get their history a few at a time
PERIODS_Q, PERIODS_FY = 72, 18   # "compare any two periods" offers up to 18 years (XBRL starts in 2009-2011)
PERIODS_PER_RUN = 150        # companies stored before that list existed get it a few at a time (one SEC request each)
PENDING_HOURS = 24         # companyfacts can lag a filing by hours: keep trying this long (however often the scan runs)


# ---------------------------------------------------------------- store helpers
def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


class Store:
    def __init__(self, root):
        self.root = root
        self.state = load(os.path.join(root, "state.json"), {"seen": {}, "pending": {}, "log": []})

    def cpath(self, cik):
        return os.path.join(self.root, "companies", f"{int(cik)}.json")

    def company(self, cik):
        return load(self.cpath(cik), {"quarters": {}, "dims_ytd": {}})

    def put(self, cik, c):
        save(self.cpath(cik), c)

    def ciks(self):
        d = os.path.join(self.root, "companies")
        return [int(n[:-5]) for n in os.listdir(d) if n.endswith(".json")] if os.path.isdir(d) else []

    def commit(self):
        seen = self.state["seen"]
        if len(seen) > 60000:                                   # keep the newest accession numbers
            self.state["seen"] = dict(sorted(seen.items(), key=lambda kv: kv[1].get("t", ""))[-40000:])
        self.state["log"] = self.state["log"][-200:]
        save(os.path.join(self.root, "state.json"), self.state)


# ---------------------------------------------------------------- per-run caches
_sub, _cf = {}, {}


def submissions(cik):
    if cik not in _sub:
        _sub[cik] = sec.get_json(sec.submissions_url(cik))
    return _sub[cik]


def companyfacts(cik):
    if cik not in _cf:
        _cf[cik] = facts.index_facts(sec.get_json(sec.companyfacts_url(cik)))
    return _cf[cik]


INTRO_RANK = {"10-K": 3, "8-K": 2, "10-Q": 1}    # where the company description comes from, best first


def intro_rank(c):
    it = c.get("intro")
    if not it:
        return 0
    return INTRO_RANK.get(it.get("source", "10-K"), 0) if isinstance(it, dict) else INTRO_RANK["10-K"]


def set_intro(c, words, url, filed, source):
    """Keep the best description: a 10-K's Item 1 over an earnings release's "About" paragraph over a 10-Q's Note 1;
    the newer filing of the same kind wins."""
    if not words:
        return False
    old = c.get("intro") if isinstance(c.get("intro"), dict) else ({"text": c["intro"]} if c.get("intro") else {})
    rank, old_rank = INTRO_RANK[source], intro_rank(c)
    if rank > old_rank or (rank == old_rank and (filed or "") >= (old.get("filed") or "")):
        c["intro"] = {"text": words, "url": url, "filed": filed, "source": source}
        return True
    return False


def periods_of(fx):
    """Every quarter and fiscal year whose revenue SEC's XBRL data has (newest last)."""
    return {"q": facts.quarter_ends(fx)[-PERIODS_Q:], "fy": facts.year_ends(fx)[-PERIODS_FY:]}


def _needs_facts(c):
    """Stored before the period list or the per-figure sources existed."""
    return c.get("periods") is None or any(q.get("src") is None and q.get("form") != "8-K" for q in c["quarters"].values()) \
        or any(y.get("src") is None for y in (c.get("years") or {}).values())


def refresh_periods(store, limit=PERIODS_PER_RUN):
    """Companies stored before the period list or the per-figure sources existed get them from SEC's company facts
    (largest first, a few per run): which tag each stored figure was read from, with SEC's standard label."""
    todo = []
    for cik in store.ciks():
        c = store.company(cik)
        if c.get("quarters") and c.get("profile") and _needs_facts(c):
            last = max(c["quarters"].values(), key=lambda q: q.get("end") or "")
            todo.append((-((last.get("raw") or {}).get("revenue") or 0), cik))
    n = 0
    for _, cik in sorted(todo)[:limit]:
        try:
            c = store.company(cik)
            fx = companyfacts(cik)
            if c.get("periods") is None:
                c["periods"] = periods_of(fx)
            for q in c["quarters"].values():
                if q.get("src") is None and q.get("form") != "8-K":
                    q["src"] = sources.from_xbrl(fx, q["end"])
            for y in (c.get("years") or {}).values():
                if y.get("src") is None:
                    y["src"] = sources.from_xbrl(fx, y["end"], annual=True)
            store.put(cik, c)
            n += 1
        except Exception as e:
            print(f"  periods not read for {cik}: {e}", file=sys.stderr)
        finally:
            _cf.pop(cik, None)                            # big files: do not keep them all in memory
    if todo:
        print(f"period lists and sources: {n} companies updated, {max(len(todo) - n, 0)} to go")


def recent_rows(sub):
    r = sub.get("filings", {}).get("recent", {})
    keys = list(r.keys())
    n = len(r.get("accessionNumber", []))
    return [{k: r[k][i] for k in keys} for i in range(n)]


def profile_of(sub):
    sic = sub.get("sic") or ""
    return {"cik": int(sub["cik"]), "name": sub.get("name", ""), "tickers": sub.get("tickers", []),
            "exchanges": sub.get("exchanges", []), "sic": sic, "industry": sub.get("sicDescription") or "",
            "sector": sectors.sector_of(sic), "fye": sub.get("fiscalYearEnd") or "1231",
            "state": sub.get("stateOfIncorporation") or "", "category": sub.get("category") or ""}


# ---------------------------------------------------------------- one filing
class Pending(Exception):
    pass


class NotApplicable(Exception):
    """The filing has XBRL facts for the period but no revenue line (funds, shells, most banks)."""


def note_keys_for(lines_struct):
    keys = {k: v for k, v in NOTE_KEYS.items()}
    keys.update({"net sales": ["net sales", "total net sales", "revenue", "revenues"]})
    if lines_struct:
        for x in lines_struct["leaves"] + lines_struct["groups"]:
            keys[x["label"]] = [x["label"]]
    return keys


def process_filing(store, cik, accn, form, starred=False):
    if form.startswith("8-K"):
        return process_release(store, cik, accn, form, starred)
    sub = submissions(cik)
    row = next((r for r in recent_rows(sub) if r["accessionNumber"] == accn), None)
    if not row or not row.get("reportDate"):
        raise Pending("filing not yet in submissions")
    end = row["reportDate"]
    fx = companyfacts(cik)
    raw = facts.extract(fx, end)
    if not raw.get("revenue") or (raw.get("ni") is None and raw.get("pl") is None):
        if any(v is not None for v in raw.values()):
            raise NotApplicable("no revenue or net income line in XBRL")
        raise Pending("XBRL facts not available yet")
    q1_end, py_end = facts.comparison_ends(fx, end)
    comp = {"q1_end": q1_end, "py_end": py_end, "raw_q1": facts.extract(fx, q1_end), "raw_py": facts.extract(fx, py_end)}
    c = store.company(cik)
    c["profile"] = profile_of(sub)

    # revenue breakdown from the XBRL instance (dimensional facts)
    lines_struct = lines_cur = lines_py = None
    dfx = inst_text = lab_text = None
    c["periods"] = periods_of(fx)                         # for "compare any two periods"
    try:
        inst_url, lab_url = dims.find_files(cik, accn)
        if inst_url:
            lab_text = sec.get(lab_url) if lab_url else None
            labels = dims.parse_labels(lab_text) if lab_text else {}
            inst_text = sec.get(inst_url)
            dfx = dims.parse_instance(inst_text, labels)
            prev_ytd = None
            if form.startswith("10-K"):
                prev_ytd = _prior_ytd(c, sub, cik, end)
            mv = dims.member_values(dfx, end, prev_ytd)
            lines_struct = dims.revenue_lines(mv, raw["revenue"])
            if lines_struct:
                ids = [l["id"] for l in lines_struct["leaves"]] + [g["id"] for g in lines_struct["groups"]]
                axis = lines_struct["axis"]
                lines_cur = {m: mv[axis][m][1] for m in ids if m in mv.get(axis, {})}
                if py_end:
                    pv = dims.member_values(dfx, py_end).get(axis, {})
                    lines_py = {m: pv[m][1] for m in ids if m in pv} or None
            c.setdefault("dims_ytd", {})[end] = dims.ytd_values(dfx, end)
            c["dims_ytd"] = dict(sorted(c["dims_ytd"].items())[-6:])
    except (sec.NotFound, Exception) as e:                       # breakdown is optional
        print(f"  dims skipped for {cik} {accn}: {e}", file=sys.stderr)
    capex_src = src = None
    try:
        capex_src = capex_from_filing(cik, sub, fx, raw, comp, end, inst_text, lab_text)
    except Exception as e:
        print(f"  capex source skipped for {cik} {accn}: {e}", file=sys.stderr)
    try:                                                  # which line and tag every figure was read from
        src = sources.from_xbrl(fx, end, dims.label_roles(lab_text) if lab_text else None)
    except Exception as e:
        print(f"  sources skipped for {cik} {accn}: {e}", file=sys.stderr)

    # the company's own words: MD&A notes and Item 1 introduction
    notes, doc = {}, None
    doc_url = sec.doc_url(cik, accn, row["primaryDocument"]) if row.get("primaryDocument") else None
    try:
        if doc_url:
            doc = sec.get(doc_url)
            md = text.mdna(doc)
            for key, words in note_keys_for(lines_struct).items():
                m = text.match_notes(md, words, fallback=key != "net sales")
                if m:
                    notes[key] = m
    except Exception as e:
        print(f"  notes skipped for {cik} {accn}: {e}", file=sys.stderr)
    try:
        if form.startswith("10-K") and doc:
            set_intro(c, text.intro(doc), doc_url, row.get("filingDate"), "10-K")
        elif intro_rank(c) < INTRO_RANK["10-K"]:
            k = next((r for r in recent_rows(sub) if r["form"] == "10-K" and r.get("primaryDocument")), None)
            if k:
                u = sec.doc_url(cik, k["accessionNumber"], k["primaryDocument"])
                set_intro(c, text.intro(sec.get(u)), u, k.get("filingDate"), "10-K")
        if intro_rank(c) < INTRO_RANK["10-Q"] and doc and form.startswith("10-Q"):   # no 10-K yet: Note 1
            p = c["profile"]
            set_intro(c, text.note1(doc, [p["name"]], p.get("tickers")), doc_url, row.get("filingDate"), "10-Q")
    except Exception as e:
        print(f"  intro skipped for {cik}: {e}", file=sys.stderr)

    label, fq, fy = facts.fiscal_label(end, c["profile"]["fye"])
    replaced = c["quarters"].get(end) if (c["quarters"].get(end) or {}).get("form") == "8-K" else None
    if replaced:
        audit_release(store.state, cik, replaced, raw, end)
    c["quarters"][end] = {
        "end": end, "label": label, "fq": fq, "fy": fy, "cal": facts.calendar_quarter(end), "form": form,
        "accn": accn, "filed": row.get("filingDate"), "doc_url": doc_url,
        "index_url": sec.filing_base(cik, accn) + f"/{accn}-index.htm",
        "raw": raw, **comp, "lines_struct": lines_struct, "lines": lines_cur, "lines_py": lines_py, "notes": notes,
        "capex_src": capex_src, "src": src,
    }
    e0 = dt.date.fromisoformat(end)                               # the 10-Q/10-K replaces a preliminary 8-K quarter
    releases = [replaced] if replaced else []
    for k in [k for k, q in c["quarters"].items() if q.get("form") == "8-K"
              and abs((dt.date.fromisoformat(k) - e0).days) <= 10]:
        audit_release(store.state, cik, c["quarters"][k], raw, end)
        releases.append(c["quarters"][k])
        if k != end:
            del c["quarters"][k]
    if releases and form != "8-K":
        c["quarters"][end]["from_release"] = release_check(releases[0], raw)
    if form.startswith("10-K"):
        year = annual_entry(c, fx, dfx, cik, accn, form, row, end, doc_url, notes, inst_text, lab_text)
        if year:
            c.setdefault("years", {})[end] = year
            c["years"] = dict(sorted(c["years"].items())[-(KEEP_STARRED_YEARS if starred else KEEP_YEARS):])
    keep = max(KEEP_STARRED if starred else KEEP_QUARTERS, c.get("keep", 0))
    c["quarters"] = dict(sorted(c["quarters"].items())[-keep:])
    store.put(cik, c)
    return end


def annual_entry(c, fx, dfx, cik, accn, form, row, end, doc_url, notes, inst_text=None, lab_text=None):
    """The full fiscal year of a 10-K, with the year before for comparison."""
    raw = facts.extract(fx, end, annual=True)
    if not raw.get("revenue") or (raw.get("ni") is None and raw.get("pl") is None):
        return None
    py_end = facts.prior_year_end(fx, end)
    comp = {"py_end": py_end, "raw_py": facts.extract(fx, py_end, annual=True) if py_end else None}
    try:
        src = sources.from_xbrl(fx, end, dims.label_roles(lab_text) if lab_text else None, annual=True)
    except Exception as e:
        print(f"  annual sources skipped for {cik} {accn}: {e}", file=sys.stderr)
        src = None
    try:
        capex_src = capex_from_filing(cik, None, fx, raw, comp, end, inst_text, lab_text, annual=True)
    except Exception as e:
        print(f"  annual capex source skipped for {cik} {accn}: {e}", file=sys.stderr)
        capex_src = None
    ls = cur = prev = None
    if dfx:
        try:
            yv = dims.year_values(dfx, end)
            ls = dims.revenue_lines(yv, raw["revenue"])
            if ls:
                ids = [l["id"] for l in ls["leaves"]] + [g["id"] for g in ls["groups"]]
                axis = ls["axis"]
                cur = {m: yv[axis][m][1] for m in ids if m in yv.get(axis, {})}
                if py_end:
                    pv = dims.year_values(dfx, py_end).get(axis, {})
                    prev = {m: pv[m][1] for m in ids if m in pv} or None
        except Exception as e:
            print(f"  annual breakdown skipped for {cik} {accn}: {e}", file=sys.stderr)
            ls = cur = prev = None
    label, fy = facts.fiscal_year_label(end, c["profile"]["fye"])
    return {"end": end, "label": label, "fy": fy, "form": form, "accn": accn, "filed": row.get("filingDate"),
            "doc_url": doc_url, "index_url": sec.filing_base(cik, accn) + f"/{accn}-index.htm", "period": "fy",
            "raw": raw, "py_end": py_end, "raw_py": comp["raw_py"], "capex_src": capex_src, "src": src,
            "lines_struct": ls, "lines": cur, "lines_py": prev, "notes": notes}


def capex_from_filing(cik, sub, fx, raw, comp, end, inst_text, lab_text, annual=False):
    """Where this period's capital expenditures come from: SEC's standard tags (companyfacts) when the company used
    one; else the filing's own XBRL, where the line is found by its printed name ("Purchases of property and
    equipment", "Capital expenditures" ...), company-specific tags included. The fallback fills raw / comp in place.
    Returns {"concept", "label", "how": "xbrl" | "instance"} or None."""
    roles = dims.label_roles(lab_text) if lab_text else {}
    concept = facts.source(fx, "capex", end, annual=annual)
    if raw.get("capex") is not None and concept:
        label = dims.statement_label(roles.get("us-gaap_" + concept)) or (fx.get("__labels__") or {}).get(concept)
        return {"concept": "us-gaap:" + concept, "label": label, "how": "xbrl"}
    if not inst_text or not roles:
        return None
    found = dims.capex_lines(inst_text, roles)
    if not found:
        return None
    mine, prev = found["facts"], None

    def with_prev():                     # cash flow is year-to-date: a quarter needs the filing before's year-to-date
        nonlocal prev
        if prev is None:
            prev = _previous_concept_facts(cik, sub, end, found["concept"]) if sub else []
        return mine + prev
    v = dims.period_value(mine, end, annual)
    if v is None and not annual:
        v = dims.period_value(with_prev(), end)
    if v is None:
        return None
    raw["capex"] = v
    if comp.get("raw_py") and comp.get("py_end"):
        pv = dims.period_value(mine, comp["py_end"], annual)
        if pv is None and not annual:
            pv = dims.period_value(with_prev(), comp["py_end"])
        if pv is not None:
            comp["raw_py"] = dict(comp["raw_py"], capex=pv)
    if not annual and comp.get("raw_q1") and comp.get("q1_end"):
        qv = dims.period_value(mine + (prev or []), comp["q1_end"])
        if qv is not None:
            comp["raw_q1"] = dict(comp["raw_q1"], capex=qv)
    return {"concept": found["concept"], "label": found["label"], "how": "instance"}


def _previous_concept_facts(cik, sub, end, concept):
    """The same XBRL line in the 10-Q/10-K for the period about a quarter before `end` (its year-to-date figures)."""
    e0 = dt.date.fromisoformat(end)
    for r in recent_rows(sub):
        if r["form"] in ("10-Q", "10-K") and r.get("reportDate") and \
                75 <= (e0 - dt.date.fromisoformat(r["reportDate"])).days <= 105:
            inst, _ = dims.find_files(cik, r["accessionNumber"])
            return dims.concept_facts(sec.get(inst), concept) if inst else []
    return []


FCF_NOTE = ("Free cash flow = operating cash flow minus capital expenditures. Proceeds from selling assets and "
            "finance-lease repayments are not netted, so it can differ from a free cash flow figure the company "
            "reports itself.")


def capex_note(src):
    """Where the capital-expenditure figure came from, for the node's note on the site."""
    if not src or not src.get("label"):
        return None
    lab = src["label"] if " " in src["label"] else dims.humanize(src["label"])     # a bare tag name: spaced out
    lab = lab[:1].upper() + lab[1:]
    if src.get("how") == "release":
        return f"Capital expenditures as printed in the earnings release’s cash-flow table: “{lab}”."
    tag = src.get("concept") or ""
    own = "" if tag.startswith("us-gaap:") else ", the company’s own XBRL tag"
    where = "SEC’s XBRL company facts" if src.get("how") == "xbrl" else "the filing’s own XBRL data"
    return f"Capital expenditures = the cash-flow line “{lab}” ({tag}{own}), from {where}."





EXHIBIT_PATTERNS = (r"ex[-_]?99[-_.]?0?1(?!\d)", r"ex[-_]?99", r"press|release|earnings")


def _exhibit(cik, accn, primary):
    """File name of the press release (Exhibit 99.1) inside an 8-K filing."""
    idx = sec.get_json(sec.filing_index_url(cik, accn))
    names = [i["name"] for i in idx.get("directory", {}).get("item", []) if re.search(r"\.html?$", i["name"], re.I)]
    for pat in EXHIBIT_PATTERNS:
        hits = [n for n in names if re.search(pat, n, re.I)]
        if hits:
            return hits[0]
    rest = [n for n in names if n != primary and "index" not in n.lower()]
    return rest[0] if rest else primary


def _release_quarter(vals, quarterly, fx, q1_end, keys):
    """Release values -> quarter values (cash flow tables are usually year-to-date)."""
    out = {}
    for k in keys:
        v = vals.get(k)
        if v is None:
            continue
        if k in release.COST_KEYS:
            v = abs(v)
        if quarterly:
            out[k] = v
        else:
            prev = facts.ytd_value(fx, k, q1_end) if q1_end else None
            if prev is not None:
                out[k] = v - (abs(prev) if k in release.COST_KEYS else prev)
    return out


AUDIT_KEYS = ("revenue", "oi", "ni", "ocf")


def audit_release(st, cik, old, raw, end):
    """When the 10-Q/10-K arrives, record how the figures read from the earnings release compare with it."""
    fields, ok = {}, True
    for k in AUDIT_KEYS:
        a, b = (old.get("raw") or {}).get(k), raw.get(k)
        if a is None or b is None:
            continue
        good = abs(a - b) <= 0.005 * abs(b) + 1e3
        fields[k] = [a, b, good]
        ok = ok and good
    if fields:
        st.setdefault("audit", []).append({"cik": cik, "end": end, "accn": old.get("accn"), "ok": ok, "fields": fields,
                                           "t": dt.datetime.utcnow().isoformat(timespec="seconds")})
        st["audit"] = st["audit"][-500:]


AUDIT_NAMES = {"revenue": "Revenue", "oi": "Operating profit", "ni": "Net earnings", "ocf": "Operating cash flow"}


def release_check(old, raw):
    """How the figures drawn from the earnings release (8-K) compare with the 10-Q/10-K that replaces them."""
    fields = []
    for k in AUDIT_KEYS:
        a, b = (old.get("raw") or {}).get(k), raw.get(k)
        if a is None or b is None:
            continue
        fields.append({"key": k, "name": AUDIT_NAMES[k], "release": a, "final": b,
                       "ok": abs(a - b) <= 0.005 * abs(b) + 1e3})
    return {"filed": old.get("filed"), "accn": old.get("accn"), "fields": fields, "ok": all(f["ok"] for f in fields)}


HISTORY_ON_RELEASE = 5          # an earnings 8-K brings in the company's last five 10-Q/10-K filings


def _queue_history(store, cik, sub, n=HISTORY_ON_RELEASE):
    st, c = store.state, store.company(cik)
    if c.get("keep", 0) >= n + 1 and c.get("hist", 0) >= HISTORY_VERSION:
        return
    have = c.get("quarters", {})
    years = c.get("years", {})
    rows = [r for r in recent_rows(sub) if r.get("reportDate")]
    pick = [r for r in rows if r["form"] == "10-Q"][:HISTORY_Q] + [r for r in rows if r["form"] == "10-K"][:HISTORY_K]
    for r in pick:
        a = r["accessionNumber"]
        done = r["reportDate"] in have and (r["form"] != "10-K" or r["reportDate"] in years)
        if not done and a not in st["pending"]:
            st["seen"].pop(a, None)                          # a 10-K read before annual charts existed is read again
            st["pending"][a] = {"cik": cik, "form": r["form"], "filed": r["filingDate"], "tries": 0, "items": None,
                                "history": True}
    c["keep"] = max(c.get("keep", 0), n + 1, KEEP_QUARTERS)
    c["hist"] = HISTORY_VERSION
    c["profile"] = profile_of(sub)
    store.put(cik, c)


def queue_history(store, cik):
    """Default history (last five 10-Qs and two 10-Ks) for one company; returns False when SEC has no such filer."""
    try:
        _queue_history(store, cik, submissions(cik))
        return True
    except sec.NotFound:
        return False


def backfill_history(store, limit=BACKFILL_PER_RUN):
    """Companies stored before the current default history get it, a few per run."""
    n = 0
    for cik in sorted(store.ciks()):
        if n >= limit:
            break
        c = store.company(cik)
        if c.get("hist", 0) >= HISTORY_VERSION or not c.get("profile"):
            continue
        try:
            queue_history(store, cik)
        except Exception as e:
            print(f"  history not queued for {cik}: {e}", file=sys.stderr)
        n += 1
    if n:
        print(f"queued the default history for {n} more companies")


def _release_cash(rel, fx, q1_end, fq, py_end=None):
    """Cash-flow tables are quarterly or year-to-date. First anchor the table: its earlier column equals either the
    year-ago year-to-date or a filed quarter in XBRL. Otherwise take the reading whose D&A (or share-based pay) is
    closest to the previous quarter's; if neither is plausible, leave the cash bridge out rather than draw it wrong."""
    if not rel["cf"]:
        return {}
    direct = _release_quarter(rel["cf"], True, fx, q1_end, release.CF_KEYS)
    ytd = direct if fq == 1 else _release_quarter(rel["cf"], False, fx, q1_end, release.CF_KEYS)
    ocf_cols = (rel.get("cf_cols") or {}).get("ocf") or []
    if fq != 1 and py_end and len(ocf_cols) > 1:
        ytd_ref = facts.ytd_value(fx, "ocf", py_end)
        q_refs = [facts.value(fx, "ocf", e) for e in (q1_end, py_end) if e]
        for v in ocf_cols[1:]:
            if release.close(v, ytd_ref, rel["scale"]):
                return ytd
            if any(release.close(v, r, rel["scale"]) for r in q_refs):
                return direct
    hint = direct if rel["cf_quarter"] is True or fq == 1 else ytd
    for key in ("da", "sbc"):
        ref = facts.value(fx, key, q1_end) if q1_end else None
        if ref and ref > 0 and (direct.get(key) or ytd.get(key)):
            dist = lambda c: abs(math.log(c[key] / ref)) if c.get(key) and c[key] > 0 else math.inf
            pick = min((hint, direct, ytd), key=dist)                 # the hint wins ties
            return pick if dist(pick) <= math.log(2.5) else {}
    return hint


def process_release(store, cik, accn, form, starred=False):
    """A preliminary quarter from an earnings release (8-K Item 2.02); the 10-Q/10-K replaces it when filed."""
    sub = submissions(cik)
    row = next((r for r in recent_rows(sub) if r["accessionNumber"] == accn), None)
    if not row:
        raise Pending("filing not yet in submissions")
    if "2.02" not in (row.get("items") or ""):
        raise NotApplicable("8-K without Item 2.02 (not an earnings release)")
    _queue_history(store, cik, sub)                   # earlier 10-Q/10-K filings, for history and comparisons
    fx = companyfacts(cik)
    ends = facts.period_ends(fx)
    if not ends:
        raise NotApplicable("no earlier quarters in XBRL to check the release against")
    last = dt.date.fromisoformat(ends[-1])
    prior_rev = facts.value(fx, "revenue", ends[-1])
    c = store.company(cik)
    c["profile"] = profile_of(sub)
    ex_name = _exhibit(cik, accn, row.get("primaryDocument"))
    if not ex_name:
        raise NotApplicable("no press release in the filing")
    ex_url = sec.doc_url(cik, accn, ex_name)
    doc = sec.get(ex_url)
    if intro_rank(c) < INTRO_RANK["8-K"]:                # no 10-K description yet: the release's "About" paragraph
        try:
            if set_intro(c, text.about(doc, [c["profile"]["name"]], c["profile"].get("tickers")), ex_url,
                         row.get("filingDate"), "8-K"):
                store.put(cik, c)                       # kept even if the release's tables turn out unreadable
        except Exception as e:
            print(f"  about skipped for {cik}: {e}", file=sys.stderr)
    try:
        rel = release.parse(doc, dt.date.fromisoformat(row["filingDate"]), last, prior_rev)
        end = rel["end"]
        e0 = dt.date.fromisoformat(end)
        if e0 <= last + dt.timedelta(days=10):
            raise NotApplicable(f"the release covers {end}, already filed in a 10-Q/10-K")
        if any(q.get("form") != "8-K" and abs((dt.date.fromisoformat(k) - e0).days) <= 10 for k, q in c["quarters"].items()):
            raise NotApplicable("the 10-Q/10-K for this quarter is already in")
        q1_end, py_end = facts.comparison_ends(fx, end)
        label, fq, fy = facts.fiscal_label(end, c["profile"]["fye"])
        if rel["is_quarter"] is False and fq != 1:
            raise ValueError("the income statement shows year-to-date figures first")
        release.anchor(rel, {"q1": facts.extract(fx, q1_end) if q1_end else None,
                             "py": facts.extract(fx, py_end) if py_end else None}, facts.extract(fx, ends[-1]))
        raw = {k: None for k in facts.CONCEPTS}
        raw.update(_release_quarter(rel["is"], True, fx, q1_end, release.IS_KEYS))
        raw.update(_release_cash(rel, fx, q1_end, fq, py_end))
        refs = [facts.value(fx, "tax", e) for e in (q1_end, py_end) if e]
        checked = release.calibrate_tax(raw, rel["cols"], refs)
        raw = release.reconcile(raw, rel["labels"], checked)
    except ValueError as e:
        raise NotApplicable(f"earnings release not readable: {e}")
    if not normalize(raw):
        raise NotApplicable("earnings release lacks revenue or net income")
    rev_ref = {"q1": facts.value(fx, "revenue", q1_end) if q1_end else None,
               "py": facts.value(fx, "revenue", py_end) if py_end else None}
    segs = release.revenue_lines(rel["tables"], raw["revenue"], rel["scale"], rev_ref)
    ls = segs["struct"] if segs else None
    notes = {}
    paras = release.note_paragraphs(doc)
    for key, words in note_keys_for(ls).items():
        m = text.match_notes(paras, words)
        if m:
            notes[key] = m
    c["quarters"][end] = {
        "end": end, "label": label, "fq": fq, "fy": fy, "cal": facts.calendar_quarter(end), "form": "8-K",
        "accn": accn, "filed": row.get("filingDate"), "doc_url": ex_url,
        "index_url": sec.filing_base(cik, accn) + f"/{accn}-index.htm", "raw": raw,
        "q1_end": q1_end, "py_end": py_end, "raw_q1": facts.extract(fx, q1_end), "raw_py": facts.extract(fx, py_end),
        "lines_struct": ls, "lines": segs and segs["cur"], "lines_q1": segs and segs.get("q1"),
        "lines_py": segs and segs.get("py"), "notes": notes,
        "capex_src": ({"label": (rel.get("cf_labels") or {}).get("capex"), "how": "release"}
                      if raw.get("capex") is not None else None),
        "src": sources.from_release(rel, raw),
    }
    keep = max(KEEP_STARRED if starred else KEEP_QUARTERS, c.get("keep", 0))
    c["quarters"] = dict(sorted(c["quarters"].items())[-keep:])
    store.put(cik, c)
    return end


def _prior_ytd(c, sub, cik, end):
    """Nine-month member values for a 10-K (Q4 = full year - nine months)."""
    e0 = dt.date.fromisoformat(end)
    for k, v in (c.get("dims_ytd") or {}).items():
        if 75 <= (e0 - dt.date.fromisoformat(k)).days <= 105 and v:
            return v
    for r in recent_rows(sub):
        if r["form"] == "10-Q" and r.get("reportDate") and \
                75 <= (e0 - dt.date.fromisoformat(r["reportDate"])).days <= 105:
            inst, lab = dims.find_files(cik, r["accessionNumber"])
            labels = dims.parse_labels(sec.get(lab)) if lab else {}
            return dims.ytd_values(dims.parse_instance(sec.get(inst), labels), r["reportDate"])
    return None


# ---------------------------------------------------------------- run
def starred_ciks(path="config/starred.txt"):
    try:
        tickers = [t.strip().upper() for t in open(path) if t.strip() and not t.startswith("#")]
    except FileNotFoundError:
        return {}
    if not tickers:
        return {}
    data = sec.get_json("https://www.sec.gov/files/company_tickers.json")
    m = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
    return {m[t]: t for t in tickers if t in m}


def company_ciks(tokens):
    """CIKs (digits) and tickers (MS, BRK.B) -> CIKs; unknown tickers are reported and skipped."""
    out, tickers = [], []
    for x in (t.strip() for t in tokens):
        if x.isdigit() and int(x) > 0:
            out.append(int(x))
        elif re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", x or ""):
            tickers.append(x.upper().replace(".", "-"))
    if tickers:
        try:
            data = sec.get_json("https://www.sec.gov/files/company_tickers.json")
            m = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in data.values()}
        except Exception as e:
            print(f"::warning::tickers not looked up ({e}): {', '.join(tickers)}")
            m = {}
        for t in tickers:
            if t in m:
                out.append(m[t])
            else:
                print(f"::warning::no SEC company with ticker {t}")
    return sorted(set(out))


RELEASE_READER = 3              # bump when the 8-K reader changes: stored 8-K quarters are read again once


def _reread_releases(store):
    st = store.state
    if st.get("release_reader", 1) >= RELEASE_READER:
        return
    n = 0
    for cik in store.ciks():
        c = store.company(cik)
        old = [k for k, q in c.get("quarters", {}).items() if q.get("form") == "8-K"]
        for k in old:
            q = c["quarters"].pop(k)
            st["seen"].pop(q["accn"], None)
            st["pending"][q["accn"]] = {"cik": cik, "form": "8-K", "filed": q["filed"], "tries": 0, "items": "2.02"}
            n += 1
        if old:
            store.put(cik, c)
    for accn, v in list(st["seen"].items()):                     # earlier rejections get another try too
        if str(v.get("s", "")).startswith("skip: earnings release not readable") and v.get("cik"):
            del st["seen"][accn]
            st["pending"][accn] = {"cik": v["cik"], "form": "8-K", "filed": v.get("t", "")[:10], "tries": 0, "items": "2.02"}
            n += 1
    st["release_reader"] = RELEASE_READER
    print(f"re-reading {n} earnings releases with reader v{RELEASE_READER}")


def run(args):
    store = Store(args.store)
    st = store.state
    now = dt.datetime.utcnow().isoformat(timespec="seconds")
    queue = scan.backfill(args.backfill_days) if args.backfill_days else scan.latest_filings()
    if args.backfill_days:
        queue += scan.latest_filings()
    for f in queue:
        if f["form"] == "8-K" and f.get("items") is not None and "2.02" not in f["items"]:
            continue                                             # 8-K that is not an earnings release
        if f["accn"] not in st["seen"] and f["accn"] not in st["pending"] and not f["form"].endswith("/A"):
            st["pending"][f["accn"]] = {"cik": f["cik"], "form": f["form"], "filed": f["filed"], "tries": 0,
                                        "items": f.get("items")}
    _reread_releases(store)
    asked = set(getattr(args, "build_ciks", None) or [])
    for cik in sorted(asked):                                  # companies readers asked for (site search)
        try:
            if not queue_history(store, cik):
                print(f"  no SEC filer with CIK {cik}")
        except Exception as e:
            print(f"  could not queue {cik} for a reader: {e}", file=sys.stderr)
    backfill_history(store)
    refresh_periods(store)
    stars = starred_ciks()
    for cik in stars:                                            # multi-quarter history for starred companies
        try:
            rows = [r for r in recent_rows(submissions(cik)) if r["form"] in ("10-Q", "10-K")][:KEEP_STARRED]
        except Exception:
            continue
        have = store.company(cik).get("quarters", {})
        for r in rows:
            if r.get("reportDate") and r["reportDate"] not in have and r["accessionNumber"] not in st["pending"] \
                    and r["accessionNumber"] not in st["seen"]:
                st["pending"][r["accessionNumber"]] = {"cik": cik, "form": r["form"], "filed": r["filingDate"], "tries": 0}
    done, tried = 0, set()
    while done < args.max_filings:                    # rounds: an earnings 8-K can queue the company's earlier filings
        order = [kv for kv in sorted(st["pending"].items(), key=lambda kv: kv[1]["filed"], reverse=True) if kv[0] not in tried]
        if not order:
            break
        order.sort(key=lambda kv: (kv[1]["cik"] not in asked,                              # what readers asked for first
                                   kv[1]["form"] == "8-K" and kv[1].get("items") is None))   # unclassified 8-Ks last
        for accn, p in order:
            if done >= args.max_filings:
                break
            done += 1
            tried.add(accn)
            _process_one(store, st, accn, p, stars, now)
            if done % 25 == 0:
                store.commit()
    st["log"].append({"t": now, "processed": done, "pending": len(st["pending"])})
    store.commit()
    render(store, args.out, set(stars))
    company_list(args.out)


def company_list(out):
    """data/companies.json: every company with a ticker on SEC's list [cik, ticker, name], so the site's search finds
    companies it has no chart for yet (a reader can then ask for them)."""
    try:
        data = sec.get_json("https://www.sec.gov/files/company_tickers.json")
    except Exception as e:
        print(f"::warning::SEC company list not fetched ({e}); the search shows only companies on the site")
        return
    seen, rows = set(), []
    for v in data.values():                               # SEC lists the largest companies first: kept, for the search
        cik = int(v["cik_str"])
        if cik in seen:                                   # one row per company: its first (main) ticker
            continue
        seen.add(cik)
        rows.append([cik, str(v.get("ticker") or "").upper(), str(v.get("title") or "")])
    with open(os.path.join(out, "companies.json"), "w") as f:
        json.dump({"generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "companies": rows}, f,
                  separators=(",", ":"))
    print(f"company list: {len(rows)} SEC companies")


def _process_one(store, st, accn, p, stars, now):
    """Process one pending filing and record the outcome in the state."""
    try:
        end = process_filing(store, p["cik"], accn, p["form"], starred=p["cik"] in stars)
        st["seen"][accn] = {"t": now, "s": "ok", "cik": p["cik"], "end": end, "form": p["form"], "filed": p["filed"]}
        del st["pending"][accn]
        print(f"ok   {p['form']:5} {p['cik']:>10} {accn} {end}")
        if store.company(p["cik"]).get("hist", 0) < HISTORY_VERSION:   # a new company: its earlier filings too
            try:
                queue_history(store, p["cik"])
            except Exception as e:
                print(f"  history not queued for {p['cik']}: {e}", file=sys.stderr)
    except Pending as e:
        p["tries"] += 1
        since = p.setdefault("since", now)
        waited = (dt.datetime.fromisoformat(now) - dt.datetime.fromisoformat(since)).total_seconds() / 3600
        if waited >= PENDING_HOURS and p["tries"] >= 3:
            st["seen"][accn] = {"t": now, "s": f"skip: {e}", "cik": p["cik"]}
            del st["pending"][accn]
        print(f"wait {p['form']:5} {p['cik']:>10} {accn} {e}")
    except NotApplicable as e:
        st["seen"][accn] = {"t": now, "s": f"skip: {e}", "cik": p["cik"]}
        del st["pending"][accn]
        print(f"skip {p['form']:5} {p['cik']:>10} {accn} {e}")
    except sec.NotFound as e:
        st["seen"][accn] = {"t": now, "s": f"missing: {e}", "cik": p["cik"]}
        del st["pending"][accn]
    except Exception as e:
        traceback.print_exc()
        st["seen"][accn] = {"t": now, "s": f"error: {e}"[:200], "cik": p["cik"]}
        del st["pending"][accn]




# ---------------------------------------------------------------- render website data
SOURCE_NOTE = ("Source: SEC EDGAR XBRL data ({form} filed {filed}). Percentages show each item’s share of the node "
               "it splits from or flows into. n/m = not meaningful (a comparison period was ≤ 0 or changed sign).")


RELEASE_NOTE = ("Source: earnings release (8-K Exhibit 99.1, filed {filed}), read from its tables; earlier quarters from SEC EDGAR "
                "XBRL data. Preliminary: replaced by the 10-Q/10-K when it is filed. Percentages show each item’s share of the node "
                "it splits from or flows into. n/m = not meaningful (a comparison period was ≤ 0 or changed sign).")


def _footer(q, kind, Nc):
    lines = [(RELEASE_NOTE if q["form"] == "8-K" else SOURCE_NOTE).format(form=q["form"], filed=q["filed"])]
    if "oi_derived" in Nc["flags"]:
        lines.append("Operating profit = revenue minus total costs and expenses (derived; the company does not tag operating income).")
    if kind == "loss":
        lines.append("Loss-making quarter: revenue, other income and the net loss together fund all costs; "
                     "the cash bridge starts from non-cash charges.")
    lines.append("Quarterly figures for 10-K periods and all cash flows are derived as year-to-date minus the prior year-to-date. "
                 "Working capital &amp; other is the residual between operating cash flow and the listed items."
                 + (" FCF = operating cash flow minus capital expenditures." if Nc.get("capex") else ""))
    return lines


def quarter_payload(c, q, prev_q):
    Nc, Nq, Ny = normalize(q["raw"]), normalize(q.get("raw_q1")), normalize(q.get("raw_py"))
    if not Nc:
        return None
    ls = q.get("lines_struct")
    lines_q1 = q.get("lines_q1") or (prev_q.get("lines") if prev_q and prev_q.get("end") == q.get("q1_end") else None)
    if lines_q1 and ls and not all(l["id"] in lines_q1 for l in ls["leaves"]):
        lines_q1 = None
    try:
        nodes, links, kind = build_spec(Nc, Nq, Ny, ls, (q.get("lines"), lines_q1, q.get("lines_py")))
    except Exception as e:                                      # a breakdown that does not reconcile: drop it
        print(f"  spec without breakdown for {c['profile']['name']}: {e}", file=sys.stderr)
        ls = None
        nodes, links, kind = build_spec(Nc, Nq, Ny)
    by_words = {tuple(v): k for k, v in NOTE_KEYS.items()}          # nodes carry search phrases; notes are keyed by name
    notes = q.get("notes", {})
    for n in nodes:
        nk = n.pop("notekeys")
        for k in list(nk) + [by_words.get(tuple(nk))]:
            if k and k in notes:
                n["notes"] = notes[k]
                break
    sources.attach(nodes, q.get("src"), Nc, ls, "q", q.get("capex_src"))
    f = Fmt(Nc["R"])
    labels = {e: x["label"] for e, x in c["quarters"].items()}
    py_label = labels.get(q.get("py_end")) or "a year earlier"
    p = c["profile"]
    name = p["name"]
    q1_label = labels.get(q.get("q1_end")) or (facts.fiscal_label(q["q1_end"], p.get("fye") or "1231")[0]
                                               if q.get("q1_end") else None)
    compare = compare_y = None
    if Nq and q1_label:
        compare = {"vs": q1_label, "title": f"{name} {q['label']} vs {q1_label}: what changed",
                   "bullets": analysis.compare_bullets(f, q1_label, Nc, Nq, ls, (q.get("lines"), lines_q1, None))}
    py_name = labels.get(q.get("py_end")) or (facts.fiscal_label(q["py_end"], p.get("fye") or "1231")[0]
                                              if q.get("py_end") else None)
    if Ny and py_name:
        compare_y = {"vs": py_name, "title": f"{name} {q['label']} vs {py_name}: what changed",
                     "bullets": analysis.compare_bullets(f, py_name, Nc, Ny, ls, (q.get("lines"), q.get("lines_py"), None))}
    return {
        "cite": sources.citation(name, q),
        "compare": compare, "compare_y": compare_y, "preliminary": q["form"] == "8-K",
        "release_check": q.get("from_release"),
        "end": q["end"], "label": q["label"], "cal": q["cal"], "form": q["form"], "filed": q["filed"],
        "doc_url": q.get("doc_url"), "index_url": q.get("index_url"), "kind": kind,
        "title": f"{name} {q['label']} earnings &amp; cash flow",
        "subtitle": (f"Quarter ended {_date(q['end'])} · GAAP · Y/Y vs. {_short(q.get('py_end'))} "
                     f"· Q/Q vs. {_short(q.get('q1_end'))}" + (" · preliminary, from the earnings release" if q["form"] == "8-K" else "")),
        "footer": _footer(q, kind, Nc), "nodes": nodes, "links": links,
        "analysis": analysis.paragraphs(f, q["label"], Nc, Nq, Ny, ls, (q.get("lines"), lines_q1, q.get("lines_py")),
                                        py_label=py_label),
        "headline": {"revenue": Nc["R"], "rev_fmt": f.money(Nc["R"]), "yoy": _g(Nc["R"], Ny and Ny["R"]),
                     "ni": Nc["pl"], "ni_fmt": f.money(Nc["pl"]), "om": Nc["oi"] / Nc["R"] * 100,
                     "oi": Nc["oi"], "ocf": Nc.get("ocf")},
        "_N": (Nc, Nq, Ny),
    }


ANNUAL_NOTE = ("Source: SEC EDGAR XBRL data ({form} filed {filed}): the full fiscal year as reported. Percentages show each "
               "item’s share of the node it splits from or flows into. n/m = not meaningful (a comparison period was ≤ 0 or changed sign).")


def _yearly(text):
    """Analysis written for quarters, reworded for a full year."""
    for a, b in (("The quarter ended", "The year ended"), ("previous quarter's", "previous year's"),
                 ("the previous quarter", "the previous year"), ("Loss-making quarter", "Loss-making year")):
        text = text.replace(a, b)
    return text


def year_payload(c, y):
    """A full fiscal year (10-K) in the same format; Y/Y against the year before."""
    Nc, Ny = normalize(y["raw"]), normalize(y.get("raw_py"))
    if not Nc:
        return None
    ls = y.get("lines_struct")
    try:
        nodes, links, kind = build_spec(Nc, None, Ny, ls, (y.get("lines"), None, y.get("lines_py")))
    except Exception as e:
        print(f"  annual spec without breakdown for {c['profile']['name']}: {e}", file=sys.stderr)
        ls = None
        nodes, links, kind = build_spec(Nc, None, Ny)
    notes = y.get("notes", {})
    by_words = {tuple(v): k for k, v in NOTE_KEYS.items()}
    for n in nodes:
        nk = n.pop("notekeys")
        for k in list(nk) + [by_words.get(tuple(nk))]:
            if k and k in notes:
                n["notes"] = notes[k]
                break
        for ln in n.get("lines") or []:                       # a year has no "previous quarter"
            if ln[0] == "mut" and ln[1].startswith("Y/Y "):
                ln[1] = ln[1].split(" · Q/Q ")[0]
        n.pop("q", None)
        n.pop("cmp", None)
    sources.attach(nodes, y.get("src"), Nc, ls, "fy", y.get("capex_src"))
    for l in links:
        l.pop("q", None)
    f = Fmt(Nc["R"])
    p = c["profile"]
    name = p["name"]
    py_label = facts.fiscal_year_label(y["py_end"], p.get("fye") or "1231")[0] if y.get("py_end") else None
    compare_y = None
    if Ny and py_label:
        compare_y = {"vs": py_label, "title": f"{name} {y['label']} vs {py_label}: what changed",
                     "bullets": [_yearly(b) for b in analysis.compare_bullets(f, py_label, Nc, Ny, ls,
                                                                            (y.get("lines"), y.get("lines_py"), None))]}
    foot = [ANNUAL_NOTE.format(form=y["form"], filed=y["filed"])]
    if "oi_derived" in Nc["flags"]:
        foot.append("Operating profit = revenue minus total costs and expenses (derived; the company does not tag operating income).")
    foot.append("Working capital &amp; other is the residual between operating cash flow and the listed items."
                + (" FCF = operating cash flow minus capital expenditures." if Nc.get("capex") else ""))
    return {
        "cite": sources.citation(name, y, "fy"),
        "period": "fy", "key": "fy-" + y["end"], "compare": None, "compare_y": compare_y, "preliminary": False,
        "end": y["end"], "label": y["label"], "cal": f"FY{y['fy']}", "form": y["form"], "filed": y["filed"],
        "doc_url": y.get("doc_url"), "index_url": y.get("index_url"), "kind": kind,
        "title": f"{name} {y['label']} earnings &amp; cash flow",
        "subtitle": f"Fiscal year ended {_date(y['end'])} · GAAP · Y/Y vs. {_short(y.get('py_end'))}",
        "footer": foot, "nodes": nodes, "links": links,
        "analysis": [_yearly(x) for x in analysis.paragraphs(f, y["label"], Nc, None, Ny, ls,
                                                             (y.get("lines"), None, y.get("lines_py")), py_label=py_label or "a year earlier")],
        "headline": {"revenue": Nc["R"], "rev_fmt": f.money(Nc["R"]), "yoy": _g(Nc["R"], Ny and Ny["R"]),
                     "ni": Nc["pl"], "ni_fmt": f.money(Nc["pl"]), "om": Nc["oi"] / Nc["R"] * 100,
                     "oi": Nc["oi"], "ocf": Nc.get("ocf")},
    }


def periods_payload(c):
    """Every quarter and fiscal year SEC has XBRL figures for: the choices for "compare any two"."""
    per = c.get("periods") or {}
    fye = c["profile"].get("fye") or "1231"
    q = []
    for e in reversed(per.get("q") or []):
        label, fq, fy = facts.fiscal_label(e, fye)
        q.append({"end": e, "label": label, "q": fq, "fy": fy})
    y = []
    for e in reversed(per.get("fy") or []):
        label, fy = facts.fiscal_year_label(e, fye)
        y.append({"end": e, "label": label, "fy": fy})
    return {"q": q, "fy": y}


def _g(a, b):
    return None if not a or not b or a <= 0 or b <= 0 else round((a / b - 1) * 100, 1)


def _date(s):
    return dt.date.fromisoformat(s).strftime("%B %-d, %Y") if s else "n/a"


def _short(s):
    return dt.date.fromisoformat(s).strftime("%b %-d, %Y") if s else "n/a"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def render(store, out, stars=frozenset()):
    os.makedirs(os.path.join(out, "c"), exist_ok=True)
    x_cfg = social.load_cfg("config/x.json")
    index, groups = [], {}
    for cik in store.ciks():
        c = store.company(cik)
        if not c.get("quarters") or not c.get("profile"):
            continue
        qs = sorted(c["quarters"].values(), key=lambda q: q["end"])
        payloads, prev = [], None
        for q in qs:
            try:
                pl = quarter_payload(c, q, prev)
            except Exception as e:
                print(f"  render failed {cik} {q['end']}: {e}", file=sys.stderr)
                pl = None
            if pl:
                payloads.append(pl)
            prev = q
        if not payloads:
            continue
        p = c["profile"]
        latest = payloads[-1]
        for pl in payloads:
            Nc, Nq, Ny = pl.pop("_N")
            for key in (("sector", p["sector"]), ("industry", p["sic"] or "none")):
                groups.setdefault(key, {}).setdefault(pl["cal"], []).append(
                    (p["tickers"][0] if p["tickers"] else p["name"][:18], Nc, Nq, Ny, cik))
        for pl in payloads:                      # the ready-to-post X thread (same text as the e-mails)
            try:
                posts = social.compose_parts({"profile": p, "intro": c.get("intro")}, pl, x_cfg)
                pl["x_thread"] = [{"text": x["text"], "len": social.xlen(x["text"]), "role": x["role"]} for x in posts]
            except Exception as e:
                print(f"  thread failed {cik} {pl['end']}: {e}", file=sys.stderr)
        years = []
        for y in sorted((c.get("years") or {}).values(), key=lambda y: y["end"], reverse=True):
            try:
                yp = year_payload(c, y)
            except Exception as e:
                print(f"  render failed {cik} FY {y['end']}: {e}", file=sys.stderr)
                yp = None
            if yp:
                years.append(yp)
        save(os.path.join(out, "c", f"{cik}.json"), {
            "profile": p, "intro": c.get("intro"), "starred": cik in stars, "quarters": payloads[::-1],
            "years": years, "periods": periods_payload(c)})
        # earlier filings of the last ten days (an 8-K release before its 10-Q), for the daily report of their day
        cut = (dt.date.fromisoformat(latest["filed"]) - dt.timedelta(days=10)).isoformat() if latest.get("filed") else "9999"
        also = [{"end": pl["end"], "label": pl["label"], "filed": pl["filed"], "form": pl["form"],
                 "rev": pl["headline"]["rev_fmt"], "revenue": pl["headline"]["revenue"], "yoy": pl["headline"]["yoy"]}
                for pl in payloads[:-1] if (pl.get("filed") or "") >= cut]
        index.append({"cik": cik, "ticker": (p["tickers"] or [""])[0], "name": p["name"], "sector": p["sector"],
                      "industry": p["industry"], "sic": p["sic"], "label": latest["label"], "end": latest["end"],
                      "cal": latest["cal"], "filed": latest["filed"], "form": latest["form"],
                      "rev": latest["headline"]["rev_fmt"], "revenue": latest["headline"]["revenue"],
                      "yoy": latest["headline"]["yoy"], "om": round(latest["headline"]["om"], 1),
                      "starred": cik in stars, "kind": latest["kind"], "prelim": latest["form"] == "8-K",
                      **({"also": also} if also else {}),
                      **({"after_release": latest["release_check"]["filed"], "release_ok": latest["release_check"]["ok"]}
                         if latest.get("release_check") else {})})
    agg_index = {"sector": [], "industry": []}
    for (level, gid), by_cal in groups.items():
        quarters = []
        for cal in sorted(by_cal, reverse=True)[:4]:
            members = by_cal[cal]
            if len(members) < 2:
                continue
            try:
                Nc, Nq, Ny, ls, lv = sectors.aggregate([(t, a, b, d) for t, a, b, d, _ in members])
                nodes, links, kind = build_spec(Nc, Nq, Ny, ls, lv)
                for n in nodes:
                    n.pop("notekeys", None)
                f = Fmt(Nc["R"])
                name = sectors.SECTORS.get(gid) if level == "sector" else _industry_name(index, gid)
                quarters.append({
                    "cal": cal, "kind": kind, "count": len(members),
                    "title": f"{name} {cal_label(cal)}: combined earnings &amp; cash flow",
                    "subtitle": f"{len(members)} companies · fiscal quarters ending in calendar {cal[2:6]} Q{cal[-1]} · GAAP",
                    "footer": ["Source: SEC EDGAR XBRL data. Sum of the companies' fiscal quarters that end in this calendar quarter; "
                               "detail lines appear only when every company reports them.",
                               "Y/Y and Q/Q compare the same companies' prior quarters when at least 90% of revenue has them."],
                    "nodes": nodes, "links": links,
                    "label": cal_label(cal),
                    "analysis": analysis.paragraphs(f, cal_label(cal), Nc, Nq, Ny, ls, lv),
                    "compare": ({"vs": cal_label(prev_cal(cal)),
                                 "title": f"{name} {cal_label(cal)} vs {cal_label(prev_cal(cal))}: what changed",
                                 "bullets": analysis.compare_bullets(f, cal_label(prev_cal(cal)), Nc, Nq, ls,
                                                                     (lv[0], lv[1], None))} if Nq else None),
                    "compare_y": ({"vs": cal_label(prev_year(cal)),
                                   "title": f"{name} {cal_label(cal)} vs {cal_label(prev_year(cal))}: what changed",
                                   "bullets": analysis.compare_bullets(f, cal_label(prev_year(cal)), Nc, Ny, ls,
                                                                       (lv[0], lv[2], None))} if Ny else None),
                    "companies": [{"cik": ck, "ticker": t, "revenue": a["R"]} for t, a, b, d, ck in
                                  sorted(members, key=lambda m: -m[1]["R"])],
                })
            except Exception as e:
                print(f"  aggregate failed {level} {gid} {cal}: {e}", file=sys.stderr)
        if quarters:
            name = sectors.SECTORS.get(gid) if level == "sector" else _industry_name(index, gid)
            save(os.path.join(out, level[0], f"{slug(str(gid))}.json"), {"id": gid, "name": name, "level": level,
                                                                          "quarters": quarters})
            agg_index[level].append({"id": slug(str(gid)), "name": name, "count": quarters[0]["count"],
                                     "cal": quarters[0]["cal"],
                                     "sector": sectors.sector_of(gid) if level == "industry" else gid})
    recent = sorted(index, key=lambda x: (x["filed"] or "", x["cik"]), reverse=True)
    audit = store.state.get("audit", [])
    tick = {x["cik"]: x["ticker"] or x["name"] for x in index}
    audit_out = {"checked": len(audit), "matched": sum(1 for a in audit if a["ok"]),
                 "mismatches": [{"ticker": tick.get(a["cik"], str(a["cik"])), "cik": a["cik"], "end": a["end"],
                                 "fields": {k: v[:2] for k, v in a["fields"].items() if not v[2]}}
                                for a in audit if not a["ok"]][-20:]}
    save(os.path.join(out, "index.json"), {
        "generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "companies": recent,
        "sectors": sorted(agg_index["sector"], key=lambda x: x["name"]),
        "industries": sorted(agg_index["industry"], key=lambda x: x["name"]),
        "sector_names": sectors.SECTORS, "release_audit": audit_out,
    })
    print(f"rendered {len(index)} companies, {len(agg_index['sector'])} sectors, {len(agg_index['industry'])} industries")


def cal_label(cal):
    return f"Q{cal[-1]} {cal[2:6]}"


def prev_year(cal):
    return f"CY{int(cal[2:6]) - 1}Q{cal[-1]}"


def prev_cal(cal):
    y, q = int(cal[2:6]), int(cal[-1])
    return f"CY{y - 1}Q4" if q == 1 else f"CY{y}Q{q - 1}"


def _industry_name(index, sic):
    return next((x["industry"] for x in index if x["sic"] == sic), f"SIC {sic}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "render"])
    ap.add_argument("--store", default="store")
    ap.add_argument("--out", default="_site/data")
    ap.add_argument("--backfill-days", type=int, default=0)
    ap.add_argument("--max-filings", type=int, default=1500)
    ap.add_argument("--build-ciks-file", default=None, help="CIKs readers asked for (one per line): fetch their history")
    args = ap.parse_args()
    args.build_ciks = []
    if args.build_ciks_file and os.path.exists(args.build_ciks_file):
        args.build_ciks = company_ciks(re.split(r"[\s,;]+", open(args.build_ciks_file).read()))
    if args.cmd == "run":
        run(args)
    else:
        render(Store(args.store), args.out, set(starred_ciks()))


if __name__ == "__main__":
    main()
