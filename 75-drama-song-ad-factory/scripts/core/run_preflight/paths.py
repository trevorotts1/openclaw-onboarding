"""paths.py - N-53: every path comes from the run lock; a tool takes only the
run folder; any audio file is matched to the lock by fingerprint before it is
cut.

Stdlib only. The lock lives at control/run-lock.json:
    {"run_root": ".",
     "paths": {"song_master": "music/song-master.mp3", ...},
     "fingerprints": {"song_master": "<sha256>", ...}}
A tool that points at another run's file is refused, never followed.
"""
import hashlib
import json
import os

CODES = ("RUN_LOCK_MISSING", "PATH_UNKNOWN", "PATH_OUTSIDE_RUN",
         "PATH_MISSING", "AUDIO_FINGERPRINT_MISMATCH")


class PathRefused(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_join(run_dir, *parts):
    """Join under the run folder and refuse anything that escapes it."""
    root = os.path.realpath(os.path.abspath(run_dir))
    target = os.path.realpath(os.path.join(root, *parts))
    if target != root and not target.startswith(root + os.sep):
        raise PathRefused("PATH_OUTSIDE_RUN",
                          "%s is outside the run folder" % os.path.join(*parts))
    return target


class RunPaths:
    def __init__(self, run_dir, lock_path=None):
        self.run_dir = os.path.realpath(os.path.abspath(os.fspath(run_dir)))
        self.lock_path = lock_path or os.path.join(self.run_dir, "control", "run-lock.json")
        self.lock = None
        self.load_error = None
        try:
            with open(self.lock_path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            self.lock = doc if isinstance(doc, dict) else None
        except (OSError, ValueError) as exc:
            self.load_error = str(exc)[:200]

    def _need_lock(self):
        if self.lock is None:
            raise PathRefused("RUN_LOCK_MISSING",
                              "control/run-lock.json is missing or unreadable: %s"
                              % (self.load_error or "no document"))

    def _root(self):
        rel_root = (self.lock or {}).get("run_root") or "."
        return safe_join(self.run_dir, rel_root)

    def keys(self):
        self._need_lock()
        return sorted((self.lock.get("paths") or {}).keys())

    def resolve(self, key, must_exist=True):
        """The lock's path for ``key``, proved to sit inside the run folder."""
        self._need_lock()
        paths = self.lock.get("paths") or {}
        if key not in paths:
            raise PathRefused("PATH_UNKNOWN",
                              "the run lock names no path %r (known: %s)"
                              % (key, ", ".join(sorted(paths)) or "none"))
        rel = paths[key]
        if os.path.isabs(rel):
            raise PathRefused("PATH_OUTSIDE_RUN",
                              "the run lock gives an absolute path for %r; tools take "
                              "only the run folder" % key)
        target = safe_join(self._root(), rel)
        if must_exist and not os.path.isfile(target):
            raise PathRefused("PATH_MISSING", "%s -> %s is missing" % (key, rel))
        return target

    def audio(self, key):
        """An audio path, matched by fingerprint before any cut."""
        target = self.resolve(key)
        expected = (self.lock.get("fingerprints") or {}).get(key)
        if not expected:
            raise PathRefused("AUDIO_FINGERPRINT_MISMATCH",
                              "the run lock holds no fingerprint for %r, so the file "
                              "cannot be trusted before a cut" % key)
        actual = fingerprint(target)
        if actual != expected:
            raise PathRefused("AUDIO_FINGERPRINT_MISMATCH",
                              "%s does not match the run lock (lock %s..., file %s...)"
                              % (key, expected[:12], actual[:12]))
        return target

    def assert_tool_target(self, path):
        """A tool's target must be inside this run folder."""
        target = os.path.realpath(os.path.abspath(path))
        if not (target == self.run_dir or target.startswith(self.run_dir + os.sep)):
            raise PathRefused("PATH_OUTSIDE_RUN", "%s is outside the run folder" % path)
        return target


def register_fingerprint(run_dir, key, path):
    """Record a validated path and its fingerprint in the run lock."""
    lock_path = os.path.join(run_dir, "control", "run-lock.json")
    try:
        with open(lock_path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    doc.setdefault("paths", {})
    doc.setdefault("fingerprints", {})
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(run_dir))
    doc["paths"][key] = rel
    doc["fingerprints"][key] = fingerprint(path)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    tmp = lock_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, lock_path)
    return {"key": key, "path": rel, "fingerprint": doc["fingerprints"][key]}
