"""FIX 61 regression: install.sh must SCHEDULE a poller that can actually run.

Why this exists. Two independent defects let install.sh report a scheduled
intake poller while launchd was handed something that could never execute, and
both were silent — the installer printed a green check either way.

  1. EMPTY-PREFIX PATH. ``PRESENTATIONS_SCRIPTS_SRC`` was resolved from a
     SINGLE candidate (the repo checkout, ``$_SCRIPT_DIR/23-ai-workforce-
     blueprint/templates/role-library/presentations/scripts``). Run install.sh
     from anything that is not a full checkout — curl|bash, a trimmed payload,
     a re-run out of /tmp — and that candidate misses, the variable stays
     EMPTY, and ``"$PRESENTATIONS_SCRIPTS_SRC/presentation-intake-poll.sh"``
     collapses to the ROOT-ANCHORED literal ``/presentation-intake-poll.sh``.
     The installer then blamed a missing FILE when the real fault was an
     unresolved DIRECTORY, which is what sent the field diagnosis down the
     wrong path. An empty string is never a usable path prefix; it has to be
     rejected on its own terms, before it is concatenated into anything.

  2. UNRENDERED PLIST REPORTED AS RENDERED. The plist template stores its
     placeholders HTML-ESCAPED inside the XML body --
     ``<string>&lt;POLL_SCRIPT_PATH&gt;</string>`` -- and BARE only inside the
     comment header. The render's sed, and the residue check that guarded it,
     both matched the BARE spelling only. So the body was substituted NOTHING,
     the guard passed, the step printed "rendered ... launchctl load OK", and
     launchd received ``ProgramArguments = ["/bin/bash", "<POLL_SCRIPT_PATH>"]``
     -- a literal placeholder as a program path. The poller never ran, and
     nothing said so. A test that only asserts the BARE token is absent would
     have passed against that broken plist, so the checks below assert BOTH
     spellings and additionally require the file to parse as a property list.

Both legs are DYNAMIC: they extract the real scheduling block out of install.sh
and execute it against a sandboxed HOME with a stubbed ``launchctl``. A static
grep would pass on a comment that merely says the right words. A static leg is
kept as well, as a bleed test against the sed regressing to bare-only.

Nothing here touches the real ``$HOME``, the real LaunchAgents directory, or
the real launchctl: HOME is redirected to pytest's tmp_path and ``launchctl``
is a stub script placed first on PATH.
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
# scripts -> presentations -> role-library -> templates -> 23-ai-workforce-blueprint -> repo root
_REPO_ROOT = _SCRIPTS_DIR.parents[4]
INSTALL_SH = _REPO_ROOT / "install.sh"

# The two placeholders the shipped template carries, in BOTH spellings. The
# escaped pair is the one that actually appears in the XML body.
PLACEHOLDER_TOKENS = (
    "<POLL_SCRIPT_PATH>",
    "<LOG_PATH>",
    "&lt;POLL_SCRIPT_PATH&gt;",
    "&lt;LOG_PATH&gt;",
)

# Marker unique to the template's comment header. A rendered plist must not
# carry it: the header sits BEFORE the <?xml?> declaration, which is not
# well-formed XML, so a file that still has it will not parse as a plist.
TEMPLATE_HEADER_MARKER = "presentation-intake-poll.plist.template"

pytestmark = pytest.mark.skipif(
    not INSTALL_SH.is_file(),
    reason=(
        "install.sh is not present; this tests dir is also deployed into the "
        "materialized department, where the installer does not ship"
    ),
)


def _extract_bash_function(src: str, name: str) -> str:
    """Return `name() { ... }` from `src`, matched to its column-0 closing brace."""
    start = re.search(rf"^{re.escape(name)}\(\) \{{$", src, re.MULTILINE)
    if start is None:
        raise AssertionError(f"install.sh no longer defines {name}()")
    lines = src[start.start():].split("\n")
    for i, line in enumerate(lines):
        if i and line == "}":
            return "\n".join(lines[: i + 1])
    raise AssertionError(f"{name}() has no column-0 closing brace")


def _build_harness(tmp_path: Path) -> Path:
    """Extract install.sh's real scheduling block into a runnable script.

    The block runs verbatim under the same `set -euo pipefail` the installer
    uses, so errexit behaviour (which is what made the old failure silent) is
    reproduced rather than approximated.
    """
    src = INSTALL_SH.read_text(encoding="utf-8")
    lines = src.split("\n")

    begin = next(
        i for i, line in enumerate(lines) if line.startswith("install_intake_poll_schedule() {")
    )
    end = next(i for i, line in enumerate(lines) if line.strip() == "export _FIX61_RC")
    block = "\n".join(lines[begin : end + 1])

    preamble = [
        "#!/bin/bash",
        "set -euo pipefail",
        # real reporting helpers, lifted from install.sh itself
        _extract_bash_function(src, "step"),
        _extract_bash_function(src, "success"),
        _extract_bash_function(src, "warn"),
        _extract_bash_function(src, "error"),
        # the installer's Telegram progress hook is a network call; stub it
        'send_telegram_progress() { echo "[stub telegram] $*" >&2; }',
    ]
    harness = tmp_path / "harness.sh"
    harness.write_text("\n".join(preamble) + "\n" + block + "\n", encoding="utf-8")
    harness.chmod(0o755)
    return harness


def _run(tmp_path: Path, script_dir: Path, home: Path) -> subprocess.CompletedProcess:
    """Run the extracted block with a sandboxed HOME and a stubbed launchctl."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "launchctl"
    stub.write_text('#!/bin/bash\necho "[stub launchctl] $*" >&2\nexit 0\n', encoding="utf-8")
    stub.chmod(0o755)

    home.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["/bin/bash", str(_build_harness(tmp_path))],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(home),
            "OPENCLAW_PLATFORM": "mac",
            "_SCRIPT_DIR": str(script_dir),
        },
    )


