"""X posts from the Filings radar (disclosures/app/filings_radar.py, published at disclosures/data/research/filings/):
red flags, SEC comment letters, buyback authorizations, at-the-market programs and dilution, IPO lock-ups, merger-arb
spreads, CEO pay against the shareholder return, and officials' trades in companies with federal contracts or lobbying.
Every number in a post is in its task; wording stays factual (a filing says what it says; no accusation, no advice)."""
import datetime as dt

from . import engage as G, social
from .xkinds import kind

FLAG_WORDS = {'late': 'late filing notice', 'auditor': 'auditor change', 'restatement': 'restatement', 'listing': 'exchange listing notice'}


def _rf(site, name):
    try:
        return G.hub_cached(site, f"research/filings/{name}.json") or {}
    except Exception as err:
        print(f"filings radar: {name} not available ({str(err)[:90]})")
        return {}


def _tk(t):
    return (t or "").upper().replace("-", ".")


def _fresh(filed, today, days=2):
    return (filed or "") >= (today - dt.timedelta(days=days)).isoformat()


def _lead(filed, today, strong=False):
    return ("BREAKING: " if strong else "JUST FILED: ") if _fresh(filed, today) else ""


def _plan(kind_, task, tks, fbs, items=None, allowed=None, lines=False, key=None, **more):
    return {"kind": kind_, "task": task, "cashtags": tks, "allowed": allowed, "items": items or [], "fallback": fbs[0], "fallbacks": fbs,
            "lines": lines, "event_key": key, **more}


# ------------------------------------------------------------------ red flags
@kind("red_flag", tag="8k", cooldown=4, schedule=["events"], label="✦ Red flag filing", corpus=6,
      title="A late filing notice, auditor change, restatement or exchange listing notice filed in the last two days",
      guide="A filing that flags trouble: say which form and what it reports (the auditor's name, the periods restated, the rule and "
            "deadline). Facts from the filing only; never imply wrongdoing; end with a question.")
def plan_red_flag(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "redflags")
    for r in d.get("rows") or []:
        tk = _tk(r.get("ticker"))
        if not tk or not _fresh(r.get("filed"), today, 3) or not state_ok("red_flag", r["accession"], hours=24 * 30):
            continue
        name = G.short_name(r.get("company") or tk, tk)
        filed = G._day(r["filed"])
        what = FLAG_WORDS.get(r["kind"], r["kind"])
        if r["kind"] == "auditor":
            detail = (f"{r.get('old') or 'its auditor'} {r.get('change') or 'changed'}" + (f"; {r['new']} engaged" if r.get("new") else "")
                      + ("; disagreements reported" if r.get("disagreements") else "; no disagreements" if r.get("disagreements") is False else "")
                      + ("; a material weakness is mentioned" if r.get("material_weakness") else "") + ("; going-concern doubt is mentioned" if r.get("going_concern") else ""))
            fb1 = f"{_lead(r['filed'], today, r['severity'] == 'high')}${tk} 8-K (Item 4.01, {filed}): {r.get('old') or 'the auditor'} {r.get('change') or 'changed'}" + (f", {r['new']} engaged" if r.get("new") else "") + ". How do you read an auditor change?"
        elif r["kind"] == "restatement":
            per = ", ".join(G._day(p) for p in (r.get("periods") or [])[:3])
            detail = "earlier financial statements should no longer be relied on" + (f" (periods ended {per})" if per else "") + (f". Why: {r['reason']}" if r.get("reason") else "")
            fb1 = f"{_lead(r['filed'], today, True)}${tk} 8-K (Item 4.02, {filed}): its earlier financial statements should no longer be relied on" + (f" — periods ended {per}" if per else "") + ". What changes for you?"
        elif r["kind"] == "listing":
            detail = f"{r.get('exchange') or 'the exchange'} notice over {r.get('reason') or 'a listing rule'}" + (f", until {G._day(r['deadline'])} to regain compliance" if r.get("deadline") else "") + ("; a delisting determination" if r.get("determination") else "")
            fb1 = f"{_lead(r['filed'], today, r.get('determination'))}${tk} 8-K (Item 3.01, {filed}): a {r.get('exchange') or 'listing'} notice over {r.get('reason') or 'a listing rule'}" + (f", with until {G._day(r['deadline'])} to regain compliance" if r.get("deadline") else "") + ". Fixable, or the start of something?"
        else:
            detail = f"{r.get('form')}: the report is late" + (f". The company's reason: {r['reason']}" if r.get("reason") else "") + ("; it expects a significant change in results" if r.get("significant_change") else "")
            fb1 = f"{_lead(r['filed'], today, r['severity'] == 'high')}${tk} filed an {r.get('form')} on {filed}: its report is late" + ("; it expects a significant change in results" if r.get("significant_change") else "") + ". Housekeeping or a warning sign?"
        form = r.get("form") or "8-K"
        form_txt = f"{form} Item {r['item']}" if r.get("item") else (form if r["kind"] != "auditor" else "8-K Item 4.01") if r["kind"] != "restatement" else "8-K Item 4.02"
        if r["kind"] == "listing" and not r.get("item"):
            form_txt = "8-K Item 3.01"
        task = (f"RED FLAG FILING by ${tk} ({name}), filed {r['filed']} ({form_txt}): {what}. {detail}. Severity (a rule of thumb): {r['severity']}."
                + (f"\nThe filing's words: “{r['quote'][:280]}”" if r.get("quote") else "")
                + "\n\n" + ("Start with “BREAKING:” or “JUST FILED:” (filed within two days). " if _fresh(r["filed"], today) else f"Say it was filed {filed}. ")
                + "Say which form and what it reports, with the names, periods or dates above; no facts beyond them, no accusation, no prediction; one closing question.")
        fb2 = f"${tk}: {what} filed {filed} — {detail.split('. ')[0]}. Worth a closer look at the filing?"
        e = by_ticker.get(tk)
        return _plan("red_flag", task, [tk], [fb1, fb2], items=[x for x in [G._chart(site, by_ticker, tk)] if x], key=f"red_flag:{r['accession']}",
                     tags=G.H.pick("8k", e, key=f"red_flag:{r['accession']}"))
    return None


