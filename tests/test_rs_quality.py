"""Quality research → X posts (pipeline/posts_quality.py): each format plans from the published files, every rule-written
phrasing passes the post checks and the training corpus's fact check, the formats reach the registry, the owner's
buttons and the training corpus."""
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ['ticker', 'cik', 'name', 'sector', 'mcap', 'price', 'f_score', 'f_n', 'z', 'z_model', 'z_zone', 'm_score', 'm_flag', 'sy',
          'div_y', 'bb_y', 'fcf_y', 'fcf_sbc_y', 'oe_y', 'roic', 'roic_inc', 'wacc', 'spread', 'dol', 'fixed_q', 'var_ratio',
          'accruals', 'gp_a', 'asset_g', 'net_iss', 'ev_s', 'growth', 'margin', 'r40', 'resid', 'line_ev_s', 'composite',
          'comp_rank', 'margin_fc4', 'fy_end']


def _row(**k):
    base = {f: None for f in FIELDS}
    base.update(sector='technology', fy_end='2025-12-31', f_n=9)
    base.update(k)
    return [base[f] for f in FIELDS]


def hub(tmp_path):
    q = tmp_path / 'disclosures' / 'data' / 'research' / 'quality'
    (q / 'c').mkdir(parents=True)
    rows = [
        _row(ticker='MSFT', cik=789019, name='MICROSOFT CORP', mcap=3.1e12, f_score=9, sy=0.031, div_y=0.008, bb_y=0.023, fcf_y=0.025,
             fcf_sbc_y=0.022, dol=3.1, fixed_q=21e9, var_ratio=0.31, ev_s=12.0, r40=58, resid=-0.1, line_ev_s=13.2, growth=0.15, margin=0.43),
        _row(ticker='KO', cik=21344, name='COCA COLA CO', mcap=2.9e11, f_score=9, sy=0.045, div_y=0.03, bb_y=0.015),
        _row(ticker='COST', cik=909832, name='COSTCO WHOLESALE CORP /NEW', mcap=4.1e11, f_score=9, sy=0.012, div_y=0.006, bb_y=0.006),
        _row(ticker='WBA', cik=1618921, name='Walgreens Boots Alliance, Inc.', mcap=9e9, z=0.84, z_model="Z''", z_zone='distress', sector='health'),
        _row(ticker='PARA', cik=813828, name='Paramount Global', mcap=7.5e9, z=1.02, z_model="Z''", z_zone='distress', sector='communication'),
        _row(ticker='F', cik=37996, name='FORD MOTOR CO', mcap=4.4e10, z=1.21, z_model='Z', z_zone='distress', sector='consumer-disc',
             sy=0.081, div_y=0.062, bb_y=0.019),
        _row(ticker='SMCI', cik=1375365, name='Super Micro Computer, Inc.', mcap=2.8e10, m_score=-1.21, m_flag=True),
        _row(ticker='SNOW', cik=1640147, name='Snowflake Inc.', mcap=5.9e10, fcf_y=0.016, fcf_sbc_y=-0.006),
        _row(ticker='PLTR', cik=1321655, name='Palantir Technologies Inc.', mcap=3.5e11, fcf_y=0.012, fcf_sbc_y=0.004),
        _row(ticker='CRM', cik=1108524, name='Salesforce, Inc.', mcap=2.5e11, fcf_y=0.05, fcf_sbc_y=0.032),
        _row(ticker='UBER', cik=1543151, name='Uber Technologies, Inc', mcap=1.6e11, fcf_y=0.042, fcf_sbc_y=0.03),
        _row(ticker='MO', cik=764180, name='ALTRIA GROUP, INC.', mcap=9.6e10, sy=0.095, div_y=0.07, bb_y=0.025),
        _row(ticker='GOOGL', cik=1652044, name='Alphabet Inc.', mcap=2.4e12, ev_s=6.1, r40=46, resid=-0.55, line_ev_s=10.6, growth=0.14,
             margin=0.32),
    ]
    (q / 'index.json').write_text(json.dumps({'fields': FIELDS, 'rows': rows, 'sector_names': {'technology': 'Technology'}}))
    (q / 'c' / 'SMCI.json').write_text(json.dumps({'metrics': {'beneish': {'m': -1.21, 'idx': {
        'dsri': 1.62, 'gmi': 1.1, 'aqi': 1.0, 'sgi': 2.1, 'depi': 1.0, 'sgai': 0.8, 'lvgi': 1.1, 'tata': 0.02}}}}))
    (q / 'ledger.json').write_text(json.dumps({'months': {
        '2026-09': {'month': '2026-09', 'frozen_at': '2026-09-02T07:00:00+00:00', 'n': 2100, 'top': [['KO', 0.9]] * 3,
                    'result': {'ic': 0.041, 'top': 0.021, 'bottom': -0.004, 'spread': 0.025, 'n': 2050}},
        '2026-10': {'month': '2026-10', 'frozen_at': '2026-10-01T07:00:00+00:00', 'n': 2150,
                    'top': [['MSFT', 0.93], ['KO', 0.92], ['COST', 0.91], ['MO', 0.9], ['CRM', 0.89]], 'result': None}},
        'scored': 1}))
    return tmp_path


