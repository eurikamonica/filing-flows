"""docs/valuation-guide.json, the Fair value appendix's plain-language guide: every method the build can show has an
explanation (what it is, why it works, what it fits, what to watch), every stage is explained, every abbreviation the
appendix prints is written out in full in the glossary, and every method on every company page says why it applies."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_rates as BR  # noqa: E402
import valuation as V  # noqa: E402
import valuation_methods as VM  # noqa: E402
import valuation_fixture as FX  # noqa: E402

GUIDE = json.loads((Path(__file__).resolve().parents[1] / 'docs' / 'valuation-guide.json').read_text(encoding='utf-8'))


def explainer(name):
    """The guide's entry for a football row, as fairvalue-view.js finds it: exact, alias prefix, then key prefix."""
    M = GUIDE['methods']
    if name in M:
        return M[name]
    for pre, key in GUIDE.get('aliases', {}).items():
        if name.startswith(pre):
            return M[key]
    for key in M:
        if name.startswith(key):
            return M[key]
    return None


class Guide(unittest.TestCase):
    def test_every_known_method_and_stage_is_explained(self):
        names = {m for ms in VM.CANDIDATES.values() for m in ms} | {m for S in BR.STAGES.values() for m, _ in S['methods']}
        names |= {"Analysts' price targets", 'Polymarket implied price', '52-week trading range', 'Stage-weighted value (mature)',
                  'Our model (Rotation forecast)', 'Combined forecast'}
        for n in sorted(names):
            e = explainer(n)
            self.assertIsNotNone(e, n)
            for k in ('family', 'what', 'why', 'fits', 'watch'):
                self.assertTrue(len(e.get(k) or '') > 20 or k == 'family', (n, k))
        self.assertEqual(set(GUIDE['stages']), set(BR.STAGES))
        for k, s in GUIDE['stages'].items():
            self.assertEqual(s['label'], BR.STAGES[k]['label'], k)
            self.assertTrue(s['means'] and s['why'], k)
        for k in ('primer', 'startups'):
            self.assertTrue(GUIDE[k]['title'] and len(GUIDE[k]['paras']) >= 4, k)

    def test_glossary_entries_are_complete(self):
        seen = set()
        for g in GUIDE['glossary']:
            self.assertTrue(g['term'] and g['full'] and len(g['plain']) > 20, g)
            self.assertNotIn(g['term'], seen)
            seen.add(g['term'])
        self.assertGreaterEqual(sum(1 for g in GUIDE['glossary'] if g.get('abbr')), 50)

    def test_company_pages_say_why_and_spell_out_every_abbreviation(self):
        tokens = {t for g in GUIDE['glossary'] for t in g.get('abbr') or []}
        allowed = {'US', 'SPDR', 'S&P', 'ETF', 'DGS10', 'OK'}            # names, not finance terms to spell out
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            pub = Path(fx['root']) / 'public'
            for c in fx['companies']:
                A = json.loads((pub / 'c' / f"{c['cik']}.json").read_text())['appendix']
                self.assertIn(A['stage'].get('key'), GUIDE['stages'], c['cik'])
                for m in A['methods']:
                    self.assertTrue(m.get('fit') and not re.search(r'\bNone\b|\bnan\b|—\.|: —', m['fit']), (c['cik'], m['method'], m.get('fit')))
                    self.assertIsNotNone(explainer(m['method']), m['method'])
                    text = ' '.join([m.get('formula') or ''] + [s for s in m.get('steps') or [] if s] + [m['fit']])
                    for tok in set(re.findall(r'(?<![A-Za-z])[A-Z][A-Z&/]*[A-Z](?![a-z])', text)):
                        parts = [p for p in re.split(r'/', tok) if p]
                        ok = tok in tokens or 'Δ' + tok in tokens or tok in allowed or all(p in tokens or p in allowed for p in parts)
                        self.assertTrue(ok, (m['method'], tok))

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_the_view_draws_the_guide_into_the_appendix(self):
        js = Path(__file__).resolve().parents[1] / 'docs' / 'fairvalue-view.js'
        code = ("const V=require(process.argv[1]);const x=JSON.parse(require('fs').readFileSync(0,'utf8'));V.setGuide(x.guide);"
                "process.stdout.write(JSON.stringify(x.docs.map((A)=>V.appendixHtml(A))))")
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            pub = Path(fx['root']) / 'public'
            docs = [json.loads((pub / 'c' / f"{c['cik']}.json").read_text())['appendix'] for c in fx['companies']]
        res = subprocess.run(['node', '-e', code, str(js)], input=json.dumps({'guide': GUIDE, 'docs': docs}), capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        html = json.loads(res.stdout)
        for A, h in zip(docs, html):
            for part in ('Valuation from zero', 'Valuing start-ups and pre-profit companies', 'Glossary', 'What this stage means'):
                self.assertIn(part, h)
            self.assertEqual(h.count('Why it applies here.'), len(A['methods']))
            self.assertEqual(h.count('<b>What it is.</b>'), len(A['methods']) + (1 if A.get('wacc') else 0))
            if any(m['method'].startswith('DCF') for m in A['methods']):
                self.assertIn('WACC = weighted average cost of capital', h)
                self.assertIn('FCFF = free cash flow to the firm', h)
        young = [h for A, h in zip(docs, html) if A['stage'].get('key') in ('pre_revenue', 'pre_profit')]
        self.assertTrue(young and all("this company's stage" in h for h in young))


if __name__ == '__main__':
    unittest.main()
