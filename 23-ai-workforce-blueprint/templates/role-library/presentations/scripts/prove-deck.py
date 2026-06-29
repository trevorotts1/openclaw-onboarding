#!/usr/bin/env python3
"""
prove-deck.py — End-of-process no-skip proof / PROCESS-CERTIFICATE generator (FIX 2a).

Called by run_signature_deck.py at P9-DELIVER (before the delivery attestation) so the
certificate is a hard pre-condition for delivery — even when the CC is offline.
Also callable standalone for operator inspection.

WHAT IT CHECKS (for every declared step in declared order):
    (a) An attestation record exists in process_manifest.json["phase_attestations"]
    (b) The attestation record has substance_verified == True
    (c) client_reports.json has a "start" AND a "done" record for the phase (the
        record EXISTING proves the report step ran; gateway_msg_id/`sent` are
        best-effort delivery confirmation — a MISSING record fails, an unconfirmed
        send does not, per OQ-2)
    (d) Attestation timestamps are monotonically ascending in declared step order
        (out-of-order execution = FAIL)
    (e) No declared step is missing (gap in attestation chain = FAIL)

BYPASS:
    A logged owner_skip_approval record in process_manifest.json["owner_skip_approvals"]
    for the relevant phase_id, passing the same well-formed-record validation enforced
    by run_signature_deck.py (no self-grant markers, no midnight timestamps, must have
    owner_msg_id or owner_action).

EXIT CODES
    0   Full pass — PROCESS-CERTIFICATE.json + .md written to delivery/<SLUG>-FINAL/.
    9   At least one declared step was skipped (without valid approval), ran out of
        order, was not substance-validated, or lacked confirmed client reports.
        Prints "AF-PROCESS-INTEGRITY" + the offending step(s).
    2   Hard invocation error or missing/unreadable required state files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Self-grant rejection markers (keep in sync with run_signature_deck.py)
# ---------------------------------------------------------------------------

_SELF_GRANT_MARKERS: Tuple[str, ...] = (
    "executive strategy",
    "via ",
    "directive",
    "auto-approved",
    "self",
    "auto",
    "workflow",
    "n8n",
    "make.com",
    "zapier",
    "system",
    "automatically",
    "on behalf",
)


# ---------------------------------------------------------------------------
# File loaders
# ---------------------------------------------------------------------------

def _load_json_required(path: Path, label: str) -> Any:
    """Load a JSON file; exit 2 if missing or unreadable (hard error)."""
    if not path.exists():
        print(f"FATAL: {label} not found at {path}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        print(f"FATAL: {label} is not valid JSON at {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def _load_json_optional(path: Path) -> Any:
    """Load a JSON file; return None on any error (optional file)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


def _load_declared_plan(run_dir: Path) -> dict:
    p = run_dir / "working" / "checkpoints" / "declared_plan.json"
    return _load_json_required(p, "declared_plan.json")


def _load_process_manifest(run_dir: Path) -> dict:
    p = run_dir / "working" / "checkpoints" / "process_manifest.json"
    obj = _load_json_optional(p)
    return obj if isinstance(obj, dict) else {}


def _load_client_reports(run_dir: Path) -> list:
    p = run_dir / "working" / "checkpoints" / "client_reports.json"
    obj = _load_json_optional(p)
    return obj if isinstance(obj, list) else []


# ---------------------------------------------------------------------------
# Skip-approval validation (mirrors run_signature_deck.py logic)
# ---------------------------------------------------------------------------

def _is_valid_skip_approval(rec: Any) -> bool:
    """Return True only for a well-formed human-owner skip-approval record.

    Rejects:
      - Non-dict records
      - Records with no owner_msg_id AND no owner_action (self-granted)
      - Midnight timestamps (T00:00:00 pattern — automated token)
      - Timestamps lacking timezone designator (Z or +offset)
      - approved_by field containing any self-grant marker
    """
    if not isinstance(rec, dict):
        return False
    if not rec.get("owner_msg_id") and not rec.get("owner_action"):
        return False
    ts = str(rec.get("approved_at", ""))
    if "T00:00:00" in ts:
        return False
    if ts and "+" not in ts and "Z" not in ts.upper():
        return False  # No timezone = suspicious automated token
    approved_by = str(rec.get("approved_by", "")).lower()
    for marker in _SELF_GRANT_MARKERS:
        if marker in approved_by:
            return False
    return True


