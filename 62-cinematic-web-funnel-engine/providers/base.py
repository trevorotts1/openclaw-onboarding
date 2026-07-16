#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base.py — provider-neutral media generation interface (Skill 62, U4).

Implements spec §10.1 (`MediaProvider`) and §10.2 (versioned, capability-keyed
model registry) plus ADR-7 ("Kie.ai is the default provider, not a hard
dependency in business logic") and ADR-8 ("Model slugs and prices resolve
from the live Kie registry at build time — never hardcoded").

Two things live here:

1. ``MediaProvider`` — an abstract base class every concrete provider adapter
   (``providers/kie.py``, a later unit) must implement. Callers only ever
   depend on this interface, never on a concrete provider's HTTP details.

2. ``ModelRegistry`` — a loader/resolver over ``providers/model-registry.json``.
   It is the ONLY place in this skill allowed to know a provider wire slug or
   a price. Every other script, prompt, or manifest addresses a model by its
   registry ``model_id`` (a capability-oriented id such as
   ``kie-bytedance-seedance-1.5-pro``) or by a named ``capability_tier``
   (such as ``draft_motion``) and asks the registry to resolve the current
   slug/price — it never embeds either value as a literal.

Nothing here calls a network API or reads a secret value. This is pure
interface + registry-resolution logic; ``providers/kie.py`` (a later unit)
is where HTTP calls to api.kie.ai live.

stdlib only.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = _SCRIPT_DIR / "model-registry.json"

# Fields spec §10.2 requires the registry to record per model, keyed by
# capability rather than marketing name. Enforced by ModelRegistry.validate().
_REQUIRED_MODEL_FIELDS: Tuple[str, ...] = (
    "model_id",
    "provider",
    "provider_model_slug",
    "status",
    "capabilities",
    "aspect_ratios",
    "output_resolutions",
    "duration_limits",
    "audio",
    "callback_support",
    "price",
    "verified_date",
)
_VALID_STATUSES: Tuple[str, ...] = ("active", "deprecated", "planned")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ModelRegistryError(Exception):
    """Base class for every registry-resolution failure. Fail-closed: callers
    must never fall back to a hardcoded slug or price when one of these is
    raised."""


class RegistryFileError(ModelRegistryError):
    """The registry file is missing, unreadable, or not valid JSON."""


class RegistrySchemaError(ModelRegistryError):
    """The registry file parsed as JSON but is missing a required field."""


class ModelNotFoundError(ModelRegistryError):
    """No model in the registry matches the requested model_id."""


class CapabilityTierNotFoundError(ModelRegistryError):
    """No capability_tier in the registry matches the requested tier name."""


class NoActiveCandidateError(ModelRegistryError):
    """A capability tier resolved to zero active, priced candidate models."""


class DeprecatedModelError(ModelRegistryError):
    """The requested model_id exists but is marked deprecated and the caller
    did not explicitly opt in to a deprecated resolution."""


class UnpricedModelError(ModelRegistryError):
    """The requested model_id has no verified, non-null price and the caller
    asked for a strict price resolution (the default) — see
    model-registry.json price.verified / price.amount semantics."""


class ProviderTaskError(Exception):
    """Raised by a MediaProvider implementation for provider-side task
    failures (submit/poll/download/cancel). Not a registry error."""


# ---------------------------------------------------------------------------
# Request / result data classes
#
# Every request below carries a registry `model_id` — never a raw provider
# slug. A MediaProvider implementation resolves the slug itself via
# ModelRegistry immediately before making its wire call.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssetUploadRequest:
    """A local file to make reachable to a provider (e.g. a reference image
    that must become a public URL before it can be used as generation
    input)."""

    path: str
    purpose: str  # e.g. "reference_image", "first_frame", "last_frame"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImageGenerationRequest:
    model_id: str  # registry id, e.g. "kie-gpt-image-2-text-to-image"
    prompt: str
    aspect_ratio: str = "16:9"
    resolution: str = "2K"
    output_format: str = "png"
    reference_image_urls: Tuple[str, ...] = field(default_factory=tuple)
    negative_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoGenerationRequest:
    model_id: str  # registry id, e.g. "kie-bytedance-seedance-1.5-pro"
    prompt: str
    duration_seconds: int
    aspect_ratio: str = "16:9"
    resolution: str = "720p"
    input_urls: Tuple[str, ...] = field(default_factory=tuple)  # 0-2 frame-pin images
    generate_audio: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskHandle:
    task_id: str
    provider: str
    model_id: str
    status: str  # e.g. "queued", "processing", "success", "failed", "cancelled"
    detail: Optional[str] = None


@dataclass(frozen=True)
class CostEstimate:
    """Returned by MediaProvider.estimate_cost(). Every field traces back to
    a registry snapshot so a downstream cost ledger (spec §10.4) can record
    exactly which registry state priced this call."""

    model_id: str
    provider_model_slug: str
    unit: str
    unit_price: Optional[float]
    quantity: float
    estimated_total: Optional[float]
    verified: bool
    registry_snapshot_id: str
    note: str = ""


# ---------------------------------------------------------------------------
# MediaProvider — spec §10.1 interface
# ---------------------------------------------------------------------------


class MediaProvider(ABC):
    """Provider-neutral media generation interface (spec §10.1, ADR-7).

    Concrete adapters (``providers/kie.py``, a later unit) implement this
    against one HTTP provider each. Business logic elsewhere in this skill
    depends only on this interface — never on a concrete adapter's request
    shapes, endpoints, or auth headers.
    """

    #: Provider identity, e.g. "kie". Concrete subclasses must set this.
    name: str = ""

    @abstractmethod
    def upload_asset(self, request: AssetUploadRequest) -> str:
        """Upload a local file and return a publicly reachable URL usable as
        generation input (e.g. a reference/frame-pin image)."""
        raise NotImplementedError

    @abstractmethod
    def generate_image(self, request: ImageGenerationRequest) -> TaskHandle:
        """Submit an image generation/edit job. Returns immediately with a
        TaskHandle; callers poll via get_task()."""
        raise NotImplementedError

    @abstractmethod
    def generate_video(self, request: VideoGenerationRequest) -> TaskHandle:
        """Submit a video generation job. Returns immediately with a
        TaskHandle; callers poll via get_task()."""
        raise NotImplementedError

    @abstractmethod
    def get_task(self, task_id: str) -> TaskHandle:
        """Query current status for a previously submitted task."""
        raise NotImplementedError

    @abstractmethod
    def cancel_task(self, task_id: str) -> bool:
        """Best-effort cancel. Returns True if the provider acknowledged
        cancellation, False otherwise (e.g. already terminal)."""
        raise NotImplementedError

    @abstractmethod
    def download_results(self, task_id: str, destination: str) -> List[str]:
        """Download a completed task's result file(s) to ``destination``.
        Returns the list of local paths written."""
        raise NotImplementedError

    @abstractmethod
    def estimate_cost(
        self, request: "ImageGenerationRequest | VideoGenerationRequest"
    ) -> CostEstimate:
        """Return a CostEstimate for a not-yet-submitted request, resolved
        through a ModelRegistry — never a hardcoded number in the adapter."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ModelRegistry — spec §10.2 versioned, capability-keyed registry
# ---------------------------------------------------------------------------


class ModelRegistry:
    """Loads and resolves ``providers/model-registry.json``.

    Design rule (ADR-8): this class is the ONLY place in the skill permitted
    to know a provider wire slug or a price. Every caller elsewhere resolves
    through here by ``model_id`` or ``capability_tier`` name — a literal
    slug or price string appearing anywhere else in this skill's Python is a
    defect.

    The registry is re-read from disk on every instantiation (no
    process-lifetime caching), so "resolve at build time" means: whatever is
    on disk in ``model-registry.json`` the moment a build/run starts is what
    gets resolved. ``snapshot_id`` is a sha256 of the raw file bytes at load
    time, so every resolution result can be traced to the exact registry
    state that produced it (for the cost ledger, spec §10.4).
    """

    def __init__(self, registry_path: "str | Path" = DEFAULT_REGISTRY_PATH) -> None:
        self.registry_path = Path(registry_path)
        self._raw_bytes = self._read_bytes(self.registry_path)
        self.snapshot_id = hashlib.sha256(self._raw_bytes).hexdigest()
        self.data = self._parse(self._raw_bytes, self.registry_path)
        self.validate()

    # -- loading -----------------------------------------------------------

    @staticmethod
    def _read_bytes(path: Path) -> bytes:
        if not path.exists():
            raise RegistryFileError(f"model registry not found at {path}")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise RegistryFileError(f"could not read model registry at {path}: {exc}") from exc

    @staticmethod
    def _parse(raw_bytes: bytes, path: Path) -> Dict[str, Any]:
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RegistryFileError(f"model registry at {path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise RegistrySchemaError(f"model registry at {path} must be a JSON object at top level")
        return data

    # -- validation ----------------------------------------------------------

    def validate(self) -> None:
        """Fail-closed schema validation. Raises RegistrySchemaError on any
        violation — a malformed registry must never resolve a partial or
        silently-wrong slug/price."""
        for key in ("registry_version", "models", "capability_tiers"):
            if key not in self.data:
                raise RegistrySchemaError(f"model registry missing required top-level key: {key}")

        models = self.data["models"]
        if not isinstance(models, list) or not models:
            raise RegistrySchemaError("model registry 'models' must be a non-empty array")

        seen_ids: set = set()
        for entry in models:
            if not isinstance(entry, dict):
                raise RegistrySchemaError(f"model registry entry is not an object: {entry!r}")
            missing = [f for f in _REQUIRED_MODEL_FIELDS if f not in entry]
            if missing:
                raise RegistrySchemaError(
                    f"model registry entry {entry.get('model_id', '<unknown>')!r} "
                    f"missing required field(s): {missing}"
                )
            model_id = entry["model_id"]
            if model_id in seen_ids:
                raise RegistrySchemaError(f"model registry has duplicate model_id: {model_id}")
            seen_ids.add(model_id)
            if entry["status"] not in _VALID_STATUSES:
                raise RegistrySchemaError(
                    f"model registry entry {model_id!r} has invalid status "
                    f"{entry['status']!r} (must be one of {_VALID_STATUSES})"
                )
            price = entry["price"]
            if not isinstance(price, dict) or "unit" not in price or "verified" not in price:
                raise RegistrySchemaError(
                    f"model registry entry {model_id!r} has a malformed price block "
                    "(must be an object with at least 'unit' and 'verified')"
                )
            if not isinstance(entry["capabilities"], list) or not entry["capabilities"]:
                raise RegistrySchemaError(
                    f"model registry entry {model_id!r} must declare a non-empty capabilities[] array"
                )

        tiers = self.data["capability_tiers"]
        if not isinstance(tiers, dict) or not tiers:
            raise RegistrySchemaError("model registry 'capability_tiers' must be a non-empty object")
        for tier_name, tier in tiers.items():
            if not isinstance(tier, dict) or "capability" not in tier or "candidates" not in tier:
                raise RegistrySchemaError(
                    f"capability_tier {tier_name!r} must declare 'capability' and 'candidates'"
                )
            if not isinstance(tier["candidates"], list) or not tier["candidates"]:
                raise RegistrySchemaError(
                    f"capability_tier {tier_name!r} must declare a non-empty candidates[] array"
                )
            unknown = [c for c in tier["candidates"] if c not in seen_ids]
            if unknown:
                raise RegistrySchemaError(
                    f"capability_tier {tier_name!r} references unknown model_id(s): {unknown}"
                )

    # -- lookup --------------------------------------------------------------

    def get_model(self, model_id: str) -> Dict[str, Any]:
        """Return the raw registry entry for ``model_id``. Raises
        ModelNotFoundError if absent."""
        for entry in self.data["models"]:
            if entry["model_id"] == model_id:
                return entry
        raise ModelNotFoundError(
            f"model_id {model_id!r} not found in registry {self.registry_path} "
            f"(snapshot {self.snapshot_id[:12]})"
        )

    def list_models(
        self,
        *,
        capability: Optional[str] = None,
        status: Optional[str] = "active",
    ) -> List[Dict[str, Any]]:
        """List registry entries, optionally filtered by capability tag and
        status (default: only 'active'). Pass status=None for every status."""
        out = []
        for entry in self.data["models"]:
            if status is not None and entry["status"] != status:
                continue
            if capability is not None and capability not in entry["capabilities"]:
                continue
            out.append(entry)
        return out

    @staticmethod
    def _is_priced(entry: Dict[str, Any]) -> bool:
        """True if `entry` has SOME resolvable, non-null price amount — a
        best-effort estimate is enough to pass this check. This is
        deliberately weaker than `verified`: it only guards against
        resolving a tier to a model with literally no price data at all
        (e.g. kie-bytedance-seedance-1.5-pro, whose Kie.ai doc page states
        pricing is not listed). Whether an amount must additionally be
        `verified` before an actual paid call is `price_for(strict=True)`'s
        job, not this one's — that stricter bar belongs to the budget gate
        (U7, AF-CWFE-PAID-GATE), not to mere tier candidate listing."""
        price = entry.get("price", {})
        if price.get("amount") is not None:
            return True
        by_res = price.get("amount_by_resolution")
        return bool(by_res)

    def resolve_tier(
        self,
        tier_name: str,
        *,
        include_deprecated: bool = False,
        require_priced: bool = True,
    ) -> List[Dict[str, Any]]:
        """Resolve a named capability_tier (e.g. "draft_motion") to its
        ordered list of eligible candidate model entries.

        Filters out deprecated candidates unless include_deprecated=True, and
        (by default) filters out candidates with no resolvable price amount
        at all (see `_is_priced`) — a tier resolving to zero eligible
        candidates raises NoActiveCandidateError rather than silently
        returning an unpriced or deprecated model. Passing a price's
        `verified` bar (confirmed against a live/official source, required
        before an actual paid call) is enforced separately by
        `price_for(strict=True)`.
        """
        tiers = self.data["capability_tiers"]
        if tier_name not in tiers:
            raise CapabilityTierNotFoundError(
                f"capability_tier {tier_name!r} not found in registry "
                f"(known tiers: {sorted(tiers.keys())})"
            )
        tier = tiers[tier_name]
        candidates = []
        for model_id in tier["candidates"]:
            entry = self.get_model(model_id)
            if not include_deprecated and entry["status"] == "deprecated":
                continue
            if require_priced and not self._is_priced(entry):
                continue
            candidates.append(entry)
        if not candidates:
            raise NoActiveCandidateError(
                f"capability_tier {tier_name!r} resolved to zero eligible candidates "
                f"(include_deprecated={include_deprecated}, require_priced={require_priced}); "
                "declared candidates were "
                f"{tier['candidates']} — check status/price.amount in model-registry.json"
            )
        return candidates

    def resolve_default(
        self,
        tier_name: str,
        *,
        include_deprecated: bool = False,
        require_priced: bool = True,
    ) -> Dict[str, Any]:
        """Convenience wrapper: resolve_tier() and return its first eligible
        candidate (registry declaration order is preference order)."""
        return self.resolve_tier(
            tier_name, include_deprecated=include_deprecated, require_priced=require_priced
        )[0]

    # -- slug / price accessors ------------------------------------------
    #
    # These are the ONLY sanctioned way anywhere in this skill to obtain a
    # provider wire slug or a price. A literal slug/price string in any other
    # module is a defect (ADR-8).

    def slug_for(self, model_id: str, *, allow_deprecated: bool = False) -> str:
        """Resolve the current provider wire slug for a registry model_id."""
        entry = self.get_model(model_id)
        if entry["status"] == "deprecated" and not allow_deprecated:
            raise DeprecatedModelError(
                f"model_id {model_id!r} is deprecated in the registry "
                f"(snapshot {self.snapshot_id[:12]}); pass allow_deprecated=True "
                "to resolve it anyway"
            )
        return entry["provider_model_slug"]

    def price_for(self, model_id: str, *, resolution: Optional[str] = None, strict: bool = True) -> Dict[str, Any]:
        """Resolve the price block for a registry model_id.

        If the model prices per-resolution (``price.amount_by_resolution``),
        pass ``resolution`` to select the specific tier's amount; otherwise
        ``price.amount`` is used directly.

        strict=True (default) raises UnpricedModelError when no verified,
        non-null amount can be resolved — callers that truly need to inspect
        an unpriced/unverified entry (e.g. to surface it to an operator, or
        to build a "resolve live price" preflight check) must pass
        strict=False.
        """
        entry = self.get_model(model_id)
        price = dict(entry["price"])
        amount = price.get("amount")
        if amount is None and "amount_by_resolution" in price:
            by_res = price["amount_by_resolution"]
            if resolution is not None and resolution in by_res:
                amount = by_res[resolution]
            elif resolution is None and len(by_res) == 1:
                amount = next(iter(by_res.values()))
        price["resolved_amount"] = amount
        if strict and (amount is None or not price.get("verified", False)):
            raise UnpricedModelError(
                f"model_id {model_id!r} has no verified price "
                f"(amount={amount!r}, verified={price.get('verified')!r}); "
                "the budget gate must resolve a live price before any paid call — "
                "pass strict=False to inspect this entry anyway. "
                f"Registry note: {price.get('note', '')}"
            )
        return price

    def estimate(
        self,
        model_id: str,
        quantity: float,
        *,
        resolution: Optional[str] = None,
        strict: bool = True,
    ) -> CostEstimate:
        """Build a CostEstimate for `quantity` units (images, or
        video-seconds/clips per the model's price.unit) of a registry
        model_id, stamped with this registry load's snapshot_id."""
        entry = self.get_model(model_id)
        try:
            price = self.price_for(model_id, resolution=resolution, strict=strict)
        except UnpricedModelError as exc:
            return CostEstimate(
                model_id=model_id,
                provider_model_slug=entry["provider_model_slug"],
                unit=entry["price"].get("unit", "unknown"),
                unit_price=None,
                quantity=quantity,
                estimated_total=None,
                verified=False,
                registry_snapshot_id=self.snapshot_id,
                note=str(exc),
            )
        unit_price = price.get("resolved_amount")
        total = None if unit_price is None else round(unit_price * quantity, 6)
        return CostEstimate(
            model_id=model_id,
            provider_model_slug=entry["provider_model_slug"],
            unit=price.get("unit", "unknown"),
            unit_price=unit_price,
            quantity=quantity,
            estimated_total=total,
            verified=bool(price.get("verified", False)),
            registry_snapshot_id=self.snapshot_id,
            note=price.get("note", ""),
        )
