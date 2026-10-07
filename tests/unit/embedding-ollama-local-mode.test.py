#!/usr/bin/env python3
"""
tests/unit/embedding-ollama-local-mode.test.py
─────────────────────────────────────────────────────────────────────────────
Local Ollama embeddings — the explicit, per-box, FREE opt-in for a box whose
Gemini key cannot pay (docs/EMBEDDINGS.md "Local Ollama mode").

Proves, offline (a stub Ollama /api/embed server on a random loopback port):
  1. get_embedder() only returns ollama for the explicit hint (never auto).
  2. EMBED-3: --verify stays gemini/3072 by default (a 768 ollama index FAILS it);
     --verify-provider ollama holds the index to 768 and still fails fake rows.
  3. cmd_reembed_local converts a gemini index in place (ids/metadata kept),
     is resumable, and search() then returns VECTOR hits via the local model.
  4. search() on an ollama index with Ollama down falls back to keyword (rc 0).
  5. provision_sop_embeddings.py SKIPs a CC DB carrying the
     sop_embeddings_local_provider marker (never overwrites local vectors).
  6. provision-persona-index.sh keeps a provider='ollama' index (no download).
  7. embedding_health.py: persona + cc_sop local mode pass against a loopback
     Ollama and FAIL for a non-loopback URL (Ollama Cloud never embeds).
  8. OLLAMA_EMBED_MODEL / OLLAMA_EMBED_DIM: default embeddinggemma-2:740m@768;
     env (and secrets/.env) override it; rows are stamped with the model used,
     the ollama --verify accepts it and rejects a mismatch or a mixed-model
     index (with a --reembed-local hint), search() queries with the
     index's stamped model, and embeddinggemma gets its model-card prefixes.

Every test fails on the pre-change tree (no ollama provider / flags / guards).

Run: python3 tests/unit/embedding-ollama-local-mode.test.py -v
"""
from __future__ import annotations

import atexit
import contextlib
import hashlib
import http.server
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

tempfile.tempdir = tempfile.mkdtemp(prefix="onb-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)
os.environ.setdefault("OPENCLAW_SANDBOX", "1")
# Pin the local model for the in-process tests so a box whose secrets/.env sets
# OLLAMA_EMBED_MODEL still sees the default contract (TestModelOverride proves
# the real default in a clean-HOME subprocess).
GEMMA = "embeddinggemma-2:740m"
OTHER = "other-embed-model"  # any non-default local model
os.environ["OLLAMA_EMBED_MODEL"] = GEMMA
os.environ["OLLAMA_EMBED_DIM"] = "768"

REPO = Path(__file__).resolve().parent.parent.parent
SU = REPO / "shared-utils"
sys.path.insert(0, str(SU))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


ee = _load("embedding_engine", SU / "embedding_engine.py")
eh = _load("embedding_health", SU / "embedding_health.py")
pse = _load("provision_sop_embeddings", SU / "sop-embed-once" / "provision_sop_embeddings.py")

import numpy as np  # noqa: E402  (embedding_engine needs numpy too)


def _tmp(suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


def _bow(text: str, dims: int = 768) -> list:
    """Deterministic bag-of-words vector: shared words => high cosine."""
    v = [0.0] * dims
    for w in text.lower().split():
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dims] += 1.0
    return v


class _Stub(http.server.BaseHTTPRequestHandler):
    dims = 768
    last = None  # last request body, for model/prefix assertions

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Stub.last = body
        out = json.dumps({"embeddings": [_bow(body["input"], _Stub.dims)]}).encode()
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
    ee.OLLAMA_EMBED_URL = URL
    os.environ["OLLAMA_EMBED_URL"] = URL


def tearDownModule():
    SERVER.shutdown()
    SERVER.server_close()


PERSONA_ROWS = [
    ("alpha__section_03", "sales negotiation closing objections pricing"),
    ("beta__section_03", "leadership team culture hiring delegation"),
    ("gamma__section_04", "marketing funnel landing page conversion copy"),
]


def _gemini_index() -> str:
    db = _tmp(".sqlite")
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE embeddings (id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER, "
              "content TEXT, vector BLOB, last_updated REAL, provider TEXT, model TEXT, dim INTEGER, "
              "section_number INTEGER, mode TEXT, persona_id TEXT)")
    for rid, content in PERSONA_ROWS:
        pid = rid.split("__")[0]
        c.execute("INSERT INTO embeddings VALUES (?,?,0,?,?,0,'gemini','gemini-embedding-2',3072,3,'both',?)",
                  (rid, f"/x/coaching-personas/personas/{pid}/persona-blueprint.md", content,
                   np.zeros(3072, dtype=np.float32).tobytes(), pid))
    c.commit()
    c.close()
    return db


def _quiet(fn, *a, **k):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **k)
    return rc, out.getvalue(), err.getvalue()


