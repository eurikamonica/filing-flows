"""European results releases (6-K exhibits) the reader used to misread: IFRS statements that print expenses as negative
figures, year-to-date columns written "Q1–Q3" or "Jan-Sep", the year-ago column not always the second one, bank and
Swedish line names, note references beside the lines, and quarters only a year-to-date statement gives."""
import datetime as dt

from pipeline import build, facts, release


def _t(head_rows, rows, title=""):
    """A table: header rows (lists of cells) above labelled rows of figures."""
    h = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in head_rows)
    b = "".join("<tr><td>" + lab + "</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for lab, *vals in rows)
    return f'<table>{"<tr><td>" + title + "</td></tr>" if title else ""}{h}{b}</table>'


def _doc(*parts, intro="Results for the third quarter ended 30 September 2026"):
    return f"<html><body><p>{intro}</p>" + "".join(parts) + "</body></html>"


FILED = dt.date(2026, 10, 29)


def test_tax_printed_negative_is_an_expense_when_the_statement_prints_costs_negative():
    # Sanofi, TotalEnergies, Tenaris: no pre-tax line, "Income tax expense (1,195)" under costs printed in parentheses
    html = _doc(_t([["(€ million)", "Q3 2026", "Q3 2025"]],
                   [("Net sales", "14,444", "12,434"), ("Cost of sales", "(3,632)", "(3,412)"),
                    ("Research and development expenses", "(1,849)", "(1,834)"), ("Operating income", "4,349", "3,623"),
                    ("Income tax expense", "(1,195)", "(680)"), ("Net income", "3,029", "2,808")]))
    r = release.parse(html, FILED)
    assert r["neg_costs"] is True
    raw = release.reconcile({k: (abs(v) if k in release.COST_KEYS else v) for k, v in r["is"].items()}, r["labels"],
                            neg_costs=r["neg_costs"])
    assert raw["tax"] == 1195e6                                   # an expense, so pre-tax = 3,029 + 1,195, not 1,834


def test_year_to_date_and_quarter_headers():
    q = release._first_is_quarter
    assert q("€ millions q1–q3 2026 q1–q3 2025") is False          # SAP's cash flows: nine months
    assert q("q3 jan-sep sek million 2026 2025") is True           # Ericsson
    assert q("three-month period ended september 30, nine-month period ended") is True     # Tenaris
    assert q("9 months 2026 £m 9 months 2025 £m") is False         # GSK's cash flows
    assert q("consolidated statement of income quarters $ million nine months q3 2026 q2 2026 q3 2025") is True   # Shell
    assert q("q326 q226 q126 q425 q325") is True                    # Barclays
    # BP: "Third | Third | Nine | Nine" above "quarter | quarter | months | months" — the columns' own titles say it
    html = _doc(_t([["", "Third", "Third", "Nine", "Nine"], ["", "quarter", "quarter", "months", "months"],
                    ["$ million", "2026", "2025", "2026", "2025"]],
                   [("Sales and other operating revenues", "68,399", "48,420", "189,759", "141,952"),
                    ("Profit before interest and taxation", "9,684", "4,555", "27,111", "13,104"),
                    ("Profit before taxation", "8,613", "3,236", "23,799", "9,249"), ("Taxation", "(3,476)", "(1,727)", "(10,120)", "(4,829)"),
                    ("Profit for the period", "5,137", "1,509", "13,679", "4,420")]))
    r = release.parse(html, dt.date(2026, 10, 30))
    assert r["is_quarter"] is True and r["is"]["oi"] == 9684e6 and r["py_col"] == 1


def test_the_year_ago_column_is_found_by_its_title():
    # TotalEnergies: "3rd quarter 2026 | 2nd quarter 2026 | 3rd quarter 2025" — the year-ago quarter is the third column
    html = _doc(_t([["", "3rd quarter", "2nd quarter", "3rd quarter"], ["(M$)", "2026", "2026", "2025"]],
                   [("Sales", "66,819", "61,771", "48,691"), ("Purchases, net of inventory variation", "(40,100)", "(38,000)", "(31,000)"),
                    ("Other operating expenses", "(9,000)", "(8,700)", "(8,100)"),
                    ("Income taxes", "(5,080)", "(3,154)", "(2,423)"), ("Consolidated net income", "8,363", "5,475", "3,762")]))
    r = release.parse(html, FILED)
    assert r["py_col"] == 2 and r["is_quarter"] is True
    # Barclays: one title per column, the year-ago quarter fifth
    html = _doc(_t([["Income statement information", "Q326", "Q226", "Q126", "Q425", "Q325"], ["", "£m", "£m", "£m", "£m", "£m"]],
                   [("Net interest income", "3,500", "3,400", "3,300", "3,300", "3,200"), ("Total income", "7,365", "8,338", "8,163", "7,077", "7,167"),
                    ("Profit before tax", "2,322", "3,252", "2,814", "1,859", "2,077"), ("Profit after tax", "1,900", "2,521", "2,176", "1,471", "1,712")]))
    r = release.parse(html, dt.date(2026, 10, 22))
    assert r["is"]["revenue"] == 7365e6 and r["py_col"] == 4    # a bank's "Total income" is its revenue
    # Santander: the quarter before, no year-ago column: none is taken
    html = _doc(_t([["EUR million", "3Q'26", "2Q'26", "%", "9M'26", "9M'25"]],
                   [("Net interest income", "11,000", "10,900", "1.0", "33,000", "32,000"), ("Total income", "15,891", "15,682", "1.3", "46,713", "45,000"),
                    ("Profit before tax", "4,828", "4,932", "-2.1", "14,789", "13,900"), ("Profit attributable to the parent", "3,432", "3,518", "-2.4", "12,405", "9,800")]))
    r = release.parse(html, FILED)
    assert r["py_col"] == -1
    assert build._py_index(r) is None


def test_oldest_quarter_first_is_read_newest_first():
    # ASML: "Q4 2025 | Q1 2026" — the current quarter is the second column, and the first is the quarter before
    html = _doc(_t([["(Figures in millions of euros)", "Q4 2025", "Q1 2026"]],
                   [("Total net sales", "9,718", "8,767"), ("Gross profit", "5,068", "4,645"), ("Net income", "2,840", "2,757")]),
                intro="ASML reports first-quarter 2026 results, quarter ended March 29, 2026")
    r = release.parse(html, dt.date(2026, 4, 15))
    assert r["is"]["revenue"] == 8767e6 and r["py_col"] == -1 and r["end"] == "2026-03-29"


def test_note_references_beside_the_lines_are_not_line_names():
    # Fresenius Medical Care: "Revenue:" over three lines and an unlabelled total with "2 a), 14" in the Note column
    html = _doc(_t([["", "Note", "Q3 2026", "Q3 2025"]],
                   [("Revenue:", ), ("Health care services", "", "3,312,626", "3,300,000"), ("Health care products", "", "1,120,332", "1,100,000"),
                    ("Insurance contracts", "", "503,784", "485,000"), ("", "2 a), 14", "4,936,742", "4,885,000"),
                    ("Operating income", "", "384,089", "476,500"), ("Income before income taxes", "", "302,630", "402,600"),
                    ("Income tax expense", "", "77,835", "75,200"), ("Net income", "", "224,795", "327,400")]),
                intro="(in thousands) Results for the three months ended September 30, 2026")
    r = release.parse(html, dt.date(2026, 11, 3))
    assert round(r["is"]["revenue"]) == 4936742e3


def test_swedish_and_ifrs_line_names():
    html = _doc(_t([["SEK million", "Q3 2026", "Q3 2025"]],
                   [("Net sales", "59,478", "56,239"), ("Cost of sales", "-31,488", "-29,462"), ("Gross income", "27,990", "26,777"),
                    ("Selling and administrative expenses", "-7,411", "-7,913"),
                    ("Earnings before financial items and income tax (EBIT)", "8,864", "15,151"),
                    ("Income after financial items", "7,954", "14,939"), ("Income tax", "-2,157", "-3,639"), ("Net income", "5,797", "11,300")]))
    r = release.parse(html, dt.date(2026, 10, 15))
    assert {k: r["is"][k] for k in ("gp", "sga", "oi", "pretax")} == {"gp": 27990e6, "sga": -7411e6, "oi": 8864e6, "pretax": 7954e6}


def test_line_names_lose_footnotes_and_thereof():
    d = release.display_label
    assert d("Thereof Cloud ERP Suite 2") == "Cloud ERP Suite" and d("IaaS 2") == "IaaS" and d("– Wealth") == "Wealth"
    assert d("Europe, Middle East and Africa¹⁾²⁾") == "Europe, Middle East and Africa"
    assert d("iPhone") == "iPhone" and d("Microsoft 365") == "Microsoft 365"


def test_total_to_core_reconciliation_is_not_the_statement():
    # GSK: a "Total results | ... | Core results" table first, the income statement with its year-ago column after it
    recon = _t([["", "Total results £m", "Intangible amortisation £m", "Core results £m"]],
               [("Turnover", "8,547", "", "8,547"), ("Operating profit", "2,593", "198", "2,791"), ("Profit before taxation", "2,456", "198", "2,654"),
                ("Taxation", "(312)", "(29)", "(341)"), ("Profit after taxation", "2,144", "169", "2,313")])
    stmt = _t([["", "Q3 2026 £m", "Q3 2025 £m"]],
              [("Turnover", "8,887", "8,547"), ("Operating profit", "2,127", "2,593"), ("Profit before taxation", "1,935", "2,456"),
               ("Taxation", "(232)", "(312)"), ("Profit after taxation", "1,703", "2,144")], title="Income statement")
    r = release.parse(_doc(recon, stmt), dt.date(2026, 10, 28))
    assert r["is"]["revenue"] == 8887e6 and r["py_col"] == 1


def test_associates_after_the_tax_line_still_reconcile():
    # Philips: "Investments in associates, net of income taxes" between the tax line and net income
    raw = {"revenue": 4393e6, "oi": 165e6, "pretax": 122e6, "tax": -92e6, "pl": 28e6}
    try:
        release.reconcile(dict(raw))
        assert False, "should not reconcile without the associates"
    except ValueError:
        pass
    r = release.reconcile(dict(raw), equity_method=True)
    assert r["tax"] == 92e6 and r["pretax"] == r["pl"] + r["tax"]


def test_first_half_after_the_full_year_column():
    # RELX: "Year ended 31 December 2025 | Six months ended 30 June 2025 | 2026": the half is the last column
    html = _doc(_t([["", "Year ended 31 December", "Six months ended 30 June"], ["GBPm", "2025", "2025", "2026"]],
                   [("Revenue", "9,590", "4,741", "4,871"), ("Operating profit", "3,027", "1,490", "1,585"),
                    ("Profit before tax", "2,750", "1,283", "1,523"), ("Tax charge", "(672)", "(304)", "(348)"),
                    ("Net profit for the period", "2,078", "979", "1,175")]),
                intro="RELX interim results for the six months ended 30 June 2026")
    r = release.parse(html, dt.date(2026, 7, 23))
    assert r["is"]["revenue"] == 4871e6 and r["cols"]["revenue"][r["py_col"]] == 4741e6


def test_period_end_from_the_statement_label_before_older_dates_in_the_text():
    # BP's first-quarter report also speaks of "the year ended 31 December 2025" (within 120 days of filing)
    html = _doc(_t([["", "First", "Fourth", "First"], ["", "quarter", "quarter", "quarter"], ["$ million", "2026", "2025", "2025"]],
                   [("Sales and other operating revenues", "52,255", "50,000", "47,383"), ("Profit before taxation", "7,365", "5,000", "1,000"),
                    ("Taxation", "(3,153)", "(2,000)", "(1,500)"), ("Profit for the period", "4,212", "3,000", "-500")]),
                intro="Annual report for the year ended 31 December 2025 was published in March.")
    r = release.parse(html, dt.date(2026, 4, 28))
    assert r["end"] == "2026-03-31"


def test_a_percentage_column_is_never_the_year_ago_one():
    # Ferrari's interim report: 2026 | % of revenues | 2025 | % of revenues | change
    rel = {"scale": 1e6, "py_col": None, "cols": {"revenue": [1896e6, 100e6, 1766e6, 100e6, 130e6]}}
    assert build._py_index(rel) == 2


def _q(end, fq, fy, raw, py=None):
    return {"end": end, "fq": fq, "fy": fy, "raw": raw, "raw_py": py, "form": "6-K"}


def test_quarters_from_the_year_to_date():
    R = lambda rev, ni, ocf=None: dict({k: None for k in facts.CONCEPTS}, revenue=rev, pl=ni, ni=ni, ocf=ocf)
    c = {"profile": {"fye": "1231"}, "quarters": {"2026-03-31": _q("2026-03-31", 1, 2026, R(17.3e9, 7.4e9, 2e9), R(15.5e9, 5.2e9, 1e9))},
         "ytd": {"2026-06-30": {"end": "2026-06-30", "fq": 2, "fy": 2026, "raw": R(35.4e9, 15.3e9, 5e9), "raw_py": R(32.2e9, 12.4e9, 3e9),
                                "py_end": "2025-06-30"},
                 "2026-09-30": {"end": "2026-09-30", "fq": 3, "fy": 2026, "raw": R(53.2e9, 22.9e9, 8e9), "raw_py": R(50.0e9, 17.9e9, 4e9),
                                "py_end": "2025-09-30"}}}
    made = build._derive_ytd_quarters(c)
    assert made == ["2026-06-30", "2026-09-30"]
    q2, q3 = c["quarters"]["2026-06-30"], c["quarters"]["2026-09-30"]
    assert round(q2["raw"]["revenue"]) == round(18.1e9) and round(q2["raw"]["ocf"]) == round(3e9) and q2["derived"] == "ytd"
    assert round(q3["raw"]["revenue"]) == round(17.8e9) and round(q3["raw_py"]["revenue"]) == round(17.8e9)
    assert q3["q1_end"] == "2026-06-30" and q2["q1_end"] == "2026-03-31"
    # a quarter read from its own release is never replaced
    c["quarters"]["2026-06-30"] = _q("2026-06-30", 2, 2026, R(18.0e9, 7.9e9))
    build._derive_ytd_quarters(c)
    assert c["quarters"]["2026-06-30"]["raw"]["revenue"] == 18.0e9 and not c["quarters"]["2026-06-30"].get("derived")
