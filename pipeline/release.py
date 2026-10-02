"""Read the financial statements printed in an earnings release (8-K Item 2.02, Exhibit 99.1).

Earnings releases carry no XBRL for their statements, so the tables are read by fixed rules (no
language model): row labels are matched against patterns, the first numeric column is the current
period, units are checked against the company's previous quarter in XBRL, and the result must
reconcile (pre-tax earnings - tax = net earnings) before it is used. Anything that does not add up
is rejected rather than guessed.
"""
import datetime as dt
import re

from bs4 import BeautifulSoup

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
                     r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(20\d\d)\b", re.I)
DASHES = {"—", "–", "-", "−", "--", "— —", "*"}

# label patterns (labels are lower-cased, footnote marks and punctuation normalised first)
P = {
    "revenue": r"^(total )?(net )?(revenues?|sales|net sales|net revenues?)(,? net)?$|^total (net )?(revenues?|sales)$"
               r"|^(net )?sales and (other )?operating revenues?$|^(total )?revenues? from contracts with customers$"
               r"|^total net sales and revenues?$|^revenues? and other income$",
    "cor": r"^(total )?cost of (net )?(revenues?|sales|goods sold|products sold|products and services sold|net sales)(,? net)?$"
           r"|^cost of revenues?,? total$|^total cost of (revenues?|sales)$|^cost of goods and services sold$",
    "gp": r"^(total )?gross (profit|margin)$",
    "rd": r"^(research(,)? and development|research, development and engineering|technology and development|"
          r"product development|engineering, research and development|research and development expenses?)$",
    "sm": r"^(sales and marketing|selling and marketing|marketing and sales|marketing|selling)( expenses?)?$",
    "ga": r"^general and administrative( expenses?)?$",
    "sga": r"^(selling|sales|marketing),? general,? and administrative( expenses?)?$",
    "costs_total": r"^total (costs and expenses|operating costs and expenses|costs and operating expenses|cost and expenses)$",
    "opex_total": r"^total operating expenses$",
    "oi": r"^(total )?operating (income|profit|loss|earnings|income \(loss\)|\(loss\) income|loss \(income\))$"
          r"|^(income|loss|earnings|income \(loss\)|\(loss\) income) from operations$",
    "pretax": r"^(income|earnings|loss|income \(loss\)|\(loss\) income|loss \(income\))( from continuing operations)?"
              r"( before (provision for |benefit from )?(income )?taxes| before income tax (expense|provision|benefit)s?)$",
    "tax": r"^((\(provision\) benefit|provision \(benefit\)|\(provision for\) benefit from|provision for \(benefit from\)|"
           r"benefit from \(provision for\)|provision for|benefit from|\(benefit\) provision) (for )?income taxes"
           r"|income tax (expense|provision|benefit|\(provision\) benefit|\(expense\) benefit|expense \(benefit\)|"
           r"benefit \(expense\)|provision \(benefit\))|income taxes|income tax)$",
    "pl": r"^net (income|earnings|loss|income \(loss\)|\(loss\) income|loss \(income\)|earnings \(loss\))$",
    "ni": r"^net (income|earnings|loss|income \(loss\)|\(loss\) income|earnings \(loss\)) (attributable|applicable|available) to "
          r"(?!non-?controlling|minority|redeemable non)",
    "nci": r"^(less: )?net (income|loss|income \(loss\)|\(income\) loss|\(loss\) income|earnings) attributable to "
           r"(non-?controlling|minority)|^(non-?controlling|minority) interests?$",
    "ocf": r"^net cash (provided by|from|used in|\(used in\) provided by|provided by \(used in\)|generated from|"
           r"provided by \(used for\)|\(used for\) provided by|provided by operating|used for) operating activities$",
    "da": r"^(depreciation|depreciation, depletion)( expense)?( and amortization( expense)?( of [a-z ,]+)?)?$"
          r"|^amortization and depreciation$|^depreciation, amortization and accretion$",
    "sbc": r"^(stock|share|equity)[- ]based compensation( expense)?$",
    "capex": r"^(purchases?|acquisitions?|additions?|expenditures) (of|to|for) (property|plant|premises)|^capital expenditures$"
             r"|^payments? for (the )?(acquisition of |purchases? of )?property",
}
PATTERNS = {k: re.compile(v) for k, v in P.items()}
COST_KEYS = ("cor", "rd", "sm", "ga", "sga", "costs_total", "opex_total", "da", "sbc", "capex")
IS_KEYS = ("revenue", "cor", "gp", "rd", "sm", "ga", "sga", "costs_total", "opex_total", "oi", "pretax", "tax", "pl", "ni", "nci")
CF_KEYS = ("ocf", "da", "sbc", "capex")
QTR_RE = re.compile(r"three months|quarter ended|quarters ended|thirteen weeks|fourteen weeks|1[34] weeks|"
                    r"(first|second|third|fourth) (fiscal )?quarter|\bq[1-4]\b|\d(st|nd|rd|th) qtr")