# ------------------------------------------------------------------ SEC letters
@kind("sec_letter", tag="sec_action", cooldown=24, schedule=["evening"], label="✦ SEC comment letter", corpus=4,
      title="A finished SEC review of a company's filing: what the staff asked about",
      guide="SEC comment letters are released after a review is finished: say the form reviewed, how many letters, the topics; "
            "a routine review, not an investigation — say so when the letter closes the review.")
def plan_sec_letter(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "letters")
    names = d.get("topic_names") or {}
    for t in d.get("threads") or []:
        tk = _tk(t.get("ticker"))
        if not tk or not _fresh(t.get("last"), today, 10) or not state_ok("sec_letter", tk, hours=24 * 60) or not t.get("topics"):
            continue
        name = G.short_name(t.get("company") or tk, tk)
        topics = ", ".join(names.get(x, x) for x in t["topics"][:3])
        about = (t.get("about_form") or "a filing") + (f" for the period ended {G._day(t['about_period'])}" if t.get("about_period") else "")
        ex = next((x.get("excerpt") for x in t.get("letters") or [] if x.get("excerpt")), "")
        task = (f"SEC COMMENT LETTERS on ${tk} ({name}), released {t['last']}: {t['n']} letters between the SEC staff and the company about its {about}, "
                f"from {t['first']} to {t['last']}" + ("; the staff closed the review" if t.get("closed") else "") + f". Topics: {topics}."
                + (f"\nWhat the staff asked: “{ex[:260]}”" if ex else "")
                + "\n\nThese letters are released only after the review is finished: a routine review, not an investigation. Say the form reviewed, "
                  "the number of letters and the topics; no judgment on the company; one closing question.")
        fb1 = f"The SEC's review of ${tk}'s {about} is out: {t['n']} letters, on {topics}. Routine questions, or something to read closely?"
        fb2 = f"${tk} — SEC comment letters released {G._day(t['last'])}: the staff asked about {topics} in its {t.get('about_form') or 'filing'}. {t['n']} letters in all. What would you ask?"
        return _plan("sec_letter", task, [tk], [fb1, fb2], items=[x for x in [G._chart(site, by_ticker, tk)] if x], key=f"sec_letter:{t['cik']}:{t['last']}",
                     tags=G.H.pick("sec_action", by_ticker.get(tk), key=f"sec_letter:{tk}:{t['last']}"))
    return None


