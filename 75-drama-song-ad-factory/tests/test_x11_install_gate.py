#!/usr/bin/env python3
"""S75-X11 call-site proofs: install.sh / update-skills.sh -> x11_install_gate.sh.

Run directly:  python3 -I tests/test_x11_install_gate.py   (also collects as pytest)

Two modes are proven. Default (no s75.x11.backup-authorization/v1 record, no env
flag) is warn-and-preserve: logged, never a hard fail, files named in the reviewed
manifest are kept (no manifest = update behaves exactly as before). Refuse
mode (record present, or S75_X11_GATE_MODE=refuse) leaves skill 75 untouched when
the gate says no. The real shell blocks are extracted between X11-GATE markers
and executed, so this tests the shipped call sites, not a copy. The
update-skills.sh region runs to the X11-GATE-TAIL-END marker inside a one-pass
loop, so the gate's own `continue` - which skips the pin, verify and 'Updated'
steps - is proven, not simulated. All synthetic.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_x11_release_gate_wiring as wiring  # noqa: E402

SKILL_ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(SKILL_ROOT)
GATE_SH = os.path.join(SKILL_ROOT, "scripts", "core", "x11_install_gate.sh")
NAME = "75-drama-song-ad-factory"


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("S75_X11_")}
    env.update(extra)
    return env


def gate(env_extra=None, records=None):
    root = tempfile.mkdtemp(prefix="x11-gate-")
    rec = records or os.path.join(root, "records")
    proc = subprocess.run(["bash", GATE_SH], capture_output=True, text=True,
                          env=clean_env(S75_X11_RECORDS_DIR=rec, **(env_extra or {})))
    return proc.returncode, proc.stdout + proc.stderr, rec


def valid_records():
    rec = tempfile.mkdtemp(prefix="x11-gate-rec-")
    wiring.records(rec)
    return rec


def block(path, end_marker="# <<< X11-GATE-END"):
    """Text between the X11-GATE-BEGIN marker and end_marker (exclusive).

    install.sh stops at X11-GATE-END. update-skills.sh runs on to
    X11-GATE-TAIL-END so the `continue` that follows its end marker is part of
    the extracted text and can be exercised inside a one-pass loop."""
    text = open(os.path.join(REPO, path), encoding="utf-8").read()
    a = text.index("# >>> X11-GATE-BEGIN")
    b = text.index(end_marker)
    return text[text.index("\n", a) + 1:b]


# ---- gate script: warn-and-preserve (default) -------------------------------
def test_default_no_record_is_warn_and_preserve():
    rc, out, _ = gate()
    assert rc == 10, (rc, out)
    assert "WARN" in out and "never deleted" in out, out


def test_default_incomplete_records_still_warn_not_fail():
    rec = tempfile.mkdtemp(prefix="x11-gate-rec-")
    wiring.records(rec)
    os.remove(os.path.join(rec, "backup-authorization.json"))
    os.remove(os.path.join(rec, "preservation.json"))  # gate would refuse
    rc, out, _ = gate(records=rec)
    assert rc == 10, (rc, out)


# ---- gate script: refuse mode -----------------------------------------------
def test_env_flag_enables_refuse():
    rc, out, _ = gate({"S75_X11_GATE_MODE": "refuse"})
    assert rc == 20 and "REFUSED" in out, (rc, out)


def test_record_present_enables_refuse_and_bad_manifest_is_refused():
    rec = valid_records()
    p = os.path.join(rec, "preservation.json")
    doc = json.load(open(p))
    doc["members"][0]["sha256"] = "f" * 64
    json.dump(doc, open(p, "w"))
    rc, out, _ = gate(records=rec)
    assert rc == 20 and "PER_FILE_SHA_MISMATCH" in out, (rc, out)


def test_valid_records_allow():
    rc, out, _ = gate(records=valid_records())
    assert rc == 0 and "ALLOW" in out, (rc, out)


# ---- update-skills.sh extracted block ---------------------------------------
UPDATE_HARNESS = r'''
set -e
oc_skill_box_state_save() { :; }
oc_skill_box_state_restore() { :; }
oc_remove_tree_guarded() { rm -rf "$1"; echo REMOVED_TREE; }
SKILL_DIR="$SRC/"; SKILL_NAME="%s"
for _once in 1; do
%s
echo REACHED_TAIL
done
'''


def run_update(env_extra, records, live_files=None):
    work = tempfile.mkdtemp(prefix="x11-upd-")
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
    script = UPDATE_HARNESS % (NAME, block("update-skills.sh", "# <<< X11-GATE-TAIL-END"))
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env=clean_env(SRC=src, SKILLS_DIR=skills,
                                        S75_X11_RECORDS_DIR=records, **env_extra))
    return proc, live


def tree_bytes(root):
    """Every file under root as {relative path: raw bytes}. Used to prove a
    folder was left byte-identical rather than merely non-empty."""
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(base, name)
            with open(full, "rb") as handle:
                out[os.path.relpath(full, root)] = handle.read()
    return out


def test_update_default_no_manifest_is_unchanged_behaviour_and_never_fails():
    """No record, no manifest: warn only. Update replaces the tree exactly as it
    always did (stale file gone, new file in) so existing installs and the
    tree-hash content gate are not disturbed."""
    proc, live = run_update({}, tempfile.mkdtemp())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARN" in proc.stdout, proc.stdout
    assert os.path.exists(os.path.join(live, "new.txt"))
    assert not os.path.exists(os.path.join(live, "stale-local.txt"))


def test_update_default_keeps_manifest_targeted_file_release_does_not_ship():
    rec = tempfile.mkdtemp(prefix="x11-gate-rec-")
    json.dump({"schema": "s75.x11.reviewed-manifest/v1", "files": [
        {"path": "stale-local.txt", "sha256": "0" * 64, "action": "delete"},
        {"path": "../escape.txt", "sha256": "0" * 64, "action": "modify"}]},
        open(os.path.join(rec, "reviewed-manifest.json"), "w"))
    proc, live = run_update({}, rec)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert os.path.exists(os.path.join(live, "stale-local.txt")), proc.stdout
    assert open(os.path.join(live, "stale-local.txt")).read() == "keep me"
    assert os.path.exists(os.path.join(live, "new.txt"))
    assert not os.path.exists(os.path.join(os.path.dirname(live), "escape.txt"))


def test_update_default_shipped_file_still_wins_over_targeted_stale_copy():
    rec = tempfile.mkdtemp(prefix="x11-gate-rec-")
    json.dump({"files": [{"path": "new.txt", "sha256": "0" * 64, "action": "modify"}]},
              open(os.path.join(rec, "reviewed-manifest.json"), "w"))
    proc, live = run_update({}, rec, live_files={"new.txt": "OLD"})
    assert open(os.path.join(live, "new.txt")).read() == "new", proc.stdout


def test_update_refuse_mode_leaves_skill_untouched_without_failing_roll():
    proc, live = run_update({"S75_X11_GATE_MODE": "refuse"}, tempfile.mkdtemp())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "REMOVED_TREE" not in proc.stdout
    assert os.path.exists(os.path.join(live, "stale-local.txt"))
    assert not os.path.exists(os.path.join(live, "new.txt"))


def test_update_refuse_mode_prints_no_updated_line_for_skill_75():
    """The skip is a real `continue` in the shipped loop: after the NOT updated
    line the pin, verify and Updated steps never run for skill 75."""
    proc, _live = run_update({"S75_X11_GATE_MODE": "refuse"}, tempfile.mkdtemp())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "NOT updated" in proc.stdout, proc.stdout
    assert "Updated:" not in proc.stdout, proc.stdout
    assert "REACHED_TAIL" not in proc.stdout, proc.stdout


def test_update_unwritable_temp_location_with_manifest_leaves_folder_byte_identical():
    """A keep-list that is not empty plus a temp location that cannot hold the
    keep folder: skill 75 is left exactly as it was, the roll does not fail."""
    rec = tempfile.mkdtemp(prefix="x11-gate-rec-")
    json.dump({"files": [{"path": "stale-local.txt", "sha256": "0" * 64,
                          "action": "delete"}]},
              open(os.path.join(rec, "reviewed-manifest.json"), "w"))
    holder = tempfile.mkdtemp(prefix="x11-no-tmp-")
    unwritable = os.path.join(holder, "not-a-directory")
    open(unwritable, "w").write("x")
    proc, live = run_update({"TMPDIR": unwritable}, rec)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "could not make a keep folder" in proc.stdout, proc.stdout
    assert "REMOVED_TREE" not in proc.stdout, proc.stdout
    assert tree_bytes(live) == {"stale-local.txt": b"keep me"}, tree_bytes(live)


def test_update_allowed_gate_uses_normal_replace():
    proc, live = run_update({}, valid_records())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "REMOVED_TREE" in proc.stdout
    assert os.path.exists(os.path.join(live, "new.txt"))
    assert not os.path.exists(os.path.join(live, "stale-local.txt"))


def test_update_other_skills_unaffected():
    work = tempfile.mkdtemp(prefix="x11-upd-")
    src = os.path.join(work, "src", "01-other")
    os.makedirs(src)
    open(os.path.join(src, "n.txt"), "w").write("n")
    skills = os.path.join(work, "skills")
    os.makedirs(os.path.join(skills, "01-other"))
    script = (UPDATE_HARNESS % ("01-other", block("update-skills.sh", "# <<< X11-GATE-TAIL-END")))
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env=clean_env(SRC=src, SKILLS_DIR=skills))
    assert proc.returncode == 0 and "REMOVED_TREE" in proc.stdout, proc.stdout + proc.stderr


# ---- install.sh extracted block ---------------------------------------------
INSTALL_HARNESS = r'''
warn() { echo "WARN: $*"; }
LOG_FILE=/dev/null
SKILL_DIR="$SRC/"; SKILL_NAME="%s"
for _once in 1; do
%s
echo REACHED_COPY
done
'''


def run_install(env_extra, records):
    work = tempfile.mkdtemp(prefix="x11-inst-")
    src = os.path.join(work, NAME)
    os.makedirs(os.path.join(src, "scripts", "core"))
    for f in ("x11_install_gate.sh", "release_gate_cli.py", "apply_release_gate.py"):
        with open(os.path.join(SKILL_ROOT, "scripts", "core", f), "rb") as r, \
             open(os.path.join(src, "scripts", "core", f), "wb") as w:
            w.write(r.read())
    script = INSTALL_HARNESS % (NAME, block("install.sh"))
    return subprocess.run(["bash", "-c", "set -e\n" + script], capture_output=True, text=True,
                          env=clean_env(SRC=src, SKILLS_DIR=work,
                                        S75_X11_RECORDS_DIR=records, **env_extra))


def test_install_default_warns_and_proceeds():
    proc = run_install({}, tempfile.mkdtemp())
    assert proc.returncode == 0 and "REACHED_COPY" in proc.stdout, proc.stdout + proc.stderr
    assert "WARN" in proc.stdout


def test_install_refuse_mode_skips_skill_without_failing():
    proc = run_install({"S75_X11_GATE_MODE": "refuse"}, tempfile.mkdtemp())
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
    print("X11_INSTALL_GATE legs=%d failures=%d" % (len(tests), fails))
    sys.exit(1 if fails else 0)
