"""test_automation_matcher.py — pytest coverage for the Skill-44 automation matcher.

Closes the audit gap: matcher flexibility + the funnel->automation expansion were tested
ONLY by `_matcher/cli.py --selftest`, which asserted a plan EXISTS rather than that the
CORRECT per-variant plan was built — which is exactly why the soap-opera id-collision
slipped through. These pytest cases run under CI/QC and lock down:

  * flex intent-mode detection + the four decisions (HONOR_USER / SUGGEST / USE / CREATE_NEW),
  * the flexibility invariants (never imposes, always overridable, never blocks),
  * COLLISION-SAFE Catalog.get() (two templates share the bare id 'soap-opera-sequence'),
  * PER-VARIANT correctness: expanding follow-up-funnel builds the SALES-CLOSE soap-opera,
    NOT the welcome-indoctrination variant (the proven cross-wiring bug, now regression-locked),
  * committed catalog-index.json is PORTABLE (no operator-local paths) and round-trips,
  * step0_match writes the match-decision receipt the QC gate reads.

No network.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_MATCHER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "automation-templates", "_matcher"))
_LINKS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "automation-templates", "_links"))
_CATALOG_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "automation-templates"))
if _MATCHER_DIR not in sys.path:
    sys.path.insert(0, _MATCHER_DIR)

import automation_matcher as am  # noqa: E402
import flex  # noqa: E402

_INDEX_PATH = os.path.join(_MATCHER_DIR, "catalog-index.json")
_LINK_MAP = os.path.join(_LINKS_DIR, "funnel-to-automation.json")


@pytest.fixture(scope="module")
def catalog() -> am.Catalog:
    return am.Catalog.load(_CATALOG_ROOT)


# ── flex intent-mode + decision matrix (the shared core) ─────────────────────
def test_flex_mode_detection():
    assert flex.detect_mode("just build the whole thing, you handle it")["mode"] == flex.MODE_HANDSOFF
    assert flex.detect_mode("not sure — what do you recommend?")["mode"] == flex.MODE_UNSURE
    assert flex.detect_mode("use my exact 3 emails, do not change them")["mode"] == flex.MODE_EXPLICIT
    assert flex.detect_mode({"text": "set it up", "steps": ["a", "b"]})["mode"] == flex.MODE_EXPLICIT


def test_flex_decision_matrix_and_invariants():
    assert flex.decide(flex.MODE_HANDSOFF, has_confident_match=True)["decision"] == flex.DEC_USE
    assert flex.decide(flex.MODE_HANDSOFF, has_confident_match=False)["decision"] == flex.DEC_CREATE_NEW
    assert flex.decide(flex.MODE_UNSURE, has_confident_match=True)["decision"] == flex.DEC_SUGGEST
    assert flex.decide(flex.MODE_UNSURE, has_confident_match=False)["decision"] == flex.DEC_CREATE_NEW
    assert flex.decide(flex.MODE_EXPLICIT, has_confident_match=True)["decision"] == flex.DEC_HONOR_USER
    for mode in flex.MODES:
        for hc in (True, False):
            d = flex.decide(mode, has_confident_match=hc)
            assert d["imposes_on_user"] is False and d["override_allowed"] is True


def test_automation_matcher_imports_shared_flex():
    # The matcher must use the SHARED flex core (DRY), not a private copy.
    assert am.flex is flex


# ── catalog integrity + collision safety ─────────────────────────────────────
def test_catalog_loads_28(catalog):
    assert len(catalog.templates) == 28


def test_soap_opera_id_is_ambiguous(catalog):
    # The exact condition that caused the cross-wiring bug.
    assert "soap-opera-sequence" in catalog.ambiguous_ids
    assert catalog.get("soap-opera-sequence") is None  # ambiguous, no group -> refuse to guess


def test_collision_safe_get_returns_correct_variant(catalog):
    sales = catalog.get("soap-opera-sequence", group="sales-close-sequences")
    welcome = catalog.get("soap-opera-sequence", group="welcome-indoctrination")
    assert sales is not None and welcome is not None
    assert sales is not welcome
    assert "sales-close-sequences" in sales["sourcePath"]
    assert "welcome-indoctrination" in welcome["sourcePath"]


# ── PER-VARIANT correctness: the regression lock for the proven bug ──────────
def test_followup_funnel_expands_to_sales_close_soap_opera(catalog):
    res = am.expand_funnel_to_automations(
        "follow-up-funnel", link_map_path=_LINK_MAP, catalog=catalog,
        intent_mode=flex.MODE_HANDSOFF)
    assert res["found"] is True
    soap = next(a for a in res["automations"] if a["automation_id"] == "soap-opera-sequence")
    assert soap["category"] == "sales-close-sequences"
    plan = soap["workflow_plan"]
    assert plan is not None
    # The build plan MUST come from the sales-close variant, never the welcome one.
    assert "sales-close-sequences/soap-opera-sequence.json" in plan["source_ref"]
    assert "welcome-indoctrination" not in plan["source_ref"]


def test_all_38_funnels_expand_to_correct_variant(catalog):
    data = json.load(open(_LINK_MAP, encoding="utf-8"))
    for link in data["links"]:
        res = am.expand_funnel_to_automations(
            link["funnel_template_id"], link_map_path=_LINK_MAP, catalog=catalog,
            intent_mode=flex.MODE_HANDSOFF)
        for a in res["automations"]:
            plan = a.get("workflow_plan")
            if plan is not None:
                # the plan's source_ref must live under the ref's declared category
                assert f"{a['category']}/{a['automation_id']}.json" in plan["source_ref"], (
                    f"{link['funnel_template_id']}: {a['automation_id']} resolved to the "
                    f"wrong variant -> {plan['source_ref']}")


# ── match_automation end-to-end decisions ────────────────────────────────────
def test_match_explicit_is_honored(catalog):
    d = am.match_automation(
        {"text": "scarcity deadline close but use my exact emails", "spec": "my copy"}, catalog)
    assert d["intent_mode"] == flex.MODE_EXPLICIT
    assert d["decision"] == flex.DEC_HONOR_USER
    assert d["imposes_on_user"] is False


def test_match_hands_off_uses_template(catalog):
    d = am.match_automation(
        {"text": "a re-engagement winback campaign for cold subscribers, just do it all"}, catalog)
    assert d["intent_mode"] == flex.MODE_HANDSOFF
    assert d["decision"] == flex.DEC_USE
    assert d["matched_template"] is not None
    assert d["matched_template_key"] is not None
    assert d["workflow_plan"] is not None


def test_match_nothing_fits_creates_new(catalog):
    d = am.match_automation(
        {"text": "a sourdough bread recipe blog about hydration, just do it"}, catalog)
    assert d["decision"] == flex.DEC_CREATE_NEW
    assert d["matched_template"] is None


# ── committed index portability ──────────────────────────────────────────────
def test_committed_index_is_portable():
    assert os.path.isfile(_INDEX_PATH)
    raw = open(_INDEX_PATH, encoding="utf-8").read()
    for leak in ("/Users/", "/private/tmp", "scratchpad", "blackceomacmini"):
        assert leak not in raw, f"operator-local path leaked into committed index: {leak}"
    idx = json.loads(raw)
    assert not os.path.isabs(idx["root"])
    for t in idx["templates"]:
        assert not os.path.isabs(t["sourcePath"])


def test_index_round_trips(catalog):
    cat = am.Catalog.from_index(_INDEX_PATH)
    assert len(cat.templates) == 28
    sp = cat.templates[0]["sourcePath"]
    assert os.path.isabs(sp) and os.path.isfile(sp)


# ── deprecated v1 link map must not drift in coverage vs the canonical v2 ────
def test_v1_link_map_is_marked_deprecated():
    v1 = json.load(open(os.path.join(_LINKS_DIR, "funnel-to-automation-link-map.json"),
                        encoding="utf-8"))
    assert v1["_meta"].get("deprecated") is True
    assert v1["_meta"].get("superseded_by") == "funnel-to-automation.json"


def test_v1_v2_link_maps_cover_same_funnels():
    v1 = json.load(open(os.path.join(_LINKS_DIR, "funnel-to-automation-link-map.json"),
                        encoding="utf-8"))
    v2 = json.load(open(_LINK_MAP, encoding="utf-8"))
    v1_ids = {fid for cat, entries in v1.items() if cat != "_meta"
              for fid in entries.keys()}
    v2_ids = {link["funnel_template_id"] for link in v2["links"]}
    assert v1_ids == v2_ids, (
        f"deprecated v1 link map drifted from canonical v2: "
        f"only-v1={v1_ids - v2_ids} only-v2={v2_ids - v1_ids}")
    assert len(v2_ids) == 38


# ── step0 writes the QC match-decision receipt ───────────────────────────────
def test_step0_writes_match_decision_receipt(tmp_path):
    task = {"brief": "a re-engagement winback campaign, just do it all"}
    am.step0_match(task, str(tmp_path), index_path=_INDEX_PATH)
    receipt = tmp_path / "routing" / "match-decision.json"
    assert receipt.is_file()
    rec = json.loads(receipt.read_text())
    assert rec["skill"] == "44-convert-and-flow-operator"
    assert "flex_decision" in rec
