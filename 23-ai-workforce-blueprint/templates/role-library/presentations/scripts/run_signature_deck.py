#!/usr/bin/env python3
"""
run_signature_deck.py — DETERMINISTIC SIGNATURE-DECK RUNNER (Decision 3C).

================================================================================
A deterministic state machine over PIPELINE-MANIFEST.json. It does NOT replace
build_deck.py — it ORCHESTRATES the pipeline AROUND it and calls build_deck.py for
the render phase. The render path inside build_deck.py is never touched.
================================================================================

WHAT IT GUARANTEES
  * Manifest-driven phase order. Phases run in ascending `order`. Each phase's
    completion is proven by an ATTESTATION appended to
    working/checkpoints/process_manifest.json.
  * Skipping / reordering a phase is STRUCTURALLY IMPOSSIBLE. Before dispatching
    phase N, EVERY phase with a lower `order` must have an attestation on disk AND
    its produces_artifact present. A missing precondition is a HARD ABORT
    (AF-PHASE-SKIPPED, exit 2) — EXCEPT when an explicit, logged OWNER-AUTHORIZED
    skip record covers it (working/checkpoints/phase_skip_approvals.json,
    owner_approved:true). That is not a free flag — absent the signed record, the
    precondition is unmet and the run aborts.
  * Phase-0 PRE-FLIGHT (before ANY dispatch/render):
      - detect_platform() box-type resource note (mac -> fewer workers; vps ->
        more) recorded into the brief/attestation.
      - Kie.ai BALANCE pre-flight (GET https://api.kie.ai/api/v1/chat/credit):
        HARD-ABORTS (AF-KIE-BALANCE, exit 4) before any render when
        balance < estimated_floor. SHARED with build_deck.kie_balance_preflight.
  * --adhoc escape: OWNER-authorized + logged
    (working/checkpoints/adhoc_authorization.json). Without the logged record,
    --adhoc is REFUSED.

EXIT CODES
    0 — all phases attested (or owner-authorized skips), pre-flight clean.
    2 — phase-precondition violation (AF-PHASE-SKIPPED) or usage error.
    4 — Phase-0 balance abort (AF-KIE-BALANCE).
    3 — a build_deck.py subprocess (render phase) failed preflight/render.

USAGE
    python3 run_signature_deck.py --run-dir DIR --slides slides.json --out out.pptx
        [--plan]            # print the resolved phase plan + preconditions, do not run
        [--phase PHASE_ID]  # advance to / dispatch a single phase (checks preconditions)
        [--platform vps|mac]
        [--adhoc]           # owner-authorized + logged escape (refused without the record)

This is a SCRIPT (not a manifest role/phase). sync_check.py does not require a
symbol for it; AF-PHASE-SKIPPED is enforced_by:runner with py_symbol:null.
"""

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Reuse build_deck.py's primitives — do NOT reimplement (detect_platform,
# find_run_dir, the shared Kie balance pre-flight, the run-dir JSON reader).
import build_deck as bd


