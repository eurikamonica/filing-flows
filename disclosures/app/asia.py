"""Customers and suppliers named by companies listed in Japan, Taiwan, Korea and Hong Kong — the other side of the US
supply chain, from their own annual reports:

    jp  EDINET 有価証券報告書: 主要な販売先 (customers above 10% of sales: name, 販売高, 割合)       app/asia_jp.py
    kr  DART 사업보고서: 주요 매출처 / 매입처 (names, often with shares)                          app/asia_kr.py
    tw  MOPS 年報: 最近二年度主要進銷貨客戶名單 (10%+ customers and suppliers, often anonymised)   app/asia_tw.py
    hk  HKEXnews annual reports: largest customer / five largest customers (and suppliers) as a
        share of sales (purchases) — Listing Rules Appendix D2 para 31; names only sometimes       app/asia_hk.py

A row such as "アップル 販売高 512,345百万円 割合 21.3%" in a Japanese supplier's report is a stated money flow: Apple →
that supplier, ¥512bn a year. Counterparty names are matched to US-listed companies (SEC filers on the site) through
their names in English and in Japanese, Chinese and Korean (ALIASES); anything not matched stays a label.

    collect   lists each market's annual reports since the last run and reads the queue, newest first (cache/<mk>.json,
              one result per report id; Japan and Korea only with their free API keys: EDINET_API_KEY, DART_API_KEY)
    build     public/index.json (every named relation), public/c/<cik>.json (per US company: who in Asia names it as a
              customer or supplier, and how much), public/companies.json (each Asian company's latest disclosure,
              concentration shares included), public/status.json

    python disclosures/app/asia.py collect --root asia --minutes 40 [--markets jp,kr,tw,hk]
    python disclosures/app/asia.py build --root asia --universe site/index.json
"""
import argparse
import datetime as dt
import importlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json  # noqa: E402

MARKETS = ('jp', 'kr', 'tw', 'hk')
KEYS = {'jp': 'EDINET_API_KEY', 'kr': 'DART_API_KEY'}
NEED_KEY = {'jp'}                      # Korea reads the public DART viewer without a key (slower); with one, OpenDART
NAMES = {'jp': 'Japan', 'kr': 'Korea', 'tw': 'Taiwan', 'hk': 'Hong Kong'}
FIRST_DAYS = 420                       # the first run lists a little over a year: every company's latest annual report
# US dollars per unit, approximate 2025 averages (Federal Reserve H.10): amounts are shown in both currencies
USD = {'USD': 1.0, 'JPY': 1 / 150.0, 'KRW': 1 / 1400.0, 'TWD': 1 / 31.5, 'HKD': 1 / 7.8, 'CNY': 1 / 7.2, 'RMB': 1 / 7.2, 'EUR': 1.13}
FX_NOTE = 'Converted at approximate 2025 average exchange rates (Federal Reserve H.10): ¥150, ₩1,400, NT$31.5, HK$7.8, RMB 7.2 per US dollar.'

