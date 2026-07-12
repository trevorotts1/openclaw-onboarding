#!/usr/bin/env python3
"""
p206-floor-short-probe.py — P2-06 (c)1: per-box HARD-floor-vs-live-board probe.

SHIPS IN P6-01 (built and QC'd now; run against live fleet boxes only in the
final rollout phase per meta-rule 2.1/2.7 — no canary, evidence-backed QC now,
post-deploy per-box validation in the real rollout).

WHAT THIS CLOSES
-----------------
P2-06's own verified gap: department-floor.py / build-workforce.py were fixed
to fail CLOSED on an unreadable naming map (a NEW build can no longer go
short), but "UNVERIFIED: how many LIVE boxes still carry a wiped floor from
the pre-fix era" was left open. This probe answers that per box: it runs the
box's OWN department-floor.py (evaluate_floor) against its OWN live
departments/ tree and reports a structured floor_short verdict — never a
grep, never a guess, the same live HARD-floor logic every other gate in the
repo already trusts.

With --remediate, on a flagged box it invokes materialize-missing-departments.py
--apply (the P2-06 (c)2 remediation script) to close the gap additively, then
re-checks and reports the after-state — mirroring the p107-sunday-update-probe.sh
--remediate contract (detect, optionally fix, always re-verify from the
SOURCE, never trust the fixer's own exit code as proof).

LAYER 3 (DISPLAYED) RE-VERIFICATION: materialize-missing-departments.py only
closes LAYER 2 (provisioned) on disk by itself; its own LAYER 3 join proof
(chosen == provisioned == displayed via prove-board-join.py) is EXPLICIT-SIGNAL
ONLY — it requires --db or $DASHBOARD_DB_PATH / $DATABASE_PATH, and NEVER
falls through to ambient DB discovery (a live incident during that unit's own
development — see materialize-missing-departments.py's _find_cc_db()). This
probe therefore accepts its own --db and threads it through to the
remediator's --db, AND independently re-runs
materialize_missing_departments.verify_board_join() itself from source after
remediation (never trusting the remediator's embedded self-report alone) so a
box that never receives --db / the env var honestly reports LAYER 3 as
NOT-APPLICABLE instead of silently skipping the check without a trace, and a
box that DOES supply --db actually gets the (c)2 contract's "then
prove-board-join.py must pass" enforced live.

USAGE
  p206-floor-short-probe.py [--json] [--box <label>] [--remediate]
                             [--departments-dir <dir>] [--build-state-file <file>]
                             [--db <mission-control.db>]

  --db is only consulted when --remediate is also passed; it (or
  $DASHBOARD_DB_PATH / $DATABASE_PATH) is what turns LAYER 3 join
  verification from NOT-APPLICABLE into a real, live check.

EXIT CODES
  0  ARMED       (floor met — either already, or closed this run via
                  --remediate — AND, when --db / the env var made LAYER 3
                  verification possible, prove-board-join.py reported OK or
                  the check was NOT-APPLICABLE)
  1  DEGRADED    (floor short; re-run with --remediate to close it) OR the
                  floor closed but the independently re-verified LAYER 3 join
                  reported DRIFT / CANNOT-VOUCH / GATE-ERROR — an un-runnable
                  or disagreeing join is not a verified join
  2  UNRESOLVABLE (no departments dir could be found on this box — usage error
                   or a box with no workforce at all; distinct from DEGRADED)
================================================================================
"""
import argparse
import contextlib
import importlib.util as _ilu
import io
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


def _resolve_skill_dir():
    """Self-locating: prefer THIS SAME CHECKOUT's 23-ai-workforce-blueprint
    (so a fresh clone always exercises its own freshly-built scripts, never a
    stale installed copy elsewhere on the box) before falling back to a box's
    installed skill-23 tree. Mirrors floor-fill-driver.py's own resolution
    order exactly (own-checkout first, THEN ~/.openclaw, THEN /data/.openclaw)."""
    cands = []
    env = os.environ.get("OPENCLAW_SKILL23_DIR")
    if env:
        cands.append(Path(env))
    cands.append(Path(__file__).resolve().parent.parent.parent / "23-ai-workforce-blueprint")
    cands += [
        Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint",
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint"),
    ]
    for c in cands:
        try:
            if (c / "scripts" / "department-floor.py").is_file():
                return c
        except OSError:
            continue
    return cands[-1]


