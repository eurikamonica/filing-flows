"""A filing's company name as the site shows it.

SEC conformed names are all capitals ("ILLINOIS TOOL WORKS INC", "W&T OFFSHORE INC", "FREEPORT-MCMORAN INC", "AMPHENOL CORP
/DE/"): cased() writes them as the companies do, word by word (initialisms, Mc-, O'-, &-joined letters, a few known
brands), and display() also drops the legal suffix and the state marker for a heading ("Illinois Tool Works").
A mixed-case name is a newer filer's own ("Sunrun Inc.", "Equitable Holdings, Inc."): kept, but a word in capitals
inside it that is no initialism is cased too ("E.W. SCRIPPS Co" → E.W. Scripps)."""
import re

KEEP_UPPER = {"AI", "AMD", "AT&T", "BP", "CVS", "HP", "IBM", "II", "III", "IV", "LLC", "LP", "NV", "PLC", "SA", "UPS", "USA", "US", "NVIDIA", "REIT",
              "ETF", "LNG", "REIT", "SPAC", "USA", "EV", "IT", "RV", "TV", "AG", "SE", "SpA", "NV", "OPCO", "MLP", "ESG",
              "ASML", "TSMC", "HSBC", "SPDR", "PIMCO", "ADR", "ADRS", "ETFS", "FTSE", "MSCI", "NYSE", "OTC"}
