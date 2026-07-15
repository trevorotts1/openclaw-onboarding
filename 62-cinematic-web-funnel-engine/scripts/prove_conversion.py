#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_conversion.py — the P12-CRM phase gate declared in CWFE-MANIFEST.json
(``"gate": "scripts/prove_conversion.py"``, ``"py_symbol":
"prove_conversion.evaluate"``, ``"af_code": "AF-CWFE-P12-CRM"``; delegate rail
06-ghl-install-pages / 44-convert-and-flow-operator, spec 14.1).

Spec Section 17.6 (conversion gate): "Validate every CTA, form, calendar,
checkout/payment link, workflow/webhook, UTM propagation, success state, and
error state through real E2E tests or approved mocks plus live smoke test."
Spec Section 14.3 (GHL integration receipts): location ID by safe identifier;
form/calendar/widget IDs; workflow/webhook IDs; conversion-event proof; no
secret values.

Like every other ``prove_*.py`` in this skill, this module NEVER trusts the
P12 producer's own ``crm-integration-receipt.json`` as the verdict — it
treats the receipt as EVIDENCE/provenance only and independently re-derives
every pass/fail decision from two sources of ground truth the receipt cannot
forge:

  1. the LOCKED ``content-manifest.json`` (P3) — its ``cta_map`` is parsed
     here with the SAME fail-closed rules ``templates/components/conversion-map.ts``
     applies in the browser (a re-implementation kept in exact parity by
     inspection, mirroring how prove_certificate.py re-implements the
     orchestrator's gate-subprocess contract rather than importing across a
     runtime boundary), and its ``conversion_requirements`` (form/calendar/
     payment) are the authoritative list of what MUST be wired; and
  2. the MATERIALIZED site on disk (P11's ``build-receipt.json`` ->
     ``site_dir``) — the real conversion wiring source files
     (``app/api/conversion-event/route.ts``, ``components/conversion-map.ts``,
     ``lib/conversion-webhook.ts``, ``lib/resolve-ghl-embeds.ts``,
     ``components/useConversionTracking.ts``, ``components/ConversionCtaWiring.tsx``)
     and the generated ``lib/site-data.generated.ts`` whose embedded
     ``ctaMap`` must equal the locked content-manifest's ``cta_map`` byte-
     for-value — proving the receipt describes the ACTUAL deployed site, not
     a fictional one.

A receipt that claims a CTA the locked map does not validly wire, a required
conversion capability with no valid+wired action, a success proof without
propagated UTM, an error-state proof that was not actually a rejection, or a
secret VALUE anywhere in the receipt is rejected fail-closed — no exception.

``crm-integration-status.json`` is written into run_dir on EVERY invocation
(pass or fail), so a rejected P12 attempt still leaves a full evidence trail,
matching every other prove_*.py in this skill (e.g. prove_certificate.py's
certificate-status.json).

CLI
---
  --run-dir DIR   phase-gate mode (uniform CWFE-MANIFEST.json gate contract):
                   evaluate DIR. Exit 0 = PASS, 2 = FAIL, 3 = usage error.
  --self-test      offline, deterministic self-test (builds the fixture site
                   source with --skip-toolchain, synthesizes an approved-mock
                   receipt, proves PASS then several fail-closed paths). No
                   network, no live CRM call (spec 19.2).

stdlib only for orchestration (ADR-5). Reuses this skill's own json_schema_lite,
state_engine.atomic_write_json, build_site.SECRET_PATTERNS (the SAME secret
detector every other receipt/site scan uses — one detector, not a fork), and
resolve_content_engine.verify_locked_manifest.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SCRIPT_DIR / "lib") not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

import json_schema_lite as jsl  # noqa: E402
import state_engine as _state_engine  # noqa: E402  (reuse the one atomic-write implementation)
import build_site as _build_site  # noqa: E402  (reuse SECRET_PATTERNS — one detector, not a fork)
import resolve_content_engine as rce  # noqa: E402  (reuse verify_locked_manifest — never re-implement the lock check)

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

AF_P12 = "AF-CWFE-P12-CRM"
AF_SECRET_LEAK = "AF-CWFE-SECRET-LEAK"

_SCHEMA_PATH = _STRUCTURE_DIR / "crm-integration-receipt.schema.json"

