"""Rotation axis registry (research specification v5 §3.3, PR slice P0-02): one contract per Rotation X/Y/Z variable —
what it measures, its cadence, when an observation becomes public, how missing values are treated, which transforms
and smoothings the chart offers, and whether any forward forecast is published for it — plus stable identifiers:

  semantic_axis_spec_id   SHA-256 of the canonical JSON of what a chart configuration MEANS (ordered axis keys and
                          their definition versions, units, cadence, observation kind, transform, smoothing, frequency,
                          benchmark, sector definition, calendar, display fill): a data refresh never changes it;
  prediction_artifact_id  SHA-256 of a semantic id plus everything that changes from run to run (entity, target,
                          origin, horizon, model / dataset / code / calibration versions, cutoff).

The registry describes the variables app/rotation.py computes and docs/rotation.js draws; it does not redefine them.
tests/test_axis_registry.py keeps the three in step (keys, price vs filed variables, scales, smoothings, fills).
"""
import hashlib
import json

REGISTRY_VERSION = 'axis_registry_v1'
SCALES = ['raw', 'log', 'rank', 'z']                      # rotation.js ROT_SCALES (spec names: raw, signed_log, rank, zscore)
SMOOTHING = ['none', 'ewma', 'ma', 'holt', 'kalman', 'median']   # rotation.js ROT_SMOOTH
FILL = ['line', 'step', 'avail', 'points']                # rotation.js ROT_FILL: quarterly figures drawn through the months
STATUS = ('calibrated', 'experimental', 'research_peer_prior_only', 'descriptive_only', 'insufficient_data', 'unavailable')

PRICE = {'cadence': 'period_close', 'observation_kind': 'period_end_close', 'lag_periods': 0,
         'available': 'at the period\'s last close (daily closes, split-adjusted)'}
FILED = {'cadence': 'quarterly_sec', 'observation_kind': 'accepted_filing', 'lag_periods': 1,
         'available': 'with the 10-Q / 10-K, weeks after the quarter: lagged one period in every forecast'}

# key: (cadence block, missing policy, in the monthly panel, extra notes)
AXES = {
    'dom': (FILED, 'unknown_not_zero', False, 'year-over-year point change; restatements replace earlier values'),
    'om': (FILED, 'unknown_not_zero', False, ''),
    'dgm': (FILED, 'unknown_not_zero', False, 'year-over-year point change'),
    'gm': (FILED, 'unknown_not_zero', False, 'gross profit, else revenue − cost of revenue'),
    'dnm': (FILED, 'unknown_not_zero', False, 'year-over-year point change'),
    'nm': (FILED, 'unknown_not_zero', False, ''),
    'revg': (FILED, 'unknown_not_zero', False, 'calendar-quarter frames; a fourth quarter is the year minus three quarters'),
    'reva': (FILED, 'unknown_not_zero', False, 'change in revenue growth'),
    'rel': (PRICE, 'unknown_not_zero', True, 'stock minus SPY over the period'),
    'rel3': (PRICE, 'unknown_not_zero', True, 'monthly panel only'),
    'rel6': (PRICE, 'unknown_not_zero', True, ''),
    'ret': (PRICE, 'unknown_not_zero', True, 'price return, dividends not included'),
    'vola': (PRICE, 'unknown_not_zero', True, 'daily log returns in the period, annualised'),
    'volz': (PRICE, 'unknown_not_zero', True, 'share volume against the company\'s own trailing average'),
    'rs': (PRICE, 'unknown_not_zero', True, 'cross-sectional rank among the companies on file in the period'),
    'mom121': (PRICE, 'unknown_not_zero', True, ''),
    'hi52': (PRICE, 'unknown_not_zero', True, ''),
    'f13': ({'cadence': 'quarterly_disclosure', 'observation_kind': 'first_public_observation', 'lag_periods': 1,
             'available': '13F reports, due 45 days after the quarter'},
            'covered_periods_only', False, 'only quarters most managers on file have reported; other quarters are unknown'),
    'gov': ({'cadence': 'event_disclosure', 'observation_kind': 'first_public_observation', 'lag_periods': 1,
             'available': 'officials\' reports, up to 45 days after the trade (dated by trade date in the chart)'},
            'covered_periods_only', False, 'zero only for quarters the reports on file fully cover'),
    'pc13': ({'cadence': 'quarterly_disclosure', 'observation_kind': 'first_public_observation', 'lag_periods': 1,
              'available': '13F option positions, due 45 days after the quarter'},
             'covered_periods_only', False, 'disclosed long options only'),
    'iv30': ({'cadence': 'provider_snapshot', 'observation_kind': 'provider_snapshot', 'lag_periods': 0,
              'available': 'CBOE delayed quotes collected since the collector started'},
             'unknown_not_zero', True, 'short history'),
    'pcoi': ({'cadence': 'provider_snapshot', 'observation_kind': 'provider_snapshot', 'lag_periods': 0,
              'available': 'CBOE delayed quotes collected since the collector started'},
             'unknown_not_zero', True, 'short history'),
}
QUARTERLY_FORECAST = ['rel', 'rel6', 'vola', 'volz', 'rs', 'mom121', 'hi52', 'dom', 'om', 'dgm', 'gm', 'dnm', 'nm', 'revg', 'reva']
MONTHLY_FORECAST = ['rel', 'rel3', 'rel6', 'volz', 'rs', 'mom121', 'hi52']


