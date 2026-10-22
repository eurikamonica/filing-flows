"""Earnings releases the reader used to reject (Meta, CACI, Southwest, Las Vegas Sands, Sonoco) and exhibit names it missed."""
import datetime as dt
import re

from pipeline import build, release

ROW = '<tr><td>{}</td><td>$</td><td>{}</td><td>$</td><td>{}</td>{}</tr>'


def _table(rows, title="", pct=False):
    extra = '<td>8.2</td><td>%</td>' if pct else ''
    body = ''.join(ROW.format(l, a, b, extra) for l, a, b in rows)
    head = '<tr><td></td><td colspan="4">Three Months Ended September 30,</td></tr><tr><td></td><td>2026</td><td>2025</td></tr>'
    return f'<table>{"<tr><td>" + title + "</td></tr>" if title else ""}{head}{body}</table>'


IS = [("Revenue", "64,601", "51,242"), ("Cost of revenue", "13,369", "9,206"), ("Income from operations", "12,988", "20,535"),
      ("Income before provision for income taxes", "13,001", "21,138"), ("Provision for income taxes", "3,141", "18,954"),
      ("Net income", "9,860", "2,184")]


def _doc(*parts):
    return "<html><body><p>Results for the quarter ended September 30, 2026</p>" + "".join(parts) + "</body></html>"


def test_footnote_about_non_gaap_above_the_statement():
    # Meta: the previous page ends with a footnote on non-GAAP measures, right above the statement's own title
    html = _doc("<p>(In millions)</p><p>For a reconciliation of GAAP to non-GAAP measures, see the table below.</p>",
                _table(IS, "CONDENSED CONSOLIDATED STATEMENTS OF INCOME"))
    r = release.parse(html, dt.date(2026, 10, 21))
    assert r["end"] == "2026-09-30" and r["is"]["revenue"] == 64601e6 and r["is"]["pl"] == 9860e6


def test_title_above_the_table_nearer_than_the_non_gaap_note():
    # Las Vegas Sands, Lithia: the title is printed above the table, a non-GAAP paragraph further up
    html = _doc("<p>Adjusted EBITDA is a non-GAAP measure.</p><p>Condensed Consolidated Statements of Operations</p>"
                "<p>(In millions)</p>", _table(IS))
    assert release.parse(html, dt.date(2026, 10, 21))["is"]["revenue"] == 64601e6


def test_percent_change_column_and_operating_revenues():
    rows = [("Total operating revenues", "8,422", "7,224")] + IS[2:]
    html = _doc("<p>(In millions)</p>", _table(rows, "Consolidated Statement of Income", pct=True))
    r = release.parse(html, dt.date(2026, 10, 21))
    assert r["is"]["revenue"] == 8422e6 and r["is"]["pl"] == 9860e6


def test_slash_labels():
    assert release.PATTERNS["pl"].search(release.norm_label("Net (loss)/income"))
    assert release.PATTERNS["oi"].search(release.norm_label("Operating (loss)/profit"))


def test_exhibit_names():
    pats = build.EXHIBIT_PATTERNS
    for name in ("meta-09302026xexhibit991.htm", "wdfc-20261021xexx991.htm", "osbc-ex99d1.htm", "ex-99_1.htm", "exhibit991102126.htm"):
        assert any(re.search(p, name, re.I) for p in pats), name
    assert build.NOT_EXHIBIT.search("R1.htm") and not build.NOT_EXHIBIT.search("spaceexplorationtechnologi.htm")
