"""price_extension — extends unit V2-W0-U2's catalog calculator (BO-PKG2-U1).

Adds four things to the choice-card total and to the D26 batch total:

  * **lip-sync close-up seconds** (choice-card-spec 3.6, price-menu 3): one
    line per ad, priced by Skill 74 ``price --model <roster model> --units
    <seconds x shapes>``. Lip-sync runs on every shape that was ordered, so
    both shapes double this line.
  * **voice packs** (price-menu 4): one line of extra Suno generations. How
    many generations a pack needs is decided upstream by the music director;
    this module asks Skill 74 ``price`` and never predicts the count or the
    rate.
  * **both shapes**: unit V2-W0-U2 already multiplies video and keyframes by
    shape count; the new lines follow the same rule - lip-sync yes, the one
    shared Suno song and its packs no.
  * **batch total** (plan 6.14, price-menu 6): one card per book, then
    ``batch total = sum over books of (Skill 74 price for that book's
    choices)``, plus the same 20% retake allowance.

Everything is done through unit V2-W0-U2's ``price_card`` / ``price_line`` /
``credits_to_usd``. This module never re-implements that arithmetic, never
stores a rate and never computes one: Skill 74 ``price --model ID --units N``
stays the single price authority (plan 5.4, choice-card-spec section 4).

Fail-closed (plan 4.2): if the base calculator cannot be located or loaded, or
if any new rate cannot be read, the card says "Price unavailable" and
``start_paid`` stays false. No partial price, no local number.

Stdlib only. No network: the Skill 74 callable is injected and the base
calculator is discovered on disk, never fetched.
"""
import math
import os

try:  # package import (core.catalog_calculator.extensions)
    from . import base_bridge
except ImportError:  # script import from inside this directory
    import base_bridge

UNIT_NAME = "catalog-calculator.extensions"
BATCH_UNIT_NAME = "catalog-calculator.extensions.batch"

# Plan 4.1 / choice-card-spec 4.3: the retake allowance. A policy percentage,
# not a price - unit V2-W0-U2 applies the same one to its own total.
RETAKE_RATE = 0.20

# Decision 33 / choice-card-spec 3.6: the lip-sync roster is closed - Kling
# avatar first, InfiniTalk as the backup. A model outside it is never offered
# and never asked for a price.
LIPSYNC_ROSTER = ("kling/ai-avatar-standard", "infinitalk/from-audio")


# ---------------------------------------------------------------- helpers

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def retake_allowance(price_usd):
    """Plan 4.1: the 20% retake allowance, half-up to the cent."""
    return math.floor(price_usd * RETAKE_RATE * 100 + 0.5) / 100.0


def find_calculator(explicit=None):
    """Absolute path of unit V2-W0-U2's calculator, or None."""
    return base_bridge.find_calculator(explicit)


def _resolve(explicit=None):
    """-> (module|None, reason|None, detail|None)."""
    if explicit and not os.path.isfile(explicit):
        # An explicit path is authoritative: no silent fall-through to a
        # different calculator than the caller asked for.
        return None, "PRICE_CALCULATOR_MISSING", \
            "explicit calculator path is not a file: %s" % explicit
    path = base_bridge.find_calculator(explicit)
    if path is None:
        searched = base_bridge.candidate_paths(explicit)
        return None, "PRICE_CALCULATOR_MISSING", "searched: %s" % ", ".join(searched)
    try:
        module = base_bridge.load_calculator(path)
    except Exception as e:  # any load fault is "no price" (plan 4.2)
        return None, "PRICE_CALCULATOR_LOAD_ERROR", "%s: %s" % (type(e).__name__, e)
    return module, None, None


def _lip_sync_spec(choice):
    """choice["lip_sync"] -> (spec|None, reason|None, kind|None).

    kind is "error" (malformed input) or "unavailable" (policy refusal).
    """
    raw = choice.get("lip_sync")
    if raw is None:
        return None, None, None
    if not isinstance(raw, dict):
        return None, "BAD_LIP_SYNC", "error"
    model = raw.get("model")
    seconds = raw.get("seconds")
    lines = raw.get("lines")
    if (not isinstance(model, str) or not model
            or not _is_int(seconds) or seconds <= 0
            or not _is_int(lines) or lines < 1):
        return None, "BAD_LIP_SYNC", "error"
    if model not in LIPSYNC_ROSTER:
        return None, "LIPSYNC_MODEL_NOT_OFFERED", "unavailable"
    return {"model": model, "seconds": seconds, "lines": lines}, None, None


def _voice_pack_spec(choice):
    """choice["voice_packs"] -> (spec|None, reason|None, kind|None)."""
    raw = choice.get("voice_packs")
    if raw is None:
        return None, None, None
    if not isinstance(raw, dict):
        return None, "BAD_VOICE_PACKS", "error"
    count = raw.get("count")
    if not _is_int(count) or count < 0:
        return None, "BAD_VOICE_PACKS", "error"
    if count == 0:  # nothing to generate, nothing to price
        return None, None, None
    return {"count": count}, None, None


