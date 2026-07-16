"""A-U9 (master spec v2, master unit U9) — exemplar convention + write-time
injection (CALIBRATION-ONLY clause + injection receipts; Skill 6 lead/buyer/
event + Skill 35 packs). SKILL-6-INTEGRATION-LEVEL acceptance tests (master
spec v2 A.10 A-U9 binary acceptance):

  (a)  >=1 exemplar pack per funnel-template category (lead/buyer/event) +
       >=1 for Skill 35, each with all three files (gold output,
       WHY-GOOD.md, provenance.json) — unit-level proof lives in
       shared-utils/test_exemplar_injection.py; this file re-confirms it
       from the SKILL-6-INTEGRATION side (the actual packs this dispatch
       consumes).
  (b)  a fixture funnel copy job's evidence tree contains
       routing/exemplar-injection.json whose hashes match the shipped
       exemplars — proven END-TO-END here through a REAL v2_dispatcher
       fixture dispatch (mirrors test_a_u7_convergence.py's
       TestAU7OfflineFixtureDispatch pattern), never a unit-test-only claim.
  (c)  an LLM reviewer pass (never a name-grep) confirms zero
       client-identifying content in every pack — unit-level proof in
       shared-utils/test_exemplar_injection.py (the llm_content_review
       receipt on every shipped pack's provenance.json).
  (d)  prompts without an applicable pack degrade to today's behavior (no
       empty-injection block) — proven here at the FULL-DISPATCH level: a
       fixture funnel whose category has no shipped pack completes exactly
       as it did before A-U9, with no exemplar-injection.json artifact at
       all (never an empty-but-present one).

MOCK-only, exactly like test_a_u7_convergence.py / test_v2_dispatcher.py:
the builder + verifier are injected fakes, no network, no browser. The
exemplar SELECTION itself is REAL — exemplar_injection.py reads the actual
shipped packs under 06-ghl-install-pages/exemplars/, so this proves genuine
selection + injection behavior, not a fixture that asserts nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_SKILL6_DIR = os.path.dirname(_TOOLS_DIR)
_SHARED_UTILS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "shared-utils"))
for _p in (_TOOLS_DIR, _SHARED_UTILS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import v2_dispatcher as disp  # noqa: E402
import skill6_convergence as conv  # noqa: E402
import exemplar_injection as exi  # noqa: E402


FAKE_TASK = {"id": "a-u9-fixture", "brand": "Fictional Trailhead Coaching",
             "location_id": "LOCATIONfake0001", "brief": "build a lead-magnet funnel"}

_LEAD_PAGES_SPEC = [
    {"order": 1, "page": "Optin", "path": "optin",
     "purpose": "clear one-liner brand messaging that clarifies the offer with a "
                "storytelling framework and message clarity",
     "blocks": ["hero", "form"], "skill44Widgets": []},
    {"order": 2, "page": "Thank You", "path": "thank-you",
     "purpose": "confirm the booked call", "blocks": ["cta"], "skill44Widgets": []},
]

_REAL_COPY = {
    "hero": ("Book a free twenty-minute session where we map the one hiking route your "
             "own audience keeps asking about, so you stop guessing which guided trip to "
             "build next and start building the one they already want."),
    "cta": "Reserve your free trail-mapping session now.",
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


def _step0_matches_group(group: str, persona_id="funnel-architect", persona_label="Funnel Architect"):
    """An injected STEP 0 that mirrors the REAL funnel_matcher.step0_match's
    two receipts: it writes routing/funnel-match.json carrying
    matched_template_key='<group>/<id>' (exactly the field
    _deliverable_type_for_task reads as its evidence-tree fallback) AND
    mutates the task with instantiated pages, exactly like
    test_a_u7_convergence.py's _step0_instantiates_real_pages but
    additionally proving the REAL (task-absent) matched_template_key
    evidence-tree read path, not the task-level shortcut."""
    import funnel_matcher as fm

    def _s0(task, evidence_root):
        tmpl = {
            "id": "synthetic-a-u9", "group": group, "name": "Synthetic A-U9 Fixture",
            "persona": {"id": persona_id, "label": persona_label, "author": "", "script": "", "detail": ""},
            "pageStructure": [dict(p) for p in _LEAD_PAGES_SPEC],
            "scripts": "",
        }
        routing = os.path.join(evidence_root, "routing")
        os.makedirs(routing, exist_ok=True)
        # The REAL step0_match receipt shape (funnel_matcher.py's own
        # json.dump(decision, ...) at routing/funnel-match.json) — carries
        # matched_template_key so _deliverable_type_for_task's evidence-tree
        # fallback path is exercised for real, not just its task-level
        # shortcut.
        with open(os.path.join(routing, "funnel-match.json"), "w", encoding="utf-8") as f:
            json.dump({
                "decision": "USE_TEMPLATE",
                "matched_template": "synthetic-a-u9",
                "matched_template_key": f"{group}/synthetic-a-u9",
            }, f)
        pages = fm.instantiate_pages(tmpl, bundle=task.get("persona_bundle"))
        task["pages"] = pages
        task["copy_persona"] = persona_label
        # Deliberately mirrors the REAL step0_match: template_match carries
        # NO matched_template_key (proving A-U9 does not depend on that
        # never-actually-populated field; see _deliverable_type_for_task's
        # docstring).
        return {"decision": "USE_TEMPLATE",
                "template_match": {"decision": "USE_TEMPLATE", "matched_template": "synthetic-a-u9"}}
    return _s0


def _builder_echoes_real_copy():
    def _b(task, evidence_root):
        os.makedirs(os.path.join(evidence_root, "funnel"), exist_ok=True)
        plan = task.get("pages") or []
        built = [{"name": p.get("name", f"p{i}"), "preview_url": f"u{i}",
                  "marker": "m", "copy": dict(_REAL_COPY)} for i, p in enumerate(plan)]
        return {"pages": built, "location_gate_ok": True, "duration_s": 5.0}
    return _b


def _fake_verifier(overall: bool, passed: int, total: int):
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


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return "sha256:" + h.hexdigest()


class TestAcceptanceAExemplarPacksShipped:
    """(a) >=1 exemplar pack per funnel-template category (lead/buyer/event)
    + >=1 for Skill 35 — re-confirmed from the actual packs this dispatch
    consumes."""

    def test_lead_buyer_event_each_ship_a_complete_pack(self):
        for category in ("lead", "buyer", "event"):
            packs = exi.discover_packs(_SKILL6_DIR, deliverable_type=category)
            assert len(packs) >= 1, f"Skill 6 must ship >=1 exemplar pack for {category!r}"

    def test_skill35_ships_a_complete_pack(self):
        skill35_dir = os.path.normpath(os.path.join(_SKILL6_DIR, "..", "35-social-media-planner"))
        packs = exi.discover_packs(skill35_dir)
        assert len(packs) >= 1, "Skill 35 must ship >=1 exemplar pack"


class TestAcceptanceBFixtureFunnelInjectionReceipt:
    """(b) a fixture funnel copy job's evidence tree contains
    routing/exemplar-injection.json whose hashes match the shipped
    exemplars — proven end-to-end through a real v2_dispatcher dispatch."""

    def test_full_dispatch_writes_exemplar_injection_receipt_with_matching_hashes(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("SKILL6_CONSUME_BLEND", "1")
        task = dict(FAKE_TASK, persona_bundle=_threaded_bundle())

        res = disp.dispatch_one(
            task, str(tmp_path),
            builder=_builder_echoes_real_copy(),
            verifier=_fake_verifier(True, passed=2, total=2),
            step0_matcher=_step0_matches_group("lead"),
        )
        assert res.state == disp.STATE_VERIFIED, res.reason

        # skill6_convergence must have resolved deliverable_type='lead' from
        # the evidence-tree routing/funnel-match.json fallback (task-level
        # template_match carries no matched_template_key, per the fixture).
        rec = json.load(open(os.path.join(str(tmp_path), "routing", "task-record.json")))
        conv_rec = rec["skill6_convergence"]
        assert conv_rec["ran"] is True
        assert conv_rec["deliverable_type"] == "lead"

        receipt_path = os.path.join(str(tmp_path), "routing", "exemplar-injection.json")
        assert os.path.isfile(receipt_path), (
            "a fixture funnel copy job's evidence tree must contain "
            "routing/exemplar-injection.json")

        on_disk = json.load(open(receipt_path, encoding="utf-8"))
        assert len(on_disk["injections"]) >= 1
        assert all(i["deliverable_type"] == "lead" for i in on_disk["injections"])
        assert any(i["injected"] for i in on_disk["injections"]), (
            "at least one page must have an applicable 'lead' pack injected"
        )

        receipt_hashes = {
            e["content_hash"]
            for i in on_disk["injections"] for e in i["exemplars"]
        }
        assert receipt_hashes, "the receipt must carry at least one exemplar hash"

        shipped_packs = exi.discover_packs(_SKILL6_DIR, deliverable_type="lead")
        shipped_hashes = {_sha256_file(p["gold_output_path"]) for p in shipped_packs}
        assert receipt_hashes <= shipped_hashes, (
            "every hash in the receipt must match a REAL shipped exemplar's "
            "sha256 — never a fabricated hash")

        # Per-page bundle receipts also carry the real exemplar_refs (the
        # seam A-U7 left as an honest empty list, per its own comment, is
        # now populated for real).
        receipts_dir = os.path.join(str(tmp_path), "routing", "persona-bundle-receipts")
        any_refs = False
        for fn in os.listdir(receipts_dir):
            page_receipt = json.load(open(os.path.join(receipts_dir, fn), encoding="utf-8"))
            if page_receipt["exemplar_refs"]:
                any_refs = True
                for ref in page_receipt["exemplar_refs"]:
                    assert ref["content_hash"] in shipped_hashes
        assert any_refs, "at least one per-page receipt must carry real exemplar_refs"

    def test_buyer_and_event_categories_also_inject_from_their_own_packs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SKILL6_CONSUME_BLEND", "1")
        for category in ("buyer", "event"):
            task = dict(FAKE_TASK, id=f"a-u9-fixture-{category}", persona_bundle=_threaded_bundle())
            work_dir = tmp_path / category
            work_dir.mkdir()
            res = disp.dispatch_one(
                task, str(work_dir),
                builder=_builder_echoes_real_copy(),
                verifier=_fake_verifier(True, passed=2, total=2),
                step0_matcher=_step0_matches_group(category),
            )
            assert res.state == disp.STATE_VERIFIED, res.reason
            receipt_path = os.path.join(str(work_dir), "routing", "exemplar-injection.json")
            assert os.path.isfile(receipt_path), f"{category} fixture must inject from its own pack"
            on_disk = json.load(open(receipt_path, encoding="utf-8"))
            assert all(i["deliverable_type"] == category for i in on_disk["injections"])


class TestAcceptanceDDegradeToTodaysBehavior:
    """(d) prompts without an applicable pack degrade to today's behavior
    (no empty-injection block) — proven at the full-dispatch level."""

    def test_unmatched_category_writes_no_exemplar_injection_file_at_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SKILL6_CONSUME_BLEND", "1")
        task = dict(FAKE_TASK, id="a-u9-no-pack", persona_bundle=_threaded_bundle())

        res = disp.dispatch_one(
            task, str(tmp_path),
            builder=_builder_echoes_real_copy(),
            verifier=_fake_verifier(True, passed=2, total=2),
            step0_matcher=_step0_matches_group("no-such-funnel-category"),
        )
        assert res.state == disp.STATE_VERIFIED, res.reason

        rec = json.load(open(os.path.join(str(tmp_path), "routing", "task-record.json")))
        assert rec["skill6_convergence"]["deliverable_type"] == "no-such-funnel-category"

        receipt_path = os.path.join(str(tmp_path), "routing", "exemplar-injection.json")
        assert not os.path.isfile(receipt_path), (
            "no applicable pack -> no injection artifact at all, never an "
            "empty-but-present one")

        receipts_dir = os.path.join(str(tmp_path), "routing", "persona-bundle-receipts")
        for fn in os.listdir(receipts_dir):
            page_receipt = json.load(open(os.path.join(receipts_dir, fn), encoding="utf-8"))
            assert page_receipt["exemplar_refs"] == [], (
                "an honest empty list — never a fabricated ref — exactly "
                "today's (pre-A-U9) behavior")

    def test_build_injection_block_is_none_for_no_applicable_pack(self):
        packs = exi.select_exemplars(_SKILL6_DIR, "no-such-funnel-category")
        assert packs == []
        assert exi.build_injection_block(packs) is None
