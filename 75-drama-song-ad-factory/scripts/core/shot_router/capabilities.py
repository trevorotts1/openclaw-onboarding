"""capabilities.py: the Shot Router reads what the models can do (N-61, 3E.3).

Two capability sources, both data the run reads at run time -- never a model
table hard-coded in this file:

* The video registry (skill 67 ``models.json``), found through the ONE shared
  locator ``prompt_limits.find_catalogs()``. Start-plus-end support is derived
  from the entry's own ``control_fields`` and ``max_reference_images``: a model
  takes both pictures in ONE request only when it declares a first-frame field
  AND a last-frame field AND room for two reference images. H3 declares both
  fields but one image, so it is derived as NOT supporting both -- never assumed.
* A picture-provider capability record (``picture-providers.json`` beside this
  file), or the newest GPT-image entry of an image catalog when one is handed
  in. The record says whether the provider takes reference pictures and how many.
  A provider that cannot hold references cannot draw a known character; the
  router refuses it with ``PROVIDER_CANNOT_HOLD_CHARACTER`` and asks the owner.
  It never falls back to text-to-image.

The run owner's choices are read, never overridden. The lip-sync model is fixed
(OmniHuman 2.0) and is not a capability question.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from .common import ShotRouterError

HERE = Path(__file__).resolve().parent
PICTURE_PROVIDERS_PATH = HERE / "picture-providers.json"

#: The plan's own refusal codes, exposed as constants for callers that branch.
PROVIDER_CANNOT_HOLD_CHARACTER = "PROVIDER_CANNOT_HOLD_CHARACTER"
PROVIDER_CAPABILITY_UNKNOWN = "PICTURE_CAPABILITY_UNKNOWN"

#: The frame field names a registry entry uses for a start or an end picture.
FIRST_FRAME_FIELDS = frozenset({"first_frame", "first_frame_url",
                                "first_frame_image_url", "start_frame"})
LAST_FRAME_FIELDS = frozenset({"last_frame", "last_frame_url",
                               "last_frame_image_url", "end_frame"})

#: Capability keys this module emits; routes.py reads ``start_plus_end_in_one_request``.
CAPABILITY_KEYS = (
    "model",
    "tasks",
    "control_fields",
    "start_plus_end_in_one_request",
    "max_reference_images",
    "duration_window_seconds",
    "resolutions",
    "cap_status",
)


def _prompt_limits():
    """The shared catalog locator (core/prompt_limits.py), imported lazily."""
    core = HERE.parent
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    import prompt_limits
    return prompt_limits


def video_registry_path(explicit=None):
    """The skill 67 ``models.json`` path, or None when no catalog is installed."""
    if explicit:
        return str(explicit)
    env = os.environ.get("KIE_MODELS_JSON")
    if env:
        return env
    try:
        _audio, video = _prompt_limits().find_catalogs()
    except Exception:  # pragma: no cover - install without the skill 67 catalog
        return None
    return str(video) if video else None


def load_video_registry(path=None):
    """Load the video registry; returns ``{"entries": [...], "by_id": {...}}``.

    A missing or unreadable catalog is ``VIDEO_REGISTRY_MISSING`` (fail closed):
    the router will not guess what a model accepts.
    """
    resolved = video_registry_path(path)
    if not resolved or not Path(resolved).is_file():
        raise ShotRouterError(
            "VIDEO_REGISTRY_MISSING",
            "no skill 67 models.json found (looked via prompt_limits.find_catalogs, "
            "KIE_MODELS_JSON and the explicit path)",
        )
    try:
        doc = json.loads(Path(resolved).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShotRouterError("VIDEO_REGISTRY_INVALID",
                              "cannot read the video registry: %s" % exc)
    entries = doc.get("models") or doc.get("entries") or []
    by_id = {}
    for entry in entries:
        model = entry.get("canonical_model_id")
        if model:
            by_id[model] = entry
    return {"entries": entries, "by_id": by_id, "path": str(resolved)}


def _fields(entry):
    return set(entry.get("control_fields") or [])


def _frame_or_media_contradicts(entry):
    """The media line saying "first OR last" means one picture per request."""
    media = str(entry.get("max_media_refs") or "")
    return bool(re.search(r"first[_a-z]*frame[_a-z]*\b.*\bOR\b.*last[_a-z]*frame",
                          media, re.IGNORECASE))


def model_capability(entry):
    """One registry entry -> the capability dict the router reads."""
    if not isinstance(entry, dict):
        raise ShotRouterError("VIDEO_REGISTRY_INVALID", "entry must be an object")
    fields = _fields(entry)
    refs = entry.get("max_reference_images")
    has_first = bool(fields & FIRST_FRAME_FIELDS)
    has_last = bool(fields & LAST_FRAME_FIELDS)
    room_for_two = refs is None or (isinstance(refs, int) and not isinstance(refs, bool)
                                    and refs >= 2)
    start_plus_end = bool(
        has_first and has_last and room_for_two
        and not _frame_or_media_contradicts(entry)
    )
    return {
        "model": entry.get("canonical_model_id"),
        "tasks": list(entry.get("tasks") or []),
        "control_fields": sorted(fields),
        "start_plus_end_in_one_request": start_plus_end,
        "max_reference_images": refs,
        "duration_window_seconds": entry.get("duration_window_seconds"),
        "resolutions": list(entry.get("resolutions") or []),
        "cap_status": entry.get("cap_status"),
        "source_url": entry.get("source_url"),
    }


def video_capability_map(registry=None):
    """``{model_id: capability}`` for every model in the registry.

    ``routes.supports_start_plus_end`` consumes this map directly. A model the
    registry does not carry is absent, so a TWO-PICTURE shot on it takes the
    safe chained path.
    """
    reg = registry if isinstance(registry, dict) and "by_id" in registry else \
        load_video_registry(registry)
    return {model: model_capability(entry)
            for model, entry in (reg.get("by_id") or {}).items()}


def model_entry(model, registry=None):
    reg = registry if isinstance(registry, dict) and "by_id" in registry else \
        load_video_registry(registry)
    entry = (reg.get("by_id") or {}).get(model)
    if entry is None:
        raise ShotRouterError(
            "MODEL_NOT_IN_REGISTRY",
            "%r is not in the live video registry; the router never assumes what "
            "a model accepts" % (model,),
        )
    return entry


# ---------------------------------------------------------------- pictures

def load_picture_providers(path=None):
    resolved = Path(path) if path else PICTURE_PROVIDERS_PATH
    if not resolved.is_file():
        raise ShotRouterError("PICTURE_CAPABILITY_MISSING",
                              "no picture provider record at %s" % resolved)
    try:
        doc = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShotRouterError("PICTURE_CAPABILITY_INVALID",
                              "cannot read the picture provider record: %s" % exc)
    return doc.get("providers") or {}


def _version_key(text):
    """Sort key for a model id like ``gpt-image-2-6/sunburst``: (2, 6)."""
    nums = re.findall(r"\d+", str(text).split("/")[0])
    return tuple(int(n) for n in nums) or (0,)


def newest_in_family(catalog, family="gpt-image"):
    """Newest model id of a family in an image catalog doc, or None.

    ``catalog`` is a parsed skill-74 style catalog or a path to one. Entries may
    be a list under ``models``/``entries`` or a dict keyed by id. No family match
    is None; the caller decides, never a silent default.
    """
    if isinstance(catalog, (str, Path)):
        try:
            catalog = json.loads(Path(catalog).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ShotRouterError("IMAGE_CATALOG_INVALID",
                                  "cannot read the image catalog: %s" % exc)
    if not isinstance(catalog, dict):
        raise ShotRouterError("IMAGE_CATALOG_INVALID", "image catalog must be an object")
    rows = catalog.get("models") or catalog.get("entries") or []
    if isinstance(rows, dict):
        rows = [dict(v, id=k) if isinstance(v, dict) else {"id": k}
                for k, v in rows.items()]
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        model = row.get("canonical_model_id") or row.get("id") or row.get("model")
        fam = row.get("family") or ""
        if model and (family in str(fam) or family in str(model)):
            candidates.append(model)
    if not candidates:
        return None
    return max(candidates, key=_version_key)


def picture_capability(provider="kie-gpt-image", providers=None, image_catalog=None):
    """The capability record for the picture provider in use (3E.3).

    ``provider`` names a record in ``picture-providers.json``; the record's
    ``newest_in_registry`` flag lets an image catalog override its model with the
    newest GPT-image entry the catalog carries.
    """
    table = providers if isinstance(providers, dict) else load_picture_providers()
    record = table.get(provider)
    if record is None:
        # Accept a model id whose family names a provider record.
        for name, row in table.items():
            model = str(row.get("model") or "")
            if provider and (provider in model or provider in name):
                record = row
                provider = name
                break
    if record is None:
        raise ShotRouterError(
            "PICTURE_PROVIDER_UNKNOWN",
            "%r is not a picture provider record on file; add it to "
            "picture-providers.json, never guess its capabilities" % (provider,),
        )
    result = dict(record)
    result["provider"] = provider
    if image_catalog is not None:
        newer = newest_in_family(image_catalog, result.get("family") or "gpt-image")
        if newer and _version_key(newer) > _version_key(result.get("model")):
            result["model"] = newer
            result["resolved_by"] = "newest in the image registry"
    result["can_hold_character"] = bool(
        result.get("takes_reference_images")
        and isinstance(result.get("max_reference_images"), int)
        and result["max_reference_images"] >= 1
    )
    return result


def require_picture_provider(provider="kie-gpt-image", providers=None,
                             image_catalog=None):
    """Read and PROVE the picture provider can draw a known character.

    A provider that cannot take reference pictures is refused with
    ``PROVIDER_CANNOT_HOLD_CHARACTER`` before any picture is drawn; the router
    never falls back to text-to-image.
    """
    record = picture_capability(provider, providers, image_catalog)
    if not record["can_hold_character"]:
        raise ShotRouterError(
            PROVIDER_CANNOT_HOLD_CHARACTER,
            "picture provider %r takes no reference pictures, so it cannot hold a "
            "known character; ask the run owner, never fall back to text-to-image"
            % (record.get("provider"),),
        )
    return record


# --------------------------------------------------------------- aliases
# Stable, short names other modules in this package (and callers) use.

def resolve_video_registry(path=None):
    """Alias: load the live video registry."""
    return load_video_registry(path)


def resolve_image_registry(path=None):
    """The image catalog to read for the newest picture model, or None.

    Explicit path, else ``S75_IMAGE_CATALOG``. No catalog is not an error here:
    picture_capability() then uses its own record on file.
    """
    resolved = path or os.environ.get("S75_IMAGE_CATALOG")
    if resolved and Path(resolved).is_file():
        return str(resolved)
    return None


def video_capability(model, registry=None):
    """One model's capability dict, read from the registry."""
    return model_capability(model_entry(model, registry))


def video_capabilities(registry=None):
    """Every model's capability dict (routes.supports_start_plus_end reads this)."""
    return video_capability_map(registry)


def newest_image_model(catalog, family="gpt-image"):
    """The newest picture model of a family in an image catalog, or None."""
    return newest_in_family(catalog, family)


def require_character_references(provider="kie-gpt-image", providers=None,
                                 image_catalog=None):
    """Alias of require_picture_provider: a provider must hold references."""
    return require_picture_provider(provider, providers, image_catalog)


def picture_capability_known(provider="kie-gpt-image", providers=None,
                             image_catalog=None):
    """True when a capability record for the provider is on file; never guesses."""
    try:
        picture_capability(provider, providers, image_catalog)
    except ShotRouterError:
        return False
    return True
