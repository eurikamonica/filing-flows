"""Text on the hub and cash-flow pages: the investment-gains page reads the research file as it is written (columnar:
the field names once, then a list per company; read as dicts the page was never written), and every item of the
profit-to-cash bridge has a label on the cash-flow page (it showed field names such as gain_inv and d_oassets)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import seo_cashflow as CF  # noqa: E402
import seo_hub as HB  # noqa: E402
from pipeline import fsa  # noqa: E402


def test_every_bridge_item_has_a_label():
    assert [k for k, *_ in fsa.NONCASH + fsa.WC if k not in CF.BRIDGE] == []


def test_investment_gains_from_the_columnar_research_file(tmp_path):
    hub = tmp_path / "disclosures" / "data"
    f = hub / "research" / "investors" / "index.json"
    f.parent.mkdir(parents=True)
    fields = ["cik", "t", "name", "sector", "gains", "share", "top_gainer"]
    rows = [[100 + i, f"T{i}", f"COMPANY {i} INC", "technology", 1e9 * (10 - i), 0.05 * i, f"HOLDING {i}"] for i in range(6)]
    rows.append([200, "LOSS", "LOSER INC", "financials", None, None, None])          # no gains: left out
    f.write_text(json.dumps({"fields": fields, "rows": rows, "losers": []}))
    r = HB.investors(str(hub), HB.Links(str(tmp_path)))
    assert r is not None
    slug, tab, title, h1, lead, body = r
    assert slug == "investment-gains" and "($10.00B)" in lead
    assert "HOLDING 0" in body and "LOSER" not in body
