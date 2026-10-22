"""EPS guidance from earnings releases (8-K Exhibit 99): "expects fourth-quarter diluted EPS of $1.40 to $1.50",
"raises full-year GAAP EPS guidance to $6.10-$6.30". Fixed rules, no language model; every row keeps its sentence.

    rows: [{"text", "lo", "hi", "mid", "period": "q" | "fy", "quarter": 1-4 | None, "year": 2026 | None,
            "basis": "gaap" | "adjusted" | "unstated"}]

The main scan reads each new release (build.process_release) and keeps the rows in store/eps-guide/<cik>.json;
the EPS model (eps_blend.py) turns a matching row into a GAAP figure for the quarter it forecasts.
"""
import json
import re
from pathlib import Path

MONEY = re.compile(r"\$\s?(\(?-?\d{1,4}(?:\.\d{1,3})?\)?)\s*(?:(?:-|–|—|to|and)\s*\$?\s?(\(?-?\d{1,4}(?:\.\d{1,3})?\)?))?(?!\s*(?:billion|million|thousand|bn|m\b))", re.I)
EPS = re.compile(r"(?i)\b(earnings|income|loss|net income) per (diluted )?share\b|\bEPS\b|\bper diluted share\b")
OUTLOOK = re.compile(r"(?i)\b(expect|expects|expected|anticipat\w*|outlook|guidance|guide|forecast\w*|project\w*|reaffirm\w*|"
                     r"rais\w+|lower\w*|narrow\w*|updat\w+|now sees|sees|target\w*|range)\b")
PAST = re.compile(r"(?i)\b(was|were|compared (to|with)|versus|prior[- ]year|last year|a year ago|increased|decreased|grew|declined)\b")
QWORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def _num(s):
    s = s.strip()
    neg = s.startswith("(") or s.startswith("-")
    v = float(s.strip("()-"))
    return -v if neg else v


def parse(paragraphs):
    """Guidance rows from a release's paragraphs (text.paragraphs output or plain strings)."""
    out = []
    for p in paragraphs:
        p = p.get("text", "") if isinstance(p, dict) else str(p)
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z(])", p):
            if len(sent) > 700 or not EPS.search(sent) or not OUTLOOK.search(sent):
                continue
            m = MONEY.search(sent, EPS.search(sent).start()) or MONEY.search(sent)
            if not m:
                continue
            try:
                lo = _num(m.group(1))
                hi = _num(m.group(2)) if m.group(2) else lo
            except ValueError:
                continue
            if lo > hi:
                lo, hi = hi, lo
            if not (abs(lo) < 1000 and abs(hi) < 1000):
                continue
            head = sent[: m.start()]
            if PAST.search(head) and not OUTLOOK.search(head):
                continue                                         # a reported figure, not an outlook
            low = sent.lower()
            q = re.search(r"\b(first|second|third|fourth)[- ]quarter\b|\bq([1-4])\b", low)
            fy = re.search(r"\b(full[- ]year|fiscal[- ]year|fiscal 20\d\d|full fiscal|annual|for the year|20\d\d (?:full year|outlook|guidance))\b", low)
            period = "q" if q and not (fy and fy.start() < q.start()) else "fy" if fy else ("q" if "quarter" in low else None)
            if not period:
                continue
            yr = re.search(r"\b(?:fiscal |fy\s?)?(20\d\d)\b", low)
            basis = "adjusted" if re.search(r"(?i)non-gaap|adjusted|excluding|core\b|operating eps", sent) else \
                "gaap" if re.search(r"\bGAAP\b", sent) else "unstated"
            out.append({"text": sent.strip()[:500], "lo": lo, "hi": hi, "mid": round((lo + hi) / 2, 4), "period": period,
                        "quarter": QWORD.get((q.group(1) or q.group(2))) if q else None,
                        "year": int(yr.group(1)) if yr else None, "basis": basis})
    seen, rows = set(), []
    for r in out:
        k = (r["period"], r["quarter"], r["basis"], r["lo"], r["hi"])
        if k not in seen:
            seen.add(k)
            rows.append(r)
    return rows[:8]


def keep(root, cik, rows, accn, filed, url, end=None):
    """Add a release's guidance to store/eps-guide/<cik>.json (newest first, at most 12 releases)."""
    if not root:
        return
    path = Path(root) / "eps-guide" / f"{int(cik)}.json"
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {"cik": int(cik), "releases": []}
    rel = [r for r in d.get("releases", []) if r.get("accn") != accn]
    rel.insert(0, {"accn": accn, "filed": filed, "url": url, "period_end": end, "rows": rows})
    d["releases"] = sorted(rel, key=lambda r: r.get("filed") or "", reverse=True)[:12]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
