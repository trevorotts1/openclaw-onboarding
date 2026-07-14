"""test_funnel_matcher.py — pytest coverage for the Skill-6 funnel matcher.

Closes the audit gap: matcher flexibility was previously tested ONLY by the ad-hoc
`funnel_matcher_cli.py --selftest`, which never ran under CI and asserted only that a
plan EXISTS (not that the correct per-variant plan was built). These tests run under the
standing QC gate and lock down:

  * the four flexibility decisions per intent mode
    (HONOR_USER / SUGGEST_TEMPLATE / USE_TEMPLATE / CREATE_NEW),
  * the flexibility invariants (imposes_on_user is always False, override always allowed,
    never blocks a build),
  * the collision-safe Catalog.get() (qualified group/id, refuses to guess ambiguous ids),
  * the committed catalog-index.json round-trips PORTABLY (no operator-local paths),
  * step0_match stamps task['funnel_template_id'] so it survives the P4->P5 handoff.

No network, no browser.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import funnel_matcher as fm  # noqa: E402

_CATALOG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "funnel-templates"))
_INDEX_PATH = os.path.join(_TOOLS_DIR, "catalog-index.json")


@pytest.fixture(scope="module")
def catalog() -> fm.Catalog:
    return fm.Catalog.load(_CATALOG_ROOT)


def flex_dec(mode: str, confident: bool) -> str:
    return fm.flex_decide(mode, has_confident_match=confident, has_any_match=True)["decision"]


# ── catalog integrity ────────────────────────────────────────────────────────
def test_catalog_loads_all_38(catalog):
    assert len(catalog.templates) == 38
    assert set(catalog.by_key.keys()) == {f"{t['group']}/{t['id']}" for t in catalog.templates}


def test_catalog_get_is_collision_safe(catalog):
    # Every id is currently unique, so bare-id get() resolves.
    sample = catalog.templates[0]
    assert catalog.get(sample["id"]) is sample
    assert catalog.get(sample["id"], group=sample["group"]) is sample
    # Unknown id -> None, never an exception.
    assert catalog.get("definitely-not-a-funnel") is None


def test_catalog_get_refuses_to_guess_ambiguous():
    # Synthesise a duplicate bare id across two groups and prove get() refuses to guess.
    t1 = {"id": "dup", "group": "buyer", "name": "A"}
    t2 = {"id": "dup", "group": "lead", "name": "B"}
    cat = fm.Catalog("/x", [t1, t2], {})
    assert "dup" in cat.ambiguous_ids
    assert cat.get("dup") is None                      # ambiguous, no group -> refuse
    assert cat.get("dup", group="lead") is t2          # qualified -> correct variant
    assert cat.get("dup", group="buyer") is t1


# ── the four flexibility decisions ───────────────────────────────────────────
def test_explicit_named_funnel_is_honored(catalog):
    # Naming a funnel forces EXPLICIT -> HONOR_USER (template never imposed).
    d = fm.match_funnel({"text": "build a survey quiz funnel that segments my list"}, catalog)
    assert d["intent_mode"] == fm.MODE_EXPLICIT
    assert d["decision"] == fm.DEC_HONOR_USER
    assert d["imposes_on_user"] is False
    assert d["override_allowed"] is True


def test_decision_matrix_is_the_flexibility_contract():
    # (mode, has_confident_match) -> decision. This is the deterministic core contract;
    # match_funnel routes to exactly these decisions.
    assert flex_dec(fm.MODE_HANDSOFF, True) == fm.DEC_USE
    assert flex_dec(fm.MODE_HANDSOFF, False) == fm.DEC_CREATE_NEW
    assert flex_dec(fm.MODE_UNSURE, True) == fm.DEC_SUGGEST
    assert flex_dec(fm.MODE_UNSURE, False) == fm.DEC_CREATE_NEW
    # EXPLICIT always honors the user regardless of match availability.
    assert flex_dec(fm.MODE_EXPLICIT, True) == fm.DEC_HONOR_USER
    assert flex_dec(fm.MODE_EXPLICIT, False) == fm.DEC_HONOR_USER
    # invariants on every cell
    for mode in (fm.MODE_HANDSOFF, fm.MODE_UNSURE, fm.MODE_EXPLICIT):
        for hc in (True, False):
            dec = fm.flex_decide(mode, has_confident_match=hc, has_any_match=True)
            assert dec["imposes_on_user"] is False
            assert dec["override_allowed"] is True


def test_hands_off_unnamed_builds_or_creates(catalog):
    # Hands-off WITHOUT naming a funnel -> HANDS_OFF mode; builds from template or creates.
    d = fm.match_funnel({"text": "just do it all, set it up turnkey for me to grow my list"},
                        catalog)
    assert d["intent_mode"] == fm.MODE_HANDSOFF
    assert d["decision"] in (fm.DEC_USE, fm.DEC_CREATE_NEW)
    if d["decision"] == fm.DEC_USE:
        assert d["pages"] is not None and d["matched_template"] is not None


def test_unsure_suggests_or_creates(catalog):
    d = fm.match_funnel({"text": "not sure what funnel I need, what do you recommend?"},
                        catalog)
    assert d["intent_mode"] == fm.MODE_UNSURE
    assert d["decision"] in (fm.DEC_SUGGEST, fm.DEC_CREATE_NEW)
    assert d["await_confirm"] is True


def test_nothing_fits_creates_new(catalog):
    d = fm.match_funnel({"text": "a sourdough bread recipe blog about hydration ratios"},
                        catalog)
    assert d["decision"] == fm.DEC_CREATE_NEW
    # A weak best-ref may still be carried, but it is below threshold and not built from.
    assert d["confidence"] < d["threshold"]
    assert d["build_from_template"] is False


def test_flex_invariants_hold_across_every_decision(catalog):
    for text in ("just do it all", "what should i pick?", "a quiz that segments my audience",
                 "totally unrelated nonsense topic xyz"):
        d = fm.match_funnel({"text": text}, catalog)
        assert d["imposes_on_user"] is False
        assert d["override_allowed"] is True


# ── committed index portability (no operator-local paths) ────────────────────
def test_committed_index_is_portable():
    assert os.path.isfile(_INDEX_PATH), "catalog-index.json must be committed"
    raw = open(_INDEX_PATH, encoding="utf-8").read()
    for leak in ("/Users/", "/private/tmp", "scratchpad", "blackceomacmini"):
        assert leak not in raw, f"operator-local path leaked into committed index: {leak}"
    idx = json.loads(raw)
    assert not os.path.isabs(idx["root"]), "index root must be relative (portable)"
    for t in idx["templates"]:
        assert not os.path.isabs(t["sourcePath"]), "sourcePath must be relative in committed index"


def test_index_round_trips_and_reabsolutises():
    cat = fm.Catalog.from_index(_INDEX_PATH)
    assert len(cat.templates) == 38
    # After load, sourcePath must point at a real file on THIS box.
    sp = cat.templates[0]["sourcePath"]
    assert os.path.isabs(sp) and os.path.isfile(sp)


# ── step0 stamps funnel identity for the cross-department handoff ────────────
def test_step0_stamps_funnel_template_id(tmp_path):
    task = {"text": "just build the whole survey quiz funnel, handle it all"}
    fm.step0_match(task, str(tmp_path), index_path=_INDEX_PATH,
                   link_map_path=None)
    # An identified funnel must be stamped onto the task so it survives the handoff.
    if task.get("template_match", {}).get("matched_template"):
        assert task.get("funnel_template_id"), "funnel_template_id must be stamped on the task"
    receipt = tmp_path / "routing" / "match-decision.json"
    assert receipt.is_file(), "match-decision.json receipt must be written for the QC gate"


# ── B-U2 / U16: per-page build_blend_directive; template persona demoted to a
# crosswalk-resolved topic hint; copy_persona back-compat ────────────────────

def _synthetic_template(persona_id: str = "funnel-architect",
                        persona_label: str = "Funnel Architect") -> dict:
    return {
        "id": "synthetic-two-step", "group": "synthetic", "name": "Synthetic Two-Step",
        "persona": {"id": persona_id, "label": persona_label, "author": "", "script": "", "detail": ""},
        "pageStructure": [
            {"order": 1, "page": "Optin", "purpose": "capture the lead's email",
             "blocks": ["hero", "form"], "skill44Widgets": []},
            {"order": 2, "page": "Thank You", "purpose": "confirm the booked call",
             "blocks": ["cta"], "skill44Widgets": []},
        ],
        "scripts": "",
    }


_GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"


def test_instantiate_pages_without_bundle_is_legacy_unchanged():
    tmpl = _synthetic_template()
    pages = fm.instantiate_pages(tmpl)
    for p in pages:
        assert p["copy_persona"] == "Funnel Architect"
        assert "blend_directive" not in p
        assert "voice_persona_id" not in p
        assert "topic_persona_id" not in p


def test_instantiate_pages_with_bundle_adds_blend_fields():
    tmpl = _synthetic_template()
    bundle = {
        "voice_persona_id": "hormozi-100m-offers",
        "topic_persona_id": "miller-building-storybrand",
        "audience_id": None, "audience_label": "solo-founder coaches",
        "confirm_required": False, "content_task": True,
        "task_personas": [{"seq": 1, "persona_id": "hormozi-100m-offers"}],
    }
    pages = fm.instantiate_pages(tmpl, bundle=bundle)
    for p in pages:
        assert p["voice_persona_id"] == "hormozi-100m-offers"
        assert p["blend_directive"], "every page must carry a non-empty blend_directive"
        assert _GUARDRAIL_MARK in p["blend_directive"], (
            "every blend_directive must end in the verbatim GUARDRAIL_CLAUSE"
        )
        # copy_persona is UNCHANGED — back-compat topic/craft hint, never the voice.
        assert p["copy_persona"] == "Funnel Architect"


def test_instantiate_pages_crosswalk_resolves_to_canonical_id():
    tmpl = _synthetic_template(persona_id="funnel-architect")
    bundle = {"voice_persona_id": "hormozi-100m-offers", "confirm_required": False}
    pages = fm.instantiate_pages(tmpl, bundle=bundle)
    xwalk = fm._load_crosswalk_once()
    assert xwalk is not None, "persona_crosswalk must be reachable for this test to be meaningful"
    _pcw, canonical, _crosswalk = xwalk
    for p in pages:
        assert p["topic_persona_id"] in canonical, (
            f"page topic_persona_id {p['topic_persona_id']!r} must resolve to a real "
            "persona-categories.json id"
        )
    # 'funnel-architect' is a known slug_map entry -> brunson-marketing-secrets-blackbook.
    assert pages[0]["topic_persona_id"] == "brunson-marketing-secrets-blackbook"


def test_instantiate_pages_two_purposes_distinct_directives_same_voice():
    tmpl = _synthetic_template()
    bundle = {"voice_persona_id": "hormozi-100m-offers", "confirm_required": False}
    pages = fm.instantiate_pages(tmpl, bundle=bundle)
    assert len(pages) == 2
    assert pages[0]["blend_directive"] != pages[1]["blend_directive"], (
        "two pages with different purposes must produce two distinct directives"
    )
    assert pages[0]["voice_persona_id"] == pages[1]["voice_persona_id"], (
        "the VOICE stays the ONE task-level persona across every page"
    )


def test_instantiate_pages_ghl_survey_builder_fixture_bit_identical():
    # ghl_survey_builder reads task['copy_persona'] / pages[i]['copy_persona'] only —
    # a bundle-carrying run must not change what that consumer sees.
    tmpl = _synthetic_template()
    no_bundle_pages = fm.instantiate_pages(tmpl)
    bundle = {"voice_persona_id": "hormozi-100m-offers", "confirm_required": False}
    with_bundle_pages = fm.instantiate_pages(tmpl, bundle=bundle)
    for a, b in zip(no_bundle_pages, with_bundle_pages):
        assert a["copy_persona"] == b["copy_persona"]
        assert a["order"] == b["order"]
        assert a["path"] == b["path"]
        assert a["purpose"] == b["purpose"]
        assert a["blocks"] == b["blocks"]


def test_instantiate_pages_missing_voice_id_skips_blend_fields():
    # A bundle without a usable voice_persona_id (e.g. an 'absent'-source
    # normalized receipt) must never add blend fields — legacy shape preserved.
    tmpl = _synthetic_template()
    pages = fm.instantiate_pages(tmpl, bundle={"voice_persona_id": None})
    for p in pages:
        assert "blend_directive" not in p


def test_match_funnel_threads_persona_bundle_to_pages(catalog):
    bundle = {"voice_persona_id": "hormozi-100m-offers", "confirm_required": False}
    d = fm.match_funnel({"text": "build a survey quiz funnel that segments my list"},
                        catalog, persona_bundle=bundle)
    if d.get("pages"):
        for p in d["pages"]:
            assert p.get("voice_persona_id") == "hormozi-100m-offers"