def _prepare(choice):
    """-> (spec|None, reason|None, kind|None)."""
    if not isinstance(choice, dict):
        return None, "BAD_CHOICE", "error"
    lip, err, kind = _lip_sync_spec(choice)
    if err:
        return None, err, kind
    vp, err, kind = _voice_pack_spec(choice)
    if err:
        return None, err, kind
    return {"lip_sync": lip, "voice_packs": vp}, None, None


def _fail(kind, reasons, approval, unit=UNIT_NAME, warnings=None, default=None):
    """One fail-closed / error envelope, shaped like unit V2-W0-U2's."""
    return {"unit": unit, "state": kind, "price_label": "Price unavailable",
            "card": None, "fallback": None, "default": default,
            "reasons": list(reasons), "warnings": list(warnings or []),
            "start_paid": False,
            "approval_recorded": approval is not None}


# ---------------------------------------------------------------- card

def _extend_card(base, card, lip, vp, choice, skill74):
    """Add the lip-sync and voice-pack lines and re-total the card.

    -> (card|None, reason|None, detail|None). Any unreadable rate returns
    (None, reason, detail): the caller fails closed instead of shipping a
    partial price.
    """
    shape_count = card.get("shape_count")
    if not _is_int(shape_count) or shape_count < 1:
        return None, "PRICE_CALCULATOR_MALFORMED", "card has no usable shape_count"
    items = [dict(li) for li in (card.get("line_items") or [])]
    lip_block = None
    vp_block = None

    if lip:
        # Lip-sync runs per shape (price-menu 3: both shapes when both are
        # ordered), so both the seconds and the close-up count scale.
        units = lip["seconds"] * shape_count
        jobs = lip["lines"] * shape_count
        line, reason, detail = base.price_line(skill74, lip["model"], units, jobs)
        if line is None:
            return None, reason, detail
        line = dict(line)
        line["component"] = "lip_sync"
        items.append(line)
        lip_block = {"model_id": lip["model"], "seconds": units, "lines": jobs,
                     "seconds_per_shape": lip["seconds"],
                     "lines_per_shape": lip["lines"],
                     "shape_count": shape_count}

    if vp:
        # The song and its voice packs are one audio asset shared by every
        # shape (plan 6.2), so the pack count is not multiplied.
        music_model = choice.get("music_model")
        if not isinstance(music_model, str) or not music_model:
            return None, "MISSING_MUSIC_MODEL", "no music model to price packs against"
        line, reason, detail = base.price_line(skill74, music_model,
                                               vp["count"], vp["count"])
        if line is None:
            return None, reason, detail
        line = dict(line)
        line["component"] = "voice_packs"
        items.append(line)
        vp_block = {"count": vp["count"], "model_id": music_model}

    total_credits = round(sum(li["credits"] for li in items), 4)
    total_usd = base.credits_to_usd(total_credits)
    retake = retake_allowance(total_usd)

    out = dict(card)
    out["line_items"] = items
    out["price_credits"] = total_credits
    out["price_usd"] = total_usd
    out["price_label"] = base.usd_label(total_usd)
    out["retake_allowance_usd"] = retake
    out["spending_limit_usd"] = round(total_usd + retake, 2)
    out["lip_sync"] = lip_block
    out["voice_packs"] = vp_block
    return out, None, None


def _extend_fallback(base, env, lip, vp, choice, skill74):
    """Extend the offered fallback card too; drop it if that cannot be priced."""
    fb = env.get("fallback")
    if not isinstance(fb, dict) or not fb.get("card"):
        return env
    card, reason, detail = _extend_card(base, fb["card"], lip, vp, choice, skill74)
    out = dict(env)
    warnings = list(env.get("warnings") or [])
    if card is None:
        out["fallback"] = None
        out["reasons"] = list(env.get("reasons") or []) + [reason]
        warnings.append("fallback card not priced: %s %s" % (reason, detail))
    else:
        out["fallback"] = dict(fb, card=card)
    out["warnings"] = warnings
    return out


def _price_one(base, choice, pre, catalog, skill74, approval):
    """Price one ad through the real base calculator, then extend its card."""
    env = base.price_card(choice, catalog, skill74, approval)
    if not isinstance(env, dict) or env.get("state") not in ("ok", "unavailable",
                                                             "error"):
        return _fail("unavailable", ["PRICE_CALCULATOR_MALFORMED"], approval,
                     warnings=[repr(env)])
    env = dict(env)
    env["unit"] = UNIT_NAME
    if env.get("state") == "error":
        return env

    lip = pre["lip_sync"]
    vp = pre["voice_packs"]
    if lip is None and vp is None:
        # Nothing to add: the base card is the answer, unchanged.
        return env

    if env.get("state") != "ok" or not env.get("card"):
        return _extend_fallback(base, env, lip, vp, choice, skill74)

    card, reason, detail = _extend_card(base, env["card"], lip, vp, choice,
                                        skill74)
    if card is None:
        return _fail("unavailable",
                     list(env.get("reasons") or []) + [reason], approval,
                     warnings=[detail], default=env.get("default"))
    env["card"] = card
    env["price_label"] = card["price_label"]
    return env


