"""S06-08: tenant-safe read-back + no-secret evidence (doc 18 section 7).

MOCK/FIXTURE TIER ONLY: no network, no browser, no live GHL. Live legs stay
LIVE_PROOF_PENDING. Covers the prep step-9 test set for S06-08's scope:

  1. wrong-location read-back refused        -> TestWrongLocationRefused
  2. cross-tenant page receipt + cross-tenant result receipt as
     contradictions                           -> TestCrossTenantReceipts
  3. secret-file permission failure reported  -> TestPermissionFailureReported
     (the resolver's *_FILE refusal itself is proven in
     tests/test_ghl_secret_resolver.py and is cited, not re-implemented)
  4. expired browser auth = honest failed record
                                              -> TestExpiredAuthHonestFailure
  5. sensitive screenshot/trace handling      -> TestTraceSuppression
     (the artifact-content sweep over every sink lives in
     tests/test_ghl_secret_hygiene.py::TestEvidenceNoSecretSweep)
  6. unauthenticated receipt access denied by step-8 permissions
                                              -> TestUnauthenticatedAccessDenied

Plus the contract units: binding derivation + Q2 grandfathering, the
per-run read-back index (Q1 form 2), media caller-asserted stamping (Q6),
inventory tenant derivation (gap 11), and the run-state scrub sink (gap 9).
"""
from __future__ import annotations

import json
import os
import stat
import sys

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_evidence as ev  # noqa: E402
import ghl_fallback_ladder as fl  # noqa: E402
import ghl_id_handoff as handoff  # noqa: E402
import ghl_inventory as inv  # noqa: E402
import ghl_login_browser as lb  # noqa: E402
import ghl_media as media  # noqa: E402
import ghl_object_router as router  # noqa: E402
import ghl_receipts as receipts  # noqa: E402
import ghl_run_state as rs  # noqa: E402
import ghl_verify as verify  # noqa: E402

# Fabricated GHL-shaped location ids (NOT real client ids).
LOC_A = "Ab1Cd2Ef3Gh4Ij5Kl6Mn"
LOC_B = "Zy9Xw8Vu7Ts6Rq5Po4Nm"

posix_only = pytest.mark.skipif(os.name != "posix", reason="mode bits are POSIX")


def _page(step="s1"):
    return {"step": step, "page_id": "p1", "preview_url": "https://x/preview",
            "marker": "M", "copy_fidelity": False}


def _ok_fetcher(location_id=None, dom=""):
    def _f(url, marker):
        res = {"ok": True, "http": 200, "marker_in_rendered_dom": True,
               "render_errors": [], "dom_path": "", "png_path": "",
               "console_path": "", "dom_sha256": "", "png_sha256": "",
               "console_sha256": "", "dom_bytes": 0, "visible_text_len": 500}
        if location_id:
            res["location_id"] = location_id
        if dom:
            res["dom"] = dom
        return res
    return _f


# ---------------------------------------------------------------------------
# Contract units: derivation + Q2 grandfathering
# ---------------------------------------------------------------------------
class TestBindingDerivation:
    def test_bound_mismatch_unbound(self):
        assert ev.tenant_binding(LOC_A, LOC_A) == "bound"
        assert ev.tenant_binding(LOC_A, LOC_B) == "mismatch"
        assert ev.tenant_binding(LOC_A, None) == "unbound"
        assert ev.tenant_binding(None, LOC_A) == "unbound"
        assert ev.tenant_binding(None, None) == "unbound"

    def test_legacy_record_flags_unbound_never_silently_bound(self):
        assert ev.effective_binding({}) == "unbound"
        assert ev.effective_binding({"location_id": LOC_A}) == "unbound"
        fields = ev.tenant_fields(None, None)
        assert fields["tenant_binding"] == "unbound"
        assert fields["expected_location_id"] is None

    def test_observed_extraction_single_distinct_id_only(self):
        dom = f'<img src="https://assets.cdn.filesafe.space/{LOC_A}/media/x.png">'
        assert ev.extract_observed_location_id(dom) == LOC_A
        both = dom + f'<a href="https://app.gohighlevel.com/location/{LOC_B}/">x</a>'
        assert ev.extract_observed_location_id(both) is None  # ambiguous
        assert ev.extract_observed_location_id("<p>nothing</p>") is None


