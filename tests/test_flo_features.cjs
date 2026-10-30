// web/earnings-day.js (the home page's earnings-day dashboard), web/flo-features.js (Flo: explain a node, compare two
// companies, the watchlist, the page guide) and the overview tiles' trend lines (web/overview.js), on fixed data.
const assert = require('node:assert/strict');
const path = require('node:path');
let checks = 0;
const ok = (c, m) => { assert.ok(c, m); checks++; };
const W = (f) => path.join(__dirname, '..', 'web', f);

const mem = {};
global.localStorage = { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = String(v); } };
global.RRGCompanyView = require(path.join(__dirname, '..', 'disclosures', 'docs', 'rrg-company-view.js'));
global.FFUx = require(W('ux.js'));
const ED = require(W('earnings-day.js'));
const FX = require(W('flo-features.js'));
const OV = require(W('overview.js'));
const M = require(W('mascot.js'));

// ---------- earnings day ----------
const ix = { sector_names: { tech: 'Technology', energy: 'Energy' }, companies: [
  { cik: 1, ticker: 'BIG', name: 'Big &amp; Co', sector: 'tech', filed: '2026-10-28', form: '10-Q', revenue: 9e10, yoy: 20, om: 40, label: 'Q3 2026', end: '2026-09-30', rev: '$90.0B' },
  { cik: 2, ticker: 'MID', name: 'Mid Inc', sector: 'tech', filed: '2026-10-28', form: '8-K', prelim: true, revenue: 3e10, yoy: 10, om: 20, label: 'Q3 2026', end: '2026-09-30' },
  { cik: 3, ticker: 'OIL', name: 'Oil Corp', sector: 'energy', filed: '2026-10-28', form: '10-Q', revenue: 5e10, yoy: -5, om: 8, label: 'Q3 2026', end: '2026-09-30' },
  { cik: 4, ticker: 'SML', name: 'Small', sector: 'tech', filed: '2026-10-28', form: '10-Q', revenue: 1e9, yoy: 30, om: -3, label: 'Q3 2026', end: '2026-09-30' },
  { cik: 5, ticker: 'OLD', name: 'Old', sector: 'tech', filed: '2026-10-20', form: '10-Q', revenue: 2e10, yoy: 1, om: 9, label: 'Q3 2026', end: '2026-09-30',
    also: [{ filed: '2026-10-28', form: '8-K', end: '2026-12-31', label: 'Q4 2026' }] },
] };
const S = ED.summarize(ix, '2026-10-28');
ok(S.count === 5, 'every filing of the day, the 8-K of an older filer too: ' + S.count);
ok(S.sectors[0].id === 'tech' && S.sectors[0].median === 15 && S.sectors[0].n === 4 && S.sectors[1].median === -5, 'sector medians, highest first: ' + JSON.stringify(S.sectors));
ok(S.top.map((e) => e.ticker).join() === 'BIG,OIL,MID,OLD,SML' && S.dots.length === 5, 'largest first; dots need both figures');
ok(ED.median([3, 1, 2, 10]) === 2.5 && ED.median([]) === null, 'median');
ok(ED.heat(0) === '#f1f6f2' && ED.heat(99) === '#7fbf9a', 'the colour scale stays light enough for dark text');
ok(ED.summarize(ix, '2026-10-29').count === 0, 'a day without filings');

// ---------- the overview tiles' trend lines ----------
const co = { profile: { name: 'X' }, quarters: [5, 4, 3, 2, 1].map((k, i) => ({ end: `2026-0${9 - i * 2 > 0 ? 9 - i * 2 : 1}-30`, label: 'Q' + k, headline: { revenue: 100 + 10 * k, ni: 10 * k, ocf: 5 * k, om: 20 + k } })) };
ok(JSON.stringify(OV.series(co, co.quarters[0], 'revenue')) === '[110,120,130,140,150]', 'the line runs oldest to newest up to the quarter shown');
ok(JSON.stringify(OV.series(co, co.quarters[2], 'revenue')) === '[110,120,130]', 'an older quarter: the line ends at it');
ok(OV.sparkSVG({ v: [1, 2, 3], role: 'profit' }).includes('fx-spark profit') && OV.sparkSVG({ v: [1, 2] }) === '', 'two points draw no line');

// ---------- Flo: explain a node from the chart's own figures ----------
const nodes = [{ id: 'a', name: 'Segment A', v: 60, q: 50, y: 40 }, { id: 'b', name: 'Segment B', v: 40, q: 40, y: 30 }, { id: 'revenue', name: 'Revenue', v: 100, q: 90, y: 70 },
  { id: 'gp', name: 'Gross profit', v: 70, q: 60, y: 45 }, { id: 'cor', name: 'Cost of revenue', v: 30, q: 30, y: 25 }, { id: 'net', name: 'Net earnings', v: 50, q: 40, y: 30 },
  { id: 'wc_out', name: 'Working capital &amp; other', v: 30, q: 5, y: 5 }, { id: 'ocf', name: 'Operating cash flow', v: 20, q: 35, y: 25 }];
const links = [{ s: 'a', t: 'revenue', v: 60, q: 50 }, { s: 'b', t: 'revenue', v: 40, q: 40 }, { s: 'revenue', t: 'gp', v: 70, q: 60 }, { s: 'revenue', t: 'cor', v: 30, q: 30 },
  { s: 'net', t: 'wc_out', v: 30, q: 5 }, { s: 'net', t: 'ocf', v: 20, q: 35 }];
