"""downsell_extension tests (DTY-05, DTY-06, DTY-07, DTY-13).

Every run below stages only copy, journey and enrichment (plus the record,
graph and request dispatch already holds); the extension and the trial
disclosure are derived, never staged. All values are test-only.
"""
import copy
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent
SKILL81 = SCRIPTS.parents[1] / "81-signature-downsell"
sys.path.insert(0, str(SCRIPTS))
import downsell_extension as dx  # noqa: E402
import downsell_wrapper as dw  # noqa: E402  (its stdlib schema check)
import test_downsell_wrapper as tw  # noqa: E402  (its staging helpers)

_spec = importlib.util.spec_from_file_location(
    "validate_downsell", SKILL81 / "validators" / "validate_downsell.py")
vd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vd)
EXT_SCHEMA = json.loads(
    (SKILL81 / "schemas" / "downsell-result-extension.schema.json").read_text())

SIDECAR = {"difference_kind": "reduced_scope",
           "rationale": "TEST ONLY recorded rationale.",
           "entry_guard_ref": "TEST-ENTRY-GUARD"}


def trial_launch(graph_hash=None):
    """D1 is the fixture page's own offer: $1 trial, then $27 monthly."""
    launch = tw._launch(graph_hash or GRAPH_HASH)
    d1 = [o for o in launch["offers"] if o["slot"] == "downsell_1"][0]
    d1["prices"] = [{"amount_minor": 100, "billing_type": "trial",
                     "currency": "USD", "approval_status": "approved",
                     "native_price_id": "TEST-D1-PRICE",
                     "schedule": [{"amount_minor": 2700, "due": "day 31"}]}]
    return launch


def one_time_launch():
    launch = tw._launch(GRAPH_HASH)  # D1 is a $37 one-time price
    return launch


def page(trial=True, **edits):
    """The valid trial page, or a $37 one-time version of it."""
    text = json.dumps(tw.PAGE_FIXTURE)
    if not trial:
        text = text.replace(
            " After the trial, $27 per month continues the membership "
            "unless you cancel. The first renewal charge is on day 31, and "
            "renewals are monthly after that. You can cancel anytime before "
            "a renewal charge to stop future charges. If you cancel, your "
            "access continues until the end of the trial or the current "
            "paid month, then your membership access ends and you will not "
            "be charged again.", "").replace("$1", "$37")
    doc = json.loads(text)
    for path, value in edits.items():
        doc["page"]["sections"][int(path)]["body"] = value
    return doc


def graph():
    return json.loads(tw._graph_bytes())


GRAPH_HASH = hashlib.sha256(tw._graph_bytes()).hexdigest()
REQUEST = tw._request(GRAPH_HASH)


def derive(copy_doc=None, launch=None, sidecar=None, staged=None):
    return dx.derive(REQUEST, launch or trial_launch(), graph(),
                     copy_doc or page(), sidecar or SIDECAR, staged)


def problems(**kw):
    with pytest.raises(dx.ExtensionError) as exc:
        derive(**kw)
    return " | ".join(exc.value.problems)


def test_derived_extension_has_every_attested_field_and_validates():
    ext, disclosure = derive()
    assert [c["action_ref"] for c in ext["cta_map"]] == ["native-d1-action"] * 8
    assert [c["section"] for c in ext["cta_map"]] == list(range(1, 9))
    assert ext["decline_action_ref"] == "native-decline-d1"
    assert ext["disclosure_audit"] == {
        "billing_type": "trial", "due_now_minor": 100,
        "renewal_amount_minor": 2700, "renewal_date_or_rule": "day 31",
        "cancellation_terms_present": True}
    assert ext["route_result"] == {
        "success_target": "upsell_2", "decline_target": "thank_you",
        "u2_entry_context": "from_downsell_1",
        "canonical_u2_page_id": tw.U2_PAGE_ID}
    assert ext["heading_normalization"]["recorded"] is True
    assert ext["difference_matrix"]["entitlements_u1_only"] == [
        "TEST-ENT-FULL", "TEST-ENT-COACHING"]
    assert dw._schema_violations(ext, EXT_SCHEMA) == []
    assert vd.validate_result_extension(ext, tw.U2_PAGE_ID) == []
    assert vd.validate_trial_disclosure(
        [o for o in trial_launch()["offers"] if o["slot"] == "downsell_1"][0],
        disclosure) == []
    assert set(ext) == set(EXT_SCHEMA["required"])