def price_card_ext(choice, catalog, skill74, approval=None, calculator_path=None):
    """One choice card, priced by unit V2-W0-U2 plus this unit's lines.

    ``choice`` is the base calculator's choice with two optional additions::

        "lip_sync":     {"model": <roster id>, "seconds": int>0, "lines": int>=1}
        "voice_packs":  {"count": int>=0}      # 0 or absent = no line

    ``skill74`` is the injected ``(model, units) -> Skill 74 price JSON``
    callable, exactly as unit V2-W0-U2 takes it. Returns that unit's envelope
    with ``unit`` set to ``catalog-calculator.extensions``; when neither
    addition is present the envelope is otherwise the base one, untouched.
    """
    pre, err, kind = _prepare(choice)
    if err:
        return _fail(kind, [err], approval)
    base, reason, detail = _resolve(calculator_path)
    if base is None:
        return _fail("unavailable", [reason], approval, warnings=[detail])
    return _price_one(base, choice, pre, catalog, skill74, approval)


# ---------------------------------------------------------------- batch

def _cents(price_usd):
    """Whole cents of a card price (the base calculator rounds to the cent)."""
    return int(round(price_usd * 100))


def price_batch(ads, catalog, skill74, approval=None, calculator_path=None):
    """D26 batch (plan 6.14): one card per book, batch total = the sum.

    ``ads`` is the list of per-book choices - each one carries its own brief's
    lip-sync seconds and pack count, while look / music / length / shape come
    from the single choice card the client approved for the whole batch.

    Any ad that cannot be priced takes the whole batch down: the envelope then
    says "Price unavailable" with no numbers anywhere and ``start_paid`` false
    (choice-card-spec 4.4). On success ``batch.total`` is the exact sum of the
    per-ad card prices, with the 20% retake allowance on top.
    """
    if not isinstance(ads, (list, tuple)) or not ads:
        return _fail("error", ["BATCH_EMPTY"], approval, unit=BATCH_UNIT_NAME)

    base, reason, detail = _resolve(calculator_path)
    if base is None:
        return _fail("unavailable", [reason], approval, unit=BATCH_UNIT_NAME,
                     warnings=[detail])

    items = []
    for index, ad in enumerate(ads):
        pre, err, kind = _prepare(ad)
        if err:
            prefix = "BATCH_AD_ERROR" if kind == "error" else "BATCH_AD_UNAVAILABLE"
            env = _fail(kind, [prefix, err], approval, unit=BATCH_UNIT_NAME)
            env["failed_ad"] = index
            return env
        env = _price_one(base, ad, pre, catalog, skill74, approval)
        if env.get("state") != "ok" or not env.get("card"):
            env = dict(env)
            env["unit"] = BATCH_UNIT_NAME
            env["failed_ad"] = index
            prefix = "BATCH_AD_ERROR" if env.get("state") == "error" \
                else "BATCH_AD_UNAVAILABLE"
            env["reasons"] = [prefix] + list(env.get("reasons") or [])
            env["warnings"] = list(env.get("warnings") or []) + [
                "ad %d: %s" % (index, ", ".join(env.get("reasons") or []) or
                               env.get("state"))]
            return env
        card = env["card"]
        items.append({"index": index, "state": "ok",
                      "price_label": card["price_label"],
                      "price_credits": card["price_credits"],
                      "price_usd": card["price_usd"], "card": card})

    # Batch total = the sum of the per-ad card prices, exactly: add whole
    # cents so the sum of already-rounded quotes never drifts.
    total_credits = round(sum(i["price_credits"] for i in items), 4)
    total_usd = sum(_cents(i["price_usd"]) for i in items) / 100.0
    retake = retake_allowance(total_usd)
    summary = {"kind": "batch", "ad_count": len(items),
               "price_credits": total_credits, "price_usd": total_usd,
               "price_label": base.usd_label(total_usd),
               "retake_allowance_usd": retake,
               "spending_limit_usd": round(total_usd + retake, 2)}
    batch = dict(summary)
    batch["items"] = items
    return {"unit": BATCH_UNIT_NAME, "state": "ok",
            "price_label": summary["price_label"],
            "card": dict(summary), "batch": batch,
            "fallback": None, "default": None,
            "reasons": [] if approval is not None else ["APPROVAL_RECORD_MISSING"],
            "warnings": [],
            "start_paid": approval is not None,
            "approval_recorded": approval is not None}
