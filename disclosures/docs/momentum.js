/* Momentum tab (Disclosure Hub): who leads and who lags on momentum at the latest week, in three universes —
     Companies         the site's companies (data/market/history/momentum-latest.json: app/momentum.py in the
                       rotation-history build)
     ETFs              the ETFs that are neither leveraged nor inverse (data/etf/momentum-latest.json: the ETF build)
     Sectors & styles  the sector and style ETFs and the site's sector indices, computed here from rrg.json by the
                       formulas of momentum-view.js (no build of its own)
   ranked by the composite score or any factor, with the selection's breadth, the spread of the composite score and a
   summary by sector or asset class; a ticker opens its history (momentum-view.js). #momentum/NVDA opens a ticker,
   #momentum/etfs a universe. */
const MO_U = [['stocks', 'Companies'], ['etfs', 'ETFs'], ['sectors', 'Sectors & styles']];
const MO_SORT = [['comp', 'Composite score'], ['m12_1', '12-1 month return'], ['m6_1', '6-1 month return'], ['hi52', 'Distance from the 52-week high'],
  ['ra12', 'Vol-scaled 12-1'], ['rel_b', 'Relative to SPY (12-1)'], ['rel_s', 'Relative to the sector ETF (12-1)'], ['rcomp', 'Relative composite'],
  ['m1', 'Latest month'], ['vol', 'Volatility']];
const MO_SECTOR = { technology: 'Technology', communication: 'Communication services', 'consumer-disc': 'Consumer discretionary',
  'consumer-staples': 'Consumer staples', health: 'Health care', financials: 'Financials', 'real-estate': 'Real estate', energy: 'Energy',
  materials: 'Materials', industrials: 'Industrials', utilities: 'Utilities', other: 'Other' };
