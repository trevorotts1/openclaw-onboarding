"""test_negative_fixtures.py — W28b-B2: the adversarial rows of QC.md, as tests.

Covers the four negative fixtures (see tests/negative_fixtures.py):

  FIX 32  forged approval        — AF-FORGED-APPROVAL, fail-closed on all four
                                   enforcement surfaces; verified-id control ACCEPTED.
  FIX 35/110 dark negation       — dark REQUEST fails; DO-NOT prohibition row PASSES
                                   (negation-aware scan) and earns the prompt lint;
                                   client_dark_theme / DARK_OK opt-in control passes.
  FIX 33  same-model judge       — graded_by == authoring stamp blocks
                                   qc_aggregate; different-model grader control clean.
  9.11    stylised-type OCR      — checked:true/matched:false slide FAILS without the
                                   logged, oracle-verified AF-OCR-READBACK owner skip,
                                   PASSES with one (owner_msg_id resolvable); an
                                   UNDETERMINED id keeps the gate shut; checked:false
                                   is NEVER waivable.

Every negative row names the gate it exercises; every negative has a positive
control on the same instrument (QC.md rule 6 / the negative-result contract).

Run with pytest (pytest tests/test_negative_fixtures.py) or standalone
(python3 tests/test_negative_fixtures.py) — the standalone runner exits non-zero
when any row fails.
"""
import io
import contextlib
import json
import pathlib
import sys
import types

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS_DIR.parent
for _p in (str(SCRIPTS), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import negative_fixtures as nf  # noqa: E402
import build_deck as bd  # noqa: E402
import run_signature_deck as rsd  # noqa: E402
import phase_verifiers as pv  # noqa: E402
import canonical_render_guard as guard  # noqa: E402
import qc_aggregate  # noqa: E402


def _stub_cc_oracle(monkeypatch, msg_id: str = "msg-777") -> None:
    """Stub the Command Center owner-message oracle so a record carrying
    owner_msg_id=msg_id RESOLVES (the positive control). sys.modules stub works
    for both pytest and the standalone runner."""
    stub = types.ModuleType("cc_board")
    stub.owner_message_ids_match = lambda run_dir, _x, env=None: frozenset({msg_id})
    stub.list_owner_message_ids = lambda task_id, env=None: frozenset({msg_id})
    monkeypatch.setitem(sys.modules, "cc_board", stub)


def _capture_stderr(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        out = fn(*a, **k)
    return out, buf.getvalue()


# ===========================================================================
# 1. FORGED APPROVAL — QC.md FIX 32
# ===========================================================================
class TestForgedApproval:
    def test_no_owner_msg_id_raises_forged_approval(self):
        """The live-E2E vector: owner_action-only record with NO owner_msg_id
        must raise ForgedApprovalError (AF-FORGED-APPROVAL), never authorize."""
        rd = nf.fixture_forged_approval()
        with pytest.raises(rsd.ForgedApprovalError, match="AF-FORGED-APPROVAL"):
            rsd.load_skip_approvals(rd)

    def test_unresolvable_owner_msg_id_denied_fail_closed(self):
        """Even WITH a msg id, if the CC oracle cannot prove it, the skip is
        DENIED — undetermined never opens the gate."""
        rd = nf.fixture_forged_approval(with_owner_msg_id=True,
                                        owner_msg_id="e2e-test-002")
        with pytest.raises(rsd.ForgedApprovalError, match="AF-FORGED-APPROVAL"):
            rsd.load_skip_approvals(rd)

    def test_verified_owner_msg_id_control_accepted(self, monkeypatch):
        """Positive control: same instrument, verified owner_msg_id -> ACCEPTED."""
        _stub_cc_oracle(monkeypatch)
        rd = nf.fixture_forged_approval(with_owner_msg_id=True,
                                        owner_msg_id="msg-777")
        approvals = rsd.load_skip_approvals(rd)
        assert approvals.get("P4-COPY", {}).get("phase_id") == "P4-COPY"

    def test_build_deck_preconditions_refuse_forged_record(self):
        """build_deck.check_phase_preconditions: the msg-id-less record prints
        AF-FORGED-APPROVAL and the phase STAYS REQUIRED (AF-PHASE-SKIPPED)."""
        rd = nf.fixture_forged_approval()
        out, err = _capture_stderr(bd.check_phase_preconditions, rd, "P4-RENDER", ["P4-COPY"])
        assert "AF-FORGED-APPROVAL" in err
        assert "AF-PHASE-SKIPPED" in out

    def test_phase_verifiers_refuse_self_minted_token(self):
        """A token found ONLY in process_manifest.json is a SELF-MINT:
        owner_skip_approval_authorizes returns None and names AF-FORGED-APPROVAL
        — even when quote/issuer/captured_at-shaped fields are present."""
        rd = nf.fixture_self_minted_skip_token()
        reasons: list = []
        w = pv.owner_skip_approval_authorizes("P8-ASSEMBLE", reasons, rd)
        assert w is None
        assert reasons and "AF-FORGED-APPROVAL" in reasons[0]

    def test_canonical_render_guard_malformed_token_authorizes_nothing(self):
        """canonical_render_guard: owner_approved not literal true -> the
        malformed token authorizes NOTHING."""
        rd = nf.fixture_malformed_guard_token()
        assert guard.load_owner_skip_approvals(rd) == {}

    def test_self_grant_marker_rejected(self, tmp_path, monkeypatch):
        """Extra FIX-32 hardening row: approved_by containing a self-grant
        marker ('builder') is rejected even before the oracle is consulted."""
        rec = {"phase_id": "P4-COPY", "owner_approved": True,
               "approved_by": "builder (executive strategy)",
               "owner_msg_id": "msg-1",
               "reason": "self-approved skip", "timestamp": nf.VALID_TS}
        (tmp_path / "working" / "checkpoints").mkdir(parents=True)
        (tmp_path / "working" / "checkpoints" / "phase_skip_approvals.json").write_text(
            json.dumps({"approvals": [rec]}), encoding="utf-8")
        _stub_cc_oracle(monkeypatch)  # oracle would accept the id; the marker must not
        approvals = rsd.load_skip_approvals(tmp_path)
        assert approvals == {}


# ===========================================================================
# 2. DARK NEGATION — QC.md FIX 35 / FIX 110
# ===========================================================================
class TestDarkNegation:
    def test_dark_request_fails_af_dark_slide(self):
        """Negative fixture: a prompt REQUESTING a dark background must FAIL
        AF-DARK-SLIDE (no client opt-in)."""
        rd = nf.fixture_dark_prompt(kind="request")
        out = bd._chk_no_dark_slides(rd)
        assert "AF-DARK-SLIDE" in out

    def test_light_prompt_control_passes(self):
        """Positive control: the light-background prompt PASSES on the same gate."""
        rd = nf.fixture_dark_prompt(kind="light")
        assert bd._chk_no_dark_slides(rd) == ""

    def test_client_dark_theme_optin_control_passes(self):
        """Positive control: dark REQUEST + explicit client_dark_theme:true
        PASSES (dark is opt-in by client request only)."""
        rd = nf.fixture_dark_prompt(kind="request", client_dark_theme=True)
        assert bd._chk_no_dark_slides(rd) == ""

    def test_dark_ok_alias_optin_control_passes(self):
        """Positive control: the role-doc alias DARK_OK:true is the SAME intent
        and PASSES the gate."""
        rd = nf.fixture_dark_prompt(kind="request", dark_ok_alias=True)
        assert bd._chk_no_dark_slides(rd) == ""

    def test_prohibition_block_is_the_negation_row(self):
        """The negation row: a prompt whose DO-NOT block only PROHIBITS dark
        ('no dark background anywhere') must NOT be read as a dark request.

        QC.md FIX 35: this prompt PASSES. W29b (FIX 110) landed: the scanner is
        negation-aware (presentation_job.scanners.scan_negation_aware via
        build_deck._chk_no_dark_slides), so the prohibition parses as a
        prohibition and the gate passes — while the dark REQUEST row above
        still fails on the same instrument. The prohibition phrased IN scanner
        vocabulary additionally earns the FIX-110 prompt lint: a staged warning
        (working/qc/staged_warnings.json, key prompt_prohibition_in_scanner_
        vocabulary) nudging positive art direction — warning only, never a
        gate. This is the flip the prior unlanded-W29b row promised."""
        rd = nf.fixture_dark_prompt(kind="prohibition")
        out, err = _capture_stderr(bd._chk_no_dark_slides, rd)
        prompt = (rd / "working" / "prompts" / "slide-01.txt").read_text()
        assert "no dark background anywhere" in prompt  # the fixture holds the negation
        assert out == ""  # FIX 110: the prohibition parses as a prohibition — PASS
        assert "AF-DARK-SLIDE" not in out
        # the ONLY dark mention in the fixture's positive block is inside DO-NOT:
        body = prompt.split("DO-NOT:")[0]
        assert "dark" not in body.lower()
        # the FIX-110 prompt lint fired on the same instrument (warning, not gate):
        staged = json.loads(
            (rd / "working" / "qc" / "staged_warnings.json").read_text())
        assert staged.get("prompt_prohibition_in_scanner_vocabulary", 0) >= 1

    def test_prohibition_without_scanner_vocab_is_silent(self):
        """A prohibition phrased in POSITIVE art direction ('render light
        backgrounds only' plus a DO-NOT in non-scanner words) passes with NO
        lint: the FIX-110 warning targets scanner vocabulary only."""
        rd = nf.fixture_dark_prompt(kind="prohibition")
        prompt_path = rd / "working" / "prompts" / "slide-01.txt"
        prompt_path.write_text(
            "SLIDE 1 IMAGE PROMPT\n\n"
            "Scene: a bright, airy conference room bathed in natural daylight; "
            "ivory walls, warm gold accents, open and energetic.\n\n"
            "DO-NOT:\n"
            "- render light backgrounds only; keep every panel luminous\n",
            encoding="utf-8")
        out, _ = _capture_stderr(bd._chk_no_dark_slides, rd)
        assert out == ""
        staged_file = rd / "working" / "qc" / "staged_warnings.json"
        assert not staged_file.exists(), (
            "positive-direction prohibition must earn NO lint")

    def test_dark_request_still_fails_after_negation_split(self):
        """Guard on the flip: the negation-aware scanner must not go soft — a
        prompt that REQUESTS dark in plain prose still FAILS on the same
        instrument the prohibition row just passed."""
        rd = nf.fixture_dark_prompt(kind="request")
        out = bd._chk_no_dark_slides(rd)
        assert "AF-DARK-SLIDE" in out


# ===========================================================================
# 3. SAME-MODEL JUDGE — QC.md FIX 33
# ===========================================================================
class TestSameModelJudge:
    def test_same_model_judge_blocks_image_domain(self):
        """Negative fixture: a report whose grader equals the authoring stamp
        (graded_by == built_by) BLOCKS the image domain with AF-QC-INDEPENDENCE
        and leaves the aggregate's gate-facing average null."""
        rd = nf.fixture_qc_reports(same_model_judge=True)
        report = qc_aggregate.aggregate(rd)
        img = report["domains"]["image"]
        assert any("AF-QC-INDEPENDENCE" in r for r in img["reasons"])
        assert report["average"] is None

    def test_self_graded_flag_blocks(self):
        """self_graded:true variant also BLOCKS."""
        rd = nf.fixture_qc_reports(same_model_judge=True, self_graded=True)
        report = qc_aggregate.aggregate(rd)
        assert any("AF-QC-INDEPENDENCE" in r for r in report["blocking_reasons"])

    def test_omitted_provenance_blocks(self):
        """A report that simply OMITS the provenance FAILS: independence is
        proven, not assumed."""
        rd = nf.fixture_qc_reports(same_model_judge=True, omit_provenance=True)
        report = qc_aggregate.aggregate(rd)
        assert any("AF-QC-INDEPENDENCE" in r for r in report["blocking_reasons"])

    def test_independent_judge_control_clean(self):
        """Positive control: same reports, grader a DIFFERENT model -> the
        image domain carries NO reasons."""
        rd = nf.fixture_qc_reports(same_model_judge=False)
        report = qc_aggregate.aggregate(rd)
        assert report["domains"]["image"]["reasons"] == []

    def test_independent_judge_full_set_passes(self):
        """Positive control at aggregate level: the full six-report set with an
        independent grader aggregates to a genuine pass."""
        rd = nf.fixture_qc_reports(same_model_judge=False, full_set=True)
        report = qc_aggregate.aggregate(rd)
        assert report["pass"] is True
        assert report["average"] == report["computed_average"]

    def test_qc_aggregate_exit_code_5_on_same_model_judge(self, tmp_path):
        """End-to-end row: qc_aggregate.main() exits 5 (BLOCKED) on the
        same-model-judge fixture and writes no fabricated average."""
        import subprocess
        rd = nf.fixture_qc_reports(same_model_judge=True)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "qc_aggregate.py"), "--run-dir", str(rd)],
            capture_output=True, text=True)
        assert proc.returncode == 5
        written = json.loads((rd / "working" / "qc" / "final_qc_report.json").read_text())
        assert written["average"] is None
        assert written["pass"] is False


