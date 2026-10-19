"""reddit_hot.py: tickers in thread titles, the heat ranking, the ApeWisdom fallback and the published file."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import reddit_hot as R

KNOWN = {'NVDA': 'NVIDIA CORP', 'AMD': 'ADVANCED MICRO DEVICES', 'ALL': 'ALLSTATE CORP', 'IT': 'GARTNER INC', 'OPEN': 'OPENDOOR',
         'BRK-B': 'BERKSHIRE HATHAWAY', 'PLTR': 'PALANTIR', 'AI': 'C3.AI'}


def thread(title, score, comments, hours_ago, sub='wallstreetbets', text=''):
    return {'sub': sub, 'id': title[:8], 'title': title, 'text': text, 'score': score, 'comments': comments,
            'created': time.time() - hours_ago * 3600, 'url': 'https://www.reddit.com/r/x/1', 'flair': ''}


class Tickers(unittest.TestCase):
    def test_cashtags_and_bare_words(self):
        self.assertEqual(R.tickers_in('$NVDA and AMD calls — ALL IN, IT is going up', KNOWN), {'NVDA', 'AMD'})   # ALL / IT are words
        self.assertEqual(R.tickers_in('Is $ALL cheap? $brk.b too', KNOWN), {'ALL', 'BRK-B'})                  # a cashtag always counts
        self.assertEqual(R.tickers_in('AI will eat software', KNOWN), set())                                   # "AI" as a word
        self.assertEqual(R.tickers_in('PLTR earnings', KNOWN, 'thinking about $AI here'), {'PLTR', 'AI'})      # cashtags in the text


class Heat(unittest.TestCase):
    def test_ranking_prefers_fresh_engagement(self):
        th = [thread('NVDA to the moon', 4000, 900, 2), thread('$AMD DD', 300, 80, 3), thread('AMD again', 100, 20, 40),
              thread('PLTR old news', 9000, 3000, 47), thread('ancient NVDA', 99999, 9999, 60)]
        rows = R.heat(th, KNOWN)
        self.assertEqual([r['ticker'] for r in rows], ['NVDA', 'AMD', 'PLTR'])   # a 47-hour-old hit fades below fresh threads
        amd = rows[1]
        self.assertEqual((amd['mentions'], amd['mentions_prev']), (1, 1))   # last 24 h vs the 24 h before; > 48 h ignored
        self.assertEqual(rows[0]['threads'][0]['title'], 'NVDA to the moon')


class Publish(unittest.TestCase):
    def test_collect_and_publish(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            R.write_json(root / 'cache' / 'prices' / 'sec-tickers.json', {'rows': [{'ticker': t.replace('-', '.'), 'title': n} for t, n in KNOWN.items()]})
            th = [thread('NVDA beats', 5000, 1200, 1), thread('$AMD', 200, 40, 5)]
            with mock.patch.object(R, 'read_reddit', return_value=(th, 'reddit', [])):
                r = R.collect(None, root)
            self.assertEqual((r['hottest'], r['source']), ('NVDA', 'reddit'))
            out = R.publish(root, root / 'market')
            self.assertEqual(out['hottest'], '$NVDA')
            pub = json.loads((root / 'market' / 'reddit.json').read_text())
            self.assertEqual(pub['hottest']['cashtag'], '$NVDA')
            self.assertEqual(pub['hottest']['name'], 'NVIDIA CORP')
            self.assertTrue(pub['hottest']['leading_since'])
            self.assertEqual(len(pub['leaders']), 1)

    def test_apewisdom_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            R.write_json(root / 'cache' / 'prices' / 'sec-tickers.json', {'rows': [{'ticker': 'BRK.B', 'title': 'BERKSHIRE'}, {'ticker': 'PLTR', 'title': 'PALANTIR'},
                                                                              {'ticker': 'SPY', 'title': 'SPDR S&P 500 ETF TRUST'}, {'ticker': 'DTE', 'title': 'DTE ENERGY CO'},
                                                                              {'ticker': 'GLD', 'title': 'SPDR GOLD TRUST'}]})
            page = {'results': [{'ticker': 'SPY', 'mentions': '900'}, {'ticker': 'DTE', 'mentions': '700'}, {'ticker': 'GLD', 'mentions': '500'},
                                {'ticker': 'PLTR', 'mentions': '310', 'upvotes': '2500', 'rank_24h_ago': '4', 'mentions_24h_ago': '120'},
                                {'ticker': 'ZZZZ', 'mentions': '999'}, {'ticker': 'BRK.B', 'mentions': '40', 'upvotes': '100'}]}
            with mock.patch.object(R, 'read_reddit', return_value=([], 'reddit', ['r/stocks/hot: HTTP Error 403: Blocked'])), \
                 mock.patch.object(R, '_get', return_value=page):
                r = R.collect(None, root)
            self.assertEqual((r['source'], r['hottest'], r['status']), ('apewisdom', 'PLTR', 'partial'))
            pub = R.publish(root, root / 'market')
            rows = json.loads((root / 'market' / 'reddit.json').read_text())['rows']
            self.assertEqual([x['ticker'] for x in rows], ['PLTR', 'BRK-B'])          # funds, options slang (DTE) and unlisted tickers left out
            self.assertEqual((rows[0]['mentions'], rows[0]['mentions_prev']), (310, 120))
            self.assertEqual(pub['hottest'], '$PLTR')


if __name__ == '__main__':
    unittest.main()