# ------------------------------------------------------------------ buybacks
@kind("buyback", tag="capital", cooldown=12, schedule=["events"], label="✦ Buyback authorization", corpus=6,
      title="A share repurchase authorization from an 8-K, as a share of the market cap",
      guide="A buyback authorization: the amount, the share of the market cap it represents, whether it adds to a program and when it "
            "expires. An authorization is permission, not a purchase — never say the company is buying.")
def plan_buyback(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "capital")
    for r in d.get("buybacks") or []:
        tk = _tk(r.get("ticker"))
        if not tk or not r.get("amount") or not _fresh(r.get("filed"), today, 4) or not state_ok("buyback", r["accession"], hours=24 * 30):
            continue
        name = G.short_name(r.get("company") or tk, tk)
        amt, pct = G.money(r["amount"]), (f"{r['pct_mcap'] * 100:.1f}%" if r.get("pct_mcap") else None)
        task = (f"BUYBACK AUTHORIZATION: ${tk} ({name}) filed an 8-K on {r['filed']}: its board authorized" + (" an additional" if r.get("increase") else "")
                + f" {amt} of share repurchases" + (f" — {pct} of its market cap of {G.money(r['mcap'])}" if pct else "")
                + (f"; the program expires {G._day(r['expires'])}" if r.get("expires") else "; no expiration date" if r.get("no_expiration") else "") + "."
                + (f"\nThe release's title: “{r['headline'][:150]}”" if r.get("headline") else "")
                + "\n\nAn authorization is permission to buy, not a purchase. Give the amount and the share of the market cap; one closing question.")
        fb1 = f"{_lead(r['filed'], today)}${tk} authorizes {amt} of buybacks" + (f" — {pct} of its market cap" if pct else "") + (f", expiring {G._day(r['expires'])}" if r.get("expires") else "") + ". Will it use all of it?"
        fb2 = f"${tk} board: " + ("an additional " if r.get("increase") else "a ") + f"{amt} share repurchase authorization (8-K, {G._day(r['filed'])})" + (f", {pct} of the market cap" if pct else "") + ". Return of capital, or support for the stock?"
        return _plan("buyback", task, [tk], [fb1, fb2], items=[x for x in [G._chart(site, by_ticker, tk)] if x], key=f"buyback:{r['accession']}",
                     tags=G.H.pick("capital", by_ticker.get(tk), key=f"buyback:{r['accession']}"))
    return None


# ------------------------------------------------------------------ dilution
@kind("dilution", tag="capital", cooldown=12, schedule=["events"], label="✦ ATM / offering", corpus=6,
      title="A new at-the-market program or offering, as a share of the market cap",
      guide="An at-the-market program or offering: the size, the share of the market cap, and the change in shares outstanding over the "
            "last year when known. Dilution is a fact of the filing; say nothing about where the stock goes.")