# ---------------------------------------------------------------------------
# Step 9 (1): wrong-location read-back refused
# ---------------------------------------------------------------------------
class TestWrongLocationRefused:
    def test_wrong_location_fails_the_page_no_override(self, tmp_path):
        rec = verify.verify_page(
            _page(), run_dir=str(tmp_path), fetcher=_ok_fetcher(LOC_B),
            live=False, expected_location_id=LOC_A)
        assert rec["PASS"] is False
        assert rec["tenant_binding"] == "mismatch"
        assert rec["expected_location_id"] == LOC_A
        assert rec["observed_location_id"] == LOC_B
        assert any("tenant_mismatch" in e for e in rec["render_errors"])

    def test_right_location_binds_and_passes(self, tmp_path):
        rec = verify.verify_page(
            _page(), run_dir=str(tmp_path), fetcher=_ok_fetcher(LOC_A),
            live=False, expected_location_id=LOC_A)
        assert rec["PASS"] is True
        assert rec["tenant_binding"] == "bound"

    def test_dom_observed_location_binds(self, tmp_path):
        dom = f'<img src="https://assets.cdn.filesafe.space/{LOC_A}/media/hero.png">'
        rec = verify.verify_page(
            _page(), run_dir=str(tmp_path), fetcher=_ok_fetcher(dom=dom),
            live=False, expected_location_id=LOC_A)
        assert rec["observed_location_id"] == LOC_A
        assert rec["tenant_binding"] == "bound"

    def test_no_expected_location_states_unbound_explicitly(self, tmp_path):
        rec = verify.verify_page(
            _page(), run_dir=str(tmp_path), fetcher=_ok_fetcher(LOC_A),
            live=False)
        assert rec["PASS"] is True
        assert rec["tenant_binding"] == "unbound"  # stated, never omitted

    def test_verify_all_mismatch_summary_is_honest_and_consistent(self, tmp_path):
        # Two pages need two fetcher behaviours; dispatch on the URL.
        def dispatch(url, marker):
            loc = LOC_A if "good" in url else LOC_B
            return _ok_fetcher(loc)(url, marker)
        pages = [dict(_page("good"), preview_url="https://x/good"),
                 dict(_page("bad"), preview_url="https://x/bad")]
        out = verify.verify_all(
            str(tmp_path), pages, live=False, fetcher=dispatch,
            run_id="run-t1", expected_location_id=LOC_A)
        summary = out["summary"]
        assert summary["overall_pass"] is False
        assert summary["tenant_binding"] == "mismatch"
        assert summary["expected_location_id"] == LOC_A
        # The honest mismatch summary passes the guard (verify_all already
        # ran it); claiming "bound" for it must raise.
        lie = dict(summary)
        lie["tenant_binding"] = "bound"
        with pytest.raises(verify.VerifyContradiction):
            verify.assert_consistent(lie, out["raw"])

    def test_mirror_invariant_refuses_unbound_pass(self):
        raw = [{"step": "s1", "PASS": True, "http": 200, "render_errors": [],
                "missing_images": [], "expected_location_id": LOC_A,
                "observed_location_id": None, "tenant_binding": "unbound"}]
        summary = verify.derive_summary(raw, run_id="r")
        assert summary["expected_location_id"] == LOC_A
        with pytest.raises(verify.VerifyContradiction):
            verify.assert_consistent(summary, raw)

    def test_legacy_summary_without_expected_is_untouched(self):
        raw = [{"step": "s1", "PASS": True, "http": 200, "render_errors": []}]
        summary = verify.derive_summary(raw, run_id="r")
        assert summary["expected_location_id"] is None
        verify.assert_consistent(summary, raw)  # Q2: must not raise


