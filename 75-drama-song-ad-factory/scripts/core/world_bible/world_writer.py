#!/usr/bin/env python3
"""world_bible.world_writer: EARLY episode-world authoring (S75-T08).

The world is authored BEFORE the script and BEFORE music. It answers where the
story can happen and under what physical and social conditions: locations,
light, palette, texture, era, sound, plus a never-list of what this world must
never contain.

It is deliberately SEPARATE from reusable character identity. ``cast_refs``
carries reference IDs only -- a character id and an identity revision -- and the
validator refuses any mutation-shaped identity field (name, background,
appearance, psychology) in that list. That separation is what lets a character
survive a change of setting: move a scene from a neighbourhood workshop to a
formal building and the same person ID is still the same person, while the
world, the scene plan, the script and the visual outputs go stale.

Validator scope: a world with NO locations or NO light doctrine is refused.
Three SEMANTIC refusals fire by name with the offending field:

  * ``WORLD_LAYOUT_ACTION_CONTRADICTION`` -- the written action uses a layout
    feature the floor plan does not have;
  * ``WORLD_IMPOSSIBLE_TIMELINE`` -- a scene time runs backwards or teleports
    between locations with no explicit transition, or falls beyond the era;
  * ``WORLD_UNSUPPORTED_REAL_LOCATION_CLAIM`` -- a location names a real place
    and claims entry with no claim/source/owner-answer link.

Authoring is a REAL dispatch through the existing supported model layer
(``choice_card.intake_card.ai_models``) and a REGISTERED TRANSPORT that runs in
THIS process. ``dispatch_author`` admits the run's persisted role binding, sends
the exact request through the transport, captures request and response
provenance and records the attempt through ``record_attempt``.

The anti-forgery rule: the TRANSPORT -- never the caller, never a file -- mints
the dispatch receipt at the moment of the call, drawing a nonce from OS entropy
and binding it to this process's session identity, and the call returns a live,
single-use :class:`DispatchHandle` that exists only in this process's memory.
``author_world`` seals against that handle and consumes it. A response fixture,
a hand-written ``model-bindings.json`` and a record read back from a JSON file
carry strings only: they cannot mint a handle and cannot replay one, so an
authoring record can only be claimed by a dispatch that actually happened in
this run. A dispatch that cannot be proven is refused with
``WORLD_AUTHORING_DISPATCH_UNPROVEN``; ``author_world`` only seals a body that a
proven dispatch actually produced. Tests inject a deterministic no-spend
transport (``no_spend_transport``); no provider is called.

Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import secrets
import sys

SCHEMA_VERSION = "1.0.0"
WORLD_KIND = "episode_world"

#: Named semantic refusal codes (WORLD-AND-CONTINUITY.md, S75-A08 evidence).
CODE_LAYOUT_ACTION = "WORLD_LAYOUT_ACTION_CONTRADICTION"
CODE_IMPOSSIBLE_TIMELINE = "WORLD_IMPOSSIBLE_TIMELINE"
CODE_REAL_LOCATION = "WORLD_UNSUPPORTED_REAL_LOCATION_CLAIM"
CODE_DISPATCH_UNPROVEN = "WORLD_AUTHORING_DISPATCH_UNPROVEN"

#: The real authoring dispatch identity (SPEC 56: operation + implemented
#: handler + prompt/template revision are part of the captured provenance).
DISPATCH_OPERATION = "episode_world_author"
DISPATCH_HANDLER = "world_bible.world_writer.dispatch_author"
PROMPT_TEMPLATE_REVISION = "episode-world-author-prompt/v1"
#: The one supported model layer every stage dispatch consumes.
MODELS_LAYER = "choice_card.intake_card.ai_models"

#: Sections every authored world must carry. Missing ones are named in errors.
REQUIRED_SECTIONS = (
    "premise", "era", "locations", "light", "palette", "texture", "sound",
    "never_list", "cast_refs", "continuity",
)

#: Identity fields that belong to the CHARACTER BIBLE, never to a world record.
#: Their presence in ``cast_refs`` means the two foundations have been merged and
#: a later setting change would silently rewrite a person.
IDENTITY_FIELDS = (
    "name", "display_name", "full_name", "background", "backstory", "biography",
    "appearance", "physique", "ethnicity", "age", "personality", "psychology",
    "motivation", "want", "wound", "voice", "voice_notes", "relationships",
)

#: Outputs a setting change invalidates. Character identity is NOT in this list.
SETTING_DEPENDENTS = ("scene_plan", "script", "visual_outputs")

LOCATION_ID_RE = re.compile(r"^loc_[A-Za-z0-9][A-Za-z0-9_.-]*$")
CHARACTER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class WorldError(ValueError):
    """Raised when a world record is refused by the validator."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def _nonempty_list(value):
    return isinstance(value, list) and len(value) > 0


