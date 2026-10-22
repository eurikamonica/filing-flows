from pipeline import custnet as N

ROWS = [[320193, "AAPL", "Apple Inc."], [104169, "WMT", "Walmart Inc."], [27419, "TGT", "TARGET CORP"],
        [1018724, "AMZN", "AMAZON COM INC"], [789019, "MSFT", "MICROSOFT CORP"], [1652044, "GOOGL", "Alphabet Inc."],
        [354950, "HD", "HOME DEPOT, INC."], [60667, "LOW", "LOWE'S COMPANIES INC"], [927653, "MCK", "MCKESSON CORP"],
        [1140859, "COR", "Cencora, Inc."], [721371, "CAH", "CARDINAL HEALTH INC"], [1046179, "TSM", "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD"],
        [1111, "SKWK", "Skyworks Solutions, Inc."], [2222, "GNRL", "General Inc."], [3333, "BEST", "Best Corp"]]


def names():
    return N.Names(ROWS)


DOC = """<html><body>
<ix:header><div>Hidden Walmart Inc. accounted for 99% of everything</div></ix:header>
<p>Sales to Walmart Inc. and its affiliates accounted for approximately 16%, 17% and 18% of our net sales in fiscal 2025,
2024 and 2023, respectively. Our target market is broad and includes general merchandise retailers.</p>
<p>Sales to The Home Depot and Lowe&#8217;s represented 22% and 11% of net sales, respectively.</p>
<p>Revenue increased 12% to $4.2 billion compared with the prior year, driven by sales growth.</p>
<p>Amazon accounted for 14% of accounts receivable as of December 31, 2025.</p>
<p>We rely on TSMC to manufacture substantially all of our wafers, and purchases from TSMC accounted for 41% of our total purchases.</p>
<p>The U.S. Government accounted for 12% of our revenues in 2025.</p>
<p>Major customers</p>
<table><tr><td>Customer</td><td>2025</td><td>2024</td></tr>
<tr><td>Apple Inc.</td><td>23</td><td>%</td><td>20</td><td>%</td></tr>
<tr><td>Customer B</td><td>11</td><td>%</td><td>9</td><td>%</td></tr></table>
</body></html>"""


def test_sentences_keep_customer_and_supplier_statements():
    s = N.sentences(DOC)
    texts = " ".join(x["t"] for x in s)
    assert "99%" not in texts                                   # the hidden iXBRL header is not text
    assert any(x["k"] == "row" and x["t"].startswith("Apple Inc.") for x in s)
    assert any(x["k"] == "buy" and "TSMC" in x["t"] for x in s)
    assert not any("Revenue increased 12%" in x["t"] for x in s)


def test_links_name_the_counterparties_with_their_shares():
    rec = {"s": N.sentences(DOC), "x": [{"l": "Customer A", "pct": 0.16}, {"l": "Customer B", "pct": 0.11}]}
    ls = N.links_from(rec, names(), 9999)
    by = {(l["dir"], l["label"]): l for l in ls if l["label"]}
    wmt = next(l for l in ls if l["cik"] == 104169)
    assert abs(wmt["pct"] - 0.16) < 1e-9 and wmt["dir"] == "sell" and wmt.get("xbrl")
    hd = next(l for l in ls if l["cik"] == 354950)
    low = next(l for l in ls if l["cik"] == 60667)
    assert abs(hd["pct"] - 0.22) < 1e-9 and abs(low["pct"] - 0.11) < 1e-9
    assert not any(l["cik"] == 27419 for l in ls)               # "our target market" is not Target
    amzn = next(l for l in ls if l["cik"] == 1018724)
    assert amzn["pct"] is None and amzn["how"] == "receivables"
    tsm = next(l for l in ls if l["cik"] == 1046179)
    assert tsm["dir"] == "buy" and abs(tsm["pct"] - 0.41) < 1e-9
    gov = by[("sell", "U.S. government")]
    assert abs(gov["pct"] - 0.12) < 1e-9 and gov["cik"] is None
    aapl = next(l for l in ls if l["cik"] == 320193)
    assert abs(aapl["pct"] - 0.23) < 1e-9 and aapl["how"] == "customer table"
    # Customer B's 11% stays an unnamed share once (Lowe's has a stated 11% too, so it is matched, not duplicated)
    assert sum(1 for l in ls if l["label"] is None) <= 1


