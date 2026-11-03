"""Revenue breakdowns (products, segments) from a filing's XBRL instance - dimensional facts are not in companyfacts."""
import datetime as dt
import re
import xml.etree.ElementTree as ET

from . import sec
from .facts import CONCEPTS

AXES = ("ProductOrServiceAxis", "StatementBusinessSegmentsAxis")
TOL = 0.004                     # a breakdown must add up to total revenue within 0.4%


def _local(tag):
    return tag.split("}")[-1]


def find_files(cik, accn):
    """(instance url, label linkbase url) from the filing's directory listing."""
    idx = sec.get_json(sec.filing_index_url(cik, accn))
    names = [i["name"] for i in idx.get("directory", {}).get("item", [])]
    inst = next((n for n in names if n.endswith("_htm.xml")), None)
    if not inst:
        inst = next((n for n in names if re.search(r"\d{8}\.xml$", n) and not re.search(r"_(cal|def|lab|pre)\.xml$", n)), None)
    lab = next((n for n in names if n.endswith("_lab.xml")), None)
    url = lambda n: sec.doc_url(cik, accn, n) if n else None
    return url(inst), url(lab)


NOT_A_NAME = re.compile(r"\b(costs?|expenses?|liabilit(y|ies)|payables?|receivables?|accrued|deferred|amortization)\b", re.I)
DOC_LIKE = re.compile(r"^(this|the) (member|element|axis|domain)\b|\bstands for\b|\belement represents\b", re.I)


