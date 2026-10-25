# Appearance and Flo wardrobe

Open **Settings** next to the day/night button. The original day/night theme remains the default; all extra preferences are opt-in and stored locally under `ff:appearance:v1`. Restore defaults clears the custom presentation choices without changing the user's existing day/night preference.

## Included

- Nine website styles including the original, brand mint, newspaper, terminal, millennium, future, finance, technology and notebook, with separate light/dark palettes.
- Seven background treatments with adjustable strength; independent reading and numeric fonts; optional light paper chart canvas. Financial values, chart geometry and positive/negative meanings are unchanged.
- Company and sector following on company and sector routes. Company palettes are curated for AAPL, MSFT, NVDA, JPM, GS, KO and PEP; other companies use their sector. Missing context falls back to the original skin. These are presentation choices, not official company branding.
- Video Studio can use the appearance palette in its existing canvas renderer and export pipeline. Original Studio themes remain available. Export captures a palette snapshot so changing settings cannot change colors midway through a recording.
- Seven coordinated logo/Flo palettes, nine clothing choices, nine headwear choices, five accessories, eight idle expressions and three optional backlights. Overlays attach to the native mascot SVG; its shape, pupils, mouse tracking, split/open animation and financial question handling remain intact.
- Local-date seasons (northern/southern hemisphere), holidays including Lunar New Year where the browser supports the Chinese calendar, and weekday moods. Manual holiday/clothing choices remain available. Explicit clothing and hats take priority over calendar suggestions.
- Optional company weekly-return expressions from the existing `disclosures/data/market/history/t/<ticker>.json` adjusted-close series. The latest adjacent observations must be positive finite numbers and at most ten days old. Future, missing and stale data produce a neutral state. Settings displays the date and percentage. This is **not** an intraday or daily-quote feed. Weekday moods are decorative.

## Architecture

`web/appearance.js` validates stored settings, resolves context, decorates native SVGs and provides `window.FFAppearance`. `web/appearance.css` scopes all presentation overrides. The existing day/night attribute remains authoritative. `mascot.js` only adds an idle-expression hook and ready event. `studio.js` adds an Appearance theme through its existing renderer. `build_site.py` discovers both new assets from `web/index.html`.

No new account permissions, backend service, external image assets, data mutations or paid dependencies are introduced. Settings use a native modal dialog with keyboard Escape, focus handling and responsive controls. Reduced-motion preferences are preserved.

## Verification

```sh
node tests/test_appearance.cjs
node tests/test_mascot.cjs
node tests/test_studio.cjs
# With Playwright installed (optionally set CHROMIUM_PATH):
node tests/test_appearance_browser.cjs
python scripts/build_site.py --data <existing-data-directory> --out <site-directory>
```

Browser checks cover local persistence, original defaults, light/dark colors, company/sector navigation, all clothing/style choices, mobile settings layout and opening the original Flo panel. Appearance changes are in the existing Pages workflow's push paths so a merged release runs the normal production build. Revert the feature commit to roll back; removing the settings key also restores local defaults.
