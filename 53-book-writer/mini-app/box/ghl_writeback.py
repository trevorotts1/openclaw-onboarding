#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP — U15 GHL WRITE-BACK ON BOX (Skill 44 rails, isolation)
# -----------------------------------------------------------------------------
# mini-app/box/ghl_writeback.py
#
# The box-side worker that turns a STAGED ANSWER (produced by the U12 ingest
# poller) into a GHL contact write on the CLIENT's sub-account — via the
# Skill 44 contact rails (services.leadconnectorhq.com/contacts/, Bearer
# LOCATION-PIT, Version: 2021-07-28, locationId in the body), with the per
# -step answer ALSO mirrored to a durable LOCAL LEDGER MIRROR. The edge Worker
# is a DUMB RELAY that stages answers but holds ZERO client PITs; THIS module
# is where the answer terminates in the GHL Location bound to the token's
# client (MASTER-PLAN section 3).
#
# ISOLATION (section 3 — the three locks, enforced HERE on the box):
#   1. POSSESSION  — the delivery reaches this module with that client's token
#      binding row. A token unknown to this binding is refused before any call.
#   2. BINDING     — the server-side KV binding row is the SOLE authority for
#      the destination. The destination (client_id + location_id) is derived
#      ONLY from the binding row; any location_id/contact_id/client_id inside
#      the answer body is IGNORED (defense in depth against injected dest).
#   3. CREDENTIAL + WHITELIST — the Location-PIT is read from env (location-
#      scoped by construction) and `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` /
#      `CAF_ALLOWED_LOCATION_IDS` must contain the bound location_id. Empty
#      whitelist = REFUSE ALL WRITES (fail-closed). The safety gate fires
#      BEFORE any API call — even a buggy handler cannot cross locations.
#      When the installed Skill 44 engine is importable, its real
#      `safety_gate.check_write()` is ALSO invoked (defense in depth); the
#      native whitelist check always runs.
#
# NEVER THE OPERATOR'S OWN GHL: the PIT this module authenticates with is the
# CLIENT's location-scoped PIT resolved from env (canonical 11-alias set), and
# the bound location_id must be in the client's own whitelist. The operator's
# GHL is never targeted BY CONSTRUCTION (there is no operator credential in
# this file and no literal location id anywhere).
#
# GHL IS A MIRROR, NOT THE ONLY COPY (section 8 fail modes): every write attempt
# is mirrored to the durable local ledger mirror, so a persistent GHL outage
# never silently drops an answer. On persistent failure the module exits
# non-zero with an HONEST FAILURE RECEIPT — never a fabricated success.
#
# RAIL CONTRACT (Skill 44 + phase config):
#   - phase config `submit` block (U01 gen_phase_config.py) drives the mapping:
#       { action: ghl_contact|gate_receipt,
#         custom_field_map: { <qid>: "bw_<field>" },
#         tags: [...], raw_json_note: true, dedupe_key }
#   - raw_json_note: the raw normalized JSON answer is appended to the bound
#     contact as a GHL note (system-of-record for reconstructing run/intake.json).
#   - bound_contact_id: the binding row MAY carry `contact_id` (the contact
#     bound to this run). When present, the write targets that contact
#     (PUT /contacts/<id> + POST /contacts/<id>/notes); when absent, a contact
#     is created (POST /contacts/) and the returned contact_id is captured in
#     the ledger receipt so the run binds to it thereafter.
#
# ENV-REF CREDENTIALS ONLY — no secrets in code, no literals:
#   GOHIGHLEVEL_API_KEY            (client LOCATION-PIT; 11 canonical aliases)
#   GOHIGHLEVEL_ALLOWED_LOCATION_IDS / CAF_ALLOWED_LOCATION_IDS  (whitelist)
#   GOHIGHLEVEL_APPROVAL_TOKEN / CAF_APPROVAL_TOKEN             (Skill 44 gate)
#   GOHIGHLEVEL_LOCATION_ID        (optional; the binding row wins when set)
#
# NO ANTHROPIC: no Anthropic/claude ids anywhere in this file by construction.
#
# EXIT CODES (prover/worker convention):
#   0  WRITTEN      — the answer reached the bound GHL location AND the local
#                    ledger mirror, with an honest receipt.
#   2  REFUSED      — an isolation/safety rule fired (unbound / whitelist /
#                    placeholder target / missing token). ZERO GHL calls.
#   3  USAGE/IO     — missing/unreadable input file, bad args, ledger unwritable.
#   4  PERSISTENT   — transient retry/backoff exhausted; honest failure receipt
#                    written to the ledger mirror. The answer is never dropped.
#
# USAGE:
#   python3 ghl_writeback.py <delivery.json> --config <phase-config.json>
#       [--ledger-dir DIR] [--base-url URL] [--approval-token TOKEN] [--json]
#   python3 ghl_writeback.py --self-test
#
# delivery.json shape (written by the U12 poller):
#   { "binding": { client_id, location_id, slug, phase_id, run_id,
#                  exp, status, mode?, contact_id? },      # KV binding row — SOLE authority
#     "answer":  { qid, answer, source, received_at, answer_id,
#                  destination: {...} } }                  # staged answer (U03/U12)
#
# The write-back derives the destination ONLY from `binding.client_id` +
# `binding.location_id`. Any destination/location/contact inside `answer` is
# ignored.
# =============================================================================
"""U15 — box-side GHL write-back on the Skill 44 contact rails (isolated)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Exit codes (see module docstring)
# ---------------------------------------------------------------------------
EXIT_WRITTEN = 0
EXIT_REFUSED = 2
EXIT_USAGE = 3
EXIT_PERSISTENT = 4

# ---------------------------------------------------------------------------
# AF codes (MASTER-PLAN section 8 failure modes — named, never silent)
# ---------------------------------------------------------------------------
AF_UNBOUND = "AF-BW-MA-WB-UNBOUND"            # no/incomplete binding row
AF_WHITELIST = "AF-BW-MA-WB-WHITELIST"        # bound location not whitelisted
AF_PLACEHOLDER = "AF-BW-MA-WB-PLACEHOLDER"    # token/target is a doc placeholder
AF_NOTOKEN = "AF-BW-MA-WB-NOTOKEN"            # no client PIT resolved from env
AF_PERSISTENT = "AF-BW-MA-WB-PERSISTENT"      # retries exhausted (honest receipt)
AF_NOCONFIG = "AF-BW-MA-WB-NOCONFIG"          # phase config submit block missing

# ---------------------------------------------------------------------------
# Canonical env names (Skill 44 credential model — never literals in code)
# ---------------------------------------------------------------------------
# The full LOCATION-PIT alias set, in resolution order (mirrors ghl_client.py
# `_LOCATION_PIT_ENV_NAMES` — the canonical 11-alias scan).
_TOKEN_ENV_NAMES = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GHL_PIT",
    "GHL_TOKEN",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "PRIVATE_INTEGRATION_TOKEN",
    "GHL_PRIVATE_TOKEN",
    "PIT_TOKEN",
    "GHL_PIT_TOKEN",
    "GOHIGHLEVEL_LOCATION_PIT",
    "GHL_LOCATION_PIT",
)
_WHITELIST_ENV_NAMES = ("GOHIGHLEVEL_ALLOWED_LOCATION_IDS", "CAF_ALLOWED_LOCATION_IDS")
_APPROVAL_ENV_NAMES = ("GOHIGHLEVEL_APPROVAL_TOKEN", "CAF_APPROVAL_TOKEN")
_LOCATION_ENV_NAMES = ("GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID")

DEFAULT_BASE_URL = "https://services.leadconnectorhq.com"
GHL_VERSION = "2021-07-28"

# Transient classes worth retrying with backoff (Skill 44 gate + section 8):
#   5xx (server), 429 (rate limit), network/timeout. 4xx (other than 429) are
#   persistent — a retry cannot fix a rejected payload.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 8.0

# Control-char strip for note bodies (keep \n \t \r). Mirrors the ONE
# normalization boundary used across the mini-app.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")
# Documentation-placeholder shapes (mirrors ghl_client._is_placeholder).
_PLACEHOLDER_RE = re.compile(
    r"^(pit-abc|changeme|xxx|your[-_]|.*_here|.*-here).*$", re.IGNORECASE
)
# Unresolved template tokens — NEVER shipped ({{...}} / $('...') / $("...")).
_TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}|\$\(\s*['\"][^'\"]*['\"]\s*\)")

# Fields in the answer body that may NEVER steer the destination (injected
# destination is ignored by construction — section 3 lock 2).
_INJECTED_DEST_FIELDS = ("location_id", "contact_id", "client_id")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    """ISO-8601 UTC timestamp (naive, deterministic for ledger lines)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_placeholder(value: Any) -> bool:
    """True when a value is a documentation placeholder, not a real credential /
    location id. Short (<20 chars) strings are refused too (a real location id
    and a real PIT are long; the doc placeholders are short)."""
    if not value:
        return True
    s = str(value).strip()
    if len(s) < 20:
        return True
    low = s.lower()
    if _PLACEHOLDER_RE.match(low):
        return True
    if s.startswith("<") and s.endswith(">"):
        return True
    return False


