# DATASET CARD

Created by ChatGPT (OpenAI).

Version: basic-finance-v3. Train/dev/sealed rows: 3600/160/160.

Sixty newly downloaded owner-website company JSONs are stratified by latest 10-K/10-Q/8-K form, with company/document separation. Old train/dev/sealed and legacy downloaded companies are excluded. Website numbers/headings are literal source labels, not independently verified SEC facts. Chart tasks use serialized values; no vision/OCR or complete-footnote competence is established.

Synthetic tasks are explicit independent hypothetical fixtures, checked with Decimal and Fraction for arithmetic. No human review, teacher-generated answers or textbook permissions are claimed. Basic ratios, cash flow, accruals, reserves, negative amounts, units and period alignment are included. S1 is a local evidence alias mapped to URL/hash/location, never a fabricated SEC accession. Output types are explicitly declared.

Exact prompt, company and document overlap across splits is zero. Financial formula semantics are shared; templates are rendered differently by split. Full dev has up to eight rows per task; the frozen GPU protocol has two per task from different entities. The sealed test was generated and checked by the dataset builder, but is not loaded by training/evaluation or used for selection. Rule checks are not semantic SEC evidence audits. All hashes/counts/labels are recorded in manifest.json.
