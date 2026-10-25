/* Flo Spreadsheet Lab — small, offline, Excel-style accounting model exercises.
   No eval(), external scripts, financial data fetch, or uploaded user workbook.
   All starter numbers are hypothetical (NOT SEC company facts).
*/
(function(root) {
  'use strict';
  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g,
    ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const I = (v, note='') => ({type:'input',raw:String(v),note});
  const F = (formula, note='') => ({type:'target',raw:formula,note});
  const H = v => ({type:'heading',raw:String(v)});
  const L = v => ({type:'label',raw:String(v)});
  const row = (id, label, cells) => ({id,label,cells});
  const letters = 'ABCDEFGH';
  const cols = n => Array.from({length:n},(_,i)=>letters[i]);
  const cellRef = (letter,n) => letter+n;

  function dcf() {
    const yrs=cols(7).slice(2); // C:G, five future years
    const rows=[
      row(2,'Year', {B:H('Base FY'),...Object.fromEntries(yrs.map((c,i)=>[c,H('Year '+(i+1))]))}),
      row(3,'Revenue ($M)',{B:I(1000,'Base-year hypothetical revenue.')}),
      row(4,'Revenue growth',{}), row(5,'EBIT margin',{}), row(6,'EBIT',{}),
      row(7,'Cash tax rate',{}), row(8,'NOPAT',{}), row(9,'D&A / sales',{}),
      row(10,'D&A',{}), row(11,'CapEx / sales',{}), row(12,'CapEx',{}),
      row(13,'ΔNWC / Δsales',{}), row(14,'ΔNWC',{}), row(15,'FCFF',{}),
      row(16,'WACC',{B:I(0.10,'Use consistent nominal after-tax WACC and debt definitions.')}),
      row(17,'PV factor',{}), row(18,'PV of FCFF',{}),
      row(19,'Terminal growth g',{B:I(0.03,'Must be smaller than WACC.')}),
      row(20,'Terminal value',{}),row(21,'PV of terminal',{}),
      row(22,'Enterprise value',{}),row(23,'Net debt ($M)',{B:I(250)}),
      row(24,'Equity value',{}),row(25,'Diluted shares (M)',{B:I(100)}),
      row(26,'Value per share',{})
    ];
    const add=(n,c,x)=>rows.find(r=>r.id===n).cells[c]=x;
    yrs.forEach((c,i)=>{
      const prev=letters[letters.indexOf(c)-1];
      add(3,c,F('='+prev+'3*(1+'+c+'4)','Revenue grows from previous year.'));
      add(4,c,I([.12,.10,.08,.07,.05][i],'Expected growth; modify in scenario analysis.'));
      add(5,c,I([.30,.29,.28,.27,.26][i]));
      add(6,c,F('='+c+'3*'+c+'5','Operating income proxy for EBIT.'));
      add(7,c,I(.21));
      add(8,c,F('='+c+'6*(1-'+c+'7)','After-tax operating profit.'));
      add(9,c,I(.045)); add(10,c,F('='+c+'3*'+c+'9'));
      add(11,c,I(.12)); add(12,c,F('='+c+'3*'+c+'11'));
      add(13,c,I(.08)); add(14,c,F('=('+c+'3-'+prev+'3)*'+c+'13','Increased NWC consumes cash.'));
      add(15,c,F('='+c+'8+'+c+'10-'+c+'12-'+c+'14','FCFF = NOPAT + D&A - CapEx - ΔNWC.'));
      add(17,c,F('=1/(1+$B$16)^'+(i+1)));
      add(18,c,F('='+c+'15*'+c+'17'));
    });
    add(20,'G',F('=G15*(1+$B$19)/($B$16-$B$19)','Perpetuity only when WACC > g.'));
    add(21,'G',F('=G20*G17'));add(22,'G',F('=SUM(C18:G18)+G21'));
    add(24,'G',F('=G22-B23'));add(26,'G',F('=G24/B25'));
    return {id:'dcf',name:'5-Year DCF / FCFF',nameZH:'五年 DCF / FCFF',about:'Forecast operating cash generation, terminal value and value per share. WACC must exceed perpetual growth.',
      aboutZH:'预测 FCFF、终值、企业价值及每股价值；永续增长率必须小于 WACC。',
      rows,columns:cols(7),final:'G26',scenario:[
        {name:'Base',nameZH:'基准',changes:{}},
        {name:'Bull',nameZH:'乐观',changes:{C4:.16,D4:.14,E4:.12,F4:.09,G4:.07,B16:.09,B19:.035}},
        {name:'Bear',nameZH:'悲观',changes:{C4:.06,D4:.04,E4:.03,F4:.02,G4:.02,B16:.12,B19:.02}}
      ]};
  }

  function threeStatements() {
    const years=['C','D','E'];const rows=[
      row(2,'Period',{B:H('Base FY'),C:H('FY1'),D:H('FY2'),E:H('FY3')}),
      row(3,'Revenue ($M)',{B:I(500)}),row(4,'Revenue growth',{}),
      row(5,'EBIT margin',{}),row(6,'EBIT',{}),row(7,'Interest expense',{}),
      row(8,'Pretax income',{}),row(9,'Tax rate',{}),row(10,'Net income',{}),
      row(11,'Depreciation',{}),row(12,'CapEx',{}),
      row(13,'AR / Revenue',{}),row(14,'Inventory / Revenue',{}),
      row(15,'AP / Revenue',{}),row(16,'Accounts receivable',{B:I(60)}),
      row(17,'Inventory',{B:I(40)}),row(18,'Accounts payable',{B:I(50)}),
      row(19,'Change in NWC',{}),row(20,'Cash from operations',{}),
      row(21,'Cash from investing',{}),row(22,'Cash from financing',{}),
      row(23,'Net cash change',{}),row(24,'Cash',{B:I(80)}),
      row(25,'Net PP&E',{B:I(200)}),row(26,'Debt',{B:I(100)}),
      row(27,'Equity',{B:F('=B24+B16+B17+B25-B18-B26')}),
      row(28,'Total assets',{}),row(29,'Liabilities + equity',{}),
      row(30,'Balance sheet check',{})
    ];
    const add=(n,c,x)=>rows.find(r=>r.id===n).cells[c]=x;
    years.forEach((c,i)=>{
      const p=letters[letters.indexOf(c)-1];
      add(4,c,I([.08,.06,.05][i]));add(5,c,I(.25));
      add(3,c,F('='+p+'3*(1+'+c+'4)'));
      add(6,c,F('='+c+'3*'+c+'5'));add(7,c,I(5));
      add(8,c,F('='+c+'6-'+c+'7'));add(9,c,I(.22));
      add(10,c,F('='+c+'8*(1-'+c+'9)'));
      add(11,c,I(10));add(12,c,I(20));
      add(13,c,I(.12));add(14,c,I(.08));add(15,c,I(.10));
      add(16,c,F('='+c+'3*'+c+'13'));add(17,c,F('='+c+'3*'+c+'14'));
      add(18,c,F('='+c+'3*'+c+'15'));
      add(19,c,F('=('+c+'16-'+p+'16)+('+c+'17-'+p+'17)-('+c+'18-'+p+'18)'));
      add(20,c,F('='+c+'10+'+c+'11-'+c+'19'));
      add(21,c,F('=-'+c+'12'));add(22,c,I(0,'Simplified net financing cash flow: debt issued (+) or repaid (-).'));
      add(23,c,F('='+c+'20+'+c+'21+'+c+'22'));add(24,c,F('='+p+'24+'+c+'23'));
      add(25,c,F('='+p+'25+'+c+'12-'+c+'11'));
      add(26,c,F('='+p+'26+'+c+'22'));
      // Parent balance + current net income. Simplified: interest is paid in CFO;
      // excludes dividends, deferred tax and other comprehensive income.
      add(27,c,F('='+p+'27+'+c+'10'));
      add(28,c,F('='+c+'24+'+c+'16+'+c+'17+'+c+'25'));
      add(29,c,F('='+c+'18+'+c+'26+'+c+'27'));
      add(30,c,F('='+c+'28-'+c+'29','Must equal zero: check CFO, PP&E, debt and equity links.'));
    });
    add(28,'B',F('=B24+B16+B17+B25'));add(29,'B',F('=B18+B26+B27'));
    add(30,'B',F('=B28-B29'));
    return {id:'three',name:'Integrated 3-Statement Bridge',nameZH:'简化三表联动',about:'Income statement, indirect CFO, cash flows and a balanced balance sheet (simplified, no dividends/other changes).',
      aboutZH:'联动利润表、间接法 CFO、现金流及资产负债表；简化模型不含股利与其他综合项目。',
      rows,columns:cols(5),final:'E30',
      scenario:[{name:'Base',nameZH:'基准',changes:{}},{name:'Growth',nameZH:'高增长',changes:{C4:.15,D4:.12,E4:.10}},
        {name:'Stress',nameZH:'压力',changes:{C4:-.05,D4:0,E4:.02,C5:.12,D5:.15,E5:.17,C12:45}}]};
  }

  function comps() {
    const rows=[
      row(2,'Company',{B:H('Peer 1'),C:H('Peer 2'),D:H('Peer 3'),E:H('Target')}),
      row(3,'Enterprise value',{B:I(300),C:I(450),D:I(600)}),
      row(4,'EBITDA',{B:I(30),C:I(50),D:I(60)}),
      row(5,'EV / EBITDA',{B:F('=B3/B4'),C:F('=C3/C4'),D:F('=D3/D4')}),
      row(6,'Peer median',{D:F('=MEDIAN(B5:D5)')}),
      row(7,'Target EBITDA',{E:I(42)}),
      row(8,'Implied target EV',{E:F('=D6*E7')}),
      row(9,'Target net debt',{E:I(50)}),
      row(10,'Target equity value',{E:F('=E8-E9')}),
      row(11,'Target diluted shares',{E:I(20)}),
      row(12,'Implied share price',{E:F('=E10/E11')})
    ];
    return {id:'comps',name:'Trading Comps / EV-EBITDA',nameZH:'可比公司倍数估值',about:'Compute peer multiples and a median-based target equity value; confirm peers and EBITDA basis before real use.',
      aboutZH:'由可比公司 EV/EBITDA 的中位数推导目标股权价值；真实估值须核对同业和 EBITDA 口径。',
      rows,columns:cols(5),final:'E12',
      scenario:[{name:'Base',nameZH:'基准',changes:{}},{name:'Upcycle',nameZH:'景气回升',changes:{B3:390,C3:540,D3:720,E7:48}},
        {name:'Downcycle',nameZH:'景气衰退',changes:{B3:210,C3:350,D3:450,E7:35}}]};
  }

  function ddm() {
    const y=['C','D','E','F','G'];const rows=[
      row(2,'Year',{B:H('FY0'),...Object.fromEntries(y.map((c,i)=>[c,H('Y'+(i+1))]))}),
      row(3,'Dividend / share',{B:I(2)}),row(4,'Dividend growth',{}),
      row(5,'Cost of equity',{B:I(.09)}),row(6,'PV dividends',{}),
      row(7,'Terminal growth',{B:I(.03)}),
      row(8,'Terminal equity price',{}),row(9,'PV terminal price',{}),
      row(10,'DDM fair value / share',{})
    ];
    const add=(n,c,x)=>rows.find(r=>r.id===n).cells[c]=x;
    y.forEach((c,i)=>{
      const prev=letters[letters.indexOf(c)-1];
      add(4,c,I([.08,.07,.06,.05,.04][i]));
      add(3,c,F('='+prev+'3*(1+'+c+'4)'));
      add(6,c,F('='+c+'3/(1+$B$5)^'+(i+1)));
    });
    add(8,'G',F('=G3*(1+$B$7)/($B$5-$B$7)'));
    add(9,'G',F('=G8/(1+$B$5)^5'));
    add(10,'G',F('=SUM(C6:G6)+G9'));
    return {id:'ddm',name:'Dividend Discount Model',nameZH:'股息折现模型',about:'Five dividend forecasts plus Gordon terminal value. Requires cost of equity > sustainable growth.',
      aboutZH:'五期股息折现及永续终值。股权成本应高于可持续股息增长率。',
      rows,columns:cols(7),final:'G10',scenario:[{name:'Base',nameZH:'基准',changes:{}},
        {name:'Dividend growth',nameZH:'增速提高',changes:{C4:.11,D4:.10,E4:.08,F4:.07,G4:.06,B7:.035}},
        {name:'Higher discount',nameZH:'高折现率',changes:{B5:.12,B7:.02}}]};
  }

  function dupont() {
    const rows=[
      row(2,'Period',{B:H('FY0'),C:H('FY1'),D:H('FY2')}),
      row(3,'Revenue',{B:I(1000),C:I(1100),D:I(1200)}),
      row(4,'Net income',{B:I(120),C:I(145),D:I(150)}),
      row(5,'Average assets',{B:I(900),C:I(950),D:I(1000)}),
      row(6,'Average equity',{B:I(450),C:I(480),D:I(500)}),
      row(7,'Net profit margin',{}),row(8,'Asset turnover',{}),
      row(9,'Equity multiplier',{}),row(10,'DuPont ROE',{}),
      row(11,'Direct ROE',{}),row(12,'Reconciliation',{})
    ];
    const add=(n,c,x)=>rows.find(r=>r.id===n).cells[c]=x;
    for(const c of ['B','C','D']){
      add(7,c,F('='+c+'4/'+c+'3'));add(8,c,F('='+c+'3/'+c+'5'));
      add(9,c,F('='+c+'5/'+c+'6'));add(10,c,F('='+c+'7*'+c+'8*'+c+'9'));
      add(11,c,F('='+c+'4/'+c+'6'));add(12,c,F('='+c+'10-'+c+'11'));
    }
    return {id:'dupont',name:'DuPont ROE Decomposition',nameZH:'DuPont 三因素分解',
      about:'ROE = margin × asset turnover × equity multiplier. Compare with net income / average equity.',
      aboutZH:'ROE = 净利润率 × 资产周转率 × 权益乘数，并和直接计算的 ROE 对账。',
      rows,columns:cols(4),final:'D10',
      scenario:[{name:'Base',nameZH:'基准',changes:{}},{name:'Leverage',nameZH:'杠杆提高',changes:{C6:380,D6:350}},
        {name:'Margin pressure',nameZH:'利润率承压',changes:{C4:100,D4:85}}]};
  }

  function reserves() {
    return {id:'reserves',name:'Reserve Rollforward & Cookie Jar',nameZH:'准备金增减和 Cookie Jar',
      about:'Reconcile opening + provisions − releases − utilization + other to closing. A release is not proof of fraud.',
      aboutZH:'期初 + 计提 − 转回 − 使用 + 其他 = 期末；准备金转回不等于舞弊证据。',
      rows:[row(2,'Reserve events',{B:H('Opening'),C:H('Provision'),D:H('Release'),E:H('Used'),F:H('Other'),G:H('Closing')}),
        row(3,'Reserve ($M)',{B:I(50),C:I(30),D:I(20),E:I(25),F:I(5),G:F('=B3+C3-D3-E3+F3')}),
        row(4,'Reported closing',{G:I(40)}),
        row(5,'Reported − modeled',{G:F('=G4-G3')}),
        row(6,'Release / opening',{G:F('=D3/B3')})],
      columns:cols(7),final:'G5',scenario:[{name:'Base',nameZH:'基准',changes:{}},
        {name:'Higher releases',nameZH:'更多转回',changes:{D3:35,G4:25}},
        {name:'Cash use',nameZH:'更多结算',changes:{E3:40,G4:25}}]};
  }

  const builders={dcf,three:threeStatements,comps,ddm,dupont,reserves};
  const idNames=Object.keys(builders);
  function template(id) {
    if(!Object.prototype.hasOwnProperty.call(builders,id))throw Error('Unknown model');
    return builders[id]();
  }
  function cellsFrom(t) {
    const result={};
    for(const r of t.rows)for(const [col,item] of Object.entries(r.cells||{}))
      result[cellRef(col,r.id)]={...item};
    return result;
  }

  // Mini formula interpreter: numeric literals, 4 operators, ^, parentheses,
  // $A$1 references, and SUM/AVERAGE/MEDIAN/MIN/MAX over bounded ranges.
  // Does not execute JavaScript, external formulas, workbook links or macros.
  const limitRef=/^\$?([A-H])\$?([1-9][0-9]?)$/i;
  function tokens(src) {
    const s=String(src||'').trim();
    if(!s.startsWith('=')||s.length>220)throw Error('#FORMULA!');
    const result=[];let pos=1;
    while(pos<s.length){
      if(/\s/.test(s[pos])){pos++;continue;}
      const m=/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|^\$?[A-H]\$?[1-9][0-9]?|^[A-Za-z_]+|^[+\-*\/^():,]/.exec(s.slice(pos));
      if(!m)throw Error('#FORMULA!');
      result.push(m[0]);pos+=m[0].length;
      if(result.length>160)throw Error('#FORMULA!');
    }
    return result;
  }
  function evaluate(sheet, ref, opts={}) {
    const memo=new Map(), stack=new Set(), fixed=opts.answers||{};
    const ids=Object.keys(sheet);
    const read=(name)=>{
      const normalized=String(name).replace(/\$/g,'').toUpperCase();
      if(!limitRef.test(normalized)||!Object.prototype.hasOwnProperty.call(sheet,normalized))throw Error('#REF!');
      if(memo.has(normalized))return memo.get(normalized);
      if(stack.has(normalized))throw Error('#CYCLE!');
      stack.add(normalized);
      try{
        // Guard perpetual-growth models: otherwise a negative/infinite terminal
        // value could masquerade as a legitimate modeled equity value.
        if(normalized==='G20'&&sheet['B16']&&sheet['B19']&&sheet['G26']&&read('B16')<=read('B19'))
          throw Error('#WACC≤g!');
        if(normalized==='G8'&&sheet['B5']&&sheet['B7']&&sheet['G10']&&read('B5')<=read('B7'))
          throw Error('#Ke≤g!');
        const item=sheet[normalized], raw=Object.prototype.hasOwnProperty.call(fixed,normalized)?fixed[normalized]:item.raw;
        let v;
        if(raw===''||raw==null)throw Error('#BLANK!');
        if(String(raw).trim().startsWith('='))v=parse(raw);
        else if(!Number.isFinite(Number(raw)))throw Error('#VALUE!');
        else v=Number(raw);
        if(!Number.isFinite(v))throw Error('#NUM!');
        memo.set(normalized,v);return v;
      }finally{stack.delete(normalized);}
    };
    const range=(from,to)=>{
      const a=/^([A-H])(\d+)$/.exec(from.replace(/\$/g,'').toUpperCase());
      const b=/^([A-H])(\d+)$/.exec(to.replace(/\$/g,'').toUpperCase());
      if(!a||!b)throw Error('#REF!');
      const x0=letters.indexOf(a[1]),x1=letters.indexOf(b[1]),y0=Number(a[2]),y1=Number(b[2]);
      if(x0>x1||y0>y1||(x1-x0+1)*(y1-y0+1)>100)throw Error('#REF!');
      const out=[];
      for(let row=y0;row<=y1;row++)for(let col=x0;col<=x1;col++){
        const id=cellRef(letters[col],row);
        if(Object.prototype.hasOwnProperty.call(sheet,id))out.push(read(id)); // actual populated cells only
      }
      return out;
    };
    function parse(source){
      const a=tokens(source);let i=0;
      function take(t){if(a[i]===t){i++;return true;}return false;}
      function expect(t){if(!take(t))throw Error('#FORMULA!');}
      function expression(){let v=term();while(a[i]==='+'||a[i]==='-'){const op=a[i++];const x=term();v=op==='+'?v+x:v-x;}return v;}
      function term(){let v=unary();while(a[i]==='*'||a[i]==='/'){const op=a[i++];const x=unary();if(op==='/'&&x===0)throw Error('#DIV/0!');v=op==='*'?v*x:v/x;}return v;}
      function unary(){if(take('+'))return unary();if(take('-'))return -unary();return power();}
      function power(){let v=atom();if(take('^'))v=Math.pow(v,unary());return v;}
      function atom(){
        if(take('(')){const v=expression();expect(')');return v;}
        const x=a[i++];if(!x)throw Error('#FORMULA!');
        if(/^(?:\d|\.)/.test(x))return Number(x);
        if(limitRef.test(x)){
          if(take(':')) {
            const end=a[i++];if(!limitRef.test(end||''))throw Error('#REF!');
            return range(x,end);
          }
          return read(x);
        }
        if(/^[A-Za-z_]+$/.test(x)){
          const fn=x.toUpperCase();if(!['SUM','AVERAGE','MEDIAN','MIN','MAX'].includes(fn))throw Error('#NAME?');
          expect('(');
          const args=[];if(a[i]!==')'){do{const p=expression();args.push(...(Array.isArray(p)?p:[p]));}while(take(','));}
          expect(')');
          if(!args.length)throw Error('#VALUE!');
          if(fn==='SUM')return args.reduce((v,n)=>v+n,0);
          if(fn==='AVERAGE')return args.reduce((v,n)=>v+n,0)/args.length;
          if(fn==='MIN')return Math.min(...args);
          if(fn==='MAX')return Math.max(...args);
          const sorted=args.slice().sort((v,n)=>v-n),n=sorted.length;
          return n%2?sorted[(n-1)/2]:(sorted[n/2-1]+sorted[n/2])/2;
        }
        throw Error('#FORMULA!');
      }
      const result=expression();
      if(i!==a.length||Array.isArray(result)||!Number.isFinite(result))throw Error('#FORMULA!');
      return result;
    }
    return read(ref);
  }
  function rawTeacher(t) {
    const sheet=cellsFrom(t),answers={};
    for(const [ref,item] of Object.entries(sheet))if(item.type==='target')answers[ref]=item.raw;
    return {sheet,answers};
  }
  function newSession(id) {
    const t=template(id),base=cellsFrom(t),answers={};
    for(const [key,c] of Object.entries(base))if(c.type==='target'){
      answers[key]=c.raw;
      c.raw=''; // Practice is the default: blanks to fill with formulas
    }
    return {template:t,cells:base,answers,selected:Object.keys(answers)[0],scenario:0,mode:'practice',message:'',grade:null};
  }
  function score(session) {
    const good=[],bad=[];
    for(const [ref,formula] of Object.entries(session.answers)){
      let expected,result,reason='';
      try{expected=evaluate(session.cells,ref,{answers:session.answers});}catch(e){bad.push({ref,reason:'template: '+e.message});continue;}
      const raw=session.cells[ref].raw;
      if(!String(raw).trim().startsWith('=')){bad.push({ref,reason:'Enter an Excel-style =formula'});continue;}
      try{result=evaluate(session.cells,ref);if(Math.abs(result-expected)<=1e-7*Math.max(1,Math.abs(expected)))good.push(ref);
        else reason='Expected math differs: review references and signs';}
      catch(e){reason=e.message;}
      if(reason)bad.push({ref,reason});
    }
    return {correct:good.length,total:Object.keys(session.answers).length,good,bad};
  }
  function setCell(s,ref,value){
    if(!s.cells[ref]||!['input','target'].includes(s.cells[ref].type))throw Error('Read-only cell');
    const raw=String(value||'').trim();
    if(raw.length>220)throw Error('Cell entry too long');
    if(raw&&!raw.startsWith('=')&&!/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i.test(raw))throw Error('Enter a number or an =formula');
    s.cells[ref].raw=raw;s.grade=null;
  }
  function useScenario(s,index){
    if(!Number.isInteger(index)||index<0||index>=s.template.scenario.length)throw Error('Unknown scenario');
    const prev=s.template.scenario[s.scenario].changes;
    // Restore only affected assumption input cells to original baseline before applying the next scenario.
    const baseline=cellsFrom(s.template);
    const keys=new Set([...Object.keys(prev),...Object.keys(s.template.scenario[index].changes)]);
    for(const k of keys)if(s.cells[k]&&s.cells[k].type==='input')s.cells[k].raw=baseline[k].raw;
    for(const [k,v] of Object.entries(s.template.scenario[index].changes))
      if(s.cells[k]&&s.cells[k].type==='input')s.cells[k].raw=String(v);
    s.scenario=index;s.grade=null;
  }
  const percentRow=new Set([4,5,7,9,11,13,16,19]);
  function format(value,ref,s){
    if(!Number.isFinite(value))return '—';
    const id=s.template.id,rowNum=Number(ref.replace(/^[A-Z]+/,''));
    const percentages=id==='dcf'?percentRow.has(rowNum):
      id==='three'?[4,5,9,13,14,15].includes(rowNum):
      id==='dupont'?[7,10,11,12].includes(rowNum):
      id==='ddm'?[4,5,7].includes(rowNum):
      id==='reserves'?[6].includes(rowNum):false;
    return percentages?(value*100).toFixed(1)+'%':Number(value).toLocaleString('en-US',{maximumFractionDigits:3});
  }
  function sheetHTML(s,lang) {
    const zh=lang==='zh',t=s.template,selected=s.selected;
    const options=idNames.map(id=>'<option value="'+id+'" '+(t.id===id?'selected':'')+'>'+esc(zh?template(id).nameZH:template(id).name)+'</option>').join('');
    const scenarios=t.scenario.map((o,i)=>'<option value="'+i+'" '+(i===s.scenario?'selected':'')+'>'+esc(zh?o.nameZH:o.name)+'</option>').join('');
    let body='<tr><th class="flo-wb-corner">#</th>'+t.columns.map(c=>'<th>'+c+'</th>').join('')+'</tr>';
    for(const r of t.rows){
      body+='<tr><th class="flo-wb-line">'+r.id+'</th>';
      for(const c of t.columns){
        const ref=cellRef(c,r.id),item=s.cells[ref],isLabel=c==='A',input=item&&item.type==='input',target=item&&item.type==='target',selectedCell=selected===ref;
        if(isLabel){body+='<th class="flo-wb-label">'+esc(r.label)+'</th>';continue;}
        if(!item){body+='<td class="flo-wb-empty"></td>';continue;}
        if(item.type==='heading'){body+='<th class="flo-wb-heading">'+esc(item.raw)+'</th>';continue;}
        let value,err;
        try{value=evaluate(s.cells,ref);}catch(e){err=e.message;}
        const name=input?'input':'formula';
        body+='<td class="flo-wb-'+name+(selectedCell?' selected':'')+(err==='#BLANK!'?' empty':'')+'">'+
          '<button type="button" data-ref="'+ref+'" title="'+esc(ref+' = '+item.raw)+'">'+
          (err?(err==='#BLANK!'?'□':esc(err)):esc(format(value,ref,s)))+'</button></td>';
      }
      body+='</tr>';
    }
    const item=s.cells[selected],help=item&&item.note||'';
    return '<div class="flo-wb-head"><b>Flo · Spreadsheet Lab</b><small>'+esc(zh?t.nameZH:t.name)+'</small></div>'+
      '<p class="flo-source">'+esc(zh?t.aboutZH:t.about)+'<br><b>'+(zh?'全部为模拟数据，不是公司真实披露。':'All values are hypothetical, NOT issuer disclosures.')+'</b></p>'+
      '<div class="flo-wb-controls"><label>'+(zh?'模型':'Model')+' <select data-wb-model>'+options+'</select></label>'+
      '<label>'+(zh?'情景':'Scenario')+' <select data-wb-scenario>'+scenarios+'</select></label></div>'+
      '<div class="flo-wb-toolbar"><button type="button" data-wb-mode="practice">'+(zh?'练习：清空公式':'Practice: blank formulas')+'</button>'+
      '<button type="button" data-wb-check>'+(zh?'检查答案':'Check work')+'</button>'+
      '<button type="button" data-wb-hint>'+(zh?'提示':'Hint')+'</button>'+
      '<button type="button" data-wb-reveal>'+(zh?'显示答案':'Show formulas')+'</button>'+
      '<button type="button" data-wb-export>CSV</button>'+
      '<button type="button" data-wb-reset>'+(zh?'重置':'Reset')+'</button></div>'+
      '<div class="flo-wb-formula"><span>'+esc(selected||'')+'</span>'+
      '<input data-wb-editor aria-label="Formula or value for selected cell" autocomplete="off" spellcheck="false" value="'+esc(item?item.raw:'')+'" '+
      (!item||!['input','target'].includes(item.type)?'disabled':'')+' placeholder="=B3*(1+C4)">'+
      '<button type="button" data-wb-apply>'+(zh?'写入':'Apply')+'</button></div>'+
      '<div class="flo-wb-help">'+esc(help||(
        zh?'蓝色数值为可修改假设；紫色框为需要填写的公式。点击单元格，再在公式栏输入 =...。':
          'Blue cells are assumptions; purple cells are formula exercises. Select a cell, then type =... in the formula bar.'
      ))+'</div>'+
      '<div class="flo-wb-scroll" role="region" tabindex="0" aria-label="Spreadsheet cells"><table class="flo-wb-table"><tbody>'+body+'</tbody></table></div>'+
      '<p class="flo-wb-feedback" aria-live="polite">'+(s.grade?(zh?'正确 ':'Correct ')+s.grade.correct+' / '+s.grade.total+' · '+esc(s.message||''):esc(s.message||''))+'</p>'+
      '<p class="flo-source">'+(zh?'公式支持 A1、$B$1、SUM、AVERAGE、MEDIAN、MIN、MAX、+ − × ÷ ^；禁止宏、外部链接和脚本。CSV 导出的是计算后的数值。':
        'Supports A1, $B$1, SUM, AVERAGE, MEDIAN, MIN, MAX, + − × ÷ ^. No macros or external links. CSV exports computed values only.')+'</p>';
  }
  function safeCSV(s) {
    const data=s.template.rows.map(r=>{
      const row=[r.label];
      for(const col of s.template.columns.slice(1)){
        const ref=cellRef(col,r.id),item=s.cells[ref];
        if(!item){row.push('');continue;}
        if(item.type==='heading'){row.push(item.raw);continue;}
        try{row.push(String(evaluate(s.cells,ref)));}catch(e){row.push(e.message);}
      }
      return row;
    });
    return [['Model: '+s.template.name+' — HYPOTHETICAL DATA ONLY',...s.template.columns.slice(1)],...data]
      .map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""').replace(/^[=+\-@]/,m=>"'"+m)+'"').join(',')).join('\r\n');
  }
  const memory=new Map();
  function launch(question,lang) {
    const text=String(question||'').toLowerCase();
    const chosen=/three.?statement|3.?statement|三表/.test(text)?'three':
      /comps|ebitda|multiples?|可比|倍数/.test(text)?'comps':
      /dividend|股息|ddm/.test(text)?'ddm':
      /dupont|roe|杜邦/.test(text)?'dupont':
      /cookie|reserve|准备金/.test(text)?'reserves':'dcf';
    return {html:'<div class="flo-workbook" data-ffwb="'+chosen+'"></div>',
      workbook:true,wide:true,facts:[],links:[],mood:'happy',intents:['workbook']};
  }
  function match(question) {
    const s=String(question||'').toLowerCase();
    return /spreadsheet|worksheet|excel|workbook|spreadsheet.lab|modeling lab|model practice|practice model|financial model lab|模拟.?excel|电子表格|练习表格|建模练习|模拟表格|模型练习/i.test(s);
  }
  function mountAll(node,lang='en') {
    if(!node||!node.querySelectorAll)return;
    for(const wrapper of node.querySelectorAll('.flo-workbook[data-ffwb]'))mount(wrapper,lang);
  }
  function mount(wrapper,lang='en'){
    let session=newSession(wrapper.dataset.ffwb||'dcf');
    const paint=()=>{wrapper.innerHTML=sheetHTML(session,lang);};
    const apply=(value)=>{
      if(!session.selected)return;
      try{setCell(session,session.selected,value);session.message=(lang==='zh'?'已重算。':'Recalculated.');}
      catch(e){session.message=e.message;}
      paint();
    };
    wrapper.addEventListener('click',event=>{
      const button=event.target.closest('button');if(!button||!wrapper.contains(button))return;
      if(button.dataset.ref){session.selected=button.dataset.ref;paint();return;}
      if(button.hasAttribute('data-wb-apply')){apply(wrapper.querySelector('[data-wb-editor]').value);return;}
      if(button.hasAttribute('data-wb-check')){
        const grade=score(session);session.grade=grade;
        session.message=grade.bad.length?'First incorrect: '+grade.bad[0].ref+' — '+grade.bad[0].reason:
          'All formula outputs match the model; this is a mathematical check, not accounting audit.';
        paint();return;
      }
      if(button.hasAttribute('data-wb-hint')){
        const ref=session.selected,item=session.cells[ref];
        session.message=(item&&item.note)||('Select '+ref+': identify referenced cells and explain the sign of each term.');
        paint();return;
      }
      if(button.hasAttribute('data-wb-reveal')){
        for(const [ref,formula] of Object.entries(session.answers))session.cells[ref].raw=formula;
        session.mode='guided';session.grade=null;session.message='Instructor formulas revealed; start Practice to try again.';paint();return;
      }
      if(button.dataset.wbMode==='practice'){
        for(const ref of Object.keys(session.answers))session.cells[ref].raw='';
        session.mode='practice';session.grade=null;session.message='Practice: enter formulas in blank purple cells.';paint();return;
      }
      if(button.hasAttribute('data-wb-reset')){session=newSession(session.template.id);paint();return;}
      if(button.hasAttribute('data-wb-export')){
        const content=safeCSV(session),url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));
        const a=document.createElement('a');a.href=url;a.download='flo-'+session.template.id+'-hypothetical.csv';
        a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;
      }
    });
    wrapper.addEventListener('change',event=>{
      if(event.target.matches('[data-wb-model]')){
        session=newSession(event.target.value);paint();
      }else if(event.target.matches('[data-wb-scenario]')){
        try{useScenario(session,Number(event.target.value));session.message='Assumptions changed; recompute formulas.';}
        catch(e){session.message=e.message;}
        paint();
      }
    });
    wrapper.addEventListener('keydown',event=>{
      if(event.key==='Enter'&&event.target.matches('[data-wb-editor]')){
        event.preventDefault();apply(event.target.value);
      }
    });
    paint();memory.set(wrapper,session);
  }
  root.FFFloWorkbook={match,launch,mountAll,template,newSession,evaluate,score,setCell,useScenario,safeCSV,fcffModel:'dcf'};
  if(typeof module!=='undefined')module.exports=root.FFFloWorkbook;
})(typeof globalThis!=='undefined'?globalThis:this);