def test_quality_post_formats(tmp_path):
    from pipeline import corpus, engage, local_model as L, notify, posts_quality as PQ, xkinds as X
    X.load()
    site = notify.Site(str(hub(tmp_path)))
    ok = lambda *a, **k: True
    today = dt.date(2026, 10, 19)
    c = engage.cfg()
    names = ['quality_piotroski', 'quality_altman', 'quality_beneish', 'quality_yield', 'quality_sbc', 'quality_leverage',
             'quality_cheap', 'quality_factors']
    assert set(names) <= set(X.REG)
    assert {b['kind'] for b in X.buttons()} >= {'engage_' + n for n in names}
    got = {n: engage.registered_plan(n, site, [], c, {}, ok, today) for n in names}
    assert all(got.values()), [n for n, p in got.items() if not p]
    assert got['quality_piotroski']['allowed'][:3] == ['MSFT', 'COST', 'KO']                 # largest first
    assert "WBA" in got['quality_altman']['allowed'] and "Z'' 0.84" in got['quality_altman']['fallback']
    assert 'not an accusation' in got['quality_beneish']['fallback'] and 'sales growth index 2.10' in got['quality_beneish']['fallback']
    assert got['quality_yield']['allowed'][0] == 'MO' and '$MO 9.5% (7.0% div + 2.5% buybacks)' in got['quality_yield']['fallback']
    assert got['quality_sbc']['allowed'][:2] == ['SNOW', 'PLTR'] and '$SNOW 1.6% → −0.6%' in got['quality_sbc']['fallback']
    assert got['quality_leverage']['cashtags'] == ['MSFT'] and 'about 3.1%' in got['quality_leverage']['fallback']
    assert got['quality_cheap']['cashtags'] == ['GOOGL'] and '6.1x' in got['quality_cheap']['fallback']
    assert '+2.5%' in got['quality_factors']['task'] and got['quality_factors']['allowed'][0] == 'MSFT'
    for n, p in got.items():
        msgs = engage.messages(n, p['task'], p['cashtags'], p['tags'], p.get('allowed'))
        for fb in p['fallbacks']:
            post = engage.clean(fb, p['cashtags'], p['tags'], allowed=p.get('allowed'), must=p.get('must'), lines=p.get('lines', False))
            assert ('\n' in post) == bool(p.get('lines')), (n, post)
            assert not L.unsupported(post, L.compact(msgs)), (n, post, L.unsupported(post, L.compact(msgs)))
            ex = corpus.example(n, 'k', msgs, fb, 'engage', p['cashtags'], p['tags'], None, allowed=p.get('allowed'),
                                lines=p.get('lines', False), must=p.get('must'))
            assert ex is not None, (n, fb)
    # a cooldown on every name leaves nothing to post
    none = lambda *a, **k: False
    assert engage.registered_plan('quality_piotroski', site, [], c, {}, none, today) is None
    # the training corpus plans the registered formats too
    out = corpus.market_examples(site, [], {}, set(), today, limits={k: 0 for k in corpus.MARKET})
    assert out.get('quality_piotroski') and out.get('quality_beneish')
    assert all(ex['target'] and 'not an accusation' in ex['target'] for ex in out['quality_beneish'])
    _ = PQ


def test_quality_views_and_tab_wiring():
    views = json.load(open(os.path.join(ROOT, 'disclosures', 'docs', 'views.json'), encoding='utf-8'))
    q = next(v for v in views if v['id'] == 'quality')
    assert q['script'] == 'quality-view.js' and q['global'] == 'QualityView'
    for f in ('quality-view.js', 'quality.js'):
        assert os.path.exists(os.path.join(ROOT, 'disclosures', 'docs', f)), f
    html = open(os.path.join(ROOT, 'disclosures', 'docs', 'index.html'), encoding='utf-8').read()
    assert 'data-tab="quality"' in html and 'src="quality.js"' in html and 'src="quality-view.js"' in html
    ci = open(os.path.join(ROOT, '.github', 'workflows', 'ci.yml'), encoding='utf-8').read()
    assert 'docs/quality.js' in ci and 'docs/quality-view.js' in ci
    wf = open(os.path.join(ROOT, '.github', 'workflows', 'research-quality.yml'), encoding='utf-8').read()
    assert 'research-quality' in wf and 'quality.py collect' in wf and 'quality.py build' in wf
