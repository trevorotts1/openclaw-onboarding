"""S63 L1 - Agnes Image model resolver (build target for 63-agnes-image).

Implements spec 15 sections 1 and 3:
- Unpinned / generic image requests resolve to the DEFAULT image model
  agnes-image-2.5-flash.
- Explicit legacy pins of agnes-image-2.1-flash are preserved as legacy
  compatibility behavior; they are never silently rewritten.
- Similarly named TEXT (agnes-2.5-flash) and VIDEO (agnes-video-2.5-flash)
  model IDs are rejected by this IMAGE adapter, never mapped.
- Provenance is always reported: default | explicit_pin | explicit_alias.
  A stored config value whose provenance is unknown is reported as
  ambiguous rather than overwritten (section 3).

Companion changes: scripts/normalize_alias.py carries the same alias
policy, and models.json carries the matching launch_role metadata
("default" for 2.5, "legacy" for 2.1).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_IMAGE_MODEL = "agnes-image-2.5-flash"
LEGACY_IMAGE_MODEL = "agnes-image-2.1-flash"

# IDs that must never be accepted by the image adapter (spec section 1).
NON_IMAGE_MODEL_IDS = {
    "agnes-2.5-flash",        # text model
    "agnes-2.0-flash",        # text model (historical)
    "agnes-video-2.5-flash",  # video model
    "agnes-video-2.0-flash",  # video model (historical, being retired elsewhere)
}

_GENERIC_ALIASES = {
    "agnes image",
    "agnes image flash",
    "agnes-image-flash",
    "agnes image default",
    "agnes-image",
    "agnes-image-default",
}

_LEGACY_ALIASES = {
    "agnes image 2.1",
    "agnes image 2.1 flash",
    "agnes-image-21-flash",
    "agnes-image-2.1-flash",
    "agnes image legacy",
}

_DEFAULT_ALIASES = {
    "agnes image 2.5",
    "agnes image 2.5 flash",
    "agnes-image-25-flash",
    "agnes-image-2.5-flash",
}


class ResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class Resolution:
    model_id: str
    role: str          # "default" | "legacy"
    provenance: str    # "default" | "explicit_pin" | "explicit_alias" | "ambiguous"
    requested: str | None


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower())


def resolve_model(requested: str | None) -> Resolution:
    """Resolve a caller-supplied model request to a canonical image model ID.

    None / empty / generic alias -> default 2.5 (provenance=default, or
    explicit_alias for a generic alias the caller actually typed).
    Exact 2.5 or its aliases -> 2.5 (explicit_pin / explicit_alias).
    Exact 2.1 or its aliases -> 2.1 preserved (explicit_pin / explicit_alias).
    Text/video IDs and unknown agnes-image-* IDs -> ResolutionError.
    """
    if requested is None or not str(requested).strip():
        return Resolution(DEFAULT_IMAGE_MODEL, "default", "default", requested)
    raw = str(requested).strip()
    cleaned = _clean(raw)
    if cleaned in NON_IMAGE_MODEL_IDS:
        raise ResolutionError(
            f"'{raw}' is not an Agnes image model; the image adapter rejects "
            "text/video model IDs. Use agnes-image-2.5-flash (or an explicit "
            "legacy pin agnes-image-2.1-flash)."
        )
    if cleaned == DEFAULT_IMAGE_MODEL:
        return Resolution(DEFAULT_IMAGE_MODEL, "default", "explicit_pin", raw)
    if cleaned in _DEFAULT_ALIASES:
        return Resolution(DEFAULT_IMAGE_MODEL, "default", "explicit_alias", raw)
    if cleaned == LEGACY_IMAGE_MODEL:
        return Resolution(LEGACY_IMAGE_MODEL, "legacy", "explicit_pin", raw)
    if cleaned in _LEGACY_ALIASES:
        return Resolution(LEGACY_IMAGE_MODEL, "legacy", "explicit_alias", raw)
    if cleaned in _GENERIC_ALIASES:
        return Resolution(DEFAULT_IMAGE_MODEL, "default", "explicit_alias", raw)
    if cleaned.startswith("agnes-image"):
        raise ResolutionError(
            f"Unknown Agnes image model '{raw}'. Supported image models: "
            f"{DEFAULT_IMAGE_MODEL} (default), {LEGACY_IMAGE_MODEL} (legacy pin)."
        )
    raise ResolutionError(f"Unrecognized model request '{raw}' for the Agnes image adapter.")


def resolve_stored_config(value: str | None, provenance: str | None) -> Resolution:
    """Resolve a value found in an existing client config (spec section 3).

    An old generated default and an explicit client pin can hold the same
    string. Only provenance decides: 'generated_default' may be updated to
    the new default; 'explicit_pin' is preserved; missing provenance is
    reported ambiguous and must not be overwritten indiscriminately.
    """
    if provenance == "explicit_pin":
        return resolve_model(value)
    if provenance == "generated_default":
        # A generated default follows the current default regardless of the
        # stale string it was generated with.
        return Resolution(DEFAULT_IMAGE_MODEL, "default", "default", value)
    if provenance is None:
        base = resolve_model(value)
        return Resolution(base.model_id, base.role, "ambiguous", value)
    raise ResolutionError(f"Unknown provenance '{provenance}'.")


def registry_roles(models_json_path: str | Path) -> dict[str, str]:
    """Derive default/legacy role metadata from a models.json registry.

    models.json entries carry an explicit 'launch_role' field ('default'
    for 2.5, 'legacy' for 2.1). Roles are read from that field; the
    canonical-ID fallback only covers a registry that predates the field,
    so consumers never guess from list order.
    """
    entries = json.loads(Path(models_json_path).read_text(encoding="utf-8"))
    roles: dict[str, str] = {}
    for entry in entries:
        cid = entry.get("canonical_model_id")
        if cid == DEFAULT_IMAGE_MODEL:
            roles[cid] = entry.get("launch_role", "default")
        elif cid == LEGACY_IMAGE_MODEL:
            roles[cid] = entry.get("launch_role", "legacy")
    return roles