def entry(key, label=None, unit=None, group=None, centred=None):
    """The registry contract for one axis key (label, unit, group, centred come from rotation.VARS)."""
    block, missing, monthly, notes = AXES[key]
    status = 'experimental' if key in QUARTERLY_FORECAST or key in MONTHLY_FORECAST else 'descriptive_only'
    return {'key': key, 'label': label, 'unit': unit, 'group': group, 'centred': centred, **block,
            'missing_policy': missing, 'monthly': monthly, 'transform_choices': SCALES, 'smoothing_choices': SMOOTHING,
            'forecast': {'quarterly': key in QUARTERLY_FORECAST, 'monthly': key in MONTHLY_FORECAST},
            'predictability_status': status, 'definition_version': f'{key}_v1', 'notes': notes}


def registry(vars_meta=None):
    """{'version', 'axes': [...]} with labels from rotation.VARS-style tuples (key, label, unit, centred, group)."""
    meta = {v[0]: v for v in vars_meta or ()}
    axes = []
    for key in AXES:
        v = meta.get(key)
        axes.append(entry(key, v[1], v[2], v[4], v[3]) if v else entry(key))
    return {'version': REGISTRY_VERSION, 'scales': SCALES, 'smoothing': SMOOTHING, 'fill': FILL, 'status_values': list(STATUS),
            'axes': axes,
            'note': ('Display transforms and smoothing are versioned transformations of observed values; they never create new '
                     'observations. Filed variables are public one period later; a missing value is unknown, never zero.')}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def axis_spec(axes, frequency, scale='raw', smoothing='none', fill=None, benchmark='SPY', sector='site_sector_v1',
              formula='rotation_v1'):
    """The semantic description of a chart configuration: ordered axis keys (x, y, z or '__time'), each with what it
    means, plus the frequency ('q' / 'm' / 'w'), transform, smoothing, benchmark, sector definition and fill."""
    if scale not in SCALES or smoothing not in SMOOTHING or (fill is not None and fill not in FILL):
        raise ValueError('unknown transform, smoothing or fill')
    out = []
    for k in axes:
        if k == '__time':
            out.append({'key': '__time'})
            continue
        e = entry(k)
        out.append({'key': k, 'definition_version': e['definition_version'], 'cadence': e['cadence'],
                    'observation_kind': e['observation_kind'], 'lag_periods': e['lag_periods']})
    return {'axes': out, 'frequency': frequency, 'transform': scale, 'smoothing': smoothing,
            'fill': fill if frequency == 'm' else None, 'benchmark': benchmark, 'sector_definition': sector,
            'calendar': {'q': 'calendar_quarter', 'm': 'calendar_month', 'w': 'friday_week'}[frequency],
            'formula_version': formula, 'registry_version': REGISTRY_VERSION}


def semantic_axis_spec_id(spec):
    return hashlib.sha256(canonical(spec).encode('utf-8')).hexdigest()


def prediction_artifact_id(semantic_id, entity, target, origin, horizon, model_version, dataset_version, code_sha,
                           cutoff, calibration_version=None):
    return hashlib.sha256(canonical({'semantic_axis_spec_id': semantic_id, 'entity': entity, 'target': target,
                                     'origin': origin, 'horizon': horizon, 'model_version': model_version,
                                     'dataset_version': dataset_version, 'code_sha': code_sha, 'cutoff': cutoff,
                                     'calibration_version': calibration_version}).encode('utf-8')).hexdigest()
