"""Fixture for tests/test_ipo_market_browser.cjs: the reviewed Anthropic seed's standard charts and a prospectus
reading of the small made-up registration statement in tests/test_ipo_reader.py, as the collector publishes them."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
from pipeline import ipo_charts, ipo_market  # noqa: E402
from test_ipo_reader import plain_doc  # noqa: E402

seed = json.loads((HERE.parent / "pipeline/data/ipo/2130357.json").read_text())
reader = ipo_market.read_prospectus(plain_doc(), {k: seed[k] for k in ("cik", "name", "form", "filed", "accession", "source_url")}, seed)
print(json.dumps({"charts": ipo_charts.charts(seed), "reader": reader, "summary": ipo_market.reader_summary(reader)}))
