#!/usr/bin/env python3
"""Capability router: directive 16 request -> Skill 67 models.json selection.

Directive sections 16.1-16.3 + 24.5 (model capability/pin validated before
submission). Stdlib only. No network, no secrets, no hardcoded model catalog:
the Skill 67 registry is READ at runtime from models.json (or --catalog /
$KIE_MODELS_JSON). The default catalog is resolved the way kie_dispatch
does: walk up from this file looking for 67-kie-video/models.json. Policy
tokens (capability names, task tags used for ranking) are routing vocabulary,
never catalog rows.

Contract:
- Planner asks CAPABILITIES (text-to-video, image-to-video, first/last frame
  control, multi-reference, character slot/reference ID, camera control,
  multi-shot, duration, resolution, aspect ratio, audio off/on, motion
  transfer, edit/repaint). Skill 67 catalog decides which model serves them.
- Silent-video default (16.2): when the request does not state audio, audio
  defaults to "disabled" so the master song stays the soundtrack. Models with
  always-on audio and no disable control are then ineligible; ask for
  audio "enabled" (diegetic sound) or "any" to unlock them.
- Explicit pin wins: a pinned canonical_model_id is honored exactly. If the
  pin cannot satisfy the request we PARK with a reason - never silently
  override the pin, never fall back (directive 16: architecture is
  model-agnostic; explicit model wins).
- Unmet capability parks with a reason, no model id. Undetermined catalog data
  (NOT_PUBLISHED / empty lists / no such field) never becomes support: it is
  reported as undetermined and, for capabilities, blocks selection
  (fail-closed); for constraints it warns only (a proven mismatch still blocks).
- Candidate races (16.3): >1 candidate requires a recorded, approved budget
  plan with ceiling and max_candidates. No cost plan, no fan-out. Candidate
  order is deterministic rank, never random; quality scoring happens at QC.

Exit codes (EXIT): ok 0, error 1, waiting 3, parked 4, rejected 5.
Output: single JSON object on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

TOOL_NAME = "video_router"
TOOL_VERSION = "1.0.0"
EXIT = {"ok": 0, "error": 1, "waiting": 3, "parked": 4, "rejected": 5}

#: Relative catalog candidates walked up from this file (kie_dispatch pattern).
CATALOG_RELS = (
    ("67-kie-video", "models.json"),
    ("scripts", "core", "67-kie-video", "models.json"),
    ("installer-registration", "helpers", "67-kie-video", "models.json"),
)
CATALOG_ENV_VAR = "KIE_MODELS_JSON"


def resolve_catalog(explicit=None):
    """Resolve Skill 67 models.json the way kie_dispatch.resolve_adapter does.

    explicit (already non-empty) -> env $KIE_MODELS_JSON -> walk up from this
    file for CATALOG_RELS. Returns a path string or None. Never a hard-coded
    user-home default.
    """
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get(CATALOG_ENV_VAR)
    if env and os.path.isfile(env):
        return env
    start = Path(__file__).resolve()
    for parent in (start,) + tuple(start.parents):
        for rel in CATALOG_RELS:
            cand = parent.joinpath(*rel)
            if cand.is_file():
                return str(cand)
    return None

# Capability vocabulary from directive 16.1 (normalized spellings only).
CAP_ALIASES = {
    "text_to_video": "text_to_video",
    "text_to_video_generation": "text_to_video",
    "image_to_video": "image_to_video",
    "image_to_video_generation": "image_to_video",
    "reference_to_video": "multi_reference",
    "first_last_frame": "first_last_frame",
    "first_last_frame_control": "first_last_frame",
    "first_and_last_frame_control": "first_last_frame",
    "first_last": "first_last_frame",
    "keyframe_interpolation": "first_last_frame",
    "multi_reference": "multi_reference",
    "multi_reference_control": "multi_reference",
    "multi_ref": "multi_reference",
    "character_slot": "character_slot",
    "character_slot_reference_id": "character_slot",
    "character_reference_id": "character_slot",
    "character_ids": "character_slot",
    "camera_control": "camera_control",
    "multi_shot": "multi_shot",
    "multishot": "multi_shot",
    "motion_transfer": "motion_transfer",
    "motion_control": "motion_transfer",
    "puppet_motion_transfer": "motion_transfer",
    "edit_repaint": "edit_repaint",
    "edit": "edit_repaint",
    "repaint": "edit_repaint",
    "video_editing": "edit_repaint",
    "video_edit": "edit_repaint",
    # Audio is a directive 16.1 capability but routes through the audio field.
    "audio_disabled": "@audio:disabled",
    "audio_off": "@audio:disabled",
    "audio_silent": "@audio:disabled",
    "audio_enabled": "@audio:enabled",
    "audio_on": "@audio:enabled",
    # Pure constraints: named capabilities that need a value, not a predicate.
    "duration": "@constraint:duration_seconds",
    "resolution": "@constraint:resolution",
    "aspect_ratio": "@constraint:aspect_ratio",
    "audio": "@constraint:audio",
}

CAPABILITY_TOKENS = tuple(sorted(
    k for k, v in CAP_ALIASES.items() if not v.startswith("@")))

FIRST_FRAME_FIELDS = frozenset({
    "first_frame", "first_frame_url", "first_frame_image_url"})
LAST_FRAME_FIELDS = frozenset({
    "last_frame", "last_frame_url", "last_frame_image_url"})
# control_fields that can turn provider audio off (silent-video default).
AUDIO_OFF_FIELDS = frozenset({
    "audio", "generate_audio", "generate_audio_switch", "audio_setting",
    "audio_url", "sound"})
AUDIO_MODES = ("disabled", "enabled", "any")


class CatalogError(Exception):
    pass


def _norm(value):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_",
                  str(value).strip().lower())).strip("_")


def load_catalog(path):
    """(dict, list): parse Skill 67 models.json; raise CatalogError fail-closed."""
    p = Path(os.path.expanduser(str(path)))
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogError(
            "catalog not readable at %s (%s); restore Skill 67 models.json "
            "or pass --catalog" % (p, exc.strerror or exc)) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise CatalogError("catalog at %s is not valid JSON: %s" % (p, exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise CatalogError("catalog at %s has no 'models' list" % p)
    models = [m for m in data["models"]
              if isinstance(m, dict) and m.get("active", True)]
    if not models:
        raise CatalogError("catalog at %s has no active models" % p)
    return data, models


def _catalog_provenance(data, models, path):
    return {
        "path": str(path),
        "schema_version": data.get("schema_version"),
        "verified_at": data.get("verified_at"),
        "active_model_count": len(models),
        "source": "read-at-runtime",
    }


def _house_band(data):
    pol = data.get("registry_policy") or {}
    band = pol.get("house_band_chars") or {}
    lo, hi = band.get("min"), band.get("max")
    if not isinstance(lo, int) or not isinstance(hi, int):
        return 5000, 19000  # only if the catalog itself omits the band
    return lo, hi


# ---------------------------------------------------------------- capabilities

def _ref_capacity(model):
    """int | None: published image-reference capacity; None = undetermined."""
    value = model.get("max_reference_images")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    refs = model.get("max_media_refs")
    if isinstance(refs, str) and refs.strip().lower().startswith("none"):
        return 0
    return None


def _native_audio(model):
    value = model.get("native_audio")
    if value is False or value is None:
        return False
    if value is True:
        return True
    return bool(str(value).strip())


def _capability(cap, model, req):
    """(ok, undetermined, detail) for one capability against one model."""
    fields = frozenset(model.get("control_fields") or ())
    tasks = frozenset(model.get("tasks") or ())
    if cap == "text_to_video":
        return ("text-to-video" in tasks, False, "task text-to-video")
    if cap == "image_to_video":
        return ("image-to-video" in tasks, False, "task image-to-video")
    if cap == "first_last_frame":
        have_first = bool(fields & FIRST_FRAME_FIELDS)
        have_last = bool(fields & LAST_FRAME_FIELDS)
        return (have_first and have_last, False,
                "control_fields first/last frame")
    if cap == "multi_reference":
        need = req.get("reference_images")
        if not isinstance(need, int) or need < 1:
            need = 2  # "multi" means at least two references
        capacity = _ref_capacity(model)
        if capacity is None:
            return (False, True,
                    "image-reference capacity NOT_PUBLISHED (undetermined)")
        return (capacity >= need, False,
                "max_reference_images=%s vs need=%s" % (capacity, need))
    if cap == "character_slot":
        return ("character_ids" in fields, False, "control_fields character_ids")
    if cap == "camera_control":
        # No model in the Skill 67 registry publishes a camera-control field.
        return (False, True,
                "camera_control not represented in Skill 67 catalog "
                "(undetermined support)")
    if cap == "multi_shot":
        return ("multi-shot" in tasks, False, "task multi-shot")
    if cap == "motion_transfer":
        return (bool(tasks & {"motion-control", "puppet-motion-transfer"}),
                False, "task motion-control/puppet-motion-transfer")
    if cap == "edit_repaint":
        return (bool(tasks & {"video-editing", "transformation",
                              "style-transfer", "style-repainting",
                              "video-to-video"}),
                False, "task video-editing/transformation/repaint")
    return (False, False, "unknown capability")  # unreachable: validated earlier


def _audio_ok(model, want):
    """(ok, detail) for the silent-video default / explicit audio ask."""
    has_native = _native_audio(model)
    fields = frozenset(model.get("control_fields") or ())
    can_disable = (not has_native) or bool(fields & AUDIO_OFF_FIELDS)
    if want == "disabled":
        if can_disable:
            return True, "audio can be silent"
        return False, ("native audio is always-on and no audio control field "
                       "can disable it (directive 16.2 silent default)")
    if want == "enabled":
        if has_native:
            return True, "native audio available"
        return False, "model produces no native audio"
    return True, "audio mode any"


def _duration_ok(model, want):
    """(ok, undetermined, detail) for duration_seconds against the window."""
    window = model.get("duration_window_seconds")
    if window is None:
        return True, True, "duration window not published (undetermined)"
    if isinstance(window, (list, tuple)) and len(window) == 2:
        try:
            lo, hi = float(window[0]), float(window[1])
        except (TypeError, ValueError):
            return True, True, "duration window unparsable (undetermined)"
        return (lo <= want <= hi, False,
                "window [%s,%s]" % (lo, hi))
    text = str(window).strip()
    if not text:
        return True, True, "duration window empty (undetermined)"
    rng = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", text)
    if rng:
        lo, hi = float(rng.group(1)), float(rng.group(2))
        ok = lo <= want <= hi
        if not ok and want == -1 and re.search(r"(^|\D)-1(\D|$)", text):
            ok = True  # "-1 auto" windows accept auto duration
        if not ok and want == 0 and "full length" in text.lower():
            ok = True
        return ok, False, "window %s" % text
    values = {float(v) for v in re.findall(r"\d+(?:\.\d+)?", text)}
    if not values:
        return True, True, "duration window unparsable (undetermined)"
    return (want in values, False, "discrete window %s" % text)


def _resolution_ok(model, want):
    """(ok, undetermined, detail) for a resolution ask."""
    entries = model.get("resolutions") or []
    if not entries:
        return True, True, "resolutions not published (undetermined)"
    token = re.sub(r"[^a-z0-9]", "", str(want).lower())
    for entry in entries:
        if token and token in re.sub(r"[^a-z0-9]", "", str(entry).lower()):
            return True, False, "resolutions %s" % entries
    return False, False, "resolution %s absent from %s" % (want, entries)


def _prompt_ok(model, want, house_max):
    """(ok, detail, warnings) for prompt_chars against the published cap."""
    warnings = []
    cap = model.get("vendor_hard_cap_chars")
    status = str(model.get("cap_status") or "")
    if isinstance(cap, int) and not isinstance(cap, bool):
        if want <= cap:
            return True, "cap %s (%s)" % (cap, status), warnings
        if status == "VERIFIED":
            return False, ("prompt %s exceeds VERIFIED cap %s"
                           % (want, cap)), warnings
        # OWNER_* observed caps warn, never hard-fail (cap_status_legend).
        warnings.append(
            "prompt %s exceeds %s cap %s (warn-only)"
            % (want, status or "observed", cap))
        return True, "cap %s (%s)" % (cap, status), warnings
    if want > house_max:
        warnings.append(
            "cap %s; prompt %s exceeds house band max %s - Skill 74 must "
            "confirm before dispatch" % (status or "unknown", want, house_max))
    return True, "cap %s" % (status or "unknown"), warnings


# --------------------------------------------------------------------- ranking

def _preferred_tags(caps, req):
    tags = []
    if "multi_shot" in caps:
        tags += ["multi-shot"]
    if "motion_transfer" in caps:
        tags += ["motion-control", "puppet-motion-transfer"]
    if "edit_repaint" in caps:
        tags += ["video-editing", "transformation",
                 "style-repainting", "style-transfer"]
    if "character_slot" in caps:
        tags += ["character-consistency", "multimodal-subject-driven"]
    if "multi_reference" in caps:
        tags += ["reference-to-video"]
    if "image_to_video" in caps:
        tags += ["image-to-video", "keyframe-interpolation",
                 "two-image-animation"]
    if "first_last_frame" in caps:
        tags += ["image-to-video", "keyframe-interpolation",
                 "two-image-animation", "transition"]
    if "text_to_video" in caps and not caps - {"text_to_video"}:
        tags += ["text-to-video"]
    duration = req.get("duration_seconds")
    if isinstance(duration, (int, float)) and duration > 15:
        tags += ["long-form-cinematic"]
    if req.get("prefer") == "fast":
        tags += ["fast-generation"]
    if str(req.get("resolution") or "").lower().startswith("2k"):
        tags += ["high-resolution-2k"]
    return tags


def _evaluate(model, caps, req, house_band):
    """(eligible, unmet[], undetermined[], warnings[], notes[]) for one model."""
    unmet, undetermined, warnings, notes = [], [], [], []
    for cap in sorted(caps):
        ok, und, detail = _capability(cap, model, req)
        if und:
            undetermined.append({"capability": cap, "detail": detail})
        elif not ok:
            unmet.append({"capability": cap, "detail": detail})
        else:
            notes.append("%s: %s" % (cap, detail))
    audio_mode = req.get("audio", "disabled")
    ok, detail = _audio_ok(model, audio_mode)
    if ok:
        notes.append("audio %s: %s" % (audio_mode, detail))
    else:
        unmet.append({"capability": "audio_" + audio_mode, "detail": detail})
    duration = req.get("duration_seconds")
    if isinstance(duration, (int, float)):
        ok, und, detail = _duration_ok(model, duration)
        if und:
            warnings.append("duration %s: %s" % (duration, detail))
        elif not ok:
            unmet.append({"capability": "duration",
                          "detail": "duration %ss outside %s"
                                    % (duration, detail)})
    resolution = req.get("resolution")
    if resolution:
        ok, und, detail = _resolution_ok(model, resolution)
        if und:
            warnings.append("resolution %s: %s" % (resolution, detail))
        elif not ok:
            unmet.append({"capability": "resolution", "detail": detail})
    if req.get("aspect_ratio"):
        warnings.append(
            "aspect_ratio %s: not represented in Skill 67 catalog "
            "(undetermined; verify at payload validation)"
            % req["aspect_ratio"])
    prompt = req.get("prompt_chars")
    if isinstance(prompt, int) and not isinstance(prompt, bool) and prompt >= 0:
        ok, detail, prompt_warnings = _prompt_ok(
            model, prompt, house_band[1])
        warnings.extend(prompt_warnings)
        if not ok:
            unmet.append({"capability": "prompt_chars", "detail": detail})
        else:
            notes.append("prompt: %s" % detail)
    # Fail-closed: a capability that is undetermined against this catalog
    # blocks selection exactly like a proven-unmet one. Duration/resolution
    # uncertainty only warns (they ride in `warnings`, not `undetermined`).
    return (not unmet and not undetermined), unmet, undetermined, warnings, notes


# ----------------------------------------------------------------------- route

def _reject(code, reason, extra=None):
    out = {"outcome": "rejected", "code": code, "reason": reason,
           "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    if extra:
        out.update(extra)
    return out


def _park(code, reason, catalog, unmet=None, undetermined=None, warnings=None):
    return {
        "outcome": "parked", "code": code, "reason": reason,
        "unmet": unmet or [], "undetermined": undetermined or [],
        "warnings": warnings or [], "catalog": catalog,
        "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
        "recovery": "adjust the capability request, or extend the Skill 67 "
                    "catalog with a verified model that serves it",
    }


def _parse_request(req):
    """(caps, audio_mode, audio_defaulted, errors) or (None, None, None, errors)."""
    errors = []
    tokens = req.get("capabilities", [])
    if isinstance(tokens, str):
        tokens = [tokens]
    if not isinstance(tokens, list):
        return None, None, False, ["capabilities must be a list"]
    caps, audio_mode, audio_defaulted = set(), None, False
    audio_explicit = req.get("audio")
    if audio_explicit is not None:
        if audio_explicit not in AUDIO_MODES:
            errors.append("audio must be one of %s" % (AUDIO_MODES,))
        else:
            audio_mode = audio_explicit
    for raw in tokens:
        if not isinstance(raw, str) or not raw.strip():
            errors.append("capability tokens must be non-empty strings")
            continue
        key = _norm(raw)
        alias = CAP_ALIASES.get(key)
        if alias is None:
            errors.append(
                "unknown capability %r; known capabilities: %s"
                % (raw, ", ".join(CAPABILITY_TOKENS)))
            continue
        if alias.startswith("@audio:"):
            want = alias.split(":", 1)[1]
            if audio_mode is not None and audio_mode != want:
                errors.append(
                    "audio capability conflict: request states both %r and %r"
                    % (audio_mode, want))
            audio_mode = want
        elif alias.startswith("@constraint:"):
            field = alias.split(":", 1)[1]
            if field == "audio":
                if audio_mode is None:
                    errors.append(
                        "capability 'audio' listed without audio= "
                        "(disabled|enabled|any)")
            elif not req.get(field):
                errors.append(
                    "capability %r listed without %s value" % (raw, field))
        else:
            caps.add(alias)
    if audio_mode is None:
        # Directive 16.2: silent by default; the master song is the soundtrack.
        audio_mode, audio_defaulted = "disabled", True
    return caps, audio_mode, audio_defaulted, errors


def route(req, catalog_path=None):
    """Route one capability request. Returns the JSON envelope (see module doc)."""
    if not isinstance(req, dict):
        return _reject("INVALID_REQUEST", "request must be a JSON object")
    caps, audio_mode, audio_defaulted, errors = _parse_request(req)
    for field in ("prompt_chars", "reference_images", "candidates"):
        value = req.get(field)
        if value is not None and (isinstance(value, bool)
                                  or not isinstance(value, int) or value < 0):
            errors.append("%s must be a non-negative integer" % field)
    if req.get("candidates") is not None and req["candidates"] < 1:
        errors.append("candidates must be >= 1")
    duration = req.get("duration_seconds")
    if duration is not None and (isinstance(duration, bool)
                                 or not isinstance(duration, (int, float))):
        errors.append("duration_seconds must be a number")
    pin = req.get("pin")
    if pin is not None and (not isinstance(pin, str) or not pin.strip()):
        errors.append("pin must be a non-empty canonical_model_id string")
    prefer = req.get("prefer")
    if prefer is not None and prefer not in ("fast",):
        errors.append("prefer must be 'fast' when present")
    if errors:
        return _reject("INVALID_REQUEST", "; ".join(errors))

    req = dict(req)
    req["audio"] = audio_mode
    path = resolve_catalog(catalog_path or req.get("catalog"))
    if path is None:
        return {"outcome": "error", "code": "CATALOG_UNAVAILABLE",
                "reason": ("no Skill 67 models.json found via --catalog, "
                           "request catalog, $KIE_MODELS_JSON, or walk-up "
                           "from %s" % __file__),
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                "recovery": "install Skill 67 (models.json) or pass --catalog"}
    try:
        data, models = load_catalog(path)
    except CatalogError as exc:
        return {"outcome": "error", "code": "CATALOG_UNAVAILABLE",
                "reason": str(exc), "tool": TOOL_NAME,
                "tool_version": TOOL_VERSION,
                "recovery": "install Skill 67 (models.json) or pass --catalog"}
    catalog = _catalog_provenance(data, models, path)
    house_band = _house_band(data)
    by_id = {m.get("canonical_model_id"): m for m in models}
    all_by_id = {}
    for m in (data.get("models") or []):
        if isinstance(m, dict) and m.get("canonical_model_id"):
            all_by_id[m["canonical_model_id"]] = m

    # Candidate-race gate (16.3): no recorded cost plan, no fan-out.
    want_candidates = req.get("candidates") or 1
    budget_plan = req.get("budget_plan")
    if want_candidates > 1:
        if not isinstance(budget_plan, dict):
            return _park(
                "RACE_REQUIRES_COST_PLAN",
                "candidate race of %s requires a recorded approved "
                "budget_plan (ceiling + max_candidates); directive 16.3 "
                "forbids silent expensive fan-out" % want_candidates,
                catalog)
        if budget_plan.get("approved") is not True:
            return _park(
                "RACE_NOT_APPROVED",
                "budget_plan.approved must be true for a candidate race "
                "(rule: user-approved expensive fan-out must be recorded)",
                catalog)
        ceiling = budget_plan.get("ceiling")
        if isinstance(ceiling, bool) or not isinstance(ceiling, int) or ceiling < 0:
            return _park(
                "RACE_BUDGET_UNDETERMINED",
                "budget_plan.ceiling must be a non-negative integer; "
                "unknown prices require a decision before dispatch",
                catalog)
        max_candidates = budget_plan.get("max_candidates")
        if (isinstance(max_candidates, bool)
                or not isinstance(max_candidates, int) or max_candidates < 1):
            return _park(
                "RACE_BUDGET_UNDETERMINED",
                "budget_plan.max_candidates must be a positive integer",
                catalog)
        if want_candidates > max_candidates:
            return _park(
                "RACE_EXCEEDS_BUDGET_PLAN",
                "requested %s candidates but budget_plan.max_candidates=%s"
                % (want_candidates, max_candidates),
                catalog)

    # Pin resolution: explicit model wins, and it is validated, never overridden.
    if pin:
        pinned = all_by_id.get(pin)
        if pinned is None or not pinned.get("active", True):
            return _park(
                "UNKNOWN_PIN",
                "pinned model %r is not an active Skill 67 catalog entry "
                "(no auto-latest for video; pins are honored exactly)"
                % pin,
                catalog)
        eligible, unmet, undetermined, warnings, notes = _evaluate(
            pinned, caps, req, house_band)
        if not eligible:
            problems = (
                ["%s (%s)" % (u["capability"], u["detail"]) for u in unmet]
                + ["%s (%s)" % (u["capability"], u["detail"])
                   for u in undetermined])
            return _park(
                "PIN_CAPABILITY_MISMATCH",
                "pinned model %r cannot satisfy the request: %s"
                % (pin, "; ".join(problems)),
                catalog, unmet=unmet, undetermined=undetermined,
                warnings=warnings)
        warnings.append(
            "explicit pin honored; ranking skipped (explicit model wins)")
        return {
            "outcome": "ok", "model_id": pin,
            "api_family": pinned.get("api_family"),
            "create_endpoint": pinned.get("create_endpoint"),
            "query_endpoint": pinned.get("query_endpoint"),
            "auth_env": pinned.get("auth_env"),
            "pinned": True, "audio": audio_mode,
            "audio_defaulted": audio_defaulted,
            "capabilities": sorted(caps),
            "candidates": [{"model_id": pin, "rank": 1, "pinned": True}],
            "warnings": warnings, "notes": notes, "catalog": catalog,
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
        }

    # Eligible set: proven-unmet capability blocks; undetermined capability
    # also blocks (fail-closed); constraints block only on proven mismatch.
    considered, eligible_rows = [], []
    for index, model in enumerate(models):
        model_id = model.get("canonical_model_id")
        ok, unmet, undetermined, warnings, notes = _evaluate(
            model, caps, req, house_band)
        row = {
            "model_id": model_id, "index": index, "eligible": ok,
            "unmet": unmet, "undetermined": undetermined,
            "warnings": warnings, "notes": notes,
            "tasks": list(model.get("tasks") or ()),
            "ref_capacity": _ref_capacity(model),
        }
        considered.append(row)
        if ok:
            eligible_rows.append((model, row))

    if not eligible_rows:
        total = len(models)
        detail = []
        for row in considered:
            for item in row["unmet"]:
                detail.append("%s: %s (%s)" % (
                    row["model_id"], item["capability"], item["detail"]))
        undet = sorted({
            item["capability"] for row in considered
            for item in row["undetermined"]})
        if undet:
            reason = (
                "no active catalog model can prove capability set %s; "
                "capabilities undetermined against this catalog: %s "
                "(%s models considered, none eligible - fail-closed park)"
                % (sorted(caps) or ["<none>"], undet, total))
        elif detail:
            reason = (
                "no active catalog model satisfies the request; first "
                "unmet rows: %s" % "; ".join(detail[:5]))
        else:
            reason = ("no active catalog model satisfies the request "
                      "(%s models considered)" % total)
        return _park("UNMET_CAPABILITY", reason, catalog,
                     unmet=[{"capability": c, "detail": reason}
                            for c in sorted(caps)] or
                            [{"capability": "constraints", "detail": reason}],
                     undetermined=[{"capability": c,
                                    "detail": "undetermined in catalog"}
                                   for c in undet])

    tags = _preferred_tags(caps, req)
    want_ref = req.get("reference_images")

    def sort_key(pair):
        model, row = pair
        tasks = set(row["tasks"])
        tag_miss = 0 if (not tags or tasks & set(tags)) else 1
        capacity = row["ref_capacity"] or 0
        ref_rank = -capacity if "multi_reference" in caps else 0
        return (tag_miss, ref_rank, row["index"])

    ranked = sorted(eligible_rows, key=sort_key)
    candidates = []
    for rank, (model, row) in enumerate(ranked, start=1):
        entry = {
            "model_id": model.get("canonical_model_id"),
            "rank": rank,
            "api_family": model.get("api_family"),
            "warnings": row["warnings"],
            "notes": row["notes"],
            "matched_tags": sorted(set(row["tasks"]) & set(tags)),
        }
        if rank == 1:
            entry["why"] = ("pin-free rank: preferred tags %s, then catalog "
                            "order (deterministic, never random)" % (tags or ["<none>"]))
        candidates.append(entry)
    selected = candidates[0]
    top_model = ranked[0][0]
    warnings = list(ranked[0][1]["warnings"])
    if audio_defaulted:
        warnings.append(
            "audio defaulted to 'disabled' (directive 16.2 silent-video "
            "default: master Suno song is the soundtrack)")
    if req.get("aspect_ratio"):
        warnings.append(
            "aspect_ratio %s is unverified against this catalog"
            % req["aspect_ratio"])
    race = None
    if want_candidates > 1:
        race = {
            "count": want_candidates,
            "ordered": [c["model_id"] for c in candidates[:want_candidates]],
            "budget_plan": budget_plan,
            "scoring": "deterministic rank (capability match, preferred tags, "
                       "reference capacity, catalog order); quality scoring "
                       "runs at QC, never random selection",
        }
        warnings.append(
            "candidate race of %s recorded against approved ceiling %s"
            % (want_candidates, budget_plan.get("ceiling")))

    out = {
        "outcome": "ok",
        "model_id": selected["model_id"],
        "api_family": top_model.get("api_family"),
        "create_endpoint": top_model.get("create_endpoint"),
        "query_endpoint": top_model.get("query_endpoint"),
        "auth_env": top_model.get("auth_env"),
        "pinned": False,
        "audio": audio_mode,
        "audio_defaulted": audio_defaulted,
        "capabilities": sorted(caps),
        "reference_images": want_ref,
        "duration_seconds": req.get("duration_seconds"),
        "resolution": req.get("resolution"),
        "aspect_ratio": req.get("aspect_ratio"),
        "prompt_chars": req.get("prompt_chars"),
        "candidates": candidates,
        "race": race,
        "warnings": warnings,
        "notes": ranked[0][1]["notes"],
        "catalog": catalog,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
    }
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Directive 16 capability router over Skill 67 models.json")
    parser.add_argument("--request", required=True,
                        help="capability request JSON file, or - for stdin")
    parser.add_argument("--catalog", default=None,
                        help="path to Skill 67 models.json "
                             "(default: walk-up for 67-kie-video/models.json "
                             "or $KIE_MODELS_JSON)")
    args = parser.parse_args(argv)
    try:
        if args.request == "-":
            req = json.load(sys.stdin)
        else:
            req = json.loads(Path(args.request).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        payload = _reject("INVALID_REQUEST", "cannot read request: %s" % exc)
        print(json.dumps(payload, sort_keys=True))
        return EXIT["rejected"]
    payload = route(req, catalog_path=args.catalog)
    print(json.dumps(payload, sort_keys=True))
    return EXIT.get(payload.get("outcome"), EXIT["error"])


if __name__ == "__main__":
    sys.exit(main())
