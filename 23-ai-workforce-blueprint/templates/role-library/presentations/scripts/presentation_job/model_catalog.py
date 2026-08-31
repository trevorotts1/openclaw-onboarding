"""presentation_job/model_catalog.py -- FIX 13 live model catalog resolver.

THE ONE-SENTENCE PROBLEM THIS FIXES: literal image/text/vision model IDs were
hardcoded in pipeline code paths (build_deck.py MODEL_T2I/MODEL_I2I, the retired
render_deck.py APPROVED_MODELS/FALLBACK_MODEL with its dead `nano-banana-2`,
dispatcher.py DEEPSEEK_MODEL, and the image-path siblings prompt_gate.py /
kie_generate.py / workbook_builder.py), so a provider shipping a newer GPT-Image
version — or retiring a fallback — required editing pipeline code, and the three
copies had already begun to drift.

CONTRACT:
  * `model_catalog.json` (shipped beside this module) is the ONLY place a literal
    model ID for the presentations dept lives. Code paths resolve ALIASES:
        image.t2i / image.i2i / image.fallback   -- render class (P-STYLE-PREVIEW, P4-RENDER)
        text.strong / text.fast / text.judge     -- authoring/judge classes (FIX 7 router)
        vision.ocr                               -- vision+OCR class (P-TYPO-QC, P-IMAGE-QC)
    FIX 7 (model_router) and FIX 10 (gap analysis) consume these aliases; FIX 12
    consumes the per-model `unit_costs` blocks (null + status "cost_unknown" means
    preflight must fail closed for that model until a price is entered -- never
    assume free).
  * Operator bump: point PRESENTATION_MODEL_CATALOG_DIR at a directory holding a
    model_catalog.json (the live "bump the catalog's preferred image model" knob --
    the file is re-read whenever its mtime/size changes, so no code edit and no
    restart is needed). Without the env var, the shipped catalog resolves.
  * Fail-closed: a missing/unparseable catalog, an unknown alias, or an alias that
    resolves to a RETIRED id raises CatalogError. Silence is never an option --
    a wrong model id spends real money on real client jobs.
  * `prefer_latest` on an image alias + a `candidates` list: the resolver picks the
    candidate with the highest embedded version token (and refuses retired ones),
    so "prefer latest GPT-Image version" is catalog data, not code.
  * Rollback: PRESENTATION_MODEL_CATALOG=0 restores the exact pre-FIX-13 literals
    from the pinned ROLLBACK table below (single documented location; the ONLY
    remaining literal place, and it is dead unless the flag is set to 0).

No network here: the live provider `models` inventory belongs to FIX 9
(capacity.py probes / resource_profile.py); this module turns ALIAS -> ID from
versioned catalog data, and FIX 7's router intersects the result with the
FIX 9-detected inventory before any call is made.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

FLAG_ENV = "PRESENTATION_MODEL_CATALOG"
FLAG_DEFAULT = "1"
DIR_ENV = "PRESENTATION_MODEL_CATALOG_DIR"

#: Pre-FIX-13 literals, kept ONLY as the =0 rollback table. With the flag at its
#: default (1) nothing in the pipeline reads these; every value above in the
#: shipped catalog equals one of these so turning the flag off restores the
#: exact old behavior.
ROLLBACK_MODELS: Dict[str, str] = {
    "image.t2i": "gpt-image-2-text-to-image",
    "image.i2i": "gpt-image-2-image-to-image",
    # The rollback MUST reproduce old behavior EXACTLY, and the old
    # render_deck.py FALLBACK_MODEL literal was "nano-banana-2". That id is
    # retired in the live catalog (the =1 path can never resolve to it); the
    # =0 rollback restores the old string verbatim for parity, nothing else.
    "image.fallback": "nano-banana-2",
    "text.strong": "deepseek-v4-pro",
    "text.fast": "deepseek-v4-flash",
    "text.judge": "deepseek-v4-flash",
    "vision.ocr": "glm-ocr",
}

#: Aliases the dept code paths are allowed to request. Anything else is a
#: programming error and fails closed.
ALIASES = ("image.t2i", "image.i2i", "image.fallback",
           "text.strong", "text.fast", "text.judge", "vision.ocr")

SHIPPED_CATALOG = Path(__file__).resolve().parent / "model_catalog.json"


class CatalogError(RuntimeError):
    """Fail-closed catalog problem: missing file, bad JSON, unknown alias,
    retired target, or no live candidate. Never proceed on a guessed model id."""


def flag_enabled() -> bool:
    """True (default) = resolve through the catalog. PRESENTATION_MODEL_CATALOG=0
    = pre-FIX-13 rollback literals (documented single-line escape; reverts every
    dept code path to its old hardcoded value at once)."""
    return os.environ.get(FLAG_ENV, FLAG_DEFAULT) != "0"


def catalog_path() -> Path:
    """Active catalog file: override dir wins, shipped catalog otherwise."""
    env = os.environ.get(DIR_ENV)
    if env:
        return Path(env).expanduser() / "model_catalog.json"
    return SHIPPED_CATALOG


# Resolve-time cache keyed by (path, mtime_ns, size): an operator editing the
# override catalog takes effect on the next resolve, no restart, and a steady
# pipeline does not re-read the file on every slide.
_CACHE: Dict[Any, Any] = {"key": None, "doc": None}


def load_catalog(refresh: bool = False) -> Dict[str, Any]:
    path = catalog_path()
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError as exc:
        raise CatalogError(f"model catalog unreadable at {path}: {exc}") from exc
    if not refresh and _CACHE["key"] == key and _CACHE["doc"] is not None:
        return _CACHE["doc"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"model catalog unparseable at {path}: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("aliases"), dict):
        raise CatalogError(f"model catalog at {path} has no 'aliases' object")
    _CACHE["key"], _CACHE["doc"] = key, doc
    return doc


_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def _version_token(model_id: str) -> float:
    """Highest dotted-number token in an id, for prefer_latest ordering.
    'gpt-image-3-text-to-image' -> 3.0; 'gpt-image-2-0724' -> 724.0 is NOT wanted,
    so only the FIRST version run after the family name counts."""
    m = _VERSION_RE.search(model_id)
    if not m:
        return 0.0
    parts = m.group(1).split(".")
    try:
        return float(parts[0]) + (float(parts[1]) / 100.0 if len(parts) > 1 else 0.0)
    except ValueError:
        return 0.0


def resolve(alias: str, *, catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Full catalog entry for an alias (provider, model, unit_costs, ...).
    Fail-closed on unknown alias / retired resolution."""
    if not flag_enabled():
        if alias not in ALIASES:
            raise CatalogError(f"unknown model alias {alias!r}")
        rb_key = alias
        model = ROLLBACK_MODELS.get(rb_key)
        if model is None:
            raise CatalogError(f"rollback table has no entry for {alias!r}")
        return {"provider": "rollback", "model": model, "alias": alias,
                "source": f"{FLAG_ENV}=0 rollback literal"}
    doc = catalog or load_catalog()
    entry = doc.get("aliases", {}).get(alias)
    if not isinstance(entry, dict):
        raise CatalogError(
            f"model alias {alias!r} not present in catalog "
            f"({catalog_path()}); refusing to guess a model id")
    retired = set(doc.get("retired", {}) or {})
    candidates = [c for c in (entry.get("candidates") or []) if c not in retired]
    model = entry.get("model")
    if entry.get("prefer_latest") and candidates:
        model = max(candidates, key=_version_token)
    if model in retired:
        raise CatalogError(
            f"alias {alias!r} resolves to retired model id {model!r} "
            f"(catalog {catalog_path()}); bump the alias to a live id")
    if not isinstance(model, str) or not model.strip():
        raise CatalogError(f"alias {alias!r} has no live model id in catalog")
    out = dict(entry)
    out["model"] = model
    out["alias"] = alias
    out["source"] = str(catalog_path())
    return out


def resolve_alias(alias: str) -> Dict[str, Any]:
    """Name FIX 7's model_router.py and FIX 10's resource_profile.py look for
    first when they probe for the catalog; identical to resolve()."""
    return resolve(alias)


def model_id(alias: str) -> str:
    """The literal provider model id an alias resolves to. THIS is what the
    payload builders send; nothing upstream of it carries a literal."""
    return resolve(alias)["model"]


def rollback_literal(alias: str) -> Optional[str]:
    """Pre-FIX-13 literal for an alias (rollback/parity callers only)."""
    return ROLLBACK_MODELS.get(alias)


def image_mode_table() -> Dict[str, str]:
    """{MODEL_T2I: ..., MODEL_I2I: ...} shaped resolution used by the image-path
    modules; re-read on every call so a catalog bump changes the NEXT submit."""
    return {"MODEL_T2I": model_id("image.t2i"), "MODEL_I2I": model_id("image.i2i")}


def approved_image_models() -> List[str]:
    """The live approved-list for render-path model validation (t2i + i2i)."""
    return [model_id("image.t2i"), model_id("image.i2i")]
