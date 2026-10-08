#!/usr/bin/env python3
"""Suno extend-to-exact-length: top a short take up to exact seconds.

Owner unit BO-AUDIO2-U3, owned output ``core/audio_c3/extend/``. stdlib only.

Source of truth is the reference receipt's honest deviation line
(``qualification/hybrid-one-check-chanel/five/final/
hybrid-occ-5min-rnb-flow.receipt.md``)::

    The Suno take is 282 s; the same song was extended with the Suno extend
    route (instrumental outro) to 300 s

Rules implemented here:

1. **Extend path tops up to the exact target.** A take short of the target
   is sent through the Suno extend route (catalog id ``suno-extend``, route
   and endpoint read from the work copy at ``onboarding/68-kie-audio/
   models.json``) until the produced audio reaches the target, then fitted
   so the delivered length *is* the target to the second. A take already at
   or above the target never calls extend.
2. **Extend has no duration field** (work copy, ``known_inconsistencies``:
   "No duration field exists on extend; extension length is implicit and
   continueAt marks the start point"). So exactness cannot be requested -
   it must be *measured back*: ``top_up`` takes an injected
   ``extend_fn(payload) -> produced`` callable, measures what came back and
   re-extends or fits. The module carries no transport of its own.
3. **Fits both ways.** Produced within ``EXACT_TOL_S`` of the target counts
   as exact; produced past the target is trimmed to it (``trimmed_s``);
   produced short re-extends until ``MAX_EXTEND_ROUNDS`` runs out, then
   fails closed as ``extend-unresolved`` - never a short master shipped.
4. **Timing map spans the full length.** One contiguous map from ``0.0`` to
   the target: the original take segment, then one segment per extend
   round, with the last segment fitted so the map ends on the target. A
   map whose segments do not total the length is refused.
5. **continue_at sits strictly inside the source** (KIE: ``continueAt > 0
   and < total duration``), so every round overlaps the source by
   ``OVERLAP_S`` instead of starting at the very end.

Deliberate scope (ponytail): the envelope built here is the ``audio_id``
form of the current createTask route. The catalog's ``route_models.current``
also lists ``ai-music-api/upload-and-extend-audio`` (the ``upload_url``
form for a source file URL); add it when a caller has a file URL and no
task audio id. The catalog carries no ``model_default`` for ``suno-extend``,
so the default version is pinned to ``DEFAULT_EXTEND_VERSION`` (V6, the
version the reference receipt used) and every version is checked against
the catalog's ``model_enum``.

Out of scope: beat pacing, shot grids and the generation split belong to
``core/length_engine/long`` (unit V2B-EXTEND-R-U2); this package owns only
the extend-to-exact step and the segment map over it.

Run: python3 core/audio_c3/extend/test_extend.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SCHEMA_VERSION = "blackceo.audio-c3/suno-extend/v1"
TOOL_VERSION = "0.1.0"
EXIT = {"ok": 0, "error": 1, "rejected": 4}

EXTEND_CATALOG_ID = "suno-extend"

#: Catalog entry suno-extend has no ``model_default`` (checked 2026-10-07),
#: so the default is pinned here - V6, the version the reference receipt used
#: - and validated against the catalog's ``model_enum`` on every build.
DEFAULT_EXTEND_VERSION = "V6"

#: Reference receipt took one round (282 -> 300 s). The cap is a ceiling
#: for takes that come back short; exhaustion fails closed, never ships short.
MAX_EXTEND_ROUNDS = 4

#: Overlap of every extend round into its source (KIE continueAt must be
#: strictly greater than 0 and strictly less than the source duration).
OVERLAP_S = 1.0

#: A difference no larger than this is assembly fit, not a length error.
#: One frame at 30 fps is ~0.033 s; 0.05 s keeps a whole frame of slack.
EXACT_TOL_S = 0.05

#: A round that moves the take forward by less than this is no progress.
MIN_PROGRESS_S = 0.001


class ExtendError(ValueError):
    """Invalid input, invalid envelope, or a map that does not reach length."""


def _seconds(v, name):
    """A finite, strictly positive number of seconds."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ExtendError("%s: not a number (%r)" % (name, v))
    v = float(v)
    if not math.isfinite(v) or v <= 0.0:
        raise ExtendError("%s: must be greater than 0, got %r" % (name, v))
    return v


