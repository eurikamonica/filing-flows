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

  /* ---- in words: the three largest movements, each with what explains it (also the X card's text) ---- */
  const SHORT = { ni: 'net income', sbc: 'stock compensation', buyback: 'buybacks', div: 'dividends', withhold: 'shares withheld', stock: 'shares issued', nci: 'minority flows',
    ocf: 'operating cash flow', inv: 'investing', fin: 'financing', fx: 'currency', capex: 'capex', realestate: 'real estate', da: 'D&A', inv_other: 'securities and other investing', sales: 'asset sales',
    acq: 'acquisitions', impair: 'impairments', gain_inv: 'investment gains', borrow: 'net borrowing', d_ar: 'the receivables line', d_orec: 'other receivables', d_casset: 'contract assets', d_inv: 'the inventories line',
    d_ap: 'the payables line', d_accr: 'accrued liabilities', d_emp: 'employee liabilities', d_contract: 'deferred revenue', d_oliab: 'other liabilities', d_tax: 'taxes payable', d_onet: 'other operating capital', d_oassets: 'prepaid and other', dtax: 'deferred taxes' };
  function words(p, n) {
    const top = p.accounts.slice().sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).filter((a) => Math.abs(a.delta) >= 1e6).slice(0, n || 3);
    return top.map((a) => {
      const fl = a.flows.slice().sort((x, y) => Math.abs(y[2]) - Math.abs(x[2])).slice(0, 3).map((f) => `${sgn(f[2])} ${SHORT[f[0]] || f[1].toLowerCase()}`);
      const res = Math.abs(a.residual) >= Math.max(1e6, Math.abs(a.delta) * 0.05) ? `${sgn(a.residual)} not explained by the statements` : '';
      const parts = fl.concat(res ? [res] : []);
      return { k: a.k, text: `${a.name} ${a.delta >= 0 ? 'up' : 'down'} ${big(Math.abs(a.delta))}` + (parts.length ? ': ' + parts.join(', ') : ': no statement line maps to it') + '.' };
    });
  }
  const wrapText = (t, n) => { const out = []; let line = ''; String(t).split(' ').forEach((w) => { if ((line + ' ' + w).trim().length > n) { out.push(line.trim()); line = w; } else line += ' ' + w; }); if (line.trim()) out.push(line.trim()); return out; };
  /* ---- the X card: 1200×675, the six largest movements as bars and the words beside them ---- */
  function card(p, meta) {
    const W = 1200, H = 675, L = 40, top = 118, rows = p.accounts.slice().sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 6);
    const barX = 250, barW = 400, rowH = 62, zero = barX + barW / 2, lo = barX, hi = barX + barW;
    const one = (a) => { let pos = 0, neg = 0; a.flows.concat([[null, null, a.residual]]).forEach((f) => { if (f[2] >= 0) pos += f[2]; else neg -= f[2]; }); return Math.max(pos, neg, Math.abs(a.delta)); };
    const scaleRows = rows.filter((a) => a.k !== 'cash' && a.k !== 'eq');
    const mx = Math.max(...(scaleRows.length ? scaleRows : rows).map(one), 1), sx = (v) => zero + (v / mx) * (barW / 2), cl = (x) => Math.max(lo, Math.min(hi, x));
    const ink = '#1d1d1b', mu = '#6b6a66', bg = '#fbfaf7';
    const colors = { p: '#2e8b57', bridge: '#2a78d6', cap: '#d9822b', sec: '#d9822b' };
    let o = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif">`;
    o += `<defs><pattern id="xh" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="${bg}"/><line x1="0" y1="0" x2="0" y2="7" stroke="${mu}" stroke-width="2.2"/></pattern></defs>`;
    o += `<rect width="${W}" height="${H}" fill="${bg}"/>`;
    o += `<text x="${L}" y="52" font-size="30" font-weight="700" fill="${ink}">${esc(meta.ticker || '')} ${esc(meta.name || '')}</text>`;
    o += `<text x="${L}" y="82" font-size="19" fill="${mu}">Where the balance sheet moved · ${esc(p.start)} → ${esc(p.end)} · ${p.kind === 'q' ? 'one quarter\'s flows' : 'four quarters\' flows'}</text>`;
    let clippedAny = false;
    rows.forEach((a, i) => {
      const y = top + i * rowH;
      o += `<text x="${barX - 14}" y="${y + 26}" font-size="18" text-anchor="end" fill="${ink}">${esc(a.name.replace('Property, plant and equipment', 'PP&E').replace('Goodwill and intangibles', 'Goodwill & intangibles').replace('Cash and equivalents', 'Cash'))}</text>`;
      o += `<text x="${barX - 14}" y="${y + 46}" font-size="13" text-anchor="end" fill="${mu}">${esc(big(a.open))} → ${esc(big(a.close))}</text>`;
      let pos = 0, neg = 0;
      const segs = a.flows.map((f) => [kindOf(f[0]), f[2], f[1]]).concat(Math.abs(a.residual) >= 0.5 ? [['res', a.residual, 'Not explained']] : []);
      segs.forEach(([k, v, lab]) => {
        let x0, x1; if (v >= 0) { x0 = sx(pos); pos += v; x1 = sx(pos); } else { x1 = sx(neg); neg += v; x0 = sx(neg); }
        if (cl(x1) > cl(x0)) o += `<rect x="${cl(x0)}" y="${y + 10}" width="${Math.max(0.6, cl(x1) - cl(x0))}" height="28" fill="${k === 'res' ? 'url(#xh)' : colors[k]}" ${k === 'res' ? `stroke="${mu}" stroke-width="1"` : ''}/>`;
      });
      const clipped = sx(pos) > hi || sx(neg) < lo; clippedAny = clippedAny || clipped;
      const xd = cl(sx(a.delta));
      o += `<line x1="${xd}" x2="${xd}" y1="${y + 4}" y2="${y + 44}" stroke="${ink}" stroke-width="3"/>`;
      // the value sits right of the bar (or left of a negative one), never over the words
      o += `<text x="${hi + 12}" y="${y + 30}" font-size="17" font-weight="600" fill="${ink}">${esc(sgn(a.delta))}${clipped ? ' »' : ''}</text>`;
    });
    o += `<line x1="${zero}" x2="${zero}" y1="${top - 6}" y2="${top + rows.length * rowH}" stroke="#d8d6d0"/>`;
    o += `<text x="${lo}" y="${top + rows.length * rowH + 18}" font-size="13" fill="${mu}">← decreases</text><text x="${hi}" y="${top + rows.length * rowH + 18}" font-size="13" text-anchor="end" fill="${mu}">increases →</text>`;
    // the words
    const tx = 790;
    const wrap = (t, n) => { const out = []; let line = ''; t.split(' ').forEach((w) => { if ((line + ' ' + w).trim().length > n) { out.push(line.trim()); line = w; } else line += ' ' + w; }); if (line.trim()) out.push(line.trim()); return out; };
    let ty = top + 8;
    words(p, 3).forEach((w) => {
      const lines = wrap(w.text, 40);
      lines.forEach((ln, j) => { o += `<text x="${tx}" y="${ty}" font-size="17" fill="${j === 0 ? ink : mu}" ${j === 0 ? 'font-weight="600"' : ''}>${esc(ln)}</text>`; ty += 24; });
      ty += 12;
    });
    o += `<text x="${tx}" y="${ty + 6}" font-size="16" fill="${mu}">The two flow statements explain ${Math.round(100 * (p.explained_share || 0))}% of the movement;</text><text x="${tx}" y="${ty + 30}" font-size="16" fill="${mu}">the rest is in the notes.</text>`;
    const legY = H - 72;
    [['p', 'income statement / operating cash flow'], ['bridge', 'net income → OCF bridge'], ['cap', 'investing & financing'], ['res', 'not explained (hatched)']].forEach(([k, lab], i) => {
      const x = L + i * 290;
      o += `<rect x="${x}" y="${legY - 11}" width="14" height="14" fill="${k === 'res' ? 'url(#xh)' : colors[k]}" ${k === 'res' ? `stroke="${mu}"` : ''}/><text x="${x + 20}" y="${legY + 1}" font-size="14" fill="${mu}">${esc(lab)}</text>`;
    });
    o += `<text x="${L}" y="${H - 38}" font-size="13.5" fill="${mu}">Balances from the filings at both dates (the same XBRL tag at both); bars are the statement lines that touch the account, the tick is the actual change${clippedAny ? '; » = bar cut at the edge' : ''}.</text>`;
    o += `<text x="${L}" y="${H - 18}" font-size="13.5" fill="${mu}">A residual is a question for the notes, not a finding. Not investment advice.</text>`;
    o += `<text x="${W - L}" y="${H - 18}" font-size="16" font-weight="700" text-anchor="end" fill="${ink}">filing-flows.com</text></svg>`;
    return o;
  }

  /* ---- the detailed card: the cash flow statement as a waterfall, every account, every movement in words ---- */
  function cardDetailed(p, meta) {
    const W = 1200, L = 40, ink = '#1d1d1b', mu = '#6b6a66', bg = '#fbfaf7', colors = { p: '#2e8b57', bridge: '#2a78d6', cap: '#d9822b', sec: '#d9822b', res: mu };
    const cf = p.cf, cash = p.accounts.find((a) => a.k === 'cash');
    let o = '', y = 0;
    const text = (x, yy, t, size, fill, extra) => `<text x="${x}" y="${yy}" font-size="${size}" fill="${fill || ink}" ${extra || ''}>${esc(t)}</text>`;
    // header
    o += text(L, 52, `${meta.ticker || ''} ${meta.name || ''}`, 30, ink, 'font-weight="700"');
    o += text(L, 82, `Balance sheet roll-forward in full · ${p.start} → ${p.end} · ${p.kind === 'q' ? "one quarter's flows" : "four quarters' flows (" + (p.quarters || []).join(', ') + ')'}`, 19, mu);
    y = 120;
    // 1. the cash flow statement, as a waterfall from net income to the change in cash
    if (cf) {
      o += text(L, y, '1 · The cash flow statement: from net income to the change in cash', 20, ink, 'font-weight="700"'); y += 14;
      const rows = [['Net income', cf.ni, 'p', 'total']];
      const nc = cf.noncash.slice().sort((a, b) => Math.abs(b[2]) - Math.abs(a[2]));
      nc.slice(0, 4).forEach((x) => rows.push([x[1], x[2], 'bridge']));
      const ncRest = nc.slice(4).reduce((s2, x) => s2 + x[2], 0); if (Math.abs(ncRest) >= 0.5) rows.push(['Other non-cash items', ncRest, 'bridge']);
      const wc = cf.wc.slice().sort((a, b) => Math.abs(b[2]) - Math.abs(a[2]));
      wc.slice(0, 5).forEach((x) => rows.push([x[1], x[2], 'bridge']));
      const wcRest = wc.slice(5).reduce((s2, x) => s2 + x[2], 0); if (Math.abs(wcRest) >= 0.5) rows.push(['Other working capital', wcRest, 'bridge']);
      if (Math.abs(cf.op_other) >= 0.5) rows.push(['Operating lines not itemised', cf.op_other, 'res']);
      rows.push(['Operating cash flow', cf.ocf, 'p', 'total']);
      cf.inv.forEach((x) => rows.push([x[1], x[2], 'cap']));
      if (cf.inv_other_gap != null && Math.abs(cf.inv_other_gap) >= 0.5) rows.push(['Investing lines not itemised', cf.inv_other_gap, 'res']);
      cf.fin.forEach((x) => rows.push([x[1], x[2], 'cap']));
      if (cf.fin_other_gap != null && Math.abs(cf.fin_other_gap) >= 0.5) rows.push(['Financing lines not itemised', cf.fin_other_gap, 'res']);
      if (cf.fx != null && Math.abs(cf.fx) >= 0.5) rows.push(['Currency effect on cash', cf.fx, 'cap']);
      if (cf.dcash != null) rows.push(['Change in cash (the statement)', cf.dcash, 'p', 'total']);
      if (cash) rows.push([`Cash on the balance sheet: ${big(cash.open)} → ${big(cash.close)}`, cash.delta, 'res', 'total']);
      const run = []; let r = 0; rows.forEach((x) => { if (x[3] === 'total') { run.push([0, x[1]]); r = x[1]; } else { run.push([r, r + x[1]]); r += x[1]; } });
      const lo = Math.min(0, ...run.flat()), hi = Math.max(0, ...run.flat()) || 1, bx = 380, bw = 560, sx = (v) => bx + (v - lo) / (hi - lo) * bw, rh = 27;
      rows.forEach((x, i) => {
        const yy = y + 22 + i * rh, [a, b] = run[i];
        o += text(bx - 12, yy + 5, x[0], 14, x[3] === 'total' ? ink : mu, `text-anchor="end" ${x[3] === 'total' ? 'font-weight="600"' : ''}`);
        const fill = x[3] === 'total' ? (x[2] === 'res' ? 'none' : '#4a4a46') : x[2] === 'res' ? 'url(#xh)' : colors[x[2]];
        o += `<rect x="${Math.min(sx(a), sx(b))}" y="${yy - 9}" width="${Math.max(1, Math.abs(sx(b) - sx(a)))}" height="18" fill="${fill}" ${x[2] === 'res' ? `stroke="${mu}" stroke-dasharray="${x[3] === 'total' ? '4 3' : 'none'}"` : ''}/>`;
        o += text(bx + bw + 12, yy + 5, x[3] === 'total' ? big(x[1]) : sgn(x[1]), 14, ink, x[3] === 'total' ? 'font-weight="600"' : '');
      });
      o += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${y + 6}" y2="${y + 22 + rows.length * rh}" stroke="#d8d6d0"/>`;
      y += 22 + rows.length * rh + 10;
      wrapText('Totals (net income, operating cash flow, the change in cash) start from zero; the lines between them run on. Hatched: what the statement does not itemise. The last line is the balance sheet\'s own cash; a gap to the statement is restricted cash or a different cash definition.', 150).forEach((ln) => { o += text(L, y, ln, 12.5, mu); y += 17; });
      y += 20;
    }
    // 2. every account
    o += text(L, y, '2 · Every balance-sheet account: opening balance, what the statements explain, closing balance', 20, ink, 'font-weight="700"'); y += 16;
    const A = p.accounts, barX = 300, barW = 520, zero = barX + barW / 2, lo2 = barX, hi2 = barX + barW, rowH = 50;
    const one = (a) => { let pos = 0, neg = 0; a.flows.concat([[null, null, a.residual]]).forEach((f) => { if (f[2] >= 0) pos += f[2]; else neg -= f[2]; }); return Math.max(pos, neg, Math.abs(a.delta)); };
    const sr = A.filter((a) => a.k !== 'cash' && a.k !== 'eq'), mx = Math.max(...(sr.length ? sr : A).map(one), 1), sx2 = (v) => zero + (v / mx) * (barW / 2), cl = (x) => Math.max(lo2, Math.min(hi2, x));
    let side = '', clippedAny = false;
    A.forEach((a, i) => {
      const yy = y + i * rowH;
      if (a.side !== side) { side = a.side; o += text(L, yy + 24, SIDE[side], 13, mu, 'font-weight="600"'); }
      o += text(barX - 14, yy + 22, a.name, 16, ink, 'text-anchor="end"');
      o += text(barX - 14, yy + 39, `${big(a.open)} → ${big(a.close)}`, 12, mu, 'text-anchor="end"');
      let pos = 0, neg = 0;
      a.flows.map((f) => [kindOf(f[0]), f[2]]).concat(Math.abs(a.residual) >= 0.5 ? [['res', a.residual]] : []).forEach(([k, v]) => {
        let x0, x1; if (v >= 0) { x0 = sx2(pos); pos += v; x1 = sx2(pos); } else { x1 = sx2(neg); neg += v; x0 = sx2(neg); }
        if (cl(x1) > cl(x0)) o += `<rect x="${cl(x0)}" y="${yy + 10}" width="${Math.max(0.6, cl(x1) - cl(x0))}" height="22" fill="${k === 'res' ? 'url(#xh)' : colors[k]}" ${k === 'res' ? `stroke="${mu}"` : ''}/>`;
      });
      const clipped = sx2(pos) > hi2 || sx2(neg) < lo2; clippedAny = clippedAny || clipped;
      const xd = cl(sx2(a.delta));
      o += `<line x1="${xd}" x2="${xd}" y1="${yy + 5}" y2="${yy + 37}" stroke="${ink}" stroke-width="3"/>`;
      o += text(hi2 + 12, yy + 26, sgn(a.delta) + (clipped ? ' »' : ''), 15, ink, 'font-weight="600"');
      o += text(hi2 + 100, yy + 26, Math.abs(a.residual) >= 0.5 ? `residual ${sgn(a.residual)}` : 'fully explained', 12.5, mu);
    });
    o += `<line x1="${zero}" x2="${zero}" y1="${y}" y2="${y + A.length * rowH}" stroke="#d8d6d0"/>`;
    y += A.length * rowH + 8;
    o += text(barX, y + 8, '← decreases', 12.5, mu); o += text(hi2, y + 8, 'increases →', 12.5, mu, 'text-anchor="end"');
    y += 34;
    // 3. in words
    o += text(L, y, '3 · Each movement in words', 20, ink, 'font-weight="700"'); y += 10;
    const wrap = wrapText;
    const floor = Math.max(1e6, (p.totals.assets_close || 0) * 0.005);
    words(p, 11).filter((w) => Math.abs(p.accounts.find((a) => a.k === w.k).delta) >= floor).forEach((w) => {
      wrap(w.text, 118).forEach((ln, j) => { y += 22; o += text(L, y, ln, 15, j === 0 ? ink : mu); });
      y += 6;
    });
    y += 26;
    wrapText(`The two flow statements explain ${Math.round(100 * (p.explained_share || 0))}% of the movement across the accounts; the rest is in the notes (acquisitions, currency, fair value, other comprehensive income, reclassification).`, 135).forEach((ln) => { o += text(L, y, ln, 14, mu); y += 19; });
    y += 26;
    // legend + footer
    [['p', 'income statement / operating cash flow'], ['bridge', 'net income → OCF bridge'], ['cap', 'investing & financing'], ['res', 'not explained / not itemised (hatched)']].forEach(([k, lab], i) => {
      const x = L + i * 290;
      o += `<rect x="${x}" y="${y - 11}" width="14" height="14" fill="${k === 'res' ? 'url(#xh)' : colors[k]}" ${k === 'res' ? `stroke="${mu}"` : ''}/>` + text(x + 20, y + 1, lab, 13.5, mu);
    });
    y += 26;
    o += text(L, y, `Balances from the filings at both dates (the same XBRL tag at both)${clippedAny ? '; » = bar cut at the edge of the scale' : ''}.`, 13, mu);
    y += 18;
    o += text(L, y, 'A residual is a question for the notes, not a finding. Not investment advice.', 13, mu);
    o += text(W - L, y, 'filing-flows.com', 16, ink, 'font-weight="700" text-anchor="end"');
    const H = y + 28;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif"><defs><pattern id="xh" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="${bg}"/><line x1="0" y1="0" x2="0" y2="7" stroke="${mu}" stroke-width="2.2"/></pattern></defs><rect width="${W}" height="${H}" fill="${bg}"/>${o}</svg>`;
  }
  function download(svg, name) {
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }), url = URL.createObjectURL(blob), img = new Image();
    img.onload = () => {
      const m = svg.match(/viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"/), w = m ? +m[1] : 1200, h = m ? +m[2] : 675;
      const c = document.createElement('canvas'); c.width = 2 * w; c.height = 2 * h;
      const g = c.getContext('2d'); g.drawImage(img, 0, 0, 2 * w, 2 * h); URL.revokeObjectURL(url);
      c.toBlob((b) => { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000); }, 'image/png');
    };
    img.src = url;
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
<div class="rv-card"><p><b>In words</b></p><ul style="margin:4px 0 6px;padding-left:18px">${words(p, 3).map((w) => `<li>${esc(w.text)}</li>`).join('')}</ul><p class="sm"><button id="rv-x">Download the X card (PNG, 1200×675)</button> <button id="rv-xd">Download the detailed card (PNG, 1200 wide)</button> <span class="muted">the short card: the six largest movements and the words; the detailed one adds the cash flow statement as a waterfall, every account and every movement in words</span></p></div>
<div class="rv-legend"><span><i style="background:${COL.p}"></i>${esc(KIND_NAME.p)}</span><span><i style="background:${COL.bridge}"></i>${esc(KIND_NAME.bridge)}</span><span><i style="background:${COL.cap}"></i>${esc(KIND_NAME.cap)}</span><span><i style="background:repeating-linear-gradient(45deg,${COL.res} 0 2px,transparent 2px 5px)"></i>${esc(KIND_NAME.res)}</span></div>
<div class="rv-wrap">${strip(p)}</div>
<p class="muted sm">Click an account for its bridge. Balances are the standard tags at each date, the same tag at both dates (a line tagged at one date only falls into "other"); "other assets" and "other liabilities" are what the tagged lines leave of the totals, so the totals always match the filing.</p>
<div id="rv-bridge">${bridge(p.accounts.find((a) => a.k === state.open) || p.accounts.reduce((m, a) => (Math.abs(a.delta) > Math.abs(m.delta) ? a : m), p.accounts[0]), p)}</div>
<details><summary>The matrix: which statement line explains which account</summary>${matrix(p)}</details>
<p class="muted sm">How to read a residual: in receivables or payables it is usually acquisitions, currency or a reclassification between lines; in PP&E the amortisation of intangibles inside one D&A line; in equity other comprehensive income; in investments the securities bought and sold inside "other investing". A large residual is a question for the notes, not a finding. Not investment advice.</p></div>`;
      el.querySelectorAll('button[data-m]').forEach((b) => { b.onclick = () => { state.mode = b.dataset.m; state.i = -1; state.open = null; draw(); }; });
      el.querySelector('#rv-p').onchange = (e) => { state.i = +e.target.value; draw(); };
      el.querySelector('#rv-xd').onclick = () => download(cardDetailed(p, { ticker: opt.ticker || c.ticker || (c.profile || {}).ticker, name: c.name || (c.profile || {}).name }), `${(opt.ticker || 'company')}-balance-sheet-detailed-${p.end}.png`);
      el.querySelector('#rv-x').onclick = () => download(card(p, { ticker: opt.ticker || c.ticker || (c.profile || {}).ticker, name: c.name || (c.profile || {}).name }), `${(opt.ticker || 'company')}-balance-sheet-${p.end}.png`);
      el.querySelectorAll('.rv-row').forEach((g) => { g.onclick = () => { state.open = g.dataset.k; el.querySelector('#rv-bridge').innerHTML = bridge(p.accounts.find((a) => a.k === state.open), p); }; });
    };
    draw();
  }
  window.RollView = { render, strip, bridge, matrix, words, card, cardDetailed };
})();
