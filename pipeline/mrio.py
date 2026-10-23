"""Inter-country input-output coefficients (pipeline/data/mrio.json, built by scripts/mrio_build.py) for Money flow
Beta 1.1: FIGARO (Eurostat), ADB MRIO and, when it has been added, OECD ICIO.

A company's industry is matched through its BEA industries (pipeline/data/bea_io.json, NAICS-based codes) to ISIC
divisions, which every multi-country table uses: e.g. BEA 333914 (pumps) → NAICS 333 → ISIC 28 (machinery) → FIGARO C28,
ADB c13, ICIO C28. Coefficients are output-weighted over the table industries that cover those divisions."""
import json
import os
from collections import defaultdict

DATA = os.path.join(os.path.dirname(__file__), "data", "mrio.json")
LABEL = {"figaro": "Eurostat FIGARO", "adb": "ADB MRIO", "icio": "OECD ICIO", "bea": "BEA"}

# NAICS (BEA detail codes start with it) → ISIC Rev. 4 division; the longest prefix wins
NAICS_ISIC = [("111", 1), ("112", 1), ("113", 2), ("114", 3), ("115", 1), ("211", 6), ("2121", 5), ("2122", 7), ("2123", 8),
              ("212", 8), ("213", 9), ("2211", 35), ("2212", 35), ("2213", 36), ("221", 35), ("23", 41), ("311", 10),
              ("3121", 11), ("3122", 12), ("312", 11), ("313", 13), ("314", 13), ("315", 14), ("316", 15), ("321", 16),
              ("322", 17), ("323", 18), ("324", 19), ("3254", 21), ("325", 20), ("326", 22), ("327", 23), ("331", 24),
              ("332", 25), ("333", 28), ("334", 26), ("335", 27), ("3364", 30), ("3365", 30), ("3366", 30), ("3369", 30),
              ("336", 29), ("337", 31), ("3391", 32), ("339", 32), ("42", 46), ("441", 45), ("44", 47), ("45", 47), ("4A", 47),
              ("481", 51), ("482", 49), ("483", 50), ("484", 49), ("485", 49), ("486", 49), ("487", 49), ("488", 52),
              ("48A", 52), ("491", 53), ("492", 53), ("493", 52), ("511", 58), ("512", 59), ("515", 60), ("517", 61),
              ("518", 63), ("519", 63), ("521", 64), ("522", 64), ("52A", 64), ("523", 66), ("524", 65), ("525", 64),
              ("531", 68), ("532", 77), ("533", 77), ("5411", 69), ("5412", 69), ("5413", 71), ("5414", 74), ("5415", 62),
              ("5416", 70), ("5417", 72), ("5418", 73), ("5419", 74), ("541", 74), ("55", 70), ("5613", 78), ("5615", 79),
              ("5616", 80), ("5617", 81), ("561", 82), ("562", 38), ("61", 85), ("621", 86), ("622", 86), ("623", 87),
              ("624", 88), ("711", 90), ("712", 91), ("713", 93), ("721", 55), ("722", 56), ("811", 95), ("812", 96),
              ("813", 94), ("814", 97), ("S00", 84), ("G", 84)]
ISO_NAME = {"USA": "United States", "CHN": "China", "DEU": "Germany", "JPN": "Japan", "KOR": "South Korea", "TWN": "Taiwan",
            "MEX": "Mexico", "CAN": "Canada", "GBR": "United Kingdom", "FRA": "France", "ITA": "Italy", "NLD": "Netherlands",
            "IRL": "Ireland", "CHE": "Switzerland", "IND": "India", "BRA": "Brazil", "VNM": "Viet Nam", "MYS": "Malaysia",
            "THA": "Thailand", "SGP": "Singapore", "IDN": "Indonesia", "PHL": "Philippines", "ESP": "Spain", "BEL": "Belgium",
            "SWE": "Sweden", "DNK": "Denmark", "NOR": "Norway", "FIN": "Finland", "AUT": "Austria", "POL": "Poland",
            "CZE": "Czechia", "HUN": "Hungary", "ISR": "Israel", "AUS": "Australia", "SAU": "Saudi Arabia", "TUR": "Türkiye",
            "ZAF": "South Africa", "RUS": "Russia", "ARG": "Argentina", "PRT": "Portugal", "GRC": "Greece", "LUX": "Luxembourg",
            "HKG": "Hong Kong", "ROW": "Rest of the world", "NZL": "New Zealand", "ARE": "United Arab Emirates", "CHL": "Chile",
            "COL": "Colombia", "PER": "Peru", "ROU": "Romania", "BGR": "Bulgaria", "SVK": "Slovakia", "SVN": "Slovenia",
            "HRV": "Croatia", "LTU": "Lithuania", "LVA": "Latvia", "EST": "Estonia", "CYP": "Cyprus", "MLT": "Malta",
            "BGD": "Bangladesh", "PAK": "Pakistan", "KAZ": "Kazakhstan", "LKA": "Sri Lanka", "KHM": "Cambodia"}