# ---------------------------------------------------------------------------
# Step 9 (2): cross-tenant receipts are contradictions
# ---------------------------------------------------------------------------
class TestCrossTenantReceipts:
    def test_cross_tenant_page_receipt_contradicts_summary(self, tmp_path):
        receipts.write_receipt(str(tmp_path), receipts.make_receipt(
            "page", "zhc_p", "created", response_id="p1",
            verify={"ok": True}, expected_location_id=LOC_B,
            observed_location_id=LOC_B))
        summary = receipts.reduce_receipts(str(tmp_path))
        summary["expected_location_id"] = LOC_A
        with pytest.raises(receipts.ReceiptContradiction):
            receipts.assert_consistent(summary, str(tmp_path))

    def test_cross_tenant_result_receipt_via_router(self, tmp_path):
        res = router.execute_write(
            "custom_field", "zhc_xt", evidence_root=str(tmp_path),
            idempotency_probe=lambda: None,
            rail_runners={router.Rail.SKILL44_CAF:
                          lambda s: router.RunResult(ok=True, response_id="cf-1")},
            verifier=lambda rid: {"ok": True, "location_id": LOC_B},
            expected_location_id=LOC_A, run_id="run-t2",
        )
        assert res["action"] == "failed"
        assert res["tenant_binding"] == "mismatch"
        summ = receipts.reduce_receipts(str(tmp_path))
        assert "custom_field:zhc_xt" in summ["failed"]
        assert "custom_field:zhc_xt" not in summ["verified"]
        assert summ["tenant"]["mismatch"] == ["custom_field:zhc_xt"]

    def test_bound_router_write_reduces_bound(self, tmp_path):
        res = router.execute_write(
            "tag", "zhc_ok", evidence_root=str(tmp_path),
            idempotency_probe=lambda: None,
            rail_runners={router.Rail.SKILL44_CAF:
                          lambda s: router.RunResult(ok=True, response_id="t1")},
            verifier=lambda rid: {"ok": True, "location_id": LOC_A},
            expected_location_id=LOC_A, run_id="run-t2",
        )
        assert res["action"] == "created"
        assert res["tenant_binding"] == "bound"
        summ = receipts.reduce_receipts(str(tmp_path))
        assert summ["tenant"]["bound"] == ["tag:zhc_ok"]
        receipts.assert_consistent(summ, str(tmp_path))  # must not raise

    def test_undeclared_mixed_tenant_reduction_refused(self, tmp_path):
        for loc, slug in ((LOC_A, "a"), (LOC_B, "b")):
            receipts.write_receipt(str(tmp_path), receipts.make_receipt(
                "tag", slug, "created", response_id=slug, verify={"ok": True},
                expected_location_id=loc, observed_location_id=loc))
        declared = receipts.reduce_receipts(str(tmp_path))
        assert declared["tenant"]["mixed_tenant"] is True
        receipts.assert_consistent(declared, str(tmp_path))  # declared: fine
        undeclared = dict(declared)
        undeclared.pop("tenant", None)
        with pytest.raises(receipts.ReceiptContradiction):
            receipts.assert_consistent(undeclared, str(tmp_path))

    def test_legacy_receipts_flag_unbound_in_reduction(self, tmp_path):
        receipts.write_receipt(str(tmp_path), receipts.make_receipt(
            "tag", "zhc_legacy", "created", response_id="t9",
            verify={"ok": True}))
        summ = receipts.reduce_receipts(str(tmp_path))
        assert summ["tenant"]["unbound"] == ["tag:zhc_legacy"]
        assert summ["tenant"]["mixed_tenant"] is False
        receipts.assert_consistent(summ, str(tmp_path))  # grandfathered: fine