YTD_RE = re.compile(r"six months|nine months|twelve months|years? ended|fiscal (year )?20\d\d\b|full year|"
                    r"2[67] weeks|39 weeks|40 weeks|5[23] weeks|year[- ]to[- ]date|\bytd\b")


def _date(m):
    return dt.date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))


def norm_label(s):
    s = s.lower().replace(" ", " ").replace("&", " and ").replace("’", "'")
    s = re.sub(r"\((\d{1,2}|[a-z]|[ivx]+)\)|\*+|†|‡", " ", s)            # footnote marks
    s = re.sub(r"[:$]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.;-")
    return s


def _number(cell):
    s = cell.replace("$", "").replace(" ", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("(") or s.startswith("−") or (s.startswith("-") and len(s) > 1)
    core = s.strip("()−-%")
    if re.fullmatch(r"[0-9][0-9,]*(\.[0-9]+)?", core) and (core.count(",") == 0 or re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", core)):
        v = float(core.replace(",", ""))
        return -v if neg else v
    return None


def read_tables(html):
    soup = BeautifulSoup(html, "lxml")
    for bad in soup.find_all(["script", "style"]):
        bad.decompose()
    out = []
    for t in soup.find_all("table"):
        if t.find_parent("table"):
            continue
        rows = []
        for tr in t.find_all("tr"):
            cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip() for td in tr.find_all(["td", "th"])]
            label, vals, pct = None, [], False
            for c in cells:
                if not c or c in ("$", ")", "(", "%"):
                    pct = pct or c == "%"
                    continue
                if c in DASHES:
                    if label is not None:
                        vals.append(0.0)
                    continue
                v = _number(c)
                if v is not None and label is not None:
                    vals.append(v)
                    pct = pct or c.endswith("%")
                elif v is None and label is None and re.search(r"[A-Za-z]", c):
                    label = c
                elif v is not None and label is None:
                    vals.append(v)                        # header numbers (years) or unlabeled rows
            rows.append({"cells": cells, "label": label, "key": norm_label(label) if label else "", "vals": vals, "pct": pct})
        before = " ".join(s.strip() for s in t.find_all_previous(string=True, limit=30))[:1500]
        out.append({"rows": rows, "before": before, "text": t.get_text(" ", strip=True)})
    return out


def _header(table):
    """Text of the rows above the first labelled row that carries numbers."""
    head = []
    for r in table["rows"]:
        if r["label"] and r["vals"] and not all(1990 <= abs(v) <= 2100 for v in r["vals"]):
            break
        head.append(" ".join(r["cells"]))
    return " ".join(head).lower()


def _first_is_quarter(header_text):
    q, y = QTR_RE.search(header_text), YTD_RE.search(header_text)
    if q and (not y or q.start() < y.start()):
        return True
    if y:
        return False
    return None


def _map_rows(table, keys, full=False):
    found, section = {}, ""
    for r in table["rows"]:
        lab = r["key"]
        if lab and not r["vals"]:
            section = lab
            continue
        if not lab or not r["vals"] or r["pct"]:
            continue
        if lab in ("total", "total, net", "net") and section:
            lab = norm_label("total " + section)
        if re.search(r"per (diluted |basic )?share|per common share|margin %|% of|percent|weighted|shares used|non-gaap|adjusted",
                     lab):
            continue
        for k in keys:
            if PATTERNS[k].search(lab):
                v = r["vals"][0]
                if k == "revenue":
                    prev = found.get(k)
                    if prev is None or lab.startswith("total") or (not prev[1].startswith("total") and v > prev[0]):
                        found[k] = (v, lab, r["vals"])
                elif k not in found:
                    found[k] = (v, lab, r["vals"])
                break
    if full:
        return found
    return {k: x[0] for k, x in found.items()}


def _units(table):
    m = re.search(r"in (thousands|millions|billions)", (table["before"] + " " + table["text"][:600]).lower())
    return {"thousands": 1e3, "millions": 1e6, "billions": 1e9}[m.group(1)] if m else None


def _is_nongaap(table):
    return bool(re.search(r"non-gaap|adjusted|reconciliation", (table["before"][-400:] + " " + table["text"][:300]).lower()))


def pick_tables(tables):
    weights = {"revenue": 3, "pretax": 2, "tax": 2, "pl": 2, "ni": 2, "oi": 1, "gp": 1, "cor": 1}
    best_is = best_cf = None
    for t in tables:
        if _is_nongaap(t):
            continue
        m = _map_rows(t, IS_KEYS)
        score = sum(w for k, w in weights.items() if k in m)
        if "revenue" in m and ("pl" in m or "ni" in m) and (best_is is None or score > best_is[0]):
            best_is = (score, t, m)
        c = _map_rows(t, CF_KEYS)
        if "ocf" in c and (best_cf is None or len(c) > len(best_cf[2])):
            best_cf = (len(c), t, c)
    return best_is, best_cf


def period_end(html_text, tables, last_end, filed):
    """Quarter end named in the release: a date 75-110 days after the last quarter in XBRL (or before filing)."""
    dates = set(_date(m) for m in DATE_RE.finditer(html_text))
    for t in tables:
        dates.update(_date(m) for m in DATE_RE.finditer(_header(t)))
    if last_end:
        cands = [x for x in dates if 75 <= (x - last_end).days <= 110 and x < filed]
        target = last_end + dt.timedelta(days=91)
    else:
        cands = [x for x in dates if 0 < (filed - x).days <= 100]
        target = filed - dt.timedelta(days=30)
    return min(cands, key=lambda x: abs((x - target).days)) if cands else None


def parse(html, filed, last_end=None, prior_revenue=None):
    """Returns {"end", "is": {key: value}, "cf": {key: value}, "is_quarter", "cf_quarter", "scale"} or raises ValueError."""
    tables = read_tables(html)
    best_is, best_cf = pick_tables(tables)
    if not best_is:
        raise ValueError("no statement of operations found")
    _, t_is, m_is = best_is
    # units: stated units first, then checked against the previous quarter's revenue in XBRL
    scale = _units(t_is)
    if prior_revenue:
        ok = lambda s: s and 0.2 <= m_is["revenue"] * s / prior_revenue <= 5
        if not ok(scale):
            scale = next((s for s in (1e6, 1e3, 1e9, 1.0) if ok(s)), None)
    if not scale:
        raise ValueError("cannot tell the units of the release tables")
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    end = period_end(text[:6000], [t_is], last_end, filed)
    if not end:
        raise ValueError("cannot find the quarter end date in the release")
    full = _map_rows(t_is, IS_KEYS, full=True)
    out = {"end": end.isoformat(), "scale": scale, "is_quarter": _first_is_quarter(_header(t_is)),
           "is": {k: v * scale for k, v in m_is.items()}, "cf": {}, "cf_quarter": None,
           "labels": {k: x[1] for k, x in full.items()},
           "cols": {k: [v * scale for v in x[2]] for k, x in full.items()}}       # every column, for sign checks
    if best_cf:
        _, t_cf, m_cf = best_cf
        u_is, u_cf = _units(t_is), _units(t_cf)
        s_cf = u_cf if (u_cf and u_is and u_cf != u_is) else scale    # same units as the income statement unless stated
        out["cf"] = {k: v * s_cf for k, v in m_cf.items()}
        out["cf_quarter"] = _first_is_quarter(_header(t_cf))
    return out


def calibrate_tax(raw, cols, refs):
    """Releases print tax either as an expense (positive) or as a "(provision)" (negative). Compare the release's
    earlier-period columns with the same periods in XBRL, where expense is positive, and flip when they disagree."""
    tax_cols = (cols or {}).get("tax") or []
    for col in tax_cols[1:]:
        for ref in refs:
            if ref and col and abs(abs(col) - abs(ref)) <= 0.02 * abs(ref) + 1e5:
                if col * ref < 0 and raw.get("tax") is not None:
                    raw["tax"] = -raw["tax"]
                return True
    return False


def reconcile(raw, labels=None, tax_checked=False):
    """Fix signs the way statements print them and check that the income statement adds up."""
    r = dict(raw)
    for k in COST_KEYS:
        if r.get(k) is not None:
            r[k] = abs(r[k])
    if r.get("revenue") is None or r["revenue"] <= 0:
        raise ValueError("no positive revenue")
    pl, ni, nci = r.get("pl"), r.get("ni"), r.get("nci")
    if pl is not None and ni is None:
        ni = pl                                               # no minority interests line
    if ni is None:
        raise ValueError("no net income line")
    if r.get("pretax") is not None and r.get("tax") is not None:
        nets = [pl] if pl is not None else [ni] + ([ni + abs(nci), ni - abs(nci)] if nci else [])
        tol = max(abs(r["pretax"]), abs(ni)) * 0.01 + 1e5
        for net in nets:
            hit = next((sg for sg in (1, -1) if abs(r["pretax"] - sg * r["tax"] - net) <= tol), None)
            if hit:
                r["tax"], pl = hit * r["tax"], net             # tax printed as a negative "(provision)" flips sign
                break
        else:
            raise ValueError("pre-tax earnings, tax and net income do not reconcile")
    elif r.get("tax") is not None and not tax_checked:
        # no pre-tax line and no earlier column to compare: read the sign from the label
        lab = (labels or {}).get("tax", "")
        if r["tax"] < 0 and re.search(r"\(provision|\(expense\)|benefit \((expense|provision)", lab):
            r["tax"] = -r["tax"]
    r["pl"], r["ni"] = pl, ni
    r["nci"] = (pl - ni) if pl is not None else None
    if r.get("gp") is not None and r.get("cor") is not None and abs(r["revenue"] - r["cor"] - r["gp"]) > 0.01 * r["revenue"]:
        r["cor"] = None
    return r


def note_paragraphs(html):
    """The release's own text, as paragraphs, for node notes (tables excluded)."""
    from . import text
    return [p for p in text.paragraphs(html) if not p["heading"] or len(p["text"]) < 90]
