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
#   * call the shared launch-plan validator FIRST (shared-utils/
#     signature_launch_contract/validate_launch_plan.py) and refuse with its exact
#     error text; this reader keeps only Skill 44 checks (credentials, build-plan
#     binding, IANA zone / offset / DST resolution). Calendar ORDER is the shared
#     law's; the reader keeps no private order of its own.
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
#                  [--acknowledge-dropped-sends <dropped_sends_hash>]
#                  [--text-copy-dir working/text]
#                  --out automation-builds.json
#   plan_reader.py --selftest
#
#   map.json: {"email_pre_launch": "path/to/build-plan.json", ...}
#   Without a map, each build plan is bound to a launch email_sequence by
#   _meta.sequence_id / _meta.source_ids.sequence_id, then by file stem, then by
#   the single sequence id its workflow keys/names/tags name. Ambiguity fails.
#
# LATE START: promotional sends already in the past are DROPPED (state stays
# ready for the still-future steps) and listed under owner_acknowledgement; the
# owner acknowledges that exact list by passing its dropped_sends_hash back.
#
# BLACK FRIDAY: launch_calendar.black_friday carries the teaser / countdown /
# cyber_monday / last_call instants. pre_launch starts at the teaser, and the
# four instants become calendar nodes. The shared launch-plan schema has no
# Black Friday email sequence kinds, so this reader keeps none; Black Friday
# ordering is the shared calendar law's (and Skill 83's).
#
# EXIT CODES: 0 ok / 2 usage-or-structural-invalid / 3 IO /
#             4 BLOCKED (output written, but a build is blocked or has no workflow)
# =============================================================================
"""Skill 50 build plans -> launch automation builds (launch-c)."""

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_IO = 3
EXIT_BLOCKED = 4

SCHEMA_VERSION = "1.0.0"

STEP_TYPES = {"email", "wait"}
# Credential-shaped keys must never travel in a plan; sender configuration is a
# named reference and binds under a *_ref key.
CREDENTIAL_KEY_RE = re.compile(
    r"(password|passwd|secret|api[-_]?key|credential|private[-_]?key|(^|_)token(_|$))",
    re.IGNORECASE,
)

# launch_calendar.black_friday instants, as the shared calendar law names them.
# They are calendar nodes only: no email sequence kind is a Black Friday kind.
BLACK_FRIDAY_FIELDS = ("teaser_at", "countdown_at", "cyber_monday_at", "last_call_at")
# Phase ranks: a phase may only wait on a strictly earlier phase.
PHASE_RANK = {"pre_launch": 0, "main_launch": 2, "doors_closing": 5}
PROMOTIONAL_KINDS = {
    "pre_launch", "main_launch", "doors_closing",
    "upsell_followup", "downsell_followup", "abandoned_checkout",
}
# Access/entitlement mail is transactional: a purchase never cancels it.
TRANSACTIONAL_KINDS = {"welcome_access"}
# An upsell/downsell follow-up goes only to a verified buyer of the main offer, so
# its stop must name the offer it follows (purchase_of); the launch-wide buyer tag
# is already on that buyer.  Must equal launch_step_compiler.FOLLOW_UP_FAMILY's
# sequence kinds (a test asserts it).
FOLLOW_UP_KINDS = {"upsell_followup", "downsell_followup"}
FOLLOWED_OFFER_KEY = "followed_offer_id"

WAIT_SECONDS = {
    "minutes": 60, "minute": 60,
    "hour": 3600, "hours": 3600,
    "days": 86400, "day": 86400,
    "weeks": 604800,
}
CLOSE_GUARD_SECONDS = 60

# The DEFAULT_* values below are the contract's reference shapes. They are used by
# --selftest and by the parity test against the installable compiler; the reader
# NEVER substitutes them for a build plan that carries none (a guard satisfied by
# the checker's own defaults is not a guard): see _merge_meta / build_document.
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

# The post-sale short handler's variant identity.  The buildable template
# (launch-b/post-sale-purchase.json, node n2) carries the literal placeholder
# "variant tag (main / upsell-N / downsell-N)"; the launch compiler binds that
# placeholder from build["variant_tag"] (workflow_builder.compile_launch_builds
# -> launch_step_compiler._resolve_tags).  So the launch plan declares the tag
# ONCE, on the automation unit, and this reader carries it through under the
# same key: one identity, never a second variant system.
VARIANT_TAG_KEY = "variant_tag"
# Must accept exactly what launch_step_compiler._resolve_tags accepts, so a
# plan-supplied tag can never pass this reader and then fail to bind.
VARIANT_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_./-]*$")

