/* Spin Sankey Flo Academy: deterministic education & SEC-evidence based research.
 * The browser module NEVER generates or invents company financial figures.
 * Corporate figures are loaded from the same company report used by Sankey.
 * Teaching exercises are explicitly hypothetical and never labeled SEC facts.
 */
(function (root) {
  'use strict';
  const html = value => String(value == null ? '' : value).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = n => n !== null && n !== '' && Number.isFinite(Number(n));
  const cash = n => finite(n) ? (Number(n) < 0 ? '−$' : '$') +
    Math.abs(Number(n)).toLocaleString('en-US',{maximumFractionDigits:2}) : '—';
  const pct = n => finite(n) ? (100 * Number(n)).toFixed(2) + '%' : '—';
  const secURL = u => /^https:\/\/(www\.)?sec\.gov\//i.test(String(u || '')) ? u : null;
  const lessonTitles = [
    ['Read the filing','阅读真实财报'],
    ['Build FCFF','计算企业自由现金流'],
    ['Forecast five years','预测五年现金流'],
    ['Estimate WACC','估计加权资本成本'],
    ['Discount forecast FCF','折现预测现金流'],
    ['Terminal value','计算终值'],
    ['Equity value & sensitivity','股权价值与敏感性']
  ];
  const cases = [
    {
      key:'sunbeam', company:'Sunbeam Corporation', years:'1996–1998',
      issue:'Improper restructuring reserves, earnings smoothing and premature supplier rebates',
      issueZH:'不当重组准备金、利润平滑及提前确认供应商返利',
      finding:'The SEC described at least $35 million in improper 1996 reserves later reversed into 1997 earnings. Sunbeam also accelerated supplier rebates attributable to later purchases.',
      findingZH:'SEC 文件指出：1996 年设立至少 3,500 万美元不当准备金，之后在 1997 年用于改善收益；公司还将与未来采购有关的供应商返利提前计入当期结果。',
      question:'Compare the reserve rollforward and classify which supplier rebate relates to unsold inventory.',
      questionZH:'重建准备金增减表，并判断哪些返利应留在未售存货成本中。',
      url:'https://www.sec.gov/enforcement-litigation/administrative-proceedings/33-7976'
    },
    {
      key:'dell', company:'Dell Inc.', years:'FY2003–FY2007',
      issue:'Intel exclusivity payments and improperly maintained accruals',
      issueZH:'Intel 排他性付款及不当应计项目',
      finding:'The SEC stated Intel payments peaked at 76% of Dell operating income in FY2007 Q1; the enforcement action also addressed accounting fraud.',
      findingZH:'SEC 指出 Intel 的排他性付款在 Dell FY2007 Q1 达到其营业利润的 76%；案件还涉及不当会计处理。',
      question:'Separate operating improvement from supplier incentives and look for unexplained accrual releases.',
      questionZH:'区分真正的经营改善与供应商补贴，并追踪缺乏依据的应计项目转回。',
      url:'https://www.sec.gov/newsroom/press-releases/2010-131-sec-charges-dell-senior-executives-disclosure-accounting-fraud'
    }
  ];
  const lessonBody = [
    ['Read the SEC 10-K/10-Q first. Match fiscal year vs quarter, currency and source. Do not combine annual EBIT with quarterly capital expenditure.',
     '先核对 SEC 10-K/10-Q、财年或季度、币种和期间。不要把全年 EBIT 与单季度 CapEx 直接混算。'],
    ['FCFF = EBIT × (1 − marginal/normalized cash tax rate) + D&A − CapEx − change in operating NWC. Use operating income as an EBIT proxy only after checking nonoperating items. D&A is added back because it was a noncash expense. CapEx and increases in NWC consume cash.',
     'FCFF = EBIT × (1 − 规范化边际税率) + 折旧摊销 − 资本支出 − 经营性净营运资本增加额。营业利润是否等于 EBIT 需要核查。折旧是非现金费用，所以加回；资本支出与营运资本占用通常扣除。'],
    ['Choose explicit revenue, operating margin, tax, reinvestment and working-capital assumptions for each of years 1–5. Project EBIT, D&A, CapEx and NWC on internally consistent bases.',
     '分别设定未来五年收入增速、营业利润率、税率、再投资及营运资本假设，逐年预测 EBIT、D&A、CapEx 与 NWC。'],
    ['WACC = E/(D+E) × cost of equity + D/(D+E) × after-tax cost of debt. Cost of equity often uses Rf + beta × ERP. Reconcile debt, lease treatment, and market-value weights.',
     'WACC = 股权权重 × 股权成本 + 债务权重 × 税后债务成本。股权成本常用 Rf + Beta × ERP，需确认融资权重与租赁口径。'],
    ['Discount each projected FCFF at WACC: PV = sum(FCFF_t / (1+WACC)^t). Midyear convention is optional but must be documented.',
     '把每年预测 FCFF 按 WACC 折现：PV = Σ FCFF_t/(1+WACC)^t。可选年中折现，但要统一说明。'],
    ['Perpetuity example: TV_5 = FCFF_6/(WACC−g), valid only when WACC > g. Also check an exit-multiple method for cross-validation.',
     '永续增长法：TV_5 = FCFF_6/(WACC−g)，必须 WACC > g；还应与退出倍数法交叉检查。'],
    ['Enterprise value = PV of forecast FCFF + PV of terminal value. Equity value = enterprise value − financing debt + surplus cash and appropriate nonoperating adjustments. Divide by diluted shares; run WACC × g sensitivities.',
     '企业价值 = 预测期 FCFF 现值 + 终值现值。股权价值需扣除融资性债务、加回适当的非经营现金及调整项，再除以稀释股数。最后执行 WACC × g 敏感性分析。']
  ];
  let active = null;
  const btn = (label, question) => ({label, question});
  const answer = (body, actions, links, facts, mood) =>
    ({html:body, actions:actions || [], links:links || [], facts:facts || [], mood:mood || 'talk', intents:['academy']});
  function match(q) {
    const s=String(q||'').trim();
    if (/^(next step|previous step|prev step|stop lesson|hint|下一步|上一步|结束课程|提示)$/i.test(s)) return active ? 'continue' : null;
    if (/\b(fcff|free cash flow to firm)\b|企业自由现金流|计算自由现金流/i.test(s) && /(?:^|\s)(?:ebit|tax|da|capex|nwc)=/i.test(s)) return 'fcff';
    if (/\b(?:case study|sunbeam|dell case|accounting case)\b|真实案例|案例研究|森宾|太阳能.*案例/i.test(s)) return 'case';
    if (/rebates?|supplier incentives|vendor allowances|返利|供应商补贴|供应商激励/i.test(s)) return 'rebate';
    if (/cookie.jar (?:simulation|example|lab)|模拟(?:准备金|cookie.?jar)|准备金模拟/i.test(s)) return 'reserve_demo';
    if (/cookie.jar|accounting detective|reserves? (?:release|rollforward)|earnings smoothing|财务侦探|准备金|利润平滑|盈余管理/i.test(s)) return 'detective';
    if (/teach|tutorial|walk.?through|step.by.step|how (?:do i|to) (?:build|model)|learn dcf|build (?:a )?dcf|逐步建模|教我|教程|带我建模|学习dcf/i.test(s)) return 'lesson';
    if (/explain (?:this |the )?(?:number|gross profit|revenue|ebit|net income|operating income|operating cash flow)|解释(?:这个|财务)?数字|为什么(?:毛利|营业利润)/i.test(s)) return 'explain';
    return null;
  }
  function getSteps(k) {
    const z=k==='en';
    return [
      btn(z?'Next step':'下一步',z?'next step':'下一步'),
      btn(z?'Previous step':'上一步',z?'previous step':'上一步'),
      btn(z?'Stop lesson':'结束课程',z?'stop lesson':'结束课程')
    ];
  }
  function line(n, name, value) {
    return '<li><b>'+html(name)+'</b>: '+html(finite(value)?cash(value):'not reported here')+'</li>';
  }
  async function lesson(q, co, lang, load) {
    const isStart = match(q)==='lesson' || !active;
    if(isStart) active={step:0,cik:co&&co.cik||null,ticker:co&&co.ticker||null,company:co||null};
    co=co||(active&&active.company)||null;
    if(!isStart) {
      if(/stop lesson|结束课程/i.test(q)){active=null;return answer(lang==='zh'?'课程已结束。可以随时重新开始。':'Lesson closed. Start again any time.',[]);}
      if(/previous step|上一步/i.test(q)) active.step=Math.max(0,active.step-1);
      if(/next step|下一步/i.test(q)) active.step=Math.min(lessonBody.length-1,active.step+1);
    }
    const st=active.step, zh=lang==='zh', data=co&&load?await load(co):null;
    const qs=(data&&data.quarters)||[], newest=qs.slice().sort((a,b)=>String(b.end||'').localeCompare(String(a.end||'')))[0], h=(newest&&newest.headline)||{};
    const ticker=active.ticker;
    let p='<div class="flo-ac-head"><b>Flo Academy · DCF '+(st+1)+'/7</b><small>'+html(lessonTitles[st][zh?1:0])+'</small></div>';
    p+='<p>'+html(lessonBody[st][zh?1:0])+'</p>';
    if(ticker){
      p+='<p><b>'+html(ticker)+'</b>: '+(zh?'下列仅引用当前网站已处理的最新财报数据，而非自动预测值。':'These are latest processed filing figures, not auto-generated forecasts.')+'</p>';
      if(newest){
        p+='<p class="flo-source">'+html(newest.label||newest.end||'')+' · '+html(newest.form||'10-K/10-Q')+' · '+(zh?'提交日 ':'filed ')+html(newest.filed||'unknown')+'</p>';
        p+='<ul class="flo-list">'+line(0,'Reported operating income (EBIT proxy)',h.oi)+line(0,'Reported operating cash flow (NOT FCFF)',h.ocf)+'</ul>';
      } else p+='<p class="flo-source">'+(zh?'尚无可用财报数值；教学练习不冒充公司实际数据。':'No published company filing values available; the exercise is hypothetical.')+'</p>';
    }
    if(st===1) {
      p+='<div class="flo-example"><b>'+(zh?'假设练习，单位百万美元':'Hypothetical exercise, USD millions')+'</b><p>EBIT 100 · Tax 20% · D&amp;A 8 · CapEx 12 · ΔNWC 5 → FCFF = 100 × 0.8 + 8 − 12 − 5 = <b>71</b>.</p></div>';
      p+='<form class="flo-mini-form" data-flo-calc="fcff"><label>EBIT <input name="ebit" inputmode="decimal" type="number" step="any" value="100" required></label><label>Tax % <input name="tax" type="number" step="any" min="0" max="100" value="20" required></label><label>D&amp;A <input name="da" type="number" step="any" min="0" value="8" required></label><label>CapEx <input name="capex" type="number" step="any" min="0" value="12" required></label><label>ΔNWC <input name="nwc" type="number" step="any" value="5" required></label><button type="submit">'+(zh?'计算 FCFF':'Calculate FCFF')+'</button></form>';
    }
    if(st===3) p+='<p class="flo-source">'+(zh?'WACC 中的税率未必与 FCFF 使用的规范化税率完全相同；需要解释税盾假设。':'Debt tax shields require separate documented assumptions.')+'</p>';
    const links=ticker?[['#c-'+active.cik,zh?'财务报表及节点':'Financial statements']]:[];
    if(newest&&secURL(newest.doc_url))links.push([newest.doc_url,zh?'原始 SEC 文件':'Original SEC filing']);
    const actions=getSteps(zh?'zh':'en');
    return answer(p,actions,links,['Training only; actual company values are only taken from published filings; no future forecasts invented.']);
  }
  function fcff(inputs) {
    const a=['ebit','tax','da','capex','nwc'];
    if(a.some(k=>!finite(inputs[k])))throw Error('All five numeric inputs are required.');
    const x=Object.fromEntries(a.map(k=>[k,Number(inputs[k])]));
    if(x.tax<0||x.tax>100||x.da<0||x.capex<0)throw Error('Tax 0–100%; D&A and CapEx must not be negative.');
    if(a.some(k=>Math.abs(x[k])>1e13))throw Error('Input is outside the supported exercise range.');
    return x.ebit*(1-x.tax/100)+x.da-x.capex-x.nwc;
  }
  function reserveScenario(inputs) {
    const balance=Number(inputs.balance),profit=Number(inputs.profit),bank=Number(inputs.bank),
      amount=Number(inputs.amount),action=String(inputs.action||'');
    if(![balance,profit,bank,amount].every(Number.isFinite)||balance<0||amount<0||amount>1e9||
      !['add','use','release'].includes(action)||(action!=='add'&&amount>balance)) {
      throw Error('Invalid reserve scenario: choose add/use/release, nonnegative units and a sufficient reserve balance.');
    }
    return {reserve:balance+(action==='add'?amount:-amount),
      profit:profit+(action==='add'?-amount:action==='release'?amount:0),
      cash:bank-(action==='use'?amount:0)};
  }
  function reserveDemo(lang) {
    const zh=lang==='zh';
    const s='<b>'+(zh?'Cookie Jar 准备金模拟':'Cookie Jar Reserve Lab')+'</b><p>'+
    (zh?'纯教学模拟：计提使利润减少，转回使利润增加，使用/支付准备金使现金减少。实际转回必须有合理的估计依据；不能据此推断任何公司的舞弊。':
    'Hypothetical reserve account: provision reduces profit, release increases profit, use/settlement reduces cash. An actual release requires a supported estimate change.')+'</p>'+
    '<form class="flo-mini-form" data-flo-calc="reserve"><label>Opening reserve <input name="balance" type="number" value="50" min="0" step="any" required></label>'+
    '<label>Profit (before) <input name="profit" type="number" value="100" step="any" required></label>'+
    '<label>Cash (before) <input name="bank" type="number" value="100" step="any" required></label>'+
    '<label>Amount <input name="amount" type="number" min="0" step="any" value="20" required></label>'+
    '<label>Action <select name="action"><option value="add">Record a provision</option><option value="use">Settle in cash</option><option value="release">Release estimate</option></select></label>'+
    '<button type="submit">'+(zh?'查看调整后的数字':'Run scenario')+'</button></form>';
    return answer(s,[btn(zh?'Sunbeam 真实案例':'Sunbeam case study',zh?'Sunbeam 案例':'Sunbeam case study')]);
  }
  function rebate(inputs){
    const purchased=Number(inputs.purchased),sold=Number(inputs.sold),rebate=Number(inputs.rebate);
    if(![purchased,sold,rebate].every(Number.isFinite)||!Number.isInteger(purchased)||!Number.isInteger(sold)||
       purchased<=0||sold<0||sold>purchased||rebate<0||rebate>1e9)throw Error('Require whole units: purchased > 0, 0 ≤ sold ≤ purchased, rebate ≥ 0.');
    return {total:purchased*rebate,cogs:sold*rebate,inventory:(purchased-sold)*rebate};
  }
  function rebateAnswer(lang) {
    const zh=lang==='zh';
    let s='<b>'+(zh?'供应商返利会计练习':'Supplier rebate allocation exercise')+'</b><p>'+
      (zh?'以下全部为教学假设，并非任何公司的实际财报。采购返利如属于产品价格折扣，原则上随对应商品销售进入 COGS；未售商品部分调整存货成本。实际合同应逐项分析。':
       'Entirely hypothetical: when rebates adjust the purchase price, allocate the rebate to cost of goods sold as goods sell; the unsold portion reduces inventory cost. Contract terms may alter the result.')+'</p>';
    s+='<form class="flo-mini-form" data-flo-calc="rebate"><label>'+(zh?'采购件数':'Purchased units')+' <input name="purchased" type="number" min="1" step="1" value="1000" required></label><label>'+(zh?'已售件数':'Sold units')+' <input name="sold" type="number" min="0" step="1" value="400" required></label><label>'+(zh?'每件返利 $':'Rebate per unit $')+' <input name="rebate" type="number" min="0" step="any" value="10" required></label><button type="submit">'+(zh?'计算分配':'Allocate rebate')+'</button></form>';
    return answer(s,[btn(zh?'查看 Sunbeam 真实案例':'Open Sunbeam case',zh?'Sunbeam 案例研究':'Sunbeam case study')],
      [['https://www.sec.gov/enforcement-litigation/administrative-proceedings/33-7976',zh?'SEC Sunbeam 执法文件':'SEC Sunbeam enforcement order']]);
  }
  function caseStudy(q,lang) {
    const zh=lang==='zh', sought=/dell/i.test(q)?'dell':/sunbeam/i.test(q)?'sunbeam':null;
    const selected=sought?cases.filter(x=>x.key===sought):cases;
    let s='<b>'+(zh?'SEC 真实会计案例':'SEC Accounting Case Studies')+'</b><p class="flo-source">'+(zh?'历史执法文件；不是对当前公司风险的指控。':'Historical enforcement materials, not allegations about a company currently being viewed.')+'</p>';
    for(const c of selected) s+='<div class="flo-example"><b>'+html(c.company)+' · '+html(c.years)+'</b><p>'+html(zh?c.issueZH:c.issue)+'</p><p>'+html(zh?c.findingZH:c.finding)+'</p><small>'+html(zh?c.questionZH:c.question)+'</small></div>';
    return answer(s,[btn(zh?'尝试返利会计练习':'Try rebate allocation',zh?'供应商返利练习':'supplier rebate exercise'),
      btn(zh?'检测当前公司 Cookie Jar 线索':'Inspect company reserve signals',zh?'寻找 Cookie Jar':'cookie jar')],selected.map(c=>[c.url,c.company+' — SEC']));
  }
  async function detective(co,lang,load) {
    const zh=lang==='zh';
    if(!co) return answer(zh?'Cookie Jar 财务侦探需要先选择公司，例如 “AAPL Cookie Jar”。也可以先阅读 Sunbeam 案例。':'Choose a company, e.g. “AAPL cookie jar”, or open a historical case.',
      [btn(zh?'Sunbeam 案例':'Sunbeam case','Sunbeam case study')]);
    const d=await load(co), q=d&&d.quality, reserve=(q&&q.reserves)||[];
    const lastByFamily=new Map();
    reserve.slice().sort((a,b)=>String(a.end||'').localeCompare(String(b.end||''))).forEach(r=>{if(r.id)lastByFamily.set(r.id,r);});
    const lines=[];
    for(const r of lastByFamily.values()){
      if(!finite(r.opening)||!finite(r.closing))continue;
      const rel=finite(r.releases)?Number(r.releases):null;
      const ratio=rel!==null&&Number(r.opening)>0?rel/Number(r.opening):null;
      lines.push('<li><b>'+html(r.name||r.id)+'</b> ('+html(r.end||'FY')+'): '+(zh?'期初 ':'open ')+cash(r.opening)+
        ', '+(zh?'转回 ':'released ')+(rel===null?'—':cash(rel))+', '+(zh?'期末 ':'close ')+cash(r.closing)+
        (ratio===null?'':'; release/open '+pct(ratio))+'. '+(r.reconciled===false?(zh?'有未对账差异，需查看附注。':'Incomplete tagged reconciliation; inspect notes.'):'')+'</li>');
    }
    const s='<b>'+html(co.ticker)+' · '+(zh?'Cookie Jar 线索筛查':'Cookie Jar Reserve Screen')+'</b>'+
      '<p>'+(zh?'这不是舞弊识别器。准备金计提与转回可能合理；必须结合合同、估计变动和原始附注。':
      'Screening, not a fraud verdict. Provisions and releases can be legitimate; review estimates, contract terms and footnotes.')+'</p>'+
      (lines.length?'<ul class="flo-list">'+lines.join('')+'</ul>':'<p class="flo-source">'+(zh?'该公司尚无足够的、带来源的准备金增减数据；不能据此声称存在或不存在 Cookie Jar。':'Insufficient sourced reserve rollforwards to evaluate this company. Absence of data is not absence of risk.')+'</p>')+
      '<p class="flo-source">'+(zh?'应继续检查：准备金转回/期初余额、跨年估计变化、净利润−经营现金流、利润波动与 SEC 附注。':'Next: releases/opening, year-to-year estimates, NI−OCF, smoothing patterns and SEC note evidence.')+'</p>';
    const links=[['#c-'+co.cik+'-cash',zh?'利润与现金 · 准备金图':'Profit & cash: reserve waterfalls']];
    const yearly=((d&&d.years)||[]),latest=yearly[0]||((d&&d.quarters)||[]).find(x=>x.form==='10-K');
    if(latest&&secURL(latest.doc_url))links.push([latest.doc_url,zh?'SEC 报告原文':'Original SEC report']);
    return answer(s,[btn(zh?'学习 Cookie Jar 案例':'Study the Sunbeam case',zh?'Sunbeam 案例研究':'Sunbeam case study'),
      btn(zh?'做准备金模拟':'Practice a reserve release',zh?'cookie jar 模拟':'cookie jar simulation')],links,
      ['Reserve screen only; filings and footnotes must substantiate classification.'],lines.length?'think':'worried');
  }
  function explain(co,lang,ctx) {
    const zh=lang==='zh', c=ctx||{},name=String(c.label||c.name||'Financial figure');
    const defs=[
      [/gross profit|毛利/i,'Gross Profit = Revenue − Cost of Goods Sold','毛利润 = 营业收入 − 营业成本'],
      [/operating income|operating profit|营业利润|ebit/i,'Operating income = Revenue − Operating costs; check if it is a suitable EBIT proxy','营业利润 = 收入 − 经营成本；使用为 EBIT 代理时需核对非经营项目'],
      [/free cash flow|fcff|自由现金流/i,'FCFF = EBIT × (1−T) + D&A − CapEx − Δ operating NWC','FCFF = EBIT × (1−税率) + 折旧摊销 − CapEx − Δ经营性净营运资本'],
      [/net income|净利润/i,'Net income = pretax income − income tax expense, after other required adjustments','净利润 = 税前利润 − 所得税费用（并按报表口径调整）'],
      [/revenue|sales|收入|营收/i,'Revenue is recognized under applicable accounting policies, not simply cash received','收入按适用收入确认政策记录，并不等于现金流入'],
      [/cash from operating|operating cash|经营现金/i,'Operating cash flow begins with net income (indirect method) and adjusts noncash and working-capital items','经营现金流间接法从净利润出发，调整非现金项目与营运资本项目']
    ];
    const df=defs.find(x=>x[0].test(name))||[null,'Check the issuer-defined XBRL concept and reporting period.','核对公司自定义 XBRL 科目及其报告期间。'];
    const s='<b>'+html(name)+'</b>'+((c.display || finite(c.amount))?'<p><b>'+html(c.display || cash(c.amount))+'</b> · '+html(c.period||'period not supplied')+'</p>':'')+
      '<p>'+html(zh?df[2]:df[1])+'</p>'+
      '<p class="flo-source">'+(zh?'本面板仅解释已选中的节点；数字来自页面当前报表，不能自动推断其差异的原因。':'This explains the selected node only; it cannot infer causality without further source evidence.')+'</p>';
    const links=[];
    if(secURL(c.docUrl))links.push([c.docUrl,zh?'原始 SEC 披露':'Original SEC filing']);
    if(co)links.push(['#c-'+co.cik,zh?'财报桑基图':'Financial Sankey']);
    return answer(s,[btn(zh?'学习 DCF':'Learn DCF',zh?'教我逐步建模 DCF':'teach me DCF step by step')],links,[]);
  }
  async function handle(q,co,lang,load) {
    const kind=match(q);
    if(!kind)return null;
    if(kind==='lesson'||kind==='continue')return lesson(q,co,lang,load);
    if(kind==='rebate')return rebateAnswer(lang);
    if(kind==='reserve_demo')return reserveDemo(lang);
    if(kind==='case')return caseStudy(q,lang);
    if(kind==='detective')return detective(co,lang,load);
    if(kind==='fcff'){
      const input=Object.fromEntries([...q.matchAll(/(ebit|tax|da|capex|nwc)=(-?[0-9]+(?:\.[0-9]+)?)/ig)].map(x=>[x[1].toLowerCase(),x[2]]));
      try{return answer('FCFF = EBIT × (1 − tax%) + D&A − CapEx − ΔNWC = <b>'+html(cash(fcff(input)))+'</b> (same units as input). <b>Teaching calculation, not SEC company data.</b>');}
      catch(e){return answer(html(e.message),[],[],[],'worried');}
    }
    return explain(co,lang,{label:q});
  }
  root.FFFloAcademy={match,handle,lesson,fcff,rebate,reserveScenario,reserveDemo,caseStudy,detective,explain,cases};
  if(typeof module!=='undefined')module.exports=root.FFFloAcademy;
})(typeof globalThis!=='undefined'?globalThis:this);
