"""Guidance in an earnings release: what changed (in words and in numbers) and the ranges themselves.

A release says how its outlook moved in many ways — "raises", "lifts", "trims", "narrows", "tightens", "widens",
"raising the low end", "improves the midpoint", "reaffirms", "initiates", "now expects", "withdraws" — and gives the
numbers as "$3.75 billion to $3.77 billion", "$565-$585 million", "between $815 million and $855 million",
"$65.0 billion, plus or minus 2%", "at least $290 million", "approximately 23%", "18% to 20%" or an outlook table.
This module reads both:

  read(paras)       → {'label', 'tags', 'quote', 'items'}: the change words found in the release and, per metric,
                       the guided range with the prior range when the release states it ("from $6.85-$7.05").
  compare(cur, old) → raised / lowered / reaffirmed, narrowed / widened, which end moved: from the numbers alone, so a
                       range that moved without a word about it is not missed.
  diff(items, earlier) fills each item's prior range from an earlier release of the same company (same metric, basis,
                       period and unit) when the release itself does not state it, and sets each item's change.

Items: {metric, name, basis ('GAAP' | 'non-GAAP' | ''), period ('Q4 2026', 'Q3 FY2027', 'FY2026', ''), unit ('usd',
'pct', 'ps' per share, 'growth' % y/y, 'bps' change in basis points, 'x' a multiple), lo, hi, approx, bound ('min' |
'max'), scope ('' the whole company | 'segment' | 'organic'), said (the change word of its own sentence), prior {lo, hi,
src}, change, range, ends, quote}. Fixed rules, no model: a sentence it cannot read is left out rather than guessed.
"""
import re

VERSION = 3                   # bump when read() changes: the releases kept (app/guidance_history.py) are read again
                              # 2: a comparison base ("compared with … fourth quarter 2025") no longer dates the guide
                              # 3: the audit of the largest companies' releases — the base figures a guide is built on
                              #    ("based on the following Q3 FY26 figures") are not guides; a short heading or table
                              #    header names the section's period ("Third quarter", "Consolidated metric Q3 FY27", "For
                              #    the third quarter of 2026, we expect:"); a quarter ending on a date; tables of versions
                              #    ("Original … As of … As of …", "Unchanged"); "$X for Q3 and $Y for FY27"; "raises …
                              #    by $200M, $300M in CC" are changes; a product's or business's revenue ("AI server
                              #    revenue") is not the company's; rows of results (this year, last year, % change) skipped

# ------------------------------------------------------------------ change words
NOUN = r'(?:guidance|outlook|forecasts?|financial (?:targets?|framework)|targets?|expectations?|projections?|guidance ranges?|range)'
_STOP = (r'(?:than|ahead|above|below|exceed\w*|versus|vs|compared|relative|beat|surpass\w*|within|despite|while|but|although|after|'
         r'because|which|that|reflect\w*|driven|due|given|as|when|if|beyond|against|was|were|result\w*|primarily|mainly|partly|partially|following|change|changes)')
GAP = rf'(?:[\s,]+(?!{_STOP}\b)[\w&\'’./()+%$-]+){{0,14}}?[\s,]+'
V = {
    'raised': r'rais(?:e|es|ed|ing)|increas(?:e|es|ed|ing)|lift(?:s|ed|ing)?|boost(?:s|ed|ing)?|upgrad(?:e|es|ed|ing)|hik(?:e|es|ed|ing)|'
              r'up(?:s|ped|ping)|elevat(?:e|es|ed|ing)|bump(?:s|ed|ing)? up|mov(?:e|es|ed|ing) up|push(?:es|ed|ing)? up|improv(?:e|es|ed|ing) (?:the )?midpoint',
    'lowered': r'lower(?:s|ed|ing)?|reduc(?:e|es|ed|ing)|cut(?:s|ting)?|trim(?:s|med|ming)?|downgrad(?:e|es|ed|ing)|decreas(?:e|es|ed|ing)|'
               r'par(?:e|es|ed|ing)|slash(?:es|ed|ing)?|tak(?:e|es|ing) down|took down|walk(?:s|ed|ing)? back|ratchet(?:s|ed|ing)? down|scal(?:e|es|ed|ing) back',
    'narrowed': r'narrow(?:s|ed|ing)?|tighten(?:s|ed|ing)?|refin(?:e|es|ed|ing)',
    'widened': r'widen(?:s|ed|ing)?|broaden(?:s|ed|ing)?|expand(?:s|ed|ing)? (?:the )?range',
    'reaffirmed': r'reaffirm(?:s|ed|ing)?|reiterat(?:e|es|ed|ing)|maintain(?:s|ed|ing)?|confirm(?:s|ed|ing)?|affirm(?:s|ed|ing)?|reconfirm(?:s|ed|ing)?|'
                  r'stand(?:s|ing)? by|stood by|continu(?:e|es|ed|ing) to expect|remain(?:s|ed)? on track (?:to|with)|keep(?:s|ing)?|kept|hold(?:s|ing)?|held',
    'initiated': r'initiat(?:e|es|ed|ing)|introduc(?:e|es|ed|ing)|issu(?:e|es|ed|ing)|establish(?:es|ed|ing)?|launch(?:es|ed|ing)?|'
                 r'provid(?:e|es|ed|ing) (?:its |the |our )?(?:initial|first|preliminary)|set(?:s|ting)? (?:its |the |our )?(?:initial|first)',
    'withdrawn': r'withdr(?:aw|aws|ew|awn|awing)|suspend(?:s|ed|ing)?|pull(?:s|ed|ing)? (?=its|the|our)|rescind(?:s|ed|ing)?|retract(?:s|ed|ing)?|'
                 r'discontinu(?:e|es|ed|ing) (?=providing|giving|issuing|its|the|our)|no longer (?:provid(?:e|es|ing)|giv(?:e|es|ing)|offer(?:s|ing)?)|will not (?:provide|issue|give)',
    'updated': r'updat(?:e|es|ed|ing)|revis(?:e|es|ed|ing)|adjust(?:s|ed|ing)?|modif(?:y|ies|ied|ying)|recalibrat(?:e|es|ed|ing)|reset(?:s|ting)?',
}
PASSIVE = {
    'raised': r'raised|increased|lifted|boosted|upgraded|revised (?:up|upward|higher)', 'lowered': r'lowered|reduced|cut|trimmed|revised (?:down|downward|lower)',
    'narrowed': r'narrowed|tightened', 'widened': r'widened|broadened', 'reaffirmed': r'reaffirmed|reiterated|maintained|unchanged|confirmed',
    'withdrawn': r'withdrawn|suspended|rescinded', 'updated': r'updated|revised',
}
WORD = {k: re.compile(rf'\b(?:{v})\b{GAP}{NOUN}\b', re.I) for k, v in V.items()}
PASS = {k: re.compile(rf'\b{NOUN}(?:\s+(?:range|ranges?|midpoint))?\s+(?:is|are|was|were|has been|have been|being|remains?|remained)\s+(?:now\s+)?(?:{v})\b', re.I)
        for k, v in PASSIVE.items()}
EXTRA = [
    ('raised', re.compile(rf'\b(?:upward(?:ly)? revis\w*|revis\w*{GAP}{NOUN}\s+(?:up|upward|higher)|higher{GAP}{NOUN}|{NOUN} (?:raise|increase|hike)\b|beat[- ]and[- ]raise)', re.I)),
    ('lowered', re.compile(rf'\b(?:downward(?:ly)? revis\w*|revis\w*{GAP}{NOUN}\s+(?:down|downward|lower)|{NOUN} (?:cut|reduction)\b)', re.I)),
    ('reaffirmed', re.compile(rf'\b(?:no change (?:to|in)\s+(?:its |the |our )?{NOUN}|{NOUN}[^.;]{{0,40}}\bunchanged\b|unchanged from (?:its |the |our )?(?:prior |previous )?{NOUN})', re.I)),
    ('updated', re.compile(r'\b(?:now (?:expects?|anticipates?|sees|projects?|forecasts?|estimates?|targets?)|(?:is|are) now expected)\b', re.I)),
]
# which end moved: "raising the lower end", "raised the low end", "lowering the top end", "maintaining the upper end"
ENDS = re.compile(rf'\b(?P<v>{V["raised"]}|{V["lowered"]}|{V["reaffirmed"]})\b(?:\s+[\w-]+){{0,3}}?\s+(?:the\s+)?'
                  r'(?P<e>low(?:er)?|bottom|high(?:er)?|top|upper)[- ]end', re.I)
NOT_CHANGE = re.compile(r'(?i)\b(?:exceed\w*|beat|surpass\w*|ahead of|above|below|in line with|within|toward|at) (?:the )?(?:high|low|top|upper|lower|bottom)?(?:[- ]end)?'
                        r'(?: of)? (?:its |our |the |their )?(?:prior |previous |original |respective )?(?:guidance|outlook|expectations)')
BOILER = re.compile(r'(?i)forward[- ]looking|safe harbor|no assurance|undertakes? no|not (?:able|possible) to (?:predict|provide)|'
                    r'without unreasonable effort|risks? and uncertaint|reconciliation of')
PRIORITY = ['withdrawn', 'mixed', 'raised', 'lowered', 'narrowed', 'widened', 'initiated', 'reaffirmed', 'updated']


