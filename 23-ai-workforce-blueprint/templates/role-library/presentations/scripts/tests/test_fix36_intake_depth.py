"""FIX 36(3) — the canonical entry's intake-depth flag.

Spec (PRESENTATION-DEPT-FIX-SPEC.md, FIX 36 change 3): "add the documented
canonical-entry intake-depth flag as **`--intake-depth quick|in-depth`** (env
`PRESENTATION_INTAKE_DEPTH`), passed to FIX 30's `standard_mode`; this flag is
deliberately distinct from FIX 38's run-mode `--mode`/`PRESENTATION_MODE`,
whose vocabulary is only `Ultra|Standard|Economy` (FIX 11)".

Two legs, mirroring test_canonical_entry_scripts_dir.py's structure:

  1. STATIC — the flag, the env fallback, the FIX 30 vocabulary and the
     never-reuse--mode collision message must all be present in BOTH copies
     (the canonical source and the byte-identical generated mirror).
  2. DYNAMIC — actually run the entry script in --plan mode and observe:
     - --intake-depth in-depth stamps pre_presentation_capture.STANDARD_MODE
       = "IN-DEPTH" (the schema's stored form) in working/copy/intake.json;
     - default (no flag, no env) stamps "QUICK" (the schema default);
     - PRESENTATION_INTAKE_DEPTH is honored as the env fallback;
     - run-mode vocabulary (Ultra/Standard/Economy) is REFUSED with a message
       naming the collision — never accepted as intake depth;
     - a garbage value is refused, never silently coerced.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_ENTRY_DEPLOYED = _SCRIPTS_DIR / "presentation-canonical-entry.sh"
_ENTRY_REPO = _SCRIPTS_DIR.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO
MIRROR = _SCRIPTS_DIR / "presentation-canonical-entry.sh"
CANON = _ENTRY_REPO


def _read(path: Path) -> str:
    assert path.is_file(), f"entry script not found at {path}"
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 1. STATIC
# ---------------------------------------------------------------------------

def test_flag_and_env_present_in_both_copies():
    for path in (CANON, MIRROR):
        src = _read(path)
        for needle in (
            "--intake-depth",
            "PRESENTATION_INTAKE_DEPTH",
            "STANDARD_MODE",
            "quick|in-depth",
        ):
            assert needle in src, f"expected {needle!r} in {path}"


def test_run_mode_vocabulary_collision_guard_present():
    """The refusal message must name the FIX 11 run-mode vocabulary and state
    the axes never interchange — the spec's named resolution of the collision."""
    src = _read(ENTRY)
    assert "Ultra|Standard|Economy" in src
    assert "never interchangeable" in src


def test_no_bare_mode_flag_added():
    """--mode must NOT be a parsable flag on the entry script: one vocabulary
    per axis. (Mentions of --mode in explanatory comments are fine; a case
    pattern or env var definition is not.)"""
    src = _read(ENTRY)
    assert "--mode)" not in src, (
        "the entry script defines a --mode case in its arg parser — the "
        "run-mode axis must never be a canonical-entry flag")
    assert 'PRESENTATION_MODE' not in src, (
        "the entry script reads PRESENTATION_MODE — that is the run-mode "
        "axis (FIX 11), which the canonical entry must not expose")


def test_mirror_is_byte_identical():
    assert CANON.read_bytes() == MIRROR.read_bytes(), (
        "presentation-canonical-entry.sh's canonical source and generated "
        "mirror diverged (FIX 31) — re-cp the mirror."
    )


# ---------------------------------------------------------------------------
# 2. DYNAMIC
# ---------------------------------------------------------------------------

def _make_fixture(tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "copy" / "intake.json").write_text(
        json.dumps({"client_name": "Test", "requester_chat_id": "123"}), encoding="utf-8")
    scripts = tmp_path / "fake-scripts"
    scripts.mkdir()
    (scripts / "build_deck.py").write_text("# stub build_deck\n")
    (scripts / "run_signature_deck.py").write_text("# stub runner\n")
    (scripts / "ghl_media.py").write_text("# stub ghl_media\n")
    return run_dir, scripts