def test_the_filer_itself_and_common_words_are_not_customers():
    nm = names()
    rec = {"s": [{"t": "Sales of Walmart Inc. products to Best Buy and General accounted for 30% of our revenue.", "k": "sell"}], "x": []}
    ls = N.links_from(rec, nm, 104169)
    assert not any(l["cik"] == 104169 for l in ls)
    assert not any(l["cik"] in (2222, 3333) for l in ls)        # "General", "Best" alone are words, not names
    assert nm.resolve("Customer A") == (None, None)
    assert nm.resolve("Walmart Inc. [Member]")[0] == 104169
    assert nm.resolve("Google LLC")[0] == 1652044


REAL = [   # sentences from 2025 annual reports, and what they must (not) give
    ("Walmart Inc. accounted for approximately 18.7 % of our fiscal 2025 consolidated sales.", [(104169, 0.187, "sell")]),
    ("Sales of Apple Inc. products and services comprised approximately 12%, 12% , and 11% of our total revenue for fiscal "
     "years 2025, 2024, and 2023, respectively.", [(320193, None, "buy")]),
    ("Depending on the aircraft model, airline customers may have a choice between our engines and those of other "
     "manufacturers or, as in the case of some Apple models, our engines may be the sole source engine.", []),
    ("For the year ended December 31, 2025, our Medicaid, Commercial, Medicare and Other segments accounted for 57%, 21%, "
     "19% and 3%, respectively, of our total external revenues.", []),
    ("Sales to OptumRx generated 17 percent of our consolidated revenue in fiscal 2023.", []),
    ("Collins’ largest commercial customers are Apple and Walmart with combined sales of 16%, 16%, and 19% of total "
     "Collins segment sales in 2025, 2024, and 2023, respectively.", [(320193, None, "sell"), (104169, None, "sell")]),
    ("We are the fourth largest card network based on purchase volume, behind Visa, China UnionPay and Mastercard.", []),
]


def test_real_sentences():
    nm = N.Names(ROWS + [[731766, "UNH", "UNITEDHEALTH GROUP INC"]])
    for text, want in REAL:
        k = "sell"
        ls = [l for l in N.links_from({"s": [{"t": text, "k": k}], "x": [], "fy": "2025-12-31"}, nm, 9999) if l["label"]]
        got = sorted((l["cik"], l["pct"], l["dir"]) for l in ls)
        assert got == sorted(want), (text[:60], got)


def test_subsidiary_shares_have_no_company_dollars():
    nm = names()
    t = "McLane’s major customers during 2025 included Walmart (approximately 17.2% of revenues); Target Corp (approximately 13.3% of revenues)."
    ls = N.links_from({"s": [{"t": t, "k": "sell"}], "x": [], "fy": "2025-12-31"}, nm, 9999)
    by = {l["cik"]: l for l in ls}
    assert by[104169]["pct"] == 0.172 and by[27419]["pct"] == 0.133 and by[104169]["unit"] == "McLane"


def test_several_names_without_respectively_share_one_combined_figure():
    rec = {"s": [{"t": "McKesson Corporation, Cencora, Inc. and Cardinal Health, Inc. together accounted for 89% of our gross product sales.", "k": "sell"}], "x": []}
    ls = N.links_from(rec, names(), 9999)
    assert {l["cik"] for l in ls} == {927653, 1140859, 721371}
    assert all(l["pct"] is None and l["combined"] == 0.89 for l in ls)


def test_concept_basket_gathers_one_customer_across_members(tmp_path):
    import json

    class Store:
        def company(self, cik):
            return {"years": {"2025-12-31": {"raw": {"revenue": 1e9}}}}
    nm = N.Names([[1, "AAA", "Aaa Corp"], [2, "BBB", "Bbb Corp"], [104169, "WMT", "Walmart Inc."]])
    node = lambda cik, label=None: {"cik": cik, "t": nm.ticker.get(cik), "name": nm.title.get(cik) or label}
    flows = [{"s": 1, "c": 104169, "label": "Walmart", "usd": 2e8, "pct": 0.2, "how": "sentence", "dir": "sell"},
             {"s": 2, "c": 104169, "label": "Walmart", "usd": 3e8, "pct": 0.3, "how": "sentence", "dir": "sell"},
             {"s": 9, "c": 7, "label": "x", "usd": 1e8, "dir": "sell", "how": "sentence"}]
    cfg = {"chains": [{"id": "t", "name": "T", "layers": [{"id": "l", "members": [{"t": "AAA"}, {"t": "BBB"}]}]}]}
    N.concepts(Store(), str(tmp_path), flows, node, nm, cfg)
    d = json.loads((tmp_path / "network" / "x" / "t.json").read_text())
    assert len(d["links"]) == 2 and {l["c"]["cik"] for l in d["links"]} == {104169}
    assert d["revenue"] == 2e9 and all(m["linked"] for m in d["members"])