def _text(v, name):
    if not isinstance(v, str) or not v.strip():
        raise ExtendError("%s: non-empty string required" % name)
    return v


# --- the work-copy catalog (route, endpoint, versions) ---------------------
_CATS = {}


def _catalog_path(catalog_path=None):
    if catalog_path is not None:
        return Path(catalog_path)
    # core/audio_c3/extend/suno_extend.py -> repo root
    return Path(__file__).resolve().parents[3] / "onboarding" / "68-kie-audio" / "models.json"


def catalog(catalog_path=None):
    """canonical_model_id -> entry, read from the work copy. Never hardcoded."""
    p = _catalog_path(catalog_path)
    key = str(p)
    if key not in _CATS:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ExtendError("catalog-missing: %s" % p) from None
        except (ValueError, OSError) as e:
            raise ExtendError("catalog-unreadable: %s: %s" % (p, e)) from None
        if not isinstance(doc, dict):
            raise ExtendError("catalog-unreadable: %s: not an object" % p)
        _CATS[key] = {
            e.get("canonical_model_id"): e
            for e in doc.get("entries", [])
            if isinstance(e, dict) and e.get("canonical_model_id")
        }
    return _CATS[key]


def _entry(catalog_id, catalog_path=None):
    ent = catalog(catalog_path).get(catalog_id)
    if not isinstance(ent, dict):
        raise ExtendError("catalog-entry-missing: %s" % catalog_id)
    return ent


def route_model(catalog_id=EXTEND_CATALOG_ID, catalog_path=None):
    """Current-route id, first token of route_models.current (work copy)."""
    cur = _entry(catalog_id, catalog_path).get("route_models", {}).get("current")
    if not isinstance(cur, str) or not cur.strip():
        raise ExtendError("catalog-route-missing: %s" % catalog_id)
    return cur.split()[0]


def endpoint(catalog_id=EXTEND_CATALOG_ID, catalog_path=None):
    """createTask endpoint, read from the work copy, never hardcoded."""
    ep = _entry(catalog_id, catalog_path).get("route_models", {}).get(
        "current_endpoint")
    if not isinstance(ep, str) or not ep.strip():
        raise ExtendError("catalog-endpoint-missing: %s" % catalog_id)
    return ep


def version_enum(catalog_id=EXTEND_CATALOG_ID, catalog_path=None):
    enum = _entry(catalog_id, catalog_path).get("model_enum")
    if not isinstance(enum, (list, tuple)) or not enum:
        raise ExtendError("catalog-enum-missing: %s" % catalog_id)
    return tuple(enum)


def _checked_version(version, catalog_id=EXTEND_CATALOG_ID, catalog_path=None):
    v = DEFAULT_EXTEND_VERSION if version is None else version
    if not isinstance(v, str) or not v:
        raise ExtendError("version: non-empty string required (%r)" % (version,))
    if v not in version_enum(catalog_id, catalog_path):
        raise ExtendError(
            "unknown-version: %r not in %s enum %s"
            % (v, catalog_id, list(version_enum(catalog_id, catalog_path)))
        )
    return v


