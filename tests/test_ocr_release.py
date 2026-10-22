"""Releases printed as pictures (pipeline/ocr.py): figures placed under their period headings, newest first, then read
by the release reader; and, where Tesseract is installed, a statement drawn as a picture read end to end."""
import datetime as dt
import io
import shutil

from pipeline import ocr, release


def _line(y, *cells):
    """cells: (text, x_center) — one word each."""
    return [{"t": t, "x0": x - 20, "x1": x + 20, "y": y} for t, x in cells]


HEAD = ("Q3-2025", 600), ("Q4-2025", 700), ("Q1-2026", 800), ("Q2-2026", 900), ("Q3-2026", 1000)


def _rows():
    lines = [_line(10, ("In", 50), ("millions", 120), *HEAD)]
    data = [("Total revenues", [28095, 24901, 22387, 28236, 28046]), ("Total cost of revenues", [23041, 19892, 17667, 23485, 22552]),
            ("Gross profit", [5054, 5009, 4720, 4751, 5494]), ("INCOME FROM OPERATIONS", [1624, 1409, 941, 398, 718]),
            ("INCOME BEFORE INCOME TAXES", [1959, 1181, 748, 1329, 956]), ("Provision for income taxes", [570, 325, 257, 201, 152]),
            ("NET INCOME", [1389, 856, 491, 1128, 804])]
    for k, (lab, vals) in enumerate(data):
        words = [(w, 40 + 60 * i) for i, w in enumerate(lab.split())]
        lines.append(_line(40 + 20 * k, *words, *[(f"{v:,}", x) for v, (_, x) in zip(vals, HEAD)], ("9%", 1100)))
    return lines


def test_columns_newest_first_and_trailing_change_column_dropped():
    html = ("<html><body><p>Results for the quarter ended September 30, 2026</p><p>STATEMENT OF OPERATIONS (Unaudited)</p>"
            + ocr.table_html(_rows()) + "</body></html>")
    r = release.parse(html, dt.date(2026, 10, 22))
    assert r["end"] == "2026-09-30" and r["is_quarter"] is True
    assert r["is"]["revenue"] == 28046e6 and r["is"]["pl"] == 804e6
    assert r["cols"]["revenue"][1] == 28236e6                      # Q2-2026 next: the column the XBRL anchor checks
    assert ocr.adds_up(r)
    r["is"]["gp"] = 5394e6                                          # a misread digit
    assert not ocr.adds_up(r)


def test_period_tokens():
    assert ocr._period_key("Q3-2026") == (2026, 3) and ocr._period_key("3Q26") == (2026, 3) and ocr._period_key("2025") == (2025, 0)
    assert ocr._period_key("1,234") is None


def test_picture_end_to_end():
    if not shutil.which("tesseract"):
        return                                                      # CI runners without Tesseract: the logic is tested above
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    im = Image.new("RGB", (1400, 520), "white")
    d = ImageDraw.Draw(im)
    d.text((40, 20), "STATEMENT OF OPERATIONS (Unaudited)", fill="black", font=font)
    d.text((40, 60), "In millions of USD", fill="black", font=font)
    for (t, x) in HEAD:
        d.text((x + 150, 60), t, fill="black", font=font)
    for k, ws in enumerate(_rows()[1:]):
        lab = " ".join(w["t"] for w in ws if not w["t"][0].isdigit())
        d.text((40, 100 + 50 * k), lab.replace(" 9%", ""), fill="black", font=font)
        for w in ws:
            if w["t"][0].isdigit() and not w["t"].endswith("%"):
                d.text((w["x0"] + 170, 100 + 50 * k), w["t"], fill="black", font=font)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    doc = ocr.rebuild('<img src="p1.png">', lambda n: buf.getvalue(), "results for the quarter ended September 30, 2026")
    assert doc, "no statement found"
    r = release.parse(doc, dt.date(2026, 10, 22))
    assert r["is"]["revenue"] == 28046e6 and r["is"]["pl"] == 804e6 and ocr.adds_up(r)
