"""capability_route.py: a route the picture provider cannot serve is refused (N-61, 3E.3).

Section 3E.3. The Shot Router is the same for any picture provider: KIE's GPT
image model (today the newest GPT-image entry in the image registry, or
``gpt-image-2-6/sunburst``) or Agnes. Capabilities are READ at run time by
``capabilities.py``; nothing about a provider is hard-coded here.

* **A provider that cannot take reference pictures cannot draw a known
  character.** The router refuses that provider for those frames with
  ``PROVIDER_CANNOT_HOLD_CHARACTER`` and asks the run owner. It never falls back
  to text-to-image.
* **The run owner's choices are never overridden.** The story-clip model, the
  picture provider and the quality mode are theirs. When a route is not
  possible under those choices, the router takes the closest route that is and
  records why; it never switches the provider or the model on its own.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

from .capabilities import (
    PROVIDER_CANNOT_HOLD_CHARACTER,
    PROVIDER_CAPABILITY_UNKNOWN,
    picture_capability,
    require_character_references,
)
from .common import ShotRouterError

#: Route -> how many reference pictures the shot's own faces need.
ROUTE_NEEDS_REFERENCES = {
    "one_picture": 1,
    "two_picture": 1,
    "lip_sync": 1,
    "merged": 1,
    "nine_picture": 9,
    "long_take": 9,
}


def provider_references(provider="kie-gpt-image", *, providers=None,
                        image_catalog=None):
    """The provider's reference capacity, read from its record (3E.3)."""
    record = picture_capability(provider, providers, image_catalog)
    return record, record.get("max_reference_images")


def check_provider(provider="kie-gpt-image", route="one_picture", *,
                   cast_present=True, providers=None, image_catalog=None):
    """Refuse a route the chosen picture provider cannot serve.

    ``provider``: the provider name (a ``picture-providers.json`` key) or a
    model id whose family names one. ``cast_present``: the frame shows a known
    character, the case that needs reference pictures.
    """
    need = ROUTE_NEEDS_REFERENCES.get(route or "one_picture", 1)
    if not cast_present:
        return {"ok": True, "need": 0, "detail": "no known character in frame"}
    try:
        record = require_character_references(provider, providers, image_catalog)
    except ShotRouterError as exc:
        if exc.code == PROVIDER_CANNOT_HOLD_CHARACTER:
            raise ShotRouterError(
                PROVIDER_CANNOT_HOLD_CHARACTER,
                "%s; the %s route needs %d reference picture(s) for a known "
                "character. It never falls back to text-to-image — ask the run "
                "owner for another picture provider."
                % (exc.message, route, need)) from exc
        raise
    except Exception as exc:  # absence of capability data is a refusal, not a guess
        raise ShotRouterError(
            PROVIDER_CAPABILITY_UNKNOWN,
            "the picture provider's capability record is unreadable (%s); the "
            "router cannot prove it can draw a known character" % exc) from exc
    capacity = record.get("max_reference_images")
    if isinstance(capacity, int) and not isinstance(capacity, bool) \
            and capacity < need:
        raise ShotRouterError(
            PROVIDER_CANNOT_HOLD_CHARACTER,
            "picture provider %r holds at most %d reference image(s); the %s "
            "route needs %d. Ask the run owner; never fall back to text-to-image."
            % (record.get("provider") or provider, capacity, route, need))
    return {"ok": True, "need": need, "max": capacity,
            "provider": record.get("provider"), "model": record.get("model"),
            "detail": "provider holds the references"}


def closest_route(route, *, story_clip_model, supported_routes,
                  provider="kie-gpt-image", providers=None, image_catalog=None,
                  cast_present=True):
    """The closest route the owner's choices allow, with the reason (3E.3)."""
    if route in supported_routes:
        try:
            check_provider(provider, route, cast_present=cast_present,
                           providers=providers, image_catalog=image_catalog)
            return {"route": route, "changed": False, "reason": None}
        except ShotRouterError as exc:
            if exc.code != PROVIDER_CANNOT_HOLD_CHARACTER:
                raise
    order = ("lip_sync", "two_picture", "nine_picture", "one_picture")
    if route in order:
        start = order.index(route)
        candidates = order[start + 1:] + order[:start]
    else:
        candidates = order
    for candidate in candidates:
        if candidate not in supported_routes:
            continue
        try:
            check_provider(provider, candidate, cast_present=cast_present,
                           providers=providers, image_catalog=image_catalog)
        except ShotRouterError:
            continue
        return {
            "route": candidate,
            "changed": True,
            "original": route,
            "reason": "%r is not possible under %s and the chosen picture "
                      "provider; %r is the closest route that is"
                      % (route, story_clip_model, candidate),
            "owner_choice_preserved": True,
        }
    raise ShotRouterError(
        "NO_ROUTE_UNDER_OWNER_CHOICES",
        "none of the four routes is possible under %s and the chosen picture "
        "provider; the run owner must choose again" % story_clip_model)


def capability_row(provider, route, *, cast_present=True, providers=None,
                   image_catalog=None):
    """The row written onto the run's record for one route's provider read."""
    need = (ROUTE_NEEDS_REFERENCES.get(route or "one_picture", 1)
            if cast_present else 0)
    try:
        record = picture_capability(provider, providers, image_catalog)
    except ShotRouterError:
        record = {}
    return {
        "route": route,
        "provider": record.get("provider") or provider,
        "model": record.get("model"),
        "reference_images_needed": need,
        "reference_images_max": record.get("max_reference_images"),
        "price_credits_per_image": record.get("price_credits_per_image"),
        "reads_registry_at_run_time": True,
    }
