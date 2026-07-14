#!/usr/bin/env python3
"""Unit test for F1.2 (FDN-5): orchestrator.py Phase-5 (embedding) failure
propagates a DISTINCT non-zero exit code (8 = EMBED_FAILED) end-to-end from
--single-book mode, while a successful embed exits 0.

The heavy pipeline (LLM calls, provider preflight, the real Gemini indexer) is
stubbed so the test is hermetic — it exercises ONLY the exit-code decision in
main()'s single-book tail against a controlled pipeline-status outcome.

Run:
    python3 tests/unit/orchestrator-embed-fail-exit8.test.py
    or: pytest tests/unit/orchestrator-embed-fail-exit8.test.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_PIPE = _REPO_ROOT / "22-book-to-persona-coaching-leadership-system" / "pipeline"
sys.path.insert(0, str(_PIPE))

# orchestrator.py's main() unconditionally builds an aiohttp.TCPConnector +
# aiohttp.ClientSession as async-with infrastructure BEFORE dispatching to
# preflight_providers/process_book (both stubbed below) — so even this
# fixture-only, no-network test needs a real `aiohttp` name to import
# cleanly. This test never calls a session method (process_book is replaced
# with a stub that ignores `session`), so a minimal fake with working
# async-context-manager support is enough. Matches the same
# inject-a-fake-aiohttp-module pattern tests/unit/storm-guard.test.sh and
# tests/unit/pipeline-provider-routing.test.sh already use for this exact
# "aiohttp not installed on the bare CI runner" gap — injected unconditionally
# (not gated on a real import failing) for deterministic behavior whether or
# not the box running this test happens to have aiohttp installed.
class _FakeClientTimeout:
    def __init__(self, *a, **k):
        pass


class _FakeClientSession:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeTCPConnector:
    def __init__(self, *a, **k):
        pass


_fake_aiohttp = types.ModuleType("aiohttp")
_fake_aiohttp.ClientSession = _FakeClientSession
_fake_aiohttp.ClientTimeout = _FakeClientTimeout
_fake_aiohttp.TCPConnector = _FakeTCPConnector
sys.modules["aiohttp"] = _fake_aiohttp

_spec = importlib.util.spec_from_file_location("orchestrator", _PIPE / "orchestrator.py")
orch = importlib.util.module_from_spec(_spec)
sys.modules["orchestrator"] = orch
_spec.loader.exec_module(orch)


def _args(slug: str, source_json: str):
    ns = types.SimpleNamespace()
    ns.single_book = True
    ns.slug = slug
    ns.source_json = source_json
    return ns


class TestOrchestratorEmbedFailExit8(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.slug = "fixture-author-fixture-book"
        personas = base / "personas"
        (personas / self.slug).mkdir(parents=True)
        # A blueprint on disk so run_synthesis' re-entry path is available and
        # the "leave blueprint on disk" invariant is observable.
        (personas / self.slug / "persona-blueprint.md").write_text("# BP\n")
        # source.json marker (what add-persona-from-source.sh writes).
        self.source_json = personas / self.slug / "source.json"
        self.source_json.write_text(json.dumps({
            "slug": self.slug, "title": "Fixture Book", "author": "Fixture Author",
            "source_type": "text", "source_path": "", "text_file": "",
            "pipeline_status": "PENDING",
        }))

        # Redirect all module-level paths at the fixture sandbox.
        self._orig = {k: getattr(orch, k) for k in
                      ("BASE", "PERSONAS_DIR", "STATUS_FILE", "LOG_FILE")}
        orch.BASE = base
        orch.PERSONAS_DIR = personas
        orch.STATUS_FILE = base / "pipeline-status.json"
        orch.LOG_FILE = base / "pipeline-log.txt"

        # Stub the network / heavy bits. init_storm_guard + preflight are no-ops;
        # process_book is replaced with a coroutine that records a controllable
        # phase5 outcome (the thing under test). _assert_provider_route is also
        # stubbed: it is a SEPARATE precondition main() checks before
        # preflight_providers ever runs (no API key / no local Ollama daemon on
        # a bare CI runner would otherwise raise ValueError before main() ever
        # reaches the phase5 exit-code tail this test exercises) — this test
        # is about the phase5-outcome-to-exit-code mapping, never about
        # live provider-route availability.
        self._orig_pre = orch.preflight_providers
        self._orig_isg = orch.init_storm_guard
        self._orig_pb = orch.process_book
        self._orig_apr = orch._assert_provider_route

        async def _no_preflight(*a, **k):
            return None
        orch.preflight_providers = _no_preflight
        orch.init_storm_guard = lambda *a, **k: None
        orch._assert_provider_route = lambda: None

        # Neutralize orphan-guard lock/arm side effects if the module is present.
        try:
            import orphan_guard as og  # noqa
            self._og = og
            self._orig_og = (og.arm, og.acquire_slug_lock, og.run_dir_path)
            og.arm = lambda *a, **k: None
            og.acquire_slug_lock = lambda *a, **k: object()
            og.run_dir_path = lambda p: p
        except Exception:
            self._og = None

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(orch, k, v)
        orch.preflight_providers = self._orig_pre
        orch.init_storm_guard = self._orig_isg
        orch.process_book = self._orig_pb
        orch._assert_provider_route = self._orig_apr
        if self._og is not None:
            self._og.arm, self._og.acquire_slug_lock, self._og.run_dir_path = self._orig_og
        self.tmp.cleanup()

    def _run_with_phase5(self, phase5_outcome: str):
        """Patch process_book to record the given phase5 outcome, run main(),
        and return the SystemExit code (0 means clean return / exit 0)."""
        slug = self.slug

        async def _pb(session, book, status):
            folder = book["folder"]
            status[folder]["phase1"] = "COMPLETE"
            status[folder]["phase2"] = "COMPLETE"
            status[folder]["phase3"] = "COMPLETE"
            status[folder]["phase5"] = phase5_outcome
            orch.save_status(status)
        orch.process_book = _pb

        try:
            asyncio.run(orch.main(_args(slug, str(self.source_json))))
            return 0
        except SystemExit as e:
            return int(e.code) if e.code is not None else 0

    def test_embed_failed_exits_8(self):
        code = self._run_with_phase5("FAILED")
        self.assertEqual(code, 8, "Phase-5 FAILED must propagate exit code 8 (EMBED_FAILED)")
        # Invariant: the blueprint is LEFT ON DISK for an idempotent re-embed.
        self.assertTrue((orch.PERSONAS_DIR / self.slug / "persona-blueprint.md").exists(),
                        "blueprint must remain on disk after EMBED_FAILED")

    def test_embed_done_exits_0(self):
        code = self._run_with_phase5("DONE")
        self.assertEqual(code, 0, "Phase-5 DONE must exit 0 (no false failure)")

    def test_embed_deferred_exits_0(self):
        # A-U8: DEFERRED (credential-shaped gap, honest receipt written) is
        # NOT "FAILED" — the single-book tail's exit-8 gate must not fire.
        code = self._run_with_phase5("DEFERRED")
        self.assertEqual(code, 0,
                         "Phase-5 DEFERRED must exit 0 — an honest, "
                         "non-fatal credential gap is never EMBED_FAILED (8)")
        # Invariant: the blueprint ships regardless (same as DONE/FAILED).
        self.assertTrue((orch.PERSONAS_DIR / self.slug / "persona-blueprint.md").exists(),
                        "blueprint must remain on disk after a DEFERRED embed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
