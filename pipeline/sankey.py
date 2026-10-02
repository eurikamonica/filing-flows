"""Build a Sankey spec in the earnings-sankey standard format from normalized quarter values.

The spec is plain JSON consumed by web/sankey.js: nodes carry column, colour role, label lines and
label side; links carry values (current and previous quarter, for the comparison strips).
"""
import datetime as dt
import math

from .model import ITEM_LABELS, quantities

FOLD = 0.003            # lines smaller than 0.3% of revenue are folded into a label note


class Fmt:
    def __init__(self, revenue):
        self.unit = "B" if revenue >= 1e9 else "M"

    def money(self, v):
        if v is None:
            return "n/a"
        a = abs(v)
        sign = "−" if v < 0 else ""
        if self.unit == "B":
            b = a / 1e9
            return f"{sign}${b:.1f}B" if b >= 0.95 else f"{sign}${b:.2f}B"
        m = a / 1e6
        return f"{sign}${m:,.1f}M" if m >= 0.95 else f"{sign}${a / 1e3:,.0f}K"

    def num(self, v):                       # signed amount without unit, for scale/mix
        x = v / (1e9 if self.unit == "B" else 1e6)
        s = f"{abs(x):.1f}" if abs(x) >= 0.95 else f"{abs(x):.2f}"
        return ("+" if v > 0 else "−" if v < 0 else "±") + s

    def delta(self, v):
        m = self.money(abs(v))
        return ("+" if v > 0 else "−" if v < 0 else "±") + m


def pct_change(a, b):
    if a is None or b is None:
        return "—"
    if a <= 0 or b <= 0:
        return "n/m"
    g = round((a / b - 1) * 100)
    return ("+" if g > 0 else "−" if g < 0 else "") + f"{abs(g)}%"


def share(v, p):
    if not p or v is None or p <= 0:
        return None
    s = v / p * 100
    return f"{s:.1f}%" if s < 10 else f"{s:.0f}%"


class Spec:
    def __init__(self, Qc, Qq, Qy, fmt):
        self.Qc, self.Qq, self.Qy, self.f = Qc, Qq or {}, Qy or {}, fmt
        self.nodes, self.links, self.ids = [], [], {}

    def val(self, Q, key, sign):
        v = Q.get(key)
        return None if v is None else sign * v

    def node(self, nid, col, key, color, name, pos, parent=None, plabel=None, sign=1, style="name", extra=(), notekeys=()):
        n = {"id": nid, "col": col, "key": key, "sign": sign, "color": color, "name": name, "pos": pos,
             "parent": parent, "plabel": plabel, "style": style, "extra": list(extra), "notekeys": list(notekeys),
             "v": self.val(self.Qc, key, sign), "q": self.val(self.Qq, key, sign), "y": self.val(self.Qy, key, sign)}
        self.nodes.append(n)
        self.ids[nid] = n
        return n

    def link(self, s, t, key, color, sign=1):
        v = self.val(self.Qc, key, sign)
        if v is None or v <= 0:
            return
        self.links.append({"s": s, "t": t, "v": v, "q": self.val(self.Qq, key, sign), "color": color})

    def finish(self):
        f = self.f
        for n in self.nodes:
            lines = [[n["style"], n["name"]]]
            val = f.money(n["v"])
            p = self.ids.get(n["parent"])
            if p and n["plabel"]:
                s = share(n["v"], p["v"])
                if s:
                    val += f" · {s} of {n['plabel']}"
            lines.append(["val", val])
            lines.append(["mut", f"Y/Y {pct_change(n['v'], n['y'])} · Q/Q {pct_change(n['v'], n['q'])}"])
            for e in n["extra"]:
                lines.append(["mut", e])
            n["lines"] = lines
            # comparison-variant line: delta vs previous quarter = scale + mix
            if n["q"] is None:
                n["cmp"] = "Δ n/a (no prior quarter)"
            else:
                dlt = n["v"] - n["q"]
                txt = f"Δ {f.delta(dlt)}"
                if p and p["q"] is not None:
                    c0, c1, p0, p1 = n["q"], n["v"], p["q"], p["v"]
                    if p0 <= 0 or p1 <= 0 or c0 < 0 or c1 < 0:
                        txt += " · scale/mix n/m"
                    else:
                        scale = (p1 - p0) * c0 / p0
                        mix = p1 * (c1 / p1 - c0 / p0)
                        assert abs(scale + mix - dlt) <= 1e-6 * max(1, abs(dlt)) + 1
                        txt += f" · scale {f.num(scale)} · mix {f.num(mix)}"
                n["cmp"] = txt
        for n in self.nodes:
            for k in ("key", "sign", "parent", "plabel", "extra", "style"):
                n.pop(k, None)
        return self.nodes, self.links


