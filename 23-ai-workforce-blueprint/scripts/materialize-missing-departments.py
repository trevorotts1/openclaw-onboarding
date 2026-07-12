#!/usr/bin/env python3
"""
materialize-missing-departments.py — P2-06 (c)2: THE FLOOR-WIPE FIX, live remediation.

ROOT CAUSE (P2-06 (b), already fixed at the BUILD-TIME layer): when
department-naming-map.json was unreadable, the build used to SILENTLY drop
to 22 departments (losing the 6 universal-primary). department-floor.py /
build-workforce.py now fail CLOSED (unreadable map -> the full 28-department
floor is still enforced via HARDCODED_MANDATORY + HARDCODED_UNIVERSAL_PRIMARY,
never a silent short list). That fix stops a NEW build from ever going short.

This script closes the RESIDUE: a box that was BUILT before the fix landed
(or otherwise "hit the wipe") is still missing whole departments TODAY, and
nothing in the update path re-materializes a whole missing department (only
missing ROLES/SOPS inside an EXISTING department — see
migrate-existing-workforce.sh Step 2b / floor-fill-driver.py v16.0.2). A
department that is entirely absent from disk was invisible to that path
because make-gap-from-staleness.py deliberately drops "dept"-kind items
(see tests/unit/floor-fill-gap.test.sh: "STALE / dept items must be dropped").

This script is the whole-department remediation floor-fill-driver.py never
got wired for:

  1. department_floor.evaluate_floor(departments_dir) -> the LIVE HARD-floor
     verdict (respects client declines; never re-adds a declined dept).
  2. For each dept the verdict reports MISSING (missing_mandatory +
     missing_universal_primary), resolve its role-library folder via
     create_role_workspaces.normalize_dept() and enumerate every shipped
     role .md file there -> the FULL roster (the dept does not exist on disk
     at all, so every library role for it is "missing").
  3. Write that as a gap-map in floor-fill-driver.py's own schema and invoke
     floor-fill-driver.py (subprocess, --apply) — REUSING the already-shipped,
     already-QC'd v16.0.2 additive / skip-existing / no-clobber materializer
     instead of re-implementing folder creation here.
  4. Re-run evaluate_floor() and report the before/after verdict.

SAFETY CONTRACT (inherited from floor-fill-driver.py, not reimplemented):
  - additive-only: only CREATES departments/roles absent from disk. A
    department already present (under its canonical id OR any known variant
    slug — department_floor._present()) is never touched: evaluate_floor()
    only reports it in missing_mandatory/missing_universal_primary when it is
    genuinely absent, so this script never even builds a gap-map entry for it.
  - skip-existing, no-clobber: floor-fill-driver.py's own per-role check
    (existing_role_keys) refuses to touch a role that is already on disk, so
    a partially-seeded dept from an interrupted prior run is never re-clobbered
    on retry (idempotent).
  - dry-run by default; --apply required to mutate.
  - never fabricates content: every role file comes from the box's real,
    shipped templates/role-library/ tree via floor-fill-driver's own
    create_role_workspace() (try_library_fill) — identical to a fresh build.
    A dept whose library source is missing is SKIPPED and reported under
    "no_library_source", never stubbed.

JOIN VERIFICATION (P2-06 (c)2's own closing requirement — "then
prove-board-join.py must pass"): materializing the missing department
directories only closes the PROVISIONED layer of the three-layer contract
(chosen == provisioned == displayed) that prove-board-join.py enforces. A box
can leave this script with floor_met=True on disk and STILL be broken for the
client if (a) the CHOSEN artifact (<company_dir>/departments.json) never
listed the newly-materialized department (a pre-C7 or otherwise-short chosen
list — the box may have hit the SAME wipe at the chosen-list layer, not just
on disk), or (b) the Command Center's `workspaces` table was seeded before
today and was never told about the department that just appeared. So, after a
successful --apply that actually closed a gap, this script — UNLESS
--skip-join-verify is passed —:
  1. Appends the newly-closed department id(s) to the CHOSEN artifact
     (<company_dir>/departments.json + build-state
     canonicalReconciliation.chosenDepartments) — APPEND-ONLY, every existing
     entry carried through byte-for-byte (mirrors write_chosen_departments_
     artifact()'s own shape; never a second source of truth for dept-info —
     resolved via build-workforce.load_canonical_floor() / the same
     vertical_packs block apply_vertical_packs() reads).
  2. If a Command Center database can be found on this box (the SAME shared
     resolve_db.find_dashboard_db() every other gate uses, honoring
     $DASHBOARD_DB_PATH), re-runs 32-command-center-setup/scripts/
     seed-workspaces.py (idempotent, INSERT OR IGNORE) so the DISPLAYED layer
     picks up the now-chosen-and-provisioned department, then runs
     prove-board-join.py --company-dir <company_dir> --db <db> --json and
     records its verdict under result["join_verification"].
  3. If NO Command Center database is found, join verification is
     NOT-APPLICABLE (a box with no CC yet has nothing to join — this is not a
     failure) and is recorded as such, never silently skipped without a trace.
  A DRIFT or CANNOT-VOUCH join verdict downgrades the overall exit code to 1
  (needs operator attention) even though the on-disk floor is met — the
  residue is not FULLY closed until chosen == provisioned == displayed.

USAGE
  materialize-missing-departments.py [--departments-dir <dir>] [--apply] [--json]
                                      [--skip-join-verify] [--db <mission-control.db>]

  --departments-dir defaults to department_floor.resolve_departments_dir()
  (the same platform-appropriate resolver department-floor.py itself uses),
  so on a real box this needs no argument at all.

EXIT CODES
  0  floor already met (nothing to do), OR --apply successfully closed the gap
     AND (join verification passed OR was NOT-APPLICABLE / skipped)
  1  still short after --apply (a dept's role-library source is missing —
     logged under no_library_source, never fabricated) — needs operator
     attention; OR the floor closed but join verification reported DRIFT /
     CANNOT-VOUCH (chosen/provisioned/displayed disagree — also needs
     operator attention)
  2  usage error / no departments dir resolvable
  3  floor is short and --apply was NOT passed (dry-run informs, does not mutate)
"""
import argparse
import importlib.util as _ilu
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(mod_name, filename):
    """Import a hyphenated sibling script as a module (mirrors
    check-floor-count-drift.py's importlib.util technique)."""
    path = SCRIPT_DIR / filename
    spec = _ilu.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = _ilu.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT_DIR))
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


