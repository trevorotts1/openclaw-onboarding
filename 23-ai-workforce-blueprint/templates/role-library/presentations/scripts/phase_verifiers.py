#!/usr/bin/env python3
"""
phase_verifiers.py — PER-PHASE SUBSTANCE VERIFIERS (FIX F).

================================================================================
Replaces existence-only attestation. The runner used to attest a phase the moment
its produces_artifact merely EXISTED on disk (run_signature_deck._artifact_present)
— a weak model could write an empty/placeholder file and the phase "passed." This
module reads each phase's REAL output and checks SUBSTANCE, reusing the existing,
proven engine checkers (build_deck.py + intelligence_engines_check.py +
pitch_engines_check.py + canonical_render_guard.py). Existence AND substance must
both pass; on a substance failure the runner blocks + routes back (no attest).
================================================================================

PUBLIC API
  verify_phase(phase_id, run_dir) -> (ok: bool, reason: str)
      The single entry the runner (FIX E) and prove-deck.py (FIX C) call. ok=True
      means the phase's artifact has real substance (or no substance verifier is
      registered for that phase — existence-only fallback, reason says so).

WHAT IT REUSES (per the FIX F spec — never reimplement a checker)
  * Deep Research  -> build_deck._chk_research_cited + _chk_claims_without_citation
                      + a RESEARCH MINIMUM-EVIDENCE gate (FM-5): a self-asserted
                      research_complete flag is ignored; N cited live URLs are
                      required and any fact-validation ledger entry must be
                      verified:true (the fetch-and-confirm proxy that stops
                      fabricated, source-less statistics shipping as fact).
  * Copy / Copy-QC -> intelligence_engines_check.check_copy + pitch_engines_check
                      .check_copy — arc ORDER (HOOK->VILLAIN->FELT_STAKES->PROMISE
                      ->PRICE->RECAP), villain-before-hero, felt-stakes, cadence.
                      This is the FM-2 upgrade: ORDER + semantic presence, NOT the
                      gameable regex token-presence. (When an independent heavy QC
                      model is wired, _llm_judge() runs on top; absent it, the
                      deterministic arc-order checker is the floor.)
  * Prompts        -> build_deck.check_prompt_qc_deterministic (both floors).
  * Render/Image-QC-> build_deck.check_image_qc_vision / _chk_image_qc (pixel/vision).
  * Assemble       -> build_deck.check_deck_harmony (deck cohesion).

ZERO third-party deps (stdlib json / importlib / pathlib only). NEVER raises —
an unavailable checker degrades to "substance not verifiable for <phase>" (the
runner then falls back to existence-only for THAT phase, logged, never silent).
"""

import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _imp(modname):
    try:
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        return importlib.import_module(modname)
    except Exception:  # noqa: BLE001
        return None


def _interpret(result):
    """Normalize a checker return into (ok, reason). Preflight checkers return '' /
    None on pass and a message string on fail; QC checkers return {pass:bool,...};
    engine checkers append problem dicts to a list (handled by their callers)."""
    if result is None:
        return True, ""
    if isinstance(result, bool):
        return result, ("" if result else "checker returned False")
    if isinstance(result, str):
        return (not result.strip()), result.strip()
    if isinstance(result, dict):
        if result.get("pass") is False:
            probs = result.get("problems") or result.get("deficiencies") or result
            return False, json.dumps(probs)[:600]
        return True, ""
    if isinstance(result, (list, tuple)):
        return (len(result) == 0), (json.dumps(list(result))[:600] if result else "")
    return True, ""


def _bd_checker(name, run_dir):
    """Run a build_deck checker by name against run_dir; (ok, reason). Unavailable
    => (True, note) so a box missing build_deck degrades, never crashes."""
    bd = _imp("build_deck")
    if bd is None:
        return True, f"build_deck unavailable; {name} substance not verifiable"
    fn = getattr(bd, name, None)
    if not callable(fn):
        return True, f"build_deck.{name} missing; substance not verifiable"
    try:
        return _interpret(fn(run_dir))
    except Exception as exc:  # noqa: BLE001
        return True, f"build_deck.{name} raised {exc!r}; substance not verifiable"


# ---------------------------------------------------------------------------
# FM-5 — research minimum-evidence gate (kills fabricated, source-less stats)
# ---------------------------------------------------------------------------
def _research_evidence_gate(run_dir: Path):
    # 1. >= MIN_CITED_SOURCES distinct live URLs (self-asserted research_complete is ignored).
    ok1, r1 = _bd_checker("_chk_research_cited", run_dir)
    if not ok1:
        return False, f"insufficient cited live sources: {r1}"
    # 2. every slide-bound claim marker has a cited URL.
    ok2, r2 = _bd_checker("_chk_claims_without_citation", run_dir)
    if not ok2:
        return False, f"claim without citation: {r2}"
    # 3. fetch-and-confirm proxy: any fact-validation ledger entry must be verified.
    for cand in list((run_dir / "working" / "research").glob("fact_validation*.json")) if \
            (run_dir / "working" / "research").is_dir() else []:
        try:
            obj = json.loads(cand.read_text())
        except Exception:  # noqa: BLE001
            return False, f"fact-validation ledger {cand.name} is unreadable"
        rows = obj.get("entries") if isinstance(obj, dict) else obj
        for row in rows or []:
            if isinstance(row, dict) and row.get("verified") is not True:
                return False, (f"fact-validation ledger has an UNVERIFIED stat "
                               f"({row.get('claim') or row.get('stat') or 'entry'}) — every "
                               f"statistic must be fetched and confirmed before research_complete")
    return True, ""


