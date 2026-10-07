#!/usr/bin/env python3
"""tests/unit/semantic-task-fit-local-mode.test.py

The persona selector's in-process Layer-5 (semantic_task_fit / Stage-C
semantic_persona_ids) on a LOCAL-mode box — one whose persona index was
re-embedded with `embedding_engine.py --reembed-local` (rows stamped
provider='ollama'). Offline: a stub Ollama /api/embed on a loopback port.

  1. Local index: the task is embedded with the index's stamped model through
     embedding_engine._ollama_embed (embeddinggemma query prefix), scored only
     against that model's rows, method "ollama_embedding"; Gemini never called.
  2. Gemini index: unchanged — Gemini embeds, method "gemini_embedding", the
     stub Ollama receives zero requests.
  3. Ollama down: keyword overlap, ONE log line, one attempt per process, no
     Gemini call.
  4. Mixed (partial re-embed) local index: keyword, no embed call at all.

Run: python3 tests/unit/semantic-task-fit-local-mode.test.py -v
"""
from __future__ import annotations

import contextlib
import hashlib
import http.server
import importlib
import io
import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENCLAW_SANDBOX", "1")
GEMMA = "embeddinggemma-2:740m"
os.environ["OLLAMA_EMBED_MODEL"] = GEMMA
os.environ["OLLAMA_EMBED_DIM"] = "768"

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "shared-utils"))

import numpy as np  # noqa: E402
import embedding_engine as ee  # noqa: E402
import semantic_task_fit as m  # noqa: E402


def _bow(text: str, dims: int) -> list:
    v = [0.0] * dims
    for w in text.lower().replace("|", " ").replace(":", " ").split():
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dims] += 1.0
    return v


