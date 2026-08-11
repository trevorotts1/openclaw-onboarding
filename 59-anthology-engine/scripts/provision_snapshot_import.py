#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: provision_snapshot_import.py  (MASTER-SPEC NEW-2)
# IDEMPOTENT SNAPSHOT IMPORT INTO A CLIENT CONVERT AND FLOW SUB-ACCOUNT.
#
# WHAT THIS IS (config/anthology-snapshot-contract.json provisioning_branches_note
# SAME-AGENCY branch; the automated sibling of the MANUAL import owned by
# anthology_snapshot.py):
#   The client's Convert and Flow location IS a sub-account under BlackCEO's own
#   agency (companyId DAD7unnJpNUFc36952Xp): the agency PIT (locations.write scope)
#   can PUSH the snapshot directly into it -- PUT /locations/{id} with body
#   {companyId, snapshot:{id, override:true}} (references/anthology-snapshot-guide.md
#   section 6). This module OWNS that push:
#
#     import       idempotent PUT of the snapshot into the client's location, after
#                  a GET-check-by-name that proves the import has NOT already
#                  landed (a location that already carries the standard pipeline
#                  "Anthology Engine" BY NAME is left untouched: exit 0, verified,
#                  no second import). Then a read-back STATUS poll (GET
#                  snapshot-status, the same surface the n8n Snapshot Provisioner
#                  polls) until "completed" or a bound; after completion the module
#                  RESOLVES the field-map (the 28 field keys/ids read back from the
#                  imported location BY KEY, stamped into field-map.json in place --
#                  the exact resolved-field-map output the spec calls for) and
#                  writes provision_report.json (the machine-readable per-import
#                  report). NOTHING is created when the pipeline already exists.
#     status       READ-ONLY poll of snapshot-status for the location; never mutates.
#     plan         OFFLINE: validates the snapshot fixture against the contract +
#                  field-map, resolves the field-map from the fixture alone, prints
#                  the plan (no network, no writes).
#     self-test    OFFLINE golden + attack fixtures (no network, no secrets).
#
# IDEMPOTENCY LAW (GET-check-by-name BEFORE create): the pipeline is the snapshot's
# only UI-visible signature -- GoHighLevel exposes NO public v2 API to CREATE or
# DELETE a pipeline, and a re-import of a snapshot over an already-imported location
# is exactly the double-apply this engine must never perform. A location that
# already lists the standard pipeline BY NAME is therefore VERIFIED, never
# re-pushed. The genuine-completion authority stays box-side: the sibling
# anthology_snapshot.py verify-imported (client's OWN PIT) gates per-asset
# materialization; this module's field-map resolution is the SAME-BY-KEY proof.
#
# CREDENTIAL DOCTRINE: the token + location are resolved BY LABEL exactly like every
# other adapter (reg.resolve_pit / reg.resolve_location: CONVERT_AND_FLOW_PIT /
# CONVERT_AND_FLOW_LOCATION_ID etc. across live process env then the three canonical
# client env stores). The agency PIT used for the push is the OPERATOR-OWNED agency
# token under the same labels; values are NEVER printed (SET / NOT SET + masked
# location only). The browser User-Agent rides every request via reg.CafClient
# (W0.6/GK-09: services.leadconnectorhq.com is Cloudflare-fronted and 403s
# urllib's default UA -- CF 1010 -- before the request reaches Convert and Flow).
# The engine's scope-vs-edge-block discrimination (ScopeDenied vs
# UpstreamBlockedError) applies to every read AND write: a bare 401/403 is NEVER
# reported as a scope problem (the Wave 5 false positive), it is HELD.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-SNAPIMPORT-PIPELINE-PRESENT  -> a pipeline already carries the standard
#          name on the location: import is a no-op (this is the idempotent OK
#          branch; the module reports "already imported", resolves the field-map,
#          and exits 0 -- never a second push).
#   AF-AE-SNAPIMPORT-PIPELINE-MISSING  -> GET-check-by-name found NO standard
#          pipeline and the snapshot PUT was NOT performed (usage refusal: no
#          snapshot fixture / companyId not configured / dry-run). STOP.
#   AF-AE-SNAPIMPORT-PUSH-REFUSED      -> the location exists but the snapshot PUT
#          was rejected (validation / scope / edge block / transport). STOP or HELD
#          per class, never a silent skip.
#   AF-AE-SNAPIMPORT-NO-FIXTURE        -> the --snapshot fixture is absent, not the
#          contract snapshot, or drifted from the contract (field keys / pipeline
#          name / stages / companyId). STOP.
#   AF-AE-SNAPIMPORT-STATUS-STALLED    -> the status poll never reached "completed"
#          (timeout bound). HELD (exit 3), never a false pass.
#   AF-AE-SNAPIMPORT-READBACK-MISMATCH -> after completion the location's custom
#          fields did not carry every intended key byte-for-byte. exit 5; NOTHING
#          stamped into field-map.json.
#   AF-AE-SNAPIMPORT-COMPANYID-MISSING -> companyId for the push is not configured
#          (--company-id arg or env label) and no SAME-AGENCY tenancy is declared.
#          STOP: the module never invents an agency id.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator surface):
#   0  verified success (idempotent no-op / dry run counts as pass)
#   1  unexpected error
#   2  STOP refusal — usage error / missing credential / refusal to create
#   3  Convert and Flow API unreachable / dependency held / status not completed
#      (retryable)
#   5  read-back mismatch (a contract key absent from the present fields)
#
# STDLIB ONLY (urllib + json), reusing anthology_registry.CafClient + credential
# resolution. Calls NO model. DOCTRINE: move in silence; NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; NEVER print a
# secret value; config writes are atomic temp+replace; --self-test and --plan are
# OFFLINE.
# =============================================================================
"""provision_snapshot_import.py — idempotent snapshot import into a client
Convert and Flow sub-account + resolved field-map + provision report (Skill 59,
MASTER-SPEC NEW-2)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Sibling import bootstrap (mirrors anthology_snapshot.py's own convention). The
# registry does the Cloudflare browser-UA wiring + LeadConnector client +
# label resolution we reuse.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)

SKILL_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The engine's SAME-AGENCY company id (BlackCEO's own Convert and Flow agency;
# the client's location is a sub-account under it). Recorded in the snapshot
# contract's provisioning_branches_note + authorized_mechanisms. An arg or env
# label wins over this default so the module never hardcodes a value that drifted.
SAME_AGENCY_COMPANY_ID = "DAD7unnJpNUFc36952Xp"
COMPANY_ID_LABELS = ("ANTHOLOGY_SNAPSHOT_COMPANY_ID",)

# The snapshot-status poll surface the n8n Snapshot Provisioner workflow polls
# (same endpoint, same query shape; this module polls it directly after the push).
SNAPSHOT_STATUS_PATH = "/snapshots/status"
# Status values the LeadConnector v2 snapshot surface reports.
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"
_STATUS_PROCESSING = "processing"

# Bounds for the post-push status poll. The workflow honors a ~15-20 min asset
# materialization settle before notifying; the API-level "completed" transition is
# faster, so 12 min at 10 s cadence is a generous but bounded wait. --poll-timeout
# overrides, --poll-count 0 skips the wait (single read-back only).
DEFAULT_POLL_TIMEOUT_S = 720
DEFAULT_POLL_INTERVAL_S = 10


# ---------------------------------------------------------------------------
# Contract + fixture helpers. Values are never printed; drift is fail-closed.
# ---------------------------------------------------------------------------
def load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_company_id(override: str = ""):
    """(label, company_id) or (None, None). The engine's SAME-AGENCY company id:
    arg wins, else env label, else the contract-recorded default. NEVER printed
    beyond the final 4 chars (it is operator infra config, not a secret)."""
    if override and override.strip():
        return "(--company-id)", override.strip()
    for name in COMPANY_ID_LABELS:
        v = os.environ.get(name, "")
        if v and v.strip():
            return name, v.strip()
    return "(contract default)", SAME_AGENCY_COMPANY_ID


def fixture_snapshot_id(fixture: dict) -> str:
    """The snapshot id this module pushes: the fixture's own id, or the contract's
    snapshot_version (the date-stamped name the operator gives the exported
    snapshot). Fail-closed: an empty id is a validation refusal, never a push."""
    sid = (fixture.get("id") or "").strip()
    if not sid:
        sid = (fixture.get("snapshot_id") or "").strip()
    if not sid:
        sid = (fixture.get("snapshot_version") or "").strip()
    return sid


def contract_snapshot_id(contract: dict) -> str:
    return (contract.get("snapshot_version") or "").strip()


def fixture_intended_keys(fixture: dict):
    """The custom-field keys the fixture carries, derived the SAME way the engine
    derives them (fieldKey = "contact." + create_name). The snapshot contract and
    the field-map derive keys identically (qc-snapshot-contract.sh asserts the
    contract mirrors field-map provisioning.fields), so a fixture that carries
    the contract's create_names carries the engine's exact keys."""
    out = []
    for f in (fixture.get("custom_fields") or {}).get("fields") or []:
        if isinstance(f, dict):
            cname = (f.get("create_name") or "").strip() or (f.get("name") or "").strip()
            if cname:
                out.append(reg.derive_field_key(cname))
    return out


def fixture_pipeline_name(fixture: dict) -> str:
    return (fixture.get("pipeline") or {}).get("name") or ""


def fixture_stage_names(fixture: dict) -> list:
    out = []
    for s in (fixture.get("pipeline") or {}).get("stages") or []:
        if isinstance(s, dict) and s.get("name"):
            out.append(s["name"])
    return out


# ---------------------------------------------------------------------------
# Contract <-> fixture coherence (offline, fail-closed; AF-AE-SNAPIMPORT-NO-FIXTURE)
# ---------------------------------------------------------------------------
def check_fixture(fixture: dict, contract: dict, *, out=None, require_fields=True):
    """Validate the fixture against the snapshot contract BEFORE any push. Returns
    (ok, mismatches): mismatches is a list of (kind, detail) pairs, kinds
    "pipeline-name", "stages", "field", "snapshot-id". A drifted fixture STOPS
    setup -- a stale snapshot must never be pushed (the same law
    qc-snapshot-contract.sh enforces at CI time)."""
    out = out or sys.stderr
    mism = []
    cname = (contract.get("pipeline") or {}).get("name")
    if fixture_pipeline_name(fixture) != cname:
        mism.append(("pipeline-name",
                     "fixture pipeline name %r != contract %r" % (
                         fixture_pipeline_name(fixture), cname)))
    cstages = [s["name"] for s in (contract.get("pipeline") or {}).get("stages") or []]
    fstages = fixture_stage_names(fixture)
    if fstages != cstages:
        mism.append(("stages", "fixture stages %r != contract %r" % (fstages, cstages)))
    if require_fields:
        want = [f["create_name"] for f in (contract.get("custom_fields") or {}).get("fields") or []]
        got = [(f.get("create_name") or "").strip() or (f.get("name") or "").strip()
               for f in (fixture.get("custom_fields") or {}).get("fields") or []]
        missing = [w for w in want if w not in got]
        if missing:
            mism.append(("field", "fixture missing contract custom fields: %s" % ", ".join(missing)))
    cid = contract_snapshot_id(contract)
    if cid and fixture_snapshot_id(fixture) != cid:
        # A fixture may legitimately carry its own snapshot id (a fresh cut is
        # versioned at cut time); only flag when the fixture claims a DIFFERENT
        # contract version string outright.
        fver = fixture.get("snapshot_version")
        if fver and fver != cid:
            mism.append(("snapshot-id", "fixture snapshot_version %r != contract %r" % (fver, cid)))
    return (not mism), mism


# ---------------------------------------------------------------------------
# Resolved field-map: read the location's fields BACK BY KEY and stamp in place.
# ---------------------------------------------------------------------------
def resolve_field_map(field_map_path: Path, client, location_id: str, *,
                      out=None, jsonout=None):
    """Read the location's custom fields (list_custom_fields), verify every
    inventory intended_key exists BY KEY byte-for-byte, and stamp the resolved
    slots into field-map.json in place (atomic temp+replace, same as
    reg.save_field_map). Returns (exit_code, resolved_count). A key absent or a
    server fieldKey mismatch -> exit 5, NOTHING stamped (AF-AE-SNAPIMPORT-READBACK-MISMATCH).
    This is the SAME read-back law anthology_registry.provision_fields enforces;
    here the snapshot import already landed the fields, so the map is RESOLVED
    rather than created."""
    out = out or sys.stderr
    fm = load_json(field_map_path)
    inventory = fm.get("provisioning", {}).get("fields")
    if not isinstance(inventory, list) or not inventory:
        out.write("[resolve-field-map] STOP: %s has no provisioning.fields inventory\n"
                  % field_map_path)
        return EX_MISMATCH, 0
    masked = reg._mask_location(location_id)
    try:
        existing_list = client.list_custom_fields(location_id)
    except reg.ScopeDenied:
        out.write("[resolve-field-map] STOP: the Convert and Flow token cannot READ "
                  "custom fields on this location (marker %s). "
                  "AF-AE-SNAPIMPORT-READBACK-MISMATCH: resolution refused, "
                  "nothing stamped.\n" % masked)
        return EX_MISMATCH, 0
    except reg.CafUnreachable as exc:
        out.write("[resolve-field-map] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
        return EX_HELD, 0
    existing = {}
    for f in existing_list:
        fk = f.get("fieldKey")
        if fk:
            existing[fk] = f
    now = reg._now_iso()
    missing = []
    resolved = 0
    for item in inventory:
        intended = item["intended_key"]
        cname = item["create_name"]
        if reg.derive_field_key(cname) != intended:
            missing.append((intended, "create_name %r does not derive to the intended key" % cname))
            continue
        fobj = existing.get(intended)
        if not fobj:
            missing.append((intended, "absent from the imported location"))
            continue
        item["field_key"] = intended
        item["field_id"] = fobj.get("id")
        item["verified_at"] = now
        item["location_masked"] = masked
        resolved += 1
    if missing:
        out.write("[resolve-field-map] MISMATCH (marker %s): %d of %d keys missing/mismatched.\n"
                  % (masked, len(missing), len(inventory)))
        for k, why in missing:
            out.write("    - %s -> %s\n" % (k, why))
        out.write("    AF-AE-SNAPIMPORT-READBACK-MISMATCH: NOTHING stamped into field-map.json.\n")
        return EX_MISMATCH, resolved
    # Atomic stamp, exactly like reg.save_field_map.
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(field_map_path.parent),
                                      prefix=".field-map.", suffix=".tmp", delete=False)
    try:
        json.dump(fm, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, str(field_map_path))
    out.write("[resolve-field-map] OK (marker %s): %d keys resolved + stamped into %s\n"
              % (masked, resolved, field_map_path))
    if jsonout is not None:
        json.dump({"ok": True, "location": masked, "resolved_keys": resolved,
                   "field_map_path": str(field_map_path)}, jsonout)
        jsonout.write("\n")
    return EX_OK, resolved


# ---------------------------------------------------------------------------
# provision_report.json (the machine-readable per-import output)
# ---------------------------------------------------------------------------
def write_provision_report(report_path: Path, report: dict, *, out=None) -> None:
    """Atomic write of the provision report. The report NEVER carries a token or a
    secret value; the location id is masked."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(report_path.parent),
                                      prefix=".provision-report.", suffix=".tmp", delete=False)
    try:
        json.dump(report, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, str(report_path))


