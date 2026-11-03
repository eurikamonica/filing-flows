/* Screener — the hub tab: every listed company in one table (data/screener.json, scripts/screener.py: the latest quarter,
   fundamentals and factor scores, the earnings quality score, the next report, 13F flows, insider trades, short interest,
   cash, debt and runway), filtered by any mix of thresholds, sorted by any column, exported as CSV. Ten preset screens
   (the same ones disclosures/screener/ lists as plain pages). Deep links: #screener/<preset>. */
const scStore = {};
function scData() {
  const m = scStore.d || (scStore.d = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/screener.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(d => { const F = d.fields; d.list = (d.rows || []).map(r => Object.fromEntries(F.map((k, i) => [k, r[i]]))); m.data = d; if (scStore.pending) { scApplyPreset(d, scStore.pending); scStore.pending = null; } if (state.tab === 'screener') render() })
    .catch(e => { m.err = e.message; if (state.tab === 'screener') render() });
  return m;
}
// the filters: key, label, kind (min | max | pick | flag), field, unit (pct: the field is a fraction; pts: percentage points; usd; days; x)
const SC_FILTERS = [
  ['mcap', 'Market value ≥ $B', 'min', 'mcap', 'B'], ['growth', 'Revenue growth FY ≥ %', 'min', 'growth', 'pct'], ['yoy', 'Revenue Y/Y (quarter) ≥ %', 'min', 'yoy', 'pts'],
  ['om', 'Operating margin ≥ %', 'min', 'om', 'pts'], ['fcf', 'FCF yield ≥ %', 'min', 'fcf_y', 'pct'], ['sy', 'Shareholder yield ≥ %', 'min', 'sy', 'pct'], ['roic', 'ROIC ≥ %', 'min', 'roic', 'pct'],
  ['evs', 'EV / sales ≤', 'max', 'ev_s', 'x'], ['f', 'Piotroski F ≥', 'min', 'f_score', 'x'], ['q', 'Quality score ≥', 'min', 'qscore', 'x'],
  ['beat', 'Beat rate ≥ %', 'min', 'beat_rate', 'pct'], ['days', 'Reports within days', 'days', 'report_date', 'days'], ['r3', '3-month return ≥ %', 'min', 'r3m', 'pct'],
  ['r1y', '12-month return ≥ %', 'min', 'r1y', 'pct'], ['high', 'From 52-wk high ≤ %', 'max', 'from_high', 'pct'], ['f13', '13F net buying ≥ $M', 'min', 'f13_net', 'M'],
  ['insb', 'Insider buys ≥', 'min', 'ins_buys', 'x'], ['dtc', 'Days to cover ≥', 'min', 'short_dtc', 'x'], ['shchg', 'Short interest change ≥ %', 'min', 'short_chg', 'pts'],
  ['netcash', 'Net cash ≥ $B', 'min', 'net_cash', 'B'], ['runway', 'Runway ≤ months', 'max', 'runway_months', 'x']];
const SC_COLS = [['mcap', 'Mkt value', 'usd'], ['price', 'Price', 'num'], ['revenue', 'Revenue, qtr', 'usd'], ['yoy', 'Rev Y/Y', 'pts'], ['om', 'Op. margin', 'pts'], ['growth', 'Growth FY', 'pct'],
  ['margin', 'Margin FY', 'pct'], ['fcf_y', 'FCF yield', 'pct'], ['sy', 'Sh. yield', 'pct'], ['roic', 'ROIC', 'pct'], ['ev_s', 'EV/S', 'num'], ['f_score', 'Piotroski', 'num'], ['z', 'Altman Z', 'num'],
  ['z_zone', 'Zone', 'str'], ['m_flag', 'Beneish', 'flag'], ['qmj', 'QMJ', 'num'], ['qscore', 'Quality', 'num'], ['qgrade', 'Grade', 'str'], ['report_date', 'Reports', 'date'], ['beat_rate', 'Beat rate', 'pct'],
  ['implied', 'Implied move', 'pct'], ['avg_move', 'Avg move', 'pct'], ['r1m', '1 mo', 'pct'], ['r3m', '3 mo', 'pct'], ['r1y', '12 mo', 'pct'], ['from_high', 'From high', 'pct'], ['above_ma200', '>200d', 'flag'],
  ['f13_net', '13F net', 'usd'], ['f13_buyers', '13F buyers', 'num'], ['f13_sellers', '13F sellers', 'num'], ['heat', 'Heat', 'num'], ['ins_buys', 'Ins. buys', 'num'], ['ins_buy_usd', 'Ins. bought', 'usd'],
  ['ins_sells', 'Ins. sales', 'num'], ['ins_sell_usd', 'Ins. sold', 'usd'], ['short_dtc', 'Days to cover', 'num'], ['short_chg', 'SI change', 'pts'], ['cash', 'Cash', 'usd'], ['debt', 'Debt', 'usd'],
  ['net_cash', 'Net cash', 'usd'], ['fcf_ttm', 'FCF 12m', 'usd'], ['runway_months', 'Runway', 'months']];
const SC_DEFAULT_COLS = ['mcap', 'growth', 'om', 'fcf_y', 'qscore', 'report_date', 'r3m', 'f13_net', 'ins_buys', 'net_cash'];
const SC_SECTORS = [['', 'Any sector'], ['technology', 'Technology'], ['communication', 'Communication'], ['consumer-disc', 'Consumer discretionary'], ['consumer-staples', 'Consumer staples'], ['health', 'Health care'],
  ['financials', 'Financials'], ['real-estate', 'Real estate'], ['energy', 'Energy'], ['materials', 'Materials'], ['industrials', 'Industrials'], ['utilities', 'Utilities']];
const scUsd = v => v == null || !Number.isFinite(+v) ? '—' : (v < 0 ? '−' : '') + '$' + compact(Math.abs(v));
const scSigned = (v, d = 1) => v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), d);
function scCell(kind, v) {
  if (v == null) return '—';
  if (kind === 'usd') return scUsd(v);
  if (kind === 'pct') return `<span class="${v > 0 ? 'positive' : v < 0 ? 'negative' : ''}">${scSigned(100 * v)}%</span>`;
  if (kind === 'pts') return `<span class="${v > 0 ? 'positive' : v < 0 ? 'negative' : ''}">${scSigned(v)}%</span>`;
  if (kind === 'flag') return v ? '✓' : '';
  if (kind === 'date') return esc(String(v));
  if (kind === 'months') return v >= 24 ? fmt(v / 12, 1) + ' yrs' : fmt(v, 0) + ' mo';
  if (kind === 'num') return typeof v === 'number' && !Number.isInteger(v) ? fmt(v, 2) : fmt(v);
  return esc(String(v));
}
function scPasses(r, f) {
  const today = new Date().toISOString().slice(0, 10);
  if (f.sector && r.sector !== f.sector) return false;
  if (f.q) { const q = f.q.toUpperCase(); if (!String(r.ticker).includes(q) && !String(r.name || '').toUpperCase().includes(q) && !String(r.industry || '').toUpperCase().includes(q)) return false; }
  if (f.ma === 'above' && r.above_ma200 !== true) return false;
  if (f.ma === 'below' && r.above_ma200 !== false) return false;
  if (f.grade && (r.qgrade == null || r.qgrade > f.grade)) return false;
  if (f.zone && r.z_zone !== f.zone) return false;
  if (f.tag && !(r.tags || []).includes(f.tag)) return false;
  for (const [key, , kind, field, unit] of SC_FILTERS) {
    const raw = f[key];
    if (raw === '' || raw == null) continue;
    const x = +raw;
    if (!Number.isFinite(x)) continue;
    let v = r[field];
    if (kind === 'days') { if (!v) return false; const d = (Date.parse(v) - Date.parse(today)) / 864e5; if (d < 0 || d > x) return false; continue; }
    if (v == null) return false;
    const th = unit === 'pct' ? x / 100 : unit === 'B' ? x * 1e9 : unit === 'M' ? x * 1e6 : x;
    if (kind === 'min' && !(v >= th)) return false;
    if (kind === 'max' && !(v <= th)) return false;
  }
  return true;
}
function scApplyPreset(D, key) {
  const p = (D.presets || []).find(x => x.key === key);
  if (!p) return;
  state.scf = {}; state.scPreset = key; state.scSort = p.sort; state.scDir = p.dir; state.scCols = p.cols.filter(c => SC_COLS.some(x => x[0] === c));
  state.scOnly = new Set(p.tickers);
}
function screenerView() {
  const m = scData();
  const f = state.scf || (state.scf = {});
  let out = `<div class="section-head"><h2>Screener</h2><span class="tag">XBRL · 13F · Form 4 · FINRA · daily closes</span></div>
    <p class="sub">Every listed company the site covers in one table: growth, margins, cash flow and yields, the Piotroski, Altman and Beneish scores, the earnings quality score, the next report, 13F and insider flows, short interest, cash, debt and runway. Set any thresholds; sort by any column; export the rows.</p>`;
  if (m.err) return out + empty(`The screener data could not load (${m.err}). It is rebuilt with the site (scripts/screener.py).`);
  if (!m.data) return out + empty('Loading the screener…');
  const D = m.data;
  const presets = [['', 'Custom screen'], ...(D.presets || []).map(p => [p.key, `${p.title} (${p.tickers.length})`])];
  out += `<div class="toolbar">${field('scpreset', 'Preset screen', presets, state.scPreset || '')}${field('scsector', 'Sector', SC_SECTORS, f.sector || '')}
    <div class="field"><label for="scq">Ticker, name or industry</label><input id="scq" value="${esc(f.q || '')}" placeholder="e.g. NVDA, semiconductors"></div>
    ${field('scma', '200-day average', [['', 'Either side'], ['above', 'Above'], ['below', 'Below']], f.ma || '')}
    ${field('scgrade', 'Quality grade at least', [['', 'Any'], ['A', 'A'], ['B', 'B'], ['C', 'C'], ['D', 'D']], f.grade || '')}
    ${field('sczone', 'Altman zone', [['', 'Any'], ['safe', 'Safe'], ['grey', 'Grey'], ['distress', 'Distress']], f.zone || '')}
    ${field('sctag', 'Signal tag', [['', 'Any'], ...Object.keys(D.list.reduce((a, r) => { (r.tags || []).forEach(t => a[t] = 1); return a; }, {})).sort().map(t => [t, t.replace(/_/g, ' ')])], f.tag || '')}
    <details class="field wide"><summary>Thresholds (${SC_FILTERS.filter(x => f[x[0]] !== undefined && f[x[0]] !== '').length} set)</summary><div class="sc-grid">
    ${SC_FILTERS.map(([k, label]) => `<label class="sc-th">${esc(label)}<input type="number" step="any" data-scf="${k}" value="${esc(f[k] == null ? '' : String(f[k]))}"></label>`).join('')}</div></details>
    <details class="field wide"><summary>Columns (${(state.scCols || SC_DEFAULT_COLS).length})</summary><div class="sc-grid">
    ${SC_COLS.map(([k, label]) => `<label class="sc-col"><input type="checkbox" data-sccol="${k}" ${(state.scCols || SC_DEFAULT_COLS).includes(k) ? 'checked' : ''}> ${esc(label)}</label>`).join('')}</div></details></div>`;
  const cols = (state.scCols || SC_DEFAULT_COLS).map(k => SC_COLS.find(c => c[0] === k)).filter(Boolean);
  let L = D.list.filter(r => scPasses(r, f));
  if (state.scPreset && state.scOnly) L = L.filter(r => state.scOnly.has(r.ticker));
  const sk = state.scSort || 'mcap', dir = state.scDir || -1;
  L.sort((a, b) => { const x = a[sk], y = b[sk]; if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (typeof x === 'string' ? x.localeCompare(y) : x - y) * dir; });
  exported = L.map(r => { const o = { ...r }; o.tags = (r.tags || []).join(' '); delete o.slug; return o; });
  const p = state.scPreset && (D.presets || []).find(x => x.key === state.scPreset);
  out += `<div class="section-head"><div><h3>${p ? esc(p.title) : 'Companies that pass'} <span class="tag">${fmt(L.length)} of ${fmt(D.list.length)}</span></h3>${p ? `<p class="sub">${esc(p.line)}</p>` : ''}</div><button class="action" id="csv">Export CSV ↓</button></div>`;
  const th = (k, label) => `<th><button class="text-button sc-sort" data-scs="${k}">${esc(label)}${sk === k ? (dir < 0 ? ' ↓' : ' ↑') : ''}</button></th>`;
  out += `<div class="tablebox"><table><thead><tr><th>#</th>${th('ticker', 'Company')}${cols.map(c => th(c[0], c[1])).join('')}</tr></thead><tbody>
    ${L.slice(0, state.scShow || 150).map((r, i) => `<tr><td>${i + 1}</td><td><a href="../#c-${esc(r.cik)}"><b>${esc(r.ticker)}</b></a><br><span class="sub">${esc(r.name || '')}${r.label ? ' · ' + esc(r.label) : ''}</span></td>
      ${cols.map(c => `<td class="num">${scCell(c[2], r[c[0]])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  if (L.length > (state.scShow || 150)) out += `<p><button class="action" id="scmore">Show ${Math.min(L.length, (state.scShow || 150) + 300)} of ${fmt(L.length)}</button></p>`;
  out += `<div class="explain">${esc(D.note || '')} Built ${esc(D.generated_at || '')}. Thresholds in percent are of the latest fiscal year (growth, margins, yields) or the latest quarter (revenue Y/Y, operating margin); returns and the distance from the 52-week high are from daily closes. A blank cell means the file has no figure, and a company with a blank fails that threshold.</div>`;
  return out;
}
function bindScreener() {
  if (state.tab !== 'screener') return;
  const D = (scData().data || {});
  const re = () => { state.scShow = 150; render(); };
  if ($('scpreset')) $('scpreset').onchange = e => { if (e.target.value) scApplyPreset(D, e.target.value); else { state.scPreset = ''; state.scOnly = null; } try { history.replaceState(null, '', '#screener' + (e.target.value ? '/' + e.target.value : '')) } catch (x) {} re(); };
  const set = (id, key) => { if ($(id)) $(id).onchange = e => { state.scf[key] = e.target.value; state.scPreset = ''; state.scOnly = null; re(); }; };
  set('scsector', 'sector'); set('scq', 'q'); set('scma', 'ma'); set('scgrade', 'grade'); set('sczone', 'zone'); set('sctag', 'tag');
  document.querySelectorAll('#workspace [data-scf]').forEach(i => i.onchange = e => { state.scf[e.target.dataset.scf] = e.target.value; state.scPreset = ''; state.scOnly = null; re(); });
  document.querySelectorAll('#workspace [data-sccol]').forEach(i => i.onchange = e => { const k = e.target.dataset.sccol, cs = new Set(state.scCols || SC_DEFAULT_COLS); if (e.target.checked) cs.add(k); else cs.delete(k); state.scCols = SC_COLS.map(c => c[0]).filter(c => cs.has(c)); render(); });
  document.querySelectorAll('#workspace [data-scs]').forEach(b => b.onclick = () => { const k = b.dataset.scs; if (state.scSort === k) state.scDir = -(state.scDir || -1); else { state.scSort = k; state.scDir = k === 'ticker' || k === 'report_date' || k === 'runway_months' ? 1 : -1; } render(); });
  if ($('scmore')) $('scmore').onclick = () => { state.scShow = (state.scShow || 150) + 300; render(); };
  if ($('csv')) $('csv').onclick = downloadCSV;
}
function screenerDeepLink(arg) {
  const key = decodeURIComponent(arg || '').trim();
  const m = scData();
  if (m.data) scApplyPreset(m.data, key); else scStore.pending = key;
}
function screenerNotice() {
  const m = scData(), d = m.data;
  if (m.err) return { stale: true, text: 'Official derived view · Screener unavailable · ' + m.err };
  if (!d) return { stale: false, text: 'Official derived view · Screener loading…' };
  const age = (Date.now() - Date.parse(d.generated_at)) / 3600000;
  return { stale: !(age <= 48), text: `Official derived view · Screener built ${d.generated_at} · ${fmt(d.list.length)} companies · rebuilt with the site` + (age > 48 ? ' · stale' : '') };
}
window.HUB_NOTICES = Object.assign(window.HUB_NOTICES || {}, { screener: screenerNotice });
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { screener: screenerView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { screener: bindScreener });
