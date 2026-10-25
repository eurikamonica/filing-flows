"""etf_tags.py: the leverage multiple, the single stock, the region, the asset class set right, and the tags."""
import datetime as dt, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import etf_tags as T


class Leverage(unittest.TestCase):
    def x(self, *a, **k):
        L = T.leverage(*a, **k)
        return L['x'] if L['dir'] else 0

    def test_from_the_prospectus(self):
        self.assertEqual(self.x('ProShares UltraPro QQQ', 'seeks daily investment results, before fees and expenses, that correspond to three times (3x) the daily performance of the Nasdaq-100 Index'), 3)
        self.assertEqual(self.x('ProShares UltraPro Short QQQ', 'correspond to three times the inverse (-3x) of the daily performance of the Nasdaq-100 Index'), -3)
        self.assertEqual(self.x('ProShares Short S&P500', 'correspond to the inverse (-1x) of the daily performance of the S&P 500 Index'), -1)
        self.assertEqual(self.x('GraniteShares 2x Long NVDA Daily ETF', 'seeks daily investment results, before fees and expenses, of 2 times (200%) the daily percentage change of the common stock of NVIDIA Corporation (NASDAQ: NVDA).'), 2)
        self.assertEqual(self.x('Roundhill PLTR WeeklyPay ETF', 'The Funds primary investment objective is to pay weekly distributions.',
                                'swap agreements and common stock that in aggregate return approximately 1.2 times (120%) the calendar week total return of common shares of PLTR'), 1.2)
        L = T.leverage('REX NVDA Growth & Income ETF', 'to pay weekly distributions.', 'a covered call strategy and maintaining between 105% and 150% notional exposure to the Underlying Security')
        self.assertEqual((L['x'], L['lo'], T.lev_label(L)), (1.5, 1.05, '1.05–1.5× exposure'))

    def test_from_the_name(self):
        for name, cat, want in (('Direxion Daily S&P 500 Bear 3X ETF', 'Trading--Inverse Equity', -3), ('ProShares UltraShort QQQ', 'Trading--Inverse Equity', -2),
                                ('ProShares Ultra Silver', 'Trading--Leveraged Commodities', 2), ('MicroSectors U.S. Big Banks 3 Leveraged ETNs due February 17, 2039', '', 3),
                                ('ETRACS Monthly Pay 2xLeveraged US High Dividend Low Volatility ETN', '', 2), ('Direxion Daily GOOGL Bear 1X ETF', 'Trading--Inverse Equity', -1),
                                ('MicroSectors Gold -3X Inverse Leveraged ETNs due January 29, 2043', '', -3), ('AdvisorShares Ranger Equity Bear ETF', 'Trading--Inverse Equity', -1)):
            self.assertEqual(self.x(name, category=cat), want, name)

    def test_not_leverage(self):
        for name, cat in (('State Street SPDR Portfolio Short Term Corporate Bond ETF', 'Short-Term Bond'), ('Northern Trust Ultra-Short Fixed Income ETF', 'Ultrashort Bond'),
                          ('Harbor Long-Short Equity ETF', 'Long-Short Equity'), ('State Street SPDR S&P Leveraged Loan ETF', 'Bank Loan'),
                          ('Innovator U.S. Equity Ultra Buffer ETF - July', 'Defined Outcome'), ('YieldMax Ultra Option Income Strategy ETF', 'Derivative Income'),
                          ('AB Ultra Short Income ETF', 'Ultrashort Bond')):
            self.assertEqual(self.x(name, category=cat), 0, name)
        self.assertEqual(self.x('VIX Short-Term Futures ETF', category='Trading--Miscellaneous', sym='VIXY'), 0)
        self.assertEqual(self.x('ProShares Short VIX Short-Term Futures ETF', sym='SVXY'), -0.5)
        # N-CEN's leveraged/inverse answer alone (the trust's, not the fund's) is not enough
        self.assertEqual(self.x('American Customer Satisfaction ETF', category='Large Blend', multi_inverse=True), 0)
        self.assertEqual(T.leverage('Roundhill Meme Stock ETF', category='Trading--Leveraged Equity')['dir'], 1)


