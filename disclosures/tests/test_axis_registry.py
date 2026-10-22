"""The Rotation axis registry (app/axis_registry.py; research spec v5 §3.3, P0-02): it must describe exactly the variables
rotation.py computes and rotation.js offers, with the same price / filed split the forecasts use, and its semantic ids
must come out identical in Python and in the browser."""
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import axis_registry as AR
import rotation

JS = (ROOT / 'docs' / 'rotation.js').read_text(encoding='utf-8')
try:
    import chaos_forecast as CF
except ImportError:                                   # numpy / scikit-learn missing: the chaos checks are skipped
    CF = None


def js_pairs(name):
    m = re.search(r'const ' + name + r'=\[(.*?)\];', JS)
    return [k for k in re.findall(r"\['([^']+)',", m.group(1))]


def js_set(name):
    m = re.search(r'const ' + name + r'=new Set\(\[(.*?)\]\)', JS)
    return set(re.findall(r"'([^']+)'", m.group(1)))


class Contract(unittest.TestCase):
    def test_keys_match_rotation(self):
        keys = set(AR.AXES)
        self.assertEqual(keys - {'rel3'}, set(rotation.KEYS))
        self.assertEqual({k for k, v in AR.AXES.items() if v[2]}, set(rotation.MONTH_FIELDS))

    def test_price_and_filed_split_matches_the_chart_and_the_forecasts(self):
        price = {k for k in AR.AXES if AR.entry(k)['lag_periods'] == 0}
        self.assertEqual(price, js_set('ROT_PRICE'))
        if CF is not None:
            self.assertEqual(price, set(CF.PRICE_VARS))
            self.assertEqual({k for k in AR.AXES if AR.entry(k)['lag_periods'] == 1}, set(CF.FUND_VARS))
            self.assertEqual(AR.QUARTERLY_FORECAST, CF.FORECAST_Q)
            self.assertEqual(AR.MONTHLY_FORECAST, CF.FORECAST_M)

    def test_transforms_match_the_chart_controls(self):
        self.assertEqual(AR.SCALES, js_pairs('ROT_SCALES'))
        self.assertEqual(AR.SMOOTHING, js_pairs('ROT_SMOOTH'))
        self.assertEqual(AR.FILL, js_pairs('ROT_FILL'))

    def test_registry_entries(self):
        r = AR.registry(rotation.VARS)
        self.assertEqual(len(r['axes']), len(AR.AXES))
        f13 = next(a for a in r['axes'] if a['key'] == 'f13')
        self.assertEqual((f13['missing_policy'], f13['predictability_status'], f13['label']),
                         ('covered_periods_only', 'descriptive_only', 'Net 13F managers (buyers − sellers)'))
        self.assertTrue(all(a['predictability_status'] in AR.STATUS for a in r['axes']))


class Ids(unittest.TestCase):
    def test_semantic_id_is_about_meaning_not_data(self):
        a = AR.axis_spec(['dom', 'rel', 'volz'], 'q')
        self.assertEqual(AR.semantic_axis_spec_id(a), AR.semantic_axis_spec_id(AR.axis_spec(['dom', 'rel', 'volz'], 'q')))
        for other in (AR.axis_spec(['rel', 'dom', 'volz'], 'q'), AR.axis_spec(['dom', 'rel', 'volz'], 'q', smoothing='ewma'),
                      AR.axis_spec(['dom', 'rel', 'volz'], 'm', fill='step'), AR.axis_spec(['dom', 'rel', '__time'], 'q')):
            self.assertNotEqual(AR.semantic_axis_spec_id(a), AR.semantic_axis_spec_id(other))
        self.assertIsNone(AR.axis_spec(['dom', 'rel'], 'q', fill='step')['fill'])     # fill only means something monthly
        with self.assertRaises(ValueError):
            AR.axis_spec(['dom', 'rel'], 'q', scale='cube')

    def test_artifact_id_changes_with_the_run_not_the_axes(self):
        s = AR.semantic_axis_spec_id(AR.axis_spec(['rel', 'vola'], 'q'))
        a = AR.prediction_artifact_id(s, 'NVDA', 'next_rel', 'CY2026Q2', '1q', 'm1', 'd1', 'abc', '2026-07-01')
        b = AR.prediction_artifact_id(s, 'NVDA', 'next_rel', 'CY2026Q2', '1q', 'm1', 'd2', 'abc', '2026-07-01')
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 64)


@unittest.skipIf(subprocess.run(['node', '--version'], capture_output=True).returncode != 0, 'node not installed')
class BrowserParity(unittest.TestCase):
    def run_js(self, body):
        start, end = JS.index('const rotCanon='), JS.index('const rotSpecTag=')
        prog = JS[start:end] + body
        out = subprocess.run(['node', '-e', prog], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_sha256(self):
        texts = ['', 'abc', 'x' * 200, 'Stock vs the S&P 500 − a year earlier 漢字', 'a' * 55, 'a' * 56, 'a' * 64]
        got = self.run_js('console.log(JSON.stringify(' + json.dumps(texts) + '.map(rotSha256)))')
        self.assertEqual(got, [hashlib.sha256(t.encode('utf-8')).hexdigest() for t in texts])

    def test_semantic_ids_match_python(self):
        V = {k: {**AR.entry(k)} for k in AR.AXES}
        cases = [(['dom', 'rel', 'volz'], 'q', 'raw', 'none', None), (['rel', 'hi52'], 'm', 'rank', 'kalman', 'avail'),
                 (['revg', 'f13', '__time'], 'q', 'z', 'holt', None)]
        js = 'const V=' + json.dumps(V) + ';console.log(JSON.stringify(' + json.dumps(cases) + \
             '.map(c=>rotSha256(rotCanon(rotAxisSpec(c[0],V,c[1],c[2],c[3],c[4]))))))'
        got = self.run_js(js)
        want = [AR.semantic_axis_spec_id(AR.axis_spec(k, f, scale=s, smoothing=m, fill=fl)) for k, f, s, m, fl in cases]
        self.assertEqual(got, want)


if __name__ == '__main__':
    unittest.main()
