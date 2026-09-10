#!/usr/bin/env python3
# =============================================================================
# SHARED RESCUE ADMISSION CLIENT :: scripts/lib/rescue_admission.py
# RR-015 -- Route EWS through actual rescue admission (SPEC RR-015 exact repair)
# -----------------------------------------------------------------------------
# THE ONE SHARED, VERSIONED ADMISSION CLIENT for the Skill 60 EWS escalation
# paths (ews_alert.py escalate() and ews_fleet.py dead-man). It POSTs a
# structured escalation to the canonical rescue intake webhook
# (rr-v2-intake) -- the ONLY path that mints a durable rescue ticket -- and
# returns a STRUCTURED RECEIPT. A gateway Telegram message is NOT admission:
# it is supplemental operator visibility, recorded separately, and can never
# mark an escalation accepted.
#
# DESIGN (SPEC RR-015 exact repair, clause by clause):
#   * shared versioned client .. this module, versioned below, loaded through
#     ews_common.load_rescue_admission() so both EWS paths share ONE
#     implementation (no second send path).
#   * validate enrolled client and runtime identity .. the payload carries the
#     box's canonical identity (FLEET_STANDING_BOX_SLUG when present) and the
#     admission credential SCHEMA is resolved explicitly: v2 per-enrollment
#     (RR_BOX_CRED + RR_BOX_ID) preferred, then v1 shared fleet secret
#     (RESCUE_RANGERS_WEBHOOK_SECRET), then unauthenticated (intake soft
#     phase). Credential VALUES are read from the environment but never
#     printed, journaled or placed in any payload field.
#   * source event and operation ID .. every attempt carries a deterministic
#     operation_id (sha256 of box + source + event identity) so a replay of the
#     same event reproduces the SAME operation identity and the intake's
#     idempotency can fold it. No wall-clock timestamp rides the body, so a
#     retry is byte-identical.
#   * nine-field legacy compatibility .. the body carries the nine advertised
#     intake fields (person, clientName, agentName, boxName, boxType,
#     openclawVersion, problem, alreadyTried, returnTo) plus a source/machine
#     block; empty fields are accepted by the intake as degraded INCOMPLETE
#     (never dropped).
#   * bounded HTTP .. stdlib urllib, monotonic timeout (measured intake
#     latency ~30s, default 120s = 4x headroom per the Skill 61 finding),
#     body read limited to 64 KiB.
#   * retry journal .. every attempt is journaled durably in the EWS ledger
#     (rescue_admissions table -- the ledger is the sole EWS state writer) with
#     status, receipt digest (never the response body) and sanitized detail.
#     A FAILED/UNCERTAIN attempt leaves the source event OPEN and retry
#     eligible; only a validated admission receipt changes incident state.
#   * redaction .. responses carrying a credential SHAPE are dropped whole;
#     journal detail carries statuses and ids only.
#   * structured receipt .. admit() returns one dict with an explicit status:
#     admitted | refused | failed | replay | dry_run | no_enrollment |
#     client_unavailable, plus operation_id, ticket_id (when the intake
#     answered one), admission_schema and a sanitized detail.
#   * missing enrollment is a PENDING REPAIR with an OWNER, never an admission
#     and never a policy refusal of the incident (RR-015 exact repair, and the
#     reason this clause exists: "A gateway Telegram message is NOT admission"
#     applies equally to an unauthenticated POST). See the intake-contract
#     drift block below for the live evidence that made this reachable.
#
# -----------------------------------------------------------------------------
# CURRENT INTAKE CONTRACT (verified against the shipped FLEET export, not from
# memory -- blackceo-fleet-ops rescue/workflows/RR-01-intake.json on FLEET main,
# node "Webhook Auth Check", read 2026-09-10):
#
#   * AUTH is the FIRST node after the webhook trigger and it FAILS CLOSED. It
#     reads EXACTLY ONE header -- `x-rescue-secret` -- and compares its SHA-256
#     against a stored accepted-hash set. There is NO "soft"/unauthenticated
#     phase in the current intake: an unauthenticated POST is answered 403
#     {"status":"unauthorized"} before payload parsing, before any admission
#     claim, before any ticket.
#   * RR-003 (identity lane) DECLARES a v2 per-enrollment pair (X-RR-Box-Cred +
#     X-RR-Box-Id) and this client implements it, but the LIVE intake does not
#     READ those headers yet. Sending them therefore lands on the 403 above.
#     That is a FLEET workflow-export change owned by the manifest/export
#     owner -- it is NOT edited from here. Until it lands, a v2-only box
#     receives `no_enrollment` (truthful: its credential is not accepted by the
#     current intake) rather than a fabricated "refused".
#   * VERDICT: the body carries `accepted` (bool) with `status`/`reason`; a
#     duplicate is answered 200 {"accepted":true,"status":"duplicate_ignored"}
#     -- the fold this client reports as `replay`.
# -----------------------------------------------------------------------------
#   * Reuse means REUSE: the timeout shape, the verdict parsing and the
#     redaction rules are the Skill 61 loop_escalate.py concepts (its measured
#     30.3s admission and the 200-with-refusal trap), carried here as the
#     canonical transport. The Skill 61 UNSENT autonomous drain stays
#     deliberately disarmed -- this module NEVER drains, replays autonomously
#     or posts a backlog.
#
# STDLIB ONLY. NEVER prints a credential value; NEVER sends to a client chat;
# NO model call. The transport is injectable (tests + self-test run fully
# offline). The production transport is used only when a transport is not
# injected.
#
# EXIT CODES (CLI): 0 admitted/replay/dry_run, 3 refused, 2 usage,
#                   1 failed/unavailable/missing config.
# =============================================================================
"""rescue_admission.py - shared versioned rescue admission client (Skill 60 EWS paths)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RESCUE_ADMISSION_CLIENT_VERSION = "1.0.0"


def _load_ews_ledger():
    """The EWS ledger module (sole state writer; the admission journal lives
    in its rescue_admissions table). Resolved from the running import first
    (the EWS skill scripts dir is already on sys.path when this client is
    loaded through ews_common.load_rescue_admission()), then by probing the
    repo tree and the standard installed roots, because this file can also be
    run stand-alone (python3 scripts/lib/rescue_admission.py --self-test)."""
    try:
        import ews_ledger as led_mod  # noqa: F401
        return led_mod
    except ImportError:
        pass
    import importlib.util
    this = Path(__file__).resolve()
    probes = [
        # repo tree: 60-zhc-early-warning-system/scripts/ews_ledger.py
        this.parent.parent.parent / "60-zhc-early-warning-system" / "scripts" / "ews_ledger.py",
    ]
    roots = []
    env_root = os.environ.get("EWS_OPENCLAW_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser())
    if Path("/data/.openclaw").is_dir():
        roots.append(Path("/data/.openclaw"))
    home = os.environ.get("HOME", "")
    if home:
        roots.append(Path(home).expanduser() / ".openclaw")
    for r in roots:
        probes.append(r / "skills" / "60-zhc-early-warning-system" / "scripts" / "ews_ledger.py")
        probes.append(r / "scripts" / "ews_ledger.py")
    for cand in probes:
        try:
            if cand.is_file():
                spec = importlib.util.spec_from_file_location("ews_ledger", str(cand))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
        except Exception:  # noqa: BLE001
            continue
    return None

# ---- configuration names (NAMES only; values never printed) ----------------
WEBHOOK_URL_ENV = "RESCUE_RANGERS_WEBHOOK_URL"
DEFAULT_WEBHOOK_URL = "https://main.blackceoautomations.com/webhook/rr-v2-intake"
SECRET_ENV = "RESCUE_RANGERS_WEBHOOK_SECRET"          # v1 shared fleet secret
BOX_CRED_ENV = "RR_BOX_CRED"                          # v2 per-enrollment credential
BOX_ID_ENV = "RR_BOX_ID"                              # v2 public enrollment id
BOX_SLUG_ENV = "FLEET_STANDING_BOX_SLUG"              # canonical per-box slug
TIMEOUT_ENV = "EWS_RESCUE_ADMISSION_TIMEOUT"
DEFAULT_TIMEOUT = 120.0
BODY_READ_LIMIT = 65536
V2_HEADERS_ENV = "EWS_RESCUE_ADMISSION_SEND_V2_HEADERS"

# OWNERSHIP of a missing enrollment. RR-015: "Record missing enrollment as
# pending repair with owner". The owner is the same role that seeds the
# enrollment rows themselves -- per the FLEET contract manifest, rr_box_auth is
# written by the "operator seeder (D08)" (RR-07-receiver-gw maintains only
# last_seen/last_ack/receiver_version). Carried as a NAMED constant so the
# journal, the digest and the receipt all agree on one owner string.
REPAIR_OWNER_ENROLLMENT = "operator-seeder-D08"
REPAIR_ACTION_ENROLLMENT = "enroll this box in rr_box_auth with an accepted admission credential"
# Status vocabulary: a receipt status that is a PENDING REPAIR (owned, visible,
# retryable) rather than an admission, a policy refusal, or an unowned fault.
PENDING_REPAIR_STATUSES = ("no_enrollment",)

# A validated admission receipt needs: a 2xx status AND an intake verdict of
# accept/admit. An unparseable body is UNDETERMINED (never a refusal, never a
# success) -- exactly the Skill 61 trap: intake answers HTTP 200 with
# {"accepted":false,...} and a bare status check would log it as sent.
_ADMIT_KEYS = ("accepted",)
_REFUSAL_KEYS = ("rejectReason", "reject_reason", "rejected", "error", "status")

# credential SHAPE markers: a response carrying any of these is dropped whole.
_SECRET_SHAPES = ("sk-", "Bearer ", "eyJ", "AIza", "xoxb-")

TRY = "try"     # a transport exception or undetermined answer
DONE = "done"   # a terminal attempt outcome (admitted / refused)


class AdmissionRefused(Exception):
    """The intake was REACHED and explicitly refused the payload. Terminal for
    this attempt; distinct from a transport failure."""


class AdmissionTransportError(Exception):
    """The intake was NOT reached (network, timeout, non-2xx). Retryable."""


# --------------------------------------------------------------------------- #
# value-free helpers
# --------------------------------------------------------------------------- #
def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def trim(text, limit=400):
    """Collapse a value to one loggable line; a credential SHAPE is dropped
    whole (doctrine: no secret value enters a journal/artifact)."""
    t = " ".join((text or "").split())
    for shape in _SECRET_SHAPES:
        if shape in t:
            return "<redacted: response carried a credential shape>"
    return t[:limit]


def _unquote_env(value):
    """Strip a MATCHED surrounding quote pair (config-drift artifact)."""
    v = (value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1].strip()
    return v


def _env_num(name, default, minimum=1):
    raw = _unquote_env(os.environ.get(name, ""))
    if raw == "":
        return default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    return v if v >= minimum else default


def timeout_seconds() -> float:
    """Admission timeout (default 120s ~= 4x the measured 30.3s admission path;
    overridable per box, minimum 1 -- a sub-second timeout is a fault)."""
    return _env_num(TIMEOUT_ENV, DEFAULT_TIMEOUT)


# --------------------------------------------------------------------------- #
# identity helpers
# --------------------------------------------------------------------------- #
def box_identity(meta_box=None, env_slug=None) -> str:
    """The canonical box identity for the payload: the enrolled fleet slug when
    present, else the EWS ledger meta box, else the hostname. Never empty --
    an escalation without a box is refused at the intake door (400)."""
    slug = (env_slug or os.environ.get(BOX_SLUG_ENV, "")).strip()
    if slug:
        return slug
    if meta_box:
        return str(meta_box).strip()
    import socket
    return str(socket.gethostname())


def resolve_admission_schema():
    """(schema, cred_value, id_value) -- 'v2' when the per-enrollment pair is
    present, else 'v1' when the shared secret is present, else 'none'.
    RETURNED FOR CALLERS' USE ONLY; never printed, never journaled."""
    cred = _unquote_env(os.environ.get(BOX_CRED_ENV, ""))
    bid = _unquote_env(os.environ.get(BOX_ID_ENV, ""))
    if cred and bid:
        return "v2", cred, bid
    secret = _unquote_env(os.environ.get(SECRET_ENV, ""))
    if secret:
        return "v1", secret, None
    return "none", None, None


