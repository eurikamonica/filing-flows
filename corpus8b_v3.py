"""Auditable basic-finance and owner-website corpus. Created by ChatGPT (OpenAI)."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import urllib.request

from lab import LAB, BETA, AUTHOR, read, write, sha, doc

REAL_TASKS = ['field_extraction', 'filing_route', 'missing_field', 'evidence_abstention', 'note_heading', 'chart_data']
SYNTH_TASKS = ['free_cash_flow', 'total_accruals', 'accrual_ratio', 'reserve_calculation', 'quarter_from_ytd',
               'unit_conversion', 'percent_change', 'operating_margin', 'balance_equation', 'cash_conversion',
               'negative_number', 'period_alignment', 'reserve_movement', 'basic_instruction']


def compact(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def numeric(expression, exact):
    """Two independent numeric representations must agree before generating a label."""
    answer = Decimal(expression)
    if abs(float(answer) - float(exact)) > max(1e-10, abs(float(exact)) * 1e-12):
        raise ValueError('Decimal/Fraction gold check failed')
    return int(answer) if answer == answer.to_integral_value() else float(answer)


def make_row(split, company, document, task, evidence, request, expected, provenance, index, kind):
    types = {key: ('number or null' if value is None or type(value) in (int, float)
                    else 'boolean' if isinstance(value, bool) else 'string') for key, value in expected.items()}
    contract = ('Return only one JSON object with these fields and types: ' + compact(types) +
                '. Numbers must be JSON numbers, never quoted strings or arithmetic expressions. '
                'Use null for unavailable values. Copy source_id S1. No Markdown. ')
    # Different surface representations across splits; shared task semantics are disclosed.
    rendered = compact(evidence) if split == 'train' else '\n'.join(f'{key}: {compact(value)}' for key, value in evidence.items())
    if split == 'sealed_test':
        rendered = '\n'.join(f'- {key} = {compact(value)}' for key, value in evidence.items())
    prompt = contract + '\nEvidence S1:\n' + rendered + '\nRequest: ' + request
    return {'author': AUTHOR, 'id': f'v3-{split}-{index:06d}', 'split': split, 'company_id': company,
            'document_id': document, 'task': task, 'input': prompt, 'output': compact(expected), 'expected': expected,
            'label_kind': kind, 'review': 'machine_checked_not_human_reviewed', 'source_aliases': {'S1': provenance},
            'rendering_family': {'train': 'compact_json', 'dev': 'fact_lines', 'sealed_test': 'bullet_facts'}[split]}


def synthetic(split, task, number):
    seed = int.from_bytes(hashlib.sha256(f'20261016-v3:{split}:{task}:{number}'.encode()).digest()[:8], 'big')
    rng = random.Random(seed)
    a, b, c, d = [rng.randint(1, 750) for _ in range(4)]
    e = {'status': 'Explicitly hypothetical independent example', 'unit': 'USD millions'}
    extra = {}
    if task == 'free_cash_flow':
        e.update(operating_cash_flow=a, capital_expenditure_cash_outflow=b)
        request = 'Compute free cash flow as OCF minus positive capex outflow.'
        value = numeric(str(Decimal(a) - Decimal(b)), Fraction(a) - b)
    elif task == 'total_accruals':
        e.update(net_income=a, operating_cash_flow=b)
        request = 'Compute total accruals as net income minus operating cash flow.'
        value = numeric(str(Decimal(a) - Decimal(b)), Fraction(a) - b)
    elif task == 'accrual_ratio':
        # Include exact simple ratios and harder values; no hidden rounding convention.
        denominator = rng.choice([100, 200, 400, 500, 1000])
        e.update(net_income=a, operating_cash_flow=b, average_total_assets=denominator)
        request = 'Compute annual accrual ratio (net income - OCF) / average total assets as a fraction, not percent.'
        value = numeric(str((Decimal(a) - b) / denominator), Fraction(a - b, denominator))
    elif task == 'reserve_calculation':
        a = c + d + a
        e.update(opening_reserve=a, additions=b, utilization=c, reversal=d, other_movements=0)
        request = 'Compute closing reserve = opening + additions - utilization - reversal. No other movements.'
        value = numeric(str(Decimal(a) + b - c - d), Fraction(a) + b - c - d)
    elif task == 'quarter_from_ytd':
        e.update(current_ytd=a, prior_ytd_original=b + 7, prior_ytd_amended=b, periods_aligned=True)
        request = 'Compute current quarter from current YTD minus amended prior YTD; use the amendment.'
        value = numeric(str(Decimal(a) - b), Fraction(a) - b)
    elif task == 'unit_conversion':
        e.update(amount=a, unit='USD thousands', requested_unit='USD')
        request = 'Convert the amount to USD.'
        value = numeric(str(Decimal(a) * 1000), Fraction(a) * 1000)
    elif task == 'percent_change':
        previous = rng.choice([100, 200, 400, 500])
        e.update(current=a, prior=previous)
        request = 'Compute percent change = (current - prior) / prior * 100. Return a percentage, not a fraction.'
        value = numeric(str((Decimal(a) - previous) / previous * 100), Fraction((a - previous) * 100, previous))
    elif task == 'operating_margin':
        revenue = rng.choice([100, 200, 400, 500, 1000])
        income = a if number % 2 else -a
        e.update(operating_income=income, revenue=revenue)
        request = 'Compute operating margin = operating income / revenue as a fraction, not percent.'
        value = numeric(str(Decimal(income) / revenue), Fraction(income, revenue))
    elif task == 'balance_equation':
        e.update(total_assets=a + b, total_liabilities=b)
        request = 'Compute total equity using assets = liabilities + equity.'
        value = numeric(str(Decimal(a + b) - b), Fraction(a + b) - b)
    elif task == 'cash_conversion':
        income = rng.choice([100, 200, 400, 500])
        e.update(operating_cash_flow=a, net_income=income)
        request = 'Compute cash conversion OCF / net income as a fraction.'
        value = numeric(str(Decimal(a) / income), Fraction(a, income))
    elif task == 'negative_number':
        e.update(table_amount=f'({a:,})', table_convention='Parentheses indicate negative amounts')
        request = 'Read the signed amount as a JSON number.'
        value = -a
    elif task == 'period_alignment':
        e.update(net_income=a, net_income_basis='quarter', operating_cash_flow=b, cash_flow_basis='year-to-date')
        request = 'Can same-period accruals be calculated? Return value null and reason period_mismatch.'
        value, extra = None, {'reason': 'period_mismatch'}
    elif task == 'reserve_movement':
        utilization = number % 2 == 0
        e.update(description='Claims paid using the reserve' if utilization else 'Estimate released through earnings')
        request = 'Classify movement as utilization or reversal; do not confuse cash settlement with earnings release.'
        value, extra = None, {'movement': 'utilization' if utilization else 'reversal'}
    else:
        e.update(instruction_token=rng.choice(['confirmed', 'received', 'ready', 'acknowledged']))
        request = 'Copy instruction_token into status.'
        value, extra = None, {'status': e['instruction_token']}
    expected = {'value': value, **extra, 'source_id': 'S1'}
    if task in ('basic_instruction', 'reserve_movement'):
        expected.pop('value')
    company = f'hypothetical-v3-{split}-{number:05d}'
    provenance = {'kind': 'hypothetical', 'generator': 'corpus8b_v3.py', 'seed': seed,
                  'verification': 'Decimal and Fraction agree for generated arithmetic; rule checked for categorical examples'}
    return make_row(split, company, company + ':' + task, task, e, request, expected, provenance, number, 'hypothetical')


def website_rows(split, cik, path):
    data = read(path)
    output = []
    for collection in ('quarters', 'years'):
        for position, period in enumerate(data.get(collection, [])[:4]):
            form, end = period.get('form'), period.get('end')
            if not form or not end:
                continue
            loc = f'{collection}[{position}]'
            document = str(cik) + ':' + (period.get('doc_url') or form + ':' + end)
            provenance = {'kind': 'owner_website_literal_not_independent_SEC_verification',
                          'url': f'https://filing-flows.com/data/c/{cik}.json', 'sha256': sha(path),
                          'path': str(path), 'location': loc, 'filing_url': period.get('doc_url')}
            base = {'company': data['profile'].get('name'), 'form': form, 'period_end': end,
                    'period_label': period.get('label'), 'site_scope': 'Website summary, not a full filing'}
            headline = {key: value for key, value in period.get('headline', {}).items()
                        if key in ('revenue', 'ni', 'oi', 'ocf') and type(value) in (int, float)}
            for metric, value in headline.items():
                evidence = {**base, 'literal_headline': headline, 'amount_basis': 'Website native numeric value; do not rescale'}
                expected = {'value': value, 'period_end': end, 'source_id': 'S1'}
                output.append(make_row(split, str(cik), document, 'field_extraction', evidence,
                              f'Copy literal_headline.{metric} exactly as a JSON number and its period_end.', expected,
                              {**provenance, 'field': 'headline.' + metric}, len(output), 'observed_website_literal'))
            output.append(make_row(split, str(cik), document, 'filing_route', base, 'Return the stated form and period_end.',
                          {'form': form, 'period_end': end, 'source_id': 'S1'}, provenance, len(output), 'observed_website_literal'))
            evidence = {**base, 'available_fields': headline, 'reserve_closing_provided': False}
            output.append(make_row(split, str(cik), document, 'missing_field', evidence,
                          'Return closing reserve. It is absent: use null, never invent zero.',
                          {'value': None, 'source_id': 'S1'}, provenance, len(output), 'derived_rule'))
            output.append(make_row(split, str(cik), document, 'evidence_abstention', {**base, 'literal_headline': headline},
                          'Do these summary amounts alone establish deliberate earnings manipulation? Return supported false.',
                          {'supported': False, 'source_id': 'S1'}, provenance, len(output), 'derived_rule'))
            for node_idx, node in enumerate(period.get('nodes', [])):
                if type(node.get('v')) in (int, float):
                    evidence = {**base, 'serialized_chart': {'series': node.get('name'), 'current_value': node['v'],
                                                          'prior_year_value': node.get('y')}}
                    output.append(make_row(split, str(cik), document, 'chart_data', evidence,
                                  'Copy serialized_chart.current_value as a JSON number. This is text chart data, not an image.',
                                  {'value': node['v'], 'source_id': 'S1'}, {**provenance, 'node': node_idx}, len(output), 'observed_website_literal'))
                    break
            found = False
            for node_idx, node in enumerate(period.get('nodes', [])):
                for note_idx, note in enumerate(node.get('notes', [])):
                    heading = note.get('heading')
                    if not isinstance(heading, str) or not heading.strip() or len(heading) > 160:
                        continue
                    # Complete headings are retained. The bounded contextual sentence is explicitly partial.
                    text = note.get('text', '')
                    sentences = re.split(r'(?<=[.!?])\s+', text)
                    excerpt = sentences[0] if sentences and len(sentences[0]) <= 500 else ''
                    evidence = {**base, 'provided_note_heading': heading,
                                'partial_context_sentence': excerpt, 'excerpt_scope': 'Heading/partial website excerpt only'}
                    output.append(make_row(split, str(cik), document, 'note_heading', evidence,
                                  'Copy the provided note heading. Do not infer a universal note number.',
                                  {'heading': heading, 'source_id': 'S1'}, {**provenance, 'node': node_idx, 'note': note_idx}, len(output), 'observed_website_literal'))
                    found = True
                    break
                if found:
                    break
    return output


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(compact(row) + '\n' for row in rows), encoding='utf-8')


def build():
    root = LAB / 'runs' / ('corpus-v3-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    root.mkdir(exist_ok=False)
    source_dir = root / 'sources'
    source_dir.mkdir()
    previous_sources = {}
    if (LAB / 'current-corpus-v3.json').exists():
        previous_root = Path(read(LAB / 'current-corpus-v3.json')['root'])
        previous_sources = {r['cik']: r for r in read(previous_root / 'sources/manifest.json')['files']}
    old = read(LAB / 'runs/20261016T171524Z/data-v2/manifest.json')
    excluded = {str(cik) for group in old['splits'].values() for cik in group['companies']}
    excluded |= set(read(BETA / '.runtime/website-data/manifest.json')['files'])
    index = read(BETA / '.runtime/overnight/site-index.json')
    # Split before download/label generation. Preserve entire companies and filings in one split.
    memberships = {split: [] for split in ('train', 'dev', 'sealed_test')}
    for form in ('10-K', '10-Q', '8-K'):
        eligible = sorted((row for row in index['companies'] if row.get('form') == form and str(row['cik']) not in excluded),
                          key=lambda row: hashlib.sha256(('v3-company-' + str(row['cik'])).encode()).hexdigest())[:20]
        if len(eligible) != 20:
            raise RuntimeError('Insufficient independent company strata: ' + form)
        for split, group in zip(memberships, (eligible[:14], eligible[14:17], eligible[17:20])):
            memberships[split].extend(str(row['cik']) for row in group)
    write(root / 'split-membership.json', {'author': AUTHOR, 'companies': memberships,
          'excluded_prior_companies': sorted(excluded), 'stratification': '14 train / 3 dev / 3 sealed per latest 10-K, 10-Q, 8-K stratum'})

    def download(cik):
        url = f'https://filing-flows.com/data/c/{cik}.json'
        cached = previous_sources.get(cik)
        if cached and cached['url'] == url and sha(Path(cached['path'])) == cached['sha256']:
            path = source_dir / (cik + '.json')
            shutil.copy2(cached['path'], path)
            return {**cached, 'path': str(path), 'reused_verified_download': True}
        request = urllib.request.Request(url, headers={'User-Agent': 'FilingFlowsBeta/0.3 (owner-authorized local research)'})
        with urllib.request.urlopen(request, timeout=30) as response:
            blob = response.read(8 * 1024 * 1024 + 1)
        if len(blob) > 8 * 1024 * 1024:
            raise RuntimeError('Company download size budget exceeded: ' + cik)
        obj = json.loads(blob)
        if str(obj['profile']['cik']) != cik:
            raise ValueError('Company identity mismatch')
        path = source_dir / (cik + '.json')
        path.write_bytes(blob)
        return {'cik': cik, 'url': url, 'path': str(path), 'sha256': sha(path), 'bytes': len(blob)}

    with ThreadPoolExecutor(max_workers=4) as executor:
        sources = list(executor.map(download, [c for group in memberships.values() for c in group]))
    write(source_dir / 'manifest.json', {'author': AUTHOR, 'files': sources, 'permission': 'User-owned website; user explicitly authorized download',
          'limits': 'No textbook scraping, model teacher labels, or independent SEC verification'})
    manifests = {}
    for split, companies in memberships.items():
        rows = []
        for cik in companies:
            rows.extend(website_rows(split, cik, source_dir / (cik + '.json')))
        per_task = 180 if split == 'train' else 8
        rows.extend(synthetic(split, task, number) for task in SYNTH_TASKS for number in range(per_task))
        # Balance real tasks without duplicating rows. Train cap keeps literal copying from swamping calculations.
        groups = defaultdict(list)
        for row in rows:
            groups[row['task']].append(row)
        selected = []
        for task, group in sorted(groups.items()):
            group.sort(key=lambda row: hashlib.sha256(row['input'].encode()).hexdigest())
            selected.extend(group[:180] if split == 'train' else group[:8])
        if set(groups) != set(REAL_TASKS + SYNTH_TASKS):
            raise RuntimeError('Missing task coverage in split ' + split)
        for i, row in enumerate(selected):
            row['id'] = f'v3-{split}-{i:06d}'
        random.Random(20261017).shuffle(selected)
        path = root / ('sealed/test.jsonl' if split == 'sealed_test' else split + '.jsonl')
        write_rows(path, selected)
        manifests[split] = {'path': str(path), 'sha256': sha(path), 'rows': len(selected), 'companies': companies,
                            'tasks': dict(Counter(row['task'] for row in selected)),
                            'label_kinds': dict(Counter(row['label_kind'] for row in selected)),
                            'documents': len({row['document_id'] for row in selected}),
                            'forms': dict(Counter(re.search(r'"form":"([^"]+)"', row['input']).group(1)
                                      for row in selected if re.search(r'"form":"([^"]+)"', row['input'])))}
        if split == 'dev':
            # Two rows per task, distinct companies/documents whenever available.
            protocol = []
            for task in sorted(groups):
                candidates = [row for row in selected if row['task'] == task]
                first = candidates[0]
                second = next(row for row in candidates[1:] if row['company_id'] != first['company_id'])
                protocol.extend([first, second])
            write_rows(root / 'dev-protocol.jsonl', protocol)
            write(root / 'dev-protocol-manifest.json', {'rows': len(protocol), 'tasks': dict(Counter(r['task'] for r in protocol)),
                  'real_companies': sorted({r['company_id'] for r in protocol if not r['company_id'].startswith('hypothetical')}),
                  'sha256': sha(root / 'dev-protocol.jsonl'), 'selection': 'Fixed before any GPU generation; two distinct companies per task'})
    # Exact prompt overlap and company/document overlap checks without exposing sealed labels to the trainer.
    all_rows = {s: [json.loads(line) for line in Path(m['path']).read_text().splitlines()] for s, m in manifests.items()}
    checks = {}
    for a, b in [('train', 'dev'), ('train', 'sealed_test'), ('dev', 'sealed_test')]:
        checks[a + ':' + b] = {field: len({r[field] for r in all_rows[a]} & {r[field] for r in all_rows[b]})
                               for field in ('company_id', 'document_id', 'input')}
        if any(checks[a + ':' + b].values()):
            raise RuntimeError('Cross-split leakage')
    manifest = {'author': AUTHOR, 'version': 'basic-finance-v3', 'splits': manifests, 'contamination_checks': checks,
                'sealed_test_evaluated': False, 'prior_v2_sealed_test_untouched': True,
                'template_limit': 'Shared financial task/formula semantics; rendering families and entities differ by split. Not a held-out formula-family claim.',
                'source_download_bytes': sum(s['bytes'] for s in sources), 'source_files': len(sources)}
    write(root / 'manifest.json', manifest)
    shutil.copy2(Path(__file__), root / 'corpus8b_v3.py')
    doc(root, 'DATASET_CARD.md', f"Version: basic-finance-v3. Train/dev/sealed rows: {manifests['train']['rows']}/{manifests['dev']['rows']}/{manifests['sealed_test']['rows']}.\n\n"
        'Sixty newly downloaded owner-website company JSONs are stratified by latest 10-K/10-Q/8-K form, with company/document separation. '
        'Old train/dev/sealed and legacy downloaded companies are excluded. Website numbers/headings are literal source labels, not independently verified SEC facts. '
        'Chart tasks use serialized values; no vision/OCR or complete-footnote competence is established.\n\n'
        'Synthetic tasks are explicit independent hypothetical fixtures, checked with Decimal and Fraction for arithmetic. '
        'No human review, teacher-generated answers or textbook permissions are claimed. Basic ratios, cash flow, accruals, reserves, negative amounts, units and period alignment are included. '
        'S1 is a local evidence alias mapped to URL/hash/location, never a fabricated SEC accession. Output types are explicitly declared.\n\n'
        'Exact prompt, company and document overlap across splits is zero. Financial formula semantics are shared; templates are rendered differently by split. '
        'Full dev has up to eight rows per task; the frozen GPU protocol has two per task from different entities. '
        'The sealed test was generated and checked by the dataset builder, but is not loaded by training/evaluation or used for selection. '
        'Rule checks are not semantic SEC evidence audits. All hashes/counts/labels are recorded in manifest.json.')
    write(LAB / 'current-corpus-v3.json', {'author': AUTHOR, 'root': str(root), 'manifest_sha256': sha(root / 'manifest.json')})
    print(compact({'root': str(root), 'rows': {k: v['rows'] for k, v in manifests.items()}, 'sources': len(sources), 'checks': checks}), flush=True)
    return root


if __name__ == '__main__':
    build()