def words(s):
    """The change words of one sentence: a set of raised / lowered / narrowed / widened / reaffirmed / initiated /
    withdrawn / updated, with which end moved ('low end raised' …)."""
    if BOILER.search(s):
        return set(), []
    found = set()
    for k, rx in WORD.items():
        for m in rx.finditer(s):
            pre = s[max(0, m.start() - 24):m.start()]
            if k == 'lowered' and re.match(r'(?i)lower(?:s|ed|ing)?\s+(?:end|half|bound)', m.group(0)):
                continue              # "the lower end of our guidance": a place in the range, not a cut
            if k == 'raised' and re.match(r'(?i)increas(?:e|es|ed|ing)\s+(?:of|in)\b', m.group(0)) and not re.search(r'(?i)(guidance|outlook)\s*$', s[:m.start()]):
                continue              # "an increase of 8% ... over 2025": growth, not a raise
            if k == 'reaffirmed' and re.search(r'(?i)\b(?:keep|kept|hold|holds|holding|held)\b', m.group(0)) and not re.search(rf'(?i)^(?:keep|kept|hold\w*|held)\s+(?:its |the |our )?(?:\w+\s+){{0,4}}{NOUN}', m.group(0)):
                continue
            if k == 'updated' and re.search(r'(?i)\bupdat\w*\s+(?:on|from)\b', m.group(0)):
                continue
            if re.search(r'(?i)\b(?:not|no|never|without)\s+(?:\w+\s+)?$', pre) and k not in ('withdrawn',):
                continue
            head = m.group(0).split()[0].lower()
            if re.search(r'(?i)\b(?:the|a|an|this|that|these|those)\s+$', pre) and re.match(
                    r'(?:increase|decrease|cut|raise|lift|boost|hike|update|trim|upgrade|downgrade)s?$', head):
                continue              # "the decrease was …": a noun, not the company changing its outlook
            if re.search(r'(?i)\b(?:over|than|versus|vs\.?|above|below|of)\s+$', pre) and head.endswith('ed'):
                continue              # "growth over increased 2026 guidance": an adjective
            found.add(k)
            break
    for k, rx in PASS.items():
        if rx.search(s):
            found.add(k)
    for k, rx in EXTRA:
        if rx.search(s) and (k != 'updated' or re.search(r'\d', s)):
            found.add(k)
    ends = []
    for m in ENDS.finditer(s):
        v = m.group('v').lower()
        kind = 'raised' if re.match(V['raised'], v, re.I) else 'lowered' if re.match(V['lowered'], v, re.I) else 'kept'
        e = 'low end' if re.match(r'(?i)low|bottom', m.group('e')) else 'high end'
        ends.append(f'{e} {kind}')
        if kind == 'raised':
            found.add('raised')
            found.add('narrowed' if e == 'low end' else 'widened')
        elif kind == 'lowered':
            found.add('lowered')
            found.add('narrowed' if e == 'high end' else 'widened')
    if 'raised' in found and NOT_CHANGE.search(s) and not re.search(rf'(?i)\b(?:{V["raised"]})\b{GAP}{NOUN}', NOT_CHANGE.sub(' ', s)):
        found.discard('raised')
    if found & {'raised', 'lowered', 'narrowed', 'widened', 'reaffirmed', 'initiated', 'withdrawn'}:
        found.discard('updated')
    return found, ends


# ------------------------------------------------------------------ numbers
SCALE = {'trillion': 1e12, 'billion': 1e9, 'bn': 1e9, 'b': 1e9, 'million': 1e6, 'mm': 1e6, 'mn': 1e6, 'm': 1e6,
         'thousand': 1e3, 'k': 1e3}
TOK = re.compile(r'(?P<neg>\(\s*)?(?P<cur>(?:US)?\$|USD\s?)?\s?(?P<neg2>\()?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\)?'
                 r'(?:\s?(?P<unit>trillion|billion|million|thousand|bn|mm|mn|[BMK](?![A-Za-z])|%|percent|basis points|bps|x(?![A-Za-z])))?\)?', re.I)
JOIN = re.compile(r'^\s*(?:to|-|–|—|through|thru)\s*$', re.I)
AND = re.compile(r'^\s*and\s*$', re.I)
BETWEEN = re.compile(r'(?i)\bbetween\s*$')
PRIOR_PRE = re.compile(
    r'(?i)(?:\b(?:from|previously|prior(?: guidance| outlook| range| expectations?)?(?: of)?|original(?:ly)?(?: guidance| outlook)?(?: of)?|'
    r'up from|down from|replacing|in place of)\s*|\b(?:compared (?:to|with)|versus|vs\.?|as compared to|was)\s+(?=(?:(?:its|our|the|a|their)\s+)?(?:prior|previous|earlier|original|initial|guidance|outlook)))'
    r'(?:(?:its|our|the|a|their)\s+)?(?:(?:prior|previous|previously (?:issued|announced|provided)|earlier|original|initial|last)\s+)?'
    r'(?:(?:full[- ]year|annual|\d{4}|guidance|outlook|range|expectation|ranges)\s+)*(?:(?:for [\w\s,-]{0,40}?|of)\s+)?'
    r'(?:(?:a|the)\s+range\s+of\s+)?(?:approximately\s+|about\s+|around\s+)?(?:between\s+)?$')
CURRENT_PRE = re.compile(r'(?i)(?:(?<!compared )(?<!relative )(?<!as compared )\bto|\bbe|\bat)\s+(?:a\s+(?:new\s+)?range\s+of\s+|between\s+|approximately\s+|about\s+)?$')


def _tok(m, scale_hint=1.0):
    num = float(m.group('num').replace(',', ''))
    unit = (m.group('unit') or '').lower()
    neg = bool(m.group('neg') or m.group('neg2'))
    cur = bool(m.group('cur'))
    lead = len(m.group(0)) - len(m.group(0).lstrip())
    t = {'start': m.start() + lead, 'end': m.end(), 'num': num, 'cur': cur, 'unit': unit, 'neg': neg, 'text': m.group(0).strip()}
    plain = not cur and not unit
    t['year'] = plain and ',' not in m.group('num') and '.' not in m.group('num') and 1990 <= num <= 2100
    t['plain'] = plain
    return t


def _amount(t, scale_hint):
    """(value, unit) of one token; unit 'usd' | 'pct' | 'bps' | 'x' | 'num'."""
    u = t['unit']
    v = -t['num'] if t['neg'] else t['num']
    if u in ('%', 'percent'):
        return v, 'pct'
    if u in ('basis points', 'bps'):
        return v, 'bps'
    if u == 'x':
        return v, 'x'
    if u in SCALE:
        return v * SCALE[u], 'usd'
    if t['cur']:
        return v * scale_hint, 'usd'
    return v * scale_hint, 'num'


