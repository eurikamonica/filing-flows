"""Money flow Beta 1.0 (pipeline/ioflow_beta.py): filed figures kept apart from estimates, the US share from a 10-K
sentence, suppliers a filing names, provenance on every band, and the checks that hold a level back."""
import json
import os

from pipeline import ioflow, ioflow_beta

ENDS = ["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]


class Store:
    def __init__(self, recs):
        self.recs = recs

    def company(self, cik):
        return self.recs.get(int(cik), {"quarters": {}})


def _rec(name, ticker, sic, rev, oi, da, capex, ocf, cn=None, segs=None):
    qs = {}
    for e in ENDS:
        qs[e] = {"end": e, "form": "10-Q", "filed": e, "doc_url": "https://www.sec.gov/x.htm",
                 "raw": {"revenue": rev / 4, "oi": oi / 4, "da": da / 4, "capex": capex / 4, "ocf": ocf / 4}}
    if segs:
        qs[ENDS[-1]]["lines_struct"] = {"axis": "StatementBusinessSegmentsAxis",
                                        "leaves": [{"id": k, "label": k} for k in segs]}
        qs[ENDS[-1]]["lines"] = segs
    return {"quarters": qs, "profile": {"name": name, "tickers": [ticker], "sic": sic}, **({"cn": cn} if cn else {})}


def _setup(tmp_path):
    recs = {
        29905: _rec("Dover", "DOV", "3530", 8_576_562_000, 1_462_186_000, 391_518_000, 219_994_000, 1_409_877_000,
                    cn={"v": 3, "url": "https://www.sec.gov/dov-10k.htm", "form": "10-K", "filed": "2026-02-13",
                        "s": [{"t": "Approximately 46% of our revenues for both 2025 and 2024 were derived outside the United States.", "k": "sell"}]},
                    segs={"Pumps & Process Solutions": 2e9, "Engineered Products": 1e9}),
        73309: _rec("Nucor", "NUE", "3312", 30e9, 3e9, 1.4e9, 3e9, 4e9),
    }
    index = [{"cik": c, "sic": r["profile"]["sic"], "ticker": r["profile"]["tickers"][0], "name": r["profile"]["name"],
              "end": ENDS[-1], "currency": "USD", "industry": "Industry " + r["profile"]["sic"]} for c, r in recs.items()]
    out = str(tmp_path)
    os.makedirs(os.path.join(out, "network", "c"))
    with open(os.path.join(out, "network", "c", "29905.json"), "w") as f:
        json.dump({"suppliers": [{"cik": 73309, "t": "NUE", "name": "Nucor", "usd": 40e6, "q": "Sales to Dover were $40 million.",
                                  "url": "https://www.sec.gov/nue.htm", "form": "10-K", "fy": "2025-12-31", "by": "other"}]}, f)
    return Store(recs), out, index


def test_layers_geo_stated_and_checks(tmp_path):
    store, out, index = _setup(tmp_path)
    assert ioflow_beta.build(store, out, index) >= 2
    d = json.load(open(os.path.join(out, "gamma", "io-beta", "3530.json")))
    F = d["filed"]
    assert F["revenue"] == 8_576_562_000 and F["capex"] == 219_994_000
    assert F["ocf"] == 1_409_877_000 and F["fcf"] == 1_409_877_000 - 219_994_000
    assert F["ebitda_capex"] == 1_462_186_000 + 391_518_000 - 219_994_000
    m = d["members"][0]
    assert m["us"] == 0.54 and "outside the United States" in m["geo"]["text"]
    labels = {n["id"]: n for n in d["nodes"]}
    assert labels["k:left"]["label"] == "EBITDA − capital spending" and labels["k:capex"]["grade"] == "A"
    cost = 8_576_562_000 - 1_462_186_000 - 391_518_000
    assert abs(d["estimate"]["outside"]["v"] - cost * 0.46) < 2
    # every band has provenance with a grade; modelled suppliers say so
    for s, t, v in d["links"]:
        p = d["prov"][s + "|" + t]
        assert p["grade"] in "ABCD" and p.get("formula")
        if t.startswith("s:"):
            assert p["grade"] == "D" and p["note"].startswith("Modelled allocation")
    st = [l for l in d["links"] if l[1] == "x:73309"]
    assert st and st[0][2] == 40_000_000 and d["prov"][st[0][0] + "|x:73309"]["grade"] == "B"
    p = d["prov"]["m:29905|k:purchases"]
    assert p["lo"] <= p["v"] <= p["hi"] and "54% US share" in p["formula"]
    # Dover is not its own supplier
    assert not any(l[1] == "s:29905" for l in d["links"])
    assert d["checks"] and json.load(open(os.path.join(out, "gamma", "io-beta", "index.json")))["failed"] == []


def test_segments_matched_by_name(tmp_path):
    store, out, index = _setup(tmp_path)
    io = ioflow.load()
    seg = ioflow_beta.segment_mix(io, store.company(29905), ioflow.bea_mix(io, "3530"))
    assert seg and any("pump" in (s["bea_name"] or "").lower() for s in seg["segments"])


def test_unbalanced_level_is_held_back(tmp_path):
    store, out, index = _setup(tmp_path)
    io = ioflow.load()
    R = ioflow_beta.Ranges(io)
    fl = ioflow_beta.company(io, R, __import__("pipeline.chains", fromlist=["Co"]).Co(29905, store.company(29905)),
                             store.company(29905), "3530", ENDS[-1], out)
    m = {"cik": 29905, "ticker": "DOV", "name": "Dover", "sic": "3530", "sector": "industrials", "industry": "x"}
    doc, links, nodes = ioflow_beta.doc_for("3530", "t", "industry", [(m, fl)], {}, io)
    assert ioflow_beta.check(doc, links, nodes) == []
    links[0][2] *= 1.5                                       # a band that no longer adds up
    assert ioflow_beta.check(doc, links, nodes)


def test_us_share_sentences():
    f = lambda t: (ioflow_beta.us_share({"cn": {"s": [{"t": t}]}}) or {}).get("us")
    assert f("International sales accounted for approximately 38% of net sales in 2025.") == 0.62
    assert f("Approximately 70% of our revenue was generated in the United States.") == 0.7
    assert f("No customer accounted for more than 10% of revenue.") is None
