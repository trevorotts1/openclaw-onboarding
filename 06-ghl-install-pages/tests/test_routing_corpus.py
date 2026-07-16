"""MOCK-only unit tests — U23/B-U9 decision-engine hardening, gap (3):
committed routing regression corpus.

These tests are MOCK-ONLY. There is NO live GoHighLevel, NO Vercel deploy,
NO network of any kind. Every entry in ``tests/fixtures/routing_corpus.json``
is fed straight into ``ghl_method.classify_page`` (a pure function) and the
resulting method/widgets are asserted against the entry's declared
expectation.

Coverage:
  * Every corpus entry's classify_page(...).method matches its
    expected_method (100% pass on the committed corpus).
  * Every corpus entry's detected widget kinds match its
    expected_widget_kinds (order-sensitive — form-then-calendar).
  * The corpus itself is well-formed (non-empty, every entry has the
    required keys, ~20+ entries as the spec calls for).
  * scripts/guard-ghl-method-decision.sh --corpus (the CI guard) exits 0
    against the real, unmodified corpus.
  * scripts/guard-ghl-method-decision.sh --corpus FAILS (non-zero exit) on
    a SEEDED regression — a corpus copy with one entry's expected_method
    flipped to the wrong value. This is BINARY acceptance (c) from B-U9:
    "the guard fails on a seeded corpus regression".

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_routing_corpus.py -v
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SKILL_DIR = os.path.normpath(os.path.join(_TESTS_DIR, ".."))
_TOOLS_DIR = os.path.join(_SKILL_DIR, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_method as m

CORPUS_PATH = os.path.join(_TESTS_DIR, "fixtures", "routing_corpus.json")
GUARD_SCRIPT = os.path.join(_SKILL_DIR, "scripts", "guard-ghl-method-decision.sh")


def _load_corpus() -> dict:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _materialize_entry_spec(entry: dict) -> dict:
    """Return a real page_spec for ``entry``, expanding the ``html_repeat``
    synthetic key (used for the over-max-bytes fixture so the corpus JSON
    doesn't have to embed a literal 270KB blob) into a real ``html`` field."""
    spec = copy.deepcopy(entry["page_spec"])
    repeat = spec.pop("html_repeat", None)
    if repeat is not None:
        unit = repeat["unit"]
        min_bytes = repeat["min_bytes"]
        reps = (min_bytes // len(unit.encode("utf-8"))) + 1
        spec["html"] = unit * reps
    return spec


def _method_val(decision) -> str:
    meth = decision.method
    return meth.value if hasattr(meth, "value") else str(meth)


# ── Corpus well-formedness ─────────────────────────────────────────────────────

class TestCorpusWellFormed:
    def test_corpus_file_exists_and_parses(self):
        corpus = _load_corpus()
        assert isinstance(corpus, dict)
        assert "entries" in corpus

    def test_corpus_has_at_least_twenty_entries(self):
        corpus = _load_corpus()
        assert len(corpus["entries"]) >= 20, (
            f"routing corpus must have ~20 entries per B-U9; got "
            f"{len(corpus['entries'])}"
        )

    def test_every_entry_has_required_keys(self):
        corpus = _load_corpus()
        for entry in corpus["entries"]:
            for key in ("name", "page_spec", "expected_method"):
                assert key in entry, f"corpus entry missing {key!r}: {entry}"

    def test_every_entry_name_is_unique(self):
        corpus = _load_corpus()
        names = [e["name"] for e in corpus["entries"]]
        assert len(names) == len(set(names)), "corpus entry names must be unique"

    def test_every_expected_method_is_valid(self):
        corpus = _load_corpus()
        valid = {m.PageMethod.DIRECT.value, m.PageMethod.VERCEL_EMBED.value}
        for entry in corpus["entries"]:
            assert entry["expected_method"] in valid, (
                f"{entry['name']}: expected_method {entry['expected_method']!r} "
                f"not in {valid}"
            )

    def test_corpus_covers_both_methods(self):
        """The corpus must actually exercise both DIRECT and VERCEL_EMBED —
        a corpus that is all-one-method would never catch a regression."""
        corpus = _load_corpus()
        methods = {e["expected_method"] for e in corpus["entries"]}
        assert methods == {"direct", "vercel_embed"}


# ── Every corpus entry classifies as expected ──────────────────────────────────

class TestCorpusEntriesClassifyCorrectly:
    @pytest.fixture(params=_load_corpus()["entries"], ids=lambda e: e["name"])
    def entry(self, request):
        return request.param

    def test_entry_method_matches_expected(self, entry):
        spec = _materialize_entry_spec(entry)
        decision = m.classify_page(spec)
        assert _method_val(decision) == entry["expected_method"], (
            f"{entry['name']}: expected {entry['expected_method']!r}, "
            f"got {_method_val(decision)!r} (score={decision.score}, "
            f"signals={decision.signals})"
        )

    def test_entry_widget_kinds_match_expected(self, entry):
        spec = _materialize_entry_spec(entry)
        decision = m.classify_page(spec)
        actual_kinds = [w.kind.value for w in decision.widgets]
        assert actual_kinds == entry.get("expected_widget_kinds", []), (
            f"{entry['name']}: expected widget kinds "
            f"{entry.get('expected_widget_kinds', [])!r}, got {actual_kinds!r}"
        )


# ── guard-ghl-method-decision.sh --corpus (the CI guard) ──────────────────────

class TestGuardCorpusMode:
    def test_guard_script_exists_and_is_executable(self):
        assert os.path.isfile(GUARD_SCRIPT)
        assert os.access(GUARD_SCRIPT, os.X_OK)

    def test_guard_passes_on_real_unmodified_corpus(self):
        result = subprocess.run(
            ["bash", GUARD_SCRIPT, "--corpus", CORPUS_PATH],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"guard --corpus must PASS on the real corpus.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_guard_fails_on_seeded_regression_wrong_expected_method(self, tmp_path):
        """BINARY acceptance (c): 'the guard fails on a seeded corpus
        regression.' Flip one entry's expected_method to the wrong value and
        confirm the guard catches it."""
        corpus = _load_corpus()
        broken = copy.deepcopy(corpus)
        target = broken["entries"][0]
        assert target["expected_method"] == "direct", (
            "test assumes entries[0] is a 'direct' fixture — update if the "
            "corpus ordering changes"
        )
        target["expected_method"] = "vercel_embed"  # seeded WRONG value

        broken_path = tmp_path / "routing_corpus.broken.json"
        broken_path.write_text(json.dumps(broken, indent=2))

        result = subprocess.run(
            ["bash", GUARD_SCRIPT, "--corpus", str(broken_path)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            "guard --corpus must FAIL (non-zero exit) on a seeded regression"
        )
        assert target["name"] in result.stdout

    def test_guard_fails_on_seeded_regression_wrong_widget_kind(self, tmp_path):
        corpus = _load_corpus()
        broken = copy.deepcopy(corpus)
        target = next(
            e for e in broken["entries"] if e.get("expected_widget_kinds")
        )
        target["expected_widget_kinds"] = ["booking"]  # seeded WRONG value

        broken_path = tmp_path / "routing_corpus.broken_widget.json"
        broken_path.write_text(json.dumps(broken, indent=2))

        result = subprocess.run(
            ["bash", GUARD_SCRIPT, "--corpus", str(broken_path)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_guard_fails_on_missing_corpus_file(self, tmp_path):
        result = subprocess.run(
            ["bash", GUARD_SCRIPT, "--corpus", str(tmp_path / "nope.json")],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
