"""Currencies: charts of companies that report in another currency than the US dollar.

A foreign private issuer's 20-F and 6-K results are drawn in the currency it reports in (euros, yen, NT dollars …),
labelled as such. Beside that, the same charts in US dollars:
  1. the company's own figures in dollars, when it gives them — a "convenience translation" rate stated in the filing
     ("solely for the convenience of the reader … at NT$30.66 to US$1.00") or a US$ column next to its own;
  2. otherwise the period's average exchange rate: the Federal Reserve's H.10 noon buying rates (FRED), else the ECB's
     reference rates (Frankfurter) for currencies H.10 does not carry.
The rate and where it comes from go on every converted chart.

Formatting: the amount formatters (sankey.Fmt, social.money, checks.money) write the symbol of the currency in use()
— US dollars unless a company's own currency is set while its charts are drawn.
"""
import contextlib
import copy
import csv
import datetime as dt
import io
import json
import os
import re

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "RMB ", "TWD": "NT$", "KRW": "₩", "INR": "₹", "CAD": "C$",
           "AUD": "A$", "NZD": "NZ$", "CHF": "CHF ", "HKD": "HK$", "SGD": "S$", "BRL": "R$", "MXN": "MX$", "SEK": "SEK ",
           "DKK": "DKK ", "NOK": "NOK ", "ZAR": "ZAR ", "ILS": "₪", "THB": "฿", "PHP": "₱", "IDR": "Rp ", "TRY": "₺", "PLN": "zł ",
           "MYR": "RM ", "CLP": "CLP ", "COP": "COP ", "ARS": "ARS ", "PEN": "S/ ", "RUB": "₽", "CZK": "CZK ", "HUF": "HUF "}
NAMES = {"USD": "US dollars", "EUR": "euros", "GBP": "pounds sterling", "JPY": "Japanese yen", "CNY": "Chinese yuan (renminbi)",
         "TWD": "New Taiwan dollars", "KRW": "Korean won", "INR": "Indian rupees", "CAD": "Canadian dollars", "AUD": "Australian dollars",
         "NZD": "New Zealand dollars", "CHF": "Swiss francs", "HKD": "Hong Kong dollars", "SGD": "Singapore dollars", "BRL": "Brazilian reais",
         "MXN": "Mexican pesos", "SEK": "Swedish kronor", "DKK": "Danish kroner", "NOK": "Norwegian kroner", "ZAR": "South African rand",
         "ILS": "Israeli shekels", "THB": "Thai baht", "PHP": "Philippine pesos", "IDR": "Indonesian rupiah", "TRY": "Turkish lira",
         "PLN": "Polish zloty", "MYR": "Malaysian ringgit", "CLP": "Chilean pesos", "COP": "Colombian pesos", "ARS": "Argentine pesos",
         "PEN": "Peruvian soles", "RUB": "Russian rubles", "CZK": "Czech koruna", "HUF": "Hungarian forint"}
# FRED series of the Federal Reserve's H.10 rates: (series, True when quoted as US dollars per unit of the currency)
FRED = {"EUR": ("DEXUSEU", True), "GBP": ("DEXUSUK", True), "AUD": ("DEXUSAL", True), "NZD": ("DEXUSNZ", True),
        "JPY": ("DEXJPUS", False), "CNY": ("DEXCHUS", False), "TWD": ("DEXTAUS", False), "KRW": ("DEXKOUS", False),
        "INR": ("DEXINUS", False), "CAD": ("DEXCAUS", False), "CHF": ("DEXSZUS", False), "SEK": ("DEXSDUS", False),
        "DKK": ("DEXDNUS", False), "NOK": ("DEXNOUS", False), "HKD": ("DEXHKUS", False), "SGD": ("DEXSIUS", False),
        "BRL": ("DEXBZUS", False), "MXN": ("DEXMXUS", False), "ZAR": ("DEXSFUS", False), "THB": ("DEXTHUS", False),
        "MYR": ("DEXMAUS", False)}
ECB = {"ILS", "IDR", "PHP", "PLN", "TRY", "CZK", "HUF", "ISK", "RON", "BGN"}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
ECB_URL = "https://api.frankfurter.app/{start}..{end}?from=USD&to={cur}"
START = "2015-01-01"

_cur = ["USD"]


@contextlib.contextmanager
def use(code):
    """Amounts written while inside are in this currency (sankey.Fmt, social.money, checks.money)."""
    old = _cur[0]
    _cur[0] = code or "USD"
    try:
        yield
    finally:
        _cur[0] = old


def current():
    return _cur[0]


def sym(code=None):
    c = code or _cur[0]
    return SYMBOLS.get(c, c + " ")


def name(code):
    return NAMES.get(code, code)


