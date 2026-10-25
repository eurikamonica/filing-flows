// Flo (web/mascot.js): the question → intents and company, and the answers it writes from the site's model files.
const assert = require('node:assert/strict');
const path = require('node:path');
global.RRGCompanyView = require(path.join(__dirname, '..', 'disclosures', 'docs', 'rrg-company-view.js'));
const M = require(path.join(__dirname, '..', 'web', 'mascot.js'));
let checks = 0;
const ok = (c, m) => { assert.ok(c, m); checks++; };

const ix = { companies: [{ cik: 1045810, ticker: 'NVDA', name: 'NVIDIA CORP', revenue: 4e10 }, { cik: 320193, ticker: 'AAPL', name: 'Apple Inc.', revenue: 9e10 },
  { cik: 1326801, ticker: 'META', name: 'Meta Platforms, Inc.', revenue: 4e10 }, { cik: 1067983, ticker: 'BRK-B', name: 'BERKSHIRE HATHAWAY INC', revenue: 9e10 },
  { cik: 9999, ticker: 'IT', name: 'Gartner Inc', revenue: 1e9 }] };
// intents, in English and Chinese
const has = (q, k) => M.classify(q).includes(k);
ok(has('What is NVDA worth?', 'valuation') && has('NVDA 值多少钱？', 'valuation'), 'valuation');
ok(has('Will META be Leading next week?', 'rotation') && has('META 下周会进入领先象限吗', 'rotation'), 'rotation');
ok(has('AAPL options max pain', 'options') && has('苹果期权的最大痛点', 'options'), 'options');
ok(has("How is NVDA's industry rotating?", 'industry') && !has("How is NVDA's industry rotating?", 'rotation'), 'industry wins over rotation');
ok(has('latest earnings', 'earnings') && has('最新财报', 'earnings') && has('debt and default risk', 'credit') && has('分析师目标价', 'analysts'), 'earnings, credit, analysts');
ok(M.lang('苹果值多少') === 'zh' && M.lang('apple') === 'en', 'language');
// the company: cashtag, ticker, Chinese name, company name, never a stop word
const tk = (q) => (M.findCompany(q, ix) || {}).ticker;
ok(tk('$nvda valuation') === 'NVDA' && tk('Is NVDA cheap?') === 'NVDA' && tk('英伟达估值') === 'NVDA', 'NVDA');
ok(tk('what about apple earnings') === 'AAPL' && tk('苹果最新财报') === 'AAPL' && tk('meta next week') === 'META', 'names');
ok(tk('BRK-B value') === 'BRK-B', 'a class ticker');
ok(tk('IS IT CHEAP?') === undefined, 'stop words are not tickers');
ok(tk('how does it work') === undefined, 'no company');

// the page decides the default questions
const ix2 = Object.assign({}, ix, { companies: ix.companies.map((c) => Object.assign({ sector: c.ticker === 'BRK-B' ? 'financials' : 'tech', sic: c.ticker === 'NVDA' ? 3674 : 1000 }, c)),
  sector_names: { tech: 'Technology' }, industries: [{ id: '3674', name: 'Semiconductors' }] });
const at = (hash, pathname = '/') => M.pageContext(ix2, { hash, pathname });
let cx = at('#c-1045810');
ok(cx.kind === 'company' && cx.co.ticker === 'NVDA' && cx.topic === 'earnings', 'company page → that company, earnings first');
ok(M.chipsFor(cx, true)[0] === 'NVDA 最新财报' && M.chipsFor(cx, true).every((q) => q.includes('NVDA')), 'every default question is about NVDA');
cx = at('#c-1045810-x-options');
ok(cx.topic === 'options' && /期权/.test(M.chipsFor(cx, true)[0]) && M.classify(M.chipsFor(cx, false)[0]).includes('options'), 'options tab → options question first');
ok(at('#c-1045810-x-rotation').topic === 'rotation' && at('#c-1045810-debt').topic === 'credit' && at('#c-1045810-2025-07-27').topic === 'earnings', 'tabs → topics');
cx = at('#i-3674');
ok(cx.kind === 'group' && cx.label === 'Semiconductors' && M.chipsFor(cx, false)[0] === 'What is NVDA worth?', 'industry page → its companies');
cx = at('#s-tech');
ok(cx.label === 'Technology' && cx.cos[0].ticker === 'AAPL', 'sector page → its largest companies');
const inds = { rows: [{ id: 'sic4:3674', label: 'Semiconductors', tickers: ['NVDA', 'AMD'] }] };
cx = M.pageContext(ix2, { hash: '#rotation/ind~sic4%3A3674', pathname: '/disclosures/' }, inds);
ok(cx.kind === 'industry' && cx.co.ticker === 'NVDA' && M.classify(M.chipsFor(cx, false)[0]).includes('industry'), 'industry RRG → industry questions');
cx = M.pageContext(ix2, { hash: '#options', pathname: '/disclosures/' });
ok(cx.kind === 'hub' && cx.topic === 'options' && M.chipsFor(cx, false).slice(0, 3).every((q) => M.classify(q).includes('options')), 'hub options tab → options questions');
ok(M.chipsFor(M.pageContext(ix2, { hash: '#home', pathname: '/' }), false).length === 5, 'home → general questions');
ok(M.greetFor(at('#c-1045810-x-options'), true).includes('NVDA') && M.greetFor(at('#home'), true) === null, 'greeting names the page');
// every default question is understood: it classifies to a topic and names its company
for (const h of ['#c-1045810', '#c-1045810-x-fairvalue', '#c-1045810-x-rotation', '#c-1045810-x-options', '#c-1045810-debt', '#c-1045810-consensus', '#s-tech', '#home']) {
  for (const zh of [true, false]) for (const q of M.chipsFor(at(h), zh)) ok(M.classify(q).length && M.findCompany(q, ix2), `understood: ${q}`);
}

