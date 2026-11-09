#!/usr/bin/env python3
"""S75-T15: the local store is a SYNC-STATE CACHE of Notion, never the source.

Notion owns every shared character record. A document written here is a cached
copy: it can be missing, stale or dropped at any time, and it is rebuilt from
the Notion side. Nothing is invented locally to fill a gap.

Stdlib only. No network, no credential, no database id of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

CACHE_SCHEMA = "s75.notion-sync-cache/v1"
SOURCE_OF_TRUTH = "notion"
LOCAL_ROLE = "sync-state-cache"
RECOVERABLE_FROM = (SOURCE_OF_TRUTH,)


class CacheError(ValueError):
    """Plain-English reason a cache read or write stopped."""


class CacheUnrecoverable(CacheError):
    """The Notion side has no record, so there is nothing to rebuild from."""


def describe():
    """Declare, in one place, what this local storage is and is not."""
    return {
        "schema": CACHE_SCHEMA,
        "local_role": LOCAL_ROLE,
        "source_of_truth": SOURCE_OF_TRUTH,
        "recoverable_from": list(RECOVERABLE_FROM),
        "local_is_cache": True,
    }


def _segment(value):
    """Filesystem-safe, collision-free segment for a namespace or document."""
    text = str(value)
    keep = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in text)[:40]
    return "%s-%s" % (keep or "x", hashlib.sha256(text.encode("utf-8")).hexdigest()[:8])


def _atomic_write(path, value):
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".cache-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Cache:
    """One client's cached copies. Scoped by client namespace, never shared."""

    def __init__(self, root, client_namespace):
        namespace = str(client_namespace or "").strip()
        if not namespace:
            raise CacheError("The client identity is missing, so no cache can be opened.")
        self.root = os.path.expanduser(str(root))
        self.client_namespace = namespace

    def dir(self):
        return os.path.join(self.root, "clients", _segment(self.client_namespace))

    def path(self, document):
        return os.path.join(self.dir(), _segment(document) + ".json")

    def load(self, document):
        """The cached value, or None. Never raises on a missing document."""
        try:
            with open(self.path(document), encoding="utf-8") as f:
                envelope = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(envelope, dict):
            return None
        if envelope.get("client_namespace") != self.client_namespace:
            return None
        return envelope

    def value(self, document):
        envelope = self.load(document)
        return None if envelope is None else envelope.get("value")

    def revision(self, document):
        envelope = self.load(document)
        return None if envelope is None else envelope.get("revision")

    def store(self, document, value, *, revision=1, source="LOCAL"):
        """Write a cached copy. The envelope states what the local side is."""
        envelope = dict(describe())
        envelope.update({
            "client_namespace": self.client_namespace,
            "document": str(document),
            "revision": revision,
            "source": str(source),
            "value": value,
        })
        _atomic_write(self.path(document), envelope)
        return envelope

    def drop(self, document):
        try:
            os.unlink(self.path(document))
        except OSError:
            return False
        return True

    def documents(self):
        """Every cached envelope for this client, keyed by its document name."""
        found = {}
        try:
            names = os.listdir(self.dir())
        except OSError:
            return found
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.dir(), name), encoding="utf-8") as f:
                    envelope = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(envelope, dict):
                continue
            if envelope.get("client_namespace") != self.client_namespace:
                continue
            document = envelope.get("document")
            if isinstance(document, str):
                found[document] = envelope
        return found

    def state(self, document, remote_revision):
        """MISSING, STALE or IN_SYNC against the Notion-side revision."""
        envelope = self.load(document)
        if envelope is None:
            return "MISSING"
        return "IN_SYNC" if envelope.get("revision") == remote_revision else "STALE"

    def recover(self, document, remote_value, *, revision=1):
        """Rebuild this document from the Notion side. Never invents data.

        ``remote_value`` is what Notion holds. No local data is preferred over
        it: the cached copy is replaced by the authoritative record.
        """
        if remote_value is None:
            if self.load(document) is None:
                raise CacheUnrecoverable(
                    "The Notion side has no record for this character, so the "
                    "local copy cannot be rebuilt. Nothing is invented.")
            return "CACHED_ONLY"
        self.store(document, remote_value, revision=revision, source=SOURCE_OF_TRUTH)
        return "RECOVERED"
