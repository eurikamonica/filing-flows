// Flo's research answers (web/flo-insights.js through web/mascot.js): the new intents, market questions, follow-ups,
// misspelt names and the next questions, each answered from fixture files shaped like the site's.
const assert = require('node:assert/strict');
const path = require('node:path');
global.RRGCompanyView = require(path.join(__dirname, '..', 'disclosures', 'docs', 'rrg-company-view.js'));
const M = require(path.join(__dirname, '..', 'web', 'mascot.js'));
const I = require(path.join(__dirname, '..', 'web', 'flo-insights.js'));
let n = 0;
const ok = (c, m) => { assert.ok(c, m); n++; };
const has = (q, k) => M.classify(q).includes(k);

// intents, English and Chinese; a more specific one replaces the model's
ok(has('Who owns NVDA?', 'owners') && has('谁持有英伟达？', 'owners') && has('Are hedge funds buying AAPL', 'owners'), 'owners');
ok(has('Are NVDA insiders buying?', 'insiders') && has('CEO sold shares', 'insiders') && has('英伟达高管减持', 'insiders'), 'insiders');
ok(has('Congress trades in NVDA', 'congress') && has('Did Pelosi buy NVDA', 'congress') && has('议员买了苹果吗', 'congress'), 'congress');
ok(has('NVDA latest 8-K', 'events') && has('Latest deals and material 8-Ks', 'events') && has('苹果最近的收购', 'events'), 'events');
ok(has('NVDA free cash flow', 'cashflow') && has('How much does AAPL spend on buybacks', 'cashflow') && has('苹果自由现金流', 'cashflow'), 'cash flow');
ok(has('How does Apple make money?', 'segments') && has('苹果怎么赚钱', 'segments') && !has('How does Apple make money?', 'earnings'), 'segments, not the earnings');
ok(has('When does NVDA report next?', 'nextEarnings') && has('NVDA earnings date', 'nextEarnings') && !has('NVDA earnings date', 'earnings') && has('英伟达下次财报什么时候', 'nextEarnings'), 'next earnings replaces earnings');
ok(has('Who reports earnings this week?', 'nextEarnings') && has('本周哪些公司发财报？', 'nextEarnings'), 'earnings this week');
ok(has('NVDA customers and suppliers', 'ties') && has('苹果的供应商', 'ties'), 'ties');
ok(has('TSLA short interest', 'shorts') && has('Most shorted stocks', 'shorts') && !has('TSLA short interest', 'opportunity'), 'short interest, not shorting odds');
ok(has("How rare is NVDA's latest move?", 'moves') && has('Most unusual moves today', 'moves') && has('英伟达今天为什么跌', 'moves'), 'moves');
ok(has('Does NVDA meet its guidance?', 'guidanceRecord') && has('Who raised guidance lately?', 'guidanceRecord') && !has('Does NVDA meet its guidance?', 'calls'), 'guidance record');
ok(has('GOOGL investment gains', 'investments') && has('谷歌投资收益', 'investments'), 'investments');
ok(has('What is NVDA worth?', 'valuation') && !has('What is NVDA worth?', 'owners'), 'old intents unchanged');

// market words, follow-ups, misspelt names
ok(I.isMarket('Biggest insider buying lately', null, false) && !I.isMarket('Are its insiders buying?', null, false) && !I.isMarket('insiders buying?', null, true)
  && I.isMarket('Which stocks have the biggest insider buying?', null, true), 'market questions (on a company page only the strong words)');
ok(I.isFollow('what about AMD?') && I.isFollow('AMD 呢？') && I.isFollow('and Apple?') && !I.isFollow('What is AMD worth and who owns it and is it cheap compared with peers?'), 'follow-ups');
const ix = { companies: [{ cik: 1, ticker: 'NVDA', name: 'NVIDIA CORP', revenue: 4e10, sic: '3674' }, { cik: 2, ticker: 'AAPL', name: 'Apple Inc.', revenue: 9e10 },
  { cik: 3, ticker: 'MSFT', name: 'MICROSOFT CORP', revenue: 7e10 }, { cik: 4, ticker: 'GOOGL', name: 'Alphabet Inc.', revenue: 8e10 },
  { cik: 5, ticker: 'FFLO', name: 'Free Flow Inc', revenue: 1e6 }, { cik: 6, ticker: 'MGM', name: 'MGM Resorts International', revenue: 4e9 }, { cik: 7, ticker: 'TDAY', name: 'USA TODAY Co', revenue: 6e8 }] };
