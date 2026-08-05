#!/usr/bin/env python3
"""
prebuild-standard-workforce.py — PHASE 2 engine of the AI Workforce
standard-first redesign (master plan 2026-08-04).

THE STANDARD PREBUILD: materialize the FULL canonical department floor for a
new client box at ONBOARDING (operator-triggered, BEFORE the interview), so
the interview EDITS an already-built company instead of gathering a plan that
a later build creates. This is a TIMING change on already-standardized
content, not a semantic change to the floor: the floor is still the live
naming-map floor (mandatory + universal-primary, read from
department-naming-map.json at runtime — NEVER a hardcoded count here), and a
provenanced decline is still the only way a department leaves it.

CONTRACT (master plan PHASE 2, in execution order):

  1. CONSENT GATE (fail-closed, mirrors _enforce_consent_or_refuse in
     build-workforce.py). The prebuild runs BEFORE the owner has said
     anything, so the ONLY honest consenting party is the OPERATOR. An
     explicit, provenanced operator-consent record is REQUIRED — same shape
     as ownerConsent ({decision, source, decidedAt, decidedBy, sessionId},
     all five present and truthy) with source == "operator-prebuild". No
     record, a malformed record, or a wrong source REFUSES (exit 2).
     Additionally:
       - interviewComplete == true in the build-state REFUSES (exit 4) — the
         prebuild is a pre-interview action; a box that already finished its
         interview builds via the apply-diff / legacy lane, never here.
       - buildType handling (frozen in-flight clients = legacy ruling):
           buildType == "standard-first"   -> proceed (idempotent resume).
           buildType ABSENT                -> decision "prebuild" WRITES
                                              buildType = "standard-first"
                                              (the new-box path; the consent
                                              explicitly authorizes the lane).
           buildType == "legacy"           -> REFUSES (exit 5) UNLESS the
                                              consent decision is the explicit
                                              "prebuild-and-convert-legacy",
                                              which overwrites it. A frozen
                                              box is never converted by the
                                              default path.
  2. FLOOR RESOLUTION: department_floor.evaluate_floor() over the live naming
     map (mandatory_ids + universal_primary_vertical_departments, minus any
     provenanced declines in the build-state — at onboarding there are none).
     The count is derived live; this script never restates it.
  3. MATERIALIZATION: drives the ALREADY-SHIPPED materializer
     23-ai-workforce-blueprint/scripts/materialize-missing-departments.py,
     which itself drives floor-fill-driver.py + create_role_workspaces.py
     (additive-only, skip-existing, no-clobber, dry-run default, library-
     sourced). It resolves every department's role roster through
     create_role_workspaces.normalize_dept() — the alias-trap guard: the
     library keys billing roles under 'billing' and legal roles under
     'legal-compliance', so 'billing-finance' / 'legal' floor ids must go
     through normalize_dept or two EMPTY departments get materialized.
     This engine never copies from any other client's tree.
  4. PERSONAS: generate-governing-personas.sh stamps governing-personas.md
     per department (token-fill only, NO LLM authoring — the SKILL.md:489
     boundary).
  5. SOP DECISION (Trevor's GO, ruling (a)): the shipped SOP library (140
     SOPs, 82 of them in presentations) CANNOT satisfy the substantive-SOP
     floor (>=4 substantive SOPs per role at >=7KB + DMAIC) by copy. The
     materializer copies every SOP the library HAS (scaffold_department's
     sops/ fill — most departments have 0-6); departments the library cannot
     fill stay sopLibraryStatus = "pending" so the library gate remains
     ARMED and the interview / post-interview personalization completes them.
     This driver NEVER fabricates SOP stub content (a stub file is exactly
     what the substance gate fails on); the pending status is the tracking
     mechanism (ruling (a), gate-consistent form).
  6. CHOSEN ARTIFACT: build-workforce.write_chosen_departments_artifact()
     writes <company_dir>/departments.json (CC schema, CEO column first) +
     build-state canonicalReconciliation.chosenDepartments — the MERGE-
     NEVER-REPLACE U109 writer, so the three-layer join contract
     (chosen == provisioned == displayed) holds from day one.
  7. CC SEEDING: 32-command-center-setup/scripts/seed-workspaces.py
     (INSERT OR IGNORE, idempotent) against an EXPLICIT db only, then
     prove-board-join.py must PASS (rc 0). No db provided -> NOT-APPLICABLE
     (a box with no Command Center wired in yet has nothing to join — this
     is recorded, never silently skipped).
  8. STATE WRITE: buildType = "standard-first"; standardPrebuild =
     {status: "done", standardReadyAt, floorVersion
     ("<naming-map version>@<git sha>"), prebuiltDepartments[],
     agentRegistration: "deferred", source, operatorConsentRef};
     departments[] seeded with status "prebuilt" (NOT "pending" — this
     distinction keeps the resume cron from ever counting a prebuilt
     department as pending-build work, master plan PHASE 5); the validated
     operator consent record is preserved at build-state["operatorConsent"]
     for the audit trail. A run that dies mid-flight leaves status
     "pending" (or "failed" + standardPrebuildFailureReason when the engine
     can still write) so a re-run RESUMES instead of restarting.
  9. PROGRESS: build-progress.json via build-workforce.write_build_progress()
     so /onboarding/building renders the prebuild live.

EXPLICITLY OUT OF SCOPE (never done here):
  - agents.list registration — DEFERRED to interviewComplete for
    confirmed-kept departments only (lazy registration, the deferred
    Moment 3.5 inside the apply-diff build). This engine never touches
    openclaw.json.
  - verticalPacks record — industry is unknown pre-interview; the U107
    derivation guard must see nothing declared (industry-gated extras stay
    gated until the interview declares them).
  - ANY LLM content authoring, ANY interviewProgress / interviewQc write,
    ANY interviewComplete write (anti-fabrication: the prebuild is
    operator-initiated, library-sourced, and records no owner answers).
  - Skill-38 comms-automation handoff — suppressed on standardPrebuilt
    until interviewComplete.
  - cron registration of ANY kind: this is a ONE-SHOT operator-run driver
    (ZHC-BUILDOUT-EXPERIENCE.md:122-126 token-runaway doctrine — nothing
    that fires forever). It self-disables by construction: it registers
    nothing that could re-fire it.

NO-CO-MINGLING (binding, SKILL.md:41-43 / NO-COMINGLING-RULE.md): this
driver sources EXCLUSIVELY from templates/role-library/ via the shipped
materializers (materialize-missing-departments.py -> floor-fill-driver.py ->
create_role_workspaces.create_role_workspace's try_library_fill). Copying
from another client's tree is a hard violation and is structurally
impossible here: no other client path is ever read.

USAGE
  python3 prebuild-standard-workforce.py --operator-consent-file <consent.json>
            [--departments-dir <dir>] [--company-dir <dir>]
            [--company-name <name>] [--company-slug <slug>]
            [--build-state-file <state.json>] [--db <mission-control.db>]
            [--apply] [--json]

  DEFAULT IS DRY-RUN: without --apply nothing is mutated (the materializer's
  own dry-run is driven, personas run --dry-run, and every write this engine
  owns is REPORTED, not performed). Pass --apply to materialize.

  --build-state-file / --db exist for SCRATCH-company isolation (the operator
  box is itself a built client with a live 60+-department tree and a live
  Command Center database — canary runs MUST use a scratch company dir + a
  scratch db + a scratch build-state, never the operator's live ones;
  materialize-missing-departments.py's explicit-signal-only discipline is the
  precedent). When --build-state-file is given, this engine also redirects
  build-workforce's build-state reads/writes to that file so the chosen-
  artifact writer cannot touch the live state.

EXIT CODES
  0  success (--apply: floor met + join OK/NOT-APPLICABLE + state written;
     dry-run: plan computed, nothing mutated)
  1  a step failed (materializer rc 1/2, personas hard-fail, state write
     impossible, floor still short after --apply)
  2  usage error / consent gate refusal (missing or malformed operator
     consent record, wrong source) — fail-closed
  4  interviewComplete is already true — prebuild refused
  5  buildType lane refusal (box frozen as "legacy" without an explicit
     convert consent)
  7  Command Center board join verification failed (DRIFT / CANNOT-VOUCH /
     GATE-ERROR) after --apply — chosen/provisioned/displayed disagree or
     could not be proven; needs operator attention
"""
import argparse
import importlib.util as _ilu
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parent

