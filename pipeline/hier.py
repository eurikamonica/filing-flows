"""One growth model at four levels — company, sub-industry (SIC), sector, trading concept (a chain's layer or a whole
chain) — each level learning from the one above it (data/model/, the "Forecast" boxes on the site).

Every entity has a quarterly revenue series in dollars by calendar quarter: a company's own; a group's is the sum of
its members' (an industry, a sector, the whole market, a chain layer, a chain). A group's growth is measured on the
same companies — the sum this quarter over the sum of the same companies a year earlier — so a newly covered company
does not look like growth.

The model for an entity e with parent p (company -> its SIC industry -> its sector -> the market; a chain layer and a
chain -> the market):

    g_e,t = a + ρ·g_e,t−1 + γ·g_p,t + ε          g = revenue this quarter ÷ the same quarter a year earlier − 1

ρ is how persistent the entity's own growth is, γ how much of its parent's growth it carries (its beta to the group).
Bayesian regression (pipeline/chainmodel.fit) with an empirical-Bayes prior: the siblings of e (the other members of
its parent) are fitted together first, and that pooled estimate, with the siblings' spread, is the prior for e — so a
company with three quarters on file is mostly its industry, one with thirty is mostly itself. Each posterior comes
with how much of it the entity's own data decided ("data weight"), and the fit is tested out of sample on a rolling
origin, one quarter ahead, against the naive forecast (growth stays what it was) — once given the parent's actual
growth, once with the parent forecast too.

Forecasts run top-down: the market's growth (an AR(1)) -> each sector -> each industry -> each company, four quarters
ahead, revenue = the year-ago quarter × (1 + g); 80% intervals from the posterior predictive. A concept (chain layer,
chain) is forecast both as a basket (its own model against the market) and bottom-up (the sum of its members'
forecasts); both are published.
"""
import datetime as dt
import json
import math
import os

from . import chainmodel as CM

VERSION = 1
MIN_Q = 8                       # quarters of growth an entity needs for its own fit (fewer: the prior alone)
MIN_MEMBERS = 3                 # members a group needs
HORIZON = 4
BT_N = 6                        # rolling-origin backtests per entity
Z80 = CM.Z80
CLIP = 3.0                      # growth rates beyond ±300% are left out (reverse mergers, tiny bases)


# ------------------------------------------------------------------ series

def yoy(y):
    """{k: revenue} -> {k: growth vs the quarter a year earlier}, both positive, within CLIP."""
    out = {}
    for k, v in y.items():
        b = y.get(k - 4)
        if v is not None and b and b > 0 and v > 0:
            g = v / b - 1
            if abs(g) <= CLIP:
                out[k] = g
    return out


def group_series(members):
    """Same-company growth of a group: {k: (growth, n, dollars this quarter)} from its members' {k: revenue}."""
    ks = sorted({k for y in members for k in y})
    out = {}
    for k in ks:
        now = tot = 0.0
        n = 0
        for y in members:
            v, b = y.get(k), y.get(k - 4)
            if v is not None and v > 0:
                tot += v
            if v is not None and b and b > 0 and v > 0 and abs(v / b - 1) <= CLIP:
                now += v
                n += 1
                out.setdefault(k, [0.0, 0.0, 0, 0.0])
                out[k][0] += v
                out[k][1] += b
        if k in out:
            out[k] = (out[k][0] / out[k][1] - 1, n, tot)
    return out


# ------------------------------------------------------------------ the model

def _rows(g, P, ks):
    return [[1.0, g[k - 1], P[k]] for k in ks]


def _usable(g, P):
    return sorted(k for k in g if (k - 1) in g and P.get(k) is not None)


STRUCT = ([0.0, 0.7, 0.5], [0.03, 0.1, 0.3])
"""The structural prior every entity starts from: no growth of its own beyond its parent's (a ≈ 0), growth that
persists (ρ ≈ 0.7: a year-on-year rate carries most of itself into the next quarter), half its parent's move (γ).
Chosen on a 900-company sample by rolling backtest: a loose prior, or one pooled from the siblings' least-squares
fits (which tiny samples make wild), forecast worse than "growth stays what it was"; this one beats it."""


