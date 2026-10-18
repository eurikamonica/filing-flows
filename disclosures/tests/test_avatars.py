"""Avatars: name keys match across spellings, Congress portraits by name, owner pictures by CIK / name / file."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'automation'))
import avatars as A  # noqa: E402

LEGIS = [{'id': {'bioguide': 'P000197'}, 'name': {'first': 'Nancy', 'last': 'Pelosi', 'official_full': 'Nancy Pelosi'}},
         {'id': {'bioguide': 'T000490'}, 'name': {'first': 'David', 'last': 'Taylor', 'official_full': 'David J. Taylor'}},
         {'id': {'bioguide': 'S000001'}, 'name': {'first': 'John', 'last': 'Smith'}}, {'id': {'bioguide': 'S000002'}, 'name': {'first': 'John', 'last': 'Smith'}}]


class Avatars(unittest.TestCase):
    def test_keys(self):
        for n in ('Nancy Pelosi', 'Hon. Nancy Pelosi', 'Nancy P. Pelosi', 'PELOSI, NANCY', 'Nancy Pelosi Jr.'):
            self.assertEqual(A.person_key(n), 'nancy pelosi')
        self.assertEqual(A.org_key('BERKSHIRE HATHAWAY INC'), 'berkshire hathaway inc')

    def test_build(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {'managers': {'1067983': {'image': 'https://example.com/b.png', 'label': 'Berkshire Hathaway'}, '_note': {}},
                   'people': {'Jane Doe': {'image': 'jane.jpg'}}}
            res = A.build(d, ['Nancy Pelosi', 'David J. Taylor', 'John Smith', 'Someone Else'],
                          [{'cik': '1067983', 'name': 'BERKSHIRE HATHAWAY INC'}], legis=LEGIS, cfg=cfg)
            self.assertTrue(res['people']['nancy pelosi']['image'].endswith('/P000197.jpg'))
            self.assertEqual(res['people']['david taylor']['bioguide'], 'T000490')
            self.assertNotIn('john smith', res['people'])                  # two members share the name: no guess
            self.assertNotIn('someone else', res['people'])
            self.assertEqual(res['people']['jane doe']['image'], 'data/avatars/jane.jpg')
            self.assertEqual(res['manager_names']['berkshire hathaway inc'], '1067983')
            self.assertTrue(json.loads((Path(d) / 'data' / 'avatars.json').read_text())['managers']['1067983'])


if __name__ == '__main__':
    unittest.main()