def values(text, table=False, scale=1.0, lead=''):
    """The amounts in a clause, ranges joined: [{lo, hi, unit, approx, bound, prior, delta, growth, ps, end, pm}] in order of
    position; lead: the words before the clause (read for "from", "by", "raising … by")."""
    full, off = lead + text, len(lead)
    toks = [_tok(m) for m in TOK.finditer(full) if m.start() >= off]
    for t in toks:                    # a minus sign that is not a range dash: "-3% to -2%", "−$0.10"
        j = t['start'] - 1
        if j >= 0 and (full[j] == '−' or full[j] == '-' and (j == 0 or full[j - 1] in ' (') and not re.search(r'[\d%]\s*$', full[:j])):
            t['neg'] = True
    toks = [t for t in toks if not t['year'] and not (t['plain'] and not table and t['num'] < 1000
                                                     and not re.match(r'\s*(?:-|–|to)\s*\$?\d', full[t['end']:t['end'] + 6]))]
    # not figures: the day of a date ("July 29, 2026"), "Table 1", "Note 3", footnote marks ("EPS (Diluted) 2,4 / Mid-point")
    toks = [t for t in toks if not (t['plain'] and (
        re.search(r'(?i)\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s*$', full[max(0, t['start'] - 12):t['start']])
        or re.search(r'(?i)\b(?:table|note|item|exhibit|schedule|footnote|page)\s*$', full[max(0, t['start'] - 12):t['start']])
        or re.search(r'(?i)(?:\bq|\bh|\bfy|\bcy|\bfq)\s?$', full[max(0, t['start'] - 3):t['start']]) or re.match(r'(?i)q\b', full[t['end']:t['end'] + 2])
        or (t['num'] < 10 and re.match(r'\s*(?:,\s*\d\b|/)', full[t['end']:t['end'] + 4]))
        or (t['num'] < 10 and re.search(r',\s*$', full[max(0, t['start'] - 3):t['start']]) and re.search(r'\b\d\s*,\s*$', full[max(0, t['start'] - 5):t['start']]))))]
    out, i = [], 0
    while i < len(toks):
        a = toks[i]
        b = toks[i + 1] if i + 1 < len(toks) else None
        joined = False
        if b is not None:
            gap = full[a['end']:b['start']]
            if JOIN.match(gap) or (AND.match(gap) and BETWEEN.search(full[max(0, a['start'] - 12):a['start']])):
                joined = True
        if joined:
            if not a['unit'] and b['unit']:
                a = dict(a, unit=b['unit'])
            if not a['cur'] and b['cur']:
                a = dict(a, cur=True)
            if not b['cur'] and a['cur']:
                b = dict(b, cur=True)
            if a['plain'] and b['plain'] and not table:
                i += 2
                continue
            (lo, u1), (hi, u2) = _amount(a, scale), _amount(b, scale)
            if u1 == u2:
                if lo > hi:
                    lo, hi = hi, lo
                out.append({'lo': lo, 'hi': hi, 'unit': u1, 'start': a['start'], 'end': b['end']})
            i += 2
            continue
        if a['plain'] and not table:
            i += 1
            continue
        v, u = _amount(a, scale)
        out.append({'lo': v, 'hi': v, 'unit': u, 'start': a['start'], 'end': a['end']})
        i += 1
    out = [x for x in out if not re.search(r'(?i)(?:plus or minus|\+/-|±|give or take)\s*$', full[max(0, x['start'] - 20):x['start']])]
    for x in out:
        pre = full[max(0, x['start'] - 90):x['start']]
        post = full[x['end']:x['end'] + 60]
        if re.search(r'(?i)(?:approximately|about|around|roughly|nearly|close to|~|≈|an estimated|in the area of)\s*$', pre):
            x['approx'] = True
        if re.search(r'(?i)(?:at least|a minimum of|no less than|not less than|more than|greater than|in excess of|over|exceed(?:s|ing)?|north of|upwards of)\s*$', pre):
            x['bound'] = 'min'
        elif re.search(r'(?i)(?:up to|no more than|not more than|at most|a maximum of|less than|below|under)\s*$', pre):
            x['bound'] = 'max'
        pm = re.match(r'(?i)\s*,?\s*(?:plus or minus|\+/-|±|give or take)\s*', post)
        m2 = TOK.match(post, pm.end()) if pm else None
        if m2:
            t = _tok(m2)
            x['pm'] = (t['num'], t['unit'].lower())
        if re.match(r'(?i)\s*(?:per|a|/)\s*(?:diluted\s+|basic\s+|common\s+|fully diluted\s+)*(?:share|unit)\b', post):
            x['ps'] = True
        if re.match(r'(?i)\s*(?:y/y|yoy|year[- ]over[- ]year|growth|annual growth|organic growth|increase|decrease|decline|higher|lower|cagr)\b', post) or \
                re.search(r'(?i)\b(?:grow(?:th)?|increase|decrease|decline|up|down|change|expansion|contraction)\s+(?:of\s+|by\s+|in\s+)?(?:approximately\s+|about\s+|around\s+|roughly\s+)?$', pre):
            x['growth'] = True
        if (re.search(r'(?i)\bby\s*(?:approximately |about |roughly |an additional |another )?$', pre) and
                re.search(rf'(?i)\b(?:{V["raised"]}|{V["lowered"]}|increase|decrease|reduction|improvement)\b[^.;$]{{0,140}}$', full[max(0, x['start'] - 160):x['start']])) or \
                re.search(r'(?i)\b(?:increase|decrease|reduction|improvement|raise|cut|lift|change)\s+of\s*(?:approximately |about |roughly )?$', pre) or \
                re.search(r'(?i)\b(?:down|up|lower|higher)\s+(?:by\s+)?(?:approximately|about|roughly|nearly|some)\s*$', pre):
            x['delta'] = True
            x.pop('growth', None)
        prevx = out[out.index(x) - 1] if out.index(x) > 0 else None
        if prevx is not None and prevx.get('delta') and re.fullmatch(r'\s*(?:,|or|and|/)\s*', full[prevx['end']:x['start']]):
            x['delta'] = True                         # "raises … by $200M, $300M in constant currency"
            x.pop('growth', None)
        if (PRIOR_PRE.search(pre) and not CURRENT_PRE.search(pre)) or re.match(r'(?i)\s*\)?\s*\(?(?:previously|prior)\b', post):
            x['prior'] = True
        m = re.search(r'(?i)\b(?:(low(?:er)?|bottom)|(high(?:er)?|upper|top))[- ]end\b[^$\d]{0,40}?(?:to|at|of)\s*(?:approximately\s+)?$', pre)
        if m:
            x['end'] = 'low' if m.group(1) else 'high'
    return out


def _apply_pm(x):
    if 'pm' not in x:
        return x
    n, u = x['pm']
    mid = (x['lo'] + x['hi']) / 2
    if x['unit'] == 'pct':
        d = n / 100 if u in ('basis points', 'bps') else n if u in ('%', 'percent') else None
    elif u in ('%', 'percent'):
        d = abs(mid) * n / 100
    elif u in SCALE:
        d = n * SCALE[u]
    else:
        d = n
    if d is None:
        return x
    return dict(x, lo=mid - d, hi=mid + d)


# ------------------------------------------------------------------ metrics, basis, period
METRICS = [
    ('gross_margin', 'Gross margin', r'gross (?:profit )?margins?'),
    ('ebitda_margin', 'EBITDA margin', r'(?:adj(?:usted|\.)?\s+)?ebitda(?:re)? margins?'),
    ('operating_margin', 'Operating margin', r'(?:segment |adjusted |non-gaap |gaap )?(?:operating(?: income| profit)?|ebit) margins?'),
    ('net_interest_margin', 'Net interest margin', r'net interest margins?'),
    ('tax_rate', 'Tax rate', r'(?:effective |adjusted |non-gaap |gaap )*(?:income )?tax rates?'),
    ('ffo_ps', 'FFO per share', r'\b(?:core |normalized |adjusted |nareit )?a?ffo(?:aa| as adjusted)?(?: attributable to [\w ,&]{0,50}?)?(?: per (?:diluted )?(?:common )?share)'),
    ('eps', 'EPS', r'(?:earnings|net income|net earnings|income|loss|eps)(?: \(loss\))? per (?:diluted |basic |common |fully diluted )*share(?: attributable to [\w ,&.]{0,40}?(?:\W{1,3}diluted)?)?|\b(?:diluted )?eps\b|per diluted share|\bearnings guidance'),
    ('ebitda', 'EBITDA', r'\bebitda(?:re)?\b'),
    ('fcf', 'Free cash flow', r'free cash flows?'),
    ('ocf', 'Operating cash flow', r'operating cash flows?|cash flows? from operati(?:ons|ng activities)|cash provided by operating activities'),
    ('capex', 'Capital expenditures', r'capital expenditures?|\bcapex\b|capital spending|capital investments?|capital plan'),
    ('opex', 'Operating expenses', r'(?:total )?operating expenses|\bopex\b|operating costs'),
    ('gross_profit', 'Gross profit', r'gross profit'),
    ('operating_income', 'Operating income', r'operating (?:income|profit|earnings)|income from operations|\bebit\b|segment profit'),
    ('net_income', 'Net income', r'net (?:income|earnings|loss)(?! per)(?: attributable to [\w ,&]{0,40}?)?'),
    ('other_income', 'Other income', r'other income(?: and expense)?(?:,? net)?|interest and other income(?:,? net)?|other (?:income|expense),? net|non-?operating income'),
    ('interest_expense', 'Interest expense', r'(?:net )?interest expense'),
    ('sbc', 'Stock-based compensation', r'(?:stock|share|equity)-based compensation'),
    ('da', 'Depreciation & amortization', r'depreciation(?:,)? (?:and|&) amortization'),
    ('ffo', 'FFO', r'\b(?:core |normalized |adjusted )?a?ffo(?:aa)?\b|funds from operations'),
    ('revenue', 'Revenue', r'(?:total |net |consolidated |gaap |operating |adjusted net |adjusted )?revenues?|net sales|\b(?:total )?sales\b|top[- ]line'),
]
_MET = [(k, n, re.compile(p, re.I)) for k, n, p in METRICS]
MONEY = {'ebitda', 'fcf', 'ocf', 'capex', 'opex', 'gross_profit', 'operating_income', 'net_income', 'other_income', 'interest_expense',
         'sbc', 'da', 'ffo', 'revenue'}
PCT = {'gross_margin', 'ebitda_margin', 'operating_margin', 'net_interest_margin', 'tax_rate'}
PS = {'eps', 'ffo_ps'}
# words that may stand between a business line's name and its metric without being a name themselves
# ("Full-Year 2026 Total Revenue", "Q4 Consolidated Net Sales"); a verb or any other lower-case word ends the scan
# words before "revenue" that keep it the company's own: verbs, articles, time and basis words
PRODUCT_OK = {'of', 'in', 'for', 'and', 'or', 'with', 'to', 'that', 'expects', 'expect', 'expected', 'see', 'sees', 'guides', 'guide', 'guided',
              'anticipates', 'anticipate', 'projects', 'project', 'targets', 'target', 'forecasts', 'forecast', 'estimates', 'estimate',
              'is', 'are', 'be', 'will', 'a', 'an', 'this', 'that', 'record', 'total', 'overall', 'half', 'second-half', 'first-half',
              'month', 'months', 'period', 'year-over-year', 'yearly', 'sequential', 'sequentially', 'quarter’s', 'year’s', 'all',
              'ended', 'ending', 'to-date', 'ytd', 'combined', 'group', 'aggregate', 'expected', 'approximately', 'our', 'its'}
MOD_WORDS = {'total', 'net', 'consolidated', 'gaap', 'non-gaap', 'adjusted', 'full', 'year', 'full-year', 'fiscal', 'quarter', 'first',
             'second', 'third', 'fourth', 'annual', 'reported', 'operating', 'core', 'comparable', 'non', 'calendar', 'fy', 'diluted',
             'gross', 'quarterly', 'the', 'its', 'our', 'their', 'company', 'company’s', "company's", 'consolidated'}


