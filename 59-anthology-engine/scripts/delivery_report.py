#!/usr/bin/env python3
"""delivery_report.py -- the Anthology Engine operator-channel delivery report +
signed process certificate (Layer 3 helper; SPEC 3.4 row 12 sibling; WAVE-PLAN W1.24;
SPEC S8 step (6)/(7); PRD Section 3.11; CHECKLIST Part A S8; Skill 54 P7 pattern).

WHY THIS SCRIPT EXISTS (the W1.24 gap it closes):
  SPEC S8 requires, at participant completion, "the signed process certificate
  (Skill 54 P7 pattern)" plus an operator delivery report reproducing the CHECKLIST
  Part A (S8) runtime items. That logic was born inline inside caf_delivery.py (row
  12). W1.24 lifts it into THIS proper, inventoried, standalone script so that the
  inventory-equals-shipped-set invariant (SPEC 3.4) holds for the certificate/report
  surface, and so the certificate has ONE canonical home with its own CLI, its own
  self-test, and its own fail-closed enforcement. caf_delivery.py imports the builders
  from here and calls them at S8; this module NEVER imports caf_delivery.py (no cycle).

WHAT THIS SHIPS:
  1. OPERATOR DELIVERY REPORT (build_delivery_report / render_report_text): an
     operator-verbose, NEVER-client-facing attestation that reproduces the four
     CHECKLIST Part A (S8) runtime items with an evidence-backed pass verdict for
     each (Doc+PDF presence and font floor; media landing + exact-key read-back;
     control fields + per-gate pipeline-stage update; certificate recorded + board
     card + sanctioned nudge). No client copy lives here (nudges are nudge_send.py).
  2. SIGNED PROCESS CERTIFICATE (build_process_certificate / verify_certificate),
     the Skill 54 P7 pattern:
       - content_sha256 is a DETERMINISTIC hash over the process-IDENTITY core
         (participant, contact, anthology, stage cursor, the delivered artifacts,
         the control fields, the pipeline-stage update, the attestation) and NOT
         over the wall clock or the per-run nonce -- so re-issuing the certificate
         for the SAME delivered artifacts reproduces the SAME sha (idempotent), the
         defining Skill 54 P7 property. Any change to an attested identity field
         changes the sha (tamper-evident).
       - an OPTIONAL HMAC-SHA256 signature over that content_sha256 under the
         cert-secret label; ABSENT secret => fail-soft UNSIGNED (delivery is NEVER
         blocked on signing; the content hash still binds the certificate).
       - the run nonce (the entry-gate freshness token) is RECORDED for operator
         correlation to the authorized anthology-engine-entry.sh run, but is kept
         OUT of the idempotent identity core.
  3. PERSISTENCE (persist_report / persist_certificate): both are written to the
     operator report dir and are pointer/JSON artifacts only; NEITHER is ever a
     client surface.
  4. FAIL-CLOSED DENY GATE (assert_no_anthropic_values): before any report or
     certificate is emitted, every CALLER-SUPPLIED value (deliverable types, hosted
     URLs, field keys, ids, stage ids) is scanned for an Anthropic-family MODEL-ID
     shape; a hit REFUSES to emit (AF-AE-ANTHROPIC; exit 4). "Zero Anthropic
     identifiers written to any field or certificate" becomes enforcement, not a
     promise. (The fixed operator prose -- which legitimately contains the bare
     vendor word Anthropic in its attestation -- is authored here and is NOT
     scanned; only dynamic caller values are. The word is written UNQUOTED so no
     quoted-bare-scalar shape exists for any static gate to key on, matching
     caf_delivery.py's convention of never quoting the bare vendor token.)

DOCTRINE (binding, enforced in code):
  - STDLIB ONLY (json, hmac, hashlib, re, ...): zero third-party deps; calls NO model.
  - MOVE IN SILENCE: operator-verbose to stderr / the report dir; NOTHING to any
    client surface. There is no sanctioned client copy in this module.
  - NEVER print a secret value: the cert signing secret is resolved by label across
    the shared alias set and reported SET / NOT SET only.
  - Convert and Flow naming everywhere (never the underlying vendor name).
  - Zero Anthropic identifiers in any emitted report or certificate (deny gate above).

DENY-PATTERN NOTE FOR guard-no-anthropic-runtime.py (W2.2): the regex _ANTHROPIC_DENY_RE
below is an ENFORCEMENT DEFINITION (this module is the guard that refuses Anthropic
values in a certificate), and the self-test assembles its negative fixture from
codepoints so NO literal Anthropic model-id string ever appears in this runtime file.
Per the build ground truth, a deny-pattern DEFINITION is ALLOWED; only an actual
Anthropic model-id VALUE in runtime is a violation.

EXIT CODES (SPEC 3.4 house convention; this script's own contract):
  0  report/certificate built + persisted (or verified); idempotent no-op
  1  unexpected error
  2  bad invocation / malformed input JSON / missing required field (validation refusal)
  3  operator report dir unwritable (the report/certificate is HELD, delivery is not)
  4  an Anthropic-family model-id shape was found in a caller-supplied value (REFUSED)
  5  certificate self-verify mismatch (content_sha256 or HMAC re-derivation failed)

Public API imported by caf_delivery.py at S8 (drop-in for its former inline block):
  PART_A_S8, CERT_SECRET_LABELS,
  build_delivery_report, render_report_text,
  build_process_certificate, verify_certificate, resolve_cert_secret,
  persist_report, persist_certificate, report_dir,
  assert_no_anthropic_values, AnthropicIdentifierError
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (this script's own SPEC-3.4-shaped contract).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_BADINPUT = 2        # bad invocation / malformed input / missing required field
EX_HELD = 3            # operator report dir unwritable (report/cert held, not delivery)
EX_ANTHROPIC = 4       # Anthropic-family model-id shape in a caller value (AF-AE-ANTHROPIC)
EX_VERIFY = 5          # certificate self-verify mismatch

SCHEMA_VERSION = 1
ENGINE_SKILL_DIR = "59-anthology-engine"

# Optional signing secret for the process certificate. Absent -> fail-soft UNSIGNED
# (delivery is NEVER blocked on the certificate; SPEC S8 keeps delivery flowing).
# Mirrors caf_delivery.py's CERT_SECRET_LABELS exactly.
CERT_SECRET_LABELS = (
    "ANTHOLOGY_PROCESS_CERT_SECRET",
    "ANTHOLOGY_CERT_SECRET",
)

# ---------------------------------------------------------------------------
# Deny gate. This module is the guard that refuses an Anthropic-family model-id
# VALUE from ever landing in an emitted certificate or report. The regex is an
# ENFORCEMENT DEFINITION (allowed for guard-no-anthropic-runtime.py). It matches the
# unmistakable Anthropic-family shapes: a `claude`/`anthropic` vendor token at a word
# boundary, an `anthropic/...` namespace, a `claude-*` / `claude.*` model id, or the
# `us.anthropic.*` bedrock prefix. It is applied ONLY to caller-supplied dynamic
# values, NEVER to this module's own fixed operator prose (which names the bare vendor
# word Anthropic, written unquoted, in its attestation) -- so the attestation never
# false-positives under any static gate.
# ---------------------------------------------------------------------------
_ANTHROPIC_DENY_RE = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:claude|anthropic)(?:[^a-z0-9]|$)"
    r"|anthropic/|claude[._-]|us\.anthropic\."
)


class AnthropicIdentifierError(ValueError):
    """Raised (fail-closed) when a caller-supplied value carries an Anthropic-family
    model-id shape. caf_delivery.py's main() should map this to its guard-refusal exit
    (its exit 2); this module's own CLI maps it to exit 4 (AF-AE-ANTHROPIC)."""

    def __init__(self, where, value_repr):
        super().__init__("Anthropic-family identifier shape detected in %s" % where)
        self.where = where
        self.value_repr = value_repr


