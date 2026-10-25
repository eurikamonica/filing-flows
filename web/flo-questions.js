/* Flo's question bank (web/mascot.js reads it).
   default   questions Flo suggests, by topic; {t} is the page's company ticker. Each page leads with its own topic and
             rotates through the list ("More questions" shows the next set), so add as many as you like.
   examples  ways people ask that Flo must understand (no ticker): tests/test_mascot.cjs checks that every default
             question and every example is classified to its topic. Add a phrasing here when Flo misses one, then widen
             the topic's pattern in mascot.js until the test passes.
   Topics: filings, valuation, rotation, industry, options, earnings, credit, analysts — the answers mascot.js can write. */
(function (root) {
  'use strict';
  const BANK = {
    filings: {
      default: {
        en: [
          '{t} latest SEC filing', 'What is the latest filing for {t}?',
          'Show {t} recent SEC submissions', '{t} most recent EDGAR filing',
          'Where can I read {t} latest SEC report?', '{t} most recent SEC document'
        ],
        zh: [
          '{t} 最新 SEC 申报', '{t} 最近一次披露是什么？',
          '{t} 最近的 SEC 文件', '{t} 最新的 SEC 申报',
          '{t} 最近一次 SEC 提交', '{t} 的最新 EDGAR 文件'
        ]
      },
      examples: {
        en: ['latest filing', 'latest filling', 'last SEC filing', 'recent SEC submissions',
          'most recent EDGAR filing', 'newest SEC document'],
        zh: ['最新申报', '最新 SEC 文件', '最近披露', '最近一次 SEC 提交', '最新 SEC 申报', '最新 EDGAR']
      }
    },
    valuation: {
      default: {
        en: ['What is {t} worth?', '{t} DCF and Monte Carlo', 'Is {t} undervalued?', 'Is {t} overvalued?', "What's {t}'s fair value?", 'How much upside does {t} have?',
          'What does {t} price in for growth?', '{t} intrinsic value', 'Is {t} cheap or expensive?', '{t} valuation range', 'How likely is {t} worth more than its price?', '{t} margin of safety'],
        zh: ['{t} 值多少钱？', '{t} 的 DCF 和蒙特卡洛估值', '{t} 被低估了吗？', '{t} 被高估了吗？', '{t} 的合理价值是多少？', '{t} 还有多少上涨空间？',
          '{t} 的股价为增长付了多少？', '{t} 的内在价值', '{t} 现在贵还是便宜？', '{t} 的估值区间', '{t} 价值高于股价的概率有多大？', '{t} 的安全边际'],
      },
      examples: {
        en: ['what is it worth', 'fair value', 'is it cheap', 'too expensive?', 'overvalued or undervalued', 'dcf', 'intrinsic value please', 'how much upside', 'margin of safety', 'monte carlo value', 'pvgo', 'should I buy'],
        zh: ['值多少', '估值', '贵不贵', '便宜吗', '低估还是高估', '合理价', '内在价值', '上涨空间', '下跌空间', '安全边际', '蒙特卡洛', '值得买吗'],
      },
    },
    rotation: {
      default: {
        en: ['Will {t} be Leading next week?', "Where will {t}'s quadrant be in 4 weeks?", 'What price puts {t} into Leading?', 'Is {t} outperforming the S&P 500?', '{t} RRG quadrant',
          "{t} relative strength vs SPY", 'What close drops {t} into Lagging?', '{t} momentum against the market', '{t} Markov odds 4 weeks out', 'Is {t} improving or weakening?'],
        zh: ['{t} 下周会进入领先象限吗？', '{t} 4 周后在哪个象限？', '{t} 涨到多少能进入领先？', '{t} 跑赢标普了吗？', '{t} 的 RRG 象限',
          '{t} 相对 SPY 的相对强弱', '{t} 跌到多少会落入落后象限？', '{t} 相对大盘的动量', '{t} 4 周后的马尔科夫概率', '{t} 在改善还是转弱？'],
      },
      examples: {
        en: ['rrg', 'which quadrant', 'leading or lagging', 'next week', 'relative strength', 'is it outperforming', 'momentum', 'rs-ratio', 'markov odds', 'rotation'],
        zh: ['象限', '轮动', '领先还是落后', '下周', '相对强弱', '跑赢大盘吗', '跑输', '动量', '马尔科夫', '强于大盘吗'],
      },
    },
    industry: {
      default: {
        en: ["How is {t}'s industry rotating?", "Is {t}'s industry Leading?", "{t}'s industry vs the S&P 500", "What does {t}'s industry need to be Leading?", "{t} peers' quadrant", "Is {t}'s sector lagging?"],
        zh: ['{t} 所在行业轮动', '{t} 所在行业处于哪个象限？', '{t} 的行业相对标普 500 怎么样？', '{t} 所在行业要涨多少才能领先？', '{t} 同业现在在哪个象限？', '{t} 所在板块落后了吗？'],
      },
      examples: {
        en: ['its industry', 'the sector', 'how are its peers doing', 'industry rotation', 'industry index'],
        zh: ['行业', '板块怎么样', '同业', '行业轮动', '行业指数'],
      },
    },
    options: {
      default: {
        en: ['{t} options: range and max pain', '{t} put wall and call wall', "{t}'s implied move this month", "What range do {t}'s options price in?", '{t} max pain', '{t} 95% option range',
          "Where are {t}'s option walls?", '{t} implied volatility range'],
        zh: ['{t} 期权的隐含区间和最大痛点', '{t} 期权的 put wall 和 call wall', '{t} 本月期权隐含波动区间', '{t} 期权定价的价格区间是多少？', '{t} 的最大痛点', '{t} 期权 95% 区间',
          '{t} 的看涨墙和看跌墙在哪？', '{t} 隐含波动率区间'],
      },
      examples: {
        en: ['options', 'max pain', 'call wall', 'put wall', 'implied move', 'implied volatility', 'iv', 'expected move', 'option range', 'strike'],
        zh: ['期权', '最大痛点', '看涨墙', '看跌墙', '隐含波动', '隐含区间', '预期波动', '行权价', '到期日区间'],
      },
    },
    earnings: {
      default: {
        en: ['{t} latest earnings', '{t} revenue growth and margin', 'How did {t} do last quarter?', "{t}'s operating margin", '{t} net income', '{t} operating cash flow', 'Is {t} growing year on year?', "{t}'s latest 10-Q"],
        zh: ['{t} 最新财报', '{t} 营收增长和利润率', '{t} 上季度表现如何？', '{t} 的营业利润率', '{t} 的净利润', '{t} 的经营现金流', '{t} 同比在增长吗？', '{t} 最新的 10-Q'],
      },
      examples: {
        en: ['earnings', 'last quarter', 'revenue', 'sales growth', 'profit', 'margin', 'eps', 'net income', 'cash flow', 'year over year', '10-q', '10-k'],
        zh: ['财报', '业绩', '营收', '收入', '利润', '毛利', '净利', '现金流', '季度', '同比', '年报', '季报'],
      },
    },
    credit: {
      default: {
        en: ['{t} debt and default risk', '{t} Altman Z and credit spread', 'Is {t} at risk of bankruptcy?', "{t}'s distance to default", 'How safe is {t}\'s debt?', '{t} leverage and solvency'],
        zh: ['{t} 的债务和违约风险', '{t} 的信用利差和 Altman Z', '{t} 有破产风险吗？', '{t} 的违约距离', '{t} 的债务安全吗？', '{t} 的杠杆和偿债能力'],
      },
      examples: {
        en: ['debt', 'credit risk', 'default', 'bankruptcy', 'altman z', 'distress', 'solvency', 'leverage', 'credit spread'],
        zh: ['债务', '违约', '信用', '破产', '偿债', '杠杆', '信用利差', '违约距离'],
      },
    },
    analysts: {
      default: {
        en: ['{t} analyst price target', '{t} Polymarket implied price', 'What does Wall Street think of {t}?', "{t}'s consensus target", "How far is {t} from analysts' targets?", '{t} analyst target range'],
        zh: ['{t} 分析师目标价', '{t} 预测市场隐含价格', '华尔街怎么看 {t}？', '{t} 的一致预期目标价', '{t} 离分析师目标价还有多远？', '{t} 分析师目标价区间'],
      },
      examples: {
        en: ['analysts', 'price target', 'target price', 'consensus', 'wall street', 'polymarket', 'kalshi', 'analyst rating'],
        zh: ['分析师', '目标价', '一致预期', '华尔街', '预测市场', '评级'],
      },
    },
  };
  // round 2 additions, merged into the lists above (keep adding here or above; both are read)
  const MORE = {
    valuation: {
      default: {
        en: ['Is {t} a buy at this price?', 'What would {t} be worth with slower growth?', "How does {t}'s DCF compare with its price?", "What's the bull case value for {t}?",
          "What's the bear case value for {t}?", 'How much of {t}\'s price is for future growth?', 'Which valuation method fits {t}?', '{t} stage-weighted value',
          'Is {t} fairly valued?', "What is {t}'s downside to fair value?", '{t} value per share', 'How does {t} compare with its fair value range?'],
        zh: ['{t} 现在这个价格值得买吗？', '{t} 增长放缓的话值多少？', '{t} 的 DCF 和股价比怎么样？', '{t} 乐观情形的估值是多少？',
          '{t} 悲观情形的估值是多少？', '{t} 的股价有多少是为未来增长付费？', '哪种估值方法适合 {t}？', '{t} 的阶段加权估值',
          '{t} 估值合理吗？', '{t} 离合理价值还有多少下跌空间？', '{t} 每股价值是多少？', '{t} 现价在估值区间的什么位置？'],
      },
      examples: {
        en: ['is it fairly valued', 'bull case', 'bear case', 'what is the stock worth', 'price vs value', 'valuation range', 'is the price justified', 'worth buying'],
        zh: ['估值合理吗', '乐观估值', '悲观估值', '股票值多少', '现价和价值', '估值区间', '价格合理吗', '值不值得买'],
      },
    },
    rotation: {
      default: {
        en: ['Is {t} gaining momentum?', 'Is {t} losing momentum?', 'Has {t} turned Improving?', 'How long has {t} been Leading?', '{t} rotation next month',
          'Is {t} beating the market lately?', "What's the chance {t} is Leading in 4 weeks?", 'Will {t} fall into Lagging?', '{t} RS-Momentum this week', 'Is {t} rotating out?'],
        zh: ['{t} 动量在增强吗？', '{t} 动量在减弱吗？', '{t} 转入改善象限了吗？', '{t} 领先多久了？', '{t} 下个月的轮动',
          '{t} 最近跑赢大盘吗？', '{t} 4 周后领先的概率有多大？', '{t} 会掉进落后象限吗？', '{t} 本周的 RS-Momentum', '{t} 资金在轮出吗？'],
      },
      examples: {
        en: ['gaining momentum', 'losing momentum', 'beating the market', 'rotating out', 'rotating in', 'quadrant next month', 'underperforming', 'rs momentum'],
        zh: ['动量增强', '动量减弱', '跑赢市场', '轮出', '轮入', '下个月在哪个象限', '弱于大盘', '相对动量'],
      },
    },
    industry: {
      default: {
        en: ["Is {t}'s industry gaining momentum?", "How many companies are in {t}'s industry?", "Is {t}'s industry beating the market?", "Where will {t}'s industry be in 4 weeks?", "{t} sector rotation"],
        zh: ['{t} 所在行业动量在增强吗？', '{t} 的行业有多少家公司？', '{t} 所在行业跑赢大盘吗？', '{t} 所在行业 4 周后在哪？', '{t} 板块轮动'],
      },
      examples: {
        en: ['sector rotation', 'which industry', 'peer group', 'industry momentum', 'sector strength'],
        zh: ['板块轮动', '哪个行业', '同业公司', '行业动量', '板块强弱'],
      },
    },
    options: {
      default: {
        en: ['Where do {t} options say the price will be next month?', '{t} options: the 80% range', 'Is {t} near its max pain?', 'What is the options market pricing for {t}?',
          '{t} option expiry range', 'How wide is {t}\'s implied range?', '{t} options vs the current price', '{t} call wall resistance'],
        zh: ['期权认为 {t} 下个月在哪？', '{t} 期权的 80% 区间', '{t} 离最大痛点近吗？', '期权市场对 {t} 怎么定价？',
          '{t} 期权到期区间', '{t} 的隐含区间有多宽？', '{t} 期权和现价对比', '{t} 看涨墙的阻力位'],
      },
      examples: {
        en: ['options market', 'option expiry', 'implied range', '80% range', 'max pain level', 'call wall resistance', 'put wall support'],
        zh: ['期权市场', '期权到期', '隐含区间多少', '80% 区间期权', '最大痛点在哪', '看涨墙阻力', '看跌墙支撑'],
      },
    },
    earnings: {
      default: {
        en: ['Did {t} grow revenue last quarter?', "What's {t}'s net margin?", "{t}'s quarterly profit", 'Is {t} profitable?', '{t} sales this quarter', "How fast is {t}'s revenue growing?",
          "{t}'s cash flow from operations", "When did {t} last file earnings?", '{t} income statement summary', "{t}'s operating income"],
        zh: ['{t} 上季度营收增长了吗？', '{t} 的净利率是多少？', '{t} 的季度利润', '{t} 盈利吗？', '{t} 本季度销售额', '{t} 营收增长有多快？',
          '{t} 的经营活动现金流', '{t} 最近一次财报是什么时候？', '{t} 利润表摘要', '{t} 的营业利润'],
      },
      examples: {
        en: ['is it profitable', 'quarterly results', 'net margin', 'operating income', 'income statement', 'latest results', 'top line', 'sales this quarter'],
        zh: ['盈利吗', '季度业绩', '净利率', '营业利润', '利润表', '最新业绩', '营收增速', '销售额'],
      },
    },
    credit: {
      default: {
        en: ["Can {t} pay its debt?", "{t}'s credit rating band", "{t}'s 5-year credit spread", 'Is {t} in financial distress?', "How much debt does {t} carry?", "{t}'s one-year default probability"],
        zh: ['{t} 还得起债吗？', '{t} 的信用评级区间', '{t} 的 5 年期信用利差', '{t} 有财务困境吗？', '{t} 有多少债务？', '{t} 一年期违约概率'],
      },
      examples: {
        en: ['can it pay its debt', 'financial distress', 'default probability', 'credit rating', 'balance sheet risk', 'how much debt'],
        zh: ['还得起债吗', '财务困境', '违约概率', '信用评级', '负债风险', '有多少债务'],
      },
    },
    analysts: {
      default: {
        en: ["What's the highest analyst target for {t}?", "What's the lowest analyst target for {t}?", 'Do analysts see upside in {t}?', "{t} consensus vs price", "What do prediction markets say about {t}?"],
        zh: ['{t} 最高的分析师目标价？', '{t} 最低的分析师目标价？', '分析师认为 {t} 有上涨空间吗？', '{t} 一致预期和现价对比', '预测市场怎么看 {t}？'],
      },
      examples: {
        en: ['highest target', 'lowest target', 'analyst consensus', 'street target', 'prediction markets'],
        zh: ['最高目标价', '最低目标价', '分析师一致预期', '华尔街目标', '预测市场怎么看'],
      },
    },
  };
  for (const [k, v] of Object.entries(MORE)) for (const part of ['default', 'examples']) for (const lg of ['en', 'zh']) BANK[k][part][lg].push(...v[part][lg]);
  root.FFFloQuestions = BANK;
  if (typeof module !== 'undefined') module.exports = BANK;
})(typeof globalThis !== 'undefined' ? globalThis : this);