def _run(run_dir: Path, scripts: Path, extra_args, env_overrides=None):
    env = dict(os.environ)
    env["OPENCLAW_WORKSPACE"] = str(run_dir.parent / "no-such-workspace")
    env.pop("SCRIPTS_DIR", None)
    env.pop("PRESENTATION_INTAKE_DEPTH", None)
    for k, v in (env_overrides or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return subprocess.run(
        ["bash", str(ENTRY), "--run-dir", str(run_dir), "--plan", *extra_args],
        env=env, capture_output=True, text=True, timeout=120)


def _stamped(run_dir: Path):
    p = run_dir / "working" / "copy" / "intake.json"
    return json.loads(p.read_text(encoding="utf-8")).get(
        "pre_presentation_capture", {}).get("STANDARD_MODE")


def test_intake_depth_flag_stamps_in_depth(tmp_path):
    run_dir, scripts = _make_fixture(tmp_path)
    r = _run(run_dir, scripts, ["--intake-depth", "in-depth", "--scripts-dir", str(scripts)])
    assert r.returncode == 0, f"rc={r.returncode}\nstderr: {r.stderr}"
    assert _stamped(run_dir) == "IN-DEPTH"


def test_default_is_quick(tmp_path):
    run_dir, scripts = _make_fixture(tmp_path)
    r = _run(run_dir, scripts, ["--scripts-dir", str(scripts)])
    assert r.returncode == 0, f"rc={r.returncode}\nstderr: {r.stderr}"
    assert _stamped(run_dir) == "QUICK"


def test_env_fallback_honored(tmp_path):
    run_dir, scripts = _make_fixture(tmp_path)
    r = _run(run_dir, scripts, ["--scripts-dir", str(scripts)],
             {"PRESENTATION_INTAKE_DEPTH": "in-depth"})
    assert r.returncode == 0, f"rc={r.returncode}\nstderr: {r.stderr}"
    assert _stamped(run_dir) == "IN-DEPTH"


def test_run_mode_vocabulary_refused(tmp_path):
    """FIX 11's run-mode words must NEVER pass as intake depth — the spec's
    named collision. Each is refused with exit 2 and a message naming both
    vocabularies."""
    run_dir, scripts = _make_fixture(tmp_path)
    for value in ("Ultra", "Standard", "Economy", "ultra", "economy"):
        r = _run(run_dir, scripts, ["--intake-depth", value, "--scripts-dir", str(scripts)])
        assert r.returncode == 2, (
            f"--intake-depth {value!r} was accepted (rc {r.returncode}); the "
            "run-mode vocabulary must never be reused as intake depth")
        assert "never interchangeable" in r.stderr
        assert "quick|in-depth" in r.stderr


def test_invalid_value_refused_not_coerced(tmp_path):
    run_dir, scripts = _make_fixture(tmp_path)
    r = _run(run_dir, scripts, ["--intake-depth", "deep", "--scripts-dir", str(scripts)])
    assert r.returncode == 2
    assert "invalid value" in r.stderr
    assert "quick|in-depth" in r.stderr


def test_interview_depth_docstring_distinct_from_run_mode(tmp_path):
    """The usage/help text must present intake-depth as the interview-depth
    axis only — never as a deck-quality/run-mode control."""
    run_dir, scripts = _make_fixture(tmp_path)
    r = _run(run_dir, scripts, ["--help"])
    assert "--intake-depth quick|in-depth" in r.stderr or \
        "--intake-depth quick|in-depth" in r.stdout
    combined = r.stdout + r.stderr
    assert "Ultra|Standard|Economy" in combined
    assert "deliberately distinct" in combined


# ---------------------------------------------------------------------------
# FIX 36(5) — displayed phase count derives from the canonical manifest
# ---------------------------------------------------------------------------

def _fixture_with_manifest(tmp_path: Path, n_phases: int) -> tuple[Path, Path]:
    run_dir, scripts = _make_fixture(tmp_path)
    sops = scripts.parent / "sops"
    sops.mkdir()
    manifest = {"manifest_version": 999,
                "phases": [{"id": f"P{i}"} for i in range(n_phases)]}
    (sops / "PIPELINE-MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir, scripts


def test_plan_mode_phase_count_derived_from_manifest(tmp_path):
    """--plan's displayed 'Manifest phases' must equal the manifest's own
    phase count — never a stale hardcoded number (FIX 36(5))."""
    run_dir, scripts = _fixture_with_manifest(tmp_path, 7)
    r = _run(run_dir, scripts, ["--scripts-dir", str(scripts)])
    assert r.returncode == 0, f"rc={r.returncode}\nstderr: {r.stderr}"
    assert "Manifest phases: 7" in (r.stdout + r.stderr), (
        f"expected the displayed count to come from the manifest (7); got: "
        f"{r.stdout}\n{r.stderr}")


def test_dispatch_note_count_derived_from_manifest(tmp_path):
    """The ALL-GATES-PASSED dispatch note must carry the manifest-derived
    count too (the note fires only with a resolvable engine; the --plan leg
    above already pins the same resolver)."""
    src = _read(ENTRY)
    # the dispatch note interpolates $_PHASE_COUNT, not a literal
    assert "all $_PHASE_COUNT manifest phases" in src
    # and the count is computed via the canonical manifest resolution
    assert "sops/PIPELINE-MANIFEST.json" in src
    assert "resolve_manifest" in src
    assert "all 36 phases, mechanical" not in src, (
        "the stale hardcoded 36 is still in the dispatch note")