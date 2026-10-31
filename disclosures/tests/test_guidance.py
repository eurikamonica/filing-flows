"""Guidance in earnings releases (app/guidance.py): the change words (up, down, narrower, wider, reaffirmed, initiated,
withdrawn — none missed), the guided ranges and their prior ranges, and changes found from the numbers alone.
The sentences are taken from real 8-K Exhibit 99.1 releases (Oct 2026)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import guidance as G  # noqa: E402


def one(text, **want):
    r = G.read([text] if isinstance(text, str) else text)
    return r


def item(r, metric, **kw):
    for it in r['items']:
        if it['metric'] == metric and all(it.get(k) == v for k, v in kw.items()):
            return it
    raise AssertionError(f'no {metric} {kw} in {[(i["metric"], i.get("basis"), i.get("period"), i.get("unit")) for i in r["items"]]}')


class Words(unittest.TestCase):
    def test_every_direction_is_read(self):
        cases = [
            ('Raises full-year 2026 revenue guidance.', 'raised'),
            ('The Company lifted its 2026 outlook.', 'raised'),
            ('We are boosting our full-year EBITDA guidance.', 'raised'),
            ('Ups FY26 EPS guidance.', 'raised'),
            ('The company lowered its fiscal 2026 adjusted EPS guidance to $1.10.', 'lowered'),
            ('Trims full-year outlook; now sees revenue of $4.1 billion to $4.2 billion.', 'lowered'),
            ('We are cutting our 2026 sales forecast.', 'lowered'),
            ('The Company reduced its full-year revenue guidance.', 'lowered'),
            ('◦ Narrows Adjusted EBITDA and Free Cash Flow guidance within original ranges.', 'narrowed'),
            ('We are tightening our full-year revenue guidance.', 'narrowed'),
            ('The company widened its 2026 EPS guidance range citing tariff uncertainty.', 'widened'),
            ('CMS Energy reaffirmed its 2026 adjusted earnings guidance of $3.83 to $3.90 per share.', 'reaffirmed'),
            ('The company maintained its adjusted EBITDA guidance.', 'reaffirmed'),
            ('Reiterates full-year outlook.', 'reaffirmed'),
            ('· Initiates 2027 non-GAAP EPS guidance range of $2.07-$2.09.', 'initiated'),
            ('• Introduced preliminary 2027 net sales guidance of $1 billion.', 'initiated'),
            ('The company is withdrawing its 2026 guidance.', 'withdrawn'),
            ('The Company suspended its full-year outlook given the uncertainty.', 'withdrawn'),
        ]
        for s, want in cases:
            self.assertEqual(G.read([s])['label'], want, s)

    def test_raise_and_narrow_together_and_which_end_moved(self):
        r = G.read(['Raising and narrowing full-year adjusted EPS outlook to a range of $7.23-$7.38, from $6.85-$7.05.'])
        self.assertEqual(r['tags'][:2], ['raised', 'narrowed'])
        w, ends = G.words('We are also raising the lower end of our annual revenue guidance to $5.89 billion, while maintaining the upper end at $5.92 billion.')
        self.assertEqual((sorted(w & {'raised', 'narrowed'}), ends[0]), (['narrowed', 'raised'], 'low end raised'))
        r = G.read(['We are also raising the lower end of our annual revenue guidance to $5.89 billion, while maintaining the upper end at $5.92 billion.'])
        rev = item(r, 'revenue', unit='usd')
        self.assertEqual((rev['lo'], rev['hi']), (5.89e9, 5.92e9))

    def test_not_a_change(self):
        for s in ['The decrease was the result of improved outlook on credit quality.',
                  'The outlook reflects input costs at current levels and assumes no further increases.',
                  'Third quarter revenue of $5.2 billion was above the high end of our guidance range of $4.9 billion to $5.1 billion.',
                  'IQVIA delivered another record quarter, with revenue, Adjusted EBITDA and Adjusted Diluted EPS all exceeding the high end of our expectations.',
                  'This release contains forward-looking statements, including our guidance, which involve risks.',
                  'Comcast suspended its share repurchase program beginning in the third quarter.']:
            self.assertIsNone(G.read([s])['label'], s)


class Ranges(unittest.TestCase):
    def test_from_to_ranges_and_their_change(self):
        r = G.read(['Assuming the continuation of current market conditions, CTS is increasing its previous guidance of 2026 sales from a range of '
                    '$565-$585 million to $580-$590 million and adjusted diluted EPS from a range of $2.55-$2.70 to $2.78-$2.88.'])
        rev, eps = item(r, 'revenue'), item(r, 'eps')
        self.assertEqual((rev['period'], rev['lo'], rev['hi'], rev['prior']['lo'], rev['prior']['hi']), ('FY2026', 580e6, 590e6, 565e6, 585e6))
        self.assertEqual((rev['change'], rev['range']), ('raised', 'narrowed'))
        self.assertEqual((eps['basis'], eps['unit'], eps['lo'], eps['hi'], eps['prior']['lo']), ('non-GAAP', 'ps', 2.78, 2.88, 2.55))

    def test_compared_to_prior_guidance(self):
        r = G.read(['We now expect adjusted diluted earnings per share* of $0.86 to $0.88, an increase of approximately 12% to 14% from Fiscal Year '
                    '2025, compared to our prior guidance of $0.84 to $0.87.'])
        eps = item(r, 'eps', unit='ps')
        self.assertEqual((eps['lo'], eps['hi'], eps['prior']['lo'], eps['prior']['hi'], eps['change'], eps['range']), (0.86, 0.88, 0.84, 0.87, 'raised', 'narrowed'))
        r = G.read(['GE Vernova is raising its 2026 financial guidance and now expects revenue of $46.5-$47.5 billion, up from $45.5-$46.5 billion,'])
        rev = item(r, 'revenue')
        self.assertEqual((rev['lo'], rev['prior']['hi'], rev['change'], rev.get('range')), (46.5e9, 46.5e9, 'raised', None))
        r = G.read(['Full-year 2026 adjusted EBITDA margin is now expected to be approximately 20.5 to 21.0% as compared to the previous guidance range of 20.0 to 21.0%.'])
        m = item(r, 'ebitda_margin')
        self.assertEqual((m['lo'], m['prior']['lo'], m['change'], m['range'], m['ends']), (20.5, 20.0, 'raised', 'narrowed', 'low end raised'))

    def test_plus_or_minus_respectively_and_both_bases(self):
        r = G.read(['NVIDIA’s outlook for the third quarter of fiscal 2027 is as follows:',
                    '• Revenue is expected to be $108.0 billion, plus or minus 2%.',
                    '• GAAP and non-GAAP gross margins are expected to be 74.0%, plus or minus 50 basis points.',
                    '• GAAP and non-GAAP operating expenses are expected to be approximately $9.2 billion and $9.0 billion, respectively.',
                    'For the full year fiscal 2027, NVIDIA expects GAAP and non-GAAP tax rates to be between 16.0% and 18.0%.'])
        rev = item(r, 'revenue')
        self.assertEqual((rev['period'], rev['lo'], rev['hi']), ('Q3 FY2027', 105.84e9, 110.16e9))
        self.assertEqual((item(r, 'gross_margin', basis='GAAP')['lo'], item(r, 'gross_margin', basis='non-GAAP')['hi']), (73.5, 74.5))
        self.assertEqual((item(r, 'opex', basis='GAAP')['lo'], item(r, 'opex', basis='non-GAAP')['lo']), (9.2e9, 9.0e9))
        self.assertEqual(item(r, 'tax_rate', basis='GAAP')['period'], 'FY2027')

    def test_bounds_deltas_growth_and_loss(self):
        r = G.read(['For 2026, we expect full-year revenue of at least $290 million, representing growth of at least 29%.'])
        self.assertEqual((item(r, 'revenue', unit='usd')['bound'], item(r, 'revenue', unit='growth')['lo']), ('min', 29.0))
        r = G.read(['The Company is increasing its Adjusted EBITDA guidance for the full year of 2026 to a range of $820 million to $840 million, '
                    'which represents an increase of $30 million at the midpoint of the range from its guidance in July 2026.'])
        e = item(r, 'ebitda')
        self.assertEqual((e['lo'], e['hi'], e['delta']['v'], e['period']), (820e6, 840e6, 30e6, 'FY2026'))
        r = G.read(['For the full year, we now expect an adjusted loss per share between ($5.50) and ($5.00).'])
        self.assertEqual((item(r, 'eps')['lo'], item(r, 'eps')['hi']), (-5.5, -5.0))

    def test_outlook_table_prior_and_updated_columns(self):
        r = G.read(['Full-Year 2026 Guidance', 'Previous Guidance Updated Guidance', '($ in millions, except per share data)',
                    'Net operating revenues $6,410 to $6,490 $6,450 to $6,500', 'Adjusted EBITDA $1,365 to $1,395 $1,395 to $1,415',
                    'Adjusted earnings per share $6.02 to $6.25 $6.23 to $6.37'])
        rev, eps = item(r, 'revenue'), item(r, 'eps')
        self.assertEqual((rev['lo'], rev['hi'], rev['prior']['lo'], rev['change'], rev['range']), (6450e6, 6500e6, 6410e6, 'raised', 'narrowed'))
        self.assertEqual((eps['lo'], eps['prior']['hi']), (6.23, 6.25))

    def test_results_are_not_guidance(self):
        r = G.read(['Example Corp Reports Third Quarter 2026 Results',
                    'Revenue for the third quarter of 2026 was $812 million, compared to $650 million for the third quarter of 2025.',
                    'For the fourth quarter of 2026, the Company expects revenue in the range of $850 million to $870 million.'])
        self.assertEqual([(i['period'], i['lo']) for i in r['items'] if i['metric'] == 'revenue' and i['unit'] == 'usd'], [('Q4 2026', 850e6)])

    def test_a_comparison_base_does_not_date_the_guide(self):
        # Amazon, Oct 2026: the guided quarter is the section's; the quarter of the figure it is compared with is not
        r = G.read(['Fourth Quarter 2026 Guidance',
                    '• Net sales are expected to be between $240.0 billion and $247.0 billion, or to grow between 12% and 16% '
                    'compared with fourth quarter 2025.',
                    '• Operating income is expected to be between $28.5 billion and $33.5 billion, compared with $25.0 billion in '
                    'fourth quarter 2025.',
                    '• We continue to expect 2026 cash capital expenditures to be approximately $220 billion.'])
        self.assertEqual(item(r, 'revenue', unit='usd')['period'], 'Q4 2026')
        self.assertEqual(item(r, 'revenue', unit='growth')['period'], 'Q4 2026')
        self.assertEqual((item(r, 'operating_income')['period'], item(r, 'operating_income')['lo']), ('Q4 2026', 28.5e9))
        self.assertEqual(item(r, 'capex')['period'], 'FY2026')
        # a quarter named before the metric with another figure in between belongs to that figure
        r = G.read(['“We delivered 39% revenue growth in Q3 ($184 billion run rate) and expect revenue growth of over 40% in 2027,” said the CEO.'])
        self.assertEqual(item(r, 'revenue', unit='growth')['period'], 'FY2027')


class Numbers(unittest.TestCase):
    def test_compare(self):
        self.assertEqual({k: v for k, v in G.compare({'lo': 10.1, 'hi': 10.2}, {'lo': 10.0, 'hi': 10.3}).items() if k in ('change', 'range')},
                         {'change': 'reaffirmed', 'range': 'narrowed'})
        self.assertEqual(G.compare({'lo': 2.0, 'hi': 2.4}, {'lo': 2.1, 'hi': 2.3})['range'], 'widened')
        self.assertEqual(G.compare({'lo': 4.0, 'hi': 4.1}, {'lo': 4.1, 'hi': 4.2})['change'], 'lowered')
        c = G.compare({'lo': 5.89, 'hi': 5.92}, {'lo': 5.85, 'hi': 5.92})
        self.assertEqual((c['change'], c['range'], c['ends']), ('raised', 'narrowed', 'low end raised'))

    def test_a_silent_change_is_found_against_the_earlier_release(self):
        now = G.read(['For the full year 2026, the company expects revenue of $3.00 billion to $3.10 billion.'])['items']
        before = G.read(['For the full year 2026, the company expects revenue of $3.05 billion to $3.25 billion.'])['items']
        rev = next(i for i in G.diff(now, [('2026-07-30', before)]) if i['metric'] == 'revenue')
        self.assertEqual((rev['change'], rev['range'], rev['prior']['src'], rev['prior']['filed']), ('lowered', 'narrowed', 'earlier release', '2026-07-30'))
        self.assertEqual(G.tags_of([rev]), ['lowered', 'narrowed'])
        self.assertEqual(G.phrase(['raised', 'narrowed']), 'raised and narrowed')
        new = G.diff(G.read(['The company expects fourth quarter 2026 revenue of $1.0 billion to $1.1 billion.'])['items'], [])
        self.assertEqual(new[0]['change'], 'new')


class Tables(unittest.TestCase):
    def rows(self, r):
        return sorted((i['metric'], i.get('basis') or '', i['period'], i['lo'], i['hi']) for i in r['items'])

    def test_gaap_and_non_gaap_columns(self):
        # Micron: the period on its own line, then a GAAP and a non-GAAP column heading; revenue the same in both
        r = G.read(['Business Outlook', 'The following table presents Micron’s guidance for the fourth quarter of 2026:', 'FQ4-26',
                    'GAAP (1) Outlook', 'Non-GAAP (2) Outlook', 'Revenue', '$50.0 billion ± $1.0 billion $50.0 billion ± $1.0 billion',
                    'Gross margin', 'Approximately 86% Approximately 86%', 'Operating expenses', 'Approximately $1.86 billion Approximately $1.65 billion'])
        rows = self.rows(r)
        self.assertIn(('opex', 'GAAP', 'Q4 FY2026', 1.86e9, 1.86e9), rows)
        self.assertIn(('opex', 'non-GAAP', 'Q4 FY2026', 1.65e9, 1.65e9), rows)
        self.assertIn(('revenue', '', 'Q4 FY2026', 49e9, 51e9), rows)
        # Intel: one header line names the quarter and both bases; "($B)" scales the row
        r = G.read(['Business Outlook', 'Q4 2026 GAAP Non-GAAP', 'Revenue ($B) $15.0 - $16.0', 'Gross margin 37.1% 38.0%',
                    'Earnings (loss) per share attributable to Intel—diluted $(0.07) $0.30'])
        rows = self.rows(r)
        self.assertIn(('revenue', '', 'Q4 2026', 15e9, 16e9), rows)
        self.assertIn(('gross_margin', 'non-GAAP', 'Q4 2026', 38.0, 38.0), rows)
        self.assertIn(('eps', 'GAAP', 'Q4 2026', -0.07, -0.07), rows)

    def test_column_titles_on_their_own_lines_and_a_not_applicable_cell(self):
        # Sandisk: the scale, then "GAAP(1)" and "Non-GAAP(1)" each on a line (not the end of the section); "N/A" in the
        # GAAP column leaves the figure to the non-GAAP one
        r = G.read(['Sandisk Reports Fiscal First Quarter 2027 Financial Results', 'Business Outlook for Fiscal Second Quarter of 2027',
                    '(in millions, except per share amounts)', 'GAAP(1)', 'Non-GAAP(1)', 'Revenue $12,200 - $12,600 $12,200 - $12,600',
                    'Gross Margin 84.4% - 85.4% 84.5% - 85.5%', 'Operating Expenses $677 - $745 $540 - $560',
                    'Diluted Net Income Per Share N/A $55.00 - $57.00'], filed='2026-10-29')
        rows = self.rows(r)
        self.assertIn(('gross_margin', 'GAAP', 'Q2 FY2027', 84.4, 85.4), rows)
        self.assertIn(('gross_margin', 'non-GAAP', 'Q2 FY2027', 84.5, 85.5), rows)
        self.assertIn(('opex', 'GAAP', 'Q2 FY2027', 677e6, 745e6), rows)
        self.assertIn(('opex', 'non-GAAP', 'Q2 FY2027', 540e6, 560e6), rows)
        self.assertIn(('eps', 'non-GAAP', 'Q2 FY2027', 55.0, 57.0), rows)
        self.assertNotIn(('eps', '', 'Q2 FY2027', 55.0, 57.0), rows)
        self.assertTrue(any(x[0] == 'revenue' and x[3] == 12.2e9 and x[1] != 'non-GAAP' for x in rows))

    def test_fiscal_quarter_with_dash(self):
        self.assertEqual(G.period('FQ1-27 GAAP Outlook', None), 'Q1 FY2027')

    def test_a_definition_in_passing_is_not_guided(self):
        r = G.read(['• Core Adjusted EBITDA, which is Adjusted EBITDA less lease revenues, is expected to be between $37.35 billion and $37.45 billion.'])
        self.assertEqual([i['metric'] for i in r['items']], ['ebitda'])

    def test_a_release_that_names_no_year(self):
        # "Q3 Results …" and bullets naming no period: the year of the filing; not passed on as the release's own naming
        r = G.read(['Q3 Results Demonstrate Growth', 'Raising Guidance', '• Effective tax rate is now expected to be between 24% and 25%.'], filed='2026-10-28')
        self.assertEqual((r['items'][0]['period'], r['reported']), ('FY2026', None))


if __name__ == '__main__':
    unittest.main()
