#!/usr/bin/env python3
"""script_writer.py: actual model-authored full scene script and lyric sheet (S75-T10 / S75-A10).

This is the writing operation, not a validator. It resolves the complete early
foundation (research, character identities, episode cast, world, causal beats,
scene plan), persists one input manifest with exact ids/revisions/digests, then
DISPATCHES an authoring request through an injected model/tool seam. No
dispatch -> no script and no lyrics artifact. Reading a prewritten story.json
and running checks can never claim generation.

Order enforced before any model call (``story_first_contracts.check_stage``):
research/premise -> complete cast + world -> causal beats + full scene plan ->
script/lyrics. A missing cast field is a missing requirement, never an opt-out.

Dispatch contract (stdlib only, no network in this module)::

    dispatch(request: dict) -> response: dict

The caller binds the supported model/tool layer (the existing transport) and
passes it in; tests pass a deterministic fake dispatcher. Every request and
response is recorded: requested/effective binding, prompt revision, attempt,
idempotency key, native response id and raw-response digest/sha with bounded
raw text retained for diagnosis.

The authored response is a complete scene script plus a lyric sheet. Canonical
lyric line records are DERIVED from the scene performance lines and reconciled
against the returned sheet, so the intended song cannot bind to another draft
by filename coincidence.

On a defect the writer issues a targeted revision request carrying the exact
scene/line pointers and keeps the usable candidate. Two attempts with an
unchanged defect signature stop with ``UNPRODUCTIVE_REVISION``: a changed
hypothesis/input/method or a safe split is required, never an endless broad
rewrite.

ponytail: the six client durations are not hardcoded here; the caller supplies
the selected duration/route/style constraints. Add the duration policy table
when the intake module owns it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_first_contracts as C  # noqa: E402  (sibling module in core/)

TOOL_NAME = "script_writer"
PROMPT_REVISION = "s75.script_writer.prompt.v1"
SCHEMA_VERSION = "s75.script.v1"
REQUIRED_FOUNDATION = (
    "research_bundle",
    "character_identity_library_snapshot",
    "episode_cast_manifest",
    "episode_world",
    "causal_story_beats",
    "scene_plan",
)
#: Contract: the opening 12 seconds carry spoken/articulated words.
SPOKEN_OPENING_S = 12.0
MAX_ATTEMPTS = 2
RAW_KEEP_CHARS = 20000
LINE_FIELDS = ("line_id", "character_id", "text", "start_s", "end_s")


class WriterRefused(Exception):
    def __init__(self, code, message, packet=None):
        super().__init__(message)
        self.code = code
        self.packet = packet or {}


def _digest(record):
    return C.artifact_digest(record)


def _defect(code, pointer, detail=None, **refs):
    out = {"code": code, "pointer": pointer}
    if detail:
        out["detail"] = detail
    out.update({k: v for k, v in refs.items() if v is not None})
    return out


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _norm(text):
    return " ".join(str(text or "").split()).lower()


# --- foundation -----------------------------------------------------------

def _payload_of(registry, kind):
    record = registry.get(kind) if registry is not None else None
    return record or None


def _raise_missing(kind, why, registry):
    raise WriterRefused(
        "MISSING_FOUNDATION",
        "script writing refused: %s %s" % (kind, why),
        {"kind": kind, "issue": why, "present": registry.kinds() if registry else ()},
    )


def _check_research(payload):
    premise = payload.get("premise")
    if not isinstance(premise, dict) or not any(premise.values()):
        return ["premise"]
    claims = payload.get("claim_map") or payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["claim_map"]
    if any(not isinstance(c, dict) or not c.get("claim_id") for c in claims):
        return ["claim_map.claim_id"]
    return []


def _check_beats(payload):
    beats = payload.get("beats")
    if not isinstance(beats, list) or not beats:
        return ["beats"]
    ids = [b.get("beat_id") for b in beats if isinstance(b, dict)]
    if len(ids) != len(beats) or any(not i for i in ids):
        return ["beats.beat_id"]
    for beat in beats[1:]:
        if beat.get("caused_by") not in ids:
            return ["beats.caused_by"]
    return []


def _identity_map(snapshot):
    if isinstance(snapshot, dict) and isinstance(snapshot.get("identities"), dict):
        return snapshot["identities"]
    if isinstance(snapshot, dict) and isinstance(snapshot.get("identities"), list):
        return {i.get("character_id"): i for i in snapshot["identities"] if isinstance(i, dict)}
    return {}


def _check_identities(snapshot, manifest):
    identities = _identity_map(snapshot)
    defects = []
    if not identities:
        return ["identities"]
    for entry in (manifest or {}).get("cast") or []:
        cid = entry.get("character_id")
        record = identities.get(cid)
        if not record:
            defects.append("identities.%s" % cid)
            continue
        errors = C.validate_identity(record)
        if errors:
            defects.append("identities.%s.%s" % (cid, errors[0].get("field")))
        if record.get("revision") != entry.get("identity_revision"):
            defects.append("identities.%s.revision" % cid)
        if entry.get("identity_digest") and record.get("content_digest") != entry.get("identity_digest"):
            defects.append("identities.%s.content_digest" % cid)
    return defects


def build_foundation(registry):
    """Resolve the complete early foundation, or refuse before any dispatch."""
    for kind in REQUIRED_FOUNDATION:
        record = registry.get(kind)
        if not record or not record.get("digest"):
            _raise_missing(kind, "absent", registry)
        if record.get("state") not in (C.COMPLETE, C.APPROVED):
            _raise_missing(kind, "not ready (%s)" % record.get("state"), registry)

    payloads = {kind: registry.payload_of(kind) for kind in REQUIRED_FOUNDATION}
    manifest = payloads["episode_cast_manifest"]
    world = payloads["episode_world"]
    plan = payloads["scene_plan"]

    checks = (
        ("research_bundle", _check_research(payloads["research_bundle"])),
        ("causal_story_beats", _check_beats(payloads["causal_story_beats"])),
        ("character_identity_library_snapshot",
         _check_identities(payloads["character_identity_library_snapshot"], manifest)),
    )
    for kind, fields in checks:
        if fields:
            raise WriterRefused("INCOMPLETE_FOUNDATION",
                                "%s is incomplete: %s" % (kind, ", ".join(fields)),
                                {"kind": kind, "fields": fields})
    for kind, defects in (
        ("episode_world", C.validate_world(world)),
        ("episode_cast_manifest", C.validate_cast_manifest(manifest, plan.get("scenes"))),
        ("scene_plan", C.validate_scene_plan(plan, world=world, manifest=manifest)),
    ):
        if defects:
            raise WriterRefused("INCOMPLETE_FOUNDATION", "%s has schema defects" % kind,
                                {"kind": kind, "defects": defects})

    try:
        C.check_stage("script_lyrics", registry)
    except C.ContractError as exc:
        raise WriterRefused("MISSING_FOUNDATION", str(exc), dict(exc.packet, code=exc.code))

    identities = _identity_map(payloads["character_identity_library_snapshot"])
    foundation = {
        "prompt_revision": PROMPT_REVISION,
        "artifacts": {
            kind: {
                "artifact_id": registry.get(kind).get("artifact_id"),
                "revision": registry.get(kind).get("revision"),
                "digest": registry.get(kind).get("digest"),
                "state": registry.get(kind).get("state"),
            }
            for kind in REQUIRED_FOUNDATION
        },
        "identities": {
            entry["character_id"]: {
                "revision": identities[entry["character_id"]].get("revision"),
                "content_digest": identities[entry["character_id"]].get("content_digest"),
                "display_name": identities[entry["character_id"]].get("display_name"),
            }
            for entry in manifest.get("cast") or []
        },
        "world_revision": world.get("revision"),
        "cast_ids": [e.get("character_id") for e in manifest.get("cast") or []],
        "scene_ids": [s.get("scene_id") for s in plan.get("scenes") or []],
        "payloads": payloads,
    }
    foundation["digest"] = _digest({k: foundation[k] for k in
                                    ("artifacts", "identities", "world_revision",
                                     "cast_ids", "scene_ids")})
    return foundation


# --- request --------------------------------------------------------------

def _constraint_defects(constraints):
    defects = []
    if not isinstance(constraints, dict):
        return ["constraints"]
    for key in ("duration_seconds", "route", "style_id"):
        value = constraints.get(key)
        if value in (None, "", [], {}):
            defects.append(key)
    duration = constraints.get("duration_seconds")
    if duration is not None and (_num(duration) is None or _num(duration) <= 0):
        defects.append("duration_seconds")
    return defects


PROMPT_RULES = (
    "Write the COMPLETE script and lyric sheet for every planned scene. "
    "Preserve every scene_id and its sequence, or declare an explicit split/merge lineage. "
    "Use only the declared cast_ids; never add an undefined speaker or meaningful extra. "
    "Every line carries line_id, character_id, exact text, start_s, end_s and delivery "
    "(spoken|sung). The first 12 seconds carry spoken/articulated words. "
    "Each scene after the first must name its causal_predecessor (the previous scene_id or "
    "its causal_outcome_id) and a causal_outcome_id that makes the next scene necessary. "
    "Mark exactly ONE scene with solution_introduced=true, and it must come after the "
    "consequential choice and emotional turn. Mark every later scene where behavior visibly "
    "changes with behavior_change=true. Exactly one CTA line, marked role=\"cta\", after the "
    "earned outcome. Return lyric_sheet.lines repeating every sung line identically "
    "(line_id, character_id, text) so the song cannot bind to another draft. "
    "Reply with JSON only, no prose and no code fence."
)


def build_prompt(foundation, constraints):
    """The full authoring prompt: plan, cast, world, facts -- never keywords alone."""
    payloads = foundation["payloads"]
    lines = [
        "You are the script and lyric writer for one drama-song episode.",
        "PROMPT REVISION: %s" % PROMPT_REVISION,
        "",
        "SELECTED CONSTRAINTS",
        json.dumps(constraints, indent=2, sort_keys=True),
        "",
        "FOUNDATION REVISIONS",
        json.dumps(foundation["artifacts"], indent=2, sort_keys=True),
        "",
        "CHARACTER IDENTITIES (complete; each line must match one of these people)",
        json.dumps(_identity_map(payloads["character_identity_library_snapshot"]),
                   indent=2, sort_keys=True),
        "",
        "EPISODE CAST MANIFEST",
        json.dumps(payloads["episode_cast_manifest"], indent=2, sort_keys=True),
        "",
        "EPISODE WORLD",
        json.dumps(payloads["episode_world"], indent=2, sort_keys=True),
        "",
        "RESEARCH AND PREMISE (verified facts and claims; invent no client result)",
        json.dumps(payloads["research_bundle"], indent=2, sort_keys=True),
        "",
        "CAUSAL STORY BEATS (because/therefore, not and-then)",
        json.dumps(payloads["causal_story_beats"], indent=2, sort_keys=True),
        "",
        "FULL SCENE PLAN (author every scene in these terms)",
        json.dumps(payloads["scene_plan"], indent=2, sort_keys=True),
        "",
        "OUTPUT CONTRACT",
        "schema_version: %s" % SCHEMA_VERSION,
        "Top-level keys: schema_version, lineage {split[], merged[]}, scenes[], "
        "lyric_sheet {lines[]}, cta {line_id}.",
        PROMPT_RULES,
    ]
    return "\n".join(lines)


def build_request(foundation, constraints, model_binding, attempt=1, revision=None):
    defects = _constraint_defects(constraints)
    if defects:
        raise WriterRefused("INCOMPLETE_CONSTRAINTS",
                            "script writing refused: selected constraints invalid",
                            {"fields": defects})
    prompt = build_prompt(foundation, constraints)
    key = _digest({
        "tool": TOOL_NAME,
        "prompt_revision": PROMPT_REVISION,
        "foundation": foundation["digest"],
        "constraints": constraints,
        "binding": model_binding,
    })
    request = {
        "tool": TOOL_NAME,
        "prompt_revision": PROMPT_REVISION,
        "attempt": attempt,
        "idempotency_key": "%s:%d" % (key, attempt),
        "run_key": key,
        "binding": {"requested": model_binding, "effective": None},
        "foundation": foundation["artifacts"],
        "foundation_digest": foundation["digest"],
        "constraints": dict(constraints),
        "messages": [{"role": "user", "content": prompt}],
        "response_schema": SCHEMA_VERSION,
    }
    if revision:
        request["revision"] = revision
    return request


# --- parsing --------------------------------------------------------------

def _extract_payload(raw_text):
    if not isinstance(raw_text, str):
        raise WriterRefused("DISPATCH_RESPONSE_INVALID", "response carried no raw_text",
                            {"raw_type": type(raw_text).__name__})
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        return json.loads(text)
    except ValueError as exc:
        raise WriterRefused("AUTHORED_UNPARSEABLE", "model output is not JSON: %s" % exc,
                            {"raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
                             "raw_excerpt": raw_text[:400]})


def parse_response(request, response):
    """Keep raw provenance and parse the authored script; never trust a filename."""
    if not isinstance(response, dict):
        raise WriterRefused("DISPATCH_RESPONSE_INVALID", "dispatch returned no response object")
    for key in ("response_id", "raw_text"):
        if not response.get(key):
            raise WriterRefused("DISPATCH_RESPONSE_INVALID",
                                "response missing %s" % key, {"missing": key})
    raw = response["raw_text"]
    authored = _extract_payload(raw)
    encoded = raw.encode("utf-8")
    dispatch = {
        "attempt": request["attempt"],
        "idempotency_key": request["idempotency_key"],
        "requested_binding": request["binding"]["requested"],
        "effective_binding": response.get("effective_binding") or {
            "provider": response.get("provider"), "model": response.get("model")},
        "response_id": response["response_id"],
        "provider": response.get("provider"),
        "model": response.get("model"),
        "raw_sha256": hashlib.sha256(encoded).hexdigest(),
        "raw_bytes": len(encoded),
        "raw_retained": raw[:RAW_KEEP_CHARS],
        "raw_truncated": len(raw) > RAW_KEEP_CHARS,
    }
    return {"authored": authored, "dispatch": dispatch}


# --- authored validation --------------------------------------------------

def derive_lyric_lines(scenes):
    """Canonical lyric records derived from the scenes' own performance lines."""
    lines = []
    for scene in scenes:
        for line in scene.get("sung_lyrics") or []:
            if not isinstance(line, dict):
                continue
            lines.append({
                "line_id": line.get("line_id"),
                "character_id": line.get("character_id"),
                "text": line.get("text"),
                "scene_id": scene.get("scene_id"),
                "section": line.get("section") or scene.get("song_section") or "verse",
                "repeat_of": line.get("repeat_of"),
            })
    repeats = [{"line_id": ln["line_id"], "repeat_of": ln["repeat_of"]}
               for ln in lines if ln.get("repeat_of")]
    return {"schema_version": SCHEMA_VERSION, "lines": lines, "repeat_structure": repeats}


