"""pipeline/investments.py: investment balances and gains from company facts, investees read from a 10-Q's XBRL and its
sentences (with the false friends real filings contain), and the pages built from both."""
import json

from pipeline import investments as I
from pipeline.custnet import Names


def fx_with(inst=None, dur=None, labels=None):
    fx = {"__instants__": {c: {d: {"val": v, "filed": "2026-11-01"} for d, v in days.items()} for c, days in (inst or {}).items()},
          "__labels__": labels or {}}
    for concept, per in (dur or {}).items():
        fx[concept] = {k: {"val": v, "filed": "2026-11-01"} for k, v in per.items()}
    return fx


Q = [("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30")]
B = 1e9


def test_balances_gains_and_their_share_of_pretax_income():
    fx = fx_with(
        inst={"EquitySecuritiesWithoutReadilyDeterminableFairValueAmount": {"2025-12-31": 16.2 * B, "2026-03-31": 48.1 * B,
                                                                           "2026-06-30": 122.3 * B, "2026-09-30": 143.7 * B},
              "EquityMethodInvestments": {"2026-09-30": 0.4 * B},
              "OtherLongTermInvestments": {"2026-09-30": 150 * B}},
        dur={"EquitySecuritiesWithoutReadilyDeterminableFairValueUpwardPriceAdjustmentAnnualAmount":
                 {Q[0]: 0.4 * B, Q[1]: 12.33 * B, ("2026-01-01", "2026-06-30"): 62.82 * B, ("2026-01-01", "2026-09-30"): 62.85 * B},
             "EquitySecuritiesFvNiGainLoss": {Q[0]: 0.86 * B, Q[1]: -0.88 * B, Q[2]: 1.30 * B, Q[3]: -0.65 * B},
             "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments":
                 {Q[0]: 26.61 * B, Q[1]: 39.83 * B, Q[2]: 80.86 * B, Q[3]: 26.87 * B}},
        labels={"EquitySecuritiesWithoutReadilyDeterminableFairValueAmount": "Equity Securities without Readily Determinable Fair Value"})
    r = I.compute(fx, "1231")
    last = r["q"][-1]
    assert last["end"] == "2026-09-30" and last["label"] == "Q3 2026"
    assert last["nm"] == 143.7 * B and last["em"] == 0.4 * B and "lt" not in last       # long-term only without nm/em
    q2 = next(x for x in r["q"] if x["end"] == "2026-06-30")
    assert abs(q2["up"] - 50.49 * B) < 1e6                       # half year less the first quarter
    assert abs(q2["g"] - (1.30 + 50.49) * B) < 1e6 and q2["gk"] == "sum"
    assert abs(r["ttm"]["pti"] - 174.17 * B) < 1e6 and abs(r["ttm"]["g"] - (0.4 + 0.86 + 11.45 + 51.79 + 0.03 - 0.65) * B) < 1e7
    assert r["src"]["nm"][1].startswith("Equity Securities without")


def test_a_company_total_wins_and_a_line_tagged_twice_counts_once():
    fx = fx_with(inst={"EquitySecuritiesWithoutReadilyDeterminableFairValueAmount": {"2026-07-26": 47.9 * B},
                       "EquitySecuritiesFvNi": {"2026-07-26": 47.9 * B}},
                 dur={"GainLossOnInvestments": {("2026-04-27", "2026-07-26"): 7.77 * B},
                      "EquitySecuritiesFvNiGainLoss": {("2026-04-27", "2026-07-26"): 2.0 * B}})
    r = I.compute(fx, "0126")
    last = r["q"][-1]
    assert last["g"] == 7.77 * B and last["gk"] == "GainLossOnInvestments"
    assert "fv" not in last                                       # NVIDIA tagged one line both ways in 2024–2025


def test_long_term_investments_stand_in_when_nothing_else_is_tagged():
    fx = fx_with(inst={"OtherLongTermInvestments": {"2026-07-31": 11.32 * B}},
                 dur={"GainLossOnInvestments": {("2026-05-01", "2026-07-31"): 2.61 * B}})
    last = I.compute(fx, "0131")["q"][-1]
    assert last["lt"] == 11.32 * B and last["g"] == 2.61 * B
    assert I.compute(fx_with(), "1231") == {"v": I.VERSION}