# The automation's own settings (launch-plan.schema.json definitions.automation
# .settings) and the purchase identity its post-sale handler deduplicates on.
# The reader carries both VERBATIM: it never turns an absent setting into a
# default, because a guess here would be applied to a real workflow.
SETTINGS_KEY = "settings"
REENTRY_VALUES = ("allow", "block", "unknown", None)
ENROLLMENT_VALUES = ("single", "successive", "unknown", None)
PURCHASE_IDENTITY_KEY = "purchase_identity"

# The automation's own provider settings, declared on the launch plan unit under
# ``settings`` (shared launch contract).  The builder APPLIES Allow Reentry to the
# workflow settings object and reads it back after the save
# (workflow_builder.compile_settings -> CampaignBuilder); like the variant tag,
# the reader is the only producer of an automation build document, so it must
# carry the declared value or the setting can never reach the provider.
#
# ``unknown`` and an absent value both stay UNKNOWN (None): a reentry setting the
# plan did not decide is never normalised to False, and an unproven setting is
# never reported as applied.
REENTRY_SETTINGS = {"allow": True, "block": False, "unknown": None}
# ``successive`` keeps a SECOND purchase's fulfilment (deduplicated by the native
# event/transaction/line identity); ``single`` enrols once; ``unknown`` is not a
# claim.  Absent stays None for the same reason as reentry.
ENROLLMENT_SETTINGS = {"single": "single", "successive": "successive",
                       "unknown": None}
ALLOW_REENTRY_KEY = "allow_reentry"
ENROLLMENT_KEY = "enrollment"


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


@lru_cache(maxsize=1)
def _launch_contract():
    """(validator module, schema path) of the shared launch-plan contract, from the
    repo checkout or the installed skills tree, imported by path (same lookup as
    the Skill 50 launch adapter) so a same-named module can never shadow it."""
    here = Path(__file__).resolve()
    candidates = [p / "shared-utils" / "signature_launch_contract" for p in here.parents]
    candidates += [
        Path.home() / ".openclaw" / "skills" / "shared-utils" / "signature_launch_contract",
        Path("/data/.openclaw/skills/shared-utils/signature_launch_contract"),
    ]
    for directory in candidates:
        validator = directory / "validate_launch_plan.py"
        schema = directory / "launch-plan.schema.json"
        if validator.is_file() and schema.is_file():
            spec = importlib.util.spec_from_file_location("_launch_contract_validator", validator)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module, schema
    _fail("LAUNCH-PLAN-CONTRACT",
          "shared launch contract (shared-utils/signature_launch_contract) not found; "
          "the plan cannot be proven against the contract it claims to follow")


@lru_cache(maxsize=1)
def _calendar_law():
    """The ONE launch calendar law (shared-utils/signature_launch_contract/calendar_law.py),
    imported by path from the same directory as the shared validator."""
    spec = importlib.util.spec_from_file_location(
        "_launch_calendar_law", _launch_contract()[1].parent / "calendar_law.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_calendar_law(calendar, black_friday_required):
    """Phase ORDER is the shared law's, never a private rule of this reader."""
    violations = _calendar_law().violations(calendar, black_friday_required=black_friday_required)
    _require(not violations, "CALENDAR-PHASE-ORDER", "; ".join(violations))


@lru_cache(maxsize=1)
def _buildable_keys():
    """Template keys of this skill's OWN sibling manifest (_matcher/buildable-templates.json).
    A missing or unreadable manifest yields no keys, so every template is refused (fail closed)."""
    path = Path(__file__).resolve().parents[1] / "_matcher" / "buildable-templates.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return frozenset(t["key"] for t in data.get("templates", [])
                         if isinstance(t, dict) and t.get("key"))
    except (OSError, ValueError, AttributeError):
        return frozenset()


def _shared_errors(plan):
    """Error strings from the shared validator (empty list = the contract accepts it)."""
    module, schema_path = _launch_contract()
    try:
        return list(module.validate_plan(plan, module.load_json(schema_path)))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _fail("LAUNCH-PLAN-CONTRACT", "shared validator could not read the plan: %s" % exc)


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