def _lineage_explains(lineage, planned, authored):
    if not isinstance(lineage, dict):
        return False
    reachable = set(planned)
    for entry in (lineage.get("split") or []):
        if not isinstance(entry, dict) or entry.get("from") not in planned or not entry.get("into"):
            return False
        if entry.get("from") in reachable:
            reachable.discard(entry["from"])
            reachable.update(entry["into"])
    for entry in (lineage.get("merged") or []):
        if not isinstance(entry, dict) or len(entry.get("from") or []) < 2:
            return False
        reachable.add(entry.get("into"))
    return reachable == set(authored)


def _all_lines(scenes):
    for index, scene in enumerate(scenes):
        for field in ("spoken_dialogue", "sung_lyrics"):
            for line in scene.get(field) or []:
                if isinstance(line, dict):
                    yield index, field, line


def validate_authored(authored, foundation):
    """Structural + semantic defects for one authored candidate, with exact pointers."""
    if not isinstance(authored, dict):
        return [_defect("AUTHORED_NOT_OBJECT", "/")]
    scenes = authored.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return [_defect("SCENES_MISSING", "/scenes", "every planned scene must be authored")]

    payloads = foundation["payloads"]
    world = payloads["episode_world"]
    manifest = payloads["episode_cast_manifest"]
    defects = []
    seen = set()
    sequences = []
    for index, scene in enumerate(scenes):
        pointer = "/scenes/%d" % index
        if not isinstance(scene, dict):
            defects.append(_defect("SCENE_NOT_OBJECT", pointer))
            continue
        sid = scene.get("scene_id")
        if sid in seen:
            defects.append(_defect("DUPLICATE_SCENE_ID", pointer, scene_id=sid))
        seen.add(sid)
        sequences.append(scene.get("sequence"))
        for issue in C.validate_scene(scene, world=world):
            ref = issue.get("ref")
            line_id = ref if isinstance(ref, str) else (ref or {}).get("line_id")
            defects.append(_defect("SCENE_SCHEMA", pointer + "/" + str(issue.get("field")),
                                   issue.get("issue"), scene_id=sid, line_id=line_id))
    for issue in C.validate_cast_manifest(manifest, scenes):
        ref = issue.get("ref") or {}
        defects.append(_defect("UNDEFINED_PERFORMER", "/scenes", issue.get("field"),
                               scene_id=(ref or {}).get("scene_id"),
                               character_id=(ref or {}).get("character_id")))

    if seen != set(foundation["scene_ids"]):
        if not _lineage_explains(authored.get("lineage"), foundation["scene_ids"], seen):
            defects.append(_defect("SCENE_PLAN_DRIFT", "/scenes",
                                   "authored scenes neither match the plan nor declare lineage",
                                   planned=sorted(foundation["scene_ids"]),
                                   authored=sorted(x for x in seen if x)))

    if any(_num(s) is None for s in sequences) or sequences != sorted(sequences) or \
            sequences != list(range(1, len(sequences) + 1)):
        defects.append(_defect("SEQUENCE_BROKEN", "/scenes", "sequence must be 1..n in order"))

    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        if index == 0:
            continue
        previous = scenes[index - 1]
        allowed = {previous.get("scene_id"), previous.get("causal_outcome_id")}
        if scene.get("causal_predecessor") not in allowed or not previous.get("causal_outcome_id"):
            defects.append(_defect("CAUSAL_GAP", "/scenes/%d/causal_predecessor" % index,
                                   "predecessor must be the previous scene or its outcome",
                                   scene_id=scene.get("scene_id")))

    opening = scenes[0] if isinstance(scenes[0], dict) else {}
    spoken_opening = [
        ln for ln in opening.get("spoken_dialogue") or []
        if isinstance(ln, dict) and _num(ln.get("start_s")) is not None
        and _num(ln["start_s"]) < SPOKEN_OPENING_S
    ]
    if not spoken_opening:
        defects.append(_defect("SPOKEN_OPENING_MISSING", "/scenes/0/spoken_dialogue",
                               "the first 12 s must carry spoken/articulated words",
                               scene_id=opening.get("scene_id")))

    total = 0.0
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        duration = _num(scene.get("duration_seconds")) or 0.0
        total += duration
        for field in ("spoken_dialogue", "sung_lyrics"):
            for line in scene.get(field) or []:
                if not isinstance(line, dict):
                    continue
                pointer = "/scenes/%d/%s/%s" % (index, field, line.get("line_id"))
                start, end = _num(line.get("start_s")), _num(line.get("end_s"))
                if start is None or end is None or end <= start:
                    defects.append(_defect("LINE_TIMING_INVALID", pointer,
                                           "line needs start_s < end_s",
                                           line_id=line.get("line_id"),
                                           scene_id=scene.get("scene_id")))
                elif duration and end > duration + 0.001:
                    defects.append(_defect("LINE_TIMING_INVALID", pointer,
                                           "line runs past the scene duration",
                                           line_id=line.get("line_id"),
                                           scene_id=scene.get("scene_id")))
    target = _num((foundation.get("constraints") or {}).get("duration_seconds"))
    if target and abs(total - target) > max(2.0, target * 0.1):
        defects.append(_defect("TOTAL_DURATION_DRIFT", "/scenes",
                               "authored durations do not fit the selected duration",
                               authored_total=round(total, 3), selected_total=target))

    line_ids = {ln.get("line_id") for _, _, ln in _all_lines(scenes)}
    cta_id = ((authored.get("cta") or {}).get("line_id"))
    cta_lines = [(i, ln) for i, _, ln in _all_lines(scenes)
                 if ln.get("role") == "cta" or (cta_id and ln.get("line_id") == cta_id)]
    cta_ids = {ln.get("line_id") for _, ln in cta_lines}
    if len(cta_ids) != 1:
        defects.append(_defect("CTA_COUNT", "/cta", "exactly one CTA line is required",
                               found=sorted(x for x in cta_ids if x)))
    if cta_id and cta_id not in line_ids:
        defects.append(_defect("CTA_UNBOUND", "/cta/line_id", "CTA names no authored line",
                               line_id=cta_id))

    solution = [i for i, s in enumerate(scenes)
                if isinstance(s, dict) and s.get("solution_introduced")]
    if not solution:
        defects.append(_defect("SOLUTION_MISSING", "/scenes", "no scene introduces the solution"))
    else:
        sol_index = solution[0]
        earned = [s for s in scenes[:sol_index] if isinstance(s, dict)
                  and s.get("turn_trigger") and s.get("consequential_choice")]
        if sol_index == 0 or not earned:
            defects.append(_defect("SOLUTION_UNEARNED", "/scenes/%d" % sol_index,
                                   "solution arrives before a consequential choice and turn",
                                   scene_id=scenes[sol_index].get("scene_id")))
        transformed = [i for i, s in enumerate(scenes)
                       if isinstance(s, dict) and i > sol_index and s.get("behavior_change")]
        if not transformed:
            defects.append(_defect("TRANSFORMATION_UNSHOWN", "/scenes",
                                   "no later scene shows changed behavior"))
        for index, _line in cta_lines:
            if index <= sol_index:
                defects.append(_defect("CTA_EARLY", "/cta",
                                       "CTA must follow the earned outcome",
                                       scene_id=scenes[index].get("scene_id")))

    derived = derive_lyric_lines(scenes)
    sheet = (authored.get("lyric_sheet") or {}).get("lines")
    if sheet is not None:
        if not isinstance(sheet, list):
            defects.append(_defect("LYRIC_SHEET_INVALID", "/lyric_sheet/lines"))
        else:
            sheet_keys = {(ln.get("line_id"), ln.get("character_id"), _norm(ln.get("text")))
                          for ln in sheet if isinstance(ln, dict)}
            derived_keys = {(ln["line_id"], ln["character_id"], _norm(ln["text"]))
                            for ln in derived["lines"]}
            for key in sorted(sheet_keys - derived_keys, key=str):
                defects.append(_defect("LYRIC_LINE_UNBOUND", "/lyric_sheet/lines",
                                       "sheet line has no scene performance line", line_id=key[0]))
            for key in sorted(derived_keys - sheet_keys, key=str):
                defects.append(_defect("LYRIC_LINE_MISSING", "/lyric_sheet/lines",
                                       "sung scene line absent from the sheet", line_id=key[0]))
    return defects


