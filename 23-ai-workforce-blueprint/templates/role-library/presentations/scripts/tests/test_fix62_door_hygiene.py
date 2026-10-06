"""FIX 62 QC gate — door hygiene (W14, R4 §H.4-5).

Proof (verbatim from QC.md; the critic runs exactly this):
  Three failed gate invocations then one passing invocation do not hit the
  attempts cap; `--plan` does not increment it; `cc_post` import is gone.

The three mechanisms:
  1. ATTEMPT BUMP IS POST-GATE — a run that dies on any gate exits with the
     budget untouched, so gate-repair cycles never burn the cap. The bump
     happens only after "ALL GATES PASSED", and only when PLAN=0.
  2. RESET ON SUCCESS — a build whose engine exits 0 clears the counter, so
     the next deck in the same run dir starts from a fresh budget.
  3. --plan IS EXEMPT FROM EVERY SIDE EFFECT — it never reaches the bump and
     never stamps pre_presentation_capture.STANDARD_MODE (read-only contract).
  4. DEAD cc_post IMPORT REMOVED — the sync_drift_deferred event posts inline
     (env-based config contract, best-effort) instead of importing a symbol
     that never existed in any cc_board.py copy.

No grep anywhere. Targeted python only, hermetic (fake scripts dir + stub
engine, the same fixture contract test_fix23_door_reliability.py uses).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent  # .../presentations/scripts
# Deployed tree first (scripts/presentation-canonical-entry.sh), repo-checkout
# fallback — mirrors test_fix23_door_reliability.py's resolution.
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO
assert ENTRY.is_file(), f"canonical entry script not found ({ENTRY})"

# ---------------------------------------------------------------------------
# Fixtures: a run dir that satisfies GATE 0/0b, and a fake SCRIPTS_DIR whose
# stub engine exits with a chosen code. Gates 0c/1/1b/2/3 pass under the QC
# test-context contract (QC_SKIP_PRESENTATION_DEPS=1 + .test-context marker).
# ---------------------------------------------------------------------------
def make_run_dir(base: Path) -> Path:
    run_dir = base / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "checkpoints" / ".test-context").write_text("")
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True}))
    (run_dir / "working" / "interview" / "intake_transcript.json").write_text(
        json.dumps({"driver": "deck-intake-driver", "signature": "signed",
                    "turns": [{"q": "What topic?", "a": "A long enough answer " * 40}] * 10}))
    (run_dir / "slides.json").write_text("{}")
    return run_dir


def make_scripts_dir(base: Path, engine_rc: int = 0) -> Path:
    d = base / f"fake-scripts-{engine_rc}"
    d.mkdir(exist_ok=True)
    (d / "build_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "run_signature_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "presentation_job.py").write_text(
        "import sys\n"
        "if '--new' in sys.argv:\n"
        "    sys.exit(0)   # --new must succeed (state.json job creation)\n"
        f"sys.exit({engine_rc})   # --run/--resume exits with the chosen code\n")
    (d / "presentation_job").mkdir(exist_ok=True)
    (d / "presentation_job" / "resolve_intake.py").write_text(
        "import argparse, json, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--ledger'); p.add_argument('--out'); p.add_argument('--source')\n"
        "p.add_argument('--intake-depth', default=None)\n"
        "a = p.parse_args()\n"
        "json.dump({'presentation_type': 'signature_presentation'}, open(a.out, 'w'))\n"
        "print('intake resolved')\n"
        "sys.exit(0)\n")
    (d / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\n"
        "def list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n")
    (d / "sync_check.py").write_text(
        "import json, sys\n"
        "print(json.dumps({'in_sync': True, 'manifest_version': 39, 'drift': [],\n"
        "                  'drift_summary': {'total': 0, 'render_path': 0, 'library_only': 0}}))\n"
        "sys.exit(0)\n")
    return d


def attempts_file(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / ".canonical-entry-attempts"


def read_attempts(run_dir: Path) -> int:
    p = attempts_file(run_dir)
    if not p.is_file():
        return 0
    try:
        return int(p.read_text().strip() or "0")
    except ValueError:
        return 0


def run_entry(run_dir: Path, scripts_dir: Path, *extra: str,
              plan: bool = False, env_extra: dict | None = None):
    env = dict(os.environ)
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    env.update(env_extra or {})
    cmd = ["bash", str(ENTRY), "--run-dir", str(run_dir),
           "--scripts-dir", str(scripts_dir)]
    if plan:
        cmd.append("--plan")
    else:
        cmd += ["--slides", str(run_dir / "slides.json"),
                "--out", str(run_dir / "out.pptx")]
    cmd += list(extra)
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


# ---------------------------------------------------------------------------
# THE PROOF — three failed gate runs, then one passing run, never hit the cap.
# ---------------------------------------------------------------------------
def test_three_failed_gate_runs_then_one_pass_never_hits_cap(tmp_path):
    """THE FIX 62 PROOF, verbatim. Three invocations that FAIL a gate leave the
    attempt counter untouched; the fourth — repaired — invocation passes and is
    NOT bricked by the cap, and its successful engine exit RESETS the counter."""
    run_dir = make_run_dir(tmp_path)
    # A scripts dir whose sync_check reports render-path drift: every invocation
    # fails GATE 3 (exit 7, AF-CANONICAL-RENDER-BYPASS) BEFORE the post-gate bump.
    drifted = tmp_path / "fake-scripts-drift"
    drifted.mkdir()
    (drifted / "build_deck.py").write_text("import sys\nsys.exit(0)\n")
    (drifted / "run_signature_deck.py").write_text("import sys\nsys.exit(0)\n")
    (drifted / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\n"
        "def list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n")
    (drifted / "sync_check.py").write_text(
        "import json, sys\n"
        "print(json.dumps({'in_sync': False, 'manifest_version': 39,\n"
        "  'drift': [{'check': 'B2', 'item': 'AF-X', 'detail': 'y', 'class': 'render_path'}],\n"
        "  'drift_summary': {'total': 1, 'render_path': 1, 'library_only': 0}}))\n"
        "sys.exit(4)\n")
    # Gate 0 must fail BEFORE the bump (the bump sits behind ALL GATES PASSED).
    assert 'gate_fail' in ENTRY.read_text(encoding="utf-8")

    for i in (1, 2, 3):
        r = run_entry(run_dir, drifted, env_extra={"OPENCLAW_WORKSPACE": str(tmp_path / "no-ws")})
        assert r.returncode != 0, f"failed-gate run {i} must not succeed: {r.stdout}"
        assert read_attempts(run_dir) == 0, (
            f"gate failure {i} consumed an attempt — the bump is not post-gate")

    # The repair: a scripts dir in lockstep, stub engine exits 0.
    ok_dir = make_scripts_dir(tmp_path, engine_rc=0)
    r4 = run_entry(run_dir, ok_dir, env_extra={"OPENCLAW_WORKSPACE": str(tmp_path / "no-ws")})
    assert r4.returncode == 0, (
        f"the repaired 4th invocation must pass — the cap must not brick a "
        f"gate-repair cycle\nstdout: {r4.stdout}\nstderr: {r4.stderr}")
    # A successful engine exit RESETS the budget.
    assert read_attempts(run_dir) == 0, (
        "a successful engine exit must reset the attempt counter to 0")


def test_engine_failing_builds_do_consume_and_cap_still_guards(tmp_path):
    """The cap still stops the engine-keeps-failing loop: builds that REACH the
    engine consume one attempt each, and the 4th dies with the explicit message."""
    run_dir = make_run_dir(tmp_path)
    fail_dir = make_scripts_dir(tmp_path, engine_rc=7)
    for i in (1, 2, 3):
        r = run_entry(run_dir, fail_dir, env_extra={"OPENCLAW_WORKSPACE": str(tmp_path / "no-ws")})
        assert r.returncode == 7, f"stub engine exit must propagate (run {i})"
        assert read_attempts(run_dir) == i, f"attempt {i} must be counted"
    r4 = run_entry(run_dir, fail_dir, env_extra={"OPENCLAW_WORKSPACE": str(tmp_path / "no-ws")})
    assert r4.returncode == 2, "the 4th build must be bricked by the cap (exit 2)"
    assert "Do NOT write a custom driver" in r4.stderr, r4.stderr


def test_plan_does_not_increment_attempts(tmp_path):
    """--plan is read-only inspection: it never consumes the entry budget."""
    run_dir = make_run_dir(tmp_path)
    ok_dir = make_scripts_dir(tmp_path, engine_rc=0)
    for _ in range(5):
        r = run_entry(run_dir, ok_dir, plan=True,
                      env_extra={"OPENCLAW_WORKSPACE": str(tmp_path / "no-ws")})
        assert r.returncode == 0, r.stderr
    assert read_attempts(run_dir) == 0, "--plan must not increment the attempt counter"


def test_plan_writes_no_intake_depth_side_effect(tmp_path):
    """--plan must not stamp pre_presentation_capture.STANDARD_MODE — the stamp
    is a build-time side effect gated on PLAN=0 (B4 proof: five --plan runs each
    appended a depth_audit record before this gate)."""
    run_dir = make_run_dir(tmp_path)
    ok_dir = make_scripts_dir(tmp_path, engine_rc=0)
    r = run_entry(run_dir, ok_dir, plan=True,
                  env_extra={"OPENCLAW_WORKSPACE": str(tmp_path / "no-ws")})
    assert r.returncode == 0, r.stderr
    stamped = run_dir / "working" / "copy" / "intake.json"
    assert not stamped.exists(), (
        "--plan must write no intake-depth side effect (read-only contract)")


def test_gate_failed_run_leaves_no_intake_depth_stamp(tmp_path):
    """A run that fails a gate must write NO depth stamp: the stamp fires only
    behind ALL GATES PASSED (FIX 62's 'stamp_intake_depth runs after gates')."""
    run_dir = make_run_dir(tmp_path)
    # GATE 0 fails: the intake ledger was removed after fixture creation.
    (run_dir / "working" / "interview" / "intake_ledger.json").unlink()
    ok_dir = make_scripts_dir(tmp_path, engine_rc=0)
    r = run_entry(run_dir, ok_dir, env_extra={"OPENCLAW_WORKSPACE": str(tmp_path / "no-ws")})
    assert r.returncode != 0, "gate-failing run must not succeed"
    stamped = run_dir / "working" / "copy" / "intake.json"
    assert not stamped.exists() or "STANDARD_MODE" not in stamped.read_text(), (
        "a gate-failed run must not stamp the intake depth")


def test_cc_post_import_is_gone():
    """`cc_post` import is gone: no live `from cc_board import cc_post` (or any
    cc_board import) remains in the entry script — the sync_drift_deferred event
    posts inline (best-effort) instead of a dead import a bare except swallowed."""
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "cc_board" not in stripped or "import" not in stripped, (
            f"live cc_board import remains: {stripped!r}")
        assert "cc_post" not in stripped, f"live cc_post reference remains: {stripped!r}"
    # And the inline event poster replaced it.
    assert "sync_drift_deferred" in src
    assert "/api/events" in src
    assert "x-webhook-signature" in src


def test_bump_and_reset_are_plan_gated_in_source():
    """Static contract: the bump block sits inside `if [ "$PLAN" -eq 0 ]`, the
    reset is keyed on a successful engine exit, and the stamp wrapper is
    PLAN-gated (the definition-order hazards FIX 62 reconciled)."""
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    # The reset exists and is keyed on engine success.
    assert 'if [ "$_ENGINE_RC" -eq 0 ]; then' in src
    assert "canonical-entry attempt budget reset" in src
    # The stamp wrapper refuses to run in plan mode.
    assert "stamp_intake_depth_after_gates() {" in src
    wrapper_idx = src.index("stamp_intake_depth_after_gates() {")
    wrapper = src[wrapper_idx:wrapper_idx + 220]
    assert '[ "$PLAN" -eq 0 ] || return 0' in wrapper
    # Definition order: gate_fail / owner_skip_approved / _record_dep_gate_bypassed
    # / trace_fail are all DEFINED before GATE 0c executes (bash does not hoist).
    for fn in ("owner_skip_approved()", "_record_dep_gate_bypassed()",
               "gate_fail()", "trace_fail()"):
        def_idx = src.index(fn)
        gate0c_idx = src.index('if [ -f "$SELF_DIR/presentations-drift-gates.sh" ]; then')
        assert def_idx < gate0c_idx, f"{fn} must be defined before GATE 0c executes"
    # SELF_DIR is defined before GATE 0c's first read of it.
    self_dir_idx = src.index('SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"')
    gate0c_idx = src.index('if [ -f "$SELF_DIR/presentations-drift-gates.sh" ]; then')
    assert self_dir_idx < gate0c_idx, "SELF_DIR must be defined before GATE 0c"
