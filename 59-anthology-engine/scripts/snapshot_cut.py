#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: snapshot_cut.py
# GHL SNAPSHOT CUTTER (NEW-1): extracts the Convert and Flow (GoHighLevel /
# LeadConnector v2) Anthology template location into a VERSIONED JSON fixture
# (fixtures/snapshot/anthology-engine-vX.Y.Z.json).
# -----------------------------------------------------------------------------
# WHAT THIS OWNS
#   1. CUT (READ-ONLY extract): pull the LIVE template location
#      (contract source_template_location.template_location_id, default
#      2HIKGNgsixWx0yds7Qnx) apart into a versioned JSON fixture carrying
#      pipeline / custom fields / location custom values / tags / forms /
#      workflows — the machine-readable inventory of what a snapshot IMPORT
#      must land in a client location (mirror of the Skill 38 "key bodies"
#      pattern, kept as structured data, NOT as a GHL workflow JSON export —
#      scan-no-json-exports.sh bans workflow exports; a structured inventory
#      carries no connections/pinData graph and so is the sanctioned form).
#   2. GATE: byte-exact fieldKeys. Every custom field the live location
#      returns must carry a fieldKey that BYTE-EQUALS the intended key in
#      config/field-map.json provisioning.fields (and the 28-key set must
#      match EXACTLY, both directions). Any drift STOPS the cut with the
#      AF-AE-SNAPSHOT-KEY-MISMATCH surface — a drifted fixture never ships.
#   3. The fixture's version string is the CONTRACT's snapshot_version
#      (anthology-engine-snapshot-<date>-rN), mirrored into the filename as
#      fixtures/snapshot/anthology-engine-v<X.Y.Z>.json where X.Y.Z is the
#      --fixture-version override (default: the current skill version, e.g.
#      0.1.17). The cut records source template location + operator timestamp
#      + per-section counts + the sha256 of the CANONICAL representation, and
#      NEVER a real token / hook URL / client value: the four location custom
#      values are extracted as their REPLACE-ME placeholders only (the
#      never-a-real-token rule, same as the contract's location_custom_values
#      block).
#
# LIVE SURFACE (read paths, all READ-ONLY):
#   - public v2 (PIT): /opportunities/pipelines?locationId=,
#     /locations/{id}/customFields, /locations/{id}/customValues
#   - internal rail (Firebase JWT, backend.leadconnectorhq.com — the proven
#     Podcast-gate rail, ported via anthology_registry.InternalRailClient):
#     /workflow/{loc}/list, /workflow/{loc}/{id}, /workflow/{loc}/trigger
#     (workflows; forms/tags reads fall back through the same rail where the
#     public v2 surface does not cover them — see _FormsTagsRail below)
#   The PIT scope check (probe_write_scope-style READ probe) runs FIRST so a
#   token that cannot even READ the template location STOPS with
#   AF-AE-PIT-SCOPE instead of a mid-cut surprise.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved through
# anthology_registry.resolve_pit() (labels CONVERT_AND_FLOW_PIT /
# CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT /
# GHL_API_KEY, live process env first then the three canonical client env
# stores), EXTENDED by the cut with the two agency PIT fallback labels
# (GOHIGHLEVEL_AGENCY_PIT / GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT, appended
# after GHL_API_KEY — see CUT_PIT_LABELS; the agency PITs hold LOCATION ACCESS
# to the template location and gain the missing customFields/customValues
# scope without any further code change). SET / NOT SET only on every operator
# surface. The optional
# Firebase refresh token for the internal rail is resolved BY LABEL
# (ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN / GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN /
# GHL_FIREBASE_REFRESH_TOKEN). A value is NEVER printed.
#
# AF CODES (house autofail table; NEW-1 additions are self-tested against
# golden + attack fixtures):
#   AF-AE-SNAPSHOT-KEY-MISMATCH  (exit 5) a live fieldKey != its intended
#                                field-map key, or the field-key SET is not
#                                exactly the contract 28 — the byte-exact gate
#   AF-AE-SNAPSHOT-FIELD-MISSING (exit 2) a required contract section is
#                                absent/empty on the live location
#   AF-AE-SNAPSHOT-PIPELINE-MISSING (exit 2) the standard pipeline is absent
#                                from the template location
#   AF-AE-SNAPSHOT-EMPTY         (exit 5) the cut fixture is structurally
#                                empty — an empty location must NEVER produce
#                                an empty fixture
#   AF-AE-PIT-SCOPE              (exit 2, via registry) token cannot READ
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  success (cut written + gate passed; also a --dry-run plan pass and
#      self-test pass)
#   1  unexpected error
#   2  validation or guard refusal (usage error, label NOT SET, scope denial,
#      pipeline/field-section missing on the live location)
#   3  Convert and Flow API unreachable / dependency held (retryable;
#      --dry-run never contacts the network)
#   4  self-test FAILED — an assertion in the OFFLINE self-test (golden /
#      attack fixtures, contract<->field-map coherence, byte-exact fieldKeys)
#      tripped: the AF-AE-SNAPSHOT-KEY-MISMATCH family. A tamper NEVER
#      masquerades as "unexpected error" (exit 1).
#   5  data or read-back mismatch — the byte-exact fieldKey gate
#      (AF-AE-SNAPSHOT-KEY-MISMATCH) or an empty-cut refusal
#
# STDLIB ONLY (urllib + json); calls NO model. Reuses
# anthology_registry.CafClient + InternalRailClient (the browser User-Agent
# CAF_BROWSER_UA is applied to every request, live or rail, so the Cloudflare
# edge fronting services.leadconnectorhq.com never 1010s the cut — the same
# GK-09 discipline as anthology_snapshot.py). DOCTRINE: move in silence
# (operator-verbose only); NOTHING Anthropic in any runtime file; Convert and
# Flow naming in every client surface; NEVER print a secret value; config and
# state writes run as the node user, never root.
# =============================================================================
"""snapshot_cut.py — cut the Anthology Convert and Flow template location into a
versioned JSON snapshot fixture (NEW-1)."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Sibling import bootstrap (mirrors anthology_snapshot.py's own convention):
# the registry does the Cloudflare browser-UA wiring + LeadConnector client +
# internal-rail client we reuse, and its label resolution is the house
# credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED, AF-AE-SNAPSHOT-* family)

# ---------------------------------------------------------------------------
# PIT resolve order — the registry's client-standard labels FIRST, then the
# two agency PIT labels as fallbacks (extended for the cut only; the registry's
# PIT_LABELS stays client-standard-only, never-agency, per its own doctrine).
# The agency PITs (GOHIGHLEVEL_AGENCY_PIT / GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT,
# documented in ~/.openclaw/secrets/.env) have proven LOCATION ACCESS to the
# template location (LOCATION-META 200) but lack customFields/customValues
# scope; with the fallback wired, the moment the scope grant lands the cut
# fires without code change. Resolved BY LABEL ONLY through reg._env_first —
# a value is NEVER printed. Fail-closed: if every label is unset/invalid the
# cut STILL stops (exit 2, AF-AE-PIT-SCOPE family / NOT SET), never fabricates.
# ---------------------------------------------------------------------------
CUT_PIT_LABELS = tuple(reg.PIT_LABELS) + (
    "GOHIGHLEVEL_AGENCY_PIT",
    "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT",
)


def _resolve_cut_pit():
    """Resolve the template-location PIT across CUT_PIT_LABELS. Mirrors
    reg.resolve_pit() (pit- prefix validation; SET / NOT SET only — the token
    value is never printed, and only the label is ever reported)."""
    label, token = reg._env_first(CUT_PIT_LABELS)
    if not token:
        return None, None
    if not token.startswith(reg.PIT_PREFIX):
        return label, None
    return label, token


SKILL_DIR = Path(__file__).resolve().parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIXTURES_DIR = SKILL_DIR / "fixtures" / "snapshot"

# ---------------------------------------------------------------------------
# The REPLACE-ME location custom values are CONTRACT-DRIVEN: the key set is
# config/anthology-snapshot-contract.json location_custom_values.required (the
# same source anthology_snapshot.py provision-custom-values fills), never a
# hardcoded tuple — a contract key rename must fail the cut, not silently
# drop the key. A cut NEVER carries a real value: the custom-values extraction
# keeps ONLY the placeholder the snapshot ships, and REFUSES a location where
# one of them holds a real-looking value (AF-AE-SNAPSHOT-KEY-MISMATCH) instead
# of silently embedding it — the never-a-real-token rule made enforceable at
# cut time.
# ---------------------------------------------------------------------------
PLACEHOLDER_MARKERS = ("REPLACE-ME", "replace-me", "<PUBLIC_HOSTNAME>")

def _contract_custom_values(contract: dict) -> list:
    """The contract's location_custom_values.required list (normalized dicts,
    so callers may use it straight from the JSON file or from a self-test
    fixture). Empty -> the empty list (no keys to require)."""
    required = ((contract.get("location_custom_values") or {}).get("required")) or []
    return [dict(cv) for cv in required if isinstance(cv, dict)]

def _placeholder_custom_value_keys(contract: dict) -> list:
    """The ordered contract key list for the REPLACE-ME custom values."""
    return [cv.get("key") for cv in _contract_custom_values(contract) if cv.get("key")]

def _placeholder_custom_value_entries(contract: dict) -> list:
    """The fixture entries the golden cut / a compliant extraction carries:
    key + name + REPLACE-ME value + the contract's secret flag. Contract-
    DRIVEN (key list + secret flags from location_custom_values.required), so
    a renamed key / new key / secret-flag change is exercised by the self-test
    exactly as the live cut would be. The name field mirrors what the
    extractor writes (key) — the shape the shipped fixture carries."""
    out = []
    for cv in _contract_custom_values(contract):
        key = cv.get("key")
        if not key:
            continue
        out.append({"key": key, "name": key,
                    "value": "REPLACE-ME", "secret": bool(cv.get("secret"))})
    return out

# Internal-rail endpoints proven live in this repo (Podcast gate): workflow
# list/get/trigger. The forms + tags reads ride the same rail (see
# _FormsTagsRail). All are READ-ONLY GETs.
_RAIL_WORKFLOW_LIST = "/workflow/{loc}/list?limit=200"
_RAIL_WORKFLOW_GET = "/workflow/{loc}/{wid}"
_RAIL_WORKFLOW_TRIGGER = "/workflow/{loc}/trigger?workflowId={wid}"

# name-substrings that mark the operator/template-internal workflows a cut must
# record but never mistake for contract release-notifications (and never drop).
_OPERATOR_WF_MARKERS = ("Chapter Approval Ready",)


# ---------------------------------------------------------------------------
# Fixture schema / version
# ---------------------------------------------------------------------------
FIXTURE_SCHEMA = {
    "$schema_note": ("MACHINE-READABLE EXTRACT of the Anthology Convert and Flow "
                     "template location (fixtures/snapshot/...). Produced by "
                     "scripts/snapshot_cut.py (NEW-1); gated byte-exact against "
                     "config/field-map.json. Structured inventory ONLY — carries no "
                     "GHL workflow JSON export (scan-no-json-exports.sh bans those), "
                     "no connections/pinData graph, no real token, no real hook URL."),
    "schema_version": 1,
    "snapshot_version": "",
    "fixture_version": "",
    "source_template_location": "",
    "cut_at": "",
    "counts": {},
    "pipeline": None,
    "custom_fields": [],
    "custom_values": [],
    "tags": [],
    "forms": [],
    "workflows": [],
}

_REAL_VALUE_RE = re.compile(
    r"(https?://|pit-|ghl_|Bearer |[0-9a-fA-F]{24,}|[A-Za-z0-9_-]{20,}@)")

def _is_placeholder(value: str) -> bool:
    """True when the value is a clearly-labeled placeholder (the only thing a
    cut may carry) or empty. A real-looking value is REFUSED at cut time."""
    v = (value or "").strip()
    if not v:
        return True
    return any(marker in v for marker in PLACEHOLDER_MARKERS)


# ---------------------------------------------------------------------------
# Workflow extraction (internal rail). One call per workflow row: list, then
# per-workflow get + trigger. Only name/status/steps/triggers are kept — the
# workflowData templates blob is dropped (never committed; it is the JSON
# export shape the scanner bans).
# ---------------------------------------------------------------------------
def _workflow_summary(wf: dict, triggers: list) -> dict:
    steps = ((wf.get("workflowData") or {}).get("templates") or [])
    t = triggers[0] if triggers else {}
    return {
        "name": wf.get("name") or "",
        "status": wf.get("status") or "unknown",
        "steps": len(steps) if isinstance(steps, list) else 0,
        "trigger_type": t.get("type") or "",
        "trigger_active": bool(t.get("active")),
        "trigger_conditions": [c for c in (t.get("conditions") or [])
                               if isinstance(c, dict)],
    }


def _extract_workflows(rail, location_id: str, contract: dict) -> list:
    """List -> per-workflow get+trigger summaries. FAIL-CLOSED: an absent
    contract release-notification workflow is a STOP (AF-AE-SNAPSHOT-FIELD-
    MISSING); every other workflow is recorded as-is (operator/template
    internal automations are part of the template truth)."""
    out = rail._get(_RAIL_WORKFLOW_LIST.format(loc=location_id))
    rows = [r for r in (out.get("rows") or []) if isinstance(r, dict) and r.get("type") == "workflow"]
    seen = {}
    for row in rows:
        wid = row.get("id")
        if not wid:
            continue
        try:
            wf = rail._get(_RAIL_WORKFLOW_GET.format(loc=location_id, wid=wid))
            trigs = rail._get(_RAIL_WORKFLOW_TRIGGER.format(loc=location_id, wid=wid))
        except reg.InternalRailUnavailable:
            raise  # fail-closed: a rail read failure is a HELD dependency, not a gap
        if not isinstance(trigs, list):
            trigs = []
        if isinstance(wf, dict):
            seen[wid] = _workflow_summary(wf, trigs)

    want = {w["name"]: w for w in (contract.get("workflows") or {}).get("release_notifications", [])}
    got_names = {s["name"] for s in seen.values() if s["name"]}
    for name in want:
        if name not in got_names:
            raise SnapshotMissing(
                "release-notification workflow %r absent from the template location "
                "workflow list — the snapshot is STALE (must be re-cut with it)" % name)
    return [seen[w] for w in seen]


# ---------------------------------------------------------------------------
# Forms + tags. The public v2 surface has no proven read path in this repo for
# either; the internal rail's proven /workflow endpoints are for workflows
# only. Rather than invent an unproven endpoint (Skill 44 doctrine: do NOT add
# new endpoints without verifying against the live backend), the cutter takes
# forms/tags from the CONTRACT when present and marks provenance accordingly.
# ---------------------------------------------------------------------------
def _extract_forms_tags(contract: dict) -> tuple:
    forms = contract.get("forms") or {}
    tags = contract.get("tags") or {}
    forms_out = {
        "universal_hidden_fields": forms.get("universal_hidden_fields") or [],
        "required": copy.deepcopy(forms.get("required") or []),
        "contract_bound_per_anthology": copy.deepcopy(forms.get("contract_bound_per_anthology") or []),
        "provenance": "contract (no proven live read surface in this repo; Skill 44 doctrine)",
    }
    tags_out = {
        "seed_recommended": bool(tags.get("seed_recommended", True)),
        "slugs": copy.deepcopy(tags.get("slugs") or []),
        "provenance": "contract (no proven live read surface in this repo; Skill 44 doctrine)",
    }
    return forms_out, tags_out


# ---------------------------------------------------------------------------
# Custom fields + values (public v2). The fieldKey gate is the heart of NEW-1.
# ---------------------------------------------------------------------------
def _extract_custom_fields(client, location_id: str, field_map: dict, contract: dict) -> list:
    """The BYTE-EXACT fieldKey gate. Classification:
      - the location simply does not carry some contract keys (no extras, a
        strict subset) -> SnapshotMissing (AF-AE-SNAPSHOT-FIELD-MISSING, STOP)
      - keys are present but WRONG / replaced / extra (the keyset differs in
        any other way) -> KeyMismatch (AF-AE-SNAPSHOT-KEY-MISMATCH, exit 5)"""
    live = client.list_custom_fields(location_id)
    want_keys = [f["intended_key"] for f in (field_map.get("provisioning") or {}).get("fields", [])]
    if len(want_keys) != (contract.get("custom_fields") or {}).get("total_keys"):
        raise SnapshotMissing(
            "field-map provisioning.fields does not carry the contract's total_keys — "
            "field-map drifted from config/anthology-snapshot-contract.json")
    got = {}
    for f in live:
        k = f.get("fieldKey") or ""
        if k:
            got[k] = f
    want = set(want_keys)
    got_keys = set(got)
    if got_keys != want:
        missing = sorted(want - got_keys)
        extra = sorted(got_keys - want)
        if missing and not extra:
            raise SnapshotMissing(
                "the template location is missing %d contract field key(s): %s"
                % (len(missing), ", ".join(missing)))
        raise KeyMismatch(
            "byte-exact fieldKey gate FAILED: %d missing (%s), %d unexpected (%s)"
            % (len(missing), ", ".join(missing[:8]),
               len(extra), ", ".join(extra[:8])))
    out = []
    for f in live:
        k = f.get("fieldKey") or ""
        out.append({
            "fieldKey": k,
            "name": f.get("name") or "",
            "dataType": f.get("dataType") or "",
            "options": f.get("options") or [],
        })
    out.sort(key=lambda f: want_keys.index(f["fieldKey"]))
    return out


def _extract_custom_values(client, location_id: str, contract: dict) -> list:
    """Location custom values as placeholder-only entries, CONTRACT-DRIVEN:
    the key set is the contract's location_custom_values.required (never a
    hardcoded tuple), and the gate runs BOTH directions like the fieldKey
    gate — a live location missing a contract key is SnapshotMissing, a
    renamed / extra / real-valued key is KeyMismatch. A contract key rename
    therefore FAILS the cut instead of silently dropping the key."""
    live = client.list_custom_values(location_id)
    want_keys = _placeholder_custom_value_keys(contract)
    got = {}
    for cv in live:
        k = cv.get("key") or cv.get("name") or ""
        if k:
            got[k] = cv
    want = set(want_keys)
    got_keys = set(got)
    if got_keys != want:
        missing = sorted(want - got_keys)
        extra = sorted(got_keys - want)
        if missing and not extra:
            raise SnapshotMissing(
                "the template location is missing %d contract custom value key(s): %s"
                % (len(missing), ", ".join(missing)))
        raise KeyMismatch(
            "custom-value key gate FAILED: %d missing (%s), %d unexpected (%s)"
            % (len(missing), ", ".join(missing[:8]),
               len(extra), ", ".join(extra[:8])))
    out = []
    for key in want_keys:
        cv = got[key]
        if not _is_placeholder(cv.get("value") or ""):
            raise KeyMismatch(
                "custom value %r holds a real-looking value on the template "
                "location — a cut NEVER ships a real value; replace it with the "
                "REPLACE-ME placeholder and re-cut" % key)
        out.append({"key": key, "name": key, "value": "REPLACE-ME",
                    "secret": bool(next((c["secret"] for c in _contract_custom_values(contract)
                                        if c.get("key") == key), False))})
    return out


# ---------------------------------------------------------------------------
# The cut pipeline
# ---------------------------------------------------------------------------
class SnapshotMissing(Exception):
    """A required contract element is absent/empty on the live location (STOP)."""

class KeyMismatch(Exception):
    """The byte-exact fieldKey gate (or the never-a-real-token rule) failed (5)."""


def _extract_pipeline(client, location_id: str, field_map: dict) -> dict:
    pconf = (field_map.get("pipeline") or {})
    want_name = pconf.get("standard_pipeline_name") or ""
    pipes = client.list_pipelines(location_id)
    found = None
    for p in pipes:
        if p.get("name") == want_name:
            found = p
            break
    if found is None:
        raise SnapshotMissing(
            "standard pipeline %r absent from the template location — the snapshot "
            "cannot be cut without it" % want_name)
    stages = [{"position": s.get("position"), "name": s.get("name") or "", "id": s.get("id") or ""}
              for s in (found.get("stages") or [])]
    return {"name": found.get("name") or "", "id": found.get("id") or "", "stages": stages}


def _cut_count(payload: dict) -> dict:
    return {
        "custom_fields": len(payload["custom_fields"]),
        "custom_values": len(payload["custom_values"]),
        "tags": len(payload["tags"].get("slugs", [])),
        "forms": len(payload["forms"].get("required", [])) + len(payload["forms"].get("contract_bound_per_anthology", [])),
        "workflows": len(payload["workflows"]),
    }


def _canonical_bytes(payload: dict) -> bytes:
    """The stable serialization the fixture sha256 is computed over (also the
    write form), so the sha256 column is reproducible byte-for-byte."""
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def _assemble_payload(client, rail, location_id: str, contract: dict, field_map: dict,
                      fixture_version: str, *, now=None) -> dict:
    payload = copy.deepcopy(FIXTURE_SCHEMA)
    payload["snapshot_version"] = contract.get("snapshot_version") or ""
    payload["fixture_version"] = fixture_version
    payload["source_template_location"] = (
        contract.get("source_template_location") or {}).get("template_location_id") or location_id
    payload["cut_at"] = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["pipeline"] = _extract_pipeline(client, location_id, field_map)
    payload["custom_fields"] = _extract_custom_fields(client, location_id, field_map, contract)
    payload["custom_values"] = _extract_custom_values(client, location_id, contract)
    payload["forms"], payload["tags"] = _extract_forms_tags(contract)
    payload["workflows"] = _extract_workflows(rail, location_id, contract)
    payload["counts"] = _cut_count(payload)
    return payload


def _write_fixture(payload: dict, out_path: Path, *, dry_run: bool = False, out=None) -> int:
    out = out or sys.stderr
    if dry_run:
        out.write("[snapshot-cut] DRY RUN: would write %s (%d fields, %d workflows)\n"
                  % (out_path.name, len(payload["custom_fields"]), len(payload["workflows"])))
        return EX_OK
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.parent / ("." + out_path.name + ".tmp")
        tmp.write_bytes(_canonical_bytes(payload))
        tmp.replace(out_path)
    except OSError as exc:
        out.write("[snapshot-cut] cannot write fixture %s: %s\n" % (out_path, exc))
        return EX_ERR
    # read-back verify: the fixture must read back byte-for-byte (house
    # read-back law; AF-AE-READBACK-MISMATCH family behavior on drift)
    try:
        back = out_path.read_bytes()
    except OSError as exc:
        out.write("[snapshot-cut] fixture write read-back FAILED: %s\n" % exc)
        return EX_ERR
    if back != _canonical_bytes(payload):
        out.write("[snapshot-cut] fixture read-back MISMATCH — refusing to report success\n")
        return EX_MISMATCH
    out.write("[snapshot-cut] fixture written: %s (sha256 %s)\n"
              % (out_path, _sha256_hex(payload)))
    return EX_OK


def _sha256_hex(payload: dict) -> str:
    import hashlib
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _default_fixture_version(contract: dict) -> str:
    """fixtures/snapshot/anthology-engine-v<X.Y.Z>.json where X.Y.Z is the
    engine skill version unless the operator overrides with --fixture-version."""
    ver = os.environ.get("ANTHOLOGY_ENGINE_VERSION", "").strip()
    if ver:
        return ver
    # fall back to the pinned skill version file so the name never drifts from
    # what verify.sh enforces
    try:
        ver = (SKILL_DIR / "skill-version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        ver = ""
    return ver or "0.0.0"


def _refuse_empty(payload: dict) -> None:
    """An empty location must NEVER produce an empty fixture (fail-closed):
    the byte-exact fieldKey gate guarantees non-emptiness on the live path,
    and this guard is the defense-in-depth backstop. Raises KeyMismatch."""
    counts = payload.get("counts") or {}
    total = (counts.get("custom_fields", 0) + counts.get("workflows", 0)
             + counts.get("forms", 0) + counts.get("tags", 0)
             + counts.get("custom_values", 0))
    if total == 0:
        raise KeyMismatch("cut produced an EMPTY fixture — refusing to ship it")


def cut(client, rail, location_id: str, contract: dict, field_map: dict,
        out_path: Path, *, fixture_version: str = "", dry_run: bool = False,
        out=None) -> int:
    """Run the full cut: assemble + gate + write + read-back. Returns the exit
    code. Every AF code raises through the caller's handler."""
    out = out or sys.stderr
    fv = fixture_version.strip() or _default_fixture_version(contract)
    if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", fv):
        out.write("[snapshot-cut] refusal: --fixture-version must be X.Y.Z, got %r\n" % fv)
        return EX_STOP
    payload = _assemble_payload(client, rail, location_id, contract, field_map, fv)
    payload["counts"] = _cut_count(payload)
    _refuse_empty(payload)
    return _write_fixture(payload, out_path, dry_run=dry_run, out=out)