def test_names_keys_and_member_names():
    assert I.key_of("Anthropic, PBC") == "anthropic" == I.key_of("Anthropic")
    assert I.key_of("OpenAI Global LLC") == "openai" and I.key_of("The Coca-Cola Company") == "coca cola"
    assert I.camel("OpenAIGlobalLlcMember") == "OpenAI Global Llc"
    assert I.camel("AnthropicPBCMember") == "Anthropic PBC" and I.camel("SpaceXMember") == "SpaceX"
    me = I.own_names("AMAZON COM INC", ["AMZN"])
    assert I.clean_name("Anthropic Series G", me) == "Anthropic" and I.clean_name("OpenAI’s", me) == "OpenAI"
    assert I.clean_name("Crux AI Equity Method Joint Venture") == "Crux AI"
    for junk in ("Privately held equity securities", "AI", "VIEs", "2nm", "Mandatory", "Q3 2026", "Series C", "Firm"):
        assert I.clean_name(junk, me) is None, junk
    assert I.clean_name("Amazon Web Services", me) is None                     # the filer's own units
    assert I.clean_name("ExxonMobil", I.own_names("EXXON MOBIL CORP")) is None
    assert I.also_names(["OpenAI Global Llc"]) == ["OpenAI Global Llc", "OpenAI"]


DOC = """<html><body>
<p>During the nine months ended September 30, 2026, we invested $50.0 billion in OpenAI’s Series C Preferred Stock, including
$21.3 billion invested in Q3 2026, and $10.0 billion in Anthropic nonvoting preferred stock.</p>
<p>As of July 31, 2026, our strategic investment portfolio consisted of investments in over 450 companies with a combined carrying
value of $11.3 billion, including the Company&#8217;s investment in Anthropic PBC (&#8220;Anthropic&#8221;) which represented approximately
$5.1 billion of the total strategic investments portfolio.</p>
<p>Our income tax provision for the nine months ended September 30, 2026 was $ 33.9 billion, which included $ 15.2 billion of net
discrete tax expense primarily attributable to the upward adjustments to our investments in Anthropic.</p>
<p>Certain of our investments, including our investments in Rivian and Polymarket, represent a variable interest in entities that we do not consolidate.</p>
<p>For example, in September 2025, Nvidia announced a partnership and investment in Intel to partner on new data center products.</p>
<p>We are investing in Reels and in AI initiatives across our products, including our discovery engine.</p>
<p>Our investments in Reality Labs reduced our 2025 overall operating profit by approximately $19.19 billion.</p>
<p>In 2023, we sold our ownership interest in an equity method investee in Thailand for $ 300 million.</p>
<p>Continued Investment in Technical Infrastructure: We continue to invest in capital expenditures as we scale our technical infrastructure.</p>
<p>The following chart compares the value of $100 invested in our common stock with a similar investment in the Standard &amp; Poor&#8217;s 500 Stock Index.</p>
<p>Our revenue backlog included $ 16.8 billion associated with a commercial agreement with Crux AI, an unconsolidated equity method joint venture and a related party.</p>
<p>In addition, investment commitments included our commitment to acquire Innovator Capital Management for $2.0 billion.</p>
<table><tr><td>Anthropic</td><td>$ 5,100</td></tr></table>
</body></html>"""


def test_sentences_keep_investments_and_drop_false_friends():
    me = I.own_names("AMAZON COM INC", ["AMZN"])
    s = I.sentences(DOC, me)
    names = {n for x in s for n in x["n"]}
    assert {"OpenAI", "Anthropic", "Anthropic PBC", "Rivian", "Polymarket", "Crux AI"} <= names
    for junk in ("Intel", "Reels", "Reality Labs", "Thailand", "Technical Infrastructure", "Standard & Poor", "Innovator Capital Management"):
        assert junk not in names, junk
    amounts = {}
    for x in s:
        for k, v in (x.get("a") or {}).items():
            amounts.setdefault(k, []).extend(v)
    assert ["invested", 50e9] in amounts["openai"] and ["invested", 10e9] in amounts["anthropic"]
    assert ["value", 5.1e9] in amounts["anthropic"]
    assert not any(v in (11.3e9, 15.2e9, 33.9e9, 21.3e9) for _, v in amounts["anthropic"])   # the portfolio, tax, OpenAI's Q3
    assert "crux ai" not in amounts                                # backlog is revenue, not an investment


