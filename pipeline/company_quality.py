"""Transparent quality measures, never a universal cross-industry score."""
import math
from . import fsa as W

INSTANTS = {'AssetsCurrent', 'LiabilitiesCurrent', 'CashAndCashEquivalentsAtCarryingValue'}


def measures(v):
    """Same-period inputs; ratios are fractions, missing is not zero."""
    def ratio(a, b):
        return a / b if a is not None and b is not None and b > 0 and math.isfinite(a / b) else None
    r, ocf, ni = v.get('revenue'), v.get('ocf'), v.get('ni')
    fcf = ocf - v['capex'] if ocf is not None and v.get('capex') is not None and v['capex'] >= 0 else None
    avg = (v['assets_open'] + v['assets_close']) / 2 if v.get('assets_open', 0) and v.get('assets_close', 0) and min(v['assets_open'], v['assets_close']) > 0 else None
    specs = [
        ('gross_margin', 'Gross margin', ratio(v.get('gp'), r), 'Gross profit / revenue', ['gp','revenue']),
        ('operating_margin', 'Operating margin', ratio(v.get('oi'), r), 'Operating income / revenue', ['oi','revenue']),
        ('net_margin', 'Net margin', ratio(ni, r), 'Net income / revenue', ['ni','revenue']),
        ('ocf_margin', 'Operating cash margin', ratio(ocf, r), 'Operating cash flow / revenue', ['ocf','revenue']),
        ('fcf_margin', 'Free cash flow margin', ratio(fcf, r), '(Operating cash flow − cash CapEx) / revenue', ['ocf','capex','revenue']),
        ('cash_conversion', 'Cash conversion', ratio(ocf, ni), 'Operating cash flow / positive net income', ['ocf','ni']),
        ('sbc_intensity', 'Stock compensation / revenue', ratio(v.get('sbc'), r), 'Stock compensation / revenue; not an extra deduction from GAAP earnings', ['sbc','revenue']),
        ('rd_intensity', 'R&D / revenue', ratio(v.get('rd'), r), 'R&D expense / revenue; investment intensity, not a quality verdict', ['rd','revenue']),
        ('capex_intensity', 'Cash CapEx / revenue', ratio(v.get('capex'), r), 'Cash CapEx / revenue; excludes noncash additions', ['capex','revenue']),
        ('accrual_ratio', 'Accrual ratio', ratio(ni-ocf if ni is not None and ocf is not None else None, avg), '(Net income − operating cash flow) / average assets; not annualized', ['ni','ocf','assets_open','assets_close']),
        ('roa', 'Return on average assets', ratio(ni, avg), 'Net income / average assets; not annualized', ['ni','assets_open','assets_close']),
        ('current_ratio', 'Current ratio', ratio(v.get('current_assets'),v.get('current_liabilities')), 'Current assets / current liabilities', ['current_assets','current_liabilities']),
    ]
    return [{'id':k,'label':label,'value':value,'formula':formula,'inputs':keys,
             'format':'multiple' if k in ('cash_conversion','current_ratio') else 'percent',
             'status':'available' if value is not None else 'not_available'} for k,label,value,formula,keys in specs]


def period(fx, ev, p, annual):
    v = {k:p.get(k) for k in ('ni','ocf','assets_open','assets_close')}
    refs = dict(p.get('ev') or {})
    for key in ('revenue','gp','oi','sbc','rd','capex'):
        v[key], refs[key] = W.keyed(fx,ev,key,p['end'],annual)
    for key,tag in [('current_assets','AssetsCurrent'),('current_liabilities','LiabilitiesCurrent')]:
        v[key],refs[key],_ = W.balance(fx,ev,[tag],p['end'])
    return {'inputs':v,'ev':refs,'metrics':measures(v)}
