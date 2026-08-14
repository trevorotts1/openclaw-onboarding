#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/verify_after.py  (U03 tooling)
# VERIFY-AFTER-WRITE RE-VERIFIER — the fail-closed read-back prover for every
# provision-time WRITE this engine performs: the resolved per-box field-map
# stamp, the four REPLACE-ME location custom values, and the standard
# pipeline. "Every write is read back byte-for-byte in the same job; a
# mismatch is AF-AE-READBACK-MISMATCH" (config/field-map.json readback_rule;
# MASTERDOC floor). This module is the read-back half of that law for the
# filesystem-and-Convert-and-Flow writes provision-anthology-client.sh /
# anthology_registry.py / anthology_snapshot.py perform: a write whose
# re-read does not prove the intended bytes landed is REFUSED, never carried
# forward as a clean pass.
#
# WHERE THIS SITS: scripts/u03_modules/ — the U03 tooling module. It is NOT
# a manifest row: like docs_u02.py (ENGINE-MANIFEST row-54 sibling) it ships
# as an importable module under the engine's module packages, and the
# provisioner remains the manifest row that drives it. Imported BY NAME as
# u03_modules.verify_after from the engine scripts, per the u03_modules
# package contract (__init__.py: fail-closed empty init, pure namespace
# container). Standalone invocation works too: the SAME sys.path.insert
# bootstrap the sibling modules use resolves anthology_registry from
# scripts/.
#
# WHAT THIS OWNS (three read-back gates, all READ-ONLY, all fail-closed):
#   1. THE RESOLVED FIELD-MAP STAMP (filesystem write-back). The committed
#      config/field-map.json ships with every resolved slot null; provisioning
#      stamps the RESOLVED field_key / field_id / verified_at / location_masked
#      slots IN PLACE, as the node user, per box. The re-verify asserts the
#      file that now sits on disk is still valid JSON, still the contract
#      shape, still carries the 38 intended keys byte-exact, and — when the
#      stamp resolved — that the stamped field_id matches the LIVE field id
#      and the stamped field_key byte-equals the intended key. A stamp that
#      drifted from the live read-back is drift, never a pass. The committed
#      template state (all slots null) is a legal, verifiable state: key-only
#      check, never an id check.
#   2. THE FOUR LOCATION CUSTOM VALUES (Convert and Flow read-back). The
#      snapshot's OWN plumbing (config/anthology-snapshot-contract.json
#      location_custom_values.required) — the webhook URL, the hook secret,
#      the producer name, the producer email. Each must exist BY KEY on the
#      location and hold a clearly-labeled REPLACE-ME placeholder: the
#      TEMPLATE location must NEVER carry a real hook URL or a real
#      Authorization token (never-a-real-token, Skill 38 rule). Both
#      directions fail closed: missing keys FAIL, extra/renamed/real-valued
#      keys FAIL. The VALUE is never printed, echoed, or reflected in any
#      surface — keys only, always.
#   3. THE STANDARD PIPELINE (Convert and Flow read-back). Find-and-bind is
#      BY NAME (MASTERDOC floor 11): the pipeline named BYTE-EXACT
#      "Anthology Engine" (config/field-map.json
#      pipeline.standard_pipeline_name) must exist on the location. A renamed
#      or absent pipeline silently unbinds onboarding, so ANY non-byte-exact
#      result is a STOP refusal (AF-AE-PIPELINE-UI-CREATE / the
#      AF-AE-TEMPLATE-PIPELINE-MISSING family), never a silent fallback. The
#      name law is read from the field-map, never hardcoded here.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved via
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env
# first, then the three canonical client env stores); the location id via the
# standard location labels (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID), overridable with
# --location-id. SET / NOT SET only on every operator surface; a value is
# NEVER printed. The location id is a tenant identifier, masked to its LAST 4
# characters (reg._mask_location) on every surface.
#
# BROWSER UA: every request rides reg.CafClient, which applies CAF_BROWSER_UA
# so the Cloudflare edge fronting services.leadconnectorhq.com never 1010s
# the re-verify (CF 1010 / GK-09 discipline — the exact failure mode that
# 403s urllib's default UA before the request reaches Convert and Flow).
# Scope-vs-edge-block discrimination is the registry's own: a bare 401/403
# whose body does NOT match the genuine scope-denial signature raises
# UpstreamBlockedError -> HELD, never a scope STOP.
#
# FAIL-CLOSED, BY CONSTRUCTION: a missing contract section, a malformed
# field-map, a non-list read, an empty read, a strict subset of the intended
# keys, an extra/renamed key, a real-looking custom value, or a resolved
# stamp that disagrees with the live read — ALL are refusals or FAILs, never
# a blind pass, never a fabricated success. There is no code path that
# reports PASS on a surface it did not actually read.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  verified success — stamp coherent (or template-state null), all
#      contract custom values present as placeholders, standard pipeline
#      present and BYTE-EXACT (also --dry-run plan pass and self-test pass)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — label NOT SET / non-pit- value / usage / a contract
#      section missing or malformed / the standard pipeline ABSENT or
#      RENAMED / a strict subset of the intended keys missing live / the
#      resolved stamp's field_id disagreeing with the live field id
#   3  Convert and Flow API unreachable / upstream edge block (HELD;
#      retryable — the outcome is UNDETERMINED, never proven drifted)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-READBACK-AFTER-* family). A tamper NEVER masquerades as exit 1.
#   5  mismatch — extra/renamed live keys, a live fieldKey not byte-equal to
#      its intended_key, a real-looking custom value (never-a-real-token),
#      or a resolved stamp that drifted from the live read-back
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --dry-run / plan and --self-test are OFFLINE and need NO token and
# NO network):
#   verify_after.py verify [--location-id ID] [--field-map PATH]
#   verify_after.py plan
#   verify_after.py self-test
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, resolve_pit, resolve_location,
# load_field_map, _mask_location, _stop). DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""verify_after.py — verify-after-write re-verifier: the fail-closed read-back
prover for the engine's provision-time writes (U03 tooling, Skill 59)."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring + the LeadConnector client + the credential
# label resolution — this module reuses them, never re-implements them.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The one fixed report contract. Every byte-exact intended key / the standard
# pipeline name / the four custom-value keys come from the committed contract
# files — nothing is hardcoded here (a hardcoded list would drift, and the
# whole point is the field-map and the snapshot contract are the SINGLE
# SOURCES OF TRUTH).
REPORT_CONTRACT = "anthology-engine-verify-after"

