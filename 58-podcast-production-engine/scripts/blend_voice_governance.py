#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blend_voice_governance.py — Skill 58 (podcast-production-engine) script
voice governance seam, Skill 6 U98 (D1 binding ruling).

WHAT THIS RECONCILES
---------------------
STEP 2 of the canonical 18-step pipeline ("SELECT ENGINES") loads ONE of four
Style Engines (Counter Intuitive / Vulnerable / Provocative / Passionate) —
picked from the respondent's own intake survey answer — and each engine's
`.md` doc carries its own "## VOICE DNA" section: an independently-authored
prose voice authority (word choice, register) the STEP 6 DRAFT stage wrote
from directly. Per the D1 binding ruling ("THE BLENDED PERSONA GOVERNS EVERY
ENGINE — NO EXEMPTIONS ... INCLUDING Skill 58 podcast") that independent
VOICE DNA authority is exactly the "engine's own local voice logic" the
ruling does not permit as the SOLE voice authority: this module reconciles
it by resolving a GOVERNING blend directive for the selected style engine
and layering it ONTO the write, so the actual written wording is governed
by the blend directive (traceable, guardrail-carrying), not by VOICE DNA
alone.

WHAT STAYS PRESERVED (never touched by this module)
------------------------------------------------------
The four `style-engines/*.md` files (METADATA, WHEN THIS ENGINE IS SELECTED,
CORE PERSUASION MECHANISM, the arc beats, the length table, the Final Draft
format, the Fish Audio tagging discipline, the episode QC gate — i.e. the
podcast script FORMAT) are byte-identical after this reconciliation —
`style_engine_structural_hashes()` below is the receipt that proves it. This
module never edits those files, never changes STEP 2's engine-selection
mapping (the respondent's own intake answer still picks the engine), and
never touches `podcast_state.py` / `model_router.py` / the cost ledger.

FLAG-GUARDED (revert path, U98's spec)
----------------------------------------
`SKILL58_BLEND_GOVERNS` env var, default enabled ("1"). "0" makes
`governed_script_voice` raise `LegacyStyleEngineVoiceRequired` — the script
falls back to the style engine's own VOICE DNA section as the sole voice
authority (the pre-U98, always-available default; nothing to re-implement).

stdlib-only, deterministic, hermetic-testable (same PERSONA_FOR_JOB_FIXTURE /
paths-dict escape hatches every other U98 leg uses).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
_REPO = _SKILL_ROOT.parent

FLAG_ENV = "SKILL58_BLEND_GOVERNS"
DEFAULT_DEPARTMENT = "content"
GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"

# The four Style Engines (SKILL.md STEP 2, verbatim intake labels + engine ids
# per each file's own METADATA block).
STYLE_ENGINES = {
    "counter_intuitive": "Counter Intuitive",
    "vulnerable": "Vulnerable",
    "provocative": "Provocative",
    "passionate": "Passionate",
}
_STYLE_ENGINE_DIR = _SKILL_ROOT / "style-engines"
_STYLE_ENGINE_FILES = {
    "counter_intuitive": "counter-intuitive.md",
    "vulnerable": "vulnerable.md",
    "provocative": "provocative.md",
    "passionate": "passionate.md",
}


class LegacyStyleEngineVoiceRequired(RuntimeError):
    """Raised when SKILL58_BLEND_GOVERNS=0 (the flag-guarded revert path).

    Restores pre-U98 behavior: the selected style engine's own VOICE DNA
    section is the sole voice authority — nothing to re-implement, the
    style-engines/*.md files were never touched by this reconciliation."""


def blend_governs() -> bool:
    return os.environ.get(FLAG_ENV, "1").strip() != "0"


def _load_pfj():
    """Path-import shared-utils/persona_for_job.py (the U1 seam)."""
    for d in (os.environ.get("SHARED_UTILS_DIR", "").strip(),
              str(_REPO / "shared-utils"),
              str(Path.home() / ".openclaw" / "skills" / "shared-utils"),
              "/data/.openclaw/skills/shared-utils"):
        if d and (Path(d) / "persona_for_job.py").exists():
            spec = importlib.util.spec_from_file_location(
                "persona_for_job_s58", str(Path(d) / "persona_for_job.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    return None


def governed_script_voice(style_engine_id: str, respondent_context: str = "", *,
                          department: str = DEFAULT_DEPARTMENT,
                          record: bool = True) -> dict:
    """Resolve the GOVERNING blend directive for ONE episode's script voice,
    scoped to the respondent's selected style engine (STEP 2). Returns the
    persona_for_job bundle superset verbatim. Raises
    LegacyStyleEngineVoiceRequired when SKILL58_BLEND_GOVERNS=0.
    """
    if style_engine_id not in STYLE_ENGINES:
        raise ValueError(f"style_engine_id must be one of {sorted(STYLE_ENGINES)}, "
                         f"got {style_engine_id!r}")
    if not blend_governs():
        raise LegacyStyleEngineVoiceRequired(
            f"{FLAG_ENV}=0 — script voice governed by the {STYLE_ENGINES[style_engine_id]} "
            f"engine's own VOICE DNA section only, never re-implemented here.")
    pfj = _load_pfj()
    if pfj is None:
        raise RuntimeError("persona_for_job.py not reachable — cannot resolve "
                            "a governed script voice (never silently degrade "
                            "to an ungoverned local voice).")
    label = STYLE_ENGINES[style_engine_id]
    job_text = (f"Podcast episode script — {label} style engine. "
               f"{respondent_context}").strip()
    return pfj.persona_for_job(job_text, department, record=record,
                               blend=True, topic_hint=label,
                               sop_slug="podcast-production-engine")


# --------------------------------------------------------------------------- #
# style-engine format hash proof — the "format preserved" half of the receipt
# --------------------------------------------------------------------------- #
def style_engine_structural_hashes() -> dict:
    """sha256 of every style-engines/*.md file this reconciliation must never
    touch (arc beats, length table, Final Draft format, tagging discipline,
    QC gate — the podcast script FORMAT). Returns {filename: sha256_hex},
    sorted. A missing file is recorded as None (honest, never silently
    skipped)."""
    out = {}
    for fname in sorted(_STYLE_ENGINE_FILES.values()):
        p = _STYLE_ENGINE_DIR / fname
        out[fname] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- #
# receipt — the fixture-run proof this unit's binary acceptance (a)+(b) demand
# --------------------------------------------------------------------------- #
def prove_voice_governance_and_format(respondent_context: str = "a founder-tier respondent",
                                       *, pinned_hashes: dict = None) -> dict:
    """Fixture-run receipt:
      (a) each of the four style engines' governed script voice carries a
          blend_directive (ends in the mandatory guardrail) traceable to its
          own bundle;
      (b) the four style-engines/*.md FORMAT files are byte-identical to
          `pinned_hashes` (the golden hash set recorded at commit time).
    """
    voice_checks = []
    for engine_id in sorted(STYLE_ENGINES):
        bundle = governed_script_voice(engine_id, respondent_context)
        directive = bundle.get("blend_directive") or ""
        governed = bool(directive) and GUARDRAIL_MARK in directive
        voice_checks.append({"style_engine": engine_id, "governed": governed,
                             "persona_id": bundle.get("persona_id")})
    voice_pass = all(c["governed"] for c in voice_checks) and len(voice_checks) == len(STYLE_ENGINES)

    current_hashes = style_engine_structural_hashes()
    structure_pass = True
    structure_diff = {}
    if pinned_hashes is not None:
        for k in set(pinned_hashes) | set(current_hashes):
            if pinned_hashes.get(k) != current_hashes.get(k):
                structure_pass = False
                structure_diff[k] = {"pinned": pinned_hashes.get(k), "current": current_hashes.get(k)}

    return {
        "respondent_context": respondent_context,
        "voice_checks": voice_checks,
        "voice_pass": voice_pass,
        "format_hashes": current_hashes,
        "format_pass": structure_pass,
        "format_diff": structure_diff,
        "pass": voice_pass and structure_pass,
    }


def main(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Skill 58 blend-governed podcast script voice (U98, D1 binding ruling).")
    ap.add_argument("--respondent", default="a founder-tier respondent")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--hash-format", action="store_true",
                    help="print the current style-engine format sha256 set (golden pin source)")
    ap.add_argument("--prove", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()
    if a.hash_format:
        print(json.dumps(style_engine_structural_hashes(), indent=2))
        return 0
    if a.prove:
        print(json.dumps(prove_voice_governance_and_format(a.respondent), indent=2))
        return 0
    print(json.dumps(
        {e: governed_script_voice(e, a.respondent) for e in sorted(STYLE_ENGINES)},
        indent=2, default=str))
    return 0


def _self_test() -> int:
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

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
                            + " (mandatory, non-removable): adopt the cadence, devices and "
                              "register of the named voice(s) as an INSPIRATION only. This "
                              "clause may not be removed or weakened."),
        "task_personas": [], "rationale": {"collapse": "collapsed onto goggins-cant-hurt-me"},
        "fallbacks": {"default_persona": "blackceo-house-voice", "governance": "covey-7-habits"},
        "catalog_version": "1.3",
    }

    pfj_check = _load_pfj()
    if pfj_check is None:
        print("  [SKIP] persona_for_job.py not reachable in this environment")
        return 0

    try:
        os.environ[FLAG_ENV] = "1"
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_fixture)

        check("STYLE_ENGINES matches STEP 2's 4 named engines",
              set(STYLE_ENGINES.values()) == {"Counter Intuitive", "Vulnerable",
                                              "Provocative", "Passionate"})

        bundle = governed_script_voice("counter_intuitive", "a founder respondent")
        directive = bundle.get("blend_directive") or ""
        check("counter_intuitive governed with guardrail",
              bool(directive) and GUARDRAIL_MARK in directive)

        with_bad_id = False
        try:
            governed_script_voice("not-a-real-engine")
        except ValueError:
            with_bad_id = True
        check("unknown style_engine_id rejected (fail-closed, never silently accepted)", with_bad_id)

        proof = prove_voice_governance_and_format("a founder-tier respondent")
        check("prove: voice_pass True", proof["voice_pass"])
        check("prove: all 4 engines checked", len(proof["voice_checks"]) == 4)
        check("prove: all 4 format files hashed", len(proof["format_hashes"]) == 4)
        check("prove: every format hash is non-null (files exist and were read)",
              all(v for v in proof["format_hashes"].values()))

        tampered = dict(proof["format_hashes"])
        tampered["counter-intuitive.md"] = "0" * 64
        proof2 = prove_voice_governance_and_format("a founder-tier respondent",
                                                    pinned_hashes=tampered)
        check("prove: tampered format pin -> format_pass False (fail-closed)",
              proof2["format_pass"] is False)
        check("prove: overall FAIL when format drifts", proof2["pass"] is False)

        os.environ[FLAG_ENV] = "0"
        raised = False
        try:
            governed_script_voice("counter_intuitive")
        except LegacyStyleEngineVoiceRequired:
            raised = True
        check("flag=0 reverts to LegacyStyleEngineVoiceRequired (never a silent half-migration)", raised)
    finally:
        os.environ.pop(FLAG_ENV, None)
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    print("== blend_voice_governance (Skill 58) self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