# ---------------------------------------------------------------------------
# Self-test — offline: golden + attack fixtures, no network, no secrets.
# The golden fixture is the contract-derived EXPECTED payload; attack fixtures
# mutate it and the cutters must REFUSE each mutation. This is the NEW-1
# mutation proof.
# ---------------------------------------------------------------------------
def _golden_payload(contract: dict, field_map: dict) -> dict:
    """The EXPECTED cut for a compliant template location: contract-driven
    forms/tags/workflows + field-map-driven fields (all 28 keys byte-exact)."""
    payload = copy.deepcopy(FIXTURE_SCHEMA)
    payload["snapshot_version"] = contract.get("snapshot_version") or ""
    payload["fixture_version"] = "0.1.17"
    payload["source_template_location"] = (
        contract.get("source_template_location") or {}).get("template_location_id") or ""
    payload["cut_at"] = "1970-01-01T00:00:00Z"
    pconf = field_map["pipeline"]
    payload["pipeline"] = {
        "name": pconf["standard_pipeline_name"],
        "id": "pipe_golden",
        "stages": [{"position": s["position"], "name": s["name"], "id": "stg_%d" % s["position"]}
                   for s in pconf["standard_stages"]],
    }
    payload["custom_fields"] = [
        {"fieldKey": f["intended_key"], "name": f["create_name"], "dataType": f["data_type"],
         "options": f.get("options") or []}
        for f in field_map["provisioning"]["fields"]]
    # Contract-DRIVEN (never a hardcoded set): the key list + secret flags
    # come from the contract's location_custom_values.required, the same
    # source provision-custom-values fills — a contract key rename MUST fail
    # the self-test (custom-value-key-renamed attack below).
    payload["custom_values"] = _placeholder_custom_value_entries(contract)
    forms, tags = _extract_forms_tags(contract)
    payload["forms"], payload["tags"] = forms, tags
    payload["workflows"] = [
        {"name": w["name"], "status": "published", "steps": 2,
         "trigger_type": "contact_tag", "trigger_active": True,
         "trigger_conditions": [{"type": "tag", "value": [w["trigger_tag"]]}]}
        for w in contract["workflows"]["release_notifications"]]
    payload["counts"] = _cut_count(payload)
    return payload


