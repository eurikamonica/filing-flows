"""Independent post-GitHub-Pages smoke audit; fail rather than assume publication.

Run after actions/deploy-pages has succeeded, not inside static artifact generation.
"""
import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import urlopen, Request

PROBES=[
    ("Gamma graph code","gamma.js","Network Graph"),
    ("13F quarter filters","app.js","data-own13-period"),
    ("Disclosure date controls","disclosures/app.js","discDateControls"),
    ("Kalshi/Polymarket filters","disclosures/consensus.js","cprob"),
    ("Supplier revenue page","supplier-revenue/index.html","Supplier Revenue"),
    ("Data-health page","integration-health/index.html","Production integration health"),
    ("Research snapshot metadata","data/industry-intelligence/integration-health.json",None)
]

def run(base, run_id=None, tries=6, sleep_s=12):
    base=base.rstrip("/")+"/"
    detail=[]
    for attempt in range(tries):
        checks=[]
        for name,path,needle in PROBES:
            url=urljoin(base,path)
            try:
                req=Request(url,headers={"Cache-Control":"no-cache",
                                         "User-Agent":"FilingFlows-IntegrationAudit/1.0"})
                with urlopen(req,timeout=15) as response:
                    data=response.read(8*1024*1024).decode("utf-8","replace")
                if needle is not None:
                    ok=needle in data
                else:
                    parsed=json.loads(data)
                    ok=(str(parsed.get("build_run_id"))==str(run_id) if run_id else bool(parsed.get("generated_at")))
                checks.append({"name":name,"ok":ok,"url":url,
                               "error":None if ok else "Missing marker or unexpected build id"})
            except (HTTPError,URLError,TimeoutError,ValueError,UnicodeDecodeError) as exc:
                checks.append({"name":name,"ok":False,"url":url,"error":str(exc)[:250]})
        detail=checks
        if all(k["ok"] for k in checks):
            break
        if attempt<tries-1:
            time.sleep(sleep_s)
    return {"status":"success" if all(k["ok"] for k in detail) else "failed",
            "base":base,"checks":detail}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base",required=True)
    p.add_argument("--run-id")
    args=p.parse_args()
    result=run(args.base,args.run_id)
    print(json.dumps(result,indent=2))
    import os
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("## Filing Flows production integration audit\n\n")
            f.write("Audit: **"+result["status"]+"**\n\n")
            f.write("| Check | Status | URL |\n|---|---|---|\n")
            for item in result["checks"]:
                f.write(f"| {item['name']} | {'PASS' if item['ok'] else 'FAIL'} | {item['url']} |\n")
    if result["status"]!="success":
        raise SystemExit(1)
if __name__=="__main__":
    main()