# ---------------------------------------------------------------- names of US-listed companies in Asian reports
# ticker → names as they appear in Japanese, Chinese (traditional and simplified) and Korean reports, and English forms
ALIASES = {
    'AAPL': ['Apple', 'Apple Inc', 'アップル', 'アップル・インク', 'アップルインク', '蘋果', '苹果', '애플'],
    'NVDA': ['NVIDIA', 'Nvidia', 'エヌビディア', '輝達', '辉达', '英偉達', '英伟达', '엔비디아'],
    'INTC': ['Intel', 'インテル', '英特爾', '英特尔', '인텔'],
    'MSFT': ['Microsoft', 'マイクロソフト', '微軟', '微软', '마이크로소프트'],
    'AMZN': ['Amazon', 'アマゾン', '亞馬遜', '亚马逊', '아마존'],
    'GOOGL': ['Google', 'Alphabet', 'グーグル', '谷歌', '구글'],
    'META': ['Meta', 'Meta Platforms', 'Facebook', 'メタ', '메타'],
    'TSLA': ['Tesla', 'テスラ', '特斯拉', '테슬라'],
    'GM': ['General Motors', 'GM', 'ゼネラルモーターズ', 'ゼネラル・モーターズ', '通用汽車', '通用汽车', '제너럴모터스', '제너럴 모터스'],
    'F': ['Ford', 'Ford Motor', 'フォード', '福特', '포드'],
    'QCOM': ['Qualcomm', 'クアルコム', '高通', '퀄컴'],
    'AVGO': ['Broadcom', 'ブロードコム', '博通', '브로드컴'],
    'AMD': ['AMD', 'Advanced Micro Devices', '超微', '美商超微', '超威', '超威半导体'],
    'MU': ['Micron', 'マイクロン', '美光', '마이크론'],
    'TXN': ['Texas Instruments', 'テキサス・インスツルメンツ', 'テキサスインスツルメンツ', '德州儀器', '德州仪器'],
    'AMAT': ['Applied Materials', 'アプライドマテリアルズ', 'アプライド マテリアルズ', '應用材料', '应用材料', '어플라이드 머티어리얼즈'],
    'LRCX': ['Lam Research', 'ラムリサーチ', 'ラム・リサーチ', '科林研發', '泛林'],
    'KLAC': ['KLA', 'ケーエルエー', '科磊'],
    'HPQ': ['HP Inc', 'HP', 'Hewlett-Packard', 'ヒューレット・パッカード', '惠普', 'HP Inc.'],
    'HPE': ['Hewlett Packard Enterprise', 'HPE', '慧與'],
    'DELL': ['Dell', 'Dell Technologies', 'デル', '戴爾', '戴尔', '델'],
    'CSCO': ['Cisco', 'シスコ', 'シスコシステムズ', '思科', '시스코'],
    'WMT': ['Walmart', 'Wal-Mart', 'ウォルマート', '沃爾瑪', '沃尔玛', '월마트'],
    'HD': ['Home Depot', 'The Home Depot', 'ホーム・デポ', 'ホームデポ', '家得寶', '家得宝'],
    'COST': ['Costco', 'コストコ', '好市多', '开市客', '코스트코'],
    'BBY': ['Best Buy', 'ベストバイ', '百思買', '百思买', '베스트바이'],
    'VZ': ['Verizon', 'ベライゾン', '威訊', '버라이즌'],
    'T': ['AT&T', 'エイ・ティ・アンド・ティ'],
    'TMUS': ['T-Mobile', 'Tモバイル', 'T-モバイル'],
    'BA': ['Boeing', 'ボーイング', '波音', '보잉'],
    'GE': ['General Electric', 'GE Aerospace', 'ゼネラル・エレクトリック', '奇異'],
    'CAT': ['Caterpillar', 'キャタピラー', '開拓重工', '卡特彼勒', '캐터필러'],
    'DE': ['Deere', 'John Deere', 'ディア', 'ジョンディア'],
    'HON': ['Honeywell', 'ハネウェル', '漢威聯合', '霍尼韦尔'],
    'MMM': ['3M', 'スリーエム'],
    'PG': ['Procter & Gamble', 'P&G', 'プロクター・アンド・ギャンブル', '寶僑', '宝洁'],
    'NKE': ['Nike', 'ナイキ', '耐吉', '耐克', '나이키'],
    'GLW': ['Corning', 'コーニング', '康寧', '康宁', '코닝'],
    'WDC': ['Western Digital', 'ウエスタンデジタル', 'ウェスタンデジタル', '威騰', '西部数据'],
    'STX': ['Seagate', 'シーゲイト', 'シーゲート', '希捷'],
    'ORCL': ['Oracle', 'オラクル', '甲骨文', '오라클'],
    'IBM': ['IBM', '日本アイ・ビー・エム'],
    'NFLX': ['Netflix', 'ネットフリックス', '網飛', '넷플릭스'],
    'DIS': ['Disney', 'Walt Disney', 'ディズニー', '迪士尼', '디즈니'],
    'SBUX': ['Starbucks', 'スターバックス', '星巴克', '스타벅스'],
    'MCD': ["McDonald's", 'マクドナルド', '麥當勞', '麦当劳', '맥도날드'],
    'KO': ['Coca-Cola', 'コカ・コーラ', '可口可樂', '可口可乐', '코카콜라'],
    'PEP': ['PepsiCo', 'ペプシコ', '百事', '펩시'],
    'TGT': ['Target', 'ターゲット', '塔吉特'],
    'LOW': ["Lowe's", 'ロウズ', '勞氏'],
    'SMCI': ['Super Micro', 'Supermicro', 'Super Micro Computer', '美超微', 'スーパー・マイクロ'],
    'ANET': ['Arista', 'Arista Networks', 'アリスタ'],
    'MRVL': ['Marvell', 'マーベル', '邁威爾', '迈威尔'],
    'ADI': ['Analog Devices', 'アナログ・デバイセズ', '亞德諾', '亚德诺'],
    'ON': ['ON Semiconductor', 'onsemi', 'オン・セミコンダクター', '安森美'],
    'SWKS': ['Skyworks', 'スカイワークス', '思佳訊'],
    'QRVO': ['Qorvo', 'コルボ', '威訊聯合'],
    'CRUS': ['Cirrus Logic', 'シーラス・ロジック'],
    'JBL': ['Jabil', 'ジェイビル', '捷普'],
    'FLEX': ['Flex', 'Flextronics', 'フレックス', '偉創力', '伟创力'],
    'SANM': ['Sanmina', 'サンミナ', '新美亞'],
    'WHR': ['Whirlpool', 'ワールプール', '惠而浦'],
    'SWK': ['Stanley Black & Decker', 'スタンレー・ブラック・アンド・デッカー', '史丹利百得'],
    'GRMN': ['Garmin', 'ガーミン', '台灣國際航電', '佳明'],
    'PFE': ['Pfizer', 'ファイザー', '輝瑞', '辉瑞', '화이자'],
    'MRK': ['Merck', 'Merck & Co', 'メルク', '默沙東'],
    'LLY': ['Eli Lilly', 'Lilly', 'イーライリリー', '禮來', '礼来', '일라이 릴리'],
    'JNJ': ['Johnson & Johnson', 'ジョンソン・エンド・ジョンソン', '嬌生', '强生', '존슨앤드존슨'],
    'ABT': ['Abbott', 'アボット', '亞培', '雅培'],
    'MDT': ['Medtronic', 'メドトロニック', '美敦力'],
    'MRNA': ['Moderna', 'モデルナ', '莫德納', '모더나'],
    'AMGN': ['Amgen', 'アムジェン', '安進', '암젠'],
    'BMY': ['Bristol-Myers Squibb', 'ブリストル・マイヤーズ スクイブ', '必治妥'],
    'GILD': ['Gilead', 'ギリアド', '吉利德'],
    'XOM': ['ExxonMobil', 'Exxon Mobil', 'エクソンモービル', '埃克森美孚', '엑슨모빌'],
    'CVX': ['Chevron', 'シェブロン', '雪佛龍', '쉐브론'],
    'LMT': ['Lockheed Martin', 'ロッキード・マーティン', '洛克希德', '록히드마틴'],
    'RTX': ['RTX', 'Raytheon', 'レイセオン', '雷神'],
    'NOC': ['Northrop Grumman', 'ノースロップ・グラマン'],
    'GD': ['General Dynamics', 'ジェネラル・ダイナミクス'],
    'UPS': ['UPS', 'United Parcel Service'],
    'FDX': ['FedEx', 'フェデックス', '聯邦快遞'],
    'UBER': ['Uber', 'ウーバー', '優步'],
    'ABNB': ['Airbnb', 'エアビーアンドビー'],
    'PYPL': ['PayPal', 'ペイパル'],
    'V': ['Visa', 'ビザ'],
    'MA': ['Mastercard', 'マスターカード'],
    'CRM': ['Salesforce', 'セールスフォース'],
    'ADBE': ['Adobe', 'アドビ'],
    'QSR': ['Burger King'],
    'TSM': ['TSMC', 'Taiwan Semiconductor', '台積電', '台积电', '台湾積体電路製造', '台湾積体電路', 'TSMC Arizona'],
    'SONY': ['Sony', 'ソニー', 'ソニーグループ', '索尼', '소니'],
    'TM': ['Toyota', 'トヨタ自動車', 'トヨタ', '豐田', '丰田', '도요타'],
    'HMC': ['Honda', '本田技研工業', 'ホンダ', '本田', '혼다'],
    'ASML': ['ASML', 'エーエスエムエル', '艾司摩爾', '阿斯麦'],
    'UMC': ['UMC', 'United Microelectronics', '聯電', '聯華電子', '联电'],
    'ASX': ['ASE', 'ASE Technology', '日月光', '日月光投控'],
    'NXPI': ['NXP', 'NXP Semiconductors', 'エヌエックスピー', '恩智浦'],
    'STM': ['STMicroelectronics', 'STマイクロ', '意法半導體', '意法半导体'],
    'NOK': ['Nokia', 'ノキア', '諾基亞', '诺基亚', '노키아'],
    'ERIC': ['Ericsson', 'エリクソン', '愛立信', '爱立信', '에릭슨'],
    'BABA': ['Alibaba', 'アリババ', '阿里巴巴', '알리바바'],
    'PDD': ['PDD', 'Temu', '拼多多'],
    'JD': ['JD.com', '京東', '京东'],
    'NIO': ['NIO', '蔚來', '蔚来'],
    'STLA': ['Stellantis', 'ステランティス', '斯泰蘭蒂斯', '스텔란티스'],
}
_SUFFIX = re.compile(r'(?i)[\s,.]*(?:incorporated|inc|corporation|corp|company|co|ltd|limited|llc|plc|holdings?|group|n\.?v|s\.?a|ag|se|'
                     r'株式会社|（株）|\(株\)|㈱|有限公司|股份有限公司|公司|주식회사|㈜|\(주\))\.?\s*$')


