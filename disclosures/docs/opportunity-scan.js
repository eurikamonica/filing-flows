/* Opportunity → Scan (the hub's default Opportunity view): every stock's read from every model on the site in one row —
   Opportunity's odds of a higher price, the ±10% / ±20% touch odds, Moving averages+ (the 200-day average, the 50/200
   cross, the hybrid line and where the distance to it stands in the company's own history), the hybrid RRG, the latest
   day's move odds, at the highs / at the lows / in a range — filtered by index (S&P 500, Nasdaq-100, Dow …), sector,
   signals and a minimum probability; a combined score tested before it is shown; every model's out-of-sample
   scoreboard; and a post draft in four parts (where it stands now · historically · what the site's models say · would
   you buy?) in English or Chinese, short (X's 280) or long, to copy or open in X (no link added).
   Data: data/market/history/opportunity-scan.json (app/opportunity_scan.py, branch rotation-history).
   No DOM and no network here: opportunity.js draws the hub's view with these functions (tests/test_opportunity_scan_view.cjs).
   window.OpportunityScan = {unpack, select, cells, kpis, detailHtml, draft, facts, xlen, intentUrl, scoreboardHtml,
   compositeHtml, chipsHtml, …}. */
(function () {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => {                                                   // 1,234.5 (toLocaleString is slow for 3,000 rows a render)
    if (!fin(v)) return '—';
    const s = Math.abs(+v).toFixed(d), i = s.indexOf('.'), w = i < 0 ? s : s.slice(0, i);
    return (+v < 0 && +s !== 0 ? '-' : '') + w.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (i < 0 ? '' : s.slice(i));
  };
  const ex = (lg) => (fin(lg) ? Math.expm1(+lg) : null);                       // a log distance as a simple one
  const yearOf = (s) => (/^\d{4}/.test(String(s || '')) ? +String(s).slice(0, 4) : null);
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const ord = (n) => { n = Math.round(n); const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };

  const INDEXES = [['sp500', 'S&P 500', '标普500'], ['ndx', 'Nasdaq-100', '纳斯达克100'], ['dji', 'Dow 30', '道琼斯30'], ['sp400', 'S&P 400', '标普400'],
    ['sp600', 'S&P 600', '标普600'], ['r1000', 'Russell 1000', '罗素1000'], ['r2000', 'Russell 2000', '罗素2000'], ['r3000', 'Russell 3000', '罗素3000']];
  const IX = Object.fromEntries(INDEXES.map((x) => [x[0], x]));
  const FLAGS = [
    ['buy', 'Buy flag', '买入信号'], ['short', 'Short flag', '做空信号'],
    ['above200', 'Above 200-day', '高于200日线'], ['below200', 'Below 200-day', '低于200日线'],
    ['golden', 'Golden cross', '近期金叉'], ['death', 'Death cross', '近期死叉'],
    ['ath', 'All-time high', '历史新高'], ['high', 'At its highs', '处于高位'],
    ['atl', 'All-time low', '历史低位'], ['low52', '52-week low', '52周低点'], ['low3m', '3-month low', '3个月低点'],
    ['narrow', 'Narrow range', '窄幅横盘'], ['wide', 'Wide range', '宽幅震荡'],
    ['bigup', 'Big up day', '大涨日'], ['bigdown', 'Big down day', '大跌日'],
    ['raised', 'Guidance raised', '上调指引'], ['lowered', 'Guidance lowered', '下调指引'], ['guided', 'Guidance kept / updated', '维持或更新指引'],
    ['far_above', 'Far above its line', '远高于混合均线'], ['far_below', 'Far below its line', '远低于混合均线'],
    ['sp500_cand', 'S&P 500 candidate', '标普500候选'], ['divcut', 'Dividend-cut risk', '削减股息风险'],
  ];
  const FL = Object.fromEntries(FLAGS.map((x) => [x[0], x]));
  // the probability a row is filtered and coloured by; key: its scoreboard entry (the record shown beside it)
  const PROBS = [
    ['up3m', 'Higher in 3 months', 'opp:3m', (r) => r.opp && r.opp.up3m],
    ['up1m', 'Higher in 1 month', 'opp:1m', (r) => r.opp && r.opp.up1m],
    ['buy3m', 'A buy pays, 3 months', 'opp:3m', (r) => r.opp && r.opp.buy3m],
    ['up20_13', '+20% within 13 weeks', 'odds:up20_13', (r) => r.odds && r.odds.up20_13],
    ['dn20_13', '−20% within 13 weeks', 'odds:dn20_13', (r) => r.odds && r.odds.dn20_13],
    ['up10_4', '+10% within 4 weeks', 'odds:up10_4', (r) => r.odds && r.odds.up10_4],
    ['dn10_4', '−10% within 4 weeks', 'odds:dn10_4', (r) => r.odds && r.odds.dn10_4],
    ['beat13', 'Beats SPY, 13 weeks (Odds)', 'odds:beat13', (r) => r.odds && r.odds.beat13],
    ['rrg', 'Beats SPY, 13 weeks (RRG)', 'rrg:beat13', (r) => r.rrg && r.rrg.p],
    ['p_beat', 'Beats SPY, 13 weeks (combined)', 'combined:p', (r) => r.p_beat],
    ['sp500_12m', 'Joins the S&P 500, 12 months', 'odds:sp500_12m', (r) => r.odds && r.odds.sp500_12m],
    ['divcut_12m', 'Dividend cut, 12 months', 'odds:divcut_12m', (r) => r.odds && r.odds.divcut_12m],
  ];
  const PB = Object.fromEntries(PROBS.map((x) => [x[0], x]));
  const MINS = [['', 'Any'], ['0.1', '10%+'], ['0.2', '20%+'], ['0.3', '30%+'], ['0.4', '40%+'], ['0.5', '50%+'], ['0.55', '55%+'], ['0.6', '60%+'], ['0.65', '65%+'], ['0.7', '70%+']];
  const SORTS = [['score', 'Combined score'], ['prob', 'The probability, highest'], ['prob_low', 'The probability, lowest'], ['oscore', 'Opportunity score'],
    ['move', 'Latest day: biggest rise'], ['move_low', 'Latest day: biggest fall'], ['d200', 'Furthest above the 200-day'], ['d200_low', 'Furthest below the 200-day'],
    ['hd', 'Furthest above its line (own history)'], ['hd_low', 'Furthest below its line (own history)'], ['name', 'Ticker A–Z']];

  // ------------------------------------------------------------------ data
  function unpack(doc) {
    if (!doc || doc._rows) return doc;
    const C = doc.cols || {};
    doc._rows = (doc.rows || []).map((p) => {
      const r = Object.assign({}, p);
      for (const sec of Object.keys(C)) {
        if (!Array.isArray(p[sec])) continue;
        const o = {};
        C[sec].forEach((k, i) => { if (p[sec][i] != null) o[k] = p[sec][i]; });
        r[sec] = o;
      }
      r.ix = r.ix || [];
      r.f = r.f || [];
      return r;
    });
    doc._by = Object.fromEntries(doc._rows.map((r) => [r.t, r]));
    doc._board = Object.fromEntries((doc.scoreboard || []).filter((s) => s.key).map((s) => [s.key, s]));
    return doc;
  }
  const prob = (r, key) => { const p = (PB[key] || PB.up3m)[3](r); return fin(p) ? +p : null; };
  const d200 = (r) => (r.ma && fin(r.ma.d200) ? ex(r.ma.d200) : null);
  function sortVal(r, key, pk) {
    switch (key) {
      case 'prob': return prob(r, pk);
      case 'prob_low': { const p = prob(r, pk); return p == null ? null : -p; }
      case 'oscore': return r.opp && fin(r.opp.oscore) ? r.opp.oscore : null;
      case 'move': return r.move && fin(r.move.move) ? r.move.move : null;
      case 'move_low': return r.move && fin(r.move.move) ? -r.move.move : null;
      case 'd200': return d200(r);
      case 'd200_low': { const v = d200(r); return v == null ? null : -v; }
      case 'hd': return r.ma && fin(r.ma.hd_pct) ? r.ma.hd_pct : null;
      case 'hd_low': return r.ma && fin(r.ma.hd_pct) ? -r.ma.hd_pct : null;
      default: return fin(r.score) ? r.score : null;
    }
  }
  /* q: {ix, sec, chips: [codes, all must hold], prob, min, search, sort} → the matching rows, sorted (no value last) */
  function select(doc, q) {
    unpack(doc);
    q = q || {};
    const pk = PB[q.prob] ? q.prob : 'up3m', min = fin(q.min) && +q.min > 0 ? +q.min : null;
    const s = String(q.search || '').trim().toLowerCase(), chips = (q.chips || []).filter((c) => FL[c]);
    const R = doc._rows.filter((r) => (!q.ix || r.ix.includes(q.ix)) && (!q.sec || r.s === q.sec) && chips.every((c) => r.f.includes(c))
      && (min == null || (prob(r, pk) != null && prob(r, pk) >= min))
      && (!s || r.t.toLowerCase().includes(s) || String(r.n || '').toLowerCase().includes(s)));
    if (q.sort === 'name') return R.slice().sort((a, b) => a.t.localeCompare(b.t));
    let key = q.sort || 'score';
    if (key === 'score' && !doc._rows.some((r) => fin(r.score))) key = 'prob';      // no combined score yet: by the probability
    return R.map((r) => [sortVal(r, key, pk), r]).sort((a, b) => (a[0] == null ? (b[0] == null ? 0 : 1) : b[0] == null ? -1 : b[0] - a[0])).map((x) => x[1]);
  }
  function sectors(doc) { unpack(doc); return [...new Set(doc._rows.map((r) => r.s).filter(Boolean))].sort(); }

  // ------------------------------------------------------------------ words: one set per language
  function words(lang, minus, ref) {
    const zh = lang === 'zh', m = minus || '-';
    const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '');
    const sp = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? m : '') + num(Math.abs(100 * v), d) + '%' : '');
    const ab = (v, d) => (fin(v) ? num(Math.abs(100 * v), d == null ? (Math.abs(v) < 0.1 || Math.abs(v) > 0.99 ? 1 : 0) : d) + '%' : '');
    const usd = (v) => { if (!fin(v)) return ''; const t = num(v, v >= 1000 ? 0 : v >= 1 ? 2 : 3); return zh ? t + '美元' : '$' + t; };
    const day = (s) => {
      const x = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ''));
      if (!x) return '';
      const y = +x[1], mo = +x[2], d = +x[3];
      return zh ? (y !== ref ? y + '年' : '') + mo + '月' + d + '日' : MON[mo - 1] + ' ' + d + (y !== ref ? ', ' + y : '');
    };
    return { zh, pct, sp, ab, usd, day, n: (v) => num(v, 0) };
  }
  const QUAD = { leading: ['leading', '领先'], weakening: ['weakening', '转弱'], lagging: ['lagging', '落后'], improving: ['improving', '改善'] };
  const GUIDE = { raised: ['raised', '上调'], lowered: ['lowered', '下调'], reaffirmed: ['reaffirmed', '重申'], withdrawn: ['withdrawn', '撤回'],
    initiated: ['initiated', '首次给出'], updated: ['updated', '更新'], mixed: ['mixed', '有升有降'], narrowed: ['narrowed', '收窄'], widened: ['widened', '放宽'] };
  const HZ = { '1w': ['1 week', '1周'], '1m': ['1 month', '1个月'], '3m': ['3 months', '3个月'] };

  /* The four parts, each a list of {full, short?, terse?, key}: full for the panel and the long post, short / terse for
     a post that has to fit X's 280. `extra` (panel only) holds what a post should not carry: flags, model ranks. */
  function facts(r, doc, lang, minus) {
    unpack(doc);
    const mv = r.move || {}, a = r.ma || {}, o = r.opp || {}, od = r.odds || {}, hi = r.hi, lo = r.lo, rg = r.rg, rr = r.rrg || {};
    const ref = yearOf(mv.d || doc.asof), W = words(lang, minus, ref), zh = W.zh;
    const now = [], hist = [], model = [], extra = [];
    // ---- where it stands now
    if (fin(mv.move) && mv.d) {
      const up = mv.move > 0, small = Math.abs(mv.move) < 0.005, when = W.day(mv.d), px = W.usd(mv.last);
      const rare = fin(mv.every) && mv.every >= 5 && !small, ev = W.n(mv.every);
      if (zh) {
        now.push({ key: 'move', full: small ? `${when}基本持平（${W.sp(mv.move)}），收于${px}` : `${when}${up ? '上涨' : '下跌'}${W.ab(mv.move, 1)}，收于${px}` + (rare ? `，这种幅度的${up ? '上涨' : '下跌'}平均约每${ev}个交易日出现一次` : ''),
          short: small ? `${when}基本持平，收${px}` : `${when}${up ? '涨' : '跌'}${W.ab(mv.move, 1)}，收${px}` + (rare ? `（这种${up ? '涨幅' : '跌幅'}约每${ev}个交易日一次）` : ''),
          terse: `${when}${small ? '持平' : (up ? '涨' : '跌') + W.ab(mv.move, 1)}，收${px}` });
      } else {
        now.push({ key: 'move', full: small ? `Little changed on ${when} (${W.sp(mv.move)}) at ${px}` : `${up ? 'Rose' : 'Fell'} ${W.ab(mv.move, 1)} on ${when} to ${px}` + (rare ? `: a ${up ? 'rise' : 'fall'} that size comes about once every ${ev} trading days` : ''),
          short: small ? `flat on ${when} at ${px}` : `${W.sp(mv.move)} on ${when} at ${px}` + (rare ? ` (a ${up ? 'rise' : 'fall'} that size: about every ${ev} trading days)` : ''),
          terse: `${small ? 'flat' : W.sp(mv.move)} on ${when} at ${px}` });
      }
    } else if (fin(a.d_close) && a.d_asof) {
      now.push({ key: 'move', full: zh ? `${W.day(a.d_asof)}收于${W.usd(a.d_close)}` : `Closed at ${W.usd(a.d_close)} on ${W.day(a.d_asof)}`,
        short: zh ? `${W.day(a.d_asof)}收${W.usd(a.d_close)}` : `at ${W.usd(a.d_close)} on ${W.day(a.d_asof)}` });
    }
    if (hi) {
      const h63 = fin(hi.highs63) ? W.n(hi.highs63) : null;
      now.push({ key: 'regime', strong: !!hi.ath, full: hi.ath ? (zh ? `创历史新高` + (h63 ? `（近3个月第${h63}次）` : '') : `At an all-time high` + (h63 ? ` (${h63} new highs in the last 3 months)` : ''))
        : (zh ? `接近历史高点（低于高点${W.ab(-hi.dd)}，近一个月内创过新高）` : `Near its all-time high (${W.ab(-hi.dd)} below it, with a new high in the last month)`),
        short: hi.ath ? (zh ? '创历史新高' : 'at an all-time high') : (zh ? `距历史高点${W.ab(-hi.dd)}` : `${W.ab(-hi.dd)} under its all-time high`) });
    } else if (lo) {
      const L = { atl: ['At an all-time low', '处于历史低位', 'at an all-time low', '处于历史低位'], '52w': ['Near a 52-week low', '接近52周低点', 'near a 52-week low', '接近52周低点'],
        '3m': ['Near a 3-month low', '接近3个月低点', 'near a 3-month low', '接近3个月低点'] }[lo.reg] || ['', '', '', ''];
      now.push({ key: 'regime', strong: lo.reg !== '3m', full: (zh ? L[1] : L[0]) + (fin(lo.dd) ? (zh ? `（较历史高点低${W.ab(-lo.dd)}）` : ` (${W.ab(-lo.dd)} under its all-time high)`) : ''), short: zh ? L[3] : L[2] });
    } else if (rg) {
      const wd = W.ab(rg.width, 1);
      now.push({ key: 'regime', full: rg.reg === 'narrow' ? (zh ? `近3个月窄幅横盘（区间宽度${wd}）` : `In a tight sideways range: ${wd} wide over 3 months`)
        : (zh ? `近3个月宽幅震荡但没有方向（区间宽度${wd}）` : `In a wide sideways range: ${wd} wide over 3 months, going nowhere`),
        short: rg.reg === 'narrow' ? (zh ? `窄幅横盘（${wd}）` : `in a tight ${wd} range`) : (zh ? `宽幅震荡（${wd}）` : `swinging in a wide ${wd} range`) });
    }
    const v200 = d200(r), x = Array.isArray(a.x50_200) ? a.x50_200 : null;
    if (v200 != null) {
      const above = v200 >= 0;
      let cross = '';
      if (x && fin(x[2]) && x[2] <= 10) cross = zh ? `；${x[2] === 0 ? '今天' : x[2] + '个交易日前'}出现${x[1] > 0 ? '金叉（50日线上穿200日线）' : '死叉（50日线下穿200日线）'}`
        : `; a ${x[1] > 0 ? 'golden' : 'death'} cross (the 50-day ${x[1] > 0 ? 'over' : 'under'} the 200-day) ${x[2] === 0 ? 'today' : x[2] + ' trading days ago'}`;
      else if (x && fin(a.up50_200)) cross = zh ? `；50日线自${W.day(x[0])}起${a.up50_200 > 0 ? '位于200日线上方' : '位于200日线下方'}` : `; the 50-day has been ${a.up50_200 > 0 ? 'above' : 'below'} the 200-day since ${W.day(x[0])}`;
      now.push({ key: 'ma200', full: (zh ? `${above ? '高于' : '低于'}200日均线${W.ab(v200, 1)}` : `${W.ab(v200, 1)} ${above ? 'above' : 'below'} its 200-day average`) + cross,
        short: zh ? `${above ? '高于' : '低于'}200日线${W.ab(v200, 1)}` : `${W.ab(v200, 1)} ${above ? 'above' : 'below'} its 200-day` });
    } else if (fin(a.gap40)) {
      const g = ex(a.gap40);
      now.push({ key: 'ma200', full: zh ? `${g >= 0 ? '高于' : '低于'}40周均线${W.ab(g, 1)}` : `${W.ab(g, 1)} ${g >= 0 ? 'above' : 'below'} its 40-week average`,
        short: zh ? `${g >= 0 ? '高于' : '低于'}40周线${W.ab(g, 1)}` : `${W.ab(g, 1)} ${g >= 0 ? 'above' : 'below'} its 40-week average` });
    }
    const gh = ex(a.gap_hybrid);
    if (gh != null) {
      const far = fin(a.hd_pct) && (a.hd_pct >= 0.9 || a.hd_pct <= 0.1), share = fin(a.hd_pct) ? (gh >= 0 ? a.hd_pct : 1 - a.hd_pct) : null;
      now.push({ key: 'line', far, full: zh ? `${gh >= 0 ? '高于' : '低于'}混合均线${W.ab(gh)}（40周均线结合盈利与业绩指引）` + (far ? `，偏离程度超过自身历史上${W.pct(share)}的时间` : fin(a.hd_pct) ? `，在自身历史中属正常（第${Math.round(100 * a.hd_pct)}百分位）` : '')
        : `${W.ab(gh)} ${gh >= 0 ? 'above' : 'below'} its hybrid line (the 40-week average blended with earnings and guidance)` + (far ? `: ${gh >= 0 ? 'further above' : 'further below'} than in ${W.pct(share)} of its own past weeks` : fin(a.hd_pct) ? `, usual for it (its own ${ord(100 * a.hd_pct)} percentile)` : '') });
    }
    const gl = Array.isArray(a.guid_last) ? a.guid_last : null;
    if (gl && r.f.some((c) => c === 'raised' || c === 'lowered' || c === 'guided')) {
      const k = GUIDE[gl[1]] || [gl[1], gl[1]];
      now.push({ key: 'guidance', full: zh ? `${W.day(gl[0])}${k[1]}业绩指引` : `Guidance ${k[0]} on ${W.day(gl[0])}`, short: zh ? `${W.day(gl[0])}${k[1]}指引` : `guidance ${k[0]} ${W.day(gl[0])}` });
    }
    if (rr.quad && QUAD[rr.quad]) extra.push({ key: 'quad', part: 'now', full: zh ? `相对SPY的RRG：处于${QUAD[rr.quad][1]}象限` : `On the relative-rotation graph against SPY: ${QUAD[rr.quad][0]}` });
    // ---- historically
    if (hi && fin(hi.fwd63_up)) {
      hist.push({ key: 'regime', full: zh ? `其他公司处于类似高位的${W.n(hi.n || 250)}个交易日之后，3个月后股价更高的比例为${W.pct(hi.fwd63_up)}（中位数${W.sp(hi.fwd63)}）` + (fin(hi.pull10_63) ? `；${W.pct(hi.pull10_63)}在3个月内回撤过10%` : '')
        : `After the ${W.n(hi.n || 250)} most similar days of other companies at their highs, the price was higher 3 months later ${W.pct(hi.fwd63_up)} of the time (median ${W.sp(hi.fwd63)})` + (fin(hi.pull10_63) ? `; ${W.pct(hi.pull10_63)} had a 10% pullback within 3 months` : ''),
        short: zh ? `历史上类似高位之后，3个月后上涨的比例为${W.pct(hi.fwd63_up)}` : `After similar highs, stocks were higher 3 months later ${W.pct(hi.fwd63_up)} of the time` });
    } else if (lo && fin(lo.fwd63_up)) {
      hist.push({ key: 'regime', full: zh ? `其他公司类似低位的${W.n(lo.n || 250)}个交易日之后，3个月后股价更高的比例为${W.pct(lo.fwd63_up)}（中位数${W.sp(lo.fwd63)}）` + (fin(lo.next_low63) ? `；${W.pct(lo.next_low63)}在3个月内又创新低` : '')
        : `After the ${W.n(lo.n || 250)} most similar lows of other companies, the price was higher 3 months later ${W.pct(lo.fwd63_up)} of the time (median ${W.sp(lo.fwd63)})` + (fin(lo.next_low63) ? `; a lower low came within 3 months ${W.pct(lo.next_low63)} of the time` : ''),
        short: zh ? `历史上类似低位之后，3个月后上涨的比例为${W.pct(lo.fwd63_up)}` : `After similar lows, stocks were higher 3 months later ${W.pct(lo.fwd63_up)} of the time` });
    } else if (rg && fin(rg.break21)) {
      hist.push({ key: 'regime', full: zh ? `类似的区间在一个月内突破的比例为${W.pct(rg.break21)}` + (fin(rg.up_first) ? `，其中向上突破占${W.pct(rg.up_first)}` : '') + (fin(rg.fwd63_up) ? `；3个月后股价更高的比例为${W.pct(rg.fwd63_up)}` : '')
        : `Ranges like this broke out within a month ${W.pct(rg.break21)} of the time` + (fin(rg.up_first) ? `, upward ${W.pct(rg.up_first)} of the time` : '') + (fin(rg.fwd63_up) ? `; 3 months later the price was higher ${W.pct(rg.fwd63_up)} of the time` : ''),
        short: zh ? `类似区间一个月内突破的比例为${W.pct(rg.break21)}` : `Ranges like this broke out within a month ${W.pct(rg.break21)} of the time` });
    }
    const sim = Array.isArray(mv.sim21) ? mv.sim21 : null;
    if (sim && sim[0] >= 30 && fin(sim[2])) {
      const since = yearOf(mv.d0), all = Array.isArray(mv.all21) ? mv.all21 : null;
      hist.push({ key: 'move', full: zh ? `${since ? '自' + since + '年以来，' : ''}与这天最相似的${W.n(sim[0])}个交易日之后，一个月（21个交易日）后上涨的比例为${W.pct(sim[2])}（中位数${W.sp(sim[1])}）` + (all && fin(all[1]) ? `；全部交易日为${W.pct(all[1])}` : '')
        : `After its ${W.n(sim[0])} most similar days${since ? ' since ' + since : ''}, it was higher a month later (21 trading days) ${W.pct(sim[2])} of the time (median ${W.sp(sim[1])})` + (all && fin(all[1]) ? `, against ${W.pct(all[1])} for all its days` : ''),
        short: zh ? `历史上相似的${W.n(sim[0])}个交易日之后，一个月后上涨的比例为${W.pct(sim[2])}` + (all && fin(all[1]) ? `（全部交易日${W.pct(all[1])}）` : '')
          : `After its ${W.n(sim[0])} most similar days, it was higher a month later ${W.pct(sim[2])} of the time` + (all && fin(all[1]) ? ` (all days: ${W.pct(all[1])})` : ''),
        terse: zh ? `历史上相似的${W.n(sim[0])}个交易日之后，一个月后上涨的比例为${W.pct(sim[2])}` : `After its ${W.n(sim[0])} most similar days, it was higher a month later ${W.pct(sim[2])} of the time` });
    }
    if (fin(a.seas13)) {
      const sv = ex(a.seas13);
      hist.push({ key: 'season', full: zh ? `季节性：过去几年同期的13周里，平均相对SPY ${W.sp(sv)}` : `Its own season: the same 13 weeks of past years averaged ${W.sp(sv)} against SPY` });
    }
    const bands = (((doc.history || {}).ma_bands) || {})['13'];
    if (bands && fin(a.hd_pct) && (a.hd_pct >= 0.9 || a.hd_pct <= 0.1)) {
      const j = Math.min(9, Math.max(0, Math.floor(a.hd_pct * 10))), back = (bands.back || [])[j], ret = (bands.ret || [])[j], t = (bands.ret_t || [])[j];
      if (fin(back)) {
        const pull = fin(t) && Math.abs(t) >= 2;
        hist.push({ key: 'band', full: zh ? `与自身混合均线偏离到同样程度的股票，13周内回到均线另一侧的比例为${W.pct(back)}；之后13周相对平均公司${W.sp(ret)}（t ${num(t, 1)}，${pull ? '有统计意义' : '没有可靠的均值回归'}）`
          : `Stocks this far from their own line were back on its other side within 13 weeks ${W.pct(back)} of the time; their next 13 weeks ran ${W.sp(ret)} against the average company (t ${num(t, 1)}: ${pull ? 'a reliable pull' : 'no reliable pull back'})` });
      }
    }
    // ---- what the site's models say
    const B = doc._board || {};
    if (fin(o.up3m)) {
      const sk = (B['opp:3m'] || {}).skill;
      model.push({ key: 'up3m', full: zh ? `3个月后股价更高的概率为${W.pct(o.up3m)}` + (fin(o.r10) && fin(o.r90) ? `（可能区间${W.sp(o.r10, 0)}至${W.sp(o.r90, 0)}）` : '')
        : `${W.pct(o.up3m)} chance the price is higher in 3 months` + (fin(o.r10) && fin(o.r90) ? ` (likely range ${W.sp(o.r10, 0)} to ${W.sp(o.r90, 0)})` : ''),
        short: zh ? `网站模型：3个月后更高的概率${W.pct(o.up3m)}` : `The site's model: ${W.pct(o.up3m)} odds it's higher in 3 months`, terse: zh ? `模型：3个月上涨概率${W.pct(o.up3m)}` : `Model: ${W.pct(o.up3m)} odds higher in 3 months`,
        skill: sk });
    }
    if (fin(od.up20_13) && fin(od.dn20_13)) {
      model.push({ key: 'touch', full: zh ? `13周内触及+20%的概率${W.pct(od.up20_13)}，触及-20%的概率${W.pct(od.dn20_13)}` : `Odds of touching +20% within 13 weeks: ${W.pct(od.up20_13)}; ${minus || '-'}20%: ${W.pct(od.dn20_13)}`,
        short: zh ? `13周内+20%/-20%的概率：${W.pct(od.up20_13)}/${W.pct(od.dn20_13)}` : `+20% vs -20% odds within 13 weeks: ${W.pct(od.up20_13)} vs ${W.pct(od.dn20_13)}` });
    }
    if (r.f.includes('sp500_cand') && fin(od.sp500_12m)) model.push({ key: 'sp500', strong: true, full: zh ? `12个月内被纳入标普500的概率为${W.pct(od.sp500_12m)}` : `${W.pct(od.sp500_12m)} odds of joining the S&P 500 within 12 months`,
      short: zh ? `纳入标普500概率${W.pct(od.sp500_12m)}` : `${W.pct(od.sp500_12m)} odds of S&P 500 inclusion in 12 months` });
    if (r.f.includes('divcut') && fin(od.divcut_12m)) model.push({ key: 'divcut', strong: true, full: zh ? `12个月内削减股息的概率为${W.pct(od.divcut_12m)}` : `${W.pct(od.divcut_12m)} odds of a dividend cut within 12 months`,
      short: zh ? `削减股息概率${W.pct(od.divcut_12m)}` : `${W.pct(od.divcut_12m)} odds of a dividend cut in 12 months` });
    const scored = (doc.counts || {}).scored;
    if (fin(r.score)) model.push({ key: 'score', full: zh ? `综合评分${Math.floor(r.score)}/100（本周在${W.n(scored)}只美股中的排名，综合三个经过检验的模型）` : `Combined rank this week: ${Math.floor(r.score)}/100 among ${W.n(scored)} US stocks (three tested models)` });
    if (o.side === 'buy' || o.side === 'short') extra.push({ key: 'flag', part: 'model', full: zh ? `Opportunity信号：${o.side === 'buy' ? '买入' : '做空'}（${(HZ[o.bh] || [o.bh, o.bh])[1]}；只在信号样本外赚过钱的周期才会出现）`
      : `Opportunity flag: ${o.side} at ${(HZ[o.bh] || [o.bh])[0]} (shown only at horizons where flags made money out of sample)` });
    if (fin(rr.rel)) extra.push({ key: 'rrg', part: 'model', full: zh ? `混合RRG：预计13周相对SPY ${W.sp(ex(rr.rel))}（80%区间${W.sp(ex(rr.lo), 0)}至${W.sp(ex(rr.hi), 0)}）` : `Hybrid RRG: ${W.sp(ex(rr.rel))} against SPY expected over 13 weeks (80% range ${W.sp(ex(rr.lo), 0)} to ${W.sp(ex(rr.hi), 0)})` });
    if (fin(a.pct_hybrid)) extra.push({ key: 'marank', part: 'model', full: zh ? `Moving averages+模型本周排名：第${Math.round(100 * a.pct_hybrid)}百分位（均线+基本面+指引）` : `Moving averages+ models rank it in the ${ord(100 * a.pct_hybrid)} percentile this week (averages + fundamentals + guidance)` });
    if (fin(o.up1m)) extra.push({ key: 'up1m', part: 'model', full: zh ? `1个月后更高的概率：${W.pct(o.up1m)}` : `Higher in 1 month: ${W.pct(o.up1m)}` });
    // ---- would you buy?
    const ask = zh ? { q: `这个价位你会买 $${r.t} 吗？`, short: '你会在这里买吗？1) 会 2) 再等等 3) 不会', terse: '会买吗？1) 会 2) 等 3) 不会', opts: ['会', '再等等', '不会'] }
      : { q: `Would you buy $${r.t} here?`, short: 'Would you buy here? 1) yes 2) wait 3) no', terse: 'Buy here? 1) yes 2) wait 3) no', opts: ['Yes', 'Wait for a better price', 'No'] };
    return { now, hist, model, extra, ask, words: W };
  }

  // ------------------------------------------------------------------ the post
  /* X's weighted length (twitter-text v3): code points 0–4351 and three punctuation ranges count 1, the rest 2. */
  function xlen(s) {
    let n = 0;
    for (const ch of String(s == null ? '' : s).normalize('NFC')) {
      const c = ch.codePointAt(0);
      n += c <= 4351 || (c >= 8192 && c <= 8205) || (c >= 8208 && c <= 8223) || (c >= 8242 && c <= 8247) ? 1 : 2;
    }
    return n;
  }
  const LIMIT = 280;
  const TAG = { en: '#stocks', zh: '#美股' };
  const pick = (L, k) => L.find((x) => x.key === k);
  /* opts: {lang 'en' | 'zh', len 'short' | 'long', tag true | false} → the post text */
  function draft(r, doc, opts) {
    opts = opts || {};
    const lang = opts.lang === 'zh' ? 'zh' : 'en', zh = lang === 'zh', tag = opts.tag === false ? '' : TAG[lang];
    const F = facts(r, doc, lang, '-');
    if (opts.len === 'long') {
      const dot = (L) => L.map((x) => '• ' + x.full + (zh ? '' : '.')).join('\n');
      const T = zh ? ['目前如何', '从历史上来讲', '网站推测'] : ['Where it stands now', 'Historically', "What the site's models say"];
      const parts = [`$${r.t}${r.n ? (zh ? `（${r.n}）` : ` · ${r.n}`) : ''}`];
      if (F.now.length) parts.push(`${T[0]}\n${dot(F.now)}`);
      if (F.hist.length) parts.push(`${T[1]}\n${dot(F.hist)}`);
      if (F.model.length) parts.push(`${T[2]}\n${dot(F.model)}`);
      parts.push(`${F.ask.q}\n${F.ask.opts.map((x, i) => `${i + 1}) ${x}`).join('\n')}`);
      parts.push((zh ? '历史数据与模型，不构成投资建议。' : 'History and models, not advice.') + (tag ? ' ' + tag : ''));
      return parts.join('\n\n');
    }
    const mv = pick(F.now, 'move'), reg = pick(F.now, 'regime'), m200 = pick(F.now, 'ma200');
    const side = reg && reg.strong ? reg : m200 || reg;                     // a record high or low says more than the 200-day
    const h0 = pick(F.hist, 'regime') || pick(F.hist, 'move'), m0 = pick(F.model, 'up3m'), m1 = pick(F.model, 'sp500') || pick(F.model, 'divcut') || pick(F.model, 'touch');
    const sep = zh ? '，' : '; ';
    const build = (lv) => {
      const first = [lv.move === 'terse' ? (mv && (mv.terse || mv.short)) : mv && mv.short, lv.side && side ? side.short : null].filter(Boolean);
      const lines = [`$${r.t} ` + (first.join(sep) || (zh ? '本周' : 'this week')) + (zh ? '。' : '.')];
      if (lv.hist && h0) lines.push((lv.hist === 'terse' ? h0.terse || h0.short : h0.short) + (zh ? '。' : '.'));
      const mm = [m0 ? (lv.model === 'terse' ? m0.terse : m0.short) : null, lv.m1 && m1 ? m1.short : null].filter(Boolean);
      if (mm.length) lines.push(mm.join(sep) + (zh ? '。' : '.'));
      lines.push(lv.ask === 'terse' ? F.ask.terse : F.ask.short);
      if (lv.tag && tag) lines.push(tag);
      return lines.join('\n');
    };
    const levels = [{ side: 1, hist: 1, m1: 1, tag: 1 }, { side: 1, hist: 'terse', m1: 1, tag: 1 }, { side: 1, hist: 'terse', tag: 1 }, { hist: 'terse', tag: 1 },
      { move: 'terse', hist: 'terse', tag: 1 }, { move: 'terse', hist: 'terse', model: 'terse', tag: 1 }, { move: 'terse', model: 'terse', tag: 1 },
      { move: 'terse', model: 'terse' }, { move: 'terse', model: 'terse', ask: 'terse' }];
    let text = '';
    for (const lv of levels) { text = build(lv); if (xlen(text) <= LIMIT) return text; }
    return text;
  }
  const intentUrl = (text) => 'https://x.com/intent/post?text=' + encodeURIComponent(String(text || ''));

  // a post of the filtered list itself: what the filters say, then the names with the probability picked
  const PHRASE = { ath: ['at an all-time high', '创历史新高'], high: ['running at their highs', '处于高位'], atl: ['at an all-time low', '处于历史低位'],
    low52: ['near a 52-week low', '接近52周低点'], low3m: ['near a 3-month low', '接近3个月低点'], narrow: ['in a tight range', '窄幅横盘'], wide: ['in a wide range', '宽幅震荡'],
    above200: ['above their 200-day average', '站上200日线'], below200: ['below their 200-day average', '跌破200日线'], golden: ['with a fresh golden cross', '刚出现金叉'],
    death: ['with a fresh death cross', '刚出现死叉'], bigup: ['after a big up day', '大涨之后'], bigdown: ['after a big down day', '大跌之后'],
    raised: ['that just raised guidance', '刚上调指引'], lowered: ['that just lowered guidance', '刚下调指引'], guided: ['with new guidance', '刚更新指引'],
    far_above: ['far above their own trend line', '远高于自身趋势线'], far_below: ['far below their own trend line', '远低于自身趋势线'],
    sp500_cand: ['that could join the S&P 500', '有望纳入标普500'], divcut: ['at risk of a dividend cut', '有削减股息风险'] };    // no buy / short flag: a post gives no advice
  const PNOUN = { up3m: ['odds of a higher price in 3 months', '3个月后上涨的概率'], up1m: ['odds of a higher price in 1 month', '1个月后上涨的概率'],
    buy3m: ['odds a buy pays after costs in 3 months', '3个月买入扣除成本后盈利的概率'], up20_13: ['odds of touching +20% within 13 weeks', '13周内触及+20%的概率'],
    dn20_13: ['odds of touching -20% within 13 weeks', '13周内触及-20%的概率'], up10_4: ['odds of touching +10% within 4 weeks', '4周内触及+10%的概率'],
    dn10_4: ['odds of touching -10% within 4 weeks', '4周内触及-10%的概率'], beat13: ['odds of beating SPY over 13 weeks', '13周跑赢SPY的概率'], rrg: ['odds of beating SPY over 13 weeks', '13周跑赢SPY的概率'],
    p_beat: ['odds of beating SPY over 13 weeks', '13周跑赢SPY的概率'], sp500_12m: ['odds of joining the S&P 500 within 12 months', '12个月内纳入标普500的概率'],
    divcut_12m: ['odds of a dividend cut within 12 months', '12个月内削减股息的概率'] };
  /* the list a post may describe: the filters it can say in words (Opportunity's buy / short flags are left out: a post
     gives no advice), in the list's order */
  function listRows(doc, q) { return select(doc, Object.assign({}, q, { chips: (q.chips || []).filter((c) => PHRASE[c]) })); }
  function listDraft(doc, q, opts) {
    q = q || {}; opts = opts || {};
    const lang = opts.lang === 'zh' ? 'zh' : 'en', zh = lang === 'zh', tag = opts.tag === false ? '' : TAG[lang], long = opts.len === 'long';
    const pk = PB[q.prob] ? q.prob : 'up3m', W = words(lang, '-', yearOf(doc.asof)), R = listRows(doc, q);
    const have = R.filter((r) => prob(r, pk) != null);
    const ixn = q.ix && IX[q.ix] ? IX[q.ix][zh ? 2 : 1] : null;
    const ph = (q.chips || []).map((c) => PHRASE[c]).filter(Boolean).map((x) => x[zh ? 1 : 0]);
    const min = fin(q.min) && +q.min > 0 ? +q.min : null, noun = PNOUN[pk][zh ? 1 : 0], site = pk.startsWith('up') || pk === 'buy3m' || pk.startsWith('dn');
    const head = zh ? `${ixn ? ixn + '成分股' : '美股'}中有${W.n(R.length)}只${ph.join('、')}` + (min ? `，网站给出的${noun}不低于${W.pct(min)}：` : `。网站给出的${noun}：`)
      : `${W.n(R.length)} ${ixn ? ixn + ' ' : 'US '}stock${R.length === 1 ? '' : 's'}${ph.length ? ' ' + ph.join(' and ') : ''}`
        + (min ? ` ${R.length === 1 ? 'has' : 'have'} ${W.pct(min)}+ ${noun}${site ? " (the site's models)" : ''}:` : `. The site's ${noun}:`);
    const line = (r) => {
      const base = `$${r.t} ${W.pct(prob(r, pk))}`;
      if (!long) return base;
      const mv = r.move || {}, v = d200(r), bits = [];
      if (fin(mv.move)) bits.push(zh ? `${W.day(mv.d)}${mv.move >= 0 ? '涨' : '跌'}${W.ab(mv.move, 1)}` : `${W.sp(mv.move)} on ${W.day(mv.d)}`);
      if (v != null) bits.push(zh ? `${v >= 0 ? '高于' : '低于'}200日线${W.ab(v, 1)}` : `${W.ab(v, 1)} ${v >= 0 ? 'above' : 'below'} its 200-day`);
      return base + (bits.length ? (zh ? '（' + bits.join('，') + '）' : ' · ' + bits.join(', ')) : '');
    };
    const ask = (k) => { const o = have.slice(0, Math.min(3, k)).map((r, i) => `${i + 1}) ${r.t}`).join(' '); return (zh ? '你会买哪一只？' : 'Which one would you buy? ') + o; };   // the cashtags are above: not twice
    const build = (k, withTag) => [head, ...have.slice(0, k).map(line), ...(k >= 2 ? [ask(k)] : []),
      ...(long ? [zh ? '历史数据与模型，不构成投资建议。' + (withTag && tag ? ' ' + tag : '') : 'History and models, not advice.' + (withTag && tag ? ' ' + tag : '')] : withTag && tag ? [tag] : [])].join('\n');
    if (long) return build(Math.min(10, have.length), true);
    for (let k = Math.min(5, have.length); k >= 1; k--) { const t = build(k, true); if (xlen(t) <= LIMIT) return t; }
    return build(1, false);
  }

  // ------------------------------------------------------------------ the hub's pieces (HTML strings)
  const ixTags = (r, lang) => r.ix.filter((k) => ['sp500', 'ndx', 'dji', 'sp400', 'sp600'].includes(k)).map((k) => (IX[k] || [k, k, k])[lang === 'zh' ? 2 : 1]).join(' · ');
  const hpct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const hsp = (v, d = 1) => (fin(v) ? `<span class="${v >= 0 ? 'positive' : 'negative'}">${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(100 * v), d)}%</span>` : '—');
  function regimeCell(r) {
    const t = (name, sub) => `<span class="ops-txt"><b>${name}</b>${sub ? `<br><span class="muted">${sub}</span>` : ''}</span>`;
    if (r.hi) return t(r.hi.ath ? 'All-time high' : 'At its highs', fin(r.hi.fwd63_up) ? `similar days: up ${hpct(r.hi.fwd63_up)} 3 months on` : '');
    if (r.lo) return t({ atl: 'All-time low', '52w': '52-week low', '3m': '3-month low' }[r.lo.reg] || 'Low', fin(r.lo.fwd63_up) ? `similar days: up ${hpct(r.lo.fwd63_up)} 3 months on` : '');
    if (r.rg) return t(r.rg.reg === 'narrow' ? 'Narrow range' : 'Wide range', fin(r.rg.break21) ? `breaks out within a month ${hpct(r.rg.break21)}` : '');
    return '<span class="muted">—</span>';
  }
  const HEADERS = ['Stock', 'Score', 'Probability', '±20% odds, 13 wks', 'vs 200-day', 'Highs / lows', 'Latest day', 'Signals'];
  /* one row of the results table (the hub's table(): sortable on the text of each cell) */
  function cells(r, doc, q) {
    const pk = PB[(q || {}).prob] ? q.prob : 'up3m', p = prob(r, pk), up = pk === 'up3m' || pk === 'up1m' || pk === 'buy3m';
    const v200 = d200(r), x = r.ma && Array.isArray(r.ma.x50_200) ? r.ma.x50_200 : null, mv = r.move || {};
    const tags = ixTags(r, 'en');
    const sig = r.f.filter((c) => !['ath', 'high', 'atl', 'low52', 'low3m', 'narrow', 'wide', 'above200', 'below200'].includes(c)).map((c) => (FL[c] || [c, c])[1]);
    return [
      `<button class="text-button" data-opd="${esc(r.t)}" title="The four-part read and a post draft"><b>${esc(r.t)}</b></button> <span class="muted">${esc(r.n || '')}</span>`
        + `<br><span class="muted ops-ix">${esc(tags ? tags + ' · ' : '')}${esc(r.s || '')}</span> <button class="text-button ops-draft" data-opd="${esc(r.t)}">✎ Draft</button>`,
      fin(r.score) ? `<b>${Math.floor(r.score)}</b>` : '<span class="muted">—</span>',                 // floored: only the week's top name shows 100
      p == null ? '—' : up ? `<b class="${p >= 0.5 ? 'positive' : 'negative'}">${hpct(p)}</b>` : `<b>${hpct(p)}</b>`,
      r.odds && fin(r.odds.up20_13) ? `${hpct(r.odds.up20_13)} / ${hpct(r.odds.dn20_13)}` : '—',
      (v200 == null ? (r.ma && fin(r.ma.gap40) ? hsp(ex(r.ma.gap40)) + '<br><span class="muted">40-week</span>' : '—') : hsp(v200))
        + (x && fin(x[2]) && x[2] <= 10 ? `<br><span class="muted">${x[1] > 0 ? 'golden' : 'death'} cross ${x[2]}d ago</span>` : ''),
      regimeCell(r),
      fin(mv.move) ? hsp(mv.move) + `<br><span class="muted">${fin(mv.pct) ? ord(mv.pct) + ' pct · ' : ''}${esc(words('en', '−', yearOf(mv.d)).day(mv.d))}</span>` : '—',
      sig.length ? `<span class="ops-flags">${esc(sig.join(' · '))}</span>` : '<span class="muted">—</span>',
    ];
  }
  function exportRow(r) {
    const o = r.opp || {}, od = r.odds || {}, a = r.ma || {}, mv = r.move || {};
    return { ticker: r.t, name: r.n, sector: r.s, indexes: r.ix.join(' '), score: r.score, p_beat_spy_13w: r.p_beat, p_higher_1m: o.up1m, p_higher_3m: o.up3m,
      p_buy_pays_3m: o.buy3m, range_p10_3m: o.r10, range_p90_3m: o.r90, flag: o.side, p_up20_13w: od.up20_13, p_down20_13w: od.dn20_13, p_up10_4w: od.up10_4,
      p_down10_4w: od.dn10_4, p_sp500_12m: od.sp500_12m, p_divcut_12m: od.divcut_12m, vs_200day: d200(r), vs_hybrid_line: ex(a.gap_hybrid), line_own_pct: a.hd_pct,
      last_close: mv.last, last_move: mv.move, last_move_pct: mv.pct, last_move_date: mv.d, rrg_quadrant: (r.rrg || {}).quad, signals: r.f.join(' ') };
  }
  function kpis(doc) {
    unpack(doc);
    const R = doc._rows, sp = R.filter((r) => r.ix.includes('sp500') && d200(r) != null), m = doc.market || {}, spy = m.spy || {};
    const W = words('en', '−', yearOf(doc.asof));
    return [['Stocks scanned', num(R.length), `weekly models of ${W.day(doc.asof) || '—'} · moves of ${W.day((doc.sources || {}).moves) || '—'}`],
      ['S&P 500 above 200-day', sp.length ? hpct(sp.filter((r) => d200(r) > 0).length / sp.length) : '—', `of ${num(sp.length)} members with daily closes`],
      ['At an all-time high', num(R.filter((r) => r.f.includes('ath')).length), `${num(R.filter((r) => r.f.includes('low52') || r.f.includes('atl')).length)} near a 52-week or all-time low`],
      ['SPY vs 40-week average', fin(spy.gap40) ? (spy.gap40 >= 0 ? '+' : '−') + num(Math.abs(100 * ex(spy.gap40)), 1) + '%' : '—', fin(m.recession_12m) ? `recession odds, 12 months: ${hpct(m.recession_12m)}` : '']];
  }
  function chipsHtml(on) {
    on = on || [];
    return `<div class="af-chips" role="group" aria-label="Signals: every one picked must hold">${FLAGS.map(([c, l]) => `<button type="button" class="pill${on.includes(c) ? ' on' : ''}" data-opchip="${c}" aria-pressed="${on.includes(c)}">${esc(l)}</button>`).join('')}`
      + (on.length ? `<button type="button" class="text-button" id="opch-clear">Clear ✕</button>` : '') + '</div>';
  }
  function composer(text, len, lang, opts) {
    const n = xlen(text), over = len === 'short' && n > LIMIT, zh = lang === 'zh';
    return `<div class="ops-compose"><div class="toolbar">`
      + `<div class="field"><label for="opdl">Post language</label><select id="opdl"><option value="en"${zh ? '' : ' selected'}>English</option><option value="zh"${zh ? ' selected' : ''}>中文</option></select></div>`
      + `<div class="field"><label for="opdm">Length</label><select id="opdm"><option value="short"${len === 'short' ? ' selected' : ''}>Short (fits 280)</option><option value="long"${len === 'long' ? ' selected' : ''}>Long (X Premium)</option></select></div>`
      + `<div class="field"><label for="opdh">Hashtag</label><select id="opdh"><option value="1"${opts.tag !== false ? ' selected' : ''}>${esc(TAG[lang])}</option><option value="0"${opts.tag === false ? ' selected' : ''}>None</option></select></div></div>`
      + `<label class="sr-only" for="opd-text">Post text</label><textarea id="opd-text" spellcheck="true" rows="${Math.min(26, String(text).split('\n').length + 1)}">${esc(text)}</textarea>`
      + `<div class="ops-bar"><span id="opd-count" class="ops-count${over ? ' over' : ''}">${num(n)} / ${len === 'short' ? LIMIT : '25,000'}</span>`
      + `<button type="button" class="action" id="opd-copy">Copy</button><a class="action" id="opd-x" target="_blank" rel="noopener" href="${esc(intentUrl(text))}">Open in X ↗</a><span id="opd-msg" class="muted"></span></div>`;
  }
  /* the composer for a post of the filtered list (the first names in the list's order) */
  function listHtml(doc, q, opts) {
    unpack(doc);
    q = q || {}; opts = opts || {};
    const lang = opts.lang === 'zh' ? 'zh' : 'en', len = opts.len === 'long' ? 'long' : 'short', pk = PB[q.prob] ? q.prob : 'up3m', R = listRows(doc, q);
    const text = opts.text != null ? opts.text : listDraft(doc, q, { lang, len, tag: opts.tag !== false });
    const left = (q.chips || []).filter((c) => !PHRASE[c]).map((c) => (FL[c] || [c, c])[1]);
    const s = doc._board[PB[pk][2]] || {};
    const warn = s.verdict === 'none' ? `<p class="negative">${esc(PB[pk][1])} has no out-of-sample skill (scoreboard below): a post quoting it says little. Pick another probability above.</p>` : '';
    return `<div class="panel ops-detail" id="ops-detail"><div class="ops-head"><h3>A post of this list</h3><span class="muted">${esc(num(R.length))} stocks · the first in the list's order · ${esc(PB[pk][1])}</span>`
      + `<button type="button" class="text-button" id="opd-close">Close ✕</button></div>${warn}`
      + (left.length ? `<p class="muted">${esc(left.join(' and '))}: left out of the post's list (a post gives no advice), so it counts and names the stocks the other filters pick.</p>` : '')
      + composer(text, len, lang, opts)
      + `<div class="explain">The filters become the opening line; the names come in the order of the list — change the sort to change them. Every number is the site's own; check before posting. History and models, not investment advice.</div></div></div>`;
  }
  const skillTxt = (s) => (s && fin(s.skill) ? `Brier skill ${num(100 * s.skill, 1)}%` + (fin(s.auc) ? ` · AUC ${num(s.auc, 3)}` : '') : '');
  /* the four-part read and the post composer for one stock */
  function detailHtml(r, doc, opts) {
    opts = opts || {};
    const lang = opts.lang === 'zh' ? 'zh' : 'en', len = opts.len === 'long' ? 'long' : 'short', zh = lang === 'zh';
    const F = facts(r, doc, lang, '−'), B = (unpack(doc), doc._board);
    const text = opts.text != null ? opts.text : draft(r, doc, { lang, len, tag: opts.tag !== false });
    const T = zh ? ['1 · 目前如何', '2 · 从历史上来讲', '3 · 网站推测', '4 · 你会买吗？'] : ['1 · Where it stands now', '2 · Historically', "3 · What the site's models say", '4 · Would you buy?'];
    const li = (L, part) => [...L, ...F.extra.filter((x) => x.part === part)].map((x) => `<li>${esc(x.full)}${x.key === 'up3m' && fin(x.skill) ? ` <span class="muted">(${zh ? '样本外Brier技能' : 'out-of-sample Brier skill'} ${num(100 * x.skill, 1)}%)</span>` : ''}</li>`).join('')
      || `<li class="muted">${zh ? '暂无' : 'Nothing on file'}</li>`;
    const sk = (B['combined:p'] || {}).skill;
    return `<div class="panel ops-detail" id="ops-detail">`
      + `<div class="ops-head"><h3>$${esc(r.t)} · ${esc(r.n || '')}</h3><span class="muted">${esc([ixTags(r, lang), r.s].filter(Boolean).join(' · '))}</span>`
      + `<button type="button" class="text-button" data-opt="${esc(r.t)}">Opportunity card →</button><button type="button" class="text-button" id="opd-close">Close ✕</button></div>`
      + `<div class="ops-four"><section><h4>${T[0]}</h4><ul>${li(F.now, 'now')}</ul></section><section><h4>${T[1]}</h4><ul>${li(F.hist, 'hist')}</ul></section>`
      + `<section><h4>${T[2]}</h4><ul>${li(F.model, 'model')}</ul></section><section><h4>${T[3]}</h4><p>${esc(F.ask.q)}</p><p class="muted">${F.ask.opts.map((x, i) => `${i + 1}) ${esc(x)}`).join('<br>')}</p></section></div>`
      + composer(text, len, lang, opts)
      + `<div class="explain">Every number is the site's own, from the weekly models of ${esc(doc.asof || '—')} and the daily move of ${esc((r.move || {}).d || '—')}; edit freely — a change of language, length or hashtag writes the draft again. `
      + `No link is added. Opportunity's odds of a higher price and the touch odds carry a tested edge over the base rate; the combined score is a ranking${fin(sk) ? ` (its own probability of beating SPY scores ${num(100 * sk, 2)}% over the base rate: no skill, so it is not quoted)` : ''}. History and models, not investment advice.</div></div></div>`;
  }
  const VERDICT = { useful: ['Useful skill', 'positive'], small: ['Small skill', ''], none: ['No skill', 'negative'], pays: ['Ranks and pays after costs', 'positive'],
    ranks: ["Ranks; the spread doesn't pay after costs", ''], weak: ['Weak: not reliably above zero', 'muted'], history: ['History, not a forecast', 'muted'] };
  const hzOf = (s) => { const m = /:(\d+)$/.exec(s.key || ''); return m ? m[1] : '13'; };
  function simpleTable(headers, rows, nums) {                   // not the hub's table(): that one pages with the main list
    const isNum = (i) => (nums ? nums.includes(i) : i > 0);
    return `<div class="tablebox ops-table"><table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((c) => `<tr>${c.map((v, i) => `<td class="${isNum(i) ? 'num' : ''}">${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function record(s) {
    if (s.kind === 'probability') return [skillTxt(s), fin(s.base) ? `base rate ${hpct(s.base, 1)}` : ''].filter(Boolean).join(' · ') || '—';
    if (s.kind === 'ranking') {
      const h = s.key && s.key.startsWith('combined') ? '13' : hzOf(s);
      return `rank correlation ${num(s.ic, 3)}${fin(s.ic_t) ? ` (t ${num(s.ic_t, 1)})` : ''} · best − worst fifth after costs ${hsp(s.net, 2)} per ${h} weeks${fin(s.net_t) ? ` (t ${num(s.net_t, 1)})` : ''}`
        + (fin(s.top) ? ` · top tenth vs SPY after costs ${hsp(s.top, 2)} (t ${num(s.top_t, 1)})` : '');
    }
    return 'Descriptive: what followed similar days';
  }
  function scoreboardHtml(doc) {
    const S = (doc && doc.scoreboard) || [];
    if (!S.length) return '';
    return simpleTable(['Model', 'Out-of-sample record', 'Verdict'], S.map((s) => {
      const v = VERDICT[s.verdict] || [s.verdict || '—', ''];
      return [`<span class="muted">${esc(s.group)}</span><br>${esc(s.model)}`, `<span class="ops-txt">${record(s)}</span>`, `<span class="ops-txt ${v[1]}">${esc(v[0])}</span>`];
    }), []);
  }
  function compositeHtml(doc) {
    const c = doc && doc.composite;
    if (!c) return `<div class="explain">The combined score appears once every model has kept its walk-forward forecast history (hist/cache/oos on the rotation-history branch, written by the next weekly build).</div>`;
    const W = c.weights_now || {}, tot = Object.values(W).reduce((a, b) => a + (+b || 0), 0) || 1, names = Object.fromEntries((c.components || []).map((x) => [x.key, x.name]));
    const per = Object.keys(((c.tests || {}).score_all) || {})[0];
    const g = (k, m) => (((c.tests || {})[k] || {})[per] || {})[m] || {};
    const cell = (k, m) => { const x = g(k, m); return fin(x.mean) ? `${m === 'ic' ? num(x.mean, 3) : hsp(x.mean, 2)}${fin(x.t) ? ` <span class="muted">t ${num(x.t, 1)}</span>` : ''}` : '—'; };
    const label = { score_all: 'Combined score, as published', score: 'Combined, on the names every model covers', equal: 'Equal weights (a check)', opp: names.opp || 'Opportunity', ma: names.ma || 'Moving averages', rrg: names.rrg || 'Hybrid RRG' };
    const cal = c.calibration || {};
    let out = `<p class="sub">Weights this year (each model's mean weekly rank correlation with the next 13 weeks against SPY, from the years before; a negative one weighs nothing): `
      + Object.entries(W).map(([k, v]) => `${esc(names[k] || k)} ${num(100 * v / tot, 0)}%`).join(' · ') + `.</p>`;
    out += simpleTable(['Tested ' + (per || ''), 'Rank correlation', 'Best − worst fifth, after costs', 'Top tenth vs SPY, after costs', 'Top tenth vs the average company', 'Bottom tenth vs the average'],
      ['score_all', 'score', 'equal', 'opp', 'ma', 'rrg'].filter((k) => (c.tests || {})[k]).map((k) => [esc(label[k] || k), cell(k, 'ic'), cell(k, 'net'), cell(k, 'top_spy'), cell(k, 'top_all'), cell(k, 'bottom_all')]));
    if (cal.table) {
      out += `<p class="sub">Its probability of beating SPY over 13 weeks (the beat rate of the score's tenth in the ${num(c.cal_years)} years before): Brier skill ${num(100 * (cal.skill || 0), 2)}% against always saying the base rate (${hpct(cal.base_rate, 1)}) — ${(cal.skill || 0) >= 0.02 ? 'useful' : (cal.skill || 0) >= 0.005 ? 'small' : 'none, so the page does not quote it as a forecast'}.</p>`;
      out += simpleTable(['Tenth of the score', 'Said', 'Happened', 'Name-weeks'], cal.table.map((x) => [esc(x.tenth), hpct(x.said, 1), hpct(x.happened, 1), num(x.n)]));
    }
    const L = doc.ledger;
    if (L) out += `<p class="sub">Live record: each week's scores are frozen when the week closes and scored 13 weeks later — ${num(L.resolved_weeks)} week(s) scored, ${num(L.pending_weeks)} waiting${fin(L.ic) ? `; rank correlation so far ${num(L.ic, 3)}, top − bottom tenth ${hsp(L.top_minus_bottom_tenth, 2)}` : ''}.</p>`;
    return out;
  }
  function columnsText(doc) {
    const R = doc.rules || {};
    return `<b>Score</b>: the combined score's rank this week, 0–100 (— where no tested model covers the stock). <b>Probability</b>: the one picked above, each with its out-of-sample record in the scoreboard below. `
      + `<b>+20% / −20%</b>: the odds of touching either within 13 weeks (Odds). <b>vs 200-day</b>: the latest daily close against its 200-day average (else the 40-week), with a 50/200-day cross in the last ${esc(R.recent_cross_days || 10)} trading days. `
      + `<b>Highs · lows · range</b>: at an all-time high or running at its highs, at an all-time / 52-week / 3-month low, or in a narrow or a wide sideways range, with what followed the 250 most similar days of other companies. `
      + `<b>Latest day</b>: the move and its percentile among the company's own days. <b>Signals</b>: Opportunity's buy / short flags, a big day (${esc(R.big_move_pct || 95)}th percentile or beyond), guidance in the last ${esc(R.guidance_days || 120)} days, far from its own hybrid line (top or bottom tenth of its own history), an S&P 500 candidate (10%+ odds), a dividend-cut risk (20%+). `
      + `Click a ticker for the four-part read and a post draft. Weekly models of ${esc(doc.asof || '—')}, daily moves of ${esc(((doc.sources || {}).moves) || '—')}; today's companies only (delisted names are missing from what the models learned).`;
  }
  /* the one-paragraph honest summary above the table, from the scoreboard's own numbers */
  function summaryText(doc) {
    unpack(doc);
    const B = doc._board, o = B['opp:3m'] || {}, c = B['combined:score_all'] || {}, cp = B['combined:p'] || {};
    const t20 = B['odds:up20_13'] || {}, noBeat = ['odds:beat13', 'rrg:beat13', 'combined:p'].every((k) => !B[k] || B[k].verdict === 'none');
    let s = '';
    if (fin(o.skill)) s += `Opportunity's chance of a higher price in 3 months beats always saying the base rate out of sample (Brier skill ${num(100 * o.skill, 1)}%), and so do the ±20% touch odds (${num(100 * (t20.skill || 0), 1)}%). `;
    if (fin(c.ic)) s += `The combined score is a ranking: from ${esc((doc.composite || {}).test_from || 2016)} it sorted the liquid stocks a little (rank correlation ${num(c.ic, 3)} with the next 13 weeks against SPY, t ${num(c.ic_t, 1)}), mostly through its bottom tenth (${hsp(c.bottom_all, 1)} against the average company); its top tenth ran ${hsp(c.top_all, 1)} against the average company and ${hsp(c.top, 1)} against SPY after costs. Use it to sort, not to pick. `;
    if (noBeat) s += 'No model here forecasts beating SPY better than its base rate. ';
    return s + 'History and models, not investment advice.';
  }

  const api = { unpack, select, sectors, facts, draft, listRows, listDraft, listHtml, xlen, intentUrl, cells, exportRow, kpis, chipsHtml, detailHtml, scoreboardHtml, compositeHtml, summaryText, columnsText,
    HEADERS, INDEXES, FLAGS, PROBS: PROBS.map((x) => [x[0], x[1]]), MINS, SORTS, LIMIT };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.OpportunityScan = api;
})();
