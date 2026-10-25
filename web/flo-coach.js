/* Flo Guided Coach — bilingual, source-safe, graded learning around existing sheets.
 * Forensic simulations are HYPOTHETICAL; SEC historical findings live separately.
 * Does not rely on paid models, external APIs or unsafe formula execution.
 */
(function(root){
'use strict';
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const WB=()=>root.FFFloWorkbook||(typeof module!=='undefined'?require('./flo-workbook.js'):null);
const curriculum={
 dcf:[
 ['C3','Forecast revenue','预测营业收入','Prior revenue × (1 + growth). C3 = B3 × (1 + C4).','上一年收入 ×（1 + 增长率）。C3 = B3 × (1 + C4)。'],
 ['C6','EBIT and operating margin','营业利润预测','Revenue × margin. Do not use net profit margin.','营业收入 × 营业利润率；不要使用净利率。'],
 ['C8','After-tax operating profit','计算 NOPAT','EBIT × (1 − model tax rate); tax on OPERATIONS, not cash taxes directly.','EBIT ×（1 − 模型税率），不是简单把现金缴税当作税率。'],
 ['C15','Build FCFF','计算 FCFF','NOPAT + D&A − CapEx − Δoperating NWC. Working-capital INVESTMENT is a cash outflow.','NOPAT + 折旧摊销 − CapEx − Δ经营性 NWC。营运资本增加通常占用现金。'],
 ['C18','Discount forecast cash flow','折现当期现金流','PV = FCFF / (1+WACC)^t. Do not discount accounting net income.','现值 = FCFF / (1+WACC)^t；不能用净利润替代 FCFF。'],
 ['G20','Perpetuity terminal value','计算永续终值','TV5 = FCFF6/(WACC−g), WACC > g. Terminal value at end of year 5.','TV5 = 第 6 年 FCFF/(WACC−g)，且 WACC 必须大于 g。'],
 ['G26','Enterprise to equity bridge','企业价值转股权价值','Sum PV forecast FCFF + PV terminal, subtract NET DEBT, divide diluted shares.','先汇总自由现金流及终值现值，再扣净债务、除以稀释股数。']
 ],
 three:[
 ['C3','Revenue linkage','收入预测','FY1 Revenue = Base Revenue × (1 + growth).','第一年收入 = 基期收入 ×（1+增长率）。'],
 ['C10','Build earnings','计算净利润','(EBIT − interest expense) × (1 − assumed tax).','（营业利润 − 利息费用）×（1 − 假设税率）。'],
 ['C19','Working capital movements','营运资本变动','ΔNWC = ΔAR + ΔInventory − ΔAP. Expense recognition and cash settlement differ.','营运资本增加 = 应收增加 + 存货增加 − 应付增加。'],
 ['C20','Cash from operations','经营现金流','Net income + depreciation − increase in NWC.','净利润 + 折旧 − 营运资本净增加。'],
 ['C24','Roll cash forward','滚动现金余额','Opening cash + cash from operations + investing + financing.','期初现金 + CFO + CFI + CFF。'],
 ['C30','Balance-sheet reconciliation','资产负债表平衡','Assets − liabilities − equity MUST equal zero. If not, inspect borrowing/cash and PP&E schedules.','资产 − 负债 − 权益应为零；若不平，检查现金、借款和固定资产。']
 ],
 comps:[
 ['B5','Calculate peer multiples','计算可比公司倍数','EV/EBITDA: enterprise value, NOT equity value.','EV/EBITDA 的分子是企业价值而非股票市值。'],
 ['D6','Choose peer median','可比倍数中位数','MEDIAN(B5:D5) reduces sensitivity to one extreme peer.','使用 MEDIAN(B5:D5) 减轻极端样本影响。'],
 ['E8','Estimate target enterprise value','估算目标企业价值','Target EBITDA × chosen peer multiple.','目标公司 EBITDA × 同业倍数。'],
 ['E12','Implied value per share','推导每股价值','(EV − net debt)/diluted shares, respecting units.','（企业价值 − 净债务）/ 稀释股份数，注意单位。']
 ],
 ddm:[
 ['C3','Project next dividend','预测下一期股息','D1 = D0 × (1+g1). Historical dividend is not a forecast.','D1 = D0 ×（1+g1）；历史股息不是预测。'],
 ['C6','Discount dividends','折现股息','PV = D1/(1+cost of equity). Do not use WACC for equity dividends.','股息按股权成本折现，不应直接用 WACC。'],
 ['G8','Terminal Gordon value','股息终值','TV5 = D6/(Ke−g), requires Ke > g.','TV5 = D6/(Ke−g)，股权成本必须高于 g。'],
 ['G10','Intrinsic equity value','股权内在价值','Sum discounted dividends and terminal share value.','将预测期股息现值与每股终值现值相加。']
 ],
 dupont:[
 ['B7','Compute net margin','计算净利润率','Net income / revenue.','净利润 / 收入。'],
 ['B8','Asset turnover','计算资产周转率','Revenue / average total assets.','收入 / 平均总资产。'],
 ['B9','Equity multiplier','权益乘数','Average total assets / average equity; do not equate all leverage with debt.','平均资产 / 平均权益；权益乘数不等于债务余额。'],
 ['B10','DuPont ROE','杜邦 ROE','Margin × turnover × multiplier. Check against direct NI/equity.','利润率 × 周转率 × 权益乘数，并与净利润/平均权益对账。']
 ],
 reserves:[
 ['G3','Reconcile reserve balances','准备金余额对账','Opening + provision − releases − utilization + other.','期初 + 计提 − 转回 − 使用 + 其他。'],
 ['G5','Disclosure reconciliation','披露余额校验','Reported closing minus modeled closing; a nonzero gap may mean missing tags.','披露期末 − 计算期末；差异可能来自披露字段缺失。'],
 ['G6','Earnings quality clue','准备金分析指标','Releases/opening is a screening indicator, NOT fraud probability.','转回/期初准备金仅是筛查线索，不是舞弊概率。']
 ],
 NVDA:[
 ['C3','Historical operating margin','历史营业利润率','Actual operating income divided by actual SEC revenue. All values FY2026 USD M.','FY2026 的实际营业利润 / 实际收入，单位均为百万美元。'],
 ['C4','OCF minus capital purchases','经营现金流减资本性支出','Historical cash-flow comparison. This is NOT FCFF, and NVDA capex includes intangibles.','历史 OCF 减资产购买支出，但并非 FCFF；NVDA 该项含无形资产。'],
 ['C9','Illustrative FCFF','情景 FCFF','Use a NORMALIZED tax and Δoperating NWC assumptions, NOT SEC facts.','规范化税率与经营性 NWC 变动由你设置，不可标记为 SEC 事实。']
 ],
 AAPL:[
 ['C3','Reported operating margin','历史营业利润率','Use FY2025 income-statement items with matching periods.','必须使用 FY2025 同期间真实数据。'],
 ['C4','Historical free cash flow bridge','历史现金流桥','Cash provided by operations minus purchases of PP&E.','经营现金流扣除固定资产购买。'],
 ['C9','Modeled FCFF','FCFF 模型','Distinguish OCF−CapEx from FCFF with after-tax EBIT and NWC assumptions.','区分简单 FCF 与 FCFF；税率和营运资本变动属于假设。']
 ],
 MSFT:[
 ['C3','Operating profit margin','历史营业利润率','Use exact same fiscal-year revenue and operating profit.','财年收入与营业利润必须同年。'],
 ['C4','Compare investing and OCF','对比资本开支与现金流','OCF − PP&E additions is NOT the full FCFF bridge.','OCF − PP&E 购买并非 FCFF。'],
 ['C6','CapEx intensity','资本开支强度','Cash PP&E additions / reported revenue. Clean D&A is unavailable here.','PP&E 现金增加额 / 收入；纯 D&A 数据本例缺失。']
 ],
 SUNBEAM:[
 ['C3','Restatement gap','计算重述差额','Originally reported FY1997 income − restated income.','原披露 FY1997 收益减重述后收益。'],
 ['C4','Relative overstatement','利润错报占比','Divide restatement gap by originally reported income, not restated income.','差额除以原披露收益，而非重述收益。'],
 ['C5','Separate reserve mechanism','区分准备金机制','1996 improper reserves ≠ total 1997 earnings overstatement. Different periods and mechanisms.','1996 年不当准备金不等于 1997 年全部错报额；期间及机制不同。']
 ],
 DELL:[
 ['C3','Cross-period ratio analysis','跨期比例分析','76% − 10% = 66 percentage points. The ratio is not a dollar amount.','76% − 10% = 66 个百分点；比例不是金额。'],
 ['C4','Supplier payment dependency','供应商激励依赖','76% − 38% = 38 percentage points (FY2006 to FY2007 Q1; different periods).','76% − 38% = 38 个百分点；比较全年与季度需标注期间不同。']
 ],
 WORLDCOM:[
 ['C3','Sum allegation amounts','汇总案件两期错报额','2001 FY and 2002 Q1 amounts are distinct periods; sum to explain case scope only.','2001 全年与 2002 第一季度是不同期间，只能作为案件总范围合计。'],
 ['C4','Allocate share to 2001','2001 数额占案件合计比','2001 pretax overstatement / summed case-scope overstatement.','2001 年税前利润错报 / 这两期合计错报额。']
 ],
 XEROX:[
 ['C3','Revenue timing lower bound','识别提前确认收入下界','SEC said OVER $3 billion, not exactly $3 billion. This cell is a lower-bound illustration.','SEC 表述为超过 $3B，不是恰好 $3B；公式仅显示下界。'],
 ['C4','Pretax income vs revenue','区分收入与利润','Approx $1.5B pretax impact is not a precise gross margin. Do not call their ratio exact.','约 $1.5B 税前影响与超过 $3B 收入不可组成精确利润率。']
 ],
 WASTE:[
 ['C3','Cumulative misstatement','累计错报','Convert $1.7B to $1,700M; do not assign it to FY1997 alone.','$1.7B = $1,700M，为多年的累计数。'],
 ['C4','Training-only depreciation','折旧寿命假设模拟','Cash spent does not change merely because a depreciation life assumption changes.','改变折旧年限不会自动改变历史现金支付。']
 ]
};
const questions={
 dcf:[{en:'Which cash flow is discounted for enterprise value?',zh:'企业价值 DCF 应折现什么？',
 options:['Net income','FCFF before financing flows','Stock dividends'],correct:1,
 why:'Enterprise-value DCF uses cash flow to ALL capital providers.'}],
 three:[{en:'If accounts receivable increases with no other change, indirect CFO will…',zh:'应收账款增加且其他不变，间接法 CFO 会怎样？',
 options:['Decrease','Increase','Not change'],correct:0,why:'Accrued revenue not yet collected consumes operating cash.'}],
 comps:[{en:'Enterprise value should be matched to…',zh:'企业价值 EV 应与以下哪项配对？',options:['EPS','EBITDA','Dividends per share'],correct:1,why:'EV / EBITDA is an enterprise-claimholder multiple.'}],
 ddm:[{en:'Which discount rate should a DDM use?',zh:'DDM 应使用哪个折现率？',options:['WACC','Risk-free rate only','Cost of equity'],correct:2,why:'Dividends are paid to shareholders.'}],
 dupont:[{en:'ROE may rise from greater leverage even if operating returns stagnate.',zh:'即使经营业绩没有改善，杠杆增加也可能使 ROE 上升。',options:['True / 是','False / 否'],correct:0,why:'The equity multiplier is a financing component of ROE.'}],
 reserves:[{en:'Does a reserve release prove accounting fraud?',zh:'准备金转回就能证明财务舞弊吗？',options:['Yes / 是','No / 否'],correct:1,why:'Valid changes in estimates can legitimately reverse a reserve; footnotes and evidence are essential.'}],
 NVDA:[{en:'Is reported OCF minus cash capex automatically FCFF?',zh:'OCF 减资本支出是否自动等于 FCFF？',options:['Yes / 是','No / 否'],correct:1,why:'FCFF needs an after-tax unlevered operating bridge and NWC assumptions.'}],
 AAPL:[{en:'Historical SEC figures and future assumptions should…',zh:'真实 SEC 历史数字与未来假设应如何处理？',options:['Be combined without labels','Be clearly distinguished'],correct:1,why:'Source and modeling provenance must not be confused.'}],
 MSFT:[{en:'Can D&A and OTHER be treated as clean D&A?',zh:'折旧、摊销及 OTHER 合计能当纯 D&A 吗？',options:['Yes / 可以','No / 不可以'],correct:1,why:'Other can contain unrelated cash-flow adjustments.'}],
 SUNBEAM:[{en:'Was the $35M reserve misstatement equal to the entire $96M restatement gap?',zh:'$35M 准备金就是全部 $96M 重述差额吗？',options:['Yes','No'],correct:1,why:'Other earnings manipulation mechanisms contributed to the restatement.'}],
 DELL:[{en:'76% of operating income means Intel paid Dell $76 million.',zh:'占营业利润 76% 是否意味着收到 $76M？',options:['Correct','Incorrect'],correct:1,why:'A ratio does not imply an amount without denominator.'}],
 WORLDCOM:[{en:'Expensing normal network fees as capital assets typically…',zh:'把本应费用化的线路成本错误资本化，通常会使本期利润如何变化？',options:['Overstate current profit','Reduce current profit'],correct:0,why:'Costs move off the income statement into assets (temporarily), until depreciation or impairment.'}],
 XEROX:[{en:'Is accelerated revenue necessarily cash collected now?',zh:'提前确认收入是否表示当期已经收到现金？',options:['Yes','No'],correct:1,why:'Recognition timing and collections are distinct.'}],
 WASTE:[{en:'Does longer useful life by itself increase immediate cash flow?',zh:'单纯延长折旧年限会增加当期现金吗？',options:['Yes','No'],correct:1,why:'Depreciation is non-cash; timing effects depend on tax rules not modeled here.'}]
};
function track(s){const id=s.template?s.template.id:s.id;return curriculum[id]||Object.keys(s.answers||{}).slice(0,10).map(ref=>[ref,'Explain this formula','解释当前公式','Follow source evidence and cell references.','查看来源和单元格引用。']);}
function state(s){if(!s.coach)s.coach={step:0,quiz:null,quizzesAnswered:0};return s.coach;}
function current(s){const v=track(s),c=state(s);c.step=Math.min(Math.max(0,c.step),v.length-1);return v[c.step];}
function completed(s,ref){if(!s.cells[ref]||!String(s.cells[ref].raw||'').trim())return false;
 try{const grade=WB().score(s);return grade.good.includes(ref);}catch(e){return false;}}
function next(s){const t=track(s),o=state(s);if(!t.length)return false;
 const step=t[o.step];
 if(!completed(s,step[0])){s.message='Complete and check '+step[0]+' before advancing. Use Hint if needed.';s.selected=step[0];return false;}
 o.step=Math.min(o.step+1,t.length-1);s.selected=t[o.step][0];s.message='Milestone completed. '+s.selected+' is next.';return true;}
function prev(s){const t=track(s),o=state(s);o.step=Math.max(0,o.step-1);s.selected=t[o.step][0];return o.step;}
function hint(s,lang){const p=current(s);return (lang==='zh'?p[4]:p[3]);}
function answerQuiz(s,index,lang){const id=s.template?s.template.id:s.id,quiz=questions[id]&&questions[id][0];
 if(!quiz||!Number.isInteger(index)||index<0||index>=quiz.options.length)throw Error('Invalid quiz answer');
 const pass=index===quiz.correct;state(s).quiz={index,pass};if(pass)state(s).quizzesAnswered=1;
 s.message=(pass?(lang==='zh'?'正确：':'Correct: '):(lang==='zh'?'再试一次：':'Try again: '))+quiz.why;return pass;}
function panel(s,lang='en'){
 const zh=lang==='zh',t=track(s),at=current(s),p=state(s),count=t.filter(x=>completed(s,x[0])).length,id=s.template?s.template.id:s.id,
 quiz=questions[id]&&questions[id][0],ref=at&&at[0];
 const buttons='<div class="flo-coach-controls"><button type="button" data-coach-prev '+(p.step===0?'disabled':'')+'>'+(zh?'上一步':'Previous')+'</button>'+
 '<button type="button" data-coach-focus>'+(zh?'定位单元格':'Go to cell')+'</button>'+
 '<button type="button" data-coach-hint>'+(zh?'分步提示':'Explain')+'</button>'+
 '<button type="button" data-coach-next>'+(zh?'检查并前进':'Check & next')+'</button></div>';
 return '<section class="flo-coach" aria-label="Guided modeling lesson"><header><b>Flo Guided Coach · '+(p.step+1)+'/'+t.length+
 '</b><small>'+(zh?'已完成':'Mastered')+' '+count+'/'+t.length+'</small></header>'+
 '<div class="flo-coach-progress" role="progressbar" aria-valuenow="'+count+'" aria-valuemin="0" aria-valuemax="'+t.length+'"><span style="width:'+(count/t.length*100)+'%"></span></div>'+
 '<b>'+esc(zh?at[2]:at[1])+' · '+esc(ref)+'</b><p>'+esc(zh?at[4]:at[3])+'</p>'+
 '<p class="flo-source">'+(zh?'请先在工作表填写正确公式（而不是照抄数字）。错误时先检查单位、正负号、行列引用。':'Enter a spreadsheet formula, not an answer number. Check units, signs and references if wrong.')+'</p>'+
 buttons+
 (quiz?'<div class="flo-coach-quiz"><b>'+(zh?'理解测试':'Concept checkpoint')+'</b><p>'+esc(zh?quiz.zh:quiz.en)+'</p>'+
 quiz.options.map((v,i)=>'<button type="button" data-coach-quiz="'+i+'" '+
 (p.quiz&&p.quiz.index===i?'aria-pressed="true"':'')+'>'+esc(v)+'</button>').join('')+
 (p.quiz?'<p class="flo-source">'+(p.quiz.pass?'✓ ':'↻ ')+esc(s.message||quiz.why)+'</p>':'')+'</div>':'')+'</section>';
}
function simulate(x){
 const kind=String(x.kind||'worldcom').toLowerCase(),amount=Number(x.amount),life=Number(x.life===undefined?5:x.life);
 if(!Number.isFinite(amount)||amount<0||amount>1e9||!Number.isInteger(life)||life<1||life>40)throw Error('Simulation amount must be ≥0 and life must be 1–40 years.');
 if(kind==='worldcom')return {kind,pretaxOverstatement:amount,assetsOverstatement:amount,
  laterAnnualDepreciation:amount/life,immediateCashDifference:0,
  entries:['Proper: Dr Network operating expense / Cr Payables or cash '+amount,
  'Improper: Dr Capital asset / Cr Payables or cash '+amount,
  'Future: Dr Depreciation expense / Cr Accumulated depreciation '+(amount/life).toFixed(2)],
  caveat:'Illustrative same-period entries; cash-flow classification and income tax effects excluded.'};
 if(kind==='xerox')return {kind,pretaxOverstatement:amount,receivableOverstatement:amount,immediateCashDifference:0,
  entries:['If earned: Dr Receivable / Cr Revenue '+amount,
   'If unearned: defer revenue (contract liability) or avoid premature receivable until earned'],
  caveat:'Hypothetical full amount treated as premature income before associated costs; NOT SEC Xerox historic impact.'};
 if(kind==='waste'){
  const originalLife=life,extendedLife=life*2;
  const original=amount/originalLife,adjusted=amount/extendedLife;
  return {kind,annualDepreciationOriginal:original,annualDepreciationExtended:adjusted,
   illustrativePretaxProfitIncrease:original-adjusted,immediateCashDifference:0,
   entries:['Dr Depreciation expense / Cr Accumulated depreciation '+adjusted.toFixed(2)+' under a longer assumed life'],
   caveat:'Hypothetical straight-line lives and no salvage value; not Waste Management historic entries, taxes excluded.'};
 }
 if(kind==='sunbeam')return {kind,reserveLiabilityChange:-amount,pretaxProfitIncrease:amount,immediateCashDifference:0,
   entries:['If valid re-estimate: Dr Reserve liability / Cr Provision expense '+amount],
   caveat:'A reserve release is not presumptively fraudulent; assess actual underlying obligations.'};
 if(kind==='dell'){
  const ratio=Math.min(1,Math.max(0,amount/100));
  return {kind,assumedOperatingIncome:100,assumedPaymentShare:ratio,
   illustrativePayments:amount,otherOperatingIncome:100-amount,immediateCashDifference:null,
   entries:['Comparative decomposition only: 100 hypothetical operating income less '+amount+' incentive contribution'],
   caveat:'100 operating-income units are hypothetical; Dell SEC reported payment shares, not amounts.'};
 }
 throw Error('Unknown case simulator');
}
function simulatorHTML(lang='en'){
 const zh=lang==='zh';
 return '<section class="flo-coach-sim"><b>'+(zh?'会计处理模拟器 · 非真实历史金额':'Accounting Treatment Simulator — HYPOTHETICAL')+'</b>'+
 '<p class="flo-source">'+(zh?'SEC 案例解释真实违规模式，本实验金额由你设定，不得当作案件实际数字。':'SEC cases inform the mechanism. All user-input amounts here are illustrative, not historical allegations.')+'</p>'+
 '<div class="flo-wb-controls"><label>'+(zh?'场景':'Scenario')+' <select data-flo-sim-kind>'+
 [['worldcom','WorldCom · CapEx vs expense'],['xerox','Xerox · revenue timing'],['waste','Waste Management · useful life'],['sunbeam','Sunbeam · reserve release'],['dell','Dell · incentive reliance']].map(([v,l])=>'<option value="'+v+'">'+esc(l)+'</option>').join('')+'</select></label>'+
 '<label>'+(zh?'金额/比例':'Amount / % for Dell')+' <input data-flo-sim-amount type="number" value="100" min="0" max="1000000000" step="any"></label>'+
 '<label>'+(zh?'使用年限（年）':'Useful life (years)')+' <input data-flo-sim-life type="number" value="5" min="1" max="40" step="1"></label>'+
 '<button type="button" data-flo-sim-run>'+(zh?'运行会计模拟':'Run simulation')+'</button></div>'+
 '<div class="flo-sim-results" role="status"></div></section>';
}
function renderSimResult(data){
 const rows=Object.entries(data).filter(([k,v])=>typeof v==='number'&&v!==null&&Number.isFinite(v)).map(([k,v])=>'<li><b>'+esc(k)+'</b>: '+esc(v.toLocaleString('en-US',{maximumFractionDigits:2}))+'</li>').join('');
 const journal=(data.entries||[]).map(x=>'<li>'+esc(x)+'</li>').join('');
 return '<b>Model result — teaching assumptions only</b><ul>'+rows+'</ul><b>Journal-entry teaching / mechanics</b><ul>'+journal+'</ul><p class="flo-source">'+esc(data.caveat)+'</p>';
}
root.FFFloCoach={track,state,current,completed,next,prev,hint,answerQuiz,panel,questions,curriculum,simulate,simulatorHTML,renderSimResult};
if(typeof module!=='undefined')module.exports=root.FFFloCoach;
})(typeof globalThis!=='undefined'?globalThis:this);