# --- immutable revisions --------------------------------------------------

class RevisionLog:
    """Append-only artifact revisions for one run. No IO, no persistence."""

    def __init__(self):
        self._rows = []

    def rows(self, kind=None):
        return [r for r in self._rows if kind is None or r["kind"] == kind]

    def find_by_key(self, idempotency_key):
        for row in self._rows:
            if row["idempotency_key"] == idempotency_key:
                return row
        return None

    def append(self, kind, payload, idempotency_key, dispatch_id):
        digest = _digest(payload)
        existing = self.find_by_key(idempotency_key)
        if existing and existing["kind"] == kind:
            if existing["digest"] != digest:
                raise WriterRefused("IDEMPOTENCY_CONFLICT",
                                    "same idempotency key, different payload",
                                    {"kind": kind, "line_id": None})
            return existing
        row = {
            "kind": kind,
            "artifact_id": kind,
            "revision": 1 + len(self.rows(kind)),
            "digest": digest,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "dispatch_id": dispatch_id,
        }
        self._rows.append(row)
        return row


# --- writing dispatch -----------------------------------------------------

def _build_artifacts(authored, foundation, dispatch_id):
    scenes = authored["scenes"]
    bound = {kind: {"revision": record["revision"], "digest": record["digest"]}
             for kind, record in foundation["artifacts"].items()}
    script = {
        "schema_version": SCHEMA_VERSION,
        "lineage": authored.get("lineage") or {"split": [], "merged": []},
        "scenes": scenes,
        "cta": authored.get("cta") or {},
        "bound_foundation": bound,
        "prompt_revision": PROMPT_REVISION,
        "dispatch_id": dispatch_id,
    }
    lyrics = derive_lyric_lines(scenes)
    lyrics.update({"bound_foundation": bound, "prompt_revision": PROMPT_REVISION,
                   "dispatch_id": dispatch_id,
                   "scene_plan_digest": foundation["artifacts"]["scene_plan"]["digest"]})
    return script, lyrics