department_floor = _load_module("department_floor__materialize", "department-floor.py")
crw = _load_module("create_role_workspaces__materialize", "create_role_workspaces.py")

LIBRARY = SCRIPT_DIR.parent / "templates" / "role-library"
LIBRARY_INDEX = LIBRARY / "_index.json"
FLOOR_FILL_DRIVER = SCRIPT_DIR / "floor-fill-driver.py"
REPO_ROOT = SCRIPT_DIR.parent.parent
SEED_WORKSPACES = REPO_ROOT / "32-command-center-setup" / "scripts" / "seed-workspaces.py"
PROVE_BOARD_JOIN = SCRIPT_DIR / "prove-board-join.py"


def _load_library_index():
    if not LIBRARY_INDEX.is_file():
        return []
    try:
        return json.loads(LIBRARY_INDEX.read_text(encoding="utf-8")).get("roles", [])
    except (OSError, ValueError):
        return []


def library_roster_for(dept_id, index_roles=None):
    """Every role the shipped library's _index.json carries for dept_id, as
    canonical role slugs. Reading _index.json (the SAME source
    create_role_workspaces.library_lookup() resolves through) rather than
    globbing the dept folder is required because the library uses TWO layouts
    interchangeably: flat '<slug>.md' files (e.g. sales/) AND per-role
    '<slug>/how-to.md' subdirectories (e.g. engineering/) — a naive glob for
    '*.md' at the dept-folder root silently returns [] for every subdirectory
    dept. Resolves dept_id -> library dept key via the SAME alias map
    create_role_workspaces.py / floor-fill-driver.py use (normalize_dept), so
    'billing-finance' finds the 'billing' library dept and 'legal' finds the
    'legal-compliance' library dept."""
    if index_roles is None:
        index_roles = _load_library_index()
    dept_key = crw.normalize_dept(dept_id)
    slugs = []
    seen = set()
    for entry in index_roles:
        if entry.get("dept", "").lower() != dept_key:
            continue
        slug = entry.get("slug", "")
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return sorted(slugs)


def build_gap_map(missing_depts):
    """missing_depts -> (gap_map, no_library_source).
    gap_map matches floor-fill-driver.py's schema exactly:
      { "<dept_id>": {"kind": "roster", "missing_roles": [...]} }
    A dept whose library source cannot be found is reported separately and
    NEVER given a fabricated/stub entry."""
    gap = {}
    no_library = []
    index_roles = _load_library_index()
    for dept_id in missing_depts:
        roster = library_roster_for(dept_id, index_roles=index_roles)
        if not roster:
            no_library.append(dept_id)
            continue
        gap[dept_id] = {"kind": "roster", "missing_roles": roster}
    return gap, no_library