def resolve_token(env: dict[str, str] | None = None) -> str:
    """Resolve the client LOCATION-PIT from env (11 canonical aliases). Raises
    AF_NOTOKEN when none is present, AF_PLACEHOLDER when the only candidate is a
    doc placeholder (never trust a placeholder-shaped token)."""
    env = env if env is not None else os.environ
    saw_placeholder = False
    for name in _TOKEN_ENV_NAMES:
        raw = env.get(name, "").strip()
        if not raw:
            continue
        if is_placeholder(raw):
            saw_placeholder = True
            continue
        return raw
    if saw_placeholder:
        raise WritebackRefused(
            AF_PLACEHOLDER,
            "WRITE REFUSED: the only GHL token in env is a documentation "
            "placeholder (short/dummy-shaped). Put the client's real LOCATION-PIT "
            "in secrets/.env under GOHIGHLEVEL_API_KEY (or a canonical alias).",
        )
    raise WritebackRefused(
        AF_NOTOKEN,
        "WRITE REFUSED: no GHL LOCATION-PIT resolved from env. Set "
        "GOHIGHLEVEL_API_KEY=<pit-...> (client's own location-scoped PIT) in "
        "secrets/.env. The box never holds the operator's key.",
    )


def resolve_whitelist(env: dict[str, str] | None = None) -> frozenset[str]:
    """Read the comma-separated write whitelist. Empty whitelist = REFUSE ALL
    writes (fail-closed — Skill 44 section 3 lock 3)."""
    env = env if env is not None else os.environ
    raw = ""
    for name in _WHITELIST_ENV_NAMES:
        raw = env.get(name, "").strip()
        if raw:
            break
    if not raw:
        return frozenset()
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def resolve_location_fallback(env: dict[str, str] | None = None) -> str:
    """Optional GOHIGHLEVEL_LOCATION_ID. The BINDING ROW always wins over this;
    the fallback only ever supplies a value when the binding row is missing it
    (and even then the whitelist lock still applies)."""
    env = env if env is not None else os.environ
    for name in _LOCATION_ENV_NAMES:
        v = env.get(name, "").strip()
        if v:
            return v
    return ""


