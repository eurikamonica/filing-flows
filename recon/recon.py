"""One-off reconnaissance: fetch public disclosure portals and save raw responses for offline analysis."""
import json, os, re, sys, time, urllib.parse
import requests

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'
OUT = 'recon-out'
os.makedirs(OUT, exist_ok=True)
S = requests.Session()
S.headers.update({'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9'})
log = []

def get(name, url, **kw):
    t = time.time()
    try:
        r = S.get(url, timeout=60, allow_redirects=True, **kw)
        body = r.content
        ext = '.json' if 'json' in r.headers.get('content-type', '') else '.pdf' if 'pdf' in r.headers.get('content-type', '') else '.html'
        open(os.path.join(OUT, name + ext), 'wb').write(body[:3_000_000])
        log.append({'name': name, 'url': url, 'final_url': r.url, 'status': r.status_code, 'ctype': r.headers.get('content-type'), 'bytes': len(body), 'secs': round(time.time() - t, 1), 'set_cookie': r.headers.get('set-cookie', '')[:200]})
        print(name, r.status_code, r.url, len(body))
        return r
    except Exception as e:
        log.append({'name': name, 'url': url, 'error': repr(e)})
        print(name, 'ERROR', repr(e))

def post(name, url, data=None, json_body=None, headers=None):
    t = time.time()
    try:
        r = S.post(url, data=data, json=json_body, headers=headers or {}, timeout=60)
        ext = '.json' if 'json' in r.headers.get('content-type', '') else '.html'
        open(os.path.join(OUT, name + ext), 'wb').write(r.content[:3_000_000])
        log.append({'name': name, 'url': url, 'status': r.status_code, 'ctype': r.headers.get('content-type'), 'bytes': len(r.content), 'secs': round(time.time() - t, 1)})
        print(name, r.status_code, len(r.content))
        return r
    except Exception as e:
        log.append({'name': name, 'url': url, 'error': repr(e)})
        print(name, 'ERROR', repr(e))

# --- New York (COELIG) ---
get('ny_index', 'https://ethics.ny.gov/financial-disclosure-statements-elected-officials?page=0')
get('ny_index_2025', 'https://ethics.ny.gov/financial-disclosure-statements-elected-officials?f%5B0%5D=filter_term%3A2786&page=0')
get('ny_filing_page', 'https://ethics.ny.gov/2025-governor-kathleen-hochul')
get('ny_printable', 'https://public.ethics.ny.gov/FDS/Form/_ViewPrintable/880256/55292')
get('ny_fds_data', 'https://ethics.ny.gov/financial-disclosure-statement-data')

# --- California (FPPC Form 700, Granicus DisclosureDocs eRetrieval) ---
r = get('ca_home', 'https://form700search.fppc.ca.gov/')
if r is not None:
    for m in re.findall(r'(?:src|href|action)=["\']([^"\']+)["\']', r.text):
        print('  CA asset:', m)
    open(os.path.join(OUT, 'ca_assets.txt'), 'w').write('\n'.join(re.findall(r'(?:src|href|action)=["\']([^"\']+)["\']', r.text)))
for u in ['https://form700search.fppc.ca.gov/Home/Search', 'https://form700search.fppc.ca.gov/Search/Results', 'https://form700search.fppc.ca.gov/Home/GetFilers',
          'https://form700search.fppc.ca.gov/Home/Agencies', 'https://form700search.fppc.ca.gov/api/search', 'https://form700search.fppc.ca.gov/Home/Index']:
    get('ca_probe_' + re.sub(r'\W+', '_', u.split('.gov')[1]), u)
# the Granicus eRetrieval products commonly expose these
for u in ['https://form700search.fppc.ca.gov/Home/GetSearchResults', 'https://form700search.fppc.ca.gov/Home/FilerSearch']:
    post('ca_post_' + re.sub(r'\W+', '_', u.split('.gov')[1]), u, data={'filerName': 'Newsom', 'year': '2025'}, headers={'X-Requested-With': 'XMLHttpRequest'})

# --- Texas (TEC) ---
get('tx_pfs', 'https://www.ethics.texas.gov/filers/state/pfs/')
get('tx_search_pfs', 'https://www.ethics.texas.gov/search/pfs/')
get('tx_efile_public', 'https://prd.tecprd.ethicsefile.com/TECFilerWeb/pages/public/pfs.jsf')
get('tx_efile_root', 'https://prd.tecprd.ethicsefile.com/File/')
get('tx_pfs_list', 'https://www.ethics.texas.gov/data/filinginfo/NTF/2025/Officeholders-2025PFSReminder.pdf')
get('tx_api_probe', 'https://www.ethics.texas.gov/api/v1/search?q=personal%20financial%20statement')
get('tx_pfsindex', 'https://www.ethics.state.tx.us/forms/PFSindex.php')
get('tx_pfs_viewer', 'https://www.ethics.state.tx.us/php/pfs.php')
get('tx_pfs_search2', 'https://www.ethics.state.tx.us/search/pfs/')

