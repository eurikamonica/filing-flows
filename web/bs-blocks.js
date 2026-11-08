/* Filing Flows — the balance sheet in blocks, and its bridge to the income statement (company page → Balance sheet).

   Every block is a year-end line of pipeline/reform.py (c.quality.reform) and its height is its amount: what the
   company owns (assets) beside who funds it (liabilities and equity), on one scale. What the tagged lines leave of a
   section is a block of its own ("not tagged separately", hatched). A negative rest — a detail from the notes that is
   also inside another line — comes out of that section's "other" lines, so each column adds up to the filing's totals.
   Nothing is estimated.

   Beside the income statement (c.quality.drivers.fy) the same scale shows how the assets turn into revenue, how much
   of the revenue is left as net income, and what that is on equity (ROE), with the working-capital days on their
   blocks. The equity bridge below takes last year's equity to this year's through net income, dividends, buybacks and
   share-based pay (c.quality.cap.fy, c.quality.fy): the income statement's bottom line, landing on the balance sheet. */
(function (root) {
  'use strict';
  const fin = (v) => typeof v === 'number' && isFinite(v);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const pct = (v, d) => (fin(v) ? `${(v * 100).toFixed(d == null ? 0 : d)}%` : 'n/m');
  const money0 = (v) => {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 0.95e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9) return `${s}$${(a / 1e9).toFixed(1)}B`;
    if (a >= 0.95e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
    return `${s}$${(a / 1e3).toFixed(0)}K`;
  };

  // A detail counted twice comes out of its section's "other" lines, in this order (unclassified sides: any of them).
  const CONTAINERS = { a: { 1: ['oca'], 0: ['onca'] }, l: { 1: ['ocl', 'accr'], 0: ['oncl'] } };
  const UNCLASSIFIED = { a: ['onca', 'oca'], l: ['oncl', 'ocl', 'accr'] };
  // short names for the labels inside the blocks (the tooltip has the full one)
  const SHORT = {
    cash: 'Cash', sti: 'Short-term investments', lti: 'Long-term investments', resale: 'Resale agreements', secs: 'Debt securities',
    eqsec: 'Equity securities', loans: 'Loans', ar: 'Receivables', orec: 'Other receivables', inv: 'Inventory', oca: 'Other current assets',
    ppe: 'PP&E', rou: 'Leased assets', gw: 'Goodwill', intang: 'Intangibles', eqm: 'Equity stakes', dta: 'Deferred tax',
    onca: 'Other non-current', deposits: 'Deposits', repo: 'Repo borrowing', ap: 'Payables', accr: 'Accrued liabilities', comp: 'Accrued pay',
    defrev: 'Deferred revenue', taxp: 'Taxes payable', ocl: 'Other current', std: 'Short-term debt', ltdc: 'Debt due in a year',
    ltd: 'Long-term debt', flease: 'Finance leases', olease: 'Operating leases', taxpn: 'Taxes payable, long-term', dtl: 'Deferred taxes',
    pension: 'Pensions', defrevn: 'Deferred revenue, long-term', oncl: 'Other non-current',
    cse: "Shareholders' equity", nci: 'Minority interests', temp: 'Redeemable equity',
  };
  // shorter still, for a one-line label that does not fit with its amount
  const TINY = { sti: 'ST investments', lti: 'LT investments', accr: 'Accrued', comp: 'Accrued pay', defrev: 'Deferred rev.',
    defrevn: 'Deferred rev., LT', taxpn: 'Taxes payable, LT', onca: 'Other LT assets', oncl: 'Other LT liab.', ocl: 'Other current',
    oca: 'Other current', dtl: 'Deferred tax', resale: 'Resale agr.', eqsec: 'Equities', secs: 'Debt securities' };
  // a line with a part in each section (pipeline/reform.py "cv"): [name, short name] of its current part
  const PART = { olease: ['Operating lease liabilities, current', 'Leases, current'], flease: ['Finance lease liabilities, current', 'Finance leases, current'],
    ltd: ['Current portion of long-term debt', 'Debt due in a year'] };
  const KIND = { oa: 'Operating assets', fa: 'Financial assets', ol: 'Operating liabilities', fo: 'Financial obligations', eq: 'Equity' };
  const kindOf = (b) => b.kind || (b.side === 'e' ? 'eq' : b.side === 'a' ? (b.cls === 'fin' ? 'fa' : 'oa') : (b.cls === 'fin' ? 'fo' : 'ol'));
  const SEC = { 1: 'current', 0: 'non-current' };

  // ---------------------------------------------------------------- the blocks of one year end
  // R: c.quality.reform; i: the year end; cls: the reader's classes ({line key: 'op' | 'fin'}, the workbench's choices)
  function model(R, i, cls) {
    cls = cls || {};
    const T = (k) => ((R.totals || {})[k] || [])[i];
    const m = { i, label: R.labels[i], end: R.ends[i], blocks: { a: [], l: [] }, notes: [], classified: { a: false, l: false } };
    (R.lines || []).forEach((x, n) => {
      const v = x.v[i];
      if (!fin(v)) return;
      const side = x.side, base = { line: x, side, cls: cls[x.k] || x.cls, order: n, why: x.why };
      if ('cur' in x) m.classified[side] = true;
      const cur = 'cur' in x ? x.cur : null;
      if (x.derived) {
        // lines of the same section tagged last year and not this year: probably inside this rest now
        const gone = v > 0 && i > 0 ? (R.lines || []).filter((y) => !y.derived && y.side === side && fin(y.v[i - 1]) && y.v[i - 1] > 0 && !fin(y.v[i])
          && (cur == null || y.cur === cur)).map((y) => ({ name: y.name, v: y.v[i - 1], cls: y.cls })) : [];
        m.blocks[side].push({ ...base, k: x.k, v, cur, derived: true, name: x.name, short: 'Not tagged separately', gone, prevLabel: R.labels[i - 1] });
        return;
      }
      const cv = x.cv && fin(x.cv[i]) ? x.cv[i] : 0;
      const plain = x.k === 'ltd' && /incl\. current/.test(x.name) ? 'Long-term debt' : x.name;
      if (cv > 0 && v - cv >= 0) {
        const [pn, ps] = PART[x.k] || [`${x.name}, current`, `${SHORT[x.k] || x.name}, current`];
        m.blocks[side].push({ ...base, k: `${x.k}:c`, v: cv, cur: 1, name: pn, short: ps, part: x.k });
        m.blocks[side].push({ ...base, k: x.k, v: v - cv, cur: 0, name: plain, short: SHORT[x.k] || plain, whole: v });
      } else {
        m.blocks[side].push({ ...base, k: x.k, v, cur, name: plain, short: SHORT[x.k] || plain });
      }
    });
    ['a', 'l'].forEach((side) => {
      const list = m.blocks[side];
      list.filter((d) => d.derived && d.v < 0).forEach((d) => {
        let need = -d.v;
        const took = [];
        (m.classified[side] && d.cur != null ? CONTAINERS[side][d.cur] : UNCLASSIFIED[side]).forEach((k) => {
          const b = list.find((y) => y.k === k && !y.derived && (d.cur == null || y.cur === d.cur));
          if (!b || need <= 0 || b.v <= 0) return;
          const t = Math.min(need, b.v);
          b.v -= t;
          b.less = (b.less || 0) + t;
          need -= t;
          took.push([b.k, t]);
        });
        let spread = 0;
        if (need > 1e-6) {                      // what the "other" lines cannot take: from every line of the section
          const pool = list.filter((y) => !y.derived && y.v > 0 && (d.cur == null || y.cur === d.cur));
          const sum = pool.reduce((s, y) => s + y.v, 0);
          if (sum > 0) {
            spread = Math.min(need, sum);
            const f = spread / sum;
            pool.forEach((y) => { const t = y.v * f; y.v -= t; y.less = (y.less || 0) + t; y.spread = true; });
          }
        }
        m.notes.push({ kind: 'twice', side, cur: d.cur, v: -d.v, took, spread });
        d.v = 0;
      });
      m.blocks[side] = list.filter((b) => b.v > 0);
    });
    const nci = T('nci') || 0, temp = T('temp') || 0;
    let cse = T('cse');
    if (!fin(cse) && fin(T('assets')) && fin(T('liab'))) {       // equity not tagged: what the liabilities leave
      cse = T('assets') - T('liab') - nci - temp;
      m.cseDerived = true;
    }
    m.tot = { assets: T('assets'), liab: T('liab'), ca: T('ca'), cl: T('cl'), cse, nci, temp, eq: (cse || 0) + nci + temp };
    m.equity = [];
    if (temp > 0) m.equity.push({ k: 'temp', side: 'e', cls: 'eq', v: temp, name: 'Redeemable and temporary equity', short: SHORT.temp, order: 1e3,
      why: 'Shares the holders can make the company buy back: between liabilities and equity.' });
    if (nci > 0) m.equity.push({ k: 'nci', side: 'e', cls: 'eq', v: nci, name: 'Minority interests', short: SHORT.nci, order: 1e3 + 1,
      why: 'The part of subsidiaries owned by other shareholders.' });
    if (cse > 0) m.equity.push({ k: 'cse', side: 'e', cls: 'eq', v: cse, name: "Shareholders' equity", short: SHORT.cse, order: 1e3 + 2,
      why: `What the assets are worth to the shareholders after every liability: the capital they put in plus the profit kept.${m.cseDerived ? ' Not tagged: total assets − total liabilities.' : ''}` });
    m.deficit = fin(cse) && cse < 0 ? -cse : 0;
    const sum = (L) => L.reduce((s, b) => s + b.v, 0);
    m.sumA = sum(m.blocks.a) + m.deficit;
    m.sumL = sum(m.blocks.l) + sum(m.equity);
    return m;
  }

  // the blocks top to bottom: as filed (current, non-current, equity) or operating before financing
  function ordered(m, mode) {
    const sec = (b) => (b.cur === 0 ? 1 : 0);
    const filed = (a, b) => sec(a) - sec(b) || (a.derived ? 1 : 0) - (b.derived ? 1 : 0) || a.order - b.order;
    const opfin = (a, b) => (a.cls === 'fin' ? 1 : 0) - (b.cls === 'fin' ? 1 : 0) || filed(a, b);
    const A = m.blocks.a.slice().sort(mode === 'opfin' ? opfin : filed);
    const L = m.blocks.l.slice().sort(mode === 'opfin' ? opfin : filed);
    if (m.deficit) A.push({ k: 'deficit', side: 'a', kind: 'deficit', v: m.deficit, name: 'Negative equity', short: 'Negative equity', order: 2e3,
      why: 'Liabilities are larger than the assets: shareholders’ equity is below zero (often after buybacks and dividends larger than the profit kept).' });
    return { a: A, l: L.concat(m.equity) };
  }

  // ---------------------------------------------------------------- the income statement of the same year
  function incomeOf(c, end) {
    const Q = c.quality || {}, R = Q.reform || {};
    const d = ((Q.drivers || {}).fy || []).find((x) => x.end === end);
    const f = (R.flows || []).find((x) => x.end === end) || {};
    const y = (Q.fy || []).find((x) => x.end === end) || {};
    const cur = (d && d.cur) || {};
    const revenue = fin(cur.revenue) ? cur.revenue : f.revenue;
    if (!fin(revenue) || revenue <= 0) return null;
    const ni = fin(cur.ni) ? cur.ni : f.ni, oi = fin(cur.oi) ? cur.oi : f.oi;
    if (!fin(ni)) return null;
    const cor = fin(cur.cor) ? cur.cor : fin(cur.gp) ? revenue - cur.gp : (y.wc || {}).cor;
    const opex = fin(cor) && fin(oi) ? revenue - cor - oi : null, below = fin(oi) ? oi - ni : null;
    const loss = ni < 0;
    const total = loss ? revenue - ni : revenue;               // a loss: the costs are larger than revenue
    const tries = [
      [['cor', 'Cost of revenue', cor], ['opex', 'Operating expenses', opex], ['below', loss ? 'Interest, other and tax' : 'Interest, other and tax', below]].concat(loss ? [] : [['ni', 'Net income', ni]]),
      [['cor', 'Cost of revenue', cor], ['rest', 'Other costs, interest and tax', fin(cor) ? total - cor - (loss ? 0 : ni) : null]].concat(loss ? [] : [['ni', 'Net income', ni]]),
      [['rest', 'Costs, interest and tax', total - (loss ? 0 : ni)]].concat(loss ? [] : [['ni', 'Net income', ni]]),
    ];
    const ok = (parts) => parts.every(([, , v]) => fin(v) && v >= 0) && Math.abs(parts.reduce((s, [, , v]) => s + v, 0) - total) <= Math.max(1, total * 1e-6);
    const parts = (tries.find(ok) || [[['rev', 'Revenue', revenue]]]).filter(([, , v]) => v > 0);
    const wc = y.wc || {};
    return { end, revenue, ni, oi, cor, loss, total, parts: parts.map(([k, name, v]) => ({ k, name, v })),
      dso: wc.dso, dio: wc.has_inv === false ? null : wc.dio, dpo: wc.ap_proxy ? null : wc.dpo, ev: (d && d.ev && d.ev.cur) || f.ev || {} };
  }

  // revenue ÷ average assets × net income ÷ revenue × average assets ÷ average equity = net income ÷ average equity
  function dupont(R, i, inc) {
    if (!inc || i < 1) return null;
    const T = (k, j) => ((R.totals || {})[k] || [])[j];
    const eq = (j) => (T('cse', j) || 0);
    const a0 = T('assets', i - 1), a1 = T('assets', i), e0 = eq(i - 1), e1 = eq(i);
    if (!fin(a0) || !fin(a1)) return null;
    const avgA = (a0 + a1) / 2, avgE = (e0 + e1) / 2;
    return { avgA, avgE, turnover: inc.revenue / avgA, margin: inc.ni / inc.revenue, leverage: avgE > 0 ? avgA / avgE : null, roe: avgE > 0 ? inc.ni / avgE : null };
  }

  // ---------------------------------------------------------------- equity, last year end → this one
  function equityBridge(c, i) {
    const Q = c.quality || {}, R = Q.reform || {};
    if (i < 1) return null;
    const open = ((R.totals || {}).cse || [])[i - 1], close = ((R.totals || {}).cse || [])[i], end = R.ends[i];
    if (!fin(open) || !fin(close)) return null;
    const f = (R.flows || []).find((x) => x.end === end) || {};
    const k = ((Q.cap || {}).fy || []).find((x) => x.end === end) || null;
    const y = (Q.fy || []).find((x) => x.end === end) || {};
    const it = (k && k.items) || {};
    const sbcItem = ((y.bridge || {}).items || []).find((x) => x[0] === 'sbc');
    const rows = [];
    const add = (key, name, v, ev, note) => { if (fin(v) && v !== 0) rows.push({ key, name, v, ev, note }); };
    add('ni', 'Net income (the income statement)', f.ni, { ref: (f.ev || {}).ni }, 'The year’s profit for the shareholders: what the income statement adds to equity.');
    add('div', 'Dividends', it.div, { list: (k && k.ev || {}).div }, 'Paid to shareholders in cash (cash-flow statement).');
    add('buyback', 'Buybacks', it.buyback, { list: (k && k.ev || {}).buyback }, 'Shares bought back in cash (cash-flow statement).');
    add('sbc', 'Share-based pay', sbcItem ? sbcItem[1] : null, { ref: sbcItem ? sbcItem[2] : null }, 'Expensed in the income statement without cash: the shares it promises are added to equity.');
    add('stock', 'Shares issued to employees', it.stock, { list: (k && k.ev || {}).stock }, 'Cash received for shares from stock plans.');
    add('withhold', 'Taxes paid on vested shares', it.withhold, { list: (k && k.ev || {}).withhold }, 'Shares held back to pay employees’ taxes: like a buyback.');
    const known = rows.reduce((s, r) => s + r.v, 0), other = close - open - known;
    if (Math.abs(other) > 5e-4 * Math.max(Math.abs(open), Math.abs(close))) {   // under 0.05% of equity: rounding
      rows.push({ key: 'other', name: 'Other changes in equity', v: other, gap: true,
        note: 'Equity at the end − equity at the start − the lines above: other comprehensive income (currency translation, gains on securities), shares issued for acquisitions, and what was recorded in equity but not paid in cash in the year (accrued buybacks, the excise tax).' });
    }
    return { open, close, rows, labels: [R.labels[i - 1], R.labels[i]], ref: [((R.ev_totals || {}).cse || [])[i - 1], ((R.ev_totals || {}).cse || [])[i]] };
  }

  // ---------------------------------------------------------------- drawing
  const MIN_H = 7;                          // px: thinner blocks of one kind and section are drawn as one
  const FONT_W = 6.5;                        // average width of a 12px Plex Sans character, for fitting labels
  function fit(text, px) {
    const n = Math.floor(px / FONT_W);
    if (n < 3) return '';
    return text.length <= n ? text : `${text.slice(0, Math.max(1, n - 1)).trimEnd()}…`;
  }
  // consecutive blocks too thin to see on their own (same kind and section) become one "smaller lines" block
  function merge(list, scale, minH) {
    const out = [];
    let run = [];
    const key = (b) => `${kindOf(b)}|${b.cur === 0 ? 1 : 0}`;
    const flush = () => {
      if (run.length > 1) {
        const v = run.reduce((s, b) => s + b.v, 0);
        out.push({ k: `small:${run[0].k}`, side: run[0].side, cls: run[0].cls, kind: run[0].kind, cur: run[0].cur, v, merged: run.slice(),
          name: `${run.length} smaller lines`, short: `${run.length} smaller lines`, why: run.map((b) => b.name).join(' · ') });
      } else out.push(...run);
      run = [];
    };
    list.forEach((b) => {
      if (b.v * scale < minH && !b.derived && b.kind !== 'deficit' && (!run.length || key(run[0]) === key(b))) run.push(b);
      else { flush(); if (b.v * scale < minH && !b.derived && b.kind !== 'deficit') run.push(b); else out.push(b); }
    });
    flush();
    return out;
  }
  // stack a column from the bottom line up: [{b, x, y, w, h}], the first block at the top
  function stack(list, x, w, bottom, scale) {
    const total = list.reduce((s, b) => s + b.v, 0);
    let y = bottom - total * scale;
    return list.map((b, n) => {
      const h = b.v * scale, next = list[n + 1];
      const gap = !next ? 0 : (b.cur === 0 ? 1 : 0) !== (next.cur === 0 ? 1 : 0) || kindOf(b) !== kindOf(next) ? 4 : 2;
      const r = { b, x, y, w, h: Math.max(0.6, h - gap) };
      y += h;
      return r;
    });
  }
  // Each kind has two validated tones (dataviz validate_palette.js, both themes): lighter for the current section (due
  // or used within a year, near-black text), deeper for the non-current one and for balance sheets without sections
  // (white text). Equity is one deep green.
  const tone = (b) => (b.cur === 1 ? 'c' : 'n');
  const fillClass = (b) => { const k = kindOf(b); return k === 'eq' || k === 'deficit' ? `bsb-k-${k}` : `bsb-k-${k}-${tone(b)}`; };
  function blockSVG(r, idx, pid, money, total) {
    const { b, x, y, w, h } = r, kind = kindOf(b);
    const share = total ? b.v / total : null;
    const label = `${b.name}: ${money(b.v)}${share != null ? `, ${pct(share, 1)}` : ''}`;
    // a hatched rest: the pattern goes in the style attribute, which the kind's class colour cannot override
    const fill = b.derived ? `fill:url(#${pid}-${kind}-${tone(b)})` : null;
    const cls = kind === 'deficit' ? 'bsb-deficit' : b.derived ? 'bsb-x' : fillClass(b);
    const ink = b.derived || kind === 'deficit' ? 'bsb-ink' : kind !== 'eq' && tone(b) === 'c' ? 'bsb-dk' : '';
    const txt = labelSVG(x, y, w, h, b.short || b.name, money(b.v), share != null && share >= 0.01 ? pct(share) : '', ink, TINY[b.k]);
    return `<g class="bsb-b" data-b="${idx}" tabindex="0" role="img" aria-label="${esc(label)}"><rect class="${cls}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="4"${fill ? ` style="${fill}"` : ''}/>${txt}</g>`;
  }
  // the label inside a block: the amount is never cut; a name shows when it fits (or keeps 9 characters before its "…");
  // the share is quieter than the amount
  function labelSVG(x, y, w, h, name, amount, share, ink, tiny) {
    const room = w - 14, chars = Math.floor(room / FONT_W);
    if (room < 30) return '';
    const extra = share ? ` · ${share}` : '';
    const nameFit = name.length <= chars ? name : chars >= 10 ? fit(name, room) : '';
    const withShare = (amount + extra).length <= chars;
    const am = withShare ? amount : amount.length <= chars ? amount : '';
    const amt = (yy, cls) => `<text class="bsb-t bsb-n ${cls || ''} ${ink}" x="${x + 8}" y="${yy}">${esc(am)}${withShare && extra ? `<tspan class="bsb-share">${esc(extra)}</tspan>` : ''}</text>`;
    if (h >= 33 && nameFit && am) return `<text class="bsb-t ${ink}" x="${x + 8}" y="${y + 16}">${esc(nameFit)}</text>${amt(y + 30)}`;
    if (h >= 13) {                             // one line: the name cut to what the amount leaves
      const left = chars - amount.length - 1;
      const nm = name.length <= left ? name : tiny && tiny.length <= left ? tiny : left >= 10 ? fit(name, left * FONT_W) : '';
      const yy = y + Math.min(h / 2 + 4, 17), sm = h < 17 ? 'bsb-sm' : '';
      if (nm) return `<text class="bsb-t ${sm} ${ink}" x="${x + 8}" y="${yy}">${esc(nm)} <tspan class="bsb-n">${esc(amount)}</tspan></text>`;
      return am ? amt(yy, sm) : '';
    }
    return '';
  }
  function hatches(pid) {
    const kinds = ['oa', 'fa', 'ol', 'fo'].flatMap((k) => [`${k}-c`, `${k}-n`]);
    return `<defs>${kinds.map((k) => `<pattern id="${pid}-${k}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" class="bsb-w-${k}"/><line x1="0" y1="0" x2="0" y2="7" class="bsb-l-${k}"/></pattern>`).join('')}</defs>`;
  }
  const yearHead = (m) => `${m.label}${m.end ? ` · ${dateLabel(m.end)}` : ''}`;
  function dateLabel(iso) {
    const [y, mo, d] = String(iso).split('-').map(Number);
    return y && mo ? `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][mo - 1]} ${d}, ${y}` : '';
  }

  // The balance sheet: one year; or last year's beside it on the same scale. With the equity bridge (and room for it)
  // this year's columns face last year's — liabilities and equity inside, assets outside — and the year's net income
  // and payouts step from last year's equity block to this year's between them.
  const STEP_NAME = { ni: 'Net income', div: 'Dividends', buyback: 'Buybacks', sbc: 'Share-based pay', stock: 'Shares issued',
    withhold: 'Tax on vesting', other: 'Other' };
  function blocksSVG(years, mode, W, money, pid, B) {
    const n = years.length, colGap = 6;
    const steps = n > 1 && B && B.open > 0 && B.close > 0 ? B.rows : null;
    const bridgeW = steps ? steps.length * 34 + 52 : 0;
    const side = n === 1 && W >= 640 ? 96 : 0;
    let pairGap = n > 1 ? (steps ? bridgeW : Math.max(30, Math.min(72, W * 0.07))) : 0;
    let colW = Math.min(200, (W - 2 * side - pairGap * (n - 1) - colGap * n) / (2 * n));
    const bridge = steps && colW >= 92;                      // too narrow: the pairs side by side, the bridge below only
    if (!bridge && n > 1) {
      pairGap = Math.max(30, Math.min(72, W * 0.07));
      colW = Math.min(200, (W - pairGap - colGap * 2) / 4);
    }
    const plotH = Math.round(Math.max(250, Math.min(440, W * (W < 560 ? 0.95 : 0.5)))), top = 58, H = top + plotH + 10;
    let peak = 0;
    if (bridge) { let run = B.open; steps.forEach((r) => { run += r.v; peak = Math.max(peak, run, run - r.v); }); }
    const maxT = Math.max(peak, ...years.map((y) => Math.max(y.m.sumA, y.m.sumL)));
    const scale = plotH / maxT, bottom = top + plotH;
    const x0 = (W - (2 * colW * n + colGap * n + pairGap * (n - 1))) / 2;
    const items = [];
    let svg = `<svg class="bsb-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="group" aria-label="Balance sheet in blocks">${hatches(pid)}`;
    const cols = [];
    years.forEach((y, j) => {
      const xp = x0 + j * (2 * colW + colGap + pairGap), ord = ordered(y.m, mode);
      const mirror = bridge && j === 1;                       // this year's claims face last year's
      const xa = mirror ? xp + colW + colGap : xp, xl = mirror ? xp : xp + colW + colGap;
      const A = stack(merge(ord.a, scale, MIN_H), xa, colW, bottom, scale), L = stack(merge(ord.l, scale, MIN_H), xl, colW, bottom, scale);
      cols.push({ A, L, xa, xl, m: y.m });
      const hA = y.m.sumA * scale, hL = y.m.sumL * scale, topY = bottom - Math.max(hA, hL);
      svg += `<text class="bsb-yr" x="${xp + colW + colGap / 2}" y="${topY - 30}" text-anchor="middle">${esc(y.m.label)}<tspan class="bsb-yd">${esc(y.m.end ? `  ${dateLabel(y.m.end)}` : '')}</tspan></text>`;
      svg += `<text class="bsb-ch" x="${xa + colW / 2}" y="${bottom - hA - 9}" text-anchor="middle">${esc(colW >= 120 ? `Assets ${money(y.m.tot.assets)}` : colW >= 64 ? 'Assets' : 'A')}</text>`;
      svg += `<text class="bsb-ch" x="${xl + colW / 2}" y="${bottom - hL - 9}" text-anchor="middle">${esc(colW >= 150 ? 'Liabilities + equity' : colW >= 64 ? 'Liab. + equity' : 'L+E')}</text>`;
      [[A, y.m.tot.assets || y.m.sumA, 'of assets'], [L, y.m.sumL, y.m.deficit ? 'of liabilities' : 'of liabilities and equity']].forEach(([col, total, of]) => col.forEach((r) => {
        items.push({ r, m: y.m, prev: y.prevM, total, of });
        svg += blockSVG(r, items.length - 1, pid, money, total);
      }));
      if (side && y.m.classified.a && mode !== 'opfin') svg += brackets(A, xa - 8, 'end', money, y.m, 'a');
      if (side && y.m.classified.l && mode !== 'opfin') svg += brackets(L, xl + colW + 8, 'start', money, y.m, 'l');
      if (side && mode === 'opfin') svg += kindBrackets(A, xa - 8, 'end', money) + kindBrackets(L, xl + colW + 8, 'start', money);
    });
    if (bridge) svg += bridgeSVG(steps, B, cols, colW, scale, bottom, money, items);
    else if (n > 1) {                                          // the pairs side by side: how much the assets grew
      const a0 = years[0].m.tot.assets, a1 = years[1].m.tot.assets, ax = cols[0].xl + colW + pairGap / 2;
      svg += `<path class="bsb-arrow" d="M${ax - 10},${bottom - 18} L${ax + 8},${bottom - 18} M${ax + 3},${bottom - 23} L${ax + 8},${bottom - 18} L${ax + 3},${bottom - 13}"/>`;
      if (fin(a0) && a0 > 0 && fin(a1) && pairGap >= 44) svg += `<text class="bsb-sl bsb-sv" x="${ax}" y="${bottom - 30}" text-anchor="middle">${esc(`${a1 >= a0 ? '+' : '−'}${pct(Math.abs(a1 / a0 - 1))}`)}</text>`;
    }
    svg += `<line class="bsb-base" x1="${x0 - 4}" x2="${W - x0 + 4}" y1="${bottom + 0.5}" y2="${bottom + 0.5}"/></svg>`;
    return { svg, items, H, bridge };
  }
  // last year's shareholders' equity, the year's steps, this year's: a staircase on the balance sheet's own scale
  function bridgeSVG(steps, B, cols, colW, scale, bottom, money, items) {
    const lev = (v) => bottom - v * scale;
    const from = cols[0].xl + colW, to = cols[1].xl, k = steps.length;
    const sw = Math.min(26, (to - from - 36 - (k - 1) * 8) / k), gap = (to - from - 36 - k * sw) / Math.max(1, k - 1);
    let x = from + 18, run = B.open, out = '';
    out += `<line class="bsb-conn" x1="${from}" x2="${x}" y1="${lev(run)}" y2="${lev(run)}"/>`;
    steps.forEach((r, n) => {
      const a = run, z = run + r.v, yT = lev(Math.max(a, z)), h = Math.max(1.5, Math.abs(r.v) * scale);
      const cls = r.gap ? `bsb-st-gap ${r.v < 0 ? 'minus' : 'plus'}` : r.key === 'ni' ? 'bsb-st-ni' : r.v < 0 ? 'bsb-st-minus' : 'bsb-st-plus';
      items.push({ step: r, B, r: { b: { side: 'step' }, x, y: yT, w: sw, h } });
      const name = STEP_NAME[r.key] || r.name, label = `${name} ${r.v >= 0 ? '+' : '−'}${money(Math.abs(r.v))}`, len = label.length * 6.2;
      // the label turned on its side: inside a step tall enough, else above a rise or below a fall
      const cx = x + sw / 2 + 4, roomUp = yT - 6 - len >= 24, roomDown = yT + h + 6 + len <= bottom - 4;
      const up = (r.v >= 0 && roomUp) || (r.v < 0 && !roomDown && roomUp);
      let t;
      if (h >= len + 10) t = `<text class="bsb-sv-t bsb-in${r.key === 'ni' ? ' bsb-on-ni' : ''}" transform="rotate(-90 ${cx} ${yT + h / 2})" x="${cx}" y="${yT + h / 2}" text-anchor="middle">${esc(label)}</text>`;
      else if (up) t = `<text class="bsb-sv-t" transform="rotate(-90 ${cx} ${yT - 6})" x="${cx}" y="${yT - 6}" text-anchor="start">${esc(label)}</text>`;
      else t = `<text class="bsb-sv-t" transform="rotate(-90 ${cx} ${yT + h + 6})" x="${cx}" y="${yT + h + 6}" text-anchor="end">${esc(label)}</text>`;
      out += `<g class="bsb-b bsb-step" data-b="${items.length - 1}" tabindex="0" role="img" aria-label="${esc(label)}"><rect class="${cls}" x="${x.toFixed(1)}" y="${yT.toFixed(1)}" width="${sw.toFixed(1)}" height="${h.toFixed(1)}" rx="3"/>${t}</g>`;
      run = z;
      const nx = x + sw + (n < k - 1 ? gap : 18);
      out += `<line class="bsb-conn" x1="${x + sw}" x2="${n < k - 1 ? nx : to}" y1="${lev(run)}" y2="${lev(run)}"/>`;
      x = nx;
    });
    const mid = (from + to) / 2;
    out += `<text class="bsb-yr" x="${mid}" y="16" text-anchor="middle">Equity bridge</text><text class="bsb-sl" x="${mid}" y="31" text-anchor="middle">${esc(`net income in, payouts out · ${money(B.open)} → ${money(B.close)}`)}</text>`;
    return out;
  }
  // section labels beside a column: Current $X / Non-current $Y / Equity $Z
  function brackets(col, x, anchor, money, m, side) {
    const groups = [];
    col.forEach((r) => {
      const g = r.b.side === 'e' ? 'Equity' : r.b.kind === 'deficit' ? 'Deficit' : r.b.cur === 0 ? 'Non-current' : 'Current';
      const last = groups[groups.length - 1];
      if (last && last.g === g) { last.y1 = r.y + r.h; last.v += r.b.v; } else groups.push({ g, y0: r.y, y1: r.y + r.h, v: r.b.v });
    });
    const tot = side === 'a' ? { Current: m.tot.ca } : { Current: m.tot.cl };
    return groups.filter((g) => g.y1 - g.y0 >= 26).map((g) => {
      const v = fin(tot[g.g]) ? tot[g.g] : g.v, mid = (g.y0 + g.y1) / 2, dx = anchor === 'end' ? 4 : -4;
      return `<path class="bsb-brk" d="M${x + dx},${g.y0 + 1} L${x},${g.y0 + 1} L${x},${g.y1 - 1} L${x + dx},${g.y1 - 1}"/>
        <text class="bsb-sl" x="${x + (anchor === 'end' ? -6 : 6)}" y="${mid - 3}" text-anchor="${anchor}">${esc(g.g)}</text><text class="bsb-sl bsb-sv" x="${x + (anchor === 'end' ? -6 : 6)}" y="${mid + 11}" text-anchor="${anchor}">${esc(money(v))}</text>`;
    }).join('');
  }
  function kindBrackets(col, x, anchor, money) {
    const groups = [];
    col.forEach((r) => {
      const g = KIND[kindOf(r.b)] || 'Negative equity', last = groups[groups.length - 1];
      if (last && last.g === g) { last.y1 = r.y + r.h; last.v += r.b.v; } else groups.push({ g, y0: r.y, y1: r.y + r.h, v: r.b.v });
    });
    return groups.filter((g) => g.y1 - g.y0 >= 26).map((g) => {
      const mid = (g.y0 + g.y1) / 2, dx = anchor === 'end' ? 4 : -4, words = g.g.split(' '), tx = x + (anchor === 'end' ? -6 : 6);
      const rows = words.length > 1 ? [words[0], words.slice(1).join(' ')] : [words[0]];
      return `<path class="bsb-brk" d="M${x + dx},${g.y0 + 1} L${x},${g.y0 + 1} L${x},${g.y1 - 1} L${x + dx},${g.y1 - 1}"/>
        ${rows.map((w, n) => `<text class="bsb-sl" x="${tx}" y="${mid - 3 + 14 * n}" text-anchor="${anchor}">${esc(w)}</text>`).join('')}
        <text class="bsb-sl bsb-sv" x="${tx}" y="${mid - 3 + 14 * rows.length}" text-anchor="${anchor}">${esc(money(g.v))}</text>`;
    }).join('');
  }

  // assets | the income statement | liabilities and equity, all on one scale, with the links between them
  function incomeSVG(y, inc, dp, mode, W, money, pid) {
    const isW = Math.max(62, Math.min(150, W * 0.15)), colW = Math.min(190, Math.max(70, W * 0.22));
    const gap = (W - 2 * colW - isW) / 2;
    const plotH = Math.round(Math.max(270, Math.min(460, W * (W < 560 ? 1.05 : 0.55)))), top = 46, H = top + plotH + 8, bottom = top + plotH;
    const maxT = Math.max(y.m.sumA, y.m.sumL, inc.total);
    const scale = plotH / maxT;
    const xa = 0, xi = colW + gap, xl = xi + isW + gap;
    const ord = ordered(y.m, mode);
    const A = stack(merge(ord.a, scale, MIN_H), xa, colW, bottom, scale), L = stack(merge(ord.l, scale, MIN_H), xl, colW, bottom, scale);
    const items = [];
    let svg = `<svg class="bsb-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="group" aria-label="Balance sheet beside the income statement">${hatches(pid)}`;
    const hA = y.m.sumA * scale, hL = y.m.sumL * scale, hI = inc.total * scale;
    svg += `<text class="bsb-ch" x="${xa + colW / 2}" y="${bottom - hA - 8}" text-anchor="middle">${esc(colW >= 120 ? `Assets ${money(y.m.tot.assets)}` : 'Assets')}</text>`;
    svg += `<text class="bsb-ch" x="${xl + colW / 2}" y="${bottom - hL - 8}" text-anchor="middle">${esc(colW >= 150 ? 'Liabilities + equity' : 'Liab. + equity')}</text>`;
    svg += `<text class="bsb-ch" x="${xi + isW / 2}" y="${bottom - hI - 8}" text-anchor="middle">${esc(inc.loss ? (isW >= 110 ? `Net loss ${money(-inc.ni)}` : 'Net loss') : isW >= 110 ? `Revenue ${money(inc.revenue)}` : 'Revenue')}</text>`;
    [[A, y.m.tot.assets || y.m.sumA, 'of assets'], [L, y.m.sumL, y.m.deficit ? 'of liabilities' : 'of liabilities and equity']].forEach(([col, total, of]) => col.forEach((r) => {
      items.push({ r, m: y.m, prev: y.prevM, total, of });
      svg += blockSVG(r, items.length - 1, pid, money, total);
    }));
    // the income statement in the Sankeys' colours: costs in red above net income in the equity green (where it lands)
    const I = stack(inc.parts.map((p) => ({ k: `is:${p.k}`, side: 'is', kind: p.k === 'ni' ? 'ni' : `c-${p.k}`, v: p.v, name: p.name, short: p.name, cur: 1 })),
      xi, isW, bottom, scale).map((r) => ({ ...r, h: r.h }));
    let labels = '';
    I.forEach((r) => {
      items.push({ r, m: y.m, inc, total: inc.revenue });
      const idx = items.length - 1, { b, x, y: yy, w, h } = r, share = b.v / inc.revenue;
      const ink = b.kind === 'ni' || b.kind === 'c-cor' ? '' : 'bsb-onlight';     // the deep red and the green take white text
      labels += labelSVG(x, yy, w, h, b.name, money(b.v), pct(share), ink, { 'is:below': 'Interest & tax', 'is:rest': 'Other costs', 'is:opex': 'Opex' }[b.k]);
      svg += `<g class="bsb-b" data-b="${idx}" tabindex="0" role="img" aria-label="${esc(`${b.name}: ${money(b.v)}, ${pct(share, 1)} of revenue`)}"><rect class="bsb-is-${b.kind === 'ni' ? 'ni' : b.kind}" x="${x.toFixed(1)}" y="${yy.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="4"/></g>`;
    });
    if (inc.loss) {                          // the costs pass revenue by the loss: hatched above the revenue line
      const yr = bottom - inc.revenue * scale, yt = bottom - hI;
      svg += `<rect class="bsb-loss" x="${xi - 3}" y="${yt}" width="${isW + 6}" height="${Math.max(1, yr - yt)}" rx="4" style="fill:url(#${pid}-fo-n)"/><line class="bsb-revline" x1="${xi - 6}" x2="${xi + isW + 6}" y1="${yr}" y2="${yr}"/>
        <text class="bsb-sl bsb-sv" x="${xi + isW + 8}" y="${yr + 4}">${esc(gap >= 120 ? `revenue ${money(inc.revenue)}` : 'revenue')}</text>`;
    }
    svg += labels;
    // links: a block's stock against the flow it turns over with
    const at = (col, k) => col.find((r) => r.b.k === k || (r.b.merged || []).some((b) => b.k === k));
    const seg = (k) => I.find((r) => r.b.k === `is:${k}`);
    const cor = seg('cor'), ni = seg('ni'), wide = gap >= 150;
    const rev = { x: xi, y: bottom - inc.revenue * scale, w: isW, h: 0 };   // revenue: the whole column, from its top (the revenue line)
    const days = (d, of) => (wide ? `${Math.round(d)} days of ${of}` : `${Math.round(d)} days`);
    const links = [];
    if (fin(inc.dso) && at(A, 'ar')) links.push({ a: at(A, 'ar'), b: rev, left: true, label: days(inc.dso, 'revenue'), title: 'Receivables ÷ revenue × days in the year: how long customers take to pay (DSO)' });
    if (fin(inc.dio) && at(A, 'inv') && cor) links.push({ a: at(A, 'inv'), b: cor, left: true, label: days(inc.dio, 'costs'), title: 'Inventory ÷ cost of revenue × days: how long goods wait to be sold (DIO)' });
    if (fin(inc.dpo) && at(L, 'ap') && cor) links.push({ a: at(L, 'ap'), b: cor, left: false, label: days(inc.dpo, 'costs'), title: 'Payables ÷ cost of revenue × days: how long the company takes to pay suppliers (DPO)' });
    if (dp && fin(dp.roe) && at(L, 'cse') && ni) links.push({ a: at(L, 'cse'), b: ni, left: false, label: `ROE ${pct(dp.roe)}`, title: 'Net income ÷ average shareholders’ equity', strong: true });
    links.forEach((k) => {
      const ya = k.a.y + Math.min(k.a.h / 2, 18), yb = k.b.h ? k.b.y + Math.min(k.b.h / 2, 90) : k.b.y + 3;
      const xA = k.left ? k.a.x + k.a.w : k.a.x, xB = k.left ? k.b.x : k.b.x + k.b.w;
      const mx = (xA + xB) / 2;
      svg += `<g class="bsb-link${k.strong ? ' strong' : ''}"><title>${esc(k.title)}</title><path d="M${xA},${ya} C${mx},${ya} ${mx},${yb} ${xB},${yb}"/><circle cx="${xA}" cy="${ya}" r="3"/><circle cx="${xB}" cy="${yb}" r="3"/>
        <text class="bsb-ll" x="${k.left ? xA + 8 : xA - 8}" y="${ya - 7}" text-anchor="${k.left ? 'start' : 'end'}">${esc(k.label)}</text></g>`;
    });
    svg += `<line class="bsb-base" x1="0" x2="${W}" y1="${bottom + 0.5}" y2="${bottom + 0.5}"/></svg>`;
    return { svg, items, H };
  }

  // ---------------------------------------------------------------- the tooltip of a block
  function tipHTML(it, money) {
    if (it.step) {
      const r = it.step;
      return `<b>${esc(r.name)}</b><span>${r.v >= 0 ? '+' : '−'}${esc(money(Math.abs(r.v)))} · ${esc(it.B.labels[1])}</span>${r.note ? `<span class="muted">${esc(r.note)}</span>` : ''}`;
    }
    const b = it.r.b, kind = kindOf(b);
    if (b.side === 'is') {
      const inc = it.inc;
      return `<b>${esc(b.name)}</b><span>${esc(money(b.v))} · ${pct(b.v / inc.revenue, 1)} of revenue</span>${b.k === 'is:ni' ? '<span class="muted">What the year left for the shareholders: it is added to equity (see the bridge below).</span>' : ''}`;
    }
    const prev = it.prev && (it.prev.blocks[b.side === 'e' ? 'l' : b.side] || []).concat(it.prev.equity || []).find((y) => y.k === b.k);
    const d = prev && !b.merged ? b.v - prev.v : null;
    const where = b.side === 'e' ? 'Equity' : kind === 'deficit' ? '' : `${b.cls === 'fin' ? 'Financing' : 'Operating'}${b.cur != null ? ` · ${SEC[b.cur]}` : ''}`;
    const lines = [`<b>${esc(b.name)}</b>`, `<span>${esc(money(b.v))}${it.total ? ` · ${pct(b.v / it.total, 1)} ${esc(it.of || 'of the column')}` : ''}</span>`];
    if (where) lines.push(`<span class="muted">${esc(where)}</span>`);
    if (fin(d) && prev) lines.push(`<span>${d >= 0 ? '+' : '−'}${esc(money(Math.abs(d)))} since ${esc(it.prev.label)}${prev.v > 0 ? ` (${d >= 0 ? '+' : '−'}${pct(Math.abs(d / prev.v))})` : ''}</span>`);
    if (b.merged) lines.push(`<span class="muted">${b.merged.map((x) => `${esc(x.name)} ${esc(money(x.v))}`).join('<br>')}</span>`);
    else if (b.why) lines.push(`<span class="muted">${esc(b.why)}</span>`);
    if (b.whole) lines.push(`<span class="muted">Of ${esc(money(b.whole))} in all; the part due within a year is a block of its own among the current lines.</span>`);
    if ((b.gone || []).length) lines.push(`<span>Probably inside it: ${b.gone.map((g) => `${esc(g.name.toLowerCase())} (${esc(money(g.v))} in ${esc(b.prevLabel)})`).join(', ')} — tagged last year, without a standard tag this year.</span>`);
    if (b.less) lines.push(`<span class="muted">${esc(money(b.less))} taken out: lines shown as blocks of their own are inside this one in the filing (${b.spread ? 'shared out over the section' : 'counted twice otherwise'}).</span>`);
    return lines.join('');
  }

  // ---------------------------------------------------------------- the section on the page
  function readCls(cik) {
    try { return (JSON.parse(localStorage.getItem(`ff-reform-${cik}`) || '{}') || {}).cls || {}; } catch (e) { return {}; }
  }
  function readPrefs() {
    try { return JSON.parse(localStorage.getItem('ff:bsb') || '{}') || {}; } catch (e) { return {}; }
  }
  function savePrefs(p) {
    try { localStorage.setItem('ff:bsb', JSON.stringify(p)); } catch (e) { /* private window */ }
  }

  function netOps(m) {
    const sum = (L, f) => L.filter(f).reduce((s, b) => s + b.v, 0);
    const oa = sum(m.blocks.a, (b) => b.cls !== 'fin'), fa = sum(m.blocks.a, (b) => b.cls === 'fin');
    const ol = sum(m.blocks.l, (b) => b.cls !== 'fin'), fo = sum(m.blocks.l, (b) => b.cls === 'fin');
    return { oa, fa, ol, fo, noa: oa - ol, nfo: fo - fa };
  }
  // the four numbers above the chart: size, funding, and cash against debt (or, operating / financing, NOA and NFO)
  function kpis(m, prevM, mode, money) {
    const T = m.tot, A = T.assets || m.sumA, o = netOps(m);
    const tile = (label, value, note, cls) => `<div class="q-kpi"><small>${esc(label)}</small><strong class="${cls || ''}">${esc(value)}</strong><span>${esc(note || '')}</span></div>`;
    const tiles = [];
    const d = prevM && fin(prevM.tot.assets) && prevM.tot.assets > 0 && fin(T.assets) ? T.assets / prevM.tot.assets - 1 : null;
    tiles.push(tile('Total assets', money(A), d == null ? m.label : `${d >= 0 ? '+' : '−'}${pct(Math.abs(d))} since ${prevM.label}`));
    if (m.deficit) tiles.push(tile("Shareholders' equity", money(T.cse), 'liabilities are larger than the assets', 'q-warmtext'));
    else {
      const de = prevM && fin(prevM.tot.cse) && fin(T.cse) ? T.cse - prevM.tot.cse : null;
      tiles.push(tile('Funded by equity', pct(T.eq / A), `liabilities ${pct((T.liab || 0) / A)}${de != null ? ` · equity ${de >= 0 ? '+' : '−'}${money(Math.abs(de))}` : ''}`));
    }
    if (mode === 'opfin') {
      tiles.push(tile('Net operating assets', money(o.noa), `operating assets ${money(o.oa)} − liabilities ${money(o.ol)}`));
      tiles.push(tile(o.nfo > 0 ? 'Net financial obligations' : 'Net financial assets', money(Math.abs(o.nfo)), `financial ${money(o.fa)} vs obligations ${money(o.fo)}`));
    } else {
      tiles.push(tile('Cash and investments', money(o.fa), `${pct(o.fa / A)} of the assets`));
      tiles.push(tile('Debt and leases', money(o.fo), o.fa - o.fo >= 0 ? `net cash ${money(o.fa - o.fo)}` : `net debt ${money(o.fo - o.fa)}`));
    }
    return `<div class="q-kpis cq-kpis bsb-kpis">${tiles.join('')}</div>`;
  }
  function summary(m, prevM, money) {
    const T = m.tot, A = T.assets || m.sumA;
    const fa = m.blocks.a.filter((b) => b.cls === 'fin').reduce((s, b) => s + b.v, 0);
    const fo = m.blocks.l.filter((b) => b.cls === 'fin').reduce((s, b) => s + b.v, 0);
    const parts = [];
    if (m.deficit) parts.push(`liabilities of ${money(T.liab)} are larger than the assets of ${money(A)}: shareholders’ equity is ${money(T.cse)}`);
    else parts.push(`${money(A)} of assets, funded ${pct((T.liab || 0) / A)} by liabilities and ${pct(T.eq / A)} by equity`);
    if (fa > 0) parts.push(`cash and investments are ${pct(fa / A)} of the assets`);
    parts.push(fo > 0 ? `debt and leases counted as financing are ${money(fo)}` : 'no debt is tagged');
    let s = `${m.label}: ${parts.join('; ')}.`;
    if (prevM && fin(prevM.tot.assets) && prevM.tot.assets > 0 && fin(T.assets)) {
      const d = T.assets - prevM.tot.assets;
      s += ` Assets ${d >= 0 ? 'grew' : 'fell'} ${pct(Math.abs(d / prevM.tot.assets))} since ${prevM.label} (${d >= 0 ? '+' : '−'}${money(Math.abs(d))}), equity ${fin(prevM.tot.cse) && fin(T.cse) ? `${T.cse - prevM.tot.cse >= 0 ? '+' : '−'}${money(Math.abs(T.cse - prevM.tot.cse))}` : 'n/m'}.`;
    }
    return s;
  }

  function bridgeHTML(B, money, evBtn) {
    const rows = [{ name: `Equity, ${B.labels[0]}`, v: B.open, base: true, ref: B.ref[0] }].concat(B.rows, [{ name: `Equity, ${B.labels[1]}`, v: B.close, base: true, ref: B.ref[1] }]);
    let run = 0;
    const spans = rows.map((r) => { if (r.base) { run = r.v; return [0, r.v]; } const s = [run, run + r.v]; run += r.v; return s; });
    const lo = Math.min(0, ...spans.flat()), hi = Math.max(0, ...spans.flat()), w = (hi - lo) || 1, pos = (v) => ((v - lo) / w * 100).toFixed(2);
    const pay = (r) => {
      if (!evBtn) return null;
      if (r.base) return { title: r.name, value: money(r.v), period: r.name.split(', ').pop(), ref: r.ref };
      if (r.gap) return { title: r.name, value: money(r.v), period: B.labels[1], kind: 'Derived', formula: `equity ${money(B.close)} − ${money(B.open)} − the lines above`, note: r.note };
      const e = r.ev || {};
      if (e.ref) return { title: r.name, value: money(r.v), period: B.labels[1], ref: e.ref, note: r.note };
      if ((e.list || []).length === 1) return { title: r.name, value: money(r.v), period: B.labels[1], ref: e.list[0][1], note: r.note };
      if ((e.list || []).length) return { title: r.name, value: money(r.v), period: B.labels[1], kind: 'Reported', formula: 'sum of the tagged lines', note: r.note,
        inputs: e.list.map(([v, ref]) => ({ title: r.name, value: money(v), period: B.labels[1], ref })) };
      return null;
    };
    return `<div class="cq-bridge bsb-eqb" role="table" aria-label="Equity bridge, ${esc(B.labels[0])} to ${esc(B.labels[1])}">${rows.map((r, n) => {
      const [x, z] = spans[n], left = pos(Math.min(x, z)), width = Math.max(0.4, Math.abs(pos(z) - pos(x))).toFixed(2);
      const cls = r.base ? 'base bsb-eq' : r.gap ? `dv-gap ${r.v < 0 ? 'minus' : 'plus'}` : `nc ${r.v < 0 ? 'minus' : 'plus'}${r.key === 'ni' ? ' bsb-ni' : ''}`;
      const text = `${r.base ? '' : r.v > 0 ? '+' : ''}${money(r.v)}`, p = pay(r);
      return `<div class="cq-row ${r.base ? 'base' : r.gap ? 'gap' : ''}" role="row"><span role="rowheader" title="${esc(r.note || '')}">${esc(r.name)}</span>
        <span class="cq-track" role="cell"><i class="cq-bar ${cls}" style="left:${left}%;width:${width}%"></i>${r.base ? '' : `<i class="cq-zero" style="left:${pos(0)}%"></i>`}</span>
        <span class="num" role="cell">${p && evBtn ? evBtn(esc(text), p) : esc(text)}</span></div>`;
    }).join('')}</div>`;
  }

  function mount(body, c, opts) {
    opts = opts || {};
    const money = opts.money || money0, evBtn = opts.evBtn || null;
    const R = (c.quality || {}).reform, P = c.profile || {};
    if (!R || !(R.lines || []).length || !(R.ends || []).length) return null;
    const box = document.createElement('section');
    box.className = 'section bsb';
    box.setAttribute('aria-labelledby', 'bsb-title');
    body.appendChild(box);
    const pref = readPrefs(), n = R.ends.length;
    const st = { i: n - 1, view: pref.view === 'is' ? 'is' : 'bs', mode: pref.mode === 'opfin' ? 'opfin' : 'filed',
      cmp: typeof pref.cmp === 'boolean' ? pref.cmp : (box.clientWidth || 720) >= 560 };
    const pid = `bsbp${Math.random().toString(36).slice(2, 8)}`;
    let items = [], width = 0;
    function draw() {
      const cls = readCls(P.cik), m = model(R, st.i, cls), prevM = st.i > 0 ? model(R, st.i - 1, cls) : null;
      const inc = incomeOf(c, R.ends[st.i]), dp = dupont(R, st.i, inc), B = equityBridge(c, st.i);
      const W = Math.max(300, Math.min(1120, box.clientWidth || 720));
      width = box.clientWidth;
      const view = st.view === 'is' && inc ? 'is' : 'bs';
      const years = view === 'bs' && st.cmp && prevM ? [{ m: prevM, prev: true }, { m, prevM }] : [{ m, prevM }];
      const out = view === 'is' ? incomeSVG({ m, prevM }, inc, dp, st.mode, W, money, pid) : blocksSVG(years, st.mode, W, money, pid, B);
      items = out.items;
      const twice = m.notes.filter((x) => x.kind === 'twice');
      const untagged = m.blocks.a.concat(m.blocks.l).filter((b) => b.derived);
      const sections = m.classified.a || m.classified.l;
      const legend = ['oa', 'fa', 'ol', 'fo'].map((k) => `<span><i class="bsb-key bsb-key-${k}-c"></i><i class="bsb-key bsb-key-${k}-n"></i>${KIND[k]}</span>`).join('') +
        '<span><i class="bsb-key bsb-key-eq"></i>Equity</span>' +
        (untagged.length ? '<span><i class="bsb-key bsb-key-x"></i>Not tagged separately</span>' : '') + (m.deficit ? '<span><i class="bsb-key bsb-key-d"></i>Negative equity</span>' : '') +
        (view === 'is' ? '<span><i class="bsb-key bsb-key-c"></i>Costs, interest and tax</span>' : '') +
        (out.bridge ? '<span><i class="bsb-key bsb-key-eq"></i><i class="bsb-key bsb-key-minus"></i>Equity bridge: added, paid out</span>' : '') +
        (sections ? '<span class="bsb-note">lighter: current (within a year) · deeper: non-current</span>' : '');
      box.innerHTML = `<div class="section-head"><h2 id="bsb-title">Balance sheet in blocks</h2>
          <span class="muted">What the company owns, and who funds it · each block’s height is its amount, one scale for every column · the balance sheet, XBRL</span></div>
        <div class="q-bar bsb-bar">
          <div class="seg" role="group" aria-label="View"><button type="button" data-v="bs" class="${view === 'bs' ? 'on' : ''}">Balance sheet</button><button type="button" data-v="is" class="${view === 'is' ? 'on' : ''}" ${inc ? '' : 'disabled title="No revenue tagged for this year"'}>Beside the income statement</button></div>
          <div class="seg" role="group" aria-label="Order of the blocks"><button type="button" data-o="filed" class="${st.mode === 'filed' ? 'on' : ''}">As filed</button><button type="button" data-o="opfin" class="${st.mode === 'opfin' ? 'on' : ''}">Operating / financing</button></div>
          <label class="q-pick">Fiscal year <select data-y>${R.ends.map((e, j) => `<option value="${j}" ${j === st.i ? 'selected' : ''}>${esc(R.labels[j])}</option>`).join('')}</select></label>
          ${view === 'bs' && prevM ? `<label class="q-pick bsb-cmp"><input type="checkbox" data-c ${st.cmp ? 'checked' : ''}> ${esc(prevM.label)} beside it</label>` : ''}
        </div>
        ${kpis(m, prevM, st.mode, money)}
        ${view === 'is' && dp ? `<p class="bsb-dupont">${esc(`Revenue ÷ average assets ${dp.turnover.toFixed(2)}×`)} <span>×</span> ${esc(`net income ÷ revenue ${pct(dp.margin, 1)}`)} <span>×</span> ${esc(`average assets ÷ average equity ${dp.leverage != null ? dp.leverage.toFixed(2) + '×' : 'n/m'}`)} <span>=</span> <b>${esc(`ROE ${pct(dp.roe, 1)}`)}</b></p>` : ''}
        <div class="bsb-plot">${out.svg}<div class="bsb-tip" role="status" aria-live="polite" hidden></div></div>
        <div class="q-legend bsb-legend">${legend}</div>
        ${twice.length || untagged.length || (P.sector === 'financials' || /^6[0-7]/.test(String(P.sic || ''))) ? `<p class="muted q-small">${[
          untagged.length ? `Hatched: what the tagged lines leave of ${untagged.map((b) => (b.cur === 1 ? 'current ' : b.cur === 0 ? 'non-current ' : '') + (b.side === 'a' ? 'assets' : 'liabilities')).join(' and ')} — lines the company tags its own way (${untagged.map((b) => money(b.v)).join(', ')}).` +
            untagged.filter((b) => (b.gone || []).length).map((b) => ` ${b.gone.map((g) => `${g.name} (${money(g.v)} in ${b.prevLabel})`).join(', ')} ${b.gone.length > 1 ? 'have' : 'has'} no standard tag in ${m.label}: probably inside the ${money(b.v)}${b.gone.some((g) => g.cls === 'fin') ? ' — move that line to financing in the workbench below to count it so' : ''}.`).join('') : '',
          twice.length ? `Lines counted twice in the tags (${twice.map((x) => money(x.v)).join(', ')}) are taken out of the “other” lines that contain them, so each column adds up to the filing’s total.` : '',
          P.sector === 'financials' || /^6[0-7]/.test(String(P.sic || '')) ? 'Banks and insurers: deposits, loans and investments are the business itself, and much of the balance sheet is tagged their own way.' : '',
        ].filter(Boolean).join(' ')}</p>` : ''}
        ${B ? `<h3 class="cq-h3">Net income into equity, ${esc(B.labels[0])} → ${esc(B.labels[1])}</h3>
          <p class="muted q-small">The bridge between the two statements${out.bridge ? ', line by line' : ''}: last year’s equity, plus the year’s net income from the income statement, less what was paid out, is this year’s equity. Each figure opens its tagged source.</p>
          ${bridgeHTML(B, money, evBtn)}
          <div class="q-legend"><span><i class="cq-bar plus nc"></i>Added to equity</span><span><i class="cq-bar minus nc"></i>Taken out</span><span><i class="cq-gap-key"></i>Not in a line of its own</span></div>` : ''}`;
      bind();
    }
    function show(g, ev) {
      const tip = box.querySelector('.bsb-tip'), it = items[+g.dataset.b];
      if (!tip || !it) return;
      tip.innerHTML = tipHTML(it, money);
      tip.hidden = false;
      const plot = box.querySelector('.bsb-plot').getBoundingClientRect(), r = g.getBoundingClientRect();
      const tw = Math.min(280, plot.width - 16);
      tip.style.width = `${tw}px`;
      let x = (ev && ev.clientX != null ? ev.clientX : r.left + r.width / 2) - plot.left + 14;
      if (x + tw > plot.width - 4) x = Math.max(4, (ev && ev.clientX != null ? ev.clientX : r.left) - plot.left - tw - 14);
      let y = (ev && ev.clientY != null ? ev.clientY : r.top + 8) - plot.top + 12;
      y = Math.max(4, Math.min(y, plot.height - tip.offsetHeight - 4));
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
      box.querySelectorAll('.bsb-b.on').forEach((x2) => x2.classList.remove('on'));
      g.classList.add('on');
      const svg = box.querySelector('.bsb-svg');
      if (svg) svg.classList.add('focus');
    }
    function hide() {
      const tip = box.querySelector('.bsb-tip');
      if (tip) tip.hidden = true;
      box.querySelectorAll('.bsb-b.on').forEach((x) => x.classList.remove('on'));
      const svg = box.querySelector('.bsb-svg');
      if (svg) svg.classList.remove('focus');
    }
    function bind() {
      const save = () => savePrefs({ view: st.view, mode: st.mode, cmp: st.cmp });
      box.querySelectorAll('[data-v]').forEach((b) => b.addEventListener('click', () => { st.view = b.dataset.v; save(); draw(); }));
      box.querySelectorAll('[data-o]').forEach((b) => b.addEventListener('click', () => { st.mode = b.dataset.o; save(); draw(); }));
      const sel = box.querySelector('[data-y]');
      if (sel) sel.addEventListener('change', (e) => { st.i = +e.target.value; draw(); });
      const cb = box.querySelector('[data-c]');
      if (cb) cb.addEventListener('change', (e) => { st.cmp = e.target.checked; save(); draw(); });
      box.querySelectorAll('.bsb-b').forEach((g) => {
        g.addEventListener('pointermove', (e) => show(g, e));
        g.addEventListener('click', (e) => show(g, e));          // a tap on a phone
        g.addEventListener('pointerleave', hide);
        g.addEventListener('focus', () => show(g, null));
        g.addEventListener('blur', hide);
      });
    }
    draw();
    // a new width redraws (phones turned sideways); the workbench below changing a line's class redraws as well
    if (typeof ResizeObserver !== 'undefined') {
      let t = null;
      new ResizeObserver(() => { if (Math.abs(box.clientWidth - width) < 24) return; clearTimeout(t); t = setTimeout(draw, 120); }).observe(box);
    }
    const onClass = (e) => {
      if (!box.isConnected) { document.removeEventListener('ff:reform', onClass); return; }   // the page was left
      if (!e.detail || String(e.detail.cik) === String(P.cik)) draw();
    };
    document.addEventListener('ff:reform', onClass);
    return box;
  }

  root.FFBSBlocks = { mount, model, ordered, incomeOf, dupont, equityBridge, merge, stack };
})(typeof window === 'undefined' ? globalThis : window);