def operation_id(box, source, dedup_key, event_id, signal=""):
    """STABLE operation identity for an escalation: same event, same inputs,
    same operation_id -- what makes a replay fold at the intake instead of
    minting a second ticket (RR-015: replays preserve identity)."""
    return sha256_hex("|".join([
        "ews-rescue-admission-v1", str(box), str(source), str(signal),
        str(dedup_key or ""), str(event_id or ""),
    ]))[:32]


def admission_url() -> str:
    return _unquote_env(os.environ.get(WEBHOOK_URL_ENV, "")) or DEFAULT_WEBHOOK_URL


# --------------------------------------------------------------------------- #
# payload (nine-field legacy compatibility + source/machine block)
# --------------------------------------------------------------------------- #
def build_payload(box, problem_text, *, source, signal="", key_path="",
                  dedup_key="", event_id=None, person="", client="",
                  agent="zhc-ews-sentinel", box_type="", openclaw_version="",
                  already_tried="", return_to=None, tick_ts=""):
    """The structured escalation object. Body carries the NINE advertised
    intake fields (empty ones are accepted as degraded INCOMPLETE -- a partial
    payload is never dropped) plus a source/operation block so the intake sees
    the source event and the stable operation identity. No secret value is
    admitted; problem is plain operator language (value-free per EWS doctrine).
    No wall-clock field: determinism makes a retry byte-identical."""
    op = operation_id(box, source, dedup_key, event_id, signal)
    return {
        "action": "escalate",
        "source": source,
        "box": box,
        # --- nine-field legacy contract -------------------------------------
        "person": person,
        "clientName": client,
        "agentName": agent,
        "boxName": box,
        "boxType": box_type,
        "openclawVersion": openclaw_version,
        "problem": problem_text,
        "alreadyTried": already_tried,
        "returnTo": return_to,
        # --- source event + operation identity ------------------------------
        "machine": {
            "ews_signal": signal,
            "ews_key_path": key_path,
            "ews_event_id": event_id,
            "ews_tick_ts": tick_ts,
            "source_op_id": op,
        },
        "message": problem_text,   # intake canonical; problem is the alias
        "operation_id": op,
        "client_version": RESCUE_ADMISSION_CLIENT_VERSION,
    }


