"""Supply chains (pipeline/chains.py, pipeline/xfacts.py): run with `python -m pytest tests/test_chains.py`."""
import json
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import chains, xfacts  # noqa: E402

NS = ('xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
      'xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:srt="http://fasb.org/srt/2025" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
      'xmlns:abc="http://abc.com/20260630"')


def ctx(cid, start=None, end=None, inst=None, dims=()):
    seg = ""
    if dims:
        seg = "<xbrli:segment>" + "".join(f'<xbrldi:explicitMember dimension="{a}">{m}</xbrldi:explicitMember>' for a, m in dims) + \
              "</xbrli:segment>"
    per = f"<xbrli:instant>{inst}</xbrli:instant>" if inst else f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>"
    return f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier>{seg}' \
           f'</xbrli:entity><xbrli:period>{per}</xbrli:period></xbrli:context>'


def instance(contexts, facts):
    return (f'<?xml version="1.0"?><xbrli:xbrl {NS}><xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
            '<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>'
            + "".join(contexts) + "".join(facts) + "</xbrli:xbrl>")


def fact(concept, cref, v, unit="usd"):
    return f'<{concept} contextRef="{cref}" unitRef="{unit}" decimals="-6">{v}</{concept}>'


SEG = ("us-gaap:StatementBusinessSegmentsAxis", "abc:DataCenterMember")
CUST = [("srt:MajorCustomersAxis", "abc:MicrosoftMember"), ("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerProductAndServiceBenchmarkMember"),
        ("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")]
RECV = [("srt:MajorCustomersAxis", "abc:MicrosoftMember"), ("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:AccountsReceivableMember")]
LABELS = {"abc_DataCenterMember": "Data Center", "abc_MicrosoftMember": "Microsoft Corporation"}

TENK = instance(
    [ctx("fy", "2025-01-01", "2025-12-31"), ctx("fyp", "2024-01-01", "2024-12-31"),
     ctx("fy_dc", "2025-01-01", "2025-12-31", dims=[SEG]), ctx("fyp_dc", "2024-01-01", "2024-12-31", dims=[SEG]),
     ctx("fy_ms", "2025-01-01", "2025-12-31", dims=CUST), ctx("fy_recv", "2025-01-01", "2025-12-31", inst=None, dims=RECV),
     ctx("i25", inst="2025-12-31")],
    [fact("us-gaap:Revenues", "fy", 1000e6), fact("us-gaap:Revenues", "fyp", 800e6),
     fact("us-gaap:Revenues", "fy_dc", 600e6), fact("us-gaap:Revenues", "fyp_dc", 400e6),
     fact("us-gaap:ConcentrationRiskPercentage1", "fy_ms", 0.26, "pure"), fact("us-gaap:ConcentrationRiskPercentage1", "fy_recv", 0.4, "pure"),
     fact("us-gaap:RevenueRemainingPerformanceObligation", "i25", 900e6),
     fact("us-gaap:RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability", "fy", 50e6)])
TENQ = instance(
    [ctx("ytd", "2026-01-01", "2026-06-30"), ctx("ytdp", "2025-01-01", "2025-06-30"), ctx("q", "2026-04-01", "2026-06-30"),
     ctx("ytd_dc", "2026-01-01", "2026-06-30", dims=[SEG]), ctx("ytdp_dc", "2025-01-01", "2025-06-30", dims=[SEG]),
     ctx("q_dc", "2026-04-01", "2026-06-30", dims=[SEG]), ctx("i26", inst="2026-06-30")],
    [fact("us-gaap:Revenues", "ytd", 700e6), fact("us-gaap:Revenues", "ytdp", 450e6), fact("us-gaap:Revenues", "q", 380e6),
     fact("us-gaap:Revenues", "ytd_dc", 500e6), fact("us-gaap:Revenues", "ytdp_dc", 250e6), fact("us-gaap:Revenues", "q_dc", 280e6),
     fact("us-gaap:RevenueRemainingPerformanceObligation", "i26", 1200e6)])


def test_instance_facts_and_trailing_twelve_months():
    k, q = xfacts.parse(TENK, LABELS), xfacts.parse(TENQ, LABELS)
    dc = k["axes"]["StatementBusinessSegmentsAxis"]["abc:DataCenterMember"]
    assert dc["l"] == "Data Center"
    qdc = q["axes"]["StatementBusinessSegmentsAxis"]["abc:DataCenterMember"]
    t = xfacts.ttm(dc["f"], qdc["f"])
    assert t["basis"] == "ttm" and t["end"] == "2026-06-30"
    assert abs(t["v"] - (600e6 + 500e6 - 250e6)) < 1                     # year + year to date − the same months before
    assert abs(t["yoy"] - 1.0) < 1e-9                                     # 500 vs 250 year to date
    assert t["q"] == 280e6
    cust = xfacts.customers(q, k)                                        # the 10-Q names nobody: the 10-K's list
    assert [c["l"] for c in cust] == ["Microsoft Corporation"] and cust[0]["pct"] == 0.26   # receivables left out
    assert xfacts.latest_instant(q["rpo"]) == ("2026-06-30", 1200e6)
    assert k["lease"] == [["2025-01-01", "2025-12-31", 50e6]]
    only_k = xfacts.ttm(dc["f"])
    assert only_k["basis"] == "fy" and only_k["v"] == 600e6 and abs(only_k["yoy"] - 0.5) < 1e-9


