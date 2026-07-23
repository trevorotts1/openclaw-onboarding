#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: media-key storage + URL re-resolution (U039)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network: urllib.request.urlopen is mocked. Proves:
#   1. resolve_media_key() resolves a Podbean media key to a fresh URL from the
#      API response, probing the documented field names (url, download_url,
#      nested file.url, etc.).
#   2. The lookup is BOUNDED: urlopen is always called with a finite timeout
#      (never None / unbounded).
#   3. resolve_media_key() raises when the response carries no resolvable URL.
#   4. The roster stores the media KEY (mp3_media_key) as the primary reference
#      via the `output` subcommand; the ephemeral URL column is separate.
#   5. The `resolve-media-key` CLI command returns the fresh URL end-to-end.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_media_key_resolution.py
# =============================================================================
"""Deterministic tests for media-key storage + URL re-resolution (U039)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podcast_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("podcast_state", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PS = _load_module()


class FakeResponse:
    """Minimal stand-in for urllib's HTTPResponse (context-manager + read)."""

    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestResolveMediaKey(unittest.TestCase):
    """AC#4 + AC#5: the lookup function resolves a key to a fresh URL, bounded."""

    def test_resolves_url_from_top_level_field(self):
        body = json.dumps({"url": "https://cdn.podbean.com/fresh.mp3"}).encode()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)) as m:
            url = PS.resolve_media_key("mk-123", "tok", api_base="http://mock.invalid/v1", timeout=5)
        self.assertEqual(url, "https://cdn.podbean.com/fresh.mp3")
        # Bounded: urlopen was called with a timeout kwarg.
        _, kwargs = m.call_args
        self.assertIn("timeout", kwargs)
        self.assertEqual(kwargs["timeout"], 5)

    def test_probes_nested_file_field(self):
        body = json.dumps({"file": {"download_url": "https://cdn.podbean.com/nested.mp3"}}).encode()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)):
            url = PS.resolve_media_key("mk-123", "tok", api_base="http://mock.invalid/v1", timeout=5)
        self.assertEqual(url, "https://cdn.podbean.com/nested.mp3")

    def test_raises_when_no_url_in_response(self):
        body = json.dumps({"other": "x"}).encode()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)):
            with self.assertRaises(RuntimeError):
                PS.resolve_media_key("mk-123", "tok", api_base="http://mock.invalid/v1", timeout=5)

    def test_default_timeout_is_bounded_and_finite(self):
        self.assertIsInstance(PS.RESOLVE_MEDIA_KEY_TIMEOUT, int)
        self.assertGreater(PS.RESOLVE_MEDIA_KEY_TIMEOUT, 0)


class TestRosterStoresMediaKey(unittest.TestCase):
    """AC#3: the roster stores the media key as the primary reference."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.conn = PS.connect(self.db_path)
        self.addCleanup(self.conn.close)
        self.conn.execute("INSERT INTO podcast_client_state (client_id, active) VALUES ('c1', 1)")
        self.conn.execute(
            "INSERT INTO podcast_jobs (job_id, client_id, location_id, contact_id, "
            "submission_fingerprint, mode, style, status) "
            "VALUES ('pj_test', 'c1', 'loc', 'contact', 'fp', "
            "'interview_style_podcast', 'vulnerable', 'received')"
        )

    def _args(self, **kw):
        base = dict(job_id="pj_test", json=True, db_path=self.db_path)
        base.update(kw)
        return type("Args", (), base)()

    def test_media_key_stored_as_primary_reference(self):
        PS.cmd_output(self.conn, self._args(field="mp3_media_key", value="mk-abc-123"))
        row = self.conn.execute(
            "SELECT mp3_media_key, mp3_media_url FROM podcast_jobs WHERE job_id='pj_test'"
        ).fetchone()
        # The KEY is stored as the primary reference.
        self.assertEqual(row["mp3_media_key"], "mk-abc-123")
        # The ephemeral URL is a separate column, not the primary reference.
        self.assertIsNone(row["mp3_media_url"])

    def test_resolve_media_key_command_returns_fresh_url(self):
        PS.cmd_output(self.conn, self._args(field="mp3_media_key", value="mk-abc-123"))
        body = json.dumps({"url": "https://cdn.podbean.com/fresh.mp3"}).encode()
        buf = io.StringIO()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)):
            with contextlib.redirect_stdout(buf):
                PS.cmd_resolve_media_key(
                    self.conn,
                    self._args(field="mp3", access_token="tok", api_base="http://mock.invalid/v1"),
                )
        out = json.loads(buf.getvalue().strip())
        self.assertEqual(out["fresh_url"], "https://cdn.podbean.com/fresh.mp3")
        self.assertEqual(out["media_key"], "mk-abc-123")

    def test_resolve_media_key_command_fails_without_recorded_key(self):
        # No key recorded yet -> UsageError.
        with self.assertRaises(PS.UsageError):
            PS.cmd_resolve_media_key(
                self.conn,
                self._args(field="mp3", access_token="tok", api_base="http://mock.invalid/v1"),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
