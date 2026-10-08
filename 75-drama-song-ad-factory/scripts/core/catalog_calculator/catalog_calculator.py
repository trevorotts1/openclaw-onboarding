"""Price/catalog calculator (unit V2-W0-U2). Plan sections 4.2, 5.1-5.3.

Every price shown to the client comes from Skill 74 `price --model ID --units N`
(the single price authority, plan 5.4). This module never parses pricing prose,
never stores a model rate, never computes a rate itself: it asks Skill 74, takes
`credits_estimate` (Skill 74's own answer: highest listed tier x units), and
multiplies only by quantity it can count itself (shots, shapes, one Suno
generation). Credit -> USD is a currency conversion (1 KIE credit = 0.005 USD,
proven by the build ledger), not a price.

Card rules this unit proves (plan 4.2, 5.1-5.3):
  * default model MiniMax H3 at 768P when the client makes no choice (D5).
  * if that default is unavailable (blocked, failing, missing from the live
    catalog), the card says price unavailable and OFFERS the next cheapest
    APPROVED model that fits the job, with its live price. Never a silent switch.
  * if any live rate cannot be read, the card says "Price unavailable" and
    start_paid stays false: no partial price, no invented number, paid work
    does not start.

Stdlib only. No version-1 imports. No network: the Skill 74 call is injected.
"""
import argparse
import json
import math
import sys

UNIT_NAME = "catalog-calculator"

# 1 KIE credit = 0.005 USD list price. Currency conversion, not a model rate:
# proven by qualification/long-form-media/spend-video-shot-01-reconciled.json
# (672 credits booked as 336 USD cents) and the client price menu doc.
CREDIT_USD = 0.005

# Owner decision D5: MiniMax H3 default, 768P, card states it when no choice.
DEFAULT_MODEL_FAMILY = "minimax-h3"
DEFAULT_RESOLUTION = "768P"

SHAPES = ("9:16", "16:9")

# Skill 74 units that scale with --units AND that this card can count itself:
# seconds of video and keyframe images. The adapter also scales per-1k-chars
# and per-1m-tokens (TTS/LLM); this card bills neither, so those units fail
# closed (PRICE_UNIT_UNSUPPORTED) instead of being multiplied by a wrong count.
SCALING_UNITS = ("per-second", "per-image")
# Units priced once per job; the calculator multiplies by jobs needed itself.
PER_JOB_UNITS = ("per-job", "free-as-per-job")

# Exit table: 0 ok, 4 rejected/fail closed (price unavailable => do not start),
# 1 error (unreadable or invalid input). Section 7.1's table, reused on purpose.
EXIT = {"ok": 0, "unavailable": 4, "error": 1}


# Storyboard image plan (Part I, unit I3). Per main character: a small
# reference set (3 angles + 3 expressions); then one keyframe per shot per
# shape before any video is made. Same image model as the keyframes.
REFERENCE_ANGLES = ("front", "three-quarter", "side")
REFERENCE_EXPRESSIONS = ("neutral", "sad-tired", "happy-relieved")
MAX_MAIN_CHARACTERS = 6


# ---------------------------------------------------------------- helpers

def image_plan(shots, shapes, characters, image_model):
    """The planner's image list: reference set per character + one keyframe
    per shot per shape. Counting only; the price comes from Skill 74."""
    refs = [{"character": c, "kind": "angle", "view": a}
            for c in characters for a in REFERENCE_ANGLES]
    refs += [{"character": c, "kind": "expression", "view": e}
             for c in characters for e in REFERENCE_EXPRESSIONS]
    keys = [{"shot": n, "shape": sh} for sh in shapes for n in range(1, shots + 1)]
    return {"image_model": image_model, "characters": list(characters),
            "reference_set": refs, "keyframes": keys,
            "reference_images": len(refs), "keyframe_images": len(keys),
            "total_images": len(refs) + len(keys)}


