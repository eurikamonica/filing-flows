"""cover_shares.py: reading the share count off a 10-K / 10-Q cover page in the forms it was written in (SGML text,
HTML, several classes), what is not a count (market value, shares held by insiders, authorized shares), the date
beside it, dropping misreads, and rank_panel's merge before the first XBRL count."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import cover_shares as CS
import rank_panel as RP

HEAD = ('Indicate by check mark whether the registrant (1) has filed all reports required to be filed by Section 13 or 15(d) '
        'of the Securities Exchange Act of 1934 during the preceding 12 months. Yes [X] No [ ] ')


class Parse(unittest.TestCase):
    def test_text_filing(self):
        raw = (HEAD + 'The aggregate market value of voting stock held by non-affiliates of the Registrant was approximately '
               '$ 4,193,708,403 as of December 2, 1994. 119,891,418 shares of Common Stock Issued and Outstanding as of '
               'December 2, 1994\nDOCUMENTS INCORPORATED BY REFERENCE\nPART I\nItem 1. Business 23,000,000 shares outstanding').encode()
        self.assertEqual(CS.parse_cover(raw, '1994-12-13'), ('1994-12-02', 119891418.0, 'cover'))

    def test_html_after_insider_shares(self):
        raw = ('<html><body><p>' + HEAD + '</p><p>This calculation excludes approximately 26,237,509 shares held by directors '
               'and executive officers of the registrant.</p><p>The number of shares of common stock outstanding as of March&nbsp;6, '
               '2009 was 542,453,547.</p><p>TABLE OF CONTENTS</p><p>PART I</p></body></html>').encode()
        self.assertEqual(CS.parse_cover(raw, '2009-03-13'), ('2009-03-06', 542453547.0, 'cover'))

    def test_classes_are_summed(self):
        raw = (HEAD + 'Indicate the number of shares outstanding of each of the issuer\'s classes of common stock, as of the latest '
               'practicable date. As of January 31, 2005: Class A common stock, 100,000,000 shares outstanding; Class B common '
               'stock, 25,500,000 shares outstanding. PART I').encode()
        d, v, how = CS.parse_cover(raw, '2005-03-01')
        self.assertEqual((d, v), ('2005-01-31', 125500000.0))
        self.assertTrue(how.startswith('classes'))

    def test_millions_and_no_count(self):
        raw = (HEAD + 'As of February 1, 2007, there were 123.4 million shares of the registrant\'s common stock outstanding. PART I').encode()
        self.assertEqual(CS.parse_cover(raw, '2007-03-01')[1], 123.4e6)
        self.assertIsNone(CS.parse_cover((HEAD + 'Authorized 500,000,000 shares. PART I').encode(), '2007-03-01'))

    def test_date_falls_back_to_filing(self):
        raw = (HEAD + 'Shares of common stock outstanding: 45,000,000. PART I').encode()
        self.assertEqual(CS.parse_cover(raw, '2001-03-30'), ('2001-03-30', 45000000.0, 'cover'))

    def test_clean_drops_a_misread(self):
        pts = [['2001-01-01', 100e6, '10-K', 'a'], ['2002-01-01', 1e6, '10-K', 'b'], ['2003-01-01', 110e6, '10-K', 'c']]
        self.assertEqual([p[3] for p in CS.clean(pts)], ['a', 'c'])
        split = [['2001-01-01', 100e6, '10-K', 'a'], ['2002-01-01', 200e6, '10-K', 'b'], ['2003-01-01', 205e6, '10-K', 'c']]
        self.assertEqual(len(CS.clean(split)), 3)                       # a 2-for-1 split is a change, not a misread


class Merge(unittest.TestCase):
    def test_cover_counts_before_xbrl(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'cache' / 'cover').mkdir(parents=True)
            (Path(d) / 'cache' / 'cover' / '320193.json').write_text(json.dumps(
                [['2005-11-18', 842767948, '10-K', 'x'], ['2008-10-24', 888935123, '10-K', 'y'], ['2009-10-16', 889000000, '10-K', 'z']]))
            dei = [('2009-10-16', 889292755), ('2010-01-15', 900678473)]
            m = RP.with_cover(dei, d, '320193')
            self.assertEqual([x[0] for x in m], ['2005-11-18', '2008-10-24', '2009-10-16', '2010-01-15'])   # no double count
            self.assertEqual(RP.with_cover(dei, d, '1'), dei)
            self.assertEqual(RP.with_cover(None, d, '320193')[0][0], '2005-11-18')


if __name__ == '__main__':
    unittest.main()
