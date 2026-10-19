"""build_v3_owner.py - v3 owner-approved data build: Task A (revision_reason) and Task C (bs_line_classification).

No GPU, no training, no model inference, no teacher labels. Downloads only from SEC with the owner-approved
User-Agent, a global limiter (>= 0.125 s between requests, i.e. <= 8 req/s), exponential backoff on 403/429/5xx,
and a hard budget of MAX_REQUESTS HTTP attempts. Task B (MD&A) is deferred and not built.

Usage:  python -I build_v3_owner.py [--run-dir runs/v3-data-<ts>] [--offline]
"""
import argparse
import ast
import hashlib
import html
import json
import random
import re
import shutil
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

LAB = Path(__file__).resolve().parent
UPSTREAM = {"history.py": Path(r"C:/Users/Oliver Hu/AppData/Local/Temp/ff_history.py"),
            "reform.py": Path(r"C:/Users/Oliver Hu/AppData/Local/Temp/ff_reform.py")}
UPSTREAM_PIN = "eurikamonica/filing-flows main @ 04226e2"
UA = "Filing Flows filingflows@gmail.com"
SEED = 20261018
MIN_GAP = 0.125            # seconds between request starts -> at most 8 requests per second overall
MAX_REQUESTS = 3000        # HTTP attempts (retries included); downloading stops at this budget
MAX_RETRIES = 4
EVENTS_PER_COMPANY = 10    # changing filings downloaded per company (bounded effort)
MAX_DOC_BYTES = 40_000_000
TOKEN_LIMIT_A = 900        # prompt + answer, estimated at 4 chars per token
TOKEN_LIMIT_C = 900
CHARS_PER_TOKEN = 4
CAP_PER_TAG_SPLIT = 20     # Task C rows per tag per split
N_HELDOUT_OP, N_HELDOUT_FIN = 7, 6

# Fresh companies (none of the CIKs used by earlier lab runs). All are US 10-K filers.
COMPANIES = [
    (320193, "Apple"), (789019, "Microsoft"), (1652044, "Alphabet"), (1018724, "Amazon"), (1326801, "Meta Platforms"),
    (1045810, "NVIDIA"), (50863, "Intel"), (858877, "Cisco"), (51143, "IBM"), (40545, "General Electric"),
    (12927, "Boeing"), (21344, "Coca-Cola"), (77476, "PepsiCo"), (80424, "Procter & Gamble"),
    (200406, "Johnson & Johnson"), (78003, "Pfizer"), (310158, "Merck"), (104169, "Walmart"), (354950, "Home Depot"),
    (27419, "Target"), (63908, "McDonald's"), (320187, "Nike"), (829224, "Starbucks"), (1744489, "Walt Disney"),
    (732712, "Verizon"), (34088, "Exxon Mobil"), (93410, "Chevron"), (66740, "3M"), (773840, "Honeywell"),
    (18230, "Caterpillar"), (37996, "Ford"), (1467858, "General Motors"), (1318605, "Tesla"), (1637459, "Kraft Heinz"),
    (40704, "General Mills"), (1551152, "AbbVie"), (14272, "Bristol-Myers Squibb"), (59478, "Eli Lilly"),
    (882095, "Gilead"), (64803, "CVS Health"), (1618921, "Walgreens Boots Alliance"), (60667, "Lowe's"),
    (764478, "Best Buy"), (1633917, "PayPal"), (804328, "Qualcomm"), (47217, "HP Inc"),
    (1645590, "Hewlett Packard Enterprise"), (1065280, "Netflix"), (936468, "Lockheed Martin"), (101829, "RTX"),
    (1048911, "FedEx"), (1090727, "UPS"), (764180, "Altria"), (56873, "Kroger"), (1666700, "DuPont"),
    (1375365, "Super Micro Computer"), (1657853, "Hertz Global"), (1336917, "Under Armour"), (108772, "Xerox"),
]

# history.py imports facts.CONCEPTS which we do not have; this is the concept list used here (recorded in manifest).
CONCEPTS = {"revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
            "oi": ["OperatingIncomeLoss"],
            "ni": ["NetIncomeLoss", "ProfitLoss"],
            "ocf": ["NetCashProvidedByUsedInOperatingActivities"]}
TOTAL_FIRST = {"revenue": "Revenues"}   # history.py: "Revenues" first, else the largest revenue tag
MAX_KEYS = {"revenue"}
KEYS = ["revenue", "oi", "ni", "ocf"]
YEARS = 10
MOVE = 0.0005

LABELS = {"results": ["restatement_non_reliance", "error_correction_revision", "accounting_change_retrospective"],
          "presentation": ["discontinued_operations", "segment_recast", "income_statement_reclassification"],
          "cash flow": ["cash_flow_reclassification"],
          "amended": ["amendment_restatement", "amendment_tagging_or_clerical"]}
ABSTAIN = "insufficient_evidence"
ALL_LABELS = [x for g in LABELS.values() for x in g] + [ABSTAIN]