const fz = (q) => (I.fuzzyCompany(q, ix) || {}).ticker;
ok(fz('nvidea free cash flow') === 'NVDA' && fz('microsft revenue') === 'MSFT' && fz('appel short interest') === 'AAPL' && fz('google customers') === 'GOOGL', 'misspelt and everyday names');
ok(I.lev('appel', 'apple') === 1 && I.lev('nvidia', 'nvidea') === 1, 'a swap is one edit');

// answers from fixtures
const DAY = (d) => new Date(Date.now() - d * 864e5).toISOString().slice(0, 10);
const files = {
  'data/index.json': ix,
  'disclosures/data/holders/NVDA.json': { institutional: [{ manager: 'VANGUARD GROUP INC', value_usd: 4e11, status: 'INCREASE', period: '2026-06-30' }, { manager: 'BlackRock, Inc.', value_usd: 3.8e11, status: 'DECREASE', period: '2026-06-30' }],
    flows: { buyers: 2912, sellers: 2270, new: 251, exits: 177, usd_net: 3.0e10, holders: 5383, label: 'Q2 2026 — quarter ended 2026-06-30' },
    officials: [{ person: 'Jane Doe', kind: 'transaction', transaction_type: 'purchase', amount_min: 1001, amount_max: 15000, date: DAY(5), filed_date: DAY(1) }],
    form144: [{ filed: DAY(20), seller_name: 'A Seller', value: 7e6 }],
    short: [['2026-09-30', 3.1e8, 1.0, 3.0, 1e8], ['2026-10-15', 3.0e8, -3.1, 2.9, 1.04e8]] },
  'disclosures/data/market/insiders.json': { since: '2026-07-15', summary: [{ ticker: 'NVDA', cik: '1', buys: 3, buy_value: 2e6, sells: 1, sell_value: 5e5, buyers30: 3, cluster: true },
    { ticker: 'LONA', cik: '9', buys: 1, buy_value: 9.9e9 }], latest: [{ ticker: 'NVDA', issuer_cik: '1', insider: 'J Huang', title: 'CEO', code: 'P', value: 1e6, date: DAY(3) }] },
  'disclosures/data/market/events8k.json': { days: 30, rows: [{ cik: '1', company: 'NVIDIA CORP', filed: DAY(2), items: ['1.01', '9.01'], topics: ['deal'], headline: 'NVIDIA to acquire X', url: 'https://www.sec.gov/x' }] },
  'data/c/1.json': { quarters: [{ label: 'Q2 FY27', end: '2026-07-26', form: '10-Q', filed: '2026-08-26', headline: { revenue: 100, yoy: 106, om: 66.2, ni: 60, ocf: 24 },
      analysis: ['Revenue was $100 in Q2 FY27, up 106% year over year.', 'Operating profit was $66, a 66.2% margin (up 5.4 points year over year).', 'Operating cash flow was $24.'], nodes: [{ id: 'revenue', name: 'Revenue', v: 100 }, { id: 'a', name: 'Data Center', v: 90, y: 40, color: 'rev' }, { id: 'b', name: 'Gaming', v: 10, y: 9, color: 'rev' }, { id: 'c', name: 'Research &amp; development', v: 12, y: 8, color: 'cost' }],
    links: [{ s: 'a', t: 'revenue', v: 90 }, { s: 'b', t: 'revenue', v: 10 }] },
    { label: 'Q1 FY27', end: '2026-04-26', form: '10-Q', filed: '2026-05-28', headline: { revenue: 80, yoy: 85, om: 60, ni: 45, ocf: 30 } },
    { label: 'Q2 FY26', end: '2025-07-27', form: '10-Q', filed: '2025-08-27', headline: { revenue: 48, yoy: 56, om: 61, ni: 26, ocf: 15 } }],
    quality: { cap: { q: [{ end: '2025-07-31', label: 'Q2 FY26', items: { ocf: 15, capex: -2 } }, { end: '2026-07-31', label: 'Q2 FY27', items: { ocf: 24, capex: -3 } }],
      ttm: { end: '2026-07-31', label: 'TTM', items: { ocf: 100, capex: -10, buyback: -50, div: -1 } } } } },
  'disclosures/data/research/earnings/c/NVDA.json': { report_date: DAY(-14), consensus: { eps: 2.47, rev: 1.09e11, year_ago_eps: 1.3 }, beat_rate: 0.9, model: { p: 0.8 }, implied: { move: 0.053 },
    history: [{ reported: DAY(80), est: 2.09, act: 2.22, surprise: 0.062, move: 0.07 }] },
  'data/network/c/1.json': { customers: [{ pct: 0.76, usd: 1.6e11, how: 'XBRL, unnamed' }, { t: 'HPQ', name: 'HP INC' }], suppliers: [{ t: 'FN', pct: 0.16 }] },
  'disclosures/data/research/paths/moves/index.json': { as_of: DAY(1), breadth: { down5: 0.15, up5: 0.04 }, fields: ['key', 'ticker', 'kind', 'cik', 'as_of', 'd0', 'move', 'pct', 'z', 'every', 'sim21'],
    rows: [['NVDA', 'NVDA', 'stock', 1, DAY(1), '2016-01-04', -0.042, 6.1, -2.0, 13, [347, 0.044, 0.58]], ['AAPL', 'AAPL', 'stock', 2, DAY(1), '2016-01-04', 0.03, 97, 1.8, 30, null]] },
  'disclosures/data/market/guidance-board.json': { rows: [{ t: 'NVDA', cik: 1, n: 26, rate: 0.92, beat: 15, miss: 2, raised: 0, lowered: 0 }], recent: [[DAY(1), 'AAPL', '2', 'raised', 'Apple raises outlook', 'https://x']] },
  'disclosures/data/research/earnings/index.json': { fields: ['ticker', 'name', 'report_date', 'days_to', 'eps'], rows: [['AAPL', 'Apple', DAY(-1), 1, 1.98], ['NVDA', 'NVIDIA', DAY(-14), 14, 2.47]] },
  'data/c/2.json': { quarters: [{ label: 'Q3 FY26', headline: { revenue: 109, yoy: 16, om: 32.6, ni: 30 } }],
    quality: { cap: { q: [{ end: '2026-06-27', label: 'Q3 FY26', items: { ocf: 34, capex: -2 } }], ttm: { label: 'TTM', items: { ocf: 140, capex: -10 } } } } },
  'disclosures/data/market/officials-trades.json': { summary: { d90: [{ ticker: 'NVDA', buys: 3, sells: 6, people_buy: ['Jane Doe'] }] },
    trades: [{ person: 'Nancy Pelosi', ticker: 'NVDA', type: 'purchase', amount_min: 1000001, amount_max: 5000000, date: '2026-07-24', filed_date: '2026-08-21' }] },
  'disclosures/data/research/valuation/c/1.json': { price: 200, price_date: '2026-10-28', inputs: { mcap: 5e12, ev: 4.9e12, eps: 8, debt: 3e10, cash: 7e10, ebitda: 2e11 },
    peers: { pe: { n: 32, p25: 20, p50: 41, p75: 70, own: 25 } } },
  'disclosures/data/market/rotation.json': { fields: ['cal', 'rs', 'revg'], sectors: { technology: { name: 'Technology', p: [['CY2026Q3', 64, 24]] }, health: { name: 'Health Care', p: [['CY2026Q3', 65, 11]] },
    energy: { name: 'Energy', p: [['CY2026Q3', 58, 19]] }, utilities: { name: 'Utilities', p: [['CY2026Q3', 43, 9]] } } },
};
global.fetch = async (u) => (files[u] ? { ok: true, json: async () => files[u] } : { ok: false, status: 404, json: async () => null });
const text = (a) => a.html.replace(/<[^>]+>/g, '');