# ---------------------------------------------------------------------------
# The import itself (idempotent GET-check-by-name then PUT; then status poll;
# then resolved field-map + report).
# ---------------------------------------------------------------------------
def get_standard_pipeline(client, location_id: str, standard_name: str, *, out=None):
    """GET-check-by-name: read the location's pipelines and return the one whose
    name byte-equals the standard pipeline name, or None. A location that already
    carries the standard pipeline is already imported -- the idempotency law.
    Distinguishes ScopeDenied (STOP) from an edge/WAF block (HELD) exactly like
    every other adapter read."""
    try:
        for p in client.list_pipelines(location_id):
            if (p.get("name") or "").strip() == standard_name:
                return p
    except reg.ScopeDenied:
        raise
    return None


def push_snapshot(client, location_id: str, company_id: str, snapshot_id: str, *,
                  out=None):
    """The SAME-AGENCY automated push: PUT /locations/{id} with
    {companyId, snapshot:{id, override:true}} (references/anthology-snapshot-guide.md
    section 6; contract authorized_mechanisms row 1). The agency PIT (locations.write
    scope) is the operator-owned credential resolved BY LABEL by the caller.
    Raises ScopeDenied / CafValidation / CafUnreachable / UpstreamBlockedError;
    the caller maps them to STOP / HELD surfaces (AF-AE-SNAPIMPORT-PUSH-REFUSED)."""
    out = out or sys.stderr
    body = {
        "companyId": company_id,
        "snapshot": {"id": snapshot_id, "override": True},
    }
    out.write("[push-snapshot] PUT /locations/{id} (masked %s): snapshot %r, override, "
              "companyId ...%s. AF-AE-SNAPIMPORT-PUSH-REFUSED on any rejection.\n"
              % (reg._mask_location(location_id), snapshot_id, company_id[-4:]))
    # _request raises on HTTP error; a 2xx returns the parsed body.
    return client._request("PUT", "/locations/%s" % location_id, body=body)


