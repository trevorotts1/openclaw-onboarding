#!/usr/bin/env python3
"""
executive_producer.py — DETERMINISTIC MOVIE-PRODUCER STATE-MACHINE GATE-AND-ATTEST DRIVER.

================================================================================
A deterministic state machine over VIDEO-PIPELINE-MANIFEST.json. It is OUR code
that gates AROUND the upstream OpenMontage engine — it does NOT replace, vendor,
or import any OpenMontage source (AGPLv3-safe; mirrors how run_signature_deck.py
wraps build_deck.py for the Presentations department). OpenMontage still produces
the assets and the render; this driver makes skipping/reordering/forging a phase
structurally impossible.
================================================================================

WHAT IT GUARANTEES
  * Manifest-driven phase order. The 5 DMAIC phases (V-DEFINE, V-MEASURE,
    V-ANALYZE, V-IMPROVE, V-CONTROL) run in ascending `order`. Each phase's
    completion is proven by an ATTESTATION appended to
    working/checkpoints/video_process_manifest.json.
  * Skipping / reordering / wrong-role is STRUCTURALLY IMPOSSIBLE. Before
    dispatching phase N, EVERY phase with a lower `order` must have an attestation
    on disk (by its declared owning_role) AND its produces_artifact present. A
    missing precondition is a HARD ABORT (AF-VID-PHASE-SKIPPED, exit 2) — EXCEPT
    when an explicit, logged OWNER-AUTHORIZED skip record covers it
    (working/checkpoints/phase_skip_approvals.json, owner_approved:true). The free
    documentary-montage path is exactly this: a logged owner-authorized skip of
    V-ANALYZE (Rule-Zero) because there is no paid call.
  * RECEIPT VALIDATION, not mere presence. A phase is attested only when its
    produces_artifact passes the manifest checker (video_build_check._chk_*):
    e.g. V-IMPROVE requires render-receipt ffprobe_pass:true + a real kie_task_id
    when Kie was in scope; a fabricated/placeholder task id is exit 3.
  * Phase-0 PRE-FLIGHT (before ANY paid dispatch):
      - Kie.ai BALANCE pre-flight for a PAID job (GET the credit endpoint):
        HARD-ABORTS (AF-VID-KIE-BALANCE, exit 4) when balance < estimated floor or
        the balance cannot be verified. SHARED with video_build_check.kie_balance_preflight.
  * --adhoc escape: OWNER-authorized + logged
    (working/checkpoints/adhoc_authorization.json). Without the logged record,
    --adhoc is REFUSED (exit 2).

EXIT CODES
    0 — clean: all phases attested (or owner-authorized skips), pre-flight clean.
    2 — phase-precondition violation (AF-VID-PHASE-SKIPPED), usage error, or a
        refused --adhoc.
    3 — a receipt failed VALIDATION (the produces_artifact is present but its
        checker rejected it — e.g. AF-VID-NO-FFPROBE / AF-VID-FABRICATED-RECEIPT).
    4 — Phase-0 balance abort (AF-VID-KIE-BALANCE).

USAGE
    python3 executive_producer.py --run-dir DIR [--brief job-manifest.json]
        [--plan]                 # print the resolved phase plan + preconditions
        [--phase V-IMPROVE]      # advance to / attest a single phase (checks preconditions)
        [--adhoc]                # owner-authorized + logged escape (refused without the record)

This is a SCRIPT (not a manifest role/phase). video_sync_check.py does not require a
manifest symbol for it; AF-VID-PHASE-SKIPPED is enforced_by:driver with py_symbol:null.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent  # .../47-movie-producer/scripts

# Receipt validators + Phase-0 balance live in our sibling library (OUR code).
import video_build_check as vbc
# Producer-side Command Center board caller (OUR code). FAIL-SOFT by contract:
# every cc_board call catches its own errors and returns a value, so a board outage
# / missing token NEVER affects this driver's exit codes or flow. (FIX-S36-40)
try:
    import cc_board
except Exception:  # noqa: BLE001 — the board is a convenience, never a hard dep.
    cc_board = None


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


def _runtime_manifest_path() -> Path:
    """SK1-63: the canonical manifest lives at repo-root universal-sops/, which is NOT
    shipped inside the (content-hashed) skill dir. install.sh copies it here — a runtime
    dir OUTSIDE the hashed skill dir (sibling of the OpenMontage clone) — so this driver
    can resolve it on a client box that never received the universal-sops sibling."""
    override = os.environ.get("OPENCLAW_OPENMONTAGE_DIR", "").strip()
    if override:
        # The manifest sits beside the OpenMontage clone dir.
        return Path(override).parent / "VIDEO-PIPELINE-MANIFEST.json"
    return Path.home() / ".openclaw" / "openmontage-runtime" / "VIDEO-PIPELINE-MANIFEST.json"


def load_manifest() -> dict:
    repo = _find_repo_root(HERE)
    candidates = []
    # Highest priority: an explicit operator override.
    env_path = os.environ.get("OPENCLAW_VIDEO_PIPELINE_MANIFEST", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    if repo:
        candidates.append(repo / "universal-sops" / "video-pipeline-craft"
                          / "VIDEO-PIPELINE-MANIFEST.json")
    candidates += [
        # SK1-63: the runtime copy install.sh places outside the hashed skill dir.
        _runtime_manifest_path(),
        HERE.parent / "sops" / "VIDEO-PIPELINE-MANIFEST.json",
        HERE.parent / "VIDEO-PIPELINE-MANIFEST.json",
        HERE / "VIDEO-PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception as exc:  # noqa: BLE001
                print(f"FATAL: VIDEO-PIPELINE-MANIFEST.json is not valid JSON ({exc}).",
                      file=sys.stderr)
                sys.exit(2)
    looked = "\n  ".join(str(c) for c in candidates)
    print("FATAL: VIDEO-PIPELINE-MANIFEST.json not found. The manifest ships in the repo "
          "at universal-sops/video-pipeline-craft/ and is NOT bundled inside the hashed "
          "skill dir; install.sh (Step 4.5) copies it to the runtime location below.\n"
          "Re-run install.sh, or set OPENCLAW_VIDEO_PIPELINE_MANIFEST to its path.\n"
          f"Looked in:\n  {looked}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Attestation ledger — working/checkpoints/video_process_manifest.json
# ---------------------------------------------------------------------------
def _process_manifest_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "video_process_manifest.json"


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


def attest_phase(run_dir: Path, phase_id: str, role: str, status: str,
                 checker: str = "", note: str = "") -> None:
    """Append a phase attestation (never clobber prior records). Records the
    owning_role so the precondition gate can detect a wrong-role attestation."""
    p = _process_manifest_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = _load_process_manifest(run_dir)
    obj.setdefault("job_id", _job_id(run_dir))
    obj.setdefault("pipeline_selected", _pipeline_selected(run_dir))
    obj.setdefault("phase_attestations", [])
    obj["phase_attestations"].append({
        "phase_id": phase_id,
        "owning_role": role,
        "status": status,
        "checker": checker,
        "note": note,
        "attested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    obj["finalized"] = (phase_id == "V-CONTROL" and status == "attested")
    p.write_text(json.dumps(obj, indent=2))


def _job_id(run_dir: Path) -> str:
    jm = vbc._load_job_manifest(run_dir)
    return jm.get("job_id", "") if isinstance(jm, dict) else ""


def _pipeline_selected(run_dir: Path) -> str:
    jm = vbc._load_job_manifest(run_dir)
    return jm.get("pipeline_selected", "") if isinstance(jm, dict) else ""


# ---------------------------------------------------------------------------
# Command Center board hookup (FAIL-SOFT). Lands the run on the Kanban board as one
# campaign + one card per DMAIC phase, and moves each attested phase card to `done`
# by walking the LEGAL status path (in_progress -> review -> done) so the QC review
# column is never skipped. A disabled board (no MISSION_CONTROL_URL) makes all of
# this a clean no-op, and the campaign_id + finished MP4 path are stamped into the
# render receipt at V-CONTROL. (FIX-S36-40)
# ---------------------------------------------------------------------------
def _board_stage_slug(phase_id: str) -> str:
    return str(phase_id).lower()[:64]


def _board_stages(phases: list) -> list:
    return [{"slug": _board_stage_slug(p["id"]), "title": p.get("name") or p["id"]}
            for p in sorted(phases, key=lambda x: x.get("order", 0))]


def _board_marker(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "cc-board.created"


def _board_ensure_campaign(run_dir: Path, manifest: dict) -> None:
    """Create the campaign + its 5 phase cards. Idempotent via a marker file.
    NEVER raises (board hookup must not break the driver)."""
    if cc_board is None:
        return
    try:
        job_id = _job_id(run_dir)
        if not job_id:
            return
        marker = _board_marker(run_dir)
        if marker.exists():
            return
        jm = vbc._load_job_manifest(run_dir)
        jm = jm if isinstance(jm, dict) else {}
        show_name = str(jm.get("title") or jm.get("topic") or job_id)
        campaign_id = cc_board.create_campaign(
            job_id,
            show_name,
            stages=_board_stages(manifest.get("phases", [])),
            owner=jm.get("owner"),
            department=jm.get("department") or "video",
            workspace=jm.get("workspace"),
            agent_id=jm.get("agent_id"),
            money_ceiling_usd=jm.get("budget_ceiling_usd"),
            estimated_cost_usd=jm.get("estimated_cost_usd"),
            show_date=jm.get("show_date"),
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(campaign_id or job_id)
    except Exception:  # noqa: BLE001 — board hookup must NEVER break the driver.
        pass


def _board_move(run_dir: Path, phase_id: str, status: str, *, reason: str = "") -> None:
    """Drive one phase card to `status` (fail-soft, never raises). set_stage_status
    walks the legal path, so a move to `done` traverses `review` — the QC column is
    never skipped (the V-CONTROL card lands via review -> done)."""
    if cc_board is None:
        return
    try:
        job_id = _job_id(run_dir)
        if not job_id:
            return
        cc_board.set_stage_status(job_id, _board_stage_slug(phase_id), status,
                                  reason=reason or None)
    except Exception:  # noqa: BLE001
        pass


def _board_stamp_control(run_dir: Path) -> None:
    """At V-CONTROL, stamp campaign_id (from the board marker == job_id fallback) and
    the finished MP4 path into the render receipt. Fail-soft; merge-if-exists."""
    if cc_board is None:
        return
    try:
        job_id = _job_id(run_dir)
        marker = _board_marker(run_dir)
        campaign_id = marker.read_text().strip() if marker.exists() else (job_id or None)
        rr = vbc._render_receipt(run_dir)
        final_mp4 = None
        if isinstance(rr, dict):
            final_mp4 = (str(rr.get("final_mp4_path") or rr.get("output_path") or "").strip()
                         or None)
        cc_board.stamp_receipt(run_dir, campaign_id=campaign_id, final_mp4_path=final_mp4)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Owner-authorized skip records (the controlled exception — NOT a free flag)
# ---------------------------------------------------------------------------
def load_skip_approvals(run_dir: Path) -> dict:
    """Return {phase_id: record} for every well-formed owner-authorized skip
    (owner_approved:true + approved_by + reason). A malformed or owner_approved:false
    record does NOT authorize a skip."""
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
# Phase preconditions — AF-VID-PHASE-SKIPPED
# ---------------------------------------------------------------------------
def check_phase_preconditions(run_dir: Path, phases: list, target_phase_id: str) -> str:
    """Return "" when every phase with a lower `order` than target is attested (by
    its declared owning_role) AND its produces_artifact is present — OR is covered by
    an owner-authorized skip. Otherwise return a fatal AF-VID-PHASE-SKIPPED message."""
    by_id = {ph["id"]: ph for ph in phases}
    target = by_id.get(target_phase_id)
    if target is None:
        return (f"AF-VID-PHASE-SKIPPED: unknown phase id {target_phase_id!r} "
                "(not in VIDEO-PIPELINE-MANIFEST).")
    target_order = target.get("order", 0)
    prior = sorted([ph for ph in phases if ph.get("order", 0) < target_order],
                   key=lambda p: p.get("order", 0))
    approvals = load_skip_approvals(run_dir)
    atts = _attestations(run_dir)
    att_by_phase = {}
    for a in atts:
        if isinstance(a, dict) and a.get("phase_id"):
            att_by_phase[a["phase_id"]] = a
    for ph in prior:
        pid = ph["id"]
        if pid in approvals:
            continue
        att = att_by_phase.get(pid)
        if not att:
            return ("AF-VID-PHASE-SKIPPED: phase " + target_phase_id + " was dispatched "
                    "before prior phase " + pid + " was attested. Each phase N+1 reads "
                    "phase N's attestation in working/checkpoints/"
                    "video_process_manifest.json as a precondition, so skipping or "
                    "reordering a phase is structurally impossible EXCEPT with a logged "
                    "owner-authorized skip (working/checkpoints/phase_skip_approvals.json "
                    "with phase_id + owner_approved:true + approved_by + reason).")
        # Wrong-role attestation is a violation (a phase's owning_role is fixed).
        owner = ph.get("owning_role", "")
        if owner and att.get("owning_role") and att["owning_role"] != owner:
            return ("AF-VID-PHASE-SKIPPED: prior phase " + pid + " was attested by "
                    f"{att['owning_role']!r}, but its owning_role is {owner!r}. A phase "
                    "must be produced by its declared owning_role.")
        if not _artifact_present(run_dir, ph.get("produces_artifact", "")):
            return ("AF-VID-PHASE-SKIPPED: prior phase " + pid + " is attested but its "
                    f"produces_artifact {ph.get('produces_artifact')!r} is not present in "
                    "the run dir — an attestation must correspond to a real artifact. "
                    "Re-run " + pid + " or add a logged owner-authorized skip.")
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
        fn = vbc.CHECKERS.get(name)
        if fn is None:
            return False, (f"AF-VID-PHASE-SKIPPED: phase {phase['id']} names checker "
                           f"{name!r}, which is not defined in video_build_check.py.")
        reason = fn(run_dir)
        if reason:
            return False, reason
    return True, ""


# ---------------------------------------------------------------------------
# Phase-0 pre-flight — Kie balance (AF-VID-KIE-BALANCE) for a PAID job
# ---------------------------------------------------------------------------
def _estimated_cost(run_dir: Path) -> float:
    mr = vbc._measure_receipt(run_dir)
    if isinstance(mr, dict) and isinstance(mr.get("estimated_cost_usd"), (int, float)):
        return float(mr["estimated_cost_usd"])
    jm = vbc._load_job_manifest(run_dir)
    if isinstance(jm, dict) and isinstance(jm.get("estimated_cost_usd"), (int, float)):
        return float(jm["estimated_cost_usd"])
    return 0.0


def _load_kie_api_key() -> str:
    import os
    return os.environ.get("KIE_API_KEY", "") or ""


def phase0_preflight(run_dir: Path, adhoc: bool = False) -> None:
    """Phase-0: Kie balance pre-flight for a paid job. HARD-ABORT (exit 4) on
    AF-VID-KIE-BALANCE before any paid dispatch."""
    paid = vbc._paid_in_scope(run_dir)
    print(f"=== PHASE-0 PRE-FLIGHT — paid_job={paid} ===", flush=True)
    if adhoc:
        print("=== PHASE-0 — adhoc (owner-authorized): Kie balance pre-flight skipped ===",
              flush=True)
        attest_phase(run_dir, "V-0-PREFLIGHT", "executive_producer",
                     "preflight_ok_adhoc")
        return
    if not paid:
        print("=== PHASE-0 — free path (no paid Kie call); balance pre-flight N/A ===",
              flush=True)
        attest_phase(run_dir, "V-0-PREFLIGHT", "executive_producer", "preflight_ok_free")
        return
    est = _estimated_cost(run_dir)
    api_key = _load_kie_api_key()
    if not api_key:
        # SK1-67: a PAID job with no Kie key can never run — its balance cannot be
        # verified and the paid generation will fail downstream. Deferring here (silent
        # pass) let a keyless paid job proceed to a mid-run failure. Fail LOUD now.
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: AF-VID-KIE-BALANCE — this is a PAID Kie job but KIE_API_KEY "
              "is not set on this box. A paid pipeline cannot run and its credit balance "
              "cannot be verified without the client's Kie key. Set KIE_API_KEY, switch to "
              "the free documentary-montage path, or re-run adhoc (owner-authorized) to "
              "skip the balance pre-flight deliberately.", file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)
    reason = vbc.kie_balance_preflight(run_dir, est, api_key)
    if reason:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: " + reason, file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)
    print("=== PHASE-0 — Kie balance pre-flight PASSED (balance >= estimated floor) ===",
          flush=True)
    attest_phase(run_dir, "V-0-PREFLIGHT", "executive_producer", "preflight_ok")


# ---------------------------------------------------------------------------
# Plan printing
# ---------------------------------------------------------------------------
def print_plan(run_dir: Path, phases: list) -> None:
    attested = _attested_phase_ids(run_dir)
    approvals = load_skip_approvals(run_dir)
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    print("=== MOVIE-PRODUCER PHASE PLAN (manifest order) ===")
    for ph in ordered:
        pid = ph["id"]
        if pid in attested:
            state = "ATTESTED"
        elif pid in approvals:
            state = "SKIP(owner-authorized)"
        else:
            state = "pending"
        print(f"  [{ph.get('order'):>3}] {pid:<12} {state:<22} "
              f"owner={ph.get('owning_role')}  -> {ph.get('produces_artifact')}")


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
    print("!! ADHOC MODE (owner-authorized + logged): phase preconditions + balance "
          "pre-flight relaxed.", flush=True)
    print("!! Output of this run is NOT a process-compliant client deliverable.", flush=True)
    print(bar + "\n", flush=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Deterministic Movie-Producer gate-and-attest driver (v14.1.0).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--brief", help="path to job-manifest.json (informational; the "
                                     "driver reads working/job-manifest.json in the run dir)")
    ap.add_argument("--phase", help="advance/attest a single phase id (checks preconditions)")
    ap.add_argument("--plan", action="store_true", help="print the phase plan and exit")
    ap.add_argument("--adhoc", action="store_true",
                    help="owner-authorized + logged escape (refused without the record)")
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

    # Phase-0 pre-flight (Kie balance for a paid job). HARD-ABORTS on AF-VID-KIE-BALANCE.
    phase0_preflight(run_dir, adhoc=args.adhoc)

    if args.phase:
        target = next((p for p in phases if p["id"] == args.phase), None)
        if target is None:
            print(f"FATAL: unknown phase id {args.phase!r}.", file=sys.stderr)
            sys.exit(2)

        # Board (FAIL-SOFT): ensure the campaign + 5 phase cards exist, then reflect
        # this phase as in_progress. A disabled board makes both a clean no-op.
        _board_ensure_campaign(run_dir, manifest)
        _board_move(run_dir, args.phase, "in_progress",
                    reason=f"{args.phase} dispatched")

        # 1) Preconditions — every lower-order phase attested + artifact present (or
        #    owner-skipped). Skipping/reordering/wrong-role = AF-VID-PHASE-SKIPPED (exit 2).
        if not args.adhoc:
            reason = check_phase_preconditions(run_dir, phases, args.phase)
            if reason:
                print("\nFATAL: " + reason, file=sys.stderr)
                sys.exit(2)

        # 2) The produces_artifact must be present at all (else this phase has not run).
        if not _artifact_present(run_dir, target.get("produces_artifact", "")):
            print(f"\nFATAL: AF-VID-PHASE-SKIPPED: phase {args.phase} produces_artifact "
                  f"{target.get('produces_artifact')!r} is not present; the phase has not "
                  "produced its receipt — cannot attest.", file=sys.stderr)
            sys.exit(2)

        # 3) RECEIPT VALIDATION — present is not enough; the receipt must pass its
        #    manifest checker(s). A present-but-invalid receipt is exit 3.
        if not args.adhoc:
            ok, reason = validate_phase_receipt(run_dir, target)
            if not ok:
                print("\nFATAL (receipt failed validation): " + reason, file=sys.stderr)
                sys.exit(3)

        attest_phase(run_dir, args.phase, target.get("owning_role", ""), "attested",
                     checker=(target.get("preflight") or {}).get("checker", ""))
        # Board (FAIL-SOFT): move this phase card to `done`, walking the legal path
        # (in_progress -> review -> done) so the QC review column is never skipped.
        # At V-CONTROL also stamp campaign_id + the finished MP4 path into the receipt.
        if args.phase == "V-CONTROL":
            _board_stamp_control(run_dir)
        _board_move(run_dir, args.phase, "done", reason=f"{args.phase} attested")
        print(f"=== PHASE {args.phase} ATTESTED (preconditions met + receipt validated) ===",
              flush=True)
        sys.exit(0)

    # No --phase: the safe default is to print the plan.
    print_plan(run_dir, phases)
    print("\nNote: pass --phase V-DEFINE (then V-MEASURE, V-ANALYZE, V-IMPROVE, "
          "V-CONTROL in order) to attest each phase once its receipt is present and "
          "valid. Lower-order phases must be attested first (AF-VID-PHASE-SKIPPED).",
          flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