def test_ras_meets_both_totals():
    prior = {("a", "x"): 1, ("a", "y"): 1, ("b", "x"): 1, ("b", "y"): 3}
    x = chains.ras(prior, {"a": 40, "b": 60}, {"x": 30, "y": 70})
    assert abs(x[("a", "x")] + x[("b", "x")] - 30) < 1e-6 and abs(x[("a", "y")] + x[("b", "y")] - 70) < 1e-6
    assert abs(x[("a", "x")] + x[("a", "y")] - 40) < 1e-3 and abs(x[("b", "x")] + x[("b", "y")] - 60) < 1e-3
    assert x[("b", "y")] / x[("b", "x")] > x[("a", "y")] / x[("a", "x")]   # the prior's preference survives


def test_capex_outlook_sentences():
    rows = chains.capex_guidance(["We anticipate 2027 capital expenditures, including principal payments on finance leases, "
                                  "to be in the range of $150-170 billion. Revenue grew."])
    assert rows and rows[0]["lo"] == 150e9 and rows[0]["hi"] == 170e9 and rows[0]["year"] == "2027"
    assert not chains.capex_guidance(["Capital expenditures were $30 billion in the quarter."])


class FakeStore:
    def __init__(self, root, recs, ciks):
        self.root, self.recs = root, recs
        self.state = {"chain_ciks": {"t": "2026-10-01T00:00:00", "m": ciks}}

    def company(self, cik):
        return self.recs.get(int(cik), {"quarters": {}})


def quarters(values, key, extra=None):
    ends = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    return {e: {"end": e, "form": "10-Q", "raw": {key: v, **(extra or {})}} for e, v in zip(ends, values)}


def test_spend_chain_named_customer_is_fixed_and_rest_balances():
    buyer = {"profile": {"name": "Microsoft Corp", "tickers": ["MSFT"]}, "quarters": quarters([25e9] * 4, "capex")}
    supplier = {"profile": {"name": "Arista Networks Inc", "tickers": ["ANET"]},
                "quarters": quarters([2.5e9] * 4, "revenue", {"cor": 1e9}),
                "xf": {"k": xfacts.parse(TENK.replace("1000000000.0", "10000000000.0"), LABELS)}}
    other = {"profile": {"name": "Big Chips Inc", "tickers": ["CHIP"]}, "quarters": quarters([10e9] * 4, "revenue", {"cor": 3e9})}
    cfg = {"chains": [{"id": "t", "name": "Test chain", "kind": "spend", "spend": {"metric": "capex"},
                       "buyers": [{"t": "MSFT", "names": "microsoft"}],
                       "layers": [{"id": "net", "name": "Networking", "members": [{"t": "ANET", "share": 0.1}]},
                                  {"id": "chips", "name": "Chips", "members": [{"t": "CHIP", "share": 0.5}]}]}]}
    with tempfile.TemporaryDirectory() as d:
        st = FakeStore(d, {1: buyer, 2: supplier, 3: other}, {"MSFT": 1, "ANET": 2, "CHIP": 3})
        chains.build(st, d, cfg=cfg)
        doc = json.load(open(os.path.join(d, "chains", "t.json")))
    anet = next(c for c in doc["companies"] if c["t"] == "ANET")
    assert anet["attr"] == round(0.26 * 10e9)                  # Microsoft named at 26% beats the assumed 10%
    cell = next(m for m in doc["matrix"] if m["s"] == "ANET")
    assert cell["named"] and cell["v"] == round(0.26 * 10e9)
    cov = doc["coverage"]
    assert cov["spend"] == 100e9 and cov["traced"] == round(0.26 * 10e9 + 0.5 * 40e9)
    assert cov["untraced"] == cov["spend"] - cov["traced"]
    links = doc["views"]["flow"]["links"]
    assert any(l["s"] == "MSFT" and l["t"] == "_untraced" for l in links)
    net = next(l for l in links if l["s"] == "MSFT" and l["t"] == "L:net")
    assert net["k"] == 1.0                                     # stated in the filing: drawn dark
    chip = next(l for l in links if l["s"] == "MSFT" and l["t"] == "L:chips")
    assert chip["k"] == 0                                      # estimated: drawn light
    w = {x["t"]: x["cents"] for x in doc["wallet"]}
    assert abs(w["CHIP"] - 20.0) < 0.01                        # $20B of $100B
    assert "profit" in doc["views"] and "cash" in doc["views"]


