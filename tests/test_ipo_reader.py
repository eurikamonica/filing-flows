"""The prospectus reader (pipeline/ipo_reader.py) on small made-up registration statements: the contents and the
section each link opens, the risk factors (summary bullets, also when a bullet is drawn in its own table cell, and the
risk headings by category), the notes (one per note number, continued pages merged, the interim set left out), the
cover facts, the holders and share-class tables, and positioned HTML where every printed line is its own element."""
from pipeline import ipo_reader as R

LONG = ("We design, build and sell the products described in this prospectus, and we expect our results to vary from "
        "period to period for the reasons discussed below and elsewhere in this prospectus. ")


def para(text=LONG):
    return f"<p>{text}</p>"


def plain_doc():
    toc = """<table>
      <tr><td><a href="#sum">Prospectus Summary</a></td><td><a href="#sum">1</a></td></tr>
      <tr><td><a href="#rf">Risk Factors</a></td><td><a href="#rf">9</a></td></tr>
      <tr><td><a href="#cap">Description of Capital Stock</a></td><td>40</td></tr>
      <tr><td><a href="#holders">Principal Stockholders</a></td><td>38</td></tr>
      <tr><td><a href="#notes">Notes to Consolidated Financial Statements</a></td><td>F-7</td></tr>
    </table>"""
    summary = f"""<p><a name="sum"></a><b>PROSPECTUS SUMMARY</b></p>{para()}{para()}
      <p><b>Summary of Risk Factors</b></p>{para('Our business is subject to many risks, including:')}
      <table><tr><td>●</td><td>We have a limited operating history and may not become profitable in the future.</td></tr>
             <tr><td>●</td><td>We depend on a small number of suppliers for the components of our products.</td></tr></table>
      <p>• We may need additional capital, which may not be available on acceptable terms or at all.</p>
      <p><b>Corporate Information</b></p>{para()}"""
    risks = f"""<p><b><a name="rf"></a>RISK FACTORS</b></p>{para()}
      <p><b>Risks Related to Our Business</b></p>
      <p><b><i>We have a limited operating history and may not become profitable in the future.</i></b></p>{para()}
      <p><b><i>We depend on a small number of suppliers for the components of our products.</i></b></p>{para()}
      <p>Field: Sequence; Type: Arabic; Name: PageNo 12 Field: /Sequence</p>
      <p><b>Risks Related to This Offering and Our Common Stock</b></p>
      <p><b><i>The market price of our common stock may be volatile, and you could lose all of your investment.</i></b></p>{para()}"""
    capital = f"""<div id="cap"><p><b>DESCRIPTION OF CAPITAL STOCK</b></p>{para()}
      <table><tr><td>Class</td><td>Votes per share</td><td>Shares</td></tr><tr><td>Class A</td><td>1</td><td>100</td></tr>
        <tr><td>Class B</td><td>10</td><td>50</td></tr></table></div>"""
    holders = f"""<div id="holders"><p><b>PRINCIPAL STOCKHOLDERS</b></p>{para()}
      <table><tr><td>Name of beneficial owner</td><td>Shares beneficially owned</td><td>%</td></tr>
        <tr><td>Jane Founder</td><td>1,000,000</td><td>40.0</td></tr><tr><td>Venture Fund I</td><td>500,000</td><td>20.0</td></tr>
        <tr><td>All directors and officers as a group</td><td>1,500,000</td><td>60.0</td></tr></table></div>"""
    notes = f"""<p><a name="notes"></a><b>NOTES TO CONSOLIDATED FINANCIAL STATEMENTS</b></p>
      <p><b>Note 1 — Organization and Summary of Significant Accounting Policies</b></p>{para()}
      <p><b>Basis of Presentation</b></p>{para()}<p><b>Use of Estimates</b></p>{para()}
      <p><b>NOTE 2. REVENUE</b></p>{para('Revenue is recognized when control of the promised products is transferred.')}
      <p><b>Note 2 — Revenue (cont.)</b></p><p><b>Deferred Revenue</b></p>{para()}
      <p><b>3. Leases</b></p>{para()}
      <p><b>NOTES TO CONDENSED CONSOLIDATED FINANCIAL STATEMENTS (UNAUDITED)</b></p>
      <p><b>Note 1 — Organization</b></p>{para()}"""
    cover = ("<p>This is our initial public offering. We have applied to list our common stock on the Nasdaq Global Select "
             "Market under the symbol “ACME.” We are an “emerging growth company” as defined under the federal securities "
             "laws. The initial public offering price is expected to be between $17.00 and $19.00 per share.</p>")
    return f"<html><body>{cover}{toc}{summary}{risks}{holders}{capital}{notes}</body></html>"


def test_contents_sections_and_anchors():
    r = R.read(plain_doc(), "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/acme-s1.htm")
    assert r["how"] == "toc" and r["lines"] is False
    titles = [s["title"] for s in r["sections"]]
    assert titles == ["Prospectus Summary", "Risk Factors", "Principal Stockholders", "Description of Capital Stock",
                      "Notes to Consolidated Financial Statements"]
    rf = r["sections"][1]
    assert rf["anchor"] == "rf" and rf["page"] == "9"
    # the heading that holds the anchor opens its section: it is not left at the end of the summary
    assert all("RISK FACTORS" not in t for t in r["sections"][0]["text"])
    assert rf["words"] > 50 and rf["text"][0].startswith("We design")
    assert not any(t.startswith("Field:") for s in r["sections"] for t in s["text"])
    assert r["url"].endswith("acme-s1.htm")


