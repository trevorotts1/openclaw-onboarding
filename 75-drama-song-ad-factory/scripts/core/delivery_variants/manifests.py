"""Deliverable writers: campaign-manifest.json, cost-report.json,
provenance.json. Directives 20.4 + 24.4. Stdlib only.

Hash binding: every artifact file hashed (sha256) into the manifest; the
manifest and cost-report hashes are pinned inside provenance.json.
verify_binding() recomputes and compares. File existence alone is never
acceptance; that gate belongs to delivery_verify.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "1.0.0"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 65536


class ManifestError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path, record):
    data = json.dumps(record, indent=2, sort_keys=True) + "\n"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data, encoding="utf-8")
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _artifact_entry(entry, root):
    item = dict(entry)
    if not item.get("sha256") and item.get("file"):
        base = Path(root) if root else Path.cwd()
        item["sha256"] = sha256_file(base / item["file"])
    if not item.get("artifact_id") or not item.get("path"):
        raise ManifestError("BAD_ARTIFACT", "artifact needs artifact_id and path")
    if not _SHA.match(item.get("sha256") or ""):
        raise ManifestError("BAD_HASH", "artifact %r needs sha256 hex"
                            % item.get("artifact_id"))
    return {"artifact_id": item["artifact_id"],
            "kind": item.get("kind", "video"),
            "path": item["path"],
            "sha256": item["sha256"]}


def write_campaign_manifest(path, *, campaign_id, run_id, artifacts,
                            variants=None, qc_refs=None,
                            profile_version="1.0.0", artifact_root=None):
    """Write campaign-manifest.json binding every artifact hash. Returns
    {"record", "sha256"}; the digest is pinned by provenance.json."""
    if not campaign_id or not run_id:
        raise ManifestError("BAD_ID", "campaign_id and run_id required")
    bound = [_artifact_entry(e, artifact_root) for e in (artifacts or [])]
    if not bound:
        raise ManifestError("NO_ARTIFACTS", "manifest binds at least one artifact")
    record = {"schema_version": SCHEMA_VERSION,
              "campaign_id": campaign_id,
              "run_id": run_id,
              "profile_version": profile_version,
              "created_at": _utcnow(),
              "artifacts": bound,
              "variants": variants or [],
              "qc_refs": qc_refs or []}
    return {"record": record, "sha256": _write_json(path, record)}


def write_cost_report(path, *, run_id, estimated_cost, committed_cost,
                      actual_cost, remaining_budget, currency="USD",
                      reconciled=False):
    """Write cost-report.json. Money is integer minor units, never floats."""
    money = {"estimated_cost": estimated_cost,
             "committed_cost": committed_cost,
             "actual_cost": actual_cost,
             "remaining_budget": remaining_budget}
    for key, value in money.items():
        if not isinstance(value, int) or value < 0:
            raise ManifestError("BAD_MONEY", "%s must be a non-negative int "
                                "(minor units)" % key)
    if not run_id:
        raise ManifestError("BAD_ID", "run_id required")
    record = {"schema_version": SCHEMA_VERSION,
              "run_id": run_id,
              "currency": currency,
              "created_at": _utcnow(),
              "reconciled": bool(reconciled)}
    record.update(money)
    return {"record": record, "sha256": _write_json(path, record)}


def write_provenance(path, *, run_id, campaign_manifest_sha256,
                     cost_report_sha256, artifact_hashes=None,
                     sources=None, reviewer=None):
    """Write provenance.json pinning manifest + cost-report + artifact hashes."""
    for key, value in (("campaign_manifest_sha256", campaign_manifest_sha256),
                       ("cost_report_sha256", cost_report_sha256)):
        if not _SHA.match(value or ""):
            raise ManifestError("BAD_HASH", "%s must be sha256 hex" % key)
    hashes = dict(artifact_hashes or {})
    for artifact_id, digest in hashes.items():
        if not _SHA.match(digest or ""):
            raise ManifestError("BAD_HASH", "artifact %r hash not sha256 hex"
                                % artifact_id)
    if not run_id:
        raise ManifestError("BAD_ID", "run_id required")
    record = {"schema_version": SCHEMA_VERSION,
              "run_id": run_id,
              "created_at": _utcnow(),
              "campaign_manifest_sha256": campaign_manifest_sha256,
              "cost_report_sha256": cost_report_sha256,
              "artifact_hashes": hashes,
              "sources": sources or [],
              "reviewer": reviewer or {}}
    return {"record": record, "sha256": _write_json(path, record)}


def verify_binding(manifest_path, provenance_path, cost_report_path=None,
                   artifact_root=None):
    """Recompute every pinned hash. Returns (ok, details)."""
    details = {"manifest_match": False, "cost_report_match": None,
               "artifacts": {}}
    try:
        manifest_bytes = Path(manifest_path).read_bytes()
        manifest = json.loads(manifest_bytes)
        provenance = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        details["error"] = str(exc)
        return (False, details)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    details["manifest_match"] = (
        manifest_digest == provenance.get("campaign_manifest_sha256"))
    if cost_report_path:
        try:
            report_bytes = Path(cost_report_path).read_bytes()
        except OSError as exc:
            details["error"] = str(exc)
            return (False, details)
        report_digest = hashlib.sha256(report_bytes).hexdigest()
        details["cost_report_match"] = (
            report_digest == provenance.get("cost_report_sha256"))
    base = Path(artifact_root) if artifact_root else Path.cwd()
    for entry in manifest.get("artifacts", []):
        target = base / entry.get("path", "")
        if not target.is_file():
            details["artifacts"][entry.get("artifact_id")] = "missing file"
            continue
        details["artifacts"][entry.get("artifact_id")] = (
            sha256_file(target) == entry.get("sha256"))
    artifact_ok = all(v is True for v in details["artifacts"].values())
    ok = bool(details["manifest_match"] and artifact_ok
              and details["cost_report_match"] is not False)
    details["ok"] = ok
    return (ok, details)
