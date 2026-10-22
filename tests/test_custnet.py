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


def test_several_names_without_respectively_share_one_combined_figure():
    rec = {"s": [{"t": "McKesson Corporation, Cencora, Inc. and Cardinal Health, Inc. together accounted for 89% of our gross product sales.", "k": "sell"}], "x": []}
    ls = N.links_from(rec, names(), 9999)
    assert {l["cik"] for l in ls} == {927653, 1140859, 721371}
    assert all(l["pct"] is None and l["combined"] == 0.89 for l in ls)