def test_risks_summary_bullets_and_categories():
    risks = R.read(plain_doc())["risks"]
    assert risks["summary"] == ["We have a limited operating history and may not become profitable in the future.",
                                "We depend on a small number of suppliers for the components of our products.",
                                "We may need additional capital, which may not be available on acceptable terms or at all."]
    groups = risks["groups"]
    assert [g["group"] for g in groups] == ["Risks Related to Our Business", "Risks Related to This Offering and Our Common Stock"]
    assert len(groups[0]["items"]) == 2 and groups[1]["items"][0].startswith("The market price")
    assert risks["count"] == 3


def test_notes_merge_continued_pages_and_stop_at_the_interim_set():
    notes = R.read(plain_doc())["notes"]
    assert [(n["n"], n["title"]) for n in notes] == [
        (1, "Organization and Summary of Significant Accounting Policies"), (2, "REVENUE"), (3, "Leases")]
    assert notes[0]["topics"] == ["Basis of Presentation", "Use of Estimates"]
    assert notes[1]["topics"] == ["Deferred Revenue"] and notes[1]["text"][0].startswith("Revenue is recognized")


def test_cover_holders_and_classes():
    r = R.read(plain_doc())
    assert r["cover"]["symbol"] == "ACME" and r["cover"]["exchange"] == "Nasdaq Global Select Market"
    assert "emerging growth company" in r["cover"]["flags"]
    assert r["holders"][1] == ["Jane Founder", "1,000,000", "40.0"]
    assert r["classes"][2] == ["Class B", "10", "50"]


def test_notes_found_in_the_financial_pages_without_their_own_contents_entry():
    html = plain_doc().replace('<a href="#notes">Notes to Consolidated Financial Statements</a>',
                               '<a href="#notes">Index to Consolidated Financial Statements</a>')
    notes = R.read(html)["notes"]
    assert [n["n"] for n in notes] == [1, 2, 3]


def test_positioned_lines_are_joined_back():
    lines = []
    words = ("We sell our products through distributors and directly to customers in the United States and "
             "abroad, and our results depend on both channels. ").split()
    for i in range(0, len(words) * 6, 9):
        lines.append(" ".join((words * 6)[i:i + 9]))
    body = "".join(f"<div>{t}</div>" for t in lines)
    html = (f"<html><body><div><a href='#rf'>Risk Factors</a></div><div><a href='#a'>Business</a></div>"
            f"<div><a href='#b'>Management</a></div><div><a href='#c'>Experts</a></div>"
            f"<div id='rf'><b>RISK FACTORS</b></div>{body}"
            f"<div><b>Risks Related to Our Business and</b></div><div><b>Industry</b></div>"
            f"<div><b><i>We may not be able to compete successfully against larger companies with more resources.</i></b></div>{body}"
            f"<div id='a'><b>BUSINESS</b></div>{body}<div id='b'><b>MANAGEMENT</b></div>{body}"
            f"<div id='c'><b>EXPERTS</b></div>{body}</body></html>")
    r = R.read(html)
    assert r["lines"] is True
    rf = r["sections"][0]
    # the lines of each block of text are one paragraph again (one before the risk headings, one after)
    assert len(rf["text"]) == 2 and all(t.count("We sell our products") == 6 for t in rf["text"])
    assert [g["group"] for g in r["risks"]["groups"]] == ["Risks Related to Our Business and Industry"]


def test_mdna_comparisons_in_their_usual_wordings():
    def md(*items):
        return [{"text": t, "heading": h} for h, t in items]
    lines = md((True, "Results of Operations For the Six Months ended June 30, 2026 and 2025"),
               (False, "Revenue increased by $2.0 million for the six months ended June 30, 2026."),
               (True, "Year Ended December 31, 2025 as compared to the Year Ended December 31, 2024"),
               (False, "Revenue increased by $3.0 million for the year ended December 31, 2025."),
               (True, "Comparison of the Year ended December 31, 2024 and the 2023 Period"),
               (False, "Revenue increased by $1.0 million in 2024."),
               (True, "Liquidity and Capital Resources"), (False, "We had cash of $5 million."))
    assert [p["text"][:30] for p in R._comparison(lines, 6, "2026-06-30")] == ["Revenue increased by $2.0 mill"]
    assert [p["text"][:30] for p in R._comparison(lines, 12, "2025-12-31")] == ["Revenue increased by $3.0 mill"]
    assert [p["text"][:30] for p in R._comparison(lines, 12, "2024-12-31")] == ["Revenue increased by $1.0 mill"]
    assert R._comparison(lines, 3, "2026-06-30") is None
    both = md((True, "Three and Six Months Ended June 30, 2026 as compared to the Three and Six Months Ended June 30, 2025"),
              (False, "Revenue rose."))
    assert R._comparison(both, 3, "2026-06-30") and R._comparison(both, 6, "2026-06-30")
    assert not R._is_comparison("Liquidity for the six months ended June 30, 2026 and 2025")
