// opportunity-scan.js: the hub's Opportunity → Scan — packed rows unpacked, the filters, the four-part read, the post
// drafts (X's weighted count, English and Chinese, short and long), the table cells and the scoreboard (no DOM, no network).
const assert = require('node:assert/strict');
const S = require('../docs/opportunity-scan.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const eq = (a, b, m) => { assert.deepEqual(a, b, m); n++; };

const cols = {
  opp: ['up1m', 'up3m', 'buy3m', 'r10', 'r90', 'side', 'bh', 'oscore'],
  odds: ['dn10_4', 'up10_4', 'dn20_13', 'up20_13', 'beat13', 'sp500_12m', 'divcut_12m'],
  ma: ['close', 'd200', 'x50_200', 'up50_200', 'gap_hybrid', 'hd_pct', 'pct_hybrid', 'seas13', 'guid', 'guid_last'],
  rrg: ['rel', 'p', 'lo', 'hi', 'quad'],
  move: ['d', 'last', 'move', 'pct', 'every', 'sim21', 'all21', 'd0'],
  hi: ['ath', 'highs63', 'dd', 'pull10_63', 'fwd63', 'fwd63_up', 'n'],
  lo: ['reg', 'fwd63', 'fwd63_up', 'next_low63', 'n', 'dd'],
  rg: ['reg', 'break21', 'up_first', 'fwd63_up', 'n', 'width'],
  parts: ['opp', 'ma', 'rrg'],
};
const doc = {
  asof: '2026-10-30', sources: { moves: '2026-11-04' }, counts: { rows: 4, scored: 2166, sp500: 2 }, rules: { recent_cross_days: 10, big_move_pct: 95, guidance_days: 120 },
  market: { recession_12m: 0.1234, spy: { close: 755.7, gap40: 0.039 } },
  history: { ma_bands: { 13: { back: [0.163, 0.27, 0.33, 0.37, 0.39, 0.37, 0.33, 0.28, 0.22, 0.134], ret: [-0.0029, 0, 0, 0, 0, 0, 0, 0, 0, 0.0018], ret_t: [-0.52, 0, 0, 0, 0, 0, 0, 0, 0, 0.32] } } },
  scoreboard: [
    { key: 'opp:3m', group: 'Opportunity', model: 'Higher in 3 months', kind: 'probability', skill: 0.0203, auc: 0.571, verdict: 'useful' },
    { key: 'odds:up20_13', group: 'Odds', model: 'Touches +20% within 13 weeks', kind: 'probability', skill: 0.104, auc: 0.718, base: 0.221, verdict: 'useful' },
    { key: 'odds:beat13', group: 'Odds', model: 'Beats SPY over 13 weeks', kind: 'probability', skill: -0.001, verdict: 'none' },
    { key: 'combined:score_all', group: 'Combined', model: 'Combined score', kind: 'ranking', ic: 0.0767, ic_t: 2.7, net: 0.0032, net_t: 0.1, top: -0.0088, top_t: -1.7,
      top_all: -0.0018, bottom_all: -0.0227, verdict: 'ranks' },
    { key: 'combined:p', group: 'Combined', model: 'Its probability', kind: 'probability', skill: 0.0006, base: 0.449, verdict: 'none' },
    { key: 'hist:moves', group: 'Move odds', model: 'what followed', kind: 'history', verdict: 'history' },
  ],
  composite: { test_from: 2016, cal_years: 5, components: [{ key: 'opp', name: 'Opportunity, 3 months' }, { key: 'ma', name: 'Moving averages, 13 weeks' }, { key: 'rrg', name: 'Hybrid RRG, 13 weeks' }],
    weights_now: { opp: 0.07, ma: 0.016, rrg: 0.063 },
    tests: { score_all: { '2016–2026': { ic: { mean: 0.0767, t: 2.67 }, net: { mean: 0.0032, t: 0.15 }, top_spy: { mean: -0.0088, t: -1.67 }, top_all: { mean: -0.0018, t: -0.2 }, bottom_all: { mean: -0.0227, t: -1.27 } } } },
    calibration: { skill: 0.0006, base_rate: 0.449, table: [{ tenth: 1, said: 0.409, happened: 0.381, n: 1000 }, { tenth: 10, said: 0.485, happened: 0.461, n: 1000 }] } },
  ledger: { resolved_weeks: 0, pending_weeks: 1 },
  cols,
  rows: [
    { t: 'NVDA', n: 'NVIDIA Corp', s: 'technology', ix: ['sp500', 'ndx', 'r1000'], f: ['buy', 'above200', 'far_below'], score: 98.4, tenth: 10, p_beat: 0.45, parts: [1, 0.71, 0.86],
      opp: [0.607, 0.647, 0.639, -0.163, 0.303, 'buy', '1m', 87.4], odds: [0.187, 0.216, 0.176, 0.232, 0.483, null, 0.04],
      ma: [204.64, 0.0103, ['2025-06-27', 1, 340], 1, -0.3845, 0.042, 0.585, 0.0015, null, ['2025-08-27', 'reaffirmed']],
      rrg: [-0.025, 0.479, -0.2, 0.21, 'lagging'], move: ['2026-11-04', 200.13, -0.0318, 12.4, 8.04, [347, 0.0168, 0.5706], [0.0297, 0.5937], '1999-01-22'] },
    { t: 'AAPL', n: 'Apple Inc. <script>', s: 'technology', ix: ['sp500', 'dji'], f: ['buy', 'above200', 'ath', 'bigup', 'raised'], score: 100, opp: [0.59, 0.642, 0.63, -0.12, 0.2, 'buy', '3m', 84.8],
      odds: [0.109, 0.128, 0.096, 0.132, 0.491, null, 0.03], ma: [344.6, 0.11, ['2025-09-15', 1, 286], 1, 0.187, 0.81, 0.6, 0.0066, 1, ['2026-10-30', 'raised']],
      move: ['2026-11-04', 349.51, 0.0531, 96.96, 32.86, [578, 0.0181, 0.5433], [0.0218, 0.5792], '1980-12-12'], hi: [true, 8, 0, 0.496, 0.0285, 0.577, 250] },
    { t: 'SMID', n: 'Small Mid Co with a long name that keeps going on and on', s: 'energy', ix: ['r2000'], f: ['atl', 'below200', 'sp500_cand', 'divcut'],
      opp: [0.4, 0.39, 0.37, -0.68, 1.24, 'none', null, null], odds: [0.3, 0.2, 0.35, 0.15, 0.45, 0.31, 0.25], ma: [0.23, -0.6],
      move: ['2026-11-04', 0.233, -0.049, 3, 6.2, [62, -0.132, 0.34], [0.01, 0.33], '2021-08-30'], lo: ['atl', 0.178, 0.661, 0.734, 250, -0.9989] },
    { t: 'CBZ', n: 'CBIZ', s: 'industrials', ix: ['sp400'], f: ['narrow'], opp: [0.55, 0.56, 0.55, -0.1, 0.12, 'none', null, null], rg: ['narrow', 0.94, 0.6, 0.59, 250, 0.0123] },
  ],
};

// ---- unpack and select
S.unpack(doc);
eq(doc._by.NVDA.opp.up3m, 0.647, 'a packed section is an object again');
ok(doc._by.NVDA.odds.sp500_12m === undefined, 'nulls are left out');
eq(doc._by.CBZ.ma, undefined, 'a section the row lacks stays missing');
eq(S.unpack(doc), doc, 'unpacking twice changes nothing');
eq(S.select(doc, {}).map((r) => r.t), ['AAPL', 'NVDA', 'SMID', 'CBZ'], 'by the combined score, names without one last');
eq(S.select(doc, { ix: 'sp500' }).map((r) => r.t), ['AAPL', 'NVDA'], 'only S&P 500 members');
eq(S.select(doc, { chips: ['buy', 'ath'] }).map((r) => r.t), ['AAPL'], 'every signal picked must hold');
eq(S.select(doc, { prob: 'up3m', min: '0.6', sort: 'prob' }).map((r) => r.t), ['NVDA', 'AAPL'], 'a minimum probability, sorted by it');
eq(S.select(doc, { prob: 'sp500_12m', min: '0.1' }).map((r) => r.t), ['SMID'], 'any of the probabilities');
eq(S.select(doc, { search: 'apple' }).map((r) => r.t), ['AAPL'], 'search by name');
eq(S.select(doc, { sort: 'move_low' })[0].t, 'SMID', 'the biggest fall first');
eq(S.select(doc, { sort: 'name' }).map((r) => r.t), ['AAPL', 'CBZ', 'NVDA', 'SMID']);
eq(S.sectors(doc), ['energy', 'industrials', 'technology']);
const noScore = S.unpack({ cols, rows: doc.rows.map((r) => ({ ...r, score: undefined })) });
eq(S.select(noScore, {}).map((r) => r.t), ['NVDA', 'AAPL', 'CBZ', 'SMID'], 'no combined score yet: by the probability');

// ---- X's weighted count
eq(S.xlen('abc'), 3);
eq(S.xlen('测试'), 4, 'CJK counts two');
eq(S.xlen('—'), 1, 'the em dash counts one');
eq(S.xlen('😀'), 2, 'an emoji counts two');
ok(S.intentUrl('$NVDA 50% & more').startsWith('https://x.com/intent/post?text=%24NVDA%2050%25%20%26%20more'), 'the intent URL is encoded');

// ---- the drafts
for (const r of S.select(doc, {})) {
  for (const lang of ['en', 'zh']) {
    const t = S.draft(r, doc, { lang, len: 'short' });
    ok(S.xlen(t) <= S.LIMIT, `${r.t} ${lang}: fits X's 280 (${S.xlen(t)})`);
    ok(t.startsWith('$' + r.t + ' '), `${r.t} ${lang}: opens with the cashtag`);
    ok(!/https?:\/\//.test(t), 'no link');
    ok(!/buy flag|买入信号|Opportunity flag/i.test(t), 'no flag (advice) in a post');
    ok(/1\) .+ 2\) .+ 3\) /.test(t), 'a question with numbered options');
    ok(t.endsWith(lang === 'zh' ? '#美股' : '#stocks'), 'the hashtag last');
    ok(!/undefined|NaN|null|\[object/.test(t), `${r.t} ${lang}: no empty values`);
    const L = S.draft(r, doc, { lang, len: 'long' });
    ok(!/undefined|NaN|null|\[object/.test(L), `${r.t} ${lang} long: no empty values`);
    ok(lang === 'zh' ? /目前如何/.test(L) && /网站推测/.test(L) && /你会买/.test(L) && /不构成投资建议/.test(L)
      : /Where it stands now/.test(L) && /What the site's models say/.test(L) && /Would you buy \$/.test(L) && /not advice/.test(L), `${r.t} ${lang}: the four parts`);
  }
}
const en = S.draft(doc._by.NVDA, doc, { lang: 'en', len: 'short' });
ok(/-3\.2% on Nov 4 at \$200\.13/.test(en), 'the move, the date and the price (ASCII minus, searchable)');
ok(/about every 8 trading days/.test(en), 'how rare the move is');
ok(/65% odds it's higher in 3 months/.test(en), "Opportunity's probability");
const zh = S.draft(doc._by.NVDA, doc, { lang: 'zh', len: 'short' });
ok(/11月4日跌3\.2%，收200\.13美元/.test(zh) && /3个月后更高的概率65%/.test(zh), 'the Chinese draft');
ok(!/#美股/.test(S.draft(doc._by.NVDA, doc, { lang: 'zh', tag: false })), 'no hashtag when turned off');
const ap = S.draft(doc._by.AAPL, doc, { lang: 'en' });
ok(/all-time high/.test(ap) && /After similar highs/.test(ap), 'a record high leads, with what followed similar highs');
const sm = S.draft(doc._by.SMID, doc, { lang: 'en', len: 'long' });
ok(/\$0\.233/.test(sm) && /99\.9% under its all-time high/.test(sm), 'a sub-dollar price and a near-total fall, not rounded to 100%');
ok(/31% odds of joining the S&P 500/.test(sm) && /25% odds of a dividend cut/.test(sm), 'a candidate and a dividend-cut risk are said');
const nl = S.draft(doc._by.NVDA, doc, { lang: 'en', len: 'long' });
ok(/32% below its hybrid line/.test(nl) && /96% of its own past weeks/.test(nl), 'far from its own line, against its own history');
ok(/back on its other side within 13 weeks 16% of the time/.test(nl) && /no reliable pull back/.test(nl), 'what followed that distance');
ok(/Combined rank this week: 98\/100 among 2,166/.test(nl), 'the combined score is a rank (floored)');
ok(!/45%/.test(nl), 'its probability of beating SPY (no skill) is not quoted');

// ---- a post of the filtered list
const q1 = { ix: 'sp500', chips: ['buy', 'above200'], prob: 'up3m', sort: 'prob' };
const L1 = S.listDraft(doc, q1, { lang: 'en' });
ok(L1.startsWith("2 S&P 500 stocks above their 200-day average. The site's odds of a higher price in 3 months:"), 'the filters open the post (no buy flag in it)');
ok(/\n\$NVDA 65%\n\$AAPL 64%\n/.test(L1) && /Which one would you buy\? 1\) NVDA 2\) AAPL/.test(L1) && L1.endsWith('#stocks'), 'the names in the order of the list, then the question');
ok(S.xlen(L1) <= S.LIMIT);
const q2 = { chips: ['buy'], prob: 'up3m', min: '0.5', sort: 'prob' };
eq(S.listRows(doc, q2).map((r) => r.t), ['NVDA', 'AAPL', 'CBZ'], 'a flag the post cannot say is not a filter of its list');
ok(S.listDraft(doc, q2, {}).startsWith("3 US stocks have 50%+ odds of a higher price in 3 months (the site's models):"), 'the count is of the list the post describes');
const L2 = S.listDraft(doc, q1, { lang: 'zh', len: 'long' });
ok(/^标普500成分股中有2只站上200日线。网站给出的3个月后上涨的概率：/.test(L2) && /\$NVDA 65%（11月4日跌3\.2%，高于200日线1\.0%）/.test(L2) && /不构成投资建议/.test(L2), 'the Chinese long list');
const big = { ...doc, _rows: Array.from({ length: 40 }, (_, i) => ({ ...doc._by.NVDA, t: 'TICKER' + i, f: ['far_below', 'bigdown', 'golden', 'raised'] })) };
ok(S.xlen(S.listDraft(big, { prob: 'up3m', chips: ['far_below', 'bigdown', 'golden', 'raised'] }, { lang: 'zh' })) <= S.LIMIT, 'a long list still fits');
const LH = S.listHtml(doc, { ...q1, prob: 'beat13' }, {});
ok(/A post of this list/.test(LH) && /has no out-of-sample skill/.test(LH) && /id="opd-text"/.test(LH) && /Buy flag: left out of the post/.test(LH), 'the list composer: a probability without skill, a flag left out');

// ---- the read, the cells, the pieces of the page
const F = S.facts(doc._by.NVDA, doc, 'en', '−');
eq(F.now.map((x) => x.key), ['move', 'ma200', 'line']);
eq(F.extra.map((x) => x.key), ['quad', 'flag', 'rrg', 'marank', 'up1m'], 'flags and ranks stay on the page');
const c = S.cells(doc._by.AAPL, doc, { prob: 'up3m' });
eq(c.length, S.HEADERS.length);
ok(c[0].includes('Apple Inc. &lt;script&gt;') && !c[0].includes('<script>'), 'names are escaped');
ok(c[0].includes('data-opd="AAPL"'), 'the ticker opens the draft');
ok(/>100</.test(c[1]) && /64%/.test(c[2]), 'the score and the probability');
ok(/All-time high/.test(c[5]) && /up 58%/.test(c[5]), 'the regime and what followed');
ok(/97th pct · Nov 4/.test(c[6]), "the latest day's percentile and date");
ok(/Guidance raised/.test(c[7]) && !/Above 200-day/.test(c[7]), 'signals not shown elsewhere');
ok(/>98</.test(S.cells(doc._by.NVDA, doc, {})[1]), 'scores are floored: only the top name shows 100');
const x = S.exportRow(doc._by.NVDA);
ok(x.ticker === 'NVDA' && x.p_higher_3m === 0.647 && Math.abs(x.vs_200day - Math.expm1(0.0103)) < 1e-12 && x.signals === 'buy above200 far_below', 'the CSV row');
const K = S.kpis(doc);
eq(K.length, 4);
ok(K[1][1] === '100%' && /of 2 members/.test(K[1][2]), 'S&P 500 members above their 200-day');
ok(/recession odds, 12 months: 12%/.test(K[3][2]));
ok(/data-opchip="sp500_cand"/.test(S.chipsHtml([])) && /class="pill on" data-opchip="buy"/.test(S.chipsHtml(['buy'])) && /opch-clear/.test(S.chipsHtml(['buy'])), 'the signal chips');
const D = S.detailHtml(doc._by.NVDA, doc, { lang: 'zh', len: 'short' });
ok(/id="opd-text"/.test(D) && /id="opd-count"/.test(D) && /href="https:\/\/x\.com\/intent\/post\?text=/.test(D) && /id="opd-copy"/.test(D), 'the composer');
ok(/1 · 目前如何/.test(D) && /2 · 从历史上来讲/.test(D) && /3 · 网站推测/.test(D) && /4 · 你会买吗？/.test(D), 'the four parts, in Chinese');
ok(/<option value="zh" selected>/.test(D) && /no skill, so it is not quoted/.test(D), 'the language kept, and the honest note');
const Dt = S.detailHtml(doc._by.NVDA, doc, { lang: 'en', text: 'my own words' });
ok(/>my own words<\/textarea>/.test(Dt) && /12 \/ 280/.test(Dt), 'an edited draft is kept, and counted');
const B = S.scoreboardHtml(doc);
ok(/Useful skill/.test(B) && /No skill/.test(B) && /History, not a forecast/.test(B), 'verdicts');
ok(/top tenth vs SPY after costs/.test(B), "the combined score's buyer's measure");
const P = S.compositeHtml(doc);
ok(/Opportunity, 3 months 47%/.test(P), "the weights as shares");
ok(/Top tenth vs SPY, after costs/.test(P) && /none, so the page does not quote it/.test(P), 'the tests and the calibration verdict');
ok(/appears once every model/.test(S.compositeHtml({})), 'no combined score yet');
const T = S.summaryText(doc);
ok(/Brier skill 2\.0%/.test(T) && /10\.4%/.test(T) && /Use it to sort, not to pick/.test(T) && /No model here forecasts beating SPY/.test(T), 'the honest summary');
ok(/Click a ticker/.test(S.columnsText(doc)));
console.log(`opportunity-scan view: ${n} checks passed`);
