"""PRES-035 fix61 sandbox regression: installer succeeds via repo resolution.

Why this file exists. W1 (ba2dead07, Opus) pinned ONE validated pipeline
interpreter, resolving through presentation_job/pipeline_interp.py. That
module lives in the canonical CHECKOUT (beside lib-presentation-schedules.sh),
not in the scheduled scripts dir the installer points at — which on a box
mid-remediation holds poll.sh + template only. The bare
``cd <dept-dir> && python3 -m presentation_job.pipeline_interp --resolve``
then dies ModuleNotFoundError rc=1 (field failure), the installer aborts
UNRESOLVED, and the resumed independent QC verdict (pres035 FAIL) names
fix61 5/16 failing at HEAD vs 16/16 at base.

This leg pins the REPAIRED behavior, dynamic against the real installer code:

  Leg 1 — full-dept sandbox: a materialized department WITH the module tree
  resolves through the repo-scripts-dir path and the installer SUCCEEDS
  (rc 0, plist rendered, pin env carried).
  Leg 2 — sandbox-only dir: poll.sh + template only, NO presentation_job/.
  The installer STILL succeeds via the repaired resolution path — this is
  the field failure made green, not a skip.
  Leg 3 — truly unresolvable: module absent from BOTH the scheduled dir AND
  the repo checkout. The installer fails LOUD ("interpreter UNRESOLVED",
  rc != 0, no plist) — never a silent skip, never an unpinned render.

The harness reassembles the real scheduling block from
lib-presentation-schedules.sh (the FIX 61 installer plus the two PRES-035
resolver helpers that sit above the slice), exactly like the fix61 leg does.
DISJOINT-SLICE NOTE: Writer1 owns lib-presentation-schedules.sh,
presentation_job/pipeline_interp.py and the launcher/supervisor/autospawn
helpers — this file asserts behavior THROUGH them and imports nothing from
them except pipeline_interp's public INTERPRETER_ENV/FLAG_ENV names via
sys.path (read-only; no edits to code under test anywhere in this file).
Nothing here touches the real $HOME or the real launchctl.
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
# scripts -> presentations -> role-library -> templates -> 23-ai-workforce-blueprint -> repo root
_REPO_ROOT = _SCRIPTS_DIR.parents[4]
INSTALL_SH = _REPO_ROOT / "install.sh"
SCHEDULES_LIB = _REPO_ROOT / "lib-presentation-schedules.sh"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from presentation_job import pipeline_interp as pi  # noqa: E402  (names only)

PIN_ENV = pi.INTERPRETER_ENV
ROLLBACK_ENV = pi.FLAG_ENV

pytestmark = pytest.mark.skipif(
    not (INSTALL_SH.is_file() and SCHEDULES_LIB.is_file()),
    reason=(
        "install.sh / lib-presentation-schedules.sh are not present; this tests "
        "dir is also deployed into the materialized department, where the "
        "installer does not ship"
    ),
)


def _extract_bash_function(src: str, name: str) -> str:
    """Return `name() { ... }` from `src`, matched to its column-0 closing brace."""
    start = re.search(rf"^{re.escape(name)}\(\) \{{$", src, re.MULTILINE)
    if start is None:
        raise AssertionError(f"the extracted source no longer defines {name}()")
    lines = src[start.start():].split("\n")
    for i, line in enumerate(lines):
        if i and line == "}":
            return "\n".join(lines[: i + 1])
    raise AssertionError(f"{name}() has no column-0 closing brace")


def _build_harness(tmp_path: Path, resolver: str = "", source_lib: bool = True) -> Path:
    """Extract the real intake-poll scheduling block into a runnable script.

    Same reassembly as the fix61 leg: the moved FIX 61 block from
    lib-presentation-schedules.sh, plus install.sh's own resolver line and
    _FIX61_RC latch. Runs verbatim under the installer's `set -euo pipefail`.

    source_lib=True (legs 1-2, rollback): the harness SOURCES the real lib,
    exactly like install.sh does. This is load-bearing, not a shortcut: the
    PRES-035 Fallback-1 checkout lookup derives from the lib's own
    BASH_SOURCE, so a textually extracted copy would point the fallback at
    the tmp harness dir and manufacture an UNRESOLVED the installer can
    never exhibit. Sourcing keeps the real BASH_SOURCE.
    source_lib=False (leg 3): the two PRES-035 helpers are carried verbatim
    (as the fix61 leg does), so the harness file itself stands in for a
    checkout whose tree lacks the module — the "nowhere" case.
    """
    src = INSTALL_SH.read_text(encoding="utf-8")
    lib_src = SCHEDULES_LIB.read_text(encoding="utf-8")
    lines = src.split("\n")
    lib_lines = lib_src.split("\n")
    lib_begin = next(
        i for i, line in enumerate(lib_lines)
        if line.startswith("install_intake_poll_schedule() {")
    )
    last_fn = next(
        i for i, line in enumerate(lib_lines)
        if line.startswith("_fix61_resolve_scripts_src() {")
    )
    lib_end = next(i for i, line in enumerate(lib_lines) if i > last_fn and line == "}")
    functions = "\n".join(lib_lines[lib_begin : lib_end + 1])
    if not source_lib:
        functions += "\n" + _extract_bash_function(lib_src, "_pres35_module_scripts_dir")
        functions += "\n" + _extract_bash_function(lib_src, "_pres35_resolve_interpreter")
    begin = next(
        i for i, line in enumerate(lines)
        if line.startswith('PRESENTATIONS_SCRIPTS_SRC="$(_fix61_resolve_scripts_src')
    )
    end = next(i for i, line in enumerate(lines) if line.strip() == "export _FIX61_RC")
    block = functions + "\n" + "\n".join(lines[begin : end + 1])

    preamble = [
        "#!/bin/bash",
        "set -euo pipefail",
        _extract_bash_function(src, "step"),
        _extract_bash_function(src, "success"),
        _extract_bash_function(src, "warn"),
        _extract_bash_function(src, "error"),
        'send_telegram_progress() { echo "[stub telegram] $*" >&2; }',
    ]
    if source_lib:
        # Install.sh sources this same file; the harness must too, so the
        # BASH_SOURCE-derived checkout fallback resolves identically.
        preamble.append(f'source "{SCHEDULES_LIB}"')
    harness = tmp_path / "fix61-sandbox-harness.sh"
    harness.write_text("\n".join(preamble) + "\n" + resolver + "\n" + block + "\n", encoding="utf-8")
    harness.chmod(0o755)
    return harness


def _run(tmp_path: Path, script_dir: Path, home: Path, extra_env=None, resolver="",
         source_lib: bool = True) -> subprocess.CompletedProcess:
    """Run the extracted block with a sandboxed HOME and a stubbed launchctl."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "launchctl"
    stub.write_text('#!/bin/bash\necho "[stub launchctl] $*" >&2\nexit 0\n', encoding="utf-8")
    stub.chmod(0o755)
    home.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["/bin/bash", str(_build_harness(tmp_path, resolver, source_lib))],
        capture_output=True,
        text=True,
        timeout=20,
        env={
            "PATH": f"{bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(home),
            "OPENCLAW_PLATFORM": "mac",
            "_SCRIPT_DIR": str(script_dir),
            **(extra_env or {}),
        },
    )


