"""ETF research: every US-listed ETF, read from its own filings, the market and the rest of the Disclosure Hub.

  collect
    universe   Nasdaq Trader's symbol directory (the ETF flag, all exchanges) + the SEC's fund tickers (registrant,
               series, class), company tickers (commodity / crypto trusts and ETNs file 10-Ks) and the series-class
               list; N-CEN adds the tickers of funds too new for the SEC's ticker file.
    filings    SEC DERA data sets, newest first, each processed once and kept:
                 N-CEN (annual census; the last five quarters cover every fund): index or active, leveraged/inverse
                   index, tracking difference and tracking error, management fee and net expenses, securities lending
                   (agents, income, average on loan), creation unit, in-kind share, authorized participants with the
                   value each created and redeemed, adviser and sub-advisers, custodians, administrator, transfer
                   agent, pricing services, brokers and commissions, the trust's auditor, distributor, board and CCO.
                 N-PORT (monthly portfolio reports; the last four quarters): net assets, monthly sales, reinvestments
                   and redemptions (flows), monthly returns, and the latest full portfolio of every ETF.
                 Prospectus risk/return summaries (485BPOS XBRL, last five quarters): the fee table, turnover,
                   calendar-year returns, the benchmark index, the objective, the strategy and the principal risks.
    market     Yahoo Finance: ten years of weekly closes and volume, NAV, net assets, yield, category, family.
    uit        the few unit-investment-trust ETFs that file no N-PORT (SPY, DIA, MDY): the sponsor's daily holdings file.
  build      public/: index.json (the screener), e/<SYMBOL>.json (one ETF), by/<TICKER>.json (the ETFs that hold a
             company), parties.json (authorized participants, custodians, lending agents, advisers, auditors across
             all ETFs), status.json — joined with the Hub's 13F holders, officials' trades, short interest, N-PX filers,
             and the companies inside seen through the consensus, 13F flows, officials, insiders and debt data.

    python app/etf.py collect --root etf --minutes 30
    python app/etf.py build   --root etf --hub disclosures/docs/data --consensus cons/public --debt debt/public --site-index site/index.json
"""
import argparse
import csv
import datetime as dt
import gzip
import heapq
import html
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import read_json, write_json  # noqa: E402
from consensus import Http, yahoo_crumb  # noqa: E402
import etf_market as M  # noqa: E402

csv.field_size_limit(1 << 30)
SEC_UA = os.environ.get('SEC_USER_AGENT') or 'Filing Flows research filingflows@gmail.com'
PAGES = {'ncen': 'https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets',
         'nport': 'https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets',
         'rr': 'https://www.sec.gov/data-research/sec-markets-data/mutual-fund-prospectus-riskreturn-summary-data-sets'}
KEEP = {'ncen': 5, 'nport': 4, 'rr': 5}
SERIES_CLASS = 'https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class.csv'
UIT_FILES = {'SPY': 'https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx',
             'DIA': 'https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-dia.xlsx',
             'MDY': 'https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-mdy.xlsx'}
FEE_TAGS = {'ManagementFeesOverAssets': 'management', 'OtherExpensesOverAssets': 'other', 'AcquiredFundFeesAndExpensesOverAssets': 'acquired',
            'DistributionAndService12b1FeesOverAssets': 'b12', 'ExpensesOverAssets': 'gross', 'FeeWaiverOrReimbursementOverAssets': 'waiver',
            'NetExpensesOverAssets': 'net', 'PortfolioTurnoverRate': 'turnover', 'ExpenseExampleYear01': 'cost1', 'ExpenseExampleYear10': 'cost10',
            'BarChartHighestQuarterlyReturn': 'best_q', 'BarChartLowestQuarterlyReturn': 'worst_q'}
ASSET_CAT = {'EC': 'Common equity', 'EP': 'Preferred equity', 'DBT': 'Debt', 'ABS-MBS': 'Mortgage-backed', 'ABS-O': 'Other asset-backed',
             'ABS-CBDO': 'CDO / CLO', 'ABS-APCP': 'Asset-backed CP', 'STIV': 'Short-term vehicles', 'RA': 'Repurchase agreements', 'LON': 'Loans',
             'DCO': 'Commodity derivatives', 'DCR': 'Credit derivatives', 'DE': 'Equity derivatives', 'DFE': 'FX derivatives', 'DIR': 'Rate derivatives',
             'DO': 'Other derivatives', 'COMM': 'Commodities', 'RE': 'Real estate', 'SN': 'Structured notes', 'OTHER': 'Other'}
