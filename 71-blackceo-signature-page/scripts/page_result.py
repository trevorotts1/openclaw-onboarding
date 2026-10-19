#!/usr/bin/env python3
"""Signature Launch page-result and next-page handoff builder (S71-05).

Implements the producer side of the shared page contract (Signature
Launch packet doc 02 section 6, doc 07 section 5) for Skill 71 landing
pages. When a run carries a `page-request.json` (the doc 02 section 6
request, issued from the launch context), the report pass in
scripts/stage_gate.py calls emit_for_report() so the run also emits:

  <run_dir>/page-result.json   the doc 02 section 6 result, conforming
                               to references/page-result.schema.json
                               (the skill's pinned copy of the packet
                               schema; the packet, owned by S49, is
                               canonical). The builder validates every
                               result against that schema file before
                               writing and refuses to write an invalid
                               one (fail closed, exit 2 via the CLI).
                               Validation happens fully in memory before
                               either file is written, so a refused
                               emission writes neither artifact and never
                               leaves an orphaned handoff behind.
  <run_dir>/page-handoff.json  the next-page handoff record: next role,
                               route guard state, form mapping, CTA
                               action map, popup states, the S06 install
                               request, and the routing decision.

Routing rule (doc 07 section 4, doc 02 section 4): the landing page
routes onward ONLY on a verified successful native submission or
approved API receipt. The route graph names that precondition as the
guard `verified_native_contact_submit` on the landing node's
`interest_submitted` edge (packet route-graph schema and example). The
recorded run-side equivalent of the popup component's
`sl:interest-verified` event is <run_dir>/interest-submission.json with
event "interest_verified", state "verified" and the adapter's receipt
attached. A capture-only record (the `sl:interest-capture` state,
pending verification), a verified claim without the verified event, or
a verified event without its receipt NEVER authorizes routing; doc 16
section 8 names forged success an automatic failure.

Receipt binding: the adapter's receipt must belong to THIS run. When
the receipt is a dict carrying run-identity fields (tenant_id,
location_id, launch_id, request_id, page_id), every such field it
carries must equal the page-request's value; a receipt naming a
different tenant, launch, or request is another run's receipt and
NEVER authorizes routing here. A receipt carrying no identity fields
at all (a bare string receipt, or a dict without identity fields) is
accepted on presence alone: that is an explicit, documented choice,
not an accident. No approved adapter receipt schema exists yet (the
receipt is the S06 adapter's output and its shape is not contracted),
and the only receipt shape in evidence carries no run identity, so
rejecting identifier-less receipts would refuse the one known-good
form; the binding rule therefore binds every identifier a receipt
DOES carry and records which case applied in the handoff's submission
block (`receipt_binding`), so a later contracted receipt schema can
tighten presence-only acceptance without a silent behavior change.

The page-result schema is closed (additionalProperties: false) and has
no routing field, so routing authorization lives only in
page-handoff.json's `routing` object, which page-result.json references
through its artifacts list. Nothing in the page result advances on a
submission state, and the `status` value derives only from the gate's
recorded stage receipts.

Next role (doc 07 section 5) is read from the approved route graph the
page-request references, never invented: the target role of the landing
node's `interest_submitted` edge, restricted to `product_selection`,
`checkout`, or `free_entry` (the approved free-entry destination, when
the launch record's journey_mode is `free_entry`). `free_entry` is a
journey designation, not a node role (the route-graph schema's role
enum has no such value): it is recorded only when the edge target's
own role is the graph's terminal `thank_you` role under a `free_entry`
journey. Any other target under a free-entry journey keeps its own
role and is never relabeled: a purchase-progression role (upsell_1,
downsell_1, upsell_2) presupposes a purchase a free entry has not
made, so such a route refuses emission like any other
out-of-vocabulary target. A route-graph hash
that no longer matches the page-request's recorded hash is the stale
next-role hash of doc 07 section 10: the handoff is emitted with
routing unauthorized and the mismatch recorded as a blocker.

Proof class: this emitter writes at most L1 (doc 18 section 1). Its
own evidence is schema conformance (L0) plus the gate's deterministic
local records (L1). It never asserts L2 or above and never closes
acceptance unit A07, whose minimum evidence is L3 (an authorized test
contact with the native submission verified by S06); see HANDOFF.md.

Legacy runs (no page-request.json) are untouched: build_and_write
raises NotLaunchRun and nothing is written. A page-request.json that
is PRESENT but unreadable (unparseable, or not a JSON object) is not
a legacy run: the run claims to be a launch run and its request is
corrupt, so build_and_write raises PageResultError, the CLI exits 2
naming the corruption, and the report pass fails visibly instead of
silently treating the run as non-launch.
"""
import hashlib
import json
import os
import re
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
RESULT_SCHEMA_PATH = SKILL_ROOT / "references" / "page-result.schema.json"
CONTRACT_PATH = Path(os.environ.get(
    "STAGE_GATE_CONTRACT",
    str(SKILL_ROOT / "references" / "stage-contract.json"),
))

