"""Who pays whom, from what companies say about their customers and suppliers - every filer, not only the chains.

A 10-K that says "Sales to Walmart Inc. accounted for 16% of net sales" is a stated money flow: Walmart -> the filer,
16% of the filer's revenue that year. Three readings, no model:
  - sentences of the annual report (10-K, 20-F, 40-F) that put a percentage of revenue (or of purchases) on a named
    company, and customer tables ("Customer | 2025 | 2024");
  - XBRL concentration facts (us-gaap:ConcentrationRiskPercentage1 against revenue, by customer), which give the
    percentages, though usually for "Customer A";
  - revenue tagged by customer (srt:MajorCustomersAxis), which gives dollars.
At fetch time only the candidate sentences and facts are kept (rec["cn"]); names are matched to SEC registrants when the
site is built, so the matcher can improve without reading the filings again. A name is linked only when it matches a
registrant's name exactly (or a short list of well-known other names: Google -> Alphabet); anything else stays a label.

Outputs: data/network/c/<cik>.json for each company with a link (as supplier or customer), data/network/index.json.
"""
import datetime as dt
import html as H
import json
import os
import re
import sys
from collections import defaultdict

CN_V = 2                       # the stored reading; a new version re-reads the filings
NAMES_DAYS = 7
MAX_SENT = 30
REFRESH_PER_RUN = 120
ANNUAL = ("10-K", "10-K405", "10-KT", "20-F", "40-F")

# ---------------------------------------------------------------------------------------------------- reading
_ABBR = re.compile(r"(?i)(?:\b(?:inc|corp|co|ltd|no|nos|approx|u\.s|u\.k|s\.a|n\.v|l\.p|llc|plc|jr|sr|st|vs|e\.g|i\.e|"
                   r"fig|dept|ave|bros|mfg|intl|int'l|govt)\.|\b[A-Z]\.)$")
SELL_WORDS = re.compile(r"(?i)\b(revenues?|sales|net sales|net revenues?|billings|shipments)\b")
SELL_VERB = re.compile(r"(?i)\b(accounted|accounts? for|represent\w*|comprised|constitut\w*|derived|attributable|"
                       r"generated|largest customers?|significant customers?|major customers?|customers?)\b")
BUY = re.compile(r"(?i)\b(purchases?|purchased|sole[- ]source[sd]?|single[- ]source[sd]?|sole suppliers?|single suppliers?|"
                 r"largest suppliers?|key suppliers?|primary suppliers?|principal suppliers?|contract manufactur\w*|foundry|"
                 r"foundries|manufactured (?:for us )?by|supplied by|sourced from)\b")