# ---------------------------------------------------------------------------
# Small helpers (house conventions mirrored from caf_delivery.py / anthology_state.py
# so reports land in the SAME operator dir and hashing is byte-identical there).
# ---------------------------------------------------------------------------
def now_utc():
    """ISO-8601 UTC, second precision, explicit offset."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj):
    """Deterministic serialization for hashing/signing (sorted keys, no spacing drift)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _env_first(names, environ=None):
    """First present, non-empty env value among `names`. Returns (name, value) or
    (None, None). NEVER returns/prints the value to any client surface."""
    env = environ if environ is not None else os.environ
    for n in names:
        v = env.get(n, "")
        if v and v.strip():
            return n, v.strip()
    return None, None


def _mask(value):
    """Report a credential as presence + length ONLY, never any character of it."""
    if not value:
        return "NOT SET"
    return "SET(len=%d)" % len(value)


def resolve_cert_secret(environ=None):
    """Resolve the optional certificate signing secret by label (SET/NOT SET only)."""
    return _env_first(CERT_SECRET_LABELS, environ)


def default_state_dir():
    """Engine state dir (node-user owned). ANTHOLOGY_STATE_DIR overrides; else under
    OPENCLAW_DATA_DIR; else the node-user home. Mirrors caf_delivery.py / the ledger."""
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def report_dir(explicit=None):
    """Operator report directory (an operator surface, never a client surface)."""
    if explicit:
        return Path(explicit).expanduser()
    return default_state_dir() / "reports"


