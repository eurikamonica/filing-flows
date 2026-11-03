"""Revenue-line names from a filing's label file (dims.parse_labels) and the one-time re-read of stored names."""

from pipeline import build, dims

ROLE = "http://www.xbrl.org/2003/role/"


def _linkbase(items):
    """items: (element id, [(role, text), …]) — each label a resource with its own arc, as filers write them."""
    body, k = [], 0
    for elid, labels in items:
        body.append(f'<link:loc xlink:label="loc{k}" xlink:href="x.xsd#{elid}"/>')
        for j, (role, text) in enumerate(labels):
            body.append(f'<link:label xlink:label="lab{k}_{j}" xlink:role="{ROLE}{role}">{text}</link:label>')
            body.append(f'<link:labelArc xlink:from="loc{k}" xlink:to="lab{k}_{j}"/>')
        k += 1
    return ('<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<link:labelLink>' + "".join(body) + '</link:labelLink></link:linkbase>')


LB = _linkbase([
    ("wday_ProfessionalServicesMember", [("terseLabel", "Costs of professional services"), ("label", "Professional Services [Member]")]),
    ("dal_PassengerAirTrafficMember", [("terseLabel", "Air traffic liability"), ("label", "Passenger Air Traffic [Member]"),
                                       ("verboseLabel", "Ticket")]),
    ("hgv_CostReimbursementsMember", [("terseLabel", "Cost reimbursements"), ("label", "Cost Reimbursements [Member]")]),
    ("nn_CommercialServicesMember", [("documentation", "This member stands for commercial services.")]),
    ("srts_ServiceMember", [("label", "The element represents service revenue member."), ("terseLabel", "Service")]),
    ("kd_JapanMember", [("label", "Japan.")]),
    ("w_UsMember", [("terseLabel", "U.S.")]),
    ("aapl_IPhoneMember", [("terseLabel", "iPhone"), ("label", "iPhone [Member]")]),
])


def test_a_revenue_member_is_not_named_after_a_cost_table():
    L = dims.parse_labels(LB)
    assert L["wday_ProfessionalServicesMember"] == "Professional Services"     # not the cost table's terse label
    assert L["dal_PassengerAirTrafficMember"] == "Passenger Air Traffic"
    assert L["hgv_CostReimbursementsMember"] == "Cost reimbursements"          # every label names a cost: unchanged
    assert L["aapl_IPhoneMember"] == "iPhone"                                  # terse first, as before


def test_no_documentation_sentences_or_xbrl_furniture():
    L = dims.parse_labels(LB)
    assert "nn_CommercialServicesMember" not in L                              # → dims.humanize: "Commercial Services"
    assert dims.humanize("nn:CommercialServicesMember") == "Commercial Services"
    assert L["srts_ServiceMember"] == "Service"
    assert L["kd_JapanMember"] == "Japan" and L["w_UsMember"] == "U.S."


def _company(label, notes=None):
    ls = {"axis": "ProductOrServiceAxis", "groups": [],
          "leaves": [{"id": "wday:SubscriptionServicesMember", "label": "Subscription services"},
                     {"id": "wday:ProfessionalServicesMember", "label": label}]}
    q = {"end": "2026-07-31", "form": "10-Q", "accn": "0001327811-26-000050", "lines_struct": ls, "notes": notes or {}}
    return {"profile": {"name": "Workday"}, "quarters": {"2026-07-31": q}}


def test_stored_names_are_read_again_once(tmp_path, monkeypatch):
    store = build.Store(str(tmp_path))
    store.put(1327811, _company("Costs of professional services", {"Costs of professional services": [{"text": "a note"}]}))
    store.put(320193, dict(_company("Professional services"), profile={"name": "Clean"}))
    asked = []
    monkeypatch.setattr(build.dims, "find_files", lambda cik, accn: (asked.append(cik) or ("inst", "lab")))
    monkeypatch.setattr(build.sec, "get", lambda url: LB)
    monkeypatch.setattr(build, "time_up", lambda *a, **k: False)
    build.refresh_labels(store)
    c = store.company(1327811)
    leaf = c["quarters"]["2026-07-31"]["lines_struct"]["leaves"][1]
    assert leaf["label"] == "Professional Services" and c["lab_v"] == build.LABEL_VERSION
    assert c["quarters"]["2026-07-31"]["notes"] == {"Professional Services": [{"text": "a note"}]}
    assert asked == [1327811]                                   # a company whose names look right is not fetched
    assert store.state["labels_v"] == build.LABEL_VERSION       # done: the pass no longer runs
    build.refresh_labels(store)
    assert asked == [1327811]
