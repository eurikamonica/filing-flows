"""Layout of the static search pages (web/seo.css with web/styles.css), in a browser at desktop and phone widths: no
page wider than the screen, a comparison page's two Sankeys one under the other (side by side they overflowed the page
and overlapped), the table of an app view drawn on the page (fair value) inside its column, a table cell allowed to
wrap (the signals list) at a readable width rather than one word a line, and the drawn SVG charts legible on a phone
(scrolling sideways inside their box, with a swipe hint)."""
import sys
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT / "scripts"))
import seo_svg as SV  # noqa: E402

SANKEY = "<svg viewBox='0 0 2400 1100' width='2400'><rect width='2400' height='1100' fill='#ddd'/></svg>"
BARS = SV.bars([(f"Q{i} FY26", 40.0 + 9 * i) for i in range(1, 6)], lambda v: f"${v:.1f}B", "Revenue by quarter")
SIGNALS = ("New money, Big inflow, Officials buying, Officials cluster, Insider selling, Drawdown, Buying the dip, "
           "Revenue surge, Profitable growth")
PAGE = f"""<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>{(WEB / 'styles.css').read_text()}</style><style>{(WEB / 'seo.css').read_text()}</style></head><body>
<main class="seo"><h1>Colgate Palmolive vs Estee Lauder</h1>
<h2>Where the money goes: CL and EL</h2><div class="seo-two">
  <div><h3>Colgate Palmolive (CL) · Q3 2026</h3><figure class="seo-chart" data-src="x"><div>{SANKEY}</div></figure></div>
  <div><h3>Estee Lauder (EL) · Q4 FY26</h3><figure class="seo-chart" data-src="y"><div>{SANKEY}</div></figure></div></div>
<div class="tbl-wrap"><table><thead><tr><th></th><th class="num">A</th><th class="num">B</th></tr></thead>
  <tbody><tr><td>Revenue</td><td class="num">$5.4B</td><td class="num">$3.6B</td></tr></tbody></table></div>
<div class="tbl-wrap" id="signals"><table><thead><tr><th>Stock</th><th>13F net</th><th>Managers +/−</th><th>Officials 90d buy/sell</th><th>Signals</th></tr></thead>
  <tbody><tr><td><a href="#"><b>LRCX · Lam Research</b></a></td><td>$3.18B</td><td>1,515 / 1,160</td><td>1 / 1</td>
  <td><span class='muted' style='white-space:normal'>{SIGNALS}</span></td></tr></tbody></table></div>
<section class="seo-live" data-kind="hub:fairvalue"><h2>Fair value by method</h2>
<style>/* the view's own rules (disclosures/docs/fairvalue-view.js) */
.fv-tbl{{width:100%;border-collapse:collapse;font-size:13px}}.fv-tbl td.n{{white-space:nowrap}}
.fv-two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}}
@media (max-width:640px){{.fv table.fv-tbl{{display:block;overflow-x:auto;max-width:100%}}}}</style><div class="fv"><div class="fv-two">
  <div><div class="fv-wrap" style="overflow-x:auto"><table class="fv-tbl"><tr><th>Method</th><th>Low</th><th>Central</th><th>High</th><th>How</th></tr>
  <tr><td>Discounted cash flow, ten years</td><td>$95.18</td><td>$165.43</td><td>$246.53</td><td>base case 165.43; 2,000 scenarios</td></tr></table></div></div>
  <div><table class="fv-tbl"><tr><th>Method</th><th>Low</th><th>High</th></tr><tr><td>P/E vs peers</td><td>$163.51</td><td>$569.82</td></tr></table></div></div></div></section>
{BARS}
<figure class="seo-chart" style="width:auto;margin:12px 0"><svg viewBox="0 0 860 260"><path d="M0 200 L860 40" stroke="#000"/></svg></figure>
</main></body></html>"""


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                       # no browser on this machine: the CI runner has one
            pytest.skip(f"no Chromium: {e}")
        yield b
        b.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_static_pages_fit_the_screen(browser, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.set_content(PAGE)
    m = page.evaluate("""() => {
        const r = (el) => el.getBoundingClientRect();
        const charts = [...document.querySelectorAll('.seo-two .seo-chart')].map(r);
        const fig = document.querySelector('figure.seo-svg');
        return {over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                charts: charts.map((c) => [c.left, c.right, c.top, c.bottom]),
                // a table that fits its column stays in it (no minimum width from the page); a wide one scrolls in its wrapper
                fv: [...document.querySelectorAll('.fv-two > div')].map((col) => [r(col.firstElementChild).right, r(col).right]),
                row: r(document.querySelector('#signals tbody tr')).height,
                svg: r(fig.querySelector('svg')).width, box: fig.clientWidth,
                hint: getComputedStyle(fig, '::after').content,
                line: r(document.querySelector('.seo-chart:not([data-src]) svg')).width,
                vw: document.documentElement.clientWidth};
    }""")
    assert m["over"] <= 0, f"the page is {m['over']}px wider than the screen"
    (l1, r1, t1, b1), (l2, r2, t2, b2) = m["charts"]
    assert t2 >= b1, "the second company's Sankey sits under the first"
    assert l1 >= 0 and r1 <= m["vw"] and l2 >= 0 and r2 <= m["vw"]
    for table_right, column_right in m["fv"]:
        assert table_right <= column_right + 1, "an app view's table stays in its column"
    assert m["row"] < 120, f"the signals cell wraps at a readable width (row {m['row']:.0f}px tall)"
    if width < 600:
        assert m["svg"] >= 540 and m["line"] >= 600, "a drawn chart keeps legible text on a phone"
        assert "swipe" in m["hint"], "and says the rest of it is a swipe away"
    else:
        assert m["svg"] <= m["box"], "a drawn chart fits its box on a desktop"
        assert m["hint"] in ("none", "normal")
    page.close()