def shot_count(length_seconds, max_shot_seconds):
    """Shots per shape: ceil(length / model max shot). Plan 6.1: shot count
    comes from the chosen model's max shot length, never fixed per length."""
    if max_shot_seconds <= 0:
        raise ValueError("max_shot_seconds must be > 0")
    return -(-int(length_seconds) // int(max_shot_seconds))


def credits_to_usd(credits):
    """Credits -> USD, half-up to the cent (currency conversion only).
    Parens are load-bearing: (CREDIT_USD * 100) is exactly 0.5, while
    (credits * CREDIT_USD) * 100 drifts in float and can round a cent down."""
    return math.floor(credits * (CREDIT_USD * 100) + 0.5) / 100.0


def usd_label(usd):
    return "$%.2f" % usd


def price_line(skill74, model_id, units, jobs):
    """One line item priced through Skill 74.

    units: quantity Skill 74 scales (seconds of video, images, 1).
    jobs:  how many separate jobs that line needs (shots, images, 1).
    For scaling units Skill 74 already multiplied, so jobs are not applied
    again; for per-job units Skill 74 prices one job and jobs are applied here.
    Returns (line_dict, None) or (None, reason_code).
    """
    try:
        resp = skill74(model_id, units)
    except Exception as e:  # runner blew up: live rate not read => unavailable
        return None, "PRICE_RUNNER_ERROR", "skill74 runner raised %s: %s" % (
            type(e).__name__, e)
    if not isinstance(resp, dict):
        return None, "PRICE_RUNNER_ERROR", "skill74 runner returned %r" % (resp,)
    state = resp.get("state")
    if state != "ok":
        err = resp.get("error") or {}
        code = err.get("code") or "unknown"
        msg = err.get("msg") or ""
        if code in ("price_unavailable", "price_unestimable"):
            reason = "PRICE_UNAVAILABLE"
        else:
            reason = "PRICE_RUNNER_ERROR"
        return None, reason, "%s on %s: %s %s" % (reason, model_id, code, msg)
    data = resp.get("data") or {}
    est = data.get("credits_estimate")
    if not isinstance(est, (int, float)) or isinstance(est, bool):
        return None, "PRICE_UNESTIMABLE", "no credits_estimate from Skill 74 for %s" % model_id
    unit = data.get("unit")
    if unit in SCALING_UNITS:
        credits = round(float(est), 4)
        preflight = data.get("preflight_required")
    elif unit in PER_JOB_UNITS:
        credits = round(float(est) * jobs, 4)
        pf = data.get("preflight_required")
        preflight = None if pf is None else round(float(pf) * jobs, 2)
    else:
        return None, "PRICE_UNIT_UNSUPPORTED", "Skill 74 returned unit %r for %s" % (unit, model_id)
    line = {
        "model_id": model_id,
        "unit": unit,
        "units": units,
        "jobs": jobs,
        "credits": credits,
        "usd": credits_to_usd(credits),
        "price_source": data.get("price_source"),
        "preflight_required": preflight,
    }
    return line, None, None


def model_fit(entry, shapes):
    """Does this catalog entry fit the job (plan 5.2)? (ok, reason_code)."""
    max_shot = entry.get("max_shot_seconds")
    if not isinstance(max_shot, (int, float)) or isinstance(max_shot, bool) or max_shot <= 0:
        return False, "BAD_MAX_SHOT"
    have = entry.get("shapes")
    if not isinstance(have, (list, tuple)) or any(s not in have for s in shapes):
        return False, "SHAPE_UNSUPPORTED"
    if not entry.get("image_to_video"):
        return False, "NO_IMAGE_TO_VIDEO"
    if not entry.get("silent"):
        return False, "NOT_SILENT"
    return True, None


def model_status_ok(entry):
    """Approved gate (plan 5.2): PINNED and APPROVED only. (ok, reason)."""
    status = entry.get("status")
    if status in ("PINNED", "APPROVED"):
        return True, None
    if status == "DISCOVERED":
        return False, "MODEL_NOT_APPROVED"
    if status == "BLOCKED":
        return False, "MODEL_BLOCKED"
    if status == "UNKNOWN-DRIFT":
        return False, "MODEL_UNKNOWN_DRIFT"
    return False, "MODEL_STATUS_UNKNOWN"


def _index_catalog(catalog):
    """-> (by_id, error_reason). Duplicate id or malformed entry = error."""
    if isinstance(catalog, dict):
        catalog = catalog.get("models")
    if not isinstance(catalog, list) or not catalog:
        return None, "CATALOG_EMPTY"
    by_id = {}
    for entry in catalog:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry.get("id"):
            return None, "CATALOG_ENTRY_MALFORMED"
        if not isinstance(entry.get("task"), str) or not isinstance(entry.get("status"), str):
            return None, "CATALOG_ENTRY_MALFORMED"
        if entry["id"] in by_id:
            return None, "CATALOG_DUPLICATE_ID"
        by_id[entry["id"]] = entry
    return by_id, None


def _validate_choice(choice):
    """-> (norm, error_reason). norm = dict or None."""
    if not isinstance(choice, dict):
        return None, "BAD_CHOICE"
    length = choice.get("length_seconds")
    if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
        return None, "BAD_LENGTH"
    shapes = choice.get("shapes")
    if not isinstance(shapes, (list, tuple)) or not shapes:
        return None, "BAD_SHAPES"
    shapes = list(shapes)
    if len(set(shapes)) != len(shapes):
        return None, "BAD_SHAPES"
    if any(s not in SHAPES for s in shapes):
        return None, "BAD_SHAPES"
    if not isinstance(choice.get("music_model"), str) or not choice.get("music_model"):
        return None, "MISSING_MUSIC_MODEL"
    if not isinstance(choice.get("image_model"), str) or not choice.get("image_model"):
        return None, "MISSING_IMAGE_MODEL"
    model = choice.get("model")
    if model is not None and (not isinstance(model, str) or not model):
        return None, "BAD_MODEL_ID"
    chars = choice.get("main_characters", 1)  # pricing floor: one main character
    if isinstance(chars, int) and not isinstance(chars, bool):
        chars = ["Character %d" % (i + 1) for i in range(chars)]
    if (not isinstance(chars, (list, tuple)) or not 1 <= len(chars) <= MAX_MAIN_CHARACTERS
            or any(not isinstance(c, str) or not c for c in chars)):
        return None, "BAD_MAIN_CHARACTERS"
    return {"main_characters": list(chars), "length_seconds": length, "shapes": shapes, "shape_count": len(shapes),
            "model": model, "music_model": choice["music_model"],
            "image_model": choice["image_model"]}, None


def _entry_usable(entry, task, shapes):
    """Approved + right task + fits. -> (ok, reason) or None if entry malformed."""
    if entry.get("task") != task:
        return False, "MODEL_WRONG_TASK"
    ok, reason = model_status_ok(entry)
    if not ok:
        return False, reason
    if task == "video":
        return model_fit(entry, shapes)
    return True, None


def _find_default(by_id, shapes):
    """Default video entry: family + 768P, usable (D5). -> (entry|None, reason|None)."""
    family = [e for e in by_id.values()
              if e.get("task") == "video"
              and e.get("family") == DEFAULT_MODEL_FAMILY
              and e.get("resolution") == DEFAULT_RESOLUTION]
    if not family:
        return None, "DEFAULT_MODEL_MISSING"
    fits = [e for e in family if model_fit(e, shapes)[0]]
    if not fits:
        return None, model_fit(family[0], shapes)[1]
    fits.sort(key=lambda e: e["id"])
    usable, reason = _entry_usable(fits[0], "video", shapes)
    if not usable:
        return None, reason
    return fits[0], None


def _build_card(norm, entry, lines, is_default):
    """lines = {"video":..., "music":..., "image":...}, all priced."""
    total_credits = round(sum(lines[k]["credits"] for k in ("video", "music", "image")), 4)
    total_usd = credits_to_usd(total_credits)
    retake_usd = math.floor(total_usd * 0.20 * 100 + 0.5) / 100.0  # plan 4.1: +20% retake
    shots = shot_count(norm["length_seconds"], entry.get("max_shot_seconds"))
    items = []
    for comp in ("video", "music", "image"):
        li = dict(lines[comp])
        li["component"] = comp
        items.append(li)
    return {
        "length_seconds": norm["length_seconds"],
        "shapes": list(norm["shapes"]),
        "shape_count": norm["shape_count"],
        "model_id": entry["id"],
        "resolution": entry.get("resolution"),
        "is_default": is_default,
        "shots_per_shape": shots,
        "line_items": items,
        "price_credits": total_credits,
        "price_usd": total_usd,
        "price_label": usd_label(total_usd),
        "retake_allowance_usd": retake_usd,
        "spending_limit_usd": round(total_usd + retake_usd, 2),
    }


def _price_card_for(norm, entry, music_line, skill74):
    """Price one video entry's full card (music already priced).
    -> (card|None, reason, detail)"""
    shapes = norm["shapes"]
    shots = shot_count(norm["length_seconds"], entry["max_shot_seconds"])
    jobs = shots * norm["shape_count"]
    plan = image_plan(shots, shapes, norm["main_characters"], norm["image_model"])
    image_units = plan["total_images"]  # reference sets + one keyframe per shot per shape
    image_line, reason, detail = price_line(skill74, norm["image_model"], image_units, image_units)
    if image_line is None:
        return None, reason, detail
    share = plan["reference_images"] / float(image_units)
    plan["reference_set_credits"] = round(image_line["credits"] * share, 4)
    plan["reference_set_usd"] = credits_to_usd(plan["reference_set_credits"])
    video_seconds = norm["length_seconds"] * norm["shape_count"]  # each shape native, full length
    video_line, reason, detail = price_line(skill74, entry["id"], video_seconds, jobs)
    if video_line is None:
        return None, reason, detail
    lines = {"video": video_line, "music": music_line, "image": image_line}
    card = _build_card(norm, entry, lines, False)
    card["image_plan"] = plan
    return card, None, None


def price_card(choice, catalog, skill74, approval=None):
    """Main entry. choice/catalog as read from the factory's catalog sync;
    skill74 is a callable (model, units) -> Skill 74 `price` JSON dict.
    approval: the client's approval record (plan 4.1); None means not recorded.
    Returns an envelope dict; see README for the shape."""
    warnings = []
    norm, err = _validate_choice(choice)
    if err:
        return {"unit": UNIT_NAME, "state": "error", "reasons": [err],
                "warnings": warnings, "price_label": "Price unavailable",
                "card": None, "fallback": None, "default": None,
                "start_paid": False, "approval_recorded": approval is not None}
    by_id, err = _index_catalog(catalog)
    if err:
        return {"unit": UNIT_NAME, "state": "error", "reasons": [err],
                "warnings": warnings, "price_label": "Price unavailable",
                "card": None, "fallback": None, "default": None,
                "start_paid": False, "approval_recorded": approval is not None}

    shapes = norm["shapes"]
    reasons = []

    def envelope(state, card, fallback, default_block, extra_reasons, start_paid):
        all_reasons = reasons + extra_reasons
        return {"unit": UNIT_NAME, "state": state,
                "price_label": card["price_label"] if card else "Price unavailable",
                "card": card, "fallback": fallback, "default": default_block,
                "reasons": all_reasons, "warnings": warnings,
                "start_paid": start_paid,
                "approval_recorded": approval is not None}

    # Default block is informational (catalog view; price checked only if chosen).
    default_entry, default_reason = _find_default(by_id, shapes)
    default_block = {
        "model_id": default_entry["id"] if default_entry else None,
        "resolution": default_entry.get("resolution") if default_entry else None,
        "available": default_entry is not None,
        "reason": None if default_entry is not None else default_reason,
    }

    # Resolve the target video entry (the model the card would run on).
    is_default_choice = norm["model"] is None
    target, target_reason = None, None
    if is_default_choice:
        target, target_reason = default_entry, default_reason  # already status-checked
    else:
        chosen = by_id.get(norm["model"])
        if chosen is None:
            target_reason = "MODEL_UNKNOWN"
        else:
            ok, r = _entry_usable(chosen, "video", shapes)
            if ok:
                target = chosen
            else:
                target_reason = r
    if target is None:
        reasons.append("DEFAULT_MODEL_UNAVAILABLE" if is_default_choice
                       else "CHOSEN_MODEL_UNAVAILABLE")
        if target_reason:
            reasons.append(target_reason)

    # Music first: one Suno generation shared by every shape and every length.
    music_entry = by_id.get(norm["music_model"])
    if music_entry is None:
        reasons.append("MUSIC_MODEL_UNKNOWN")
        return envelope("unavailable", None, None, default_block, [], False)
    ok, r = _entry_usable(music_entry, "music", shapes)
    if not ok:
        reasons.append(r)
        return envelope("unavailable", None, None, default_block, [], False)
    music_line, reason, detail = price_line(skill74, norm["music_model"], 1, 1)
    if music_line is None:
        reasons.append(reason)
        warnings.append(detail)
        return envelope("unavailable", None, None, default_block, [], False)

    image_entry = by_id.get(norm["image_model"])
    if image_entry is None:
        reasons.append("IMAGE_MODEL_UNKNOWN")
        return envelope("unavailable", None, None, default_block, [], False)
    ok, r = _entry_usable(image_entry, "image", shapes)
    if not ok:
        reasons.append(r)
        return envelope("unavailable", None, None, default_block, [], False)

    def fallback_block():
        """Next cheapest APPROVED model that fits, fully priced (plan 5.3)."""
        candidates = []
        fit_count = 0
        for entry in by_id.values():
            if entry.get("task") != "video" or entry["id"] == (target["id"] if target else None):
                continue
            if norm["model"] is not None and entry["id"] == norm["model"]:
                continue
            fits, _r = model_fit(entry, shapes)
            if not fits:
                continue
            ok, _r = model_status_ok(entry)
            if not ok:
                continue
            fit_count += 1
            card, r, detail = _price_card_for(norm, entry, music_line, skill74)
            if card is None:
                warnings.append("fallback candidate %s not priced: %s" % (entry["id"], detail))
                continue
            candidates.append((card["price_credits"] - music_line["credits"], entry["id"], card, entry))
        if not candidates:
            return None, "NO_PRICED_FALLBACK" if fit_count else "NO_APPROVED_FALLBACK"
        candidates.sort(key=lambda c: (c[0], c[1]))
        _vcredits, cid, card, centry = candidates[0]
        card = dict(card)
        card["is_default"] = False
        return {"why": "DEFAULT_UNAVAILABLE" if is_default_choice else "CHOSEN_UNAVAILABLE",
                "requires_client_approval": True,
                "model_id": cid,
                "card": card}, None

    if target is not None:
        card, reason, detail = _price_card_for(norm, target, music_line, skill74)
        if card is not None:
            card = dict(card)
            card["is_default"] = is_default_choice
            if approval is None:
                reasons.append("APPROVAL_RECORD_MISSING")
            return envelope("ok", card, None, default_block, [], approval is not None)
        reasons.append(reason)
        warnings.append(detail)

    # Target unavailable (fit or price): offer the next cheapest APPROVED model.
    fb, fb_reason = fallback_block()
    if fb is None:
        reasons.append(fb_reason)
        return envelope("unavailable", None, None, default_block, [], False)
    return envelope("unavailable", None, fb, default_block, [], False)


# ---------------------------------------------------------------- CLI

def skill74_subprocess(python_script):
    """Adapter for a real Skill 74 install: `python3 SCRIPT price --model M --units N`.
    Tests inject fakes instead; nothing here ever runs in the mocked suite."""
    import subprocess

    def run(model, units):
        proc = subprocess.run(
            [sys.executable, python_script, "price", "--model", model, "--units", str(units)],
            capture_output=True, text=True, timeout=60)
        try:
            return json.loads(proc.stdout)
        except ValueError:
            return {"state": "fail", "error": {"code": "bad_response",
                    "msg": "skill74 printed no JSON (rc=%s): %s" % (proc.returncode, proc.stderr[:200])}}
    return run


def main(argv=None):
    ap = argparse.ArgumentParser(prog="catalog_calculator.py",
                                 description="Price a choice card through Skill 74 rates only.")
    ap.add_argument("--choice", default=None,
                    help="JSON file: the client's choice")
    ap.add_argument("--catalog", default=None,
                    help="JSON file: the synced model catalog")
    ap.add_argument("--skill74", default=None,
                    help="path to kie_live_adapter.py (Skill 74)")
    ap.add_argument("--credits", default=None, type=int,
                    help="smoke check: convert N credits to USD "
                         "(%s USD per credit) and print the figure" % CREDIT_USD)
    ap.add_argument("--approval", default=None, help="JSON file: approval record, if recorded")
    if argv is not None and "--credits" in argv and "--choice" not in argv:
        argv = list(argv)  # credits-only conversion smoke check
        i = argv.index("--credits")
        credits = int(argv[i + 1]) if len(argv) > i + 1 else 0
        print("%s -> %s" % (credits, usd_label(credits_to_usd(credits))))
        return EXIT["ok"]
    args = ap.parse_args(argv)
    if args.credits is not None and not args.choice:
        print("%s -> %s" % (args.credits, usd_label(credits_to_usd(args.credits))))
        return EXIT["ok"]
    if not args.choice or not args.catalog or not args.skill74:
        ap.error("the following arguments are required unless --credits: "
                 "--choice, --catalog, --skill74")
    args = ap.parse_args(argv)
    try:
        with open(args.choice, encoding="utf-8") as f:
            choice = json.load(f)
        with open(args.catalog, encoding="utf-8") as f:
            catalog = json.load(f)
        approval = None
        if args.approval:
            with open(args.approval, encoding="utf-8") as f:
                approval = json.load(f)
    except (OSError, ValueError) as e:
        out = {"unit": UNIT_NAME, "state": "error", "reasons": ["INPUT_UNREADABLE"],
               "warnings": [str(e)], "price_label": "Price unavailable", "card": None,
               "fallback": None, "default": None, "start_paid": False,
               "approval_recorded": False}
        sys.stdout.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
        return EXIT["error"]
    env = price_card(choice, catalog, skill74_subprocess(args.skill74), approval)
    sys.stdout.write(json.dumps(env, indent=2, sort_keys=True) + "\n")
    return EXIT[env["state"]]


if __name__ == "__main__":
    sys.exit(main())
