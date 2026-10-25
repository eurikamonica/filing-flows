/* Flo — the site's mascot and question box. A little flow-droplet with a Sankey ribbon for a tail that sits in the
   corner of every page, waves, thinks, talks and reacts to what it finds. Ask it about any company on the site, in
   English or Chinese ("What is NVDA worth?", "META 下周会进入领先象限吗?", "AAPL 期权的最大痛点"), and it answers from the
   site's own models — written by fixed rules from the published numbers, no language model:
     valuation   the Fair value page (disclosures/data/research/valuation/c/<cik>.json): the stage-weighted value and its
                 range, the DCF, the Monte Carlo odds, what the price pays for growth, analysts, distress
     rotation    the weekly RRG against the S&P 500 (disclosures/data/market/history/, rrg-company-view.js): the quadrant,
                 the close that moves it into Leading or Lagging next week, the Markov odds 4 weeks on, the replayed range
     industry    its industry's own RRG (industries.json): quadrant and the index move into Leading
     options     the option chain's implied paths (disclosures/data/market/options/<T>.json): 80% ranges, max pain, walls
     earnings    the latest quarter from the filings (data/c/<cik>.json): revenue, operating and net income, year on year
     credit      the distress blend, Altman Z, distance to default, the bond-calibrated spread
     analysts    the analysts' targets and the Polymarket implied price
   With the owner's local model connected (local-model.js), "Explain with the local model" sends the question and these
   facts — and only these — to it. Every answer links to the page it came from. Not investment advice.
   window.FFMascot: open(), ask(question) → Promise<answer>; exported for tests: classify, findCompany, lang. */