# ----------------------------------------------------------------------------------------------- utilities

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def compact(v):
    return json.dumps(v, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def norm(s):
    """The one documented normalisation: Unicode NFC, all whitespace runs collapsed to one space, stripped."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def d(s):
    return date.fromisoformat(s)


def years_back(s, n):
    x = d(s)
    try:
        return x.replace(year=x.year - n)
    except ValueError:
        return x.replace(year=x.year - n, day=28)


# ----------------------------------------------------------------------------------------------- SEC client

class Sec:
    def __init__(self, src, offline):
        self.src, self.offline = src, offline
        self.count, self.failures, self.last = 0, [], 0.0
        self.log = src / "requests.jsonl"
        self.man_path = src / "manifest.json"
        self.manifest = json.loads(self.man_path.read_text()) if self.man_path.exists() else {"files": []}
        self.by_path = {f["path"]: f for f in self.manifest["files"]}
        if self.log.exists():
            self.count = sum(1 for _ in self.log.open())
        self.consecutive_403 = 0
        self.stopped = None
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})

    def save_manifest(self):
        self.manifest["files"] = sorted(self.by_path.values(), key=lambda f: f["path"])
        self.manifest.update(user_agent=UA, min_gap_seconds=MIN_GAP, request_attempts=self.count,
                             note="Metadata only (url, accession, sha256, bytes, utc). Content stays git-ignored.")
        self.man_path.write_text(json.dumps(self.manifest, indent=1))

    def get(self, url, rel, accession=None):
        """Cached GET. Returns bytes or None."""
        p = self.src / rel
        if p.exists():
            return p.read_bytes()
        if self.offline or self.stopped:
            return None
        delay = 1.0
        for attempt in range(MAX_RETRIES + 1):
            if self.count >= MAX_REQUESTS:
                self.stopped = f"request budget {MAX_REQUESTS} reached"
                return None
            wait = self.last + MIN_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            self.count += 1
            status, err, body = None, None, None
            try:
                r = self.s.get(url, timeout=60)
                status, body = r.status_code, r.content
            except Exception as e:  # network error
                err = repr(e)
            with self.log.open("a") as fh:
                fh.write(json.dumps({"utc": now(), "url": url, "status": status, "attempt": attempt,
                                     "bytes": len(body) if body is not None else None, "error": err}) + "\n")
            if status == 200:
                self.consecutive_403 = 0
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(body)
                self.by_path[rel] = {"path": rel, "url": url, "accession": accession, "sha256": sha(body),
                                     "bytes": len(body), "utc": now()}
                return body
            self.failures.append({"utc": now(), "url": url, "status": status, "attempt": attempt, "error": err})
            if status == 404:
                return None
            if status == 403:
                self.consecutive_403 += 1
                if self.consecutive_403 >= 3:
                    self.stopped = "three consecutive 403 responses; downloading stopped"
                    return None
            if status in (403, 429) or status is None or (status and status >= 500):
                time.sleep(delay)
                delay *= 2
                continue
            return None
        return None


# ----------------------------------------------------------------------------------------------- upstream tables

def parse_lines(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "LINES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("LINES not found in reform.py")


def parse_covers(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "COVERS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("COVERS not found")


# ----------------------------------------------------------------------------------------------- history.py logic

def kind(start, end):
    days = (d(end) - d(start)).days
    return "fy" if 350 <= days <= 380 else "q" if 75 <= days <= 100 else None


def version_index(cf):
    """concept -> {(start, end): [fact, ...]} for duration USD facts (every filing's version kept)."""
    g = cf.get("facts", {}).get("us-gaap", {})
    V = {}
    for c in {c for k in KEYS for c in CONCEPTS[k]}:
        for f in (g.get(c, {}).get("units", {}).get("USD", [])):
            if f.get("start") and f.get("end"):
                V.setdefault(c, {}).setdefault((f["start"], f["end"]), []).append(f)
    return V


def versions(V, key, start, end):
    by = {}
    for c in CONCEPTS[key]:
        for f in (V.get(c) or {}).get((start, end), []):
            by.setdefault(f.get("accn"), {})[c] = f
    out = []
    for accn, cs in by.items():
        if key in TOTAL_FIRST and TOTAL_FIRST[key] in cs:
            c = TOTAL_FIRST[key]
        elif key in MAX_KEYS:
            c = max(cs, key=lambda x: cs[x]["val"])
        else:
            c = next(x for x in CONCEPTS[key] if x in cs)
        f = cs[c]
        out.append((f.get("filed", ""), f.get("form", ""), accn, f["val"], c, f))
    out.sort(key=lambda x: (x[0], x[2] or ""))
    return out


def moved(a, b):
    return a is not None and b is not None and abs(a - b) > max(MOVE * abs(a), 0.5e6)


def pattern(form, keys):
    if form.endswith("/A"):
        return "amended"
    if "ni" in keys:
        return "results"
    if "revenue" in keys or "oi" in keys:
        return "presentation"
    return "cash flow"


def history_events(cf):
    V = version_index(cf)
    ends = [e for c in V for (s, e) in V[c]]
    if not ends:
        return []
    cut = years_back(max(ends), YEARS).isoformat()
    spans = sorted({(s, e) for c in V for (s, e) in V[c] if e >= cut and kind(s, e)}, key=lambda se: (se[1], se[0]))
    changes = {}
    for s, e in spans:
        for k in KEYS:
            last = None
            for filed, form, accn, val, c, f in versions(V, k, s, e):
                if last is None or moved(last, val):
                    if last is not None:
                        changes.setdefault(accn, {"accn": accn, "form": form, "filed": filed, "items": []})["items"].append(
                            [k, s, e, last, val])
                    last = val
    events = []
    for accn, ch in changes.items():
        ch["keys"] = sorted({x[0] for x in ch["items"]}, key=KEYS.index)
        ch["pattern"] = pattern(ch["form"], set(ch["keys"]))
        events.append(ch)
    events.sort(key=lambda x: x["filed"], reverse=True)
    return events


# ----------------------------------------------------------------------------------------------- text extraction

CELL = "\u241e"
BLOCK = re.compile(r"(?i)<(?:br|/?p|/?div|/?tr|/?li|/?h[1-6]|/?table|/?center|/?font\s+size)\b[^>]*>")


def html_paragraphs(raw):
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        s = raw.decode("cp1252", errors="replace")
    s = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", s)
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1\s*>", " ", s)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)</t[dh]\s*>", " " + CELL + " ", s)
    s = BLOCK.sub("\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return [p for p in (norm(x) for x in s.split("\n")) if p]


def is_prose(p):
    if CELL in p or len(p) < 60:
        return False
    letters = sum(ch.isalpha() for ch in p)
    return letters / len(p) > 0.6


ABBR = {"u.s", "inc", "corp", "co", "ltd", "no", "nos", "mr", "ms", "dr", "st", "l.p", "n.a", "vs", "e.g", "i.e",
        "etc", "approx", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "u.k",
        "s.a", "n.v", "plc", "llc", "a.g", "ag", "fig", "sec", "art"}


def sentences(p):
    """[(start, end)] sentence spans of a normalised paragraph."""
    spans, start = [], 0
    for m in re.finditer(r"[.!?][\"\u201d\u2019)]?\s+(?=[A-Z\u201c\"(])", p):
        before = p[start:m.start()].split(" ")[-1].lower().strip("(\"\u201c")
        if before in ABBR or re.fullmatch(r"[a-z]", before) or re.fullmatch(r"(?:[a-z]\.)+[a-z]", before):
            continue
        end = m.start() + len(m.group(0).rstrip())
        spans.append((start, end))
        start = m.end()
    if start < len(p):
        spans.append((start, len(p)))
    return [(a, b) for a, b in spans if p[a:b].strip()]


def has(s, *words):
    return any(w in s for w in words)


PRIOR = ("prior period", "prior-period", "prior year", "prior-year", "previously reported", "previously issued",
         "all periods presented", "for all periods", "comparative", "historical periods", "prior periods")


FORWARD = re.compile(r"\b(will|may|would|could|might|expects?|anticipates?|plans? to|intends? to|evaluating|"
                     r"is permitted|can be|early adoption|either|if|in the event|must be|required to be|is required|"
                     r"are required|should be applied|effective for (?:fiscal|annual|interim|our|the|us)|"
                     r"not yet adopted|currently assessing)\b")
NEGATED = ("not been recast", "not recast", "not been segregated", "not reflected", "not been reflected",
           "were not revised", "not been revised", "not been reclassified", "not reclassified", "not restated",
           "not been restated", "not been adjusted", "not adjusted", "no restatement", "without restat")
POLICY = ("clawback", "claw back", "recoup", "recovery of", "recover ", "incentive compensation", "compensation")


def rule(sentence, group):
    """Deterministic candidate label for one sentence within a pattern group, or None.
    Forward-looking or conditional sentences (new-standard descriptions, policies) and compensation-recovery
    (clawback) text never trigger a label: they do not state why this filing changed reported figures."""
    s = sentence.lower()
    if has(s, *POLICY) or has(s, *NEGATED) or (FORWARD.search(s) and not has(s, "no longer be relied upon")):
        return None
    if group == "amended":
        if has(s, "amended and restated"):          # exhibit / plan / charter titles, not a restatement of figures
            return None
        if has(s, "restate", "restatement") or (has(s, "correct") and has(s, "error") and has(s, "financial statement")):
            return "amendment_restatement"
        if has(s, "xbrl", "interactive data", "typographical", "clerical", "scrivener", "exhibit 101"):
            return "amendment_tagging_or_clerical"
        return None
    if group == "results":
        if has(s, "no longer be relied upon", "non-reliance", "item 4.02"):
            return "restatement_non_reliance"
        if has(s, "revision of previously issued", "immaterial error", "immaterial correction") or \
                (has(s, "error") and has(s, "revised", "revision", "correct", "restate") and has(s, *PRIOR)):
            return "error_correction_revision"
        if has(s, "retrospective") and not has(s, "eliminat") and has(s, "adopted", "adoption of", "asu ", "asu,", "accounting standards update",
                                               "change in accounting principle") \
                and has(s, "adopted", "we adopt", "company adopt", "have been", "has been", "were ", "was ",
                        "recast", "adjusted", "revised", "reclassified", "restated") \
                and not has(s, "no restatement", "not restated", "not been restated", "not been adjusted",
                            "not adjusted", "without restat", "not recast") \
                and (not has(s, "modified retrospective") or has(s, "recast", "revised", "retrospectively adjusted")):
            return "accounting_change_retrospective"
        if has(s, "change in accounting principle") and has(s, *PRIOR):
            return "accounting_change_retrospective"
        return None
    if group == "presentation":
        if has(s, "discontinued operation") and has(s, "recast", "reclassified", "retrospectively", "have been revised",
                                                     "presented as discontinued", "reflected as discontinued",
                                                     "reported as discontinued", "reported in discontinued",
                                                     "presented in discontinued", "reflected in discontinued", *PRIOR):
            return "discontinued_operations"
        if has(s, "segment information", "segment data", "segment results", "reportable segment", "segment presentation",
               "segment reporting", "operating segment", "segment structure", "segment financial", "new segment",
               "segment realignment", "segment reorganization", "segment change") and has(s, "recast", "retrospectively", "realign", "reorganiz", "restated", "revised",
                                       "reclassified") \
                and has(s, *PRIOR, "recast", "retrospectively"):
            return "segment_recast"
        if has(s, "reclassif") and has(s, "conform to the current", "conform with the current", "current period presentation",
                                       "current year presentation", "current-year presentation",
                                       "current-period presentation", "current year's presentation",
                                       "current period's presentation") \
                and not has(s, "cash flow", "operating activities", "investing activities", "financing activities",
                            "balance sheet"):
            return "income_statement_reclassification"
        return None
    if group == "cash flow":
        if has(s, "reclassif", "revised", "recast") and has(s, "statement of cash flows", "statements of cash flows",
                                                              "cash flow statement", "operating activities",
                                                              "investing activities", "financing activities")                 and not has(s, "hedg", "other comprehensive"):
            return "cash_flow_reclassification"
        return None
    return None


def any_rule(sentence):
    return any(rule(sentence, g) for g in LABELS)


def find_passage(paras, group, budget):
    """First (paragraph-order) prose paragraph whose sentence triggers a rule of the group, label priority order.
    Returns (label, passage, quote, para_index) or None. Whole paragraphs only; a short heading paragraph
    directly above is kept as context when it fits."""
    hits = {}
    for i, p in enumerate(paras):
        if not is_prose(p) or len(p) > budget:
            continue
        for a, b in sentences(p):
            q = p[a:b]
            if len(q) > 700:
                continue
            lab = rule(q, group)
            if lab and lab not in hits:
                hits[lab] = (i, q)
    for lab in LABELS[group]:
        if lab in hits:
            i, q = hits[lab]
            passage = paras[i]
            if i > 0 and len(paras[i - 1]) <= 120 and not is_prose(paras[i - 1]) and CELL not in paras[i - 1] \
                    and len(paras[i - 1]) + 1 + len(passage) <= budget:
                passage = paras[i - 1] + "\n" + passage
            return lab, passage, q, i
    return None


def abstain_passage(paras, group, budget):
    """A passage that is about the presentation/amendment but where no rule fires (abstention)."""
    keys = ("this amendment", "amendment no.") if group == "amended" else \
        ("basis of presentation", "principles of consolidation", "use of estimates")
    for i, p in enumerate(paras):
        if not is_prose(p) or len(p) > budget:
            continue
        low = p.lower()
        if has(low, *keys) and not any(any_rule(p[a:b]) for a, b in sentences(p)):
            return p, i
    return None


# ----------------------------------------------------------------------------------------------- rows

def contract(types, extra):
    return ("Return only one JSON object with these fields and types: " + compact(types) + ". " + extra +
            " No Markdown, no other text.")


A_TYPES = {"pattern": "string", "label": "string", "quote": "string or null", "source_id": "string"}
A_RULES = ('pattern is one of "amended", "results", "presentation", "cash flow", read from the change: "amended" '
           'if the form ends in /A; otherwise "results" if ni changed; otherwise "presentation" if revenue or oi '
           'changed; otherwise "cash flow". label must belong to the pattern\'s group or be "insufficient_evidence". '
           'Groups: results = restatement_non_reliance, error_correction_revision, accounting_change_retrospective; '
           'presentation = discontinued_operations, segment_recast, income_statement_reclassification; '
           'cash flow = cash_flow_reclassification; amended = amendment_restatement, amendment_tagging_or_clerical. '
           'quote is the sentence copied verbatim from Evidence S1 that states the reason, or null when label is '
           '"insufficient_evidence". Copy source_id S1.')

C_TYPES = {"cls": "string", "tag": "string"}
C_RULES = ('cls is "op" (operating) or "fin" (financing) in the Nissim-Penman reformulated balance sheet. '
           'tag is the line\'s us-gaap tag copied exactly from Evidence S1, including the "us-gaap:" prefix.')


def fmt_money(v):
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def build_a_input(ev, passage, src_desc):
    items = ev["items"][:3]
    ch = "; ".join(f"{k} for {s}..{e}: {fmt_money(a)} -> {fmt_money(b)} USD" for k, s, e, a, b in items)
    more = len(ev["items"]) - len(items)
    if more > 0:
        ch += f"; and {more} more change(s)"
    return (contract(A_TYPES, A_RULES) +
            f"\nChange: filing form {ev['form']}, filed {ev['filed']}; changed figures: {', '.join(ev['keys'])}. {ch}." +
            f"\nEvidence S1 ({src_desc}):\n{passage}" +
            "\nRequest: State why this filing changed previously reported figures.")


def evidence_of(inp):
    return inp.split("\nEvidence S1", 1)[1].split("\nRequest:", 1)[0]


# ----------------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    if args.run_dir:
        run = Path(args.run_dir).resolve()
    else:
        run = LAB / "runs" / ("v3-data-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    src = run / "sources"
    src.mkdir(parents=True, exist_ok=True)
    (run / "sealed").mkdir(exist_ok=True)
    (run / "upstream").mkdir(exist_ok=True)
    print("run dir:", run)

    # --- 0. pinned upstream copies
    upstream = {}
    for name, p in UPSTREAM.items():
        b = p.read_bytes()
        (run / "upstream" / name).write_bytes(b)
        upstream[name] = {"source": str(p), "pin": UPSTREAM_PIN, "sha256": sha(b), "bytes": len(b)}
    shutil.copy2(Path(__file__), run / "build_v3_owner.py")

    # --- 1. LINES table and held-out tags (before any row is built)
    lines = parse_lines(run / "upstream" / "reform.py")
    covers = parse_covers(run / "upstream" / "reform.py")
    tag_cls, tag_line = {}, {}
    for key, side, name, cls, why, groups in lines:
        for g in groups:
            for t in g:
                if t in tag_cls:
                    raise SystemExit(f"duplicate tag {t}")
                tag_cls[t], tag_line[t] = cls, key
    n_op = sum(c == "op" for c in tag_cls.values())
    n_fin = sum(c == "fin" for c in tag_cls.values())
    if len(lines) != 27 or len(tag_cls) != 66:
        raise SystemExit(f"LINES parse mismatch: {len(lines)} lines, {len(tag_cls)} tags")
    hp = run / "heldout-tags.json"
    if hp.exists():
        heldout = json.loads(hp.read_text())["heldout_tags"]
    else:
        rng = random.Random(SEED)
        ops = sorted(t for t, c in tag_cls.items() if c == "op")
        fins = sorted(t for t, c in tag_cls.items() if c == "fin")
        heldout = sorted(rng.sample(ops, N_HELDOUT_OP) + rng.sample(fins, N_HELDOUT_FIN))
        line_tags = defaultdict(list)
        for t, k in tag_line.items():
            line_tags[k].append(t)
        unseen_lines = sorted(k for k, ts in line_tags.items() if all(t in heldout for t in ts))
        hp.write_text(json.dumps({"seed": SEED, "method": "random.Random(seed).sample over sorted op tags (7) then sorted fin tags (6)",
                                  "written_utc": now(), "tag_counts": {"total": 66, "op": n_op, "fin": n_fin},
                                  "heldout_tags": heldout,
                                  "heldout_detail": [{"tag": t, "cls": tag_cls[t], "line": tag_line[t]} for t in heldout],
                                  "lines_fully_heldout": unseen_lines}, indent=1))
    heldout = set(heldout)

    # --- 2. company split (before any row is built)
    sp = run / "split-membership.json"
    if sp.exists():
        split_of = {k: v for k, v in json.loads(sp.read_text())["company_split"].items()}
    else:
        ids = [f"cik-{c}" for c, _ in sorted(COMPANIES)]
        rng = random.Random(SEED)
        rng.shuffle(ids)
        n = len(ids)
        n_tr, n_dev = round(n * 0.70), round(n * 0.15)
        split_of = {c: ("train" if i < n_tr else "dev" if i < n_tr + n_dev else "sealed_test") for i, c in enumerate(ids)}
        sp.write_text(json.dumps({"seed": SEED, "method": "sorted CIKs shuffled with random.Random(seed); 70/15/15",
                                  "written_utc": now(), "counts": Counter(split_of.values()),
                                  "company_split": dict(sorted(split_of.items()))}, indent=1))
    names = {f"cik-{c}": n for c, n in COMPANIES}

    # --- 3. companyfacts + submissions
    sec = Sec(src, args.offline)
    cfs, subs = {}, {}
    for cik, nm in COMPANIES:
        cid = f"cik-{cik}"
        b = sec.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", f"companyfacts/CIK{cik:010d}.json")
        if b:
            cfs[cid] = (json.loads(b), sha(b), f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        b = sec.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", f"submissions/CIK{cik:010d}.json")
        if b:
            subs[cid] = json.loads(b)
    sec.save_manifest()

    def filing_table(cid, need_before=None):
        """accession -> {form, filed, doc, items}; loads older submission pages if the recent block does not reach."""
        s = subs.get(cid)
        if not s:
            return {}
        out = {}

        def add(block):
            for i, a in enumerate(block.get("accessionNumber", [])):
                out[a] = {"form": block["form"][i], "filed": block["filingDate"][i],
                          "doc": block["primaryDocument"][i], "items": block.get("items", [""] * len(block["form"]))[i]}
        add(s["filings"]["recent"])
        if need_before:
            oldest = min((v["filed"] for v in out.values()), default="9999")
            if oldest > need_before:
                for f in s["filings"].get("files", []):
                    if f.get("filingTo", "") >= need_before:
                        b = sec.get("https://data.sec.gov/submissions/" + f["name"], "submissions/" + f["name"])
                        if b:
                            add(json.loads(b))
        return out

    # --- 4. Task A events and documents
    a_rows, a_excl = [], Counter()
    event_log = []
    budget_chars = TOKEN_LIMIT_A * CHARS_PER_TOKEN
    rank = {"amended": 0, "results": 1, "cash flow": 2, "presentation": 3}
    for cik, nm in COMPANIES:
        cid = f"cik-{cik}"
        if cid not in cfs:
            a_excl["no_companyfacts"] += 1
            continue
        evs = history_events(cfs[cid][0])
        for e in evs:
            event_log.append({"company_id": cid, "accn": e["accn"], "form": e["form"], "filed": e["filed"],
                              "keys": e["keys"], "pattern": e["pattern"], "n_items": len(e["items"])})
        chosen = sorted(evs, key=lambda e: (rank[e["pattern"]], e["filed"]), reverse=False)
        # within rank: most recent first
        chosen = sorted(chosen, key=lambda e: (rank[e["pattern"]], "".join(chr(255 - ord(ch)) for ch in e["filed"])))
        chosen = chosen[:EVENTS_PER_COMPANY]
        if not chosen:
            continue
        oldest = min(e["filed"] for e in chosen)
        table = filing_table(cid, need_before=(d(oldest) - timedelta(days=200)).isoformat())
        for e in chosen:
            grp = e["pattern"]
            meta = table.get(e["accn"])
            if not meta:
                a_excl["accession_not_in_submissions"] += 1
                continue
            docs = []
            # 8-K Item 4.02 around a results event
            if grp == "results":
                lo, hi = (d(e["filed"]) - timedelta(days=180)).isoformat(), (d(e["filed"]) + timedelta(days=30)).isoformat()
                for a, m in sorted(table.items(), key=lambda x: x[1]["filed"]):
                    if m["form"].startswith("8-K") and "4.02" in (m["items"] or "") and lo <= m["filed"] <= hi:
                        docs.append((a, m))
                        break
            docs.append((e["accn"], meta))
            found = None
            for accn, m in docs:
                if not m["doc"]:
                    continue
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{m['doc']}"
                rel = f"filings/{cik}/{accn}/{m['doc']}"
                raw = sec.get(url, rel, accession=accn)
                if raw is None:
                    a_excl["document_download_failed_or_skipped"] += 1
                    continue
                if len(raw) > MAX_DOC_BYTES:
                    a_excl["document_too_large"] += 1
                    continue
                paras = html_paragraphs(raw)
                desc = f"{m['form']} accession {accn}, document {m['doc']}"
                alias = {"accession": accn, "form": m["form"], "url": url, "sha256": sha(raw), "document": m["doc"],
                         "filed": m["filed"]}
                for limit in (2400, 1800, 1200, 800):
                    hit = find_passage(paras, grp, limit)
                    if not hit:
                        break
                    lab, passage, quote, pi = hit
                    out = {"pattern": grp, "label": lab, "quote": quote, "source_id": "S1"}
                    inp = build_a_input(e, passage, desc)
                    if len(inp) + len(compact(out)) <= budget_chars:
                        found = (out, inp, alias, pi, passage)
                        break
                if found:
                    break
            if not found:
                # abstention: a presentation/amendment passage of the changing filing with no stated reason
                accn, m = docs[-1]
                rel = f"filings/{cik}/{accn}/{m['doc']}"
                p = src / rel
                if m["doc"] and p.exists() and p.stat().st_size <= MAX_DOC_BYTES:
                    raw = p.read_bytes()
                    paras = html_paragraphs(raw)
                    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{m['doc']}"
                    alias = {"accession": accn, "form": m["form"], "url": url, "sha256": sha(raw), "document": m["doc"],
                             "filed": m["filed"]}
                    desc = f"{m['form']} accession {accn}, document {m['doc']}"
                    for limit in (2400, 1800, 1200, 800):
                        ab = abstain_passage(paras, grp, limit)
                        if not ab:
                            break
                        passage, pi = ab
                        out = {"pattern": grp, "label": ABSTAIN, "quote": None, "source_id": "S1"}
                        inp = build_a_input(e, passage, desc)
                        if len(inp) + len(compact(out)) <= budget_chars:
                            found = (out, inp, alias, pi, passage)
                            break
            if not found:
                a_excl["no_usable_passage"] += 1
                continue
            out, inp, alias, pi, passage = found
            alias = dict(alias, paragraph_index=pi, passage_chars=len(passage))
            a_rows.append({"split": split_of[cid], "company_id": cid, "document_id": e["accn"], "task": "revision_reason",
                           "input": inp, "output": compact(out), "expected": out, "label_kind": "rule_derived",
                           "review": "not_human_reviewed", "source_aliases": {"S1": alias},
                           "event": {"accn": e["accn"], "form": e["form"], "filed": e["filed"], "keys": e["keys"],
                                     "pattern": e["pattern"], "items": e["items"]},
                           "measured_chars": {"input": len(inp), "output": len(compact(out)), "passage": len(passage)},
                           "est_tokens": (len(inp) + len(compact(out))) // CHARS_PER_TOKEN})
        sec.save_manifest()

    # --- 5. Task C balance-sheet rows
    c_rows_all, c_excl = [], Counter()
    for cik, nm in COMPANIES:
        cid = f"cik-{cik}"
        if cid not in cfs:
            c_excl["no_companyfacts"] += 1
            continue
        cf, cf_sha, cf_url = cfs[cid]
        g = cf.get("facts", {}).get("us-gaap", {})
        assets = [f for f in g.get("Assets", {}).get("units", {}).get("USD", []) if f.get("form") == "10-K" and not f.get("start")]
        if not assets:
            c_excl["no_10k_assets"] += 1
            continue
        end = max(f["end"] for f in assets)
        accn = max((f for f in assets if f["end"] == end), key=lambda f: f.get("filed", ""))["accn"]
        filed = max(f.get("filed", "") for f in assets if f["accn"] == accn)

        def val(tag):
            for f in g.get(tag, {}).get("units", {}).get("USD", []):
                if f.get("accn") == accn and f.get("end") == end and not f.get("start"):
                    return f["val"]
            return None

        present, skipped = [], set()
        for key, side, name, cls, why, groups in lines:
            if key in skipped:
                continue
            tot, used = None, []
            for grp_ in groups:
                for t in grp_:
                    v = val(t)
                    if v is not None:
                        tot = (tot or 0) + v
                        used.append((t, v))
                        skipped |= covers.get(t, set())
                        break
                if used and used[-1][0] == "DebtCurrent":
                    break
            if key == "ltd" and tot is None and val("LongTermDebt") is not None:
                c_excl["ltd_only_total_LongTermDebt_not_in_66"] += 1
                skipped.add("ltdc")
            if tot:  # reform.py keeps a line only when a value is non-zero
                for t, v in used:
                    present.append({"key": key, "side": side, "tag": t, "cls": cls, "val": v,
                                    "label": g.get(t, {}).get("label") or t})
        if "ltdc" in skipped:
            present = [x for x in present if x["key"] != "ltdc"]
        totals = [(lab, val(t)) for lab, t in (("Total assets", "Assets"), ("Total liabilities", "Liabilities"))]
        alias = {"accession": accn, "form": "10-K", "filed": filed, "period_end": end, "url": cf_url,
                 "sha256": cf_sha, "filing_index": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/",
                 "note": "Values from SEC companyfacts for this accession; sha256 is of the companyfacts JSON."}
        split = split_of[cid]
        for i, x in enumerate(present):
            others = [(abs(j - i), j, y) for j, y in enumerate(present) if j != i
                      and not (split == "train" and y["tag"] in heldout)]
            nb = [y for _, j, y in sorted(others)[:5]]
            nb = sorted(nb, key=lambda y: present.index(y))
            nb_lines = [f"- {'asset' if y['side'] == 'a' else 'liability'} | {y['label']} | {fmt_money(y['val'])}" for y in nb]
            for lab, v in totals:
                if v is not None and len(nb_lines) < 6:
                    nb_lines.append(f"- total | {lab} | {fmt_money(v)}")
            if len(nb_lines) < 3:
                c_excl["fewer_than_3_neighbours"] += 1
                continue
            inp = (contract(C_TYPES, C_RULES) +
                   f"\nEvidence S1 (10-K balance sheet, accession {accn}, period end {end}, USD):" +
                   f"\nLine: label \"{x['label']}\"; tag us-gaap:{x['tag']}; side {'asset' if x['side'] == 'a' else 'liability'}; value {fmt_money(x['val'])}" +
                   "\nNeighbouring lines:\n" + "\n".join(nb_lines) +
                   "\nRequest: Classify this balance-sheet line as operating or financing.")
            out = {"cls": x["cls"], "tag": "us-gaap:" + x["tag"]}
            c_rows_all.append({"split": split, "company_id": cid, "document_id": accn, "task": "bs_line_classification",
                               "input": inp, "output": compact(out), "expected": out, "label_kind": "table_default",
                               "review": "not_human_reviewed", "source_aliases": {"S1": alias},
                               "line_key": x["key"], "heldout_tag": x["tag"] in heldout,
                               "est_tokens": (len(inp) + len(compact(out))) // CHARS_PER_TOKEN})

    # held-out tags never in train; per tag per split cap
    c_rows = []
    for r in c_rows_all:
        if r["split"] == "train" and r["heldout_tag"]:
            c_excl["heldout_tag_in_train_company_dropped"] += 1
            continue
        if r["est_tokens"] > TOKEN_LIMIT_C:
            c_excl["over_token_limit"] += 1
            continue
        c_rows.append(r)
    by_ts = defaultdict(list)
    for r in c_rows:
        by_ts[(r["expected"]["tag"], r["split"])].append(r)
    kept = []
    for (tag, split), rs in sorted(by_ts.items()):
        if len(rs) > CAP_PER_TAG_SPLIT:
            rng = random.Random(f"{SEED}:{tag}:{split}")
            c_excl["over_tag_split_cap"] += len(rs) - CAP_PER_TAG_SPLIT
            rs = rng.sample(rs, CAP_PER_TAG_SPLIT)
        kept += rs
    c_rows = kept
    train_tags = {r["expected"]["tag"] for r in c_rows if r["split"] == "train"}
    train_lines = {r["line_key"] for r in c_rows if r["split"] == "train"}
    for r in c_rows:
        r["tag_seen_in_train"] = r["expected"]["tag"] in train_tags
        r["eval_group"] = ("seen_tag" if r["tag_seen_in_train"] else
                           "heldout_tag_seen_line" if r["line_key"] in train_lines else "heldout_tag_unseen_line")

    # --- 6. ids, files
    order = {"train": 0, "dev": 1, "sealed_test": 2}
    rows = sorted(a_rows, key=lambda r: (order[r["split"]], r["company_id"], r["document_id"])) + \
        sorted(c_rows, key=lambda r: (order[r["split"]], r["company_id"], r["expected"]["tag"]))
    counters = Counter()
    for r in rows:
        t = "A" if r["task"] == "revision_reason" else "C"
        counters[(t, r["split"])] += 1
        r["id"] = f"v3o-{t}-{r['split']}-{counters[(t, r['split'])]:05d}"
    field_order = ["id", "split", "company_id", "document_id", "task", "input", "output", "expected", "label_kind",
                   "review", "source_aliases", "tag_seen_in_train"]
    rows = [{**{k: r[k] for k in field_order if k in r}, **{k: v for k, v in r.items() if k not in field_order}} for r in rows]
    files = {"train": run / "train.jsonl", "dev": run / "dev.jsonl", "sealed_test": run / "sealed" / "test.jsonl"}
    for split, p in files.items():
        with p.open("w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                if r["split"] == split:
                    fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    # dev protocol: up to 3 per label (A); ~40 C rows mixing seen and held-out tags
    proto = []
    dev_a = [r for r in rows if r["split"] == "dev" and r["task"] == "revision_reason"]
    for lab in ALL_LABELS:
        proto += [r for r in dev_a if r["expected"]["label"] == lab][:3]
    dev_c = [r for r in rows if r["split"] == "dev" and r["task"] == "bs_line_classification"]
    rng = random.Random(SEED)
    held = [r for r in dev_c if not r["tag_seen_in_train"]]
    seen = [r for r in dev_c if r["tag_seen_in_train"]]
    pick_h = rng.sample(held, min(20, len(held)))
    pick_s = rng.sample(seen, min(40 - len(pick_h), len(seen)))
    proto += sorted(pick_h + pick_s, key=lambda r: r["id"])
    with (run / "dev-protocol.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in proto:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")

    # --- 7. checks
    checks, fails = {}, []

    def check(name, ok, detail=None):
        checks[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            fails.append(name)

    loaded = {s: [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] for s, p in files.items()}
    for key in ("company_id", "document_id", "input"):
        sets = {s: {r[key] for r in rs} for s, rs in loaded.items()}
        ov = {f"{a}&{b}": len(sets[a] & sets[b]) for a, b in (("train", "dev"), ("train", "sealed_test"), ("dev", "sealed_test"))}
        check(f"no_{key}_overlap_across_splits", all(v == 0 for v in ov.values()), ov)
    tr = loaded["train"]
    bad = [r["id"] for r in tr if r["task"] == "bs_line_classification" and r["expected"]["tag"][8:] in heldout]
    leak = [r["id"] for r in tr if any(("us-gaap:" + t) in r["input"] for t in heldout)]
    check("heldout_tags_absent_from_train", not bad and not leak, {"expected_tag": bad[:5], "input_mentions": leak[:5]})
    allr = [r for rs in loaded.values() for r in rs]
    qbad, pbad, jbad, sbad, lbad, kbad = [], [], [], [], [], []
    for r in allr:
        try:
            o = json.loads(r["output"])
            if o != r["expected"]:
                jbad.append(r["id"])
        except Exception:
            jbad.append(r["id"])
            continue
        if split_of[r["company_id"]] != r["split"]:
            sbad.append(r["id"])
        if r["review"] != "not_human_reviewed":
            kbad.append(r["id"])
        if r["task"] == "revision_reason":
            if set(o) != set(A_TYPES) or o["source_id"] != "S1" or r["label_kind"] != "rule_derived":
                jbad.append(r["id"])
            lab, pat = o["label"], o["pattern"]
            if pat != r["event"]["pattern"] or not (lab == ABSTAIN or lab in LABELS.get(pat, [])):
                pbad.append(r["id"])
            if lab == ABSTAIN:
                if o["quote"] is not None:
                    qbad.append(r["id"])
            elif not o["quote"] or norm(o["quote"]) not in norm(evidence_of(r["input"])):
                qbad.append(r["id"])
            if r["est_tokens"] > TOKEN_LIMIT_A:
                lbad.append(r["id"])
        else:
            if set(o) != set(C_TYPES) or o["cls"] not in ("op", "fin") or tag_cls.get(o["tag"][8:]) != o["cls"]:
                jbad.append(r["id"])
            if f"tag {o['tag']};" not in r["input"]:
                jbad.append(r["id"])
            if r["est_tokens"] > TOKEN_LIMIT_C:
                lbad.append(r["id"])
    check("gold_quotes_verbatim_substring_of_evidence", not qbad, qbad[:10])
    check("pattern_group_consistency", not pbad, pbad[:10])
    check("outputs_valid_json_matching_expected_and_contract", not jbad, jbad[:10])
    check("rows_in_assigned_company_split", not sbad, sbad[:10])
    check("length_within_token_limit", not lbad, lbad[:10])
    check("no_row_marked_human_reviewed", not kbad, kbad[:10])
    check("no_oth_or_extension_tags", all(r["expected"]["tag"].startswith("us-gaap:") and r["expected"]["tag"][8:] in tag_cls
                                          for r in allr if r["task"] == "bs_line_classification"))
    check("unique_ids", len({r["id"] for r in allr}) == len(allr))
    check("request_budget_respected", sec.count <= MAX_REQUESTS, sec.count)
    (run / "checks.json").write_text(json.dumps({"utc": now(), "all_ok": not fails, "failed": fails, "checks": checks}, indent=1))

    # --- 8. manifest
    def cnt(fn):
        return dict(sorted(Counter(fn(r) for r in allr if fn(r) is not None).items()))
    file_hash = {str(p.relative_to(run)).replace("\\", "/"): sha(p.read_bytes()) for p in
                 list(files.values()) + [run / "dev-protocol.jsonl", hp, sp, run / "build_v3_owner.py"]}
    sec.save_manifest()
    man = {
        "created_utc": now(), "run_dir": str(run), "seed": SEED, "upstream": upstream,
        "builder": "build_v3_owner.py", "tasks_built": ["revision_reason (A)", "bs_line_classification (C)"],
        "tasks_deferred": ["mdna_driver_amount (B)"],
        "companies": {f"cik-{c}": {"name": n, "split": split_of[f"cik-{c}"],
                                   "companyfacts": f"cik-{c}" in cfs, "submissions": f"cik-{c}" in subs,
                                   "entity_name": cfs.get(f"cik-{c}", ({},))[0].get("entityName")} for c, n in COMPANIES},
        "history_reimplementation": {"concepts": CONCEPTS, "total_first": TOTAL_FIRST, "max_keys": sorted(MAX_KEYS),
                                     "years": YEARS, "move": MOVE, "abs_floor_usd": 0.5e6,
                                     "events_per_company_cap": EVENTS_PER_COMPANY,
                                     "event_priority": "amended, results, cash flow, presentation; newest first"},
        "events_detected": {"total": len(event_log), "by_pattern": dict(Counter(e["pattern"] for e in event_log)),
                            "by_form": dict(Counter(e["form"] for e in event_log))},
        "counts": {"rows_by_split_task": {f"{s}/{t}": n for (s, t), n in sorted(Counter((r["split"], r["task"]) for r in allr).items())},
                   "A_label_by_split": {f"{s}/{l}": n for (s, l), n in sorted(Counter((r["split"], r["expected"]["label"]) for r in allr if r["task"] == "revision_reason").items())},
                   "A_label": cnt(lambda r: r["expected"]["label"] if r["task"] == "revision_reason" else None),
                   "A_pattern": cnt(lambda r: r["expected"]["pattern"] if r["task"] == "revision_reason" else None),
                   "A_source_form": cnt(lambda r: r["source_aliases"]["S1"]["form"] if r["task"] == "revision_reason" else None),
                   "C_cls_by_split": {f"{s}/{c}": n for (s, c), n in sorted(Counter((r["split"], r["expected"]["cls"]) for r in allr if r["task"] == "bs_line_classification").items())},
                   "C_tag_by_split": {f"{t}|{s}": n for (t, s), n in sorted(Counter((r["expected"]["tag"], r["split"]) for r in allr if r["task"] == "bs_line_classification").items())},
                   "C_eval_group_by_split": {f"{s}/{g}": n for (s, g), n in sorted(Counter((r["split"], r["eval_group"]) for r in allr if r["task"] == "bs_line_classification").items())},
                   "dev_protocol": dict(Counter(r["task"] for r in proto)),
                   "A_exclusions": dict(a_excl), "C_exclusions": dict(c_excl)},
        "C_tags_never_observed": sorted(t for t in tag_cls if not any(r["task"] == "bs_line_classification" and r["expected"]["tag"] == "us-gaap:" + t for r in allr)),
        "length": {"chars_per_token_estimate": CHARS_PER_TOKEN, "limit_A": TOKEN_LIMIT_A, "limit_C": TOKEN_LIMIT_C,
                   "A_max_est_tokens": max((r["est_tokens"] for r in allr if r["task"] == "revision_reason"), default=None),
                   "A_passage_chars_max": max((r["measured_chars"]["passage"] for r in allr if r["task"] == "revision_reason"), default=None),
                   "C_max_est_tokens": max((r["est_tokens"] for r in allr if r["task"] == "bs_line_classification"), default=None)},
        "sha256": file_hash,
        "sec": {"user_agent": UA, "min_gap_seconds": MIN_GAP, "max_requests": MAX_REQUESTS,
                "request_attempts_total": sec.count, "stopped": sec.stopped,
                "failures_this_invocation": sec.failures,
                "failures_logged_total": sum(1 for x in (src / "requests.jsonl").read_text().splitlines() if json.loads(x)["status"] != 200) if (src / "requests.jsonl").exists() else 0,
                "status_counts": dict(Counter(json.loads(x)["status"] for x in (src / "requests.jsonl").read_text().splitlines())) if (src / "requests.jsonl").exists() else {}},
        "checks_all_ok": not fails,
    }
    (run / "events.json").write_text(json.dumps(event_log, indent=0))
    (run / "manifest.json").write_text(json.dumps(man, indent=1, default=str))
    print(json.dumps({"checks_ok": not fails, "failed": fails, "counts": man["counts"]["rows_by_split_task"],
                      "A_label": man["counts"]["A_label"], "sec": {k: man["sec"][k] for k in ("request_attempts_total", "stopped", "status_counts")}}, indent=1))
    if fails:
        raise SystemExit("CHECKS FAILED: " + ", ".join(fails))


if __name__ == "__main__":
    main()
