#!/usr/bin/env python3
"""Launch-plan sidecars for the dispatch path that does NOT go through the launcher.

WHY THIS EXISTS. FIX 11's launch record -- `.mode-plan.json` (which mode this
run is in, at what concurrency, under what ceiling) and `.model-plan.json` (the
routing stamp: which model fills each slot, and the thinking level) -- is
written by launcher.dispatch(). But the intake poller has TWO dispatch branches
and only one of them is the launcher:

    --resume  ->  python3 -m presentation_job.launcher --resume ...   (launcher)
    --new     ->  python3 presentation_job.py --new, then --run       (NOT the launcher)

The --new branch is the one a FRESH client intake takes. It calls the engine
entry directly -- that entry has no --mode flag by design, and the run-mode axis
is deliberately not a flag on the canonical entry either -- so before this
module existed, a fresh client intake that declared ULTRA would correctly RUN
ultra and leave NO EVIDENCE that it had. The mode governed but was unauditable,
which is the one thing worse than it not governing: "ultra was on" becomes an
unverifiable claim exactly where proof was demanded.

This module writes the same two sidecars, in the same shape, for that branch.

WHY IT DUPLICATES THE LAUNCHER'S WRITER INSTEAD OF SHARING IT. The SUBSTANCE is
not duplicated: every value below comes from the same model_router authority the
launcher calls (mode_plan, mode_ceiling, plan_report, resolve_route). What is
restated is the assembly -- roughly a dozen lines. Sharing the assembly would
mean refactoring launcher.dispatch(), and the two callers genuinely differ:

  * the launcher has inputs this path does not (plan_calls and estimate_usd from
    the FIX 12 credit preflight, which does not run on the poller's --new
    branch), so the records can never be byte-identical anyway -- only
    shape-identical, which is what a consumer actually needs;
  * the launcher's model-plan writer is fused to a REFUSAL gate
    (DISPATCH_MODEL_PLAN_REFUSED). Sharing it would import a new refusal into a
    branch that has never had one -- a behaviour change well beyond writing an
    audit record.

Drift between the two writers is guarded by an executable parity test that runs
the REAL launcher and compares its sidecar's key shape against this module's
(tests/test_fix11_client_run_mode_path.py). That test fails if EITHER writer's
shape moves, which a shared helper would not have caught any better.

ROLLBACK doctrine is inherited exactly: PRESENTATION_MODES=0 writes no
`.mode-plan.json` (the whole FIX 11 surface is inert), and
PRESENTATION_MODEL_ROUTER=0 -- or a client who declared no model plan -- writes
no `.model-plan.json`, byte-for-byte the pre-fix launch.

BEST-EFFORT, ALWAYS. A sidecar that cannot be written is announced on stderr and
never blocks a dispatch: the same contract launcher.dispatch gives its own
sidecar writes. An audit record must not be the reason a client's deck does not
get built.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

MODE_PLAN_SIDECAR = ".mode-plan.json"
MODEL_PLAN_SIDECAR = ".model-plan.json"

#: Provenance label for a mode the CLIENT declared in the intake interview
#: (deck-intake-questions.json resource_plan.run_mode -> the RUN_MODE ledger
#: key -> presentation-intake-poll.sh). The launcher's own vocabulary for the
#: other two seams ("--mode", PRESENTATION_MODE, "default") is reused verbatim
#: below so one consumer can read either path's record.
SOURCE_INTAKE = "intake-slot"


def _router():
    try:
        from . import model_router as mod
    except ImportError:  # pragma: no cover -- flat-layout fallback
        import model_router as mod  # type: ignore[no-redef]
    return mod


def _load_profile() -> Optional[Dict[str, Any]]:
    """The measured client profile, or None when the store is unreadable.

    Same semantics as launcher.dispatch: an unreadable store is UNMEASURED, and
    unmeasured is never evidence for a wider run."""
    try:
        try:
            from . import resource_profile as rp
        except ImportError:  # pragma: no cover -- flat-layout fallback
            import resource_profile as rp  # type: ignore[no-redef]
        return rp.load_profile()
    except Exception:  # noqa: BLE001 -- an unreadable store is unmeasured
        return None


def resolve_mode(explicit: Optional[str],
                 source: Optional[str] = None) -> Tuple[str, str, bool]:
    """(mode, provenance, declared) in model_router.active_mode's own order.

        1. an EXPLICIT declaration -- here, the client's intake slot;
        2. the PRESENTATION_MODE env;
        3. DEFAULT_MODE ("standard").

    `declared` matches the launcher's meaning exactly: True only when a mode
    was declared AT THE DOOR, not when one was inherited from the environment.
    An EMPTY explicit value is unset, never a selection. Never ultra by
    default."""
    router = _router()
    text = str(explicit or "").strip().strip("'\"")
    if text:
        return router.normalize_mode(text), (source or SOURCE_INTAKE), True
    env_raw = str(os.environ.get(router.MODE_ENV) or "").strip().strip("'\"")
    if env_raw:
        return router.normalize_mode(env_raw), router.MODE_ENV, False
    return router.DEFAULT_MODE, "default", False


def build_mode_plan(run_dir: Path, mode: str, source: str, declared: bool, *,
                    profile: Optional[Dict[str, Any]] = None,
                    plan_calls: Optional[Dict[str, int]] = None,
                    estimate_usd: Optional[float] = None) -> Dict[str, Any]:
    """The `.mode-plan.json` record, in the launcher's exact key shape.

    Keys: model_router.mode_plan()'s own (mode, concurrency, eta, cost, flag)
    plus the four the launcher adds (run_dir, declared, mode_source, ceiling).
    """
    router = _router()
    plan = router.mode_plan(mode, profile=profile, plan_calls=plan_calls,
                            estimate_usd=estimate_usd)
    plan["run_dir"] = str(run_dir)
    plan["declared"] = bool(declared)
    plan["mode_source"] = source
    plan["ceiling"] = router.mode_ceiling(mode, profile=profile)
    return plan


def build_model_plan(run_dir: Path, mode: str, *,
                     profile: Optional[Dict[str, Any]] = None
                     ) -> Optional[Dict[str, Any]]:
    """The `.model-plan.json` routing stamp, in the launcher's key shape.

    {run_dir, plan, decisions} -- `plan` is model_router.plan_report(), which
    carries the declared slots (workhorse / reasoning / judge) AND the thinking
    level; `decisions` is the per-capability client-plan stamp.

    Returns None when there is nothing to stamp: the router surface is off, or
    the client declared no model plan (the launcher writes no sidecar in that
    case either -- byte-for-byte the pre-fix launch). Deliberately carries NO
    refusal: this path records what was chosen, it does not gate a launch.
    """
    router = _router()
    if not router.flag_enabled():
        return None
    if not router.model_plan(profile):
        return None
    decisions: Dict[str, Any] = {}
    for phase_id, capability in router.PHASE_CAPABILITY.items():
        if capability == "mechanical" or capability in decisions:
            continue
        try:
            decisions[capability] = router.resolve_route(
                phase_id, profile=profile, mode=mode or "standard")
        except Exception as exc:  # noqa: BLE001 -- a router error is not a stamp
            print(f"launch_plan: could not resolve {phase_id} "
                  f"({exc.__class__.__name__}: {exc}) -- no routing stamp "
                  f"written", file=sys.stderr)
            return None
    stamps = []
    for capability, decision in sorted(decisions.items()):
        if decision.get("client_plan"):
            stamps.append({"capability": capability, **decision["client_plan"]})
        elif decision.get("client_plan_floor"):
            stamps.append({"capability": capability, "floor": "failed",
                           **decision["client_plan_floor"]})
    return {"run_dir": str(run_dir), "plan": router.plan_report(profile),
            "decisions": stamps}


def _write_json(path: Path, payload: Dict[str, Any]) -> bool:
    """Atomic write, best-effort. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        print(f"launch_plan: could not write {path.name}: {exc}",
              file=sys.stderr)
        return False


