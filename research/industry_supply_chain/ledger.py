"""Evidence-first, SIC-agnostic industry relationship ledger. Python stdlib only.

No invented links, no invented dollar amounts. The same physical purchase cannot
be counted once in end-buyer capex AND again as a separate upstream terminal flow.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3

DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS industries (
 sic TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT, source TEXT NOT NULL,
 observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS companies (
 cik TEXT PRIMARY KEY, ticker TEXT, name TEXT NOT NULL, sic TEXT,
 observed_at TEXT NOT NULL, FOREIGN KEY (sic) REFERENCES industries(sic)
);
CREATE INDEX IF NOT EXISTS companies_by_sic ON companies(sic);
CREATE INDEX IF NOT EXISTS companies_by_ticker ON companies(ticker);
CREATE TABLE IF NOT EXISTS evidence (
 evidence_id TEXT PRIMARY KEY, accession TEXT, form TEXT, filed_at TEXT,
 source_url TEXT, excerpt TEXT, retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relations (
 relation_id TEXT PRIMARY KEY, supplier_cik TEXT NOT NULL, customer_cik TEXT NOT NULL,
 category TEXT NOT NULL, product TEXT, tier INTEGER NOT NULL DEFAULT 1,
 evidence_level TEXT NOT NULL CHECK(evidence_level IN ('disclosed','inferred','model')),
 evidence_id TEXT REFERENCES evidence(evidence_id),
 valid_from TEXT, valid_to TEXT, observed_at TEXT NOT NULL,
 reported_transaction_usd REAL,
 CHECK(supplier_cik!=customer_cik),
 CHECK(reported_transaction_usd IS NULL OR reported_transaction_usd>=0),
 CHECK(reported_transaction_usd IS NULL OR evidence_level='disclosed'),
 CHECK(reported_transaction_usd IS NULL OR evidence_id IS NOT NULL),
 FOREIGN KEY(supplier_cik) REFERENCES companies(cik),
 FOREIGN KEY(customer_cik) REFERENCES companies(cik)
);
CREATE INDEX IF NOT EXISTS relations_supplier ON relations(supplier_cik);
CREATE INDEX IF NOT EXISTS relations_customer ON relations(customer_cik);
CREATE TABLE IF NOT EXISTS financials (
 cik TEXT NOT NULL, metric TEXT NOT NULL, period_end TEXT NOT NULL,
 fiscal_year INTEGER, fiscal_period TEXT,
 usd REAL NOT NULL, source_tag TEXT, source_url TEXT,
 accession TEXT NOT NULL, filed_at TEXT NOT NULL, observed_at TEXT NOT NULL,
 PRIMARY KEY(cik,metric,period_end,accession),
 FOREIGN KEY(cik) REFERENCES companies(cik)
);
CREATE INDEX IF NOT EXISTS financial_metric ON financials(metric,period_end);
CREATE TABLE IF NOT EXISTS collector_status (
 cik TEXT NOT NULL, feed TEXT NOT NULL, last_checked TEXT NOT NULL,
 status TEXT NOT NULL, detail TEXT, PRIMARY KEY(cik,feed)
);
CREATE TABLE IF NOT EXISTS attributed_revenue (
 scenario TEXT NOT NULL, buyer_cik TEXT NOT NULL, supplier_cik TEXT NOT NULL,
 category TEXT NOT NULL, recognition_period TEXT NOT NULL,
 usd REAL NOT NULL CHECK(usd>=0), as_of TEXT NOT NULL,
 evidence_level TEXT NOT NULL CHECK(evidence_level IN ('estimated','guided','disclosed')),
 method TEXT NOT NULL, PRIMARY KEY(scenario,buyer_cik,supplier_cik,category,recognition_period,as_of),
 FOREIGN KEY(buyer_cik) REFERENCES companies(cik), FOREIGN KEY(supplier_cik) REFERENCES companies(cik)
);
"""


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def cik(value):
    text = str(value or "").strip()
    if not text.isdigit():
        raise ValueError(f"CIK must be digits, got {value!r}")
    return str(int(text))


def sic(value):
    s = str(value or "").strip()
    if not s.isdigit() or int(s) == 0 or len(s) > 4:
        return None
    return s.zfill(4)