def _lines_values(lines_struct, vals):
    out = {}
    if not lines_struct or not vals:
        return out
    for leaf in lines_struct["leaves"]:
        if leaf["id"] in vals:
            out[leaf["id"]] = vals[leaf["id"]]
    for g in lines_struct["groups"]:
        if all(m in vals for m in g["members"]):
            out[g["id"]] = sum(vals[m] for m in g["members"])
    return out


def build(Nc, Nq, Ny, lines_struct=None, lines_vals=(None, None, None)):
    """Return (nodes, links, layout_kind) for the current quarter."""
    Qc = quantities(Nc, _lines_values(lines_struct, lines_vals[0]))
    Qq = quantities(Nq, _lines_values(lines_struct, lines_vals[1])) if Nq else {}
    Qy = quantities(Ny, _lines_values(lines_struct, lines_vals[2])) if Ny else {}
    f = Fmt(Nc["R"])
    S = Spec(Qc, Qq, Qy, f)
    R = Nc["R"]

    # ---- revenue sources ----
    col = 0
    if lines_struct and all(("line:" + l["id"]) in Qc for l in lines_struct["leaves"]):
        grouped = {m for g in lines_struct["groups"] for m in g["members"]}
        has_groups = bool(lines_struct["groups"])
        target_of = {m: g["id"] for g in lines_struct["groups"] for m in g["members"]}
        for leaf in lines_struct["leaves"]:
            if leaf["id"] in grouped:
                g = target_of[leaf["id"]]
                glabel = next(x["label"] for x in lines_struct["groups"] if x["id"] == g)
                S.node("L:" + leaf["id"], 0, "line:" + leaf["id"], "rev", leaf["label"], "left", "G:" + g,
                       glabel, notekeys=[leaf["label"]])
        rcol = 2 if has_groups else 1
        for g in lines_struct["groups"]:
            S.node("G:" + g["id"], 1, "line:" + g["id"], "rev", g["label"], "above", "revenue", "revenue",
                   notekeys=[g["label"]])
        for leaf in lines_struct["leaves"]:
            if leaf["id"] not in grouped:
                S.node("L:" + leaf["id"], rcol - 1, "line:" + leaf["id"], "rev", leaf["label"], "left", "revenue",
                       "revenue", notekeys=[leaf["label"]])
        for leaf in lines_struct["leaves"]:
            t = "G:" + target_of[leaf["id"]] if leaf["id"] in grouped else "revenue"
            S.link("L:" + leaf["id"], t, "line:" + leaf["id"], "rev")
        for g in lines_struct["groups"]:
            S.link("G:" + g["id"], "revenue", "line:" + g["id"], "rev")
        col = rcol
    loss = Nc["oi"] < 0 or Nc["pretax"] < 0 or Nc["pl"] < 0
    S.node("revenue", col, "revenue", "rev", "Revenue", "above" if col else "left", style="big",
           notekeys=["net sales", "total revenue", "revenue"])
    nonop_small = abs(Nc["nonop"]) < FOLD * R
    fold_note = (f"after {f.delta(Nc['nonop'])} interest &amp; other" if nonop_small and abs(Nc["nonop"]) > 0 else None)
    item_parent = "opex" if Nc["gp_path"] else "costs"

    def cost_items(c, parent, plabel):
        for k, v in Nc["items"]:
            S.node("I:" + k, c, "item:" + k, "cost", ITEM_LABELS[k], "right", parent, plabel,
                   notekeys=NOTE_KEYS.get(k, []))
            S.link(parent, "I:" + k, "item:" + k, "cost")

    if not loss:
        rc = col
        if Nc["gp_path"]:
            S.node("gp", rc + 1, "gp", "profit", "Gross profit", "above", "revenue", "revenue", notekeys=NOTE_KEYS["gp"])
            S.node("cor", rc + 1, "cor", "cost", "Cost of revenue", "right", "revenue", "revenue", notekeys=NOTE_KEYS["cor"])
            S.link("revenue", "gp", "gp", "profit"); S.link("revenue", "cor", "cor", "cost")
            oc = rc + 2
            if not nonop_small and Nc["nonop"] > 0:
                S.node("nonop_in", oc, "nonop", "profit", "Other income, net", "left", "pretax", "pre-tax",
                       notekeys=NOTE_KEYS["nonop"])
            S.node("oi", oc, "oi", "profit", "Operating profit", "above", "gp", "gross profit", notekeys=NOTE_KEYS["oi"])
            S.node("opex", oc, "opex", "cost", "Operating expenses", "below", "gp", "gross profit",
                   notekeys=NOTE_KEYS["opex"])
            S.link("gp", "oi", "oi", "profit"); S.link("gp", "opex", "opex", "cost")
            cost_parent, cost_plabel = "opex", "opex"
        else:
            oc = rc + 1
            if not nonop_small and Nc["nonop"] > 0:
                S.node("nonop_in", oc, "nonop", "profit", "Other income, net", "left", "pretax", "pre-tax",
                       notekeys=NOTE_KEYS["nonop"])
            S.node("oi", oc, "oi", "profit", "Operating profit", "above", "revenue", "revenue", notekeys=NOTE_KEYS["oi"])
            S.node("costs", oc, "costs", "cost", "Costs &amp; expenses", "below", "revenue", "revenue",
                   notekeys=NOTE_KEYS["costs"])
            S.link("revenue", "oi", "oi", "profit"); S.link("revenue", "costs", "costs", "cost")
            cost_parent, cost_plabel = "costs", "costs"
        S.node("pretax", oc + 1, "pretax", "profit", "Pre-tax earnings", "above", "revenue", "revenue",
               extra=[fold_note] if fold_note else [], notekeys=NOTE_KEYS["pretax"])
        if not nonop_small and Nc["nonop"] < 0:
            S.node("nonop_out", oc + 1, "nonop", "cost", "Other expense, net", "right", "oi", "operating profit",
                   sign=-1, notekeys=NOTE_KEYS["nonop"])
            S.link("oi", "nonop_out", "nonop", "cost", sign=-1)
            S.link("oi", "pretax", "pretax", "profit")
        elif not nonop_small:
            S.link("nonop_in", "pretax", "nonop", "profit")
            S.link("oi", "pretax", "oi", "profit")
        else:
            S.link("oi", "pretax", "pretax" if Nc["nonop"] < 0 else "oi", "profit")
        cost_items(oc + 1, cost_parent, cost_plabel)

        # pre-tax -> tax / minority / net
        nc = oc + 2
        has_nci = Nc["nci"] > 0.001 * R
        net_key = "ni" if has_nci else "pl"
        bridge = Nc["ocf"] is not None
        if Nc["tax"] < 0:
            S.node("taxben", oc + 1, "taxben", "profit", "Income tax benefit", "left", "net", "net earnings",
                   notekeys=NOTE_KEYS["tax"])
        S.node("net", nc, net_key, "profit", "Net earnings", "above_left" if bridge else "right", "pretax", "pre-tax",
               extra=["attributable to shareholders"] if has_nci else [], notekeys=NOTE_KEYS["net"])
        if has_nci:
            S.node("nci", nc, "nci", "profit", "Minority interests", "below_right" if bridge else "right", "pretax", "pre-tax")
        if Nc["tax"] > 0:
            S.node("tax", nc, "tax", "cost", "Income tax", "below_right" if bridge else "right", "pretax", "pre-tax",
                   notekeys=NOTE_KEYS["tax"])
        if Nc["tax"] > 0:
            S.link("pretax", "net", net_key, "profit")
        else:
            S.link("pretax", "net", "pretax_less_nci" if has_nci else "pretax", "profit")
        if Nc["tax"] < 0:
            S.link("taxben", "net", "taxben", "profit")
        if has_nci:
            S.link("pretax", "nci", "nci", "profit")
        if Nc["tax"] > 0:
            S.link("pretax", "tax", "tax", "cost")
        if bridge:
            _bridge(S, Nc, nc, "net", net_key, has_nci, f)
        kind = "profit"
    else:
        rc = col
        if not nonop_small and Nc["nonop"] > 0:
            S.node("nonop_in", rc, "nonop", "profit", "Other income, net", "left", "total", "costs",
                   notekeys=NOTE_KEYS["nonop"])
        if Nc["tax"] < 0:
            S.node("taxben", rc, "taxben", "profit", "Income tax benefit", "left", "total", "costs", notekeys=NOTE_KEYS["tax"])
        if Nc["pl"] < 0:
            S.node("netloss", rc, "netloss", "cost", "Net loss", "left", "total", "costs",
                   extra=["Y/Y, Q/Q compare the size of the loss"], notekeys=NOTE_KEYS["net"])
        S.node("total", rc + 1, "funding", "cost", "Costs &amp; expenses", "above", "revenue", "revenue")
        S.link("revenue", "total", "revenue", "rev")
        if "nonop_in" in S.ids:
            S.link("nonop_in", "total", "nonop", "profit")
        if "taxben" in S.ids:
            S.link("taxben", "total", "taxben", "profit")
        if "netloss" in S.ids:
            S.link("netloss", "total", "netloss", "cost")
        oploss = Nc["oi"] < 0
        extra = [f"exceed revenue by {f.money(-Nc['oi'])} (operating loss)"] if oploss else \
                [f"leave {f.money(Nc['oi'])} operating profit"]
        S.node("opcosts", rc + 2, "opcosts", "cost", "Operating costs", "above",
               "total", "costs", extra=extra, notekeys=NOTE_KEYS["costs"])
        S.link("total", "opcosts", "opcosts", "cost")
        if not nonop_small and Nc["nonop"] < 0:
            S.node("nonop_out", rc + 2, "nonop", "cost", "Interest &amp; other, net", "right", "total", "costs",
                   sign=-1, notekeys=NOTE_KEYS["nonop"])
            S.link("total", "nonop_out", "nonop", "cost", sign=-1)
        if Nc["tax"] > 0:
            S.node("tax", rc + 2, "tax", "cost", "Income tax", "right", "total", "costs", notekeys=NOTE_KEYS["tax"])
            S.link("total", "tax", "tax", "cost")
        if Nc["pl"] > 0:
            S.node("netinc", rc + 2, "pl", "profit", "Net earnings", "right", "total", "costs", notekeys=NOTE_KEYS["net"])
            S.link("total", "netinc", "pl", "profit")
        parts = []
        if Nc["gp_path"]:
            parts.append(("cor", "cor"))
            parts += [(k, "item:" + k) for k, _ in Nc["items"]] or [("opex", "opex")]
        else:
            parts = [(k, "item:" + k) for k, _ in Nc["items"]]
        for k, key in parts:
            label = "Operating expenses" if k == "opex" else ITEM_LABELS[k]
            S.node("I:" + k, rc + 3, key, "cost", label, "right", "opcosts", "operating costs",
                   notekeys=NOTE_KEYS.get(k, []))
            S.link("opcosts", "I:" + k, key, "cost")
        if not parts:
            S.ids["opcosts"]["pos"] = "right"
        if Nc["ocf"] is not None:
            _bridge_general(S, Nc, rc + 4, f)
        kind = "loss"
    nodes, links = S.finish()
    _check(nodes, links)
    return nodes, links, kind