def money(v, big=None):
    """'€1.2B', '¥3.4T', 'NT$950.1M' in the currency in use (big: billions when the company is that large)."""
    if v is None:
        return "n/a"
    a, s, y = abs(v), "−" if v < 0 else "", sym()
    if a >= 0.95e12:
        return f"{s}{y}{a / 1e12:.2f}T"
    if a >= 0.95e9 or (big and a >= 5e6):
        b = a / 1e9
        return f"{s}{y}{b:.1f}B" if b >= 0.95 else f"{s}{y}{b:.2f}B"
    m = a / 1e6
    return f"{s}{y}{m:,.1f}M" if m >= 0.95 else f"{s}{y}{a / 1e3:,.0f}K"


# ---------------------------------------------------------------- the company's own rate ("convenience translation")
USD_TOK = r"(?:US\s?\$|U\.S\.\s?\$|USD|U\.S\.\s?dollars?|\$)"
LOCAL_TOK = {"EUR": r"(?:€|EUR|euros?)", "GBP": r"(?:£|GBP)", "JPY": r"(?:¥|JPY|yen)", "CNY": r"(?:RMB|CNY|Rmb|renminbi|yuan)",
             "TWD": r"(?:NT\s?\$|TWD|NTD)", "KRW": r"(?:₩|KRW|W(?=\s?\d)|won)", "INR": r"(?:₹|INR|Rs\.?|rupees?)", "BRL": r"(?:R\$|BRL|reais)",
             "MXN": r"(?:Ps\.?|MXN|Mex\$|pesos?)", "CAD": r"(?:C\$|CAD|Cdn\$)", "AUD": r"(?:A\$|AUD)", "CHF": r"(?:CHF)",
             "HKD": r"(?:HK\$|HKD)", "SEK": r"(?:SEK)", "DKK": r"(?:DKK)", "NOK": r"(?:NOK)", "ZAR": r"(?:ZAR|R(?=\s?\d))",
             "ILS": r"(?:NIS|ILS|₪)", "SGD": r"(?:S\$|SGD)", "PHP": r"(?:₱|PHP|Php)", "IDR": r"(?:Rp|IDR)", "TRY": r"(?:TRY|TL|₺)",
             "CLP": r"(?:Ch\$|CLP)", "COP": r"(?:COP)", "ARS": r"(?:ARS)", "THB": r"(?:THB|Baht)", "NZD": r"(?:NZ\$|NZD)"}
NUM = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
ONE = r"1(?:\.0+)?(?!\.?\d)"
CONTEXT = re.compile(r"convenien|translat|solely for|noon buying|exchange rate|rate of exchange", re.I)


