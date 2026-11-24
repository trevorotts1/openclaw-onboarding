#!/usr/bin/env python3
"""cache.py: every cached scan result keyed by content, never by path (N-46).

A rescan of a new master once returned the old master's letter results because
the cache was keyed by file path. This module's key is the file's SHA-256 plus
the reader's version plus a fingerprint of the reader's settings; the path is
carried for the receipt only and never decides a hit.

Stdlib only. The store is in memory unless a caller hands it a JSON file path.
"""
from __future__ import annotations

import hashlib
import json
import os

TOOL_NAME = "clip_checks.cache"
TOOL_VERSION = "1.0.0"


def content_sha256(path, chunk=1 << 20):
    """SHA-256 of the file's bytes; raises OSError when it cannot be read."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def fingerprint(value):
    """Stable fingerprint of JSON-able settings (sorted keys, no whitespace)."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cache_key(path, reader_version, settings=None):
    """(key, sha256). The key is content + reader version + settings."""
    digest = content_sha256(path)
    key = "%s|%s|%s" % (digest, reader_version,
                        fingerprint(settings if settings is not None else {}))
    return key, digest


class ScanCache:
    """Content-keyed scan cache. Never a path hit.

    ``file_path`` persists the store as JSON on put(); absent, memory only.
    ``lookup`` with a path and a reader/settings pair re-hashes the file, so a
    changed master can never match an older result.
    """

    def __init__(self, file_path=None):
        self.file_path = file_path
        self._rows = {}
        if file_path and os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self._rows = loaded
            except (OSError, ValueError):
                self._rows = {}

    def get(self, key):
        row = self._rows.get(key)
        return dict(row) if isinstance(row, dict) else None

    def put(self, key, result):
        row = dict(result)
        row["cache_key"] = key
        self._rows[key] = row
        self._save()
        return row

    def lookup(self, path, reader_version, settings=None, result=None):
        """Return a cached row for this exact content, else None.

        With ``result`` supplied and no hit, the result is stored under the
        fresh key and returned. Reader version and settings are part of the
        key, so a changed reader never reuses an older verdict.
        """
        key, digest = cache_key(path, reader_version, settings)
        hit = self.get(key)
        if hit is not None:
            hit["cache_hit"] = True
            return hit
        if result is None:
            return None
        stored = dict(result)
        stored.setdefault("sha256", digest)
        stored["cache_hit"] = False
        return self.put(key, stored)

    def _save(self):
        if not self.file_path:
            return
        tmp = self.file_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._rows, fh, sort_keys=True, indent=1)
            os.replace(tmp, self.file_path)
        except OSError:
            pass                     # a failed save never breaks the scan


def cached_scan(cache, path, reader_version, scan_fn, settings=None):
    """Cache wrapper: hash -> hit or run scan_fn(path) once and store it."""
    key, digest = cache_key(path, reader_version, settings)
    hit = cache.get(key)
    if hit is not None:
        hit["cache_hit"] = True
        return hit
    result = scan_fn(path)
    stored = dict(result) if isinstance(result, dict) else {"result": result}
    stored.setdefault("sha256", digest)
    stored["cache_hit"] = False
    return cache.put(key, stored)


if __name__ == "__main__":
    # Control: the key is content + reader version + settings; a path is never
    # the key. A new master never matches an old result, and a changed reader
    # never reuses an older verdict. Uses a temp file, no network, no spend.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        master = os.path.join(tmp, "master.mp4")
        with open(master, "wb") as fh:
            fh.write(b"first master bytes")
        scan = ScanCache()
        first = cached_scan(scan, master, "ocr-1", lambda p: {"verdict": "CLEAN"})
        assert first["cache_hit"] is False
        again = cached_scan(scan, master, "ocr-1", lambda p: {"verdict": "CLEAN"})
        assert again["cache_hit"] is True               # same content, same key
        other = cached_scan(scan, master, "ocr-2", lambda p: {"verdict": "CLEAN"})
        assert other["cache_hit"] is False              # new reader, new key
        tuned = cached_scan(scan, master, "ocr-1",
                            lambda p: {"verdict": "CLEAN"}, settings={"psm": 3})
        assert tuned["cache_hit"] is False              # new settings, new key
        with open(master, "wb") as fh:
            fh.write(b"SECOND master, different bytes entirely")
        rescanned = cached_scan(scan, master, "ocr-1",
                                lambda p: {"verdict": "CLEAN"})
        assert rescanned["cache_hit"] is False          # a new master never hits
        assert rescanned["sha256"] == content_sha256(master)
        k1, d1 = cache_key(master, "ocr-1", {"psm": 3})
        assert d1 in k1 and k1.startswith(d1)
        assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    print("cache: control PASS")
