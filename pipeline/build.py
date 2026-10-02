"""Orchestrates a run: scan EDGAR, process new filings into the store, then render the website data.

    python -m pipeline.build run    --store store --out site/data [--backfill-days N] [--max-filings N]
    python -m pipeline.build render --store store --out site/data
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import traceback

from . import analysis, dims, facts, release, scan, sec, sectors, text
from .model import normalize
from .sankey import NOTE_KEYS, Fmt, build as build_spec

KEEP_QUARTERS = 3          # per ordinary company
KEEP_STARRED = 8           # multi-quarter history for starred companies
PENDING_TRIES = 24         # companyfacts can lag a filing by hours


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
    try:
        inst_url, lab_url = dims.find_files(cik, accn)
        if inst_url:
            labels = dims.parse_labels(sec.get(lab_url)) if lab_url else {}
            dfx = dims.parse_instance(sec.get(inst_url), labels)
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
            it = text.intro(doc)
            if it:
                c["intro"] = {"text": it, "url": doc_url, "filed": row.get("filingDate")}
        elif not c.get("intro"):
            k = next((r for r in recent_rows(sub) if r["form"] == "10-K" and r.get("primaryDocument")), None)
            if k:
                u = sec.doc_url(cik, k["accessionNumber"], k["primaryDocument"])
                it = text.intro(sec.get(u))
                if it:
                    c["intro"] = {"text": it, "url": u, "filed": k.get("filingDate")}
    except Exception as e:
        print(f"  intro skipped for {cik}: {e}", file=sys.stderr)

    label, fq, fy = facts.fiscal_label(end, c["profile"]["fye"])
    c["quarters"][end] = {
        "end": end, "label": label, "fq": fq, "fy": fy, "cal": facts.calendar_quarter(end), "form": form,
        "accn": accn, "filed": row.get("filingDate"), "doc_url": doc_url,
        "index_url": sec.filing_base(cik, accn) + f"/{accn}-index.htm",
        "raw": raw, **comp, "lines_struct": lines_struct, "lines": lines_cur, "lines_py": lines_py, "notes": notes,
    }
    e0 = dt.date.fromisoformat(end)                               # the 10-Q/10-K replaces a preliminary 8-K quarter
    for k in [k for k, q in c["quarters"].items() if q.get("form") == "8-K" and k != end
              and abs((dt.date.fromisoformat(k) - e0).days) <= 10]:
        del c["quarters"][k]
    keep = KEEP_STARRED if starred else KEEP_QUARTERS
    c["quarters"] = dict(sorted(c["quarters"].items())[-keep:])
    store.put(cik, c)
    return end


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


def process_release(store, cik, accn, form, starred=False):
    """A preliminary quarter from an earnings release (8-K Item 2.02); the 10-Q/10-K replaces it when filed."""
    sub = submissions(cik)
    row = next((r for r in recent_rows(sub) if r["accessionNumber"] == accn), None)
    if not row:
        raise Pending("filing not yet in submissions")
    if "2.02" not in (row.get("items") or ""):
        raise NotApplicable("8-K without Item 2.02 (not an earnings release)")
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
    try:
        rel = release.parse(doc, dt.date.fromisoformat(row["filingDate"]), last, prior_rev)
        end = rel["end"]
        e0 = dt.date.fromisoformat(end)
        if any(q.get("form") != "8-K" and abs((dt.date.fromisoformat(k) - e0).days) <= 10 for k, q in c["quarters"].items()):
            raise NotApplicable("the 10-Q/10-K for this quarter is already in")
        q1_end, py_end = facts.comparison_ends(fx, end)
        label, fq, fy = facts.fiscal_label(end, c["profile"]["fye"])
        if rel["is_quarter"] is False and fq != 1:
            raise ValueError("the income statement shows year-to-date figures first")
        raw = {k: None for k in facts.CONCEPTS}
        raw.update(_release_quarter(rel["is"], True, fx, q1_end, release.IS_KEYS))
        raw.update(_release_quarter(rel["cf"], rel["cf_quarter"] is True or fq == 1, fx, q1_end, release.CF_KEYS))
        refs = [facts.value(fx, "tax", e) for e in (q1_end, py_end) if e]
        checked = release.calibrate_tax(raw, rel["cols"], refs)
        raw = release.reconcile(raw, rel["labels"], checked)
    except ValueError as e:
        raise NotApplicable(f"earnings release not readable: {e}")
    if not normalize(raw):
        raise NotApplicable("earnings release lacks revenue or net income")
    notes = {}
    paras = release.note_paragraphs(doc)
    for key, words in note_keys_for(None).items():
        m = text.match_notes(paras, words)
        if m:
            notes[key] = m
    c["quarters"][end] = {
        "end": end, "label": label, "fq": fq, "fy": fy, "cal": facts.calendar_quarter(end), "form": "8-K",
        "accn": accn, "filed": row.get("filingDate"), "doc_url": ex_url,
        "index_url": sec.filing_base(cik, accn) + f"/{accn}-index.htm", "raw": raw,
        "q1_end": q1_end, "py_end": py_end, "raw_q1": facts.extract(fx, q1_end), "raw_py": facts.extract(fx, py_end),
        "lines_struct": None, "lines": None, "lines_py": None, "notes": notes,
    }
    keep = KEEP_STARRED if starred else KEEP_QUARTERS
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
    done = 0
    order = sorted(st["pending"].items(), key=lambda kv: kv[1]["filed"], reverse=True)
    order.sort(key=lambda kv: kv[1]["form"] == "8-K" and kv[1].get("items") is None)   # unclassified 8-Ks last
    for accn, p in order:
        if done >= args.max_filings:
            break
        done += 1
        try:
            end = process_filing(store, p["cik"], accn, p["form"], starred=p["cik"] in stars)
            st["seen"][accn] = {"t": now, "s": "ok", "cik": p["cik"], "end": end, "form": p["form"], "filed": p["filed"]}
            del st["pending"][accn]
            print(f"ok   {p['form']:5} {p['cik']:>10} {accn} {end}")
        except Pending as e:
            p["tries"] += 1
            if p["tries"] >= PENDING_TRIES:
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
        if done % 25 == 0:
            store.commit()
    st["log"].append({"t": now, "processed": done, "pending": len(st["pending"])})
    store.commit()
    render(store, args.out, set(stars))


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
    lines_q1 = prev_q.get("lines") if prev_q and prev_q.get("end") == q.get("q1_end") else None
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
    f = Fmt(Nc["R"])
    labels = {e: x["label"] for e, x in c["quarters"].items()}
    py_label = labels.get(q.get("py_end")) or "a year earlier"
    p = c["profile"]
    name = p["name"]
    q1_label = labels.get(q.get("q1_end")) or (facts.fiscal_label(q["q1_end"], p.get("fye") or "1231")[0]
                                               if q.get("q1_end") else None)
    compare = None
    if Nq and q1_label:
        compare = {"vs": q1_label, "title": f"{name} {q['label']} vs {q1_label}: what changed",
                   "bullets": analysis.compare_bullets(f, q1_label, Nc, Nq, ls, (q.get("lines"), lines_q1, None))}
    return {
        "compare": compare, "preliminary": q["form"] == "8-K",
        "end": q["end"], "label": q["label"], "cal": q["cal"], "form": q["form"], "filed": q["filed"],
        "doc_url": q.get("doc_url"), "index_url": q.get("index_url"), "kind": kind,
        "title": f"{name} {q['label']} earnings &amp; cash flow",
        "subtitle": (f"Quarter ended {_date(q['end'])} · GAAP · Y/Y vs. {_short(q.get('py_end'))} "
                     f"· Q/Q vs. {_short(q.get('q1_end'))}" + (" · preliminary, from the earnings release" if q["form"] == "8-K" else "")),
        "footer": _footer(q, kind, Nc), "nodes": nodes, "links": links,
        "analysis": analysis.paragraphs(f, q["label"], Nc, Nq, Ny, ls, (q.get("lines"), lines_q1, q.get("lines_py")),
                                        py_label=py_label),
        "headline": {"revenue": Nc["R"], "rev_fmt": f.money(Nc["R"]), "yoy": _g(Nc["R"], Ny and Ny["R"]),
                     "ni": Nc["pl"], "ni_fmt": f.money(Nc["pl"]), "om": Nc["oi"] / Nc["R"] * 100},
        "_N": (Nc, Nq, Ny),
    }


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
        save(os.path.join(out, "c", f"{cik}.json"), {
            "profile": p, "intro": c.get("intro"), "starred": cik in stars, "quarters": payloads[::-1]})
        index.append({"cik": cik, "ticker": (p["tickers"] or [""])[0], "name": p["name"], "sector": p["sector"],
                      "industry": p["industry"], "sic": p["sic"], "label": latest["label"], "end": latest["end"],
                      "cal": latest["cal"], "filed": latest["filed"], "form": latest["form"],
                      "rev": latest["headline"]["rev_fmt"], "revenue": latest["headline"]["revenue"],
                      "yoy": latest["headline"]["yoy"], "om": round(latest["headline"]["om"], 1),
                      "starred": cik in stars, "kind": latest["kind"], "prelim": latest["form"] == "8-K"})
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
    save(os.path.join(out, "index.json"), {
        "generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "companies": recent,
        "sectors": sorted(agg_index["sector"], key=lambda x: x["name"]),
        "industries": sorted(agg_index["industry"], key=lambda x: x["name"]),
        "sector_names": sectors.SECTORS,
    })
    print(f"rendered {len(index)} companies, {len(agg_index['sector'])} sectors, {len(agg_index['industry'])} industries")


def cal_label(cal):
    return f"Q{cal[-1]} {cal[2:6]}"


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
    args = ap.parse_args()
    if args.cmd == "run":
        run(args)
    else:
        render(Store(args.store), args.out, set(starred_ciks()))


if __name__ == "__main__":
    main()