# an all-capitals filing name is cased word by word; these keep their own capitals (a plain capitalize() loses them)
CASED = {"MCMORAN": "McMoRan", "CONOCOPHILLIPS": "ConocoPhillips", "JPMORGAN": "JPMorgan", "EXXONMOBIL": "ExxonMobil", "PAYPAL": "PayPal",
         "EBAY": "eBay", "LYONDELLBASELL": "LyondellBasell", "SERVICENOW": "ServiceNow", "BIOMARIN": "BioMarin", "MASTERCARD": "Mastercard",
         "GLOBALFOUNDRIES": "GlobalFoundries", "LPL": "LPL", "KLA": "KLA", "CDW": "CDW", "DXC": "DXC", "MGM": "MGM", "NXP": "NXP", "ONEOK": "ONEOK",
         "CSX": "CSX", "DTE": "DTE", "PPL": "PPL", "PNC": "PNC", "KKR": "KKR", "TPG": "TPG", "CBRE": "CBRE", "AECOM": "AECOM", "IQVIA": "IQVIA",
         "NETAPP": "NetApp", "GODADDY": "GoDaddy", "YUM": "Yum", "TKO": "TKO", "WEC": "WEC", "AES": "AES", "NRG": "NRG", "EQT": "EQT", "UGI": "UGI",
         "MSCI": "MSCI", "SBA": "SBA", "SEI": "SEI", "ITT": "ITT", "MSA": "MSA", "TJX": "TJX", "ABM": "ABM", "CNA": "CNA", "WEX": "WEX", "NCR": "NCR",
         "EMCOR": "EMCOR", "APA": "APA", "CF": "CF", "GE": "GE", "3M": "3M", "ADT": "ADT", "AMC": "AMC", "BJ'S": "BJ's", "HCA": "HCA", "IDEX": "IDEX",
         "KBR": "KBR", "L3HARRIS": "L3Harris", "MKS": "MKS", "NOV": "NOV", "OGE": "OGE", "ONE": "One", "RH": "RH", "SLB": "SLB", "SLM": "SLM",
         "UDR": "UDR", "W&T": "W&T", "H&R": "H&R", "CACI": "CACI", "MDU": "MDU", "ICF": "ICF", "MGP": "MGP", "ADP": "ADP", "CME": "CME",
         "ICE": "ICE", "LKQ": "LKQ", "ESCO": "ESCO", "NMI": "NMI", "FTAI": "FTAI", "AMETEK": "Ametek", "CTS": "CTS", "PTC": "PTC", "TTM": "TTM",
         "VSE": "VSE", "OSI": "OSI", "IPG": "IPG", "AAR": "AAR", "EOG": "EOG", "AT&T": "AT&T", "DICK'S": "Dick's", "MACY'S": "Macy's",
         "KOHL'S": "Kohl's", "O'REILLY": "O'Reilly", "LOWE'S": "Lowe's", "MCDONALD'S": "McDonald's", "MCDONALDS": "McDonald's",
         "DUPONT": "DuPont", "DR": "D.R.", "WAL": "Wal", "WALMART": "Walmart", "PEPSICO": "PepsiCo", "FEDEX": "FedEx", "CENTERPOINT": "CenterPoint",
         "NISOURCE": "NiSource", "LULULEMON": "lululemon", "ADOBE": "Adobe", "MARKETAXESS": "MarketAxess", "OPENDOOR": "Opendoor",
         "DOORDASH": "DoorDash", "LINKEDIN": "LinkedIn", "AIRBNB": "Airbnb", "SNOWFLAKE": "Snowflake", "DATADOG": "Datadog", "MONGODB": "MongoDB",
         "CROWDSTRIKE": "CrowdStrike", "DEXCOM": "DexCom", "RESMED": "ResMed", "LABCORP": "Labcorp", "QUIDELORTHO": "QuidelOrtho",
         "VERISIGN": "VeriSign", "ANSYS": "Ansys", "AUTODESK": "Autodesk", "NETFLIX": "Netflix", "ALPHABET": "Alphabet", "TESLA": "Tesla",
         # the names a 13F or a Form 4 writes in capitals (holders' tables, insiders' tables)
         "ISHARES": "iShares", "VANECK": "VanEck", "BLACKROCK": "BlackRock", "WISDOMTREE": "WisdomTree", "PROSHARES": "ProShares",
         "UNITEDHEALTH": "UnitedHealth", "ABBVIE": "AbbVie", "ASTRAZENECA": "AstraZeneca", "GLAXOSMITHKLINE": "GlaxoSmithKline",
         "TOTALENERGIES": "TotalEnergies", "XPENG": "XPeng", "BIONTECH": "BioNTech", "NEXTERA": "NextEra", "COREWEAVE": "CoreWeave",
         "MICROSTRATEGY": "MicroStrategy", "APPLOVIN": "AppLovin", "SOFI": "SoFi", "DRAFTKINGS": "DraftKings", "MERCADOLIBRE": "MercadoLibre",
         "NU": "Nu", "HUBSPOT": "HubSpot", "DOCUSIGN": "DocuSign", "ZOOMINFO": "ZoomInfo", "AUTOZONE": "AutoZone", "CARMAX": "CarMax",
         "ECHOSTAR": "EchoStar", "SPACEMOBILE": "SpaceMobile", "IONQ": "IonQ", "SOUNDHOUND": "SoundHound", "BIGBEAR": "BigBear",
         "UIPATH": "UiPath", "SENTINELONE": "SentinelOne", "GITLAB": "GitLab", "LENDINGCLUB": "LendingClub", "QUALCOMM": "Qualcomm",
         "BROADCOM": "Broadcom", "SALESFORCE": "Salesforce", "SUPERMICRO": "Supermicro", "PALANTIR": "Palantir", "ROBINHOOD": "Robinhood",
         # the apostrophe a 13F drops: "MOODYS CORP", "KOHLS CORP", "LOWES COS INC", "MACYS INC", "DILLARDS INC", "WENDYS CO"
         "MOODYS": "Moody's", "KOHLS": "Kohl's", "LOWES": "Lowe's", "MACYS": "Macy's", "DILLARDS": "Dillard's", "CARTERS": "Carter's",
         "WENDYS": "Wendy's", "DENNYS": "Denny's", "CAMPBELLS": "Campbell's", "DICKS": "Dick's", "BJS": "BJ's", "KELLOGGS": "Kellogg's",
         "HERSHEYS": "Hershey's", "LANDS": "Lands'", "CHURCHS": "Church's", "COS": "Cos",
         "COCA": "Coca", "COLA": "Cola", "MCKESSON": "McKesson", "MCCORMICK": "McCormick", "MCDONALD": "McDonald",
         # the abbreviations a 13F issuer name is filed with: "VANGUARD INDEX FDS", "COSTCO WHSL CORP NEW", "ALPHABET INC CL A"
         "FDS": "Funds", "FD": "Fund", "TR": "Trust", "WHSL": "Wholesale", "HLDGS": "Holdings", "HLDG": "Holding", "SVCS": "Services",
         "SVC": "Service", "INTL": "International", "PHARMS": "Pharmaceuticals", "PHARMA": "Pharma", "INDS": "Industries", "FINL": "Financial",
         "PPTYS": "Properties", "PPTY": "Property", "RLTY": "Realty", "MFG": "Manufacturing", "ENTMT": "Entertainment", "COMMUNS": "Communications",
         "SYS": "Systems", "AMERN": "American", "NATL": "National", "GRP": "Group", "SPON": "Sponsored", "SHS": "Shares", "CL": "Class",
         "TECHS": "Technologies", "ENTERPRS": "Enterprises", "LABS": "Labs", "SOLUTNS": "Solutions", "THERAPEUTICS": "Therapeutics",
         "BANCORP": "Bancorp", "BANCSHARES": "Bancshares", "FINCL": "Financial", "RESH": "Research", "PRODS": "Products", "INSTRS": "Instruments",
         "MGMT": "Management", "PTNRS": "Partners", "PRTNRS": "Partners", "INVT": "Investment", "ENRGY": "Energy", "INTERNATL": "International",
         "RESTR": "Restaurants", "HOLDGS": "Holdings", "CORPORATN": "Corporation", "TELECOMMUNICATNS": "Telecommunications"}