# The operator consent source token (mirrors ownerConsent's source field).
OPERATOR_CONSENT_SOURCE = "operator-prebuild"

# Consent decisions this gate accepts. "prebuild" authorizes the prebuild and
# sets buildType=standard-first on a box whose buildType is ABSENT (the
# new-box path); it REFUSES a box explicitly frozen "legacy".
# "prebuild-and-convert-legacy" is the deliberate, audit-recorded operator
# action that converts an explicitly-legacy box (frozen in-flight clients are
# never converted by the default path — only by this explicit decision).
_CONSENT_DECISION_PREBUILD = "prebuild"
_CONSENT_DECISION_CONVERT = "prebuild-and-convert-legacy"
_ACCEPTED_DECISIONS = frozenset({_CONSENT_DECISION_PREBUILD, _CONSENT_DECISION_CONVERT})

# Exit codes (documented in the module docstring).
EXIT_OK = 0
EXIT_STEP_FAILED = 1
EXIT_CONSENT_REFUSED = 2
EXIT_INTERVIEW_COMPLETE = 4
EXIT_LANE_REFUSED = 5
EXIT_JOIN_FAILED = 7

# Join verdicts that block success (mirrors materialize-missing-departments.py).
_BLOCKING_JOIN_STATUSES = ("DRIFT", "CANNOT-VOUCH", "GATE-ERROR")


def _log(msg):
    print(f"[prebuild-standard] {msg}", file=sys.stderr)


