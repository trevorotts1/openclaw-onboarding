"""U013 gate tests."""
import ast, importlib, json, sys, pathlib, tempfile, pytest
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
from presentation_job.gates import (
    Gates, GATE_KEYS, NON_WAIVABLE_GATES, WARN_ONLY_GATES, ALL_GATE_KEYS,
    _MIN_BYTES as GATES_MIN_BYTES,
)
from presentation_job.result import CheckResult
from presentation_job.waivers import WaiverError, load_waivers, validate_waiver
from phase_verifiers import verify

def _rd(): return pathlib.Path(tempfile.mkdtemp())
def _w(rd, rel, content):
    p = rd / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8"); return p
def _wj(rd, rel, obj): return _w(rd, rel, json.dumps(obj))

def test_ghl_gate_passes_on_good_media():
    src = ast.parse((SCRIPTS / "ghl_media_push.py").read_text())
    good = next(ast.literal_eval(n.value) for n in ast.walk(src)
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "GOOD_MEDIA" for t in n.targets))
    rd = _rd(); _wj(rd, "working/checkpoints/media_library.json", good)
    r = Gates(rd, {})._ghl_gate()
    assert r["state"] == "pass", str(r)
    assert r["ghl_folder_id"] == "fld_123"
    assert r["pptx_ghl_media_id"] == "pptx_9"

def test_ghl_gate_fails_on_old_key():
    rd = _rd(); _wj(rd, "working/checkpoints/media_library.json", {"media_ids": ["a", "b"]})
    r = Gates(rd, {})._ghl_gate()
    assert r["state"] == "fail", str(r)

def test_ghl_gate_fails_without_pptx():
    rd = _rd(); _wj(rd, "working/checkpoints/media_library.json",
        {"ghl_folder_id": "fld", "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"}]})
    r = Gates(rd, {})._ghl_gate()
    assert r["state"] == "fail"
    assert "pptx_ghl_media_id" in r.get("reason", "")

def test_ghl_gate_reports_partial_upload():
    rd = _rd(); _wj(rd, "working/checkpoints/media_library.json",
        {"ghl_folder_id": "fld", "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "pending"}],
         "pptx_ghl_media_id": "p9"})
    r = Gates(rd, {})._ghl_gate()
    assert r["state"] == "fail"
    assert "1 of 2" in r.get("reason", "")

def test_script_gate_both_paths():
    rd = _rd(); _w(rd, "working/deliverables/PRESENTERS-SPEECH.md", "x" * 3000)
    g = Gates(rd, {}).evaluate_all(); assert g["script"]["state"] == "pass"
    rd2 = _rd(); _w(rd2, "working/presenter-speech/PRESENTERS-SPEECH.md", "x" * 3000)
    g2 = Gates(rd2, {}).evaluate_all(); assert g2["script"]["state"] == "pass"

def test_prompt_floor_names_short_file():
    rd = _rd(); _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
    _w(rd, "working/prompts/slide-02.txt", "q" * 8999)
    g = Gates(rd, {}).evaluate_all()
    assert g["prompt_floor"]["state"] == "fail"
    r = g["prompt_floor"].get("reason", "")
    assert "8999" in r and "slide-02" in r