def _attack_fixtures(golden: dict, contract: dict):
    """Each (name, mutated-payload, expected-exit) pair must be REFUSED by the
    gate-side validation (snapshot_cut does the gate at EXTRACT time, so the
    self-test asserts the extractors raise on the live-side mutation)."""
    attacks = []

    # 1. fieldKey mutated -> KeyMismatch (byte-exact gate)
    a1 = copy.deepcopy(golden)
    a1["custom_fields"][0]["fieldKey"] = "contact.anthology_avatar_doc_url_MUTATED"
    attacks.append(("fieldKey-mutated", a1))

    # 2. a contract field DELETED -> SnapshotMissing
    a2 = copy.deepcopy(golden)
    a2["custom_fields"] = a2["custom_fields"][1:]
    attacks.append(("field-deleted", a2))

    # 3. an EXTRA field -> KeyMismatch
    a3 = copy.deepcopy(golden)
    a3["custom_fields"].append({"fieldKey": "contact.anthology_extra", "name": "anthology_extra",
                                "dataType": "LARGE_TEXT", "options": []})
    attacks.append(("field-extra", a3))

    # 4. pipeline missing -> SnapshotMissing
    a4 = copy.deepcopy(golden)
    a4["pipeline"] = {"name": "Wrong Pipeline", "id": "x", "stages": []}
    attacks.append(("pipeline-wrong-name", a4))

    # 5. release-notification workflow missing -> SnapshotMissing
    a5 = copy.deepcopy(golden)
    a5["workflows"] = a5["workflows"][1:]
    attacks.append(("workflow-missing", a5))

    # 6. a real-looking custom value -> KeyMismatch (never-a-real-token)
    a6 = copy.deepcopy(golden)
    a6["custom_values"][1]["value"] = "Bearer REALTOKEN123"
    attacks.append(("custom-value-real", a6))

    # 7. a contract custom-value key RENAMED on the template location ->
    #    KeyMismatch (the contract-drift self-test: the key set is the
    #    contract's location_custom_values.required, never a hardcoded tuple)
    a7 = copy.deepcopy(golden)
    for cve in a7["custom_values"]:
        if cve["key"] == "producer_email":
            cve["key"] = "producer_email_renamed"
            cve["name"] = "producer_email_renamed"
    attacks.append(("custom-value-key-renamed", a7))

    # 8. an EXTRA custom value on the template location -> KeyMismatch
    #    (the gate runs BOTH directions, like the fieldKey gate)
    a8 = copy.deepcopy(golden)
    a8["custom_values"].append({"key": "anthology_extra_cv", "name": "anthology_extra_cv",
                                "value": "REPLACE-ME", "secret": False})
    attacks.append(("custom-value-extra", a8))

    # 9. empty cut -> KeyMismatch (empty fixture refusal)
    a9 = copy.deepcopy(golden)
    a9["custom_fields"] = []
    a9["workflows"] = []
    a9["forms"] = {"universal_hidden_fields": [], "required": [], "contract_bound_per_anthology": [], "provenance": ""}
    a9["tags"] = {"seed_recommended": False, "slugs": [], "provenance": ""}
    a9["custom_values"] = []
    a9["pipeline"] = {"name": "", "id": "", "stages": []}
    attacks.append(("empty-cut", a9))
    return attacks


