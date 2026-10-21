/* Actual-source company EPS research, refreshed with the site's published consensus,
 * Smart Money and macro snapshots. Forecast basis: Yahoo analyst/reported EPS (not SEC GAAP).
 * Avoids claiming measured EPS skill for price-alpha, Polymarket or rating signals.
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
    const adjustment = past.length ? clamp(mean(past) * k, -0.25 * Math.max(Math.abs(+c.avg), .5), 0.25 * Math.max(Math.abs(+c.avg), .5)) : 0;
    const estimate = Number(c.avg) + adjustment;
    const prior = valid(c.yearAgoEps) ? Number(c.yearAgoEps) : null;
    const errors = past.length ? past.map(x => x - adjustment) : [];
    // This is NOT a calibrated confidence interval; only show descriptive sensitivity.
    const spread = errors.length >= 3 ? Math.max(.05, mean(errors.map(x => Math.abs(x))) * 1.5) : null;
    const beats = past.filter(x => x > 0).length;
    return {consensus: +c.avg, median: estimate, adjustment, past_n: past.length, analyst_n: +c.numberOfAnalysts,
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
      const delta = clamp(mean(prev) * prev.length / (prev.length + 8),
        -.25 * Math.max(Math.abs(+rows[i].eps_est), .5), .25 * Math.max(Math.abs(+rows[i].eps_est), .5));
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
    const mk = (doc?.markets || []).find(x => x.kind === 'beat' && !x.closed &&
      x.end && !later(asof, x.end) && (!a.next_earnings?.date ||
      Math.abs(safeTime(x.end + 'T00:00:00Z') - safeTime(a.next_earnings.date + 'T00:00:00Z')) < 20 * 86400000));
    if (mk) {
      let p = mk.outcomes?.find(x => /^yes$/i.test(x.q || x.name || ''))?.p;
      if (valid(p)) signals.polymarket = {p: +p, title: mk.title, url: mk.url, source: mk.source};
    }
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
  function el(tag, value, klass) {
    const d = document.createElement(tag); if (klass) d.className = klass;
    d.textContent = value; return d;
  }
  function line(root, a, b) {
    const x=el('div','', 'ff-eps-row');x.append(el('span',a),el('strong',b));root.append(x);
  }
  function section(root, title) {root.append(el('h3',title));}
  async function get(url) {
    const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);return r.json();
  }
  function draw(root, c, f, score, signals, peers) {
    root.textContent='';
    section(root, 'Next reported EPS · probabilistic research');
    root.append(el('p','Live source: analyst EPS consensus + shrinkage correction from the company’s previously released EPS surprises. Adjusted/reporting EPS basis; NOT SEC GAAP diluted EPS.','muted'));
    if (!f) {root.append(el('p','Unavailable: no current analyst EPS observations or the source is not point-in-time eligible.','muted'));return;}
    line(root,'Report period', f.period || 'N/A');
    line(root,'Street EPS · '+f.analyst_n+' analysts',money(f.consensus));
    line(root,'Bias-adjusted EPS point estimate',money(f.median));
    line(root,'Prior surprise observations · incremental training',String(f.past_n));
    line(root,'Estimated YoY EPS change',percent(f.yoy));
    line(root,'Empirical P(beat Street EPS) · uncalibrated',percent(f.beat_rate));
    if (f.lower_sensitivity !== null)line(root,'Historical error sensitivity · NOT P10/P90',money(f.lower_sensitivity)+' to '+money(f.upper_sensitivity));
    root.append(el('p','No validated prediction interval or company-specific calibrated win rate is claimed. Each new published result updates the historical correction and next scheduled consensus refresh.','muted'));
    section(root,'Already released peer earnings · availability gated');
    for(const kind of ['upstream','downstream','subindustry','industry']){
      const z=peers?.[kind];
      line(root,kind+' reported EPS / estimate surprise',z&&z.count?
        percent(z.mean_surprise)+' · '+z.count+' company reports':'N/A — none reported / insufficient source');
    }
    root.append(el('p','Signals activate only after a peer’s earnings report is published; suppliers and customers are inferred from the public chain map and should not be treated as audited commercial counterparties. Unannounced peers do not enter the estimate.','muted'));
    section(root,'Smart Money · Market Consensus · Rating change');
    line(root,'Smart Money score (stock alpha, not EPS)',num(signals.smart?.score)?signals.smart.score.toFixed(1):'N/A');
    line(root,'13F group score (not EPS)',num(signals.smart?.f13)?signals.smart.f13.toFixed(1):'N/A');
    line(root,'Analyst rating changes in available history',signals.ratings.upgrades+' upgrades / '+signals.ratings.downgrades+' downgrades');
    const rv=signals.ratings.revision_30d;
    line(root,'EPS estimate revisions (30d)',rv ? (rv.upLast30days||0)+' up / '+(rv.downLast30days||0)+' down':'N/A');
    line(root,'Related Polymarket earnings beat probability',signals.polymarket?percent(signals.polymarket.p):'N/A — no matched market');
    if (signals.polymarket?.url) {const link=el('a','Related prediction-market contract ↗');link.href=signals.polymarket.url;link.rel='noopener';link.target='_blank';root.append(link);}
    section(root,'FRED macro context · joint scenario inputs');
    for(const id of ['DGS2','DGS10','VIXCLS','UNRATE','BAMLH0A0HYM2']) {
      const x=signals.fred?.[id];line(root,id,x?x.value+' ('+x.period+')':'N/A');
    }
    root.append(el('p','Market, rating and macro signals are displayed as contextual evidence only; no unvalidated EPS coefficients are assigned. Historical FRED series are not ALFRED vintages, so they are excluded from the walk-forward EPS score.','muted'));
    section(root,'Company EPS historical record · independent of Smart Money alpha');
    if (score.tests.length) {
      line(root,'Retrospective test observations',String(score.tests.length));
      line(root,'Bias-corrected model MAE',money(score.mae));
      line(root,'Uncorrected analyst estimate MAE',money(score.baseline_mae));
      const table=el('table','', 'ff-eps-table'), head=el('tr','');
      for (const s of ['Reported','Pre-report proxy','Actual','Error'])head.append(el('th',s));
      const thead=document.createElement('thead');thead.append(head);table.append(thead);
      const tbody=document.createElement('tbody');
      score.tests.slice(-6).forEach(x=>{const tr=el('tr','');for (const v of [day(x.reported),money(x.forecast),money(x.actual),money(x.error)])tr.append(el('td',v));tbody.append(tr)});
      table.append(tbody);root.append(table);
    } else root.append(el('p','Not enough historical EPS surprises for a chronological retrospective test.','muted'));
    root.append(el('p','Methodological restriction: historical Yahoo analyst estimates and adjusted EPS have not been independently archived at their original prediction cutoffs. This is NOT a verified point-in-time out-of-sample backtest or an investment performance record.','muted'));
  }
  async function mount(body, ctx) {
    if (!body || !ctx?.cik || !ctx.ticker) return;
    const box=el('section','', 'section ff-eps-research');box.setAttribute('aria-label','EPS research');
    const root=el('div','Loading actual EPS source data…');box.append(root);body.append(box);
    const cik=encodeURIComponent(String(ctx.cik)), ticker=String(ctx.ticker).replace(/[^A-Z0-9.-]/ig,'').toUpperCase();
    const path='disclosures/data/';
    const [c,s,r]=await Promise.all([
      get(path+'consensus/c/'+cik+'.json').catch(()=>null),
      get(path+'smart/t/'+encodeURIComponent(ticker)+'.json').catch(()=>null),
      get(path+'debt/rates.json').catch(()=>null)
    ]);
    if (!box.isConnected || (ctx.here && !ctx.here())) return;
    const asof=new Date().toISOString().slice(0,10),f=forecast(c,asof),score=trailingTest(c,asof);
    const signals=metrics(c,s,r,asof);
    const peers=await loadPeerSignals(ticker,f?.period,asof).catch(()=>null);
    if (!box.isConnected || (ctx.here && !ctx.here())) return;
    draw(root,c,f,score,signals,peers);
  }
  window.FFEPSResearch={mount,forecast,trailingTest,publicHistory,metrics,peerSignals};
})();
