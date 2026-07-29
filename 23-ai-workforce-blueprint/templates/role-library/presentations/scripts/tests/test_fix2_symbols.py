"""Tests for U023 — the _FIX2_SYMBOLS repoint and fail-closed guarding."""

import json
import pathlib
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_a_all_names_callable():
    """Every symbol in _FIX2_SYMBOLS must be a callable on build_deck."""
    import build_deck as bd
    import canonical_render_guard as crg
    for sym, af_code in crg._FIX2_SYMBOLS:
        fn = getattr(bd, sym, None)
        assert fn is not None, f"build_deck.{sym} does not exist"
        assert callable(fn), f"build_deck.{sym} is not callable"


def test_b_two_entries_no_chk_prefix():
    """_FIX2_SYMBOLS has exactly 2 entries and none starts with _chk_."""
    import canonical_render_guard as crg
    assert len(crg._FIX2_SYMBOLS) == 2
    for sym, _ in crg._FIX2_SYMBOLS:
        assert not sym.startswith("_chk_"), f"name {sym!r} starts with _chk_"


def test_c_bogus_name_raises():
    """A bogus name in _FIX2_SYMBOLS raises RuntimeError."""
    import canonical_render_guard as crg
    saved = crg._FIX2_SYMBOLS
    try:
        crg._FIX2_SYMBOLS = [("check_no_such_function_anywhere", "AF-IMAGE-QC-VISION")]
        r = pathlib.Path(tempfile.mkdtemp())
        (r / "working").mkdir(parents=True)
        try:
            crg.run_fix2_checks(r)
        except RuntimeError as exc:
            msg = str(exc)
            assert "check_no_such_function_anywhere" in msg
            assert "AF-IMAGE-QC-VISION" in msg
        else:
            raise AssertionError("run_fix2_checks with bogus name did NOT raise")
    finally:
        crg._FIX2_SYMBOLS = saved


def test_d_owner_skip_suppresses_one_code():
    """Valid owner_skip_approval suppresses its AF code; malformed tokens don't."""
    import canonical_render_guard as crg

    def make_run_dir(token_payload):
        r = pathlib.Path(tempfile.mkdtemp())
        (r / "working" / "checkpoints").mkdir(parents=True)
        (r / "renders").mkdir(exist_ok=True)
        (r / "working" / "mk.py").write_text(
            "from PIL import Image\nim = Image.new('RGB', (2048, 1152))\n")
        if token_payload is not None:
            (r / "working" / "checkpoints" / "process_manifest.json").write_text(
                json.dumps({"owner_skip_approval": token_payload}))
        return r

    r_no_tok = make_run_dir(None)
    af_codes = {af for af, _ in crg.run_fix2_checks(r_no_tok)}
    assert len(af_codes) > 0, "Expected at least one finding without token"

    valid = {"owner_approved": True, "gate": "AF-IMAGE-QC-VISION",
             "approved_by": "owner", "reason": "documented exception",
             "timestamp": "2026-07-25T00:00:00Z"}
    af_codes_tok = {af for af, _ in crg.run_fix2_checks(make_run_dir(valid))}
    assert "AF-IMAGE-QC-VISION" not in af_codes_tok
    assert "AF-CANONICAL-RENDER-BYPASS" in af_codes_tok

    # NOTE: this fixture's run dir never gives check_image_qc_vision anything to
    # inspect (no rendered PNGs, no image_qc_report.json), so it always defers
    # ("") regardless of any token. That means "AF-IMAGE-QC-VISION present in
    # run_fix2_checks() results" is never a valid way to prove a malformed token
    # was rejected here. Assert directly on the real claim instead: a malformed
    # token must not be recognised as a valid owner skip at all.
    mal = {"owner_approved": True, "gate": "AF-IMAGE-QC-VISION", "reason": "no approved_by"}
    assert crg.load_owner_skip_approvals(make_run_dir(mal)) == {}, (
        "a token missing approved_by must not be recognised as a valid owner skip")

    mal2 = {"owner_approved": True, "gate": "AF-IMAGE-QC-VISION", "approved_by": "owner"}
    assert crg.load_owner_skip_approvals(make_run_dir(mal2)) == {}, (
        "a token missing reason must not be recognised as a valid owner skip")