# --- the extend envelope ---------------------------------------------------
def build_extend_request(audio_id, continue_at, source_duration_s, callback_url,
                         version=None, title=None, prompt=None, style=None,
                         vocal_gender=None, instrumental=True,
                         catalog_path=None):
    """Current createTask envelope for one Suno extend round.

    ``instrumental=True`` (the reference's instrumental-outro top-up) is
    combined with neither ``prompt`` nor ``vocal_gender``: the catalog
    records both as prohibited under ``instrumental_true_prohibits``.

    No ``duration`` key exists on extend - length is implicit and comes back
    measured. The caller measures it through the injected ``extend_fn``.
    """
    audio_id = _text(audio_id, "audio_id")
    callback_url = _text(callback_url, "callback_url")
    ca = _seconds(continue_at, "continue_at")
    src = _seconds(source_duration_s, "source_duration_s")
    if not ca < src:
        raise ExtendError(
            "continue-at-outside-source: %.3f not < %.3f" % (ca, src)
        )
    if instrumental and (prompt is not None or vocal_gender is not None):
        raise ExtendError(
            "instrumental-prohibits-prompt-and-vocal-gender: extend "
            "instrumental=true cannot carry prompt or vocal_gender"
        )
    ver = _checked_version(version, catalog_path=catalog_path)
    req = {
        "endpoint": endpoint(catalog_path=catalog_path),
        "model": route_model(catalog_path=catalog_path),
        "callBackUrl": callback_url,
        "input": {
            "audio_id": audio_id,
            "model": ver,
            "continue_at": ca,
            "instrumental": bool(instrumental),
        },
    }
    if title is not None:
        req["input"]["title"] = _text(title, "title")
    if prompt is not None:
        req["input"]["prompt"] = _text(prompt, "prompt")
    if style is not None:
        req["input"]["style"] = _text(style, "style")
    if vocal_gender is not None:
        if vocal_gender not in ("m", "f"):
            raise ExtendError("vocal_gender: expected 'm' or 'f' (%r)" % (vocal_gender,))
        req["input"]["vocal_gender"] = vocal_gender
    return req


# --- timing map ------------------------------------------------------------
def timing_map(segments, length_s):
    """One contiguous map spanning ``0.0 .. length_s`` from ordered segments.

    ``segments`` is an ordered sequence of ``(label, duration_s)``. Chaining
    is by construction (each segment starts where the last ended); the sum
    must land on ``length_s`` within ``EXACT_TOL_S`` or the map is refused,
    because a map that does not reach the length is not a timing map. The
    final segment is fitted so the map ends on ``length_s`` exactly.
    """
    length = _seconds(length_s, "length_s")
    if isinstance(segments, (str, bytes)) or not hasattr(segments, "__iter__"):
        raise ExtendError("segments: ordered sequence required")
    parts = list(segments)
    if not parts:
        raise ExtendError("segments: at least one segment required")

    parsed = []
    for i, seg in enumerate(parts):
        if isinstance(seg, dict):
            label, dur = seg.get("label", ""), seg.get("duration_s")
        elif isinstance(seg, (list, tuple)) and len(seg) == 2:
            label, dur = seg[0], seg[1]
        else:
            raise ExtendError("segments[%d]: need (label, duration_s)" % i)
        parsed.append((str(label), _seconds(dur, "segments[%d].duration_s" % i)))

    total = sum(d for _, d in parsed)
    if abs(total - length) > EXACT_TOL_S:
        raise ExtendError(
            "timing-map-length: segments total %.3f s, length %.3f s"
            % (total, length)
        )

    out, cursor = [], 0.0
    last = len(parsed) - 1
    for i, (label, dur) in enumerate(parsed):
        start = round(cursor, 3)
        if i == last:
            end = float(length)
        else:
            cursor += dur
            end = round(cursor, 3)
        if end <= start:
            raise ExtendError(
                "segments[%d]: non-positive span %.3f..%.3f" % (i, start, end)
            )
        out.append({
            "index": i,
            "label": label,
            "start_s": start,
            "end_s": end,
            "duration_s": round(end - start, 3),
        })
        cursor = end
    if out[-1]["end_s"] != float(length):
        raise ExtendError("timing-map-length: does not end at %.3f" % length)
    return {
        "length_s": length,
        "span_start_s": out[0]["start_s"],
        "span_end_s": out[-1]["end_s"],
        "segment_count": len(out),
        "segments": out,
    }


