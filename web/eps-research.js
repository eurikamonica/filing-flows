/* The company page's EPS forecast (#c-<cik>-eps): one GAAP diluted EPS estimate for the next quarter with its 80%
 * range and the chance it beats last year (pipeline/eps_blend.py: fundamentals + consensus converted to GAAP +
 * guidance), the forecasts frozen before each report and their scores, the Disclosure Hub's earnings preview, and the
 * details folded below. Wall Street's own numbers are on their adjusted basis and labelled so.
 */
(function () {
  'use strict';
  const num = v => typeof v === 'number' && Number.isFinite(v);
  const day = v => String(v || '').slice(0, 10);
  const valid = v => v !== null && v !== '' && Number.isFinite(Number(v));
  const money = v => num(v) ? (v < 0 ? '-$' : '$') + Math.abs(v).toFixed(3) : 'N/A';
  const percent = v => num(v) ? (100 * v).toFixed(1) + '%' : 'N/A';
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
  const later = (a, b) => day(a) > day(b);
  function bias(values, estimate) {
    if (!values.length) return 0;
    const last = values.slice(-8), w = last.map((_, i) => Math.pow(.85, last.length-1-i));
    const residual = last.map(v => clamp(v, -3, 3));
    return clamp(residual.reduce((v,x,i)=>v+x*w[i],0) / w.reduce((a,b)=>a+b,0) *
      last.length / (last.length + 8), -.25*Math.max(Math.abs(estimate),.5),
      .25*Math.max(Math.abs(estimate),.5));
  }
  function safeTime(s) { const t = Date.parse(String(s)); return Number.isFinite(t) ? t : NaN; }
  function publicHistory(doc, asof) {
    return (doc?.analysts?.surprises || doc?.surprises || []).filter(x =>
      valid(x.eps_est) && valid(x.eps_act) && x.reported &&
      later(asof, x.reported)) // conservative: report eligible the following UTC day
      .sort((a, b) => String(a.reported).localeCompare(String(b.reported)));
  }
  function forecast(doc, asof) {
    if (!doc || !doc.analysts || !doc.analysts.periods) return null;
    const q = doc.analysts.periods.find(x => x.period === '0q');
    const c = q && q.eps;
    if (!c || !valid(c.avg) || !valid(c.numberOfAnalysts) || Number(c.numberOfAnalysts) < 1 ||
        !doc.analysts.as_of || later(doc.analysts.as_of, asof)) return null;
    const history = publicHistory(doc, asof);
    // Conservative empirical-Bayes correction, fitted exclusively on earlier published surprises.
    const past = history.map(x => Number(x.eps_act) - Number(x.eps_est)).filter(num).slice(-8);
    const k = past.length ? past.length / (past.length + 8) : 0;
    const adjustment = bias(past, +c.avg);
    const estimate = Number(c.avg) + adjustment;
    const prior = valid(c.yearAgoEps) ? Number(c.yearAgoEps) : null;
    const errors = past.length ? past.map(x => x - adjustment) : [];
    // This is NOT a calibrated confidence interval; only show descriptive sensitivity.
    const spread = errors.length >= 3 ? Math.max(.05, mean(errors.map(x => Math.abs(x))) * 1.5) : null;
    const beats = past.filter(x => x > 0).length;
    return {consensus: +c.avg, median: estimate, adjustment, past_n: past.length, analyst_n: +c.numberOfAnalysts,
      bear: valid(c.low) ? +c.low+adjustment : null,
      bull: valid(c.high) ? +c.high+adjustment : null,
      period: q.end, yearAgo: prior, yoy: prior !== null && Math.abs(prior) >= .02 ? (estimate - prior) / Math.abs(prior) : null,
      beat_rate: (beats + 1) / (past.length + 2), lower_sensitivity: spread === null ? null : estimate - spread,
      upper_sensitivity: spread === null ? null : estimate + spread, interval_calibrated: false,
      next_report: doc.analysts.next_earnings?.date || null};
  }
  function trailingTest(doc, asof) {
    const rows = publicHistory(doc, asof);
    const tests = [];
    for (let i = 2; i < rows.length; i++) {
      const prev = rows.slice(Math.max(0, i - 8), i).map(x => +x.eps_act - +x.eps_est);
      const delta = bias(prev,+rows[i].eps_est);
      const actual = +rows[i].eps_act, baseline = +rows[i].eps_est, pred = baseline + delta;
      tests.push({reported: rows[i].reported, forecast: pred, baseline, actual, error: Math.abs(pred - actual)});
    }
    return {tests, mae: tests.length ? mean(tests.map(x => x.error)) : null,
      baseline_mae: tests.length ? mean(tests.map(x => Math.abs(x.baseline - x.actual))) : null,
      label: 'Retrospective walk-forward on archived surprise records; historical estimate vintages unaudited'};
  }

  function peerSignals(targetEnd, asof, ix, ticker, peers) {
    // Chain labels are public relationship research, not verified issuer-specific contracts.
    const T=String(ticker||'').toUpperCase(), companies=ix?.companies || [];
    const own=companies.find(x=>String(x.ticker||'').toUpperCase()===T);
    const byTicker=new Map(companies.map(x=>[String(x.ticker||'').toUpperCase(),x]));
    const groups={industry:[],subindustry:[],upstream:[],downstream:[]};
    for(const co of companies) {
      const tk=String(co.ticker||'').toUpperCase();
      if(!tk||tk===T)continue;
      if(own?.sector && co.sector===own.sector)groups.industry.push(tk);
      if(own?.sic && co.sic===own.sic)groups.subindustry.push(tk);
    }
    for(const chain of ix?.chains || []) {
      const buyers=(chain.buyers||[]).map(x=>String(x).toUpperCase());
      const suppliers=(chain.layers||[]).flatMap(x=>x.tickers||[]).map(x=>String(x).toUpperCase());
      if(buyers.includes(T))groups.upstream.push(...suppliers.filter(x=>x!==T));
      if(suppliers.includes(T))groups.downstream.push(...buyers.filter(x=>x!==T));
    }
    const output={};
    for(const [name,tickers] of Object.entries(groups)){
      const available=[];
      for(const tk of new Set(tickers)) {
        if(!byTicker.has(tk))continue;
        const doc=peers[tk]; if(!doc)continue;
        const rows=publicHistory(doc,asof);
        const hit=rows.filter(x=>x.quarter && Number.isFinite(Date.parse(x.quarter)) &&
          Number.isFinite(Date.parse(targetEnd)) &&
          Math.abs(Date.parse(x.quarter)-Date.parse(targetEnd))<=45*86400000 &&
          valid(x.eps_est) && valid(x.eps_act) && Math.abs(+x.eps_est)>.02).slice(-1)[0];
        if(hit)available.push({ticker:tk,reported:hit.reported,
          eps:+hit.eps_act,surprise:clamp((+hit.eps_act-(+hit.eps_est))/Math.abs(+hit.eps_est),-1,1)});
      }
      output[name]={count:available.length,mean_surprise:available.length?mean(available.map(x=>x.surprise)):null,
        tickers:available.map(x=>x.ticker)};
    }
    return output;
  }
  async function loadPeerSignals(ticker, end, asof) {
    if(!end)return null;
    const ix=await get('data/index.json').catch(()=>null);
    if(!ix)return null;
    const T=String(ticker).toUpperCase();
    const own=(ix.companies||[]).find(x=>String(x.ticker||'').toUpperCase()===T);
    if(!own)return null;
    const pool=new Set(), buyers=new Set(), suppliers=new Set();
    for(const x of (ix.companies||[])){
      if(x.ticker&&x.ticker!==T&&
        (x.sic&&x.sic===own.sic||x.sector&&x.sector===own.sector))pool.add(String(x.ticker).toUpperCase());
    }
    for(const ch of ix.chains||[]){
      const b=(ch.buyers||[]).map(x=>String(x).toUpperCase());
      const l=(ch.layers||[]).flatMap(x=>x.tickers||[]).map(x=>String(x).toUpperCase());
      if(b.includes(T))l.forEach(x=>suppliers.add(x));
      if(l.includes(T))b.forEach(x=>buyers.add(x));
    }
    const selected=[...suppliers,...buyers,...pool].filter(x=>x!==T).slice(0,36);
    const id=new Map((ix.companies||[]).filter(x=>x.ticker&&x.cik).map(x=>[String(x.ticker).toUpperCase(),x.cik]));
    const peers={};
    await Promise.all([...new Set(selected)].map(async tk=>{
      if(!id.has(tk))return;
      const doc=await get('disclosures/data/consensus/c/'+encodeURIComponent(id.get(tk))+'.json').catch(()=>null);
      if(doc)peers[tk]=doc;
    }));
    return peerSignals(end,asof,ix,T,peers);
  }

  function metrics(doc, smart, rates, asof) {
    let signals = {};
    const a = doc?.analysts || {};
    const ratingActions = (a.actions || []).filter(x => x.date && !later(x.date, asof));
    const upgrades = ratingActions.filter(x => String(x.action).toLowerCase() === 'up').length;
    const downgrades = ratingActions.filter(x => String(x.action).toLowerCase() === 'down').length;
    signals.ratings = {upgrades, downgrades, last: ratingActions[0]?.date || null,
      revision_30d: (a.periods || []).find(x => x.period === '0q')?.revisions || null};
    if (smart && smart.generated_at && safeTime(smart.generated_at) <= safeTime(asof + 'T23:59:59Z')) {
      signals.smart = {score: num(smart.now?.S) ? smart.now.S : null,
        f13: num(smart.now?.groups?.f13?.S) ? smart.now.groups.f13.S : null,
        observed_at: smart.generated_at, n: smart.now?.n || 0};
    }
    // Live Yes price is market.p (not market.outcomes); historical backtests must use
    // only timestamped prices, never future current quotes.
    const mk = (doc?.markets || []).find(x => x.kind === 'beat' && !x.closed &&
      (x.source === 'polymarket' || x.source === 'kalshi') &&
      x.end && !later(asof,x.end) && (!a.next_earnings?.date ||
      Math.abs(safeTime(x.end+'T00:00:00Z')-safeTime(a.next_earnings.date+'T00:00:00Z'))<20*86400000));
    if(mk){
      const hist=(mk.history||[]).filter(x=>day(x[0])<=asof && valid(x[1]))
        .sort((x,y)=>String(x[0]).localeCompare(String(y[0])));
      const p=hist.length?+hist[hist.length-1][1]:
        (doc.generated_at && day(doc.generated_at)<=asof && valid(mk.p)?+mk.p:null);
      if(num(p)&&p>=0&&p<=1) signals.polymarket={p,title:mk.title,
        source:mk.source,url:mk.url,volume:mk.volume,
        observed_at:hist.length?day(hist[hist.length-1][0]):day(doc.generated_at),
        basis:mk.basis||'unspecified',eps_strike:mk.eps_strike};
    }
    signals.kalshi=(doc?.markets||[]).filter(x=>x.source==='kalshi' && !x.closed &&
      x.end && !later(asof,x.end) && x.kind!=='beat' &&
      (x.kind==='kpi'||x.kind==='metric'||x.kind==='mention')).slice(0,4)
      .map(m=>({title:m.title,kind:m.kind,end:m.end,url:m.url,volume:m.volume,
        outcomes:(m.outcomes||[]).slice(0,3).map(x=>({name:x.q,p:+x.p})),
        median:m.stats?.median?.value}));
    // FRED rates are from current stored snapshot: not a retroactive ALFRED vintage.
    if (rates?.generated_at && safeTime(rates.generated_at) <= safeTime(asof + 'T23:59:59Z')) {
      signals.fred = {};
      for (const id of ['DGS2','DGS10','VIXCLS','UNRATE','BAMLH0A0HYM2']) {
        const s = rates.series?.[id]; const observations = s?.monthly || [];
        const a = observations.filter(x => x[0] && x[0] <= asof.slice(0,7) && num(x[1]));
        if (a.length) signals.fred[id] = {period: a[a.length-1][0], value: a[a.length-1][1]};
      }
    }
    return signals;
  }
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const usd = v => num(v) ? (v < 0 ? '−$' : '$') + Math.abs(v).toFixed(2) : '—';
  const pct0 = v => num(v) ? Math.round(100 * v) + '%' : '—';
  const dateL = s => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || '')); return m ? new Date(Date.UTC(+m[1], +m[2]-1, +m[3])).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'}) : '—'; };
  const rows = (pairs) => pairs.filter(Boolean).map(([a, b]) => `<div class="ff-eps-row"><span>${esc(a)}</span><strong>${b}</strong></div>`).join('');
  async function get(url) {
    const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);return r.json();
  }
  const PART = {fundamental: 'Fundamentals (revenue, margins, tax, shares)', street: 'Wall Street consensus, converted to GAAP (with the usual beat)', guidance: 'Company guidance, on the GAAP basis'};

  // the one answer: our GAAP estimate, its range, the probability against last year, and what it is made of
  function headline(h, track, oos, card, gaap, f) {
    if (!h) {
      const ref = gaap?.reference;
      const g = gaap?.forecast;
      return `<div class="ff-eps-head"><div class="ff-eps-kicker">GAAP diluted EPS · next quarter</div>
        <p class="muted">${g ? `Seasonal estimate ${usd(g.eps_point)} for the quarter ending ${esc(dateL(g.target_end))} (this company's year-ago trend model beat “same quarter last year” in its own walk-forward).`
          : 'No estimate for this company yet: its filings do not give eight comparable quarters of revenue, profit, tax and shares, and there is no analyst consensus to convert.'}
          ${ref ? ` Same quarter last year: <b>${usd(ref.year_ago_eps)}</b>; last quarter: ${usd(ref.last_eps)}.` : ''}
          ${f ? ` Wall Street expects ${usd(f.consensus)} on its adjusted basis (${f.analyst_n} analysts).` : ''}</p></div>`;
    }
    const st = h.street, g = h.guidance, w = h.weights || {};
    const parts = Object.entries(h.components || {}).map(([k, v]) => `<li><span>${esc(PART[k] || k)}</span><b>${usd(v)}</b><i>${pct0(w[k])} of the estimate</i></li>`).join('');
    const p = oos?.paired;
    const trackLine = track?.n ? `On this company's own filings, walked forward quarter by quarter, the fundamental model came closer than “same quarter last year” in <b>${pct0(track.closer_share)}</b> of ${track.n} quarters.` : '';
    const oosLine = p?.n ? ` Across ${p.n} company-quarters with a consensus (fitted on half the companies, scored on the other half), this estimate missed by ${pct0(p.blend.rel_error_model)} of a company's usual EPS, the converted consensus by ${pct0(p.street.rel_error_model)}, “same quarter last year” by ${pct0(p.blend.rel_error_baseline)}.` : '';
    const cardLine = card?.scored ? ` Forecasts frozen before the report so far: ${card.scored} scored, closer than last year in ${pct0(card.vs_year_ago?.closer_share)}.` : (card?.frozen ? ` ${card.frozen} forecasts are frozen before their reports and will be scored as the 10-Qs are filed.` : '');
    return `<div class="ff-eps-head">
      <div class="ff-eps-kicker">GAAP diluted EPS · quarter ending ${esc(dateL(h.target_end))}</div>
      <div class="ff-eps-big"><div><span>Our estimate</span><b>${usd(h.point)}</b></div>
        <div><span>80% range</span><b class="ff-eps-mid">${usd(h.p10)} – ${usd(h.p90)}</b></div>
        <div><span>Above last year's ${usd(h.year_ago)}</span><b class="ff-eps-mid">${pct0(h.p_up)}</b></div></div>
      ${st ? `<p class="ff-eps-street">Wall Street: <b>${usd(st.consensus)}</b> adjusted EPS (${esc(st.analysts || '—')} analysts${st.next_report ? `, report expected ${esc(dateL(st.next_report))}` : ''})${num(st.gap) ? ` — this company's adjusted EPS has run ${usd(Math.abs(st.gap))} ${st.gap >= 0 ? 'above' : 'below'} its GAAP EPS, so about <b>${usd(st.gaap_equivalent)}</b> GAAP${num(st.beat) && Math.abs(st.beat) >= .005 ? `; companies have ${st.beat > 0 ? 'beaten' : 'missed'} their consensus by about ${usd(Math.abs(st.beat))} for a company this size, which puts it at ${usd(st.gaap_equivalent + st.beat)}` : ''}` : ''}.</p>` : ''}
      ${g ? `<p class="ff-eps-street">Company guidance (${esc(g.kind)}, ${esc(g.basis)} basis, release of ${esc(dateL(g.filed))}): <b>${usd(g.value)}</b> GAAP. <span class="muted">“${esc(String(g.text).slice(0, 220))}”</span>${g.url ? ` <a href="${esc(g.url)}" target="_blank" rel="noopener">release ↗</a>` : ''}</p>` : ''}
      <ul class="ff-eps-parts">${parts}</ul>
      <p class="muted ff-eps-track">${trackLine}${oosLine}${cardLine} The range and probability come from these walk-forward misses, sized to the company's usual EPS; they held 80% of the time out of sample.</p>
    </div>`;
  }

  function ledgerTable(rows) {
    if (!rows || !rows.length) return '';
    return `<table class="ff-eps-table"><thead><tr><th>Quarter</th><th>Frozen</th><th>Estimate</th><th>80% range</th><th>Last year</th><th>Actual</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${esc(dateL(r.target_end))}</td><td>${esc(dateL(r.frozen_at))}${r.locked ? '' : ' <span class="muted">(updating)</span>'}</td><td>${usd(r.point)}</td><td>${usd(r.p10)} – ${usd(r.p90)}</td><td>${usd(r.year_ago)}</td><td>${r.actual == null ? '<span class="muted">not filed yet</span>' : usd(r.actual)}</td></tr>`).join('')}</tbody></table>`;
  }

  function fold(title, body) { return body ? `<details class="ff-eps-fold"><summary>${esc(title)}</summary>${body}</details>` : ''; }

  function details(c, f, score, signals, peers, gaap, research, fundamental, fstats, card) {
    const fm = fundamental?.forecast, out = [];
    if (fm) {
      const d = fm.inputs || {};
      out.push(fold('How the fundamental estimate is built', rows([
        ['Estimate', usd(fm.point)], ['Business stage', String(fm.company_stage || '—').replace('_', ' ')],
        ['Quarter revenue', num(d.revenue) ? '$' + (d.revenue / 1e9).toFixed(2) + 'B' : '—'], ['Operating margin', percent(d.operating_margin)],
        ['Other income / revenue', percent(d.nonoperating_margin)], ['Normalized tax rate', percent(d.normalized_tax_rate)],
        ['Diluted shares', num(d.diluted_shares) ? (d.diluted_shares / 1e9).toFixed(3) + 'B' : '—'],
        ['Same quarter last year (GAAP / tax-normalized)', usd(fm.eps_gaap_last_year) + ' / ' + usd(fm.normalized_eps_last_year)],
        ...['bear', 'base', 'bull'].map(k => fm.scenarios?.[k] && [k[0].toUpperCase() + k.slice(1) + ' case (revenue ' + percent(fm.scenarios[k].revenue_shock) + ', margin ' + percent(fm.scenarios[k].margin_shock) + ')', usd(fm.scenarios[k].eps)]),
      ]) + '<p class="muted">From the company’s own 10-Q and 10-K figures as first filed; a fourth quarter is the 10-K year less the nine months. A one-off tax quarter is normalized; the scenarios move revenue and margin by their usual swings.</p>'));
    }
    if (gaap?.forecast || gaap?.reference) {
      const g = gaap.forecast, gt = gaap.gate || {};
      out.push(fold('Seasonal model (EPS history only)', rows([
        g && ['Estimate', usd(g.eps_point)], gaap.reference && ['Same quarter last year', usd(gaap.reference.year_ago_eps)],
        ['Walk-forward on this company', gt.n ? `${gt.n} quarters · relative error ${pct0(gt.rel_error_model)} vs year-ago ${pct0(gt.rel_error_year_ago)}` : '—'],
        ['Shown', gt.status === 'PASSED' ? 'yes — it beat “same quarter last year”' : 'no — “same quarter last year” did as well or better'],
      ])));
    }
    if (f) {
      const hist = score.tests.slice(-6).map(x => `<tr><td>${esc(dateL(x.reported))}</td><td>${usd(x.baseline)}</td><td>${usd(x.actual)}</td></tr>`).join('');
      out.push(fold('Wall Street details', rows([
        ['Consensus (adjusted EPS)', usd(f.consensus) + ' · ' + f.analyst_n + ' analysts'],
        num(f.bear) && ['Lowest / highest estimate', usd(c?.analysts?.periods?.find(x => x.period === '0q')?.eps?.low) + ' / ' + usd(c?.analysts?.periods?.find(x => x.period === '0q')?.eps?.high)],
        ['Estimate revisions, 30 days', signals.ratings.revision_30d ? (signals.ratings.revision_30d.upLast30days || 0) + ' up / ' + (signals.ratings.revision_30d.downLast30days || 0) + ' down' : '—'],
        ['Rating changes on file', signals.ratings.upgrades + ' up / ' + signals.ratings.downgrades + ' down'],
      ]) + (hist ? `<table class="ff-eps-table"><thead><tr><th>Reported</th><th>Consensus</th><th>Actual (adjusted)</th></tr></thead><tbody>${hist}</tbody></table>` : '')));
    }
    const pm = signals.polymarket, ks = signals.kalshi || [];
    if (pm || ks.length) out.push(fold('Prediction markets', rows([
      pm && ['Polymarket “beats estimates” · latest Yes price', pct0(pm.p) + ' (' + esc(pm.observed_at) + ')' + (pm.url ? ` <a href="${esc(pm.url)}" target="_blank" rel="noopener">market ↗</a>` : '')],
      ...ks.map(m => [m.title, m.outcomes.filter(o => num(o.p)).slice(0, 2).map(o => esc(o.name) + ': ' + pct0(o.p)).join(' / ') || '—']),
    ]) + '<p class="muted">Market prices for the report, not EPS forecasts; they do not enter the estimate.</p>'));
    if (peers) out.push(fold('Peers that have already reported', rows(['upstream', 'downstream', 'subindustry', 'industry'].map(k => [
      {upstream: 'Its suppliers', downstream: 'Its customers', subindustry: 'Same SIC industry', industry: 'Same sector'}[k],
      peers[k]?.count ? 'average surprise ' + percent(peers[k].mean_surprise) + ' · ' + peers[k].count + ' reports' : '—']))));
    const fs = fstats || {}, ff = fs.fundamental || {}, oos = fs.out_of_sample || {}, wide = research?.overall, gb = research?.gaap_first_filed_backtest?.overall, pmk = research?.resolved_prediction_markets;
    const checks = rows([
      ff.n && ['Fundamental model, walk-forward', `${ff.n} company-quarters (${fs.companies} companies): relative error ${pct0(ff.rel_error_model)} vs year-ago ${pct0(ff.rel_error_baseline)}; closer in ${pct0(ff.closer_share)}; median miss ${usd(ff.median_ae_model)} vs ${usd(ff.median_ae_baseline)}`],
      oos.paired?.n && ['With a consensus, out of sample', `${oos.paired.n} quarters: estimate ${pct0(oos.paired.blend.rel_error_model)}, converted consensus ${pct0(oos.paired.street.rel_error_model)}, fundamentals ${pct0(oos.paired.fundamental.rel_error_model)}, year-ago ${pct0(oos.paired.blend.rel_error_baseline)} (relative error)`],
      oos.fundamental_range?.n && ['80% ranges, out of sample', `held ${pct0(oos.fundamental_range.coverage_80)} (fundamentals)${oos.blend_range ? ', ' + pct0(oos.blend_range.coverage_80) + ' (with consensus)' : ''}`],
      oos.probability?.n && ['“Above last year” probability', `Brier ${oos.probability.brier} vs ${oos.probability.brier_base_rate} for the base rate (lower is better)`],
      gb?.n && ['Seasonal model, walk-forward', `${gb.n} quarters: relative error ${pct0(gb.rel_error_model)} vs year-ago ${pct0(gb.rel_error_baseline)}`],
      wide?.n && ['Consensus + past-surprise correction (adjusted EPS)', `${wide.n} reports: median miss ${usd(wide.median_ae_model)} vs consensus ${usd(wide.median_ae_consensus)}`],
      pmk?.n && ['Polymarket beat markets', `${pmk.n} resolved: Brier ${Number(pmk.brier).toFixed(3)} vs ${Number(pmk.base_rate_brier).toFixed(3)} base rate`],
      card?.frozen && ['Frozen forecasts', `${card.frozen} frozen, ${card.scored} scored${card.scored ? ': closer than last year in ' + pct0(card.vs_year_ago?.closer_share) + ', median miss ' + usd(card.vs_year_ago?.median_ae_model) : ''}`],
    ]);
    out.push(fold('How well these models have done', checks + '<p class="muted">Relative error = miss ÷ the company’s usual |EPS|, capped at 5×; medians and relative errors, because a few companies with huge per-share figures dominate dollar averages. Analyst estimates are Yahoo’s archived pre-report consensus, not audited point-in-time vintages.</p>'));
    return out.join('');
  }

  async function mount(body, ctx) {
    if (!body || !ctx?.cik) return;
    const box=document.createElement('section'); box.className='section ff-eps-research'; box.setAttribute('aria-label','EPS forecast');
    box.innerHTML='<p class="muted">Loading the EPS forecast…</p>'; body.append(box);
    const cik=encodeURIComponent(String(ctx.cik)), ticker=String(ctx.ticker||'').replace(/[^A-Z0-9.-]/ig,'').toUpperCase();
    const path='disclosures/data/';
    const [c,g,wide,fundamental,fstats,card]=await Promise.all([
      get(path+'consensus/c/'+cik+'.json').catch(()=>null),
      get('data/eps-gaap/'+cik+'.json').catch(()=>null),
      get('data/eps-research/backtest.json').catch(()=>null),
      get('data/eps-fundamental/'+cik+'.json').catch(()=>null),
      get('data/eps-fundamental/backtest.json').catch(()=>null),
      get('data/eps-fundamental/scorecard.json').catch(()=>null)
    ]);
    if (!box.isConnected || (ctx.here && !ctx.here())) return;
    const asof=new Date().toISOString().slice(0,10),f=forecast(c,asof),score=trailingTest(c,asof);
    const signals=metrics(c,null,null,asof);
    const peers=ticker?await loadPeerSignals(ticker,f?.period,asof).catch(()=>null):null;
    if (!box.isConnected || (ctx.here && !ctx.here())) return;
    box.innerHTML = `<div class="section-head"><h2>EPS forecast</h2><span class="muted">GAAP diluted EPS from the filings, Wall Street and the company's guidance</span></div>
      ${headline(fundamental?.headline, fundamental?.track, fstats?.out_of_sample, card, g, f)}
      ${fundamental?.ledger?.length ? `<h3>This company's frozen forecasts</h3><p class="muted">Each quarter's estimate is updated until the report, then frozen and scored against the 10-Q.</p>${ledgerTable(fundamental.ledger)}` : ''}
      <div id="ff-eps-preview"></div>
      ${details(c, f, score, signals, peers, g, wide, fundamental, fstats, card)}`;
    if (ctx.preview) {                      // the Disclosure Hub's earnings preview: beat odds, options-implied move, read-through
      const el = box.querySelector('#ff-eps-preview');
      el.innerHTML = '<h3>Earnings preview</h3><div></div>';
      try { if (!(await ctx.preview(el.lastElementChild))) el.remove(); } catch (e) { el.remove(); }
    }
  }
  window.FFEPSResearch={mount,forecast,trailingTest,publicHistory,metrics,peerSignals,bias,headline};
})();
