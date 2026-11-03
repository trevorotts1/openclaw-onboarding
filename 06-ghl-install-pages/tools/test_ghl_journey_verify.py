"""Journey verifier + test-order gate (S06-14). Fake browser only; no network."""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghl_journey_verify as jv  # noqa: E402

ROLES = ["landing", "product_selection", "checkout", "upsell_1", "downsell_1", "thank_you"]
URLS = {r: f"https://f.example.com/{r}" for r in ROLES}
EDGES = [
    ("landing", "interest_submitted", "product_selection"),
    ("product_selection", "selection_validated", "checkout"),
    ("checkout", "payment_succeeded", "upsell_1"),
    ("upsell_1", "payment_succeeded", "thank_you"),
    ("upsell_1", "explicit_decline", "downsell_1"),
    ("downsell_1", "explicit_decline", "thank_you"),
]
GRAPH = {"nodes": [{"page_id": r, "role": r} for r in ROLES],
         "edges": [{"from": a, "event": e, "to": b, "guard": "g"} for a, e, b in EDGES]}


class FakeBrowser:
    """Published funnel: the page behind `from` + `event` lands on `site[(from, event)]`."""

    def __init__(self, site):
        self.site, self.clicked = site, []

    def click_edge(self, source_url, edge):
        self.clicked.append((source_url, edge["event"]))
        return self.site[(edge["from"], edge["event"])]


def good_site():
    return {(a, e): (URLS[b] + "/?utm=x", 200) for a, e, b in EDGES}


def test_every_edge_clicked_and_passes():
    br = FakeBrowser(good_site())
    rep = jv.verify_journey(GRAPH, URLS, br)
    assert rep["ok"] and rep["edges_checked"] == len(EDGES) == len(br.clicked)


def test_changed_edge_target_fails():
    # S06-14 proof: one route edge target changed in the fixture; the published
    # funnel still lands on checkout, so the verifier must fail that edge only.
    bad = copy.deepcopy(GRAPH)
    bad["edges"][1]["to"] = "upsell_1"
    rep = jv.verify_journey(bad, URLS, FakeBrowser(good_site()))
    assert not rep["ok"]
    assert [r["reason"] for r in rep["results"] if not r["ok"]] == ["wrong target URL"]


def test_selection_button_linking_wrong_step_fails():
    site = good_site()
    site[("product_selection", "selection_validated")] = (URLS["thank_you"], 200)
    assert not jv.verify_journey(GRAPH, URLS, FakeBrowser(site))["ok"]


def test_no_thanks_404_fails():
    site = good_site()
    site[("upsell_1", "explicit_decline")] = (URLS["downsell_1"], 404)
    rep = jv.verify_journey(GRAPH, URLS, FakeBrowser(site))
    assert not rep["ok"] and "404" in [r["reason"] for r in rep["results"] if not r["ok"]][0]


def test_fail_closed_cases():
    assert not jv.verify_journey({"edges": []}, URLS, FakeBrowser({}))["ok"]
    assert not jv.verify_journey(GRAPH, {k: v for k, v in URLS.items() if k != "checkout"},
                                 FakeBrowser(good_site()))["ok"]
    assert not jv.verify_journey(GRAPH, URLS, FakeBrowser({}))["ok"]  # browser raises KeyError


# ---- test-mode order gate ----
def _order(calls):
    def place(loc):
        calls.append(loc)
        return {"livemode": False, "id": "test_1"}
    return place


def test_order_runs_only_on_approved_test_location_with_verified_ref():
    calls = []
    ok = lambda ref, loc: ref == "APPR-1" and loc == "LOC-T"  # noqa: E731
    out = jv.run_test_order("LOC-T", "APPR-1", approved_test_locations={"LOC-T"},
                            verify_approval=ok, place_order=_order(calls))
    assert out["id"] == "test_1" and calls == ["LOC-T"]


@pytest.mark.parametrize("loc,ref,locs,verifier", [
    ("LOC-CLIENT", "APPR-1", {"LOC-T"}, lambda r, l: True),   # unmarked location
    ("LOC-T", "APPR-1", {"LOC-T"}, lambda r, l: False),       # ref does not verify
    ("LOC-T", "", {"LOC-T"}, lambda r, l: True),              # no ref
    ("LOC-T", "APPR-1", {"LOC-T"}, None),                     # no verifier -> closed
    ("", "APPR-1", {""}, lambda r, l: True),                  # empty location id
])
def test_order_refused_without_mark_or_approval(loc, ref, locs, verifier):
    calls = []
    with pytest.raises(jv.TestOrderRefused):
        jv.run_test_order(loc, ref, approved_test_locations=locs,
                          verify_approval=verifier, place_order=_order(calls))
    assert calls == []  # provider never reached


def test_live_mode_result_refused():
    with pytest.raises(jv.TestOrderRefused):
        jv.run_test_order("LOC-T", "A", approved_test_locations={"LOC-T"},
                          verify_approval=lambda r, l: True,
                          place_order=lambda loc: {"livemode": True})


def test_marker_file_missing_is_empty(tmp_path):
    assert jv.load_approved_test_locations(str(tmp_path / "nope.json")) == frozenset()
    p = tmp_path / "m.json"
    p.write_text('{"approved_test_locations": ["LOC-T"]}')
    assert jv.load_approved_test_locations(str(p)) == {"LOC-T"}
