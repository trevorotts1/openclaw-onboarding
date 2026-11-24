#!/usr/bin/env python3
"""quality_modes.mode_gate: the quality-mode card, its price table and its gate.

The card offers four quality modes -- Standard, Premium, Ultra and Hybrid -- in
place of the old per-vendor VIDEO MODEL question (F-QM-1). The run owner's
recorded pick is the authorization for the route it names (N-12). Nothing paid
starts before that pick is recorded: a missing pick is refused
`QUALITY_MODE_NOT_CHOSEN` (F-QM-5).

One price table, ``references/quality-modes.json`` (``mode_prices``), feeds the
card, the gate and the cost estimate, so they cannot drift (N-55). A cost
estimate refuses `PRICE_MISSING` only for a mode that truly has no price. Ultra
is shown always; when no live-registry model advertises 4K it is reported
`ULTRA_MODEL_UNAVAILABLE` and no lower-resolution model is ever substituted
(F-QM-4).

This module also writes the run and shot records (F-QM-6): the run file
``storyboard/quality-mode.json`` and the six shot fields.

stdlib only, no network, no spend.
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.normpath(os.path.join(_HERE, "..", "..", "..",
                                      "references", "quality-modes.json"))

#: Refusal codes, stable strings other modules and the dispatcher match on.
NOT_CHOSEN = "QUALITY_MODE_NOT_CHOSEN"
UNKNOWN = "UNKNOWN_QUALITY_MODE"
PRICE_MISSING = "PRICE_MISSING"
ULTRA_UNAVAILABLE = "ULTRA_MODEL_UNAVAILABLE"
MODES_UNAVAILABLE = "QUALITY_MODES_UNAVAILABLE"

CREDITS_USD = 0.005

TOOL_NAME = "quality_modes.mode_gate"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.quality-mode/v1"

#: The lip-sync model is fixed and is NOT a card choice (N-12, 3C.1a).
LIPSYNC_MODEL = "omnihuman-2-0"
#: Refusal code for any other lip-sync model (N-12).
LIPSYNC_MISMATCH = "LIPSYNC_MODEL_MISMATCH"


def check_lipsync_model(model_id):
    """Return the fixed lip-sync model, or raise LIPSYNC_MODEL_MISMATCH.

    OmniHuman 2.0 on every run, talking or singing, no alternative and no
    backup (3C.1a). The card never offers a lip-sync model; this is the one
    place a wrong one is refused. The governed dispatcher calls it too."""
    if model_id == LIPSYNC_MODEL:
        return LIPSYNC_MODEL
    raise ModeGateError(
        LIPSYNC_MISMATCH,
        "%r is not the lip-sync model; the lip-sync model is %s on every run, "
        "with no alternative and no backup" % (model_id, LIPSYNC_MODEL))


#: Every resolution a mode may name, cheapest first.
RESOLUTIONS = ("720p", "768P", "1080p", "2K", "4K")


class ModeGateError(ValueError):
    """A quality-mode refusal that carries its reason code."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


