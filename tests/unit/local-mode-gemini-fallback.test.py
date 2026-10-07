#!/usr/bin/env python3
"""tests/unit/local-mode-gemini-fallback.test.py

Local-mode box (persona index rows provider='ollama') with its Ollama DOWN:
persona selection uses PAID GEMINI on the box's OWN key against a SEPARATE
Gemini fallback copy (gemini-fallback-index.sqlite); keyword only if Gemini also
fails / no key / no copy. Offline: fake google.genai, dead loopback port.

  1. Ollama down + key + copy  -> Gemini used against the COPY (no mixing).
  2. no key                    -> keyword.   3. Gemini error -> keyword, one try.
  4. no copy                   -> keyword.
  5. search() (embedding_engine) same order.
  6. --reembed-local never overwrites the copy; provision_gemini_fallback_index
     installs it (sha-verified, idempotent) and never touches the live index.
  7. the vendored semantic_task_fit is byte-identical.
  8. embedding_health reports the copy/key as names only.

Run: python3 tests/unit/local-mode-gemini-fallback.test.py -v
"""
from __future__ import annotations

import contextlib
import gzip
import hashlib
import importlib
import io
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENCLAW_SANDBOX", "1")
GEMMA = "embeddinggemma-2:740m"
os.environ["OLLAMA_EMBED_MODEL"] = GEMMA
os.environ["OLLAMA_EMBED_DIM"] = "768"
SECRET_KEY = "test-key-not-real"

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "shared-utils"))

import numpy as np  # noqa: E402
import embedding_engine as ee  # noqa: E402
import semantic_task_fit as m  # noqa: E402

DIM = ee.GEMINI_OUTPUT_DIM
PERSONAS = {"alpha": "sales negotiation pricing", "beta": "leadership hiring culture"}


def _vec(i):  # unit vector on axis i of the Gemini space
    v = np.zeros(DIM, dtype=np.float32)
    v[i] = 1.0
    return v


def _index(path: Path, rows) -> Path:
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


def _local_rows():
    return [(pid, "ollama", GEMMA, np.ones(768, dtype=np.float32) * (i + 1)) for i, pid in enumerate(PERSONAS)]


def _fallback_rows():
    return [(pid, "gemini", ee.GEMINI_MODEL, _vec(i)) for i, pid in enumerate(PERSONAS)]


class _Genai:
    """Fake google.genai.Client. Query vector = axis 1 (== persona 'beta')."""
    calls = 0
    keys: list = []
    fail = False

    def __init__(self, api_key=None, **_):
        _Genai.keys.append(api_key)

        class _Models:
            def embed_content(self, **kw):
                _Genai.calls += 1
                if _Genai.fail:
                    raise RuntimeError("503 gemini unavailable")

                class R:
                    embeddings = [type("V", (), {"values": list(_vec(1))})()]
                return R()
        self.models = _Models()


def _dead_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{s.getsockname()[1]}"
    s.close()
    return url


class _Base(unittest.TestCase):
    key = True
    copy = True

    def setUp(self):
        global m
        m = importlib.reload(m)
        _Genai.calls, _Genai.keys, _Genai.fail = 0, [], False
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.db = _index(d / "gemini-index.sqlite", _local_rows())
        self.fb = d / "gemini-fallback-index.sqlite"
        if self.copy:
            _index(self.fb, _fallback_rows())
        self.paths = {"gemini_index": self.db, "secrets": d}
        # HOME -> temp so a real ~/.openclaw/openclaw.json key can never leak in.
        self._env = patch.dict(os.environ, {"HOME": str(d)})
        self._env.start()
        for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(k, None)
        if self.key:
            os.environ["GOOGLE_API_KEY"] = SECRET_KEY
        self._url = patch.object(ee, "OLLAMA_EMBED_URL", _dead_url())
        self._url.start()
        g, genai, gt = (types.ModuleType(n) for n in ("google", "google.genai", "google.genai.types"))
        gt.EmbedContentConfig = lambda **kw: kw
        gt.HttpOptions = lambda **kw: kw
        genai.Client, genai.types, g.genai = _Genai, gt, genai
        self._genai = patch.dict(sys.modules, {"google": g, "google.genai": genai, "google.genai.types": gt})
        self._genai.start()

    def tearDown(self):
        self._genai.stop()
        self._url.stop()
        self._env.stop()
        self.tmp.cleanup()

    def quiet(self, fn, *a, **k):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = fn(*a, **k)
        return out, err.getvalue()


