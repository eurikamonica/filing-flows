"""Tags for every ETF (used by etf.build; shown on the screener and each ETF's page).

  Management   passive (an index fund: N-CEN's IS_INDEX, a trust holding the asset, an ETN on an index) or active
  Leverage     the daily (or weekly) multiple, signed: 2×, 3×, −1×, −2×, −3×, 1.5×… read from the prospectus objective
               ("three times the inverse (-3x) of the daily performance"), else the strategy text ("approximately 1.2
               times (120%)", "between 105% and 150% notional exposure"), else the name ("Bull 3X", "UltraPro Short");
               bond funds' "short-term" / "ultra-short" and "long/short" are not leverage. Single-stock funds name
               their stock (the objective's "(NASDAQ: NVDA)", a ticker in the name).
  Income       high dividend (a stock ETF yielding 3%+ over 12 months), dividend growth, dividend focus, option
               income (covered calls, premium income), buffer / defined outcome, yield 8%+, pays monthly or weekly
               (distributions in the last year), preferred stock
  Alternatives commodities, precious metals, crypto, volatility, managed futures, hedge strategies (long/short,
               market neutral, merger arbitrage, multistrategy, macro), currency, private markets
  Bonds        Treasuries, T-bills / cash, high yield, municipal, inflation-protected, corporate, emerging markets,
               mortgage-backed, loans / CLOs, target maturity, long-term
  Region       US, international, emerging markets, global, and single countries
  Size, style  large / mid / small cap, growth / value (Morningstar's category, as Yahoo reports it)
  Sector       the category's sector (technology, health care, financials, real estate, energy …)
  Factor, theme equal weight, momentum, quality, low volatility, ESG; AI, semiconductors, clean energy, cybersecurity …
  Structure    ETN, a trust holding the asset, fund of funds, currency-hedged, allocation, target date
"""
import re

GROUPS = ['Management', 'Leverage', 'Income', 'Alternatives', 'Bonds', 'Region', 'Size and style', 'Sector', 'Factor and theme', 'Structure']

TAGS = {
    'passive': ('Passive (index)', 'Management'), 'active': ('Active', 'Management'),
    'lev': ('Leveraged', 'Leverage'), 'inv': ('Inverse', 'Leverage'), 'single': ('Single stock', 'Leverage'),
    'div-high': ('High dividend', 'Income'), 'div-growth': ('Dividend growth', 'Income'), 'div': ('Dividend focus', 'Income'),
    'opt-income': ('Option income', 'Income'), 'buffer': ('Buffer / defined outcome', 'Income'), 'yield8': ('Yield 8%+', 'Income'),
    'pay-monthly': ('Pays monthly', 'Income'), 'pay-weekly': ('Pays weekly', 'Income'), 'preferred': ('Preferred stock', 'Income'),
    'alt': ('Alternative', 'Alternatives'), 'alt-commodity': ('Commodities', 'Alternatives'), 'alt-metals': ('Precious metals', 'Alternatives'),
    'alt-crypto': ('Crypto', 'Alternatives'), 'alt-vol': ('Volatility', 'Alternatives'), 'alt-trend': ('Managed futures', 'Alternatives'),
    'alt-hedge': ('Hedge strategy', 'Alternatives'), 'alt-currency': ('Currency', 'Alternatives'), 'alt-private': ('Private markets', 'Alternatives'),
    'bond-treasury': ('Treasuries', 'Bonds'), 'bond-cash': ('T-bills / cash', 'Bonds'), 'bond-hy': ('High-yield bonds', 'Bonds'),
    'bond-muni': ('Municipal bonds', 'Bonds'), 'bond-tips': ('Inflation-protected', 'Bonds'), 'bond-corp': ('Corporate bonds', 'Bonds'),
    'bond-em': ('Emerging-market bonds', 'Bonds'), 'bond-mbs': ('Mortgage-backed / securitized', 'Bonds'), 'bond-loans': ('Loans / CLOs', 'Bonds'),
    'bond-target': ('Target maturity', 'Bonds'), 'bond-long': ('Long-term bonds', 'Bonds'), 'bond-conv': ('Convertibles', 'Bonds'),
    'us': ('US', 'Region'), 'intl': ('International (developed)', 'Region'), 'em': ('Emerging markets', 'Region'), 'global': ('Global', 'Region'),
    'large': ('Large cap', 'Size and style'), 'mid': ('Mid cap', 'Size and style'), 'small': ('Small cap', 'Size and style'),
    'growth': ('Growth', 'Size and style'), 'value': ('Value', 'Size and style'),
    'f-equal': ('Equal weight', 'Factor and theme'), 'f-momentum': ('Momentum', 'Factor and theme'), 'f-quality': ('Quality', 'Factor and theme'),
    'f-lowvol': ('Low volatility', 'Factor and theme'), 'esg': ('ESG / sustainable', 'Factor and theme'),
    'etn': ('ETN (a bank\'s note)', 'Structure'), 'trust': ('Trust holding the asset', 'Structure'), 'fof': ('Fund of funds', 'Structure'),
    'hedged': ('Currency-hedged', 'Structure'), 'alloc': ('Allocation (stocks and bonds)', 'Structure'), 'target-date': ('Target date', 'Structure'),
}
SECTORS = {'Technology': 'Technology', 'Health': 'Health care', 'Financial': 'Financials', 'Real Estate': 'Real estate', 'Global Real Estate': 'Real estate',
           'Equity Energy': 'Energy', 'Natural Resources': 'Natural resources', 'Communications': 'Communication', 'Consumer Cyclical': 'Consumer discretionary',
           'Consumer Defensive': 'Consumer staples', 'Industrials': 'Industrials', 'Utilities': 'Utilities', 'Equity Precious Metals': 'Gold and silver miners',
           'Infrastructure': 'Infrastructure', 'Energy Limited Partnership': 'MLPs (pipelines)', 'Equity Digital Assets': 'Crypto stocks'}