# --- plan ------------------------------------------------------------------
def plan_extend(take_s, target_s, audio_id, callback_url,
                overlap_s=OVERLAP_S, max_rounds=MAX_EXTEND_ROUNDS,
                version=None, title=None, prompt=None, style=None,
                vocal_gender=None, instrumental=True, catalog_path=None):
    """Decide and price one top-up: ``none`` (take is long enough) or
    ``extend`` (first-round payload plus the planned timing map).

    A take within ``EXACT_TOL_S`` of the target is already long enough -
    assembly fits those few milliseconds; extend is not spent on them. The
    measured shortfall is still reported in ``under_by_s`` / ``shortfall_s``
    so the plan never overstates what it has.
    """
    take = _seconds(take_s, "take_s")
    target = _seconds(target_s, "target_s")
    _text(audio_id, "audio_id")
    _text(callback_url, "callback_url")
    ov = _seconds(overlap_s, "overlap_s")
    if ov >= take:
        raise ExtendError("overlap: %.3f not < take %.3f" % (ov, take))
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
        raise ExtendError("max_rounds: positive integer required (%r)" % (max_rounds,))

    over = take - target
    if over >= -EXACT_TOL_S:
        return {
            "action": "none",
            "reason": "take-at-or-above-target",
            "take_s": take,
            "target_s": target,
            "over_by_s": round(max(0.0, over), 3),
            "under_by_s": round(max(0.0, -over), 3),
            "extend_rounds": 0,
            "max_rounds": max_rounds,
            "payload": None,
            "timing_map": timing_map([("take", target)], target),
        }

    shortfall = target - take
    ca = take - ov
    payload = build_extend_request(
        audio_id=audio_id, continue_at=ca, source_duration_s=take,
        callback_url=callback_url, version=version, title=title, prompt=prompt,
        style=style, vocal_gender=vocal_gender, instrumental=instrumental,
        catalog_path=catalog_path,
    )
    return {
        "action": "extend",
        "reason": "take-short-of-target",
        "route": payload["model"],
        "endpoint": payload["endpoint"],
        "take_s": take,
        "target_s": target,
        "shortfall_s": round(shortfall, 3),
        "over_by_s": 0.0,
        "under_by_s": round(shortfall, 3),
        "continue_at_s": round(ca, 3),
        "overlap_s": ov,
        "extend_rounds": 0,
        "max_rounds": max_rounds,
        "payload": payload,
        "timing_map": timing_map(
            [("take", take), ("extend-top-up", shortfall)], target
        ),
    }


def _normalize_produced(out, round_no):
    """Extend result -> (produced seconds, next audio id or None).

    The injected callable may return a bare number (tests and simple
    fixtures) or a callback-shaped dict carrying ``duration``/``duration_s``
    and ``id``/``audio_id``.
    """
    if isinstance(out, bool):
        raise ExtendError("extend round %d: not a duration (%r)" % (round_no, out))
    if isinstance(out, (int, float)):
        return _seconds(out, "round %d produced_s" % round_no), None
    if isinstance(out, dict):
        dur = out.get("duration_s", out.get("duration"))
        if dur is None:
            raise ExtendError("extend round %d: no duration in result" % round_no)
        nxt = out.get("audio_id") or out.get("id")
        if nxt is not None:
            nxt = _text(nxt, "round %d audio_id" % round_no)
        return _seconds(dur, "round %d produced_s" % round_no), nxt
    raise ExtendError("extend round %d: unusable result %r" % (round_no, out))