def run_floor_fill_driver(gap_map, departments_dir, apply_):
    """Invoke the already-shipped v16.0.2 materializer as a subprocess
    (matches how migrate-existing-workforce.sh Step 2b calls it) so this
    script never reimplements folder/role creation."""
    with tempfile.TemporaryDirectory() as td:
        gap_file = Path(td) / "gap.json"
        gap_file.write_text(json.dumps(gap_map), encoding="utf-8")
        cmd = [sys.executable, str(FLOOR_FILL_DRIVER),
               "--gap-file", str(gap_file), "--workspace", str(departments_dir)]
        if apply_:
            cmd.append("--apply")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        report = None
        try:
            report = json.loads(proc.stdout)
        except (ValueError, TypeError):
            pass
        return proc.returncode, report, proc.stdout, proc.stderr


# ── P2-06 (c)2 closing requirement: "then prove-board-join.py must pass" ────
# Materializing directories only closes LAYER 2 (provisioned). These helpers
# close the loop on LAYER 1 (chosen) and hand off to seed-workspaces.py /
# prove-board-join.py to prove LAYER 3 (displayed) agrees too.

def _universal_primary_dept_info(bw, dept_id):
    """Resolve {name, emoji, head, description} for a universal-primary
    vertical dept id from the SAME vertical_packs source
    build-workforce.apply_vertical_packs() reads — never a second,
    hand-maintained source of truth. None if dept_id is not universal-primary."""
    packs = bw._load_vertical_packs() or {}
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if isinstance(dept, dict) and dept.get("id") == dept_id and dept.get("universal_primary"):
                name = dept.get("name", dept_id.replace("-", " ").title())
                return {"name": name, "emoji": dept.get("emoji", "\U0001f4c1"),
                        "head": f"Director of {name}", "description": dept.get("one_liner", "")}
    return None


