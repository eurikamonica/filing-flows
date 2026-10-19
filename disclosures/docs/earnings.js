/* 4.18 Earnings season — the reports of the next three weeks and the last nine, side by side: previews (consensus,
   Polymarket, the options-implied move against the usual move, our beat probability and estimates), the scorecard
   (Polymarket vs our model vs analysts, week by week, with calibration), the season's breadth by sector and its calendar,
   post-earnings drift, peer read-through, squeeze candidates, options VRP / skew / put-call, the non-GAAP gap and
   Polymarket vs options distributions. Every forecast is frozen before the report (app/forecast_book.py) and scored after.
   Data: data/research/earnings/*.json (app/earnings_season.py, branch research-earnings); one company:
   EarningsPreviewView (earnings-view.js). */
const erStore = {};
function erData(name) {
  const m = erStore[name] || (erStore[name] = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/research/earnings/' + name + '.json', { cache: 'no-cache' })
    .then((r) => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json(); })
    .then((d) => { m.data = d; if (state.tab === 'earnings') render(); })
    .catch((e) => { m.err = e.message; if (state.tab === 'earnings') render(); });
  return m;
}
const ER_VIEWS = [['calendar', 'Calendar and breadth'], ['previews', 'Previews: the next three weeks'], ['scorecard', 'Scorecard: Polymarket vs our model vs analysts'],
  ['drift', 'Post-earnings drift'], ['readthrough', 'Peer read-through'], ['squeeze', 'Short squeeze candidates'], ['options', 'Options: VRP, skew, put/call'],
  ['nongaap', 'Non-GAAP vs GAAP gap'], ['distributions', 'Polymarket vs options distributions']];
const erP = (v, d = 0) => (v == null || !Number.isFinite(+v) ? '—' : fmt(v * 100, d) + '%');
const erS = (v, d = 1) => (v == null || !Number.isFinite(+v) ? '—' : `<span class="${v > 0 ? 'positive' : v < 0 ? 'negative' : ''}">${v > 0 ? '+' : v < 0 ? '−' : ''}${fmt(Math.abs(v) * 100, d)}%</span>`);
const erU = (v) => (v == null || !Number.isFinite(+v) ? '—' : (v < 0 ? '−$' : '$') + fmt(Math.abs(v), 2));
const erTk = (t) => `<button class="text-button" data-ert="${esc(t)}"><b>${esc(t)}</b></button>`;
function erRows(d) { const F = d.fields || []; return (d.rows || []).map((x) => { const o = {}; F.forEach((k, i) => (o[k] = x[i])); return o; }); }

function erHeat(cal) {
  if (!cal || !cal.length) return empty('No reports on the calendar yet.');
  const byDay = {}; cal.forEach((c) => (byDay[c.date] = c));
  const first = new Date(cal[0].date + 'T00:00:00Z'), last = new Date(cal[cal.length - 1].date + 'T00:00:00Z');
  first.setUTCDate(first.getUTCDate() - ((first.getUTCDay() + 6) % 7));
  let h = '<div class="er-heat"><div class="er-hd">Mon</div><div class="er-hd">Tue</div><div class="er-hd">Wed</div><div class="er-hd">Thu</div><div class="er-hd">Fri</div>';
  for (let d = new Date(first); d <= last; d.setUTCDate(d.getUTCDate() + 1)) {
    const wd = d.getUTCDay(); if (wd === 0 || wd === 6) continue;
    const k = d.toISOString().slice(0, 10), c = byDay[k];
    if (!c) { h += `<div class="er-cell er-empty"><span>${d.getUTCDate()}</span></div>`; continue; }
    const share = c.n ? c.beats / c.n : null;
    const bg = share == null ? 'var(--line,#e8e8e8)' : `hsl(${Math.round(share * 120)},55%,${c.n >= 10 ? 42 : 55}%)`;
    const tip = `${k}: ${c.n ? `${c.beats} of ${c.n} beat${c.mean_surprise != null ? `, mean surprise ${(c.mean_surprise * 100).toFixed(1)}%` : ''}` : ''}${c.upcoming ? `${c.n ? '; ' : ''}${c.upcoming} due` : ''}`;
    h += `<div class="er-cell" style="background:${bg}${share == null ? '' : ';color:#fff'}" title="${esc(tip)}"><span>${d.getUTCDate()}</span><b>${c.n ? `${c.beats}/${c.n}` : c.upcoming ? c.upcoming + ' due' : ''}</b></div>`;
  }
  return h + '</div>';
}

