# Flo Published Pulse — Non-Refreshing Disclosure & Market Notifications

**Status:** Implemented on the PR #72 feature branch; **not production-live before merge and GitHub Pages deployment.** Flo is still the existing Spin Sankey mascot (its SVG, mouse-following eyes, palette, animations and Finance Academy are retained). This feature works on an **open, visible browser tab** and requires no browser notification permission, external background agent or new paid data service.

## How it works

\`\`\`text
SEC EDGAR 8-K | watched 13F managers | sourced press release/FDA/SEC headlines
daily-close extreme-mover snapshots
                │
     Existing Filing Flows collectors
                │ staged, independently timestamped public JSON
      scripts/build_flo_alerts.py
                │ validates evidence, shapes/deduplicates <=120 small records
     _site/disclosures/data/market/flo-alerts.json
                │ same-origin browser fetch every 120 sec when visible
      web/flo-alerts.js → Flo notice pill / inbox / quiet mode
                │
      Existing FFMascot.signalReaction / showSignal
        8-K warning · 13F wave/spin · daily-price hop · news talk
                │
      Open original SEC/news source, compare company fundamentals
\`\`\`

### Source data and limits

| Channel | Input | ID / timestamp / evidence | Scope / caveat |
| --- | --- | --- | --- |
| SEC Form 8-K / 8-K/A | \`disclosures/data/market/events8k.json\` | Unique accession; SEC archival URL; accepted/filer time; item/topic tags | Alert **after collector and Pages publication**, not at company event time. SEC EDGAR accepted clock interpreted in New York time and converted to UTC. Priority is only an editorial screening tag. |
| Institution 13F | \`disclosures/data/market/watchlist.json\` | Selected watched manager CIK + quarterly period + filed date; SEC Archive link | **Initially the managers in the existing 13F watchlist**, not the entire SEC manager universe. Shows new, added, reduced and exited names from the published period-to-period comparison. Filing date is **not transaction date**; reporting is delayed. |
| News | \`disclosures/data/market/news.json\` | Original feed item ID, publication time, original PR Newswire / FDA / SEC source link | Only linked tickers (including multi-ticker item lists). **Headline content is not independently verified.** |
| Daily price moves | \`disclosures/data/market/extremes.json\` | Ticker + **published close date**, last daily close and one-day return. Magnitude at least **5%**, importance higher at **10%** | Delayed **daily-close** changes, not intraday ticks, continuous market data or proven news causality. Full intraday coverage would require a separate validated market-data publisher. |

The compact feed is built by the existing \`.github/workflows/scan.yml\` **after** \`disclosures/automation/stage-public.py\` stages the real collector JSON to \`_site/disclosures/data/market/\`. This does not initiate new SEC fetches and cannot falsely claim a collector succeeded when its source JSON is unchanged. Each output carries \`generated_at\` and the originating sources' publication timestamps. Normal hourly/15-minute scan queuing, pipeline failures and GitHub Pages CDN propagation can delay arrival beyond browser polling.

### Notification lifecycle

- **On first use:** Seed the most recent event IDs silently; **do not splash historical news as new**.
- **During an open tab:** Poll the single small JSON every **120 seconds**, without refreshing the HTML or interrupting a chart, model or input form. When the tab is hidden, pause polling and resume on visibility/online change. Unavailable feed backs off up to 15 minutes.
- **Detection:** Compare immutable event IDs and event timestamps; ignore the same accession, headline, manager/quarter and ticker/close date after repeat publication, and avoid delayed historic backfill alerts older than 72 hours. Keep up to 320 IDs browser-local. A different JSON \`generated_at\` invalidates Flo's internal cached company snapshot on the NEXT question, not by forcing the entire site to reload.
- **Action:** Show a small, dismissible alert toast and inbox counter, **never auto-open the chat**, play audio, auto-trade or request notification permissions.
- **Visible reactions:** High-priority 8-K: worried, shake, red accent; 13F: wave, spin, blue accent; negative/positive daily close: worried or happy jump, amber accent; news: talk cue, green accent. Respect \`prefers-reduced-motion\`; quiet mode suppresses motion as well as popups.
- **Evidence answer:** Clicking **Ask Flo** opens the existing assistant with the item title, filing/close timestamp, accession/topic category or manager + quarter + selected changed tickers, proper causal/method caveats and SEC/source link. A second action may compare the corresponding company's earnings, valuation or industry context, **not infer the price move was caused by the filing**.
- **Preferences:** Inbox allows 8-K/13F/News/Daily-close toggles, comma-separated ticker watchlist such as \`OKLO, IREN, CRWV\`, and quiet mode. A manager 13F matches **any linked changed ticker**, not only the first new position. Settings and seen IDs stay in **that browser's localStorage**, not a cloud database.

### Security and accessibility

- Only same-origin, read-only fetches of the generated JSON; no cookies are sent outside that origin; text is escaped or rendered through \`textContent\`.
- Outbound source links are restricted to verified \`https://sec.gov\`, \`https://prnewswire.com\`, and \`https://fda.gov\` hostnames and their \`www.\` equivalents. Lookalike domains are refused.
- All surprise UI is dismissible; alert inbox shows source-timestamp context; colors are **supplemental** to icons/text, not the only signal.
- Popup animations are reduced/disabled if the user has requested reduced motion. No system-level push notifications are asserted.

### Files

\`scripts/build_flo_alerts.py\`, \`web/flo-alerts.js\`, \`web/mascot.js\`, \`web/index.html\`, \`.github/workflows/scan.yml\`; tests: \`tests/test_flo_alert_feed.py\`, \`tests/test_flo_alerts.cjs\`, \`tests/test_flo_alert_browser.cjs\`; included in \`.github/workflows/ci.yml\` and \`.github/workflows/flo-academy-checks.yml\`.

Tests cover source URL safeguards, accepted New York → UTC conversion, 13F manager/changed ticker selection, daily-close thresholds, fake news links, initial baseline, repeat-ID deduplication, delayed backfill suppression, HTML escaping, distinct moods, open-tab arrival without a page reload, click-through to the assistant and quiet-mode suppression.

### Must-pass production verification (AFTER merge)

1. Run \`python3 tests/test_flo_alert_feed.py\`, \`node tests/test_flo_alerts.cjs\`, \`node tests/test_flo_alert_browser.cjs\`, \`node tests/test_mascot.cjs\` and all PR workflows.
2. Verify the deployment contains **both** \`web/flo-alerts.js\` and a valid, recent \`/disclosures/data/market/flo-alerts.json\`. A JS file alone is **not** a working alert feed.
3. Keep the homepage open across a genuinely new event published by the pipeline; confirm the in-page toast shows without user reload, one distinct event triggers one notification, the SEC link works, and repeat builds don't re-alert.
4. Verify a real watched manager 13F event is labeled with its **quarter-end** and **filing date**, not a same-day trade.
5. Verify a Daily Price alert explicitly says **delayed close**, not real-time intraday.
6. Test no-feed/failure behavior, tab background/foreground changes, quiet mode, watch tickers, mobile layout, and accessibility reduced-motion mode.
7. Keep the PR in Draft until deployment is verified. New capabilities are not evidence of **production enablement**.

**Future upgrades (not present):** true streaming via SSE/WebSocket, reliable background/mobile push when the tab is closed, broad all-manager 13F filing discovery, intraday volume+price feeds, user account watchlists and saved research alerts.