ASIDE = re.compile(r'(?i),\s*(?:which|that) (?:is|are|represents?|excludes?|includes?|reflects?) [^,;$%\d]{3,80},|\((?:defined as|which is|i\.e\.,?) [^)$%\d]{3,80}\)')


def mentions(text):
    """[(start, end, key, name, matched text)] of the metrics in a clause, longest match first where they overlap."""
    spans = []
    for k, name, rx in _MET:
        for m in rx.finditer(text):
            spans.append((m.start(), m.end(), k, name, m.group(0)))
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    # a definition in passing ("Core Adjusted EBITDA, which is Adjusted EBITDA less lease revenues, is expected …"): the
    # metrics it names are not guided
    asides = [(m.start(), m.end()) for m in ASIDE.finditer(text)]
    spans = [s for s in spans if not any(a < s[0] and s[1] <= b for a, b in asides)]
    out = []
    for s in spans:
        if out and s[0] < out[-1][1]:
            if s[1] - s[0] > out[-1][1] - out[-1][0]:
                out[-1] = s
            continue
        out.append(s)
    return out


def basis(text):
    b = ''
    if re.search(r'(?i)\bnon-?gaap\b|\badjusted\b|\badj\.|\bcore\b|\bcomparable\b|\bunderlying\b|\bnormalized\b|\bpro forma\b|\bex(?:cluding|\.)\b|\bas adjusted\b', text):
        b = 'non-GAAP'
    elif re.search(r'(?<![-\w])GAAP\b', text) or re.search(r'(?i)\breported\b', text):
        b = 'GAAP'
    return b


ORD = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, '1st': 1, '2nd': 2, '3rd': 3, '4th': 4}
PER_Q = re.compile(r"(?i)\b(?:(?P<f0>fiscal\s+)?(?P<w>first|second|third|fourth|1st|2nd|3rd|4th)[- ]quarter|(?P<f1>f)?q(?P<n>[1-4])(?!\s+(?:Holdings|Inc|Corp|Corporation|Group|Ltd|LLC|Technologies|Systems|Capital)\b)|(?P<n2>[1-4])q)(?:\s+of)?(?:\s+(?P<f>fiscal(?: year)?|fy))?(?:(?<=\d)-(?=\d{2}(?:\d{2})?\b)|\s*['’]?)"
                   r"(?P<y>\d{4}|\d{2}(?!\d|%|\.\d|\s*(?:million|billion|percent)))?\b")
PER_FY = re.compile(r"(?i)\b(?:(?P<w>full[- ]year|fiscal(?: year)?|fy|calendar(?: year)?|annual|year)(?:\s+of)?\s*['’]?(?P<y>\d{4}|\d{2}(?!\d|%|\.\d))\b|"
                    r"(?P<fy0>full[- ]year|fiscal year|for the year|annual|year[- ]end))")
YEAR = re.compile(r'\b(20\d{2})\b(?!\s*(?:-|–|to)\s*20\d{2})')
LONG = re.compile(r'(?i)\blong[- ]term\b|\bmulti-?year\b|\bthrough (?:fiscal )?20\d{2}\b|\bby (?:fiscal )?20\d{2}\b|\b20\d{2}\s*(?:-|–|to|through)\s*20\d{2}\b|\bcagr\b')
BASE = re.compile(r'(?i)(?:from|over|versus|vs\.?|compared (?:to|with)|than|relative to|since|ended|ending)\s+(?:the\s+)?(?:(?:full|fiscal)[- ]?(?:year\s+)?)?$')
# a comparison base a few words back: "compared with $25.0 billion in fourth quarter 2025", "versus 12% in fiscal 2025" —
# the period of the figure it is compared with, not of the guided one
CMP = re.compile(r'(?i)\b(?:compared (?:to|with)|as compared|versus|vs\.?|relative to|up from|down from|year[- ]ago|prior[- ]year|last year|(?:from )?a base of|base year)\b(?:[^.;:!?]|(?<=\d)\.(?=\d)){0,48}$')


def _yr(y):
    if not y:
        return None
    y = int(y)
    return y + 2000 if y < 100 else y


MONTHS = {m: i + 1 for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}
PER_DATE = re.compile(r"(?i)\b(?P<k>(?:fiscal |full[- ])?(?:quarter|year|three months|twelve months))\s+(?:ending|ended|that ends|to end)\s+(?:on\s+)?"
                      r"(?P<m>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+"
                      r"(?P<d>\d{1,2}),?\s+(?P<y>20\d\d)")


def _date_period(m):
    """'Q@2026-09-27' / 'FY@2027-01-31': a period named by the day it ends (record() finds it by that day)."""
    k = m.group('k').lower()
    day = f"{m.group('y')}-{MONTHS[m.group('m')[:3].lower()]:02d}-{int(m.group('d')):02d}"
    return ('FY@' if 'year' in k or 'twelve' in k else 'Q@') + day


def _periods(text):
    """[(start, 'Q4 2026' | 'FY2026' | 'FY' | 'Q@2026-09-27' | 'long-term')] named in a text, comparison bases left out
    ("growth over 2025")."""
    out = []
    dated = [(m.start(), m.end(), _date_period(m)) for m in PER_DATE.finditer(text)]
    for a, b, per in dated:
        if not CMP.search(text[max(0, a - 60):a]):
            out.append((a, per))
    cmp_ = lambda m: CMP.search(text[max(0, m.start() - 60):m.start()])
    taken = [(m.start(), m.end()) for m in PER_Q.finditer(text)] + [(a, b) for a, b, _ in dated]
    for m in PER_Q.finditer(text):
        if any(a <= m.start() < b for a, b, _ in dated):
            continue
        n = ORD.get((m.group('w') or '').lower()) or int(m.group('n') or m.group('n2'))
        y = _yr(m.group('y'))
        if (y and BASE.search(text[max(0, m.start() - 24):m.start()])) or cmp_(m):
            continue                                   # "growth over the fourth quarter of 2025", "compared with … Q4 2025"
        fis = m.group('f') or m.group('f0') or m.group('f1')
        out.append((m.start(), f"Q{n} {'FY' if fis else ''}{y}" if y else f'Q{n}' + (' FY' if fis else '')))
    for m in PER_FY.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        y = _yr(m.group('y'))
        if y and BASE.search(text[max(0, m.start() - 24):m.start()]) and not re.search(r'(?i)\b(?:of|in|during)\s+$', text[max(0, m.start() - 6):m.start()]):
            continue
        taken.append((m.start(), m.end()))
        if y and cmp_(m):
            continue
        out.append((m.start(), f'FY{y}' if y else 'FY'))
    for m in YEAR.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        before = text[max(0, m.start() - 30):m.start()]
        if BASE.search(before) or cmp_(m) or re.search(r'(?i)(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+\d{1,2},?\s*$', before):
            continue
        out.append((m.start(), f'FY{m.group(1)}'))
    for m in LONG.finditer(text):
        out.append((m.start(), 'long-term'))
    return sorted(out)


def _merge(p, default):
    """A period without its year takes the year (and fiscal) of the default: 'Q4' + 'FY2026' → 'Q4 2026'."""
    if not p or not default:
        return p or default
    m = re.search(r'(\d{4})', default)
    if p == 'FY' and m:
        return f'FY{m.group(1)}'
    q = re.match(r'^Q([1-4])( FY)?$', p)
    if q and m:
        return f"Q{q.group(1)} {'FY' if q.group(2) or ('FY' in default and default.startswith('Q')) else ''}{m.group(1)}"
    return p


def period(text, default=None):
    """'Q4 2026', 'Q3 FY2027', 'FY2026', 'FY' (year not said), 'long-term' … the first period a text names, else default."""
    ps = _periods(text)
    if not ps:
        return default
    dated = [x for x in ps if re.search(r'\d{4}', x[1])]          # "Q2 … the fourth quarter of 2026": the one with its year
    return _merge((dated or ps)[0][1], default)


def period_near(clause, pre, sentence, default=None):
    """The period a figure belongs to: named between the metric and its figure, else the nearest one before the metric
    (in its sentence), else elsewhere in the sentence, else the section's."""
    parts = re.split(r'\$|\d', clause, maxsplit=1) if clause else ['']
    head = parts[0]
    # after the figure, up to the next comparison or sentence break: "growth of over 40% both in 2027 and in 2028"
    tail = re.split(r'(?i)[;:]|\bcompared\b|\bversus\b|\bvs\.', clause[len(head):], maxsplit=1)[0] if clause else ''
    # a period before the metric with another figure in between belongs to that figure ("revenue growth in Q3 ($184
    # billion run rate) and projected growth of over 40% in 2027"): not this one's
    pp = _periods(pre)
    if pp:
        rest = pre[pp[-1][0]:]
        m0 = PER_Q.match(rest) or PER_FY.match(rest) or YEAR.match(rest) or LONG.match(rest)
        if re.search(r'[\d$]', rest[m0.end() if m0 else 0:]):
            pre = ''
    for text, pick in ((head, 0), (pre, -1), (tail, 0), (sentence, 0)):
        ps = _periods(text)
        if ps:
            p = ps[pick][1]
            if p == 'long-term':
                return p
            if p in ('FY',) or re.match(r'^Q[1-4]( FY)?$', p):
                more = [x for _, x in _periods(sentence) if re.search(r'\d{4}', x)]
                return _merge(p, more[0] if more else default)
            return p
    return default