def norm(s):
    """A name compared: full-width to half-width, lower case, company suffixes and punctuation out."""
    s = unicodedata.normalize('NFKC', str(s or '')).strip()
    s = re.sub(r'^(?:株式会社|㈱|\(株\)|（株）|주식회사|㈜|\(주\)|美商|日商|韓商|台灣|臺灣)\s*', '', s)
    for _ in range(3):
        s2 = _SUFFIX.sub('', s)
        if s2 == s:
            break
        s = s2
    s = re.sub(r'(?i)\b(?:the)\b', '', s)
    s = re.sub(r'[\s・,.\-\'’&()（）「」]+', '', s).lower()
    return s


# what may follow a parent's name in a subsidiary's ("Apple Operations International", "Google Asia Pacific", "アップルジャパン")
SUBSID = (r'^(?:社|グループ|集團|集团|及其|그룹|及|コリア|ジャパン|合同会社|日本|台灣|台湾|中国|中國|코리아|operations|international|inc|asia|'
          r'asiapacific|japan|korea|taiwan|china|singapore|ireland|europe|emea|americas|usa|us|global|technology|technologies|'
          r'semiconductor|services|sales|distribution|manufacturing|holdings|\(|（)')


class Matcher:
    """Counterparty label → (cik, ticker, name) of a company on the site, or None. Aliases first, then the exact
    normalised English name of an SEC filer; a label of fewer than 3 characters (A社, 甲) never matches."""

    def __init__(self, universe):
        self.by_t, self.by_n = {}, {}
        for c in universe:
            t = str(c.get('ticker') or '').upper()
            if t and t not in self.by_t:
                self.by_t[t] = c
            n = norm(c.get('name'))
            if len(n) >= 4 and n not in self.by_n:
                self.by_n[n] = c
        self.alias = {}
        for t, names in ALIASES.items():
            if t in self.by_t:
                for n in names:
                    k = norm(n)
                    if k:
                        self.alias.setdefault(k, self.by_t[t])
        self.long = sorted(((a, c) for a, c in self.alias.items() if len(a) >= 4), key=lambda kv: -len(kv[0]))

    def __call__(self, label):
        k = norm(label)
        if len(k) < 2 or re.fullmatch(r'[a-z]|[甲乙丙丁戊己庚]|客戶[a-z0-9]+|顧客[a-z0-9]+|[a-z]社|[a-z]公司', k):
            return None
        c = self.alias.get(k) or self.by_n.get(k)
        if not c and k.startswith('日本') and len(k) > 4:     # 日本マイクロソフト, 日本オラクル: the Japanese subsidiary
            c = self.alias.get(k[2:]) or self.by_n.get(k[2:])
        if not c:                                   # "Apple Inc. 及其子公司", "アップル社", "Apple Operations International"
            for a, cc in self.long:
                if (k.startswith(a) and re.match(SUBSID, k[len(a):] or '社')):
                    c = cc
                    break
        return c


