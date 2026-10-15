"""Approval gate evaluator for Skill 72 Motion Graphics V2 (MG-025).

The Python mirror of the TypeScript trusted gate evaluator
(runtime/src/orchestrator/gate.ts). Both evaluators implement the same
rules and must agree on every job:

- A job revision is a deterministic fingerprint over nine components
  (manifest, source bundle, design, data, assets, resolved fonts,
  timeline plus its MG-021 sidecar, narration record, runtime
  identity). Component digests hash canonical UTF-8 JSON over sorted
  {path, sha256} pairs of raw file bytes, so the two implementations
  produce identical digests. The design revision covers the
  art-direction components (design, assets, fonts); the full revision
  covers all nine, so any material change stales preview and delivery
  approvals by construction (Directive Section 16.7).
- An approval counts only when it binds this job and company, names
  the current revision for its scope (design approvals bind the
  design revision; preview and delivery approvals bind the full
  revision), and was issued through the trusted path: its actor is a
  recognized issuer in a registry held OUTSIDE the job package
  (MOTION_ISSUER_REGISTRY), and its source event is a detached event
  artifact in the job package whose exact hash the approval binds in
  artifact_refs and whose HMAC-SHA256 signature verifies under the
  issuer's key from the keyring (MOTION_APPROVER_KEYS). The built-in
  defaults recognize only the fixture test issuer, so production
  authority on an unconfigured installation reports
  MG_APPROVAL_AUTHORITY_UNAVAILABLE instead of trusting job JSON.
- The delivery gate is the promotion check: production context only,
  current preview and delivery approvals, a passing final-QC record,
  and the delivery approval naming the final artifact at its actual
  on-disk hash. Fixture renders are diagnostic and can never be
  promoted as client-ready.

The catalog consult (MG-018 registry) is enforced by the TypeScript
evaluator and the dispatcher; this Python evaluator mirrors the
revision and approval layers and reports the contracts layer through
motion_contracts.validate_job.

CLI:
    python3 scripts/check_approvals.py check <job_dir> --gate render \
        --runtime runtime.json [--registry r.json] [--keyring k.json]
    python3 scripts/check_approvals.py check <job_dir> --gate delivery \
        --runtime runtime.json --final-artifact renders/final.mp4 \
        --qc qc/final-qc.json

Prints one JSON report to stdout and exits with the report's exit_code
(Section 16.9 classes: 0 pass, 2 contract, 3 dependency, 4 approval,
6 QC, 9 security).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac as hmac_module
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motion_contracts  # noqa: E402

SCHEMA_INVALID = motion_contracts.SCHEMA_INVALID
UNKNOWN_COMPONENT = "MG_UNKNOWN_COMPONENT"
MODE_MISMATCH = "MG_MODE_MISMATCH"
TIMELINE_INVALID = "MG_TIMELINE_INVALID"
INPUT_MISSING = "MG_INPUT_MISSING"
CAPABILITY_UNSUPPORTED = "MG_CAPABILITY_UNSUPPORTED"
RUNTIME_UNAVAILABLE = "MG_RUNTIME_UNAVAILABLE"
APPROVAL_REQUIRED = "MG_APPROVAL_REQUIRED"
APPROVAL_STALE = "MG_APPROVAL_STALE"
APPROVAL_AUTHORITY_UNAVAILABLE = "MG_APPROVAL_AUTHORITY_UNAVAILABLE"
QC_FAILED = "MG_QC_FAILED"
HASH_MISMATCH = "MG_HASH_MISMATCH"
FOREIGN_JOB = "MG_FOREIGN_JOB"
SECURITY_VIOLATION = "MG_SECURITY_VIOLATION"

CATEGORY_ORDER = [
    FOREIGN_JOB,
    HASH_MISMATCH,
    SECURITY_VIOLATION,
    SCHEMA_INVALID,
    UNKNOWN_COMPONENT,
    MODE_MISMATCH,
    TIMELINE_INVALID,
    INPUT_MISSING,
    CAPABILITY_UNSUPPORTED,
    RUNTIME_UNAVAILABLE,
    APPROVAL_REQUIRED,
    APPROVAL_STALE,
    APPROVAL_AUTHORITY_UNAVAILABLE,
    QC_FAILED,
]
EXIT_BY_CATEGORY = {
    FOREIGN_JOB: 9,
    HASH_MISMATCH: 9,
    SECURITY_VIOLATION: 9,
    SCHEMA_INVALID: 2,
    UNKNOWN_COMPONENT: 2,
    MODE_MISMATCH: 2,
    TIMELINE_INVALID: 2,
    INPUT_MISSING: 3,
    CAPABILITY_UNSUPPORTED: 3,
    RUNTIME_UNAVAILABLE: 3,
    APPROVAL_REQUIRED: 4,
    APPROVAL_STALE: 4,
    APPROVAL_AUTHORITY_UNAVAILABLE: 4,
    QC_FAILED: 6,
}
GATE_PHASES = {"design": "DESIGN_APPROVED", "render": "PREVIEW_APPROVED", "delivery": "FINAL_QC_PASSED"}

FIXTURE_TEST_ISSUER = "fixture-test-issuer"
FIXTURE_TEST_KEY = "fixture-test-key-not-a-secret"
POLICY_FIXTURE_ONLY = "fixture_only"
POLICY_PRODUCTION = "owner_or_existing_authorized_reviewer"
DEFAULT_REGISTRY = [
    {"actor_id": FIXTURE_TEST_ISSUER, "role": "test", "policies": [POLICY_FIXTURE_ONLY]}
]
DEFAULT_KEYRING = {FIXTURE_TEST_ISSUER: FIXTURE_TEST_KEY}

COMPONENT_NAMES = [
    "manifest", "source", "design", "data", "assets", "fonts",
    "timeline", "narration", "runtime",
]


def _finding(category: str, path: str, message: str) -> dict:
    return {"category": category, "path": path, "message": message}


# ---------------------------------------------------------------------------
# Canonical JSON (mirrors runtime/src/orchestrator/canonical.ts exactly)
# ---------------------------------------------------------------------------

def _expand_exponent(text: str) -> str:
    if "e" not in text and "E" not in text:
        return text
    mantissa, _, exp_text = text.replace("E", "e").partition("e")
    exponent = int(exp_text)
    negative = mantissa.startswith("-")
    unsigned = mantissa[1:] if negative else mantissa
    if "." in unsigned:
        int_part, frac_part = unsigned.split(".", 1)
    else:
        int_part, frac_part = unsigned, ""
    digits = int_part + frac_part
    point = len(int_part) + exponent
    if point <= 0:
        out = "0." + "0" * (-point) + digits
    elif point >= len(digits):
        out = digits + "0" * (point - len(digits))
    else:
        out = digits[:point] + "." + digits[point:]
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return ("-" if negative else "") + out


def _canonical_number(value) -> str:
    if isinstance(value, bool):
        raise ValueError("booleans are not numbers in canonical JSON")
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        raise ValueError(f"canonical JSON cannot carry a non-finite number: {value}")
    if value == int(value) and abs(value) <= 9007199254740991:
        return str(int(value))
    return _expand_exponent(repr(value))


def canonical_json(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(entry) for entry in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        return "{" + ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + canonical_json(value[key]) for key in keys
        ) + "}"
    raise ValueError(f"canonical JSON cannot carry a value of type {type(value)}")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text, parse_constant=motion_contracts._reject_constant)


# ---------------------------------------------------------------------------
# Revision fingerprint (mirrors runtime/src/orchestrator/revision.ts)
# ---------------------------------------------------------------------------

def _component_digest(name: str, entries: list[dict]) -> str:
    ordered = sorted(entries, key=lambda e: e["path"])
    return _sha256_text(canonical_json({"component": name, "entries": ordered}))


def _combined_digest(kind: str, parts: dict) -> str | None:
    normalized = {}
    for name in sorted(parts.keys()):
        if parts[name] is None:
            return None
        normalized[name] = parts[name]
    return _sha256_text(canonical_json({"component": kind, "parts": normalized}))


def compute_revision_lock(job_dir, runtime) -> dict:
    job_dir = Path(job_dir).resolve()
    problems: list[dict] = []

    def file_entry(rel: str, required: bool) -> dict:
        abs_path = (job_dir / rel).resolve()
        if abs_path != job_dir and job_dir not in abs_path.parents:
            problems.append(_finding(SCHEMA_INVALID, rel, f"Path {rel} escapes the job directory; it cannot enter a revision fingerprint."))
            return {"path": rel, "sha256": None}
        if not abs_path.is_file():
            if required:
                problems.append(_finding(INPUT_MISSING, rel, f"Revision input {rel} is missing."))
            return {"path": rel, "sha256": None}
        return {"path": rel, "sha256": _sha256_file(abs_path)}

    def read_json(rel: str):
        abs_path = job_dir / rel
        if not abs_path.is_file():
            return None
        try:
            doc = _load_json(abs_path)
        except (ValueError, OSError):
            return None
        return doc if isinstance(doc, dict) else None

    manifest = read_json("manifest.json") or {}
    job_id = manifest.get("job_id")
    company_id = manifest.get("company_id")

    def ref(field: str, fallback: str) -> str:
        value = manifest.get(field)
        return value if isinstance(value, str) and value else fallback

    components: dict[str, dict] = {}

    def finish(name: str, entries: list[dict]) -> dict:
        record = {"digest": _component_digest(name, entries), "entries": entries}
        components[name] = record
        return record

    finish("manifest", [file_entry("manifest.json", True)])

    scene_specs = []
    scenes = manifest.get("scenes")
    if isinstance(scenes, list):
        for scene in scenes:
            if isinstance(scene, dict) and isinstance(scene.get("spec"), str):
                scene_specs.append(scene["spec"])
    source_paths = sorted({ref("storyboard", "storyboard.json"), *scene_specs})
    finish("source", [file_entry(rel, True) for rel in source_paths])

    finish("design", [file_entry(ref("design", "design.json"), True)])

    data_paths = set()
    data_dir = job_dir / "data"
    if data_dir.is_dir():
        for path in sorted(data_dir.rglob("*")):
            if path.is_file():
                data_paths.add(path.relative_to(job_dir).as_posix())
    for spec in scene_specs:
        scene_doc = read_json(spec)
        if scene_doc and isinstance(scene_doc.get("data_path"), str):
            data_paths.add(scene_doc["data_path"])
    finish("data", [file_entry(rel, True) for rel in sorted(data_paths)])

    assets_rel = ref("assets", "assets.json")
    assets_doc = read_json(assets_rel)
    asset_entries = [file_entry(assets_rel, True)]
    if assets_doc and isinstance(assets_doc.get("assets"), list):
        for asset in assets_doc["assets"]:
            if not isinstance(asset, dict) or not isinstance(asset.get("path"), str):
                continue
            entry = file_entry(asset["path"], True)
            declared = asset.get("sha256")
            if entry["sha256"] is not None and isinstance(declared, str) and declared != entry["sha256"]:
                problems.append(_finding(
                    HASH_MISMATCH, asset["path"],
                    f"Asset {asset['path']} declares sha256 {declared} in {assets_rel} but its bytes "
                    f"hash to {entry['sha256']}; the assets record does not describe the asset on disk.",
                ))
            asset_entries.append(entry)
    finish("assets", asset_entries)

    font_entries = []
    if assets_doc and isinstance(assets_doc.get("font_requirements"), list):
        for requirement in assets_doc["font_requirements"]:
            if not isinstance(requirement, dict):
                continue
            fid = requirement.get("id") if isinstance(requirement.get("id"), str) else "font"
            font_entries.append({"path": f"font:{fid}", "sha256": _sha256_text(canonical_json(requirement))})
    finish("fonts", font_entries)

    timeline_rel = ref("timeline", "timeline.json")
    if (job_dir / "timeline-sidecar.json").is_file():
        sidecar_entry = file_entry("timeline-sidecar.json", True)
    else:
        sidecar_entry = {"path": "timeline-sidecar.json", "sha256": None}
    finish("timeline", [file_entry(timeline_rel, True), sidecar_entry])

    if (job_dir / "narration.json").is_file():
        finish("narration", [file_entry("narration.json", True)])
    else:
        finish("narration", [])

    if runtime is not None:
        runtime_record = {
            "engine": runtime.get("engine"),
            "engineVersion": runtime.get("engineVersion"),
            "runtimeLockId": runtime.get("runtimeLockId"),
        }
        finish("runtime", [{"path": "runtime", "sha256": _sha256_text(canonical_json(runtime_record))}])
    else:
        components["runtime"] = {"digest": None, "entries": []}

    design_revision = _combined_digest("design-revision", {
        "assets": components["assets"]["digest"],
        "design": components["design"]["digest"],
        "fonts": components["fonts"]["digest"],
    })
    full_revision = _combined_digest("full-revision", {
        name: components[name]["digest"] for name in COMPONENT_NAMES
    })
    return {
        "job_id": job_id,
        "company_id": company_id,
        "components": components,
        "design_revision": design_revision,
        "full_revision": full_revision,
        "runtime": runtime,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# Issuer trust (mirrors runtime/src/orchestrator/issuers.ts)
# ---------------------------------------------------------------------------

def load_trust(registry_path=None, keyring_path=None) -> dict:
    registry = DEFAULT_REGISTRY
    registry_source = "built-in fixture-only defaults"
    path = registry_path or os.environ.get("MOTION_ISSUER_REGISTRY")
    if path and Path(path).is_file():
        try:
            parsed = _load_json(Path(path))
            if isinstance(parsed, list):
                entries = []
                for entry in parsed:
                    if (
                        isinstance(entry, dict)
                        and isinstance(entry.get("actor_id"), str)
                        and entry.get("role") in ("owner", "authorized_reviewer", "test")
                        and isinstance(entry.get("policies"), list)
                    ):
                        entries.append({
                            "actor_id": entry["actor_id"],
                            "role": entry["role"],
                            "policies": [p for p in entry["policies"] if isinstance(p, str)],
                        })
                registry = entries
                registry_source = str(path)
        except (ValueError, OSError):
            registry = DEFAULT_REGISTRY
            registry_source = "built-in fixture-only defaults (registry file unreadable)"
    keyring = dict(DEFAULT_KEYRING)
    keyring_source = "built-in fixture test key only"
    path = keyring_path or os.environ.get("MOTION_APPROVER_KEYS")
    if path and Path(path).is_file():
        try:
            parsed = _load_json(Path(path))
            if isinstance(parsed, dict):
                keyring = {k: v for k, v in parsed.items() if isinstance(v, str) and v}
                keyring_source = str(path)
        except (ValueError, OSError):
            keyring = dict(DEFAULT_KEYRING)
            keyring_source = "built-in fixture test key only (keyring file unreadable)"
    return {
        "registry": registry,
        "keyring": keyring,
        "registry_source": registry_source,
        "keyring_source": keyring_source,
    }


def _event_signing_payload(event: dict) -> str:
    return canonical_json({
        "actor_id": event.get("actor_id"),
        "approval_id": event.get("approval_id"),
        "artifact_refs": event.get("artifact_refs"),
        "company_id": event.get("company_id"),
        "decision": event.get("decision"),
        "event_id": event.get("event_id"),
        "job_id": event.get("job_id"),
        "scope": event.get("scope"),
        "subject_revision": event.get("subject_revision"),
    })


def sign_event(event: dict, key: str) -> dict:
    signature = hmac_module.new(
        key.encode("utf-8"), _event_signing_payload(event).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {**event, "signature": signature}


def _verify_event_signature(event: dict, key: str) -> bool:
    expected = hmac_module.new(
        key.encode("utf-8"), _event_signing_payload(event).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac_module.compare_digest(expected, str(event.get("signature") or ""))


# ---------------------------------------------------------------------------
# Gate evaluation (mirrors runtime/src/orchestrator/gate.ts)
# ---------------------------------------------------------------------------

class _Context:
    def __init__(self, job_dir, runtime, trust):
        self.job_dir = Path(job_dir).resolve()
        self.trust = trust
        self.findings: list[dict] = []
        self.manifest = None
        manifest_path = self.job_dir / "manifest.json"
        if not manifest_path.is_file():
            self.findings.append(_finding(INPUT_MISSING, "manifest.json", "Job manifest is missing; no gate can be evaluated."))
        else:
            try:
                parsed = _load_json(manifest_path)
                if isinstance(parsed, dict):
                    self.manifest = parsed
                else:
                    self.findings.append(_finding(SCHEMA_INVALID, "manifest.json", "manifest.json is not a JSON object."))
            except (ValueError, OSError) as exc:
                self.findings.append(_finding(SCHEMA_INVALID, "manifest.json", f"manifest.json is not parseable JSON: {exc}"))
        self.job_id = self.manifest.get("job_id") if self.manifest else None
        self.company_id = self.manifest.get("company_id") if self.manifest else None
        self.execution_context = self.manifest.get("execution_context") if self.manifest else None
        self.approval_policy = self.manifest.get("approval_policy") if self.manifest else None
        self.approvals: list[dict] = []
        approvals_path = self.job_dir / "approvals.json"
        if approvals_path.is_file():
            try:
                parsed = _load_json(approvals_path)
            except (ValueError, OSError) as exc:
                self.findings.append(_finding(SCHEMA_INVALID, "approvals.json", f"approvals.json is not parseable JSON: {exc}"))
                parsed = None
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                for entry in parsed:
                    if not isinstance(entry, dict):
                        self.findings.append(_finding(SCHEMA_INVALID, "approvals.json", "approvals.json contains a non-object entry."))
                        continue
                    for error in motion_contracts.validate_document(entry, "approval"):
                        self.findings.append(_finding(
                            SCHEMA_INVALID, f"approvals.json#{error['path']}",
                            f"Approval {entry.get('approval_id')!r} fails the approval schema: {error['message']}",
                        ))
                    self.approvals.append(entry)
            elif parsed is not None:
                self.findings.append(_finding(SCHEMA_INVALID, "approvals.json", "approvals.json is neither an approval record nor a list of them."))
        self.lock = compute_revision_lock(self.job_dir, runtime)
        self.findings.extend(self.lock["problems"])

    def finish(self, gate: str, approval_id=None, authority_basis=None) -> dict:
        ordered = sorted(self.findings, key=lambda f: CATEGORY_ORDER.index(f["category"]) if f["category"] in CATEGORY_ORDER else len(CATEGORY_ORDER))
        first = ordered[0]["category"] if ordered else None
        blocked = len(ordered) > 0
        return {
            "gate": gate,
            "verdict": "blocked" if blocked else "pass",
            "job_id": self.job_id,
            "company_id": self.company_id,
            "diagnostic": self.execution_context == "fixture",
            "phase": None if blocked else GATE_PHASES[gate],
            "design_revision": self.lock["design_revision"],
            "revision": self.lock["full_revision"],
            "approval_id": approval_id,
            "authority_basis": authority_basis,
            "findings": ordered,
            "first_error_category": first,
            "exit_code": EXIT_BY_CATEGORY.get(first, 2) if blocked else 0,
        }


def _verify_authority(ctx: _Context, approval: dict):
    findings = ctx.findings
    actor = approval.get("actor_id")
    if approval.get("authority_status") != "verified":
        findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "approvals.json", f"Approval {approval.get('approval_id')} claims authority_status {approval.get('authority_status')!r}; only a verified authority can satisfy a gate."))
        return None
    if not isinstance(actor, str) or not actor:
        findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "approvals.json", f"Approval {approval.get('approval_id')} names no actor; its authority cannot be verified."))
        return None
    if ctx.execution_context == "fixture":
        if ctx.approval_policy != POLICY_FIXTURE_ONLY or actor != FIXTURE_TEST_ISSUER:
            findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "approvals.json", f"Fixture jobs run under test-only authority: the single accepted issuer is {FIXTURE_TEST_ISSUER} under the fixture_only policy; got actor {actor} under policy {ctx.approval_policy}."))
            return None
        basis = "fixture_test_issuer"
    elif ctx.execution_context == "production":
        if actor == FIXTURE_TEST_ISSUER:
            findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "approvals.json", "Production jobs reject the fixture test issuer; a real authorized approval event is required."))
            return None
        entry = next((e for e in ctx.trust["registry"] if e["actor_id"] == actor), None)
        if (
            entry is None
            or entry["role"] not in ("owner", "authorized_reviewer")
            or POLICY_PRODUCTION not in entry["policies"]
        ):
            findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "approvals.json", f"Actor {actor} is not a recognized production issuer in the configured registry ({ctx.trust['registry_source']}); the job's policy is owner_or_existing_authorized_reviewer. No trusted approval source is configured for this actor, so the approval cannot be verified."))
            return None
        basis = f"registry:{entry['role']}"
    else:
        findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "manifest.json", f"Execution context {ctx.execution_context!r} has no authority rule in this gate."))
        return None
    key = ctx.trust["keyring"].get(actor)
    if not key:
        findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "approvals.json", f"No verification key is configured for issuer {actor} ({ctx.trust['keyring_source']}); the approval event cannot be authenticated."))
        return None
    ref = approval.get("source_event_ref")
    if not isinstance(ref, str) or not ref:
        findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "approvals.json", f"Approval {approval.get('approval_id')} names no source event; there is no trusted event to verify it against."))
        return None
    event_abs = (ctx.job_dir / ref).resolve()
    if event_abs != ctx.job_dir and ctx.job_dir not in event_abs.parents:
        findings.append(_finding(SECURITY_VIOLATION, ref, f"Approval {approval.get('approval_id')} names a source event outside the job directory: {ref}."))
        return None
    if not event_abs.is_file():
        findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, ref, f"Approval {approval.get('approval_id')} names source event {ref}, which is absent from the job package; its authority cannot be verified."))
        return None
    event_hash = _sha256_file(event_abs)
    bound = next((r for r in approval.get("artifact_refs", []) if isinstance(r, dict) and r.get("path") == ref), None)
    if bound is None:
        findings.append(_finding(SECURITY_VIOLATION, "approvals.json", f"Approval {approval.get('approval_id')} does not bind its source event {ref} in artifact_refs; the event is not part of what was approved."))
        return None
    if bound.get("sha256") != event_hash:
        findings.append(_finding(HASH_MISMATCH, ref, f"Approval {approval.get('approval_id')} binds event {ref} at sha256 {bound.get('sha256')}, but the event on disk hashes to {event_hash}."))
        return None
    try:
        event = _load_json(event_abs)
    except (ValueError, OSError) as exc:
        findings.append(_finding(SCHEMA_INVALID, ref, f"Approval event {ref} is not parseable JSON: {exc}"))
        return None
    if not isinstance(event, dict):
        findings.append(_finding(SCHEMA_INVALID, ref, f"Approval event {ref} is not a JSON object."))
        return None
    mismatches = []
    for field in ("approval_id", "job_id", "company_id", "scope", "decision", "subject_revision", "actor_id"):
        if event.get(field) != approval.get(field):
            mismatches.append(field)
    approval_refs = [r for r in approval.get("artifact_refs", []) if not (isinstance(r, dict) and r.get("path") == ref)]
    if canonical_json(event.get("artifact_refs") or []) != canonical_json(approval_refs):
        mismatches.append("artifact_refs")
    if mismatches:
        findings.append(_finding(SECURITY_VIOLATION, ref, f"Approval event {ref} disagrees with approval {approval.get('approval_id')} on: {', '.join(mismatches)}; the event does not authenticate this record."))
        return None
    if not _verify_event_signature(event, key):
        findings.append(_finding(SECURITY_VIOLATION, ref, f"Approval event {ref} does not verify under the key registered for issuer {actor}; the event is not authentic."))
        return None
    return basis + "+signed_event"


def _select_approval(ctx: _Context, scope: str, expected_revision, revision_label: str):
    findings = ctx.findings
    for approval in ctx.approvals:
        if approval.get("job_id") != ctx.job_id or approval.get("company_id") != ctx.company_id:
            findings.append(_finding(FOREIGN_JOB, "approvals.json", f"Approval {approval.get('approval_id')} is bound to job {approval.get('job_id')} / company {approval.get('company_id')}, not this job {ctx.job_id} / {ctx.company_id}; a foreign approval is never evidence here."))
            return None
    candidates = [a for a in ctx.approvals if a.get("scope") == scope]
    if not candidates:
        findings.append(_finding(APPROVAL_REQUIRED, "approvals.json", f"No {scope}-scope approval is recorded for this job."))
        return None
    approved = [a for a in candidates if a.get("decision") == "approved"]
    if not approved:
        named = candidates[0]
        findings.append(_finding(APPROVAL_REQUIRED, "approvals.json", f"The {scope} approval {named.get('approval_id')} carries decision {named.get('decision')!r}; no {scope} approval is in force."))
        return None
    if expected_revision is None:
        findings.append(_finding(RUNTIME_UNAVAILABLE, "revision", f"The {revision_label} cannot be computed (a revision input is unavailable), so no {scope} approval can be checked against it."))
        return None
    current = next((a for a in approved if a.get("subject_revision") == expected_revision), None)
    if current is None:
        findings.append(_finding(APPROVAL_STALE, "approvals.json", f"No {scope} approval covers the current {revision_label} {expected_revision}; recorded {scope} approvals bind: {', '.join(str(a.get('subject_revision')) for a in approved)}. A material change after approval stales the approval by construction."))
        return None
    basis = _verify_authority(ctx, current)
    if basis is None:
        return None
    return {"approval": current, "authority_basis": basis}


def _narration_findings(ctx: _Context) -> list[dict]:
    if not ctx.manifest:
        return []
    path = ctx.job_dir / "narration.json"
    if not path.is_file():
        return []
    out = []
    try:
        record = _load_json(path)
    except (ValueError, OSError) as exc:
        return [_finding(SCHEMA_INVALID, "narration.json", f"narration.json is not parseable JSON: {exc}")]
    if not isinstance(record, dict):
        return [_finding(SCHEMA_INVALID, "narration.json", "narration.json is not a JSON object.")]
    if record.get("schema_version") != "1.0" or record.get("kind") != "narration_script":
        out.append(_finding(SCHEMA_INVALID, "narration.json", 'narration.json must carry schema_version "1.0" and kind "narration_script".'))
    if record.get("job_id") != ctx.job_id:
        out.append(_finding(SCHEMA_INVALID, "narration.json", f"narration record is bound to job {record.get('job_id')}, not {ctx.job_id}."))
    scene_ids = {s.get("id") for s in ctx.manifest.get("scenes", []) if isinstance(s, dict)}
    scenes = record.get("scenes")
    if not isinstance(scenes, list):
        out.append(_finding(SCHEMA_INVALID, "narration.json", "narration.json scenes must be an array."))
        return out
    seen = set()
    for entry in scenes:
        if not isinstance(entry, dict) or not isinstance(entry.get("scene_id"), str):
            out.append(_finding(SCHEMA_INVALID, "narration.json", "narration scene entry lacks a scene_id."))
            continue
        scene_id = entry["scene_id"]
        if scene_id not in scene_ids:
            out.append(_finding(SCHEMA_INVALID, "narration.json", f"narration names scene {scene_id}, which the manifest does not declare."))
        if scene_id in seen:
            out.append(_finding(SCHEMA_INVALID, "narration.json", f"narration carries scene {scene_id} twice."))
        seen.add(scene_id)
        if not isinstance(entry.get("text"), str) or not entry.get("text"):
            out.append(_finding(SCHEMA_INVALID, "narration.json", f"narration scene {scene_id} carries no text."))
        measured = entry.get("measured")
        if measured is not None:
            ok = (
                isinstance(measured, dict)
                and isinstance(measured.get("start_sample"), int)
                and not isinstance(measured.get("start_sample"), bool)
                and isinstance(measured.get("end_sample"), int)
                and not isinstance(measured.get("end_sample"), bool)
                and 0 <= measured["start_sample"] < measured["end_sample"]
            )
            if not ok:
                out.append(_finding(SCHEMA_INVALID, "narration.json", f"narration scene {scene_id} measured range must be integer samples with 0 <= start < end at the compiled rate."))
    return out


def evaluate_design_gate(job_dir, trust) -> dict:
    ctx = _Context(job_dir, None, trust)
    approval_id = None
    basis = None
    if ctx.manifest and ctx.lock["design_revision"] is not None:
        selected = _select_approval(ctx, "design", ctx.lock["design_revision"], "design revision")
        if selected:
            approval_id = selected["approval"].get("approval_id")
            basis = selected["authority_basis"]
    elif ctx.manifest:
        ctx.findings.append(_finding(INPUT_MISSING, "revision", "The design revision cannot be computed; a design input is missing."))
    return ctx.finish("design", approval_id, basis)


def evaluate_render_gate(job_dir, runtime, trust) -> dict:
    ctx = _Context(job_dir, runtime, trust)
    if runtime is None:
        ctx.findings.append(_finding(RUNTIME_UNAVAILABLE, "revision", "No runtime identity was supplied; the full revision cannot be pinned to a runtime, so no preview approval can satisfy the render gate."))
    if ctx.manifest:
        for finding in motion_contracts.validate_job(ctx.job_dir):
            ctx.findings.append(_finding(finding["category"], finding["path"], finding["message"]))
        ctx.findings.extend(_narration_findings(ctx))
    approval_id = None
    basis = None
    if ctx.manifest and ctx.lock["design_revision"] is not None:
        design = _select_approval(ctx, "design", ctx.lock["design_revision"], "design revision")
        if design:
            basis = design["authority_basis"]
    if ctx.manifest and runtime is not None:
        preview = _select_approval(ctx, "preview", ctx.lock["full_revision"], "full revision")
        if preview:
            approval_id = preview["approval"].get("approval_id")
            basis = preview["authority_basis"]
    return ctx.finish("render", approval_id, basis)


def evaluate_delivery_gate(job_dir, runtime, trust, final_artifact, qc) -> dict:
    ctx = _Context(job_dir, runtime, trust)
    if runtime is None:
        ctx.findings.append(_finding(RUNTIME_UNAVAILABLE, "revision", "No runtime identity was supplied; the delivered revision cannot be pinned to a runtime."))
    if ctx.manifest and ctx.execution_context == "fixture":
        ctx.findings.append(_finding(APPROVAL_AUTHORITY_UNAVAILABLE, "manifest.json", "Fixture jobs run in a diagnostic test context with no production delivery privilege; a fixture render can never be promoted as client-ready."))
    approval_id = None
    basis = None
    delivery_approval = None
    if ctx.manifest and ctx.execution_context == "production" and runtime is not None:
        preview = _select_approval(ctx, "preview", ctx.lock["full_revision"], "full revision")
        if preview:
            basis = preview["authority_basis"]
        delivery = _select_approval(ctx, "delivery", ctx.lock["full_revision"], "full revision")
        if delivery:
            approval_id = delivery["approval"].get("approval_id")
            basis = delivery["authority_basis"]
            delivery_approval = delivery["approval"]
    artifact_path = final_artifact["path"]
    artifact_abs = (ctx.job_dir / artifact_path).resolve()
    if artifact_abs != ctx.job_dir and ctx.job_dir not in artifact_abs.parents:
        ctx.findings.append(_finding(SECURITY_VIOLATION, artifact_path, f"Final artifact path {artifact_path} escapes the job directory."))
    elif not artifact_abs.is_file():
        ctx.findings.append(_finding(INPUT_MISSING, artifact_path, f"Final artifact {artifact_path} is absent; there is nothing to promote."))
    else:
        disk_hash = _sha256_file(artifact_abs)
        if disk_hash != final_artifact["sha256"]:
            ctx.findings.append(_finding(HASH_MISMATCH, artifact_path, f"Final artifact {artifact_path} hashes to {disk_hash} on disk, not the presented {final_artifact['sha256']}."))
        else:
            if delivery_approval is not None:
                bound = next((r for r in delivery_approval.get("artifact_refs", []) if isinstance(r, dict) and r.get("path") == artifact_path), None)
                if bound is None:
                    ctx.findings.append(_finding(APPROVAL_STALE, "approvals.json", f"The delivery approval does not name the final artifact {artifact_path}; it does not cover these bytes."))
                elif bound.get("sha256") != disk_hash:
                    ctx.findings.append(_finding(APPROVAL_STALE, "approvals.json", f"The delivery approval binds {artifact_path} at sha256 {bound.get('sha256')}, but the artifact on disk hashes to {disk_hash}; the render changed after approval."))
            if qc is None:
                ctx.findings.append(_finding(INPUT_MISSING, "qc", "No final-QC record was supplied; delivery requires final QC on the final bytes, not preview QC (Section 16.8)."))
            elif qc.get("artifact_path") != artifact_path or qc.get("artifact_sha256") != disk_hash:
                ctx.findings.append(_finding(QC_FAILED, "qc", f"The final-QC record names {qc.get('artifact_path')} at {qc.get('artifact_sha256')}, not the presented artifact {artifact_path} at {disk_hash}; QC of other bytes is not delivery evidence."))
            elif qc.get("verdict") != "pass":
                ctx.findings.append(_finding(QC_FAILED, "qc", f"Final QC verdict for {artifact_path} is {qc.get('verdict')!r}; a failed final QC cannot be promoted."))
    return ctx.finish("delivery", approval_id, basis)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Skill 72 approval gates (MG-025).")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="Evaluate one gate over one job directory.")
    check.add_argument("job_dir")
    check.add_argument("--gate", choices=["design", "render", "delivery"], default="render")
    check.add_argument("--runtime", help="JSON file: {engine, engineVersion, runtimeLockId}.")
    check.add_argument("--registry", help="Issuer registry JSON path (default: MOTION_ISSUER_REGISTRY or built-in).")
    check.add_argument("--keyring", help="Approver keyring JSON path (default: MOTION_APPROVER_KEYS or built-in).")
    check.add_argument("--final-artifact", help="Job-relative final artifact path (delivery gate).")
    check.add_argument("--qc", help="Final-QC record JSON path (delivery gate).")
    args = parser.parse_args(argv)

    job_dir = Path(args.job_dir)
    if not job_dir.is_dir():
        report = {
            "gate": args.gate, "verdict": "blocked", "job_id": None, "company_id": None,
            "diagnostic": False, "phase": None, "design_revision": None, "revision": None,
            "approval_id": None, "authority_basis": None,
            "findings": [_finding(INPUT_MISSING, args.job_dir, f"job directory {args.job_dir} does not exist")],
            "first_error_category": INPUT_MISSING, "exit_code": 3,
        }
        print(json.dumps(report, indent=2))
        return 3

    runtime = None
    if args.runtime:
        runtime = _load_json(Path(args.runtime))
    trust = load_trust(args.registry, args.keyring)
    if args.gate == "design":
        report = evaluate_design_gate(job_dir, trust)
    elif args.gate == "render":
        report = evaluate_render_gate(job_dir, runtime, trust)
    else:
        if not args.final_artifact:
            parser.error("--gate delivery requires --final-artifact")
        artifact_abs = job_dir / args.final_artifact
        presented = _sha256_file(artifact_abs) if artifact_abs.is_file() else "0" * 64
        qc = _load_json(Path(args.qc)) if args.qc else None
        report = evaluate_delivery_gate(
            job_dir, runtime, trust,
            {"path": args.final_artifact, "sha256": presented}, qc,
        )
    print(json.dumps(report, indent=2))
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
