#!/usr/bin/env python3
"""
motion_status.py: Skill 47 side of the MG-046 status integration.

The Skill 72 motion runtime tracks one task identity from intake
through delivery in the job directory (runtime/src/status/):
working/checkpoints/motion-status.json is the current status
document and working/checkpoints/motion-status-events.jsonl is the
append-only stream of structured emissions (phase transitions,
progress, render receipts, review verdicts, production approval
events, recovery points, artifact locations). This bridge is the
transport of record between that ledger and the existing Skill 47
integration:

- ATTESTATION (V01): every status event is appended to
  working/checkpoints/video_process_manifest.json with the same
  record shape and never-clobber discipline as
  executive_producer.attest_phase ({phase_id, owning_role, status,
  checker, note, attested_at}), and under the same
  phase_attestations key attest_phase appends to, so
  executive_producer's own readers (_attestations, feeding
  _attested_phase_ids and the phase precondition checks) see the
  bridge's records. Records an earlier bridge version wrote under
  a "phases" key are history and are never rewritten; the
  bridge-state cursor counts attested events regardless of the
  key they landed under, so those events are never re-appended
  under phase_attestations on a retry. Motion phases never set
  finalized=true: only V-CONTROL does that.
- BOARD (V02): the task's stage is driven through cc_board, the
  fail-soft board transport, walking only the legal transition path
  (never an in_progress to done jump). A standalone motion job
  ensures its own campaign exactly once (the cc-board.created
  marker convention from executive_producer, plus the server's own
  idempotence on job_id). A motion INSERT ensures NOTHING: its
  stage lives on the parent job's campaign, because the component
  returns to its parent presentation or VSL job (the MG-037
  bridge's parent identity, carried in the status document) instead
  of creating an unrelated full production task.

DONE GATING: the bridge refuses to move a stage to done unless the
status document says DELIVERED, its missing_mandatory list is
empty, and the delivery receipt exists with an empty
missing_mandatory of its own. Anything absent blocks Done BY NAME
in the sync report and the stage goes no further than review. The
parent job's own completion gates are untouched: an insert's
DELIVERED means "returned to the parent", never "the parent is
done".

FAIL-SOFT: board problems are reported, never raised; attestation
still lands. Exit codes: 0 = sync completed (board outcome is in
the report), 2 = the status document is not parseable, 3 = the
status document is absent.

CLI:
    python3 scripts/motion_status.py sync RUN_DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cc_board  # noqa: E402  (fail-soft board transport, V02)

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_MISSING = 3

CHECKPOINTS = Path("working") / "checkpoints"
STATUS_DOC = "motion-status.json"
STATUS_EVENTS = "motion-status-events.jsonl"
DELIVERY_RECEIPT = "delivery-receipt.json"
BRIDGE_STATE = "motion-bridge-state.json"
BOARD_MARKER = "cc-board.created"
PROCESS_MANIFEST = "video_process_manifest.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _checkpoints(run_dir: Path) -> Path:
    return Path(run_dir) / CHECKPOINTS


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------
# Attestation (V01): mirror executive_producer.attest_phase's shape,
# discipline, and phase_attestations key against the motion status
# event stream.
# --------------------------------------------------------------------

def _event_phase_id(event: dict) -> str:
    detail = event.get("detail") or {}
    if event.get("kind") == "phase_transition" and detail.get("phase"):
        return "MG-%s" % str(detail["phase"]).upper()
    return "MG-%s" % str(event.get("kind") or "event").upper().replace("_", "-")


def _event_note(event: dict) -> str:
    kind = event.get("kind")
    d = event.get("detail") or {}
    if kind == "phase_transition":
        return "phase transition to %s" % d.get("phase")
    if kind == "render_receipt":
        arts = ", ".join(
            "%s=%s" % (a.get("kind"), a.get("path")) for a in d.get("artifacts") or [])
        return "render receipt (%s): %s" % (d.get("engine"), arts or "no artifacts")
    if kind == "review_verdict":
        return "review verdict %s from %s over %s" % (
            d.get("verdict"), d.get("source"), d.get("artifactPath"))
    if kind == "approval_event":
        return "production approval (%s gate, scope %s, %s, authority %s)" % (
            d.get("gate"), d.get("scope"), d.get("approvalId"), d.get("authorityBasis"))
    if kind == "recovery_point":
        return "recovery point: cache job key %s in %s" % (
            d.get("cacheJobKey"), d.get("cacheWorkDir"))
    if kind == "failure":
        return "failure %s: %s" % (d.get("category"), d.get("message"))
    if kind == "delivery_blocked":
        return "delivery blocked, missing: %s" % ", ".join(d.get("missing") or [])
    if kind == "delivered":
        return "delivered; delivery receipt written"
    if kind == "artifact_location":
        return "artifact %s at %s" % (d.get("kind"), d.get("path"))
    if kind == "progress":
        return "progress update"
    return str(kind)


def attest_events(run_dir: Path, events: list, already: int) -> int:
    """Append every event past index `already` to the process
    manifest, under the same phase_attestations key
    executive_producer.attest_phase appends to (so the parent's
    own readers see the records). Returns the number appended.
    Idempotent across runs: the bridge state remembers how many
    events were attested, so a fail-then-resume cycle never
    duplicates an attestation. The cursor counts events, not
    records under a key, so events an earlier bridge version
    attested under the old "phases" key already count toward
    `already` and are never re-appended under the new key; those
    old records are left untouched as history."""
    new_events = events[already:]
    if not new_events:
        return 0
    manifest_path = _checkpoints(run_dir) / PROCESS_MANIFEST
    doc = {}
    if manifest_path.exists():
        try:
            loaded = _load_json(manifest_path)
            if isinstance(loaded, dict):
                doc = loaded
        except (OSError, ValueError):
            doc = {}
    attestations = doc.get("phase_attestations")
    if not isinstance(attestations, list):
        attestations = []
        doc["phase_attestations"] = attestations
    for event in new_events:
        attestations.append({
            "phase_id": _event_phase_id(event),
            "owning_role": "skill72-motion",
            "status": event.get("productionStatus") or event.get("kind") or "event",
            "checker": "motion_status.py",
            "note": _event_note(event),
            "attested_at": _now(),
        })
    _write_json_atomic(manifest_path, doc)
    return len(new_events)


# --------------------------------------------------------------------
# Board sync (V02)
# --------------------------------------------------------------------

def desired_board_status(doc: dict) -> str | None:
    """The furthest board status the production evidence supports.
    Done is decided by sync_board's gate, not here: DELIVERED maps
    to a done REQUEST that the gate then verifies by name."""
    status = doc.get("productionStatus")
    if status == "DELIVERED":
        return "done"
    if status in ("RENDERED", "QC_PASSED", "APPROVED"):
        return "review"
    if doc.get("phase") not in (None, "CREATED") or status is not None:
        return "in_progress"
    return None


def done_gate(run_dir: Path, doc: dict) -> list:
    """Names of everything that blocks Done. Empty means the stage
    may move to done. Defense in depth at the board: the runtime
    already refused DELIVERED on partial evidence; the board
    re-checks the recorded evidence before claiming done, so a
    hand-edited or partial status document cannot card a task
    complete before its usable deliverables exist."""
    missing = []
    if doc.get("productionStatus") != "DELIVERED":
        missing.append("production_status")
    for name in doc.get("missingMandatory") or []:
        missing.append(str(name))
    receipt_path = _checkpoints(run_dir) / DELIVERY_RECEIPT
    if not receipt_path.exists():
        missing.append("delivery_receipt")
    else:
        try:
            receipt = _load_json(receipt_path)
        except (OSError, ValueError):
            receipt = None
            missing.append("delivery_receipt")
        if isinstance(receipt, dict):
            for name in receipt.get("missing_mandatory") or []:
                missing.append(str(name))
            kinds = {a.get("kind") for a in receipt.get("artifacts") or []
                     if isinstance(a, dict)}
            for kind in ("mp4",):
                if kind not in kinds:
                    missing.append(kind)
    return missing


def sync_board(run_dir: Path, doc: dict, state: dict, env=None) -> dict:
    """Drive the task's board stage from the status document.
    Fail-soft: cc_board never raises, and neither does this. The
    returned report records exactly what was attempted and what the
    board answered."""
    identity = doc.get("identity") or {}
    board_job_id = identity.get("boardJobId") or identity.get("jobId")
    stage_slug = identity.get("stageSlug") or "motion"
    is_insert = identity.get("taskOrigin") == "parent"
    report = {
        "enabled": cc_board.board_config(env) is not None,
        "board_job_id": board_job_id,
        "stage_slug": stage_slug,
        "insert": is_insert,
        "created_campaign": False,
        "campaign_id": state.get("campaign_id"),
        "stage_status": None,
        "done_blocked": [],
        "ok": True,
    }
    if not report["enabled"]:
        report["ok"] = False
        report["stage_status"] = "board disabled (MISSION_CONTROL_URL unset); no-op"
        return report

    campaign_id = state.get("campaign_id")
    if not is_insert:
        marker = _checkpoints(run_dir) / BOARD_MARKER
        if marker.exists():
            campaign_id = marker.read_text(encoding="utf-8").strip() or campaign_id
        if not campaign_id:
            created = cc_board.create_campaign(
                board_job_id,
                str(identity.get("jobId") or board_job_id),
                stages=[{"slug": stage_slug, "title": "Motion production"}],
                department="video",
                agent_id="skill72-motion",
                env=env,
            )
            if created:
                campaign_id = created
                report["created_campaign"] = True
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(str(created), encoding="utf-8")
        report["campaign_id"] = campaign_id
    # An insert never creates a campaign: its stage rides the
    # parent's campaign (board_job_id IS the parent job id).

    desired = desired_board_status(doc)
    if desired == "done":
        blocked = done_gate(run_dir, doc)
        if blocked:
            report["done_blocked"] = blocked
            desired = "review"
    if desired is None:
        report["stage_status"] = "no board move warranted yet"
        return report
    if state.get("stage_status_synced") == desired and not report["done_blocked"]:
        report["stage_status"] = desired
        return report
    ok = cc_board.set_stage_status(
        board_job_id, stage_slug, desired,
        actor="skill72-motion-status", env=env)
    report["ok"] = bool(ok)
    report["stage_status"] = desired if ok else "move to %s not confirmed" % desired
    if ok:
        state["stage_status_synced"] = desired
        if desired == "done":
            receipt_path = _checkpoints(run_dir) / DELIVERY_RECEIPT
            mp4_path = None
            try:
                receipt = _load_json(receipt_path)
                for art in receipt.get("artifacts") or []:
                    if isinstance(art, dict) and art.get("kind") == "mp4":
                        mp4_path = art.get("path")
            except (OSError, ValueError):
                mp4_path = None
            cc_board.stamp_receipt(
                Path(run_dir), campaign_id=campaign_id,
                final_mp4_path=mp4_path)
    return report


# --------------------------------------------------------------------
# Sync entry point
# --------------------------------------------------------------------

def sync(run_dir, env=None) -> tuple:
    """One bridge sync: attest new status events, then drive the
    board. Returns (exit_code, report). Board state persists in
    motion-bridge-state.json so a retry after a failure resumes the
    same task: no duplicate campaign, no duplicate attestation, no
    duplicate stamp."""
    run_dir = Path(run_dir)
    doc_path = _checkpoints(run_dir) / STATUS_DOC
    if not doc_path.exists():
        return EXIT_MISSING, {
            "ok": False,
            "error": "motion status document absent: %s" % doc_path,
        }
    try:
        doc = _load_json(doc_path)
    except (OSError, ValueError) as exc:
        return EXIT_INVALID, {
            "ok": False,
            "error": "motion status document is not parseable JSON: %s" % exc,
        }
    if not isinstance(doc, dict) or not (doc.get("identity") or {}).get("jobId"):
        return EXIT_INVALID, {
            "ok": False,
            "error": "motion status document carries no task identity",
        }

    state_path = _checkpoints(run_dir) / BRIDGE_STATE
    state = {}
    if state_path.exists():
        try:
            loaded = _load_json(state_path)
            if isinstance(loaded, dict):
                state = loaded
        except (OSError, ValueError):
            state = {}

    events = []
    events_path = _checkpoints(run_dir) / STATUS_EVENTS
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)

    report = {
        "ok": True,
        "job_id": (doc.get("identity") or {}).get("jobId"),
        "task_id": (doc.get("identity") or {}).get("taskId"),
        "production_status": doc.get("productionStatus"),
        "attested_new": 0,
        "board": None,
    }
    try:
        already = int(state.get("attested_events") or 0)
        appended = attest_events(run_dir, events, already)
        state["attested_events"] = already + appended
        report["attested_new"] = appended
    except OSError as exc:
        report["ok"] = False
        report["attestation_error"] = str(exc)

    report["board"] = sync_board(run_dir, doc, state, env=env)
    if report["board"].get("campaign_id"):
        state["campaign_id"] = report["board"]["campaign_id"]
    try:
        _write_json_atomic(state_path, state)
    except OSError as exc:
        report["ok"] = False
        report["state_error"] = str(exc)
    return EXIT_OK, report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync a motion job's status ledger to the "
                    "attestation manifest and the Command Center board.")
    sub = parser.add_subparsers(dest="command", required=True)
    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument("run_dir")
    args = parser.parse_args(argv)
    if args.command == "sync":
        code, report = sync(Path(args.run_dir))
        print(json.dumps(report, indent=2))
        return code
    return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