function erCalib(sc) {
  const series = [['Polymarket', (sc.polymarket || {}).bins || [], '#8a4fd6'], ['Our model (walk-forward)', (sc.model_backtest || {}).bins || [], '#2a78d6'], ['Our model (frozen)', (sc.model_frozen || {}).bins || [], '#16a085']];
  const W = 360, H = 300, L = 40, B = 34, T = 10, R = 10, x = (p) => L + p * (W - L - R), y = (p) => T + (1 - p) * (H - T - B);
  let s = `<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Calibration: forecast probability against how often reports beat"><line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--muted,#999)" stroke-dasharray="4 4"/>`;
  for (const p of [0, 0.5, 1]) s += `<text class="axis" x="${x(p)}" y="${H - 12}" text-anchor="middle">${p * 100}%</text><text class="axis" x="${L - 6}" y="${y(p) + 4}" text-anchor="end">${p * 100}%</text>`;
  for (const [name, bins, col] of series) {
    const pts = bins.filter((b) => b[4] >= 3);
    if (!pts.length) continue;
    s += `<path d="${pts.map((b, i) => (i ? 'L' : 'M') + x(b[2]).toFixed(1) + ',' + y(b[3]).toFixed(1)).join(' ')}" fill="none" stroke="${col}" stroke-width="2"/>`;
    pts.forEach((b) => (s += `<circle cx="${x(b[2])}" cy="${y(b[3])}" r="${Math.min(7, 2 + Math.sqrt(b[4]) / 2)}" fill="${col}"><title>${esc(name)}: forecast ${(b[2] * 100).toFixed(0)}%, beat ${(b[3] * 100).toFixed(0)}% of ${b[4]}</title></circle>`));
  }
  return s + `</svg><div class="er-legend">${series.map(([n, b, c]) => (b.length ? `<span><i style="background:${c}"></i>${esc(n)}</span>` : '')).join('')}</div>`;
}

function erScore(s, label) {
  if (!s || !s.n) return kpi(label, '—', 'no resolved forecasts yet');
  return kpi(label, `Brier ${fmt(s.brier, 3)}`, `${fmt(s.n)} reports · right ${erP(s.hit_rate)} · always-the-base-rate ${fmt(s.brier_base_rate, 3)}`);
}