def test_one_time_derives_without_a_disclosure_document():
    ext, disclosure = derive(page(trial=False), one_time_launch())
    assert disclosure is None
    assert ext["disclosure_audit"]["billing_type"] == "one_time"
    assert ext["disclosure_audit"]["renewal_amount_minor"] is None
    assert vd.validate_result_extension(ext, tw.U2_PAGE_ID) == []


def test_derivation_is_byte_reproducible(tmp_path):
    outs = []
    for run in ("a", "b"):
        d = tmp_path / run
        d.mkdir()
        outs.append(dx.dump(derive()[0]))
    assert outs[0] == outs[1] and outs[0].endswith("\n")


def run_cli(tmp_path, launch, copy_doc, staged=None, name="run"):
    d = tmp_path / name
    d.mkdir()
    files = {"request": REQUEST, "launch": launch, "route-graph": graph(),
             "copy": copy_doc, "enrichment": SIDECAR}
    cmd = [sys.executable, str(SCRIPTS / "downsell_extension.py"),
           "--out", str(d / "extension-downsell_1.json"),
           "--disclosure-out", str(d / "disclosure-downsell_1.json")]
    for key, doc in files.items():
        (d / key).write_text(json.dumps(doc))
        cmd += ["--" + key, str(d / key)]
    if staged is not None:
        (d / "staged").write_text(json.dumps(staged))
        cmd += ["--staged-extension", str(d / "staged")]
    return d, subprocess.run(cmd, capture_output=True, text=True)


def test_cli_output_is_byte_identical_across_runs(tmp_path):
    shas = []
    for name in ("one", "two"):
        d, proc = run_cli(tmp_path, trial_launch(), page(), name=name)
        assert proc.returncode == 0, proc.stderr
        shas.append(hashlib.sha256(
            (d / "extension-downsell_1.json").read_bytes()).hexdigest())
    assert shas[0] == shas[1]


def test_derived_files_carry_a_wrapper_run_to_a_page_result(tmp_path):
    """DTY-05: only copy, journey and enrichment are staged by hand."""
    d, proc = run_cli(tmp_path, trial_launch(), page())
    assert proc.returncode == 0, proc.stderr
    # spec 11 section 4: the sidecar cites the launch's recorded difference-table
    # file and pins its sha256 (a relative ref resolves beside the sidecar)
    table = d / "difference-table.json"
    table.write_text(json.dumps({"difference_kind": SIDECAR["difference_kind"],
                                 "rationale": SIDECAR["rationale"]}))
    sidecar = dict(SIDECAR, difference_table_ref=table.name,
                   difference_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest())
    paths = {}
    for name, doc in (("request", REQUEST), ("launch", trial_launch()),
                      ("route-graph", None), ("copy", page()),
                      ("journey", {"main_purchased_verified": True,
                                   "u1_event": "explicit_decline",
                                   "u1_accepted": False}),
                      ("enrichment", sidecar)):
        paths[name] = d / (name + ".json")
        if doc is not None:
            paths[name].write_text(json.dumps(doc))
    paths["route-graph"].write_bytes(tw._graph_bytes())
    result = d / "result.json"
    wrapper = subprocess.run(
        [sys.executable, str(SCRIPTS / "downsell_wrapper.py"),
         "--request", str(paths["request"]), "--result", str(result),
         "--launch", str(paths["launch"]),
         "--route-graph", str(paths["route-graph"]),
         "--copy", str(paths["copy"]), "--journey", str(paths["journey"]),
         "--enrichment", str(paths["enrichment"]),
         "--extension", str(d / "extension-downsell_1.json"),
         "--disclosure", str(d / "disclosure-downsell_1.json"),
         "--skill81-root", str(SKILL81)],
        capture_output=True, text=True, cwd=str(d))
    assert wrapper.returncode == 0, wrapper.stderr
    # DTY-14 honesty ceiling: no --skill71-root, so no image stage ran; authored / L1, never verified
    page_result = json.loads(result.read_text())
    assert page_result["status"] == "authored" and page_result["proof_class"] == "L1"
    # the cited difference table's sha256 is recorded among the result artifacts
    assert {"path": str(table), "sha256": sidecar["difference_table_sha256"]} \
        in page_result["artifacts"]


