/* Filing Flows appearance. Local presentation preferences; no account or financial data mutations. */
(function (root) {
  'use strict';
  const KEY = 'ff:appearance:v1';
  const palettes = {
    original: ['#7a7974','#a8d1b9','#17734a','#f6c3b8','#ea6a52'],
    navy: ['#65788a','#b8cbd9','#274b6b','#e8cfaa','#b89560'],
    ice: ['#708b96','#c2e6ed','#30718b','#d4dff5','#7a95c7'],
    lavender: ['#858098','#d7cdec','#655184','#e8ccd9','#b27898'],
    rose: ['#927b80','#ecd1d9','#895463','#efd6c0','#b87961'],
    sage: ['#7c8876','#d4dfc7','#4d6e48','#e8d8b7','#ae8a53'],
    cinnabar: ['#90766b','#e8d7ba','#80533d','#f0c6ad','#b85845']
  };
  // bg, panel, ink, muted, line, accent. Each skin has its own light AND dark palette.
  const skins = {
    mint: [['#f2f5ef','#fcfdf9','#263b32','#59695e','#d3e0d5','#237857'],['#14231c','#1e3026','#edf4e9','#a9c0b1','#3e5748','#a8d1b9']],
    news: [['#eadfce','#f7efdf','#30271e','#70604f','#c9b79c','#84482e'],['#241e17','#30281f','#f0e3cc','#c4b394','#64523e','#dab78b']],
    terminal: [['#eeeee2','#faf9ee','#303222','#646550','#c7c9b0','#747346'],['#111411','#1b211b','#e9e8d4','#b9bcaa','#49503f','#d5bd72']],
    y2k: [['#d4d7d9','#f3f5f5','#24344c','#596575','#9eacb9','#315f91'],['#162337','#20334c','#e9f2ff','#adc1dc','#4b6380','#a7c7f2']],
    future: [['#eaf3f7','#f9fcfd','#19394c','#526c7c','#bfd4dc','#317b91'],['#091a2b','#112b40','#e8f6ff','#b0c8d7','#36566e','#8ccfe2']],
    finance: [['#edf0f2','#fafbfd','#233b50','#596c7e','#c4ced9','#776b45'],['#182b3e','#233d54','#f3efdf','#bdc9cf','#4b6271','#ddc28d']],
    tech: [['#edf3e9','#fbfdf8','#29432e','#5b705b','#c5d6c1','#46733e'],['#102119','#19362a','#eef6e8','#b6cdb9','#3b604a','#a9d09c']],
    notebook: [['#f5f3e7','#fffdf6','#293d50','#596d7d','#bdc8cd','#345d87'],['#1d2830','#293740','#edf1e7','#b2c4cc','#526773','#a5c6de']],
    company: [['#eef0f2','#fafbfc','#252d38','#596673','#ccd4dc','#536e8c'],['#19212c','#263240','#edf1f7','#b4c0d0','#485a70','#acc5e3']],
    consumer: [['#f5eee6','#fffaf4','#473325','#796450','#ddcbb7','#92602e'],['#2b2119','#3a2e23','#f3e8d5','#c9b598','#67533e','#dfbd84']],
    health: [['#edf4f3','#f9fdfc','#24413e','#58716e','#bfd7d2','#276f67'],['#152825','#213a35','#e5f4ef','#a9c9bf','#41665b','#93ccbc']]
  };
  const choices = {
    skin: [['original','Original / 原版'],['mint','Mint Ledger / 品牌薄荷'],['news','Financial Gazette / 报纸'],['terminal','Market Terminal / 终端'],['y2k','Millennium / 2000'],['future','Future Lab / 未来'],['finance','Capital House / 金融'],['tech','Silicon Lab / 科技'],['notebook','Notebook / 手写笔记']],
    follow: [['manual','Manual / 手动'],['company','Follow company / 跟随公司'],['sector','Follow sector / 跟随行业']],
    texture: [['none','None / 无'],['cotton','Cotton paper / 棉纸'],['news','Newsprint / 报纸'],['ruled','Ruled paper / 横线纸'],['grid','Graph paper / 方格'],['linen','Linen / 亚麻'],['metal','Brushed metal / 拉丝金属']],
    font: [['default','Original / 原版'],['serif','Editorial serif / 衬线'],['mono','Terminal mono / 等宽'],['hand','Handwritten / 手写']],
    numbers: [['default','Original / 原版'],['mono','Tabular mono / 等宽对齐'],['sans','Tabular sans / 无衬线对齐']],
    chart: [['default','Original sheet / 原版画布'],['paper','Paper sheet / 纸色画布']],
    video: [['default','Keep Studio choice / 保留工作台设置'],['page','Follow page / 跟随页面'],['news','Newspaper / 报纸'],['terminal','Terminal / 终端'],['future','Future / 未来'],['y2k','2000 desktop / 千禧桌面']],
    season: [['none','None / 无'],['auto','Local season / 当地季节'],['spring','Spring / 春'],['summer','Summer / 夏'],['autumn','Autumn / 秋'],['winter','Winter / 冬']],
    hemisphere: [['north','Northern / 北半球'],['south','Southern / 南半球']],
    holiday: [['none','None / 无'],['auto','Calendar / 自动节日'],['newyear','New Year / 元旦'],['lunar','Lunar New Year / 春节'],['valentine','Valentine / 情人节'],['halloween','Halloween / 万圣节'],['thanks','Thanksgiving / 感恩节'],['christmas','Christmas / 圣诞节']],
    weekday: [['off','Off / 关闭'],['on','Weekday moods / 每日心情']],
    market: [['off','Off / 关闭'],['weekly','Latest weekly return / 最近周回报']],
    color: Object.keys(palettes).map(k=>[k,({original:'Brand / 品牌',navy:'Navy / 海军蓝',ice:'Ice / 冰蓝',lavender:'Lavender / 薰衣草',rose:'Rose / 玫瑰',sage:'Sage / 鼠尾草',cinnabar:'Cinnabar / 朱砂'})[k]]),
    clothes: [['none','None / 无'],['vest','Vest / 马甲'],['suit','Suit / 西装'],['cardigan','Cardigan / 开衫'],['coat','Lab coat / 实验服'],['hoodie','Hoodie / 卫衣'],['scarf','Scarf / 围巾'],['cape','Cape / 斗篷'],['tang','Tang jacket / 唐装']],
    hat: [['none','None / 无'],['beret','Beret / 贝雷帽'],['graduate','Graduation / 学士帽'],['beanie','Beanie / 毛线帽'],['witch','Witch / 巫师帽'],['santa','Santa / 圣诞帽'],['flower','Flower / 花饰'],['headset','Headset / 耳机'],['moon','Moon / 月亮']],
    accessory: [['none','None / 无'],['round','Round glasses / 圆眼镜'],['square','Square glasses / 方眼镜'],['monocle','Monocle / 单片镜'],['blush','Blush / 腮红']],
    expression: [['idle','Original / 原版'],['happy','Happy / 开心'],['think','Thinking / 思考'],['worried','Concerned / 关注'],['sleepy','Sleepy / 困倦'],['surprise','Surprised / 惊讶'],['excited','Stars / 星星眼'],['love','Hearts / 爱心眼']],
    light: [['off','Off / 无'],['halo','Halo / 柔光'],['rim','Rim light / 轮廓光'],['floor','Floor light / 地面光']],
    glow: [['mint','Mint / 薄荷'],['blue','Blue / 蓝'],['purple','Purple / 紫'],['gold','Gold / 金'],['rose','Rose / 玫瑰']]
  };
  const defaults = Object.fromEntries(Object.entries(choices).map(([k,v])=>[k,v[0][0]]));
  defaults.grain = 12; defaults.power = 25;
  function sanitize(input) {
    const out = {...defaults};
    if (!input || typeof input !== 'object') return out;
    for (const [k, options] of Object.entries(choices)) if (options.some(([v])=>v===input[k])) out[k]=input[k];
    for (const k of ['grain','power']) if (Number.isFinite(+input[k])) out[k]=Math.max(0,Math.min(k==='grain'?30:60,+input[k]));
    return out;
  }
  function calendar(p, date=new Date()) {
    const m=date.getMonth()+1,d=date.getDate();
    let season=p.season, holiday=p.holiday;
    if (season==='auto') { const n=p.hemisphere==='south'?(m+5)%12+1:m; season=n>=3&&n<=5?'spring':n>=6&&n<=8?'summer':n>=9&&n<=11?'autumn':'winter'; }
    if (holiday==='auto') {
      holiday=m===1&&d===1?'newyear':m===2&&d===14?'valentine':m===10&&d===31?'halloween':m===12&&d>=24&&d<=26?'christmas':m===11&&date.getDay()===4&&d>=22&&d<=28?'thanks':'none';
      try { const parts=new Intl.DateTimeFormat('en-u-ca-chinese',{month:'numeric',day:'numeric'}).formatToParts(date); if(parts.find(x=>x.type==='month')?.value==='1'&&['1','2','3'].includes(parts.find(x=>x.type==='day')?.value)) holiday='lunar'; } catch (_) { /* unsupported calendar: manual choice remains available */ }
    }
    return {season,holiday};
  }
  function weeklyState(data, now=Date.now()) {
    const vals=data && data.c, start=Date.parse(data && data.start);
    if (!Array.isArray(vals)||!Number.isFinite(start)) return {mood:'idle',label:'Weekly prices unavailable / 周行情暂无数据'};
    let i=vals.length-1; while(i>=0&&!(Number.isFinite(vals[i])&&vals[i]>0)) i--;
    const date=start+i*7*86400000, age=now-date;
    if(i<1||age<0||age>10*86400000||!Number.isFinite(vals[i-1])||vals[i-1]<=0) return {mood:'idle',label:'Weekly prices missing or stale / 周行情缺失或过期'};
    const change=vals[i]/vals[i-1]-1;
    return {mood:change>.002?'happy':change<-.002?'worried':'idle',direction:change>.002?'up':change<-.002?'down':'flat',label:`Week of ${new Date(date).toISOString().slice(0,10)}: ${change>=0?'+':''}${(change*100).toFixed(2)}% · adjusted close / 周度复权收盘，非实时`};
  }
  function sectorSkin(sector) {
    return /financ|bank|insurance/.test(sector)?'finance':/tech|information|communication/.test(sector)?'tech':/health/.test(sector)?'health':/consumer|food|beverage/.test(sector)?'consumer':'mint';
  }
  const API={sanitize,calendar,weeklyState,sectorSkin,palettes,defaults,choices};
  if(typeof module!=='undefined'&&module.exports) module.exports=API;
  if(!root.document) return;
  const doc=root.document, html=doc.documentElement;
  const source=doc.currentScript?.src||'', base=source?source.replace(/[^/]*$/,''):'';
  let prefs; try { prefs=sanitize(JSON.parse(root.localStorage.getItem(KEY))); } catch(_){prefs=sanitize(null);}
  let context=null, indexPromise=null, market={mood:'idle',label:''}, serial=0, dialog=null, effective='original';
  const managed=['bg','surface','surface-2','ink','ink-2','muted','line','accent','accent-ink','accent-soft'];
  const dark=()=>html.dataset.theme==='dark'||(!html.dataset.theme&&root.matchMedia('(prefers-color-scheme: dark)').matches);
  const request=url=>fetch(url).then(r=>r.ok?r.json():null).catch(()=>null);
  function effectiveSkin() {
    if(prefs.follow==='manual') return prefs.skin;
    if(!context) return 'original';
    if(prefs.follow==='sector') return sectorSkin(String(context.sector||''));
    return ({AAPL:'company',MSFT:'future',NVDA:'tech',JPM:'finance',GS:'finance',KO:'consumer',PEP:'consumer'})[context.ticker]||sectorSkin(String(context.sector||''));
  }
  function idleMood() {
    if(prefs.market==='weekly') return market.mood;
    if(prefs.weekday==='on') return ['sleepy','think','idle','think','idle','happy','sleepy'][new Date().getDay()];
    return prefs.expression;
  }
  function costume() {
    const {season,holiday}=calendar(prefs); let clothes=prefs.clothes,hat=prefs.hat;
    if(clothes==='none') clothes=({christmas:'scarf',thanks:'scarf',halloween:'cape',lunar:'tang'})[holiday]||(season==='winter'?'scarf':'none');
    if(hat==='none') hat=({christmas:'santa',halloween:'witch'})[holiday]||({winter:'beanie',spring:'flower'})[season]||'none';
    return {clothes,hat,season,holiday};
  }
  function decorate() {
    const p=palettes[prefs.color],s=costume();
    const a=dress(s.clothes,p),h=hats(s.hat,p);
    if(s.holiday==='newyear')h[0]+='<path d="M17 13L27 -2L39 13Z" fill="#d1b17c"/>';
    if(s.holiday==='valentine')h[1]+='<path d="M94 56C79 47 86 39 94 45C103 39 109 48 94 56Z" fill="#cb8699"/>';
    if(s.holiday==='none'&&s.season==='autumn')h[1]+='<path d="M92 40L87 32L94 34L97 27L100 35L107 33L101 44Z" fill="#bf9167"/>';
    if(s.holiday==='none'&&s.season==='summer'&&s.hat==='none')h[0]+='<path d="M11 14H44M18 12L21 2H35L39 12Z" fill="#ddc595" stroke="#aa8f55" stroke-width="2"/>';
    doc.querySelectorAll('#flo-root .flo-half').forEach((half,i)=>{
      const svg=half.querySelector('.flo-svg'); if(!svg)return;
      let g=svg.querySelector('.ff-costume');if(!g){g=doc.createElementNS('http://www.w3.org/2000/svg','g');g.setAttribute('class','ff-costume');svg.appendChild(g);}
      g.innerHTML=a[i]+h[i]+specialEyes(i?93:27,i?86:34,p)+faceAccessory(prefs.accessory,p,i?93:27,i?86:34);
      half.dataset.light=prefs.light;
    });
    root.FFMascot?.refreshAppearance?.();
  }
  function apply() {
    effective=effectiveSkin();html.dataset.ffSkin=effective;
    managed.forEach(k=>html.style.removeProperty('--'+k));
    if(skins[effective]){
      const [bg,panel,ink,muted,line,accent]=skins[effective][dark()?1:0];
      const tokens={bg,surface:panel,'surface-2':bg,ink,'ink-2':ink,muted,line,accent,'accent-ink':accent,'accent-soft':`color-mix(in srgb, ${accent} 14%, ${panel})`};
      Object.entries(tokens).forEach(([k,v])=>html.style.setProperty('--'+k,v));
    }
    html.dataset.ffTexture=prefs.texture;html.dataset.ffFont=prefs.font;html.dataset.ffNumbers=prefs.numbers;html.dataset.ffChart=prefs.chart;
    html.style.setProperty('--ff-grain',prefs.grain/100);html.style.setProperty('--ff-light-power',prefs.power/100);
    html.style.setProperty('--ff-glow',({mint:'#a8d1b9',blue:'#87b7e0',purple:'#c1a2df',gold:'#e0c48b',rose:'#e1a9b8'})[prefs.glow]);
    html.dataset.ffColor=prefs.color;
    ['rev','mint','green','salmon','red'].forEach((k,i)=>html.style.setProperty('--ff-'+k,palettes[prefs.color][i]));
    html.dataset.ffMarket=prefs.market==='weekly'?(market.direction||'none'):'none';
    decorate();
    const status=doc.getElementById('ff-appearance-status');if(status)status.textContent=(context?`${context.ticker||context.name||context.sector} · `:'')+(prefs.follow==='manual'?'':`Following ${prefs.follow}; ${effective}. `)+(prefs.market==='weekly'?market.label:'Local preferences / 设置保存在此浏览器');
    if(dialog){dialog.querySelector('[name="skin"]').disabled=prefs.follow!=='manual';dialog.querySelector('[name="expression"]').disabled=prefs.market!=='off'||prefs.weekday==='on';}
    root.dispatchEvent(new CustomEvent('ff:appearancechange',{detail:{...prefs,effective}}));
  }
  async function syncContext() {
    const token=++serial;
    if(prefs.follow==='manual'&&prefs.market==='off'){context=null;apply();return;}
    market={mood:'idle',label:'Loading weekly prices / 正在读取周行情'};context=null;apply();
    const ix=await(indexPromise||(indexPromise=request(base+'data/index.json')));
    if(token!==serial)return;
    if(!ix)indexPromise=null;
    const hash=root.location.hash,m=/^#c-(\d+)/.exec(hash),t=/^#t-([A-Za-z0-9.-]+)/.exec(hash),s=/^#s-([a-z-]+?)(?:-CY\d{4}Q\d)?$/.exec(hash);
    context=m?(ix?.companies||[]).find(c=>+c.cik===+m[1]):t?(ix?.companies||[]).find(c=>c.ticker===t[1].toUpperCase()):s?{sector:s[1]}:null;
    market={mood:'idle',label:'Select a company for weekly market moods / 选择公司后读取周行情'};apply();
    if(prefs.market==='weekly'&&context?.ticker){
      const ticker=context.ticker;
      if(!/^[A-Za-z0-9.-]{1,15}$/.test(ticker))return;
      const data=await request(base+'disclosures/data/market/history/t/'+ticker.replace(/\./g,'-')+'.json');
      if(token!==serial)return;
      market=weeklyState(data);apply();
    }
  }
  const labels={skin:'Website style / 网站风格',follow:'Follow / 自动跟随',texture:'Background / 背景纹理',font:'Reading font / 正文字体',numbers:'Numbers / 数字字体',chart:'Chart surface / 图表画布',video:'Video production / 视频制作',season:'Season / 季节',hemisphere:'Hemisphere / 半球',holiday:'Holiday / 节日',weekday:'Weekday / 每周心情',market:'Market expression / 行情表情',color:'Flo & logo palette / 品牌配色',clothes:'Clothing / 衣服',hat:'Headwear / 头饰',accessory:'Accessories / 配件',expression:'Idle expression / 待机表情',light:'Backlight / 背光',glow:'Light color / 光色'};
  function open() {
    if(!dialog){
      dialog=doc.createElement('dialog');dialog.id='ff-appearance';dialog.setAttribute('aria-labelledby','ff-appearance-title');
      const select=k=>`<label>${labels[k]}<select name="${k}">${choices[k].map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select></label>`;
      const group=(title,keys)=>`<fieldset><legend>${title}</legend><div class="ff-appearance-grid">${keys.map(select).join('')}</div></fieldset>`;
      dialog.innerHTML=`<form method="dialog"><header><h2 id="ff-appearance-title">Appearance / 外观</h2><button value="close" aria-label="Close appearance settings">Close / 关闭</button></header><p>Original day/night is the default. Changes save locally. / 默认保留原版日夜模式。</p>${group('Website & media / 页面与媒体',['skin','follow','texture','font','numbers','chart','video'])}<label class="ff-range">Texture strength / 纹理浓度 <output id="ff-grain-value"></output><input name="grain" type="range" min="0" max="30"></label>${group('Season & calendar / 季节与日历',['season','hemisphere','holiday','weekday','market'])}<p>Calendar follows your local date. Weekly market moods use dated adjusted closes, not live daily quotes. / 日历使用本地日期；行情表情采用注明日期的周数据，不冒充实时日行情。</p>${group('Flo wardrobe / Flo 衣橱',['color','clothes','hat','accessory','expression','light','glow'])}<label class="ff-range">Backlight strength / 背光强度 <output id="ff-power-value"></output><input name="power" type="range" min="0" max="60"></label><p id="ff-appearance-status" role="status" aria-live="polite"></p><footer><button type="button" id="ff-appearance-reset">Restore defaults / 恢复默认</button><a href="#studio" id="ff-open-studio">Video Studio / 视频工作台</a></footer></form>`;
      doc.body.appendChild(dialog);
      dialog.addEventListener('input',e=>{if(!e.target.name)return;prefs=sanitize({...prefs,[e.target.name]:e.target.value});save();if(['follow','market'].includes(e.target.name))syncContext();else apply();outputs();});
      dialog.querySelector('#ff-appearance-reset').addEventListener('click',()=>{prefs=sanitize(null);save();populate();syncContext();});
      dialog.querySelector('#ff-open-studio').addEventListener('click',()=>dialog.close());
      dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
    }
    populate();apply();dialog.showModal();
  }
  function outputs(){if(dialog)for(const k of ['grain','power'])dialog.querySelector('#ff-'+k+'-value').textContent=prefs[k]+'%';}
  function populate(){if(dialog){Object.entries(prefs).forEach(([k,v])=>{const el=dialog.querySelector(`[name="${k}"]`);if(el)el.value=v;});outputs();}}
  function save(){try{root.localStorage.setItem(KEY,JSON.stringify(prefs));}catch(_){/* private mode: keep current session */}}
  function videoTheme() {
    if(prefs.video==='default')return null;
    const k=prefs.video==='page'?effective:prefs.video;
    const computed=root.getComputedStyle(html);
    const colors=prefs.video==='page'?['bg','surface','ink','muted','line','accent'].map(name=>computed.getPropertyValue('--'+name).trim()):(skins[k]||skins.mint)[['terminal','future'].includes(k)?1:0];
    const [bg,panel,ink,muted,line,accent]=colors;
    return {name:'Appearance / 外观',bg:[bg,bg,panel],grid:line,axis:muted,text:ink,muted,accent,glow:k==='future'?10:0,panel,font:k==='news'?'Georgia, serif':k==='terminal'?'"IBM Plex Mono", monospace':'"IBM Plex Sans", Arial, sans-serif',pal:['#5b7fa6','#ce964c','#59a37a','#aa89c8','#db8878','#69aaa7','#92918a','#b96c90'],q:['#59a37a','#ce964c','#db8878','#5b7fa6']};
  }
  root.FFAppearance={...API,open,idleMood,videoTheme,get:()=>({...prefs}),refresh:apply};
  function mount(){
    if(doc.getElementById('ff-appearance-button'))return;
    const anchor=doc.getElementById('theme');if(!anchor)return;
    const b=doc.createElement('button');b.id='ff-appearance-button';b.type='button';b.className='ff-appearance-button';b.textContent='Settings';b.setAttribute('aria-haspopup','dialog');b.addEventListener('click',open);anchor.after(b);
    new MutationObserver(apply).observe(html,{attributes:true,attributeFilter:['data-theme']});
    root.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',apply);
    root.addEventListener('hashchange',syncContext);root.addEventListener('ff:mascotready',decorate);
    root.addEventListener('storage',e=>{if(e.key===KEY){try{prefs=sanitize(JSON.parse(e.newValue));}catch(_){prefs=sanitize(null);}populate();syncContext();}});
    doc.addEventListener('visibilitychange',()=>{if(!doc.hidden)syncContext();});
    setInterval(()=>{if(!doc.hidden)syncContext();},5*60*1000);
    syncContext();
  }
  if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',mount);else mount();
  // Wardrobe overlays use the existing mascot's 120×120 coordinates; native eyes and pointer listeners remain intact.
  function dress(type,p){let l='',r='',dark=p[2],light=p[1],trim=p[3];
const base=(fill)=>`<path d="M15 51L27 57L39 51V76Q39 83 32 84H21Q15 83 15 77Z" fill="${fill}"/>`;
if(type==='vest'||type==='suit'){l=base(dark)+`<path d="M18 51L27 58L35 51L30 70H24Z" fill="#f5f1e5"/><path d="M27 58L30 63L27 75L24 63Z" fill="${trim}"/><path d="M15 52L23 63L19 65L27 77L35 65L31 63L39 52" fill="none" stroke="${light}" stroke-width="1"/>`;if(type==='vest')l+=`<path d="M21 58L27 61L33 58V64L27 61L21 64Z" fill="${trim}"/>`;r=`<path d="M82 98L93 103L104 98V105H82Z" fill="${dark}"/>`;}
if(type==='cardigan'){l=base(light)+`<path d="M27 58V83M18 64V78M22 66V81M32 66V81M36 64V78" stroke="${dark}" stroke-width=".6"/><circle cx="28" cy="66" r="1" fill="${dark}"/><circle cx="28" cy="73" r="1" fill="${dark}"/>`;r=`<path d="M80 96Q93 102 106 96V103H80Z" fill="${trim}"/>`;}
if(type==='coat'){l=base('#e6eee9')+`<path d="M20 52L27 65L34 52M27 65V84" stroke="${dark}" stroke-width="1"/><rect x="31" y="65" width="6" height="7" rx="1" fill="${light}"/>`;r=`<path d="M81 98L93 104L105 98V106H81Z" fill="#e6eee9"/>`;}
if(type==='hoodie'){l=base(dark)+`<path d="M16 52Q27 63 38 52M22 60V67M32 60V67M20 73H34V79H20Z" fill="none" stroke="${light}" stroke-width="1.2"/>`;r=`<path d="M80 98Q93 108 106 98" fill="none" stroke="${dark}" stroke-width="4"/>`;}
if(type==='scarf'){l=`<path d="M14 51Q27 57 41 51V59Q26 64 14 59Z M31 59H38V78H31Z" fill="${trim}"/><path d="M31 75H38M31 71H38M18 54L19 61M24 56L25 62" stroke="${dark}" stroke-width=".8"/>`;r=`<path d="M79 97Q93 103 107 97V103H79Z" fill="${trim}"/>`;}
if(type==='cape'){l=`<path d="M15 49Q9 63 8 85L25 79L42 85Q42 62 39 49L27 56Z" fill="${dark}"/><path d="M15 49L27 56L39 49" fill="none" stroke="${trim}" stroke-width="2"/><circle cx="27" cy="56" r="2" fill="${trim}"/>`;}
if(type==='tang'){l=base(p[4])+`<path d="M27 56V84M23 62H31M23 69H31M23 76H31" stroke="#e3c58e" stroke-width="1.5"/><path d="M19 51L27 57L35 51" fill="none" stroke="#e3c58e" stroke-width="2"/>`;r='<path d="M80 98Q93 104 106 98V106H80Z" fill="#ad6c5e"/><path d="M92 100V106M87 103H98" stroke="#e3c58e" stroke-width="1"/>';}
return [l,r];}
function hats(type,p){const t=p[2],a=p[3];let l='',r='';
if(type==='beret')l=`<ellipse cx="26" cy="13" rx="18" ry="6" fill="${t}"/><path d="M23 7L26 3" stroke="${t}" stroke-width="3"/>`;
if(type==='graduate')r=`<path d="M75 31L94 24L112 31L94 38Z" fill="${t}"/><path d="M106 32V43" stroke="${a}" stroke-width="2"/>`;
if(type==='beanie')l=`<path d="M12 14Q13 -2 27 0Q41 0 42 14Z" fill="${a}"/><rect x="11" y="12" width="32" height="6" rx="3" fill="${p[1]}"/><circle cx="26" cy="0" r="4" fill="${p[1]}"/>`;
if(type==='witch')l=`<path d="M8 15L24 -5L37 11L46 16Q27 23 8 15Z" fill="${t}"/><path d="M17 10L36 12" stroke="${a}" stroke-width="3"/>`;
if(type==='santa')l='<path d="M12 15Q18 -7 32 1L43 10L37 14L29 6L35 15Z" fill="#bd695f"/><rect x="11" y="12" width="31" height="6" rx="3" fill="#f5efde"/><circle cx="43" cy="10" r="4" fill="#f5efde"/>';
if(type==='flower')r=`<g fill="${a}"><circle cx="89" cy="34" r="4"/><circle cx="94" cy="30" r="4"/><circle cx="99" cy="34" r="4"/><circle cx="97" cy="39" r="4"/><circle cx="91" cy="39" r="4"/></g><circle cx="94" cy="35" r="3" fill="${p[4]}"/>`;
if(type==='headset')l=`<path d="M12 34V22Q26 10 42 23V35" fill="none" stroke="${t}" stroke-width="3"/><rect x="10" y="28" width="5" height="12" rx="2" fill="${p[1]}"/><path d="M13 37Q13 47 23 45" fill="none" stroke="${t}" stroke-width="2"/>`;
if(type==='moon')r=`<path d="M99 22A8 8 0 1 0 106 34A8 8 0 0 1 99 22Z" fill="${a}"/>`;
return [l,r];}
function faceAccessory(type,p,x,y){let s='';if(type==='round')s=`<g fill="none" stroke="${p[2]}" stroke-width=".9"><circle cx="${x-5.5}" cy="${y-1}" r="4.5"/><circle cx="${x+5.5}" cy="${y-1}" r="4.5"/><path d="M${x-1} ${y-1}h2"/></g>`;if(type==='square')s=`<g fill="none" stroke="${p[2]}" stroke-width=".9"><rect x="${x-10}" y="${y-5}" width="9" height="8" rx="1"/><rect x="${x+1}" y="${y-5}" width="9" height="8" rx="1"/><path d="M${x-1} ${y-1}h2"/></g>`;if(type==='monocle')s=`<circle cx="${x-5.5}" cy="${y-1}" r="5" fill="none" stroke="${p[4]}" stroke-width="1"/><path d="M${x-10} ${y}q-5 15 2 24" fill="none" stroke="${p[4]}" stroke-width=".5"/>`;if(type==='blush')s=`<g fill="${p[4]}" opacity=".4"><ellipse cx="${x-8}" cy="${y+7}" rx="3" ry="1.5"/><ellipse cx="${x+8}" cy="${y+7}" rx="3" ry="1.5"/></g>`;return s;}
function specialEyes(x,y,p){let stars='',hearts='';for(const cx of [x-5.5,x+5.5]){stars+=`<path d="M${cx} ${y-5}l1.5 3 3.5 .5 -2.5 2.5 .5 3.5 -3 -1.5 -3 1.5 .5 -3.5 -2.5 -2.5 3.5 -.5Z"/>`;hearts+=`<path d="M${cx} ${y+4}C${cx-8} ${y-2},${cx-3} ${y-8},${cx} ${y-3}C${cx+4} ${y-8},${cx+8} ${y-2},${cx} ${y+4}Z"/>`;}return `<g class="extra-eyes stars" fill="${p[2]}">${stars}</g><g class="extra-eyes hearts" fill="${p[4]}">${hearts}</g>`;}

})(typeof globalThis!=='undefined'?globalThis:this);
