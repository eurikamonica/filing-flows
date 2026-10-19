"""Discovery & UX (workstream F1): the search index and Atom feeds (scripts/hub_extras.py), the X post formats of
pipeline/posts_ux.py, and the browser modules (web/search.js, overview.js, feed.js, charts.js, editor.js) run in Node."""
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _hub(tmp_path):
    hub = tmp_path / "hub"
    W = lambda rel, obj: (hub / rel).parent.mkdir(parents=True, exist_ok=True) or (hub / rel).write_text(json.dumps(obj))
    W("catalogs/holdings.json", [{"cik": "1067983", "name": "BERKSHIRE HATHAWAY INC", "processed": True, "filing_count": 7}, {"cik": "5", "name": "X", "processed": False}])
    W("market/watchlist.json", {"funds": [{"cik": "1067983", "name": "Berkshire Hathaway"}, {"cik": "1350694", "name": "Bridgewater Associates"}]})
    W("market/officials-trades.json", {"trades": [
        {"ticker": "AAPL", "ticker_canon": "AAPL", "ticker_status": "listed", "asset_type": "ST", "type": "purchase", "date": "2026-10-10", "filed_date": "2026-10-15",
         "amount_min": 15001, "amount_max": 50000, "person": "Jane Roe", "jurisdiction": "US House", "report_id": "h1", "source_url": "https://x.gov/1.pdf"},
        {"ticker": "AAPL", "ticker_canon": "AAPL", "ticker_status": "listed", "asset_type": "ST", "type": "sale", "date": "2026-10-12", "filed_date": "2026-10-16",
         "amount_min": 1001, "amount_max": 15000, "person": "John Doe", "jurisdiction": "US Senate", "report_id": "s1", "source_url": "https://x.gov/2.pdf"}]})
    W("market/insiders.json", {"latest": [
        {"accession": "a1", "ticker": "AAPL", "insider": "Cook Tim", "role": "CEO", "title": "CEO", "code": "S", "date": "2026-10-08", "shares": 50000, "price": 230.5, "value": 11525000, "plan_10b5_1": True, "url": "https://sec.gov/a1"},
        {"accession": "a2", "ticker": "AAPL", "insider": "Smith Ann", "role": "Director", "title": "", "code": "P", "date": "2026-10-14", "shares": 1000, "price": 228.0, "value": 228000, "url": "https://sec.gov/a2"},
        {"accession": "a3", "ticker": "META", "insider": "Doe Jo", "role": "CFO", "title": "CFO", "code": "S", "date": "2026-10-13", "shares": 2000, "price": 700.0, "value": 1400000, "url": "https://sec.gov/a3"}]})
    W("market/stakes.json", {"latest": [{"accession": "k1", "form": "13G", "filed": "2026-10-16", "ticker": "AAPL", "holder": "Big Fund", "percent": "5.6", "url": "https://sec.gov/k1"}]})
    W("market/form144.json", {"latest": [{"accession": "f1", "filed": "2026-10-15", "ticker": "META", "seller_name": "Jo Doe", "shares": "386667", "value": "18517483", "url": "https://sec.gov/f1"}]})
    W("market/events8k.json", {"rows": [{"accession": "e1", "ticker": "AAPL", "filed": "2026-10-16", "accepted": "2026-10-16T08:02", "label": "a material agreement", "items": ["1.01"], "quote": "entered into an agreement", "url": "https://sec.gov/e1"},
                                        {"accession": "e2", "ticker": "META", "filed": "2026-10-15", "label": "results", "items": ["2.02"], "url": "https://sec.gov/e2"}]})
    W("etf/index.json", {"fields": ["symbol", "name", "aum"], "rows": [["SPY", "SPDR S&P 500", 5e11], ["QQQ", "Invesco QQQ", 3e11]]})
    W("holders/AAPL.json", {"ticker": "AAPL", "insiders": [{"insider": "Smith Ann", "role": "Director", "code": "P", "date": "2026-10-14", "shares": 1000, "price": 228.0, "value": 228000, "url": "https://sec.gov/a2"}],
                            "events8k": [{"filed": "2026-10-16", "label": "a material agreement", "items": ["1.01"], "url": "https://sec.gov/e1", "accession": "e1"}]})
    return hub