class SchemaError(ValueError):
    """A run or shot record that does not match the quality-mode schema."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _load(path=None):
    path = path or _PATH
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise ModeGateError(MODES_UNAVAILABLE,
                            "quality-modes.json unreadable at %s: %s" % (path, e))


_DOC = _load()
MODES = _DOC["modes"]
MODE_PRICES = _DOC["mode_prices"]
CODES = _DOC.get("codes") or {}


def _norm(x):
    return "".join(ch for ch in str(x).lower() if ch.isalnum())


_BY_ID = {m["id"]: m for m in MODES}
_BY_KEY = {}
for _m in MODES:
    _BY_KEY[_norm(_m["id"])] = _m["id"]
    _BY_KEY[_norm(_m["label"])] = _m["id"]


def mode_ids():
    """The four mode ids, in card order."""
    return [m["id"] for m in MODES]


def recommended():
    """The id the card marks recommended (its own flag), else Standard."""
    rid = _DOC.get("recommended")
    if rid in _BY_ID:
        return rid
    return next((m["id"] for m in MODES if m.get("recommended")), "standard")


def _registry_models():
    """The live KIE catalog entries, or None when the registry cannot be read."""
    try:
        from choice_card.video_models import video_models as VM
    except Exception:                                   # pragma: no cover
        return None, "video_models unavailable"
    path = VM.resolve_registry()
    if not path:
        return None, ("no kie-model-registry.json found via "
                      "KIE_MODEL_REGISTRY_JSON or walk-up")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return None, "the live KIE model registry cannot be read (%s): %s" % (path, e)
    rows = data.get("models") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None, "the live KIE model registry carries no models list (%s)" % path
    return [m for m in rows if isinstance(m, dict)], path


def _offers_4k(m):
    fields = m.get("input_fields") or {}
    for key in ("resolution", "mode"):
        for v in ((fields.get(key) or {}).get("enum") or []):
            s = str(v).lower()
            if s == "4k" or s.startswith("2160"):
                return True
    return False


def _ultra_row():
    """The live-registry row Ultra resolves to, or (None, detail). Never faked.

    The rates table's own Ultra model is preferred when the live catalog carries
    it at 4K; otherwise the first Image-to-Video model advertising 4K."""
    models, where = _registry_models()
    if models is None:
        return None, where
    try:
        from choice_card.video_models import video_models as VM
        named = (VM.RATES.get("ultra") or {}).get("kie_model")
    except Exception:                                   # pragma: no cover
        named = None
    candidates = [m for m in models
                  if any("Image to Video" in str(t) for t in (m.get("taskType") or []))
                  and _offers_4k(m)]
    for m in candidates:
        if named and m.get("id") == named:
            return {"video_model": m["id"], "name": m.get("title") or m["id"]}, None
    if candidates:
        m = candidates[0]
        return {"video_model": m["id"], "name": m.get("title") or m["id"]}, None
    return None, ("no model in the live KIE registry advertises 4K on an "
                  "Image-to-Video task, so Ultra is shown as unavailable")


def _ultra_price(row):
    """Rate for the model Ultra resolved to -- that model's own price, never
    another model's (F-QM-4: shown, never faked).

    The rates table's Ultra entry is one model's price (Veo 3.1 Fast 4K), so it
    is used only when Ultra resolved to exactly that model. Otherwise the price
    is the resolved registry model's own highest-tier rate (credits_max), which
    is the 4K tier when that model has one."""
    try:
        from choice_card.video_models import video_models as VM
        ultra = VM.RATES.get("ultra") or {}
    except Exception:                                   # pragma: no cover
        ultra = {}
    if (ultra.get("kie_model") and ultra.get("kie_model") == row.get("video_model")
            and isinstance(ultra.get("rate_usd"), (int, float))):
        return {"rate_usd": ultra["rate_usd"], "unit": ultra.get("unit", "second"),
                "shot_s": ultra.get("shot_s")}
    models, _where = _registry_models()
    for m in models or []:
        if m.get("id") != row.get("video_model"):
            continue
        pricing = m.get("pricing") or {}
        for key in ("credits_max", "credits_estimate", "credits_min"):
            cm = pricing.get(key)
            if isinstance(cm, (int, float)) and not isinstance(cm, bool):
                return {"rate_usd": float(cm) * CREDITS_USD, "unit": "second"}
    return {"rate_usd": None, "unit": None}


def ultra_state():
    """{'available': bool, 'video_model': id|None, 'rate_usd': float|None,
    'detail': str|None} -- Ultra shown, never faked (F-QM-4)."""
    row, detail = _ultra_row()
    if not row:
        return {"available": False, "video_model": None, "rate_usd": None,
                "detail": detail}
    priced = _ultra_price(row)
    return dict({"available": True, "video_model": row["video_model"],
                 "detail": None}, **priced)


def availability(mode_id):
    """Availability for any mode; only Ultra can be unavailable.

    An unknown name is refused `UNKNOWN_QUALITY_MODE`, never guessed at.
    """
    hit = _BY_KEY.get(_norm(mode_id))
    if hit is None:
        raise ModeGateError(UNKNOWN,
                            "%r is not one of the quality modes: %s"
                            % (mode_id, ", ".join(mode_ids())))
    if hit == "ultra":
        return ultra_state()
    return {"available": True, "video_model": _BY_ID[hit].get("video_model"),
            "rate_usd": None, "detail": None}


def resolve_mode(choice=None):
    """Mode id or label -> the mode row. None is not silently defaulted here;
    the gate refuses it (QUALITY_MODE_NOT_CHOSEN). An unknown name is refused
    `UNKNOWN_QUALITY_MODE`, never defaulted."""
    if choice is None:
        raise ModeGateError(NOT_CHOSEN,
                            "no quality mode recorded; no paid work may start")
    key = _norm(choice)
    if key in ("default", "none", "nochoice"):
        #: A no-choice spelling echoes the card's own "(default)" marker. The
        #: default MODE is Standard -- the mode file's own ``default`` flag, and
        #: spec 3.8 "Standard (default)". Hybrid is only RECOMMENDED, never the
        #: default, so ``recommended()`` must not answer this.
        return dict(_BY_ID[DEFAULT_MODE])
    #: A reply that echoes the card's own row -- "4. Hybrid - ... (RECOMMENDED)"
    #: or "Standard (default)" -- must resolve, the way looks.py strips the
    #: card's marker. Strip a numbered prefix and the markers, then look up.
    for mark in ("recommended", "default"):
        if key.endswith(mark) and key[:-len(mark)]:
            key = key[:-len(mark)]
    #: "1. Standard" -- the card's row number normalizes to a leading digit.
    if key and key[0].isdigit():
        key = key.lstrip("0123456789")
    hit = _BY_KEY.get(key)
    if hit is None:
        raise ModeGateError(UNKNOWN,
                            "%r is not one of the quality modes: %s"
                            % (choice, ", ".join(mode_ids())))
    row = dict(_BY_ID[hit])
    if hit == "ultra":
        row.update(ultra_state())
        if not row["available"]:
            row["reason_code"] = ULTRA_UNAVAILABLE
    return row


def require_mode(record):
    """The recorded mode of a run, or QUALITY_MODE_NOT_CHOSEN.

    ``record`` is a run record dict (see ``record_mode``), a mode id/label, or
    None. Call this before any spend."""
    if record is None:
        raise ModeGateError(NOT_CHOSEN,
                            "no quality mode recorded; no paid work may start")
    if isinstance(record, str) and os.path.isdir(record):
        #: a caller that holds the run folder, not the parsed record: read the
        #: run file here rather than report its path as an unknown mode name.
        run_dir = record
        record = read_run_mode(run_dir)
        if record is None:
            raise ModeGateError(
                NOT_CHOSEN,
                "no %s under %s: no paid work may start until the run owner's "
                "pick is recorded" % (RUN_FILE, run_dir))
    if isinstance(record, dict):
        choice = record.get("mode") or record.get("quality_mode")
        if not choice:
            raise ModeGateError(NOT_CHOSEN,
                                "the run record has no quality mode; no paid "
                                "work may start")
        return resolve_mode(choice)
    return resolve_mode(record)


def gate(record):
    """Alias for ``require_mode``: keeps the call site reading as a gate."""
    return require_mode(record)


def mode_prices():
    """The mode price table (references/quality-modes.json, ``mode_prices``)."""
    return MODE_PRICES


def estimate(mode, seconds, hero_seconds=0):
    """Plain cost estimate in USD and credits for ``seconds`` of shots.

    Hybrid prices Standard seconds plus the Premium delta on ``hero_seconds``.
    Ultra's price comes from the live-registry model it resolves to. A mode
    that truly has no price is refused ``PRICE_MISSING``; nothing else is.
    """
    m = mode if isinstance(mode, dict) else resolve_mode(mode)
    mid = m["id"]
    seconds = float(seconds)
    if mid == "ultra":
        if not m.get("available", True):
            raise ModeGateError(ULTRA_UNAVAILABLE,
                                m.get("detail") or "no live 4K model qualifies")
        rate = m.get("rate_usd")
        if rate is None:
            raise ModeGateError(PRICE_MISSING, "Ultra has no measured price")
        if m.get("unit") == "clip":
            # a per-clip 4K price: one clip per shot_s seconds of runtime
            shot_s = float(m.get("shot_s") or 8)
            usd = float(rate) * int(-(-seconds // shot_s))
        else:
            usd = float(rate) * seconds
    else:
        row = MODE_PRICES.get(mid) or {}
        rate = row.get("rate_usd")
        if rate is None:
            raise ModeGateError(PRICE_MISSING, "%s has no measured price" % mid)
        usd = float(rate) * seconds
        if mid == "hybrid":
            hero = float(row.get("hero_rate_usd") or rate)
            usd += (hero - float(rate)) * float(hero_seconds)
    source = ("the live registry model it resolved to"
              if mid == "ultra" and m.get("unit") != "clip"
              else "references/quality-modes.json")
    return {"state": "ok", "mode": mid, "seconds": seconds,
            "usd": round(usd, 4), "credits": round(usd / CREDITS_USD, 2),
            "price_source": source}


# ---------------------------------------------------------------- records ----
RUN_FILE = "storyboard/quality-mode.json"
RUN_SCHEMA = "blackceo.quality-mode/v1"

SHOT_SCHEMA = "blackceo.quality-mode/shot/v1"
#: F-QM-6: read from the ONE file, so the schema and its plain-words rules can
#: never drift from what the gate enforces.
SHOT_FIELDS = tuple(_DOC.get("shot_fields") or ())
if not SHOT_FIELDS:
    raise RuntimeError("references/quality-modes.json carries no shot_fields")
SHOT_FIELD_RULES = dict(_DOC.get("shot_field_rules") or {})

#: The shot's picture route: the Shot Router's four routes (3E.1). Every clip is
#: image-to-video from its own checked keyframe; text-to-video is refused
#: (N-32). TWO-PICTURE is the only one that needs a model accepting both first
#: and last pictures in one request (3E.3). The allow-list must be the router's
#: own ids, or a builder threading a routed shot is refused for the right answer.
PICTURE_MODES = ("one-picture", "two-picture", "nine-picture", "lip-sync")
#: Spellings a builder may hand over for those four routes: the plan's capitals,
#: the router's snake_case, or the hyphen form. Normalised, never guessed.
_PICTURE_MODE_ALIASES = {
    "one-picture": "one-picture", "onepicture": "one-picture",
    "two-picture": "two-picture", "twopicture": "two-picture",
    "nine-picture": "nine-picture", "ninepicture": "nine-picture",
    "lip-sync": "lip-sync", "lipsync": "lip-sync",
}


def picture_mode_id(value):
    """A shot's ``picture_mode`` in canonical form, or None when off the list."""
    return _PICTURE_MODE_ALIASES.get(_norm(value))


