/* Filing Flows EPS research: historical reported EPS validation, not a live forecast.
 * Source: vivek-v-rao/Earnings-Dates; 2025 held-out research evaluation.
 * Split-adjusted EPS, ticker survivorship and retrospective release timestamps preclude PIT claims.
 * No live EPS forecast is displayed unless a validated source is separately wired in.
 */
(function () {
  'use strict';
  const history = {
    AAPL: [['2025-07-31',1.633,1.57],['2025-10-30',1.751,1.85]],
    MSFT: [['2025-07-30',3.324,3.65],['2025-10-29',3.645,3.72]],
    NVDA: [['2025-08-27',0.743,1.05],['2025-11-19',1.011,1.30]],
    AMZN: [['2025-07-31',1.659,1.68],['2025-10-30',1.775,1.95]],
    GOOGL: [['2025-07-23',2.645,2.31],['2025-10-29',2.346,2.87]],
    META: [['2025-07-30',6.776,7.14],['2025-10-29',7.616,7.25]],
    TSLA: [['2025-07-23',0.448,0.33],['2025-10-22',0.499,0.39]],
    WMT: [['2025-08-21',0.592,0.68],['2025-11-20',0.647,0.77]],
    JPM: [['2025-07-15',5.864,4.96],['2025-10-14',4.581,5.07]]
  };
  function mount(root, ctx) {
    if (!root || !ctx || !ctx.ticker || !root.isConnected) return;
    const ticker = String(ctx.ticker).toUpperCase();
    const rows = history[ticker] || [];
    const sec = document.createElement('section');
    sec.className = 'section ff-eps-research';
    sec.setAttribute('aria-label', 'EPS forecast research and historical performance');
    const title = document.createElement('div');
    title.className = 'section-head';
    const h = document.createElement('h2'); h.textContent = 'EPS forecast research';
    const subtitle = document.createElement('span');
    subtitle.className = 'muted';
    subtitle.textContent = 'Historical holdout • not a current-quarter EPS forecast';
    title.append(h, subtitle); sec.append(title);
    const status = document.createElement('p');
    status.className = 'muted';
    status.textContent = 'Live next-quarter GAAP EPS: unavailable. Point-in-time EPS observations and an audited latest-quarter forecast have not been connected. No estimated EPS is fabricated from net income.';
    sec.append(status);
    const info = document.createElement('p');
    info.textContent = '2025 held-out study: 8,350 observations • stage-based model MAE $0.8404 vs prior-year-quarter baseline $1.4602 • growth-direction accuracy 70.87% • nominal 80% interval coverage 75.34%.';
    sec.append(info);
    const caveat = document.createElement('p'); caveat.className='muted';
    caveat.textContent = 'Preliminary research: historical EPS values may be split-adjusted; the dataset is survivorship-biased and lacks independently validated historical publication timestamps. 13F, FRED, Polymarket and supply-chain improvements were NOT tested in these numbers.';
    sec.append(caveat);
    if (rows.length) {
      const t = document.createElement('table');
      t.className = 'ff-eps-table';
      const cap = document.createElement('caption');
      cap.textContent = ticker+' — illustrative 2025 holdout predictions vs reported EPS (USD/share)';
      t.append(cap);
      const tr=document.createElement('tr');
      ['Report date','Historical prediction','Reported EPS','Absolute error'].forEach(x=>{
        const th=document.createElement('th'); th.scope='col';th.textContent=x;tr.append(th);
      }); const thead=document.createElement('thead');thead.append(tr);t.append(thead);
      const tbody=document.createElement('tbody');
      rows.forEach(([date,pred,actual])=>{
        const tr=document.createElement('tr');
        [date,pred.toFixed(3),actual.toFixed(3),Math.abs(pred-actual).toFixed(3)].forEach(v=>{
          const td=document.createElement('td');td.textContent=v;tr.append(td);
        });tbody.append(tr);
      });t.append(tbody);sec.append(t);
    }
    const link=document.createElement('a');
    link.href='https://github.com/vivek-v-rao/Earnings-Dates';
    link.target='_blank';link.rel='noopener noreferrer';
    link.textContent='Historical EPS research dataset ↗';
    sec.append(link);
    root.append(sec);
  }
  window.FFEPSResearch={mount};
})();