def plan_dilution(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "dilution")
    growth = {_tk(g.get("ticker")): g for g in d.get("share_growth") or []}
    for r in d.get("offerings") or []:
        tk = _tk(r.get("ticker"))
        if not tk or r.get("kind") not in ("atm", "firm") or not r.get("amount") or not _fresh(r.get("filed"), today, 4) \
                or not state_ok("dilution", r["accession"], hours=24 * 30):
            continue
        name = G.short_name(r.get("company") or tk, tk)
        what = "an at-the-market program" if r["kind"] == "atm" else "an offering"
        amt, pct = G.money(r["amount"]), (f"{r['pct_mcap'] * 100:.0f}%" if r.get("pct_mcap") else None)
        g = growth.get(tk)
        gline = f" Shares outstanding over the last year: {g['change'] * 100:+.0f}% ({g['shares_year_ago']:,.0f} → {g['shares']:,.0f})." if g else ""
        task = (f"DILUTION: ${tk} ({name}) filed a {r['form']} on {r['filed']}: {what} of up to {amt}" + (f", {pct} of its market cap of {G.money(r['mcap'])}" if pct else "")
                + (f", {r['shares']:,.0f} shares at ${r['price']:,.2f}" if r.get("shares") and r.get("price") else "") + f".{gline}"
                + "\n\nSay what was filed, the size and the share of the market cap; no prediction; one closing question.")
        fb1 = f"{_lead(r['filed'], today)}${tk} files {what} of up to {amt}" + (f" — {pct} of its market cap" if pct else "") + (f". Shares outstanding {g['change'] * 100:+.0f}% in a year." if g else ".") + " Funding growth, or just more shares?"
        fb2 = f"${tk} {r['form']} ({G._day(r['filed'])}): up to {amt} of new shares via {what}" + (f", {pct} of the market cap" if pct else "") + ". What is the money for?"
        return _plan("dilution", task, [tk], [fb1, fb2], items=[x for x in [G._chart(site, by_ticker, tk)] if x], key=f"dilution:{r['accession']}",
                     tags=G.H.pick("capital", by_ticker.get(tk), key=f"dilution:{r['accession']}"))
    return None


# ------------------------------------------------------------------ lock-ups
@kind("lockups", tag="capital", hashtags=["#IPO", "#stocks"], cooldown=24 * 6, schedule=["weekly"], label="✦ IPO lock-ups", corpus=3,
      title="IPO lock-ups expiring in the next two weeks, with the return since pricing",
      guide="Lock-up expiries: one line per IPO with the expiry date and the return since the IPO price. Insiders become free to sell; "
            "whether they do is unknown — say nothing about the stock's direction.")
def plan_lockups(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "ipos")
    soon = (today + dt.timedelta(days=14)).isoformat()
    picks = [r for r in d.get("lockups") or [] if r.get("symbol") and today.isoformat() <= (r.get("lockup_ends") or "") <= soon
             and state_ok("lockups", r["symbol"], hours=24 * 40)][:5]
    if not picks:
        return None
    tks = [_tk(r["symbol"]) for r in picks]

    def line(r):
        s = f"${_tk(r['symbol'])} {G._day(r['lockup_ends'])}"
        return s + (f" ({G.pct_fmt(r['since_ipo'])} since the IPO)" if r.get("since_ipo") is not None else "")
    body = "\n".join(line(r) for r in picks)
    task = ("IPO LOCK-UPS EXPIRING in the next two weeks (insiders and early holders become free to sell; the prospectus date plus its lock-up):\n"
            + "\n".join(f"- ${_tk(r['symbol'])} ({G.short_name(r.get('company') or r['symbol'])}): priced {G._day(r.get('date') or r['filed'])} at ${r['price']:,.2f}, "
                        f"lock-up ends {r['lockup_ends']}" + (f", {G.pct_fmt(r['since_ipo'])} since pricing" if r.get("since_ipo") is not None else "") for r in picks)
            + "\n\nFormat with line breaks: a headline line, one “$TICKER date (return since IPO)” line each, one closing question. No prediction.")
    fbs = [f"IPO lock-ups expiring soon:\n\n{body}\n\nWhich ones see insiders head for the exit?", f"Insiders become free to trade soon:\n\n{body}\n\nLock-up expiry — event or non-event?"]
    return _plan("lockups", task, tks[:2], fbs, allowed=tks, lines=True, key="lockups:" + ",".join(tks), tags=G.H.pick("capital", None, key="lockups:" + ",".join(tks)))


# ------------------------------------------------------------------ merger arbitrage
@kind("merger_arb", tag="8k", hashtags=["#MergerArb", "#MandA"], cooldown=24 * 3, schedule=["morning"], label="✦ Merger-arb spreads", corpus=4,
      title="Pending deals: the spread between the deal price and the target's price, annualized to the expected close",
      guide="Merger-arb spreads: one line per deal, “$TGT ← $ACQ: $X cash, spread +N%”. A wide spread says the market doubts the close; "
            "say that as a question, never as a call.")
