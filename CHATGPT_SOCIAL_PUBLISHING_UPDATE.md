# Code Review and X Publishing Update Recommendations

> Author: ChatGPT (OpenAI)
> Updated: October 15, 2026
> Status: Documentation only; proposed changes are not implemented.
> Scope: Add this document only. No posts, emails, provider calls, workflow runs, production configuration changes or Beta changes are performed.
> Review snapshot: [de69ca49](https://github.com/eurikamonica/filing-flows/commit/de69ca490afb7edf5fbf17c61e17f79b4f40bc7a).
> Method: Source inspection, not an executed end-to-end publishing audit. Live account permissions, provider pricing, current API contracts and delivery history were not verified.

## 1. Existing implementation

| File | Responsibility | Observed behavior |
| --- | --- | --- |
| `config/x.json` | Automatic earnings posting policy | Enabled; Buffer mode; all-company scope; revenue threshold 1 billion; maximum four candidates per run; maximum filing age three days; preliminary filings allowed. |
| `config/tweet-guide.md` | English model writing instructions | Cashtag/quarter first, at most three headline numbers, supplied hashtags, preliminary label, factual wording and no advice. |
| `pipeline/tweet.py` | Evidence assembly and model draft | Reads filing text/MD&A, headline figures and business description; tries configured providers/models; validates selected formatting constraints; falls back to rule-based text. |
| `pipeline/social.py` | Selection, charts, composition and local state | Filters candidates, renders charts and supports email, direct X and Buffer paths. Automatic Buffer path currently emits `posts: [post]`, a single model/rule-based caption. |
| `pipeline/buffer.py` | Buffer submission | Selects a channel and creates a post/thread or draft. Logs returned ID/status/due time; does not persist a durable per-item receipt in this inspected path. |
| `scripts/publish-media.sh` | Media persistence and submission handoff | Pushes images to the media branch, then calls `pipeline.buffer` with public raw-file URLs. |
| `.github/workflows/scan.yml` | Build/deploy orchestration | Buffer job follows successful Pages deployment and invokes the media publishing helper. |

The persistent media branch already addresses images disappearing after a later site build. Extend it with immutable image references and integrity checks rather than rebuilding it.

Other owner-request, engagement and trend entry points may use different composition paths. This review does not claim exhaustive coverage of every social workflow.

## 2. Findings and priorities

### P0 — Delivery state is recorded before remote acceptance

In `social.main` Buffer mode, each candidate is added to `st["posted"]` while creating the local pending manifest. Remote submission happens later. `posted_already` checks company and nearby period end, without checking a successful delivery status.

**Consequence:** if deployment, media publication or Buffer submission fails, the ordinary candidate scan can suppress the item as already processed. This is a source-derived failure scenario, not a claim that a particular post was lost.

The direct-X error path also records an error under `posted`. This prevents blind retries but conflates failure with success. Email delivery uses the same broad posted namespace, so channel migration needs explicit semantics.

**Recommendation:** introduce a durable outbox with:
`prepared → validated → approved/auto_eligible → submitting → queued → published`.
Also support `failed`, `held` and `unknown`. Treat `queued` as provider acceptance, not proof of publication. Publication status requires a supported provider receipt/status check.

Use a stable logical key including channel, CIK, reporting period, source version and post kind. Store text hash, chart hash, attempt ID, remote ID and timestamps separately. A wording regeneration must not itself authorize a duplicate.

**Acceptance:** failed pre-submission items remain recoverable; confirmed queued items are not recreated; a timeout after possible provider acceptance becomes `unknown` until reconciled. Do not promise exactly-once delivery without provider support.

### P0 — Numeric truth is prompt guidance, not enforced validation

`tweet.clean` checks cashtag placement, supplied hashtags, advice/hype words and estimated length. It does not compare each generated amount, percentage, period or claim with source data.

**Recommendation:** build a canonical fact bundle before writing. Include raw value, display value, unit, period, calculation, source accession and evidence IDs. Have the model select facts and draft prose; validate every numeric claim against those facts with explicit rounding tolerance. Validate the deterministic fallback too.

Require preliminary status where applicable. Distinguish percent change from percentage-point movement, annual from quarterly/YTD, reported FCF from calculated FCF, and net earnings from operating income. Unsupported causal statements should be removed or held.

**Acceptance:** fixtures deliberately changing a sign, scale, period, growth basis or FCF definition fail before any queue call.

### P0 — Financial warnings are not held equally across channels

`candidates` excludes warning-marked entries only when mode is `api`. The inspected automatic Buffer manifest does not set `draft`, although the Buffer client supports draft creation.

**Recommendation:** classify check severity independently of delivery channel. Material reconciliation, period or unit errors should hold the post; recoverable ambiguity should produce a review draft with visible reasons. Draft mode is not a successful public release.

**Acceptance:** the same fixture cannot bypass financial validation merely by switching from direct X to Buffer.

### P0 — Retry and concurrency handling needs durable receipts

The Buffer CLI logs successful remote IDs, then exits nonzero if any item fails. It does not save individual receipts for a partial batch in the reviewed code. Replaying a manifest can therefore recreate items already accepted.

The media script handles Git push conflicts, but a Git rebase does not deduplicate external submissions.

**Recommendation:** persist a receipt immediately after each accepted submission; coordinate publishers sharing a channel/outbox; retry only known failed items with bounded backoff. Handle connection timeouts and malformed remote responses explicitly. Verify channel service even when an explicit ID is supplied; display the destination account in previews.

**Acceptance:** partial success followed by restart preserves accepted IDs; two workers cannot submit the same leased outbox item; uncertain submissions are not automatically resent.

### P1 — Content instructions conflict and the automatic path is not a thread

The guide says cashtag first and no emoji; `compose_one(thread=True)` asks for an attention word before the cashtag and optionally an arrow. The automatic Buffer caller does not pass `thread=True` and emits one post, irrespective of expectations raised by `owner_thread` in configuration.

**Recommendation:** define one validated post specification per kind: earnings single, earnings thread, holders, trend, correction. Give each an explicit length budget, hook policy, evidence requirements and reply structure. Document which callers support each setting.

The guide's sample also uses a segment-growth figure that is not necessarily present in the supplied headline facts. Either add supported segment metrics to the fact bundle or remove that example.

**Acceptance:** selecting thread mode actually creates multiple parts; the chosen hook does not get duplicated by cashtag repair; schema, template and guide use consistent rules.

### P1 — Holdings summaries need stricter coverage semantics

`holders_lines` groups `NOT DISCLOSED` with decreases/exits and describes the count as managers that cut or closed. It also uses buyer/seller language despite noting these are quarter-end positions.

**Recommendation:** separate confirmed comparable share decreases, verified exits and unresolved/noncomparable records. Use “reported position increased/decreased” and state the reporting period. Do not infer transaction timing or motivation from 13F changes.

**Acceptance:** an unavailable or incomplete report cannot become a confirmed sale or exit in a generated post.

### P1 — Provider selection is not a cost policy

`providers/chat` may try multiple configured providers and several Gemini models. A shared `TWEET_MODEL` override is applied across providers. Automatic model discovery does not establish free eligibility, and fallback can invoke a paid configured provider.

**Recommendation:** explicit provider/model allowlists, per-provider model settings, request/time/token budgets and a deliberate paid-fallback setting defaulting off. Cache by evidence hash and prompt/model version. Store generation provenance without logging credentials. Date and verify provider claims before updating operational instructions.

**Acceptance:** free-only mode cannot call an unapproved provider; a provider outage produces a validated rule-based draft within a bounded time.

### P1 — Preview and length checks should match actual output

The ordinary social dry-run returns before the model path and prints rule-based composition. Buffer dry-run still requires a key and performs channel lookup. Neither is a full offline preview of the eventual model-assisted submission.

`xlen` is a local approximation; complex Unicode and emoji sequences deserve compatibility fixtures against the chosen platform length rules.

**Recommendation:** separate offline preview, online generation preview and delivery. Offline preview must not contact SMTP, Buffer, X or models or mutate delivery state. Show final text, images, links, destination, validation results and length for every part.

## 3. Recommended English editorial format

Use news-style hooks only when justified by event timing:
**NEW FILING**, **EARNINGS ALERT**, **RESULTS ARE OUT**, or **BREAKING** for genuinely recent events. Recheck freshness at scheduled publication time, not just draft creation. Avoid “strange,” “weird,” fabricated urgency and investment recommendations.

A proposed earnings thread:

1. **Hook:** cashtag, fiscal period, one supported contrast and one or two key figures, plus the chart.
2. **Explanation:** what drove the result, supported by an excerpt; include reserve/accrual observations only when verified.
3. **Business description:** products/services, customers and revenue model, kept distinct from investment commentary.
4. **Source/CTA:** stable company-period link, concise source/rounding/non-advice note, and an optional specific discussion question.

Each part must pass the configured length check. For a single post, prioritize the verified result and source link; keep the business description on the linked page. Do not simply truncate away the preliminary qualifier or source attribution.

Example template, not a publication-ready post:

> EARNINGS ALERT · $TICK {period}: revenue {revenue} ({growth} Y/Y), while operating margin {direction} to {margin}. What explains the gap? {link} {relevant_tag}

Render placeholders from approved facts. Use one or two relevant hashtags when space permits rather than automatically filling the budget with broad tags. A question should invite analysis of a supported observation, not imply misconduct.

### Market reaction is optional and separately sourced

A new market-context feature should retain quote provider, observation time, session, reference close and calculation. Distinguish regular-session, premarket and after-hours moves. If fresh, usable price data is unavailable, omit the claim. Do not infer that an earnings release caused a move merely because both occurred on the same day.

No quote collection or market-reaction feature was verified as part of this review.

## 4. Topic selection and feedback

Proposed topic score, initially a product hypothesis:

`score = 0.30 freshness + 0.25 financial_materiality + 0.20 evidence_quality + 0.15 audience_relevance + 0.10 chart_readability`

Normalize components to 0–1 and document definitions. Apply hard gates before scoring: unresolved material data errors, unsupported claims or missing required evidence cannot be offset by popularity. Deduplicate by filing/event and apply per-company cooldowns.

Track approved drafts, submissions, queued posts, published posts and failed/unknown attempts separately. Where authorized analytics access exists, record link clicks, impressions, substantive replies and follows. Compute CTR only when both clicks and impressions are measured; missing analytics are not zero.

Use tagged website links and comparable publication windows. Compare styles across similar company/event groups and retain sample sizes. Do not claim a hook causes engagement improvement from a few uncontrolled posts.

## 5. Proposed code boundaries

| Component | Proposed responsibility |
| --- | --- |
| Existing composition functions | Produce deterministic factual drafts and reusable thread parts |
| New `social_facts.py` | Canonical facts, evidence mapping and numerical validation |
| New `social_outbox.py` | Durable states, item leases, receipts, replay and correction policy |
| Existing `tweet.py` | Optional wording within validated facts and provider budgets |
| Existing `buffer.py` / direct X client | Transport adapters returning structured outcomes |
| New preview report | Render exact candidate text/media/destination and validation reasons |

These filenames are proposals, not files added by this change. Start with isolated fixtures and an opt-in path; preserve the existing production behavior until the replacement passes review.

Local Qwen can later supply English draft wording via an explicit adapter. It does not replace evidence validation or transport state. A local model on a laptop is unavailable to a cloud scan unless a separate service or precomputed artifact handoff is built.

## 6. Minimum acceptance suite

- Wrong amount, sign, currency scale, percentage basis and period are blocked.
- Preliminary release wording survives generation and shortening.
- Material-warning records are held in both Buffer and direct-X modes.
- Remote acceptance followed by a local interruption becomes recoverable without blind resubmission.
- Partial thread/batch outcomes retain individual remote IDs.
- A revised filing can create an explicit correction workflow without silently duplicating the original.
- Missing holdings reports do not become exits; missing prices do not become zero returns.
- Images remain available after later deployments and match the text's source version.
- Offline preview invokes no external service and changes no publishing state.
- An unavailable model falls back to a validated deterministic draft.
- A selected Buffer channel is confirmed as the intended X destination.
- Held/queued/published counters reconcile with stored receipts.

Use mocked transports and temporary state for these tests. No live tweet is needed to validate the failure cases.

## 7. Suggested delivery sequence

1. Durable outbox and receipts, plus consistent financial warning gates.
2. Canonical fact bundle, numeric/evidence validation and accurate preview.
3. Unified English templates, explicit thread mode and correction policy.
4. Optional fresh-price context, topic ranking and analytics.
5. Optional local-model drafting after baseline quality evaluation.

**Recommended first implementation:** fix the prepared-versus-queued distinction and add recovery tests, then make financial validation mandatory for both generated and fallback text.

Related roadmap: [UPDATE.md](UPDATE.md). This review makes no claim that proposed improvements are already deployed.