function earningsView() {
  state.ev = ER_VIEWS.some((v) => v[0] === state.ev) ? state.ev : 'calendar';
  const st = erData('status');
  let out = `<div class="toolbar">${field('ev', 'View', ER_VIEWS, state.ev, true)}<div class="field"><label for="erq">One company (ticker)</label><input id="erq" value="${esc(state.etk || '')}" placeholder="e.g. AAPL"></div></div>`;
  out += `<div class="explain">The reports of the next three weeks and the last nine: analysts' consensus (Yahoo Finance), Polymarket's "beat quarterly earnings" markets, the options-implied move (CBOE) against the stock's usual two-session move, and our own beat probability — a logistic regression on earlier reports, <b>frozen three days before each report</b> and scored after it, beside Polymarket's price 24 hours before. History is what the consensus collector has gathered (about four quarters per company), so the record grows every season. ${st.data ? `Built ${esc(String(st.data.built_at || '').slice(0, 16).replace('T', ' '))} UTC · ${fmt(st.data.previews)} previews · ${fmt(st.data.reports_history)} past reports.` : ''} Not investment advice.</div>`;
  if (state.etk) return out + `<div id="er-co" class="panel"></div>`;
  if (st.err && !st.data) return out + empty(`The earnings-season files are not published yet (${st.err}). They are built before the open and after the close by .github/workflows/research-earnings.yml.`);
  const v = state.ev;
  if (v === 'calendar') {
    const s = erData('season');
    if (!s.data) return out + empty(s.err ? 'Could not load the season (' + s.err + ').' : 'Loading the season…');
    const d = s.data, o = d.overall || {}, p = d.previous || {};
    out += `<div class="metrics">${kpi('Season', d.season || '—', `${fmt(o.n)} reported so far`)}${kpi('EPS beat rate', erP(o.beat_pct), p.season ? `${p.season}: ${erP(p.beat_pct)} of ${fmt(p.n)}` : '')}${kpi('Mean · median surprise', `${erP(o.mean_surprise, 1)} · ${erP(o.median_surprise, 1)}`, 'actual vs average estimate')}${kpi('Revenue beat rate', erP(o.rev_beat_pct), `${fmt(o.rev_n)} with a pre-report estimate`)}${kpi('Estimates after the report', `${fmt(o.est_raised)} raised · ${fmt(o.est_cut)} cut`, 'current-year EPS consensus, a week later')}${kpi('Mean reaction vs SPY', erP(o.mean_reaction, 1), 'two sessions around the report')}</div>`;
    out += `<h3 class="er-h">The calendar</h3><p class="sub">Each weekday of the season: how many reports beat (green) or missed (red), and the reports still due in the next three weeks.</p>${erHeat(d.calendar)}`;
    out += `<h3 class="er-h">By sector</h3>` + table(['Sector', 'Reported', 'Beat', 'Mean surprise', 'Revenue beat', 'Estimates raised · cut', 'Reaction vs SPY'],
      (d.sectors || []).map((r) => [esc(r.sector), fmt(r.n), erP(r.beat_pct), erS(r.mean_surprise), r.rev_n ? erP(r.rev_beat_pct) : '—', `${fmt(r.est_raised)} · ${fmt(r.est_cut)}`, erS(r.mean_reaction)]));
    out += `<h3 class="er-h">Seasons on file</h3>` + table(['Season', 'Reports', 'Beat rate'], (d.history || []).slice().reverse().map((r) => [esc(r.season), fmt(r.n), erP(r.beat_pct)]));
    return out + `<p class="sub">${esc(d.note || '')}</p>`;
  }
  if (v === 'previews') {
    const ix = erData('index');
    if (!ix.data) return out + empty(ix.err ? 'Could not load the previews (' + ix.err + ').' : 'Loading the previews…');
    const rows = erRows(ix.data).filter((r) => r.days_to >= 0);
    return out + table(['Ticker', 'Reports', 'Sector', 'Consensus EPS', 'Analysts', 'Polymarket: beats', 'Our model', 'Implied move', 'Usual move', 'Beat rate', 'Dispersion', '30-day revision'],
      rows.map((r) => [erTk(r.ticker) + `<br><span class="muted">${esc(r.name || '')}</span>`, esc(r.report_date) + (r.frozen ? ' <span class="tag">frozen</span>' : ''), esc(r.sector || ''), erU(r.eps), fmt(r.n), erP(r.polymarket), erP(r.model),
        r.implied != null ? '±' + erP(r.implied, 1) : '—', r.avg_move != null ? '±' + erP(r.avg_move, 1) : '—', erP(r.beat_rate), erP(r.dispersion), erS(r.revision_30d)])) + `<p class="sub">${esc(ix.data.note || '')}</p>`;
  }
  if (v === 'scorecard') {
    const s = erData('scorecard');
    if (!s.data) return out + empty(s.err ? 'Could not load the scorecard (' + s.err + ').' : 'Loading the scorecard…');
    const d = s.data, cm = d.common || {};
    out += `<div class="metrics">${erScore(d.polymarket, 'Polymarket (24 h before)')}${erScore(d.model_backtest, 'Our model, walk-forward')}${erScore(d.model_frozen, 'Our model, frozen live')}${cm.n ? kpi('Same reports, head to head', `${fmt(cm.n)} reports`, `Brier: model ${fmt((cm.model || {}).brier, 3)} · Polymarket ${fmt((cm.polymarket || {}).brier, 3)} · both averaged ${fmt((cm.blend || {}).brier, 3)}`) : ''}${(d.eps_vs_analysts || {}).n ? kpi('Our EPS vs analysts', erP(d.eps_vs_analysts.a_closer), `closer in ${fmt(d.eps_vs_analysts.n)} reports`) : kpi('Our EPS vs analysts', '—', 'scored once frozen estimates resolve')}${(d.moves || {}).n ? kpi('Moves inside the implied move', erP(d.moves.inside), `${fmt(d.moves.n)} reports · actual ÷ implied ${fmt(d.moves.mean_ratio, 2)}`) : ''}</div>`;
    out += `<div class="er-two"><div><h3 class="er-h">Calibration</h3><p class="sub">Forecast probability against how often those reports beat. On the dashed line a forecast means what it says.</p>${erCalib(d)}</div><div><h3 class="er-h">Week by week</h3>` +
      table(['Week of', 'Reports', 'Beat', 'Polymarket right', 'Our model right', 'of them frozen', 'Inside implied move'], (d.weeks || []).map((w) => [esc(w.week), fmt(w.n), fmt(w.beats), w.pm_n ? `${w.pm_right} of ${w.pm_n}` : '—', w.model_n ? `${w.model_right} of ${w.model_n}` : '—', w.frozen_n ? `${w.frozen_right} of ${w.frozen_n}` : '—', w.moves_n ? `${w.moves_inside} of ${w.moves_n}` : '—'])) + `</div></div>`;
    out += `<h3 class="er-h">Every report</h3>` + table(['Ticker', 'Reported', 'Estimate', 'Actual', 'Surprise', 'Polymarket', 'Our model', 'Implied', 'Move'],
      (d.rows || []).map((r) => [erTk(r.ticker), esc(r.reported), erU(r.est), erU(r.act), erS(r.surprise), r.polymarket != null ? erP(r.polymarket) + (r.polymarket_right ? ' ✓' : ' ✗') : '—',
        r.model != null ? erP(r.model) + (r.model_right ? ' ✓' : ' ✗') + (r.model_source === 'backtest' ? ' <span class="muted">bt</span>' : '') : '—', r.implied != null ? '±' + erP(r.implied, 1) : '—', erS(r.move)]));
    return out + `<p class="sub">${esc(d.note || '')} Model inputs in use: ${esc(((d.model || {}).inputs_used || []).join(', '))}.</p>`;
  }
  const simple = {
    drift: ['pead', ['Ticker', 'Reported', 'Surprise', 'SUE', 'Reaction vs SPY', 'Predicted 60-session drift', '80% range'],
      (r) => [erTk(r.ticker), esc(r.reported), erS(r.surprise), fmt(r.sue, 2), erS(r.reaction), erS(r.pred), r.low != null ? `${erS(r.low)} to ${erS(r.high)}` : '—']],
    readthrough: ['readthrough', ['Ticker', 'Reports', 'Sector', 'Peers reported', 'Their mean surprise', 'Read-through'],
      (r) => [erTk(r.ticker), esc(r.report_date), esc(r.sector || ''), fmt(r.n_peers), erS(r.peer_mean), erS(r.pred)]],
    squeeze: ['squeeze', ['Ticker', 'Sector', 'Short % of shares', 'Days to cover', '1-month return', 'Score', 'Next report'],
      (r) => [erTk(r.ticker) + `<br><span class="muted">${esc(r.name || '')}</span>`, esc(r.sector || ''), erP(r.short_pct, 1), fmt(r.dtc, 1), erS(r.momentum), fmt(r.score, 2), esc(r.next_report || '—')]],
    options: ['options', ['Ticker', 'IV 30d', 'Realised 30d', 'VRP', 'Skew 25Δ', 'Put/call OI', 'Put/call volume'],
      (r) => [erTk(r.ticker), erP(r.iv30, 1), erP(r.rv30, 1), erS(r.vrp), fmt(r.skew25, 3), fmt(r.pc_oi, 2), fmt(r.pc_vol, 2)]],
    nongaap: ['nongaap', ['Ticker', 'Sector', 'Gap now (share of Street EPS)', 'Before (average)', 'Widening', 'Flag'],
      (r) => [erTk(r.ticker) + `<br><span class="muted">${esc(r.name || '')}</span>`, esc(r.sector || ''), erP(r.gap_pct), erP(r.gap_prev_mean), erS(r.widening), r.flag ? '<b>widening</b>' : '']],
    distributions: ['distributions', ['Ticker', 'Market', 'Date', 'Polymarket median', 'Options median', 'Options 80% range'],
      (r) => [erTk(r.ticker), r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title || '')}</a>` : esc(r.title || ''), esc(r.end || ''), erU((r.polymarket || {}).median), r.options ? erU(r.options.median) : (r.consensus != null ? 'consensus ' + erU(r.consensus) : '—'), r.options ? `${erU(r.options.q10)}–${erU(r.options.q90)}` : '—']],
  }[v];
  const m = erData(simple[0]);
  if (!m.data) return out + empty(m.err ? 'Could not load (' + m.err + ').' : 'Loading…');
  return out + table(simple[1], (m.data.rows || []).map(simple[2])) + `<p class="sub">${esc(m.data.note || '')}</p>`;
}

function bindEarnings() {
  if (state.tab !== 'earnings') return;
  if ($('ev')) $('ev').onchange = (e) => { state.ev = e.target.value; state.etk = ''; state.page = 0; render(); };
  if ($('erq')) { $('erq').onchange = (e) => { state.etk = e.target.value.trim().toUpperCase(); render(); }; $('erq').onkeydown = (e) => { if (e.key === 'Enter') e.target.blur(); }; }
  document.querySelectorAll('#workspace [data-ert]').forEach((b) => (b.onclick = () => { state.etk = b.dataset.ert; render(); scrollTo({ top: 0, behavior: 'smooth' }); }));
  const co = $('er-co');
  if (co && window.EarningsPreviewView) window.EarningsPreviewView.render(co, { ticker: state.etk, hub: '' });
  if (!document.getElementById('er-css')) {
    const s = document.createElement('style'); s.id = 'er-css';
    s.textContent = `.er-heat{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:4px;max-width:640px;margin:8px 0 16px}.er-hd{font-size:11px;color:var(--muted,#888);text-align:center}
.er-cell{border-radius:6px;min-height:46px;padding:4px 6px;font-size:11px;display:flex;flex-direction:column;justify-content:space-between}.er-cell b{font-size:13px;font-variant-numeric:tabular-nums}.er-empty{background:transparent;border:1px dashed var(--line,#ddd);color:var(--muted,#aaa)}
.er-two{display:grid;grid-template-columns:minmax(260px,380px) 1fr;gap:20px}@media(max-width:820px){.er-two{grid-template-columns:1fr}}.er-h{margin:18px 0 4px;font-size:15px}
.er-legend span{display:inline-flex;align-items:center;gap:5px;margin-right:12px;font-size:12px}.er-legend i{width:12px;height:3px;display:inline-block}`;
    document.head.appendChild(s);
  }
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { earnings: earningsView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { earnings: bindEarnings });
