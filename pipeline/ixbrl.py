"""Figures from an inline-XBRL document (a 6-K whose report is tagged): its own facts, read without companyfacts.

Some foreign filers furnish their quarterly report as an inline-XBRL 6-K laid out as positioned text with no HTML tables
(TD Bank's report, a PDF converted to divs), so the release table reader finds nothing. The tags carry the figures:
each <ix:nonFraction> names its concept, its period (contextRef) and its scale. release() returns the same shape as
release.parse() for the quarter (or half) the document reports, plus the year-ago period in "py".
"""
import datetime as dt
import html as _html
import re

from . import facts

CTX = re.compile(r"<(?:xbrli:)?context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:xbrli:)?context>", re.S | re.I)
UNIT = re.compile(r"<(?:xbrli:)?unit\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:xbrli:)?unit>", re.S | re.I)
NONFRAC = re.compile(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", re.S | re.I)
CF_KEYS = ("ocf", "capex", "da", "sbc")


def _attr(s, k):
    m = re.search(r"\b" + k + r"=\"([^\"]*)\"", s)
    return m.group(1) if m else None


def _value(attrs, inner):
    text = _html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
    fmt = (_attr(attrs, "format") or "").lower()
    if "zero" in fmt or text in ("", "-", "—", "–"):
        v = 0.0
    else:
        t = re.sub(r"[^\d.,]", "", text)
        if "comma" in fmt and "decimal" in fmt and "dot" not in fmt.split("decimal")[0][-6:]:
            t = t.replace(".", "").replace(" ", "").replace(",", ".")      # 1.234,5
        else:
            t = t.replace(",", "")
        try:
            v = float(t)
        except ValueError:
            return None
    v *= 10 ** int(_attr(attrs, "scale") or 0)
    return -v if _attr(attrs, "sign") == "-" else v


def read(html, resources=""):
    """{(concept, start, end): value} for non-dimensional duration facts in money, and the document's currency.
    resources: the filing's other documents, when this one's contexts and units sit in another (TD Bank's 6-K keeps
    them in its cover document)."""
    ctx = {}
    for cid, body in CTX.findall(html + resources):
        if re.search(r"segment>|<xbrldi:", body, re.I):
            continue                                            # a breakdown (segment, product), not the total
        s = re.search(r"startDate>\s*([\d-]{10})", body)
        e = re.search(r"endDate>\s*([\d-]{10})", body)
        if s and e:
            ctx[cid] = (s.group(1), e.group(1))
    units = {}
    for uid, body in UNIT.findall(html + resources):
        m = re.search(r"iso4217:([A-Z]{3})\s*<", body)
        if m and "divide" not in body.lower():
            units[uid] = m.group(1)
    out, curs = {}, {}
    for attrs, inner in NONFRAC.findall(html):
        c = ctx.get(_attr(attrs, "contextRef"))
        cur = units.get(_attr(attrs, "unitRef"))
        if not c or not cur:
            continue
        tax, _, local = (_attr(attrs, "name") or "").partition(":")
        if tax not in ("ifrs-full", "us-gaap"):
            continue
        v = _value(attrs, inner)
        if v is None:
            continue
        out.setdefault((local, c[0], c[1]), v)
        curs[cur] = curs.get(cur, 0) + 1
    return out, (max(curs, key=curs.get) if curs else None)


def _pick(vals, key, start, end):
    """The first concept of facts.CONCEPTS[key] tagged for the period; revenue: "Revenues"/"Revenue" first, else the
    largest of the revenue tags."""
    names = facts.CONCEPTS.get(key, [])
    got = [(n, vals[(n, start, end)]) for n in names if (n, start, end) in vals]
    if not got:
        return None, None
    if key == "revenue":
        tot = [g for g in got if g[0] in ("Revenues", "Revenue")]
        return max(tot or got, key=lambda g: g[1])
    return got[0]


def _period(vals, start, end):
    out, labels = {}, {}
    for key in facts.CONCEPTS:
        n, v = _pick(vals, key, start, end)
        if n is not None:
            out[key], labels[key] = v, n
    if out.get("revenue") is None and out.get("nii") is not None:   # a bank: net interest income + non-interest income
        out["revenue"] = out["nii"] + (out.get("nonii") or 0)
        labels["revenue"] = "net interest income and non-interest income"
    return out, labels


def release(html, filed, resources=""):
    """The quarter (or half) the document reports: its latest period end that fits the filing date, the shortest
    period ending then (a quarter rather than the year to date). Raises ValueError when the tags do not give one."""
    if "ix:nonfraction" not in html[:5_000_000].lower():
        raise ValueError("no inline XBRL")
    vals, cur = read(html, resources)
    if not vals:
        raise ValueError("no tagged figures")
    ends = {}
    for (_, s, e) in vals:
        try:
            d = (filed - dt.date.fromisoformat(e)).days
        except ValueError:
            continue
        if 7 <= d <= 130:
            ends[e] = ends.get(e, 0) + 1
    if not ends:
        raise ValueError("no period that fits the filing date")
    end = max(ends, key=lambda e: (ends[e], e))
    e0 = dt.date.fromisoformat(end)
    spans = sorted({(e0 - dt.date.fromisoformat(s)).days: s for (_, s, e) in vals if e == end}.items())
    spans = [(d, s) for d, s in spans if d >= 80]
    for days, start in spans:                                   # the shortest period with revenue and net income
        cur_vals, labels = _period(vals, start, end)
        if cur_vals.get("revenue") and (cur_vals.get("pl") is not None or cur_vals.get("ni") is not None):
            break
    else:
        raise ValueError("no period with revenue and net income")
    # the same period a year earlier
    s0 = dt.date.fromisoformat(start)
    py, py_end = {}, None
    for (_, s, e) in vals:
        try:
            ds, de = (s0 - dt.date.fromisoformat(s)).days, (e0 - dt.date.fromisoformat(e)).days
        except ValueError:
            continue
        if 355 <= ds <= 375 and 355 <= de <= 375:
            py, _ = _period(vals, s, e)
            py_end = e
            break
    isv = {k: v for k, v in cur_vals.items() if k not in CF_KEYS}
    cf = {k: v for k, v in cur_vals.items() if k in CF_KEYS}
    return {"end": end, "is_quarter": days <= 100, "span": days, "scale": 1.0, "is": isv, "cf": cf,
            "cf_quarter": days <= 100, "labels": labels, "cols": {}, "tables": [], "ix": True, "currency": cur,
            "py": ({k: v for k, v in py.items()} if py and py.get("revenue") else None), "py_end": py_end}