# EDGAR's location names (profile "state" codes of foreign filers) → ISO3
EDGAR_NAME_ISO = {v.upper(): k for k, v in ISO_NAME.items()}
EDGAR_NAME_ISO.update({"KOREA, REPUBLIC OF": "KOR", "TAIWAN, PROVINCE OF CHINA": "TWN", "UNITED KINGDOM": "GBR", "CHINA": "CHN",
                       "VIET NAM": "VNM", "RUSSIAN FEDERATION": "RUS", "TURKEY": "TUR", "HONG KONG": "HKG", "CZECH REPUBLIC": "CZE",
                       "CAYMAN ISLANDS": None, "BERMUDA": None, "VIRGIN ISLANDS, BRITISH": None, "JERSEY": None,
                       "GUERNSEY": None, "MARSHALL ISLANDS": None, "PANAMA": None, "BAHAMAS": None, "CURACAO": None})
CURRENCY_ISO = {"DKK": "DNK", "SEK": "SWE", "NOK": "NOR", "CHF": "CHE", "GBP": "GBR", "JPY": "JPN", "CNY": "CHN", "RMB": "CHN",
                "TWD": "TWN", "KRW": "KOR", "INR": "IND", "BRL": "BRA", "CAD": "CAN", "AUD": "AUS", "MXN": "MEX", "ILS": "ISR",
                "HKD": "HKG", "ZAR": "ZAF", "PLN": "POL", "HUF": "HUN", "CZK": "CZE", "IDR": "IDN", "THB": "THA",
                "SGD": "SGP", "MYR": "MYS", "PHP": "PHL", "TRY": "TUR", "ARS": "ARG", "CLP": "CHL", "COP": "COL"}


def division(bea_code):
    best = None
    for p, d in NAICS_ISIC:
        if bea_code.startswith(p) and (best is None or len(p) > len(best[0])):
            best = (p, d)
    return best[1] if best else None


class MRIO:
    def __init__(self, path=DATA):
        self.ok = os.path.exists(path)
        self.d = json.load(open(path, encoding="utf-8")) if self.ok else {"sources": {}}
        self.src = self.d.get("sources", {})
        self._codes = {s: defaultdict(list) for s in self.src}
        for s, v in self.src.items():
            for code, divs in (v.get("codes") or {}).items():
                for dv in divs:
                    self._codes[s][dv].append(code)
        self._iso = {s: {k.split("|")[0] for k in v.get("t", {})} for s, v in self.src.items()}

    def has(self, src, iso):
        return iso in self._iso.get(src, set())

    def year(self, src):
        return (self.src.get(src) or {}).get("year")

    def label(self, src):
        return f"{LABEL.get(src, src)} {self.year(src) or ''}".strip()

    def home(self, profile, currency=None):
        """A foreign filer's home country (ISO3) from its EDGAR location code, else its reporting currency."""
        code = (profile or {}).get("state") or ""
        name = (self.d.get("edgar") or {}).get(code, "")
        iso = EDGAR_NAME_ISO.get(name.upper()) if name else None
        if not iso and name and ", CANADA" in name.upper():
            iso = "CAN"
        if not iso and currency:
            iso = CURRENCY_ISO.get(currency.upper())
        return iso

    def coef(self, src, iso, divs):
        """Output-weighted coefficients of `iso`'s industries covering divisions {division: weight}, or None.
        iso "WORLD-USA": every country of the table except the United States."""
        T = (self.src.get(src) or {}).get("t") or {}
        if not T:
            return None
        isos = [i for i in self._iso[src] if i != "USA"] if iso == "WORLD-USA" else [iso]
        acc, wsum = defaultdict(float), 0.0
        org, ind = defaultdict(float), defaultdict(float)
        for dv, w in divs.items():
            codes = self._codes[src].get(dv) or []
            entries = [(c, T.get(f"{i}|{c}")) for i in isos for c in codes]
            # an entry whose inputs exceed its output (Iceland's tiny pharmaceutical industry in ICIO 2022) is a
            # statistical artefact of a small cell: left out
            entries = [(c, e) for c, e in entries if e and e.get("o", 0) > 0 and 0 <= e.get("i", 0) <= 1.0]
            tot = sum(e["o"] for _, e in entries)
            if not tot:
                continue
            for c, e in entries:
                x = w * e["o"] / tot
                wsum += x
                for k in ("i", "comp", "otax", "ptax", "va", "gos", "dom"):
                    if k in e:
                        acc[k] += x * e[k]
                        acc["_w_" + k] += x
                for o, s in (e.get("org") or {}).items():
                    org[o] += x * s
                for c2, s in (e.get("ind") or {}).items():
                    ind[c2] += x * s
        if not wsum:
            return None
        out = {k: acc[k] / acc["_w_" + k] for k in ("i", "comp", "otax", "ptax", "va", "gos", "dom") if acc.get("_w_" + k)}
        out["org"] = {o: v / wsum for o, v in org.items()}
        out["ind"] = {c: v / wsum for c, v in ind.items()}
        out["cover"] = wsum / (sum(divs.values()) or 1)
        out["src"] = src
        return out


def divisions_of(mix):
    """{ISIC division: weight} for a company's BEA mix {BEA code: weight}."""
    out = defaultdict(float)
    for b, w in mix.items():
        d = division(b)
        if d:
            out[d] += w
    tot = sum(out.values())
    return {d: w / tot for d, w in out.items()} if tot else {}


def country(iso):
    return ISO_NAME.get(iso, iso)