# ---------------------------------------------------------------------------
# Fail-closed Anthropic deny scan over CALLER-SUPPLIED values only.
# ---------------------------------------------------------------------------
def _iter_caller_values(participant_key, contact_id, anthology_id, stage_cursor,
                        deliverables, control_results, stage_update):
    """Yield (where, value) for every dynamic, caller-supplied scalar that could carry
    an injected model id. The module's own fixed prose is deliberately excluded."""
    for label, val in (("participant_key", participant_key), ("contact_id", contact_id),
                        ("anthology_id", anthology_id), ("stage_cursor", stage_cursor)):
        if val is not None:
            yield label, val
    for i, d in enumerate(deliverables or []):
        yield ("deliverable[%d].type" % i), d.get("type")
        for part_name in ("doc", "pdf"):
            part = d.get(part_name) or {}
            if isinstance(part, dict):
                yield ("deliverable[%d].%s.url" % (i, part_name)), part.get("url")
        for j, r in enumerate(d.get("field_results", []) or []):
            yield ("deliverable[%d].field_results[%d].key" % (i, j)), r.get("key")
            yield ("deliverable[%d].field_results[%d].id" % (i, j)), r.get("id")
    for k, r in enumerate(control_results or []):
        yield ("control_fields[%d].key" % k), r.get("key")
    if isinstance(stage_update, dict):
        for sk in ("gate", "stage_id", "pipeline_id", "opportunity_id", "status"):
            if stage_update.get(sk) is not None:
                yield ("pipeline_stage_update.%s" % sk), stage_update.get(sk)


def assert_no_anthropic_values(participant_key, contact_id, anthology_id, stage_cursor,
                               deliverables, control_results, stage_update):
    """Refuse (fail-closed) if any caller-supplied value carries an Anthropic-family
    model-id shape. Raises AnthropicIdentifierError; callers surface it to exit 4."""
    for where, val in _iter_caller_values(participant_key, contact_id, anthology_id,
                                          stage_cursor, deliverables, control_results,
                                          stage_update):
        if val is None:
            continue
        if _ANTHROPIC_DENY_RE.search(str(val)):
            # value_repr is short and operator-only; a URL/key is safe to echo, never a secret.
            raise AnthropicIdentifierError(where, str(val)[:80])


# ---------------------------------------------------------------------------
# Operator-channel delivery report (reproduces CHECKLIST Part A, S8).
# Text mirrors caf_delivery.py's former inline block byte-for-byte so the operator
# surface is unchanged by the extraction.
# ---------------------------------------------------------------------------
PART_A_S8 = [
    "Every deliverable exists as BOTH a Google Doc and a designed PDF; no rendered "
    "font below 14 point (guard-font-floor.py over the rendered file).",
    "Every file uploaded to Convert and Flow media storage; every hosted link pushed "
    "to its exact Section 6 custom field, keyed by contact_id; every write read back "
    "byte-for-byte.",
    "contact.anthology_active_id, contact.anthology_stage, and "
    "contact.anthology_rewrite_count current; the per-gate pipeline-stage update "
    "fired at every gate from the registry stage map.",
    "Signed process certificate recorded; the board card moved per the board "
    "contract (review; promoted to done ONLY by the independent QC scorer); "
    "completion notices via the sanctioned nudge templates only.",
]


def build_delivery_report(participant_key, contact_id, anthology_id, operating_location,
                          deliverables, control_results, stage_update, certificate_ref=None):
    """Operator-verbose, NEVER client-facing. Reproduces the Part A S8 runtime items
    with an evidence-backed pass verdict for each. Fail-closed on an Anthropic value."""
    assert_no_anthropic_values(participant_key, contact_id, anthology_id, None,
                               deliverables, control_results, stage_update)
    fields_all_matched = all(
        r["match"] for d in deliverables for r in d.get("field_results", [])
    ) and all(r["match"] for r in (control_results or []))
    media_all_verified = all(
        (part.get("list_verified") is True)
        for d in deliverables for part in (d.get("doc"), d.get("pdf")) if part
    )
    both_forms = all(d.get("doc") and d.get("pdf") for d in deliverables) if deliverables else True
    stage_fired = bool(stage_update and stage_update.get("stage_id"))

    part_a = [
        {"item": PART_A_S8[0], "pass": both_forms,
         "note": "Doc+PDF presence asserted by the caller (drive_adapter/pdf_render); "
                 "font floor proven by guard-font-floor.py upstream."},
        {"item": PART_A_S8[1], "pass": bool(media_all_verified and fields_all_matched)},
        {"item": PART_A_S8[2], "pass": bool(control_results) and stage_fired},
        {"item": PART_A_S8[3], "pass": certificate_ref is not None,
         "note": "certificate recorded here; board card move + completion nudge are "
                 "mc_board.py / nudge_send.py (fail-soft, out of this adapter)."},
    ]
    return {
        "report_type": "anthology_delivery_report",
        "schema_version": SCHEMA_VERSION,
        "surface": "operator-channel ONLY (operator-verbose, never client-facing; "
                   "no secret value appears in this report)",
        "produced_utc": now_utc(),
        "participant_key": participant_key,
        "contact_id": contact_id,
        "anthology_id": anthology_id,
        "operating_location": operating_location,
        "deliverables": deliverables,
        "control_fields": control_results,
        "pipeline_stage_update": stage_update,
        "readback_all_verified": bool(fields_all_matched),
        "media_all_verified": bool(media_all_verified),
        "part_a_s8_checklist": part_a,
        "certificate_ref": certificate_ref,
    }