# ---------------------------------------------------------------------------
# Step 9 (3) + step 8: permission failures are reported, never accepted
# ---------------------------------------------------------------------------
@posix_only
class TestPermissionFailureReported:
    def test_evidence_writes_land_private(self, tmp_path):
        root = str(tmp_path / "run")
        receipts.write_receipt(root, receipts.make_receipt(
            "tag", "zhc_m", "created", response_id="t1", verify={"ok": True}))
        eco = os.path.join(root, "ecosystem")
        assert stat.S_IMODE(os.stat(eco).st_mode) == 0o700
        files = os.listdir(eco)
        assert files and stat.S_IMODE(
            os.stat(os.path.join(eco, files[0])).st_mode) == 0o600
        assert ev.audit_evidence_permissions(root)["problems"] == []

    def test_loosened_file_is_reported(self, tmp_path):
        root = str(tmp_path / "run")
        path = receipts.write_receipt(root, receipts.make_receipt(
            "tag", "zhc_m", "created", response_id="t1", verify={"ok": True}))
        os.chmod(path, 0o644)
        problems = ev.audit_evidence_permissions(root)["problems"]
        assert any(p["path"] == path for p in problems)

    def test_missing_root_is_a_problem_not_a_pass(self, tmp_path):
        audit = ev.audit_evidence_permissions(str(tmp_path / "nope"))
        assert audit["problems"]

    def test_verify_outputs_are_private(self, tmp_path):
        verify.verify_all(
            str(tmp_path), [_page()], live=False, fetcher=_ok_fetcher(LOC_A),
            run_id="run-modes", expected_location_id=LOC_A)
        for rel in ("logs/final-preview-verify.json",
                    "scorecard/verify-summary.json",
                    "scorecard/render-manifest.json",
                    "scorecard/MOCK-DO-NOT-SHIP"):
            mode = stat.S_IMODE(os.stat(os.path.join(str(tmp_path), rel)).st_mode)
            assert mode == 0o600, rel
        for rel in ("logs", "scorecard"):
            mode = stat.S_IMODE(os.stat(os.path.join(str(tmp_path), rel)).st_mode)
            assert mode == 0o700, rel


# ---------------------------------------------------------------------------
# Step 9 (4): expired browser auth is an honest failed record
# ---------------------------------------------------------------------------
class TestExpiredAuthHonestFailure:
    def test_auth_stop_parks_the_ladder_with_a_receipt(self, tmp_path, monkeypatch):
        monkeypatch.setenv(fl.FLAG_ENV, "1")
        receipt_path = str(tmp_path / "ladder.json")
        result = fl.run_ladder(
            "survey",
            {"browser": lambda: {"ok": False, "code": "AUTH-STOP",
                                 "detail": "browser auth expired"},
             "api": lambda: {"ok": False, "code": "AUTH-STOP",
                             "detail": "refresh token rejected"}},
            receipt_path=receipt_path, expected_location_id=LOC_A)
        assert result.ok is False
        assert result.decision == "PARKED"
        on_disk = json.loads(open(receipt_path).read())
        assert on_disk["decision"] == "PARKED"
        assert on_disk["ok"] is False
        assert [a["code"] for a in on_disk["attempts"]] == ["AUTH-STOP", "AUTH-STOP"]
        assert on_disk["tenant_binding"] == "unbound"  # stated, never omitted

    def test_expired_auth_failed_receipt_never_reduces_as_verified(self, tmp_path):
        receipts.write_receipt(str(tmp_path), receipts.make_receipt(
            "page", "zhc_auth", "failed",
            error="auth expired: refresh token rejected (AUTH-STOP)"))
        summ = receipts.reduce_receipts(str(tmp_path))
        assert summ["failed"] == ["page:zhc_auth"]
        assert summ["verified"] == []
        assert summ["all_verified"] is False


# ---------------------------------------------------------------------------
# Step 9 (5): trace suppression records (Q5)
# ---------------------------------------------------------------------------
class _FakeEngine:
    def __init__(self):
        self.disabled = 0

    def disable_artifacts(self):
        self.disabled += 1