def canonical_digest(record):
    """SHA-256 over canonical JSON, excluding ``content_digest`` and the
    per-dispatch ``seal`` proof. The seal covers this digest instead of sitting
    inside it, so identical world content seals to an identical digest while the
    proof of the dispatch stays per-call (see :func:`_seal`)."""
    body = {k: v for k, v in record.items() if k not in ("content_digest", "seal")}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def seal_digest(seal, content_digest):
    """The digest that binds a record's content to the dispatch receipt and the
    handle that produced it: edit either and the seal stops verifying."""
    blob = json.dumps([content_digest, seal.get("dispatch_handle"), seal.get("receipt")],
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_locations(record, errors):
    locations = record.get("locations")
    if not _nonempty_list(locations):
        errors.append("world has no locations: at least one location record is required")
        return
    seen = set()
    for index, loc in enumerate(locations):
        pointer = "locations[%d]" % index
        if not isinstance(loc, dict):
            errors.append("%s must be an object" % pointer)
            continue
        loc_id = loc.get("location_id")
        if not _nonempty(loc_id):
            errors.append("%s.location_id is required" % pointer)
        elif not LOCATION_ID_RE.match(loc_id):
            errors.append("%s.location_id %r must match loc_<slug>" % (pointer, loc_id))
        elif loc_id in seen:
            errors.append("%s.location_id %r is duplicated" % (pointer, loc_id))
        else:
            seen.add(loc_id)
        if not _nonempty(loc.get("name")):
            errors.append("%s.name is required" % pointer)
        if not _nonempty(loc.get("function")):
            errors.append("%s.function is required (what the place does in the story)" % pointer)
        if not isinstance(loc.get("interior"), bool):
            errors.append("%s.interior must be true or false" % pointer)
        layout = loc.get("layout")
        features = layout.get("features") if isinstance(layout, dict) else None
        if not _nonempty_list(features):
            errors.append("%s.layout.features is required: the floor plan the written action must fit" % pointer)
        elif not all(_nonempty(f) for f in features):
            errors.append("%s.layout.features entries must be non-empty strings" % pointer)
        elif len({f.strip().lower() for f in features}) != len(features):
            errors.append("%s.layout.features repeats a value" % pointer)
        reality = loc.get("reality")
        if reality not in ("fiction", "real"):
            errors.append("%s.reality must be 'fiction' or 'real'" % pointer)
        elif reality == "real" and not _nonempty(loc.get("claim_source")):
            errors.append(
                "%s: %s.claim_source is missing; %r names a real place and %s.access claims entry "
                "without a claim/source/owner-answer link"
                % (CODE_REAL_LOCATION, pointer, loc_id, pointer))


def _validate_light(record, errors):
    light = record.get("light")
    if not isinstance(light, dict):
        errors.append("world has no light doctrine: light must be an object with sources")
        return
    sources = light.get("sources")
    if not _nonempty_list(sources):
        errors.append("world has no light doctrine: at least one motivated light source is required")
        return
    for index, src in enumerate(sources):
        pointer = "light.sources[%d]" % index
        if not isinstance(src, dict):
            errors.append("%s must be an object" % pointer)
            continue
        if not _nonempty(src.get("source")):
            errors.append("%s.source is required" % pointer)
        if not _nonempty(src.get("direction")):
            errors.append("%s.direction is required" % pointer)
    if not _nonempty(light.get("doctrine")):
        errors.append("light.doctrine is required: the rule every scene's light must obey")


def _validate_era(record, errors):
    era = record.get("era")
    if not isinstance(era, dict):
        errors.append("era must be an object with period and time_of_day")
        return
    for key in ("period", "time_of_day"):
        if not _nonempty(era.get(key)):
            errors.append("era.%s is required" % key)
    if not isinstance(era.get("time_jumps"), list):
        errors.append("era.time_jumps must be a list (empty when the story is continuous)")
    span = era.get("span_minutes")
    if not isinstance(span, int) or isinstance(span, bool) or span < 1:
        errors.append("era.span_minutes must be a positive integer (the elapsed time the world allows)")


def _validate_atmosphere(record, errors):
    for key in ("palette", "texture"):
        values = record.get(key)
        if not _nonempty_list(values):
            errors.append("%s must be a non-empty list" % key)
            continue
        if not all(_nonempty(v) for v in values):
            errors.append("%s entries must be non-empty strings" % key)
        elif len({v.strip().lower() for v in values}) != len(values):
            errors.append("%s repeats a value; repetition cannot stand in for the atmosphere" % key)


def _validate_sound(record, errors):
    sound = record.get("sound")
    if not isinstance(sound, dict):
        errors.append("sound must be an object with ambience")
        return
    if not _nonempty(sound.get("ambience")):
        errors.append("sound.ambience is required")
    for key in ("off_screen", "silence"):
        if key in sound and not isinstance(sound[key], list):
            errors.append("sound.%s must be a list" % key)


def _validate_never_list(record, errors):
    never = record.get("never_list")
    if not _nonempty_list(never):
        errors.append("never_list must be a non-empty list of things this world must never contain")
        return
    if not all(_nonempty(v) for v in never):
        errors.append("never_list entries must be non-empty strings")
    elif len({v.strip().lower() for v in never}) != len(never):
        errors.append("never_list repeats an entry")


def _validate_cast(record, errors):
    cast = record.get("cast_refs")
    if not isinstance(cast, list):
        errors.append("cast_refs must be a list of character reference IDs")
        return
    for index, ref in enumerate(cast):
        pointer = "cast_refs[%d]" % index
        if not isinstance(ref, dict):
            errors.append("%s must be an object" % pointer)
            continue
        cid = ref.get("character_id")
        if not _nonempty(cid) or not CHARACTER_ID_RE.match(cid):
            errors.append("%s.character_id is required" % pointer)
        if not isinstance(ref.get("identity_revision"), int) or ref["identity_revision"] < 1:
            errors.append("%s.identity_revision must be a positive integer" % pointer)
        leaked = sorted(set(ref) & set(IDENTITY_FIELDS))
        if leaked:
            errors.append(
                "%s copies reusable identity field(s) %s; a world holds reference IDs only"
                % (pointer, ", ".join(leaked))
            )


def _validate_scenes(record, errors):
    scenes = record.get("scenes")
    if scenes is None:
        return
    if not isinstance(scenes, list):
        errors.append("scenes must be a list")
        return
    locations = {
        loc.get("location_id"): (i, loc)
        for i, loc in enumerate(record.get("locations") or [])
        if isinstance(loc, dict) and _nonempty(loc.get("location_id"))
    }
    era = record.get("era") if isinstance(record.get("era"), dict) else {}
    span = era.get("span_minutes")
    span_ok = isinstance(span, int) and not isinstance(span, bool)
    previous = None
    for index, scene in enumerate(scenes):
        pointer = "scenes[%d]" % index
        if not isinstance(scene, dict):
            errors.append("%s must be an object" % pointer)
            continue
        loc_id = scene.get("location_id")
        if loc_id not in locations:
            errors.append("%s.location_id %r does not resolve to any location" % (pointer, loc_id))
        if not _nonempty(scene.get("action")):
            errors.append("%s.action is required: the physical action the layout must support" % pointer)
        uses = scene.get("uses")
        if not isinstance(uses, list):
            errors.append("%s.uses must be a list of the layout features the action uses" % pointer)
            uses = []
        if loc_id in locations:
            loc_index, loc = locations[loc_id]
            layout = loc.get("layout")
            features = layout.get("features") if isinstance(layout, dict) else None
            features = [f for f in (features or []) if isinstance(f, str)]
            for u_index, feature in enumerate(uses):
                if feature not in features:
                    errors.append(
                        "%s: %s.uses[%d] %r is not in locations[%d].layout.features; "
                        "the floor plan must support the written action"
                        % (CODE_LAYOUT_ACTION, pointer, u_index, feature, loc_index))
        minutes = scene.get("minutes_from_start")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 0:
            errors.append("%s.minutes_from_start must be a non-negative integer" % pointer)
            minutes = None
        if minutes is not None and span_ok and minutes > span:
            errors.append(
                "%s: %s.minutes_from_start %d is beyond era.span_minutes %d; "
                "the timeline must fit the declared era"
                % (CODE_IMPOSSIBLE_TIMELINE, pointer, minutes, span))
        if minutes is not None and previous is not None:
            transition = _nonempty(scene.get("transition"))
            moved = loc_id != previous[1]
            if minutes < previous[0] and not transition:
                errors.append(
                    "%s: %s.minutes_from_start %d moves backwards from %d with no explicit "
                    "transition; the timeline is impossible"
                    % (CODE_IMPOSSIBLE_TIMELINE, pointer, minutes, previous[0]))
            elif moved and minutes == previous[0] and not transition:
                errors.append(
                    "%s: %s.minutes_from_start %d carries travel from %r to %r in the same "
                    "minute with no explicit transition; the timeline is impossible"
                    % (CODE_IMPOSSIBLE_TIMELINE, pointer, minutes, previous[1], loc_id))
        if minutes is not None:
            previous = (minutes, loc_id)


def validate(record):
    """Return the list of refusal reasons. Empty list means the world is usable."""
    errors = []
    if not isinstance(record, dict):
        return ["world record must be a JSON object"]
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be %r" % SCHEMA_VERSION)
    if record.get("kind") != WORLD_KIND:
        errors.append("kind must be %r" % WORLD_KIND)
    for key in ("artifact_id", "run_id"):
        if not _nonempty(record.get(key)):
            errors.append("%s is required" % key)
    if not isinstance(record.get("revision"), int) or record["revision"] < 1:
        errors.append("revision must be a positive integer")
    for key in REQUIRED_SECTIONS:
        if key not in record:
            errors.append("required section %r is missing" % key)
    if not _nonempty(record.get("premise")):
        errors.append("premise is required")
    if record.get("fiction_classification") not in ("proposed_fiction", "sourced"):
        errors.append("fiction_classification must be 'proposed_fiction' or 'sourced'")
    if not isinstance(record.get("continuity"), dict) or not _nonempty_list(
            (record.get("continuity") or {}).get("must_persist")):
        errors.append("continuity.must_persist must list what survives between scenes")
    errors.extend(_dispatch_proof_errors(record.get("provenance"), "provenance"))
    errors.extend(_seal_proof_errors(record.get("seal"), "seal", record))
    _validate_locations(record, errors)
    _validate_light(record, errors)
    _validate_era(record, errors)
    _validate_atmosphere(record, errors)
    _validate_sound(record, errors)
    _validate_never_list(record, errors)
    _validate_cast(record, errors)
    _validate_scenes(record, errors)
    return errors


def _seal(record):
    """Stamp the record: the content digest over the authored body, then the
    seal digest binding that digest to this dispatch's receipt and handle."""
    record = copy.deepcopy(record)
    record.pop("content_digest", None)
    record["content_digest"] = canonical_digest(record)
    seal = dict(record.get("seal") or {})
    seal["seal_digest"] = seal_digest(seal, record["content_digest"])
    record["seal"] = seal
    return record


# ---------------------------------------------------------------------------
# real authoring dispatch through the existing supported model layer

#: Per-process session identity, drawn from OS entropy at import. It is never
#: written to a file and never serialized into a record: it is what makes a
#: dispatch receipt a fact about THIS run rather than a string written down in
#: advance.
SESSION = secrets.token_hex(16)

#: Process memory only. Nothing here is ever serialized, so a fixture, a forged
#: bindings file or a record read back from disk can neither mint nor replay a
#: dispatch handle.
_HANDLES = {}   # handle ref -> live DispatchHandle
_SEALED = {}    # sealed content digest -> ref of the handle that sealed it


class DispatchTransport:
    """The dispatch seam: an object that really calls a model in THIS process.

    Only a registered transport can dispatch, and the TRANSPORT -- never the
    caller, never a file -- mints the receipt at the moment of the call: a fresh
    nonce from OS entropy bound to this process's session identity. That receipt
    cannot be pre-created, and the handle the call returns lives only here.
    """

    def __init__(self, fn, *, kind):
        if not callable(fn):
            raise WorldError(["a dispatch transport must wrap a callable"])
        if kind not in ("live", "no_spend"):
            raise WorldError(["dispatch transport kind must be 'live' or 'no_spend'"])
        self.fn = fn
        self.kind = kind
        self.transport_id = hashlib.sha256(
            (SESSION + ":" + kind + ":" + secrets.token_hex(8)).encode("utf-8")).hexdigest()[:16]
        # the convention the other stages read: a live worker is marked
        self._s75_live_runner = (kind == "live")

    def __call__(self, request):
        response = self.fn(request)
        nonce = secrets.token_hex(16)
        receipt = {"transport_id": self.transport_id, "kind": self.kind, "nonce": nonce,
                   "session": hashlib.sha256((SESSION + ":" + nonce).encode("utf-8")).hexdigest()}
        receipt["receipt_digest"] = hashlib.sha256(json.dumps(
            receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return response, receipt


def no_spend_transport(fn):
    """Register a deterministic, zero-cost transport (tests and dry runs). It is
    a real dispatch in this process; the only thing it skips is the spend."""
    return DispatchTransport(fn, kind="no_spend")


def live_transport(fn):
    """Register the production transport that actually calls the model."""
    return DispatchTransport(fn, kind="live")


class DispatchHandle:
    """Live, single-use proof that a dispatch ran in THIS process.

    Returned only by a real call through a registered transport, kept only in
    process memory and consumed by the one record it seals. It is never written
    to any file and never copied into a record, so no fixture and no bindings
    file can produce one or replay one.
    """

    def __init__(self, *, attempt_id, request_receipt, receipt):
        self.ref = hashlib.sha256(
            (SESSION + ":" + secrets.token_hex(16)).encode("utf-8")).hexdigest()
        self.session = SESSION
        self.transport_id = receipt.get("transport_id")
        self.attempt_id = attempt_id
        self.request_receipt = request_receipt
        self.receipt = copy.deepcopy(receipt)
        self.consumed_by = None
        _HANDLES[self.ref] = self


def _live_dispatch_reason(dispatch):
    """Why this dispatch cannot be shown to be a call that ran in THIS process.

    Files hold strings; the handle exists only in this process's memory. That is
    the difference between authoring and echoing a fixture.
    """
    if not isinstance(dispatch, dict):
        return "%s: dispatch is missing; authoring requires a proven model dispatch" \
            % CODE_DISPATCH_UNPROVEN
    handle = dispatch.get("_handle")
    if not isinstance(handle, DispatchHandle) or _HANDLES.get(handle.ref) is not handle:
        return ("%s: dispatch carries no live dispatch handle; a response fixture, a hand-written "
                "model-bindings.json or a record read back from a file is not a dispatch"
                % CODE_DISPATCH_UNPROVEN)
    attempt = dispatch.get("attempt") if isinstance(dispatch.get("attempt"), dict) else {}
    seal = dispatch.get("seal") if isinstance(dispatch.get("seal"), dict) else {}
    for ok, why in (
            (handle.session == SESSION, "the dispatch handle was not minted in this run"),
            (handle.ref == seal.get("dispatch_handle"),
             "dispatch.seal.dispatch_handle does not match the live handle"),
            (handle.attempt_id == attempt.get("attempt_id"),
             "the live handle does not belong to this attempt"),
            (handle.request_receipt == dispatch.get("request_receipt"),
             "the live handle does not belong to this request"),
            (handle.receipt == seal.get("receipt"),
             "dispatch.seal.receipt is not the receipt the transport minted")):
        if not ok:
            return "%s: %s" % (CODE_DISPATCH_UNPROVEN, why)
    if handle.consumed_by:
        return ("%s: the dispatch handle already sealed %s; one dispatch proves one authoring "
                "record" % (CODE_DISPATCH_UNPROVEN, handle.consumed_by))
    return None


def build_author_request(inputs):
    """The exact authoring request: operation, implemented handler, prompt
    template revision and the exact input artifact revisions supplied."""
    if not isinstance(inputs, dict) or not inputs:
        raise WorldError(["dispatch.inputs must be a JSON object of exact input artifact revisions"])
    return {"operation": DISPATCH_OPERATION,
            "handler": DISPATCH_HANDLER,
            "prompt_template_revision": PROMPT_TEMPLATE_REVISION,
            "inputs": copy.deepcopy(inputs)}


def _dispatch_proof_errors(provenance, where):
    """The proof a captured dispatch must carry. A world that cannot show it is
    refused: a validator that only opens a JSON file never authored anything."""
    if not isinstance(provenance, dict):
        return ["%s: %s is missing; authoring requires a proven model dispatch"
                % (CODE_DISPATCH_UNPROVEN, where)]
    errors = []
    if provenance.get("operation") != DISPATCH_OPERATION:
        errors.append("%s: %s.operation must be %r" % (CODE_DISPATCH_UNPROVEN, where, DISPATCH_OPERATION))
    if provenance.get("handler") != DISPATCH_HANDLER:
        errors.append("%s: %s.handler must be %r" % (CODE_DISPATCH_UNPROVEN, where, DISPATCH_HANDLER))
    request = provenance.get("request")
    if not isinstance(request, dict) or not request.get("inputs"):
        errors.append("%s: %s.request.inputs is missing; the exact dispatched inputs are provenance"
                      % (CODE_DISPATCH_UNPROVEN, where))
    if not _nonempty(provenance.get("request_receipt")):
        errors.append("%s: %s.request_receipt is missing; the dispatched request is unproven"
                      % (CODE_DISPATCH_UNPROVEN, where))
    response = provenance.get("response") if isinstance(provenance.get("response"), dict) else {}
    for key in ("response_model", "resolved_provider_model", "raw_digest"):
        if not _nonempty(response.get(key)):
            errors.append("%s: %s.response.%s is missing; the response model is never assumed"
                          % (CODE_DISPATCH_UNPROVEN, where, key))
    if response.get("response_evidence") not in ("response_metadata", "router_receipt"):
        errors.append("%s: %s.response.response_evidence cannot prove the model called"
                      % (CODE_DISPATCH_UNPROVEN, where))
    attempt = provenance.get("attempt") if isinstance(provenance.get("attempt"), dict) else {}
    if not _nonempty(attempt.get("attempt_id")) or not _nonempty(attempt.get("binding_id")):
        errors.append("%s: %s.attempt identity is missing; the dispatch is unproven"
                      % (CODE_DISPATCH_UNPROVEN, where))
    if not _nonempty((attempt.get("evidence") or {}).get("correlation")):
        errors.append("%s: %s.attempt.evidence.correlation is missing; request/router/response "
                      "evidence is not correlated" % (CODE_DISPATCH_UNPROVEN, where))
    return errors


def _seal_proof_errors(seal, where, record=None):
    """The seal proof a record must carry: the handle the dispatch returned, the
    receipt the transport minted at call time, and a seal digest that verifies
    against the record's own content digest."""
    if not isinstance(seal, dict):
        return ["%s: %s is missing; a world record carries the seal of the dispatch that "
                "authored it" % (CODE_DISPATCH_UNPROVEN, where)]
    errors = []
    if not _nonempty(seal.get("dispatch_handle")):
        errors.append("%s: %s.dispatch_handle is missing; the record must be bound to the live "
                      "handle the dispatch returned" % (CODE_DISPATCH_UNPROVEN, where))
    receipt = seal.get("receipt") if isinstance(seal.get("receipt"), dict) else {}
    for key in ("transport_id", "nonce", "receipt_digest"):
        if not _nonempty(receipt.get(key)):
            errors.append("%s: %s.receipt.%s is missing; the transport receipt is what proves a "
                          "call happened in this run" % (CODE_DISPATCH_UNPROVEN, where, key))
    if record is not None:
        if not _nonempty(seal.get("seal_digest")):
            errors.append("%s: %s.seal_digest is missing" % (CODE_DISPATCH_UNPROVEN, where))
        elif seal.get("seal_digest") != seal_digest(seal, record.get("content_digest")):
            errors.append("%s: %s.seal_digest does not verify against the record's content digest"
                          % (CODE_DISPATCH_UNPROVEN, where))
    return errors


def dispatch_author(*, run_dir, attempt_id, inputs, runner, route=None,
                    runtime="claude-nine", router_receipt=None,
                    response_provider=None, now=None):
    """Author through the existing supported model layer.

    Admits the run's persisted role binding (``ai_models.admit_dispatch``), sends
    ``build_author_request(inputs)`` to the registered transport and records the
    attempt through ``ai_models.record_attempt``, which verifies the requested,
    resolved and response model and stores correlated request/router/response
    evidence. ``runner`` must be a :class:`DispatchTransport` created by
    ``no_spend_transport`` (tests) or ``live_transport`` (production): a bare
    callable or a fixture closure is refused, because it is not a call that
    happened in this run. The transport mints the receipt and the call returns a
    live, single-use :class:`DispatchHandle`. Returns the captured
    request/response provenance and that seal. Raises :class:`WorldError` with
    ``WORLD_AUTHORING_DISPATCH_UNPROVEN`` whenever the dispatch cannot be proven.
    """
    if not isinstance(runner, DispatchTransport):
        raise WorldError(["%s: dispatch.runner is not a registered dispatch transport; a "
                          "response fixture, a hand-written model-bindings.json or any "
                          "caller-written callable is not a dispatch. Register the transport "
                          "with no_spend_transport() (tests) or live_transport() (production)."
                          % CODE_DISPATCH_UNPROVEN])
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    from choice_card.intake_card import ai_models as models

    admission = models.admit_dispatch(run_dir, models.ROLE_BUILD,
                                      route=route, runtime=runtime)
    if not admission.get("ok"):
        raise WorldError(["%s: dispatch admission refused (%s): %s"
                          % (CODE_DISPATCH_UNPROVEN, admission.get("error_code"),
                             admission.get("reason") or admission.get("message"))])
    request = build_author_request(inputs)
    response, receipt = runner(request)
    if not isinstance(response, dict) or not isinstance(response.get("raw"), dict):
        raise WorldError(["%s: dispatch.response.raw must be the model's structured world output"
                          % CODE_DISPATCH_UNPROVEN])
    for key in ("response_model", "resolved_provider_model"):
        if not _nonempty(response.get(key)):
            raise WorldError(["%s: dispatch.response.%s is missing; the response model is never assumed"
                              % (CODE_DISPATCH_UNPROVEN, key)])
    request_receipt = hashlib.sha256(json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    raw = response["raw"]
    raw_digest = hashlib.sha256(json.dumps(
        raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    recorded = models.record_attempt(
        run_dir, models.ROLE_BUILD, attempt_id,
        requested_model=admission["binding"]["model_id"],
        resolved_provider_model=response["resolved_provider_model"],
        response_model=response["response_model"],
        route=admission["binding"]["route"],
        request_receipt=request_receipt,
        router_receipt=router_receipt,
        response_evidence="response_metadata",
        response_provider=response_provider,
        runtime=runtime, now=now)
    if not recorded.get("ok"):
        raise WorldError(["%s: the dispatch cannot be proven (%s): %s"
                          % (CODE_DISPATCH_UNPROVEN, recorded.get("error_code"),
                             recorded.get("reason") or recorded.get("message"))])
    # The handle only exists because the call above really ran: it is minted
    # here, kept in this process and returned to the caller as a live object.
    handle = DispatchHandle(attempt_id=attempt_id, request_receipt=request_receipt,
                            receipt=receipt)
    return {
        "operation": DISPATCH_OPERATION,
        "handler": DISPATCH_HANDLER,
        "prompt_template_revision": PROMPT_TEMPLATE_REVISION,
        "execution": "live" if runner.kind == "live" else "no_spend_fixture",
        "inputs": copy.deepcopy(inputs),
        "request": request,
        "request_receipt": request_receipt,
        "response": {"response_model": response["response_model"],
                     "resolved_provider_model": response["resolved_provider_model"],
                     "response_provider": response_provider,
                     "provider_job_id": response.get("provider_job_id"),
                     "response_evidence": "response_metadata",
                     "router_receipt": router_receipt,
                     "raw_digest": raw_digest},
        "attempt": copy.deepcopy(recorded["attempt"]),
        "seal": {"dispatch_handle": handle.ref, "receipt": copy.deepcopy(receipt)},
        "parsed_output": copy.deepcopy(raw),
        "_handle": handle,
    }


def author_world(payload, *, artifact_id, run_id, revision=1, dispatch=None,
                 dependencies=None):
    """Author and validate one ``episode_world`` record from a proven dispatch.

    ``payload`` is the world body the model actually returned; ``dispatch`` is
    the provenance captured by :func:`dispatch_author`. A body with no proven
    dispatch -- a dict someone merely opened from a JSON file -- is refused with
    ``WORLD_AUTHORING_DISPATCH_UNPROVEN``, and so is one whose live dispatch
    handle is missing, foreign or already spent: a seal is bound to a call that
    happened in THIS run, and one call seals one record. Raises
    :class:`WorldError` when the dispatch is unproven or the validator refuses
    the result.
    """
    if not isinstance(payload, dict):
        raise WorldError(["world payload must be a JSON object"])
    errors = _dispatch_proof_errors(dispatch, "dispatch")
    if isinstance(dispatch, dict):
        errors.extend(_seal_proof_errors(dispatch.get("seal"), "dispatch.seal"))
        if not errors and dispatch.get("parsed_output") != payload:
            errors.append("%s: dispatch.parsed_output does not match the world body; the record "
                          "must be the dispatched model output" % CODE_DISPATCH_UNPROVEN)
    if not errors:
        unproven = _live_dispatch_reason(dispatch)
        if unproven:
            errors.append(unproven)
    if errors:
        raise WorldError(errors)
    handle = dispatch["_handle"]
    provenance = {k: v for k, v in dispatch.items() if k not in ("seal", "_handle")}
    record = copy.deepcopy(payload)
    record.update({
        "schema_version": SCHEMA_VERSION,
        "kind": WORLD_KIND,
        "artifact_id": artifact_id,
        "run_id": run_id,
        "revision": revision,
        "provenance": copy.deepcopy(provenance),
        "seal": copy.deepcopy(dispatch["seal"]),
        "dependencies": dependencies or {},
    })
    record = _seal(record)
    errors = validate(record)
    if errors:
        raise WorldError(errors)
    handle.consumed_by = record["content_digest"]
    _SEALED[record["content_digest"]] = handle.ref
    return record


def _parent_seal_reason(record):
    """Why this run cannot attribute the world record to a real dispatch.

    A setting change is derived from an authored world, so the parent must be a
    record this run sealed from a live dispatch. ponytail: a world record read
    back from a file is refused here -- files carry strings, never proof of who
    authored them. Upgrade path: an external trust anchor (a transport-side
    signing key) so a later process can verify the parent's seal; add it when
    authoring and setting changes run in separate processes.
    """
    if not isinstance(record, dict):
        return "world record must be a JSON object"
    digest = record.get("content_digest")
    if digest != canonical_digest(record):
        return ("%s: the world record does not match its own content_digest; a setting change "
                "must not launder a record edited after it was sealed" % CODE_DISPATCH_UNPROVEN)
    if _SEALED.get(digest) not in _HANDLES:
        return ("%s: this run cannot attribute the world record to a live dispatch; a setting "
                "change derives from an authored world, and a record opened from a file proves "
                "nothing about who authored it" % CODE_DISPATCH_UNPROVEN)
    return None


def change_setting(record, *, locations, reason, era=None):
    """Move the story to a new setting without touching reusable character identity.

    Returns a dict holding the new world revision, the character identity IDs that
    were preserved verbatim, and only the dependent outputs that went stale. The
    parent world must be one this run sealed from a real dispatch (see
    :func:`_parent_seal_reason`); the derived revision carries that dispatch's
    seal forward and re-binds it to the new content digest.
    """
    errors = validate(record)
    if errors:
        raise WorldError(errors)
    unproven = _parent_seal_reason(record)
    if unproven:
        raise WorldError([unproven])
    if not _nonempty(reason):
        raise WorldError(["a setting change needs a stated reason"])

    new_world = copy.deepcopy(record)
    new_world["revision"] = record["revision"] + 1
    new_world["locations"] = copy.deepcopy(locations)
    if era is not None:
        new_world["era"] = copy.deepcopy(era)
    # The scene plan depends on the setting, so it goes stale with it rather than
    # carrying location IDs that no longer resolve.
    new_world.pop("scenes", None)
    new_world["previous_revision"] = record["revision"]
    new_world["change_reason"] = reason

    sealed = _seal(new_world)
    errors = validate(sealed)
    if errors:
        raise WorldError(errors)
    if sealed["cast_refs"] != record["cast_refs"]:
        raise WorldError(["a setting change must not rewrite reusable character identity"])
    _SEALED[sealed["content_digest"]] = _SEALED[record["content_digest"]]

    return {
        "world": sealed,
        "preserved_character_identity": [
            {"character_id": ref["character_id"],
             "identity_revision": ref["identity_revision"]}
            for ref in record["cast_refs"]
        ],
        "invalidated": list(SETTING_DEPENDENTS),
        "reason": reason,
    }


def _load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Author or validate an episode world (S75-T08).")
    parser.add_argument("--validate", metavar="FILE",
                        help="validate an existing world record (judgement only; never authorship)")
    parser.add_argument("--author", metavar="INPUTS",
                        help="REFUSED by design: authoring needs a live dispatch in THIS run, "
                             "not files. Kept so a file-only attempt gets a named refusal "
                             "instead of a silent success")
    parser.add_argument("--run-dir", help="accepted only to reach the --author refusal")
    parser.add_argument("--attempt-id", help="accepted only to reach the --author refusal")
    parser.add_argument("--response-fixture", metavar="FILE",
                        help="accepted only to reach the --author refusal; a fixture file is "
                             "never a dispatch")
    parser.add_argument("--artifact-id", default="world_draft_001")
    parser.add_argument("--run-id", default="run_local_001")
    parser.add_argument("--out", metavar="FILE",
                        help="accepted only to reach the --author refusal; nothing is written")
    args = parser.parse_args(argv)

    if not args.validate and not args.author:
        parser.error("choose --validate or --author")

    if args.validate:
        errors = validate(_load(args.validate))
        if errors:
            for line in errors:
                print("REFUSED: %s" % line, file=sys.stderr)
            return 1
        print("OK: world record is usable (validation only; nothing was authored)")
        return 0

    if not (args.run_dir and args.attempt_id and args.response_fixture):
        parser.error("--author requires --run-dir, --attempt-id and --response-fixture")
    print("REFUSED: %s: --response-fixture is a file, not a dispatch; no model call happened in "
          "this run, and a hand-written model-bindings.json is not proof of one. Author through "
          "world_writer.dispatch_author with a registered transport (no_spend_transport in "
          "tests, live_transport in production)." % CODE_DISPATCH_UNPROVEN, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
