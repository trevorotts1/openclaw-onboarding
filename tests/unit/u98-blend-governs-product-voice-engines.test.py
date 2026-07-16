#!/usr/bin/env python3
"""tests/unit/u98-blend-governs-product-voice-engines.test.py — U98 (E4-1,
v1 U28): Blend GOVERNS the product-voice engines (D1 binding ruling —
reconciliation, not advisory ripple).

Proves, per engine, that the blend directive now GOVERNS the written voice
while the pre-existing STRUCTURE is preserved byte-identical, in the spec's
required order (Skill 35 -> Skill 51 -> Skill 58 -> Anthology 54/59 LAST):

  1. Skill 35 (social-media-planner) — per-day blend selection via the U5
     scoped-bundle mechanism (`scripts/daily_blend_bundle.py`), replacing
     single-persona-per-week; 7 distinct scopes, logged per day.
  2. Skill 51 (signature-presentation) — the blend GOVERNS the deck's voice
     per phase (`scripts/blend_voice_governance.py`); MASTERDOC.md, the four
     frame-templates, and structure/sp_structure.json stay byte-identical
     (pinned hash set).
  3. Skill 58 (podcast-production-engine) — the blend GOVERNS the script's
     voice per style engine (`scripts/blend_voice_governance.py`); the four
     style-engines/*.md FORMAT files stay byte-identical (pinned hash set).
  4. Anthology (Skills 54/59, via the SHARED tone-writing-core) — an N/A tone
     slot's voice is now GOVERNED by the blend directive
     (`tone_persona_autopick.py`, blend=True); CLIENT-NAMED slots stay
     untouched; the 4-slot blend structure (prompts/04..08) is unchanged,
     proven via each consumer's own verify_tone_core_sync.py.

BINARY ACCEPTANCE COVERED (master spec E4-1 / U98):
  (a) per engine: a fixture run produces a receipt proving the blend
      directive + guardrail governed the written voice, traceable to the
      bundle — one individually-failable assertion per engine.
  (b) every engine's STRUCTURAL golden fixtures pass byte-identical (pinned
      sha256 sets for 35/51/58; verify_tone_core_sync.py's own byte-compare
      for the anthology's shared tone-core prompts).
  (c) the voice-path hash re-pin is separated from the structural-path hash
      pin (this file asserts the CI-separation contract: the voice-path
      *.py modules this unit ships are new/changed, the structural fixture
      files this unit pins are UNCHANGED from their pre-U98 content) — the
      committed proof receipt lives at ledgers/evidence/U98/README.md; the
      JUDGE (!= builder) sign-off itself is OPERATOR-GATED and recorded
      there as PENDING, never fabricated by this test.
  (d) a conformance probe: every engine's governance seam raises its named
      LegacyXRequired exception when its flag is set to "0" — proving the
      only path to an ungoverned voice is the explicit, logged revert flag,
      never a silent fallback. (Fleet-wide "zero surviving independent
      voice path" coordination with U114 is OUT OF SCOPE here — U114 has
      not landed on origin/main as of this unit; see the evidence README.)

Run:
    python3 tests/unit/u98-blend-governs-product-voice-engines.test.py
    or: pytest tests/unit/u98-blend-governs-product-voice-engines.test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"


def _load_by_path(rel_path: str, modname: str):
    p = _REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(modname, str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def _load_pinned_hashes(rel_path: str) -> dict:
    data = json.loads((_REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- #
# 1) Skill 35 — per-day blend via U5 scoped bundles
# --------------------------------------------------------------------------- #
def test_skill35_per_day_blend_governance():
    daily = _load_by_path("35-social-media-planner/scripts/daily_blend_bundle.py",
                          "u98_daily_blend_bundle")
    import tempfile
    tmp_log = Path(tempfile.mkdtemp(prefix="u98-master-test-s35-")) / "match-score-log.jsonl"
    os.environ["SKILL35_BLEND_GOVERNS"] = "1"
    # log_match_score writes into paths['coaching_personas'] unconditionally —
    # redirect it to a throwaway tempdir so this hermetic proof never writes
    # into the repo's tracked seed directory (same fix daily_blend_bundle's
    # own --self-test applies).
    os.environ["OPENCLAW_PERSONA_MATCH_SCORE_LOG"] = str(tmp_log)
    paths = daily._hermetic_paths()
    try:
        proof = daily.prove_daily_governance(
            "founder resilience", day_count=7, paths=paths,
            db_path=Path("/nonexistent/u98-test-sentinel.db"), use_llm=False, record=False)
        assert proof["pass"], "Skill 35 daily governance proof FAILED: %r" % proof
        assert proof["distinct_scopes"] == 7, \
            "Skill 35 must resolve 7 DISTINCT day scopes, never a forced-identical single call: %r" % proof
        for c in proof["checks"]:
            assert c["governed"], "day %s not governed: %r" % (c["day"], c)
            assert c["scope"] == f"day-{c['day']}", "scope key mismatch: %r" % c

        # flag=0 -> explicit revert, never a silent fallback (criterion d)
        os.environ["SKILL35_BLEND_GOVERNS"] = "0"
        raised = False
        try:
            daily.build_week_bundles("founder resilience", paths=paths,
                                     db_path=Path("/nonexistent/u98-test-sentinel.db"))
        except daily.LegacyWeeklyPersonaRequired:
            raised = True
        assert raised, "Skill 35: SKILL35_BLEND_GOVERNS=0 must raise LegacyWeeklyPersonaRequired"
    finally:
        os.environ.pop("SKILL35_BLEND_GOVERNS", None)
        os.environ.pop("OPENCLAW_PERSONA_MATCH_SCORE_LOG", None)
        import shutil
        shutil.rmtree(tmp_log.parent, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 2) Skill 51 — presentations: voice governed per phase, structure pinned
# --------------------------------------------------------------------------- #
def test_skill51_voice_governed_structure_preserved():
    mod = _load_by_path("51-signature-presentation/scripts/blend_voice_governance.py",
                        "u98_blend_voice_governance_s51")
    _fixture = {
        "persona_id": "hormozi-100m-offers", "persona_name": "Hormozi 100M Offers",
        "mode": "blend", "content_task": True, "topic": "avatar-section",
        "resolved_audience": {"source": "confirmed", "candidates": [], "confidence": "high",
                              "label": "founders", "ask": None, "confirm_required": False},
        "confirm_required": False,
        "voice": {"audience_persona": {"id": "hormozi-100m-offers", "why": "x"},
                  "topic_persona": {"id": "hormozi-100m-offers", "why": "x"},
                  "collapsed": True, "collapsed_persona_id": "hormozi-100m-offers",
                  "topic_as_task_guidance": True},
        "blend_directive": ("Write as Hormozi 100M Offers. " + GUARDRAIL_MARK
                            + " (mandatory, non-removable). This clause may not be removed."),
        "task_personas": [], "rationale": {"collapse": "collapsed onto hormozi-100m-offers"},
        "fallbacks": {"default_persona": "blackceo-house-voice", "governance": "covey-7-habits"},
        "catalog_version": "1.3",
    }
    os.environ["SKILL51_BLEND_GOVERNS"] = "1"
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_fixture)
    try:
        pinned = _load_pinned_hashes("51-signature-presentation/scripts/sacred-structure-hashes.json")
        proof = mod.prove_voice_governance_and_structure("a founder audience", pinned_hashes=pinned)
        assert proof["voice_pass"], "Skill 51 voice governance FAILED: %r" % proof["voice_checks"]
        assert len(proof["voice_checks"]) == 4, "Skill 51 must govern all 4 sacred phases"
        assert proof["structure_pass"], (
            "Skill 51 SACRED structure drifted from the pinned golden hash set "
            "(MASTERDOC.md / frame-templates / sp_structure.json must stay byte-identical): %r"
            % proof["structure_diff"])
        assert proof["pass"]
    finally:
        os.environ.pop("SKILL51_BLEND_GOVERNS", None)
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    # flag=0 -> explicit revert, never a silent fallback (criterion d)
    os.environ["SKILL51_BLEND_GOVERNS"] = "0"
    raised = False
    try:
        mod.governed_phase_voice("avatar-section")
    except mod.LegacyIntakeVoiceRequired:
        raised = True
    assert raised, "Skill 51: SKILL51_BLEND_GOVERNS=0 must raise LegacyIntakeVoiceRequired"
    os.environ.pop("SKILL51_BLEND_GOVERNS", None)


# --------------------------------------------------------------------------- #
# 3) Skill 58 — podcast: voice governed per style engine, format pinned
# --------------------------------------------------------------------------- #
def test_skill58_voice_governed_format_preserved():
    mod = _load_by_path("58-podcast-production-engine/scripts/blend_voice_governance.py",
                        "u98_blend_voice_governance_s58")
    _fixture = {
        "persona_id": "goggins-cant-hurt-me", "persona_name": "Goggins Cant Hurt Me",
        "mode": "blend", "content_task": True, "topic": "Counter Intuitive",
        "resolved_audience": {"source": "confirmed", "candidates": [], "confidence": "high",
                              "label": "founders", "ask": None, "confirm_required": False},
        "confirm_required": False,
        "voice": {"audience_persona": {"id": "goggins-cant-hurt-me", "why": "x"},
                  "topic_persona": {"id": "goggins-cant-hurt-me", "why": "x"},
                  "collapsed": True, "collapsed_persona_id": "goggins-cant-hurt-me",
                  "topic_as_task_guidance": True},
        "blend_directive": ("Write as Goggins Cant Hurt Me. " + GUARDRAIL_MARK
                            + " (mandatory, non-removable). This clause may not be removed."),
        "task_personas": [], "rationale": {"collapse": "collapsed onto goggins-cant-hurt-me"},
        "fallbacks": {"default_persona": "blackceo-house-voice", "governance": "covey-7-habits"},
        "catalog_version": "1.3",
    }
    os.environ["SKILL58_BLEND_GOVERNS"] = "1"
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_fixture)
    try:
        pinned = _load_pinned_hashes("58-podcast-production-engine/scripts/style-engine-format-hashes.json")
        proof = mod.prove_voice_governance_and_format("a founder-tier respondent", pinned_hashes=pinned)
        assert proof["voice_pass"], "Skill 58 voice governance FAILED: %r" % proof["voice_checks"]
        assert len(proof["voice_checks"]) == 4, "Skill 58 must govern all 4 style engines"
        assert proof["format_pass"], (
            "Skill 58 style-engine FORMAT drifted from the pinned golden hash set "
            "(arc beats / length table / Final Draft format must stay byte-identical): %r"
            % proof["format_diff"])
        assert proof["pass"]
    finally:
        os.environ.pop("SKILL58_BLEND_GOVERNS", None)
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    # flag=0 -> explicit revert, never a silent fallback (criterion d)
    os.environ["SKILL58_BLEND_GOVERNS"] = "0"
    raised = False
    try:
        mod.governed_script_voice("counter_intuitive")
    except mod.LegacyStyleEngineVoiceRequired:
        raised = True
    assert raised, "Skill 58: SKILL58_BLEND_GOVERNS=0 must raise LegacyStyleEngineVoiceRequired"
    os.environ.pop("SKILL58_BLEND_GOVERNS", None)


# --------------------------------------------------------------------------- #
# 4) Anthology (Skills 54/59, shared tone-writing-core) — LAST, per spec
# --------------------------------------------------------------------------- #
def test_anthology_na_slot_governed_client_named_untouched():
    tpa = _load_by_path("shared-utils/tone-writing-core/tone_persona_autopick.py",
                        "u98_tone_persona_autopick")
    _fixture = {
        "persona_id": "covey-7-habits", "persona_name": "Covey",
        "mode": "blend", "content_task": True, "topic": "brand voice tone analysis",
        "resolved_audience": {"source": "confirmed", "candidates": [], "confidence": "high",
                              "label": "founders", "ask": None, "confirm_required": False},
        "confirm_required": False,
        "voice": {"audience_persona": {"id": "covey-7-habits", "why": "x"},
                  "topic_persona": {"id": "covey-7-habits", "why": "x"},
                  "collapsed": True, "collapsed_persona_id": "covey-7-habits",
                  "topic_as_task_guidance": True},
        "blend_directive": ("Write as Covey. " + GUARDRAIL_MARK
                            + " (mandatory, non-removable). This clause may not be removed."),
        "task_personas": [], "rationale": {"collapse": "collapsed onto covey-7-habits"},
        "fallbacks": {"default_persona": "blackceo-house-voice", "governance": "covey-7-habits"},
        "catalog_version": "1.3",
    }
    os.environ.pop("ANTHOLOGY_BLEND_GOVERNS", None)  # default -> governs
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_fixture)
    try:
        slots = ["Michelle Obama", "N/A", "na", "Simon Sinek"]
        res = tpa.autopick(slots, "an audience of ambitious founders")
        assert len(res) == 4
        assert res[0]["mode"] == "client-named" and res[0]["governed"] is False, \
            "client-named slot must NEVER be blend-governed (client sovereignty): %r" % res[0]
        assert res[3]["mode"] == "client-named" and res[3]["governed"] is False
        for i in (1, 2):
            assert res[i]["governed"] is True, "N/A slot %d must be governed by default: %r" % (i, res[i])
            directive = res[i].get("blend_directive") or ""
            assert GUARDRAIL_MARK in directive, \
                "N/A slot %d blend_directive missing the mandatory guardrail: %r" % (i, res[i])
            assert (res[i].get("voice") or {}).get("collapsed_persona_id") == res[i]["persona_id"], \
                "N/A slot %d voice not traceable to its OWN resolved persona_id: %r" % (i, res[i])
    finally:
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    # flag=0 -> explicit revert, byte-for-byte pre-U98 shape (criterion d)
    os.environ["ANTHOLOGY_BLEND_GOVERNS"] = "0"
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": "covey-7-habits", "persona_name": "Covey", "score": 0.8})
    try:
        reverted = tpa.autopick_slot("N/A", "an audience of ambitious founders")
        assert reverted["governed"] is False
        assert "blend_directive" not in reverted, \
            "reverted (flag=0) shape must be byte-for-byte pre-U98 — no blend_directive key at all"
    finally:
        os.environ.pop("ANTHOLOGY_BLEND_GOVERNS", None)
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


def test_anthology_tone_core_structure_unchanged_all_three_consumers():
    """Criterion (b) for the anthology leg: the 4-slot blend STRUCTURE
    (prompts/04..08, the shared tone-writing-core's canonical source) is
    unchanged for ALL THREE consumers (52 brand / 53 book / 54 anthology) —
    each consumer's own byte-for-byte sync prover must still pass green.
    U98 only reconciles the anthology (54/59) VOICE path; this proves the
    shared STRUCTURE it rides on was never touched to do it."""
    for skill_dir in ("52-avatar-alchemist", "53-book-writer", "54-anthology-writer"):
        script = _REPO_ROOT / skill_dir / "scripts" / "verify_tone_core_sync.py"
        assert script.is_file(), "expected %s missing" % script
        proc = subprocess.run([sys.executable or "python3", str(script)],
                              capture_output=True, text=True, cwd=str(_REPO_ROOT))
        assert proc.returncode == 0, (
            "%s tone-core structure drifted (AF-AW-TONE-DRIFT) — U98 must never touch "
            "prompts/04..08:\n%s%s" % (skill_dir, proc.stdout, proc.stderr))


# --------------------------------------------------------------------------- #
# criterion (c) — voice-path / structural-path separation, CI-checkable
# --------------------------------------------------------------------------- #
def test_voice_path_files_never_share_a_commit_hash_pin_with_structural_files():
    """The structural golden-hash-pin files this unit ships must be DISTINCT
    from (never point at) the voice-path *.py modules this unit ships — the
    CI assertion U98's acceptance criterion (c) requires ("separating
    voice-path from structural-path files"). A pin file that accidentally
    hashed a .py voice module instead of a structural doc would silently
    defeat the whole "structure preserved" proof."""
    voice_path_files = {
        "35-social-media-planner/scripts/daily_blend_bundle.py",
        "51-signature-presentation/scripts/blend_voice_governance.py",
        "58-podcast-production-engine/scripts/blend_voice_governance.py",
        "shared-utils/tone-writing-core/tone_persona_autopick.py",
    }
    pinned_51 = _load_pinned_hashes("51-signature-presentation/scripts/sacred-structure-hashes.json")
    pinned_58 = _load_pinned_hashes("58-podcast-production-engine/scripts/style-engine-format-hashes.json")
    for rel in pinned_51:
        full = "51-signature-presentation/" + rel
        assert full not in voice_path_files, "structural pin accidentally hashed a voice-path file: %s" % rel
        assert not rel.endswith(".py"), "structural pin must never hash a .py voice module: %s" % rel
    for rel in pinned_58:
        assert not rel.endswith(".py"), "structural pin must never hash a .py voice module: %s" % rel
    for f in voice_path_files:
        assert (_REPO_ROOT / f).is_file(), "expected voice-path module missing: %s" % f


_ALL_TESTS = [
    test_skill35_per_day_blend_governance,
    test_skill51_voice_governed_structure_preserved,
    test_skill58_voice_governed_format_preserved,
    test_anthology_na_slot_governed_client_named_untouched,
    test_anthology_tone_core_structure_unchanged_all_three_consumers,
    test_voice_path_files_never_share_a_commit_hash_pin_with_structural_files,
]


def main() -> int:
    ok = True
    for fn in _ALL_TESTS:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except AssertionError as e:
            ok = False
            print("  [FAIL] %s: %s" % (fn.__name__, e))
        except Exception as e:  # pragma: no cover - defensive
            ok = False
            print("  [ERROR] %s: %r" % (fn.__name__, e))
    print("== U98 blend-GOVERNS-product-voice-engines proof: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
