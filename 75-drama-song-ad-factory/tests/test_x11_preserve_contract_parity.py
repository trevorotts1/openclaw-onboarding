#!/usr/bin/env python3
"""S75-X11 preserve contract: install.sh and update-skills.sh meet ONE contract.

Run directly:  python3 -I tests/test_x11_preserve_contract_parity.py   (also collects as pytest)

x11_install_gate.sh's warn text promises "manifest-targeted skill-75 files are
kept, never deleted". That promise is only true if each caller consults
`preserve-list` and puts back what the release does not ship. update-skills.sh
did; install.sh did not (S75-018). This asserts both do, then runs install.sh's
real extracted skill-75 region in warn mode and checks the file survives.

FAILS on the pre-fix tree: install.sh's region has no `preserve-list` call and
no restore step.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(SKILL_ROOT)
NAME = "75-drama-song-ad-factory"

GATE_BEGIN = "# >>> X11-GATE-BEGIN"
GATE_END = "# <<< X11-GATE-END"
RESTORE_END = "# <<< X11-GATE-RESTORE-END"


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("S75_X11_")}
    env.update(extra)
    return env


def update_region():
    text = open(os.path.join(REPO, "update-skills.sh"), encoding="utf-8").read()
    return text[text.index(GATE_BEGIN):text.index(GATE_END)]


def install_region():
    """Gate + stash + the real per-item overlay copy + the restore step."""
    text = open(os.path.join(REPO, "install.sh"), encoding="utf-8").read()
    return text[text.index(GATE_BEGIN):text.index(RESTORE_END) + len(RESTORE_END)]


def install_gate_region():
    """Gate + stash only (ends before the copy, so the stash is observable)."""
    text = open(os.path.join(REPO, "install.sh"), encoding="utf-8").read()
    return text[text.index(GATE_BEGIN):text.index(GATE_END)]


def test_both_callers_consult_preserve_list():
    for label, region in (("update-skills.sh", update_region()),
                          ("install.sh", install_region())):
        assert "x11_install_gate.sh\" preserve-list" in region, label


def test_both_callers_put_the_listed_files_back():
    for label, region in (("update-skills.sh", update_region()),
                          ("install.sh", install_region())):
        assert "_x11_keep" in region, label
        assert "-e \"$SKILLS_DIR/$SKILL_NAME/$_x11_rel\"" in region, label
        assert "cp -p \"$_x11_keep/$_x11_rel\"" in region, label


INSTALL_HARNESS = r'''
warn() { echo "WARN: $*"; }
note() { echo "NOTE: $*"; }
LOG_FILE=/dev/null
SKILL_DIR="$SRC/"
SKILL_NAME="%s"
for _once in 1; do
%s
echo REACHED_COPY
done
'''


def run_install(env_extra, records, live_files=None):
    work = tempfile.mkdtemp(prefix="x11-parity-inst-")
    src = os.path.join(work, "src", NAME)
    os.makedirs(os.path.join(src, "scripts", "core"))
    for f in ("x11_install_gate.sh", "release_gate_cli.py", "apply_release_gate.py"):
        with open(os.path.join(SKILL_ROOT, "scripts", "core", f), "rb") as r, \
             open(os.path.join(src, "scripts", "core", f), "wb") as w:
            w.write(r.read())
    open(os.path.join(src, "new.txt"), "w").write("new")
    skills = os.path.join(work, "skills")
    live = os.path.join(skills, NAME)
    os.makedirs(live)
    open(os.path.join(live, "stale-local.txt"), "w").write("keep me")
    for name, body in (live_files or {}).items():
        open(os.path.join(live, name), "w").write(body)
    script = INSTALL_HARNESS % (NAME, install_region())
    proc = subprocess.run(["bash", "-c", "set -e\n" + script], capture_output=True, text=True,
                          env=clean_env(SRC=src, SKILLS_DIR=skills,
                                        S75_X11_RECORDS_DIR=records, **env_extra))
    return proc, live


def test_install_stashes_the_manifest_targeted_file_the_gate_names():
    """The stash half: the gate's list really is consumed before the copy."""
    rec = tempfile.mkdtemp(prefix="x11-parity-rec-")
    json.dump({"files": [{"path": "stale-local.txt", "sha256": "0" * 64, "action": "delete"}]},
              open(os.path.join(rec, "reviewed-manifest.json"), "w"))
    work = tempfile.mkdtemp(prefix="x11-parity-stash-")
    src = os.path.join(work, "src", NAME)
    os.makedirs(os.path.join(src, "scripts", "core"))
    for f in ("x11_install_gate.sh", "release_gate_cli.py", "apply_release_gate.py"):
        with open(os.path.join(SKILL_ROOT, "scripts", "core", f), "rb") as r, \
             open(os.path.join(src, "scripts", "core", f), "wb") as w:
            w.write(r.read())
    skills = os.path.join(work, "skills")
    live = os.path.join(skills, NAME)
    os.makedirs(live)
    open(os.path.join(live, "stale-local.txt"), "w").write("keep me")
    script = (
        'warn() { echo "WARN: $*"; }\n'
        'LOG_FILE=/dev/null\n'
        'SKILL_DIR="$SRC/"\n'
        'SKILL_NAME="%s"\n'
        'for _once in 1; do\n%s\necho "STASHED=$(cd "$_x11_keep" 2>/dev/null && find . -type f | sort | tr "\\n" ",")"\n'
        'rm -rf "$_x11_keep"\ndone\n'
    ) % (NAME, install_gate_region())
    proc = subprocess.run(["bash", "-c", "set -e\n" + script], capture_output=True, text=True,
                          env=clean_env(SRC=src, SKILLS_DIR=skills,
                                        S75_X11_RECORDS_DIR=rec))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "STASHED=./stale-local.txt," in proc.stdout, out