def official_rate(text, cur):
    """US dollars per unit of `cur` from a stated convenience-translation rate in a filing's text, with the sentence it
    came from; None when the filing states none."""
    tok = LOCAL_TOK.get(cur)
    if not tok or not text:
        return None
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    t = t.replace("&nbsp;", " ").replace("&#160;", " ")
    pats = [  # (pattern, how the number reads)
        (rf"{USD_TOK}\s?{ONE}\s?(?:=|to|:|equals?|was)\s?{tok}\s?{NUM}", "local_per_usd"),
        (rf"{tok}\s?{NUM}\s?(?:=|to|per|for|:)\s?(?:each\s)?{USD_TOK}\s?{ONE}\b", "local_per_usd"),
        (rf"{tok}\s?{NUM}\s?(?:=|to|per|for)\s?(?:one|each)\s?(?:U\.S\.\s?)?dollar", "local_per_usd"),
        (rf"{tok}\s?{ONE}\s?(?:=|to|:|equals?)\s?{USD_TOK}\s?{NUM}", "usd_per_local"),
        (rf"{USD_TOK}\s?{NUM}\s?(?:=|to|per|for)\s?{tok}\s?{ONE}\b", "usd_per_local"),
    ]
    for pat, how in pats:
        for m in re.finditer(pat, t, re.I if cur not in ("KRW", "ZAR") else 0):
            ctx = t[max(0, m.start() - 350): m.end() + 150]
            if not CONTEXT.search(ctx):
                continue
            try:
                x = float(m.group(1).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if x <= 0:
                continue
            usd = 1 / x if how == "local_per_usd" else x
            s0 = max(t.rfind(". ", 0, m.start()) + 2, m.start() - 220)
            s1 = t.find(". ", m.end())
            return {"usd": usd, "text": t[s0: s1 + 1 if 0 < s1 < m.end() + 220 else m.end() + 60].strip()}
    return None


# ---------------------------------------------------------------- market rates (FRED H.10, else the ECB)
def _get(url):
    from . import sec
    if sec.FIXTURES:
        return sec.get(url)
    import requests
    r = requests.get(url, headers={"User-Agent": "FilingFlows/1.0 (exchange rates for charts)"}, timeout=30)
    r.raise_for_status()
    return r.text


def daily(cur, cache):
    """{day: US dollars per unit} for a currency, read once a day and kept in `cache` (dict, saved by the caller)."""
    if cur == "USD":
        return {}
    today = dt.date.today().isoformat()
    c = cache.get(cur) or {}
    if c.get("at") == today and c.get("d"):
        return c["d"]
    out = dict(c.get("d") or {})
    try:
        if cur in FRED:
            sid, usd_per = FRED[cur]
            for row in csv.reader(io.StringIO(_get(FRED_URL.format(sid=sid, start=START)))):
                if len(row) >= 2 and re.fullmatch(r"\d{4}-\d\d-\d\d", row[0]):
                    try:
                        v = float(row[1])
                    except ValueError:
                        continue
                    if v > 0:
                        out[row[0]] = v if usd_per else 1 / v
        elif cur in ECB:
            d = json.loads(_get(ECB_URL.format(start=START, end=today, cur=cur)))
            for day, r in (d.get("rates") or {}).items():
                v = (r or {}).get(cur)
                if v:
                    out[day] = 1 / float(v)
    except Exception as e:
        print(f"  exchange rates {cur}: {str(e)[:120]}")
        if not out:
            return {}
    cache[cur] = {"at": today, "d": out, "src": "fred" if cur in FRED else "ecb"}
    return out


def average(d, start, end):
    xs = [v for k, v in d.items() if start <= k <= end]
    return sum(xs) / len(xs) if xs else None


def period_start(end, annual):
    e = dt.date.fromisoformat(end)
    return (e - dt.timedelta(days=364 if annual else 91)).isoformat()


def source_name(cur, cache):
    return ("Federal Reserve H.10 rates, via FRED" if (cache.get(cur) or {}).get("src", "fred" if cur in FRED else "ecb") == "fred"
            else "ECB reference rates")


def rates_for(c, cache):
    """{period end: {"usd": dollars per unit, "src": "official" | "market", "note": ...}} for every period a non-dollar
    company's charts need (each quarter and year, the quarter before and the year before they compare with)."""
    cur = c.get("currency")
    if not cur or cur == "USD":
        return {}
    d = daily(cur, cache)
    out = {}

    def want(end, annual, official=None, url=None):
        if not end or end in out and out[end]["src"] == "official":
            return
        if official and official.get("usd"):
            out[end] = {"usd": official["usd"], "src": "official", "annual": annual, "text": official.get("text"), "url": url}
            return
        if end in out:
            return
        a = average(d, period_start(end, annual), end) if d else None
        if a:
            out[end] = {"usd": a, "src": "market", "annual": annual, "from": period_start(end, annual), "to": end}

    for q in (c.get("quarters") or {}).values():
        want(q["end"], False, q.get("fx_official"), q.get("doc_url"))
    for y in (c.get("years") or {}).values():
        want(y["end"], True, y.get("fx_official"), y.get("doc_url"))
    for q in (c.get("quarters") or {}).values():
        want(q.get("q1_end"), False)
        want(q.get("py_end"), False)
    for y in (c.get("years") or {}).values():
        want(y.get("py_end"), True)
    return out


def note(cur, r, cache):
    """'€1 = US$1.0812, the quarter's average (Federal Reserve H.10 rates, via FRED)' — for a chart's footer."""
    if not r:
        return None
    u = r["usd"]
    rate = f"{sym(cur).strip()}1 = US${u:.4f}" if u >= 0.1 else f"US$1 = {sym(cur).strip()}{1 / u:,.2f}"
    if r["src"] == "official":
        return f"{rate}, the company's own convenience-translation rate"
    return f"{rate}, the {'year' if r.get('annual') else 'quarter'}'s average ({source_name(cur, cache)})"


MONEY_DICTS = ("raw", "raw_q1", "raw_py", "lines", "lines_q1", "lines_py", "ytd_cf")
OWN = {"raw": "end", "lines": "end", "ytd_cf": "end", "raw_q1": "q1_end", "lines_q1": "q1_end", "raw_py": "py_end", "lines_py": "py_end"}


def _scale(d, k):
    if not isinstance(d, dict):
        return d
    return {a: (v * k if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for a, v in d.items()}


def in_dollars(c, rates):
    """A copy of the company record with every amount in US dollars — each period at its own rate (so a comparison with
    the year before includes the currency's move). Periods without a rate are left out."""
    u = copy.deepcopy(c)
    u["currency"] = "USD"
    u["converted_from"] = c.get("currency")
    for group in ("quarters", "years"):
        keep = {}
        for end, q in (u.get(group) or {}).items():
            if end not in rates:
                continue
            for k in MONEY_DICTS:
                if q.get(k) is None:
                    continue
                r = rates.get(q.get(OWN[k]))
                if r:
                    q[k] = _scale(q[k], r["usd"])
                elif k != "raw":
                    q[k] = None                          # no rate for the period it compares with: no comparison
                    if k in ("raw_q1", "raw_py"):
                        q[OWN[k]] = None
            for k in ("co_fcf", "co_fcf_py", "co_fcf_q1"):
                if isinstance(q.get(k), (int, float)):
                    q[k] = q[k] * rates[end]["usd"]
            q["fx"] = rates[end]
            keep[end] = q
        if group in u:
            u[group] = keep
    u.pop("quality", None)                               # ratios and balance-sheet views stay in the reported currency
    return u


def load_cache(root):
    p = os.path.join(root, "fx.json")
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cache(root, cache):
    with open(os.path.join(root, "fx.json"), "w") as f:
        json.dump(cache, f, separators=(",", ":"))
