"""Pages that promised what they did not show, or showed a dash where the site had the figure (the Nov 2026 audit of
the live pages): cut-off descriptions, a loss-maker's margin, report-card columns, guidance lines the record does not
judge, titles that name what the page has, officials' trades, and the Sankey's quarter in words."""
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo  # noqa: E402
import seo_history as H  # noqa: E402
import seo_people as P  # noqa: E402
import seo_reportcard as R  # noqa: E402
import seo_topics as T  # noqa: E402


def text(doc):
    doc = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", doc)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", doc)).replace("&#x27;", "'").replace("&amp;", "&")


def test_description_ends_with_a_whole_sentence():
    lead = ("Wealthfront (WLTH) made $96.2M of revenue in the second quarter 2026 (Q2 2026), +31% from a year earlier. Advisory fees "
            "brought in $80.1M (83%); interest on cash $14.8M (15%); brokerage $1.3M (1%). Of every dollar of revenue, 22¢ was left as "
            "operating profit, 18¢ as net earnings, and the rest went to costs and taxes over the quarter.")
    cut = lead[:300]                                                       # what the generators hand over
    assert cut.endswith(", 1") or not cut.endswith(".")
    assert seo.snippet(cut) == lead[:lead.index(" Of every dollar")]
    assert seo.snippet("A short one, fine as it is") == "A short one, fine as it is"
    long = "word " * 80
    assert seo.snippet(long).endswith("…") and len(seo.snippet(long)) <= 301
    doc = seo.page("T", ("First sentence here. " * 14)[:300], "https://x/", "<p>x</p>", 1, "https://x/og.png")
    assert re.search(r'name="description" content="[^"]*here\."', doc)


def _loss_company():
    nodes = [{"id": "revenue", "name": "Revenue", "v": 99.3e6, "q": 71.5e6, "y": 60e6}, {"id": "netloss", "v": 47.3e6}, {"id": "burn", "v": 60.8e6}]
    q = lambda lab, end, rev, oi, ni, ocf: {"label": lab, "end": end, "form": "10-Q", "filed": end, "nodes": nodes,   # noqa: E731
                                            "headline": {"revenue": rev, "yoy": 66, "oi": oi, "om": 100 * oi / rev, "ni": ni, "ocf": ocf}}
    return {"quarters": [q("Q2 2026", "2026-06-30", 99.3e6, -51.9e6, -47.3e6, -60.8e6), q("Q1 2026", "2026-03-31", 71.5e6, -80e6, -75e6, -70e6),
                         q("Q4 2025", "2025-12-31", 70e6, -90e6, -88e6, -66e6), q("Q3 2025", "2025-09-30", 67e6, -95e6, -92e6, -71e6),
                         q("Q2 2025", "2025-06-30", 60e6, -100e6, -98e6, -80e6)]}


def test_a_loss_makers_quarter_has_its_margin_lines_and_words():
    c = _loss_company()
    url, mod, doc = H.quarter_page({"cik": 1}, c, 0, "https://x", "lb", "Loss Bio (LB)", "Loss Bio", True)
    t = text(doc)
    assert "Operating margin -52.3%" in t and "Operating margin —" not in t           # from the headline: no "oi" node
    assert "Operating profit −$51.9M" in t and "Operating cash flow −$60.8M" in t
    assert "Operating loss was $51.9M" in t
    assert "Drawing the Sankey" not in doc and "Loss Bio, Q2 2026: revenue $99.3M (+66% year over year), operating margin -52.3%, net loss $47.3M" in t