def pooled(gs, P):
    """The siblings' beta to the parent: the median of their own fitted γ under the structural prior, clipped to
    [0, 1.5], as the centre of each sibling's γ prior; None with fewer than MIN_MEMBERS siblings on file."""
    vals = []
    for g in gs:
        ks = _usable(g, P)
        if len(ks) < MIN_Q:
            continue
        try:
            mu, _, _ = CM.fit(_rows(g, P, ks), [g[k] for k in ks], STRUCT[0], [STRUCT[1][0], STRUCT[1][1], 0.6])
        except ZeroDivisionError:
            continue
        if math.isfinite(mu[2]):
            vals.append(mu[2])
    if len(vals) < MIN_MEMBERS:
        return None
    vals.sort()
    med = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
    return [STRUCT[0][0], STRUCT[0][1], max(0.0, min(1.5, med))], list(STRUCT[1])


DEFAULT_PRIOR = STRUCT


def entity_model(g, P, prior, backtest=True):
    """Fit one entity: {"mu", "cov", "s2", "n", "dataw", "bt", "prior"} (the prior alone when too few quarters)."""
    m0, sd0 = prior
    ks = _usable(g, P)
    out = {"n": len(ks), "prior": [round(v, 4) for v in m0], "prior_sd": [round(v, 4) for v in sd0]}
    if len(ks) < MIN_Q:
        out.update(mu=list(m0), cov=[[sd0[i] ** 2 if i == j else 0.0 for j in range(3)] for i in range(3)],
                   s2=max(sd0[0] ** 2, 0.01), dataw=0.0, own=False)
        return out
    try:
        mu, cov, s2 = CM.fit(_rows(g, P, ks), [g[k] for k in ks], m0, sd0)
    except ZeroDivisionError:
        return None
    out.update(mu=mu, cov=cov, s2=s2, own=True,
               dataw=round(max(0.0, min(1.0, 1 - cov[2][2] / (sd0[2] ** 2))), 3), first=CM.qlabel(ks[0]), last=CM.qlabel(ks[-1]))
    if backtest and len(ks) >= MIN_Q + 2:
        out["bt"] = _backtest(g, P, ks, m0, sd0)
    return out


def _backtest(g, P, ks, m0, sd0):
    """Rolling origin, one quarter ahead: the model given the parent's actual growth (cond), with the parent's growth
    taken as unchanged (uncond), the naive forecast (growth unchanged), and the prior alone — errors in growth points
    and in revenue terms (|forecast/actual − 1| where revenue = year-ago × (1+g))."""
    e_c, e_u, e_n, e_p, cover = [], [], [], [], []
    origins = list(range(MIN_Q - 1, len(ks) - 1))[-BT_N:]
    for i in origins:
        train, k1 = ks[:i + 1], ks[i + 1]
        if k1 != ks[i] + 1:
            continue
        try:
            mu, cov, s2 = CM.fit(_rows(g, P, train), [g[k] for k in train], m0, sd0)
        except ZeroDivisionError:
            continue
        actual = g[k1]
        x = [1.0, g[ks[i]], P[k1]]
        pred = sum(a * b for a, b in zip(x, mu))
        sd = (CM.quad(x, cov) + s2) ** 0.5
        xu = [1.0, g[ks[i]], P.get(ks[i], P[k1])]
        pred_u = sum(a * b for a, b in zip(xu, mu))
        pred_p = sum(a * b for a, b in zip(x, m0))
        rev = lambda gg: min(abs((1 + gg) / (1 + actual) - 1), 2.0)   # error in revenue terms, capped at 200%
        e_c.append(rev(pred))
        e_u.append(rev(pred_u))
        e_n.append(rev(g[ks[i]]))
        e_p.append(rev(pred_p))
        cover.append(abs(actual - pred) <= Z80 * sd)
    if not e_c:
        return None
    m = lambda a: round(sum(a) / len(a), 4)
    return {"n": len(e_c), "cond": m(e_c), "uncond": m(e_u), "naive": m(e_n), "prior_only": m(e_p), "cover80": round(sum(cover) / len(cover), 3)}


def predict(model, g_prev, p_next):
    """(mean growth, sd) one quarter ahead."""
    x = [1.0, g_prev, p_next]
    m = sum(a * b for a, b in zip(x, model["mu"]))
    sd = (CM.quad(x, model["cov"]) + model["s2"]) ** 0.5
    return m, sd