def _flat(doc):
    """HTML -> lines: paragraphs as text, table rows as 'cell | cell', tables fenced by ¶T / ¶E."""
    s = re.sub(r"[\r\n]+", " ", doc)                     # the source's line breaks are not paragraphs
    s = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", s)
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", s)
    s = re.sub(r"(?is)<div[^>]*display:\s*none[^>]*>.*?</div>", " ", s)
    s = re.sub(r"(?i)<table\b[^>]*>", "\n¶T\n", s)
    s = re.sub(r"(?i)</table>", "\n¶E\n", s)
    s = re.sub(r"(?i)</t[dh]>", " | ", s)
    s = re.sub(r"(?i)</tr>|<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = H.unescape(s).replace("\xa0", " ").replace("​", "")
    return [re.sub(r"[ \t]+", " ", l).strip() for l in s.split("\n")]


def _sentences(par):
    parts, out = re.split(r"(?<=[.;])\s+(?=[A-Z(“\"])", par), []
    for p in parts:
        if out and _ABBR.search(out[-1]):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def sentences(doc):
    """Candidate statements about customers and suppliers in an annual report: [{"t": text, "k": "sell"|"buy"|"row"}]."""
    lines = _flat(doc)
    out, seen = [], set()

    def keep(t, k):
        t = t.strip()[:600]
        key = re.sub(r"\W+", "", t.lower())[:200]
        if key and key not in seen:
            seen.add(key)
            out.append({"t": t, "k": k})

    in_table, table, before = False, [], ""
    for line in lines:
        if line == "¶T":
            in_table, table = True, []
            continue
        if line == "¶E":
            ctx = (before[-400:] + " " + " ".join(r for r in table[:3])).lower()
            if "customer" in ctx or "distributor" in ctx:
                for r in table:
                    r = re.sub(r"\s*\|\s*%", "%", r)            # "23 | %" -> "23%"
                    cells = [c.strip() for c in r.split("|") if c.strip() and c.strip() not in ("%", "$", ")")]
                    if len(cells) >= 2 and "%" in r and re.search(r"[A-Za-z]{3}", cells[0]) and not re.search(r"(?i)^total|^other", cells[0]):
                        keep(" | ".join(cells), "row")
            in_table = False
            continue
        if not line:
            continue
        if in_table:
            if "|" in line:
                table.append(line)
            continue
        if len(line) > 40:
            before = line
        if len(line) < 30 or not re.search(r"[A-Z][a-z]", line):
            continue
        for s in _sentences(line):
            if len(s) < 25:
                continue
            if "%" in s or "percent" in s.lower():
                if (SELL_WORDS.search(s) or re.search(r"(?i)receivable", s)) and SELL_VERB.search(s):
                    keep(s, "buy" if BUY.search(s) and not re.search(r"(?i)\b(sales|revenues?) (to|from)\b", s) else "sell")
                    continue
            if BUY.search(s) and re.search(r"(?i)\b(rely|depend|purchase|sole|single|substantially all|majority|significant portion)", s):
                keep(s, "buy")
        if len(out) >= MAX_SENT:
            break
    return out[:MAX_SENT]


def xbrl_rows(parsed):
    """[{"l", "pct"}] from an xfacts.parse of the annual report's instance; dollars by customer as {"l", "usd"}."""
    from . import xfacts
    rows = []
    for c in xfacts.customers(parsed):
        rows.append({"l": c.get("l") or "", "pct": c["pct"], "e": c.get("e"), **({"seg": c["seg"]} if c.get("seg") else {})})
    for m, d in ((parsed.get("axes") or {}).get("MajorCustomersAxis") or {}).items():
        t = xfacts.ttm([[s, e, v] for s, e, v in d.get("f") or []]) if isinstance(d.get("f"), list) else None
        if t and t.get("v"):
            rows.append({"l": d.get("l") or m, "usd": t["v"], "e": t.get("end")})
    return rows


def read(cik, accn, form, filed, doc_url, doc, inst_text=None, lab_text=None, fy=None):
    """The record kept for a company: its annual report's candidate sentences and concentration facts."""
    rec = {"v": CN_V, "accn": accn, "form": form, "filed": filed, "url": doc_url, "fy": fy, "s": [], "x": []}
    try:
        rec["s"] = sentences(doc) if doc else []
    except Exception as e:
        print(f"  customer sentences skipped for {cik}: {e}", file=sys.stderr)
    if inst_text:
        try:
            from . import dims, xfacts
            labels = dims.parse_labels(lab_text) if lab_text else {}
            rec["x"] = xbrl_rows(xfacts.parse(inst_text, labels))
        except Exception as e:
            print(f"  customer facts skipped for {cik}: {e}", file=sys.stderr)
    return rec


# ---------------------------------------------------------------------------------------------------- names
SUFFIX = {"inc", "incorporated", "corp", "corporation", "co", "company", "companies", "ltd", "limited", "plc", "llc", "lp",
          "l", "p", "sa", "s", "a", "nv", "n", "v", "ag", "se", "holdings", "holding", "group", "the", "de", "new", "md",
          "del", "nv", "oyj", "asa", "spa", "kk", "bv", "class", "com", "trust", "ltda", "sab", "cv", "adr", "ads", "tw"}
# single words that are also everyday words in a sentence about customers; never a name on their own
COMMON = set("""
about above according account accounts across additional agency agreement air all also america american americas annual
another approximately asia asset assets average bank based basis before being best both business businesses canada capital
care center certain china clean client clients combined commercial common community company compared consolidated contract
contracts core corporate cost costs credit customer customers data defense department development digital direct
distribution distributor distributors domestic during each early east eastern energy enterprise entities equity europe
european every federal financial first fiscal five following foreign four france free fuel future general germany global
government great green group growth health healthcare higher home income india industrial industries information
international investment investments japan korea large largest life local major management market markets medical
merchant mexico million more most national natural net network new next north northern note number office one only
operating operations other our over pacific partner partners patient patients percent percentage period pharmacy plan
platform power premier price primary prime product products program public quarter quarters rate related renewable
research resources result results retail revenue revenues royal sale sales second security segment segments select
service services share significant single smart solutions south southern standard state states strategic summit supply
system systems taiwan technology technologies texas their these third three through total trade transportation two under
union united universal value west western which while world year years
""".split())
# what filings call companies that SEC lists under another name, and buyers that file nothing with SEC
ALIASES = {
    "google": "GOOGL", "google llc": "GOOGL", "google cloud": "GOOGL", "youtube": "GOOGL", "facebook": "META", "meta": "META",
    "amazon": "AMZN", "amazon com": "AMZN", "amazon web services": "AMZN", "aws": "AMZN", "microsoft": "MSFT", "azure": "MSFT",
    "apple": "AAPL", "walmart": "WMT", "wal mart": "WMT", "wal mart stores": "WMT", "sam s club": "WMT", "target": "TGT",
    "costco": "COST", "home depot": "HD", "lowe s": "LOW", "lowes": "LOW", "kroger": "KR", "best buy": "BBY",
    "dollar general": "DG", "dollar tree": "DLTR", "tjx": "TJX", "cvs": "CVS", "cvs caremark": "CVS", "caremark": "CVS",
    "cvs health": "CVS", "express scripts": "CI", "cigna": "CI", "optum": "UNH", "optumrx": "UNH", "unitedhealth": "UNH",
    "mckesson": "MCK", "cardinal health": "CAH", "amerisourcebergen": "COR", "cencora": "COR", "humana": "HUM",
    "nvidia": "NVDA", "intel": "INTC", "amd": "AMD", "advanced micro devices": "AMD", "qualcomm": "QCOM",
    "broadcom": "AVGO", "tsmc": "TSM", "taiwan semiconductor": "TSM", "taiwan semiconductor manufacturing": "TSM",
    "micron": "MU", "dell": "DELL", "dell technologies": "DELL", "hp": "HPQ", "hp inc": "HPQ", "hewlett packard enterprise": "HPE",
    "hpe": "HPE", "cisco": "CSCO", "oracle": "ORCL", "ibm": "IBM", "international business machines": "IBM",
    "arrow": "ARW", "arrow electronics": "ARW", "avnet": "AVT", "td synnex": "SNX", "synnex": "SNX", "ingram micro": "INGM",
    "boeing": "BA", "lockheed": "LMT", "lockheed martin": "LMT", "raytheon": "RTX", "rtx": "RTX", "northrop": "NOC",
    "northrop grumman": "NOC", "general dynamics": "GD", "l3harris": "LHX", "huntington ingalls": "HII",
    "general motors": "GM", "gm": "GM", "ford": "F", "ford motor": "F", "stellantis": "STLA", "tesla": "TSLA",
    "toyota": "TM", "honda": "HMC", "sony": "SONY", "verizon": "VZ", "at t": "T", "t mobile": "TMUS", "comcast": "CMCSA",
    "charter": "CHTR", "charter communications": "CHTR", "fedex": "FDX", "ups": "UPS", "united parcel service": "UPS",
    "exxon": "XOM", "exxonmobil": "XOM", "exxon mobil": "XOM", "chevron": "CVX", "shell": "SHEL", "bp": "BP",
    "pepsico": "PEP", "coca cola": "KO", "procter gamble": "PG", "procter and gamble": "PG", "p g": "PG",
    "jpmorgan": "JPM", "jpmorgan chase": "JPM", "chase": "JPM", "chase bank": "JPM", "citigroup": "C", "citibank": "C",
    "bank of america": "BAC", "wells fargo": "WFC", "goldman sachs": "GS", "morgan stanley": "MS", "coreweave": "CRWV",
    "openai": None, "anthropic": None, "xai": None, "samsung": None, "samsung electronics": None, "huawei": None,
    "foxconn": None, "hon hai": None, "sk hynix": None, "xiaomi": None, "lenovo": None, "quanta computer": None,
    "wistron": None, "pegatron": None, "compal": None, "inventec": None, "byd": None, "volkswagen": None, "bmw": None,
    "mercedes benz": None, "airbus": None, "siemens": None, "bosch": None, "hyundai": None, "walgreens": None,
    "walgreens boots alliance": None, "medline": None, "publix": None, "h e b": None, "meijer": None, "aldi": None,
}
GOV = [(re.compile(r"(?i)\b(u\.?\s?s\.?|united states|federal)\s+(federal\s+)?government\b|\bu\.?s\.? government agencies\b|"
                   r"\b(u\.?s\.?|united states)\s+department of defense\b|\bdepartment of defense\b|\b(?<!non-)dod\b|"
                   r"\bu\.?s\.? (army|navy|air force|space force)\b"), "U.S. government"),
       (re.compile(r"(?i)\bmedicare\b|\bmedicaid\b|\bcenters for medicare"), "Medicare & Medicaid")]
ANON = re.compile(r"(?i)^(one|two|three|a|an|our|its|the|single|largest|major|significant|other|another|certain|top|"
                  r"customer|customers|distributor|distributors|client|clients|partner|end)\b|\bcustomer\s*[a-z0-9]\b|"
                  r"^customer|^distributor|largest|top (five|ten|\d+)|all other|individually|^total")


def norm(s):
    s = (s or "").lower().replace("&", " and ").replace("'", " ").replace("’", " ")
    s = re.sub(r"/[a-z]{2,3}/?$", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def _strip_suffix(words):
    w = list(words)
    while w and w[-1] in SUFFIX:
        w.pop()
    while w and w[0] == "the":
        w.pop(0)
    if w and w[-1] == "and" or (len(w) >= 2 and w[-2:] == ["and", "co"]):
        w = w[:-1]
    return w


class Names:
    """SEC registrant names -> CIK. rows: [[cik, ticker, title]] (SEC's company_tickers.json); revenue: {cik: $} to
    choose between two registrants that share a short name."""

    def __init__(self, rows, revenue=None):
        revenue = revenue or {}
        self.by_t, self.title, self.ticker = {}, {}, {}
        alias = defaultdict(set)
        for cik, t, title in rows:
            cik = int(cik)
            self.by_t.setdefault(str(t).upper(), cik)
            self.title.setdefault(cik, title)
            self.ticker.setdefault(cik, str(t).upper())
            words = norm(title).split()
            if not words:
                continue
            alias[" ".join(words)].add(cik)                      # "home depot inc"
            core = _strip_suffix(words)
            if not core:
                continue
            short = " ".join(core)
            if len(core) >= 2 or (len(short) >= 4 and short not in COMMON):
                alias[short].add(cik)                            # "home depot", "walmart"
        self.alias = {}
        for a, ciks in alias.items():
            if len(ciks) == 1:
                self.alias[a] = next(iter(ciks))
            else:                                                # two registrants answer to the name: the bigger one,
                ranked = sorted(ciks, key=lambda c: -(revenue.get(c) or 0))   # if only one of them has revenue on file
                if (revenue.get(ranked[0]) or 0) > 0 and not (revenue.get(ranked[1]) or 0):
                    self.alias[a] = ranked[0]
        for a, t in ALIASES.items():
            if t is None:
                self.alias[a] = None
            elif t.upper() in self.by_t:
                self.alias[a] = self.by_t[t.upper()]
        self.maxlen = max((len(a.split()) for a in self.alias), default=1)

    def resolve(self, label):
        """'Walmart Inc.' -> (cik or None, display label); None when it is no name at all ('Customer A')."""
        lab = re.sub(r"\s*\[member\[?\]?$|\s*member$", "", (label or "").strip(), flags=re.I).strip(" ,.;:")
        if not lab or ANON.search(lab) or len(lab) < 2:
            for rx, name in GOV:
                if rx.search(lab or ""):
                    return None, name
            return None, None
        for rx, name in GOV:
            if rx.search(lab):
                return None, name
        n = norm(lab)
        words = n.split()
        for cand in (n, " ".join(_strip_suffix(words))):
            if cand in self.alias:
                return self.alias[cand], lab
        return None, lab

    def find(self, text, skip=()):
        """Names in a sentence, in order: [(start, cik or None, label)]. Only capitalised words can start or be a
        name ("our target market" is not Target); the longest name wins."""
        toks = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9&'’.\-]*", text)]
        out, i = [], 0
        while i < len(toks):
            hit = None
            if toks[i][2][0].isupper() or toks[i][2][0].isdigit():
                for n in range(min(self.maxlen + 2, len(toks) - i), 0, -1):
                    span = toks[i:i + n]
                    if not all(w[0].isupper() or w[0].isdigit() or w.lower() in ("and", "of", "&", "the", "s", "com")
                               for _, _, w in span):
                        continue
                    if not (span[-1][2][0].isupper() or span[-1][2][0].isdigit()):
                        continue
                    phrase = text[span[0][0]:span[-1][1]]
                    n_ = norm(phrase)
                    words = n_.split()
                    cands = [n_, " ".join(_strip_suffix(words))]
                    found = next((c for c in cands if c and c in self.alias), None)
                    if found is not None:
                        cik = self.alias[found]
                        if cik not in skip and found not in skip:
                            hit = (span[0][0], cik, phrase.rstrip(".,;"), n)
                        else:
                            hit = (span[0][0], "self", phrase, n)
                        break
            if hit:
                if hit[1] != "self":
                    out.append(hit[:3])
                i += hit[3]
            else:
                i += 1
        for rx, name in GOV:
            m = rx.search(text)
            if m:
                out.append((m.start(), None, name))
        return sorted(out, key=lambda x: x[0])


# ---------------------------------------------------------------------------------------------------- linking
PCT = re.compile(r"(\d{1,2}(?:\.\d+)?)\s?(%|percent\b)")


def _pcts(s):
    """Percentages in a sentence that are shares of revenue (or of purchases): [(pos, share, 'sell'|'buy'|None)]."""
    out = []
    for m in PCT.finditer(s):
        v = float(m.group(1)) / 100
        if not 0.01 <= v < 0.995:
            continue
        after = s[m.end():m.end() + 90].lower()
        before = s[max(0, m.start() - 12):m.start()].lower()
        if re.search(r"(increase|decrease|grew|growth|declin|rose|fell|up|down|higher|lower|change)\w*\s*(of|by)?\s*$", before):
            continue                                                 # "an increase of 12%"
        if re.search(r"^\s*(?:and \d+(?:\.\d+)?\s?%\s*)*(?:,\s*)?(?:of|from)?\s*(?:our|the|its|total|consolidated|net|gross|company|"
                     r"[a-z]+'s)?\s*(?:total|consolidated|net|gross|worldwide)?\s*(?:net\s+)?(?:product\s+|segment\s+)?"
                     r"(?:receivables?|accounts receivable|trade receivables?)", after):
            out.append((m.start(), v, "ar"))
            continue
        k = "buy" if re.search(r"^[^.;]{0,60}\b(purchases|purchased|inventory|cost of (sales|revenue|goods))", after) else \
            "sell" if re.search(r"^[^.;]{0,70}\b(revenues?|sales|net sales|billings|shipments)\b", after) else None
        out.append((m.start(), v, k))
    return out


def links_from(rec, names, self_cik):
    """[{cust or sup: (cik, label), "pct", "dir": "sell"|"buy", "how", "q"}] for one company's stored reading."""
    me = names.title.get(int(self_cik)) if self_cik else None
    skip = {int(self_cik)} | ({norm(me)} if me else set())
    if me:
        skip.add(" ".join(_strip_suffix(norm(me).split())))
    out = []
    for s in rec.get("s") or []:
        t, k = s["t"], s["k"]
        if k == "row":
            cells = t.split(" | ")
            cik, lab = names.resolve(cells[0])
            if not lab or cik in skip:
                continue
            p = next((float(m.group(1)) / 100 for c in cells[1:] for m in [PCT.search(c)] if m), None)
            if p is not None and 0.01 <= p < 0.995:
                out.append({"cik": cik, "label": lab, "pct": p, "dir": "sell", "how": "customer table", "q": t[:300]})
            continue
        found = names.find(t, skip)
        if not found:
            continue
        pcts = _pcts(t)
        sell = [p for p in pcts if p[2] in ("sell", None)] if k != "buy" else []
        buy = [p for p in pcts if p[2] == "buy"] if k == "buy" else []
        ar = [p for p in pcts if p[2] == "ar"]
        use = sell or buy
        direction = "buy" if k == "buy" else "sell"
        resp = re.search(r"(?i)\brespectively\b", t)
        # names before the first percentage are the ones the percentages are about
        first = use[0][0] if use else len(t)
        named = [f for f in found if f[0] < first] or found
        uniq = []
        for f in named:
            if not any((f[1] is not None and f[1] == u[1]) or f[2] == u[2] for u in uniq):
                uniq.append(f)
        if len(uniq) > 4:                                        # a list of companies, not of customers
            continue
        for i, (_, cik, lab) in enumerate(uniq):
            pct = None
            if use:
                if len(uniq) == 1:
                    pct = use[0][1]
                elif resp and len(use) >= len(uniq):
                    pct = use[i][1]
            how = ("sentence" if pct is not None else "named, share not stated") if not (ar and not use) else "receivables"
            out.append({"cik": cik, "label": lab, "pct": pct, "dir": direction, "how": how, "q": t[:420],
                        **({"combined": round(use[0][1], 4)} if use and pct is None and len(uniq) > 1 else {})})
    for x in rec.get("x") or []:                                 # XBRL: the share, rarely the name
        cik, lab = names.resolve(x.get("l"))
        if cik in skip:
            continue
        out.append({"cik": cik, "label": lab, "pct": x.get("pct"), "usd": x.get("usd"), "dir": "sell",
                    "how": "XBRL" if lab else "XBRL, unnamed", "q": None, **({"seg": x["seg"]} if x.get("seg") else {})})
    return _merge(out)


def _merge(rows):
    """One row per counterparty and direction; a stated name takes an unnamed XBRL share of the same size."""
    named, anon = {}, []
    for r in rows:
        if r["label"] is None:
            anon.append(r)
            continue
        key = (r["dir"], r["cik"] if r["cik"] else norm(r["label"]))
        cur = named.get(key)
        if cur is None:
            named[key] = dict(r)
            continue
        if cur.get("pct") is None and r.get("pct") is not None:
            cur.update(pct=r["pct"], how=r["how"])
        if r.get("usd") and not cur.get("usd"):
            cur["usd"] = r["usd"]
        if not cur.get("q") and r.get("q"):
            cur["q"] = r["q"]
    for a in anon:
        if a.get("pct") is None:
            continue
        same = next((n for n in named.values() if n["dir"] == "sell" and n.get("pct") is not None
                     and abs(n["pct"] - a["pct"]) < 0.006), None)
        if same:
            same["xbrl"] = True
            continue
        bare = [n for n in named.values() if n["dir"] == "sell" and n.get("pct") is None and n["how"] != "receivables"]
        if len(bare) == 1 and not any(x.get("pct") is not None and x is not a and x["label"] is None for x in anon):
            bare[0].update(pct=a["pct"], how="name in text, share from XBRL")
            continue
        named[("sell", f"anon{len(named)}")] = {"cik": None, "label": None, "pct": a["pct"], "dir": "sell",
                                                "how": a["how"], "q": None, **({"seg": a["seg"]} if a.get("seg") else {})}
    return list(named.values())


# ---------------------------------------------------------------------------------------------------- the network
def _year_revenue(rec, fy_end=None):
    years = rec.get("years") or {}
    keys = sorted(years)
    if not keys:
        return None, None
    k = fy_end if fy_end in years else keys[-1]
    raw = (years[k] or {}).get("raw") or {}
    return raw.get("revenue"), k


def _usd(rec, v):
    """Reported currency -> dollars for a foreign filer (the store keeps its own currency)."""
    if v is None:
        return None
    cur = rec.get("currency")
    rate = (rec.get("usd") or {}).get("rate") if isinstance(rec.get("usd"), dict) else None
    if cur and cur != "USD":
        return v * rate if rate else None
    return v


def build(store, out, index, today=None):
    """data/network/c/<cik>.json and data/network/index.json from every company's stored reading."""
    st = store.state
    rows = (st.get("sec_names") or {}).get("rows") or []
    revenue = {int(p["cik"]): p.get("revenue") or 0 for p in index if p.get("cik")}
    if not rows:                                                 # no SEC name list yet: the site's own companies
        rows = [[p["cik"], (p.get("tickers") or [p.get("ticker") or ""])[0] if p.get("tickers") else p.get("ticker") or "", p.get("name") or ""]
                for p in index if p.get("cik")]
    names = Names(rows, revenue)
    prof = {int(p["cik"]): p for p in index if p.get("cik")}
    edges, read_n, with_links = [], 0, 0
    for p in index:
        cik = int(p["cik"])
        rec = store.company(cik)
        cn = rec.get("cn")
        if not cn or cn.get("v") != CN_V:
            continue
        read_n += 1
        rev, fy = _year_revenue(rec, cn.get("fy"))
        rev = _usd(rec, rev)
        ls = links_from(cn, names, cik)
        if ls:
            with_links += 1
        for l in ls:
            e = {"me": cik, "dir": l["dir"], "cik": l["cik"], "label": l["label"], "pct": l.get("pct"),
                 "how": l["how"], "q": l.get("q"), "url": cn.get("url"), "form": cn.get("form"), "filed": cn.get("filed"), "fy": fy}
            if l.get("combined"):
                e["combined"] = l["combined"]
            if l.get("seg"):
                e["seg"] = l["seg"]
            if l.get("usd"):
                e["usd"] = _usd(rec, l["usd"])
            elif l.get("pct") is not None and rev and l["dir"] == "sell":
                e["usd"] = round(l["pct"] * rev)
            edges.append(e)
    # supplier -> customer, both ways a filing can state it
    flows = []
    for e in edges:
        if e["dir"] == "sell":
            s, c = e["me"], e["cik"]
        else:
            s, c = e["cik"], e["me"]
        flows.append({**e, "s": s, "c": c})
    by = defaultdict(list)
    for f in flows:
        for k in {f["s"], f["c"]} - {None}:
            by[k].append(f)

    def node(cik, label=None):
        p = prof.get(cik) if cik else None
        if p:
            return {"cik": cik, "t": (p.get("tickers") or [p.get("ticker")])[0] if p.get("tickers") else p.get("ticker"),
                    "name": p.get("name"), "sic": (p.get("profile") or p).get("sic") if isinstance(p.get("profile"), dict) else p.get("sic")}
        if cik:
            return {"cik": cik, "t": names.ticker.get(cik), "name": names.title.get(cik)}
        return {"cik": None, "t": None, "name": label}

    root = os.path.join(out, "network", "c")
    os.makedirs(root, exist_ok=True)
    keep = set()
    for cik, fl in by.items():
        me = prof.get(cik)
        if not me:
            continue
        rec = store.company(cik)
        rev, fy = _year_revenue(rec)
        doc = {"cik": cik, "me": node(cik), "revenue": _usd(rec, rev), "fy": fy,
               "customers": [], "suppliers": []}
        for f in fl:
            if f["s"] == cik:
                doc["customers"].append({**node(f["c"], f["label"]), "label": f["label"], "pct": f.get("pct"), "usd": f.get("usd"),
                                         "how": f["how"], "q": f.get("q"), "url": f.get("url"), "form": f.get("form"),
                                         "filed": f.get("filed"), "fy": f.get("fy"), "by": "self" if f["me"] == cik else "other",
                                         **{k: f[k] for k in ("combined", "seg") if f.get(k)}})
            if f["c"] == cik:
                doc["suppliers"].append({**node(f["s"], f["label"] if f["s"] != f["me"] else None), "label": f["label"], "pct": f.get("pct"),
                                         "usd": f.get("usd"), "how": f["how"], "q": f.get("q"), "url": f.get("url"),
                                         "form": f.get("form"), "filed": f.get("filed"), "fy": f.get("fy"),
                                         "by": "self" if f["me"] == cik else "other", **{k: f[k] for k in ("combined",) if f.get(k)}})
        if f"{cik}" and (doc["customers"] or doc["suppliers"]):
            for side in ("customers", "suppliers"):
                doc[side].sort(key=lambda x: (-(x.get("usd") or 0), -(x.get("pct") or 0)))
            with open(os.path.join(root, f"{cik}.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh, separators=(",", ":"))
            keep.add(cik)
    for f in os.listdir(root):
        if f.endswith(".json") and f[:-5].isdigit() and int(f[:-5]) not in keep:
            os.remove(os.path.join(root, f))
    named = [f for f in flows if f["label"]]
    linked = [f for f in named if f["s"] and f["c"]]
    top = sorted([f for f in linked if f.get("usd")], key=lambda f: -f["usd"])[:60]
    idx = {"generated": (today or dt.date.today()).isoformat(), "read": read_n, "with_links": with_links,
           "edges": len(named), "listed_both_ends": len(linked), "companies": len(keep),
           "top": [{"s": node(f["s"]), "c": node(f["c"]), "usd": f["usd"], "pct": f.get("pct"), "fy": f.get("fy")} for f in top]}
    with open(os.path.join(out, "network", "index.json"), "w", encoding="utf-8") as fh:
        json.dump(idx, fh, separators=(",", ":"))
    print(f"::notice::customer network: {read_n} annual reports read, {with_links} name a customer or supplier; "
          f"{len(named)} named links, {len(linked)} with a listed company at both ends; {len(keep)} company pages")
    return flows


def edges_for_gamma(out):
    """The network as Gamma's relationship rows (supplier/customer tickers, dollars where stated)."""
    root = os.path.join(out, "network", "c")
    rows, seen = [], set()
    if not os.path.isdir(root):
        return rows
    for f in os.listdir(root):
        try:
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        me = d["me"]
        for c in d.get("customers") or []:
            if not c.get("label"):
                continue
            key = (me["cik"], c.get("cik") or c["label"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"supplier": me.get("t") or me.get("name"), "supplier_cik": me["cik"],
                         "customer": c.get("t") or c.get("name") or c["label"], "customer_cik": c.get("cik"),
                         "value_usd": c.get("usd"), "share": c.get("pct"), "period": c.get("fy"),
                         "evidence_level": "Stated in " + (c.get("form") or "annual report") + (" (" + c["how"] + ")" if c.get("how") else ""),
                         "note": (c.get("q") or "")[:240], "source_url": c.get("url"), "source": "sec_customer_network"})
    return rows


# ---------------------------------------------------------------------------------------------------- fetching
def refresh_names(store, sec):
    st = store.state
    cur = st.get("sec_names") or {}
    age = (dt.datetime.utcnow() - dt.datetime.fromisoformat(cur["t"])).days if cur.get("t") else 99
    if age < NAMES_DAYS and cur.get("rows"):
        return
    try:
        data = sec.get_json("https://www.sec.gov/files/company_tickers.json")
        st["sec_names"] = {"t": dt.datetime.utcnow().isoformat(timespec="seconds"),
                           "rows": [[int(v["cik_str"]), str(v["ticker"]).upper().replace(".", "-"), v["title"]] for v in data.values()]}
    except Exception as e:
        print(f"::warning::SEC name list not read ({e})")


def note_filing(c, cik, form, accn, filed, doc_url, doc, inst_text, lab_text, fy=None):
    """Called while a new annual report is processed: keep its reading (the documents are already in hand)."""
    if not form or not form.startswith(ANNUAL) or not doc:
        return
    old = c.get("cn") or {}
    if old.get("v") == CN_V and (old.get("filed") or "") > (filed or ""):
        return
    c["cn"] = read(cik, accn, form, filed, doc_url, doc, inst_text, lab_text, fy)


def refresh(store, sec, dims, time_up, limit=REFRESH_PER_RUN):
    """Read the latest annual report of the companies not read yet (or read before the current version), largest first."""
    refresh_names(store, sec)
    todo = []
    for cik in store.ciks():
        rec = store.company(cik)
        if not rec.get("profile"):
            continue
        years = rec.get("years") or {}
        k = max((y for y in years.values() if (y.get("form") or "").startswith(ANNUAL) and y.get("doc_url")),
                key=lambda y: y.get("filed") or "", default=None)
        if not k:
            continue
        cn = rec.get("cn") or {}
        if cn.get("v") == CN_V and cn.get("accn") == k.get("accn"):
            continue
        rev = ((k.get("raw") or {}).get("revenue") or 0)
        todo.append((0 if not cn else 1, -rev, cik, {kk: k.get(kk) for kk in ("accn", "form", "filed", "doc_url", "end")}))
    todo.sort(key=lambda x: (x[0], x[1]))
    done = 0
    for _, _, cik, k in todo:
        if done >= limit or time_up():
            break
        done += 1
        rec = store.company(cik)
        try:
            doc = sec.get(k["doc_url"])
            inst = lab = None
            try:
                iu, lu = dims.find_files(cik, k["accn"])
                inst = sec.get(iu) if iu else None
                lab = sec.get(lu) if lu else None
            except Exception as e:
                print(f"  instance not read for {cik}: {e}", file=sys.stderr)
            rec["cn"] = read(cik, k["accn"], k.get("form"), k.get("filed"), k["doc_url"], doc, inst, lab, k.get("end"))
        except Exception as e:
            rec["cn"] = {"v": CN_V, "accn": k.get("accn"), "error": str(e)[:200], "s": [], "x": []}
            print(f"  annual report not read for {cik}: {e}", file=sys.stderr)
        store.put(cik, rec)
    if todo:
        print(f"::notice::customer network: {done} annual reports read ({len(todo) - done} waiting)")