def write(registry, dispatch, *, model_binding, constraints, ledger=None,
          max_attempts=MAX_ATTEMPTS):
    """Resolve the foundation, dispatch authoring, validate, and publish revisions."""
    if not callable(dispatch):
        raise WriterRefused("NO_DISPATCH", "script writing requires a model dispatch seam")
    foundation = build_foundation(registry)
    foundation["constraints"] = dict(constraints)
    ledger = ledger if ledger is not None else RevisionLog()

    requests, dispatches = [], []
    revision = None
    candidate = None
    last_signature = None
    authored = None
    attempts = 0

    while attempts < max_attempts:
        attempts += 1
        request = build_request(foundation, constraints, model_binding,
                                attempt=attempts, revision=revision)
        prior = ledger.find_by_key(request["idempotency_key"])
        if prior:
            script_row = next((r for r in ledger.rows("script")
                               if r["idempotency_key"] == prior["idempotency_key"]), prior)
            lyrics_row = next((r for r in ledger.rows("lyrics")
                               if r["dispatch_id"] == script_row["dispatch_id"]), None)
            if lyrics_row is None:
                raise WriterRefused("IDEMPOTENCY_CONFLICT",
                                    "replay found no matching lyrics revision")
            return {
                "foundation": foundation,
                "requests": requests,
                "dispatches": dispatches,
                "script": script_row,
                "lyrics": lyrics_row,
                "dispatch_count": len(dispatches),
                "idempotent_replay": True,
                "receipt": {"tool": TOOL_NAME, "replayed_revision": script_row["revision"]},
            }
        requests.append(request)
        response = dispatch(request)
        dispatches.append({"request": request, "response": response})
        candidate = parse_response(request, response)
        authored = candidate["authored"]
        defects = validate_authored(authored, foundation)
        if not defects:
            break
        signature = _digest([(d["code"], d.get("pointer")) for d in defects])
        if signature == last_signature:
            raise WriterRefused("UNPRODUCTIVE_REVISION",
                                "two unchanged attempts; change hypothesis/input or split safely",
                                {"defects": defects, "attempts": attempts,
                                 "requests": requests, "candidate": authored})
        last_signature = signature
        revision = {"defects": defects}
    else:
        defects = validate_authored(authored or {}, foundation)
        raise WriterRefused("WRITER_DEFECTS_REMAIN",
                            "authored candidate still has defects after %d attempts" % attempts,
                            {"defects": defects, "attempts": attempts,
                             "requests": requests, "candidate": authored})

    dispatch_id = candidate["dispatch"]["response_id"]
    script, lyrics = _build_artifacts(authored, foundation, dispatch_id)
    final_key = requests[-1]["idempotency_key"]
    script_row = ledger.append("script", script, final_key, dispatch_id)
    lyrics_row = ledger.append("lyrics", lyrics, final_key, dispatch_id)
    for kind, row in (("script", script_row), ("lyrics", lyrics_row)):
        registry.put(kind, row["payload"], revision=row["revision"], digest=row["digest"])

    receipt = {
        "tool": TOOL_NAME,
        "prompt_revision": PROMPT_REVISION,
        "foundation": foundation["artifacts"],
        "foundation_digest": foundation["digest"],
        "attempts": attempts,
        "requests": requests,
        "dispatches": [candidate["dispatch"]],
        "validation": {"defects": [], "checks": ["structural", "causal", "spoken_opening",
                                                "solution_earned", "transformation",
                                                "single_cta", "lyric_reconciliation"]},
        "artifacts": {"script": {"revision": script_row["revision"], "digest": script_row["digest"]},
                      "lyrics": {"revision": lyrics_row["revision"], "digest": lyrics_row["digest"]}},
        "spend": "none: authoring request recorded through the injected dispatch seam",
    }
    return {
        "foundation": foundation,
        "requests": requests,
        "dispatches": dispatches,
        "receipt": receipt,
        "script": script_row,
        "lyrics": lyrics_row,
        "dispatch_count": len(dispatches),
        "idempotent_replay": False,
    }


