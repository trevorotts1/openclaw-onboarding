#!/usr/bin/env python3
"""apply-standard-placeholder.py - STD001 standard company placeholder.

Owner order (Trevor, 2026-10-08): a client whose AI Workforce interview is still
incomplete 14+ days after onboarding started gets the STANDARD company (every
standard department, role, SOP and persona from templates/role-library/) named
after the client, so the Command Center and everything downstream can proceed.
The interview stays open; finishing it supersedes the placeholder.

It is the existing library-only standard prebuild, promoted to a usable company.
It is NOT Option B and NOT interview completion.

HARD RULE: this script never writes interviewComplete, interviewProgress,
interviewQc, buildCompletedAt, or any interview answers file. It asserts those
keys are byte-identical before and after. It never removes or overwrites anything.

Exit: 0 applied / already active / dry-run ok, 1 failure, 2 owner name unknown,
3 not eligible (reason token printed).
"""
import argparse, datetime as dt, importlib.util, json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STANDARD_PLACEHOLDER_AFTER_DAYS = 14  # Trevor 2026-10-08: "after 2 weeks ... move on"
PROTECTED_KEYS = ("interviewComplete", "interviewProgress", "interviewQc", "buildCompletedAt")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def now_dt():
    return dt.datetime.now(dt.timezone.utc)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(v):
    try:
        d = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def read_json(p):
    try:
        v = json.loads(Path(p).read_text())
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def oc_root(arg):
    if arg:
        return Path(arg)
    if os.environ.get("OPENCLAW_ROOT"):
        return Path(os.environ["OPENCLAW_ROOT"])
    return Path("/data/.openclaw") if os.path.isdir("/data/.openclaw") else Path.home() / ".openclaw"


def clock_start(root, state):
    """Earliest readable onboarding-start value. Returns (datetime, source) or (None, None)."""
    cands = []
    for src, val in (
        ("onboarding-state.seededAt", read_json(root / "workspace" / ".onboarding-state.json").get("seededAt")),
        ("onboarding-state.startedAt", read_json(root / ".onboarding-state.json").get("startedAt")),
        ("launchBootstrap.createdAt", (state.get("launchBootstrap") or {}).get("createdAt")),
    ):
        d = parse_iso(val) if val else None
        if d:
            cands.append((d, src))
    return min(cands) if cands else (None, None)


def resolve_owner(arg, state, root):
    """Never USER.md (it can name the operator)."""
    if arg and arg.strip():
        return arg.strip(), "operator-flag"
    if str(state.get("ownerName") or "").strip():
        return state["ownerName"].strip(), "build-state.ownerName"
    for p in (root / "onboarding-identity.json", root.parent / "onboarding-identity.json"):
        v = str(read_json(p).get("ownerName") or "").strip()
        if v:
            return v, "onboarding-identity.json"
    return None, None


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "standard-company"


def find_engine(root):
    skills_root = HERE.parents[1]
    for c in (skills_root / "scripts" / "prebuild-standard-workforce.py",
              root / "scripts" / "prebuild-standard-workforce.py"):
        if c.is_file():
            return c
    return None