def write_launch_plan(run_dir: Path, explicit: Optional[str] = None,
                      source: Optional[str] = None) -> Dict[str, Any]:
    """Write both launch-plan sidecars for a non-launcher dispatch.

    Returns a small summary {mode, mode_source, declared, wrote}. Never raises:
    an audit record must never be the reason a deck does not get built."""
    router = _router()
    run_path = Path(run_dir).expanduser().resolve()
    if not router.modes_enabled():
        # PRESENTATION_MODES=0 -- the documented rollback. The launcher writes
        # no sidecar in this state; neither do we.
        return {"mode": None, "mode_source": None, "declared": False,
                "wrote": [], "reason": f"{router.MODE_FLAG_ENV}=0 rollback"}
    mode, mode_source, declared = resolve_mode(explicit, source)
    profile = _load_profile()
    wrote = []
    if _write_json(run_path / MODE_PLAN_SIDECAR,
                   build_mode_plan(run_path, mode, mode_source, declared,
                                   profile=profile)):
        wrote.append(MODE_PLAN_SIDECAR)
    stamp = build_model_plan(run_path, mode, profile=profile)
    if stamp is not None and _write_json(run_path / MODEL_PLAN_SIDECAR, stamp):
        wrote.append(MODEL_PLAN_SIDECAR)
    return {"mode": mode, "mode_source": mode_source, "declared": declared,
            "wrote": wrote}


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(
        description="Write the FIX 11 launch-plan sidecars for a dispatch that "
                    "does not go through the launcher (the poller's --new "
                    "branch).")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--mode", default=None, metavar="ULTRA|STANDARD|ECONOMY",
                   help="the mode the CLIENT declared. Omitted/empty means "
                        "undeclared: PRESENTATION_MODE, then standard.")
    p.add_argument("--source", default=SOURCE_INTAKE,
                   help=f"provenance label for --mode (default {SOURCE_INTAKE})")
    args = p.parse_args(argv)
    try:
        result = write_launch_plan(args.run_dir, args.mode, args.source)
    except ValueError as exc:
        # An unknown mode is never silently coerced -- but it must not kill the
        # dispatch either: say so and let the launch proceed unrecorded.
        print(f"launch_plan: {exc} -- no launch-plan sidecar written",
              file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 -- best-effort, always
        print(f"launch_plan: could not record the launch plan "
              f"({exc.__class__.__name__}: {exc})", file=sys.stderr)
        return 0
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