(async () => {
  let a = await M.ask('Who owns NVDA?', ix);
  ok(a.intents[0] === 'owners' && /VANGUARD GROUP INC \$400\.0B \(added\)/.test(text(a)) && /2,912 managers bought/.test(text(a)) && /holders/.test(a.links[0][0]), 'owners answer');
  ok(a.actions.length === 3 && a.actions.every((x) => /NVDA/.test(x.question)) && M.classify(a.actions[0].question).length, 'next questions about the same company, each understood');
  a = await M.ask('Are NVDA insiders buying?', ix);
  ok(/bought \$2M \(3 trades\)/.test(text(a)) && /several insiders bought within 30 days/.test(text(a)) && /J Huang \(CEO\) bought \$1M/.test(text(a)) && /Form 144/.test(text(a)), 'insiders answer');
  a = await M.ask('Congress trades in NVDA', ix);
  ok(/1 buy and 0 sales/.test(text(a)) && /Jane Doe bought \$1K–\$15K/.test(text(a)), 'congress answer');
  a = await M.ask('NVDA latest 8-K', ix);
  ok(/material agreement — NVIDIA to acquire X/.test(text(a)), '8-K answer');
  a = await M.ask('NVDA free cash flow', ix);
  ok(/free cash flow \$21/.test(text(a)) && /\(\$13 a year earlier\)/.test(text(a)) && /buybacks \$50/.test(text(a)), 'cash flow answer');
  a = await M.ask('How does NVDA make money?', ix);
  ok(/Data Center \$90 · 90% · Y\/Y \+125%/.test(text(a)) && /Fastest-growing large line: Data Center/.test(text(a)), 'segments answer');
  a = await M.ask('When does NVDA report next?', ix);
  ok(/in 14 days/.test(text(a)) && /EPS \$2\.47/.test(text(a)) && /±5\.3%/.test(text(a)), 'next earnings answer');
  a = await M.ask('NVDA customers and suppliers', ix);
  ok(/an unnamed customer 76% \$160\.0B/.test(text(a)) && /HPQ/.test(text(a)) && /FN 16%/.test(text(a)), 'customers and suppliers');
  a = await M.ask('NVDA short interest', ix);
  ok(/300\.0M shares/.test(text(a)) && /2\.9 days/.test(text(a)), 'short interest');
  a = await M.ask("How rare is NVDA's latest move?", ix);
  ok(/moved −4\.2%/.test(text(a)) && /bottom 6\.1%/.test(text(a)) && /347 days like it/.test(text(a)), 'move odds');
  a = await M.ask('Does NVDA meet its guidance?', ix);
  ok(/met or beat 92% of the 26/.test(text(a)) && !/raised guidance 0/.test(text(a)), 'guidance record, no empty counts');
  // market questions: no company named
  a = await M.ask('Biggest insider buying lately', ix);
  ok(!a.company && /NVDA \$2M/.test(text(a)) && !/LONA/.test(text(a)), 'market: insider buying, a misread billion left out');
  a = await M.ask('Who reports earnings this week?', ix);
  ok(!a.company && /1 company reports (in the next seven days|this week)/.test(text(a)) && /AAPL \(\$1\.98\)/.test(text(a)) && a.actions.length === 3, 'market: earnings this week (not MGM Resorts)');
  a = await M.ask('Most unusual moves today', ix);
  ok(!a.company && /rarest falls/.test(text(a)) && /15% of stocks/.test(text(a)), 'market: unusual moves (not USA Today)');
  a = await M.ask('What is Congress trading?', ix);
  ok(/NVDA 3 \/ 6/.test(text(a)), 'market: Congress');
  a = await M.ask('Who raised guidance lately?', ix);
  ok(/AAPL raised/.test(text(a)), 'market: guidance changes');
  // a follow-up keeps the topic; a misspelt name still finds the company; Chinese
  await M.ask('Who owns NVDA?', ix);
  a = await M.ask('what about AAPL?', ix);
  ok(a.company && a.company.ticker === 'AAPL' && a.intents[0] === 'owners', 'follow-up asks the same thing for AAPL');
  a = await M.ask('nvidea free cash flow', ix);
  ok(a.company.ticker === 'NVDA' && /free cash flow/.test(text(a)), 'misspelt name');
  a = await M.ask('英伟达下次财报什么时候？', ix);
  ok(/下次财报/.test(text(a)) && /还有 14 天/.test(text(a)) && /。$/.test(text(a).trim()), 'Chinese next earnings');
  a = await M.ask('NVDA', ix);
  ok(a.intents.join() === 'earnings,segments,valuation', 'just a ticker: the overview leads with its earnings and how it makes money');
  // a briefing, why, a trend, one quarter, a definition, any comparison
  ok(has('Brief me on NVDA', 'brief') && has('英伟达速览', 'brief') && !has('NVDA income statement summary', 'brief') && has('NVDA income statement summary', 'earnings'), 'briefing, not the income statement');
  a = await M.ask('Brief me on NVDA', ix);
  ok(/at a glance/.test(text(a)) && /Business: \$100 revenue in Q2 FY27/.test(text(a)) && /Next report/.test(text(a)) && /Funds: 2,912/.test(text(a)) && /Insiders: bought \$2M/.test(text(a)), 'briefing from six files');
  a = await M.ask("Why did NVDA's margin improve?", ix);
  ok(a.intents[0] === 'why' && /66\.2% margin/.test(text(a)) && !/Revenue was/.test(text(a)) && /Largest changes against a year earlier: Research & development \+\$4/.test(a.html.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&')) && !/Data Center \+/.test(text(a)), 'why the margin: its paragraph and the cost lines that moved');
  a = await M.ask("Why did NVDA's revenue grow?", ix);
  ok(/Revenue was \$100/.test(text(a)) && /Data Center \+\$50/.test(text(a)), 'why the revenue: its paragraph and the revenue lines');
  a = await M.ask('NVDA revenue trend', ix);
  ok(a.intents[0] === 'trend' && /last 3 quarters/.test(text(a)) && /From \$48 to \$100 \(\+108%\)/.test(text(a)) && /[▁-█]{3}/.test(a.html), 'trend with a sparkline');
  a = await M.ask('NVDA Q1 FY27', ix);
  ok(/NVDA Q1 FY27/.test(text(a)) && /revenue \$80/.test(text(a)), 'one quarter by its label');
  a = await M.ask('What is a 13F?', ix);
  ok(a.intents[0] === 'glossary' && /investment manager with \$100 million/.test(text(a)), 'a definition');
  a = await M.ask('什么是自由现金流', ix);
  ok(/经营现金流减去资本支出/.test(text(a)), 'a definition in Chinese');
  a = await M.ask('What is NVDA worth?', ix);
  ok(!(a.intents || []).includes('glossary'), 'a company question is not a definition');
  a = await M.ask('NVDA vs AAPL free cash flow', ix);
  ok(a.intents.join() === 'compare,cashflow' && /NVDA/.test(text(a)) && /AAPL/.test(text(a)) && /free cash flow \$21/.test(text(a)) && /free cash flow \$32/.test(text(a)), 'compare any topic');
  // what it does, its multiples and debt, the sectors, the largest companies, one official's trades
  files['data/c/1.json'].profile = { industry: 'Semiconductors', sic: '3674', sector: 'technology', exchanges: ['Nasdaq'], fye: '0131' };
  files['data/c/1.json'].intro = { text: 'NVIDIA builds accelerated computing. It sells GPUs. More text.', source: '10-K' };
  a = await M.ask('What does NVDA do?', ix);
  ok(a.intents[0] === 'profile' && /“NVIDIA builds accelerated computing\. It sells GPUs\.”/.test(text(a)) && /fiscal year ends Jan 31/.test(text(a)), 'what it does, in its own words');
  a = await M.ask('NVDA P/E and market cap', ix);
  ok(a.intents[0] === 'multiples' && /market value \$5\.00T/.test(text(a)) && /P\/E 25\.0× \(industry median 41\.0×/.test(text(a)) && /middle half of its industry/.test(text(a)), 'multiples against the industry');
  ok((M.findCompany('Costco P/E', { companies: [{ cik: 9, ticker: 'P', name: 'P Corp' }, { cik: 8, ticker: 'COST', name: 'COSTCO WHOLESALE CORP' }] }) || {}).ticker === 'COST', 'P/E is not the ticker P');
  a = await M.ask('How much debt does NVDA have?', ix);
  ok(/\$30\.0B of debt and \$70\.0B of cash/.test(text(a)) && /net cash \$40\.0B/.test(text(a)), 'debt and cash');
  a = await M.ask('Which sectors are leading?', ix);
  ok(!a.company && /Health Care 65/.test(text(a)) && text(a).indexOf('Health Care') < text(a).indexOf('Technology'), 'sectors, strongest first');
  a = await M.ask('largest companies by revenue', ix);
  ok(!a.company && /AAPL \$90\.0B/.test(text(a)) && text(a).indexOf('AAPL') < text(a).indexOf('MSFT'), 'the largest companies');
  a = await M.ask('Did Pelosi buy anything?', ix);
  ok(/Nancy Pelosi's latest disclosed trades/.test(text(a)) && /NVDA bought \$1M–\$5M/.test(text(a)), "one official's trades by name");
  a = await M.ask('What is EBITDA?', ix);
  ok(/Earnings before interest/.test(text(a)), 'EBITDA defined');
  console.log(`${n} Flo insight checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