for _s in set(SECTORS.values()):
    TAGS['sec-' + _s.lower().replace(' ', '-')] = (_s, 'Sector')
THEMES = [('th-ai', 'AI', r'artificial intelligence|\bAI\b|generative'), ('th-semis', 'Semiconductors', r'semiconductor|\bchips?\b'),
          ('th-clean', 'Clean energy', r'clean energy|solar|\bwind\b|renewable|hydrogen|clean tech'), ('th-cyber', 'Cybersecurity', r'cyber ?security|\bcyber\b'),
          ('th-robotics', 'Robotics and automation', r'robotic|automation'), ('th-space', 'Space', r'\bspace\b'), ('th-defense', 'Defense', r'\bdefen[cs]e\b'),
          ('th-nuclear', 'Uranium and nuclear', r'uranium|nuclear'), ('th-biotech', 'Biotech and genomics', r'biotech|genomic|biopharma'),
          ('th-cloud', 'Cloud and software', r'\bcloud\b|software|\bsaas\b'), ('th-fintech', 'Fintech', r'fintech|digital payments?|blockchain'),
          ('th-quantum', 'Quantum computing', r'quantum'), ('th-cannabis', 'Cannabis', r'cannabis|marijuana'), ('th-china-tech', 'China internet', r'china internet|kweb|china technology')]
for _id, _l, _ in THEMES:
    TAGS[_id] = (_l, 'Factor and theme')
ISO = {'China': 'CN', 'Japan': 'JP', 'India': 'IN', 'Korea': 'KR', 'Taiwan': 'TW', 'Brazil': 'BR', 'Mexico': 'MX', 'Canada': 'CA', 'United Kingdom': 'GB',
       'Germany': 'DE', 'France': 'FR', 'Italy': 'IT', 'Spain': 'ES', 'Switzerland': 'CH', 'Netherlands': 'NL', 'Sweden': 'SE', 'Australia': 'AU',
       'Hong Kong': 'HK', 'Singapore': 'SG', 'Indonesia': 'ID', 'Vietnam': 'VN', 'Thailand': 'TH', 'Malaysia': 'MY', 'Philippines': 'PH',
       'Saudi Arabia': 'SA', 'Israel': 'IL', 'South Africa': 'ZA', 'Turkey': 'TR', 'Poland': 'PL', 'Chile': 'CL', 'Argentina': 'AR', 'Peru': 'PE',
       'Colombia': 'CO', 'Greece': 'GR', 'Ireland': 'IE'}
EM_ISO = {'CN', 'KY', 'TW', 'KR', 'IN', 'BR', 'MX', 'ZA', 'SA', 'ID', 'TH', 'MY', 'PH', 'TR', 'PL', 'CL', 'PE', 'CO', 'GR', 'QA', 'AE', 'KW', 'EG', 'HU',
          'CZ', 'AR', 'VN', 'PK', 'NG', 'KE', 'RU'}
