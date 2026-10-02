"""Build offline SEC fixtures from figures verified against the filings (see tests/README.md).

Figures are in $ millions as printed in each company's 10-Q / earnings release; they are stored in
dollars like real companyfacts. Run:  python tests/make_fixtures.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SEC_FIXTURES"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
from pipeline import sec  # noqa: E402

OUT = os.environ["SEC_FIXTURES"]
os.makedirs(OUT, exist_ok=True)
M = 1_000_000


def put(url, body):
    path = sec._fixture_path(url)
    with open(path, "w") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))


def facts_json(cik, name, periods):
    """periods: list of (start, end, accn, form, filed, {concept: value_in_millions})"""
    gaap = {}
    for start, end, accn, form, filed, vals in periods:
        for concept, v in vals.items():
            gaap.setdefault(concept, {"label": concept, "units": {"USD": []}})["units"]["USD"].append(
                {"start": start, "end": end, "val": int(round(v * M)), "accn": accn, "form": form, "filed": filed})
    return {"cik": cik, "entityName": name, "facts": {"us-gaap": gaap}}


def submissions(cik, name, tickers, sic, sic_desc, fye, rows):
    keys = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument"]
    return {"cik": str(cik), "name": name, "tickers": tickers, "exchanges": ["Nasdaq"], "sic": sic,
            "sicDescription": sic_desc, "fiscalYearEnd": fye, "stateOfIncorporation": "", "category": "Large accelerated filer",
            "filings": {"recent": {k: [r[i] for r in rows] for i, k in enumerate(keys)}}}


def atom(entries):
    body = "".join(
        f"<entry><title>{form} - {name} ({cik:010d}) (Filer)</title>"
        f"<summary type=\"html\"> &lt;b&gt;Filed:&lt;/b&gt; {filed} &lt;b&gt;AccNo:&lt;/b&gt; {accn}</summary>"
        f"<updated>{filed}T16:05:00-04:00</updated><category scheme=\"https://www.sec.gov/\" label=\"form type\" term=\"{form}\"/>"
        f"<id>urn:tag:sec.gov,2008:accession-number={accn}</id></entry>"
        for form, name, cik, accn, filed in entries)
    return f'<?xml version="1.0" encoding="ISO-8859-1" ?><feed xmlns="http://www.w3.org/2005/Atom">{body}</feed>'


def instance(prefix, contexts, facts_):
    """contexts: id -> (start, end, (axis, member) or None); facts_: list of (concept, ctx, value_m)"""
    ctx_xml = []
    for cid, (start, end, dim) in contexts.items():
        seg = (f"<xbrli:segment><xbrldi:explicitMember dimension=\"{dim[0]}\">{dim[1]}</xbrldi:explicitMember></xbrli:segment>"
               if dim else "")
        ctx_xml.append(f"<xbrli:context id=\"{cid}\"><xbrli:entity><xbrli:identifier scheme=\"http://www.sec.gov/CIK\">0</xbrli:identifier>"
                       f"{seg}</xbrli:entity><xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>"
                       f"</xbrli:period></xbrli:context>")
    fx = "".join(f"<us-gaap:{c} contextRef=\"{cid}\" unitRef=\"usd\" decimals=\"-6\">{int(v * M)}</us-gaap:{c}>" for c, cid, v in facts_)
    return ("<?xml version=\"1.0\"?><xbrli:xbrl xmlns:xbrli=\"http://www.xbrl.org/2003/instance\" "
            "xmlns:xbrldi=\"http://xbrl.org/2006/xbrldi\" xmlns:us-gaap=\"http://fasb.org/us-gaap/2025\" "
            f"xmlns:srt=\"http://fasb.org/srt/2025\" xmlns:{prefix}=\"http://example.com/{prefix}\">"
            + "".join(ctx_xml) + fx + "</xbrli:xbrl>")


def labels(items):
    locs, labs, arcs = [], [], []
    for i, (elid, text) in enumerate(items.items()):
        locs.append(f"<link:loc xlink:type=\"locator\" xlink:href=\"x.xsd#{elid}\" xlink:label=\"loc{i}\"/>")
        labs.append(f"<link:label xlink:type=\"resource\" xlink:label=\"lab{i}\" xlink:role=\"http://www.xbrl.org/2003/role/label\">{text}</link:label>")
        arcs.append(f"<link:labelArc xlink:type=\"arc\" xlink:from=\"loc{i}\" xlink:to=\"lab{i}\"/>")
    return ("<?xml version=\"1.0\"?><link:linkbase xmlns:link=\"http://www.xbrl.org/2003/linkbase\" "
            "xmlns:xlink=\"http://www.w3.org/1999/xlink\"><link:labelLink>" + "".join(locs + labs + arcs) + "</link:labelLink></link:linkbase>")


def doc(sections):
    body = "".join(f"<div><span style=\"font-weight:700\">{h}</span></div>" + "".join(f"<div><span>{p}</span></div>" for p in ps)
                   for h, ps in sections)
    return f"<html><body>{body}</body></html>"


# ------------------------------------------------------------------ Apple (fiscal year ends late September)
AAPL = 320193
A_Q3, A_Q2 = "0000320193-26-000020", "0000320193-26-000013"
A_Q1 = "0000320193-26-000006"
IS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "CostOfGoodsAndServicesSold", "GrossProfit",
      "ResearchAndDevelopmentExpense", "SellingGeneralAndAdministrativeExpense", "OperatingExpenses", "OperatingIncomeLoss",
      "NonoperatingIncomeExpense", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
      "IncomeTaxExpenseBenefit", "NetIncomeLoss"]
a_is = {  # 10-Q statements of operations, three months
    ("2026-03-29", "2026-06-27"): [109417, 54647, 54770, 11729, 7346, 19075, 35695, 572, 36267, 6478, 29789],
    ("2025-03-30", "2025-06-28"): [94036, 50318, 43718, 8866, 6650, 15516, 28202, -171, 28031, 4597, 23434],
    ("2025-12-28", "2026-03-28"): [111184, 56403, 54781, 11419, 7477, 18896, 35885, -52, 35833, 6255, 29578],
    ("2024-12-29", "2025-03-29"): [95359, 50492, 44867, 8550, 6728, 15278, 29589, -279, 29310, 4530, 24780],
}
CF = ["NetCashProvidedByUsedInOperatingActivities", "DepreciationDepletionAndAmortization", "ShareBasedCompensation",
      "PaymentsToAcquirePropertyPlantAndEquipment"]
a_cf = {  # statements of cash flows, year-to-date
    ("2025-09-28", "2025-12-27"): [53925, 3214, 3594, 2373],
    ("2025-09-28", "2026-03-28"): [82627, 6653, 7122, 4344],
    ("2025-09-28", "2026-06-27"): [116996, 9973, 10523, 6799],
    ("2024-09-29", "2024-12-28"): [29935, 3080, 3286, 2940],
    ("2024-09-29", "2025-03-29"): [53887, 5741, 6512, 6011],
    ("2024-09-29", "2025-06-28"): [81754, 8571, 9680, 9473],
}
periods = [(s, e, A_Q3, "10-Q", "2026-07-31", dict(zip(IS, v))) for (s, e), v in a_is.items()]
periods += [(s, e, A_Q3, "10-Q", "2026-07-31", dict(zip(CF, v))) for (s, e), v in a_cf.items()]
put(sec.companyfacts_url(AAPL), facts_json(AAPL, "Apple Inc.", periods))
put(sec.submissions_url(AAPL), submissions(AAPL, "Apple Inc.", ["AAPL"], "3571", "Electronic Computers", "0927", [
    [A_Q3, "2026-07-31", "2026-06-27", "10-Q", "aapl-20260627.htm"],
    [A_Q2, "2026-05-01", "2026-03-28", "10-Q", "aapl-20260328.htm"],
    [A_Q1, "2026-01-30", "2025-12-27", "10-Q", "aapl-20251227.htm"],
]))
members = {"aapl:IPhoneMember": "iPhone", "aapl:MacMember": "Mac", "aapl:IPadMember": "iPad",
           "aapl:WearablesHomeandAccessoriesMember": "Wearables, Home and Accessories",
           "us-gaap:ServiceMember": "Services", "us-gaap:ProductMember": "Products"}
lab = labels({k.replace(":", "_"): v for k, v in members.items()})
for accn, cur, prev, vals in [
    (A_Q3, ("2026-03-29", "2026-06-27"), ("2025-03-30", "2025-06-28"),
     {"aapl:IPhoneMember": (54252, 44582), "aapl:MacMember": (10352, 8046), "aapl:IPadMember": (6191, 6581),
      "aapl:WearablesHomeandAccessoriesMember": (7883, 7404), "us-gaap:ServiceMember": (30739, 27423),
      "us-gaap:ProductMember": (78678, 66613)}),
    (A_Q2, ("2025-12-28", "2026-03-28"), ("2024-12-29", "2025-03-29"),
     {"aapl:IPhoneMember": (56994, 46841), "aapl:MacMember": (8399, 7949), "aapl:IPadMember": (6914, 6402),
      "aapl:WearablesHomeandAccessoriesMember": (7901, 7522), "us-gaap:ServiceMember": (30976, 26645),
      "us-gaap:ProductMember": (80208, 68714)})]:
    ctx, fx = {}, []
    for i, (m, (v_cur, v_prev)) in enumerate(vals.items()):
        ctx[f"c{i}"] = (*cur, ("srt:ProductOrServiceAxis", m))
        ctx[f"p{i}"] = (*prev, ("srt:ProductOrServiceAxis", m))
        fx += [("RevenueFromContractWithCustomerExcludingAssessedTax", f"c{i}", v_cur),
               ("RevenueFromContractWithCustomerExcludingAssessedTax", f"p{i}", v_prev)]
    base = accn.replace("-", "")
    stem = "aapl-20260627" if accn == A_Q3 else "aapl-20260328"
    put(sec.doc_url(AAPL, accn, f"{stem}_htm.xml"), instance("aapl", ctx, fx))
    put(sec.doc_url(AAPL, accn, f"{stem}_lab.xml"), lab)
    put(sec.filing_index_url(AAPL, accn), {"directory": {"item": [{"name": f"{stem}.htm"}, {"name": f"{stem}_htm.xml"},
                                                                    {"name": f"{stem}_lab.xml"}]}})
# MD&A excerpts quoted verbatim from Apple's Q3 and Q2 FY26 Forms 10-Q
q3_mdna = [
    ("iPhone", ["iPhone net sales increased during the third quarter and first nine months of 2026 compared to the same periods in 2025 primarily due to higher net sales of Pro models."]),
    ("Mac", ["Mac net sales increased during the third quarter and first nine months of 2026 compared to the same periods in 2025 due to higher net sales of laptops."]),
    ("iPad", ["iPad net sales decreased during the third quarter of 2026 compared to the third quarter of 2025 primarily due to lower net sales of iPad mini® and iPad Air®. Year-over-year iPad net sales increased during the first nine months of 2026 primarily due to higher net sales of iPad, partially offset by lower net sales of iPad mini."]),
    ("Wearables, Home and Accessories", ["Wearables, Home and Accessories net sales increased during the third quarter and first nine months of 2026 compared to the same periods in 2025 due to higher net sales of Accessories and Wearables."]),
    ("Services", ["Services net sales increased during the third quarter and first nine months of 2026 compared to the same periods in 2025 primarily due to higher net sales from advertising and cloud services."]),
]
q2_mdna = [
    ("iPhone", ["iPhone net sales increased during the second quarter and first six months of 2026 compared to the same periods in 2025 due to higher net sales of Pro models."]),
    ("Mac", ["Mac net sales increased during the second quarter of 2026 compared to the second quarter of 2025 due to higher net sales of laptops. Year-over-year Mac net sales during the first six months of 2026 were relatively flat."]),
    ("iPad", ["iPad net sales increased during the second quarter and first six months of 2026 compared to the same periods in 2025 primarily due to higher net sales of iPad, partially offset by lower net sales of iPad mini®."]),
    ("Wearables, Home and Accessories", ["Wearables, Home and Accessories net sales increased during the second quarter of 2026 compared to the second quarter of 2025 primarily due to higher net sales of Accessories and Wearables. Year-over-year Wearables, Home and Accessories net sales during the first six months of 2026 were relatively flat."]),
    ("Services", ["Services net sales increased during the second quarter and first six months of 2026 compared to the same periods in 2025 primarily due to higher net sales from advertising, the App Store® and cloud services."]),
]
for accn, stem, sections in [(A_Q3, "aapl-20260627", q3_mdna), (A_Q2, "aapl-20260328", q2_mdna)]:
    put(sec.doc_url(AAPL, accn, f"{stem}.htm"), doc(
        [("Item 2. Management’s Discussion and Analysis of Financial Condition and Results of Operations", []),
         ("Products and Services Performance", [])]
        + sections + [("Item 3. Quantitative and Qualitative Disclosures About Market Risk", [])]))

# ------------------------------------------------------------------ Meta (calendar year; quarterly statements from the earnings releases)
META, M_Q2 = 1326801, "0001628280-26-050705"
m_cols = ["Revenues", "CostOfRevenue", "ResearchAndDevelopmentExpense", "SellingAndMarketingExpense",
          "GeneralAndAdministrativeExpense", "CostsAndExpenses", "OperatingIncomeLoss", "NonoperatingIncomeExpense",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeTaxExpenseBenefit", "NetIncomeLoss"] + CF
m_vals = {
    ("2026-04-01", "2026-06-30"): [60801, 11330, 21656, 3431, 5609, 42026, 18775, -19, 18756, 2908, 15848, 31862, 6356, 7658, 30116],
    ("2026-01-01", "2026-03-31"): [56311, 10218, 17699, 2908, 2614, 33439, 22872, -1120, 21752, -5021, 26773, 32226, 5999, 6032, 18997],
    ("2025-04-01", "2025-06-30"): [47516, 8491, 12942, 2979, 2663, 27075, 20441, 93, 20534, 2197, 18337, 25561, 4342, 4834, 16538],
}
put(sec.companyfacts_url(META), facts_json(META, "Meta Platforms, Inc.",
    [(s, e, M_Q2, "10-Q", "2026-07-30", dict(zip(m_cols, v))) for (s, e), v in m_vals.items()]))
put(sec.submissions_url(META), submissions(META, "Meta Platforms, Inc.", ["META"], "7370",
    "Services-Computer Programming, Data Processing, Etc.", "1231", [[M_Q2, "2026-07-30", "2026-06-30", "10-Q", "meta-20260630.htm"]]))
seg = {"meta:FamilyOfAppsMember": ("Family of Apps", 60370, 47146), "meta:RealityLabsMember": ("Reality Labs", 431, 370)}
ctx, fx = {}, []
for i, (m, (_, a, b)) in enumerate(seg.items()):
    ctx[f"c{i}"] = ("2026-04-01", "2026-06-30", ("us-gaap:StatementBusinessSegmentsAxis", m))
    ctx[f"p{i}"] = ("2025-04-01", "2025-06-30", ("us-gaap:StatementBusinessSegmentsAxis", m))
    fx += [("Revenues", f"c{i}", a), ("Revenues", f"p{i}", b)]
put(sec.doc_url(META, M_Q2, "meta-20260630_htm.xml"), instance("meta", ctx, fx))
put(sec.doc_url(META, M_Q2, "meta-20260630_lab.xml"), labels({k.replace(":", "_"): v[0] for k, v in seg.items()}))
put(sec.filing_index_url(META, M_Q2), {"directory": {"item": [{"name": "meta-20260630_htm.xml"}, {"name": "meta-20260630_lab.xml"}]}})

# ------------------------------------------------------------------ CoreWeave (loss-making; custom tag for technology & infrastructure)
CRWV, C_Q2 = 1769628, "0001769628-26-900001"          # placeholder accession for the offline test
c_is = ["Revenues", "CostOfRevenue", "SellingAndMarketingExpense", "GeneralAndAdministrativeExpense", "OperatingExpenses",
        "OperatingIncomeLoss", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeTaxExpenseBenefit", "NetIncomeLoss"]
c_vals = {
    ("2026-04-01", "2026-06-30"): [2575, 879, 60, 178, 2624, -49, -564, 62, -626],
    ("2026-01-01", "2026-03-31"): [2078, 716, 69, 164, 2222, -144, -656, 84, -740],
    ("2025-04-01", "2025-06-30"): [1212, 313, 36, 174, 1193, 19, -242, 48, -290],
}
c_cf = {("2026-01-01", "2026-03-31"): [2984, 1147, 153], ("2026-01-01", "2026-06-30"): [3663, 2540, 318],
        ("2025-01-01", "2025-03-31"): [61, 443, 184], ("2025-01-01", "2025-06-30"): [-190, 1003, 329]}
cp = [(s, e, C_Q2, "10-Q", "2026-08-12", dict(zip(c_is, v))) for (s, e), v in c_vals.items()]
cp += [(s, e, C_Q2, "10-Q", "2026-08-12", dict(zip(CF[:3], v))) for (s, e), v in c_cf.items()]
put(sec.companyfacts_url(CRWV), facts_json(CRWV, "CoreWeave, Inc.", cp))
put(sec.submissions_url(CRWV), submissions(CRWV, "CoreWeave, Inc.", ["CRWV"], "7374",
    "Services-Computer Processing & Data Preparation", "1231", [[C_Q2, "2026-08-12", "2026-06-30", "10-Q", "crwv-20260630.htm"]]))

# ------------------------------------------------------------------ Berkshire Hathaway (no operating-income tag; minority interests)
BRK, B_Q2 = 1067983, "0001193125-26-900002"          # placeholder accession for the offline test
b_cols = ["Revenues", "CostsAndExpenses", "CostOfGoodsAndServicesSold", "SellingGeneralAndAdministrativeExpense",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeTaxExpenseBenefit", "ProfitLoss", "NetIncomeLoss", "NetIncomeLossAttributableToNoncontrollingInterest"]
b_vals = {
    ("2026-04-01", "2026-06-30"): [101808, 86070, 45947, 6724, 32063, 6291, 25772, 25667, 105],
    ("2026-01-01", "2026-03-31"): [93675, 79927, 41207, 6556, 12319, 2140, 10179, 10106, 73],
    ("2025-04-01", "2025-06-30"): [92515, 79384, 39616, 7931, 14750, 2293, 12457, 12370, 87],
}
b_cf = {("2026-01-01", "2026-03-31"): [10438, 3510], ("2026-01-01", "2026-06-30"): [21653, 7116],
        ("2025-01-01", "2025-03-31"): [10903, 3265], ("2025-01-01", "2025-06-30"): [20988, 6594]}
bp = [(s, e, B_Q2, "10-Q", "2026-08-03", dict(zip(b_cols, v))) for (s, e), v in b_vals.items()]
bp += [(s, e, B_Q2, "10-Q", "2026-08-03", dict(zip(CF[:2], v))) for (s, e), v in b_cf.items()]
put(sec.companyfacts_url(BRK), facts_json(BRK, "Berkshire Hathaway Inc.", bp))
put(sec.submissions_url(BRK), submissions(BRK, "Berkshire Hathaway Inc.", ["BRK-B", "BRK-A"], "6331",
    "Fire, Marine & Casualty Insurance", "1231", [[B_Q2, "2026-08-03", "2026-06-30", "10-Q", "brka-20260630.htm"]]))

# ------------------------------------------------------------------ feeds and ticker map
put(sec.current_feed_url("10-Q", 0), atom([
    ("10-Q", "CoreWeave, Inc.", CRWV, C_Q2, "2026-08-12"), ("10-Q", "Berkshire Hathaway Inc.", BRK, B_Q2, "2026-08-03"),
    ("10-Q", "Apple Inc.", AAPL, A_Q3, "2026-07-31"), ("10-Q", "Meta Platforms, Inc.", META, M_Q2, "2026-07-30")]))
put(sec.current_feed_url("10-K", 0), atom([]))
put("https://www.sec.gov/files/company_tickers.json", {
    "0": {"cik_str": AAPL, "ticker": "AAPL", "title": "Apple Inc."}, "1": {"cik_str": META, "ticker": "META", "title": "Meta"},
    "2": {"cik_str": CRWV, "ticker": "CRWV", "title": "CoreWeave"}, "3": {"cik_str": BRK, "ticker": "BRK-B", "title": "Berkshire"}})
print("fixtures written to", OUT)