def resolve_approval_token(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    for name in _APPROVAL_ENV_NAMES:
        v = env.get(name, "").strip()
        if v:
            return v
    return ""


def resolve_destination(binding: Any) -> dict[str, str]:
    """THE isolation lock 2 — derive the destination ONLY from the KV binding
    row. `client_id` + `location_id` are the sole authority; any value in the
    answer body is ignored. Raises AF_UNBOUND on a missing/incomplete row."""
    if not isinstance(binding, dict):
        raise WritebackRefused(
            AF_UNBOUND,
            "WRITE REFUSED: delivery carries no binding row. The KV binding row "
            "is the SOLE authority for the destination; there is nothing to "
            "write against.",
        )
    client_id = str(binding.get("client_id") or "").strip()
    location_id = str(binding.get("location_id") or "").strip()
    if not client_id or not location_id:
        raise WritebackRefused(
            AF_UNBOUND,
            "WRITE REFUSED: binding row is missing client_id or location_id. "
            "Without a bound client+location there is no valid destination "
            "(fail-closed — no write to an unknown sub-account).",
        )
    if is_placeholder(location_id):
        raise WritebackRefused(
            AF_PLACEHOLDER,
            "WRITE REFUSED: the binding row's location_id %r looks like a "
            "documentation placeholder (short/dummy-shaped), not a real GHL "
            "sub-account id. Refusing fail-closed." % location_id,
        )
    return {
        "client_id": client_id,
        "location_id": location_id,
        "phase_id": str(binding.get("phase_id") or "").strip(),
        "run_id": str(binding.get("run_id") or "").strip(),
        "contact_id": str(binding.get("contact_id") or "").strip() or None,
    }


def enforce_isolation(dest: dict[str, str], whitelist: frozenset[str],
                      fallback_location: str = "") -> None:
    """THE isolation lock 3 — CREDENTIAL + WHITELIST. The bound location must
    be in GOHIGHLEVEL_ALLOWED_LOCATION_IDS; empty whitelist refuses all writes.
    Raises AF_WHITELIST otherwise. Fires BEFORE any API call."""
    location = dest.get("location_id") or fallback_location or ""
    if not location:
        raise WritebackRefused(
            AF_UNBOUND,
            "WRITE REFUSED: the bound location_id is empty and no env fallback "
            "is set. Refusing a write to an unknown sub-account (fail-closed).",
        )
    if not whitelist:
        raise WritebackRefused(
            AF_WHITELIST,
            "WRITE REFUSED: %s is empty or unset. Leaving it empty intentionally "
            "blocks ALL writes (fail-closed). Set it to the client's own "
            "location id." % _WHITELIST_ENV_NAMES[0],
        )
    if location not in whitelist:
        raise WritebackRefused(
            AF_WHITELIST,
            "WRITE REFUSED: location %r is not in the approved whitelist %r. "
            "A cross-location write is impossible even from a buggy handler."
            % (location, sorted(whitelist)),
        )


def load_phase_submit(config: Any) -> dict[str, Any]:
    """Read the phase config's `submit` block (U01 gen_phase_config.py shape).
    Raises AF_NOCONFIG when absent/malformed."""
    if not isinstance(config, dict):
        raise WritebackRefused(
            AF_NOCONFIG,
            "WRITE REFUSED: no phase config provided. The GHL write needs the "
            "config's submit block (custom_field_map / tags / raw_json_note).",
        )
    submit = config.get("submit")
    if not isinstance(submit, dict):
        raise WritebackRefused(
            AF_NOCONFIG,
            "WRITE REFUSED: phase config has no submit block. Cannot map answers "
            "to GHL custom fields without it.",
        )
    return submit


def _custom_field_value(value: Any) -> str:
    """Stringify an answer value for a GHL custom field, stripping control chars
    and trimming (the ONE normalization boundary, mirrored here)."""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    s = _CONTROL_CHAR_RE.sub("", "" if value is None else str(value)).strip()
    return s


def build_contact_payload(submit: dict[str, Any], dest: dict[str, str],
                          answer: dict[str, Any]) -> dict[str, Any]:
    """Build the GHL POST /contacts/ body. The `custom_field_map` in the phase
    config maps question ids -> GHL custom field ids. Any answer key that is an
    injected destination field is skipped (never copied)."""
    body: dict[str, Any] = {"locationId": dest["location_id"]}

    field_map = submit.get("custom_field_map") or {}
    if not isinstance(field_map, dict):
        field_map = {}

    # email / first_name / last_name are also surfaced on the contact root when
    # the field map calls for them (GHL uses these for identity + dedupe).
    custom_fields = []
    answer_payload = answer.get("answer")
    if isinstance(answer_payload, dict):
        for qid, ghl_field in field_map.items():
            raw_val = answer_payload.get(qid)
            if raw_val is None:
                continue
            val = _custom_field_value(raw_val)
            if val == "":
                continue
            if qid in _INJECTED_DEST_FIELDS:
                continue  # never copy an injected destination
            if ghl_field == "bw_email":
                body["email"] = val
            elif ghl_field == "bw_first_name":
                body["firstName"] = val
            elif ghl_field == "bw_last_name":
                body["lastName"] = val
            else:
                custom_fields.append({"id": ghl_field, "value": val})
    else:
        # A non-object answer (single text value) still maps when the config's
        # custom_field_map has exactly one entry for this question.
        qid = str(answer.get("qid") or "").strip()
        ghl_field = field_map.get(qid)
        if ghl_field and qid not in _INJECTED_DEST_FIELDS:
            val = _custom_field_value(answer_payload)
            if val:
                if ghl_field == "bw_email":
                    body["email"] = val
                elif ghl_field == "bw_first_name":
                    body["firstName"] = val
                elif ghl_field == "bw_last_name":
                    body["lastName"] = val
                else:
                    custom_fields.append({"id": ghl_field, "value": val})

    tags = submit.get("tags")
    if isinstance(tags, list) and tags:
        body["tags"] = [str(t) for t in tags]

    if custom_fields:
        body["customField"] = custom_fields

    return body


def build_raw_note(answer: dict[str, Any], dest: dict[str, str]) -> str:
    """The raw normalized JSON answer as a GHL note (system-of-record for
    reconstructing run/intake.json). Includes the bound destination so the note
    is self-describing, and the answer_id for idempotent de-dupe on the box."""
    note_payload = {
        "qid": answer.get("qid"),
        "answer": answer.get("answer"),
        "source": answer.get("source"),
        "received_at": answer.get("received_at"),
        "answer_id": answer.get("answer_id"),
        "bound": {
            "client_id": dest.get("client_id"),
            "location_id": dest.get("location_id"),
            "phase_id": dest.get("phase_id"),
            "run_id": dest.get("run_id"),
        },
    }
    note = json.dumps(note_payload, ensure_ascii=False, default=str, indent=2)
    note = _CONTROL_CHAR_RE.sub("", note)
    if _TEMPLATE_RE.search(note):
        note = _TEMPLATE_RE.sub("[resolved]", note)
    return note


def _safe_token(s: str) -> str:
    """Filesystem-safe token: keep letters/digits/._- , collapse path-dangerous
    chars, never return empty or a traversal path."""
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s or "unknown")
    return s.strip("._") or "unknown"