// answers from fixture files
const val = { price: 100, price_date: '2026-10-23', stage: { label: 'Growth' }, dcf: { value: 120 }, mc: { p_above: 0.62, n: 2000 }, pvgo: { growth_share: 0.4 },
  credit: { distress: { pd: 0.004 }, altman_z: 5.1, distance_to_default: 7.2, cds_5y_bps: 80, rating_band: 'A' },
  football: [{ method: 'Stage-weighted value (growth)', low: 95, high: 150, point: 125 }, { method: "Analysts' price targets", low: 90, high: 160, point: 130 }, { method: 'Polymarket implied price', point: 104 }] };
const opt = { spot: 100, max_pain: 98, max_pain_exp: '2026-11-20', path_probs: [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975],
  paths: [{ exp: '2026-11-20', days: 28, q: [80, 84, 88, 94, 100, 106, 112, 116, 120], max_pain: 98, put_wall: 90, call_wall: 110 }] };
const co = { quarters: [1, 2, 3, 4, 5].map((k) => ({ label: `Q${k}`, form: '10-Q', filed: `2026-0${k}-01`, end: `2026-0${k}-01`, doc_url: 'https://www.sec.gov/x', headline: { revenue: 100 * (1 + 0.05 * k), oi: 20, ni: 15 } })) };
const files = { 'data/index.json': ix, 'disclosures/data/research/valuation/c/1045810.json': val, 'disclosures/data/market/options/NVDA.json': opt, 'data/c/1045810.json': co };
global.fetch = async (u) => (files[u] ? { ok: true, json: async () => files[u] } : { ok: false, status: 404, json: async () => null });

(async () => {
  let a = await M.ask('What is NVDA worth?', ix);
  ok(a.html.includes('$125.00') && a.html.includes('25% above') && a.html.includes('62%') && a.mood === 'happy', 'valuation answer: ' + a.html);
  ok(a.links.some(([h]) => h.endsWith('#c-1045810-x-fairvalue')) && a.facts.length >= 4, 'valuation link and facts');
  a = await M.ask('NVDA 期权的最大痛点', ix);
  ok(a.html.includes('最大痛点 $98.00') && a.html.includes('$88.00–$112.00'), 'options answer in Chinese: ' + a.html);
  a = await M.ask('NVDA latest earnings', ix);
  ok(a.html.includes('Q5') && a.html.includes('+19.0% year on year'), 'earnings answer: ' + a.html);
  a = await M.ask('NVDA credit risk', ix);
  ok(a.html.includes('Altman Z 5.10') && a.mood === 'happy', 'credit answer');
  a = await M.ask('NVDA analyst target price', ix);
  ok(a.html.includes('mean $130.00') && a.html.includes('Polymarket implied price $104.00'), 'analysts answer');
  a = await M.ask('Is NVDA Leading next week?', ix);
  ok(/not published/.test(a.html) && a.mood === 'worried', 'no rotation file: said so, never invented');
  a = await M.ask('what is it worth?', ix);
  ok(/Which company/.test(a.html), 'asks which company');
  a = await M.ask('你好', ix);
  ok(a.html.includes('Flo') && a.mood === 'wave', 'help in Chinese');
  a = await M.ask('what is it worth?', ix, ix.companies[0]);
  ok(a.company && a.company.ticker === 'NVDA', 'no company named: the page company is used');
  a = await M.ask('AAPL', ix);
  ok(/not published/.test(a.html), 'a company without files');
  console.log(`${checks} mascot checks passed.`);
})().catch((e) => { console.error(e); process.exitCode = 1; });