class TestEngine(unittest.TestCase):
    def test_ollama_only_on_explicit_hint(self):
        self.assertEqual(ee.get_embedder(provider_hint="ollama"), ("ollama", URL, GEMMA))
        with self.assertRaises(ValueError):
            ee.get_embedder(provider_hint="local")

    def test_reembed_verify_and_vector_search(self):
        db = _gemini_index()
        rc, out, err = _quiet(ee.cmd_reembed_local, db_path=db, batch_size=2, pause=0)
        self.assertEqual(rc, 0, out + err)
        c = sqlite3.connect(db)
        rows = c.execute("SELECT id, provider, model, dim, length(vector), persona_id, mode FROM embeddings").fetchall()
        c.close()
        self.assertEqual({r[0] for r in rows}, {r[0] for r in PERSONA_ROWS})  # ids kept
        for r in rows:
            self.assertEqual(r[1:5], ("ollama", GEMMA, 768, 768 * 4))
            self.assertEqual(r[6], "both")  # section metadata untouched
        # resumable: nothing left to do
        rc, out, _ = _quiet(ee.cmd_reembed_local, db_path=db, batch_size=2, pause=0)
        self.assertEqual(rc, 0)
        self.assertIn("0 row(s) to embed", out)
        # EMBED-3: default verify is gemini/3072 and must FAIL this index
        self.assertEqual(_quiet(ee.verify_index_integrity, db)[0], 4)
        self.assertEqual(_quiet(ee.verify_index_integrity, db, expect_provider="ollama")[0], 0)
        # search uses the local model and returns vector (SCORE) hits
        rc, out, err = _quiet(ee.search, "negotiation pricing objections", 1, db)
        self.assertEqual(rc, 0, err)
        self.assertIn("SCORE:", out)
        self.assertIn("PERSONA: alpha", out)
        self.assertNotIn("keyword-fallback", err)

    def test_fake_768_rows_fail_the_ollama_verify(self):
        db = _gemini_index()
        _quiet(ee.cmd_reembed_local, db_path=db, pause=0)
        c = sqlite3.connect(db)
        c.execute("UPDATE embeddings SET provider='fake', model='deterministic-hash-768' WHERE id='beta__section_03'")
        c.commit()
        c.close()
        self.assertEqual(_quiet(ee.verify_index_integrity, db, expect_provider="ollama")[0], 4)

    def test_search_falls_back_to_keyword_when_ollama_down(self):
        db = _gemini_index()
        _quiet(ee.cmd_reembed_local, db_path=db, pause=0)
        ee.OLLAMA_EMBED_URL = "http://127.0.0.1:9"  # nothing listens
        try:
            rc, out, err = _quiet(ee.search, "leadership hiring", 1, db)
        finally:
            ee.OLLAMA_EMBED_URL = URL
        self.assertEqual(rc, 0)
        self.assertIn("KEYWORD", err)
        self.assertIn("KEYWORD-HITS", out)


def _resolved_model(home: str, **env) -> str:
    """Import the engine in a clean subprocess (HOME=home, no OLLAMA_EMBED_*)."""
    e = {k: v for k, v in os.environ.items() if not k.startswith("OLLAMA_EMBED_")}
    e.update(HOME=home, WORKSPACE_ROOT=os.path.join(home, "ws"), **env)
    code = ("import importlib.util,sys;sp=importlib.util.spec_from_file_location('e',sys.argv[1]);"
            "m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);"
            "print(m.OLLAMA_EMBED_MODEL, m.OLLAMA_EMBED_DIM)")
    return subprocess.run([sys.executable, "-c", code, str(SU / "embedding_engine.py")],
                          env=e, capture_output=True, text=True, check=True).stdout.strip()