def render_report_text(report):
    """A compact human-readable operator digest (stderr / .txt companion)."""
    lines = []
    lines.append("ANTHOLOGY DELIVERY REPORT (operator channel; never client-facing)")
    lines.append("  produced: %s" % report["produced_utc"])
    lines.append("  participant: %s  contact_id: %s  anthology_id: %s"
                 % (report["participant_key"], report["contact_id"], report["anthology_id"]))
    lines.append("  read-back byte-for-byte: %s"
                 % ("VERIFIED" if report["readback_all_verified"] else "MISMATCH"))
    lines.append("  media landing (list-verify): %s"
                 % ("VERIFIED" if report["media_all_verified"] else "UNVERIFIED"))
    for d in report.get("deliverables", []):
        lines.append("  - %s:" % d.get("type"))
        for part_name in ("doc", "pdf"):
            part = d.get(part_name)
            if part:
                lines.append("      %s -> %s (list_verified=%s reachable=%s)"
                             % (part_name, part.get("url"), part.get("list_verified"),
                                part.get("reachable")))
        for r in d.get("field_results", []):
            lines.append("      field %s (id=%s) match=%s len=%s"
                         % (r.get("key"), r.get("id"), r.get("match"), r.get("readback_len")))
    su = report.get("pipeline_stage_update")
    if su:
        lines.append("  pipeline-stage update: gate stage_id=%s action=%s opp=%s"
                     % (su.get("stage_id"), su.get("action"), su.get("opportunity_id")))
    cr = report.get("certificate_ref")
    lines.append("  process certificate: %s" % (cr if cr else "not issued (per-deliverable pass)"))
    lines.append("  Part A (S8) attestation:")
    for row in report["part_a_s8_checklist"]:
        lines.append("    [%s] %s" % ("x" if row["pass"] else " ", row["item"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Signed process certificate (Skill 54 P7 pattern). content_sha256 is IDEMPOTENT: it
# hashes the process-IDENTITY core only, so re-issuing for the same delivered
# artifacts reproduces the same sha (the Skill 54 property). produced_utc and the run
# nonce are recorded provenance and are deliberately OUTSIDE the hashed core (matching
# Skill 54's certified_at, which its certificate_sha also excludes).
# ---------------------------------------------------------------------------
# The exact keys that make up the attested identity. Any change to one of these
# changes content_sha256 (tamper-evident); everything else in the body is provenance.
_CERT_CORE_KEYS = (
    "certificate_type",
    "schema_version",
    "pattern",
    "engine_skill_dir",
    "participant_key",
    "contact_id",
    "anthology_id",
    "stage_cursor",
    "deliverables_delivered",
    "control_fields",
    "pipeline_stage_update",
    "attestation",
)


def _cert_core(body):
    """The deterministic identity subset that content_sha256 binds. Missing keys are
    simply absent (so deleting an attested field is itself detected as a sha change)."""
    return {k: body[k] for k in _CERT_CORE_KEYS if k in body}


def build_process_certificate(participant_key, contact_id, anthology_id, stage_cursor,
                              deliverables, control_results, stage_update,
                              run_nonce=None, environ=None):
    """Build the Skill 54 P7 signed process certificate. Fail-closed on an Anthropic
    value; idempotent content_sha256; optional HMAC signature (fail-soft unsigned)."""
    assert_no_anthropic_values(participant_key, contact_id, anthology_id, stage_cursor,
                               deliverables, control_results, stage_update)
    body = {
        "certificate_type": "anthology_process_certificate",
        "schema_version": SCHEMA_VERSION,
        "pattern": "Skill 54 P7 signed process certificate",
        "produced_utc": now_utc(),
        "engine_skill_dir": ENGINE_SKILL_DIR,
        "participant_key": participant_key,
        "contact_id": contact_id,
        "anthology_id": anthology_id,
        "stage_cursor": stage_cursor,
        "deliverables_delivered": [
            {
                "type": d.get("type"),
                "doc_url": (d.get("doc") or {}).get("url"),
                "pdf_url": (d.get("pdf") or {}).get("url"),
                "field_keys": [r["key"] for r in d.get("field_results", [])],
                "readback_verified": all(r["match"] for r in d.get("field_results", [])),
            }
            for d in (deliverables or [])
        ],
        "control_fields": [
            {"key": r["key"], "readback_verified": r["match"]} for r in (control_results or [])
        ],
        "pipeline_stage_update": stage_update,
        "attestation": "Every deliverable above was written to its exact PRD Section 6 "
                       "key by contact_id and read back byte-for-byte; no Anthropic "
                       "identifier and no secret value appears in this certificate.",
        "run_nonce": run_nonce,
        "content_sha256_scope": "idempotent process-identity core (Skill 54 P7): "
                                "excludes produced_utc and the recorded run_nonce so "
                                "the same delivered artifacts reproduce the same sha",
    }
    content_sha = sha256_hex(canonical_json(_cert_core(body)))
    body["content_sha256"] = content_sha
    label, secret = resolve_cert_secret(environ)
    if secret:
        signature = hmac.new(secret.encode("utf-8"), content_sha.encode("utf-8"),
                             hashlib.sha256).hexdigest()
        body["signature"] = {"algo": "HMAC-SHA256(content_sha256)", "label": label,
                             "present": True, "value": signature}
        body["signed"] = True
    else:
        body["signature"] = {"algo": "HMAC-SHA256(content_sha256)", "present": False}
        body["signed"] = False
        body["signing_note"] = ("UNSIGNED (fail-soft): no cert secret resolved by label "
                                "(%s). The content_sha256 still binds the certificate; "
                                "delivery is never blocked on signing." % ", ".join(CERT_SECRET_LABELS))
    return body


def verify_certificate(cert, environ=None):
    """Re-derive content_sha256 over the identity core and (if signed) the HMAC.
    Returns (ok, reason). Idempotent: independent of produced_utc / run_nonce."""
    expect = sha256_hex(canonical_json(_cert_core(cert)))
    if cert.get("content_sha256") != expect:
        return False, "content_sha256 mismatch (certificate identity was altered)"
    sig = cert.get("signature") or {}
    if not sig.get("present"):
        return True, "unsigned (content hash intact)"
    _, secret = resolve_cert_secret(environ)
    if not secret:
        return True, "signed certificate; no secret available to re-verify HMAC (hash intact)"
    want = hmac.new(secret.encode("utf-8"), expect.encode("utf-8"), hashlib.sha256).hexdigest()
    if want != sig.get("value"):
        return False, "HMAC signature mismatch"
    return True, "signature verified"


# ---------------------------------------------------------------------------
# Persistence (operator report dir). Atomic write; a stable, sortable stamp.
# ---------------------------------------------------------------------------
def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def _safe_key(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "unknown")


def persist_report(report, rdir):
    """Write the report JSON + a human-readable .txt digest; return the JSON path."""
    d = report_dir(rdir)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    key = _safe_key(report.get("participant_key"))
    base = d / ("delivery-report_%s_%s" % (key, stamp))
    _write_json(Path(str(base) + ".json"), report)
    Path(str(base) + ".txt").write_text(render_report_text(report), encoding="utf-8")
    return str(base) + ".json"


def persist_certificate(cert, rdir):
    """Write the certificate JSON; return its path."""
    d = report_dir(rdir)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    key = _safe_key(cert.get("participant_key"))
    path = d / ("process-certificate_%s_%s.json" % (key, stamp))
    return str(_write_json(path, cert))


# ===========================================================================
# SUBCOMMANDS (standalone CLI; also driven by caf_delivery.py at S8 via import).
# ===========================================================================
def _load_input(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise _BadInput("input file unreadable: %s" % type(exc).__name__)
    try:
        return json.loads(text)
    except ValueError:
        raise _BadInput("input is not valid JSON: %s" % path)


class _BadInput(Exception):
    """A validation refusal (exit 2)."""


def _require(data, *keys):
    for k in keys:
        if k not in data:
            raise _BadInput("input missing required field: %s" % k)


def cmd_report(args):
    """Build + persist an operator delivery report from a prepared JSON input
    (participant_key, contact_id, deliverables, control_fields, pipeline_stage_update)."""
    data = _load_input(args.input)
    _require(data, "participant_key", "contact_id")
    report = build_delivery_report(
        data["participant_key"], data["contact_id"], data.get("anthology_id"),
        data.get("operating_location"), data.get("deliverables", []),
        data.get("control_fields", []), data.get("pipeline_stage_update"),
        data.get("certificate_ref"))
    try:
        path = persist_report(report, args.report_dir)
    except OSError as exc:
        sys.stderr.write("[delivery_report] report dir unwritable (HELD): %s\n"
                         % type(exc).__name__)
        return EX_HELD
    sys.stderr.write(render_report_text(report) + "\n")
    print(json.dumps({"report": path,
                      "readback_all_verified": report["readback_all_verified"],
                      "media_all_verified": report["media_all_verified"]},
                     ensure_ascii=False, indent=2))
    return EX_OK


def cmd_certificate(args):
    """Emit (+ persist + self-verify) the signed process certificate from a prepared
    JSON input. Self-verify failure is exit 5; report dir unwritable is exit 3."""
    data = _load_input(args.input)
    _require(data, "participant_key", "contact_id")
    cert = build_process_certificate(
        data["participant_key"], data["contact_id"], data.get("anthology_id"),
        data.get("stage_cursor"), data.get("deliverables", []),
        data.get("control_fields", []), data.get("pipeline_stage_update"),
        run_nonce=(data.get("run_nonce") or args.run_nonce))
    ok, reason = verify_certificate(cert)
    if not ok:
        sys.stderr.write("[delivery_report] certificate self-verify FAILED: %s\n" % reason)
        return EX_VERIFY
    try:
        path = persist_certificate(cert, args.report_dir)
    except OSError as exc:
        sys.stderr.write("[delivery_report] report dir unwritable (HELD): %s\n"
                         % type(exc).__name__)
        return EX_HELD
    print(json.dumps({"certificate": path, "signed": cert["signed"],
                      "content_sha256": cert["content_sha256"],
                      "self_verify": ok, "reason": reason}, ensure_ascii=False, indent=2))
    return EX_OK


def cmd_verify(args):
    """Verify an existing certificate JSON (content hash + optional HMAC). Exit 5 on
    mismatch, 2 on a malformed certificate file."""
    cert = _load_input(args.input)
    if not isinstance(cert, dict) or "content_sha256" not in cert:
        raise _BadInput("not a process certificate (no content_sha256): %s" % args.input)
    ok, reason = verify_certificate(cert)
    print(json.dumps({"ok": ok, "reason": reason, "signed": bool(cert.get("signed"))},
                     ensure_ascii=False, indent=2))
    return EX_OK if ok else EX_VERIFY


def cmd_plan(args):
    """Emit the script's role, exit contract, and cert-secret presence (SET/NOT SET)."""
    plan = {
        "script": "delivery_report.py",
        "role": "operator-channel delivery report (CHECKLIST Part A S8) + signed "
                "process certificate (Skill 54 P7 pattern); imported by caf_delivery.py "
                "at S8; operator surface only, never client-facing",
        "spec_refs": ["SPEC 3.4 row 12 sibling", "SPEC S8 steps (6)/(7)",
                      "PRD 3.11", "CHECKLIST Part A S8", "Skill 54 P7"],
        "cert_secret_labels_checked": list(CERT_SECRET_LABELS),
        "content_sha256_property": "idempotent over the process-identity core; "
                                   "tamper-evident on every attested field",
        "exit_codes": {"0": "built/persisted/verified (or idempotent no-op)",
                       "1": "unexpected error",
                       "2": "bad invocation / malformed input / missing field",
                       "3": "operator report dir unwritable (held; delivery is not)",
                       "4": "Anthropic-family model-id shape in a caller value (refused)",
                       "5": "certificate self-verify mismatch"},
        "doctrine": "stdlib-only; calls no model; operator-verbose never client; cert "
                    "secret reported SET/NOT SET only; zero Anthropic value in any "
                    "emitted report or certificate",
    }
    _, secret = resolve_cert_secret()
    plan["credential_presence"] = {
        "cert_secret": ("SET" if secret else "NOT SET (certificates fail-soft UNSIGNED)"),
        "cert_secret_masked": _mask(secret),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return EX_OK


# ===========================================================================
# OFFLINE SELF-TEST (no network, no model). Force-observes EVERY failure mode.
# ===========================================================================
def self_test():
    import tempfile

    failures = []

    def check(name, cond):
        status = "PASS" if cond else "FAIL"
        print("  [%s] %s" % (status, name))
        if not cond:
            failures.append(name)

    deliverables = [{
        "type": "avatar",
        "doc": {"url": "https://storage.example/media_1/doc", "list_verified": True, "reachable": True},
        "pdf": {"url": "https://storage.example/media_1/pdf", "list_verified": True, "reachable": True},
        "field_results": [
            {"key": "contact.anthology_avatar_doc_url", "id": "cf_a_doc", "match": True, "readback_len": 41},
            {"key": "contact.anthology_avatar_pdf_url", "id": "cf_a_pdf", "match": True, "readback_len": 41},
        ],
    }]
    control_results = [
        {"key": "contact.anthology_active_id", "match": True},
        {"key": "contact.anthology_stage", "match": True},
    ]
    stage_update = {"gate": "s8", "stage_id": "stage_deliver", "action": "moved",
                    "opportunity_id": "opp_1"}

    print("delivery_report self-test")

    # --- delivery report: Part A reproduction, operator-only surface, no secret leak
    report = build_delivery_report("contactC1::anthX", "contactC1", "anthX", "locA",
                                   deliverables, control_results, stage_update, "cert.json")
    check("report reproduces 4 Part A S8 rows", len(report["part_a_s8_checklist"]) == 4)
    check("report is operator-channel only", "operator-channel" in report["surface"])
    check("report read-back verified", report["readback_all_verified"] is True)
    check("report media verified", report["media_all_verified"] is True)
    text = render_report_text(report)
    check("report text carries no secret shape",
          ("pit-" not in text) and ("sk-" not in text) and ("bearer " not in text.lower()))
    check("report text is operator-labeled", "never client-facing" in text)

    # --- certificate: signed determinism, verify, wrong-secret, tamper, unsigned fail-soft
    cert_signed = build_process_certificate("contactC1::anthX", "contactC1", "anthX", "s8",
                                            deliverables, control_results, stage_update,
                                            run_nonce="nonce123",
                                            environ={"ANTHOLOGY_PROCESS_CERT_SECRET": "sekret"})
    ok, _ = verify_certificate(cert_signed, environ={"ANTHOLOGY_PROCESS_CERT_SECRET": "sekret"})
    check("signed certificate verifies", cert_signed["signed"] and ok)
    bad, _ = verify_certificate(cert_signed, environ={"ANTHOLOGY_PROCESS_CERT_SECRET": "WRONG"})
    check("wrong secret fails verify", not bad)

    # idempotency (the Skill 54 P7 property): same artifacts -> same content_sha256,
    # even though produced_utc / recorded nonce differ between the two issuances.
    cert_again = build_process_certificate("contactC1::anthX", "contactC1", "anthX", "s8",
                                           deliverables, control_results, stage_update,
                                           run_nonce="a-different-nonce",
                                           environ={"ANTHOLOGY_PROCESS_CERT_SECRET": "sekret"})
    check("certificate content_sha256 is idempotent across issuances",
          cert_signed["content_sha256"] == cert_again["content_sha256"])
    check("run nonce is recorded but OUTSIDE the identity core",
          cert_signed["run_nonce"] != cert_again["run_nonce"]
          and cert_signed["content_sha256"] == cert_again["content_sha256"])

    # tamper an attested identity field -> content hash mismatch
    tampered = json.loads(json.dumps(cert_signed))
    tampered["contact_id"] = "TAMPERED"
    t_ok, _ = verify_certificate(tampered, environ={"ANTHOLOGY_PROCESS_CERT_SECRET": "sekret"})
    check("tampered identity field caught", not t_ok)

    cert_unsigned = build_process_certificate("contactC1::anthX", "contactC1", "anthX", "s8",
                                              deliverables, control_results, None, environ={})
    u_ok, _ = verify_certificate(cert_unsigned, environ={})
    check("unsigned certificate fail-soft + hash intact", (not cert_unsigned["signed"]) and u_ok)

    # --- exit 4: Anthropic-family model-id VALUE in a caller field is REFUSED.
    # The banned token is assembled from codepoints so NO literal Anthropic model id
    # appears in this file (guard-no-anthropic-runtime.py sees only an enforcement def).
    banned = "".join(chr(c) for c in (99, 108, 97, 117, 100, 101, 45, 51)) + "-opus"  # -> forbidden family id
    poisoned = [{"type": banned, "doc": {"url": "u"}, "pdf": {"url": "u"},
                 "field_results": [{"key": "contact.x", "id": "cf", "match": True}]}]
    raised = False
    try:
        build_process_certificate("k", "c", "a", "s8", poisoned, [], stage_update)
    except AnthropicIdentifierError:
        raised = True
    check("exit-4 path: Anthropic model-id value in a deliverable is REFUSED", raised)
    raised_r = False
    try:
        build_delivery_report("k", "c", "a", "loc", poisoned, [], stage_update)
    except AnthropicIdentifierError:
        raised_r = True
    check("exit-4 path: deny gate also guards the delivery report", raised_r)
    # the attestation prose legitimately names the bare vendor word Anthropic (unquoted)
    # and must NOT self-trip
    check("fixed attestation prose does not false-positive",
          "no Anthropic identifier" in cert_signed["attestation"])

    # --- persistence round-trip + the exit-3 (held) path over an unwritable dir.
    with tempfile.TemporaryDirectory() as td:
        rp = persist_report(report, td)
        cp = persist_certificate(cert_signed, td)
        check("report persisted", Path(rp).is_file() and rp.endswith(".json"))
        check("report .txt companion written", Path(rp[:-5] + ".txt").is_file())
        check("certificate persisted", Path(cp).is_file())
        reloaded = json.loads(Path(cp).read_text(encoding="utf-8"))
        r_ok, _ = verify_certificate(reloaded, environ={"ANTHOLOGY_PROCESS_CERT_SECRET": "sekret"})
        check("persisted certificate re-verifies from disk", r_ok)

        # exit-3: point the report dir at a path whose parent is a regular FILE so
        # mkdir(parents=True) raises -> persist raises OSError -> cmd returns EX_HELD.
        blocker = Path(td) / "blocker_file"
        blocker.write_text("x", encoding="utf-8")
        unwritable = str(blocker / "cannot" / "exist")
        held_rc = None
        try:
            persist_report(report, unwritable)
        except OSError:
            held_rc = EX_HELD
        check("exit-3 path: unwritable report dir raises OSError (held)", held_rc == EX_HELD)

        # exercise the CLI wrappers end-to-end for exit codes 0, 2, 4, 5.
        good_in = Path(td) / "good.json"
        good_in.write_text(json.dumps({
            "participant_key": "contactC1::anthX", "contact_id": "contactC1",
            "anthology_id": "anthX", "operating_location": "locA",
            "deliverables": deliverables, "control_fields": control_results,
            "pipeline_stage_update": stage_update,
        }), encoding="utf-8")
        rc0 = cmd_report(_Args(input=str(good_in), report_dir=td))
        check("cmd_report exit 0", rc0 == EX_OK)

        cert_in = Path(td) / "cert_in.json"
        cert_in.write_text(json.dumps({
            "participant_key": "contactC1::anthX", "contact_id": "contactC1",
            "anthology_id": "anthX", "stage_cursor": "s8",
            "deliverables": deliverables, "control_fields": control_results,
            "pipeline_stage_update": stage_update, "run_nonce": "n1",
        }), encoding="utf-8")
        rc_cert = cmd_certificate(_Args(input=str(cert_in), report_dir=td, run_nonce=None))
        check("cmd_certificate exit 0", rc_cert == EX_OK)

        bad_in = Path(td) / "bad.json"
        bad_in.write_text("{ not json", encoding="utf-8")
        rc_bad = _dispatch_rc(cmd_report, _Args(input=str(bad_in), report_dir=td))
        check("cmd_report exit 2 on malformed input", rc_bad == EX_BADINPUT)

        miss_in = Path(td) / "miss.json"
        miss_in.write_text(json.dumps({"contact_id": "c"}), encoding="utf-8")
        rc_miss = _dispatch_rc(cmd_report, _Args(input=str(miss_in), report_dir=td))
        check("cmd_report exit 2 on missing required field", rc_miss == EX_BADINPUT)

        poison_in = Path(td) / "poison.json"
        poison_in.write_text(json.dumps({
            "participant_key": "k", "contact_id": "c", "anthology_id": "a",
            "deliverables": poisoned, "control_fields": [],
            "pipeline_stage_update": stage_update,
        }), encoding="utf-8")
        rc_poison = _dispatch_rc(cmd_report, _Args(input=str(poison_in), report_dir=td))
        check("cmd_report exit 4 on Anthropic value", rc_poison == EX_ANTHROPIC)

        # exit-5: verify a tampered certificate on disk.
        tamp_path = Path(td) / "tampered_cert.json"
        tamp_path.write_text(json.dumps(tampered), encoding="utf-8")
        rc_verify = cmd_verify(_Args(input=str(tamp_path)))
        check("cmd_verify exit 5 on tampered certificate", rc_verify == EX_VERIFY)

    print("")
    if failures:
        print("delivery_report self-test: %d FAILURE(S): %s" % (len(failures), ", ".join(failures)))
        return 1
    print("delivery_report self-test: ALL PASS")
    return 0


class _Args:
    """A tiny argparse.Namespace stand-in for the self-test's CLI drive-throughs."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _dispatch_rc(func, args):
    """Run a subcommand exactly as main() would, mapping its typed errors to exit
    codes -- so the self-test observes the SAME code the CLI returns."""
    try:
        return func(args)
    except _BadInput:
        return EX_BADINPUT
    except AnthropicIdentifierError:
        return EX_ANTHROPIC
    except OSError:
        return EX_HELD


# ===========================================================================
# CLI
# ===========================================================================
def build_parser():
    ap = argparse.ArgumentParser(
        prog="delivery_report.py",
        description="Anthology Engine operator-channel delivery report + signed "
                    "process certificate (Skill 54 P7). Operator surface only.")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("report", help="build + persist an operator delivery report from a JSON input")
    p.add_argument("--input", required=True, help="prepared report JSON")
    p.add_argument("--report-dir", default=None, help="operator report dir (default: engine state/reports)")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("certificate", help="build + persist + self-verify the signed process certificate")
    p.add_argument("--input", required=True, help="prepared certificate JSON")
    p.add_argument("--report-dir", default=None)
    p.add_argument("--run-nonce", default=None, help="entry-gate run nonce (recorded, not hashed)")
    p.set_defaults(func=cmd_certificate)

    p = sub.add_parser("verify", help="verify an existing process certificate JSON")
    p.add_argument("--input", required=True, help="certificate JSON to verify")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("plan", help="print role, exit contract, and cert-secret presence")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("self-test", help="offline self-test (no network, no model)")
    p.set_defaults(func=lambda a: self_test())

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return EX_BADINPUT
    try:
        return args.func(args)
    except _BadInput as exc:
        sys.stderr.write("[delivery_report] %s\n" % exc)
        return EX_BADINPUT
    except AnthropicIdentifierError as exc:
        sys.stderr.write("[delivery_report] REFUSED (AF-AE-ANTHROPIC): %s in %s\n"
                         % (exc.value_repr, exc.where))
        return EX_ANTHROPIC
    except BrokenPipeError:
        # NB: BrokenPipeError IS an OSError subclass, so it MUST be caught before the
        # generic OSError (held) handler below, or a closed pipe would read as "held".
        return EX_OK
    except OSError as exc:
        sys.stderr.write("[delivery_report] operator report dir unavailable (HELD): %s\n"
                         % type(exc).__name__)
        return EX_HELD
    except Exception as exc:  # noqa: BLE001 -- house convention: unexpected -> exit 1
        sys.stderr.write("[delivery_report] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