def test_forecast_model_learns_the_share_and_beats_naive():
    import random
    from pipeline import chainmodel as CM
    rnd = random.Random(7)
    X, y = {}, {}
    k0 = 2019 * 4
    for i in range(30):                                   # capex grows with a wobble; the supplier books half a
        X[k0 + i] = 40 * (1.07 ** i) * (1 + 0.04 * math.sin(i))      # quarter ahead of it
    for i in range(1, 28):
        k = k0 + i
        y[k] = 5 + 0.1 * i + 0.12 * X[k + 1] + 0.08 * X[k] + rnd.gauss(0, 0.3)
    m = CM.supplier_model(y, X, beta0=0.1, profile="lead")
    assert m and abs(m["share"] - 0.20) < 0.04             # the data move the prior (0.10) to the truth (0.20)
    assert m["dataw"] > 0.5 and m["lag"] < 0.5             # mostly data; the supplier leads or moves with capex
    bt = m["bt"]
    assert bt["mape"] < bt["mape_rw"] and bt["mape"] < 0.05
    fc = CM.forecast(m, y, {**X, **{k0 + 30 + j: X[k0 + 29] * 1.05 ** (j + 1) for j in range(6)}}, [k0 + 28, k0 + 29])
    assert len(fc) == 2 and fc[0][2] < fc[0][1] < fc[0][3]


def test_buyer_path_spreads_the_guided_year():
    from pipeline import chainmodel as CM
    k = CM.cq("2026-06-30")                                # 2026 Q2
    hist = {k - 1: 30.0, k: 34.0}
    path, gy = CM.buyer_path(hist, {"year": "2026", "mid": 140.0}, "1231", k, k + 4)
    assert gy == 2026 and abs(path[k + 1] - 38.0) < 1e-9 and abs(path[k + 2] - 38.0) < 1e-9   # (140 − 64) / 2
    path2, gy2 = CM.buyer_path(hist, None, "1231", k, k + 2)
    assert gy2 is None and path2[k + 1] > 34.0             # no guidance: the damped trend


def test_region_and_product_concentrations_are_not_customers():
    geo = [("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerProductAndServiceBenchmarkMember"),
           ("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:GeographicConcentrationRiskMember"), ("srt:StatementGeographicalAxis", "country:CN")]
    one = [("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerProductAndServiceBenchmarkMember"),
           ("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")]
    doc = instance([ctx("g", "2025-01-01", "2025-12-31", dims=geo), ctx("o", "2025-01-01", "2025-12-31", dims=one),
                    ctx("all", "2025-01-01", "2025-12-31", dims=one[:1])],
                   [fact("us-gaap:ConcentrationRiskPercentage1", "g", 0.28, "pure"), fact("us-gaap:ConcentrationRiskPercentage1", "o", 0.12, "pure"),
                    fact("us-gaap:ConcentrationRiskPercentage1", "all", 1.0, "pure")])
    rows = xfacts.parse(doc, {})["cust"]
    assert [(r["l"], r["pct"]) for r in rows] == [("", 0.12)]


def test_capex_outlook_reads_paragraph_dicts():
    rows = chains.capex_guidance([{"text": "We expect fiscal 2027 capital expenditures to be approximately $120 billion.", "heading": False}])
    assert rows and rows[0]["lo"] == 120e9 and rows[0]["year"] == "2027"


def test_effective_life_is_recovered_from_reported_depreciation():
    from pipeline import capexreturn as CR
    C = {k: 10 * 1.05 ** i for i, k in enumerate(range(8000, 8032))}
    first = min(C)
    D = {k: sum(C.get(v, 0) for v in range(max(k - 24, first), k)) / 24 + 2.0 for k in range(8020, 8032)}
    L, base, rms = CR.fit_life(C, D)
    assert L == 24 and abs(base - 2.0) < 1e-6 and rms < 1e-6
    path = {8032 + i: C[8031] * 1.05 ** (i + 1) for i in range(8)}
    up, down = CR.project(C, L, base, path, 1.2, 8031), CR.project(C, L, base, path, 0.8, 8031)
    assert up[8035] > down[8035] and abs(up[8032] - down[8032]) < 1e-9   # next quarter's charge is already set


def test_capex_guidance_skips_multiyear_plans():
    from pipeline import chainmodel as CM
    from pipeline.chains import capex_guidance
    g = capex_guidance(["We expect capital expenditures of $39.5 billion over 2026-2030.",
                        "Our five-year capital plan of $60 billion includes grid hardening.",
                        "The company expects 2026 capital expenditures of $6.8 billion to $7.2 billion."])
    assert len(g) == 1 and g[0]["lo"] == 6.8e9 and g[0]["hi"] == 7.2e9 and g[0]["year"] == "2026"
    k = CM.cq("2026-06-30")
    hist = {k - 3: 1.6, k - 2: 1.6, k - 1: 1.7, k: 1.7}                 # $6.6 a year
    _, gy = CM.buyer_path(hist, {"year": "2026", "mid": 39.5}, "1231", k, k + 4)
    assert gy is None                                                  # six years' worth is not this year's guidance
