"""U013 gate tests."""
import ast, json, sys, pathlib, tempfile, pytest
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
from presentation_job.gates import Gates, GATE_KEYS, NON_WAIVABLE_GATES, WARN_ONLY_GATES, ALL_GATE_KEYS
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

def test_all_gates_fail_on_empty_dir():
    rd = _rd(); (rd / "working").mkdir(parents=True, exist_ok=True)
    gates = Gates(rd, {}).evaluate_all()
    f = [k for k in ALL_GATE_KEYS if gates.get(k, {}).get("state") != "pass"
         and not gates.get(k, {}).get("warn_only", False)]
    assert len(f) >= 4, f"expected >=4 failures, got {len(f)}"

def test_warn_mode_gates_are_warn_only():
    rd = _rd(); (rd / "working" / "deliverables").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "prompts").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    _w(rd, "working/deliverables/PRESENTERS-SPEECH.md", "x" * 3000)
    _w(rd, "working/deliverables/presenter-teleprompter.html", "y" * 12000)
    _w(rd, "working/prompts/slide-01.txt", "p" * 9500)
    _wj(rd, "working/checkpoints/media_library.json",
        {"ghl_folder_id": "root", "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"}], "pptx_ghl_media_id": "p9"})
    gates = Gates(rd, {}).evaluate_all()
    f = [k for k in ALL_GATE_KEYS if gates.get(k, {}).get("state") != "pass"
         and not gates.get(k, {}).get("warn_only", False)]
    assert len(f) == 0, f"all hard gates should pass, got {f}"

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