(function (root) {
  'use strict';
  const doc = typeof document !== 'undefined' ? document : null;
  const SRC = (doc && doc.currentScript && doc.currentScript.src) || '';
  const BASE = SRC ? SRC.replace(/[^/]*$/, '') : '';                 // the site root (mascot.js sits there)
  const DATA = BASE + 'data/', HUB = BASE + 'disclosures/data/', HUBJS = BASE + 'disclosures/';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, 1) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const pc = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spc = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const memo = new Map();
  const json = (u) => { if (!memo.has(u)) memo.set(u, fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null)); return memo.get(u); };
  const fileT = (t) => String(t || '').toUpperCase().replace(/\./g, '-');
  const QN = { en: ['Leading', 'Weakening', 'Lagging', 'Improving'], zh: ['领先', '转弱', '落后', '改善'] };
  const L = (lg, en, zh) => (lg === 'zh' ? zh : en);

  /* ---------- the question ---------- */
  const lang = (q) => (/[㐀-鿿]/.test(String(q || '')) ? 'zh' : 'en');
  const INTENTS = [
    ['options', /\boptions?\b|max ?pain|put wall|call wall|implied (move|vol|range)|\biv\b|期权|最大痛点|看涨墙|看跌墙|隐含波动|隐含区间/i],
    ['industry', /\bindustr(y|ies)\b|\bsector\b|\bpeers?\b|行业|板块|同业/i],
    ['rotation', /\brrg\b|rotation|rotating|momentum|quadrant|leading|lagging|weakening|improving|relative strength|next week|轮动|象限|动量|领先|落后|转弱|改善|相对强弱|下周/i],
    ['credit', /\bdebt\b|credit|default|bankrupt|distress|altman|solven|债务|违约|信用|破产|偿债/i],
    ['analysts', /analyst|price target|target price|consensus|polymarket|分析师|目标价|一致预期|预测市场/i],
    ['earnings', /revenue|earnings|profit|margin|\beps\b|quarter|sales|income|cash flow|收入|营收|利润|财报|毛利|季度|净利|现金流|业绩/i],
    ['valuation', /worth|\bvalue\b|valuation|fair|cheap|expensive|overvalued|undervalued|\bdcf\b|intrinsic|\bbuy\b|估值|值多少|便宜|贵|低估|高估|合理价|内在价值|值得买|价值/i],
    ['help', /^\s*(hi|hello|hey|help|what can you do)\b|你好|帮助|你能做什么|怎么用/i],
  ];
  function classify(q) {
    const out = [];
    for (const [k, rx] of INTENTS) if (rx.test(String(q || ''))) out.push(k);
    if (out.includes('industry') && out.includes('rotation')) out.splice(out.indexOf('rotation'), 1);   // "how is its industry rotating"
    return out;
  }
  const ZH_NAMES = { '苹果': 'AAPL', '英伟达': 'NVDA', '微软': 'MSFT', '谷歌': 'GOOGL', '亚马逊': 'AMZN', '特斯拉': 'TSLA', '脸书': 'META', '伯克希尔': 'BRK-B',
    '台积电': 'TSM', '奈飞': 'NFLX', '网飞': 'NFLX', '英特尔': 'INTC', '超威': 'AMD', '博通': 'AVGO', '甲骨文': 'ORCL', '摩根大通': 'JPM', '高盛': 'GS', '沃尔玛': 'WMT',
    '可口可乐': 'KO', '礼来': 'LLY', '诺和诺德': 'NVO', '强生': 'JNJ', '埃克森': 'XOM', '雪佛龙': 'CVX', '波音': 'BA', '迪士尼': 'DIS', '耐克': 'NKE', '星巴克': 'SBUX',
    '麦当劳': 'MCD', '花旗': 'C', '美国银行': 'BAC', '富国银行': 'WFC', '辉瑞': 'PFE', '高通': 'QCOM', '美光': 'MU', '阿斯麦': 'ASML', '帕兰提尔': 'PLTR', '赛富时': 'CRM',
    '奥多比': 'ADBE', '优步': 'UBER', '爱彼迎': 'ABNB', '好市多': 'COST', '家得宝': 'HD', '联合健康': 'UNH', '维萨': 'V', '万事达': 'MA', '贝宝': 'PYPL' };
  const STOP = new Set(['I', 'A', 'AN', 'THE', 'IS', 'IT', 'ON', 'OR', 'AND', 'TO', 'IN', 'OF', 'FOR', 'BE', 'DO', 'ME', 'MY', 'SO', 'UP', 'US', 'AT', 'BY', 'AS', 'IF',
    'NO', 'GO', 'ALL', 'ARE', 'CAN', 'HOW', 'WHAT', 'WHY', 'NOW', 'NEW', 'ONE', 'OUT', 'ANY', 'RRG', 'EPS', 'DCF', 'IV', 'PE', 'EV', 'CEO', 'CFO', 'ETF', 'Q', 'YOY',
    'SPY', 'VS', 'OK', 'WILL', 'NEXT', 'WEEK', 'MAX', 'PAIN', 'BUY', 'SELL', 'HI', 'HEY', 'GET', 'HAS', 'HAD', 'ITS', 'WAS']);
  function findCompany(q, ix) {
    const list = (ix && ix.companies) || [];
    if (!list.length) return null;
    const byT = new Map(list.map((c) => [String(c.ticker || '').toUpperCase(), c]));
    const s = String(q || '');
    const cash = s.match(/\$([A-Za-z][A-Za-z.\-]{0,6})/);
    if (cash && byT.has(cash[1].toUpperCase())) return byT.get(cash[1].toUpperCase());
    for (const [zh, t] of Object.entries(ZH_NAMES)) if (s.includes(zh) && byT.has(t)) return byT.get(t);
    for (const w of s.match(/\b[A-Z][A-Z0-9.\-]{0,5}\b/g) || []) if (!STOP.has(w) && byT.has(w)) return byT.get(w);
    // a company's name: its first word (four letters or more) in the question, largest revenue first
    const lw = new Set(s.toLowerCase().match(/[a-z]{4,}/g) || []);
    const generic = ['corp', 'group', 'holdings', 'company', 'global', 'international', 'american', 'first', 'united', 'general', 'national'];
    const hits = list.filter((c) => { const f = String(c.name || '').toLowerCase().match(/[a-z]{4,}/); return f && lw.has(f[0]) && !generic.includes(f[0]); });
    hits.sort((a, b) => (b.revenue || 0) - (a.revenue || 0));
    if (hits[0]) return hits[0];
    for (const w of s.match(/\b[a-z][a-z.\-]{1,5}\b/g) || []) { const u = w.toUpperCase(); if (!STOP.has(u) && byT.has(u)) return byT.get(u); }   // "nvda"
    return null;
  }
  const pageCik = () => { const m = /^#c-(\d+)/.exec((root.location && root.location.hash) || ''); return m ? +m[1] : null; };

  /* ---------- the page it is on: default questions and the greeting follow it ---------- */
  // company page tab → the topic it is about (#c-<cik>-x-options, #c-<cik>-debt …); the plain company page is its earnings
  const TAB_TOPIC = { 'x-fairvalue': 'valuation', value: 'valuation', 'x-rotation': 'rotation', 'x-options': 'options', debt: 'credit', consensus: 'analysts', revisions: 'analysts' };
  // disclosures-hub tab → topic
  const HUB_TOPIC = { valuation: 'valuation', rotation: 'rotation', options: 'options', debt: 'credit', consensus: 'analysts', earnings: 'earnings', quality: 'earnings', filings: 'earnings' };
  const TOPICS = ['valuation', 'rotation', 'options', 'earnings', 'industry', 'credit', 'analysts'];
  const byRevenue = (list, f) => list.filter(f).sort((a, b) => (b.revenue || 0) - (a.revenue || 0)).slice(0, 3);
  // → {kind: company|industry|group|hub|home, co?, cos?, topic?, label?, ind?, key}; `loc` is window.location (or a stand-in in tests)
  function pageContext(ix, loc, inds) {
    loc = loc || root.location || {};
    const list = (ix && ix.companies) || [], h = decodeURIComponent(String(loc.hash || '').replace(/^#\/?/, ''));
    const hub = /\/disclosures\//.test(String(loc.pathname || ''));
    let m;
    if (!hub) {
      if ((m = /^c-(\d+)(?:-([a-z0-9-]+))?$/.exec(h))) {
        const co = list.find((c) => +c.cik === +m[1]);
        if (co) { const tab = /^\d{4}-|^fy-|^cmp-|^all$/.test(m[2] || '') ? '' : (m[2] || ''); return { kind: 'company', co, topic: TAB_TOPIC[tab] || 'earnings', key: 'c' + co.cik + tab }; }
      }
      if ((m = /^s-([a-z0-9-]+?)(?:-CY\d{4}Q\d)?$/.exec(h))) return { kind: 'group', label: (ix && ix.sector_names || {})[m[1]] || m[1], cos: byRevenue(list, (c) => c.sector === m[1]), key: 's' + m[1] };
      if ((m = /^i-([a-z0-9-]+?)(?:-CY\d{4}Q\d)?$/.exec(h))) {
        const row = ((ix && ix.industries) || []).find((x) => x.id === m[1]);
        return { kind: 'group', label: row ? row.name : 'SIC ' + m[1], cos: byRevenue(list, (c) => String(c.sic) === m[1]), key: 'i' + m[1] };
      }
      return { kind: 'home', cos: byRevenue(list, () => true), key: 'home' };
    }
    const [tab, arg] = h.split('/');
    if (tab === 'rotation' && arg && /^ind~/.test(arg) && inds) {        // #rotation/ind~sic4:3674 — one industry's RRG
      const id = arg.slice(4), row = (inds.rows || []).find((r) => r.id === id);
      if (row) {
        const t = new Set((row.tickers || []).map((x) => String(x).toUpperCase()));
        const cos = list.filter((c) => t.has(String(c.ticker).toUpperCase())).sort((a, b) => (b.revenue || 0) - (a.revenue || 0)).slice(0, 3);
        return { kind: 'industry', label: row.label, ind: row, cos, co: cos[0] || null, key: 'ind' + id };
      }
    }
    return { kind: 'hub', topic: HUB_TOPIC[tab] || null, tab: tab || '', cos: byRevenue(list, () => true), key: 'hub' + (tab || '') };
  }
  const Q = {
    valuation: [(t) => `What is ${t} worth?`, (t) => `${t} 值多少钱？`, (t) => `${t} DCF and Monte Carlo`, (t) => `${t} 的 DCF 和蒙特卡洛估值`],
    rotation: [(t) => `Will ${t} be Leading next week?`, (t) => `${t} 下周会进入领先象限吗？`, (t) => `Where will ${t}'s quadrant be in 4 weeks?`, (t) => `${t} 4 周后在哪个象限？`],
    options: [(t) => `${t} options: range and max pain`, (t) => `${t} 期权的隐含区间和最大痛点`, (t) => `${t} put wall and call wall`, (t) => `${t} 期权的 put wall 和 call wall`],
    earnings: [(t) => `${t} latest earnings`, (t) => `${t} 最新财报`, (t) => `${t} revenue growth and margin`, (t) => `${t} 营收增长和利润率`],
    industry: [(t) => `How is ${t}'s industry rotating?`, (t) => `${t} 所在行业轮动`, (t) => `Is ${t}'s industry Leading?`, (t) => `${t} 所在行业处于哪个象限？`],
    credit: [(t) => `${t} debt and default risk`, (t) => `${t} 的债务和违约风险`, (t) => `${t} Altman Z and credit spread`, (t) => `${t} 的信用利差和 Altman Z`],
    analysts: [(t) => `${t} analyst price target`, (t) => `${t} 分析师目标价`, (t) => `${t} Polymarket implied price`, (t) => `${t} 预测市场隐含价格`],
  };
  const q1 = (topic, t, zh, second) => Q[topic][(second ? 2 : 0) + (zh ? 1 : 0)](t);
  // the default questions for a page: up to six, the page's own topic first
  function chipsFor(ctx, zh) {
    ctx = ctx || { kind: 'home' };
    const cos = ctx.cos || [], t0 = (ctx.co && ctx.co.ticker) || (cos[0] && cos[0].ticker) || 'NVDA';
    const T = (i) => (cos[i] && cos[i].ticker) || t0;
    if (ctx.kind === 'company') {
      const first = ctx.topic || 'earnings';
      return [q1(first, t0, zh), q1(first, t0, zh, true), ...TOPICS.filter((k) => k !== first && k !== 'credit' && k !== 'analysts').map((k) => q1(k, t0, zh))].slice(0, 6);
    }
    if (ctx.kind === 'industry') return [q1('industry', T(0), zh), q1('industry', T(0), zh, true), q1('rotation', T(0), zh), q1('rotation', T(1), zh), q1('valuation', T(0), zh), q1('earnings', T(2), zh)];
    if (ctx.kind === 'group') return [q1('valuation', T(0), zh), q1('earnings', T(1), zh), q1('rotation', T(2), zh), q1('industry', T(0), zh), q1('options', T(0), zh)];
    if (ctx.kind === 'hub' && ctx.topic) {
      const k = ctx.topic;
      return [q1(k, T(0), zh), q1(k, T(1), zh), q1(k, T(2), zh), q1(k, T(0), zh, true), ...(k === 'rotation' ? [q1('industry', T(0), zh)] : [q1('valuation', T(0), zh)])];
    }
    return [q1('valuation', T(0), zh), q1('rotation', T(1), zh), q1('options', T(2), zh), q1('earnings', T(0), zh), q1('industry', T(1), zh)];
  }
  const TOPIC_NAME = { en: { valuation: 'fair value', rotation: 'rotation (RRG)', options: 'options', earnings: 'earnings', credit: 'debt and credit', analysts: 'analysts' },
    zh: { valuation: '估值', rotation: 'RRG 轮动', options: '期权', earnings: '财报', credit: '债务与信用', analysts: '分析师' } };
  // one line that says Flo knows where you are; null on the home page (the full help is shown there)
  function greetFor(ctx, zh) {
    const lg = zh ? 'zh' : 'en', N = TOPIC_NAME[lg];
    if (!ctx || ctx.kind === 'home') return null;
    if (ctx.kind === 'company') { const c = ctx.co; return L(lg, `You're on <b>${esc(c.ticker)}</b>'s ${N[ctx.topic] || 'earnings'} page. Ask anything about it — “next week?”, “worth?” — I'll assume ${esc(c.ticker)}.`, `你在看 <b>${esc(c.ticker)}</b> 的${N[ctx.topic] || '财报'}页。直接问就行，比如「下周呢？」「值多少？」，我默认说的是 ${esc(c.ticker)}。`); }
    if (ctx.kind === 'industry') return L(lg, `This is the <b>${esc(ctx.label)}</b> industry's RRG. Ask about it or its companies${ctx.co ? ` (I'll assume ${esc(ctx.co.ticker)}, its largest)` : ''}.`, `这是 <b>${esc(ctx.label)}</b> 行业的 RRG。可以问这个行业或其中的公司${ctx.co ? `（默认用行业里最大的 ${esc(ctx.co.ticker)}）` : ''}。`);
    if (ctx.kind === 'group') return L(lg, `You're looking at <b>${esc(ctx.label)}</b>. Here are questions about its largest companies.`, `你在看 <b>${esc(ctx.label)}</b>。下面是关于其中最大几家公司的问题。`);
    if (ctx.kind === 'hub' && ctx.topic) return L(lg, `This page is about ${N[ctx.topic]}. Name a company and I'll answer from the same model.`, `这一页是${N[ctx.topic]}。告诉我公司名或代码，我用同一个模型回答。`);
    return null;
  }

  /* ---------- the answers: each returns {html, mood, facts[], links[]} ---------- */
  const link = (href, text) => `<a href="${esc(href)}"${/^https?:/.test(href) ? ' target="_blank" rel="noopener"' : ''}>${esc(text)}</a>`;
  async function valuation(c, lg) {
    const d = await json(HUB + 'research/valuation/c/' + c.cik + '.json');
    if (!d) return null;
    const st = d.stage || {}, fb = d.football || [], price = d.price;
    const get = (rx) => fb.find((b) => rx.test(b.method));
    const sw = get(/^Stage-weighted/), an = get(/^Analysts/), dc = d.dcf, mc = d.mc, pv = d.pvgo, dist = ((d.credit || {}).distress || {}).pd;
    const gap = sw && fin(price) && price > 0 ? sw.point / price - 1 : null;
    const facts = [`price ${usd(price)} (${d.price_date || ''})`, sw ? `stage-weighted value (${st.label}) ${usd(sw.point)}, range ${usd(sw.low)}–${usd(sw.high)}` : '',
      dc ? `DCF base case ${usd(dc.value)}` : '', mc ? `Monte Carlo: value above the price in ${pc(mc.p_above)} of ${num(mc.n)} scenarios` : '',
      pv ? `the price pays ${pc(pv.growth_share)} for growth (PVGO)` : '', an ? `analysts' mean target ${usd(an.point)}` : '', fin(dist) ? `one-year distress probability ${pc(dist, 1)}` : ''].filter(Boolean);
    const p = [L(lg, `<b>${esc(c.ticker)}</b> trades at <b>${usd(price)}</b>.`, `<b>${esc(c.ticker)}</b> 现价 <b>${usd(price)}</b>。`)];
    if (sw && fin(gap)) p.push(L(lg, `As a <b>${esc((st.label || '').toLowerCase())}</b> company its methods weigh to <b>${usd(sw.point)}</b> (range ${usd(sw.low)}–${usd(sw.high)}), ${spc(Math.abs(gap), 0).replace('+', '')} ${gap >= 0 ? 'above' : 'below'} the price.`,
      `按「${esc(st.label || '')}」阶段加权，各方法给出 <b>${usd(sw.point)}</b>（区间 ${usd(sw.low)}–${usd(sw.high)}），比现价${gap >= 0 ? '高' : '低'} ${spc(Math.abs(gap), 0).replace('+', '')}。`));
    if (dc) p.push(L(lg, `DCF base case ${usd(dc.value)}${mc ? `; in ${pc(mc.p_above)} of ${num(mc.n)} Monte Carlo scenarios the value is above the price` : ''}.`,
      `DCF 基准情形 ${usd(dc.value)}${mc ? `；${num(mc.n)} 次蒙特卡洛中 ${pc(mc.p_above)} 的情形价值高于现价` : ''}。`));
    if (pv && fin(pv.growth_share)) p.push(L(lg, `The price pays ${pc(Math.max(0, pv.growth_share))} for growth not yet earned.`, `股价中约 ${pc(Math.max(0, pv.growth_share))} 是在为尚未实现的增长付费。`));
    if (an) p.push(L(lg, `Analysts' mean target: ${usd(an.point)}.`, `分析师平均目标价：${usd(an.point)}。`));
    if (fin(dist)) p.push(L(lg, `One-year distress probability (model blend): ${pc(dist, 1)}.`, `一年期困境概率（模型混合）：${pc(dist, 1)}。`));
    return { html: p.join(' '), facts, mood: !fin(gap) ? 'talk' : gap > 0.15 ? 'happy' : gap < -0.15 ? 'worried' : 'talk',
      links: [[`${BASE}#c-${c.cik}-x-fairvalue`, L(lg, 'Fair value — every method and the appendix', 'Fair value 页：所有方法与附录')]] };
  }
  let rrgP = null;
  function rrgTools() {
    if (root.RRGCompanyView && root.RRGCompanyView._t) return Promise.resolve(root.RRGCompanyView._t);
    return rrgP || (rrgP = new Promise((ok) => { const sc = doc.createElement('script'); sc.src = HUBJS + 'rrg-company-view.js'; sc.onload = () => ok(root.RRGCompanyView && root.RRGCompanyView._t); sc.onerror = () => ok(null); doc.head.appendChild(sc); }));
  }
  async function rotation(c, lg) {
    const T = fileT(c.ticker), base = HUB + 'market/history/';
    const [D, t, M, R] = await Promise.all([json(base + 'rrg.json'), json(base + 't/' + T + '.json'), json(base + 'rrg-transition-model.json'), rrgTools()]);
    if (!D || !t || !t.c || !R) return null;
    const G = R.grid(D), SPY = R.place(G, D.bench.start, D.bench.c), C = R.place(G, t.start, t.c), V = t.v ? R.place(G, t.start, t.v, 1000) : null;
    const A = R.analyse(G, C, V, SPY, {});
    if (!A) return null;
    const d = M ? R.odds(M, 'company_vs_market', A.st, '4') : null, ok = fin(A.th.mx) && fin(A.th.my);
    const hi = ok ? A.close * Math.max(A.th.mx, A.th.my) : null, lo = ok ? A.close * Math.min(A.th.mx, A.th.my) : null;
    const cum = A.paths.map((p) => p.cum[3]), r10 = Math.exp(R.qtl(cum, 0.1)), r90 = Math.exp(R.qtl(cum, 0.9));
    const shown = d && ['calibrated', 'experimental'].includes(d.label) && A.liquid, pv = d ? (shown ? d.p : d.hist) : null;
    const q = A.st.q, Q = QN[lg];
    const odds = pv ? Q.map((n, j) => `${n} ${pc(pv[j])}`).join(lg === 'zh' ? '，' : ', ') : '';
    const facts = [`RRG vs SPY, week of ${A.day}: ${QN.en[q]} (RS-Ratio ${num(A.S.x[A.k], 2)}, RS-Momentum ${num(A.S.y[A.k], 2)})`,
      ok ? `next week, SPY flat: a close at or above ${usd(hi)} puts it into Leading, below ${usd(lo)} into Lagging` : '',
      pv ? `4-week Markov odds (${shown ? d.label : 'history only'}): ${QN.en.map((n, j) => `${n} ${pc(pv[j])}`).join(', ')}` : '',
      A.paths.length >= 30 ? `replayed 4-week range ${usd(A.close * r10)}–${usd(A.close * r90)}` : ''].filter(Boolean);
    const p = [L(lg, `<b>${esc(c.ticker)}</b> is <b>${Q[q]}</b> against the S&P 500 (week of ${esc(A.day)}; RS-Ratio ${num(A.S.x[A.k], 1)}, RS-Momentum ${num(A.S.y[A.k], 1)}).`,
      `<b>${esc(c.ticker)}</b> 相对标普 500 处于<b>${Q[q]}</b>象限（${esc(A.day)} 当周；RS-Ratio ${num(A.S.x[A.k], 1)}，RS-Momentum ${num(A.S.y[A.k], 1)}）。`)];
    if (ok) p.push(L(lg, `With SPY flat, a close at or above <b>${usd(hi)}</b> (${spc(hi / A.close - 1)}) next week puts it into Leading; below <b>${usd(lo)}</b> (${spc(lo / A.close - 1)}) into Lagging.`,
      `假设 SPY 不动，下周收盘 ≥ <b>${usd(hi)}</b>（${spc(hi / A.close - 1)}）进入领先，低于 <b>${usd(lo)}</b>（${spc(lo / A.close - 1)}）落入落后。`));
    if (pv) p.push(L(lg, `Where lines in its spot stood 4 weeks later (${shown ? d.label : 'history only'}): ${odds}.`, `同位置的股票 4 周后的去向（${shown ? (d.label === 'calibrated' ? '已校准' : '实验性') : '仅历史'}）：${odds}。`));
    if (A.paths.length >= 30) p.push(L(lg, `Its own past runs replayed: ${usd(A.close * r10)}–${usd(A.close * r90)} in 4 weeks (80%).`, `用它自己的历史走势回放：4 周后 80% 区间 ${usd(A.close * r10)}–${usd(A.close * r90)}。`));
    return { html: p.join(' '), facts, mood: q === 0 ? 'happy' : q === 2 ? 'worried' : 'talk', links: [[`${BASE}#c-${c.cik}-x-rotation`, L(lg, 'Rotation (RRG) page', 'RRG 轮动页')]] };
  }
  async function industry(c, lg) {
    const base = HUB + 'market/history/';
    const [D, t, I, M, R] = await Promise.all([json(base + 'rrg.json'), json(base + 't/' + fileT(c.ticker) + '.json'), json(base + 'industries.json'), json(base + 'rrg-transition-model.json'), rrgTools()]);
    if (!D || !t || !t.bid || !I || !R) return null;
    const row = (I.rows || []).find((r) => r.id === t.bid);
    if (!row) return null;
    const G = R.grid(D), SPY = R.place(G, D.bench.start, D.bench.c), A = R.analyse(G, R.place(G, row.start, row.c), null, SPY, { always: true });
    if (!A) return null;
    const d = M ? R.odds(M, 'industry_vs_market', A.st, '4') : null, ok = fin(A.th.mx) && fin(A.th.my), Q = QN[lg];
    const lead = ok ? Math.max(A.th.mx, A.th.my) - 1 : null;
    const pv = d ? (['calibrated', 'experimental'].includes(d.label) ? d.p : d.hist) : null;
    const facts = [`industry ${row.label}: ${QN.en[A.st.q]} vs SPY`, ok ? `index move into Leading next week ${spc(lead)}` : '', pv ? `4-week odds ${QN.en.map((n, j) => `${n} ${pc(pv[j])}`).join(', ')}` : ''].filter(Boolean);
    const html = L(lg, `${esc(c.ticker)}'s industry, <b>${esc(row.label)}</b> (${num(row.members)} companies), is <b>${Q[A.st.q]}</b> against the S&P 500.${ok ? ` Its index needs ${spc(lead)} next week (SPY flat) to be Leading.` : ''}${pv ? ` 4 weeks on, lines like it stood: ${Q.map((n, j) => `${n} ${pc(pv[j])}`).join(', ')}.` : ''}`,
      `${esc(c.ticker)} 所在行业 <b>${esc(row.label)}</b>（${num(row.members)} 家公司）相对标普 500 处于<b>${Q[A.st.q]}</b>象限。${ok ? `行业指数下周需要 ${spc(lead)}（SPY 不动）才能进入领先。` : ''}${pv ? `同类行业 4 周后：${Q.map((n, j) => `${n} ${pc(pv[j])}`).join('，')}。` : ''}`);
    return { html, facts, mood: A.st.q === 0 ? 'happy' : A.st.q === 2 ? 'worried' : 'talk', links: [[`${BASE}disclosures/#rotation/ind~${encodeURIComponent(row.id)}`, L(lg, 'This industry in the Industry RRG', '行业 RRG 中查看')]] };
  }
  async function options(c, lg) {
    const o = await json(HUB + 'market/options/' + encodeURIComponent(fileT(c.ticker)) + '.json');
    if (!o) return { html: L(lg, `${esc(c.ticker)}'s option chain is not collected (the daily collector covers the indexes, sector ETFs and the most-held stocks).`, `${esc(c.ticker)} 的期权链暂未采集（每日只采集指数、行业 ETF 和 13F 持仓最多的股票）。`), facts: [], mood: 'talk', links: [] };
    const P = (o.paths || []).filter((x) => (x.q || []).length), pr = o.path_probs || [], k = (x, p) => x.q[pr.indexOf(p)];
    const x = P.reduce((b, y) => (!b || Math.abs(y.days - 30) < Math.abs(b.days - 30) ? y : b), null);
    const facts = [`spot ${usd(o.spot)}`, x ? `${x.exp} (${x.days} days): 80% ${usd(k(x, 0.1))}–${usd(k(x, 0.9))}, 95% ${usd(k(x, 0.025))}–${usd(k(x, 0.975))}, max pain ${usd(x.max_pain)}, put wall ${usd(x.put_wall)}, call wall ${usd(x.call_wall)}` : '',
      `nearest monthly max pain ${usd(o.max_pain)} (${o.max_pain_exp || ''})`].filter(Boolean);
    const html = x ? L(lg, `${esc(c.ticker)} at ${usd(o.spot)}. For <b>${esc(x.exp)}</b> (${x.days} days) its options imply an 80% range of <b>${usd(k(x, 0.1))}–${usd(k(x, 0.9))}</b> (95%: ${usd(k(x, 0.025))}–${usd(k(x, 0.975))}); max pain ${usd(x.max_pain)}, put wall ${usd(x.put_wall)}, call wall ${usd(x.call_wall)}. Risk-neutral, not a forecast.`,
      `${esc(c.ticker)} 现价 ${usd(o.spot)}。<b>${esc(x.exp)}</b>（${x.days} 天）期权隐含的 80% 区间 <b>${usd(k(x, 0.1))}–${usd(k(x, 0.9))}</b>（95%：${usd(k(x, 0.025))}–${usd(k(x, 0.975))}）；最大痛点 ${usd(x.max_pain)}，put wall ${usd(x.put_wall)}，call wall ${usd(x.call_wall)}。风险中性分布，不是预测。`)
      : L(lg, `Max pain for ${esc(o.max_pain_exp || 'the nearest monthly')}: ${usd(o.max_pain)}.`, `最近月度到期（${esc(o.max_pain_exp || '')}）最大痛点：${usd(o.max_pain)}。`);
    return { html, facts, mood: 'talk', links: [[`${BASE}#c-${c.cik}-x-options`, L(lg, 'Options: price paths', '期权价格路径页')]] };
  }
  async function earnings(c, lg) {
    const d = await json(DATA + 'c/' + c.cik + '.json');
    const qs = (d && d.quarters) || [];
    if (!qs.length) return null;
    const q = qs[qs.length - 1], h = q.headline || {}, ya = qs.length >= 5 ? (qs[qs.length - 5].headline || {}) : {};
    const yoy = (a, b) => (fin(a) && fin(b) && b > 0 ? a / b - 1 : null), g = yoy(h.revenue, ya.revenue);
    const om = fin(h.oi) && fin(h.revenue) && h.revenue > 0 ? h.oi / h.revenue : null;
    const facts = [`${q.label} (${q.form}, filed ${q.filed}): revenue ${big(h.revenue)}${fin(g) ? ` (${spc(g)} y/y)` : ''}, operating income ${big(h.oi)}, net income ${big(h.ni)}${fin(h.ocf) ? `, operating cash flow ${big(h.ocf)}` : ''}`];
    const html = L(lg, `${esc(c.ticker)}'s latest quarter, <b>${esc(q.label)}</b> (${esc(q.form)}, filed ${esc(q.filed)}): revenue <b>${big(h.revenue)}</b>${fin(g) ? ` (${spc(g)} year on year)` : ''}, operating income ${big(h.oi)}${fin(om) ? ` (${pc(om, 1)} margin)` : ''}, net income ${big(h.ni)}${fin(h.ocf) ? `, operating cash flow ${big(h.ocf)}` : ''}.`,
      `${esc(c.ticker)} 最新一季 <b>${esc(q.label)}</b>（${esc(q.form)}，${esc(q.filed)} 提交）：营收 <b>${big(h.revenue)}</b>${fin(g) ? `（同比 ${spc(g)}）` : ''}，营业利润 ${big(h.oi)}${fin(om) ? `（利润率 ${pc(om, 1)}）` : ''}，净利润 ${big(h.ni)}${fin(h.ocf) ? `，经营现金流 ${big(h.ocf)}` : ''}。`);
    return { html, facts, mood: fin(g) && g > 0.1 ? 'happy' : fin(g) && g < -0.05 ? 'worried' : 'talk',
      links: [[`${BASE}#c-${c.cik}`, L(lg, 'Earnings Sankey', '财报桑基图')], ...(q.doc_url ? [[q.doc_url, L(lg, 'The filing on SEC.gov', 'SEC 原始文件')]] : [])] };
  }
  async function credit(c, lg) {
    const d = await json(HUB + 'research/valuation/c/' + c.cik + '.json');
    const cr = d && d.credit;
    if (!cr) return null;
    const pd = (cr.distress || {}).pd;
    const facts = [fin(pd) ? `one-year distress ${pc(pd, 2)}` : '', fin(cr.altman_z) ? `Altman Z ${num(cr.altman_z, 2)}` : '', fin(cr.distance_to_default) ? `distance to default ${num(cr.distance_to_default, 1)}` : '',
      fin(cr.cds_5y_bps) ? `5-year spread ${num(cr.cds_5y_bps)} bp${cr.rating_band ? ' (' + cr.rating_band + ')' : ''}` : ''].filter(Boolean);
    const html = L(lg, `${esc(c.ticker)}'s credit: ${esc(facts.join(', ') || 'no credit figures on file')}. The distress figure blends Merton, the bond-calibrated spread, Altman Z and the debt cushion; read it as a ranking, not a calibrated probability.`,
      `${esc(c.ticker)} 的信用：${esc(facts.join('，') || '暂无信用数据')}。困境概率混合了 Merton、债券校准利差、Altman Z 和债务缓冲，只适合做排序，不是校准过的概率。`);
    return { html, facts, mood: fin(pd) && pd > 0.05 ? 'worried' : fin(pd) && pd < 0.005 ? 'happy' : 'talk', links: [[`${BASE}#c-${c.cik}-debt`, L(lg, 'Debt & rates', '债务与利率页')]] };
  }
  async function analysts(c, lg) {
    const d = await json(HUB + 'research/valuation/c/' + c.cik + '.json');
    const fb = (d && d.football) || [], an = fb.find((b) => /^Analysts/.test(b.method)), pm = fb.find((b) => /^Polymarket/.test(b.method));
    if (!an && !pm) return null;
    const facts = [an ? `analysts' targets ${usd(an.low)}–${usd(an.high)}, mean ${usd(an.point)}` : '', pm ? `Polymarket implied price ${usd(pm.point)}` : ''].filter(Boolean);
    const html = L(lg, `${esc(c.ticker)} at ${usd(d.price)}: ${esc(facts.join('; '))}.`,
      `${esc(c.ticker)} 现价 ${usd(d.price)}：${an ? `分析师目标价 ${usd(an.low)}–${usd(an.high)}，平均 ${usd(an.point)}` : ''}${an && pm ? '；' : ''}${pm ? `Polymarket 隐含价格 ${usd(pm.point)}` : ''}。`);
    return { html, facts, mood: an && fin(d.price) && an.point > d.price * 1.15 ? 'happy' : 'talk', links: [[`${BASE}#c-${c.cik}-consensus`, L(lg, 'Consensus', '一致预期页')]] };
  }
  const HANDLERS = { valuation, rotation, industry, options, earnings, credit, analysts };

  function helpAnswer(lg, company) {
    const t = company ? company.ticker : 'NVDA';
    return { html: L(lg, `Hi, I'm <b>Flo</b>. Ask me about any company on the site — I answer from the site's own models: <b>valuation</b> (fair value, DCF, every method), <b>rotation</b> (RRG quadrant, the price that moves it next week, Markov odds), its <b>industry</b>, <b>options</b> (implied range, max pain, walls), the latest <b>earnings</b>, <b>credit</b> and <b>analysts</b>. Try “What is ${t} worth?”`,
      `你好，我是 <b>Flo</b>。可以问我网站上任何公司的问题，我用网站自己的模型回答：<b>估值</b>（合理价值、DCF、各方法）、<b>轮动</b>（RRG 象限、下周进入各象限的价格、马尔科夫概率）、所属<b>行业</b>、<b>期权</b>（隐含区间、最大痛点、call/put wall）、最新<b>财报</b>、<b>信用</b>和<b>分析师</b>。试试「${t} 值多少钱？」`), facts: [], mood: 'wave', links: [] };
  }
  let IX = null;
  const index = () => IX || (IX = json(DATA + 'index.json'));
  // ctxCo: the company of the page being read, used when the question names none ("下周呢？" on MU's page)
  async function ask(q, ixArg, ctxCo) {
    q = String(q || '');
    const lg = lang(q), ix = ixArg || await index(), cls = classify(q);
    let co = findCompany(q, ix) || ctxCo || null;
    if (!co && pageCik() && ix) co = (ix.companies || []).find((c) => +c.cik === pageCik()) || null;
    if (!co) return cls.includes('help') || !q.trim() ? helpAnswer(lg, null)
      : { html: L(lg, 'Which company? Give me a ticker or a name — for example “NVDA valuation” or “Is Apple Leading next week?”', '哪家公司？请给我代码或名称，比如「NVDA 估值」或「苹果下周会进入领先吗？」'), facts: [], mood: 'think', links: [] };
    let intents = cls.filter((k) => k !== 'help');
    if (!intents.length && cls.includes('help')) return helpAnswer(lg, co);
    if (!intents.length) intents = ['valuation', 'rotation', 'earnings'];             // just a company: the overview
    const parts = (await Promise.all(intents.slice(0, 3).map((k) => HANDLERS[k](co, lg).catch(() => null)))).filter(Boolean);
    if (!parts.length) return { html: L(lg, `I don't have that for ${esc(co.ticker)} yet: its data is not published.`, `暂时没有 ${esc(co.ticker)} 的这项数据：尚未发布。`), facts: [], mood: 'worried', links: [[`${BASE}#c-${co.cik}`, co.ticker]], company: co };
    const order = ['worried', 'happy', 'talk'], mood = parts.map((p) => p.mood).sort((a, b) => order.indexOf(a) - order.indexOf(b))[0];
    return { html: parts.map((p) => `<p>${p.html}</p>`).join(''), facts: parts.flatMap((p) => p.facts), mood, links: parts.flatMap((p) => p.links), company: co, intents };
  }

  /* ---------- the mascot ---------- */
  // each copy gets its own gradient ids: a gradient inside a hidden copy (the launcher while the panel is open) does not paint
  const SVG = (n) => `<svg class="flo-svg" viewBox="0 0 120 124" aria-hidden="true">
    <defs><linearGradient id="flo-body${n}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4cc3b2"/><stop offset="1" stop-color="#1f8f80"/></linearGradient>
    <linearGradient id="flo-rib${n}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2a78d6"/><stop offset=".55" stop-color="#4cc3b2"/><stop offset="1" stop-color="#f0b429"/></linearGradient></defs>
    <path class="flo-rib" d="M40 96 C 26 104, 18 116, 4 112 C 16 122, 30 118, 48 104 Z" fill="url(#flo-rib${n})"/>
    <g class="flo-body-g">
      <path d="M60 16 C 58 7, 66 3, 72 8" fill="none" stroke="#1f8f80" stroke-width="3.2" stroke-linecap="round"/><circle cx="72.5" cy="8.5" r="3" fill="#f0b429"/>
      <path d="M60 15 C 85 15, 99 41, 99 65 C 99 89, 83 104, 60 104 C 37 104, 21 89, 21 65 C 21 41, 35 15, 60 15 Z" fill="url(#flo-body${n})"/>
      <ellipse cx="60" cy="86" rx="23" ry="13" fill="#ffffff" opacity=".18"/>
      <g class="flo-arm-l"><path d="M24 70 C 14 72, 10 80, 13 85" fill="none" stroke="#1f8f80" stroke-width="6" stroke-linecap="round"/></g>
      <g class="flo-arm-r"><path d="M96 70 C 106 66, 110 58, 108 52" fill="none" stroke="#1f8f80" stroke-width="6" stroke-linecap="round"/>
        <rect x="100" y="34" width="18" height="15" rx="3" fill="#fff" stroke="#1f8f80" stroke-width="1.5"/><path d="M103 45 L107 41 L110 43 L115 37" fill="none" stroke="#17734a" stroke-width="1.8" stroke-linecap="round"/></g>
      <g class="flo-brows"><path d="M41 43 L52 46" stroke="#123" stroke-width="2.4" stroke-linecap="round"/><path d="M79 43 L68 46" stroke="#123" stroke-width="2.4" stroke-linecap="round"/></g>
      <g class="flo-eyes"><ellipse cx="48" cy="57" rx="9" ry="10" fill="#fff"/><ellipse cx="72" cy="57" rx="9" ry="10" fill="#fff"/>
        <g class="flo-pupils"><circle cx="49" cy="59" r="4.6" fill="#1d1d1b"/><circle cx="73" cy="59" r="4.6" fill="#1d1d1b"/><circle cx="50.6" cy="57" r="1.5" fill="#fff"/><circle cx="74.6" cy="57" r="1.5" fill="#fff"/></g>
        <g class="flo-lids"><rect x="38" y="46" width="20" height="22" rx="9" fill="#3cb4a3"/><rect x="62" y="46" width="20" height="22" rx="9" fill="#3cb4a3"/></g></g>
      <g class="flo-happy-eyes"><path d="M41 59 Q48 51 55 59" fill="none" stroke="#1d1d1b" stroke-width="3" stroke-linecap="round"/><path d="M65 59 Q72 51 79 59" fill="none" stroke="#1d1d1b" stroke-width="3" stroke-linecap="round"/></g>
      <ellipse cx="39" cy="72" rx="5" ry="3" fill="#ff8f8f" opacity=".55"/><ellipse cx="81" cy="72" rx="5" ry="3" fill="#ff8f8f" opacity=".55"/>
      <path class="flo-m-smile" d="M52 74 Q60 82 68 74" fill="none" stroke="#1d1d1b" stroke-width="2.6" stroke-linecap="round"/>
      <ellipse class="flo-m-open" cx="60" cy="77" rx="5.5" ry="4.5" fill="#1d1d1b"/>
      <path class="flo-m-worry" d="M52 79 Q60 72 68 79" fill="none" stroke="#1d1d1b" stroke-width="2.6" stroke-linecap="round"/>
      <path class="flo-sweat" d="M92 40 C 89 46, 89 50, 92 51 C 95 50, 95 46, 92 40 Z" fill="#7fc8ff"/>
    </g>
    <g class="flo-dots"><circle cx="92" cy="18" r="3"/><circle cx="102" cy="12" r="3.5"/><circle cx="113" cy="6" r="4"/></g>
    <g class="flo-spark"><path d="M14 30 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z"/><path d="M104 88 l1.6 4 4 1.6 -4 1.6 -1.6 4 -1.6 -4 -4 -1.6 4 -1.6z"/></g>
  </svg>`;
  const CSS = `.flo-launch{position:fixed;right:18px;bottom:18px;z-index:9000;display:flex;align-items:flex-end;gap:8px;pointer-events:none}.flo-launch[hidden],.flo-panel[hidden]{display:none}
.flo-launch>*{pointer-events:auto}.flo-btn{width:68px;height:70px;border:0;background:none;padding:0;cursor:pointer;filter:drop-shadow(0 4px 10px rgba(0,0,0,.18))}
.flo-btn .flo-svg{width:100%;height:100%}.flo-btn:focus-visible{outline:2px solid var(--accent,#17734a);outline-offset:4px;border-radius:50%}
.flo-hint{background:var(--surface,#fff);color:var(--ink,#222);border:1px solid var(--line,#ddd);border-radius:12px 12px 2px 12px;padding:7px 10px;font-size:12.5px;max-width:200px;box-shadow:0 4px 14px rgba(0,0,0,.08);margin-bottom:34px;animation:flo-pop .4s ease-out}
.flo-hint button{border:0;background:none;color:var(--muted,#888);cursor:pointer;font-size:14px;margin-left:4px;padding:0}
.flo-panel{position:fixed;right:18px;bottom:18px;z-index:9001;width:380px;max-width:calc(100vw - 24px);height:560px;max-height:calc(100vh - 36px);display:flex;flex-direction:column;background:var(--surface,#fff);color:var(--ink,#222);border:1px solid var(--line,#ddd);border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.22);overflow:hidden;animation:flo-pop .25s ease-out;font-family:inherit}
.flo-head{display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid var(--line,#e5e5e5);background:color-mix(in srgb,#4cc3b2 12%,var(--surface,#fff))}
.flo-head .flo-svg{width:56px;height:58px;flex:none}.flo-head b{font-size:15px}.flo-head small{display:block;color:var(--muted,#777);font-size:11.5px;line-height:1.35}
.flo-x{margin-left:auto;border:0;background:none;font-size:22px;line-height:1;color:var(--muted,#777);cursor:pointer;padding:4px 6px;align-self:flex-start}
.flo-log{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;font-size:13.5px;line-height:1.5}
.flo-msg{max-width:92%;padding:8px 11px;border-radius:12px}.flo-msg p{margin:0 0 6px}.flo-msg p:last-child{margin:0}
.flo-me{align-self:flex-end;background:var(--accent,#17734a);color:#fff;border-bottom-right-radius:3px}
.flo-bot{align-self:flex-start;background:var(--surface-2,#efeee9);border-bottom-left-radius:3px}.flo-bot a{color:var(--accent,#17734a)}
.flo-links{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}.flo-links a{font-size:12px;border:1px solid var(--line,#ccc);border-radius:9px;padding:2px 8px;text-decoration:none}
.flo-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px}.flo-chips button{font:inherit;font-size:12px;border:1px solid var(--line,#ccc);background:none;color:inherit;border-radius:12px;padding:3px 9px;cursor:pointer}
.flo-chips button:hover{border-color:var(--accent,#17734a);color:var(--accent,#17734a)}
.flo-form{display:flex;gap:6px;padding:10px 12px;border-top:1px solid var(--line,#e5e5e5)}.flo-form input{flex:1;font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--line,#ccc);border-radius:10px;background:var(--bg,#fff);color:inherit;min-width:0}
.flo-form button{font:inherit;font-size:13px;border:0;border-radius:10px;padding:0 14px;background:var(--accent,#17734a);color:#fff;cursor:pointer}
.flo-local{font:inherit;font-size:12px;margin-top:6px;border:1px dashed var(--line,#bbb);background:none;color:inherit;border-radius:9px;padding:2px 8px;cursor:pointer}
.flo-typing{letter-spacing:2px;animation:flo-dot 1s infinite}
@media (max-width:560px){.flo-panel{right:0;left:0;bottom:0;width:100%;max-width:100%;height:80vh;border-radius:16px 16px 0 0}.flo-launch{right:10px;bottom:10px}.flo-btn{width:54px;height:56px}.flo-hint{display:none}}
@keyframes flo-pop{from{transform:translateY(12px) scale(.96);opacity:0}to{transform:none;opacity:1}}
.flo-svg{overflow:visible}.flo-svg *{transform-box:fill-box}.flo-body-g{transform-origin:50% 100%;animation:flo-bob 3.2s ease-in-out infinite}
.flo-rib{transform-origin:100% 0%;animation:flo-sway 2.6s ease-in-out infinite}
.flo-lids rect{transform-origin:50% 0%;transform:scaleY(0);animation:flo-blink 4.6s infinite}
.flo-arm-r{transform-origin:0% 100%}.flo-arm-l{transform-origin:100% 0%}
.flo-m-open,.flo-m-worry,.flo-brows,.flo-sweat,.flo-dots,.flo-spark,.flo-happy-eyes{opacity:0;transition:opacity .2s}
.flo-dots circle{fill:var(--muted,#9aa)}.flo-spark path{fill:#f0b429}
@keyframes flo-bob{0%,100%{transform:translateY(0) scaleY(1)}50%{transform:translateY(-3px) scaleY(1.015)}}
@keyframes flo-sway{0%,100%{transform:rotate(0)}50%{transform:rotate(-7deg)}}
@keyframes flo-blink{0%,93%,100%{transform:scaleY(0)}95%,97%{transform:scaleY(1)}}
.flo-wave .flo-arm-r{animation:flo-wave .45s ease-in-out 4}
@keyframes flo-wave{0%,100%{transform:rotate(0)}50%{transform:rotate(-28deg)}}
.flo-think .flo-dots{opacity:1}.flo-think .flo-dots circle{animation:flo-dot 1.2s infinite}.flo-think .flo-dots circle:nth-child(2){animation-delay:.2s}.flo-think .flo-dots circle:nth-child(3){animation-delay:.4s}
.flo-think .flo-pupils{transform:translate(2px,-3px);transition:transform .3s}.flo-think .flo-arm-l{transform:rotate(-55deg);transition:transform .3s}
@keyframes flo-dot{0%,100%{opacity:.25}50%{opacity:1}}
.flo-talk .flo-m-smile{opacity:0}.flo-talk .flo-m-open{opacity:1;transform-origin:50% 50%;animation:flo-talk .22s ease-in-out infinite alternate}
@keyframes flo-talk{from{transform:scaleY(.25)}to{transform:scaleY(1)}}
.flo-happy .flo-body-g{animation:flo-jump .55s ease-out 2}.flo-happy .flo-spark{opacity:1;animation:flo-twinkle .8s ease-in-out infinite alternate}.flo-happy .flo-happy-eyes{opacity:1}.flo-happy .flo-eyes{opacity:0}
.flo-happy .flo-arm-r{animation:flo-wave .3s ease-in-out 3}
@keyframes flo-jump{0%{transform:translateY(0) scale(1,1)}30%{transform:translateY(-12px) scale(.96,1.06)}60%{transform:translateY(0) scale(1.06,.94)}100%{transform:translateY(0) scale(1)}}
@keyframes flo-twinkle{from{opacity:.4}to{opacity:1}}
.flo-worried .flo-brows,.flo-worried .flo-m-worry{opacity:1}.flo-worried .flo-m-smile{opacity:0}.flo-worried .flo-body-g{animation:flo-shiver .12s linear 6}
.flo-worried .flo-sweat{opacity:1;animation:flo-drip 1.6s ease-in infinite}
@keyframes flo-shiver{0%,100%{transform:translateX(0)}50%{transform:translateX(1.5px)}}
@keyframes flo-drip{0%{transform:translateY(-2px);opacity:0}30%{opacity:1}100%{transform:translateY(8px);opacity:0}}
@media (prefers-reduced-motion:reduce){.flo-svg *,.flo-panel,.flo-hint{animation:none!important;transition:none!important}}`;

  let ui = null, moodTimer = null;
  function mood(m, ms) {
    if (!ui) return;
    const all = ['flo-wave', 'flo-think', 'flo-talk', 'flo-happy', 'flo-worried'];
    [ui.btn, ui.panel].forEach((el) => { el.classList.remove(...all); if (m && m !== 'idle') el.classList.add('flo-' + m); });
    clearTimeout(moodTimer);
    if (ms) moodTimer = setTimeout(() => mood('idle'), ms);
  }
  const store = { get(k) { try { return root.localStorage.getItem('ffx:flo-' + k); } catch (e) { return null; } }, set(k, v) { try { root.localStorage.setItem('ffx:flo-' + k, v); } catch (e) { /* no storage */ } } };
  const zhUI = () => !!(root.navigator && /^zh/i.test(root.navigator.language || ''));
  const chips = () => chipsFor(ui && ui.ctx, zhUI());
  function addMsg(html, who) {
    const m = doc.createElement('div');
    m.className = 'flo-msg ' + (who === 'me' ? 'flo-me' : 'flo-bot');
    m.innerHTML = html;
    ui.log.appendChild(m);
    ui.log.scrollTop = ui.log.scrollHeight;
    return m;
  }
  async function send(q) {
    q = String(q || '').trim();
    if (!q) return;
    addMsg(esc(q), 'me');
    ui.input.value = '';
    mood('think');
    const wait = addMsg('<span class="flo-typing">• • •</span>', 'bot');
    let a;
    try { a = await ask(q, null, ui.co); } catch (e) { a = { html: 'Something went wrong: ' + esc(e.message), mood: 'worried', facts: [], links: [] }; }
    if (a.company && (!ui.co || a.company.cik !== ui.co.cik) && (!ui.ctx || ui.ctx.kind !== 'company')) { ui.co = a.company; ui.ctx = { kind: 'company', co: a.company, topic: (a.intents || [])[0] || 'earnings', key: ui.ctx && ui.ctx.key }; renderChips(); }
    mood('talk');
    const lg = lang(q), LM = root.LocalFilingModel;
    const local = LM && LM.isConnected && LM.isConnected() && LM.ask && (a.facts || []).length;
    wait.innerHTML = a.html + ((a.links || []).length ? `<div class="flo-links">${a.links.map(([h, t]) => link(h, t)).join('')}</div>` : '') +
      (local ? `<button type="button" class="flo-local">${lg === 'zh' ? '用本地模型解释' : 'Explain with the local model'}</button>` : '');
    ui.log.scrollTop = ui.log.scrollHeight;
    const b = wait.querySelector('.flo-local');
    if (b) b.addEventListener('click', async () => {
      b.disabled = true; b.textContent = '…'; mood('think');
      try {
        const r = await LM.ask(q, a.facts.map((f, i) => ({ id: 'F' + (i + 1), text: f })));
        addMsg(esc(r.insufficient_evidence ? L(lg, 'These figures do not support an answer.', '这些数据不足以回答。') : r.answer), 'bot');
        mood('talk', 1800);
      } catch (e) { addMsg(esc(e.message), 'bot'); mood('worried', 2500); }
      b.remove();
    });
    setTimeout(() => mood(a.mood === 'talk' ? 'idle' : a.mood, a.mood === 'talk' ? 0 : 3200), 1400);
  }
  function renderChips() {
    if (!ui) return;
    ui.chips.innerHTML = chips().map((c) => `<button type="button">${esc(c)}</button>`).join('');
    ui.chips.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => send(b.textContent)));
  }
  function open() {
    if (!ui) return;
    ui.panel.hidden = false; ui.launch.hidden = true;
    if (!ui.log.childElementCount) {
      const g = greetFor(ui.ctx, zhUI());
      addMsg(g || helpAnswer(zhUI() ? 'zh' : 'en', ui.co).html, 'bot'); ui.greeted = ui.ctx && ui.ctx.key; mood('wave', 2000);
    }
    renderChips();
    setTimeout(() => ui.input.focus(), 50);
    store.set('seen', '1');
  }
  function close() { if (!ui) return; ui.panel.hidden = true; ui.launch.hidden = false; mood('idle'); }
  function mount() {
    if (!doc || !doc.body || doc.getElementById('flo-root')) return;
    const st = doc.createElement('style'); st.id = 'flo-css'; st.textContent = CSS; doc.head.appendChild(st);
    const r = doc.createElement('div'); r.id = 'flo-root';
    r.innerHTML = `<div class="flo-launch"><div class="flo-hint"${store.get('seen') ? ' hidden' : ''}>${zhUI() ? '你好！问我任何公司的问题' : 'Hi! Ask me about any company'} <button type="button" aria-label="Dismiss">×</button></div><button type="button" class="flo-btn" aria-label="Ask Flo, the site's assistant">${SVG('a')}</button></div>
      <section class="flo-panel" role="dialog" aria-label="Ask Flo" hidden><div class="flo-head">${SVG('b')}<div><b>Flo</b><small>${zhUI() ? '用网站自己的模型回答：估值、RRG、期权、财报、信用。按固定规则生成，不是投资建议。' : "Answers from the site's models: valuation, RRG, options, earnings, credit. Written by fixed rules; not investment advice."}</small></div><button type="button" class="flo-x" aria-label="Close">×</button></div>
      <div class="flo-log" aria-live="polite"></div><div class="flo-chips"></div>
      <form class="flo-form"><input type="text" placeholder="${zhUI() ? '问一家公司…' : 'Ask about a company…'}" aria-label="Your question" maxlength="300"><button type="submit">${zhUI() ? '问' : 'Ask'}</button></form></section>`;
    doc.body.appendChild(r);
    ui = { launch: r.querySelector('.flo-launch'), btn: r.querySelector('.flo-btn'), panel: r.querySelector('.flo-panel'), log: r.querySelector('.flo-log'), chips: r.querySelector('.flo-chips'),
      input: r.querySelector('.flo-form input'), co: null };
    ui.btn.addEventListener('click', open);
    ui.btn.addEventListener('mouseenter', () => mood('wave', 1800));
    r.querySelector('.flo-hint button').addEventListener('click', (e) => { e.stopPropagation(); e.currentTarget.parentElement.hidden = true; store.set('seen', '1'); });
    r.querySelector('.flo-x').addEventListener('click', close);
    r.querySelector('.flo-form').addEventListener('submit', (e) => { e.preventDefault(); send(ui.input.value); });
    doc.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !ui.panel.hidden) close(); });
    // follow the page: its company becomes the default, its topic leads the default questions
    let indsP = null;
    const sync = async () => {
      const ix = await index();
      const hub = /\/disclosures\//.test(String((root.location || {}).pathname || ''));
      const inds = hub && /^#rotation\/ind~/.test(root.location.hash || '') ? await (indsP || (indsP = json(HUB + 'market/history/industries.json'))) : null;
      const ctx = pageContext(ix, root.location, inds);
      if (ui.ctx && ui.ctx.key === ctx.key) return;
      ui.ctx = ctx; ui.co = ctx.co || null;
      renderChips();
      if (!ui.panel.hidden && ui.log.childElementCount && ui.greeted !== ctx.key) { const g = greetFor(ctx, zhUI()); if (g) { addMsg(g, 'bot'); ui.greeted = ctx.key; } }
    };
    root.addEventListener('hashchange', sync); sync();
    setTimeout(() => mood('wave', 1800), 1200);
  }
  root.FFMascot = { open, ask, mount, classify, findCompany, lang, pageContext, chipsFor };
  if (doc && doc.body !== undefined) { if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', mount); else mount(); }
  if (typeof module !== 'undefined') module.exports = { classify, findCompany, lang, ask, helpAnswer, pageContext, chipsFor, greetFor };
})(typeof globalThis !== 'undefined' ? globalThis : this);