DOMICILE = {'IE', 'BM', 'CW', 'JE', 'GG', 'VG', 'PA', 'LR', 'MH', 'LU', 'XX', ''}    # where companies are incorporated, not where they are


def region_of(countries):
    """N-PORT's country weights {ISO: share} → (region, single country or None); (None, None) when too little is known.
    Cayman (KY) counts with China; tax domiciles (Ireland, Bermuda, Curaçao …) are left out of the shares."""
    if not countries:
        return None, None
    c, dom = {}, 0.0
    for k, v in countries.items():
        if v and v > 0 and k not in DOMICILE:
            k = 'CN' if k == 'KY' else k
            c[k] = c.get(k, 0) + v
        elif v and v > 0:
            dom += v
    den = sum(c.values())
    if len(countries) >= 15:                        # the fifteen largest only: the rest is spread over other countries
        den = max(den, 1.0 - dom)
    if den < 0.3:
        return None, None
    us, em = (c.get('US', 0) + c.get('PR', 0)) / den, sum(v for k, v in c.items() if k in EM_ISO) / den
    reg = 'us' if us >= 0.85 else ('em' if em >= 0.6 else 'intl') if us <= 0.15 else 'global'
    top = max(((k, v / den) for k, v in c.items() if k not in ('US', 'PR')), key=lambda x: x[1], default=(None, 0))
    name = next((n for n, iso in ISO.items() if iso == top[0]), None) if top[1] >= 0.75 else None
    return reg, name


COUNTRIES = ['China', 'Japan', 'India', 'Korea', 'Taiwan', 'Brazil', 'Mexico', 'Canada', 'United Kingdom', 'Germany', 'France', 'Italy', 'Spain',
             'Switzerland', 'Netherlands', 'Sweden', 'Australia', 'Hong Kong', 'Singapore', 'Indonesia', 'Vietnam', 'Thailand', 'Malaysia',
             'Philippines', 'Saudi Arabia', 'Israel', 'South Africa', 'Turkey', 'Poland', 'Chile', 'Argentina', 'Peru', 'Colombia', 'Greece', 'Ireland']
for _c in COUNTRIES:
    TAGS['cty-' + _c.lower().replace(' ', '-')] = (_c, 'Region')

WORDNUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}
NOT_LEVERAGE = re.compile(r'short[- ]?(?:term|duration|maturity|dated)|ultra[- ]short(?! (?:qqq|s&p|dow|russell|midcap|smallcap|bitcoin|ether|vix|gold|silver|oil|crude|natural|yen|euro|real|20|7|financ|semic|basic|consumer|health|industr|utilit|technology|oil))|'
                          r'ultrashort (?:bond|income|duration|muni|government|treasury|term)|short (?:treasury|government|corporate|municipal|muni|income|bond|high yield|tips|maturity)|'
                          r'long[/ -]+short|short[- ]interest|ultra buffer|ultra option income|ultra short option|short option income|enhanced short|short-only|leveraged loans?', re.I)
SHORT_WORDS = re.compile(r'\b(?:short|bear|inverse)\b', re.I)
# known exchange-traded products without a prospectus objective on file (1933-Act VIX futures funds)
KNOWN = {'SVXY': -0.5, 'UVXY': 1.5, 'UVIX': 2.0, 'SVIX': -1.0, 'VIXY': 1.0, 'VIXM': 1.0, 'VXX': 1.0, 'VXZ': 1.0}


def _signed(v, text):
    return -abs(v) if re.search(r'inverse|opposite|[-−]\s*\d', text, re.I) else v


