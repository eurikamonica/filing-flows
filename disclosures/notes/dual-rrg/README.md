# Experiment 1 — does the second RRG layer add information? (results)

Design fixed before the run: [DESIGN.md](DESIGN.md). Code: [experiment.py](experiment.py) (pre-registered) and
[post_hoc.py](post_hoc.py) (written after the results were seen). Numbers: [results.json](results.json),
[results_post_hoc.json](results_post_hoc.json). Data: branch `rotation-history` through 2026-10-23, 3,622 companies
with weekly closes and a SIC code; 3,620 got an industry benchmark (3,014 at SIC4, 278 SIC3, 313 SIC2, 15 sector).
192 test origins (every 4th Friday, 2012 – 2026), about 1,190 eligible companies per origin. Today's companies only:
survivorship flatters every model alike. Gross, no costs. Not investment advice.

## 1. Pre-registered result

Target: the company's next 4 weeks against its whole leave-one-out industry (every member with prices, equal weight).
Rank IC per origin, mean with 95% bootstrap interval over origins.

| Model | IC vs industry | 2012–2018 | 2019–2026 | Top − bottom fifth, 4 w |
|---|---:|---:|---:|---:|
| MOM (13-week momentum, last week) | +0.002 [−0.011, +0.016] | +0.009 | −0.005 | +0.10% |
| B2m (company vs SPY RRG) | +0.012 [−0.000, +0.023] | +0.013 | +0.011 | +0.21% |
| B2 (company vs industry RRG) | +0.017 [+0.005, +0.030] | +0.020 | +0.015 | +0.54% |
| **B3 (dual: + industry vs SPY)** | **+0.030 [+0.021, +0.039]** | +0.033 | +0.028 | +0.63% |
| B3+ (dual + momentum) | +0.028 [+0.018, +0.037] | +0.034 | +0.021 | +0.56% |
| NC (dual, industry coordinates shuffled) | +0.016 [+0.004, +0.028] | +0.018 | +0.015 | +0.53% |

Primary comparison **B3 − B2: +0.013 [+0.006, +0.020]**; B3 − NC +0.014 [+0.007, +0.021]. By the rule written in
advance, the second layer "adds information". Against SPY no model is distinguishable from zero.

## 2. Why that result does not mean what it seems (post hoc)

The full-sample fit gave the industry's RS-Ratio against SPY the largest weight, negative (−28 basis points per
standard deviation per 4 weeks), and an intercept of +55 bp: the eligible companies beat "their industry" by 0.55% every
4 weeks on average. Both point to composition. The benchmark holds every priced member, liquid or not; only liquid
companies (≥ $3, ≥ $10M a week) are ranked. When an industry trends up against the market, its small, illiquid,
high-beta members run further than the liquid ones, so a liquid company "lags its industry" whatever its own RRG says.

The check, written after seeing the above and labelled so: the same models and scores against the **other eligible
companies of the same industry** only (equal weight, at least three).

| Model | IC vs liquid peers | Top − bottom fifth, 4 w |
|---|---:|---:|
| MOM | +0.002 [−0.011, +0.016] | +0.00% |
| B2m | +0.007 [−0.003, +0.017] | +0.16% |
| B2 | +0.007 [−0.005, +0.019] | +0.26% |
| B3 | +0.008 [−0.004, +0.019] | +0.21% |
| B3+ | +0.008 [−0.002, +0.018] | +0.22% |

**B3 − B2: +0.001 [−0.000, +0.002].** The intercept falls to +6 bp and the industry weight to −4 bp. Against liquid
peers, neither layer ranks companies better than chance at 4 weeks, and the second layer adds nothing measurable.

## 3. Conclusion

- The pre-registered "gain" from the second RRG layer is mostly a benchmark-composition effect (liquid vs illiquid
  members of the same industry), not information about rotation. It would not survive a liquid-peer benchmark.
- Within-industry 4-week ranking from RRG coordinates or momentum: not distinguishable from zero against liquid peers.
- Consequence for the site: the dual RRG stays a descriptive chart (no forecast or probability), and its industry
  benchmark now counts only members that are liquid at each week (≥ $3, ≥ $10M weekly dollar volume over 13 weeks),
  so a chart line is not bent by illiquid members.
- What the spec's later slices would need before any probability: a point-in-time universe (delistings), costs, and
  a benchmark definition fixed before the test — this note shows how much the benchmark alone can manufacture.