def read_calendar(calendar, black_friday_required=False):
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

    compiled["phases"] = {
        "doors_open": values["doors_open_at"].isoformat(),
        "launch": values["launch_at"].isoformat(),
        "doors_close": values["doors_close_at"].isoformat(),
    }

    black_friday = calendar.get("black_friday")
    if black_friday is not None:
        _require(isinstance(black_friday, dict), "CALENDAR-SHAPE",
                 "launch_calendar.black_friday is not an object")
        for field in BLACK_FRIDAY_FIELDS:
            label = "launch_calendar.black_friday.%s" % field
            resolved, ambiguous = _zone_time(
                _parse_datetime(black_friday.get(field), label), zone, label)
            values[field] = resolved
            compiled.setdefault("black_friday", {})[field] = resolved.isoformat()
            compiled["dst_ambiguous"] = compiled["dst_ambiguous"] or ambiguous

    # Zone/offset/DST resolution lives here; phase ORDER is delegated to the shared law.
    _assert_calendar_law(calendar, black_friday_required)
    return compiled, values


# ------------------------------------------------------------------- launch plan
def automation_settings(item):
    """``(allow_reentry, enrollment)`` from one automation unit's ``settings``.

    Only the two values the builder can actually act on travel onward:
    ``allow_reentry`` as a bool (or None when the plan did not decide) and
    ``enrollment`` as "single" / "successive" (or None).  A value outside the
    shared contract's own vocabulary is refused here rather than dropped, so a
    typo can never silently become "not declared".
    """
    settings = item.get("settings")
    if settings is None:
        return None, None
    _require(isinstance(settings, dict), "LAUNCH-PLAN-SETTINGS",
             "automation %r settings is not an object" % item.get("id"))
    reentry = settings.get("reentry")
    if reentry is not None and reentry not in REENTRY_SETTINGS:
        _fail("LAUNCH-PLAN-SETTINGS",
              "automation %r settings.reentry %r is not one of %s"
              % (item.get("id"), reentry, sorted(REENTRY_SETTINGS)))
    enrollment = settings.get("enrollment")
    if enrollment is not None and enrollment not in ENROLLMENT_SETTINGS:
        _fail("LAUNCH-PLAN-SETTINGS",
              "automation %r settings.enrollment %r is not one of %s"
              % (item.get("id"), enrollment, sorted(ENROLLMENT_SETTINGS)))
    return (REENTRY_SETTINGS.get(reentry) if reentry is not None else None,
            ENROLLMENT_SETTINGS.get(enrollment) if enrollment is not None else None)


