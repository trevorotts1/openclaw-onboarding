#!/usr/bin/env python3
"""test_ghl_verify_evidence_receipts.py — bound-evidence receipts.

The render manifest already binds a run's artifacts to their sha256, but the
manifest is written by the same pass that captured the artifacts. A reviewer
signing THOSE bytes is what makes the chain independent. These tests prove the
refusals, because a receipt that cannot refuse anything proves nothing:

  * a receipt whose artifact is missing is refused;
  * a receipt whose artifact changed after review is refused;
  * a receipt signed by the capturing run itself is refused;
  * a non-approving verdict is refused;
  * a receipt missing a binding field is refused;
  * a receipt with all of them and matching bytes passes.

No network. Artifacts are written into pytest's tmp_path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_verify as gv  # noqa: E402


@pytest.fixture()
def artifact(tmp_path):
    p = tmp_path / "capture-dom.html"
    p.write_bytes(b"<html><body>rendered page</body></html>\n")
    return p


@pytest.fixture()
def receipt(artifact):
    return gv.make_evidence_receipt(
        str(artifact), reviewer="independent-reviewer", run_id="run-1",
        reviewed_at="2026-10-22T12:00:00Z", captured_by="capturing-run",
        candidate_revision="a" * 40)


class TestBoundReceiptAccepts:
    def test_a_matching_receipt_passes(self, receipt):
        gv.assert_receipts_bound([receipt])  # no raise

    def test_the_digest_is_taken_from_the_file(self, artifact, receipt):
        import hashlib
        assert receipt["artifact_sha256"] == hashlib.sha256(
            artifact.read_bytes()).hexdigest()

    def test_receipts_round_trip_through_the_private_writer(self, tmp_path,
                                                            receipt):
        path = gv.write_evidence_receipt(str(tmp_path), receipt, "dom")
        assert path.endswith(".json")
        on_disk = json.loads(Path(path).read_text(encoding="utf-8"))
        mode = Path(path).stat().st_mode & 0o777
        assert mode == 0o600
        gv.assert_receipts_bound([on_disk])


class TestBoundReceiptRefusals:
    def test_a_missing_artifact_is_refused(self, receipt):
        receipt["artifact_path"] = "/nonexistent/capture-dom.html"
        with pytest.raises(gv.VerifyContradiction, match="missing"):
            gv.assert_receipts_bound([receipt])

    def test_an_artifact_changed_after_review_is_refused(self, artifact,
                                                         receipt):
        artifact.write_bytes(b"<html>tampered after the review</html>")
        with pytest.raises(gv.VerifyContradiction, match="changed after review"):
            gv.assert_receipts_bound([receipt])

    def test_a_receipt_signed_by_the_capturing_run_is_refused(self, receipt):
        receipt["reviewer"] = receipt["captured_by"]
        with pytest.raises(gv.VerifyContradiction, match="independent"):
            gv.assert_receipts_bound([receipt])

    def test_a_non_approving_verdict_is_refused(self, receipt):
        receipt["verdict"] = "rejected"
        with pytest.raises(gv.VerifyContradiction, match="verdict"):
            gv.assert_receipts_bound([receipt])

    @pytest.mark.parametrize("field", list(
        gv.REQUIRED_EVIDENCE_RECEIPT_FIELDS))
    def test_each_required_field_is_enforced(self, receipt, field):
        receipt[field] = ""
        with pytest.raises(gv.VerifyContradiction, match=field):
            gv.assert_receipts_bound([receipt])

    def test_a_non_dict_receipt_is_refused(self):
        with pytest.raises(gv.VerifyContradiction):
            gv.assert_receipts_bound(["not-a-receipt"])

    def test_one_bad_receipt_fails_the_whole_set(self, artifact, receipt):
        bad = gv.make_evidence_receipt(
            str(artifact), reviewer="independent-reviewer", run_id="run-2",
            captured_by="other-run")
        bad["artifact_path"] = "/nonexistent/x.html"
        with pytest.raises(gv.VerifyContradiction):
            gv.assert_receipts_bound([receipt, bad])

    def test_an_empty_receipt_set_is_not_an_error(self):
        """No receipts means no bound evidence was claimed — the gate lives
        where receipts are required, not here."""
        gv.assert_receipts_bound([])


class TestContractIsReusedNotReinvented:
    def test_receipts_use_the_existing_hasher(self, artifact):
        """The receipt digest is ghl_verify's own artifact hasher."""
        assert gv.make_evidence_receipt(
            str(artifact), reviewer="r")["artifact_sha256"] == \
            gv._sha256_file(str(artifact))

    def test_receipt_path_is_under_the_run_evidence_dir(self, tmp_path):
        path = gv.write_evidence_receipt(
            str(tmp_path), {"artifact_path": "x.html"}, "x")
        assert gv.EVIDENCE_RECEIPT_REL in path
        assert path.startswith(str(tmp_path))