def _rendered_plist(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / "com.blackceo.presentation-intake-poll.plist"


def _sandbox_only_dept(workspace: Path) -> Path:
    """A mid-remediation department: poll.sh + template ONLY, no module tree.

    This is the field shape — the resolver must NOT need
    presentation_job/ here; it re-locates the module to the repo checkout.
    """
    dept = workspace / "departments" / "Presentations" / "scripts"
    dept.mkdir(parents=True)
    for name in ("presentation-intake-poll.sh", "presentation-intake-poll.plist.template"):
        (dept / name).write_bytes((_SCRIPTS_DIR / name).read_bytes())
    assert not (dept / "presentation_job").exists()
    return dept


# ---------------------------------------------------------------------------
# Leg 1 — full-dept sandbox resolves through the repo path and succeeds
# ---------------------------------------------------------------------------
def test_full_dept_sandbox_installs_with_repo_resolution(tmp_path):
    """Module present beside the scheduled dir: installer succeeds, pin carried."""
    empty_root = tmp_path / "not-a-checkout"
    empty_root.mkdir()
    home = tmp_path / "home"
    workspace = tmp_path / "client workspace"
    dept = _sandbox_only_dept(workspace)
    (dept / "presentation_job").mkdir()
    for name in ("__init__.py", "pipeline_interp.py", "oc_paths.py"):
        (dept / "presentation_job" / name).write_bytes(
            (_SCRIPTS_DIR / "presentation_job" / name).read_bytes()
        )
    proc = _run(tmp_path, empty_root, home,
                {"OPENCLAW_ROOT": str(tmp_path / "client-root"),
                 "OPENCLAW_WORKSPACE_ROOT": str(workspace)})
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"full-dept sandbox refused:\n{combined}"
    plist = _rendered_plist(home)
    assert plist.is_file(), f"no plist rendered:\n{combined}"
    data = plistlib.loads(plist.read_bytes())
    pin = data["EnvironmentVariables"].get(PIN_ENV, "")
    assert pin.startswith("/"), f"rendered pin is not absolute: {pin!r}"
    # The installer suppresses launchctl's own output (>/dev/null 2>&1), so
    # the stub leaves no marker — the success line is the load proof.
    assert "launchctl load OK" in combined or "already loaded" in combined, combined


# ---------------------------------------------------------------------------
# Leg 2 — sandbox-only dir (the field failure) still succeeds after repair
# ---------------------------------------------------------------------------
def test_sandbox_only_dir_succeeds_via_repo_scripts_dir_path(tmp_path):
    """poll.sh + template only: success, not UNRESOLVED — the repaired path.

    Pre-repair this exact shape died: `cd <dept> && python3 -m
    presentation_job.pipeline_interp --resolve` -> ModuleNotFoundError rc=1
    -> installer aborted UNRESOLVED. The repair re-locates the module to the
    repo checkout; the pin still resolves through the module's own untouched
    precedence (override -> client venv -> PATH), so success here proves the
    resolution PATH, not a skip.
    """
    empty_root = tmp_path / "not-a-checkout"
    empty_root.mkdir()
    home = tmp_path / "home"
    workspace = tmp_path / "sandbox client"
    _sandbox_only_dept(workspace)
    proc = _run(tmp_path, empty_root, home,
                {"OPENCLAW_ROOT": str(tmp_path / "client-root"),
                 "OPENCLAW_WORKSPACE_ROOT": str(workspace)})
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, (
        "sandbox-only installer still aborts — the field failure is NOT "
        f"repaired:\n{combined}"
    )
    assert "interpreter UNRESOLVED" not in combined, (
        f"sandbox-only dir reported UNRESOLVED after repair:\n{combined}"
    )
    plist = _rendered_plist(home)
    assert plist.is_file(), f"no plist rendered from sandbox-only dir:\n{combined}"
    data = plistlib.loads(plist.read_bytes())
    pin = data["EnvironmentVariables"].get(PIN_ENV, "")
    assert os.path.isabs(pin), f"rendered pin is not absolute: {pin!r}"
    assert os.access(pin, os.X_OK), f"rendered pin is not executable: {pin!r}"
    assert "launchctl load OK" in combined or "already loaded" in combined, combined


# ---------------------------------------------------------------------------
# Leg 3 — truly unresolvable fails LOUD, never silent, never unpinned
# ---------------------------------------------------------------------------
def test_truly_unresolvable_module_fails_loud_without_plist(tmp_path):
    """Module absent from the scheduled dir AND the repo checkout: loud fail.

    Reached by pointing the lib's Fallback-1 checkout at an empty repo root:
    _SCRIPT_DIR is a bare dir (no 23-ai-workforce-blueprint tree), the
    scheduled dept has no module, and the selected workspace has no module
    either. No plist may be promoted and no launchctl call may happen.
    """
    bare = tmp_path / "bare-no-checkout"
    bare.mkdir()
    home = tmp_path / "home"
    workspace = tmp_path / "ws-nomodule"
    _sandbox_only_dept(workspace)
    # source_lib=False: the harness file itself stands in for a checkout
    # whose tree lacks the module (BASH_SOURCE fallback finds no
    # presentation_job/), so NEITHER the scheduled dir NOR the checkout can
    # supply the authority. The selected workspace dept has no module either.
    proc = _run(tmp_path, bare, home,
                {"OPENCLAW_ROOT": str(tmp_path / "client-root"),
                 "OPENCLAW_WORKSPACE_ROOT": str(workspace)},
                source_lib=False)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        f"installer SUCCEEDED with no module anywhere — an unpinned render "
        f"or silent skip slipped through:\n{combined}"
    )
    assert "interpreter UNRESOLVED" in combined, (
        f"failure did not name the interpreter as the cause:\n{combined}"
    )
    assert not _rendered_plist(home).exists(), (
        "invalid candidate became the active plist"
    )
    assert "[stub launchctl]" not in combined, (
        "launchctl ran despite an unresolved interpreter"
    )


def test_rollback_flag_zero_still_refuses_unpinned_render(tmp_path):
    """PRESENTATION_PIPELINE_PIN=0 does not smuggle in an unpinned render.

    The documented rollback restores pre-fix PATH behavior — and the repaired
    installer treats "no pin" as UNRESOLVED (prior plist kept), never as a
    green unpinned schedule.
    """
    empty_root = tmp_path / "not-a-checkout"
    empty_root.mkdir()
    home = tmp_path / "home"
    workspace = tmp_path / "rollback client"
    _sandbox_only_dept(workspace)
    proc = _run(tmp_path, empty_root, home,
                {"OPENCLAW_ROOT": str(tmp_path / "client-root"),
                 "OPENCLAW_WORKSPACE_ROOT": str(workspace),
                 ROLLBACK_ENV: "0"})
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        f"rollback=0 produced a successful schedule with no pin:\n{combined}"
    )
    assert not _rendered_plist(home).exists()
