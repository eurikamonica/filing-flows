#!/usr/bin/env node
/* The guidance hit-rate board (Disclosures → Guidance): for every company with a guidance record, how often what it then
   reported met or beat what it guided — the same record() as the company page (web/guidance.js), on the releases kept
   (holders/<T>.json → guidance_history) and the MD&A's guided figures (data/outlook/<cik>.json, pipeline/outlook.py) —
   with its latest guidance move and its forward-looking statements' counts; plus the latest guidance changes from 8-Ks.

     node scripts/guidance_board.cjs --site _site
   reads   _site/data/index.json, _site/data/c/<cik>.json, _site/data/outlook/<cik>.json, _site/disclosures/data/holders/<T>.json,
           _site/disclosures/data/market/events8k.json
   writes  _site/disclosures/data/market/guidance-board.json */
'use strict';
const fs = require('fs');
const path = require('path');
const G = require('../web/guidance.js');
const OV = require('../disclosures/docs/outlook-view.js');

function readJSON(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; } }

function board(site) {
  const ix = readJSON(path.join(site, 'data', 'index.json')) || {};
  const holdersDir = path.join(site, 'disclosures', 'data', 'holders');
  const rows = [];
  let withHistory = 0;
  for (const co of ix.companies || []) {
    if (!co.ticker || !co.cik) continue;
    const h = readJSON(path.join(holdersDir, `${co.ticker}.json`));
    const ol = readJSON(path.join(site, 'data', 'outlook', `${co.cik}.json`));
    const merged = OV.merge(h && h.guidance_history, ol);
    const latestDoc = ((ol && ol.docs) || []).find((d) => d.kind === 'mdna');
    const g = h && h.guidance;
    if (!merged && !latestDoc && !(g && g.label)) continue;
    let hr = null, said = null;
    if (merged) {
      withHistory += 1;
      const comp = readJSON(path.join(site, 'data', 'c', `${co.cik}.json`));
      try {
        const rec = G.record(merged, comp || {});
        hr = OV.hitRate(rec);
        said = rec && rec.said;
      } catch (e) { /* a record that cannot be read is left out */ }
    }
    const c = (latestDoc && latestDoc.counts) || {};
    rows.push({ t: co.ticker, cik: co.cik, name: co.name, sector: co.sector,
      n: hr ? hr.n : 0, hit: hr ? hr.hit : 0, beat: hr ? hr.beat : 0, miss: hr ? hr.miss : 0, rate: hr ? Math.round(hr.rate * 1000) / 1000 : null,
      metrics: hr ? hr.metrics.slice(0, 4) : [], raised: said ? said.raised : 0, lowered: said ? said.lowered : 0,
      g: g && g.label ? [g.label, g.filed] : null,
      fls: latestDoc ? [latestDoc.form, latestDoc.filed, c.n || 0, c.new || 0, c.updated || 0, c.dropped || 0, c.tone == null ? null : c.tone, c.hedged || 0] : null });
  }
  const ev = readJSON(path.join(site, 'disclosures', 'data', 'market', 'events8k.json')) || {};
  const recent = (ev.rows || []).filter((r) => r.guidance && r.ticker).slice(0, 150)
    .map((r) => [r.filed, r.ticker, r.cik, r.guidance, r.headline || '', r.url || '']);
  return { generated_at: new Date().toISOString(), companies: rows.length, with_record: withHistory,
    judged: rows.filter((r) => r.n).length, rows, recent };
}

if (require.main === module) {
  const i = process.argv.indexOf('--site');
  const site = i > 0 ? process.argv[i + 1] : '_site';
  const out = board(site);
  const dest = path.join(site, 'disclosures', 'data', 'market', 'guidance-board.json');
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, JSON.stringify(out));
  console.log(`guidance board: ${out.companies} companies, ${out.with_record} with a guidance record, ${out.judged} with periods judged, ${out.recent.length} recent changes`);
}
module.exports = { board };
