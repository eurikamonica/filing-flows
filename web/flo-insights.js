/* Flo's research answers beyond the models (web/mascot.js asks this file first for what it covers):

   about one company — every answer from the site's own published files, with the page it came from:
     owners        who owns it: the largest 13F holders and last quarter's fund buying (disclosures/data/holders/<T>.json)
     insiders      its officers' and directors' open-market buys and sells (market/insiders.json), planned sales (Form 144)
     congress      members of Congress' and officials' trades in it (holders/<T>.json officials)
     events        its latest material 8-Ks: deals, agreements, debt, leadership, delisting (market/events8k.json)
     cashflow      free cash flow, where the cash went (data/c/<cik>.json quality.cap)
     segments      how it makes money: the lines that make up revenue, their share and growth (the latest quarter)
     nextEarnings  the next report: date, what analysts expect, how often it beats, the implied move (research/earnings)
     ties          the customers and suppliers named in filings (data/network/c/<cik>.json)
     shorts        short interest: shares short, change, days to cover (holders/<T>.json short)
     moves         how rare the latest move is in its own history and what followed days like it (research/paths/moves)
     guidanceRecord  how often it meets the guidance it gives (market/guidance-board.json)
     investments   gains on the stakes it holds in other companies (research/investors/index.json)
   about the market — when no company is named: who reports this week, the biggest insider buys, Congress' most traded,
   the funds' biggest net buys, the most unusual moves, new activist stakes, the latest deals, the most shorted, the
   guidance raised and lowered, the largest investment gains.

   Also: follow-ups ("what about AMD?", "AMD 呢？" ask the last question again for another company), a misspelt name
   found by its closest company ("nvidea", "microsft"), and next questions under every answer.
   No language model: sentences written by fixed rules from the published figures. Not investment advice. */
