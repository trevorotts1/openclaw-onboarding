"""card_render — the one-click choice card with real dollar figures (B4).

Every dollar figure on the card comes from Skill 74 ``price`` through the
price extension (``catalog_calculator.extensions``), the single price
authority (plan 5.4, choice-card-spec section 4). This module never computes
a rate: it renders rows, and the row prices come from the priced envelope the
extension returns. When any live rate cannot be read the card says "Price
unavailable" and refuses to approve — paid work never starts on a partial
price (choice-card-spec 4.3-4.4, fail closed).

The rows are ``INSTRUCTIONS.md`` lines 213-221, in order: Length, Shape,
Style, Music, Voice, Clips, Video model. The total line carries the 20%
retake allowance the same way the paid extension does (plan 4.1).

``price_fn`` is the Skill 74 ``price`` adapter (or any callable that answers
the same JSON for ``(model, units)``). With no ``price_fn`` the card renders
unpriced: rows only, "Price unavailable" total, approval blocked.

Stdlib only. No network: the price callable is injected.
"""
import os
import sys

try:  # package import (core.catalog_calculator)
    from .extensions import price_card_ext
    from .extensions import base_bridge
except ImportError:  # script import from inside this directory
    from extensions import price_card_ext                 # type: ignore
    from extensions import base_bridge                    # type: ignore

try:
    from choice_card.looks import looks as LOOKS
    from choice_card.video_models import video_models as VM
    from music_styles import music_styles as MS
except ImportError:
    _CORE_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _CORE_HERE not in sys.path:
        sys.path.insert(0, _CORE_HERE)
    from choice_card.looks import looks as LOOKS          # type: ignore
    from choice_card.video_models import video_models as VM  # type: ignore
    from music_styles import music_styles as MS           # type: ignore

UNIT_NAME = "catalog-calculator.card-render"

#: The card rows, in INSTRUCTIONS.md 213-221 order.
CARD_ROWS = ("Length", "Shape", "Style", "Music", "Voice", "Clips",
             "Video model")

#: Skill 74 model ids behind each row's priced work (fixture + D5 default).
DEFAULT_VIDEO_MODEL = "minimax-h3/image-to-video"   # MiniMax H3 at 768P (D5)
DEFAULT_IMAGE_MODEL = "google/imagen4-fast"         # one keyframe per shot
DEFAULT_MUSIC_MODEL = "ai-music-api/generate"       # one Suno generation

#: Length row -> seconds, for pricing and shot maths.
LENGTH_SECONDS = {
    "60 seconds": 60,
    "90 seconds": 90,
    "3 minutes": 180,
    "5 minutes": 300,
    "10-minute long version": 600,
}

#: Length row -> offered clip line (INSTRUCTIONS.md row 6).
CLIPS_OFFER = {
    "60 seconds": "not offered (60/90-second lengths only)",
    "90 seconds": "not offered (60/90-second lengths only)",
    "3 minutes": "not offered (clips are a 5/10-minute option)",
    "5 minutes": "automatic 60-second and 90-second clips",
    "10-minute long version": "automatic 60-second and 90-second clips",
}

RETAKE_RATE = 0.20  # plan 4.1; the extension applies the same rate


def _cents(value):
    return int(round(float(value) * 100))


def default_choice(card, model=None):
    """The D5/D24 default choice for one ad, from a card's five fields.
    ``model`` is the client's video model table entry (default: H3).

    Batch cards choose the five fields once; this turns them into the
    calculator's ``choice`` + shipped fixtures, so a card renders with real
    prices without any operator path or catalog sync state.
    """
    length = LENGTH_SECONDS.get(str(card.get("length") or "60 seconds"), 60)
    shape = str(card.get("shape") or "9:16")
    shapes = ("9:16", "16:9") if shape == "both" else (shape if shape in
                                                       ("9:16", "16:9") else "9:16",)
    return {
        "length_seconds": length,
        "shapes": list(shapes),
        "model": (model or VM.chosen())["kie_model"],
        "music_model": DEFAULT_MUSIC_MODEL,
        "image_model": DEFAULT_IMAGE_MODEL,
        "main_characters": card.get("main_characters") or 1,
    }


def price_envelope(card, price_fn, state_store=None, run_id=None, catalog=None):
    """THE price: the question, the final card and batch all call this.

    The client's model comes from card["video_model"] (option number) or the run
    state lock; the video line is priced at the resolution the factory renders,
    everything else (pictures, song, lip-sync) through ``price_fn``.
    Returns (envelope, model_entry).
    """
    m = VM.chosen(state_store, run_id, card.get("video_model"))
    env = price_card_ext(default_choice(card, m), VM.catalog_for(m, catalog or _load_shipped_catalog()),
                         VM.rated_price_fn(m, price_fn))
    return env, m


def quote(n, length_label):
    """Question price for option n at the chosen length: the card's own total
    with its 20% redo allowance, in dollars (None if the card cannot price it)."""
    env, _m = price_envelope({"length": length_label, "video_model": n}, None)
    card = env.get("card") if env.get("state") == "ok" else None
    return card["spending_limit_usd"] if card else None


def _row_values(card, model=None):
    """The seven INSTRUCTIONS.md row values in card order."""
    shape = str(card.get("shape") or "9:16")
    voice = str(card.get("voice") or "all-suno")
    voice_label = {"all-suno": "All Suno", "velvet-voiceover":
                   "Velvet Voiceover"}.get(voice, voice)
    return {
        "Length": str(card.get("length") or "60 seconds"),
        "Shape": shape,
        "Style": _style_label(card.get("style")),
        "Music": _music_label(card.get("music")),
        "Voice": voice_label,
        "Clips": CLIPS_OFFER.get(str(card.get("length") or "60 seconds"),
                                 "automatic 60-second and 90-second clips"),
        "Video model": VM.row_label(model or VM.chosen(None, None, card.get("video_model"))),
    }


