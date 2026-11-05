"""One ticker, one company on the site (build.unique_tickers): NAVI was on Navient Corp and on Navient Holdings."""
from pipeline import build


def test_a_ticker_names_the_company_that_files_now():
    ix = [{"cik": 1593538, "ticker": "NAVI", "name": "Navient Corp", "filed": "2025-02-27", "end": "2024-12-31"},
          {"cik": 2152623, "ticker": "NAVI", "name": "Navient Holdings, Inc.", "filed": "2026-11-04", "end": "2026-09-30"},
          {"cik": 320193, "ticker": "AAPL", "name": "Apple Inc.", "filed": "2026-10-31", "end": "2026-09-27"},
          {"cik": 7, "ticker": "", "name": "No Ticker Inc.", "filed": "2026-08-01", "end": "2026-06-30"}]
    build.unique_tickers(ix)
    by = {x["cik"]: x for x in ix}
    assert by[2152623]["ticker"] == "NAVI" and "former_ticker" not in by[2152623]
    assert by[1593538]["ticker"] == "" and by[1593538]["former_ticker"] == "NAVI"
    assert by[320193]["ticker"] == "AAPL" and by[7]["ticker"] == ""
