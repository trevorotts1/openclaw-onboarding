"""Offline tests for the F6 receipts store + reducer (ghl_receipts.py).

No network, no browser, no GHL writes — everything runs against a tmp dir.
These wrap the module's own selftest AND add direct behavioural assertions so
a regression in "no receipt = not created" / the anti-fabrication guard fails
CI, not a live build three weeks from now.
"""

import json
import os
import sys
import tempfile

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_receipts as receipts  # noqa: E402
import ghl_object_router as router  # noqa: E402


def test_receipts_selftest_passes():
    assert receipts._selftest() == 0


# ---------------------------------------------------------------------------
# Store round-trip
# ---------------------------------------------------------------------------
def test_write_receipt_round_trips_and_is_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        r = receipts.make_receipt(
            "custom_field", "zhc_favorite_color", "created",
            response_id="cf-1", request_shape={"key": "zhc_favorite_color"},
            verify={"ok": True, "proof": "GET matched"},
        )
        path = receipts.write_receipt(tmp, r)
        assert os.path.exists(path)
        assert path.endswith("custom_field-zhc_favorite_color.json")
        with open(path) as fh:
            on_disk = json.load(fh)
        assert on_disk["object_type"] == "custom_field"
        assert on_disk["response_id"] == "cf-1"
        assert on_disk["created"] is True


def test_make_receipt_rejects_invalid_action():
    with pytest.raises(ValueError):
        receipts.make_receipt("tag", "x", "not_a_real_action")


def test_slug_is_sanitized_in_the_filename():
    with tempfile.TemporaryDirectory() as tmp:
        r = receipts.make_receipt("survey", "ZHC Intake / Survey #1!", "created",
                                   response_id="s1", verify={"ok": True})
        path = receipts.write_receipt(tmp, r)
        # no path traversal, no raw slashes/spaces smuggled into the filename
        assert "/" not in os.path.basename(path).replace(".json", "")
        assert os.path.exists(path)


# ---------------------------------------------------------------------------
# Reduction — the ONLY legitimate path to a run summary
# ---------------------------------------------------------------------------
def test_reduce_receipts_on_empty_root_is_honest_zero():
    with tempfile.TemporaryDirectory() as tmp:
        summ = receipts.reduce_receipts(tmp)
        assert summ == {
            "created": [], "reused": [], "failed": [], "unreadable": [],
            "verified": [], "unverified": [], "total": 0, "all_verified": True,
        }


def test_reduce_receipts_never_trusts_memory_only_disk():
    """A crashed mid-run process should still leave an honest PARTIAL summary —
    reduce_receipts must re-read disk every call, not accumulate in-process."""
    with tempfile.TemporaryDirectory() as tmp:
        receipts.write_receipt(tmp, receipts.make_receipt(
            "tag", "zhc_a", "created", response_id="t1", verify={"ok": True}))
        summ1 = receipts.reduce_receipts(tmp)
        assert summ1["created"] == ["tag:zhc_a"]

        # simulate a second object landing mid-run, written by another process
        receipts.write_receipt(tmp, receipts.make_receipt(
            "tag", "zhc_b", "created", response_id="t2", verify={"ok": True}))
        summ2 = receipts.reduce_receipts(tmp)
        assert summ2["created"] == ["tag:zhc_a", "tag:zhc_b"]
        assert summ2["total"] == 2


def test_failed_receipt_never_counted_as_created_or_reused():
    with tempfile.TemporaryDirectory() as tmp:
        receipts.write_receipt(tmp, receipts.make_receipt(
            "survey", "zhc_survey", "failed", error="public URL 404"))
        summ = receipts.reduce_receipts(tmp)
        assert summ["failed"] == ["survey:zhc_survey"]
        assert "survey:zhc_survey" not in summ["created"]
        assert "survey:zhc_survey" not in summ["reused"]
        assert summ["all_verified"] is False


def test_unverified_create_is_excluded_from_verified_bucket():
    with tempfile.TemporaryDirectory() as tmp:
        receipts.write_receipt(tmp, receipts.make_receipt(
            "custom_field", "zhc_fav", "created", response_id="cf1",
            verify={"ok": False, "detail": "read-back mismatch"}))
        summ = receipts.reduce_receipts(tmp)
        assert summ["created"] == ["custom_field:zhc_fav"]
        assert summ["verified"] == []
        assert summ["unverified"] == ["custom_field:zhc_fav"]
        assert summ["all_verified"] is False


def test_corrupt_receipt_file_surfaces_never_silently_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        eco = os.path.join(tmp, "ecosystem")
        os.makedirs(eco)
        with open(os.path.join(eco, "tag-broken.json"), "w") as fh:
            fh.write("{not valid json at all")
        summ = receipts.reduce_receipts(tmp)
        assert summ["unreadable"] == ["None:tag-broken.json"]
        assert summ["total"] == 1
        assert summ["all_verified"] is False