def _bridge(S, Nc, nc, net_id, net_key, has_nci, f):
    """Operating-cash-flow bridge attached to the Net earnings node (profitable case)."""
    rkey = "r_nci" if has_nci else "r"
    rx = S.Qc[rkey]
    nib = S.Qc[net_key]
    if nib > 0 and Nc["ocf"] > 0 and nib + min(rx, 0) >= 0:
        ac, oc = nc + 1, nc + 2
        if Nc["da"] > 0:
            S.node("da", ac, "da", "profit", "Depreciation &amp; amortization", "left", "ocf", "OCF", notekeys=NOTE_KEYS["da"])
        if Nc["sbc"] > 0:
            S.node("sbc", ac, "sbc", "profit", "Share-based compensation", "left", "ocf", "OCF", notekeys=NOTE_KEYS["sbc"])
        note = ["incl. minority interests"] if has_nci else []
        if rx > 0:
            S.node("wc_in", ac, rkey, "profit", "Working capital &amp; other", "left", "ocf", "OCF", extra=note,
                   notekeys=NOTE_KEYS["wc"])
        else:
            S.node("wc_out", oc, rkey, "noncash", "Working capital &amp; other", "right", "net", "net earnings",
                   sign=-1, extra=["non-cash or timing, removed"] + note, notekeys=NOTE_KEYS["wc"])
        conv = round(Nc["ocf"] / nib * 100) if nib else None
        capex = f"capex {f.money(Nc['capex'])} · FCF {f.money(Nc['ocf'] - Nc['capex'])}" if Nc.get("capex") else None
        S.node("ocf", oc, "ocf", "profit", "Operating cash flow", "right", "revenue", "revenue", style="ocf",
               extra=[x for x in (f"{conv}% of net earnings" if conv is not None else None, capex) if x],
               notekeys=NOTE_KEYS["ocf"])
        S.Qc["_net_to_ocf"] = nib + min(rx, 0)
        if S.Qq.get(net_key) is not None and S.Qq.get(rkey) is not None:
            S.Qq["_net_to_ocf"] = S.Qq[net_key] + min(S.Qq[rkey], 0)
        if rx < 0:
            S.link(net_id, "wc_out", rkey, "noncash", sign=-1)
        S.link(net_id, "ocf", "_net_to_ocf", "profit")
        for k in ("da", "sbc"):
            if k in S.ids:
                S.link(k, "ocf", k, "profit")
        if rx > 0:
            S.link("wc_in", "ocf", rkey, "profit")
    else:
        _bridge_general(S, Nc, nc + 1, f, net_id=net_id, net_key=net_key, rkey=rkey)


