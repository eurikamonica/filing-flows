# Sources and provenance

Checked 2026-10-06. API behavior, document formats and access policies may change.

## Integration provenance

- Original Filing Flows repository, read-only research: https://github.com/eurikamonica/filing-flows/tree/main
- README successfully retrieved: https://raw.githubusercontent.com/eurikamonica/filing-flows/main/README.md
- Earlier user artifact actually retrieved and inspected: `Filing-Flows-13F-Standalone.zip`.
- Reused from that artifact: namespace-aware 13F parser, identity/aggregation, restatement/new-holdings resolution, comparison formulas and 17 tests. Discovery/load functions were adapted to the shared client. The new unified frontend implements the former treemap, change and history interactions.
- This is an independent project. No claim of a full original-repository audit; no changes to that repository.

## SEC

- EDGAR API overview: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Technical specifications: https://www.sec.gov/submit-filings/technical-specifications
- 13F FAQ: https://www.sec.gov/files/divisions/investment/13ffaq.htm
- N-PX reporting explanation: https://www.sec.gov/newsroom/press-releases/2022-198
- N-PX sample: https://www.sec.gov/Archives/edgar/data/1630243/000163024325000012/0001630243-25-000012-index.htm

The collectors discover filings through submissions, traverse actual accession directories, and download listed XML documents. Every displayed 13F snapshot contains its source filing chain.

## House and Senate

- House disclosure overview: https://disclosures-clerk.house.gov/FinancialDisclosure
- Actual overview partial containing annual links: https://disclosures-clerk.house.gov/FinancialDisclosure/ViewReport
- House access/use conditions: https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch
- 2024 annual report used for checked excerpts: https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2024/10066169.pdf
- 2025 annual report used for checked excerpts: https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2025/10075701.pdf
- PTR used for checked transaction and OCR smoke test: https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20035553.pdf
- Senate disclosure/access guidance: https://www.ethics.senate.gov/public/index.cfm/financialdisclosure
- Senate public search entry: https://efdsearch.senate.gov/search/home/

Annual archive links are extracted from the live House page. PDF routes are restricted to the currently verified House P/O adapter and validated with the PDF signature. Other filing codes are explicit unsupported coverage, not guessed equivalents.

## CFTC and FDIC

- COT help/API: https://publicreporting.cftc.gov/stories/s/COT-Help/p2fg-u73y/
- Disaggregated futures-only: https://publicreporting.cftc.gov/d/72hh-3qpy
- TFF futures-only: https://publicreporting.cftc.gov/d/gpe5-46if
- FDIC data downloads: https://www.fdic.gov/bank-data-guide/data-downloads
- BankFind API docs: https://api.fdic.gov/banks/docs/
- Financial field definitions: https://api.fdic.gov/banks/docs/risview_properties.yaml
- API 101/key information: https://banks.data.fdic.gov/bankfind-suite/bulkData/api101

## Tools and deployment

- pdfplumber: https://github.com/jsvine/pdfplumber
- Tesseract installation: https://tesseract-ocr.github.io/tessdoc/Installation.html
- GitHub Pages custom workflows: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- GitHub scheduled events: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

Source evidence records preserve URLs, acquisition timestamps and SHA-256. Public free data access does not promise unlimited requests, permanent endpoints or zero infrastructure costs.

## v3 discovery and deployment references

- SEC index documentation: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SEC full indexes: https://www.sec.gov/Archives/edgar/full-index/
- House actual annual ZIP links: https://disclosures-clerk.house.gov/FinancialDisclosure/ViewReport
- GitHub browser upload limits: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository

## v4 expanded sources

- FDIC API documentation and institutions endpoint: https://api.fdic.gov/banks/docs
- CFTC Public Reporting Environment API guide: https://publicreporting.cftc.gov/stories/s/COT-Help/p2fg-u73y/
- CFTC report family coverage: https://publicreporting.cftc.gov/stories/s/Public-Reporting-FAQ/inwp-fmhz/
- N-PX XML example: https://www.sec.gov/Archives/edgar/data/1434997/0001434997-24-000005-index.htm

Live v4 collection requests and hashes are recorded in notes/v4-collection-runs.json.