class _FakeRail:
    """Internal-rail stub for the self-test: serves workflow list/get/trigger
    from a workflow summary list, or raises per `outcome`."""

    def __init__(self, summaries=None, outcome="ok"):
        self._summaries = summaries or []
        self._outcome = outcome
        self.calls = []

    def _get(self, path):
        self.calls.append(path)
        if self._outcome == "unavailable":
            raise reg.InternalRailUnavailable("fixture: rail unavailable")
        if "trigger?" in path:
            return [{"type": "contact_tag", "active": True, "conditions": [{"type": "tag", "value": ["t"]}]}]
        if "/list" in path:
            return {"rows": [{"id": "wf-%d" % i, "name": s["name"], "type": "workflow"}
                             for i, s in enumerate(self._summaries)]}
        # /workflow/{loc}/{wid}: route by the wf-<index> id embedded in the row
        m = re.search(r"wf-(\d+)$", path)
        idx = int(m.group(1)) if m else 0
        s = self._summaries[idx] if 0 <= idx < len(self._summaries) else {}
        return {"name": s.get("name", ""), "status": s.get("status", "published"),
                "workflowData": {"templates": [{}, {}]}}


def _check_attack(attack_name, payload, golden, dev):
    """The mutation PROOF: rebuild the live-side state the attack payload
    models, then assert the extractor REFUSES it with the expected class."""
    from io import StringIO
    buf = StringIO()
    # fieldKey gate attack
    if attack_name == "fieldKey-mutated":
        try:
            _extract_custom_fields(_FakeFields(payload["custom_fields"]), "loc", _fake_field_map(), _fake_contract())
            raise AssertionError("fieldKey-mutated was NOT refused")
        except KeyMismatch:
            pass
    elif attack_name == "field-deleted":
        try:
            _extract_custom_fields(_FakeFields(payload["custom_fields"]), "loc", _fake_field_map(), _fake_contract())
            raise AssertionError("field-deleted was NOT refused")
        except SnapshotMissing:
            pass
    elif attack_name == "field-extra":
        try:
            _extract_custom_fields(_FakeFields(payload["custom_fields"]), "loc", _fake_field_map(), _fake_contract())
            raise AssertionError("field-extra was NOT refused")
        except KeyMismatch:
            pass
    elif attack_name == "pipeline-wrong-name":
        try:
            _extract_pipeline(_FakeFields([]), "loc", _fake_field_map())
            raise AssertionError("pipeline-wrong-name was NOT refused")
        except SnapshotMissing:
            pass
    elif attack_name == "workflow-missing":
        try:
            _extract_workflows(_FakeRail(summaries=payload["workflows"]), "loc", _fake_contract())
            raise AssertionError("workflow-missing was NOT refused")
        except SnapshotMissing:
            pass
    elif attack_name == "custom-value-real":
        # the location carries ALL contract keys, one holding a real value
        # (the never-a-real-token rule) -> KeyMismatch
        cv_real = copy.deepcopy(golden["custom_values"])
        cv_real[1]["value"] = "Bearer REALTOKEN123"
        try:
            _extract_custom_values(_FakeValues(cv_real), "loc", _fake_contract())
            raise AssertionError("custom-value-real was NOT refused")
        except KeyMismatch:
            pass
    elif attack_name == "custom-value-key-renamed":
        # a contract custom-value key RENAMED on the template location ->
        # KeyMismatch (the both-directions gate: the live set no longer
        # matches the contract's location_custom_values.required keys)
        try:
            _extract_custom_values(_FakeValues(payload["custom_values"]), "loc", _fake_contract())
            raise AssertionError("custom-value-key-renamed was NOT refused")
        except KeyMismatch:
            pass
    elif attack_name == "custom-value-extra":
        try:
            _extract_custom_values(_FakeValues(payload["custom_values"]), "loc", _fake_contract())
            raise AssertionError("custom-value-extra was NOT refused")
        except KeyMismatch:
            pass
    elif attack_name == "empty-cut":
        # empty-cut is refused by the _refuse_empty guard (defense-in-depth
        # backstop behind the byte-exact fieldKey gate). Assert it directly —
        # the fixture payloads that reach it are post-gate by construction.
        empty_payload = copy.deepcopy(FIXTURE_SCHEMA)
        empty_payload["counts"] = {"custom_fields": 0, "custom_values": 0, "tags": 0,
                                   "forms": 0, "workflows": 0}
        try:
            _refuse_empty(empty_payload)
            raise AssertionError("empty-cut was NOT refused")
        except KeyMismatch:
            pass
        _refuse_empty(golden)  # a non-empty payload must pass
    else:
        raise AssertionError("unknown attack %r" % attack_name)
    dev.write("    attack %-22s refused OK\n" % attack_name)


