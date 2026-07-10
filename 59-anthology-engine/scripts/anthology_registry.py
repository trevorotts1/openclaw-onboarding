#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: anthology_registry.py
# PER-ANTHOLOGY BINDINGS + CONVERT AND FLOW AUTO-PROVISIONING (SPEC 3.4 row 3;
# PRD Gap 9; W0.5.json surface 5). Manifest exit-code line: "0; 2 unknown
# anthology or binding; 5 validation" — refined below with the house 1/3 codes.
# -----------------------------------------------------------------------------
# WHAT THIS OWNS
#   1. BIND the STANDARD Anthology pipeline in the CLIENT's OWN Convert and Flow
#      account using the CLIENT's OWN private-integration token. GoHighLevel /
#      Convert and Flow exposes NO public v2 API to CREATE a pipeline -- pipelines
#      are UI-only (confirmed against the official v2 API spec and the Skill 29
#      413-endpoint reference). So this module is FIND-AND-BIND, never auto-create:
#      it READS the location's pipelines, finds the standard one BY NAME, and
#      persists its id + stage ids. If the standard pipeline is ABSENT it STOPS
#      with an operator surface (AF-AE-PIPELINE-UI-CREATE) instructing a one-time
#      creation in the Convert and Flow UI (or an explicit pre-existing bind via
#      `bind --pipeline-id`) -- NEVER a silent fallback and NEVER a call to a
#      nonexistent create endpoint. A token that cannot even READ pipelines STOPS
#      with AF-AE-PIT-SCOPE.
#   2. CREATE-OR-VERIFY each PRD Section 6 contact custom field, then persist the
#      SERVER-RETURNED fieldKey (and the field id the runtime write needs) into
#      config/field-map.json with an EXACT-MATCH verify. A fieldKey that does not
#      byte-equal its intended PRD key STOPS setup (AF-AE-FIELD-KEY-MISMATCH).
#   3. PER-ANTHOLOGY bindings: bind an anthology_id to its pipeline, its
#      caf_stage_map (engine stage -> resolved pipeline stage id, NEVER
#      hardcoded — SPEC M8), its Convert and Flow Location (the intake tenant
#      check), its form ids, and its Drive folder. Bindings are per-box config,
#      stored under the engine state dir; they are NOT committed and are NOT
#      participant ledger rows (anthology_state.py remains the SOLE ledger
#      writer — this module never writes the base directly).
#
# EXIT CODE CONTRACT (house convention; manifest row 3 is the subset 0/2/5):
#   0  verified success (INCLUDING an idempotent create-or-verify no-op / dry run)
#   1  unexpected error
#   2  STOP-setup guard refusal — PIT/Location label NOT SET, resolved value is
#      not a pit- token, the token cannot READ pipelines, the standard pipeline is
#      absent (UI-only; there is no API create endpoint), or an unknown
#      anthology/binding. Emits a LOUD operator surface; never silent.
#   3  Convert and Flow API unreachable / dependency held (retryable; the daily
#      tick or a re-run resumes; nothing half-written is relied upon)
#   5  validation or EXACT-MATCH mismatch — a server fieldKey != its intended PRD
#      key, a --confirm-name mismatch, or a malformed bind (NOTHING is stamped)
#
# The setup STOP families map for provision-anthology-client.sh (W2.6):
#   exit 2  ->  AF-AE-PIT-SCOPE (token cannot read pipelines) /
#              AF-AE-PIPELINE-UI-CREATE (standard pipeline absent; UI-only) /
#              label-not-set STOP
#   exit 5  ->  AF-AE-FIELD-KEY-MISMATCH / AF-AE-FIELD-MISSING
# py_symbols the manifest binds live here: probe_write_scope, verify_fields.
#
# STDLIB ONLY (urllib + json). Calls NO model. Convert and Flow is a white-label
# LeadConnector v2 instance (api base services.leadconnectorhq.com, Version
# header 2021-07-28) per W0.5. DOCTRINE: move in silence (operator-verbose only);
# NOTHING Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value (labels resolve SET / NOT SET only); config
# and state writes run as the node user, never root.
# =============================================================================
"""anthology_registry.py — Convert and Flow provisioning + per-anthology bindings."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# W0.6 (cover_render.py): services.leadconnectorhq.com is Cloudflare-fronted and
# 403s urllib's default "Python-urllib/x.y" User-Agent at the WAF edge (CF error
# 1010) BEFORE the request ever reaches Convert and Flow -- so a browser User-Agent
# is REQUIRED on every request here too. Reuse the SINGLE constant of record rather
# than re-typing the string (the sibling-import convention already used for the
# delivery_report import in caf_delivery.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cover_render import MOZILLA_UA  # noqa: E402  (sibling import after path bootstrap)

# ---- exit codes -------------------------------------------------------------
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5

# ---- layout -----------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# ---- Convert and Flow (LeadConnector v2) surface, verified at W0.5 ----------
CAF_API_BASE = "https://services.leadconnectorhq.com"
CAF_VERSION_HEADER = "2021-07-28"

# The CLIENT's OWN standard credential labels, resolved across the client env
# stores (live process env first) via the shared alias resolver. ONLY the
# client's own standard labels appear here — NEVER an agency/company token and
# NEVER a client-name-prefixed label (never-touch-client-credentials doctrine).
PIT_LABELS = ("CONVERT_AND_FLOW_PIT", "GOHIGHLEVEL_API_KEY", "GHL_API_KEY")
LOCATION_LABELS = ("CONVERT_AND_FLOW_LOCATION_ID", "GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID")
PIT_PREFIX = "pit-"  # PRD Section 14: the private integration token prefix


# ---------------------------------------------------------------------------
# Environment / credential resolution. SET / NOT SET only; values never printed.
# ---------------------------------------------------------------------------
def default_state_dir() -> Path:
    """The engine state directory (owned by the node user). Mirrors
    anthology_state.py so both agree on where per-box state lives."""
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def _env_first(names):
    """First present, non-empty env value among `names`. Returns (name, value)
    or (None, None). NEVER prints the value (doctrine: SET / NOT SET only)."""
    for n in names:
        v = os.environ.get(n, "")
        if v and v.strip():
            return n, v.strip()
    return None, None


def _mask_location(loc: str) -> str:
    """A non-reversible marker for a location id: last 4 chars only."""
    loc = (loc or "").strip()
    return ("..." + loc[-4:]) if len(loc) >= 4 else "...(short)"


def resolve_pit():
    """Resolve the client's OWN Convert and Flow private-integration token.
    Returns (label, token) or (None, None). Validates the pit- prefix so a
    placeholder or a mis-set value is refused. The token value is NEVER printed."""
    label, token = _env_first(PIT_LABELS)
    if not token:
        return None, None
    if not token.startswith(PIT_PREFIX):
        # Resolved a value under a PIT label, but it is not a pit- token. Refuse
        # WITHOUT printing it. The caller STOPs setup.
        return label, None
    return label, token


def resolve_location(override: str = ""):
    if override and override.strip():
        return "(--location-id)", override.strip()
    return _env_first(LOCATION_LABELS)


# ---------------------------------------------------------------------------
# Convert and Flow REST client. STDLIB urllib only. Never logs the token or a
# response body (either could echo a credential). Distinguishes scope-denied
# (401/403), validation (400/422), and unreachable (everything else / transport).
# ---------------------------------------------------------------------------
class ScopeDenied(Exception):
    """A GENUINE Convert and Flow scope denial: the response BODY matched the W0.5
    signature "The token is not authorized for this scope." (never a bare HTTP
    401/403 status -- a Cloudflare/WAF edge block also carries a 403)."""


class CafValidation(Exception):
    """The API rejected the request as invalid (4xx that is not auth/scope)."""


class CafUnreachable(Exception):
    """Transport failure or a server error; the op is retryable / held."""


class UpstreamBlockedError(CafUnreachable):
    """A 401/403 whose body did NOT match a genuine scope-denial signature -- e.g.
    a Cloudflare/WAF edge block (CF error 1010) that 403s the request AT THE EDGE,
    before it ever reaches Convert and Flow's scope check. Kept DISTINCT from
    ScopeDenied (and, as a CafUnreachable subclass, treated as retryable/HELD by
    every caller) so an edge block is NEVER misdiagnosed as a missing token scope
    -- the exact Wave 5 false positive this guards against. The token scope is
    UNDETERMINED here, not proven absent."""


# The one fixed substring that identifies a GENUINE Convert and Flow (LeadConnector
# v2) scope denial, verified live: a JSON body {"message": "The token is not
# authorized for this scope."} on an auth-scoped endpoint. A Cloudflare edge block
# carries no such JSON (it is an HTML challenge page / CF 1010), so it fails this
# test and is classified as an upstream block instead.
_SCOPE_DENIAL_SIGNATURE = "not authorized for this scope"


def _auth_denial_kind(raw) -> str:
    """Classify a 401/403 response BODY as "scope" (a genuine Convert and Flow
    scope denial) or "blocked" (a Cloudflare/WAF edge block or any other non-scope
    401/403). Inspects the body, never the bare status. The raw bytes are never
    surfaced; only the fixed signature substring is matched."""
    try:
        text = (raw or b"").decode("utf-8", "replace")
    except Exception:
        return "blocked"
    stripped = text.lstrip()
    # An HTML / non-JSON body (a Cloudflare challenge page, a WAF interstitial, an
    # empty body) is never a Convert and Flow JSON scope denial.
    if not stripped or stripped[0] == "<":
        return "blocked"
    try:
        obj = json.loads(text)
    except Exception:
        return "blocked"
    if isinstance(obj, dict):
        for k in ("message", "error", "msg"):
            v = obj.get(k)
            if isinstance(v, str) and _SCOPE_DENIAL_SIGNATURE in v.lower():
                return "scope"
    return "blocked"


class CafClient:
    """Thin LeadConnector v2 client covering exactly the provisioning surface."""

    def __init__(self, token: str, timeout: int = 15):
        self._token = token
        self._timeout = timeout

    def _request(self, method: str, path: str, query=None, body=None):
        url = CAF_API_BASE + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": "Bearer %s" % self._token,
            "Version": CAF_VERSION_HEADER,
            "Accept": "application/json",
            # W0.6: the Cloudflare edge fronting services.leadconnectorhq.com 403s
            # urllib's default UA (CF 1010) before the request reaches Convert and
            # Flow. A browser UA is REQUIRED for the request to be scope-checked.
            "User-Agent": MOZILLA_UA,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code in (401, 403):
                # A bare 401/403 is NOT proof of a scope problem: the Cloudflare
                # edge fronting services.leadconnectorhq.com returns 403 (CF 1010)
                # for a blocked request BEFORE it ever reaches the scope check.
                # Inspect the BODY and only call it a scope denial when it matches
                # the genuine W0.5 signature; otherwise it is an upstream/edge block.
                body = b""
                try:
                    body = exc.read()
                except Exception:
                    body = b""
                if _auth_denial_kind(body) == "scope":
                    # NEVER surface the body verbatim (it could echo a credential);
                    # we matched only the fixed signature substring.
                    raise ScopeDenied("token not authorized for this scope (HTTP %s)" % code)
                raise UpstreamBlockedError(
                    "HTTP %s did NOT match a Convert and Flow scope-denial signature "
                    "-- likely a Cloudflare/WAF edge block (verify the browser "
                    "User-Agent), NOT a token-scope problem" % code)
            if code in (400, 409, 422):
                raise CafValidation("Convert and Flow rejected the request (HTTP %s)" % code)
            raise CafUnreachable("Convert and Flow HTTP %s on %s" % (code, method))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise CafUnreachable("Convert and Flow transport error: %s" % type(exc).__name__)

    # ---- pipelines (READ-ONLY) -------------------------------------------
    # GoHighLevel / Convert and Flow exposes NO public v2 API to CREATE or DELETE
    # a pipeline -- pipelines are UI-only. The engine binds an EXISTING pipeline by
    # name (provision_pipeline) and probes READ access (probe_write_scope); it
    # never calls a nonexistent create/delete endpoint. Listing is the only
    # pipeline surface the v2 API provides.
    def list_pipelines(self, location_id: str):
        out = self._request("GET", "/opportunities/pipelines", query={"locationId": location_id})
        return out.get("pipelines") or []

    # ---- custom fields ----------------------------------------------------
    def list_custom_fields(self, location_id: str):
        out = self._request("GET", "/locations/%s/customFields" % urllib.parse.quote(location_id, safe=""))
        return out.get("customFields") or []

    def create_custom_field(self, location_id: str, name: str, data_type: str, options=None):
        body = {"name": name, "dataType": data_type, "model": "contact"}
        # SINGLE_OPTIONS (and the sibling picklist types) require their options on
        # create -- e.g. the U8 anthology_cover_choice field, whose four options are
        # the named cover-style names the client picks from in the universal-review
        # dropdown. TEXT/LARGE_TEXT fields carry none.
        if options and data_type in ("SINGLE_OPTIONS", "MULTIPLE_OPTIONS", "RADIO", "CHECKBOX"):
            body["options"] = list(options)
        out = self._request("POST", "/locations/%s/customFields" % urllib.parse.quote(location_id, safe=""),
                            body=body)
        return out.get("customField") or out


# ---------------------------------------------------------------------------
# fieldKey derivation law (verified at W0.5). The API DERIVES the fieldKey; it is
# not accepted on create. We create with name = the intended key minus the
# leading "contact." and then assert the server echoed "contact.<name>".
# ---------------------------------------------------------------------------
_KEY_PREFIX = "contact."


def create_name_of(intended_key: str) -> str:
    return intended_key[len(_KEY_PREFIX):] if intended_key.startswith(_KEY_PREFIX) else intended_key


def derive_field_key(create_name: str) -> str:
    return _KEY_PREFIX + create_name


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# field-map.json IO. The committed template ships with every resolved slot null;
# provisioning stamps the resolved slots IN PLACE, as the node user, per box.
# ---------------------------------------------------------------------------
def load_field_map(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_field_map(path: Path, data: dict) -> None:
    # Atomic write (temp + replace) so a crash never leaves a half-written map.
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent),
                                      prefix=".field-map.", suffix=".tmp", delete=False)
    try:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, str(path))


def _stop(out, title: str, lines) -> None:
    """A LOUD operator STOP surface (stderr). Never silent, never a secret."""
    out.write("\n")
    out.write("================ ANTHOLOGY ENGINE :: SETUP STOP ================\n")
    out.write("  %s\n" % title)
    for ln in lines:
        out.write("    - %s\n" % ln)
    out.write("  Setup is STOPPED. Resolve the above, then re-run. Never a silent fallback.\n")
    out.write("===============================================================\n")


# ---------------------------------------------------------------------------
# PROVISIONING: custom fields (create-or-verify + exact-match + persist).
# ---------------------------------------------------------------------------
def provision_fields(client, field_map_path: Path, location_id: str, *,
                     dry_run: bool = False, out=None, jsonout=None):
    """py_symbol: verify_fields. Create-or-verify all 28 fields (the 19 base PRD
    Section 6 link/control keys + the 4 chapter-rewrite-preservation keys, Gap G10 +
    the 5 U8 cover-style keys); every free-text key is LARGE_TEXT (Gap G11) and the
    lone cover-choice key is SINGLE_OPTIONS. Exact-match verify each server fieldKey,
    and persist into field-map.json. Returns an exit code."""
    out = out or sys.stderr
    fm = load_field_map(field_map_path)
    inventory = fm.get("provisioning", {}).get("fields")
    if not isinstance(inventory, list) or not inventory:
        _stop(out, "field-map.json has no provisioning.fields inventory", [str(field_map_path)])
        return EX_MISMATCH
    masked = _mask_location(location_id)

    # Existing fields on the location, keyed by their fieldKey (idempotency).
    if not dry_run:
        try:
            existing_list = client.list_custom_fields(location_id)
        except ScopeDenied:
            _stop(out, "The Convert and Flow token cannot READ custom fields on this location.",
                  ["Location marker: %s" % masked,
                   "Grant the location-scoped token contacts/custom-field READ+WRITE scope.",
                   "AF-AE-FIELD-MISSING family: STOP, never a silent runtime create."])
            return EX_STOP
        except CafUnreachable as exc:
            out.write("[provision-fields] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
            return EX_HELD
        existing = {}
        for f in existing_list:
            fk = f.get("fieldKey")
            if fk:
                existing[fk] = f
    else:
        existing = {}

    verified, created, planned_create, mismatches = [], [], [], []

    for item in inventory:
        intended = item["intended_key"]
        cname = item["create_name"]
        # Default LARGE_TEXT (PRD Gap G11): live Convert and Flow provisions every
        # anthology free-text field as LARGE_TEXT, and the multi-line law requires it.
        # Every inventory row carries an explicit data_type; this default only bites a
        # malformed row, and it must match reality (LARGE_TEXT), never the old TEXT.
        dtype = item.get("data_type", "LARGE_TEXT")
        # Contract sanity: the create_name must derive back to the intended key.
        if derive_field_key(cname) != intended:
            mismatches.append((intended, "create_name %r does not derive to the intended key" % cname))
            continue

        if intended in existing:
            fobj = existing[intended]
            item["field_key"] = intended
            item["field_id"] = fobj.get("id")
            item["verified_at"] = _now_iso()
            item["location_masked"] = masked
            verified.append(intended)
            continue

        if dry_run:
            planned_create.append(intended)
            continue

        try:
            resp = client.create_custom_field(location_id, cname, dtype, options=item.get("options"))
        except ScopeDenied:
            _stop(out, "The Convert and Flow token lacks custom-field WRITE scope.",
                  ["Location marker: %s" % masked,
                   "Field that could not be created: %s" % intended,
                   "Grant the location-scoped token custom-field WRITE scope and re-run.",
                   "AF-AE-FIELD-MISSING: STOP, never a silent runtime create."])
            return EX_STOP
        except CafValidation as exc:
            mismatches.append((intended, "create rejected: %s" % exc))
            continue
        except CafUnreachable as exc:
            out.write("[provision-fields] HELD after %d verified: %s (marker %s). Retryable.\n"
                      % (len(verified) + len(created), exc, masked))
            return EX_HELD

        server_key = resp.get("fieldKey")
        if server_key != intended:
            mismatches.append((intended, "server fieldKey %r != intended (derivation law changed)" % server_key))
            continue
        item["field_key"] = server_key
        item["field_id"] = resp.get("id")
        item["verified_at"] = _now_iso()
        item["location_masked"] = masked
        created.append(intended)

    if dry_run:
        out.write("[provision-fields] DRY RUN (marker %s): %d already present/verifiable-by-key, "
                  "%d would be created. No writes performed.\n"
                  % (masked, len(verified), len(planned_create)))
        if jsonout is not None:
            json.dump({"ok": True, "dry_run": True, "location": masked,
                       "already_present": verified, "would_create": planned_create}, jsonout)
            jsonout.write("\n")
        return EX_OK

    if mismatches:
        _stop(out, "EXACT-MATCH verify FAILED for one or more custom fields (AF-AE-FIELD-KEY-MISMATCH).",
              ["%s  ->  %s" % (k, why) for k, why in mismatches]
              + ["NOTHING was stamped into field-map.json. Setup STOPPED."])
        if jsonout is not None:
            json.dump({"ok": False, "reason": "field_key_mismatch",
                       "mismatches": [{"key": k, "why": w} for k, w in mismatches]}, jsonout)
            jsonout.write("\n")
        return EX_MISMATCH

    # All 24 resolved. Stamp in place.
    save_field_map(field_map_path, fm)
    out.write("[provision-fields] OK (marker %s): %d newly created, %d verified-by-key, %d total resolved. "
              "field-map.json stamped.\n" % (masked, len(created), len(verified), len(verified) + len(created)))
    if jsonout is not None:
        json.dump({"ok": True, "location": masked, "created": created, "verified": verified,
                   "total_resolved": len(verified) + len(created)}, jsonout)
        jsonout.write("\n")
    return EX_OK


def verify_fields_resolved(field_map_path: Path, *, out=None) -> int:
    """READ-ONLY: assert every inventory field is resolved (field_key + field_id
    present) and that each field_key byte-equals its intended key. For verify.sh.
    exit 0 all resolved+exact; exit 5 any unresolved-or-mismatch."""
    out = out or sys.stderr
    fm = load_field_map(field_map_path)
    inventory = fm.get("provisioning", {}).get("fields") or []
    unresolved, mism = [], []
    for item in inventory:
        intended = item["intended_key"]
        if not item.get("field_key") or not item.get("field_id"):
            unresolved.append(intended)
            continue
        if item.get("field_key") != intended:
            mism.append(intended)
    if unresolved or mism:
        out.write("[verify-fields] NOT resolved: %d unresolved, %d mismatched (of %d).\n"
                  % (len(unresolved), len(mism), len(inventory)))
        for k in unresolved:
            out.write("    unresolved: %s\n" % k)
        for k in mism:
            out.write("    mismatch:   %s\n" % k)
        return EX_MISMATCH
    out.write("[verify-fields] OK: all %d fields resolved and exact-match.\n" % len(inventory))
    return EX_OK


# ---------------------------------------------------------------------------
# PROVISIONING: the standard pipeline (read-probe -> find-by-name -> bind/persist).
# Pipelines are UI-only in GoHighLevel/Convert and Flow; there is no create call.
# ---------------------------------------------------------------------------
def _find_pipeline(pipelines, name: str):
    for p in pipelines:
        if p.get("name") == name:
            return p
    return None


def _stage_id_map(pipeline: dict) -> dict:
    out = {}
    for s in pipeline.get("stages") or []:
        if s.get("name") and s.get("id"):
            out[s["name"]] = s["id"]
    return out


def probe_write_scope(client, location_id: str, *, dry_run: bool = False, out=None, jsonout=None):
    """py_symbol: probe_write_scope. Pipeline PRE-FLIGHT (read-based).

    GoHighLevel / Convert and Flow exposes NO public v2 API to CREATE a pipeline
    (pipelines are UI-only), so this is deliberately NOT a create-feasibility probe.
    It verifies the client's OWN token can READ pipelines on the location -- which
    proves (a) the opportunities scope is granted and (b) the request reaches
    Convert and Flow past the Cloudflare edge (a WAF block surfaces as
    UpstreamBlockedError -> HELD, never a scope STOP). exit 0 readable; exit 2 the
    token cannot read pipelines (genuine scope STOP, AF-AE-PIT-SCOPE); exit 3
    unreachable or an upstream/edge block (undetermined; retryable)."""
    out = out or sys.stderr
    masked = _mask_location(location_id)
    if dry_run:
        out.write("[probe-scope] DRY RUN (marker %s): would READ the location pipelines "
                  "(read-only; no write, no create -- pipelines are UI-only).\n" % masked)
        return EX_OK
    try:
        pipelines = client.list_pipelines(location_id)
    except ScopeDenied:
        _stop(out, "The Convert and Flow token cannot READ pipelines/opportunities on this location (AF-AE-PIT-SCOPE).",
              ["Location marker: %s" % masked,
               "Grant the client's OWN location-scoped token the opportunities scope and re-run.",
               "Setup STOPPED; never a silent fallback."])
        if jsonout is not None:
            json.dump({"ok": False, "scope": "absent", "reason": "pit_scope"}, jsonout)
            jsonout.write("\n")
        return EX_STOP
    except UpstreamBlockedError as exc:
        out.write("[probe-scope] HELD: %s (marker %s). NOT a token-scope problem; retryable.\n" % (exc, masked))
        return EX_HELD
    except CafUnreachable as exc:
        out.write("[probe-scope] HELD: %s (marker %s). Read scope undetermined; retryable.\n" % (exc, masked))
        return EX_HELD

    out.write("[probe-scope] OK: the token can READ %d pipeline(s) on this location (marker %s). "
              "Pipeline creation is a one-time Convert and Flow UI step; provision-pipeline binds it by name.\n"
              % (len(pipelines), masked))
    if jsonout is not None:
        json.dump({"ok": True, "scope": "present", "pipelines_readable": len(pipelines)}, jsonout)
        jsonout.write("\n")
    return EX_OK


def provision_pipeline(client, field_map_path: Path, location_id: str, *,
                       dry_run: bool = False, out=None, jsonout=None):
    """FIND-AND-BIND the standard Anthology pipeline into field-map.json.

    GoHighLevel / Convert and Flow has NO public v2 API to CREATE a pipeline
    (pipelines are UI-only), so this is NEVER an auto-create: it READS the
    location's pipelines, finds the standard one BY NAME, and persists its id +
    stage ids (idempotent). If the standard pipeline is ABSENT it STOPS with an
    operator instruction to create it ONCE in the Convert and Flow UI (or to bind
    a pre-existing pipeline via `bind --pipeline-id`) -- it never calls a
    nonexistent create endpoint."""
    out = out or sys.stderr
    fm = load_field_map(field_map_path)
    pconf = fm.get("pipeline")
    if not isinstance(pconf, dict):
        _stop(out, "field-map.json has no pipeline config block", [str(field_map_path)])
        return EX_MISMATCH
    name = pconf["standard_pipeline_name"]
    masked = _mask_location(location_id)

    try:
        pipelines = client.list_pipelines(location_id)
    except ScopeDenied:
        _stop(out, "The Convert and Flow token cannot READ pipelines on this location (AF-AE-PIT-SCOPE).",
              ["Location marker: %s" % masked,
               "Grant the client's OWN location-scoped token the opportunities scope and re-run."])
        return EX_STOP
    except UpstreamBlockedError as exc:
        out.write("[provision-pipeline] HELD: %s (marker %s). NOT a token-scope problem; retryable.\n" % (exc, masked))
        return EX_HELD
    except CafUnreachable as exc:
        out.write("[provision-pipeline] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
        return EX_HELD

    found = _find_pipeline(pipelines, name)
    if found:
        sid = _stage_id_map(found)
        _stamp_pipeline(pconf, found.get("id"), sid, masked)
        save_field_map(field_map_path, fm)
        out.write("[provision-pipeline] OK (marker %s): bound the standard pipeline %r "
                  "(%d stage ids recorded; idempotent).\n" % (masked, name, len(sid)))
        if jsonout is not None:
            json.dump({"ok": True, "action": "bound_existing", "stages": len(sid)}, jsonout)
            jsonout.write("\n")
        return EX_OK

    # NOT present. Pipelines are UI-only; there is NO create endpoint to fall back
    # on. STOP with a clear, actionable operator surface (never a nonexistent POST).
    if dry_run:
        out.write("[provision-pipeline] DRY RUN (marker %s): the standard pipeline %r is NOT present. "
                  "It must be created ONCE in the Convert and Flow UI (there is no API create endpoint), "
                  "then re-run to bind it by name. No write performed.\n" % (masked, name))
        if jsonout is not None:
            json.dump({"ok": True, "dry_run": True, "standard_pipeline_present": False, "needs_ui_create": name},
                      jsonout)
            jsonout.write("\n")
        return EX_OK
    _stop(out, "The standard Anthology pipeline %r is NOT present on this location, and Convert and Flow "
               "(GoHighLevel) exposes NO API to create one -- pipelines are UI-only (AF-AE-PIPELINE-UI-CREATE)." % name,
          ["Location marker: %s" % masked,
           "Create a pipeline named EXACTLY %r once in the Convert and Flow UI (with the standard stages)," % name,
           "then re-run provision-pipeline: it binds the pipeline by name and records the stage ids.",
           "Or bind a pre-existing pipeline explicitly: bind --anthology-id <id> --pipeline-id <existing-id>.",
           "Setup STOPPED; the engine never calls a nonexistent create endpoint."])
    if jsonout is not None:
        json.dump({"ok": False, "reason": "pipeline_ui_create_required", "pipeline_name": name}, jsonout)
        jsonout.write("\n")
    return EX_STOP


def _stamp_pipeline(pconf: dict, pipeline_id, stage_ids: dict, masked: str) -> None:
    pconf.setdefault("resolved", {})
    pconf["resolved"]["pipeline_id"] = pipeline_id
    pconf["resolved"]["stage_ids"] = stage_ids
    pconf["resolved"]["provisioned_at"] = _now_iso()
    pconf["resolved"]["location_masked"] = masked


# ---------------------------------------------------------------------------
# PER-ANTHOLOGY BINDINGS (per-box registry file; NOT the ledger, NOT committed).
# ---------------------------------------------------------------------------
def registry_path(override: str = "") -> Path:
    if override:
        return Path(override).expanduser()
    return default_state_dir() / "registry.json"


def _load_registry(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"contract": "anthology-engine-registry", "schema_version": 1, "bindings": {}}


def _save_registry(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent),
                                      prefix=".registry.", suffix=".tmp", delete=False)
    try:
        json.dump(data, tmp, indent=2, ensure_ascii=False, sort_keys=True)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, str(path))


def _default_stage_map(field_map_path: Path) -> dict:
    """engine stage (s0..s9) -> resolved pipeline stage id, derived from the
    standard pipeline resolved stage ids. Empty if the pipeline is unresolved."""
    fm = load_field_map(field_map_path)
    pconf = fm.get("pipeline", {})
    engine_map = pconf.get("engine_stage_to_pipeline_stage", {})
    stage_ids = (pconf.get("resolved") or {}).get("stage_ids") or {}
    out = {}
    for engine_stage, stage_name in engine_map.items():
        if stage_name in stage_ids:
            out[engine_stage] = stage_ids[stage_name]
    return out


def bind_anthology(reg_path: Path, field_map_path: Path, *, anthology_id: str, location_id: str,
                   pipeline_id: str = "", stage_map=None, form_ids=None, drive_folder: str = "",
                   out=None) -> int:
    out = out or sys.stderr
    if not anthology_id or not location_id:
        out.write("[bind] validation: --anthology-id and --location-id are required.\n")
        return EX_MISMATCH
    if pipeline_id == "":
        fm = load_field_map(field_map_path)
        pipeline_id = ((fm.get("pipeline", {}).get("resolved") or {}).get("pipeline_id")) or ""
    if not pipeline_id:
        _stop(out, "Cannot bind anthology %r: no pipeline is resolved and none was supplied." % anthology_id,
              ["Run provision-pipeline first, or pass --pipeline-id for a pre-existing pipeline (override)."])
        return EX_STOP
    if stage_map is None:
        stage_map = _default_stage_map(field_map_path)
    reg = _load_registry(reg_path)
    reg.setdefault("bindings", {})[anthology_id] = {
        "anthology_id": anthology_id,
        "caf_location_id": location_id,
        "pipeline_id": pipeline_id,
        "caf_stage_map": stage_map,
        "form_ids": form_ids or {},
        "drive_folder_id": drive_folder or None,
        "bound_at": _now_iso(),
    }
    _save_registry(reg_path, reg)
    out.write("[bind] OK: anthology %r bound (pipeline ...%s, %d stage-map entries, marker %s).\n"
              % (anthology_id, str(pipeline_id)[-6:], len(stage_map), _mask_location(location_id)))
    return EX_OK


def resolve_anthology(reg_path: Path, anthology_id: str, *, out=None, jsonout=None) -> int:
    out = out or sys.stderr
    reg = _load_registry(reg_path)
    binding = reg.get("bindings", {}).get(anthology_id)
    if not binding:
        out.write("[resolve] unknown anthology binding: %r\n" % anthology_id)
        return EX_STOP
    target = jsonout or sys.stdout
    json.dump(binding, target, indent=2, ensure_ascii=False, sort_keys=True)
    target.write("\n")
    return EX_OK


def list_bindings(reg_path: Path, *, out=None) -> int:
    out = out or sys.stdout
    reg = _load_registry(reg_path)
    bindings = reg.get("bindings", {})
    if not bindings:
        out.write("(no anthology bindings on this box)\n")
        return EX_OK
    for aid, b in sorted(bindings.items()):
        out.write("  %s  ->  pipeline ...%s  location %s  stages=%d  bound_at=%s\n"
                  % (aid, str(b.get("pipeline_id", ""))[-6:], _mask_location(b.get("caf_location_id", "")),
                     len(b.get("caf_stage_map", {})), b.get("bound_at", "?")))
    return EX_OK


# ---------------------------------------------------------------------------
# plan (offline, no network): show the standard pipeline + field inventory +
# resolved status straight from the committed/installed field-map.json.
# ---------------------------------------------------------------------------
def plan(field_map_path: Path, *, out=None) -> int:
    out = out or sys.stdout
    fm = load_field_map(field_map_path)
    pconf = fm.get("pipeline", {})
    out.write("ANTHOLOGY REGISTRY — PROVISIONING PLAN (offline)\n")
    out.write("  standard pipeline: %r\n" % pconf.get("standard_pipeline_name"))
    for s in pconf.get("standard_stages", []):
        out.write("    [%d] %s\n" % (s["position"], s["name"]))
    presolved = pconf.get("resolved", {}) or {}
    out.write("  pipeline resolved: %s\n" % ("YES" if presolved.get("pipeline_id") else "no (template)"))
    inv = fm.get("provisioning", {}).get("fields", [])
    resolved_n = sum(1 for i in inv if i.get("field_key") and i.get("field_id"))
    out.write("  PRD Section 6 fields: %d total, %d resolved\n" % (len(inv), resolved_n))
    for i in inv:
        mark = "RESOLVED" if (i.get("field_key") and i.get("field_id")) else "pending"
        out.write("    [%-8s] %s  (create name %s, %s)\n"
                  % (mark, i["intended_key"], i["create_name"], i.get("data_type", "LARGE_TEXT")))
    out.write("  PIT labels checked (in order): %s\n" % ", ".join(PIT_LABELS))
    out.write("  Location labels checked (in order): %s\n" % ", ".join(LOCATION_LABELS))
    return EX_OK


# ---------------------------------------------------------------------------
# Live-client construction (resolves creds by label; STOPs if absent/invalid).
# Returns (client, location_id) or (None, exit_code).
# ---------------------------------------------------------------------------
def _live_client(location_override: str = "", out=None):
    out = out or sys.stderr
    pit_label, token = resolve_pit()
    loc_label, loc = resolve_location(location_override)
    if not token:
        checked = ", ".join(PIT_LABELS)
        if pit_label:
            _stop(out, "A Convert and Flow token is SET but is not a valid private-integration token.",
                  ["Label %s resolved a value that does NOT start with %r." % (pit_label, PIT_PREFIX),
                   "The value is not printed. Set a real pit- token under one of: %s" % checked])
        else:
            _stop(out, "No Convert and Flow private-integration token is SET.",
                  ["Checked (in order): %s — all NOT SET." % checked,
                   "Set the client's OWN location-scoped pit- token and re-run."])
        return None, EX_STOP
    if not loc:
        _stop(out, "No Convert and Flow Location id is SET.",
              ["Checked (in order): %s — all NOT SET." % ", ".join(LOCATION_LABELS),
               "Set the client's OWN location id (the intake tenant check binds to it)."])
        return None, EX_STOP
    out.write("[creds] PIT resolved via %s (SET). Location via %s (marker %s).\n"
              % (pit_label, loc_label, _mask_location(loc)))
    return CafClient(token), loc


# ---------------------------------------------------------------------------
# SELF-TEST: exercises the full create/verify/persist/stop/idempotent logic
# against an in-memory fake Convert and Flow, plus the binding round-trip. No
# network, no secrets, no live location touched.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow for the self-test. Mirrors the REAL CafClient
    surface: list/create custom fields and (READ-ONLY) list pipelines. There is no
    create_pipeline/delete_pipeline -- pipelines are UI-only in the real API."""

    def __init__(self, *, pipeline_read=True, field_write=True, key_mangler=None,
                 existing_fields=None, existing_pipelines=None):
        self.pipeline_read = pipeline_read
        self.field_write = field_write
        self.key_mangler = key_mangler
        self.fields = {}   # fieldKey -> {id, name, dataType}
        self.pipelines = []
        self._n = 0
        for f in (existing_fields or []):
            self.fields[f["fieldKey"]] = f
        for p in (existing_pipelines or []):
            self.pipelines.append(p)

    def list_custom_fields(self, location_id):
        return [dict(fieldKey=k, **{kk: vv for kk, vv in v.items() if kk != "fieldKey"})
                for k, v in self.fields.items()]

    def create_custom_field(self, location_id, name, data_type, options=None):
        if not self.field_write:
            raise ScopeDenied("no custom-field write")
        self._n += 1
        fk = self.key_mangler(name) if self.key_mangler else derive_field_key(name)
        fid = "fld_fake_%d" % self._n
        self.fields[fk] = {"id": fid, "name": name, "dataType": data_type, "options": options}
        return {"fieldKey": fk, "id": fid, "name": name, "dataType": data_type, "options": options}

    def list_pipelines(self, location_id):
        if not self.pipeline_read:
            raise ScopeDenied("no pipeline read")
        return [json.loads(json.dumps(p)) for p in self.pipelines]