class TestCanonicalPromptDirProblemsThreeValued:
    """B4-1 acceptance. _canonical_prompt_dir_problems() used to `return []` when
    BOTH the build_deck route and the shared prompt_gate fallback failed --
    identical to "checked, no duplicates". Now it returns
    (CheckResult.UNDETERMINED, []) instead, and the prompt_floor gate refuses
    rather than passing on that verdict."""

    def _boom_build_deck(self, monkeypatch):
        """Simulate the build_deck import route failing, forcing the function
        into its except branch (its documented, real fallback path)."""
        real_import_module = importlib.import_module
        def _raise_for_build_deck(name, *a, **kw):
            if name == "build_deck":
                raise ImportError("simulated build_deck import failure")
            return real_import_module(name, *a, **kw)
        monkeypatch.setattr(importlib, "import_module", _raise_for_build_deck)

    def test_good_clean_dir_is_pass_with_no_problems(self):
        """GOOD control: canonical, non-duplicate prompt files -> PASS, []."""
        rd = _rd(); _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
        result, problems = Gates(rd, {})._canonical_prompt_dir_problems()
        assert result is CheckResult.PASS
        assert problems == []

    def test_bad_real_duplicate_is_fail_with_problems_listed(self):
        """BAD control: a genuine slide-1.txt/slide-01.txt collision (D16) ->
        FAIL, with the collision named in the problem list. Detector runs
        successfully end-to-end here -- nothing simulated."""
        rd = _rd()
        _w(rd, "working/prompts/slide-1.txt", "p" * 9500)
        _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
        result, problems = Gates(rd, {})._canonical_prompt_dir_problems()
        assert result is CheckResult.FAIL
        assert problems, "a real duplicate must produce at least one problem string"
        assert any("DUP-FILE" in p for p in problems)
        # And the gate built on top of this must actually block:
        gate = Gates(rd, {})._prompt_floor_gate()
        assert gate["state"] == "fail"

    def test_unknowable_both_fallbacks_failing_is_undetermined_not_pass(self, monkeypatch):
        """THE regression proof. build_deck import raises AND the shared
        prompt_gate fallback is unavailable (_prompt_gate() -> None) -- the
        exact double-fallback-failure shape the sweep found. Must be
        UNDETERMINED, never PASS, and never silently equal to the GOOD case's
        (PASS, [])."""
        rd = _rd(); _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
        self._boom_build_deck(monkeypatch)
        g = Gates(rd, {})
        monkeypatch.setattr(g, "_prompt_gate", lambda: None)
        result, problems = g._canonical_prompt_dir_problems()
        assert result is CheckResult.UNDETERMINED
        assert result is not CheckResult.PASS
        assert problems == []

    def test_unknowable_detector_no_longer_reads_as_a_pass_at_the_gate_level(self, monkeypatch):
        """The same UNDETERMINED case, but observed through the public gate
        this feeds: _prompt_floor_gate(). The prompt files here are otherwise
        entirely legitimate (long enough, canonically named) -- with a working
        detector this would PASS. Because the duplicate/name detector itself
        could not run, the gate must refuse (state=fail), not silently pass a
        deck it never actually checked for D16 collisions."""
        rd = _rd(); _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
        self._boom_build_deck(monkeypatch)
        g = Gates(rd, {})
        monkeypatch.setattr(g, "_prompt_gate", lambda: None)
        gate = g._prompt_floor_gate()
        assert gate["state"] == "fail", (
            "a security/completeness gate must refuse when it could not check, "
            f"got: {gate}"
        )
        assert "could not run" in gate["reason"] or "UNDETERMINED" in gate["reason"]

    def test_only_prompt_gate_fallback_failing_is_also_undetermined(self, monkeypatch):
        """Second way to reach UNDETERMINED: build_deck import raises AND the
        recovered prompt_gate module's own detector call raises too (not just
        _prompt_gate() returning None). Must still be UNDETERMINED, not an
        uncaught exception and not a silent pass."""
        rd = _rd(); _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
        self._boom_build_deck(monkeypatch)
        g = Gates(rd, {})
        class _BoomingPromptGate:
            def prompt_dir_problems(self, _dir):
                raise RuntimeError("simulated shared prompt_gate failure")
        monkeypatch.setattr(g, "_prompt_gate", lambda: _BoomingPromptGate())
        result, problems = g._canonical_prompt_dir_problems()
        assert result is CheckResult.UNDETERMINED
        assert problems == []

def test_all_gates_fail_on_empty_dir():
    rd = _rd(); (rd / "working").mkdir(parents=True, exist_ok=True)
    gates = Gates(rd, {}).evaluate_all()
    f = [k for k in ALL_GATE_KEYS if gates.get(k, {}).get("state") != "pass"
         and not gates.get(k, {}).get("warn_only", False)]
    assert len(f) >= 4, f"expected >=4 failures, got {len(f)}"

