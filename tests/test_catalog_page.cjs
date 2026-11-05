// The data catalog page (#data, web/catalog.js): every kind in its group with its source, home, store, size and age;
// late kinds and homes missing from the build marked; what is kept twice; the checks (not catalogued, identical files).
const assert = require('node:assert/strict');
const C = require('../web/catalog.js')._t;
const cat = {
  generated_at: '2026-11-05T15:20:00+00:00', commit: 'abc123', groups: [['companies', 'Companies & filings'], ['holders', 'Funds & holders']],
  kinds: [
    { id: 'companies', group: 'companies', title: 'Company earnings charts', what: 'Every quarter', source: 'SEC XBRL', store: 'branch data', workflow: 'scan.yml', script: 'pipeline/build.py',
      cadence: 'every 15 minutes', pages: ['#home', '#c-320193', '#c-320193-eps'], files: 4100, bytes: 812e6, updated: '2026-11-05T14:34:08Z', age_h: 0.8,
      homes: [{ path: 'data/index.json', files: 1, bytes: 1.4e6 }, { path: 'data/c/', files: 4099, bytes: 810e6 }] },
    { id: 'etf', group: 'holders', title: 'ETFs', what: 'Every ETF', source: 'N-PORT', store: 'branch etf-history', workflow: 'etf.yml', cadence: 'every 4 hours',
      pages: ['#etf'], files: 3, bytes: 2e6, updated: '2026-11-03T13:00:01+00:00', age_h: 50, homes: [{ path: 'disclosures/data/etf/', files: 3, bytes: 2e6 }, { path: 'disclosures/data/etf-old/', missing: true }] },
    { id: 'holders-history', group: 'holders', title: 'Major holders since 2013', what: 'Quarter by quarter', source: '13F data sets', store: 'branch holders-history',
      workflow: 'holders-history.yml', cadence: 'daily', pages: ['#studio/k=holders&t=AAPL'], files: 0, bytes: 0, homes: [], remote: 'https://raw.githubusercontent.com/o/r/holders-history/public/' },
    { id: 'prices-daily', group: 'holders', title: 'Daily closes', what: 'x', source: 'Yahoo', store: 'main branch', workflow: 'disclosures.yml', cadence: 'daily', pages: [], files: 0, bytes: 0, homes: [], published: false },
  ],
  overlaps: [{ title: '13F positions are kept twice', kinds: ['etf'], what: 'cache and shards', plan: 'one store' }],
  unlisted: [{ path: 'data/surprise/', files: 2, bytes: 3e7 }], unlisted_folders: 1,
  duplicates: { groups: 1, bytes: 5000, top: [{ bytes: 5000, copies: 2, paths: ['data/c/1.json', 'data/c/2.json'] }] },
  totals: { data: { files: 4100, bytes: 812e6 }, 'disclosures/data': { files: 3, bytes: 2e6 } },
  branches: { used: ['etf-history', 'data'], unread: ['probe-data'] },
};
const h = C.html(cat);
assert.match(h, /<h1>Data catalog<\/h1>/);
assert.match(h, /4 kinds of data/);
assert.match(h, /814 MB in 4,103 files on the site/, 'the total');
assert.match(h, /<h2>Companies &amp; filings<\/h2>[\s\S]*<h2>Funds &amp; holders<\/h2>/, 'groups in order');
assert.match(h, /href="#c-320193-eps">company: eps</, 'a company view as a short label');
assert.match(h, /href="#c-320193">company page</);
assert.match(h, /<a href="data\/index\.json"[^>]*><code>data\/index\.json<\/code><\/a> <code>data\/c\/<\/code>/, 'a file links, a folder does not');
assert.match(h, /class="dc-miss" title="not in this build">disclosures\/data\/etf-old\//, 'a home missing from the build');
assert.match(h, /class="dc-late"[^>]*>2 days ago/, 'every 4 hours, 50 h old: late');
assert.match(h, /1 late/);
assert.match(h, /under an hour ago/);
assert.match(h, /read from the repository:<\/span> <code>holders-history\/public\/<\/code>/, 'remote data: where it is read from');
assert.match(h, /not published: the collectors’ own store/);
assert.match(h, /Kept more than once[\s\S]*13F positions are kept twice[\s\S]*One copy:<\/b> one store/);
assert.match(h, /1 folder of data no kind describes yet[\s\S]*data\/surprise\/[\s\S]*30\.0 MB/);
assert.match(h, /1 group of identical files \(5 KB repeated\)/);
assert.match(h, /1 kind · 812 MB on the site/);
assert.match(h, /1 home not in this build/);
assert.match(h, /1 data branch nothing here reads[\s\S]*<code>probe-data<\/code>[\s\S]*2 data branches are in use/);
assert.equal(C.expected('every 15 minutes'), 1);
assert.equal(C.expected('every 3 hours'), 3);
assert.equal(C.expected('daily'), 24);
assert.equal(C.expected('quarterly'), null);
assert.equal(C.late({ cadence: 'daily', age_h: 70 }), false);
assert.equal(C.late({ cadence: 'daily', age_h: 80 }), true);
assert.equal(C.size(2.5e9), '2.50 GB');
console.log('Data catalog page: groups, homes, ages, overlaps and checks passed');