# prepositions and articles inside a name stay lower case: DuPont de Nemours, Bank of America, Van der Moolen
LOWER_INSIDE = {"DE", "OF", "AND", "THE", "FOR", "VAN", "DER", "VON", "DA", "DO", "DU", "ET", "EN", "LA", "LE", "DEL", "Y", "DI", "DELLA", "DES"}
# all-capitals words of three letters or fewer are usually initialisms (CNA, EQT, GE) — except these everyday words
SHORT_WORDS = {"THE", "AND", "FOR", "INC", "LTD", "CO", "OF", "DE", "DEL", "LA", "LE", "NEW", "SUN", "GAS", "OIL", "AIR", "BIO", "NET", "ONE",
               "BIG", "RED", "TOP", "KEY", "GAP", "BOX", "ARM", "VAN", "DER", "VON", "DA", "DO", "DU", "ET", "EN", "AL", "AM", "AN", "AS", "AT",
               "BY", "IN", "ON", "OR", "TO", "UP", "NO", "SO", "MY", "WE", "GO", "SEA", "ICE", "OLD", "ALL", "TWO", "SIX", "TEN", "DAY", "HUB",
               "CAR", "SKY", "MAX", "ARC", "ACE", "ERA", "ART", "LAB", "BAY", "FOX", "RAY", "SET", "ZIP", "FIT", "ADS", "NY", "NJ", "FL", "TX",
               "CA", "MD", "PA", "VA", "WA", "OH", "GA", "IL", "MA", "CT", "MN", "MI", "NC", "SC", "MO", "WI", "IA", "KS", "KY", "OK", "OR", "UT",
               "AZ", "NV", "CO", "ID", "MT", "NE", "ND", "SD", "NM", "WY", "AK", "HI", "ME", "VT", "NH", "RI", "DC", "AL", "AR", "LA", "MS", "TN",
               "WV", "IN", "DE"}
SHORT_WORDS |= {"COM", "LLC"}
# first names and everyday words of three letters in company names: Eli Lilly, Lee Enterprises, Hot Topic, Via Renewables, Mid-America
SHORT_WORDS |= {"ELI", "SAM", "LEE", "BEN", "JOE", "JIM", "TOM", "DAN", "ANN", "JAY", "KIM", "ROY", "TIM", "TED", "ROB", "RON", "BOB", "IAN",
                "LOU", "MEL", "LEO", "LIZ", "PAT", "DON", "REX", "AMY", "NED", "NAT", "EVE", "MAE", "AVA", "ZOE", "ABE", "GUS", "HAL", "SID", "VIC",
                "SOL", "OAK", "ELM", "ASH", "BAR", "CAT", "DOG", "FLY", "HAT", "JET", "JOY", "KIT", "MAP", "MUD", "PEN", "PIE", "PIN", "POP", "POT",
                "RAM", "ROD", "RYE", "SAW", "SKI", "SPA", "TAB", "TAG", "TAP", "TEA", "TIN", "TOY", "WAX", "WEB", "ZEN", "ZOO", "BEE", "BUG", "ANT",
                "APE", "OWL", "PET", "RAW", "RUN", "WIN", "WAY", "ZAP", "YES", "YOU", "WHO", "HOW", "WHY", "OUR", "ITS", "OFF", "OUT", "OWN", "GET",
                "PUT", "LET", "SAY", "SEE", "USE", "VIA", "PER", "PRO", "ANY", "FEW", "LOT", "MIX", "FUN", "HOT", "WET", "DRY", "FAR", "LOW", "MID",
                "END", "EGG", "HAM", "JAM", "BAD", "FAT", "ODD", "SON", "RIO", "SAN", "LOS", "LAS", "DEL", "MAR", "SUR"}
SHORT_WORDS -= {"US", "NV", "SA"}