class TestModelOverride(unittest.TestCase):
    def test_default_and_env_and_secrets_file(self):
        home = tempfile.mkdtemp()
        self.assertEqual(_resolved_model(home), f"{GEMMA} 768")
        self.assertEqual(_resolved_model(home, OLLAMA_EMBED_MODEL=OTHER, OLLAMA_EMBED_DIM="768"),
                         f"{OTHER} 768")
        os.makedirs(os.path.join(home, ".openclaw", "secrets"))
        Path(home, ".openclaw", "secrets", ".env").write_text(
            f"OTHER=x\nOLLAMA_EMBED_MODEL={OTHER}\nOLLAMA_EMBED_DIM=768\n")
        self.assertEqual(_resolved_model(home), f"{OTHER} 768")

    def test_invalid_dim_falls_back_to_768(self):
        home = tempfile.mkdtemp()
        for bad in ("abc", "0", "-5"):
            self.assertEqual(_resolved_model(home, OLLAMA_EMBED_DIM=bad), f"{GEMMA} 768")

    def test_gemma_stamps_and_prefixes(self):
        db = _gemini_index()
        rc, out, err = _quiet(ee.cmd_reembed_local, db_path=db, pause=0)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(_Stub.last["model"], GEMMA)
        self.assertTrue(_Stub.last["input"].startswith("title: none | text: "))
        rc, out, err = _quiet(ee.search, "negotiation pricing objections", 1, db)
        self.assertIn("PERSONA: alpha", out)
        self.assertEqual(_Stub.last["input"],
                         "task: search result | query: negotiation pricing objections")

    def test_override_stamps_verifies_and_rejects_mismatch(self):
        db = _gemini_index()
        old = ee.OLLAMA_EMBED_MODEL
        ee.OLLAMA_EMBED_MODEL = OTHER
        try:
            rc, out, err = _quiet(ee.cmd_reembed_local, db_path=db, pause=0)
            self.assertEqual(rc, 0, out + err)
            self.assertEqual(_Stub.last, {"model": OTHER, "input": _Stub.last["input"]})
            self.assertFalse(_Stub.last["input"].startswith("title:"))  # no gemma prefix
            c = sqlite3.connect(db)
            stamps = set(c.execute("SELECT provider, model, dim FROM embeddings").fetchall())
            c.close()
            self.assertEqual(stamps, {("ollama", OTHER, 768)})
            self.assertEqual(_quiet(ee.verify_index_integrity, db, expect_provider="ollama")[0], 0)
        finally:
            ee.OLLAMA_EMBED_MODEL = old
        # default (gemma) contract rejects the other-model index, loudly
        rc, _, err = _quiet(ee.verify_index_integrity, db, expect_provider="ollama")
        self.assertEqual(rc, 4)
        self.assertIn("--reembed-local", err)
        # ...search warns, and still queries with the index's own stamped model.
        rc, out, err = _quiet(ee.search, "negotiation pricing objections", 1, db)
        self.assertIn("PERSONA: alpha", out)
        self.assertIn("Re-embed with --reembed-local", err)
        self.assertEqual(_Stub.last["model"], OTHER)

    def test_mixed_model_index_fails_verify_and_keyword_search(self):
        db = _gemini_index()
        _quiet(ee.cmd_reembed_local, db_path=db, pause=0)  # all gemma
        c = sqlite3.connect(db)
        c.execute("UPDATE embeddings SET model=? WHERE id='beta__section_03'", (OTHER,))
        c.commit()
        c.close()
        rc, _, err = _quiet(ee.verify_index_integrity, db, expect_provider="ollama")
        self.assertEqual(rc, 4)
        self.assertIn("1/3 row(s)", err)
        self.assertIn("--reembed-local", err)
        rc, out, err = _quiet(ee.search, "negotiation pricing", 1, db)
        self.assertIn("KEYWORD", err)  # never cross-model cosine
        # resume converts only the stray row, then verify passes
        rc, out, _ = _quiet(ee.cmd_reembed_local, db_path=db, pause=0)
        self.assertEqual(rc, 0)
        self.assertIn("1 row(s) to embed", out)


