"""A filing's own XBRL instance read as SEC company facts, for a 10-Q or 10-K that SEC's companyfacts API lacks.

SEC's company facts (data.sec.gov/api/xbrl/companyfacts) is where every chart's figures come from. For some filers it
stops taking in new filings: Verisk's, Humana's, Duke Energy's, Qorvo's and Avis Budget's Q2 2026 10-Qs (filed late
July) were still not in it in November, so the scan waited for them ("XBRL facts not available yet") and after a day
gave up — 465 filings of 249 companies by Nov 2 2026, their pages left on an older quarter or on the preliminary
figures of an earnings release. The filing's instance (<name>_htm.xml beside it on EDGAR) holds the same facts; here
they are put in company-facts form (only facts without dimensions, as company facts has them), tagged with the
filing's accession number, form and date, and merged with what company facts has for the earlier periods.
"""
import xml.etree.ElementTree as ET

TAXONOMIES = (("fasb.org/us-gaap", "us-gaap"), ("ifrs.org/taxonomy", "ifrs-full"), ("xbrl.sec.gov/dei", "dei"))
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"


def _local(tag):
    return tag.split("}")[-1]


def _ns(tag):
    return tag[1:].split("}")[0] if tag.startswith("{") else ""


def _measure(text):
    """iso4217:USD → USD, xbrli:shares → shares, xbrli:pure → pure."""
    return (text or "").strip().split(":")[-1]


def to_companyfacts(xml_text, accn, form, filed):
    """{"facts": {taxonomy: {concept: {"label": None, "units": {unit: [fact, …]}}}}} from an instance document."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    contexts, units = {}, {}
    for el in root:
        name = _local(el.tag)
        if name == "context":
            start = end = None
            dims = False
            for x in el.iter():
                n = _local(x.tag)
                if n in ("explicitMember", "typedMember"):
                    dims = True
                elif n == "startDate":
                    start = (x.text or "").strip()
                elif n in ("endDate", "instant"):
                    end = (x.text or "").strip()
            if end and not dims:
                contexts[el.get("id")] = (start, end)
        elif name == "unit":
            num = [_measure(m.text) for m in el.iter() if _local(m.tag) == "measure"]
            div = [x for x in el.iter() if _local(x.tag) == "divide"]
            if div and len(num) == 2:
                units[el.get("id")] = f"{num[0]}/{num[1]}"
            elif num:
                units[el.get("id")] = num[0]
    out, seen = {}, set()
    for el in root:
        ctx = el.get("contextRef")
        if ctx not in contexts or el.get(XSI_NIL) == "true":
            continue
        tax = next((t for k, t in TAXONOMIES if k in _ns(el.tag)), None)
        if not tax:
            continue
        try:
            val = float((el.text or "").strip())
        except ValueError:
            continue
        start, end = contexts[ctx]
        unit = units.get(el.get("unitRef"), "pure")
        concept = _local(el.tag)
        key = (tax, concept, unit, start, end, val)
        if key in seen:
            continue
        seen.add(key)
        f = {"end": end, "val": int(val) if val.is_integer() else val, "accn": accn, "form": form, "filed": filed}
        if start:
            f["start"] = start
        body = out.setdefault(tax, {}).setdefault(concept, {"label": None, "units": {}})
        body["units"].setdefault(unit, []).append(f)
    return {"facts": out}


def merge(companyfacts, extra):
    """extra's facts added to companyfacts (in place); returns the number added."""
    n = 0
    facts = companyfacts.setdefault("facts", {})
    for tax, concepts in (extra.get("facts") or {}).items():
        for concept, body in concepts.items():
            have = facts.setdefault(tax, {}).setdefault(concept, {"label": body.get("label"), "units": {}})
            for unit, fs in body["units"].items():
                have.setdefault("units", {}).setdefault(unit, []).extend(fs)
                n += len(fs)
    return n