def parse_labels(xml_text):
    """element id (e.g. 'aapl_IPhoneMember') -> preferred label.

    Every label the company gives the element counts (one element can have several label resources, each with its
    own arc). The terse label first, then the standard and the verbose one, then any other role — never the
    documentation, a sentence ("This member stands for …"). A label that names a cost, an expense or a liability is
    passed over when another one does not: companies give a revenue member the terse label of a cost table it also
    appears in (Workday: professional services → "Costs of professional services"; Delta: passenger → "Air traffic
    liability"; Xenia: rooms → "Rooms expenses"). When every label names one, the terse label stays, as before."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    xl = "{http://www.w3.org/1999/xlink}"
    loc, lab_by_res, arcs = {}, {}, []
    for el in root.iter():
        name = _local(el.tag)
        if name == "loc":
            loc[el.get(xl + "label")] = el.get(xl + "href", "").split("#")[-1]
        elif name == "label":
            role = el.get(xl + "role", "")
            lab_by_res.setdefault(el.get(xl + "label"), []).append((role, (el.text or "").strip()))
        elif name == "labelArc":
            arcs.append((el.get(xl + "from"), el.get(xl + "to")))
    by_el = {}
    for frm, to in arcs:
        elid = loc.get(frm)
        if elid:
            by_el.setdefault(elid, []).extend(lab_by_res.get(to, []))
    order = ("terseLabel", "label", "verboseLabel")
    out = {}
    for elid, labs in by_el.items():
        roles = {}
        for role, text in labs:
            r = role.rsplit("/", 1)[-1]
            t = clean_label(text)
            if r not in ("documentation", "definitionGuidance", "commentaryGuidance") and t and not DOC_LIKE.search(t):
                roles.setdefault(r, t)
        cands = [roles[r] for r in order if r in roles] + [t for r, t in roles.items() if r not in order]
        if not cands:
            continue
        plain = [t for t in cands if not NOT_A_NAME.search(t)]
        out[elid] = clean_label(plain[0] if plain else cands[0], elid)
    return out


DOCUMENTATION = re.compile(r"^(this member|represents|information (pertaining|about)|the member|a member|member stands|element)", re.I)


def clean_label(text, elid=""):
    """A member's label as a chart writes it: "[Member]", "[Members]" and a trailing "Member" word gone ("Cabinetry And
    Millwork Member", "Direct to Consumer [member]"); a documentation sentence put in the label's place ("This member
    stands for the information pertaining to …") replaced by the element's own name in words; "[Domain]", "[Axis]" and
    a closing full stop ("Japan." → "Japan") gone too."""
    t = re.sub(r"\s*\[\s*(?:members?|domain|axis|line items?|table|abstract)\s*\]", "", (text or "").strip(), flags=re.I)   # "[Member] [Domain]"
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+Members?$", "", t)
    if elid and (DOCUMENTATION.search(t) or len(t) > 90 or (t.endswith(".") and len(t) > 40)):
        t = humanize(elid.split("_", 1)[-1]) if "_" in elid else humanize(elid)
    t = re.sub(r"(?<=[a-z]{3})\.$", "", t)              # a closing full stop ("Japan." → "Japan"), not "U.S."
    return t.strip()


def label_roles(xml_text):
    """element id (e.g. 'us-gaap_PaymentsToAcquirePropertyPlantAndEquipment') -> {label role (short): text}."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    xl = "{http://www.w3.org/1999/xlink}"
    loc, res, out = {}, {}, {}
    arcs = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "loc":
            loc[el.get(xl + "label")] = el.get(xl + "href", "").split("#")[-1]
        elif name == "label":
            res.setdefault(el.get(xl + "label"), []).append((el.get(xl + "role", "").rsplit("/", 1)[-1], (el.text or "").strip()))
        elif name == "labelArc":
            arcs.append((el.get(xl + "from"), el.get(xl + "to")))
    for frm, to in arcs:
        elid = loc.get(frm)
        if elid:
            out.setdefault(elid, {}).update({r: t for r, t in res.get(to, []) if t})
    return out


def statement_label(roles):
    """The line name as printed in the statement: the negated or terse label, else the standard one."""
    for r in ("negatedLabel", "negatedTerseLabel", "terseLabel", "label"):
        if (roles or {}).get(r):
            return roles[r]
    return next(iter((roles or {}).values()), None)


CAPEX_LABEL = re.compile(r"^(purchases?|acquisitions?|additions?|expenditures?|investments?|payments?|capital "
                         r"expenditures?)\b.*\b(property|plant|equipment|premises|fixed assets|oil and gas|capital)"
                         r"|^capital (expenditures?|spending|investments?)\b", re.I)
CAPEX_NOT = re.compile(r"proceeds|sale|dispos|accrued|unpaid|non-?cash|included in|financ|lease|deposit|business|"
                       r"intangible|software|acquired|accounts payable|liabilit|interest|reimburse|dividend|"
                       r"distribution|stock|shares?\b|repurchase|debt|loan|notes?\b", re.I)


def _contexts(root):
    out = {}
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        start = end = None
        dims = False
        for el in ctx.iter():
            n = _local(el.tag)
            if n == "startDate":
                start = el.text.strip()
            elif n == "endDate":
                end = el.text.strip()
            elif n in ("explicitMember", "typedMember"):
                dims = True
        if start and end and not dims:
            out[ctx.get("id")] = (start, end)
    return out


def capex_lines(xml_text, roles):
    """The capital-expenditure line of a filing found by its printed name, standard or company-specific tag:
    {"concept": "abc:PaymentsForEquipment", "label": "Purchases of property and equipment", "facts": [(start, end, v)]}."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    ctx = _contexts(root)
    by_local = {}
    for elid in roles:
        by_local.setdefault(elid.split("_", 1)[-1], []).append(elid)
    found = {}
    for el in root.iter():
        cref = el.get("contextRef")
        if cref not in ctx or not (el.text or "").strip():
            continue
        local = _local(el.tag)
        ids = by_local.get(local)
        if not ids:
            continue
        label = statement_label(roles[ids[0]])
        names = label + " | " + (roles[ids[0]].get("label") or "")
        if not label or not CAPEX_LABEL.search(label) or CAPEX_NOT.search(names):
            continue
        try:
            val = abs(float(el.text.strip()))
        except ValueError:
            continue
        start, end = ctx[cref]
        found.setdefault(ids[0], {"label": label, "facts": {}})["facts"][(start, end)] = val
    if not found:
        return None
    latest = lambda f: max(f["facts"].items(), key=lambda kv: (kv[0][1], kv[1]))[1]
    elid, f = max(found.items(), key=lambda kv: latest(kv[1]))        # the main line, not a sub-line
    prefix, local = elid.split("_", 1) if "_" in elid else ("", elid)
    return {"concept": f"{prefix}:{local}" if prefix else local, "label": f["label"],
            "facts": sorted((s, e, v) for (s, e), v in f["facts"].items())}


def concept_facts(xml_text, concept):
    """Non-dimensional duration facts [(start, end, value)] of one concept ('prefix:Local') in an instance."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    ctx = _contexts(root)
    local = concept.split(":")[-1]
    out = {}
    for el in root.iter():
        if _local(el.tag) == local and el.get("contextRef") in ctx and (el.text or "").strip():
            try:
                out[ctx[el.get("contextRef")]] = abs(float(el.text.strip()))
            except ValueError:
                pass
    return sorted((s, e, v) for (s, e), v in out.items())


def period_value(facts_, end, annual=False):
    """A quarter (or, annual, a fiscal year) ending at `end` from duration facts: a 3-month fact, or the longest
    year-to-date minus the year-to-date before it with the same start (Q4 = full year - nine months)."""
    at = [(s, v) for s, e, v in facts_ if e == end]
    if not at:
        return None
    if annual:
        return next((v for s, v in at if 350 <= _span(s, end) <= 380), None)
    for s, v in at:
        if 75 <= _span(s, end) <= 100:
            return v
    s0, v0 = min(at)
    for s, e, v in facts_:
        if s == s0 and e != end and 75 <= _span(e, end) <= 105:
            return v0 - v
    return None


def humanize(qname):
    name = qname.split(":")[-1]
    name = re.sub(r"Member$", "", name)
    name = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return name.strip()


def parse_instance(xml_text, labels=None):
    """Revenue facts with exactly one breakdown dimension: list of (axis, member, label, start, end, value)."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    contexts = {}
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        start = end = None
        dims = []
        for el in ctx.iter():
            n = _local(el.tag)
            if n == "startDate":
                start = el.text.strip()
            elif n == "endDate":
                end = el.text.strip()
            elif n == "explicitMember":
                dims.append((el.get("dimension"), (el.text or "").strip()))
        if start and end:
            contexts[ctx.get("id")] = (start, end, dims)
    rev_concepts = set(CONCEPTS["revenue"])
    out = []
    for el in root.iter():
        if _local(el.tag) not in rev_concepts or el.get("contextRef") not in contexts:
            continue
        start, end, dims = contexts[el.get("contextRef")]
        if len(dims) != 1 or dims[0][0].split(":")[-1] not in AXES or not (el.text or "").strip():
            continue
        try:
            val = float(el.text.strip())
        except ValueError:
            continue
        axis, member = dims[0][0].split(":")[-1], dims[0][1]
        elid = member.replace(":", "_")
        label = (labels or {}).get(elid) or humanize(member)
        out.append((axis, member, label, start, end, val))
    return out


def _span(start, end):
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def member_values(facts, end, prev_ytd=None):
    """axis -> member -> value for the quarter ending `end` (3-month fact, or YTD minus prev_ytd)."""
    out = {}
    for axis, member, label, start, e, val in facts:
        if e != end:
            continue
        span = _span(start, e)
        cur = out.setdefault(axis, {})
        if 75 <= span <= 100:
            cur[member] = (label, val)
    if any(out.values()):
        return out
    if prev_ytd:
        for axis, member, label, start, e, val in facts:
            if e == end and _span(start, e) > 250 and member in prev_ytd.get(axis, {}):
                out.setdefault(axis, {})[member] = (label, val - prev_ytd[axis][member][1])
    return out


def year_values(facts, end):
    """axis -> member -> value for the fiscal year ending `end`."""
    out = {}
    for axis, member, label, start, e, val in facts:
        if e == end and 350 <= _span(start, e) <= 380:
            out.setdefault(axis, {})[member] = (label, val)
    return out


def ytd_values(facts, end):
    out = {}
    for axis, member, label, start, e, val in facts:
        if e == end and _span(start, e) > 250:
            out.setdefault(axis, {})[member] = (label, val)
    return out


# members that are no revenue line: the total itself, or per-share rows that slip onto the axis (Interactive Brokers:
# "Basic" and "Diluted" beside "Revenues"); a member below the tolerance cannot be told from rounding either
NOT_LINES = {"basic", "diluted", "revenues", "revenue", "total revenues", "total revenue", "total", "net revenues"}
NOT_A_LINE = re.compile(r"\bper\b.*\bshare\b|\bper unit\b|\bdividend|\bweighted\b|\beps\b|^segment total$|^total (?:reportable )?segments$|^reportable segments total$")    # per-share rows (Tractor Supply's
# a member that is itself a subtotal of other members (ASU 2023-07's "all reportable segments" aggregation: Chevron's
# ReportableSegmentAggregationBeforeOtherOperatingSegmentMember, "Segment Total"): never a revenue line
AGGREGATE_ID = re.compile(r"Aggregation|SegmentTotal|TotalSegments|TotalReportableSegment", re.I)
                                                                                               # "dividends declared per common share")


def tight(err, n, unit, ref):
    """Within the rounding of n figures printed to `unit` (half a unit each, and the total's own), capped at TOL."""
    return unit is not None and err <= min(0.5 * unit * (n + 1), TOL * abs(ref))


def best_partition(members, total, unit=None):
    """Largest set of members adding up to total, plus groups = other members equal to a subset of it.

    unit (the rounding of figures read from a table, e.g. 1e6 for "in millions"): a set that adds up to the total
    within that rounding beats any set that only comes within TOL. With many lines from one table a loose match is
    often a coincidence: Apple's Q4 FY26 release, where six region and product lines plus Services came within 0.075%
    of total net sales while the real breakdowns add up exactly. Without unit (XBRL members) the rule is unchanged."""
    # lines under TOL of the total are left out (slivers) — except when figures from a table are matched to its
    # rounding (unit): then a small line is what makes the sum exact (Vertex: a new drug's first $10M)
    floor = unit if unit is not None else TOL * abs(total)
    items = [(m, lab, v) for m, (lab, v) in members.items()
             if v >= floor and v > 0 and str(lab or "").strip().lower() not in NOT_LINES
             and not NOT_A_LINE.search(str(lab or "").lower()) and not AGGREGATE_ID.search(str(m or ""))]
    items.sort(key=lambda x: -x[2])
    items = items[:14]
    best = None
    n = len(items)
    for mask in range(1, 1 << n):
        s = sum(items[i][2] for i in range(n) if mask >> i & 1)
        if abs(s - total) <= TOL * abs(total):
            size = bin(mask).count("1")
            key = (size >= 2 and tight(abs(s - total), size, unit, total), size, -abs(s - total) if unit is not None else 0)
            if best is None or key > best[0]:
                best = (key, mask)
    if not best or best[0][1] < 2:
        return None
    leaves = [items[i] for i in range(n) if best[1] >> i & 1]
    rest = [items[i] for i in range(n) if not best[1] >> i & 1]
    groups = []
    used = set()
    for gm, glab, gv in sorted(rest, key=lambda x: -x[2]):
        cand = [l for l in leaves if l[0] not in used]
        k = len(cand)
        for mask in range(1, 1 << k):
            sub = [cand[i] for i in range(k) if mask >> i & 1]
            err = abs(sum(x[2] for x in sub) - gv)
            if 2 <= len(sub) < len(leaves) and (tight(err, len(sub), unit, gv) if unit is not None else err <= TOL * gv):
                groups.append({"id": gm, "label": glab, "members": [x[0] for x in sub]})
                used.update(x[0] for x in sub)
                break
    return {"leaves": [{"id": m, "label": lab} for m, lab, _ in leaves], "groups": groups}


def revenue_lines(member_vals, total):
    """Pick the most detailed breakdown that adds up to total revenue."""
    best = None
    for axis in AXES:
        part = best_partition(member_vals.get(axis, {}), total) if total else None
        if part and (best is None or len(part["leaves"]) > len(best["leaves"])):
            part["axis"] = axis
            best = part
    return best


RECON = {"label": "Revenue from contracts with customers"}
# lines that add up to neither total revenue nor contract revenue (found when a stored quarter is read again): hidden
# by default, drawn with the difference as its own line for readers who ask for it (Alerts)
UNMATCHED = {"label": "Sum of the revenue lines", "unmatched": True}


def revenue_lines_for(member_vals, raw):
    """revenue_lines against total revenue; failing that, against revenue from contracts with customers when that
    differs from the total (Vistra: lines add up to $4.40B of contract revenue; other revenues of −$0.38B, hedging
    results, make the $4.02B total). Then the breakdown carries "recon" and the chart draws the difference."""
    R = raw.get("revenue")
    ls = revenue_lines(member_vals, R)
    if ls:
        return ls
    C = raw.get("rev_contract")
    if R and C and abs(C - R) > TOL * abs(R):
        ls = revenue_lines(member_vals, C)
        if ls:
            ls["recon"] = dict(RECON)
    return ls

