"""Rule-based English analysis paragraphs (no language model): every sentence is computed from the numbers."""


def _pct(a, b):
    if a is None or b is None or b == 0 or a <= 0 or b <= 0:
        return None
    return (a / b - 1) * 100


def _chg_words(g, noun="up", neg="down"):
    if g is None:
        return None
    if abs(g) < 0.5:
        return "roughly flat"
    return f"{noun if g > 0 else neg} {abs(g):.0f}%"


def _margin(x, r):
    return None if x is None or not r else x / r * 100


def _pp(a, b):
    if a is None or b is None:
        return None
    d = a - b
    if abs(d) < 0.05:
        return "unchanged"
    return f"{'up' if d > 0 else 'down'} {abs(d):.1f} points"


def paragraphs(f, label, Nc, Nq, Ny, lines_struct=None, lines=(None, None, None), py_label="a year earlier"):
    out = []
    R = Nc["R"]
    # 1. top line
    gy, gq = _pct(R, Ny and Ny["R"]), _pct(R, Nq and Nq["R"])
    s = f"Revenue was {f.money(R)} in {label}"
    parts = [p for p in (_chg_words(gy) and f"{_chg_words(gy)} year over year",
                         _chg_words(gq) and f"{_chg_words(gq)} from the previous quarter") if p]
    s += (", " + " and ".join(parts) if parts else "") + "."
    if lines_struct and lines[0]:
        cur, py = lines[0], lines[2] or {}
        leaves = [(l["label"], cur.get(l["id"]), py.get(l["id"])) for l in lines_struct["leaves"] if l["id"] in cur]
        if leaves:
            top = max(leaves, key=lambda x: x[1])
            s += f" {top[0]} was the largest line at {top[1] / R * 100:.0f}% of revenue."
            moves = [(lab, c - p, _pct(c, p)) for lab, c, p in leaves if p]
            if moves and Ny:
                dR = R - Ny["R"]
                best = max(moves, key=lambda x: x[1] if dR >= 0 else -x[1])
                if best[1] * dR > 0 and abs(dR) > 0:
                    s += (f" {best[0]} {'added' if best[1] > 0 else 'lost'} {f.money(abs(best[1]))} year over year"
                          f" ({_chg_words(best[2])}), {abs(best[1]) / abs(dR) * 100:.0f}% of the total change.")
                worst = [m for m in moves if m[2] is not None and m[2] < -0.5]
                if worst and dR > 0:
                    w = min(worst, key=lambda x: x[2])
                    s += f" {w[0]} declined {abs(w[2]):.0f}%."
    out.append(s)

    # 2. profitability
    s = ""
    om = _margin(Nc["oi"], R)
    if Nc["gp_path"] and Nc["gp"] is not None:
        gm = _margin(Nc["gp"], R)
        gm_y = _margin(Ny and Ny.get("gp"), Ny and Ny["R"]) if Ny and Ny.get("gp_path") else None
        s += f"Gross margin was {gm:.1f}%" + (f", {_pp(gm, gm_y)} from {py_label}" if gm_y is not None else "") + ". "
    if Nc["oi"] >= 0:
        om_y = _margin(Ny["oi"], Ny["R"]) if Ny else None
        s += f"Operating profit was {f.money(Nc['oi'])}, a {om:.1f}% margin" + \
             (f" ({_pp(om, om_y)} year over year)" if om_y is not None else "") + "."
        if Ny and Ny["R"] and R > Ny["R"] and Ny["oi"] is not None and Ny["oi"] > 0:
            d_oi, d_r = Nc["oi"] - Ny["oi"], R - Ny["R"]
            if d_oi >= 0:
                inc = d_oi / d_r * 100
                s += (f" Of the extra revenue versus {py_label}, {inc:.0f}% reached operating profit, "
                      f"{'above' if inc > om_y else 'below'} the {om_y:.0f}% margin then.")
            else:
                s += (f" Operating profit fell {f.money(-d_oi)} even though revenue rose {f.money(d_r)} versus {py_label}, "
                      f"so costs grew faster than sales.")
    else:
        s += f"Operating costs exceeded revenue by {f.money(-Nc['oi'])}, an operating margin of {om:.1f}%."
    cost_key = "opex" if Nc["gp_path"] else "costs"
    pool_y = (Ny["pool"] if Ny and Ny["gp_path"] == Nc["gp_path"] else None)
    g_pool = _pct(Nc["pool"], pool_y)
    if g_pool is not None and gy is not None:
        name = "Operating expenses" if cost_key == "opex" else "Total costs"
        s += f" {name} grew {g_pool:.0f}% against revenue growth of {gy:.0f}%." if g_pool >= 0 else \
             f" {name} fell {abs(g_pool):.0f}% while revenue changed {gy:+.0f}%."
    if Nc["items"] and Ny:
        ymap = dict(Ny["items"])
        fast = [(k, v, _pct(v, ymap.get(k))) for k, v in Nc["items"] if ymap.get(k)]
        fast = [x for x in fast if x[2] is not None]
        if fast:
            k, v, g = max(fast, key=lambda x: x[2])
            from .model import ITEM_LABELS
            if g > 10:
                s += f" The fastest-growing cost line was {ITEM_LABELS[k].replace('&amp;', '&')} ({g:+.0f}%)."
    if Nc["pl"] >= 0:
        gni = _pct(Nc["ni"], Ny and Ny["ni"])
        s += f" Net earnings were {f.money(Nc['ni'])}" + (f", {_chg_words(gni)} year over year" if gni is not None else "") + "."
        if Nc["pretax"] > 0 and Nc["tax"] is not None:
            s += f" The effective tax rate was {Nc['tax'] / Nc['pretax'] * 100:.1f}%."
    else:
        s += f" The quarter ended with a net loss of {f.money(-Nc['pl'])}"
        if Nq:
            s += (f", {'narrower' if -Nc['pl'] < -Nq['pl'] else 'wider'} than the previous quarter's "
                  f"{f.money(-Nq['pl'])} loss" if Nq["pl"] < 0 else f", after a profit of {f.money(Nq['pl'])} the previous quarter")
        s += "."
        if Nc["nonop"] < 0 and -Nc["nonop"] > 0.5 * -Nc["pl"]:
            s += f" Net interest and other expense of {f.money(-Nc['nonop'])} was the main reason."
    if abs(Nc["nonop"]) > 0.2 * max(abs(Nc["pretax"]), 1) and Nc["nonop"] > 0:
        s += (f" Non-operating items added {f.money(Nc['nonop'])}, "
              f"{Nc['nonop'] / Nc['pretax'] * 100:.0f}% of pre-tax earnings, so the bottom line overstates operating performance.")
    out.append(s.strip())

    # 3. cash
    if Nc["ocf"] is not None:
        s = f"Operating cash flow was {f.money(Nc['ocf'])}"
        g = _pct(Nc["ocf"], Ny and Ny["ocf"])
        if g is not None:
            s += f" ({_chg_words(g)} year over year)"
        if Nc["pl"] > 0 and Nc["ocf"] > 0:
            s += f", {Nc['ocf'] / Nc['pl'] * 100:.0f}% of net earnings"
        s += "."
        adds = [(n, v) for n, v in (("depreciation and amortization", Nc["da"]), ("share-based compensation", Nc["sbc"])) if v]
        if adds:
            s += " Non-cash charges added back " + " and ".join(f"{f.money(v)} of {n}" for n, v in adds) + "."
        r = Nc["ocf"] - Nc["pl"] - Nc["da"] - Nc["sbc"]
        if abs(r) > 0.05 * abs(Nc["ocf"]):
            s += f" Working capital and other items {'added' if r > 0 else 'used'} {f.money(abs(r))}."
        if Nc.get("capex"):
            fcf = Nc["ocf"] - Nc["capex"]
            s += (f" Capital expenditures of {f.money(Nc['capex'])} left free cash flow of {f.money(fcf)}." if fcf >= 0 else
                  f" Capital expenditures of {f.money(Nc['capex'])} exceeded it, leaving free cash flow of {f.money(fcf)}.")
        out.append(s)
    return out