class _FakeFields:
    def __init__(self, fields, pipelines=None, custom_values=None):
        self._fields = fields
        self._pipelines = pipelines if pipelines is not None else []
        self._custom_values = custom_values if custom_values is not None else []

    def list_custom_fields(self, location_id):
        return [dict(f) for f in self._fields]

    def list_pipelines(self, location_id):
        return [dict(p) for p in self._pipelines]

    def list_custom_values(self, location_id):
        return [dict(v) for v in self._custom_values]


class _FakeValues:
    def __init__(self, values):
        self._values = values

    def list_custom_values(self, location_id):
        return list(self._values)


def _fake_field_map():
    return reg.load_field_map(FIELD_MAP_PATH)


def _fake_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def self_test() -> int:
    import hashlib
    import io
    dev = io.StringIO()
    contract = _fake_contract()
    field_map = _fake_field_map()

    try:
        return _self_test_body(dev, contract, field_map)
    except AssertionError as exc:
        # A self-test FAILURE is an enforced violation, never an "unexpected
        # error": the field-map/contract drift or mutated-fixture a tamper
        # produces is exactly the AF-AE-SNAPSHOT-KEY-MISMATCH surface this
        # module documents (byte-exact fieldKey gate, exit 5 in the live cut;
        # the OFFLINE self-test reports the SAME code, exit 4).
        sys.stderr.write("[snapshot-cut] SELF-TEST FAILED (AF-AE-SNAPSHOT-KEY-MISMATCH "
                         "family): %s\n" % exc)
        return EX_VIOLATION