def forecast_entity(model, g, y, P_path, last_k):
    """Four quarters ahead from last_k: [[quarter, growth, revenue, lo80, hi80]] (revenue only where the year-ago
    quarter is on file)."""
    out, gp, var = [], g.get(last_k), 0.0
    if gp is None:
        return out
    for h in range(1, HORIZON + 1):
        k = last_k + h
        pn = P_path.get(k)
        if pn is None:
            break
        m, sd = predict(model, gp, pn)
        var = sd ** 2 + (model["mu"][1] ** 2) * var      # the previous quarter's uncertainty carries through ρ
        s = var ** 0.5
        base = y.get(k - 4) if h <= 4 else None
        rev = base * (1 + m) if base else None
        out.append([CM.qlabel(k), round(m, 4), round(rev, 1) if rev else None,
                    round(base * (1 + m - Z80 * s), 1) if base else None, round(base * (1 + m + Z80 * s), 1) if base else None,
                    round(s, 4)])
        gp = m
    return out


# ------------------------------------------------------------------ the levels

class Node:
    def __init__(self, kind, id_, name, parent=None, members=None, extra=None):
        self.kind, self.id, self.name, self.parent = kind, id_, name, parent
        self.members = members or []            # company ciks for a group
        self.y = {}                             # {k: revenue}
        self.g = {}                             # {k: growth}
        self.n = {}                             # {k: companies in the growth}
        self.model = None
        self.fc = []
        self.extra = extra or {}


def market_model(g, ks):
    """The top: an AR(1) on the market's own growth (its 'parent' is its own last value)."""
    P = {k: g[k - 1] for k in ks if (k - 1) in g}
    m0, sd0 = [0.0, 0.6, 0.0], [0.1, 0.3, 0.001]
    kk = [k for k in ks if k in P and (k - 1) in g]
    return entity_model(g, P, (m0, sd0)), P