# ------------------------------------------------------------------ reading a release
def _sentences(p):
    return [s for s in re.split(r'(?<=[.!?;])\s+(?=[A-Z(“"•·◦▪])|\s+(?=[•·◦▪]\s)', p) if s.strip()]


# a result held to its guidance ("roughly 200 basis points above guidance midpoint", "at the high end of our guidance range")
GUIDE_CMP = re.compile(r'(?i)\b(?:above|below|exceed\w*|beat|ahead of|in line with|within|versus|vs\.?|compared (?:to|with)|top of|'
                       r'(?:the )?(?:high|low|upper|lower|top|bottom)[- ]end of)\s+(?:the |our |its )?(?:high end of )?(?:prior |previous |original |raised )?'
                       r'(?:guidance|outlook|expectations?)(?:\s+(?:range|midpoint))?')
# the figures a guide is built on, not a guide: "guidance is based on the following Q3 FY26 figures: Net sales: $177.8 billion"
BASEFIG = re.compile(r'(?i)\bbased on the following\b|\b(?:is|are) based on (?:the )?(?:Q[1-4]|fiscal|FY|full[- ]year|prior[- ]year)\b[^.;]{0,40}\b(?:figures|results)\b|'
                     r'\bbaseline (?:of|figures?|results?)\b|\bfrom (?:an?|our|the) (?:higher |lower |new )?(?:earnings )?baseline\b')
# a row of results in a table: this year, last year and the change ("Net revenue $24,181 $22,726 6.4%")
RESULT_ROW = re.compile(r'(?i)\$?\(?\d[\d,]*(?:\.\d+)?\)?\s+\$?\(?\d[\d,]*(?:\.\d+)?\)?\s+\(?-?\d+(?:\.\d+)?\s?%\)?')
FORWARD = re.compile(r'(?i)\b(?:expect\w*|anticipat\w*|guidance|outlook|forecast\w*|project(?:s|ed|ing|ions?)|targets?|guid(?:e|es|ed|ing)|'
                     r'sees|estimates?|plans? to|is likely|range of|for the (?:full )?(?:fiscal )?year|fourth quarter|next quarter)\b')
PAST = re.compile(r'(?i)\b(?:was|were|totaled|came in at|reported|delivered|achieved|grew|generated|posted|recorded)\b')
HEAD = re.compile(r'(?i)(?:outlook|guidance|forecast|expectations|financial targets)\b')
STOP_HEAD = re.compile(r'(?i)^(?:forward[- ]looking|about |conference call|webcast|earnings call|non-gaap(?!\s*(?:\(\d+\)\s*)?(?:outlook|guidance|estimates?))|use of non|reconciliation|contacts?\b|investor|media|'
                       r'safe harbor|cautionary|condensed|consolidated (?:statements|balance)|balance sheet|cash flow|dividend|share repurchase|'
                       r'(?:third|second|first|fourth) quarter (?:\d{4} )?(?:highlights|results|financial)|highlights|recent|business update|segment results)')


def _section_scale(p):
    m = re.search(r'(?i)\(?\s*(?:\$|dollars|amounts)?\s*in (millions|billions|thousands)', p)
    return {'millions': 1e6, 'billions': 1e9, 'thousands': 1e3}[m.group(1).lower()] if m else None


def _row_scale(p):
    m = re.search(r'\(\s*(?:US)?\$\s*(B|M|K|bn|mm|billions?|millions?|thousands?)\s*\)|\(\s*in (billions|millions|thousands)\s*\)', p, re.I)
    if not m:
        return None
    t = (m.group(1) or m.group(2)).lower()
    return 1e9 if t[0] == 'b' else 1e6 if t[0] == 'm' else 1e3


def _clauses(s, spans):
    """Split a sentence into one clause per metric mention (from one metric to the next). A metric whose clause has no
    figure while the next one starts right after "and" or "," ("GAAP and non-GAAP gross margins", "revenue and EPS") is
    kept: the figures may come after both."""
    out = []
    for i, sp in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(s)
        out.append((sp, s[sp[0]:end], s[max(0, sp[0] - 60):sp[0]]))
    return out


def _scope(s, sp):
    """'' the whole company; 'segment' (a business line named before it); 'organic'."""
    pre = s[max(0, sp[0] - 40):sp[0]]
    if re.search(r'(?i)\borganic\b|\bexcluding\b|\bex-', pre + s[sp[0]:sp[1] + 30]):
        return 'organic'
    if re.search(r'(?i)\bsegment\b|\bdivision\b|\bbusiness\b|\bfrom the\b|\bfrom\b\s*$|\bincluding\b', pre[-30:]):
        return 'segment'
    # a name in capitals right before the metric ("Data Center revenue", "Employer Services revenue"); the scan stops at
    # the first other word: a verb or a lower-case word ("AMD expects revenue", "Hayward now expects net sales" are the
    # company's own), a possessive ("AMD's revenue") or the start of the sentence
    words_ = re.findall(r"[\w&'’.-]+", pre)
    if sp[2] == 'revenue' and words_:
        last = words_[-1]
        lw = last.lower().strip('.')
        if (lw not in MOD_WORDS and lw not in PRODUCT_OK and not VERB_ANY.fullmatch(last) and not re.match(r'^(?:\d{2,4}|fy\d*|q[1-4]|\(?\d\)?|h[12])$', lw)
                and re.match(r'^[a-z][a-z-]+$', last) and not re.search(r"['’]s$", last)):
            return 'segment'                          # "AI server revenue", "subscription revenue", "non-handset revenues"
    for w in reversed(words_[-4:]):
        lw = w.lower().strip('.')
        if lw in MOD_WORDS or re.match(r'^(?:\d{2,4}|fy\d*|q[1-4]|\(?\d\)?)$', lw):
            continue
        if not w[:1].isupper() or VERB_ANY.fullmatch(w) or re.search(r"['’]s$", w):
            return ''
        return 'segment'
    return ''


VERB_ANY = re.compile('|'.join(rf'(?P<{k}>\b(?:{v})\b)' for k, v in V.items()), re.I)


def _verb_before(s, pos, found):
    """The change words governing a metric mentioned at pos: the nearest change verb before it in the sentence (with the
    verbs chained to it by "and" — "raising and narrowing"), of the kinds the sentence was found to say."""
    ms = [m for m in VERB_ANY.finditer(s[:pos]) if m.lastgroup in found]
    if not ms:
        return set()
    got, last = {ms[-1].lastgroup}, ms[-1]
    for m in reversed(ms[:-1]):
        if re.fullmatch(r'\s*(?:and|,|, and|&|/)\s*', s[m.end():last.start()]):
            got.add(m.lastgroup)
            last = m
        else:
            break
    nxt = VERB_ANY.match(s, ms[-1].end() + len(re.match(r'\s*(?:and|&|,)\s*', s[ms[-1].end():]).group(0)) if re.match(r'\s*(?:and|&|,)\s*', s[ms[-1].end():]) else ms[-1].end())
    if nxt and nxt.lastgroup in found and nxt.start() < pos:
        got.add(nxt.lastgroup)
    return got


OTHER_NOUN = re.compile(r'(?i)^\s*(?:of|related to|associated with|attributable to|in connection with|tied to)\s+(?!(?:the |our |its )?(?:revenue|sales|net sales|'
                        r'growth|guidance|outlook|range|midpoint|total|consolidated|gaap|non-gaap|adjusted|fiscal|full|first|second|third|fourth|q[1-4]|20\d\d|approximately))')
PAST_VALUE = re.compile(r'(?i)^\s*,?\s*(?:an? )?(?:increased|decreased|grew|declined|rose|fell|was|were)\b')


def _own(full, v):
    """False when the figure describes something else than the metric of its clause, or reports a result (full: the text
    the figure's positions count in — the sentence up to the clause and the clause)."""
    e = v.get('end')
    post = full[e:e + 70] if isinstance(e, int) else ''
    return not (OTHER_NOUN.match(post) or PAST_VALUE.match(post))