# ===========================================================================
# 4. STYLISED-TYPE OCR WAIVER — ruling 9.11 / QC.md FIX 24
# ===========================================================================
class TestStylisedTypeOcrWaiver:
    def test_unwaived_mismatch_fails(self):
        """Negative fixture: slide 5 stylised type (checked:true, matched:false)
        FAILS check_ocr_readback naming '1 of 12' while no waiver is logged."""
        rd = nf.fixture_stylised_type_run_dir(waiver=False)
        out = bd.check_ocr_readback(rd)
        assert "AF-OCR-READBACK" in out
        assert "1 of 12" in out

    def test_logged_owner_skip_waives_by_design(self, monkeypatch):
        """The ruling-9.11(b) path: with a well-formed, ORACLE-VERIFIED
        AF-OCR-READBACK owner skip in process_manifest.json the SAME run
        PASSES by design. The waiver token carries an owner_msg_id (the
        Fix-32-authentic shape); the stubbed cc_board oracle proves the id
        resolves to a real owner-authored message."""
        _stub_cc_oracle(monkeypatch, msg_id="msg-ocr-waiver-001")
        rd = nf.fixture_stylised_type_run_dir(
            waiver=True, owner_msg_id="msg-ocr-waiver-001")
        out, err = _capture_stderr(bd.check_ocr_readback, rd)
        assert out == ""
        assert "WAIVED" in err or "waived" in err

    def test_waiver_without_resolvable_id_does_not_open_gate(self):
        """Fix-32 consistency row: the SAME stylised-type token whose
        owner_msg_id cannot be proven by any oracle (cc_board absent — the
        UNDETERMINED case) does NOT waive. Undetermined never opens a gate."""
        rd = nf.fixture_stylised_type_run_dir(
            waiver=True, owner_msg_id="msg-ocr-waiver-001")
        out = bd.check_ocr_readback(rd)
        assert "AF-OCR-READBACK" in out
        assert "1 of 12" in out

    def test_all_matched_control_passes_without_waiver(self):
        """Positive control: a clean 12-slide run (every sidecar matched) needs
        NO waiver and PASSES."""
        rd = nf.fixture_stylised_type_run_dir(mismatched_slides=(), waiver=False)
        assert bd.check_ocr_readback(rd) == ""

    def test_checked_false_never_waivable(self):
        """The non-waivable branch: checked:false means the OCR engine never
        ran. NO token — however well-formed — can waive it."""
        rd = nf.fixture_stylised_type_run_dir(checked=False, waiver=True)
        out = bd.check_ocr_readback(rd)
        assert "AF-OCR-READBACK" in out
        assert "NOT waivable" in out

    def test_missing_sidecar_fails(self, tmp_path):
        """A rendered PNG with NO sidecar FAILS (the engine's readback record
        is mandatory once PNGs exist)."""
        rd = nf.fixture_stylised_type_run_dir(waiver=True)
        (rd / "renders" / "slide-07.ocr.json").unlink()
        out = bd.check_ocr_readback(rd)
        assert "AF-OCR-READBACK" in out
        assert "missing or unreadable" in out

    def test_waiver_token_shape_is_well_formed(self):
        """Instrument check on the fixture itself: the written token satisfies
        _owner_skip_structurally_valid (owner_approved literal true, approved_by,
        >=8-char reason, parseable tz-aware timestamp)."""
        from pathlib import Path
        rd = nf.fixture_stylised_type_run_dir(waiver=True)
        obj = json.loads((rd / "working" / "checkpoints" / "process_manifest.json").read_text())
        rec = obj["owner_skip_approval"][0]
        ok, why = bd._owner_skip_structurally_valid(rec)
        assert ok, why
        assert rec["gate"] == "AF-OCR-READBACK"
        assert (rd / "renders" / "slide-05.ocr.json").exists()


if __name__ == "__main__":
    # Standalone entry: delegate to pytest (the fixtures need tmp_path /
    # monkeypatch fixtures). Exit code mirrors pytest's.
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