def _bridge_general(S, Nc, c0, f, net_id=None, net_key=None, rkey="r"):
    """Sources -> 'Operating cash sources' -> uses, for losses, negative OCF or heavy working-capital drains."""
    rx = S.Qc[rkey]
    srcs, uses = [], []
    if net_id and S.Qc[net_key] > 0:
        srcs.append((net_id, net_key, 1, None, "net"))
    if Nc["da"] > 0:
        srcs.append(("da", "da", 1, "Depreciation &amp; amortization", "da"))
    if Nc["sbc"] > 0:
        srcs.append(("sbc", "sbc", 1, "Share-based compensation", "sbc"))
    if rx > 0:
        srcs.append(("wc_in", rkey, 1, "Working capital &amp; other", "wc"))
    if Nc["ocf"] < 0:
        srcs.append(("burn", "ocf", -1, "Cash used in operations", "ocf"))
    if Nc["pl"] < 0:
        uses.append(("loss_abs", "netloss", 1, "Net loss absorbed", "cost", "net"))
    if rx < 0:
        uses.append(("wc_out", rkey, -1, "Working capital &amp; other", "noncash", "wc"))
    if Nc["ocf"] >= 0:
        uses.append(("ocf", "ocf", 1, "Operating cash flow", "profit", "ocf"))

    def total(Q):
        try:
            return sum(sg * Q[k] for _, k, sg, _, _ in srcs)
        except (KeyError, TypeError):
            return None
    S.Qc["bridge_total"] = total(S.Qc)
    if S.Qq:
        S.Qq["bridge_total"] = total(S.Qq)
    if S.Qy:
        S.Qy["bridge_total"] = total(S.Qy)
    S.node("bridge", c0 + 1, "bridge_total", "profit", "Operating cash sources", "above", "revenue", "revenue")
    for nid, key, sign, name, nk in srcs:
        if nid != net_id:
            S.node(nid, c0, key, "cost" if nid == "burn" else "profit", name, "left", "bridge", "sources", sign=sign,
                   notekeys=NOTE_KEYS[nk])
        S.link(nid, "bridge", key, "cost" if nid == "burn" else "profit", sign=sign)
    for nid, key, sign, name, color, nk in uses:
        extra = []
        if nid == "ocf":
            extra = [f"{share(S.Qc['ocf'], S.Qc['bridge_total'])} of cash sources"]
            if Nc.get("capex"):
                extra.append(f"capex {f.money(Nc['capex'])} \u00b7 FCF {f.money(Nc['ocf'] - Nc['capex'])}")
        if nid == "loss_abs":
            extra = ["same loss as in the income statement"]
        if nid == "wc_out":
            extra = ["timing items, removed"]
        S.node(nid, c0 + 2, key, color, name, "right", "revenue" if nid == "ocf" else "bridge",
               "revenue" if nid == "ocf" else "sources", sign=sign, style="ocf" if nid == "ocf" else "name",
               extra=extra, notekeys=NOTE_KEYS[nk])
        S.link("bridge", nid, key, color, sign=sign)