def from_text(t):
    """A prospectus objective or strategy → (multiple, upper of a range or None) or (None, None). Only text about a daily
    (weekly, monthly) multiple or a notional exposure counts."""
    t = ' '.join(str(t or '').split())
    if not t or not re.search(r'daily|weekly|calendar week|monthly|notional exposure|times|\d\s*x\)', t, re.I):
        return None, None
    m = re.search(r'between (\d{3})% and (\d{3})% (?:of (?:its|the fund.s) net assets )?(?:notional )?exposure|(\d{3})% and (\d{3})% notional exposure', t, re.I)
    if m:
        lo, hi = [int(x) for x in m.groups() if x][:2]
        return round(hi / 100, 2), round(lo / 100, 2)
    m = re.search(r'\(\s*([-−]?\s*\d(?:\.\d+)?)\s*[x×]\s*\)', t, re.I)            # "(3x)", "(-3x)", "(-1x)"
    if m:
        v = float(m.group(1).replace('−', '-').replace(' ', ''))
        before = t[max(0, m.start() - 80):m.start()]
        return (v if v < 0 else _signed(v, before)), None
    m = re.search(r'\b(\d(?:\.\d+)?|one|two|three|four|five)(\s+and\s+one[- ]half)?\s+times\s*(\(\s*\d{2,3}%\s*\))?\s*(the inverse|the opposite)?', t, re.I)
    if m and re.search(r'daily|week|month|performance|return|percentage change', t[m.end():m.end() + 120], re.I):
        g = m.group(1).lower()
        v = float(WORDNUM.get(g, g)) + (0.5 if m.group(2) else 0)
        return (-v if m.group(4) else _signed(v, t[max(0, m.start() - 40):m.start()])), None
    m = re.search(r'([-−])?\b([1-5]\d{2})%\s+(?:of\s+)?(?:the\s+)?(?:inverse\s+)?(?:of\s+)?(?:the\s+)?(?:daily|calendar|weekly|monthly)', t, re.I)
    if m:
        v = int(m.group(2)) / 100
        return (-v if m.group(1) or 'inverse' in m.group(0).lower() else v), None
    if re.search(r'(?:correspond to|seeks?) (?:daily investment results[^.]{0,60})?the inverse \(?-?1x?\)? of the daily|the inverse of the daily', t, re.I):
        return -1.0, None
    return None, None


def from_name(name):
    """The multiple the name states: "Bull 3X", "-3X Inverse", "UltraPro Short", "2x Long NVDA", "Bear 1X"."""
    n = NOT_LEVERAGE.sub(' ', name or '')
    m = re.search(r'(?<![\w.%])([-−+]?\d(?:\.\d+)?)\s*[xX×](?![A-Za-z])', n) or re.search(r'(?<![\w.%])([-−+]?\d(?:\.\d+)?)\s*(?:[xX×]\s*)?(?=leveraged\b)', n, re.I)
    if m:
        v = float(m.group(1).replace('−', '-'))
        return -abs(v) if v < 0 or SHORT_WORDS.search(n) else v
    if re.search(r'\bultrapro short\b', n, re.I):
        return -3.0
    if re.search(r'\bultrashort\b', n, re.I):
        return -2.0
    if re.search(r'\bultrapro\b', n, re.I):
        return 3.0
    if re.search(r'^proshares ultra\b', n, re.I):
        return 2.0
    return None


def leverage(name, objective=None, strategy=None, category=None, multi_inverse=None, sym=None):
    """{'x': signed multiple or None when not stated, 'dir': 1 leveraged, −1 inverse, 0 neither, 'lo': a range's lower end}."""
    if sym in KNOWN:
        x = KNOWN[sym]
        return {'x': x, 'dir': 0 if x == 1 else (1 if x > 0 else -1), 'lo': None}
    cat = category or ''
    x, lo = from_text(objective)
    if x is None:
        x, lo = from_text((strategy or '')[:1500])
    if x is None:
        x = from_name(name)
    stripped = NOT_LEVERAGE.sub(' ', name or '')
    trading = cat.startswith('Trading--')
    # N-CEN's "leveraged / inverse index fund" answer is sometimes the trust's, not the fund's: it counts with a second sign
    multi_inverse = bool(multi_inverse) and (trading or bool(re.search(r'\bdaily\b|\bleveraged\b|inverse|\bbull\b|\bbear\b|ultra', stripped + ' ' + str(objective or ''), re.I)))
    if x is None and (trading or multi_inverse) and re.search(r'inverse|bear|\bshort\b', stripped + ' ' + cat, re.I) and 'Leveraged' not in cat:
        x = -1.0                                         # an inverse fund that names no multiple: −1×
    if x is None:
        lev = bool(multi_inverse) or (trading and ('Leveraged' in cat or 'Inverse' in cat))
        if not lev and re.search(r'\bleveraged\b|\bdaily (?:bull|bear)\b', stripped, re.I):
            lev = True
        return {'x': None, 'dir': (-1 if 'Inverse' in cat else 1) if lev else 0, 'lo': None}
    if x == 1:
        return {'x': 1.0, 'dir': 0, 'lo': None}
    return {'x': x, 'dir': 1 if x > 0 else -1, 'lo': lo}