# ---------------------------------------------------------------------------
# Manifest resolution (same cluster-or-deployed layout sync_check uses)
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
        candidates.append(repo / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json")
    candidates += [
        HERE.parent / "sops" / "PIPELINE-MANIFEST.json",
        HERE.parent / "PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            return json.loads(c.read_text())
    print("FATAL: PIPELINE-MANIFEST.json not found.", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Attestation ledger (process_manifest.json is build_deck.py's cumulative file)
# ---------------------------------------------------------------------------
def _process_manifest_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "process_manifest.json"


def _load_process_manifest(run_dir: Path) -> dict:
    p = _process_manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _attested_phase_ids(run_dir: Path) -> set:
    """Return the set of phase_ids that have an attestation. Accepts BOTH the
    runner's phase attestations (under 'phase_attestations') AND build_deck.py's
    own 'render' phase record (so a render done by the canonical renderer counts as
    the render phase being attested without the runner re-stamping it)."""
    obj = _load_process_manifest(run_dir)
    ids = set()
    for att in obj.get("phase_attestations", []) or []:
        if isinstance(att, dict) and att.get("phase_id"):
            ids.add(att["phase_id"])
    # build_deck.py appends render records under "phases": [{"phase":"render", ...}]
    for ph in obj.get("phases", []) or []:
        if isinstance(ph, dict) and ph.get("phase") == "render":
            ids.add("P4-RENDER")
    return ids


def attest_phase(run_dir: Path, phase_id: str, role: str, status: str,
                 artifact_sha: str = "") -> None:
    """Append a phase attestation to process_manifest.json (never clobber prior
    records — mirrors build_deck.write_process_manifest's append discipline)."""
    p = _process_manifest_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = _load_process_manifest(run_dir)
    obj.setdefault("phase_attestations", [])
    obj["phase_attestations"].append({
        "phase_id": phase_id,
        "owning_role": role,
        "status": status,
        "artifact_sha": artifact_sha,
        "attested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    p.write_text(json.dumps(obj, indent=2))


# ---------------------------------------------------------------------------
# Owner-authorized skip records (the controlled exception — NOT a free flag)
# ---------------------------------------------------------------------------
def load_skip_approvals(run_dir: Path) -> dict:
    """Return {phase_id: approval_record} for every owner-authorized skip whose
    record is well-formed (owner_approved:true + approved_by + reason). A malformed
    or owner_approved:false record does NOT authorize a skip."""
    p = run_dir / "working" / "checkpoints" / "phase_skip_approvals.json"
    approvals = {}
    if not p.exists():
        return approvals
    try:
        obj = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return approvals
    records = obj if isinstance(obj, list) else obj.get("approvals", []) if isinstance(obj, dict) else []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if (rec.get("owner_approved") is True and rec.get("phase_id")
                and str(rec.get("approved_by", "")).strip()
                and str(rec.get("reason", "")).strip()):
            approvals[rec["phase_id"]] = rec
    return approvals


def _artifact_present(run_dir: Path, produces_artifact: str) -> bool:
    """True when a phase's declared produces_artifact exists in the run dir.
    Supports glob patterns (e.g. 'working/research/brief-*.md'). A null/empty
    artifact spec counts as satisfied (the phase declares no concrete artifact)."""
    spec = (produces_artifact or "").strip()
    if not spec:
        return True
    # Try run-dir-relative, then a bundle-style bare filename glob anywhere.
    if "*" in spec or "?" in spec:
        if list(run_dir.glob(spec)):
            return True
        return bool(list(run_dir.glob("**/" + spec.split("/")[-1])))
    p = run_dir / spec
    if p.exists():
        return True
    # bare-filename artifacts (e.g. '*-FINAL.pptx') may live in the bundle dir
    return bool(list(run_dir.glob("**/" + spec.split("/")[-1])))


# ---------------------------------------------------------------------------
# Phase preconditions — AF-PHASE-SKIPPED
# ---------------------------------------------------------------------------
def check_phase_preconditions(run_dir: Path, phases: list, target_phase_id: str) -> str:
    """Return "" when every phase with a lower `order` than target is attested AND
    its produces_artifact is present (or is covered by an owner-authorized skip).
    Otherwise return a fatal AF-PHASE-SKIPPED message. This computes the ordered
    prior-phase list and DELEGATES the attestation/owner-skip decision to the shared
    build_deck.check_phase_preconditions (single source of truth — not reimplemented).
    It additionally enforces produces_artifact presence for each prior phase."""
    by_id = {ph["id"]: ph for ph in phases}
    target = by_id.get(target_phase_id)
    if target is None:
        return f"AF-PHASE-SKIPPED: unknown phase id {target_phase_id!r} (not in manifest)."
    target_order = target.get("order", 0)
    prior = sorted([ph for ph in phases if ph.get("order", 0) < target_order],
                   key=lambda p: p.get("order", 0))
    prior_ids = [ph["id"] for ph in prior]
    # Shared attestation / owner-skip decision (build_deck is the single source of truth).
    reason = bd.check_phase_preconditions(run_dir, target_phase_id, prior_ids)
    if reason:
        return reason
    # Additionally require each attested prior phase's produces_artifact to be present
    # (an attestation must correspond to a real artifact, unless owner-skip-approved).
    approvals = load_skip_approvals(run_dir)
    for ph in prior:
        pid = ph["id"]
        if pid in approvals:
            continue
        if not _artifact_present(run_dir, ph.get("produces_artifact", "")):
            return (f"AF-PHASE-SKIPPED: prior phase {pid!r} is attested but its "
                    f"produces_artifact {ph.get('produces_artifact')!r} is not present in "
                    f"the run dir — an attestation must correspond to a real artifact. "
                    f"Re-run {pid!r} or add a logged owner-authorized skip.")
    return ""


# ---------------------------------------------------------------------------
# Phase-0 pre-flight — platform note + Kie balance (AF-KIE-BALANCE)
# ---------------------------------------------------------------------------
def _slide_count(run_dir: Path, slides_path: Path) -> int:
    try:
        slides = json.loads(slides_path.read_text())
        if isinstance(slides, list):
            return len(slides)
    except Exception:  # noqa: BLE001
        pass
    n = bd._count_output_slides(run_dir, slides_path)
    return n or 0


def phase0_preflight(run_dir: Path, slides_path: Path, platform_override=None,
                     adhoc: bool = False) -> None:
    """Phase-0: detect box type (resource note) + Kie balance pre-flight. HARD-ABORT
    (exit 4) on AF-KIE-BALANCE before any phase is dispatched."""
    platform = bd.detect_platform(run_dir, override=platform_override)
    worker_note = "mac -> fewer parallel render workers" if platform == "mac" else \
                  "vps -> more parallel render workers"
    print(f"=== PHASE-0 PRE-FLIGHT — box_type={platform} ({worker_note}) ===", flush=True)

    slide_count = _slide_count(run_dir, slides_path)
    print(f"=== PHASE-0 — deck slide_count={slide_count} ===", flush=True)

    if adhoc:
        print("=== PHASE-0 — adhoc (owner-authorized): Kie balance pre-flight skipped ===",
              flush=True)
        attest_phase(run_dir, "P-0-PREFLIGHT", "run_signature_deck",
                     "preflight_ok_adhoc")
        return

    api_key = ""
    try:
        api_key = bd.load_api_key()
    except SystemExit:
        # No key on this box — the render-phase subprocess will fail loud on its own.
        print("=== PHASE-0 — no Kie API key on this box; balance pre-flight deferred to "
              "the render subprocess ===", flush=True)
    reason = bd.kie_balance_preflight(run_dir, slide_count, api_key or None)
    if reason:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: " + reason, file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)
    print("=== PHASE-0 — Kie balance pre-flight PASSED (balance >= estimated floor) ===",
          flush=True)
    attest_phase(run_dir, "P-0-PREFLIGHT", "run_signature_deck", "preflight_ok")


# ---------------------------------------------------------------------------
# Plan printing
# ---------------------------------------------------------------------------
def print_plan(run_dir: Path, phases: list) -> None:
    attested = _attested_phase_ids(run_dir)
    approvals = load_skip_approvals(run_dir)
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    print("=== SIGNATURE-DECK PHASE PLAN (manifest order) ===")
    for ph in ordered:
        pid = ph["id"]
        if pid in attested:
            state = "ATTESTED"
        elif pid in approvals:
            state = "SKIP(owner-authorized)"
        else:
            state = "pending"
        print(f"  [{ph.get('order'):>5}] {pid:<16} {state:<22} "
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
    ap = argparse.ArgumentParser(description="Deterministic signature-deck runner (3C).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--slides", help="slides.json (required to run; optional for --plan)")
    ap.add_argument("--out", help="out.pptx (required to dispatch the render phase)")
    ap.add_argument("--phase", help="dispatch/advance a single phase id (checks preconditions)")
    ap.add_argument("--platform", choices=["vps", "mac"], default=None)
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

    if not args.slides:
        print("FATAL: --slides is required to run (use --plan to inspect only).",
              file=sys.stderr)
        sys.exit(2)
    slides_path = Path(args.slides).resolve()
    if not slides_path.exists():
        print(f"FATAL: slides.json not found: {slides_path}", file=sys.stderr)
        sys.exit(2)

    # Phase-0 pre-flight (platform note + Kie balance). HARD-ABORTS on AF-KIE-BALANCE.
    phase0_preflight(run_dir, slides_path, platform_override=args.platform,
                     adhoc=args.adhoc)

    # Single-phase dispatch: enforce preconditions (AF-PHASE-SKIPPED), then dispatch.
    if args.phase:
        if not args.adhoc:
            reason = check_phase_preconditions(run_dir, phases, args.phase)
            if reason:
                print("\nFATAL: " + reason, file=sys.stderr)
                sys.exit(2)
        target = next((p for p in phases if p["id"] == args.phase), None)
        # The render phase is the only one this runner dispatches into build_deck.py;
        # all other phases are produced by their owning department role/agent, and the
        # runner records their attestation once their produces_artifact is present.
        if args.phase == "P4-RENDER":
            if not args.out:
                print("FATAL: --out is required to dispatch the render phase.",
                      file=sys.stderr)
                sys.exit(2)
            rc = _dispatch_render(run_dir, slides_path, Path(args.out).resolve(),
                                  platform=args.platform, adhoc=args.adhoc)
            sys.exit(rc)
        # Non-render phase: verify the artifact landed, then attest.
        if _artifact_present(run_dir, target.get("produces_artifact", "")):
            attest_phase(run_dir, args.phase, target.get("owning_role", ""),
                         "artifact_present")
            print(f"=== PHASE {args.phase} attested (produces_artifact present) ===",
                  flush=True)
            sys.exit(0)
        print(f"FATAL: phase {args.phase} produces_artifact "
              f"{target.get('produces_artifact')!r} is not present; cannot attest.",
              file=sys.stderr)
        sys.exit(2)

    # No --phase: print the plan (the safe default — the runner never blindly fans
    # out every department role; it dispatches the render and attests artifacts).
    print_plan(run_dir, phases)
    print("\nNote: pass --phase P4-RENDER --out out.pptx to dispatch the deterministic "
          "render (build_deck.py) once all upstream phases are attested.", flush=True)
    sys.exit(0)


def _dispatch_render(run_dir: Path, slides_path: Path, out_path: Path,
                     platform=None, adhoc=False) -> int:
    """Dispatch the render phase by invoking build_deck.py as a SUBPROCESS with the
    same args (its render path is untouched). Returns the subprocess return code."""
    import subprocess
    cmd = [sys.executable, str(HERE / "build_deck.py"), str(slides_path), str(out_path),
           "--run-dir", str(run_dir)]
    if platform:
        cmd += ["--platform", platform]
    if adhoc:
        cmd += ["--adhoc-no-process"]
    print(f"=== DISPATCH RENDER (subprocess): {' '.join(cmd)} ===", flush=True)
    proc = subprocess.run(cmd)
    if proc.returncode == 0:
        # build_deck.py appends its own render record; the attestation reader counts it.
        print("=== RENDER phase complete — build_deck.py render record attested ===",
              flush=True)
    return proc.returncode


if __name__ == "__main__":
    main()
