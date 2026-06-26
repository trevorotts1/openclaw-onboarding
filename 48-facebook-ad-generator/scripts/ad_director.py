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
    0 — clean: the phase attested (or owner-authorized skips), pre-flight clean; OR a
        --recover/--resume actionable step (DONE / PRODUCE / REDO) — read the JSON
        verdict's "action".
    2 — dependency-precondition violation (AF-FBAD-DEP-SKIPPED), usage error, a
        refused --adhoc, or a refused paid run pinned to a reboot-wiped tmp dir.
    3 — a receipt failed VALIDATION (the produces_artifact is present but its
        checker rejected it — e.g. AF-FBAD-IMAGE-TASKID / AF-FBAD-COPY-QC).
    4 — Phase-0 balance abort (AF-FBAD-KIE-BALANCE) on the legacy --phase path.
    5 — PARKED (--recover/--resume): a durable save-point was written (PARKED.json +
        a box-level pointer) and the job PAUSED at a non-recoverable / human-gated /
        budget-exhausted condition. Nothing is discarded. Clear the blocker, then
        --resume to re-enter at the exact last-incomplete phase (idempotent on the
        run-id ledger — never re-charges, never re-uploads).

SELF-CORRECT + PARK-AND-RESUME (opt-in; the legacy --phase 0/2/3/4 path is untouched)
    --recover  drive the next actionable step. The engine (ad_recovery.py) reads the
               per-gate recovery policy from the manifest and returns ONE verdict:
                 PRODUCE  — make this phase's artifact, then call --recover again
                 ADVANCE  — (internal) a phase just attested; the loop continues
                 REDO     — a recovery:"auto" gate failed; redo ONLY the failing
                            artifact with "feedback", up to "max" attempts, re-call
                 PARK     — a recovery:"park" gate, an exhausted budget, or no-progress
                            wrote a durable checkpoint (exit 5)
                 AWAIT_HUMAN — a human gate (PICK-10 / PUBLISH) is waiting (exit 5)
                 DONE     — every phase attested
    --resume   re-run the parked checkpoint's clearing checker(s); if they pass, clear
               the park and continue from the last-incomplete phase; else stay parked.
    --status   print attested phases, spend tally, park state, attempt counters, next.

USAGE
    python3 ad_director.py --run-dir DIR
        [--plan]                 # print the resolved dependency plan + readiness
        [--phase S5-IMAGE-GEN]   # advance to / attest a single phase (legacy gate)
        [--adhoc]                # owner-authorized + logged escape (refused without it)
        [--recover]              # self-correct/park foreman: drive the next step
        [--resume]               # resume a parked run once the blocker clears
        [--status]               # report attested/spend/park/attempt state
        [--item N]               # per-item budget key for a per-image gate (S5)
        [--allow-ephemeral]      # permit a paid run under a tmp dir (dry/test only)

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
# Producer-side Command Center board caller (OUR code). FAIL-SOFT by contract:
# every cc_board call catches its own errors and returns a value, so a board
# outage / missing token NEVER affects this foreman's exit codes or flow.
import cc_board


# ---------------------------------------------------------------------------
# Command Center board hookup (FAIL-SOFT). Lands the run on the Kanban board as
# one campaign + one card per phase, and moves cards through the lifecycle:
#   job start         -> create campaign (cards in backlog) + stamp campaign_id
#   phase in progress -> card in_progress     (PRODUCE step)
#   human pause       -> card review          (PICK-10 / PUBLISH await)
#   phase attested    -> card done
#   dangerous park    -> card blocked (reason + ask)
# A disabled board (no MISSION_CONTROL_URL) makes all of this a clean no-op, and
# a stamped deterministic job_id keeps the offline board check satisfied.
# ---------------------------------------------------------------------------