class TestFallbackOrder(_Base):
    def test_ollama_down_key_and_copy_uses_gemini_against_the_copy_only(self):
        r, err = self.quiet(m.semantic_task_fit, "beta", "leadership hiring", self.paths)
        self.assertEqual(r["method"], "gemini_embedding", r)
        self.assertIn("gemini-fallback-index.sqlite", r["detail"])
        self.assertEqual(r["score"], 0.98)  # query == beta's copy vector, cos 1.0
        r2, _ = self.quiet(m.semantic_task_fit, "alpha", "leadership hiring", self.paths)
        self.assertEqual(r2["score"], 0.5)  # orthogonal axis, cos 0.0: copy rows, not local rows
        self.assertEqual(_Genai.calls, 1, "one paid embed per selection")
        self.assertEqual(_Genai.keys, [SECRET_KEY], "the box's own key")
        self.assertEqual(err.count("local Ollama embed failed"), 1)
        ids, _ = self.quiet(m.semantic_persona_ids, "leadership hiring", self.paths)
        self.assertEqual(ids[0], "beta")
        self.assertEqual(_Genai.calls, 1, "Stage C shares the task embed")

    def test_key_only_in_openclaw_json_env_vars_still_uses_gemini(self):
        os.environ.pop("GOOGLE_API_KEY")
        oc = Path(os.environ["HOME"]) / ".openclaw"
        oc.mkdir()
        (oc / "openclaw.json").write_text('{"env":{"vars":{"GOOGLE_API_KEY":"%s"}}}' % SECRET_KEY)
        r, err = self.quiet(m.semantic_task_fit, "beta", "leadership hiring", self.paths)
        self.assertEqual(r["method"], "gemini_embedding", r)
        self.assertEqual(_Genai.keys, [SECRET_KEY])
        self.assertNotIn(SECRET_KEY, err)

    def test_gemini_box_key_lookup_unchanged(self):
        os.environ.pop("GOOGLE_API_KEY")
        oc = Path(os.environ["HOME"]) / ".openclaw"
        oc.mkdir()
        (oc / "openclaw.json").write_text('{"env":{"vars":{"GOOGLE_API_KEY":"%s"}}}' % SECRET_KEY)
        self.assertEqual(m._get_google_api_key(self.paths), "")

    def test_no_key_is_keyword(self):
        os.environ.pop("GOOGLE_API_KEY")
        self.assertEqual(self._keyword_only()[0], 0)

    def _keyword_only(self):
        rs, err = self.quiet(lambda: [m.semantic_task_fit(p, "sales pricing", self.paths) for p in PERSONAS])
        self.assertTrue(all(r["method"] in ("keyword_overlap", "neutral_fallback") for r in rs), rs)
        ids, _ = self.quiet(m.semantic_persona_ids, "sales pricing", self.paths)
        self.assertIsNone(ids)
        return _Genai.calls, err

    def test_gemini_error_is_keyword_and_latched(self):
        _Genai.fail = True
        calls, err = self._keyword_only()
        self.assertEqual(calls, 1, "one failed Gemini attempt per process, not per candidate")
        self.assertIn("Gemini fallback embed failed", err)

    def test_retries_local_on_next_process(self):
        global m
        self.quiet(m.semantic_task_fit, "beta", "x leadership", self.paths)
        self.assertTrue(m._LOCAL_DOWN)
        m = importlib.reload(sys.modules["semantic_task_fit"])  # a new process
        self.assertFalse(m._LOCAL_DOWN)


class TestNoCopy(_Base):
    copy = False

    def test_no_copy_is_keyword_without_a_paid_call(self):
        rs, _ = self.quiet(lambda: [m.semantic_task_fit(p, "sales pricing", self.paths) for p in PERSONAS])
        self.assertTrue(all(r["method"] == "keyword_overlap" for r in rs), rs)
        self.assertEqual(_Genai.calls, 0)