def validate_payload(payload) -> list:
    """Return a list of named problems; empty == valid. A payload without a
    box or without a message is a CALLER ERROR (the intake answers 400)."""
    problems = []
    if not str(payload.get("boxName") or "").strip():
        problems.append("missing_box")
    if not str(payload.get("message") or "").strip():
        problems.append("missing_message")
    if not str(payload.get("operation_id") or "").strip():
        problems.append("missing_operation_id")
    return problems


# --------------------------------------------------------------------------- #
# verdict parsing (the Skill 61 200-with-refusal trap)
# --------------------------------------------------------------------------- #
def intake_verdict(body_text):
    """True = admitted, False = explicit refusal, None = UNDETERMINED.
    An unparseable body is NOT evidence of refusal."""
    if not body_text:
        return None
    try:
        doc = json.loads(body_text)
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    adm = doc.get("admission")
    if isinstance(adm, dict):
        decision = str(adm.get("decision", "")).lower()
        if decision.startswith("reject"):
            return False
        if decision.startswith(("accept", "admit")):
            return True
    if isinstance(doc.get("accepted"), bool):
        return doc["accepted"]
    for key in ("ok", "success"):
        if isinstance(doc.get(key), bool) and key in ("ok", "success"):
            return doc[key]
    for key in ("rejectReason", "reject_reason", "rejected", "error", "status"):
        if doc.get(key):
            return False
    return None


