#!/usr/bin/env python3
"""tests/unit/u114-no-exemption-blend-governance-conformance.test.py — U114
(E5-9, closes G3; implements the D1 binding ruling's enforcement half that
U98 adopts). Serialized AFTER U98 on the ONB train (U98 wired the governing
blend IN; U114 removes the old path + pins the invariant), anthology LAST.

WHAT THIS PROVES
-----------------
U98 built the FIRST governance seam for four product-voice engines (Skill 35
social, Skill 51 presentation, Skill 58 podcast, Anthology 54/59 via the
shared tone-writing-core) — each one now resolves its written voice through
`persona_for_job(..., blend=True)`, flag-guarded for an explicit, logged
revert (never a silent fallback). U98's own evidence README named the
remaining gap honestly: "a fleet-wide conformance sweep is U114's job, not
duplicated or pre-empted [t]here" and `tone_persona_autopick.py` says outright
that its decommissioned single-persona call path is "retained behind this
flag UNTIL U114's independent-voice-path invariant lands fleet-wide."

This unit's FIRST ACT (per its own spec's Honesty clause) was reading each
of the four named engines end-to-end to record the precise module + file:line
each engine's voice authority lives at. Findings (grounded, VERIFIED this
pass by direct read):

  * Skill 51 (signature-presentation) — the ONLY voice-selection call site is
    `51-signature-presentation/scripts/blend_voice_governance.py:99-121`
    (`governed_phase_voice`), which routes through the shared U1 seam
    (`shared-utils/persona_for_job.py`, `blend=True`). No OTHER *.py file
    under `51-signature-presentation/` defines a persona/voice-selection
    function or a hardcoded voice table — VERIFIED by direct read of every
    `scripts/*.py` file in the skill (six files total, none of them any
    other candidate). The revert path
    (`blend_voice_governance.py:109-112`, `SKILL51_BLEND_GOVERNS=0`) raises
    `LegacyIntakeVoiceRequired` rather than silently falling back — the
    "local voice path" it restores is `director-of-presentations-sops.md`'s
    pre-existing intake-tone-only rule, an explicit, logged, spec-sanctioned
    LAST-RESORT revert (this unit's own revert clause), never a silent
    exemption.
  * Skill 58 (podcast-production-engine) — the ONLY voice-selection call
    site is `58-podcast-production-engine/scripts/blend_voice_governance.py:
    104-129` (`governed_script_voice`), same U1 seam, `blend=True`. VERIFIED
    by direct read of every `scripts/*.py` file in the skill (24 files
    total plus `webhook/`, `caf/`, `tests/` subtrees — none define an
    independent voice/persona picker). The revert path
    (`blend_voice_governance.py:115-118`, `SKILL58_BLEND_GOVERNS=0`) raises
    `LegacyStyleEngineVoiceRequired`; the restored "local voice path" is the
    selected style engine's own `style-engines/*.md` VOICE DNA section —
    STRUCTURE, pinned byte-identical, sanctioned as the last-resort revert.
  * Anthology (Skills 54/59, via `shared-utils/tone-writing-core/
    tone_persona_autopick.py:90-172`, the ONE seam shared by 52/53/54) — the
    ONLY N/A-slot voice-selection call site. VERIFIED by direct read: no
    file under `54-anthology-writer/scripts/` or `59-anthology-engine/
    scripts/` calls `persona_for_job` directly or defines an independent
    tone/voice picker (Skill 59's `stage_s2_tone.py` is a thin WIRING
    dispatcher that hands off entirely to `54-anthology-writer/
    anthology-entry.sh`, the Layer-1 authoring core; grep-free confirmed via
    direct read, zero `tone_persona_autopick` / `persona_for_job` references
    inside Skill 54's own tree — the shared tone-core is consumed at the
    prompt/SOP layer, not a second in-skill Python call site). The revert
    path (`ANTHOLOGY_BLEND_GOVERNS=0`) restores the byte-for-byte pre-U98
    single-persona shape — explicit, logged (via `record=True`), never
    silent.

CONCLUSION OF THE FIRST-ACT AUDIT: no *additional* rogue/independent
voice-selection module survives beyond the three sanctioned governance seams
U98 already built + their own explicitly-logged, flag-guarded, spec-sanctioned
revert paths (this unit's own revert clause: "reverting an engine restores
its local voice path behind the flag (last resort)"). There is therefore
nothing further to physically delete without touching SACRED structure
(MASTERDOC.md / frame-templates / style-engines/*.md / the shared tone-core
prompts) or without breaking the explicit, honest, already-logged revert
affordance the spec itself sanctions as a last resort. This unit's
DECOMMISSION action is therefore the piece U98 explicitly deferred and
anticipated: the FLEET-WIDE, always-on, CI-enforced NO-EXEMPTION INVARIANT
GUARD proven below — modeled on U95's orchestrator-only invariant guard
(one static scan + one behavioral fixture + one CI-checkable mutation proof,
never advisory) — closing G3 for real by making a *future* rogue
reintroduction fail closed, in CI, automatically.

BINARY ACCEPTANCE COVERED (U114):
  (a) static scan finds ZERO surviving independent voice-selection path
      outside the blend directive, per engine, individually failable.
  (b) behavioral fixture: forcing a DIFFERENT bundle changes the voice,
      traceable to the bundle, for all three concrete seams.
  (c) mutation proof: the guard FAILS on a scratch-tree mutation
      re-introducing a local voice path, then PASSES with it removed.
  (d) each STRUCTURAL golden fixture + prover suite (U98's own, unmodified
      by this unit) passes unchanged.

Run:
    python3 tests/unit/u114-no-exemption-blend-governance-conformance.test.py
    or: pytest tests/unit/u114-no-exemption-blend-governance-conformance.test.py
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------#
# The sanctioned governance seams (per engine) — these, and ONLY these, may
# resolve a product-voice engine's written voice. Any OTHER *.py file in an
# engine's scope that (a) calls persona_for_job(..., blend=False) or (b)
# defines a voice/persona-selection function that never routes through one
# of these sanctioned symbols, or (c) hardcodes a module-level VOICE/PERSONA
# table, is a rogue local-voice path — the static scan below must catch it.
# ---------------------------------------------------------------------------#
SANCTIONED_SYMBOLS = {
    "persona_for_job", "governed_phase_voice", "governed_script_voice",
    "governed_deck_voice", "autopick_slot", "autopick",
    "prove_voice_governance_and_structure", "prove_voice_governance_and_format",
}

# Per-engine scan roots: (label, root dir relative to repo, sanctioned-file
# basenames excluded from the scan because THEY are the seam itself).
ENGINE_SCAN_ROOTS = [
    ("skill51-signature-presentation", "51-signature-presentation/scripts",
     {"blend_voice_governance.py"}),
    ("skill58-podcast-production-engine", "58-podcast-production-engine/scripts",
     {"blend_voice_governance.py"}),
    ("skill54-anthology-writer", "54-anthology-writer/scripts", set()),
    ("skill59-anthology-engine", "59-anthology-engine/scripts", set()),
    ("shared-tone-writing-core", "shared-utils/tone-writing-core",
     {"tone_persona_autopick.py"}),
]

_VOICE_NAME_HINTS = ("voice", "persona", "tone")
_SELECT_NAME_HINTS = ("select", "pick", "choose", "autopick", "resolve")
_TABLE_NAME_HINTS = ("VOICE_DNA", "VOICE_MAP", "PERSONA_MAP", "VOICE_TABLE", "PERSONA_TABLE")


def _iter_py_files(root: Path, exclude_basenames: set):
    if not root.is_dir():
        return
    for p in sorted(root.rglob("*.py")):
        if p.name in exclude_basenames:
            continue
        # never scan the engines' own test trees — tests legitimately
        # reference blend=False fixtures/exception classes by name.
        if "tests" in p.relative_to(root).parts:
            continue
        yield p


def _calls_a_sanctioned_symbol(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if name in SANCTIONED_SYMBOLS:
                return True
    return False


def _find_blend_false_call(tree: ast.AST, relpath: str) -> list:
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if name == "persona_for_job":
                for kw in node.keywords:
                    if kw.arg == "blend" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                        findings.append({
                            "file": relpath, "line": node.lineno,
                            "kind": "persona_for_job(blend=False) outside the sanctioned seam",
                        })
    return findings


def _find_rogue_selector_functions(tree: ast.AST, relpath: str) -> list:
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            lname = node.name.lower()
            looks_like_voice_selector = (
                any(h in lname for h in _VOICE_NAME_HINTS)
                and any(h in lname for h in _SELECT_NAME_HINTS)
            )
            if looks_like_voice_selector and not _calls_a_sanctioned_symbol(node):
                findings.append({
                    "file": relpath, "line": node.lineno,
                    "kind": "voice-selector function %r never routes through a sanctioned seam" % node.name,
                })
    return findings


def _find_hardcoded_voice_tables(tree: ast.AST, relpath: str) -> list:
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Dict,)):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and any(h in tgt.id.upper() for h in _TABLE_NAME_HINTS):
                    findings.append({
                        "file": relpath, "line": node.lineno,
                        "kind": "hardcoded voice/persona table %r outside the sanctioned seam" % tgt.id,
                    })
    return findings


def scan_engine_for_rogue_voice_paths(root: Path, exclude_basenames: set) -> list:
    """Static scan (criterion a). Returns a list of finding dicts; empty ==
    clean (no surviving independent voice-selection path)."""
    findings = []
    for py_file in _iter_py_files(root, exclude_basenames):
        try:
            src = py_file.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(py_file))
        except SyntaxError as exc:
            findings.append({"file": str(py_file), "line": exc.lineno or 0,
                             "kind": "unparsable .py file (cannot prove clean): %s" % exc})
            continue
        relpath = str(py_file)
        findings += _find_blend_false_call(tree, relpath)
        findings += _find_rogue_selector_functions(tree, relpath)
        findings += _find_hardcoded_voice_tables(tree, relpath)
    return findings


# --------------------------------------------------------------------------- #
# (a) static scan — one individually-failable assertion PER ENGINE
# --------------------------------------------------------------------------- #
def test_skill51_static_scan_zero_rogue_voice_paths():
    root = _REPO_ROOT / "51-signature-presentation" / "scripts"
    findings = scan_engine_for_rogue_voice_paths(root, {"blend_voice_governance.py"})
    assert findings == [], "Skill 51 rogue local-voice path(s) found: %r" % findings


def test_skill58_static_scan_zero_rogue_voice_paths():
    root = _REPO_ROOT / "58-podcast-production-engine" / "scripts"
    findings = scan_engine_for_rogue_voice_paths(root, {"blend_voice_governance.py"})
    assert findings == [], "Skill 58 rogue local-voice path(s) found: %r" % findings


def test_skill54_static_scan_zero_rogue_voice_paths():
    root = _REPO_ROOT / "54-anthology-writer" / "scripts"
    findings = scan_engine_for_rogue_voice_paths(root, set())
    assert findings == [], "Skill 54 rogue local-voice path(s) found: %r" % findings


def test_skill59_static_scan_zero_rogue_voice_paths():
    root = _REPO_ROOT / "59-anthology-engine" / "scripts"
    findings = scan_engine_for_rogue_voice_paths(root, set())
    assert findings == [], "Skill 59 rogue local-voice path(s) found: %r" % findings


def test_shared_tone_core_static_scan_zero_rogue_voice_paths():
    root = _REPO_ROOT / "shared-utils" / "tone-writing-core"
    findings = scan_engine_for_rogue_voice_paths(root, {"tone_persona_autopick.py"})
    assert findings == [], "shared tone-writing-core rogue local-voice path(s) found: %r" % findings


# --------------------------------------------------------------------------- #
# (b) behavioral fixture — forcing a DIFFERENT bundle changes the voice,
# traceable to the bundle, for all three concrete governance seams.
# --------------------------------------------------------------------------- #
def _load_by_path(rel_path: str, modname: str):
    import importlib.util
    p = _REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(modname, str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def _fixture(persona_id: str, persona_name: str, topic: str, guardrail: str) -> dict:
    return {
        "persona_id": persona_id, "persona_name": persona_name,
        "mode": "blend", "content_task": True, "topic": topic,
        "resolved_audience": {"source": "confirmed", "candidates": [], "confidence": "high",
                              "label": "founders", "ask": None, "confirm_required": False},
        "confirm_required": False,
        "voice": {"audience_persona": {"id": persona_id, "why": "x"},
                  "topic_persona": {"id": persona_id, "why": "x"},
                  "collapsed": True, "collapsed_persona_id": persona_id,
                  "topic_as_task_guidance": True},
        "blend_directive": ("Write as %s. %s (mandatory, non-removable). "
                            "This clause may not be removed." % (persona_name, guardrail)),
        "task_personas": [], "rationale": {"collapse": "collapsed onto %s" % persona_id},
        "fallbacks": {"default_persona": "blackceo-house-voice", "governance": "covey-7-habits"},
        "catalog_version": "1.3",
    }


GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"


def test_skill51_behavioral_different_bundle_changes_voice():
    import json
    import os
    mod = _load_by_path("51-signature-presentation/scripts/blend_voice_governance.py",
                        "u114_bvg_s51")
    os.environ["SKILL51_BLEND_GOVERNS"] = "1"
    try:
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            _fixture("hormozi-100m-offers", "Hormozi 100M Offers", "avatar-section", GUARDRAIL_MARK))
        bundle_a = mod.governed_phase_voice("avatar-section")

        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            _fixture("goggins-cant-hurt-me", "Goggins Cant Hurt Me", "avatar-section", GUARDRAIL_MARK))
        bundle_b = mod.governed_phase_voice("avatar-section")

        assert bundle_a["persona_id"] != bundle_b["persona_id"], \
            "forcing a different bundle must change the resolved persona_id: %r vs %r" % (bundle_a, bundle_b)
        assert bundle_a["blend_directive"] != bundle_b["blend_directive"], \
            "forcing a different bundle must change the written blend_directive"
        assert "Hormozi" in bundle_a["blend_directive"] and "Hormozi" not in bundle_b["blend_directive"]
        assert "Goggins" in bundle_b["blend_directive"] and "Goggins" not in bundle_a["blend_directive"]
        assert bundle_a["voice"]["collapsed_persona_id"] == bundle_a["persona_id"], \
            "voice must trace to ITS OWN bundle, never the other call's"
        assert bundle_b["voice"]["collapsed_persona_id"] == bundle_b["persona_id"]
    finally:
        os.environ.pop("SKILL51_BLEND_GOVERNS", None)
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


def test_skill58_behavioral_different_bundle_changes_voice():
    import json
    import os
    mod = _load_by_path("58-podcast-production-engine/scripts/blend_voice_governance.py",
                        "u114_bvg_s58")
    os.environ["SKILL58_BLEND_GOVERNS"] = "1"
    try:
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            _fixture("hormozi-100m-offers", "Hormozi 100M Offers", "Counter Intuitive", GUARDRAIL_MARK))
        bundle_a = mod.governed_script_voice("counter_intuitive")

        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            _fixture("goggins-cant-hurt-me", "Goggins Cant Hurt Me", "Counter Intuitive", GUARDRAIL_MARK))
        bundle_b = mod.governed_script_voice("counter_intuitive")

        assert bundle_a["persona_id"] != bundle_b["persona_id"]
        assert bundle_a["blend_directive"] != bundle_b["blend_directive"]
        assert bundle_a["voice"]["collapsed_persona_id"] == bundle_a["persona_id"]
        assert bundle_b["voice"]["collapsed_persona_id"] == bundle_b["persona_id"]
    finally:
        os.environ.pop("SKILL58_BLEND_GOVERNS", None)
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


def test_anthology_behavioral_different_bundle_changes_voice():
    import json
    import os
    tpa = _load_by_path("shared-utils/tone-writing-core/tone_persona_autopick.py",
                        "u114_tpa")
    os.environ.pop("ANTHOLOGY_BLEND_GOVERNS", None)  # default -> governs
    try:
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            _fixture("covey-7-habits", "Covey", "brand voice tone analysis", GUARDRAIL_MARK))
        bundle_a = tpa.autopick_slot("N/A", "an audience of ambitious founders")

        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            _fixture("hormozi-100m-offers", "Hormozi 100M Offers", "brand voice tone analysis", GUARDRAIL_MARK))
        bundle_b = tpa.autopick_slot("N/A", "an audience of ambitious founders")

        assert bundle_a["persona_id"] != bundle_b["persona_id"], \
            "N/A slot must resolve a DIFFERENT persona_id when the governing bundle differs"
        assert bundle_a["blend_directive"] != bundle_b["blend_directive"]
        assert bundle_a["voice"]["collapsed_persona_id"] == bundle_a["persona_id"]
        assert bundle_b["voice"]["collapsed_persona_id"] == bundle_b["persona_id"]
    finally:
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


# --------------------------------------------------------------------------- #
# (c) mutation proof — the guard FAILS on a scratch-tree mutation
# re-introducing a local voice path, then PASSES with it removed.
# --------------------------------------------------------------------------- #
_ROGUE_MODULE_SOURCE = '''\
"""rogue_voice_picker.py — scratch-tree mutation fixture, U114 mutation proof.
A hand-authored, hardcoded voice table + a selector function that NEVER
routes through any sanctioned governance seam. This file must never exist
on a real branch; it exists ONLY inside a throwaway tempdir for this test.
"""

PERSONA_MAP = {
    "counter_intuitive": "Some Hardcoded Voice",
    "vulnerable": "Another Hardcoded Voice",
}


def select_voice_for_engine(engine_id):
    """Rogue: returns a hardcoded voice, never consults the blend directive."""
    return PERSONA_MAP.get(engine_id, "default hardcoded voice")
'''


def test_mutation_proof_guard_fails_closed_then_passes_clean():
    """Binary acceptance (c): write a rogue local-voice module into a SCRATCH
    copy of one engine's scripts/ tree, prove the static scanner FAILS
    (finds it) — then delete it and prove the scanner PASSES again. Never
    touches the real repo tree; this is the guard's own self-proof that it
    is genuinely failable, not a hollow always-green check."""
    real_root = _REPO_ROOT / "58-podcast-production-engine" / "scripts"
    tmp_root = Path(tempfile.mkdtemp(prefix="u114-mutation-proof-"))
    try:
        scratch = tmp_root / "scripts"
        shutil.copytree(real_root, scratch, ignore=shutil.ignore_patterns("tests", "__pycache__"))

        clean = scan_engine_for_rogue_voice_paths(scratch, {"blend_voice_governance.py"})
        assert clean == [], "scratch copy of Skill 58 scripts/ must start clean: %r" % clean

        rogue_file = scratch / "rogue_voice_picker.py"
        rogue_file.write_text(_ROGUE_MODULE_SOURCE, encoding="utf-8")

        mutated = scan_engine_for_rogue_voice_paths(scratch, {"blend_voice_governance.py"})
        assert mutated != [], (
            "MUTATION PROOF FAILED: the guard did not detect a hand-planted rogue "
            "local-voice module (PERSONA_MAP + select_voice_for_engine never "
            "routing through a sanctioned seam) — the guard would be hollow.")
        assert any("rogue_voice_picker.py" in f["file"] for f in mutated), \
            "the finding must point at the planted rogue file: %r" % mutated

        rogue_file.unlink()
        healed = scan_engine_for_rogue_voice_paths(scratch, {"blend_voice_governance.py"})
        assert healed == [], "guard must PASS again once the rogue module is removed: %r" % healed
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


# --------------------------------------------------------------------------- #
# (d) STRUCTURAL golden fixtures + prover suites pass UNCHANGED — this unit
# never edits U98's governance modules, the sacred structure, or the shared
# tone-core; re-running U98's own full proof + the per-engine self-tests +
# the tone-core sync provers is the regression receipt.
# --------------------------------------------------------------------------- #
def _run(argv, timeout=180):
    return subprocess.run(argv, capture_output=True, text=True, cwd=str(_REPO_ROOT), timeout=timeout)


def test_u98_golden_suite_passes_unchanged():
    proc = _run([sys.executable or "python3",
                "tests/unit/u98-blend-governs-product-voice-engines.test.py"])
    assert proc.returncode == 0, (
        "U98's own golden proof suite must pass UNCHANGED after U114:\n%s%s"
        % (proc.stdout, proc.stderr))


def test_per_engine_self_tests_pass_unchanged():
    checks = [
        ["51-signature-presentation/scripts/blend_voice_governance.py", "--self-test"],
        ["58-podcast-production-engine/scripts/blend_voice_governance.py", "--self-test"],
        ["shared-utils/tone-writing-core/tone_persona_autopick.py", "--self-test"],
    ]
    for rel_argv in checks:
        proc = _run([sys.executable or "python3"] + rel_argv)
        assert proc.returncode == 0, (
            "%s must self-test clean, unchanged by U114:\n%s%s"
            % (rel_argv[0], proc.stdout, proc.stderr))


def test_tone_core_sync_provers_pass_unchanged():
    for skill_dir in ("52-avatar-alchemist", "53-book-writer", "54-anthology-writer"):
        script = _REPO_ROOT / skill_dir / "scripts" / "verify_tone_core_sync.py"
        assert script.is_file(), "expected %s missing" % script
        proc = _run([sys.executable or "python3", str(script)])
        assert proc.returncode == 0, (
            "%s tone-core structure drifted (AF-AW-TONE-DRIFT) — U114 must never "
            "touch prompts/04..08:\n%s%s" % (skill_dir, proc.stdout, proc.stderr))


_ALL_TESTS = [
    test_skill51_static_scan_zero_rogue_voice_paths,
    test_skill58_static_scan_zero_rogue_voice_paths,
    test_skill54_static_scan_zero_rogue_voice_paths,
    test_skill59_static_scan_zero_rogue_voice_paths,
    test_shared_tone_core_static_scan_zero_rogue_voice_paths,
    test_skill51_behavioral_different_bundle_changes_voice,
    test_skill58_behavioral_different_bundle_changes_voice,
    test_anthology_behavioral_different_bundle_changes_voice,
    test_mutation_proof_guard_fails_closed_then_passes_clean,
    test_u98_golden_suite_passes_unchanged,
    test_per_engine_self_tests_pass_unchanged,
    test_tone_core_sync_provers_pass_unchanged,
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
    print("== U114 no-exemption blend-governance conformance proof: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