def poll_snapshot_status(client, location_id: str, *, timeout_s: int,
                         interval_s: int, out=None, sleep_fn=time.sleep):
    """Poll GET /snapshots/status?locationId=... until "completed". Returns
    (rc, status). rc EX_OK on completed; EX_HELD on timeout/stalled
    (AF-AE-SNAPIMPORT-STATUS-STALLED) or a transient/edge error (never a false
    pass); EX_STOP on a scope denial (never retry a scope STOP)."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    deadline = time.monotonic() + timeout_s
    last_status = ""
    while True:
        try:
            resp = client._request("GET", SNAPSHOT_STATUS_PATH, query={"locationId": location_id})
        except reg.ScopeDenied:
            out.write("[snapshot-status] STOP: token not authorized for snapshot-status "
                      "on marker %s (AF-AE-SNAPIMPORT-STATUS-STALLED: never a false "
                      "pass).\n" % masked)
            return EX_STOP, last_status
        except reg.CafUnreachable as exc:
            out.write("[snapshot-status] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
            return EX_HELD, last_status
        status = (resp.get("status") or "").strip().lower() or last_status
        if status:
            last_status = status
        if status == _STATUS_COMPLETED:
            out.write("[snapshot-status] completed (marker %s).\n" % masked)
            return EX_OK, status
        if status == _STATUS_FAILED:
            out.write("[snapshot-status] FAILED (marker %s): the import reported failure. "
                      "AF-AE-SNAPIMPORT-STATUS-STALLED: never a false pass.\n" % masked)
            return EX_HELD, status
        if time.monotonic() >= deadline:
            out.write("[snapshot-status] stalled (marker %s): status %r never reached "
                      "completed within %ds. AF-AE-SNAPIMPORT-STATUS-STALLED: HELD, "
                      "retryable, never a false pass.\n" % (masked, last_status, timeout_s))
            return EX_HELD, last_status
        sleep_fn(interval_s)


def provision_import(client, location_id: str, fixture: dict, contract: dict,
                     field_map_path: Path, report_path: Path, *,
                     company_id: str = "", standard_pipeline_name: str = "",
                     poll_timeout_s: int = DEFAULT_POLL_TIMEOUT_S,
                     poll_interval_s: int = DEFAULT_POLL_INTERVAL_S,
                     poll_count: int = -1, dry_run: bool = False,
                     out=None, jsonout=None):
    """Idempotently import the snapshot fixture into the client's location and
    produce the two outputs (resolved field-map.json + provision_report.json).

    ORDER (the idempotency law, never inverted):
      1. GET-check-by-name: a location that already carries the standard pipeline
         is ALREADY IMPORTED -> verify only: resolve the field-map from the live
         read-back, write the "already_imported" report, exit 0. NO second push.
      2. Else dry-run -> report the planned push, exit 0, write nothing.
      3. Else require the snapshot fixture (AF-AE-SNAPIMPORT-NO-FIXTURE) and the
         SAME-AGENCY companyId (AF-AE-SNAPIMPORT-COMPANYID-MISSING), then PUT.
         The fixture is validated against the contract BEFORE the push.
      4. Poll snapshot-status to completed (bounded; stalled -> HELD, never pass).
      5. Resolve the field-map from the read-back custom fields BY KEY (missing
         key -> exit 5, nothing stamped).
      6. Write provision_report.json and exit 0.

    Returns an exit code; the report carries per-step status so a later
    re-run or the operator surface can see exactly what happened."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    std_name = standard_pipeline_name.strip() or (contract.get("pipeline") or {}).get("name") or ""

    # -- 1. GET-check-by-name (idempotency) ---------------------------------
    try:
        existing = get_standard_pipeline(client, location_id, std_name, out=out)
    except reg.ScopeDenied:
        out.write("[provision-import] STOP: token cannot READ pipelines on marker %s. "
                  "AF-AE-SNAPIMPORT-PIPELINE-MISSING family: STOP, never a blind "
                  "push.\n" % masked)
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[provision-import] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
        return EX_HELD

    report = {
        "schema_version": 1,
        "engine": "anthology",
        "contract": contract.get("contract"),
        "snapshot_version": contract_snapshot_id(contract),
        "fixture_snapshot_id": fixture_snapshot_id(fixture),
        "location_masked": masked,
        "tenant_branch": "same_agency",
        "import_state": "already_imported" if existing else "pending",
        "pipeline_present_by_name": bool(existing),
        "at": reg._now_iso(),
    }

    if existing:
        # Already imported: resolve the field-map from the live location, report
        # the no-op, exit per the resolve result. NEVER a second push.
        out.write("[provision-import] idempotent no-op (marker %s): the standard "
                  "pipeline %r already exists BY NAME on this location (AF-AE-"
                  "SNAPIMPORT-PIPELINE-PRESENT) -- no snapshot push performed.\n"
                  % (masked, std_name))
        rc, resolved = resolve_field_map(field_map_path, client, location_id,
                                         out=out, jsonout=None)
        report["import_state"] = "already_imported"
        report["pipeline_present_by_name"] = True
        report["field_map_resolved"] = rc == EX_OK
        report["resolved_keys"] = resolved
        report["pushed"] = False
        write_provision_report(report_path, report, out=out)
        out.write("[provision-import] provision report written to %s\n" % report_path)
        return rc

    # -- 2. dry-run: plan only, write nothing ---------------------------------
    if dry_run:
        out.write("[provision-import] DRY RUN (marker %s): standard pipeline %r absent "
                  "(AF-AE-SNAPIMPORT-PIPELINE-MISSING); would PUT snapshot %r with "
                  "override into this location. No writes performed.\n"
                  % (masked, std_name, fixture_snapshot_id(fixture)))
        report["import_state"] = "planned"
        report["pushed"] = False
        report["planned_push"] = True
        report["field_map_resolved"] = False
        report["resolved_keys"] = 0
        write_provision_report(report_path, report, out=out)
        if jsonout is not None:
            json.dump({"ok": True, "dry_run": True, "location": masked,
                       "state": "planned_push"}, jsonout)
            jsonout.write("\n")
        return EX_OK

    # -- 3. fixture + companyId gates, then the push ---------------------------
    sid = fixture_snapshot_id(fixture)
    if not sid:
        out.write("[provision-import] STOP: the snapshot fixture %s carries no "
                  "snapshot id/version (AF-AE-SNAPIMPORT-NO-FIXTURE). Refused "
                  "before any push.\n" % fixture_path_for(fixture))
        return EX_STOP
    ok, mism = check_fixture(fixture, contract, out=out)
    if not ok:
        out.write("[provision-import] STOP: fixture drifted from the snapshot "
                  "contract (AF-AE-SNAPIMPORT-NO-FIXTURE):\n")
        for kind, detail in mism:
            out.write("    - [%s] %s\n" % (kind, detail))
        out.write("    A stale snapshot is never pushed. Re-cut or re-point the "
                  "fixture, then re-run.\n")
        return EX_STOP
    cid_label, cid = resolve_company_id("")
    if not cid or not cid.strip():
        out.write("[provision-import] STOP: SAME-AGENCY companyId not configured "
                  "(--company-id or %s env). AF-AE-SNAPIMPORT-COMPANYID-MISSING: "
                  "the module never invents an agency id.\n" % " / ".join(COMPANY_ID_LABELS))
        return EX_STOP

    report["company_id_masked"] = "...%s" % cid[-4:]
    try:
        push_snapshot(client, location_id, cid, sid, out=out)
    except reg.ScopeDenied:
        out.write("[provision-import] STOP: the token was denied WRITE scope for the "
                  "snapshot push on marker %s. AF-AE-SNAPIMPORT-PUSH-REFUSED "
                  "(scope). Re-run with an agency PIT that carries locations.write "
                  "scope.\n" % masked)
        report["import_state"] = "push_refused_scope"
        write_provision_report(report_path, report, out=out)
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[provision-import] STOP: Convert and Flow REJECTED the snapshot "
                  "push (marker %s): %s. AF-AE-SNAPIMPORT-PUSH-REFUSED "
                  "(validation).\n" % (masked, exc))
        report["import_state"] = "push_refused_validation"
        write_provision_report(report_path, report, out=out)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        out.write("[provision-import] HELD: %s (marker %s). This is NOT a scope "
                  "problem -- likely a Cloudflare/WAF edge block (CF 1010); the "
                  "request already carries the proven browser User-Agent. "
                  "AF-AE-SNAPIMPORT-PUSH-REFUSED (edge). Retryable.\n"
                  % (exc, masked))
        report["import_state"] = "push_held_edge"
        write_provision_report(report_path, report, out=out)
        return EX_HELD
    except reg.CafUnreachable as exc:
        out.write("[provision-import] HELD: %s (marker %s). AF-AE-SNAPIMPORT-PUSH-"
                  "REFUSED (transport). Retryable.\n" % (exc, masked))
        report["import_state"] = "push_held_transport"
        write_provision_report(report_path, report, out=out)
        return EX_HELD
    report["pushed"] = True
    report["push_at"] = reg._now_iso()

    # -- 4. status poll (bounded) ----------------------------------------------
    if poll_count == 0:
        rc, status = EX_HELD, ""
        out.write("[provision-import] --poll-count 0: status poll skipped; the import "
                  "is NOT verified. AF-AE-SNAPIMPORT-STATUS-STALLED: HELD, re-run "
                  "`status` to complete.\n")
    else:
        rc, status = poll_snapshot_status(
            client, location_id, timeout_s=poll_timeout_s, interval_s=poll_interval_s,
            out=out)
    report["status"] = status
    if rc != EX_OK:
        report["import_state"] = "status_not_completed"
        write_provision_report(report_path, report, out=out)
        return rc

    # -- 5. resolve the field-map from the read-back -----------------------------
    report["import_state"] = "imported"
    rc, resolved = resolve_field_map(field_map_path, client, location_id,
                                     out=out, jsonout=None)
    report["field_map_resolved"] = rc == EX_OK
    report["resolved_keys"] = resolved

    # -- 6. report ---------------------------------------------------------------
    report["complete_at"] = reg._now_iso()
    write_provision_report(report_path, report, out=out)
    out.write("[provision-import] OK (marker %s): snapshot %r imported into the "
              "client's location; field-map resolved (%d keys); provision report "
              "written to %s\n" % (masked, sid, resolved, report_path))
    if jsonout is not None:
        json.dump({"ok": True, "location": masked, "imported": True,
                   "resolved_keys": resolved, "report": str(report_path)}, jsonout)
        jsonout.write("\n")
    return rc