def _rendered_plist(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / "com.blackceo.presentation-intake-poll.plist"


# ---------------------------------------------------------------------------
# LEG 1 — the empty prefix must never become a path
# ---------------------------------------------------------------------------
def test_unresolved_scripts_dir_never_builds_a_root_anchored_path(tmp_path):
    """With nothing resolvable, the installer must name the UNRESOLVED DIRECTORY.

    It must never report a root-anchored "/presentation-intake-poll.sh", which
    is the empty prefix silently concatenated into a filename.
    """
    empty_root = tmp_path / "not-a-checkout"
    empty_root.mkdir()
    proc = _run(tmp_path, script_dir=empty_root, home=tmp_path / "home")
    combined = proc.stdout + proc.stderr

    assert "at /presentation-intake-poll.sh" not in combined, (
        "install.sh still concatenates an empty PRESENTATIONS_SCRIPTS_SRC into "
        f"a filename, producing '/presentation-intake-poll.sh':\n{combined}"
    )
    assert "PRESENTATIONS_SCRIPTS_SRC is EMPTY" in combined, (
        "an unresolved scripts dir must be reported as an unresolved DIRECTORY, "
        f"not as a missing file:\n{combined}"
    )


def test_unresolved_scripts_dir_fails_the_install_loudly(tmp_path):
    """A box that cannot schedule the dispatcher must stop and say why."""
    empty_root = tmp_path / "not-a-checkout"
    empty_root.mkdir()
    proc = _run(tmp_path, script_dir=empty_root, home=tmp_path / "home")
    combined = proc.stdout + proc.stderr

    assert proc.returncode != 0, f"install continued past an unschedulable poller:\n{combined}"
    assert "ERROR" in combined, f"the failure was not raised as an error:\n{combined}"
    assert "NOT scheduled" in combined, f"the consequence was not stated:\n{combined}"


def test_materialized_department_is_a_fallback_source(tmp_path):
    """Outside a checkout, the deployed department is a legitimate source.

    This is the case that previously aborted the whole install.
    """
    empty_root = tmp_path / "not-a-checkout"
    empty_root.mkdir()
    home = tmp_path / "home"
    dept = home / ".openclaw" / "workspace" / "departments" / "Presentations" / "scripts"
    dept.mkdir(parents=True)
    for name in (
        "presentation-intake-poll.sh",
        "presentation-intake-poll.plist.template",
    ):
        (dept / name).write_bytes((_SCRIPTS_DIR / name).read_bytes())

    proc = _run(tmp_path, script_dir=empty_root, home=home)
    assert proc.returncode == 0, f"department fallback did not resolve:\n{proc.stdout}{proc.stderr}"
    plist = _rendered_plist(home)
    assert plist.is_file()
    assert str(dept) in plist.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# LEG 2 — the plist must be RENDERED, not copied
# ---------------------------------------------------------------------------
def test_rendered_plist_carries_no_placeholder_and_no_template_header(tmp_path):
    """The installed LaunchAgent must be a rendered artifact, not the template."""
    home = tmp_path / "home"
    proc = _run(tmp_path, script_dir=_REPO_ROOT, home=home)
    assert proc.returncode == 0, f"render path failed:\n{proc.stdout}{proc.stderr}"

    plist = _rendered_plist(home)
    assert plist.is_file(), "no plist was written"
    raw = plist.read_text(encoding="utf-8")

    for token in PLACEHOLDER_TOKENS:
        assert token not in raw, (
            f"the installed plist still contains the placeholder {token!r} — it was "
            "copied without being rendered, and launchd would exec a literal "
            "placeholder as a program path"
        )
    assert TEMPLATE_HEADER_MARKER not in raw, (
        "the installed plist still carries the template's comment header; that "
        "header precedes the <?xml?> declaration and makes the file unparseable "
        "as a property list"
    )


def test_rendered_plist_parses_and_points_at_a_real_script(tmp_path):
    """plistlib must accept the installed file, and the program must exist."""
    home = tmp_path / "home"
    proc = _run(tmp_path, script_dir=_REPO_ROOT, home=home)
    assert proc.returncode == 0, f"render path failed:\n{proc.stdout}{proc.stderr}"

    with _rendered_plist(home).open("rb") as fh:
        parsed = plistlib.load(fh)  # no sed workaround: it must parse as shipped

    assert parsed["Label"] == "com.blackceo.presentation-intake-poll"
    args = parsed["ProgramArguments"]
    poll_script = args[1]
    assert os.path.isabs(poll_script), f"program path is not absolute: {poll_script!r}"
    assert os.path.exists(poll_script), f"scheduled program does not exist: {poll_script!r}"
    assert os.path.isabs(parsed["StandardOutPath"])


# ---------------------------------------------------------------------------
# LEG 3 — static bleed test against the sed regressing to bare-only
# ---------------------------------------------------------------------------
def test_render_and_guard_cover_the_escaped_placeholder_spelling():
    """The body stores placeholders escaped; matching only the bare form is the bug."""
    src = INSTALL_SH.read_text(encoding="utf-8")
    block = _extract_bash_function(src, "install_intake_poll_schedule")

    for token in ("&lt;POLL_SCRIPT_PATH&gt;", "&lt;LOG_PATH&gt;"):
        assert token in block, (
            f"the render no longer substitutes {token!r}. The template stores its "
            "placeholders HTML-escaped inside the XML body, so a bare-only sed "
            "substitutes nothing there and launchd gets a literal placeholder."
        )


def test_template_still_stores_placeholders_escaped_in_the_body():
    """Pin the assumption the render depends on.

    If the template ever stops escaping its placeholders, the escaped-form sed
    above becomes dead and this test says so rather than letting the render
    quietly depend on a spelling that no longer exists.
    """
    template = _SCRIPTS_DIR / "presentation-intake-poll.plist.template"
    body = template.read_text(encoding="utf-8")
    body = body[body.index("<?xml"):]
    assert "&lt;POLL_SCRIPT_PATH&gt;" in body, (
        "template body no longer stores <POLL_SCRIPT_PATH> escaped; the render's "
        "escaped-form substitution must be revisited"
    )
