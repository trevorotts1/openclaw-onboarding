"""A-U7 — Skill 6 convergence (THE unification unit). OFFLINE-ONLY acceptance
tests per the OPERATOR RULINGS 2026-07-15 per-repo/offline doctrine (master
spec v2 §A.10 A-U7 binary acceptance, ONB half):

  (a)  a fixture funnel evidence tree (offline dry-run instantiation, no live
       deploy) shows per-page bundle receipts (blend + goal + exemplar refs)
       for 100% of pages.
  (a2) *(MOVED from A-U5)* the same offline fixture funnel build produces N
       pages with >=2 DISTINCT blends and exactly N per-page
       persona-selection-log entries, each stating WHY pages share or differ.
  (c)  the P2 receipt (routing/p2-persona-attach.json) validates under the
       D-A3 ratified rule: {voice_persona, topic_persona, copy_task_persona}
       with copy_task_persona in copy_craft_pool.
  (d-offline) with SKILL6_CONSUME_BLEND=1, an OFFLINE fixture dispatch
       through v2_dispatcher consumes the acquired bundle and clears the
       FIXTURE gate chain (FAB-QC >= 8.5, blend grounded) using NO live
       GHL/Vercel — the injected verifier stands in for render_check against
       a sealed local fixture snapshot, never a live page.

MOCK-only, exactly like test_v2_dispatcher.py: the builder is an injected
fake, the verifier is injected (live=False), no network, no browser. The
per-page blend SELECTION itself is REAL — skill6_convergence.py calls the
real persona_blend.match_topic_persona over the real
persona-categories.json catalog and the real persona-crosswalk.json
copy_craft_pool, so this proves genuine selection behavior, not a fixture
that asserts nothing.
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_SHARED_UTILS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "shared-utils"))
for _p in (_TOOLS_DIR, _SHARED_UTILS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import v2_dispatcher as disp  # noqa: E402
import skill6_convergence as conv  # noqa: E402
import persona_crosswalk as pcw  # noqa: E402


FAKE_TASK = {"id": "a-u7-fixture", "brand": "Fictional Scent Studio",
             "location_id": "LOCATIONfake0000", "brief": "build a lead-magnet funnel"}

# A 3-page synthetic template whose page PURPOSES intentionally carry real
# topics[] signal for three DIFFERENT catalog personas — chosen by reading
# the real persona-categories.json topics[] arrays (never by hand-wiring the
# id the test expects to see; the assertions below check DISTINCTNESS, not a
# specific hard-coded id, so this stays a genuine behavioral proof).
_PAGES_SPEC = [
    {"order": 1, "page": "Optin", "path": "optin",
     "purpose": "clear one-liner brand messaging that clarifies the offer with a "
                "storytelling framework and message clarity",
     "blocks": ["hero", "form"], "skill44Widgets": []},
    {"order": 2, "page": "Sales", "path": "sales",
     "purpose": "sales page architecture with guarantees and risk reversal, "
                "scarcity and urgency, bonuses and stacking, pricing and premium pricing",
     "blocks": ["hero", "stack", "guarantee"], "skill44Widgets": []},
    {"order": 3, "page": "Thank You", "path": "thank-you",
     "purpose": "confirm the booked call", "blocks": ["cta"], "skill44Widgets": []},
]

_REAL_COPY = {
    "hero": ("Design your own signature scent in a single evening and walk out wearing "
             "it — a hands-on scent-bar workshop where you blend, name, and bottle a "
             "fragrance that is unmistakably yours. No experience needed, nothing to buy "
             "afterward, and a finished bottle in your hand before you ever leave the "
             "room. Every perfume on the department-store shelf was designed by a "
             "committee to smell acceptable to a million strangers, which is exactly why "
             "none of them ever smell like you — tonight that changes for good."),
    "stack": ("A private two-hour guided blending session at the scent bar, small group, "
              "real instruction, your own hands on every single step of the process. A "
              "take-home kit with your final formula written out in full, so the scent "
              "you made tonight is one you can make again next season without guessing. "
              "A recipe card and the complete three-layer framework in print, so the "
              "method is yours to keep long after the workshop itself has ended for good."),
    "guarantee": ("Blend-it-or-it-is-free: sit through the full guided session, follow "
                  "the three-layer method with an instructor beside you at every step, "
                  "and if you do not leave with a finished bottle you are genuinely proud "
                  "to wear, the entire evening is on us — full refund, no questions asked, "
                  "and you keep the take-home kit anyway. You carry none of the risk here; "
                  "either you walk out wearing something truly yours, or you do not pay."),
    "cta": "Reserve your scent-bar seat now before this week's evening fills.",
}


def _threaded_bundle() -> dict:
    return {
        "voice_persona_id": "hormozi-100m-offers",
        "topic_persona_id": "hormozi-100m-offers",
        "audience_id": None,
        "audience_label": "solo-founder coaches",
        "confirm_required": False,
        "content_task": True,
        "blend_directive": "Write in Hormozi's voice. GUARDRAIL",
        "task_personas": [{"seq": 1, "persona_id": "hormozi-100m-offers"}],
    }


def _step0_instantiates_real_pages(persona_id="funnel-architect", persona_label="Funnel Architect"):
    """An injected STEP 0 that builds a synthetic template, calls the REAL
    (unmodified) funnel_matcher.instantiate_pages(bundle=...) to get U16's
    per-page fields, writes routing/match-decision.json (the FAB-QC contract,
    mirroring funnel_matcher.step0_match's own receipt shape), and mutates
    the task exactly as step0_match would on a USE_TEMPLATE decision."""
    import funnel_matcher as fm

    def _s0(task, evidence_root):
        tmpl = {
            "id": "synthetic-a-u7", "group": "synthetic", "name": "Synthetic A-U7 Fixture",
            "persona": {"id": persona_id, "label": persona_label, "author": "", "script": "", "detail": ""},
            "pageStructure": [dict(p) for p in _PAGES_SPEC],
            "scripts": "",
        }
        routing = os.path.join(evidence_root, "routing")
        os.makedirs(routing, exist_ok=True)
        with open(os.path.join(routing, "matched-template.json"), "w", encoding="utf-8") as f:
            json.dump(tmpl, f)
        with open(os.path.join(routing, "match-decision.json"), "w", encoding="utf-8") as f:
            json.dump({"matched_template_id": "synthetic-a-u7",
                       "template_path": "matched-template.json",
                       "intent_mode": "HANDS_OFF_DO_IT_ALL", "flex_decision": "USE_TEMPLATE"}, f)
        pages = fm.instantiate_pages(tmpl, bundle=task.get("persona_bundle"))
        task["pages"] = pages
        task["copy_persona"] = persona_label
        return {"decision": "USE_TEMPLATE",
                "template_match": {"decision": "USE_TEMPLATE", "matched_template": "synthetic-a-u7"}}
    return _s0


def _builder_echoes_real_copy():
    """Returns the pages the builder 'built' WITH real, substantial copy
    attached — mirrors test_v2_dispatcher.py's TestFabArtifactProducer
    pattern. Deliberately does NOT touch persona-selection-log.md, so the
    A-U7 convergence pass's per-page log (written before the builder runs)
    survives to the end of the dispatch untouched — this is what (a2) reads."""
    def _b(task, evidence_root):
        os.makedirs(os.path.join(evidence_root, "funnel"), exist_ok=True)
        plan = task.get("pages") or []
        built = [{"name": p.get("name", f"p{i}"), "preview_url": f"u{i}",
                  "marker": "m", "copy": dict(_REAL_COPY)} for i, p in enumerate(plan)]
        return {"pages": built, "location_gate_ok": True, "duration_s": 5.0}
    return _b


def _fake_verifier(overall: bool, passed: int, total: int):
    """Injected verifier — the OFFLINE stand-in for a live render_check
    against a sealed local fixture snapshot (never a live GHL/Vercel page)."""
    def _v(evidence_root, pages, **kw):
        summary = {"overall_pass": overall, "passed": passed, "total": total,
                   "failed": total - passed}
        os.makedirs(os.path.join(evidence_root, "scorecard"), exist_ok=True)
        os.makedirs(os.path.join(evidence_root, "logs"), exist_ok=True)
        with open(os.path.join(evidence_root, "scorecard", "verify-summary.json"), "w") as f:
            json.dump(summary, f)
        with open(os.path.join(evidence_root, "logs", "final-preview-verify.json"), "w") as f:
            json.dump({"raw": "sealed-local-fixture-snapshot", "pages": pages}, f)
        return summary
    return _v


class TestAU7ConvergencePerPageBlends:
    """(a2) N pages, >=2 DISTINCT blends, exactly N per-page selection-log
    entries stating WHY pages share/differ. Runs skill6_convergence directly
    (no dispatch needed) against the REAL catalog + REAL crosswalk."""

    def test_offline_fixture_yields_at_least_two_distinct_blends(self, tmp_path):
        import funnel_matcher as fm
        tmpl = {
            "id": "t", "group": "g", "name": "n",
            "persona": {"id": "funnel-architect", "label": "Funnel Architect"},
            "pageStructure": [dict(p) for p in _PAGES_SPEC], "scripts": "",
        }
        bundle = _threaded_bundle()
        pages = fm.instantiate_pages(tmpl, bundle=bundle)
        assert len(pages) == 3

        blends = conv.select_page_blends(pages, bundle, conversion_goal="book-a-call")
        assert len(blends) == 3, "one blend-selection entry per page"

        distinct_topics = {b["topic_persona_id"] for b in blends}
        assert len(distinct_topics) >= 2, (
            f"expected >=2 DISTINCT blends across pages with genuinely different "
            f"purposes, got {distinct_topics}"
        )
        voices = {b["voice_persona_id"] for b in blends}
        assert voices == {"hormozi-100m-offers"}, "VOICE stays the ONE task-level persona across every page"

        conv.annotate_pages(pages, blends)
        for p in pages:
            assert p.get("topic_persona_id"), "every page must carry a refined topic_persona_id"

        log_path = conv.write_selection_log(str(tmp_path), blends)
        text = open(log_path, encoding="utf-8").read()
        assert text.count("## Page ") == 3, "exactly N per-page persona-selection-log entries"
        assert text.count("share_or_differ:") == 3, "every entry states WHY pages share or differ"
        assert "DIFFERENT" in text, "at least one page must be logged as DIFFERENT (>=2 distinct blends)"
        assert f"distinct_blend_count: {len(distinct_topics)}" in text

    def test_per_page_bundle_receipts_cover_100_percent_of_pages(self, tmp_path):
        """(a): per-page bundle receipts (blend + goal + exemplar refs) for
        100% of pages."""
        import funnel_matcher as fm
        tmpl = {
            "id": "t", "group": "g", "name": "n",
            "persona": {"id": "funnel-architect", "label": "Funnel Architect"},
            "pageStructure": [dict(p) for p in _PAGES_SPEC], "scripts": "",
        }
        bundle = _threaded_bundle()
        pages = fm.instantiate_pages(tmpl, bundle=bundle)
        blends = conv.select_page_blends(pages, bundle, conversion_goal="book-a-call")

        receipt_paths = conv.write_per_page_bundle_receipts(str(tmp_path), blends)
        assert len(receipt_paths) == len(pages) == 3, "a receipt for 100% of pages"
        for rp in receipt_paths:
            receipt = json.load(open(rp, encoding="utf-8"))
            assert receipt["voice_persona_id"] == "hormozi-100m-offers"
            assert receipt["topic_persona_id"], "every receipt must carry a resolved topic persona"
            assert receipt["conversion_goal"] == "book-a-call", "goal carried on every receipt"
            assert receipt["exemplar_refs"] == [], (
                "A-U9 has not landed yet — an honest empty list, never a fabricated ref"
            )

    def test_share_or_differ_reasoning_on_a_forced_shared_blend(self, tmp_path):
        """Two pages with NO page-specific topics[] signal (generic purpose
        text) legitimately share the SAME crosswalk-resolved blend — the log
        must say WHY (never a silent identical blend)."""
        bundle = _threaded_bundle()
        pages = [
            {"order": 1, "name": "A", "path": "a", "purpose": "step one", "copy_persona": "Funnel Architect"},
            {"order": 2, "name": "B", "path": "b", "purpose": "step two", "copy_persona": "Funnel Architect"},
        ]
        blends = conv.select_page_blends(pages, bundle, conversion_goal="")
        assert blends[0]["topic_persona_id"] == blends[1]["topic_persona_id"], (
            "generic purposes with no topics[] signal legitimately share the crosswalk fallback"
        )
        log_path = conv.write_selection_log(str(tmp_path), blends)
        text = open(log_path, encoding="utf-8").read()
        assert "SAME topic persona as page" in text
        assert "distinct_blend_count: 1" in text


class TestAU7P2Receipt:
    """(c) the P2 receipt validates under the D-A3 ratified rule."""

    def test_p2_receipt_carries_voice_topic_and_pool_validated_copy_task_persona(self, tmp_path):
        bundle = _threaded_bundle()
        receipt = conv.write_p2_persona_attach_receipt(
            str(tmp_path), bundle, template_persona_ref="funnel-architect")

        assert receipt["voice_persona"] == "hormozi-100m-offers"
        assert receipt["topic_persona"] == "hormozi-100m-offers"
        assert receipt["copy_task_persona"], "copy_task_persona must be resolved"
        pool = pcw.load_copy_craft_pool()
        assert receipt["copy_task_persona"] in pool, (
            "D-A3: the copy-craft TASK slot must be a copy_craft_pool member"
        )
        assert receipt["copy_task_persona_in_allowlist"] is True
        assert "TASK/CONVERSION slot ONLY" in receipt["d_a3_rule"]

        on_disk = json.load(open(os.path.join(str(tmp_path), "routing", "p2-persona-attach.json")))
        assert on_disk == receipt

    def test_voice_is_never_forced_into_the_allowlist(self, tmp_path):
        """D-A3: VOICE may be ANY of the 99 catalog personas — never limited
        to copy_craft_pool. Only copy_task_persona is pool-validated."""
        bundle = {
            "voice_persona_id": "michelle-obama-becoming",  # deliberately NOT in copy_craft_pool
            "topic_persona_id": "michelle-obama-becoming",
            "task_personas": [],
        }
        receipt = conv.write_p2_persona_attach_receipt(str(tmp_path), bundle)
        assert receipt["voice_persona"] == "michelle-obama-becoming"
        pool = pcw.load_copy_craft_pool()
        assert receipt["copy_task_persona"] in pool
        assert receipt["copy_task_persona"] != receipt["voice_persona"], (
            "the allowlist governs the TASK slot only, never overrides VOICE"
        )


class TestAU7OfflineFixtureDispatch:
    """(d-offline): with SKILL6_CONSUME_BLEND=1, an OFFLINE fixture dispatch
    through v2_dispatcher consumes the acquired bundle and clears the FIXTURE
    gate chain (FAB-QC >= 8.5, blend grounded), NO live GHL/Vercel."""

    def test_full_offline_dispatch_consumes_blend_and_clears_fab_qc_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SKILL6_CONSUME_BLEND", "1")
        task = dict(FAKE_TASK, persona_bundle=_threaded_bundle())

        res = disp.dispatch_one(
            task, str(tmp_path),
            builder=_builder_echoes_real_copy(),
            verifier=_fake_verifier(True, passed=3, total=3),
            step0_matcher=_step0_instantiates_real_pages(),
        )

        assert res.state == disp.STATE_VERIFIED, res.reason
        assert bool(res), "a passing dispatch must be truthy"

        rec = json.load(open(os.path.join(str(tmp_path), "routing", "task-record.json")))
        conv_rec = rec["skill6_convergence"]
        assert conv_rec["ran"] is True, "convergence must have run (SKILL6_CONSUME_BLEND=1, usable bundle, pages present)"
        assert conv_rec["page_count"] == 3
        assert conv_rec["distinct_blend_count"] >= 2

        # FAB-QC gate genuinely fired and cleared >= 8.5 with the blend GROUNDED.
        fab = rec["fab_qc"]
        assert fab["ran"] is True, "FAB-QC must have fired on the real evidence tree"
        assert fab["passed"] is True, f"FAB-QC must clear >=8.5, got {fab}"
        assert fab["score"] >= 8.5

        # The persona-bundle receipt proves NO live GHL/Vercel call — the ladder
        # (source=threaded) and the injected verifier (sealed local fixture
        # snapshot) are the only sources of truth in this test.
        pb_receipt = json.load(open(os.path.join(str(tmp_path), "routing", "persona-bundle-receipt.json")))
        assert pb_receipt["source"] == "threaded"

        # (a2) exactly N per-page selection-log entries survived to the end of dispatch.
        log_text = open(os.path.join(str(tmp_path), "persona-selection-log.md")).read()
        assert log_text.count("## Page ") == 3

        # (c) the P2 receipt was written as part of the SAME dispatch.
        p2 = json.load(open(os.path.join(str(tmp_path), "routing", "p2-persona-attach.json")))
        assert p2["voice_persona"] == "hormozi-100m-offers"
        assert p2["copy_task_persona_in_allowlist"] is True

        # (a) per-page bundle receipts for 100% of pages.
        receipts_dir = os.path.join(str(tmp_path), "routing", "persona-bundle-receipts")
        assert len(os.listdir(receipts_dir)) == 3

    def test_gate_off_reverts_to_template_persona_only_legacy_behavior(self, tmp_path, monkeypatch):
        """REVERT proof: SKILL6_CONSUME_BLEND=0 flips consumption off
        INSTANTLY — the bundle stays acquired + receipted, but the
        convergence pass (per-page refinement, selection-log, P2 receipt) is
        a clean no-op."""
        monkeypatch.setenv("SKILL6_CONSUME_BLEND", "0")
        task = dict(FAKE_TASK, id="a-u7-revert", persona_bundle=_threaded_bundle())

        # NOTE: this dispatch is NOT expected to reach STATE_VERIFIED — with
        # the A-U7 convergence pass off, persona-selection-log.md is never
        # written by anything in this fixture, so the (unrelated, pre-existing)
        # FAB-QC D4 grounding gate fails closed for lack of a log. That is the
        # CORRECT, honest legacy behavior this test is proving: the revert
        # switch genuinely disables A-U7's OWN machinery, it does not paper
        # over what disabling it costs downstream.
        res = disp.dispatch_one(
            task, str(tmp_path),
            builder=_builder_echoes_real_copy(),
            verifier=_fake_verifier(True, passed=3, total=3),
            step0_matcher=_step0_instantiates_real_pages(),
        )

        # task-record.json only carries skill6_convergence on a VERIFIED
        # transition (this dispatch FAILED downstream at the unrelated FAB-QC
        # D4 gate, per the note above) — the task dict itself is the direct,
        # unconditional source of truth for whether A-U7's own pass ran.
        assert task["skill6_convergence"]["ran"] is False
        assert "disabled" in task["skill6_convergence"]["reason"]

        # the bundle was still acquired + receipted (B-U1/U15 untouched by this gate)
        pb_receipt = json.load(open(os.path.join(str(tmp_path), "routing", "persona-bundle-receipt.json")))
        assert pb_receipt["source"] == "threaded"

        # no A-U7 artifacts written
        assert not os.path.isfile(os.path.join(str(tmp_path), "routing", "p2-persona-attach.json"))
        assert not os.path.isdir(os.path.join(str(tmp_path), "routing", "persona-bundle-receipts"))

    def test_no_bundle_no_pages_convergence_is_a_clean_noop(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SKILL6_CONSUME_BLEND", "1")
        res = disp.dispatch_one(
            dict(FAKE_TASK, id="a-u7-nobundle"), str(tmp_path),
            builder=lambda t, r: {"pages": [], "location_gate_ok": True, "duration_s": 1.0},
            verifier=_fake_verifier(True, passed=0, total=0),
        )
        assert res.state == disp.STATE_VERIFIED, res.reason
        rec = json.load(open(os.path.join(str(tmp_path), "routing", "task-record.json")))
        assert rec["skill6_convergence"]["ran"] is False
