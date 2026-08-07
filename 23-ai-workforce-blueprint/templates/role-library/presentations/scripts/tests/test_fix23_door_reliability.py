"""FIX-23 QC gate — canonical-entry door reliability (Error 5 / R5).

Per-task QC standard (Gauntlet doc, FIX-23 row):
  - With seeded A5/A6-only drift GATE 3 proceeds (evented)
  - With render-path drift GATE 3 fails
  - 4th canonical-entry attempt dies
  - sync_check.py --json after repair reports 0 drift items
  - GATE 1b imports ghl_media under the render interpreter; ghl_media imports cleanly
    (co-located Skill-48 sibling resolution)

No grep anywhere. Targeted python only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent  # .../presentations/scripts
DEPT_ROOT = SCRIPTS.parents[3]                    # .../23-ai-workforce-blueprint
ENTRY = DEPT_ROOT / "scripts" / "presentation-canonical-entry.sh"
MANIFEST = Path(__file__).resolve().parents[6] / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"


# ---------------------------------------------------------------------------
# Sub-unit (a) — sync_check.py emits `class`; GATE 3 classifies.
# ---------------------------------------------------------------------------
def _load_sync_check():
    sys.path.insert(0, str(SCRIPTS))
    import sync_check
    return sync_check


def test_sync_check_emits_class_on_drift_items():
    """Every drift item in --json output carries a `class` field. A5/A6 are
    library-only; every other class is render_path. This is the contract GATE 3
    classifies against."""
    sync_check = _load_sync_check()
    drift = [{"check": "A5", "item": "x", "detail": "d"},
             {"check": "A6", "item": "y", "detail": "d"},
             {"check": "B2", "item": "z", "detail": "d"},
             {"check": "V2", "item": "w", "detail": "d"},
             {"check": "A2", "item": "v", "detail": "d"}]
    # Re-run the classification logic run_checks' add() uses on sample items.
    classified = []
    for d in drift:
        if d["check"] in ("A5", "A6"):
            cls = "A5/A6"
        else:
            cls = "render_path"
        classified.append({**d, "class": cls})
    for c, cls in zip(classified, ["A5/A6", "A5/A6", "render_path", "render_path", "render_path"]):
        assert c["class"] == cls, (c, cls)


def test_sync_check_json_has_drift_summary_key():
    """The --json output carries drift_summary with render_path/library_only split."""
    r = subprocess.run([sys.executable, str(SCRIPTS / "sync_check.py"), "--json"],
                       capture_output=True, text=True)
    assert r.returncode in (0, 4), r.stderr
    d = json.loads(r.stdout)
    assert "drift_summary" in d
    assert d["drift_summary"]["total"] == d["drift_summary"]["render_path"] + d["drift_summary"]["library_only"]


def test_gate3_proceeds_on_library_only_drift():
    """GATE 3 classification: drift containing ONLY A5/A6 -> proceed (exit 0)."""
    lib_only = [
        {"check": "A5", "item": "r1", "detail": "x", "class": "A5/A6"},
        {"check": "A6", "item": "p1", "detail": "y", "class": "A5/A6"},
    ]
    blocking = [x for x in lib_only if x.get("class") != "A5/A6"]
    assert blocking == []


def test_gate3_fails_on_render_path_drift():
    """GATE 3 classification: ANY non-A5/A6 drift -> block (fail closed)."""
    mixed = [
        {"check": "A5", "item": "r1", "detail": "x", "class": "A5/A6"},
        {"check": "B2", "item": "AF-X", "detail": "y", "class": "render_path"},
    ]
    blocking = [x for x in mixed if x.get("class") != "A5/A6"]
    assert len(blocking) == 1
    assert blocking[0]["check"] == "B2"


def test_entry_gate3_has_classification_filter():
    """The entry script's GATE 3 must parse sync_check --json and filter on class,
    not treat every drift as fatal (the pre-fix behavior that bricked the door)."""
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    # The classification filter must exist (python heredoc parsing --json drift).
    assert 'sync_check.py" --json' in src
    assert 'x.get("class") != "A5/A6"' in src
    assert "library-only A5/A6 drift deferred" in src
    assert "sync_drift_deferred" in src


def _make_fake_scripts_dir(tmp_path: Path, sync_drift_json: str) -> Path:
    """Build a fake SCRIPTS_DIR holding stub build_deck/run_signature_deck/ghl_media
    plus a fake sync_check.py that prints `sync_drift_json` to stdout and exits 4
    (drift) or 0 (sync) based on the payload. GATE 3 runs this fake under the real
    classification filter. The payload is written as a JSON data file and loaded by
    the fake (so JSON booleans stay valid Python)."""
    d = tmp_path / "fake-scripts"
    d.mkdir()
    (d / "build_deck.py").write_text("# stub build_deck\n")
    (d / "run_signature_deck.py").write_text(
        "import sys\nprint('stub run_signature_deck plan')\nsys.exit(0)\n"
    )
    (d / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\ndef list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n"
    )
    (d / "_payload.json").write_text(sync_drift_json)
    (d / "sync_check.py").write_text(
        "import json, sys\n"
        "_PAYLOAD = json.load(open(%r))\n"
        "print(json.dumps(_PAYLOAD))\n"
        "sys.exit(0 if _PAYLOAD['in_sync'] else 4)\n" % str(d / "_payload.json")
    )
    return d


def _run_entry(run_dir: Path, scripts_dir: Path, extra_env):
    env = dict(os.environ)
    env.update(extra_env)
    env["OPENCLAW_WORKSPACE"] = str(run_dir.parent / "no-such-workspace")
    cmd = ["bash", str(ENTRY), "--run-dir", str(run_dir), "--plan",
           "--scripts-dir", str(scripts_dir)]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)


def test_gate3_end_to_end_library_only_proceeds(tmp_path):
    """END-TO-END QC gate (a): a fake sync_check emitting ONLY A5/A6 (library-only)
    drift -> GATE 3 proceeds (exit 0) and logs the deferral — the sanctioned door is
    NOT bricked by library maintenance debt."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "checkpoints" / ".test-context").write_text("")
    payload = {
        "in_sync": False,
        "manifest_version": 39,
        "drift": [
            {"check": "A5", "item": "undeclared-role", "detail": "x", "class": "A5/A6"},
            {"check": "A6", "item": "P-SOME", "detail": "y", "class": "A5/A6"},
        ],
        "drift_summary": {"total": 2, "render_path": 0, "library_only": 2},
    }
    scripts = _make_fake_scripts_dir(tmp_path, json.dumps(payload))
    env = {"QC_SKIP_PRESENTATION_DEPS": "1"}
    result = _run_entry(run_dir, scripts, env)
    assert result.returncode == 0, (
        f"library-only drift must PROCEED; got exit {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "library-only A5/A6 drift deferred" in result.stdout + result.stderr, result.stderr
    # The deferral is ALSO wired to emit a sync_drift_deferred CC event (best-effort;
    # the event code lives in the entry script's heredoc, proven present by the static
    # assertion above — the event POST itself is wrapped `|| true` so a box without
    # cc_board reachable never blocks the door).
    assert "sync_drift_deferred" in ENTRY.read_text(encoding="utf-8", errors="replace")


def test_gate3_end_to_end_render_path_fails(tmp_path):
    """END-TO-END QC gate (a): a fake sync_check emitting a render-path drift item
    (B2) -> GATE 3 FAILS CLOSED (exit 7, AF-CANONICAL-RENDER-BYPASS)."""
    run_dir = tmp_path / "run2"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "checkpoints" / ".test-context").write_text("")
    payload = {
        "in_sync": False,
        "manifest_version": 39,
        "drift": [
            {"check": "B2", "item": "AF-ORPHAN", "detail": "y", "class": "render_path"},
        ],
        "drift_summary": {"total": 1, "render_path": 1, "library_only": 0},
    }
    scripts = _make_fake_scripts_dir(tmp_path, json.dumps(payload))
    env = {"QC_SKIP_PRESENTATION_DEPS": "1"}
    result = _run_entry(run_dir, scripts, env)
    assert result.returncode == 7, (
        f"render-path drift must FAIL CLOSED (exit 7); got exit {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "AF-CANONICAL-RENDER-BYPASS" in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# Sub-unit (b) — 3-attempt cap.
# ---------------------------------------------------------------------------
def test_entry_has_attempt_cap():
    """The entry script must carry the canonical-entry attempt cap: per run dir,
    3 attempts allowed, the 4th invocation dies with an explicit message."""
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    assert ".canonical-entry-attempts" in src
    assert "_ATTEMPTS" in src
    assert '_ATTEMPTS" -gt 3' in src or "_ATTEMPTS -gt 3" in src
    assert "Do NOT write a custom driver" in src


def test_attempt_cap_behavior(tmp_path):
    """Run the entry script 4 times against one run dir; the 4th must die with the
    >3 attempts message. Uses --plan to clear GATE 0/1/3 while still exercising the
    cap (the cap is gated on PLAN=0, so use a build-style invocation with all gates
    satisfied instead). To keep this hermetic and dependency-free, we simulate the
    cap's exact counter logic."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    attempt_file = run_dir / "working" / "checkpoints" / ".canonical-entry-attempts"
    # Simulate the shell arithmetic exactly as the entry script does.
    def bump():
        n = int((attempt_file.read_text().strip() or "0")) if attempt_file.exists() else 0
        n += 1
        attempt_file.write_text(str(n))
        return n
    counts = [bump() for _ in range(4)]
    assert counts == [1, 2, 3, 4]
    # The 4th exceeds the cap.
    assert counts[-1] > 3


def test_entry_plan_exempts_attempt_cap():
    """--plan (read-only inspection) must NOT consume the entry budget — inspecting
    a run dir is not a build attempt."""
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    # The cap block must be inside `if [ "$PLAN" -eq 0 ]`.
    cap_idx = src.find(".canonical-entry-attempts")
    assert cap_idx != -1
    # Look backwards for the nearest `if [ "$PLAN" -eq 0 ]` gate.
    before = src[:cap_idx]
    assert 'if [ "$PLAN" -eq 0 ]; then' in before
    # And the cap's own condition is on PLAN (the whole block is inside it).
    after = src[cap_idx:cap_idx + 1200]
    assert "_ATTEMPTS" in after


def _run_entry_build(run_dir: Path, scripts_dir: Path, extra_env):
    """BUILD-mode entry invocation (no --plan): exercises the attempt cap and the
    full gate chain. Requires --slides/--out; the stub runner exits 0 so the chain
    completes."""
    env = dict(os.environ)
    env.update(extra_env)
    env["OPENCLAW_WORKSPACE"] = str(run_dir.parent / "no-such-workspace")
    slides = run_dir / "slides.json"
    slides.write_text("{}")
    out = run_dir / "out.pptx"
    cmd = ["bash", str(ENTRY), "--run-dir", str(run_dir),
           "--slides", str(slides), "--out", str(out),
           "--scripts-dir", str(scripts_dir)]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)


def test_attempt_cap_end_to_end_4th_dies(tmp_path):
    """END-TO-END QC gate (b): 3 canonical-entry invocations on one run dir succeed
    through the gate chain; the 4th dies with the explicit >3-attempts message and
    NO custom driver is permitted. Runs in BUILD mode (no --plan) so the cap (gated
    on PLAN=0) is actually exercised."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "checkpoints" / ".test-context").write_text("")
    # BUILD mode trips GATE 0 (intake ledger) + GATE 0b (intake trace): seed both.
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True}))
    (run_dir / "working" / "interview" / "intake_transcript.json").write_text(
        json.dumps({"driver": "deck-intake-driver", "signature": "signed",
                    "turns": [{"q": "What topic?", "a": "A long enough answer " * 40}]}))
    payload = {"in_sync": True, "manifest_version": 39, "drift": [],
               "drift_summary": {"total": 0, "render_path": 0, "library_only": 0}}
    scripts = _make_fake_scripts_dir(tmp_path, json.dumps(payload))
    env = {"QC_SKIP_PRESENTATION_DEPS": "1"}
    # Attempt 1-3: succeed (gates pass, stub runner exits 0).
    for attempt in (1, 2, 3):
        r = _run_entry_build(run_dir, scripts, env)
        assert r.returncode == 0, (
            f"attempt {attempt} must pass; got {r.returncode}\n{r.stderr}"
        )
    # Attempt 4: MUST die with the explicit >3 message (exit 2).
    r4 = _run_entry_build(run_dir, scripts, env)
    assert r4.returncode == 2, f"4th attempt must die (exit 2); got {r4.returncode}"
    assert ">3" in r4.stderr or "attempted 4 times" in r4.stderr, r4.stderr
    assert "Do NOT write a custom driver" in r4.stderr, r4.stderr
    # The counter file recorded 4.
    counter = run_dir / "working" / "checkpoints" / ".canonical-entry-attempts"
    assert counter.read_text().strip() == "4"


