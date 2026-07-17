#!/usr/bin/env python3
"""
department-optout-sync.py — U108 (E5-3, closes G2b): derives the single,
machine-readable department OPT-OUT CONTRACT FILE
(`provisioning/department-optout.json`) from the interview's provenance-gated
department decisions.

WHY THIS EXISTS:
record-dept-decision.sh (P2-05) already lets an owner decline a department
and, for a FLOOR department (23 mandatory + 6 universal-primary vertical-pack
departments), REQUIRES the owner to be shown the department-loss-warning.py
`loss_warning` text and pass --confirm-loss before the decline is written.
department-floor.py / materialize-missing-departments.py already HONOR that
decline (a declined department is never scaffolded / re-added — see
declined_set() -> expected_floor). What did NOT exist before this unit: a
single purpose-built artifact, at the path U108 names, listing exactly which
departments are opted out RIGHT NOW, carrying the warning that was shown, for
downstream consumers to read without reaching into
.workforce-build-state.json's internal shape — the Command Center board
(U110's board-column skip, cross-referenced by this unit's own spec) and any
CC settings surface being the named consumers.

THE GUARD THIS ADDS (U108 BINARY acceptance (d) — "a guard proves no
department is ever removed without the warning being surfaced"):
canonical_decline.py's declined_set() only checks PROVENANCE (decision /
source / decidedAt / decidedBy) — by design it does not, and should not, know
about the loss-warning gate (that gate is a record-dept-decision.sh CLI-layer
concern, not a floor-honoring concern). That means a decision object written
by some OTHER path directly into canonicalReconciliation.decisions
(bypassing record-dept-decision.sh) with correct provenance but WITHOUT
`lossWarningAck` would still be a floor-honored decline at the
department-floor.py layer. THIS script closes that gap for the OPT-OUT
CONTRACT specifically: a FLOOR department is only written into
department-optout.json with `optedOut: true` when its decision object
carries `lossWarningAck: true` (or the department is NOT a floor department,
which carries no loss_warning and needs no confirmation to opt out of).
Anything else is reported under `unconfirmed` and is NEVER treated as an
honored opt-out by this artifact — so any consumer that reads ONLY this file
can never silently drop a department without the warning having been shown
and acknowledged. This is a narrower, ADDITIONAL guarantee layered on top of
department-floor.py's own declined_set() (which this script imports and
never modifies).

REVERSIBLE BY CONSTRUCTION (U108 acceptance (c)): this script is idempotent
and reads the CURRENT build-state fresh on every run — it never appends to a
log or keeps its own persisted "removed" list. Re-running
record-dept-decision.sh --decision yes for a previously-opted-out department
(the interview's own re-opt-in path — the writer OVERWRITES that dept's
decision object) flips canonical_decline's declined_set() so the department
is no longer declined; the very next sync run therefore drops it from
`optedOut` automatically — no special-cased "undo" logic is needed or built
here, and department-floor.py's expected_floor picks the department back up
on its own.

USAGE
  department-optout-sync.py [--state <build-state.json>] [--naming-map <path>]
                             [--out <department-optout.json path>] [--json]
                             [--dry-run]

DEFAULT OUTPUT PATH: `provisioning/department-optout.json` BESIDE
.workforce-build-state.json in the box's own per-client workspace
(/data/.openclaw/workspace or ~/.openclaw/workspace) — generated, box-
specific state, never inside the shared git repo checkout (that would leave
the repo perpetually dirty). Falls back to a repo-relative path only when no
workspace dir resolves at all (e.g. a repo-only CI checkout). Always pass
--out explicitly in tests for hermetic isolation.

EXIT CODES
  0  synced (or --dry-run reported) successfully, zero unconfirmed anomalies
  1  synced (or reported) successfully, but >=1 floor decline was UNCONFIRMED
     (listed under `unconfirmed`, NEVER honored as an opt-out) — the caller
     should surface this to the operator/owner; the file is still written so
     nothing is silently swallowed
  2  usage / could not read --state explicitly passed (a missing DEFAULT
     build-state, e.g. no workforce on this box yet, is not an error — it
     syncs an empty optedOut set)

Import-safe: `from department_optout_sync import compute_optout, sync`.
"""