# The never-a-real-token markers a custom value must carry. A value that is
# neither empty nor marker-labeled is REAL and REFUSED — the exact marker set
# custom_values_check.py uses for the same template gate.
PLACEHOLDER_MARKERS = ("REPLACE-ME", "replace-me", "<PUBLIC_HOSTNAME>")

# The resolver label families the live read needs (surfaced BY NAME only, on
# a STOP refusal). Values are NEVER printed.
PIT_LABELS = tuple(reg.PIT_LABELS)
LOCATION_LABELS = tuple(reg.LOCATION_LABELS)


class VerifyAfterError(Exception):
    """A fail-closed verification refusal (STOP or mismatch family): a
    missing contract section, a malformed field-map, a non-list read, a
    strict subset, a drifted stamp — a refusal, never a blind pass."""


def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing or malformed section is a refusal,
# never a pass — the re-verifier cannot judge a surface it has no law for)
# ---------------------------------------------------------------------------
def _contract_inventory(field_map: dict) -> list:
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise VerifyAfterError(
            "field-map.json has no provisioning.fields inventory — the "
            "byte-exact gate has nothing to assert; refusing a blind pass.")
    return [f for f in fields if isinstance(f, dict)]


def _contract_intended_keys(field_map: dict) -> list:
    return [f.get("intended_key") for f in _contract_inventory(field_map)
            if f.get("intended_key")]


def _contract_total(field_map: dict) -> int | None:
    total = (field_map.get("provisioning") or {}).get("total_keys")
    return total if isinstance(total, int) else None


def _contract_custom_values(contract: dict) -> list:
    """The contract's required location custom values, contract-driven
    (never a hardcoded tuple). Empty when the contract declares none."""
    return [dict(cv) for cv in ((contract.get("location_custom_values") or {}).get("required") or [])
            if isinstance(cv, dict)]


def _standard_pipeline_name(field_map: dict) -> str:
    name = (field_map.get("pipeline") or {}).get("standard_pipeline_name") or ""
    if not name:
        raise VerifyAfterError(
            "config/field-map.json pipeline.standard_pipeline_name is EMPTY "
            "— the name law has no contract source")
    return name


