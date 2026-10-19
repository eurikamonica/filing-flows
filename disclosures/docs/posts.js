/* Posts — for every company, a ready-to-post X text for each family of charts, with a paragraph of analysis and a short
   narrative, written by fixed rules from the published data (no language model; every number is in the data):
     earnings   the latest quarter (its X thread when the site wrote one)
     markets    Polymarket and Kalshi (what each prices, where they price the same thing) against the options (CBOE: max pain,
                put / call walls, the implied range at the same date) and the hourly ladders' expected value (app/ladders.py)
     flows      13F managers, active ETFs, insiders (open market), insiders' 10b5-1 plan trades and officials, this quarter
                so far and the quarter before (smart/combined/), ETF creations and redemptions, the smart-money score
     capital    where the cash went (capital allocation: buybacks, dividends, capex, acquisitions, debt)
     debt       debt, liquidity, what falls due, the model-implied spread, the latest bond
     rotation   RRG against SPY and against its sector (2-D position, the 3-D spiral of the last weeks, the 4-D measures),
                the momentum clock and the solar system (quarterly figures against its sector's sun), the galaxy
   Shared by the Disclosure Hub and the Sankey site (company page → Posts, the views' "Post" boxes, the owner's X report).
   window.FFPosts: load(ticker, cik) → bundle; build(kind, bundle); all(bundle); box(item); render(el, items); bind(el);
   blocks(item) → X Article blocks. No dependencies. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v, d) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), d == null ? (Math.abs(v) >= 1000 ? 0 : 2) : d) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, a >= 1e7 ? 0 : 1) + 'M' : a >= 1e3 ? '$' + num(a / 1e3, 0) + 'K' : '$' + num(a, 0)); };
  const sbig = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + big(Math.abs(v)) : '—');
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const pts = (v) => (fin(v) ? num(v, Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const day = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || '')); return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : String(s || ''); };
  const cash = (t) => '$' + String(t || '').toUpperCase().replace(/-/g, '.');
  const plural = (n, a, b) => `${num(n)} ${n === 1 ? a : (b || a + 's')}`;
  const xlen = (s) => String(s).replace(/https?:\/\/\S+/g, 'x'.repeat(23)).replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, 'xx').length;
  // the post: lines in order of importance, dropped from the end (never the first, the question or the link) until it fits
  function fit(lines, tail, link, max = 280) {
    const L = lines.filter(Boolean), end = [tail, link].filter(Boolean).join(' ');
    while (L.length > 1 && xlen(L.join(' ') + ' ' + end) > max) L.splice(L.length - 1, 1);
    let s = (L.join(' ') + (end ? ' ' + end : '')).trim();
    if (xlen(s) > max) s = s.slice(0, Math.max(0, s.length - (xlen(s) - max) - 1)).replace(/\s+\S*$/, '') + '…' + (link ? ' ' + link : '');
    return s;
  }

  // ---------------------------------------------------------------- where the data is
  const SRC = ((typeof document !== 'undefined' && document.currentScript && document.currentScript.src) || '').replace(/[^/]*$/, '');
  const HUB = SRC || 'disclosures/';                               // .../disclosures/
  const SITE = HUB.replace(/disclosures\/$/, '');                  // the Sankey site
  const siteURL = () => { const s = SITE || (typeof location !== 'undefined' ? location.origin + '/' : ''); return /^https?:/.test(s) ? s : 'https://filing-flows.com/'; };
  const cacheJ = new Map();
  const get = (url) => {
    if (!cacheJ.has(url)) cacheJ.set(url, fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    return cacheJ.get(url);
  };
  let remote = null;
  const ladders = (path) => (remote || (remote = get(HUB + 'data/remote.json'))).then((cfg) =>
    (cfg && cfg.ladders ? get(cfg.ladders + path) : Promise.resolve(null)).then((d) => d || get(HUB + 'data/ladders/' + path)));
  const fileT = (t) => String(t || '').toUpperCase().replace(/\./g, '-');
  const L = {
    cons: (cik) => (cik ? get(`${HUB}data/consensus/c/${+cik}.json`) : Promise.resolve(null)),
    lad: (t) => ladders('t/' + fileT(t) + '.json'),
    opt: (t) => get(`${HUB}data/market/options/${fileT(t)}.json`),
    smart: (t) => get(`${HUB}data/smart/t/${fileT(t).replace(/[^A-Za-z0-9-]/g, '_')}.json`),
    combIndex: () => get(`${HUB}data/smart/combined/index.json`),
    comb: (k) => get(`${HUB}data/smart/combined/${k}.json`),
    etf: (t) => get(`${HUB}data/etf/by/${encodeURIComponent(fileT(t))}.json`).then((d) => d || get(`${HUB}data/etf/by/${encodeURIComponent(String(t).toUpperCase())}.json`)),
    holders: (t) => get(`${HUB}data/holders/${encodeURIComponent(String(t).toUpperCase())}.json`),
    debt: (cik) => (cik ? get(`${HUB}data/debt/c/${+cik}.json`) : Promise.resolve(null)),
    site: (cik) => (cik ? get(`${SITE}data/c/${+cik}.json`) : Promise.resolve(null)),
    rrg: () => get(`${HUB}data/market/history/rrg.json`),
    hist: (t) => get(`${HUB}data/market/history/t/${fileT(t)}.json`),
    galaxy: () => get(`${HUB}data/market/history/galaxy.json`),
    rot: () => get(`${HUB}data/market/rotation.json`),
    options: () => get(`${HUB}data/market/options.json`),
    opt13: () => get(`${HUB}data/market/options13f.json`),
  };
  const KINDS = [['earnings', 'Earnings (Sankey)'], ['moves', 'Market move: the stock against its normal range'], ['optmoves', 'Options move: IV, put/call, gamma, 13F options'],
    ['markets', 'Prediction markets & options'], ['events', '8-Ks and news'], ['insiders', 'Insiders (Form 4, 10b5-1 plans)'], ['officials', 'Officials\' trades (House, Senate)'],
    ['flows', 'Flows: 13F, ETFs, insiders, officials'], ['capital', 'Capital allocation'], ['debt', 'Debt & rates'], ['rotation', 'Rotation: RRG 2-D / 3-D / 4-D, clock, solar system, galaxy']];
  const NEEDS = { earnings: ['site'], markets: ['cons', 'lad', 'opt'], flows: ['smart', 'comb', 'etf', 'holders'], capital: ['site'], debt: ['debt'],
    rotation: ['rrg', 'hist', 'galaxy', 'rot'], events: ['holders'], insiders: ['holders'], officials: ['holders'], moves: ['options', 'hist', 'lad', 'rrg'],
    optmoves: ['options', 'opt', 'opt13'] };

  async function load(ticker, cik, kinds) {
    const want = new Set((kinds || KINDS.map((k) => k[0])).flatMap((k) => NEEDS[k] || []));
    const t = String(ticker || '').toUpperCase(), B = { ticker: t, cik: cik ? +cik : null };
    const jobs = [];
    const take = (k, p) => jobs.push(p.then((v) => { B[k] = v; }).catch(() => { B[k] = null; }));
    if (want.has('site')) take('site', L.site(cik));
    if (want.has('cons')) take('cons', L.cons(cik));
    if (want.has('lad') && t) take('lad', L.lad(t));
    if (want.has('opt') && t) take('opt', L.opt(t));
    if (want.has('smart') && t) take('smart', L.smart(t));
    if (want.has('etf') && t) take('etf', L.etf(t));
    if (want.has('holders') && t) take('holders', L.holders(t));
    if (want.has('debt')) take('debt', L.debt(cik));
    if (want.has('comb')) take('comb', L.combIndex().then(async (ix) => {
      if (!ix) return null;
      const keys = ['prev', 'prev2', 'qtd'].filter((k) => (ix.periods || []).some((p) => p.key === k));
      const files = await Promise.all(keys.map((k) => L.comb(k)));
      const out = { periods: {}, labels: ix.labels || {} };
      keys.forEach((k, i) => {
        const d = files[i], per = ix.periods.find((p) => p.key === k);
        if (!d) return;
        const F = d.fields, row = (d.rows || []).find((r) => String(r[0]).toUpperCase() === t || String(r[0]).toUpperCase() === fileT(t));
        out.periods[k] = { per, row: row ? Object.fromEntries(F.map((f, j) => [f, row[j]])) : null };
      });
      return out;
    }));
    if (want.has('rrg')) take('rrg', L.rrg());
    if (want.has('hist') && t) take('hist', L.hist(t));
    if (want.has('galaxy')) take('galaxy', L.galaxy());
    if (want.has('rot')) take('rot', L.rot());
    if (want.has('options')) take('options', L.options());
    if (want.has('opt13')) take('opt13', L.opt13());
    await Promise.all(jobs);
    if (!B.cik && B.cons && B.cons.cik) B.cik = B.cons.cik;
    const name = (B.site && B.site.profile && B.site.profile.name) || (B.cons && B.cons.name) || (B.debt && B.debt.name) || (B.smart && B.smart.name) || t;
    B.name = String(name).replace(/&amp;/g, '&');
    return B;
  }
  const co = (B) => `${cash(B.ticker)}`;
  const link = (B, tab) => `${siteURL()}#c-${B.cik}${tab ? '-' + tab : ''}`;

  // ---------------------------------------------------------------- earnings
  function earnings(B) {
    const c = B.site;
    if (!c || !(c.quarters || []).length) return null;
    const q = c.quarters[0], h = q.headline || {}, tk = B.ticker || ((c.profile.tickers || [])[0]) || '';
    const thread = (q.x_thread || []).map((x) => x.text);
    const dec = (s) => String(s || '').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"');
    const paras = (q.analysis || []).slice(0, 3).map(dec);
    const om = fin(h.om) ? `${num(h.om, 1)}% operating margin` : '';
    const story = `${B.name} ${dec(q.label)}: revenue ${dec(h.rev_fmt) || big(h.revenue)}${fin(h.yoy) ? ` (${h.yoy > 0 ? '+' : ''}${num(h.yoy, 0)}% Y/Y)` : ''}, net ${dec(h.ni_fmt) || big(h.ni)}${om ? ', ' + om : ''}. ${q.form === '8-K' ? 'Preliminary (earnings release); the 10-Q replaces it.' : `From the ${q.form}.`}`;
    const post = thread[0] || fit([`${cash(tk)} ${dec(q.label)}: revenue ${dec(h.rev_fmt)}${fin(h.yoy) ? `, ${h.yoy > 0 ? '+' : ''}${num(h.yoy, 0)}% Y/Y` : ''}.`,
      `Net ${dec(h.ni_fmt)}${om ? `, ${om}` : ''}.`, 'Where every dollar went ⬇'], '', link(B));
    return { kind: 'earnings', label: 'Earnings', title: `${B.name} ${dec(q.label)}: where the revenue went`, paras, story, post, thread, link: link(B, ''), q };
  }

  // ---------------------------------------------------------------- prediction markets and options
  const KW = [['deliver', 'deliveries'], ['revenue', 'revenue'], ['subscri', 'subscribers'], ['eps|earnings per share', 'EPS'], ['user', 'users'],
    ['margin', 'margin'], ['capex|capital expend', 'capex'], ['guidance', 'guidance'], ['beat', 'earnings beat'], ['price|close', 'price']];
  const topic = (title) => { const s = String(title || '').toLowerCase(); const k = KW.find(([re]) => new RegExp(re).test(s)); return k ? k[1] : null; };
  const medOf = (m) => (m && m.stats && m.stats.median ? m.stats.median.value : null);
  function markets(B) {
    const C = B.cons || {}, Ld = B.lad || {}, O = B.opt || {};
    const today = new Date().toISOString().slice(0, 10);
    const live = (C.markets || []).filter((m) => !m.closed && (!m.end || m.end >= today));
    const poly = live.filter((m) => m.source === 'polymarket'), kal = live.filter((m) => m.source === 'kalshi');
    const lads = (Ld.open || []).slice().sort((a, b) => String(a.end).localeCompare(String(b.end)));
    if (!poly.length && !kal.length && !lads.length && !fin(O.spot)) return null;
    const T = cash(B.ticker), spot = fin(Ld.spot) ? Ld.spot : fin(O.spot) ? O.spot : (C.analysts || {}).price;
    const near = lads.find((m) => m.period === 'day') || lads[0], wk = lads.find((m) => m.period === 'week'), mo = lads.find((m) => m.period === 'month');
    const beat = poly.find((m) => m.kind === 'beat');
    const paras = [], lines = [];
    const rng = (m) => `${usd(m.q10)}–${usd(m.q90)}`;
    // the crowd
    if (near) {
      const dev = fin(spot) && spot ? near.ev / spot - 1 : null;
      paras.push(`Polymarket's ${near.period === 'day' ? 'daily' : near.period === 'week' ? 'weekly' : ''} ladder for ${day(near.end)} implies an expected close of ${usd(near.ev)}${fin(dev) ? ` (${spct(dev)} from ${usd(spot)})` : ''}, median ${usd(near.median)}, 80% between ${rng(near)}.` +
        [wk && wk !== near ? ` The week (${day(wk.end)}): ${usd(wk.ev)}, 80% ${rng(wk)}.` : '', mo && mo !== near ? ` The month (${day(mo.end)}): ${usd(mo.ev)}, 80% ${rng(mo)}.` : ''].join(''));
      lines.push(`${T} into ${day(near.end)}: Polymarket's ladder implies ~${usd(near.ev)} (80%: ${rng(near)}).`);
    } else if (poly.some((m) => m.kind === 'above' || m.kind === 'bracket')) {
      const m = poly.find((x) => x.kind === 'above' || x.kind === 'bracket');
      paras.push(`Polymarket's "${m.title}" puts the median at ${usd(medOf(m))}.`);
      lines.push(`${T}: Polymarket's median ${usd(medOf(m))} for ${day(m.end)}.`);
    }
    if (beat) {
      paras.push(`Polymarket gives ${pct(beat.p)} that ${B.name} beats the ${usd(beat.eps_strike)} EPS line${beat.report_date ? ` (report ${day(beat.report_date)})` : ''}.`);
      lines.push(`Beat the ${usd(beat.eps_strike)} EPS line? Polymarket ${pct(beat.p)}.`);
    }
    // the options at the same date
    const no = near && near.options;
    if (no && (fin(no.max_pain) || fin(no.q10))) {
      const same = no.exact ? 'expiring the same day' : `of the next expiry (${day(no.exp)})`;
      const inOpt = fin(no.q10) ? ` imply an 80% range of ${usd(no.q10)}–${usd(no.q90)}` : '';
      paras.push(`Options ${same}${inOpt}; max pain ${usd(no.max_pain)}, put wall ${usd(no.put_wall)}, call wall ${usd(no.call_wall)}${fin(no.atm_iv) ? `, at-the-money IV ${pct(no.atm_iv)}` : ''}.` +
        (fin(no.q10) && fin(near.q10) ? (near.q90 - near.q10 > 1.15 * (no.q90 - no.q10) ? ' The crowd\'s range is wider than the options\'.' : no.q90 - no.q10 > 1.15 * (near.q90 - near.q10) ? ' The options price a wider range than the crowd.' : ' The crowd and the options see about the same width.') : ''));
      // one strike side by side
      if (near.strikes && near.p && near.op && fin(spot)) {
        let best = -1, bd = 1e18;
        near.strikes.forEach((k, i) => { if (fin(near.p[i]) && fin(near.op[i]) && Math.abs(k - spot) < bd) { bd = Math.abs(k - spot); best = i; } });
        if (best >= 0) {
          const k = near.strikes[best], a = near.p[best], b = near.op[best];
          paras.push(`Close above ${usd(k)} on ${day(near.end)}: Polymarket ${pct(a)}, options ${pct(b)}${Math.abs(a - b) >= 0.08 ? ` — a ${num(Math.abs(a - b) * 100, 0)}-point gap` : ''}.`);
          lines.push(`Above ${usd(k)}? Polymarket ${pct(a)} vs options ${pct(b)}.`);
        }
      }
      lines.push(`Options: max pain ${usd(no.max_pain)}, walls ${usd(no.put_wall)} / ${usd(no.call_wall)}.`);
    } else if (fin(O.max_pain)) {
      paras.push(`Options (nearest monthly expiry ${day(O.max_pain_exp)}): max pain ${usd(O.max_pain)}, put wall ${usd(O.put_wall)}, call wall ${usd(O.call_wall)}${fin(O.iv30) ? `, 30-day IV ${num(O.iv30, 1)}%` : ''}${fin(O.pc_oi) ? `, put/call open interest ${num(O.pc_oi, 2)}` : ''}.`);
      lines.push(`Options: max pain ${usd(O.max_pain)}, walls ${usd(O.put_wall)} / ${usd(O.call_wall)}.`);
    }
    // Polymarket against Kalshi
    let vs = '';
    const pairs = [];
    if (lads.length) {                                    // the same date on both (index ranges)
      const byEnd = {};
      lads.forEach((m) => { (byEnd[m.end] = byEnd[m.end] || {})[m.source] = m; });
      Object.entries(byEnd).forEach(([e, x]) => { if (x.polymarket && x.kalshi) pairs.push([e, x.polymarket, x.kalshi]); });
    }
    if (pairs.length) {
      const [e, p, k] = pairs[0], f = (v, m) => (m.to_page && m.to_page !== 1 ? pts(v * m.to_page) : usd(v));
      vs = `Same date on both (${day(e)}): Polymarket ${f(p.ev, p)}, Kalshi ${f(k.ev, k)} — ${Math.abs(p.ev * (p.to_page || 1) / (k.ev * (k.to_page || 1)) - 1) < 0.003 ? 'they agree' : 'a gap of ' + spct(p.ev * (p.to_page || 1) / (k.ev * (k.to_page || 1)) - 1)}.`;
    } else {
      const kt = kal.map((m) => [topic(m.title), m]).filter((x) => x[0]), pt = poly.map((m) => [m.kind === 'beat' ? 'earnings beat' : topic(m.title), m]).filter((x) => x[0]);
      const match = kt.find(([tk]) => pt.some(([tp]) => tp === tk));
      if (match) {
        const pm = pt.find(([tp]) => tp === match[0])[1], km = match[1];
        vs = `Both price ${match[0]}: Polymarket "${pm.title}" ${fin(medOf(pm)) ? 'median ' + num(medOf(pm), 2) : fin(pm.p) ? pct(pm.p) : ''}, Kalshi "${km.title}" ${fin(medOf(km)) ? 'median ' + num(medOf(km), 2) : ''}.`;
      } else if (kal.length || poly.length) {
        const kTop = kal.slice().sort((a, b) => (b.volume || 0) - (a.volume || 0))[0];
        const what = [...new Set(kal.map((m) => m.kind === 'kpi' ? 'its KPIs' : m.kind === 'mention' ? 'words said on the earnings call' : 'company events'))];
        vs = `${plural(poly.length, 'open Polymarket market')} and ${plural(kal.length, 'Kalshi market')} on ${B.name}${kal.length ? ` — Kalshi prices ${what.length > 1 ? what.slice(0, -1).join(', ') + ' and ' + what[what.length - 1] : what[0]}${kTop ? ` (largest: "${kTop.title}")` : ''}` : ', none on Kalshi'}; no question is priced on both, so there is no head-to-head.`;
      }
    }
    if (vs) paras.push(vs);
    // how the ladders have done
    const bt = (Ld.backtest_all || []).find((r) => r.bucket === '1–3 days') || (Ld.backtest_all || [])[0];
    if (bt && bt.mae && fin(bt.mae.ev)) paras.push(`Track record (${num(bt.markets)} resolved ladders, read ${bt.bucket} before the close): the expected value missed by ${pct(bt.mae.ev, 1)} on average, the price at the time by ${pct(bt.mae.price, 1)}; the ladders' 80% ranges held ${pct(bt.inside80 && bt.inside80.ladder)} of the time.`);
    const agree = near && no && fin(no.max_pain) ? (Math.abs(near.ev / no.max_pain - 1) < 0.01 ? 'agree' : near.ev > no.max_pain ? 'sit above max pain' : 'sit below max pain') : null;
    const story = near ? `The crowd ${agree === 'agree' ? 'and the options agree' : agree ? agree.replace('sit', 'sits') + ' (' + usd(no.max_pain) + ')' : 'sets the line'} for ${day(near.end)}: ${usd(near.ev)} expected against ${usd(spot)} now${no && fin(no.call_wall) ? `, between the put wall at ${usd(no.put_wall)} and the call wall at ${usd(no.call_wall)}` : ''}. ${pairs.length || vs.startsWith('Both') ? vs : ''}`.trim()
      : paras[0] || '';
    const lk = B.cik ? link(B, 'consensus') : `${siteURL()}disclosures/#consensus`;
    const post = fit(lines, 'Who\'s right — 1) the crowd 2) the options 3) neither? 👇', lk);
    return { kind: 'markets', label: 'Prediction markets & options', title: `${B.name}: what the crowd and the options expect`, paras, story, post, link: lk };
  }

  // ---------------------------------------------------------------- flows
  const GN = { f13: '13F managers', etf: 'active ETFs', ins: 'insiders', plan: '10b5-1 plan trades', gov: 'officials' };
  function flows(B) {
    const P = (B.comb && B.comb.periods) || {}, sm = B.smart && B.smart.now, E = B.etf && B.etf.flows, H = B.holders || {};
    const rows = ['prev', 'qtd', 'prev2'].map((k) => P[k] && P[k].row ? [k, P[k]] : null).filter(Boolean);
    if (!rows.length && !sm && !E) return null;
    const T = cash(B.ticker), paras = [], lines = [];
    const groupLine = (r, short) => ['f13', 'etf', 'ins', 'plan', 'gov'].filter((g) => r[g + '_b'] || r[g + '_s'] || r[g + '_usd'])
      .map((g) => `${GN[g]} ${sbig(r[g + '_usd'])}${short ? '' : ` (${num(r[g + '_b'])} buying · ${num(r[g + '_s'])} selling)`}`).join(', ');
    let headline = null;
    const short = (k, per) => { const q = String(per.label).split(' ')[0] + ' ' + String(per.label).split(' ')[1]; return k === 'prev' ? `${q} (13F reports still arriving)` : k === 'qtd' ? `${q} to date` : q; };
    for (const [k, x] of rows) {
      const r = x.row, lab = short(k, x.per);
      const net = ['f13', 'etf', 'ins', 'gov'].reduce((a, g) => a + (r[g + '_usd'] || 0), 0);
      paras.push(`${lab}: ${groupLine(r)}. Net of the four decision groups ${sbig(net)}${r.plan_usd ? `; with the plan trades ${sbig(net + r.plan_usd)}` : ''}.` +
        (r.groups_buy || r.groups_sell ? ` ${num(r.groups_buy)} group${r.groups_buy === 1 ? '' : 's'} net buying, ${num(r.groups_sell)} net selling.` : ''));
      if (!headline) headline = [lab, r, net];
    }
    if (headline) lines.push(`${T} flows, ${headline[0]}: ${groupLine(headline[1], true)}.`);
    if (E && (E.months || []).length) {
      const n = E.months.length, cov = E.cov || [];
      let j = n - 1; while (j > 0 && fin(cov[j]) && cov[j] < 0.6) j--;
      const net = (E.in[j] || 0) - (E.out[j] || 0), net3 = [0, 1, 2].reduce((a, d) => a + ((E.in[j - d] || 0) - (E.out[j - d] || 0)), 0);
      const mon = (s) => { const m = /^(\d{4})-(\d{2})$/.exec(s || ''); return m ? new Date(Date.UTC(+m[1], +m[2] - 1, 1)).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' }) : s; };
      paras.push(`ETFs holding ${B.ticker} (${num(B.etf.etfs)} of them): creations minus redemptions put ${sbig(net)} into it in ${mon(E.months[j])} and ${sbig(net3)} over three months (each fund's flow × its weight).`);
      lines.push(`ETF creations/redemptions: ${sbig(net)} in ${mon(E.months[j])}.`);
    }
    const plan = (H.insiders || []).filter((x) => x.plan_10b5_1 && x.code === 'S');
    if (plan.length) {
      const tot = plan.reduce((a, x) => a + (x.value || 0), 0), who = [...new Set(plan.map((x) => x.insider))].slice(0, 2);
      paras.push(`10b5-1 plan sales on file (last 120 days): ${plural(plan.length, 'sale')}, ${big(tot)}, by ${who.join(' and ')}${plan.length > 2 ? ' and others' : ''} — pre-arranged, so not a decision taken that day.`);
    }
    const open = (H.insiders || []).filter((x) => !x.plan_10b5_1 && x.code === 'P');
    if (open.length) paras.push(`Open-market purchases by insiders: ${plural(open.length, 'trade')}, ${big(open.reduce((a, x) => a + (x.value || 0), 0))} (latest: ${open[0].insider}, ${day(open[0].date)}).`);
    if (sm && fin(sm.S)) {
      paras.push(`Smart-money score ${sm.S > 0 ? '+' : ''}${num(sm.S, 0)} on a scale of −100 to +100 (each trader's vote weighted by how often their past trades beat SPY over the next three months; ${num(sm.n)} votes; everyone counted alike ${sm.raw > 0 ? '+' : sm.raw < 0 ? '−' : ''}${num(Math.abs(sm.raw), 0)}).`);
      lines.push(`Smart-money score ${sm.S > 0 ? '+' : ''}${num(sm.S, 0)} of ±100.`);
    }
    const sh = (H.short || []).slice(-1)[0];
    if (sh && fin(sh[1])) paras.push(`Short interest ${big(sh[1]).replace('$', '')} shares on ${day(sh[0])}${fin(sh[2]) ? ` (${sh[2] > 0 ? '+' : ''}${sh[2]}% vs the prior date)` : ''}${fin(sh[3]) ? `, ${sh[3]} days to cover` : ''}.`);
    const r = headline && headline[1];
    const split = r && ['f13', 'etf', 'ins', 'gov'].filter((g) => r[g + '_usd']);
    const ups = split ? split.filter((g) => r[g + '_usd'] > 0) : [], downs = split ? split.filter((g) => r[g + '_usd'] < 0) : [];
    const story = r ? (ups.length && downs.length ? `The disclosed money is split on ${B.name}: ${ups.map((g) => GN[g]).join(' and ')} adding, ${downs.map((g) => GN[g]).join(' and ')} cutting.`
      : ups.length ? `Every group that traded ${B.name} in ${headline[0]} was a net buyer.` : downs.length ? `Every group that traded ${B.name} in ${headline[0]} was a net seller.` : '') +
      (sm && fin(sm.S) ? ` The traders with the best records lean ${sm.S > 20 ? 'to buying' : sm.S < -20 ? 'to selling' : 'neither way'} (${sm.S > 0 ? '+' : ''}${num(sm.S, 0)}).` : '')
      : paras[0];
    const lk = B.cik ? link(B, '') : `${siteURL()}disclosures/#smart/${encodeURIComponent(B.ticker)}`;
    const post = fit(lines, ups.length && downs.length ? 'Who has it right? 1) the funds 2) the insiders 3) Washington 👇' : 'Signal or noise? 1) signal 2) noise 3) too early 👇', lk);
    return { kind: 'flows', label: 'Flows', title: `${B.name}: who is buying and selling`, paras, story, post, link: lk };
  }

  // ---------------------------------------------------------------- capital allocation
  const CAPN = { ocf: 'operating cash flow', capex: 'capex', realestate: 'real estate', acq: 'acquisitions', sales: 'asset sales', buyback: 'buybacks',
    div: 'dividends', withhold: 'taxes on employee shares', stock: 'stock issued', borrow: 'net borrowing', nci: 'minority holders', cash: 'cash on the balance sheet' };
  function capital(B) {
    const Q = B.site && B.site.quality && B.site.quality.cap;
    if (!Q) return null;
    const P = Q.ttm || (Q.fy || [])[Q.fy.length - 1] || (Q.q || [])[Q.q.length - 1];
    if (!P || !P.items) return null;
    const it = P.items, T = cash(B.ticker), ocf = it.ocf;
    const uses = Object.entries(it).filter(([k, v]) => v < 0 && CAPN[k] && k !== 'cash').sort((a, b) => a[1] - b[1]);
    const total = uses.reduce((a, [, v]) => a - v, 0);
    const share = (v) => (total ? pct(-v / total) : '—');
    const lab = P.kind === 'ttm' ? 'the last twelve months' : String(P.label || P.end);
    const paras = [`Over ${lab}, ${B.name} generated ${big(ocf)} of operating cash flow and put ${big(total)} to work: ` +
      uses.slice(0, 5).map(([k, v]) => `${CAPN[k]} ${big(-v)} (${share(v)})`).join(', ') + '.'];
    const ret = -((it.buyback || 0) + (it.div || 0));
    if (ret && fin(ocf) && ocf) paras.push(`Returned to shareholders: ${big(ret)} (buybacks ${big(-(it.buyback || 0))}, dividends ${big(-(it.div || 0))}) — ${pct(ret / ocf)} of operating cash flow.`);
    if (fin(it.borrow) && Math.abs(it.borrow) > 0.05 * Math.abs(ocf || 1)) paras.push(`It ${it.borrow > 0 ? 'borrowed' : 'repaid'} a net ${big(Math.abs(it.borrow))}${fin(it.cash) ? `, and ${it.cash > 0 ? 'drew' : 'added'} ${big(Math.abs(it.cash))} ${it.cash > 0 ? 'from' : 'to'} its cash` : ''}.`);
    const S2 = (Q.shares || []).filter((x) => fin(x.diluted) && !(x.split || []).includes('diluted')).slice(-2);
    if (S2.length === 2) paras.push(`Diluted share count ${spct(S2[1].diluted / S2[0].diluted - 1)} in ${S2[1].label} (${num(S2[1].diluted / 1e6, 1)}M)${fin(S2[1].sbc) ? `; share-based pay ${big(S2[1].sbc)}` : ''}${fin(S2[1].bb) ? `, buybacks ${big(S2[1].bb)}` : ''}.`);
    const top = uses[0];
    const story = top ? `${B.name}'s biggest use of cash is ${CAPN[top[0]]}: ${big(-top[1])}, ${share(top[1])} of everything it spent${ret ? `; shareholders got ${big(ret)}` : ''}.` : paras[0];
    const lines = [`${T}, ${lab}: ${big(ocf)} of operating cash flow →`, uses.slice(0, 4).map(([k, v]) => `${CAPN[k]} ${big(-v)}`).join(', ') + '.', ret ? `${pct(ret / (ocf || 1))} of OCF went back to shareholders.` : ''];
    const post = fit(lines, 'Right priorities? 1) yes 2) more buybacks 3) more investment 👇', link(B, 'capital'));
    return { kind: 'capital', label: 'Capital allocation', title: `${B.name}: where the cash went`, paras, story, post, link: link(B, 'capital') };
  }

  // ---------------------------------------------------------------- debt
  function debt(B) {
    const D = B.debt;
    if (!D || !D.analysis) return null;
    const A = D.analysis, T = cash(B.ticker), im = A.implied || {};
    const paras = [];
    paras.push(`${B.name} carries ${big(A.total_debt)} of debt against ${big(A.cash_and_investments)} of cash and investments: net debt ${big(A.net_debt)}${fin(A.net_leverage) ? `, ${num(A.net_leverage, 2)}× EBITDA` : ''}${fin(A.interest_coverage) ? `; EBIT covers interest ${num(A.interest_coverage, 1)}×` : ''}.`);
    if (fin(A.due_12m)) paras.push(`${big(A.due_12m)} falls due in the next 12 months${fin(A.liquidity_to_due12) ? `, against ${num(A.liquidity_to_due12, 1)}× that in liquidity` : ''}${fin(A.floating_share) ? `; ${pct(A.floating_share)} of the debt floats (+100 bp would cost ${big(A.plus100bp_interest)} a year)` : ''}.`);
    if (fin(im.calibrated_5y_bps)) paras.push(`The model built from the share price and the balance sheet puts a 5-year spread of about ${num(im.calibrated_5y_bps, 0)} bp on it${im.rating_band ? ` (${im.rating_band} band)` : ''}${fin(im.dd) ? `, distance to default ${num(im.dd, 1)}` : ''}${fin(A.altman_z) ? `; Altman Z ${num(A.altman_z, 1)}` : ''}.`);
    const iss = (D.issues || []).filter((x) => x.coupon != null && x.maturity).sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')))[0];
    if (iss) paras.push(`Latest bond: ${iss.title}${fin(iss.spread_bps) ? `, priced at +${num(iss.spread_bps, 0)} bp over Treasuries` : ''}${iss.date ? ` (${day(iss.date)})` : ''}.`);
    if (fin(A.cushion_score)) paras.push(`Debt cushion score ${num(A.cushion_score, 0)} of 100 (liquidity, coverage, maturities and the market's view together).`);
    const story = `${fin(A.net_debt) && A.net_debt < 0 ? `${B.name} holds more cash than debt (net cash ${big(-A.net_debt)}).` : `${B.name} owes a net ${big(A.net_debt)}.`} ${fin(A.liquidity_to_due12) ? (A.liquidity_to_due12 >= 2 ? 'What falls due this year is well covered.' : A.liquidity_to_due12 >= 1 ? 'What falls due this year is covered, without much room.' : 'Liquidity does not cover what falls due this year.') : ''} ${fin(im.calibrated_5y_bps) ? `The equity-implied spread, ~${num(im.calibrated_5y_bps, 0)} bp, ${im.calibrated_5y_bps < 120 ? 'reads investment grade' : im.calibrated_5y_bps < 350 ? 'reads high yield' : 'reads distressed'}.` : ''}`.replace(/\s+/g, ' ').trim();
    const lines = [`${T} debt check: ${big(A.total_debt)} of debt, ${big(A.cash_and_investments)} cash → net ${big(A.net_debt)}${fin(A.net_leverage) ? ` (${num(A.net_leverage, 1)}× EBITDA)` : ''}.`,
      fin(A.due_12m) ? `${big(A.due_12m)} due in 12 months${fin(A.liquidity_to_due12) ? ` vs ${num(A.liquidity_to_due12, 1)}× liquidity` : ''}.` : '',
      fin(im.calibrated_5y_bps) ? `Equity-implied 5-yr spread ~${num(im.calibrated_5y_bps, 0)} bp${im.rating_band ? ` (${im.rating_band})` : ''}.` : '',
      iss && fin(iss.spread_bps) ? `Latest bond +${num(iss.spread_bps, 0)} bp.` : ''];
    const post = fit(lines, 'As safe as it looks? 1) yes 2) no 3) depends on rates 👇', link(B, 'debt'));
    return { kind: 'debt', label: 'Debt & rates', title: `${B.name}: debt, liquidity and what the market implies`, paras, story, post, link: link(B, 'debt') };
  }

  // ---------------------------------------------------------------- rotation: RRG, clock, solar system, galaxy
  const QN = ['Leading', 'Weakening', 'Lagging', 'Improving'];
  const quad = (x, y) => (x >= 100 ? (y >= 100 ? 0 : 1) : (y < 100 ? 2 : 3));
  function rrgOf(D, ent, bench, n = 10) {                // the hub's RRG formula (rrg.js rrgCalc), weekly
    if (!D || !ent || !bench) return null;
    const t0 = Date.parse(D.start + 'T00:00:00Z'), N = Math.round((Date.parse(D.weeks + 'T00:00:00Z') - t0) / 6048e5) + 1;
    const full = (e) => { const a = new Array(N).fill(null), src = e.c || [], o = Math.round((Date.parse(e.start + 'T00:00:00Z') - t0) / 6048e5); for (let i = 0; i < src.length; i++) if (o + i >= 0 && o + i < N) a[o + i] = src[i]; return a; };
    const C = full(ent), Bm = full(bench);
    const rs = C.map((v, i) => (v != null && Bm[i] != null && Bm[i] > 0 ? 100 * v / Bm[i] : null));
    const sh = 4, long = Math.max(52, 3 * n);
    const ema = (a, span) => { const al = 2 / (span + 1), o = new Array(a.length).fill(null); let m = null, c = 0; for (let k = 0; k < a.length; k++) { if (a[k] == null) { m = null; c = 0; continue; } m = m == null ? a[k] : m + al * (a[k] - m); c++; o[k] = c >= Math.min(span, 6) ? m : null; } return o; };
    const s_ = ema(rs, sh), t_ = ema(s_, n), dev = s_.map((v, k) => (v != null && t_[k] ? 100 * (v / t_[k] - 1) : null));
    const roc = ema(dev.map((v, k) => (k && v != null && dev[k - 1] != null ? v - dev[k - 1] : null)), sh);
    const norm = (a) => a.map((v, k) => { if (v == null) return null; let s2 = 0, m = 0; for (let i = Math.max(0, k - long + 1); i <= k; i++) if (a[i] != null) { s2 += a[i] * a[i]; m++; } return m >= Math.min(long, 26) && s2 > 0 ? 100 + v / Math.sqrt(s2 / m) : null; });
    const x = norm(dev), y = norm(roc);
    let last = N - 1; while (last > 0 && (x[last] == null || y[last] == null)) last--;
    if (x[last] == null) return null;
    const hi = (() => { let h = null, c = 0; for (let j = Math.max(0, last - 51); j <= last; j++) if (C[j] != null) { c++; h = h == null ? C[j] : Math.max(h, C[j]); } return c >= 45 && C[last] != null ? C[last] / h - 1 : null; })();
    const r52 = last >= 52 && rs[last] != null && rs[last - 52] != null ? rs[last] / rs[last - 52] - 1 : null;
    const lr = (A, i) => (A[i] != null && A[i - 1] != null && A[i] > 0 && A[i - 1] > 0 ? Math.log(A[i] / A[i - 1]) : null);
    const sd13 = (A, i) => { const r = []; for (let j = i - 12; j <= i; j++) { if (j < 1) continue; const v = lr(A, j); if (v != null) r.push(v); } if (r.length < 10) return null; const mu = r.reduce((a, b) => a + b, 0) / r.length; return Math.sqrt(r.reduce((a, b) => a + (b - mu) ** 2, 0) / (r.length - 1)); };
    const vr = sd13(C, last), vb = sd13(Bm, last);
    // the spiral: how far and which way it turned over the last 13 weeks (clockwise is the usual rotation)
    let turn = 0, prev = null;
    for (let k = Math.max(1, last - 12); k <= last; k++) {
      if (x[k] == null || y[k] == null) continue;
      const a = Math.atan2(y[k] - 100, x[k] - 100);
      if (prev != null) { let d = a - prev; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; turn += d; }
      prev = a;
    }
    const k4 = Math.max(0, last - 4);
    return { x: x[last], y: y[last], q: quad(x[last], y[last]), dx: x[last] - (x[k4] || x[last]), dy: y[last] - (y[k4] || y[last]), turn,
      dist: Math.hypot(x[last] - 100, y[last] - 100), r52, hi52: hi, vrel: vr != null && vb ? vr / vb - 1 : null, week: new Date(t0 + last * 6048e5).toISOString().slice(0, 10) };
  }
  const heading = (r) => {
    const a = Math.atan2(r.dy, r.dx) * 180 / Math.PI, dir = Math.hypot(r.dx, r.dy) < 0.15 ? 'barely moving' : a > 45 && a <= 135 ? 'gaining momentum' : a > -135 && a <= -45 ? 'losing momentum' : a > -45 && a <= 45 ? 'strengthening against its trend' : 'weakening against its trend';
    return dir;
  };
  function rotation(B) {
    const D = B.rrg, H = B.hist, T = cash(B.ticker);
    const ent = H && H.c ? { id: B.ticker, start: H.start, c: H.c } : null;
    const meta = D && D.tickers ? (D.tickers[B.ticker] || D.tickers[fileT(B.ticker)]) : null;
    const r = D && ent ? rrgOf(D, ent, D.bench) : null;
    const secSer = D && meta && meta.s ? (D.series || []).find((s) => s.group === 'site-sector' && s.sector === meta.s) : null;
    const rs = secSer ? rrgOf(D, ent, secSer) : null;
    const R = B.rot, rc = R && (R.companies || []).find((c) => String(c.t).toUpperCase() === B.ticker || String(c.t).toUpperCase() === fileT(B.ticker));
    const G = B.galaxy;
    if (!r && !rc) return null;
    const paras = [], lines = [];
    if (r) {
      paras.push(`RRG against SPY (weekly, ${day(r.week)}): RS-Ratio ${num(r.x, 1)}, RS-Momentum ${num(r.y, 1)} — the ${QN[r.q]} quadrant${r.q === 0 ? ' (outperforming and gaining)' : r.q === 1 ? ' (still above its trend, losing speed)' : r.q === 2 ? ' (under its trend and losing)' : ' (under its trend, gaining speed)'}, ${num(r.dist, 1)} spreads from the centre, ${heading(r)} over the last four weeks.`);
      const deg = Math.abs(r.turn) * 180 / Math.PI;
      paras.push(`3-D (time as depth): over 13 weeks the line turned ${num(deg, 0)}°${deg >= 330 ? ' (a full loop)' : ''} ${r.turn < 0 ? 'clockwise — the usual rotation, leading → weakening → lagging → improving' : 'counter-clockwise, against the usual rotation'}. 4-D: 12 months vs SPY ${spct(r.r52)}${fin(r.hi52) ? (r.hi52 > -0.005 ? ', at its 52-week high' : `, ${spct(r.hi52)} from its 52-week high`) : ''}${fin(r.vrel) ? `, volatility ${spct(r.vrel, 0)} vs SPY` : ''}.`);
      lines.push(`${T} on the RRG vs SPY: ${QN[r.q]} (RS-Ratio ${num(r.x, 1)}, momentum ${num(r.y, 1)}), ${heading(r)}.`);
    }
    if (rs) {
      paras.push(`Against its own sector (${secSer.name.replace(/ · site companies$/, '')}): ${QN[rs.q]} (RS-Ratio ${num(rs.x, 1)}, momentum ${num(rs.y, 1)})${r ? (rs.q === r.q ? ' — the same quadrant as against the market' : '') : ''}.`);
      lines.push(`Vs its sector: ${QN[rs.q]}.`);
    }
    if (G && G.galaxies && meta && meta.s && G.galaxies[meta.s]) {
      const g = G.galaxies[meta.s], k = (g.x || []).length - 1, gx = 100 + (g.x[k] || 0) / 100, gy = 100 + ((g.y || [])[k] || 0) / 100;
      const fx = (g.fx || []).filter((v) => v != null).slice(-1)[0], fy = (g.fy || []).filter((v) => v != null).slice(-1)[0];
      paras.push(`The galaxy (sectors as galaxies around the market): ${g.name} sits in ${QN[quad(gx, gy)]}${fin(fx) && fin(fy) ? `; the gravity + tidal model's next week points to ${QN[quad(100 + fx / 100, 100 + fy / 100)]}` : ''}.`);
      const star = (G.stars || []).find((s) => String(s[0]).toUpperCase() === B.ticker);
      if (star) { const sx = 100 + (star[4] || 0) / 100, sy = 100 + (star[5] || 0) / 100; paras.push(`As a star of its galaxy: ${QN[quad(sx, sy)]}${fin(star[8]) ? `; next-week forecast vs the sector ${spct(star[8] / 1e4, 2)}` : ''}.`); }
    }
    if (rc && R.fields) {
      const F = R.fields, last = (rc.p || [])[rc.p.length - 1], o = last ? Object.fromEntries(F.map((f, i) => [f, last[i]])) : null;
      const sunP = R.sectors && R.sectors[rc.s] ? R.sectors[rc.s].p : null, SF = R.sun_fields || F;
      const sun = sunP ? Object.fromEntries(SF.map((f, i) => [f, (sunP.find((p) => p[0] === (o && o.cal)) || [])[i]])) : null;
      if (o) {
        const cq = fin(o.dom) && fin(o.rel) ? (o.dom >= 0 ? (o.rel >= 0 ? 'margins rising and the stock beating the S&P 500' : 'margins rising while the stock lags the S&P 500') : (o.rel >= 0 ? 'margins falling while the stock beats the S&P 500' : 'margins falling and the stock lagging')) : '';
        paras.push(`Momentum clock (${String(o.cal || '').replace(/^CY(\d{4})Q(\d)$/, 'Q$2 $1')}): operating margin ${fin(o.dom) ? (o.dom > 0 ? '+' : '') + num(o.dom, 1) + ' pts vs a year earlier' : '—'}, stock ${fin(o.rel) ? spct(o.rel / 100) : '—'} vs the S&P 500 in the quarter${fin(o.revg) ? `, revenue ${spct(o.revg / 100, 0)} Y/Y` : ''} — ${cq || 'not enough figures'}.` +
          (sun && fin(sun.dom) && fin(o.dom) ? ` Solar system: its sector's sun sits at ${(sun.dom > 0 ? '+' : '') + num(sun.dom, 1)} pts and ${spct((sun.rel || 0) / 100)}, so the company orbits ${o.dom > sun.dom && o.rel > (sun.rel || 0) ? 'ahead of' : o.dom < sun.dom && o.rel < (sun.rel || 0) ? 'behind' : 'beside'} its sector.` : ''));
        if (cq) lines.push(`Momentum clock: ${cq}.`);
      }
    }
    const story = r ? `${B.name} is in the ${QN[r.q]} quadrant against the market${rs ? ` and ${QN[rs.q]} against its sector` : ''}, ${heading(r)}. ${r.turn < -0.3 ? 'The rotation runs the usual way, clockwise' : r.turn > 0.3 ? 'The rotation runs against the usual direction' : 'The line has not turned much'}${r.q === 3 ? ': next stop, if it continues, is Leading' : r.q === 1 ? ': next stop, if it continues, is Lagging' : ''}.` : paras[0];
    const post = fit(lines, 'Rotation in or out? 1) in 2) out 3) chop 👇', `${siteURL()}disclosures/#rotation`);
    return { kind: 'rotation', label: 'Rotation (RRG · clock · solar · galaxy)', title: `${B.name}: where it sits in the rotation`, paras, story, post, link: `${siteURL()}disclosures/#rotation` };
  }

  // ---------------------------------------------------------------- 8-Ks and news
  function events(B) {
    const H = B.holders || {}, E = (H.events8k || []).slice().sort((a, b) => String(b.filed || '').localeCompare(String(a.filed || ''))), N = (H.news || []).slice(0, 6);
    if (!E.length && !N.length) return null;
    const T = cash(B.ticker), paras = [], lines = [];
    const top = E.find((e) => e.headline) || E[0];
    if (E.length) {
      const by = {};
      E.forEach((e) => (e.topics || [e.label || 'other']).forEach((x) => { by[x] = (by[x] || 0) + 1; }));
      paras.push(`${plural(E.length, '8-K')} in the last 120 days${Object.keys(by).length ? ': ' + Object.entries(by).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, n]) => `${k} (${n})`).join(', ') : ''}.`);
      if (top) {
        paras.push(`Latest of note — ${day(top.filed)}: ${top.label || 'Form 8-K'}${top.headline ? ` — "${String(top.headline).slice(0, 160)}"` : ''}${top.quote ? `. From the filing: "${String(top.quote).slice(0, 200)}${String(top.quote).length > 200 ? '…' : ''}"` : ''}.`);
        lines.push(`${T} filed an 8-K on ${day(top.filed)}: ${top.label || 'an event'}${top.headline ? ` — ${String(top.headline).slice(0, 90)}` : ''}.`);
      }
      const g = E.find((e) => e.guidance);
      if (g) paras.push(`Guidance mentioned in the 8-K of ${day(g.filed)}.`);
    }
    if (N.length) {
      paras.push(`In the news: ${N.slice(0, 3).map((n) => `"${String(n.title || n.headline || '').slice(0, 100)}" (${n.source || n.src || ''}${n.date || n.published ? ', ' + day(n.date || n.published) : ''})`).join('; ')}.`);
      if (!lines.length) lines.push(`${T} in the news: "${String(N[0].title || N[0].headline || '').slice(0, 120)}".`);
    }
    const story = top ? `What ${B.name} told the SEC most recently: ${top.label || 'an 8-K'} on ${day(top.filed)}.` : paras[0];
    const post = fit(lines, 'How do you read it — 1) material 2) routine 3) wait for more? 👇', B.cik ? link(B, '') : `${siteURL()}disclosures/#events`);
    return { kind: 'events', label: '8-Ks and news', title: `${B.name}: what it filed and what was said`, paras, story, post, link: B.cik ? link(B, '') : `${siteURL()}disclosures/#events` };
  }

  // ---------------------------------------------------------------- insiders (Form 4)
  function insiders(B) {
    const I = ((B.holders || {}).insiders || []).slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
    if (!I.length) return null;
    const T = cash(B.ticker), paras = [], lines = [];
    const buys = I.filter((x) => x.code === 'P'), sales = I.filter((x) => x.code === 'S'), plan = sales.filter((x) => x.plan_10b5_1), disc = sales.filter((x) => !x.plan_10b5_1);
    const sum = (L) => L.reduce((a, x) => a + (x.value || 0), 0);
    paras.push(`Form 4s on file (last 120 days; purchases and sales of $100K or more): ${plural(buys.length, 'open-market purchase')} (${big(sum(buys))}), ${plural(disc.length, 'discretionary sale')} (${big(sum(disc))}) and ${plural(plan.length, 'sale')} under 10b5-1 plans (${big(sum(plan))}).`);
    const bigB = buys.slice().sort((a, b) => (b.value || 0) - (a.value || 0))[0], bigS = disc.slice().sort((a, b) => (b.value || 0) - (a.value || 0))[0];
    if (bigB) { paras.push(`Largest purchase: ${bigB.insider} (${bigB.title || bigB.role}) bought ${big(bigB.value)}${fin(bigB.price) ? ` at ${usd(bigB.price)}` : ''} on ${day(bigB.date)}.`); lines.push(`${T}: ${bigB.title || bigB.role} ${bigB.insider} bought ${big(bigB.value)}${fin(bigB.price) ? ` at ${usd(bigB.price)}` : ''} on ${day(bigB.date)} (Form 4).`); }
    if (bigS) paras.push(`Largest discretionary sale: ${bigS.insider} (${bigS.title || bigS.role}) sold ${big(bigS.value)} on ${day(bigS.date)}.`);
    const who = new Set(buys.filter((x) => (Date.now() - Date.parse(x.date)) < 30 * 864e5).map((x) => x.insider));
    if (who.size >= 3) { paras.push(`Cluster: ${who.size} insiders bought within 30 days.`); lines.unshift(`${who.size} ${T} insiders bought in 30 days.`); }
    if (!lines.length && (bigS || plan[0])) { const x = bigS || plan[0]; lines.push(`${T}: ${x.title || x.role} ${x.insider} sold ${big(x.value)} on ${day(x.date)}${x.plan_10b5_1 ? ' under a 10b5-1 plan' : ''} (Form 4).`); }
    const story = buys.length ? `Insiders put their own money into ${B.name}: ${big(sum(buys))} in the open market, against ${big(sum(disc))} sold at their own discretion.` : `No open-market purchase by ${B.name}'s insiders; ${big(sum(sales))} sold, ${pct(sum(plan) / (sum(sales) || 1))} of it under pre-arranged plans.`;
    const post = fit(lines, buys.length ? 'Conviction or optics? 1) conviction 2) optics 3) too small 👇' : 'Routine or telling? 1) routine 2) telling 3) too early 👇', B.cik ? link(B, '') : `${siteURL()}disclosures/#insiders`);
    return { kind: 'insiders', label: 'Insiders (Form 4)', title: `${B.name}: what its insiders did`, paras, story, post, link: B.cik ? link(B, '') : `${siteURL()}disclosures/#insiders` };
  }

  // ---------------------------------------------------------------- officials (House, Senate)
  function officials(B) {
    const O = ((B.holders || {}).officials || []).filter((x) => x.date).sort((a, b) => String(b.date).localeCompare(String(a.date)));
    if (!O.length) return null;
    const T = cash(B.ticker), yr = O.filter((x) => Date.now() - Date.parse(x.date) < 365 * 864e5);
    const isBuy = (x) => /purchase|buy/i.test(x.transaction_type || ''), isSale = (x) => /sale|sell/i.test(x.transaction_type || '');
    const b = yr.filter(isBuy), s_ = yr.filter(isSale), who = (L) => [...new Set(L.map((x) => x.person))];
    const rng = (x) => (fin(x.amount_min) ? `$${num(x.amount_min)}${fin(x.amount_max) ? '–$' + num(x.amount_max) : '+'}` : 'amount not given');
    const OWN = { SP: 'spouse', JT: 'joint account', DC: 'dependent child', SELF: '' }, whose = (x) => { const o = String(x.owner || '').trim(); const w = OWN[o.toUpperCase()] != null ? OWN[o.toUpperCase()] : /self/i.test(o) ? '' : o.toLowerCase(); return w; };
    const L0 = O[0], paras = [];
    paras.push(`Officials' reports on file, last 12 months: ${plural(b.length, 'purchase')} by ${plural(who(b).length, 'official')}${who(b).length ? ` (${who(b).slice(0, 3).join(', ')})` : ''}, ${plural(s_.length, 'sale')} by ${plural(who(s_).length, 'official')}.`);
    paras.push(`Latest: ${L0.person}${whose(L0) ? ` (${whose(L0)})` : ''} — ${String(L0.transaction_type || 'a trade').toLowerCase()} of ${B.ticker}, ${rng(L0)}, on ${day(L0.date)}${L0.filed_date ? `, reported ${day(L0.filed_date)}` : ''} (${L0.jurisdiction || 'disclosure'}).`);
    const story = b.length > s_.length ? `Washington has been buying ${B.name}: ${b.length} purchases to ${s_.length} sales in a year.` : s_.length > b.length ? `Washington has been selling ${B.name}: ${s_.length} sales to ${b.length} purchases in a year.` : `Officials' trades in ${B.name} are balanced.`;
    const lines = [`${L0.jurisdiction && /senate/i.test(L0.jurisdiction) ? 'Senate' : 'House'} disclosure: ${L0.person}${whose(L0) ? `'s ${whose(L0)}` : ''} ${isBuy(L0) ? 'bought' : isSale(L0) ? 'sold' : 'traded'} ${T} (${rng(L0)}) on ${day(L0.date)}${L0.filed_date ? `, reported ${day(L0.filed_date)}` : ''}.`,
      `12 months: ${b.length} buys, ${s_.length} sales by officials.`];
    const post = fit(lines, 'How do you read officials\' trades — 1) noise 2) worth tracking 3) depends who 👇', B.cik ? link(B, '') : `${siteURL()}disclosures/#trades`);
    return { kind: 'officials', label: 'Officials\' trades', title: `${B.name}: what officials traded`, paras, story, post, link: B.cik ? link(B, '') : `${siteURL()}disclosures/#trades` };
  }

  // ---------------------------------------------------------------- market move: the stock against its normal range
  const optRow = (D, t) => ((D && D.rows) || []).find((r) => String(r.ticker).toUpperCase() === fileT(t));
  function moves(B) {
    const T = cash(B.ticker), R = optRow(B.options, B.ticker), SPYr = optRow(B.options, 'SPY'), H = B.hist, Ld = B.lad;
    const paras = [], lines = [];
    let dmove = null, z = null, when = null;
    const hh = R && (R.history || []).filter((x) => fin(x[1]));
    if (hh && hh.length >= 3) {                           // daily closes from the options history (CBOE, end of day)
      const r = hh.map((x, i) => (i ? Math.log(x[1] / hh[i - 1][1]) : null)).filter((x) => x != null);
      const last = r[r.length - 1], hist = r.slice(0, -1), sd = Math.sqrt(hist.reduce((a, x) => a + x * x, 0) / Math.max(1, hist.length));
      dmove = Math.exp(last) - 1; z = sd && hist.length >= 10 ? last / sd : null; when = hh[hh.length - 1][0];
      const w5 = hh.length > 5 ? hh[hh.length - 1][1] / hh[hh.length - 6][1] - 1 : null;
      const sh = SPYr && (SPYr.history || []).filter((x) => fin(x[1])), sm = sh && sh.length >= 2 ? sh[sh.length - 1][1] / sh[sh.length - 2][1] - 1 : null;
      paras.push(`${day(when)}: ${spct(dmove, 1)} to ${usd(hh[hh.length - 1][1])}${fin(z) ? ` — ${num(Math.abs(z), 1)}× its typical daily move over ${hh.length} sessions` : ''}${fin(sm) ? `; SPY ${spct(sm, 1)}` : ''}.${fin(w5) ? ` Five sessions: ${spct(w5, 1)}.` : ''}`);
      lines.push(`${T} ${spct(dmove, 1)} on ${day(when)} to ${usd(hh[hh.length - 1][1])}${fin(z) && Math.abs(z) >= 2 ? ` — a ${num(Math.abs(z), 1)}σ day` : ''}.`);
    }
    if (Ld && (Ld.hourly || []).length >= 2) {            // today, hour by hour (the price-ladder job)
      const Hr = Ld.hourly, lastDay = Hr[Hr.length - 1][0].slice(0, 10), prev = Hr.filter((x) => x[0].slice(0, 10) < lastDay).slice(-1)[0];
      if (prev) { const mv = Hr[Hr.length - 1][1] / prev[1] - 1; paras.push(`Latest hourly price ${usd(Hr[Hr.length - 1][1])} (${Hr[Hr.length - 1][0].replace('T', ' ')}:00 UTC), ${spct(mv, 1)} from the previous day's last reading.`); if (!lines.length) lines.push(`${T} ${spct(mv, 1)} today at ${usd(Hr[Hr.length - 1][1])}.`); }
    }
    if (H && (H.c || []).length >= 30) {                  // weekly closes and volume (the rotation history)
      const c = H.c.filter(fin), v = (H.v || []).filter(fin);
      const wr = c.map((x, i) => (i ? Math.log(x / c[i - 1]) : null)).filter((x) => x != null).slice(-53);
      const lw = wr[wr.length - 1], sdw = Math.sqrt(wr.slice(0, -1).reduce((a, x) => a + x * x, 0) / Math.max(1, wr.length - 1));
      const hi = Math.max(...c.slice(-52)), fromHi = c[c.length - 1] / hi - 1, r4 = c.length > 4 ? c[c.length - 1] / c[c.length - 5] - 1 : null;
      const vr = v.length >= 20 ? v[v.length - 1] / (v.slice(-53, -1).reduce((a, x) => a + x, 0) / Math.min(52, v.length - 1)) - 1 : null;
      paras.push(`The week: ${spct(Math.exp(lw) - 1, 1)}${sdw ? ` (${num(Math.abs(lw / sdw), 1)}× a typical week)` : ''}, four weeks ${spct(r4, 1)}, ${fromHi > -0.005 ? 'at its 52-week high' : spct(fromHi, 1) + ' from its 52-week high'}${fin(vr) ? `; volume ${spct(vr, 0)} against its year's average` : ''}.`);
      if (!lines.length) lines.push(`${T} ${spct(Math.exp(lw) - 1, 1)} this week${sdw && Math.abs(lw / sdw) >= 2 ? ` — ${num(Math.abs(lw / sdw), 1)}× a typical week` : ''}, ${fromHi > -0.005 ? 'at a 52-week high' : spct(fromHi, 1) + ' from its high'}.`);
    }
    if (!paras.length) return null;
    const story = fin(z) ? (Math.abs(z) >= 2 ? `An unusual day for ${B.name}: ${spct(dmove, 1)}, about ${num(Math.abs(z), 1)} times its normal daily swing.` : `An ordinary day for ${B.name} by its own standards (${spct(dmove, 1)}).`) : paras[0];
    const post = fit(lines, 'What\'s behind it — 1) news 2) the market 3) flows? 👇', B.cik ? link(B, '') : `${siteURL()}disclosures/#signals`);
    return { kind: 'moves', label: 'Market move', title: `${B.name}: the move against its normal range`, paras, story, post, link: B.cik ? link(B, '') : `${siteURL()}disclosures/#signals` };
  }

  // ---------------------------------------------------------------- options move: IV, put/call, gamma, disclosed 13F options
  function optmoves(B) {
    const T = cash(B.ticker), R = optRow(B.options, B.ticker), O = B.opt || R, Q = optRow(B.opt13, B.ticker);
    if (!R && !Q && !(O && fin(O.iv30))) return null;
    const paras = [], lines = [];
    if (O && fin(O.iv30)) {
      const hh = (R && R.history) || [], ivs = hh.map((x) => x[2]).filter(fin), pcs = hh.map((x) => x[3]).filter(fin);
      const avgPc = pcs.length >= 10 ? pcs.slice(0, -1).reduce((a, x) => a + x, 0) / (pcs.length - 1) : null;
      paras.push(`30-day implied volatility ${num(O.iv30, 1)}%${fin(O.iv30_chg) ? ` (${O.iv30_chg > 0 ? '+' : ''}${num(O.iv30_chg, 1)} pts on the day)` : ''}${R && fin(R.iv30_pct) ? `, higher than ${pct(R.iv30_pct)} of its readings on file` : ''}.` +
        ` Put/call open interest ${num(O.pc_oi, 2)}${fin(avgPc) ? ` against ${num(avgPc, 2)} on average` : ''}${fin(O.pc_vol) ? `, put/call volume ${num(O.pc_vol, 2)}` : ''}${fin(O.skew25) ? `; 25-delta skew ${num(O.skew25 * 100, 1)} pts` : ''}.`);
      if (fin(O.net_gex)) paras.push(`Dealer gamma ${O.net_gex >= 0 ? 'positive' : 'negative'} (${sbig(O.net_gex)} per 1% move — a model, assuming dealers are long calls and short puts)${fin(O.gamma_flip) ? `, flipping near ${usd(O.gamma_flip)}` : ''}; call wall ${usd(O.call_wall)}, put wall ${usd(O.put_wall)}, max pain ${usd(O.max_pain)}${O.max_pain_exp ? ` (${day(O.max_pain_exp)})` : ''}.`);
      const jump = fin(O.iv30_chg) && Math.abs(O.iv30_chg) >= 3;
      lines.push(`${T} options${jump ? `: 30-day IV ${O.iv30_chg > 0 ? 'jumped' : 'fell'} ${num(Math.abs(O.iv30_chg), 1)} pts to ${num(O.iv30, 1)}%` : `: IV ${num(O.iv30, 1)}%`}, put/call OI ${num(O.pc_oi, 2)}${fin(avgPc) ? ` (avg ${num(avgPc, 2)})` : ''}.`);
      lines.push(`Walls ${usd(O.put_wall)} / ${usd(O.call_wall)}, max pain ${usd(O.max_pain)}.`);
    }
    if (Q) {
      const tot = (Q.call_usd || 0) + (Q.put_usd || 0);
      paras.push(`Disclosed in 13F (${(B.opt13 && B.opt13.quarter) || 'the latest quarter'}): calls on ${big(Q.call_usd)} of stock by ${plural(Q.call_mgrs || 0, 'manager')}, puts on ${big(Q.put_usd)} by ${plural(Q.put_mgrs || 0, 'manager')}${fin(Q.pc_usd) ? ` (put/call ${num(Q.pc_usd, 2)})` : ''}; change in the quarter: calls ${sbig(Q.d_call_usd)}, puts ${sbig(Q.d_put_usd)}${Q.new_call || Q.new_put ? ` — ${Q.new_call || 0} new call and ${Q.new_put || 0} new put positions` : ''}.`);
      if ((Q.top || [])[0]) paras.push(`Largest: ${Q.top[0].manager}, ${String(Q.top[0].pc || '').toLowerCase()}s on ${big(Q.top[0].usd)}.`);
      if (tot) lines.push(`13F: calls ${big(Q.call_usd)} vs puts ${big(Q.put_usd)}; in the quarter calls ${sbig(Q.d_call_usd)}, puts ${sbig(Q.d_put_usd)}.`);
    }
    if (!paras.length) return null;
    const story = O && fin(O.iv30_chg) && Math.abs(O.iv30_chg) >= 3 ? `The options market repriced ${B.name}: implied volatility ${O.iv30_chg > 0 ? 'up' : 'down'} ${num(Math.abs(O.iv30_chg), 1)} points in a day.` : Q && fin(Q.pc_usd) ? `Funds' disclosed options lean ${Q.pc_usd > 1.2 ? 'to puts' : Q.pc_usd < 0.8 ? 'to calls' : 'neither way'} (put/call ${num(Q.pc_usd, 2)}).` : paras[0];
    const post = fit(lines, 'Hedge or bet? 1) hedge 2) bet 3) noise 👇', B.cik ? link(B, 'consensus') : `${siteURL()}disclosures/#options`);
    return { kind: 'optmoves', label: 'Options move', title: `${B.name}: what the options market did`, paras, story, post, link: B.cik ? link(B, 'consensus') : `${siteURL()}disclosures/#options` };
  }

  const BUILD = { earnings, markets, flows, capital, debt, rotation, events, insiders, officials, moves, optmoves };
  function build(kind, B) { try { return BUILD[kind] ? BUILD[kind](B) : null; } catch (e) { console.warn('post', kind, e); return null; } }
  function all(B, kinds) { return (kinds || KINDS.map((k) => k[0])).map((k) => build(k, B)).filter(Boolean); }

  // ---------------------------------------------------------------- drawing
  function css() {
    if (typeof document === 'undefined' || document.getElementById('ffp-css')) return;
    const s = document.createElement('style'); s.id = 'ffp-css';
    s.textContent = `.ffp{border:1px solid var(--line,#ddd);border-radius:12px;padding:12px 14px;margin:14px 0;background:var(--surface,transparent)}
.ffp h4{margin:0 0 6px;font-size:14px}.ffp .ffp-k{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted,#777);margin-right:6px}
.ffp p{margin:6px 0;font-size:13.5px;line-height:1.5}.ffp .ffp-story{font-style:italic}
.ffp textarea{width:100%;box-sizing:border-box;min-height:84px;font:inherit;font-size:13.5px;line-height:1.45;padding:8px 10px;border:1px solid var(--line,#ddd);border-radius:8px;background:var(--bg,#fff);color:inherit;resize:vertical}
.ffp .ffp-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px;font-size:12px;color:var(--muted,#777)}
.ffp button{font:inherit;font-size:12.5px;padding:4px 10px;border-radius:8px;border:1px solid var(--line,#ccc);background:none;color:inherit;cursor:pointer}
.ffp button.primary{background:var(--accent,#2a78d6);border-color:var(--accent,#2a78d6);color:#fff}.ffp .ffp-over{color:var(--mk-cost,#c0392b)}
.ffp details{margin-top:6px}.ffp ol{margin:6px 0 0 18px;padding:0;font-size:13px}`;
    document.head.appendChild(s);
  }
  let uid = 0;
  function box(p, opt = {}) {
    if (!p) return '';
    css();
    const id = 'ffp' + (++uid), n = xlen(p.post);
    return `<div class="ffp" data-ffp="${id}"><h4><span class="ffp-k">Post · ${esc(p.label)}</span>${esc(p.title)}</h4>
      ${opt.noAnalysis ? '' : `<p>${p.paras.map(esc).join(' ')}</p>`}${p.story ? `<p class="ffp-story">${esc(p.story)}</p>` : ''}
      <textarea id="${id}-t" aria-label="Post text" spellcheck="true">${esc(p.post)}</textarea>
      <div class="ffp-row"><button type="button" class="primary" data-ffp-copy="${id}">Copy post</button><button type="button" data-ffp-all="${id}">Copy analysis + post</button>
        <a href="https://x.com/intent/post?text=${encodeURIComponent(p.post)}" target="_blank" rel="noopener">Open in X ↗</a>
        <span data-ffp-n="${id}" class="${n > 280 ? 'ffp-over' : ''}">${n}/280</span><span data-ffp-msg="${id}" role="status"></span></div>
      ${(p.thread || []).length > 1 ? `<details><summary>The full thread (${p.thread.length} posts)</summary><ol>${p.thread.map((x) => `<li>${esc(x)}</li>`).join('')}</ol></details>` : ''}
      <script type="application/json" data-ffp-src="${id}">${JSON.stringify({ a: p.paras.join(' '), s: p.story || '' }).replace(/</g, '\\u003c')}</script></div>`;
  }
  function render(el, items, intro) {
    css();
    el.innerHTML = (intro || '') + (items.length ? items.map((p) => box(p)).join('') : '<p class="muted">No data for a post yet.</p>');
    bind(el);
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; } ta.remove(); return ok;
    }
  }
  function bind(el) {
    if (!el || !el.querySelectorAll) return;
    el.querySelectorAll('[data-ffp] textarea').forEach((ta) => {
      ta.oninput = () => { const id = ta.id.slice(0, -2), n = xlen(ta.value), e = el.querySelector(`[data-ffp-n="${id}"]`); if (e) { e.textContent = n + '/280'; e.className = n > 280 ? 'ffp-over' : ''; } };
    });
    const say = (id, x) => { const e = el.querySelector(`[data-ffp-msg="${id}"]`); if (e) e.textContent = x; };
    el.querySelectorAll('[data-ffp-copy]').forEach((b) => { b.onclick = async () => { const id = b.dataset.ffpCopy; say(id, (await copy(el.querySelector('#' + id + '-t').value)) ? 'Copied' : 'Could not copy'); }; });
    el.querySelectorAll('[data-ffp-all]').forEach((b) => { b.onclick = async () => {
      const id = b.dataset.ffpAll, src = JSON.parse((el.querySelector(`[data-ffp-src="${id}"]`) || {}).textContent || '{}');
      say(id, (await copy([src.a, src.s, el.querySelector('#' + id + '-t').value].filter(Boolean).join('\n\n'))) ? 'Copied' : 'Could not copy');
    }; });
  }
  // an X Article's blocks for one post (app.js articleHTML / articleText draw them)
  function blocks(p, opt = {}) {
    if (!p) return [];
    const out = [];
    if (opt.heading !== false) out.push({ k: 'h2', text: opt.heading || p.title });
    if (p.story) out.push({ k: 'p', text: p.story, bold: p.story.split(':')[0].length < 80 && p.story.includes(':') ? p.story.split(':')[0] : '' });
    p.paras.forEach((x) => out.push({ k: 'p', text: x }));
    if (p.link) out.push({ k: 'ul', links: [[p.link, `${p.label} on Filing Flows`]] });
    return out;
  }

  // placeholders a view leaves for a post: <div data-post-t="NVDA" data-post-k="flows,rotation" data-post-cik="1045810">
  const filled = new Map();
  function fill(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll('[data-post-t]').forEach((el) => {
      const t = el.dataset.postT, kinds = String(el.dataset.postK || 'flows').split(','), cik = el.dataset.postCik || null, key = t + '|' + kinds.join(',') + '|' + (cik || '');
      if (el.dataset.postDone === key) return;
      el.dataset.postDone = key;
      const draw = (html) => { if (el.isConnected) { el.innerHTML = html; bind(el); } };
      if (filled.has(key)) { draw(filled.get(key)); return; }
      el.innerHTML = '<p class="muted">Writing the post…</p>';
      load(t, cik, kinds).then((B) => { const html = all(B, kinds).map((p) => box(p)).join('') || ''; filled.set(key, html); draw(html); }).catch(() => draw(''));
    });
  }

  window.FFPosts = { KINDS, load, build, all, box, render, bind, blocks, fill, rrgOf, fit, xlen, siteURL };
})();
