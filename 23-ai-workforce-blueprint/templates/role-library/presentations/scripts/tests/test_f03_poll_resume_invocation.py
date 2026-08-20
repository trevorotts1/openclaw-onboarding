"""F03 regression: presentation-intake-poll.sh's --resume dispatch must invoke
launcher.py as a MODULE, never by file path.

Why this exists: launcher.py is a member of the presentation_job package and
imports its siblings with a relative import (`from .vocab import
normalize_presentation_type, UnknownPresentationType`). Invoking it by file
path (`python3 "$SCRIPTS_DIR/presentation_job/launcher.py"`) makes Python
treat it as a parentless top-level script -- there is no package context for
"." to resolve against -- so that import dies INSTANTLY:

    ImportError: attempted relative import with no known parent package

Proven on this box before the fix:
    python3 presentation_job/launcher.py --check --run-dir <run>   -> ImportError
    python3 -m presentation_job.launcher --check --run-dir <run>   -> runs cleanly

presentation-intake-poll.sh is the 5-minute production cron that resumes a
parked engine job (`python3 "$LAUNCHER" --resume --run-dir "$run_dir"`). Every
single --resume dispatch through the old file-path form died the same way,
silently (the traceback only ever reached the poller's own log file), so a
parked job could never actually resume -- a fail-closed-in-the-worst-way
defect in the department's own automation.

The fix runs launcher.py as a module instead: `python3 -m
presentation_job.launcher --resume --run-dir "$run_dir"`, executed with
SCRIPTS_DIR (the package's PARENT directory) as the working directory --
`-m` requires that, since `python -m pkg.mod` inserts the CURRENT working
directory into sys.path[0], not the target module's own directory.

This test has three legs, mirroring tests/test_canonical_entry_scripts_dir.py:

  1. STATIC   -- the shipped --resume dispatch command must use `-m
                 presentation_job.launcher`, never `"$LAUNCHER"` (file path).
  2. DYNAMIC  -- actually extract that command VERBATIM from the shipped
                 script and execute it (not a hand-written stand-in) against
                 a scratch run-dir. This is the whole point: the reason this
                 defect survived is that nothing ever ran the real line.
  3. NEGATIVE CONTROL -- revert a SCRATCH COPY (never the worktree) of the
                 dispatch line back to the pre-fix file-path form and confirm
                 the same extract-and-execute harness actually catches the
                 ImportError. This proves leg 2 is not vacuous -- it is
                 capable of failing on the real historical bug, not just
                 capable of passing on the current text.

Every leg here is safe to run repeatedly and unattended: the scratch run-dir
used in legs 2 and 3 deliberately has NO state.json, and launcher.py's
dispatch_resume() checks for state.json as its very first act, returning
before ever spawning a child process (see presentation_job/launcher.py). So
this test can never launch the real engine, touch a renderer, or make a
Kie.ai call -- it only proves the import chain resolves and real application
code executes.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
POLL_SCRIPT = _SCRIPTS_DIR / "presentation-intake-poll.sh"
LAUNCHER = _SCRIPTS_DIR / "presentation_job" / "launcher.py"

# Captures the shell command between the "resuming parked job" log line and
# the `2>&1 | while` pipe that streams its output into the poller's log --
# i.e. exactly the invocation the poller uses to dispatch --resume. Matches
# both the pre-fix file-path form and the post-fix module form, so this same
# extraction logic works on either shape of the script (see leg 3 below).
_RESUME_DISPATCH_RE = re.compile(
    r'log "resuming parked job: \$run_dir"\s*\n\s*'
    r'(?P<cmd>.*?python3.*?--resume --run-dir "\$run_dir".*?)'
    r'\s*2>&1 \| while',
    re.S,
)


def _extract_resume_dispatch_command(src: str) -> str:
    m = _RESUME_DISPATCH_RE.search(src)
    assert m, (
        "could not find the --resume dispatch invocation in the poll "
        "script -- has its shape changed? (regex: "
        f"{_RESUME_DISPATCH_RE.pattern!r})"
    )
    return m.group("cmd").strip()


def _run_resume_dispatch(script_src: str, run_dir: Path) -> subprocess.CompletedProcess:
    """Extract the poller's REAL --resume dispatch command out of
    `script_src` and actually execute it -- substituting only the shell
    variables the poller itself would already have substituted at that
    point in its own execution ($LAUNCHER, $SCRIPTS_DIR, $run_dir) -- rather
    than reimplementing an equivalent command by hand."""
    cmd = _extract_resume_dispatch_command(script_src)
    cmd = cmd.replace('"$LAUNCHER"', f'"{LAUNCHER}"')
    cmd = cmd.replace('"$SCRIPTS_DIR"', f'"{_SCRIPTS_DIR}"')
    cmd = cmd.replace('"$run_dir"', f'"{run_dir}"')
    return subprocess.run(
        ["bash", "-c", cmd],
        cwd=str(_SCRIPTS_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_poll_script_and_launcher_exist():
    assert POLL_SCRIPT.is_file(), f"poll script not found at {POLL_SCRIPT}"
    assert LAUNCHER.is_file(), f"launcher.py not found at {LAUNCHER}"


def test_poll_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(POLL_SCRIPT)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, (
        f"bash -n failed on {POLL_SCRIPT}:\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 1. STATIC -- the dispatch command must be the module form.
# ---------------------------------------------------------------------------

def test_resume_dispatch_is_module_form_not_file_path():
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    cmd = _extract_resume_dispatch_command(src)
    assert "-m presentation_job.launcher" in cmd, (
        f"--resume dispatch does not invoke launcher.py as a module: {cmd!r}"
    )
    assert '"$LAUNCHER"' not in cmd, (
        f"--resume dispatch still invokes launcher.py by file path: {cmd!r}"
    )


# ---------------------------------------------------------------------------
# 2. DYNAMIC -- actually run the extracted line; do not just read it.
# ---------------------------------------------------------------------------

def test_resume_dispatch_actually_imports_and_runs(tmp_path):
    run_dir = tmp_path / "pres-f03-scratch"
    run_dir.mkdir()
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    result = _run_resume_dispatch(src, run_dir)

    combined = result.stdout + result.stderr
    assert "ImportError" not in combined, (
        "the poller's real --resume dispatch line ImportErrors -- "
        f"launcher.py is being invoked by file path, not as a module.\n"
        f"command output:\n{combined}"
    )
    assert "attempted relative import" not in combined, combined
    # Proves execution got PAST the import and into real application logic
    # (not a vacuous pass because the command silently did nothing / the
    # shell failed to even launch it).
    assert "no state.json" in combined and "cannot resume" in combined, (
        "expected launcher.py's real 'no state.json ... cannot resume' "
        f"message (proving actual execution, not a no-op); got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# 3. NEGATIVE CONTROL -- non-vacuousness proof, permanently in the suite.
# ---------------------------------------------------------------------------

def test_broken_file_path_form_would_have_been_caught(tmp_path):
    """Revert a SCRATCH COPY (never the worktree -- fixed_src is read from
    disk but never written back) of the --resume dispatch line to the
    pre-fix file-path form, run it through the exact same
    _run_resume_dispatch harness leg 2 uses, and confirm it fails with the
    real ImportError. Guards the guard: if leg 2 were ever weakened into a
    vacuous pass, this test still proves the harness is capable of catching
    the actual historical bug."""
    fixed_src = POLL_SCRIPT.read_text(encoding="utf-8")
    old_cmd = 'python3 "$LAUNCHER" --resume --run-dir "$run_dir"'

    m = _RESUME_DISPATCH_RE.search(fixed_src)
    assert m, "could not locate the --resume dispatch block to revert"
    broken_src = fixed_src[: m.start("cmd")] + old_cmd + fixed_src[m.end("cmd") :]
    assert broken_src != fixed_src, "failed to synthesize the reverted scratch copy"
    assert 'python3 "$LAUNCHER"' in _extract_resume_dispatch_command(broken_src)

    run_dir = tmp_path / "pres-f03-scratch-negctrl"
    run_dir.mkdir()
    result = _run_resume_dispatch(broken_src, run_dir)
    combined = result.stdout + result.stderr

    assert "ImportError" in combined and "attempted relative import" in combined, (
        "negative control did NOT reproduce the ImportError on the reverted "
        "scratch copy -- the extract-and-execute harness above may not "
        f"actually be exercising real execution.\ncommand output:\n{combined}"
    )


# ---------------------------------------------------------------------------
# 4. PATH hardening (F03 secondary finding): bare `python3` must resolve
#    consistently even under a minimal cron/launchd PATH.
# ---------------------------------------------------------------------------

def test_script_exports_a_hardened_path_before_any_python3_call():
    """cron/launchd runs this script with a minimal PATH (observed on this
    box: /usr/bin:/bin:/usr/sbin:/sbin has no /opt/homebrew/bin). A bare
    `python3` under that PATH still resolves -- macOS ships a stub at
    /usr/bin/python3 -- but SILENTLY to a different interpreter than the one
    this codebase is developed against. The script must export a PATH that
    puts the homebrew locations first, and it must do so before the first
    bare `python3` invocation."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    path_export = re.search(r'^export PATH=.*$', src, re.M)
    assert path_export, "no explicit `export PATH=` hardening found in the poll script"
    # Only count REAL invocations (`python3 -c`, `python3 "...`), not the
    # word "python3" appearing inside a comment -- e.g. this test file's own
    # header, or the hardening comment above the export line itself.
    invocation = re.search(r'^\s*python3[\s"]', src, re.M)
    assert invocation, "no bare `python3` invocation found in the poll script"
    assert path_export.start() < invocation.start(), (
        "PATH export must appear before the first bare `python3` invocation "
        f"(export at offset {path_export.start()}, invocation at "
        f"{invocation.start()})"
    )


def test_hardened_path_resolves_python3_under_minimal_cron_path():
    """DYNAMIC: actually source the script's PATH-export line under a
    genuinely minimal env (no /opt/homebrew/bin, matching what `env -i`
    plus a bare PATH reproduces for cron/launchd) and confirm `python3`
    still resolves to a concrete interpreter afterward."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    m = re.search(r'^export PATH=.*$', src, re.M)
    assert m, "no explicit `export PATH=` hardening found in the poll script"
    export_line = m.group(0)

    result = subprocess.run(
        ["bash", "-c", f"{export_line}\ncommand -v python3"],
        env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0 and result.stdout.strip(), (
        f"python3 did not resolve after sourcing the hardened PATH export "
        f"under a minimal cron-like environment.\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
