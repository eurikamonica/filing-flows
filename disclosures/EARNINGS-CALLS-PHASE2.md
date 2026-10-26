# Earnings Call Intelligence — Phase 2 (stacked on PR #74)

This is an additive feature branch. Phase 2 depends on Phase 1's
\`disclosures/app/earnings_calls.py\`, so **merge Phase 1 first**, then
retarget or merge this stacked PR. Neither PR has deployed data merely by
existing in GitHub.

## Official IR discovery matrix

| Symbol | Landing page | Discovery stage | Verified transcript parser |
|---|---|---|---|
| MSFT | Microsoft IR FY2026 Q4 event and rolling FY event pages | Existing HTML verification | Yes, HTML and named turns |
| META | investor.atmeta.com/investor-events/ | Bounded issuer link discovery | No, PDF is *candidate only* |
| GOOGL | alphabet2025ir.q4web.com/investor/earnings/ | Bounded issuer link discovery | Only if visible full HTML speakers |
| NVDA | investor.nvidia.com events and presentations | Bounded issuer link discovery | Only if verified issuer HTML |
| AAPL | investor.apple.com/investor-relations/ | Bounded issuer link discovery | Only if verified issuer HTML |
| AMZN | ir.aboutamazon.com/events/ | Bounded issuer link discovery | Only if verified issuer HTML |
| TSLA | ir.tesla.com/ | Bounded issuer link discovery | Only if verified issuer HTML |

Configured hostnames are *issuer-specific allowlists*. The discovery crawler
does not automatically follow off-domain CDNs, webcast vendors, shorteners,
search engines, or arbitrary unreviewed links. A linked PDF is never called
a verified transcript without a separate rights-reviewed PDF parser.

Discovery is currently limited to one landing URL per company, up to
eight candidates and two HTML verification attempts per four-hour run.
This is **not yet broad market transcript coverage**. Add each issuer's
rights-reviewed domain and parser in configuration and regression fixtures.

## Extraction

\`disclosures/app/earnings_call_intel.py\` splits a verified issuer HTML
transcript at uppercase named speaker turns; \`management_speakers\` provides
a conservative management allowlist. Q&A topic labels are heuristic and
do **not** prove an analyst made a precise claim. Forward-looking numeric
guidance must contain an explicit range, a metric, and compatible units.
Excluded: historical financial results, standalone round numbers, vague
outlook claims, estimates supplied by an analyst, and ranges with mixed
percentage/currency units.

Outputs per verified event (in public metadata only):

- \`guidance\`: company-stated ranges, explicit forecast horizon, units, source
  speaker and SHA256 evidence fingerprint, **not SEC-reconciled**.
- \`analyst_questions\`: analyst speaker name and *generated topic-based*
  research prompt, **not a verbatim question transcript**.
- \`qa_topic_counts\`: counts only, not sentiment, confidence or changes in
  corporate fundamentals.
- \`quantitative_exercises\`: deterministic midpoint/width problems, the
  exact formula, answers, and explicit input verification status.
- \`guidance_changes\`: arithmetic deltas only when previous statements are
  about **the identical forecast period/metric/unit**; not a comparison
  between Q3 and Q4 as if these were one period.
- \`qa_topic_changes\`: relative *question counts*, never a shift in
  management sentiment.
- \`verified_at\`: first observed verification time, preserved on re-scan.

Raw full transcript text is not copied into public JSON, and programmatic
fingerprints are not claims of fact-level SEC verification.

## Flo alerts and questions

Both the homepage and Disclosures hub load
\`web/flo-earnings-alerts.js\`. The browser checks published
\`main\` index.json approximately every five minutes while visible.
Only a *new, recently verified* issuer transcript ID not seen previously
triggers an accessible toast, mascot special animation and source-aware Flo
message. Initial visit silently baselines prior events; repeated polling
does not alert again. No new SEC 8-K or unverified PDF will trigger a
"verified call" notification. Polls can lag GitHub Actions / Pages and
depend on visitor being on the site: this is not push notification or
an always-on server.

Flo now answers questions explicitly naming calls/transcripts/guidance
using the verified metadata and links back to /disclosures/#calls.
The Earnings Calls tab displays answer-reveal quantitative practice tasks
alongside guidance and analyst themes.

## Test and deployment

\`\`\`bash
PYTHONPATH=disclosures/app python -m unittest discover -s disclosures/tests -p 'test_earnings_calls.py' -v
PYTHONPATH=disclosures/app python -m unittest discover -s disclosures/tests -p 'test_earnings_call_intel.py' -v
node --check disclosures/docs/earnings-calls.js
node --check web/mascot.js
node --check web/flo-earnings-alerts.js
node web/test-flo-earnings-alerts.cjs
\`\`\`

Following review, merge PR #74 first, merge Phase 2, set
\`SEC_USER_AGENT\` with real project contact, dispatch the dedicated
Earnings Calls action, check the generated index and Pages deployment,
and then validate a genuinely verified fresh event + a non-verifiable
PDF candidate in the live browser.

## Future (NOT part of Phase 2)

Issuer-vetted PDF/audio transcript extraction, analyst speaker employment
affiliation, sentence-level SEC 10-K/10-Q reconciliation, model-generated
qualitative Q&A beyond fixed research prompts, scaled universe expansion,
mobile push notifications, and market-news/price anomaly integration
need separate source quality and reliability controls.