def compare_bullets(f, q1_label, Nc, Nq, lines_struct=None, lines=(None, None, None)):
    """Three 'what changed vs the previous quarter' bullets for the comparison view."""
    if not Nq:
        return []
    from .model import ITEM_LABELS
    out = []
    R0, R1, o0, o1 = Nq["R"], Nc["R"], Nq["oi"], Nc["oi"]
    dR, dO = R1 - R0, o1 - o0
    m0 = o0 / R0 * 100 if R0 else None
    if dR > 0 and dO >= 0 and m0 is not None and m0 <= 0:
        out.append(f"Revenue rose {f.money(dR)} versus {q1_label} and the operating result improved by {f.money(dO)}, "
                   f"{dO / dR * 100:.0f}% of the added revenue.")
    elif dR > 0 and dO >= 0 and m0 is not None:
        inc = dO / dR * 100
        out.append(f"Revenue rose {f.money(dR)} versus {q1_label}; {inc:.0f}% of it reached operating profit, "
                   f"{'above' if inc > m0 else 'below'} the {m0:.0f}% operating margin in {q1_label}.")
    elif dR > 0:
        out.append(f"Revenue rose {f.money(dR)} versus {q1_label}, but operating profit fell {f.money(-dO)}: "
                   f"costs grew by more than sales.")
    elif dR < 0:
        out.append(f"Revenue fell {f.money(-dR)} versus {q1_label}; operating profit "
                   f"{'rose' if dO > 0 else 'fell'} {f.money(abs(dO))}.")
    else:
        out.append(f"Revenue was unchanged versus {q1_label}.")
    cands = []
    if lines_struct and lines[0] and lines[1]:
        for l in lines_struct["leaves"]:
            a, b = lines[0].get(l["id"]), lines[1].get(l["id"])
            if a is not None and b is not None:
                cands.append((l["label"], a - b, b))
    if Nc["gp_path"] and Nq["gp_path"]:
        cands.append(("Cost of revenue", Nc["cor"] - Nq["cor"], Nq["cor"]))
    qmap = dict(Nq["items"])
    for k, v in Nc["items"]:
        if k in qmap:
            cands.append((ITEM_LABELS[k].replace("&amp;", "&"), v - qmap[k], qmap[k]))
    cands.append(("Non-operating income and expense", Nc["nonop"] - Nq["nonop"], None))
    cands.append(("Income tax", -(Nc["tax"] - Nq["tax"]), None))
    if cands:
        lab, d, base = max(cands, key=lambda x: abs(x[1]))
        if abs(d) > 0.005 * R1:
            pct = f" ({d / base * 100:+.0f}%)".replace("-", "−") if base and base > 0 else ""
            if lab == "Income tax":
                out.append(f"The largest single swing was income tax, {'lower' if d > 0 else 'higher'} by {f.money(abs(d))}.")
            elif lab.startswith("Non-operating"):
                out.append(f"The largest single swing was non-operating items, {'up' if d > 0 else 'down'} {f.money(abs(d))} "
                           f"to {f.delta(Nc['nonop'])}.")
            else:
                out.append(f"The largest single swing was {lab}, {f.delta(d)}{pct}.")
    if Nc["ocf"] is not None and Nq["ocf"] is not None:
        d_ocf, d_pl = Nc["ocf"] - Nq["ocf"], Nc["pl"] - Nq["pl"]
        out.append(f"Operating cash flow {'rose' if d_ocf >= 0 else 'fell'} {f.money(abs(d_ocf))} to {f.money(Nc['ocf'])}, "
                   f"while net earnings {'rose' if d_pl >= 0 else 'fell'} {f.money(abs(d_pl))} to {f.money(Nc['pl'])}.")
    return out
