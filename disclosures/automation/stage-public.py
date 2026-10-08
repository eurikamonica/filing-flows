"""Copy the Disclosure Hub's static site into the Filing Flows Pages build.

    python disclosures/automation/stage-public.py --out _site/disclosures

Collector-only files (cache/, discovery-state.json, npx-queue-state.json) stay in the repository
for incremental collection but are left out of the public site, exactly as the stand-alone
update-and-deploy workflow does.
"""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='_site/disclosures')
    args = ap.parse_args()
    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(DOCS, out, ignore=shutil.ignore_patterns('cache', 'discovery-state.json', 'npx-queue-state.json'))
    n = sum(1 for p in out.rglob('*') if p.is_file())
    print(f'disclosure hub staged to {out} ({n} files)')


if __name__ == '__main__':
    main()
