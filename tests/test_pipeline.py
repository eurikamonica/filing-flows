"""Offline tests: run with `python -m pytest tests` (fixtures stand in for SEC endpoints)."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import dims, text  # noqa: E402
from pipeline.sankey import pct_change, share  # noqa: E402

DOC = """<html><body>
<div>Table of Contents</div><div>Item 1. Business</div><div>Item 1A. Risk Factors</div>
<p><b>PART I</b></p><p><b>Item 1. Business</b></p>
<p><b>Company Background</b></p>
<p>The Example Company designs and sells widgets and related services to customers in more than forty countries, through its own stores and partners.</p>
<p>The Company's fiscal year is the 52- or 53-week period that ends on the last Saturday of September, which the Company uses for all reporting.</p>
<p><b>Products</b></p>
<p>Widgets come in three sizes and are sold directly and through cellular network carriers, wholesalers, retailers and resellers worldwide.</p>
<p><b>Item 1A. Risk Factors</b></p><p>Risks.</p>
<p><b>Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations</b></p>
<p><b>Widgets</b></p>
<p>Widgets net sales increased during the quarter compared to the same quarter last year primarily due to higher demand for large widgets.</p>
<p><b>Services</b></p>
<p>Services net sales increased due to higher subscription revenue across all regions during the quarter and the first nine months.</p>
<p>Filler paragraph to give the section enough length for the parser to accept it as the real MD&amp;A body and not a table of contents line.</p>
<p><b>Item 3. Quantitative and Qualitative Disclosures About Market Risk</b></p>
</body></html>"""


def test_intro_takes_item1_paragraphs():
    it = text.intro(DOC)
    assert it.startswith("The Example Company designs")
    assert "last Saturday of September" in it


def test_notes_match_heading_exactly():
    md = text.mdna(DOC)
    n = text.match_notes(md, ["Widgets"])
    assert n and n[0]["heading"] == "Widgets" and "large widgets" in n[0]["text"]
    assert text.match_notes(md, ["Gadgets"], fallback=False) == []


def test_partition_finds_lines_that_add_up():
    members = {"a": ("A", 50.0), "b": ("B", 30.0), "c": ("C", 20.0), "ab": ("A+B", 80.0)}
    part = dims.best_partition(members, 100.0)
    assert {l["id"] for l in part["leaves"]} == {"a", "b", "c"}
    assert part["groups"][0]["members"] == ["a", "b"] or set(part["groups"][0]["members"]) == {"a", "b"}


def test_formatting_rules():
    assert pct_change(110, 100) == "+10%"
    assert pct_change(-1, 100) == "n/m"
    assert share(5, 100) == "5.0%" and share(50, 100) == "50%"


def test_fixture_run_renders_site(tmp_path):
    env = dict(os.environ, SEC_FIXTURES=os.path.join(ROOT, "tests", "fixtures"), SEC_USER_AGENT="test test@example.com")
    out = tmp_path / "data"
    subprocess.run([sys.executable, "-m", "pipeline.build", "run", "--store", str(tmp_path / "store"), "--out", str(out)],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    ix = json.load(open(out / "index.json"))
    assert {c["ticker"] for c in ix["companies"]} >= {"AAPL", "META", "CRWV", "BRK-B"}
    apple = json.load(open(out / "c" / "320193.json"))
    q = apple["quarters"][0]
    iphone = next(n for n in q["nodes"] if n["name"] == "iPhone")
    assert iphone["lines"][1][1].startswith("$54.3B · 69% of Products")
    assert iphone["notes"][0]["text"].startswith("iPhone net sales increased")
    assert q["compare"]["vs"] == "Q2 FY26" and len(q["compare"]["bullets"]) == 3
    assert all(isinstance(p, str) and p for p in q["analysis"])


def test_earnings_release_8k(tmp_path):
    """Fictional companies EXDV / SMCL: quarter read from the press release tables, units, signs and YTD cash flow."""
    env = dict(os.environ, SEC_FIXTURES=os.path.join(ROOT, "tests", "fixtures"), SEC_USER_AGENT="test test@example.com")
    store = tmp_path / "store"
    subprocess.run([sys.executable, "-m", "pipeline.build", "run", "--store", str(store), "--out", str(tmp_path / "data")],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    x = json.load(open(store / "companies" / "9999901.json"))["quarters"]["2026-08-30"]
    assert x["form"] == "8-K" and x["label"] == "Q4 FY26"
    want = dict(revenue=5240, cor=2870, gp=2370, oi=1110, pretax=1097, tax=165, ni=932, ocf=1600, da=520, sbc=105, capex=1100)
    assert all(abs(x["raw"][k] / 1e6 - v) < 0.01 for k, v in want.items())
    s = json.load(open(store / "companies" / "9999902.json"))["quarters"]["2026-06-30"]
    want = dict(revenue=412.5, oi=-41.1, pretax=-50.3, tax=1.2, pl=-51.5, ni=-51.0, nci=-0.5, ocf=36, capex=65)
    assert all(abs(s["raw"][k] / 1e6 - v) < 0.01 for k, v in want.items())
    seen = json.load(open(store / "state.json"))["seen"]
    assert "0009999901-26-000046" not in seen                     # Item 5.02 8-K is never queued
    page = json.load(open(tmp_path / "data" / "c" / "9999901.json"))["quarters"][0]
    assert page["preliminary"] and "earnings release" in page["subtitle"]
