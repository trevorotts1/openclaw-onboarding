"""S06-06 / S06-24: Skill 6 publishes only against a launcher approval record.

Run: python3 -m pytest 06-ghl-install-pages/tools/test_ghl_publish_approval.py -q

No network, no browser, no real ids. The "launch store" is a tmp directory of
<approval_ref>.json files; the gate evidence is a synthesized machine summary
(same shape tests/test_ghl_gate.py uses).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import uuid

import pytest

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_builder as b
import ghl_publish_approval as pa
import ghl_verify

LOC = "FIXTURE0LOCATION0000"
PAGE = "PAGEID0000000000fake"
FUNNEL = "FUNNELID000000000fake"
MARKER = "ZHC-APPROVAL-MARKER"
LIVE = "approved_live_publication"


def _record(ref="APPR-LIVE", **over):
    rec = {"approval_ref": ref, "allowed_write_target": LIVE, "test_only": False,
           "location_id": LOC, "page_ids": [PAGE]}
    rec.update(over)
    return rec


@pytest.fixture()
def store(tmp_path, monkeypatch):
    d = tmp_path / "launch-store"
    d.mkdir()
    monkeypatch.setenv(pa.STORE_ENV, str(d))

    def put(ref="APPR-LIVE", **over):
        (d / f"{ref}.json").write_text(json.dumps(_record(ref, **over)))
        return ref

    put.dir = d
    return put


@pytest.fixture(autouse=True)
def _nonce_dir(tmp_path_factory, monkeypatch):
    # TEST-ONLY: the run-nonce file ghl_verify.verify_all leaves OUTSIDE the
    # evidence tree lives in a throwaway dir (S06-04).
    monkeypatch.setenv(ghl_verify.NONCE_DIR_ENV, str(tmp_path_factory.mktemp("nonces")))


def _seal(run_dir) -> None:
    """TEST-ONLY seal: write the render manifest (dom/png/console re-hashed by
    ghl_gate) and the 0600 run-nonce file, the shape ghl_verify.verify_all
    leaves. A tree without them is hand-forged and the gate refuses it (S06-04).
    Same recipe as tests/test_ghl_gate.py::_seal."""
    run_dir = str(run_dir)
    raw_path = os.path.join(run_dir, ghl_verify.RAW_REL)
    summary_path = os.path.join(run_dir, ghl_verify.SUMMARY_REL)
    with open(raw_path) as f:
        raw = json.load(f)
    render = os.path.join(run_dir, "render")
    os.makedirs(render, exist_ok=True)
    manifest = {}
    for i, r in enumerate(raw):
        step = r.get("step") or r.get("page_id") or f"row{i}"
        marker = r.setdefault("marker", f"SEAL-MARKER-{step}") if r.get("PASS") is True else "SEAL"
        entry = {}
        for key, ext, data in (("dom", "dom.html", f"<html><body><p>{marker}</p></body></html>".encode()),
                               ("png", "png", b"\x89PNG\r\n\x1a\n" + b"x" * 64),
                               ("console", "console.json", b"[]")):
            p = os.path.join(render, f"{step}.{ext}")
            with open(p, "wb") as f:
                f.write(data)
            entry[f"{key}_path"] = p
            entry[f"{key}_sha256"] = ghl_verify._sha256_file(p)
        manifest[step] = entry
    with open(raw_path, "w") as f:
        json.dump(raw, f)
    manifest_path = os.path.join(run_dir, ghl_verify.RENDER_MANIFEST_REL)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    with open(summary_path) as f:
        summary = json.load(f)
    ghl_verify.write_run_nonce(run_dir, summary["run_nonce"], raw_path, manifest_path)


def _evidence(tmp_path, *, page=PAGE, passed=True):
    """A synthesized passing (or failing) ghl_gate evidence root for one page."""
    root = tmp_path / "evidence"
    (root / "scorecard").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "scorecard" / "verify-summary.json").write_text(json.dumps({
        "overall_pass": passed, "passed": int(passed), "total": 1,
        "failed": int(not passed), "writer": "ghl_verify.verify_all",
        "run_nonce": str(uuid.uuid4())}))
    (root / "logs" / "final-preview-verify.json").write_text(json.dumps(
        [{"step": "home", "page_id": page, "PASS": passed, "http_code": 200 if passed else 500}]))
    _seal(root)
    return str(root)


def _page_data():
    return {"sections": [{"elements": [{"id": "e", "type": "custom-code", "extra": {
        "customCode": {"value": {"rawCustomCode": "x"}}}}]}], "settings": {}}


def _save_kwargs(**over):
    kw = dict(page_id=PAGE, funnel_id=FUNNEL, location_id=LOC, current_location_id=LOC,
              locator={"section_idx": 0, "element_idx": 0}, new_value=f"<p>{MARKER}</p>",
              page_version=1, page_data=_page_data(),
              preview_url=f"https://www.example.com/preview/{PAGE}", marker=MARKER)
    kw.update(over)
    return kw


# -- ROW 1: free strings and bare booleans are refused --------------------------------

@pytest.mark.parametrize("approval", ["yes", "live", "publish", "approved", "go", "true",
                                      True, False, None, "", {"allowed_write_target": LIVE}])
def test_may_publish_refuses_free_string_boolean_and_dict(approval, store, tmp_path):
    assert b.may_publish(approval) is False
    assert b.may_publish(approval, location_id=LOC, page_id=PAGE,
                         evidence_root=_evidence(tmp_path)) is False


def test_may_publish_true_only_with_record_and_gate(store, tmp_path):
    ref = store()
    ev = _evidence(tmp_path)
    assert b.may_publish(ref, location_id=LOC, page_id=PAGE, evidence_root=ev) is True
    # verified record alone is not enough: ghl_gate must have passed for THIS page
    assert b.may_publish(ref, location_id=LOC, page_id=PAGE) is False
    assert b.may_publish(ref, location_id=LOC, page_id=PAGE,
                         evidence_root=_evidence(tmp_path / "x", page="OTHERPAGE0000000fake")) is False


@pytest.mark.parametrize("over", [
    {"allowed_write_target": "approved_test_location"},
    {"allowed_write_target": "local_only"},
    {"test_only": True},
    {"test_only": "false"},
    {"location_id": "WRONGLOCATION000fake"},
    {"page_ids": ["SOMEOTHERPAGE000fake"]},
    {"page_ids": []},
    {"revoked": True},
    {"expires_at": time.time() - 60},
    {"expires_at": "not-a-date"},
])
def test_record_that_does_not_authorize_is_refused(over, store, tmp_path):
    ref = store(**over)
    ev = _evidence(tmp_path)
    assert b.may_publish(ref, location_id=LOC, page_id=PAGE, evidence_root=ev) is False


def test_ref_is_not_a_path_and_missing_store_refuses(store, monkeypatch):
    assert pa.read_record("../APPR-LIVE") is None
    store()
    monkeypatch.delenv(pa.STORE_ENV)
    assert pa.read_record("APPR-LIVE") is None


# -- ROW 3 (S06-06 proof): page_autosave(publish=True) ---------------------------------

def _autosave(**over):
    kw = dict(funnel_id=FUNNEL, page_version=1, location_id=LOC, publish=True)
    kw.update(over)
    return b.page_autosave(PAGE, _page_data(), **kw)


def test_page_autosave_publish_without_record_raises(store, tmp_path):
    with pytest.raises(pa.PublishApprovalError):
        _autosave()
    with pytest.raises(pa.PublishApprovalError):
        _autosave(approval="yes", evidence_root=_evidence(tmp_path))


def test_page_autosave_publish_with_test_only_approval_is_refused(store, tmp_path):
    ref = store("APPR-TEST", test_only=True, allowed_write_target="approved_test_location")
    with pytest.raises(pa.PublishApprovalError):
        _autosave(approval=ref, evidence_root=_evidence(tmp_path))


def test_page_autosave_publish_before_gate_is_refused(store, tmp_path):
    ref = store()
    with pytest.raises(pa.PublishApprovalError):
        _autosave(approval=ref)  # no evidence: verification has not run
    with pytest.raises(pa.PublishApprovalError):
        _autosave(approval=ref, evidence_root=_evidence(tmp_path, passed=False))


def test_page_autosave_publish_with_record_and_gate_publishes(store, tmp_path):
    ref = store()
    step = _autosave(approval=ref, evidence_root=_evidence(tmp_path))
    assert step["body"]["pageType"] == "published"


def test_page_autosave_default_is_draft(store):
    assert _autosave(publish=False)["body"]["pageType"] == "draft"


# -- emit_rest_save_plan: publish gating + S06-24 verify step ---------------------------

def _save_step(plan):
    return next(s for s in plan["steps"] if s["step"] == "page_autosave")


def test_plan_with_free_string_approval_stays_draft_and_says_why(store):
    plan = b.emit_rest_save_plan(**_save_kwargs(approval="yes"))
    assert plan["publish"] is False
    assert _save_step(plan)["body"]["pageType"] == "draft"
    assert plan["publish_refused"]


def test_plan_publishes_only_after_record_and_gate(store, tmp_path):
    ref = store()
    before = b.emit_rest_save_plan(**_save_kwargs(approval=ref))  # pre-verify emission
    assert before["publish"] is False and before["publish_refused"]
    after = b.emit_rest_save_plan(**_save_kwargs(approval=ref, evidence_root=_evidence(tmp_path)))
    assert after["publish"] is True
    assert _save_step(after)["body"]["pageType"] == "published"
    assert "publish_refused" not in after


def test_plan_with_test_only_record_never_publishes(store, tmp_path):
    ref = store("APPR-TEST", test_only=True, allowed_write_target="approved_test_location")
    plan = b.emit_rest_save_plan(**_save_kwargs(approval=ref, evidence_root=_evidence(tmp_path)))
    assert plan["publish"] is False


# -- ROW 4 (S06-24 proof): the verify step is verify_all / render_check -----------------

def test_rest_save_plan_verify_step_names_verify_all(store):
    plan = b.emit_rest_save_plan(**_save_kwargs())
    verify = next(s for s in plan["steps"] if s["step"] == "verify_preview")
    assert verify["action"] == "verify_all"
    assert "verify_all" in verify["call"] and "render_check" in verify["call"]
    assert verify["page_id"] == PAGE
    assert verify["expect"]["marker_in_rendered_dom"] is True
    assert "verify_all" in json.dumps(plan)
    assert verify["action"] != "verify_url"  # raw-body marker check never advances 'previewed'


# -- ROW 2: graphics_ghl_push refuses a push without the same record --------------------

def _load_graphics_push():
    here = os.path.abspath(_TOOLS)
    root = os.path.dirname(os.path.dirname(here))
    path = os.path.join(root, "45-design-intelligence-library", "scripts", "graphics_ghl_push.py")
    spec = importlib.util.spec_from_file_location("graphics_ghl_push_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_graphics_push_refuses_without_record(store, tmp_path, monkeypatch):
    g = _load_graphics_push()
    monkeypatch.setenv("GHL_LOCATION_ID", LOC)
    monkeypatch.setenv("GHL_API_KEY", "pit-fixture")
    job = tmp_path / "job"
    (job / "qc").mkdir(parents=True)
    (job / "qc" / "image_qc_report.json").write_text(json.dumps({"assets": [
        {"local_path": "a.png", "pass": True, "triggered_autofails": []}]}))
    uploads = []

    def opener(req, timeout):
        uploads.append(req)
        raise AssertionError("no network call may happen without the record")

    test_rec = store("APPR-TEST", test_only=True, allowed_write_target="approved_test_location")
    for ref in (None, "yes", True, test_rec, "APPR-MISSING"):
        with pytest.raises(RuntimeError, match="REFUSE live write"):
            g.push_graphics_media(job, opener=opener, approval_ref=ref)
    assert uploads == [] and not (job / "media_library.json").exists()


def test_graphics_selftest_still_passes():
    assert _load_graphics_push()._selftest() == 0