class TestTraceSuppression:
    def test_default_records_cover_login_and_payment(self):
        records = ev.default_trace_suppression()
        assert {r["step"] for r in records} == {"login", "payment"}
        assert all(r["artifacts_suppressed"] is True for r in records)
        assert all(r["capture_artifacts"] is False for r in records)
        ev.validate_trace_suppression(records)  # must not raise

    def test_unsuppressed_payment_record_is_refused(self):
        with pytest.raises(ev.TraceSuppressionError):
            ev.validate_trace_suppression(
                [{"step": "payment", "capture_artifacts": True,
                  "artifacts_suppressed": False}])

    def test_login_driver_proof_artifact(self):
        engine = _FakeEngine()
        driver = lb.LoginBrowser(engine=engine)
        assert driver.capture_artifacts is False
        assert engine.disabled == 1
        assert driver.artifact_suppression_record() == {
            "step": "login", "capture_artifacts": False,
            "artifacts_suppressed": True}
        assert lb.artifact_suppression_record()["step"] == "login"

    def test_run_state_carries_and_reports_the_flags(self, tmp_path):
        st = rs.RunState.start(
            "fixture-builder", [rs.PhaseSpec("a")], run_id="TS-RUN",
            state_root=str(tmp_path),
            trace_suppression=ev.default_trace_suppression(),
            expected_location_id=LOC_A)
        assert st.doc["trace_suppression"]
        block = rs.format_run_report(
            builder="fixture-builder", run_id="TS-RUN", status=rs.STATUS_OK,
            dry_run=True, evidence_root=str(tmp_path), duration_s=0.1,
            script_path=__file__, state=st, state_root=str(tmp_path))
        assert "login:suppressed" in block
        assert "payment:suppressed" in block

    def test_run_state_refuses_an_unsuppressed_payment_claim(self, tmp_path):
        with pytest.raises(ev.TraceSuppressionError):
            rs.RunState.start(
                "fixture-builder", [rs.PhaseSpec("a")], run_id="TS-BAD",
                state_root=str(tmp_path),
                trace_suppression=[{"step": "payment",
                                    "capture_artifacts": True,
                                    "artifacts_suppressed": False}])


# ---------------------------------------------------------------------------
# Step 9 (6): unauthenticated receipt access denied by permissions
# ---------------------------------------------------------------------------
@posix_only
class TestUnauthenticatedAccessDenied:
    def test_receipt_store_bits_deny_other_users(self, tmp_path):
        root = str(tmp_path / "run")
        path = receipts.write_receipt(root, receipts.make_receipt(
            "tag", "zhc_deny", "created", response_id="t1",
            verify={"ok": True}))
        dir_mode = stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode)
        file_mode = stat.S_IMODE(os.stat(path).st_mode)
        # No group/other bit anywhere on the path: another local user can
        # neither traverse the store dir nor read the receipt file.
        assert dir_mode & 0o077 == 0
        assert file_mode & 0o077 == 0
        assert ev.audit_evidence_permissions(root)["problems"] == []