def lev_label(L):
    if not L or not L['dir']:
        return None
    x = L['x']
    if x is None:
        return 'Inverse' if L['dir'] < 0 else 'Leveraged'
    f = lambda v: ('%g' % abs(v))
    if L.get('lo'):
        return f'{f(L["lo"])}–{f(x)}× exposure'
    return f'{"−" if x < 0 else ""}{f(x)}× {"inverse" if x < 0 else "leveraged"}'


ALIASES = {'tesla': 'TSLA', 'nvidia': 'NVDA', 'apple': 'AAPL', 'microsoft': 'MSFT', 'amazon': 'AMZN', 'alphabet': 'GOOGL', 'google': 'GOOGL',
           'netflix': 'NFLX', 'microstrategy': 'MSTR', 'coinbase': 'COIN', 'palantir': 'PLTR', 'broadcom': 'AVGO', 'robinhood': 'HOOD',
           'intel': 'INTC', 'oracle': 'ORCL', 'salesforce': 'CRM', 'boeing': 'BA', 'eli lilly': 'LLY', 'super micro': 'SMCI', 'micron': 'MU',
           'gamestop': 'GME', 'advanced micro': 'AMD', 'taiwan semiconductor': 'TSM', 'berkshire': 'BRK-B', 'meta platforms': 'META', 'uber': 'UBER',
           'shopify': 'SHOP', 'snowflake': 'SNOW', 'rivian': 'RIVN', 'lucid': 'LCID', 'nio': 'NIO', 'alibaba': 'BABA', 'pdd': 'PDD', 'arm holdings': 'ARM'}
STOP = {'ETF', 'ETFS', 'ETN', 'ETNS', 'USD', 'US', 'USA', 'ESG', 'AI', 'MSCI', 'S', 'P', 'DJ', 'II', 'III', 'IV', 'REIT', 'REITS', 'BDC', 'MLP', 'FANG',
        'NYSE', 'NASDAQ', 'CBOE', 'VIX', 'ICE', 'NYLI', 'NYLIM', 'SPDR', 'DB', 'UBS', 'JPM', 'MAX', 'TR', 'T', 'X', 'REX', 'FT', 'TCW', 'PGIM',
        'ARK', 'BNY', 'ALPS', 'NEOS', 'AB', 'KFA', 'CSI', 'FTSE', 'CRSP', 'EUR', 'GBP', 'JPY', 'CNY', 'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'A', 'I',
        'UK', 'EM', 'EAFE', 'ACWI', 'IPO', 'SPAC', 'ADR', 'LONG', 'SHORT', 'BULL', 'BEAR', 'DAILY', 'TARGET', 'INCOME', 'OPTION', 'WEEKLYPAY', 'CORGI'}


def underlying(name, objective=None, strategy=None, stocks=None, etf_syms=None):
    """The one stock a single-stock fund follows: the objective's "(NASDAQ: NVDA)" / "common shares of PLTR", a ticker in
    the name that is a listed company (not an ETF), or a company name ("Tesla"). None for an index or a basket."""
    stocks, etf_syms = stocks or set(), etf_syms or set()
    txt = ' '.join(str((objective or '') + ' ' + (strategy or '')[:1500]).split())
    m = re.search(r'\((?:NASDAQ|Nasdaq|NYSE|NYSE American|NYSE Arca|Cboe BZX)\s*:\s*([A-Z][A-Z.\-]{0,6})\)', txt)
    if m:
        return m.group(1).replace('.', '-')
    m = re.search(r'common (?:stock|shares) of ([A-Z][A-Z.\-]{0,5})\b', txt)
    if m and m.group(1) not in STOP:
        return m.group(1).replace('.', '-')
    if re.search(r'\b(?:index|basket|top \d+|magnificent|innovation|sector|industry|all world)\b', name or '', re.I):
        return None
    for tok in re.findall(r'\b[A-Z][A-Z.\-]{0,5}\b', name or ''):
        t = tok.replace('.', '-')
        if t not in STOP and t in stocks and t not in etf_syms:
            return t
    low = (name or '').lower()
    for k, t in ALIASES.items():
        if re.search(r'\b' + re.escape(k) + r'\b', low):
            return t
    return None


BOND_CATS = re.compile(r'bond|^muni|government|bank loan|ultrashort|money market|target maturity|inflation-protected|convertibles|fixed income', re.I)
ALT_HEDGE_CATS = {'Long-Short Equity', 'Equity Market Neutral', 'Event Driven', 'Multistrategy', 'Macro Trading', 'Relative Value Arbitrage', 'Equity Hedged'}
OPTIONS = re.compile(r'premium income|covered call|option income|buy-?write|enhanced income|put ?write|yieldmax|option strategy|weeklypay|growth & income|option overlay|high income', re.I)
BUFFER = re.compile(r'buffer|defined (?:outcome|protection)|floor\b|structured outcome|accelerat|max(?:imum)? ?(?:buffer|cap)|barrier|autocallable', re.I)