def test_search_index_and_feeds(tmp_path):
    from scripts import hub_extras as X
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    (site / "data" / "index.json").write_text(json.dumps({"companies": [
        {"cik": 320193, "ticker": "AAPL", "name": "Apple Inc.", "filed": "2026-07-31", "form": "10-Q", "label": "Q3 FY26", "end": "2026-06-27", "rev": "$109.4B", "revenue": 109.4e9, "yoy": 16.3, "om": 32.6},
        {"cik": 1326801, "ticker": "META", "name": "Meta", "filed": "2026-07-30", "form": "10-Q", "label": "Q2 2026", "end": "2026-06-30", "rev": "$60.8B", "revenue": 60.8e9}]}))
    r = X.build(site, "https://example.org/", 1, hub=_hub(tmp_path))
    sx = json.loads((site / "data" / "search.json").read_text())
    assert [m[0] for m in sx["managers"]][:2] == ["1067983", "1350694"] and sx["managers"][0][2] == "Berkshire Hathaway"
    assert sx["officials"][0][0] in ("Jane Roe", "John Doe") and [e[0] for e in sx["etfs"]] == ["SPY", "QQQ"]
    assert sx["feeds"] == ["AAPL"] and r["company_feeds"] == 1 and r["feeds"]["insiders"] == 3
    f = (site / "feeds" / "filings.xml").read_text()
    assert f.startswith('<?xml version="1.0"') and "<entry>" in f and "AAPL — Apple Inc.: 10-Q Q3 FY26" in f and "https://example.org/#c-320193-2026-06-27" in f
    c = (site / "feeds" / "c" / "AAPL.xml").read_text()
    assert "Insider: Smith Ann (Director) bought 1,000 shares" in c and "8-K — a material agreement" in c and "<id>urn:filing-flows:" in c or "<id>https://sec.gov" in c
    off = (site / "feeds" / "officials.xml").read_text()
    assert "Jane Roe: purchase AAPL ($15,001–$50,000)" in off and "&lt;" not in off.split("<title>")[0]
    assert not (site / "feeds" / "c" / "META.xml").exists()                  # only the largest company got a feed (n=1)


def test_who_traded_and_disclosure_week_posts(tmp_path):
    from pipeline import engage, notify, posts_ux as P, train_local, xkinds as X
    hub = _hub(tmp_path)
    site = tmp_path / "s"
    (site / "data").mkdir(parents=True)
    (site / "data" / "index.json").write_text(json.dumps({"companies": []}))
    (site / "disclosures").mkdir()
    (site / "disclosures" / "data").symlink_to(hub)
    s = notify.Site(str(site))
    today, ok = dt.date(2026, 10, 19), (lambda *a, **k: True)
    ev = P.disclosed(s, today, 30)
    assert sorted(ev) == ["AAPL", "META"] and len(ev["AAPL"]) == 6 and {e[1] for e in ev["AAPL"]} == {"insider", "official", "stake", "8k"}
    p = P.plan_who_traded(s, [], engage.cfg(), {}, ok, today)
    assert p["cashtags"] == ["AAPL"] and p["lines"] and "Oct 14 · Director Smith Ann bought 1,000 sh at $228.00" in p["fallback"]
    assert "8-K" not in p["fallback"] and "Jane Roe bought ($15K–$50K)" in p["fallback"]
    w = P.plan_disclosure_week(s, [], engage.cfg(), {}, ok, today)
    assert w is None                                                            # only two stocks with three disclosures: not a list
    for plan in (p,):
        for fb in plan["fallbacks"]:
            post = engage.clean(fb, plan["cashtags"], plan["tags"], allowed=plan.get("allowed"), lines=True)
            assert "\n" in post and post.endswith(" ".join(plan["tags"])), post
            prompt = __import__("pipeline.local_model", fromlist=["x"]).compact(engage.messages(plan["kind"], plan["task"], plan["cashtags"], plan["tags"]))
            assert not __import__("pipeline.local_model", fromlist=["x"]).unsupported(post, prompt), post
    # registered: the dispatch, the schedule, the owner's button, the schema
    assert set(X.load()) >= {"who_traded", "disclosure_week"} and "who_traded" in X.expand(["@evening"]) and "disclosure_week" in X.expand(["@weekly"])
    assert engage.registered_plan("who_traded", s, [], engage.cfg(), {}, ok, today)["kind"] == "who_traded"
    assert any(b["kind"] == "engage_who_traded" for b in X.buttons())


