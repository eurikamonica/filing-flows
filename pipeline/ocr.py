"""Earnings releases printed as pictures (Tesla's quarterly update, Genworth's results): the statement pages are read
with Tesseract OCR and rebuilt as plain HTML tables, which pipeline/release.py then reads like any other release.

OCR misreads digits, so nothing read this way is trusted on its own: rebuild() keeps a statement only when its current
column adds up (revenue - cost of revenue = gross profit, pre-tax earnings - tax = net income, where printed), and the
caller (pipeline/build.py) still applies every check of a typed release — units against the previous quarter, one of
the earlier columns equal to what the company already filed in XBRL, and the reconciliation in release.reconcile.

Columns are placed by position: each figure goes to the period heading above it (Q3-2025 … Q3-2026, or 2026 2025),
and the columns are written newest first, which is how the reader expects them."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html import escape

PERIOD = re.compile(r"^(?:Q([1-4])[-–' ]?(?:FY)?(20\d\d|\d\d)|(?:FY|F)?(20\d\d)|([1-4])Q(?:FY)?(20\d\d|\d\d))[,.:]?$", re.I)
NUM = re.compile(r"^[S$]?\(?[S$]?-?\d[\d,]*(?:\.\d+)?\)?%?[,.]?$|^\(?[\d,]+\.?\d*\)?$")
DASH = {"—", "–", "-", "--", "=", "_", "~"}
STATEMENT = re.compile(r"statements? of (consolidated )?(operations|income|earnings)|income statement|statements? of cash flows"
                       r"|results of operations|statements? of comprehensive", re.I)
MAX_PAGES = 45


def available():
    return shutil.which("tesseract") is not None


def ensure():
    """Tesseract, installed on a GitHub runner the first time a release needs it (most runs never do)."""
    if available():
        return True
    if os.environ.get("GITHUB_ACTIONS") == "true" and shutil.which("sudo"):
        try:
            subprocess.run("sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tesseract-ocr",
                           shell=True, timeout=240, check=True, capture_output=True)
        except Exception as e:                               # noqa: BLE001 — no OCR: the release waits for the 10-Q
            print(f"  OCR unavailable: {e}", file=sys.stderr)
    return available()


def _prepare(data, scale, top=None):
    from PIL import Image, ImageOps
    import io
    im = Image.open(io.BytesIO(data)).convert("L")
    if top:
        im = im.crop((0, 0, im.width, int(im.height * top)))
    if scale > 1 and im.width < 3000:
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    im = ImageOps.autocontrast(im)
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    im.save(f.name)
    return f.name


def _tesseract(path, tsv):
    args = ["tesseract", path, "stdout", "--psm", "6"] + (["tsv"] if tsv else [])
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}            # pages run side by side instead
    return subprocess.run(args, capture_output=True, text=True, timeout=180, env=env).stdout


def page_text(data):
    """Quick OCR of the top of a page (original size), where the statement's title is: to find the statement pages."""
    p = _prepare(data, 1, top=0.22)
    try:
        return _tesseract(p, False)
    finally:
        os.unlink(p)


def words(data):
    """Words with their boxes (3x upscaled: digits read far better), grouped into Tesseract's lines."""
    p = _prepare(data, 3)
    try:
        out = _tesseract(p, True)
    finally:
        os.unlink(p)
    lines = {}
    for row in out.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or not f[11].strip():
            continue
        key = (int(f[2]), int(f[3]), int(f[4]))
        left, top, width, height = map(int, f[6:10])
        lines.setdefault(key, []).append({"t": f[11].strip(), "x0": left, "x1": left + width, "y": top + height / 2})
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(lines.items(), key=lambda kv: min(w["y"] for w in kv[1]))]


def _period_key(tok):
    m = PERIOD.match(tok)
    if not m:
        return None
    if m.group(1):
        y = m.group(2)
        return (int(y if len(y) == 4 else "20" + y), int(m.group(1)))
    if m.group(4):
        y = m.group(5)
        return (int(y if len(y) == 4 else "20" + y), int(m.group(4)))
    return (int(m.group(3)), 0)


def _clean_num(tok):
    t = tok.replace("S$", "$").rstrip(",.") if not re.search(r"\.\d", tok) else tok.replace("S$", "$")
    t = t.lstrip("$S")
    if t.startswith("(") and not t.endswith(")"):
        t += ")"
    if t.endswith(")") and not t.startswith("("):
        t = "(" + t
    return t