def test_install_warn_mode_keeps_manifest_targeted_file_and_says_so():
    rec = tempfile.mkdtemp(prefix="x11-parity-rec-")
    json.dump({"schema": "s75.x11.reviewed-manifest/v1", "files": [
        {"path": "stale-local.txt", "sha256": "0" * 64, "action": "delete"},
        {"path": "../escape.txt", "sha256": "0" * 64, "action": "modify"}]},
        open(os.path.join(rec, "reviewed-manifest.json"), "w"))
    proc, live = run_install({}, rec)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0 and "REACHED_COPY" in proc.stdout, out
    assert "WARN" in proc.stdout, out
    assert os.path.exists(os.path.join(live, "stale-local.txt")), out
    assert open(os.path.join(live, "stale-local.txt")).read() == "keep me", out
    assert os.path.exists(os.path.join(live, "new.txt")), out
    assert not os.path.exists(os.path.join(os.path.dirname(live), "escape.txt")), out


def test_install_shipped_file_still_wins_over_targeted_stale_copy():
    rec = tempfile.mkdtemp(prefix="x11-parity-rec-")
    json.dump({"files": [{"path": "new.txt", "sha256": "0" * 64, "action": "modify"}]},
              open(os.path.join(rec, "reviewed-manifest.json"), "w"))
    proc, live = run_install({}, rec, live_files={"new.txt": "OLD"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert open(os.path.join(live, "new.txt")).read() == "new", proc.stdout


def test_install_refuse_mode_still_skips_skill():
    proc, live = run_install({"S75_X11_GATE_MODE": "refuse"}, tempfile.mkdtemp())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "REACHED_COPY" not in proc.stdout
    assert "REFUSED skill 75" in proc.stdout


def test_both_scripts_parse():
    for f in ("install.sh", "update-skills.sh"):
        subprocess.run(["bash", "-n", os.path.join(REPO, f)], check=True)


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(exc))
    print("X11_PRESERVE_PARITY legs=%d failures=%d" % (len(tests), fails))
    sys.exit(1 if fails else 0)