import argparse
import importlib.util as _ilu
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent
# Fallback ONLY when no per-box workspace dir resolves (e.g. a pure repo/CI
# checkout with no ~/.openclaw workspace at all) — see _default_out_path().
_REPO_FALLBACK_OUT = REPO_ROOT / "provisioning" / "department-optout.json"


def _load_module(mod_name, filename):
    """Import a hyphenated sibling script as a module (mirrors the technique
    already used by materialize-missing-departments.py / check-floor-count-drift.py)."""
    path = SCRIPT_DIR / filename
    spec = _ilu.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = _ilu.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT_DIR))
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


canonical_decline = _load_module("canonical_decline__optout_sync", "canonical_decline.py")
loss_warning_mod = _load_module("department_loss_warning__optout_sync", "department-loss-warning.py")


def _resolve_workspace_dir():
    """Mirror record-dept-decision.sh's own state-directory resolution
    (/data/.openclaw/workspace, then ~/.openclaw/workspace). Returns Path|None."""
    for d in ("/data/.openclaw/workspace", str(Path.home() / ".openclaw" / "workspace")):
        if Path(d).is_dir():
            return Path(d)
    return None


def _default_state_path():
    ws = _resolve_workspace_dir()
    return (ws / ".workforce-build-state.json") if ws else None


def _default_out_path():
    """The opt-out contract file lives BESIDE .workforce-build-state.json in
    the per-box/per-client workspace — it is generated, box-specific state,
    not template content, so it must never default into the shared git
    repo checkout (that would leave the repo perpetually dirty and risks the
    generated file being committed or wiped by a repo-level git operation).
    Only when no workspace dir resolves at all (e.g. a repo-only checkout
    with no ~/.openclaw workspace, such as a fresh CI runner) does this fall
    back to a repo-relative path, purely so the script still runs somewhere
    sane rather than crashing."""
    ws = _resolve_workspace_dir()
    if ws:
        return ws / "provisioning" / "department-optout.json"
    return _REPO_FALLBACK_OUT


def load_build_state(path=None):
    """Returns (build_state: dict, resolved_path: Path|None). Never raises —
    a missing/unreadable default state degrades to an empty dict (matches
    department-loss-warning.py's own read-only fail-soft convention); an
    EXPLICITLY passed --state that cannot be read is the caller's problem
    (main() reports it and exits 2)."""
    p = Path(path) if path else _default_state_path()
    if p is None or not p.exists():
        return {}, p
    try:
        return json.loads(p.read_text(encoding="utf-8")), p
    except (OSError, json.JSONDecodeError):
        return {}, p


def _raw_decisions(build_state):
    recon = (build_state or {}).get("canonicalReconciliation") or {}
    decisions = recon.get("decisions")
    return decisions if isinstance(decisions, dict) else {}


def _record(decision_obj, warning_text, floor_status):
    return {
        "optedOut": True,
        "lossWarningShown": warning_text is not None,
        "lossWarningText": warning_text,
        "floorStatus": floor_status,
        "decidedAt": decision_obj.get("decidedAt"),
        "decidedBy": decision_obj.get("decidedBy"),
        "source": decision_obj.get("source"),
        "reversible": True,
    }


