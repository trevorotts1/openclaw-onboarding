"""agnes_price — the money lines of an Agnes choice card (SPEC A9).

With ``agnes == "yes"`` the video and the pictures come out of the client's
Agnes daily plan, so those lines carry no dollar figure: they read
``included in your Agnes plan`` and the card states how much Agnes video time
it uses ("Agnes video time: about N of your 500 seconds today"). Only the song
and the lip-sync close-ups are still paid studio work, so ``envelope`` prices
exactly those two lines through the injected Skill 74 ``price_fn`` and never
asks it for video or images. The backup model's price belongs on the backup
question, never on this card (SPEC A9/A10).

No rate is computed or stored here: ``price_line`` / ``credits_to_usd`` from
the shipped calculator, ``retake_allowance`` and ``_lip_sync_spec`` from the
price extension, and ``lipsync_clips.budget`` for the lip-sync line do the
arithmetic; Skill 74 ``price`` supplies every number (plan 5.4,
choice-card-spec section 4). Any unreadable rate fails the card closed with
"Price unavailable".

Agnes video time comes from ``agnes_plan.need`` (unit W1-agnes-core-U4: 10 s
fixed windows x shapes) — imported, never re-implemented. When that unit's
module is not on this branch the answer is ``AGNES_PLAN_UNAVAILABLE`` and the
card prices nothing, never a guess.

Stdlib only. No network: the price callable is injected.
"""
import math
import os
import sys

#: core/ is where the sibling modules (lipsync_clips, agnes_plan) live.
_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:  # package import (core.catalog_calculator)
    from .extensions import base_bridge
    from .extensions.price_extension import (LIPSYNC_ROSTER, _lip_sync_spec,
                                             _resolve, retake_allowance)
except ImportError:  # script import from inside this directory
    from extensions import base_bridge                            # type: ignore
    from extensions.price_extension import (LIPSYNC_ROSTER,       # type: ignore
                                            _lip_sync_spec, _resolve,
                                            retake_allowance)

import lipsync_clips                 # the one lip-sync plan (one source)

UNIT_NAME = "catalog-calculator.agnes-price"

#: The card rows whose dollars are Agnes video/picture work: those lines read
#: the plan text instead of a figure (SPEC A9; row names from card_render).
INCLUDED_ROWS = ("Length", "Shape", "Video model")

#: What an Agnes-included line item says, and it never carries a figure.
INCLUDED = "agnes-plan"

#: Agnes video seconds per day, every plan: wiki.agnes-ai.com/en/docs/tokenplan.md
#: "500 seconds per day" (RESEARCH.md 1-2, read 2026-10-13).
DAILY_VIDEO_S = 500


def _fail(state, reasons, warnings=None):
    """One fail-closed envelope, shaped like the extension's."""
    return {"unit": UNIT_NAME, "state": state, "price_label": "Price unavailable",
            "card": None, "fallback": None, "default": None,
            "reasons": list(reasons), "warnings": list(warnings or []),
            "start_paid": False, "approval_recorded": False}


def _card_render():
    """card_render, imported on the call: card_render imports this module."""
    try:
        from . import card_render as CR
    except ImportError:
        from catalog_calculator import card_render as CR          # type: ignore
    return CR


def video_seconds(card):
    """(Agnes video seconds for this card, None) or (None, reason).

    SPEC A9: N comes from ``agnes_plan.need`` — 10 s x segments x shapes —
    so the card and the plan never count twice.
    """
    try:
        import agnes_plan
    except ImportError:
        return None, "AGNES_PLAN_UNAVAILABLE"
    try:
        choice = _card_render().default_choice(card or {})
        n = agnes_plan.need(agnes_plan.segments(choice["length_seconds"]),
                            choice["shapes"])["video_seconds"]
        return int(n), None
    except Exception as e:
        return None, "AGNES_PLAN_ERROR: %s: %s" % (type(e).__name__, e)


def _lip_sync_line(length_s, shape_count):
    """lip_sync spec + (units, jobs): the card's lip-sync line (SPEC A9).

    Seconds and clip count come from the one lip-sync rule
    (``lipsync_clips.budget``: 30-40 s and 6-8 clips per 60 s ad, every clip
    at most 6 s) at its planned ceiling, so the card never under-quotes;
    ``_lip_sync_spec`` then enforces the roster and the 6 s cap.
    """
    budget = lipsync_clips.budget(length_s)
    spec, err, kind = _lip_sync_spec({
        "lip_sync": {"model": LIPSYNC_ROSTER[0],
                     "seconds": int(math.ceil(budget["total_max_s"])),
                     "lines": int(budget["max_clips"])}})
    if err:
        return None, None, err, kind
    units = spec["seconds"] * shape_count       # lip-sync runs on every shape
    jobs = spec["lines"] * shape_count
    return spec, (units, jobs), None, None


def envelope(card, price_fn):
    """The Agnes card's priced envelope, same shape as ``price_envelope``.

    ``price_fn`` is the Skill 74 ``price`` adapter; it is asked only for the
    song and the lip-sync close-ups. Video and image lines are Agnes plan
    lines (``included`` / ``agnes_seconds``, no figure). A rate that cannot be
    read fails the card closed: no partial price, no local number.
    """
    if (card or {}).get("agnes") != "yes":
        return _fail("error", ["AGNES_NOT_CHOSEN"])
    n, reason = video_seconds(card)
    if n is None:
        return _fail("unavailable", [reason])
    base, reason, detail = _resolve()
    if base is None:
        return _fail("unavailable", [reason], [detail])

    choice = _card_render().default_choice(card)
    shape_count = len(choice["shapes"])

    music, reason, detail = base.price_line(price_fn, choice["music_model"], 1, 1)
    if music is None:
        return _fail("unavailable", [reason], [detail])
    music = dict(music)
    music["component"] = "music"                # one song, shared by every shape

    spec, amounts, err, kind = _lip_sync_line(choice["length_seconds"], shape_count)
    if err:
        return _fail(kind or "unavailable", [err])
    units, jobs = amounts
    lip, reason, detail = base.price_line(price_fn, spec["model"], units, jobs)
    if lip is None:
        return _fail("unavailable", [reason], [detail])
    lip = dict(lip)
    lip["component"] = "lip_sync"

    agnes_line = {"included": INCLUDED, "usd": None, "agnes_seconds": n}
    items = [dict(agnes_line, component="video"), music,
             dict(agnes_line, component="image"), lip]

    credits = round(sum(float(li.get("credits") or 0.0) for li in items), 4)
    usd = base.credits_to_usd(credits)
    retake = retake_allowance(usd)
    priced = {
        "length_seconds": choice["length_seconds"],
        "shapes": list(choice["shapes"]),
        "shape_count": shape_count,
        "agnes": "yes",
        "agnes_seconds": n,
        "line_items": items,
        "price_credits": credits,
        "price_usd": usd,
        "price_label": base.usd_label(usd),
        "retake_allowance_usd": retake,
        "spending_limit_usd": round(usd + retake, 2),
        "lip_sync": {"model_id": spec["model"], "seconds": units, "lines": jobs,
                     "seconds_per_shape": spec["seconds"],
                     "lines_per_shape": spec["lines"],
                     "shape_count": shape_count},
    }
    return {"unit": UNIT_NAME, "state": "ok", "price_label": priced["price_label"],
            "card": priced, "fallback": None, "default": None,
            "reasons": [], "warnings": [], "start_paid": False,
            "approval_recorded": False}