def test_staged_one_time_label_on_a_trial_is_refused(tmp_path):
    """DTY-06."""
    ext, _ = derive()
    lie = copy.deepcopy(ext)
    lie["disclosure_audit"] = {
        "billing_type": "one_time", "due_now_minor": 100,
        "renewal_amount_minor": None, "renewal_date_or_rule": None,
        "cancellation_terms_present": True}
    assert "billing_type mismatch" in problems(staged=lie)
    d, proc = run_cli(tmp_path, trial_launch(), page(), staged=lie)
    assert proc.returncode == 2 and "billing_type mismatch" in proc.stderr
    # the honest staged extension is accepted, bare or wrapped
    assert derive(staged=ext)[0] == ext
    assert derive(staged={"downsell_result_extension": ext})[0] == ext


def test_staged_cta_and_decline_refs_must_equal_the_page(tmp_path):
    ext, _ = derive()
    bad = copy.deepcopy(ext)
    bad["decline_action_ref"] = "native-d1-action"
    assert "decline_action_ref mismatch" in problems(staged=bad)
    bad = copy.deepcopy(ext)
    bad["cta_map"][3]["action_ref"] = "other-action"
    assert "cta_map mismatch" in problems(staged=bad)


def test_page_stating_the_wrong_price_is_refused(tmp_path):
    """DTY-07 variant 1: $4.97 where the D1 price is $1 then $27."""
    wrong = page(**{"0": "Join for just $4.97 today."})
    assert "price-not-in-record" in problems(copy_doc=wrong)
    d, proc = run_cli(tmp_path, trial_launch(), wrong)
    assert proc.returncode == 2 and "price-not-in-record" in proc.stderr


def test_page_may_not_borrow_another_offers_amount():
    """The old check allowed every offer's amount; D1 alone is allowed now."""
    # $37 is the one-time D1 amount of the OTHER launch shape, not this trial's
    borrowed = page(**{"0": "Join for just $37 today."})
    assert "price-not-in-record" in problems(copy_doc=borrowed)
    # and a word-form price is caught too
    assert "price-not-in-record" in problems(
        copy_doc=page(**{"0": "Join for just five dollars."}))


def test_trial_page_with_no_price_or_terms_is_refused(tmp_path):
    """DTY-07 variant 2: no price and no renewal text at all."""
    bare = page()
    for s in bare["page"]["sections"]:
        s["body"], s["cta"]["label"] = "Join us.", "Join now"
    bare["page"]["sections"][7]["missed_out_items"] = ["Nothing here."] * 7
    bare["page"]["decline_action"]["label"] = "No thanks"
    msg = problems(copy_doc=bare)
    assert "price-not-on-page" in msg and "missing-renewal-terms" in msg
    d, proc = run_cli(tmp_path, trial_launch(), bare)
    assert proc.returncode == 2 and "missing-renewal-terms" in proc.stderr