# ---------------------------------------------------------------- network
class Http:
    """GET/POST with a polite pause per host, retries on 429/5xx; None on 404."""

    def __init__(self, ua=None, gap=0.35):
        self.ua = ua or os.environ.get('SEC_USER_AGENT') or 'Filing Flows research (https://filing-flows.com)'
        self.gap, self.last = gap, defaultdict(float)

    def _do(self, url, params=None, headers=None, data=None):
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        host = urllib.parse.urlparse(url).netloc
        for attempt in range(4):
            time.sleep(max(0.0, self.gap - (time.monotonic() - self.last[host])))
            self.last[host] = time.monotonic()
            try:
                body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
                req = urllib.request.Request(url, data=body, headers={'User-Agent': self.ua, 'Accept-Encoding': 'identity', **(headers or {})})
                with urllib.request.urlopen(req, timeout=90) as r:
                    return r.read(80 * 1024 * 1024)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code not in (403, 429, 500, 502, 503, 504) or attempt == 3:
                    raise
                time.sleep(3 * 2 ** attempt)
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        return None

    def get(self, url, params=None, headers=None):
        return self._do(url, params, headers)

    def post(self, url, data=None, headers=None):
        return self._do(url, None, headers, data if data is not None else b'')


def module(mk):
    return importlib.import_module('asia_' + mk)


