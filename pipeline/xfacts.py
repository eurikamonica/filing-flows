"""Extra XBRL facts for the supply-chain pages (pipeline/chains.py), read from a filing's own XBRL instance:

  - revenue broken down along any single axis: segments, products, regions, and named customers when a company tags
    the dollars it earned from one customer (srt:MajorCustomersAxis);
  - customer-concentration percentages (us-gaap:ConcentrationRiskPercentage1 against revenue): "Microsoft accounted
    for 26% of revenue", or "Customer A 16%" when the filer keeps the name out;
  - remaining performance obligations (contracted revenue not yet recognized: backlog), at the balance-sheet date;
  - assets taken on under finance leases in the period (capex paid for over time instead of in cash).

Dimensional facts are not in SEC's companyfacts, so they come from the instance, as for dims.py. A trailing twelve
months comes from the latest 10-K's fiscal year plus the latest 10-Q's year to date minus the same months a year
earlier (both are in the 10-Q), which is how analysts compute it.
"""
import datetime as dt
import re
import xml.etree.ElementTree as ET

from .facts import CONCEPTS

VERSION = 1                     # bump when the reading changes: chain companies are read again
REV = set(CONCEPTS["revenue"])
CONC = {"ConcentrationRiskPercentage1", "ConcentrationRiskPercentage"}
RPO = {"RevenueRemainingPerformanceObligation", "ContractWithCustomerLiabilityAndRemainingPerformanceObligation"}
LEASE = {"RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability", "CapitalLeaseObligationsIncurred"}
LEASE_CUSTOM = re.compile(r"(?i)(acquired|obtained).*finance\s*lease|finance\s*lease.*(acquired|obtained)")
COMPANION = {"ConsolidationItemsAxis"}                # "operating segments" next to the real breakdown axis
SKIP_MEMBER = re.compile(r"(?i)elimination|intersegment|reconcil|corporate.?and.?other.?member$|consolidat")
BENCH_OK = re.compile(r"(?i)revenue|sales")
BENCH_NOT = re.compile(r"(?i)receivable|purchase|cost|supplier|vendor|inventor|payable|asset|deposit|loan")
KEEP_DAYS = 800                 # facts ending more than this long before the filing's period are left out
MAX_MEMBERS = 40                # per axis (a list of every country is not a breakdown anyone needs)
MAX_AXES = 14


def _local(tag):
    return tag.split("}")[-1]


def _d(s):
    return dt.date.fromisoformat(s)


def _span(s, e):
    return (_d(e) - _d(s)).days


def _num(text):
    try:
        return float((text or "").strip())
    except ValueError:
        return None