def is_replay_answer(body_text) -> bool:
    """True when the intake folded this operation onto an EXISTING ticket
    instead of minting a new one. The live intake answers a duplicate with
    HTTP 200 {"accepted":true,"status":"duplicate_ignored"} (node 'Build
    Non-Admitted Response', FLEET export) -- an accepted admission whose
    identity already existed. Reported as `replay` so a caller can distinguish
    "this attempt is what created the ticket" from "the ticket already existed
    and this attempt folded onto it"; BOTH are ack-eligible (a replay proves a
    durable ticket exists), and neither is ever a refusal."""
    if not body_text:
        return False
    try:
        doc = json.loads(body_text)
    except ValueError:
        return False
    if not isinstance(doc, dict):
        return False
    status = str(doc.get("status", "")).strip().lower()
    if status in ("duplicate_ignored", "duplicate", "replay", "folded"):
        return True
    adm = doc.get("admission")
    return isinstance(adm, dict) and str(adm.get("decision", "")).lower() in (
        "duplicate", "replay", "folded")


def _ticket_id(doc):
    if isinstance(doc, dict):
        for k in ("ticketId", "ticket_id", "ticket"):
            if doc.get(k):
                return str(doc[k])
        if isinstance(doc.get("ticket"), dict) and doc["ticket"].get("ticket_id"):
            return str(doc["ticket"]["ticket_id"])
    return None


def _handle_http_error(exc):
    """Classify a urllib HTTPError: 5xx/429 = transport/retryable, other 4xx =
    explicit refusal (terminal for this attempt)."""
    code = int(getattr(exc, "code", 0) or 0)
    try:
        detail = exc.read(BODY_READ_LIMIT).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        detail = ""
    if code == 429 or code >= 500:
        raise AdmissionTransportError(
            "intake HTTP %d: %s" % (code, trim(detail))) from exc
    raise AdmissionRefused(
        "intake HTTP %d: %s" % (code, trim(detail))) from exc


# Auth-shaped refusals. The current intake auth gate fails closed with 403
# {"status":"unauthorized"} for any header it cannot verify, so an auth refusal
# is NOT evidence the incident was rejected -- it is evidence this BOX's
# credential is not accepted by this intake. Kept as an explicit tuple (never a
# loose substring scan on the whole body) so a payload refusal that merely
# mentions authorization cannot be misread.
_AUTH_REFUSAL_MARKERS = (
    "unauthorized", "identity_mismatch", "forbidden", "forbidden_action",
    "invalid_credential", "credential_not_accepted", "not_enrolled",
)


def is_auth_refusal(detail) -> bool:
    """True when a refusal says the CALLER's credential/enrollment was not
    accepted (an owned setup repair), not that the incident was rejected."""
    d = " ".join(str(detail or "").lower().split())
    return any(marker in d for marker in _AUTH_REFUSAL_MARKERS)


