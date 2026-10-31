/* The ultra-detailed flow canvas (opened from a company page's "Detailed flow" section).
 *
 * Data: disclosures/app/flowdetail.py, each period's `u` — the company's own XBRL calculations as junctions (a total and its
 * parts), deeper than the detailed chart (notes four levels down, income tax fully, the cash flow statement's nested lines),
 * and its alternative views: revenue by every dimension whose members add up, the segments' own income statements
 * (ASU 2023-07: each segment's revenue → its significant expenses → its profit; the profits with what is not allocated make
 * the consolidated line), the cash flows by use (operating cash flow → capital spending → free cash flow → buybacks,
 * dividends, acquisitions, debt …), and stock pay inside the cost lines.
 *
 * build(u, opts) turns one period into the spec web/sankey.js draws, computing the flows here (the same rules as the
 * Python chart): every open junction's inflows fill its outflows in order; a junction's orientation is the root's times the
 * signs of the weights on the way to it; a closed junction leaves its total as one node with a + to open it. open(o) shows
 * the canvas: + / − on the nodes, the view switches, Q/Q, Y/Y and vs guidance, wheel / drag / pinch zoom.
 */
(function (global) {
  'use strict';
  const MAIN = {
    revenue: ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'SalesRevenueNet',
      'RevenuesNetOfInterestExpense', 'SalesRevenueGoodsNet', 'SalesRevenueServicesNet', 'RegulatedAndUnregulatedOperatingRevenue',
      'RegulatedOperatingRevenue', 'ElectricUtilityRevenue'],
    cor: ['CostOfRevenue', 'CostOfGoodsAndServicesSold', 'CostOfGoodsSold', 'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization'],
    gp: ['GrossProfit'], opex: ['OperatingExpenses'], costs: ['CostsAndExpenses', 'OperatingCostsAndExpenses', 'BenefitsLossesAndExpenses'],
    oi: ['OperatingIncomeLoss'], nonop: ['NonoperatingIncomeExpense'],
    pretax: ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
      'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
      'IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic', 'IncomeLossBeforeIncomeTaxes'],
    tax: ['IncomeTaxExpenseBenefit', 'IncomeTaxesPaidNet'],
    net: ['NetIncomeLoss', 'ProfitLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic', 'IncomeLossFromContinuingOperations'],
    ocf: ['NetCashProvidedByUsedInOperatingActivities', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
    icf: ['NetCashProvidedByUsedInInvestingActivities', 'NetCashProvidedByUsedInInvestingActivitiesContinuingOperations'],
    fincf: ['NetCashProvidedByUsedInFinancingActivities', 'NetCashProvidedByUsedInFinancingActivitiesContinuingOperations'],
    capex: ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'],
    da: ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet', 'DepreciationAndAmortization', 'Depreciation'],
    sbc: ['ShareBasedCompensation', 'AllocatedShareBasedCompensationExpense', 'ShareBasedPaymentArrangementNoncashExpense'],
    interest: ['InterestExpense', 'InterestExpenseNonoperating', 'InterestExpenseDebt', 'InterestExpenseNet'],
    cash_chg: ['CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect',
      'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect',
      'CashAndCashEquivalentsPeriodIncreaseDecrease', 'CashPeriodIncreaseDecrease'],
  };
  const MAIN_OF = {};
  Object.keys(MAIN).forEach((id) => MAIN[id].forEach((loc) => { if (!(loc in MAIN_OF)) MAIN_OF[loc] = id; }));
  const NAMES = { revenue: 'Revenue', gp: 'Gross profit', oi: 'Operating profit', pretax: 'Pre-tax earnings', net: 'Net earnings',
    ocf: 'Operating cash flow', icf: 'Investing activities', fincf: 'Financing activities', tax: 'Income tax', cor: 'Cost of revenue',
    opex: 'Operating expenses' };
  const SHORT = { fcf: 'free cash flow', capex: 'capital spending', da: 'D&A', sbc: 'stock pay', interest: 'interest expense', revenue: 'revenue', gp: 'gross profit', opex: 'opex', costs: 'costs', oi: 'operating profit', pretax: 'pre-tax', net: 'net earnings',
    ocf: 'OCF', cor: 'cost of revenue', tax: 'income tax', nonop: 'other income', icf: 'investing', fincf: 'financing', cash_chg: 'cash' };
  const AXIS_WORD = { 'srt:ProductOrServiceAxis': 'Products', 'us-gaap:StatementBusinessSegmentsAxis': 'Segments', 'srt:StatementGeographicalAxis': 'Regions' };
  const CHAIN = new Set(['revenue', 'gp', 'oi', 'pretax', 'net', 'ocf', 'costs', 'opex']);
  const FOLD = 0.001;            // parts under 0.1% of revenue are summed into "Other" (opened with +)
  const MAX_PARTS = 12;

  const local = (c) => c.split(':').pop();
  const concept = (k) => { let c = k.startsWith('cf>') ? k.slice(3) : k; return c.split('|')[0]; };
  function mainOf(k) {
    if (!k || k.includes('~') || /^(#|seg>)/.test(k)) return null;
    const c = k.startsWith('cf>') ? k.slice(3) : k;
    if (c.includes('|') || c.startsWith('seg>')) return null;
    return MAIN_OF[local(c)] || null;
  }
  const ENT = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };
  const dec = (s) => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, (m) => ENT[m]);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // ---------- the structure of one view ----------
  // → {J: {total: [[part, weight]]}, runs: [[total, σ]] beyond the root's, alias: {key: node key}, open: Set of junctions open
  // unless closed by the reader}
  function structure(u, o) {
    const J = Object.assign({}, u.J);
    const defOpen = new Set(u.default || []);
    const runs = [], alias = {};
    const ax = o.revAxis && u.alt && u.alt[o.revAxis] ? o.revAxis : u.axis;
    const segOn = o.costs === 'segments' && u.seg;
    // revenue by the chosen dimension (the segments' own view leaves the segment split to the right of revenue)
    if (ax !== u.axis || segOn) {
      Object.keys(J).forEach((t) => { if (String((u.via || {})[t] || '').startsWith('dims:')) delete J[t]; });
      const use = segOn && ax === 'us-gaap:StatementBusinessSegmentsAxis' ? Object.keys(u.alt || {}).find((a) => a !== ax) : ax;
      if (use && u.alt[use]) Object.entries(u.alt[use]).forEach(([t, kids]) => { J[t] = kids; defOpen.add(t); });
    }
    if (segOn) {
      Object.entries(u.seg.J).forEach(([t, kids]) => { J[t] = kids; defOpen.add(t); });
      alias[u.seg.rev] = u.seg.src;
      runs.push([u.seg.rev, -1]);                    // revenue → the segments
      if (J[u.seg.src]) runs.push([u.seg.src, 1]);   // what makes up revenue → revenue
    }
    if (o.cash === 'uses' && u.cash_uses && u.cash_root) {
      // the statement's sections give way to the groups by use (operating cash flow keeps its own lines)
      const ocf = (J[u.cash_root] || []).map(([k]) => k).find((k) => mainOf(k) === 'ocf');
      const drop = (k) => { if (k === ocf || !J[k]) return; const kids = J[k]; delete J[k]; kids.forEach(([x]) => drop(x)); };
      drop(u.cash_root);
      Object.entries(u.cash_uses.J).forEach(([t, kids]) => { J[t] = kids; if (t === u.cash_root || t === '#cat:fcf') defOpen.add(t); });
    }
    return { J, runs, alias, defOpen };
  }

  // ---------- the flows of one period ----------
  function flows(S, u, vals, R, isOpen, fold) {
    const J = S.J, links = new Map(), kind = new Map(), parent = new Map(), order = [], folded = new Map(), decided = {}, jx = [];
    const alias = S.alias;
    const nid = (k) => alias[k] || k;
    const weights = (X) => { const w = {}; (J[X] || []).forEach(([k, ww]) => { w[k] = ww; }); return w; };
    const v = (k) => {
      if (folded.has(k)) {
        const X = k.slice(0, k.lastIndexOf('~')), w = weights(X);
        let s = 0, any = false;
        folded.get(k).forEach((x) => { if (vals[x] != null) { s += vals[x] * (w[x] == null ? 1 : w[x]); any = true; } });
        return any ? s : null;
      }
      return vals[k] == null ? null : vals[k];
    };
    const kidsOf = (X) => {
      if (J[X]) return J[X];
      if (folded.has(X)) { const w = weights(X.slice(0, X.lastIndexOf('~'))); return folded.get(X).map((k) => [k, w[k] == null ? 1 : w[k]]); }
      return null;
    };
    const eps = 1e-9 * (R || 1);
    function fill(ins, outs) {
      ins = ins.map((x) => x.slice()); outs = outs.map((x) => x.slice());
      let i = 0, j = 0;
      while (i < ins.length && j < outs.length) {
        const a = Math.min(ins[i][1], outs[j][1]);
        if (a > eps) { const key = ins[i][0] + '\u0001' + outs[j][0]; links.set(key, (links.get(key) || 0) + a); }
        ins[i][1] -= a; outs[j][1] -= a;
        if (ins[i][1] <= eps) i++;
        if (outs[j][1] <= eps) j++;
      }
    }
    function foldOf(X, kids, sigma) {
      let rec = fold ? fold[X] : null;
      if (!fold) {
        const sides = { in: [], out: [] };
        kids.forEach(([k, w]) => { const a = sigma * w * v(k); sides[a > 0 ? 'in' : 'out'].push([k, Math.abs(a)]); });
        rec = {};
        Object.entries(sides).forEach(([side, lst]) => {
          lst.sort((a, b) => b[1] - a[1]);
          const small = lst.filter(([, a], i) => a < FOLD * (R || 1) || (lst.length > MAX_PARTS && i >= MAX_PARTS - 1)).map(([k]) => k);
          if (small.length >= 2) rec[side] = small;
        });
        if (Object.keys(rec).length) decided[X] = rec; else rec = null;
      }
      if (!rec) return kids;
      const gone = new Set();
      Object.entries(rec).forEach(([side, keys]) => { folded.set(`${X}~${side}`, keys); keys.forEach((k) => gone.add(k)); });
      const out = (J[X] || kids).filter(([k]) => !gone.has(k) && vals[k] != null && vals[k] !== 0);
      Object.keys(rec).forEach((side) => { const ok = `${X}~${side}`; if (v(ok)) out.push([ok, 1]); });
      return out;
    }
    function junction(X, sigma, depth, force) {
      if (depth > 16) return;
      const all = kidsOf(X);
      if (!all || (!force && !isOpen(X))) return;
      const vX = v(X);
      if (vX == null) return;
      const raw = all.filter(([k]) => v(k) != null && v(k) !== 0);
      const tot = raw.reduce((s, [k, w]) => s + w * v(k), 0);
      const tol = Math.max(Math.abs(vX) * 0.002, (R >= 1e9 ? 0.6e6 : 600) * (raw.length + 1));
      if (!raw.length || Math.abs(tot - vX) > tol) return;
      const kids = folded.has(X) ? raw : foldOf(X, raw, sigma);
      const terms = kids.map(([k, w]) => [k, sigma * w * v(k), w]);
      const Xn = nid(X), aX = sigma * -vX;
      const ins = terms.filter((t) => t[1] > 0).map(([k, a]) => [nid(k), a]).sort((a, b) => b[1] - a[1]);
      const outs = terms.filter((t) => t[1] < 0).map(([k, a]) => [nid(k), -a]);
      const main = ins.length ? ins[0][0] : null;
      if (aX > 0) ins.push([Xn, aX]); else if (aX < 0) outs.push([Xn, -aX]);
      if (!order.includes(Xn)) order.push(Xn);
      terms.slice().sort((a, b) => (a[1] < 0) - (b[1] < 0)).forEach(([k, a]) => {
        const kn = nid(k);
        if (!order.includes(kn)) order.push(kn);
        if (!kind.has(kn)) kind.set(kn, a > 0 ? 'src' : 'use');
      });
      const chain = main && (CHAIN.has(mainOf(main)) || /^(Revenue|Sales)/.test(local(concept(main))));   // a segment's revenue too
      terms.forEach(([k, a]) => {
        const kn = nid(k);
        if (parent.has(kn)) return;
        if (a < 0) parent.set(kn, aX > 0 || !chain ? Xn : main);
        else if (kn !== main || !J[k]) parent.set(kn, Xn);
      });
      if (aX < 0 && main && mainOf(X) !== 'revenue' && !parent.has(Xn)) {
        const mv = Math.abs(v(main) == null ? vX : v(main));
        if (Math.abs(vX) <= mv + eps) parent.set(Xn, main); else if (S.rev && S.rev !== Xn) parent.set(Xn, S.rev);
      }
      fill(ins, outs);
      jx.push([ins.map(([k]) => k), outs.map(([k]) => k), X]);
      kids.forEach(([k, w]) => {
        if (nid(k) === u.root && k !== X) return;
        junction(k, sigma * (w > 0 ? 1 : -1), depth + 1, false);
      });
    }
    order.push(u.root);
    kind.set(u.root, (v(u.root) || 0) >= 0 ? 'src' : 'use');
    junction(u.root, 1, 0, true);
    if (u.cash_root) {
      if (u.cash_ni && u.cash_ni !== u.root) alias[u.cash_ni] = u.root;
      junction(u.cash_root, 1, 0, true);
      // the cash flows by section or by use did not add up this quarter: operating cash flow on its own still does
      const ocfKey = Object.keys(J).find((k) => mainOf(k) === 'ocf');
      if (ocfKey && ![...links.keys()].some((key) => key.split('\u0001').includes(ocfKey))) junction(ocfKey, 1, 0, true);
    }
    S.runs.forEach(([X, sg]) => junction(X, sg, 0, true));
    return { links, kind, parent, order, folded, decided, jx, v, kidsOf };
  }

  // ---------- figures ----------
  function money(v, unit) {
    if (v == null) return 'n/a';
    const a = Math.abs(v), sign = v < 0 ? '−' : '';
    if (a >= 0.95e12) return `${sign}$${(a / 1e12).toFixed(2)}T`;
    if (unit === 'B' && a >= 5e6) { const b = a / 1e9; return `${sign}$${b >= 0.95 ? b.toFixed(1) : b.toFixed(2)}B`; }
    const m = a / 1e6;
    return m >= 0.95 ? `${sign}$${m.toLocaleString('en-US', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}M` : `${sign}$${Math.round(a / 1e3).toLocaleString('en-US')}K`;
  }
  const pct = (a, b) => (a == null || b == null ? '—' : a <= 0 || b <= 0 ? 'n/m' : (() => { const g = Math.round((a / b - 1) * 100); return (g > 0 ? '+' : g < 0 ? '−' : '') + Math.abs(g) + '%'; })());
  const share = (v, p) => (!p || v == null || p <= 0 ? null : (() => { const s = v / p * 100; return s < 10 ? s.toFixed(1) + '%' : Math.round(s) + '%'; })());
  function delta(n, p, attr, missing, unit) {
    if (n[attr] == null) return `Δ n/a (${missing})`;
    const d = n.v - n[attr];
    let txt = `Δ ${d > 0 ? '+' : d < 0 ? '−' : '±'}${money(Math.abs(d), unit)}`;
    if (p && p !== n && p[attr] != null) {
      const c0 = n[attr], c1 = n.v, p0 = p[attr], p1 = p.v;
      if (p0 > 0 && p1 > 0 && c0 >= 0 && c1 >= 0) {
        const f = (x) => { const y = x / (unit === 'B' ? 1e9 : 1e6); return (x > 0 ? '+' : x < 0 ? '−' : '±') + (Math.abs(y) >= 0.95 ? Math.abs(y).toFixed(1) : Math.abs(y).toFixed(2)); };
        txt += ` · scale ${f((p1 - p0) * c0 / p0)} · mix ${f(p1 * (c1 / p1 - c0 / p0))}`;
      } else txt += ' · scale/mix n/m';
    }
    return txt;
  }

  // ---------- one period → the spec web/sankey.js draws ----------
  // opts: {revAxis, costs: 'accounts' | 'segments', cash: 'statement' | 'uses', opened: Set, closed: Set, annual}
  function build(u, opts) {
    const o = opts || {};
    const S = structure(u, o);
    const now = u.now || {}, q = u.q, y = u.y;
    const rev = Object.keys(S.J).find((k) => mainOf(k) === 'revenue' && now[k] != null) ||
      Object.values(S.J).flat().map(([k]) => k).find((k) => mainOf(k) === 'revenue' && now[k] != null) ||
      (u.seg && o.costs === 'segments' && now[u.seg.src] != null ? u.seg.src : null) ||
      Object.keys(now).find((k) => mainOf(k) === 'revenue');
    S.rev = rev;
    const R = Math.abs((rev && now[rev]) || 0);
    const opened = o.opened || new Set(), closed = o.closed || new Set();
    const isOpen = (X) => !!o.all || (S.defOpen.has(X) && !closed.has(X)) || opened.has(X);
    const fl = flows(S, u, now, R, isOpen, null);
    if (u.seg && o.costs === 'segments') (u.seg.J[u.seg.rev] || []).forEach(([k]) => { if (!k.startsWith('#gap:')) fl.parent.set(k, u.seg.src); });
    let fq = q ? flows(S, u, q, R, isOpen, fl.decided) : null;
    let fy = y ? flows(S, u, y, R, isOpen, fl.decided) : null;
    const unit = R >= 1e9 ? 'B' : 'M';
    const ins = new Map(), outs = new Map();
    const pairs = [...fl.links.keys()].map((k) => k.split('\u0001'));
    pairs.forEach(([s, t]) => { (outs.get(s) || outs.set(s, []).get(s)).push(t); (ins.get(t) || ins.set(t, []).get(t)).push(s); });
    const nodeV = (f, k) => {
      if (!f) return null;
      let a = 0, b = 0;
      f.links.forEach((v, key) => { const [s, t] = key.split('\u0001'); if (t === k) a += v; if (s === k) b += v; });
      return a || b ? Math.max(a, b) : null;
    };
    const keys = fl.order.filter((k) => ins.has(k) || outs.has(k));
    // columns: in each junction the inflows one column before the outflows; the cash flows after the income statement
    const col = new Map([[u.root, 0]]);
    const cashJ = (a, b) => a.concat(b).some((k) => k.startsWith('cf>') || k.startsWith('#cat:') || mainOf(k) === 'ocf');
    function settle(js, shift) {
      for (let pass = 0; pass < js.length + 2; pass++) {
        let ch = false;
        js.forEach(([a, b]) => {
          const ab = a.concat(b);
          const wide = a.includes(u.root) && ab.some((k) => mainOf(k) === 'ocf');
          const sect = !wide && ab.some((k) => mainOf(k) === 'ocf') && u.cash_root && ab.includes(u.cash_root);
          const off = {};
          if (wide) ab.forEach((k) => { off[k] = k === u.root ? 0 : mainOf(k) === 'ocf' ? 2 + shift : 1 + shift; });
          else if (sect) ab.forEach((k) => { off[k] = mainOf(k) === 'ocf' ? 0 : 1; });
          else { a.forEach((k) => { off[k] = 0; }); b.forEach((k) => { off[k] = 1; }); }
          const known = ab.find((k) => col.has(k));
          if (known === undefined) return;
          const base = col.get(known) - off[known];
          ab.forEach((k) => { if (!col.has(k)) { col.set(k, base + off[k]); ch = true; } });
        });
        if (!ch) break;
      }
    }
    settle(fl.jx.filter(([a, b]) => !cashJ(a, b)), 0);
    settle(fl.jx.filter(([a, b]) => cashJ(a, b)), Math.max(0, Math.max(...col.values()) - col.get(u.root)));
    keys.forEach((k) => { if (!col.has(k)) col.set(k, 0); });
    const lo = Math.min(...keys.map((k) => col.get(k)));
    const used = [...new Set(keys.map((k) => col.get(k) - lo))].sort((a, b) => a - b);
    const remap = new Map(used.map((c, i) => [c, i]));       // no empty columns
    const into = new Set();
    const stack = rev ? [rev] : [];
    while (stack.length) { const x = stack.pop(); (ins.get(x) || []).forEach((s) => { if (!into.has(s)) { into.add(s); stack.push(s); } }); }
    if (u.seg && o.costs === 'segments') {                  // the segments' revenue (to the right of revenue) is revenue too
      Object.values(u.seg.J).forEach((kids) => kids.forEach(([k]) => { if (u.seg.J[u.seg.rev].some(([x]) => x === k)) into.add(k); }));
    }
    const ocf = keys.find((k) => mainOf(k) === 'ocf');
    const color = (k) => {
      if (k === rev || into.has(k)) return 'rev';
      const kd = fl.kind.get(k) || 'src';
      if ((k.startsWith('cf>') || k.startsWith('#cat:')) && k !== ocf && mainOf(k) !== 'cash_chg') return kd === 'use' ? 'cost' : k === '#cat:fcf' ? 'profit' : 'noncash';
      return kd === 'src' ? 'profit' : 'cost';
    };
    const lab = u.labels || {};
    const ids = new Map(), byk = new Map(), nodes = [];
    const nameOf = (k) => {
      if (k.includes('~')) return `Other (${(fl.folded.get(k) || []).length} items)`;
      const m = mainOf(k);
      let name = NAMES[m] || lab[k] || local(concept(k));
      if (m === 'net' && concept(k).endsWith('ProfitLoss')) name = 'Net earnings (incl. minority interests)';
      if (m === 'cash_chg') name = (now[k] || 0) > 0 ? 'Added to cash' : 'Drawn from cash';
      if (k === '#cat:fcf') name = 'Free cash flow';
      return name;
    };
    const toggles = new Map();                              // node id → '+' (closed, can open) | '−' (open, can close)
    keys.forEach((k) => {
      const m = mainOf(k);
      // the main lines keep the standard chart's ids (the guidance finds them by id); free cash flow and capital spending
      // by use too
      const mm = m || (k === '#cat:fcf' ? 'fcf' : k === '#cat:capex' ? 'capex' : null);
      const i = mm && ![...ids.values()].includes(mm) ? mm : (k.includes('~') ? 'o:' : 'k:') + k;
      ids.set(k, i);
      const name = nameOf(k);
      const short = name.length <= 56 ? name : name.slice(0, 54).replace(/\s+\S*$/, '').replace(/[,;:–-]$/, '') + ' …';
      const n = { id: i, key: k, col: remap.get(col.get(k) - lo), color: color(k), name: esc(short), full: short !== name ? name : null,
        pos: !ins.has(k) ? 'left' : !outs.has(k) ? 'right' : fl.kind.get(k) === 'src' ? 'above' : 'below',
        v: nodeV(fl, k), q: nodeV(fq, k), y: nodeV(fy, k) };
      const canOpen = !!fl.kidsOf(k) && (fl.kidsOf(k) || []).length > 0;
      const isO = isOpen(k) && pairs.some(([s, t]) => (s === k || t === k) && fl.jx.some((jj) => jj[2] === k));
      if (canOpen && !isOpen(k)) toggles.set(i, '+');
      else if (canOpen && isO && k !== u.root && !CHAIN.has(m) && k !== u.cash_root && !k.startsWith('seg>') &&
        !(o.costs === 'segments' && u.seg && u.seg.J[k]) && k !== '#cat:fcf') toggles.set(i, '−');   // the view's own skeleton stays
      nodes.push(n);
      byk.set(k, n);
    });
    // stock pay (and amortization) inside the cost lines: a line in the label, the band into the line lined
    const ofv = new Map();
    Object.entries(u.of || {}).forEach(([k, d]) => {
      const n = byk.get(k);
      if (!n) return;
      const sbc = d.sbc && now[d.sbc], am = d.amort && now[d.amort];
      if (sbc || am) ofv.set(k, { sbc: sbc || 0, amort: am || 0 });
    });
    const links = pairs.map(([s, t]) => {
      const key = s + '\u0001' + t, L = { s: byk.get(s).id, t: byk.get(t).id, v: fl.links.get(key), q: fq ? fq.links.get(key) : null, y: fy ? fy.links.get(key) : null, color: byk.get(t).color };
      const of = ofv.get(t);
      if (of && byk.get(t).v > 0) L.of = Math.min(1, of.sbc / byk.get(t).v);
      return L;
    });
    byk.forEach((n, k) => {
      const pk = fl.parent.get(k), p = byk.get(pk);
      const lines = [[n.id === 'revenue' ? 'big' : n.id === 'ocf' ? 'ocf' : 'name', n.name]];
      let val = money(n.v, unit);
      if (p && p !== n) { const s = share(n.v, p.v); if (s && n.v <= p.v * 1.0005) val += ` · ${s} of ${SHORT[p.id] || esc((lab[pk] || dec(p.name) || '').toLowerCase().slice(0, 30))}`; }
      lines.push(['val', val]);
      lines.push(['mut', `Y/Y ${pct(n.v, n.y)}` + (o.annual ? '' : ` · Q/Q ${pct(n.v, n.q)}`)]);
      if (k.includes('~')) { const parts = fl.folded.get(k) || []; lines.push(['mut', esc(parts.slice(0, 2).map((x) => lab[x] || local(concept(x))).join(', ') + (parts.length > 2 ? ' …' : ''))]); }
      const of = ofv.get(k);
      if (of) lines.push(['mut', [of.sbc ? `stock pay ${money(of.sbc, unit)} (${share(of.sbc, n.v) || '—'})` : '', of.amort ? `amortization ${money(of.amort, unit)}` : ''].filter(Boolean).join(' · ') + ' inside']);
      n.lines = lines;
      n.cmp = delta(n, p, 'q', 'no prior quarter', unit);
      n.cmp_y = delta(n, p, 'y', o.annual ? 'no prior year' : 'no year-ago quarter', unit);
      const via = (u.via || {})[k] || (u.seg && u.seg.J[k] ? 'the segment note' : k.startsWith('#cat:') ? 'the cash flow statement (grouped by use)' : null);
      const src = [];
      if (n.full) src.push(n.full + '.');
      if (k.includes('~')) src.push('Small parts summed here: ' + (fl.folded.get(k) || []).map((x) => `${lab[x] || local(concept(x))} ${money(Math.abs(now[x] || 0), unit)}`).join('; ') + '.');
      else if (k.startsWith('#gap:')) src.push('What the split leaves of the total (not assigned to a member or segment).');
      else if (!k.startsWith('#') && !k.startsWith('seg>')) src.push('XBRL: ' + concept(k) + (k.includes('|') ? ' · ' + k.split('|').slice(1).map((d) => d.split('=').map((x) => x.split(':').pop()).join(' = ')).join(' · ') : '') + '.');
      if (via && fl.jx.some((jj) => jj[2] === k)) src.push(String(via).startsWith('dims:') ? `Split by the filing’s ${(AXIS_WORD[via.slice(5)] || 'members').toLowerCase()}.` : `Split by “${dec(via)}”.`);
      if (of) src.push(`Inside it, from the notes: stock-based pay ${money(of.sbc, unit)}${of.amort ? `, amortization of acquired intangibles ${money(of.amort, unit)}` : ''}.`);
      n.source = esc(src.join(' '));
      if (!k.includes('|') && concept(k).startsWith('us-gaap:') && !k.includes('~')) n.tag = concept(k);
    });
    return { nodes, links, toggles, keys: new Map([...byk].map(([k, n]) => [n.id, k])), segOn: !!(u.seg && o.costs === 'segments') };
  }

  // the views a period offers (for the switches)
  function views(u) {
    return {
      rev: Object.keys((u && u.alt) || {}).map((a) => [a, AXIS_WORD[a] || a.split(':').pop()]),
      seg: !!(u && u.seg), segMembers: u && u.seg ? u.seg.members.length : 0,
      cash: !!(u && u.cash_uses && u.cash_root),
    };
  }

  // ---------- what the company says ahead (pipeline/outlook.py: the MD&A's and the earnings release's statements) ----------
  // each statement goes to the line it names (a segment, a cost line …), else to the line of its topic
  const TOPIC_LINES = { demand: ['revenue'], backlog: ['revenue'], ai: ['revenue'], products: ['revenue'], macro: ['revenue'], margin: ['gp', 'oi'],
    costs: ['opex', 'costs', 'cor'], supply: ['cor', 'costs'], capex: ['capex'], returns: ['#cat:buyback', '#cat:dividend'], financing: ['#cat:debt'],
    tax: ['tax'], people: ['opex', 'costs'], deals: ['#cat:acq'], regulation: [], other: [] };
  const GENERIC = /^(revenue|other|net|total|cost|costs|expenses?|income|operating|profit|gross profit|operating profit|net earnings|pre-tax earnings)$/i;
  function outlookOn(ol, sp) {
    const out = new Map();
    if (!ol || !ol.docs || !sp) return out;
    const docs = [ol.docs.find((d) => d.kind === 'mdna'), ol.docs.find((d) => d.kind === 'release')].filter(Boolean);
    const named = sp.nodes.map((n) => [n, dec(n.full || n.name).replace(/\s*·.*$/, '').replace(/\s*\(.*\)$/, '').trim()])
      .filter(([n, nm]) => nm.length >= 4 && !GENERIC.test(nm) && !/^Other \(/.test(nm) && !n.id.startsWith('o:'))
      .sort((a, b) => b[1].length - a[1].length);
    const byKey = new Map(sp.nodes.map((n) => [n.key, n])), byId = new Map(sp.nodes.map((n) => [n.id, n]));
    docs.forEach((d) => (d.statements || []).forEach((x) => {
      if (!x || !x.t || x.status === 'dropped') return;
      const low = x.t.toLowerCase();
      let n = (named.find(([, nm]) => low.includes(nm.toLowerCase())) || [])[0];
      if (!n) { const ids = TOPIC_LINES[x.topic] || []; for (const id of ids) { n = byId.get(id) || byKey.get(id); if (n) break; } }
      if (!n) return;
      if (!out.has(n.id)) out.set(n.id, []);
      out.get(n.id).push({ t: x.t, tone: x.tone, hedge: x.hedge, status: x.status, when: x.when, src: d.kind === 'mdna' ? `${d.form} MD&A` : 'earnings release', filed: d.filed });
    }));
    return out;
  }

  // the lines that moved most (the comparison's notes under the chart)
  function movers(sp, attr) {
    const unit = Math.max(...sp.nodes.map((n) => n.v || 0)) >= 1e9 ? 'B' : 'M';
    return sp.nodes.filter((n) => n[attr] != null && n.v != null && n.id !== 'revenue').sort((a, b) => Math.abs(b.v - b[attr]) - Math.abs(a.v - a[attr])).slice(0, 4)
      .map((n) => { const d = n.v - n[attr]; return `${dec(n.name)}: ${money(n.v, unit)}, ${d >= 0 ? '+' : '−'}${money(Math.abs(d), unit)} (${pct(n.v, n[attr])})`; });
  }

  // the guidance to draw the next period from: the latest release's items and, for the same periods, the figures of a newer
  // 10-Q / 10-K outlook (it restates or updates them)
  function guidanceDoc(src) {
    if (!src) return null;
    const g = src.g ? Object.assign({}, src.g, { items: (src.g.items || []).slice() }) : null;
    const newer = ((src.hist && src.hist.releases) || []).filter((r) => r.src && r.src !== '8-K' && (!g || !g.filed || r.filed >= g.filed));
    if (!g && !newer.length) return null;
    const out = g || { items: [], filed: newer[0].filed, label: null };
    newer.slice().reverse().forEach((r) => (r.items || []).forEach((it) => {
      const k = `${it.metric}|${it.basis || ''}|${it.period}`;
      out.items = out.items.filter((x) => `${x.metric}|${x.basis || ''}|${x.period}` !== k);
      out.items.push(Object.assign({}, it, { src: r.src }));
    }));
    return out;
  }

  // a fourth quarter guided for revenue while a cash line is guided only for the year (Amazon: capital spending for 2026):
  // the year's figure less the three quarters reported, read from this company's own quarters on the canvas
  function impliedQ4(g, base, company) {
    const FG = global.FFGuidance;
    if (!FG || !FG.target) return g;
    const tg = FG.target(g, base, company);
    const m = tg && /^Q4 (?:FY)?(\d{4})$/.exec(tg.period || '');
    if (!m) return g;
    const fyLabel = `FY${m[1]}`;
    const qs = (company._doc || []).filter((p) => p.u && p.fq >= 1 && p.fq <= 3).sort((a, b) => (a.end < b.end ? 1 : -1)).slice(0, 3);
    if (qs.length !== 3 || new Set(qs.map((p) => p.fq)).size !== 3) return g;
    const lineOf = (p, metric) => {
      const now = p.u.now || {}, keys = Object.keys(now);
      if (metric === 'capex') return now['#cat:capex'] != null ? -now['#cat:capex'] : (now[keys.find((k) => mainOf(k) === 'capex')] || null);
      if (metric === 'ocf') return now[keys.find((k) => mainOf(k) === 'ocf')] || null;
      if (metric === 'fcf') return now['#cat:fcf'] != null ? now['#cat:fcf'] : null;
      if (metric === 'da') return now[keys.find((k) => mainOf(k) === 'da' && k.startsWith('cf>'))] || null;
      if (metric === 'sbc') return now[keys.find((k) => mainOf(k) === 'sbc' && k.startsWith('cf>'))] || null;
      return null;
    };
    const items = g.items.slice();
    ['capex', 'ocf', 'fcf', 'da', 'sbc'].forEach((metric) => {
      if (items.some((it) => it.metric === metric && it.period === tg.period)) return;
      const fy = items.find((it) => it.metric === metric && it.unit === 'usd' && it.period === fyLabel && it.lo != null);
      if (!fy) return;
      const done = qs.map((p) => lineOf(p, metric));
      if (done.some((v) => v == null)) return;
      const ytd = done.reduce((a, b) => a + b, 0);
      const lo = fy.lo - ytd, hi = (fy.hi == null ? fy.lo : fy.hi) - ytd;
      if (!(hi > 0)) return;
      items.push(Object.assign({}, fy, { period: tg.period, lo, hi, approx: fy.approx, ends: `implied: ${fyLabel} guidance less three quarters` }));
    });
    return Object.assign({}, g, { items });
  }

  // ---------- the next period as guided, in this detail ----------
  // web/guidance.js projects the drawn chart (the guided lines at their midpoints, every other line at its share of its
  // parent). Here that projection becomes values for every line of the period (a line not drawn moves with the drawn line it
  // sits in), the cash lines the company guided are set (capital spending, operating and free cash flow, D&A, stock-based
  // pay), every total is summed again and the flows are built anew: free cash flow can turn from a gap into a surplus, and
  // the cash drawn or added is what the other lines leave.
  function guidedValues(u, o, sp0, r, items, period, cs) {
    const S = structure(u, o);
    const J = S.J, now = u.now || {};
    const rv = new Map(r.nodes.map((n) => [n.id, +n.v]));
    const rho = new Map();
    sp0.nodes.forEach((n) => {
      const k = sp0.keys.get(n.id);
      if (k && n.v > 0) rho.set(k, rv.has(n.id) ? rv.get(n.id) / n.v : 0);
    });
    Object.entries(S.alias).forEach(([a, b]) => { if (rho.has(b) && !rho.has(a)) rho.set(a, rho.get(b)); });
    if (u.cash_ni && u.cash_ni !== u.root && rho.has(u.root) && !rho.has(u.cash_ni)) rho.set(u.cash_ni, rho.get(u.root));
    const parent = new Map();
    Object.entries(J).forEach(([t, kids]) => kids.forEach(([k]) => { if (!parent.has(k)) parent.set(k, t); }));
    // the cash lines stay as in the period on file unless guided (net earnings come in as projected; the cash drawn or added
    // is the balance)
    const cashLine = (k) => (k.startsWith('cf>') || k.startsWith('#cat:')) && k !== u.cash_ni;
    const ratio = (k, d) => (cashLine(k) ? 1 : rho.has(k) ? rho.get(k) : (d || 0) < 24 && parent.has(k) ? ratio(parent.get(k), (d || 0) + 1) : 1);
    const vals = {};
    Object.keys(now).forEach((k) => { vals[k] = now[k] * ratio(k); });
    Object.entries(u.of || {}).forEach(([k, d]) => [d.sbc, d.amort].forEach((x) => {
      if (x && now[x] != null && !parent.has(x) && !rho.has(x)) vals[x] = now[x] * ratio(k);
    }));
    const R0 = Math.max(0, ...sp0.nodes.map((n) => +n.v || 0));
    // every total that added up in the filing is summed again (what it did not itemize moves with it)
    function resum() {
      const done = new Set(), busy = new Set();
      const go = (t) => {
        if (done.has(t) || busy.has(t) || !J[t]) return;
        busy.add(t);
        J[t].forEach(([k]) => go(k));
        busy.delete(t); done.add(t);
        if (now[t] == null) return;
        const kids = J[t].filter(([k]) => now[k] != null);
        if (!kids.length) return;
        const s0 = kids.reduce((a, [k, w]) => a + w * now[k], 0);
        const tol = Math.max(Math.abs(now[t]) * 0.002, (R0 >= 1e9 ? 0.6e6 : 600) * (kids.length + 1));
        if (Math.abs(s0 - now[t]) > tol) return;
        vals[t] = kids.reduce((a, [k, w]) => a + w * (vals[k] || 0), 0) + (now[t] - s0) * ratio(t);
      };
      Object.keys(J).forEach(go);
      if (u.cash_ni && u.cash_ni !== u.root && now[u.cash_ni] != null && now[u.root] != null) vals[u.cash_ni] = vals[u.root] + (now[u.cash_ni] - now[u.root]);
    }
    resum();
    resum();
    const pick = (m) => {
      const xs = (items || []).filter((it) => it.metric === m && it.period === period && it.unit === 'usd' && it.lo != null && it.basis !== 'non-GAAP');
      return xs.find((x) => x.basis === 'GAAP') || xs.find((x) => !x.basis) || null;
    };
    // the point of the range the scenario draws (web/guidance.js pointOf: the midpoint, or the low / high case)
    const FG0 = global.FFGuidance;
    const midOf = (it) => (FG0 && FG0.pointOf ? FG0.pointOf(it, it.metric, cs) : (it.lo + (it.hi == null ? it.lo : it.hi)) / 2);
    const keyOf = (m) => Object.keys(now).find((k) => k.startsWith('cf>') && mainOf(k) === m && now[k] != null);
    const guided = {};
    const sgn = (x) => (x < 0 ? -1 : 1);
    ['da', 'sbc'].forEach((m) => {
      const it = pick(m), k = keyOf(m);
      if (it && k && midOf(it) > 0) { vals[k] = sgn(now[k]) * midOf(it); guided[k] = it; }
    });
    resum();
    // capital spending: the group by use (net of what sales of equipment bring in), else the purchases line
    const catKids = (u.cash_uses && u.cash_uses.J && u.cash_uses.J['#cat:capex']) || null;
    const capKey = keyOf('capex');
    const capNow = () => {
      if (catKids) return -catKids.reduce((a, [k, w]) => a + w * (vals[k] || 0), 0);
      return capKey ? Math.abs(vals[capKey]) : null;
    };
    const setCapex = (C, it) => {
      if (!(C > 0)) return false;
      if (catKids) {
        const net0 = -catKids.reduce((a, [k, w]) => a + w * (now[k] || 0), 0);
        if (!(net0 > 0)) return false;
        catKids.forEach(([k]) => { if (now[k] != null) vals[k] = now[k] * C / net0; });
        guided['#cat:capex'] = it;
        if (capKey) guided[capKey] = it;
      } else if (capKey) { vals[capKey] = sgn(now[capKey]) * C; guided[capKey] = it; } else return false;
      return true;
    };
    const ocfKey = keyOf('ocf');
    const setOcf = (O, it) => {
      if (!ocfKey || !J[ocfKey] || O == null) return false;
      const skip = new Set([u.cash_ni, u.root, ...Object.keys(guided)]);
      const adj = J[ocfKey].filter(([k]) => !skip.has(k) && vals[k] != null && vals[k] !== 0);
      const A = adj.reduce((a, [k, w]) => a + Math.abs(w * vals[k]), 0);
      const delta = O - vals[ocfKey];
      if (A > 0) adj.forEach(([k, w]) => { vals[k] += delta * Math.abs(w * vals[k]) / A / w; });
      resum();
      vals[ocfKey] = O;
      if (it) guided[ocfKey] = it;
      return true;
    };
    const itC = pick('capex'), itO = pick('ocf'), itF = pick('fcf');
    if (itC) setCapex(midOf(itC), itC);
    resum();
    if (itO) setOcf(midOf(itO), itO);
    else if (itF && capNow() != null) setOcf(midOf(itF) + capNow(), null);
    resum();
    if (itF && itO && !itC) setCapex(midOf(itO) - midOf(itF), null);
    resum();
    if (itF) guided['#cat:fcf'] = itF;
    return { vals, guided };
  }

  // the canvas spec of the next period as guided: r is web/guidance.js's projection of sp0 (the period on the canvas)
  function guidedFlows(p, o, sp0, r, g, period, ago, cs) {
    const FG = global.FFGuidance;
    const { vals, guided } = guidedValues(p.u, o, sp0, r, g.items, period, cs);
    const u1 = Object.assign({}, p.u, { now: vals, q: o.annual ? null : p.u.now, y: o.annual ? p.u.now : ago || null });
    const sp = build(u1, o);
    const rById = new Map(r.nodes.map((n) => [n.id, n]));
    const base = dec(r.base || '');
    const fROLE = (c) => 'f_' + (c === 'rev' || c === 'profit' ? c : 'cost');
    const isG = new Set();
    sp.nodes.forEach((n) => {
      const k = sp.keys.get(n.id), rn = rById.get(n.id), it = guided[k];
      if (rn && rn.gnote && rn.gnote.guided && !it) {
        n.color = rn.color; n.range = rn.range; n.gnote = rn.gnote;
        n.lines = n.lines.concat(rn.lines.slice(3));
        isG.add(n.id);
      } else if (it) {
        const w = FG && FG.words ? FG.words(it) : [];
        n.color = fROLE(n.color);
        n.lines.push([it.change === 'lowered' || it.change === 'withdrawn' ? 'gdn' : it.change === 'raised' ? 'gup' : 'gnt',
          esc(`guided ${FG && FG.range ? FG.range(it) : ''}${w.length ? ' · ' + w.join(' · ') : ''}`)]);
        if (it.hi != null && it.hi > it.lo) n.range = [it.lo, it.hi];
        n.gnote = { guided: true, item: it };
        isG.add(n.id);
      } else {
        const m = mainOf(k);
        const was = rn && (rn.lines.find((l) => l[0] === 'gas') || [])[1];
        const v0 = (p.u.now || {})[k];
        const same = v0 != null && Math.abs((vals[k] || 0) - v0) <= Math.abs(v0) * 0.001;
        const txt = m === 'cash_chg' ? 'the balance: what the other cash lines leave'
          : k === '#cat:fcf' ? 'operating cash flow less capital spending'
          : m === 'ocf' ? `net earnings as projected, the other items as in ${esc(base)}`
          : same && (k.startsWith('cf>') || k.startsWith('#cat:')) ? `assumed: as in ${esc(base)}`
          : was || (same ? `assumed: as in ${esc(base)}` : 'follows from the lines guided');
        n.lines.push(['gas', txt]);
        n.gnote = { guided: false };
      }
    });
    sp.links.forEach((l) => { if (isG.has(l.t)) l.color = fROLE(l.color); });
    const subtitle = String(r.subtitle || '').replace(/\d+ guided lines?/, `${isG.size} guided line${isG.size === 1 ? '' : 's'}`);
    return { sp, spec: Object.assign({}, r, { nodes: sp.nodes, links: sp.links, subtitle }) };
  }

  // ---------- the canvas ----------
  // o: {doc (public/c/<TICKER>.json), fy, end (the period on the page), name, labelOf(end, fy), guidance() → Promise of
  //     web/guidance.js sources, periods (the site's numbering, for vs guidance), slug}
  function open(o) {
    const S = global.Sankey;
    if (!S || !o || !o.doc) return null;
    const list = (o.fy ? o.doc.years : o.doc.quarters) || [];
    const near = (a, b) => a && b && Math.abs(Date.parse(a) - Date.parse(b)) <= 6 * 864e5;
    let idx = Math.max(0, list.findIndex((x) => near(x.end, o.end)));
    const st = { revAxis: null, costs: 'accounts', cash: 'statement', opened: new Set(), closed: new Set(), all: false, cmp: '', guide: false, next: false, says: true, case: 'mid' };
    let vb = null, scene = null, sel = null, src = null, srcP = null;
    const el = document.createElement('div');
    el.className = 'ffu';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-label', 'Ultra-detailed flow');
    el.innerHTML = `<div class="ffu-bar">
        <b class="ffu-title"></b>
        <label class="ffu-per">Period <select data-per>${list.map((x, i) => `<option value="${i}">${esc(o.labelOf(x.end, o.fy))}</option>`).join('')}</select></label>
        <span class="ffu-seg" data-g="rev"></span>
        <span class="ffu-seg" data-g="costs"><span>Costs</span><button type="button" data-costs="accounts">By account</button><button type="button" data-costs="segments">By segment</button></span>
        <span class="ffu-seg" data-g="cash"><span>Cash</span><button type="button" data-cash="statement">As filed</button><button type="button" data-cash="uses">By use</button></span>
        <span class="ffu-seg"><button type="button" data-cmp="">Now</button><button type="button" data-cmp="q">vs prior quarter</button><button type="button" data-cmp="y">vs year ago</button></span>
        <button type="button" class="ffu-btn" data-guide title="This period against the guidance it was given (the cash lines too)">◆ vs guidance</button>
        <button type="button" class="ffu-btn" data-next title="The next period as the company guided it (earnings release and 10-Q / 10-K outlook), drawn in this detail: guided lines in violet, the rest at today’s shares">◇ Next period as guided</button>
        <span class="ffu-seg" data-g="case" hidden title="The guided ranges: the low case takes the end of every range that leaves less profit (revenue and margins low, costs and capital spending high), the high case the other end"><span>Case</span><button type="button" data-case="low">Low</button><button type="button" data-case="mid">Mid</button><button type="button" data-case="high">High</button></span>
        <button type="button" class="ffu-btn" data-says title="What the company says ahead (its MD&amp;A and earnings release), pinned to the line each statement is about">💬 Outlook</button>
        <button type="button" class="ffu-btn" data-all>Open everything</button>
        <button type="button" class="ffu-btn" data-std>Back to detailed</button>
        <span class="ffu-seg"><button type="button" data-z="out" aria-label="Zoom out">−</button><button type="button" data-z="fit">Fit</button><button type="button" data-z="in" aria-label="Zoom in">+</button></span>
        <button type="button" class="ffu-btn" data-png>PNG</button>
        <button type="button" class="ffu-btn ffu-close" data-close aria-label="Close">✕</button>
      </div>
      <div class="ffu-stage"><div class="ffu-svg"></div><aside class="ffu-info" hidden></aside><p class="ffu-msg" hidden></p></div>
      <div class="ffu-hint">Click <b>+</b> on a line to open its parts, <b>−</b> to close them · drag to move · wheel or pinch to zoom · Esc to close</div>`;
    const $ = (q) => el.querySelector(q), $$ = (q) => [...el.querySelectorAll(q)];
    const stage = $('.ffu-stage'), host = $('.ffu-svg'), info = $('.ffu-info'), msg = $('.ffu-msg');
    const per = () => list[idx];

    function specOf(p, opts) {
      const sp = build(p.u, Object.assign({ annual: !!o.fy }, opts));
      return { sp, spec: { nodes: sp.nodes, links: sp.links, end: p.end, label: o.labelOf(p.end, o.fy), period: o.fy ? 'fy' : undefined, filed: p.filed } };
    }
    function current() {
      const p = per();
      const { sp, spec } = specOf(p, st);
      const lab = o.labelOf(p.end, o.fy), name = o.name;
      const prev = p.q_end ? o.labelOf(p.q_end, false) : null;
      const yAgo = new Date(Date.parse(p.end) - 364 * 864e5).toISOString().slice(0, 10);
      const yl = o.labelOf(yAgo, o.fy);
      const v = views(p.u);
      Object.assign(spec, {
        dense: true, title: `${name} ${lab} — ultra-detailed flow`,
        subtitle: `${o.fy ? 'Fiscal year' : 'Quarter'} ended ${p.end} · ${st.costs === 'segments' && v.seg ? 'costs by segment (the segment note)' : 'costs by account'} · ${st.cash === 'uses' && v.cash ? 'cash by use' : 'cash as filed'} · GAAP · XBRL of the ${p.form || 'filing'} and its notes`,
        footer: ['Each total and its parts are the company’s own calculation in its XBRL — the statements, the notes that split a line further, revenue by the filing’s own members, each segment’s revenue, significant expenses and profit (ASU 2023-07). Parts under 0.1% of revenue are summed as Other.',
          'Lines marked + have parts not drawn; open them on the canvas.'],
        compare: prev ? { vs: prev, title: `${name} ${lab} vs ${prev}: what changed (ultra-detailed)`, bullets: movers(sp, 'q') } : null,
        compare_y: p.has_y ? { vs: yl, title: `${name} ${lab} vs ${yl}: what changed (ultra-detailed)`, bullets: movers(sp, 'y') } : null,
      });
      return { sp, spec };
    }
    function sync() {
      const p = per(), v = views(p.u);
      $('.ffu-title').textContent = `${o.name} · ultra-detailed`;
      const rg = $('[data-g="rev"]');
      rg.innerHTML = v.rev.length > 1 ? '<span>Revenue</span>' + v.rev.map(([a, w]) => `<button type="button" data-rev="${esc(a)}">By ${esc(w.toLowerCase())}</button>`).join('') : '';
      rg.hidden = v.rev.length < 2;
      $('[data-g="costs"]').hidden = !v.seg;
      $('[data-g="cash"]').hidden = !v.cash;
      const ax = st.revAxis && (p.u.alt || {})[st.revAxis] ? st.revAxis : p.u.axis;
      $$('[data-rev]').forEach((b) => b.classList.toggle('on', b.dataset.rev === ax));
      $$('[data-costs]').forEach((b) => b.classList.toggle('on', b.dataset.costs === (v.seg ? st.costs : 'accounts')));
      $$('[data-cash]').forEach((b) => b.classList.toggle('on', b.dataset.cash === (v.cash ? st.cash : 'statement')));
      $$('[data-cmp]').forEach((b) => { b.classList.toggle('on', b.dataset.cmp === st.cmp); b.disabled = (b.dataset.cmp === 'q' && (o.fy || !p.q_end)) || (b.dataset.cmp === 'y' && !p.has_y); });
      $('[data-guide]').classList.toggle('on', st.guide && !st.next);
      $('[data-next]').classList.toggle('on', st.next);
      $('[data-g="case"]').hidden = !st.next;
      $$('[data-case]').forEach((b) => b.classList.toggle('on', b.dataset.case === st.case));
      $('[data-says]').classList.toggle('on', st.says);
      $$('[data-cmp]').forEach((b) => { if (st.next) b.disabled = true; });
      $('[data-all]').classList.toggle('on', st.all);
      $('[data-per]').value = String(idx);
    }
    function applyView() {
      const svg = host.querySelector('svg');
      if (!svg || !scene) return;
      const v = vb || [0, 0, scene.W, scene.H];
      svg.setAttribute('viewBox', v.map((x) => +x.toFixed(2)).join(' '));
      // the + / − keep their size on screen at any zoom (about 22 px)
      const r = stage.getBoundingClientRect(), k = Math.max(1, Math.max(v[2] / Math.max(r.width, 1), v[3] / Math.max(r.height, 1)));
      svg.querySelectorAll('.ffu-tog').forEach((g) => g.setAttribute('transform', `translate(${g.dataset.x} ${g.dataset.y}) scale(${k.toFixed(3)})`));
    }
    function fit(whole) {
      if (!scene) return;
      const r = stage.getBoundingClientRect(), kFit = Math.max(scene.W / Math.max(r.width, 1), scene.H / Math.max(r.height, 1));
      // a phone: the whole chart would be too small to read; it opens at the left (revenue) at a readable size instead
      const k = whole ? kFit : Math.min(kFit, Math.max(1.6, scene.H / Math.max(r.height, 1)));
      const w = r.width * k, h = r.height * k;
      vb = [k < kFit ? 0 : (scene.W - w) / 2, (scene.H - h) / 2, w, h];
      applyView();
    }
    async function draw(keep) {
      const before = keep && scene ? scene.nodes.find((n) => n.id === keep.id) : null;
      let { sp, spec } = current();
      let shown = spec, guided = false;
      msg.hidden = true;
      if ((st.guide || st.next || st.says) && !srcP) srcP = Promise.resolve(o.guidance ? o.guidance() : null).catch(() => null);
      if (srcP) src = await srcP;
      if (st.next && global.FFGuidance && global.FFGuidance.future) {
        // the next period as guided: the latest release's guidance with the newer MD&A outlook's figures for the same period
        try {
          let g = guidanceDoc(src);
          const company = { quarters: [Object.assign({}, spec)], years: [], periods: o.periods, _doc: list.filter((x) => x.end <= per().end) };
          if (o.fy) { company.years = company.quarters; company.quarters = []; }
          if (g && !o.fy) g = impliedQ4(g, Object.assign({}, spec, { label: o.labelOf(per().end, false) }), company);
          const r = g ? global.FFGuidance.future(Object.assign({}, spec, { label: o.labelOf(per().end, o.fy) }), g, { company, name: o.name, history: src && src.hist, full: true, case: st.case })
            : { error: 'No guidance on file for this company.' };
          if (r && !r.error) {
            shown = Object.assign({}, r, { dense: true, title: `${o.name} ${r.period || 'next period'} as guided${r.case && r.case !== 'mid' ? ` (${r.case} case)` : ''} — ultra-detailed` });
            // the projection carried into every line (and the guided cash lines set), the flows built anew
            try {
              const tg = global.FFGuidance.target(g, Object.assign({}, spec, { label: o.labelOf(per().end, o.fy) }), company);
              const end = Date.parse(per().end) + (o.fy ? 365 : 91) * 864e5 - 365 * 864e5;
              const ago = o.fy ? null : list.find((x) => x.u && Math.abs(Date.parse(x.end) - end) <= 12 * 864e5);
              const nx = tg ? guidedFlows(per(), Object.assign({ annual: !!o.fy }, st), sp, r, g, tg.period, ago && ago.u.now, st.case) : null;
              if (nx && nx.sp.nodes.length >= 6) { sp = nx.sp; shown = Object.assign(nx.spec, { dense: true, title: shown.title }); }
            } catch (err) { if (global.FF_DEBUG) console.error(err); }   // the projection as drawn by web/guidance.js stays
          }
          else { msg.textContent = (r && r.error) || 'No guidance on file.'; msg.hidden = false; }
        } catch (err) { msg.textContent = 'The guidance could not be drawn.'; msg.hidden = false; }
      }
      if (st.guide && !st.next && global.FFGuidance && global.FFGuidance.versus) {
        try {
          const older = list.filter((x) => x.end < per().end && x.u);
          const base = older.length ? older.reduce((a, b) => (a.end > b.end ? a : b)) : null;
          // the period and the one before it, both drawn the same way (the guidance is projected onto the one before)
          const company = { quarters: [], years: [], periods: o.periods };
          const into = company[o.fy ? 'years' : 'quarters'];
          into.push(Object.assign({}, spec, { period: o.fy ? 'fy' : undefined }));
          if (base) into.push(Object.assign(specOf(base, st).spec, { label: o.labelOf(base.end, o.fy) }));
          const r = src ? global.FFGuidance.versus(spec, src, { company, name: o.name, full: true }) : { error: 'No guidance on file for this company.' };
          if (r && !r.error) { shown = r; guided = true; } else { msg.textContent = (r && r.error) || 'No guidance on file.'; msg.hidden = false; }
        } catch (err) { msg.textContent = 'The guidance could not be read.'; msg.hidden = false; }
      }
      scene = S.layout(shown, { compare: st.next ? null : st.cmp || null, guide: guided });
      const says = st.says && src ? outlookOn(src.outlook, Object.assign({}, sp, { nodes: shown.nodes.map((n) => Object.assign({}, n, { key: (sp.nodes.find((x) => x.id === n.id) || {}).key })) })) : new Map();
      st.saysMap = says;
      // + / − on the lines that open: drawn over the chart (screen only)
      // the + / − and the 💬 sit beside the bar, on the side away from its label (readable at any zoom); a label above or
      // below the bar leaves them on its right, lifted a little off a label underneath
      const ctl = (n) => {
        const [x, y, w, h] = n.bar, L = n.label || [];
        const side = L.length && L[0] + L[2] <= x + 1 ? 1 : L.length && L[0] >= x + w - 1 ? -1 : 0;
        const under = !side && L.length && L[1] >= y + h - 1;
        return { s: side || 1, ax: side < 0 ? x : x + w, ay: y + Math.min(h / 2, 12), dy: under ? -8 : 0 };
      };
      const tog = scene.nodes.filter((n) => sp.toggles.has(n.id)).map((n) => {
        const t = sp.toggles.get(n.id), c = ctl(n);
        return `<g class="ffu-tog" data-tog="${esc(n.id)}" data-x="${c.ax.toFixed(1)}" data-y="${c.ay.toFixed(1)}" transform="translate(${c.ax.toFixed(1)} ${c.ay.toFixed(1)})"><title>${t === '+' ? 'Open its parts' : 'Close its parts'}</title><g transform="translate(${c.s * 14} ${c.dy})"><circle r="11" fill="${t === '+' ? '#1d1d1b' : '#6b6a66'}" stroke="#fff" stroke-width="2"/>` +
          `<path d="M-5 0H5${t === '+' ? 'M0 -5V5' : ''}" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></g></g>`;
      }).join('');
      // 💬 what the company says ahead about the line: a bubble with the number of statements, coloured by their tone
      const TONE = { positive: '#0b7a75', negative: '#d9480f', neutral: '#6b6a80' };
      const bub = scene.nodes.filter((n) => says.has(n.id)).map((n) => {
        const xs = says.get(n.id), pos = xs.filter((x) => x.tone === 'positive').length, neg = xs.filter((x) => x.tone === 'negative').length;
        const tone = pos > neg ? 'positive' : neg > pos ? 'negative' : 'neutral';
        const c = ctl(n), dx = c.s * (sp.toggles.has(n.id) ? 40 : 16);
        return `<g class="ffu-tog ffu-say" data-say="${esc(n.id)}" data-x="${c.ax.toFixed(1)}" data-y="${c.ay.toFixed(1)}" transform="translate(${c.ax.toFixed(1)} ${c.ay.toFixed(1)})"><title>${xs.length} statement${xs.length === 1 ? '' : 's'} about what is ahead</title><g transform="translate(${dx} ${c.dy})">` +
          `<path d="M-10 -9h20a2 2 0 0 1 2 2v11a2 2 0 0 1 -2 2h-12l-5 4v-4h-3a2 2 0 0 1 -2 -2v-11a2 2 0 0 1 2 -2z" fill="${TONE[tone]}" stroke="#fff" stroke-width="1.5"/>` +
          `<text x="0" y="2.5" font-size="10" font-weight="700" fill="#fff" text-anchor="middle">${xs.length}</text></g></g>`;
      }).join('');
      host.innerHTML = S.toSVG(scene, `${o.name} ultra-detailed flow`).replace('</svg>', `<g>${bub}${tog}</g></svg>`);
      const svg = host.querySelector('svg');
      svg.removeAttribute('width'); svg.removeAttribute('height');
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      if (before && vb) {                              // the line clicked stays where it was on screen
        const after = scene.nodes.find((n) => n.id === keep.id);
        if (after) { vb[0] += after.bar[0] - before.bar[0]; vb[1] += after.bar[1] - before.bar[1]; }
        applyView();
      } else fit();
      st.sp = sp;
      st.shown = shown;
      sync();
      if (sel && !sp.keys.has(sel)) { sel = null; info.hidden = true; }
    }
    function showInfo(id) {
      const n = (st.shown && st.shown.nodes || st.sp && st.sp.nodes || []).find((x) => x.id === id) || (st.sp && st.sp.nodes || []).find((x) => x.id === id);
      if (!n) { info.hidden = true; return; }
      sel = id;
      const lines = (n.lines || []).slice(1).map((l) => `<div>${l[1]}</div>`).join('');
      const cm = st.cmp === 'q' ? n.cmp : st.cmp === 'y' ? n.cmp_y : '';
      const xs = (st.saysMap && st.saysMap.get(id)) || [];
      const says = xs.length ? `<div class="ffu-says"><div class="ffu-k2">What the company says ahead</div>${xs.slice(0, 8).map((x) =>
        `<p class="ffu-say-${esc(x.tone || 'neutral')}">${esc(x.t)} <span class="muted">— ${esc(x.src)}${x.filed ? ' ' + esc(x.filed) : ''}${x.status && x.status !== 'repeated' ? ' · ' + esc(x.status) : ''}${x.hedge ? ' · hedged' : ''}</span></p>`).join('')}</div>` : '';
      info.innerHTML = `<div class="ffu-k">${n.name}</div><div class="ffu-v">${lines}${cm ? `<div>${esc(cm)}</div>` : ''}</div>${says}` +
        `${n.source ? `<p class="ffu-src">${n.source}</p>` : ''}${st.sp.toggles.has(id) ? `<button type="button" class="ffu-btn" data-tog-info="${esc(id)}">${st.sp.toggles.get(id) === '+' ? '+ Open its parts' : '− Close its parts'}</button>` : ''}` +
        '<button type="button" class="ffu-btn" data-info-close>Close</button>';
      info.hidden = false;
    }
    function toggle(id) {
      const k = st.sp.keys.get(id);
      if (!k) return;
      if (st.sp.toggles.get(id) === '+') { st.opened.add(k); st.closed.delete(k); } else { st.closed.add(k); st.opened.delete(k); st.all = false; }
      draw({ id }).then(() => { if (sel === id) showInfo(id); });
    }
    // controls
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button, .ffu-tog, [data-node]');
      if (!b) return;
      if (b.matches('.ffu-say')) { e.stopPropagation(); showInfo(b.dataset.say); return; }
      if (b.matches('.ffu-tog')) { e.stopPropagation(); toggle(b.dataset.tog); return; }
      if (b.dataset.togInfo) { toggle(b.dataset.togInfo); return; }
      if (b.hasAttribute('data-info-close')) { info.hidden = true; sel = null; return; }
      if (b.hasAttribute('data-node')) { if (!dragged) showInfo(b.dataset.node); return; }
      if (b.dataset.rev) { st.revAxis = b.dataset.rev; draw(); return; }
      if (b.dataset.costs) { st.costs = b.dataset.costs; draw(); return; }
      if (b.dataset.cash) { st.cash = b.dataset.cash; draw(); return; }
      if (b.dataset.cmp !== undefined && b.hasAttribute('data-cmp')) { st.cmp = b.dataset.cmp; draw(); return; }
      if (b.hasAttribute('data-guide')) { st.guide = !st.guide; st.next = false; draw(); return; }
      if (b.hasAttribute('data-next')) {
        st.next = !st.next; st.guide = false;
        if (st.next && per().u.cash_uses && st.cash === 'statement') st.cash = 'uses';   // capital spending and free cash flow as their own lines
        draw(); return;
      }
      if (b.dataset.case) { st.case = b.dataset.case; draw(); return; }
      if (b.hasAttribute('data-says')) { st.says = !st.says; draw(); return; }
      if (b.hasAttribute('data-all')) { st.all = !st.all; if (!st.all) st.opened.clear(); draw(); return; }
      if (b.hasAttribute('data-std')) { Object.assign(st, { revAxis: null, costs: 'accounts', cash: 'statement', all: false }); st.opened.clear(); st.closed.clear(); draw(); return; }
      if (b.dataset.z) { zoom(b.dataset.z === 'in' ? 0.7 : b.dataset.z === 'out' ? 1 / 0.7 : 0); return; }
      if (b.hasAttribute('data-png')) { png(); return; }
      if (b.hasAttribute('data-close')) close();
    });
    $('[data-per]').addEventListener('change', (e) => { idx = +e.target.value; st.opened.clear(); st.closed.clear(); draw(); });
    function zoom(k, px, py) {
      if (!scene) return;
      if (!k) { fit(true); return; }
      const v = vb || [0, 0, scene.W, scene.H];
      const cx = px == null ? v[0] + v[2] / 2 : px, cy = py == null ? v[1] + v[3] / 2 : py;
      const w = Math.min(Math.max(v[2] * k, 120), scene.W * 4), h = w * v[3] / v[2];
      vb = [cx - (cx - v[0]) * (w / v[2]), cy - (cy - v[1]) * (h / v[3]), w, h];
      applyView();
    }
    const at = (x, y) => { const r = host.getBoundingClientRect(), v = vb || [0, 0, scene.W, scene.H], k = Math.max(v[2] / r.width, v[3] / r.height);
      return [v[0] + (x - r.left - (r.width - v[2] / k) / 2) * k, v[1] + (y - r.top - (r.height - v[3] / k) / 2) * k, k]; };
    stage.addEventListener('wheel', (e) => { if (!scene) return; e.preventDefault(); const [px, py] = at(e.clientX, e.clientY); zoom(Math.exp(Math.max(-300, Math.min(300, e.deltaY)) * 0.0015), px, py); }, { passive: false });
    const pts = new Map();
    let drag = null, dragged = false, pinch = null;
    stage.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.ffu-info, .ffu-tog')) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      try { stage.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
      dragged = false;
      if (pts.size === 1) drag = { x: e.clientX, y: e.clientY, vb: (vb || [0, 0, scene.W, scene.H]).slice() };
      if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), vb: (vb || [0, 0, scene.W, scene.H]).slice(), c: at((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) }; drag = null; }
    });
    stage.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId) || !scene) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (pinch && pts.size === 2) {
        const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        vb = pinch.vb.slice(); zoom(pinch.d / Math.max(d, 1), pinch.c[0], pinch.c[1]); dragged = true;
      } else if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (!dragged && Math.hypot(dx, dy) < 4) return;
        dragged = true; stage.classList.add('grabbing');
        const k = at(0, 0)[2];
        vb = [drag.vb[0] - dx * k, drag.vb[1] - dy * k, drag.vb[2], drag.vb[3]];
        applyView();
      }
    });
    const up = (e) => { pts.delete(e.pointerId); if (pts.size < 2) pinch = null; if (!pts.size) { drag = null; stage.classList.remove('grabbing'); setTimeout(() => { dragged = false; }, 0); } };
    stage.addEventListener('pointerup', up);
    stage.addEventListener('pointercancel', up);
    function png() {
      if (!scene) return;
      const c = S.toCanvas(scene, 2);
      c.toBlob((b) => { if (!b) return; const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = `${o.slug || 'company'}-ultra-detailed-sankey.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); }, 'image/png');
    }
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    function close() { document.removeEventListener('keydown', onKey); el.remove(); document.body.classList.remove('ffu-open'); }
    document.addEventListener('keydown', onKey);
    document.body.appendChild(el);
    document.body.classList.add('ffu-open');
    window.addEventListener('resize', () => { if (el.isConnected && !vb) fit(); });
    draw();
    return el;
  }

  global.FFFlow = { build, views, structure, mainOf, money, AXIS_WORD, open, guidedValues, guidedFlows, impliedQ4, outlookOn, guidanceDoc };
  if (typeof module !== 'undefined' && module.exports) module.exports = global.FFFlow;
})(typeof window !== 'undefined' ? window : globalThis);
