"""A 10-Q that SEC's company facts lacks, read from its own XBRL instance (pipeline/instance.py, build._merge_instance)."""
from pipeline import build, facts, instance

INST = """<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025"
 xmlns:dei="http://xbrl.sec.gov/dei/2025" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <xbrli:context id="q"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001442145</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="qseg"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001442145</xbrli:identifier>
  <xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">vrsk:UnderwritingMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="i"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001442145</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context>
 <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
 <xbrli:unit id="usdps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>
  <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
 <us-gaap:Revenues contextRef="q" unitRef="usd" decimals="-5">806300000</us-gaap:Revenues>
 <us-gaap:Revenues contextRef="q" unitRef="usd" decimals="-5">806300000</us-gaap:Revenues>
 <us-gaap:Revenues contextRef="qseg" unitRef="usd" decimals="-5">569000000</us-gaap:Revenues>
 <us-gaap:NetIncomeLoss contextRef="q" unitRef="usd" decimals="-5">228600000</us-gaap:NetIncomeLoss>
 <us-gaap:EarningsPerShareDiluted contextRef="q" unitRef="usdps" decimals="2">1.63</us-gaap:EarningsPerShareDiluted>
 <us-gaap:Assets contextRef="i" unitRef="usd" decimals="-5">4500000000</us-gaap:Assets>
 <us-gaap:Goodwill contextRef="i" unitRef="usd" xsi:nil="true"/>
 <dei:DocumentType contextRef="q">10-Q</dei:DocumentType>
</xbrli:xbrl>"""


def test_instance_in_company_facts_form():
    cf = instance.to_companyfacts(INST, "0001437749-26-024749", "10-Q", "2026-07-29")
    g = cf["facts"]["us-gaap"]
    assert g["Revenues"]["units"]["USD"] == [{"start": "2026-04-01", "end": "2026-06-30", "val": 806300000,
                                              "accn": "0001437749-26-024749", "form": "10-Q", "filed": "2026-07-29"}]
    assert g["EarningsPerShareDiluted"]["units"]["USD/shares"][0]["val"] == 1.63
    assert "start" not in g["Assets"]["units"]["USD"][0]                     # a balance: an instant
    assert "Goodwill" not in g                                               # nil
    idx = facts.index_facts(cf, "USD", "0001437749-26-024749")               # what the chart reader takes
    assert idx["Revenues"][("2026-04-01", "2026-06-30")]["val"] == 806300000


def test_a_filing_missing_from_company_facts_is_read_from_its_instance(monkeypatch):
    accn = "0001437749-26-024749"
    old = {"facts": {"us-gaap": {"Revenues": {"label": "Revenues", "units": {"USD": [
        {"start": "2026-01-01", "end": "2026-03-31", "val": 772000000, "accn": "0001437749-26-013729", "form": "10-Q", "filed": "2026-04-29"}]}}}}}
    monkeypatch.setattr(build, "_cf", {})
    monkeypatch.setattr(build.sec, "get_json", lambda url: old)
    monkeypatch.setattr(build.sec, "get", lambda url: INST)
    monkeypatch.setattr(build, "submissions", lambda cik: {})
    monkeypatch.setattr(build, "recent_rows", lambda sub: [{"accessionNumber": accn, "form": "10-Q", "filingDate": "2026-07-29", "reportDate": "2026-06-30"}])
    monkeypatch.setattr(build.dims, "find_files", lambda cik, a: ("vrsk-20260630_htm.xml", None))
    fx = build.companyfacts(1442145, accn)
    assert fx["Revenues"][("2026-04-01", "2026-06-30")]["val"] == 806300000   # this quarter, from the instance
    assert fx["Revenues"][("2026-01-01", "2026-03-31")]["val"] == 772000000   # the one before, from company facts


def test_skipped_filings_are_queued_again_once(tmp_path, monkeypatch):
    store = build.Store(str(tmp_path))
    store.state["seen"] = {"0001437749-26-024749": {"t": "2026-10-08", "s": "skip: XBRL facts not available yet", "cik": 1442145},
                           "0001437749-26-024748": {"t": "2026-10-08", "s": "ok", "cik": 1442145}}
    monkeypatch.setattr(build, "submissions", lambda cik: {})
    monkeypatch.setattr(build, "recent_rows", lambda sub: [{"accessionNumber": "0001437749-26-024749", "form": "10-Q",
                                                            "filingDate": "2026-07-29", "reportDate": "2026-06-30"}])
    monkeypatch.setattr(build, "time_up", lambda *a, **k: False)
    build.requeue_missing_facts(store)
    assert store.state["pending"]["0001437749-26-024749"]["form"] == "10-Q"
    assert "0001437749-26-024749" not in store.state["seen"] and "0001437749-26-024748" in store.state["seen"]
    assert store.state["instance_requeue"] == build.INSTANCE_REQUEUE
