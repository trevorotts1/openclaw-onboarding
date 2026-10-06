"""Contract tests for wire.sh's venv-outside-skill-root migration.

Hermetic: no network, no real pip install. Each fake venv's `bin/python` is a
one-line shell stub (`exit 0` = healthy / importable, `exit 1` = unhealthy) —
wire.sh's `venv_ok()` probe and its `pip install` calls both just invoke
`$VENV_DIR/bin/python ...`, so the stub's exit code is all either path cares
about. A MARKER file inside each fake venv proves, after the run, which venv
(legacy or already-new) ended up live at the final path.
"""

import os
import shutil
import stat
import subprocess


def _setup_skills(tmp_path, skill_root):
    """Copy the real skill source into a throwaway skills/25-video-creator."""
    skills = tmp_path / "skills"
    shutil.copytree(skill_root, skills / "25-video-creator")
    return skills


def _make_fake_venv(path, healthy, marker):
    (path / "bin").mkdir(parents=True)
    script = path / "bin" / "python"
    script.write_text("#!/bin/sh\nexit {}\n".format(0 if healthy else 1))
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    (path / "MARKER").write_text(marker)


def _run_wire(skills, tmp_path):
    env = os.environ.copy()
    for var in ("VIDEO_CREATOR_DIR", "VENV_DIR", "PYTHON"):
        env.pop(var, None)
    return subprocess.run(
        ["bash", str(skills / "25-video-creator" / "wire.sh")],
        env=env,
        cwd=str(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_legacy_venv_only_is_moved_outside_skill_root(tmp_path, skill_root):
    skills = _setup_skills(tmp_path, skill_root)
    legacy = skills / "video-creator" / "venv"
    _make_fake_venv(legacy, healthy=True, marker="legacy-a")
    new_venv = tmp_path / "venvs" / "video-creator"

    result = _run_wire(skills, tmp_path)

    assert result.returncode == 0, result.stdout
    assert not legacy.exists(), "legacy venv must be gone (moved, not copied)"
    assert (new_venv / "MARKER").read_text() == "legacy-a"
    assert not (skills / "video-creator" / "venv").exists()
    assert (skills / "video-creator" / ".installed-from").exists()


def test_both_present_new_healthy_keeps_new_removes_legacy(tmp_path, skill_root):
    skills = _setup_skills(tmp_path, skill_root)
    legacy = skills / "video-creator" / "venv"
    _make_fake_venv(legacy, healthy=True, marker="legacy-b")
    new_venv = tmp_path / "venvs" / "video-creator"
    _make_fake_venv(new_venv, healthy=True, marker="new-b")

    result = _run_wire(skills, tmp_path)

    assert result.returncode == 0, result.stdout
    assert not legacy.exists(), "legacy venv must be removed once new is healthy"
    assert (new_venv / "MARKER").read_text() == "new-b", "healthy new venv must not be clobbered"


def test_both_present_new_unhealthy_legacy_replaces_it(tmp_path, skill_root):
    skills = _setup_skills(tmp_path, skill_root)
    legacy = skills / "video-creator" / "venv"
    _make_fake_venv(legacy, healthy=True, marker="legacy-c")
    new_venv = tmp_path / "venvs" / "video-creator"
    _make_fake_venv(new_venv, healthy=False, marker="new-c-broken")

    result = _run_wire(skills, tmp_path)

    assert result.returncode == 0, result.stdout
    assert not legacy.exists()
    assert (new_venv / "MARKER").read_text() == "legacy-c", (
        "the healthy legacy venv must replace the broken one at the new path"
    )


def test_runtime_copy_has_no_skill_md_and_never_gets_a_copied_venv(tmp_path, skill_root):
    skills = _setup_skills(tmp_path, skill_root)

    # A stale SKILL.md left over from an older install (pre-fix wire.sh used to
    # copy one in) must be removed, not just "not re-added".
    vc_dir = skills / "video-creator"
    vc_dir.mkdir(parents=True)
    (vc_dir / "SKILL.md").write_text("stale duplicate skill registration\n")

    # A venv accidentally built inside the SOURCE folder itself must never be
    # copied into the runtime copy.
    source_venv = skills / "25-video-creator" / "venv"
    _make_fake_venv(source_venv, healthy=True, marker="source-should-not-copy")

    # Pre-seed a healthy venv at the new (outside-skill-root) location so this
    # run never has to build one for real (hermetic: no network, no pip).
    new_venv = tmp_path / "venvs" / "video-creator"
    _make_fake_venv(new_venv, healthy=True, marker="pre-seeded")

    result = _run_wire(skills, tmp_path)

    assert result.returncode == 0, result.stdout
    assert not (vc_dir / "SKILL.md").exists(), "runtime copy must not register a 2nd skill"
    assert not (vc_dir / "venv").exists(), "a source-folder venv must never be copied into VC_DIR"
    assert (vc_dir / "scripts" / "text_to_video.py").exists()


if __name__ == "__main__":
    # ponytail: smallest runnable self-check, exercised via pytest above; this
    # __main__ block just proves the helper functions are wired correctly when
    # run directly (`python3 test_wire_contracts.py`) without a pytest fixture.
    import pathlib
    import sys

    _skill_root = pathlib.Path(__file__).resolve().parents[1]
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        _tmp = pathlib.Path(td)
        test_legacy_venv_only_is_moved_outside_skill_root(_tmp, _skill_root)
    print("demo OK: legacy-venv migration self-check passed")
    sys.exit(0)
