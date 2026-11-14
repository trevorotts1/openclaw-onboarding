#!/usr/bin/env python3
"""S75-018 / U-GEN313: two documents, one filename, no more.

The X11 installed-apply decision the release gate reads and the song run
artifact ``<run>/music/acceptance/operator-decision.json`` are different
documents with different shapes. This test pins that they are named differently
and that a song-shaped document handed to the reader under the X11 name is
refused, never read as an allow.

MUST FAIL before the fix: both basenames were ``operator-decision.json``.

Run directly:  python3 -I tests/test_x11_operator_decision_filename.py
Also collects as pytest (functions named test_*). Everything is synthetic and
written under TMPDIR; no real backup, no tree copy, no owner authority.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "scripts", "core")
CLI = os.path.join(CORE, "release_gate_cli.py")

sys.path.insert(0, CORE)
from song_dispatch import song_dispatch as SD  # noqa: E402

import release_gate_cli  # noqa: E402

TARGET = {"repository": "repo://synthetic", "skill_root": "75-skill",
          "target_id": "installed-copy", "kind": "installed", "tree_digest": "a" * 64}
A_PATH, A_BYTES = "scripts/core/a.py", b"print('a')\n"
B_PATH, B_BYTES = "scripts/core/b.py", b"print('b')\n"
SHA = lambda data: hashlib.sha256(data).hexdigest()

#: The shape song_dispatch.record_operator_decision writes. It has no
#: ``installed_apply`` key at all.
SONG_SHAPED = {
    "decision": "ACCEPTED_RISK", "operator": "fixture-operator",
    "at_utc": "2026-11-01T00:00:00Z", "gates_not_proven": ["length"],
    "measured_evidence_digest": "e" * 64,
    "reason": "fixture reason long enough to be a reason",
    "recorded_at_utc": "2026-11-01T00:00:01Z",
}


def x11_filename():
    """The name the CLI reads. Pre-fix the constant does not exist and the old
    shared name is what the code reads, which is what the first test catches."""
    return getattr(release_gate_cli, "OPERATOR_DECISION_FILE", "operator-decision.json")


def song_filename():
    return os.path.basename(SD.operator_decision_path(os.path.join("run", "dir")))


def installed_records(path):
    doc = {
        "target.json": dict(TARGET),
        "backup-authorization.json": {
            "schema": "s75.x11.backup-authorization/v1",
            "authorization_id": "auth-1", "issuer": "owner:trevor",
            "channel": "trevor-command", "source": "harness-user-input",
            "issued_at": "2026-11-01T00:00:00+00:00", "backup_mode": "targeted",
            "scope": ["installed-copy"], "target": dict(TARGET)},
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
    }
    os.makedirs(path, exist_ok=True)
    for name, value in doc.items():
        with open(os.path.join(path, name), "w", encoding="utf-8") as handle:
            json.dump(value, handle)


def run_apply(records_dir):
    proc = subprocess.run([sys.executable, "-I", CLI, "apply",
                           "--records", records_dir],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def test_x11_filename_differs_from_song_run_artifact():
    x11, song = x11_filename(), song_filename()
    assert x11 != song, (
        "the X11 installed-apply decision and the song run artifact share the "
        "filename %r; a song-shaped document can be read as the X11 one" % (x11,))


def test_song_shaped_document_at_x11_path_is_refused():
    root = tempfile.mkdtemp(prefix="x11-od-name-")
    records = os.path.join(root, "records")
    installed_records(records)
    decision_path = os.path.join(records, x11_filename())
    with open(decision_path, "w", encoding="utf-8") as handle:
        json.dump(SONG_SHAPED, handle)
    rc, out = run_apply(records)
    assert rc == 2, ("a song-shaped document was not refused", rc, out)
    assert "INSTALLED_APPLY_NOT_AUTHORIZED" in out, out
    assert '"ALLOW_APPLY"' not in out, out


def test_installed_apply_true_at_x11_path_still_allows():
    """The rename must not break the one decision the gate does accept."""
    root = tempfile.mkdtemp(prefix="x11-od-allow-")
    records = os.path.join(root, "records")
    installed_records(records)
    with open(os.path.join(records, x11_filename()), "w", encoding="utf-8") as handle:
        json.dump({"installed_apply": True}, handle)
    rc, out = run_apply(records)
    assert rc == 0, (rc, out)
    assert '"ALLOW_APPLY"' in out, out


if __name__ == "__main__":
    failures = 0
    names = [n for n in sorted(globals()) if n.startswith("test_") and callable(globals()[n])]
    for name in names:
        try:
            globals()[name]()
            print("PASS", name)
        except AssertionError as error:
            failures += 1
            print("FAIL", name, error)
    print("OPERATOR_DECISION_NAME_PROOF", "PASS" if not failures else "FAIL",
          "legs=%d failures=%d" % (len(names), failures))
    sys.exit(0 if not failures else 1)
