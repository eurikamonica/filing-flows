#!/usr/bin/env node
/* The Buyouts board: runs the LBO model (disclosures/docs/lbo-model.js, default assumptions) for every company of
   research/lbo public/index.json and adds the results to its rows: IRR at today's price plus 30%, the most a buyer could
   pay for 20% (and how far that is from the price), entry multiple, leverage, flags — then a buyout score that weighs
   the three angles: the model (IRR), history (the chance companies like it were bought) and what is being said (rumors).
     node disclosures/app/lbo_board.cjs <root>/public */
'use strict';
const fs = require('fs');
const path = require('path');
const M = require('../docs/lbo-model.js');

function rank(vals) {                       // percentile rank in 0..1 of each value (null stays null)
  const xs = vals.map((v, i) => [v, i]).filter((x) => x[0] != null && Number.isFinite(x[0])).sort((a, b) => a[0] - b[0]);
  const out = vals.map(() => null);
  xs.forEach((x, k) => { out[x[1]] = xs.length > 1 ? k / (xs.length - 1) : 0.5; });
  return out;
}

function board(doc) {
  const F = doc.fields, ix = (k) => F.indexOf(k);
  const rates = doc.rates || {};
  const rows = doc.rows.map((r) => {
    const inp = r[ix('inputs')];
    let res = null, mp = null;
    if (inp) {
      res = M.run(inp, {}, rates);
      mp = res.ok ? M.maxPrice(inp, {}, rates) : null;
    }
    return { r, inp, res, mp };
  });
  const irr = rank(rows.map((x) => (x.res && x.res.ok && !x.res.flags.length ? x.res.irr : null)));
  const hist = rank(rows.map((x) => x.r[ix('p_acquired')]));
  const out = rows.map((x, k) => {
    const r = x.r, ok = x.res && x.res.ok;
    const rum = Math.min(1, (r[ix('rumor')] || 0) / 5);
    const parts = [[irr[k], 0.4], [hist[k], 0.35], [rum, 0.25]].filter((p) => p[0] != null);
    const w = parts.reduce((a, p) => a + p[1], 0);
    const score = w ? Math.round(100 * parts.reduce((a, p) => a + p[0] * p[1], 0) / w) : null;
    return [r[ix('cik')], r[ix('ticker')], r[ix('name')], r[ix('sector')], x.inp ? x.inp.price : null,
      ok ? Math.round(1000 * x.res.irr) / 1000 : null, x.mp && x.mp.price != null ? Math.round(100 * x.mp.price) / 100 : null,
      x.mp && x.mp.price != null && x.inp ? Math.round(1000 * (x.mp.price / x.inp.price - 1)) / 1000 : null,
      ok ? Math.round(10 * x.res.todayMultiple) / 10 : null, ok ? Math.round(10 * x.res.entry.leverage) / 10 : null,
      ok ? x.res.flags : (x.res ? [x.res.why] : []), x.inp ? Math.round(x.inp.price * x.inp.shares + (x.inp.debt || 0) - (x.inp.cash || 0)) : null,
      r[ix('p_acquired')], r[ix('decile')], r[ix('p_private')], r[ix('rumor')], r[ix('rumor_date')], r[ix('rumor_kind')], r[ix('rumor_text')], score];
  });
  const fields = ['cik', 'ticker', 'name', 'sector', 'price', 'irr', 'max_price', 'max_vs_price', 'ev_ebitda', 'leverage', 'flags', 'ev',
    'p_acquired', 'decile', 'p_private', 'rumor', 'rumor_date', 'rumor_kind', 'rumor_text', 'score'];
  return { generated_at: doc.generated_at, board_at: new Date().toISOString(), rates, assumptions: M.DEFAULTS, fields, rows: out };
}

if (require.main === module) {
  const pub = process.argv[2] || 'public';
  const doc = JSON.parse(fs.readFileSync(path.join(pub, 'index.json'), 'utf8'));
  const b = board(doc);
  fs.writeFileSync(path.join(pub, 'board.json'), JSON.stringify(b));
  const n = b.rows.filter((r) => r[5] != null).length, floor = b.rows.filter((r) => r[7] != null && r[7] > 0 && !(r[10] || []).length).length;
  console.log(`buyouts board: ${b.rows.length} companies, ${n} modelled, ${floor} with a 20% buyout price above today's`);
}
module.exports = { board };
