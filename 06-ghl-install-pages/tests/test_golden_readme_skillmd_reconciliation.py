"""MOCK-only doc-reconciliation test — U23/B-U9 decision-engine hardening,
gap (5): the golden-README / SKILL.md drift on whether new_page_blob() is
pure or golden-loading.

B-U9's acceptance (e): "the golden-README/SKILL.md drift is reconciled to
one statement (diff shows exactly one doc changed)."

VERIFIED GROUND TRUTH (read directly from tools/ghl_rest_canvas.py, not
assumed): ``new_page_blob()`` assembles its blob from the inlined
``_FLAT_*``/``_CC_*`` module-level constants; ``_load_golden(surface)`` is a
SEPARATE function that CAN read ``references/golden/*.json`` from disk on
demand but is never called by ``new_page_blob()`` or anywhere else in the
production build path. ``SKILL.md``'s Phase-5 section already stated this
correctly ("pure, self-contained function... does NOT load from
references/golden/ at build time"); ``references/golden/README.md``
previously contradicted it ("new_page_blob() loads funnel-optin.page-data.json
as the structural template") -- STALE. This test proves the contradiction is
gone and both docs now agree, without re-writing SKILL.md (only the README
changed -- SKILL.md is untouched by this unit, matching the "exactly one doc
changed" acceptance).

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_golden_readme_skillmd_reconciliation.py -v
"""
from __future__ import annotations

import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SKILL_DIR = os.path.normpath(os.path.join(_TESTS_DIR, ".."))
_TOOLS_DIR = os.path.join(_SKILL_DIR, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

README_PATH = os.path.join(_SKILL_DIR, "references", "golden", "README.md")
SKILL_MD_PATH = os.path.join(_SKILL_DIR, "SKILL.md")
GHL_REST_CANVAS_PATH = os.path.join(_TOOLS_DIR, "ghl_rest_canvas.py")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestGroundTruthInCode:
    """Re-derive the ground truth from the actual code, not from either doc
    -- the judge/reviewer must never trust either document on its own word."""

    def test_new_page_blob_docstring_states_it_is_pure(self):
        src = _read(GHL_REST_CANVAS_PATH)
        idx = src.find("def new_page_blob(")
        assert idx != -1, "new_page_blob not found in ghl_rest_canvas.py"
        end = src.find("\ndef ", idx + 1)
        docstring_window = src[idx:end if end != -1 else idx + 8000]
        assert "NOT loaded from a golden file" in docstring_window

    def test_load_golden_is_a_separate_unused_by_new_page_blob_function(self):
        src = _read(GHL_REST_CANVAS_PATH)
        assert "def _load_golden(surface: str) -> dict:" in src
        # new_page_blob's own body never calls _load_golden -- the docstring
        # says so explicitly ("_load_golden is a separate function").
        idx = src.find("def new_page_blob(")
        end = src.find("\ndef ", idx + 1)
        body = src[idx:end if end != -1 else len(src)]
        assert "_load_golden(" not in body, (
            "new_page_blob's body must never call _load_golden -- it is a "
            "pure function assembled from inlined _FLAT_* constants"
        )

    def test_flat_theme_colors_constant_is_inlined_not_loaded(self):
        src = _read(GHL_REST_CANVAS_PATH)
        assert "_FLAT_THEME_COLORS = [" in src


class TestReadmeNoLongerContradicts:
    def test_readme_exists(self):
        assert os.path.isfile(README_PATH)

    def test_readme_no_longer_claims_new_page_blob_loads_the_golden_file(self):
        text = _read(README_PATH)
        stale_claim = (
            "new_page_blob() loads funnel-optin.page-data.json as the "
            "structural template"
        )
        assert stale_claim not in text, (
            "references/golden/README.md still carries the STALE claim that "
            "contradicted SKILL.md's Phase-5 doctrine"
        )

    def test_readme_now_states_new_page_blob_is_pure(self):
        text = _read(README_PATH)
        assert "does NOT load these files at build time" in text
        assert "pure" in text.lower()

    def test_readme_mentions_load_golden_as_a_separate_helper(self):
        text = _read(README_PATH)
        assert "_load_golden" in text


class TestSkillMdUnchangedAndConsistent:
    """SKILL.md already stated the correct doctrine before this unit ran --
    this unit changes ONLY the README (the stale doc), never SKILL.md."""

    def test_skill_md_still_states_pure_self_contained(self):
        text = _read(SKILL_MD_PATH)
        assert "pure, self-contained" in text
        assert "does NOT load from" in text
        assert "references/golden/" in text

    def test_both_docs_now_agree_on_the_core_claim(self):
        readme_text = _read(README_PATH)
        skill_text = _read(SKILL_MD_PATH)
        # Both docs must assert the SAME fact: new_page_blob does not load
        # references/golden/ at build time.
        assert "does not load" in readme_text.lower()
        assert "does not load" in skill_text.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