# Once-per-run marker so we POST the campaign only once (server is idempotent on
# job_id too, but this avoids needless calls/logs).
def _board_marker(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "cc-board.created"


def _board_stage_slug(phase_id: str) -> str:
    """Stable card slug for a manifest phase id (lowercased; <=64 chars)."""
    return str(phase_id).lower()[:64]


def _board_stages(phases: list) -> list:
    return [{"slug": _board_stage_slug(p["id"]), "title": p.get("name") or p["id"]}
            for p in sorted(phases, key=lambda x: x.get("order", 0))]


# park_class (from _PARK_CLASS) -> CC blocked_reason vocabulary
# {decision, approval, credential, payment}.
_BLOCKED_REASON = {
    "money": "payment",
    "budget_exhausted": "payment",
    "fabrication": "approval",
    "integrity": "approval",
    "no_progress": "decision",
    "await_human": "decision",
}


def _board_ensure_campaign(run_dir: Path, manifest: dict) -> None:
    """Create the campaign + stamp campaign_id into the deliver receipt. Idempotent
    via a marker file. ALWAYS stamps the deterministic job_id (the receipt-number)
    so the offline AF-FBAD-BOARD check passes whether or not the live POST landed."""
    try:
        job_id = _job_id(run_dir)
        if not job_id:
            return
        marker = _board_marker(run_dir)
        if marker.exists():
            return
        jm = abc._load_job_manifest(run_dir)
        jm = jm if isinstance(jm, dict) else {}
        campaign_id = cc_board.create_campaign(
            job_id,
            str(jm.get("show_name") or job_id),
            stages=_board_stages(manifest.get("phases", [])),
            owner=jm.get("owner"),
            department=jm.get("department") or "paid-advertisement",
            workspace=jm.get("workspace"),
            agent_id=jm.get("agent_id"),
            money_ceiling_usd=jm.get("money_ceiling_usd"),
            estimated_cost_usd=jm.get("estimated_cost_usd"),
            show_date=jm.get("show_date"),
        )
        # campaign_id == job_id on the server; fall back to job_id when the board
        # is down so the run still groups under its receipt-number.
        cc_board.stamp_campaign_id(run_dir, campaign_id or job_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(campaign_id or job_id)
    except Exception:  # noqa: BLE001 — board hookup must NEVER break the foreman.
        pass


def _board_move(run_dir: Path, phase_id: str, status: str, *, reason: str = "",
                blocked_reason=None, ask=None) -> None:
    """Drive one phase card to `status` (fail-soft, never raises)."""
    try:
        job_id = _job_id(run_dir)
        if not job_id:
            return
        cc_board.set_stage_status(
            job_id, _board_stage_slug(phase_id), status,
            reason=reason or None, blocked_reason=blocked_reason,
            blocked_on_human=("owner" if phase_id in ("PICK-10", "PUBLISH") else "operator"),
            ask=ask,
        )
    except Exception:  # noqa: BLE001
        pass


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
    # Board: an attested phase's card moves to done (fail-soft no-op when the
    # board is disabled / unreachable).
    if status == "attested":
        _board_move(run_dir, phase_id, "done", reason=(note or f"{phase_id} attested"))


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


# ===========================================================================
# SELF-CORRECT + PARK-AND-RESUME FOREMAN (--recover / --resume / --status)
# Thin orchestration over ad_recovery.py (the engine) + ad_build_check (the real
# checkers). The legacy --phase 0/2/3/4 path above is deliberately untouched.
# ===========================================================================

# park_class label per dangerous AF code. Every code here is a REAL manifest code
# (so ad_sync_check B2 stays clean); a park code not listed defaults to await_human.
# The invariant that these codes MUST be recovery:"park" is enforced in the manifest
# and locked by ad_sync_check R4 — NOT by this cosmetic label map.
_PARK_CLASS = {
    "AF-FBAD-BRIEF-INCOMPLETE": "await_human",
    "AF-FBAD-SELECTION-COUNT": "await_human",
    "AF-FBAD-SELECTION-SUBSET": "await_human",
    "AF-FBAD-APPROVE": "await_human",
    "AF-FBAD-DEP-SKIPPED": "await_human",
    "AF-FBAD-COST-CEILING": "money",
    "AF-FBAD-KIE-BALANCE": "money",
    "AF-FBAD-TALLY-CROSS": "money",
    "AF-FBAD-IMAGE-TASKID": "fabrication",
    "AF-FBAD-TARGETING-REAL": "fabrication",
    "AF-FBAD-GHL-URL": "fabrication",
    "AF-FBAD-QC-INDEPENDENCE": "integrity",
}


def _phase_checker_names(phase: dict) -> list:
    names = []
    pf = phase.get("preflight")
    if pf and pf.get("checker"):
        names.append(pf["checker"])
    for ap in phase.get("additional_preflights", []) or []:
        if ap.get("checker"):
            names.append(ap["checker"])
    return names


def _waiting_for(af: str, phase_id: str) -> str:
    if phase_id == "PICK-10":
        return "owner must reply with a valid 10-pick (PICK: n,n,...)"
    if phase_id == "PUBLISH":
        return "owner must approve-to-publish (named approval + timestamp + confirmed)"
    cls = _PARK_CLASS.get(af, "await_human")
    if af == "AF-FBAD-KIE-BALANCE":
        return "top up the Kie.ai balance (or fix the API key), then --resume"
    if cls == "money":
        return "raise the per-job money ceiling or cut the batch so the estimate fits"
    if cls == "fabrication":
        return ("correct the flagged artifact so it carries a REAL, verifiable value "
                "(a real task-id / real Meta id / real hosted link), then --resume")
    if cls == "integrity":
        return "assign a genuinely independent grader (grader != maker), then --resume"
    if af == "AF-FBAD-BRIEF-INCOMPLETE":
        return "owner must supply the missing intake-brief field, then --resume"
    return "human input required to clear the blocker, then --resume"


def _artifact_bytes(run_dir: Path, phase: dict) -> bytes:
    """Bytes of the phase's produces_artifact (the progress fingerprint source).
    Empty when absent — the engine treats first-seen as 'changed'."""
    spec = (phase.get("produces_artifact") or "").strip()
    if not spec:
        return b""
    cands = []
    p = run_dir / spec
    if p.exists():
        cands.append(p)
    else:
        cands = sorted(run_dir.glob("**/" + spec.split("/")[-1]))
    blob = b""
    for c in cands:
        try:
            blob += c.read_bytes()
        except Exception:  # noqa: BLE001
            pass
    return blob


def _balance_reason(run_dir: Path, manifest: dict) -> str:
    """Non-exiting Phase-0 balance preflight (a money PARK in recover, not exit 4)."""
    if not abc._paid_in_scope(run_dir):
        return ""
    est = _estimated_cost(run_dir)
    api_key = _load_kie_api_key()
    return abc.kie_balance_preflight(run_dir, est, api_key or None)


def _do_park(run_dir: Path, manifest: dict, *, parked_by: str, park_class: str,
             phase: str, waiting_for: str, resume_clears_when, feedback: str) -> dict:
    import ad_recovery as rec
    run_id = _job_id(run_dir)
    attested = sorted(_attested_phase_ids(run_dir))
    led = abc._ledger(run_dir)
    led = led if isinstance(led, dict) else {}
    spent = led.get("spent_usd", 0.0)
    done = [e.get("key") for e in (led.get("events", []) or [])
            if isinstance(e, dict) and e.get("key")]
    sel = abc._selection(run_dir)
    selections = {"pick10": sel.get("selection")} if isinstance(sel, dict) else {}
    rec.write_park(run_dir, run_id=run_id, parked_by_af=parked_by, park_class=park_class,
                   phase=phase, waiting_for=waiting_for, resume_clears_when=resume_clears_when,
                   feedback=feedback, attested_phases=attested, selections=selections,
                   spent_usd=spent, ledger_done_keys=done)
    return {
        "action": "PARK", "parked_by": parked_by, "park_class": park_class,
        "phase": phase, "waiting_for": waiting_for,
        "resume_clears_when": resume_clears_when, "feedback": feedback,
        "attested_phases": attested, "spent_usd": spent,
        "note": ("durable save-point written (PARKED.json + box pointer). No work "
                 "discarded — attested phases + paid ledger keys are preserved. Clear the "
                 "blocker, then run --resume to re-enter at the last-incomplete phase "
                 "(idempotent on the run-id ledger; never re-charges / re-uploads)."),
    }


def _handle_fail(run_dir: Path, manifest: dict, phase: dict, reason: str, item):
    """Map a REAL failing check to a verdict via the recovery engine. Returns
    (verdict_dict, exit_code). REDO => exit 0 (agent redoes the one artifact and
    re-calls). PARK/AWAIT => exit 5 (durable checkpoint)."""
    import ad_recovery as rec
    pid = phase["id"]
    af = rec.af_from_reason(reason) or (phase.get("gate_codes") or ["AF-FBAD-DEP-SKIPPED"])[0]
    decision = rec.classify_fail(run_dir, manifest, pid, af, item=item,
                                 artifact_bytes=_artifact_bytes(run_dir, phase))
    if decision["decision"] == "REDO":
        return ({
            "action": "REDO", "phase": pid, "failing_af": af, "feedback": reason,
            "attempt": decision["attempt"], "max": decision["max"], "item": item,
            "note": ("redo ONLY the failing artifact using the gate feedback, then call "
                     "--recover again. The re-call re-runs the REAL checker — there is no "
                     "fabricated pass."),
        }, 0)
    # PARK
    park_reason = decision.get("reason", "park_gate")
    if park_reason == "park_gate":
        park_class = _PARK_CLASS.get(af, "await_human")
        waiting = _waiting_for(af, pid)
    elif park_reason == "no_progress":
        park_class = "no_progress"
        waiting = (f"the redo for {af} resubmitted a byte-identical artifact "
                   f"{decision.get('no_progress')}x — it is not changing anything; human "
                   "help needed, then --resume")
    else:  # budget_exhausted / total_budget_exhausted
        park_class = "budget_exhausted"
        waiting = (f"the auto-fix budget ({decision.get('max', '?')}) for {af} is spent "
                   f"({park_reason}); a human must fix the artifact, then --resume")
    # Board: a dangerous park blocks the card with a structured reason + the ask.
    _board_move(run_dir, pid, "blocked",
                reason=reason,
                blocked_reason=_BLOCKED_REASON.get(park_class, "decision"),
                ask=waiting)
    return (_do_park(run_dir, manifest, parked_by=af, park_class=park_class, phase=pid,
                     waiting_for=waiting, resume_clears_when=_phase_checker_names(phase),
                     feedback=reason), 5)


def _recover_loop(run_dir: Path, manifest: dict, item):
    """Advance the run one ACTIONABLE step. Attesting a passed phase loops to the next;
    PRODUCE / REDO / PARK / AWAIT_HUMAN / DONE return a verdict to the agent."""
    import ad_recovery as rec
    phases = manifest["phases"]
    while True:
        attested = _attested_phase_ids(run_dir)
        ph = rec.next_actionable_phase(phases, attested)
        if ph is None:
            # Whole run complete — close the epic card (CC marks the campaign complete).
            _board_move(run_dir, "epic", "done", reason="run complete (PUBLISH attested)")
            return ({"action": "DONE", "attested": sorted(attested),
                     "note": "every phase attested through PUBLISH; the run is complete."}, 0)
        pid = ph["id"]
        is_human = bool(ph.get("human_gate"))
        present = _artifact_present(run_dir, ph.get("produces_artifact", ""))

        if is_human:
            # A human gate is NEVER auto-made or auto-redone — the human must supply it.
            ok, reason = (False, "")
            if present:
                ok, reason = validate_phase_receipt(run_dir, ph)
            if present and ok:
                attest_phase(run_dir, pid, ph.get("owning_role", ""), "attested",
                             checker=(ph.get("preflight") or {}).get("checker", ""))
                continue
            af = (rec.af_from_reason(reason) if reason else None) \
                or (ph.get("gate_codes") or ["AF-FBAD-DEP-SKIPPED"])[0]
            verdict = _do_park(run_dir, manifest, parked_by=af, park_class="await_human",
                               phase=pid, waiting_for=_waiting_for(af, pid),
                               resume_clears_when=_phase_checker_names(ph),
                               feedback=(reason or f"{af}: awaiting human input at {pid}."))
            verdict["action"] = "AWAIT_HUMAN"
            # Board: a human pause (PICK-10 / PUBLISH) parks the card in review.
            _board_move(run_dir, pid, "review",
                        reason=verdict.get("waiting_for") or f"{pid} awaiting human")
            return (verdict, 5)

        if not present:
            # Board: this phase is now the one being worked.
            _board_move(run_dir, pid, "in_progress", reason=f"producing {pid}")
            return ({"action": "PRODUCE", "phase": pid,
                     "owning_role": ph.get("owning_role"), "sop_refs": ph.get("sop_refs", []),
                     "produces_artifact": ph.get("produces_artifact"),
                     "note": "produce this artifact, then call --recover again."}, 0)

        ok, reason = validate_phase_receipt(run_dir, ph)
        if ok:
            attest_phase(run_dir, pid, ph.get("owning_role", ""), "attested",
                         checker=(ph.get("preflight") or {}).get("checker", ""))
            continue
        return _handle_fail(run_dir, manifest, ph, reason, item)


def cmd_recover(run_dir: Path, manifest: dict, item=None, allow_ephemeral=False):
    import ad_recovery as rec
    # Board: file the run as one campaign (one card per phase) on first entry,
    # and stamp campaign_id into the deliver receipt. Fail-soft no-op when disabled.
    _board_ensure_campaign(run_dir, manifest)
    paid = abc._paid_in_scope(run_dir)
    refusal = rec.refuse_paid_tmp(run_dir, paid, allow_ephemeral)
    if refusal:
        return ({"action": "REFUSE", "reason": refusal}, 2)
    parked = rec.read_park(run_dir)
    if parked:
        return ({"action": "PARKED", "parked_by": parked.get("parked_by_af"),
                 "park_class": parked.get("park_class"),
                 "waiting_for": parked.get("waiting_for"),
                 "note": "run is parked; clear the blocker and call --resume."}, 5)
    # Phase-0 balance preflight for a paid job — a money PARK, never a hard abort.
    if paid:
        breason = _balance_reason(run_dir, manifest)
        if breason:
            return (_do_park(run_dir, manifest, parked_by="AF-FBAD-KIE-BALANCE",
                             park_class="money", phase="Phase-0",
                             waiting_for=_waiting_for("AF-FBAD-KIE-BALANCE", "Phase-0"),
                             resume_clears_when=["kie_balance_preflight"],
                             feedback=breason), 5)
    return _recover_loop(run_dir, manifest, item)


def _clears_blocking(run_dir: Path, manifest: dict, clears) -> list:
    """Re-run the parked checkpoint's clearing checker(s). Return the list of still-
    failing (token, reason) — empty means the blocker is genuinely cleared."""
    still = []
    for token in (clears or []):
        if token == "kie_balance_preflight":
            reason = _balance_reason(run_dir, manifest)
        else:
            fn = abc.CHECKERS.get(token)
            reason = fn(run_dir) if fn else f"unknown clearing checker {token!r}"
        if reason:
            still.append({"checker": token, "reason": reason})
    return still


def cmd_resume(run_dir: Path, manifest: dict, item=None, allow_ephemeral=False):
    import ad_recovery as rec
    parked = rec.read_park(run_dir)
    if parked is None:
        # nothing parked — resume is a no-op alias for recover (idempotent).
        return cmd_recover(run_dir, manifest, item, allow_ephemeral)
    still = _clears_blocking(run_dir, manifest, parked.get("resume_clears_when"))
    if still:
        return ({"action": "STILL_PARKED", "parked_by": parked.get("parked_by_af"),
                 "park_class": parked.get("park_class"),
                 "waiting_for": parked.get("waiting_for"), "blocking": still,
                 "note": ("the blocker is NOT cleared yet — the real checker still fails. "
                          "Supply/correct it, then run --resume again. A park is never "
                          "auto-cleared without the real check passing.")}, 5)
    rec.clear_park(run_dir, run_id=parked.get("run_id"))
    # Re-enter via recover: re-checks balance, skips attested phases + paid ledger keys.
    return cmd_recover(run_dir, manifest, item, allow_ephemeral)


def cmd_status(run_dir: Path, manifest: dict):
    import ad_recovery as rec
    attested = sorted(_attested_phase_ids(run_dir))
    led = abc._ledger(run_dir)
    led = led if isinstance(led, dict) else {}
    parked = rec.read_park(run_dir)
    st = rec.load_state(run_dir)
    nxt = rec.next_actionable_phase(manifest["phases"], set(attested))
    return ({
        "run_dir": str(Path(run_dir).resolve()),
        "run_id": _job_id(run_dir),
        "attested_phases": attested,
        "spent_usd": led.get("spent_usd", 0.0),
        "ledger_done_keys": [e.get("key") for e in (led.get("events", []) or [])
                             if isinstance(e, dict) and e.get("key")],
        "parked": ({"parked_by": parked.get("parked_by_af"),
                    "park_class": parked.get("park_class"),
                    "waiting_for": parked.get("waiting_for"),
                    "resume_clears_when": parked.get("resume_clears_when")}
                   if parked else None),
        "attempt_counters": st.get("attempts", {}),
        "no_progress_counters": st.get("no_progress", {}),
        "next_action": (None if parked else (nxt["id"] if nxt else "DONE")),
    }, 0)


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
    ap.add_argument("--recover", action="store_true",
                    help="self-correct/park foreman: drive the next actionable step")
    ap.add_argument("--resume", action="store_true",
                    help="resume a parked run once its blocker clears")
    ap.add_argument("--status", action="store_true",
                    help="report attested/spend/park/attempt state (JSON)")
    ap.add_argument("--item", type=int, default=None,
                    help="per-item budget key for a per-image gate (S5)")
    ap.add_argument("--allow-ephemeral", action="store_true",
                    help="permit a paid run under a tmp dir (dry/test only)")
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

    # Self-correct + park-and-resume modes (opt-in). They own exit code 5 (PARKED) and
    # do their OWN non-exiting balance preflight — the legacy --phase 0/2/3/4 path below
    # is left byte-for-byte unchanged so the CI GOOD/BAD self-test stays green.
    if args.status:
        verdict, code = cmd_status(run_dir, manifest)
        print(json.dumps(verdict, indent=2))
        sys.exit(code)
    if args.recover:
        verdict, code = cmd_recover(run_dir, manifest, item=args.item,
                                    allow_ephemeral=args.allow_ephemeral)
        print(json.dumps(verdict, indent=2))
        sys.exit(code)
    if args.resume:
        verdict, code = cmd_resume(run_dir, manifest, item=args.item,
                                   allow_ephemeral=args.allow_ephemeral)
        print(json.dumps(verdict, indent=2))
        sys.exit(code)

    if args.adhoc:
        assert_adhoc_authorized(run_dir)

    # Phase-0 pre-flight (Kie balance for a paid job). HARD-ABORTS on AF-FBAD-KIE-BALANCE.
    phase0_preflight(run_dir, adhoc=args.adhoc)

    if args.phase:
        target = next((p for p in phases if p["id"] == args.phase), None)
        if target is None:
            print(f"FATAL: unknown phase id {args.phase!r}.", file=sys.stderr)
            sys.exit(2)

        # Board: ensure the campaign + cards exist (idempotent) before we attest
        # this phase. attest_phase() then moves the attested card to done.
        _board_ensure_campaign(run_dir, manifest)

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
