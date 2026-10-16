"""As Known Then: every version of a company's headline figures, as each filing reported them — the company page's
"Revisions" tab.

SEC company facts keep a fact for every filing that reported it: the 10-Q that first gave a quarter, the next year's
10-Q that repeated it as a comparative, the 10-K, an amendment (10-K/A), an 8-K that recast earlier years. The rest of
the site uses the latest version; here all of them are kept, so the page can show the figures as known on any day,
and which filing changed what.

For each filing that changed figures it had not first reported, the pattern of the change is read from the numbers:
  amended       the filing is an amendment (10-K/A, 10-Q/A)
  results       net income changed: a restatement, a correction of an error, or an accounting change applied to
                earlier years (a new standard adopted retrospectively)
  presentation  revenue or operating income moved but net income did not: a reclassification, usually discontinued
                operations taken out of continuing results or a recast of segments
  cash flow     only operating cash flow changed: a reclassification within the cash-flow statement
The reason itself is in the filing's text (the explanatory note of a 10-K/A, an 8-K Item 4.02, the basis-of-
presentation note): each change carries an empty "why" for it, to be filled from the filing.
"""
from . import facts as F

KEYS = ["revenue", "oi", "ni", "ocf"]
CONCEPTS = {c for k in KEYS for c in F.CONCEPTS[k]}       # the facts index keeps every version of these (facts.py)
YEARS = 10                                                 # periods ending in the last ten years
MOVE = 0.0005                                              # a change under 0.05% (or $0.5M) is rounding, not a revision


def _kind(start, end):
    days = (F.d(end) - F.d(start)).days
    return "fy" if 350 <= days <= 380 else "q" if 75 <= days <= 100 else None


def versions(fx, key, start, end):
    """[(filed, form, accn, value, concept, fact)] of the figure for one period as each filing reported it, oldest first.
    Within one filing the tag is chosen as for the rest of the site (facts._pick): "Revenues" first, else the largest
    revenue tag; the first candidate for the other figures."""
    V = fx.get("__versions__") or {}
    by = {}
    for c in F.CONCEPTS[key]:
        for f in (V.get(c) or {}).get((start, end), []):
            by.setdefault(f.get("accn"), {})[c] = f
    out = []
    for accn, cs in by.items():
        if key in F.TOTAL_FIRST and F.TOTAL_FIRST[key] in cs:
            c = F.TOTAL_FIRST[key]
        elif key in F.MAX_KEYS:
            c = max(cs, key=lambda x: cs[x]["val"])
        else:
            c = next(x for x in F.CONCEPTS[key] if x in cs)
        f = cs[c]
        out.append((f.get("filed", ""), f.get("form", ""), accn, f["val"], c, f))
    out.sort(key=lambda x: (x[0], x[2] or ""))
    return out


def moved(a, b):
    return a is not None and b is not None and abs(a - b) > max(MOVE * abs(a), 0.5e6)


def pattern(form, keys):
    """The kind of revision from the filing's form and the figures it changed (see the module docstring)."""
    if form.endswith("/A"):
        return "amended"
    if "ni" in keys:
        return "results"
    if "revenue" in keys or "oi" in keys:
        return "presentation"
    return "cash flow"


def compute(fx, ev, fye="1231"):
    """{"keys", "periods": [[start, end, kind, label]], "v": {key: [[period index, [[value, ref], ...]], ...]},
    "events": [...]} — versions listed only when the value changed — or None."""
    V = fx.get("__versions__") or {}
    ends = [e for c in CONCEPTS for (s, e) in (V.get(c) or {})]
    if not ends:
        return None
    cut = F.d(max(ends)).replace(year=F.d(max(ends)).year - YEARS).isoformat()
    spans = sorted({(s, e) for c in CONCEPTS for (s, e) in (V.get(c) or {}) if e >= cut and _kind(s, e)},
                   key=lambda se: (se[1], se[0]))
    periods, pidx, out, changes = [], {}, {k: [] for k in KEYS}, {}
    for s, e in spans:
        kind = _kind(s, e)
        rows = {k: versions(fx, k, s, e) for k in KEYS}
        if not any(rows.values()):
            continue
        if (s, e) not in pidx:
            pidx[(s, e)] = len(periods)
            label = F.fiscal_year_label(e, fye)[0] if kind == "fy" else F.fiscal_label(e, fye)[0]
            periods.append([s, e, kind, label])
        i = pidx[(s, e)]
        for k, vs in rows.items():
            if not vs:
                continue
            kept, last = [], None
            for filed, form, accn, val, c, f in vs:
                if last is None or moved(last, val):
                    ref = ev.ref(c, kind if kind == "fy" else "3m", [f])
                    kept.append([val, ref])
                    if last is not None:                     # a later filing changed this figure
                        changes.setdefault(accn, {"form": form, "filed": filed, "ref": ref, "items": []})["items"].append(
                            [k, i, last, val])
                    last = val
            out[k].append([i, kept])
    events = []
    for accn, ch in changes.items():
        keys = {x[0] for x in ch["items"]}
        ch["pattern"] = pattern(ch["form"], keys)
        ch["filing"] = ch.pop("ref")[2][0]                 # the filing's index in the evidence list
        ch["why"] = None                                     # the filing's own explanation, to be read from its text
        events.append(ch)
    events.sort(key=lambda x: x["filed"], reverse=True)
    if not periods:
        return None
    return {"keys": KEYS, "periods": periods, "v": out, "events": events}