INST = """<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:amzn="http://www.amazon.com/20260930" xmlns:srt="http://fasb.org/srt/2025">
 <context id="a"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="srt:ScheduleOfEquityMethodInvestmentEquityMethodInvesteeNameAxis">amzn:AnthropicMember</xbrldi:explicitMember></segment></entity><period><instant>2026-09-30</instant></period></context>
 <context id="r"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="us-gaap:FairValueByMeasurementFrequencyAxis">us-gaap:FairValueMeasurementsRecurringMember</xbrldi:explicitMember></segment></entity><period><instant>2026-09-30</instant></period></context>
 <context id="b"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="dei:LegalEntityAxis">amzn:BlackstoneIncMember</xbrldi:explicitMember></segment></entity><period><instant>2026-05-31</instant></period></context>
 <context id="s"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">amzn:AWSSegmentMember</xbrldi:explicitMember></segment></entity><period><startDate>2026-07-01</startDate><endDate>2026-09-30</endDate></period></context>
 <context id="p"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="us-gaap:FinancialInstrumentAxis">amzn:PrivatelyHeldEquitySecuritiesMember</xbrldi:explicitMember></segment></entity><period><startDate>2026-07-01</startDate><endDate>2026-09-30</endDate></period></context>
 <unit id="usd"><measure>iso4217:USD</measure></unit><unit id="sh"><measure>xbrli:shares</measure></unit>
 <us-gaap:InvestmentOwnedBalanceShares contextRef="a" unitRef="sh" decimals="-6">164000000</us-gaap:InvestmentOwnedBalanceShares>
 <us-gaap:EquitySecuritiesWithoutReadilyDeterminableFairValueAmount contextRef="a" unitRef="usd" decimals="-8">20000000000</us-gaap:EquitySecuritiesWithoutReadilyDeterminableFairValueAmount>
 <us-gaap:EquitySecuritiesFvNi contextRef="r" unitRef="usd" decimals="-6">90380000000</us-gaap:EquitySecuritiesFvNi>
 <us-gaap:EquityMethodInvestmentCommittedCapitalContribution contextRef="b" unitRef="usd">5000000000</us-gaap:EquityMethodInvestmentCommittedCapitalContribution>
 <us-gaap:Revenues contextRef="s" unitRef="usd">33000000000</us-gaap:Revenues>
 <us-gaap:UnrealizedGainLossOnInvestments contextRef="p" unitRef="usd">2894000000</us-gaap:UnrealizedGainLossOnInvestments>
</xbrl>"""
LABELS = {"amzn_AnthropicMember": "Anthropic", "amzn_BlackstoneIncMember": "Blackstone Inc", "amzn_AWSSegmentMember": "AWS",
          "amzn_PrivatelyHeldEquitySecuritiesMember": "Privately held equity securities",
          "us-gaap_InvestmentOwnedBalanceShares": "Investment owned, shares"}


def test_instance_members_balances_and_segments():
    members, bal, segs = I.instance(INST, LABELS)
    by = {m["name"]: m for m in members}
    assert set(by) == {"Anthropic", "Blackstone Inc"}             # a type of security is no investee
    assert not by["Anthropic"]["weak"] and by["Blackstone Inc"]["weak"]
    assert ["InvestmentOwnedBalanceShares", "Investment owned, shares", None, "2026-09-30", 164e6, "shares"] in by["Anthropic"]["f"]
    assert bal == {"fv": {"2026-09-30": 90.38e9}} and "aws" in segs


def test_read_keeps_a_legal_entity_only_when_the_text_invests_in_it_and_names_resolve():
    rec = I.read(1018724, "0001018724-26-000040", "10-Q", "2026-10-30", "https://www.sec.gov/x.htm", DOC, INST, None,
                 "2026-09-30", I.own_names("AMAZON COM INC", ["AMZN"]))
    assert [x["name"] for x in rec["x"]] == ["Anthropic"]         # Blackstone: a co-investor, never invested in
    old = I.read(1018724, "0001018724-26-000004", "10-K", "2026-02-06", "https://www.sec.gov/k.htm",
                 "<p>The valuation loss of $(2.3) billion is primarily from our equity investment in Rivian Automotive, Inc. (“Rivian”).</p>",
                 None, None, "2025-12-31", I.own_names("AMAZON COM INC"))
    rows = [[1018724, "AMZN", "AMAZON COM INC"], [2130357, "ANT", "Anthropic, PBC"], [1874178, "RIVN", "Rivian Automotive, Inc. / DE"],
            [1181412, "SPCX", "SPACE EXPLORATION TECHNOLOGIES CORP"]]
    nm = I.named({"q": rec, "k": old}, Names(rows), 1018724)
    by = {n["key"]: n for n in nm}
    assert by["anthropic"]["cik"] == 2130357 and set(by["anthropic"]["via"]) == {"xbrl", "text"}
    assert by["anthropic"]["best"]["k"] == "value" and by["anthropic"]["best"]["how"] == "xbrl"     # the balance tagged on it
    assert by["openai"]["best"] == {"k": "invested", "usd": 50e9, "how": "text"} and "cik" not in by["openai"]
    assert "rivian" in by and by["rivian"]["cik"] == 1874178 and "rivian automotive" not in by     # one investee, two names
    assert by["openai"]["s"][0]["t"].startswith("During the nine months")          # the sentence its amount came from
    assert I._resolve(Names(rows), {"SpaceX": 1}, "spacex") == 1181412