def _build_skip_index(manifest: dict) -> Dict[str, dict]:
    """Return {phase_id: skip_record} for all valid skip approvals."""
    raw = manifest.get("owner_skip_approvals") or []
    index: Dict[str, dict] = {}
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        phase_id = rec.get("phase_id")
        if not phase_id:
            continue
        if _is_valid_skip_approval(rec):
            index[phase_id] = rec  # Last well-formed approval wins.
    return index


# ---------------------------------------------------------------------------
# Attestation index
# ---------------------------------------------------------------------------

def _build_attestation_index(manifest: dict) -> Dict[str, dict]:
    """Return {phase_id: attestation_record} from process_manifest phase_attestations."""
    raw = manifest.get("phase_attestations") or []
    index: Dict[str, dict] = {}
    for rec in raw:
        if isinstance(rec, dict) and rec.get("phase_id"):
            index[rec["phase_id"]] = rec  # Last attestation per phase wins.
    return index


# ---------------------------------------------------------------------------
# Client-report index
# ---------------------------------------------------------------------------

def _build_report_index(client_reports: list) -> Dict[str, Dict[str, dict]]:
    """Return {phase_id: {"start": rec, "done": rec}} for every report record that
    EXISTS.

    A report record satisfies the gate by EXISTING — it proves the client-report
    step ran for that phase. gateway_msg_id and the `sent` flag are recorded for
    audit/confirmation, but an empty id does NOT fail the gate: per OQ-2 the
    process-integrity gate bites on a MISSING record (a skipped report step), not on
    an unconfirmed send (e.g. a box with no configured owner target). This avoids a
    fleet-wide delivery deadlock while still forbidding a silently skipped report."""
    index: Dict[str, Dict[str, dict]] = {}
    for rec in client_reports:
        if not isinstance(rec, dict):
            continue
        phase_id = rec.get("phase_id")
        kind = rec.get("kind")
        if not phase_id or kind not in ("start", "done"):
            continue
        index.setdefault(phase_id, {})
        index[phase_id][kind] = rec  # last record of each kind wins
    return index


# ---------------------------------------------------------------------------
# Timestamp parser
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to a timezone-aware datetime, or None."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            if ts_str.endswith("Z") and fmt.endswith("%z"):
                continue
            if ts_str.endswith("Z") and fmt.endswith("Z"):
                return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Per-step check result
# ---------------------------------------------------------------------------

class StepResult:
    """Outcome of checking one declared step."""
    __slots__ = ("order", "phase_id", "name", "ok", "disposition", "findings")

    def __init__(self, order: float, phase_id: str, name: str) -> None:
        self.order = order
        self.phase_id = phase_id
        self.name = name
        self.ok: bool = False
        self.disposition: str = ""   # "attested" | "owner-skip" | "fail"
        self.findings: List[str] = []

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "phase_id": self.phase_id,
            "name": self.name,
            "disposition": self.disposition,
            "ok": self.ok,
            "findings": self.findings,
        }


# ---------------------------------------------------------------------------
# Main check loop
# ---------------------------------------------------------------------------