EQUITY = {'EC', 'EP'}
DEBT = {'DBT', 'ABS-MBS', 'ABS-O', 'ABS-CBDO', 'ABS-APCP', 'LON', 'RA', 'SN'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _d(s):
    """'31-MAY-2026' or '20260531' → '2026-05-31'."""
    s = (s or '').strip()
    for fmt in ('%d-%b-%Y', '%Y%m%d', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _txt(s, n):
    s = html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= n else s[:n].rsplit(' ', 1)[0] + ' …'


def sec_get(h, url):
    return h.get(url, headers={'User-Agent': SEC_UA})


def download(url, dest, ua=None):
    req = urllib.request.Request(url, headers={'User-Agent': ua or SEC_UA, 'Accept-Encoding': 'identity'})
    for k in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as r, open(dest, 'wb') as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            return dest
        except Exception as exc:
            print(f'  download {url}: {exc}', flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError(f'could not download {url}')


def tsv(z, name):
    """Rows of one table of a DERA zip as dicts (the member may sit in a folder)."""
    m = next((n for n in z.namelist() if n.split('/')[-1].upper() == name.upper()), None)
    if not m:
        return
    with z.open(m) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8', errors='replace', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE)


def wj(path, obj):
    """Compact JSON (the public files are many; indentation would double them)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def save_gz(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(obj, f, separators=(',', ':'))


def load_gz(path, default=None):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------ N-CEN
def process_ncen(zpath):
    """Every ETF in one quarterly N-CEN set → {series_id: record} (the fund, its ETF items and every related party)."""
    z = zipfile.ZipFile(zpath)
    sub = {r['ACCESSION_NUMBER']: {'filed': _d(r['FILING_DATE']), 'period': _d(r['REPORT_ENDING_PERIOD']), 'cik': int(r.get('CIK') or 0)} for r in tsv(z, 'SUBMISSION.tsv')}
    reg = {r['ACCESSION_NUMBER']: {'name': r.get('REGISTRANT_NAME'), 'file_num': r.get('FILE_NUM'), 'lei': r.get('LEI'), 'family': r.get('FAMILY_INVESTMENT_COMPANY_NAME'),
                                   'type': r.get('INVESTMENT_COMPANY_TYPE'), 'state': r.get('STATE'), 'material_weakness': r.get('IS_MATERIAL_WEAKNESS_NOTED') == 'Y',
                                   'accountant_changed': r.get('IS_PUB_ACCOUNTANT_CHANGED') == 'Y', 'legal_proceeding': r.get('HAS_LEGAL_PROCEEDING') == 'Y'}
           for r in tsv(z, 'REGISTRANT.tsv')}
    by_acc = defaultdict(lambda: defaultdict(list))
    for t, f in (('PUBLIC_ACCOUNTANT.tsv', lambda r: r['PUB_ACCOUNTANT_NAME']), ('PRINCIPAL_UNDERWRITER.tsv', lambda r: [r['UNDERWRITER_NAME'], r.get('IS_AFFILIATED') == 'Y']),
                 ('DIRECTOR.tsv', lambda r: [r['DIRECTOR_NAME'], r.get('IS_INTERESTED_PERSON') == 'Y']), ('CHIEF_COMPLIANCE_OFFICER.tsv', lambda r: r['CCO_NAME'])):
        for r in tsv(z, t):
            by_acc[r['ACCESSION_NUMBER']][t.split('.')[0].lower()].append(f(r))
    funds = {}
    for r in tsv(z, 'FUND_REPORTED_INFO.tsv'):
        if r.get('IS_ETF') != 'Y' and r.get('IS_ETMF') != 'Y':
            continue
        acc = r['ACCESSION_NUMBER']
        funds[r['FUND_ID']] = {
            'series': r['SERIES_ID'], 'name': r.get('FUND_NAME'), 'lei': r.get('LEI'), 'acc': acc, **sub.get(acc, {}),
            'index': r.get('IS_INDEX') == 'Y', 'index_affiliated': r.get('IS_INDEX_AFFILIATED') == 'Y', 'index_exclusive': r.get('IS_INDEX_EXCLUSIVE') == 'Y',
            'multi_inverse': r.get('IS_MULTI_INVERSE_INDEX') == 'Y', 'fund_of_funds': r.get('IS_FUND_OF_FUND') == 'Y', 'non_diversified': r.get('IS_NON_DIVERSIFIED') == 'Y',
            'track_diff_gross': _f(r.get('RETURN_B4_FEES_AND_EXPENSES')), 'track_diff': _f(r.get('RETURN_AFTR_FEES_AND_EXPENSES')),
            'track_err_gross': _f(r.get('STDV_B4_FEES_AND_EXPENSES')), 'track_err': _f(r.get('STDV_AFTR_FEES_AND_EXPENSES')),
            'lends': r.get('DID_LEND_SECURITIES') == 'Y', 'lending_ok': r.get('IS_SEC_LENDING_AUTHORIZED') == 'Y', 'avg_on_loan': _f(r.get('AVG_VALUE_SEC_LOAN')),
            'lending_income': _f(r.get('NET_INCOME_SEC_LENDING')), 'expense_cap': r.get('HAS_EXP_LIMIT') == 'Y', 'fees_waived': r.get('HAS_EXP_REDUCED_WAIVED') == 'Y',
            'commissions': _f(r.get('AGG_COMMISSION')), 'principal_trades': _f(r.get('AGG_PRINCIPAL')), 'avg_net_assets': _f(r.get('MONTHLY_AVG_NET_ASSETS')) or _f(r.get('DAILY_AVG_NET_ASSETS')),
            'mgmt_fee': _f(r.get('MANAGEMENT_FEE')), 'net_expenses': _f(r.get('NET_OPERATING_EXPENSES')), 'price': _f(r.get('MARKET_PRICE_PER_SHARE')),
            'nav': _f(r.get('NAV_PER_SHARE')), 'derivatives_rule': r.get('IS_RELYON_RULE_18F_4') == 'Y', 'line_of_credit': r.get('HAS_LINE_OF_CREDIT') == 'Y',
            'registrant': reg.get(acc), 'accountant': by_acc[acc]['public_accountant'], 'distributor': by_acc[acc]['principal_underwriter'],
            'board': by_acc[acc]['director'], 'cco': by_acc[acc]['chief_compliance_officer']}
    want = set(funds)
    for r in tsv(z, 'ETF.tsv'):
        if r['FUND_ID'] in want:
            funds[r['FUND_ID']]['etf'] = {'creation_unit': _f(r.get('NUM_SHARES_PER_CREATION_UNIT')), 'cash_in': _f(r.get('PURCHASED_AVG_PCT_CASH')),
                                          'cash_out': _f(r.get('REDEEMED_AVG_PCT_CASH')), 'fee_in': _f(r.get('PURCH_AVG_FEE_SAME_DAY')) or _f(r.get('PURCH_AVG_FEE_PER_UNIT')),
                                          'fee_out': _f(r.get('REDEEM_AVG_FEE_SAME_DAY')) or _f(r.get('REDEEM_AVG_FEE_PER_UNIT')), 'in_kind': r.get('IS_FUND_IN_KIND_ETF') == 'Y',
                                          'collateral': r.get('IS_COLLATERAL_REQUIRED') == 'Y', 'track_diff': _f(r.get('ANNUAL_DIFF_AFTER_FEE_EXPENSE')),
                                          'track_err': _f(r.get('ANNUAL_STDV_AFTER_FEE_EXPENSE'))}
    lists = {'ADVISER.tsv': ('advisers', lambda r: [r['ADVISER_NAME'], r['ADVISER_TYPE'], r.get('CRD_NUM'), r.get('IS_AFFILIATED') == 'Y', r.get('ADVISOR_START_DATE')]),
             'CUSTODIAN.tsv': ('custodians', lambda r: [r['CUSTODIAN_NAME'], r.get('IS_SUB_CUSTODIAN') == 'Y', r.get('IS_AFFILIATED') == 'Y', (r.get('CUSTODY_TYPE') or '')[:60], r.get('COUNTRY')]),
             'ADMIN.tsv': ('administrators', lambda r: [r['ADMIN_NAME'], r.get('IS_AFFILIATED') == 'Y']),
             'TRANSFER_AGENT.tsv': ('transfer_agents', lambda r: [r['TRANSFERAGENT_NAME'], r.get('IS_AFFILIATED') == 'Y']),
             'SECURITY_LENDING.tsv': ('lending_agents', lambda r: [r['SECURITIES_AGENT_NAME'], r.get('IS_AFFILIATED') == 'Y', r.get('SECURITY_AGENT_IDEMNITY') == 'Y']),
             'COLLATERAL_MANAGER.tsv': ('collateral_managers', lambda r: [r['COLLATERAL_MANAGER_NAME'], r.get('IS_AFFILIATED') == 'Y']),
             'PRICING_SERVICE.tsv': ('pricing', lambda r: [r['PRICING_SERVICE_NAME'], r.get('IS_AFFILIATED') == 'Y']),
             'BROKER.tsv': ('brokers', lambda r: [r['BROKER_NAME'], _f(r.get('GROSS_COMMISSION'))]),
             'PRINCIPAL_TRANSACTION.tsv': ('principals', lambda r: [r['PRINCIPAL_NAME'], _f(r.get('PRINCIPAL_TOTAL_PURCHASE_SALE'))]),
             'AUTHORIZED_PARTICIPANT.tsv': ('aps', lambda r: [r['PARTICIPANT_NAME'].rstrip('*').strip(), _f(r.get('PURCHASE_VALUE')), _f(r.get('REDEEM_VALUE')), r.get('CRD_NUM') or '']),
             'SHARES_OUTSTANDING.tsv': ('classes', lambda r: [r.get('CLASS_ID'), (r.get('TICKER') or '').strip().upper(), r.get('CLASS_NAME')]),
             'SECURITY_EXCHANGE.tsv': ('listings', lambda r: [r.get('FUND_EXCHANGE'), (r.get('FUND_TICKER_SYMBOL') or '').strip().upper()])}
    for t, (key, f) in lists.items():
        for r in tsv(z, t):
            if r['FUND_ID'] in want:
                funds[r['FUND_ID']].setdefault(key, []).append(f(r))
    out = {}
    for rec in funds.values():
        for k in ('brokers', 'principals'):
            if rec.get(k):
                rec[k] = sorted(rec[k], key=lambda x: -(x[1] or 0))[:12]
        if rec.get('pricing'):
            rec['pricing'] = rec['pricing'][:8]
        if rec.get('custodians'):
            rec['custodians'] = sorted(rec['custodians'], key=lambda x: x[1])[:12]
        s = rec['series']
        if s and (s not in out or (rec.get('filed') or '') > (out[s].get('filed') or '')):
            out[s] = rec
    return out


# ------------------------------------------------------------------ prospectus risk/return summaries
def process_rr(zpath, keep_series, class_series):
    """Fee table, turnover, calendar-year returns, benchmark, objective, strategy and principal risks of every ETF
    series (and its ETF share class) in one quarterly risk/return set → {series_id: record}."""
    z = zipfile.ZipFile(zpath)
    subs = {r['adsh']: {'form': r['form'], 'filed': _d(r['filed']), 'cik': int(r['cik'] or 0), 'name': r['name']} for r in tsv(z, 'sub.tsv')}
    recs = {}

    def rec_of(adsh, series, cls):
        s = series or class_series.get(cls)
        if not s or s not in keep_series:
            return None
        key = (s, adsh)
        if key not in recs:
            recs[key] = {'series': s, 'adsh': adsh, **subs.get(adsh, {}), 'fees': {}, 'class_fees': {}, 'annual': {}, 'index': {}, 'risks': []}
        return recs[key]

    cls_re = re.compile(r'Class=(C\d+)')
    measures, loose = set(), set()
    for r in tsv(z, 'num.tsv'):
        tag = r['tag']
        if tag not in FEE_TAGS and tag not in ('AnnlRtrPct', 'AvgAnnlRtrPct'):
            continue
        m = cls_re.search(r.get('otherdims') or '')
        cls = m.group(1) if m else None
        if tag == 'AvgAnnlRtrPct' and not r.get('series') and not cls and r.get('measure') and not re.search(r'Tax|Return(Before|After)', r['measure']):
            loose.add((r['adsh'], r['measure'])); measures.add((r['adsh'], r['measure']))
            continue
        rec = rec_of(r['adsh'], r.get('series'), cls)
        if not rec:
            continue
        v = _f(r['value'])
        if tag in FEE_TAGS:
            if cls:
                rec['class_fees'].setdefault(cls, {})[FEE_TAGS[tag]] = v
            else:
                rec['fees'][FEE_TAGS[tag]] = v
        elif tag == 'AnnlRtrPct' and r.get('ddate'):
            rec['annual'].setdefault(cls or '', {})[r['ddate'][:4]] = v
        elif tag == 'AvgAnnlRtrPct' and r.get('measure') and not re.search(r'Tax|Return(Before|After)', r['measure']) and not cls:
            rec['index'][r['measure']] = rec['index'].get(r['measure'], 0) + 1
            measures.add((r['adsh'], r['measure']))
    risk_re = re.compile(r'Risk=([A-Za-z0-9_]+)')
    for r in tsv(z, 'txt.tsv'):
        tag = r['tag']
        if tag not in ('ObjectivePrimaryTextBlock', 'StrategyNarrativeTextBlock', 'RiskTextBlock', 'RiskNarrativeTextBlock'):
            continue
        m = cls_re.search(r.get('otherdims') or '')
        rec = rec_of(r['adsh'], r.get('series'), m.group(1) if m else None)
        if not rec:
            continue
        if tag == 'ObjectivePrimaryTextBlock':
            rec['objective'] = _txt(r['value'], 700)
        elif tag == 'StrategyNarrativeTextBlock':
            rec['strategy'] = _txt(r['value'], 3000)
        elif tag == 'RiskNarrativeTextBlock' and not rec['risks']:
            rec['risk_narrative'] = _txt(r['value'], 2500)
        elif tag == 'RiskTextBlock' and len(rec['risks']) < 40:
            rm = risk_re.search(r.get('otherdims') or '')
            if rm:
                measures.add((r['adsh'], rm.group(1) + 'Member'))
                rec['risks'].append([rm.group(1), _txt(r['value'], 600)])
    labels = {}
    if measures:
        for r in tsv(z, 'lab.tsv'):
            k = (r['adsh'], r['tag'])
            if k in measures or (r['adsh'], r['tag'].removesuffix('Member')) in measures:
                labels[(r['adsh'], r['tag'].removesuffix('Member'))] = re.sub(r'\s*\[Member\]$', '', r.get('terse') or r.get('std') or r['tag'])
    per_adsh = defaultdict(set)
    for (s, adsh) in recs:
        per_adsh[adsh].add(s)
    for adsh, m in loose:                      # an index row without a series belongs to a one-series filing
        if len(per_adsh.get(adsh, ())) == 1:
            rec = recs[(next(iter(per_adsh[adsh])), adsh)]
            rec['index'][m] = rec['index'].get(m, 0) + 1
    out = {}
    for (s, adsh), rec in recs.items():
        idx = sorted(rec['index'].items(), key=lambda x: -x[1])
        rec['benchmarks'] = [labels.get((adsh, k), re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k)) for k, _ in idx][:3]
        if not rec['benchmarks'] and rec.get('strategy'):
            m = re.search(r'(?:track|replicate|correspond to|seeks investment results)[^.]{0,160}?\b(?:the\s+)?((?:[A-Z0-9][\w&®.\-/]*\s+){1,9}Index)\b', rec['strategy'])
            if m:
                rec['benchmarks'] = [m.group(1).strip()]
        rec['risks'] = [[labels.get((adsh, k), re.sub(r'Risk$', '', re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k)).strip()), t] for k, t in rec['risks']]
        del rec['index']
        if s not in out or (rec.get('filed') or '') > (out[s].get('filed') or ''):
            out[s] = rec
    return out


# ------------------------------------------------------------------ N-PORT
def process_nport(zpath, keep_series, holdings=True, top=150):
    """One quarterly N-PORT set → {'funds': {series: {reports: [...]}}, 'holdings': {series: portfolio of the latest report}}.
    Flows: sales, reinvestments and redemptions of each of the three months of every report."""
    z = zipfile.ZipFile(zpath)
    sub = {r['ACCESSION_NUMBER']: (_d(r['REPORT_DATE']), _d(r['FILING_DATE'])) for r in tsv(z, 'SUBMISSION.tsv')}
    regs = {r['ACCESSION_NUMBER']: (int(r['CIK'] or 0), r['REGISTRANT_NAME']) for r in tsv(z, 'REGISTRANT.tsv')}
    funds, acc_series = {}, {}
    for r in tsv(z, 'FUND_REPORTED_INFO.tsv'):
        s = r['SERIES_ID']
        if s not in keep_series:
            continue
        acc = r['ACCESSION_NUMBER']
        rd, fd = sub.get(acc, (None, None))
        if not rd:
            continue
        acc_series[acc] = s
        f = lambda k: _f(r.get(k)) or 0.0
        months = []
        y, m = int(rd[:4]), int(rd[5:7])
        for i in (3, 2, 1):
            mm = (y * 12 + m - 1) - (3 - i)
            months.append([f'{mm // 12}-{mm % 12 + 1:02d}', f(f'SALES_FLOW_MON{i}'), f(f'REINVESTMENT_FLOW_MON{i}'), f(f'REDEMPTION_FLOW_MON{i}')])
        funds.setdefault(s, {'name': r['SERIES_NAME'], 'reports': []})['reports'].append(
            {'acc': acc, 'date': rd, 'filed': fd, 'cik': regs.get(acc, (None,))[0], 'registrant': regs.get(acc, (None, None))[1], 'net_assets': _f(r.get('NET_ASSETS')),
             'total_assets': _f(r.get('TOTAL_ASSETS')), 'liabilities': _f(r.get('TOTAL_LIABILITIES')), 'flows': sorted(months)})
    rets = defaultdict(dict)
    for r in tsv(z, 'MONTHLY_TOTAL_RETURN.tsv'):
        if r['ACCESSION_NUMBER'] in acc_series:
            rets[r['ACCESSION_NUMBER']][r.get('CLASS_ID') or ''] = [_f(r.get(f'MONTHLY_TOTAL_RETURN{i}')) for i in (1, 2, 3)]
    for s, fd in funds.items():
        for rep in fd['reports']:
            rep['returns'] = rets.get(rep['acc'], {})
        fd['reports'].sort(key=lambda x: x['date'])
    out = {'funds': funds, 'holdings': {}}
    if not holdings:
        return out
    latest = {fd['reports'][-1]['acc']: s for s, fd in funds.items()}
    hold = defaultdict(list)
    hid = {}
    for r in tsv(z, 'FUND_REPORTED_HOLDING.tsv'):
        acc = r['ACCESSION_NUMBER']
        if acc not in latest:
            continue
        v, p = _f(r.get('CURRENCY_VALUE')), _f(r.get('PERCENTAGE'))
        row = [r.get('ISSUER_NAME') or '', r.get('ISSUER_TITLE') or '', (r.get('ISSUER_CUSIP') or '').upper(), None, None, v, p, r.get('ASSET_CAT') or '',
               r.get('ISSUER_TYPE') or '', r.get('INVESTMENT_COUNTRY') or '', r.get('PAYOFF_PROFILE') or '', r.get('DERIVATIVE_CAT') or '', 0.0]
        hid[r['HOLDING_ID']] = row
        hold[acc].append(row)
    for r in tsv(z, 'IDENTIFIERS.tsv'):
        row = hid.get(r['HOLDING_ID'])
        if row:
            if r.get('IDENTIFIER_ISIN') and not row[3]:
                row[3] = r['IDENTIFIER_ISIN'].upper()
            if r.get('IDENTIFIER_TICKER') and not row[4]:
                row[4] = r['IDENTIFIER_TICKER'].upper()
    for r in tsv(z, 'SECURITIES_LENDING.tsv'):
        row = hid.get(r['HOLDING_ID'])
        if row and r.get('LOAN_VALUE'):
            row[12] = _f(r['LOAN_VALUE']) or 0.0
    hid.clear()
    for acc, rows in hold.items():
        s = latest[acc]
        rep = funds[s]['reports'][-1]
        na = rep['net_assets'] or sum(abs(x[5] or 0) for x in rows) or 1
        mix, iss, ctry, deriv = defaultdict(float), defaultdict(float), defaultdict(float), 0.0
        for x in rows:
            w = (x[6] / 100) if x[6] is not None else ((x[5] or 0) / na)
            x[6] = w
            mix[x[7] or 'OTHER'] += w
            iss[x[8] or 'OTHER'] += w
            ctry[x[9] or '??'] += w
            if x[11] or (x[7] or '').startswith('D'):
                deriv += abs(w)
        rows.sort(key=lambda x: -abs(x[6] or 0))
        out['holdings'][s] = {'acc': acc, 'date': rep['date'], 'net_assets': rep['net_assets'], 'n': len(rows),
                              'top': [[x[0][:60], x[1][:60], x[2], x[3], x[4], round(x[5] or 0), round(x[6] or 0, 6), x[7], x[8], x[9], x[10]] for x in rows[:top]],
                              'weights': [[x[4] or x[2] or x[3], round(x[6], 7), round(x[5] or 0)] for x in rows if x[7] in EQUITY and (x[4] or x[2] or x[3]) and (x[10] or 'Long') == 'Long'],
                              'mix': {k: round(v, 5) for k, v in sorted(mix.items(), key=lambda x: -x[1])},
                              'issuers': {k: round(v, 5) for k, v in sorted(iss.items(), key=lambda x: -x[1])[:10]},
                              'countries': {k: round(v, 5) for k, v in sorted(ctry.items(), key=lambda x: -x[1])[:15]},
                              'derivatives': round(deriv, 5), 'on_loan': round(sum(x[12] for x in rows)), 'top10': round(sum(x[6] or 0 for x in rows[:10]), 5)}
    return out


# ------------------------------------------------------------------ UIT holdings (sponsor files)
def parse_xlsx_rows(data):
    """The first worksheet of an .xlsx as lists of cell strings (shared strings resolved). Standard library only."""
    import xml.etree.ElementTree as ET
    z = zipfile.ZipFile(io.BytesIO(data))
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(ns + 'si'):
            shared.append(''.join(t.text or '' for t in si.iter(ns + 't')))
    sheet = next(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))
    rows = []
    for row in ET.fromstring(z.read(sheet)).iter(ns + 'row'):
        cells = {}
        for c in row.iter(ns + 'c'):
            ref = re.match(r'([A-Z]+)', c.get('r', 'A')).group(1)
            col = 0
            for ch in ref:
                col = col * 26 + ord(ch) - 64
            v = c.find(ns + 'v')
            val = v.text if v is not None else ''.join(t.text or '' for t in c.iter(ns + 't'))
            if c.get('t') == 's' and val is not None and val.isdigit():
                val = shared[int(val)]
            cells[col - 1] = val
        if cells:
            rows.append([cells.get(i, '') for i in range(max(cells) + 1)])
    return rows


def parse_uit_holdings(data):
    rows = parse_xlsx_rows(data)
    head = next((i for i, r in enumerate(rows) if any(str(c).strip().lower() == 'ticker' for c in r) and any('weight' in str(c).lower() for c in r)), None)
    if head is None:
        return []
    H = [str(c).strip().lower() for c in rows[head]]
    ix = lambda name: next((i for i, h in enumerate(H) if h.startswith(name)), None)
    it, iw, iname, iid, isec = ix('ticker'), ix('weight'), ix('name'), ix('identifier'), ix('sector')
    out = []
    for r in rows[head + 1:]:
        if it is None or it >= len(r) or not str(r[it]).strip():
            continue
        w = _f(r[iw]) if iw is not None and iw < len(r) else None
        if w is None:
            continue
        out.append([str(r[iname]) if iname is not None and iname < len(r) else '', str(r[it]).strip().upper(), str(r[iid]).strip() if iid is not None and iid < len(r) else '',
                    w / 100, str(r[isec]) if isec is not None and isec < len(r) else ''])
    return out


# ------------------------------------------------------------------ collect
def dataset_links(h):
    out = {}
    for k, u in PAGES.items():
        try:
            page = sec_get(h, u).decode('utf-8', 'replace')
        except Exception as exc:
            print(f'::warning::{k} listing: {exc}', flush=True)
            continue
        ls = sorted(set(re.findall(r'href="([^"]+\.zip)"', page, re.I)))
        out[k] = sorted(urllib.parse.urljoin(u, l) for l in ls if re.search(r'(\d{4})q(\d)', l))
    return out


def qkey(url):
    m = re.search(r'(\d{4})q(\d)', url)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def collect_universe(h, root):
    """The ETF list with SEC identifiers (cached; refreshed every run, it is a few requests)."""
    root = Path(root)
    c = read_json(root / 'cache' / 'universe_src.json', {}) or {}
    try:
        c['nasdaq'] = M.parse_nasdaq_dir(h.get(M.NASDAQ_DIR).decode('utf-8', 'replace'))
        c['mf'] = json.loads(sec_get(h, 'https://www.sec.gov/files/company_tickers_mf.json'))
        c['cos'] = json.loads(sec_get(h, 'https://www.sec.gov/files/company_tickers_exchange.json'))
        c['at'] = now()
    except Exception as exc:
        print(f'::warning::universe sources: {exc}', flush=True)
    if not c.get('series_class') or (c.get('series_class_at') or '') < (dt.date.today() - dt.timedelta(days=7)).isoformat():
        try:
            txt = sec_get(h, SERIES_CLASS).decode('utf-8-sig', 'replace')
            sc = {}
            for r in csv.DictReader(io.StringIO(txt)):
                t = (r.get('Class Ticker') or '').strip().upper()
                if t and t != '[NULL]':
                    sc[t] = [int(r.get('CIK Number') or 0), r.get('Series ID'), r.get('Class ID'), r.get('Entity Name'), r.get('Series Name')]
            c['series_class'], c['series_class_at'] = sc, dt.date.today().isoformat()
        except Exception as exc:
            print(f'::warning::series-class list: {exc}', flush=True)
    write_json(root / 'cache' / 'universe_src.json', c)
    return c


def universe(root, src=None):
    root = Path(root)
    src = src or read_json(root / 'cache' / 'universe_src.json', {}) or {}
    etfs = M.build_universe(src.get('nasdaq') or [], src.get('mf') or {}, src.get('cos') or {})
    sc = src.get('series_class') or {}
    ncen_t = {}
    for p in sorted((root / 'cache' / 'ncen').glob('*.json.gz')):
        for s, rec in (load_gz(p, {}) or {}).items():
            for cid, t, _ in rec.get('classes') or []:
                if t:
                    ncen_t[t] = (s, cid, (rec.get('registrant') or {}).get('name'), rec.get('cik'))
            for _, t in rec.get('listings') or []:
                if t and t not in ncen_t:
                    ncen_t[t] = (s, None, (rec.get('registrant') or {}).get('name'), rec.get('cik'))
    for e in etfs:
        if e.get('series'):
            continue
        t = e['symbol']
        if t in sc and sc[t][1]:
            e.update(cik=sc[t][0] or e.get('cik'), series=sc[t][1], cls=sc[t][2], act='40')
        elif t in ncen_t:
            s, cid, _, cik = ncen_t[t]
            e.update(series=s, cls=cid or e.get('cls'), act='40', cik=e.get('cik') or cik)
    return etfs


def collect_datasets(h, root, tmp='/tmp/etf-dl', max_new=None):
    """Download and process the DERA sets not processed yet (newest first). N-PORT holdings for the newest set only."""
    root = Path(root)
    links = dataset_links(h)
    st = read_json(root / 'state.json', {}) or {}
    done = st.setdefault('datasets', {})
    Path(tmp).mkdir(parents=True, exist_ok=True)
    src = read_json(root / 'cache' / 'universe_src.json', {}) or {}
    mf = src.get('mf') or {}
    F = mf.get('fields') or ['cik', 'seriesId', 'classId', 'symbol']
    class_series = {}
    for r in mf.get('data') or []:
        d = dict(zip(F, r))
        if d.get('classId') and d.get('seriesId'):
            class_series[d['classId']] = d['seriesId']
    for t, v in (src.get('series_class') or {}).items():
        if v[2] and v[1]:
            class_series.setdefault(v[2], v[1])
    report = {}
    for kind in ('ncen', 'nport', 'rr'):
        urls = sorted(links.get(kind, []), key=qkey)[-KEEP[kind]:]
        if not urls:
            continue
        newest = urls[-1]
        for u in reversed(urls):
            name = Path(u).name
            out = root / 'cache' / kind / (name.replace('.zip', '') + '.json.gz')
            need_holdings = kind == 'nport' and u == newest
            if out.exists() and done.get(name) and (not need_holdings or done[name].get('holdings')):
                continue
            if max_new is not None and sum(1 for v in report.values() for _ in v) >= max_new:
                break
            ets = etf_series(root)
            t0 = time.time()
            zp = Path(tmp) / name
            try:
                download(u, zp)
                if kind == 'ncen':
                    data = process_ncen(zp)
                elif kind == 'rr':
                    data = process_rr(zp, ets, class_series)
                else:
                    data = process_nport(zp, ets, holdings=need_holdings)
                    if need_holdings:
                        save_gz(root / 'cache' / 'nport_holdings.json.gz', {'source': name, 'holdings': data.pop('holdings')})
                    else:
                        data.pop('holdings', None)
                    data = data['funds']
                save_gz(out, data)
                done[name] = {'at': now(), 'rows': len(data), 'holdings': need_holdings, 'seconds': round(time.time() - t0)}
                report.setdefault(kind, []).append([name, len(data), round(time.time() - t0)])
                print(f'{kind} {name}: {len(data)} funds in {time.time() - t0:.0f}s', flush=True)
            except Exception as exc:
                print(f'::warning::{kind} {name}: {exc}', flush=True)
                done[name] = {'at': now(), 'error': str(exc)[:200]}
            finally:
                zp.unlink(missing_ok=True)
            write_json(root / 'state.json', st)
        keep = {Path(u).name.replace('.zip', '') + '.json.gz' for u in urls}
        for p in (root / 'cache' / kind).glob('*.json.gz'):
            if p.name not in keep:
                p.unlink()
    return report


def etf_series(root):
    """Series ids of ETFs: the listed ETFs' SEC series plus every series N-CEN marks as an ETF."""
    s = {e['series'] for e in universe(root) if e.get('series')}
    for p in (Path(root) / 'cache' / 'ncen').glob('*.json.gz'):
        s |= set((load_gz(p, {}) or {}).keys())
    return s


def collect_uit(root):
    out = {}
    for t, u in UIT_FILES.items():
        try:
            req = urllib.request.Request(u, headers={'User-Agent': M.__dict__.get('BROWSER', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36')})
            with urllib.request.urlopen(req, timeout=60) as r:
                rows = parse_uit_holdings(r.read())
            if rows:
                out[t] = {'at': now(), 'rows': rows}
        except Exception as exc:
            print(f'  uit {t}: {exc}', flush=True)
    if out:
        old = read_json(Path(root) / 'cache' / 'uit.json', {}) or {}
        old.update(out)
        write_json(Path(root) / 'cache' / 'uit.json', old)
    return {k: len(v['rows']) for k, v in out.items()}


def collect(root, minutes=30.0, datasets=True):
    root = Path(root)
    t0 = time.time()
    h = Http({'www.sec.gov': 0.15, 'www.nasdaqtrader.com': 1, 'query2.finance.yahoo.com': 0.6, 'fc.yahoo.com': 0.5})
    src = collect_universe(h, root)
    rep = {'universe': len(universe(root, src))}
    if datasets:
        rep['datasets'] = collect_datasets(h, root)
    rep['uit'] = collect_uit(root)
    etfs = universe(root)
    caps = {}
    hd = load_gz(root / 'cache' / 'nport_holdings.json.gz', {}) or {}
    for s, x in (hd.get('holdings') or {}).items():
        caps[s] = x.get('net_assets') or 0
    for e in etfs:
        e['assets'] = caps.get(e.get('series'), 0)
    left = max(3.0, minutes - (time.time() - t0) / 60)
    rep['market'] = M.collect_market(h, root, etfs, yahoo_crumb, minutes=left)
    return rep


# ------------------------------------------------------------------ build
CRYPTO = re.compile(r'bitcoin|ether(eum)?\b|solana|\bxrp\b|crypto|litecoin|dogecoin|avalanche|cardano|polkadot|hyperliquid|digital asset|\bsui\b|chainlink|hedera', re.I)
METALS = re.compile(r'\bgold\b|silver|platinum|palladium|precious metal', re.I)
COMMOD = re.compile(r'\boil\b|crude|natural gas|commodit|agricultur|wheat|corn|soybean|copper|uranium|carbon|dry bulk|freight', re.I)
VOLA = re.compile(r'\bvix\b|volatility', re.I)
FX = re.compile(r'\bdollar\b|euro\b|\byen\b|currenc|franc\b|sterling|pound\b|yuan', re.I)
OPTIONS = re.compile(r'premium income|covered call|option income|buy-?write|buffer|defined (outcome|protection)|autocallable|enhanced income|income strategy|put ?write|target \d+|yieldmax|option strategy', re.I)


def classify(e, h, nc):
    """Asset class and strategy from what the filings show (holdings mix, N-CEN flags), the name only as a last resort."""
    name = e.get('name') or ''
    mix = (h or {}).get('mix') or {}
    eq = sum(v for k, v in mix.items() if k in EQUITY)
    debt = sum(v for k, v in mix.items() if k in DEBT)
    rf = (h or {}).get('issuers', {}).get('RF', 0)
    if e.get('act') == 'etn':
        ac = 'ETN'
    elif mix and e.get('act') in ('33', 'uit') and eq >= 0.6:
        ac = 'Equity'
    elif e.get('leveraged') or (nc or {}).get('multi_inverse'):
        ac = 'Leveraged / inverse'
    elif CRYPTO.search(name):
        ac = 'Crypto'
    elif e.get('act') == '33' and METALS.search(name) or (not mix and METALS.search(name)):
        ac = 'Commodity: precious metals'
    elif VOLA.search(name) and (e.get('act') == '33' or not eq):
        ac = 'Volatility'
    elif e.get('act') == '33' and FX.search(name):
        ac = 'Currency'
    elif e.get('act') == '33' or (COMMOD.search(name) and eq < 0.5):
        ac = 'Commodity'
    elif mix:
        ac = 'Equity' if eq >= 0.6 else 'Fixed income' if debt >= 0.6 else 'Multi-asset (fund of funds)' if rf >= 0.5 else 'Multi-asset / alternatives'
    else:
        ac = 'Fixed income' if re.search(r'bond|treasury|municipal|income|credit|clo\b|mortgage|floating|t-bill|duration|yield', name, re.I) and not re.search(r'equity|dividend', name, re.I) else 'Equity' if re.search(r'equity|stock|dividend|growth|value|cap\b|sector|index', name, re.I) else 'Other'
    if (nc or {}).get('index'):
        strat = 'Index'
    elif nc:
        strat = 'Active'
    else:
        strat = 'Index' if re.search(r'\bindex\b', name, re.I) else None
    if OPTIONS.search(name):
        strat = (strat + ' · ' if strat else '') + 'options / defined outcome'
    return ac, strat


GENERIC_BENCH = re.compile(r'^(the\s+)?(underlying|benchmark|target|reference|primary)?\s*(index|benchmark)$', re.I)


def benchmarks_of(pr):
    """The benchmark index names of a prospectus record; generic labels ("Underlying Index") replaced by the name the
    strategy text gives ("… the S&P 500 (the "Underlying Index")")."""
    b = [x for x in (pr or {}).get('benchmarks') or [] if x and not GENERIC_BENCH.match(x.strip())]
    if b:
        return b
    st = ((pr or {}).get('objective') or '') + ' ' + ((pr or {}).get('strategy') or '')
    for pat in (r'(?:track|replicate|correspond to)[^.]{0,120}?(?:results|performance) of (?:the\s+)?([A-Z0-9][^()“"]{2,90}?)\s*\((?:the\s+)?[“"]?(?:Underlying|Target|Benchmark) Index',
                r'(?:track|replicate|correspond to)[^.]{0,160}?\b(?:the\s+)?((?:[A-Z0-9][\w&®™℠.\-/]*\s+){1,9}Index)\b'):
        m = re.search(pat, st)
        if m:
            return [m.group(1).strip().rstrip(',')]
    return []


def norm_t(t):
    t = (t or '').upper().strip().replace('/', '.').replace(' ', '')
    return re.sub(r'\.?(US|UN|UW|UQ)$', '', t) if len(t) > 4 and re.search(r'\.?(US|UN|UW|UQ)$', t) else t


def merge_latest(kind, root):
    out = {}
    for p in sorted((Path(root) / 'cache' / kind).glob('*.json.gz')):
        for s, rec in (load_gz(p, {}) or {}).items():
            if s not in out or (rec.get('filed') or '') >= (out[s].get('filed') or ''):
                out[s] = rec
    return out


def implied_flows(lst, fl_of, n=12):
    """What ETF creations and redemptions passed through to one company, month by month (an estimate): each ETF's
    N-PORT sales (+ reinvestments) and redemptions × the company's weight in that ETF's latest portfolio, summed over the
    ETFs that hold it. Leveraged and inverse funds are left out (they get their exposure from swaps). cov: the share of the
    dollars ETFs hold in the company whose fund reported that month (the newest months fill in as N-PORT reports arrive).
    lst: [[symbol, weight, value held] …]; fl_of: symbol → (leveraged or inverse, {month: (in, out)})."""
    keep = [(sym, w, v) for sym, w, v in lst if w and not fl_of.get(sym, (True, {}))[0]]
    held = sum(v or 0 for _, _, v in keep)
    agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
    for sym, w, v in keep:
        for m, (i, o) in fl_of[sym][1].items():
            a = agg[m]
            a[0] += w * i; a[1] += w * o; a[2] += v or 0; a[3] += 1
    months = sorted(agg)[-n:]
    if len(months) < 3:
        return None
    return {'months': months, 'in': [round(agg[m][0]) for m in months], 'out': [round(agg[m][1]) for m in months],
            'cov': [round(agg[m][2] / held, 3) if held else None for m in months], 'etfs': [agg[m][3] for m in months]}


def nport_history(root):
    """Every report of every ETF series across the kept quarters → monthly flows (one row a month) and net assets."""
    out = {}
    for p in sorted((Path(root) / 'cache' / 'nport').glob('*.json.gz')):
        for s, fd in (load_gz(p, {}) or {}).items():
            o = out.setdefault(s, {'name': fd.get('name'), 'months': {}, 'assets': {}, 'returns': {}, 'reports': []})
            for rep in fd.get('reports') or []:
                o['assets'][rep['date']] = rep.get('net_assets')
                o['reports'].append({k: rep.get(k) for k in ('acc', 'date', 'filed', 'cik', 'registrant', 'net_assets')})
                for mth, sales, reinv, red in rep.get('flows') or []:
                    o['months'][mth] = [sales, reinv, red]
                for cls, rs in (rep.get('returns') or {}).items():
                    y, m = int(rep['date'][:4]), int(rep['date'][5:7])
                    for i, r in enumerate(rs):
                        mm = (y * 12 + m - 1) - (2 - i)
                        if r is not None:
                            o['returns'].setdefault(cls, {})[f'{mm // 12}-{mm % 12 + 1:02d}'] = r
    return out


def build(root, hub=None, cons=None, debt=None, verbose=True):
    root = Path(root); pub = root / 'public'
    for d in ('e', 'by'):
        (pub / d).mkdir(parents=True, exist_ok=True)
    etfs = universe(root)
    ncen = merge_latest('ncen', root)
    rr = merge_latest('rr', root)
    hist = nport_history(root)
    hd = load_gz(root / 'cache' / 'nport_holdings.json.gz', {}) or {}
    holds = hd.get('holdings') or {}
    uit = read_json(root / 'cache' / 'uit.json', {}) or {}
    hub = Path(hub) if hub else None
    cusip_t = read_json(hub / 'market' / 'cusip-tickers.json', {}) if hub else {}
    t_cusip = {}
    for c, t in cusip_t.items():
        t_cusip.setdefault(t, c)
    cons_rows = {}
    if cons and (Path(cons) / 'index.json').exists():
        ci = read_json(Path(cons) / 'index.json', {})
        for r in ci.get('rows') or []:
            d = dict(zip(ci['fields'], r))
            cons_rows[d['ticker']] = d
    debt_rows = {}
    if debt and (Path(debt) / 'index.json').exists():
        di = read_json(Path(debt) / 'index.json', {})
        for r in di.get('rows') or []:
            d = dict(zip(di['fields'], r))
            if d.get('ticker'):
                debt_rows[d['ticker']] = d
    flows13 = read_json(hub / 'market' / 'flows.json', {}) if hub else {}
    f_hist = flows13.get('history') or {}
    officials = M.officials_by_ticker(hub) if hub else {}
    shorts, short_date = M.shorts_by_ticker(hub) if hub else ({}, None)
    ins = {r['ticker']: r for r in (read_json(hub / 'market' / 'insiders.json', {}) or {}).get('summary') or [] if r.get('ticker')} if hub else {}
    npx = {int(r['cik']): r for r in (read_json(hub / 'catalogs' / 'npx.json', []) if hub else []) if str(r.get('cik', '')).isdigit()}
    etf_cusips = {t_cusip[e['symbol']]: e['symbol'] for e in etfs if e['symbol'] in t_cusip}
    h13, periods13 = M.holders_13f(hub, list(etf_cusips)) if hub else ({}, [])
    today = dt.date.today()
    d90 = (today - dt.timedelta(days=90)).isoformat()
    d365 = (today - dt.timedelta(days=365)).isoformat()

    def key_ticker(k):
        k = norm_t(k)
        if k in cons_rows or k in debt_rows:
            return k
        if k in cusip_t:
            return cusip_t[k]
        if len(k) == 12 and k[:2] == 'US' and k[2:11] in cusip_t:
            return cusip_t[k[2:11]]
        return k if re.fullmatch(r'[A-Z][A-Z.]{0,5}', k) else None

    def look_through(ws):
        """The companies inside, at their weights, through the Hub's other data."""
        tot = cov = 0.0
        acc = defaultdict(float)
        sect = defaultdict(float)
        rows = []
        for k, w, v in ws:
            t = key_ticker(k)
            tot += w
            if not t:
                continue
            c = cons_rows.get(t)
            if c and c.get('sector'):
                sect[c['sector']] += w
            if c:
                cov += w
                if c.get('target_mean') and c.get('price'):
                    acc['tw'] += w; acc['t'] += w * max(-0.6, min(1.0, c['target_mean'] / c['price'] - 1))
                if c.get('rating_mean'):
                    acc['rw'] += w; acc['r'] += w * c['rating_mean']
                if c.get('our_price') and c.get('price'):
                    acc['ow'] += w; acc['o'] += w * (c['our_price'] / c['price'] - 1)
                if c.get('eps_rev_30d') is not None:
                    acc['ew'] += w
                    acc['eu'] += w if c['eps_rev_30d'] > 0.001 else 0
                    acc['ed'] += w if c['eps_rev_30d'] < -0.001 else 0
                if c.get('next_earnings') and today.isoformat() <= c['next_earnings'] <= (today + dt.timedelta(days=14)).isoformat():
                    acc['soon'] += w
            cu = t_cusip.get(t)
            fh = f_hist.get(cu) if cu else None
            fq = next((x for x in (fh or []) if periods13 and x[0] == periods13[-1] and x[1] is not None), None)
            if fq:
                acc['fw'] += w
                acc['fb'] += w if fq[1] > 0 else 0
                acc['fs'] += w if fq[1] < 0 else 0
            ot = [x for x in officials.get(t, []) if (x.get('date') or '') >= d90]
            if ot:
                b = sum(1 for x in ot if (x.get('type') or '').startswith('purchase'))
                acc['ob'] += w if b > len(ot) - b else 0
                acc['os'] += w if b < len(ot) - b else 0
                acc['on'] += len(ot)
            if t in ins and ins[t].get('buys'):
                acc['ib'] += w
            d = debt_rows.get(t)
            if d and d.get('implied_cds_5y_bps') is not None:
                acc['cw'] += w; acc['c'] += w * d['implied_cds_5y_bps']
            if len(rows) < 25 and c:
                rows.append([t, c.get('name'), round(w, 5), c.get('price'), c.get('target_mean'), c.get('rating_mean'), c.get('our_price'), c.get('next_earnings'),
                             (fq[1] if fq else None), len(ot)])
        r = lambda a, b: (acc[a] / acc[b]) if acc[b] else None
        return {'weight_seen': round(tot, 4), 'covered': round(cov, 4), 'target_ret': r('t', 'tw'), 'rating': r('r', 'rw'), 'ours_ret': r('o', 'ow'),
                'eps_up': r('eu', 'ew'), 'eps_down': r('ed', 'ew'), 'reporting_14d': round(acc['soon'], 4), 'f13_buying': r('fb', 'fw'), 'f13_selling': r('fs', 'fw'),
                'officials_buying': round(acc['ob'], 4), 'officials_selling': round(acc['os'], 4), 'officials_trades': int(acc['on']), 'insider_buying': round(acc['ib'], 4),
                'cds_bps': r('c', 'cw'), 'sectors': {k: round(v, 4) for k, v in sorted(sect.items(), key=lambda x: -x[1])[:12]}, 'rows': rows}

    by = defaultdict(list)
    fl_of = {}                                 # symbol → (leveraged / inverse, {month: (sales + reinvestments, redemptions)})
    parties = {k: defaultdict(lambda: {'etfs': 0, 'aum': 0.0, 'x': 0.0, 'y': 0.0}) for k in ('aps', 'custodians', 'lending', 'advisers', 'subadvisers', 'auditors', 'distributors', 'administrators', 'transfer')}
    raw_parties = defaultdict(list)            # kind → [(name, crd, aum, x, y)], merged after the loop

    def pk(name, crd=None):
        return (name or '').strip(), (crd or '').lstrip('0')
    index_rows = []
    for e in etfs:
        sym = e['symbol']
        s = e.get('series')
        nc = ncen.get(s) if s else None
        pr = rr.get(s) if s else None
        hh = hist.get(s) if s else None
        h = holds.get(s) if s else None
        mk = read_json(root / 'cache' / 'market' / f'{sym}.json', {}) or {}
        fund = mk.get('fund') or {}
        st = M.market_stats(mk.get('weekly') or [])
        if sym in UIT_FILES:
            e['act'] = 'uit'
        if sym in uit and not h:
            rows = uit[sym]['rows']
            h = {'date': uit[sym]['at'][:10], 'n': len(rows), 'source': 'sponsor holdings file', 'top': [[r[0], '', r[2], None, r[1], None, r[3], 'EC', 'CORP', 'US', 'Long'] for r in rows[:150]],
                 'weights': [[r[1], r[3], None] for r in rows], 'top10': sum(r[3] for r in sorted(rows, key=lambda x: -x[3])[:10]), 'mix': {'EC': sum(r[3] for r in rows)}}
        if h and not h.get('_mapped'):        # tickers for every position the Hub can name (iShares reports CUSIPs only)
            h = dict(h)
            h['top'] = [x[:4] + [x[4] or key_ticker(x[2] or x[3] or '') if (x[7] in EQUITY) else x[4]] + x[5:] for x in h.get('top') or []]
            h['weights'] = [[key_ticker(k) or k, w, v] for k, w, v in h.get('weights') or []]
            h['_mapped'] = True
        ac, strat = classify(e, h, nc)
        fees = dict((pr or {}).get('fees') or {})
        cf = ((pr or {}).get('class_fees') or {}).get(e.get('cls') or '') or {}
        fees.update({k: v for k, v in cf.items() if v is not None})
        expense = fees.get('net') if fees.get('net') is not None else fees.get('gross')
        if expense is None and nc and nc.get('net_expenses') is not None:
            expense = nc['net_expenses'] / 100
        if expense is None:
            expense = fund.get('y_expense')
        months = sorted(((hh or {}).get('months') or {}).items())[-12:]
        net = [[m, (v[0] or 0) + (v[1] or 0) - (v[2] or 0)] for m, v in months]
        f3 = sum(x[1] for x in net[-3:]) if net else None
        f12 = sum(x[1] for x in net) if len(net) >= 6 else None
        assets_np = h.get('net_assets') if h else (sorted(((hh or {}).get('assets') or {}).items())[-1][1] if (hh or {}).get('assets') else None)
        aum = fund.get('y_assets') or assets_np
        aps = (nc or {}).get('aps') or []
        active_aps = [a for a in aps if (a[1] or 0) or (a[2] or 0)]
        cu = t_cusip.get(sym)
        o13 = h13.get(cu) if cu else None
        off = officials.get(sym, [])
        lt = look_through(h.get('weights') or []) if h and ac in ('Equity', 'Multi-asset / alternatives', 'Leveraged / inverse') and h.get('weights') else None
        if h:
            for k, w, v in h.get('weights') or []:
                t = key_ticker(k)
                if t and w and w > 0:
                    by[t].append([sym, round(w, 6), v])
        issuer = M.issuer_of(e.get('name')) or ((nc or {}).get('registrant') or {}).get('family')
        sh = shorts.get(sym)
        lev = bool(e.get('leveraged') or (nc or {}).get('multi_inverse'))
        fl_of[sym] = (lev or bool(e.get('inverse')), {m: ((v[0] or 0) + (v[1] or 0), v[2] or 0)
                                                      for m, v in sorted(((hh or {}).get('months') or {}).items())[-15:]})
        row = {'symbol': sym, 'name': e.get('name'), 'issuer': issuer, 'exchange': e.get('exchange'), 'act': e.get('act'), 'asset_class': ac, 'strategy': strat,
               'leveraged': bool(e.get('leveraged') or (nc or {}).get('multi_inverse')), 'inverse': bool(e.get('inverse')), 'category': fund.get('y_category'),
               'expense': expense, 'aum': aum, 'flows_3m': f3, 'flows_12m': f12, 'n_holdings': (h or {}).get('n'), 'top10': (h or {}).get('top10'),
               'track_diff': None if lev else (nc or {}).get('track_diff'), 'track_err': None if lev else (nc or {}).get('track_err'), 'r1m': st.get('r1m'), 'r3m': st.get('r3m'), 'ytd': st.get('ytd'),
               'r1y': st.get('r1y'), 'r3y': st.get('r3y'), 'r5y': st.get('r5y'), 'vol': st.get('vol1y'), 'max_dd': st.get('max_dd'), 'dollar_vol': st.get('dollar_vol'),
               'premium': fund.get('premium'), 'yield': fund.get('y_yield'), 'inception': fund.get('y_inception'), 'price': st.get('price') or fund.get('y_price'),
               'holders13f': (o13 or {}).get('holders'), 'usd13f': (o13 or {}).get('usd'), 'holders13f_chg': ((o13['holders'] - o13['prev_holders']) if o13 and o13.get('prev_holders') is not None else None),
               'officials_1y': sum(1 for x in off if (x.get('date') or '') >= d365), 'short_dtc': (sh or {}).get('dtc'), 'aps': len(active_aps),
               'lending_income': (nc or {}).get('lending_income'), 'lt_target': (lt or {}).get('target_ret'), 'lt_ours': (lt or {}).get('ours_ret'),
               'lt_13f_buy': (lt or {}).get('f13_buying'), 'index_fund': bool((nc or {}).get('index')), 'cik': e.get('cik'), 'series': s}
        index_rows.append(row)
        # parties
        a_ = aum or 0
        for a in active_aps:
            raw_parties['aps'].append((a[0], (a[3] or '').lstrip('0'), a_, a[1] or 0, abs(a[2] or 0)))
        for k, src, flt in (('custodians', 'custodians', lambda x: not x[1]), ('lending', 'lending_agents', lambda x: True), ('administrators', 'administrators', lambda x: True),
                            ('transfer', 'transfer_agents', lambda x: True)):
            for x in {x[0]: x for x in (nc or {}).get(src) or [] if flt(x)}.values():
                raw_parties[k].append((x[0], '', a_, ((nc or {}).get('lending_income') or 0) if k == 'lending' else 0, 0))
        for x in (nc or {}).get('advisers') or []:
            raw_parties['subadvisers' if 'sub' in (x[1] or '').lower() else 'advisers'].append((x[0], (x[2] or '').lstrip('0'), a_, 0, 0))
        for x in set((nc or {}).get('accountant') or []):
            raw_parties['auditors'].append((x, '', a_, 0, 0))
        for x in {d[0] for d in (nc or {}).get('distributor') or []}:
            raw_parties['distributors'].append((x, '', a_, 0, 0))
        # the page
        doc = {'symbol': sym, 'generated_at': now(), **{k: row[k] for k in ('name', 'issuer', 'exchange', 'act', 'asset_class', 'strategy', 'leveraged', 'inverse', 'category', 'cik', 'series')},
               'cls': e.get('cls'), 'series_classes': e.get('series_classes'), 'registrant': e.get('registrant') or ((nc or {}).get('registrant') or {}).get('name') or (h or {}).get('registrant'),
               'market': {**st, **{k: fund.get(k) for k in ('y_nav', 'premium', 'y_assets', 'y_yield', 'y_beta3y', 'y_family', 'y_expense', 'y_turnover', 'y_inception', 'y_avg_vol', 'y_duration', 'y_maturity', 'y_sectors', 'y_mix')},
                          'weekly': [[w[0], w[2]] for w in (mk.get('weekly') or [])][-261:], 'at': mk.get('at')},
               'prospectus': {'filed': (pr or {}).get('filed'), 'form': (pr or {}).get('form'), 'adsh': (pr or {}).get('adsh'), 'cik': (pr or {}).get('cik'), 'fees': fees,
                              'annual': (((pr or {}).get('annual') or {}).get(e.get('cls') or '') or next(iter(((pr or {}).get('annual') or {}).values()), {})),
                              'benchmarks': benchmarks_of(pr), 'objective': (pr or {}).get('objective'), 'strategy': (pr or {}).get('strategy'),
                              'risks': (pr or {}).get('risks'), 'risk_narrative': (pr or {}).get('risk_narrative')} if pr else None,
               'ncen': {k: v for k, v in (nc or {}).items() if k not in ('aps', 'classes', 'listings')} if nc else None,
               'aps': sorted(aps, key=lambda a: -((a[1] or 0) + abs(a[2] or 0)))[:40], 'aps_total': len(aps),
               'holdings': {k: v for k, v in (h or {}).items() if k not in ('weights', '_mapped')} if h else None, 'weights': (h or {}).get('weights', [])[:600] if h else [],
               'flows': {'months': [[m] + v for m, v in months], 'net': net, 'assets': sorted(((hh or {}).get('assets') or {}).items())[-12:],
                         'returns': sorted((((hh or {}).get('returns') or {}).get(e.get('cls') or '') or next(iter(((hh or {}).get('returns') or {}).values()), {})).items())[-12:]} if hh else None,
               'holders13f': o13, 'periods13f': periods13, 'officials': sorted(off, key=lambda x: x.get('date') or '', reverse=True)[:40],
               'short': {**sh, 'settlement': short_date} if sh else None, 'look_through': lt,
               'npx': {k: npx[e['cik']].get(k) for k in ('name', 'latest_filing', 'filing_count')} if e.get('cik') in npx else None,
               'filings': {'edgar': f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={e["cik"]}&type=&dateb=&owner=include&count=40' if e.get('cik') else None,
                           'prospectus': f'https://www.sec.gov/Archives/edgar/data/{(pr or {}).get("cik")}/{(pr or {}).get("adsh", "").replace("-", "")}/' if pr else None,
                           'ncen': f'https://www.sec.gov/Archives/edgar/data/{(nc or {}).get("cik")}/{(nc or {}).get("acc", "").replace("-", "")}/' if nc else None,
                           'nport': f'https://www.sec.gov/Archives/edgar/data/{((hh or {}).get("reports") or [{}])[-1].get("cik")}/{(((hh or {}).get("reports") or [{}])[-1].get("acc") or "").replace("-", "")}/' if hh else None}}
        wj(pub / 'e' / f'{sym}.json', _clean(doc))
    # the ETFs that hold each company
    names = {e['symbol']: e.get('name') for e in etfs}
    aum_of = {r['symbol']: r['aum'] for r in index_rows}
    for t, lst in by.items():
        lst.sort(key=lambda x: -((x[2] or (x[1] * (aum_of.get(x[0]) or 0)))))
        tot = sum((x[2] or 0) for x in lst)
        wj(pub / 'by' / f'{t.replace("/", "-")}.json', _clean({'ticker': t, 'etfs': len(lst), 'usd': tot, 'name': (cons_rows.get(t) or {}).get('name'),
                                                                     'rows': [[x[0], names.get(x[0]), x[1], x[2], aum_of.get(x[0])] for x in lst[:400]],
                                                                     'flows': implied_flows(lst, fl_of)}))
    fields = list(index_rows[0].keys()) if index_rows else []
    wj(pub / 'index.json', _clean({'generated_at': now(), 'fields': fields, 'rows': [[r[k] for k in fields] for r in index_rows]}))
    lt_ = {k: merge_parties(raw_parties.get(k, []), k) for k in parties}
    wj(pub / 'parties.json', _clean({'generated_at': now(), 'fields': ['name', 'etfs', 'aum', 'x', 'y', 'crd'], 'tables': lt_}))
    st = read_json(root / 'state.json', {}) or {}
    status = {'built_at': now(), 'etfs': len(index_rows), 'with_series': sum(1 for e in etfs if e.get('series')), 'ncen': len(ncen), 'prospectus': len(rr),
              'nport_funds': len(hist), 'holdings': len(holds), 'holdings_source': hd.get('source'), 'companies_held': len(by), 'market': st.get('market_summary'),
              'datasets': {k: v for k, v in (st.get('datasets') or {}).items()}, 'periods13f': periods13}
    write_json(pub / 'status.json', status)
    if verbose:
        print(f'etf build: {len(index_rows)} ETFs, {len(ncen)} N-CEN, {len(rr)} prospectus, {len(holds)} portfolios, {len(by)} companies held', flush=True)
    return {k: status[k] for k in ('etfs', 'ncen', 'prospectus', 'holdings', 'companies_held')}


PARTY_STOP = {'LLC', 'INC', 'LP', 'LLP', 'LTD', 'CO', 'CORP', 'CORPORATION', 'COMPANY', 'CAPITAL', 'SECURITIES', 'MARKETS', 'AMERICAS', 'USA', 'US', 'NA',
              'NATIONAL', 'ASSOCIATION', 'THE', 'AND', 'OF', 'GROUP', 'HOLDINGS', 'PRO', 'LIMITED', 'PLC', 'AG', 'SA', 'NV', 'BV', 'LLP', 'GLOBAL'}


def party_tokens(name):
    n = (name or '').upper().replace('&', ' ').replace('J.P.', 'JP').replace('J. P.', 'JP')
    toks = [t for t in re.sub(r'[^A-Z0-9 ]', ' ', n.replace('.', '')).split() if t not in PARTY_STOP]
    return tuple(toks[:2]) or (n.strip(),)


def merge_parties(rows, kind):
    """One line per firm: the same CRD number, or the same first two distinctive words ("Jane Street", "Goldman Sachs"),
    with a one-word name folded into the longer one it begins ("Citigroup" → "Citigroup Global"). Sorted by activity."""
    key_of_crd, groups = {}, {}
    for name, crd, *_ in rows:
        t = party_tokens(name)
        if crd:
            key_of_crd.setdefault(crd, t)
    tok_crd = {t: c for c, t in key_of_crd.items()}
    keys = {party_tokens(n) for n, *_ in rows}
    fold = {}
    for t in keys:
        if len(t) == 1 and len(t[0]) >= 4:
            longer = [u for u in keys if len(u) > 1 and u[0] == t[0]]
            if len(longer) == 1:
                fold[t] = longer[0]
    for name, crd, aum, x, y in rows:
        t = party_tokens(name)
        t = key_of_crd.get(crd, fold.get(t, t))
        g = groups.setdefault(t, {'names': defaultdict(int), 'etfs': 0, 'aum': 0.0, 'x': 0.0, 'y': 0.0, 'crd': crd or tok_crd.get(t)})
        g['names'][name] += 1; g['etfs'] += 1; g['aum'] += aum or 0; g['x'] += x or 0; g['y'] += y or 0
    out = []
    for g in groups.values():
        nm = max(g['names'].items(), key=lambda kv: (kv[1], any(c.islower() for c in kv[0])))[0]
        out.append([nm, g['etfs'], round(g['aum']), round(g['x']), round(g['y']), g['crd'] or None])
    order = (lambda r: -(r[3] + r[4])) if kind == 'aps' else (lambda r: -r[3]) if kind == 'lending' else (lambda r: -r[2])
    return sorted(out, key=lambda r: (order(r), -r[1]))[:100]


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 6)
    if isinstance(o, set):
        return sorted(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['collect', 'build'])
    ap.add_argument('--root', default='etf')
    ap.add_argument('--minutes', type=float, default=30)
    ap.add_argument('--no-datasets', action='store_true')
    ap.add_argument('--hub', default=None, help="the Hub's data folder (disclosures/docs/data): 13F, officials, short interest, insiders, N-PX")
    ap.add_argument('--consensus', default=None, help='public/ of the consensus-history branch')
    ap.add_argument('--debt', default=None, help='public/ of the debt-history branch')
    a = ap.parse_args()
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.minutes, datasets=not a.no_datasets)), flush=True)
    else:
        print(json.dumps(build(a.root, a.hub, a.consensus, a.debt)), flush=True)


if __name__ == '__main__':
    main()
