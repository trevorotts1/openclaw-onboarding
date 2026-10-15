"""MG-037: the Skill 47 side of the desktop VSL handoff.

A Skill 47 production (the parent VSL job) requests a motion
insert from Skill 72, consumes the returned package, and lands it
in the assembled VSL, all through its own manifest conventions:

- The parent job keeps ONE identity: working/job-manifest.json is
  the job's manifest and its delivery ledger. This bridge adds one
  additive key, ``motion_inserts``, whose entries track each
  insert from request to assembly. No existing key is renamed,
  removed, or reinterpreted, and this module does not touch
  executive_producer.py's attestation or board behavior (that
  integration belongs to a separate item); the bridge writes its
  own checkpoint receipts under working/checkpoints/.

- request_insert(run_dir, handoff): validates the handoff through
  the Skill 72 producer (scripts/vsl_handoff.py in
  72-motion-video-plus), checks it names THIS parent job, files
  the handoff of record at working/checkpoints/vsl-handoff.json,
  and records the request in the manifest ledger.

- consume_return(run_dir, return_dir): validates the Skill 72
  return package and recomputes its artifact hashes before the
  insert is accepted into the parent's ledger. A package that
  answers a different handoff or a different parent, or whose
  bytes no longer match its record, is refused by name.

- assemble(run_dir, media_spec): drives the Skill 72 producer's
  parent assembly (the shipped MG-021 compiler plus the shipped
  assembler in plan mode) with the parent's own media package
  (host scenes, narration, music: the parent production owns
  those files), writes the assembled VSL under renders/, files
  the measured assembly report as a checkpoint, and records the
  delivery in the manifest ledger entry.

The Skill 72 scripts directory is resolved from the repository
layout (../../72-motion-video-plus/scripts relative to this file)
or the SKILL72_MOTION_SCRIPTS environment override.

CLI:
    python3 vsl_handoff.py request --run-dir DIR --handoff H.json
    python3 vsl_handoff.py consume --run-dir DIR --return-dir DIR
    python3 vsl_handoff.py assemble --run-dir DIR --media-spec S.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_CONTRACT = 2
EXIT_INPUT = 3
EXIT_QC = 6
EXIT_FOREIGN = 9


class BridgeError(Exception):
    def __init__(self, code, message, mg_category="MG_SCHEMA_INVALID",
                 exit_code=EXIT_CONTRACT):
        super().__init__(message)
        self.code = code
        self.message = message
        self.mg_category = mg_category
        self.exit_code = exit_code

    def document(self):
        return {"status": "FAILED", "code": self.code,
                "mg_category": self.mg_category,
                "exit_code": self.exit_code, "message": self.message}


def _skill72_scripts() -> Path:
    override = os.environ.get("SKILL72_MOTION_SCRIPTS")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "72-motion-video-plus" / "scripts"


def _producer():
    scripts = _skill72_scripts()
    module_path = scripts / "vsl_handoff.py"
    if not module_path.is_file():
        raise BridgeError(
            "VSL_BRIDGE_SKILL72_MISSING",
            "the Skill 72 handoff producer was not found at %s; set "
            "SKILL72_MOTION_SCRIPTS to the 72-motion-video-plus "
            "scripts directory" % module_path,
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "skill72_vsl_handoff", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_path(run_dir: Path) -> Path:
    return run_dir / "working" / "job-manifest.json"


def _load_manifest(run_dir: Path) -> dict:
    path = _manifest_path(run_dir)
    if not path.is_file():
        raise BridgeError(
            "VSL_BRIDGE_PARENT_MANIFEST_MISSING",
            "no parent job manifest at %s; the bridge records "
            "inserts in the parent job's own manifest and never "
            "invents one" % path,
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BridgeError(
            "VSL_BRIDGE_PARENT_MANIFEST_INVALID",
            "parent job manifest %s is not parseable JSON: %s"
            % (path, exc),
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)


def _save_manifest(run_dir: Path, manifest: dict) -> None:
    path = _manifest_path(run_dir)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _entry(manifest: dict, handoff_id: str):
    for entry in manifest.get("motion_inserts") or []:
        if isinstance(entry, dict) and entry.get("handoff_id") == handoff_id:
            return entry
    return None


def _checkpoints(run_dir: Path) -> Path:
    path = run_dir / "working" / "checkpoints"
    path.mkdir(parents=True, exist_ok=True)
    return path


def request_insert(run_dir, handoff_path, parent_job_id=None) -> dict:
    """File a validated handoff as this parent job's request."""
    producer = _producer()
    run_dir = Path(run_dir)
    manifest = _load_manifest(run_dir)
    handoff = producer.load_json(handoff_path, "handoff")
    producer.validate_handoff(handoff)

    named = manifest.get("job_id") or parent_job_id
    if not named:
        raise BridgeError(
            "VSL_BRIDGE_PARENT_IDENTITY_MISSING",
            "the parent job manifest names no job_id and none was "
            "supplied; the bridge never guesses which parent job a "
            "handoff belongs to",
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    if named != handoff["parent"]["job_id"]:
        raise BridgeError(
            "VSL_BRIDGE_PARENT_MISMATCH",
            "handoff %s is addressed to parent job %r, but this run "
            "is parent job %r; a handoff is never filed under the "
            "wrong parent" % (handoff["handoff_id"],
                              handoff["parent"]["job_id"], named),
            mg_category="MG_FOREIGN_JOB", exit_code=EXIT_FOREIGN)

    checkpoints = _checkpoints(run_dir)
    filed = checkpoints / "vsl-handoff.json"
    shutil.copyfile(handoff_path, filed)
    receipt = {
        "schema_version": "1.0",
        "kind": "vsl_insert_request",
        "handoff_id": handoff["handoff_id"],
        "parent_job_id": handoff["parent"]["job_id"],
        "parent_task_id": handoff["parent"]["task_id"],
        "insert_job_id": handoff["insert"]["job_id"],
        "slot": handoff["parent"]["slot"],
        "cue_id": handoff["parent"]["narration_cue"]["id"],
        "status": "requested",
        "requested_at": _now(),
        "handoff_path": "working/checkpoints/vsl-handoff.json",
    }
    (checkpoints / "vsl-request-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    entries = manifest.setdefault("motion_inserts", [])
    entry = _entry(manifest, handoff["handoff_id"])
    if entry is None:
        entry = {"handoff_id": handoff["handoff_id"]}
        entries.append(entry)
    entry.update({
        "insert_job_id": handoff["insert"]["job_id"],
        "parent_job_id": handoff["parent"]["job_id"],
        "status": "requested",
        "handoff": "working/checkpoints/vsl-handoff.json",
        "request_receipt": "working/checkpoints/vsl-request-receipt.json",
    })
    _save_manifest(run_dir, manifest)
    return receipt


def consume_return(run_dir, return_dir) -> dict:
    """Accept a Skill 72 return package into the parent's ledger."""
    producer = _producer()
    run_dir = Path(run_dir)
    return_dir = Path(return_dir)
    manifest = _load_manifest(run_dir)
    checkpoints = _checkpoints(run_dir)
    filed = checkpoints / "vsl-handoff.json"
    if not filed.is_file():
        raise BridgeError(
            "VSL_BRIDGE_HANDOFF_NOT_REQUESTED",
            "no handoff of record at %s; a return is only consumed "
            "against a filed request" % filed,
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    handoff = producer.load_json(filed, "handoff of record")
    doc = producer.load_json(return_dir / "return-package.json",
                             "return package")
    producer.validate_return_package(doc)
    if doc["handoff_id"] != handoff["handoff_id"] \
            or doc["parent_job_id"] != handoff["parent"]["job_id"]:
        raise BridgeError(
            "VSL_BRIDGE_RETURN_FOREIGN",
            "return package answers handoff %r for parent %r; this "
            "run filed handoff %r for parent %r"
            % (doc["handoff_id"], doc["parent_job_id"],
               handoff["handoff_id"], handoff["parent"]["job_id"]),
            mg_category="MG_FOREIGN_JOB", exit_code=EXIT_FOREIGN)
    producer.verify_return_hashes(doc, return_dir)

    receipt = {
        "schema_version": "1.0",
        "kind": "vsl_insert_return",
        "handoff_id": doc["handoff_id"],
        "parent_job_id": doc["parent_job_id"],
        "insert_job_id": doc["insert_job_id"],
        "engine": doc["engine"],
        "artifacts": doc["artifacts"],
        "timing": doc["timing"],
        "approval": doc["approval"],
        "status": "returned",
        "received_at": _now(),
        "return_dir": str(return_dir),
    }
    (checkpoints / "vsl-insert-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    entry = _entry(manifest, doc["handoff_id"])
    if entry is None:
        entry = {"handoff_id": doc["handoff_id"],
                 "insert_job_id": doc["insert_job_id"],
                 "parent_job_id": doc["parent_job_id"]}
        manifest.setdefault("motion_inserts", []).append(entry)
    entry.update({
        "status": "returned",
        "return_dir": str(return_dir),
        "insert_receipt": "working/checkpoints/vsl-insert-receipt.json",
        "artifacts": {
            key: {"path": rec["path"], "sha256": rec["sha256"],
                  "bytes": rec["bytes"]}
            for key, rec in doc["artifacts"].items()
            if isinstance(rec, dict) and "sha256" in rec},
    })
    _save_manifest(run_dir, manifest)
    return receipt


def assemble(run_dir, media_spec_path, out_name="final-vsl.mp4") -> dict:
    """Assemble the parent VSL with the returned insert in its slot
    and record the delivery in the parent's manifest ledger."""
    producer = _producer()
    run_dir = Path(run_dir)
    manifest = _load_manifest(run_dir)
    checkpoints = _checkpoints(run_dir)
    filed = checkpoints / "vsl-handoff.json"
    if not filed.is_file():
        raise BridgeError(
            "VSL_BRIDGE_HANDOFF_NOT_REQUESTED",
            "no handoff of record at %s; assembly follows a filed "
            "request and an accepted return" % filed,
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    handoff = producer.load_json(filed, "handoff of record")
    entry = _entry(manifest, handoff["handoff_id"])
    if entry is None or entry.get("status") not in ("returned", "assembled") \
            or not entry.get("return_dir"):
        raise BridgeError(
            "VSL_BRIDGE_RETURN_NOT_CONSUMED",
            "handoff %s has no consumed return in the parent "
            "ledger; consume the return package before assembly"
            % handoff["handoff_id"],
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)

    out_path = run_dir / "renders" / out_name
    result = producer.assemble_parent(
        filed, entry["return_dir"], media_spec_path, out_path,
        run_dir / "working" / "vsl-assembly")
    report = result["assembly_report"]
    filed_report = checkpoints / "vsl-assembly-report.json"
    shutil.copyfile(result["assembly_report_path"], filed_report)

    if report["verdict"] != "pass":
        entry.update({"status": "assembly_failed",
                      "assembly_report":
                          "working/checkpoints/vsl-assembly-report.json"})
        _save_manifest(run_dir, manifest)
        raise BridgeError(
            "VSL_BRIDGE_ASSEMBLY_QC_FAILED",
            "the assembled VSL failed its measured checks; see %s"
            % filed_report,
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)

    delivery = {
        "assembled_path": "renders/%s" % out_name,
        "sha256": report["assembled"]["sha256"],
        "bytes": report["assembled"]["bytes"],
        "decoded_frames": report["assembled"]["decoded_frames"],
        "duration_seconds": report["assembled"]["duration_seconds"],
        "assembly_report":
            "working/checkpoints/vsl-assembly-report.json",
        "assembled_at": _now(),
    }
    entry.update({"status": "assembled", "delivery": delivery})
    _save_manifest(run_dir, manifest)
    return delivery


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Skill 47 bridge for the desktop VSL handoff (MG-037).")
    sub = parser.add_subparsers(dest="command", required=True)
    p_req = sub.add_parser("request", help="File a handoff as a request.")
    p_req.add_argument("--run-dir", required=True)
    p_req.add_argument("--handoff", required=True)
    p_req.add_argument("--parent-job-id")
    p_con = sub.add_parser("consume", help="Accept a return package.")
    p_con.add_argument("--run-dir", required=True)
    p_con.add_argument("--return-dir", required=True)
    p_asm = sub.add_parser("assemble", help="Assemble the parent VSL.")
    p_asm.add_argument("--run-dir", required=True)
    p_asm.add_argument("--media-spec", required=True)
    p_asm.add_argument("--out-name", default="final-vsl.mp4")
    args = parser.parse_args(argv)

    try:
        if args.command == "request":
            result = request_insert(args.run_dir, args.handoff,
                                    parent_job_id=args.parent_job_id)
        elif args.command == "consume":
            result = consume_return(args.run_dir, args.return_dir)
        else:
            result = assemble(args.run_dir, args.media_spec,
                              out_name=args.out_name)
        print(json.dumps(result, indent=2))
        return EXIT_OK
    except BridgeError as err:
        print(json.dumps(err.document(), indent=2), file=sys.stderr)
        return err.exit_code
    except Exception as err:  # the Skill 72 producer's named errors
        document = getattr(err, "document", None)
        if callable(document):
            print(json.dumps(document(), indent=2), file=sys.stderr)
            return int(getattr(err, "exit_code", EXIT_INTERNAL))
        raise


if __name__ == "__main__":
    sys.exit(main())
