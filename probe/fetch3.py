"""Temporary: fetch SEC company facts for a few companies (facts ending 2017 or later), for testing the capital
allocation, dilution and debt maturity figures offline. Delete this branch afterwards."""
import gzip, json, os, time, urllib.request
CIKS = [320193, 789019, 21344, 18230, 66740, 19617, 1018724, 1318605, 1326801, 1045810, 1652044, 34088, 78003, 1730168,
        1341439, 732717, 104169, 354950, 1067983, 1321655, 1065280, 1403161, 909832, 753308, 726728, 1769628, 1744489,
        50863, 731766, 1551152, 1874178, 2488]
UA = os.environ.get("SEC_USER_AGENT") or "Filing Flows research"
os.makedirs("probe/facts3", exist_ok=True)
for cik in CIKS:
    req = urllib.request.Request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                                 headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        raw = urllib.request.urlopen(req, timeout=60).read()
        d = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    except Exception as e:
        print(cik, "failed", e); continue
    for tax in d.get("facts", {}).values():
        for body in tax.values():
            for u, fs in list(body.get("units", {}).items()):
                body["units"][u] = [f for f in fs if f.get("end", "") >= "2017-01-01"]
    with gzip.open(f"probe/facts3/{cik}.json.gz", "wt") as fh:
        json.dump(d, fh)
    print(cik, d.get("entityName"), os.path.getsize(f"probe/facts3/{cik}.json.gz"))
    time.sleep(0.25)
