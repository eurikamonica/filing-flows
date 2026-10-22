"""Estimated industry money flows (pipeline/ioflow.py): the four columns add up and follow the BEA shares."""
import json
import os
import tempfile
from collections import defaultdict

from pipeline import ioflow

IO = {'year': 2017, 'scale_year': 2023, 'source': {'url': 'x'}, 'capex_note': 'fixed assets',
      'industries': {
          'A': {'name': 'Chips', 'output': 100e9, 'inter': .5, 'comp': .45, 'tax': .05, 'imports': .2,
                'suppliers': {'B': .5, 'A': .3}, 'fa': 'FA1'},
          'B': {'name': 'Power', 'output': 50e9, 'inter': .4, 'comp': .5, 'tax': .1, 'imports': 0,
                'suppliers': {'B': .6, '_OTHER': .4}}},
      'invest': {'suppliers': {'B': 1.0}, 'imports': 0},
      'capex': {'FA1': {'name': 'Chips', 'suppliers': {'B': .75}, 'imports': .25}},
      'sic': {'3674': [['A', 1.0]], '4911': [['B', 1.0]]}}


class Store:
    def __init__(self, recs):
        self.recs = recs

    def company(self, cik):
        return self.recs[int(cik)]


def rec(name, rev, oi, da, capex):
    q = {}
    for e in ('2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30'):
        q[e] = {'raw': {'revenue': rev / 4, 'oi': oi / 4, 'da': da / 4, 'capex': capex / 4}}
    return {'profile': {'name': name, 'tickers': [name]}, 'quarters': q}


def test_flows_add_up_and_follow_the_shares():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'io.json')
        json.dump(IO, open(path, 'w'))
        store = Store({1: rec('CHIP', 100e9, 30e9, 10e9, 20e9), 2: rec('PWR', 40e9, 8e9, 4e9, 2e9),
                       3: rec('LOSS', 10e9, -5e9, 1e9, 4e9)})
        index = [{'cik': 1, 'ticker': 'CHIP', 'name': 'Chip Co', 'sic': '3674', 'sector': 'technology', 'end': '2026-06-30'},
                 {'cik': 2, 'ticker': 'PWR', 'name': 'Power Co', 'sic': '4911', 'sector': 'utilities', 'end': '2026-06-30'},
                 {'cik': 3, 'ticker': 'LOSS', 'name': 'Loss Co', 'sic': '3674', 'sector': 'technology', 'end': '2026-06-30'}]
        n = ioflow.build(store, tmp, index, path=path)
        assert n == 6                                   # two industries, two major groups, two sectors
        d = json.load(open(os.path.join(tmp, 'gamma', 'io', '3674.json')))
        out, inn = defaultdict(float), defaultdict(float)
        for s, t, v in d['links']:
            out[s] += v
            inn[t] += v
        col = {x['id']: x['col'] for x in d['nodes']}
        tot = lambda c, side: sum(v for k, v in side.items() if col.get(k) == c)
        assert abs(tot(0, out) - tot(1, inn)) < 5          # sources = spending
        # CHIP: cash costs 100 − 30 − 10 = 60 → purchases 30, employees 27, taxes 3; capex 20; left 100 − 60 − 20 = 20;
        # LOSS: 10 + 5 − 1 = 14 → purchases 7
        assert abs(d['totals']['purchases'] - 37e9) < 1e3
        assert abs(d['totals']['capex'] - 24e9) < 1e3
        # LOSS spent 14 + 4 = 18 against 10 of revenue: the gap is borrowing or reserves
        assert abs(d['totals']['gap'] - 8e9) < 1e3
        assert any(x['id'] == 'm:gap' for x in d['nodes'])
        # spending on purchases and capex = supplying industries + imports
        assert abs(inn['k:purchases'] + inn['k:capex'] - tot(2, inn)) < 50
        imp = inn['i:imports']
        assert abs(imp - (37e9 * .2 + 24e9 * .25)) < 1e3
        # supplying industries' domestic part = listed + unlisted suppliers; PWR ($40B) is 80% of Power's $50B output
        assert abs(tot(2, inn) - imp - tot(3, inn)) < 50
        b_flow = inn['i:B']
        assert abs(inn['s:2'] - b_flow * .8) < 1e3 and abs(inn['s:unlisted'] - (b_flow * .2 + inn['i:other'])) < 1e3
        assert d['level'] == 'industry' and d['estimate'] is True
        # chips sell to chips: CHIP and LOSS split industry A's purchases (110B revenue > 100B output: revenue alone)
        a_flow = sum(v for s, t, v in d['links'] if s == 'i:A')
        assert abs(inn['s:1'] + inn['s:3'] - a_flow) < 50


def test_lenders_and_insurers_use_an_expense_ratio():
    assert ioflow.fin_ratio('6021') == .40 and ioflow.fin_ratio('6324') == .15 and ioflow.fin_ratio('6331') == .28
    assert ioflow.fin_ratio('6211') is None and ioflow.fin_ratio('3674') is None


def test_sec_group_codes_take_their_group():
    io = {'industries': {'X': {'output': 3}, 'Y': {'output': 1}}, 'sic': {'7371': [['X', 1]], '7375': [['Y', 1]]}}
    assert ioflow.bea_mix(io, '7370') == {'X': .75, 'Y': .25}
    assert ioflow.bea_mix(io, '7371') == {'X': 1}
    assert ioflow.bea_mix(io, '9999') == {}
