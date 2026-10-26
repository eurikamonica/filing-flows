import json
from pathlib import Path
from unittest.mock import patch
import pytest
from pipeline import ipo
from pipeline.company_quality import measures

ROOT=Path(__file__).resolve().parents[1]
META=json.loads((ROOT/'pipeline/data/ipo/2130357.json').read_text())
META={k:META[k] for k in ('cik','name','form','filed','accession','source_url')}


def test_quality_missing_and_negative_income():
    m={x['id']:x for x in measures({'revenue':100,'ni':-40,'ocf':20,'capex':5,'sbc':10})}
    assert m['cash_conversion']['value'] is None
    assert m['fcf_margin']['value']==.15
    assert m['net_margin']['value']==-.4
    assert m['gross_margin']['value'] is None
    assert all(m['value'] is None for m in measures({}))


def test_anthropic_original_statement_reconciliation():
    html=(ROOT/'tests/fixtures/anthropic_s1_tables.html').read_text()
    periods=ipo.parse(html,META)['periods']
    assert len(periods)==5
    p=periods[-1];v=p['values']
    assert p['label']=='H1 2026'
    assert v['revenue']==16286000000
    assert v['ni']==-80748000000
    assert v['ocf']==3929000000
    assert v['capex']==482000000
    assert v['ocf']-v['capex']==3447000000
    assert next(m for m in p['metrics'] if m['id']=='gross_margin')['value'] is None
    with pytest.raises(ValueError): ipo.parse(html.replace('16,286','16,999'),META)
    with pytest.raises(ValueError): ipo.parse(html.replace('2026','2027'),META)
    with pytest.raises(ValueError): ipo.parse(html.replace('millions','thousands'),META)


def tagged(value='100', extra=''):
    return f'''<xbrli:context id="c"><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>{extra}</xbrli:context><xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit><ix:nonFraction name="us-gaap:Revenues" contextRef="c" unitRef="u" scale="6">{value}</ix:nonFraction>'''


def test_inline_safety():
    vals,cur=ipo.inline_values(tagged()); assert cur=='USD'; assert next(iter(vals.values()))==100e6
    with pytest.raises(ValueError): ipo.inline_values(tagged(extra='<xbrli:scenario><xbrldi:explicitMember>proforma</xbrldi:explicitMember></xbrli:scenario>'))
    with pytest.raises(ValueError): ipo.inline_values(tagged()+tagged('101'))
    with pytest.raises(ValueError): ipo.inline_values(tagged().replace('scale="6"','scale="6" xsi:nil="true"'))


def test_failed_refresh_keeps_verified_snapshot(tmp_path):
    with patch.object(ipo.sec,'get_json',side_effect=RuntimeError('offline')):
        ipo.publish(tmp_path/'out',tmp_path/'cache',True)
    d=json.loads((tmp_path/'out/2130357.json').read_text())
    assert d['scan']['state']=='failed'
    assert d['scan']['last_success'] is None
    assert d['accession']==META['accession']
    assert len(list((tmp_path/'cache/history/2130357').glob('*.json')))==1
