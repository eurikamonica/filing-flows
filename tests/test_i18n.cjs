// The French and Spanish versions (web/i18n.js + web/i18n-dict.js): phrases, periods, dates and amounts.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function load(lang) {
  const win = {
    location: { search: `?lang=${lang}`, href: `https://filing-flows.com/?lang=${lang}` },
    navigator: { language: 'en-US' },
  };
  const ctx = {
    window: win, URLSearchParams, URL,
    localStorage: { getItem: () => null, setItem: () => {} },
    document: { documentElement: {}, readyState: 'loading', addEventListener: () => {}, querySelector: () => null, title: '' },
    Document: function Document() {},
    MutationObserver: class { observe() {} disconnect() {} },
    NodeFilter: { SHOW_TEXT: 4, SHOW_ELEMENT: 1 },
  };
  ctx.window.localStorage = ctx.localStorage;
  vm.createContext(ctx);
  for (const f of ['i18n-dict.js', 'i18n.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'web', f), 'utf8'), ctx, { filename: f });
  }
  return win;
}
const fr = load('fr'), es = load('es'), en = load('en');
const NB = ' ', NNB = ' ';

test('English is left as written', () => {
  assert.strictEqual(en.FFLang, 'en');
  assert.strictEqual(en.FFT('Net earnings'), 'Net earnings');
});

test('menu and chart phrases', () => {
  assert.strictEqual(fr.FFT('Net earnings'), 'Résultat net');
  assert.strictEqual(es.FFT('Net earnings'), 'Beneficio neto');
  assert.strictEqual(fr.FFT('  Revenue '), '  Chiffre d’affaires ');
  assert.strictEqual(es.FFT('Latest filings'), 'Últimos informes');
  assert.strictEqual(fr.FFT('Period:'), `Période${NB}:`);
  assert.strictEqual(es.FFT('Period:'), 'Periodo:');
});

test('periods', () => {
  assert.strictEqual(fr.FFT('Q3 2026'), 'T3 2026');
  assert.strictEqual(es.FFT('Q3 2026'), '3T 2026');
  assert.strictEqual(fr.FFT('Q1 FY27'), 'T1 Ex.27');
  assert.strictEqual(es.FFT('H1 FY26'), '1S AF26');
  assert.strictEqual(fr.FFT('FY2025'), 'Ex. 2025');
  assert.strictEqual(fr.FFT('+13% Y/Y'), `+13${NNB}% a/a`);
  assert.strictEqual(es.FFT('−4.5% Q/Q'), `−4,5${NB}% t/t`);
  assert.strictEqual(fr.FFT('Q2 Holdings'), 'Q2 Holdings');             // a company's name
  assert.strictEqual(fr.FFT('vs Q2'), 'vs T2');
});

test('dates', () => {
  assert.strictEqual(fr.FFT('September 30, 2026'), '30 septembre 2026');
  assert.strictEqual(fr.FFT('March 1, 2026'), '1er mars 2026');
  assert.strictEqual(es.FFT('September 30, 2026'), '30 de septiembre de 2026');
  assert.strictEqual(fr.FFT('filed Nov 8, 2026'), 'déposé le 8 nov. 2026');
  assert.strictEqual(es.FFT('Sep 2026'), 'sept. 2026');
  assert.strictEqual(fr.FFT('May 1, 2026'), '1er mai 2026');
});