def test_report_card_fills_revenue_and_moves_and_drops_empty_columns():
    days = ["2026-04-28", "2026-04-29", "2026-04-30", "2026-07-28", "2026-07-29", "2026-07-30", "2026-10-27", "2026-10-28", "2026-10-29"]
    cum = [0, 0, math.log(1.10), math.log(1.10), math.log(1.10), math.log(1.21), math.log(1.21), math.log(1.21), math.log(1.21 * 0.95)]
    spy = (days, [0] * len(days))
    assert abs(R.day_move((days, cum), spy, "2026-04-29")[0] - 0.10) < 1e-9          # the close before → the session after
    assert abs(R.day_move((days, cum), spy, "2026-10-28")[0] + 0.05) < 1e-9
    assert R.day_move((days, cum), spy, "2027-01-01") == (None, None)
    er = {"history": [{"quarter": "2026-03-31", "reported": "2026-04-29", "est": 1.0, "act": 1.1, "surprise": 0.1, "beat": 1},
                      {"quarter": "2026-06-30", "reported": "2026-07-29", "est": 1.0, "act": 0.9, "surprise": -0.1, "beat": 0, "move": 0.10},
                      {"quarter": "2026-09-30", "reported": "2026-10-28", "est": 1.0, "act": 1.2, "surprise": 0.2, "beat": 1}]}
    c = {"quarters": [{"label": "Q3 2026", "end": "2026-09-30", "headline": {"revenue": 166e6}},
                      {"label": "Q2 2026", "end": "2026-06-30", "headline": {"revenue": 114e6}},
                      {"label": "Q1 2026", "end": "2026-03-31", "headline": {"revenue": 97e6}}]}
    url, mod, doc, card = R.page_for({"name": "Riley Co", "ticker": "RCO", "cik": 1}, er, None, "https://x", "rco", c, (days, cum), spy)
    t = text(doc)
    assert "Revenue reported" in t and "$166M" in t and "$97.0M" in t
    assert "Revenue guided" not in t and "GAAP EPS" not in t                               # no report of this company fills them
    assert "+10.0%" in t and "-5.0%" in t                                                  # the moves the research had not got
    assert "Revenue reported is from the company's filing." in t
    url, mod, doc, card = R.page_for({"name": "Riley Co", "ticker": "RCO", "cik": 1}, er, None, "https://x", "rco", c, None, None)
    assert "No daily prices are on file for these report days" in text(doc) or "Stock, the day" in text(doc)


def test_guidance_history_shows_the_filings_figure_it_does_not_judge():
    rec = {"releases": 3, "since": "2024-02-13", "said": {},
           "metrics": [{"name": "Operating cash flow", "metric": "ocf", "basis": "", "unit": "usd", "hits": {"n": 0},
                        "rows": [{"label": "FY2026", "pending": True, "guides": [{"filed": "2026-02-10", "lo": 14.4e9, "hi": 14.4e9}]},
                                 {"label": "FY2024", "pending": False, "guides": [{"filed": "2024-02-13", "lo": 11.4e9, "hi": 11.4e9}]}]},
                       {"name": "Adjusted EPS", "metric": "eps", "basis": "non-GAAP", "unit": "ps", "hits": {"n": 0},
                        "rows": [{"label": "FY2024", "pending": False, "guides": [{"filed": "2024-02-13", "lo": 2.69, "hi": 2.69}]}]}]}
    c = {"years": [{"label": "FY2024", "nodes": [{"id": "ocf", "v": 6.8e9}], "headline": {"ocf": 6.8e9}}], "quarters": []}
    url, mod, doc = H.guidance_page({"cik": 1}, rec, "https://x", "ko", "Coca Cola (KO)", "Coca Cola", True, c)
    t = text(doc)
    assert "$6.8B (GAAP)" in t and "not judged" in t
    assert "it is not judged against the guide" in t
    assert "adjusted basis that the GAAP statements do not show" in t


