/* Filing Flows: valuation math for the company page's Valuation tab — a forward FCFF DCF, a one-parameter reverse
   solver and the sensitivity grids. Pure functions, no DOM: tested in Node (tests/test_fsa.cjs).
   Specification and acceptance cases from fsa-beta/planning/03_VALUATION.md (beta/fsa-chatgpt, ChatGPT (OpenAI)). */
(function (root) {
  'use strict';
  const fin = (v) => typeof v === 'number' && Number.isFinite(v);
  const at = (v, t) => (Array.isArray(v) ? v[Math.min(t, v.length - 1)] : v);       // a constant or a per-year array

  // inputs: rev0 (last full-year revenue), years, growth, margin (EBIT / revenue), tax, da (D&A / revenue),
  // capex (capex / revenue), wc (change in operating working capital / change in revenue), wacc, g,
  // terminal: 'roic' (reinvestment = g / roic) or 'simple' (FCFF[N] × (1 + g)), roic, lossTax: 'none' | 'symmetric',
  // debt, cash, claims (noncontrolling interests, preferred), nonop (other nonoperating assets), shares
  function validate(x) {
    const errs = [];
    for (const k of ['rev0', 'tax', 'da', 'capex', 'wc', 'wacc', 'g', 'debt', 'cash', 'claims', 'nonop', 'shares'])
      if (!fin(x[k])) errs.push(`${k} is missing or not a number`);
    for (const k of ['growth', 'margin']) if (![].concat(x[k]).every(fin)) errs.push(`${k} is missing or not a number`);
    if (!(x.years >= 1 && x.years <= 15 && Number.isInteger(x.years))) errs.push('forecast years must be 1 to 15');
    if (fin(x.wacc) && x.wacc <= -1) errs.push('WACC must be above −100%');
    if (fin(x.wacc) && fin(x.g) && x.wacc <= x.g) errs.push('WACC must be above terminal growth');
    if (fin(x.shares) && x.shares <= 0) errs.push('diluted shares must be positive');
    if (x.terminal === 'roic' && !(fin(x.roic) && x.roic > 0)) errs.push('terminal ROIC must be positive');
    if (x.terminal === 'roic' && fin(x.roic) && fin(x.g) && x.g > x.roic) errs.push('terminal growth above terminal ROIC needs more reinvestment than profit');
    return errs;
  }

  function dcf(x) {
    const errs = validate(x);
    if (errs.length) return { ok: false, errors: errs };
    const rows = [];
    let rev = x.rev0, pv = 0;
    const nopatOf = (ebit) => (ebit > 0 || x.lossTax === 'symmetric' ? ebit * (1 - x.tax) : ebit);
    for (let t = 1; t <= x.years; t++) {
      const prev = rev;
      rev = prev * (1 + at(x.growth, t - 1));
      const ebit = rev * at(x.margin, t - 1), nopat = nopatOf(ebit);
      const da = rev * x.da, capex = rev * x.capex, dwc = (rev - prev) * x.wc;
      const fcff = nopat + da - capex - dwc, df = Math.pow(1 + x.wacc, -t);
      pv += fcff * df;
      rows.push({ t, rev, ebit, nopat, da, capex, dwc, fcff, df, pv: fcff * df });
    }
    const last = rows[rows.length - 1];
    let fcffNext;
    if (x.terminal === 'roic') {
      const nopatNext = nopatOf(last.rev * (1 + x.g) * at(x.margin, x.years - 1));
      fcffNext = nopatNext * (1 - x.g / x.roic);
    } else fcffNext = last.fcff * (1 + x.g);
    const tv = fcffNext / (x.wacc - x.g), tvPv = tv * Math.pow(1 + x.wacc, -x.years);
    const ev = pv + tvPv;
    const equity = ev - x.debt - x.claims + x.cash + x.nonop;
    const flags = [];
    if (ev > 0 && tvPv / ev > 0.75) flags.push(`terminal value is ${Math.round(tvPv / ev * 100)}% of enterprise value`);
    if (fcffNext < 0) flags.push('terminal-year free cash flow is negative');
    if (equity < 0) flags.push('equity value is negative: claims exceed the value of the operations');
    return { ok: true, rows, fcffNext, tv, tvPv, pvExplicit: pv, ev, equity, perShare: equity / x.shares, flags };
  }

  const value = (x) => { const r = dcf(x); return r.ok ? r.perShare : NaN; };

  // Reverse DCF: the value of ONE parameter (growth, margin or wacc) at which the model gives `price`, everything else
  // held. Scans the user's bounds for sign changes, bisects only inside a bracket, and says so when there is no
  // solution, more than one, or no convergence — never clamps to a bound.
  function root1(f, lo, hi, opt) {               // f's single root in [lo, hi], or why there is none
    opt = opt || {};
    const steps = opt.steps || 120, tol = opt.tol || 1e-7;
    const pts = [];
    for (let i = 0; i <= steps; i++) { const v = lo + (hi - lo) * i / steps; pts.push([v, f(v)]); }
    const brackets = [];
    for (let i = 1; i < pts.length; i++) {
      const [a, fa] = pts[i - 1], [b, fb] = pts[i];
      if (!fin(fa) || !fin(fb)) continue;
      if (fa === 0) brackets.push([a, a]);
      else if (fa * fb < 0) brackets.push([a, b]);
    }
    if (fin(pts[pts.length - 1][1]) && pts[pts.length - 1][1] === 0) brackets.push([hi, hi]);
    const ok = pts.filter((p) => fin(p[1]));
    if (!brackets.length) return { status: 'none', range: ok.length ? [Math.min(...ok.map((p) => p[1])), Math.max(...ok.map((p) => p[1]))] : null };
    if (brackets.length > 1) return { status: 'multiple', brackets };
    let [a, b] = brackets[0], fa = f(a), it = 0;
    while (b - a > tol && it++ < 200) {
      const m = (a + b) / 2, fm = f(m);
      if (!fin(fm)) return { status: 'nonconvergent' };
      if (fm === 0) { a = b = m; break; }
      if (fa * fm < 0) b = m; else { a = m; fa = fm; }
    }
    return b - a > tol ? { status: 'nonconvergent' } : { status: 'ok', value: (a + b) / 2, iterations: it };
  }

  function solve(x, param, price, lo, hi, opt) {
    const r = root1((v) => value({ ...x, [param]: v }) - price, lo, hi, opt);
    if (r.status === 'none') {
      r.note = r.range ? `no value between ${lo} and ${hi} gives this price (the model ranges from ${(r.range[0] + price).toFixed(2)} to ${
        (r.range[1] + price).toFixed(2)} a share)` : 'the model is not defined anywhere in these bounds';
      return r;
    }
    if (r.status !== 'ok') return r;
    const check = value({ ...x, [param]: r.value });           // fed back through the forward model
    return { ...r, check, residual: check - price };
  }

  // grid of per-share values: rows = values of `rp`, columns = values of `cp`
  function grid(x, rp, rvals, cp, cvals) {
    return rvals.map((r) => cvals.map((c) => value({ ...x, [rp]: r, [cp]: c })));
  }

  const api = { validate, dcf, value, solve, root1, grid };
  root.FSA = api;
  if (typeof module !== 'undefined') module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