def plan_merger_arb(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "deals")
    picks = [x for x in d.get("deals") or [] if x.get("status") == "pending" and x.get("spread") is not None and x.get("target_ticker")
             and -0.05 <= x["spread"] <= 0.6 and state_ok("merger_arb", x["target_ticker"], hours=24 * 20)][:5]
    if len(picks) < 2:
        return None
    tks = [_tk(x["target_ticker"]) for x in picks]
    allowed = tks + [_tk(x["acquirer_ticker"]) for x in picks if x.get("acquirer_ticker")]

    def terms(x):
        return " + ".join(s for s in [f"${x['cash']:,.2f} cash" if x.get("cash") else "", f"{x['ratio']:.4g} shares" if x.get("ratio") else ""] if s)

    def line(x):
        acq = f"${_tk(x['acquirer_ticker'])}" if x.get("acquirer_ticker") else G.short_name(x.get("acquirer") or "an acquirer")
        return f"${_tk(x['target_ticker'])} ← {acq}: {G.pct_fmt(x['spread'], 1)}"
    body = "\n".join(line(x) for x in picks)
    task = ("MERGER ARBITRAGE — pending deals from SEC filings (spread = deal value at the acquirer's last close ÷ the target's last close − 1):\n"
            + "\n".join(f"- ${_tk(x['target_ticker'])} ({G.short_name(x.get('target') or '')}) acquired by {x.get('acquirer') or '?'}"
                        + (f" (${_tk(x['acquirer_ticker'])})" if x.get("acquirer_ticker") else "") + f": {terms(x)} per share, worth ${x['value']:,.2f} vs the target's ${x['target_price']:,.2f} "
                        f"→ spread {G.pct_fmt(x['spread'], 1)}" + (f", {G.pct_fmt(x['annualized'], 0)} annualized to the expected close {x['close_by']}" if x.get("annualized") is not None else "")
                        for x in picks)
            + "\n\nFormat with line breaks: a headline, one “$TGT ← $ACQ: spread” line each, one question (which spread is the market right about?). No advice.")
    fbs = [f"Merger-arb spreads right now:\n\n{body}\n\nWhich deal is the market doubting?", f"Deal price vs the stock, pending mergers:\n\n{body}\n\nWhere is the risk priced right?"]
    return _plan("merger_arb", task, tks[:2], fbs, allowed=allowed, lines=True, key="merger_arb:" + ",".join(tks), tags=G.H.pick("8k", None, key="arb:" + ",".join(tks)))


# ------------------------------------------------------------------ CEO pay vs TSR
@kind("ceo_pay", tag="capital", hashtags=["#CEOpay", "#CorporateGovernance"], cooldown=24 * 2, schedule=["evening"], label="✦ CEO pay vs return", corpus=4,
      title="A CEO's pay against the shareholder return (pay versus performance, from the proxy's XBRL)",
      guide="Pay versus performance: total pay, its change, and the value of $100 invested (TSR) over the same year. The numbers come "
            "from the proxy statement; compare, never judge.")