def test_titles_name_what_the_page_has():
    f = T.forecast({"who_name": "Rocky Brands", "ticker": "RCKY"}, {"price": 52.27, "football": []},
                   {"analysts": {"targets": {"median": 52, "low": 52, "high": 52, "n": 1}}})
    assert f["title"] == "Rocky Brands (RCKY) stock forecast, price target" and f["qa"][0][1].startswith("One analyst's 12-month target is $52.00")
    f = T.forecast({"who_name": "X", "ticker": "X"}, {"price": 10, "football": [{"method": "DCF", "low": 8, "point": 9, "high": 11}]}, {})
    assert f["title"] == "X (X) stock forecast, fair value"
    o = T.owners({"who_name": "Kingsway", "ticker": "KWY"}, {"institutional": [{"manager": "Stilwell Value LLC", "value_usd": 35e6, "shares": 3e6}]})
    assert o["title"] == "Who owns Kingsway (KWY) stock? Top holders"
    one = {"quarters": [{"label": "Q2 2026", "form": "10-Q", "filed": "2026-08-01", "headline": {"revenue": 1e9},
                         "nodes": [{"id": "revenue", "label": "Revenue"}, {"id": "net", "label": "Net"}], "links": [{"s": "revenue", "t": "net", "v": 1e8}]}]}
    assert "revenue, costs and profit" in T.revenue({"who_name": "Solo", "ticker": "SOLO", "cik": 1}, one)["title"]


def test_guidance_page_never_empty_or_zero():
    co = {"who_name": "Berkshire Hathaway", "ticker": "BRK-B"}
    assert T.guidance(co, {}, {"docs": [{"kind": "mdna", "form": "10-Q", "filed": "2026-05-04", "counts": {"n": 0}, "statements": []}]}) is None
    g = T.guidance({"who_name": "NextTrip", "ticker": "NTRP"},
                   {"guidance": {"label": "initiated", "filed": "2026-10-08", "items": [{"metric": "revenue", "name": "Revenue", "period": "FY2026", "unit": "growth",
                                                                                        "lo": 100, "hi": 100, "scope": "travel segment"}]}}, None)
    assert ": ." not in g["desc"] and "Revenue (travel segment) +100% for FY2026" in g["desc"]


def test_risks_say_what_was_found():
    r = T.risks({"who_name": "iSpecimen", "ticker": "ISPC"}, {"trials": {"active": 1, "phases": {}}})
    assert r["title"] == "iSpecimen (ISPC) clinical trials" and "1 active study on ClinicalTrials.gov" in r["qa"][0][1]
    r = T.risks({"who_name": "Campbell's", "ticker": "CPB"},
                {"environment": {"facilities": 26, "in_violation": 2, "penalties_5y": 0,
                                 "top": [["CAMPBELL'S EXPRESS", "PITMAN", "NJ", "N", 12, "Violation Identified", 0, 0, None, None, None, "1"]]}})
    assert "no penalties in five years" in r["desc"] and "$0 in penalties" not in r["desc"]
    assert "CAMPBELL'S EXPRESS" in text(r["body"]) and "can belong to another business of the same name" in r["body"]
    r = T.risks({"who_name": "Glaukos", "ticker": "GKOS"}, {"environment": {"facilities": 3, "in_violation": 0, "penalties_5y": 0}, "trials": {"active": 11}})
    assert "EPA" not in r["desc"] and r["title"] == "Glaukos (GKOS) clinical trials"


def test_an_official_page_lists_the_trades_on_file():
    o = {"name": "Adam B Schiff", "slug": "adam-b-schiff", "chamber": "US Senate", "party": "Democrat", "state": "CA", "committees": [],
         "performance": {"n": 3, "scored": 2, "follow": -0.1473, "hit": 0.0, "first": "2021-07-23", "last": "2025-09-22"}, "recent": [],
         "scored": [["2025-09-22", "AAPL", -1, 32500.5, 0.0481, 0.0441, "2025-09-30"], ["2021-07-23", "ABBV", -1, 8000.5, None, None, "2021-07-30"]]}
    out = P.official_page(o, "https://x")
    t = text(out[-1] if isinstance(out, tuple) else out)
    assert "Every trade on file and how it did" in t and "AAPL Sold" in t and "+4.4% no" in t