PAGE_REQUEST_NAME = "page-request.json"
SUBMISSION_NAME = "interest-submission.json"
RESULT_NAME = "page-result.json"
HANDOFF_NAME = "page-handoff.json"
AUTOMATION_HANDOFF_REL = "handoff/automation-handoff.json"

ROUTE_EVENT = "interest_submitted"
VERIFIED_GUARD = "verified_native_contact_submit"
NEXT_ROLES = ("product_selection", "checkout", "free_entry")

# `free_entry` is a journey designation, not a route-graph node role.
# Under a free_entry journey it may be recorded as the next role only
# when the landing edge target's own role is the graph's terminal
# destination role; any other target keeps its own role and is never
# relabeled (see resolve_route).
FREE_ENTRY_TARGET_ROLES = ("thank_you",)

# Run-identity fields an adapter receipt dict may carry. Every such
# field present in the receipt must equal the page-request's value for
# the receipt to count as bound to this run (see receipt_binding).
RECEIPT_IDENTITY_FIELDS = ("tenant_id", "location_id", "launch_id",
                           "request_id", "page_id")

# The interest popup component's contract (owner S71, doc 07 section 4,
# doc 16 section 1): the exact visitor field set and its native CRM
# mapping, and the component's named states. The popup emits
# sl:interest-capture on submit (state pending-verification) and the
# consumer dispatches sl:interest-verified only after a verified
# native submission.
POPUP_COMPONENT = "interest-popup"
POPUP_COMPONENT_VERSION = "1.0.0"
NATIVE_FIELD_MAP = {
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "phone": "phone",
}
POPUP_STATES = ("closed", "open", "pending", "error", "verified")
CAPTURE_EVENT = "interest_capture"
VERIFIED_EVENT = "interest_verified"

SESSION_ENV_VARS = ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID",
                    "CLAUDE_SESSION_ID")
UNKNOWN_SESSIONS = ("", "UNKNOWN")


class NotLaunchRun(Exception):
    """The run carries no page-request.json: not a Signature Launch run."""


class PageResultError(Exception):
    """The page result cannot be built validly; carries failure lines."""

    def __init__(self, lines):
        self.lines = list(lines)
        super().__init__("; ".join(self.lines))


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def session_from_env():
    for name in SESSION_ENV_VARS:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


# ---------------------------------------------------------------------------
# Minimal JSON Schema validation, driven by the schema file itself.
#
# Supports the subset references/page-result.schema.json uses (type,
# const, enum, required, properties, additionalProperties, items,
# minLength, minimum, pattern). It exists so the builder can fail closed
# on its own output in any environment, with or without the third-party
# jsonschema package; the test suite cross-checks with that package
# when it is installed.
# ---------------------------------------------------------------------------

