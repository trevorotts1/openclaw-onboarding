"""PD-026 — three small door defects (acceptance rows A1, A2, A3).

A1  library-only drift (sync_check exit 4, class A5/A6) is DEFERRED, not fatal:
    the door proceeds and records a `sync_drift_deferred` row. cc_board.py's own
    main offers NO posting verb (it exposes --reconcile only), so per the unit's
    consolidation amendment (a) the row is appended to the run's gate log and
    printed. This test asserts that row exists.

A2  the raw sync_check JSON lives under the run's own checkpoints directory —
    never the system temp folder — and is removed on every exit path. Proved by
    listing the system temp folder before and after a real door run, and by a
    static guard that no `_pce_sync` name survives in the door.

A3  every interpreter call in the door is `$PRESENTATION_PY`, `$_gate_py`, or
    inside `_pres35_resolve_entry_interpreter` (which must run before the pin is
    final). No bare `python3` invocation survives anywhere else.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO
assert ENTRY.is_file(), f"canonical entry script not found ({ENTRY})"


# ---------------------------------------------------------------------------
# Hermetic fixture — same contract as test_fix62_door_hygiene.py (fake scripts
# dir + stub engine), but sync_check reports LIBRARY-ONLY (A5/A6) drift.
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
        json.dumps({"format": "sp-intake-transcript-v1",
                    "driver": "deck-intake-driver",
                    "driver_signature": "fixture-signed",
                    "qid_sequence": ["q1", "q2"],
                    "turns": [{"q": "What topic?", "a": "A long enough answer " * 40}] * 10}))
    (run_dir / "slides.json").write_text("{}")
    return run_dir


def make_scripts_dir(base: Path) -> Path:
    d = base / "fake-scripts"
    d.mkdir(exist_ok=True)
    (d / "build_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "run_signature_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "presentation_job.py").write_text(
        "import sys\n"
        "if '--new' in sys.argv:\n"
        "    sys.exit(0)\n"
        "sys.exit(0)\n")
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
    # LIBRARY-ONLY drift: the door must proceed and event it, never fail closed.
    (d / "sync_check.py").write_text(
        "import json, sys\n"
        "print(json.dumps({'in_sync': False, 'manifest_version': 39,\n"
        "  'drift': [{'check': 'A5', 'item': 'role-roster', 'detail': 'y', 'class': 'A5/A6'}],\n"
        "  'drift_summary': {'total': 1, 'render_path': 0, 'library_only': 1}}))\n"
        "sys.exit(4)\n")
    return d


def run_entry(run_dir: Path, scripts_dir: Path):
    env = dict(os.environ)
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    env["OPENCLAW_WORKSPACE"] = str(run_dir.parent / "no-ws")
    cmd = ["bash", str(ENTRY), "--run-dir", str(run_dir),
           "--scripts-dir", str(scripts_dir),
           "--slides", str(run_dir / "slides.json"),
           "--out", str(run_dir / "out.pptx")]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180)


def _temp_names():
    """Every entry name in the system temp folder."""
    return set(os.listdir(tempfile.gettempdir()))


# ---------------------------------------------------------------------------
# A1 — the deferred event row exists.
# ---------------------------------------------------------------------------
def test_a1_library_only_drift_writes_gate_log_row(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = run_entry(run_dir, scripts)
    assert r.returncode == 0, (
        f"library-only A5/A6 drift must NOT brick the door\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    log = run_dir / "working" / "checkpoints" / "gate_log.jsonl"
    assert log.is_file(), f"no gate log written at {log}"
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    deferred = [row for row in rows if row.get("event") == "sync_drift_deferred"]
    assert deferred, f"no sync_drift_deferred row in {log}: {rows}"
    assert deferred[0].get("severity") == "warn", deferred[0]
    assert "sync_drift_deferred event deferred to the gate log" in r.stdout, (
        f"the deferral was not printed as required\nstdout:\n{r.stdout}")
    assert "not posted" not in r.stderr, (
        f"the row write failed but the run hid it\nstderr:\n{r.stderr}")


# ---------------------------------------------------------------------------
# A2 — nothing named _pce_sync lands in the system temp folder; the run's own
# temp file is cleaned up on the exit path.
# ---------------------------------------------------------------------------
def test_a2_no_pce_sync_in_system_temp_and_run_temp_cleaned(tmp_path):
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    assert "_pce_sync" not in src, (
        "the door still references the old _pce_sync temp file name")
    assert ".sync-check." in src, "the door does not use the run-owned temp file"

    before = _temp_names()
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = run_entry(run_dir, scripts)
    assert r.returncode == 0, f"door run failed\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    after = _temp_names()

    created = {n for n in (after - before) if "_pce_sync" in n}
    assert not created, (
        f"the run left _pce_sync file(s) in the system temp folder: {sorted(created)}")
    assert not [n for n in after if "_pce_sync" in n], (
        "a _pce_sync file exists in the system temp folder after the run")

    leftovers = sorted(p.name for p in
                       (run_dir / "working" / "checkpoints").glob(".sync-check.*"))
    assert leftovers == [], f"the run-owned sync temp file was not removed: {leftovers}"


# ---------------------------------------------------------------------------
# A3 — every interpreter call is pinned.
# ---------------------------------------------------------------------------
_INVOKE = re.compile(r'(?<![\w$/-])(python3|python)(?=\s+-)')


def _resolver_range(lines):
    """1-based (first, last) line numbers of the resolver function body."""
    start = None
    for i, line in enumerate(lines, 1):
        if "_pres35_resolve_entry_interpreter() {" in line:
            start = i
            break
    assert start is not None, "the resolver function is gone from the door"
    for j in range(start, len(lines) + 1):
        if lines[j - 1] == "}":
            return start, j
    raise AssertionError("the resolver function has no closing }")


def test_a3_every_interpreter_call_is_pinned(tmp_path):
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")
    first, last = _resolver_range(lines)

    offenders = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if _INVOKE.search(line) and not (first <= i <= last):
            offenders.append((i, stripped))
    assert not offenders, (
        "bare python3/python invocation(s) outside the resolver: "
        + "; ".join(f"line {i}: {t}" for i, t in offenders))

    # The read_run_mode helper (the one bare call PD-026 names) now uses the pin.
    mode_idx = lines.index("read_run_mode() {")
    body = "\n".join(lines[mode_idx:mode_idx + 6])
    assert '"$PRESENTATION_PY" - "$1" "$SCRIPTS_DIR"' in body, (
        f"read_run_mode does not invoke the resolved pin:\n{body}")

    # Every interpreter-invoking line is one of the two pinned forms.
    pinned = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r'"\$(PRESENTATION_PY|_gate_py)"\s+-', line) \
           or re.search(r'"\$\{PRESENTATION_PY:-python3\}"\s+-', line):
            pinned += 1
    assert pinned >= 8, f"expected the door's pinned interpreter calls; found {pinned}"