def _style_label(style_id):
    try:
        return LOOKS.LOOK_LABELS.get(style_id, style_id or "Lifelike 3D")
    except Exception:
        return str(style_id or "Lifelike 3D")


def _music_label(music_id):
    try:
        return MS.style(music_id).get("label", music_id or "Soul Ballad")
    except Exception:
        return str(music_id or "Soul Ballad")


def render(card, price_fn, state_store=None, run_id=None):
    """The one-click card in plain text, dollar figures included.

    ``card`` is any card dict with the five once-chosen fields (batch make_card
    or the intake card). ``price_fn`` is the Skill 74 ``price`` adapter
    ``(model, units) -> JSON``; None means render unpriced.

    Returns (text, priced_ok). The card always renders every row; a card
    whose price cannot be read says "Price unavailable" on the total and is
    safe to show, and approval must stay blocked (fail closed, 4.4).
    """
    model = VM.chosen(state_store, run_id, card.get("video_model"))
    values = _row_values(card, model)
    lines = []
    priced_ok = False
    total = None
    envelope = None

    if price_fn is not None:
        # The shipped catalog is data in the repo, never an operator path.
        try:
            envelope, _m = price_envelope(card, price_fn, state_store, run_id)
            ok_card = envelope.get("card") if envelope.get("state") == "ok" else None
            if ok_card:
                priced_ok = True
                total = ok_card["price_usd"]
                row_dollars = _row_dollars(ok_card)
            else:
                row_dollars = None
        except Exception:
            priced_ok = False
            row_dollars = None
    else:
        row_dollars = None

    for row in CARD_ROWS:
        figure = "$%.2f" % row_dollars[row] if (row_dollars and row in row_dollars) else ""
        lines.append("  %-12s %s%s" % (row + ":", values[row],
                                       ("   " + figure) if figure else ""))

    plan = ((envelope or {}).get("card") or {}).get("image_plan") if priced_ok else None
    if plan:
        lines.append("  %-12s %d character reference pictures + %d shot pictures "
                     "(added $%.2f for the reference pictures, included in the total)"
                     % ("Images:", plan["reference_images"], plan["keyframe_images"],
                        plan["reference_set_usd"]))
    if priced_ok and total is not None:
        retake = ok_card["retake_allowance_usd"]
        lines.append("")
        lines.append("  %-12s $%.2f + $%.2f retake allowance (20%%) = $%.2f"
                     % ("Total:", total, retake, ok_card["spending_limit_usd"]))
    else:
        lines.append("")
        lines.append("  %-12s Price unavailable -- media generation pricing is "
                     "not readable, nothing starts" % "Total:")
        reasons = [str(r) for r in ((envelope or {}).get("reasons") or [])]
        if reasons:
            lines.append("  (%s)" % "; ".join(reasons[:4]))
    return "\n".join(lines), priced_ok


def _load_shipped_catalog():
    """The repository fixtures catalog (data in the repo, no operator path)."""
    import json
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "extensions", "fixtures", "catalog.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _row_dollars(priced_card):
    """Row -> USD, from the priced envelope's line items.

    Row prices: Length and Shape are realized by the video line (the video
    job is length x shapes), Style by the keyframe/image line, Music by the
    one Suno generation. Voice and Clips are free rows (cutting is free).
    """
    by_component = {}
    for li in priced_card.get("line_items") or []:
        component = li.get("component") or "video"
        by_component[component] = float(li.get("usd") or 0.0)
    video = by_component.get("video", 0.0)
    image = by_component.get("image", 0.0)
    music = by_component.get("music", 0.0)
    lip_sync = by_component.get("lip_sync", 0.0)
    return {
        "Length": video,
        "Shape": image,       # keyframes are per shot per shape
        "Style": image + lip_sync,
        "Music": music,
        "Voice": music,       # All Suno: the song IS the voice
        "Clips": 0.0,         # cutting is free (no new AI media)
        "Video model": video,
    }


def price_fn_default(adapter_path=None):
    """Skill 74 ``price`` adapter for an installed 74-kie-live-adapter.

    None adapter path -> the one found by the video router's own search
    order. Returns None when no adapter exists on this machine; callers then
    render "Price unavailable" (fail closed), never a made-up number.
    """
    import json
    import subprocess as _sp
    script = _find_adapter(adapter_path)
    if script is None:
        return None

    def run(model, units):
        proc = _sp.run([sys.executable, script, "price", "--model", model,
                        "--units", str(units)],
                       capture_output=True, text=True, timeout=60)
        try:
            resp = json.loads(proc.stdout)
        except ValueError:
            resp = {"state": "fail", "error": {
                "code": "bad_response",
                "msg": "skill74 printed no JSON (rc=%s)" % proc.returncode}}
        # The live adapter answers state success/fail; the calculator's
        # contract (unit V2-W0-U2) says ok/fail. Translate here, never in
        # the copied calculator, so its own suite keeps its semantics.
        if isinstance(resp, dict) and resp.get("state") == "success":
            resp = dict(resp, state="ok")
        return resp
    return run


def _find_adapter(explicit=None):
    """Absolute path of kie_live_adapter.py, or None."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get("DSAF_SKILL74_ADAPTER")
    if env and os.path.isfile(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    for _ in range(6):  # catalog_calculator -> core -> 75 -> onboarding root
        probe = os.path.join(root, "74-kie-live-adapter", "scripts",
                             "kie_live_adapter.py")
        if os.path.isfile(probe):
            return probe
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    return None