# --- Canada: Office of the Conflict of Interest and Ethics Commissioner public registry ---
get('ca_reg_home', 'https://prciec-rpccie.parl.gc.ca/EN/PublicRegistries/Pages/PublicRegistryHome.aspx')
get('ca_reg_poh', 'https://prciec-rpccie.parl.gc.ca/EN/PublicRegistries/Pages/PublicOfficeHoldersList.aspx')
get('ca_reg_members', 'https://prciec-rpccie.parl.gc.ca/EN/PublicRegistries/Pages/MembersList.aspx')
get('ca_reg_search', 'https://prciec-rpccie.parl.gc.ca/EN/PublicRegistries/Pages/Search.aspx')
get('ca_reg_root', 'https://prciec-rpccie.parl.gc.ca/')
get('ciec_home', 'https://ciec-ccie.parl.gc.ca/en/home')
get('ciec_registry', 'https://ciec-ccie.parl.gc.ca/en/publications/Pages/PublicRegistry-RegistrePublic.aspx')

# --- Canada: SEDI ---
get('sedi_root', 'https://www.sedi.ca/sedi/SVTSelectInsiderIssuerType?locale=en_CA')
get('sedi_home', 'https://www.sedi.ca/')
# --- Canada: SEDAR+ public search (for reference) ---
get('sedarplus', 'https://www.sedarplus.ca/csa-party/service/create.html?targetAppCode=csa-party&service=searchDocuments')

# --- Prices ---
get('stooq_aapl', 'https://stooq.com/q/d/l/?s=aapl.us&i=d')
get('stooq_brk', 'https://stooq.com/q/d/l/?s=brk-b.us&i=d')
get('yahoo_aapl', 'https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=3mo&interval=1d')
get('sec_tickers', 'https://www.sec.gov/files/company_tickers.json', headers={'User-Agent': 'Eurika eurikamonica@gmail.com'})
post('openfigi', 'https://api.openfigi.com/v3/mapping', json_body=[{'idType': 'ID_CUSIP', 'idValue': '037833100'}], headers={'Content-Type': 'application/json'})

json.dump(log, open(os.path.join(OUT, '_log.json'), 'w'), indent=1)
print(json.dumps(log, indent=1))

# ---- digest to stdout (artifacts/pushes are not reachable from the analysis side) ----
import html as _html
def digest(path):
    raw = open(path, 'rb').read()
    try: t = raw.decode('utf-8', 'replace')
    except Exception: t = ''
    print('\n' + '=' * 100 + '\n### ' + path + ' (' + str(len(raw)) + ' bytes)')
    if path.endswith('.json') or path.endswith('.pdf') or 'stooq' in path:
        print(t[:1500]); return
    for tag in ['form', 'input', 'select', 'script', 'a', 'iframe', 'link']:
        items = re.findall(r'<' + tag + r'\b[^>]*>', t, re.I)
        keep = []
        for it in items:
            if tag == 'a':
                h = re.search(r'href=["\']([^"\']+)', it, re.I)
                if not h: continue
                hv = h.group(1)
                if hv.startswith('#') or 'javascript:' in hv: continue
                keep.append(hv)
            elif tag == 'script':
                s = re.search(r'src=["\']([^"\']+)', it, re.I)
                if s: keep.append(s.group(1))
            elif tag == 'link':
                s = re.search(r'href=["\']([^"\']+)', it, re.I)
                if s and 'css' not in s.group(1): keep.append(s.group(1))
            else:
                keep.append(it[:300])
        keep = list(dict.fromkeys(keep))
        if keep:
            print('--', tag, len(keep))
            for k in keep[:80]: print('   ', k)
    for m in re.findall(r'(?:url|endpoint|api)[A-Za-z]*\s*[:=]\s*["\']([^"\']{4,160})["\']', t, re.I)[:40]:
        print('   js-url:', m)
    text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', t, flags=re.S | re.I)
    text = _html.unescape(re.sub(r'<[^>]+>', ' ', text))
    text = re.sub(r'\s+', ' ', text)
    print('-- text:', text[:2500])
for f in sorted(os.listdir(OUT)):
    if f.startswith('_'): continue
    digest(os.path.join(OUT, f))