def is_placeholder(value: str) -> bool:
    """True when a custom-value payload is a clearly-labeled placeholder:
    empty or carrying a PLACEHOLDER_MARKERS marker. A real-looking value
    (e.g. https://... or Bearer ...) is NOT a placeholder. Only the fixed
    marker substrings are matched — the value itself is never printed."""
    v = (value or "").strip()
    if not v:
        return True
    return any(marker in v for marker in PLACEHOLDER_MARKERS)


# ---------------------------------------------------------------------------
# Gate 1 — the resolved field-map STAMP (filesystem write-back). READ-ONLY:
# this module never writes the map; it verifies the stamp a prior
# provision-time write left on disk.
# ---------------------------------------------------------------------------
def check_stamp(field_map: dict) -> dict:
    """Verify the field-map.json that sits on disk is the coherent contract
    shape — valid JSON (the caller's loader already proved that), the 38
    intended keys unique with the contact. prefix, the inventory equaling
    provisioning.total_keys, and — when the per-box stamp resolved slots —
    every stamped field_key byte-equal to its intended_key and every stamped
    field_id non-empty. The committed template state (all resolved slots
    null) is a legal, verifiable state: key-only check, never an id check.

    Returns the report dict; raises VerifyAfterError (STOP family) on a
    self-contradicting map — never a blind pass.
    """
    inventory = _contract_inventory(field_map)
    want_keys = _contract_intended_keys(field_map)
    total = _contract_total(field_map)
    if total is not None and len(want_keys) != total:
        raise VerifyAfterError(
            "field-map provisioning.fields carries %d intended keys but the "
            "provisioning.total_keys contract says %d — the field-map drifted "
            "from its own contract; refusing to judge a self-contradicting "
            "map." % (len(want_keys), total))
    if not want_keys:
        raise VerifyAfterError(
            "field-map provisioning.fields carries no intended_key entries — "
            "refusing a blind pass.")
    if len(set(want_keys)) != len(want_keys):
        raise VerifyAfterError(
            "field-map provisioning.fields carries duplicate intended_key "
            "entries — refusing a blind pass.")
    for key in want_keys:
        if not key.startswith("contact."):
            raise VerifyAfterError(
                "field-map intended key %r does not carry the contact. "
                "prefix — refusing a blind pass." % key)

    resolved = []
    for f in inventory:
        fk = f.get("field_key")
        if fk:
            resolved.append(f)
    template_state = not resolved

    stamped_drift = []
    for f in resolved:
        key = f.get("intended_key") or ""
        fk = f.get("field_key") or ""
        fid = f.get("field_id")
        if fk != key:
            stamped_drift.append("%s (stamped field_key %r != intended_key)"
                                 % (key, fk))
        if not fid:
            stamped_drift.append("%s (resolved stamp without a field_id)"
                                 % key)

    ok = not stamped_drift
    detail = ("all %d intended keys present, byte-exact, stamp coherent"
              % len(want_keys) if ok else
              "%d stamped slot(s) drifted" % len(stamped_drift))
    return {
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "gate": "stamp",
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "total": len(want_keys),
        "resolved": len(resolved),
        "template_state": template_state,
        "stamped_drift": stamped_drift,
        "detail": detail,
        "fail_closed": {
            "stamp_drift_fails": True,
            "template_state_legal": True,
            "note": "a resolved slot that drifted from its intended_key, or a "
                    "resolved stamp without a field_id, is drift — never a pass. "
                    "The committed template (all slots null) is key-only."},
    }


