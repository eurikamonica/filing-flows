"""The leveraged-buyout figures for the takeover pages (c/<slug>/takeover/, scripts/seo_topics.py), from the very model
the interactive view and the hub's Buyouts board run (disclosures/docs/lbo-model.js): one Node process works out every
company, so the static page prints the numbers the interactive view draws — the entry, the debt, five years under the
buyer, the exit, the IRR at several premiums and the most a buyer could pay for 20%.

Without Node or the model file nothing is computed ({}): the pages then keep the board's one-line summary.
"""
import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, 'disclosures', 'docs', 'lbo-model.js')
PREMIUMS = (0.10, 0.20, 0.30, 0.40, 0.50)

JS = r"""
let buf = '';
process.stdin.on('data', (d) => { buf += d; });
process.stdin.on('end', () => {
  const job = JSON.parse(buf), M = require(job.model), out = {};
  for (const [k, pair] of Object.entries(job.jobs)) {
    const inp = pair[0], rates = pair[1] || {};
    try {
      const run = M.run(inp, {}, rates);
      if (!run.ok) { out[k] = { ok: false, why: run.why }; continue; }
      const sens = job.premiums.map((p) => { const r = M.run(inp, { premium: p }, rates); return [p, r.ok ? r.price : null, r.ok ? r.irr : null]; });
      out[k] = { ok: true, run, max: M.maxPrice(inp, {}, rates), sens };
    } catch (err) { out[k] = { ok: false, why: 'model error' }; }
  }
  process.stdout.write(JSON.stringify({ defaults: M.DEFAULTS, results: out }));
});
"""


def model_path(site=None):
    """the repository's model, else the copy the build stages on the site (/disclosures/lbo-model.js)"""
    for p in (MODEL, os.path.join(site or '', 'disclosures', 'lbo-model.js') if site else None):
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return None


def model_all(jobs, site=None, timeout=300):
    """({key: result}, the model's default assumptions) for {key: (inputs, rates)}; ({}, None) when it cannot run.
    A result is {'ok': False, 'why': …} or {'ok': True, 'run': …, 'max': …, 'sens': [[premium, price, irr], …]}."""
    if not jobs:
        return {}, None
    node, path = shutil.which('node'), model_path(site)
    if not node or not path:
        print('  LBO model: not run (' + ('no Node' if not node else 'lbo-model.js not found') + '); takeover pages keep the summary')
        return {}, None
    try:
        p = subprocess.run([node, '-e', JS], input=json.dumps({'model': path, 'premiums': list(PREMIUMS),
                                                               'jobs': {str(k): v for k, v in jobs.items()}}),
                           capture_output=True, text=True, timeout=timeout, check=True)
        d = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        print(f'  LBO model: not run ({type(err).__name__}: {str(err)[:200]})')
        return {}, None
    back = {str(k): k for k in jobs}
    return {back[k]: v for k, v in (d.get('results') or {}).items() if k in back}, d.get('defaults')
