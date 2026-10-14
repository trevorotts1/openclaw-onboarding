#!/usr/bin/env python3
"""S8 assembly integration tests (Item 29).

Covers the behavior that only exists once the stream builds are
composed: the Item 13 layout gate and its recorded waivers (S3
Requests 2/3), the production grade-calibration refusal at
image-generation-qc close (S2 GCR-1), the {copy_version} gate
placeholder (S4 CR-2 with CR-1's fail-closed rule), the Item 28 step 3
transport alias for claude-nine runs, and the Item 24/25 run-events
feed plus REPORT.json twin (S6's gate-side emission spec, implemented
at integration).

Event lines and REPORT.json are validated against the frozen schemas
when the jsonschema package is available; otherwise the same checks
run structurally (required keys, enum membership). The Docker test
image spec (tests/docker/Dockerfile) pins jsonschema so CI always
takes the full path.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PY = sys.executable
sys.path.insert(0, str(SCRIPTS))

import stage_gate as gate  # noqa: E402

try:
    import jsonschema
except Exception:
    jsonschema = None


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def validate(instance, schema_name):
    schema = json.loads((ROOT / "references" / schema_name).read_text())
    if jsonschema is not None:
        jsonschema.validate(instance, schema)
    else:
        for key in schema.get("required", []):
            assert key in instance, f"{schema_name}: missing required {key}"


def fixture_brand(run, grade=None):
    write(run / "private" / "brand.json", json.dumps({
        "fonts": {"display": "Test", "body": "Test", "accent": "Test"},
        "logo": {"files": "test.png", "masthead_files": "test.png"},
        "founder_photos": "test.png",
        "grade": grade if grade is not None else {},
    }))


def fixture_intake(run, **over):
    data = {"page_version": "standard", "brand_owner": "blackceo",
            "brand_file": "private/brand.json", "creative_direction": None,
            "image_cap": 2, "test_run": True, "image_engine": "kie",
            "copy_version": "standard"}
    data.update(over)
    write(run / "intake.json", json.dumps(data))
    return data


def put_receipt(run, stage, **over):
    r = {"stage": stage, "status": "pass", "author_agent": "builder-agent",
         "reviewer_agent": "reviewer-agent",
         "started_at": "2026-10-05T10:00:00+00:00",
         "finished_at": "2026-10-05T10:30:00+00:00",
         "artifacts": [], "notes": "fixture"}
    r.update(over)
    write(run / "private" / "receipts" / f"{stage}.json", json.dumps(r))


def run_gate(*args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([PY, str(SCRIPTS / "stage_gate.py"), *args],
                          text=True, capture_output=True, env=e)


def events_of(run):
    path = run / "private" / "run-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------- layout gate

def test_layout_gate_failures_and_waivers():
    missing = [n for n in gate.LAYOUT_REFERENCE_FILES
               if not (gate.SKILL_ROOT / "assets" / "page-references" / n).is_file()]
    assert missing, "precondition: the owner-supplied references are absent here"
    with tempfile.TemporaryDirectory() as td:
        run = Path(td)
        fixture_intake(run)
        failures = gate.layout_gate_failures(run)
        assert failures and "missing layout reference" in failures[0], failures
        fixture_intake(run, layout_waivers=[{"gate": "layout-references",
                                             "reason": "owner waived for this run"}])
        assert gate.layout_gate_failures(run) == []
        fixture_intake(run, layout_references_waived=True,
                       layout_references_waiver_reason="owner waived, flat form")
        assert gate.layout_gate_failures(run) == []
        fixture_intake(run, layout_waivers=[{"gate": "layout-references",
                                             "reason": "  "}])
        assert gate.layout_gate_failures(run), "a waiver without a reason is not a waiver"


# ------------------------------------------------------------- grade calibrated

def test_grade_calibrated_builtin():
    with tempfile.TemporaryDirectory() as td:
        run = Path(td)
        fixture_brand(run, grade={"min_mean_saturation": None, "min_luma_std": None})
        fixture_intake(run, test_run=False)
        out = gate.run_builtin("gate:grade_calibrated", [], run)
        assert out and "uncalibrated" in out, out
        fixture_intake(run, test_run=True)
        assert gate.run_builtin("gate:grade_calibrated", [], run) is None
        fixture_intake(run, test_run=False)
        fixture_brand(run, grade={"min_mean_saturation": 0.1, "min_luma_std": 5.0})
        assert gate.run_builtin("gate:grade_calibrated", [], run) is None


# -------------------------------------------------------------- copy_version

def test_copy_version_placeholder():
    cmd = ("python3 scripts/validate_copy_structure.py {run_dir} "
           "--spec references/copy-specs/{copy_version}-v6.json")
    with tempfile.TemporaryDirectory() as td:
        run = Path(td)
        fixture_intake(run, copy_version="long-form")
        resolved, lines = gate.resolve_brand_placeholder(cmd, run, "copy", None)
        assert lines == [] and "long-form-v6.json" in resolved, (resolved, lines)
        data = json.loads((run / "intake.json").read_text())
        del data["copy_version"]
        write(run / "intake.json", json.dumps(data))
        resolved, lines = gate.resolve_brand_placeholder(cmd, run, "copy", None)
        assert resolved is None and any("copy_version" in l for l in lines), lines


# -------------------------------------------------------------- transport alias

def _alias_run(td, runtime):
    run = Path(td)
    fixture_intake(run, runtime=runtime)
    write(run / "image-generation-qc" / "Image-001.png", "stub")
    task = {"file": "image-generation-qc/Image-001.png", "task_id": "task-001",
            "model_id": "model-from-skill-66", "model_source": "latest-family",
            "requested_ratio": "16:9", "generated_ratio": "16:9",
            "preflight_ok": True, "budget_exit": 0}
    write(run / "receipts" / "kie74" / "task-001.json", json.dumps({
        "provider": "kie", "adapter": "kie", "task_id": "task-001",
        "state": "success", "saved_paths": [task["file"]], "warnings": [], "data": {}}))
    receipt = {"transport": {"skill": "kie", "policy": "kie", "tasks": [task]},
               "cost": {"provider": "kie", "credits_before": 10.0, "credits_after": 9.0}}
    return run, receipt


def test_transport_alias_claude_nine():
    with tempfile.TemporaryDirectory() as td:
        run, receipt = _alias_run(td, "claude-nine")
        problems = gate.check_transport(run, "image-generation-qc", receipt)
        assert problems == [], problems
    with tempfile.TemporaryDirectory() as td:
        run, receipt = _alias_run(td, None)
        problems = gate.check_transport(run, "image-generation-qc", receipt)
        assert problems and "not an approved route" in problems[0], problems
    with tempfile.TemporaryDirectory() as td:
        run, receipt = _alias_run(td, "claude-nine")
        receipt["transport"]["tasks"][0]["preflight_ok"] = False
        problems = gate.check_transport(run, "image-generation-qc", receipt)
        assert any("preflight_ok" in p for p in problems), problems
    with tempfile.TemporaryDirectory() as td:
        # The generated 999 policy names the pin a user pin: validation
        # maps it onto the department-pin rule (evidence required)
        # while the stored receipt keeps "user-pin".
        run, receipt = _alias_run(td, "claude-nine")
        task = receipt["transport"]["tasks"][0]
        task["model_source"] = "user-pin"
        task["evidence"] = "user pin recorded at intake"
        problems = gate.check_transport(run, "image-generation-qc", receipt)
        assert problems == [], problems
        assert task["model_source"] == "user-pin"


# ------------------------------------------------------- events + REPORT.json

def test_events_and_report_twin():
    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run"
        run.mkdir(parents=True)
        fixture_brand(run)
        fixture_intake(run)
        proc = run_gate("init", str(run))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        state = json.loads((run / "private" / "state.json").read_text())
        assert state.get("run_id"), "cmd_init must mint run_id"
        put_receipt(run, "intake")
        proc = run_gate("close", str(run), "intake")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        proc = run_gate("report", str(run))
        assert proc.returncode == 1, "report on an incomplete run exits 1"
        assert (run / "REPORT.md").exists() and (run / "REPORT.json").exists()
        md = (run / "REPORT.md").read_text()
        assert "Structured twin: REPORT.json" in md
        twin = json.loads((run / "REPORT.json").read_text())
        validate(twin, "report-json.schema.json")
        assert twin["run_id"] == state["run_id"]
        assert twin["overall"] == "test-run"  # fixture intake is a test run
        assert len(twin["stages"]) == 14
        intake_row = [s for s in twin["stages"] if s["stage"] == "intake"][0]
        assert intake_row["status"] == "PASS"
        assert intake_row["duration_s"] == 1800
        evs = events_of(run)
        types = [e["event_type"] for e in evs]
        assert types[0] == "run_initialized", types
        assert "stage_closed" in types and "report_generated" in types, types
        for e in evs:
            validate(e, "run-events.schema.json")
            assert e["run_id"] == state["run_id"]
        closed = [e for e in evs if e["event_type"] == "stage_closed"][0]
        assert closed["stage"] == "intake" and closed["receipt_status"] == "pass"
        assert closed["duration_s"] == 1800
        # Re-running init on an existing run emits nothing new.
        before = len(evs)
        proc = run_gate("init", str(run))
        assert proc.returncode == 0
        assert len(events_of(run)) == before


def test_stage_blocked_event():
    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run"
        run.mkdir(parents=True)
        fixture_brand(run)
        fixture_intake(run)
        assert run_gate("init", str(run)).returncode == 0
        # No receipt for copy: the close is refused and the refusal is
        # emitted as stage_blocked with the gate's failure lines.
        proc = run_gate("close", str(run), "copy")
        assert proc.returncode == 1
        blocked = [e for e in events_of(run) if e["event_type"] == "stage_blocked"]
        assert blocked and blocked[0]["stage"] == "copy" and blocked[0]["failures"], blocked
        validate(blocked[0], "run-events.schema.json")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"ALL PASS: {len(fns)} assembly integration tests")
