#!/usr/bin/env python3
"""S75-X11 wiring proofs: the call site refuses, allows and catches a killed guard.

Run directly:  python3 -I tests/test_x11_release_gate_wiring.py
Also collects as pytest (functions named test_*).

Everything is synthetic, in a temp dir. No real backup, no tree copy, no
owner authority.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "scripts", "core")
CLI = os.path.join(CORE, "release_gate_cli.py")
GATE = os.path.join(CORE, "apply_release_gate.py")

TARGET = {"repository": "repo://synthetic", "skill_root": "75-skill",
          "target_id": "canonical-copy", "kind": "canonical", "tree_digest": "a" * 64}
A_PATH, A_BYTES = "scripts/core/a.py", b"print('a')\n"
B_PATH, B_BYTES = "scripts/core/b.py", b"print('b')\n"
SHA = lambda data: hashlib.sha256(data).hexdigest()


def records(path):
    doc = {
        "target.json": dict(TARGET),
        "backup-authorization.json": {
            "schema": "s75.x11.backup-authorization/v1",
            "authorization_id": "auth-1", "issuer": "owner:trevor",
            "channel": "trevor-command", "source": "harness-user-input",
            "issued_at": "2026-11-01T00:00:00+00:00", "backup_mode": "targeted",
            "scope": ["canonical-copy"], "target": dict(TARGET)},
        "reviewed-manifest.json": {
            "schema": "s75.x11.reviewed-manifest/v1", "manifest_id": "m-1",
            "sha256": "b" * 64,
            "files": [{"path": A_PATH, "sha256": SHA(A_BYTES), "action": "modify"},
                      {"path": B_PATH, "sha256": SHA(B_BYTES), "action": "add"}]},
        "preservation.json": {
            "schema": "s75.x11.targeted-preservation/v1",
            "preservation_id": "pres-1", "target": dict(TARGET),
            "backup_mode": "targeted", "archive_sha256": "c" * 64,
            "created_at": "2026-11-01T00:00:01+00:00",
            "members": [{"path": A_PATH, "sha256": SHA(A_BYTES)},
                        {"path": B_PATH, "sha256": SHA(B_BYTES)}]},
        "applied-verification.json": {
            "schema": "s75.x11.applied-tree-verification/v1", "receipt_id": "v-1",
            "target": dict(TARGET), "applier": {"identity": "builder"},
            "verifier": {"identity": "checker", "independent": True},
            "applied_digest": TARGET["tree_digest"],
            "applied_at": "2026-11-01T00:00:02+00:00",
            "verified_at": "2026-11-01T00:00:03+00:00",
            "checks": [{"name": "tree-digest", "status": "PASS"}], "result": "PASS"},
    }
    os.makedirs(path, exist_ok=True)
    for name, value in doc.items():
        with open(os.path.join(path, name), "w", encoding="utf-8") as handle:
            json.dump(value, handle)


def run(command, record_dir, gate=GATE):
    proc = subprocess.run([sys.executable, "-I", CLI, command,
                           "--records", record_dir, "--gate-module", gate],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def with_records():
    root = tempfile.mkdtemp(prefix="x11-wire-")
    records(root)
    return root


def test_apply_allows_correct_manifest():
    rc, out = run("apply", with_records())
    assert rc == 0, out
    assert '"ALLOW_APPLY"' in out, out


def test_release_allows_with_independent_verification():
    rc, out = run("release", with_records())
    assert rc == 0, out
    assert '"ALLOW_RELEASE"' in out, out


def test_refuses_tampered_member():
    root = tempfile.mkdtemp(prefix="x11-wire-")
    records(root)
    doc = json.load(open(os.path.join(root, "preservation.json")))
    doc["members"][0]["sha256"] = "f" * 64
    json.dump(doc, open(os.path.join(root, "preservation.json"), "w"))
    rc, out = run("apply", root)
    assert rc == 3, (rc, out)
    assert "PER_FILE_SHA_MISMATCH" in out, out


def test_refuses_removed_member():
    root = tempfile.mkdtemp(prefix="x11-wire-")
    records(root)
    doc = json.load(open(os.path.join(root, "preservation.json")))
    doc["members"] = doc["members"][1:]
    json.dump(doc, open(os.path.join(root, "preservation.json"), "w"))
    rc, out = run("apply", root)
    assert rc == 4, (rc, out)
    assert "BACKUP_MISSING_CHANGED_FILE" in out, out


def test_refuses_deleted_original_work():
    root = tempfile.mkdtemp(prefix="x11-wire-")
    records(root)
    doc = json.load(open(os.path.join(root, "reviewed-manifest.json")))
    doc["files"][0]["action"] = "delete"
    json.dump(doc, open(os.path.join(root, "reviewed-manifest.json"), "w"))
    rc, out = run("apply", root)
    assert rc == 5, (rc, out)
    assert "ORIGINAL_WORK_DELETED" in out, out


def test_refuses_absent_preservation():
    root = tempfile.mkdtemp(prefix="x11-wire-")
    records(root)
    os.remove(os.path.join(root, "preservation.json"))
    rc, out = run("apply", root)
    assert rc == 2, (rc, out)
    assert "MISSING_TARGETED_PRESERVATION" in out, out


def test_refuses_release_without_applied_verification():
    root = tempfile.mkdtemp(prefix="x11-wire-")
    records(root)
    os.remove(os.path.join(root, "applied-verification.json"))
    rc, out = run("release", root)
    assert rc == 2, (rc, out)
    assert "MISSING_APPLIED_TREE_VERIFICATION" in out, out


def test_mutant_disabled_guard_is_caught():
    """Kill the guard in a copy: the same negatives must stop refusing, which
    is what proves the refusal legs above discriminate rather than pass blind."""
    root = tempfile.mkdtemp(prefix="x11-wire-mutant-")
    mutant = os.path.join(root, "apply_release_gate.py")
    shutil.copyfile(GATE, mutant)
    source = open(mutant, encoding="utf-8").read()
    needle = 'PRESERVED_ACTIONS = ("modify", "add")'
    assert needle in source, "module drift: PRESERVED_ACTIONS line moved"
    source = source.replace(needle, 'PRESERVED_ACTIONS = ("modify", "add", "delete")')
    needle = """    for path in sorted(reviewed):
        if backed_up[path] != reviewed[path]:"""
    assert needle in source, "module drift: per-file compare block moved"
    source = source.replace(needle, """    for path in sorted(reviewed):
        if False:""")
    open(mutant, "w", encoding="utf-8").write(source)

    deleted = os.path.join(root, "deleted")
    records(deleted)
    doc = json.load(open(os.path.join(deleted, "reviewed-manifest.json")))
    doc["files"][0]["action"] = "delete"
    json.dump(doc, open(os.path.join(deleted, "reviewed-manifest.json"), "w"))
    rc, out = run("apply", deleted, gate=mutant)
    assert rc == 0, ("mutant still refuses delete; test would pass blind", rc, out)

    tampered = os.path.join(root, "tampered")
    records(tampered)
    doc = json.load(open(os.path.join(tampered, "preservation.json")))
    doc["members"][0]["sha256"] = "f" * 64
    json.dump(doc, open(os.path.join(tampered, "preservation.json"), "w"))
    rc, out = run("apply", tampered, gate=mutant)
    assert rc == 0, ("mutant still refuses tampering; test would pass blind", rc, out)


if __name__ == "__main__":
    failures = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print("PASS", name)
            except AssertionError as error:
                failures += 1
                print("FAIL", name, error)
    print("WIRING_PROOF", "PASS" if not failures else "FAIL",
          "legs=%d failures=%d" % (
              len([n for n in globals() if n.startswith("test_")]), failures))
    sys.exit(0 if not failures else 1)