# ---------------------------------------------------------------------------
# assert_consistent — the anti-fabrication guard (the "30/30 vs 1/6" incident)
# ---------------------------------------------------------------------------
def test_assert_consistent_passes_for_a_truthful_summary():
    with tempfile.TemporaryDirectory() as tmp:
        receipts.write_receipt(tmp, receipts.make_receipt(
            "tag", "zhc_a", "created", response_id="t1", verify={"ok": True}))
        truth = receipts.reduce_receipts(tmp)
        receipts.assert_consistent(truth, tmp)  # must not raise


def test_assert_consistent_raises_on_fabricated_created_claim():
    with tempfile.TemporaryDirectory() as tmp:
        truth = receipts.reduce_receipts(tmp)  # empty root
        lie = dict(truth)
        lie["created"] = ["tag:zhc_never_happened"]
        with pytest.raises(receipts.ReceiptContradiction):
            receipts.assert_consistent(lie, tmp)


def test_assert_consistent_raises_on_fabricated_verified_claim():
    """The exact shape of the historical incident: N/N PASS claimed while the
    receipts show a lower true verified count."""
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(6):
            ok = i < 1  # only 1 of 6 actually verifies live
            receipts.write_receipt(tmp, receipts.make_receipt(
                "page", f"zhc_page_{i}", "created", response_id=f"p{i}",
                verify={"ok": ok}))
        truth = receipts.reduce_receipts(tmp)
        assert len(truth["created"]) == 6
        assert len(truth["verified"]) == 1

        fabricated = dict(truth)
        fabricated["verified"] = list(truth["created"])  # claims 30/30-style
        with pytest.raises(receipts.ReceiptContradiction):
            receipts.assert_consistent(fabricated, tmp)

        # the TRUE summary must still pass
        receipts.assert_consistent(truth, tmp)


def test_assert_consistent_allows_honest_under_claiming():
    with tempfile.TemporaryDirectory() as tmp:
        receipts.write_receipt(tmp, receipts.make_receipt(
            "tag", "zhc_a", "created", response_id="t1", verify={"ok": True}))
        partial = {"created": [], "reused": [], "verified": [], "total": 0}
        receipts.assert_consistent(partial, tmp)  # must not raise


def test_reduce_receipts_strict_raises_on_conflicting_response_id():
    with tempfile.TemporaryDirectory() as tmp:
        eco = os.path.join(tmp, "ecosystem")
        os.makedirs(eco)
        r1 = receipts.make_receipt("tag", "zhc_x", "created", response_id="A")
        r2 = receipts.make_receipt("tag", "zhc_x", "created", response_id="B")
        with open(os.path.join(eco, "tag-zhc_x.json"), "w") as fh:
            json.dump(r1, fh)
        with open(os.path.join(eco, "tag-zhc_x__race.json"), "w") as fh:
            json.dump(r2, fh)
        with pytest.raises(receipts.ReceiptContradiction):
            receipts.reduce_receipts(tmp, strict=True)
        # default (non-strict) does not raise — backward compatible
        receipts.reduce_receipts(tmp, strict=False)


# ---------------------------------------------------------------------------
# Router integration — the router must use the SAME store, not a shadow copy
# ---------------------------------------------------------------------------
def test_router_reexports_the_same_receipts_module():
    assert router.make_receipt is receipts.make_receipt
    assert router.reduce_receipts is receipts.reduce_receipts
    assert router.write_receipt is receipts.write_receipt
    assert router.assert_consistent is receipts.assert_consistent


def test_router_execute_write_receipts_are_readable_by_the_shared_reducer():
    with tempfile.TemporaryDirectory() as tmp:
        res = router.execute_write(
            "custom_field", "zhc_shared", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={router.Rail.SKILL44_CAF:
                          lambda s: router.RunResult(ok=True, response_id="cf-shared")},
            verifier=lambda rid: {"ok": True, "proof": "GET matched"},
        )
        assert res["action"] == "created"
        summ = receipts.reduce_receipts(tmp)
        assert "custom_field:zhc_shared" in summ["created"]
        assert "custom_field:zhc_shared" in summ["verified"]
        receipts.assert_consistent(summ, tmp)  # self-consistent by construction


def test_router_execute_write_failure_never_reduces_as_created():
    with tempfile.TemporaryDirectory() as tmp:
        res = router.execute_write(
            "survey", "zhc_fails", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={router.Rail.BROWSER:
                          lambda s: router.RunResult(ok=True, response_id="s1")},
            verifier=lambda rid: {"ok": False, "detail": "public URL 404"},
        )
        assert res["action"] == "failed"
        summ = receipts.reduce_receipts(tmp)
        assert "survey:zhc_fails" not in summ["created"]
        assert "survey:zhc_fails" in summ["failed"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_summarize_prints_json(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        receipts.write_receipt(tmp, receipts.make_receipt(
            "tag", "zhc_cli", "created", response_id="t1", verify={"ok": True}))
        rc = receipts.main(["--summarize", tmp])
        assert rc == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["created"] == ["tag:zhc_cli"]


def test_cli_selftest_exits_zero():
    assert receipts.main(["--selftest"]) == 0