def _cased(w):
    """One word of an all-capitals filing name, cased for a page: W&T, Freeport-McMoRan, O'Reilly, BJ's, 3M, CNA, N.V., the."""
    core, tail = re.match(r"^(.*?)([,.;:]*)$", w).groups()        # "MACY'S," → the word and its punctuation
    if core in CASED:
        return CASED[core] + tail
    if core in KEEP_UPPER or re.search(r"\d", core) or re.fullmatch(r"(?:[A-Z]\.)+[A-Z]?", core):
        return w                                                   # 3M, N.V., U.S.
    if re.fullmatch(r"[A-Z]{1,3}", core) and core not in SHORT_WORDS:
        return w                                                   # CNA Financial, EQT, GE: an initialism
    parts = re.split(r"([&/'’\-])", core)
    if len(parts) > 1 and all(re.fullmatch(r"[A-Z]{1,3}", x) for x in parts[::2] if x) and any(x in "&/" for x in parts[1::2]):
        return w                                                   # W&T, AT&T, H&R, PG&E, RE/MAX
    out = ""
    for i, part in enumerate(parts):
        if i % 2 or not part:
            out += part
            continue
        prev = parts[i - 1] if i else ""
        if prev in ("'", "’") and part == "S":
            out += "s"                                             # Macy's, Kohl's, BJ's
        elif part in CASED:
            out += CASED[part]
        elif re.fullmatch(r"MC[A-Z]{3,}", part):
            out += "Mc" + part[2:].capitalize()                    # McKesson, McCormick
        else:
            out += part.capitalize()
    return out + tail


SUFFIX = re.compile(r",?\s+(?:&\s+)?(Inc|Corp|Corporation|Co|Ltd|Plc|Holdings|Group|Company)\.?$", re.I)


def cased(name):
    """The name with its own capitals, the legal suffix kept: 'ILLINOIS TOOL WORKS INC' → Illinois Tool Works Inc,
    'W&T OFFSHORE INC' → W&T Offshore Inc, 'ACUITY INC. (DE)' → Acuity Inc., 'Huntsman CORP' → Huntsman Corp."""
    name = (name or "").strip()
    name = re.sub(r"\s*[/(\\]\s*[A-Z]{2,3}\s*[/)\\]?\s*$", "", name)          # "/DE/", "(DE)", "\DE\"
    name = re.sub(r"\s*/\s*$", "", name)                                      # "AMETEK INC/"
    if name.upper() == name:
        name = re.sub(r"\s+(?:NEW|DEL|DE)(?:\s+(?:NEW|DEL|DE))?$", "", name)     # "BERKSHIRE HATHAWAY INC DEL", "COSTCO WHSL CORP NEW"
        words = name.split()
        name = " ".join(w.lower() if i and w in LOWER_INSIDE else _cased(w) for i, w in enumerate(words))
    else:
        name = " ".join(_cased(w) if re.fullmatch(r"[A-Z][A-Z,.;:'’&/\-]{3,}", w) else w for w in name.split())
    return name.replace("Jpmorgan", "JPMorgan").replace("Amazon Com", "Amazon.com").replace("O Reilly", "O'Reilly").rstrip(" ,/")


SUFFIXES = {"JR": "Jr.", "JR.": "Jr.", "SR": "Sr.", "SR.": "Sr.", "II": "II", "III": "III", "IV": "IV"}


def _person_word(w):
    """One word of a person's name written in capitals: O'Brien, McCarthy, Smith-Jones, de la Cruz (inside), an initial kept."""
    core, tail = re.match(r"^(.*?)([,.;:]*)$", w).groups()
    if core in SUFFIXES:
        return SUFFIXES[core]
    if re.fullmatch(r"[A-Z]", core):
        return w                                                   # an initial: "KIRK RONALD J"
    parts = re.split(r"([&'’\-])", core)
    out = ""
    for i, part in enumerate(parts):
        if i % 2 or not part:
            out += part
        elif re.fullmatch(r"MC[A-Z]{2,}", part):
            out += "Mc" + part[2:].capitalize()                    # McCarthy, McDonald
        else:
            out += part.capitalize()
    return out + tail


def person(name):
    """A person's name as a Form 4 or a Schedule 13D writes it, in capitals ("BERHO CARRANZA LORENZO DOMINIQUE",
    "O'BRIEN MICHAEL J"), cased word by word; a mixed-case name is kept as written. The filing's word order is kept."""
    name = (name or "").strip()
    if name.upper() != name or not re.search(r"[A-Z]{2}", name):
        return name
    words = name.split()
    return " ".join(w.lower() if i and w in LOWER_INSIDE and w not in ("Y",) else _person_word(w) for i, w in enumerate(words))


def display(name):
    """A heading's name: cased, without the legal suffix: 'AMETEK INC/' → Ametek, 'AMPHENOL CORP /DE/' → Amphenol,
    'FREEPORT-MCMORAN INC' → Freeport-McMoRan, 'MKS INC' → MKS, 'AMAZON COM INC' → Amazon."""
    name = SUFFIX.sub("", cased(name))
    name = re.sub(r",?\s+(?:Inc|Corp|Corporation|Co|Ltd|Plc)\.?$", "", name)    # "SK TELECOM CO LTD" → SK Telecom, "… CO INC" → …
    name = re.sub(r"\s+Com$", "", name)                          # "AMAZON COM INC" → Amazon, not "Amazon Com"
    return name.rstrip(" &,/")