def fixture_path_for(fixture: dict) -> str:
    """Best-effort human label for the fixture (never a secret, never the path
    into a secret-bearing file)."""
    return (fixture.get("$fixture") or "").strip() or "<snapshot fixture>"


# ---------------------------------------------------------------------------
# READ-ONLY status subcommand (never mutates)
# ---------------------------------------------------------------------------
def status_command(client, location_id: str, *, timeout_s: int, interval_s: int,
                   out=None, jsonout=None):
    rc, status = poll_snapshot_status(client, location_id, timeout_s=timeout_s,
                                      interval_s=interval_s, out=out)
    if jsonout is not None:
        json.dump({"ok": rc == EX_OK, "location": reg._mask_location(location_id),
                   "status": status, "exit": rc}, jsonout)
        jsonout.write("\n")
    return rc


# ---------------------------------------------------------------------------
# OFFLINE plan: fixture <-> contract coherence + resolved field-map from the
# fixture alone. No network, no writes.
# ---------------------------------------------------------------------------
def plan_command(fixture: dict, contract: dict, field_map_path: Path, *,
                 out=None, jsonout=None):
    ok, mism = check_fixture(fixture, contract, out=out)
    fm = load_json(field_map_path)
    inventory = fm.get("provisioning", {}).get("fields") or []
    fixture_keys = set(fixture_intended_keys(fixture))
    resolved = sum(1 for f in inventory if f.get("intended_key") in fixture_keys)
    if jsonout is not None:
        json.dump({
            "ok": ok, "mismatches": [{"kind": k, "detail": d} for k, d in mism],
            "fixture_snapshot_id": fixture_snapshot_id(fixture),
            "fixture_pipeline": fixture_pipeline_name(fixture),
            "fixture_stages": fixture_stage_names(fixture),
            "contract_pipeline": (contract.get("pipeline") or {}).get("name"),
            "resolved_keys_offline": resolved,
            "field_map_total": len(inventory),
        }, jsonout)
        jsonout.write("\n")
    return EX_OK if ok else EX_STOP


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets. Mirrors the
# sibling self-tests (anthology_snapshot.py / anthology_registry.py): an
# in-memory fake Convert and Flow exercises the idempotency law, the push, the
# poll ladder, the resolved field-map, the report, and the never-print rule.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the import surface:
    list_pipelines (GET-check-by-name), list_custom_fields (read-back),
    snapshot PUT (recorded), snapshot-status GET (scripted)."""

    def __init__(self, *, pipelines=None, fields=None, status_outcome="completed",
                 push_behavior="ok", field_write=True, pipeline_read=True):
        self._pipelines = list(pipelines or [])
        self._fields = {f["fieldKey"]: dict(f) for f in (fields or [])}
        self._status_outcome = status_outcome
        self._push_behavior = push_behavior
        self.pipeline_read = pipeline_read
        self.pushes = []
        self._seq = 0

    def list_pipelines(self, location_id):
        if not self.pipeline_read:
            raise reg.ScopeDenied("no pipeline read")
        return [dict(p) for p in self._pipelines]

    def list_custom_fields(self, location_id):
        return [dict(fieldKey=k, **{kk: vv for kk, vv in v.items() if kk != "fieldKey"})
                for k, v in self._fields.items()]

    def _request(self, method, path, query=None, body=None):
        if method == "PUT" and path.startswith("/locations/"):
            # A REFUSED push is never recorded as a push: the failure branches
            # below raise BEFORE the attempt is appended, so `pushes` counts
            # successful pushes only (the assertion a refused import never
            # reports "pushed").
            if self._push_behavior == "scope":
                raise reg.ScopeDenied("fixture: no locations.write scope")
            if self._push_behavior == "validation":
                raise reg.CafValidation("fixture: snapshot rejected (400)")
            if self._push_behavior == "edge":
                raise reg.UpstreamBlockedError("fixture: HTTP 403 edge block (CF 1010)")
            if self._push_behavior == "transport":
                raise reg.CafUnreachable("fixture: connect timeout")
            self._seq += 1
            self.pushes.append({"path": path, "body": body})
            return {"ok": True}
        if method == "GET" and path == SNAPSHOT_STATUS_PATH:
            if self._status_outcome == "processing-then-completed":
                if getattr(self, "_status_calls", 0) == 0:
                    self._status_calls = 1
                    return {"status": _STATUS_PROCESSING}
                return {"status": _STATUS_COMPLETED}
            if self._status_outcome == "failed":
                return {"status": _STATUS_FAILED}
            if self._status_outcome == "stalled":
                return {"status": _STATUS_PROCESSING}
            if self._status_outcome == "scope":
                raise reg.ScopeDenied("fixture: no snapshot-status scope")
            return {"status": _STATUS_COMPLETED}
        raise AssertionError("unexpected %s %s" % (method, path))


def _fixture_fields(field_map, *, drop=None):
    """The location's field read-back exactly as an imported snapshot would carry
    it: fieldKey derived per the engine law, id assigned, name == create_name."""
    out = []
    for f in field_map["provisioning"]["fields"]:
        if f["intended_key"] == drop:
            continue
        out.append({"fieldKey": f["intended_key"], "id": "fld-%s" % f["create_name"],
                    "name": f["create_name"], "dataType": f.get("data_type", "LARGE_TEXT")})
    return out


def _fixture_pipeline(contract):
    return {"id": "pipe-1", "name": contract["pipeline"]["name"],
            "stages": [{"id": "stg-%d" % s["position"], "name": s["name"]}
                       for s in contract["pipeline"]["stages"]]}


def _golden_fixture(contract):
    """A snapshot fixture that byte-matches the contract: the same pipeline name,
    the same stage names, every contract custom field by create_name, and the
    contract snapshot_version. This is the fixture verify.sh's drift gate would
    accept (mirror of qc-snapshot-contract.sh's shape)."""
    return {
        "$fixture": "golden",
        "id": contract["snapshot_version"],
        "snapshot_version": contract["snapshot_version"],
        "pipeline": {
            "name": contract["pipeline"]["name"],
            "stages": [dict(s) for s in contract["pipeline"]["stages"]],
        },
        "custom_fields": {
            "fields": [{"create_name": f["create_name"], "data_type": f["data_type"]}
                       for f in contract["custom_fields"]["fields"]],
        },
        "location_custom_values": [dict(cv) for cv in contract["location_custom_values"]["required"]],
    }


def _attack_fixture(contract):
    """An ATTACK fixture: wrong pipeline name, truncated stages, dropped fields,
    and a foreign snapshot_version. Every check must fail closed on it."""
    return {
        "$fixture": "attack",
        "id": "stale-snapshot-000000",
        "snapshot_version": "not-the-contract-version",
        "pipeline": {
            "name": "Other Pipeline",
            "stages": [{"position": 0, "name": "Wrong Stage"}],
        },
        "custom_fields": {
            "fields": [{"create_name": "contact.stolen_key"}],
        },
    }


def self_test() -> int:
    import io
    dev = io.StringIO()
    contract = load_json(CONTRACT_PATH)
    field_map = load_json(FIELD_MAP_PATH)
    td = Path(tempfile.mkdtemp(prefix="ae-snapimport-"))
    fm_path = td / "field-map.json"
    rpt_path = td / "provision_report.json"

    # (0) fixture coherence: golden passes, attack fails on every axis
    ok, mism = check_fixture(_golden_fixture(contract), contract, out=dev)
    assert ok, "golden fixture must be coherent: %r" % mism
    ok, mism = check_fixture(_attack_fixture(contract), contract, out=dev)
    assert not ok, "attack fixture must FAIL coherence"
    kinds = {k for k, _ in mism}
    assert kinds >= {"pipeline-name", "stages", "field", "snapshot-id"}, kinds

    # (1) idempotency: an already-imported location (standard pipeline present BY
    #     NAME) -> no push, field-map resolved from the read-back, report says
    #     already_imported, exit 0.
    fm_clean = load_json(FIELD_MAP_PATH)
    fm_clean["provisioning"]["fields"] = [
        {k: v for k, v in f.items() if k not in ("field_key", "field_id", "verified_at", "location_masked")}
        for f in fm_clean["provisioning"]["fields"]]
    import json as _json
    with open(fm_path, "w", encoding="utf-8") as fh:
        _json.dump(fm_clean, fh, indent=2)
    pre = load_json(fm_path)
    assert all(f.get("field_key") is None for f in pre["provisioning"]["fields"]), \
        "fixture map must start unresolved"

    caf = _FakeCaf(pipelines=[_fixture_pipeline(contract)],
                   fields=_fixture_fields(field_map))
    rc = provision_import(caf, "loc_QcDX", _golden_fixture(contract), contract,
                          fm_path, rpt_path, out=dev)
    assert rc == EX_OK, "already-imported location must exit 0, got %s" % rc
    assert caf.pushes == [], "already-imported location must NEVER be pushed"
    post = load_json(fm_path)
    resolved = [f for f in post["provisioning"]["fields"] if f["field_key"] and f["field_id"]]
    assert len(resolved) == len(fm_clean["provisioning"]["fields"]), \
        "expected every key resolved on the no-op path, got %d" % len(resolved)
    rpt = load_json(rpt_path)
    assert rpt["import_state"] == "already_imported" and rpt["pushed"] is False and \
        rpt["field_map_resolved"] is True, rpt

    # (2) fresh location: push + status poll (processing -> completed) + resolve
    caf2 = _FakeCaf(fields=_fixture_fields(field_map), status_outcome="processing-then-completed")
    rc = provision_import(caf2, "loc_QcDX", _golden_fixture(contract), contract,
                          fm_path, rpt_path, poll_count=-1, out=dev)
    assert rc == EX_OK, "fresh import must exit 0, got %s" % rc
    assert len(caf2.pushes) == 1, "fresh import must push exactly once, got %d" % len(caf2.pushes)
    body = caf2.pushes[0]["body"]
    assert body["snapshot"]["override"] is True and body["snapshot"]["id"] == contract["snapshot_version"]
    assert body["companyId"] == SAME_AGENCY_COMPANY_ID, "companyId must be the SAME-AGENCY id"
    rpt2 = load_json(rpt_path)
    assert rpt2["import_state"] == "imported" and rpt2["pushed"] is True and \
        rpt2["status"] == "completed" and rpt2["field_map_resolved"] is True, rpt2

    # (3) attack fixture NEVER reaches the push: STOP before any PUT
    caf3 = _FakeCaf(fields=_fixture_fields(field_map))
    rc = provision_import(caf3, "loc_QcDX", _attack_fixture(contract), contract,
                          fm_path, rpt_path, out=dev)
    assert rc == EX_STOP, "attack fixture must STOP (exit 2), got %s" % rc
    assert caf3.pushes == [], "attack fixture must NEVER be pushed"
    assert "AF-AE-SNAPIMPORT-NO-FIXTURE" in dev.getvalue()

    # (4) push refusal ladder: scope -> STOP, validation -> STOP, edge block ->
    #     HELD (never mislabeled as scope), transport -> HELD
    for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                           ("edge", EX_HELD), ("transport", EX_HELD)):
        dev4 = io.StringIO()
        caf4 = _FakeCaf(fields=_fixture_fields(field_map), push_behavior=behavior)
        rc = provision_import(caf4, "loc_QcDX", _golden_fixture(contract), contract,
                              fm_path, rpt_path, out=dev4)
        assert rc == want, "push_behavior %r: want %s, got %s" % (behavior, want, rc)
        assert caf4.pushes == [], "a refused push must not be recorded as pushed"
        if behavior == "edge":
            assert "NOT a scope problem" in dev4.getvalue(), \
                "an edge block must NEVER be mislabeled as a scope problem"

    # (5) status ladder: failed -> HELD, stalled -> HELD, scope -> STOP
    for outcome, want in (("failed", EX_HELD), ("stalled", EX_HELD), ("scope", EX_STOP)):
        dev5 = io.StringIO()
        caf5 = _FakeCaf(fields=_fixture_fields(field_map), status_outcome=outcome)
        rc = provision_import(caf5, "loc_QcDX", _golden_fixture(contract), contract,
                              fm_path, rpt_path, poll_count=-1,
                              poll_timeout_s=1, poll_interval_s=1, out=dev5)
        assert rc == want, "status_outcome %r: want %s, got %s" % (outcome, want, rc)
    # a fresh import with an unresolved location GET (read fails) is HELD too
    dev5b = io.StringIO()
    caf5b = _FakeCaf(pipelines=[], fields=_fixture_fields(field_map), status_outcome="stalled")
    caf5b.pipeline_read = True
    rc = provision_import(caf5b, "loc_QcDX", _golden_fixture(contract), contract,
                          fm_path, rpt_path, poll_count=-1,
                          poll_timeout_s=1, poll_interval_s=1, out=dev5b)
    assert rc == EX_HELD, "stalled status must HELD (never a false pass), got %s" % rc

    # (6) read-back mismatch: the imported location misses a field -> exit 5,
    #     NOTHING stamped into field-map.json. The map is reset to unresolved
    #     first so the file's pre-call state is provably untouched.
    dev6 = io.StringIO()
    drop_key = field_map["provisioning"]["fields"][-1]["intended_key"]
    caf6 = _FakeCaf(fields=_fixture_fields(field_map, drop=drop_key),
                    status_outcome="completed")
    with open(fm_path, "w", encoding="utf-8") as fh:
        _json.dump(fm_clean, fh, indent=2)
    pre6 = io.open(fm_path, encoding="utf-8").read()
    rc = provision_import(caf6, "loc_QcDX", _golden_fixture(contract), contract,
                          fm_path, rpt_path, out=dev6)
    assert rc == EX_MISMATCH, "missing read-back field must exit 5, got %s" % rc
    post6 = io.open(fm_path, encoding="utf-8").read()
    assert post6 == pre6, "NOTHING may be stamped on a read-back mismatch"
    assert "AF-AE-SNAPIMPORT-READBACK-MISMATCH" in dev6.getvalue()

    # (7) dry-run: planned push, NO write, NO report
    dev7 = io.StringIO()
    caf7 = _FakeCaf(fields=_fixture_fields(field_map))
    rc = provision_import(caf7, "loc_QcDX", _golden_fixture(contract), contract,
                          fm_path, rpt_path, dry_run=True, out=dev7)
    assert rc == EX_OK and caf7.pushes == [], "dry-run must plan without pushing"
    assert "DRY RUN" in dev7.getvalue()

    # (8) never-print: no secret value ever reaches any surface (the report and
    #     the operator stream carry no token, no location id, no secret)
    all_text = dev.getvalue() + dev6.getvalue() + dev7.getvalue() + _json.dumps(load_json(rpt_path))
    for token in ("pit-", "loc_QcDX", "SEKRIT", "Bearer "):
        assert token not in all_text, "surface leak: %r must never appear" % token

    # (9) offline plan: golden plans OK, attack STOPs
    dev9 = io.StringIO()
    rc = plan_command(_golden_fixture(contract), contract, FIELD_MAP_PATH, out=dev9)
    assert rc == EX_OK, "golden plan must exit 0, got %s" % rc
    rc = plan_command(_attack_fixture(contract), contract, FIELD_MAP_PATH, out=dev9)
    assert rc == EX_STOP, "attack plan must STOP, got %s" % rc

    print("provision_snapshot_import self-test: OK "
          "(golden+attack fixture coherence, GET-check-by-name idempotency "
          "[already-imported -> no push, field-map resolved], fresh push + status "
          "poll + resolve, attack never pushed, push-refusal ladder scope/validation/"
          "edge/transport, status ladder failed/stalled/scope, read-back mismatch "
          "stamps nothing, dry-run plans without writing, never-print, offline plan)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="provision_snapshot_import.py",
        description="Idempotent Convert and Flow snapshot import into a client "
                    "sub-account (same-agency push) + resolved field-map + "
                    "provision report (Skill 59, MASTER-SPEC NEW-2).")
    ap.add_argument("--snapshot", default="", help="path to the snapshot fixture JSON "
                    "(default: contract snapshot_version is pushed; fixture required "
                    "for the offline plan and coherence gate)")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (READ to resolve; WRITTEN in place "
                    "with resolved slots on success)")
    ap.add_argument("--provision-report", default="",
                    help="path to the provision_report.json output "
                    "(default: config/provision_report.json next to the field-map)")
    ap.add_argument("--location-id", default="",
                    help="override the client Convert and Flow location id (label "
                    "CONVERT_AND_FLOW_LOCATION_ID by default; never printed)")
    ap.add_argument("--company-id", default="",
                    help="override the SAME-AGENCY companyId (env "
                    "ANTHOLOGY_SNAPSHOT_COMPANY_ID, else the contract-recorded "
                    "BlackCEO agency id)")
    ap.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_S,
                    help="snapshot-status poll bound in seconds (default %d)"
                    % DEFAULT_POLL_TIMEOUT_S)
    ap.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL_S,
                    help="snapshot-status poll cadence in seconds (default %d)"
                    % DEFAULT_POLL_INTERVAL_S)
    ap.add_argument("--poll-count", type=int, default=-1,
                    help="status poll cap (-1 = poll until timeout; 0 = skip the "
                    "wait, never verified)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the import without performing it / no network")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["import", "status", "plan", "self-test"])

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # so argparse's required positional cmd never rejects the flag form.
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()

        contract = load_json(CONTRACT_PATH)

        # --snapshot fixture: required for plan and for a real push; the import
        # command may run WITHOUT a fixture only when the GET-check proves the
        # location is already imported (idempotent no-op).
        fixture = {}
        if args.snapshot.strip():
            fixture_path = Path(args.snapshot).expanduser()
            if not fixture_path.is_file():
                sys.stderr.write("[provision_snapshot_import] snapshot fixture not "
                                 "found: %s\n" % args.snapshot)
                return EX_ERR
            fixture = load_json(fixture_path)
            fixture["$fixture"] = str(fixture_path)
        elif args.cmd != "import":
            sys.stderr.write("[provision_snapshot_import] --snapshot is required "
                             "for %r (the offline plan validates the fixture)\n"
                             % args.cmd)
            return EX_STOP

        report_path = Path(args.provision_report).expanduser() if args.provision_report.strip() \
            else Path(args.field_map).expanduser().parent / "provision_report.json"

        if args.cmd == "plan":
            if not fixture:
                sys.stderr.write("[provision_snapshot_import] plan needs --snapshot\n")
                return EX_STOP
            return plan_command(fixture, contract, Path(args.field_map).expanduser(),
                                jsonout=jsonout)

        if args.cmd == "import":
            if args.dry_run:
                # No network in dry-run: use a masked placeholder location so
                # surfaces read; the GET-check is skipped (nothing exists offline).
                masked_loc = args.location_id or "DRYRUN"
                out = sys.stderr
                out.write("[provision-import] DRY RUN (marker %s): would GET-check "
                          "the standard pipeline by name, then PUT the snapshot "
                          "fixture with override. No writes performed.\n" % masked_loc)
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True, "location": masked_loc,
                               "state": "planned_push"}, jsonout)
                    jsonout.write("\n")
                return EX_OK
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return provision_import(
                client, loc_or_rc, fixture, contract,
                Path(args.field_map).expanduser(), report_path,
                company_id=args.company_id,
                poll_timeout_s=args.poll_timeout,
                poll_interval_s=args.poll_interval,
                poll_count=args.poll_count, dry_run=False, jsonout=jsonout)

        if args.cmd == "status":
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return status_command(client, loc_or_rc,
                                  timeout_s=args.poll_timeout,
                                  interval_s=args.poll_interval, jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        sys.stderr.write("[provision_snapshot_import] file not found: %s\n" % exc)
        return EX_ERR
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[provision_snapshot_import] unexpected error: %s\n"
                         % type(exc).__name__)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