def open_db(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn


def ensure_company(con, row, observed_at):
    identifier = cik(row["cik"])
    industry = sic(row.get("sic"))
    if industry:
        con.execute("INSERT OR IGNORE INTO industries VALUES (?,?,?,?,?)",
                    (industry, "SIC " + industry, None, "SEC industry code", observed_at))
    name = str(row.get("name") or "").strip()
    if not name:
        raise ValueError("Company must have a legal name")
    ticker = (row.get("ticker") or "").strip().upper()
    # Upsert retains known SIC when an index lacks SIC, and retains a nonempty ticker.
    con.execute("""INSERT INTO companies(cik,ticker,name,sic,observed_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(cik) DO UPDATE SET
                   ticker=COALESCE(NULLIF(excluded.ticker,''),companies.ticker),
                   name=excluded.name, sic=COALESCE(excluded.sic,companies.sic),
                   observed_at=excluded.observed_at""",
                (identifier, ticker, name, industry, observed_at))
    return identifier


def ingest_gamma(con, site_root, at=None):
    """Imports ALL SIC files already observed by Gamma, not nonexistent market entities.

    Legacy Gamma/Chains named relationships are *not* promoted to SEC verified
    evidence, because many have no accession/URL or are model allocations.
    """
    at = at or utcnow()
    root = Path(site_root) / "gamma"
    catalog = json.loads((root / "index.json").read_text(encoding="utf-8"))
    count, observed, links, skipped = 0, 0, 0, 0
    for sector in catalog.get("industries", []):
        code = sic(sector.get("sic"))
        if not code:
            continue
        con.execute("""INSERT INTO industries VALUES(?,?,?,?,?)
                       ON CONFLICT(sic) DO UPDATE SET name=excluded.name,
                         sector=excluded.sector,source=excluded.source,observed_at=excluded.observed_at""",
                    (code, sector.get("name") or "SIC "+code, sector.get("sector"),
                     "Gamma / SEC-derived industry", at))
        p = root / (code + ".json")
        if not p.exists():
            continue
        info = json.loads(p.read_text(encoding="utf-8"))
        for member in info.get("companies", []):
            if member.get("cik"):
                ensure_company(con, {**member, "sic":code}, at)
                count += 1
                if member.get("current"):
                    observed += 1
        for edge in info.get("relationships", []):
            if edge.get("supplier_cik") and edge.get("customer_cik"):
                supplier, customer = cik(edge["supplier_cik"]), cik(edge["customer_cik"])
                if supplier == customer:
                    skipped += 1
                    continue
                # Import only if endpoints resolve to known SEC CIKs.
                known = con.execute("SELECT COUNT(*) FROM companies WHERE cik IN (?,?)",
                                    (supplier, customer)).fetchone()[0]
                if known != 2:
                    skipped += 1
                    continue
                source = edge.get("source_url") or ""
                disclosure = bool(re.fullmatch(r"https://(www[.])?sec[.]gov/.+",source))
                eid = None
                if disclosure and edge.get("accession_number"):
                    eid = hashlib.sha256((edge["accession_number"]+"|"+source).encode()).hexdigest()[:32]
                    con.execute("INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?)",
                                (eid, edge["accession_number"], edge.get("form"),
                                 edge.get("filing_date"), source, edge.get("source_excerpt"), at))
                level = "disclosed" if eid else "inferred"
                edgekey = supplier+"|"+customer+"|"+(edge.get("chain") or "")+"|"+(edge.get("source") or "")
                rid = hashlib.sha256(edgekey.encode()).hexdigest()[:32]
                con.execute("""INSERT OR IGNORE INTO relations
                  (relation_id,supplier_cik,customer_cik,category,product,tier,
                   evidence_level,evidence_id,valid_from,valid_to,observed_at,reported_transaction_usd)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                            (rid,supplier,customer,edge.get("kind") or "supplier_customer",
                             None,1,level,eid,edge.get("valid_from"),edge.get("valid_to"),at))
                links += 1
            else:
                skipped += 1
    con.commit()
    return {"gamma_sic_groups":len(catalog.get("industries", [])),
            "imported_company_records":count,"observed_reporting_records":observed,
            "resolved_relation_records":links,"unresolved_or_unsafe_edges":skipped,
            "note":"Historical Gamma snapshot coverage, NOT a claim of all SEC issuers."}


def add_relation(con, relation, at=None):
    """Add a genuine pair with optional SEC evidence; never infer dollar flows."""
    at=at or utcnow()
    supplier, customer = cik(relation["supplier_cik"]), cik(relation["customer_cik"])
    if supplier==customer:
        raise ValueError("Self-edge not supported")
    for ident in (supplier,customer):
        if not con.execute("SELECT 1 FROM companies WHERE cik=?",(ident,)).fetchone():
            raise ValueError(f"Unknown CIK {ident}; import entity first")
    level = relation.get("evidence_level","inferred")
    if level not in ("disclosed","inferred","model"):
        raise ValueError("Invalid evidence level")
    source = relation.get("source") or {}
    if level == "disclosed" and not (source.get("url","").startswith("https://www.sec.gov/") and
                                     source.get("accession") and source.get("filed_at")):
        raise ValueError("Disclosed relationship requires SEC URL, accession and filing date")
    value = relation.get("reported_transaction_usd")
    if value is not None and (level != "disclosed" or not isinstance(value,(int,float)) or
                              not 0 <= value < float("inf")):
        raise ValueError("A relationship amount must be finite and SEC-supported")
    eid = None
    if source.get("url"):
        eid = hashlib.sha256((source.get("accession","")+"|"+source["url"]).encode()).hexdigest()[:32]
        con.execute("INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?)",
                    (eid,source.get("accession"),source.get("form"),
                     source.get("filed_at"),source["url"],source.get("excerpt"),at))
    token=json.dumps({k:relation.get(k) for k in ("supplier_cik","customer_cik","category","product",
                                                  "valid_from","valid_to","tier")},sort_keys=True)
    rid=hashlib.sha256(token.encode()).hexdigest()[:32]
    con.execute("""INSERT INTO relations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(relation_id) DO UPDATE SET
                   evidence_level=excluded.evidence_level,evidence_id=excluded.evidence_id,
                   reported_transaction_usd=excluded.reported_transaction_usd,observed_at=excluded.observed_at""",
                (rid,supplier,customer,relation.get("category") or "supplier_customer",
                 relation.get("product"),int(relation.get("tier",1)),level,
                 eid,relation.get("valid_from"),relation.get("valid_to"),at,value))
    con.commit()
    return rid


def coverage(con):
    names=["industries","companies","relations","financials","attributed_revenue"]
    result={n:con.execute("SELECT COUNT(*) FROM "+n).fetchone()[0] for n in names}
    result["companies_with_sic"]=con.execute("SELECT COUNT(*) FROM companies WHERE sic IS NOT NULL").fetchone()[0]
    result["verified_relations"]=con.execute("SELECT COUNT(*) FROM relations WHERE evidence_level='disclosed'").fetchone()[0]
    result["undocumented_relations"]=result["relations"]-result["verified_relations"]
    result["capex_rows"]=con.execute("SELECT COUNT(*) FROM financials WHERE metric='cash_capex'").fetchone()[0]
    return result


def reconcile(con, scenario, period, as_of):
    """By-vendor totals for a single *scenario* and revenue-recognition period.

    Predicted procurement attributed revenue is NOT the same as total GAAP vendor
    revenue. If no comparable SEC value exists, error remains null.
    """
    query="""SELECT supplier_cik,SUM(usd) predicted FROM attributed_revenue
             WHERE scenario=? AND recognition_period=? AND as_of<=?
             GROUP BY supplier_cik"""
    ans=[]
    for r in con.execute(query,(scenario,period,as_of)):
        actual=con.execute("""SELECT usd,accession,filed_at FROM financials
          WHERE cik=? AND metric='revenue_segment' AND period_end=?
                AND filed_at<=?
          ORDER BY filed_at DESC LIMIT 1""",(r["supplier_cik"],period,as_of)).fetchone()
        v=actual["usd"] if actual else None
        ans.append({"supplier_cik":r["supplier_cik"],"period_end":period,"scenario":scenario,
                    "attributed_revenue_usd":r["predicted"],"actual_segment_revenue_usd":v,
                    "unattributed_other_customers_usd":v-r["predicted"] if v is not None else None,
                    "percentage_error":((r["predicted"]-v)/v) if v not in (None,0) else None,
                    "actual_accession":actual["accession"] if actual else None,
                    "note":"Not a customer invoice reconciliation; negative residual flags possible over-attribution."})
    return ans


def cli():
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db",type=Path,required=True)
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("init")
    sub.add_parser("coverage")
    g=sub.add_parser("import-gamma");g.add_argument("--site",type=Path,required=True)
    add=sub.add_parser("add-evidence-edge");add.add_argument("--json",type=Path,required=True)
    rec=sub.add_parser("reconcile");rec.add_argument("--scenario",required=True)
    rec.add_argument("--period",required=True);rec.add_argument("--as-of",required=True)
    args=p.parse_args()
    args.db.parent.mkdir(parents=True,exist_ok=True)
    with open_db(args.db) as con:
        if args.cmd=="init": out={"status":"initialized"}
        elif args.cmd=="coverage":out=coverage(con)
        elif args.cmd=="import-gamma":out=ingest_gamma(con,args.site)
        elif args.cmd=="add-evidence-edge":out={"relation_id":add_relation(con,json.loads(args.json.read_text(encoding="utf-8")))}
        else:out=reconcile(con,args.scenario,args.period,args.as_of)
    print(json.dumps(out,indent=2))


if __name__=="__main__":
    cli()
