"""Fetch 20-F / 6-K samples from SEC for building the foreign-filer reader (temporary probe)."""
import gzip, json, os, re, sys, time, urllib.request

UA = os.environ.get("SEC_USER_AGENT") or "Filing Flows research filingflows@gmail.com"
COS = {1513845: "NBIS", 1015922: "CHKP", 1639920: "SPOT", 1046179: "TSM"}
OUT = "samples"
os.makedirs(OUT, exist_ok=True)
last = [0.0]


def get(url, binary=False):
    wait = 0.15 - (time.time() - last[0])
    if wait > 0:
        time.sleep(wait)
    last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
    return data if binary else data.decode("utf-8", "replace")


def save(name, text):
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if name.endswith(".gz"):
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(text)
    else:
        open(path, "w", encoding="utf-8").write(text)


log = []
for cik, tk in COS.items():
    c10 = f"{cik:010d}"
    try:
        sub = get(f"https://data.sec.gov/submissions/CIK{c10}.json")
        save(f"{tk}/submissions.json", sub)
        facts = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c10}.json")
        save(f"{tk}/companyfacts.json.gz", facts)
    except Exception as e:
        log.append(f"{tk} submissions/facts failed: {e}")
        continue
    s = json.loads(sub)
    r = s["filings"]["recent"]
    rows = [{k: r[k][i] for k in r} for i in range(len(r["form"]))]
    six = [x for x in rows if x["form"] == "6-K"][:40 if tk in ("NBIS", "CHKP") else 16]
    twenty = [x for x in rows if x["form"] in ("20-F", "40-F")][:2]
    log.append(f"{tk}: fye {s.get('fiscalYearEnd')} forms {sorted(set(x['form'] for x in rows))[:30]} 6-K {len(six)} 20-F {len(twenty)}")
    for x in six + twenty:
        acc = x["accessionNumber"]
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
        try:
            idx = get(base + "/index.json")
            save(f"{tk}/{acc}/index.json", idx)
            items = [i["name"] for i in json.loads(idx).get("directory", {}).get("item", [])]
            htm = [n for n in items if re.search(r"\.html?$", n, re.I) and "index" not in n.lower()]
            if x["form"] == "6-K":
                for n in htm[:4]:
                    body = get(base + "/" + n)
                    if len(body) < 3_000_000:
                        save(f"{tk}/{acc}/{n}", body)
            else:
                log.append(f"  {tk} {x['form']} {acc} report {x.get('reportDate')} primary {x.get('primaryDocument')} files {htm[:6]}")
        except Exception as e:
            log.append(f"  {tk} {acc} failed: {e}")
save("log.txt", "\n".join(log))
print("\n".join(log))