def _items_of(s, ctx, said, ends, table=False, scale=1.0, columns=None, carry=None):
    """The guided figures of one sentence (or table row)."""
    spans = mentions(s)
    if not spans and carry:
        spans = [(0, 0, carry[0], carry[1], carry[2])]
    out = []
    resp = re.search(r'(?i)\brespectively\b', s)
    pm_all = re.search(r'(?i)respectively,?\s*(?:plus or minus|\+/-|±)\s*', s)
    pm_all = _tok(TOK.match(s, pm_all.end())) if pm_all and TOK.match(s, pm_all.end()) else None
    for sp, clause, pre in _clauses(s, spans):
        k, name, word = sp[2], sp[3], sp[4]
        rs = _row_scale(clause[:40]) if table or columns else None    # "Revenue ($B) $15.0 - $16.0"
        vals = values(clause, table=table, scale=1.0 if k in PS else (rs or scale), lead=s[:sp[0]])
        if pm_all:
            for v in vals:
                v.setdefault('pm', (pm_all['num'], pm_all['unit']))
        vals = [_apply_pm(v) for v in vals if _own(s[:sp[0]] + clause, v)]
        b = basis(pre[-40:] + ' ' + word) or basis(clause[:60]) or ctx.get('basis', '')
        both = re.search(r'(?i)\bGAAP and non-GAAP\b', s[max(0, sp[0] - 60):sp[1] + 20])
        per = period_near(clause, s[:sp[0]], s, ctx.get('period'))      # all of the sentence before the metric: a window cut a period in half
        if k in MONEY and any(v.get('ps') for v in vals):
            # "net income of $736 million to $743 million, or $21.28 to $21.48 per diluted share": both figures
            psv = values(clause, table=table, scale=1.0, lead=s[:sp[0]])
            psv = [v for v in psv if v.get('ps')]
            cur_ps = next((v for v in psv if not v.get('prior')), None)
            if cur_ps:
                it = _item('eps', 'EPS', b, per, cur_ps, next((v for v in psv if v.get('prior')), None), _verb_before(s, sp[0], said) or set(said or ()),
                           ends, s, '', table)
                if it:
                    out.append(it)
            vals = [v for v in vals if not v.get('ps')]
            if not vals:
                continue
        sc = _scope(s, sp) if k in MONEY else ''
        own = _verb_before(s, sp[0], said) if said else set()
        w = own or set(said or ())
        if columns and columns[0] == 'versions':
            # one cell per version: "Unchanged" repeats the one to its left; the last is current, the one before the prior
            cells = []
            for seg in re.split(r'(?i)\bunchanged\b', clause):
                vs = [_apply_pm(v) for v in values(seg, table=table, scale=1.0 if k in PS else scale)]
                if cells or vs:
                    cells.extend(vs[:1])
                cells.append(None)
            cells = cells[:-1]
            seq = []
            for c in cells:
                seq.append(c if c is not None else (seq[-1] if seq else None))
            seq = [c for c in seq if c is not None]
            if not seq:
                continue
            cur_v, prev_v = seq[-1], seq[-2] if len(seq) > 1 else None
            item = _item(k, name, b, per, cur_v, dict(prev_v, prior=True) if prev_v else None, w, ends, s, sc, table)
            if item:
                out.append(item)
            continue
        if columns and vals and all(str(c).startswith('basis:') for c in columns):
            # a GAAP column and a non-GAAP column; one figure for both (revenue): the row's own basis
            vals = [v for v in vals if not v.get('growth') and not v.get('delta')]
            if len(vals) == 1:
                item = _item(k, name, b, per, vals[0], None, w, ends, s, sc, table)
                if item:
                    out.append(item)
            elif len(vals) == len(columns):
                for c, v in zip(columns, vals):
                    item = _item(k, name, c[6:], per, v, None, w, ends, s, sc, table)
                    if item:
                        out.append(item)
            continue
        if columns and vals:
            vals = [v for v in vals if not v.get('growth') and not v.get('delta') and v['unit'] in ('usd', 'num', 'pct')]
            if len(vals) != len(columns):
                continue
            cur = {c: v for c, v in zip(columns, vals)}
            for c, v in cur.items():
                if c == 'prior':
                    continue
                item = _item(k, name, b, per if c == 'current' else c, v, cur.get('prior'), w, ends, s, sc, table)
                if item:
                    out.append(item)
            continue
        cur = [v for v in vals if not v.get('prior') and not v.get('delta')]
        prior = [v for v in vals if v.get('prior') and not v.get('delta')]
        delta = next((v for v in vals if v.get('delta')), None)
        lo_end = next((v for v in cur if v.get('end') == 'low'), None)
        hi_end = next((v for v in cur if v.get('end') == 'high'), None)
        if lo_end and hi_end and lo_end['unit'] == hi_end['unit']:
            merged = dict(lo_end, lo=lo_end['lo'], hi=hi_end['hi'])
            merged.pop('end', None)
            cur = [merged] + [v for v in cur if v is not lo_end and v is not hi_end]
        if both and len(cur) >= 2 and resp:
            for bb, v, pv in (('GAAP', cur[0], prior[0] if prior else None), ('non-GAAP', cur[1], prior[1] if len(prior) > 1 else None)):
                it = _item(k, name, bb, per, v, pv, w, ends, s, sc, table)
                if it:
                    out.append(it)
            continue
        if not cur:
            if w and (w - {'updated'}) and not table:
                it = _item(k, name, b, per, None, prior[0] if prior else None, w, ends, s, sc, table, delta=delta)
                if it:
                    out.append(it)
            continue
        if (len(cur) == 2 and cur[0]['unit'] == cur[1]['unit'] and not cur[0].get('growth') and not cur[1].get('growth')
                and all(isinstance(c.get('end'), int) and isinstance(c.get('start'), int) for c in cur)):
            # positions count in the sentence (values() read the clause after the sentence's start)
            after = [s[cur[0]['end']:cur[1]['start']], s[cur[1]['end']:cur[1]['end'] + 40]]
            pers = [_periods(a) for a in after]
            if pers[0] and pers[1] and pers[0][0][1] != pers[1][0][1]:
                dated = [x for _, x in _periods(s) if re.search(r'\d{4}', x)]
                for v, ps_ in zip(cur, pers):
                    pv_ = ps_[0][1]
                    pv_ = pv_ if re.search(r'\d{4}', pv_) else _merge(pv_, next((d for d in dated if d != pv_), None) or ctx.get('period'))
                    it = _item(k, name, b, pv_, v, None, w, ends, s, sc, table)
                    if it:
                        out.append(it)
                continue
        main = cur[0]
        # a growth rate first ("growth of 5% to 7%, or $X to $Y"): the amount is the guided figure, the rate its growth
        if main.get('growth') and len(cur) > 1 and not cur[1].get('growth'):
            main = cur[1]
        bases = ['GAAP', 'non-GAAP'] if both and not resp else [b]
        for bb in bases:
            it = _item(k, name, bb, per, main, prior[0] if prior else None, w, ends, s, sc, table, delta=delta)
            if it:
                out.append(it)
        for extra in cur[1:3]:
            if extra is main or not (extra.get('growth') or extra['unit'] != main['unit']):
                continue
            it = _item(k, name, bases[0], per, extra, None, w, ends, s, sc, table)
            if it:
                out.append(it)
    return out


def _unit(k, v):
    u = v['unit']
    if v.get('growth') and u == 'pct':
        return 'growth'
    if u == 'bps':
        return 'bps'
    if k in PS:
        return 'ps' if u in ('usd', 'num') else ('growth' if u == 'pct' else None)
    if k in PCT:
        return 'pct' if u == 'pct' else None
    if k in MONEY:
        if u == 'pct':
            return 'growth'
        if u == 'x':
            return None
        return 'usd' if u in ('usd', 'num') else None
    return None


def _item(k, name, b, per, v, pv, said, ends, s, scope, table, delta=None):
    if v is None:
        it = {'metric': k, 'name': name, 'basis': '' if k == 'revenue' and b != 'non-GAAP' else b, 'period': per or '', 'unit': '',
              'lo': None, 'hi': None, 'said': _primary(said), 'quote': s.strip()[:280]}
        if delta:
            u = _unit(k, delta)
            if u:
                it['delta'] = {'v': delta['lo'], 'unit': u}
        if ends:
            it['ends'] = ends[0]
        return it
    u = _unit(k, v)
    if not u:
        return None
    if u == 'usd' and k in MONEY and k != 'other_income' and v['lo'] < 0 and k not in ('net_income', 'operating_income', 'fcf', 'ebitda'):
        return None
    if u == 'usd' and max(abs(v['hi']), abs(v['lo'])) < 100_000:
        return None                      # "$5" with no scale, a footnote "1": a price or a marker, not a guided total
    if u == 'ps' and max(abs(v['hi']), abs(v['lo'])) >= 1000:
        return None                      # a per-share figure read with a table's "in thousands"
    it = {'metric': k, 'name': name, 'basis': '' if k == 'revenue' and b != 'non-GAAP' else b, 'period': per or '', 'unit': u,
          'lo': _r(v['lo']), 'hi': _r(v['hi'])}
    if v.get('approx'):
        it['approx'] = True
    if v.get('bound'):
        it['bound'] = v['bound']
    if scope:
        it['scope'] = scope
    if pv is not None and _unit(k, pv) == u:
        pv = _apply_pm(pv)
        it['prior'] = {'lo': _r(pv['lo']), 'hi': _r(pv['hi']), 'src': 'release'}
    if said:
        it['said'] = _primary(said)
        if 'narrowed' in said or 'widened' in said:
            it['said_range'] = 'narrowed' if 'narrowed' in said else 'widened'
    if ends:
        it['ends'] = ends[0]
    if delta:
        du = _unit(k, delta)
        if du:
            it['delta'] = {'v': _r(delta['lo']), 'unit': du}
    it['quote'] = s.strip()[:280]
    return it


def _r(x):
    return None if x is None else (round(x, 4) if abs(x) < 1000 else round(x))


def _primary(tags):
    tags = set(tags or ())
    if 'raised' in tags and 'lowered' in tags:
        return 'mixed'
    return next((t for t in PRIORITY if t in tags), None)


VERSION_COL = re.compile(r'(?i)\b(?:as of|original(?:ly)?(?: from| as of)?|updated|revised|issued)\s+(?:[a-z]{3,9}\.? \d{1,2},? \d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})')


