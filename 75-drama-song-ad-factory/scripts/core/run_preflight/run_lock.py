#!/usr/bin/env python3
"""run_lock.py - N-53: every path comes from the run lock; a tool takes only
the run folder; audio is matched by fingerprint before any cut (3D.6).

Section 3D.6 today's failure: run tools carried hard-coded paths and one
pointed at another run's vocal track. The fix is one rule, enforced here:

  * ``control/run-lock.json`` is the only place a path is named. Every tool
    receives the run folder and reads the lock; it never receives a path.
  * ``resolve`` returns paths INSIDE the run folder only. A lock entry that
    points outside is refused ``PATH_OUTSIDE_RUN``.
  * ``match_audio`` compares a candidate audio file's content fingerprint
    before any cut. A mismatch is refused ``AUDIO_FINGERPRINT_MISMATCH``.

Stdlib only.
"""
import argparse
import hashlib
import json
import os
import sys

SCHEMA = "blackceo.run-lock/v1"
LOCK_REL = os.path.join("control", "run-lock.json")


class LockRefused(Exception):
    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code, self.detail = code, detail


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def lock_path(run_dir):
    return os.path.join(run_dir, LOCK_REL)


def load_lock(run_dir):
    path = lock_path(run_dir)
    if not os.path.isfile(path):
        raise LockRefused("RUN_LOCK_MISSING", path)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("schema") != SCHEMA or not isinstance(doc.get("paths"), dict):
        raise LockRefused("RUN_LOCK_MALFORMED",
                          "needs schema %s and a paths object" % SCHEMA)
    return doc


def write_lock(run_dir, paths):
    """Create the lock. Every recorded path must already be inside the run."""
    run_dir = os.path.abspath(run_dir)
    for key, rel in (paths or {}).items():
        target = os.path.abspath(os.path.join(run_dir, rel))
        if os.path.commonpath([run_dir, target]) != run_dir:
            raise LockRefused("PATH_OUTSIDE_RUN", "%s -> %s" % (key, rel))
    doc = {"schema": SCHEMA, "paths": dict(paths or {})}
    path = lock_path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return doc


def resolve(run_dir, key, must_exist=True):
    """Return the absolute path the lock names for ``key``, inside the run."""
    run_dir = os.path.abspath(run_dir)
    doc = load_lock(run_dir)
    rel = (doc["paths"] or {}).get(key)
    if not rel:
        raise LockRefused("RUN_LOCK_KEY_MISSING", key)
    target = os.path.abspath(os.path.join(run_dir, rel))
    if os.path.commonpath([run_dir, target]) != run_dir:
        raise LockRefused("PATH_OUTSIDE_RUN", "%s -> %s" % (key, rel))
    if must_exist and not os.path.isfile(target):
        raise LockRefused("LOCKED_FILE_MISSING", "%s -> %s" % (key, rel))
    return target


def match_audio(run_dir, key, candidate, expected_sha256=None):
    """Prove ``candidate`` is the audio the lock names before any cut."""
    locked = resolve(run_dir, key)
    expected = expected_sha256 or fingerprint(locked)
    actual = fingerprint(candidate)
    if actual != expected:
        raise LockRefused("AUDIO_FINGERPRINT_MISMATCH",
                          "%s is %s, the lock's %s is %s"
                          % (candidate, actual[:12], key, expected[:12]))
    return {"match": True, "sha256": actual, "path": candidate}


def selftest():
    import tempfile
    proofs = []
    with tempfile.TemporaryDirectory() as base:
        run = os.path.join(base, "run-a")
        other = os.path.join(base, "run-b")
        os.makedirs(run)
        os.makedirs(other)
        with open(os.path.join(run, "vocal.wav"), "wb") as fh:
            fh.write(b"RIFF" + b"\x00" * 100)
        with open(os.path.join(other, "vocal.wav"), "wb") as fh:
            fh.write(b"RIFF" + b"\x01" * 100)

        def refused(code, fn, *a):
            try:
                fn(*a)
            except LockRefused as exc:
                return exc.code == code
            return False

        proofs.append(("a tool with no lock is refused",
                       refused("RUN_LOCK_MISSING", resolve, run, "vocal")))
        write_lock(run, {"vocal": "vocal.wav"})
        proofs.append(("the lock resolves the file inside the run",
                       resolve(run, "vocal").endswith("vocal.wav")))
        proofs.append(("a lock path outside the run is refused",
                       refused("PATH_OUTSIDE_RUN", write_lock, run,
                               {"x": os.path.join("..", "run-b", "vocal.wav")})))
        proofs.append(("another run's audio fails its fingerprint before the cut",
                       refused("AUDIO_FINGERPRINT_MISMATCH", match_audio, run,
                               "vocal", os.path.join(other, "vocal.wav"))))
        proofs.append(("the lock's own audio matches",
                       match_audio(run, "vocal", os.path.join(run, "vocal.wav"))["match"]))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_res = sub.add_parser("resolve")
    p_res.add_argument("--key", required=True)
    p_match = sub.add_parser("match-audio")
    p_match.add_argument("--key", required=True)
    p_match.add_argument("--candidate", required=True)
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    try:
        if args.cmd == "resolve":
            print(json.dumps({"path": resolve(args.run_dir, args.key)}, indent=2))
        else:
            print(json.dumps(match_audio(args.run_dir, args.key, args.candidate),
                             indent=2, sort_keys=True))
    except LockRefused as exc:
        print(json.dumps({"outcome": "rejected", "reason_code": exc.code,
                          "detail": exc.detail}, indent=2))
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
