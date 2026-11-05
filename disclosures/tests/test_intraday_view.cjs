// intraday-view.js: the live layer of the hub's Move odds — the session's status from live.json, a card's lead (today's
// move so far, its rank at this time of day, the days most like it to 4 pm, the price against VWAP), the asset's panel
// (today's path and VWAP with the similar days' fan, every day's move by then, the move to the close against every
// day's, the days after, the odds against VWAP and their chart), the banner, and the in-place painting (the overnight
// update takes over after the close). No browser, no network.
const assert = require('node:assert/strict');
const V = require('../docs/intraday-view.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const clean = (h, m) => ok(!/NaN|undefined|Infinity|\[object/.test(h), m + ' shows NaN/undefined');
const q = (p50, s = 0.004) => ({ p10: p50 - 2 * s, p25: p50 - s, p50, p75: p50 + s, p90: p50 + 2 * s, n: 60, up: 0.55 });
const fan = [[2, 0, 0, 0, 0, 0], [3, -0.003, -0.001, 0.0005, 0.002, 0.004], [4, -0.004, -0.0015, 0.0008, 0.003, 0.005], [5, -0.005, -0.002, 0.001, 0.0035, 0.006],
  [6, -0.006, -0.002, 0.0012, 0.004, 0.007], [7, -0.007, -0.0025, 0.0012, 0.0045, 0.008]];
const odds = {
  mark: '11:30', j: 2, days: 498, from: '2024-11-06', pct: 22.6, every: 4.4, dist: [3, 2, 4, 8, 20, 70, 160, 150, 50, 18, 8, 3, 1, 1],
  rest_edges: [-0.01, -0.0075, -0.005, -0.0025, 0, 0.0025, 0.005, 0.0075, 0.01],
  similar: { n: 60, rest: q(0.0012), above: 0.57, green: 0.38, next: { 1: q(0.001, 0.01), 5: q(0.003, 0.02), 21: q(0.009, 0.04) }, fan, close: [667.4, 672.9, 678.2], moves_by_then: [-0.0061, -0.0035], rest_dist: [1, 2, 4, 8, 12, 14, 10, 5, 3, 1] },
  base: { n: 498, rest: q(0.0004), above: 0.52, green: 0.55, next: { 1: q(0.0005, 0.01), 5: q(0.002, 0.02), 21: q(0.01, 0.04) }, rest_dist: [10, 20, 40, 80, 100, 110, 75, 35, 20, 8] },
};
const vq = (p50, s = 0.003) => ({ ...q(p50, s), n: 60 });
const vwapOdds = {
  mark: '11:30', j: 2, days: 498, from: '2024-11-06', gap: -0.001174, pct: 31.4, edges: [-0.004, -0.003, -0.002, -0.001, 0, 0.001, 0.002, 0.003, 0.004],
  bins: [[5, 0.2, 0.4, -0.001], [12, 0.25, 0.5, 0.0005], [30, 0.33, 0.6, 0.0008], [70, 0.4, 0.66, 0.0006], [120, 0.47, 0.7, 0.0004], [118, 0.55, 0.72, 0.0002], [80, 0.6, 0.66, 0.0001], [40, 0.66, 0.6, -0.0002], [16, 0.7, 0.55, -0.0004], [7, 0.75, 0.5, -0.0006]],
  similar: { n: 60, above: 0.42, back: 0.68, end: vq(-0.0005), rest: vq(0.0003), next: { 1: q(0.0008, 0.01), 5: q(0.002, 0.02), 21: q(0.008, 0.04) }, gaps: [-0.0015, -0.0009] },
  base: { n: 498, above: 0.52, back: 0.66, end: vq(0.0002), rest: vq(0.0004), next: { 1: q(0.0005, 0.01), 5: q(0.002, 0.02), 21: q(0.01, 0.04) } },
};
const doc = {
  schema: 'intraday.v1', generated_at: '2026-11-05T16:25:30+00:00', source: 'Yahoo Finance chart API (prices as published; some may be delayed)',
  marks: ['09:30', '10:30', '11:30', '12:30', '13:30', '14:30', '15:30', '16:00'], edges: [-0.03, -0.025, -0.02, -0.015, -0.01, -0.005, 0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03], k: 60,
  session: { date: '2026-11-05', start: '2026-11-05T09:30:00-05:00', end: '2026-11-05T16:00:00-05:00', open: true, short: false },
  assets: {
    SPY: { key: 'SPY', name: 'S&P 500 (SPY)', kind: 'market', symbol: 'SPY', price: 672.11, prev: 675.3, move: -0.004724, time: '2026-11-05T11:25:00-05:00', today: true,
      path: Array.from({ length: 23 }, (_, i) => [5 * (i + 1), -0.0002 * (i + 1)]), hi: 0.0012, lo: -0.0051, odds,
      vwap: 672.9, vs_vwap: -0.001174, vwap_path: Array.from({ length: 23 }, (_, i) => [5 * (i + 1), -0.00015 * (i + 1)]), vwap_odds: vwapOdds },
    XLE: { key: 'XLE', name: 'Energy sector (XLE)', kind: 'sector', price: 88.2, prev: 90.1, move: -0.0211, time: '2026-11-05T11:25:00-05:00', today: true, path: [[5, -0.01], [10, -0.02]], hi: 0, lo: -0.022 },
    OLD: { key: 'OLD', name: 'Yesterday only', kind: 'style', price: 10, prev: 9.9, move: 0.0101, time: '2026-11-04T16:00:00-05:00', today: false, path: [] },
  },
};
const T = (iso) => Date.parse(iso);
const realNow = Date.now;
const at = (iso, fn) => { Date.now = () => T(iso); try { return fn(); } finally { Date.now = realNow; } };
const LIVE = '2026-11-05T16:30:00Z', STALE = '2026-11-05T16:50:00Z', DOWN = '2026-11-05T18:30:00Z', AFTER = '2026-11-05T22:00:00Z', NEXT = '2026-11-06T15:00:00Z';
const closedDoc = { ...doc, generated_at: '2026-11-05T21:02:00+00:00', assets: { ...doc.assets, SPY: { ...doc.assets.SPY, move: -0.0062, price: 671.1, time: '2026-11-05T16:00:00-05:00', odds: { ...odds, mark: '16:00', j: 7, pct: 18.2, rest_edges: null, similar: { ...odds.similar, fan: [[7, 0, 0, 0, 0, 0]] } } } } };
const shortDoc = { ...doc, session: { ...doc.session, end: '2026-11-05T13:00:00-05:00', short: true } };

// the session's status
ok(V.status(doc, T(LIVE)) === 'live', 'on, fresh: live');
ok(V.status(doc, T(STALE)) === 'stale', 'on, 25 minutes since the last scan: stale');
ok(V.status(doc, T(DOWN)) === 'down', 'on, two hours since the last scan: down');
ok(V.status(closedDoc, T(AFTER)) === 'closed', 'after 4 pm, a scan after the close: closed');
ok(V.status(doc, T(AFTER)) === null, 'after 4 pm with no scan near the close: nothing');
ok(V.status(closedDoc, T(NEXT)) === null, 'the next morning: nothing live');
ok(V.status(null) === null && V.status({}) === null, 'no file');
ok(V.status({ ...doc, assets: { OLD: doc.assets.OLD } }, T(LIVE)) === null, 'no reading of today (before the open, a holiday): nothing');
ok(!V.isToday(doc.assets.OLD, doc) && V.isToday(doc.assets.SPY, doc), "yesterday's last price is no reading of today");
ok(!V.isToday({ move: 0.01, time: '2026-11-05T09:10:00-05:00' }, doc) && V.isToday({ move: 0.01, time: '2026-11-05T09:35:00-05:00' }, doc), 'an older file: by the time against the open');

// a card's lead
at(LIVE, () => {
  const c = V.cardHtml(doc.assets.SPY, doc);
  clean(c, 'the card');
  ok(c.startsWith('<b class="iv-down">−0.47%<span class="iv-at"><span class="iv-dot"></span>11:25</span></b><div class="mvh-meter"'), 'the move so far leads, the time beside it, with its percentile meter');
  ok(c.includes('<i>bottom 22.6% so far</i>'), 'its rank among the days at that time');
  ok(c.includes('to 4 pm, 60 days like it:<br><span class="iv-up">+0.12%</span> · 57% higher'), 'the days most like it to the close');
  ok(c.includes('<i>vs VWAP <span class="iv-down">−0.12%</span><br>68% came back to it</i>'), 'the price against VWAP, and how often the days like it came back');
  const x = V.cardHtml(doc.assets.XLE, doc);
  ok(x.includes('−2.11%') && !x.includes('to 4 pm') && !x.includes('mvh-meter'), 'no history: the move and the time alone');
  ok(!V.cardHtml(doc.assets.SPY, shortDoc).includes('to 4 pm'), 'an early close: no odds to 4 pm');
  const low = { ...doc.assets.SPY, odds: { ...odds, pct: 0.0, every: 997 }, vwap_odds: { ...vwapOdds, pct: 0.0 } };
  ok(V.cardHtml(low, doc).includes('<i>the lowest of 498 days by then</i>'), 'beyond every day on file: said, not "bottom 0.0%"');
  const ld = V.detailHtml(low, doc);
  ok(ld.includes('<b>the lowest</b> of its 498 days since Nov 6, 2024 at that time of day — further than any day on file') && ld.includes('<b>the furthest below</b> of its 498 days by 11:30 am'), 'and in the panel');
});
at(STALE, () => { const c = V.cardHtml(doc.assets.SPY, doc); ok(c.includes('11:25 (delayed)') && !c.includes('iv-dot'), 'behind: the time said, no live dot'); });
at(AFTER, () => {
  const c = V.cardHtml(closedDoc.assets.SPY, closedDoc);
  ok(c.includes('−0.62%<span class="iv-at">at the close</span></b>') && c.includes('<i>bottom 18.2% day</i>') && c.includes('the day after days like it: <span class="iv-up">+0.10%</span> · 55% rose') && !c.includes('to 4 pm'), "after the close: today's close and the day after");
});

// the asset's panel
at(LIVE, () => {
  const d = V.detailHtml(doc.assets.SPY, doc);
  clean(d, 'the panel');
  for (const want of ['S&amp;P 500 (SPY) today: <b class="iv-down">−0.47%</b> at 11:25 am New York time', '672.11, the previous close 675.30', "today's high +0.12%, low −0.51%",
    '<h4>So far</h4>', 'by about 11:30 am: in the <b>bottom 22.6%</b> of its 498 days since Nov 6, 2024 at that time of day', 'a fall this far by then comes about once in 4.4 days',
    "Every day's move by 11:30 am from the previous close, in bands of 0.5%", '<h4>To the close</h4>', '(−0.61% to −0.35% by then)', 'went a median <b class="iv-up">+0.12%</b> further by 4 pm (10–90%: −0.68% to +0.92%)',
    '<b>57%</b> closed above that price and 38% above the previous close', 'a close near <b>672.90</b> (10–90%: 667.40–678.20)', 'Every day from 11:30 am: a median +0.04%, 52% higher',
    'the 60 days like it', 'bands of 0.25%', '<h4>The days after</h4>', '<th>The 60 days like it</th><th>Every day</th>', '<td>Next day</td>', '<td>21 days</td><td><span class="iv-up">+0.90%</span> · 55% rose<small>−7.1% to +8.9%</small>', 'History, not a forecast'])
    ok(d.includes(want), `the panel lacks “${want}”`);
  ok((d.match(/<svg/g) || []).length === 4, "four charts: today's path and fan, every day's move by then, the move to the close, the odds against VWAP by its gap");
  ok((d.match(/<polygon/g) || []).length === 2 && /<polyline[^>]+stroke-dasharray/.test(d), "the fan's two bands and its dashed median");
  ok(/>today<\/text>/.test(d), "today's band labelled");
  ok((d.match(/<path d="M/g) || []).length === 14 + 10, 'fourteen bands of every day by then, ten bands to the close (rounded data ends)');
  ok(/<polyline points="[^"]+" fill="none" stroke="var\(--rot-1,#2a78d6\)"/.test(d) && d.includes('</span>VWAP'), "today's VWAP drawn and keyed");
  for (const want of ['<h4>Against VWAP</h4>', "<b>0.12%</b> below today's VWAP (672.90) at 11:25 am", 'the <b>bottom 31.4%</b> of its 498 days by 11:30 am', '(−0.15% to −0.09%)',
    '<b>42%</b> closed above their VWAP, <b>68%</b> came back to it before the close', 'a median <span class="iv-up">+0.03%</span> to 4 pm', 'Every day from 11:30 am: 52% closed above VWAP, 66% came back',
    'The day after such days: a median <span class="iv-up">+0.08%</span>, 55% rose', 'came back to VWAP before the close — every day by its gap to VWAP at 11:30 am, bands of 0.1%'])
    ok(d.includes(want), `the VWAP section lacks “${want}”`);
  ok((d.match(/class="iv-hit"/g) || []).length === 23 + 5 + 14 + 10 + 10, 'a hover column for each five minutes, each mark ahead, each band of the three histograms and of the VWAP chart');
  ok(/data-tip="11:25 am\n−0\.46% today\n−0\.35% VWAP"/.test(d), "a column's tooltip: the time, today, its VWAP");
  const vc = V.vwapChart(vwapOdds);
  ok((vc.match(/<polyline/g) || []).length === 2 && (vc.match(/<circle/g) || []).length === 2 * 8 && />today<\/text>/.test(vc), 'the probability chart: two series, no point for a band of under eight days, today marked');
  ok(vc.includes('too few to say') && vc.includes('−0.2% to −0.1% from VWAP · today · 70 days\n40% closed above VWAP\n66% came back to VWAP'), "a band's tooltip; today's band");
  ok(!V.detailHtml({ ...doc.assets.SPY, vs_vwap: undefined, vwap: undefined }, doc).includes('Against VWAP'), 'no volume: no VWAP');
  ok(V.detailHtml(doc.assets.XLE, doc).includes('not on file yet'), 'no history yet: said');
  const narrow = V.chart(doc.assets.SPY, true, 360), wide = V.chart(doc.assets.SPY, true, 760);
  ok(narrow.includes('viewBox="0 0 360 200"') && narrow.includes('>11:30<') && !narrow.includes('>10:30<') && !narrow.includes('>3:30<') && narrow.includes('>4 pm<'), 'a phone: the chart at its width, every other hour');
  ok(wide.includes('viewBox="0 0 760 230"') && wide.includes('>10:30<') && wide.includes('>3:30<'), 'a wide panel: every hour');
  const s = V.detailHtml(doc.assets.SPY, shortDoc);
  ok(s.includes('closes early, at 1:00 pm') && !s.includes('<h4>To the close</h4>') && (s.match(/<polygon/g) || []).length === 0, 'an early close: said, no odds to 4 pm, no fan');
  ok(s.includes("the odds against VWAP of full days don't apply"), 'an early close: no VWAP odds either');
});
at(AFTER, () => {
  const d = V.detailHtml(closedDoc.assets.SPY, closedDoc);
  clean(d, 'the panel after the close');
  ok(d.includes('closed at 671.10, <b class="iv-down">−0.62%</b> on the day') && d.includes('<h4>The day</h4>') && !d.includes('<h4>To the close</h4>') && d.includes('<h4>The days after</h4>'), "after the close: the day and the days after");
});

// the banner
at(LIVE, () => { const b = V.banner(doc, null, '2026-11-04'); ok(b.includes('<b>Live</b>, 11:25 am New York time') && b.includes('60 days most like it'), 'the live banner'); });
at(STALE, () => ok(V.banner(doc, 'HTTP 404').includes('at 11:25 am New York time (HTTP 404)'), 'behind: the last reading and the error'));
at(DOWN, () => ok(V.banner(doc).includes('stopped at 11:25 am'), 'down: the last close'));
at(AFTER, () => {
  ok(V.banner(closedDoc, null, '2026-11-04').includes("Today's session is over"), "after the close, before tonight's update");
  ok(V.banner(closedDoc, null, '2026-11-05') === '', "tonight's update is in: no banner");
});

// painting in place
const card = () => ({ classList: { on: false, toggle(k, v) { this.on = v; } } });
const el = (data) => { const c = card(); return { dataset: data, innerHTML: 'x', hidden: false, card: c, closest: () => c }; };
const cards = [el({ ivc: 'SPY', asof: '2026-11-04' }), el({ ivc: 'QQQ', asof: '2026-11-04' }), el({ ivc: 'OLD', asof: '2026-11-04' })];
const panels = [el({ ivd: 'SPY', asof: '2026-11-04' })], banners = [el({ ivb: '', asof: '2026-11-04' })];
const root = { querySelectorAll: (sel) => (sel === '[data-ivc]' ? cards : sel === '[data-ivd]' ? panels : sel === '[data-ivb]' ? banners : []) };
V.set(doc);
at(LIVE, () => {
  V.paint(root);
  ok(cards[0].innerHTML.includes('−0.47%') && cards[0].card.classList.on, 'a card of an asset in the file leads with today');
  ok(cards[1].innerHTML === '' && !cards[1].card.classList.on, 'an asset not in the file keeps its last close');
  ok(cards[2].innerHTML === '' && !cards[2].card.classList.on, "an asset with yesterday's price only keeps its last close");
  ok(panels[0].innerHTML.includes('To the close') && banners[0].innerHTML.includes('Live') && !banners[0].hidden, 'the panel and the banner');
});
at(DOWN, () => { V.paint(root); ok(cards[0].innerHTML === '' && banners[0].innerHTML.includes('stopped') && !banners[0].hidden, 'down: the cards back to the last close, the banner says so'); });
at(NEXT, () => { V.paint(root); ok(cards[0].innerHTML === '' && panels[0].innerHTML === '' && banners[0].hidden, 'a day old: nothing shown as live'); });
V.set(closedDoc);
at(AFTER, () => {
  V.paint(root);
  ok(cards[0].innerHTML.includes('at the close'), "after the close: today's close until tonight's update");
  cards[0].dataset.asof = '2026-11-05'; panels[0].dataset.asof = '2026-11-05'; banners[0].dataset.asof = '2026-11-05';
  V.paint(root);
  ok(cards[0].innerHTML === '' && !cards[0].card.classList.on && panels[0].innerHTML === '' && banners[0].hidden, "tonight's update is in: the page's own numbers");
});
ok(V.SRC.includes('intraday-live/live.json'), 'read from the branch intraday-live');
console.log(`intraday view: ${n} checks passed`);