def fix_class(ac, category, name, leveraged):
    """The asset class from the holdings, set right by the category where the holdings mislead (a T-bill fund read as
    "multi-asset", an option-income fund holding T-bills read as fixed income, a merger-arbitrage fund read as equity)."""
    cat, n = category or '', name or ''
    if leveraged:
        return ac
    if cat == 'Derivative Income' and ac == 'Fixed income':
        return 'Crypto' if re.search(r'bitcoin|ether|crypto|solana|xrp', n, re.I) else 'Equity'
    if cat == 'Single Currency' or (re.search(r'\bUSD Index\b|U\.S\. Dollar|\bdollar\b', n) and cat.startswith('Trading')):
        return 'Currency'
    if BOND_CATS.search(cat) and ac in ('Multi-asset / alternatives', 'Other', 'Equity') and cat != 'Preferred Stock' and not (ac == 'Equity' and 'Convertible' not in cat and not re.search(r'bond|treasury|income|muni|credit|loan|t-bill', n, re.I)):
        return 'Fixed income'
    if (cat in ALT_HEDGE_CATS or cat == 'Systematic Trend') and ac == 'Equity':
        return 'Multi-asset / alternatives'
    if ac == 'Other':
        if cat == 'Digital Assets':
            return 'Crypto'
        if cat.startswith('Commodities'):
            return 'Commodity'
        if re.search(r'allocation|target-date', cat, re.I):
            return 'Multi-asset / alternatives'
        if cat and not cat.startswith('Trading'):
            return 'Equity'
    return ac


def pays(divs, today):
    """'weekly' / 'monthly' / None from the distributions of the last year ([[date, amount] …])."""
    import datetime as dt
    d0 = (today - dt.timedelta(days=365)).isoformat()
    n = sum(1 for d, v in divs or [] if d >= d0 and v and v > 0)
    return 'weekly' if n >= 40 else 'monthly' if n >= 10 else None


PASSIVE_TXT = re.compile(r'(?:track|replicate|correspond(?: generally)? to|seeks? (?:daily )?investment results[^.]{0,80}?(?:correspond|of))[^.]{0,120}?\b(?:index|benchmark)\b|index fund|passively managed|not actively managed', re.I)
ACTIVE_TXT = re.compile(r'\bactively[- ]managed\b|does not (?:seek to )?track (?:an|any) index|not an index fund', re.I)