# ---------------------------------------------------------------------------
# The read-back index (Q1 form 2) + NQ2 root pinning
# ---------------------------------------------------------------------------
class TestReadBackIndex:
    def _run_dir(self, tmp_path):
        run_dir = str(tmp_path / "run-idx")
        out = verify.verify_all(
            run_dir, [_page()], live=False, fetcher=_ok_fetcher(LOC_A),
            run_id="run-idx", expected_location_id=LOC_A)
        receipt_file = receipts.write_receipt(run_dir, receipts.make_receipt(
            "tag", "zhc_i", "created", response_id="t1", verify={"ok": True},
            expected_location_id=LOC_A, observed_location_id=LOC_A,
            run_id="run-idx"))
        handoff_file = handoff.write_handoff(
            run_dir, handoff.new_handoff(run_id="run-idx"))
        return run_dir, out, receipt_file, handoff_file

    def test_index_binds_the_run_and_verifies(self, tmp_path):
        run_dir, out, receipt_file, handoff_file = self._run_dir(tmp_path)
        index = ev.build_readback_index(
            run_dir, run_id="run-idx", expected_location_id=LOC_A,
            artifacts=[
                {"path": out["raw_path"], "kind": "verify_raw",
                 "observed_location_id": LOC_A},
                {"path": out["summary_path"], "kind": "verify_summary"},
                {"path": receipt_file, "kind": "receipt",
                 "observed_location_id": LOC_A},
                {"path": handoff_file, "kind": "id_handoff",
                 "observed_location_id": LOC_A},
            ])
        assert index["tenant_binding"] == "bound"
        assert index["run_dir"] == run_dir  # the run's OWN root (NQ2)
        path = ev.write_readback_index(run_dir, index)
        loaded = json.loads(open(path).read())
        result = ev.verify_readback_index(loaded)
        assert result["ok"] is True
        assert result["tenant_binding"] == "bound"

    def test_tampered_member_is_a_contradiction(self, tmp_path):
        run_dir, out, _r, _h = self._run_dir(tmp_path)
        index = ev.build_readback_index(
            run_dir, run_id="run-idx", expected_location_id=LOC_A,
            artifacts=[{"path": out["raw_path"], "kind": "verify_raw"}])
        with open(out["raw_path"], "a") as fh:
            fh.write("\n ")
        with pytest.raises(ev.EvidenceContradiction):
            ev.verify_readback_index(index)

    def test_cross_tenant_member_is_a_contradiction(self, tmp_path):
        run_dir, out, _r, _h = self._run_dir(tmp_path)
        index = ev.build_readback_index(
            run_dir, run_id="run-idx", expected_location_id=LOC_A,
            artifacts=[{"path": out["raw_path"], "kind": "verify_raw",
                        "observed_location_id": LOC_B}])
        assert index["tenant_binding"] == "mismatch"
        with pytest.raises(ev.EvidenceContradiction):
            ev.verify_readback_index(index)

    def test_missing_member_is_refused_at_build(self, tmp_path):
        with pytest.raises(ev.EvidenceContradiction):
            ev.build_readback_index(
                str(tmp_path), run_id="r",
                artifacts=[{"path": str(tmp_path / "ghost.json"),
                            "kind": "verify_raw"}])

    def test_index_member_redactions_survive_round_trip(self, tmp_path):
        # S06-08 D3 cure: a redactions count supplied on the artifact dict
        # is recorded on the member entry (at base it was silently dropped)
        # and survives build + write + verify. A supplied 0 is a real count
        # and is recorded as 0, not treated as absent.
        member = tmp_path / "artifact.json"
        member.write_text(json.dumps({"x": 1}))
        member2 = tmp_path / "artifact2.json"
        member2.write_text(json.dumps({"y": 2}))
        index = ev.build_readback_index(
            str(tmp_path), run_id="r",
            artifacts=[
                {"path": str(member), "kind": "verify_raw", "redactions": 3},
                {"path": str(member2), "kind": "receipt", "redactions": 0},
            ])
        by_kind = {e["kind"]: e for e in index["artifacts"]}
        assert by_kind["verify_raw"]["redactions"] == 3
        assert by_kind["receipt"]["redactions"] == 0
        path = ev.write_readback_index(str(tmp_path), index)
        loaded = json.loads(open(path).read())
        loaded_by_kind = {e["kind"]: e for e in loaded["artifacts"]}
        assert loaded_by_kind["verify_raw"]["redactions"] == 3
        assert loaded_by_kind["receipt"]["redactions"] == 0
        assert ev.verify_readback_index(loaded)["ok"] is True

    def test_index_member_without_redactions_omits_the_field(self, tmp_path):
        # S06-08 D3 convention, pinned: when the caller supplies no count,
        # the entry carries no "redactions" key at all (the module's
        # existing convention for optional entry data, as with
        # observed_location_id), and the member shape is otherwise exactly
        # the pre-cure shape.
        member = tmp_path / "artifact.json"
        member.write_text(json.dumps({"x": 1}))
        index = ev.build_readback_index(
            str(tmp_path), run_id="r",
            artifacts=[{"path": str(member), "kind": "verify_raw"}])
        (entry,) = index["artifacts"]
        assert "redactions" not in entry
        assert set(entry) == {"path", "kind", "sha256", "bytes"}
        assert ev.verify_readback_index(index)["ok"] is True