def _columns(p):
    """An outlook table's header: ['prior', 'current'] (or with a quarter column) when it says so; a table of versions
    ("Original from 2.19.2026 · As of 5.21.2026 · As of 8.20.2026"): ['versions', n] — the last column current, the one
    before it the prior, "Unchanged" repeating the column to its left."""
    low = p.lower()
    vs = VERSION_COL.findall(p)
    if len(vs) >= 2:
        return ['versions', len(vs)]
    pers = []
    for _, x in _periods(p):
        if x != 'long-term' and x not in pers and re.search(r'\d{4}', x):
            pers.append(x)
    if len(pers) >= 2 and not values(p) and len(p) <= 160:
        return pers
    if re.search(r'(?<![-\w])GAAP\b.*\bnon-?GAAP\b', p, re.I) and not values(p) and len(p) <= 80:
        return ['basis:GAAP', 'basis:non-GAAP']                # "Q4 2026 GAAP Non-GAAP"
    asof = re.findall(r'as of [a-z]{3,9}\.? \d{1,2},? \d{4}', low)
    if len(asof) == 2:
        return ['prior', 'current']
    m = re.search(r'\b(prior|previous|original|initial)\b.*\b(revised|updated|current|new|raised|lowered)\b', low)
    if m:
        cols = ['prior', 'current']
        rest = low[m.end():]
        q = PER_Q.search(rest)
        if q and re.search(r'guidance|outlook', rest[q.end():q.end() + 20]):
            cols.append(period(rest[q.start():]))
        return cols
    return None


def _reported(paras, filed=None):
    """(year, quarter, fiscal) of the results a release reports ("third quarter 2026 results"), or None. A quarter named
    without its year ("Q3 Results Demonstrate …") takes the year of the filing date (the calendar quarter just ended)."""
    bare = None
    for p in paras:
        if not re.search(r'(?i)\b(?:results?|reports?|reported|announces?|earnings)\b', p):
            continue
        m = PER_Q.search(p)
        if m and m.group('y'):
            n = ORD.get((m.group('w') or '').lower()) or int(m.group('n') or m.group('n2'))
            return (_yr(m.group('y')), n, bool(m.group('f')))
        if m and bare is None and not (m.group('f') or m.group('f0') or m.group('f1')) and re.search(r'(?i)\bresults?\b', p):
            bare = ORD.get((m.group('w') or '').lower()) or int(m.group('n') or m.group('n2'))
        # "fourth quarter and full year 2023 results", "fourth quarter and fiscal 2026 results"
        m = re.search(r'(?i)\b(first|second|third|fourth)[- ]quarter and (?:the )?(?:full[- ]year|fiscal(?: year)?|full fiscal year|year[- ]end)\s*(?:of\s+)?(?:fiscal\s+)?(20\d\d)\b', p)
        if m:
            return (int(m.group(2)), ORD[m.group(1).lower()], bool(re.search(r'(?i)fiscal', m.group(0))))
    if bare and filed and re.match(r'^\d{4}-\d{2}', filed):
        y, mo = int(filed[:4]), int(filed[5:7])
        return (y if 3 * bare <= mo else y - 1, bare, False)
    return None


def _past(per, reported):
    """A period already reported (or earlier): results, not guidance."""
    if not per or not reported:
        return False
    y, q, fis = reported
    m = re.match(r'^Q([1-4]) (FY)?(\d{4})$', per)
    if m:
        return (int(m.group(3)), int(m.group(1))) <= (y, q) and bool(m.group(2)) == fis or int(m.group(3)) < y - (0 if bool(m.group(2)) == fis else 1)
    m = re.match(r'^FY(\d{4})$', per)
    return bool(m) and (int(m.group(1)) < y or int(m.group(1)) == y and q == 4)


def read(paras, limit=1500, filed=None):
    """The release's guidance: {'label', 'tags', 'quote', 'items'}; label is the release's main change (withdrawn, mixed,
    raised, lowered, narrowed, widened, initiated, reaffirmed, updated) or None."""
    tags, quotes, items = set(), {}, []
    section = None                     # {'period', 'basis', 'scale', 'columns', 'left'}
    carry = None
    reported = _reported(paras[:12])
    # no year named for the quarter reported: the filing date's calendar year, used only to date figures that name no
    # period at all (a fiscal company's own year naming may differ, so it is neither used for quarters nor passed on)
    guess = None if reported else _reported(paras[:12], filed)
    for p in paras[:limit]:
        p = p.strip()
        if not p or re.search(r'(?i)forward[- ]looking statements|safe harbor|cautionary (?:note|statement)', p[:140]) and len(p) > 160:
            continue
        short = len(p) < 110
        if section and (STOP_HEAD.search(p) and short or section['left'] <= 0):
            section = None
        heading = (short and HEAD.search(p) and not BOILER.search(p) and not re.search(r'(?i)non-gaap|reconcil|forward-looking', p)
                   and not values(p) and not p.endswith('.') and (not p.lstrip().startswith(('•', '·', '◦', '▪', '-', '–')) or p.rstrip().endswith(':'))
                   and (p.rstrip().endswith(':') or not VERB_ANY.search(p))
                   and not re.search(r'(?i)\b(?:results?|reports?|reported|announces?|highlights|delivers?|posts?)\b', p))
        if section:
            section['seq'] = section.get('seq', 0) + 1
        if heading and section and section.get('head_seq') == section.get('seq', 0) - 1 and len(p) <= 70:
            # under a table's first column title, the next title ("Guidance Full Year FY27") or a bare "Guidance": still
            # the header, not a new section
            pp = period(p, None)
            if pp and pp != 'long-term':
                pp = pp if re.search(r'\d{4}', pp) else _merge(pp, section.get('period')) or pp
                heads = section.setdefault('heads', [section['period']] if section.get('period') else [])
                if pp not in heads:
                    heads.append(pp)
                    section['columns'] = list(heads) if len(heads) > 1 else None
                    section['period'] = heads[0]
            bb = basis(p)
            if bb:                                     # "FQ1-27 GAAP Outlook" then "Non-GAAP Outlook": a column each
                bs = section.setdefault('bases', [])
                if bb not in bs:
                    bs.append(bb)
                if len(bs) > 1 and not section.get('heads', [None])[1:]:
                    section['columns'] = ['basis:' + x for x in bs]
            section['head_seq'] = section['seq']
            continue
        if heading:
            pp0 = period(p, None)
            # a heading right after a line that named the period ("… guidance for the first quarter of 2027:" then the
            # table's title "FQ1-27 GAAP Outlook"): the period carries on
            if not pp0 and section and section.get('head_seq') is not None and section.get('head_seq') >= section.get('seq', 0) - 1:
                pp0 = section.get('period')
            section = {'period': pp0, 'basis': basis(p), 'scale': _section_scale(p) or 1.0, 'columns': None, 'left': 45, 'seq': 0,
                       'head_seq': 0 if period(p, None) else None, 'bases': [basis(p)] if basis(p) else []}
            hc = _columns(p)
            if hc:
                section['columns'] = hc
            carry = None
        elif section:
            section['left'] -= 1
            sc = _section_scale(p)
            if sc and len(p) < 160:
                section['scale'] = sc
            cols = _columns(p)
            if cols and not values(p):
                section['columns'] = cols
                pp = period(p, None) if cols[0].startswith('basis:') else None
                if pp and pp != 'long-term':           # "Q4 2026 GAAP Non-GAAP": the table's period too
                    section['period'] = pp if re.search(r'\d{4}', pp) else _merge(pp, section.get('period')) or pp
                continue
            if len(p) <= 40 and not values(p) and section.get('head_seq') == section['seq'] - 1 and basis(p) and not period(p, None):
                bs = section.setdefault('bases', [])
                if basis(p) not in bs:
                    bs.append(basis(p))
                if len(bs) > 1:
                    section['columns'] = ['basis:' + x for x in bs]
                section['head_seq'] = section['seq']
                continue
            # a short heading or a table header that names a period: the section's period from here on ("Third quarter",
            # "Fiscal year 2027", "Consolidated metric Q3 FY27", "For the third quarter of 2026, we expect:"); two of them in a
            # row ("Q3 FY27 Guidance", "Full Year FY27 Guidance") are the columns of the table that follows
            if len(p) <= 120 and not values(p) and not BASEFIG.search(p) and (p.rstrip().endswith(':') or len(p) <= 70):
                pp = period(p, None)
                if pp and pp != 'long-term':
                    pp = pp if re.search(r'\d{4}', pp) else _merge(pp, section.get('period')) or pp
                    heads = section.get('heads') or []
                    if heads and section.get('head_seq') == section['seq'] - 1 and pp not in heads and not p.rstrip().endswith(':'):
                        heads.append(pp)
                        section['columns'] = list(heads)
                    else:
                        heads = [pp]
                        section['period'] = pp
                        if not p.rstrip().endswith(':'):
                            section['columns'] = None
                    section['heads'], section['head_seq'] = heads, section['seq']
                    continue
        for s in _sentences(p):
            if len(s) > 600:
                continue
            w, e = words(s)
            if w:
                tags |= w
                for t in w:
                    quotes.setdefault(t, []).append(s)
            if BOILER.search(s) or NOT_CHANGE.search(s) and not w:
                continue
            if BASEFIG.search(s):
                continue
            if re.search(r'(?i)\b(?:three|six|nine|twelve) months ended\b|\byear ended\b|\bquarter ended\b', s) and not re.search(r'(?i)\b(?:expect|anticipat|guidance|outlook|forecast|project|will)\w*', s):
                continue
            in_table = bool(section) and (len(s) < 160 or s.lstrip().startswith(('•', '·', '◦', '▪')))
            if in_table and RESULT_ROW.search(s) and not re.search(r'(?i)\bto\b|–|—|\+/-|±|approximately|about|range|between|increase|decrease|flat', s):
                continue
            if not in_table and not FORWARD.search(s) and not w:
                continue
            if PAST.search(s) and not w and not re.search(r'(?i)\b(?:expect|anticipat|guidance|outlook|forecast|project)', GUIDE_CMP.sub('', s)):
                continue
            ctx = {'period': (section or {}).get('period'), 'basis': (section or {}).get('basis', '')}
            got = _items_of(s, ctx, w, e, table=in_table, scale=(section or {}).get('scale', 1.0),
                            columns=(section or {}).get('columns') if in_table else None, carry=carry if in_table else None)
            if in_table and not FORWARD.search(s):        # a bare table row: no period is assumed for it
                for it in got:
                    it['_tbl'] = True
            items.extend(got)
            sp = mentions(s)
            if in_table and sp and not values(s, table=True):
                carry = (sp[0][2], sp[0][3], sp[0][4])
            elif in_table and got:
                carry = None
    # a quarter named without its year belongs to the year of the quarter just reported: the same quarter or a later one
    # this year, an earlier number next year ("the first quarter" in a fourth-quarter release)
    if reported:
        ry, rq, rfis = reported
        for it in items:
            m = re.match(r'^Q([1-4])( FY)?$', it.get('period') or '')
            if m:
                n = int(m.group(1))
                it['period'] = f"Q{n} {'FY' if (m.group(2) or rfis) else ''}{ry + 1 if n < rq else ry}"
    years = [int(m.group(1)) for it in items for m in [re.match(r'^FY(\d{4})$', it.get('period') or '')] if m]
    if not years and (reported or guess):
        years = [(reported or guess)[0] + (1 if (reported or guess)[1] == 4 else 0)]
    if years:
        y = max(set(years), key=lambda v: (years.count(v), -v))
        for it in items:
            if it.get('period') == 'FY':
                it['period'] = f'FY{y}'
            elif re.match(r'^Q[1-4]( FY)?$', it.get('period') or ''):
                it['period'] = _merge(it['period'], f'FY{y}' if ' FY' in it['period'] else str(y))
    # one style per year: when the release names a fiscal quarter of a year ("Q3 FY27"), its other quarters of that year are too
    fisc = {m.group(1) for it in items for m in [re.match(r'^Q[1-4] FY(\d{4})$', it.get('period') or '')] if m}
    for it in items:
        m = re.match(r'^Q([1-4]) (\d{4})$', it.get('period') or '')
        if m and m.group(2) in fisc:
            it['period'] = f'Q{m.group(1)} FY{m.group(2)}'
    named = [it['period'] for it in items if it.get('period') and it.get('lo') is not None and it['period'] != 'long-term'
             and not _past(it['period'], reported)]          # a figure with no period of its own: the release's main guided period
    if named:
        common = max(set(named), key=named.count)
        for it in items:
            if not it.get('period'):
                it['period'] = common
                it['period_assumed'] = True
    if not named and (reported or guess):          # nothing names a period: the year the release reports in ("Updated 2026 guidance")
        y = (reported or guess)[0] + (1 if (reported or guess)[1] == 4 else 0)
        for it in items:
            if not it.get('period') and not it.get('_tbl'):
                it['period'] = f'FY{y}'
                it['period_assumed'] = True
    for it in items:
        it.pop('_tbl', None)
    items = [it for it in items if not _past(it.get('period'), reported)]
    items = dedupe(items)
    for it in items:
        compare_item(it)
        if it.get('change') and it['change'] not in ('initiated', 'new'):
            tags.add(it['change'])
        if it.get('range'):
            tags.add(it['range'])
    label = _primary(tags)
    pick = lambda xs: next((x for x in xs if re.search(r'\d', x) and re.search(r'\$|%', x)), xs[0]) if xs else ''
    quote = pick(quotes.get(label) or (quotes.get('raised', []) + quotes.get('lowered', []) if label == 'mixed' else [])
                 or next((quotes[t] for t in PRIORITY if quotes.get(t)), []))
    return {'label': label, 'tags': [t for t in PRIORITY if t in tags], 'quote': quote, 'items': items[:40],
            'reported': list(reported) if reported else None}   # the period whose results the release reports, in the company's own naming


