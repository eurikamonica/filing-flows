/* Workforce — every company's headcount from its 10-Ks: revenue and net income per employee against its industry, hiring
   and layoffs year on year. One company: WorkforceView (workforce-view.js).
   Data: data/research/employees/{index,status}.json (app/employees.py, branch research-employees).
   Deep links: #workforce/<view> (all, layoffs, hiring, efficient, leaner), #workforce/<TICKER>. */
const wfStore = {};
function wfData(name) {
  const m = wfStore[name] || (wfStore[name] = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/research/employees/' + name + '.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(d => { m.data = d; render() }).catch(e => { m.err = e.message; render() });
  return m;
}
const WF_VIEWS = [['all', 'Every company'], ['layoffs', 'Fewest people vs a year ago'], ['hiring', 'Most hiring'], ['efficient', 'Highest revenue per employee'],
  ['profit', 'Highest net income per employee'], ['leaner', 'Fewer people, more revenue']];
const wfBig = v => v == null || !Number.isFinite(+v) ? '—' : (v < 0 ? '−' : '') + '$' + compact(Math.abs(v));
const wfPct = v => v == null || !Number.isFinite(+v) ? '—' : `<span class="${v > 0 ? 'positive' : v < 0 ? 'negative' : ''}">${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(100 * v).toFixed(1)}%</span>`;
function workforceView() {
  const m = wfData('index');
  state.wfv = WF_VIEWS.some(v => v[0] === state.wfv) ? state.wfv : 'all';
  let out = `<div class="section-head"><h3>Workforce</h3></div><div class="toolbar">${field('wfv', 'Show', WF_VIEWS, state.wfv)}<div class="field"><label for="wfq">Ticker or name</label><input id="wfq" value="${esc(state.wfq || '')}" placeholder="e.g. AMZN · Enter"></div></div>`;
  if (m.err) return out + empty(`The workforce research could not load (${m.err}). It is rebuilt daily by the research-employees workflow.`);
  if (!m.data) return out + empty('Loading the workforce research…');
  const F = m.data.fields, rows = (m.data.rows || []).map(r => { const o = {}; F.forEach((k, i) => o[k] = r[i]); return o });
  const q = (state.wfq || '').trim().toUpperCase();
  if (state.wfone) return out + `<div id="wf-one"></div>`;
  let L = rows.filter(r => !q || String(r.ticker || '').includes(q) || String(r.name || '').toUpperCase().includes(q));
  const v = state.wfv, has = k => r => r[k] != null;
  if (v === 'layoffs') L = L.filter(has('change')).sort((a, b) => a.change - b.change);
  else if (v === 'hiring') L = L.filter(has('change')).sort((a, b) => b.change - a.change);
  else if (v === 'efficient') L = L.filter(has('rev_emp')).sort((a, b) => b.rev_emp - a.rev_emp);
  else if (v === 'profit') L = L.filter(has('ni_emp')).sort((a, b) => b.ni_emp - a.ni_emp);
  else if (v === 'leaner') L = L.filter(r => (r.change || 0) < 0 && (r.rev_growth || 0) > 0).sort((a, b) => (b.rev_growth - b.change) - (a.rev_growth - a.change));
  exported = L;
  const tot = rows.reduce((a, r) => a + (r.employees || 0), 0), ch = rows.filter(r => r.change != null);
  const page = state.page || 0, per = 50, slice = L.slice(page * per, page * per + per);
  out += `<div class="metrics">${kpi('Companies', fmt(rows.length), 'with a headcount read from a 10-K')}${kpi('People employed', compact(tot), 'as the latest 10-Ks state it')}
    ${kpi('Grew their workforce', ch.length ? Math.round(100 * ch.filter(r => r.change > 0).length / ch.length) + '%' : '—', `of ${fmt(ch.length)} with two years`)}${kpi('Cut it 5%+', fmt(ch.filter(r => r.change <= -0.05).length), 'companies')}</div>`;
  out += `<div class="explain">${esc(m.data.note || '')} Percentile: where the company's revenue per employee sits among its peers. Click a ticker for its years, its own sentences and its peers.</div>`;
  out += `<div class="tablebox"><table><thead><tr><th>Company</th><th>Employees</th><th>As of</th><th>Change</th><th>Revenue growth</th><th>Revenue / person</th><th>Peer pct.</th><th>Net income / person</th><th>Peers</th></tr></thead><tbody>
    ${slice.map(r => `<tr><td><button class="text-button" data-wft="${esc(r.cik)}"><b>${esc(r.ticker || '')}</b></button><br><span class="sub">${esc(r.name || '')}</span></td><td>${fmt(r.employees)}</td><td>${esc(r.as_of || '')}</td>
      <td>${wfPct(r.change)}${r.change_n != null ? `<br><span class="sub">${r.change_n >= 0 ? '+' : '−'}${fmt(Math.abs(r.change_n))}</span>` : ''}</td><td>${wfPct(r.rev_growth)}</td><td>${wfBig(r.rev_emp)}</td>
      <td>${r.rev_emp_pct == null ? '—' : Math.min(99, Math.max(1, Math.round(100 * r.rev_emp_pct)))}</td><td>${wfBig(r.ni_emp)}</td><td class="sub">${esc(r.peer_group || '')}</td></tr>`).join('')}</tbody></table></div>
    <div class="pager"><span>${fmt(L.length)} companies · page ${page + 1} of ${Math.max(1, Math.ceil(L.length / per))}</span><button class="action" data-wfpage="-1" ${page ? '' : 'disabled'}>Previous</button><button class="action" data-wfpage="1" ${(page + 1) * per < L.length ? '' : 'disabled'}>Next</button></div>`;
  return out;
}
function bindWorkforce() {
  if (state.tab !== 'workforce') return;
  if ($('wfv')) $('wfv').onchange = e => { state.wfv = e.target.value; state.wfone = ''; state.page = 0; render() };
  if ($('wfq')) $('wfq').onchange = e => { state.wfq = e.target.value; state.wfone = ''; state.page = 0; render() };
  document.querySelectorAll('#workspace [data-wfpage]').forEach(b => b.onclick = () => { state.page = Math.max(0, (state.page || 0) + +b.dataset.wfpage); render() });
  document.querySelectorAll('#workspace [data-wft]').forEach(b => b.onclick = () => { state.wfone = b.dataset.wft; render() });
  const one = $('wf-one');
  if (one && window.WorkforceView) {
    const back = document.createElement('button'); back.className = 'action'; back.textContent = '← Every company';
    back.onclick = () => { state.wfone = ''; render() };
    one.before(back);
    window.WorkforceView.render(one, { cik: state.wfone, hub: '' });
  }
}
function workforceDeepLink(arg) {
  const v = decodeURIComponent(arg || '').trim();
  if (WF_VIEWS.some(x => x[0] === v)) { state.wfv = v; state.wfone = ''; return; }
  const m = wfData('index');
  if (/^\d+$/.test(v)) { state.wfone = v; return; }
  state.wfq = v.toUpperCase(); state.wfone = '';
  if (m.data) { const F = m.data.fields, i = F.indexOf('ticker'), c = F.indexOf('cik'), r = (m.data.rows || []).find(x => x[i] === v.toUpperCase()); if (r) state.wfone = String(r[c]); }
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { workforce: workforceView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { workforce: bindWorkforce });
