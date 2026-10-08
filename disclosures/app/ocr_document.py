"""Extract one PDF locally, optionally forcing OCR. Never uploads document contents."""
import argparse
from pathlib import Path
from congress import extract_pdf
from core import write_json
p=argparse.ArgumentParser();p.add_argument('pdf',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--force-ocr',action='store_true');p.add_argument('--max-pages',type=int,default=100)
a=p.parse_args();pages=extract_pdf(a.pdf,{'max_pdf_pages':a.max_pages,'ocr_dpi':200},a.force_ocr);write_json(a.output,pages)
print(f'Extracted {len(pages)} pages; '+', '.join(sorted({x['method']for x in pages})))