# ---------------------------------------------------------------------------
# Q6: media evidence claim is caller-asserted, never "verified" by assertion
# ---------------------------------------------------------------------------
class TestMediaEvidenceStatus:
    _REC = {"id": "hero", "prompt": "p", "file": "/x/hero.png",
            "cdn_url": "https://storage.googleapis.com/msgsndr/x/hero.png",
            "cdn_http_status": 200, "used_on_page_id": "P1"}

    def test_entries_are_stamped_caller_asserted(self, tmp_path):
        out = media.build_image_manifest(
            [dict(self._REC)], out_path=str(tmp_path / "manifest.json"))
        assert out[0]["evidence_status"] == "caller_asserted"

    def test_cdn_verified_claim_is_refused(self):
        with pytest.raises(ValueError):
            media.build_image_manifest(
                [dict(self._REC, evidence_status="cdn_verified")])

    @posix_only
    def test_manifest_file_is_private(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        media.build_image_manifest([dict(self._REC)], out_path=path)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# ---------------------------------------------------------------------------
# Gap 11: inventory tenant derivation
# ---------------------------------------------------------------------------
class TestInventoryTenant:
    def test_rows_carrying_the_asked_location_bind(self):
        report = inv.enumerate_zhc_inventory(
            LOC_A,
            funnel_lister=lambda loc: [
                {"id": "f1", "name": "ZHC X", "locationId": LOC_A}],
            page_lister=lambda f, loc: [
                {"id": "p1", "name": "ZHC Y", "status": "draft",
                 "locationId": LOC_A}])
        assert report.tenant_binding == "bound"
        assert report.observed_location_id == LOC_A
        assert len(report.pages) == 1

    def test_foreign_row_is_excluded_and_counted(self):
        report = inv.enumerate_zhc_inventory(
            LOC_A,
            funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [
                {"id": "p1", "name": "ZHC mine", "status": "draft",
                 "locationId": LOC_A},
                {"id": "p2", "name": "ZHC foreign", "status": "draft",
                 "locationId": LOC_B}])
        assert [p.page for p in report.pages] == ["p1"]
        assert report.tenant_mismatch_rows == 1
        assert report.tenant_binding == "mismatch"

    def test_rows_without_location_are_honestly_unbound(self):
        report = inv.enumerate_zhc_inventory(
            LOC_A,
            funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [
                {"id": "p1", "name": "ZHC Y", "status": "draft"}])
        assert report.tenant_binding == "unbound"
        assert report.observed_location_id is None

    def test_write_load_round_trip_preserves_tenant_fields(self, tmp_path):
        report = inv.enumerate_zhc_inventory(
            LOC_A,
            funnel_lister=lambda loc: [
                {"id": "f1", "name": "ZHC X", "locationId": LOC_A}],
            page_lister=lambda f, loc: [
                {"id": "p1", "name": "ZHC Y", "status": "draft",
                 "locationId": LOC_A}])
        path = inv.write_inventory(str(tmp_path), report)
        loaded = inv.load_inventory(path)
        assert loaded.tenant_binding == "bound"
        assert loaded.observed_location_id == LOC_A


# ---------------------------------------------------------------------------
# Gap 9: the run-state sink scrubs argv/carry and lands private
# ---------------------------------------------------------------------------
@posix_only
class TestRunStateSink:
    def test_argv_secret_value_never_reaches_disk(self, tmp_path):
        secret = "pit-fixture-abcdef0123456789"
        st = rs.RunState.start(
            "fixture-builder", [rs.PhaseSpec("a")], run_id="RS-1",
            state_root=str(tmp_path), argv=["--pit", secret],
            secret_values=[secret])
        st.carry_set("note", f"token was {secret}")
        st.save()
        text = open(st.path).read()
        assert secret not in text
        assert st.doc["redactions"] >= 1
        assert stat.S_IMODE(os.stat(st.path).st_mode) == 0o600
        # The state ROOT only gains 0700 when this module creates it;
        # tmp_path pre-exists here, and pre-existing roots are never
        # chmodded (ensure_private_dir's created-only rule).

    def test_shaped_secret_in_carry_is_scrubbed_without_values(self, tmp_path):
        st = rs.RunState.start(
            "fixture-builder", [rs.PhaseSpec("a")], run_id="RS-2",
            state_root=str(tmp_path))
        st.carry_set("auth", "Authorization: Bearer abcdefgh12345678")
        st.save()
        assert "abcdefgh12345678" not in open(st.path).read()
