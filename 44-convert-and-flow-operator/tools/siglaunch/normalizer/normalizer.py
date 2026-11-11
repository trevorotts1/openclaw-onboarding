"""S44-04 production normalizer (DESIGN-S44-04-v1.md).

Converts a native order/transaction read-back into the canonical
purchase-event envelope, or into a QUARANTINE record — the only response
to ambiguity. Unlike the L1 reference (events.py, which raises), this
module returns quarantine as data and persists it as a visible review
item in the durable store; nothing quarantined grants, tags, enrolls,
or sends.

Rules enforced here (design sections 3-8):
- slot comes ONLY from verified bindings; the native submission label
  is never read (it says 'Upsell' for U1, D1 and U2 alike);
- payment_status comes ONLY from the verified native transaction
  status; a submission without a transaction status is `unknown`,
  which never grants; a status outside the schema enum quarantines,
  never coerces;
- identity is the verified provider event id within tenant; absent or
  empty quarantines; transaction refs are never synthesized;
- tenant/location/launch must match the launch context the bindings
  came from, or the event quarantines (tenant_mismatch);
- cancellation / access-change kinds are NOT mapped yet (the adapter
  addendum owns that mapping) — they quarantine as unmapped_event_kind
  rather than ride an improvised mapping;
- contact_ref (schema v1.1, CR-S44-001 ruling): emitted only when the
  read-back supplies the opaque native contact ID AND a v1.1 schema is
  configured; otherwise it travels in processing context and the event
  stamps 1.0. Never derived from a name or email.
- parent_order_ref (schema v1.2, CR-S44-003 ruling): emitted only when
  the native read-back itself carries the opaque provider order id of
  the initial order AND a v1.2 schema is configured. Never synthesized,
  never derived, never required, never identity/grouping/dedupe. When it
  is carried the event stamps 1.2 (S82 refuses the field on 1.1); when
  it is absent the old-stream stamp is unchanged (1.1 with contact_ref,
  else 1.0).

Runtime binding (issue 31, WP-17b): `normalizer.py --emit-binding <dir|file>`
is the install step that writes runtime-binding.json, the record Skill 83's
checkout rule reads before a checkout piece may claim live_verified or
ready_for_activation. It writes nothing until the REAL normalizer, processor
and store have just proven, on probe events in a throwaway database, that a
verified paid event grants once, a redelivery or replay grants nothing more,
and no non-paid status (pending, failed, requires_customer_action, unknown)
grants; a refund only revokes. A failed probe raises BindingRefused and the
CLI exits 7 with the file untouched. `--verify-binding <dir|file>` is the
read-only check that a record was written by this step: it re-runs the probes
and refuses a record whose values or evidence digest the probes do not
reproduce, so a hand-written file does not verify. See RUNTIME-BINDING.md
beside this file.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# PYDEPS-ACTIVATION:BEGIN (shared contract, byte-identical in every file that imports jsonschema; stdlib only)
# jsonschema lives in <root>/pydeps/py<X.Y>/ when pip refuses the interpreter (PEP 668); put it on sys.path first.
import os as _os
import sys as _sys

_pytag = "py%d.%d" % _sys.version_info[:2]
_pyroot = _os.environ.get("OPENCLAW_ROOT") or (
    "/data/.openclaw" if _os.path.isdir("/data/.openclaw") else _os.path.expanduser("~/.openclaw"))
_sys.path[:0] = [_d for _d in (
    [_os.environ["OC_PYDEPS_DIR"]] if _os.environ.get("OC_PYDEPS_DIR") else
    [_os.path.join(_pyroot, "pydeps", _pytag), _os.path.expanduser("~/.claude/pydeps/" + _pytag)])
    if _os.path.isdir(_d) and _d not in _sys.path]
del _pytag, _pyroot
# PYDEPS-ACTIVATION:END

import jsonschema

# S44-19 (decision: native GHL for Black Friday 2026). The siglaunch
# pipeline has no runner (no CLI, webhook, poller or production catalog).
# The declared Black Friday 2026 purchase path is the native Convert and
# Flow post-sale workflows; this module refuses to run as a production
# entry until a runner exists and an owner-approved change flips the flag.
BLACK_FRIDAY_2026_PURCHASE_PATH = "native-ghl-post-sale-workflows"
PRODUCTION_ENTRY_ENABLED = False
EXIT_NOT_PRODUCTION = 6
# --emit-binding (write) and --verify-binding (read-only check) are the two
# install-step modes. Neither ingests a live event or starts a runner, so
# neither flips PRODUCTION_ENTRY_ENABLED.
EXIT_BINDING_REFUSED = 7
BINDING_FILE = "runtime-binding.json"
BINDING_NORMALIZER = "44/tools/siglaunch/normalizer"


def main(argv=None) -> int:
    import sys
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] in (["--emit-binding"], ["--verify-binding"]):
        if len(args) != 2:
            print("usage: normalizer.py --emit-binding|--verify-binding <directory-or-file>", file=sys.stderr)
            return 2
        try:
            print((emit_binding if args[0] == "--emit-binding" else verify_binding)(args[1]))
        except BindingRefused as exc:
            print("siglaunch normalizer: %s" % exc, file=sys.stderr)
            return EXIT_BINDING_REFUSED
        return 0
    print("siglaunch %s is not a production entry: the Black Friday 2026 "
          "purchase path is %s (no runner exists; refusing)."
          % (__name__ if __name__ != "__main__" else "module",
             BLACK_FRIDAY_2026_PURCHASE_PATH), file=sys.stderr)
    return EXIT_NOT_PRODUCTION

# Staging note: the schema is vendored beside this module (copied from
# packet/reference/schemas/purchase-event.schema.json) so the staged
# tree is self-contained; the work-tree original resolved it from the
# packet by a parents[4] relative path.
_PACKET_SCHEMA = (Path(__file__).resolve().parent
                  / "purchase-event.schema.json")
_SCHEMA_V10 = json.loads(_PACKET_SCHEMA.read_text())

# Schema v1.1 switch (CR-S44-001): the v1.1 schema is vendored beside
# this module too (byte copy of shared-utils/signature_launch/domain/
# purchase-event.schema.json on main). It is loaded once here and
# wired into ingest() as the default schema_v11, so the production
# pipeline stamps 1.1 and carries contact_ref whenever a read-back
# supplies it. Direct normalize() callers keep the explicit-injection
# contract: no schema_v11 passed, no 1.1 stamp (context only).
_V11_SCHEMA_PATH = (Path(__file__).resolve().parent
                    / "purchase-event.v1.1.schema.json")
_SCHEMA_V11 = (json.loads(_V11_SCHEMA_PATH.read_text())
               if _V11_SCHEMA_PATH.exists() else None)

# Schema v1.2 switch (CR-S44-003, consumer gate closed): the v1.2 schema
# is vendored beside this module too (byte copy of shared-utils/
# signature_launch/domain/purchase-event.schema.json on main, which the
# processor and the S82/S79 consumers already accept). Same explicit-
# injection contract as v1.1: normalize() callers pass schema_v12 to
# enable the 1.2 stamp; ingest() wires it by default, so the production
# pipeline stamps 1.2 and carries parent_order_ref whenever (and only
# when) the native read-back supplies it.
_V12_SCHEMA_PATH = (Path(__file__).resolve().parent
                    / "purchase-event.v1.2.schema.json")
_SCHEMA_V12 = (json.loads(_V12_SCHEMA_PATH.read_text())
               if _V12_SCHEMA_PATH.exists() else None)

PAYMENT_STATUSES = {"pending", "succeeded", "failed",
                    "requires_customer_action", "refunded",
                    "partially_refunded", "unknown"}
EVENT_TYPES = {"purchase_observed", "payment_updated", "refund_observed",
               "subscription_updated"}

# native read-back kind -> envelope event_type. Cancellation and access
# change are deliberately ABSENT: underdetermined by the sources, fixed
# by the adapter addendum, quarantined until then (design section 4).
KIND_MAP = {
    "order_paid": "purchase_observed",
    "purchase": "purchase_observed",
    "payment_updated": "payment_updated",
    "refund": "refund_observed",
    "subscription": "subscription_updated",
    "subscription_renewal": "subscription_updated",
}
UNMAPPED_KINDS = {"cancellation", "access_change"}


class LaunchContext:
    def __init__(self, tenant_id: str, location_id: str, launch_id: str,
                 bindings: dict[str, str]):
        self.tenant_id = tenant_id
        self.location_id = location_id
        self.launch_id = launch_id
        self.bindings = bindings


def _quarantine(reason_code: str, detail: str, readback: dict) -> dict:
    return {"quarantine": {
        "reason_code": reason_code,
        "detail": detail,
        "evidence_ref": readback.get("evidence_ref"),
        "readback": readback,
    }}


def normalize(readback: dict, ctx: LaunchContext,
              schema_v11: Optional[dict] = None,
              schema_v12: Optional[dict] = None) -> dict:
    """Return {"event": envelope, "contact_ref_context": str|None} or
    {"quarantine": {...}}. Never raises for ambiguity."""
    # tenant integrity first: the read-back must belong to the launch
    # context whose bindings would resolve its slots
    for field, expected in (("tenant_id", ctx.tenant_id),
                            ("location_id", ctx.location_id),
                            ("launch_id", ctx.launch_id)):
        if readback.get(field) != expected:
            return _quarantine(
                "tenant_mismatch",
                f"read-back {field}={readback.get(field)!r} does not match "
                f"the launch context {expected!r}", readback)
    # verified provider event identity is the dedup anchor; absent = stop
    if not readback.get("provider_event_id"):
        return _quarantine("no_verified_event_identity",
                           "read-back carries no provider_event_id",
                           readback)
    # event kind: explicit schema event_type wins; else the kind map;
    # cancellation/access-change and unknown kinds quarantine
    event_type = readback.get("event_type")
    if event_type is not None and event_type not in EVENT_TYPES:
        return _quarantine("unmapped_event_kind",
                           f"event_type {event_type!r} is outside the "
                           "schema enum; never coerced", readback)
    if event_type is None:
        kind = readback.get("native_event_kind")
        if kind in UNMAPPED_KINDS or kind not in KIND_MAP:
            return _quarantine(
                "unmapped_event_kind",
                f"native kind {kind!r} has no settled envelope mapping "
                "(adapter addendum owns it)", readback)
        event_type = KIND_MAP[kind]
    # payment truth: only the verified transaction status; a bare
    # submission is `unknown`; an out-of-enum value quarantines
    status = readback.get("payment_status")
    if status is None:
        status = "unknown"
    elif status not in PAYMENT_STATUSES:
        return _quarantine("schema_invalid",
                           f"payment_status {status!r} is outside the "
                           "schema enum; never coerced", readback)
    # lines: all of them, every time; one unmapped product quarantines
    # the whole event (partial normalization would drop lines silently)
    lines = []
    for item in readback.get("line_items", []):
        slot = ctx.bindings.get(item.get("native_product_ref"))
        if slot is None:
            return _quarantine(
                "unmapped_native_product",
                f"no verified binding for native product "
                f"{item.get('native_product_ref')!r} in this launch",
                readback)
        lines.append({
            "native_line_ref": item["native_line_ref"],
            "offer_id": item["offer_id"],
            "slot": slot,
            "currency": item["currency"],
            "amount_minor": int(item["amount_minor"]),
            "entitlement_ids": list(item["entitlement_ids"]),
        })
    contact_ref = readback.get("contact_ref")
    parent_order_ref = readback.get("parent_order_ref")
    event = {
        "schema_version": "1.0",
        "tenant_id": ctx.tenant_id,
        "location_id": ctx.location_id,
        "launch_id": ctx.launch_id,
        "provider": readback["provider"],
        "event_id": readback["provider_event_id"],
        "event_type": event_type,
        "native_order_ref": readback["native_order_ref"],
        # never synthesized: absent stays null, the action key falls
        # back to the order ref downstream
        "native_transaction_ref": readback.get("native_transaction_ref"),
        "occurred_at": readback["occurred_at"],
        "received_at": readback["received_at"],
        "payment_status": status,
        "line_items": lines,
        "evidence_ref": readback["evidence_ref"],
        "test_only": bool(readback.get("test_only", False)),
    }
    schema = _SCHEMA_V10
    if parent_order_ref and schema_v12 is not None:
        # v1.2: the field is version-scoped to 1.2 (a 1.1 event carrying
        # it is refused by the S82 consumer), so the stamp follows the
        # field. contact_ref rides along when supplied: 1.2 defines it.
        if contact_ref:
            event["contact_ref"] = contact_ref
        event["parent_order_ref"] = parent_order_ref
        event["schema_version"] = "1.2"
        schema = schema_v12
    elif contact_ref and schema_v11 is not None:
        event["contact_ref"] = contact_ref
        event["schema_version"] = "1.1"
        schema = schema_v11
    try:
        jsonschema.validate(event, schema)
    except jsonschema.ValidationError as e:
        return _quarantine("schema_invalid",
                           f"normalized envelope failed validation: "
                           f"{e.message}", readback)
    return {"event": event,
            "contact_ref_context": contact_ref}


def ingest(store, readback: dict, ctx: LaunchContext,
           schema_v11: Optional[dict] = None,
           schema_v12: Optional[dict] = None) -> tuple[str, dict]:
    """Pipeline glue (design section 1): normalize, then record-if-unseen
    in the durable inbox, or persist the quarantine as a review item.
    Returns ("accepted"|"duplicate"|"quarantined", payload)."""
    if schema_v11 is None:
        schema_v11 = _SCHEMA_V11  # the vendored v1.1 wiring (above)
    if schema_v12 is None:
        schema_v12 = _SCHEMA_V12  # the vendored v1.2 wiring (above)
    result = normalize(readback, ctx, schema_v11=schema_v11,
                       schema_v12=schema_v12)
    if "quarantine" in result:
        q = result["quarantine"]
        qid = store.add_quarantine(
            ctx.tenant_id, readback.get("location_id"),
            readback.get("launch_id"), q["reason_code"], q["detail"],
            q["evidence_ref"], readback, readback.get("received_at", ""))
        return "quarantined", {"quarantine_id": qid, **q}
    event = result["event"]
    seen = store.record_event_if_unseen(
        event["tenant_id"], event["provider"], event["event_id"], event)
    return ("accepted" if seen else "duplicate"), result


class BindingRefused(Exception):
    """A probe failed: runtime-binding.json is not written."""


def _sibling(dirname: str, filename: str):
    """Load a sibling siglaunch module by file path: no sys.path edits, no name clash."""
    path = Path(__file__).resolve().parent.parent / dirname / filename
    spec = importlib.util.spec_from_file_location("siglaunch_binding_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _readback(ctx: LaunchContext, event_id: str, line_ref: str, status: Optional[str],
              kind: str = "order_paid") -> dict:
    rb = {
        "tenant_id": ctx.tenant_id, "location_id": ctx.location_id,
        "launch_id": ctx.launch_id, "provider": "probe",
        "provider_event_id": event_id, "native_event_kind": kind,
        "native_order_ref": "ord-" + event_id,
        "native_transaction_ref": "txn-" + event_id,
        "occurred_at": "2026-01-01T00:00:00Z",
        "received_at": "2026-01-01T00:00:01Z",
        "line_items": [{"native_line_ref": line_ref,
                        "native_product_ref": "probe-main", "offer_id": "probe-offer",
                        "currency": "USD", "amount_minor": 100,
                        "entitlement_ids": ["probe-ent"]}],
        "evidence_ref": "probe/" + event_id, "test_only": True,
    }
    if status is not None:  # absent stays absent: the normalizer reads it as `unknown`
        rb["payment_status"] = status
    return rb


def probe_binding(processor_module=None, store_module=None) -> dict:
    """Run the real normalizer, processor and store on probe events in a throwaway
    database and report what they did. {"ok", "probes", "digest"}; the digest is over the
    deterministic transcript (no clock, no random id), so re-running the probes re-derives it.
    The module arguments exist so a test can break one claim and watch the record refuse."""
    processor_module = processor_module or _sibling("processor", "processor.py")
    store_module = store_module or _sibling("store", "store.py")
    ctx = LaunchContext("PROBE-T", "PROBE-LOC", "PROBE-LN", {"probe-main": "main"})
    probes: list = []

    def run(name, fn):
        try:
            ok, observed = fn()
        except Exception as exc:  # a crashing path is a failed probe, never a pass
            ok, observed = False, {"error": type(exc).__name__}
        probes.append({"probe": name, "ok": bool(ok), "observed": observed})

    with tempfile.TemporaryDirectory() as tmp:
        store = store_module.Store(Path(tmp) / "probe.db")
        proc = processor_module.DurableProcessor(store)
        paid = _readback(ctx, "ev-paid", "line-paid", "succeeded")
        seen = {}

        def book(line_ref):
            return store.entitlement_state(ctx.tenant_id, line_ref, "probe-ent")

        def paid_event_grants():
            status, res = ingest(store, paid, ctx)
            seen["event"] = res.get("event")
            out = proc.process(res["event"])
            return (status == "accepted" and out["result"] == "processed" and book("line-paid") == "active",
                    {"ingest": status, "result": out["result"], "book": book("line-paid")})

        def redelivery_is_duplicate():
            status = ingest(store, paid, ctx)[0]
            return status == "duplicate", {"ingest": status}

        def replay_grants_nothing_more():
            out = proc.process(seen["event"])
            active = store.active_entitlements(ctx.tenant_id)
            return (out["actions_created"] == 0 and out["rights_reconciled"] == 0 and active == ["probe-ent"],
                    {"actions_created": out["actions_created"], "rights_reconciled": out["rights_reconciled"],
                     "active": active})

        def never_grants(status):
            def probe():
                line = "line-" + (status or "unknown")
                ingested, res = ingest(store, _readback(ctx, "ev-" + line, line, status), ctx)
                out = proc.process(res["event"])
                return (out["result"] == "no_grant:" + (status or "unknown") and book(line) is None,
                        {"ingest": ingested, "result": out["result"], "book": book(line)})
            return probe

        def refund_revokes():
            rb = _readback(ctx, "ev-refund", "line-paid", "refunded", kind="refund")
            ingested, res = ingest(store, rb, ctx)
            out = proc.process(res["event"])
            return (out["result"] == "refund_applied" and book("line-paid") == "revoked",
                    {"ingest": ingested, "result": out["result"], "book": book("line-paid")})

        run("paid-event-grants", paid_event_grants)
        run("redelivery-is-duplicate", redelivery_is_duplicate)
        run("replay-grants-nothing-more", replay_grants_nothing_more)
        for status in ("pending", "failed", "requires_customer_action", None):
            run((status or "unknown") + "-never-grants", never_grants(status))
        run("refund-revokes-never-grants", refund_revokes)
        store._conn().close()  # the throwaway database; Store has no public close

    transcript = json.dumps(probes, sort_keys=True, separators=(",", ":"))
    return {"ok": all(p["ok"] for p in probes), "probes": probes,
            "digest": hashlib.sha256(transcript.encode()).hexdigest()}


def _proven_record(**inject) -> dict:
    """The six-key record this normalizer can vouch for right now: the probes run, every one passed,
    and the values below are what they proved. Raises BindingRefused otherwise. `verified_at` is the
    one key the probes do not determine; the caller stamps it."""
    if _SCHEMA_V12 is None:  # schema_version is read from the vendored 1.2 schema; no fallback to an older one
        raise BindingRefused("the vendored purchase-event v1.2 schema is missing, %s not written" % BINDING_FILE)
    result = probe_binding(**inject)
    if not result["ok"]:
        failed = ", ".join(p["probe"] for p in result["probes"] if not p["ok"])
        raise BindingRefused("probes failed, %s not written: %s" % (BINDING_FILE, failed))
    return {
        "normalizer": BINDING_NORMALIZER,
        "schema_version": _SCHEMA_V12["properties"]["schema_version"]["const"],
        "grant_policy": "once",
        "paid_edges_only": True,
        "evidence_ref": "siglaunch-normalizer-probe:sha256:" + result["digest"],
    }


def _binding_path(out) -> Path:
    out = Path(out)
    return out / BINDING_FILE if out.is_dir() else out


def emit_binding(out, *, now: Optional[datetime] = None, **inject) -> Path:
    """Write runtime-binding.json (to <out>/runtime-binding.json when `out` is a directory,
    else to `out`) once, and only if, every probe passes. Exactly the six contract keys."""
    record = _proven_record(**inject)
    path = _binding_path(out)
    if not path.parent.is_dir():
        raise BindingRefused("%s cannot be written: %s is not a directory" % (BINDING_FILE, path.parent))
    record["verified_at"] = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    return path


def verify_binding(path, **inject) -> Path:
    """Refuse a runtime-binding.json this normalizer did not write. The evidence digest is over a
    deterministic probe transcript, so the probes are run again and the record must carry exactly the
    six keys, every value the probes prove now, and a well-formed verified_at. A hand-written file, a
    flipped value or a record from a normalizer that behaved differently does not verify.
    Read-only: nothing is written."""
    path = _binding_path(path)
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise BindingRefused("%s is not readable JSON (%s)" % (path.name, type(exc).__name__))
    expected = _proven_record(**inject)
    if not isinstance(record, dict) or set(record) != set(expected) | {"verified_at"}:
        raise BindingRefused("%s must be an object with exactly the six contract keys" % path.name)
    wrong = sorted(k for k, v in expected.items() if record[k] != v or type(record[k]) is not type(v))
    try:
        datetime.strptime(record["verified_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        wrong.append("verified_at")
    if wrong:
        raise BindingRefused("%s does not match what this normalizer proves: %s" % (path.name, ", ".join(wrong)))
    return path


if __name__ == "__main__":
    raise SystemExit(main())