def tags_of(r, L, under, pay=None, fof=False, trust_act=None, text=None, countries=None):
    """r: the screener row (name, asset_class, strategy, category, yield, act, index_fund); L: leverage(); under: the
    single stock or None. → [tag ids], in the order of GROUPS."""
    name, ac, cat = r.get('name') or '', r.get('asset_class') or '', r.get('category') or ''
    strat, yld, act = r.get('strategy') or '', r.get('yield'), r.get('act')
    n = name
    out = []
    add = out.append
    # management
    if r.get('index_fund') or strat.startswith('Index') or act in ('33', 'uit', 'etn') and not strat.startswith('Active'):
        add('passive')
    elif strat.startswith('Active') or re.search(r'\bactive\b', n, re.I):
        add('active')
    elif text and ACTIVE_TXT.search(text):
        add('active')
    elif text and PASSIVE_TXT.search(text) or re.search(r'\bindex\b', n, re.I):
        add('passive')
    # leverage
    if L and L['dir']:
        x = L['x']
        if x is None:
            add('inv' if L['dir'] < 0 else 'lev')
        else:
            tid = 'lev:%g' % x
            TAGS.setdefault(tid, (lev_label(L), 'Leverage'))
            add(tid)
            add('inv' if x < 0 else 'lev')
    if under:
        add('single')
    # income
    opt = cat == 'Derivative Income' or bool(OPTIONS.search(n))
    buf = cat == 'Defined Outcome' or bool(BUFFER.search(n))
    lev = bool(L and L['dir'])
    if ac == 'Equity' and not opt and not buf and not lev and cat != 'Preferred Stock':
        if re.search(r'\bdiv(?:idend)?s?\.?\s+(?:growth|appreciation|grower|increas)|aristocrat|achiever|rising dividend', n, re.I):
            add('div-growth')
        named = re.search(r'high dividend|dividend yield|high[- ]yield (?:equity|dividend|stock)|dividend income|equity income|\bhigh div\b', n, re.I)
        if yld is not None and yld >= 0.03 or named and (yld is None or yld >= 0.02):
            add('div-high')
        elif 'div-growth' not in out and re.search(r'\bdiv(?:idend)?s?\b', n, re.I):
            add('div')
    if opt and not buf:
        add('opt-income')
    if buf:
        add('buffer')
    if yld is not None and yld >= 0.08 and act != 'etn' and (not lev or opt or re.search(r'weekly|income|pay', n, re.I)):
        add('yield8')
    if pay == 'weekly':
        add('pay-weekly')
    elif pay == 'monthly':
        add('pay-monthly')
    if cat == 'Preferred Stock' or re.search(r'\bpreferred\b', n, re.I):
        add('preferred')
    # alternatives
    alt = []
    if ac == 'Crypto' or cat == 'Digital Assets':
        alt.append('alt-crypto')
    elif ac == 'Commodity: precious metals':
        alt.append('alt-metals')
    elif ac == 'Volatility' or (re.search(r'\bvix\b', n, re.I) and cat.startswith('Trading')):
        alt.append('alt-vol')
    elif ac == 'Commodity' or cat.startswith('Commodities') or cat in ('Trading--Leveraged Commodities', 'Trading--Inverse Commodities'):
        alt.append('alt-metals' if re.search(r'\bgold\b|silver|platinum|palladium', n, re.I) else 'alt-commodity')
    elif ac == 'Currency':
        alt.append('alt-currency')
    if cat == 'Systematic Trend' or re.search(r'managed futures|\btrend[- ]following\b', n, re.I):
        alt.append('alt-trend')
    if cat in ALT_HEDGE_CATS or re.search(r'long[/ -]+short|market neutral|merger arbitrage|\bhedge fund|hedge multi|event[- ]driven|tail risk|global macro', n, re.I):
        alt.append('alt-hedge')
    if re.search(r'private equity|private credit|business development|\bBDC\b|listed private|venture capital|private markets', n, re.I):
        alt.append('alt-private')
    if alt:
        add('alt')
        out.extend(dict.fromkeys(alt))
    # bonds
    if ac == 'Fixed income' or BOND_CATS.search(cat):
        if re.search(r'Muni', cat) or re.search(r'municipal|\bmuni\b|tax[- ]free|tax[- ]exempt', n, re.I):
            add('bond-muni')
        if re.search(r'Money Market', cat) or re.search(r't-?bill|0-3 month|1-3 month|0-1 year|treasury bill|money market|cash management|floating rate treasury', n, re.I):
            add('bond-cash')
        elif re.search(r'Government', cat) and 'Mortgage' not in cat or re.search(r'treasury|treasuries|government bond', n, re.I):
            add('bond-treasury')
        if 'High Yield' in cat or re.search(r'high[- ]yield|junk|fallen angel', n, re.I):
            add('bond-hy')
        if 'Inflation-Protected' in cat or re.search(r'\btips\b|inflation[- ]protected|inflation[- ]linked', n, re.I):
            add('bond-tips')
        if cat == 'Corporate Bond' or re.search(r'corporate', n, re.I) and 'bond-hy' not in out:
            add('bond-corp')
        if 'Emerging' in cat or re.search(r'emerging market', n, re.I):
            add('bond-em')
        if 'Securitized' in cat or 'Mortgage' in cat or re.search(r'mortgage|\bmbs\b|securitized|asset-backed', n, re.I):
            add('bond-mbs')
        if cat == 'Bank Loan' or re.search(r'\bclo\b|senior loan|bank loan|leveraged loan', n, re.I):
            add('bond-loans')
        if 'Target Maturity' in cat or re.search(r'\bibonds\b|bulletshares|\b20[2-4]\d\b', n, re.I) and 'Target' in cat:
            add('bond-target')
        if cat in ('Long Government', 'Long-Term Bond', 'Muni National Long') or re.search(r'20\+ year|long[- ]term (?:treasury|bond|corporate)|long duration|extended duration', n, re.I):
            add('bond-long')
        if cat == 'Convertibles' or re.search(r'convertible', n, re.I):
            add('bond-conv')
    # region (the issuer "Global X" is not a region)
    n = re.sub(r'^\s*global x\b', '', name, flags=re.I)
    reg, geo_cty = region_of(countries)
    if reg:
        pass
    elif re.search(r'Emerging|India Equity|Latin America|China Region', cat) or re.search(r'emerging|frontier', n, re.I):
        reg = 'em'
    elif re.search(r'^Global|World', cat) or re.search(r'\bglobal\b|\bworld\b|all[- ]country|\bacwi\b', n, re.I):
        reg = 'global'
    elif re.search(r'^Foreign|Europe Stock|Japan Stock|Pacific|Diversified Pacific', cat) or re.search(r'international|\bintl\b|ex[- ]u\.?s\.?\b|developed markets|\beafe\b|europe', n, re.I):
        reg = 'intl'
    elif re.search(r'^(Large|Mid-Cap|Small) (Value|Blend|Growth)$', cat) or re.search(r'\bu\.?s\.?\b|america|s&p 500|nasdaq|russell|dow jones', n, re.I) and ac == 'Equity':
        reg = 'us'
    if reg:
        add(reg)
    cty = geo_cty
    if cty or reg and reg != 'em' and reg != 'intl':
        pass
    elif re.search(r'China Region', cat) or re.search(r'\bchina\b|chinese|\bcsi \d+', n, re.I):
        cty = 'China'
    else:
        for c in COUNTRIES:
            if re.search(r'\b' + re.escape(c) + r'\b', n, re.I) or (c == 'Japan' and cat == 'Japan Stock') or (c == 'India' and cat == 'India Equity') \
                    or (c == 'Korea' and re.search(r'south korea', n, re.I)) or (c == 'United Kingdom' and re.search(r'\bu\.?k\.?\b|britain|british', n)):
                cty = c
                break
    if cty and not under:
        if not reg:
            add('em' if cty in ('China', 'India', 'Brazil', 'Mexico', 'Indonesia', 'Vietnam', 'Thailand', 'Malaysia', 'Philippines', 'Saudi Arabia',
                                'South Africa', 'Turkey', 'Poland', 'Chile', 'Argentina', 'Peru', 'Colombia', 'Greece', 'Taiwan', 'Korea') else 'intl')
        add('cty-' + cty.lower().replace(' ', '-'))
    # size and style
    m = re.match(r'^(?:Foreign |Global )?(Large|Mid-Cap|Small|Small/Mid)(?:-Stock)? (Value|Blend|Growth)', cat)
    if m:
        add({'Large': 'large', 'Mid-Cap': 'mid', 'Small': 'small', 'Small/Mid': 'small'}[m.group(1)])
        if m.group(2) != 'Blend':
            add(m.group(2).lower())
    elif ac == 'Equity':
        if re.search(r'small[- ]?cap|russell 2000|s&p 600|small companies', n, re.I):
            add('small')
        elif re.search(r'mid[- ]?cap|s&p 400|midcap', n, re.I):
            add('mid')
        if re.search(r'\bgrowth\b', n, re.I) and 'div-growth' not in out:
            add('growth')
        elif re.search(r'\bvalue\b', n, re.I):
            add('value')
    # sector
    if cat in SECTORS:
        add('sec-' + SECTORS[cat].lower().replace(' ', '-'))
    # factor and theme
    for tid, pat in (('f-equal', r'equal[- ]weight'), ('f-momentum', r'momentum'), ('f-quality', r'\bquality\b'),
                     ('f-lowvol', r'min(?:imum)? vol|low vol(?:atility)?|managed volatility|low beta'),
                     ('esg', r'\besg\b|sustainab|\bsri\b|paris[- ]aligned|low carbon|fossil fuel|climate|social(?:ly)? responsible|impact')):
        if re.search(pat, n, re.I):
            add(tid)
    if not lev or under is None:
        for tid, _, pat in THEMES:
            if re.search(pat, n, re.I if tid != 'th-ai' else 0) and not (tid == 'th-ai' and re.search(r'\bAI\b', n) is None and not re.search(r'artificial intelligence|generative', n, re.I)):
                add(tid)
    # structure
    if act == 'etn':
        add('etn')
    elif act == '33' and trust_act:
        add('trust')
    if fof:
        add('fof')
    if re.search(r'currency[- ]hedged|\bhedged\b', n, re.I) and 'alt-hedge' not in out and reg in ('intl', 'em', 'global'):
        add('hedged')
    if re.search(r'Allocation', cat):
        add('alloc')
    if 'Target-Date' in cat or re.search(r'target date|target retirement', n, re.I):
        add('target-date')
    return list(dict.fromkeys(out))
