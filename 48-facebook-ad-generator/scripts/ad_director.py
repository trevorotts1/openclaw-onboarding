#!/usr/bin/env python3
"""
ad_director.py — DETERMINISTIC FACEBOOK/INSTAGRAM AD-PIPELINE GATE-AND-ATTEST FOREMAN.

================================================================================
A deterministic state machine over AD-PIPELINE-MANIFEST.json. It is the foreman
the Facebook & Instagram Ad-Run Producer runs. It mirrors the Movie Producer's
executive_producer.py spine but is a DELIBERATE DEPENDENCY-MAP REWRITE, not a
file-for-file copy:

  * Skill 47 gated on "every LOWER-ORDER phase is attested." This foreman gates
    on each phase's EXPLICIT depends_on[] list, so the independent stages run in
    parallel: after PICK-10, S2 (bodies) / S3 (headlines) / S4 (image prompts)
    all become dispatchable at once; S5 (images) waits only on S4; S6 (targeting)
    waits on S2 + S3; S7 (deliver) waits on S5 + S6.
  * The two HUMAN GATES — PICK-10 and PUBLISH — are NON-SKIPPABLE. No
    owner-authorized skip record and no --adhoc relaxation can bypass them. A
    downstream phase that depends on a human gate can never have that dependency
    skip-approved away.

WHAT IT GUARANTEES
  * Dependency-map order. Before dispatching/attesting phase N, EVERY phase in
    N.depends_on must carry an attestation (by its declared owning_role) in
    working/checkpoints/ad_process_manifest.json AND its produces_artifact must
    be present. A missing dependency is a HARD ABORT (AF-FBAD-DEP-SKIPPED, exit 2)
    — EXCEPT a NON-human-gate dependency may be covered by a logged owner-authorized
    skip (working/checkpoints/phase_skip_approvals.json, owner_approved:true).
  * Receipt VALIDATION, not mere presence. A phase is attested only when its
    produces_artifact passes the manifest checker(s) (ad_build_check._chk_*): e.g.
    S5 requires every image to carry a real kie_task_id, be 1500x1500, and use a
    gpt-image-* model; a fabricated/placeholder task id is exit 3.
  * Phase-0 PRE-FLIGHT (run ONCE, before ANY paid dispatch):
      - Kie.ai BALANCE preflight for a PAID job: HARD-ABORTS (AF-FBAD-KIE-BALANCE,
        exit 4) when the live balance < the estimated floor or cannot be verified.
        SHARED with ad_build_check.kie_balance_preflight.
  * --adhoc escape: OWNER-authorized + logged
    (working/checkpoints/adhoc_authorization.json). Without the logged record,
    --adhoc is REFUSED (exit 2). --adhoc NEVER relaxes a human gate.

MONEY MODEL (LOCKED DECISIONS) — enforced via the receipt checkers, not here:
  estimate up front (AF-FBAD-COST-CEILING) -> per-job ceiling -> a cheap LOCAL
  running tally that stops before crossing (AF-FBAD-TALLY-CROSS) -> a single
  balance preflight at start (AF-FBAD-KIE-BALANCE). NOT a balance call per image.

EXIT CODES
    0 — clean: the phase attested (or owner-authorized skips), pre-flight clean.
    2 — dependency-precondition violation (AF-FBAD-DEP-SKIPPED), usage error, or a
        refused --adhoc.
    3 — a receipt failed VALIDATION (the produces_artifact is present but its
        checker rejected it — e.g. AF-FBAD-IMAGE-TASKID / AF-FBAD-COPY-QC).
    4 — Phase-0 balance abort (AF-FBAD-KIE-BALANCE).

USAGE
    python3 ad_director.py --run-dir DIR
        [--plan]                 # print the resolved dependency plan + readiness
        [--phase S5-IMAGE-GEN]   # advance to / attest a single phase
        [--adhoc]                # owner-authorized + logged escape (refused without it)

AF-FBAD-DEP-SKIPPED is enforced_by:driver with py_symbol:null (the foreman's
check_dependency_preconditions is the enforcer; the manifest does not require a
symbol for it). AF-FBAD-KIE-BALANCE is enforced_by:ad_director with py_symbol
kie_balance_preflight (defined in ad_build_check, referenced here).
"""

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent  # .../48-facebook-ad-generator/scripts