(function (root) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, 1) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : a >= 1e3 ? '$' + num(a / 1e3, 0) + 'K' : '$' + num(a, 0)); };
  const pc = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spc = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const L = (lg, en, zh) => (lg === 'zh' ? zh : en);
  const fileT = (t) => String(t || '').toUpperCase().replace(/\./g, '-');
  const day = (s) => String(s || '').slice(0, 10);
  const ago = (d, n) => { const t = Date.parse(day(d) + 'T00:00:00Z'); return Number.isFinite(t) && Date.now() - t <= n * 864e5; };

  /* ---------- the questions it covers ---------- */
  const INTENTS = [
    ['owners', /who owns|\bholders?\b|institution(al)?s?\b|\b13-?f\b|hedge funds?|(funds?|managers?) (own|hold|buy|bought|sell|sold|adding|cutting)|biggest (holder|owner|shareholder)|top shareholders?|谁持有|持股|机构持仓|机构|基金(经理)?(买|卖|持有|增持|减持)?|大股东|股东/i],
    ['insiders', /insiders?|form ?4\b|(ceo|cfo|executives?|directors?|management|officers?) (bought|sold|buy|sell|buying|selling)|10b5-?1|form ?144|内部人|高管(买|卖|增持|减持)|董事(买|卖)|增持|减持|管理层(买|卖)/i],
    ['congress', /congress|senators?|representatives?|politicians?|lawmakers?|pelosi|officials?'?\s*trad|国会|议员|政客|佩洛西|官员交易/i],
    ['events', /\b8-?ks?\b|\bdeals?\b|material (events?|agreements?)|announce|acquisitions?|acquire|mergers?|buyouts?|takeover|(ceo|cfo) (left|leaves|resign|depart|change)|resign|impairment|restat|bankruptcy|delist|重大事件|公告|收购|并购|合并|辞职|离职|换帅|减值|重述|退市|破产/i],
    ['cashflow', /free cash ?flow|\bfcf\b|cash burn|burn(ing)? cash|capex|capital (spending|expenditure)|buy ?backs?|repurchase|dividends?|where (does|did) (its |the )?cash go|自由现金流|资本支出|回购|分红|股息|烧钱|现金去哪/i],
    ['segments', /makes? (its )?money|revenue (mix|breakdown|by segment|sources?)|segments?|business (lines?|units?)|product lines?|where (does|do) (its|the) revenue come|收入构成|收入来源|业务构成|怎么赚钱|靠什么赚钱|分部|各业务/i],
    ['nextEarnings', /when (does|do|will|is) .{0,30}(report|earnings)|who (reports|is reporting)|report(s|ing)? (earnings )?(this|next) week|earnings (calendar|this week|next week|season)|earnings (date|day|preview)|next (earnings|report|quarter'?s? results)|report date|what to expect|eps estimate|consensus eps|(will|can) .{0,20}beat|beat rate|什么时候(发|公布|出)?财报|发财报|公布财报|财报季|财报日历|财报(日期|日|时间|预期|预览)|下次财报|下一次财报|业绩预期|会超预期|超预期吗|预期每股/i],
    ['ties', /customers?|suppliers?|supply chain|who (buys|sells) (from|to)|clients?|vendors?|depend(s|ent)? on|biggest buyer|客户|供应商|供应链|卖给谁|买谁的|依赖/i],
    ['shorts', /short interest|short squeeze|(most|heavily) shorted|shorted|days to cover|short sellers?|空头|卖空|做空比例|做空仓位|轧空|空头回补/i],
    ['moves', /how (rare|unusual)|unusual moves?|biggest movers?|top movers?|movers|moves? today|today'?s (move|drop|fall|gain|jump)|why (is|did|was) .{0,25}(down|up|drop|fall|fell|jump|rise|rose|move|moving)|move odds|(dropped|fell|jumped|soared|plunged|crashed) (today|yesterday)|今天(为什么)?(涨|跌|大涨|大跌)|为什么(涨|跌)|跌了多少|涨了多少|异动|罕见|暴跌|暴涨/i],
    ['guidanceRecord', /guidance (track record|record|history|reliab|accura|changes?|raises?|cuts?)|(raised|lowered|raises|lowers|cut|cuts|withdrew|withdrawn|reaffirmed) (its |their )?guidance|上调(了)?指引|下调(了)?指引|指引(上调|下调|变化)|(meet|meets|met|hit|hits|beat|beats|miss|misses) (its |their )?(own )?guidance|sandbag|guidance credib|指引(兑现|可信|记录|历史|准确)|兑现率|说到做到/i],
    ['investments', /investment gains?|gains? on (its )?investments?|stakes? in (other )?companies|equity investments?|venture (bets|stakes)|what (did|does) .{0,20}invest in|投资收益|投资了哪些|持有哪些公司|股权投资|投了谁/i],
  ];
  // words that ask about the market rather than one company ("who reports this week", "biggest insider buys")
  const MARKET = /this week|next week|today|lately|recent(ly)?|latest|biggest|largest|most|top \d*|which (stocks|companies)|what (stocks|companies)|any (stocks|companies)|list|ranking|leaderboard|across the market|in the market|本周|这周|下周|今天|最近|最新|最大|最多|哪些|哪几|排行|榜|全市场|有哪/i;
  const PRONOUN = /\b(it|its|this (company|stock)|they|their|the company)\b|这家|它|该公司|这只/i;
  function classify(q) {
    const s = String(q || ''), out = [];
    for (const [k, rx] of INTENTS) if (rx.test(s)) out.push(k);
    return out;
  }
  // the model intents (mascot.js) a more specific one here replaces: "earnings date" is not the last quarter's earnings
  const REPLACES = { nextEarnings: ['earnings', 'calls'], cashflow: ['earnings'], segments: ['earnings'], guidanceRecord: ['calls'], shorts: ['opportunity'],
    moves: ['rotation'], investments: ['valuation'], ties: ['industry'], insiders: ['earnings'] };
  function merge(base, mine) {
    const drop = new Set(mine.flatMap((k) => REPLACES[k] || []));
    return [...new Set([...mine, ...base.filter((k) => !drop.has(k) && !mine.includes(k))])];
  }
  const STRONG = /biggest|largest|\bmost\b|\btop\b|which (stocks|companies)|what (stocks|companies)|ranking|leaderboard|across the market|in the market|哪些|哪几|最多|最大|排行|榜|全市场/i;
  // a market question: no company named, market words, no "its"; on a company's page only the strong words count
  const isMarket = (q, named, onPage) => !named && !PRONOUN.test(String(q || '')) && (!onPage || STRONG.test(String(q || '')));
  // "what about AMD?", "and Apple?", "AMD 呢？", "那苹果呢" — the last question, for another company
  const FOLLOW = /^\s*(what about|how about|and( for)?|same (for|with)|now|then|也看看|那|再看看?|换成)\b|呢\s*[?？]?\s*$|^\s*[$A-Za-z.\-]{1,8}\s*[?？]\s*$/i;
  const isFollow = (q) => FOLLOW.test(String(q || '')) && String(q || '').length <= 40;

  /* ---------- a misspelt name: the closest company by its first word ---------- */
  // edit distance counting a swap of two neighbours as one edit ("appel" → "apple")
  function lev(a, b) {
    if (Math.abs(a.length - b.length) > 2) return 9;
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
    return d[a.length][b.length];
  }
  const GENERIC = new Set(['corp', 'group', 'holdings', 'company', 'global', 'international', 'american', 'first', 'united', 'general', 'national', 'financial',
    'technologies', 'technology', 'systems', 'energy', 'capital', 'bancorp', 'industries', 'partners', 'trust', 'brands', 'therapeutics', 'pharmaceuticals']);
  const COMMON = new Set(['about', 'after', 'again', 'their', 'there', 'these', 'which', 'would', 'could', 'should', 'price', 'stock', 'stocks', 'shares', 'today', 'worth',
    'value', 'money', 'quarter', 'report', 'earnings', 'revenue', 'profit', 'margin', 'owns', 'holders', 'buying', 'selling', 'insider', 'insiders', 'short', 'growth',
    'market', 'filing', 'filings', 'options', 'interest', 'shorted', 'trading', 'traded', 'latest', 'biggest', 'largest', 'unusual', 'activist', 'stakes', 'deals', 'guidance', 'customers', 'suppliers', 'segments', 'congress', 'industry', 'sector', 'compare', 'versus', 'debt', 'credit']);
  // what people call a company when its filing name differs ("Google" files as Alphabet, "Disney" as Walt Disney)
  const ALIAS = { google: 'GOOGL', youtube: 'GOOGL', alphabet: 'GOOGL', facebook: 'META', instagram: 'META', whatsapp: 'META', disney: 'DIS', coke: 'KO', cocacola: 'KO',
    pepsi: 'PEP', pepsico: 'PEP', 'home depot': 'HD', homedepot: 'HD', walmart: 'WMT', chase: 'JPM', jpmorgan: 'JPM', berkshire: 'BRK-B', buffett: 'BRK-B',
    goldman: 'GS', 'morgan stanley': 'MS', 'bank of america': 'BAC', 'wells fargo': 'WFC', 'johnson & johnson': 'JNJ', 'j&j': 'JNJ', exxon: 'XOM', chevron: 'CVX',
    mcdonalds: 'MCD', "mcdonald's": 'MCD', starbucks: 'SBUX', 'at&t': 'T', verizon: 'VZ', tsmc: 'TSM', 'taiwan semi': 'TSM', costco: 'COST', salesforce: 'CRM',
    netflix: 'NFLX', tesla: 'TSLA', nvidia: 'NVDA', microsoft: 'MSFT', apple: 'AAPL', amazon: 'AMZN', 'eli lilly': 'LLY', lilly: 'LLY', 'novo nordisk': 'NVO',
    palantir: 'PLTR', broadcom: 'AVGO', oracle: 'ORCL', intel: 'INTC', adobe: 'ADBE', uber: 'UBER', airbnb: 'ABNB', paypal: 'PYPL', shopify: 'SHOP', spotify: 'SPOT' };
  function fuzzyCompany(q, ix, stop) {
    const list = (ix && ix.companies) || [];
    const byT = new Map(list.map((c) => [String(c.ticker || '').toUpperCase(), c]));
    const low = String(q || '').toLowerCase();
    for (const [k, tk] of Object.entries(ALIAS)) if (k.includes(' ') || /[&']/.test(k) ? low.includes(k) : new RegExp('\\b' + k + 's?\\b').test(low)) { if (byT.has(tk)) return byT.get(tk); }
    for (const w of low.match(/[a-z]{5,}/g) || []) for (const [k, tk] of Object.entries(ALIAS)) if (k.length >= 5 && !/[ &']/.test(k) && lev(w, k) === 1 && byT.has(tk)) return byT.get(tk);
    const words = (String(q || '').toLowerCase().match(/[a-z]{5,}/g) || []).filter((w) => !COMMON.has(w) && !(stop && (stop.has(w) || stop.has(w.replace(/s$/, '')))));
    if (!words.length || !list.length) return null;
    let best = null;
    for (const c of list) {
      const f = (String(c.name || '').toLowerCase().match(/[a-z]{4,}/) || [])[0];
      if (!f || GENERIC.has(f) || f.length < 5) continue;
      for (const w of words) {
        const d = lev(w, f);
        if (d <= (f.length >= 8 ? 2 : 1) && (!best || d < best.d || (d === best.d && (c.revenue || 0) > (best.c.revenue || 0)))) best = { c, d };
      }
    }
    return best ? best.c : null;
  }

  /* ---------- the answers: {html, facts[], mood, links[[href, text]]} ---------- */
  function make(env) {
    const { json, BASE, HUB, DATA } = env;
    const lk = (h, t) => [h, t];
    const holders = (c) => json(HUB + 'holders/' + encodeURIComponent(fileT(c.ticker)) + '.json');

    async function owners(c, lg) {
      const h = await holders(c);
      if (!h || !(h.institutional || []).length) return null;
      const inst = h.institutional.slice().sort((a, b) => (b.value_usd || 0) - (a.value_usd || 0)).slice(0, 5);
      const ST = { INCREASE: ['added', '增持'], DECREASE: ['cut', '减持'], NEW: ['new', '新建仓'], UNCHANGED: ['held', '持平'], SOLD_OUT: ['sold out', '清仓'] };
      const st = (x) => (ST[x.status] || ['', ''])[lg === 'zh' ? 1 : 0];
      const f = h.flows || {};
      const top = inst.map((x) => `${esc(x.manager)} ${big(x.value_usd)}${st(x) ? L(lg, ` (${st(x)})`, `（${st(x)}）`) : ''}`).join(lg === 'zh' ? '；' : '; ');
      const p = [L(lg, `<b>${esc(c.ticker)}</b>'s largest 13F holders: ${top}.`, `<b>${esc(c.ticker)}</b> 最大的 13F 持有人：${top}。`)];
      if (fin(f.buyers)) p.push(L(lg, `${esc(String(f.label || 'Last quarter').split(' —')[0])}: <b>${num(f.buyers)}</b> managers bought and <b>${num(f.sellers)}</b> sold, net <b>${big(f.usd_net)}</b>; ${num(f.new)} new positions, ${num(f.exits)} exits, ${num(f.holders)} holders in all.`,
        `${esc(String(f.label || '上季').split(' —')[0])}：<b>${num(f.buyers)}</b> 家机构买入、<b>${num(f.sellers)}</b> 家卖出，净额 <b>${big(f.usd_net)}</b>；新建仓 ${num(f.new)} 家、清仓 ${num(f.exits)} 家，共 ${num(f.holders)} 家持有。`));
      const facts = [`largest 13F holders: ${inst.map((x) => `${x.manager} ${big(x.value_usd)} (${x.period})`).join('; ')}`,
        fin(f.buyers) ? `${f.label}: ${f.buyers} buyers, ${f.sellers} sellers, net ${big(f.usd_net)}, ${f.new} new, ${f.exits} exits` : ''].filter(Boolean);
      return { html: p.join(' '), facts, mood: fin(f.usd_net) && f.usd_net > 0 ? 'happy' : 'talk', links: [lk(`${BASE}#c-${c.cik}-holders`, L(lg, '13F funds & officials', '13F 机构与官员持仓'))] };
    }

    async function insiders(c, lg) {
      const [d, h] = await Promise.all([json(HUB + 'market/insiders.json'), holders(c)]);
      const T = fileT(c.ticker);
      const s = ((d && d.summary) || []).find((x) => fileT(x.ticker) === T || String(x.cik) === String(c.cik));
      const lt = ((d && d.latest) || []).filter((x) => fileT(x.ticker) === T || String(x.issuer_cik) === String(c.cik)).slice(0, 4);
      const f144 = ((h && h.form144) || []).filter((x) => ago(x.filed, 120)).slice(0, 3);
      if (!s && !lt.length && !f144.length) return { html: L(lg, `No open-market insider buys or sells of <b>${esc(c.ticker)}</b> since ${esc((d && d.since) || 'the start of the record')} (Form 4, codes P and S); grants and option exercises are left out.`, `自 ${esc((d && d.since) || '记录开始')} 以来，<b>${esc(c.ticker)}</b> 没有内部人公开市场买卖（Form 4，代码 P 和 S）；授予与行权不计。`), facts: [], mood: 'talk', links: [lk(`${BASE}#c-${c.cik}-x-insiders`, 'Insiders')] };
      const p = [];
      if (!s && !lt.length) p.push(L(lg, `No open-market buys or sells by <b>${esc(c.ticker)}</b> insiders since ${esc((d && d.since) || 'the start of the record')} (Form 4, codes P and S).`, `自 ${esc((d && d.since) || '记录开始')} 以来，<b>${esc(c.ticker)}</b> 内部人没有公开市场买卖（Form 4，代码 P 和 S）。`));
      if (s) p.push(L(lg, `Since ${esc(d.since)}, <b>${esc(c.ticker)}</b> insiders bought <b>${big(s.buy_value)}</b> (${num(s.buys)} trades) and sold <b>${big(s.sell_value)}</b> (${num(s.sells)})${s.cluster || (s.buyers30 || 0) >= 3 ? '; <b>several insiders bought within 30 days</b>, the pattern studies find most telling' : ''}${s.ceo_cfo_sell ? '; the CEO or CFO sold' : ''}${s.plan_sells ? `; ${num(s.plan_sells)} sales were pre-planned (10b5-1)` : ''}.`,
        `自 ${esc(d.since)} 起，<b>${esc(c.ticker)}</b> 内部人买入 <b>${big(s.buy_value)}</b>（${num(s.buys)} 笔），卖出 <b>${big(s.sell_value)}</b>（${num(s.sells)} 笔）${s.cluster || (s.buyers30 || 0) >= 3 ? '；<b>30 天内多位内部人同时买入</b>，研究认为这种信号最有参考价值' : ''}${s.ceo_cfo_sell ? '；CEO 或 CFO 有卖出' : ''}${s.plan_sells ? `；其中 ${num(s.plan_sells)} 笔卖出是预先计划的（10b5-1）` : ''}。`));
      if (lt.length) p.push(L(lg, 'Latest: ', '最近：') + lt.map((x) => `${esc(x.insider)} (${esc(x.title || x.role || '')}) ${x.code === 'P' ? L(lg, 'bought', '买入') : L(lg, 'sold', '卖出')} ${big(x.value)} ${L(lg, 'on', '于')} ${esc(day(x.date))}`).join(lg === 'zh' ? '；' : '; ') + '.');
      if (f144.length) p.push(L(lg, 'Planned sales (Form 144): ', '拟出售通知（Form 144）：') + f144.map((x) => `${esc(x.seller_name || x.seller)} ${big(x.value)} (${esc(day(x.filed))})`).join(lg === 'zh' ? '；' : '; ') + '.');
      const facts = [s ? `insiders since ${d.since}: bought ${big(s.buy_value)} in ${s.buys} trades, sold ${big(s.sell_value)} in ${s.sells}` : '',
        ...lt.map((x) => `${x.insider} ${x.code === 'P' ? 'bought' : 'sold'} ${big(x.value)} on ${day(x.date)}`)].filter(Boolean);
      return { html: p.join(' '), facts, mood: s && s.buy_value > s.sell_value ? 'happy' : 'talk', links: [lk(`${BASE}#c-${c.cik}-x-insiders`, L(lg, 'Insiders (Form 4, 10b5-1)', '内部人交易'))] };
    }

    async function congress(c, lg) {
      const h = await holders(c);
      const rows = ((h && h.officials) || []).filter((x) => x.kind === 'transaction' || x.transaction_type).sort((a, b) => day(b.date).localeCompare(day(a.date)));
      if (!rows.length) return { html: L(lg, `No trades in <b>${esc(c.ticker)}</b> disclosed by members of Congress or other officials on file.`, `记录中没有国会议员或其他官员披露过 <b>${esc(c.ticker)}</b> 的交易。`), facts: [], mood: 'talk', links: [] };
      const r90 = rows.filter((x) => ago(x.date, 90)), buy = (x) => /purchase|buy/i.test(x.transaction_type || '');
      const nb = r90.filter(buy).length, ns = r90.length - nb;
      const amt = (x) => `${big(x.amount_min)}–${big(x.amount_max)}`;
      const p = [L(lg, `In the last 90 days officials disclosed <b>${nb}</b> buy${nb === 1 ? '' : 's'} and <b>${ns}</b> sale${ns === 1 ? '' : 's'} of <b>${esc(c.ticker)}</b>.`, `过去 90 天，官员披露了 <b>${nb}</b> 笔买入和 <b>${ns}</b> 笔卖出 <b>${esc(c.ticker)}</b>。`),
        L(lg, 'Latest: ', '最近：') + rows.slice(0, 4).map((x) => `${esc(x.person)} ${buy(x) ? L(lg, 'bought', '买入') : L(lg, 'sold', '卖出')} ${amt(x)} ${L(lg, 'on', '于')} ${esc(day(x.date))}${x.filed_date ? L(lg, ` (reported ${esc(day(x.filed_date))})`, `（${esc(day(x.filed_date))} 申报）`) : ''}`).join(lg === 'zh' ? '；' : '; ') + '.',
        L(lg, 'Amounts are disclosed in ranges only, up to 45 days after the trade.', '金额只按区间披露，最长可在交易后 45 天才申报。')];
      return { html: p.join(' '), facts: rows.slice(0, 6).map((x) => `${x.person} ${x.transaction_type} ${amt(x)} on ${day(x.date)}`), mood: 'talk', links: [lk(`${BASE}#c-${c.cik}-holders`, L(lg, 'Officials\' trades', '官员交易'))] };
    }

    const ITEM = { '1.01': ['material agreement', '重大协议'], '1.02': ['agreement ended', '协议终止'], '1.03': ['bankruptcy', '破产'], '1.05': ['cyber incident', '网络安全事件'],
      '2.01': ['acquisition or sale completed', '完成收购或出售'], '2.02': ['results', '业绩'], '2.03': ['new debt', '新增债务'], '2.05': ['restructuring', '重组'], '2.06': ['impairment', '减值'],
      '3.01': ['delisting notice', '退市通知'], '3.02': ['unregistered share sale', '未注册股票发行'], '4.01': ['auditor change', '更换审计师'], '4.02': ['restatement', '财报重述'],
      '5.01': ['change in control', '控制权变更'], '5.02': ['leadership change', '高管或董事变动'], '5.07': ['shareholder vote', '股东投票'], '7.01': ['Reg FD', 'Reg FD 披露'], '8.01': ['other event', '其他事项'] };
    async function events(c, lg) {
      const d = await json(HUB + 'market/events8k.json');
      const rows = ((d && d.rows) || []).filter((x) => String(x.cik) === String(c.cik)).sort((a, b) => String(b.filed).localeCompare(String(a.filed))).slice(0, 4);
      if (!rows.length) return { html: L(lg, `No 8-K from <b>${esc(c.ticker)}</b> in the last ${num((d && d.days) || 30)} days.`, `<b>${esc(c.ticker)}</b> 最近 ${num((d && d.days) || 30)} 天没有 8-K。`), facts: [], mood: 'talk', links: [lk(`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${c.cik}&type=8-K`, 'SEC: 8-K')] };
      const what = (x) => (x.items || []).filter((i) => i !== '9.01').map((i) => (ITEM[i] || [i, i])[lg === 'zh' ? 1 : 0]).join(', ');
      const p = [L(lg, `<b>${esc(c.ticker)}</b>'s latest 8-Ks:`, `<b>${esc(c.ticker)}</b> 最近的 8-K：`),
        '<ul class="flo-list">' + rows.map((x) => `<li><b>${esc(day(x.filed))}</b> · ${esc(what(x))}${x.headline ? ' — ' + esc(String(x.headline).slice(0, 140)) : x.quote ? ' — “' + esc(String(x.quote).slice(0, 140)) + '…”' : ''} <a href="${esc(x.url)}" target="_blank" rel="noopener">SEC</a></li>`).join('') + '</ul>'];
      return { html: p.join(' '), facts: rows.map((x) => `8-K ${day(x.filed)} items ${(x.items || []).join(',')}: ${x.headline || String(x.quote || '').slice(0, 160)}`), mood: rows.some((x) => /1\.03|4\.02|3\.01|2\.06/.test((x.items || []).join(' '))) ? 'worried' : 'talk',
        links: [lk(`${BASE}#c-${c.cik}-x-events`, L(lg, '8-Ks and news', '8-K 与新闻'))] };
    }

    const CASH = { capex: ['capital spending', '资本支出'], acq: ['acquisitions', '收购'], buyback: ['buybacks', '回购'], div: ['dividends', '分红'], borrow: ['net borrowing', '净借款'],
      stock: ['shares issued', '发行股票'], realestate: ['real estate', '房地产'], withhold: ['taxes on employees\' shares', '员工股票代扣税'], inv_other: ['other investing', '其他投资'], sales: ['asset sales', '资产出售'] };
    async function cashflow(c, lg) {
      const d = await json(DATA + 'c/' + c.cik + '.json');
      const cap = ((d && d.quality) || {}).cap || {};
      const qs = (cap.q || []).filter((x) => x.items && fin(x.items.ocf));
      if (!qs.length) return null;
      const q = qs[qs.length - 1], it = q.items, fcf = it.ocf + (it.capex || 0), t = cap.ttm, ti = (t && t.items) || {};
      const tf = fin(ti.ocf) ? ti.ocf + (ti.capex || 0) : null;
      const ya = qs.find((x) => x.end && q.end && x.end.slice(5) === q.end.slice(5) && +x.end.slice(0, 4) === +q.end.slice(0, 4) - 1);
      const yf = ya ? ya.items.ocf + (ya.items.capex || 0) : null;
      const uses = Object.entries(ti).filter(([k, v]) => CASH[k] && v < 0).sort((a, b) => a[1] - b[1]).slice(0, 3);
      const p = [L(lg, `In <b>${esc(q.label)}</b> <b>${esc(c.ticker)}</b> generated ${big(it.ocf)} from operations and spent ${big(-(it.capex || 0))} on capital projects: free cash flow <b>${big(fcf)}</b>${fin(yf) ? ` (${big(yf)} a year earlier)` : ''}.`,
        `<b>${esc(c.ticker)}</b> 在 <b>${esc(q.label)}</b> 经营现金流 ${big(it.ocf)}，资本支出 ${big(-(it.capex || 0))}：自由现金流 <b>${big(fcf)}</b>${fin(yf) ? `（去年同期 ${big(yf)}）` : ''}。`)];
      if (fin(tf)) p.push(L(lg, `Over twelve months: free cash flow ${big(tf)}${uses.length ? '; the largest uses of cash were ' + uses.map(([k, v]) => `${CASH[k][0]} ${big(-v)}`).join(', ') : ''}.`,
        `过去十二个月自由现金流 ${big(tf)}${uses.length ? '；现金主要用于' + uses.map(([k, v]) => `${CASH[k][1]} ${big(-v)}`).join('、') : ''}。`));
      return { html: p.join(' '), facts: [`${q.label}: operating cash flow ${big(it.ocf)}, capex ${big(it.capex)}, free cash flow ${big(fcf)}`, fin(tf) ? `${t.label}: free cash flow ${big(tf)}` : ''].filter(Boolean),
        mood: fcf < 0 ? 'worried' : 'talk', links: [lk(`${BASE}#c-${c.cik}-capital`, L(lg, 'Capital allocation', '资本配置'))] };
    }

    async function segments(c, lg) {
      const d = await json(DATA + 'c/' + c.cik + '.json');
      const q = ((d && d.quarters) || [])[0];
      if (!q || !q.nodes) return null;
      const N = new Map(q.nodes.map((n) => [n.id, n])), rev = N.get('revenue');
      const lines = (q.links || []).filter((l) => l.t === 'revenue' && N.get(l.s)).map((l) => N.get(l.s)).filter((n) => fin(n.v)).sort((a, b) => b.v - a.v);
      const tot = (rev && rev.v) || lines.reduce((s, n) => s + n.v, 0);
      if (lines.length < 2) return { html: L(lg, `<b>${esc(c.ticker)}</b> reports its revenue as one line in ${esc(q.label)} (${big(tot)}); it does not tag segments in its filing.`, `<b>${esc(c.ticker)}</b> 在 ${esc(q.label)} 只把营收报为一项（${big(tot)}），申报中没有按业务分部标注。`), facts: [], mood: 'talk', links: [lk(`${BASE}#c-${c.cik}`, 'Sankey')] };
      const g = (n) => (fin(n.y) && n.y > 0 ? spc(n.v / n.y - 1, 0) : null);
      const fast = lines.filter((n) => fin(n.y) && n.y > 0 && n.v > 0.05 * tot).sort((a, b) => b.v / b.y - a.v / a.y)[0];
      const p = [L(lg, `<b>${esc(c.ticker)}</b> made <b>${big(tot)}</b> in ${esc(q.label)}:`, `<b>${esc(c.ticker)}</b> 在 ${esc(q.label)} 收入 <b>${big(tot)}</b>：`),
        '<ul class="flo-list">' + lines.slice(0, 6).map((n) => `<li><b>${esc(n.name)}</b> ${big(n.v)} · ${n.v / tot < 0.01 ? '<1%' : pc(n.v / tot, 0)}${g(n) ? ` · ${L(lg, 'Y/Y', '同比')} ${g(n)}` : ''}</li>`).join('') + '</ul>'];
      if (fast) p.push(L(lg, `Fastest-growing large line: <b>${esc(fast.name)}</b> (${g(fast)}).`, `增长最快的主要业务：<b>${esc(fast.name)}</b>（${g(fast)}）。`));
      return { html: p.join(' '), facts: lines.slice(0, 6).map((n) => `${n.name} ${big(n.v)} (${pc(n.v / tot, 0)} of revenue${g(n) ? ', ' + g(n) + ' y/y' : ''})`), mood: 'talk',
        links: [lk(`${BASE}#c-${c.cik}`, L(lg, 'The revenue Sankey', '收入桑基图'))] };
    }

    async function nextEarnings(c, lg) {
      const e = await json(HUB + 'research/earnings/c/' + encodeURIComponent(fileT(c.ticker)) + '.json');
      if (!e || !e.report_date) return null;
      const cs = e.consensus || {}, h = (e.history || []).filter((x) => fin(x.act) && fin(x.est)), last = h[h.length - 1];
      const days = Math.round((Date.parse(e.report_date + 'T00:00:00Z') - Date.parse(new Date().toISOString().slice(0, 10) + 'T00:00:00Z')) / 864e5);
      const p = [];
      if (last && ago(last.reported, 10)) p.push(L(lg, `<b>${esc(c.ticker)}</b> reported on ${esc(last.reported)}: EPS <b>$${num(last.act, 2)}</b> against $${num(last.est, 2)} expected (${spc(last.surprise)})${fin(last.move) ? `, and the stock moved ${spc(last.move)}` : ''}.`,
        `<b>${esc(c.ticker)}</b> 已于 ${esc(last.reported)} 公布：EPS <b>$${num(last.act, 2)}</b>，预期 $${num(last.est, 2)}（${spc(last.surprise)}）${fin(last.move) ? `，股价反应 ${spc(last.move)}` : ''}。`));
      if (days >= 0) p.push(L(lg, `<b>${esc(c.ticker)}</b>'s next report: <b>${esc(e.report_date)}</b>${e.date_estimated ? ' (estimated)' : ''}, in ${days} day${days === 1 ? '' : 's'}.${fin(cs.eps) ? ` Analysts expect EPS <b>$${num(cs.eps, 2)}</b>${fin(cs.rev) ? ` on revenue of ${big(cs.rev)}` : ''}${fin(cs.year_ago_eps) ? ` (a year ago: $${num(cs.year_ago_eps, 2)})` : ''}.` : ''}`,
        `<b>${esc(c.ticker)}</b> 下次财报：<b>${esc(e.report_date)}</b>${e.date_estimated ? '（估计）' : ''}，还有 ${days} 天。${fin(cs.eps) ? `分析师预期 EPS <b>$${num(cs.eps, 2)}</b>${fin(cs.rev) ? `，营收 ${big(cs.rev)}` : ''}${fin(cs.year_ago_eps) ? `（去年同期 $${num(cs.year_ago_eps, 2)}）` : ''}。` : ''}`));
      const br = e.beat_rate, mp = (e.model || {}).p, mv = (e.implied || {}).move;
      const extra = [fin(br) ? L(lg, `beat the estimate in ${pc(br)} of past reports`, `过去 ${pc(br)} 的财报超出预期`) : '', fin(mp) && days >= 0 ? L(lg, `the model gives ${pc(mp)} odds of a beat`, `模型给出的超预期概率 ${pc(mp)}`) : '',
        fin(mv) && days >= 0 ? L(lg, `options imply a move of about ±${pc(mv, 1)} on the day`, `期权隐含财报日波动约 ±${pc(mv, 1)}`) : ''].filter(Boolean);
      if (extra.length) p.push(L(lg, 'It ', '') + extra.join(lg === 'zh' ? '；' : '; ') + L(lg, '.', '。'));
      if (!p.length) return null;
      return { html: p.join(' '), facts: [`next report ${e.report_date}`, fin(cs.eps) ? `consensus EPS $${num(cs.eps, 2)}, revenue ${big(cs.rev)}` : '', fin(br) ? `beat rate ${pc(br)}` : ''].filter(Boolean),
        mood: fin(mp) && mp > 0.7 ? 'happy' : 'talk', links: [lk(`${BASE}#c-${c.cik}-eps`, L(lg, 'EPS forecast & preview', 'EPS 预测与财报预览'))] };
    }

    async function ties(c, lg) {
      const d = await json(DATA + 'network/c/' + c.cik + '.json');
      if (!d || (!(d.customers || []).length && !(d.suppliers || []).length)) return { html: L(lg, `No customers or suppliers of <b>${esc(c.ticker)}</b> are named in the filings read so far.`, `目前读到的申报中没有点名 <b>${esc(c.ticker)}</b> 的客户或供应商。`), facts: [], mood: 'talk', links: [] };
      const rank = (a) => a.slice().sort((x, y) => (y.pct || 0) - (x.pct || 0) || (y.usd || 0) - (x.usd || 0));
      const who = (x) => (x.t || x.name || x.label ? esc(x.t || x.name || x.label) : L(lg, 'an unnamed customer', '一位未具名客户') + (x.seg ? ` (${esc(x.seg)})` : ''))
        + (fin(x.pct) ? ` ${pc(x.pct)}` : '') + (fin(x.usd) && !(x.t || x.name) ? ` ${big(x.usd)}` : '');
      const cu = rank(d.customers || []).slice(0, 6), su = rank(d.suppliers || []).slice(0, 6);
      const p = [];
      if (cu.length) p.push(L(lg, `<b>${esc(c.ticker)}</b> sells to: ${cu.map(who).join(', ')}.`, `<b>${esc(c.ticker)}</b> 的客户：${cu.map(who).join('、')}。`));
      if (su.length) p.push(L(lg, `It buys from: ${su.map(who).join(', ')}.`, `供应商：${su.map(who).join('、')}。`));
      p.push(L(lg, 'Percentages are the share of the seller\'s revenue where a filing states it; "named" links come from a sentence in a 10-K.', '百分比是申报中写明的占卖方收入比例；没有百分比的是 10-K 里点名提到的。'));
      return { html: p.join(' '), facts: [...cu.map((x) => `customer ${x.t || x.name}${fin(x.pct) ? ' ' + pc(x.pct) : ''}`), ...su.map((x) => `supplier ${x.t || x.name}${fin(x.pct) ? ' ' + pc(x.pct) : ''}`)],
        mood: 'talk', links: [lk(`${BASE}#c-${c.cik}-links`, L(lg, 'Customers, suppliers & model', '客户、供应商与模型'))] };
    }

    async function shorts(c, lg) {
      const h = await holders(c);
      const s = ((h && h.short) || []).filter((x) => Array.isArray(x) && fin(x[1]));
      if (s.length < 2) return null;
      const [d, sh, , dtc, adv] = s[s.length - 1], prev = s[s.length - 2], chg = prev[1] > 0 ? sh / prev[1] - 1 : null;   // [date, short, change %, days to cover, ADV]
      const yAgo = Date.parse(d + 'T00:00:00Z') - 365 * 864e5, yr = s.find((x) => Math.abs(Date.parse(x[0] + 'T00:00:00Z') - yAgo) <= 20 * 864e5);
      const p = [L(lg, `<b>${esc(c.ticker)}</b> short interest on ${esc(d)}: <b>${num(sh / 1e6, 1)}M shares</b>, ${spc(chg)} since ${esc(prev[0])}${fin(dtc) ? `; <b>${num(dtc, 1)} days</b> of average volume${fin(adv) ? ` (${num(adv / 1e6, 1)}M a day)` : ''} to cover` : ''}.`,
        `<b>${esc(c.ticker)}</b> ${esc(d)} 空头仓位：<b>${num(sh / 1e6, 1)} 百万股</b>，较 ${esc(prev[0])} ${spc(chg)}${fin(dtc) ? `；按日均成交量${fin(adv) ? `（${num(adv / 1e6, 1)} 百万股）` : ''}需 <b>${num(dtc, 1)} 天</b>回补` : ''}。`)];
      if (yr && yr !== s[s.length - 1] && yr[1] > 0) p.push(L(lg, `A year earlier: ${num(yr[1] / 1e6, 1)}M (${spc(sh / yr[1] - 1, 0)}).`, `一年前：${num(yr[1] / 1e6, 1)} 百万股（${spc(sh / yr[1] - 1, 0)}）。`));
      return { html: p.join(' '), facts: [`short interest ${d}: ${num(sh)} shares${fin(dtc) ? ', ' + dtc + ' days to cover' : ''}`], mood: fin(dtc) && dtc > 8 ? 'worried' : 'talk',
        links: [lk(`${BASE}#c-${c.cik}-holders`, L(lg, 'Holders, officials and short interest', '持仓、官员与空头'))] };
    }

    async function moves(c, lg) {
      const d = await json(HUB + 'research/paths/moves/index.json');
      if (!d) return null;
      const F = d.fields, row = (d.rows || []).map((r) => Object.fromEntries(F.map((f, i) => [f, r[i]]))).find((r) => fileT(r.key) === fileT(c.ticker));
      if (!row || !fin(row.move)) return null;
      const rank = row.pct >= 50 ? L(lg, `top ${num(100 - row.pct, 1)}%`, `前 ${num(100 - row.pct, 1)}%`) : L(lg, `bottom ${num(row.pct, 1)}%`, `后 ${num(row.pct, 1)}%`);
      const s = row.sim21;
      const p = [L(lg, `On ${esc(row.as_of)} <b>${esc(c.ticker)}</b> moved <b>${spc(row.move)}</b>: a ${rank} day in its history since ${esc(String(row.d0).slice(0, 4))}${fin(row.z) ? `, ${num(Math.abs(row.z), 1)}× its recent daily volatility` : ''}${fin(row.every) ? `; moves this large come about once every ${num(row.every)} trading days` : ''}.`,
        `<b>${esc(c.ticker)}</b> 在 ${esc(row.as_of)} 变动 <b>${spc(row.move)}</b>：在它 ${esc(String(row.d0).slice(0, 4))} 年以来的历史中排在${rank}${fin(row.z) ? `，相当于近期日波动的 ${num(Math.abs(row.z), 1)} 倍` : ''}${fin(row.every) ? `；这么大的波动大约每 ${num(row.every)} 个交易日出现一次` : ''}。`)];
      if (s) p.push(L(lg, `After ${num(s[0])} days like it, the stock was ${spc(s[1])} a month later on median, higher in ${pc(s[2])} of cases.`, `历史上 ${num(s[0])} 个类似交易日之后，一个月后的中位数表现为 ${spc(s[1])}，${pc(s[2])} 的情况上涨。`));
      p.push(L(lg, 'Why it moved: the filings and news around the day are on the page.', '为什么涨跌：当天前后的申报和新闻见下方页面。'));
      return { html: p.join(' '), facts: [`${row.as_of}: move ${spc(row.move)}, percentile ${num(row.pct, 1)}`, s ? `after similar days: median ${spc(s[1])} a month later, ${pc(s[2])} higher` : ''].filter(Boolean),
        mood: row.pct < 5 ? 'worried' : row.pct > 95 ? 'happy' : 'talk', links: [lk(`${BASE}#c-${c.cik}-x-moves`, L(lg, 'Move odds', '涨跌罕见度'))] };
    }

    async function guidanceRecord(c, lg) {
      const d = await json(HUB + 'market/guidance-board.json');
      const r = ((d && d.rows) || []).find((x) => String(x.cik) === String(c.cik) || fileT(x.t) === fileT(c.ticker));
      if (!r || !r.n) return { html: L(lg, `<b>${esc(c.ticker)}</b> has no guided period judged against its results yet.`, `<b>${esc(c.ticker)}</b> 还没有可以和实际结果对照的业绩指引。`), facts: [], mood: 'talk', links: [] };
      const rate = r.rate > 1 ? r.rate / 100 : r.rate;
      const p = [L(lg, `<b>${esc(c.ticker)}</b> met or beat <b>${pc(rate)}</b> of the ${num(r.n)} guided figures judged so far (${num(r.beat)} beat, ${num(r.miss)} missed)${r.raised || r.lowered ? `; it raised guidance ${num(r.raised)} times and lowered it ${num(r.lowered)}` : ''}.`,
        `<b>${esc(c.ticker)}</b> 已核对的 ${num(r.n)} 个指引数字中，<b>${pc(rate)}</b> 达到或超过（超过 ${num(r.beat)} 个，未达 ${num(r.miss)} 个）${r.raised || r.lowered ? `；上调指引 ${num(r.raised)} 次，下调 ${num(r.lowered)} 次` : ''}。`)];
      return { html: p.join(' '), facts: [`guidance record: ${pc(rate)} of ${r.n} met or beat, ${r.beat} beat, ${r.miss} missed`], mood: rate >= 0.8 ? 'happy' : rate < 0.5 ? 'worried' : 'talk',
        links: [lk(`${BASE}#c-${c.cik}-x-outlook`, L(lg, 'Outlook & guidance', '展望与指引'))] };
    }

    async function investments(c, lg) {
      const d = await json(HUB + 'research/investors/index.json');
      if (!d) return null;
      const F = d.fields, r = (d.rows || []).map((x) => Object.fromEntries(F.map((f, i) => [f, x[i]]))).find((x) => String(x.cik) === String(c.cik));
      if (!r) return { html: L(lg, `<b>${esc(c.ticker)}</b> reports no material gains on investments in other companies over the last four quarters.`, `<b>${esc(c.ticker)}</b> 过去四个季度没有报告重大的对外投资收益。`), facts: [], mood: 'talk', links: [] };
      const p = [L(lg, `Over the last four quarters <b>${esc(c.ticker)}</b> booked <b>${big(r.gains)}</b> of gains on its stakes in other companies${fin(r.share) ? `, ${pc(r.share)} of its pre-tax profit` : ''}.`,
        `过去四个季度 <b>${esc(c.ticker)}</b> 从持有的其他公司股权中获得 <b>${big(r.gains)}</b> 收益${fin(r.share) ? `，占税前利润 ${pc(r.share)}` : ''}。`)];
      const hs = (r.holdings || []).slice(0, 5);
      if (r.top_gainer) p.push(L(lg, `Its listed stake that gained most: ${esc(r.top_gainer)}${fin(r.top_gain) ? ` (+${big(r.top_gain)})` : ''}.`, `涨幅贡献最大的上市持股：${esc(r.top_gainer)}${fin(r.top_gain) ? `（+${big(r.top_gain)}）` : ''}。`));
      if (hs.length) p.push(L(lg, `Its 13F stakes include ${hs.map(esc).join(', ')}.`, `13F 持仓包括 ${hs.map(esc).join('、')}。`));
      return { html: p.join(' '), facts: [`gains on investments, four quarters: ${big(r.gains)}`, r.top_gainer ? `largest 13F holding ${r.top_gainer}` : ''].filter(Boolean), mood: r.gains > 0 ? 'happy' : 'worried',
        links: [lk(`${BASE}#c-${c.cik}-x-investments`, L(lg, 'Investments: gains and what it bought', '投资收益与持仓'))] };
    }

    /* ---------- about the market ---------- */
    const coLink = (t, cik) => (cik ? `<a href="${esc(BASE)}#c-${esc(cik)}">${esc(t)}</a>` : esc(t));
    const ol = (rows) => '<ol class="flo-list">' + rows.map((x) => `<li>${x}</li>`).join('') + '</ol>';
    const MK = {
      async nextEarnings(lg, ix) {
        const d = await json(HUB + 'research/earnings/index.json');
        if (!d) return null;
        const F = d.fields, rows = (d.rows || []).map((r) => Object.fromEntries(F.map((f, i) => [f, r[i]]))).filter((r) => fin(r.days_to) && r.days_to >= 0 && r.days_to <= 7);
        const rev = new Map(((ix && ix.companies) || []).map((c) => [fileT(c.ticker), c]));
        const R = (x) => (rev.get(fileT(x.ticker)) || {}).revenue || 0;
        rows.sort((a, b) => R(b) - R(a));
        if (!rows.length) return null;
        const by = {};
        rows.forEach((r) => (by[r.report_date] = by[r.report_date] || []).push(r));
        const html = L(lg, `<b>${rows.length}</b> ${rows.length === 1 ? 'company reports' : 'companies report'} in the next seven days. The largest:`, `未来 7 天有 <b>${rows.length}</b> 家公司发布财报，规模最大的：`) +
          ol(Object.keys(by).sort().map((dd) => `<b>${esc(dd)}</b>: ${by[dd].slice(0, 6).map((r) => coLink(r.ticker, (rev.get(fileT(r.ticker)) || {}).cik) + (fin(r.eps) ? ` (${r.eps < 0 ? '−' : ''}$${num(Math.abs(r.eps), 2)})` : '')).join(', ')}`));
        return { html, facts: rows.slice(0, 20).map((r) => `${r.ticker} reports ${r.report_date}, EPS estimate ${fin(r.eps) ? '$' + num(r.eps, 2) : 'n/a'}`), mood: 'talk', links: [lk(`${BASE}daily/earnings-calendar/`, L(lg, 'Earnings calendar', '财报日历'))] };
      },
      async insiders(lg) {
        const d = await json(HUB + 'market/insiders.json');
        const s = ((d && d.summary) || []).filter((x) => x.buy_value > 0 && x.buy_value < 1.5e9 && /^[A-Z][A-Z0-9.\-]{0,5}$/.test(x.ticker || '') && x.ticker !== 'NONE')   // a billion-dollar 'purchase' is a misread filing
          .sort((a, b) => b.buy_value - a.buy_value).slice(0, 8);
        if (!s.length) return null;
        const cl = s.filter((x) => x.cluster || (x.buyers30 || 0) >= 3);
        return { html: L(lg, `Largest insider buying since ${esc(d.since)} (open market, Form 4):`, `自 ${esc(d.since)} 以来内部人买入最多（公开市场，Form 4）：`) + ol(s.map((x) => `${coLink(x.ticker, x.cik)} ${big(x.buy_value)} · ${num(x.buys)} ${L(lg, x.buys === 1 ? 'buy' : 'buys', '笔')}${x.cluster || (x.buyers30 || 0) >= 3 ? L(lg, ' · <b>cluster</b>', ' · <b>多人同时买入</b>') : ''}`))
          + (cl.length ? L(lg, `Clusters (three or more insiders within 30 days) are the pattern studies find most telling.`, '30 天内三位以上内部人同时买入，被研究认为最有参考价值。') : ''),
        facts: s.map((x) => `${x.ticker} insiders bought ${big(x.buy_value)}`), mood: 'happy', links: [lk(`${BASE}disclosures/insider-trades/`, L(lg, 'Insider trading', '内部人交易'))] };
      },
      async congress(lg) {
        const d = await json(HUB + 'market/officials-trades.json');
        const s = (((d && d.summary) || {}).d90 || []).slice().sort((a, b) => (b.buys + b.sells) - (a.buys + a.sells)).slice(0, 8);
        if (!s.length) return null;
        return { html: L(lg, 'Most traded by members of Congress and officials in the last 90 days (buys / sells):', '过去 90 天国会议员和官员交易最多的股票（买 / 卖）：') + ol(s.map((x) => `<b>${esc(x.ticker)}</b> ${num(x.buys)} / ${num(x.sells)}${(x.people_buy || []).length ? ' · ' + esc(x.people_buy.slice(0, 2).join(', ')) : ''}`)),
          facts: s.map((x) => `${x.ticker}: ${x.buys} buys, ${x.sells} sells`), mood: 'talk', links: [lk(`${BASE}disclosures/congress-trades/`, L(lg, 'Congress stock trades', '国会议员交易'))] };
      },
      async owners(lg) {
        const d = await json(HUB + 'market/signals.json');
        const r = ((d && d.rows) || []).filter((x) => x.f13 && fin(x.f13.usd_net)).sort((a, b) => b.f13.usd_net - a.f13.usd_net);
        if (!r.length) return null;
        const q = (d.clock || {}).report_quarter_end;
        return { html: L(lg, `Funds' largest net buys in the quarter ended ${esc(q)} (13F):`, `截至 ${esc(q)} 的季度，机构净买入最多（13F）：`) + ol(r.slice(0, 6).map((x) => `<b>${esc(x.ticker)}</b> ${big(x.f13.usd_net)} · ${num(x.f13.buyers)} ${L(lg, 'buyers', '家买入')}`))
          + L(lg, 'Largest net sells: ', '净卖出最多：') + r.slice(-4).reverse().map((x) => `<b>${esc(x.ticker)}</b> ${big(x.f13.usd_net)}`).join(', ') + '.',
        facts: r.slice(0, 6).map((x) => `${x.ticker} 13F net ${big(x.f13.usd_net)}`), mood: 'talk', links: [lk(`${BASE}disclosures/smart-money/`, L(lg, 'Smart money', '机构资金流向'))] };
      },
      async moves(lg) {
        const d = await json(HUB + 'research/paths/moves/index.json');
        if (!d) return null;
        const F = d.fields, st = (d.rows || []).map((r) => Object.fromEntries(F.map((f, i) => [f, r[i]]))).filter((r) => r.kind === 'stock' && r.as_of === d.as_of && fin(r.pct));
        const dn = st.slice().sort((a, b) => a.pct - b.pct).slice(0, 5), up = st.slice().sort((a, b) => b.pct - a.pct).slice(0, 5);
        const b = d.breadth || {};
        return { html: L(lg, `${esc(d.as_of)}: the rarest falls in their own history — `, `${esc(d.as_of)} 历史上最罕见的下跌：`) + dn.map((x) => `${coLink(x.ticker, x.cik)} ${spc(x.move)}`).join(', ') + L(lg, '; the rarest rises — ', '；最罕见的上涨：') + up.map((x) => `${coLink(x.ticker, x.cik)} ${spc(x.move)}`).join(', ') + '.'
          + (fin(b.down5) ? L(lg, ` ${pc(b.down5)} of stocks had a bottom-5% day and ${pc(b.up5)} a top-5% day (about 5% each on an ordinary day).`, ` 当天 ${pc(b.down5)} 的股票出现历史后 5% 的跌幅，${pc(b.up5)} 出现前 5% 的涨幅（平常各约 5%）。`) : ''),
        facts: [...dn, ...up].map((x) => `${x.ticker} ${spc(x.move)} (percentile ${num(x.pct, 1)})`), mood: 'talk', links: [lk(`${BASE}disclosures/#moves/stocks`, L(lg, 'Move odds', '涨跌罕见度'))] };
      },
      async events(lg) {
        const d = await json(HUB + 'market/events8k.json');
        const rows = ((d && d.rows) || []).filter((x) => (x.topics || []).some((t) => /deal|control|bankruptcy|restatement|delisting|ceo|cfo|impairment|cyber/.test(t))).sort((a, b) => String(b.filed).localeCompare(String(a.filed))).slice(0, 8);
        if (!rows.length) return null;
        return { html: L(lg, 'Latest material 8-Ks:', '最新的重大 8-K：') + ol(rows.map((x) => `<b>${esc(day(x.filed))}</b> ${coLink(x.ticker || x.company, x.cik)} · ${esc((x.topics || []).join(', '))}${x.headline ? ' — ' + esc(String(x.headline).slice(0, 110)) : ''}`)),
          facts: rows.map((x) => `${day(x.filed)} ${x.company}: ${(x.topics || []).join(', ')}`), mood: 'talk', links: [lk(`${BASE}events/`, L(lg, 'Material 8-K events', '重大 8-K 事件'))] };
      },
      async shorts(lg) {
        const d = await json(HUB + 'market/short-interest.json');
        if (!d) return null;
        const by = new Map((d.rows || []).map((r) => [r.ticker, r])), pickr = (k) => ((d.top || {})[k] || []).map((t) => by.get(t)).filter(Boolean).slice(0, 5);
        const dtc = pickr('dtc'), rise = pickr('rise');
        return { html: L(lg, `Short interest on ${esc(d.settlement_date)} — most days to cover: `, `${esc(d.settlement_date)} 的空头数据 — 回补天数最多：`) + dtc.map((x) => `<b>${esc(x.ticker)}</b> ${num(x.dtc, 1)}`).join(', ')
          + L(lg, '; largest rises: ', '；空头增加最多：') + rise.map((x) => `<b>${esc(x.ticker)}</b> ${x.change_pct > 0 ? '+' : ''}${num(x.change_pct, 0)}%`).join(', ') + '.',
        facts: dtc.map((x) => `${x.ticker} ${x.dtc} days to cover`), mood: 'talk', links: [lk(`${BASE}disclosures/short-interest/`, L(lg, 'Short interest', '空头仓位'))] };
      },
      async guidanceRecord(lg) {
        const d = await json(HUB + 'market/guidance-board.json');
        const rec = ((d && d.recent) || []).filter((x) => /raised|lowered|withdrawn/.test(x[3])).slice(0, 8);
        if (!rec.length) return null;
        const W = { raised: ['raised', '上调'], lowered: ['lowered', '下调'], withdrawn: ['withdrew', '撤回'] };
        return { html: L(lg, 'Latest guidance changes:', '最新的指引变化：') + ol(rec.map((x) => `<b>${esc(x[0])}</b> ${coLink(x[1], x[2])} ${esc((W[x[3]] || [x[3], x[3]])[lg === 'zh' ? 1 : 0])}`)),
          facts: rec.map((x) => `${x[0]} ${x[1]} ${x[3]} guidance`), mood: 'talk', links: [lk(`${BASE}disclosures/guidance-track-record/`, L(lg, 'Guidance track record', '指引兑现记录'))] };
      },
      async investments(lg) {
        const d = await json(HUB + 'research/investors/index.json');
        if (!d) return null;
        const F = d.fields, r = (d.rows || []).map((x) => Object.fromEntries(F.map((f, i) => [f, x[i]]))).filter((x) => fin(x.gains)).sort((a, b) => b.gains - a.gains).slice(0, 6);
        return { html: L(lg, 'Largest gains on investments in other companies, last four quarters:', '过去四个季度对外投资收益最大的公司：') + ol(r.map((x) => `${coLink(x.t || x.name, x.cik)} ${big(x.gains)}${x.top_gainer ? ' · ' + esc(x.top_gainer) : ''}`)),
          facts: r.map((x) => `${x.t} investment gains ${big(x.gains)}`), mood: 'happy', links: [lk(`${BASE}disclosures/investment-gains/`, L(lg, 'Investment gains', '投资收益'))] };
      },
    };
    MK.stakes = async (lg) => {
      const d = await json(HUB + 'market/stakes.json');
      const s = ((d && d.summary) || []).filter((x) => x.new13d).sort((a, b) => String(b.last).localeCompare(String(a.last))).slice(0, 8);
      if (!s.length) return null;
      return { html: L(lg, 'New activist (13D) stakes — a holder above 5% who may seek to influence the company:', '新的激进投资者（13D）持股——持股超过 5% 且可能寻求影响公司的股东：') + ol(s.map((x) => `${coLink(x.ticker || x.issuer, x.cik)} · ${esc((x.filers || []).slice(0, 2).join(', '))} · ${num(x.max_percent, 1)}% · ${esc(x.last)}`)),
        facts: s.map((x) => `${x.ticker} 13D ${x.max_percent}%`), mood: 'talk', links: [lk(`${BASE}disclosures/activist-stakes/`, L(lg, 'Activist stakes', '激进投资者持股'))] };
    };
    const STAKES = /activist|13-?d\b|13-?g\b|5% (stake|holder)|激进投资|举牌/i;

    return { owners, insiders, congress, events, cashflow, segments, nextEarnings, ties, shorts, moves, guidanceRecord, investments, MK, STAKES };
  }

  /* ---------- the next questions under an answer ---------- */
  const REL = { valuation: ['analysts', 'nextEarnings', 'cashflow'], earnings: ['segments', 'cashflow', 'nextEarnings'], segments: ['ties', 'earnings'], cashflow: ['credit', 'valuation'],
    owners: ['insiders', 'congress', 'shorts'], insiders: ['owners', 'events'], congress: ['owners', 'insiders'], events: ['moves', 'earnings'], nextEarnings: ['guidanceRecord', 'options', 'segments'],
    ties: ['segments', 'industry'], shorts: ['options', 'moves', 'owners'], moves: ['events', 'opportunity'], rotation: ['industry', 'moves'], options: ['moves', 'nextEarnings'],
    credit: ['cashflow', 'valuation'], analysts: ['valuation', 'nextEarnings'], opportunity: ['rotation', 'moves'], guidanceRecord: ['nextEarnings', 'calls'], investments: ['owners', 'cashflow'],
    filings: ['events', 'earnings'], industry: ['rotation', 'ties'], calls: ['guidanceRecord', 'nextEarnings'] };
  const ASK = { segments: ['How does {t} make money?', '{t} 怎么赚钱？'], cashflow: ['{t} free cash flow', '{t} 自由现金流'], nextEarnings: ['When does {t} report next?', '{t} 下次财报什么时候？'],
    owners: ['Who owns {t}?', '谁持有 {t}？'], insiders: ['Are {t} insiders buying?', '{t} 内部人在买还是卖？'], congress: ['Congress trades in {t}', '国会议员交易 {t}'],
    events: ['{t} latest 8-K', '{t} 最新 8-K'], ties: ['{t} customers and suppliers', '{t} 的客户和供应商'], shorts: ['{t} short interest', '{t} 空头仓位'],
    moves: ['How rare is {t}\'s latest move?', '{t} 最近的涨跌有多罕见？'], guidanceRecord: ['Does {t} meet its guidance?', '{t} 的指引兑现率'], investments: ['{t} investment gains', '{t} 投资收益'],
    valuation: ['What is {t} worth?', '{t} 值多少钱？'], earnings: ['{t} latest earnings', '{t} 最新财报'], credit: ['{t} debt and default risk', '{t} 的债务和违约风险'],
    analysts: ['{t} analyst price target', '{t} 分析师目标价'], options: ['{t} options: range and max pain', '{t} 期权隐含区间'], rotation: ['Will {t} be Leading next week?', '{t} 下周会进入领先吗？'],
    industry: ['How is {t}\'s industry rotating?', '{t} 所在行业轮动'], opportunity: ['Will {t} go up or down next month?', '{t} 下个月会涨吗？'], calls: ['{t} earnings call guidance', '{t} 电话会议指引'] };
  function followUps(intents, co, lg, n = 3) {
    if (!co || !co.ticker) return [];
    const seen = new Set(intents), out = [];
    for (const k of intents) for (const r of REL[k] || []) if (!seen.has(r) && ASK[r] && out.length < n) { seen.add(r); out.push(r); }
    for (const r of ['segments', 'owners', 'nextEarnings', 'valuation']) if (out.length < n && !seen.has(r)) { seen.add(r); out.push(r); }
    return out.map((k) => { const q = ASK[k][lg === 'zh' ? 1 : 0].replace(/\{t\}/g, co.ticker); return { label: q, question: q }; });
  }
  const MARKET_ASK = [['nextEarnings', 'Who reports earnings this week?', '本周哪些公司发财报？'], ['insiders', 'Biggest insider buying lately', '最近内部人买入最多的股票'],
    ['congress', 'What is Congress trading?', '国会议员最近在交易什么？'], ['owners', 'What did funds buy most last quarter?', '上季度机构买得最多的股票'],
    ['moves', 'Most unusual moves today', '今天最罕见的涨跌'], ['events', 'Latest deals and material 8-Ks', '最新的并购和重大 8-K'], ['shorts', 'Most shorted stocks', '空头最多的股票'],
    ['guidanceRecord', 'Who raised guidance lately?', '最近谁上调了指引？']];

  const marketWords = (q) => MARKET.test(String(q || ''));
  const API = { classify, merge, isMarket, marketWords, isFollow, fuzzyCompany, make, followUps, MARKET_ASK, INTENTS, lev };
  root.FFFloInsights = API;
  if (typeof module !== 'undefined') module.exports = API;
})(typeof window !== 'undefined' ? window : globalThis);