class TestProvisioningGuards(unittest.TestCase):
    def test_sop_provision_skips_local_mode_db(self):
        db = _tmp(".db")
        c = sqlite3.connect(db)
        c.executescript("""
            CREATE TABLE sops (id TEXT PRIMARY KEY, slug TEXT, deleted_at TEXT);
            CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB, embedding_model TEXT,
                                         embedding_dims INTEGER, embedded_at TEXT);
            CREATE TABLE sop_embeddings_local_provider (id INTEGER PRIMARY KEY CHECK (id = 1),
                provider TEXT NOT NULL, model TEXT NOT NULL, dims INTEGER NOT NULL, updated_at TEXT);
            INSERT INTO sops VALUES ('sop_a', 'a', NULL);
            INSERT INTO sop_embeddings VALUES ('sop_a', x'00', 'embeddinggemma-2:740m', 768, 'now');
            INSERT INTO sop_embeddings_local_provider VALUES (1, 'ollama', 'embeddinggemma-2:740m', 768, 'now');
        """)
        c.commit()
        c.close()
        manifest = _tmp(".json")
        Path(manifest).write_text(json.dumps({
            "model": "gemini-embedding-2", "dims": 3072, "sop_count": 1, "release_tag": "sop-embeddings-v9",
            "asset_url": "file:///nonexistent.gz", "sha256": "x", "asset_rebuild_required": False}))
        r = pse.provision_sop_embeddings(manifest, db, dry_run=False)
        self.assertEqual(r["status"], "SKIP", r)
        self.assertIn("local embedding mode", r["reason"])
        c = sqlite3.connect(db)
        self.assertEqual(c.execute("SELECT embedding_model FROM sop_embeddings").fetchone()[0], GEMMA)
        c.close()

    def test_persona_provision_keeps_local_index(self):
        d = Path(tempfile.mkdtemp())
        db = _gemini_index()
        _quiet(ee.cmd_reembed_local, db_path=db, pause=0)
        shutil.copy(db, d / "gemini-index.sqlite")
        manifest = SU / "prebuilt-index" / "INDEX-MANIFEST.json"
        p = subprocess.run(
            ["bash", "-c", f'source "{SU}/provision-persona-index.sh"; provision_persona_index "{manifest}" "{d}"'],
            capture_output=True, text=True, env={**os.environ, "PROVISION_DRY_RUN": "1"}, timeout=60)
        self.assertIn("local Ollama mode", p.stdout, p.stdout + p.stderr)
        self.assertNotIn("would download", p.stdout)


class TestHealth(unittest.TestCase):
    def test_persona_local_mode_passes_on_loopback(self):
        root = Path(tempfile.mkdtemp())
        idx = root / "workspace" / "data" / "coaching-personas"
        idx.mkdir(parents=True)
        db = _gemini_index()
        _quiet(ee.cmd_reembed_local, db_path=db, pause=0)
        shutil.copy(db, idx / "gemini-index.sqlite")
        res = eh.check_persona_gemini_index(root, {}, None)
        self.assertTrue(res["pass"], res)
        os.environ["OLLAMA_EMBED_URL"] = "https://ollama.com"
        try:
            res = eh.check_persona_gemini_index(root, {}, None)
        finally:
            os.environ["OLLAMA_EMBED_URL"] = URL
        self.assertFalse(res["pass"])
        self.assertFalse(res["leg_c_generative_not_embedding"])

    def test_cc_sop_local_mode_uses_marker_model(self):
        cc = Path(tempfile.mkdtemp())
        c = sqlite3.connect(cc / "mission-control.db")
        c.executescript("""
            CREATE TABLE sops (id TEXT PRIMARY KEY);
            CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding_model TEXT, embedding_dims INTEGER);
            CREATE TABLE sop_embeddings_local_provider (id INTEGER PRIMARY KEY, provider TEXT, model TEXT, dims INTEGER);
            INSERT INTO sops VALUES ('a'); INSERT INTO sops VALUES ('b');
            INSERT INTO sop_embeddings VALUES ('a', 'embeddinggemma-2:740m', 768);
            INSERT INTO sop_embeddings VALUES ('b', 'embeddinggemma-2:740m', 768);
            INSERT INTO sop_embeddings_local_provider VALUES (1, 'ollama', 'embeddinggemma-2:740m', 768);
        """)
        c.commit()
        c.close()
        res = eh.check_cc_sop_index(cc, {}, None, expected_sop_count=2)
        self.assertTrue(res["leg_a_smoke"], res)
        self.assertTrue(res["pass"], res)
        self.assertIn("local ollama", res["name"])


if __name__ == "__main__":
    unittest.main()