def _resolve_skill23_scripts():
    """Locate the Skill 23 scripts dir (the shipped materializers live there).
    Precedence: explicit env override, then this repo's skill checkout, then
    the two installed-skill locations. Fail-closed: None -> usage error."""
    env_dir = os.environ.get("SKILL23_SCRIPTS_DIR", "").strip()
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend([
        REPO_ROOT / "23-ai-workforce-blueprint" / "scripts",
        Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint" / "scripts",
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint/scripts"),
    ])
    for c in candidates:
        if (c / "materialize-missing-departments.py").is_file() and (c / "department-floor.py").is_file():
            return c
    return None


def _load_module(mod_name, path):
    """Import a hyphenated script as a module (the importlib.util technique
    materialize-missing-departments.py itself uses)."""
    spec = _ilu.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = _ilu.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).parent))
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── CONSENT GATE ─────────────────────────────────────────────────────────────

def _validate_operator_consent(consent):
    """Validate the operator consent record. Mirrors build-workforce.py's
    _validate_owner_consent() provenance rule: every required field present
    and truthy; the source must be exactly the operator-prebuild token; the
    decision must be an accepted prebuild decision. Returns (ok, reason)."""
    if not isinstance(consent, dict):
        return False, "operator consent record is not a JSON object"
    required = ["decision", "source", "decidedAt", "decidedBy", "sessionId"]
    missing = [f for f in required if not str(consent.get(f) or "").strip()]
    if missing:
        return False, f"operator consent missing/empty fields: {', '.join(missing)}"
    source = str(consent.get("source")).strip()
    if source != OPERATOR_CONSENT_SOURCE:
        return False, (f"operator consent source='{source}' is not "
                       f"'{OPERATOR_CONSENT_SOURCE}' — only the operator-prebuild "
                       "consent form authorizes a standard prebuild")
    decision = str(consent.get("decision")).strip().lower().replace("_", "-")
    if decision not in _ACCEPTED_DECISIONS:
        return False, (f"operator consent decision='{consent.get('decision')}' is not "
                       f"one of {sorted(_ACCEPTED_DECISIONS)}")
    return True, ""


def _refuse(result, rc, reason):
    result["rc"] = rc
    result["refused"] = True
    result["reason"] = reason
    _log(f"REFUSED (rc={rc}): {reason}")
    return rc


# ── FLOOR RESOLUTION ─────────────────────────────────────────────────────────

def _universal_primary_dept_info(bw, dept_id):
    """Resolve {name, emoji, head, description} for a universal-primary dept
    from the SAME vertical_packs source build-workforce.apply_vertical_packs()
    reads (never a second, hand-maintained source of truth). Mirrors
    materialize-missing-departments.py's helper of the same name."""
    packs = bw._load_vertical_packs() or {}
    for _pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if isinstance(dept, dict) and dept.get("id") == dept_id and dept.get("universal_primary"):
                name = dept.get("name", dept_id.replace("-", " ").title())
                return {"name": name, "emoji": dept.get("emoji", "\U0001f4c1"),
                        "head": f"Director of {name}",
                        "description": dept.get("one_liner", "")}
    return None


def _master_orchestrator_info(df):
    """master-orchestrator is a FLOOR-ONLY mandatory id with no decline path
    (naming map v2.8.0): build-workforce.load_canonical_floor() deliberately
    excludes it (it is provisioned outside the interview as the CEO column),
    so resolve its display info straight from the naming map."""
    nm = df.load_naming_map()
    m = (nm.get("mandatory") or {}).get("master-orchestrator") or {}
    return {
        "name": m.get("display_name", "Master Orchestrator"),
        "emoji": m.get("emoji", "\U0001f9e0"),
        "head": m.get("director_title", "Master Orchestrator"),
        "description": m.get("one_liner", ""),
    }


# ── STATE IO ─────────────────────────────────────────────────────────────────

def _load_state(state_path):
    try:
        return json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _atomic_write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _git_short_sha():
    """The onboarding repo git sha for the floorVersion provenance pin.
    Best-effort: 'unknown' when git is unavailable (never fatal)."""
    try:
        proc = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=15)
        sha = proc.stdout.strip()
        return sha if proc.returncode == 0 and sha else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ── CC SEEDING + JOIN PROOF ──────────────────────────────────────────────────

def _ensure_company_config(company_dir, company_slug, company_name, apply_, result):
    """Write <company_dir>/company-config.json (additive — never clobbers an
    existing file). seed-workspaces.find_company_info() derives the company
    slug from this file (it does NOT honor $COMPANY_SLUG), so this is the
    single mechanism that pins workspaces.company_id to the prebuild's slug.
    Without it a company named 'Scratch Canary Co' seeds under
    'scratch-canary-co' and prove-board-join's company-scoped join cannot
    vouch for the slug the prebuild recorded."""
    cfg_path = company_dir / "company-config.json"
    if cfg_path.is_file():
        result["company_config"] = f"kept existing {cfg_path} (never clobber)"
        return
    payload = {"name": company_name or company_slug.replace("-", " ").title(),
               "slug": company_slug}
    if apply_:
        try:
            _atomic_write_json(cfg_path, payload)
            result["company_config"] = str(cfg_path)
        except OSError as exc:
            result["company_config"] = f"could not write {cfg_path}: {exc}"
    else:
        result["company_config"] = f"would write {cfg_path} ({payload})"