SKILL_DIR = _resolve_skill_dir()
SCRIPTS_DIR = SKILL_DIR / "scripts"


def _load_module(mod_name, filename):
    path = SCRIPTS_DIR / filename
    spec = _ilu.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = _ilu.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _hostname():
    try:
        return socket.gethostname().split(".")[0]
    except OSError:
        return "unknown"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--box", default=os.environ.get("OPENCLAW_BOX_LABEL") or _hostname())
    ap.add_argument("--remediate", action="store_true")
    ap.add_argument("--departments-dir", default=None)
    ap.add_argument("--build-state-file", default=None,
                     help="test isolation / operator override — default is the box's real "
                          "build-state (department_floor.load_build_state()).")
    ap.add_argument("--db", default=None,
                     help="explicit mission-control.db path, threaded through to "
                          "materialize-missing-departments.py --db (or set "
                          "$DASHBOARD_DB_PATH / $DATABASE_PATH) so --remediate's LAYER 3 "
                          "(displayed) join verification actually runs instead of reporting "
                          "NOT-APPLICABLE. EXPLICIT-SIGNAL ONLY -- never ambient discovery.")
    args = ap.parse_args(argv)

    department_floor_path = SCRIPTS_DIR / "department-floor.py"
    if not department_floor_path.is_file():
        verdict = {
            "box": args.box,
            "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rc": 2,
            "reason": f"department-floor.py not found at {department_floor_path} "
                      f"(skill 23 not installed on this box)",
        }
        _emit(verdict, args.json)
        return 2

    department_floor = _load_module("department_floor__p206probe", "department-floor.py")

    build_state = None
    if args.build_state_file:
        try:
            build_state = json.loads(Path(args.build_state_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            verdict = {"box": args.box, "rc": 2, "reason": f"could not read --build-state-file: {exc}"}
            _emit(verdict, args.json)
            return 2

    dd = Path(args.departments_dir) if args.departments_dir else None
    try:
        before = department_floor.evaluate_floor(departments_dir=dd, build_state=build_state)
    except SystemExit as exc:
        # HARDENING (found by this unit's own test suite, T4): when no
        # --departments-dir is given, evaluate_floor() -> resolve_departments_dir()
        # falls through to detect_platform.get_openclaw_paths(), which does
        # `raise SystemExit(1)` (not a catchable Exception) when it cannot find
        # ANY of /data/.openclaw, ~/.openclaw, ~/clawd on this box.
        # resolve_departments_dir()'s own `except Exception: pass` does not (and,
        # being a shared module other gates depend on, should not be changed
        # here) catch SystemExit, so it propagates. A fleet probe must NEVER
        # crash uncleanly with an ambiguous exit code on an unresolvable box --
        # it must emit a structured verdict. This converts that specific,
        # expected "no platform detected" case into the SAME rc=2 UNRESOLVABLE
        # verdict the dd-is-None/no-workforce path already returns below.
        verdict = {
            "box": args.box,
            "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rc": 2,
            "reason": f"platform/workforce not detectable on this box (SystemExit({exc.code}) "
                      f"from detect_platform while resolving the departments dir)",
        }
        _emit(verdict, args.json)
        return 2

    if before["rc"] == 7:
        verdict = {
            "box": args.box,
            "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rc": 2,
            "reason": "no departments dir resolvable on this box (no workforce, or non-standard layout)",
        }
        _emit(verdict, args.json)
        return 2

    floor_short = not before["floor_met"]
    departments_dir = before["departments_dir"]

    remediated = False
    remediation_report = None
    join_verification = None
    after = before
    if args.remediate and floor_short:
        materialize = _load_module("materialize_missing_departments__p206probe",
                                    "materialize-missing-departments.py")
        mz_argv = ["--departments-dir", departments_dir, "--apply", "--json"]
        if args.build_state_file:
            mz_argv += ["--build-state-file", args.build_state_file]
        if args.db:
            mz_argv += ["--db", args.db]
        # Capture the remediator's own stdout (its --json report) so it never
        # corrupts THIS probe's --json output; surfaced under remediation_report
        # instead, for the ledger to inspect.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            materialize.main(mz_argv)
        remediated = True
        try:
            remediation_report = json.loads(buf.getvalue())
        except (ValueError, TypeError):
            remediation_report = {"raw": buf.getvalue()[-4000:]}
        # Never trust the remediator's own report as proof — RE-VERIFY from the
        # source (meta-rule 2.3.6 / session-survival rule 6): re-run
        # evaluate_floor() against the live tree it just wrote to.
        after = department_floor.evaluate_floor(departments_dir=Path(departments_dir), build_state=build_state)
        # LAYER 3 (displayed): the remediator's own embedded join_verification
        # (inside remediation_report) is a sub-agent's self-report, not proof —
        # independently re-run materialize's verify_board_join() from source
        # against the SAME --db (or env var) this probe was given, so the
        # (c)2 contract "then prove-board-join.py must pass" is actually
        # exercised live rather than trusted from the remediator's own claim.
        join_verification = materialize.verify_board_join(Path(departments_dir), args.db)

    overall_armed = bool(after["floor_met"])
    if join_verification is not None and join_verification["status"] in materialize.BLOCKING_JOIN_STATUSES:
        overall_armed = False

    verdict = {
        "box": args.box,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departments_dir": departments_dir,
        "floor_short": floor_short,
        "expected_floor_count": before["expected_floor_count"],
        "on_disk_count": before["on_disk_count"],
        "missing_mandatory": before["missing_mandatory"],
        "missing_universal_primary": before["missing_universal_primary"],
        "remediated_this_run": remediated,
        "overall_armed": overall_armed,
    }
    if remediated:
        verdict["missing_after"] = after["missing_mandatory"] + after["missing_universal_primary"]
        verdict["remediation_report"] = remediation_report
        verdict["join_verification"] = join_verification

    _emit(verdict, args.json)
    return 0 if overall_armed else 1


def _emit(verdict, as_json):
    if as_json:
        print(json.dumps(verdict, indent=2))
        return
    box = verdict.get("box", "unknown")
    checked_at = verdict.get("checked_at", "")
    print(f"P2-06 floor-short probe — box: {box}  ({checked_at})")
    if verdict.get("rc") == 2:
        print(f"  [ERROR] {verdict.get('reason')}")
        return
    if verdict.get("floor_short"):
        print(f"  [MISS] floor short — {verdict['on_disk_count']}/{verdict['expected_floor_count']} departments")
        if verdict.get("missing_mandatory"):
            print(f"         missing mandatory: {', '.join(verdict['missing_mandatory'])}")
        if verdict.get("missing_universal_primary"):
            print(f"         missing universal-primary: {', '.join(verdict['missing_universal_primary'])}")
    else:
        print(f"  [OK]   floor met — {verdict['on_disk_count']}/{verdict['expected_floor_count']} departments")
    if verdict.get("remediated_this_run"):
        print(f"  [INFO] --remediate ran materialize-missing-departments.py --apply; "
              f"missing_after={verdict.get('missing_after')}")
        jv = verdict.get("join_verification") or {}
        print(f"  [INFO] LAYER 3 join re-verification (independent, from source): "
              f"status={jv.get('status')} rc={jv.get('rc')}")
    print(f"  VERDICT: {'ARMED' if verdict.get('overall_armed') else 'DEGRADED'}")


if __name__ == "__main__":
    sys.exit(main())
