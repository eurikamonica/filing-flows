// Browser checks for the market UI against deterministic public SEC-shaped fixtures.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require('playwright');
const root=path.join(__dirname,'..'),seed=JSON.parse(fs.readFileSync(path.join(root,'pipeline/data/ipo/2130357.json')));
const acc=seed.accession,now=new Date().toISOString();
const known={cik:2130357,name:seed.name,form:'S-1',filed:seed.filed,accession:acc,state:'parsed',classification:'ipo_language_identified',source_url:seed.source_url,filing_count:1,analysis_accession:acc};
const missing={cik:1234567,name:'Unknown <Company>',form:'F-1',filed:'2026-10-26',accession:'0001234567-26-000001',state:'needs_review',classification:'registration_unclassified',index_url:'https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/0001234567-26-000001-index.html',filing_count:1};
let generation='one';
const status=()=>({generation,generated_at:now,feed_last_success:now,last_attempt:now,feed_state:'ok',coverage_start:'2024-01-01',quarters_completed:2,quarters_total:12,filing_count:2,states:{parsed:1,needs_review:1}});
const doc={...seed,latest_discovered:known,filings:[known],analysis_state:'parsed'};
const unparsed={...missing,periods:[],latest_discovered:missing,filings:[missing],sections:[{title:'Use of Proceeds',excerpt:'Source <script> text must be escaped.'}],source_tables:[{table_index:1,note:'Mapping requires review',rows:[['2025','2024'],['Revenue','100']]}]};
const fixture=`<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/quality-ipo.css"></head><body><main id="app" class="wrap"></main><script src="/sankey.js"></script><script src="/ipo-market.js"></script><script src="/quality-ipo.js"></script><script>let version=0;async function route(){const v=++version,m=/^#ipo(?:-(\\d+)(?:\\/(\\d{10}-\\d{2}-\\d{6}))?)?$/.exec(location.hash);await FFQualityIPO.ipo(document.getElementById('app'),()=>v===version,m&&m[1],m&&m[2]);}addEventListener('hashchange',route);route();</script></body></html>`;
const server=http.createServer((req,res)=>{const url=req.url.split('?')[0];res.setHeader('Content-Type','application/json');let data;
if(url==='/data/ipo/source.json')data={};
else if(url==='/data/ipo/index.json')data={generation,companies:[known,missing],status:status()};
else if(url==='/data/ipo/status.json')data=status();
else if(url==='/data/ipo/2130357.json'||url===`/data/ipo/filings/${acc}.json`)data=doc;
else if(url==='/data/ipo/1234567.json'||url===`/data/ipo/filings/${missing.accession}.json`)data=unparsed;
if(data){res.end(JSON.stringify(data));return;}
if(url==='/'){res.setHeader('Content-Type','text/html');res.end(fixture);return;}
const name=path.basename(url);if(!/^[\w.-]+\.(js|css)$/.test(name)){res.statusCode=404;res.end('{}');return;}
res.setHeader('Content-Type',name.endsWith('js')?'text/javascript':'text/css');res.end(fs.readFileSync(path.join(root,'web',name)));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;try{
browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=`http://127.0.0.1:${server.address().port}`;await page.goto(base+'/#ipo');await page.waitForSelector('#ipo-search');
assert.equal(await page.locator('#ipo-results tbody tr').count(),2);await page.fill('#ipo-search','unknown');assert.equal(await page.locator('#ipo-results tbody tr').count(),1);assert((await page.locator('#ipo-results').innerText()).includes('Unknown <Company>'));
await page.click('a[href="#ipo-1234567"]');await page.waitForSelector('h1:has-text("Unknown")');assert.equal(await page.locator('.qi-chart').count(),0);assert.equal(await page.locator('#ipo-period').isVisible(),false);assert((await page.locator('body').innerText()).includes('Financial values are not yet mapped'));
await page.goto(base+'/#ipo-2130357');await page.waitForSelector('.qi-chart svg');assert.equal(await page.locator('.qi-chart svg').count(),4);await page.selectOption('#ipo-period','2');assert((await page.locator('.qi-cards').innerText()).includes('4.59B'));
const pending=page.waitForEvent('download');await page.locator('.qi-chart button').first().click();const dl=await pending;assert((await dl.path()).length>0);
await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
await page.goto(base+'/#ipo-2130357/'+acc);await page.waitForSelector('.qi-chart svg');assert.equal(await page.locator('.qi-chart svg').count(),4);
await page.clock.install();await page.goto(base+'/#ipo');await page.waitForSelector('#ipo-search');generation='two';await page.clock.fastForward(61000);await page.waitForSelector('[data-ipo-update]');await page.locator('[data-ipo-update] button').click();await page.waitForSelector('#ipo-search');
assert.equal(errors.length,0,errors.join('\n'));console.log('IPO market browser: filters, escaped source tables, unparsed page, 4 charts, periods, PNG export, mobile bounds, history and live update passed');
}finally{if(browser)await browser.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;server.close();});
