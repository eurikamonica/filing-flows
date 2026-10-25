// Run with Playwright installed; CHROMIUM_PATH optionally selects a system browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require('playwright');
const web = path.join(__dirname, '../web');
const fixture = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/appearance.css"></head><body><header class="top"><div class="wrap"><a class="brand">Filing Flows</a><button id="theme">Day/night</button></div></header><main id="app" class="wrap"><h1>Apple Inc.</h1><p class="intro">Appearance integration fixture</p><div class="sheet">Chart canvas</div></main><script>document.getElementById('theme').onclick=()=>document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';</script><script src="/appearance.js"></script><script src="/studio.js"></script><script src="/mascot.js"></script></body></html>`;
const ix={companies:[{cik:320193,ticker:'AAPL',name:'Apple Inc.',sector:'technology',revenue:100},{cik:19617,ticker:'JPM',name:'JPMorgan',sector:'financials',revenue:80}]};
const server=http.createServer((req,res)=>{
  if(req.url.startsWith('/data/')) { res.setHeader('content-type','application/json');res.end(JSON.stringify(req.url.endsWith('index.json')?ix:{}));return; }
  if(req.url==='/'){res.setHeader('content-type','text/html');res.end(fixture);return;}
  const name=path.basename(req.url);if(!/^[\w.-]+\.(css|js)$/.test(name)){res.statusCode=404;res.end();return;}
  const file=path.join(web,name);if(!fs.existsSync(file)){res.statusCode=404;res.end();return;}
  res.setHeader('content-type',name.endsWith('.js')?'text/javascript':'text/css');res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox','--disable-gpu']});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
    page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
    await page.goto(`http://127.0.0.1:${server.address().port}/#c-320193`);
    await page.waitForSelector('#ff-appearance-button');await page.waitForSelector('#flo-root',{state:'attached'});
    assert.equal(await page.locator('html').getAttribute('data-ff-skin'),'original');
    assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(243, 242, 238)');
    await page.locator('#ff-appearance-button').click();
    await page.locator('[name=skin]').selectOption('news');
    await page.locator('[name=texture]').selectOption('cotton');
    await page.locator('[name=holiday]').selectOption('christmas');
    await page.locator('[name=light]').selectOption('halo');
    await page.locator('[name=color]').selectOption('lavender');
    await page.locator('[name=expression]').selectOption('love');
    assert.equal(await page.locator('.ff-costume').count(),2);
    await page.locator('#ff-appearance button[value=close]').click();
    await page.locator('#theme').click();
    assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(36, 30, 23)');
    await page.reload();await page.waitForSelector('#ff-appearance-button');
    assert.equal(await page.locator('html').getAttribute('data-ff-skin'),'news');
    await page.locator('#ff-appearance-button').click();
    await page.locator('[name=follow]').selectOption('company');
    await page.waitForFunction(()=>document.documentElement.dataset.ffSkin==='company');
    await page.locator('[name=follow]').selectOption('sector');
    await page.waitForFunction(()=>document.documentElement.dataset.ffSkin==='tech');
    await page.evaluate(()=>location.hash='#c-19617');
    await page.waitForFunction(()=>document.documentElement.dataset.ffSkin==='finance');
    await page.locator('[name=video]').selectOption('news');
    assert.equal(await page.evaluate(()=>FFAppearance.videoTheme().font),'Georgia, serif');
    await page.locator('#ff-appearance-reset').click();
    assert.equal(await page.locator('html').getAttribute('data-ff-skin'),'original');
    assert.equal(await page.evaluate(()=>FFAppearance.videoTheme()),null);
    // Every wardrobe/skin choice renders without losing the original eye nodes.
    for(const key of ['skin','texture','font','numbers','chart','season','holiday','color','clothes','hat','accessory','expression','light','glow']){
      const values=await page.locator(`[name=${key}] option`).evaluateAll(opts=>opts.map(o=>o.value));
      for(const v of values)await page.locator(`[name=${key}]`).selectOption(v);
    }
    assert.equal(await page.locator('#flo-root .flo-pupils').count(),2);
    await page.setViewportSize({width:360,height:800});
    assert.ok(await page.evaluate(()=>document.querySelector('#ff-appearance').scrollWidth<=document.querySelector('#ff-appearance').clientWidth));
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#ff-appearance').evaluate(el=>el.open),false);
    await page.locator('.flo-btn').click();assert.equal(await page.locator('.flo-panel').isVisible(),true);
    if(process.env.APPEARANCE_SCREENSHOT)await page.screenshot({path:process.env.APPEARANCE_SCREENSHOT,fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('Appearance browser: persistence, light/dark, company/sector routes, all style/wardrobe choices, mobile dialog, Flo interaction passed.');
  }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