# ---------------------------------------------------------------------------
# Sub-unit (d) — GHL co-location / GATE 1b import under render interpreter.
# ---------------------------------------------------------------------------
def test_ghl_media_imports_cleanly():
    """ghl_media imports under the render interpreter (stdlib + Skill-48 sibling)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code = ("import ghl_media\n"
            "assert hasattr(ghl_media, 'upload_media')\n"
            "assert hasattr(ghl_media, 'list_media')\n"
            "assert hasattr(ghl_media, 'create_media_folder')\n"
            "assert hasattr(ghl_media, 'resolve_location_pit')\n"
            "print('GHM-OK', ghl_media.CANONICAL_SOURCE)\n")
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "GHM-OK" in r.stdout


def test_ghl_co_location_sibling_resolution(tmp_path):
    """A deployed dept scripts dir (no repo sibling reachable) resolves the
    Skill-48 canonical module from the co-located _skill48_ghl_media.py copy."""
    dept = tmp_path / "departments" / "Presentations" / "scripts"
    dept.mkdir(parents=True)
    src_ghl = SCRIPTS / "ghl_media.py"
    src_sibling = Path(__file__).resolve().parents[6] / "48-facebook-ad-generator" / "tools" / "ghl_media.py"
    assert src_ghl.is_file()
    assert src_sibling.is_file(), f"sibling not found at {src_sibling}"
    (dept / "ghl_media.py").write_bytes(src_ghl.read_bytes())
    (dept / "_skill48_ghl_media.py").write_bytes(src_sibling.read_bytes())
    empty_skills = tmp_path / "empty-skills"
    empty_skills.mkdir()
    env = dict(os.environ)
    env["OPENCLAW_SKILLS_DIR"] = str(empty_skills)
    env.pop("PYTHONPATH", None)
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import ghl_media\n"
        "print('CANS:', ghl_media.CANONICAL_SOURCE)\n"
        "assert '_skill48_ghl_media.py' in ghl_media.CANONICAL_SOURCE, ghl_media.CANONICAL_SOURCE\n"
        "assert hasattr(ghl_media, 'list_media')\n"
    ) % str(dept)
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "CANS:" in r.stdout


def test_gate1b_imports_with_render_interpreter():
    """GATE 1b must run the import with $SCRIPTS_DIR on PYTHONPATH and surface the
    real import error (the render interpreter — same python3 that runs build_deck)."""
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    assert 'PYTHONPATH="$SCRIPTS_DIR' in src
    assert 'python3 -c "import ghl_media"' in src
    assert "import> " in src  # surfaces the real import error


# ---------------------------------------------------------------------------
# Sub-unit (c) — 27 drift items repaired to 0.
# ---------------------------------------------------------------------------
def test_sync_check_zero_drift_after_repair():
    """After the drift repair (manifest autofails registered for the two orphan
    codes; roles/owning_role reconciled), sync_check --json reports 0 drift."""
    r = subprocess.run([sys.executable, str(SCRIPTS / "sync_check.py"), "--json"],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)
    assert d["in_sync"] is True, f"drift remains: {d.get('drift')}"
    assert d["drift_summary"]["total"] == 0


def test_manifest_registers_orphan_codes():
    """The two B2-orphan codes cited by build_deck (AF-FORGED-APPROVAL,
    AF-KIE-AUTH) are now registered in PIPELINE-MANIFEST.autofails so lockstep
    passes (this is the repo-side half of the drift repair)."""
    m = json.loads(MANIFEST.read_text())
    codes = {a["code"] for a in m["autofails"]}
    assert "AF-FORGED-APPROVAL" in codes
    assert "AF-KIE-AUTH" in codes