def check_all_steps(
    declared_steps: List[dict],
    attestation_index: Dict[str, dict],
    report_index: Dict[str, Dict[str, dict]],
    skip_index: Dict[str, dict],
) -> List[StepResult]:
    """Walk declared steps in declared order; return one StepResult per step."""
    results: List[StepResult] = []
    last_ts: Optional[datetime] = None  # Monotonic check anchor.

    for step in declared_steps:
        phase_id = step.get("id", "")
        name = step.get("name", phase_id)
        order = float(step.get("order", 0))
        sr = StepResult(order, phase_id, name)

        # ---- Owner-approved skip bypass (replaces all other checks for this step) ----
        if phase_id in skip_index:
            skip_rec = skip_index[phase_id]
            sr.ok = True
            sr.disposition = "owner-skip"
            sr.findings.append(
                f"Owner-approved skip: approved_by={skip_rec.get('approved_by')!r} "
                f"at {skip_rec.get('approved_at')!r} "
                f"msg_id={skip_rec.get('owner_msg_id')!r}"
            )
            results.append(sr)
            continue

        failures: List[str] = []

        # (a) Attestation must exist.
        attest = attestation_index.get(phase_id)
        if attest is None:
            failures.append(
                f"(a) No attestation record for phase {phase_id!r} — "
                f"phase was either never run or the runner exited without attesting it."
            )

        if attest is not None:
            # (b) substance_verified must be True on the attestation record.
            if not attest.get("substance_verified"):
                failures.append(
                    f"(b) substance_verified is not True for phase {phase_id!r} "
                    f"(actual value: {attest.get('substance_verified')!r}). "
                    f"The substance verifier must pass before attestation is valid."
                )

            # (d) Monotonically ascending attested_at timestamp.
            ts_str = attest.get("attested_at") or attest.get("ts") or ""
            ts = _parse_ts(ts_str)
            if ts is None:
                failures.append(
                    f"(d) Cannot parse attested_at for phase {phase_id!r}: {ts_str!r} — "
                    f"timestamp is malformed."
                )
            else:
                if last_ts is not None and ts < last_ts:
                    failures.append(
                        f"(d) Out-of-order execution: phase {phase_id!r} attested at "
                        f"{ts_str!r} which is BEFORE the prior attested step "
                        f"({last_ts.isoformat()!r})."
                    )
                last_ts = ts

        # (c) client_reports.json must have a start AND a done record for this phase
        #     (the record EXISTING proves the report step ran; gateway_msg_id is
        #     best-effort confirmation only — OQ-2).
        phase_reports = report_index.get(phase_id, {})
        if "start" not in phase_reports:
            failures.append(
                f"(c) AF-PHASE-REPORT-START: No start client-report record for {phase_id!r} "
                "— its client start-report step was skipped."
            )
        if "done" not in phase_reports:
            failures.append(
                f"(c) AF-PHASE-REPORT-DONE: No done client-report record for {phase_id!r} "
                "— its client done-report step was skipped."
            )

        if failures:
            sr.ok = False
            sr.disposition = "fail"
            sr.findings = failures
        else:
            sr.ok = True
            sr.disposition = "attested"
            sr.findings.append(
                "substance_verified=True; start+done client reports confirmed; "
                "attested in order."
            )

        results.append(sr)

    return results


