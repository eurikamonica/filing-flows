# Changelog

## 4.1.0

Officials' disclosures beyond the US House: New York State (COELIG statements, HTML, value categories), California
(FPPC Public Official Financial Disclosure Portal, Form 700 PDFs since 2025), Canada (federal public registry
declarations); Texas and Canada SEDI as imports with an honest status (no public online PFS viewer; SEDI bot
protection probed every run). Optional price-based cost estimates: Stooq daily closes + OpenFIGI CUSIP→ticker;
13F quantity change × quarter-average close, reviewed transactions priced on their date; toggle in the UI, stored
per browser. Jurisdiction filter, per-jurisdiction health table, `prices` module. HTTP client gained POST/JSON,
cookies and challenge-page detection. Verified against the live sources: California downloads use the portal's
`GET GetRedactedFormPdf?indexID&fileNameInfo.*` call; New York statements are served as PDFs; the Canadian registry
lives at ethicscanada.ca (profile pages); SEDI is probed at its root. Per-jurisdiction batch shares, cursors for the
NY index, CA partition rotation and the Canada listing, resilient data commits.

## 4.0.0

Broad COT and active-FDIC catalogs with rotating history queues; two-stage N-PX discovery/download queue; per-entity histories and 1,000-row vote chunks; demand-loaded catalogs; priority bank/market inputs and hourly markets run; v3 data migration; source-count validation and COT consolidated-code support.

## 3.0.0

SEC 13F/N-PX index discovery; unfiltered House index catalog; durable batching and priority Actions inputs; quarter shards and compressed caches; directory and coverage counters; redesigned responsive workspace; complete asset names and compact intervals; centered weight-change bars; position sorting; treemap-to-security selection; missing House dates no longer discard an index; large-manager security menu lookup optimized.

## 2.0.0

Integrated prior 13F library and tests, House watchlist PDF/OCR, reviewed records, English interface and Actions/Pages template.

## 1.1

Configured COT, bank financials and N-PX; SEC contact set to Eurika eurikamonica@gmail.com.