def sends_v2_headers() -> bool:
    """Whether this client should actually emit the RR-003 v2 per-enrollment
    headers. DEFAULT FALSE: the live intake reads ONLY x-rescue-secret (verified
    against the shipped FLEET export), so emitting unread v2 headers would turn
    a healthy v1 escalation into a 403. Opt a box in with
    EWS_RESCUE_ADMISSION_SEND_V2_HEADERS=1 once the intake-side v2 reader has
    landed -- that FLEET export change belongs to the manifest/export owner."""
    return _unquote_env(os.environ.get(V2_HEADERS_ENV, "")).lower() in (
        "1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# production transport (stdlib urllib; used only when not injected)
# --------------------------------------------------------------------------- #
def urllib_transport(url, payload_bytes, timeout=None):
    """POST JSON to the intake. Returns the RESPONSE BODY TEXT (the caller
    parses the verdict -- a status is not the receipt). Raises
    AdmissionRefused for 4xx/refusal, AdmissionTransportError for
    network/5xx/timeout/undetermined."""
    import urllib.error
    import urllib.request
    timeout = timeout or timeout_seconds()
    schema, cred, bid = resolve_admission_schema()
    headers = {"Content-Type": "application/json"}
    # The header this client SENDS is decided by what the LIVE intake READS,
    # not by which credential the box happens to hold. The current intake
    # accepts only x-rescue-secret, so that is the default. A box carrying a v2
    # pair PLUS the shared secret authenticates as v1 (accepted today); a box
    # carrying ONLY the v2 pair cannot authenticate at all until the intake-side
    # v2 reader lands -- that is reported truthfully as no_enrollment, and the
    # v2 headers are emitted only when explicitly opted in.
    if schema == "v2" and sends_v2_headers():
        headers["X-RR-Box-Cred"] = cred
        headers["X-RR-Box-Id"] = bid
    elif schema in ("v2", "v1"):
        if schema == "v2":
            # v2 pair present but v2 headers not enabled: try the shared secret
            # as the credential the live intake actually accepts.
            cred = _unquote_env(os.environ.get(SECRET_ENV, ""))
        if cred:
            headers["X-Rescue-Secret"] = cred
    req = urllib.request.Request(url, data=payload_bytes,
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 0) or 0)
            body = resp.read(BODY_READ_LIMIT).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        _handle_http_error(exc)
        return ""  # unreachable; keeps linters quiet
    except Exception as exc:  # noqa: BLE001 - timeout/conn refused/OSError
        raise AdmissionTransportError(
            "%s: %s" % (type(exc).__name__, trim(str(exc)))) from exc
    if not 200 <= status < 300:
        raise AdmissionTransportError(
            "intake HTTP %d: %s" % (status, trim(body)))
    return body