def compute_optout(build_state, naming_map_path=None):
    """
    Pure function (no I/O beyond the naming-map read). Returns
    (optout: {dept_id: record}, unconfirmed: [{department, reason}]).

    `optout` is the HONORED opt-out set — the only departments a downstream
    consumer (provisioning, the CC board) may treat as removed.
    `unconfirmed` lists every declined-per-canonical_decline department this
    script REFUSED to honor as an opt-out because a floor department's loss
    warning was never confirmed shown — never silently dropped, always named.
    """
    analysis = canonical_decline.analyze(build_state, quiet=True)
    declined = analysis["declined"]  # set of NORMALIZED ids, provenance-honored
    raw = _raw_decisions(build_state)

    nm = loss_warning_mod.load_naming_map(naming_map_path)
    nm_usable = loss_warning_mod.naming_map_is_usable(nm)

    by_norm = {}
    for raw_id, obj in raw.items():
        by_norm[canonical_decline.norm(raw_id)] = (raw_id, obj if isinstance(obj, dict) else {})

    optout = {}
    unconfirmed = []

    for ncid in sorted(declined):
        raw_id, obj = by_norm.get(ncid, (ncid, {}))

        if not nm_usable:
            # FAIL-CLOSED (mirrors department-loss-warning.py's rc=4 doctrine):
            # floor status cannot be determined at all. Only honor when the
            # decision ALREADY carries an explicit lossWarningAck (the owner
            # was shown *something* and confirmed); otherwise refuse.
            if obj.get("lossWarningAck") is True:
                optout[raw_id] = _record(obj, obj.get("lossWarning"),
                                          "indeterminate-map-but-explicitly-confirmed")
            else:
                unconfirmed.append({
                    "department": raw_id,
                    "reason": "department-naming-map.json is unreadable/unusable — floor "
                              "status cannot be determined and no lossWarningAck is present "
                              "on this decline; NOT honored as an opt-out (fail-closed).",
                })
            continue

        warning_text = loss_warning_mod.loss_warning_for(raw_id, nm=nm)
        is_floor = warning_text is not None

        if not is_floor:
            # Non-floor department (keyword-matched industry extra, or a custom
            # department): no guaranteed functionality is lost, no warning owed.
            optout[raw_id] = _record(obj, None, "non-floor")
            continue

        # FLOOR department — THE GUARD: only honored when the warning was
        # actually shown and acknowledged (lossWarningAck stamped True by
        # record-dept-decision.sh's --confirm-loss path).
        if obj.get("lossWarningAck") is True:
            optout[raw_id] = _record(obj, obj.get("lossWarning") or warning_text, "floor-confirmed")
        else:
            unconfirmed.append({
                "department": raw_id,
                "reason": (f"'{raw_id}' is a FLOOR department (would lose: {warning_text}) "
                           f"but its decline is missing lossWarningAck — the loss warning was "
                           f"never confirmed shown. NOT honored as an opt-out."),
            })

    return optout, unconfirmed


def sync(state_path=None, naming_map_path=None, out_path=None, dry_run=False):
    """Compute the opt-out payload and (unless dry_run) atomically write it to
    `out_path` (default: see _default_out_path() — beside the box's own
    .workforce-build-state.json). Returns (payload: dict, out_path: Path)."""
    build_state, resolved_state_path = load_build_state(state_path)
    optout, unconfirmed = compute_optout(build_state, naming_map_path)

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(resolved_state_path) if resolved_state_path else None,
        "optedOut": optout,
        "unconfirmed": unconfirmed,
    }

    out = Path(out_path) if out_path else _default_out_path()
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.parent / f"{out.name}.tmp.{os.getpid()}"
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(out)

    return payload, out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default=None,
                     help="explicit .workforce-build-state.json path (test isolation / operator override)")
    ap.add_argument("--naming-map", default=None,
                     help="override department-naming-map.json path (testing)")
    ap.add_argument("--out", default=None,
                     help="override provisioning/department-optout.json output path")
    ap.add_argument("--json", action="store_true", help="print the payload to stdout")
    ap.add_argument("--dry-run", action="store_true", help="compute + report only, never write")
    args = ap.parse_args(argv)

    if args.state and not Path(args.state).exists():
        print(f"ERROR: --state path does not exist: {args.state}", file=sys.stderr)
        return 2

    payload, out = sync(state_path=args.state, naming_map_path=args.naming_map,
                         out_path=args.out, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        n_out = len(payload["optedOut"])
        n_unc = len(payload["unconfirmed"])
        dest = "stdout only (--dry-run)" if args.dry_run else str(out)
        print(f"department-optout-sync: {n_out} opted-out department(s), "
              f"{n_unc} unconfirmed anomaly(ies) -> {dest}", file=sys.stderr)
        for d in payload["unconfirmed"]:
            print(f"  UNCONFIRMED: {d['department']}: {d['reason']}", file=sys.stderr)

    return 1 if payload["unconfirmed"] else 0


if __name__ == "__main__":
    sys.exit(main())