# --- no-spend fixture replay ---------------------------------------------

DEFAULT_FIXTURE = Path(os.path.dirname(os.path.abspath(__file__))) / "fixtures" / "rich_script.json"


def registry_from_foundation(payloads):
    registry = C.RunRegistry()
    for kind, payload in payloads.items():
        registry.put(kind, payload)
    return registry


def replay_fixture(record):
    """Replay the recorded request/response with no provider call and prove provenance."""
    registry = registry_from_foundation(record["foundation"])
    seen = []

    def dispatch(request):
        seen.append(request)
        return dict(record["response"])

    result = write(registry, dispatch, model_binding=record["model_binding"],
                   constraints=record["constraints"])
    if not seen:
        raise WriterRefused("FIXTURE_NOT_DISPATCHED", "fixture replay made no dispatch")
    if seen[0] != record["request"]:
        raise WriterRefused("FIXTURE_PROVENANCE_MISMATCH",
                            "rebuilt request differs from the recorded request",
                            {"expected": record["request"], "actual": seen[0]})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Script/lyric writing dispatch (S75-T10).")
    parser.add_argument("--check-fixture", nargs="?", const=str(DEFAULT_FIXTURE),
                        default=str(DEFAULT_FIXTURE),
                        help="replay the recorded no-spend fixture")
    args = parser.parse_args(argv)
    try:
        record = json.loads(Path(args.check_fixture).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": "fixture unreadable: %s" % exc}))
        return 2
    try:
        result = replay_fixture(record)
    except WriterRefused as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": str(exc),
                          "packet": exc.packet}, sort_keys=True))
        return 1
    print(json.dumps({
        "ok": True,
        "response_id": result["receipt"]["dispatches"][0]["response_id"],
        "script_revision": result["receipt"]["artifacts"]["script"]["revision"],
        "lyrics_revision": result["receipt"]["artifacts"]["lyrics"]["revision"],
        "dispatch_count": result["dispatch_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
