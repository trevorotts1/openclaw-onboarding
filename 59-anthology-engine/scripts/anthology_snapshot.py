#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: anthology_snapshot.py
# CLIENT-BOX SNAPSHOT IMPORT/LOAD MECHANISM (the realistic Skill-38-style
# MANUAL-IMPORT path). The Anthology Convert and Flow (GoHighLevel / LeadConnector
# v2) snapshot is CUT ONCE from the operator's OWN template location and IMPORTED
# per client into the client's OWN location (Settings -> Snapshots -> Import/Load).
# This module owns the per-client tail of that flow, run by
# provision-anthology-client.sh after the operator's manual import:
#
#   verify-imported          READ-ONLY: prove the snapshot LANDED on the live
#                            location -- the standard pipeline exists BY NAME with
#                            every contract stage, and every contract custom field
#                            exists BY KEY. A missing pipeline STOPs setup with the
#                            AF-AE-SNAPSHOT-PIPELINE-MISSING surface (import the
#                            snapshot); a missing field STOPs with
#                            AF-AE-SNAPSHOT-FIELD-MISSING.
#   provision-custom-values  FILL the four per-client location custom VALUES the
#                            snapshot ships as REPLACE-ME placeholders
#                            (anthology_webhook_url, anthology_hook_secret,
#                            producer, producer_email). IDEMPOTENT: GET-check then
#                            create-only-missing / update-in-place. The hook-secret
#                            Authorization value is resolved BY LABEL
#                            (ANTHOLOGY_INTAKE_HOOK_SECRET) and is NEVER printed to
#                            any surface (SET / NOT SET only). A missing secret
#                            label leaves that ONE placeholder unfilled with a note,
#                            never a hard fail (mirrors the step-7 gateway deferral).
#   stamp-version            Record which snapshot the box was provisioned from into
#                            the per-box marker $STATE_DIR/snapshot-version.json.
#   plan / self-test         Offline; no network.
#
# WHY MANUAL IMPORT AND NOT AN AGENCY->SUBACCOUNT AUTO-PUSH: this fleet's topology
# is EACH-CLIENT-OWNS-THEIR-OWN-GHL. A client's Convert and Flow location is owned
# by the client under their own agency, NOT a subaccount of a BlackCEO agency, so a
# cross-agency snapshot PUSH/LOAD into a location the operator does not own is
# almost certainly impossible and is REJECTED (recorded in
# config/anthology-snapshot-contract.json -> rejected_mechanisms). The only realistic
# path is the operator-run MANUAL IMPORT proven + finished here.
#
# The WHAT-THE-SNAPSHOT-CONTAINS contract is config/anthology-snapshot-contract.json,
# which is machine-pinned against the engine's own single-source-of-truth
# config/field-map.json (+ engine-config.template.json) by scripts/qc-snapshot-contract.sh
# so a stale snapshot cannot ship. This module reads the SAME field-map for the
# verify keys, so it can never drift from what the engine actually expects.
#
# STDLIB ONLY (urllib + json), reusing anthology_registry.CafClient. Calls NO model.
# DOCTRINE: move in silence (operator-verbose only); NOTHING Anthropic in any runtime
# file; Convert and Flow naming in every client surface; NEVER print a secret value
# (labels resolve SET / NOT SET only); config and state writes run as the node user,
# never root.
#
# EXIT CODES (house convention; nonzero STOPS setup with an operator surface):
#   0  verified success (idempotent no-op / dry run counts as pass)
#   1  unexpected error
#   2  STOP-setup guard refusal — snapshot not imported (pipeline/field absent),
#      customValues scope denied, or a usage error. LOUD operator surface.
#   3  Convert and Flow API unreachable / dependency held (retryable)
#   5  validation / read-back mismatch (a contract stage name absent from the
#      present pipeline)
# =============================================================================
"""anthology_snapshot.py — per-client Convert and Flow snapshot import verify +
custom-value fill + snapshot-version stamp (Skill 59)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Sibling import bootstrap (mirrors anthology_registry.py's own convention). The
# registry does the Cloudflare browser-UA wiring + LeadConnector client we reuse.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)

SKILL_DIR = Path(__file__).resolve().parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The Authorization-header custom value is the client's OWN intake-hook secret,
# resolved env-first BY LABEL. The value is NEVER printed (SET / NOT SET only). The
# aliases mirror the engine's route_secret_label contract.
HOOK_SECRET_LABELS = ("ANTHOLOGY_INTAKE_HOOK_SECRET",)
# The box's public hostname (NOT a secret): arg wins, else one of these env names.
PUBLIC_HOSTNAME_LABELS = ("ANTHOLOGY_PUBLIC_HOSTNAME", "PUBLIC_HOSTNAME",
                          "OPENCLAW_PUBLIC_HOSTNAME")


# ---------------------------------------------------------------------------
# Contract + resolution helpers. SET / NOT SET only; secret values never printed.
# ---------------------------------------------------------------------------
def load_contract(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_hook_secret():
    """(label, value) or (None, None). The value is NEVER printed."""
    for name in HOOK_SECRET_LABELS:
        v = os.environ.get(name, "")
        if v and v.strip():
            return name, v.strip()
    return None, None


def resolve_public_hostname(override: str = ""):
    if override and override.strip():
        return override.strip()
    for name in PUBLIC_HOSTNAME_LABELS:
        v = os.environ.get(name, "")
        if v and v.strip():
            return v.strip()
    return ""


def _norm_host(host: str) -> str:
    """Strip any scheme + trailing slash so we build exactly one clean URL."""
    h = (host or "").strip()
    for pfx in ("https://", "http://"):
        if h.lower().startswith(pfx):
            h = h[len(pfx):]
    return h.rstrip("/")


def build_fill_values(contract: dict, *, producer: str, producer_email: str,
                      webhook_url: str, bearer_present: bool, bearer_value: str):
    """From the contract's REQUIRED custom-value list, compute the concrete value to
    write for each key from the supplied per-client inputs. Returns (to_write,
    skipped): to_write is a list of dicts {key,name,value,secret}; skipped is a list
    of (key, reason). Contract-DRIVEN (never a hardcoded custom-value set) so it can
    never drift from what the snapshot ships."""
    required = ((contract.get("location_custom_values") or {}).get("required")) or []
    by_key = {}
    if producer:
        by_key["producer"] = producer
    if producer_email:
        by_key["producer_email"] = producer_email
    if webhook_url:
        by_key["anthology_webhook_url"] = webhook_url
    if bearer_present:
        by_key["anthology_hook_secret"] = "Bearer %s" % bearer_value

    to_write, skipped = [], []
    for cv in required:
        key = cv.get("key")
        name = cv.get("name") or key
        is_secret = bool(cv.get("secret"))
        if key in by_key:
            to_write.append({"key": key, "name": name, "value": by_key[key], "secret": is_secret})
        else:
            if key == "anthology_hook_secret":
                reason = ("ANTHOLOGY_INTAKE_HOOK_SECRET NOT SET in any env store yet "
                          "(export the step-7 0600 secret, then re-run to fill this custom value)")
            elif key == "anthology_webhook_url":
                reason = "no public hostname (pass --public-hostname or set ANTHOLOGY_PUBLIC_HOSTNAME)"
            elif key == "producer":
                reason = "no --producer supplied"
            elif key == "producer_email":
                reason = "no --producer-email supplied"
            else:
                reason = "no value supplied for this custom value"
            skipped.append((key, reason))
    return to_write, skipped


# ---------------------------------------------------------------------------
# provision-custom-values — idempotent GET-check + create-only-missing / update.
# ---------------------------------------------------------------------------
def provision_custom_values(client, location_id: str, contract: dict, *,
                            producer: str = "", producer_email: str = "",
                            webhook_url: str = "", bearer_present: bool = False,
                            bearer_value: str = "", require_secret: bool = False,
                            dry_run: bool = False, out=None, jsonout=None) -> int:
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    to_write, skipped = build_fill_values(
        contract, producer=producer, producer_email=producer_email,
        webhook_url=webhook_url, bearer_present=bearer_present, bearer_value=bearer_value)

    # A skipped SECRET under --require-live is a HELD deferral (never a false green):
    # the Authorization-header custom value cannot be filled until the label resolves.
    secret_skipped = any(k == "anthology_hook_secret" for k, _ in skipped)

    if dry_run:
        out.write("[snapshot custom-values] DRY RUN (marker %s): would fill %d custom value(s): %s. "
                  "Skipped %d: %s. No writes performed.\n"
                  % (masked, len(to_write), ", ".join(w["key"] for w in to_write) or "(none)",
                     len(skipped), "; ".join("%s (%s)" % (k, r) for k, r in skipped) or "(none)"))
        if jsonout is not None:
            json.dump({"ok": True, "dry_run": True, "location": masked,
                       "would_fill": [w["key"] for w in to_write],
                       "skipped": [{"key": k, "reason": r} for k, r in skipped]}, jsonout)
            jsonout.write("\n")
        if require_secret and secret_skipped:
            return EX_HELD
        return EX_OK

    # GET the location's existing custom values ONCE (idempotency index by name,
    # case-insensitive). The response can echo a value, so we never log it.
    try:
        existing = client.list_custom_values(location_id)
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ location custom values.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped PIT the customValues READ+WRITE scope.",
                   "AF-AE-SNAPSHOT-CV-SCOPE: STOP, never a silent skip."])
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[snapshot custom-values] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
        return EX_HELD

    index = {}
    for cv in existing:
        nm = cv.get("name")
        cid = cv.get("id") or cv.get("_id")
        if isinstance(nm, str) and cid:
            index[nm.strip().lower()] = cid

    created, updated = [], []
    for w in to_write:
        key, name, value, is_secret = w["key"], w["name"], w["value"], w["secret"]
        shown = "(secret; value not shown)" if is_secret else "set"
        cid = index.get(name.strip().lower())
        try:
            if cid:
                client.update_custom_value(location_id, cid, name, value)
                updated.append(key)
                out.write("[snapshot custom-values]   update %-24s -> %s\n" % (key, shown))
            else:
                client.create_custom_value(location_id, name, value)
                created.append(key)
                out.write("[snapshot custom-values]   create %-24s -> %s\n" % (key, shown))
        except reg.ScopeDenied:
            reg._stop(out, "The Convert and Flow token lacks customValues WRITE scope.",
                      ["Location marker: %s" % masked,
                       "Custom value that could not be written: %s" % key,
                       "Grant the client's OWN location-scoped PIT customValues WRITE scope and re-run.",
                       "AF-AE-SNAPSHOT-CV-SCOPE: STOP, never a silent skip."])
            return EX_STOP
        except reg.CafValidation as exc:
            reg._stop(out, "Convert and Flow rejected a custom-value write (%s)." % key,
                      ["Location marker: %s" % masked, "Detail: %s" % exc])
            return EX_MISMATCH
        except reg.CafUnreachable as exc:
            out.write("[snapshot custom-values] HELD after %d written: %s (marker %s). Retryable.\n"
                      % (len(created) + len(updated), exc, masked))
            return EX_HELD

    for key, reason in skipped:
        out.write("[snapshot custom-values]   skip   %-24s -> %s\n" % (key, reason))
    out.write("[snapshot custom-values] OK (marker %s): %d created, %d updated, %d skipped. "
              "Idempotent (GET-check + create-or-update).\n"
              % (masked, len(created), len(updated), len(skipped)))
    if jsonout is not None:
        json.dump({"ok": True, "location": masked, "created": created, "updated": updated,
                   "skipped": [{"key": k, "reason": r} for k, r in skipped]}, jsonout)
        jsonout.write("\n")
    if require_secret and secret_skipped:
        out.write("[snapshot custom-values] --require-live: the Authorization-header custom value "
                  "is UNFILLED (secret label not resolvable). HELD.\n")
        return EX_HELD
    return EX_OK


# ---------------------------------------------------------------------------
# verify-imported — READ-ONLY proof the snapshot landed (pipeline + fields).
# ---------------------------------------------------------------------------
def _contract_field_keys(contract: dict):
    return [f["intended_key"] for f in ((contract.get("custom_fields") or {}).get("fields") or [])]


def verify_imported(client, location_id: str, contract: dict, field_map: dict, *,
                    dry_run: bool = False, out=None, jsonout=None) -> int:
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    if dry_run:
        out.write("[snapshot verify] DRY RUN (marker %s): would READ pipelines + custom fields and "
                  "assert the '%s' pipeline + all %d contract fields are present (read-only).\n"
                  % (masked, ((contract.get("pipeline") or {}).get("name")),
                     len(_contract_field_keys(contract))))
        return EX_OK

    # The SOURCE OF TRUTH for the keys is field-map.json (the same file the engine
    # provisions from); the contract only mirrors it (and the drift gate proves the
    # two agree). Verify against the field-map so we can never assert a stale set.
    want_keys = [f["intended_key"] for f in (field_map.get("provisioning", {}).get("fields") or [])]
    pconf = field_map.get("pipeline", {})
    want_pipeline = pconf.get("standard_pipeline_name")
    want_stages = [s["name"] for s in (pconf.get("standard_stages") or [])]

    # ---- pipeline present BY NAME with every stage ----
    try:
        pipelines = client.list_pipelines(location_id)
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ pipelines on this location.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped PIT the opportunities scope.",
                   "AF-AE-PIT-SCOPE."])
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[snapshot verify] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
        return EX_HELD

    found = next((p for p in pipelines if p.get("name") == want_pipeline), None)
    if found is None:
        reg._stop(out, "The Anthology snapshot pipeline %r is ABSENT on this location." % want_pipeline,
                  ["Location marker: %s" % masked,
                   "The pipeline is UI/snapshot-only (GoHighLevel has no API to create a pipeline).",
                   "IMPORT the Anthology snapshot into THIS client's OWN Convert and Flow location "
                   "(Settings -> Snapshots -> Import/Load); see references/anthology-snapshot-guide.md.",
                   "AF-AE-SNAPSHOT-PIPELINE-MISSING."])
        return EX_STOP
    present_stages = {s.get("name") for s in (found.get("stages") or [])}
    missing_stages = [s for s in want_stages if s not in present_stages]
    if missing_stages:
        reg._stop(out, "The Anthology pipeline is present but is MISSING contract stage(s).",
                  ["Location marker: %s" % masked,
                   "Missing stage name(s): %s" % ", ".join(missing_stages),
                   "Re-import the current Anthology snapshot (the stage names are load-bearing).",
                   "AF-AE-SNAPSHOT-PIPELINE-STAGES."])
        return EX_MISMATCH

    # ---- every contract custom field present BY KEY ----
    try:
        fields = client.list_custom_fields(location_id)
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ custom fields on this location.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped PIT the customField READ scope.",
                   "AF-AE-PIT-SCOPE."])
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[snapshot verify] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
        return EX_HELD

    present_keys = {f.get("fieldKey") for f in fields}
    missing_fields = [k for k in want_keys if k not in present_keys]
    if missing_fields:
        reg._stop(out, "The snapshot import did not land %d contract custom field(s)." % len(missing_fields),
                  ["Location marker: %s" % masked,
                   "First missing key(s): %s" % ", ".join(missing_fields[:5]),
                   "Import the Anthology snapshot (it ships all %d fields), or let step 2 "
                   "(provision-fields) create them, then re-run." % len(want_keys),
                   "AF-AE-SNAPSHOT-FIELD-MISSING."])
        return EX_STOP

    out.write("[snapshot verify] OK (marker %s): pipeline %r present with all %d stages; "
              "all %d contract custom fields present by key.\n"
              % (masked, want_pipeline, len(want_stages), len(want_keys)))
    if jsonout is not None:
        json.dump({"ok": True, "location": masked, "pipeline": want_pipeline,
                   "stages_present": len(want_stages), "fields_present": len(want_keys)}, jsonout)
        jsonout.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# stamp-version — record which snapshot the box was provisioned from.
# ---------------------------------------------------------------------------
def stamp_version(contract: dict, state_dir: Path, *, dry_run: bool = False, out=None) -> int:
    out = out or sys.stderr
    marker = state_dir / "snapshot-version.json"
    payload = {
        "contract": "anthology-engine-snapshot-version-marker",
        "schema_version": 1,
        "snapshot_version": contract.get("snapshot_version"),
        "template_location_id": ((contract.get("source_template_location") or {}).get("template_location_id")),
        "stamped_at": reg._now_iso(),
    }
    if dry_run:
        out.write("[snapshot stamp] DRY RUN: would write %s (snapshot_version=%s).\n"
                  % (marker, payload["snapshot_version"]))
        return EX_OK
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".snapver.", suffix=".json.tmp", dir=str(state_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.chmod(tmp, 0o644)
            os.replace(tmp, str(marker))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001
        out.write("[snapshot stamp] ERROR writing %s: %s\n" % (marker, type(exc).__name__))
        return EX_ERR
    out.write("[snapshot stamp] OK: %s (snapshot_version=%s).\n" % (marker, payload["snapshot_version"]))
    return EX_OK


# ---------------------------------------------------------------------------
# plan — offline summary (no network).
# ---------------------------------------------------------------------------
def plan(contract: dict, field_map: dict, *, out=None) -> int:
    out = out or sys.stdout
    pl = contract.get("pipeline") or {}
    cv = (contract.get("location_custom_values") or {}).get("required") or []
    fields = _contract_field_keys(contract)
    out.write("ANTHOLOGY SNAPSHOT — IMPORT/LOAD PLAN (offline)\n")
    out.write("  snapshot_version: %s\n" % contract.get("snapshot_version"))
    out.write("  cut-from template location: %s\n"
              % ((contract.get("source_template_location") or {}).get("template_location_id")))
    out.write("  MANUAL IMPORT: Settings -> Snapshots -> Import/Load into the client's OWN location\n")
    out.write("  pipeline (UI/snapshot-only): %r with %d stages: %s\n"
              % (pl.get("name"), len(pl.get("stages") or []),
                 ", ".join(s["name"] for s in (pl.get("stages") or []))))
    out.write("  custom fields verified by key: %d\n" % len(fields))
    out.write("  per-client custom VALUES filled here (REPLACE-ME placeholders in the snapshot):\n")
    for c in cv:
        out.write("    - %-24s (%s)\n"
                  % (c.get("key"), "SECRET; value never printed" if c.get("secret") else "not secret"))
    out.write("  rejected mechanism (recorded): agency->subaccount API auto-push "
              "(each-client-owns-their-own-GHL topology)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# self-test — offline; fake clients; no network, no real writes outside a temp dir.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """A minimal in-memory LeadConnector stub covering exactly the snapshot surface."""

    def __init__(self, *, pipelines=None, fields=None, cv_read=True, cv_write=True):
        self._pipelines = pipelines if pipelines is not None else []
        self._fields = fields if fields is not None else []
        self._cv_read = cv_read
        self._cv_write = cv_write
        self.values = {}  # id -> {name,value}
        self._seq = 0

    def list_pipelines(self, location_id):
        return list(self._pipelines)

    def list_custom_fields(self, location_id):
        return list(self._fields)

    def list_custom_values(self, location_id):
        if not self._cv_read:
            raise reg.ScopeDenied("no customValues read scope")
        return [{"id": k, "name": v["name"], "value": v["value"]} for k, v in self.values.items()]

    def create_custom_value(self, location_id, name, value):
        if not self._cv_write:
            raise reg.ScopeDenied("no customValues write scope")
        self._seq += 1
        cid = "cv-%d" % self._seq
        self.values[cid] = {"name": name, "value": value}
        return {"id": cid, "name": name}

    def update_custom_value(self, location_id, cv_id, name, value):
        if not self._cv_write:
            raise reg.ScopeDenied("no customValues write scope")
        self.values[cv_id] = {"name": name, "value": value}
        return {"id": cv_id, "name": name}


def _fixture_pipeline(contract, *, drop_stage=None):
    pl = contract["pipeline"]
    stages = [{"name": s["name"], "id": "stg-%d" % s["position"]}
              for s in pl["stages"] if s["name"] != drop_stage]
    return {"id": "pipe-1", "name": pl["name"], "stages": stages}


def _fixture_fields(field_map, *, drop=None):
    out = []
    for f in field_map["provisioning"]["fields"]:
        if f["intended_key"] == drop:
            continue
        out.append({"fieldKey": f["intended_key"], "id": "fld-%s" % f["create_name"]})
    return out


def self_test() -> int:
    import io
    dev = io.StringIO()
    contract = load_contract(CONTRACT_PATH)
    field_map = reg.load_field_map(FIELD_MAP_PATH)

    # -- contract mirrors the field-map (defense-in-depth; the real gate is the drift
    #    gate, but the module refuses to run on a self-inconsistent pair) -----------
    c_keys = _contract_field_keys(contract)
    fm_keys = [f["intended_key"] for f in field_map["provisioning"]["fields"]]
    assert c_keys == fm_keys, "contract custom_fields drifted from field-map provisioning.fields"
    assert (contract["pipeline"]["name"] == field_map["pipeline"]["standard_pipeline_name"]), \
        "contract pipeline name drifted from field-map"
    assert ([s["name"] for s in contract["pipeline"]["stages"]]
            == [s["name"] for s in field_map["pipeline"]["standard_stages"]]), \
        "contract pipeline stages drifted from field-map"

    # -- build_fill_values: contract-driven, secret formatted as Bearer, skips noted --
    to_write, skipped = build_fill_values(
        contract, producer="Jane Doe", producer_email="jane@example.com",
        webhook_url="https://box.example.com/hooks/anthology-intake",
        bearer_present=True, bearer_value="SEKRIT")
    wk = {w["key"]: w for w in to_write}
    assert set(wk) == {"anthology_webhook_url", "anthology_hook_secret", "producer", "producer_email"}, wk
    assert wk["anthology_hook_secret"]["value"] == "Bearer SEKRIT" and wk["anthology_hook_secret"]["secret"]
    assert skipped == [], skipped
    # missing secret + hostname -> those two skipped, the rest still written
    to_write2, skipped2 = build_fill_values(
        contract, producer="J", producer_email="", webhook_url="",
        bearer_present=False, bearer_value="")
    sk = {k for k, _ in skipped2}
    assert "anthology_hook_secret" in sk and "anthology_webhook_url" in sk and "producer_email" in sk, sk
    assert {w["key"] for w in to_write2} == {"producer"}

    # -- provision_custom_values: create-then-update idempotency, secret never printed --
    caf = _FakeCaf()
    rc = provision_custom_values(
        caf, "loc_QcDX", contract, producer="Jane Doe", producer_email="jane@example.com",
        webhook_url="https://box.example.com/hooks/anthology-intake",
        bearer_present=True, bearer_value="SEKRIT", out=dev)
    assert rc == EX_OK and len(caf.values) == 4, "expected 4 custom values created, got %d" % len(caf.values)
    # the secret value must NEVER appear on the operator surface
    assert "SEKRIT" not in dev.getvalue(), "SECRET VALUE LEAKED to the operator surface"
    # re-run -> all UPDATE, still 4 (idempotent, no duplicates)
    rc = provision_custom_values(
        caf, "loc_QcDX", contract, producer="Jane Doe", producer_email="jane@example.com",
        webhook_url="https://box.example.com/hooks/anthology-intake",
        bearer_present=True, bearer_value="SEKRIT2", out=dev)
    assert rc == EX_OK and len(caf.values) == 4, "idempotent re-run must not duplicate custom values"
    assert "SEKRIT2" not in dev.getvalue(), "SECRET VALUE LEAKED on update"
    # write-scope denied -> STOP
    rc = provision_custom_values(
        _FakeCaf(cv_write=False), "loc_QcDX", contract, producer="X",
        out=dev)
    assert rc == EX_STOP, "no customValues write scope must STOP exit 2, got %s" % rc
    # --require-live with an unresolved secret -> HELD (never false green)
    rc = provision_custom_values(
        _FakeCaf(), "loc_QcDX", contract, producer="X", producer_email="x@example.com",
        webhook_url="https://h/hooks/anthology-intake", bearer_present=False,
        require_secret=True, out=dev)
    assert rc == EX_HELD, "require-live + unresolved secret must HELD, got %s" % rc
    # dry-run performs no writes
    caf_d = _FakeCaf()
    rc = provision_custom_values(caf_d, "loc_QcDX", contract, producer="X", dry_run=True, out=dev)
    assert rc == EX_OK and not caf_d.values, "dry-run must not write"

    # -- verify_imported: present -> OK; pipeline absent -> STOP; stage/field gaps ----
    good = _FakeCaf(pipelines=[_fixture_pipeline(contract)], fields=_fixture_fields(field_map))
    assert verify_imported(good, "loc_QcDX", contract, field_map, out=dev) == EX_OK
    nopipe = _FakeCaf(pipelines=[], fields=_fixture_fields(field_map))
    assert verify_imported(nopipe, "loc_QcDX", contract, field_map, out=dev) == EX_STOP, "absent pipeline must STOP"
    badstage = _FakeCaf(pipelines=[_fixture_pipeline(contract, drop_stage="Cover")],
                        fields=_fixture_fields(field_map))
    assert verify_imported(badstage, "loc_QcDX", contract, field_map, out=dev) == EX_MISMATCH, "missing stage -> 5"
    nofield = _FakeCaf(pipelines=[_fixture_pipeline(contract)],
                       fields=_fixture_fields(field_map, drop="contact.anthology_cover_choice"))
    assert verify_imported(nofield, "loc_QcDX", contract, field_map, out=dev) == EX_STOP, "missing field must STOP"

    # -- stamp_version writes a marker ------------------------------------------------
    td = Path(tempfile.mkdtemp(prefix="ae-snap-"))
    assert stamp_version(contract, td, out=dev) == EX_OK
    marker = json.load(open(td / "snapshot-version.json", encoding="utf-8"))
    assert marker["snapshot_version"] == contract["snapshot_version"]
    assert marker["template_location_id"] == contract["source_template_location"]["template_location_id"]

    print("anthology_snapshot self-test: OK "
          "(contract<->field-map coherence, contract-driven fill, create/update idempotency, "
          "secret never printed, scope STOP, require-live HELD, verify pipeline/stage/field, stamp-version)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="anthology_snapshot.py",
        description="Convert and Flow snapshot import verify + custom-value fill + version stamp (Skill 59).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for verify keys)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--location-id", default="", help="override the Convert and Flow location id")
    ap.add_argument("--state-dir", default="", help="override the engine state dir (snapshot-version marker)")
    ap.add_argument("--producer", default="", help="producer (box owner) display name")
    ap.add_argument("--producer-email", default="", help="producer email")
    ap.add_argument("--public-hostname", default="",
                    help="the box's public hostname for the intake webhook URL (never a secret)")
    ap.add_argument("--webhook-url", default="",
                    help="override the full intake webhook URL (else built from --public-hostname + route_path)")
    ap.add_argument("--require-live", action="store_true",
                    help="an unfilled Authorization-header custom value (secret label NOT SET) is HELD, not deferred")
    ap.add_argument("--dry-run", action="store_true", help="plan writes without performing them / no network")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["provision-custom-values", "verify-imported",
                                    "stamp-version", "plan", "self-test"])

    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()

        contract = load_contract(Path(args.contract).expanduser())

        if args.cmd == "plan":
            field_map = reg.load_field_map(Path(args.field_map).expanduser())
            return plan(contract, field_map)

        if args.cmd == "stamp-version":
            state_dir = Path(args.state_dir).expanduser() if args.state_dir else reg.default_state_dir()
            return stamp_version(contract, state_dir, dry_run=args.dry_run)

        # ---- commands that need the live client (unless --dry-run) ----
        if args.dry_run:
            # No network in dry-run: use a masked placeholder location so surfaces read.
            masked_loc = args.location_id or "DRYRUN"
            if args.cmd == "verify-imported":
                field_map = reg.load_field_map(Path(args.field_map).expanduser())
                return verify_imported(None, masked_loc, contract, field_map,
                                       dry_run=True, jsonout=jsonout)
            if args.cmd == "provision-custom-values":
                host = _norm_host(resolve_public_hostname(args.public_hostname))
                webhook = args.webhook_url.strip() or (
                    "https://%s%s" % (host, (contract.get("intake") or {}).get("route_path", "")) if host else "")
                slabel, _sval = resolve_hook_secret()
                return provision_custom_values(
                    None, masked_loc, contract, producer=args.producer,
                    producer_email=args.producer_email, webhook_url=webhook,
                    bearer_present=bool(slabel), bearer_value="",
                    require_secret=args.require_live, dry_run=True, jsonout=jsonout)

        client, loc_or_rc = reg._live_client(args.location_id)
        if client is None:
            return loc_or_rc
        location_id = loc_or_rc

        if args.cmd == "verify-imported":
            field_map = reg.load_field_map(Path(args.field_map).expanduser())
            return verify_imported(client, location_id, contract, field_map, jsonout=jsonout)

        if args.cmd == "provision-custom-values":
            host = _norm_host(resolve_public_hostname(args.public_hostname))
            route_path = (contract.get("intake") or {}).get("route_path", "")
            webhook = args.webhook_url.strip() or (("https://%s%s" % (host, route_path)) if host else "")
            slabel, sval = resolve_hook_secret()
            return provision_custom_values(
                client, location_id, contract, producer=args.producer,
                producer_email=args.producer_email, webhook_url=webhook,
                bearer_present=bool(sval), bearer_value=(sval or ""),
                require_secret=args.require_live, jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        sys.stderr.write("[anthology_snapshot] file not found: %s\n" % exc)
        return EX_ERR
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[anthology_snapshot] unexpected error: %s\n" % type(exc).__name__)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
