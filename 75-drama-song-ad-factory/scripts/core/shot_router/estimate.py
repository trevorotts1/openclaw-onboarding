"""estimate.py: cost and time per shot and per run, shown before any paid job (N-62).

Section 3E.4. Rates come from KIE's own records for 119 tasks (2026-11-23) and
from the 27-piece OmniHuman test; they live in ``rates.json`` beside this file
so a price change is a data edit, never a code edit. A model with no rate on
file reports ``PRICE_MISSING`` and the run total is withheld -- never a zero.

What a shot costs:

* pictures -- every keyframe is TWO candidates (N-82); a picture's price is the
  provider record's ``price_credits_per_image`` times its candidate count.
* the clip -- H3 image-to-video and nine-picture clips are priced by the second
  at the measured rates; a lip-sync take is 14 credits per whole second of
  audio, rounded up.
* a failed job costs 0: refunds are the provider's, never a line here.

What a shot takes, in minutes, is the 9-in-10 job time of its slowest route, so
a burst's wall time is its slowest job, not a sum. A model without a time on
file reports ``TIME_MISSING``.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

import json
from pathlib import Path

from .common import ShotRouterError, as_number, ceil_seconds

HERE = Path(__file__).resolve().parent
RATES_PATH = HERE / "rates.json"

#: 1 KIE credit = half a cent, the plan's own conversion (3E.4).
USD_PER_CREDIT = 0.005

PRICE_MISSING = "PRICE_MISSING"
TIME_MISSING = "TIME_MISSING"

#: The only models with a measured price on file (3E.4). Any other model is
#: PRICE_MISSING -- never charged at another model's rate.
PRICED_VIDEO_MODELS = frozenset({
    "minimax-h3/image-to-video",
    "minimax-h3/reference-to-video",
})
PRICED_LIPSYNC_MODELS = frozenset({"omnihuman-2-0", "omnihuman"})


def load_rates(path=None):
    resolved = Path(path) if path else RATES_PATH
    try:
        doc = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShotRouterError("RATES_UNREADABLE",
                              "cannot read measured rates at %s: %s" % (resolved, exc))
    return doc


def _clip_seconds_used(record):
    """The clip length the estimate charges for: the hint, else the window."""
    clip = record.get("clip") or {}
    if isinstance(clip, dict):
        for key in ("seconds", "clip_seconds"):
            value = clip.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    hint = record.get("clip_seconds_hint")
    if isinstance(hint, (int, float)) and not isinstance(hint, bool):
        return float(hint)
    window = record.get("song_window_seconds") or []
    if len(window) == 2:
        return max(0.0, float(window[1]) - float(window[0]))
    return 0.0


def _h3_credits(route, seconds, rates):
    """H3 credits by route and whole-second clip length (measured table)."""
    table = (rates.get("h3_nine_picture") if route in ("nine_picture", "long_take")
             else rates.get("h3_image_to_video")) or {}
    whole = int(ceil_seconds(seconds))
    if str(whole) in table:
        return table[str(whole)], whole
    # A length past the measured table is charged at the longest measured rate
    # per second and FLAGGED, so an unmeasured length never looks priced.
    longest = max(int(k) for k in table) if table else 0
    if not longest:
        return None, whole
    per_second = table[str(longest)] / float(longest)
    return round(per_second * whole, 2), whole


def _picture_credits(record, picture_rates):
    """Credits for every picture in a record's list, including candidates."""
    rates = picture_rates or {}
    total = 0.0
    rows = []
    for picture in record.get("pictures") or []:
        price = rates.get(picture.get("kind") or picture.get("purpose"))
        if price is None:
            price = rates.get("default")
        candidates = picture.get("candidates") or 1
        if price is None:
            rows.append({"picture": picture.get("purpose"), "credits": None,
                         "code": PRICE_MISSING})
            continue
        credits = round(float(price) * int(candidates), 2)
        total += credits
        rows.append({"picture": picture.get("purpose"),
                     "candidates": int(candidates), "credits": credits})
    return total, rows