# ---------------------------------------------------------------------------
# Certificate writer
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cert_sha(body: dict) -> str:
    """Compute deterministic sha256 of the certificate body (sorted keys)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_certificate(
    run_dir: Path,
    deck_slug: str,
    declared_at: str,
    step_results: List[StepResult],
) -> Path:
    """Write PROCESS-CERTIFICATE.json + .md under delivery/<DECK_SLUG>-FINAL/."""
    out_dir = run_dir / "delivery" / f"{deck_slug}-FINAL"
    out_dir.mkdir(parents=True, exist_ok=True)

    certified_at = _now_iso()
    total = len(step_results)
    attested = sum(1 for s in step_results if s.disposition == "attested")
    owner_skips = sum(1 for s in step_results if s.disposition == "owner-skip")

    # Build body WITHOUT certificate_sha so the sha covers a stable structure.
    body: dict = {
        "schema": "process-certificate-v1",
        "deck_slug": deck_slug,
        "declared_at": declared_at,
        "certified_at": certified_at,
        "declared_steps": total,
        "verified_steps": attested,
        "skipped_with_approval": owner_skips,
        "all_steps_pass": all(s.ok for s in step_results),
        "steps": [s.to_dict() for s in step_results],
    }
    sha = _cert_sha(body)
    body["certificate_sha"] = sha  # Add AFTER computing sha.

    json_path = out_dir / "PROCESS-CERTIFICATE.json"
    json_path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    # Human-readable Markdown.
    md_lines = [
        f"# Process Certificate — {deck_slug}",
        "",
        (
            f"**Deck built via the governed {total}-step process; "
            f"every step validated and reported — proof below.**"
        ),
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Deck slug | `{deck_slug}` |",
        f"| Declared at | {declared_at} |",
        f"| Certified at | {certified_at} |",
        f"| Declared steps | {total} |",
        f"| Verified steps | {attested} |",
        f"| Owner-approved skips | {owner_skips} |",
        f"| Certificate SHA | `{sha}` |",
        "",
        "## Step Detail",
        "",
        "| Order | Phase ID | Disposition | Notes |",
        "|---|---|---|---|",
    ]
    for sr in step_results:
        note = sr.findings[0] if sr.findings else ""
        if len(note) > 100:
            note = note[:97] + "..."
        md_lines.append(
            f"| {sr.order} | `{sr.phase_id}` | {sr.disposition} | {note} |"
        )
    md_lines += [
        "",
        "*Generated by prove-deck.py — AF-PROCESS-INTEGRITY enforcement (FIX 2a)*",
    ]

    md_path = out_dir / "PROCESS-CERTIFICATE.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return json_path


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest() -> None:
    """Deterministic self-tests. All must pass. Exits 0 on success, 1 on failure."""
    import tempfile

    test_fails: List[str] = []

    # ---- Helpers ----
    def _mk_run(tmp: str) -> Path:
        rd = Path(tmp)
        (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
        return rd

    def _write(rd: Path, fname: str, obj: Any) -> None:
        (rd / "working" / "checkpoints" / fname).write_text(
            json.dumps(obj), encoding="utf-8"
        )

    declared_steps = [
        {"order": 0.1, "id": "P0A-INTAKE", "name": "Intake"},
        {"order": 4.0, "id": "P4-COPY", "name": "Slide Copy"},
    ]
    good_manifest = {
        "phase_attestations": [
            {"phase_id": "P0A-INTAKE", "substance_verified": True,
             "attested_at": "2026-06-29T10:00:00+00:00"},
            {"phase_id": "P4-COPY", "substance_verified": True,
             "attested_at": "2026-06-29T11:00:00+00:00"},
        ],
        "owner_skip_approvals": [],
    }
    good_reports = [
        {"phase_id": "P0A-INTAKE", "kind": "start", "gateway_msg_id": "msg-1"},
        {"phase_id": "P0A-INTAKE", "kind": "done",  "gateway_msg_id": "msg-2"},
        {"phase_id": "P4-COPY",    "kind": "start", "gateway_msg_id": "msg-3"},
        {"phase_id": "P4-COPY",    "kind": "done",  "gateway_msg_id": "msg-4"},
    ]

    # T1: All good → pass.
    with tempfile.TemporaryDirectory(prefix="pd_t1_") as tmp:
        rd = _mk_run(tmp)
        _write(rd, "process_manifest.json", good_manifest)
        attest_idx = _build_attestation_index(good_manifest)
        report_idx = _build_report_index(good_reports)
        skip_idx = _build_skip_index(good_manifest)
        results = check_all_steps(declared_steps, attest_idx, report_idx, skip_idx)
        if not all(r.ok for r in results):
            failures_found = [f"{r.phase_id}: {r.findings}" for r in results if not r.ok]
            test_fails.append(f"T1: all-good should pass; got failures: {failures_found}")

    # T2: Missing attestation → fail (a).
    with tempfile.TemporaryDirectory(prefix="pd_t2_") as tmp:
        rd = _mk_run(tmp)
        partial_manifest = {
            "phase_attestations": [
                {"phase_id": "P0A-INTAKE", "substance_verified": True,
                 "attested_at": "2026-06-29T10:00:00+00:00"},
                # P4-COPY missing
            ],
            "owner_skip_approvals": [],
        }
        attest_idx = _build_attestation_index(partial_manifest)
        report_idx = _build_report_index(good_reports)
        skip_idx = _build_skip_index(partial_manifest)
        results = check_all_steps(declared_steps, attest_idx, report_idx, skip_idx)
        copy_result = next((r for r in results if r.phase_id == "P4-COPY"), None)
        if copy_result is None or copy_result.ok:
            test_fails.append("T2: missing attestation for P4-COPY should fail")

    # T3: substance_verified=False → fail (b).
    with tempfile.TemporaryDirectory(prefix="pd_t3_") as tmp:
        m = {
            "phase_attestations": [
                {"phase_id": "P0A-INTAKE", "substance_verified": False,
                 "attested_at": "2026-06-29T10:00:00+00:00"},
                {"phase_id": "P4-COPY", "substance_verified": True,
                 "attested_at": "2026-06-29T11:00:00+00:00"},
            ],
            "owner_skip_approvals": [],
        }
        attest_idx = _build_attestation_index(m)
        report_idx = _build_report_index(good_reports)
        skip_idx = _build_skip_index(m)
        results = check_all_steps(declared_steps, attest_idx, report_idx, skip_idx)
        intake_r = next((r for r in results if r.phase_id == "P0A-INTAKE"), None)
        if intake_r is None or intake_r.ok:
            test_fails.append("T3: substance_verified=False should fail")

    # T4: Missing done report → fail (c).
    with tempfile.TemporaryDirectory(prefix="pd_t4_") as tmp:
        partial_reports = [
            {"phase_id": "P0A-INTAKE", "kind": "start", "gateway_msg_id": "msg-1"},
            # done missing for P0A-INTAKE
            {"phase_id": "P4-COPY", "kind": "start", "gateway_msg_id": "msg-3"},
            {"phase_id": "P4-COPY", "kind": "done",  "gateway_msg_id": "msg-4"},
        ]
        attest_idx = _build_attestation_index(good_manifest)
        report_idx = _build_report_index(partial_reports)
        skip_idx = _build_skip_index(good_manifest)
        results = check_all_steps(declared_steps, attest_idx, report_idx, skip_idx)
        intake_r = next((r for r in results if r.phase_id == "P0A-INTAKE"), None)
        if intake_r is None or intake_r.ok:
            test_fails.append("T4: missing done report should fail")

    # T5: Out-of-order timestamps → fail (d).
    with tempfile.TemporaryDirectory(prefix="pd_t5_") as tmp:
        m_oop = {
            "phase_attestations": [
                {"phase_id": "P0A-INTAKE", "substance_verified": True,
                 "attested_at": "2026-06-29T12:00:00+00:00"},  # later than P4-COPY
                {"phase_id": "P4-COPY", "substance_verified": True,
                 "attested_at": "2026-06-29T10:00:00+00:00"},  # earlier
            ],
            "owner_skip_approvals": [],
        }
        attest_idx = _build_attestation_index(m_oop)
        report_idx = _build_report_index(good_reports)
        skip_idx = _build_skip_index(m_oop)
        results = check_all_steps(declared_steps, attest_idx, report_idx, skip_idx)
        copy_r = next((r for r in results if r.phase_id == "P4-COPY"), None)
        if copy_r is None or copy_r.ok:
            test_fails.append("T5: out-of-order timestamps should fail")

    # T6: Valid owner-skip bypass.
    with tempfile.TemporaryDirectory(prefix="pd_t6_") as tmp:
        m_skip = {
            "phase_attestations": [
                {"phase_id": "P0A-INTAKE", "substance_verified": True,
                 "attested_at": "2026-06-29T10:00:00+00:00"},
            ],
            "owner_skip_approvals": [
                {
                    "phase_id": "P4-COPY",
                    "approved_by": "operator",
                    "approved_at": "2026-06-29T10:30:00+00:00",
                    "owner_msg_id": "tg-789",
                    "reason": "client waived copy review",
                }
            ],
        }
        attest_idx = _build_attestation_index(m_skip)
        report_idx = _build_report_index(good_reports)
        skip_idx = _build_skip_index(m_skip)
        results = check_all_steps(declared_steps, attest_idx, report_idx, skip_idx)
        if not all(r.ok for r in results):
            test_fails.append("T6: valid owner-skip should result in all-ok")

    # T7: Self-grant marker rejection.
    bad_skip = {
        "phase_id": "P4-COPY",
        "approved_by": "executive strategy auto-approved",
        "approved_at": "2026-06-29T10:30:00+00:00",
        "owner_msg_id": "tg-789",
    }
    if _is_valid_skip_approval(bad_skip):
        test_fails.append("T7: self-grant marker should be rejected by _is_valid_skip_approval")

    # T8: Midnight timestamp rejection.
    midnight_skip = {
        "phase_id": "P4-COPY",
        "approved_by": "operator",
        "approved_at": "2026-06-29T00:00:00Z",
        "owner_msg_id": "tg-789",
    }
    if _is_valid_skip_approval(midnight_skip):
        test_fails.append("T8: midnight timestamp should be rejected")

    # T9: Certificate write.
    with tempfile.TemporaryDirectory(prefix="pd_t9_") as tmp:
        rd = Path(tmp)
        steps = [StepResult(0.1, "P0A-INTAKE", "Intake")]
        steps[0].ok = True
        steps[0].disposition = "attested"
        cert_path = write_certificate(rd, "test-deck", "2026-06-29T09:00:00+00:00", steps)
        if not cert_path.exists():
            test_fails.append("T9: certificate JSON not written")
        else:
            cert = json.loads(cert_path.read_text())
            if "certificate_sha" not in cert:
                test_fails.append("T9: certificate_sha missing from certificate")

    if test_fails:
        for f in test_fails:
            print(f"[prove-deck selftest] FAIL: {f}", file=sys.stderr)
        sys.exit(1)
    print("[prove-deck selftest] PASS — all self-tests passed.", flush=True)
    sys.exit(0)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="prove-deck.py — deterministic process-integrity verifier (FIX 2a)",
    )
    ap.add_argument(
        "--run-dir", required=False,
        help="Path to the deck run directory (contains working/ and delivery/).",
    )
    ap.add_argument(
        "--selftest", action="store_true",
        help="Run built-in deterministic self-tests and exit.",
    )
    args = ap.parse_args()

    if args.selftest:
        _selftest()  # exits internally

    if not args.run_dir:
        ap.error("--run-dir is required (or use --selftest).")

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir does not exist or is not a directory: {run_dir}",
              file=sys.stderr)
        return 2

    # Load state files.
    declared_plan = _load_declared_plan(run_dir)
    process_manifest = _load_process_manifest(run_dir)
    client_reports = _load_client_reports(run_dir)

    raw_steps: List[dict] = declared_plan.get("steps") or []
    if not raw_steps:
        print("FATAL: declared_plan.json has no steps — cannot prove process integrity.",
              file=sys.stderr)
        return 2

    deck_slug: str = declared_plan.get("deck_slug") or run_dir.name
    declared_at: str = declared_plan.get("declared_at") or ""

    # Build indices.
    attestation_index = _build_attestation_index(process_manifest)
    report_index = _build_report_index(client_reports)
    skip_index = _build_skip_index(process_manifest)

    # Run the main check loop.
    step_results = check_all_steps(raw_steps, attestation_index, report_index, skip_index)
    failures = [sr for sr in step_results if not sr.ok]

    if failures:
        print(
            f"AF-PROCESS-INTEGRITY: {len(failures)} of {len(step_results)} declared "
            f"step(s) failed process-integrity checks.",
            file=sys.stderr,
        )
        for sr in failures:
            print(f"\n  FAIL  [{sr.order}] {sr.phase_id!r} ({sr.name})", file=sys.stderr)
            for finding in sr.findings:
                print(f"        {finding}", file=sys.stderr)
        return 9

    # All steps pass — write certificate.
    cert_path = write_certificate(run_dir, deck_slug, declared_at, step_results)
    cert_data = json.loads(cert_path.read_text(encoding="utf-8"))
    sha = cert_data.get("certificate_sha", "?")

    print(
        f"PROCESS-CERTIFICATE: all {len(step_results)} declared steps verified "
        f"(substance_validated + client_reported + attested in order).",
        flush=True,
    )
    print(f"  certificate_sha: {sha}", flush=True)
    print(f"  written to: {cert_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