def run(args):
    root = oc_root(args.oc_root)
    scn = _load("set_company_name", HERE / "set-company-name.py")
    state_path = args.build_state_file or str(root / "workspace" / ".workforce-build-state.json")
    from workforce_state import read, update
    state = read(state_path)

    def out(rc, line, **extra):
        if args.json:
            print(json.dumps({"rc": rc, "result": line, **extra}, indent=2))
        else:
            print(line)
        return rc

    # --- eligibility (2.3) ---
    ph = state.get("standardPlaceholder") or {}
    if state.get("companyMode") == "standard-placeholder" and ph.get("status") == "active":
        return out(0, "ALREADY_ACTIVE")
    if state.get("interviewComplete") is True:
        return out(3, "INELIGIBLE INTERVIEW_COMPLETE")
    if state.get("buildCompletedAt") or state.get("closeoutStatus") in ("done", "sent"):
        return out(3, "INELIGIBLE BUILT_COMPANY")
    if state.get("buildType") == "legacy":
        return out(3, "INELIGIBLE LEGACY_FROZEN")
    start, start_src = clock_start(root, state)
    days = None
    if start is None:
        if not args.force:
            return out(3, "INELIGIBLE CLOCK_UNKNOWN")
    else:
        days = (now_dt() - start).days
        if days < STANDARD_PLACEHOLDER_AFTER_DAYS and not args.force:
            return out(3, f"NOT_DUE ({days}/{STANDARD_PLACEHOLDER_AFTER_DAYS} days)")
    if not args.auto and not args.force:
        return out(3, "INELIGIBLE need --auto or --force")

    owner, owner_src = resolve_owner(args.owner_name, state, root)
    if not owner:
        return out(2, "OWNER_NAME_UNKNOWN")
    scn.clean_name(owner)

    established = bool(state.get("companyId") and (state.get("companySlug") or state.get("clientSlug")))
    prior_name = state.get("companyName") or None
    company_name = prior_name if (established and prior_name) else owner
    slug = state.get("companySlug") or state.get("clientSlug") or slugify(owner)

    # --- departments dir + pre-existing vertical departments (guard exemption snapshot) ---
    df = _load("department_floor_sp", HERE / "department-floor.py")
    guard = _load("vertical_guard_sp", HERE / "vertical-derivation-guard.py")
    dd = Path(args.departments_dir) if args.departments_dir else df.resolve_departments_dir()
    if dd is None:
        return out(1, "FAILED no departments dir resolvable (pass --departments-dir)")
    dd = Path(dd)
    pre_vertical = sorted(p["id"] for p in guard.provisioned_vertical_departments(
        dd, guard.dept_pack_index(guard.load_naming_map()))) if dd.is_dir() else []

    summary = {"owner": owner, "companyName": company_name, "slug": slug, "days": days,
               "preexistingVerticalDepartments": pre_vertical}
    if not args.apply:
        return out(0, f"DRY-RUN would apply standard placeholder for '{company_name}' (slug {slug})", **summary)

    protected_before = json.dumps({k: state.get(k) for k in PROTECTED_KEYS}, sort_keys=True)

    # --- library-only prebuild, when it has not run ---
    if (state.get("standardPrebuild") or {}).get("status") != "done":
        engine = find_engine(root)
        if engine is None:
            return out(1, "FAILED prebuild engine prebuild-standard-workforce.py not found")
        decided_by = os.environ.get("USER", "operator") if args.force else "standard-placeholder-policy"
        consent = {"decision": "prebuild", "source": "operator-prebuild", "decidedAt": iso(now_dt()),
                   "decidedBy": decided_by,
                   "sessionId": f"{state.get('installationId') or os.uname().nodename}:standard-placeholder",
                   "policyVersion": "standard-placeholder.v1",
                   "requestedAction": f"standard-placeholder-after-{STANDARD_PLACEHOLDER_AFTER_DAYS}-days"}
        cpath = root / "workspace" / "provisioning" / "standard-placeholder-consent.json"
        if args.build_state_file:
            cpath = Path(args.build_state_file).parent / "standard-placeholder-consent.json"
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(consent, indent=2) + "\n")
        cmd = [sys.executable, str(engine), "--operator-consent-file", str(cpath), "--company-slug", slug,
               "--company-name", company_name, "--departments-dir", str(dd),
               "--standard-first-onboarding", "at-onboarding", "--apply", "--json"]
        if args.company_dir:
            cmd += ["--company-dir", args.company_dir]
        if args.build_state_file:
            cmd += ["--build-state-file", state_path]
        env = dict(os.environ, STANDARD_FIRST_ONBOARDING="1", SKILL23_SCRIPTS_DIR=str(HERE))
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            tail = " | ".join((r.stderr or "").strip().splitlines()[-6:])
            try:
                reason = json.loads(r.stdout).get("reason", "")
            except ValueError:
                reason = ""
            return out(1, f"FAILED prebuild rc={r.returncode} {reason} {tail}".strip())

    # --- write placeholder state under the lock ---
    def mutate(s):
        s["companyMode"] = "standard-placeholder"
        s["standardPlaceholder"] = {
            "status": "active", "appliedAt": iso(now_dt()),
            "appliedBy": "operator" if args.force else "daily-update",
            "trigger": "forced" if args.force else f"{STANDARD_PLACEHOLDER_AFTER_DAYS}-day",
            "thresholdDays": STANDARD_PLACEHOLDER_AFTER_DAYS,
            "clockStart": iso(start) if start else None, "clockSource": start_src, "daysElapsed": days,
            "ownerName": owner, "ownerNameSource": owner_src, "priorCompanyName": prior_name,
            "preexistingVerticalDepartments": pre_vertical, "ccProvisionedAt": None, "supersededAt": None,
            "source": "apply-standard-placeholder.py", "policyRef": "trevor-owner-order-2026-10-08",
        }
        if not str(s.get("ownerName") or "").strip():
            s["ownerName"] = owner
        if "verticalPacks" not in s:
            s["verticalPacks"] = {"detectedPacks": [], "source": "standard-placeholder", "recordedAt": iso(now_dt())}
    update(state_path, mutate)

    if company_name != prior_name:
        scn.set_company_name(company_name, state_path, True, cc_dir=args.cc_dir)

    after = read(state_path)
    assert json.dumps({k: after.get(k) for k in PROTECTED_KEYS}, sort_keys=True) == protected_before, \
        "STD001 invariant broken: interview keys changed"
    return out(0, "APPLIED", **summary)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--auto", action="store_true", help="respect the %d-day threshold" % STANDARD_PLACEHOLDER_AFTER_DAYS)
    ap.add_argument("--force", action="store_true", help="operator: skip the day check (other rules still apply)")
    ap.add_argument("--owner-name", default=None)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--build-state-file", default=None)
    ap.add_argument("--oc-root", default=None)
    ap.add_argument("--departments-dir", default=None, help="scratch isolation")
    ap.add_argument("--company-dir", default=None, help="scratch isolation")
    ap.add_argument("--cc-dir", default=None, help="Command Center dir override (scratch isolation)")
    try:
        return run(ap.parse_args(argv))
    except (ValueError, OSError, AssertionError) as e:
        print(f"FAILED {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
