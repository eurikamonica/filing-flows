"""pipeline/fx.py: when FRED does not answer, the ECB's reference rates and then the Treasury's quarterly rates; a source
that failed is not asked again in the run, and what is on file serves when nothing answers."""
import json

from pipeline import fx


def test_fallbacks(monkeypatch):
    asked = []

    def get(url):
        asked.append(url.split('/')[2])
        if 'stlouisfed' in url:
            raise RuntimeError('Read timed out')
        if 'frankfurter' in url:
            return json.dumps({'rates': {'2026-10-01': {'CAD': 1.25}, '2026-10-02': {'CAD': 1.6}}})
        if 'treasury' in url:
            assert 'Taiwan-Dollar' in url
            return json.dumps({'data': [{'record_date': '2026-06-30', 'exchange_rate': '32.0'}, {'record_date': '2026-09-30', 'exchange_rate': 'x'}]})
        raise AssertionError(url)
    monkeypatch.setattr(fx, '_get', get)
    monkeypatch.setattr(fx, '_tried', {})
    cache = {}
    cad = fx.daily('CAD', cache)
    assert cad == {'2026-10-01': 0.8, '2026-10-02': 0.625} and cache['CAD']['src'] == 'ecb' and fx.source_name('CAD', cache) == 'ECB reference rates'
    twd = fx.daily('TWD', cache)
    assert twd == {'2026-06-30': 1 / 32} and cache['TWD']['src'] == 'treasury' and 'Treasury' in fx.source_name('TWD', cache)
    n = len(asked)
    assert fx.daily('CAD', cache) is cad and len(asked) == n            # once a run
    # nothing answers: yesterday's rates on file serve, and the cache keeps its date (tried again tomorrow)
    monkeypatch.setattr(fx, '_tried', {})
    monkeypatch.setattr(fx, '_get', lambda url: (_ for _ in ()).throw(RuntimeError('down')))
    old = {'EUR': {'at': '2000-01-01', 'd': {'2026-10-01': 1.1}, 'src': 'fred'}}
    assert fx.daily('EUR', old) == {'2026-10-01': 1.1} and old['EUR']['at'] == '2000-01-01'
    assert fx.daily('XXX', {}) == {}
