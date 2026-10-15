/* Created by ChatGPT (OpenAI). Deterministic, independent lab calculations. */
(function(root){
'use strict';
const numeric=v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=1e12;
function accrual(p){return numeric(p.net_income)&&numeric(p.ocf)?p.net_income-p.ocf:null;}
function ratio(p){const a=accrual(p);return a!==null&&numeric(p.opening_assets)&&numeric(p.closing_assets)&&p.opening_assets>0&&p.closing_assets>0?a/((p.opening_assets+p.closing_assets)/2):null;}
function roll(r){const keys=['opening','additions','releases','utilization','other','closing'];if(!r||!keys.every(k=>numeric(r[k])))return null;const expected=r.opening+r.additions-r.releases-r.utilization+r.other;return {expected,residual:r.closing-expected};}
function validate(d){
 if(!d||d.schema!=='visual-lab-1'||typeof d.company!=='string'||typeof d.unit!=='string'||typeof d.demo!=='boolean'||!Array.isArray(d.periods)||!d.periods.length||d.periods.length>24)throw Error('Use visual-lab-1 schema with 1–24 periods, company, unit and demo flag.');
 const labels=new Set();for(const p of d.periods){if(typeof p.label!=='string'||!p.label.length||p.label.length>30||labels.has(p.label))throw Error('Period labels must be unique, nonempty and at most 30 characters.');labels.add(p.label);
 for(const k of ['net_income','ocf','opening_assets','closing_assets'])if(p[k]!=null&&!numeric(p[k]))throw Error('Amounts must be finite numbers, null or omitted.');
 if(p.reserves!=null&&!Array.isArray(p.reserves))throw Error('reserves must be an array.');if((p.reserves||[]).length>20)throw Error('Maximum 20 reserves per period.');
 for(const r of p.reserves||[]){if(typeof r.name!=='string')throw Error('Reserve name required.');for(const k of ['opening','additions','releases','utilization','other','closing']){if(r[k]!=null&&(!numeric(r[k])||(k!=='other'&&r[k]<0)))throw Error('Reserve amounts require nonnegative magnitudes; other may be signed.');}if(r.release_in_income!=null&&typeof r.release_in_income!=='boolean')throw Error('release_in_income must be boolean.');}
 if(p.source!=null&&typeof p.source!=='string')throw Error('Source must be text.');
 }return d;
}
function transact(s,action,amount){if(!Number.isInteger(amount)||amount<1||amount>100)throw Error('Choose a whole amount from 1 to 100.');if(!['add','use','release'].includes(action))throw Error('Unknown action.');if(action!=='add'&&amount>s.reserve)throw Error('Cannot use or release more than the available reserve.');return {reserve:s.reserve+(action==='add'?amount:-amount),profit:s.profit+(action==='add'?-amount:action==='release'?amount:0),cash:s.cash-(action==='use'?amount:0)};}
const api={numeric,accrual,ratio,roll,validate,transact};root.LabMath=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