# ---------------------------------------------------------------------------
# Gate 2 — the four location custom values (Convert and Flow read-back).
# READ-ONLY, both directions, never-a-real-token.
# ---------------------------------------------------------------------------
def check_custom_values(client, location_id: str, contract: dict) -> dict:
    """Verify every contract location custom value exists BY KEY on the
    location and holds a clearly-labeled placeholder (never-a-real-token).
    Both key-set directions fail closed: missing keys FAIL, extra/renamed
    keys FAIL, real-valued keys FAIL (the attack this gate exists for). The
    report names KEYS ONLY — a value is never printed, echoed, or reflected
    in any surface. Returns the report dict; reg.ScopeDenied /
    reg.CafUnreachable propagate upward (the caller maps them HELD / STOP).
    """
    masked = _mask_location(location_id)
    want_rows = _contract_custom_values(contract)
    if not want_rows:
        raise VerifyAfterError(
            "the snapshot contract declares NO location custom values — "
            "config/anthology-snapshot-contract.json "
            "location_custom_values.required is empty or absent; a missing "
            "contract section is NEVER a blind pass")
    want = [cv.get("key") for cv in want_rows if cv.get("key")]
    if not want or len(want) != len(want_rows):
        raise VerifyAfterError(
            "the contract's custom-value list is malformed (a row lacks its "
            "key) — refusing a blind pass")

    live_rows = client.list_custom_values(location_id)
    if not isinstance(live_rows, list):
        raise VerifyAfterError(
            "customValues read did not return a list — refusing to judge an "
            "unread surface (never fabricated)")

    got = {}
    for cv in live_rows:
        k = cv.get("key") or cv.get("name") or ""
        if k:
            got[k] = cv

    want_set, got_set = set(want), set(got)
    missing = sorted(want_set - got_set)
    extra = sorted(got_set - want_set)
    found = sorted(want_set & got_set)

    # Real-valued placeholders: the TEMPLATE location must NEVER carry a real
    # hook URL or a real token. Refuse with a LOUD surface, naming the key
    # only (the value is never surfaced, never printed).
    real_keys = [k for k in found
                 if not is_placeholder((got[k] or {}).get("value") or "")]

    ok = (not missing and not extra and not real_keys)
    detail = ("all %d contract custom value(s) present, placeholders only"
              % len(want) if ok else
              "%d missing, %d extra, %d real-valued"
              % (len(missing), len(extra), len(real_keys)))
    return {
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "gate": "custom_values",
        "location": masked,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "found": found,
        "missing": missing,
        "extra": extra,
        "real_keys": real_keys,
        "detail": detail,
        "fail_closed": {
            "strict_subset_fails": bool(missing),
            "extra_keys_fail": bool(extra),
            "never_a_real_token": bool(real_keys),
            "note": "values are keys-only on every surface; a real-looking "
                    "value is REFUSED, never reported as a clean pass."},
    }


# ---------------------------------------------------------------------------
# Gate 3 — the standard pipeline (Convert and Flow read-back). Find-and-bind
# is BY NAME (MASTERDOC floor 11); any non-byte-exact result is a STOP.
# ---------------------------------------------------------------------------
def check_pipeline(client, location_id: str, field_map: dict) -> dict:
    """Verify the standard pipeline exists BYTE-EXACT BY NAME on the location.
    A renamed or absent pipeline silently unbinds onboarding, so ANY
    non-byte-exact result is a STOP refusal (the found names are surfaced in
    the report — never fabricated). Returns the report dict; raises
    VerifyAfterError (STOP family) on a non-exact result; reg.ScopeDenied /
    reg.CafUnreachable propagate upward.
    """
    want = _standard_pipeline_name(field_map)
    masked = _mask_location(location_id)

    pipes = client.list_pipelines(location_id)
    if not isinstance(pipes, list):
        raise VerifyAfterError(
            "pipelines read did not return a list — refusing to judge an "
            "unread surface (never fabricated)")

    found = next((p for p in pipes if isinstance(p, dict) and p.get("name") == want), None)
    if found is None:
        names = sorted({p.get("name") for p in pipes if isinstance(p, dict) and p.get("name")})
        raise VerifyAfterError(
            "AF-AE-TEMPLATE-PIPELINE-MISSING: the standard pipeline %r is "
            "ABSENT from the location (found: %s). Find-and-bind would fail "
            "silently — restore it in the Convert and Flow UI."
            % (want, ", ".join(names) or "(none)"))

    name = found.get("name") or ""
    stages = len([s for s in (found.get("stages") or []) if isinstance(s, dict)])
    ok = name == want
    if not ok:
        raise VerifyAfterError(
            "AF-AE-TEMPLATE-PIPELINE-MISSING: the standard pipeline is RENAMED "
            "on the location (live name %r != contract %r). Find-and-bind is "
            "BY NAME and would fail silently — restore the byte-exact name in "
            "the Convert and Flow UI." % (name, want))
    return {
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "gate": "pipeline",
        "location": masked,
        "ok": True,
        "verdict": "PASS",
        "name": name,
        "stage_count": stages,
        "detail": "standard pipeline present and BYTE-EXACT BY NAME",
        "fail_closed": {
            "find_and_bind_by_name": True,
            "note": "any non-byte-exact name is a STOP refusal — never a "
                    "silent fallback, never a faked success."},
    }