@pytest.mark.parametrize("cut,named", [
    (" unless you cancel. The first renewal charge is on day 31, and "
     "renewals are monthly after that. You can cancel anytime before a "
     "renewal charge to stop future charges. If you cancel, your access "
     "continues until the end of the trial or the current paid month, then "
     "your membership access ends and you will not be charged again.",
     "cancellation statement"),
    ("After the trial, $27 per month continues the membership unless you "
     "cancel. ", "renewal amount"),
    ("$27 per month", "billing interval"),
])
def test_trial_page_missing_renewal_terms_is_refused(cut, named):
    """DTY-07 variant 3."""
    body = tw.PAGE_FIXTURE["page"]["sections"][6]["body"]
    assert cut in body
    replaced = "$27 per cycle" if named == "billing interval" else ""
    edited = body.replace(cut, replaced)
    if named == "billing interval":
        edited = edited.replace("renewals are monthly after that", "renewals continue")
    msg = problems(copy_doc=page(**{"6": edited}))
    assert "missing-renewal-terms" in msg and named in msg


def test_one_time_page_without_its_price_is_refused():
    stated = page(trial=False)
    for s in stated["page"]["sections"]:
        s["body"] = s["body"].replace("$37", "a small amount")
        s["cta"]["label"] = s["cta"]["label"].replace("$37", "today")
    stated["page"]["decline_action"]["label"] = "No thanks"
    for item in range(len(stated["page"]["sections"][7]["missed_out_items"])):
        stated["page"]["sections"][7]["missed_out_items"][item] = \
            stated["page"]["sections"][7]["missed_out_items"][item].replace("$37", "x")
    assert "price-not-on-page" in problems(copy_doc=stated,
                                           launch=one_time_launch())


def test_stated_amounts_parser():
    got = lambda t, c="USD": sorted(int(m) for _, m in dx.stated_amounts(t, c))
    assert got("$27.00 now, $1 trial, 30 days, 5 hours") == [100, 2700]
    assert got("only 1,997 USD or USD 47 or twenty-seven dollars") == \
        [2700, 4700, 199700]
    assert got("5,000 JPY", "JPY") == [5000]
    assert got("no money here") == []


def two_main_launch(d1_entitlements):
    launch = trial_launch()
    launch["offers"].insert(0, {
        "slot": "main", "offer_id": "TEST-MAIN-2",
        "entitlement_ids": ["TEST-ENT-MAIN-2"],
        "deliverables": ["second main"], "native_product_id": "p",
        "prices": [{"amount_minor": 9900, "billing_type": "one_time",
                    "approval_status": "approved", "native_price_id": "q"}]})
    [o for o in launch["offers"] if o["slot"] == "downsell_1"][0][
        "entitlement_ids"] = d1_entitlements
    return launch


def test_d1_regranting_a_main_entitlement_is_refused(tmp_path):
    """DTY-13: two mains, D1 repeats the SECOND main's entitlement."""
    launch = two_main_launch(["TEST-ENT-LITE", "test-ent-main-2"])
    assert "D1-OFFER-REGRANTS-MAIN" in problems(launch=launch)
    d, proc = run_cli(tmp_path, launch, page())
    assert proc.returncode == 2 and "D1-OFFER-REGRANTS-MAIN" in proc.stderr
    derive(launch=two_main_launch(["TEST-ENT-LITE"]))  # distinct: accepted


def test_entitlements_removed_vs_u1_is_computed_and_checked_against_all_mains():
    launch = two_main_launch(["TEST-ENT-LITE"])
    u1 = [o for o in launch["offers"] if o["slot"] == "upsell_1"][0]
    u1["entitlement_ids"] = ["TEST-ENT-FULL", "TEST-ENT-MAIN-2"]
    u1_, d1_, base = dx.offer_difference_inputs(launch, SIDECAR)
    assert d1_["entitlements_removed_vs_u1"] == [
        "TEST-ENT-FULL", "TEST-ENT-MAIN-2"]
    assert set(base["entitlement_ids"]) == {"TEST-ENT-MAIN",
                                            "TEST-ENT-MAIN-2"}
    # with two mains the single-main lookup returned None and skipped this
    assert "D1-OFFER-REMOVES-BASE-PURCHASE" in vd.validate_offer_difference(
        u1_, d1_, base)
