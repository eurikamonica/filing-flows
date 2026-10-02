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


def parse_labels(xml_text):
    """element id (e.g. 'aapl_IPhoneMember') -> preferred label."""
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
    out = {}
    for frm, to in arcs:
        elid = loc.get(frm)
        labels = dict(lab_by_res.get(to, []))
        text = (labels.get("http://www.xbrl.org/2003/role/terseLabel") or labels.get("http://www.xbrl.org/2003/role/label")
                or next(iter(labels.values()), ""))
        if elid and text:
            out[elid] = re.sub(r"\s*\[Member\]$", "", text)
    return out


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


def ytd_values(facts, end):
    out = {}
    for axis, member, label, start, e, val in facts:
        if e == end and _span(start, e) > 250:
            out.setdefault(axis, {})[member] = (label, val)
    return out


def best_partition(members, total):
    """Largest set of members adding up to total, plus groups = other members equal to a subset of it."""
    items = [(m, lab, v) for m, (lab, v) in members.items() if v > 0]
    items.sort(key=lambda x: -x[2])
    items = items[:14]
    best = None
    n = len(items)
    for mask in range(1, 1 << n):
        s = sum(items[i][2] for i in range(n) if mask >> i & 1)
        if abs(s - total) <= TOL * abs(total):
            size = bin(mask).count("1")
            if best is None or size > best[0]:
                best = (size, mask)
    if not best or best[0] < 2:
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
            if 2 <= len(sub) < len(leaves) and abs(sum(x[2] for x in sub) - gv) <= TOL * gv:
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