class Underlying(unittest.TestCase):
    def test_the_one_stock(self):
        S = {'NVDA', 'LITE', 'TSLA', 'PLTR'}
        self.assertEqual(T.underlying('GraniteShares 2x Long NVDA Daily ETF', 'of the common stock of NVIDIA Corporation (NASDAQ: NVDA).'), 'NVDA')
        self.assertEqual(T.underlying('Tradr 2X Long LITE Daily ETF', stocks=S), 'LITE')
        self.assertEqual(T.underlying('T-Rex 2X Inverse Tesla Daily Target ETF', stocks=S), 'TSLA')
        self.assertEqual(T.underlying('Roundhill PLTR WeeklyPay ETF', None, 'the calendar week total return of common shares of PLTR'), 'PLTR')
        self.assertIsNone(T.underlying('Direxion Daily Technology Top 5 Bull 2X ETF', stocks=S))
        self.assertIsNone(T.underlying('Leverage Shares 2X Long QQQ Daily ETF', stocks=S, etf_syms={'QQQ'}))


class Region(unittest.TestCase):
    def test_from_the_holdings(self):
        self.assertEqual(T.region_of({'US': 0.95, 'IE': 0.03, 'CW': 0.02}), ('us', None))
        self.assertEqual(T.region_of({'JP': 0.15, 'GB': 0.09, 'TW': 0.08, 'CA': 0.08, 'HK': 0.06, 'KR': 0.06}), ('intl', None))
        self.assertEqual(T.region_of({'TW': 0.26, 'KR': 0.23, 'IN': 0.11, 'KY': 0.11, 'CN': 0.09, 'BR': 0.03}), ('em', None))
        acwi = {'US': 0.626, 'JP': 0.05, 'GB': 0.032, 'CA': 0.031, 'TW': 0.031, 'CH': 0.023, 'FR': 0.022, 'DE': 0.02, 'IN': 0.016, 'AU': 0.015,
                'KY': 0.013, 'KR': 0.012, 'NL': 0.011, 'IE': 0.01, 'SE': 0.008}
        self.assertEqual(T.region_of(acwi), ('global', None))                         # fifteen countries listed: the rest is elsewhere
        self.assertEqual(T.region_of({'US': 0.63}), ('us', None))                      # a swap-based fund: the rest has no country
        self.assertEqual(T.region_of({'JP': 0.99, 'US': 0.001}), ('intl', 'Japan'))
        self.assertEqual(T.region_of({'KY': 0.5, 'CN': 0.4, 'HK': 0.05}), ('em', 'China'))
        self.assertEqual(T.region_of({'US': 0.1}), (None, None))


class Classes(unittest.TestCase):
    def test_set_right_by_the_category(self):
        self.assertEqual(T.fix_class('Multi-asset / alternatives', 'Ultrashort Bond', 'State Street SPDR Bloomberg 1-3 Month T-Bill ETF', False), 'Fixed income')
        self.assertEqual(T.fix_class('Fixed income', 'Derivative Income', 'YieldMax MSTR Option Income Strategy ETF', False), 'Equity')
        self.assertEqual(T.fix_class('Commodity', 'Trading--Miscellaneous', 'Invesco DB USD Index Bullish Fund ETF', False), 'Currency')
        self.assertEqual(T.fix_class('Equity', 'Multistrategy', 'NYLIM Hedge Multi-Strategy Tracker ETF', False), 'Multi-asset / alternatives')
        self.assertEqual(T.fix_class('Equity', 'Large Blend', 'Vanguard S&P 500 ETF', False), 'Equity')

    def test_pays(self):
        today = dt.date(2026, 10, 25)
        weekly = [[(today - dt.timedelta(days=7 * i)).isoformat(), 0.1] for i in range(52)]
        monthly = [[(today - dt.timedelta(days=30 * i)).isoformat(), 0.1] for i in range(12)]
        self.assertEqual((T.pays(weekly, today), T.pays(monthly, today), T.pays(monthly[:4], today)), ('weekly', 'monthly', None))


