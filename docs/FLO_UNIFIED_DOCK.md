# Flo Unified Mobile Dock

## Why

The old site loaded three independent fixed-position surfaces: the original **Spin Sankey Flo** mascot in `web/mascot.js`, a fixed **Flo · Published** pill in `web/flo-alerts.js`, and a fixed **Flo · 5m** pill in `web/flo-momentum.js`. On mobile, all three overlapped Daily Report / Alerts content and created multiple competing entrances.

## Design

There is **exactly one fixed Flo launcher**: the original mascot and halves. Inside the existing Flo dialogue:

| Tab | Function | Reused controller |
| --- | --- | --- |
| ✦ Academy / Chat | Real SEC workbooks, DCF, cases, tutor and natural-language company research | `FFMascot` |
| ◉ Scans | 8-K, 13F, official-source news, daily closes; event timeline, original filing links, watchlist, quiet mode and source freshness | `FFFloAlerts.openPanel(host)` |
| ↗ 5m | Exact five-minute gainers in S&P 500 / Russell 1000 / Russell 2000; user filters for gain, dollar turnover and streak; incomplete coverage warnings | `FFFloMomentum.openPanel(host)` |

The embedded panels retain their underlying polling and business logic; only their **presentation** changes. Neither scanner creates a standalone floating pill or toast. They attach their pane to `FFMascot.toolHost()`, and Flo owns the notification speech bubble and unread counter. For a genuinely new (not first-load) SEC event, the mascot retains the kind-specific gesture. For a new leading five-minute gainer, it retains the price gesture and quiet/filter gating. On the **next mascot tap**, the corresponding Scans / 5m tab opens automatically. Clicking a filing's Research/Timeline action returns to Flo Chat with the source-backed analysis.

## Accessibility and responsive behavior

- Top-level tabs are real `button` elements with `role=tab` and updated `aria-selected`.
- A live unread badge appears only as part of the existing mascot; tool badges are inside the panel.
- The tool host scrolls inside Flo and avoids additional fixed panels. The original mobile Flo drawer occupies up to 82dvh (or full height when user explicitly expands it).
- The original DCF Academy and worksheets remain fully functional. There is no forced refresh, no background push subscription, no extra stock API or invented market coverage.
- Page CSS uses the existing site's colors and styles; no AI-generated image or new unrelated mascot.

## Tests

`tests/test_flo_alert_browser.cjs` now confirms that a tab left open learns of a new SEC event and invokes a **single** mascot notice; after the first-load baseline it exposes embedded inbox / 8-K source / timeline / modeling guidance and still suppresses alerts in quiet mode. No separate `flo-pulse-pill` or `flo-pulse-toast` is added.

`tests/test_flo_unified_dock.cjs` covers three tab APIs, the absence of standalone 5m/published pills, reading the existing 5-minute Supabase projection, source-valid gainers, unchanged min-filters, new leader notifications, original mascot gestures and no second floating toast. CI runs both tests in the Flo Academy, Flo Pulse and site-wide workflows.

## Production validation required

After merge and deployment, open `https://filing-flows.com/` on Android. Verify that only the Spin Sankey Flo mascot floats at the bottom, then tap **学院 / 扫描 / 5m** to inspect each tool. The site must continue to show "not authorized / data unavailable" where minute candles or licensed index membership are not available; this PR does not add market feeds.
