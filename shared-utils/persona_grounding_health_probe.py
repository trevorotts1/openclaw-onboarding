#!/usr/bin/env python3
"""
persona_grounding_health_probe.py — A-U12 (Skill 6 v2 master spec, Section
A.10) "Blend observability" ONB probe.

Master-spec unit A-U12 (crosswalk of master id U12) is a BOTH-REPO unit
("CC (+ ONB probe)"): the Command Center owns the deep-health RESPONSE shape
and the persona_grounding_degraded event/chip; THIS file is the ONB half —
the probe the Command Center's deep-health check shells out to (or a
fleet-refresh step imports) for the underlying signal. It never gates
anything itself (see ADVISORY DOCTRINE below) — that discipline is enforced
by the Command Center's caller, not by this script refusing to run.

WHAT IT REPORTS
----------------
1. `persona_match` — a NON-GATING advisory object built DIRECTLY from
   23-ai-workforce-blueprint/scripts/persona_blend.py's own
   match_score_distribution(): {count, mean, min, max, buckets:{low,mid,
   high}}. This probe never re-implements that arithmetic — it calls the
   real function so it can never disagree with the number the selector
   itself is logging. Per A-U12 Section A.10 (A.1.1): "the JSONL log
   currently has NO reader" — this probe IS the first reader; re-confirmed
   at build time (2026-07 pass): a repo-wide search for
   `match_score_distribution` outside persona_blend.py itself found only
   its own test file and the CHANGELOG — no production caller existed
   before this unit.

2. `grounding` — a degraded/ok verdict for the 5-layer selector's GROUNDING
   layers falling back to their NEUTRAL FLOOR (persona-selector-v2.py):
     - company-config.json absent/unreadable -> `load_company_config()`
       itself warns "Layers 1-3 will fall back to neutral defaults".
     - the semantic_task_fit module not importable -> Layer 5 falls back to
       a flat 0.6 ("module_missing" — the selector's own import-time stub).
   EITHER firing => grounding.degraded=True and
   grounding.event="persona_grounding_degraded" (else event=None). This
   probe reuses the selector's OWN functions/flags for every check (never
   re-implements the detection), so it can never disagree with what the
   live selector itself is doing on this box.

   `llm_score_available` is reported in `layers` as INFORMATIONAL context
   ONLY — it never drives `degraded`/`event`. Traced against
   compute_layer_scores() (persona-selector-v2.py): SCORING_MODE defaults to
   "heuristic" whenever LLM_AVAILABLE is False (line 157), and
   compute_layer_scores() only ever calls the LLM path when BOTH
   `effective == "llm"` AND `LLM_AVAILABLE` are true — so on an
   LLM-unavailable box the real runtime path never reaches the `score_layer`
   stub at all; it always routes to `_heuristic_layer_scores()`, which
   computes REAL keyword-overlap scores against the SAME company-config
   text Layers 1-3 read, not a wholesale flat 0.6. SCORING_MODE=heuristic is
   a first-class, explicitly documented, cheap-and-supported mode ("Cheap,
   no LLM calls" — persona-selector-v2.py `_heuristic_layer_scores`
   docstring), not a broken/degraded state. Treating every heuristic-mode
   box as `persona_grounding_degraded` would be a false-positive noise
   generator fleet-wide, so this probe does not do that.

ADVISORY DOCTRINE (A-U12 accept (a); REVERT note: "nothing gates on them by
design") — BINDING ON EVERY CALLER, ONB AND CC ALIKE:
  - Nothing in this probe's output is a pass/fail boolean for the BOX's
    overall health. `advisory_only: true` is stamped at the top level as an
    explicit, machine-checkable contract marker.
  - The CLI ALWAYS exits 0, deliberately — a non-zero exit would tempt a
    caller into treating an advisory read as a health gate, exactly the
    failure mode A-U12 exists to rule out. Degraded/healthy is conveyed
    ONLY via `grounding.degraded` in the JSON body, never via exit code.
  - Mirrors persona_blend.match_score_distribution()'s own doctrine
    ("never raises, never fabricates a distribution") and
    persona_embedding_drift_probe.py's ("emits exactly ONE result dict per
    run, never one per persona/score") — this file's functions never raise
    into a caller; a failure anywhere inside becomes an honest degraded
    reason, not an exception.

WHAT THIS FILE DOES NOT DO (owned by the Command Center's train, the other
half of this both-repo unit):
  - It does not expose an HTTP endpoint. The Command Center's deep-health
    check (src/lib/health/*) is expected to invoke this script as a
    subprocess (`--json`) exactly as it already does for its other
    box-local checks, and fold `persona_match` + `grounding` into its own
    deep-health response.
  - It does not render a chip or fire a Command-Center board event. It only
    emits the `persona_grounding_degraded` EVENT NAME as a string field —
    the Command Center owns turning that into a board chip/event exactly as
    it already owns `persona_blend_regression` / `persona_mismatch`
    (board-hygiene.ts).

Usage:
    persona_grounding_health_probe.py [--json] [--box LABEL]
                                       [--company-config PATH]
                                       [--coaching-personas DIR]

The match-score log itself can also be pointed at a fixture path directly
via the OPENCLAW_PERSONA_MATCH_SCORE_LOG env var — the same override
persona_blend.py's own log reader/writer already honors (used by this
unit's tests so they never touch a live box).

Exit code: ALWAYS 0. See ADVISORY DOCTRINE above.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.normpath(
    os.path.join(_HERE, "..", "23-ai-workforce-blueprint", "scripts"))
sys.path.insert(0, _HERE)
sys.path.insert(0, _SCRIPTS)

try:
    from detect_platform import get_openclaw_paths as _get_paths  # type: ignore
except Exception:  # pragma: no cover — graceful fallback, mirrors
    # persona_embedding_drift_probe.py's own import-failure posture.
    _get_paths = None


_PERSONA_BLEND_MODULE = None
_SELECTOR_MODULE = None


def _load_persona_blend():
    """Import 23-ai-workforce-blueprint/scripts/persona_blend.py by path
    (cached per-process). This probe NEVER re-implements
    match_score_distribution()'s arithmetic — it calls the real thing so it
    can never disagree with the number the selector itself is logging."""
    global _PERSONA_BLEND_MODULE
    if _PERSONA_BLEND_MODULE is not None:
        return _PERSONA_BLEND_MODULE
    import importlib.util
    path = Path(_SCRIPTS) / "persona_blend.py"
    spec = importlib.util.spec_from_file_location(
        "persona_blend_for_grounding_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    _PERSONA_BLEND_MODULE = mod
    return mod


def _load_selector():
    """Import 23-ai-workforce-blueprint/scripts/persona-selector-v2.py by
    path (cached per-process; hyphenated filename, the same importlib-by-
    path technique the selector's own test suite already uses —
    tests/unit/persona-fallback-invariant.test.py). Reused ONLY for its
    already-shipped grounding signals: load_company_config() (Layers 1-3)
    and the SEMANTIC_AVAILABLE / LLM_AVAILABLE import-time flags (Layer 5 /
    Layers 1-4's LLM path) — never re-implemented here, so this probe can
    never disagree with what the live selector itself would do."""
    global _SELECTOR_MODULE
    if _SELECTOR_MODULE is not None:
        return _SELECTOR_MODULE
    import importlib.util
    path = Path(_SCRIPTS) / "persona-selector-v2.py"
    spec = importlib.util.spec_from_file_location(
        "persona_selector_v2_for_grounding_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    _SELECTOR_MODULE = mod
    return mod


def _hostname() -> str:
    try:
        import socket
        return socket.gethostname().split(".")[0]
    except Exception:
        return "unknown"


def _default_paths() -> dict:
    """Resolve the canonical live paths dict, mirroring
    persona_embedding_drift_probe.py's own fallback doctrine (try the real
    platform detector; fall back to a WORKSPACE_ROOT-relative guess) so this
    probe can never disagree with what the real selector/blend read on a
    live box, and still runs somewhere sane on a bare/CI box."""
    if _get_paths is not None:
        try:
            return _get_paths()
        except (Exception, SystemExit):
            pass
    workspace_root = Path(os.environ.get(
        "WORKSPACE_ROOT", os.path.expanduser("~/.openclaw/workspace")))
    coaching_personas = workspace_root / "data" / "coaching-personas"
    return {
        "coaching_personas": coaching_personas,
        "company_config": coaching_personas.parent / "company-config.json",
    }


def get_persona_match_advisory(paths: dict) -> dict:
    """The `persona_match` advisory object — {count, mean, min, max,
    buckets} — VERBATIM from persona_blend.match_score_distribution(paths).
    Pure read, no mutation, never raises (mirrors
    match_score_distribution's own "never fabricates a distribution"
    doctrine): an absent/unreadable log yields the honest empty state
    (count=0), never a fabricated reading.

    NON-GATING BY DESIGN (A-U12 accept (a)): nothing in this dict is a
    pass/fail boolean — callers must never derive a health verdict from any
    value inside it.
    """
    try:
        pb = _load_persona_blend()
        return pb.match_score_distribution(paths)
    except Exception:
        # Observability must never raise into the caller — an unreadable
        # module/log looks exactly like "no data yet", never a crash.
        return {"count": 0, "mean": None, "min": None, "max": None,
                "buckets": {"low": 0, "mid": 0, "high": 0}}


def check_grounding_layers(paths: dict) -> dict:
    """Detect the 5-layer selector's grounding layers falling back to their
    NEUTRAL FLOOR — the condition A-U12 names `persona_grounding_degraded`:

      - company-config.json absent/unreadable => persona-selector-v2.py's
        own load_company_config() WARNs "Layers 1-3 will fall back to
        neutral defaults".
      - the semantic_task_fit module not importable => Layer 5 falls back
        to a flat 0.6 ('module_missing' — the selector's own import-time
        stub).

    `llm_score_available` is reported in the returned `layers` dict as
    INFORMATIONAL CONTEXT ONLY and never contributes to `degraded`/`event` —
    see the module docstring's "grounding" section for why: an
    LLM-unavailable box always runs the real, non-flat heuristic scoring
    path (SCORING_MODE defaults to "heuristic"), never the flat-0.6 stub, so
    it is not a neutral-floor condition.

    Reuses the selector's OWN functions/flags (never re-implements the
    detection) so this probe can never disagree with what the live selector
    itself is doing. Returns {degraded, event, reasons, layers}. NEVER
    raises into the caller — a failure to even load the selector module is
    itself reported as a degraded reason, not an unhandled exception.
    """
    reasons: list[str] = []
    company_config_present = False
    semantic_available = False
    llm_available = False

    try:
        sel = _load_selector()
        # Reset the selector's process-local company-config cache before
        # every check. In production this probe runs as a fresh CLI process
        # per invocation, so this is a no-op safety net; it matters for a
        # caller that imports this module long-lived (e.g. a test suite
        # re-checking a toggled fixture path at the SAME company_config
        # path) — mirrors the selector's own test suite's
        # _reset_cfg_cache() pattern exactly.
        sel._COMPANY_CONFIG_CACHE = {"path": None, "data": None, "warned": False}
        cfg = sel.load_company_config(paths)
        company_config_present = bool(cfg)
        semantic_available = bool(getattr(sel, "SEMANTIC_AVAILABLE", False))
        llm_available = bool(getattr(sel, "LLM_AVAILABLE", False))
    except Exception as exc:
        # Wording note: deliberately "could not load", never "failed to load".
        # fleet_refresh_runner.run_box decides a box's verdict with a substring
        # test for "failed" over every step value, so an advisory reason that
        # merely used that word would flip the box to partial/failed. The
        # runner scrubs the token defensively too (_scrub_gating_token — {exc}
        # is arbitrary text and can contain anything); this keeps the common
        # case honest and readable rather than silently rewritten.
        reasons.append(f"selector module unavailable/could not load: {exc}")

    layers = {
        "company_config_present": company_config_present,
        "semantic_task_fit_available": semantic_available,
        "llm_score_available": llm_available,
    }

    if not company_config_present:
        reasons.append("company-config.json absent/unreadable -> Layers 1-3 "
                        "fall back to neutral defaults")
    if not semantic_available:
        reasons.append("semantic_task_fit module not importable -> Layer 5 "
                        "falls back to a flat 0.6 (module_missing)")
    # llm_score_available is intentionally NOT a `reasons`/degraded trigger —
    # see check_grounding_layers()'s own docstring above for why (heuristic
    # mode is a real, supported, non-flat scoring path, not a neutral floor).

    degraded = bool(reasons)
    return {
        "degraded": degraded,
        "event": "persona_grounding_degraded" if degraded else None,
        "reasons": reasons,
        "layers": layers,
    }


def run_probe(paths: Optional[dict] = None, box: Optional[str] = None) -> dict:
    """The one entry point — mirrors persona_embedding_drift_probe.py's
    run_drift_check() shape. Returns ONE result dict combining both A-U12
    signals. `advisory_only: True` is the explicit non-gating contract
    marker the Command Center's deep-health caller must honor.
    """
    paths = paths if paths is not None else _default_paths()
    box = box or os.environ.get("OPENCLAW_BOX_LABEL") or _hostname()
    return {
        "probe": "persona-grounding-health",
        "box": box,
        "advisory_only": True,
        "persona_match": get_persona_match_advisory(paths),
        "grounding": check_grounding_layers(paths),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="Machine JSON output")
    ap.add_argument("--box", default=None, help="Box label override")
    ap.add_argument("--company-config", default=None,
                    help="Explicit company-config.json path override")
    ap.add_argument("--coaching-personas", default=None,
                    help="Explicit coaching-personas dir override "
                         "(match-score-log.jsonl lives alongside it; can "
                         "also be overridden directly via the "
                         "OPENCLAW_PERSONA_MATCH_SCORE_LOG env var)")
    args = ap.parse_args()

    paths = _default_paths()
    if args.coaching_personas:
        paths["coaching_personas"] = Path(args.coaching_personas)
    if args.company_config:
        paths["company_config"] = Path(args.company_config)

    result = run_probe(paths=paths, box=args.box)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        pm = result["persona_match"]
        gr = result["grounding"]
        print(f"── persona-grounding-health probe [box: {result['box']}] ──")
        print("  persona_match (advisory, non-gating):")
        print(f"    count={pm['count']} mean={pm['mean']} buckets={pm['buckets']}")
        print(f"  grounding: {'DEGRADED' if gr['degraded'] else 'ok'}")
        if gr["degraded"]:
            for r in gr["reasons"]:
                print(f"    - {r}")
        print("  (advisory only — this probe never gates the box's health status)")

    # ALWAYS exit 0 — see ADVISORY DOCTRINE in the module docstring.
    sys.exit(0)


if __name__ == "__main__":
    main()
