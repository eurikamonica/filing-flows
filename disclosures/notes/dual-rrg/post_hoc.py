"""POST-HOC robustness check for Experiment 1 (written after the pre-registered results were seen — see README.md).

The pre-registered target compares a company with its whole leave-one-out industry (equal-weighted, every member with
prices, liquid or not). The full-sample fit put a large negative weight on the industry's RS-Ratio against SPY. One
mechanical reading: in industries trending up against the market, the small, illiquid members inside the benchmark
(high beta) run further than the liquid companies that are eligible to be ranked, so the eligible company "lags its
industry" by composition rather than by anything the RRG knows. Check: the same models and scores against a benchmark
of the OTHER ELIGIBLE companies of the same industry group only (same liquidity and price filters at the origin; at
least three of them), equal-weighted.

  python notes/dual-rrg/post_hoc.py --public <rotation-history>/public --index <site>/data/index.json --out notes/dual-rrg
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import experiment as E               # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public', required=True)
    ap.add_argument('--index', required=True)
    ap.add_argument('--out', default=str(HERE))
    a = ap.parse_args()
    weeks, bench, companies, series, C, V = E.load(a.public, a.index)
    rows, bm = E.panel(weeks, bench, companies, series, C, V)
    own = {}
    for r in rows:
        i, t = r[0], r[1]
        own[(i, t)] = float(np.log(C[t][i + E.H] / C[t][i]))
    by = {}
    for r in rows:
        by.setdefault((r[0], r[2]), []).append(r)
    rows2 = []
    for (i, g), rs in by.items():
        if len(rs) < 4:                                  # the company plus at least three other eligible peers
            continue
        tot = sum(own[(i, r[1])] for r in rs)
        for r in rs:
            peers = (tot - own[(i, r[1])]) / (len(rs) - 1)
            rows2.append((*r[:-2], own[(i, r[1])] - peers, r[-1]))
    out = E.run(rows2, weeks)
    s, pairs = E.summarise(out)
    res = {'post_hoc': True, 'target': 'company minus the other eligible companies of its industry group (equal weight, >= 3)',
           'rows': len(rows2), 'models': s, 'paired_ic_differences': pairs, 'coefficients_full_sample_bp_per_sd': E.coefficients(rows2)}
    Path(a.out, 'results_post_hoc.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
    print(json.dumps({'rows': len(rows2), 'pairs': pairs, 'B3': s['B3']['ic_vs_industry'], 'B2': s['B2']['ic_vs_industry'],
                      'coef': res['coefficients_full_sample_bp_per_sd']}, indent=1))


if __name__ == '__main__':
    main()
