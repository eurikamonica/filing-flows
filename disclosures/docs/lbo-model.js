/* A leveraged buyout of a listed company, by fixed rules (the "LBO & takeover" view and the hub's Buyouts board; the
   board runs the same code in node: disclosures/app/lbo_board.cjs).

   run(inputs, a) — inputs from research/lbo c/<cik>.json (trailing revenue, EBITDA, D&A, capex, tax rate, growth; price,
   shares, debt, cash, claims) and the debt market (rates: base = SOFR, spread_b = the high-yield B spread, %):
   - entry: the shares bought at today's price plus a premium, the existing debt refinanced (enterprise value), fees;
   - new debt: the least of leverage × EBITDA, a share of the price, and what EBITDA covers twice in interest;
     the loan rate = base + B spread + a loan premium;
   - five years: revenue grows at the company's own rate (held between −3% and +8%, fading to 3%), the EBITDA margin
     stays (or rises by marginUp, cost cuts, over the years), D&A and capex as shares of revenue stay as they are, working capital takes 10% of the revenue added, cash taxes
     on EBIT after interest; every dollar of free cash flow repays debt (a shortfall is borrowed);
   - exit at today's trading multiple (enterprise value / EBITDA before any premium; or the one given), the debt left
     repaid: the buyer's IRR and money multiple. Flags: already levered (net debt over 6× EBITDA), larger than any buyout
     on record (enterprise value over $60 billion).
   maxPrice(inputs, a, target) — the highest price a share at which the buyer still makes `target` (20%): the price
   a financial buyer could pay, a floor under the share price when it is above it. */
(function (global) {
  'use strict';
  const DEFAULTS = { premium: 0.30, leverage: 5.5, maxDebtShare: 0.65, minCoverage: 2.0, loanPremium: 0.5, fees: 0.02, years: 5, exitMultiple: null,
    target: 0.20, growth: null, nwc: 0.10, tax: null, marginUp: 0 };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const fin = (v) => v != null && Number.isFinite(+v);

  function usable(i) {
    if (!i || !fin(i.revenue) || !fin(i.ebitda) || !fin(i.price) || !fin(i.shares)) return 'figures missing';
    if (i.ebitda <= 0) return 'no positive EBITDA to borrow against';
    if (i.ebitda / i.revenue < 0.03) return 'EBITDA margin under 3%';
    return null;
  }
  function rateOf(r, a) { return ((fin(r && r.base) ? +r.base : 4) + (fin(r && r.spread_b) ? +r.spread_b : 3.5) + a.loanPremium) / 100; }

  function run(i, opts, rates) {
    const a = Object.assign({}, DEFAULTS, opts || {});
    const why = usable(i);
    if (why) return { ok: false, why };
    const rate = fin(a.rate) ? a.rate : rateOf(rates, a);
    const debt0 = i.debt || 0, cash0 = i.cash || 0, claims = i.claims || 0;
    const price = fin(a.price) ? a.price : i.price * (1 + a.premium);
    const equityPrice = price * i.shares;
    const ev = equityPrice + debt0 - cash0 + claims;
    const mult = ev / i.ebitda;
    const D0 = Math.max(0, Math.min(a.leverage * i.ebitda, a.maxDebtShare * ev, i.ebitda / (a.minCoverage * rate)));
    const fees = a.fees * ev;
    const eq0 = ev + fees - D0;
    if (eq0 <= 0) return { ok: false, why: 'the debt alone pays for it' };
    const margin = i.ebitda / i.revenue, daS = (i.da || 0) / i.revenue, capS = Math.abs(i.capex || 0) / i.revenue;
    const tax = fin(a.tax) ? a.tax : clamp(fin(i.tax_rate) ? (i.tax_rate > 1 ? i.tax_rate / 100 : i.tax_rate) : 0.24, 0.12, 0.30);
    const g1 = fin(a.growth) ? a.growth : clamp(fin(i.g0) ? (Math.abs(i.g0) > 1 ? i.g0 / 100 : i.g0) : 0.03, -0.03, 0.08);
    let rev = i.revenue, D = D0, cash = 0;
    const years = [];
    for (let t = 1; t <= a.years; t++) {
      const g = fin(a.growth) ? a.growth : g1 + (0.03 - g1) * (t - 1) / Math.max(1, a.years - 1);
      const prevRev = rev;
      rev *= 1 + g;
      const ebitda = rev * (margin + a.marginUp * t / a.years), da = rev * daS, capex = rev * capS, int = D * rate;
      const taxes = Math.max(0, ebitda - da - int) * tax, wc = a.nwc * Math.max(0, rev - prevRev);
      const fcf = ebitda - capex - taxes - int - wc;
      if (fcf >= 0) { const pay = Math.min(D, fcf); D -= pay; cash += fcf - pay; } else { const use = Math.min(cash, -fcf); cash -= use; D += -fcf - use; }
      years.push({ t, revenue: rev, ebitda, capex, interest: int, taxes, fcf, debt: D, cash });
    }
    const last = years[years.length - 1];
    const today = (i.price * i.shares + debt0 - cash0 + claims) / i.ebitda;
    const exitMult = fin(a.exitMultiple) ? a.exitMultiple : Math.max(1, today);
    const exitEV = exitMult * last.ebitda;
    const eq5 = exitEV - last.debt + last.cash;
    const moic = eq5 / eq0;
    const irr = eq5 <= 0 ? -1 : Math.pow(moic, 1 / a.years) - 1;
    const flags = [];
    if ((debt0 - cash0) / i.ebitda > 6) flags.push('levered');
    if (ev > 60e9) flags.push('too big');
    return { ok: true, price, premium: price / i.price - 1, irr, moic, rate, tax, growth: g1, flags, todayMultiple: today,
      entry: { ev, multiple: mult, debt: D0, leverage: D0 / i.ebitda, equity: eq0, equityShare: eq0 / (ev + fees), fees, coverage: i.ebitda / (D0 * rate || 1) },
      exit: { ev: exitEV, multiple: exitMult, debt: last.debt, cash: last.cash, equity: eq5 }, years,
      paidDown: D0 ? 1 - last.debt / D0 : null };
  }

  // the highest price a share for the target IRR (bisection: the IRR falls as the price rises)
  function maxPrice(i, opts, rates, target) {
    const tg = fin(target) ? target : (opts && opts.target) || DEFAULTS.target;
    if (usable(i)) return null;
    let lo = i.price * 0.02, hi = i.price * 6;
    const at = (p) => { const r = run(i, Object.assign({}, opts, { price: p }), rates); return r.ok ? r.irr : -1; };
    if (at(lo) < tg) return { price: null, why: 'not even a near-zero price earns the target' };
    if (at(hi) >= tg) return { price: hi, capped: true };
    for (let k = 0; k < 60; k++) { const m = (lo + hi) / 2; if (at(m) >= tg) lo = m; else hi = m; }
    return { price: lo, vsPrice: lo / i.price - 1 };
  }

  const api = { run, maxPrice, usable, DEFAULTS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.FFLbo = api;
})(typeof window !== 'undefined' ? window : globalThis);