const MO_FIELDS = ['m12_1', 'm6_1', 'hi52', 'ra12', 'comp'];          // the ranked factors (app/momentum.py FIELDS)
const moStore = {};
const moHub = () => globalThis.FF_HUB_ROOT || '';
const moFin = v => v != null && Number.isFinite(+v);
const moSig = v => moFin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2) + 'σ' : '—';
const moPc = (v, d = 1) => moFin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—';
const moTone = (v, s) => moFin(v) && v !== 0 ? `<span class="${v > 0 ? 'positive' : 'negative'}">${s}</span>` : s;
function moData(u) {
  const m = moStore[u] || (moStore[u] = {});
  if (m.data || m.err || m.loading) return m;
  const url = moHub() + (u === 'etfs' ? 'data/etf/momentum-latest.json' : 'data/market/history/' + (u === 'sectors' ? 'rrg.json' : 'momentum-latest.json'));
  m.loading = fetch(url, { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error(r.status === 404 ? 'not published yet' : 'HTTP ' + r.status); return r.json() })
    .then(d => { m.data = u === 'sectors' ? moSectors(d) : moLatest(d); if (state.tab === 'momentum') render() })
    .catch(e => { m.err = e.message; if (state.tab === 'momentum') render() });
  return m;
}
// the latest-week file: {cols, rows: {ticker: [values in cols' order]}} → one object per ticker
function moLatest(d) {
  const cols = d.cols || [];
  const list = Object.entries(d.rows || {}).map(([t, r]) => { const o = { t }; cols.forEach((k, i) => { o[k] = r[i] }); return o });
  return { list, n: d.n || list.length, week: d.week, month: d.month, built: d.generated_at };
}
// percentiles 0–100, ties at their mean rank, none under five values (app/momentum.py _pct)
function moPct(vals) {
  const xs = Object.entries(vals).filter(([, v]) => moFin(v)).sort((a, b) => a[1] - b[1]), n = xs.length, out = {};
  if (n < 5) return out;
  for (let i = 0; i < n;) { let j = i; while (j + 1 < n && xs[j + 1][1] === xs[i][1]) j++; const r = (i + j) / 2; for (let k = i; k <= j; k++) out[xs[k][0]] = Math.round(100 * r / (n - 1)); i = j + 1 }
  return out;
}
// the sector and style ETFs and the site's sector indices of rrg.json, each read at the latest week SPY has a close
function moSectors(D) {
  const MV = window.MomentumView;
  if (!MV) throw Error('momentum-view.js did not load');
  const weeks = MV.grid(D), wk = Object.fromEntries(weeks.map((w, i) => [w, i])), n = weeks.length;
  const b = MV.fullOf(D.bench, wk, n), B = MV.prep(b);
  let L = n - 1; while (L >= 0 && b[L] == null) L--;
  const KIND = { 'sector-etf': 'Sector ETF', 'style-etf': 'Style & asset ETF', 'site-sector': 'Site companies' };
  const ents = [{ id: D.benchmark || 'SPY', name: 'S&P 500 (SPY)', group: 'bench', start: (D.bench || {}).start, c: (D.bench || {}).c }].concat((D.series || []).filter(s => KIND[s.group]));
  const list = [];
  if (L >= 0) for (const s of ents) {
    const c = MV.fullOf(s, wk, n), own = s.group === 'bench';
    const f = MV.factorAt(MV.prep(c), L, own ? null : B, null, own ? null : MV.prep(c.map((x, i) => (x && b[i] ? x / b[i] : null))));
    if (f) list.push(Object.assign({ t: s.id, n: s.name, g: own ? 'Benchmark' : KIND[s.group], s: s.sector || null }, f));
  }
  for (const k of MO_FIELDS) { const p = moPct(Object.fromEntries(list.map(r => [r.t, r[k]]))); list.forEach(r => { r['p_' + k] = p[r.t] ?? null }) }
  return { list, n: list.length, week: L >= 0 ? weeks[L] : null, built: D.generated_at, here: true };
}
// the spread of the composite score: bins of 0.5σ from −3σ to +3σ, the tails gathered at each end
function moHist(vals) {
  const xs = vals.filter(moFin);
  if (xs.length < 5) return '';
  const cnt = new Array(14).fill(0);
  xs.forEach(v => { cnt[v < -3 ? 0 : v >= 3 ? 13 : 1 + Math.floor((v + 3) / 0.5)]++ });
  const W = 520, H = 150, L = 8, R = 8, T = 14, Bm = 24, bw = (W - L - R) / cnt.length, mx = Math.max(...cnt) || 1;
  const at = e => L + (1 + (e + 3) / 0.5) * bw;
  let o = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="How the composite score is spread" style="display:block;width:100%;max-width:${W}px;height:auto">`;
  cnt.forEach((c, k) => {
    const h = (H - T - Bm) * c / mx, x = L + k * bw, mid = k === 0 ? -3.25 : k === 13 ? 3.25 : -3 + (k - 1) * 0.5 + 0.25;
    const lab = k === 0 ? 'below −3σ' : k === 13 ? '+3σ and above' : `${moSig(-3 + (k - 1) * 0.5)} to ${moSig(-3 + k * 0.5)}`;
    o += `<rect x="${(x + 1).toFixed(1)}" y="${(H - Bm - h).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${mid > 0 ? 'var(--mk-profit,#17734a)' : 'var(--mk-cost,#ea6a52)'}" opacity="${Math.min(1, 0.4 + Math.abs(mid) / 4).toFixed(2)}"><title>${esc(lab)}: ${c}</title></rect>`;
    if (c) o += `<text x="${(x + bw / 2).toFixed(1)}" y="${(H - Bm - h - 3).toFixed(1)}" text-anchor="middle" font-size="11" fill="var(--muted,#777)">${c}</text>`;
  });
  for (let e = -3; e <= 3; e++) o += `<text x="${at(e).toFixed(1)}" y="${H - 6}" text-anchor="middle" font-size="12" fill="var(--muted,#777)">${e ? moSig(e).replace('.00', '') : '0'}</text>`;
  o += `<line x1="${at(0)}" x2="${at(0)}" y1="${T}" y2="${H - Bm}" stroke="var(--ink-2,#555)" stroke-dasharray="3 3"/>`;
  return o + '</svg>';
}
function moMissing(u, err) {
  const what = u === 'etfs' ? 'The ETFs’ momentum readings are published by the ETF build (every four hours)' : 'The companies’ momentum readings are published by the rotation history’s build (every three hours)';
  return `<div class="empty">${esc(what)} and are not on file yet (${esc(err)}). Meanwhile: <button type="button" class="text-button" data-mou="sectors">the sectors and styles</button>, computed here from the weekly closes, or type a ticker above — a ticker's history is computed in your browser and needs no build.</div>`;
}
function momentumView() {
  const u = MO_U.some(x => x[0] === state.mou) ? state.mou : (state.mou = 'stocks');
  const t = String(state.mot || '').trim();
  let out = head('Momentum', 'Which stocks and ETFs are in a trend — on their own, against the market and against their sector: the 12-1 and 6-1 month returns, the distance from the 52-week high, relative momentum against SPY and the sector ETF, and a <b>composite score</b> that averages the 3-, 6- and 12-month trends, each in units of the ticker’s own volatility. Every reading uses the closes up to its week only; a reading of a factor, not a forecast or advice.', 'Derived · weekly closes');
  out += `<div class="toolbar">${field('mou', 'Universe', MO_U, u)}<div class="field wide"><label for="mot">A ticker's history</label><input id="mot" value="${esc(t)}" placeholder="e.g. NVDA, SMH, XLK · Enter"></div></div>`;
  if (t) return out + `<p><button type="button" class="action" id="mo-back">← The ${esc(((MO_U.find(x => x[0] === u) || [])[1] || '').toLowerCase())} leaderboard</button></p><div class="panel" id="mo-one" data-k="${esc(t)}"></div>`;
  const m = moData(u);
  if (m.err) return out + moMissing(u, m.err);
  if (!m.data) return out + empty(u === 'sectors' ? 'Reading the weekly closes…' : 'Reading the momentum readings…');
  const d = m.data, gkey = u === 'stocks' ? 's' : u === 'etfs' ? 'ac' : 'g', noun = u === 'stocks' ? 'companies' : u === 'etfs' ? 'ETFs' : 'lines';
  const gname = v => (u === 'stocks' ? MO_SECTOR[v] || v : v) || '—';
  const groups = uniq(d.list.map(r => r[gkey]).filter(Boolean)).sort((a, b) => gname(a).localeCompare(gname(b)));
  if (state.mogrp && !groups.includes(state.mogrp)) state.mogrp = '';
  const sorts = MO_SORT.filter(([k]) => k !== 'rel_s' || u === 'stocks');
  const sk = sorts.some(x => x[0] === state.mosort) ? state.mosort : 'comp', dir = state.modir === 'asc' ? 'asc' : 'desc';
  const aum = u === 'etfs' ? String(state.moaum ?? '1e8') : '0';
  out += `<div class="toolbar">${field('mosort', 'Rank by', sorts, sk)}${field('modir', 'Order', [['desc', 'Highest first'], ['asc', 'Lowest first']], dir)}${field('mogrp', u === 'stocks' ? 'Sector' : u === 'etfs' ? 'Asset class' : 'Kind', [['', 'All']].concat(groups.map(g => [g, gname(g)])), state.mogrp || '')}${u === 'etfs' ? field('moaum', 'Net assets', [['0', 'Any size'], ['1e8', '$100M or more'], ['1e9', '$1B or more'], ['1e10', '$10B or more']], aum) : ''}<div class="field"><label for="moq">Ticker or name</label><input id="moq" value="${esc(state.moq || '')}" placeholder="filter the list"></div></div>`;
  const q = String(state.moq || '').trim().toLowerCase();
  const rows = d.list.filter(r => (!state.mogrp || r[gkey] === state.mogrp) && (+aum <= 0 || (r.aum || 0) >= +aum) && (!q || r.t.toLowerCase().includes(q) || String(r.n || '').toLowerCase().includes(q)));
  rows.sort((a, b) => (!moFin(a[sk])) - (!moFin(b[sk])) || (dir === 'asc' ? a[sk] - b[sk] : b[sk] - a[sk]));
  // breadth of the selection
  const vals = k => rows.map(r => r[k]).filter(moFin);
  const sh = (k, f) => { const xs = vals(k); return xs.length ? xs.filter(f).length / xs.length : null };
  const med = k => { const xs = vals(k).sort((a, b) => a - b); return xs.length ? (xs[(xs.length - 1) >> 1] + xs[xs.length >> 1]) / 2 : null };
  out += `<p class="muted">${fmt(rows.length)} of ${fmt(d.list.length)} ${noun} · weekly closes to ${esc(d.week || '—')}${d.month ? ` · monthly ranks to ${esc(d.month)}` : ''}${d.here ? ' · computed in your browser from the rotation data' : d.built ? ` · built ${esc(String(d.built).replace('T', ' ').slice(0, 16))} UTC` : ''}${u === 'etfs' ? ' · left out: leveraged and inverse ETFs (their momentum is a multiple of another fund’s) and cash-like funds (under 3% a year of volatility: their trend is their yield)' : ''}</p>`;
  out += `<div class="metrics">${kpi('In an uptrend', pct(sh('m12_1', v => v > 0), 0), '12-1 month return above zero')}${kpi('Strong uptrend', pct(sh('comp', v => v > 1), 0), 'composite score above +1σ')}${kpi('Strong downtrend', pct(sh('comp', v => v < -1), 0), 'composite score below −1σ')}${kpi('Ahead of SPY', pct(sh('rel_b', v => v > 0), 0), '12-1 return, relative to SPY')}${kpi('Near the high', pct(sh('hi52', v => v >= -0.05), 0), 'within 5% of the 52-week high')}${kpi('Median composite', moSig(med('comp')), `of the ${fmt(vals('comp').length)} ${noun} with a year of closes`)}</div>`;
  const hist = moHist(vals('comp'));
  if (hist) out += `<div class="panel"><h3>How the composite score is spread</h3><p class="sub">Each ${u === 'stocks' ? 'company' : u === 'etfs' ? 'ETF' : 'line'} of the selection by its composite score at the latest week: above zero its 3-, 6- and 12-month trends point up on balance; beyond ±1σ the trend is strong for its own volatility.</p>${hist}</div>`;
  // by sector or asset class
  if (u !== 'sectors' && !state.mogrp && groups.length > 1) {
    const by = {};
    rows.forEach(r => { (by[r[gkey] || ''] = by[r[gkey] || ''] || []).push(r) });
    const gl = Object.entries(by).filter(([g, xs]) => g && xs.length >= 3).map(([g, xs]) => {
      const cs = xs.map(r => r.comp).filter(moFin).sort((a, b) => a - b), up = xs.map(r => r.m12_1).filter(moFin), ah = xs.map(r => r.rel_b).filter(moFin);
      return { g, n: xs.length, med: cs.length ? (cs[(cs.length - 1) >> 1] + cs[cs.length >> 1]) / 2 : null, up: up.length ? up.filter(v => v > 0).length / up.length : null,
        ah: ah.length ? ah.filter(v => v > 0).length / ah.length : null, top: xs.filter(r => moFin(r.comp)).sort((a, b) => b.comp - a.comp).slice(0, 3) };
    }).sort((a, b) => (moFin(b.med) ? b.med : -99) - (moFin(a.med) ? a.med : -99));
    if (gl.length) out += `<div class="panel"><h3>By ${u === 'stocks' ? 'sector' : 'asset class'}</h3><p class="sub">The median composite score of each ${u === 'stocks' ? 'sector’s companies' : 'asset class’s ETFs'} in the selection, the share in an uptrend and ahead of SPY, and the strongest by the composite score. Click one to list it.</p><div class="tablebox"><table><thead><tr><th>${u === 'stocks' ? 'Sector' : 'Asset class'}</th><th class="num">${esc(noun[0].toUpperCase() + noun.slice(1))}</th><th class="num">Median composite</th><th class="num">12-1 above zero</th><th class="num">Ahead of SPY</th><th>Strongest</th></tr></thead><tbody>`
      + gl.map(x => `<tr><td style="min-width:9em"><button type="button" class="text-button" data-mogrp="${esc(x.g)}">${esc(gname(x.g))}</button></td><td class="num">${fmt(x.n)}</td><td class="num">${moTone(x.med, moSig(x.med))}</td><td class="num">${pct(x.up, 0)}</td><td class="num">${pct(x.ah, 0)}</td><td style="white-space:nowrap">${x.top.map(r => `<a href="#momentum/${encodeURIComponent(r.t)}">${esc(r.t)}</a> <span class="muted">${moSig(r.comp)}</span>`).join(' · ')}</td></tr>`).join('')
      + '</tbody></table></div></div>';
  }
  // the leaderboard
  const rk = (r, k) => (moFin(r['p_' + k]) ? String(Math.round(r['p_' + k])) : '—');
  const headers = ['Ticker', 'Name', u === 'stocks' ? 'Sector' : u === 'etfs' ? 'Asset class' : 'Kind', 'Composite', 'Rank', ...(u === 'etfs' ? ['Rank in class', 'Net assets'] : []), '12-1', '6-1', 'Latest month', 'From 52w high', 'Vol-scaled 12-1', 'vs SPY', ...(u === 'stocks' ? ['vs sector ETF'] : []), 'Relative composite'];
  exported = rows.map(r => ({ ticker: r.t, name: r.n, [u === 'stocks' ? 'sector' : u === 'etfs' ? 'asset_class' : 'kind']: gname(r[gkey]), composite: r.comp, composite_rank: r.p_comp, ...(u === 'etfs' ? { rank_in_class: r.p_comp_group, net_assets: r.aum } : {}),
    m12_1: r.m12_1, m6_1: r.m6_1, m1: r.m1, from_52w_high: r.hi52, vol: r.vol, vol_scaled_12_1: r.ra12, rel_spy: r.rel_b, ...(u === 'stocks' ? { rel_sector: r.rel_s } : {}), rel_composite: r.rcomp, week: d.week }));
  out += `<div class="section-head"><h3>${esc((sorts.find(x => x[0] === sk) || [])[1])}, ${dir === 'asc' ? 'lowest' : 'highest'} first</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out += `<p class="sub">Rank: the percentile (0–100) of the composite score among all ${fmt(d.n || d.list.length)} ${noun}${u === 'etfs' ? '; in class: among the ETFs of the same asset class' : ''}. 12-1 and 6-1: the return over 12 and 6 months, skipping the latest month. vs SPY${u === 'stocks' ? ' and vs sector ETF' : ''}: the 12-1 return less the benchmark's (log difference). Relative composite: the composite score of the line ticker ÷ SPY. Click a ticker for its history; click a column to sort by it.</p>`;
  const tk = r => (String(r.t).startsWith('s:') ? MO_SECTOR[r.s] || r.t.slice(2) : r.t);      // a site sector index by its sector
  out += table(headers, rows.map(r => [`<a href="#momentum/${encodeURIComponent(r.t)}"><b>${esc(tk(r))}</b></a>`, esc(String(r.n || '').slice(0, 48)), esc(gname(r[gkey])),
    moTone(r.comp, moSig(r.comp)), rk(r, 'comp'), ...(u === 'etfs' ? [moFin(r.p_comp_group) ? String(r.p_comp_group) : '—', moFin(r.aum) ? '$' + compact(r.aum) : '—'] : []),
    moTone(r.m12_1, moPc(r.m12_1)), moTone(r.m6_1, moPc(r.m6_1)), moPc(r.m1), moPc(r.hi52), moFin(r.ra12) ? (r.ra12 < 0 ? '−' : '') + Math.abs(r.ra12).toFixed(2) : '—',
    moTone(r.rel_b, moPc(r.rel_b)), ...(u === 'stocks' ? [moTone(r.rel_s, moPc(r.rel_s))] : []), moTone(r.rcomp, moSig(r.rcomp))]));
  out += `<details class="panel"><summary>Definitions and limits</summary><p class="sub">12-1 = P[t−4w] ÷ P[t−52w] − 1 (Jegadeesh &amp; Titman 1993; the skipped month after Jegadeesh 1990). Composite score = the mean over 13, 26 and 52 weeks of ln(P[t−4w] ÷ P[t−w]) ÷ (the weekly σ of the last 52 weekly returns × √(w − 4)) — volatility-scaled time-series momentum (Moskowitz, Ooi &amp; Pedersen 2012) over three horizons; σ is floored at 0.4% a week (≈ 2.9% a year) so a cash-like fund's steady yield does not read as an extreme trend. Relative: against SPY and the company's sector SPDR; the relative composite is the composite score of the price ratio. 52-week high: George &amp; Hwang (2004). Vol-scaled 12-1: 12-1 ÷ the annualised volatility, with the same floor (Barroso &amp; Santa-Clara 2015). Weekly total-return closes (Yahoo Finance; Stooq as the fallback), a month = 4 weeks; today's tickers only (survivorship); no costs, borrow or taxes. Momentum has crashed after bear-market lows (Daniel &amp; Moskowitz 2016). Not investment advice.</p></details>`;
  return out;
}
function bindMomentum() {
  if (state.tab !== 'momentum') return;
  const hash = h => { try { history.replaceState(null, '', h) } catch (e) {} };
  for (const k of ['mou', 'mosort', 'modir', 'mogrp', 'moaum']) if ($(k)) $(k).onchange = e => { state[k] = e.target.value; if (k === 'mou') { state.mogrp = ''; hash('#momentum/' + state.mou) } state.page = 0; render() };
  if ($('moq')) { $('moq').onchange = e => { state.moq = e.target.value; state.page = 0; render() }; $('moq').onkeydown = e => { if (e.key === 'Enter') e.target.blur() } }
  if ($('mot')) { $('mot').onchange = e => { state.mot = e.target.value.trim(); hash('#momentum' + (state.mot ? '/' + encodeURIComponent(state.mot) : '')); render() }; $('mot').onkeydown = e => { if (e.key === 'Enter') e.target.blur() } }
  if ($('mo-back')) $('mo-back').onclick = () => { state.mot = ''; hash('#momentum/' + (state.mou || 'stocks')); render() };
  document.querySelectorAll('#workspace [data-mou]').forEach(b => b.onclick = () => { state.mou = b.dataset.mou; state.mogrp = ''; state.page = 0; hash('#momentum/' + state.mou); render() });
  document.querySelectorAll('#workspace [data-mogrp]').forEach(b => b.onclick = () => { state.mogrp = b.dataset.mogrp; state.page = 0; render(); scrollTo({ top: 0, behavior: 'smooth' }) });
  const el = $('mo-one');
  if (el && window.MomentumView && el.dataset.on !== el.dataset.k) {
    const k = el.dataset.k;
    el.dataset.on = k;
    window.MomentumView.render(el, { ticker: k, hub: moHub(), here: () => state.tab === 'momentum' && String(state.mot || '').trim() === k });
  }
}
function momentumDeepLink(arg) {
  const v = String(decodeURIComponent(arg || '')).trim(), u = { stocks: 'stocks', companies: 'stocks', etfs: 'etfs', sectors: 'sectors' }[v.toLowerCase()];
  if (u) { state.mou = u; state.mot = '' } else state.mot = v;
}
function momentumNotice() {
  const u = state.mou || 'stocks', m = moStore[u];
  if (state.mot || !m || (!m.data && !m.err)) return null;
  return m.err ? { stale: false, text: `Derived view · Momentum · the ${u === 'etfs' ? 'ETF' : 'companies’'} readings are ${m.err}` }
    : { stale: false, text: `Derived view · Momentum · weekly closes to ${m.data.week || '—'}${m.data.built ? ' · built ' + m.data.built : ''}` };
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { momentum: momentumView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { momentum: bindMomentum });
window.HUB_NOTICES = Object.assign(window.HUB_NOTICES || {}, { momentum: momentumNotice });
window.momentumDeepLink = momentumDeepLink;
if (typeof module !== 'undefined') module.exports = { moData, moLatest, moPct, moSectors, moHist, momentumView, bindMomentum, momentumDeepLink, momentumNotice, moStore };