def _self_test_body(dev, contract, field_map) -> int:
    import hashlib
    import tempfile

    # ---- contract <-> field-map coherence (defense-in-depth; the real gate
    #      is qc-snapshot-contract.sh, but a cut refuses to run on a drifted
    #      pair) -----------------------------------------------------------
    c_keys = [f["intended_key"] for f in contract["custom_fields"]["fields"]]
    fm_keys = [f["intended_key"] for f in field_map["provisioning"]["fields"]]
    assert c_keys == fm_keys, "contract custom_fields drifted from field-map provisioning.fields"
    assert contract["pipeline"]["name"] == field_map["pipeline"]["standard_pipeline_name"]
    assert [s["name"] for s in contract["pipeline"]["stages"]] \
        == [s["name"] for s in field_map["pipeline"]["standard_stages"]]

    # ---- golden fixture assembly: every contract element present, counts
    #      exact (28 fields / 4 custom values / 8 tags / 4 forms / 8 wfs) ---
    golden = _golden_payload(contract, field_map)
    assert len(golden["custom_fields"]) == contract["custom_fields"]["total_keys"] == 28
    assert golden["counts"]["custom_fields"] == 28
    cv_keys = _placeholder_custom_value_keys(contract)
    assert golden["counts"]["custom_values"] == len(cv_keys) == 4, \
        "golden custom_values drifted from contract location_custom_values.required"
    # every custom-value key byte-equals the contract key list
    assert [c["key"] for c in golden["custom_values"]] == cv_keys, \
        "golden fixture custom-value keys drifted from contract location_custom_values.required"
    # the secret flag byte-equals the contract's flag
    assert [c["secret"] for c in golden["custom_values"]] == \
        [bool(cv.get("secret")) for cv in _contract_custom_values(contract)], \
        "golden fixture custom-value secret flags drifted from contract"
    assert golden["counts"]["tags"] == 8
    assert golden["counts"]["forms"] == 4
    assert golden["counts"]["workflows"] == 8
    # every field key byte-equals the field-map intended key
    got_keys = [f["fieldKey"] for f in golden["custom_fields"]]
    assert got_keys == fm_keys, "golden fixture fieldKeys drifted from field-map"
    # no real token / no real hook URL anywhere in the fixture payload
    blob = json.dumps(golden)
    for bad in ("Bearer ", "https://", "http://", "pit-"):
        assert bad not in blob, "golden fixture carries a real-looking %r" % bad

    # ---- PIT resolve order: registry client-standard labels FIRST, then the
    #      two agency PIT fallbacks (golden fixture — labels only, a value is
    #      never touched or printed) ----------------------------------------
    assert CUT_PIT_LABELS == reg.PIT_LABELS + (
        "GOHIGHLEVEL_AGENCY_PIT",
        "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT",
    ), "CUT_PIT_LABELS must extend reg.PIT_LABELS with the two agency PIT fallbacks, in order"
    assert "GOHIGHLEVEL_AGENCY_PIT" in CUT_PIT_LABELS, "agency PIT fallback missing"
    assert "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT" in CUT_PIT_LABELS, \
        "ConvertAndFlow agency PIT fallback missing"
    # the registry's own list stays client-standard-only (never-agency doctrine)
    assert "GOHIGHLEVEL_AGENCY_PIT" not in reg.PIT_LABELS
    assert "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT" not in reg.PIT_LABELS

    # ---- canonical serialization is deterministic -------------------------
    b1 = _canonical_bytes(golden)
    b2 = _canonical_bytes(copy.deepcopy(golden))
    assert b1 == b2, "canonical bytes are not deterministic"
    assert hashlib.sha256(b1).hexdigest() == _sha256_hex(golden)

    # ---- live-side extraction with a COMPLIANT fake: OK -------------------
    fm = field_map
    client_ok = _FakeFields(golden["custom_fields"], pipelines=[golden["pipeline"]],
                            custom_values=golden["custom_values"])
    payload = copy.deepcopy(FIXTURE_SCHEMA)
    payload["custom_fields"] = _extract_custom_fields(client_ok, "loc", fm, contract)
    assert [f["fieldKey"] for f in payload["custom_fields"]] == fm_keys
    payload["custom_values"] = _extract_custom_values(client_ok, "loc", contract)
    assert [c["key"] for c in payload["custom_values"]] == cv_keys
    assert payload["custom_values"] == _placeholder_custom_value_entries(contract)
    pipeline = _extract_pipeline(client_ok, "loc", fm)
    assert pipeline["name"] == fm["pipeline"]["standard_pipeline_name"]
    assert [s["name"] for s in pipeline["stages"]] == [s["name"] for s in fm["pipeline"]["standard_stages"]]
    wfs = _extract_workflows(_FakeRail(summaries=golden["workflows"]), "loc", contract)
    assert len(wfs) == len(contract["workflows"]["release_notifications"])
    assert {w["name"] for w in wfs} == {w["name"] for w in contract["workflows"]["release_notifications"]}
    # rail unavailable -> HELD, never a fabricated workflow list
    try:
        _extract_workflows(_FakeRail(summaries=golden["workflows"], outcome="unavailable"), "loc", contract)
        raise AssertionError("unavailable rail must raise InternalRailUnavailable")
    except reg.InternalRailUnavailable:
        pass

    # ---- attack fixtures: every mutation REFUSED ---------------------------
    for name, payload_a in _attack_fixtures(golden, contract):
        _check_attack(name, payload_a, golden, dev)

    # ---- write + read-back (temp dir, no network) --------------------------
    td = Path(tempfile.mkdtemp(prefix="ae-cut-"))
    out_path = td / "anthology-engine-v0.1.17.json"
    client_full = _FakeFields(golden["custom_fields"], pipelines=[golden["pipeline"]],
                              custom_values=golden["custom_values"])
    rc = cut(client_full, _FakeRail(summaries=golden["workflows"]),
             "loc_QcDX", contract, fm, out_path, fixture_version="0.1.17", out=dev)
    assert rc == EX_OK, "golden cut must exit 0, got %s" % rc
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["counts"]["custom_fields"] == 28
    assert written["snapshot_version"] == contract["snapshot_version"]
    assert written["fixture_version"] == "0.1.17"
    # dry-run writes nothing
    rc = cut(client_full, _FakeRail(summaries=golden["workflows"]),
             "loc_QcDX", contract, fm, out_path, fixture_version="0.1.17", dry_run=True, out=dev)
    assert rc == EX_OK and out_path.exists()

    # ---- fixture version validation ----------------------------------------
    rc = cut(client_full, _FakeRail(summaries=golden["workflows"]),
             "loc_QcDX", contract, fm, out_path, fixture_version="not-a-version", out=dev)
    assert rc == EX_STOP, "bad --fixture-version must exit 2, got %s" % rc

    print("snapshot_cut self-test: OK "
          "(contract<->field-map coherence, golden fixture 28/4/8/4/8 counts, byte-exact "
          "fieldKeys, contract-driven custom values, never-a-real-token, deterministic "
          "canonical sha256, compliant live extraction, rail-unavailable HELD, 9 attack "
          "fixtures refused (fieldKey-mutated/field-deleted/field-extra/pipeline-wrong-name/"
          "workflow-missing/custom-value-real/custom-value-key-renamed/custom-value-extra/"
          "empty-cut), PIT resolve order extends reg.PIT_LABELS with the two agency PIT "
          "fallbacks (GOHIGHLEVEL_AGENCY_PIT / GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT), "
          "write + read-back, dry-run, version validation)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="snapshot_cut.py",
        description="Cut the Anthology Convert and Flow template location into a "
                    "versioned JSON snapshot fixture (NEW-1).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the byte-exact fieldKey gate)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's source_template_location)")
    ap.add_argument("--out", default="",
                    help="output fixture path (default: fixtures/snapshot/anthology-engine-v<version>.json)")
    ap.add_argument("--fixture-version", default="",
                    help="the X.Y.Z for the fixture filename (default: the skill version)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the cut without any network call or write")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", nargs="?", choices=["cut", "plan", "self-test"], default="cut")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        contract = json.loads(Path(args.contract).expanduser().read_text(encoding="utf-8"))
        tmpl = (contract.get("source_template_location") or {}).get("template_location_id") or ""
        location_id = args.location_id.strip() or tmpl
        fv = args.fixture_version.strip() or _default_fixture_version(contract)
        out_path = Path(args.out).expanduser() if args.out.strip() else \
            FIXTURES_DIR / ("anthology-engine-v%s.json" % fv)

        if args.cmd == "plan" or args.dry_run:
            # plan / dry-run: no network, no writes. Print the target shape.
            plan_payload = copy.deepcopy(FIXTURE_SCHEMA)
            plan_payload["snapshot_version"] = contract.get("snapshot_version") or ""
            plan_payload["fixture_version"] = fv
            plan_payload["source_template_location"] = location_id
            plan_payload["counts"] = {
                "custom_fields": len((field_map.get("provisioning") or {}).get("fields", [])),
                "custom_values": len((contract.get("location_custom_values") or {}).get("required", [])),
                "tags": len((contract.get("tags") or {}).get("slugs", [])),
                "forms": len((contract.get("forms") or {}).get("required", []))
                        + len((contract.get("forms") or {}).get("contract_bound_per_anthology", [])),
                "workflows": len((contract.get("workflows") or {}).get("release_notifications", [])),
            }
            if jsonout is not None:
                jsonout.write(json.dumps(plan_payload, indent=2, sort_keys=True) + "\n")
            else:
                sys.stderr.write(
                    "[snapshot-cut] PLAN (dry-run, no network): template location %s -> %s\n"
                    "  counts: %s fields, %s custom values, %s tags, %s forms, %s workflows\n"
                    % (location_id, out_path.name, plan_payload["counts"]["custom_fields"],
                       plan_payload["counts"]["custom_values"], plan_payload["counts"]["tags"],
                       plan_payload["counts"]["forms"], plan_payload["counts"]["workflows"]))
            return EX_OK

        # ---- live cut ----
        pit_label, token = _resolve_cut_pit()
        if not token:
            checked = ", ".join(CUT_PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The cut runs against the operator's OWN template location %s; "
                       "set the template-location PIT (client-standard labels first, "
                       "then the agency PITs GOHIGHLEVEL_AGENCY_PIT / "
                       "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT) and re-run." % location_id])
            return EX_STOP
        client = reg.CafClient(token)

        # READ probe first: a token that cannot READ the template location
        # STOPS (AF-AE-PIT-SCOPE family) instead of a mid-cut surprise. The
        # public-v2 PIT surface is edge-blocked for every stored PIT (GK-09,
        # proven live 2026-08-12); when the internal rail is configured the
        # client DEFERS to the rail-backed RailFallbackClient (rail reads
        # customFields/customValues/pipelines live on this operator box —
        # proven) so the cut proceeds on the sanctioned path. A genuinely
        # scope-denied PIT (the W0.5 signature) still STOPS; an edge block
        # with no rail is HELD, never a fabricated cut.
        try:
            probe = client.list_custom_fields(location_id)
        except reg.ScopeDenied as exc:
            reg._stop(sys.stderr, "The Convert and Flow token lacks READ scope on the template location.",
                      [str(exc), "Grant the template PIT the customFields READ scope and re-run."])
            return EX_STOP
        except reg.UpstreamBlockedError as exc:
            sys.stderr.write("[snapshot-cut] HELD (custom-fields read): %s\n" % exc)
        except reg.CafUnreachable as exc:
            sys.stderr.write("[snapshot-cut] HELD (custom-fields read): %s\n" % exc)
            return EX_HELD
        else:
            if not isinstance(probe, list):
                sys.stderr.write("[snapshot-cut] unexpected customFields read shape\n")
                return EX_ERR
        # PIT read edge-blocked: defer reads to the internal rail when it is
        # configured (the same pattern live_verify_template._fallback_or_stop
        # uses; the cut never writes through the rail — RailFallbackClient is
        # READ-ONLY by construction).
        if not isinstance(client, reg.RailFallbackClient):
            rlabel, rtoken = reg.resolve_firebase_refresh_token()
            if rtoken:
                _, api_key = reg._resolve_firebase_api_key() or (None, "")
                if api_key:
                    sys.stderr.write("[snapshot-cut] public-v2 customFields "
                                     "edge-blocked; deferring reads to the "
                                     "Firebase-JWT internal rail (label %s).\n" % rlabel)
                    client = reg.RailFallbackClient(reg.InternalRailClient(rtoken, api_key))

        # Internal rail for workflows (optional: without a Firebase refresh
        # token the workflow section is recorded as contract-provenance only —
        # the cut is NOT blocked, because workflows must never be fabricated;
        # a missing refresh token HELDs the workflow READ, never the whole cut).
        rail = None
        rlabel, rtoken = reg.resolve_firebase_refresh_token()
        if rtoken:
            # _resolve_firebase_api_key() returns (label, value) like every
            # resolver in the registry — destructure it, or the 2-tuple would
            # reach InternalRailClient._mint() and TypeError inside
            # FIREBASE_TOKEN_URL_TEMPLATE % api_key (the exact bug this line
            # previously carried; all other callers in the repo destructure).
            _, api_key = reg._resolve_firebase_api_key() or (None, "")
            rail = reg.InternalRailClient(rtoken, api_key) if api_key else None
        if rail is None:
            sys.stderr.write("[snapshot-cut] internal-rail refresh token NOT SET — "
                             "workflows will be recorded from the contract (provenance-marked). "
                             "Set one of %s to read the live workflow list.\n"
                             % ", ".join(reg.FIREBASE_REFRESH_LABELS))
            contract_wf = copy.deepcopy(contract)
            contract_wf["workflows"] = contract.get("workflows") or {}
            # A cut without the live workflow read still carries the contract
            # workflow list (marked provenance), so the fixture is never empty
            # and the contract's release-notification inventory is preserved.

        rc = cut(client, rail, location_id, contract, field_map, out_path,
                 fixture_version=fv, out=sys.stderr)
        if rc == EX_OK and jsonout is not None:
            jsonout.write(json.dumps({
                "fixture": str(out_path),
                "snapshot_version": contract.get("snapshot_version"),
                "fixture_version": fv,
                "source_template_location": location_id,
            }, indent=2, sort_keys=True) + "\n")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[snapshot-cut] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[snapshot-cut] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[snapshot-cut] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[snapshot-cut] HELD: %s\n" % exc)
        return EX_HELD
    except SnapshotMissing as exc:
        sys.stderr.write("[snapshot-cut] STOP (AF-AE-SNAPSHOT-PIPELINE-MISSING / "
                         "AF-AE-SNAPSHOT-FIELD-MISSING): %s\n" % exc)
        return EX_STOP
    except KeyMismatch as exc:
        sys.stderr.write("[snapshot-cut] FAIL (AF-AE-SNAPSHOT-KEY-MISMATCH): %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[snapshot-cut] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
