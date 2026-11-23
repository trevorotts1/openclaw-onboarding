"""run_lock.py - N-53: every path comes from the run lock; a tool takes only
the run folder; audio is matched by fingerprint before any cut (section 3D.6).

The run lock is ``control/run-lock.json``. It records the run folder, the
named paths a tool may use, and the content fingerprints of the inputs that
must not drift (the song master, each vocal track, each lip piece). A caller
resolves a named path through the lock instead of writing its own; a path
outside the run folder is refused; an audio file whose bytes do not match the
locked fingerprint is refused before it is cut.

Stdlib only. Read-only helpers never mutate; ``RunLock.save`` is the one writer.
"""
import hashlib
import json
import os

SCHEMA = "blackceo.run-lock/v1"
LOCK_REL = os.path.join("control", "run-lock.json")
CODE_OUTSIDE = "PATH_OUTSIDE_RUN"
CODE_AUDIO = "AUDIO_FINGERPRINT_MISMATCH"
CODE_LOCK = "RUN_LOCK_MISSING"


class RunLockError(Exception):
    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code, self.detail = code, detail


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(root, target):
    root = os.path.realpath(root)
    target = os.path.realpath(target)
    return target == root or target.startswith(root + os.sep)


class RunLock:
    """One run's path and fingerprint authority."""

    def __init__(self, run_dir, doc):
        self.run_dir = os.path.abspath(run_dir)
        self.doc = doc if isinstance(doc, dict) else {}

    @classmethod
    def open(cls, run_dir):
        path = os.path.join(run_dir, LOCK_REL)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except FileNotFoundError:
            raise RunLockError(CODE_LOCK, path)
        except (OSError, ValueError) as exc:
            raise RunLockError(CODE_LOCK, "%s: %s" % (path, exc))
        if not isinstance(doc, dict):
            raise RunLockError(CODE_LOCK, "%s is not an object" % path)
        return cls(run_dir, doc)

    def resolve(self, rel):
        """Resolve a run-relative path and refuse anything outside the run."""
        if os.path.isabs(rel):
            target = rel
        else:
            target = os.path.join(self.run_dir, rel)
        if not _inside(self.run_dir, target):
            raise RunLockError(CODE_OUTSIDE,
                               "%s resolves outside the run folder %s"
                               % (rel, self.run_dir))
        return os.path.abspath(target)

    def path(self, key, *, required=True):
        rel = (self.doc.get("paths") or {}).get(key)
        if not rel:
            if required:
                raise RunLockError(CODE_LOCK, "no path named %r in the run lock" % key)
            return None
        return self.resolve(rel)

    def add_path(self, key, rel, *, save=True):
        self.doc.setdefault("paths", {})[key] = rel
        self.resolve(rel)                       # validate before recording
        if save:
            self.save()
        return self.resolve(rel)

    def fingerprint(self, rel_or_key):
        rel = (self.doc.get("paths") or {}).get(rel_or_key, rel_or_key)
        return sha256_file(self.resolve(rel))

    def add_fingerprint(self, key, rel=None, *, save=True):
        target = self.path(key) if rel is None else self.resolve(rel)
        digest = sha256_file(target)
        self.doc.setdefault("fingerprints", {})[key] = digest
        if save:
            self.save()
        return digest

    def _audio_keys(self):
        keys = []
        for key in (self.doc.get("fingerprints") or {}):
            low = key.lower()
            if any(word in low for word in ("audio", "song", "vocal", "track", "lip")):
                keys.append(key)
        return keys

    def audio_matches(self, path, key=None):
        """True when the file's bytes match a locked audio fingerprint."""
        digest = sha256_file(path)
        prints = self.doc.get("fingerprints") or {}
        keys = [key] if key else self._audio_keys()
        if not keys:
            raise RunLockError(CODE_LOCK, "no audio fingerprint is recorded")
        return any(prints.get(k) == digest for k in keys)

    def require_audio(self, path, key=None):
        if not self.audio_matches(path, key):
            raise RunLockError(CODE_AUDIO,
                               "%s does not match the locked audio fingerprint; "
                               "it is never cut" % path)
        return True

    def save(self):
        os.makedirs(os.path.dirname(os.path.join(self.run_dir, LOCK_REL)),
                    exist_ok=True)
        path = os.path.join(self.run_dir, LOCK_REL)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)


def only_run_folder(run_dir, path):
    """A tool may touch only paths inside the run folder (N-53)."""
    if not _inside(run_dir, path):
        raise RunLockError(CODE_OUTSIDE,
                           "%s is outside the run folder %s" % (path, run_dir))
    return os.path.abspath(path)


def match_audio_before_cut(run_dir, audio_path, key=None):
    """The pre-cut gate: an audio file is used only if its fingerprint matches."""
    return RunLock.open(run_dir).require_audio(audio_path, key)
