#!/usr/bin/env python3
"""Local-only PDF/DOCX/TXT/MD research staging. NO automatic model labels or upload."""
import argparse,hashlib,json,re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

RULE=re.compile(r"(?i)\b(revenue|net sales|EBITDA|operating income|net income|EPS|free cash flow|capital expenditure)\b.{0,70}?(-?\$?\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|m|%)?)")

def extract(path):
    if path.suffix.lower() in (".txt",".md"):
        return path.read_text(encoding="utf-8",errors="replace")
    if path.suffix.lower()==".docx":
        with ZipFile(path) as z:
            root=ElementTree.fromstring(z.read("word/document.xml"))
        return "\n".join((node.text or "") for node in root.iter() if node.tag.endswith("}t"))
    if path.suffix.lower()==".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Install pypdf locally: pip install pypdf") from exc
        pdf=PdfReader(str(path))
        if len(pdf.pages)>200:raise ValueError("Report longer than 200 pages")
        return "\n".join((page.extract_text() or "") for page in pdf.pages)
    raise ValueError("Unrecognized document format")

def stage(inbox,metadata,out):
    details=json.loads(Path(metadata).read_text(encoding="utf-8"))
    findings=[];warnings=[]
    for p in sorted(Path(inbox).iterdir()):
        if not p.is_file() or p.suffix.lower() not in (".pdf",".docx",".txt",".md"):continue
        license_info=details.get(p.name,{})
        if license_info.get("ml_rights") not in ("owned","licensed_for_training","public_domain") or not license_info.get("rights_evidence"):
            warnings.append(f"{p.name}: missing documented permission");continue
        if p.stat().st_size>30_000_000:
            warnings.append(f"{p.name}: exceeds 30MB limit");continue
        try:
            content=extract(p)
        except (ValueError,RuntimeError,OSError,KeyError) as err:
            warnings.append(f"{p.name}: {type(err).__name__}");continue
        matches=[{"metric":m.group(1),"candidate_value":m.group(2),
                  "offset":m.start(),"human_verified":False}
                 for m in list(RULE.finditer(content))[:50]]
        findings.append({"filename":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                         "characters":len(content),"metadata":license_info,"candidates":matches,
                         "status":"PENDING_HUMAN_REVIEW",
                         "warning":"Regex values are unverified. Compare against original text, page, period and units."})
    destination=Path(out);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps({"documents":findings,"warnings":warnings},
                                     indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Staged {len(findings)} local reports. No training labels or uploads made.")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--inbox",required=True);p.add_argument("--metadata",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();stage(a.inbox,a.metadata,a.out)
