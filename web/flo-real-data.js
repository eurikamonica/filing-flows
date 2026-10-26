/* Flo SEC Laboratory — audited historical disclosures and historical SEC case-study anchors.
 * Values transcribed from the named original 10-K reports, USD millions. Frozen
 * annual historical observations, not "latest stock data". Never interpolate a
 * missing reported number or treat a scenario assumption as SEC fact.
 */
(function(root){
'use strict';
const snapshots={
 NVDA:{cik:1045810,ticker:'NVDA',name:'NVIDIA Corporation',fy:'FY2026',end:'2026-01-25',currency:'USD',unit:'USD millions',
   revenue:215938,oi:130387,netIncome:120067,da:2843,capex:6042,ocf:102718,
   netCapexLabel:'Purchases related to property and equipment and intangible assets',
   source:'https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm',
   context:'The 10-K reports cash purchases of PP&E AND intangible assets together; this is not a pure PP&E capex line. Reported FY2026 operating income is an EBIT proxy; FCFF requires additional after-tax and operating working-capital assumptions.'},
 AAPL:{cik:320193,ticker:'AAPL',name:'Apple Inc.',fy:'FY2025',end:'2025-09-27',currency:'USD',unit:'USD millions',
   revenue:416161,oi:133050,netIncome:112010,da:11698,capex:12715,ocf:111482,
   netCapexLabel:'Payments for acquisition of property, plant and equipment',
   source:'https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm',
   context:'Full fiscal 2025 10-K, reported net sales and operating earnings. Capital expenditures are a cash line, not total cash used in investing.'},
 MSFT:{cik:789019,ticker:'MSFT',name:'Microsoft Corporation',fy:'FY2026',end:'2026-06-30',currency:'USD',unit:'USD millions',
   revenue:331839,oi:155237,netIncome:133749,da:null,capex:115948,ocf:182935,
   netCapexLabel:'Additions to property and equipment',
   source:'https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm',
   context:'Microsoft cash-flow statement groups depreciation, amortization AND OTHER ($38,534M), which is not a clean D&A number: D&A is intentionally missing from this drill rather than invented. FY2026 capex is cash additions to PP&E.'}
};
const cases={
 sunbeam:{
  company:'Sunbeam Corporation',dates:'1996–1998',
  citation:'https://www.sec.gov/enforcement-litigation/administrative-proceedings/33-7976',
  sourceType:'SEC administrative enforcement order',
  figures:{improperReserves:35,reported1997:189,restated1997:93,supplierRebatesQ2:2.75,releaseQ1:4.3},
  units:'USD millions',
  exercise:'Restated net income = $93M, originally reported $189M. Calculate misstatement $96M and fraction of originally reported income = 96/189 = 50.8%. The $35M improperly formed reserves are a distinct mechanism, not the full $96M adjustment. Distinguish reserve releases, early vendor rebates and improperly recognized sales.',
  exerciseZH:'1997 年原披露净收益 $189M、重述为 $93M。计算差额 $96M，占原报告利润 50.8%。$35M 不当准备金只是其中一种机制，不能误当全部重述额。分别考察准备金转回、提前返利及不当销售。'
 },
 dell:{
  company:'Dell Inc.',dates:'FY2003–FY2007',
  citation:'https://www.sec.gov/newsroom/press-releases/2010-131-sec-charges-dell-senior-executives-disclosure-accounting-fraud',
  sourceType:'SEC 2010-131 enforcement news release',
  figures:{intelShareOperatingFY2003:.10,intelShareOperatingFY2006:.38,intelShareOperatingFY2007Q1:.76},
  units:'ratio, not dollars',
  exercise:'Intel exclusivity payments increased from 10% of operating income in FY2003 to 38% in FY2006 and 76% in FY2007 Q1. These are RATIO disclosures: never turn them into dollar amounts without the matching operating income. Explain the fragility of earnings dependent on incentives.',
  exerciseZH:'Intel 排他性付款占 Dell 营业利润比例从 FY2003 的 10%，升至 FY2006 的 38%，FY2007 Q1 的 76%。这是比例，不是具体金额；没有同一期间营业利润就不能推算返利美元金额。分析对激励付款的依赖。'
 },
 worldcom:{
  company:'WorldCom Inc.', dates:'FY2001 and Q1 2002',
  citation:'https://www.sec.gov/enforcement-litigation/litigation-releases/lr-17588',
  sourceType:'SEC Litigation Release 17588 / June 27, 2002 (complaint allegations)',
  figures:{overstated2001:3055,overstated2002Q1:797},
  units:'USD millions',
  exercise:'SEC complaint alleged approximately $3,055M FY2001 and $797M Q1 2002 pretax income overstatements, totaling $3,852M across DIFFERENT periods (sum for case scope, not a single fiscal year). Line costs were improper capitalizations; distinguish recurring operating costs from qualifying capital expenditure.',
  exerciseZH:'SEC 诉状指出 2001 全年税前利润被夸大约 $3,055M、2002 Q1 约 $797M。两期合计约 $3,852M，仅为案件涉及金额合计，不能当作单一财年。练习识别将经常性线路费用不当资本化的影响。'
 },
 xerox:{
  company:'Xerox Corporation', dates:'1997–2000',
  citation:'https://www.sec.gov/enforcement-litigation/litigation-releases/lr-17465',
  sourceType:'SEC Litigation Release 17465 / April 11, 2002',
  figures:{acceleratedRevenueLowerBound:3000,approxPretaxIncomeIncrease:1500},
  units:'USD millions: revenue > $3,000M, pretax earnings approximately $1,500M',
  exercise:'SEC alleged accelerated equipment revenue of OVER $3,000M and approximately $1,500M increase to pretax earnings over 1997–2000. $3,000M is a lower bound, NOT an exact reported amount; do not calculate an exact profit-to-revenue ratio. Model revenue timing separately from cash collection.',
  exerciseZH:'SEC 指出 1997–2000 年设备收入被提前确认超过 $3,000M、税前利润增加约 $1,500M。$3,000M 仅是严格下界，并非精确值，不能据此声称精确利润率。练习区分收入确认时点与现金收取时点。'
 },
 waste:{
  company:'Waste Management Inc.', dates:'1992–1997 Q3',
  citation:'https://www.sec.gov/newsroom/press-releases/2002-44-waste-management-founder-five-other-former-top-officers-sued-massive-fraud',
  sourceType:'SEC 2002-44 press release / accounting litigation',
  figures:{cumulativePretaxMisstatement:1700},
  units:'USD millions, cumulative estimated',
  exercise:'SEC described approximately $1,700M cumulative pre-tax misstatement for statements from 1992 through Q3 1997. The cumulative figure has no attributable single-year allocation in this exercise. Simulate a depreciation-useful-life choice using hypothetical asset costs, not an invented historic Waste Management schedule.',
  exerciseZH:'SEC 认定 1992 至 1997 年 Q3 之间累计税前利润错报约 $1,700M。现有案例只记录累计额，不人为分配到单季度或年份；折旧年限模拟将使用明确标注的教学假设。'
 },
 healthsouth:{
  company:'HealthSouth Corporation',dates:'FY1999–H1 2002',
  citation:'https://www.sec.gov/litigation/complaints/comphealths.htm',
  sourceType:'SEC 2003 complaint: table of reported versus actual pretax income (allegations)',
  figures:{reported1999:230,actual1999:-191,reported2000:559,actual2000:194,
    reported2001:434,actual2001:9,reportedH12002:340,actualH12002:157},
  units:'USD millions; FY1999/FY2000/FY2001/H1 2002 are DISTINCT periods',
  exercise:'The SEC complaint lists reported vs actual pretax earnings (USD M): 1999 $230 vs −$191, 2000 $559 vs $194, 2001 $434 vs $9, and H1 2002 $340 vs $157. Reconcile each overstatement ($421M/$365M/$425M/$183M) and SUM $1,394M across these four separate periods. SEC also alleged at least $1.4B cumulative overstatement; figures and case scope need not equal a single exact-period total.',
  exerciseZH:'SEC 诉状分别列出税前利润（百万美元）：1999 原报 $230、实际 −$191；2000 原报 $559、实际 $194；2001 原报 $434、实际 $9；2002 上半年原报 $340、实际 $157。逐期计算差额 $421M/$365M/$425M/$183M，合计 $1,394M；注意 H1 不是完整财年，也不能把该四期合计当作整个案件的精确累计额。'
 },
 bristol:{
  company:'Bristol-Myers Squibb Company',dates:'Q1 2000–Q4 2001',
  citation:'https://www.sec.gov/enforcement-litigation/litigation-releases/lr-18820',
  sourceType:'SEC Litigation Release 18820 / Aug 4 2004; SEC described a settled civil fraud case',
  figures:{improperRevenueApprox:1500,civilSettlementPenalty:150},
  units:'USD millions, revenue and penalty are DISTINCT types of amounts',
  exercise:'SEC described approximately $1,500M of improperly recognized consignment-like distributor revenue in 2000–2001, together with channel stuffing and cookie jar reserves. A separate $150M penalty was part of settlement; NEVER subtract the penalty from revenue to derive adjusted sales. Use an explicitly HYPOTHETICAL revenue baseline to practice deferred-revenue and revenue-quality adjustments.',
  exerciseZH:'SEC 指出 BMS 在 2000–2001 年间从类似寄售安排中不当确认约 $1,500M 收入，并涉及渠道压货及 Cookie Jar 准备金。和解罚款 $150M 是独立事实，不应从收入中扣罚款来计算调整后销售；练习调整收入须使用明确标注的模拟收入基数。'
 }
};
const hasNum=v=>typeof v==='number'&&Number.isFinite(v);
const linkOK=s=>/^https:\/\/(?:www\.)?sec\.gov\/(?:Archives\/|enforcement-litigation\/|newsroom\/|litigation\/complaints\/)/.test(String(s||''));
function verifiedCopy(ticker){
 const d=snapshots[String(ticker||'').toUpperCase()];
 return d?JSON.parse(JSON.stringify(d)):null;
}
function verify(d){
 if(!d||!linkOK(d.source)||!d.fy||!d.end||d.currency!=='USD'||!hasNum(d.revenue)||d.revenue<=0||!hasNum(d.oi))throw Error('No complete, sourced USD annual filing in this exercise.');
 for(const k of ['da','capex','ocf','netIncome'])if(d[k]!==null&&d[k]!==undefined&&!hasNum(d[k]))throw Error('Invalid '+k);
 return d;
}
function fcfBridge(d){
 verify(d);
 if(!hasNum(d.ocf)||!hasNum(d.capex))throw Error('No sourced operating cash flow/capex pair');
 return d.ocf-d.capex;
}
// For future issuers: consume Filing Flows' published ANNUAL company JSON
// (NOT the most recent quarter), matching exact IDs and source provenance.
// Amounts are stored in native currency units; convert USD to millions.
// Never guess missing depreciation from SBC or net-investing cash flows.
function fromPublished(payload,cik){
 if(!payload||typeof payload!=='object'||(payload.currency&&payload.currency!=='USD'))return null;
 const years=(payload.years||[]).filter(x=>x&&/^10-K$/.test(x.form||'')&&linkOK(x.doc_url)&&x.end);
 years.sort((a,b)=>String(b.end).localeCompare(String(a.end)));
 if(!years.length)return null;
 const a=years[0],nodes=a.nodes||[],node=id=>nodes.find(n=>n.id===id&&hasNum(n.v));
 const get=id=>{const n=node(id);return n&&hasNum(n.v)?n.v/1e6:null;};
 const rev=get('rev')??get('R')??(hasNum(a.headline&&a.headline.revenue)?a.headline.revenue/1e6:null);
 const oi=get('oi')??(hasNum(a.headline&&a.headline.oi)?a.headline.oi/1e6:null);
 const ocf=get('ocf')??(hasNum(a.headline&&a.headline.ocf)?a.headline.ocf/1e6:null);
 // Strict label guard: the 'da' node must actually be D&A (not depreciation-only).
 const daNode=node('da'),da=daNode&&/depreciation.{0,8}amorti/i.test(String(daNode.name||''))?daNode.v/1e6:null;
 const capNode=node('capex'),capex=capNode&&/capital expenditures|purchases? of property|property and equipment|purchases? related to property/i.test(capNode.name||'')?capNode.v/1e6:null;
 const data={cik:Number(cik)||payload.profile&&payload.profile.cik||null,ticker:(payload.profile&&payload.profile.tickers||[])[0]||'',name:(payload.profile&&payload.profile.name)||'Company',
  fy:a.label||'FY',end:a.end,currency:'USD',unit:'USD millions',revenue:rev,oi,ocf,da,capex,netIncome:get('ni'),source:a.doc_url,
  netCapexLabel:capNode&&capNode.name||'No source capex node',context:'Derived from the latest full-year 10-K that Filing Flows has actually processed. Source node labels checked; missing values remain unknown. Period is NOT a live quote.',
  provenance:'filing-flows-published-annual'};
 try{return verify(data)}catch(e){return null;}
}
const valueGuide=d=>({revenue:'SEC reported full-year revenue',oi:'SEC reported operating profit (EBIT proxy)',netIncome:'SEC reported net earnings',
 da:d.da===null?'NOT AVAILABLE: cash-flow report may contain other adjustments':'SEC full-year cash-flow depreciation/amortization',
 capex:d.netCapexLabel,ocf:'SEC reported net cash provided by operating activities',
 tax:'Scenario assumption (NOT SEC effective tax or normalized tax rate)',nwc:'Scenario assumption: Δoperating NWC (NOT SEC disclosed cash flow)',wacc:'Scenario assumption, not issuer reported'});
root.FFFloRealData={snapshots,cases,verifiedCopy,verify,fromPublished,fcfBridge,valueGuide,linkOK};
if(typeof module!=='undefined')module.exports=root.FFFloRealData;
})(typeof globalThis!=='undefined'?globalThis:this);