def record_mode(mode, chosen_by, at, source="card", hero_seconds=0, extra=None):
    """The run record written to ``storyboard/quality-mode.json``."""
    m = mode if isinstance(mode, dict) else resolve_mode(mode)
    rec = {
        "schema": RUN_SCHEMA,
        "run_file": RUN_FILE,
        "mode": m["id"],
        "label": m["label"],
        "recommended": bool(m.get("recommended")),
        "video_model": m.get("video_model"),
        "max_resolution": m.get("max_resolution"),
        "available": bool(m.get("available", True)),
        "chosen_by": chosen_by,
        "at": at,
        "source": source,
        "hero_seconds": hero_seconds,
    }
    if m["id"] == "ultra" and not m.get("available", True):
        rec["unavailable_code"] = ULTRA_UNAVAILABLE
        rec["detail"] = m.get("detail")
    if extra:
        rec.update(extra)
    return validate_run(rec)


def validate_run(doc):
    """Check the run record before it is written. Returns it unchanged."""
    if not isinstance(doc, dict):
        raise SchemaError("RUN_INVALID", "quality-mode record must be a dict")
    for key in ("schema", "mode", "chosen_by", "at"):
        if not doc.get(key):
            raise SchemaError("RUN_FIELD_MISSING",
                              "quality-mode record is missing %r" % key)
    if doc["mode"] not in _BY_ID:
        raise SchemaError(UNKNOWN, "%r is not a quality mode" % doc["mode"])
    return doc


