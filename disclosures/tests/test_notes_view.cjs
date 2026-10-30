// notes-view.js: the four panes render from a notes file (the synthetic 10-K of tests/test_notes.py, built by notes.py),
// with a stand-in for the page element (no browser, no network).
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const V = require('../docs/notes-view.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };

const py = ['python3', 'python'].find((p) => spawnSync(p, ['--version']).status === 0);
const out = spawnSync(py, ['-c', `import sys, json; sys.path[:0] = ['app', 'tests']; import notes as N, test_notes as T
print(json.dumps(N.build(T.synthetic(inv_gap=40), {'ticker': 'TST', 'name': 'Test Co', 'cik': 1, 'form': '10-K', 'accession': 'x'})))`],
{ cwd: path.join(__dirname, '..'), encoding: 'utf8', maxBuffer: 1 << 26 });
assert.equal(out.status, 0, out.stderr);
const d = JSON.parse(out.stdout);

function fakeEl() {
  const pane = { innerHTML: '', querySelectorAll: () => [], querySelector: () => null };
  return { pane, innerHTML: '', isConnected: true, querySelector: (s) => (s === '.nv-pane' ? pane : null), querySelectorAll: () => [], addEventListener() {} };
}
const paneOf = (tab, more) => { const el = fakeEl(); V._draw(el, d, { hub: '', tab, ...more }); return [el.innerHTML, el.pane.innerHTML]; };

const [head, read] = paneOf('read');
ok(/3 notes/.test(head) && /checks/.test(head), 'the header counts the notes and checks');
ok(/Explained difference|explained/.test(head), 'the explained difference is counted');
ok(/<svg/.test(read), 'the linkage map is drawn');
const bs = d.statements.find((x) => x.kind === 'bs').id;
const [, st] = paneOf('statements', { stmt: bs });
ok(/Inventor/.test(st) && /data-nv-note="n1"/.test(st), 'a balance sheet line links to its note');
const [, notes] = paneOf('notes');
ok(/Product Warranty/.test(notes) && /Segment Information/.test(notes), 'every note is listed');
const [, checks] = paneOf('checks');
ok(/Inventories: change on the balance sheet/.test(checks), 'the balance sheet vs cash flow check is listed');
ok(/data-nv-status="gap"/.test(checks), 'the checks can be filtered by result');

const wf = d.notes.flatMap((x) => x.tables).flatMap((t) => t.charts).find((c) => c.type === 'waterfall');
ok(wf && /<svg/.test(V._chart(wf)) && /Opening/.test(V._chart(wf)), 'a roll-forward draws as a waterfall');
const mem = d.notes.flatMap((x) => x.tables).flatMap((t) => t.charts).find((c) => c.type === 'members');
ok(mem && /Segment A/.test(V._chart(mem)), 'a split by segment names its members');
ok(V._money(1.234e9, 'USD') === '$1.2B' || /1\.2/.test(V._money(1.234e9, 'USD')), 'money in billions');
console.log(`notes-view: ${n} checks passed`);
