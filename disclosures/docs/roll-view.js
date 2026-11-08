/* Balance sheet roll-forward — two balance sheets and the flows between them (pipeline/rollforward.py, quality.roll).
   One row per account: the opening balance, the income-statement and cash-flow lines that explain the change, what
   they do not explain (the residual, hatched), the closing balance — all on one dollar scale, so a residual is as
   visible as a flow. Quarter on quarter (one quarter's flows, observed) or year on year (the same quarter end a year
   earlier, four quarters' flows added, derived). Click an account for its own bridge; the matrix shows which statement
   line explains which account. Shared by the company page ("Balance sheet roll-forward") and the Disclosure Hub.
   window.RollView.render(el, {cik, ticker, company, here, hub, site}) */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const big = (v) => { if (!fin(v)) return '—'; if (+v === 0) return '$0'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? '$' + (a / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(0) + 'M' : '$' + (a / 1e3).toFixed(0) + 'K'); };
  const sgn = (v) => (v > 0 ? '+' : '') + big(v);
  const SIDE = { a: 'Assets', l: 'Liabilities', e: 'Equity' };
  // one colour per statement, not per direction: the sign is in the label and the position
  const COL = { p: 'var(--mk-profit,#2e8b57)', bridge: 'var(--accent,#2a78d6)', cap: 'var(--q-warm,#d9822b)', sec: 'var(--q-warm,#d9822b)', res: 'var(--muted,#8a8a8a)' };
  const KIND = { ni: 'p', ocf: 'p', inv: 'sec', fin: 'sec', fx: 'cap', capex: 'cap', realestate: 'cap', inv_other: 'cap', sales: 'cap', acq: 'cap', borrow: 'cap', buyback: 'cap', div: 'cap', withhold: 'cap', stock: 'cap', nci: 'cap' };
  const kindOf = (k) => KIND[k] || 'bridge';
  const KIND_NAME = { p: 'income statement / operating cash flow', bridge: 'net income → OCF bridge (cash flow statement)', cap: 'investing and financing sections', sec: 'cash flow statement sections', res: 'not explained by the statements' };
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.rv{font-size:14px}.rv h3{margin:18px 0 6px;font-size:16px}.rv .muted{color:var(--muted,#777)}.rv .sm{font-size:12.5px}
.rv .rv-bar{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin:6px 0 10px}.rv select,.rv button{font:inherit;font-size:13px;padding:4px 8px;border:1px solid var(--line,#ddd);border-radius:8px;background:var(--surface,transparent);color:inherit}
.rv button.on{border-color:var(--accent,#2a78d6);color:var(--accent,#2a78d6)}
.rv svg{display:block;width:100%;height:auto;overflow:visible}.rv svg text{font-size:11px;fill:var(--ink,#222)}.rv svg text.mu{fill:var(--muted,#777)}
.rv .rv-row:hover rect.bg{fill:var(--line,#eee);fill-opacity:.5}.rv .rv-row{cursor:pointer}
.rv table{border-collapse:collapse;width:100%;font-size:13px}.rv td,.rv th{padding:4px 6px;border-bottom:1px solid var(--line,#eee);text-align:left;vertical-align:top}.rv td.n,.rv th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rv .rv-wrap{overflow-x:auto}.rv .rv-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0}.rv .rv-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle}
.rv .rv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 14px;margin:8px 0;background:var(--surface,transparent);overflow-wrap:anywhere}
.rv details summary{cursor:pointer;color:var(--accent,#2a78d6)}`;
    document.head.appendChild(s);
  }
  const hatch = (id) => `<defs><pattern id="${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--surface,#fff)"/><line x1="0" y1="0" x2="0" y2="6" stroke="${COL.res}" stroke-width="2"/></pattern></defs>`;
  /* the strip chart: open | flows and residual | close, one scale */
  function strip(p) {
    const A = p.accounts, W = 860, L = 170, R = 70, rowH = 30, top = 26, H = top + A.length * rowH + 28;
    const maxBal = Math.max(...A.map((a) => Math.max(Math.abs(a.open), Math.abs(a.close))), 1);
    // the movement scale: the largest one-sided stack of any account but cash and equity, whose gross flows (operating in,
    // financing out; net income in, buybacks out) dwarf every other row; their bars are clipped at the edge and marked »
    const oneSide = (a) => { let pos = 0, neg = 0; a.flows.concat([[null, null, a.residual]]).forEach((f) => { if (f[2] >= 0) pos += f[2]; else neg -= f[2]; }); return Math.max(pos, neg, Math.abs(a.delta)); };
    const maxMove = Math.max(...A.filter((a) => a.k !== 'cash' && a.k !== 'eq').map(oneSide), 1);
    // left: the balances on their scale (two thin bars, open above close); right: the movement on its own scale
    const balW = 150, moveX = L + balW + 24, moveW = W - moveX - R, zero = moveX + moveW * (maxMove / (2 * maxMove));
    const sx = (v) => zero + (v / maxMove) * (moveW / 2);
    let o = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Balance sheet roll-forward" style="min-width:720px">${hatch('rv-h')}`;
    o += `<text x="${L}" y="12" class="mu">Balance ${esc(p.start)} (upper) · ${esc(p.end)} (lower)</text><text x="${W - R - 4}" y="12" text-anchor="end" class="mu">Change and what explains it</text>`;
    o += `<line x1="${zero}" x2="${zero}" y1="${top - 6}" y2="${H - 24}" stroke="var(--line,#ccc)"/>`;
    let side = '';
    A.forEach((a, i) => {
      const y = top + i * rowH;
      o += `<g class="rv-row" data-k="${esc(a.k)}"><rect class="bg" x="0" y="${y}" width="${W}" height="${rowH}" fill="transparent"/>`;
      if (a.side !== side) { side = a.side; o += `<text x="2" y="${y + 19}" class="mu" font-weight="600">${esc(SIDE[side])}</text>`; }
      o += `<text x="${L - 6}" y="${y + 19}" text-anchor="end">${esc(a.name)}</text>`;
      const bo = Math.abs(a.open) / maxBal * balW, bc = Math.abs(a.close) / maxBal * balW;
      o += `<rect x="${L}" y="${y + 6}" width="${Math.max(1, bo)}" height="8" fill="var(--ink,#444)" fill-opacity=".35"><title>Open ${esc(big(a.open))}</title></rect>`;
      o += `<rect x="${L}" y="${y + 16}" width="${Math.max(1, bc)}" height="8" fill="var(--ink,#444)" fill-opacity=".75"><title>Close ${esc(big(a.close))}</title></rect>`;
      // the movement: flows stacked from zero in their direction, the residual last, the actual change as a tick
      let pos = 0, neg = 0;
      const segs = a.flows.map((f) => ({ k: f[0], lab: f[1], v: f[2], kind: kindOf(f[0]) })).concat(Math.abs(a.residual) >= 0.5 ? [{ k: 'residual', lab: 'Not explained', v: a.residual, kind: 'res' }] : []);
      segs.forEach((s) => {
        let x0, x1;
        if (s.v >= 0) { x0 = sx(pos); pos += s.v; x1 = sx(pos); } else { x1 = sx(neg); neg += s.v; x0 = sx(neg); }
        const lo = moveX, hi = moveX + moveW, cx0 = Math.max(lo, Math.min(hi, x0)), cx1 = Math.max(lo, Math.min(hi, x1));
        if (cx1 > cx0 || (x0 >= lo && x0 <= hi)) o += `<rect x="${cx0}" y="${y + 7}" width="${Math.max(0.5, cx1 - cx0)}" height="16" fill="${s.kind === 'res' ? 'url(#rv-h)' : COL[s.kind]}" ${s.kind === 'res' ? `stroke="${COL.res}" stroke-width=".8"` : ''}><title>${esc(s.lab)}: ${esc(sgn(s.v))}</title></rect>`;
        if (x1 > hi) o += `<text x="${hi + 2}" y="${y + 19}" class="mu">»</text>`;
        if (x0 < lo) o += `<text x="${lo - 10}" y="${y + 19}" class="mu">«</text>`;
      });
      const xd = Math.max(moveX, Math.min(moveX + moveW, sx(a.delta)));
      o += `<line x1="${xd}" x2="${xd}" y1="${y + 3}" y2="${y + 27}" stroke="var(--ink,#222)" stroke-width="2"><title>Change ${esc(sgn(a.delta))}</title></line>`;
      o += `<text x="${W - R + 6}" y="${y + 19}" class="${Math.abs(a.residual) > Math.abs(a.delta) * 0.5 && Math.abs(a.residual) > maxMove * 0.02 ? '' : 'mu'}">${esc(sgn(a.delta))}</text></g>`;
    });
    o += `<text x="${moveX}" y="${H - 8}" class="mu">← decreases · increases →   bars: statement lines; hatched: residual; tick: the change in the balance</text></svg>`;
    return o;
  }
  /* one account's bridge: open → each flow → residual → close */
  function bridge(a, p) {
    const steps = [['Opening balance', a.open, 'total']].concat(a.flows.map((f) => [f[1], f[2], kindOf(f[0])]), [['Not explained by the statements', a.residual, 'res'], ['Closing balance', a.close, 'total']]);
    const W = 560, H = 230, L = 10, T = 20, w = (W - 2 * L) / steps.length;
    const run = []; let r = 0; steps.forEach((s) => { if (s[2] === 'total') { run.push([0, s[1]]); r = s[1]; } else { run.push([r, r + s[1]]); r += s[1]; } });
    const lo = Math.min(0, ...run.flat()), hi = Math.max(0, ...run.flat()) || 1, sy = (v) => T + (hi - v) / (hi - lo) * (H - T - 56);
    let o = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(a.name)} bridge">${hatch('rv-h2')}`;
    steps.forEach((s, i) => {
      const [y0, y1] = run[i], x = L + i * w + 6, bw = w - 12, topY = Math.min(sy(y0), sy(y1)), h = Math.max(2, Math.abs(sy(y0) - sy(y1)));
      const fill = s[2] === 'total' ? 'var(--ink,#444)' : s[2] === 'res' ? 'url(#rv-h2)' : COL[s[2]];
      o += `<rect x="${x}" y="${topY}" width="${bw}" height="${h}" fill="${fill}" ${s[2] === 'res' ? `stroke="${COL.res}"` : ''} fill-opacity="${s[2] === 'total' ? .8 : .9}"><title>${esc(s[0])}: ${esc(s[2] === 'total' ? big(s[1]) : sgn(s[1]))}</title></rect>`;
      o += `<text x="${x + bw / 2}" y="${topY - 4}" text-anchor="middle">${esc(s[2] === 'total' ? big(s[1]) : sgn(s[1]))}</text>`;
      const lab = s[0].replace(/ \(cash flow statement\)/, '').replace('Not explained by the statements', 'Not explained'); const lb = lab.length > 24 ? lab.slice(0, 23) + '…' : lab;
      o += `<text x="${x + bw / 2}" y="${H - 36}" text-anchor="middle" class="mu" transform="rotate(-18 ${x + bw / 2} ${H - 36})">${esc(lb)}</text>`;
    });
    o += `<line x1="${L}" x2="${W - L}" y1="${sy(0)}" y2="${sy(0)}" stroke="var(--line,#ccc)"/></svg>`;
    const check = `${big(a.open)} ${a.flows.map((f) => (f[2] >= 0 ? '+ ' : '− ') + big(Math.abs(f[2]))).join(' ')} ${a.residual >= 0 ? '+' : '−'} ${big(Math.abs(a.residual))} = ${big(a.close)}`;
    return `<div class="rv-card"><p><b>${esc(a.name)}</b> <span class="muted sm">${esc(p.label)} · tags: ${esc((a.tags || []).join(', ') || 'derived from the totals (what the tagged lines leave)')}</span></p>${o}<p class="muted sm">Check: ${esc(check)}.${a.note ? ' ' + esc(a.note) : ''}</p></div>`;
  }
  /* the articulation matrix: accounts × statement lines */
  function matrix(p) {
    const cols = [];
    p.accounts.forEach((a) => a.flows.forEach((f) => { if (!cols.some((c) => c[0] === f[0])) cols.push([f[0], f[1]]); }));
    let h = '<div class="rv-wrap"><table><thead><tr><th>Account</th><th class="n">Change</th>' + cols.map((c) => `<th class="n" title="${esc(c[1])}">${esc(c[0])}</th>`).join('') + '<th class="n">Residual</th></tr></thead><tbody>';
    p.accounts.forEach((a) => {
      const m = Object.fromEntries(a.flows.map((f) => [f[0], f[2]]));
      h += `<tr><td>${esc(a.name)}</td><td class="n"><b>${esc(sgn(a.delta))}</b></td>` + cols.map((c) => `<td class="n">${c[0] in m ? esc(sgn(m[c[0]])) : '<span class="muted">·</span>'}</td>`).join('') + `<td class="n">${esc(sgn(a.residual))}</td></tr>`;
    });
    return h + '</tbody></table></div><p class="muted sm">Columns are the cash-flow statement\'s lines (keys as in the data); a line that explains two accounts appears under both. Hover a key for its name.</p>';
  }
  async function render(el, opt) {
    css();
    const site = opt.site != null ? opt.site : (opt.hub ? '' : '../');
    const here = () => el.isConnected && (typeof opt.here !== 'function' || opt.here());
    let c = opt.company;
    if (!c) {
      el.innerHTML = '<p class="muted">Reading the balance sheets…</p>';
      try { c = await fetch(`${site}data/c/${encodeURIComponent(opt.cik)}.json`, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }); } catch (e) { if (here()) el.innerHTML = `<div class="rv"><p class="muted">${esc(e.message)}</p></div>`; return; }
    }
    if (!here()) return;
    const roll = (c.quality || {}).roll;
    if (!roll || (!(roll.q || []).length && !(roll.y || []).length)) { el.innerHTML = '<div class="rv"><p class="muted">No balance-sheet roll-forward for this company yet: it needs total assets, liabilities and equity tagged at two quarter ends, and the quarter\'s cash flow lines. It is built with the next scan of the filings.</p></div>'; return; }
    const state = { mode: (roll.q || []).length ? 'q' : 'y', i: -1, open: null };
    const draw = () => {
      const list = roll[state.mode] || [];
      if (!list.length) { state.mode = state.mode === 'q' ? 'y' : 'q'; }
      const L2 = roll[state.mode] || [];
      const idx = state.i < 0 ? L2.length - 1 : Math.min(state.i, L2.length - 1);
      const p = L2[idx];
      const share = fin(p.explained_share) ? Math.round(100 * p.explained_share) + '%' : '—';
      const t = p.totals;
      el.innerHTML = `<div class="rv"><h3>Balance sheet roll-forward: ${esc(p.start)} → ${esc(p.end)}</h3>
<p class="muted">Each account's change, and the income-statement and cash-flow lines that explain it. ${state.mode === 'q' ? 'One quarter\'s flows, as the filing reports them (observed).' : 'The same quarter end a year earlier; four quarters\' flows added (' + esc((p.quarters || []).join(', ')) + '), so derived.'} What the lines do not explain is drawn hatched, never spread over the others.</p>
<div class="rv-bar"><span><button data-m="q" class="${state.mode === 'q' ? 'on' : ''}" ${(roll.q || []).length ? '' : 'disabled'}>Quarter on quarter</button> <button data-m="y" class="${state.mode === 'y' ? 'on' : ''}" ${(roll.y || []).length ? '' : 'disabled'}>Year on year</button></span>
<label>Period <select id="rv-p">${L2.map((x, j) => `<option value="${j}" ${j === idx ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select></label>
<span class="muted sm">Total assets ${esc(big(t.assets_open))} → ${esc(big(t.assets_close))} · liabilities ${esc(big(t.liab_open))} → ${esc(big(t.liab_close))} · equity ${esc(big(t.eq_open))} → ${esc(big(t.eq_close))} · ${share} of the movement explained by the statements${Math.abs(p.identity_gap || 0) > 1e6 ? ' · assets − liabilities − equity = ' + esc(big(p.identity_gap)) + ' (temporary equity or rounding)' : ''}</span></div>
<div class="rv-legend"><span><i style="background:${COL.p}"></i>${esc(KIND_NAME.p)}</span><span><i style="background:${COL.bridge}"></i>${esc(KIND_NAME.bridge)}</span><span><i style="background:${COL.cap}"></i>${esc(KIND_NAME.cap)}</span><span><i style="background:repeating-linear-gradient(45deg,${COL.res} 0 2px,transparent 2px 5px)"></i>${esc(KIND_NAME.res)}</span></div>
<div class="rv-wrap">${strip(p)}</div>
<p class="muted sm">Click an account for its bridge. Balances are the standard tags at each date, the same tag at both dates (a line tagged at one date only falls into "other"); "other assets" and "other liabilities" are what the tagged lines leave of the totals, so the totals always match the filing.</p>
<div id="rv-bridge">${bridge(p.accounts.find((a) => a.k === state.open) || p.accounts.reduce((m, a) => (Math.abs(a.delta) > Math.abs(m.delta) ? a : m), p.accounts[0]), p)}</div>
<details><summary>The matrix: which statement line explains which account</summary>${matrix(p)}</details>
<p class="muted sm">How to read a residual: in receivables or payables it is usually acquisitions, currency or a reclassification between lines; in PP&E the amortisation of intangibles inside one D&A line; in equity other comprehensive income; in investments the securities bought and sold inside "other investing". A large residual is a question for the notes, not a finding. Not investment advice.</p></div>`;
      el.querySelectorAll('button[data-m]').forEach((b) => { b.onclick = () => { state.mode = b.dataset.m; state.i = -1; state.open = null; draw(); }; });
      el.querySelector('#rv-p').onchange = (e) => { state.i = +e.target.value; draw(); };
      el.querySelectorAll('.rv-row').forEach((g) => { g.onclick = () => { state.open = g.dataset.k; el.querySelector('#rv-bridge').innerHTML = bridge(p.accounts.find((a) => a.k === state.open), p); }; });
    };
    draw();
  }
  window.RollView = { render, strip, bridge, matrix };
})();