def read_launch_plan(plan, source="launch-plan"):
    _require(isinstance(plan, dict), "LAUNCH-PLAN-SHAPE", "%s is not an object" % source)
    # The shared contract validator goes first and is refused with its own text.
    # Everything it proves (shape, ids, waits_for, drafts, calendar order) is not
    # re-checked here; only Skill 44 concerns follow.
    errors = _shared_errors(plan)
    _require(not errors, "LAUNCH-PLAN-CONTRACT", "; ".join(errors))
    reject_credentials(plan, source)

    # A launch_calendar.black_friday block, when present, is ordered by the shared
    # calendar law (read_calendar); the shared validator above already refused any
    # email sequence kind the contract does not list.
    calendar_doc, calendar_times = read_calendar(plan["launch_calendar"])
    units = {}            # id -> kind
    pages, email_sequences, text_sets, automations = {}, {}, {}, []
    targets = {"pages": pages, "email_sequences": email_sequences, "text_sets": text_sets}
    edges = {}
    # commerce_units (optional contract array) only take part in waits_for ordering.
    for kind in ("pages", "email_sequences", "text_sets", "automations", "commerce_units"):
        for item in plan.get(kind, []):
            units[item["id"]] = kind
            edges[item["id"]] = list(item["waits_for"])
            if kind == "automations":
                template = item.get("template")
                new = item.get("new_template")
                approved_new = (template == "new" and isinstance(new, dict)
                                and bool(str(new.get("owner_approved_reason") or "").strip())
                                and bool(new.get("compile_spec")))
                _require(template in _buildable_keys() or approved_new,
                         "LAUNCH-PLAN-TEMPLATE-UNBUILDABLE",
                         "automation %r template %r is not in buildable-templates.json "
                         "(a 'new' template needs new_template.owner_approved_reason and "
                         "new_template.compile_spec)" % (item["id"], template))
                # A declared variant tag must really be a contact tag: it is
                # written to the provider, and a value that does not bind leaves
                # the post-sale handler on its sequence instead of its graph.
                variant = item.get(VARIANT_TAG_KEY)
                if variant is not None:
                    _require(isinstance(variant, str) and bool(VARIANT_TAG_RE.match(variant)),
                             "LAUNCH-PLAN-VARIANT-TAG",
                             "automation %r %s %r is not a contact tag; it must "
                             "match %s" % (item["id"], VARIANT_TAG_KEY, variant,
                                           VARIANT_TAG_RE.pattern))
                # A declared setting must be one of the contract's own values; an
                # absent one stays absent (the compiler records it insufficient).
                settings = item.get(SETTINGS_KEY)
                if settings is not None:
                    _require(isinstance(settings, dict), "LAUNCH-PLAN-SETTINGS",
                             "automation %r %s is not an object" % (item["id"], SETTINGS_KEY))
                    _require(settings.get("reentry") in REENTRY_VALUES,
                             "LAUNCH-PLAN-REENTRY",
                             "automation %r settings.reentry %r is not allow|block|unknown"
                             % (item["id"], settings.get("reentry")))
                    _require(settings.get("enrollment") in ENROLLMENT_VALUES,
                             "LAUNCH-PLAN-ENROLLMENT",
                             "automation %r settings.enrollment %r is not "
                             "single|successive|unknown"
                             % (item["id"], settings.get("enrollment")))
                identity = item.get(PURCHASE_IDENTITY_KEY)
                if identity is not None:
                    _require(isinstance(identity, dict), "LAUNCH-PLAN-PURCHASE-IDENTITY",
                             "automation %r %s is not an object"
                             % (item["id"], PURCHASE_IDENTITY_KEY))
                # Declared settings are proved here so a typo refuses the plan
                # instead of silently reaching the build as "not declared".
                automation_settings(item)
                followed = item.get(FOLLOWED_OFFER_KEY)
                if followed is not None:
                    _require(isinstance(followed, str) and bool(VARIANT_TAG_RE.match(followed)),
                             "LAUNCH-PLAN-FOLLOWED-OFFER",
                             "automation %r %s %r is not a contact-tag-safe offer id"
                             % (item["id"], FOLLOWED_OFFER_KEY, followed))
                automations.append(item)
            elif kind in targets:
                targets[kind][item["id"]] = item

    order = _assert_acyclic(edges)

    # Strict phase order between email sequences (a later phase never gates an
    # earlier one).
    for seq_id, sequence in email_sequences.items():
        rank = PHASE_RANK.get(sequence["kind"])
        for dep in sequence["waits_for"]:
            dep_rank = PHASE_RANK.get(email_sequences.get(dep, {}).get("kind"))
            if rank is not None and dep_rank is not None:
                _require(dep_rank < rank, "EMAIL-SEQUENCE-PHASE-ORDER",
                         "email sequence %r (%s) waits for %r (%s); phases run "
                         "pre_launch -> main_launch -> doors_closing"
                         % (seq_id, sequence["kind"], dep, email_sequences[dep]["kind"]))

    return {
        "launch_id": plan["launch_id"],
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

    pre_launch starts at the teaser when the calendar carries one. Otherwise
    promotional phases are pinned so their LAST email lands just before the phase
    boundary (doors open for pre-launch, doors close for doors-closing); main
    launch starts at the launch instant. A 60 s guard keeps even the last send
    strictly before the boundary.
    """
    guard = timedelta(seconds=CLOSE_GUARD_SECONDS)
    if kind == "pre_launch" and "teaser_at" in times:
        return "teaser_at", times["teaser_at"]
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
      * promotional sends at/before `now` are SUPPRESSED (past-time): dropped,
        never blocking, and listed for owner acknowledgement (build_document)
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
                               "workflow_key": workflow["key"], "at": node["at"]})
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
    phases = [("doors_open", "doors_open_at"), ("launch", "launch_at"),
              ("doors_close", "doors_close_at")]
    phases += [(field[:-len("_at")], field) for field in BLACK_FRIDAY_FIELDS
               if field in calendar_times]
    nodes = [{
        "phase": phase,
        "kind": "absolute",
        "at": calendar_times[key].isoformat(),
        "status": "past" if calendar_times[key] <= now else "scheduled",
    } for phase, key in phases]
    # Black Friday adds phases around the three base ones: keep time order
    # (stable, so the three base nodes keep their order on a plain launch).
    return sorted(nodes, key=lambda node: datetime.fromisoformat(node["at"]))


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
    # What the build plans carried, and nothing else: an absent value stays empty
    # so build_document can block the build instead of inventing one.
    return {
        "eligibility": eligibility,
        "lifecycle": lifecycle or {},
        "sender": sender or {},
        "content_hashes": content_hashes,
    }


def _absent_meta(merged):
    """Names of the bound build plans' metadata the plan did not carry."""
    return [name for name in ("lifecycle", "eligibility", "sender") if not merged[name]]


def _compile_guard_issues(lifecycle, kind):
    """Missing suppression guards block activation. An absent lifecycle carries no
    rules, so every guard is reported (the build is also blocked by ``lifecycle``)."""
    if kind not in PROMOTIONAL_KINDS:
        return []
    issues = []
    stops = {rule.get("rule") for rule in lifecycle.get("stop_rules", []) or []}
    suppressions = {rule.get("rule") for rule in lifecycle.get("suppression_rules", []) or []}
    if "stop_on_unsubscribe" not in stops:
        issues.append("stop_on_unsubscribe")
    if "stop_on_verified_purchase" not in stops:
        issues.append("stop_on_verified_purchase")
    elif kind in FOLLOW_UP_KINDS and any(
            rule.get("rule") == "stop_on_verified_purchase"
            and not str(rule.get("purchase_of") or "").strip()
            for rule in lifecycle.get("stop_rules", []) or []):
        issues.append("stop_on_verified_purchase.purchase_of")
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


# ------------------------------------------------------------------ text copy
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def read_text_copy(copy_dir, set_id, expected_messages):
    """``(copy, problem)`` for one launch text set.

    ``copy`` is Skill 50's approved ``<copy_dir>/<set_id>.sms.json``
    (``{"set_id", "messages": [{"step_id", "body", "category"}], "profile_sha256"}``);
    ``problem`` is why it cannot be bound, and the build that needs it stays blocked.
    The reader checks shape and count only: Skill 50's text-profile validator owns the
    compliance rules (STOP, reply invitation, length) and ran before the file was written.
    """
    if not copy_dir:
        return None, "no --text-copy-dir given"
    path = Path(copy_dir) / ("%s.sms.json" % set_id)
    if not path.is_file():
        return None, "%s is absent" % path.name
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, "%s is unreadable (%s)" % (path.name, exc)
    messages = doc.get("messages") if isinstance(doc, dict) else None
    if not (isinstance(doc, dict) and doc.get("set_id") == set_id
            and isinstance(messages, list) and messages
            and isinstance(doc.get("profile_sha256"), str)
            and SHA256_RE.match(doc["profile_sha256"])):
        return None, "%s is not a Skill 50 sms set for %s" % (path.name, set_id)
    ids = []
    for message in messages:
        if not (isinstance(message, dict)
                and all(isinstance(message.get(k), str) and message[k].strip()
                        for k in ("step_id", "body", "category"))):
            return None, "%s has a message without step_id, body and category" % path.name
        ids.append(message["step_id"])
    if len(set(ids)) != len(ids):
        return None, "%s repeats a step_id" % path.name
    if isinstance(expected_messages, int) and len(messages) != expected_messages:
        return None, "%s has %d message(s), the launch plan says %d" % (
            path.name, len(messages), expected_messages)
    return doc, None


def _text_bindings(plan, copy_dir):
    """set_id -> ``(copy or None, problem or None)`` for every launch text set."""
    return {set_id: read_text_copy(copy_dir, set_id, doc.get("messages"))
            for set_id, doc in plan["text_sets"].items()}


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


def _settings_value(automation, key):
    """One declared settings value, or None when the plan declares none."""
    settings = automation.get(SETTINGS_KEY)
    if not isinstance(settings, dict):
        return None
    value = settings.get(key)
    return value if isinstance(value, str) else None


def _allow_reentry(automation):
    """True/False for a declared allow/block, None when the plan declares none.

    None is the honest "not declared" this reader hands on: the compiler records
    it insufficient and applies nothing, rather than defaulting to False.
    """
    value = _settings_value(automation, "reentry")
    return True if value == "allow" else False if value == "block" else None


def _enrollment(automation):
    """single/successive as declared, else None (never defaulted)."""
    value = _settings_value(automation, "enrollment")
    return value if value in ("single", "successive") else None


def build_document(plan_path, plan, bound, unbound, warnings, now=None, acknowledged=None,
                   text_copy_dir=None):
    now = now or datetime.now(timezone.utc)
    text_copy = _text_bindings(plan, text_copy_dir)
    email_sequences = plan["email_sequences"]
    times = dict(plan["calendar_times"])
    times["timezone"] = plan["calendar"]["timezone"]
    builds = []
    build_states = {}
    journal = {}
    all_dropped = []

    for automation in plan["order"]:
        if plan["units"].get(automation) != "automations":
            continue
        automation = next(item for item in plan["automations"] if item["id"] == automation)
        refs = [dep for dep in automation["waits_for"] if dep in email_sequences]
        workflows = []
        missing = []
        blocked_by = []
        # The plan's own reentry / enrolment decision, carried so the builder can
        # APPLY it, read it back, and refuse to call an unproven setting applied.
        allow_reentry, enrollment = automation_settings(automation)
        if enrollment == "successive" and allow_reentry is False:
            # Successive delivery means a second purchase must be able to enter
            # this automation. With reentry blocked the provider drops it, so the
            # plan asks for something the workflow forbids: blocked, never built.
            blocked_by.append("settings:successive_without_reentry")
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

        # Texts the client elected for this automation: their approved SMS copy travels
        # with the build (bindings.sms_copy) or the build is blocked, never built with the
        # copy left pending.
        elected = [dep for dep in automation["waits_for"] if plan["units"].get(dep) == "text_sets"]
        sms_copy = {}
        for set_id in elected:
            copy, problem = text_copy[set_id]
            if copy is None:
                blocked_by.append("text_set:%s copy" % set_id)
            else:
                sms_copy.update({m["step_id"]: m["body"] for m in copy["messages"]})

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
        # Lifecycle / eligibility / sender come from the Skill 50 build plan or the
        # build is blocked: the reader never substitutes its own defaults, because
        # the guard check below would then be satisfied by the reader itself.
        if bound_meta:
            blocked_by.extend(name for name in _absent_meta(merged)
                              if name not in blocked_by)

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
                # Past sends are DROPPED, not blocking (late start); only a send
                # that cannot land before doors close blocks the build.
                if any(i["reason"] == "CLOSE-TIME-SUPPRESSED" for i in suppressed):
                    reason = "schedule_suppressed:%s" % seq_id
                    if reason not in blocked_by:
                        blocked_by.append(reason)

        dropped = [item for item in schedule_suppressed
                   if item["reason"] == "PAST-TIME-SUPPRESSED"]
        all_dropped.extend(dict(item, automation=automation["id"]) for item in dropped)
        if schedule_nodes and not any(n["status"] == "scheduled" for n in schedule_nodes):
            blocked_by.append("no_future_sends")

        unit_key = "%s/%s" % (plan["launch_id"], automation["id"])
        expected_hash = _sha256({
            "unit_key": unit_key,
            "workflows": workflows,
            "schedule": schedule_nodes,
        })
        journal[unit_key] = expected_hash

        # Nothing to build is blocked, never "ready" (S44-04 reader half).
        if not workflows and "no_buildable_workflow" not in blocked_by:
            blocked_by.append("no_buildable_workflow")

        state = "blocked" if (missing or blocked_by) else "ready"
        build_states[automation["id"]] = state
        builds.append({
            "id": automation["id"],
            "unit_key": unit_key,
            "family": automation["family"],
            "phase": automation["family"],
            "template": automation.get("template"),
            # The variant tag the short post-sale handler sets, declared once on
            # the launch plan.  Always present (null when the plan declares none)
            # so the key set a compiler reads never depends on the plan's mood.
            VARIANT_TAG_KEY: automation.get(VARIANT_TAG_KEY),
            # The offer an upsell/downsell follow-up follows, declared once on the
            # launch plan's automation unit (null when none).  The compiler gates
            # on purchased-<this id>; without it the follow-up build is blocked.
            FOLLOWED_OFFER_KEY: automation.get(FOLLOWED_OFFER_KEY),
            # Reentry/enrolment exactly as the plan declared them.  allow_reentry
            # is the native boolean CampaignBuilder applies and reads back; None
            # means "not declared" and the compiler records it insufficient.
            SETTINGS_KEY: automation.get(SETTINGS_KEY),
            ALLOW_REENTRY_KEY: _allow_reentry(automation),
            "allow_enrollment": _enrollment(automation),
            # The same enrolment decision under the key the installable compiler
            # reads (launch_step_compiler.purchase_identity), so a ``successive``
            # automation says why an order-level basis will not do.  Always
            # present (null when the plan decided nothing), so the key set a
            # compiler reads never depends on the plan's mood and "not declared"
            # stays distinguishable from "declared false".
            ENROLLMENT_KEY: enrollment,
            # The purchase-event identity the handler deduplicates on, carried
            # verbatim: the compiler decides sufficiency, never this reader.
            PURCHASE_IDENTITY_KEY: automation.get(PURCHASE_IDENTITY_KEY),
            "build_rail": automation["build_rail"],
            "draft_only": True,
            "trigger": automation["trigger"],
            "waits_for": list(automation["waits_for"]),
            "depends_on": list(automation["waits_for"]),
            "email_sequences": refs,
            "workflows": workflows,
            "eligibility": merged["eligibility"],
            "lifecycle": merged["lifecycle"],
            # Provenance the installable compiler reads: the lifecycle came from the
            # Skill 50 build plan (never from this reader), or there is none.
            "lifecycle_source": "build_plan" if merged["lifecycle"] else None,
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
            "dropped_sends": dropped,
            "state": state,
            "blocked_by": blocked_by,
            **({"text_sets": elected, "bindings": {"sms_copy": sms_copy}} if elected else {}),
        })

    text_builds = []
    for set_id, set_doc in plan["text_sets"].items():
        copy, problem = text_copy[set_id]
        electing = [b["id"] for b in builds if set_id in b.get("text_sets", [])]
        text_builds.append({
            "id": set_id,
            "unit_key": "%s/%s" % (plan["launch_id"], set_id),
            "template": "launch-text-set",
            "kind": set_doc.get("kind"),
            "messages": set_doc.get("messages"),
            "state": "ready" if copy is not None else "blocked",
            "blocked_by": [] if copy is not None else ["text_set:%s copy" % set_id],
            "automations": electing,
            "bindings": {"sms_copy": ({m["step_id"]: m["body"] for m in copy["messages"]}
                                      if copy is not None else {})},
            "categories": ({m["step_id"]: m["category"] for m in copy["messages"]}
                           if copy is not None else {}),
            "profile_sha256": copy["profile_sha256"] if copy is not None else None,
        })

    dropped_hash = _sha256(all_dropped)
    _require(acknowledged in (None, dropped_hash), "ACKNOWLEDGEMENT-MISMATCH",
             "--acknowledge-dropped-sends does not match the dropped sends of this "
             "compile (dropped_sends_hash %s)" % dropped_hash)
    return {
        "schema_version": SCHEMA_VERSION,
        "launch_id": plan["launch_id"],
        "draft_only": True,
        "owner_acknowledgement": {
            "required": bool(all_dropped),
            "acknowledged": bool(all_dropped) and acknowledged == dropped_hash,
            "dropped_sends_hash": dropped_hash,
            "dropped_sends": all_dropped,
        },
        "sources": {"launch_plan": str(plan_path), "build_plans": sorted(
            path for path, _doc, _wfs in bound.values())},
        "calendar": plan["calendar"],
        "schedule_policy": {
            "now": now.isoformat(),
            "past_time": "drop_with_owner_acknowledgement",
            "close_time": "suppress_promotional",
            "close_guard_seconds": CLOSE_GUARD_SECONDS,
            "timezone": plan["calendar"]["timezone"],
        },
        "journal": {"stable_unit_keys": journal},
        "builds": builds,
        **({"text_builds": text_builds} if text_builds else {}),
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
    document = build_document(
        args.launch_plan, parsed, bound, unbound, [],
        now=_parse_now(getattr(args, "now", None)),
        acknowledged=getattr(args, "acknowledge_dropped_sends", None),
        text_copy_dir=getattr(args, "text_copy_dir", None))
    validate_output(document)
    return document


def validate_output(document):
    """Refuse to hand on an automation-build document the schema does not accept."""
    module, _ = _launch_contract()
    schema = load_json(Path(__file__).resolve().with_name("automation-build.schema.json"),
                       "automation-build.schema")
    errors = []
    try:
        module._validate_node(document, schema, schema, "", errors)
    except ValueError as exc:
        errors.append(str(exc))
    _require(not errors, "OUTPUT-SCHEMA",
             "automation-build.schema.json rejects the output: %s" % "; ".join(errors[:8]))


def blocked_builds(document):
    """Ids of builds that cannot be built (blocked or carrying no workflow); an
    empty build list is itself blocked."""
    ids = [b["id"] for b in document["builds"] if b["state"] == "blocked" or not b["workflows"]]
    ids += [t["id"] for t in document.get("text_builds", []) if t["state"] == "blocked"]
    return ids or ([] if document["builds"] else ["(no automation builds)"])

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
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "pages": [{"id": "page_landing", "kind": "landing",
                   "url": "https://example.com", "waits_for": []}],
        "email_sequences": [
            {"id": "email_pre_launch", "kind": "pre_launch", "provider": "skill50",
             "email_count": 1, "draft_only": True, "waits_for": []}],
        "text_sets": [],
        "automations": [
            {"id": "auto_pre_launch", "family": "pre_launch",
             "template": "launch-a/launch-a-prelaunch-window",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "tag_added"}, "waits_for": ["email_pre_launch"]}],
    }
    parsed = read_launch_plan(plan)
    doc = {"folder": "F", "_meta": {
        "enrollment_conditions": DEFAULT_ENROLLMENT_CONDITIONS,
        "lifecycle": DEFAULT_LIFECYCLE,
        "sender_config_refs": DEFAULT_SENDER,
    }, "wf": {"name": "wf", "status": "draft", "templates": [
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

    # No lifecycle / eligibility / sender in the build plan: blocked, never defaulted.
    bare = json.loads(json.dumps(doc))
    del bare["_meta"]
    bare_flows = read_build_plan(bare, "selftest")
    out = build_document("selftest", parsed, {"email_pre_launch": ("selftest", bare, bare_flows)},
                         [], [], now=now)
    build = out["builds"][0]
    assert build["state"] == "blocked", build["state"]
    for name in ("lifecycle", "eligibility", "sender"):
        assert name in build["blocked_by"], build["blocked_by"]
    assert build["lifecycle"] == {} and build["sender"] == {} and build["eligibility"] == []

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
        assert exc.code == "LAUNCH-PLAN-CONTRACT" and "cycle" in exc.message, exc.code

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
    out_of_order["launch_calendar"]["doors_close_at"] = "2026-11-03T08:00:00-05:00"
    try:
        read_launch_plan(out_of_order)
        raise AssertionError("out-of-order calendar was accepted")
    except ReaderError as exc:
        assert exc.code == "LAUNCH-PLAN-CONTRACT", exc.code

    # read_calendar on its own delegates order to the shared law (CALENDAR-PHASE-ORDER).
    try:
        read_calendar(out_of_order["launch_calendar"])
        raise AssertionError("out-of-order calendar was accepted by read_calendar")
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
    parser.add_argument("--acknowledge-dropped-sends", default=None, metavar="HASH",
                        help="owner acknowledgement: the dropped_sends_hash of a late "
                             "compile, passed back to accept that exact list of dropped sends")
    parser.add_argument("--text-copy-dir", default=None, metavar="DIR",
                        help="directory holding Skill 50's <text_set id>.sms.json files "
                             "(working/text); a launch text set with no valid file blocks its builds")
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
    blocked = blocked_builds(document)
    if blocked:
        print("plan-reader: BLOCKED: nothing can be built for: %s (see blocked_by in %s)"
              % (", ".join(blocked), args.out), file=sys.stderr)
        return EXIT_BLOCKED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
