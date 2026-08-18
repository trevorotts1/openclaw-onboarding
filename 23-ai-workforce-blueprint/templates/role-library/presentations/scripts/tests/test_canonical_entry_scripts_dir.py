"""U006 regression: presentation-canonical-entry.sh must REFUSE rather than
autodetect the scripts directory.

Why this exists: U006 replaced the entry script's seven-candidate
autodetect loop in resolve_scripts_dir() with an explicit two-candidate
resolver (--scripts-dir / $SCRIPTS_DIR, else the materialized department
default) that refuses with a plain-language message rather than guessing.
That fix (commit edc8a2fd, "feat(U006): stop entry script guessing scripts
dir") landed on a branch cut BEFORE it, and when that branch (U025 —
retire the front-door build guard) was merged to main it silently carried
the OLD seven-candidate loop back in. U006's own later "Land U006" merge
only touched tests/docs/installers, never re-touched the script, so
ancestry said "U006 is merged" while the file on disk still guessed.

This test is the guard against that happening again. It has two legs:

  1. STATIC — grep the script source for the seven-candidate loop shape.
     This is the "bleed test": reintroduce the loop (e.g. add back
     "$RUN_DIR/../scripts" or "$SELF_DIR" as a resolver candidate) and
     this test fails; remove it and this test passes. A regex that only
     asserts presence of the new strings is not enough — the old loop's
     candidate paths overlap textually with some of the new required
     strings (both mention "departments/Presentations/scripts" and
     "templates/role-library/presentations/scripts"), so the absence
     check has to target the loop's actual shape, not just borrow
     word-fragments.
  2. DYNAMIC (executing) — actually invoke the script and observe the
     refusal / success at runtime, not just read the file. A comment
     that says the right words would pass the static leg without the
     behaviour ever running.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
# The canonical entry script ships inside the deployed scripts dir itself
# (scripts/presentation-canonical-entry.sh — the R2/R3 nonce-route fix moved it
# there so the manifest's phase executors can reference it by relative path).
# The old repo-checkout path (.../23-ai-workforce-blueprint/scripts/...) remains
# the fallback for tests run from a checkout.
_ENTRY_DEPLOYED = _SCRIPTS_DIR / "presentation-canonical-entry.sh"
_ENTRY_REPO = _SCRIPTS_DIR.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO


def _read_entry() -> str:
    assert ENTRY.is_file(), f"entry script not found at {ENTRY}"
    # errors="replace" mirrors `grep -a`: never silently skip the file over a
    # decode hiccup — a script this load-bearing must always be read.
    return ENTRY.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 1. STATIC — the seven-candidate autodetect loop must be ABSENT.
# ---------------------------------------------------------------------------

def test_seven_candidate_autodetect_loop_is_absent():
    """Fails if resolve_scripts_dir()'s old multi-candidate `for c in ... ; do`
    shape reappears. Each of these candidate lines is a distinct historical
    autodetect guess; any one of them coming back is the same regression."""
    src = _read_entry()
    old_candidates = [
        r"\$SELF_DIR\"\s*\\",              # candidate: the entry script's own dir
        r"\$RUN_DIR/\.\./scripts",         # candidate: sibling of the run dir
        r"\$RUN_DIR/scripts",              # candidate: inside the run dir
        r"\$HOME/departments/Presentations/scripts",  # candidate: bare $HOME guess
    ]
    found = [pat for pat in old_candidates if re.search(pat, src)]
    assert not found, (
        "the old autodetect candidate(s) are back in resolve_scripts_dir(): "
        f"{found}. U006 requires an explicit two-candidate resolver "
        "(--scripts-dir/$SCRIPTS_DIR, else the materialized department "
        "default) that REFUSES rather than guesses. See SPEC/units/U006.md "
        "and commit edc8a2fd."
    )


def test_resolver_is_two_candidate_not_a_for_loop_over_many():
    """A structural check on resolve_scripts_dir() itself, independent of the
    exact candidate strings above: the function body must not contain a
    multi-line `for c in \\` continuation (the seven-candidate shape), and
    must contain exactly the two-candidate `for c in "$SCRIPTS_DIR" "..."`
    form on one line."""
    src = _read_entry()
    m = re.search(r"resolve_scripts_dir\(\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "resolve_scripts_dir() function not found in the entry script"
    body = m.group(1)
    # The old loop opened with a backslash-continued `for c in \` spanning
    # several lines. The new resolver's `for` is a single line.
    assert not re.search(r"for c in\s*\\\s*\n", body), (
        "resolve_scripts_dir() still opens its loop with a backslash-"
        "continued multi-line candidate list (the old seven-candidate shape)."
    )
    assert re.search(r'for c in "\$SCRIPTS_DIR" "\$DEPT_SCRIPTS_DEFAULT"', body), (
        "resolve_scripts_dir() does not contain the explicit two-candidate "
        "loop over $SCRIPTS_DIR and $DEPT_SCRIPTS_DEFAULT."
    )


def test_refusal_language_present():
    """The refusal wording U006 shipped must be present verbatim (this mirrors
    tests/unit/presentation-deps-gate.test.sh's assert_entry_has checks, kept
    here too so the presentations pytest suite carries its own copy of the
    guard rather than depending solely on a bash script outside this suite)."""
    src = _read_entry()
    for needle in (
        "Refusing to autodetect",
        "DEPT_SCRIPTS_DEFAULT",
        "materialized department",
        "--scripts-dir",
    ):
        assert needle in src, f"expected {needle!r} in {ENTRY}"


# ---------------------------------------------------------------------------
# 2. DYNAMIC — actually run the script; do not just read it.
# ---------------------------------------------------------------------------

def _make_fake_scripts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fake-scripts"
    d.mkdir()
    (d / "build_deck.py").write_text("# stub build_deck\n")
    (d / "run_signature_deck.py").write_text(
        "import sys\nprint('stub run_signature_deck')\nsys.exit(0)\n"
    )
    (d / "ghl_media.py").write_text("# stub ghl_media\n")
    return d


def _run_entry(run_dir: Path, extra_args, env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    cmd = ["bash", str(ENTRY), "--run-dir", str(run_dir), "--plan", *extra_args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)


def test_refuses_when_no_scripts_dir_and_no_materialized_department(tmp_path):
    """No --scripts-dir, no $SCRIPTS_DIR, and a deliberately nonexistent
    OPENCLAW_WORKSPACE (so this test is hermetic and does not depend on
    whatever the host box happens to have materialized) -> must exit 2 with
    a plain-language refusal, never a silent guess."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    fake_workspace = tmp_path / "no-such-workspace"

    env = {"OPENCLAW_WORKSPACE": str(fake_workspace)}
    env.pop("SCRIPTS_DIR", None)
    result = _run_entry(run_dir, [], env)

    assert result.returncode == 2, (
        f"expected exit 2 (usage/refusal), got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Refusing to autodetect" in result.stderr, (
        f"expected 'Refusing to autodetect' on stderr; got: {result.stderr}"
    )
    assert str(fake_workspace) in result.stderr, (
        "the refusal message should name the materialized-department path it "
        f"looked for; got: {result.stderr}"
    )


def test_refuses_when_stated_scripts_dir_is_wrong(tmp_path):
    """--scripts-dir pointing at a real directory that does NOT hold both
    build_deck.py and run_signature_deck.py must refuse (exit 2), not fall
    through to guessing something else."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    wrong_dir = tmp_path / "empty-scripts-dir"
    wrong_dir.mkdir()

    env = {"OPENCLAW_WORKSPACE": str(tmp_path / "no-such-workspace")}
    result = _run_entry(run_dir, ["--scripts-dir", str(wrong_dir)], env)

    assert result.returncode == 2, (
        f"expected exit 2, got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "Refusing to autodetect" in result.stderr


def test_refuses_skills_template_copy_by_name(tmp_path):
    """Even if --scripts-dir is stated AND holds both files, a path ending in
    templates/role-library/presentations/scripts must be refused by name.
    This is the specific wrong tree the old seven-candidate loop used to land
    on (candidate 3 in the pre-U006 resolver) — the audit's flagged defect."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    template_dir = tmp_path / "templates" / "role-library" / "presentations" / "scripts"
    template_dir.mkdir(parents=True)
    (template_dir / "build_deck.py").write_text("# stub\n")
    (template_dir / "run_signature_deck.py").write_text("# stub\n")

    env = {"OPENCLAW_WORKSPACE": str(tmp_path / "no-such-workspace")}
    result = _run_entry(run_dir, ["--scripts-dir", str(template_dir)], env)

    assert result.returncode == 2, (
        f"expected exit 2, got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "skills-TEMPLATE copy" in result.stderr, (
        f"expected the template-copy refusal; got: {result.stderr}"
    )


def test_succeeds_with_a_valid_stated_scripts_dir(tmp_path):
    """The negative control: a CORRECT --scripts-dir must NOT be refused.
    Without this, test_refuses_* above would still pass on a resolver that
    refuses everything unconditionally — a guard that always fails is not a
    guard. QC_SKIP_PRESENTATION_DEPS + the .test-context marker clear GATE 1
    (deps); --plan clears GATE 0 (intake ledger); the stub scripts have no
    sync_check.py / pin file so GATE 3 is a no-op; a stub run_signature_deck.py
    exits 0 so the whole chain completes successfully end to end."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "checkpoints" / ".test-context").write_text("")
    fake_scripts = _make_fake_scripts_dir(tmp_path)

    env = {
        "OPENCLAW_WORKSPACE": str(tmp_path / "no-such-workspace"),
        "QC_SKIP_PRESENTATION_DEPS": "1",
    }
    result = _run_entry(run_dir, ["--scripts-dir", str(fake_scripts)], env)

    assert result.returncode == 0, (
        f"a valid --scripts-dir must not be refused; got exit {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Refusing to autodetect" not in result.stderr
    assert f"canonical scripts: {fake_scripts}" in result.stdout, (
        f"expected the provenance banner naming {fake_scripts}; "
        f"got stdout: {result.stdout}"
    )
    assert "source: --scripts-dir" in result.stdout