# ---------------------------------------------------------------- collect
def collect(root, markets=MARKETS, minutes=40, http=None, today=None):
    root = Path(root)
    t0 = time.monotonic()
    http = http or Http()
    today = today or dt.date.today()
    state = read_json(root / 'cache' / 'state.json', {}) or {}
    stats = {}
    live = [mk for mk in markets if mk not in NEED_KEY or os.environ.get(KEYS[mk])]
    for mk in markets:
        if mk not in live:
            stats[mk] = {'skipped': f'no {KEYS[mk]} (free key: see the workflow file)'}
    budget = minutes * 60 / max(len(live), 1)
    for mk in live:
        m0 = time.monotonic()
        try:
            M = module(mk)
        except ImportError as e:
            stats[mk] = {'skipped': f'no reader ({e})'}
            continue
        key = os.environ.get(KEYS[mk]) if KEYS.get(mk) else None
        st = state.setdefault(mk, {'listed': None, 'queue': []})
        got = read_json(root / 'cache' / f'{mk}.json', {}) or {}
        s = {'listed': 0, 'read': 0, 'found': 0, 'errors': 0}
        since = st.get('listed') or (today - dt.timedelta(days=FIRST_DAYS)).isoformat()
        until = today.isoformat()
        if since <= until:
            try:
                reps = M.list_reports(http, since, until, key=key) or []
                have = {r['id'] for r in st['queue']} | set(got)
                new = [r for r in reps if r.get('id') and r['id'] not in have]
                prio = {r['id']: r.get('prio') or 0 for r in reps if r.get('id')}
                for r in st['queue']:                       # a size the market gives (Taiwan: paid-in capital)
                    r['prio'] = prio.get(r['id'], r.get('prio') or 0)
                st['queue'] = sorted(st['queue'] + new, key=lambda r: (r.get('filed') or '', r.get('prio') or 0), reverse=True)
                st['listed'] = until
                s['listed'] = len(new)
            except Exception as e:                  # noqa: BLE001 — the reading below still runs on the queue
                s['errors'] += 1
                print(f'asia {mk} list: {str(e)[:200]}', flush=True)
        keep = []
        for rep in st['queue']:
            if time.monotonic() - m0 > budget or time.monotonic() - t0 > minutes * 60:
                keep.append(rep)
                continue
            try:
                r = M.read_report(http, rep, key=key)
                got[rep['id']] = _slim(r, rep) if r else None
                s['read'] += 1
                s['found'] += 1 if r and (r.get('rows') or r.get('concentration')) else 0
            except Exception as e:                  # noqa: BLE001
                s['errors'] += 1
                rep['tries'] = rep.get('tries', 0) + 1
                if rep['tries'] < 3:
                    keep.append(rep)
                print(f'asia {mk} {rep.get("id")}: {str(e)[:160]}', flush=True)
            if s['read'] and s['read'] % 100 == 0:
                write_json(root / 'cache' / f'{mk}.json', got)
        st['queue'] = keep
        s['queued'] = len(keep)
        write_json(root / 'cache' / f'{mk}.json', got)
        stats[mk] = s
    write_json(root / 'cache' / 'state.json', state)
    stats['seconds'] = round(time.monotonic() - t0)
    return stats