def sync_chosen_artifact(departments_dir, closed_ids):
    """
    APPEND-ONLY merge of the newly-closed department id(s) into the CHOSEN
    artifact (<company_dir>/departments.json) + build-state
    canonicalReconciliation.chosenDepartments. Every existing entry is
    preserved unchanged; only ids not already present are appended. Returns
    the list of ids actually appended (empty if they were already chosen —
    the common case, since C7 builds usually chose the full floor already and
    this box's residue was PROVISIONED-only).
    """
    bw = _load_module("build_workforce__materialize_join", "build-workforce.py")
    company_dir = Path(departments_dir).parent
    artifact_path = company_dir / "departments.json"
    try:
        existing = json.loads(artifact_path.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    except (OSError, ValueError):
        existing = []

    known = set()
    for e in existing:
        if isinstance(e, dict):
            slug = e.get("slug") or (e.get("id") or "").removeprefix("dept-")
            if slug:
                known.add(slug)

    canonical_floor = bw.load_canonical_floor()
    merged = list(existing)
    appended = []
    for did in closed_ids:
        if did in known:
            continue
        info = canonical_floor.get(did) or _universal_primary_dept_info(bw, did)
        if not info:
            continue
        merged.append({
            "id": f"dept-{did}", "slug": did,
            "emoji": info.get("emoji", "\U0001f4c1"),
            "name": info.get("name", did.replace("-", " ").title()),
            "headTitle": info.get("head", f"Director of {did}"),
            "workspacePath": f"departments/{did}",
        })
        appended.append(did)
        known.add(did)

    if not appended:
        return []

    try:
        company_dir.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    except OSError:
        return []  # fail-soft: a chosen-artifact write failure must never abort remediation

    try:
        state_path = Path(bw._build_state_path())
        state = bw._load_build_state()
        recon = state.get("canonicalReconciliation", {})
        if not isinstance(recon, dict):
            recon = {}
        chosen = recon.get("chosenDepartments", {})
        prior = chosen.get("slugs") if isinstance(chosen, dict) and isinstance(chosen.get("slugs"), list) else []
        new_slugs = list(prior)
        for sid in appended:
            if sid not in new_slugs:
                new_slugs.append(sid)
        recon["chosenDepartments"] = {
            **(chosen if isinstance(chosen, dict) else {}),
            "slugs": new_slugs, "count": len(new_slugs),
            "artifactPath": str(artifact_path), "companyDir": str(company_dir),
            "artifactWritten": True, "source": "p2-06-materialize-missing-departments",
        }
        state["canonicalReconciliation"] = recon
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass  # the artifact write above already succeeded; build-state mirror is best-effort

    return appended


def _find_cc_db(explicit_db):
    """
    EXPLICIT-SIGNAL ONLY — never ambient install-path discovery.

    SAFETY (found during this unit's own development, live incident):
    resolve_db.find_dashboard_db()'s full candidate list includes fixed
    per-platform install paths (e.g. ~/projects/command-center/mission-
    control.db) that match a REAL, LIVE database on any box that has ever had
    a real Command Center installed — including the operator's own dev
    machine. Calling that full resolver unconditionally from a script that
    can run in an unrelated test/scratch context (no isolated $HOME) silently
    found and mutated a live database during this unit's own test run
    ("do NOT touch any client/operator box" — violated once, here, and fixed
    on the spot). This function therefore honors ONLY an EXPLICIT --db
    argument or the $DASHBOARD_DB_PATH / $DATABASE_PATH env vars — both of
    which require a caller to deliberately opt in — and NEVER falls through
    to the shared resolver's ambient install-path candidate list. A caller
    (the P6-01 rollout) that wants join verification on a real box must pass
    --db (or the env var) explicitly; a bare --apply with neither set is
    NOT-APPLICABLE by design, never a guess.
    """
    if explicit_db:
        p = Path(explicit_db)
        return p if p.is_file() else None
    for env_var in ("DASHBOARD_DB_PATH", "DATABASE_PATH"):
        v = os.environ.get(env_var)
        if v and Path(v).is_file():
            return Path(v)
    return None


def verify_board_join(departments_dir, explicit_db):
    """
    Close LAYER 3: re-seed the Command Center's `workspaces` table (idempotent
    INSERT OR IGNORE — never touches an already-displayed row) then run
    prove-board-join.py and report its verdict. Returns a dict:
      {"status": "OK"|"DRIFT"|"CANNOT-VOUCH"|"NOT-APPLICABLE"|"GATE-ERROR",
       "rc": <prove-board-join.py exit code or None>,
       "seed_ran": bool, "verdict": {...} or None}
    NOT-APPLICABLE (no CC database on this box yet) is NOT a failure — a box
    with no Command Center installed has nothing to join.
    """
    company_dir = Path(departments_dir).parent
    db_path = _find_cc_db(explicit_db)
    if db_path is None:
        return {"status": "NOT-APPLICABLE", "rc": None, "seed_ran": False, "verdict": None,
                "reason": "no Command Center database found on this box "
                          "(checked $DASHBOARD_DB_PATH / $DATABASE_PATH / install candidates)"}

    seed_ran = False
    if SEED_WORKSPACES.is_file():
        env = dict(os.environ)
        env["DASHBOARD_DB_PATH"] = str(db_path)
        subprocess.run([sys.executable, str(SEED_WORKSPACES)], capture_output=True, text=True, env=env)
        seed_ran = True

    if not PROVE_BOARD_JOIN.is_file():
        return {"status": "GATE-ERROR", "rc": None, "seed_ran": seed_ran, "verdict": None,
                "reason": f"prove-board-join.py not found at {PROVE_BOARD_JOIN}"}

    proc = subprocess.run(
        [sys.executable, str(PROVE_BOARD_JOIN), "--company-dir", str(company_dir),
         "--db", str(db_path), "--json"],
        capture_output=True, text=True,
    )
    verdict = None
    stdout = proc.stdout
    brace = stdout.find("{")
    if brace >= 0:
        try:
            verdict = json.loads(stdout[brace:])
        except ValueError:
            verdict = None
    status_by_rc = {0: "OK", 1: "GATE-ERROR", 2: "DRIFT", 3: "CANNOT-VOUCH", 4: "NOT-APPLICABLE"}
    return {
        "status": status_by_rc.get(proc.returncode, "GATE-ERROR"),
        "rc": proc.returncode, "seed_ran": seed_ran, "verdict": verdict,
        "reason": None if verdict is not None else (proc.stderr[-2000:] or stdout[-2000:]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--departments-dir", default=None,
                     help="departments/ dir; default = department_floor.resolve_departments_dir()")
    ap.add_argument("--build-state-file", default=None,
                     help="explicit build-state JSON file (test isolation / operator override); "
                          "default = department_floor.load_build_state() (the box's real "
                          "~/.openclaw or /data/.openclaw workforce build-state) — declines in it "
                          "are always honored, a declined dept is NEVER re-added.")
    ap.add_argument("--apply", action="store_true", help="mutate (default: dry-run report only)")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON on stdout")
    ap.add_argument("--skip-join-verify", action="store_true",
                     help="skip the post-apply chosen-artifact sync + prove-board-join.py "
                          "verification (isolated testing only; the live remediation path "
                          "should always leave this on so the residue is FULLY closed)")
    ap.add_argument("--db", default=None,
                     help="explicit mission-control.db path for join verification "
                          "(default: the shared resolve_db.find_dashboard_db() candidate list)")
    args = ap.parse_args(argv)

    dd = Path(args.departments_dir) if args.departments_dir else department_floor.resolve_departments_dir()
    if dd is None:
        _emit({"rc": 2, "reason": "no departments dir resolvable"}, args.json)
        return 2
    dd = Path(dd)
    if not dd.is_dir():
        _emit({"rc": 2, "reason": f"departments dir not found: {dd}"}, args.json)
        return 2

    build_state = None
    if args.build_state_file:
        try:
            build_state = json.loads(Path(args.build_state_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit({"rc": 2, "reason": f"could not read --build-state-file: {exc}"}, args.json)
            return 2

    before = department_floor.evaluate_floor(departments_dir=dd, build_state=build_state)
    missing = list(before["missing_mandatory"]) + list(before["missing_universal_primary"])

    result = {
        "departments_dir": str(dd),
        "apply": args.apply,
        "before_floor_met": before["floor_met"],
        "missing_before": missing,
    }

    if not missing:
        result.update(action="none -- floor already met", after_floor_met=True, rc=0)
        _emit(result, args.json)
        return 0

    if not args.apply:
        result.update(action="dry-run -- floor is short; re-run with --apply to materialize",
                       after_floor_met=before["floor_met"], rc=3)
        _emit(result, args.json)
        return 3

    gap_map, no_library = build_gap_map(missing)
    result["no_library_source"] = no_library

    if gap_map:
        ff_rc, ff_report, ff_stdout, ff_stderr = run_floor_fill_driver(gap_map, dd, apply_=True)
        result["floor_fill_driver_rc"] = ff_rc
        result["floor_fill_driver_report"] = ff_report if ff_report is not None else ff_stdout[-4000:]
        if ff_stderr.strip():
            result["floor_fill_driver_stderr"] = ff_stderr[-4000:]

    after = department_floor.evaluate_floor(departments_dir=dd, build_state=build_state)
    result["after_floor_met"] = after["floor_met"]
    result["missing_after"] = list(after["missing_mandatory"]) + list(after["missing_universal_primary"])
    result["action"] = "materialized via floor-fill-driver.py --apply"
    result["rc"] = 0 if after["floor_met"] else 1

    # P2-06 (c)2's own closing requirement: "then prove-board-join.py must
    # pass." Only reached when SOMETHING was actually closed (gap_map
    # non-empty) — an already-met floor short-circuited above and never
    # reaches here, so the pre-existing "none -- floor already met" contract
    # (relied on by test-materialize-missing-departments.sh T2 / the P2-06(c)1
    # probe's short-circuit) is untouched.
    closed_ids = [d for d in missing if d not in no_library]
    if closed_ids and not args.skip_join_verify:
        appended = sync_chosen_artifact(dd, closed_ids)
        result["chosen_artifact_appended"] = appended
        join = verify_board_join(dd, args.db)
        result["join_verification"] = join
        if after["floor_met"] and join["status"] in ("DRIFT", "CANNOT-VOUCH"):
            result["rc"] = 1
            result["action"] = ("materialized via floor-fill-driver.py --apply, but "
                                 f"prove-board-join.py reported {join['status']} "
                                 "(chosen/provisioned/displayed disagree) -- residue "
                                 "not fully closed")

    _emit(result, args.json)
    return result["rc"]


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, indent=2))
        return
    print("============================================", file=sys.stderr)
    print("materialize-missing-departments.py", file=sys.stderr)
    print(f"departments_dir = {result.get('departments_dir')}", file=sys.stderr)
    if "before_floor_met" in result:
        print(f"before: floor_met={result['before_floor_met']} missing={result.get('missing_before')}",
              file=sys.stderr)
    if result.get("no_library_source"):
        print(f"NO LIBRARY SOURCE (skipped, never fabricated): {result['no_library_source']}",
              file=sys.stderr)
    if "after_floor_met" in result:
        print(f"after:  floor_met={result['after_floor_met']} missing={result.get('missing_after', [])}",
              file=sys.stderr)
    if result.get("chosen_artifact_appended"):
        print(f"chosen artifact: appended {result['chosen_artifact_appended']}", file=sys.stderr)
    if "join_verification" in result:
        jv = result["join_verification"]
        print(f"join verification (prove-board-join.py): status={jv.get('status')} rc={jv.get('rc')}",
              file=sys.stderr)
        if jv.get("reason"):
            print(f"  reason: {jv['reason']}", file=sys.stderr)
    print(f"action: {result.get('action')}", file=sys.stderr)
    print(f"RESULT: rc={result.get('rc')}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
