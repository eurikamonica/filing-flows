# DATASET CARD

Created by ChatGPT (OpenAI).

Gate 1 passed with limitations. Thirty previously undownloaded companies, split 18 train / 6 dev / 6 sealed test; old 96 company snapshots excluded. All documents of a company share its split. Exact original excerpt duplicates removed across splits. No paraphrase generation or teacher answers. Template identifiers are split-scoped, but mathematical operations/schemas necessarily overlap; this is not a novel-reasoning benchmark. Source paths/hashes and per-task counts are in data/manifest.json.

Owner-authorized website literal values/headings are observed labels; unsupported-claim/missing-field labels are derived from the supplied context only. Fictional note/table/YTD/reserve cases are explicitly hypothetical, not authentic issuer disclosures. Rule checks are not human review. Full footnote Item/Note cross-reference semantics, factual evidence entailment and original table extraction remain coverage gaps. No textbook corpus was used. Whole paragraphs are retained; examples exceeding the token budget must fail, never truncate gold answers. Test answers are generated during construction but are not scored or inspected for candidate selection. Sealing is procedural, not cryptographic access control.

The CPU retrieval baseline operates on provided evidence, preserves source IDs and abstains outside its literal extraction scope. It is not equivalent to a full production RAG retriever. New filings remain evidence inputs rather than memorization targets.

## Frozen counts

| Split | Rows | Companies | SHA256 |
| --- | --- | --- | --- |
| train | 628 | 18 | 2b6d8f537bf88160e44453e3f170a7c0e7d35460b7e0dbfdfd17cca895b01bc2 |
| dev | 218 | 6 | 23a2d3c5c74bb9984492a217b811bf31c08273643219d8ee6e74a57070a760e0 |
| sealed_test | 237 | 6 | 17f8c758f455d292c7b45d07c042263c6628207546538ba27aa29cca09da33ef |

512-token pilot retains 623 train rows, excludes 5 complete oversized excerpt-heading samples without truncation, and uses 30 fixed new development plus 18 historical validation regression questions. All 218 new dev rows remain available; their larger denominator must not be confused with this 48-question pilot. The excluded passages are retained in the source corpus; 1024-context coverage is deferred rather than claiming full-note support.

Coverage limits: the fresh selected website documents include 10-K and 10-Q but no 8-K. Item/Note tables, amended periods and reserve interpretation in this pilot are hypothetical fixtures rather than issuer originals. Generator structure is shared even though company/document membership and split-scoped template identifiers are disjoint; template IDs alone do not establish generator-family isolation. Full original-footnote and unseen-template acceptance remains unmet. Gate 1 completion refers to this bounded, explicitly limited data pilot, not satisfaction of all rich-corpus goals. No data were changed in response to baseline answers.

Provenance erratum: this frozen version uses source_kind=hypothetical_fixture as a fallback for derived website missing-field/abstention rows. Their label_kind=derived, source_url, source_sha256 and supplied evidence correctly identify their website origin; label_kind is authoritative. This metadata-only generator bug was corrected for future runs without changing any frozen bytes or model inputs/answers in the current run. Document IDs identify website snapshot/period offsets, not SEC accession/page locations.

CPU literal retrieval baseline: 42/218 correct overall, with unsupported task types explicitly abstained. This is 42 literal-extraction answers out of 218 development questions, not a neural or full-document retrieval score.

## Prospective corrected v2 (not used in this training)

Explicit output contracts and provenance metadata corrected. Evidence rendering families are split-separated; common semantic operations remain shared. Added one previously unused 8-K company per split. Counts: {"train": 632, "dev": 222, "sealed_test": 241}. Exact membership/hashes: data-v2/manifest.json. V2 test has not been scored. No v2 model exists. See DATA_QUALITY_REVIEW.md. Full real-footnote/table and human-reviewed data goals remain unmet.