def _slim(r, rep):
    out = {k: r.get(k) for k in ('code', 'name', 'name_en', 'fy', 'currency', 'revenue', 'concentration')}
    out['filed'] = rep.get('filed')
    out['url'] = r.get('url') or rep.get('url')
    out['rows'] = [{k: x.get(k) for k in ('role', 'label', 'amount', 'share', 'year', 'sentence', 'anonymous')} for x in (r.get('rows') or [])][:40]
    for x in out['rows']:
        x['sentence'] = (x.get('sentence') or '')[:400]
    return out


# ---------------------------------------------------------------- build
def build(root, universe_path, out=None):
    root = Path(root)
    out = Path(out or root / 'public')
    uni = read_json(universe_path, {}) or {}
    cos = uni.get('companies') if isinstance(uni, dict) else uni
    match = Matcher(cos or [])
    rels, companies, per_us = [], [], defaultdict(lambda: {'customers': [], 'suppliers': []})
    counts = {}
    for mk in MARKETS:
        got = read_json(root / 'cache' / f'{mk}.json', {}) or {}
        latest = {}
        for rid, r in got.items():
            if not r or not r.get('code'):
                continue
            k = r['code']
            if k not in latest or (r.get('fy') or '', r.get('filed') or '') > (latest[k].get('fy') or '', latest[k].get('filed') or ''):
                latest[k] = r
        n_named = n_matched = 0
        for code, r in latest.items():
            cur = (r.get('currency') or module_currency(mk)).upper()
            fx = USD.get(cur)
            self_sec = match(r.get('name_en')) or match(r.get('name'))
            co = {'mk': mk, 'code': code, 'name': r.get('name'), 'name_en': r.get('name_en'), 'fy': r.get('fy'), 'filed': r.get('filed'),
                  'currency': cur, 'revenue': r.get('revenue'), 'url': r.get('url'), 'conc': r.get('concentration') or {},
                  'sec': {'cik': int(self_sec['cik']), 't': self_sec.get('ticker')} if self_sec else None, 'named': 0}
            for x in r.get('rows') or []:
                if x.get('anonymous') or junk(x.get('label')):
                    continue
                c = match(x.get('label'))
                amount = x.get('amount')
                if amount is None and x.get('share') is not None and r.get('revenue') and x.get('role') == 'customer':
                    amount = x['share'] * r['revenue']                 # share × the seller's revenue
                    est = True
                else:
                    est = False
                row = {'mk': mk, 'code': code, 'name': r.get('name'), 'name_en': r.get('name_en'), 'role': x.get('role'),
                       'label': x.get('label'), 'share': x.get('share'), 'amount': amount, 'currency': cur,
                       'usd': round(amount * fx) if amount is not None and fx else None, 'computed': est, 'year': x.get('year') or r.get('fy'),
                       'fy': r.get('fy'), 'url': r.get('url'), 'q': x.get('sentence'),
                       'cik': int(c['cik']) if c else None, 't': c.get('ticker') if c else None, 'us_name': c.get('name') if c else None,
                       'self': co['sec']}
                rels.append(row)
                co['named'] += 1
                n_named += 1
                if c:
                    n_matched += 1
                    # the Asian company says the US company is its customer → it supplies the US company, and back
                    per_us[int(c['cik'])]['suppliers' if x.get('role') == 'customer' else 'customers'].append(row)
            companies.append(co)
        counts[mk] = {'companies': len(latest), 'named': n_named, 'matched_us': n_matched,
                      'with_concentration': sum(1 for c in companies if c['mk'] == mk and c['conc'])}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'c').mkdir(exist_ok=True)
    for old in (out / 'c').glob('*.json'):
        old.unlink()
    for cik, d in per_us.items():
        for k in d:
            d[k].sort(key=lambda r: -(r.get('usd') or 0))
        write_json(out / 'c' / f'{cik}.json', {'cik': cik, 'generated_at': now(), 'fx_note': FX_NOTE, **d})
    fields = ['mk', 'code', 'name', 'name_en', 'role', 'label', 'share', 'amount', 'currency', 'usd', 'computed', 'year', 'url', 'cik', 't']
    rels.sort(key=lambda r: -(r.get('usd') or 0))
    write_json(out / 'index.json', {'generated_at': now(), 'fields': fields, 'rows': [[r.get(f) for f in fields] for r in rels],
                                    'fx_note': FX_NOTE, 'markets': NAMES})
    write_json(out / 'companies.json', {'generated_at': now(), 'companies': companies})
    st = {'built_at': now(), 'markets': counts, 'relations': len(rels), 'us_companies': len(per_us)}
    write_json(out / 'status.json', st)
    return st