class _Stub(http.server.BaseHTTPRequestHandler):
    calls: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Stub.calls.append(body)
        out = json.dumps({"embeddings": [_bow(body["input"], 768)]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def setUpModule():
    global SERVER, URL
    SERVER = http.server.HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    URL = f"http://127.0.0.1:{SERVER.server_address[1]}"


def tearDownModule():
    SERVER.shutdown()
    SERVER.server_close()


PERSONAS = {
    "alpha": "sales negotiation closing objections pricing",
    "beta": "leadership team culture hiring delegation",
}


def _index(path: Path, rows) -> Path:
    """rows: (persona_id, provider, model, vector)"""
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE embeddings (id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER, "
              "content TEXT, vector BLOB, last_updated REAL, provider TEXT, model TEXT, dim INTEGER)")
    for i, (pid, prov, model, vec) in enumerate(rows):
        c.execute("INSERT INTO embeddings VALUES (?,?,0,?,?,0,?,?,?)",
                  (f"r{i}", f"/x/coaching-personas/personas/{pid}/persona-blueprint.md",
                   PERSONAS[pid], np.asarray(vec, dtype=np.float32).tobytes(), prov, model, len(vec)))
    c.commit()
    c.close()
    return path


def _local_rows(model=GEMMA):
    # Document vectors as --reembed-local writes them (document prefix).
    return [(pid, "ollama", model, _bow(f"title: none | text: {t}", 768)) for pid, t in PERSONAS.items()]


class _GenaiSpy:
    """Fake google.genai.Client: counts calls, returns a fixed 3-dim vector."""
    calls = 0

    def __init__(self, api_key=None, **_):
        class _Models:
            def embed_content(self, **kw):
                _GenaiSpy.calls += 1

                class R:
                    embeddings = [type("V", (), {"values": [1.0, 0.0, 0.0]})()]
                return R()
        self.models = _Models()


class _Base(unittest.TestCase):
    def setUp(self):
        global m
        m = importlib.reload(m)
        _Stub.calls = []
        _GenaiSpy.calls = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "gemini-index.sqlite"
        self.paths = {"gemini_index": self.db, "secrets": Path(self.tmp.name)}
        os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
        self._url = patch.object(ee, "OLLAMA_EMBED_URL", URL)
        self._url.start()
        # Fake google.genai in sys.modules: runs with or without the real SDK.
        g, genai, gtypes = (types.ModuleType(n) for n in ("google", "google.genai", "google.genai.types"))
        gtypes.EmbedContentConfig = lambda **kw: kw
        genai.Client, genai.types, g.genai = _GenaiSpy, gtypes, genai
        self._genai = patch.dict(sys.modules, {"google": g, "google.genai": genai,
                                               "google.genai.types": gtypes})
        self._genai.start()

    def tearDown(self):
        self._genai.stop()
        self._url.stop()
        os.environ.pop("GOOGLE_API_KEY", None)
        self.tmp.cleanup()

    def run_quiet(self, fn, *a):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = fn(*a)
        return out, err.getvalue()


class TestLocalMode(_Base):
    def test_layer5_embeds_locally_with_model_and_query_prefix(self):
        _index(self.db, _local_rows())
        r, _ = self.run_quiet(m.semantic_task_fit, "alpha", "sales negotiation pricing", self.paths)
        self.assertEqual(r["method"], "ollama_embedding", r)
        self.assertIn(f"model={GEMMA}", r["detail"])
        self.assertEqual(len(_Stub.calls), 1)
        self.assertEqual(_Stub.calls[0]["model"], GEMMA)
        self.assertEqual(_Stub.calls[0]["input"], "task: search result | query: sales negotiation pricing")
        self.assertEqual(_GenaiSpy.calls, 0, "a local-mode box must never call Gemini")
        # Second candidate reuses the cached task vector (one embed per selection).
        r2, _ = self.run_quiet(m.semantic_task_fit, "beta", "sales negotiation pricing", self.paths)
        self.assertEqual(r2["method"], "ollama_embedding")
        self.assertGreater(r["score"], r2["score"], "the matching persona must score higher")
        self.assertEqual(len(_Stub.calls), 1)

    def test_stage_c_ranks_locally_and_shares_the_task_embed(self):
        _index(self.db, _local_rows())
        ids, _ = self.run_quiet(m.semantic_persona_ids, "leadership hiring culture", self.paths)
        self.assertEqual(ids[0], "beta")
        self.run_quiet(m.semantic_task_fit, "beta", "leadership hiring culture", self.paths)
        self.assertEqual(len(_Stub.calls), 1, "Stage C and Layer 5 share one task embed")
        self.assertEqual(_GenaiSpy.calls, 0)

    def test_index_stamped_with_another_model_queries_that_model(self):
        _index(self.db, _local_rows(model="other-embed-model"))
        self.run_quiet(m.semantic_task_fit, "alpha", "sales", self.paths)
        self.assertEqual(_Stub.calls[0]["model"], "other-embed-model")
        self.assertEqual(_Stub.calls[0]["input"], "sales", "non-embeddinggemma models get raw text")


class TestGeminiBoxUnchanged(_Base):
    def test_gemini_index_uses_gemini_and_never_ollama(self):
        _index(self.db, [(pid, "gemini", ee.GEMINI_MODEL, [1.0, 0.0, 0.0]) for pid in PERSONAS])
        r, _ = self.run_quiet(m.semantic_task_fit, "alpha", "sales", self.paths)
        self.assertEqual(r, {"score": 0.98, "method": "gemini_embedding",
                             "detail": "cos=1.000, db=gemini-index.sqlite"})
        ids, _ = self.run_quiet(m.semantic_persona_ids, "sales", self.paths)
        self.assertEqual(sorted(ids), ["alpha", "beta"])
        self.assertEqual(_GenaiSpy.calls, 1)
        self.assertEqual(_Stub.calls, [], "a Gemini box must never call Ollama")


class TestOllamaDown(_Base):
    def test_keyword_fallback_one_log_line_no_gemini(self):
        _index(self.db, _local_rows())
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        dead = f"http://127.0.0.1:{s.getsockname()[1]}"
        s.close()  # nothing listens here now
        with patch.object(ee, "OLLAMA_EMBED_URL", dead):
            results, err = self.run_quiet(
                lambda: [m.semantic_task_fit(p, "sales negotiation", self.paths) for p in PERSONAS])
            ids, err2 = self.run_quiet(m.semantic_persona_ids, "sales negotiation", self.paths)
        self.assertTrue(all(r["method"] in ("keyword_overlap", "neutral_fallback") for r in results), results)
        self.assertEqual(results[0]["score"], m._keyword_overlap_score("alpha", "sales negotiation"))
        self.assertIsNone(ids)
        lines = [ln for ln in (err + err2).splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("local Ollama embed failed", lines[0])
        self.assertEqual(_GenaiSpy.calls, 0)


class TestMixedLocalIndex(_Base):
    def test_partial_reembed_is_keyword_without_any_embed(self):
        rows = _local_rows()[:1] + [("beta", "gemini", ee.GEMINI_MODEL, [1.0, 0.0, 0.0])]
        _index(self.db, rows)
        r, err = self.run_quiet(m.semantic_task_fit, "alpha", "sales negotiation", self.paths)
        self.assertEqual(r["method"], "keyword_overlap")
        self.assertIn("mixed-model", err)
        self.assertEqual((_Stub.calls, _GenaiSpy.calls), ([], 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