def _check(nodes, links):
    """Every node's inflows and outflows must match its value (Sankey conservation)."""
    ins, outs = {}, {}
    for l in links:
        outs[l["s"]] = outs.get(l["s"], 0) + l["v"]
        ins[l["t"]] = ins.get(l["t"], 0) + l["v"]
    for n in nodes:
        v = n["v"]
        for side in (ins, outs):
            if n["id"] in side:
                tol = max(abs(v) * 0.004, 1.0)
                if abs(side[n["id"]] - v) > tol and n["id"] not in ("oi", "pretax"):
                    raise ValueError(f"flow mismatch at {n['id']}: {side[n['id']]} vs {v}")


NOTE_KEYS = {
    "gp": ["gross margin", "gross profit"],
    "cor": ["cost of sales", "cost of revenue", "cost of revenues", "cost of goods sold"],
    "oi": ["operating income", "income from operations", "operating margin"],
    "opex": ["operating expenses"],
    "costs": ["costs and expenses", "operating expenses"],
    "rd": ["research and development", "technology and development"],
    "sm": ["sales and marketing", "selling and marketing", "marketing and sales"],
    "ga": ["general and administrative"],
    "sga": ["selling, general and administrative"],
    "other_opex": ["other operating"],
    "nonop": ["other income", "interest expense", "interest and other", "other (income) expense", "nonoperating"],
    "pretax": ["income before"],
    "tax": ["provision for income taxes", "income taxes", "effective tax rate"],
    "net": ["net income", "net loss"],
    "ocf": ["cash flows from operating activities", "operating activities", "cash generated by operating"],
    "da": ["depreciation and amortization", "depreciation"],
    "sbc": ["share-based compensation", "stock-based compensation"],
    "wc": ["working capital", "deferred revenue", "accounts receivable"],
}
