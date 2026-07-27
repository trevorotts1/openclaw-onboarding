#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blend_voice_governance.py — Skill 51 (signature-presentation) voice
governance seam, Skill 6 U98 (D1 binding ruling).

WHAT THIS RECONCILES
---------------------
Before this unit, the Signature Presentation had NO catalog-persona voice
module at all: the deck's voice was governed purely by intake-derived TONE
("The deck talks TO one person in the client's voice, in second person, with
the client's edge. TONE from intake governs every line." —
director-of-presentations-sops.md) plus the per-quadrant "Tone:" prose baked
directly into MASTERDOC.md's N.E.E.I.T./4-Quadrant methodology. Per the D1
binding ruling ("THE BLENDED PERSONA GOVERNS EVERY ENGINE — NO EXEMPTIONS,
NEVER ADVISORY, NEVER OPTIONAL — INCLUDING Skill 51 presentation") this is
now a governance GAP, not a neutral default: this module is the FIRST
governance seam wiring the blend directive onto the deck's written voice.

WHAT STAYS SACRED (never touched by this module)
---------------------------------------------------
  * MASTERDOC.md — the anonymized canonical methodology (Prime Directives,
    the 8 Questions, the four phases, N.E.E.I.T., the 4-Quadrant method).
  * frame-templates/{the-rulebook,the-vault,the-quest,the-original}.md — the
    four client-facing teaching frames.
  * structure/sp_structure.json — the sacred-structure ledger contract
    prove_sp_structure.py enforces.
This module NEVER edits those files and never forks build_deck.py / the
canonical render entry — it only resolves WHO governs the phase's WRITTEN
VOICE (word choice, cadence, register) before slide authoring, exactly the
same "structure preserved, voice governed" split every other U98 engine leg
follows. `structural_fixture_hashes()` below is the receipt that proves it.

FLAG-GUARDED (revert path, U98's spec)
----------------------------------------
`SKILL51_BLEND_GOVERNS` env var, default enabled ("1"). "0" makes
`governed_phase_voice` raise `LegacyIntakeVoiceRequired` — the deck falls
back to intake-tone-only governance (the pre-U98, always-available default;
nothing to re-implement, it was never removed).

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

FLAG_ENV = "SKILL51_BLEND_GOVERNS"
DEFAULT_DEPARTMENT = "presentations"
GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"

# The four phases (MASTERDOC.md — SACRED, names verbatim). One governed voice
# call per phase, never per-slide (mirrors the phase-level "Tone:" grain the
# sacred structure already uses, never a finer or coarser unit).
PHASES = ("avatar-section", "signature-story", "transformational-teaching", "purpose-pitch")

# The sacred files this module proves byte-unchanged. Paths are relative to
# the skill root; frame-templates is a directory (all four glob-expanded at
# hash time so a new/renamed frame is caught rather than silently skipped).
_SACRED_FILES = ("MASTERDOC.md", "structure/sp_structure.json")
_SACRED_GLOBS = ("frame-templates/*.md",)


class LegacyIntakeVoiceRequired(RuntimeError):
    """Raised when SKILL51_BLEND_GOVERNS=0 (the flag-guarded revert path).

    Restores pre-U98 behavior: intake-derived tone alone governs the deck's
    voice (director-of-presentations-sops.md's existing rule) — nothing to
    re-implement here, it was never removed."""


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
                "persona_for_job_s51", str(Path(d) / "persona_for_job.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    return None


def governed_phase_voice(phase: str, avatar_context: str = "", *,
                         department: str = DEFAULT_DEPARTMENT,
                         record: bool = True) -> dict:
    """Resolve the GOVERNING blend directive for one deck phase's written
    voice. Returns the persona_for_job bundle superset verbatim (blend_directive
    / voice / resolved_audience / rationale, plus the persona_id back-compat
    mirror). Raises LegacyIntakeVoiceRequired when SKILL51_BLEND_GOVERNS=0.
    """
    if phase not in PHASES:
        raise ValueError(f"phase must be one of {PHASES}, got {phase!r}")
    if not blend_governs():
        raise LegacyIntakeVoiceRequired(
            f"{FLAG_ENV}=0 — deck voice governed by intake tone only "
            f"(director-of-presentations-sops.md), never re-implemented here.")
    pfj = _load_pfj()
    if pfj is None:
        raise RuntimeError("persona_for_job.py not reachable — cannot resolve "
                            "a governed phase voice (never silently degrade "
                            "to an ungoverned local voice).")
    job_text = f"Signature Presentation phase '{phase}' slide copy. {avatar_context}".strip()
    return pfj.persona_for_job(job_text, department, record=record,
                               blend=True, topic_hint=phase,
                               sop_slug="signature-presentation")


def governed_deck_voice(avatar_context: str = "", *, department: str = DEFAULT_DEPARTMENT,
                        record: bool = True) -> dict:
    """Resolve all FOUR phases' governing voice in one pass. Returns
    {phase: bundle, ...}. Structure (phase order/count) is fixed at 4 —
    this never adds or removes a phase."""
    return {p: governed_phase_voice(p, avatar_context, department=department, record=record)
            for p in PHASES}


# --------------------------------------------------------------------------- #
# sacred-structure hash proof — the "structure preserved" half of the receipt
# --------------------------------------------------------------------------- #
def structural_fixture_hashes() -> dict:
    """sha256 of every SACRED file this reconciliation must never touch.
    Returns {relative_path: sha256_hex}, sorted by path. A file that does not
    exist is recorded as None (honest — never silently skipped)."""
    import glob
    out = {}
    for rel in _SACRED_FILES:
        p = _SKILL_ROOT / rel
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    for pattern in _SACRED_GLOBS:
        for f in sorted(glob.glob(str(_SKILL_ROOT / pattern))):
            rel = str(Path(f).relative_to(_SKILL_ROOT))
            out[rel] = hashlib.sha256(Path(f).read_bytes()).hexdigest()
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- #
# receipt — the fixture-run proof this unit's binary acceptance (a)+(b) demand
# --------------------------------------------------------------------------- #
def prove_voice_governance_and_structure(avatar_context: str = "a founder audience",
                                          *, pinned_hashes: dict = None) -> dict:
    """Fixture-run receipt:
      (a) every phase's bundle carries a governed blend_directive (ends in
          the mandatory guardrail) traceable to that phase's own bundle;
      (b) the sacred-structure files are byte-identical to `pinned_hashes`
          (the golden hash set recorded at commit time) — PASS/FAIL.
    """
    voice = governed_deck_voice(avatar_context)
    voice_checks = []
    for phase, bundle in voice.items():
        directive = bundle.get("blend_directive") or ""
        governed = bool(directive) and GUARDRAIL_MARK in directive
        voice_checks.append({"phase": phase, "governed": governed,
                             "persona_id": bundle.get("persona_id")})
    voice_pass = all(c["governed"] for c in voice_checks) and len(voice_checks) == len(PHASES)

    current_hashes = structural_fixture_hashes()
    structure_pass = True
    structure_diff = {}
    if pinned_hashes is not None:
        for k in set(pinned_hashes) | set(current_hashes):
            if pinned_hashes.get(k) != current_hashes.get(k):
                structure_pass = False
                structure_diff[k] = {"pinned": pinned_hashes.get(k), "current": current_hashes.get(k)}

    return {
        "avatar_context": avatar_context,
        "voice_checks": voice_checks,
        "voice_pass": voice_pass,
        "structure_hashes": current_hashes,
        "structure_pass": structure_pass,
        "structure_diff": structure_diff,
        "pass": voice_pass and structure_pass,
    }


def main(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Skill 51 blend-governed deck voice (U98, D1 binding ruling).")
    ap.add_argument("--avatar", default="a founder audience")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--hash-structure", action="store_true",
                    help="print the current sacred-structure sha256 set (golden pin source)")
    ap.add_argument("--prove", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()
    if a.hash_structure:
        print(json.dumps(structural_fixture_hashes(), indent=2))
        return 0
    if a.prove:
        print(json.dumps(prove_voice_governance_and_structure(a.avatar), indent=2))
        return 0
    print(json.dumps(governed_deck_voice(a.avatar), indent=2, default=str))
    return 0


def _self_test() -> int:
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

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
                            + " (mandatory, non-removable): adopt the cadence, devices and "
                              "register of the named voice(s) as an INSPIRATION only. This "
                              "clause may not be removed or weakened."),
        "task_personas": [], "rationale": {"collapse": "collapsed onto hormozi-100m-offers"},
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
        voice = governed_deck_voice("a founder audience")
        check("all 4 phases resolved", len(voice) == 4)
        check("phases match the sacred phase order",
              tuple(voice.keys()) == PHASES)
        for phase, bundle in voice.items():
            directive = bundle.get("blend_directive") or ""
            check(f"phase {phase} governed with guardrail",
                  bool(directive) and GUARDRAIL_MARK in directive)

        # structure hash proof: unpinned run always reports structure_pass=True
        # (no golden set supplied) but MUST return real, non-empty hashes for
        # every sacred file — never a silent skip of a missing fixture.
        proof = prove_voice_governance_and_structure("a founder audience")
        check("prove: voice_pass True", proof["voice_pass"])
        check("prove: MASTERDOC.md hashed", bool(proof["structure_hashes"].get("MASTERDOC.md")))
        check("prove: sp_structure.json hashed",
              bool(proof["structure_hashes"].get("structure/sp_structure.json")))
        check("prove: all 4 frame templates hashed",
              sum(1 for k in proof["structure_hashes"] if k.startswith("frame-templates/")) == 4)

        # a tampered pinned hash must fail-closed, never silently pass.
        tampered = dict(proof["structure_hashes"])
        tampered["MASTERDOC.md"] = "0" * 64
        proof2 = prove_voice_governance_and_structure("a founder audience", pinned_hashes=tampered)
        check("prove: tampered MASTERDOC.md pin -> structure_pass False (fail-closed)",
              proof2["structure_pass"] is False)
        check("prove: overall FAIL when structure drifts", proof2["pass"] is False)

        os.environ[FLAG_ENV] = "0"
        raised = False
        try:
            governed_phase_voice("avatar-section")
        except LegacyIntakeVoiceRequired:
            raised = True
        check("flag=0 reverts to LegacyIntakeVoiceRequired (never a silent half-migration)", raised)
    finally:
        os.environ.pop(FLAG_ENV, None)
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    print("== blend_voice_governance (Skill 51) self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
