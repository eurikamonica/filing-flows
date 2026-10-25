/* Flo — the site's mascot and question box: Spin Sankey Flo, two Fs (one upright, one turned 180°) locked together in
   the corner of every page. Its eyes follow the pointer; it waves, thinks, talks and reacts to what it finds, and when
   the chat opens the two Fs split onto the panel's corners. Ask it about any company on the site, in
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
  const academy = () => root.FFFloAcademy || (typeof module !== 'undefined' ? require('./flo-academy.js') : null);
  const workbooks = () => root.FFFloWorkbook || (typeof module !== 'undefined' ? require('./flo-workbook.js') : null);
  const memo = new Map();
  const json = (u) => { if (!memo.has(u)) memo.set(u, fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null)); return memo.get(u); };
  const fileT = (t) => String(t || '').toUpperCase().replace(/\./g, '-');
  const QN = { en: ['Leading', 'Weakening', 'Lagging', 'Improving'], zh: ['领先', '转弱', '落后', '改善'] };
  const L = (lg, en, zh) => (lg === 'zh' ? zh : en);

  /* ---------- the question ---------- */
  const lang = (q) => (/[㐀-鿿]/.test(String(q || '')) ? 'zh' : 'en');
  const INTENTS = [
    ['filings', /\bfil(?:ing|ings|ling|lings)\b|\bedgar\b|\b(?:sec\s+)?submissions?\b|(?:latest|recent|newest|last)\s+(?:sec\s+)?(?:reports?|documents?|filings?|fillings?)\b|(?:最新|最近(?:一次)?)(?:的|\s)*(?:SEC\s*)?(?:申报|披露|文件|提交)|SEC\s*(?:文件|申报|披露)/i],
    // widen these when web/flo-questions.js gains a phrasing Flo misses (tests/test_mascot.cjs checks every one)
    ['options', /\boptions?\b|max ?pain|put wall|call wall|option walls?|implied (move|vol|range)|expected move|\d+% range|\biv\b|\bstrikes?\b|expir|期权|最大痛点|看涨墙|看跌墙|隐含波动|隐含区间|预期波动|行权价|到期/i],
    ['industry', /\bindustr(y|ies)\b|\bsector\b|\bpeers?\b|行业|板块|同业/i],
    ['rotation', /\brrg\b|rotation|rotating|momentum|quadrant|leading|lagging|weakening|improving|relative strength|rs-?ratio|outperform|underperform|beating the market|markov|next week|轮动|象限|动量|领先|落后|转弱|改善|相对强弱|跑赢|跑输|强于大盘|弱于大盘|马尔科夫|轮出|轮入|下周/i],
    ['credit', /\bdebt\b|credit|default|bankrupt|distress|altman|solven|leverage|balance sheet|债务|违约|信用|破产|偿债|杠杆|利差|还得起债|财务困境|负债/i],
    ['analysts', /analyst|price target|target price|consensus|polymarket|kalshi|wall street|prediction markets?|\btargets?\b|\bstreet\b|\brating\b|分析师|目标价|一致预期|预测市场|华尔街|评级/i],
    ['earnings', /revenue|earnings|profit|margin(?! of safety)|\beps\b|quarter|sales|income|cash flow|year (on|over) year|\byoy\b|\b10-[qk]\b|results|top line|收入|营收|利润|财报|毛利|季度|净利|现金流|业绩|同比|年报|季报|盈利|销售额/i],
    ['valuation', /worth|\bvalue\b|valuation|fair|cheap|expensive|overvalued|undervalued|\bdcf\b|intrinsic|\bbuy\b|upside|downside|margin of safety|monte carlo|\bpvgo\b|for growth|future growth|bull case|bear case|justified|估值|值多少|便宜|贵|低估|高估|合理价|内在价值|值得买|价值|上涨空间|下跌空间|安全边际|蒙特卡洛|为增长|未来增长|价格合理/i],
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
  const HUB_TOPIC = { filings: 'filings', valuation: 'valuation', rotation: 'rotation', options: 'options', debt: 'credit', consensus: 'analysts', earnings: 'earnings', quality: 'earnings', filings: 'earnings' };
  const TOPICS = ['filings', 'valuation', 'rotation', 'options', 'earnings', 'industry', 'credit', 'analysts'];
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
    filings: [(t) => `${t} latest SEC filing`, (t) => `${t} 最新 SEC 申报`, (t) => `${t} most recent 10-K or 10-Q`, (t) => `${t} 最近的 10-K 或 10-Q`],
    valuation: [(t) => `What is ${t} worth?`, (t) => `${t} 值多少钱？`, (t) => `${t} DCF and Monte Carlo`, (t) => `${t} 的 DCF 和蒙特卡洛估值`],
    rotation: [(t) => `Will ${t} be Leading next week?`, (t) => `${t} 下周会进入领先象限吗？`, (t) => `Where will ${t}'s quadrant be in 4 weeks?`, (t) => `${t} 4 周后在哪个象限？`],
    options: [(t) => `${t} options: range and max pain`, (t) => `${t} 期权的隐含区间和最大痛点`, (t) => `${t} put wall and call wall`, (t) => `${t} 期权的 put wall 和 call wall`],
    earnings: [(t) => `${t} latest earnings`, (t) => `${t} 最新财报`, (t) => `${t} revenue growth and margin`, (t) => `${t} 营收增长和利润率`],
    industry: [(t) => `How is ${t}'s industry rotating?`, (t) => `${t} 所在行业轮动`, (t) => `Is ${t}'s industry Leading?`, (t) => `${t} 所在行业处于哪个象限？`],
    credit: [(t) => `${t} debt and default risk`, (t) => `${t} 的债务和违约风险`, (t) => `${t} Altman Z and credit spread`, (t) => `${t} 的信用利差和 Altman Z`],
    analysts: [(t) => `${t} analyst price target`, (t) => `${t} 分析师目标价`, (t) => `${t} Polymarket implied price`, (t) => `${t} 预测市场隐含价格`],
  };
  // the bank (web/flo-questions.js) when it is loaded; the two built-in questions per topic otherwise
  function pool(topic, zh) {
    const b = root.FFFloQuestions, l = b && b[topic] && b[topic].default && b[topic].default[zh ? 'zh' : 'en'];
    if (l && l.length) return l;
    const f = Q[topic];
    return zh ? [f[1]('{t}'), f[3]('{t}')] : [f[0]('{t}'), f[2]('{t}')];
  }
  const pick = (topic, t, zh, n) => { const l = pool(topic, zh); return l[((n % l.length) + l.length) % l.length].replace(/\{t\}/g, t); };
  // the default questions for a page: up to six, the page's own topic first; `seed` (More questions) moves through the bank
  function chipsFor(ctx, zh, seed) {
    ctx = ctx || { kind: 'home' };
    const s = +seed || 0;
    const q1 = (topic, t, zh2, second) => pick(topic, t, zh2, (second ? 2 * s + 1 : 2 * s));
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
  const TOPIC_NAME = { en: { filings: 'SEC filings', valuation: 'fair value', rotation: 'rotation (RRG)', options: 'options', earnings: 'earnings', credit: 'debt and credit', analysts: 'analysts' },
    zh: { filings: 'SEC 申报', valuation: '估值', rotation: 'RRG 轮动', options: '期权', earnings: '财报', credit: '债务与信用', analysts: '分析师' } };
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
  // A filing is not automatically an earnings release. Current per-company cache
  // provides processed 10-K / 10-Q records, not a complete/live SEC submissions list.
  async function filings(c, lg) {
    const secBrowse = 'https://www.sec.gov/edgar/browse/?CIK=' + encodeURIComponent(String(c.cik));
    const links = [[secBrowse, L(lg, 'SEC EDGAR: latest filings of all forms', 'SEC EDGAR：所有表格的最新申报')]];
    const d = await fetch(DATA + 'c/' + c.cik + '.json', { cache: 'no-cache' })
      .then(r => r.ok ? r.json() : null).catch(() => null);
    const qs = ((d && d.quarters) || []).filter(q =>
      q && /^10-[KQ](?:\/A)?$/i.test(String(q.form || '')) &&
      /^\d{4}-\d{2}-\d{2}/.test(String(q.filed || '')));
    if (!qs.length) {
      const html = L(lg,
        'I cannot verify ' + esc(c.ticker) + "'s latest SEC filing from this site's published reports. Check the live EDGAR link. A 10-K/10-Q is not necessarily the newest SEC submission.",
        '目前网站发布的数据无法核实 ' + esc(c.ticker) + ' 最新的 SEC 申报。请通过 EDGAR 实时页面查看；最新 10-K/10-Q 不一定是最新 SEC 文件。');
      return {html, facts:[], mood:'think', links};
    }
    qs.sort((a,b)=> String(b.filed).localeCompare(String(a.filed)) ||
      String(b.label || '').localeCompare(String(a.label || '')));
    const q = qs[0];
    if (/^https:\/\/www\.sec\.gov\//i.test(String(q.doc_url || '')))
      links.unshift([q.doc_url, L(lg, 'Original 10-K / 10-Q document', '原始 10-K / 10-Q 文件')]);
    links.push([BASE + '#c-' + c.cik, L(lg, 'Filing Flows: financial statements', 'Filing Flows 财报页面')]);
    const facts = [c.ticker + ' latest processed financial filing: ' + q.form +
      ', quarter ' + (q.label || 'unknown') + ', filed ' + q.filed +
      '. All-form latest SEC submission NOT verified from this cache.'];
    const html = L(lg,
      'The most recent <b>10-K/10-Q in Filing Flows</b> for <b>' + esc(c.ticker) +
      '</b> is <b>' + esc(q.form) + '</b> (' + esc(q.label || 'period unavailable') +
      '), filed <b>' + esc(q.filed) +
      '</b>. This is the latest <em>processed financial report</em>, not necessarily the newest SEC filing overall. For newer 8-K, Form 4, 144 or other submissions, check the live SEC EDGAR link.',
      '<b>' + esc(c.ticker) + '</b> 在 Filing Flows 已处理的最新 <b>10-K/10-Q</b> 是 <b>' +
      esc(q.form) + '</b>（' + esc(q.label || '报告期间未知') + '），于 <b>' + esc(q.filed) +
      '</b> 提交。这只是网站处理过的最新<b>财务定期报告</b>，不代表 SEC 所有表格中最新的一份。要查看更新的 8-K、Form 4、144 等，请打开 SEC EDGAR 实时页面。');
    return {html, facts, mood:'talk', links};
  }

  async function earnings(c, lg) {
    const d = await json(DATA + 'c/' + c.cik + '.json');
    const qs = (d && d.quarters) || [];
    if (!qs.length) return null;
    // the newest quarter by its end date (the page lists newest first), and the one about a year before it
    const T = (x) => Date.parse((x.end || x.filed || '') + 'T00:00:00Z') || 0, srt = qs.slice().sort((a, b) => T(b) - T(a));
    const q = srt[0], h = q.headline || {}, yq = srt.find((x) => Math.abs((T(q) - T(x)) / 864e5 - 364) <= 45), ya = (yq && yq.headline) || {};
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
  const HANDLERS = { filings, valuation, rotation, industry, options, earnings, credit, analysts };

  function helpAnswer(lg, company) {
    const t = company ? company.ticker : 'NVDA';
    return { html: L(lg, `Hi, I'm <b>Flo</b>. Ask me for a step-by-step DCF tutorial, cookie jar investigation, a number explanation, or SEC case studies. I also answer from the site's own models: <b>valuation</b> (fair value, DCF, every method), <b>rotation</b> (RRG quadrant, the price that moves it next week, Markov odds), its <b>industry</b>, <b>options</b> (implied range, max pain, walls), the latest <b>earnings</b>, <b>SEC filings</b>, <b>credit</b> and <b>analysts</b>. Try “What is ${t} worth?”`,
      `你好，我是 <b>Flo</b>。我还能逐步教 DCF、调查 Cookie Jar 准备金、解释图表中的数字并讲解 SEC 真实案例。网站模型包括：<b>估值</b>（合理价值、DCF、各方法）、<b>轮动</b>（RRG 象限、下周进入各象限的价格、马尔科夫概率）、所属<b>行业</b>、<b>期权</b>（隐含区间、最大痛点、call/put wall）、最新<b>财报</b>、<b>SEC 申报</b>、<b>信用</b>和<b>分析师</b>。试试「${t} 值多少钱？」`), facts: [], mood: 'wave', links: [] };
  }
  let IX = null;
  const index = () => IX || (IX = json(DATA + 'index.json'));
  // ctxCo: the company of the page being read, used when the question names none ("下周呢？" on MU's page)
  async function ask(q, ixArg, ctxCo) {
    q = String(q || '');
    const lg = lang(q), ix = ixArg || await index(), cls = classify(q);
    let co = findCompany(q, ix) || ctxCo || null;
    const WB = workbooks();
    if (WB && WB.match(q)) return { ...WB.launch(q, lg), company: co || null };
    const A = academy();
    if (A && A.match(q)) {
      const a = await A.handle(q, co, lg, c => json(DATA + 'c/' + c.cik + '.json'));
      if (a) return { ...a, company: co || null };
    }
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

  /* ---------- the mascot: Spin Sankey Flo ---------- */
  // Two Fs, one upright and one turned 180°, locked together: Filing (grey stem) and Flows (mint stem), each with a
  // Sankey band for its middle bar and the logo's green and red tips. Both halves follow the pointer with their eyes and
  // lean toward it; when the chat opens they split and sit on the panel's top-left and bottom-right corners.
  const C = { rev: '#7a7974', mint: '#a8d1b9', green: '#17734a', salmon: '#f6c3b8', red: '#ea6a52' };
  const F = (stem, top) => `<rect x="38" y="14" width="50" height="16" rx="6" fill="${top}"/><rect x="88" y="14" width="6" height="16" rx="1.5" fill="${C.green}"/>` +
    `<path d="M38 38 C 54 38, 56 44, 72 44 L 72 56 C 56 56, 54 50, 38 50 Z" fill="${C.salmon}"/><rect x="72" y="44" width="5" height="12" rx="1.5" fill="${C.red}"/>` +
    `<rect x="14" y="14" width="26" height="70" rx="9" fill="${stem}"/>`;
  const FACE = (tf) => `<g transform="${tf}">
    <g class="flo-eyes"><ellipse cx="48" cy="57" rx="8.5" ry="9.5" fill="#fff"/><ellipse cx="72" cy="57" rx="8.5" ry="9.5" fill="#fff"/>
      <g class="flo-pupils"><circle cx="49" cy="59" r="4.4" fill="#1d1d1b"/><circle cx="73" cy="59" r="4.4" fill="#1d1d1b"/><circle cx="50.5" cy="57" r="1.4" fill="#fff"/><circle cx="74.5" cy="57" r="1.4" fill="#fff"/></g></g>
    <g class="flo-h-eyes"><path d="M41 60 Q48 51 55 60" fill="none" stroke="#1d1d1b" stroke-width="3.2" stroke-linecap="round"/><path d="M65 60 Q72 51 79 60" fill="none" stroke="#1d1d1b" stroke-width="3.2" stroke-linecap="round"/></g>
    <g class="flo-brows"><path d="M38 43 L52 47" stroke="#1d1d1b" stroke-width="2.8" stroke-linecap="round"/><path d="M82 43 L68 47" stroke="#1d1d1b" stroke-width="2.8" stroke-linecap="round"/></g>
    <path class="flo-m-idle" d="M52 74 Q60 81 68 74" fill="none" stroke="#1d1d1b" stroke-width="2.6" stroke-linecap="round"/>
    <path class="flo-m-happy" d="M51 70 Q60 85 69 70 Z" fill="#1d1d1b"/>
    <ellipse class="flo-m-talk" cx="60" cy="76" rx="5.5" ry="4.5" fill="#1d1d1b"/>
    <path class="flo-m-think" d="M55 76 L66 74" fill="none" stroke="#1d1d1b" stroke-width="2.6" stroke-linecap="round"/>
    <path class="flo-m-worried" d="M53 78 Q60 72 67 78" fill="none" stroke="#1d1d1b" stroke-width="2.6" stroke-linecap="round"/>
    <path class="flo-sweat" d="M92 30 C 88 38, 88 42, 92 43 C 96 42, 96 38, 92 30 Z" fill="#5b7fa6"/></g>`;
  const EXTRA = (x, y) => `<g class="flo-dots"><circle cx="${x}" cy="${y}" r="3"/><circle cx="${x + 8}" cy="${y - 5}" r="3.4"/><circle cx="${x + 17}" cy="${y - 10}" r="3.8"/></g>` +
    `<path class="flo-spark" d="M${x + 10} ${y - 14} l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z" fill="${C.green}"/>`;
  const FX1 = 'translate(27 34) scale(0.46) translate(-60 -60)', FX2 = 'translate(93 86) scale(0.46) translate(-60 -60)';
  const HALF1 = `<svg class="flo-svg" viewBox="0 0 120 120" aria-hidden="true">${F(C.rev, C.mint)}${FACE(FX1)}${EXTRA(46, 14)}</svg>`;
  const HALF2 = `<svg class="flo-svg" viewBox="0 0 120 120" aria-hidden="true"><g transform="rotate(180 60 60)">${F(C.mint, C.rev)}</g>${FACE(FX2)}${EXTRA(100, 64)}</svg>`;
  const CSS = `.flo-launch{position:fixed;right:18px;bottom:18px;z-index:9000;display:flex;align-items:flex-end;gap:8px;pointer-events:none}.flo-launch[hidden],.flo-panel[hidden]{display:none}
.flo-launch>*{pointer-events:auto}.flo-btn{width:84px;height:84px;border:0;background:none;padding:0;cursor:pointer;opacity:0}
.flo-btn:focus-visible{opacity:1;outline:2px solid var(--accent,#17734a);outline-offset:4px;border-radius:18px}
.flo-hint{background:var(--surface,#fff);color:var(--ink,#222);border:1px solid var(--line,#ddd);border-radius:12px 12px 2px 12px;padding:7px 10px;font-size:12.5px;max-width:200px;box-shadow:0 4px 14px rgba(0,0,0,.08);margin-bottom:40px;animation:flo-pop .4s ease-out}
.flo-hint button{border:0;background:none;color:var(--muted,#888);cursor:pointer;font-size:14px;margin-left:4px;padding:0}
.flo-half{position:fixed;left:0;top:0;width:84px;height:84px;z-index:9002;cursor:pointer;-webkit-tap-highlight-color:transparent;transition:left .62s cubic-bezier(.34,1.4,.5,1),top .62s cubic-bezier(.34,1.4,.5,1),width .5s,height .5s;filter:drop-shadow(0 3px 6px rgba(0,0,0,.14))}
.flo-half .flo-svg{width:100%;height:100%;overflow:visible;display:block}
.flo-panel{position:fixed;right:58px;bottom:58px;z-index:9001;width:380px;max-width:calc(100vw - 120px);height:540px;max-height:calc(100vh - 150px);display:flex;flex-direction:column;background:var(--surface,#fff);color:var(--ink,#222);border:1px solid var(--line,#ddd);border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.22);overflow:hidden;animation:flo-pop .3s cubic-bezier(.3,1.3,.5,1);font-family:inherit}
.flo-head{display:flex;align-items:center;gap:10px;padding:10px 12px 10px 58px;border-bottom:1px solid var(--line,#e5e5e5);background:color-mix(in srgb,#a8d1b9 22%,var(--surface,#fff))}
.flo-head b{font-size:15px}.flo-head small{display:block;color:var(--muted,#777);font-size:11.5px;line-height:1.35}
.flo-x{margin-left:auto;border:0;background:none;font-size:22px;line-height:1;color:var(--muted,#777);cursor:pointer;padding:4px 6px;align-self:flex-start}
.flo-log{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;font-size:13.5px;line-height:1.5}
.flo-msg{max-width:92%;padding:8px 11px;border-radius:12px}.flo-msg p{margin:0 0 6px}.flo-msg p:last-child{margin:0}
.flo-me{align-self:flex-end;background:var(--accent,#17734a);color:#fff;border-bottom-right-radius:3px}
.flo-bot{align-self:flex-start;background:var(--surface-2,#efeee9);border-bottom-left-radius:3px}.flo-bot a{color:var(--accent,#17734a)}
.flo-links{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}.flo-links a{font-size:12px;border:1px solid var(--line,#ccc);border-radius:9px;padding:2px 8px;text-decoration:none}
.flo-modes{display:flex;gap:5px;flex-wrap:wrap;flex-basis:100%;padding:1px 0 4px}.flo-modes button{background:color-mix(in srgb,var(--accent,#17734a) 12%,var(--surface,#fff));border-color:var(--accent,#17734a);font-weight:600}
.flo-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.flo-actions button{font:inherit;font-size:12px;border:1px solid var(--accent,#17734a);border-radius:8px;background:transparent;color:inherit;padding:4px 8px;cursor:pointer}
.flo-panel.flo-wide{width:min(850px,calc(100vw - 120px))}.flo-wide .flo-msg.flo-bot{max-width:100%;width:100%}
.flo-workbook{border:1px solid var(--line,#d7d7d7);border-radius:10px;padding:8px;background:var(--surface,#fff);color:var(--ink,#222)}
.flo-wb-head{display:flex;align-items:center;justify-content:space-between;gap:12px;font-weight:700}.flo-wb-head small{font-weight:400;color:var(--muted,#777)}
.flo-wb-controls,.flo-wb-toolbar{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}.flo-wb-controls label{font-size:11px;display:flex;align-items:center;gap:5px}.flo-wb-controls select{max-width:240px;min-width:100px;font:inherit;padding:5px;border:1px solid var(--line,#ccc);border-radius:6px;background:var(--surface,#fff);color:inherit}
.flo-wb-toolbar button{font:inherit;font-size:11px;padding:5px 7px;border:1px solid var(--line,#ccc);border-radius:6px;background:var(--surface,#fff);color:inherit;cursor:pointer}
.flo-wb-toolbar button:hover{border-color:var(--accent,#17734a)}
.flo-wb-formula{display:flex;align-items:stretch;gap:5px;margin-bottom:6px}
.flo-wb-formula span{font-family:monospace;background:var(--surface-2,#eee);padding:6px 10px;border:1px solid var(--line,#ccc);min-width:52px;text-align:center}
.flo-wb-formula input{font-family:monospace;min-width:0;flex:1;border:1px solid var(--line,#ccc);padding:6px;background:var(--surface,#fff);color:inherit;border-radius:6px}
.flo-wb-formula button{border:0;border-radius:6px;color:#fff;background:var(--accent,#17734a);cursor:pointer}
.flo-wb-scroll{overflow-x:auto;max-width:100%;border:1px solid var(--line,#ccc);border-radius:6px;max-height:360px;overflow-y:auto}
.flo-wb-table{border-collapse:separate;border-spacing:0;font:11px 'IBM Plex Mono',monospace;min-width:570px;width:100%;table-layout:fixed}
.flo-wb-table th,.flo-wb-table td{border-right:1px solid var(--line,#dedede);border-bottom:1px solid var(--line,#dedede);padding:0;overflow:hidden;white-space:nowrap}
.flo-wb-table thead th,.flo-wb-table tr:first-child th{background:var(--surface-2,#eee)}
.flo-wb-table th.flo-wb-line{position:sticky;left:0;background:var(--surface-2,#eee);width:28px;text-align:center;z-index:2}
.flo-wb-table th.flo-wb-label{position:sticky;left:28px;background:var(--surface,#fff);min-width:190px;width:190px;padding:6px 7px;text-align:left;z-index:1}
.flo-wb-table tr:first-child th:first-child{width:28px}
.flo-wb-table td{min-width:85px;text-align:right}
.flo-wb-table td button{display:block;border:0;background:none;color:inherit;padding:6px 8px;font:inherit;width:100%;text-align:right;cursor:cell;min-height:26px}
.flo-wb-table .flo-wb-input{background:color-mix(in srgb,#397ad7 13%,var(--surface,#fff));color:var(--ink,#222)}
.flo-wb-table .flo-wb-formula{background:color-mix(in srgb,#9871cb 12%,var(--surface,#fff));color:var(--ink,#222)}
.flo-wb-table td.selected{outline:2px solid var(--accent,#17734a);outline-offset:-2px;position:relative}
.flo-wb-table .flo-wb-empty{background:var(--surface,#fff)}
.flo-wb-table th.flo-wb-heading{background:var(--surface-2,#eee);color:var(--ink,#222);padding:6px}
.flo-wb-help,.flo-wb-feedback{font-size:11px;color:var(--muted,#777);margin:5px 0}
@media (max-width:560px){.flo-panel.flo-wide{width:100%;max-width:100%}.flo-wb-scroll{max-height:44vh}.flo-wb-table th.flo-wb-label{width:155px;min-width:155px}}
.flo-mini-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:8px 0}.flo-mini-form label{display:flex;flex-direction:column;font-size:11px}.flo-mini-form input{min-width:0;width:100%;border-radius:6px;border:1px solid var(--line,#ccc);color:inherit;background:var(--surface,#fff);font:inherit;padding:5px}.flo-mini-form button{border:0;border-radius:8px;background:var(--accent,#17734a);color:#fff;cursor:pointer;padding:6px;font:inherit;grid-column:1/-1}
.flo-example{border-left:3px solid var(--accent,#17734a);padding:7px 9px;margin:7px 0;background:var(--surface,#fff);border-radius:0 8px 8px 0}.flo-source{font-size:11px;color:var(--muted,#777)}.flo-list{padding-left:18px;margin:7px 0}.flo-list li{margin-bottom:4px}.flo-ac-head{display:flex;align-items:center;justify-content:space-between;gap:7px}.flo-ac-head small{color:var(--muted,#777)}

.flo-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px}.flo-chips button{font:inherit;font-size:12px;border:1px solid var(--line,#ccc);background:none;color:inherit;border-radius:12px;padding:3px 9px;cursor:pointer}
.flo-chips .flo-more{border-style:dashed;color:var(--muted,#777)}.flo-chips button:hover{border-color:var(--accent,#17734a);color:var(--accent,#17734a)}
.flo-form{display:flex;gap:6px;padding:10px 54px 12px 12px;border-top:1px solid var(--line,#e5e5e5)}.flo-form input{flex:1;font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--line,#ccc);border-radius:10px;background:var(--bg,#fff);color:inherit;min-width:0}
.flo-form button{font:inherit;font-size:13px;border:0;border-radius:10px;padding:0 14px;background:var(--accent,#17734a);color:#fff;cursor:pointer}
.flo-local{font:inherit;font-size:12px;margin-top:6px;border:1px dashed var(--line,#bbb);background:none;color:inherit;border-radius:9px;padding:2px 8px;cursor:pointer}
.flo-typing{letter-spacing:2px;animation:flo-dot 1s infinite}
@media (max-width:560px){.flo-panel{right:0;left:0;bottom:0;width:100%;max-width:100%;height:74vh;max-height:74vh;border-radius:16px 16px 0 0}.flo-head{padding-left:12px}.flo-launch{right:10px;bottom:10px}.flo-btn{width:66px;height:66px}.flo-hint{display:none}.flo-form{padding-right:12px}}
@keyframes flo-pop{from{transform:translateY(12px) scale(.96);opacity:0}to{transform:none;opacity:1}}
.flo-eyes{transform-box:fill-box;transform-origin:center;transition:transform .09s}.flo-blink .flo-eyes{transform:scaleY(.08)}
.flo-half .flo-h-eyes,.flo-half .flo-brows,.flo-half .flo-m-happy,.flo-half .flo-m-talk,.flo-half .flo-m-think,.flo-half .flo-m-worried,.flo-half .flo-sweat,.flo-half .flo-dots,.flo-half .flo-spark{display:none}
.flo-half[data-mood="happy"] .flo-eyes,.flo-half[data-mood="wave"] .flo-eyes{display:none}
.flo-half[data-mood="happy"] .flo-h-eyes,.flo-half[data-mood="happy"] .flo-m-happy,.flo-half[data-mood="happy"] .flo-spark,.flo-half[data-mood="wave"] .flo-h-eyes,.flo-half[data-mood="wave"] .flo-m-happy{display:inline}
.flo-half[data-mood]:not([data-mood="idle"]) .flo-m-idle{display:none}
.flo-half[data-mood="talk"] .flo-m-talk{display:inline;transform-box:fill-box;transform-origin:center;animation:flo-talk .22s ease-in-out infinite alternate}
.flo-half[data-mood="think"] .flo-m-think,.flo-half[data-mood="think"] .flo-dots{display:inline}
.flo-half[data-mood="worried"] .flo-brows,.flo-half[data-mood="worried"] .flo-m-worried,.flo-half[data-mood="worried"] .flo-sweat{display:inline}
.flo-dots circle{fill:var(--muted,#9a9994);animation:flo-dot 1s infinite}.flo-dots circle:nth-child(2){animation-delay:.15s}.flo-dots circle:nth-child(3){animation-delay:.3s}
@keyframes flo-dot{0%,100%{opacity:.25}50%{opacity:1}}
@keyframes flo-talk{from{transform:scaleY(.3)}to{transform:scaleY(1)}}
@media (prefers-reduced-motion:reduce){.flo-half,.flo-panel,.flo-hint,.flo-half *{animation:none!important;transition:none!important}}`;

  let ui = null, moodTimer = null;
  const nowMs = () => (root.performance && root.performance.now ? root.performance.now() : Date.now());
  function mood(m, ms) {
    if (!ui) return;
    m = m || 'idle';
    ui.mood = m;
    ui.halves.forEach((h) => { h.el.dataset.mood = m; });
    const t = nowMs();
    if (m === 'happy' || m === 'wave') ui.halves.forEach((h, i) => { h.hop = t + 460 + i * 140; });
    if (m === 'worried') ui.halves.forEach((h) => { h.shake = t + 560; });
    clearTimeout(moodTimer);
    if (ms) moodTimer = setTimeout(() => mood('idle'), ms);
  }
  const store = { get(k) { try { return root.localStorage.getItem('ffx:flo-' + k); } catch (e) { return null; } }, set(k, v) { try { root.localStorage.setItem('ffx:flo-' + k, v); } catch (e) { /* no storage */ } } };
  const zhUI = () => !!(root.navigator && /^zh/i.test(root.navigator.language || ''));
  const chips = () => chipsFor(ui && ui.ctx, zhUI(), ui ? ui.seed : 0);
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
    ui.panel.classList.toggle('flo-wide', !!a.workbook);
    wait.innerHTML = a.html + ((a.links || []).length ? `<div class="flo-links">${a.links.map(([h, t]) => link(h, t)).join('')}</div>` : '') +
      ((a.actions || []).length ? `<div class="flo-actions">${a.actions.map(x => `<button type="button" class="flo-action" data-flo-q="${esc(x.question)}">${esc(x.label)}</button>`).join('')}</div>` : '') +
      (local ? `<button type="button" class="flo-local">${lg === 'zh' ? '用本地模型解释' : 'Explain with the local model'}</button>` : '');
    ui.log.scrollTop = ui.log.scrollHeight;
    if (a.workbook && workbooks()) workbooks().mountAll(wait,lg);
    wait.querySelectorAll('.flo-action').forEach(b => b.addEventListener('click', () => send(b.dataset.floQ)));
    wait.querySelectorAll('form[data-flo-calc]').forEach(form => form.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const A = academy(); if (!A) return;
      const fields = Object.fromEntries(Array.from(form.querySelectorAll('input[name], select[name]')).map(input => [input.name, input.value]));
      try {
        if (form.dataset.floCalc === 'reserve') {
          const v = A.reserveScenario(fields);
          addMsg('<b>Reserve rollforward simulation</b><p>Closing reserve ' + usd(v.reserve) +
            ' · Pretax profit ' + usd(v.profit) +
            ' · Cash ' + usd(v.cash) +
            '.</p><small>Illustration only. Releases are not proof of earnings manipulation.</small>', 'bot');
        } else if (form.dataset.floCalc === 'fcff') {
          const v = A.fcff(fields);
          addMsg('<b>FCFF = ' + esc(v.toLocaleString('en-US', {maximumFractionDigits:2})) +
            '</b> (same units as exercise). EBIT × (1−Tax%) + D&amp;A − CapEx − ΔNWC. <small>Hypothetical inputs, NOT company data.</small>', 'bot');
        } else if (form.dataset.floCalc === 'rebate') {
          const v = A.rebate(fields);
          addMsg('<b>Rebate allocation</b><p>Total ' + usd(v.total) +
            ' · Sold units → COGS reduction ' + usd(v.cogs) +
            ' · Unsold units → inventory cost reduction ' + usd(v.inventory) +
            '.</p><small>Hypothetical contract; actual recognition varies.</small>', 'bot');
        }
        mood('happy',1600);
      } catch(e) { addMsg(esc(e.message),'bot'); mood('worried',1800); }
    }));
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
    const T = (ui.co && ui.co.ticker) || 'NVDA';
    const zh = zhUI();
    const modes = [
      [zh ? 'Excel 模拟练习' : 'Spreadsheet Lab', 'open Excel modeling lab'],
      [zh ? '学 DCF' : 'Learn DCF', 'teach ' + T + ' DCF step by step'],
      [zh ? 'Cookie Jar 侦探' : 'Cookie Jar', T + ' cookie jar'],
      [zh ? 'SEC 案例' : 'SEC cases', 'Sunbeam case study'],
      [zh ? '返利练习' : 'Rebate lab', 'supplier rebate exercise']
    ];
    ui.chips.innerHTML = '<div class="flo-modes">' + modes.map(m => '<button type="button" class="flo-mode" data-flo-q="' + esc(m[1]) + '">' + esc(m[0]) + '</button>').join('') + '</div>' +
      chips().map((c) => `<button type="button">${esc(c)}</button>`).join('') +
      `<button type="button" class="flo-more" aria-label="${zhUI() ? '换一批问题' : 'More questions'}">↻ ${zhUI() ? '换一批' : 'More'}</button>`;
    ui.chips.querySelectorAll('.flo-mode').forEach(b => b.addEventListener('click', () => send(b.dataset.floQ)));
    ui.chips.querySelectorAll('button:not(.flo-more):not(.flo-mode)').forEach(b => b.addEventListener('click', () => send(b.textContent)));
    ui.chips.querySelector('.flo-more').addEventListener('click', () => { ui.seed = (ui.seed || 0) + 1; renderChips(); });
  }

  /* where the halves stand: locked together in the corner, or split onto the open panel's corners */
  function place(h, x, y, s) { h.x = x; h.y = y; h.s = s; h.el.style.left = x + 'px'; h.el.style.top = y + 'px'; h.el.style.width = h.el.style.height = s + 'px'; }
  function layout() {
    if (!ui) return;
    const W = root.innerWidth, H = root.innerHeight, small = W <= 560;
    if (ui.panel.hidden) {
      const S = small ? 66 : 84, a = ui.hover ? 6 : 0, pad = small ? 10 : 18;
      const L0 = W - pad - S, T0 = H - pad - S;
      place(ui.halves[0], L0 - a, T0 - a, S); place(ui.halves[1], L0 + a, T0 + a, S);
    } else {
      const r = ui.panel.getBoundingClientRect(), S = small ? 72 : 96;
      if (small) {                                     // a phone's bottom sheet: both stand on its top edge, clear of the ×
        place(ui.halves[0], r.left + 4, r.top - 0.86 * S, S);
        place(ui.halves[1], r.right - 0.9 * S - 52, r.top - 0.9 * S, S);
      } else {                                         // each F's own box centred on a corner, half of it outside
        place(ui.halves[0], r.left - 0.45 * S, r.top - 0.41 * S, S);
        place(ui.halves[1], r.right - 0.55 * S, r.bottom - 0.59 * S, S);
      }
    }
  }
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function target(h, i, t) {
    if (h.look && t < h.look.until) return h.look;
    if (ui.mood === 'think') { const r = h.el.getBoundingClientRect(); return { x: r.left + r.width, y: r.top - 80 }; }
    if (!ui.panel.hidden && t < ui.typingUntil) { const r = ui.input.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }
    if (t - ui.ptr.t > 4000) {                         // nobody moving the pointer: look around
      const k = Math.floor((t - ui.ptr.t) / 1600), ang = k * 2.4 + i;
      return { x: root.innerWidth / 2 + Math.cos(ang) * root.innerWidth * 0.4, y: root.innerHeight / 2 + Math.sin(ang) * root.innerHeight * 0.35 };
    }
    return ui.ptr;
  }
  function frame() {
    if (!ui) return;
    const t = nowMs();
    ui.halves.forEach((h, i) => {
      const r = h.el.getBoundingClientRect();
      const cx = r.left + h.fx / 120 * r.width, cy = r.top + h.fy / 120 * r.height;
      const g = target(h, i, t), dx = g.x - cx, dy = g.y - cy, d = Math.hypot(dx, dy) || 1, k = Math.min(d / 180, 1);
      h.pupils.setAttribute('transform', `translate(${(dx / d * k * 4.2).toFixed(2)} ${(dy / d * k * 3.6).toFixed(2)})`);
      let lean = clamp(dx / 260, -1, 1) * 8, extra = 0, hop = 0;
      const nx = clamp(dx / 300, -1, 1) * 3, ny = clamp(dy / 300, -1, 1) * 2;
      const bob = ui.reduce ? 0 : Math.sin(t / 700 + i * 1.3) * 1.6;
      if (h.hop > t) hop = -Math.sin((1 - (h.hop - t) / 460) * Math.PI) * 16;
      if (h.shake > t) extra += Math.sin(t / 22) * 5;
      if (h.spin > t) { const p = 1 - (h.spin - t) / 720; extra += (1 - Math.pow(1 - p, 3)) * 360 - 360; }
      h.el.style.transformOrigin = (!ui.panel.hidden || h.spin > t) ? `${h.fx / 1.2}% ${h.fy / 1.2}%` : '50% 50%';
      if (ui.reduce) { lean *= 0.3; hop = 0; extra = 0; }
      h.el.style.transform = `translate(${nx.toFixed(1)}px, ${(ny + bob + hop).toFixed(1)}px) rotate(${(lean + extra).toFixed(1)}deg)`;
    });
    root.requestAnimationFrame(frame);
  }

  async function explainNode(context) {
    const A = academy(); if (!A) return null;
    const ix = await index();
    const co = ((ix && ix.companies) || []).find(c => +c.cik === +(context && context.cik)) || null;
    const answer = A.explain(co, zhUI() ? 'zh' : 'en', context || {});
    if (!ui) return answer;
    open();
    const msg = addMsg(answer.html + (answer.links && answer.links.length ?
      '<div class="flo-links">' + answer.links.map(([u,l]) => link(u,l)).join('') + '</div>' : ''), 'bot');
    if (answer.actions && answer.actions.length) {
      const actions = doc.createElement('div'); actions.className = 'flo-actions';
      answer.actions.forEach(a => {const b = doc.createElement('button'); b.type='button'; b.className='flo-action'; b.textContent=a.label;
        b.addEventListener('click',()=>send(a.question)); actions.appendChild(b);});
      msg.appendChild(actions);
    }
    mood('talk',1800);
    return answer;
  }
  function open() {
    if (!ui) return;
    ui.panel.hidden = false; ui.launch.hidden = true;
    if (!ui.log.childElementCount) {
      const g = greetFor(ui.ctx, zhUI());
      addMsg(g || helpAnswer(zhUI() ? 'zh' : 'en', ui.co).html, 'bot'); ui.greeted = ui.ctx && ui.ctx.key;
    }
    renderChips();
    layout();
    mood('wave', 1600);
    setTimeout(() => ui.input.focus({ preventScroll: true }), 350);
    store.set('seen', '1');
  }
  function close() {
    if (!ui) return;
    ui.panel.hidden = true; ui.launch.hidden = false;
    layout();
    const t = nowMs();
    ui.halves[1].spin = t + 720; ui.halves[0].hop = t + 460;        // they fly home and lock with a half-turn
    mood('idle');
  }
  function mount() {
    if (!doc || !doc.body || doc.getElementById('flo-root')) return;
    const st = doc.createElement('style'); st.id = 'flo-css'; st.textContent = CSS; doc.head.appendChild(st);
    const r = doc.createElement('div'); r.id = 'flo-root';
    r.innerHTML = `<div class="flo-launch"><div class="flo-hint"${store.get('seen') ? ' hidden' : ''}>${zhUI() ? '你好！问我任何公司的问题' : 'Hi! Ask me about any company'} <button type="button" aria-label="Dismiss">×</button></div><button type="button" class="flo-btn" aria-label="Ask Flo, the site's assistant"></button></div>
      <section class="flo-panel" role="dialog" aria-label="Ask Flo" hidden><div class="flo-head"><div><b>Flo</b><small>${zhUI() ? '用网站自己的模型回答：估值、RRG、期权、财报、信用。按固定规则生成，不是投资建议。' : "Answers from the site's models: valuation, RRG, options, earnings, credit. Written by fixed rules; not investment advice."}</small></div><button type="button" class="flo-x" aria-label="Close">×</button></div>
      <div class="flo-log" aria-live="polite"></div><div class="flo-chips"></div>
      <form class="flo-form"><input type="text" placeholder="${zhUI() ? '问一家公司…' : 'Ask about a company…'}" aria-label="Your question" maxlength="300"><button type="submit">${zhUI() ? '问' : 'Ask'}</button></form></section>
      <div class="flo-half flo-h1" aria-hidden="true">${HALF1}</div><div class="flo-half flo-h2" aria-hidden="true">${HALF2}</div>`;
    doc.body.appendChild(r);
    const mk = (sel, fx, fy) => { const el = r.querySelector(sel); return { el, fx, fy, pupils: el.querySelector('.flo-pupils'), hop: 0, shake: 0, spin: 0, look: null }; };
    ui = { launch: r.querySelector('.flo-launch'), btn: r.querySelector('.flo-btn'), panel: r.querySelector('.flo-panel'), log: r.querySelector('.flo-log'), chips: r.querySelector('.flo-chips'),
      input: r.querySelector('.flo-form input'), co: null, halves: [mk('.flo-h1', 27, 34), mk('.flo-h2', 93, 86)], mood: 'idle', hover: false,
      ptr: { x: root.innerWidth / 2, y: root.innerHeight / 2, t: nowMs() }, typingUntil: 0,
      reduce: !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches) };
    mood('idle');
    ui.btn.addEventListener('click', open);
    ui.halves.forEach((h, i) => {
      h.el.addEventListener('pointerenter', () => { if (ui.panel.hidden) { ui.hover = true; layout(); } });
      h.el.addEventListener('pointerleave', () => { ui.hover = false; if (ui.panel.hidden) layout(); });
      h.el.addEventListener('click', () => {
        if (ui.panel.hidden) return open();
        const t = nowMs(), other = ui.halves[1 - i], b = h.el.getBoundingClientRect();
        h.hop = t + 460; h.spin = t + 720;                // the clicked half hops and spins, the other one looks at it
        other.look = { x: b.left + b.width / 2, y: b.top + b.height / 2, until: t + 1400 };
        h.el.dataset.mood = 'happy'; setTimeout(() => { h.el.dataset.mood = ui.mood; }, 900);
      });
    });
    // blinking, each half on its own clock
    ui.halves.forEach((h) => {
      const blink = () => { h.el.classList.add('flo-blink'); setTimeout(() => h.el.classList.remove('flo-blink'), 120); setTimeout(blink, 2200 + Math.random() * 3200); };
      setTimeout(blink, 800 + Math.random() * 2000);
    });
    root.addEventListener('pointermove', (e) => { ui.ptr = { x: e.clientX, y: e.clientY, t: nowMs() }; }, { passive: true });
    root.addEventListener('resize', layout);
    ui.input.addEventListener('input', () => { const t = nowMs(); ui.typingUntil = t + 1500; ui.halves[1].hop = t + 260; });
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
      ui.ctx = ctx; ui.co = ctx.co || null; ui.seed = 0;
      renderChips();
      if (!ui.panel.hidden && ui.log.childElementCount && ui.greeted !== ctx.key) { const g = greetFor(ctx, zhUI()); if (g) { addMsg(g, 'bot'); ui.greeted = ctx.key; } }
    };
    root.addEventListener('hashchange', sync); sync();
    layout();
    root.requestAnimationFrame(frame);
    setTimeout(() => mood('wave', 1800), 1200);
  }
  root.FFMascot = { open, ask, explain: explainNode, mount, classify, findCompany, lang, pageContext, chipsFor };
  if (doc && doc.body !== undefined) { if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', mount); else mount(); }
  if (typeof module !== 'undefined') module.exports = { classify, findCompany, lang, ask, helpAnswer, pageContext, chipsFor, greetFor };
})(typeof globalThis !== 'undefined' ? globalThis : this);