def key(it):
    return (it['metric'], it.get('basis') or '', it.get('period') or '', it.get('unit') or '', it.get('scope') or '')


def dedupe(items):
    """One item per metric, basis, period and unit: the one with a stated prior, then with numbers, then the first."""
    best = {}
    order = []
    for it in items:
        k = key(it) if it.get('lo') is not None else key(it) + ('words',)
        if k not in best:
            best[k] = it
            order.append(k)
            continue
        old = best[k]
        rank = lambda x: (x.get('prior') is not None, x.get('said') is not None, x.get('lo') is not None)
        if rank(it) > rank(old):
            merged = dict(it)
            if not merged.get('said') and old.get('said'):
                merged['said'] = old['said']
            best[k] = merged
        elif not old.get('said') and it.get('said'):
            best[k] = dict(old, said=it['said'])
    out = [best[k] for k in order]
    with_numbers = {key(x)[:3] for x in out if x.get('lo') is not None}
    return [x for x in out if x.get('lo') is not None or (x['metric'], x.get('basis') or '', x.get('period') or '') not in with_numbers]


# ------------------------------------------------------------------ comparing ranges
def compare(cur, old, tol=0.002):
    """{'change': raised | lowered | reaffirmed, 'range': narrowed | widened | None, 'ends': 'low end raised' …} of a
    range against the earlier range (both {lo, hi})."""
    lo, hi, plo, phi = cur['lo'], cur['hi'], old['lo'], old['hi']
    if None in (lo, hi, plo, phi):
        return {}
    scale = max(abs(plo), abs(phi), abs(lo), abs(hi), 1e-9)
    eps = scale * tol
    mid, pmid = (lo + hi) / 2, (plo + phi) / 2
    w, pw = hi - lo, phi - plo
    out = {'change': 'raised' if mid > pmid + eps else 'lowered' if mid < pmid - eps else 'reaffirmed',
           'range': 'narrowed' if w < pw - eps else 'widened' if w > pw + eps else None}
    dl, dh = lo - plo, hi - phi
    moved = []
    if abs(dl) > eps:
        moved.append('low end ' + ('raised' if dl > 0 else 'lowered'))
    if abs(dh) > eps:
        moved.append('high end ' + ('raised' if dh > 0 else 'lowered'))
    if len(moved) == 1 or (moved and out['range']):
        out['ends'] = ' · '.join(moved)
    out['delta_mid'] = _r(mid - pmid)
    out['delta_pct'] = round((mid - pmid) / abs(pmid) * 100, 2) if pmid else None
    return out


def compare_item(it):
    """Sets the item's change from its numbers (a stated prior), else from its own sentence's words."""
    if it.get('lo') is not None and it.get('prior'):
        it.update({k: v for k, v in compare(it, it['prior']).items() if v is not None})
        if it.get('said') == 'reaffirmed' and it.get('change') != 'reaffirmed':
            it['said_vs_numbers'] = 'the words say reaffirmed; the numbers moved'
        return it
    s = it.get('said')
    if s in ('raised', 'lowered', 'reaffirmed', 'initiated', 'withdrawn', 'mixed'):
        it['change'] = s
    elif s in ('narrowed', 'widened'):
        it['change'] = 'reaffirmed' if s == 'narrowed' and it.get('ends') is None else it.get('change')
        it['range'] = s
    if it.get('said_range'):
        it.setdefault('range', it['said_range'])
    return it


def diff(items, earlier):
    """Items of the latest release against an earlier release's items (newest first): an item without a stated prior gets
    the earlier range of the same metric, basis, period, unit and scope, and its change from the numbers. Items the
    earlier release had and this one dropped are not returned (a release need not repeat every figure)."""
    out = []
    for it in items:
        it = dict(it)
        if it.get('lo') is not None and not it.get('prior'):
            for when, rows in earlier:
                old = next((x for x in rows if x.get('lo') is not None and key(x) == key(it)), None)
                if old:
                    it['prior'] = {'lo': old['lo'], 'hi': old['hi'], 'src': 'earlier release', 'filed': when}
                    it.pop('change', None)
                    it.pop('range', None)
                    compare_item(it)
                    break
            else:
                if not it.get('change'):
                    it['change'] = 'initiated' if it.get('said') == 'initiated' else 'new'
        out.append(it)
    return out


def tags_of(items, words_tags=()):
    t = set(words_tags)
    for it in items:
        if it.get('change') in ('raised', 'lowered', 'reaffirmed', 'initiated', 'withdrawn'):
            t.add(it['change'])
        if it.get('range'):
            t.add(it['range'])
    return [x for x in PRIORITY if x in t or (x == 'mixed' and {'raised', 'lowered'} <= t)]


def phrase(tags):
    """'raised and narrowed', 'lowered', 'reaffirmed' … — the words a reader sees."""
    t = [x for x in tags if x != 'mixed']
    if 'raised' in t and 'lowered' in t:
        head = 'raised and lowered'
    else:
        head = next((x for x in ('withdrawn', 'raised', 'lowered', 'initiated', 'reaffirmed', 'updated') if x in t), None)
    rng = next((x for x in ('narrowed', 'widened') if x in t), None)
    if head and rng:
        return f'{head} and {rng}'
    return head or rng or ''