def estimate_shot(record, *, rates=None, picture_rates=None, provider_record=None):
    """One shot's credits and minutes. Raises nothing; codes ride on the row."""
    book = rates if isinstance(rates, dict) else load_rates()
    if picture_rates is None:
        picture_rates = dict(book.get("picture_credits") or {})
        if provider_record and provider_record.get("price_credits_per_image") is not None:
            picture_rates["default"] = provider_record["price_credits_per_image"]
    codes = []
    pictures_credits, picture_rows = _picture_credits(
        {"pictures": record.get("pictures") or []}, picture_rates)
    for row in picture_rows:
        if row["credits"] is None and PRICE_MISSING not in codes:
            codes.append(PRICE_MISSING)

    route = record.get("route")
    model = record.get("model")
    seconds = _clip_seconds_used(record)
    clip_credits = 0.0
    clip_minutes = None
    if route == "lip_sync":
        audio = (record.get("lip_sync") or {}).get("audio_seconds")
        audio = seconds if audio is None else float(audio)
        omni = book.get("omnihuman") or {}
        rate = omni.get("credits_per_second")
        if model not in PRICED_LIPSYNC_MODELS or rate is None:
            codes.append(PRICE_MISSING)
        else:
            clip_credits = round(rate * ceil_seconds(audio), 2)
        clip_minutes = _minutes(omni.get("time_seconds") or {}, audio, codes)
    elif model not in PRICED_VIDEO_MODELS:
        # A model with no rate on file is never charged at another's rate.
        codes.append(PRICE_MISSING)
        clip_minutes = _minutes(book.get("h3_time_seconds") or {}, seconds, codes)
    else:
        is_nine = route in ("nine_picture", "long_take")
        credit_table = book.get("h3_nine_picture" if is_nine
                                else "h3_image_to_video") or {}
        time_table = book.get("h3_nine_picture_time_seconds" if is_nine
                              else "h3_time_seconds") or {}
        whole = int(ceil_seconds(seconds))
        if str(whole) not in credit_table:
            codes.append("TIME_UNMEASURED_LENGTH")
        value, whole = _h3_credits(route, seconds, book)
        if value is None:
            codes.append(PRICE_MISSING)
        else:
            clip_credits = value
        clip_minutes = _minutes(time_table, float(whole), codes)

    credits = round(pictures_credits + clip_credits, 2)
    row = {
        "shot_id": record.get("shot_id"),
        "route": route,
        "model": model,
        "clip_seconds": seconds,
        "pictures": picture_rows,
        "picture_credits": pictures_credits,
        "clip_credits": clip_credits,
        "credits": credits,
        "usd": round(credits * USD_PER_CREDIT, 4),
        "minutes": clip_minutes,
        "codes": codes,
    }
    return row


def _minutes(table, seconds, codes):
    """One job's 9-in-10 minutes; the nearest measured length when none is exact."""
    if not table:
        codes.append(TIME_MISSING)
        return None
    sec = int(ceil_seconds(seconds))
    value = table.get(str(sec))
    if value is None:
        codes.append("TIME_UNMEASURED_LENGTH")
        nearest = min((int(k) for k in table),
                      key=lambda k: (abs(k - sec), -k))
        value = table[str(nearest)]
    if isinstance(value, dict):
        return float(value.get("p90_seconds", 0)) / 60.0
    return float(value) / 60.0


def estimate_run(records, **kwargs):
    """Per-shot rows plus the run total. Totals are withheld when a price is missing.

    Minutes are NOT summed: a burst takes as long as its slowest job, so the
    run row reports ``slowest_job_minutes`` beside the summed picture minutes.
    """
    rows = [estimate_shot(record, **kwargs) for record in records]
    codes = sorted({code for row in rows for code in row["codes"]})
    priced = PRICE_MISSING not in codes
    minutes = [row["minutes"] for row in rows if row["minutes"] is not None]
    credits = round(sum(row["credits"] for row in rows), 2) if priced else None
    return {
        "shots": rows,
        "totals": {
            "shots": len(rows),
            "credits": credits,
            "usd": round(credits * USD_PER_CREDIT, 4) if credits is not None else None,
            "slowest_job_minutes": round(max(minutes), 2) if minutes else None,
            "job_minutes_sum": round(sum(minutes), 2) if minutes else None,
            "codes": codes,
            "price_complete": priced,
        },
        "rates_source": "rates.json: KIE records for 119 tasks and the 27-piece "
                        "OmniHuman test, 2026-11-23",
    }


def require_estimate(records, **kwargs):
    """Estimate a run and REFUSE to hand it to a paid job when any price is missing."""
    result = estimate_run(records, **kwargs)
    if not result["totals"]["price_complete"]:
        missing = [row["shot_id"] for row in result["shots"]
                   if PRICE_MISSING in row["codes"]]
        raise ShotRouterError(
            PRICE_MISSING,
            "no price on file for %s; the run total is withheld until every "
            "model has a measured price (3E.4)" % (", ".join(missing) or "the run"),
        )
    return result