class Tags(unittest.TestCase):
    def t(self, row, L=None, under=None, **k):
        return T.tags_of(row, L or {'x': None, 'dir': 0, 'lo': None}, under, **k)

    def test_examples(self):
        schd = self.t({'name': 'Schwab US Dividend Equity ETF', 'asset_class': 'Equity', 'strategy': 'Index', 'category': 'Large Value', 'yield': 0.0324, 'act': '40', 'index_fund': True},
                      countries={'US': 0.95})
        self.assertEqual(schd, ['passive', 'div-high', 'us', 'large', 'value'])
        vym = self.t({'name': 'Vanguard High Dividend Yield ETF', 'asset_class': 'Equity', 'strategy': 'Index', 'category': 'Large Value', 'yield': 0.0237, 'index_fund': True})
        self.assertIn('div-high', vym)
        vig = self.t({'name': 'Vanguard Div Appreciation ETF', 'asset_class': 'Equity', 'category': 'Large Blend', 'yield': 0.0156, 'index_fund': True})
        self.assertIn('div-growth', vig)
        jepi = self.t({'name': 'JPMorgan Equity Premium Income ETF', 'asset_class': 'Equity', 'strategy': 'Active · options / defined outcome', 'category': 'Derivative Income', 'yield': 0.0816})
        self.assertEqual(jepi[:3], ['active', 'opt-income', 'yield8'])
        tqqq = self.t({'name': 'ProShares UltraPro QQQ', 'asset_class': 'Leveraged / inverse', 'strategy': 'Index', 'category': 'Trading--Leveraged Equity', 'yield': 0.006, 'index_fund': True},
                      T.leverage('ProShares UltraPro QQQ'))
        self.assertEqual(tqqq[:3], ['passive', 'lev:3', 'lev'])
        self.assertEqual(T.TAGS['lev:3'][0], '3× leveraged')
        sqqq = self.t({'name': 'ProShares UltraPro Short QQQ', 'asset_class': 'Leveraged / inverse', 'category': 'Trading--Inverse Equity', 'yield': 0.09, 'index_fund': True},
                      T.leverage('ProShares UltraPro Short QQQ'))
        self.assertEqual(sqqq, ['passive', 'lev:-3', 'inv'])                            # an inverse fund's interest is not an income strategy
        gld = self.t({'name': 'SPDR Gold Shares', 'asset_class': 'Commodity: precious metals', 'category': 'Commodities Focused', 'act': '33'}, trust_act=True)
        self.assertEqual(gld, ['passive', 'alt', 'alt-metals', 'trust'])
        bil = self.t({'name': 'State Street SPDR Bloomberg 1-3 Month T-Bill ETF', 'asset_class': 'Fixed income', 'category': 'Ultrashort Bond', 'index_fund': True})
        self.assertIn('bond-cash', bil)
        mbb = self.t({'name': 'iShares MBS ETF', 'asset_class': 'Fixed income', 'category': 'Government Mortgage-Backed Bond', 'index_fund': True})
        self.assertNotIn('bond-treasury', mbb); self.assertIn('bond-mbs', mbb)
        qyld = self.t({'name': 'Global X NASDAQ 100 Covered Call ETF', 'asset_class': 'Equity', 'category': 'Derivative Income', 'index_fund': True})
        self.assertNotIn('global', qyld)                                                # "Global X" is the issuer
        nvdl = self.t({'name': 'GraniteShares 2x Long NVDA Daily ETF', 'asset_class': 'Leveraged / inverse', 'strategy': 'Active', 'category': 'Trading--Leveraged Equity'},
                      T.leverage('GraniteShares 2x Long NVDA Daily ETF'), 'NVDA', countries={'US': 1.0})
        self.assertEqual(nvdl, ['active', 'lev:2', 'lev', 'single', 'us'])
        qqq = self.t({'name': 'Invesco QQQ Trust, Series 1', 'asset_class': 'Equity', 'category': 'Large Growth'},
                     text='The Fund seeks investment results that generally correspond to the price and yield performance of the Nasdaq-100 Index.')
        self.assertEqual(qqq[0], 'passive')
        self.assertEqual(self.t({'name': 'ARK Innovation ETF', 'asset_class': 'Equity', 'category': 'Mid-Cap Growth'}, text='The Fund is an actively managed exchange-traded fund')[0], 'active')
        ewj = self.t({'name': 'iShares MSCI Japan ETF', 'asset_class': 'Equity', 'category': 'Japan Stock', 'index_fund': True}, countries={'JP': 0.99})
        self.assertEqual([x for x in ewj if x in ('intl', 'cty-japan')], ['intl', 'cty-japan'])
        dbmf = self.t({'name': 'iMGP DBi Managed Futures Strategy ETF', 'asset_class': 'Multi-asset / alternatives', 'strategy': 'Active', 'category': 'Systematic Trend'})
        self.assertEqual(dbmf, ['active', 'alt', 'alt-trend'])
        for t in schd + jepi + gld + bil + ewj + dbmf:
            self.assertIn(T.TAGS[t][1], T.GROUPS)


if __name__ == '__main__':
    unittest.main()