def _seed_cc_and_prove_join(skill23, company_dir, db_path, company_slug):
    """Seed the Command Center workspaces table (idempotent INSERT OR IGNORE)
    then PROVE chosen == provisioned == displayed with prove-board-join.py.
    EXPLICIT db only (the _find_cc_db explicit-signal discipline). Returns a
    verdict dict {status, seed_rc, join_rc, reason}."""
    seed_script = REPO_ROOT / "32-command-center-setup" / "scripts" / "seed-workspaces.py"
    prove_script = skill23 / "prove-board-join.py"

    # The shared db resolver (resolve_db.find_dashboard_db) and
    # seed-workspaces.find_db both require the db file to ALREADY EXIST
    # (.exists() / .is_file() checks) — a scratch canary run starts from no
    # Command Center, so create the empty file first: sqlite3.connect() treats
    # a zero-byte file as a fresh database and seed() creates the schema.
    try:
        db_path = Path(db_path)
        if not db_path.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.touch()
    except OSError as exc:
        return {"status": "GATE-ERROR", "seed_rc": None, "join_rc": None,
                "reason": f"could not create Command Center database at {db_path}: {exc}"}

    env = dict(os.environ)
    env["DASHBOARD_DB_PATH"] = str(db_path)
    env["DATABASE_PATH"] = str(db_path)
    env["COMPANY_SLUG"] = company_slug
    # Deliberately NOT setting COMPANY_NAME: seed-workspaces.find_company_info()
    # gives the COMPANY_NAME env var TOP precedence, and when it is set the
    # company slug is re-derived from the NAME ('Scratch Canary Co' ->
    # 'scratch-canary-co'), bypassing company-config.json's pinned slug and
    # breaking prove-board-join's company-scoped join. company-config.json
    # (written by _ensure_company_config) carries BOTH the name and the slug,
    # so the env var must stay unset for the pin to hold.
    env.pop("COMPANY_NAME", None)

    seed_rc = None
    if seed_script.is_file():
        seed_rc = subprocess.run(
            [sys.executable, str(seed_script)],
            capture_output=True, text=True, env=env,
        ).returncode
        _log(f"seed-workspaces.py rc={seed_rc} (db={db_path}, slug={company_slug})")
    else:
        return {"status": "GATE-ERROR", "seed_rc": None, "join_rc": None,
                "reason": f"seed-workspaces.py not found at {seed_script}"}

    if not prove_script.is_file():
        return {"status": "GATE-ERROR", "seed_rc": seed_rc, "join_rc": None,
                "reason": f"prove-board-join.py not found at {prove_script}"}

    proc = subprocess.run(
        [sys.executable, str(prove_script),
         "--company-dir", str(company_dir), "--db", str(db_path),
         "--company-slug", company_slug, "--json"],
        capture_output=True, text=True,
    )
    status_by_rc = {0: "OK", 1: "GATE-ERROR", 2: "DRIFT", 3: "CANNOT-VOUCH", 4: "NOT-APPLICABLE"}
    status = status_by_rc.get(proc.returncode, "GATE-ERROR")
    reason = None
    if status != "OK":
        reason = (proc.stderr or proc.stdout or "")[-2000:]
    return {"status": status, "seed_rc": seed_rc, "join_rc": proc.returncode,
            "reason": reason}


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--operator-consent-file", default=None,
                    help="REQUIRED. Path to the operator consent JSON record "
                         "{decision, source='operator-prebuild', decidedAt, decidedBy, "
                         "sessionId}. No record -> the prebuild is REFUSED (fail-closed).")
    ap.add_argument("--departments-dir", default=None,
                    help="departments/ dir to prebuild into (default: "
                         "department_floor.resolve_departments_dir() — the box's live "
                         "company; SCRATCH runs must pass this explicitly)")
    ap.add_argument("--company-dir", default=None,
                    help="ZHC company dir (parent of departments/); default = parent of "
                         "--departments-dir")
    ap.add_argument("--company-name", default=None, help="company display name (CC seeding)")
    ap.add_argument("--company-slug", default=None,
                    help="company slug (default: company dir basename)")
    ap.add_argument("--build-state-file", default=None,
                    help="explicit build-state JSON (scratch isolation; also redirects "
                         "build-workforce's state reads/writes so the live state is never "
                         "touched by a scratch run)")
    ap.add_argument("--db", default=None,
                    help="explicit mission-control.db for CC seeding + join proof "
                         "(or $DASHBOARD_DB_PATH / $DATABASE_PATH). EXPLICIT-SIGNAL ONLY — "
                         "with none set, CC seeding + join proof are NOT-APPLICABLE and "
                         "recorded as such.")
    ap.add_argument("--apply", action="store_true",
                    help="mutate (default: dry-run report only)")
    ap.add_argument("--json", action="store_true", help="emit the result JSON on stdout")
    args = ap.parse_args(argv)

    result = {
        "driver": "prebuild-standard-workforce",
        "phase": "PHASE-2-standard-prebuild",
        "apply": args.apply,
        "startedAt": _now_iso(),
    }

    def emit(rc):
        result["rc"] = rc
        result["finishedAt"] = _now_iso()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            _log(f"RESULT: rc={rc} "
                 f"({'APPLY' if args.apply else 'DRY-RUN'}, "
                 f"status={result.get('standardPrebuildStatus', 'n/a')})")
        return rc

    # ── locate the Skill 23 machinery ──
    skill23 = _resolve_skill23_scripts()
    if skill23 is None:
        result["reason"] = ("Skill 23 scripts dir not found (checked $SKILL23_SCRIPTS_DIR, "
                            "this repo's 23-ai-workforce-blueprint/scripts/, and the "
                            "installed-skill locations)")
        return emit(EXIT_STEP_FAILED)
    df = _load_module("department_floor__prebuild", skill23 / "department-floor.py")
    bw = _load_module("build_workforce__prebuild", skill23 / "build-workforce.py")

    # ── resolve target company dir / departments dir ──
    if args.departments_dir:
        dd = Path(args.departments_dir)
    else:
        dd = df.resolve_departments_dir()
        if dd is None:
            result["reason"] = ("no departments dir resolvable on this box — pass "
                                "--departments-dir for a scratch prebuild")
            return emit(EXIT_STEP_FAILED)
    dd = Path(dd)
    company_dir = Path(args.company_dir) if args.company_dir else dd.parent
    company_slug = (args.company_slug or company_dir.name or "").strip().lower()
    company_slug = re.sub(r"[^a-z0-9]+", "-", company_slug).strip("-") or "standard-prebuild"
    result["departments_dir"] = str(dd)
    result["company_dir"] = str(company_dir)
    result["company_slug"] = company_slug

    # ── build-state path (explicit scratch file wins; else the box's real one) ──
    state_path = Path(args.build_state_file) if args.build_state_file else Path(bw._build_state_path())
    result["build_state_file"] = str(state_path)
    state = _load_state(state_path)

    # SCRATCH ISOLATION: when an explicit build-state file is given, redirect
    # build-workforce's own state reads/writes to it so write_chosen_departments_
    # artifact() can never touch the live state. Both functions are resolved via
    # the module's globals at call time, so rebinding here is sufficient.
    if args.build_state_file:
        bw._build_state_path = lambda: str(state_path)  # type: ignore[method-assign]
        bw._load_build_state = lambda: _load_state(state_path)  # type: ignore[method-assign]

    # ══ STEP 1 — CONSENT GATE (fail-closed, before ANY mutation) ══
    if not args.operator_consent_file:
        return emit(_refuse(result, EXIT_CONSENT_REFUSED,
                            "--operator-consent-file is REQUIRED: the prebuild runs before "
                            "the owner has said anything, so only an explicit, provenanced "
                            "OPERATOR consent record (source='operator-prebuild') can "
                            "authorize it"))
    try:
        consent = json.loads(Path(args.operator_consent_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return emit(_refuse(result, EXIT_CONSENT_REFUSED,
                            f"could not read operator consent file: {exc}"))
    ok, reason = _validate_operator_consent(consent)
    if not ok:
        return emit(_refuse(result, EXIT_CONSENT_REFUSED, reason))
    consent["decision"] = str(consent["decision"]).strip().lower().replace("_", "-")
    result["operatorConsent"] = {
        "decision": consent["decision"], "decidedBy": consent["decidedBy"],
        "decidedAt": consent["decidedAt"], "sessionId": consent["sessionId"],
    }
    _log(f"operator consent verified (decidedBy={consent['decidedBy']}, "
         f"decision={consent['decision']})")

    # interviewComplete already true -> the interview lane owns this box now.
    if state.get("interviewComplete") is True:
        return emit(_refuse(result, EXIT_INTERVIEW_COMPLETE,
                            "interviewComplete is already true — the standard prebuild is a "
                            "PRE-interview action; this box builds via the interview lane "
                            "(apply-diff in standard-first mode)"))

    # buildType lane gate (frozen in-flight clients default to legacy).
    build_type = state.get("buildType")
    decision = consent["decision"]
    if build_type == "standard-first":
        pass  # idempotent resume of the standard-first lane
    elif build_type is None:
        if not args.apply:
            result["buildTypeAction"] = "would set buildType=standard-first (consent-authorized)"
        # written in the final state-write step (apply only)
    elif build_type == "legacy":
        if decision != _CONSENT_DECISION_CONVERT:
            return emit(_refuse(
                result, EXIT_LANE_REFUSED,
                "buildType is 'legacy' (frozen in-flight client) — the default prebuild "
                "consent does not convert it. If this box must move to the standard-first "
                "lane, record a NEW operator consent with decision "
                f"'{_CONSENT_DECISION_CONVERT}'."))
        if not args.apply:
            result["buildTypeAction"] = "would CONVERT buildType legacy -> standard-first (explicit consent)"
    else:
        return emit(_refuse(result, EXIT_LANE_REFUSED,
                            f"buildType '{build_type}' is unrecognized — refusing"))

    # ══ STEP 2 — FLOOR RESOLUTION (live naming map, declines honored) ══
    if args.apply:
        dd.mkdir(parents=True, exist_ok=True)
    verdict_before = df.evaluate_floor(departments_dir=dd, build_state=state)
    expected_floor = list(verdict_before["expected_floor"])
    result["naming_map_version"] = (df.load_naming_map() or {}).get("version")
    result["expected_floor_count"] = len(expected_floor)
    result["expected_floor"] = expected_floor
    result["declines_honored"] = verdict_before.get("declined", [])
    _log(f"floor resolved live: {len(expected_floor)} departments "
         f"({len(verdict_before['mandatory'])} mandatory incl. master-orchestrator + "
         f"{len(verdict_before['universal_primary_vertical'])} universal-primary, "
         f"minus {len(result['declines_honored'])} provenanced declines)")

    if not expected_floor:
        return emit(_refuse(result, EXIT_STEP_FAILED,
                            "the live floor resolved to ZERO departments — the naming map "
                            "is unreadable AND the hardcoded fallback failed; refusing to "
                            "prebuild nothing"))

    # ══ STEP 3 — MATERIALIZATION (shipped materializer, additive-only) ══
    mat_script = skill23 / "materialize-missing-departments.py"
    mat_cmd = [sys.executable, str(mat_script), "--departments-dir", str(dd), "--json",
               "--skip-join-verify"]  # the driver proves the join itself, over the FULL floor
    if args.build_state_file:
        mat_cmd += ["--build-state-file", str(state_path)]
    if args.apply:
        mat_cmd.append("--apply")
    _log(f"driving materializer ({'APPLY' if args.apply else 'dry-run'}): "
         f"{' '.join(mat_cmd[1:])}")
    mat_proc = subprocess.run(mat_cmd, capture_output=True, text=True)
    mat_report = None
    try:
        brace = mat_proc.stdout.find("{")
        if brace >= 0:
            mat_report = json.loads(mat_proc.stdout[brace:])
    except ValueError:
        mat_report = None
    result["materializer_rc"] = mat_proc.returncode
    result["materializer"] = mat_report if mat_report is not None else (mat_proc.stdout or "")[-4000:]
    if mat_proc.returncode not in (0, 3):
        # rc 1 = still short after --apply OR no_library_source gaps; rc 2 = usage error.
        # rc 3 = dry-run with a short floor (EXPECTED in dry-run mode).
        if args.apply:
            result["standardPrebuildStatus"] = "failed"
            result["reason"] = (f"materializer rc={mat_proc.returncode}: "
                                f"{(mat_report or {}).get('reason') or 'see materializer output'}")
            return emit(EXIT_STEP_FAILED)
        # dry-run: a short floor is exactly what the dry-run reports
    if args.apply and mat_proc.returncode == 0 and (mat_report or {}).get("after_floor_met") is False:
        result["standardPrebuildStatus"] = "failed"
        result["reason"] = "materializer returned 0 but reports the floor still short"
        return emit(EXIT_STEP_FAILED)

    # ══ STEP 4 — PERSONAS (token-fill only, never LLM-authored) ══
    persona_script = skill23 / "generate-governing-personas.sh"
    if persona_script.is_file():
        penv = dict(os.environ)
        penv["DEPARTMENTS_DIR"] = str(dd)
        pcmd = ["bash", str(persona_script)]
        if not args.apply:
            pcmd.append("--dry-run")
        _log(f"stamping governing personas ({'APPLY' if args.apply else 'dry-run'})")
        pproc = subprocess.run(pcmd, capture_output=True, text=True, env=penv)
        result["personas_rc"] = pproc.returncode
        if pproc.returncode != 0 and args.apply:
            result["standardPrebuildStatus"] = "failed"
            result["reason"] = (f"generate-governing-personas.sh rc={pproc.returncode}: "
                                f"{(pproc.stderr or pproc.stdout or '')[-1500:]}")
            return emit(EXIT_STEP_FAILED)
    else:
        result["personas_rc"] = None
        _log("WARNING: generate-governing-personas.sh not found — personas step skipped")

    # ══ STEP 5 — SOP DECISION provenance (ruling (a), gate-consistent) ══
    # The library's SOPs are copied by the materializer's scaffold where the
    # library HAS them; departments it cannot fill stay sopLibraryStatus
    # 'pending' (written in the state step) so the substantive-SOP gate stays
    # ARMED for the interview / personalization. No stub files are ever
    # fabricated here.
    result["sopDecision"] = {
        "ruling": "a-pending-tracked",
        "sopLibraryStatus": "pending",
        "note": ("library SOPs copied where the library has them; the substantive-SOP "
                 "floor remains the interview/personalization step's job; no stub content "
                 "is fabricated pre-interview"),
    }

    # ══ STEP 6 — CHOSEN ARTIFACT (the three-layer join, layer 1) ══
    floor_info = bw.load_canonical_floor()  # the 23 buildable mandatory (live)
    selected = {}
    for cid in expected_floor:
        if cid in ("ceo", "dept-ceo"):
            continue
        if cid in floor_info:
            selected[cid] = floor_info[cid]
        elif cid == "master-orchestrator":
            selected[cid] = _master_orchestrator_info(df)
        else:
            info = _universal_primary_dept_info(bw, cid)
            if info is None:
                nm_mandatory = (df.load_naming_map().get("mandatory") or {}).get(cid) or {}
                info = {"name": nm_mandatory.get("display_name", cid.replace("-", " ").title()),
                        "emoji": nm_mandatory.get("emoji", "\U0001f4c1"),
                        "head": nm_mandatory.get("director_title", f"Director of {cid}"),
                        "description": nm_mandatory.get("one_liner", "")}
            selected[cid] = info

    bw.COMPANY_DIR = str(company_dir)  # write_build_progress + artifact target
    if args.apply:
        written = bw.write_chosen_departments_artifact(
            selected, company_dir=str(company_dir),
            source="prebuild-standard-workforce")
        result["chosen_artifact_written"] = written
        _log(f"chosen artifact: {written}")
    else:
        result["chosen_artifact_written"] = []
        result["chosen_artifact_plan"] = (
            f"would write {company_dir / 'departments.json'} with CEO column + "
            f"{len(selected)} floor departments via write_chosen_departments_artifact()")

    # ══ STEP 9 (first emit) — PROGRESS for /onboarding/building ══
    if args.apply:
        bw.write_build_progress(
            "prebuild-standard",
            "Pre-building your standard company foundation from the canonical library...",
            departments=[{"slug": cid, "status": "prebuilt",
                          "roles_total": len((mat_report or {}).get("missing_before", []) or [])}
                         for cid in selected],
            started_at=result["startedAt"])

    # ══ STEP 7 — CC SEEDING + JOIN PROOF (layers 2+3) ══
    _ensure_company_config(company_dir, company_slug, args.company_name,
                           args.apply, result)
    db_path = None
    if args.db:
        p = Path(args.db)
        if p.is_file():
            db_path = p
        elif p.parent.is_dir():
            # Not yet created: seed-workspaces.py's sqlite3.connect() creates
            # the file (scratch canary runs start from no CC database). Accept
            # any path inside an existing directory; a path whose parent does
            # not exist is a typo, not a target.
            db_path = p
            result["cc_db_will_create"] = str(p)
        else:
            result["cc_db"] = f"--db {args.db}: no such file and its parent directory does not exist"
    if db_path is None:
        for env_var in ("DASHBOARD_DB_PATH", "DATABASE_PATH"):
            v = os.environ.get(env_var)
            if v and Path(v).is_file():
                db_path = Path(v)
                break

    if db_path is None:
        result["cc_seeding"] = {
            "status": "NOT-APPLICABLE", "seed_rc": None, "join_rc": None,
            "reason": ("no Command Center database provided (checked --db / "
                       "$DASHBOARD_DB_PATH / $DATABASE_PATH ONLY — explicit-signal-only, "
                       "never ambient install-path discovery). A box with no Command "
                       "Center wired in yet has nothing to join; re-run with --db once "
                       "the CC is installed to close the displayed layer."),
        }
        _log("CC seeding + join proof: NOT-APPLICABLE (no explicit db)")
    elif not args.apply:
        result["cc_seeding"] = {
            "status": "DRY-RUN", "seed_rc": None, "join_rc": None,
            "reason": f"would seed {db_path} and prove the board join for slug '{company_slug}'",
        }
    else:
        join = _seed_cc_and_prove_join(skill23, company_dir, db_path, company_slug)
        result["cc_seeding"] = join
        _log(f"CC seeding + join proof: status={join['status']} (seed rc={join['seed_rc']}, "
             f"join rc={join['join_rc']})")
        if join["status"] in _BLOCKING_JOIN_STATUSES:
            result["standardPrebuildStatus"] = "failed"
            result["reason"] = (f"board join verification {join['status']}: chosen / "
                                "provisioned / displayed disagree or could not be proven "
                                f"({(join.get('reason') or '')[-800:]})")
            return emit(EXIT_JOIN_FAILED)

    # ══ STEP 2 (re-check) — the floor MUST be met after --apply ══
    if args.apply:
        verdict_after = df.evaluate_floor(departments_dir=dd, build_state=state)
        result["floor_met"] = bool(verdict_after["floor_met"])
        result["missing_after"] = (list(verdict_after["missing_mandatory"])
                                   + list(verdict_after["missing_universal_primary"]))
        if not verdict_after["floor_met"]:
            result["standardPrebuildStatus"] = "failed"
            result["reason"] = f"floor still short after --apply: {result['missing_after']}"
            return emit(EXIT_STEP_FAILED)
    else:
        result["floor_met"] = bool(verdict_before["floor_met"])

    # ══ STEP 8 — STATE WRITE (namespaced; never interview fields) ══
    naming_version = (df.load_naming_map() or {}).get("version") or "unknown"
    floor_version = f"{naming_version}@{_git_short_sha()}"
    prebuilt_slugs = list(expected_floor)

    if args.apply:
        new_state = _load_state(state_path)  # re-read: the chosen-artifact writer may have touched it
        new_state["buildType"] = "standard-first"
        new_state["operatorConsent"] = consent
        new_state["standardPrebuild"] = {
            "status": "done",
            "standardReadyAt": _now_iso(),
            "floorVersion": floor_version,
            "prebuiltDepartments": prebuilt_slugs,
            "agentRegistration": "deferred",
            "source": "prebuild-standard-workforce.sh",
            "operatorConsentRef": (f"{OPERATOR_CONSENT_SOURCE}/{consent['decision']}/"
                                   f"{consent['decidedAt']}/{consent['decidedBy']}"),
        }
        # departments[]: seed every prebuilt dept with status "prebuilt" (NOT
        # "pending" — this keeps the resume cron from counting prebuilt
        # departments as pending-build work; master plan PHASE 5). Merge
        # additive: an existing entry for the same slug is moved to "prebuilt";
        # entries for other slugs are carried through untouched.
        existing_depts = new_state.get("departments")
        existing_depts = existing_depts if isinstance(existing_depts, list) else []
        by_slug = {}
        for e in existing_depts:
            if isinstance(e, dict) and e.get("slug"):
                by_slug[e["slug"]] = e
        for cid in prebuilt_slugs:
            entry = by_slug.get(cid) or {"slug": cid}
            entry["name"] = selected.get(cid, {}).get("name", cid.replace("-", " ").title())
            entry["status"] = "prebuilt"
            by_slug[cid] = entry
        new_state["departments"] = list(by_slug.values())
        # required-field sentinels for a fresh state file (mirrors
        # update-interview-state.sh's seeding; interviewComplete is NEVER set
        # true by this driver — the prebuild is not the interview).
        new_state.setdefault("version", 1)
        new_state.setdefault("interviewComplete", False)
        new_state.setdefault("ownerChat", 0)
        # library + closeout gates armed pending (ruling (a)): the SOP floor is
        # the personalization step's job; a missing/non-"done" value is already
        # treated as not-done by the gates.
        if new_state.get("roleLibraryStatus") is None:
            new_state["roleLibraryStatus"] = "pending"
        if new_state.get("sopLibraryStatus") is None:
            new_state["sopLibraryStatus"] = "pending"
        if new_state.get("closeoutStatus") is None:
            new_state["closeoutStatus"] = "pending"
        try:
            _atomic_write_json(state_path, new_state)
        except OSError as exc:
            result["standardPrebuildStatus"] = "failed"
            result["reason"] = f"could not write build-state to {state_path}: {exc}"
            return emit(EXIT_STEP_FAILED)
        result["standardPrebuildStatus"] = "done"
        result["floorVersion"] = floor_version
        result["prebuilt_departments"] = prebuilt_slugs
        _log(f"state written: buildType=standard-first, standardPrebuild.status=done, "
             f"{len(prebuilt_slugs)} departments status=prebuilt -> {state_path}")

        # final progress emit (terminal)
        bw.write_build_progress(
            "prebuild-standard",
            "Your standard company foundation is pre-built. The interview tailors it.",
            departments=[{"slug": cid, "status": "prebuilt"} for cid in prebuilt_slugs],
            completed_at=_now_iso(), started_at=result["startedAt"])
    else:
        result["standardPrebuildStatus"] = "dry-run"
        result["state_plan"] = {
            "buildType": "standard-first",
            "standardPrebuild": {"status": "done", "floorVersion": floor_version,
                                 "agentRegistration": "deferred",
                                 "prebuiltDepartments": prebuilt_slugs},
            "departments_status": "prebuilt",
        }

    # ══ STEP 10 — SELF-DISABLE proof ══
    # One-shot by construction: this driver registers NO cron, NO hook, NO
    # self-ping lane — nothing exists after this exit that could re-fire it.
    result["selfDisable"] = {
        "cronRegistered": False,
        "note": ("one-shot operator-run driver; registers nothing that could re-fire it "
                 "(ZHC-BUILDOUT-EXPERIENCE.md:122-126 token-runaway doctrine)"),
    }
    return emit(EXIT_OK)


if __name__ == "__main__":
    sys.exit(main())