def _standard_pipeline_fixture() -> dict:
    """Build an EXISTING standard pipeline exactly as one created once in the
    Convert and Flow UI would read back: name == the field-map standard name, one
    stage per standard stage, each carrying an id. provision_pipeline finds it by
    name and binds it."""
    fm = load_field_map(FIELD_MAP_PATH)
    pc = fm["pipeline"]
    stages = [{"name": s["name"], "position": s["position"], "id": "st_seed_%d" % s["position"]}
              for s in pc["standard_stages"]]
    return {"id": "pl_seed_std", "name": pc["standard_pipeline_name"], "stages": stages}


def _tmp_field_map() -> Path:
    """Copy the committed template into a temp file so the self-test never
    dirties the real field-map.json."""
    src = load_field_map(FIELD_MAP_PATH)
    d = Path(tempfile.mkdtemp(prefix="ae-reg-selftest-"))
    p = d / "field-map.json"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(src, fh, indent=2, ensure_ascii=False)
    return p


def self_test() -> int:
    dev = io.StringIO()  # swallow operator surfaces during the test

    # -- derivation law -----------------------------------------------------
    assert create_name_of("contact.anthology_avatar_doc_url") == "anthology_avatar_doc_url"
    assert derive_field_key("anthology_avatar_doc_url") == "contact.anthology_avatar_doc_url"

    # -- inventory integrity: 28 keys, each derives cleanly --------------------
    #    (19 base PRD Section 6 link/control keys + 4 G10 rewrite keys + 5 U8 cover-style)
    fm0 = load_field_map(FIELD_MAP_PATH)
    inv = fm0["provisioning"]["fields"]
    assert len(inv) == 28, "expected 28 fields (19 base + 4 G10 rewrite + 5 U8 cover-style), got %d" % len(inv)
    keys = {i["intended_key"] for i in inv}
    assert len(keys) == 28, "duplicate intended_key in inventory"
    for i in inv:
        assert derive_field_key(i["create_name"]) == i["intended_key"], i["intended_key"]
        assert i["field_key"] is None and i["field_id"] is None, "template must ship resolved=null"
        # Gap G11: every FREE-TEXT key is declared LARGE_TEXT (matches live), not TEXT.
        # The one exception is the U8 cover-choice picklist, which is SINGLE_OPTIONS.
        if i["intended_key"] == "contact.anthology_cover_choice":
            assert i["data_type"] == "SINGLE_OPTIONS", \
                "the cover choice must be SINGLE_OPTIONS, got %s" % i.get("data_type")
        else:
            assert i["data_type"] == "LARGE_TEXT", \
                "%s must declare LARGE_TEXT (G11), got %s" % (i["intended_key"], i.get("data_type"))
    # Gap G10: the four rewrite-preservation keys are present and distinct from the base
    # chapter pair, so a rewrite can never overwrite the original.
    for slot in ("rewrite1_doc_url", "rewrite1_pdf_url", "rewrite2_doc_url", "rewrite2_pdf_url"):
        assert ("contact.anthology_chapter_%s" % slot) in keys, "G10 missing %s" % slot
    assert "contact.anthology_chapter_doc_url" in keys and \
           "contact.anthology_chapter_rewrite1_doc_url" in keys, "G10 base + rewrite1 both present"
    # U8: exactly one SINGLE_OPTIONS field (the cover choice), and it ships its options
    single_opts = [i for i in inv if i.get("data_type") == "SINGLE_OPTIONS"]
    assert len(single_opts) == 1 and single_opts[0]["intended_key"] == "contact.anthology_cover_choice"
    assert single_opts[0].get("options"), "the SINGLE_OPTIONS choice field must ship its picklist options"
    # every PRD Section 6 deliverable + control key AND the U8 cover-style keys are represented
    contract_keys = set()
    for pair in fm0["deliverable_fields"].values():
        contract_keys.update(pair.values())
    contract_keys.update(fm0["control_fields"].values())
    csf0 = fm0.get("cover_style_fields") or {}
    contract_keys.update((csf0.get("sample_url_fields") or {}).values())
    if csf0.get("choice_field"):
        contract_keys.add(csf0["choice_field"])
    assert contract_keys == keys, "inventory drifted from the deliverable/control/cover-style contract"

    # -- fields: happy path create-or-verify + persist ----------------------
    p1 = _tmp_field_map()
    caf = _FakeCaf()
    rc = provision_fields(caf, p1, "loc_test_QcDX", out=dev)
    assert rc == EX_OK, "happy provision_fields rc=%s" % rc
    fm1 = load_field_map(p1)
    assert all(i["field_key"] == i["intended_key"] and i["field_id"] for i in fm1["provisioning"]["fields"])
    assert verify_fields_resolved(p1, out=dev) == EX_OK
    # Gap G11: create-or-verify on a FRESH location yields LARGE_TEXT for every
    # free-text field, matching live (no TEXT ever created). All 28 keys are created on
    # the empty box; the lone U8 cover-choice field is created as SINGLE_OPTIONS.
    assert len(caf.fields) == 28, "fresh location should hold all 28 created fields, got %d" % len(caf.fields)
    created_types = {f["dataType"] for f in caf.fields.values()}
    assert created_types == {"LARGE_TEXT", "SINGLE_OPTIONS"}, \
        "fresh-location create must be LARGE_TEXT for free-text + SINGLE_OPTIONS for the cover choice (G11), got %s" % created_types
    # and the persisted map records LARGE_TEXT on every free-text row (all but the cover choice)
    assert all(i["data_type"] == "LARGE_TEXT" for i in fm1["provisioning"]["fields"]
               if i["intended_key"] != "contact.anthology_cover_choice")
    assert next(i for i in fm1["provisioning"]["fields"]
                if i["intended_key"] == "contact.anthology_cover_choice")["data_type"] == "SINGLE_OPTIONS"
    # idempotent re-run: fields now exist -> verified-by-key, still OK
    rc = provision_fields(caf, p1, "loc_test_QcDX", out=dev)
    assert rc == EX_OK, "idempotent provision_fields rc=%s" % rc

    # -- fields: exact-match MISMATCH -> exit 5, nothing stamped ------------
    p2 = _tmp_field_map()
    bad = _FakeCaf(key_mangler=lambda name: "contact." + name + "_WRONG")
    rc = provision_fields(bad, p2, "loc_test_QcDX", out=dev)
    assert rc == EX_MISMATCH, "mismatch should be exit 5, got %s" % rc
    fm2 = load_field_map(p2)
    assert all(i["field_key"] is None for i in fm2["provisioning"]["fields"]), "no stamp on mismatch STOP"

    # -- fields: WRITE scope absent -> exit 2 STOP -------------------------
    p3 = _tmp_field_map()
    noscope = _FakeCaf(field_write=False)
    rc = provision_fields(noscope, p3, "loc_test_QcDX", out=dev)
    assert rc == EX_STOP, "no field-write scope should STOP exit 2, got %s" % rc

    # -- fields: dry run performs no writes --------------------------------
    p4 = _tmp_field_map()
    rc = provision_fields(_FakeCaf(), p4, "loc_test_QcDX", dry_run=True, out=dev)
    assert rc == EX_OK
    assert all(i["field_key"] is None for i in load_field_map(p4)["provisioning"]["fields"]), "dry run wrote data"

    # -- pipeline (BUG 2): READ scope absent -> exit 2 STOP -----------------
    p5 = _tmp_field_map()
    rc = provision_pipeline(_FakeCaf(pipeline_read=False), p5, "loc_test_QcDX", out=dev)
    assert rc == EX_STOP, "no pipeline-read scope should STOP exit 2, got %s" % rc

    # -- pipeline (BUG 2): standard pipeline ABSENT -> UI-create STOP -------
    # There is NO API create endpoint; an empty account must STOP with the
    # UI-create instruction, NEVER attempt a (nonexistent) auto-create.
    p5b = _tmp_field_map()
    rc = provision_pipeline(_FakeCaf(), p5b, "loc_test_QcDX", out=dev)
    assert rc == EX_STOP, "absent standard pipeline should STOP (UI-create), got %s" % rc
    assert (load_field_map(p5b)["pipeline"].get("resolved") or {}).get("pipeline_id") is None, \
        "nothing may be stamped on the UI-create STOP"

    # -- pipeline (BUG 2): BIND a pre-existing standard pipeline -> persist -
    existing_std = _standard_pipeline_fixture()
    p6 = _tmp_field_map()
    caf6 = _FakeCaf(existing_pipelines=[existing_std])
    rc = provision_pipeline(caf6, p6, "loc_test_QcDX", out=dev)
    assert rc == EX_OK, "bind existing pipeline rc=%s" % rc
    fm6 = load_field_map(p6)
    resolved = fm6["pipeline"]["resolved"]
    assert resolved["pipeline_id"] and len(resolved["stage_ids"]) == 9, "pipeline resolved incompletely"
    # idempotent: same standard pipeline still present -> re-bind, OK
    rc = provision_pipeline(caf6, p6, "loc_test_QcDX", out=dev)
    assert rc == EX_OK, "idempotent pipeline rc=%s" % rc
    # dry-run against an empty account: reports the UI-create need, stamps nothing
    p6d = _tmp_field_map()
    assert provision_pipeline(_FakeCaf(), p6d, "loc_test_QcDX", dry_run=True, out=dev) == EX_OK
    assert (load_field_map(p6d)["pipeline"].get("resolved") or {}).get("pipeline_id") is None

    # -- probe-scope (BUG 2): read feasible (OK) and unreadable (STOP) ------
    assert probe_write_scope(_FakeCaf(existing_pipelines=[existing_std]), "loc_test_QcDX", out=dev) == EX_OK
    assert probe_write_scope(_FakeCaf(pipeline_read=False), "loc_test_QcDX", out=dev) == EX_STOP

    # -- BUG 1: browser User-Agent + scope-vs-Cloudflare discrimination -----
    # The REAL CafClient._request is exercised end to end by patching urlopen so a
    # crafted upstream response drives the exact production code path. A default
    # urllib UA would 403 at the Cloudflare edge; a genuine scope body must raise
    # ScopeDenied; a Cloudflare/WAF block must NOT be mislabeled as a scope denial.
    _orig_urlopen = urllib.request.urlopen
    captured_ua = {}

    class _FakeResp:
        def __init__(self, body=b"{}"):
            self._body = body
        def read(self):
            return self._body
        def getcode(self):
            return 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _http_error(status, body, headers):
        return urllib.error.HTTPError("https://services.leadconnectorhq.com/x",
                                      status, "err", headers, io.BytesIO(body))

    try:
        # (a) the browser User-Agent actually rides on every request
        def _ok_open(req, timeout=None):
            captured_ua["ua"] = {k.lower(): v for k, v in req.header_items()}.get("user-agent")
            return _FakeResp(b'{"pipelines": []}')
        urllib.request.urlopen = _ok_open
        CafClient("tok_probe").list_pipelines("loc_test_QcDX")
        assert captured_ua.get("ua") == MOZILLA_UA, \
            "browser User-Agent not sent on the request: %r" % captured_ua.get("ua")

        # (b) a GENUINE scope denial (W0.5 JSON signature) -> ScopeDenied
        def _scope_open(req, timeout=None):
            raise _http_error(401, b'{"message": "The token is not authorized for this scope."}',
                              {"Content-Type": "application/json"})
        urllib.request.urlopen = _scope_open
        try:
            CafClient("tok_probe").list_pipelines("loc_test_QcDX")
            assert False, "a genuine scope denial must raise ScopeDenied"
        except ScopeDenied:
            pass

        # (c) a Cloudflare/WAF edge block (CF 1010 HTML) -> NOT ScopeDenied
        def _cf_open(req, timeout=None):
            raise _http_error(403,
                              b"<!DOCTYPE html><html><head><title>Attention Required! | Cloudflare</title></head>"
                              b"<body>error code: 1010 Ray ID: deadbeef</body></html>",
                              {"Server": "cloudflare", "Content-Type": "text/html"})
        urllib.request.urlopen = _cf_open
        try:
            CafClient("tok_probe").list_pipelines("loc_test_QcDX")
            assert False, "a Cloudflare block must raise, but NOT ScopeDenied"
        except ScopeDenied:
            assert False, "Cloudflare WAF block MISLABELED as ScopeDenied (the Wave 5 false positive)"
        except UpstreamBlockedError:
            pass  # correctly distinguished from a scope problem

        # (d) a non-JSON / non-Cloudflare 403 is ALSO not a scope denial
        def _plain_open(req, timeout=None):
            raise _http_error(403, b"Forbidden", {"Content-Type": "text/plain"})
        urllib.request.urlopen = _plain_open
        try:
            CafClient("tok_probe").list_pipelines("loc_test_QcDX")
            assert False, "a plain 403 must raise"
        except ScopeDenied:
            assert False, "a non-scope 403 must not be labeled ScopeDenied"
        except UpstreamBlockedError:
            pass
    finally:
        urllib.request.urlopen = _orig_urlopen

    # unit-level: the body classifier itself agrees
    assert _auth_denial_kind(b'{"message": "The token is not authorized for this scope."}') == "scope"
    assert _auth_denial_kind(b"<!DOCTYPE html> ... cloudflare 1010") == "blocked"
    assert _auth_denial_kind(b'{"message": "Rate limit exceeded"}') == "blocked"
    assert _auth_denial_kind(b"") == "blocked"

    # -- binding round-trip on p6 (pipeline resolved) ----------------------
    regdir = Path(tempfile.mkdtemp(prefix="ae-reg-bind-"))
    regp = regdir / "registry.json"
    rc = bind_anthology(regp, p6, anthology_id="anth-001", location_id="loc_test_QcDX", out=dev)
    assert rc == EX_OK, "bind rc=%s" % rc
    cap = io.StringIO()
    assert resolve_anthology(regp, "anth-001", jsonout=cap) == EX_OK
    b = json.loads(cap.getvalue())
    assert b["anthology_id"] == "anth-001" and b["caf_stage_map"], "binding did not persist a stage map"
    assert len(b["caf_stage_map"]) == 10, "expected s0..s9 stage-map entries"
    assert resolve_anthology(regp, "nope", out=dev) == EX_STOP  # unknown binding
    # bind refuses when no pipeline resolved and none supplied
    p7 = _tmp_field_map()
    assert bind_anthology(regp, p7, anthology_id="anth-x", location_id="loc", out=dev) == EX_STOP
    # bind validation: missing ids
    assert bind_anthology(regp, p6, anthology_id="", location_id="", out=dev) == EX_MISMATCH

    print("anthology_registry self-test: OK "
          "(derivation, 28-field inventory incl. 4 G10 rewrite + 5 U8 cover-style/SINGLE_OPTIONS, "
          "create/verify/persist, exact-match STOP, "
          "scope STOP, dry-run, pipeline find-and-bind + UI-create STOP + idempotent, "
          "probe-scope read feasibility, browser-UA + scope-vs-Cloudflare discrimination, "
          "binding round-trip)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="anthology_registry.py",
        description="Convert and Flow auto-provisioning + per-anthology bindings (Skill 59).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (default: the skill's config copy)")
    ap.add_argument("--registry", default="", help="path to the per-box registry.json (default: state dir)")
    ap.add_argument("--location-id", default="", help="override the Convert and Flow location id")
    ap.add_argument("--dry-run", action="store_true", help="plan writes without performing them")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable summary on stdout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in [
        ("probe-scope", "verify the token can READ pipelines on the location (pipelines are UI-only; no create)"),
        ("provision-pipeline", "find the standard Anthology pipeline BY NAME and bind it (UI-only; no auto-create)"),
        ("provision-fields", "create-or-verify the 28 fields (19 PRD Section 6 + 4 G10 rewrite + 5 U8 cover-style); persist server fieldKey + id"),
        ("provision-all", "provision-pipeline then provision-fields (stops on first STOP)"),
        ("verify-fields", "READ-ONLY: assert field-map.json is fully resolved and exact-match"),
        ("bind", "bind an anthology_id to a pipeline, stage map, forms, and Drive folder"),
        ("resolve", "print a per-anthology binding as JSON"),
        ("list", "list per-anthology bindings on this box"),
        ("plan", "offline: show the standard pipeline + field inventory + resolved status"),
        ("self-test", "run the offline self-test and exit"),
    ]:
        sp = sub.add_parser(name, help=help_)
        # Accept the global flags AFTER the subcommand too (the natural call
        # shape a shell caller reaches for: `... provision-fields --dry-run`).
        # default=SUPPRESS means an unset flag on the subparser never clobbers
        # the value the main parser already resolved (the classic argparse
        # subparser default-clobber, worked around exactly as anthology_state.py).
        for opt in ("--field-map", "--registry", "--location-id"):
            sp.add_argument(opt, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        if name in ("bind", "resolve"):
            sp.add_argument("--anthology-id", required=(name == "resolve"))
        if name == "bind":
            sp.add_argument("--pipeline-id", default="")
            sp.add_argument("--stage-map", default="", help="JSON engine-stage->stage-id (default: derived)")
            sp.add_argument("--form-ids", default="", help="JSON map of form ids")
            sp.add_argument("--drive-folder", default="")

    args = ap.parse_args(argv)
    field_map = Path(args.field_map).expanduser()
    reg_path = registry_path(args.registry)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan(field_map)
        if args.cmd == "verify-fields":
            return verify_fields_resolved(field_map)
        if args.cmd == "list":
            return list_bindings(reg_path)
        if args.cmd == "resolve":
            return resolve_anthology(reg_path, args.anthology_id, jsonout=jsonout)
        if args.cmd == "bind":
            aid = args.anthology_id
            _, loc = resolve_location(args.location_id)
            stage_map = json.loads(args.stage_map) if args.stage_map else None
            form_ids = json.loads(args.form_ids) if args.form_ids else None
            return bind_anthology(reg_path, field_map, anthology_id=aid or "",
                                  location_id=loc or "", pipeline_id=args.pipeline_id,
                                  stage_map=stage_map, form_ids=form_ids, drive_folder=args.drive_folder)

        # live-network commands below
        client, loc_or_rc = _live_client(args.location_id)
        if client is None:
            return loc_or_rc
        location_id = loc_or_rc
        if args.cmd == "probe-scope":
            return probe_write_scope(client, location_id, dry_run=args.dry_run, jsonout=jsonout)
        if args.cmd == "provision-pipeline":
            return provision_pipeline(client, field_map, location_id, dry_run=args.dry_run, jsonout=jsonout)
        if args.cmd == "provision-fields":
            return provision_fields(client, field_map, location_id, dry_run=args.dry_run, jsonout=jsonout)
        if args.cmd == "provision-all":
            rc = provision_pipeline(client, field_map, location_id, dry_run=args.dry_run, jsonout=jsonout)
            if rc != EX_OK:
                return rc
            return provision_fields(client, field_map, location_id, dry_run=args.dry_run, jsonout=jsonout)
        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        sys.stderr.write("[anthology_registry] file not found: %s\n" % exc)
        return EX_ERR
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[anthology_registry] unexpected error: %s\n" % type(exc).__name__)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
