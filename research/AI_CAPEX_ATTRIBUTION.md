# AI CapEx → Vendor Revenue Attribution (research prototype)

This is a **hypothetical** bottom-up **terminal spending** and **recognition-timing** calculator. It does not scrape SEC, infer hidden orders, train an 8B model or certify supplier sales. In particular, all numbers in `example.json` are **illustrative assumptions**, not Google's guidance or a Morgan Stanley forecast.

Run with Python 3.11+ (stdlib only):

```bash
python research/ai_capex_attribution.py research/ai_capex_example.json --out attribution.json
python -m unittest discover -s research -p "test_ai_capex_attribution.py"
```

**Accounting discipline**

1. Allocate the terminal buyer budget once across mutually exclusive spending categories (category weights sum to 100%).
2. Allocate a category across named suppliers plus an explicitly unallocated remainder (supplier fractions at most 100%).
3. Compute vendor-level **attributed end-customer spend**, not verified GAAP revenue.
4. Apply a user-declared quarterly recognition lag distribution, including negative lags when vendors recognize before end-buyer CapEx.
5. Never add a chipmaker's HBM content twice: the AI-compute category includes integrated HBM and the standalone-memory category excludes it. A true multi-tier BOM ledger is a *separate* next phase.
6. Generate evidence-labelled Gamma/Chains edges with `value_type=terminal_spend_attribution`, `evidence_level=illustrative_assumption`.
7. Report unspecified or unallocated spend instead of forcing every dollar to a selected vendor.

**Illustrative base case:** a hypothetical $10B spend budget yields *terminal allocated spend*: NVDA $2.775B, AVGO $0.675B, MU $0.525B, ANET $0.450B (and others). These are **NOT forecasts of their reported revenues**. Revenue recognition is separately distributed 20% to the preceding quarter, 50% to the CapEx quarter, 30% to the following quarter, solely as an example.

**Research roadmap:** SEC/XBRL actual and projected CapEx by buyer → facility construction / power capacity / BOM counts and ASP → as-of-dated procurement evidence → entity resolution and non-overlapping upstream BOM → customer/supplier lag calibration → reconciliation against actual *supplier segment revenue*, with explicit residual for customers not modeled → walk-forward error by vintage and scenario. Only after validation should model-estimated edges appear alongside SEC-identified relationships.

**Model usage:** existing Qwen3-0.6B LoRA in the `model` branch is trained for writing valid X posts, not for financial attribution. A separate Qwen3-4B FSA experiment is not a validated 8B attribution model. Use LLMs only for extraction with filing citations; the numerical allocator must be deterministic and auditable.
