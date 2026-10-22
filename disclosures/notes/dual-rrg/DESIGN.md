# Experiment 1 — does the second RRG layer add information? (design, fixed before the run)

Research specification v5 §19, Experiment 1; §11.3 ladder B0 → B3 and G0. Written before any result was computed;
the results go to README.md and results.json unchanged by them.

**Question.** For a company's next 4 weeks against its own industry, do its RRG coordinates against that industry
(single layer) and the industry's coordinates against the market (second layer) rank companies better than plain
relative momentum — out of sample, with an interval?

**Data.** Branch `rotation-history` public/ (weekly adjusted Friday closes and volume, SPY), the site index for SIC codes.
Industry benchmark per company: `rotation_history.industry_benchmarks` — most specific of SIC4 / SIC3 / SIC2 / site
sector with five or more other priced companies; leave-one-out index (bx) and full index (bi); **equal weights** here
(no revenue history offline, so no later revenue can leak in). Today's companies: survivorship flatters every model
alike and is not corrected.

**Origins.** Every 4th Friday; training from 2006, test origins from 2012-01-06 to the last origin with a full 4-week
outcome — non-overlapping 4-week windows, so origins are the independent units. Eligible at an origin (known then):
close ≥ $3, mean weekly dollar volume over the last 13 weeks ≥ $10M, ≥ 156 weeks of closes, every feature finite.

**Primary target.** 4-week log return of the company minus that of its leave-one-out industry (stock vs industry).
Secondary: minus SPY.

**Features at the origin** (all from closes up to the origin): RRG x / y (14-week, the chart's formula) of company vs
SPY (cm), company vs its leave-one-out industry (ci), industry vs SPY (im); 13-week log momentum vs the industry
(mom13); last week's return vs the industry (rev1).

**Models** (ordinary least squares on features standardised with training rows only, refitted at every test origin on
all earlier origins whose 4-week outcome had closed):
- B0 — no information (rank IC 0 by construction; the reference for spreads).
- G0 — the mechanical RRG step (no relative move): predicts zero relative return for every company, so its rank IC
  is 0; it is the benchmark the RRG-coordinate models must beat.
- MOM — mom13 (and rev1): plain relative momentum / reversal.
- B2m — company vs SPY RRG (cm x, y): the usual single RRG.
- B2 — company vs industry RRG (ci x, y): the single layer against the right benchmark.
- B3 — B2 + industry vs SPY (im x, y): the dual RRG.
- B3+ — B3 + MOM.
- NC — negative control: B3 with the industry coordinates shuffled across industries within each origin.

**Scores.** Per test origin: Spearman rank IC of prediction vs target; top-minus-bottom quintile mean target. Means
with 95% bootstrap intervals over origins (2,000 resamples). **Primary comparison: B3 − B2 IC** (paired by origin);
then B2 − MOM, B3+ − MOM, B3 − NC. Sub-periods 2012–2018 and 2019–end for stability. No parameter is tuned on the
test origins; nothing is selected after looking.

**Reading.** A layer "adds information" only if its paired IC difference has an interval above zero and survives
the shuffle control. Gross returns, no costs; this is a ranking study, not a strategy.