def _write_run_file(run_dir, doc):
    path = os.path.join(run_dir, RUN_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return path


def write_run_mode(run_dir, mode, chosen_by, at, **kw):
    """Record the mode pick on a run and write its run file. Returns (doc, path)."""
    doc = record_mode(mode, chosen_by=chosen_by, at=at, **kw)
    return doc, _write_run_file(run_dir, doc)


def read_run_mode(run_dir):
    """The run's recorded mode record, or None when it has not picked yet."""
    path = os.path.join(run_dir, RUN_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return None


def shot_record(picture_mode, reason, reference_image_ids, look_drifted,
                video_model=None, max_resolution=None, schema=True):
    """The six shot fields (F-QM-6), validated. ``schema`` adds the shot tag."""
    rec = {
        "picture_mode": picture_mode,
        "picture_mode_reason": reason,
        "reference_image_ids": list(reference_image_ids or []),
        "look_drifted": bool(look_drifted),
        "video_model": video_model,
        "max_resolution": max_resolution,
    }
    if schema:
        rec["schema"] = SHOT_SCHEMA
    return validate_shot(rec)


def validate_shot(shot):
    """Check a shot's quality-mode fields. Returns it unchanged."""
    if not isinstance(shot, dict):
        raise SchemaError("SHOT_INVALID", "shot fields must be a dict")
    missing = [k for k in SHOT_FIELDS if k not in shot]
    if missing:
        raise SchemaError("SHOT_FIELD_MISSING",
                          "shot is missing: %s" % ", ".join(missing))
    if picture_mode_id(shot["picture_mode"]) is None:
        raise SchemaError("PICTURE_MODE_UNKNOWN",
                          "%r is not one of the four routes %s"
                          % (shot["picture_mode"], PICTURE_MODES))
    if not isinstance(shot["reference_image_ids"], list):
        raise SchemaError("REFERENCE_IMAGE_IDS_INVALID",
                          "reference_image_ids must be a list")
    #: The five resolutions are the whole allowed set (shot_field_rules). None
    #: means "not set yet" and is left to the builder; any other value is a
    #: wrong cap that would ride into a request, so it is refused here.
    if shot["max_resolution"] is not None and \
            shot["max_resolution"] not in RESOLUTIONS:
        raise SchemaError("MAX_RESOLUTION_UNKNOWN",
                          "%r is not one of %s"
                          % (shot["max_resolution"], RESOLUTIONS))
    return shot


def apply_to_request(request, shot):
    """Thread the six shot fields into a request object (F-QM-6).

    Returns a copy; the caller's request is never mutated. The fields ride at
    the top level beside model/input, the same place make_h3_request.py keeps
    ``shot_id`` and the receipts."""
    validate_shot(shot)
    out = dict(request)
    for key in SHOT_FIELDS:
        out[key] = shot[key]
    out["quality_mode_schema"] = SHOT_SCHEMA
    return out


# ------------------------------------------------------------ name aliases ----
#: The __init__ surface other units import. Kept as plain aliases so there is
#: one implementation of each behaviour above.

QualityModeError = ModeGateError           # the refusal class, one name per site
MODES_BY_ID = _BY_ID
RECOMMENDED_MODE = recommended()
DEFAULT_MODE = next((m["id"] for m in MODES if m.get("default")),
                    RECOMMENDED_MODE)
SPEC = _DOC

load = _load
read_mode = read_run_mode


def ultra_model(explicit=None):
    """The live-registry row Ultra resolves to, or None (never faked)."""
    row, _reason = _ultra_row()
    return row


def mode_rows():
    """The card's four rows, in card order, each with its plain-words line."""
    out = []
    for m in MODES:
        row = dict(m)
        row["recommended"] = (m["id"] == recommended())
        if m["id"] == "ultra":
            st = ultra_state()
            row.update(st)
            if not st["available"]:
                row["reason_code"] = ULTRA_UNAVAILABLE
        out.append(row)
    return out


def mode_card_text(length_seconds=None, n=None, total=None):
    """The card as the client reads it: numbered mode rows, Hybrid recommended.

    The header is `Question <n> of <total> - QUALITY MODE` (spec section 1:
    the card prints its own numbers and no document states a total). Called
    without them it prints `Question - QUALITY MODE`, the unnumbered form the
    spec block shows.

    A plain-words price appears on a row only where the table carries one; an
    unpriced row says so rather than showing a made-up figure.
    """
    header = ("Question %d of %d - QUALITY MODE" % (n, total)
              if n and total else "Question - QUALITY MODE")
    lines = [header, "How polished should your shots be?"]
    for i, row in enumerate(mode_rows(), 1):
        mark = " (RECOMMENDED)" if row["id"] == recommended() else ""
        price = ""
        if length_seconds:
            try:
                est = estimate(row, length_seconds)
                price = " - about $%.2f" % est["usd"]
                if row["id"] == "hybrid":
                    # the hero shots' Premium seconds are chosen per shot by the
                    # Shot Router; that cost lands on the final card through the
                    # same table, never as a made-up share here.
                    price += " (hero shots priced on the final card)"
            except ModeGateError as e:
                price = (" - not available on this box"
                         if e.code == ULTRA_UNAVAILABLE
                         else " - price unavailable (%s)" % e.code)
        elif row["id"] == "ultra" and not row.get("available", True):
            price = " - not available on this box"
        lines.append("%d. %s - %s%s%s" % (i, row["label"], row["blurb"], price,
                                         mark))
    return "\n".join(lines)


def shot_problems(shot):
    """Every problem with a shot's quality-mode fields, as (code, detail)."""
    problems = []
    if not isinstance(shot, dict):
        return [("SHOT_INVALID", "shot fields must be a dict")]
    for key in SHOT_FIELDS:
        if key not in shot:
            problems.append(("SHOT_FIELD_MISSING", key))
    if "picture_mode" in shot and picture_mode_id(shot["picture_mode"]) is None:
        problems.append(("PICTURE_MODE_UNKNOWN", str(shot["picture_mode"])))
    if "reference_image_ids" in shot and \
            not isinstance(shot["reference_image_ids"], list):
        problems.append(("REFERENCE_IMAGE_IDS_INVALID", "not a list"))
    if "max_resolution" in shot and shot["max_resolution"] is not None \
            and shot["max_resolution"] not in RESOLUTIONS:
        problems.append(("MAX_RESOLUTION_UNKNOWN",
                         str(shot["max_resolution"])))
    return problems


def require_shot(shot):
    """The shot's six fields, or SchemaError naming every problem at once."""
    problems = shot_problems(shot)
    if problems:
        raise SchemaError(problems[0][0],
                          "; ".join("%s %s" % p for p in problems))
    return validate_shot(shot)


def shot_stamp(shot):
    """A short fingerprint of a shot's quality-mode fields, for receipts."""
    import hashlib
    payload = json.dumps({k: shot.get(k) for k in SHOT_FIELDS},
                         sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]
