"""scripts/seo_hub.py momentum(): the crawlable momentum page from the latest-week files app/momentum.py writes (the
companies with the rotation history, the ETFs with the ETF build) — the breadth in the lead, the sectors by their median
composite, the strongest and weakest, the ETFs of $100M or more; nothing without enough companies."""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_hub as HB  # noqa: E402

LATEST = ['m12_1', 'm6_1', 'm1', 'hi52', 'vol', 'ra12', 'comp', 'rel_b', 'rel_s', 'rcomp']
P = ['p_m12_1', 'p_m6_1', 'p_hi52', 'p_ra12', 'p_comp']


def w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)


def stocks(n):
    secs = ['technology', 'energy', 'health', 'financials']
    rows = {}
    for i in range(n):
        comp = 2.0 - 4.0 * i / (n - 1)                                   # T00 strongest … the last weakest
        rows[f'T{i:02d}'] = [comp / 5, comp / 8, 0.01, -0.05, 0.3, comp / 2, comp, comp / 10 - 0.05, None, comp / 3,
                             50, 50, 50, 50, round(100 * (n - 1 - i) / (n - 1)), f'Company {i}', secs[i % 4]]
    return {'v': 1, 'generated_at': '2026-11-08T03:00:00+00:00', 'week': '2026-11-06', 'month': '2026-10-30', 'n': n, 'cols': LATEST + P + ['n', 's'], 'rows': rows}


def test_momentum_page(tmp_path):
    s = tmp_path / "site"
    h = s / "disclosures" / "data"
    w(s / "data" / "index.json", {"companies": [{"cik": 1, "ticker": "T00", "name": "COMPANY 0"}]})
    w(s / "c" / "t00" / "index.html", "x")
    w(s / "disclosures" / "index.html", "<html><body>hub</body></html>")
    w(h / "market" / "history" / "momentum-latest.json", stocks(24))
    etf = {'cols': LATEST + P + ['p_comp_group', 'ac', 'aum', 'dv', 'n'], 'rows': {
        'BIG': [0.3, 0.1, 0.0, -0.01, 0.2, 1.5, 1.4, 0.1, None, 0.5, 90, 90, 90, 90, 95, 97, 'Equity', 5e10, 1e9, 'Big Fund'],
        'SML': [0.9, 0.5, 0.0, 0.0, 0.5, 1.8, 2.5, 0.6, None, 1.5, 99, 99, 99, 99, 100, 100, 'Equity', 5e7, 1e6, 'Small Fund']}}
    w(h / "etf" / "momentum-latest.json", etf)
    L = HB.Links(str(s))
    slug, tab, title, h1, lead, body = HB.momentum(str(h), L)
    assert (slug, tab) == ('momentum', 'momentum') and 'Nov 6, 2026' in title
    # 12 of 24 with a positive 12-1 (comp > 0 for the first twelve), ahead of SPY when comp/10 > 0.05
    assert 'the 24 companies' in lead and '50% have a positive 12-month' in lead and 'Strongest now: T00, T01, T02' in lead
    assert body.index('Sectors by momentum') < body.index('Strongest momentum') < body.index('Weakest momentum') < body.index('ETFs with the strongest')
    strong = body[body.index('<h2>Strongest momentum'):body.index('<h2>Weakest momentum')]
    assert strong.index('T00') < strong.index('T01') and "href='../../c/t00/'" in strong and '+2.00σ' in strong
    weak = body[body.index('<h2>Weakest momentum'):body.index('<h2>ETFs')]
    assert weak.index('T23') < weak.index('T22')
    etfs = body[body.index('<h2>ETFs'):]
    assert "#momentum/BIG" in etfs and 'SML' not in etfs                 # under $100M of net assets: left out
    # the page is written, linked from the hub and listed in the sitemap
    pages, _ = HB.write(str(s), "https://example.com", str(tmp_path / "store"), dt.date(2026, 11, 9))
    assert pages == ['momentum']
    page = (s / "disclosures" / "momentum" / "index.html").read_text()
    assert "href='../../#momentum'" in page and 'https://example.com/disclosures/momentum/' in (s / "sitemap-hub.xml").read_text()
    # too few companies: no page
    w(h / "market" / "history" / "momentum-latest.json", stocks(10))
    assert HB.momentum(str(h), L) is None
