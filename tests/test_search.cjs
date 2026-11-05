'use strict';
// Site search (web/search.js): the header box ranks every kind together; a ticker followed by words is the ticker.
const assert = require('node:assert/strict');
globalThis.FFUx = { esc: (s) => String(s), dec: (s) => s, site: async () => null };
const S = require('../web/search.js');
S._setIndex({
  site: [{ k: 'company', id: 1045810, tk: 'NVDA', name: 'NVIDIA Corp', rev: 1e11, href: '#c-1045810' }],
  sec: [{ k: 'company', id: 1608741, tk: 'QQQX', name: 'Nuveen NASDAQ 100 Dynamic Overwrite Fund', rev: -5, off: true, href: '#c-1608741' },
    { k: 'company', id: 1046179, tk: 'TSM', name: 'Taiwan Semiconductor Manufacturing Co Ltd', rev: -1, off: true, href: '#c-1046179' }],
  mgr: [], off: [], etf: [{ k: 'etf', id: 'QQQ', tk: 'QQQ', name: 'Invesco QQQ Trust, Series 1', w: 3e11, href: '#etf/QQQ' }],
  pages: [{ k: 'page', id: '#studio', tk: '', name: 'Videos: animated charts to post', href: '#studio' }, { k: 'page', id: '#flows', tk: '', name: '13F flows', href: '#flows' }],
  groups: [{ k: 'chain', id: 'cai', tk: '', name: 'AI capex', sub: 'supply chain / theme', href: '#chain-ai-capex' }] });
const first = (q) => S.headerHTML(q).flat[0];
assert.equal(first('QQQ').href, '#etf/QQQ');          // the ETF, not QQQX
assert.equal(first('tsmc').href, '#c-1046179');                     // the initials
assert.equal(first('nvda revenue').href, '#c-1045810');             // the ticker, then words about it
assert.equal(first('video').href, '#studio');
assert.equal(first('ai capex').href, '#chain-ai-capex');
assert.equal(first('13f').href, '#flows');
assert.match(S.headerHTML('QQQ').html, /class="fx-sg">ETFs</);
// a two-letter ticker before words is no ticker query: "ai capex" is the theme, not C3.ai
assert.equal(S.score({ k: 'company', tk: 'AI', name: 'C3.ai, Inc.' }, 'ai capex') < S.score({ k: 'chain', tk: '', name: 'AI capex' }, 'ai capex'), true);
console.log('Search: every kind ranked together passed');