def _type_ok(value, type_name):
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def validate_against_schema(instance, schema, path="$"):
    """Return a list of violation strings (empty when valid)."""
    errors = []
    if not isinstance(schema, dict):
        return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}, "
                      f"got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of "
                      f"{schema['enum']!r}")
    type_spec = schema.get("type")
    if type_spec is not None:
        type_names = type_spec if isinstance(type_spec, list) else [type_spec]
        if not any(_type_ok(instance, t) for t in type_names):
            errors.append(f"{path}: expected type {type_spec!r}, got "
                          f"{type(instance).__name__}")
            return errors
    if isinstance(instance, str):
        min_len = schema.get("minLength")
        if min_len is not None and len(instance) < min_len:
            errors.append(f"{path}: shorter than minLength {min_len}")
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, instance):
            errors.append(f"{path}: {instance!r} does not match "
                          f"pattern {pattern!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: {instance!r} below minimum {minimum}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} "
                                  f"is not allowed")
        for key, subschema in properties.items():
            if key in instance:
                errors.extend(validate_against_schema(
                    instance[key], subschema, f"{path}.{key}"))
    if isinstance(instance, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                errors.extend(validate_against_schema(
                    item, item_schema, f"{path}[{i}]"))
    return errors


# ---------------------------------------------------------------------------
# Run reading helpers (mirroring scripts/stage_gate.py's own readers).
# ---------------------------------------------------------------------------

def stage_order():
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        return list(contract.get("stage_order", []))
    except Exception:
        return []


def load_state(run_dir):
    data = load_json(run_dir / "private" / "state.json") or {}
    data.setdefault("stages", {})
    return data


def load_receipts(run_dir, order):
    receipts = {}
    for stage in order:
        receipt = load_json(run_dir / "private" / "receipts" / f"{stage}.json")
        if receipt is not None:
            receipts[stage] = receipt
    return receipts


def automation_wiring_required(run_dir):
    """Mirror of the gate's Item 31 rule: automation-wiring is required
    exactly when intake publishes to GHL with workflows scope."""
    intake = load_json(run_dir / "intake.json") or {}
    return (intake.get("publish_target") == "ghl"
            and intake.get("automation_scope") == "workflows")


def author_session_for(receipts, order):
    """The run's producer identity: the author session recorded on the
    latest stage receipt that names one (receipts carry author_session,
    falling back to author_agent, per references/artifact-contracts.md);
    else the environment session chain scripts/write_review.py uses;
    else the literal the review writer uses, never an invented one."""
    for stage in reversed(order):
        receipt = receipts.get(stage) or {}
        for key in ("author_session", "author_agent"):
            value = receipt.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return session_from_env() or "unknown-author"


def reviewer_identity_for(run_dir):
    """(reviewer_session, independent_review) from the run's Review
    Receipt v2 files: the latest real (named, non-UNKNOWN) review wins.
    Independence is the file's own computed flag and requires the
    reviewer session to differ from the review's author session."""
    reviews_root = run_dir / "private" / "reviews"
    records = []
    if reviews_root.is_dir():
        for p in sorted(reviews_root.glob("*/*.review.json")):
            data = load_json(p)
            if data is None:
                continue
            reviewer = data.get("reviewer_session")
            reviewer = reviewer.strip() if isinstance(reviewer, str) else ""
            if reviewer in UNKNOWN_SESSIONS:
                continue
            records.append(data)
    if not records:
        return None, False
    records.sort(key=lambda d: str(d.get("reviewed_at") or ""))
    latest = records[-1]
    reviewer = str(latest.get("reviewer_session")).strip()
    author = latest.get("author_session")
    author = author.strip() if isinstance(author, str) else ""
    independent = bool(latest.get("independent_review")) and reviewer != author
    return reviewer, independent


def derive_status(run_dir, order, state, receipts):
    """Page status from the gate's recorded evidence only (doc 02
    section 6 status vocabulary; none implies the next)."""
    stages = state.get("stages", {})
    for stage in order:
        receipt = receipts.get(stage) or {}
        entry = stages.get(stage, {})
        if receipt.get("status") == "blocked" or entry.get("status") == "blocked":
            return "blocked"
    publish = receipts.get("publish-verify") or {}
    install = receipts.get("ghl-install-test") or {}
    if publish.get("status") == "pass":
        return "live_verified"
    if publish.get("status") == "not_authorized" \
            and install.get("status") == "pass":
        return "ready_for_activation"
    if install.get("status") == "pass":
        return "installed_test_verified"
    # locally_verified: the whole local production chain (every stage
    # before ghl-install-test in contract order) is closed. Install and
    # publication have their own statuses above; a page whose local
    # chain is incomplete is merely authored.
    if "ghl-install-test" in order:
        local_chain = order[:order.index("ghl-install-test")]
    else:
        local_chain = order
    if local_chain and all(
            stages.get(s, {}).get("status") == "closed"
            for s in local_chain):
        return "locally_verified"
    return "authored"


def collect_blockers(run_dir, order, state, receipts):
    blockers = []
    stages = state.get("stages", {})
    wiring_required = automation_wiring_required(run_dir)
    for stage in order:
        entry = stages.get(stage, {})
        receipt = receipts.get(stage) or {}
        status = entry.get("status")
        if status == "blocked" or receipt.get("status") == "blocked":
            reason = entry.get("reason") or receipt.get("blocked_reason") \
                or receipt.get("reason") or "recorded blocked"
            blockers.append(f"stage {stage} is blocked: {reason}")
            continue
        if stage == "automation-wiring" and not wiring_required \
                and status == "not_applicable":
            continue
        if receipt.get("status") == "not_authorized":
            # A held stage is a known blocker to any higher status
            # even when the gate recorded the stage itself closed
            # with the not_authorized receipt (doc 07 section 8).
            blockers.append(
                f"stage {stage} is held not_authorized: the stage awaits "
                f"authorization and is not passed (doc 07 section 8)")
            continue
        if status != "closed":
            blockers.append(f"stage {stage} is not closed")
    return blockers


# ---------------------------------------------------------------------------
# Route and submission evidence.
# ---------------------------------------------------------------------------

def resolve_route(run_dir, request):
    """Read the approved route graph the page-request references.

    Returns (route_info, errors). route_info carries next_role,
    next_page_id, guard, and the graph hash facts; next_role is None
    when it cannot be determined from the graph."""
    info = {
        "route_graph_ref": request.get("route_graph_ref"),
        "route_graph_hash_recorded": request.get("route_graph_hash"),
        "route_graph_hash_on_disk": None,
        "hash_matches": False,
        "event": ROUTE_EVENT,
        "guard": None,
        "next_role": None,
        "next_page_id": None,
    }
    ref = request.get("route_graph_ref")
    if not isinstance(ref, str) or not ref.strip():
        return info, ["page-request.json carries no route_graph_ref; the "
                      "approved next role cannot be determined"]
    graph_path = run_dir / ref
    if not graph_path.is_file():
        return info, [f"route graph {ref!r} is not present in the run; "
                      f"the approved next role cannot be determined"]
    info["route_graph_hash_on_disk"] = sha256_file(graph_path)
    info["hash_matches"] = (
        info["route_graph_hash_on_disk"] == request.get("route_graph_hash"))
    graph = load_json(graph_path)
    if graph is None:
        return info, [f"route graph {ref!r} is not readable JSON"]
    nodes = {n.get("page_id"): n for n in graph.get("nodes", [])
             if isinstance(n, dict)}
    page = nodes.get(request.get("page_id"))
    page_role = request.get("page_role")
    if page is None or page.get("role") != page_role:
        return info, [f"route graph has no {page_role!r} node for page "
                      f"{request.get('page_id')!r}"]
    edge = None
    for candidate in graph.get("edges", []):
        if isinstance(candidate, dict) \
                and candidate.get("from") == request.get("page_id") \
                and candidate.get("event") == ROUTE_EVENT:
            edge = candidate
            break
    if edge is None:
        return info, [f"route graph has no {ROUTE_EVENT} edge from the "
                      f"landing node"]
    info["guard"] = edge.get("guard")
    target = nodes.get(edge.get("to"))
    if target is None:
        return info, [f"route graph edge target {edge.get('to')!r} is "
                      f"not a node in the graph"]
    info["next_page_id"] = target.get("page_id")
    target_role = target.get("role")
    launch = load_json(run_dir / "launch.json") or {}
    if target_role in ("product_selection", "checkout"):
        info["next_role"] = target_role
    elif launch.get("journey_mode") == "free_entry" \
            and target_role in FREE_ENTRY_TARGET_ROLES:
        info["next_role"] = "free_entry"
    elif launch.get("journey_mode") == "free_entry":
        return info, [
            f"route graph sends the landing page to role {target_role!r} "
            f"under a free_entry journey; that role is not the approved "
            f"free-entry destination (the graph's "
            f"{FREE_ENTRY_TARGET_ROLES[0]!r} terminal) and is never "
            f"relabeled free_entry; doc 07 section 5 restricts the "
            f"landing next role to product_selection, checkout, or an "
            f"approved free-entry destination, so no conforming page "
            f"result can be emitted for this route"]
    else:
        return info, [
            f"route graph sends the landing page to role {target_role!r}; "
            f"doc 07 section 5 restricts the landing next role to "
            f"product_selection, checkout, or an approved free-entry "
            f"destination, so no conforming page result can be emitted "
            f"for this route"]
    return info, []


def read_submission(run_dir):
    """The run's recorded interest-submission evidence, or None.

    Returns (record, state, receipt_present): state is one of
    "verified", "pending_verification", "failed". Only the verified
    event with its receipt counts as verified: a record that pairs the
    capture event with a verified claim, or the verified event with no
    receipt, is reported as pending, never as verified. Whether the
    receipt belongs to THIS run is a separate check, receipt_binding,
    applied when routing is decided in build_and_write."""
    record = load_json(run_dir / SUBMISSION_NAME)
    if record is None:
        return None, None, False
    receipt = record.get("receipt")
    receipt_present = (isinstance(receipt, dict) and bool(receipt)) or \
        (isinstance(receipt, str) and bool(receipt.strip()))
    if record.get("state") == "failed":
        return record, "failed", receipt_present
    if record.get("event") == VERIFIED_EVENT \
            and record.get("state") == "verified" and receipt_present:
        return record, "verified", True
    return record, "pending_verification", receipt_present


def receipt_binding(request, receipt):
    """Bind the adapter's receipt to this run's page-request.

    Returns (binding, mismatches): binding is "bound" when the receipt
    is a dict carrying at least one run-identity field
    (RECEIPT_IDENTITY_FIELDS) and every identity field it carries
    equals the page-request's value; "contradicted" with one mismatch
    line per contradicting field when any carried identity field names
    a different tenant, location, launch, request, or page (another
    run's receipt); "no_identity_fields" when the receipt carries no
    identity fields to check (a bare string receipt, or a dict without
    identity fields).

    Judgment (explicit, per the module docstring): a receipt with no
    identity fields is accepted on presence alone. No approved adapter
    receipt schema exists yet and the only receipt shape in evidence
    carries no run identity, so refusing identifier-less receipts
    would refuse the known-good form; but every identifier a receipt
    DOES carry binds, and a contradiction fails closed."""
    if not isinstance(receipt, dict):
        return "no_identity_fields", []
    mismatches = []
    checked = 0
    for field in RECEIPT_IDENTITY_FIELDS:
        value = receipt.get(field)
        if value is None:
            continue
        checked += 1
        if value != request.get(field):
            mismatches.append(
                f"receipt {field} {value!r} does not match the "
                f"page-request's {field} {request.get(field)!r}")
    if mismatches:
        return "contradicted", mismatches
    return ("bound" if checked else "no_identity_fields"), []


# ---------------------------------------------------------------------------
# Builders.
# ---------------------------------------------------------------------------

def build_handoff(run_dir, request, route, submission, submission_state,
                  receipt_present, routing_authorized, routing_basis,
                  status, binding="no_identity_fields"):
    automation_handoff = load_json(run_dir / AUTOMATION_HANDOFF_REL)
    native_form_id = None
    if automation_handoff:
        forms = automation_handoff.get("forms") or []
        for form in forms:
            if isinstance(form, dict) and form.get("form_id"):
                native_form_id = form["form_id"]
                break
    install_receipt = load_json(
        run_dir / "private" / "receipts" / "ghl-install-test.json") or {}
    install_executed = install_receipt.get("status") == "pass"
    submission_block = None
    if submission is not None:
        submission_block = {
            "event": submission.get("event"),
            "state": submission_state,
            "receipt_present": receipt_present,
            "receipt_binding": binding,
            "recorded_at": submission.get("recorded_at"),
            "record_ref": SUBMISSION_NAME,
        }
    return {
        "schema_version": "1.0",
        "kind": "skill71-page-handoff",
        "tenant_id": request.get("tenant_id"),
        "location_id": request.get("location_id"),
        "launch_id": request.get("launch_id"),
        "revision": request.get("revision"),
        "request_id": request.get("request_id"),
        "page_id": request.get("page_id"),
        "input_hash": request.get("input_hash"),
        "page_role": request.get("page_role"),
        "page_status": status,
        "next_role": route["next_role"],
        "next_page_id": route["next_page_id"],
        "route": {
            "route_graph_ref": route["route_graph_ref"],
            "route_graph_hash_recorded": route["route_graph_hash_recorded"],
            "route_graph_hash_on_disk": route["route_graph_hash_on_disk"],
            "hash_matches": route["hash_matches"],
            "event": route["event"],
            "guard": route["guard"],
        },
        "form_mapping": {
            "component": POPUP_COMPONENT,
            "component_version": POPUP_COMPONENT_VERSION,
            "native_field_map": dict(NATIVE_FIELD_MAP),
            "native_form_id": native_form_id,
            "native_bindings_ref": AUTOMATION_HANDOFF_REL
            if automation_handoff else None,
        },
        "cta_action_map": [
            {"on": "cta_click", "opens_component": POPUP_COMPONENT},
            {"on": "form_submit", "component": POPUP_COMPONENT,
             "emits": "sl:interest-capture"},
            {"on": "sl:interest-verified", "guard": route["guard"],
             "effect": "route", "to_role": route["next_role"],
             "to_page_id": route["next_page_id"]},
        ],
        "popup_states": list(POPUP_STATES),
        "submission": submission_block,
        "routing": {
            "authorized": routing_authorized,
            "basis": routing_basis,
        },
        "install_request": {
            "consumer": "S06",
            "target": request.get("allowed_write_target"),
            "status": "executed" if install_executed else "pending",
            "evidence_ref": "private/receipts/ghl-install-test.json"
            if install_executed else None,
        },
        "result_ref": RESULT_NAME,
        "test_only": bool(request.get("test_only")),
    }


def build_result(run_dir, request, status, blockers, artifacts,
                 author_session, reviewer_session, independent_review,
                 proof_class):
    return {
        "schema_version": "1.0",
        "tenant_id": request.get("tenant_id"),
        "location_id": request.get("location_id"),
        "launch_id": request.get("launch_id"),
        "revision": request.get("revision"),
        "request_id": request.get("request_id"),
        "input_hash": request.get("input_hash"),
        "page_id": request.get("page_id"),
        "page_role": request.get("page_role"),
        "status": status,
        "artifacts": artifacts,
        "author_session": author_session,
        "reviewer_session": reviewer_session,
        "independent_review": independent_review,
        "proof_class": proof_class,
        "blockers": blockers,
        "native_bindings_ref": AUTOMATION_HANDOFF_REL
        if (run_dir / AUTOMATION_HANDOFF_REL).is_file() else None,
        "test_only": bool(request.get("test_only")),
    }


def artifact_refs(run_dir, state):
    """Artifact references for the result: the gate's close-recorded
    stage artifact hashes, plus the stage receipts themselves (the
    stage receipts doc 07 section 5 names), hashed from disk."""
    merged = {}
    for entry in (state.get("stages") or {}).values():
        if isinstance(entry, dict):
            for rel, digest in (entry.get("artifact_hashes") or {}).items():
                merged[rel] = digest
    refs = {rel: digest for rel, digest in merged.items()}
    receipts_dir = run_dir / "private" / "receipts"
    if receipts_dir.is_dir():
        for p in sorted(receipts_dir.glob("*.json")):
            rel = str(p.relative_to(run_dir))
            if rel not in refs:
                refs[rel] = sha256_file(p)
    report_json = run_dir / "REPORT.json"
    if report_json.is_file() and "REPORT.json" not in refs:
        refs["REPORT.json"] = sha256_file(report_json)
    return [{"path": rel, "sha256": refs[rel]} for rel in sorted(refs)]


def build_and_write(run_dir):
    """Build and write page-handoff.json + page-result.json for a run.

    Returns (result_path, handoff_path, routing_authorized).
    Raises NotLaunchRun when the run carries no page-request.json, and
    PageResultError when no valid result can be emitted (including a
    page-request.json that is present but corrupt). Both artifacts
    are validated in memory before either is written, so a
    PageResultError leaves neither file written by this call."""
    run_dir = Path(run_dir)
    request_path = run_dir / PAGE_REQUEST_NAME
    if not request_path.is_file():
        raise NotLaunchRun(
            f"{run_dir} carries no {PAGE_REQUEST_NAME}")
    request = load_json(request_path)
    if request is None:
        raise PageResultError(
            [f"{PAGE_REQUEST_NAME} is present in {run_dir} but is not "
             f"readable JSON (corrupt or not a JSON object); the run "
             f"claims to be a Signature Launch run, so this is an "
             f"error state, not a legacy run, and no page result can "
             f"be emitted from a corrupt request"])
    for field in ("tenant_id", "location_id", "launch_id", "revision",
                  "request_id", "input_hash", "page_id"):
        value = request.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise PageResultError(
                [f"page-request.json is missing {field!r}; the page "
                 f"result cannot be emitted without it"])

    order = stage_order()
    state = load_state(run_dir)
    receipts = load_receipts(run_dir, order)
    status = derive_status(run_dir, order, state, receipts)
    blockers = collect_blockers(run_dir, order, state, receipts)

    route, route_errors = resolve_route(run_dir, request)
    fatal = [e for e in route_errors if "restricts the landing next role" in e]
    if fatal:
        raise PageResultError(fatal)
    for line in route_errors:
        blockers.append(f"route: {line}")
    if route["next_role"] is not None and not route["hash_matches"]:
        blockers.append(
            "route graph hash mismatch: the page-request's recorded "
            "route_graph_hash does not match the route graph in the run "
            "(stale next-role hash, doc 07 section 10); routing is not "
            "authorized")

    submission, submission_state, receipt_present = read_submission(run_dir)
    binding, binding_mismatches = ("no_identity_fields", [])
    if submission is not None and receipt_present:
        binding, binding_mismatches = receipt_binding(
            request, submission.get("receipt"))
    if submission_state == "verified":
        routing_authorized = True
        routing_basis = (
            "interest-submission.json records the verified event "
            "(sl:interest-verified) with the delivery adapter's receipt; "
            f"guard {VERIFIED_GUARD} is satisfied")
        if binding == "contradicted":
            routing_authorized = False
            routing_basis = (
                "a verified submission is recorded, but the adapter's "
                "receipt is not bound to this run: "
                + "; ".join(binding_mismatches)
                + "; a receipt naming a different run never authorizes "
                "routing here (receipt binding, doc 07 section 4)")
            blockers.append(
                "adapter receipt is not bound to this run: "
                + "; ".join(binding_mismatches)
                + "; routing is not authorized")
        elif route["guard"] != VERIFIED_GUARD:
            routing_authorized = False
            routing_basis = (
                f"the route graph's landing edge guard is "
                f"{route['guard']!r}, not {VERIFIED_GUARD!r}; the "
                f"verified-submission precondition the contract names "
                f"is not the edge's guard")
        elif not route["hash_matches"]:
            routing_authorized = False
            routing_basis = (
                "a verified submission is recorded, but the route "
                "graph hash does not match the page-request's recorded "
                "hash (stale next-role hash); routing is not authorized")
        elif route["next_role"] is None:
            routing_authorized = False
            routing_basis = (
                "a verified submission is recorded, but the approved "
                "next role could not be determined from the route graph")
    elif submission_state == "pending_verification":
        routing_authorized = False
        routing_basis = (
            "an interest capture is recorded but not verified (the "
            "popup's post-submit state is pending verification until "
            "the delivery adapter verifies the native submission); "
            f"guard {VERIFIED_GUARD} is not satisfied and routing is "
            f"not authorized")
        blockers.append(
            "interest submission recorded but not verified: routing "
            "is not authorized (doc 07 section 4)")
    elif submission_state == "failed":
        routing_authorized = False
        routing_basis = (
            "the recorded native submission failed; routing is not "
            "authorized")
        blockers.append(
            "interest submission recorded as failed: routing is not "
            "authorized (doc 07 section 4)")
    else:
        routing_authorized = False
        routing_basis = (
            "no interest submission is recorded for this run; routing "
            f"is not authorized until a verified native submission "
            f"satisfies guard {VERIFIED_GUARD}")

    author_session = author_session_for(receipts, order)
    reviewer_session, independent_review = reviewer_identity_for(run_dir)
    proof_class = "L1" if status in (
        "locally_verified", "installed_test_verified",
        "ready_for_activation", "live_verified") else "L0"

    handoff = build_handoff(run_dir, request, route, submission,
                             submission_state, receipt_present,
                             routing_authorized, routing_basis, status,
                             binding)
    handoff_path = run_dir / HANDOFF_NAME
    # Write ordering: both artifacts are built and the result is
    # validated entirely in memory BEFORE either file is written, so
    # a refused emission writes neither file and never leaves an
    # orphaned page-handoff.json referencing a page-result.json that
    # does not exist. Files from an earlier successful emission are
    # left untouched by a refused one, never half-overwritten. The
    # handoff's artifact hash is taken over the exact bytes that will
    # be written.
    handoff_text = json.dumps(handoff, indent=2) + "\n"

    artifacts = artifact_refs(run_dir, state)
    artifacts.append({"path": HANDOFF_NAME,
                      "sha256": hashlib.sha256(
                          handoff_text.encode("utf-8")).hexdigest()})
    artifacts.sort(key=lambda a: a["path"])

    result = build_result(run_dir, request, status, blockers, artifacts,
                          author_session, reviewer_session,
                          independent_review, proof_class)
    schema = load_json(RESULT_SCHEMA_PATH)
    if schema is None:
        raise PageResultError(
            [f"page-result schema {RESULT_SCHEMA_PATH} is missing or "
             f"unreadable; refusing to emit an unvalidated result"])
    violations = validate_against_schema(result, schema)
    if violations:
        raise PageResultError(
            ["page-result.json would violate "
             "references/page-result.schema.json:"]
            + [f"  {v}" for v in violations])
    result_path = run_dir / RESULT_NAME
    handoff_path.write_text(handoff_text, encoding="utf-8")
    result_path.write_text(json.dumps(result, indent=2) + "\n",
                           encoding="utf-8")
    return result_path, handoff_path, routing_authorized


def emit_for_report(run_dir):
    """stage_gate.py report-pass hook. Returns (ok, lines): ok False
    only when the run IS a launch run whose result cannot be built
    validly; a run without a page-request is not this hook's concern."""
    try:
        result_path, handoff_path, authorized = build_and_write(run_dir)
    except NotLaunchRun:
        return True, []
    except PageResultError as exc:
        return False, ["FAIL: page-result emission (S71-05):"] \
            + [f"- {line}" for line in exc.lines]
    return True, [
        f"page-result: wrote {result_path} and {handoff_path} "
        f"(S71-05; routing authorized: "
        f"{'yes' if authorized else 'no'})"]
