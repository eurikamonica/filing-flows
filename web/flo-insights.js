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
  const usd = (v) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const spc = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const L = (lg, en, zh) => (lg === 'zh' ? zh : en);
  const fileT = (t) => String(t || '').toUpperCase().replace(/\./g, '-');
  const dec = (s) => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, (m) => ({ '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" }[m]));
  const nm = (s) => esc(dec(s));                                       // a node's name as filed (already escaped in the data)
  const day = (s) => String(s || '').slice(0, 10);
  const ago = (d, n) => { const t = Date.parse(day(d) + 'T00:00:00Z'); return Number.isFinite(t) && Date.now() - t <= n * 864e5; };

  /* ---------- the questions it covers ---------- */
  const QLABEL = /\b(?:Q[1-4]\s*(?:FY\s*)?'?\d{2,4}|FY\s*'?\d{2,4})\b/i;      // "Q1 FY26", "Q3 2025", "FY2025"
  const INTENTS = [
    ['profile', /what does .{1,30} do\b|what('?s| is) .{1,25}'?s? business|business model|what (kind|sort) of (company|business)|describe (the )?(company|business)|是做什么的|做什么的|主营(业务)?|业务是什么|公司介绍|是干什么的|干什么的/i],
    ['multiples', /(compared? (with|to)|versus|vs\.?|relative to|than) (its )?(peers|rivals|competitors|the industry)|peer (multiples|valuation)|同行|同业相比|和同业|\bp\/?e\b|price.?to.?(earnings|sales|book)|pe ratio|multiples?\b|market (cap|capitali[sz]ation|value)|enterprise value|\bev\b|ebitda|(share|stock) price|price of|how much is .{1,20} (stock|share)|valued at|市盈率|市值|估值倍数|企业价值|股价|多少钱一股|市销率/i],
    ['debtLoad', /how much (debt|cash)|debt load|net (debt|cash)|cash (pile|on hand|position)|total debt|debt maturit|falls? due|负债多少|多少(债|负债|现金)|净负债|净现金|现金储备|账上.{0,4}现金|到期债务|债务到期/i],
    ['sectors', /which sectors?|(best|worst|strongest|weakest|top) (performing )?sectors?|sectors? (are |is )?(leading|lagging|ranking|performance|rotation|doing)|how are (the )?sectors|哪个板块|哪些板块|板块(轮动|排名|强弱|表现)|行业板块|最强(的)?板块/i],
    ['largest', /(largest|biggest|top \d*) (companies|firms|businesses)|companies by (revenue|size|sales)|最大的公司|营收最(高|大)的公司|规模最大/i],
    ['brief', /\bbrief(ing)?\b|summar(y|ise|ize)|overview|tell me about|what'?s (going on|new) (with|at)|key (facts|points|numbers|things)|things to know|snapshot|in a nutshell|tl;?dr|总结|概况|简介|介绍一下|一句话|要点|速览|快速了解|基本情况/i],
    ['why', /\bwhy\b.{0,40}\b(revenue|sales|profit|margins?|income|earnings|eps|cash|costs?|expenses?|grow|grew|growth|drop(ped)?|decline[sd]?|fell|rose|jump(ed)?|improve[sd]?|worse|better)\b|what (drove|caused|changed)|explain (the|its) (quarter|results)|为什么.{0,12}(营收|收入|利润|毛利|净利|现金|成本|费用|增长|下降|下滑|提高|变好|变差)|什么导致|原因是什么/i],
    ['trend', /\btrend\b|over time|by quarter|quarter by quarter|last \d+ quarters|past \d+ quarters|\bhistory\b|historical|each quarter|every quarter|趋势|历史|过去几个季度|每个季度|逐季|近几个季度|历年/i],
    ['owners', /who owns|who('s| is| are) (buying|selling|holding)|\bholders?\b|institution(al)?s?\b|\b13-?f\b|hedge funds?|(funds?|managers?) (own|hold|buy|bought|sell|sold|adding|cutting)|biggest (holder|owner|shareholder)|top shareholders?|谁持有|持股|机构持仓|机构|基金(经理)?(买|卖|持有|增持|减持)?|大股东|股东/i],
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
    ['investments', /\binvestments\b(?! (bank|banking|grade|advis))|investment gains?|investment portfolio|gains? on (its )?investments?|stakes? in (other )?companies|equity investments?|venture (bets|stakes)|what (did|does) .{0,20}invest in|投资收益|投资了哪些|持有哪些公司|股权投资|投了谁/i],
    ['quality', /earnings quality|quality (score|grade|of (its |the )?(earnings|profits?))|accruals?|beneish|dechow|piotroski|manipulat|cook(ing|ed) the books|aggressive accounting|red flags? in (its |the )?(accounting|earnings)|盈余质量|财报质量|利润质量|盈利质量|做假账|操纵利润|会计(质量|风险)|财务造假/i],
    ['runway', /cash runway|\brunway\b|how long (can|will|does) .{0,25}(last|survive|fund)|months of cash|run(s|ning)? out of (cash|money)|going concern|现金(能|还能)?撑|还能撑|现金跑道|现金够(用|不够)|会不会(破产|没钱)|能撑多久/i],
    ['screen', /\bscreen(er|s)?\b|which (stocks|companies) (have|are|with|show)|find (me )?(stocks|companies|names)|(stocks|companies) (with|that have|where|whose)|momentum stocks|short squeeze|fallen (leaders|angels)|cash machines|distress(ed)? (watch|stocks|companies)|筛选|选股|找(一些|几个|出)?(股票|公司)|哪些公司.{0,8}(有|在|是|正在)|有哪些.{0,6}(股票|公司)/i],
    ['afterEvent', /what (usually |typically |normally )?happens? after|after (an? |the )?8-?k|8-?k (impact|reaction|effect|items?)|which 8-?k|items? \d\.\d\d|(move|reaction|react) (after|following|to) (an? )?(8-?k|filing|announcement)|公告(之)?后|8-?k ?(之后|后|影响|反应)|哪种公告|公告.{0,4}(涨|跌)/i],
    ['insiderSignal', /insider (trades?|buys?|buying|signals?) (predict|work|track record|backtest|reliab|matter|mean)|do insiders? (know|predict|beat)|follow(ing)? (the )?insiders|insider (signal|pattern|backtest|track record)|cluster buy|内部人.{0,8}(准不准|靠谱|信号|预测|跟着|胜率|有用)|跟着内部人/i],
    ['backtest', /if (i|you|one) (had )?(bought|invested|put)|had i (bought|invested)|what would .{0,40}(bought|invested|put in|ago).{0,40} be worth|worth (now|today) if|(bought|invested) .{0,30}\b(in|on|at) (20\d\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|\d+ years? ago.{0,30}(worth|now|today)|如果.{0,10}(买|投)(了|入)?|当初买|要是.{0,8}买了|(买了|投了).{0,12}现在值多少|回测/i],
  ];
  // words that ask about the market rather than one company ("who reports this week", "biggest insider buys")
  const MARKET = /which sectors?|sectors? (are|is) |by revenue|largest companies|biggest companies|this week|next week|today|lately|recent(ly)?|latest|biggest|largest|most|top \d*|which (stocks|companies)|what (stocks|companies)|any (stocks|companies)|list|ranking|leaderboard|across the market|in the market|本周|这周|下周|今天|最近|最新|最大|最多|哪些|哪几|排行|榜|全市场|有哪/i;
  const PRONOUN = /\b(it|its|this (company|stock)|they|their|the company)\b|这家|它|该公司|这只/i;
  function classify(q) {
    const s = String(q || ''), out = [];
    for (const [k, rx] of INTENTS) if (rx.test(s)) out.push(k);
    if (QLABEL.test(s) && !out.includes('trend') && !out.includes('nextEarnings')) out.push('trend');
    // "NVDA market cap" is the multiples; "NVDA 的股价为增长付了多少" is the models' value: the price alone does not decide
    if (out.includes('multiples') && !/\bp\/?e\b|price.?to|pe ratio|multiples?\b|market (cap|capitali|value)|enterprise value|\bev\b|ebitda|市盈率|市值|估值倍数|企业价值|市销率/i.test(s)
      && /为增长|growth|pvgo|\bdcf\b|worth|值多少|值得|低估|高估|fair|intrinsic|合理|monte carlo|蒙特卡洛|upside|上涨空间|价值|概率|odds/i.test(s)) out.splice(out.indexOf('multiples'), 1);
    if (out.includes('why') && out.includes('moves') && /revenue|sales|profit|margin|income|earnings|eps|cash|cost|expense|营收|收入|利润|毛利|净利|现金|成本|费用/i.test(s)) out.splice(out.indexOf('moves'), 1);
    if (out.includes('why') && /scan|扫描|lately|recently|since/i.test(s) && !/revenue|profit|margin|income|cash|营收|利润/i.test(s)) out.splice(out.indexOf('why'), 1);
    if (out.includes('brief') && (out.length > 1 || /income statement|statement|earnings|results|quarter|revenue|cash ?flow|balance sheet|财报|利润表|季度|营收/i.test(s)))
      out.splice(out.indexOf('brief'), 1);                         // "income statement summary", "overview of its cash flow": that, not a briefing
    // the newer models answer the whole question: a screen is not the insider list, "after an 8-K" is not the latest 8-K
    const ONLY = { screen: ['insiders', 'shorts', 'events', 'multiples', 'owners', 'nextEarnings', 'cashflow', 'quality'], afterEvent: ['events', 'multiples', 'moves'], insiderSignal: ['insiders'], backtest: ['multiples', 'trend', 'moves'], runway: ['cashflow', 'debtLoad'] };
    for (const k of Object.keys(ONLY)) if (out.includes(k)) for (const r of ONLY[k]) if (out.includes(r)) out.splice(out.indexOf(r), 1);
    return out;
  }
  // the model intents (mascot.js) a more specific one here replaces: "earnings date" is not the last quarter's earnings
  const REPLACES = { quality: ['earnings', 'credit'], runway: ['cashflow', 'debtLoad', 'credit'], screen: ['help', 'rotation', 'opportunity', 'industry'], afterEvent: ['events', 'moves'], insiderSignal: ['insiders'], backtest: ['moves', 'earnings', 'valuation'], profile: ['segments', 'valuation', 'help'], multiples: ['analysts', 'industry'], debtLoad: ['cashflow'], brief: ['earnings', 'valuation', 'rotation'], why: ['earnings', 'moves', 'calls'], trend: ['earnings'], nextEarnings: ['earnings', 'calls'], cashflow: ['earnings'], segments: ['earnings'], guidanceRecord: ['calls'], shorts: ['opportunity'],
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

  /* ---------- what a term means ("What is free cash flow?", "什么是 13F") ---------- */
  const GLOSSARY = [
    [/free cash flow|\bfcf\b|自由现金流/i, ['Free cash flow', 'Cash from operations minus capital spending: what the business produced that it could pay out, invest or keep. It can be negative in heavy investment years even when the company is profitable.'],
      ['自由现金流', '经营现金流减去资本支出：企业经营产生、可以分红、回购、再投资或留存的现金。大举投资的年份即使盈利，自由现金流也可能为负。']],
    [/operating cash flow|\bocf\b|经营现金流/i, ['Operating cash flow', 'Net income adjusted for non-cash items (depreciation, stock pay) and for money tied up in or released from working capital — the cash the business itself brought in.'],
      ['经营现金流', '在净利润基础上加回折旧、股票薪酬等非现金项目，并扣除或加回营运资金的变化，即业务本身带来的现金。']],
    [/operating margin|营业利润率|经营利润率/i, ['Operating margin', 'Operating income divided by revenue: how many cents of each dollar of sales are left after the costs of running the business, before interest and tax.'],
      ['营业利润率', '营业利润除以营收：每 1 美元销售在扣除经营成本后、利息和税之前还剩多少。']],
    [/gross margin|毛利率/i, ['Gross margin', 'Revenue minus the direct cost of what was sold, as a share of revenue.'], ['毛利率', '营收减去所售商品或服务的直接成本，再除以营收。']],
    [/\beps\b|earnings per share|每股收益/i, ['EPS', 'Net income per share. Analysts\' estimates usually use adjusted (non-GAAP) EPS, which can differ from the GAAP figure in the filing.'],
      ['每股收益（EPS）', '每股净利润。分析师预期通常用调整后（非 GAAP）的 EPS，可能与财报中的 GAAP 数字不同。']],
    [/\b13-?f\b/i, ['13F', 'A quarterly SEC report of the US-listed stocks held by every investment manager with $100 million or more, filed within 45 days of the quarter\'s end. It shows long positions only.'],
      ['13F', '管理资产超过 1 亿美元的投资机构每季度向 SEC 报告所持美股的文件，季度结束后 45 天内提交，只包含多头持仓。']],
    [/\b13-?d\b|\b13-?g\b/i, ['Schedule 13D / 13G', 'Filed by anyone who owns more than 5% of a company\'s shares. A 13D means the holder may try to influence the company (an activist); a 13G is for passive holders.'],
      ['13D / 13G', '持有公司 5% 以上股份时必须提交。13D 表示持有人可能寻求影响公司（激进投资者）；13G 用于被动持有人。']],
    [/form ?4\b/i, ['Form 4', 'Filed within two business days when an officer, director or 10% owner trades the company\'s stock. Code P is an open-market purchase, S a sale.'],
      ['Form 4', '高管、董事或 10% 股东买卖公司股票后两个工作日内提交。代码 P 是公开市场买入，S 是卖出。']],
    [/form ?144\b/i, ['Form 144', 'A notice that an affiliate intends to sell restricted or control shares. It is an intention, not a sale; the sale itself is reported on Form 4.'],
      ['Form 144', '关联人拟出售受限股或控制性股份的通知。只是意向，实际卖出要看 Form 4。']],
    [/\b8-?k\b/i, ['8-K', 'A current report a company files within four business days of a material event: results, a deal, new debt, a leadership change, an impairment, a delisting notice.'],
      ['8-K', '公司在发生重大事件后四个工作日内提交的临时报告：业绩、交易、新增债务、高管变动、减值、退市通知等。']],
    [/\b10-?q\b|\b10-?k\b/i, ['10-Q and 10-K', 'The quarterly (10-Q) and annual (10-K) reports with the financial statements; the 10-K is audited and describes the business and its risks.'],
      ['10-Q 与 10-K', '季度报告（10-Q）和年度报告（10-K），包含财务报表；10-K 经过审计，并介绍业务与风险。']],
    [/short interest|空头仓位|卖空比例/i, ['Short interest', 'Shares sold short and not yet bought back, reported twice a month (FINRA). Days to cover = short interest divided by average daily volume.'],
      ['空头仓位', '已卖空但尚未买回的股数，每月公布两次（FINRA）。回补天数 = 空头仓位 ÷ 日均成交量。']],
    [/days to cover|回补天数/i, ['Days to cover', 'Short interest divided by average daily volume: how many days of normal trading it would take short sellers to buy back.'], ['回补天数', '空头仓位除以日均成交量：按正常成交量空头需要几天才能全部买回。']],
    [/max(imum)? ?pain|最大痛点/i, ['Max pain', 'The expiry price at which the options outstanding would pay their holders the least. Some traders watch it; it is not a forecast.'],
      ['最大痛点', '在该到期价格下，未平仓期权支付给持有人的总额最少。部分交易者会参考，但它不是预测。']],
    [/implied vol(atility)?|\biv\b|隐含波动/i, ['Implied volatility', 'The size of moves priced into options, as an annual percentage. ±IV × √(days/365) gives a rough one-standard-deviation range.'],
      ['隐含波动率', '期权价格中隐含的波动幅度（年化百分比）。±IV × √(天数/365) 约等于一个标准差的价格区间。']],
    [/\brrg\b|relative rotation|相对轮动/i, ['RRG (relative rotation graph)', 'Plots a stock\'s strength against the market (RS-Ratio) against the momentum of that strength (RS-Momentum). Leading: strong and rising; Weakening; Lagging; Improving.'],
      ['RRG（相对轮动图）', '横轴是相对大盘的强弱（RS-Ratio），纵轴是这种强弱的动量（RS-Momentum）。领先：强且在增强；转弱；落后；改善。']],
    [/\bdcf\b|discounted cash flow|现金流折现/i, ['DCF', 'Discounted cash flow: the value today of the cash a business is expected to produce, each year\'s cash discounted at the cost of capital.'],
      ['DCF（现金流折现）', '把企业未来预计产生的现金按资本成本折回今天的价值。']],
    [/\bpvgo\b|增长机会现值/i, ['PVGO', 'Present value of growth opportunities: the part of the price above what today\'s earnings would be worth with no growth.'], ['PVGO', '增长机会现值：股价中超过“零增长时当前盈利价值”的部分。']],
    [/altman|z-?score/i, ['Altman Z-score', 'A distress score from working capital, retained earnings, operating profit, market value and sales relative to assets and liabilities. Below about 1.8: distress zone; above about 3: safe.'],
      ['Altman Z 值', '用营运资金、留存收益、营业利润、市值和销售额相对资产负债计算的困境评分。约低于 1.8 为困境区，高于约 3 为安全区。']],
    [/monte carlo|蒙特卡洛/i, ['Monte Carlo', 'Thousands of scenarios with the model\'s inputs drawn at random; the share of scenarios above the price is a rough sense of the odds, not a probability forecast.'],
      ['蒙特卡洛', '随机抽取模型输入、模拟数千种情形；价值高于股价的情形占比只是大致的倾向，不是概率预测。']],
    [/\bxbrl\b/i, ['XBRL', 'The tagged data in SEC filings: each number in the financial statements carries a tag, which is how Filing Flows reads them.'], ['XBRL', 'SEC 申报中的结构化标签数据：财报中每个数字都带标签，Filing Flows 就是读取这些标签。']],
    [/sankey|桑基/i, ['Sankey diagram', 'A flow chart whose band widths are proportional to amounts: here revenue splitting into costs, profit, tax and cash.'], ['桑基图', '带宽与金额成比例的流向图：这里显示营收如何流向成本、利润、税和现金。']],
    [/10b5-?1/i, ['10b5-1 plan', 'A trading plan an insider sets up in advance; sales under it are scheduled and say less about the insider\'s current view.'], ['10b5-1 计划', '内部人预先设定的交易计划；按计划的卖出是事先安排的，较少反映内部人当下的看法。']],
    [/guidance|业绩指引/i, ['Guidance', 'What a company says it expects for the coming quarter or year (revenue, EPS, margins), usually in its earnings release.'], ['业绩指引', '公司对下一季度或全年的预期（营收、EPS、利润率等），通常在业绩公告中给出。']],
    [/buy ?backs?|share repurchases?|回购/i, ['Buyback', 'A company buying its own shares; fewer shares outstanding means each remaining share owns more of the earnings.'], ['回购', '公司买回自己的股票；流通股减少，每股对应的盈利更多。']],
    [/capex|capital (spending|expenditures?)|资本支出/i, ['Capital spending (capex)', 'Cash paid for long-lived assets — buildings, equipment, data centers, software — recorded in investing cash flow.'], ['资本支出', '购买厂房、设备、数据中心、软件等长期资产所付的现金，记在投资现金流里。']],
    [/working capital|cash conversion cycle|营运资金|现金转换周期/i, ['Working capital', 'Receivables plus inventory minus payables. The cash conversion cycle (receivable days + inventory days − payable days) is how long cash is tied up.'],
      ['营运资金', '应收账款加存货减应付账款。现金转换周期 = 应收天数 + 存货天数 − 应付天数，表示现金被占用多久。']],
    [/impairment|减值/i, ['Impairment', 'A write-down of an asset — often goodwill from an acquisition — to less than what was paid for it.'], ['减值', '将资产（常见为收购产生的商誉）减记到低于原支付价格的价值。']],
    [/\bebitda\b/i, ['EBITDA', 'Earnings before interest, taxes, depreciation and amortization: operating profit with the non-cash charges added back. A rough measure of cash earnings before capital spending.'],
      ['EBITDA', '息税折旧摊销前利润：营业利润加回折旧和摊销等非现金费用，粗略衡量资本支出之前的现金盈利。']],
    [/\bp\/?e\b|price.?to.?earnings|pe ratio|市盈率/i, ['P/E', 'Share price divided by earnings per share (usually the last twelve months): how many years of today\'s profit the price pays for.'], ['市盈率（P/E）', '股价除以每股收益（通常是过去十二个月）：股价相当于多少年的当前利润。']],
    [/market cap(itali[sz]ation)?|市值/i, ['Market capitalization', 'Share price times shares outstanding: what the market values the equity at.'], ['市值', '股价乘以流通股数：市场对公司股权的估值。']],
    [/enterprise value|企业价值/i, ['Enterprise value', 'Market value plus debt minus cash: the price of the whole business, owed to shareholders and lenders.'], ['企业价值', '市值加债务减现金：整个企业（股东和债权人）的价格。']],
    [/dividend yield|股息率/i, ['Dividend yield', 'Dividends paid over a year divided by the share price.'], ['股息率', '一年分红除以股价。']],
    [/goodwill|商誉/i, ['Goodwill', 'The part of an acquisition\'s price above the fair value of the assets bought; it is tested for impairment, not amortized.'], ['商誉', '收购价格中超过所购资产公允价值的部分；不摊销，但要做减值测试。']],
    [/\broe\b|return on equity|净资产收益率/i, ['ROE', 'Net income divided by shareholders\' equity: profit earned on the owners\' capital.'], ['ROE（净资产收益率）', '净利润除以股东权益：股东资本的回报率。']],
    [/\bbeta\b|贝塔/i, ['Beta', 'How much a stock has moved with the market: 1 moves with it, above 1 more, below 1 less.'], ['贝塔', '股票随大盘波动的程度：1 与大盘同步，大于 1 波动更大，小于 1 更小。']],
    [/gross profit|毛利(?!率)/i, ['Gross profit', 'Revenue minus the cost of what was sold.'], ['毛利', '营收减去所售商品或服务的成本。']],
    [/net income|net earnings|净利润/i, ['Net income', 'What is left of revenue after every cost, interest and tax: the bottom line.'], ['净利润', '营收扣除所有成本、利息和税之后剩下的部分，即“底线”。']],
    [/non-?gaap|adjusted earnings|非 ?gaap/i, ['Non-GAAP', 'Figures the company adjusts itself, usually excluding stock pay, amortization and one-offs; they are not audited like GAAP figures.'], ['非 GAAP', '公司自行调整的指标，通常剔除股票薪酬、摊销和一次性项目，不像 GAAP 数字那样经过审计。']],
  ];
  const DEFINE = /^\s*(what('?s| is| are| does| do)|define|definition of|meaning of|explain( what)?|what is meant by)\b|什么是|是什么意思|是什么|啥是|什么叫|意思是|解释一下/i;
  function glossary(q, lg) {
    const s = String(q || '');
    if (!DEFINE.test(s)) return null;
    const hit = GLOSSARY.filter(([rx]) => rx.test(s));
    if (!hit.length) return null;
    const html = hit.slice(0, 2).map(([, en, zh]) => { const [k, v] = lg === 'zh' ? zh : en; return `<b>${esc(k)}</b>: ${esc(v)}`; }).join('<br><br>');
    return { html, facts: hit.slice(0, 2).map(([, en]) => `${en[0]}: ${en[1]}`), mood: 'talk', links: [], intents: ['glossary'] };
  }

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
    'market', 'filing', 'filings', 'options', 'expensive', 'compared', 'compare', 'peers', 'against', 'versus', 'interest', 'shorted', 'trading', 'traded', 'latest', 'biggest', 'largest', 'unusual', 'activist', 'stakes', 'deals', 'guidance', 'customers', 'suppliers', 'segments', 'congress', 'industry', 'sector', 'compare', 'versus', 'debt', 'credit']);
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
        if (d <= 1 && (!best || d < best.d || (d === best.d && (c.revenue || 0) > (best.c.revenue || 0)))) best = { c, d };
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
      const ask = String(arguments[2] || '');
      const want = [/dividend|股息|分红/i.test(ask) && 'div', /buy ?back|repurchase|回购/i.test(ask) && 'buyback'].filter(Boolean);
      for (const k of want) p.push(fin(ti[k]) && ti[k] < 0 ? L(lg, `${CASH[k][0][0].toUpperCase() + CASH[k][0].slice(1)} over twelve months: <b>${big(-ti[k])}</b>${fin(tf) && tf > 0 ? ` (${pc(-ti[k] / tf)} of free cash flow)` : ''}.`, `过去十二个月${CASH[k][1]}：<b>${big(-ti[k])}</b>${fin(tf) && tf > 0 ? `（占自由现金流 ${pc(-ti[k] / tf)}）` : ''}。`)
        : L(lg, `No ${CASH[k][0]} in the last twelve months' cash-flow statements.`, `过去十二个月现金流量表中没有${CASH[k][1]}。`));
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
        '<ul class="flo-list">' + lines.slice(0, 6).map((n) => `<li><b>${nm(n.name)}</b> ${big(n.v)} · ${n.v / tot < 0.01 ? '<1%' : pc(n.v / tot, 0)}${g(n) ? ` · ${L(lg, 'Y/Y', '同比')} ${g(n)}` : ''}</li>`).join('') + '</ul>'];
      if (fast) p.push(L(lg, `Fastest-growing large line: <b>${nm(fast.name)}</b> (${g(fast)}).`, `增长最快的主要业务：<b>${nm(fast.name)}</b>（${g(fast)}）。`));
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
      if (days < 0 && !(last && ago(last.reported, 10))) p.push(L(lg, `<b>${esc(c.ticker)}</b> last reported on ${esc(e.report_date)}; the next date is not set yet.`, `<b>${esc(c.ticker)}</b> 上次财报在 ${esc(e.report_date)}；下次日期尚未公布。`));
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
      const pr = (x) => (x < 0.1 ? '0.1' : num(x, x < 1 ? 2 : 1)), lt = (x) => (x < 0.1 ? L(lg, 'under ', '不到 ') : '');
      const rank = row.pct >= 50 ? L(lg, `top ${lt(100 - row.pct)}${pr(100 - row.pct)}%`, `前 ${lt(100 - row.pct)}${pr(100 - row.pct)}%`) : L(lg, `bottom ${lt(row.pct)}${pr(row.pct)}%`, `后 ${lt(row.pct)}${pr(row.pct)}%`);
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
      async nextEarnings(lg, ix, q) {
        const d = await json(HUB + 'research/earnings/index.json');
        if (!d) return null;
        // "this week" runs to Friday, "next week" is Monday to Friday after it, otherwise the next seven days
        const now = new Date(), dow = now.getUTCDay(), iso = (n) => new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + n)).toISOString().slice(0, 10);
        const nextMon = ((8 - dow) % 7) || 7;
        const [a, b, what] = /next week|下周|下星期/i.test(String(q || '')) ? [iso(nextMon), iso(nextMon + 4), L(lg, 'next week', '下周')]
          : /this week|本周|这周|这星期/i.test(String(q || '')) && dow >= 1 && dow <= 5 ? [iso(0), iso(5 - dow), L(lg, 'this week', '本周')] : [iso(0), iso(7), L(lg, 'in the next seven days', '未来 7 天')];
        const F = d.fields, rows = (d.rows || []).map((r) => Object.fromEntries(F.map((f, i) => [f, r[i]]))).filter((r) => r.report_date >= a && r.report_date <= b);
        const rev = new Map(((ix && ix.companies) || []).map((c) => [fileT(c.ticker), c]));
        const R = (x) => (rev.get(fileT(x.ticker)) || {}).revenue || 0;
        rows.sort((a, b) => R(b) - R(a));
        if (!rows.length) return null;
        const by = {};
        rows.forEach((r) => (by[r.report_date] = by[r.report_date] || []).push(r));
        const html = L(lg, `<b>${rows.length}</b> ${rows.length === 1 ? 'company reports' : 'companies report'} ${what}. The largest:`, `${what}有 <b>${rows.length}</b> 家公司发布财报，规模最大的：`) +
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
      async congress(lg, ix, q) {
        const d = await json(HUB + 'market/officials-trades.json');
        const words = (String(q || '').toLowerCase().match(/[a-z]{4,}/g) || []).filter((w) => !['what', 'congress', 'trading', 'trade', 'trades', 'bought', 'sold', 'anything', 'stock', 'stocks', 'members', 'lately', 'recent', 'recently', 'senator', 'representative'].includes(w));
        const byP = words.length ? ((d && d.trades) || []).filter((x) => words.some((w) => String(x.person || '').toLowerCase().split(/[\s.,]+/).includes(w))) : [];
        if (byP.length) {
          const who = byP[0].person, rows = byP.filter((x) => x.person === who).sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 8);
          const bw = (x) => (/purchase|buy/i.test(x.type || '') ? L(lg, 'bought', '买入') : L(lg, 'sold', '卖出'));
          return { html: L(lg, `<b>${esc(who)}</b>'s latest disclosed trades:`, `<b>${esc(who)}</b> 最近披露的交易：`) + ol(rows.map((x) => `<b>${esc(x.ticker || x.asset_raw || '')}</b> ${bw(x)} ${big(x.amount_min)}–${big(x.amount_max)} · ${esc(day(x.date))}${x.filed_date ? L(lg, ` (reported ${esc(day(x.filed_date))})`, `（${esc(day(x.filed_date))} 申报）`) : ''}`)),
            facts: rows.map((x) => `${who} ${x.type} ${x.ticker} ${day(x.date)}`), mood: 'talk', links: [lk(`${BASE}disclosures/congress-trades/`, L(lg, 'Congress stock trades', '国会议员交易'))] };
        }
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
    MK.largest = async (lg, ix) => {
      const rows = ((ix && ix.companies) || []).filter((c) => fin(c.revenue) && c.ticker).sort((a, b) => b.revenue - a.revenue).slice(0, 10);
      if (!rows.length) return null;
      return { html: L(lg, 'The largest companies on file by their latest quarter\'s revenue:', '按最新一季营收排名的最大公司：') + ol(rows.map((c) => `${coLink(c.ticker, c.cik)} ${big(c.revenue)} · ${esc(c.label || '')}${fin(c.yoy) ? ` · ${L(lg, '', '同比 ')}${c.yoy >= 0 ? '+' : '−'}${num(Math.abs(c.yoy))}%${L(lg, ' Y/Y', '')}` : ''}`)),
        facts: rows.map((c) => `${c.ticker} ${big(c.revenue)} in ${c.label}`), mood: 'talk', links: [lk(`${BASE}c/`, L(lg, 'Every company A–Z', '全部公司'))] };
    };
    MK.stakes = async (lg) => {
      const d = await json(HUB + 'market/stakes.json');
      const s = ((d && d.summary) || []).filter((x) => x.new13d).sort((a, b) => String(b.last).localeCompare(String(a.last))).slice(0, 8);
      if (!s.length) return null;
      return { html: L(lg, 'New activist (13D) stakes — a holder above 5% who may seek to influence the company:', '新的激进投资者（13D）持股——持股超过 5% 且可能寻求影响公司的股东：') + ol(s.map((x) => `${coLink(x.ticker || x.issuer, x.cik)} · ${esc((x.filers || []).slice(0, 2).join(', '))} · ${num(x.max_percent, 1)}% · ${esc(x.last)}`)),
        facts: s.map((x) => `${x.ticker} 13D ${x.max_percent}%`), mood: 'talk', links: [lk(`${BASE}disclosures/activist-stakes/`, L(lg, 'Activist stakes', '激进投资者持股'))] };
    };
    const STAKES = /activist|13-?d\b|13-?g\b|5% (stake|holder)|激进投资|举牌/i;

    // brief: six lines from six files — the business, profit and cash, value, the next report, the funds, the insiders
    async function brief(c, lg) {
      const T = encodeURIComponent(fileT(c.ticker));
      const [d, v, e, h, ins] = await Promise.all([json(DATA + 'c/' + c.cik + '.json'), json(HUB + 'research/valuation/c/' + c.cik + '.json'),
        json(HUB + 'research/earnings/c/' + T + '.json'), holders(c), json(HUB + 'market/insiders.json')]);
      const q = ((d && d.quarters) || [])[0], hd = (q && q.headline) || {}, items = [];
      if (q && fin(hd.revenue)) {
        const N = new Map((q.nodes || []).map((n) => [n.id, n]));
        const segs = (q.links || []).filter((l) => l.t === 'revenue' && N.get(l.s)).map((l) => N.get(l.s)).filter((n) => fin(n.v)).sort((a, b) => b.v - a.v);
        items.push(L(lg, `<b>Business</b>: ${big(hd.revenue)} revenue in ${esc(q.label)}${fin(hd.yoy) ? ` (${hd.yoy >= 0 ? '+' : '−'}${num(Math.abs(hd.yoy))}% Y/Y)` : ''}${segs.length >= 2 && segs[0].v / hd.revenue < 0.95 ? `, mostly ${nm(segs[0].name)} (${pc(segs[0].v / hd.revenue)})` : ''}.`,
          `<b>业务</b>：${esc(q.label)} 营收 ${big(hd.revenue)}${fin(hd.yoy) ? `（同比 ${hd.yoy >= 0 ? '+' : '−'}${num(Math.abs(hd.yoy))}%）` : ''}${segs.length >= 2 && segs[0].v / hd.revenue < 0.95 ? `，主要来自 ${nm(segs[0].name)}（${pc(segs[0].v / hd.revenue)}）` : ''}。`));
      }
      const tt = (((d && d.quality) || {}).cap || {}).ttm, ti = (tt && tt.items) || {}, fcf = fin(ti.ocf) ? ti.ocf + (ti.capex || 0) : null;
      if (fin(hd.om) || fin(fcf)) items.push(L(lg, `<b>Profit and cash</b>: ${fin(hd.om) ? `operating margin ${num(hd.om, 1)}%` : ''}${fin(hd.om) && fin(fcf) ? '; ' : ''}${fin(fcf) ? `free cash flow ${big(fcf)} over twelve months` : ''}.`,
        `<b>利润与现金</b>：${fin(hd.om) ? `营业利润率 ${num(hd.om, 1)}%` : ''}${fin(hd.om) && fin(fcf) ? '；' : ''}${fin(fcf) ? `过去十二个月自由现金流 ${big(fcf)}` : ''}。`));
      const sw = ((v && v.football) || []).find((b) => /^Stage-weighted/.test(b.method));
      if (sw && fin(v.price) && v.price > 0) { const g = sw.point / v.price - 1; items.push(L(lg, `<b>Value</b>: ${usd(v.price)} against a model value of ${usd(sw.point)} (${g >= 0 ? '+' : '−'}${pc(Math.abs(g))}).`, `<b>估值</b>：现价 ${usd(v.price)}，模型价值 ${usd(sw.point)}（${g >= 0 ? '+' : '−'}${pc(Math.abs(g))}）。`)); }
      const today = new Date().toISOString().slice(0, 10);
      if (e && e.report_date && e.report_date < today) items.push(L(lg, `<b>Last report</b>: ${esc(e.report_date)}; the next date is not set yet.`, `<b>上次财报</b>：${esc(e.report_date)}；下次日期尚未公布。`));
      else if (e && e.report_date) { const cs = e.consensus || {}; items.push(L(lg, `<b>Next report</b>: ${esc(e.report_date)}${fin(cs.eps) ? `, EPS expected $${num(cs.eps, 2)}` : ''}${fin(e.beat_rate) ? `; beat ${pc(e.beat_rate)} of the time` : ''}.`, `<b>下次财报</b>：${esc(e.report_date)}${fin(cs.eps) ? `，预期 EPS $${num(cs.eps, 2)}` : ''}${fin(e.beat_rate) ? `；历史超预期率 ${pc(e.beat_rate)}` : ''}。`)); }
      const f = (h && h.flows) || {};
      if (fin(f.usd_net)) items.push(L(lg, `<b>Funds</b>: ${num(f.buyers)} 13F managers bought, ${num(f.sellers)} sold last quarter (net ${big(f.usd_net)}).`, `<b>机构</b>：上季度 ${num(f.buyers)} 家 13F 机构买入、${num(f.sellers)} 家卖出（净额 ${big(f.usd_net)}）。`));
      const s = ((ins && ins.summary) || []).find((x) => fileT(x.ticker) === fileT(c.ticker));
      const bs = (s0) => [s0.buy_value > 0 && L(lg, `bought ${big(s0.buy_value)}`, `买入 ${big(s0.buy_value)}`), s0.sell_value > 0 && L(lg, `sold ${big(s0.sell_value)}`, `卖出 ${big(s0.sell_value)}`)].filter(Boolean).join(lg === 'zh' ? '，' : ', ');
      items.push(s ? L(lg, `<b>Insiders</b>: ${bs(s)} since ${esc(ins.since)}.`, `<b>内部人</b>：自 ${esc(ins.since)} 起${bs(s)}。`)
        : ins ? L(lg, `<b>Insiders</b>: no open-market buys or sells since ${esc(ins.since)}.`, `<b>内部人</b>：自 ${esc(ins.since)} 起没有公开市场买卖。`) : '');
      const list = items.filter(Boolean);
      if (list.length < 2) return null;
      return { html: L(lg, `<b>${esc(c.ticker)}</b> at a glance:`, `<b>${esc(c.ticker)}</b> 速览：`) + '<ul class="flo-list">' + list.map((x) => `<li>${x}</li>`).join('') + '</ul>',
        facts: list.map((x) => x.replace(/<[^>]+>/g, '')), mood: 'talk', links: [lk(`${BASE}#c-${c.cik}`, L(lg, 'Company page', '公司页'))] };
    }

    // why: the quarter's own analysis (written from the figures) and the lines that moved most against a year earlier
    async function why(c, lg, q0) {
      const d = await json(DATA + 'c/' + c.cik + '.json');
      const q = ((d && d.quarters) || [])[0];
      if (!q) return null;
      const s = String(q0 || '');
      const topic = /margin|profit|income|earnings|eps|cost|expense|利润|毛利|净利|成本|费用/i.test(s) ? 1 : /cash|现金/i.test(s) ? 2 : /revenue|sales|grow|营收|收入|增长/i.test(s) ? 0 : -1;
      const an = (q.analysis || []).filter(Boolean);
      const paras = topic >= 0 && an[topic] ? [an[topic]] : an.slice(0, 2);
      const CASHN = /cash|depreciation|share-based|stock-based|working capital|capital expend|amorti/i;
      const side = (n) => (topic === 0 ? n.color === 'rev' : topic === 1 ? (n.color === 'cost' || n.color === 'profit') && !CASHN.test(dec(n.name)) : topic === 2 ? CASHN.test(dec(n.name)) : true);
      const moved = (q.nodes || []).filter((n) => fin(n.v) && fin(n.y) && n.id !== 'revenue' && side(n)).map((n) => [n.name, n.v - n.y]).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 4);
      if (!paras.length && !moved.length) return null;
      const p = paras.map((x) => esc(x));
      if (moved.length) p.push(L(lg, 'Largest changes against a year earlier: ', '与去年同期相比变化最大的项目：') + moved.map(([k, v]) => `${nm(k)} ${v >= 0 ? '+' : '−'}${big(Math.abs(v)).replace('−', '')}`).join(', ') + '.');
      p.push(L(lg, 'These say what changed in the figures; the reasons are in the company\'s own words in the filing (click a line in the Sankey).', '以上说明数字发生了什么变化；原因请看申报中公司自己的说明（点击桑基图中的项目）。'));
      return { html: `<b>${esc(c.ticker)} · ${esc(q.label)}</b>: ` + p.join(' '), facts: [...paras, ...moved.map(([k, v]) => `${k} changed ${big(v)} year over year`)], mood: 'talk',
        links: [lk(`${BASE}#c-${c.cik}`, L(lg, 'The Sankey and the filing\'s notes', '桑基图与申报说明')), ...(q.doc_url ? [lk(q.doc_url, 'SEC')] : [])] };
    }

    // trend: the last quarters side by side with a small bar for each, or one quarter named in the question
    const BARS = '▁▂▃▄▅▆▇█';
    const spark = (vals) => { const ok = vals.filter(fin); if (!ok.length) return ''; const lo = Math.min(0, ...ok), hi = Math.max(...ok); return vals.map((v) => (fin(v) ? BARS[Math.round((v - lo) / ((hi - lo) || 1) * 7)] : ' ')).join(''); };
    async function trend(c, lg, q0) {
      const d = await json(DATA + 'c/' + c.cik + '.json');
      const qs = ((d && d.quarters) || []).filter((x) => x.headline && fin(x.headline.revenue));
      if (!qs.length) return null;
      const s = String(q0 || ''), want = (s.match(QLABEL) || [])[0];
      const norm = (x) => String(x || '').toUpperCase().replace(/\s+/g, '').replace(/'/g, '').replace(/FY20(\d\d)/, 'FY$1');
      const one = want && qs.find((x) => norm(x.label) === norm(want) || norm(x.label).replace(/^(Q\d)(\d{2})$/, '$1FY$2') === norm(want));
      if (want && one) {
        const h = one.headline, ya = qs.find((x) => x.end && one.end && Math.abs(Date.parse(one.end) - Date.parse(x.end) - 365 * 864e5) < 45 * 864e5);
        return { html: L(lg, `<b>${esc(c.ticker)} ${esc(one.label)}</b> (${esc(one.form)} filed ${esc(one.filed)}): revenue <b>${big(h.revenue)}</b>${fin(h.yoy) ? ` (${h.yoy >= 0 ? '+' : '−'}${num(Math.abs(h.yoy))}% Y/Y)` : ''}, operating margin ${fin(h.om) ? num(h.om, 1) + '%' : '—'}, net earnings ${big(h.ni)}, operating cash flow ${big(h.ocf)}${ya ? ` (a year earlier: revenue ${big(ya.headline.revenue)}, net ${big(ya.headline.ni)})` : ''}.`,
          `<b>${esc(c.ticker)} ${esc(one.label)}</b>（${esc(one.form)}，${esc(one.filed)} 提交）：营收 <b>${big(h.revenue)}</b>${fin(h.yoy) ? `（同比 ${h.yoy >= 0 ? '+' : '−'}${num(Math.abs(h.yoy))}%）` : ''}，营业利润率 ${fin(h.om) ? num(h.om, 1) + '%' : '—'}，净利润 ${big(h.ni)}，经营现金流 ${big(h.ocf)}${ya ? `（去年同期营收 ${big(ya.headline.revenue)}，净利润 ${big(ya.headline.ni)}）` : ''}。`),
          facts: [`${one.label}: revenue ${big(h.revenue)}, net ${big(h.ni)}`], mood: 'talk', links: [lk(`${BASE}#c-${c.cik}-${one.end}`, one.label)] };
      }
      const gm = (x) => { const r = (x.nodes || []).find((n) => n.id === 'revenue'), g = (x.nodes || []).find((n) => /^gross (profit|margin)/i.test(dec(n.name || ''))); return r && g && r.v > 0 ? 100 * g.v / r.v : null; };
      qs.forEach((x) => { x.headline = Object.assign({}, x.headline, { gm: gm(x) }); });
      const m = /gross|毛利/i.test(s) && qs.some((x) => fin(x.headline.gm)) ? 'gm' : /margin|利润率/i.test(s) ? 'om' : /net (income|earnings)|profit|净利|利润/i.test(s) ? 'ni' : /cash|现金/i.test(s) ? 'ocf' : 'revenue';
      const NAME = { revenue: ['Revenue', '营收'], ni: ['Net earnings', '净利润'], ocf: ['Operating cash flow', '经营现金流'], om: ['Operating margin', '营业利润率'], gm: ['Gross margin', '毛利率'] };
      const rows = qs.slice(0, 8).reverse(), vals = rows.map((x) => x.headline[m]);
      const f = (v) => (m === 'om' || m === 'gm' ? (fin(v) ? num(v, 1) + '%' : '—') : big(v));
      const first = vals.find(fin), last = vals[vals.length - 1];
      const html = L(lg, `<b>${esc(c.ticker)}</b> ${NAME[m][0].toLowerCase()}, last ${rows.length} quarters:`, `<b>${esc(c.ticker)}</b> 最近 ${rows.length} 个季度的${NAME[m][1]}：`)
        + `<div style="font:22px/1 monospace;letter-spacing:2px;margin:6px 0;color:var(--accent,#17734a)">${spark(vals)}</div>`
        + '<ul class="flo-list">' + rows.slice().reverse().map((x) => `<li>${esc(x.label)}: <b>${f(x.headline[m])}</b>${m === 'revenue' && fin(x.headline.yoy) ? ` · ${x.headline.yoy >= 0 ? '+' : '−'}${num(Math.abs(x.headline.yoy))}% Y/Y` : ''}</li>`).join('') + '</ul>'
        + (fin(first) && fin(last) && m !== 'om' && m !== 'gm' && first > 0 ? L(lg, `From ${f(first)} to ${f(last)} (${spc(last / first - 1, 0)}).`, `从 ${f(first)} 到 ${f(last)}（${spc(last / first - 1, 0)}）。`) : '');
      return { html, facts: rows.map((x) => `${x.label} ${NAME[m][0]} ${f(x.headline[m])}`), mood: 'talk', links: [lk(`${BASE}#c-${c.cik}-all`, L(lg, 'Every quarter', '所有季度'))] };
    }

    const SECTOR_ZH = { technology: '科技', financials: '金融', health: '医疗', 'consumer-disc': '可选消费', 'consumer-staples': '必需消费', energy: '能源', industrials: '工业',
      materials: '材料', utilities: '公用事业', communication: '通信', 'real-estate': '房地产', other: '其他' };
    async function profile(c, lg) {
      const d = await json(DATA + 'c/' + c.cik + '.json');
      const pr = (d && d.profile) || {}, it = (d && d.intro) || {};
      const text = String(it.text || '').replace(/\s+/g, ' ').trim(), two = (text.match(/[^.!?]+[.!?]+/g) || [text]).slice(0, 2).map((x) => x.trim()).join(' ').slice(0, 420);
      if (!text && !pr.industry) return null;
      const fye = /^\d{4}$/.test(pr.fye || '') ? ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][+pr.fye.slice(0, 2) - 1] + ' ' + +pr.fye.slice(2) : '';
      const meta = L(lg, [pr.industry && `SEC industry: ${esc(pr.industry)} (SIC ${esc(pr.sic)})`, (pr.exchanges || []).length && `listed on ${esc(pr.exchanges.join(', '))}`, fye && `fiscal year ends ${fye}`, pr.state && `incorporated in ${esc(pr.state)}`].filter(Boolean).join(' · '),
        [pr.industry && `SEC 行业：${esc(pr.industry)}（SIC ${esc(pr.sic)}）`, pr.sector && `板块：${esc(SECTOR_ZH[pr.sector] || pr.sector)}`, (pr.exchanges || []).length && `上市地：${esc(pr.exchanges.join('、'))}`, fye && `财年截止：${fye}`].filter(Boolean).join(' · '));
      const p = [];
      if (two) p.push(L(lg, `In its own words (${esc(it.source || 'annual report')}): “${esc(two)}”`, `公司自述（${esc(it.source || '年报')}）：“${esc(two)}”`));
      if (meta) p.push(meta + L(lg, '.', '。'));
      return { html: `<b>${esc(c.ticker)}</b> · ` + p.join(' '), facts: [two, meta].filter(Boolean), mood: 'talk', links: [lk(`${BASE}#c-${c.cik}`, L(lg, 'Company page', '公司页'))] };
    }

    async function multiples(c, lg) {
      const v = await json(HUB + 'research/valuation/c/' + c.cik + '.json');
      if (!v || !v.inputs) return null;
      const i = v.inputs, P = v.peers || {}, price = v.price;
      const pe = fin(price) && fin(i.eps) && i.eps > 0 ? price / i.eps : null;
      const row = (k, name, own) => { const x = P[k]; if (!x || !fin(own)) return ''; return L(lg, `${name} <b>${num(own, 1)}×</b> (industry median ${num(x.p50, 1)}×, middle half ${num(x.p25, 1)}–${num(x.p75, 1)}× across ${num(x.n)} companies)`, `${name} <b>${num(own, 1)} 倍</b>（行业中位数 ${num(x.p50, 1)} 倍，中间一半 ${num(x.p25, 1)}–${num(x.p75, 1)} 倍，共 ${num(x.n)} 家）`); };
      const lines = [row('pe', 'P/E', fin((P.pe || {}).own) ? P.pe.own : pe), row('ev_ebitda', 'EV/EBITDA', (P.ev_ebitda || {}).own), row('ev_sales', L(lg, 'EV/sales', 'EV/销售额'), (P.ev_sales || {}).own)].filter(Boolean);
      const p = [L(lg, `<b>${esc(c.ticker)}</b> ${usd(price)} (${esc(v.price_date || '')}): market value <b>${big(i.mcap)}</b>, enterprise value ${big(i.ev)}${fin(i.eps) ? `, trailing EPS $${num(i.eps, 2)}` : ''}.`,
        `<b>${esc(c.ticker)}</b> ${usd(price)}（${esc(v.price_date || '')}）：市值 <b>${big(i.mcap)}</b>，企业价值 ${big(i.ev)}${fin(i.eps) ? `，过去十二个月 EPS $${num(i.eps, 2)}` : ''}。`)];
      if (lines.length) p.push(lines.join(lg === 'zh' ? '；' : '; ') + L(lg, '.', '。'));
      const pp = P.pe || {};
      if (fin(pp.own) && fin(pp.p50)) p.push(pp.own > pp.p75 ? L(lg, 'On earnings it is priced above three quarters of its industry.', '按市盈率，它比行业里四分之三的公司都贵。') : pp.own < pp.p25 ? L(lg, 'On earnings it is priced below three quarters of its industry.', '按市盈率，它比行业里四分之三的公司都便宜。') : L(lg, 'On earnings it sits within the middle half of its industry.', '按市盈率，它处于行业中间一半的范围。'));
      return { html: p.join(' '), facts: [`price ${usd(price)} on ${v.price_date}`, `market cap ${big(i.mcap)}`, fin(pe) ? `P/E ${num(pe, 1)}` : ''].filter(Boolean), mood: 'talk',
        links: [lk(`${BASE}#c-${c.cik}-x-fairvalue`, L(lg, 'Fair value and multiples', '估值与倍数'))] };
    }

    async function debtLoad(c, lg) {
      const [v, d] = await Promise.all([json(HUB + 'research/valuation/c/' + c.cik + '.json'), json(DATA + 'c/' + c.cik + '.json')]);
      const i = (v && v.inputs) || {}, mat = ((((d && d.quality) || {}).cap) || {}).maturities;
      const debt = i.debt > 0 ? i.debt : mat && mat.ltd > 0 ? mat.ltd : null, cash = fin(i.cash) ? i.cash : mat && fin(mat.cash) ? mat.cash + (mat.sti || 0) : null;
      if (!fin(debt)) return fin(cash) ? { html: L(lg, `<b>${esc(c.ticker)}</b> holds ${big(cash)} of cash and short-term investments; its debt is not tagged in a way the site reads (finance arms and deposits are often reported apart). The balance sheet in the filing has it.`,
        `<b>${esc(c.ticker)}</b> 持有 ${big(cash)} 现金及短期投资；它的债务没有以网站能读取的方式标注（金融子公司和存款常单独列示），请看申报中的资产负债表。`), facts: [`cash ${big(cash)}`], mood: 'think', links: [lk(`${BASE}#c-${c.cik}-bs`, L(lg, 'Balance sheet', '资产负债表'))] } : null;
      const net = fin(debt) && fin(cash) ? debt - cash : null;
      const p = [L(lg, `<b>${esc(c.ticker)}</b> has <b>${big(debt)}</b> of debt and <b>${big(cash)}</b> of cash and short-term investments: ${fin(net) ? (net > 0 ? `net debt ${big(net)}` : `net cash ${big(-net)}`) : ''}${fin(net) && fin(i.ebitda) && i.ebitda > 0 && net > 0 ? `, ${num(net / i.ebitda, 1)}× a year's EBITDA` : ''}.`,
        `<b>${esc(c.ticker)}</b> 有 <b>${big(debt)}</b> 债务和 <b>${big(cash)}</b> 现金及短期投资：${fin(net) ? (net > 0 ? `净负债 ${big(net)}` : `净现金 ${big(-net)}`) : ''}${fin(net) && fin(i.ebitda) && i.ebitda > 0 && net > 0 ? `，相当于 ${num(net / i.ebitda, 1)} 年的 EBITDA` : ''}。`)];
      const b = ((mat && mat.buckets) || []).filter((x) => fin(x[1]) && x[1] > 0);
      if (b.length) p.push(L(lg, `Long-term debt falling due (${esc(mat.label)}): `, `长期债务到期（${esc(mat.label)}）：`) + b.map((x) => `${x[0] < 6 ? (mat.fy || 0) + x[0] : L(lg, 'later', '以后')} ${big(x[1])}`).join(', ') + L(lg, '.', '。'));
      return { html: p.join(' '), facts: [`debt ${big(debt)}, cash ${big(cash)}`, ...b.map((x) => `due year +${x[0]}: ${big(x[1])}`)], mood: fin(net) && fin(i.ebitda) && i.ebitda > 0 && net / i.ebitda > 4 ? 'worried' : 'talk',
        links: [lk(`${BASE}#c-${c.cik}-debt`, L(lg, 'Debt & rates', '债务与利率'))] };
    }

    /* ---------- the newer models: earnings quality, cash runway, what follows an 8-K, insider patterns, screens, a backtest ---------- */
    const slugOf = (c) => { const t = String(c.ticker || '').toLowerCase().replace(/\./g, '-'); return /^[a-z0-9-]{1,12}$/.test(t) ? t : 'cik-' + c.cik; };
    const qrows = async () => { const d = await json(DATA + 'quality-score.json'); if (!d || !d.fields) return null; const F = d.fields; return { n: d.n, rows: (d.rows || []).map((r) => Object.fromEntries(F.map((k, i) => [k, r[i]]))) }; };
    const GRADE_ZH = { A: '优', B: '良', C: '中', D: '差', E: '很差' };
    async function quality(c, lg) {
      const d = await qrows();
      if (!d) return null;
      const T = fileT(c.ticker), r = d.rows.find((x) => fileT(x.ticker) === T || String(x.cik) === String(c.cik));
      if (!r) return null;
      const lost = (r.lost || []).slice(0, 2).map(esc).join(lg === 'zh' ? '；' : '; '), won = (r.won || []).slice(0, 2).map(esc).join(lg === 'zh' ? '；' : '; ');
      const html = L(lg, `<b>${esc(c.ticker)}</b> scores <b>${num(r.score)} of 100</b> for earnings quality (grade ${esc(r.grade)}, rank ${num(r.rank)} of ${num(d.n)}): eight published measures of whether profit is backed by cash and free of the markers of managed earnings — accruals, discretionary accruals, Beneish M, Dechow F, Montier C, Piotroski F, the non-GAAP gap and smoothness.${lost ? ` It loses the most points on ${lost}.` : ''}${won ? ` Full marks for ${won}.` : ''} A statistical screen, not an audit${r.score < 50 ? '; fast growth lowers it by construction' : ''}.`,
        `<b>${esc(c.ticker)}</b> 盈余质量得分 <b>${num(r.score)}/100</b>（${esc(r.grade)} 级，${num(d.n)} 家中排第 ${num(r.rank)}）：由八项公开指标组成——应计项目、可操纵应计、Beneish M、Dechow F、Montier C、Piotroski F、非 GAAP 差距和利润平滑度，衡量利润是否有现金支撑、是否带有盈余管理的特征。${lost ? `失分最多的是：${lost}。` : ''}${won ? `得满分的是：${won}。` : ''}这是统计筛查，不是审计${r.score < 50 ? '；高增长本身会拉低分数' : ''}。`);
      return { html, facts: [`earnings quality score ${r.score}/100 grade ${r.grade} rank ${r.rank}/${d.n}`, ...(r.lost || []).map((x) => 'loses points: ' + x)], mood: r.score >= 65 ? 'happy' : r.score < 50 ? 'worried' : 'talk',
        links: [lk(`${BASE}c/${slugOf(c)}/earnings-quality/`, L(lg, 'Earnings quality score', '盈余质量评分')), lk(`${BASE}disclosures/#quality`, L(lg, 'Quality workbench', '质量工作台'))] };
    }
    MK.quality = async (lg, ix, q) => {
      const d = await qrows();
      if (!d) return null;
      const low = /lowest|worst|low|poor|flag|manipulat|cook|red flag|最差|最低|造假|操纵|风险/i.test(String(q || ''));
      const big = d.rows.filter((x) => true);
      const rows = (low ? big.slice().sort((a, b) => a.score - b.score) : big).slice(0, 8);
      const names = Object.fromEntries(((ix && ix.companies) || []).filter((x) => x.ticker).map((x) => [fileT(x.ticker), x]));
      return { html: L(lg, `${low ? 'Lowest' : 'Highest'} earnings quality scores (0–100, eight published measures):`, `盈余质量得分${low ? '最低' : '最高'}的公司（0–100，八项公开指标）：`)
        + ol(rows.map((r) => `${coLink(r.ticker, (names[fileT(r.ticker)] || {}).cik || r.cik)} ${num(r.score)} (${esc(r.grade)})${(r.lost || [])[0] && low ? L(lg, ` — ${esc(r.lost[0])}`, ` — ${esc(r.lost[0])}`) : ''}`)),
        facts: rows.map((r) => `${r.ticker} quality ${r.score} ${r.grade}`), mood: 'talk', links: [lk(`${BASE}disclosures/earnings-quality/`, L(lg, 'Every company ranked', '全部公司排名'))] };
    };
    const runwayOf = (c) => {
      const v = ((c.quality || {}).val) || {};
      const cash = fin(v.cash_all) ? v.cash_all : fin(v.b_cash) ? (v.b_cash || 0) + (v.b_sti || 0) : null;
      if (!fin(cash)) return null;
      const debt = fin(v.debt) ? v.debt : (v.b_ltd || 0) + (v.b_stb || 0);
      const fcf = fin(v.ocf) ? v.ocf - (fin(v.capex) ? Math.abs(v.capex) : 0) : null;
      const burn = fin(fcf) && fcf < 0 ? -fcf : null;
      const due = fin(v.b_ltd_c) ? (v.b_ltd_c || 0) + (v.b_stb || 0) : null;
      return { cash, debt, fcf, burn, months: burn ? 12 * cash / burn : null, due, ocf: v.ocf, end: v.end };
    };
    async function runway(c, lg) {
      const d = await json(DATA + 'c/' + c.cik + '.json');
      const r = d ? runwayOf(d) : null;
      if (!r) return null;
      const yrs = (m) => (m >= 24 ? L(lg, `${num(m / 12, 1)} years`, `${num(m / 12, 1)} 年`) : L(lg, `${num(m)} months`, `${num(m)} 个月`));
      const html = r.burn
        ? L(lg, `<b>${esc(c.ticker)}</b> ${r.ocf < 0 ? 'is burning cash: operations consumed' : 'spends more on capital than operations bring in:'} free cash flow of <b>${big(-r.burn)}</b> over the trailing twelve months against <b>${big(r.cash)}</b> of cash and investments — a runway of about <b>${yrs(r.months)}</b> at that rate, before any new financing${fin(r.due) && r.due > 0 ? `; ${big(r.due)} of debt comes due within a year${r.cash >= r.due + r.burn ? ', which the cash covers' : ', which would need refinancing'}` : ''}.`,
          `<b>${esc(c.ticker)}</b> ${r.ocf < 0 ? '在烧钱：经营活动消耗现金，' : '资本开支超过经营现金流：'}过去十二个月自由现金流 <b>${big(-r.burn)}</b>，账上现金及投资 <b>${big(r.cash)}</b}——按此速度现金跑道约 <b>${yrs(r.months)}</b>（不计新融资）${fin(r.due) && r.due > 0 ? `；一年内到期债务 ${big(r.due)}${r.cash >= r.due + r.burn ? '，现金足以覆盖' : '，需要再融资'}` : ''}。`)
        : L(lg, `<b>${esc(c.ticker)}</b> funds itself: free cash flow of <b>${big(r.fcf)}</b> over the trailing twelve months, <b>${big(r.cash)}</b> of cash and investments against ${r.debt ? `<b>${big(r.debt)}</b> of debt` : 'no debt'}${fin(r.due) && r.due > 0 ? ` (${big(r.due)} due within a year, ${num(r.cash / r.due, 1)}× covered)` : ''}. No runway question arises while it generates cash.`,
          `<b>${esc(c.ticker)}</b> 能自我造血：过去十二个月自由现金流 <b>${big(r.fcf)}</b>，账上现金及投资 <b>${big(r.cash)}</b>，${r.debt ? `债务 <b>${big(r.debt)}</b>` : '没有债务'}${fin(r.due) && r.due > 0 ? `（一年内到期 ${big(r.due)}，现金覆盖 ${num(r.cash / r.due, 1)} 倍）` : ''}。只要持续产生现金，就不存在跑道问题。`);
      return { html: html.replace('</b}', '</b>'), facts: [`cash ${big(r.cash)}, debt ${big(r.debt)}, FCF ttm ${big(r.fcf)}` + (r.months ? `, runway ${num(r.months)} months` : '')], mood: r.months != null && r.months < 12 ? 'worried' : 'talk',
        links: [lk(`${BASE}c/${slugOf(c)}/cash-flow/#runway`, L(lg, 'Cash runway & debt wall', '现金跑道与债务到期')), lk(`${BASE}disclosures/cash-runway/`, L(lg, 'Who is burning cash', '谁在烧钱'))] };
    }
    MK.runway = async (lg, ix) => {
      const d = await json(HUB + 'screener.json');
      if (!d || !d.fields) return null;
      const F = d.fields, rows = d.rows.map((r) => Object.fromEntries(F.map((k, i) => [k, r[i]]))).filter((r) => fin(r.runway_months) && (r.mcap || 0) >= 3e8).sort((a, b) => a.runway_months - b.runway_months).slice(0, 8);
      if (!rows.length) return null;
      return { html: L(lg, 'Shortest cash runway at the current burn (market value $300M+):', '按当前烧钱速度现金跑道最短的公司（市值 3 亿美元以上）：') + ol(rows.map((r) => `${coLink(r.ticker, r.cik)} ${r.runway_months >= 24 ? num(r.runway_months / 12, 1) + L(lg, ' yrs', ' 年') : num(r.runway_months) + L(lg, ' mo', ' 个月')} · ${L(lg, 'cash', '现金')} ${big(r.cash)}`)),
        facts: rows.map((r) => `${r.ticker} runway ${r.runway_months} months`), mood: 'worried', links: [lk(`${BASE}disclosures/cash-runway/`, L(lg, 'Cash runway, every company', '现金跑道榜'))] };
    };
    const ITEM_ZH = { '1.01': '重大协议', '1.02': '协议终止', '2.01': '完成收购或处置', '2.02': '业绩公告', '2.03': '新增债务', '2.05': '退出成本', '2.06': '资产减值', '3.01': '退市通知', '3.02': '非注册股权发行', '4.01': '更换审计师', '4.02': '财务重述', '5.01': '控制权变更', '5.02': '高管董事变动', '5.03': '章程修订', '5.07': '股东投票结果', '8.01': '其他事项' };
    const sp = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(100 * v), 1)}%`;
    MK.afterEvent = async (lg, ix, q) => {
      const d = await json(DATA + 'event-stats.json');
      if (!d || !d.items) return null;
      const m = /(\d\.\d\d)/.exec(String(q || ''));
      const items = Object.entries(d.items).filter(([, s]) => s.h1 && s.h1.n >= 30);
      if (m && d.items[m[1]] && d.items[m[1]].h1) {
        const s = d.items[m[1]], k = m[1];
        return { html: L(lg, `After an 8-K reporting Item ${esc(k)} (${esc(s.name || '')}), across <b>${num(s.h1.n)}</b> filings: the stock's median move the next session was <b>${sp(s.h1.median)}</b> (typical size ±${num(100 * s.h1.abs_median, 1)}%, up ${num(100 * s.h1.up)}% of the time)${s.h21 ? `; over 21 sessions ${sp(s.h21.median)}` : ''}. Measured from the close before the filing reached EDGAR; descriptive, not predictive.`,
          `报告 Item ${esc(k)}（${esc(ITEM_ZH[k] || s.name || '')}）的 8-K 之后，统计 <b>${num(s.h1.n)}</b> 份：次日股价中位数变动 <b>${sp(s.h1.median)}</b>（典型幅度 ±${num(100 * s.h1.abs_median, 1)}%，上涨概率 ${num(100 * s.h1.up)}%）${s.h21 ? `；21 个交易日后 ${sp(s.h21.median)}` : ''}。从公告送达 EDGAR 前的收盘算起；描述历史，不是预测。`),
          facts: [`item ${k}: n ${s.h1.n}, next-session median ${sp(s.h1.median)}, abs ${num(100 * s.h1.abs_median, 1)}%, up ${num(100 * s.h1.up)}%`], mood: 'talk', links: [lk(`${BASE}events/impact/`, L(lg, 'Every 8-K item scored', '各类 8-K 影响'))] };
      }
      const rows = items.sort((a, b) => b[1].h1.abs_median - a[1].h1.abs_median).slice(0, 7);
      return { html: L(lg, `Which 8-K items move stocks most, by the typical next-session move across ${num(d.events)} filings:`, `哪类 8-K 最能推动股价（${num(d.events)} 份公告，次日典型幅度）：`)
        + ol(rows.map(([k, s]) => `Item ${esc(k)} ${esc(lg === 'zh' ? ITEM_ZH[k] || s.name || '' : s.name || '')}: ±${num(100 * s.h1.abs_median, 1)}%, ${L(lg, 'median', '中位数')} ${sp(s.h1.median)}, ${L(lg, 'up', '上涨')} ${num(100 * s.h1.up)}%`)),
        facts: rows.map(([k, s]) => `item ${k} abs ${num(100 * s.h1.abs_median, 1)}% median ${sp(s.h1.median)}`), mood: 'talk', links: [lk(`${BASE}events/impact/`, L(lg, 'Every 8-K item scored', '各类 8-K 影响'))] };
    };
    MK.insiderSignal = async (lg) => {
      const d = await json(DATA + 'insider-stats.json');
      const p = d && d.patterns;
      if (!p || !p.buy) return null;
      const line = (k) => (p[k] ? `${esc(p[k].label)}: ${L(lg, 'right', '正确')} ${num(100 * p[k].hit)}%, ${L(lg, 'median excess', '超额中位数')} ${sp(p[k].median_excess)} (${num(p[k].n)})` : '');
      return { html: L(lg, `Do insider trades predict the stock? Over ${num(d.trades)} scored Form 4 trades (the stock against SPY over the next 63 sessions): buys beat the market <b>${num(100 * p.buy.hit)}%</b> of the time, sales were followed by a lagging stock <b>${num(100 * p.sell.hit)}%</b> of the time. By pattern:`,
        `内部人交易准不准？统计 ${num(d.trades)} 笔已评分的 Form 4 交易（之后 63 个交易日相对 SPY）：买入后跑赢大盘的概率 <b>${num(100 * p.buy.hit)}%</b>，卖出后跑输的概率 <b>${num(100 * p.sell.hit)}%</b>。分模式看：`)
        + ol(['buy_large', 'buy_mid', 'buy_small', 'buy_cluster', 'buy_repeat', 'sell_large'].map(line).filter(Boolean)),
        facts: Object.values(p).map((x) => `${x.label}: hit ${x.hit}, median excess ${x.median_excess}, n ${x.n}`), mood: 'talk', links: [lk(`${BASE}disclosures/insider-signals/`, L(lg, 'Every insider pattern scored', '内部人信号全表'))] };
    };
    const PRESET_RX = [['insiders-buying', /insider/i], ['momentum', /momentum|strong|rising|动量|强势/i], ['short-squeeze', /short|squeeze|空头|轧空/i], ['distress', /distress|bankrupt|run(ning)? out|burn|困境|破产|烧钱/i],
      ['cash-machines', /cash (machine|cow|rich)|free cash|buyback|dividend|现金牛|分红|回购/i], ['quality-growth', /quality growth|growth|growing|high.?quality|优质|成长/i], ['fallen-leaders', /fallen|beaten|down \d+|from (its |the )?high|cheap|回调|跌了|低位/i],
      ['smart-money-inflows', /13-?f|funds?|institution|smart money|机构|聪明钱/i], ['low-quality-earnings', /low.?quality|manipulat|beneish|red flag|造假|低质量/i], ['earnings-this-week', /earnings|report|this week|财报|本周/i]];
    MK.screen = async (lg, ix, q) => {
      const d = await json(HUB + 'screener.json');
      if (!d || !d.presets) return null;
      const hit = PRESET_RX.find(([, rx]) => rx.test(String(q || '')));
      const names = Object.fromEntries(((ix && ix.companies) || []).filter((x) => x.ticker).map((x) => [fileT(x.ticker), x]));
      if (hit) {
        const p = d.presets.find((x) => x.key === hit[0]);
        if (p) {
          const ts = p.tickers.slice(0, 10);
          return { html: L(lg, `<b>${esc(p.title)}</b> — ${esc(p.line)} ${num(p.tickers.length)} companies pass today${ts.length ? ', the first ' + ts.length + ':' : '.'}`, `<b>${esc(p.title)}</b>——${esc(p.line)} 今天有 ${num(p.tickers.length)} 家公司通过${ts.length ? '，前 ' + ts.length + ' 家：' : '。'}`)
            + (ts.length ? ' ' + ts.map((t) => coLink(t, (names[t] || {}).cik)).join(', ') : ''),
            facts: [`screen ${p.key}: ${p.tickers.length} pass; ${ts.join(' ')}`], mood: 'talk', links: [lk(`${BASE}disclosures/#screener/${p.key}`, L(lg, 'Open this screen live', '打开实时筛选')), lk(`${BASE}disclosures/screener/`, L(lg, 'All preset screens', '全部预设筛选'))] };
        }
      }
      return { html: L(lg, `The screener holds ${num(d.rows.length)} companies and ${num(d.fields.length - 6)} fields from the filings — growth, margins, cash flow and yields, Piotroski, Altman and Beneish, the quality score, the next report, 13F and insider flows, short interest, cash and runway. Preset screens:`, `筛选器收录 ${num(d.rows.length)} 家公司、${num(d.fields.length - 6)} 个来自财报的字段——增长、利润率、现金流与收益率、Piotroski、Altman、Beneish、质量评分、下次财报、13F 与内部人资金流、空头、现金与跑道。预设筛选：`)
        + ol(d.presets.map((p) => `<a href="${esc(BASE)}disclosures/#screener/${esc(p.key)}">${esc(p.title)}</a> (${num(p.tickers.length)})`)),
        facts: d.presets.map((p) => `${p.key}: ${p.tickers.length}`), mood: 'talk', links: [lk(`${BASE}disclosures/#screener`, L(lg, 'Open the screener', '打开筛选器'))] };
    };
    // "$10,000 in NVDA in January 2024": the daily closes decoded as the backtest page does
    const decodeMoves = (doc) => { if (!doc || !doc.last) return null; let days; if (doc.dates) days = doc.dates.slice(); else { const d = new Date(doc.d0 + 'T00:00:00Z'); days = [doc.d0]; for (const ch of doc.gaps || '') { d.setUTCDate(d.getUTCDate() + parseInt(ch, 36)); days.push(d.toISOString().slice(0, 10)); } } const r = doc.r || [], n = Math.min(days.length, r.length + 1), px = new Array(n); let s = 0; for (let i = n - 1; i >= 0; i--) { px[i] = doc.last * Math.exp(-s); if (i > 0) s += r[i - 1] / 1e4; } return { days: days.slice(0, n), px, asOf: doc.as_of }; };
    const MON = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
    function whenAsked(q) {
      const s = String(q || '');
      let m = /(\d{4})-(\d{2})-(\d{2})/.exec(s);
      if (m) return m[0];
      m = /(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? ?(\d{1,2})?,? ?(20\d\d)/i.exec(s);
      if (m) return `${m[3]}-${String(MON[m[1].slice(0, 3).toLowerCase()]).padStart(2, '0')}-${String(m[2] || 1).padStart(2, '0')}`;
      m = /(20\d\d)年(?:(\d{1,2})月)?(?:(\d{1,2})[日号])?/.exec(s);
      if (m) return `${m[1]}-${String(m[2] || 1).padStart(2, '0')}-${String(m[3] || 1).padStart(2, '0')}`;
      m = /\b(20[12]\d)\b/.exec(s);
      if (m) return `${m[1]}-01-01`;
      m = /(\d+)\s*(years?|yrs?|年)\s*(ago|前)/i.exec(s) || /(ago|前).{0,3}(\d+)\s*(years?|yrs?|年)/i.exec(s);
      if (m) { const n = +(m[1] || m[2]); const d = new Date(); d.setUTCFullYear(d.getUTCFullYear() - n); return d.toISOString().slice(0, 10); }
      return null;
    }
    const amountAsked = (q) => { const m = /\$ ?([\d,]+(?:\.\d+)?)\s*(k|m|万|千)?|([\d,]+(?:\.\d+)?)\s*(k|万|千)?\s*(美元|dollars|usd|块)/i.exec(String(q || '')); if (!m) return 10000; const v = parseFloat((m[1] || m[3] || '').replace(/,/g, '')), u = (m[2] || m[4] || '').toLowerCase(); return v * (u === 'k' || u === '千' ? 1e3 : u === 'm' ? 1e6 : u === '万' ? 1e4 : 1) || 10000; };
    async function backtest(c, lg, q) {
      const T = fileT(c.ticker);
      const [a, b] = await Promise.all([json(HUB + 'research/paths/moves/a/' + encodeURIComponent(T) + '.json'), json(HUB + 'research/paths/moves/a/SPY.json')]);
      const S = decodeMoves(a), B = decodeMoves(b);
      if (!S) return null;
      let from = whenAsked(q) || S.days[Math.max(0, S.days.length - 252)];
      if (from < S.days[0]) from = S.days[0];
      const amt = amountAsked(q);
      const at = (X, d) => { let lo = 0, hi = X.days.length; while (lo < hi) { const m = (lo + hi) >> 1; if (X.days[m] < d) lo = m + 1; else hi = m; } return lo; };
      const i0 = at(S, from);
      if (i0 >= S.days.length - 1) return null;
      const end = amt * S.px[S.px.length - 1] / S.px[i0], ret = end / amt - 1;
      const yrs = (Date.parse(S.days[S.days.length - 1]) - Date.parse(S.days[i0])) / (365.25 * 864e5);
      const cagr = yrs > 0.5 ? Math.pow(end / amt, 1 / yrs) - 1 : null;
      let bench = '';
      if (B) { const j = at(B, S.days[i0]); if (j < B.px.length - 1) { const be = amt * B.px[B.px.length - 1] / B.px[j]; bench = L(lg, ` The same money in SPY: <b>${big(be)}</b> (${sp(be / amt - 1)}), so ${esc(c.ticker)} is ${end >= be ? 'ahead' : 'behind'} by ${big(Math.abs(end - be))}.`, ` 同样的钱买 SPY：<b>${big(be)}</b>（${sp(be / amt - 1)}），${esc(c.ticker)} ${end >= be ? '领先' : '落后'} ${big(Math.abs(end - be))}。`); } }
      const html = L(lg, `<b>${big(amt)}</b> in <b>${esc(c.ticker)}</b> on ${esc(day(S.days[i0]))} at ${'$' + num(S.px[i0], 2)} a share would be <b>${big(end)}</b> at the ${esc(day(S.days[S.days.length - 1]))} close (${sp(ret)}${cagr != null ? `, ${sp(cagr)} a year` : ''}), prices as traded, dividends not counted.${bench}`,
        `${esc(day(S.days[i0]))} 以每股 ${'$' + num(S.px[i0], 2)} 买入 <b>${big(amt)}</b> 的 <b>${esc(c.ticker)}</b>，到 ${esc(day(S.days[S.days.length - 1]))} 收盘值 <b>${big(end)}</b>（${sp(ret)}${cagr != null ? `，年化 ${sp(cagr)}` : ''}），按交易价格计算，不含股息。${bench}`);
      return { html, facts: [`${big(amt)} in ${c.ticker} on ${S.days[i0]} → ${big(end)} (${sp(ret)})`], mood: ret > 0 ? 'happy' : 'worried', links: [lk(`${BASE}#backtest/t=${encodeURIComponent(T)}&from=${S.days[i0]}&amt=${Math.round(amt)}`, L(lg, 'The path, with every disclosure marked', '完整路径与每次披露')), lk(`${BASE}c/${slugOf(c)}/timeline/`, L(lg, 'Timeline', '时间线'))] };
    }

    MK.sectors = async (lg) => {
      const d = await json(HUB + 'market/rotation.json');
      if (!d || !d.fields || !d.sectors) return null;
      const ix = Object.fromEntries(d.fields.map((f, i) => [f, i]));
      const rows = Object.entries(d.sectors).map(([id, s]) => { const x = (s.p || []).filter((r) => r && fin(r[ix.rs])).pop(); return x ? [id, s.name || id, x] : null; }).filter(Boolean).sort((a, b) => b[2][ix.rs] - a[2][ix.rs]);
      if (rows.length < 4) return null;
      const lab = (r) => (lg === 'zh' ? SECTOR_ZH[r[0]] || r[1] : r[1]), q = rows[0][2][ix.cal];
      const fmt = (r) => `${esc(lab(r))} ${num(r[2][ix.rs])}${fin(r[2][ix.revg]) ? L(lg, ` (revenue ${r[2][ix.revg] >= 0 ? '+' : '−'}${num(Math.abs(r[2][ix.revg]))}% Y/Y)`, `（营收同比 ${r[2][ix.revg] >= 0 ? '+' : '−'}${num(Math.abs(r[2][ix.revg]))}%）`) : ''}`;
      return { html: L(lg, `Sectors in ${esc(q)}, strongest against the market first (relative strength, 1–99):`, `${esc(q)} 各板块，按相对大盘强弱排序（1–99）：`) + ol(rows.map(fmt)),
        facts: rows.map((r) => `${r[1]} relative strength ${r[2][ix.rs]}`), mood: 'talk', links: [lk(`${BASE}disclosures/sector-rotation/`, L(lg, 'Sector rotation', '板块轮动'))] };
    };

    return { owners, insiders, congress, events, cashflow, segments, nextEarnings, ties, shorts, moves, guidanceRecord, investments, brief, why, trend, profile, multiples, debtLoad, quality, runway, backtest, MK, STAKES };
  }

  /* ---------- the next questions under an answer ---------- */
  const REL = { profile: ['segments', 'brief', 'ties'], multiples: ['valuation', 'analysts', 'trend'], debtLoad: ['cashflow'], brief: ['why', 'nextEarnings', 'owners'], why: ['trend', 'segments', 'cashflow'], trend: ['why', 'segments', 'nextEarnings'], valuation: ['analysts', 'nextEarnings', 'cashflow'], earnings: ['segments', 'cashflow', 'nextEarnings'], segments: ['ties', 'earnings'], cashflow: ['credit', 'valuation'],
    owners: ['insiders', 'congress', 'shorts'], insiders: ['owners', 'events'], congress: ['owners', 'insiders'], events: ['moves', 'earnings'], nextEarnings: ['guidanceRecord', 'options', 'segments'],
    ties: ['segments', 'industry'], shorts: ['options', 'moves', 'owners'], moves: ['events', 'opportunity'], rotation: ['industry', 'moves'], options: ['moves', 'nextEarnings'],
    credit: ['cashflow', 'valuation'], analysts: ['valuation', 'nextEarnings'], opportunity: ['rotation', 'moves'], guidanceRecord: ['nextEarnings', 'calls'], investments: ['owners', 'cashflow'],
    filings: ['events', 'earnings'], industry: ['rotation', 'ties'], calls: ['guidanceRecord', 'nextEarnings'], quality: ['cashflow', 'why', 'runway'], runway: ['debtLoad', 'cashflow', 'quality'], backtest: ['moves', 'insiders', 'nextEarnings'] };
  const ASK = { profile: ['What does {t} do?', '{t} 是做什么的？'], multiples: ['{t} P/E and market cap', '{t} 市盈率和市值'], debtLoad: ['How much debt does {t} have?', '{t} 有多少负债？'], brief: ['Brief me on {t}', '{t} 速览'], why: ['Why did {t}\'s results change?', '{t} 业绩为什么变化？'], trend: ['{t} revenue trend', '{t} 营收趋势'], segments: ['How does {t} make money?', '{t} 怎么赚钱？'], cashflow: ['{t} free cash flow', '{t} 自由现金流'], nextEarnings: ['When does {t} report next?', '{t} 下次财报什么时候？'],
    owners: ['Who owns {t}?', '谁持有 {t}？'], insiders: ['Are {t} insiders buying?', '{t} 内部人在买还是卖？'], congress: ['Congress trades in {t}', '国会议员交易 {t}'],
    events: ['{t} latest 8-K', '{t} 最新 8-K'], ties: ['{t} customers and suppliers', '{t} 的客户和供应商'], shorts: ['{t} short interest', '{t} 空头仓位'],
    moves: ['How rare is {t}\'s latest move?', '{t} 最近的涨跌有多罕见？'], guidanceRecord: ['Does {t} meet its guidance?', '{t} 的指引兑现率'], investments: ['{t} investment gains', '{t} 投资收益'],
    valuation: ['What is {t} worth?', '{t} 值多少钱？'], earnings: ['{t} latest earnings', '{t} 最新财报'], credit: ['{t} debt and default risk', '{t} 的债务和违约风险'],
    analysts: ['{t} analyst price target', '{t} 分析师目标价'], options: ['{t} options: range and max pain', '{t} 期权隐含区间'], rotation: ['Will {t} be Leading next week?', '{t} 下周会进入领先吗？'],
    industry: ['How is {t}\'s industry rotating?', '{t} 所在行业轮动'], opportunity: ['Will {t} go up or down next month?', '{t} 下个月会涨吗？'], calls: ['{t} earnings call guidance', '{t} 电话会议指引'],
    quality: ['{t} earnings quality score', '{t} 盈余质量评分'], runway: ['How long can {t}\'s cash last?', '{t} 的现金能撑多久？'], backtest: ['If I had bought {t} a year ago?', '一年前买 {t} 现在值多少？'] };
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
    ['guidanceRecord', 'Who raised guidance lately?', '最近谁上调了指引？'], ['sectors', 'Which sectors are leading?', '哪些板块最强？'],
    ['quality', 'Lowest earnings quality scores', '盈余质量最差的公司'], ['screen', 'Find stocks with insiders buying', '找内部人在买的股票'], ['afterEvent', 'Which 8-K items move stocks?', '哪类公告最能推动股价？'], ['insiderSignal', 'Do insider trades predict the stock?', '跟着内部人买靠谱吗？'], ['runway', 'Who is running out of cash?', '哪些公司快没现金了？']];

  const marketWords = (q) => MARKET.test(String(q || ''));
  const API = { glossary, GLOSSARY, QLABEL, classify, merge, isMarket, marketWords, isFollow, fuzzyCompany, make, followUps, MARKET_ASK, INTENTS, lev };
  root.FFFloInsights = API;
  if (typeof module !== 'undefined') module.exports = API;
})(typeof window !== 'undefined' ? window : globalThis);