def test_no_gate_is_warn_only_anymore():
    # WARN_ONLY_GATES used to carry both ocr_readback and, later, qc alone -- both were
    # fixed to fail-closed (see gates.py's WARN_ONLY_GATES comment and CHANGELOG
    # [Unreleased] qc-gate-fail-closed). This is a regression guard: the tuple must stay
    # empty, and every gate this fixture satisfies for real (including a genuine passing
    # final_qc_report.json) must show up as a hard pass with warn_only False.
    assert WARN_ONLY_GATES == (), (
        "a gate was added back to WARN_ONLY_GATES -- see D10: a check that defers "
        "because its input is missing is a fail-open wearing a fail-closed label")
    rd = _rd(); (rd / "working" / "deliverables").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "prompts").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "qc").mkdir(parents=True, exist_ok=True)
    (rd / "renders").mkdir(parents=True, exist_ok=True)
    _w(rd, "working/deliverables/PRESENTERS-SPEECH.md", "x" * 3000)
    # RECONCILED (split-brain fix, 2026-08-18): was a hardcoded "y" * 12000 -- a real
    # teleprompter render is never that small (build_teleprompter.py's own template is
    # ~40KB before any speech content), and 12000 only ever passed this gate because
    # gates.py's floor was itself a stale 10_240. Derived from the same spec the gate
    # now reads, with headroom, so this fixture tracks the doctrine floor instead of
    # drifting back to an arbitrary undersized stub.
    _w(rd, "working/deliverables/presenter-teleprompter.html",
       "y" * (GATES_MIN_BYTES["teleprompter_html"] + 1000))
    _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
    _wj(rd, "working/checkpoints/media_library.json",
        {"ghl_folder_id": "root", "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"}], "pptx_ghl_media_id": "p9"})
    _wj(rd, "renders/slide-01.ocr.json", {"checked": True, "matched": True})
    _wj(rd, "working/qc/final_qc_report.json", {"average": 9.0})
    gates = Gates(rd, {}).evaluate_all()
    assert gates["ocr_readback"]["state"] == "pass", gates["ocr_readback"]
    assert gates["qc"]["state"] == "pass", gates["qc"]
    assert gates["qc"]["warn_only"] is False
    f = [k for k in ALL_GATE_KEYS if gates.get(k, {}).get("state") != "pass"
         and not gates.get(k, {}).get("warn_only", False)]
    assert len(f) == 0, f"all hard gates should pass, got {f}"

def test_qc_gate_missing_report_is_hard_failure_not_warn_only():
    """The exact scenario the fail-open bug describes: no phase ever writes
    working/qc/final_qc_report.json. This must BLOCK (D10), never defer to a
    non-blocking warning."""
    rd = _rd()
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False, "a missing QC report must not be warn-only -- it must block"
    assert "qc" not in WARN_ONLY_GATES

def test_qc_gate_unreadable_report_is_hard_failure():
    rd = _rd(); _w(rd, "working/qc/final_qc_report.json", "{not valid json")
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False

def test_qc_gate_no_numeric_score_is_hard_failure():
    rd = _rd(); _wj(rd, "working/qc/final_qc_report.json", {"notes": "looks fine to me"})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False

def test_qc_gate_below_threshold_is_hard_failure():
    rd = _rd(); _wj(rd, "working/qc/final_qc_report.json", {"average": 7.9})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False
    assert "7.9" in g["reason"]

def test_qc_gate_passes_on_genuine_report_at_or_above_threshold():
    rd = _rd(); _wj(rd, "working/qc/final_qc_report.json", {"average": 8.5})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "pass", g
    assert g["warn_only"] is False
    assert g["score"] == 8.5

def test_qc_gate_surfaces_blocking_reasons_from_the_aggregator():
    """qc_aggregate.py (P-QC-AGGREGATE) writes final_qc_report.json with a
    null "average" and a "blocking_reasons" list naming exactly which domain is
    missing/untrusted/sub-threshold when it cannot honestly certify a pass. The
    gate must fold that detail into its own reason -- purely additive: a report
    with no blocking_reasons key (every OTHER fixture in this file) is unaffected,
    proven by test_qc_gate_below_threshold_is_hard_failure and
    test_qc_gate_no_numeric_score_is_hard_failure above still passing verbatim."""
    rd = _rd()
    _wj(rd, "working/qc/final_qc_report.json", {
        "average": None,
        "blocking_reasons": ["Speech QC (P-SPEECH-QC): missing domain report at "
                             "working/qc/speech_qc_report.json"],
    })
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False
    assert "speech_qc_report.json" in g["reason"], g["reason"]
    assert "P-SPEECH-QC" in g["reason"], g["reason"]

def test_qc_gate_blocking_reasons_do_not_leak_into_a_passing_score():
    """blocking_reasons is diagnostic detail for a FAILING report -- it must never
    turn a genuinely passing numeric score into anything other than a pass."""
    rd = _rd()
    _wj(rd, "working/qc/final_qc_report.json",
        {"average": 9.1, "blocking_reasons": []})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "pass", g
    assert g["score"] == 9.1