# The conversion-wiring source files the P11 site build must have materialized
# for P12 to be provable. Every one is a REAL file U16 ships in
# templates/nextjs-app + templates/components; a missing one means the
# conversion layer was never wired into this site.
_REQUIRED_SITE_WIRING = [
    "app/api/conversion-event/route.ts",
    "components/conversion-map.ts",
    "components/types.ts",
    "components/useConversionTracking.ts",
    "components/ConversionCtaWiring.tsx",
    "lib/conversion-webhook.ts",
    "lib/resolve-ghl-embeds.ts",
    "lib/site-data.generated.ts",
]

_VALID_KINDS = ("ghl-form-embed", "ghl-webhook", "external-link")
# A CTA that actually delivers a lead into the CRM (spec 17.6 form/calendar/
# workflow/webhook) — as opposed to a plain outbound external-link.
_CRM_KINDS = ("ghl-form-embed", "ghl-webhook")
# The canonical UTM param set the site's useConversionTracking.ts preserves
# (spec 13.3 "UTM preservation").
_UTM_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# cta_map parsing — an EXACT-parity Python re-implementation of
# templates/components/conversion-map.ts::parseConversionMap, so the gate's
# view of "which CTAs are validly wired" can never silently diverge from what
# the browser/server actually accepts at runtime.
# ---------------------------------------------------------------------------
def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def parse_conversion_action(raw: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Returns (action, None) for a valid entry, or (None, reason) for a
    rejected one — never a partially-filled action with an assumed default,
    exactly like conversion-map.ts::parseConversionAction."""
    if not isinstance(raw, dict):
        return None, "entry is not an object"
    kind = raw.get("kind")
    if not _is_non_empty_str(kind) or kind not in _VALID_KINDS:
        return None, f'"kind" must be one of {", ".join(_VALID_KINDS)}'
    if not _is_non_empty_str(raw.get("label")):
        return None, '"label" is required and must be a non-empty string'
    required_fields = raw.get("requiredFields", [])
    if not (isinstance(required_fields, list) and all(isinstance(f, str) for f in required_fields)):
        return None, '"requiredFields" must be an array of strings when present'

    if kind == "ghl-form-embed":
        if not _is_non_empty_str(raw.get("embedUrlEnvVar")):
            return None, 'kind "ghl-form-embed" requires a non-empty "embedUrlEnvVar" (env var NAME, not a URL)'
        return {"kind": kind, "label": raw["label"], "embedUrlEnvVar": raw["embedUrlEnvVar"], "requiredFields": list(required_fields)}, None
    if kind == "ghl-webhook":
        if not _is_non_empty_str(raw.get("webhookEnvVar")):
            return None, 'kind "ghl-webhook" requires a non-empty "webhookEnvVar" (env var NAME, not a URL)'
        return {"kind": kind, "label": raw["label"], "webhookEnvVar": raw["webhookEnvVar"], "requiredFields": list(required_fields)}, None
    # external-link
    if not _is_non_empty_str(raw.get("href")):
        return None, 'kind "external-link" requires a non-empty "href"'
    return {"kind": kind, "label": raw["label"], "href": raw["href"], "requiredFields": list(required_fields)}, None


def parse_conversion_map(raw: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    actions: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}
    for cta_id, raw_action in (raw or {}).items():
        action, reason = parse_conversion_action(raw_action)
        if reason is not None:
            errors[cta_id] = reason
        else:
            actions[cta_id] = action  # type: ignore[assignment]
    return actions, errors


def _action_env_var(action: Dict[str, Any]) -> Optional[str]:
    if action["kind"] == "ghl-form-embed":
        return action.get("embedUrlEnvVar")
    if action["kind"] == "ghl-webhook":
        return action.get("webhookEnvVar")
    return None


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------
def _load_json(path: Path, reasons: List[str], label: str) -> Optional[Any]:
    if not path.is_file():
        reasons.append(f"{label} not found at {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        reasons.append(f"{label} is not valid JSON: {exc}")
        return None


def _load_content_manifest(run_dir: Path, reasons: List[str]) -> Optional[Dict[str, Any]]:
    manifest = _load_json(run_dir / "content-manifest.json", reasons, "content-manifest.json (P3-CONTENT)")
    if manifest is None:
        return None
    schema = json.loads((_STRUCTURE_DIR / "content-manifest.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(manifest, schema)
    if errors:
        reasons.append("content-manifest.json failed schema validation: " + "; ".join(errors))
        return None
    ok, reason = rce.verify_locked_manifest(manifest)
    if not ok:
        reasons.append(f"content-manifest.json failed lock verification: {reason}")
        return None
    return manifest


def _load_build_receipt_site_dir(run_dir: Path, reasons: List[str]) -> Optional[Path]:
    receipt = _load_json(run_dir / "build-receipt.json", reasons, "build-receipt.json (P11-SITE-BUILD)")
    if receipt is None:
        reasons.append("P11-SITE-BUILD must run before P12-CRM (no build-receipt.json to locate the site)")
        return None
    site_dir_raw = receipt.get("site_dir")
    if not _is_non_empty_str(site_dir_raw):
        reasons.append("build-receipt.json has no usable site_dir")
        return None
    site_dir = Path(site_dir_raw)
    if not site_dir.is_dir():
        reasons.append(f"build-receipt.json site_dir does not exist on disk: {site_dir}")
        return None
    return site_dir


def _load_receipt(run_dir: Path, reasons: List[str]) -> Optional[Dict[str, Any]]:
    receipt = _load_json(run_dir / "crm-integration-receipt.json", reasons, "crm-integration-receipt.json (P12-CRM)")
    if receipt is None:
        return None
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = jsl.validate(receipt, schema)
    if errors:
        reasons.append("crm-integration-receipt.json failed schema validation: " + "; ".join(errors))
        return None
    return receipt


# ---------------------------------------------------------------------------
# site-data.generated.ts embedded ctaMap extraction (independent re-derivation
# of "what the built site actually wires", never trusting the receipt)
# ---------------------------------------------------------------------------
def _extract_site_data(site_dir: Path, reasons: List[str]) -> Optional[Dict[str, Any]]:
    path = site_dir / "lib" / "site-data.generated.ts"
    if not path.is_file():
        reasons.append(f"lib/site-data.generated.ts not found in site_dir at {path}")
        return None
    text = path.read_text(encoding="utf-8")
    marker = "SITE_DATA: SiteData ="
    idx = text.find(marker)
    if idx < 0:
        reasons.append("lib/site-data.generated.ts does not contain the expected SITE_DATA export")
        return None
    brace_start = text.find("{", idx)
    if brace_start < 0:
        reasons.append("lib/site-data.generated.ts SITE_DATA export is malformed (no opening brace)")
        return None
    depth = 0
    end = -1
    for i in range(brace_start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        reasons.append("lib/site-data.generated.ts SITE_DATA export is malformed (unbalanced braces)")
        return None
    try:
        return json.loads(text[brace_start:end])
    except json.JSONDecodeError as exc:
        reasons.append(f"lib/site-data.generated.ts SITE_DATA is not parseable JSON: {exc}")
        return None


# ---------------------------------------------------------------------------
# Secret scan (reuse build_site.SECRET_PATTERNS — the one detector)
# ---------------------------------------------------------------------------
def _secret_scan(receipt: Dict[str, Any]) -> List[str]:
    """Scans the serialized receipt for a secret VALUE (spec 14.3 'no secret
    values'; spec 20). Reports only WHICH pattern tripped, never the matched
    text, so a failed scan can never itself become a leak."""
    serialized = json.dumps(receipt, sort_keys=True)
    findings: List[str] = []
    for pattern in _build_site.SECRET_PATTERNS:
        if pattern.search(serialized):
            findings.append(f"crm-integration-receipt.json matched secret pattern {pattern.pattern!r}")
    return findings


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------
def evaluate(run_dir: "str | Path") -> Tuple[bool, str]:
    """The uniform P12-CRM phase-gate contract. Returns (passed, detail) and
    writes crm-integration-status.json into run_dir on every invocation."""
    run_dir = Path(run_dir)
    reasons: List[str] = []

    manifest = _load_content_manifest(run_dir, reasons)
    site_dir = _load_build_receipt_site_dir(run_dir, reasons)
    receipt = _load_receipt(run_dir, reasons)

    # If any of the three inputs failed to load/validate, fail closed now —
    # the downstream cross-checks would be meaningless.
    if manifest is None or site_dir is None or receipt is None:
        return _finish(run_dir, False, reasons, receipt)

    # --- secret VALUE scan (fail-closed, before anything else is trusted) ---
    secret_findings = _secret_scan(receipt)
    if secret_findings:
        reasons.append(f"[{AF_SECRET_LEAK}] " + "; ".join(secret_findings))
        return _finish(run_dir, False, reasons, receipt)

    if receipt.get("project_id") != manifest.get("project_id"):
        reasons.append(
            f"receipt project_id {receipt.get('project_id')!r} != content-manifest project_id "
            f"{manifest.get('project_id')!r} — receipt is not for this project"
        )

    # --- 1) the site actually wires the conversion layer ---
    for rel in _REQUIRED_SITE_WIRING:
        if not (site_dir / rel).is_file():
            reasons.append(f"conversion wiring missing from the built site: {rel}")

    # --- 2) the built site's ctaMap == the LOCKED content-manifest cta_map ---
    cta_map = manifest.get("cta_map") or {}
    site_data = _extract_site_data(site_dir, reasons)
    if site_data is not None:
        site_cta_map = site_data.get("ctaMap")
        if site_cta_map != cta_map:
            reasons.append(
                "the built site's site-data.generated.ts ctaMap does not match the locked "
                "content-manifest.json cta_map — the deployed conversion config drifted from the "
                "content the receipt claims to describe"
            )

    # --- 3) parse the LOCKED cta_map with the site's own fail-closed rules ---
    parsed_actions, parse_errors = parse_conversion_map(cta_map)

    # --- 4) cross-check every receipt conversion_action against the locked map ---
    receipt_actions: Dict[str, Dict[str, Any]] = {}
    for ra in receipt.get("conversion_actions", []):
        cta_id = ra.get("cta_id")
        receipt_actions[cta_id] = ra
        if cta_id in parse_errors:
            reasons.append(
                f"receipt conversion_action {cta_id!r} is INVALID in the locked cta_map "
                f"({parse_errors[cta_id]}) — cannot certify a CTA the site would reject"
            )
            continue
        parsed = parsed_actions.get(cta_id)
        if parsed is None:
            reasons.append(f"receipt conversion_action {cta_id!r} is not present in the locked content-manifest cta_map")
            continue
        if ra.get("kind") != parsed["kind"]:
            reasons.append(
                f"receipt conversion_action {cta_id!r} kind {ra.get('kind')!r} != locked cta_map kind {parsed['kind']!r}"
            )
        if set(ra.get("required_fields", [])) != set(parsed["requiredFields"]):
            reasons.append(
                f"receipt conversion_action {cta_id!r} required_fields {sorted(ra.get('required_fields', []))} "
                f"!= locked cta_map requiredFields {sorted(parsed['requiredFields'])}"
            )
        if parsed["kind"] in _CRM_KINDS:
            expected_env = _action_env_var(parsed)
            if not ra.get("env_var_name"):
                reasons.append(f"receipt conversion_action {cta_id!r} (kind {parsed['kind']}) has no env_var_name")
            elif ra.get("env_var_name") != expected_env:
                reasons.append(
                    f"receipt conversion_action {cta_id!r} env_var_name {ra.get('env_var_name')!r} "
                    f"!= locked cta_map env var NAME {expected_env!r}"
                )
        elif parsed["kind"] == "external-link":
            if ra.get("href") != parsed.get("href"):
                reasons.append(
                    f"receipt conversion_action {cta_id!r} href {ra.get('href')!r} != locked cta_map href {parsed.get('href')!r}"
                )

    # --- 5) every required conversion capability is covered by a valid+wired action ---
    requirements = manifest.get("conversion_requirements") or {}
    for capability in ("form", "calendar", "payment"):
        if not requirements.get(capability):
            continue
        covering = [
            ra for ra in receipt.get("conversion_actions", [])
            if capability in (ra.get("satisfies") or [])
            and ra.get("cta_id") in parsed_actions
            and ra.get("cta_id") not in parse_errors
        ]
        if not covering:
            reasons.append(
                f"content-manifest requires a working {capability!r} conversion path, but no valid, "
                f"site-wired conversion_action in the receipt declares it satisfies {capability!r}"
            )

    # --- 6) conversion-event proof: success (with UTM) AND error state ---
    _check_event_proof(receipt, parsed_actions, parse_errors, reasons)

    passed = not reasons
    return _finish(run_dir, passed, reasons, receipt)


def _check_event_proof(
    receipt: Dict[str, Any],
    parsed_actions: Dict[str, Dict[str, Any]],
    parse_errors: Dict[str, str],
    reasons: List[str],
) -> None:
    proof = receipt.get("conversion_event_proof") or {}
    success = proof.get("success") or {}
    error_state = proof.get("error_state") or {}

    # success path must be a real CRM-delivering CTA with propagated UTM.
    s_cta = success.get("cta_id")
    s_parsed = parsed_actions.get(s_cta)
    if s_cta in parse_errors or s_parsed is None:
        reasons.append(f"conversion_event_proof.success cta_id {s_cta!r} is not a valid, wired conversion action")
    elif s_parsed["kind"] not in _CRM_KINDS:
        reasons.append(
            f"conversion_event_proof.success cta_id {s_cta!r} is kind {s_parsed['kind']!r}, which delivers no "
            f"CRM conversion event (must be one of {_CRM_KINDS})"
        )
    if success.get("succeeded") is not True or not (200 <= int(success.get("response_status", 0)) < 300):
        reasons.append("conversion_event_proof.success must record succeeded=true with a 2xx response_status")
    utm = success.get("utm") or {}
    if success.get("utm_propagated") is not True or not utm:
        reasons.append(
            "conversion_event_proof.success must prove UTM propagation (utm_propagated=true and at least one utm param) — spec 13.3"
        )
    else:
        unknown = set(utm) - _UTM_KEYS
        if unknown:
            reasons.append(f"conversion_event_proof.success.utm contains non-canonical UTM keys: {sorted(unknown)}")

    # error path must be a real rejection of a submission that withheld a
    # required field (proving the fail-closed 400 path, not just the 200 path).
    e_cta = error_state.get("cta_id")
    e_parsed = parsed_actions.get(e_cta)
    if e_cta in parse_errors or e_parsed is None:
        reasons.append(f"conversion_event_proof.error_state cta_id {e_cta!r} is not a valid, wired conversion action")
    else:
        submitted = set(error_state.get("submitted_fields", []))
        required = set(e_parsed["requiredFields"])
        if required and not (required - submitted):
            reasons.append(
                "conversion_event_proof.error_state submitted every required field — it does not prove the "
                "fail-closed missing-required-field rejection path"
            )
    if error_state.get("rejected") is not True or not (400 <= int(error_state.get("response_status", 0)) < 500):
        reasons.append("conversion_event_proof.error_state must record rejected=true with a 4xx response_status")


def _finish(run_dir: Path, passed: bool, reasons: List[str], receipt: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    run_dir.mkdir(parents=True, exist_ok=True)
    status_record = {
        "generated_at": _now(),
        "run_dir": str(run_dir),
        "phase": "P12-CRM",
        "af_code": AF_P12,
        "passed": passed,
        "reasons": reasons,
        "receipt_present": receipt is not None,
    }
    try:
        _state_engine.atomic_write_json(run_dir / "crm-integration-status.json", status_record)
    except OSError:
        pass
    if passed:
        return True, (
            "P12-CRM PASS: every wired conversion action matches the locked content-manifest cta_map and the "
            "built site's own ctaMap; every required conversion capability is covered; UTM propagation and both "
            "the success and error (fail-closed) states are proven; no secret values."
        )
    return False, f"P12-CRM FAIL [{AF_P12}]: " + " | ".join(reasons)


# ---------------------------------------------------------------------------
# Self-test — offline, deterministic, no network, no live CRM call (spec 19.2).
# ---------------------------------------------------------------------------
def _build_fixture_p12_run_dir(run_dir: Path) -> Dict[str, Any]:
    """Writes the deterministic U15 fixture, patches its cta_map to carry a real
    ghl-webhook conversion CTA (satisfying the fixture's form requirement) plus
    a plain external-link CTA, materializes the site SOURCE via build_site
    --skip-toolchain (fast/offline — the conversion wiring files are copied in
    regardless of whether the npm toolchain runs), then synthesizes an
    approved-mock crm-integration-receipt.json consistent with all of it.
    Returns the synthesized receipt (already written to disk) so the caller can
    mutate copies of it for the fail-closed proofs."""
    fixture_dir = _SKILL_DIR / "tests" / "fixtures" / "site-fixture"
    if str(fixture_dir) not in sys.path:
        sys.path.insert(0, str(fixture_dir))
    import make_fixture  # noqa: E402

    make_fixture.write_fixture_run_dir(run_dir)

    manifest_path = run_dir / "content-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cta_map"] = {
        "primary": {"kind": "external-link", "label": "Book Your Strategy Call", "href": "#book"},
        "lead-capture": {
            "kind": "ghl-webhook",
            "label": "Request My Slot",
            "webhookEnvVar": "CWFE_GHL_WEBHOOK_URL",
            "requiredFields": ["email"],
        },
    }
    manifest["content_hash"] = rce.compute_content_hash(manifest)
    ok, reason = rce.verify_locked_manifest(manifest)
    if not ok:
        raise AssertionError(f"patched fixture manifest failed self-verification: {reason}")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Materialize the site source (skip_toolchain: fast, offline). build_site
    # raises SiteBuildError on a skipped toolchain by design (a skipped
    # toolchain can never be a P11 "pass"), but the site tree + build-receipt
    # are written before that raise — P12 only needs the materialized
    # conversion wiring + site_dir, never P11's own pass/fail verdict.
    if str(_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR))
    import build_site as bs  # noqa: E402

    try:
        bs.build_site(run_dir, skip_toolchain=True)
    except bs.SiteBuildError:
        pass

    now = "2026-07-15T00:00:00Z"
    receipt = {
        "schema_version": "1.0.0",
        "project_id": manifest["project_id"],
        "crm": {
            "provider": "gohighlevel",
            "location_id": "loc-selftest-fixture-123",
            "delegated_to": ["06-ghl-install-pages", "44-convert-and-flow-operator"],
            "secret_names": ["CWFE_GHL_WEBHOOK_URL"],
        },
        "conversion_actions": [
            {
                "cta_id": "lead-capture",
                "kind": "ghl-webhook",
                "env_var_name": "CWFE_GHL_WEBHOOK_URL",
                "required_fields": ["email"],
                "satisfies": ["form"],
                "ghl_resource": {"type": "workflow", "id": "wf-selftest-0001"},
            }
        ],
        "conversion_event_proof": {
            "mode": "approved-mock",
            "success": {
                "cta_id": "lead-capture",
                "submitted_fields": ["email"],
                "utm": {"utm_source": "instagram", "utm_campaign": "cwfe-selftest"},
                "utm_propagated": True,
                "response_status": 200,
                "succeeded": True,
            },
            "error_state": {
                "cta_id": "lead-capture",
                "submitted_fields": [],
                "response_status": 400,
                "rejected": True,
            },
        },
        "cleanup": {"test_contact_id": None, "cleaned_up": True},
        "created_at": now,
        "updated_at": now,
    }
    (run_dir / "crm-integration-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _write_receipt(run_dir: Path, receipt: Dict[str, Any]) -> None:
    (run_dir / "crm-integration-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _self_test() -> bool:  # noqa: C901 — a self-test naturally enumerates many small cases
    import copy
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory(prefix="cwfe-prove-conversion-selftest-") as tmp:
        run_dir = Path(tmp) / "run"
        good_receipt = _build_fixture_p12_run_dir(run_dir)

        # --- Proof 1: the good, consistent receipt PASSES ---
        passed, detail = evaluate(run_dir)
        print("good receipt evaluate():", passed, "-", detail[:220])
        if not passed:
            ok = False
            print("RESULT: FAIL (expected PASS on a consistent P12 fixture)")
        if not (run_dir / "crm-integration-status.json").is_file():
            ok = False
            print("RESULT: FAIL (crm-integration-status.json evidence not written)")

        def expect_fail(label: str, mutate) -> None:
            nonlocal ok
            receipt = copy.deepcopy(good_receipt)
            mutate(receipt)
            _write_receipt(run_dir, receipt)
            passed_x, detail_x = evaluate(run_dir)
            print(f"{label} evaluate():", passed_x, "-", detail_x[:200])
            if passed_x:
                ok = False
                print(f"RESULT: FAIL (gate did not fail closed: {label})")
            _write_receipt(run_dir, good_receipt)  # restore

        # --- Proof 2: a secret VALUE anywhere in the receipt is caught ---
        expect_fail("secret-leak", lambda r: r["conversion_actions"][0]["ghl_resource"].__setitem__("id", "sk-" + "a" * 32))

        # --- Proof 3: receipt claims a kind the locked cta_map does not wire ---
        expect_fail("kind-mismatch", lambda r: r["conversion_actions"][0].__setitem__("kind", "ghl-form-embed"))

        # --- Proof 4: env var NAME drift from the locked cta_map ---
        expect_fail("env-var-drift", lambda r: r["conversion_actions"][0].__setitem__("env_var_name", "CWFE_WRONG_ENV"))

        # --- Proof 5: a required conversion capability is left uncovered ---
        expect_fail("requirement-uncovered", lambda r: r["conversion_actions"][0].__setitem__("satisfies", []))

        # --- Proof 6: success proof without propagated UTM ---
        expect_fail("no-utm", lambda r: r["conversion_event_proof"]["success"].update({"utm_propagated": False, "utm": {}}))

        # --- Proof 7: error-state proof that submitted every required field (not a real rejection) ---
        expect_fail("weak-error-state", lambda r: r["conversion_event_proof"]["error_state"].__setitem__("submitted_fields", ["email"]))

        # --- Proof 8: success proof pointed at a non-CRM external-link CTA ---
        expect_fail("success-on-external-link", lambda r: r["conversion_event_proof"]["success"].__setitem__("cta_id", "primary"))

        # --- Proof 9: receipt describes a CTA absent from the locked cta_map ---
        expect_fail(
            "phantom-cta",
            lambda r: r["conversion_actions"].append(
                {"cta_id": "ghost", "kind": "ghl-webhook", "env_var_name": "CWFE_GHOST", "required_fields": [], "satisfies": [], "ghl_resource": {"type": "webhook", "id": "wh-ghost"}}
            ),
        )

        # --- Proof 10: a missing receipt fails closed with a clear reason ---
        (run_dir / "crm-integration-receipt.json").unlink()
        passed_m, detail_m = evaluate(run_dir)
        print("missing-receipt evaluate():", passed_m, "-", detail_m[:200])
        if passed_m or "crm-integration-receipt.json" not in detail_m:
            ok = False
            print("RESULT: FAIL (gate did not fail closed on a missing receipt)")
        _write_receipt(run_dir, good_receipt)

        # --- Proof 11: drift between the built site's ctaMap and the locked manifest ---
        site_data_path = Path(json.loads((run_dir / "build-receipt.json").read_text())["site_dir"]) / "lib" / "site-data.generated.ts"
        original = site_data_path.read_text(encoding="utf-8")
        try:
            tampered = original.replace('"lead-capture"', '"lead-capture-DRIFTED"', 1)
            if tampered == original:
                ok = False
                print("RESULT: FAIL (could not tamper site-data.generated.ts — selector drifted)")
            else:
                site_data_path.write_text(tampered, encoding="utf-8")
                passed_d, detail_d = evaluate(run_dir)
                print("site-ctaMap-drift evaluate():", passed_d, "-", detail_d[:200])
                if passed_d or "ctaMap" not in detail_d:
                    ok = False
                    print("RESULT: FAIL (gate did not catch a site whose wired ctaMap drifted from the locked content)")
        finally:
            site_data_path.write_text(original, encoding="utf-8")

        # --- Proof 12: restoring everything leaves a clean PASS ---
        passed_r, _ = evaluate(run_dir)
        if not passed_r:
            ok = False
            print("RESULT: FAIL (restoring the fixture did not restore a passing state)")

    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="P12-CRM conversion gate for the Cinematic and Web Funnel Engine. "
        "Invoked by run_cinematic_web_funnel.py as `prove_conversion.py --run-dir <dir>`.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return EXIT_OK if _self_test() else EXIT_FAIL

    if not args.run_dir:
        print("USAGE ERROR: --run-dir is required (unless --self-test)", file=sys.stderr)
        return EXIT_USAGE
    if not args.run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {args.run_dir}", file=sys.stderr)
        return EXIT_USAGE

    passed, detail = evaluate(args.run_dir)
    if passed:
        print(f"[PASS] P12-CRM — {detail}")
        return EXIT_OK
    print(f"[FAIL] P12-CRM — {detail}", file=sys.stderr)
    return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
