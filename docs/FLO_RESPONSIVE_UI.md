# Flo Academy — Responsive Workspace & Compact Quick Tools

## Problem observed

A desktop capture around 1190 × 750 px showed the original assistant
`380 × 540 px` window with a long title banner, eleven always-visible
tool shortcuts, example chips, a tiny message viewport, independent nested
course scrolling, and a mascot overlapping input/title areas.

This update changes only **web/mascot.js** layout/interaction and adds
**tests/test_flo_layout.cjs**. SEC models, Academy lesson state, event
monitoring, the underlying calculations, and the mascot's reactions are
not modified.

## Revised behavior

| Mode | Viewport sizing | Key improvement |
|---|---|---|
| Desktop normal | Width up to 490px, height up to 730px or dynamic available height | More room for long SEC research answers |
| Desktop spreadsheet | Width up to 880px | Wider financial model and Excel-style exercises |
| Desktop expand | Width up to 1080px, height near full dynamic viewport | Optional spacious study workspace |
| Mobile normal | Bottom sheet occupying 82dvh | Keeps the page accessible underneath |
| Mobile expand | Full-width, full-height 100dvh | More room for guided modeling and financial statements |

A **⤢ / ⤡** header control expands and restores the panel without closing
the conversation or resetting the active lesson. `aria-pressed`,
`aria-label` and the title update with the state; the × and Escape actions
still close Flo normally.

The tool strip now defaults to four frequently used actions in a single
horizontally scrollable row: **Real SEC Lab**, **Spreadsheet Lab**,
**Learn DCF**, and **5m Market Movers**. All other existing course modes and
the question bank remain under **More tools**; changing a lesson restores the
compact strip to maximize reading space. The rotating **More questions**
button remains accessible in the expanded tools.

The input composer is not squeezed by a long lesson and the answers scroll
within the workspace instead of shrinking the message region. Coursework
and workbooks can fill the width of the message column, while their financial
tables can scroll horizontally. The compact title still displays an
investment-risk disclaimer. Mobile styling includes bottom safe-area
padding, and reduced-motion preferences are preserved.

Mascot halves stay visible beside the desktop panel rather than over the
composer. Mobile halves stay at the top edge; expanded view makes them
subtle and non-interactive to keep controls accessible.

## Testing and rollout

`tests/test_flo_layout.cjs` validates stylesheet sizing rules, mobile
breakpoints, scrolling and screen-safe spacing, script compilation,
dynamic page mount, toolbar expansion/collapse, preservation of all eleven
primary/secondary course actions, expand/restore accessibility, side mascot
positioning and close action.

Run:

```bash
node --check web/mascot.js
node tests/test_flo_layout.cjs
node tests/test_mascot.cjs
```

The new layout test is also wired to **Flo Academy checks** and the main
**offline CI** workflows. This PR is a proposed interface fix, not a claim
that GitHub Pages has already published it. Merge and verify the deployed
site across desktop (including short browser heights) and mobile before
marking it live.
