#!/usr/bin/env python3
# =============================================================================
# LAUNCH-C — PLAN READER :: Skill 50 build plans -> launch automation builds
# -----------------------------------------------------------------------------
# Reads the U-CONTRACT launch plan (shared-utils/signature_launch_contract) and
# the Skill 50 P4 build plan(s) (50-email-engine/schema/build-plan.schema.json)
# and emits ONE automation-build document for the automation lanes (WF-AUTO-*).
#
# Deterministic, stdlib-only, model-free, DRAFT-ONLY. It never sends, never
# calls a provider, and never publishes: every workflow it carries must already
# be status "draft" in the Skill 50 plan or the read FAILS CLOSED.
#
# L07 (UL-010) COMPILER DUTIES
#   * validate the launch calendar: IANA zone, offset agreement, DST gap/overlap
#     and strict phase order (doors_open < launch < doors_close)
#   * compile absolute (calendar-anchored) and relative (enrollment-anchored)
#     schedule nodes, apply past-time policy and close-time suppression
#   * enforce every declared dependency and required output; a missing page URL,
#     missing/incomplete text set, missing build plan or email-count mismatch
#     BLOCKS the build instead of warning
#   * carry eligibility / lifecycle / sender metadata (named references only)
#     through to the provider compiler, with stable unit keys and expected
#     graph hashes for the build journal
#
# USAGE
#   plan_reader.py --launch-plan plan.json --build-plan pre.json [--build-plan ...]
#                  [--sequence-map map.json] [--now 2026-11-01T00:00:00-05:00]
#                  --out automation-builds.json
#   plan_reader.py --selftest
#
#   map.json: {"email_pre_launch": "path/to/build-plan.json", ...}
#   Without a map, each build plan is bound to a launch email_sequence by
#   _meta.sequence_id / _meta.source_ids.sequence_id, then by file stem, then by
#   the single sequence id its workflow keys/names/tags name. Ambiguity fails.
#
# EXIT CODES: 0 ok / 2 usage-or-structural-invalid / 3 IO
# =============================================================================
"""Skill 50 build plans -> launch automation builds (launch-c)."""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_IO = 3

SCHEMA_VERSION = "1.0.0"

FAMILIES = {
    "pre_launch", "opt_in", "event_reminders", "post_sale", "upsell_downsell",
    "abandoned_checkout", "page_retargeting", "onboarding_review", "win_back",
    "failed_payment", "conversation_ai_reply",
}
RAILS = {"ghl_api", "skill44_engine", "unknown"}
STEP_TYPES = {"email", "wait"}
UNIT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
LAUNCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CLOCK_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
# Credential-shaped keys must never travel in a plan; sender configuration is a
# named reference and binds under a *_ref key.
CREDENTIAL_KEY_RE = re.compile(
    r"(password|passwd|secret|api[-_]?key|credential|private[-_]?key|(^|_)token(_|$))",
    re.IGNORECASE,
)

# Phase ranks: a phase may only wait on a strictly earlier phase.
PHASE_RANK = {"pre_launch": 0, "main_launch": 1, "doors_closing": 2}
PROMOTIONAL_KINDS = {
    "pre_launch", "main_launch", "doors_closing",
    "upsell_followup", "downsell_followup", "abandoned_checkout",
}
# Access/entitlement mail is transactional: a purchase never cancels it.
TRANSACTIONAL_KINDS = {"welcome_access"}

WAIT_SECONDS = {
    "minutes": 60, "minute": 60,
    "hour": 3600, "hours": 3600,
    "days": 86400, "day": 86400,
    "weeks": 604800,
}
CLOSE_GUARD_SECONDS = 60

DEFAULT_ENROLLMENT_CONDITIONS = [
    {"rule": "enroll_from_approved_launch_optin",
     "source_ref": "approved_signature_landing_page"},
    {"rule": "email_consent_required", "policy_ref": "approved_communication_policy"},
    {"rule": "exclude_verified_buyers", "check": "verified_purchase",
     "timing": "at_enrollment"},
]
DEFAULT_LIFECYCLE = {
    "stop_rules": [
        {"rule": "stop_on_verified_purchase", "scope": "this_campaign_only"},
        {"rule": "stop_on_unsubscribe", "scope": "this_campaign_only"},
        {"rule": "stop_on_offer_version_superseded", "scope": "this_campaign_only"},
    ],
    "suppression_rules": [
        {"rule": "suppress_promotion_after_verified_purchase",
         "event": "purchase_verified", "applies_to": "all_remaining_email_steps",
         "scope": "this_campaign"},
        {"rule": "recheck_eligibility_immediately_before_send",
         "applies_to": "each_scheduled_email_step",
         "checks": ["verified_purchase", "unsubscribe", "offer_version_current"]},
    ],
}
DEFAULT_SENDER = {
    "sender_profile_ref": "sender-config:default",
    "reply_to_ref": "sender-config:default",
}


class ReaderError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _fail(code, message):
    raise ReaderError(code, message)


def _require(cond, code, message):
    if not cond:
        _fail(code, message)


# ----------------------------------------------------------------------------- IO
def load_json(path, label):
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        _fail("IO", "%s %s: %s" % (label, p, exc))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail("INVALID-JSON", "%s %s: %s" % (label, p, exc))


