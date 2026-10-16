// Created by ChatGPT (OpenAI). CPU-only evidence-budget regression tests.
const assert = require('node:assert/strict');
const { passages } = require('../web/local-model.js');
const company = { name: 'Example', cik: 123 };
const period = { label: 'Q1 2026', end: '2026-03-31', form: '10-Q', filed: '2026-05-01',
  doc_url: 'https://www.sec.gov/Archives/example.htm', headline: { revenue: -142, ocf: 8 },
  nodes: [{ name: 'Reserve', v: -12, notes: [{ text: 'Litigation reserve was negative USD 12.' }, { text: 'x'.repeat(3000) }] }] };
const rows = passages(company, period, 'What is the litigation reserve?');
assert.ok(rows[0].text.includes('Litigation reserve was negative USD 12.'));
assert.ok(rows.every((p, i) => p.id === `S${i + 1}` && p.text.includes('2026-03-31') && p.text.length <= 2400));
assert.ok(rows.length <= 3 && rows.reduce((sum, p) => sum + p.text.length, 0) <= 3600);
assert.ok(rows.every((p) => !p.text.includes('x'.repeat(3000))));
assert.ok(rows.some((p) => p.text.includes('-12')));
assert.equal(passages(company, { ...period, headline: {}, nodes: [] }, 'revenue').length, 0);
assert.ok(passages(company, period, 'revenue').some((p) => p.text.includes('revenue: -142 USD.')));
console.log('Local model evidence: all checks passed');