# not a counterparty: table words, totals, units, kinds of customer ("지자체" local governments, "가맹점" franchisees)
JUNK = re.compile(r'^(?:from|to|the|total|others?|other customers?|(?:rmb|hk\$|us\$|nt\$|usd)\s?[\d.,]+.*|rmb|hk\$|us\$|ntd?|usd|[\d.,%\s"“”\'-]+|.*(?:\d[\d,.]*\s*%|百分之|低\s*於|未有達|其他|合計|小計|'
                  r'營收淨額|銷貨淨額|進貨淨額|供應商$|客戶$|原料供應商$)|지자체|가맹점|건설업|상품|제품|교육기관|관공서|정부|개인|기타|국내|해외|.*부문|'
                  r'[\d]+\s*\D{0,2}份有限公司.*|^\d[\u4e00-\u9fff].*)$', re.I)


def junk(label):
    s = str(label or '').strip().strip('"“”\' ')
    return len(s) < 2 or bool(JUNK.match(s)) or bool(re.match(r'^[A-Z]?\d{3,}$', s))


def module_currency(mk):
    return {'jp': 'JPY', 'kr': 'KRW', 'tw': 'TWD', 'hk': 'HKD'}[mk]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--minutes', type=float, default=40)
    c.add_argument('--markets', default=','.join(MARKETS))
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--universe', required=True)
    a = ap.parse_args()
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, [m for m in a.markets.split(',') if m in MARKETS], a.minutes)), flush=True)
    else:
        print(json.dumps(build(a.root, a.universe)), flush=True)


if __name__ == '__main__':
    main()