test('amounts and figures, each converted once', () => {
  assert.strictEqual(fr.FFT('€10.3B'), `10,3${NB}Md€`);
  assert.strictEqual(es.FFT('€10.3B'), `10,3${NB}mil M€`);
  assert.strictEqual(fr.FFT('$233.45'), `233,45${NB}$`);
  assert.strictEqual(fr.FFT('US$1.2B'), `1,2${NB}Md${NB}US$`);
  assert.strictEqual(es.FFT('€1,234M'), `1.234${NB}M€`);                  // not read again as "1.234"
  assert.strictEqual(es.FFT(es.FFT('€1,234M')), `1.234${NB}M€`);
  assert.strictEqual(fr.FFT('−€0.8B'), `−0,8${NB}Md€`);
  assert.strictEqual(fr.FFT('(SEK 12.5B)'), `(12,5${NB}Md${NB}SEK)`);
  assert.strictEqual(fr.FFT('1,234,567 shares'), `1${NNB}234${NNB}567 actions`);
  assert.strictEqual(es.FFT('25.3x'), '25,3x');
  assert.strictEqual(fr.FFT('3M'), '3M');                                 // a company, not a figure
  assert.strictEqual(fr.FFT('22% of revenue'), `22${NNB}% du CA`);
  assert.strictEqual(es.FFT('€0.80B · 27% of pre-tax'), `0,80${NB}mil M€ · 27${NB}% del BAI`);
  assert.strictEqual(fr.FFT('Assets €10.3B'), `Actif 10,3${NB}Md€`);
  assert.strictEqual(fr.FFT('Gross margin 47.2% → 47.9%'), `Taux de marge brute 47,2${NNB}% → 47,9${NNB}%`);
  assert.strictEqual(es.FFT('Operating income, Q4 FY25 → Q4 FY26'), 'Resultado operativo, 4T AF25 → 4T AF26');
});

test('sentences: a template, else English as written (never half translated)', () => {
  assert.strictEqual(fr.FFT('No 8-K from AAPL on file in the last four months.'), 'Aucun 8-K de AAPL au cours des quatre derniers mois.');
  assert.strictEqual(es.FFT('No Form 144 notice of $25K or more on SAP on file.'), `No consta ningún aviso Form 144 de 25${NB}mil${NB}$ o más sobre SAP.`);
  assert.strictEqual(fr.FFT('10-K for Q4 FY26'), '10-K pour T4 Ex.26');
  const s = 'Operating cash flow fell $6.3B to $28.1B, while net earnings rose $0.92B to $30.7B.';
  assert.strictEqual(fr.FFT(s), s);
  assert.strictEqual(fr.FFT('Days of cost of revenue kept as stock.'), 'Days of cost of revenue kept as stock.');
  assert.strictEqual(fr.FFT('Bank of America Corp'), 'Bank of America Corp');
  assert.strictEqual(es.FFT('$474.8B of $478.8B'), `474,8${NB}mil M$ de 478,8${NB}mil M$`);
  assert.strictEqual(fr.FFT('57.6B · 69% of Products'.replace(/^/, '$')), `57,6${NB}Md$ · 69${NNB}% de Products`);
  assert.strictEqual(fr.FFT('€5.5B · 62% of Cloud and software revenue'), `5,5${NB}Md€ · 62${NNB}% de Cloud and software revenue`);
});

test('a button’s word can differ from the same word in a table', () => {
  assert.strictEqual(fr.FFT('Close'), 'Clôture');
  assert.strictEqual(fr.FFT('Close', true), 'Fermer');
  assert.strictEqual(es.FFT('Sort by Ticker'), 'Ordenar por Símbolo');
  assert.strictEqual(fr.FFT('All 8 quarters'), 'Les 8 trimestres');           // "All" begins a phrase, it is not a line
  assert.strictEqual(fr.FFT('Latest 32 quarters'), 'Les 32 derniers trimestres');
});

test('long generated text stays as written', () => {
  const long = 'Revenue rose 13% to €10.3B as cloud grew; the operating margin widened by 2.1 points on lower restructuring costs.';
  assert.strictEqual(fr.FFT(long), long);
});

test('every phrase has a French and a Spanish version, once', () => {
  const seen = new Set();
  for (const row of fr.FFI18N) {
    assert.strictEqual(row.length, 3, row[0]);
    assert.ok(row[1] && row[2], row[0]);
    assert.ok(!seen.has(row[0]), `twice: ${row[0]}`);
    seen.add(row[0]);
  }
  for (const [re] of fr.FFI18N_PIECES) assert.doesNotThrow(() => new RegExp(re, 'g'), re);
});
