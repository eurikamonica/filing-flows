"""FSA Beta deterministic accounting engine. Created by ChatGPT (OpenAI).
All amounts share one currency/unit. Missing is never zero.
"""
import datetime as dt
import math

AUTHOR = 'ChatGPT (OpenAI)'
FIELDS = ('revenue','operating_income','net_income','ocf','capex','assets',
          'operating_assets','operating_liabilities','financial_assets','financial_liabilities','equity')
RESERVE_FIELDS = ('opening','additions','releases','utilization','other','closing')


def analyze(data):
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Expected schema_version: 1')
    sources = data.get('sources', {})
    if not isinstance(sources, dict):
        raise ValueError('sources must be an object keyed by evidence ID')
    for sid, src in sources.items():
        if not isinstance(src, dict) or not isinstance(src.get('excerpt',''),str):
            raise ValueError('Each source must be an object with a text excerpt')
    periods = data.get('periods', [])
    if not isinstance(periods,list) or not 1 <= len(periods) <= 20:
        raise ValueError('Provide 1–20 periods, oldest first')
    warnings, results = [], []
    used = set()
    def number(obj, key, context, nonnegative=False):
        cell = obj.get(key)
        if cell is None:
            return None
        if not isinstance(cell,dict) or set(cell) - {'value','source_ids'}:
            raise ValueError(f'{context}.{key}: expected value and source_ids')
        value, refs = cell.get('value'), cell.get('source_ids',[])
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError(f'{context}.{key}: value must be finite')
        if not isinstance(refs,list) or any(not isinstance(s,str) or s not in sources for s in refs):
            raise ValueError(f'{context}.{key}: unknown source ID')
        if nonnegative and value < 0:
            raise ValueError(f'{context}.{key}: use nonnegative magnitude')
        used.update(refs)
        if not refs:
            warnings.append(f'{context}.{key}: user supplied; source missing')
        return float(value)
    last_end = None
    for p in periods:
        start, end = dt.date.fromisoformat(p['start']), dt.date.fromisoformat(p['end'])
        days = (end-start).days + 1
        if end < start or (last_end and start <= last_end):
            raise ValueError('Periods must be chronological and nonoverlapping')
        last_end = end
        kind = p.get('kind')
        if kind not in ('quarter','annual'):
            raise ValueError('kind must be quarter or annual; convert YTD before import')
        if not ((75 <= days <= 105) if kind == 'quarter' else (350 <= days <= 380)):
            raise ValueError('Duration does not match kind; YTD/transition periods unsupported')
        label = str(p.get('label',p['end']))
        if p.get('currency', data.get('currency')) != data.get('currency') or p.get('unit', data.get('unit')) != data.get('unit'):
            raise ValueError('Mixed currencies/units must be normalized before import')
        values = {k:number(p.get('values',{}),k,label,k=='capex') for k in FIELDS}
        n = values
        metrics = {}
        def metric(key, value, formula, inputs, assumption=None):
            metrics[key] = {'value':value,'formula':formula,'inputs':inputs,'assumption':assumption}
        def sub(a,b):
            return n[a]-n[b] if n[a] is not None and n[b] is not None else None
        metric('accruals',sub('net_income','ocf'),'Net income - OCF',['net_income','ocf'])
        metric('fcf',sub('ocf','capex'),'OCF - capex',['ocf','capex'])
        metric('noa',sub('operating_assets','operating_liabilities'),'Operating assets - operating liabilities',['operating_assets','operating_liabilities'])
        metric('nfo',sub('financial_liabilities','financial_assets'),'Financial liabilities - financial assets',['financial_liabilities','financial_assets'])
        tax = p.get('operating_tax_rate')
        if tax is not None and (isinstance(tax,bool) or not isinstance(tax,(int,float)) or not math.isfinite(tax) or not 0 <= tax <= 1):
            raise ValueError('operating_tax_rate must be between 0 and 1')
        nopat = n['operating_income']*(1-tax) if tax is not None and n['operating_income'] is not None else None
        metric('nopat_estimate',nopat,'Operating income × (1 - assumed operating tax rate)',['operating_income'],tax)
        ratio = n['ocf']/n['net_income'] if n['ocf'] is not None and n['net_income'] is not None and n['net_income']>0 else None
        metric('cash_conversion',ratio,'OCF / positive net income',['ocf','net_income'])
        prev = results[-1] if results else None
        contiguous = prev and (start-dt.date.fromisoformat(prev['end'])).days == 1 and prev['kind']==kind
        avg_assets = (n['assets']+prev['values']['assets'])/2 if contiguous and n['assets'] is not None and prev['values']['assets'] is not None else None
        prev_noa = prev['metrics']['noa']['value'] if contiguous else None
        noa = metrics['noa']['value']
        avg_noa = (noa+prev_noa)/2 if noa is not None and prev_noa is not None else None
        accr = metrics['accruals']['value']
        metric('accrual_ratio',accr/avg_assets if accr is not None and avg_assets is not None and avg_assets>0 else None,'(Net income - OCF) / average total assets',['net_income','ocf','assets','prior.assets'])
        metric('rnoa',nopat/avg_noa if nopat is not None and avg_noa is not None and avg_noa>0 else None,'Estimated NOPAT / average NOA (period return, not annualized)',['operating_income','noa','prior.noa'],tax)
        nfo = metrics['nfo']['value']
        residual = noa-nfo-n['equity'] if all(v is not None for v in (noa,nfo,n['equity'])) else None
        metric('balance_residual',residual,'NOA - NFO - equity',['noa','nfo','equity'])
        asset_gap = n['operating_assets'] + n['financial_assets'] - n['assets'] if all(n[k] is not None for k in ('operating_assets','financial_assets','assets')) else None
        metric('asset_classification_residual',asset_gap,'Operating assets + financial assets - total assets',['operating_assets','financial_assets','assets'])
        flags = []
        if asset_gap is not None and abs(asset_gap)>max(0.01,abs(n['assets'])*0.001):
            flags.append({'id':'asset_gap','level':'warning','text':'Operating and financial assets do not reconcile to total assets.'})
        if accr is not None and accr>0:
            flags.append({'id':'positive_accruals','level':'review','text':'Earnings exceed operating cash flow. Inspect working capital, noncash items and seasonality; this alone does not establish manipulation.'})
        if residual is not None and abs(residual)>max(0.01,abs(n['equity'])*0.001):
            flags.append({'id':'classification_gap','level':'warning','text':'Operating/financing classifications do not reconcile to equity. Review scope, noncontrolling interests and classification.'})
        reserves=[]
        for r in p.get('reserves',[]):
            name=str(r.get('name','Reserve'))
            rv={k:number(r,k,label+'.'+name, k!='other') for k in RESERVE_FIELDS}
            complete=all(v is not None for v in rv.values())
            expected=rv['opening']+rv['additions']-rv['releases']-rv['utilization']+rv['other'] if complete else None
            gap=rv['closing']-expected if complete else None
            valid=gap is not None and abs(gap)<=max(0.01,abs(rv['closing'])*0.001)
            release_income = r.get('release_in_income',False)
            if not isinstance(release_income,bool):
                raise ValueError('release_in_income must be boolean')
            if gap is not None and not valid:
                flags.append({'id':'reserve_gap','level':'warning','text':name+': rollforward does not reconcile; inspect missing movements.'})
            if not complete:
                flags.append({'id':'reserve_incomplete','level':'missing','text':name+': incomplete rollforward; no reconciliation or release inference.'})
            if valid and rv['releases']>0 and release_income:
                flags.append({'id':'reserve_release','level':'review','text':name+': a disclosed release benefits pretax income. Review original estimates and business conditions; this is not proof of a cookie jar.'})
            reserves.append({'name':name,'values':rv,'residual':gap,'reconciles':valid,'release_in_income':release_income,
                             'pretax_release_benefit':rv['releases'] if complete and valid and release_income else None})
        results.append({'label':label,'start':p['start'],'end':p['end'],'kind':kind,'values':values,'metrics':metrics,'reserves':reserves,'findings':flags,'value_source_ids':{k:(p.get('values',{}).get(k) or {}).get('source_ids',[]) for k in FIELDS}})
    return {'schema_version':1,'author':AUTHOR,'company':str(data.get('company','Unnamed')),
            'currency':str(data.get('currency','USD')),'unit':str(data.get('unit','millions')),
            'demo':data.get('demo') is True,'periods':results,'warnings':warnings,
            'sources':{s:sources[s] for s in sorted(used)},
            'limitations':['Screening signals, not fraud determinations.','NOA classifications must be supplied and reviewed; financial-sector classifications need specialist treatment.',
                            'Returns use the stated period and are not annualized. Missing or nonpositive denominators return null.',
                            'Source references are user supplied; Beta validates references, not filing authenticity.']}
