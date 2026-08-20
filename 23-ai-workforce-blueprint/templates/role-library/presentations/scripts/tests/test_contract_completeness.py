"""THE DRIFT TEST: fail RED when a rule exists on P4-COPY's judging path but is
absent from ARTIFACT_CONTRACTS["P4-COPY"].

WHY THIS FILE EXISTS
--------------------
tests/test_af_c8_copy_contract.py locked ONE missing rule (AF-C8) into the
contract.  That was the instance.  This file is the class: it re-derives the
whole constraint set from the code that judges the artifact and fails when the
contract does not carry it -- including a rule added months from now by someone
who has never read this file.

MEASURED ROOT CAUSE (live run pres-wave-e-v3-1787240658, 2026-08-20; read out of
that run's state.json `events` array, not summarised from a report):

  12:33:13  P-SP-P3-HYGIENE  AF-SP-P3-PITCH / AF-SP-PRICE-IN-TEACH
  14:27:22  P1Q-COPY-QC      AF-C8 x2 (slides 20 and 25)
  15:14:17  P4-COPY          AF-NO-FELT-STAKES
  16:21:32  P4-COPY          AF-NO-RECAP
  16:37:09  P4-COPY          AF-NO-VILLAIN + AF-NO-RECAP + AF-NARRATIVE-HARMONY

Seven distinct codes, each discovered only after the previous re-author, each
re-author a real paid DeepSeek call.  Five of the seven judge
working/copy/slides_copy.md -- the file P4-COPY writes -- and belong in this
contract.  TWO DO NOT, and the distinction is load-bearing rather than
pedantic: build_deck._chk_sp_no_pitch (the source of AF-SP-P3-PITCH, whose
message body carries the AF-SP-PRICE-IN-TEACH sub-reasons) delegates to
prove_sp_no_pitch.evaluate_paths(working/copy/sp_intake.json,
working/copy/sp_structure.json) -- it never opens slides_copy.md at all.  Those
two are P-SP-STRUCTURE's author's constraints.  Putting them here would tell the
copywriter to fix a file it does not write, which is the same category of error
as the omissions this test exists to prevent.  They are asserted EXCLUDED below,
with that reasoning attached, so the exclusion is a recorded decision rather
than another silent gap.

HOW THIS TEST AVOIDS BEING VACUOUS
----------------------------------
dispatcher composes the contract by APPENDING a generated index
(contract_introspect.render_constraint_index()).  A test that only asserted
"every derived code appears in the contract" would therefore be checking that a
string contains itself.  So the primary assertion is scoped to the contract's
HAND-WRITTEN PROSE -- everything BEFORE dispatcher.CONSTRAINT_INDEX_MARKER --
for every code that BLOCKS THIS PHASE.  A new rule added to any checker on the
verification path reaches the generated index automatically (so no author is
ever blind in the meantime) and still turns this test RED until a human writes
real guidance for it, which is the only thing that actually converges.

Flat file inside tests/, manages its own import path -- matching every sibling
in this directory (test_af_c8_copy_contract.py, test_dispatcher_autospawn.py).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import contract_introspect as ci  # noqa: E402
from presentation_job import dispatcher as d  # noqa: E402

# The five of the seven live-run codes that judge working/copy/slides_copy.md.
SEVEN_LIVE_CODES_IN_SCOPE = (
    "AF-NO-FELT-STAKES",
    "AF-NO-RECAP",
    "AF-NO-VILLAIN",
    "AF-NARRATIVE-HARMONY",
    "AF-C8",
)
# The two that judge working/copy/sp_structure.json + sp_intake.json instead.
SEVEN_LIVE_CODES_OUT_OF_SCOPE = (
    "AF-SP-P3-PITCH",
    "AF-SP-PRICE-IN-TEACH",
)

# Codes that live in the two engine modules but are NOT reachable from the COPY
# entry points -- image/prompt-QC (check_prompts, _check_hook_image) and
# speech-QC (CHECKS["SPEECH-QC"]).  Pinned here so that a NEW code appearing
# anywhere in either module is either in the contract or a deliberate,
# reviewed addition to this list -- never an unnoticed third state.
ENGINE_CODES_OFF_THE_COPY_PATH = frozenset(
    {
        "AF-FACE-PROMPT-MISSING",
        "AF-HAIR-INAUTHENTIC",
        "AF-HOOK",
        "AF-HOOK-IMG-MISSING",
        "AF-LIGHT-PROMPT-MISSING",
        "AF-SPEECH-HOOK-COUNT",
        "AF-WORLD-SCALE",
    }
)

_CODE_DICT_RE = re.compile(r"""['"]code['"]\s*:\s*['"](AF-[A-Z0-9-]+)['"]""")


def _contract() -> str:
    return d.ARTIFACT_CONTRACTS["P4-COPY"]


def _prose_half() -> str:
    """The hand-written part of the contract: everything before the generated
    index.  Asserting against THIS is what keeps the test non-vacuous."""
    text = _contract()
    assert d.CONSTRAINT_INDEX_MARKER in text, (
        "the generated constraint index marker is missing from the P4-COPY contract "
        "-- dispatcher._compose_p4_copy_contract did not run"
    )
    return text.split(d.CONSTRAINT_INDEX_MARKER)[0]


def _mentions(code: str, text: str) -> bool:
    """Whole-code match. Plain `in` would let 'AF-HOOK' be satisfied by
    'AF-HOOK-1' and quietly mask a genuinely missing rule."""
    return re.search(re.escape(code) + r"(?![A-Z0-9-])", text) is not None


# ---------------------------------------------------------------------------
# 1. The derivation itself must be alive.  An empty / fallback derivation would
#    make every other assertion below trivially satisfiable.
# ---------------------------------------------------------------------------
class TestDerivationIsHealthy:
    def test_contract_index_was_actually_derived(self):
        assert d.P4_COPY_CONTRACT_DERIVED is True, (
            "the P4-COPY contract fell back to the 'index unavailable' notice: "
            f"{d.P4_COPY_CONTRACT_DERIVATION_ERROR}"
        )
        assert d.P4_COPY_CONTRACT_DERIVATION_ERROR is None

    def test_entry_points_resolve_to_both_engine_checkers(self):
        entries = ci.verifier_entry_points("P4-COPY")
        assert ("intelligence_engines_check", "check_copy") in entries
        assert ("pitch_engines_check", "check_copy") in entries

    def test_derivation_reaches_a_realistic_number_of_checkers(self):
        report = ci.derivation_report()
        # 26 checker functions were visited when this was written. A floor of 20
        # catches a resolver that silently stops following the call graph -- the
        # failure mode that would make an under-derived contract look "clean".
        assert len(report["visited_checkers"]) >= 20, report["visited_checkers"]
        assert report["code_count"] >= 40, report["codes"]
        assert report["registry_size"] >= 180


# ---------------------------------------------------------------------------
# 2. KNOWN-GOOD CONTROL.  The AST resolver's table-dispatch step (CHECKS["1Q"])
#    is the one piece of the derivation that could under-resolve without
#    raising.  Cross-check it against a RUNTIME import of the same module --
#    a genuinely different mechanism reading the same truth.
# ---------------------------------------------------------------------------
class TestKnownGoodControls:
    def test_ast_resolved_1q_checks_match_the_runtime_dict(self):
        import pitch_engines_check as pec  # runtime import: stdlib-only leaf module

        runtime = {fn.__name__ for fn in pec.CHECKS["1Q"]}
        visited: list[str] = []
        ci._walk_checker("pitch_engines_check", "check_copy", "verifier", visited_symbols=visited)
        static = {s.split(".", 1)[1] for s in visited}
        assert runtime <= static, (
            "the AST table-dispatch resolver missed checkers that pitch_engines_check "
            f"really runs at phase 1Q: {sorted(runtime - static)}"
        )

    def test_the_control_can_actually_fail(self):
        """Prove the control above discriminates: a checker that pitch_engines_check
        runs ONLY for SPEECH-QC must NOT be resolved onto the copy path. If this
        assertion ever passes-by-accident (everything resolved), the control above
        is measuring nothing."""
        import pitch_engines_check as pec

        speech_only = {fn.__name__ for fn in pec.CHECKS["SPEECH-QC"]} - {
            fn.__name__ for fn in pec.CHECKS["1Q"]
        }
        assert speech_only, "fixture assumption broken: SPEECH-QC has no exclusive checker"
        visited: list[str] = []
        ci._walk_checker("pitch_engines_check", "check_copy", "verifier", visited_symbols=visited)
        static = {s.split(".", 1)[1] for s in visited}
        assert not (speech_only & static), (
            "the resolver dragged SPEECH-QC-only checkers onto the COPY path: "
            f"{sorted(speech_only & static)}"
        )

    def test_intelligence_engine_entry_point_exists_at_runtime(self):
        import intelligence_engines_check as iec

        assert callable(getattr(iec, "check_copy", None))


# ---------------------------------------------------------------------------
# 3. THE DRIFT TEST.
# ---------------------------------------------------------------------------
class TestContractNamesEveryRuleOnTheJudgingPath:
    def test_every_blocking_code_is_named_in_the_hand_written_prose(self):
        """RED when a rule that BLOCKS P4-COPY exists in the verifier /
        gate / preflight / doctrine path but the contract's own prose never
        names it.  This is the assertion that goes red for a NEW rule."""
        prose = _prose_half()
        blocking = [
            r
            for r in ci.p4_copy_rules()
            if r.code and r.ring in ("verifier", "gate", "preflight", "doctrine")
        ]
        assert blocking, "derived zero blocking rules -- the derivation is broken"
        missing = [(r.code, r.ring, r.source) for r in blocking if not _mentions(r.code, prose)]
        assert not missing, (
            "CONTRACT DRIFT: these rules judge working/copy/slides_copy.md and block "
            "P4-COPY, but ARTIFACT_CONTRACTS['P4-COPY'] never names them in its own "
            "prose. The generated index below the marker is the floor, not a "
            "substitute for telling the author HOW to satisfy a rule. Add a numbered "
            "point for each:\n"
            + "\n".join(f"  {c}  ({ring}, from {src})" for c, ring, src in missing)
        )

    def test_every_derived_code_reaches_the_author_somewhere(self):
        """Weaker but broader: downstream codes (graded by a later phase against
        this same file) must at minimum appear in the generated index."""
        text = _contract()
        missing = [c for c in ci.p4_copy_codes() if not _mentions(c, text)]
        assert not missing, missing

    def test_un_coded_preflight_floors_reach_the_author_too(self):
        """A checker with no registered AF code is still a gate. _chk_slides_copy's
        near-empty floor has no code at all -- exactly the kind of rule that is
        invisible to any code-name-based audit."""
        text = _contract()
        floors = [r for r in ci.p4_copy_rules() if not r.code]
        assert floors, "no un-coded floors derived -- _chk_slides_copy went missing"
        for r in floors:
            checker = r.source.rsplit("::", 1)[-1]
            assert checker in text, f"un-coded floor {checker} never reaches the author"


# ---------------------------------------------------------------------------
# 4. Today's regression, locked.
# ---------------------------------------------------------------------------
class TestSevenLiveRunCodes:
    @pytest.mark.parametrize("code", SEVEN_LIVE_CODES_IN_SCOPE)
    def test_in_scope_live_code_is_named_in_the_prose(self, code):
        assert _mentions(code, _prose_half()), (
            f"{code} auto-failed live run pres-wave-e-v3-1787240658 against "
            "working/copy/slides_copy.md and must be taught in this contract's prose"
        )

    @pytest.mark.parametrize("code", SEVEN_LIVE_CODES_OUT_OF_SCOPE)
    def test_out_of_scope_live_code_is_not_derived_for_this_artifact(self, code):
        """These two judge working/copy/sp_structure.json + sp_intake.json via
        build_deck._chk_sp_no_pitch -> prove_sp_no_pitch.evaluate_paths, which
        never reads slides_copy.md. They belong to P-SP-STRUCTURE's author."""
        assert code not in ci.p4_copy_codes(), (
            f"{code} was derived into P4-COPY's constraint set, but it is judged "
            "against sp_structure.json / sp_intake.json -- files P4-COPY does not "
            "write. Check the scope rule in contract_introspect."
        )

    def test_af_c8_carveout_numbers_are_present_and_sourced_from_doctrine(self):
        prose = _prose_half()
        _, carve_out = ci.af_c8_doctrine()
        # The carve-out must be present VERBATIM, not paraphrased, so amending the
        # ruling in MASTER-QC-AUTOFAIL-RULESET.md propagates without a code edit.
        assert carve_out in prose
        for token in ("30 words max", "9 words", "18 words", "6 items", "7 words", "62 words"):
            assert token in prose, token


# ---------------------------------------------------------------------------
# 5. Module-wide sweep: a NEW code added ANYWHERE in either engine module is
#    either in the contract or a reviewed off-path entry. No third state.
# ---------------------------------------------------------------------------
class TestEngineModuleSweep:
    @pytest.mark.parametrize("mod", ["intelligence_engines_check", "pitch_engines_check"])
    def test_no_unaccounted_code_in_the_engine_modules(self, mod):
        src = ci.module_source(mod)
        found = set(_CODE_DICT_RE.findall(src))
        assert found, f"regex sweep found no codes in {mod} -- the sweep itself is broken"
        text = _contract()
        unaccounted = sorted(
            c for c in found if not _mentions(c, text) and c not in ENGINE_CODES_OFF_THE_COPY_PATH
        )
        assert not unaccounted, (
            f"{mod} can emit codes that are neither in the P4-COPY contract nor listed "
            "in ENGINE_CODES_OFF_THE_COPY_PATH: "
            + ", ".join(unaccounted)
            + ". Either they judge slides_copy.md (teach them in the contract) or they "
            "do not (add them to the off-path list, with a reason)."
        )


# ---------------------------------------------------------------------------
# 6. The scope must stay a SCOPE, not a dump of the whole registry.
# ---------------------------------------------------------------------------
class TestScopingIsDisciplined:
    def test_scope_is_a_small_fraction_of_the_registry(self):
        codes = ci.p4_copy_codes()
        registry = ci.autofail_registry()
        assert 30 <= len(codes) <= 70, len(codes)
        assert len(codes) < len(registry) / 2, (
            f"{len(codes)} of {len(registry)} registered codes -- this stopped being a "
            "scoped constraint set and became a dump"
        )

    def test_no_signature_presentation_structure_codes_leaked_in(self):
        leaked = [c for c in ci.p4_copy_codes() if c.startswith("AF-SP-")]
        assert not leaked, leaked

    def test_index_stays_within_a_sane_prompt_budget(self):
        """P4-COPY's prompt was already retuned once for size (dispatcher's
        _P4_COPY_UPSTREAM_MAX_CHARS = 100_000). The index must not undo that."""
        assert len(ci.render_constraint_index()) < 20_000