def build(store, out, index, usd_recs=None, cfg=None, today=None):
    """Write data/model/index.json, data/model/i/<sic>.json, data/model/c/<cik>.json, data/model/x/<chain>.json."""
    from . import chains as CH
    from . import sectors as SEC
    cfg = cfg or CH.load_cfg()
    today = today or dt.date.today()
    k_now = CM.cq(today.isoformat())
    # 1. every company's revenue by calendar quarter (dollars)
    cos, names = {}, {}
    for r in index:
        cik = int(r["cik"])
        rec = store.company(cik)
        if not rec.get("quarters"):
            continue
        co = CH.Co(cik, rec, (usd_recs or {}).get(cik), ticker=r.get("ticker"))
        y = {k: v for k, v in CM.by_quarter(co.history("revenue")).items() if v is not None and v > 0 and k < k_now}
        if len(y) >= 5:
            cos[cik] = y
            names[cik] = {"t": r.get("ticker") or "", "name": r.get("name") or "", "sic": str(r.get("sic") or "").zfill(4),
                          "sector": r.get("sector") or SEC.sector_of(r.get("sic"))}
    # 2. the tree: market -> sectors -> industries -> companies; the market -> chain layers, chains
    market = Node("market", "market", "All companies on the site", members=list(cos))
    sectors, inds = {}, {}
    for cik, meta in names.items():
        s = sectors.setdefault(meta["sector"], Node("sector", meta["sector"], SEC.SECTORS.get(meta["sector"], meta["sector"]), "market"))
        s.members.append(cik)
        i = inds.setdefault(meta["sic"], Node("industry", meta["sic"], _industry_name(index, meta["sic"]), meta["sector"]))
        i.members.append(cik)
    concepts = {}
    tick = {meta["t"]: cik for cik, meta in names.items() if meta["t"]}
    for ch in cfg.get("chains", []):
        all_m = []
        for L in ch.get("layers", []):
            ms = [tick[m["t"].upper()] for m in L.get("members", []) if m["t"].upper() in tick]
            all_m += ms
            if len(ms) >= MIN_MEMBERS:
                concepts[f"{ch['id']}:{L['id']}"] = Node("layer", f"{ch['id']}:{L['id']}", f"{ch['name']} · {L['name']}", "market", ms,
                                                          {"chain": ch["id"], "layer": L["id"], "zh": L.get("zh")})
        all_m = list(dict.fromkeys(all_m))
        if len(all_m) >= MIN_MEMBERS:
            concepts[ch["id"]] = Node("chain", ch["id"], ch["name"], "market", all_m, {"chain": ch["id"], "zh": ch.get("zh")})
    groups = [market] + list(sectors.values()) + list(inds.values()) + list(concepts.values())
    for n in groups:
        gs = group_series([cos[c] for c in n.members])
        n.g = {k: v[0] for k, v in gs.items() if v[1] >= (MIN_MEMBERS if n.kind != "industry" else 2)}
        n.n = {k: v[1] for k, v in gs.items()}
        n.y = {k: v[2] for k, v in gs.items()}
    comp = {cik: Node("company", str(cik), names[cik]["name"], names[cik]["sic"]) for cik in cos}
    for cik, n in comp.items():
        n.y, n.g = cos[cik], yoy(cos[cik])
    # 3. fit top-down, each level's prior from its siblings
    ks_m = sorted(market.g)
    market.model, Pm = market_model(market.g, ks_m)
    last_k = ks_m[-1] if ks_m else None
    if not market.model or last_k is None:
        print("::warning::hier: the market series is too short")
        return None
    # the market's path ahead
    path = {"market": {}}
    gp = market.g[last_k]
    for h in range(1, HORIZON + 1):
        gp, _ = predict(market.model, gp, gp)
        path["market"][last_k + h] = gp
    market.fc = forecast_entity(market.model, market.g, market.y, {**{k: market.g.get(k - 1) for k in ks_m}, **path["market"]}, last_k)

    def fit_level(nodes, parent_of):
        by_parent = {}
        for n in nodes:
            by_parent.setdefault(parent_of(n), []).append(n)
        for pid, sibs in by_parent.items():
            P = _parent_series(pid)
            if P is None:
                continue
            pr = pooled([s.g for s in sibs], P) or DEFAULT_PRIOR
            for s in sibs:
                s.model = entity_model(s.g, P, pr)
                if s.model:
                    s.model["pooled"] = pr is not DEFAULT_PRIOR
                    s.fc = forecast_entity(s.model, s.g, s.y, {**P, **path.get(pid, {})}, min(max(s.g), last_k) if s.g else last_k)
                    path[s.id] = {CM.cq_from_label(q): g for q, g, *_ in s.fc}

    def _parent_series(pid):
        if pid == "market":
            return market.g
        n = sectors.get(pid) or inds.get(pid)
        return n.g if n and n.g else None

    fit_level(list(sectors.values()), lambda n: "market")
    fit_level(list(inds.values()), lambda n: n.parent)
    fit_level(list(concepts.values()), lambda n: "market")
    fit_level(list(comp.values()), lambda n: n.parent)
    # 4. write
    os.makedirs(os.path.join(out, "model", "i"), exist_ok=True)
    os.makedirs(os.path.join(out, "model", "c"), exist_ok=True)
    os.makedirs(os.path.join(out, "model", "x"), exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    def summary(n, with_series=False):
        m = n.model or {}
        d = {"id": n.id, "kind": n.kind, "name": n.name, "parent": n.parent, "members": len(n.members) if n.kind != "company" else None,
             "last": CM.qlabel(max(n.g)) if n.g else None, "g_now": round(n.g[max(n.g)], 4) if n.g else None,
             "n_now": n.n.get(max(n.g)) if n.g and n.n else None,
             "rev_ttm": round(sum(n.y.get(k, 0) for k in range(max(n.y) - 3, max(n.y) + 1))) if n.y else None,
             "fc": n.fc, **n.extra}
        if m:
            d["model"] = {"a": round(m["mu"][0], 4), "rho": round(m["mu"][1], 4), "gamma": round(m["mu"][2], 4),
                          "gamma_sd": round(m["cov"][2][2] ** 0.5, 4), "sd": round(m["s2"] ** 0.5, 4), "n": m["n"], "own": m.get("own", False),
                          "dataw": m.get("dataw"), "pooled": m.get("pooled", False), "prior": m.get("prior"), "bt": m.get("bt")}
        if with_series:
            ks = sorted(n.g)[-24:]
            d["series"] = [[CM.qlabel(k), round(n.g[k], 4), round(n.y.get(k, 0)), n.n.get(k)] for k in ks]
        return d

    def score(nodes):
        """Across the entities of a level: the median of their one-quarter-ahead revenue errors (a mean is a few
        reverse mergers), interval coverage, and how many the model beats the naive forecast for."""
        bts = [n.model["bt"] for n in nodes if n.model and n.model.get("bt")]
        if not bts:
            return None

        def med(key):
            v = sorted(b[key] for b in bts)
            return round(v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2, 4)
        return {"entities": len(bts), "cond": med("cond"), "uncond": med("uncond"), "naive": med("naive"), "prior_only": med("prior_only"),
                "cover80": round(sum(b["cover80"] for b in bts) / len(bts), 4), "beats_naive": sum(1 for b in bts if b["uncond"] < b["naive"]),
                "ties": sum(1 for b in bts if b["uncond"] == b["naive"])}

    doc = {"generated": now, "version": VERSION, "asof": CM.qlabel(last_k), "horizon": HORIZON,
           "market": summary(market, True),
           "sectors": sorted((summary(n, True) for n in sectors.values()), key=lambda d: -(d["rev_ttm"] or 0)),
           "industries": sorted((summary(n) for n in inds.values() if n.model), key=lambda d: -(d["rev_ttm"] or 0)),
           "concepts": sorted((summary(n, True) for n in concepts.values()), key=lambda d: (d["kind"] != "chain", d["id"])),
           "scores": {"sectors": score(sectors.values()), "industries": score(inds.values()), "concepts": score(concepts.values()),
                      "companies": score(comp.values())},
           "companies": len(comp)}
    with open(os.path.join(out, "model", "index.json"), "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    for sic, n in inds.items():
        d = summary(n, True)
        d["companies"] = sorted((summary(comp[c]) | {"cik": c, "t": names[c]["t"]} for c in n.members), key=lambda x: -(x["rev_ttm"] or 0))
        with open(os.path.join(out, "model", "i", f"{sic}.json"), "w") as f:
            json.dump(d, f, separators=(",", ":"))
    for cid, n in concepts.items():
        d = summary(n, True)
        d["companies"] = sorted((summary(comp[c]) | {"cik": c, "t": names[c]["t"]} for c in n.members), key=lambda x: -(x["rev_ttm"] or 0))
        d["bottom_up"] = _bottom_up(d["companies"])
        with open(os.path.join(out, "model", "x", f"{cid.replace(':', '--')}.json"), "w") as f:
            json.dump(d, f, separators=(",", ":"))
    for cik, n in comp.items():
        if not n.model:
            continue
        d = summary(n, True) | {"cik": cik, "t": names[cik]["t"], "industry": inds[n.parent].name,
                                "industry_model": (summary(inds[n.parent]).get("model") or {}),
                                "industry_fc": inds[n.parent].fc, "sector": names[cik]["sector"]}
        with open(os.path.join(out, "model", "c", f"{cik}.json"), "w") as f:
            json.dump(d, f, separators=(",", ":"))
    sc = doc["scores"]["companies"] or {}
    print(f"::notice::hier model: {len(comp)} companies, {len(inds)} industries, {len(sectors)} sectors, {len(concepts)} concepts; "
          f"companies one quarter ahead: model {sc.get('uncond')} vs naive {sc.get('naive')} (revenue error), beats naive {sc.get('beats_naive')} of {sc.get('entities')}")
    return doc


def _bottom_up(rows):
    """The sum of the members' forecasts by quarter, where every member with a year-ago base has one."""
    tot = {}
    for r in rows:
        for q, g, rev, lo, hi, s in r.get("fc") or []:
            if rev is not None:
                t = tot.setdefault(q, [0.0, 0.0, 0.0, 0])
                t[0] += rev
                t[1] += lo
                t[2] += hi
                t[3] += 1
    return [[q, round(v[0]), round(v[1]), round(v[2]), v[3]] for q, v in sorted(tot.items(), key=lambda kv: CM.cq_from_label(kv[0]))]


def _industry_name(index, sic):
    return next((r["industry"] for r in index if str(r.get("sic") or "").zfill(4) == sic and r.get("industry")), f"SIC {sic}")
