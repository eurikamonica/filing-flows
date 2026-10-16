# 06 — Executable work packages and release gates

Created by ChatGPT (OpenAI). Tasks are planned, not completed. Effort labels describe relative engineering scope, not promised calendar dates.

## Implementation queue

| Ticket | Scope and output | Acceptance | Depends on | Effort |
| --- | --- | --- | --- | --- |
| CORE-01 | New observation/evidence contracts and fictional fixtures | Units, timing, missingness and provenance validated | none | Small |
| CORE-02 | Read-only adapter for one selected existing export | Unsupported fields reported; original hashes unchanged | CORE-01 | Medium |
| EVID-01 | New evidence drawer + six-metric change map | Every value opens source and formula; accessible table | CORE-01/02 | Medium |
| CASH-01 | CCC and cash-flow bridge pure calculations | Proxy denominators labeled; residual and missing endpoints tested | CORE-01 | Medium |
| CASH-02 | Working-capital page | Chart/table agree; period changes do not mix scopes | CASH-01, EVID-01 | Medium |
| FSA-01 | Versioned classification overlay | Unclassified totals and equity residual visible; reset works | CORE-01 | Medium |
| FSA-02 | RNOA decomposition UI | Product identity holds; nonpositive NOA handled | FSA-01 | Medium |
| VAL-01 | Forward FCFF DCF | Perpetuity fixture and equity bridge agree; invalid spread rejected | CORE-01 | Medium |
| VAL-02 | Sensitivity and reverse solver | Synthetic recovery; no-solution and multiple-bracket states | VAL-01 | Medium |
| VAL-03 | Evidence-linked valuation page | Assumptions/export reproducible; no implied unique forecast | VAL-02, EVID-01 | Medium |
| MAC-01 | Collector for a reviewed small series list | Terms, units, vintage metadata and stale state retained | CORE-01 | Medium |
| MAC-02 | As-of timeline and revision comparison | Future revisions excluded; timestamp precision visible | MAC-01 | Medium |
| RES-01 | Market/event dataset audit | Calendar, adjusted returns, coverage and rights documented | CORE-01 | Large |
| RES-02 | Event-study batch implementation | Zero-AR and injected-residual fixtures; leakage tests | RES-01 | Medium |
| RES-03 | Reproducible results viewer/export | Exclusions, specification and hashes included; valid inference only | RES-02 | Medium |
| DEP-01 | Separate static publication package | Allowlist only; browser acceptance; no production changes | accepted module | Small |
| DEP-02 | Separate repository deployment | Research URL verified; rollback exercised | DEP-01 | Small |
| DEP-03 | Scheduled snapshot refresh | Partial failure preserves last valid manifest | collector + DEP-02 | Medium |
| AI-01 | Base-vs-adapter held-out comparison | Numerical claims, evidence, abstention and latency measured | independent evaluation set | Medium |
| AI-02 | Optional narrative exports | No arithmetic replacement; reviewed provenance and model version | AI-01, CORE-01 | Medium |

## First concrete implementation batch

Implement CORE-01, then EVID-01 with a fictional fixture, then CORE-02 for one real exported company. This order makes the interface and tests concrete before broad ingestion. Limit the first real dataset to two annual periods and six reviewed metrics. Do not begin macro collection, a public backend and DCF simultaneously.

After that batch passes, build VAL-01/02 alongside a separately scoped CASH-01/02 sequence if resources permit. Do not mix modules into a single commit or broad framework rewrite.

## Definition of done for each module

- New English code/docs attributed to ChatGPT (OpenAI).
- README identifies observed, derived and assumed data, start instructions and known limits.
- Deterministic calculations have independent numeric fixtures and meaningful edge-case tests.
- Desktop and narrow-screen browser checks performed; all interactive controls keyboard-accessible; reduced-motion behavior respected.
- Chart values match the table/export, including losses and missing values.
- Data/version IDs and exact source references retained.
- Comparison with parent commit shows additions only within approved new paths; no shared production edits.
- No API keys, local model files or private inputs in published artifacts.
- Browser/export limitations are recorded honestly; a syntax pass is not visual verification.

## Model evaluation before integration

The reported 20-step local QLoRA run establishes a training smoke test only. Assemble a held-out set separated by company and document, including negative earnings, YTD versus quarter, unit scaling, missing evidence, reserve utilization versus reversal and unsupported requests. Compare base model, adapter and deterministic template baseline on the same inputs.

Measure numeric consistency, source attribution correctness, unsupported-claim rate, correct abstention, latency and peak GPU memory. Arithmetic remains in code. Use a predeclared acceptance rule, not training loss alone. Save model/adapter revision and evaluation dataset hashes. Do not train on unreviewed generated text or assume a provider permits distillation without checking its current terms.

## Copyable implementation brief for local Codex

> Implement CORE-01 and a fixture-only EVID-01 according to fsa-beta/planning. First inspect the current workspace instructions and git status. Preserve all uncommitted local QLoRA work. Work on a new branch or clean worktree; add files only under new research-core and evidence-lab directories. Do not modify production, existing beta pages, workflows or deployment configuration. Use English UI/docs with Created by ChatGPT (OpenAI). Build source/period/unit validation, evidence-linked six-metric comparison, fictional fixtures, accessible table fallback and meaningful tests. Run available checks and explicitly record unperformed browser validation. Show the complete diff and updated instructions. Do not publish a site, send posts or run model training as part of this task.

## Decision points that remain open

Choose the first real company/export format after inspecting available data; identify the macro series and source licenses; select historical price coverage before an academic backtest; measure actual hosting needs before choosing a live backend. These decisions should be resolved with evidence at the relevant ticket, not guessed across the entire roadmap now.