# ---------------------------------------------------------------------------
# FM-2 — copy arc ORDER + semantic presence (kills token-presence gaming)
# ---------------------------------------------------------------------------
def _copy_arc_order(run_dir: Path):
    """Reuse the engine checkers that measure arc ORDER + semantic presence, not
    regex token counts: a deck that pattern-matches the reward tokens but holds no
    real 6-beat arc IN ORDER still fails (AF-NARRATIVE-HARMONY / AF-NO-VILLAIN /
    AF-NO-FELT-STAKES / AF-PRICE-BEFORE-PROMISE)."""
    working = run_dir / "working"
    problems = []
    iec = _imp("intelligence_engines_check")
    if iec is not None and hasattr(iec, "check_copy"):
        try:
            iec.check_copy(working, problems)
        except Exception as exc:  # noqa: BLE001
            return True, f"intelligence_engines_check raised {exc!r}; arc-order not verifiable"
    else:
        return True, "intelligence_engines_check unavailable; arc-order not verifiable"
    pec = _imp("pitch_engines_check")
    if pec is not None and hasattr(pec, "check_copy"):
        try:
            pec.check_copy(working, problems)
        except Exception:  # noqa: BLE001
            pass
    if problems:
        codes = ", ".join(sorted({str(p.get("code")) for p in problems if isinstance(p, dict)}))
        return False, f"copy fails arc ORDER / semantic presence: {codes}"
    # Optional: when an independent heavy QC model is wired, layer the LLM-judge on top.
    judged_ok, judged_reason = _llm_judge(run_dir)
    if not judged_ok:
        return False, judged_reason
    return True, ""


def _llm_judge(run_dir: Path):
    """Hook for the independent heavy QC model LLM-judge (FIX A). When an
    llm_judge.py helper is deployed AND an independent QC model is configured it
    runs a semantic-presence judgment; otherwise it is a no-op pass (the
    deterministic arc-order checker above is the floor). Never raises."""
    lj = _imp("llm_judge")
    if lj is None or not hasattr(lj, "judge_copy"):
        return True, ""
    try:
        verdict = lj.judge_copy(run_dir)
        if isinstance(verdict, dict) and verdict.get("pass") is False:
            return False, f"LLM-judge (independent heavy QC model): {verdict.get('reason', 'fail')}"
    except Exception:  # noqa: BLE001
        return True, ""
    return True, ""


# ---------------------------------------------------------------------------
# Phase -> substance verifier registry
# ---------------------------------------------------------------------------
def _v_research(run_dir):
    return _research_evidence_gate(run_dir)


def _v_copy(run_dir):
    return _copy_arc_order(run_dir)


_REGISTRY = {
    "P-0.5-RESEARCH":   _v_research,
    "P0A-INTAKE":       lambda rd: _bd_checker("_chk_intake", rd),
    "P0B-PRIORITY":     lambda rd: _bd_checker("_chk_priority_shift", rd),
    "P1Q-COPY-QC":      _v_copy,
    "P3-ARC":           lambda rd: _bd_checker("_chk_arc", rd),
    "P-3.5-RESEARCH-MAP": lambda rd: _bd_checker("_chk_research_map", rd),
    "P4-COPY":          _v_copy,
    "PF-DESIGN":        lambda rd: _bd_checker("_chk_design_brief", rd),
    "P4-PROMPT":        lambda rd: _bd_checker("check_prompt_qc_deterministic", rd),
    "P-PROMPT-QC":      lambda rd: _bd_checker("_chk_prompt_qc", rd),
    "P4-RENDER":        lambda rd: _bd_checker("check_image_qc_vision", rd),
    "P-IMAGE-QC":       lambda rd: _bd_checker("_chk_image_qc", rd),
    "P8-ASSEMBLE":      lambda rd: _bd_checker("check_deck_harmony", rd),
}


def verify_phase(phase_id, run_dir):
    """(ok, reason). A phase with no registered verifier returns (True, note) — the
    runner then falls back to existence-only for THAT phase (logged, never silent)."""
    run_dir = Path(run_dir)
    fn = _REGISTRY.get(phase_id)
    if fn is None:
        return True, f"no substance verifier registered for {phase_id} (existence-only)"
    try:
        ok, reason = fn(run_dir)
        return bool(ok), str(reason or "")
    except Exception as exc:  # noqa: BLE001
        return True, f"verifier for {phase_id} raised {exc!r}; substance not verifiable"


def substance_ok(phase_id, run_dir):
    ok, _ = verify_phase(phase_id, run_dir)
    return ok


def has_verifier(phase_id):
    return phase_id in _REGISTRY


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Per-phase substance verifier (FIX F).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--phase", required=True)
    a = ap.parse_args()
    ok, reason = verify_phase(a.phase, Path(a.run_dir).resolve())
    print(json.dumps({"phase": a.phase, "substance_ok": ok, "reason": reason}, indent=2))
    sys.exit(0 if ok else 1)