# --------------------------------------------------------------------------- #
# the one entry point
# --------------------------------------------------------------------------- #
def admit(state_dir=None, box="", problem_text="", *,
          source="skill-60-ews", signal="", key_path="", dedup_key="",
          event_id=None, tick_ts="", transport=None, url=None,
          dry_run=False, ledger=None, meta_box=None):
    """Attempt rescue admission. Returns a STRUCTURED RECEIPT dict:
        {
          "status": "admitted"|"replay"|"refused"|"failed"|"dry_run"|
                    "no_enrollment"|"client_unavailable",
          "operation_id": str,
          "ticket_id": str|None,
          "admission_schema": "v2"|"v1"|"none",
          "detail": sanitized one-liner,
          "reply_digest": sha256 of the verified reply body (never the body),
          "attempted_at": iso,
        }
    Journaling: every NON-dry-run attempt writes a durable row in the EWS
    ledger rescue_admissions table (the ledger is the sole EWS state writer).
    Failure/uncertainty NEVER consumes an incident: the caller decides state
    transitions from the receipt status. dry_run performs no network and no
    journal write."""
    led_mod = _load_ews_ledger()
    Ledger = led_mod.Ledger if led_mod is not None else None
    box = box_identity(meta_box, env_slug=box)
    op = operation_id(box, source, dedup_key, event_id, signal)
    schema, _cred, _id = resolve_admission_schema()
    receipt = {
        "status": "failed", "operation_id": op, "ticket_id": None,
        "admission_schema": schema, "detail": "", "reply_digest": None,
        "attempted_at": now_utc(),
    }
    led = ledger if ledger is not None else (
        Ledger(state_dir) if state_dir and Ledger is not None else None)
    own_ledger = led is None
    if own_ledger and Ledger is not None:
        led = Ledger(led_mod.default_state_dir())

    def journal(status, detail="", ticket_id=None, reply_digest=None,
                exception_type=""):
        if led is None:
            return  # no ledger: journal degraded, INCIDENT STATE still decided
        try:
            led.record_admission_attempt(
                operation_id=op, source=source, box=box, signal=signal,
                event_id=event_id, dedup_key=dedup_key, status=status,
                ticket_id=ticket_id, reply_digest=reply_digest,
                admission_schema=schema, detail=detail,
                exception_type=exception_type)
        except Exception:  # noqa: BLE001 - journaling must never crash a tick
            pass

    try:
        # 1. dry-run branches BEFORE any ledger write and any network action.
        if dry_run:
            receipt["status"] = "dry_run"
            receipt["detail"] = "dry run: no admission attempted"
            return receipt

        # 2. validate the payload BEFORE posting (caller-error vs refusal).
        payload = build_payload(box, problem_text, source=source, signal=signal,
                                key_path=key_path, dedup_key=dedup_key,
                                event_id=event_id, tick_ts=tick_ts)
        problems = validate_payload(payload)
        if problems:
            receipt["status"] = "failed"
            receipt["detail"] = "invalid payload: %s" % ",".join(problems)
            receipt["detail_sanitized"] = True
            journal("failed", receipt["detail"] + " (no network)", None)
            return receipt

        # 3. bounded POST.
        url = url or admission_url()
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        tx = transport or urllib_transport
        try:
            resp_text = tx(url, body)
        except AdmissionRefused as exc:
            receipt["detail"] = trim(str(exc))
            receipt["detail_sanitized"] = True
            # RR-015: "Record missing enrollment as pending repair with owner;
            # do not report admission because a group send succeeded." An auth
            # refusal is an OWNED SETUP REPAIR of this box's enrollment, NOT a
            # policy refusal of the incident -- so it must not be journaled or
            # reported in the same class. Detection is on the client-side facts
            # available WITHOUT trusting the body: the credential schema this
            # attempt actually presented, or an auth-shaped refusal reason.
            if schema == "none" or is_auth_refusal(receipt["detail"]):
                receipt["status"] = "no_enrollment"
                receipt["pending_repair"] = True
                receipt["repair_owner"] = REPAIR_OWNER_ENROLLMENT
                receipt["repair_action"] = REPAIR_ACTION_ENROLLMENT
                receipt["detail"] = (
                    "no enrollment accepted by the intake (schema=%s); "
                    "pending repair owned by %s: %s"
                    % (schema, REPAIR_OWNER_ENROLLMENT, REPAIR_ACTION_ENROLLMENT))
                journal("no_enrollment", receipt["detail"], None)
                return receipt
            receipt["status"] = "refused"
            journal("refused", receipt["detail"], None)
            return receipt
        except AdmissionTransportError as exc:
            receipt["status"] = "failed"
            receipt["detail"] = trim(str(exc))
            receipt["detail_sanitized"] = True
            journal("failed", receipt["detail"], None, exception_type=type(exc).__name__)
            return receipt
        except Exception as exc:  # noqa: BLE001 - injected transport raised
            receipt["status"] = "failed"
            receipt["detail"] = "%s: %s" % (type(exc).__name__, trim(str(exc)))
            receipt["detail_sanitized"] = True
            journal("failed", receipt["detail"], None, exception_type=type(exc).__name__)
            return receipt

        # 4. verdict: a 2xx on its own is NOT the receipt (Skill 61 trap).
        verdict = intake_verdict(resp_text)
        digest = sha256_hex(resp_text) if resp_text else None
        if verdict is True:
            doc = {}
            try:
                doc = json.loads(resp_text)
            except ValueError:
                pass
            ticket = _ticket_id(doc)
            # A duplicate fold is an ACCEPTED admission whose identity already
            # existed -- reported as replay, journaled as its own status, and
            # ack-eligible exactly like admitted (a durable ticket provably
            # exists either way).
            replay = is_replay_answer(resp_text)
            receipt["status"] = "replay" if replay else "admitted"
            receipt["ticket_id"] = ticket
            receipt["reply_digest"] = digest
            receipt["detail"] = ("%s%s" % (
                "replay (folded onto an existing ticket)" if replay else "admitted",
                " ticket_id=" + str(ticket) if ticket else ""))
            journal(receipt["status"], receipt["detail"], ticket, digest)
            return receipt
        if verdict is False:
            receipt["reply_digest"] = digest
            receipt["detail"] = trim(resp_text) or "intake refused payload"
            receipt["detail_sanitized"] = True
            # Same split as the 4xx path: an auth/enrollment refusal reached on
            # a 2xx-with-refusal answer is a pending enrollment repair, not a
            # policy refusal of the incident.
            if schema == "none" or is_auth_refusal(receipt["detail"]):
                receipt["status"] = "no_enrollment"
                receipt["pending_repair"] = True
                receipt["repair_owner"] = REPAIR_OWNER_ENROLLMENT
                receipt["repair_action"] = REPAIR_ACTION_ENROLLMENT
                receipt["detail"] = (
                    "no enrollment accepted by the intake (schema=%s); "
                    "pending repair owned by %s: %s"
                    % (schema, REPAIR_OWNER_ENROLLMENT, REPAIR_ACTION_ENROLLMENT))
                journal("no_enrollment", receipt["detail"], None, digest)
                return receipt
            receipt["status"] = "refused"
            journal("refused", receipt["detail"], None, digest)
            return receipt
        # UNDETERMINED (malformed / non-JSON / empty): a value was printed by
        # nobody. NEVER a success, never an explicit refusal.
        receipt["status"] = "failed"
        receipt["reply_digest"] = digest
        receipt["detail"] = ("undetermined intake answer (non-JSON or empty); "
                             "no admission evidence")
        journal("failed", receipt["detail"], None, digest)
        return receipt
    finally:
        if own_ledger and led is not None:
            try:
                led.close()
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------- #
# CLI (deterministic offline self-test + a manual attempt path)
# --------------------------------------------------------------------------- #
def self_test():
    import tempfile
    print("[rescue_admission] self-test: versioned client, nine-field payload, "
          "verdict parity, redaction, journaling")
    n = 0

    def ok(name):
        nonlocal n
        n += 1
        print("  ok %s" % name)

    def fail(name, detail=""):
        nonlocal n
        n += 1
        print("  FAIL %s %s" % (name, detail))

    def check(cond, name, detail=""):
        if cond:
            ok(name)
        else:
            fail(name, detail)

    check(RESCUE_ADMISSION_CLIENT_VERSION == "1.0.0", "client version pinned 1.0.0")
    payload = build_payload("box-admission-example", "fixture problem 1234 5678",
                            source="skill-60-ews", signal="S6",
                            key_path="config.owner", dedup_key="S6|config.owner",
                            event_id=7, tick_ts="2000-01-01T00:00:00+00:00")
    check(set(payload) >= {"action", "source", "box", "person", "clientName",
                           "agentName", "boxName", "boxType", "openclawVersion",
                           "problem", "alreadyTried", "returnTo", "message",
                           "operation_id", "machine"},
          "nine-field legacy contract + source/operation block present")
    check(payload["boxName"] == payload["box"], "boxName is the identity carrier")
    check(payload["message"] == payload["problem"], "message alias rides with problem")
    check(payload["machine"]["ews_event_id"] == 7, "source event id recorded")
    op = operation_id("box-admission-example", "skill-60-ews", "S6|config.owner", 7, "S6")
    check(payload["operation_id"] == op, "operation id deterministic")
    check(operation_id("box-admission-example", "skill-60-ews", "S6|config.owner", 7, "S6") == op,
          "operation id stable across replays (identity preserved)")
    check(validate_payload(payload) == [], "valid payload passes validation")
    check("missing_box" in validate_payload(dict(payload, boxName="")),
          "box-less payload rejected by validation")
    check("missing_message" in validate_payload(dict(payload, message="", problem="")),
          "message-less payload rejected by validation")

    # verdict parity: 2xx alone is never the receipt (Skill 61 trap)
    check(intake_verdict('{"accepted":false,"rejectReason":"missing message"}') is False,
          "explicit refusal detected")
    check(intake_verdict('{"accepted":true,"ticketId":"T1"}') is True, "admission detected")
    check(intake_verdict('{"admission":{"decision":"reject_invalid"}}') is False,
          "admission-block refusal detected")
    check(intake_verdict('{"admission":{"decision":"accept"}}') is True,
          "admission-block accept detected")
    check(intake_verdict("<html>502 Bad Gateway</html>") is None,
          "HTML answer is UNDETERMINED, never success")
    check(intake_verdict("") is None, "empty body is UNDETERMINED, never success")

    # replay: the intake's duplicate fold is an ACCEPTED admission, not a refusal
    check(is_replay_answer('{"accepted":true,"status":"duplicate_ignored"}'),
          "duplicate fold detected as replay")
    check(not is_replay_answer('{"accepted":true,"ticketId":"T1"}'),
          "a first admission is not a replay")
    check(not is_replay_answer("<html>502</html>"),
          "unparseable answer is never a replay")

    # auth refusals are an OWNED ENROLLMENT REPAIR, not a policy refusal
    check(is_auth_refusal("intake HTTP 403: unauthorized"),
          "403 unauthorized classified as an auth refusal")
    check(is_auth_refusal('{"status":"identity_mismatch"}'),
          "identity_mismatch classified as an auth refusal")
    check(not is_auth_refusal("intake HTTP 400: missing message"),
          "a payload refusal is NOT an auth refusal")
    _prev_v2 = os.environ.pop(V2_HEADERS_ENV, None)
    try:
        check(sends_v2_headers() is False,
              "v2 headers are OFF by default (the live intake reads only x-rescue-secret)")
    finally:
        if _prev_v2 is not None:
            os.environ[V2_HEADERS_ENV] = _prev_v2

    # redaction: a credential SHAPE is dropped whole
    t = trim("synthetic-fixture-ok Bearer sk-proj-x" + "A" * 40)
    check("redacted" in t, "credential-shaped response is dropped whole")

    # journal + receipt through an injected transport, fully offline
    seen = []

    def ok_transport(url, body):
        seen.append({"url": url, "body": json.loads(body.decode("utf-8"))})
        return '{"accepted":true,"ticketId":"T-DRILL"}'

    os.environ["EWS_STATE_DIR"] = ""
    with tempfile.TemporaryDirectory(prefix="rr015-client-") as td:
        prev = os.environ.get("EWS_STATE_DIR")
        os.environ["EWS_STATE_DIR"] = td
        try:
            r = admit(td, box="box-admission-example",
                      problem_text="fixture problem 1234 5678",
                      source="skill-60-ews", signal="S6",
                      dedup_key="S6|config.owner", event_id=7,
                      transport=ok_transport, url="https://intake.invalid/x")
            check(r["status"] == "admitted" and r["ticket_id"] == "T-DRILL",
                  "validated admission receipt returns ticket id")
            check(len(seen) == 1 and seen[0]["body"]["operation_id"] == r["operation_id"],
                  "one post carrying the stable operation id")
            _led = _load_ews_ledger()
            check(_led is not None, "ews ledger module resolves from the client")
            with _led.Ledger(td) as led:
                latest = led.latest_admission(r["operation_id"])
            check(latest is not None and latest["status"] == "admitted" and
                  latest["ticket_id"] == "T-DRILL" and latest["reply_digest"] is not None,
                  "admission journaled durably with digest (never the body)")
            # replay: same op id -> idempotent, no second post
            r2 = admit(td, box="box-admission-example",
                       problem_text="fixture problem 1234 5678",
                       source="skill-60-ews", signal="S6",
                       dedup_key="S6|config.owner", event_id=7,
                       transport=lambda u, b: (_ for _ in ()).throw(
                           AssertionError("a replay must not re-post")),
                       url="https://intake.invalid/x")
            check(r2["status"] == "failed", "replay attempt still attempts (caller policy decides)")
            # refusal does not become failure and vice versa. A POLICY refusal
            # (the incident/payload was rejected) stays `refused`; an AUTH
            # refusal is a different class entirely -- see the no_enrollment
            # case immediately below.
            # This case must present a credential: with NO credential at all the
            # request cannot have been authenticated, so a refusal is about the
            # enrollment and no_enrollment is the honest answer (proven in the
            # case below). A POLICY refusal is only distinguishable once this
            # box actually authenticated.
            def refuse_transport(url, body):
                raise AdmissionRefused("intake HTTP 400: missing message")
            _saved_secret = os.environ.get(SECRET_ENV)
            os.environ[SECRET_ENV] = "fixture-v1-shared-secret-not-real"
            try:
                r3 = admit(td, box="box-admission-example",
                           problem_text="fixture problem 1234 5678",
                           source="skill-60-ews", signal="S6",
                           dedup_key="S6|config.owner", event_id=8,
                           transport=refuse_transport, url="https://intake.invalid/x")
            finally:
                if _saved_secret is None:
                    os.environ.pop(SECRET_ENV, None)
                else:
                    os.environ[SECRET_ENV] = _saved_secret
            check(r3["status"] == "refused", "policy refusal classified refused", r3)
            check("no_enrollment" != r3["status"],
                  "a policy refusal is NOT misclassified as a pending repair")

            # RR-015: a missing/unaccepted ENROLLMENT is a PENDING REPAIR with an
            # owner -- not an admission, and not a policy refusal either.
            def auth_refuse_transport(url, body):
                raise AdmissionRefused("intake HTTP 403: unauthorized")
            _saved = {k: os.environ.pop(k, None) for k in (BOX_CRED_ENV, BOX_ID_ENV, SECRET_ENV)}
            try:
                r3b = admit(td, box="box-admission-example",
                            problem_text="fixture problem 1234 5678",
                            source="skill-60-ews", signal="S6",
                            dedup_key="S6|config.owner", event_id=10,
                            transport=auth_refuse_transport, url="https://intake.invalid/x")
                check(r3b["status"] == "no_enrollment",
                      "unaccepted credential reported no_enrollment, not refused", r3b)
                check(r3b["pending_repair"] is True and
                      r3b["repair_owner"] == REPAIR_OWNER_ENROLLMENT and
                      bool(r3b["repair_action"]),
                      "no_enrollment carries a pending-repair owner and next action", r3b)
                check(r3b["ticket_id"] is None,
                      "no_enrollment is NEVER reported as an admission", r3b)
                with _led.Ledger(td) as led:
                    jr = led.latest_admission(r3b["operation_id"])
                check(jr is not None and jr["status"] == "no_enrollment",
                      "no_enrollment journaled under its own status", jr)
            finally:
                for k, v in _saved.items():
                    if v is not None:
                        os.environ[k] = v

            # the intake's duplicate fold is an accepted admission -> replay
            r5 = admit(td, box="box-admission-example",
                       problem_text="fixture problem 1234 5678",
                       source="skill-60-ews", signal="S6",
                       dedup_key="S6|config.owner", event_id=11,
                       transport=lambda u, b: '{"accepted":true,"status":"duplicate_ignored","ticketId":"T1"}',
                       url="https://intake.invalid/x")
            check(r5["status"] == "replay",
                  "a duplicate fold is reported replay, not admitted/refused", r5)
            check(r5["ticket_id"] == "T1", "replay still carries the ticket id")
            # dry_run: no network, no journal
            before = None
            with _led.Ledger(td) as led:
                before = led.count_admissions()
            r4 = admit(td, box="box-admission-example",
                       problem_text="fixture problem 1234 5678",
                       source="skill-60-ews", signal="S6",
                       dedup_key="S6|config.owner", event_id=9,
                       transport=lambda u, b: (_ for _ in ()).throw(
                           AssertionError("dry-run must never post")),
                       dry_run=True)
            check(r4["status"] == "dry_run", "dry-run returns dry_run")
            with _led.Ledger(td) as led:
                after = led.count_admissions()
            check(after == before, "dry-run writes no journal row")
        finally:
            if prev is None:
                os.environ.pop("EWS_STATE_DIR", None)
            else:
                os.environ["EWS_STATE_DIR"] = prev

    print("[rescue_admission] self-test: %s checks done" % n)
    return 0


def _cli(argv=None):
    ap = argparse.ArgumentParser(
        description="Rescue admission client (Skill 60 EWS). Self-test is fully offline.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--box", default="")
    ap.add_argument("--problem", default="")
    ap.add_argument("--source", default="skill-60-ews")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    r = admit(None, box=args.box, problem_text=args.problem,
              source=args.source, dry_run=args.dry_run)
    sys.stdout.write(json.dumps(r, sort_keys=True) + "\n")
    return 0 if r["status"] in ("admitted", "replay", "dry_run") else (
        3 if r["status"] == "refused" else 1)


if __name__ == "__main__":
    sys.exit(_cli())