# --- the top-up driver -----------------------------------------------------
def top_up(take_s, target_s, extend_fn, audio_id, callback_url,
           overlap_s=OVERLAP_S, max_rounds=MAX_EXTEND_ROUNDS,
           version=None, title=None, prompt=None, style=None,
           vocal_gender=None, instrumental=True, catalog_path=None):
    """Drive Suno extend until the take is exactly the target length.

    ``extend_fn`` is the only call path - the injected stand-in for the
    dispatch transport (scripted in tests, so zero paid calls). Returns a
    record with ``status``:

    * ``ok`` - ``delivered_s == target_s``; ``extend_rounds`` is how many
      rounds it took (0 when the take was already long enough), ``trimmed_s``
      the seconds over the target that assembly must cut (an extend overshoot
      or a take that was already too long), ``timing_map`` contiguous to the
      target;
    * ``extend-unresolved`` / ``extend-no-progress`` /
      ``extend-no-audio-id`` - fail closed, no ``delivered_s`` and no
      timing map, because a map that does not reach the length is refused.
    """
    if not callable(extend_fn):
        raise ExtendError("extend_fn: callable required")
    plan = plan_extend(
        take_s, target_s, audio_id=audio_id, callback_url=callback_url,
        overlap_s=overlap_s, max_rounds=max_rounds, version=version,
        title=title, prompt=prompt, style=style, vocal_gender=vocal_gender,
        instrumental=instrumental, catalog_path=catalog_path,
    )
    take, target = plan["take_s"], plan["target_s"]
    base = {"take_s": take, "target_s": target}

    if plan["action"] == "none":
        return dict(base, **{
            "status": "ok",
            "action": "none",
            "reason": plan["reason"],
            "extend_rounds": 0,
            "delivered_s": target,
            "extended_s": 0.0,
            "trimmed_s": plan["over_by_s"],
            "under_by_s": plan["under_by_s"],
            "history": [],
            "timing_map": plan["timing_map"],
        })

    ov = plan["overlap_s"]
    current_audio = plan["payload"]["input"]["audio_id"]
    current_d = take
    segments = [("take", take)]
    history = []

    for rnd in range(1, plan["max_rounds"] + 1):
        payload = build_extend_request(
            audio_id=current_audio, continue_at=current_d - ov,
            source_duration_s=current_d, callback_url=callback_url,
            version=version, title=title, prompt=prompt, style=style,
            vocal_gender=vocal_gender, instrumental=instrumental,
            catalog_path=catalog_path,
        )
        produced, nxt = _normalize_produced(extend_fn(payload), rnd)
        history.append({
            "round": rnd,
            "continue_at_s": round(payload["input"]["continue_at"], 3),
            "from_s": current_d,
            "produced_s": produced,
            "audio_id": current_audio,
        })

        if produced <= current_d + MIN_PROGRESS_S:
            return dict(base, **{
                "status": "extend-no-progress",
                "reason": "round %d moved %.3f -> %.3f s"
                          % (rnd, current_d, produced),
                "extend_rounds": rnd,
                "history": history,
            })

        segments.append(("extend-round-%d" % rnd, produced - current_d))

        if produced >= target - EXACT_TOL_S:
            # Fit the last segment onto the target: an overshoot is trimmed
            # (the tail is not shipped), an undershoot inside EXACT_TOL_S is
            # absorbed - either way the delivered map ends on the target.
            prev = sum(d for _, d in segments[:-1])
            segments[-1] = ("extend-round-%d" % rnd, target - prev)
            return dict(base, **{
                "status": "ok",
                "action": "extend",
                "reason": "topped-up",
                "extend_rounds": rnd,
                "delivered_s": target,
                "extended_s": round(target - take, 3),
                "produced_s": produced,
                "trimmed_s": (round(produced - target, 3)
                              if produced - target > EXACT_TOL_S else 0.0),
                "history": history,
                "timing_map": timing_map(segments, target),
            })

        if not nxt:
            return dict(base, **{
                "status": "extend-no-audio-id",
                "reason": "round %d returned %.3f s with no audio id; a "
                          "further round cannot name its source"
                          % (rnd, produced),
                "extend_rounds": rnd,
                "history": history,
            })
        current_audio, current_d = nxt, produced

    return dict(base, **{
        "status": "extend-unresolved",
        "reason": "cap of %d rounds exhausted at %.3f s against a %.3f s "
                  "target" % (plan["max_rounds"], current_d, target),
        "extend_rounds": plan["max_rounds"],
        "history": history,
    })


__all__ = [
    "DEFAULT_EXTEND_VERSION",
    "EXIT",
    "EXACT_TOL_S",
    "EXTEND_CATALOG_ID",
    "ExtendError",
    "MAX_EXTEND_ROUNDS",
    "MIN_PROGRESS_S",
    "OVERLAP_S",
    "SCHEMA_VERSION",
    "TOOL_VERSION",
    "build_extend_request",
    "catalog",
    "endpoint",
    "plan_extend",
    "route_model",
    "timing_map",
    "top_up",
    "version_enum",
]