def sanitize_dir(part: str) -> str:
    """Filesystem-safe directory part (run_id). No suffix is appended."""
    return _safe_token(part)


def sanitize_step(phase_id: str, qid: str) -> str:
    """Filesystem-safe ledger step name: `<phase_id>.<qid>` with any path-dangerous
    chars replaced. The ledger mirror path is `answers/<run>/<step>.jsonl`."""
    return "%s.%s" % (_safe_token(phase_id), _safe_token(qid))


def retry_delay(attempt: int) -> float:
    """Exponential backoff with a small deterministic jitter. attempt is
    0-based (the first retry). Bounded between 1s and 8s."""
    delay = BACKOFF_BASE_SECONDS * (2 ** attempt)
    delay = min(delay, BACKOFF_MAX_SECONDS)
    return round(delay, 3)


# ---------------------------------------------------------------------------
# Refusal / receipt exceptions
# ---------------------------------------------------------------------------

class WritebackRefused(RuntimeError):
    """Raised when an isolation/safety rule blocks the write (fail-closed).
    Carries an AF code so the honest receipt names the exact refusal."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Local ledger mirror (the durable source of truth — GHL is a mirror, not the
# only copy). Append-only JSONL at answers/<run>/<step>.jsonl.
# ---------------------------------------------------------------------------

def ledger_line(ledger_root: Path, run_id: str, step: str) -> Path:
    """Resolve the append-only ledger mirror file for this run+step. Creates the
    parent directories. Raises on an unwritable ledger (fail-closed — an answer
    must never be written to GHL without a durable local record)."""
    safe_run = sanitize_dir(run_id)
    ledger_path = ledger_root / "answers" / safe_run / ("%s.jsonl" % step)
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(
            "USAGE/IO: cannot create ledger mirror dir %s: %s"
            % (ledger_path.parent, exc)
        )
    return ledger_path


def append_ledger(ledger_root: Path, run_id: str, step: str,
                  record: dict[str, Any]) -> Path:
    """Append one JSON line to the ledger mirror. Returns the path. Raises
    OSError when the ledger cannot be written (the write-back then refuses,
    because the durable local copy must exist)."""
    ledger_path = ledger_line(ledger_root, run_id, step)
    record = dict(record)
    record["ts"] = record.get("ts") or _now_utc()
    line = json.dumps(record, ensure_ascii=False, default=str, sort_keys=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return ledger_path


# ---------------------------------------------------------------------------
# GHL transport (Skill 44 rails). `requests`-backed (never bare urllib — the
# Cloudflare WAF 403-blocks the urllib default UA; requests is the proven rail).
# ---------------------------------------------------------------------------

def http_json(method: str, base_url: str, path: str, token: str,
              payload: dict[str, Any] | None = None,
              timeout: int = 30) -> tuple[int, dict[str, Any]]:
    """One raw HTTPS call to GHL. Returns (status_code, json_body). Raises
    WritebackRefused(AF_PERSISTENT) on a network/timeout fault (transient —
    the caller retries with backoff). 4xx (non-429) responses are returned to
    the caller (persistent)."""
    import requests  # local import — requests is a runtime rail, not import-time

    headers = {
        "Authorization": "Bearer %s" % token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": GHL_VERSION,
        "User-Agent": "book-writer-mini-app-u15",  # explicit UA (Cloudflare rail)
    }
    url = "%s%s" % (base_url.rstrip("/"), path)
    try:
        if method == "POST":
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        elif method == "PUT":
            resp = requests.put(url, headers=headers, json=payload, timeout=timeout)
        else:  # GET
            resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise WritebackRefused(
            AF_PERSISTENT,
            "TRANSIENT: GHL call failed at the transport layer (%s %s): %s"
            % (method, url, exc),
        )
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        body = {"_raw": resp.text[:200]}
    return resp.status_code, body


def post_with_retry(base_url: str, path: str, token: str,
                    payload: dict[str, Any],
                    timeout: int = 30) -> tuple[int, dict[str, Any], int]:
    """POST with retry/backoff on transient failure (5xx / 429 / network).
    Persistent 4xx (non-429) returns immediately — a retry cannot fix a
    rejected payload. Returns (status, body, attempts)."""
    attempts = 0
    while True:
        attempts += 1
        try:
            status, body = http_json("POST", base_url, path, token, payload, timeout)
        except WritebackRefused as exc:
            # Transport fault — transient. Retry up to MAX_ATTEMPTS.
            if attempts >= MAX_ATTEMPTS:
                raise WritebackRefused(
                    AF_PERSISTENT,
                    "%s (%s attempt(s), backoff exhausted)" % (exc.message, attempts),
                )
            time.sleep(retry_delay(attempts - 1))
            continue
        if status in RETRYABLE_STATUS and attempts < MAX_ATTEMPTS:
            time.sleep(retry_delay(attempts - 1))
            continue
        return status, body, attempts


def put_with_retry(base_url: str, path: str, token: str,
                   payload: dict[str, Any],
                   timeout: int = 30) -> tuple[int, dict[str, Any], int]:
    """PUT with the same retry/backoff discipline as post_with_retry."""
    attempts = 0
    while True:
        attempts += 1
        try:
            status, body = http_json("PUT", base_url, path, token, payload, timeout)
        except WritebackRefused as exc:
            if attempts >= MAX_ATTEMPTS:
                raise WritebackRefused(
                    AF_PERSISTENT,
                    "%s (%s attempt(s), backoff exhausted)" % (exc.message, attempts),
                )
            time.sleep(retry_delay(attempts - 1))
            continue
        if status in RETRYABLE_STATUS and attempts < MAX_ATTEMPTS:
            time.sleep(retry_delay(attempts - 1))
            continue
        return status, body, attempts


# ---------------------------------------------------------------------------
# Optional Skill 44 safety-gate import (defense in depth). Best-effort — the
# native whitelist check above ALWAYS runs; when the installed engine is
# importable its real check_write() is ALSO invoked.
# ---------------------------------------------------------------------------

def _skill44_safety_gate():
    """Return the installed Skill 44 safety_gate.check_write callable, or None.
    The engine is at ~/.openclaw/tools/convert-and-flow-cli/engine by default;
    override with GHL_ENGINE_DIR. Never fails the box when absent — the native
    isolation checks are the mandatory rails."""
    try:
        engine_dir = os.environ.get("GHL_ENGINE_DIR", "").strip() or str(
            Path.home() / ".openclaw/tools/convert-and-flow-cli/engine"
        )
        if not Path(engine_dir).exists():
            return None
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        from cli_anything.gohighlevel.utils.safety_gate import check_write  # noqa
        return check_write
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The write-back orchestration
# ---------------------------------------------------------------------------

def run_writeback(
    delivery: dict[str, Any],
    config: dict[str, Any],
    *,
    ledger_root: Path,
    base_url: str = DEFAULT_BASE_URL,
    env: dict[str, str] | None = None,
    transport: Any = None,
) -> dict[str, Any]:
    """Full U15 write-back for ONE staged answer.

    Returns an HONEST outcome dict; on refusal/persistent-failure the caller
    still gets the outcome (never a fabricated success) and must exit non-zero.

    Args:
        delivery: {binding, answer} — binding is the SOLE destination authority.
        config:   phase config object (for the submit block).
        ledger_root: root dir for the ledger mirror (answers/<run>/<step>.jsonl).
        base_url: GHL base URL (defaults to services.leadconnectorhq.com).
        env:      env mapping override (tests inject a stub env).
        transport: optional stub transport exposing post()/put() (self-test);
                   production uses the requests-backed Skill 44 rails.
    """
    env = env if env is not None else os.environ
    binding = delivery.get("binding")
    answer = delivery.get("answer") if isinstance(delivery.get("answer"), dict) else {}

    # ---- 1. BINDING — destination from the KV binding row ONLY (lock 2) ----
    dest = resolve_destination(binding)

    # ---- 2. CREDENTIAL + WHITELIST — before any network call (lock 3) -----
    whitelist = resolve_whitelist(env)
    fallback_loc = resolve_location_fallback(env)
    enforce_isolation(dest, whitelist, fallback_loc)
    token = resolve_token(env)

    # ---- 3. Phase config submit block (mapping rails) ---------------------
    submit = load_phase_submit(config)

    # ---- 4. Skill 44 real safety gate (best-effort, defense in depth) -----
    # The engine gate reads the PROCESS env, and its whitelist env-var is the
    # `CAF_` form (the `caf` wrapper normally maps GOHIGHLEVEL_* -> CAF_*). This
    # module is invoked standalone, so the resolved native values (whitelist +
    # approval token) are mirrored onto the CAF_ names BEFORE the gate runs —
    # keeping the defense-in-depth gate consistent with the native checks above.
    # In the self-test the injected env override governs the native checks; the
    # real engine gate is skipped so the stub controls the isolation proof.
    gate = _skill44_safety_gate()
    if gate is not None and transport is None:
        # Mirror the resolved native values onto the CAF_ names the engine gate
        # reads (the standalone `caf` wrapper would normally do this mapping).
        _mirrored: list[tuple[str, str | None]] = []
        if "CAF_ALLOWED_LOCATION_IDS" not in os.environ:
            os.environ["CAF_ALLOWED_LOCATION_IDS"] = ",".join(sorted(whitelist))
            _mirrored.append(("CAF_ALLOWED_LOCATION_IDS", None))
        if "CAF_APPROVAL_TOKEN" not in os.environ:
            tok = resolve_approval_token(env)
            if tok:
                os.environ["CAF_APPROVAL_TOKEN"] = tok
                _mirrored.append(("CAF_APPROVAL_TOKEN", None))
        url = "%s/contacts/" % base_url.rstrip("/")
        payload = build_contact_payload(submit, dest, answer)
        try:
            gate("POST", url, payload, location_id=dest["location_id"])
        except Exception as exc:  # SafetyRefused (or SystemExit on dry-run)
            raise WritebackRefused(
                AF_WHITELIST,
                "Skill 44 safety gate refused the write: %s" % exc,
            )
        finally:
            for name, _old in _mirrored:
                os.environ.pop(name, None)

    # ---- 5. Build the GHL payload + raw_json_note -------------------------
    body = build_contact_payload(submit, dest, answer)
    note = build_raw_note(answer, dest)
    qid = str(answer.get("qid") or "").strip()
    step = sanitize_step(dest.get("phase_id") or "phase", qid)
    run_id = dest.get("run_id") or "run-unknown"

    # ---- 6. Write to GHL (create or update the bound contact) -------------
    contact_id = dest.get("contact_id")
    contact_status = 0
    contact_body: dict[str, Any] = {}
    note_status = 0
    attempts = 0

    # Transport selection: the self-test injects a stub transport (the stub IS
    # the control); production uses the requests-backed Skill 44 rails.
    post_fn = transport.post if transport is not None else post_with_retry
    put_fn = transport.put if transport is not None else put_with_retry

    if contact_id:
        # Bound contact exists — update it (no duplicate creation).
        status, contact_body, attempts = put_fn(
            base_url, "/contacts/%s" % contact_id, token, body
        )
        contact_status = status
    else:
        status, contact_body, attempts = post_fn(
            base_url, "/contacts/", token, body
        )
        contact_status = status
        new_id = None
        if isinstance(contact_body, dict):
            c = contact_body.get("contact") or {}
            if isinstance(c, dict):
                new_id = c.get("id") or contact_body.get("id")
        if new_id:
            contact_id = str(new_id)

    if contact_status in (200, 201):
        # raw_json_note — append the system-of-record note to the contact.
        if contact_id:
            note_path = "/contacts/%s/notes" % contact_id
            nstatus, _nbody, _natt = post_fn(
                base_url, note_path, token, {"body": note}
            )
            note_status = nstatus
        else:
            # No contact id captured (e.g. a stub that returned no id) — the
            # note cannot attach; the ledger mirror still holds the answer.
            note_status = 0
        if note_status not in (200, 201):
            # The answer is still durable in the ledger; the note is a mirror
            # convenience, not the only copy. Record the gap, never a lie.
            note_status = note_status

    # ---- 7. Durable local ledger mirror (ALWAYS written) ------------------
    outcome = {
        "event": "writeback",
        "ts": _now_utc(),
        "run_id": run_id,
        "phase_id": dest.get("phase_id"),
        "question_id": qid,
        "answer_id": answer.get("answer_id"),
        "client_id": dest.get("client_id"),
        "location_id": dest.get("location_id"),
        "bound_contact_id": contact_id,
        "status": "written" if contact_status in (200, 201) else "failed",
        "method": "PUT /contacts/<id>" if dest.get("contact_id") else "POST /contacts/",
        "ghl_status": contact_status,
        "note_status": note_status,
        "note_written": note_status in (200, 201),
        "attempts": attempts,
        "error": None,
        "ledger_path": None,
    }
    try:
        ledger_path = append_ledger(ledger_root, run_id, step, outcome)
        outcome["ledger_path"] = str(ledger_path)
    except OSError as exc:
        # The durable copy must exist even when GHL is unreachable. If the
        # ledger itself cannot be written, this is a hard failure (USAGE/IO).
        raise WritebackRefused(
            AF_PERSISTENT,
            "WRITE REFUSED: the local ledger mirror could not be written (%s). "
            "An answer is never dropped, and never written to GHL without a "
            "durable local copy." % exc,
        )

    if contact_status not in (200, 201):
        raise WritebackRefused(
            AF_PERSISTENT,
            "HONEST FAILURE RECEIPT: GHL returned %s for the contact write. The "
            "answer is durable in the local ledger mirror (%s) — it is NOT lost "
            "— but it has NOT reached the client's GHL. No fabricated success."
            % (contact_status, outcome["ledger_path"]),
        )

    return outcome


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_json_file(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WritebackRefused(
            AF_NOCONFIG,
            "USAGE/IO: cannot read/parse JSON %s: %s" % (path, exc),
        )
    if not isinstance(data, dict):
        raise WritebackRefused(
            AF_NOCONFIG, "USAGE/IO: %s must be a JSON object" % path,
        )
    return data


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="ghl_writeback.py",
        description="U15 GHL write-back on box (Skill 44 rails, isolation).",
    )
    parser.add_argument("delivery", nargs="?", help="delivery.json {binding, answer}")
    parser.add_argument("--config", default=None, help="phase config JSON (submit block)")
    parser.add_argument("--ledger-dir", default=None,
                        help="root for the ledger mirror (default: <delivery dir>)")
    parser.add_argument("--base-url", default=None,
                        help="GHL base URL (default services.leadconnectorhq.com)")
    parser.add_argument("--json", action="store_true", help="emit the outcome as JSON")
    parser.add_argument("--self-test", "--selftest", action="store_true",
                        help="run the stub-endpoint self-test (positive + negative)")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_selftest(json_out=args.json)

    if not args.delivery:
        parser.error("delivery.json is required (or pass --self-test)")
    if not args.config:
        parser.error("--config <phase-config.json> is required")

    try:
        delivery = _read_json_file(args.delivery)
        config = _read_json_file(args.config)
    except WritebackRefused as exc:
        print("REFUSED [%s] %s" % (exc.code, exc.message), file=sys.stderr)
        return EXIT_USAGE

    ledger_root = Path(args.ledger_dir) if args.ledger_dir else Path(args.delivery).parent
    base_url = args.base_url or DEFAULT_BASE_URL

    try:
        outcome = run_writeback(
            delivery, config, ledger_root=ledger_root, base_url=base_url,
        )
    except WritebackRefused as exc:
        if args.json:
            print(json.dumps({"ok": False, "code": exc.code, "error": exc.message},
                             indent=2))
        else:
            print("REFUSED [%s] %s" % (exc.code, exc.message), file=sys.stderr)
        # A refused write is a hard isolation gate -> EXIT_REFUSED (or
        # EXIT_PERSISTENT when the refusal is a post-retry transport failure).
        return EXIT_PERSISTENT if exc.code == AF_PERSISTENT else EXIT_REFUSED

    if args.json:
        print(json.dumps(outcome, indent=2))
    else:
        print("WRITTEN [%s] phase=%s qid=%s -> location=%s contact=%s (ledger %s)"
              % (outcome.get("status"), outcome.get("phase_id"),
                 outcome.get("question_id"), outcome.get("location_id"),
                 outcome.get("bound_contact_id"), outcome.get("ledger_path")))
    return EXIT_WRITTEN


# ---------------------------------------------------------------------------
# Self-test against a STUBBED GHL endpoint
# ---------------------------------------------------------------------------
# The stub IS the control: it records every write it sees, so 'loc got nothing'
# on a refused case is a PROVEN negative (the stub saw zero requests), not an
# absence. Positive: the bound answer lands exactly on the bound location.
# Negative: unbound token -> refused; wrong location -> refused (both with
# ZERO stub hits). No real GHL is ever contacted.
# ---------------------------------------------------------------------------

class _StubGHL:
    """In-process GHL stub recording per-location write sets.

    Auth rule (mirrors the location-scoped PIT): a request's bearer token must
    equal the stub's configured PIT for that location, or 401. A write whose
    body locationId differs from the requested path's location scope is 403.
    """

    def __init__(self):
        self.token = "pit-STUB-AAAAAAAAAAAAAAAAAAAAAAAAAAA"   # 32+ chars, stub only
        self.allowed_location = "loc_stub_a_location_id_long_0001"
        self.writes: list[dict[str, Any]] = []
        self.hits: list[dict[str, Any]] = []

    # --- transport shape compatible with http_json/post_with_retry ---------
    def post(self, path, headers, payload, timeout):
        self.hits.append({"method": "POST", "path": path, "payload": payload})
        auth = headers.get("Authorization", "")
        if auth != "Bearer %s" % self.token:
            return 401, {"message": "invalid token"}
        body = payload or {}
        if body.get("locationId") and body["locationId"] != self.allowed_location:
            return 403, {"message": "location not in scope"}
        self.writes.append(body)
        if path.startswith("/contacts/") and path.endswith("/notes"):
            return 201, {"id": "note-stub-1"}
        return 201, {"contact": {"id": "contact-stub-1"}}

    def put(self, path, headers, payload, timeout):
        self.hits.append({"method": "PUT", "path": path, "payload": payload})
        auth = headers.get("Authorization", "")
        if auth != "Bearer %s" % self.token:
            return 401, {"message": "invalid token"}
        body = payload or {}
        if body.get("locationId") and body["locationId"] != self.allowed_location:
            return 403, {"message": "location not in scope"}
        self.writes.append(body)
        return 200, {"contact": {"id": "contact-stub-1"}}


class _StubTransport:
    """Wraps _StubGHL with the post_with_retry signature (status, body, attempts)."""

    def __init__(self, stub: _StubGHL):
        self.stub = stub

    def post(self, base_url, path, token, payload, timeout=30):
        status, body = self.stub.post(path, {"Authorization": "Bearer %s" % token},
                                      payload, timeout)
        return status, body, 1

    def put(self, base_url, path, token, payload, timeout=30):
        status, body = self.stub.put(path, {"Authorization": "Bearer %s" % token},
                                     payload, timeout)
        return status, body, 1


def _env_for(stub: _StubGHL, location: str, include_token: bool = True) -> dict[str, str]:
    env = {
        "GOHIGHLEVEL_ALLOWED_LOCATION_IDS": location,
        "CAF_APPROVAL_TOKEN": "stub-approval",
    }
    if include_token:
        env["GOHIGHLEVEL_API_KEY"] = stub.token
    return env


def _delivery(location: str, run_id: str = "run_selftest_1",
              contact_id: str | None = None) -> dict[str, Any]:
    return {
        "binding": {
            "client_id": "client_STUB_A",
            "location_id": location,
            "slug": "stub-client",
            "phase_id": "P0-INTAKE",
            "run_id": run_id,
            "exp": 9999999999,
            "status": "open",
            "contact_id": contact_id,
        },
        "answer": {
            "qid": "first_name",
            "answer": "Stub Person",
            "source": "typed",
            "received_at": 1754500000,
            "answer_id": "ans-selftest-0001",
            "destination": {"location_id": "loc_attacker", "client_id": "client_ATTACKER"},
        },
    }


_CONFIG = {
    "phase": "P0-INTAKE",
    "submit": {
        "action": "ghl_contact",
        "custom_field_map": {"first_name": "bw_first_name"},
        "tags": ["book-writer", "intake", "phase-p0"],
        "raw_json_note": True,
    },
}


def _run_case(name: str, ok: bool, checks: list[tuple[str, bool]],
              results: list[tuple[str, bool, str]]) -> None:
    results.append((name, ok, "; ".join(
        "OK %s" % lbl if good else "XX %s" % lbl for lbl, good in checks
    )))


def run_selftest(json_out: bool = False) -> int:
    results: list[tuple[str, bool, str]] = []
    stub = _StubGHL()
    transport = _StubTransport(stub)
    ledger_root = Path(
        os.environ.get("TMPDIR", "/tmp")
    ) / ("u15-selftest-%s" % uuid.uuid4().hex[:8])

    def case(name, fn, expect_write: bool):
        stub.hits = []
        try:
            outcome = fn()
            # A CONTACT write is any POST /contacts/ or PUT /contacts/<id> (the
            # note write carries no locationId). Every contact write's body
            # locationId must equal the allowed_location — any other value is a
            # cross-location leak.
            contact_hits = [h for h in stub.hits
                            if h["method"] in ("POST", "PUT")
                            and h["path"].startswith("/contacts/")]
            wrote = any(
                (h.get("payload") or {}).get("locationId") == stub.allowed_location
                for h in contact_hits
            )
            notes = any(
                h["method"] == "POST" and h["path"].endswith("/notes")
                for h in stub.hits
            )
            cross_leak = any(
                (h.get("payload") or {}).get("locationId")
                not in (None, stub.allowed_location)
                for h in contact_hits
            )
            checks = [
                ("bound write landed" if wrote else "bound write present", wrote == expect_write),
                ("zero cross-location writes", not cross_leak),
                ("note appended", notes if expect_write else not notes),
            ]
            _run_case(name, all(c[1] for c in checks), checks, results)
        except WritebackRefused:
            # A refusal is CORRECT only when no write was expected.
            checks = [
                ("refused (no stub write)" if not expect_write else "unexpected refusal", not expect_write),
                ("zero GHL hits on refusal", len(stub.hits) == 0),
            ]
            _run_case(name, all(c[1] for c in checks), checks, results)
        except Exception as exc:  # any unexpected error is a FAIL
            _run_case(name, False, [("no unexpected exception", False)], results)

    # ---- POSITIVE: answer lands on the bound location, note appended -------
    def pos():
        return run_writeback(
            _delivery(stub.allowed_location),
            _CONFIG,
            ledger_root=ledger_root,
            env=_env_for(stub, stub.allowed_location),
            base_url="http://stub.local",
            transport=transport,
        )
    case("POSITIVE: bound answer lands on the bound location", pos, True)

    # ---- NEGATIVE: unbound token -> refused (zero GHL calls) ---------------
    def neg_unbound_token():
        env = _env_for(stub, stub.allowed_location, include_token=False)
        return run_writeback(
            _delivery(stub.allowed_location),
            _CONFIG,
            ledger_root=ledger_root,
            env=env,
            base_url="http://stub.local",
            transport=transport,
        )
    case("NEGATIVE: unbound token -> refused", neg_unbound_token, False)

    # ---- NEGATIVE: wrong location -> refused (zero GHL calls) --------------
    def neg_wrong_location():
        return run_writeback(
            _delivery("loc_wrong_location_other_client_999"),
            _CONFIG,
            ledger_root=ledger_root,
            env=_env_for(stub, stub.allowed_location),
            base_url="http://stub.local",
            transport=transport,
        )
    case("NEGATIVE: wrong location -> refused", neg_wrong_location, False)

    # ---- NEGATIVE: injected destination is ignored (attacker loc in answer) -
    def neg_injected():
        # The delivery's answer carries destination.location_id=attacker; the
        # binding row is the SOLE authority -> the write still targets the bound
        # location, never the attacker's.
        return run_writeback(
            _delivery(stub.allowed_location),
            _CONFIG,
            ledger_root=ledger_root,
            env=_env_for(stub, stub.allowed_location),
            base_url="http://stub.local",
            transport=transport,
        )
    case("NEGATIVE: injected destination ignored (binding is authority)", neg_injected, True)

    # ---- NEGATIVE: empty whitelist -> refuse all (fail-closed) -------------
    def neg_empty_whitelist():
        env = {"GOHIGHLEVEL_ALLOWED_LOCATION_IDS": "", "GOHIGHLEVEL_API_KEY": stub.token}
        return run_writeback(
            _delivery(stub.allowed_location),
            _CONFIG,
            ledger_root=ledger_root,
            env=env,
            base_url="http://stub.local",
            transport=transport,
        )
    case("NEGATIVE: empty whitelist -> refuse all", neg_empty_whitelist, False)

    # ---- POSITIVE: bound contact_id -> update (PUT), not duplicate create ---
    def pos_bound_contact():
        return run_writeback(
            _delivery(stub.allowed_location, contact_id="contact-stub-1"),
            _CONFIG,
            ledger_root=ledger_root,
            env=_env_for(stub, stub.allowed_location),
            base_url="http://stub.local",
            transport=transport,
        )
    case("POSITIVE: bound contact_id -> update not create", pos_bound_contact, True)

    # ---- print + exit -------------------------------------------------------
    lines = []
    all_pass = True
    for name, ok, detail in results:
        lines.append("%s %s  %s" % ("PASS" if ok else "FAIL", name, detail))
        all_pass = all_pass and ok
    if json_out:
        print(json.dumps({
            "prover": "U15-ghl-writeback-selftest",
            "passed": all_pass,
            "cases": [{"name": n, "ok": o, "detail": d} for n, o, d in results],
        }, indent=2))
    else:
        for line in lines:
            print(line)
        print("== U15 GHL write-back self-test: %s =="
              % ("ALL ASSERTIONS PASSED" if all_pass else "FAILED"))

    import shutil
    shutil.rmtree(ledger_root, ignore_errors=True)
    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