def plan_ceo_pay(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "paycomp")
    cands = [r for r in d.get("rows") or [] if r.get("total_chg") is not None and r.get("tsr_chg") is not None and (r.get("mcap") or 0) >= 2e9]
    cands.sort(key=lambda r: (not r.get("misaligned"), _tk(r["ticker"]) not in by_ticker, -abs(r["total_chg"] - r["tsr_chg"])))
    for r in cands:
        tk = _tk(r["ticker"])
        if not state_ok("ceo_pay", tk, hours=24 * 120):
            continue
        name = G.short_name(r.get("company") or tk, tk)
        yr = (r.get("fy_end") or "")[:4]
        task = (f"CEO PAY VS SHAREHOLDER RETURN at ${tk} ({name}), fiscal {yr} (pay-versus-performance table in the proxy statement, SEC Item 402(v)): "
                f"total compensation {G.money(r['total'])} ({r['total_chg'] * 100:+.0f}% vs the year before); compensation actually paid {G.money(r['cap'])}; "
                f"the value of $100 invested in the stock at the start of the table: ${r['tsr']:,.0f} ({r['tsr_chg'] * 100:+.0f}% in the year)"
                + (f", peer group ${r['peer_tsr']:,.0f}" if r.get("peer_tsr") else "") + "."
                + "\n\nGive the pay, its change and the shareholder return in the same year; a comparison, not a judgment; one closing question.")
        fb1 = f"${tk} CEO pay, fiscal {yr}: {G.money(r['total'])} ({r['total_chg'] * 100:+.0f}%). The stock's $100 the same year: ${r['tsr']:,.0f} ({r['tsr_chg'] * 100:+.0f}%). Aligned?"
        fb2 = f"Pay vs performance at ${tk}: total compensation {G.money(r['total'])}, up {abs(r['total_chg']) * 100:.0f}%, in a year the shareholder return was {r['tsr_chg'] * 100:+.0f}%. What would you ask the board?" if r["total_chg"] > 0 else \
              f"Pay vs performance at ${tk}: total compensation {G.money(r['total'])} ({r['total_chg'] * 100:+.0f}%) in a year the shareholder return was {r['tsr_chg'] * 100:+.0f}%. Fair?"
        return _plan("ceo_pay", task, [tk], [fb1, fb2], items=[x for x in [G._chart(site, by_ticker, tk)] if x], key=f"ceo_pay:{tk}:{yr}",
                     tags=G.H.pick("capital", by_ticker.get(tk), key=f"ceo_pay:{tk}:{yr}"))
    return None


# ------------------------------------------------------------------ officials, contracts, lobbying
@kind("gov_trades", tag="congress", cooldown=24 * 2, schedule=["evening"], label="✦ Officials & contractors", corpus=4,
      title="An official's trade in a company with large federal contracts or lobbying spend",
      guide="An official's disclosed trade beside the company's federal contracts and lobbying: dates, amounts and sources only; a fact "
            "to note, never an accusation; one closing question.")
def plan_gov_trades(site, rows, c, by_ticker, state_ok, today):
    d = _rf(site, "gov")
    for r in d.get("overlap") or []:
        tk = _tk(r.get("ticker"))
        key = f"{r.get('person')}:{tk}:{r.get('date')}"
        if not tk or not _fresh(r.get("filed"), today, 14) or not state_ok("gov_trades", key, hours=24 * 60):
            continue
        amt = G.amount_range(r.get("amount_min"), r.get("amount_max"))
        verb = {"purchase": "bought", "sale": "sold", "partial sale": "sold part of a holding in"}.get(r.get("type"), "traded")
        bits = []
        if r.get("contracts_90d"):
            bits.append(f"{G.money(r['contracts_90d'])} of federal contract obligations in the last 90 days (USAspending)")
        if r.get("lobbying_4q"):
            bits.append(f"{G.money(r['lobbying_4q'])} of lobbying over four quarters" + (f" ({', '.join(r['lobbying_issues'][:2])})" if r.get("lobbying_issues") else ""))
        ctx = "; ".join(bits)
        task = (f"OFFICIAL'S TRADE: {r['person']} ({r['chamber']}) {verb} ${tk} ({amt}) on {r['date']}, disclosed {r['filed']}. The company: {ctx}."
                "\n\nState the trade (who, what, the range, the dates) and the company's contracts and lobbying as separate facts; no link implied, no "
                "accusation, no prediction; one closing question.")
        fb1 = f"{r['person']} ({r['chamber']}) {verb} ${tk} ({amt}) on {G._day(r['date'])}, per a report filed {G._day(r['filed'])}. The company: {bits[0]}. Worth tracking?"
        fb2 = f"${tk}: {bits[0]}. On {G._day(r['date'])} {r['person']} ({r['chamber']}) {verb} it ({amt}). Two facts side by side — what do you make of them?"
        return _plan("gov_trades", task, [tk], [fb1, fb2], items=[x for x in [G._chart(site, by_ticker, tk)] if x], key="gov_trades:" + key,
                     tags=G.H.pick("congress", by_ticker.get(tk), key="gov:" + key))
    return None


__all__ = ["plan_red_flag", "plan_sec_letter", "plan_buyback", "plan_dilution", "plan_lockups", "plan_merger_arb", "plan_ceo_pay", "plan_gov_trades"]
_ = social