let e = FX.explainFigures({ id: 'revenue', nodes, links, period: 'Q3' }, 'en');
ok(e.html.includes('<b>Segment A</b> accounted for') && e.html.includes('(100%)') && e.html.includes('Where it went: Gross profit 70%, Cost of revenue 30%'), 'what moved revenue and where it went: ' + e.html);
e = FX.explainFigures({ id: 'gp', nodes, links, period: 'Q3' }, 'en');
ok(e.html.includes('70% of revenue (67% a quarter earlier)') && e.html.includes('added 100¢') && e.facts.some((f) => /Margin on revenue: 70\.0% · \+3\.3 pts Q\/Q/.test(f)), 'a profit line: its share and margin: ' + e.facts);
e = FX.explainFigures({ id: 'ocf', nodes, links, period: 'Q3' }, 'zh');
ok(e.html.includes('净利润') && e.html.includes('40%') && e.html.includes('88%'), 'cash against earnings, in Chinese');
ok(!/NaN|undefined/.test(e.html) && FX.explainFigures({ id: 'nope', nodes, links }, 'en') === null, 'no node: no answer');

// ---------- Flo: two companies side by side ----------
const ix2 = { companies: [{ cik: 1045810, ticker: 'NVDA', name: 'NVIDIA CORP', revenue: 9e10 }, { cik: 2488, ticker: 'AMD', name: 'ADVANCED MICRO DEVICES INC', revenue: 1e10 },
  { cik: 320193, ticker: 'AAPL', name: 'Apple Inc.', revenue: 9e10 }] };
ok(FX.isCompare('NVDA vs AMD') && FX.isCompare('英伟达和超威对比') && !FX.isCompare('NVDA latest earnings'), 'compare intent');
ok(FX.findCompanies('NVDA vs AMD', ix2, M.findCompany).map((c) => c.ticker).join() === 'NVDA,AMD', 'two tickers');
ok(FX.findCompanies('compare apple with nvidia', ix2, M.findCompany).length === 2, 'two names');
ok(FX.findCompanies('NVDA relative strength vs SPY', ix2, M.findCompany).length === 1, 'an index is not a company');
const C = { 1045810: { quarters: [{ label: 'Q2 FY27', end: '2026-07-26', headline: { revenue: 96.2e9, yoy: 106, om: 66.2, ni: 59.7e9, ocf: 24.1e9 } }] },
  2488: { quarters: [{ label: 'Q2 2026', end: '2026-06-27', headline: { revenue: 11.5e9, yoy: 50, om: 17.3, ni: 2.3e9, ocf: 2.4e9 } }] } };

// ---------- Flo: watchlist ----------
ok(FX.isWatch('follow AMD') && FX.isWatch('关注 AMD') && !FX.isWatch('NVDA follow-up'), 'watch intent');
let w = FX.watchAnswer('follow AMD', ix2.companies[1], 'en');
ok(w.html.includes('Following <b>AMD</b>') && FX.watched().join() === 'AMD', 'followed in this browser');
FX.watchAnswer('follow NVDA', ix2.companies[0], 'en');
FX.watchAnswer('unfollow AMD', ix2.companies[1], 'en');
ok(FX.watched().join() === 'NVDA', 'unfollow');
const ix3 = { companies: [{ cik: 1045810, ticker: 'NVDA', name: 'NVIDIA', filed: '2026-08-26', form: '10-Q', label: 'Q2 FY27', revenue: 96e9, rev: '$96.2B', yoy: 105.9, om: 66.2 },
  { cik: 789019, ticker: 'MSFT', name: 'Microsoft', filed: '2026-10-28', form: '10-Q', label: 'Q1 FY27', revenue: 92e9, rev: '$92.3B', yoy: 18.8, om: 49.8 }] };
FX.setWatch(['NVDA', 'MSFT']);
const d = FX.digest(ix3, FX.watched(), '2026-10-26', 'en');
ok(d.rows.length === 1 && d.rows[0].ticker === 'MSFT' && d.quiet[0].ticker === 'NVDA' && d.html.includes('+18.8% Y/Y'), 'what was filed since the last visit');
ok(FX.visitDigest(ix3, 'en', '2026-10-29') && FX.visitDigest(ix3, 'en', '2026-10-29') === null, 'once a day');

// ---------- Flo: the page guide ----------
ok(FX.isTour('show me around') && FX.isTour('带我看看') && !FX.isTour('NVDA valuation'), 'guide intent');
ok(FX.tourKind({ kind: 'company' }) === 'company' && FX.tourKind({ kind: 'hub' }) === 'hub' && FX.tourKind({ kind: 'group' }) === null, 'guided pages');
ok(Object.values(FX.STEPS).every((s) => s.every(([sel, t, x]) => sel && t.length === 2 && x.length === 2)), 'every step in English and Chinese');

(async () => {
  const r = await FX.compare([ix2.companies[0], ix2.companies[1]], 'en', async (c) => C[c.cik]);
  ok(r.html.includes('8.4×') && r.html.includes('66.2% against 17.3%') && r.html.includes('1 month apart') && r.links.length === 3, 'compare: ' + r.html.slice(0, 200));
  ok(await FX.compare([ix2.companies[0], ix2.companies[2]], 'en', async (c) => C[c.cik] || null) === null, 'a company without figures: no table');
  console.log(`${checks} earnings-day, trend-line and Flo feature checks passed.`);
})().catch((err) => { console.error(err); process.exitCode = 1; });