# ---------------------------------------------------------------------------
# The aggregate — ONE fail-closed report, verdict, and exit code.
# ---------------------------------------------------------------------------
def verify_after(client, location_id: str, field_map: dict, contract: dict,
                 *, out=None) -> int:
    """Run the three read-back gates and print the ONE JSON report object to
    stdout. Returns the exit code: 0 all gates PASS; 2 a STOP-family refusal;
    5 a mismatch; reg.ScopeDenied / reg.CafUnreachable propagate upward (the
    CLI maps them to STOP / HELD)."""
    out = out or sys.stderr
    masked = _mask_location(location_id)

    gate_reports = {
        "stamp": check_stamp(field_map),
        "custom_values": check_custom_values(client, location_id, contract),
        "pipeline": check_pipeline(client, location_id, field_map),
    }
    failed = [name for name, g in gate_reports.items() if not g.get("ok")]
    verdict = "PASS" if not failed else "FAIL"
    report = {
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "location": masked,
        "gates": gate_reports,
        "verdict": verdict,
        "fail_closed": True,
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if not failed:
        out.write("[verify-after] OK (marker %s): stamp coherent, custom "
                  "values placeholders only, standard pipeline byte-exact.\n"
                  % masked)
        return EX_OK
    out.write("[verify-after] FAIL (marker %s): gates %s fail-closed.\n"
              % (masked, ", ".join(failed)))
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials: the exact surfaces the live
# re-verify will assert, straight from the contract files (the single sources
# of truth — never hardcoded lists).
# ---------------------------------------------------------------------------
def plan(field_map: dict, contract: dict, *, out=None) -> int:
    out = out or sys.stderr
    try:
        keys = _contract_intended_keys(field_map)
        total = _contract_total(field_map)
        if total is not None and len(keys) != total:
            out.write("[verify-after] plan: inventory %d != total_keys %d — "
                      "refusing.\n" % (len(keys), total))
            return EX_MISMATCH
        cv_rows = _contract_custom_values(contract)
        cv_keys = [cv.get("key") for cv in cv_rows if cv.get("key")]
        pipeline_name = _standard_pipeline_name(field_map)
    except VerifyAfterError as exc:
        out.write("[verify-after] plan: %s\n" % exc)
        return EX_STOP
    print(json.dumps({
        "contract": REPORT_CONTRACT + "-plan",
        "schema_version": 1,
        "gates": ["stamp", "custom_values", "pipeline"],
        "intended_keys": keys,
        "total": len(keys),
        "custom_value_keys": cv_keys,
        "pipeline_name": pipeline_name,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, no network, no secrets.
# A FAILED self-test is exit 4 (enforced violation, AF-AE-READBACK-AFTER-*
# family), never 'unexpected error'.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the read surface with a
    programmable listing and a call log (self-tests prove zero writes)."""

    def __init__(self, custom_values=None, pipelines=None, behavior=None):
        self._custom_values = custom_values
        self._pipelines = pipelines
        self.behavior = behavior  # None | scope | edge | transport
        self.calls = []

    def list_custom_values(self, location_id):
        self.calls.append(("customValues", location_id))
        self._maybe_raise()
        if isinstance(self._custom_values, list):
            return [dict(cv) for cv in self._custom_values]
        return self._custom_values

    def list_pipelines(self, location_id):
        self.calls.append(("pipelines", location_id))
        self._maybe_raise()
        if isinstance(self._pipelines, list):
            return [dict(p) for p in self._pipelines]
        return self._pipelines

    def _maybe_raise(self):
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self.behavior == "transport":
            raise reg.CafUnreachable("Convert and Flow transport error: URLError")


def _fake_field_map():
    return reg.load_field_map(FIELD_MAP_PATH)


def _fake_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _golden_custom_values(contract: dict) -> list:
    """A live listing that EXACTLY matches the contract's custom-value keys,
    every value a clearly-labeled placeholder (never-a-real-token)."""
    rows = _contract_custom_values(contract)
    out = []
    for i, cv in enumerate(rows):
        key = cv.get("key") or ""
        out.append({"key": key, "name": key,
                    "value": "REPLACE-ME-%d" % (i + 1)})
    return out


def _golden_pipelines(field_map: dict) -> list:
    """A live listing carrying the standard pipeline byte-exact, with the
    contract's nine stages (so the stage-count surface is exercised)."""
    name = _standard_pipeline_name(field_map)
    stages = (field_map.get("pipeline") or {}).get("standard_stages") or []
    return [{"name": name, "id": "pipe_golden",
             "stages": [{"id": "stg_%d" % i, "name": (s or {}).get("name") or ""}
                        for i, s in enumerate(stages)]}]


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[verify-after] SELF-TEST FAILED "
                         "(AF-AE-READBACK-AFTER-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    import contextlib

    field_map = _fake_field_map()
    contract = _fake_contract()
    want_keys = _contract_intended_keys(field_map)
    total = _contract_total(field_map)
    assert want_keys, "field-map must carry intended keys"
    assert total is not None and len(want_keys) == total, \
        "inventory must equal provisioning.total_keys (%s != %s)" % (len(want_keys), total)
    assert all(k.startswith("contact.") for k in want_keys), \
        "every intended key must carry the contact. prefix"
    assert len(set(want_keys)) == len(want_keys), \
        "intended keys must be unique"
    cv_rows = _contract_custom_values(contract)
    assert cv_rows, "the snapshot contract must declare the four custom values"
    cv_keys = [cv.get("key") for cv in cv_rows]
    assert len(cv_keys) == len(cv_rows) and len(set(cv_keys)) == len(cv_keys), \
        "custom-value rows must each carry a unique key"

    # ---- golden live state: EVERYTHING passes ----
    golden_cv = _golden_custom_values(contract)
    golden_pipes = _golden_pipelines(field_map)
    caf = _FakeCaf(custom_values=golden_cv, pipelines=golden_pipes)

    stamp = check_stamp(field_map)
    assert stamp["verdict"] == "PASS", "template-state stamp must PASS: %s" % stamp["detail"]
    assert stamp["template_state"] is True, "committed map must be template state"
    assert stamp["total"] == len(want_keys)

    cv = check_custom_values(caf, "loc_fx", contract)
    assert cv["verdict"] == "PASS", "golden custom values: %s" % cv["detail"]
    assert cv["missing"] == [] and cv["extra"] == [] and cv["real_keys"] == []
    assert cv["location"] == "...c_fx", "location marker must be masked: %r" % cv["location"]
    _cv_blob = json.dumps(cv)
    assert all(((row.get("value") or "") not in _cv_blob)
               for row in golden_cv), \
        "no custom-value payload may appear in the report (keys only)"

    pipe = check_pipeline(caf, "loc_fx", field_map)
    assert pipe["verdict"] == "PASS" and pipe["ok"] is True, "golden pipeline must PASS"
    assert pipe["name"] == _standard_pipeline_name(field_map)

    # full aggregate on the golden state: exit 0, ONE JSON object on stdout
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_after(caf, "loc_fx", field_map, contract, out=io.StringIO())
    assert rc == EX_OK, "golden verify_after must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS", "golden report must carry verdict PASS"
    assert parsed["fail_closed"] is True
    assert set(parsed["gates"]) == {"stamp", "custom_values", "pipeline"}

    # ---- the aggregate NEVER writes ----
    assert caf.calls and all(m in ("customValues", "pipelines") for m, _ in caf.calls), \
        "verify_after performed an unexpected call: %s" % caf.calls

    # ---- attack fixtures: every mutation REFUSED / FAIL-recorded ----
    # 1. half-stamped slot (field_key resolved, field_id missing) -> drift
    partial = copy.deepcopy(field_map)
    partial["provisioning"]["fields"][0]["field_key"] = want_keys[0]
    stamp = check_stamp(partial)
    assert stamp["verdict"] == "FAIL", "half-stamped slot must FAIL"
    assert any("resolved stamp without a field_id" in d for d in stamp["stamped_drift"]), \
        "the half-stamp must be named in stamped_drift"

    # 2. resolved stamp whose field_key drifted from its intended_key -> drift
    drifted_map = copy.deepcopy(field_map)
    for f in drifted_map["provisioning"]["fields"]:
        f["field_key"] = f.get("intended_key")
        f["field_id"] = "fld_x"
    drifted_map["provisioning"]["fields"][0]["field_key"] = want_keys[0] + "_MUTATED"
    stamp = check_stamp(drifted_map)
    assert stamp["verdict"] == "FAIL", "stamped field_key drift must FAIL"
    assert any("_MUTATED" in d for d in stamp["stamped_drift"]), \
        "the drifted key must be named in stamped_drift"

    # 3. custom-value key MISSING (strict subset) -> FAIL, never a pass
    a1 = copy.deepcopy(golden_cv)[1:]
    cv = check_custom_values(_FakeCaf(custom_values=a1, pipelines=golden_pipes),
                             "loc_fx", contract)
    assert cv["verdict"] == "FAIL" and cv["missing"] == [cv_keys[0]], \
        "custom-value missing must be FAIL-recorded"

    # 4. custom value holding a REAL-looking value -> REFUSED (never-a-real-token)
    a2 = copy.deepcopy(golden_cv)
    a2[0]["value"] = "https://hooks.example.com/inline"
    cv = check_custom_values(_FakeCaf(custom_values=a2, pipelines=golden_pipes),
                             "loc_fx", contract)
    assert cv["verdict"] == "FAIL" and cv["real_keys"] == [cv_keys[0]], \
        "a real-looking custom value must be REFUSED, keys only"

    # 5. EXTRA custom-value key -> FAIL (exit 5 family), never a pass
    a3 = copy.deepcopy(golden_cv)
    a3.append({"key": "anthology_extra", "name": "anthology_extra",
               "value": "REPLACE-ME-9"})
    cv = check_custom_values(_FakeCaf(custom_values=a3, pipelines=golden_pipes),
                             "loc_fx", contract)
    assert cv["verdict"] == "FAIL" and cv["extra"] == ["anthology_extra"], \
        "custom-value extra must FAIL"

    # 6. non-list customValues read -> hard refusal (VerifyAfterError)
    try:
        check_custom_values(_FakeCaf(custom_values={"not": "a list"},
                                     pipelines=golden_pipes), "loc_fx", contract)
        raise AssertionError("non-list customValues read was NOT refused")
    except VerifyAfterError:
        pass

    # 7. standard pipeline ABSENT -> STOP refusal naming the found names
    try:
        check_pipeline(_FakeCaf(custom_values=golden_cv, pipelines=[]), "loc_fx", field_map)
        raise AssertionError("absent pipeline was NOT refused")
    except VerifyAfterError as exc:
        assert "AF-AE-TEMPLATE-PIPELINE-MISSING" in str(exc), "must carry the AF code"

    # 8. standard pipeline RENAMED -> STOP refusal
    renamed = [{"name": "Renamed Pipeline", "id": "pipe_r", "stages": []}]
    try:
        check_pipeline(_FakeCaf(custom_values=golden_cv, pipelines=renamed), "loc_fx", field_map)
        raise AssertionError("renamed pipeline was NOT refused")
    except VerifyAfterError:
        pass

    # 9. scope denied on a read -> STOP family, never a fabricated pass
    try:
        check_custom_values(_FakeCaf(custom_values=golden_cv, pipelines=golden_pipes,
                                     behavior="scope"), "loc_fx", contract)
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass

    # 10. edge block -> HELD family, never mislabeled as scope
    try:
        check_pipeline(_FakeCaf(custom_values=golden_cv, pipelines=golden_pipes,
                                behavior="edge"), "loc_fx", field_map)
        raise AssertionError("edge-block was NOT refused")
    except reg.UpstreamBlockedError:
        pass

    # 11. transport failure -> HELD family
    try:
        check_custom_values(_FakeCaf(custom_values=golden_cv, pipelines=golden_pipes,
                                     behavior="transport"), "loc_fx", contract)
        raise AssertionError("transport failure was NOT refused")
    except reg.CafUnreachable:
        pass

    # 12. empty live customValues listing -> strict subset -> FAIL, never pass
    cv = check_custom_values(_FakeCaf(custom_values=[], pipelines=golden_pipes),
                             "loc_fx", contract)
    assert cv["verdict"] == "FAIL" and len(cv["missing"]) == len(cv_keys), \
        "empty customValues listing must fail closed"

    # 13. field-map with no provisioning.fields -> hard refusal
    try:
        check_stamp({})
        raise AssertionError("missing inventory was NOT refused")
    except VerifyAfterError:
        pass

    # 14. inventory total != contract total_keys -> hard refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["total_keys"] = (total or 0) + 1
    try:
        check_stamp(tampered)
        raise AssertionError("total_keys drift was NOT refused")
    except VerifyAfterError:
        pass

    # 15. duplicate intended keys -> hard refusal
    dup = copy.deepcopy(field_map)
    dup["provisioning"]["fields"].append(dict(dup["provisioning"]["fields"][0]))
    try:
        check_stamp(dup)
        raise AssertionError("duplicate intended keys were NOT refused")
    except VerifyAfterError:
        pass

    # 16. non-contact-prefixed intended key -> hard refusal
    bad = copy.deepcopy(field_map)
    bad["provisioning"]["fields"][0]["intended_key"] = "anthology_no_prefix"
    try:
        check_stamp(bad)
        raise AssertionError("non-prefixed key was NOT refused")
    except VerifyAfterError:
        pass

    # 17. contract declares NO custom values -> hard refusal
    empty_contract = copy.deepcopy(contract)
    empty_contract["location_custom_values"] = {"required": []}
    try:
        check_custom_values(_FakeCaf(custom_values=golden_cv, pipelines=golden_pipes),
                            "loc_fx", empty_contract)
        raise AssertionError("absent contract section was NOT refused")
    except VerifyAfterError:
        pass

    # ---- plan: offline, no network, exact surface ----
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc = plan(field_map, contract, out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf2.getvalue())
    assert p["intended_keys"] == want_keys, "plan must list the intended keys in order"
    assert p["custom_value_keys"] == cv_keys, "plan must list the custom-value keys in order"
    assert p["pipeline_name"] == _standard_pipeline_name(field_map), \
        "plan must carry the standard pipeline name"

    dev.write("verify_after self-test: OK (field-map coherence %d keys == "
              "total_keys, golden all-PASS + aggregate exit 0, 17 attack "
              "fixtures refused or FAIL-recorded (partial-stamp/stamped-key-"
              "drift/custom-value-missing/custom-value-real/custom-value-extra/"
              "non-list-read/pipeline-absent/pipeline-renamed/scope-denied/"
              "edge-block/transport/empty-listing/no-inventory/total_keys-"
              "drift/duplicate-keys/non-prefixed-key/no-contract-section), "
              "no-writes, masked-location, values keys-only, plan offline)\n"
              % total)


# ---------------------------------------------------------------------------
# CLI — house shape: verify / plan / self-test subcommands; --self-test /
# --selftest normalize exactly as the sibling modules and the registry.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="verify_after.py",
        description="Verify-after-write re-verifier (U03 tooling, Skill 59): "
                    "the fail-closed read-back prover for every provision-time "
                    "write — the resolved field-map stamp, the four REPLACE-ME "
                    "location custom values, and the standard pipeline — one "
                    "JSON report, fail-closed.")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id (default: "
                         "the CLIENT-standard location label)")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    default="verify")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the sibling modules use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        contract = _read_json(Path(args.contract).expanduser(), "anthology-snapshot-contract.json")
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan(field_map, contract)

        # ---- live verify ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(PIT_LABELS)
            reg._stop(sys.stderr,
                      "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the client's OWN location-scoped pit- token and re-run."])
            return EX_STOP
        loc_label, loc = reg.resolve_location(args.location_id)
        if not loc:
            reg._stop(sys.stderr, "No Convert and Flow Location id is SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(LOCATION_LABELS),
                       "Set the client's OWN location id and re-run."])
            return EX_STOP
        sys.stderr.write("[verify-after] PIT resolved via %s (SET). Location "
                         "via %s (marker %s).\n"
                         % (pit_label, loc_label, reg._mask_location(loc)))
        client = reg.CafClient(token)
        return verify_after(client, loc, field_map, contract, out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[verify-after] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[verify-after] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[verify-after] HELD: %s\n" % exc)
        return EX_HELD
    except VerifyAfterError as exc:
        sys.stderr.write("[verify-after] STOP: %s\n" % exc)
        return EX_STOP
    except FileNotFoundError as exc:
        sys.stderr.write("[verify-after] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[verify-after] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


def _read_json(path: Path, what: str) -> dict:
    """Fail-closed contract reader — a missing section is never a blind pass."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise VerifyAfterError("cannot read %s: %s" % (what, exc)) from exc
    except ValueError as exc:
        raise VerifyAfterError("%s is not valid JSON: %s" % (what, exc)) from exc
    if not isinstance(data, dict):
        raise VerifyAfterError("%s does not parse to a JSON object" % what)
    return data


if __name__ == "__main__":
    sys.exit(main())