def test_qc_is_waivable_with_genuine_client_quote():
    """Unlike ocr_readback, qc stays in GATE_KEYS -- a client-quoted waiver (validated by
    waivers.py against the client's own recorded words) is the ONLY bypass. This is not
    weakened by the fail-closed fix."""
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"skip_qc": "Please skip the QC check for this run."})
    w = {"rule": "qc", "source": "intake_field", "intake_field": "skip_qc",
         "client_request_quote": "skip the QC check", "captured_at": "2026-01-01T00:00:00Z"}
    validate_waiver(w, rd)  # must not raise
    assert "qc" not in NON_WAIVABLE_GATES

def test_ocr_readback_unchecked_is_hard_failure_not_warn_only():
    """MASTER-SPEC 7.4 / D10: an unchecked readback BLOCKS -- it must never be routed
    into the warn-only path. Regression guard for the WARN_ONLY_GATES contradiction."""
    rd = _rd(); (rd / "renders").mkdir(parents=True, exist_ok=True)
    _wj(rd, "renders/slide-01.ocr.json", {"checked": False, "matched": None})
    g = Gates(rd, {})._ocr_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False, "an unchecked readback must not be warn-only -- it must block"
    assert "ocr_readback" not in WARN_ONLY_GATES

def test_ocr_readback_no_sidecars_is_hard_failure_not_warn_only():
    """The zero-sidecar case (no phase ever produced renders/slide-*.ocr.json) must also
    block -- 'unverifiable' fails closed (D10), it does not defer to a silent pass."""
    rd = _rd()
    g = Gates(rd, {})._ocr_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False

def test_ocr_readback_mismatch_is_hard_failure_not_warn_only():
    rd = _rd(); (rd / "renders").mkdir(parents=True, exist_ok=True)
    _wj(rd, "renders/slide-01.ocr.json", {"checked": True, "matched": False, "misses": ["X"]})
    g = Gates(rd, {})._ocr_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False

def test_ocr_is_non_waivable():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"x": True})
    w = {"rule": "ocr_readback", "source": "intake_field", "intake_field": "x",
         "client_request_quote": "I waive OCR readback", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError): validate_waiver(w, rd)

def test_short_waiver_quote_rejected():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"f": True})
    w = {"rule": "teleprompter", "source": "intake_field", "intake_field": "f",
         "client_request_quote": "ok", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError): validate_waiver(w, rd)

def test_duplicate_waivers_rejected():
    rd = _rd(); _wj(rd, "waivers.json", [
        {"rule": "qc", "source": "intake_field", "intake_field": "f1",
         "client_request_quote": "skip QC", "captured_at": "2026-01-01T00:00:00Z"},
        {"rule": "qc", "source": "intake_field", "intake_field": "f2",
         "client_request_quote": "skip again", "captured_at": "2026-01-01T00:00:01Z"}])
    with pytest.raises(WaiverError, match="(?i)two waivers"): load_waivers(rd)

def test_valid_intake_waiver_loads():
    # The quote must genuinely appear in the intake field's recorded value —
    # a bare presence check on a boolean flag is the defect this guards against.
    rd = _rd()
    _wj(rd, "working/copy/intake.json", {"skip_qc": "Please skip the QC check for this run."})
    _wj(rd, "waivers.json", [{"rule": "qc", "source": "intake_field", "intake_field": "skip_qc",
        "client_request_quote": "skip the QC check", "captured_at": "2026-01-01T00:00:00Z"}])
    waivers = load_waivers(rd)
    validate_waiver(waivers[0], rd)
    wk = {w.get("rule") for w in waivers if w.get("rule")}
    assert "qc" in wk
    gates = Gates(rd, {}).evaluate_all()
    g = gates.get("qc", {})
    if "qc" in wk:
        g["state"] = "waived"
    assert g["state"] == "waived"

def test_gate_keys_non_overlap():
    assert not (set(GATE_KEYS) & set(NON_WAIVABLE_GATES))

def test_verify_unregistered_phase_fails(tmp_path):
    ok, reasons = verify("P-NOT-A-PHASE", tmp_path)
    assert ok is False
    assert any("P-NOT-A-PHASE" in r for r in reasons)

def test_verify_raises_fails(tmp_path):
    import phase_verifiers as pv_mod
    pv_mod.PHASE_VERIFIERS["P-TEST-RAISE"] = lambda rd: (_ for _ in ()).throw(RuntimeError("boom"))
    ok, reasons = pv_mod.verify("P-TEST-RAISE", tmp_path)
    assert ok is False
    assert any("RuntimeError" in r or "boom" in r for r in reasons)