class TestSearchOrder(_Base):
    def _run(self, fake_key=True, fail=False):
        class Client:
            class models:
                @staticmethod
                def embed_content(**kw):
                    if fail:
                        raise RuntimeError("503 gemini unavailable")
                    return type("R", (), {"embeddings": [type("V", (), {"values": list(_vec(1))})()]})()
        if not fake_key:
            os.environ.pop("GOOGLE_API_KEY", None)  # truly keyless box
        real = ee.get_embedder

        def fake(provider_hint=None):
            if provider_hint == "gemini":
                return ("gemini", Client, ee.GEMINI_MODEL) if fake_key else None
            return real(provider_hint)
        buf, err = io.StringIO(), io.StringIO()
        with patch.object(ee, "get_embedder", fake), \
                patch.object(ee, "_genai_types", types.SimpleNamespace(EmbedContentConfig=lambda **k: k)), \
                contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = ee.search("leadership hiring", 2, str(self.db))
        return rc, buf.getvalue(), err.getvalue()

    def test_gemini_against_copy(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("PERSONA: beta", out)
        self.assertIn("SCORE: 1.0000 | PERSONA: beta", out)
        self.assertNotIn("KEYWORD", out)
        self.assertIn("gemini-fallback-index.sqlite", err)

    def test_key_only_in_env_vars_still_uses_gemini(self):
        os.environ.pop("GOOGLE_API_KEY")
        oc = Path(os.environ["HOME"]) / ".openclaw"
        oc.mkdir()
        (oc / "openclaw.json").write_text('{"env":{"vars":{"GOOGLE_API_KEY":"%s"}}}' % SECRET_KEY)
        real = ee.get_embedder
        patches = [
            patch.object(ee, "get_embedder", lambda provider_hint=None: None if provider_hint == "gemini" else real(provider_hint)),
            patch.object(ee, "GENAI_AVAILABLE", True),
            patch.object(ee, "genai", types.SimpleNamespace(Client=_Genai), create=True),
            patch.object(ee, "_genai_types", types.SimpleNamespace(
                EmbedContentConfig=lambda **k: k, HttpOptions=lambda **k: k)),
        ]
        buf, err = io.StringIO(), io.StringIO()
        for p_ in patches:
            p_.start()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                rc = ee.search("leadership hiring", 2, str(self.db))
        finally:
            for p_ in patches:
                p_.stop()
        self.assertEqual(rc, 0)
        self.assertNotIn("KEYWORD", buf.getvalue())
        self.assertIn("PERSONA: beta", buf.getvalue())
        self.assertEqual(_Genai.keys, [SECRET_KEY])
        self.assertNotIn(SECRET_KEY, err.getvalue() + buf.getvalue())

    def test_no_key_keyword(self):
        rc, out, _ = self._run(fake_key=False)
        self.assertEqual(rc, 0)
        self.assertIn("KEYWORD-HITS", out)

    def test_gemini_error_keyword(self):
        rc, out, _ = self._run(fail=True)
        self.assertEqual(rc, 0)
        self.assertIn("KEYWORD-HITS", out)


class TestCopyIsSeparate(_Base):
    def test_reembed_local_never_overwrites_the_copy(self):
        self.db.unlink()  # a not-yet-converted (gemini) live index, so reembed-local really writes
        _index(self.db, _fallback_rows())
        before = hashlib.sha256(self.fb.read_bytes()).hexdigest()
        live_before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        import http.server, json, threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                self.rfile.read(int(self.headers["Content-Length"]))
                out = json.dumps({"embeddings": [[0.5] * 768]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with patch.object(ee, "OLLAMA_EMBED_URL", f"http://127.0.0.1:{srv.server_address[1]}"):
                self.quiet(ee.cmd_reembed_local, str(self.db))
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(hashlib.sha256(self.fb.read_bytes()).hexdigest(), before)
        self.assertEqual(ee.gemini_fallback_index_path(str(self.db)), str(self.fb))
        self.assertNotEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), live_before)


class TestProvision(unittest.TestCase):
    def test_install_idempotent_and_live_index_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            src = d / "asset.sqlite"
            _index(src, _fallback_rows())
            gz = d / "asset.gz"
            gz.write_bytes(gzip.compress(src.read_bytes()))
            man = d / "m.json"
            man.write_text('{"asset_url":"file://%s","sha256":"%s","release_tag":"t1","persona_count":2}'
                           % (gz, hashlib.sha256(gz.read_bytes()).hexdigest()))
            cdir = d / "coach"
            cdir.mkdir()
            live = _index(cdir / "gemini-index.sqlite", _local_rows())
            lsha = hashlib.sha256(live.read_bytes()).hexdigest()
            run = lambda: subprocess.run(  # noqa: E731
                ["/bin/bash", "-c", f'. "{REPO}/shared-utils/provision-persona-index.sh"; '
                 f'provision_gemini_fallback_index "{man}" "{cdir}"'],
                capture_output=True, text=True)
            out = run().stdout
            self.assertIn("installed", out)
            fb = cdir / "gemini-fallback-index.sqlite"
            self.assertEqual(fb.read_bytes(), src.read_bytes())
            gz.unlink()  # a second run must not need the network
            self.assertIn("already provisioned", run().stdout)
            self.assertEqual(hashlib.sha256(live.read_bytes()).hexdigest(), lsha)
            # new release with a WRONG sha: refused, the good copy is kept
            gz.write_bytes(b"corrupt")
            man.write_text(man.read_text().replace("t1", "t2"))
            self.assertIn("sha256 MISMATCH", run().stdout)
            self.assertEqual(fb.read_bytes(), src.read_bytes())


class TestVendoredAndHealth(unittest.TestCase):
    def test_vendored_semantic_task_fit_identical(self):
        v = (REPO / "23-ai-workforce-blueprint/templates/role-library/presentations/scripts/"
             "presentation_job/persona_service/resources/helpers/semantic_task_fit.py")
        self.assertEqual(v.read_bytes(), (REPO / "shared-utils/semantic_task_fit.py").read_bytes())

    def test_health_reports_names_only(self):
        eh = importlib.import_module("embedding_health")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            cd = root / "workspace/data/coaching-personas"
            cd.mkdir(parents=True)
            _index(cd / "gemini-index.sqlite", _local_rows())
            _index(cd / "gemini-fallback-index.sqlite", _fallback_rows())
            with patch.dict(os.environ, {"GOOGLE_API_KEY": SECRET_KEY, "HOME": t}), \
                    patch.object(eh, "_apply_local_smoke", lambda *a, **k: None), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                res = eh.check_persona_gemini_index(root, {}, None)
        self.assertTrue(res["gemini_fallback_copy_present"])
        self.assertTrue(res["gemini_fallback_key_present"])
        self.assertIn("gemini-fallback-index.sqlite present", err.getvalue())
        self.assertNotIn(SECRET_KEY, err.getvalue() + repr(res))


if __name__ == "__main__":
    unittest.main(verbosity=2)