def _walk_keys(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            here = "%s.%s" % (path, key) if path else str(key)
            yield here, key
            for item in _walk_keys(value, here):
                yield item
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            for item in _walk_keys(value, "%s[%d]" % (path, idx)):
                yield item


def reject_credentials(doc, label):
    for where, key in _walk_keys(doc):
        if key.lower().endswith("_ref"):
            continue
        if CREDENTIAL_KEY_RE.search(str(key)):
            _fail("CREDENTIAL-IN-PLAN", "%s carries credential-shaped key %r at %s" % (label, key, where))


# --------------------------------------------------------------------- calendar
def _parse_datetime(value, label):
    _require(isinstance(value, str) and value.strip(), "CALENDAR-SHAPE",
             "%s is missing" % label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("CALENDAR-SHAPE", "%s %r is not an ISO-8601 date-time" % (label, value))
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             "CALENDAR-SHAPE", "%s %r has no UTC offset" % (label, value))
    return parsed


def _zone_time(dt, zone, label):
    """Validate one local wall time against its IANA zone.

    Rejects a DST gap (a wall time that never exists) and an offset that does
    not agree with the zone at that wall time. An overlap (fall-back hour) is
    accepted only when the supplied offset names one of the two folds; the
    returned datetime carries the resolved fold.
    """
    local = dt.replace(tzinfo=None)
    fold0 = local.replace(tzinfo=zone, fold=0)
    fold1 = local.replace(tzinfo=zone, fold=1)
    roundtrip = fold0.astimezone(timezone.utc).astimezone(zone)
    if roundtrip.replace(tzinfo=None) != local:
        _fail("CALENDAR-DST",
              "%s %r does not exist in %s (DST gap)" % (label, local.isoformat(), zone.key))
    offsets = {fold0.utcoffset(), fold1.utcoffset()}
    if dt.utcoffset() not in offsets:
        _fail("CALENDAR-OFFSET",
              "%s %r carries offset %s but %s uses %s at that wall time"
              % (label, local.isoformat(), dt.utcoffset(), zone.key,
                 fold0.utcoffset()))
    ambiguous = len(offsets) > 1
    resolved = fold0 if fold0.utcoffset() == dt.utcoffset() else fold1
    return resolved, ambiguous


def read_calendar(calendar):
    _require(isinstance(calendar, dict), "CALENDAR-SHAPE",
             "launch_calendar is missing or is not an object")
    for field in ("launch_at", "doors_open_at", "doors_close_at", "timezone"):
        _require(field in calendar, "CALENDAR-SHAPE",
                 "launch_calendar.%s is missing" % field)
    zone_name = calendar["timezone"]
    _require(isinstance(zone_name, str) and zone_name.strip(), "CALENDAR-ZONE",
             "launch_calendar.timezone is empty")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        _fail("CALENDAR-ZONE", "%r is not a valid IANA timezone" % zone_name)

    compiled = {"timezone": zone_name, "dst_ambiguous": False, "phases": {}}
    values = {}
    for field in ("doors_open_at", "launch_at", "doors_close_at"):
        raw = _parse_datetime(calendar[field], "launch_calendar.%s" % field)
        resolved, ambiguous = _zone_time(raw, zone, "launch_calendar.%s" % field)
        values[field] = resolved
        compiled[field] = resolved.isoformat()
        compiled["dst_ambiguous"] = compiled["dst_ambiguous"] or ambiguous

    _require(values["doors_open_at"] < values["launch_at"] < values["doors_close_at"],
             "CALENDAR-PHASE-ORDER",
             "strict phase order required: doors_open_at < launch_at < doors_close_at")
    compiled["phases"] = {
        "doors_open": values["doors_open_at"].isoformat(),
        "launch": values["launch_at"].isoformat(),
        "doors_close": values["doors_close_at"].isoformat(),
    }

    black_friday = calendar.get("black_friday")
    if black_friday is not None:
        _require(isinstance(black_friday, dict), "CALENDAR-SHAPE",
                 "launch_calendar.black_friday is not an object")
        order = ["teaser_at", "countdown_at", "cyber_monday_at", "last_call_at"]
        previous = values["doors_open_at"]
        for field in order:
            raw = _parse_datetime(black_friday.get(field),
                                  "launch_calendar.black_friday.%s" % field)
            resolved, ambiguous = _zone_time(
                raw, zone, "launch_calendar.black_friday.%s" % field)
            _require(resolved > previous, "CALENDAR-PHASE-ORDER",
                     "black_friday.%s must be strictly after %s"
                     % (field, previous.isoformat()))
            previous = resolved
            compiled.setdefault("black_friday", {})[field] = resolved.isoformat()
            compiled["dst_ambiguous"] = compiled["dst_ambiguous"] or ambiguous
        _require(previous < values["doors_close_at"], "CALENDAR-PHASE-ORDER",
                 "black_friday.last_call_at must be before doors_close_at")

    return compiled, {
        "doors_open_at": values["doors_open_at"],
        "launch_at": values["launch_at"],
        "doors_close_at": values["doors_close_at"],
    }


# ------------------------------------------------------------------- launch plan
def read_launch_plan(plan, source="launch-plan"):
    _require(isinstance(plan, dict), "LAUNCH-PLAN-SHAPE", "%s is not an object" % source)
    _require(plan.get("schema_version") == SCHEMA_VERSION,
             "LAUNCH-PLAN-VERSION", "schema_version must be %r" % SCHEMA_VERSION)
    launch_id = plan.get("launch_id")
    _require(isinstance(launch_id, str) and LAUNCH_ID_RE.match(launch_id),
             "LAUNCH-PLAN-ID", "launch_id is missing or malformed")
    reject_credentials(plan, source)

    calendar_doc, calendar_times = read_calendar(plan.get("launch_calendar"))
    offer = plan.get("offer")
    if offer is not None:
        _require(isinstance(offer, dict), "LAUNCH-PLAN-OFFER", "offer is not an object")
        _require(isinstance(offer.get("name"), str) and offer["name"].strip(),
                 "LAUNCH-PLAN-OFFER", "offer.name is missing")
        price = offer.get("price_usd")
        _require(isinstance(price, (int, float)) and not isinstance(price, bool) and price >= 0,
                 "LAUNCH-PLAN-OFFER", "offer.price_usd must be a non-negative number")
        _require(isinstance(offer.get("currency"), str)
                 and CURRENCY_RE.match(offer["currency"]),
                 "LAUNCH-PLAN-OFFER", "offer.currency must be a 3-letter code")
        _require(isinstance(offer.get("payment_plans"), bool),
                 "LAUNCH-PLAN-OFFER", "offer.payment_plans must be boolean")

    units = {}            # id -> kind
    pages = {}
    email_sequences = {}  # id -> sequence object (insertion order = plan order)
    text_sets = {}
    automations = []

    for kind in ("pages", "email_sequences", "text_sets", "automations"):
        items = plan.get(kind)
        _require(isinstance(items, list), "LAUNCH-PLAN-SHAPE", "%s must be a list" % kind)
        for item in items:
            _require(isinstance(item, dict), "LAUNCH-PLAN-SHAPE", "%s entry is not an object" % kind)
            unit_id = item.get("id")
            _require(isinstance(unit_id, str) and UNIT_ID_RE.match(unit_id),
                     "LAUNCH-PLAN-UNIT-ID", "%s unit id %r is malformed" % (kind, unit_id))
            _require(unit_id not in units, "LAUNCH-PLAN-DUPLICATE-ID",
                     "unit id %r appears twice" % unit_id)
            units[unit_id] = kind
            if kind == "pages":
                url = item.get("url")
                _require(url is None or (isinstance(url, str) and url.strip()),
                         "LAUNCH-PLAN-PAGE-URL",
                         "page %r url must be an approved URL or null" % unit_id)
                pages[unit_id] = item
            elif kind == "email_sequences":
                _require(item.get("draft_only") is True,
                         "LAUNCH-PLAN-NOT-DRAFT", "email sequence %r is not draft_only" % unit_id)
                _require(item.get("kind") in PHASE_RANK or item.get("kind") in {
                    "upsell_followup", "downsell_followup", "abandoned_checkout",
                    "welcome_access"},
                    "LAUNCH-PLAN-SEQUENCE-KIND",
                    "email sequence %r kind %r is not canonical" % (unit_id, item.get("kind")))
                count = item.get("email_count")
                _require(isinstance(count, int) and not isinstance(count, bool) and count >= 1,
                         "LAUNCH-PLAN-SEQUENCE-COUNT",
                         "email sequence %r email_count must be >= 1" % unit_id)
                _require(item.get("provider") == "skill50",
                         "LAUNCH-PLAN-SEQUENCE-PROVIDER",
                         "email sequence %r provider must be 'skill50'" % unit_id)
                email_sequences[unit_id] = item
            elif kind == "text_sets":
                _validate_text_set(item)
                text_sets[unit_id] = item

    # waits_for resolution + acyclicity over every unit.
    edges = {unit_id: [] for unit_id in units}
    for kind in ("pages", "email_sequences", "text_sets", "automations"):
        for item in plan[kind]:
            waits = item.get("waits_for")
            _require(isinstance(waits, list), "LAUNCH-PLAN-WAITS",
                     "%s %r waits_for must be a list" % (kind, item["id"]))
            _require(len(waits) == len(set(waits)), "LAUNCH-PLAN-WAITS",
                     "%s %r waits_for contains duplicates" % (kind, item["id"]))
            for dep in waits:
                _require(dep in units, "LAUNCH-PLAN-UNRESOLVED-WAITS",
                         "%s %r waits for unknown unit %r" % (kind, item["id"], dep))
                edges[item["id"]].append(dep)
    order = _assert_acyclic(edges)

    # Strict phase order between email sequences (a later phase never gates an
    # earlier one).
    for seq_id, sequence in email_sequences.items():
        rank = PHASE_RANK.get(sequence.get("kind"))
        for dep in sequence["waits_for"]:
            dep_rank = PHASE_RANK.get(email_sequences.get(dep, {}).get("kind"))
            if rank is not None and dep_rank is not None:
                _require(dep_rank < rank, "EMAIL-SEQUENCE-PHASE-ORDER",
                         "email sequence %r (%s) waits for %r (%s); phases run "
                         "pre_launch -> main_launch -> doors_closing"
                         % (seq_id, sequence.get("kind"), dep,
                            email_sequences[dep].get("kind")))

    for item in plan["automations"]:
        unit_id = item["id"]
        family = item.get("family")
        _require(family in FAMILIES, "LAUNCH-PLAN-FAMILY",
                 "automation %r family %r is not canonical" % (unit_id, family))
        rail = item.get("build_rail")
        _require(rail in RAILS, "LAUNCH-PLAN-RAIL",
                 "automation %r build_rail %r is not canonical" % (unit_id, rail))
        _require(item.get("draft_only") is True,
                 "LAUNCH-PLAN-NOT-DRAFT", "automation %r is not draft_only" % unit_id)
        template = item.get("template")
        _require(isinstance(template, str) and template.strip(),
                 "LAUNCH-PLAN-TEMPLATE", "automation %r template is missing" % unit_id)
        trigger = item.get("trigger")
        _require(isinstance(trigger, dict) and isinstance(trigger.get("type"), str) and trigger["type"],
                 "LAUNCH-PLAN-TRIGGER", "automation %r trigger.type is missing" % unit_id)
        automations.append(item)

    return {
        "launch_id": launch_id,
        "units": units,
        "pages": pages,
        "email_sequences": email_sequences,
        "text_sets": text_sets,
        "automations": automations,
        "edges": edges,
        "order": order,
        "calendar": calendar_doc,
        "calendar_times": calendar_times,
    }


def _validate_text_set(item):
    unit_id = item["id"]
    messages = item.get("messages")
    _require(isinstance(messages, int) and not isinstance(messages, bool) and messages >= 1,
             "LAUNCH-PLAN-TEXT-SET", "text set %r messages must be >= 1" % unit_id)
    _require(isinstance(item.get("promotional"), bool), "LAUNCH-PLAN-TEXT-SET",
             "text set %r promotional must be boolean" % unit_id)
    _require(item.get("draft_only") is True, "LAUNCH-PLAN-NOT-DRAFT",
             "text set %r is not draft_only" % unit_id)
    _require(item.get("opt_out_keyword") == "STOP", "LAUNCH-PLAN-TEXT-SET",
             "text set %r opt_out_keyword must be STOP" % unit_id)
    _require(item.get("includes_reply_invitation") is True, "LAUNCH-PLAN-TEXT-SET",
             "text set %r must include a reply invitation" % unit_id)
    window = item.get("send_window")
    _require(isinstance(window, dict), "LAUNCH-PLAN-TEXT-SET",
             "text set %r send_window is missing" % unit_id)
    for field in ("start", "end"):
        _require(isinstance(window.get(field), str) and CLOCK_RE.match(window[field]),
                 "LAUNCH-PLAN-TEXT-SET",
                 "text set %r send_window.%s must be HH:MM" % (unit_id, field))
    _require(isinstance(window.get("timezone"), str) and window["timezone"].strip(),
             "LAUNCH-PLAN-TEXT-SET",
             "text set %r send_window.timezone is missing" % unit_id)


def _assert_acyclic(edges):
    indegree = {node: 0 for node in edges}
    forward = {node: [] for node in edges}
    for node, deps in edges.items():
        for dep in deps:
            forward[dep].append(node)
            indegree[node] += 1
    ready = [node for node, deg in indegree.items() if deg == 0]
    order = []
    while ready:
        node = ready.pop()
        order.append(node)
        for nxt in forward[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(edges):
        _fail("LAUNCH-PLAN-CYCLE", "waits_for graph contains a cycle")
    return order


# ------------------------------------------------------------------- build plan
def read_build_plan(doc, source):
    """Validate one Skill 50 P4 build plan and return its workflows verbatim."""
    _require(isinstance(doc, dict), "BUILD-PLAN-SHAPE", "%s is not an object" % source)
    folder = doc.get("folder")
    _require(isinstance(folder, str) and folder.strip(), "BUILD-PLAN-FOLDER",
             "%s has no folder" % source)
    reject_credentials(doc, source)

    meta = doc.get("_meta")
    if isinstance(meta, dict):
        if "draft_only" in meta:
            _require(meta["draft_only"] is True, "BUILD-PLAN-NOT-DRAFT",
                     "%s _meta.draft_only must be true" % source)
        if "deploy_mode" in meta:
            _require(meta["deploy_mode"] == "draft-only", "BUILD-PLAN-NOT-DRAFT",
                     "%s _meta.deploy_mode must be 'draft-only'" % source)

    workflows = []
    for key, workflow in doc.items():
        if key in ("folder", "_meta"):
            continue
        where = "%s#%s" % (source, key)
        _require(isinstance(workflow, dict), "BUILD-PLAN-SHAPE", "%s is not an object" % where)
        _require(isinstance(workflow.get("name"), str) and workflow["name"].strip(),
                 "BUILD-PLAN-WORKFLOW-NAME", "%s has no name" % where)
        status = workflow.get("status", "draft")
        _require(status == "draft", "BUILD-PLAN-NOT-DRAFT",
                 "%s status %r is not 'draft'; nothing but a draft may be read" % (where, status))
        templates = workflow.get("templates")
        _require(isinstance(templates, list) and templates, "BUILD-PLAN-STEPS",
                 "%s has no templates" % where)
        email_count = wait_count = 0
        for idx, step in enumerate(templates):
            _validate_step(step, "%s step %d" % (where, idx))
            if step["type"] == "email":
                email_count += 1
            else:
                wait_count += 1
        workflows.append({
            "key": key,
            "name": workflow["name"],
            "tag": workflow.get("tag"),
            "status": status,
            "folder": folder,
            "email_count": email_count,
            "wait_count": wait_count,
            "steps": templates,
        })
    _require(workflows, "BUILD-PLAN-EMPTY", "%s carries no workflows" % source)
    return workflows


def _validate_step(step, where):
    _require(isinstance(step, dict), "BUILD-PLAN-STEP", "%s is not an object" % where)
    _require(isinstance(step.get("id"), str) and step["id"], "BUILD-PLAN-STEP-ID",
             "%s has no id" % where)
    _require(isinstance(step.get("name"), str) and step["name"], "BUILD-PLAN-STEP-NAME",
             "%s has no name" % where)
    step_type = step.get("type")
    _require(step_type in STEP_TYPES, "BUILD-PLAN-STEP-TYPE",
             "%s type %r is not email|wait" % (where, step_type))
    attrs = step.get("attributes")
    _require(isinstance(attrs, dict), "BUILD-PLAN-STEP-ATTRS", "%s has no attributes" % where)
    if step_type == "email":
        for field in ("subject", "body", "html"):
            _require(isinstance(attrs.get(field), str) and attrs[field].strip(),
                     "BUILD-PLAN-EMAIL-ATTRS", "%s email is missing %s" % (where, field))
        _require(isinstance(attrs.get("fromName"), str), "BUILD-PLAN-EMAIL-ATTRS",
                 "%s email is missing fromName" % where)
    else:
        start = attrs.get("startAfter")
        _require(isinstance(start, dict), "BUILD-PLAN-WAIT-ATTRS",
                 "%s wait is missing startAfter" % where)
        for field in ("type", "when"):
            _require(isinstance(start.get(field), str) and start[field],
                     "BUILD-PLAN-WAIT-ATTRS", "%s wait startAfter.%s is missing" % (where, field))
        _require(isinstance(start.get("value"), int) and start["value"] >= 0,
                 "BUILD-PLAN-WAIT-ATTRS", "%s wait startAfter.value must be a non-negative integer" % where)
        _require(start["type"] in WAIT_SECONDS, "BUILD-PLAN-WAIT-ATTRS",
                 "%s wait startAfter.type %r is unsupported" % (where, start["type"]))


# ---------------------------------------------------------------- sequence bind
def _meta_sequence_id(doc):
    meta = doc.get("_meta")
    if not isinstance(meta, dict):
        return None
    if meta.get("sequence_id"):
        return meta["sequence_id"]
    src = meta.get("source_ids")
    if isinstance(src, dict) and src.get("sequence_id"):
        return src["sequence_id"]
    return None


def bind_build_plans(paths, email_sequence_ids, explicit_map):
    """Bind each build plan to exactly one launch email_sequence id."""
    seq_ids = list(email_sequence_ids)
    bound = {}      # seq id -> (path, doc, workflows)
    explicit = {str(Path(p).resolve()): seq for seq, p in explicit_map.items()}
    problems = []

    for path in paths:
        doc = load_json(path, "build-plan")
        workflows = read_build_plan(doc, str(path))
        resolved = Path(path).resolve()

        seq = explicit.get(str(resolved))
        if seq is not None:
            _require(seq in email_sequence_ids, "SEQUENCE-MAP-UNKNOWN",
                     "--sequence-map names unknown email_sequence %r" % seq)

        if seq is None:
            candidates = []
            meta_seq = _meta_sequence_id(doc)
            if meta_seq in email_sequence_ids:
                candidates.append(meta_seq)
            stem = resolved.stem.lower()
            if stem in email_sequence_ids:
                candidates.append(stem)
            else:
                hits = [sid for sid in seq_ids if sid in stem]
                if len(hits) == 1:
                    candidates.append(hits[0])
            if not candidates:
                hits = set()
                for workflow in workflows:
                    blob = " ".join(str(workflow.get(f) or "") for f in ("key", "name", "tag")).lower()
                    hits.update(sid for sid in seq_ids if sid in blob)
                if len(hits) == 1:
                    candidates.append(hits.pop())
            unique = sorted(set(candidates))
            if len(unique) > 1:
                _fail("SEQUENCE-BIND-AMBIGUOUS",
                      "%s could belong to %s; pass --sequence-map" % (path, unique))
            if not unique:
                problems.append({"build_plan": str(path),
                                 "reason": "no launch email_sequence matches",
                                 "workflows": [w["key"] for w in workflows]})
                continue
            seq = unique[0]

        if seq in bound:
            _fail("SEQUENCE-BIND-DUPLICATE",
                  "two build plans claim email_sequence %r: %s and %s" % (seq, bound[seq][0], path))
        bound[seq] = (str(path), doc, workflows)

    return bound, problems


# ------------------------------------------------------------------- scheduling
def _wait_seconds(attrs, where):
    start = attrs.get("startAfter") or {}
    unit = start.get("type")
    value = start.get("value")
    if unit not in WAIT_SECONDS or not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail("BUILD-PLAN-WAIT-ATTRS", "%s wait startAfter is unsupported" % where)
    return value * WAIT_SECONDS[unit]


def _workflow_offsets(workflow):
    """[(index, step, seconds_before_this_step)] for each email step."""
    elapsed = 0
    offsets = []
    for idx, step in enumerate(workflow["steps"]):
        if step["type"] == "email":
            offsets.append((idx, step, elapsed))
        else:
            elapsed += _wait_seconds(step.get("attributes") or {},
                                     "%s step %d" % (workflow["key"], idx))
    return offsets, elapsed


def _sequence_anchor(kind, times, duration):
    """Anchor datetime for an absolute phase, or None for a relative phase.

    Promotional phases are pinned so their LAST email lands just before the
    phase boundary (doors open for pre-launch, doors close for doors-closing);
    main launch starts at the launch instant. A 60 s guard keeps even the last
    send strictly before the boundary.
    """
    guard = timedelta(seconds=CLOSE_GUARD_SECONDS)
    if kind == "pre_launch":
        return "doors_open_at", times["doors_open_at"] - guard - timedelta(seconds=duration)
    if kind == "main_launch":
        return "launch_at", times["launch_at"]
    if kind == "doors_closing":
        return "doors_close_at", times["doors_close_at"] - guard - timedelta(seconds=duration)
    return None, None


def compile_schedule(sequence_kind, workflow, times, now):
    """Compile one bound workflow into absolute/relative provider schedule nodes.

    Policy:
      * promotional sends at/after doors_close_at are SUPPRESSED (close-time)
      * promotional sends at/before `now` are SUPPRESSED (past-time)
      * transactional access (welcome_access) is never suppressed
      * relative phases carry a runtime close-time guard instead of a wall time
    """
    promotional = sequence_kind in PROMOTIONAL_KINDS
    offsets, duration = _workflow_offsets(workflow)
    anchor_key, anchor_dt = _sequence_anchor(sequence_kind, times, duration)
    close_at = times["doors_close_at"]
    nodes, suppressed = [], []
    for idx, step, elapsed in offsets:
        node = {
            "workflow_key": workflow["key"],
            "step_id": step["id"],
            "phase": sequence_kind,
            "kind": "absolute" if anchor_dt is not None else "relative",
            "anchor": anchor_key,
            "offset_seconds": elapsed,
            "at": None,
            "status": "scheduled",
            "reason": None,
        }
        if promotional and now >= close_at:
            node["status"] = "suppressed"
            node["reason"] = "CLOSE-TIME-SUPPRESSED"
        elif anchor_dt is not None:
            at = anchor_dt + timedelta(seconds=elapsed)
            node["at"] = at.isoformat()
            if promotional and at >= close_at:
                node["status"] = "suppressed"
                node["reason"] = "CLOSE-TIME-SUPPRESSED"
            elif promotional and at <= now:
                node["status"] = "suppressed"
                node["reason"] = "PAST-TIME-SUPPRESSED"
        else:
            node["suppress_after"] = close_at.isoformat()
        if node["status"] == "suppressed":
            suppressed.append({"step_id": step["id"], "reason": node["reason"],
                               "workflow_key": workflow["key"]})
        nodes.append(node)
    return {
        "workflow_key": workflow["key"],
        "timezone": times["timezone"] if isinstance(times, dict) and "timezone" in times
        else None,
        "anchor": anchor_key,
        "kind": "absolute" if anchor_dt is not None else "relative",
        "duration_seconds": duration,
        "close_at": close_at.isoformat(),
        "promotional": promotional,
        "nodes": nodes,
    }, suppressed


def compile_calendar_nodes(calendar_times, now):
    nodes = []
    for phase, key in (("doors_open", "doors_open_at"),
                       ("launch", "launch_at"),
                       ("doors_close", "doors_close_at")):
        at = calendar_times[key]
        nodes.append({
            "phase": phase,
            "kind": "absolute",
            "at": at.isoformat(),
            "status": "past" if at <= now else "scheduled",
        })
    return nodes


# ----------------------------------------------------------------- binding meta
def _plan_meta(doc):
    meta = doc.get("_meta")
    return meta if isinstance(meta, dict) else {}


def _merge_meta(bound_for_sequences):
    eligibility, lifecycle, sender, content_hashes = [], None, None, {}
    for _seq_id, _path, doc, workflows in bound_for_sequences:
        meta = _plan_meta(doc)
        conditions = meta.get("enrollment_conditions")
        if isinstance(conditions, list):
            for condition in conditions:
                if condition not in eligibility:
                    eligibility.append(condition)
        if isinstance(meta.get("lifecycle"), dict):
            if lifecycle is None:
                lifecycle = meta["lifecycle"]
            else:
                for key in ("stop_rules", "suppression_rules"):
                    for rule in meta["lifecycle"].get(key, []) or []:
                        if rule not in lifecycle.setdefault(key, []):
                            lifecycle[key].append(rule)
        if isinstance(meta.get("sender_config_refs"), dict):
            sender = dict(meta["sender_config_refs"])
        hashes = meta.get("content_hashes")
        if isinstance(hashes, dict):
            content_hashes.update({w["key"]: hashes for w in workflows})
    return {
        "eligibility": eligibility or list(DEFAULT_ENROLLMENT_CONDITIONS),
        "lifecycle": lifecycle or dict(DEFAULT_LIFECYCLE),
        "sender": sender or dict(DEFAULT_SENDER),
        "content_hashes": content_hashes,
    }


def _compile_guard_issues(lifecycle, kind):
    """Missing suppression guards block activation. Absent lifecycle = contract defaults."""
    if kind not in PROMOTIONAL_KINDS:
        return []
    issues = []
    stops = {rule.get("rule") for rule in lifecycle.get("stop_rules", []) or []}
    suppressions = {rule.get("rule") for rule in lifecycle.get("suppression_rules", []) or []}
    if "stop_on_unsubscribe" not in stops:
        issues.append("stop_on_unsubscribe")
    if "stop_on_verified_purchase" not in stops:
        issues.append("stop_on_verified_purchase")
    if "suppress_promotion_after_verified_purchase" not in suppressions:
        issues.append("suppress_promotion_after_verified_purchase")
    if "recheck_eligibility_immediately_before_send" not in suppressions:
        issues.append("recheck_eligibility_immediately_before_send")
    return issues


# ---------------------------------------------------------------------- hashing
def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------- builder
def _dependency_blocker(dep, plan, bound, build_states):
    kind = plan["units"].get(dep)
    if kind == "pages":
        if not plan["pages"][dep].get("url"):
            return "page_url:%s" % dep
    elif kind == "email_sequences":
        if dep not in bound:
            return dep
        expected = plan["email_sequences"][dep].get("email_count")
        got = sum(w["email_count"] for w in bound[dep][2])
        if isinstance(expected, int) and expected != got:
            return "email_count:%s" % dep
    elif kind == "text_sets":
        set_doc = plan["text_sets"][dep]
        if set_doc.get("messages", 0) < 1:
            return "text_set:%s" % dep
    elif kind == "automations":
        if build_states.get(dep) == "blocked":
            return "upstream:%s" % dep
    return None


def build_document(plan_path, plan, bound, unbound, warnings, now=None):
    now = now or datetime.now(timezone.utc)
    email_sequences = plan["email_sequences"]
    times = dict(plan["calendar_times"])
    times["timezone"] = plan["calendar"]["timezone"]
    builds = []
    build_states = {}
    journal = {}

    for automation in plan["order"]:
        if plan["units"].get(automation) != "automations":
            continue
        automation = next(item for item in plan["automations"] if item["id"] == automation)
        refs = [dep for dep in automation["waits_for"] if dep in email_sequences]
        workflows = []
        missing = []
        blocked_by = []
        for seq_id in refs:
            if seq_id not in bound:
                missing.append(seq_id)
                continue
            _path, _doc, wfs = bound[seq_id]
            workflows.extend(wfs)

        # Every declared dependency must be satisfied, not merely resolvable.
        for dep in automation["waits_for"]:
            reason = _dependency_blocker(dep, plan, bound, build_states)
            if reason and reason not in blocked_by:
                blocked_by.append(reason)

        # Email count is a hard output contract: a mismatch blocks the build.
        for seq_id in refs:
            if seq_id not in bound:
                continue
            expected = email_sequences[seq_id].get("email_count")
            got = sum(w["email_count"] for w in bound[seq_id][2])
            if isinstance(expected, int) and expected != got:
                warnings.append({
                    "code": "EMAIL-COUNT-MISMATCH",
                    "automation": automation["id"],
                    "email_sequence": seq_id,
                    "expected": expected,
                    "build_plan_emails": got,
                    "blocking": True,
                })

        bound_meta = [(seq_id, str(bound[seq_id][0]), bound[seq_id][1], bound[seq_id][2])
                      for seq_id in refs if seq_id in bound]
        merged = _merge_meta(bound_meta)

        schedule_nodes, schedule_suppressed, sequence_schedules = [], [], {}
        for seq_id in refs:
            if seq_id not in bound:
                continue
            kind = email_sequences[seq_id].get("kind")
            guard_issues = _compile_guard_issues(merged["lifecycle"], kind)
            if guard_issues:
                blocked_by.append("guards:%s:%s" % (seq_id, ",".join(guard_issues)))
            for workflow in bound[seq_id][2]:
                schedule, suppressed = compile_schedule(kind, workflow, times, now)
                sequence_schedules[seq_id] = schedule
                schedule_nodes.extend(schedule["nodes"])
                for item in suppressed:
                    item["email_sequence"] = seq_id
                schedule_suppressed.extend(suppressed)
                if suppressed:
                    reason = "schedule_suppressed:%s" % seq_id
                    if reason not in blocked_by:
                        blocked_by.append(reason)

        unit_key = "%s/%s" % (plan["launch_id"], automation["id"])
        expected_hash = _sha256({
            "unit_key": unit_key,
            "workflows": workflows,
            "schedule": schedule_nodes,
        })
        journal[unit_key] = expected_hash

        state = "blocked" if (missing or blocked_by) else "ready"
        build_states[automation["id"]] = state
        builds.append({
            "id": automation["id"],
            "unit_key": unit_key,
            "family": automation["family"],
            "phase": automation["family"],
            "template": automation.get("template"),
            "build_rail": automation["build_rail"],
            "draft_only": True,
            "trigger": automation["trigger"],
            "waits_for": list(automation["waits_for"]),
            "depends_on": list(automation["waits_for"]),
            "email_sequences": refs,
            "workflows": workflows,
            "eligibility": merged["eligibility"],
            "lifecycle": merged["lifecycle"],
            "sender": merged["sender"],
            "content_hashes": merged["content_hashes"],
            "expected_graph_hash": expected_hash,
            "required_outputs": ["workflows", "schedule", "guards"],
            "schedule": {
                "timezone": plan["calendar"]["timezone"],
                "calendar_nodes": compile_calendar_nodes(times, now),
                "sequences": sequence_schedules,
                "nodes": schedule_nodes,
                "suppressed": schedule_suppressed,
            },
            "suppressed": schedule_suppressed,
            "state": state,
            "blocked_by": blocked_by,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "launch_id": plan["launch_id"],
        "draft_only": True,
        "sources": {"launch_plan": str(plan_path), "build_plans": sorted(
            path for path, _doc, _wfs in bound.values())},
        "calendar": plan["calendar"],
        "schedule_policy": {
            "now": now.isoformat(),
            "past_time": "suppress_promotional",
            "close_time": "suppress_promotional",
            "close_guard_seconds": CLOSE_GUARD_SECONDS,
            "timezone": plan["calendar"]["timezone"],
        },
        "journal": {"stable_unit_keys": journal},
        "builds": builds,
        "unused_build_plan_workflows": unbound,
        "warnings": warnings,
    }


# -------------------------------------------------------------------------- CLI
def read_sequence_map(path):
    if not path:
        return {}
    doc = load_json(path, "sequence-map")
    _require(isinstance(doc, dict), "SEQUENCE-MAP-SHAPE", "sequence map is not an object")
    for seq, build_path in doc.items():
        _require(isinstance(build_path, str) and build_path, "SEQUENCE-MAP-SHAPE",
                 "sequence map entry %r is not a path" % seq)
    return doc


def _parse_now(value):
    if not value:
        return datetime.now(timezone.utc)
    parsed = _parse_datetime(value, "--now")
    return parsed


def run(args):
    plan = load_json(args.launch_plan, "launch-plan")
    parsed = read_launch_plan(plan, args.launch_plan)
    explicit = read_sequence_map(args.sequence_map)
    bound, unbound = bind_build_plans(
        args.build_plan or [], parsed["email_sequences"], explicit)
    return build_document(args.launch_plan, parsed, bound, unbound, [],
                          now=_parse_now(getattr(args, "now", None)))


def _selftest():
    plan = {
        "schema_version": "1.0.0",
        "launch_id": "selftest-launch",
        "launch_calendar": {
            "launch_at": "2026-11-03T12:00:00-05:00",
            "doors_open_at": "2026-11-03T09:00:00-05:00",
            "doors_close_at": "2026-11-10T23:59:00-05:00",
            "timezone": "America/New_York",
        },
        "offer": {"name": "Selftest", "price_usd": 1, "currency": "USD",
                  "payment_plans": False},
        "pages": [{"id": "page_landing", "kind": "landing",
                   "url": "https://example.com", "waits_for": []}],
        "email_sequences": [
            {"id": "email_pre_launch", "kind": "pre_launch", "provider": "skill50",
             "email_count": 1, "draft_only": True, "waits_for": []}],
        "text_sets": [],
        "automations": [
            {"id": "auto_pre_launch", "family": "pre_launch", "template": "new",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "tag_added"}, "waits_for": ["email_pre_launch"]}],
    }
    parsed = read_launch_plan(plan)
    doc = {"folder": "F", "wf": {"name": "wf", "status": "draft", "templates": [
        {"id": "e1", "type": "email", "name": "Email 1", "attributes": {
            "subject": "s", "body": "b", "html": "<p>b</p>", "fromName": "n"}},
        {"id": "w1", "type": "wait", "name": "Wait 1 Days", "attributes": {
            "type": "time", "startAfter": {"type": "days", "value": 1, "when": "after"}}}],
    }}
    workflows = read_build_plan(doc, "selftest")
    bound = {"email_pre_launch": ("selftest", doc, workflows)}
    now = datetime.fromisoformat("2026-11-01T00:00:00-05:00")
    out = build_document("selftest", parsed, bound, [], [], now=now)
    build = out["builds"][0]
    assert build["blocked_by"] == [], build["blocked_by"]
    assert build["state"] == "ready"
    assert build["workflows"][0]["email_count"] == 1
    assert build["draft_only"] is True
    assert build["unit_key"] == "selftest-launch/auto_pre_launch"
    assert out["journal"]["stable_unit_keys"][build["unit_key"]] == build["expected_graph_hash"]
    assert build["lifecycle"]["stop_rules"]

    bad = json.loads(json.dumps(doc))
    bad["wf"]["status"] = "published"
    try:
        read_build_plan(bad, "selftest")
        raise AssertionError("published workflow was accepted")
    except ReaderError as exc:
        assert exc.code == "BUILD-PLAN-NOT-DRAFT", exc.code

    bad = json.loads(json.dumps(doc))
    bad["wf"]["templates"][0]["attributes"]["api_key"] = "x"
    try:
        read_build_plan(bad, "selftest")
        raise AssertionError("credential key was accepted")
    except ReaderError as exc:
        assert exc.code == "CREDENTIAL-IN-PLAN", exc.code

    cyclic = json.loads(json.dumps(plan))
    cyclic["automations"][0]["waits_for"] = ["auto_pre_launch"]
    try:
        read_launch_plan(cyclic)
        raise AssertionError("cycle was accepted")
    except ReaderError as exc:
        assert exc.code == "LAUNCH-PLAN-CYCLE", exc.code

    broken = json.loads(json.dumps(plan))
    broken["launch_calendar"]["timezone"] = "Mars/Olympus"
    try:
        read_launch_plan(broken)
        raise AssertionError("bad IANA zone was accepted")
    except ReaderError as exc:
        assert exc.code == "CALENDAR-ZONE", exc.code

    dst_gap = json.loads(json.dumps(plan))
    dst_gap["launch_calendar"].update({
        "launch_at": "2026-03-08T02:30:00-05:00",
        "doors_open_at": "2026-03-08T01:00:00-05:00",
    })
    try:
        read_launch_plan(dst_gap)
        raise AssertionError("DST gap was accepted")
    except ReaderError as exc:
        assert exc.code == "CALENDAR-DST", exc.code

    bad_offset = json.loads(json.dumps(plan))
    bad_offset["launch_calendar"]["launch_at"] = "2026-11-03T12:00:00-08:00"
    try:
        read_launch_plan(bad_offset)
        raise AssertionError("zone/offset disagreement was accepted")
    except ReaderError as exc:
        assert exc.code == "CALENDAR-OFFSET", exc.code

    out_of_order = json.loads(json.dumps(plan))
    out_of_order["launch_calendar"]["launch_at"] = "2026-11-03T09:00:00-05:00"
    try:
        read_launch_plan(out_of_order)
        raise AssertionError("non-strict phase order was accepted")
    except ReaderError as exc:
        assert exc.code == "CALENDAR-PHASE-ORDER", exc.code

    print("selftest ok")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read Skill 50 build plans into launch automation builds.")
    parser.add_argument("--launch-plan")
    parser.add_argument("--build-plan", action="append", default=[])
    parser.add_argument("--sequence-map")
    parser.add_argument("--out")
    parser.add_argument("--now", default=None,
                        help="Evaluation instant for past-time policy (ISO-8601, default: now)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return EXIT_OK
    if not args.launch_plan or not args.out:
        parser.error("--launch-plan and --out are required")

    try:
        document = run(args)
        Path(args.out).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except ReaderError as exc:
        print("plan-reader: %s" % exc, file=sys.stderr)
        return EXIT_IO if exc.code == "IO" else EXIT_INVALID
    except OSError as exc:
        print("plan-reader: IO: %s" % exc, file=sys.stderr)
        return EXIT_IO
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