def _node(script):
    r = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def test_browser_modules_in_node():
    out = _node(r"""
const U = require('./web/ux.js');
const S = require('./web/search.js');
S._setIndex({ site: [{k:'company', id:320193, tk:'AAPL', name:'Apple Inc.', rev:1e11, href:'#c-320193'}, {k:'company', id:1, tk:'AAPX', name:'Apex Co', rev:1, href:'#c-1'}],
  sec: [{k:'company', id:2, tk:'META', name:'Meta', rev:0, off:true, href:'#c-2'}], mgr: [{k:'manager', id:'1067983', tk:'', name:'Berkshire Hathaway', w:7, href:'disclosures/#holdings/1067983'}],
  off: [{k:'official', id:'Nancy Pelosi', tk:'', name:'Nancy Pelosi', w:40, href:'disclosures/#trades/Nancy%20Pelosi'}], etf: [{k:'etf', id:'SPY', tk:'SPY', name:'SPDR S&P 500', w:1, href:'disclosures/#etf/SPY'}], pages: [] });
const g = Object.fromEntries(S.find('aapl'));
console.log(JSON.stringify([g.Companies.map(e => e.tk), Object.fromEntries(S.find('berk'))['13F managers'][0].name, Object.fromEntries(S.find('pelosi')).Officials[0].href, Object.fromEntries(S.find('spy')).ETFs.length, S.find('zzzz').length]));
const F = require('./web/feed.js');
const ev = F.events('AAPL', { insiders: [{insider:'A B', role:'CEO', code:'P', date:'2026-10-14', shares:1000, price:228, value:228000, url:'https://sec.gov/x'}], events8k: [{filed:'2026-10-16', label:'a deal', url:'https://sec.gov/e'}],
  flows: {buyers: 3, sellers: 1, usd_net: 5e6, label: 'Q2'}, institutional: [{filed:'2026-08-14'}] }, {cik: 320193, filed: '2026-07-31', form: '10-Q', label: 'Q3 FY26', end: '2026-06-27', rev: '$1B', yoy: 5},
  { analysts: {as_of: '2026-10-18'}, markets: [{kind:'beat', p: 0.64, eps_strike: 1.15, end: '2026-10-30'}] }, { asof: '2026-10-16', row: {new_hi: 1, close: 230, day_hi: 231} });
console.log(JSON.stringify(ev.sort((a, b) => b.date.localeCompare(a.date) || a.type.localeCompare(b.type)).map(e => e.type)));
const C = require('./web/charts.js');
const c = { profile: {name: 'Apple Inc.', tickers: ['AAPL']}, quarters: [{end: '2026-06-27', label: 'Q3 FY26', headline: {revenue: 100, oi: 30, ni: 25, ocf: 28, om: 30}, nodes: [{id:'I:rd', name:'Research &amp; development', v: 11}]}, {end: '2026-03-28', label: 'Q2 FY26', headline: {revenue: 90, oi: 28, ni: 22, ocf: 20, om: 31}, nodes: [{id:'I:rd', name:'Research &amp; development', v: 10}]}],
  quality: { hist: { periods: [['2025-01-01', '2025-03-29', 'q', 'Q2 FY25'], ['2025-07-01', '2025-09-27', 'fy', 'FY25']], v: { revenue: [[0, [[80, []]]], [1, [[400, []]]]] } } } };
const ser = C.seriesOf(c);
const st = C.parse('c=320193&i=h:revenue,n:Research%20%26%20development&t=bar');
const data = new Map([[320193, {c, name: 'Apple Inc.', ticker: 'AAPL', ser}]]);
const pl = C.plotted(st, data);
console.log(JSON.stringify([ser.S['h:revenue'].size, [...ser.S['h:revenue'].keys()], ser.label['n:Research & development'], pl.length, C.serialize(st), C.svg(pl, 'bar').includes('<rect')]));
const E = require('./web/editor.js');
const q = { label: 'Q3 FY26', headline: {revenue: 100, oi: 30, ni: 24}, nodes: [{id:'a', col:0, color:'rev', name:'A', v:60, lines:[['name','A'],['val','$60 · 60% of revenue']]}, {id:'b', col:0, color:'rev', name:'B', v:40, lines:[['name','B'],['val','$40 · 40% of revenue']]}, {id:'revenue', col:1, color:'rev', name:'Revenue', v:100, lines:[['big','Revenue'],['val','$100']]}, {id:'cor', col:2, color:'cost', name:'Cost of revenue', v:50, lines:[['name','Cost of revenue'],['val','']]}, {id:'gp', col:2, color:'profit', name:'Gross profit', v:50, lines:[['name','Gross profit'],['val','']]}, {id:'opex', col:3, color:'cost', name:'Operating expenses', v:20, lines:[]}, {id:'oi', col:3, color:'profit', name:'Operating profit', v:30, lines:[]}, {id:'pretax', col:4, color:'profit', name:'Pre-tax', v:30, lines:[]}, {id:'net', col:5, color:'profit', name:'Net earnings', v:24, lines:[]}, {id:'tax', col:5, color:'cost', name:'Income tax', v:6, lines:[]}],
  links: [{s:'a', t:'revenue', v:60, color:'rev'}, {s:'b', t:'revenue', v:40, color:'rev'}, {s:'revenue', t:'cor', v:50, color:'cost'}, {s:'revenue', t:'gp', v:50, color:'profit'}, {s:'gp', t:'opex', v:20, color:'cost'}, {s:'gp', t:'oi', v:30, color:'profit'}, {s:'oi', t:'pretax', v:30, color:'profit'}, {s:'pretax', t:'net', v:24, color:'profit'}, {s:'pretax', t:'tax', v:6, color:'cost'}] };
const spec = JSON.parse(JSON.stringify(q));
E.merge(spec, ['a', 'b'], 'All segments');
const m = spec.nodes.find(n => n.id.startsWith('fx:m:'));
let bad = ''; try { E.merge(JSON.parse(JSON.stringify(q)), ['a', 'cor'], 'x'); } catch (e) { bad = e.message; }
const B = E.baseOf(q), P = E.project(B, {growth: 0.1, gm: 0.5, opex: 0.2, tax: 0.2});
const sc = E.scenarioSpec(q, 'Apple', P, {v: 10, basis: 'diluted', label: 'FY26'});
console.log(JSON.stringify([m.v, m.lines[1][1], spec.links.filter(l => l.t === 'revenue').length, bad.length > 0, B.gm, B.tax, Math.round(P.NET * 100) / 100, sc.nodes.map(n => n.id), Math.round(sc._eps * 100) / 100]));
""")
    lines = [json.loads(l) for l in out.strip().split("\n")]
    assert lines[0] == [["AAPL"], "Berkshire Hathaway", "disclosures/#trades/Nancy%20Pelosi", 1, 0]
    assert lines[1] == ["market", "8k", "extreme", "insider", "13f", "filing"], lines[1]
    assert lines[2] == [3, ["2025-03-29", "2026-06-27", "2026-03-28"], "Research & development", 2, "chart/c=320193&i=h%3Arevenue,n%3AResearch%20%26%20development&t=bar", True]
    assert lines[3] == [100, "$100 · 100% of revenue", 1, True, 0.5, 0.2, 26.4, ["revenue", "cor", "gp", "opex", "oi", "pretax", "net", "tax"], 2.64]


def test_site_wiring():
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    for s in ("ux.js", "search.js", "overview.js", "feed.js", "charts.js", "editor.js"):
        assert f'<script src="{s}"></script>' in html
    assert 'href="feeds/filings.xml"' in html and 'id="palette-btn"' in html and 'href="#feed"' in html and 'href="#chart"' in html
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    assert "window.FFFeed.render" in app and "window.FFCharts.render" in app and "window.FFOverview.mount" in app and "window.FFEditor.mount" in app and "FFSearch.moreHTML" in app
    views = json.load(open(os.path.join(ROOT, "disclosures", "docs", "views.json")))
    assert {"id": "events", "label": "Events", "script": "events-view.js", "global": "EventsView"} in views
    ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml")).read()
    assert "docs/events-view.js" in ci
    scan = open(os.path.join(ROOT, ".github", "workflows", "scan.yml")).read()
    assert "scripts/hub_extras.py --site _site" in scan
