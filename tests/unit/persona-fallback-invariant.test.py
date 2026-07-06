#!/usr/bin/env python3
"""
Contract test for FDN-1 / F3.1 — the "no naked task" persona invariant in
23-ai-workforce-blueprint/scripts/persona-selector-v2.py.

Proves, by exercising the selector directly (hermetic — no DB, no network):

  1. EMPTY UNIVERSE (A1): select_persona() on an empty persona library NEVER
     returns persona_id:null. It attaches the resolved default fallback persona,
     tags it fallback:"default_persona", and KEEPS the NO_PERSONAS_AVAILABLE
     warning (degraded state stays loud).
  2. DEFAULT RESOLUTION ORDER (Q2): company-config.default_persona_id (client
     override) wins; else the first REAL seed key (deterministic); else the
     pinned DEFAULT_PERSONA_FALLBACK constant. Never None.
  3. GOVERNANCE RESOLUTION ORDER (Q1): company-config.governance_persona_id
     wins; else the pinned GOVERNANCE_PERSONA_FALLBACK constant. Never None.
  4. FUNNEL EXCLUSION: list_available_personas() drops fallback:true personas so
     the generic house voice can never enter normal scoring competition.
  5. PINS: the two constants are exactly the FDN-1 ids.

Run:
    python3 tests/unit/persona-fallback-invariant.test.py
    or: pytest tests/unit/persona-fallback-invariant.test.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent            # tests/unit/
_REPO_ROOT = _HERE.parent.parent         # repo root
_SCRIPTS = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"
assert _SCRIPTS.is_dir(), f"selector scripts dir not found at {_SCRIPTS}"

# Import the hyphenated selector module by path, with its sibling helper modules
# (adaptive_weights, llm_score, semantic_task_fit) reachable on sys.path.
sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location(
    "persona_selector_v2", _SCRIPTS / "persona-selector-v2.py")
sel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sel)


def _paths(tmp: Path, *, categories: Path | None = None,
           company_config: Path | None = None,
           personas_dir: Path | None = None) -> dict:
    """Build a synthetic `paths` dict pointing at temp files. Missing files are
    simply absent (the selector treats absence as empty), which is exactly the
    A1 empty-universe condition."""
    return {
        "user_md": tmp / "USER.md",                       # absent -> ""
        "persona_categories": categories or (tmp / "no-such-categories.json"),
        "coaching_personas": personas_dir or (tmp / "coaching"),
        "company_config": company_config or (tmp / "no-such-company-config.json"),
        "skills": tmp / "skills",
    }


def _reset_cfg_cache() -> None:
    """load_company_config caches by path in a module global; reset between
    cases so a fresh temp config is actually re-read."""
    sel._COMPANY_CONFIG_CACHE = {"path": None, "data": None, "warned": False}


def _write_categories(path: Path, personas: dict) -> None:
    path.write_text(json.dumps({
        "schemaVersion": "1.1",
        "domainTags": ["communication", "marketing", "leadership"],
        "perspectiveTags": [],
        "personas": personas,
    }), encoding="utf-8")


class PersonaFallbackInvariant(unittest.TestCase):

    # ── 5. pins ───────────────────────────────────────────────────────────
    def test_pins_are_the_fdn1_ids(self):
        self.assertEqual(sel.DEFAULT_PERSONA_FALLBACK, "blackceo-house-voice")
        self.assertEqual(sel.GOVERNANCE_PERSONA_FALLBACK, "covey-7-habits")

    # ── 1. empty universe never naked ─────────────────────────────────────
    def test_empty_universe_select_is_never_naked(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _reset_cfg_cache()
            paths = _paths(tmp)  # no categories file, no personas dir
            out = sel.select_persona(
                task="write a launch email for a new coaching offer",
                department="marketing", mode="leadership",
                weights=sel.DEFAULT_WEIGHTS, paths=paths,
                db_path=tmp / "nope.db", variety=False)
            self.assertIsNotNone(out.get("persona_id"),
                                 "SELECT mode emitted a naked persona_id:null")
            self.assertEqual(out["persona_id"], "blackceo-house-voice")
            self.assertEqual(out.get("fallback"), "default_persona")
            # degraded state must stay loud
            self.assertEqual(out.get("warning"), "NO_PERSONAS_AVAILABLE")

    # ── 2. default resolution order ───────────────────────────────────────
    def test_default_resolution_falls_to_constant(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _reset_cfg_cache()
            pid, src = sel._resolve_default_persona_id(_paths(tmp), available=[])
            self.assertEqual(pid, "blackceo-house-voice")
            self.assertEqual(src, "default_persona")

    def test_default_resolution_prefers_first_real_seed(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _reset_cfg_cache()
            # house-voice present but must NOT be chosen over a real persona;
            # deterministic = sorted-first of the real ids.
            avail = ["zzz-last", "aaa-first", "blackceo-house-voice"]
            pid, src = sel._resolve_default_persona_id(_paths(tmp), available=avail)
            self.assertEqual(pid, "aaa-first")
            self.assertEqual(src, "first_seed_category")

    def test_default_resolution_client_override_wins(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = tmp / "company-config.json"
            cfg.write_text(json.dumps({"default_persona_id": "client-pick"}),
                           encoding="utf-8")
            _reset_cfg_cache()
            paths = _paths(tmp, company_config=cfg)
            # a full real library is available, but the client override still wins
            pid, src = sel._resolve_default_persona_id(
                paths, available=["aaa-first", "blackceo-house-voice"])
            self.assertEqual(pid, "client-pick")
            self.assertEqual(src, "company_config")

    # ── 3. governance resolution order ────────────────────────────────────
    def test_governance_resolution_falls_to_constant(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _reset_cfg_cache()
            pid, src = sel._resolve_governance_persona_id(_paths(tmp))
            self.assertEqual(pid, "covey-7-habits")
            self.assertEqual(src, "governance_default")

    def test_governance_resolution_client_override_wins(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = tmp / "company-config.json"
            cfg.write_text(json.dumps({"governance_persona_id": "client-gov"}),
                           encoding="utf-8")
            _reset_cfg_cache()
            pid, src = sel._resolve_governance_persona_id(
                _paths(tmp, company_config=cfg))
            self.assertEqual(pid, "client-gov")
            self.assertEqual(src, "company_config")

    # ── 4. funnel exclusion of fallback:true ──────────────────────────────
    def test_list_available_excludes_fallback_personas(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cats = tmp / "persona-categories.json"
            _write_categories(cats, {
                "real-one": {"domain": ["marketing"]},
                "blackceo-house-voice": {"domain": ["communication"],
                                         "fallback": True},
            })
            avail = sel.list_available_personas(_paths(tmp, categories=cats))
            self.assertIn("real-one", avail)
            self.assertNotIn("blackceo-house-voice", avail,
                             "fallback:true persona leaked into the funnel pool")


if __name__ == "__main__":
    unittest.main(verbosity=2)