# Receipt validators + Phase-0 balance live in our sibling library (OUR code).
import ad_build_check as abc


# ---------------------------------------------------------------------------
# Manifest resolution (repo cluster OR deployed-beside-the-skill layout)
# ---------------------------------------------------------------------------
def _find_repo_root(start: Path):
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_manifest() -> dict:
    repo = _find_repo_root(HERE)
    candidates = []
    if repo:
        candidates.append(repo / "universal-sops" / "fb-ad-craft"
                          / "AD-PIPELINE-MANIFEST.json")
    candidates += [
        HERE.parent / "sops" / "AD-PIPELINE-MANIFEST.json",
        HERE.parent / "AD-PIPELINE-MANIFEST.json",
        HERE / "AD-PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception as exc:  # noqa: BLE001
                print(f"FATAL: AD-PIPELINE-MANIFEST.json is not valid JSON ({exc}).",
                      file=sys.stderr)
                sys.exit(2)
    print("FATAL: AD-PIPELINE-MANIFEST.json not found.", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Attestation ledger — working/checkpoints/ad_process_manifest.json
# ---------------------------------------------------------------------------
def _process_manifest_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "ad_process_manifest.json"


def _load_process_manifest(run_dir: Path) -> dict:
    p = _process_manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _attestations(run_dir: Path) -> list:
    return _load_process_manifest(run_dir).get("phase_attestations", []) or []


def _attested_phase_ids(run_dir: Path) -> set:
    ids = set()
    for att in _attestations(run_dir):
        if isinstance(att, dict) and att.get("phase_id"):
            ids.add(att["phase_id"])
    return ids


def _job_id(run_dir: Path) -> str:
    jm = abc._load_job_manifest(run_dir)
    return jm.get("job_id", "") if isinstance(jm, dict) else ""


def attest_phase(run_dir: Path, phase_id: str, role: str, status: str,
                 checker: str = "", note: str = "") -> None:
    """Append a phase attestation (never clobber prior records). Records the
    owning_role so the precondition gate can detect a wrong-role attestation."""
    p = _process_manifest_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = _load_process_manifest(run_dir)
    obj.setdefault("job_id", _job_id(run_dir))
    obj.setdefault("phase_attestations", [])
    obj["phase_attestations"].append({
        "phase_id": phase_id,
        "owning_role": role,
        "status": status,
        "checker": checker,
        "note": note,
        "attested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    obj["finalized"] = (phase_id == "PUBLISH" and status == "attested")
    p.write_text(json.dumps(obj, indent=2))


# ---------------------------------------------------------------------------
# Owner-authorized skip records (the controlled exception — NOT for human gates)
# ---------------------------------------------------------------------------
def load_skip_approvals(run_dir: Path) -> dict:
    """Return {phase_id: record} for every well-formed owner-authorized skip
    (owner_approved:true + approved_by + reason). A malformed or owner_approved:false
    record does NOT authorize a skip. Human-gate phases are filtered out by the
    caller — they can never be skip-approved."""
    p = run_dir / "working" / "checkpoints" / "phase_skip_approvals.json"
    approvals = {}
    if not p.exists():
        return approvals
    try:
        obj = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return approvals
    records = obj if isinstance(obj, list) else (
        obj.get("approvals") or obj.get("skips") or [] if isinstance(obj, dict) else [])
    for rec in records if isinstance(records, list) else []:
        if (isinstance(rec, dict) and rec.get("owner_approved") is True
                and rec.get("phase_id")
                and str(rec.get("approved_by", "")).strip()
                and str(rec.get("reason", "")).strip()):
            approvals[rec["phase_id"]] = rec
    return approvals


def _artifact_present(run_dir: Path, produces_artifact: str) -> bool:
    """True when a phase's declared produces_artifact exists in the run dir.
    Supports glob patterns. A null/empty spec counts as satisfied."""
    spec = (produces_artifact or "").strip()
    if not spec:
        return True
    if "*" in spec or "?" in spec:
        if list(run_dir.glob(spec)):
            return True
        return bool(list(run_dir.glob("**/" + spec.split("/")[-1])))
    p = run_dir / spec
    if p.exists():
        return True
    return bool(list(run_dir.glob("**/" + spec.split("/")[-1])))


# ---------------------------------------------------------------------------
# Dependency preconditions — AF-FBAD-DEP-SKIPPED (the dependency-map gate)
# ---------------------------------------------------------------------------
def check_dependency_preconditions(run_dir: Path, phases: list,
                                   target_phase_id: str) -> str:
    """Return "" when EVERY phase named in target.depends_on[] is attested (by its
    declared owning_role) AND its produces_artifact is present — OR (for a
    NON-human-gate dependency only) is covered by an owner-authorized skip.
    Otherwise return a fatal AF-FBAD-DEP-SKIPPED message. The two human gates
    (PICK-10, PUBLISH) can NEVER be skipped."""
    by_id = {ph["id"]: ph for ph in phases}
    target = by_id.get(target_phase_id)
    if target is None:
        return (f"AF-FBAD-DEP-SKIPPED: unknown phase id {target_phase_id!r} "
                "(not in AD-PIPELINE-MANIFEST).")
    deps = target.get("depends_on") or []
    approvals = load_skip_approvals(run_dir)
    att_by_phase = {}
    for a in _attestations(run_dir):
        if isinstance(a, dict) and a.get("phase_id"):
            att_by_phase[a["phase_id"]] = a
    for dep_id in deps:
        dep = by_id.get(dep_id)
        if dep is None:
            return (f"AF-FBAD-DEP-SKIPPED: phase {target_phase_id} declares an unknown "
                    f"dependency {dep_id!r}.")
        is_human = bool(dep.get("human_gate"))
        att = att_by_phase.get(dep_id)
        # A NON-human-gate dependency may be covered by a logged owner skip.
        if att is None:
            if not is_human and dep_id in approvals:
                continue
            human_note = (" This dependency is a HUMAN GATE and can NEVER be skipped "
                          "(no skip record, no --adhoc)." if is_human else "")
            return ("AF-FBAD-DEP-SKIPPED: phase " + target_phase_id + " was dispatched "
                    "before its declared dependency " + dep_id + " was attested. Each "
                    "phase reads its depends_on[] attestations in working/checkpoints/"
                    "ad_process_manifest.json as a precondition, so skipping or "
                    "reordering is structurally impossible." + human_note)
        # Wrong-role attestation is a violation (a phase's owning_role is fixed).
        owner = dep.get("owning_role", "")
        if owner and att.get("owning_role") and att["owning_role"] != owner:
            return ("AF-FBAD-DEP-SKIPPED: dependency " + dep_id + " was attested by "
                    f"{att['owning_role']!r}, but its owning_role is {owner!r}. A phase "
                    "must be produced by its declared owning_role.")
        if not _artifact_present(run_dir, dep.get("produces_artifact", "")):
            return ("AF-FBAD-DEP-SKIPPED: dependency " + dep_id + " is attested but its "
                    f"produces_artifact {dep.get('produces_artifact')!r} is not present "
                    "in the run dir — an attestation must correspond to a real artifact.")
    return ""


# ---------------------------------------------------------------------------
# Receipt validation — run the phase's manifest checker(s) against the artifact.
# Returns (ok, reason). A present-but-invalid receipt is exit 3.
# ---------------------------------------------------------------------------
def validate_phase_receipt(run_dir: Path, phase: dict):
    checkers = []
    pf = phase.get("preflight")
    if pf and pf.get("checker"):
        checkers.append(pf["checker"])
    for ap in phase.get("additional_preflights", []) or []:
        if ap.get("checker"):
            checkers.append(ap["checker"])
    for name in checkers:
        fn = abc.CHECKERS.get(name)
        if fn is None:
            return False, (f"AF-FBAD-DEP-SKIPPED: phase {phase['id']} names checker "
                           f"{name!r}, which is not defined in ad_build_check.py.")
        reason = fn(run_dir)
        if reason:
            return False, reason
    return True, ""


# ---------------------------------------------------------------------------
# Phase-0 pre-flight — Kie balance (AF-FBAD-KIE-BALANCE) for a PAID job
# ---------------------------------------------------------------------------
def _estimated_cost(run_dir: Path) -> float:
    jm = abc._load_job_manifest(run_dir)
    if isinstance(jm, dict) and isinstance(jm.get("estimated_cost_usd"), (int, float)):
        return float(jm["estimated_cost_usd"])
    return 0.0


def _load_kie_api_key() -> str:
    import os
    return os.environ.get("KIE_API_KEY", "") or ""


def phase0_preflight(run_dir: Path, adhoc: bool = False) -> None:
    """Phase-0: Kie balance preflight for a paid job, run ONCE. HARD-ABORT (exit 4)
    on AF-FBAD-KIE-BALANCE before any paid dispatch."""
    paid = abc._paid_in_scope(run_dir)
    print(f"=== PHASE-0 PRE-FLIGHT — paid_job={paid} ===", flush=True)
    if adhoc:
        print("=== PHASE-0 — adhoc (owner-authorized): Kie balance preflight skipped ===",
              flush=True)
        return
    if not paid:
        print("=== PHASE-0 — free/dry path (no paid Kie call); balance preflight N/A ===",
              flush=True)
        return
    est = _estimated_cost(run_dir)
    api_key = _load_kie_api_key()
    if not api_key:
        print("=== PHASE-0 — no Kie API key on this box; balance preflight deferred to "
              "the generation subprocess ===", flush=True)
    reason = abc.kie_balance_preflight(run_dir, est, api_key or None)
    if reason:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: " + reason, file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)
    print("=== PHASE-0 — Kie balance preflight PASSED (balance >= estimated floor) ===",
          flush=True)


# ---------------------------------------------------------------------------
# Plan printing
# ---------------------------------------------------------------------------
def print_plan(run_dir: Path, phases: list) -> None:
    attested = _attested_phase_ids(run_dir)
    approvals = load_skip_approvals(run_dir)
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    print("=== FB/IG AD-PIPELINE DEPENDENCY PLAN (manifest) ===")
    for ph in ordered:
        pid = ph["id"]
        deps = ph.get("depends_on") or []
        if pid in attested:
            state = "ATTESTED"
        elif all((d in attested) or (not _is_human(phases, d) and d in approvals)
                 for d in deps):
            state = "READY"
        else:
            state = "waiting"
        human = " [HUMAN-GATE]" if ph.get("human_gate") else ""
        print(f"  [{ph.get('order'):>3}] {pid:<16} {state:<10}{human:<13} "
              f"depends_on={deps} owner={ph.get('owning_role')}")


def _is_human(phases: list, phase_id: str) -> bool:
    for ph in phases:
        if ph["id"] == phase_id:
            return bool(ph.get("human_gate"))
    return False


# ---------------------------------------------------------------------------
# adhoc authorization (owner-authorized + logged; refused without the record)
# ---------------------------------------------------------------------------
def assert_adhoc_authorized(run_dir: Path) -> None:
    p = run_dir / "working" / "checkpoints" / "adhoc_authorization.json"
    ok = False
    if p.exists():
        try:
            obj = json.loads(p.read_text())
            ok = (isinstance(obj, dict) and obj.get("owner_approved") is True
                  and str(obj.get("approved_by", "")).strip()
                  and str(obj.get("reason", "")).strip())
        except Exception:  # noqa: BLE001
            ok = False
    if not ok:
        print("FATAL: --adhoc requires an OWNER-AUTHORIZED, LOGGED record at "
              "working/checkpoints/adhoc_authorization.json "
              "(owner_approved:true + approved_by + reason). It is NOT a free flag. "
              "Refusing the ad-hoc run.", file=sys.stderr)
        sys.exit(2)
    bar = "!" * 78
    print(bar, flush=True)
    print("!! ADHOC MODE (owner-authorized + logged): NON-human-gate phase preconditions "
          "+ balance preflight relaxed.", flush=True)
    print("!! The two HUMAN GATES (PICK-10, PUBLISH) are STILL enforced — --adhoc never "
          "bypasses a human gate.", flush=True)
    print("!! Output of this run is NOT a process-compliant client deliverable.", flush=True)
    print(bar + "\n", flush=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Deterministic FB/IG ad-pipeline dependency-map gate-and-attest "
                    "foreman (Skill 48).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--phase", help="advance/attest a single phase id (checks "
                                     "dependency preconditions)")
    ap.add_argument("--plan", action="store_true", help="print the dependency plan + exit")
    ap.add_argument("--adhoc", action="store_true",
                    help="owner-authorized + logged escape (refused without the record; "
                         "never bypasses a human gate)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        sys.exit(2)

    manifest = load_manifest()
    phases = manifest["phases"]

    if args.plan:
        print_plan(run_dir, phases)
        sys.exit(0)

    if args.adhoc:
        assert_adhoc_authorized(run_dir)

    # Phase-0 pre-flight (Kie balance for a paid job). HARD-ABORTS on AF-FBAD-KIE-BALANCE.
    phase0_preflight(run_dir, adhoc=args.adhoc)

    if args.phase:
        target = next((p for p in phases if p["id"] == args.phase), None)
        if target is None:
            print(f"FATAL: unknown phase id {args.phase!r}.", file=sys.stderr)
            sys.exit(2)

        is_human = bool(target.get("human_gate"))
        # A human gate is NEVER relaxed by --adhoc; a non-human phase is.
        enforce = (not args.adhoc) or is_human

        # 1) Dependency preconditions — every depends_on phase attested + artifact
        #    present (or, for a non-human dep, owner-skipped). AF-FBAD-DEP-SKIPPED (exit 2).
        if enforce:
            reason = check_dependency_preconditions(run_dir, phases, args.phase)
            if reason:
                print("\nFATAL: " + reason, file=sys.stderr)
                sys.exit(2)

        # 2) The produces_artifact must be present at all (else the phase has not run).
        if not _artifact_present(run_dir, target.get("produces_artifact", "")):
            print(f"\nFATAL: AF-FBAD-DEP-SKIPPED: phase {args.phase} produces_artifact "
                  f"{target.get('produces_artifact')!r} is not present; the phase has "
                  "not produced its receipt — cannot attest.", file=sys.stderr)
            sys.exit(2)

        # 3) RECEIPT VALIDATION — present is not enough; the receipt must pass its
        #    manifest checker(s). A present-but-invalid receipt is exit 3. A human gate
        #    is ALWAYS validated, even under --adhoc.
        if enforce:
            ok, reason = validate_phase_receipt(run_dir, target)
            if not ok:
                print("\nFATAL (receipt failed validation): " + reason, file=sys.stderr)
                sys.exit(3)

        attest_phase(run_dir, args.phase, target.get("owning_role", ""), "attested",
                     checker=(target.get("preflight") or {}).get("checker", ""))
        print(f"=== PHASE {args.phase} ATTESTED (dependencies met + receipt validated) ===",
              flush=True)
        sys.exit(0)

    # No --phase: the safe default is to print the plan.
    print_plan(run_dir, phases)
    print("\nNote: pass --phase S0-INTAKE (then the stages in dependency order: "
          "S1-OVERLAYS, PICK-10, then S2/S3/S4 in parallel, S5, S6, S7, PUBLISH) to "
          "attest each phase once its receipt is present and valid. A phase's "
          "depends_on[] must be attested first (AF-FBAD-DEP-SKIPPED).", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