def parse(xml_text, labels=None):
    """{"end", "unit", "total": [[start, end, value]], "axes": {axis: {member: {"l": label, "f": [[start, end, v]]}}},
    "cust": [{"m", "l", "pct", "s", "e", "b"}], "rpo": [[day, v]], "lease": [[start, end, v]]}."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    labels = labels or {}
    by_local = {k.split("_", 1)[-1]: v for k, v in labels.items()}
    ctx, units = {}, {}
    for el in root:
        n = _local(el.tag)
        if n == "context":
            start = end = inst = None
            dims = []
            for x in el.iter():
                m = _local(x.tag)
                if m == "startDate":
                    start = (x.text or "").strip()
                elif m == "endDate":
                    end = (x.text or "").strip()
                elif m == "instant":
                    inst = (x.text or "").strip()
                elif m == "explicitMember":
                    dims.append((x.get("dimension", "").split(":")[-1], (x.text or "").strip()))
                elif m == "typedMember":
                    dims.append((x.get("dimension", "").split(":")[-1], "typed"))
            ctx[el.get("id")] = (start, end, inst, dims)
        elif n == "unit":
            meas = [(x.text or "").strip() for x in el.iter() if _local(x.tag) == "measure"]
            if len(meas) == 1:
                units[el.get("id")] = meas[0].split(":")[-1]
    raw_total, raw_axes, cust, rpo, lease, money_units = {}, {}, [], {}, {}, {}
    for el in root:
        cref = el.get("contextRef")
        if cref not in ctx:
            continue
        local = _local(el.tag)
        start, end, inst, dims = ctx[cref]
        is_rev = local in REV
        is_lease = local in LEASE or bool(LEASE_CUSTOM.search(local) or LEASE_CUSTOM.search(by_local.get(local, "")))
        if not (is_rev or local in CONC or local in RPO or is_lease):
            continue
        v = _num(el.text)
        if v is None:
            continue
        u = units.get(el.get("unitRef"))
        if is_rev and u:
            money_units[u] = money_units.get(u, 0) + 1
        if local in CONC:
            if not start or not end:
                continue
            dd = dict(dims)
            bench = dd.get("ConcentrationRiskByBenchmarkAxis", "")
            ctype = dd.get("ConcentrationRiskByTypeAxis", "")
            if bench and (not BENCH_OK.search(bench) or BENCH_NOT.search(bench)):
                continue
            if not bench and ctype and "Customer" not in ctype:
                continue
            who = dd.get("MajorCustomersAxis")
            if not who:
                rest = [m for a, m in dims if a not in ("ConcentrationRiskByBenchmarkAxis", "ConcentrationRiskByTypeAxis",
                                                         "StatementBusinessSegmentsAxis", "ConsolidationItemsAxis")]
                who = rest[0] if rest else ""
            pct = v / 100 if v > 1.5 else v
            if not 0 < pct <= 1:
                continue
            seg = dd.get("StatementBusinessSegmentsAxis")
            cust.append({"m": who, "l": _label(who, labels) if who else "", "pct": round(pct, 4), "s": start, "e": end,
                         "b": bench.split(":")[-1], **({"seg": _label(seg, labels)} if seg else {})})
            continue
        if local in RPO:
            if inst and not dims:
                rpo[inst] = max(rpo.get(inst, 0), v)
            continue
        if is_lease:
            if start and end and not dims:
                lease[(start, end)] = abs(v)
            continue
        if not (start and end):
            continue
        real = [(a, m) for a, m in dims if a not in COMPANION]
        if any(a in COMPANION and "Elimination" in m for a, m in dims):
            continue
        if not dims:
            key = (start, end)
            raw_total.setdefault(key, {})[local] = v
        elif len(real) == 1 and real[0][1] != "typed" and not SKIP_MEMBER.search(real[0][1]):
            a, m = real[0]
            raw_axes.setdefault(a, {}).setdefault(m, {}).setdefault((start, end), {})[local] = v
    unit = max(money_units.items(), key=lambda kv: kv[1])[0] if money_units else "USD"
    ends = [e for (s, e) in raw_total] or [e for ax in raw_axes.values() for mm in ax.values() for (s, e) in mm]
    last = max(ends) if ends else None
    keep = (lambda e: last is None or (_d(last) - _d(e)).days <= KEEP_DAYS)

    def pick(by_concept):                        # "Revenues" is the total by definition; otherwise the largest tag
        if "Revenues" in by_concept:
            return by_concept["Revenues"]
        return max(by_concept.values())

    total = sorted([s, e, pick(c)] for (s, e), c in raw_total.items() if keep(e))
    axes = {}
    for a, members in sorted(raw_axes.items(), key=lambda kv: -len(kv[1])):
        if len(members) > MAX_MEMBERS or len(axes) >= MAX_AXES:
            continue
        out = {}
        for m, per in members.items():
            f = sorted([s, e, pick(c)] for (s, e), c in per.items() if keep(e))
            if f:
                out[m] = {"l": _label(m, labels), "f": f}
        if out:
            axes[a] = out
    return {"v": VERSION, "end": last, "unit": unit, "total": total, "axes": axes,
            "cust": [c for c in cust if keep(c["e"])],
            "rpo": sorted([d, v] for d, v in rpo.items() if keep(d)),
            "lease": sorted([s, e, v] for (s, e), v in lease.items() if keep(e))}


def _label(qname, labels):
    elid = (qname or "").replace(":", "_")
    lab = labels.get(elid)
    if lab:
        return lab
    name = (qname or "").split(":")[-1]
    name = re.sub(r"Member$", "", name)
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name).strip()


# ------------------------------------------------------------------ trailing twelve months

def _near(a, b, days=12):
    return abs((_d(a) - _d(b)).days) <= days


def _minus_year(s):
    d = _d(s)
    try:
        return d.replace(year=d.year - 1).isoformat()
    except ValueError:                                 # 29 February
        return (d - dt.timedelta(days=365)).isoformat()


def ttm(*fact_lists):
    """Trailing twelve months from duration facts [[start, end, v]] (a 10-K's and a later 10-Q's, merged):
    {"v", "end", "basis": "ttm" | "fy", "yoy", "q", "q_end", "q_yoy", "fy", "fy_end"} or None. yoy compares the year to
    date (or the fiscal year) with the same months a year earlier; q is the latest three-month figure."""
    per = {}
    for fl in fact_lists:
        for s, e, v in fl or []:
            per[(s, e)] = v
    if not per:
        return None
    facts = [(s, e, v) for (s, e), v in per.items()]
    annual = sorted((x for x in facts if 350 <= _span(x[0], x[1]) <= 380), key=lambda x: x[1])
    quarters = sorted((x for x in facts if 80 <= _span(x[0], x[1]) <= 100), key=lambda x: x[1])
    out = {}
    if quarters:
        qs, qe, qv = quarters[-1]
        out.update(q=qv, q_end=qe)
        prev = next((v for s, e, v in quarters if _near(e, _minus_year(qe))), None)
        if prev:
            out["q_yoy"] = qv / prev - 1 if prev > 0 else None
    if not annual:
        if len(quarters) >= 4:                              # four quarters in a row
            last4 = quarters[-4:]
            if all(_near(last4[i][0], (_d(last4[i - 1][1]) + dt.timedelta(days=1)).isoformat(), 6) for i in range(1, 4)):
                out.update(v=sum(x[2] for x in last4), end=last4[-1][1], basis="ttm")
                return out
        return out or None
    fs, fe, fv = annual[-1]
    out.update(fy=fv, fy_end=fe)
    fy_prev = next((v for s, e, v in annual if _near(e, _minus_year(fe))), None)
    nxt = (_d(fe) + dt.timedelta(days=1)).isoformat()
    ytd = sorted((x for x in facts if _near(x[0], nxt, 7) and _d(x[1]) > _d(fe) and _span(x[0], x[1]) < 350),
                 key=lambda x: x[1])
    if ytd:
        ys, ye, yv = ytd[-1]
        prior = next((v for s, e, v in facts if _near(s, _minus_year(ys)) and _near(e, _minus_year(ye))), None)
        if prior is not None:
            out.update(v=fv + yv - prior, end=ye, basis="ttm", yoy=(yv / prior - 1) if prior > 0 else None)
            return out
    out.update(v=fv, end=fe, basis="fy", yoy=(fv / fy_prev - 1) if fy_prev and fy_prev > 0 else None)
    return out


def latest_instant(pairs):
    """[day, v] -> (day, v) of the latest."""
    return tuple(max(pairs)) if pairs else (None, None)


def customers(*parses):
    """Concentration facts of the latest period each parse has, newest filing first; one row per customer."""
    rows, seen = [], set()
    for p in parses:
        if not p or not p.get("cust"):
            continue
        last = max(c["e"] for c in p["cust"])
        cur = [c for c in p["cust"] if c["e"] == last]
        longest = max(_span(c["s"], c["e"]) for c in cur)
        for c in sorted(cur, key=lambda c: -c["pct"]):
            if _span(c["s"], c["e"]) < longest - 20:       # the year to date, not also its last quarter
                continue
            key = (c["m"] or c["l"], c.get("seg"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(c)
        if rows:
            break
    return rows
