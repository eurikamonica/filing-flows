# Earnings Call Intelligence — official IR + SEC (Phase 1)

Scope: this pipeline is additive. It **does not modify** the established 13F, 8-K,
Earnings Season or research branch collectors. It discovers SEC 8-K Item 2.02
earnings-release evidence and validates issuer IR transcript pages.

## Source truth / legal boundaries

- SEC 8-K Item 2.02 is earnings-release **evidence**, **not** a call transcript.
- A transcript is available only after a permitted, HTTPS-only, approved IR page
  has been downloaded and visibly contains a Transcript heading, enough text,
  and at least two named speaker turns. Otherwise no positive availability claim.
- The public JSON publishes **metadata, SHA256 fingerprints, and source links**,
  not redistributed full text; original IR pages remain authoritative.
- Respect issuer robots/terms and transcript rights. The per-company allowlist is
  a manual onboarding gate, not a license to copy or republish material.
- Raw bytes downloaded by core.Client live only under disclosures/storage/ and
  may appear in the workflow evidence artifact, not in the public Pages build.
- Some companies publish only audio or PDF. These require separately reviewed
  official-source adapters; the generic HTML detector never invents a transcript.

## Initial coverage

SEC 8-K Item 2.02 metadata: MSFT, NVDA, AAPL, AMZN, META, GOOGL, TSLA.
Official IR transcript detection: MSFT, seeded with the verified FY26 Q4 URL and
bounded candidate scanning for the latest fiscal quarters. Other issuers have
empty IR allowlists and are **not** counted as transcript-covered until vetted.

## Run

From the repository root:

    python disclosures/app/earnings_calls.py
    PYTHONPATH=disclosures/app python -m unittest discover -s disclosures/tests -p test_earnings_calls.py -v

Input: disclosures/config/earnings_calls.json
Output: disclosures/docs/data/earnings-calls/index.json
Page: /disclosures/#calls (published after a Pages build).
Workflow: .github/workflows/earnings-calls.yml, every 4 hours or manual dispatch.

Uses the same SEC_USER_AGENT contract as disclosures/app/core.py; a real
app-and-contact address must be configured. SEC fair-access max is currently
10 requests/second, but this module uses the existing client host pacing.
Failures retain prior valid records per ticker and report partial health, not
fake success. The last attempt, last full success, source date and Pages publish
timestamp are separate concepts; the static page does not claim it updated until
the site build actually deploys.

## Next phases (not implemented yet)

- Vet and onboard other issuers' IR URLs, RSS and PDFs company-by-company.
- With appropriate rights, add a licensed full-text store, speaker-turn parsing,
  guidance revision histories and speech-to-text for accessible authorized audio.
- Link transcript sentences to SEC 10-Q / 10-K numbers; provide analyst Q&A and
  a source-aware Flo alert only for newly verified call transcripts.
- Add rights/audit metadata, idempotent queues and per-provider replay tests.