def test_build_writes_the_ranking_the_company_pages_and_who_invested_in_what(tmp_path):
    me = I.own_names("AMAZON COM INC", ["AMZN"])
    amzn = {"profile": {"cik": 1018724, "name": "AMAZON COM INC", "tickers": ["AMZN"], "sic": 5961},
            "inv": I.compute(fx_with(inst={"EquitySecuritiesWithoutReadilyDeterminableFairValueAmount": {"2025-09-30": 16 * B, "2026-09-30": 143.7 * B}}), "1231"),
            "invr": {"q": I.read(1018724, "a1", "10-Q", "2026-10-30", "https://www.sec.gov/a.htm", DOC, None, None, "2026-09-30", me)}}
    crm = {"profile": {"cik": 1108524, "name": "Salesforce, Inc.", "tickers": ["CRM"], "sic": 7372},
           "inv": I.compute(fx_with(inst={"OtherLongTermInvestments": {"2026-07-31": 11.32 * B}}), "0131"),
           "invr": {"q": I.read(1108524, "c1", "10-Q", "2026-08-27", "https://www.sec.gov/c.htm",
                                "<p>As of July 31, 2026, the Company’s investment in Anthropic PBC represented approximately $5.1 billion of its strategic investments portfolio.</p>",
                                None, None, "2026-07-31", I.own_names("Salesforce, Inc."))}}
    bank = {"profile": {"cik": 19617, "name": "JPMORGAN CHASE & CO", "tickers": ["JPM"], "sic": 6021},
            "inv": I.compute(fx_with(inst={"EquitySecuritiesWithoutReadilyDeterminableFairValueAmount": {"2026-09-30": 8.2 * B}}), "1231")}
    recs = {1018724: amzn, 1108524: crm, 19617: bank, 1: {"profile": {"cik": 1, "name": "Nothing Inc"}}}

    class Store:
        state = {"sec_names": {"rows": [[2130357, "ANT", "Anthropic, PBC"]]}}

        def company(self, cik):
            return recs.get(int(cik), {})
    index = [{"cik": c, "ticker": (r["profile"].get("tickers") or [""])[0], "name": r["profile"]["name"]} for c, r in recs.items()]
    I.build(Store(), str(tmp_path), index, today=None)
    ix = json.loads((tmp_path / "investors" / "index.json").read_text())
    f = {k: i for i, k in enumerate(ix["fields"])}
    rows = {r[f["t"]]: r for r in ix["rows"]}
    assert set(rows) == {"AMZN", "CRM", "JPM"} and rows["JPM"][f["fin"]] == 1 and rows["AMZN"][f["fin"]] == 0
    assert rows["AMZN"][f["total"]] == 143.7 * B and rows["AMZN"][f["total_ya"]] == 16 * B
    assert rows["CRM"][f["total"]] == 11.32 * B
    assert ix["investees"][0]["key"] == "anthropic" and ix["investees"][0]["n"] == 2 and ix["investees"][0]["cik"] == 2130357
    inv = json.loads((tmp_path / "investors" / "investees.json").read_text())
    ant = next(r for r in inv["rows"] if r["key"] == "anthropic")
    assert [x["t"] for x in ant["inv"]] == ["AMZN", "CRM"]            # the larger stated amount first
    page = json.loads((tmp_path / "investors" / "c" / "1018724.json").read_text())
    assert page["q"][-1]["nm"] == 143.7 * B and {n["key"] for n in page["named"]} >= {"anthropic", "openai", "rivian", "polymarket"}
    assert not (tmp_path / "investors" / "c" / "1.json").exists()


def test_note_filing_keeps_the_newest_reading_per_kind_of_filing():
    c = {"profile": {"name": "AMAZON COM INC", "tickers": ["AMZN"]}}
    I.note_filing(c, 1018724, "10-Q", "q2", "2026-07-31", "u2", DOC, None, None, "2026-06-30")
    I.note_filing(c, 1018724, "10-Q", "q1", "2026-04-30", "u1", DOC, None, None, "2026-03-31")      # older: ignored
    I.note_filing(c, 1018724, "8-K", "e", "2026-08-01", "u3", DOC, None, None)                       # not a 10-Q/10-K
    assert c["invr"]["q"]["accn"] == "q2" and "k" not in c["invr"]
    assert I.latest_filings({"quarters": {"a": {"form": "10-Q", "accn": "x", "filed": "2026-10-30", "doc_url": "d", "end": "2026-09-30"},
                                          "b": {"form": "10-K", "accn": "y", "filed": "2026-02-06", "doc_url": "e", "end": "2025-12-31"}}}) == {
        "q": {"accn": "x", "form": "10-Q", "filed": "2026-10-30", "doc_url": "d", "end": "2026-09-30"},
        "k": {"accn": "y", "form": "10-K", "filed": "2026-02-06", "doc_url": "e", "end": "2025-12-31"}}