def table_html(lines):
    """One page's lines → HTML: the lines above the period headings as paragraphs, the rest as one table."""
    head_i = next((i for i, ws in enumerate(lines) if sum(1 for w in ws if _period_key(w["t"])) >= 2), None)
    if head_i is None:
        return None
    head = lines[head_i]
    cols = [w for w in head if _period_key(w["t"])]
    centers = [(w["x0"] + w["x1"]) / 2 for w in cols]
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    tol = (min(gaps) / 2) if gaps else 200
    keys = [_period_key(w["t"]) for w in cols]
    quarters = all(k[1] for k in keys) and len(set(keys)) == len(keys)
    order = sorted(range(len(cols)), key=lambda i: keys[i], reverse=True) if quarters else list(range(len(cols)))
    label = lambda k: f"Q{k[1]} {k[0]}" if k[1] else str(k[0])
    head_label = " ".join(w["t"] for w in head if not _period_key(w["t"]))
    paras = [" ".join(w["t"] for w in ws) for ws in lines[:head_i]]
    rows = [f"<tr><td>{escape(head_label)}</td>" + "".join(f"<td>{label(keys[i])}</td>" for i in order) + "</tr>"]
    for ws in lines[head_i + 1:]:
        if sum(1 for w in ws if _period_key(w["t"])) >= 2:
            break                                            # a second statement on the page: keep the first
        lab, cells = [], [None] * len(cols)
        for w in ws:
            t = w["t"]
            numeric = NUM.match(t) or (t in DASH and lab)
            c = (w["x0"] + w["x1"]) / 2
            j = min(range(len(cols)), key=lambda i: abs(centers[i] - c))
            if numeric and abs(centers[j] - c) <= tol and (lab or t not in DASH):
                if cells[j] is None:
                    cells[j] = "—" if t in DASH else _clean_num(t)
            elif not numeric and all(x is None for x in cells) and t not in ("$", "S$", "S"):
                lab.append(t)
        if not lab:
            continue
        if all(x is None for x in cells):
            rows.append(f"<tr><td>{escape(' '.join(lab))}</td></tr>")       # a section heading ("COST OF REVENUES")
            continue
        if cells[order[0]] is None:
            continue                                         # no current-period figure: the row is not used
        vals = ["—" if cells[i] is None else cells[i] for i in order]
        rows.append(f"<tr><td>{escape(' '.join(lab))}</td>" + "".join(f"<td>{escape(v)}</td>" for v in vals) + "</tr>")
    return "".join(f"<p>{escape(p)}</p>" for p in paras) + "<table>" + "".join(rows) + "</table>"


def adds_up(rel):
    """The current column of an OCR'd statement must add up wherever its totals are printed."""
    i = rel.get("is") or {}
    near = lambda a, b: abs(a - b) <= max(0.002 * abs(b), 1.5 * rel.get("scale", 1))
    if all(i.get(k) is not None for k in ("revenue", "cor", "gp")) and not near(abs(i["revenue"]) - abs(i["cor"]), i["gp"]):
        return False
    net = i.get("pl") if i.get("pl") is not None else i.get("ni")
    if i.get("pretax") is not None and i.get("tax") is not None and net is not None and \
            not any(near(i["pretax"] - s * i["tax"], net) for s in (1, -1)):
        return False
    return True


def images_in(html):
    """The pictures of a release page, in page order (<img src=…>)."""
    return [m.group(1) for m in re.finditer(r"<img[^>]+src=[\"']?([^\"' >]+)", html, re.I)]


def rebuild(html, fetch, intro=""):
    """A release made of pictures → an HTML document of its statement pages (or None). fetch(name) returns the bytes of
    one picture of the filing; intro: the 8-K's own text, which usually names the quarter ("… ended September 30")."""
    names = [n for n in images_in(html) if re.search(r"\.(jpe?g|png|gif)$", n, re.I)][:MAX_PAGES]
    if not names or not ensure():
        return None
    from concurrent.futures import ThreadPoolExecutor

    def one(n):
        try:
            data = fetch(n)
            if not STATEMENT.search(page_text(data)):
                return None
            return table_html(words(data))
        except Exception as e:                               # noqa: BLE001 — one unreadable page: the others may do
            print(f"  OCR skipped {n}: {e}", file=sys.stderr)
            return None
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as pool:
        tables = [t for t in pool.map(one, names) if t]
    parts = ([f"<p>{escape(intro[:3000])}</p>"] if intro else []) + tables
    return "<html><body>" + "".join(parts) + "</body></html>" if tables else None
