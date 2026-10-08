"""Music styles D18: the three offered styles and their Suno style prompts,
plus the D15 spoken-share target each one carries. stdlib only, no network.

Owner decisions (2026-10-07):
  D18 - exactly three styles are offered: Soul Ballad, R&B Flow, Soul Rise.
  D15 retarget (Decision log 37, plan 6.7) - spoken-style delivery targets
        45% of runtime, never more than 55%, never less than 40%, for EVERY
        length and EVERY style; rap is spoken-style delivery. The earlier
        wider ceiling and the per-length targets are retired: there is one
        band now, not a table. The spoken opener stays short and the first
        sung line starts within about 10 seconds.

Enforcement lives here: check_share() refuses any spoken share outside
0.40..0.55 for every style and every length. The three numbers are read
from core/spoken_share (the single source for the retarget), never kept as
a second copy here. Voice gender is NOT ours -- that is V2B-AUDIO-U1
(core/audio_c3), so prompts say "lead vocal" only.
"""
from __future__ import annotations

from math import isfinite

try:
    import spoken_share as _SS                      # core/ on sys.path
except ImportError:                                 # imported as core.*
    from .. import spoken_share as _SS

TOOL_NAME = "music_styles"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.music-styles/v1"

#: Owner D15 hard band, as fractions of total runtime. One band: every
#: style, every length. Sourced from core/spoken_share so it cannot drift.
SPOKEN_SHARE_TARGET = _SS.TARGET
SPOKEN_SHARE_MIN = _SS.FLOOR
SPOKEN_SHARE_MAX = _SS.CAP
#: Music arrives sooner: the spoken opener is short and the first sung line
#: starts within about this many seconds (owner D12 + D15 retarget). The
#: planner-side rule itself lives in core/spoken_share and is re-exported
#: here so the planner/QC read one copy of it.
FIRST_SUNG_WITHIN_SECONDS = _SS.FIRST_SUNG_WITHIN_SECONDS
check_first_sung = _SS.check_first_sung

#: Offered lengths (owner D6 + D23) -> accepted spellings.
LENGTH_ALIASES = {
    "60": 60, "60s": 60, "60sec": 60, "60seconds": 60,
    "90": 90, "90s": 90, "90sec": 90, "90seconds": 90,
    "180": 180, "3m": 180, "3min": 180, "3minutes": 180,
    "300": 300, "5m": 300, "5min": 300, "5minutes": 300,
    "600": 600, "10m": 600, "10min": 600, "10minutes": 600,
}

#: Every length the factory offers. The D15 band is keyed by NONE of them --
#: this tuple only bounds what a caller may ask about.
OFFERED_LENGTHS_S = (60, 90, 180, 300, 600)

#: Delivery labels a timing segment may carry.
DELIVERIES = ("spoken", "rap", "sung")

#: Rap is spoken-style delivery (D18 table, R&B Flow note). Counting it is
#: what stops a rap-heavy cut from measuring under the cap by accident.
SPOKEN_STYLE_DELIVERIES = frozenset({"spoken", "rap"})

SOURCE_D18 = "Owner D18 2026-10-07, plan 6.7"
SOURCE_D15 = "Owner D15 retarget 2026-10-07, Decision log 37; plan 6.7"


class MusicStyleError(Exception):
    """Unknown style, unknown length, or a malformed measurement input."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


#: The three offered styles (D18). Prompts are Suno style-field text: comma
#: separated tags, no lyric text, no character gender (voice casting is U1).
#: Every style carries the SAME D15 share rule: one band, not a table.
_SHARE_RULE = ("target %d%% of runtime, never more than %d%%, never less "
               "than %d%% (rap counts as spoken)"
               % (_SS.SPOKEN_TARGET_PCT, _SS.SPOKEN_MAX_PCT,
                  _SS.SPOKEN_MIN_PCT))
STYLES = {
    "soul-ballad": {
        "style_id": "soul-ballad",
        "label": "Soul Ballad",
        "sound": "Slow, emotional, soulful singing",
        "share_rule": _SHARE_RULE,
        "notes": ("The original drama-song style."),
        "suno_style_prompt": (
            "soul ballad, slow emotional 62-68 bpm, warm felt piano, "
            "swelling analog strings, brushed kit entering at the chorus, "
            "deep rounded bass, soulful lead vocal with melismatic runs, "
            "gospel-tinged backing harmonies, minor key, intimate verse "
            "opening into a full-throated chorus, long held final note, "
            "clean cinematic studio mix, no distortion"
        ),
    },
    "rnb-flow": {
        "style_id": "rnb-flow",
        "label": "R&B Flow",
        "sound": "Rap verses with a smooth sung R&B hook",
        "share_rule": _SHARE_RULE,
        "notes": ("Like the One Check Chanel reference. Approved example: "
                  "Version F (final-9x16-h3-F-3d-rnb-rap.mp4, lifelike 3D), "
                  "Trevor 2026-10-07: a keeper."),
        "suno_style_prompt": (
            "contemporary r&b with hip-hop flow, 84-94 bpm, crisp programmed "
            "drums with tight hats, deep sub bass, Rhodes chord stabs, airy "
            "synth plucks, rhythmic rap verses delivered with clear diction "
            "over the beat, smooth sung r&b hook, call-and-response ad-libs, "
            "confident swagger, radio-ready mix, no vocals in the intro pad"
        ),
    },
    "soul-rise": {
        "style_id": "soul-rise",
        "label": "Soul Rise",
        "sound": ("Starts slow and soulful through the pain, lifts into an "
                  "upbeat groove at the turning point (mentor / product)"),
        "share_rule": _SHARE_RULE,
        "notes": ("The tempo lift lands on the story's turn."),
        "suno_style_prompt": (
            "soul with a two-part arc, brooding 62-68 bpm opening lifting to "
            "an upbeat 100-112 bpm groove at the turn, warm piano and round "
            "bass foundation, percussion thickening as it lifts, triumphant "
            "horn stabs and claps from the turnaround, hopeful minor-to-major "
            "resolution, soulful lead vocal rising in register, gospel-tinged "
            "backing choir, polished commercial mix, single continuous take"
        ),
    },
}

#: Recommended Suno section tags for the arc, keyed by style. Advisory only:
#: the lyric writer owns line text, this owns the style field.
SECTION_HINTS = {
    "soul-ballad": "[Verse] slow and close, [Pre-Chorus] lift, "
                   "[Chorus] full voice, [Bridge] stripped back",
    "rnb-flow": "[Verse] rap, [Hook] sung r&b, [Verse] rap, [Hook] sung r&b",
    "soul-rise": "[Verse] slow soul, [Build] pressure, "
                 "[Chorus] upbeat groove, [Outro] hold the lift",
}


def style_ids():
    """The three offered style ids, in the order the card lists them."""
    return tuple(STYLES)


def _style_key(style):
    """Normalize an id, a label, or a card option record to a style id."""
    if isinstance(style, dict):          # card option block {"value": ...}
        style = style.get("value", style.get("style_id"))
    if not isinstance(style, str) or not style.strip():
        raise MusicStyleError("BAD_STYLE",
                              "style must be a non-empty string, got %r"
                              % (style,))
    key = style.strip().lower()
    if key in STYLES:
        return key
    for sid, rec in STYLES.items():
        if key == rec["label"].lower():
            return sid
    raise MusicStyleError("UNKNOWN_STYLE",
                          "not one of the three D18 styles: %r" % style)


def _length_key(length):
    """Normalize a length to the seconds key the offered menu uses."""
    if isinstance(length, dict):
        length = length.get("value", length.get("seconds"))
    if isinstance(length, bool):
        raise MusicStyleError("BAD_LENGTH", "length must not be a bool")
    if isinstance(length, (int, float)):
        secs = int(round(float(length)))
        if secs in OFFERED_LENGTHS_S:
            return secs
        raise MusicStyleError("UNKNOWN_LENGTH",
                              "length %r s is not one of the offered lengths "
                              "%s" % (length, list(OFFERED_LENGTHS_S)))
    if isinstance(length, str):
        key = length.strip().lower().replace(" ", "").replace("-", "")
        if key in LENGTH_ALIASES:
            return LENGTH_ALIASES[key]
        raise MusicStyleError("UNKNOWN_LENGTH",
                              "length %r is not one of the offered lengths"
                              % length)
    raise MusicStyleError("BAD_LENGTH",
                          "length must be seconds or an id, got %r"
                          % (type(length).__name__,))


def style(style_id):
    """Full record for one style. Raises MusicStyleError on an unknown id."""
    return dict(STYLES[_style_key(style_id)])


def style_prompt(style_id):
    """Suno style-field text for one style (id or label accepted).

    Contract consumed by core/style_defaults (V2B-AUDIO-U5): returns a
    non-empty str, raises only on an unknown style id.
    """
    return STYLES[_style_key(style_id)]["suno_style_prompt"]


def section_hint(style_id):
    """Advisory Suno section-tag string for one style."""
    return SECTION_HINTS[_style_key(style_id)]


def d15_range(length):
    """The owner's D15 spoken-share band for one length: (floor, cap).

    Since the retarget the band is ONE range for every offered length --
    asking by length is kept only so existing callers keep working.
    """
    _length_key(length)
    return (SPOKEN_SHARE_MIN, SPOKEN_SHARE_MAX)


def spoken_target(style_id, length):
    """Spoken-share target for one style at one length.

    target is the point the song brief aims at (45% of runtime); floor/cap
    are the hard band (40%..55%) and they are identical for every style and
    every length. Rap counts toward the target as spoken-style delivery.

    The earlier per-length target table and the earlier per-style upper end
    are retired: there is one target now.
    """
    sid = _style_key(style_id)
    secs = _length_key(length)
    return {
        "style_id": sid,
        "label": STYLES[sid]["label"],
        "length_seconds": secs,
        "d15_min": SPOKEN_SHARE_MIN,
        "d15_max": SPOKEN_SHARE_MAX,
        "target": SPOKEN_SHARE_TARGET,
        "target_mode": "d15",
        "target_note": ("target %.0f%% of runtime; rap counts as spoken-style"
                        % (SPOKEN_SHARE_TARGET * 100.0)),
        "floor": SPOKEN_SHARE_MIN,
        "cap": SPOKEN_SHARE_MAX,
        "first_sung_within_seconds": FIRST_SUNG_WITHIN_SECONDS,
        "rap_counts_as_spoken": True,
        "source": "%s; %s" % (SOURCE_D18, SOURCE_D15),
    }


def spoken_targets(style_id=None):
    """The D15 share-target table: every offered length for one style, or
    every style x length pair when style_id is None. Every cell is the same
    band -- the table is shape, not a per-length rule."""
    sids = [_style_key(style_id)] if style_id is not None else list(STYLES)
    out = {}
    for sid in sids:
        out[sid] = {str(secs): spoken_target(sid, secs)
                    for secs in OFFERED_LENGTHS_S}
    return out


def _segment_seconds(seg):
    """Seconds one timing segment covers. Accepts seconds or start/end."""
    if not isinstance(seg, dict):
        raise MusicStyleError("BAD_SEGMENT",
                              "segment must be a record, got %r"
                              % (type(seg).__name__,))
    delivery = seg.get("delivery")
    if not isinstance(delivery, str) or delivery.strip().lower() not in DELIVERIES:
        raise MusicStyleError("BAD_DELIVERY",
                              "delivery must be one of %s, got %r"
                              % (list(DELIVERIES), delivery))
    if "seconds" in seg:
        secs = seg["seconds"]
        if isinstance(secs, bool) or not isinstance(secs, (int, float)):
            raise MusicStyleError("BAD_SEGMENT",
                                  "seconds must be a number, got %r" % (secs,))
        secs = float(secs)
    elif "start" in seg and "end" in seg:
        st, en = seg["start"], seg["end"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               for v in (st, en)):
            raise MusicStyleError("BAD_SEGMENT", "start/end must be numbers")
        secs = float(en) - float(st)
    else:
        raise MusicStyleError("BAD_SEGMENT",
                              "segment needs seconds, or start and end")
    if secs < 0:
        raise MusicStyleError("BAD_SEGMENT", "segment seconds must be >= 0")
    return delivery.strip().lower(), secs


def measure_share(segments):
    """Spoken-style share of runtime from timing segments.

    A segment is {"delivery": "spoken"|"rap"|"sung", "seconds": n} or
    {"delivery": ..., "start": a, "end": b}. Rap is spoken-style, so it is
    counted -- that is the rule that catches a rap-heavy R&B cut.

    Returns spoken/rap/sung/total seconds and share as a fraction of total.
    Total 0 is refused rather than reported as 0%.
    """
    if not isinstance(segments, list) or not segments:
        raise MusicStyleError("BAD_SEGMENTS",
                              "segments must be a non-empty list")
    seconds = dict.fromkeys(DELIVERIES, 0.0)
    for seg in segments:
        delivery, secs = _segment_seconds(seg)
        if not isfinite(secs):
            raise MusicStyleError("BAD_SEGMENT",
                                  "segment seconds must be finite, got %r"
                                  % (secs,))
        seconds[delivery] += secs
    spoken, rap, sung = (seconds[d] for d in ("spoken", "rap", "sung"))
    total = spoken + rap + sung
    if total <= 0:
        raise MusicStyleError("ZERO_RUNTIME",
                              "segments total 0 seconds; share undefined")
    spoken_style = sum(v for d, v in seconds.items()
                       if d in SPOKEN_STYLE_DELIVERIES)
    return {
        "spoken_seconds": round(spoken, 6),
        "rap_seconds": round(rap, 6),
        "sung_seconds": round(sung, 6),
        "total_seconds": round(total, 6),
        "spoken_style_seconds": round(spoken_style, 6),
        "share": round(spoken_style / total, 6),
        "rap_counts_as_spoken": True,
    }


def share_pct(share):
    """Human percent for a share fraction, rounded to one decimal."""
    return round(float(share) * 100.0, 1)


def check_share(style_id, length, share, segments=None):
    """Enforce the D15 band on one style at one length. Never raises on a
    share that is merely out of band -- that is a FAIL verdict, not an error.

    Returns {"verdict": PASS|FAIL, "share", "floor", "cap", "target",
             "reasons": [...]}. Raises MusicStyleError only for an unknown
    style/length or a malformed share, which are caller bugs.

    segments, when given, is measured first and its share is the one judged
    (rap included); share then must agree with it or the check fails closed.
    """
    target = spoken_target(style_id, length)
    if isinstance(share, bool) or not isinstance(share, (int, float)):
        raise MusicStyleError("BAD_SHARE",
                              "share must be a fraction 0..1, got %r"
                              % (type(share).__name__,))
    share = float(share)
    if not isfinite(share):
        raise MusicStyleError("BAD_SHARE", "share must be finite, got %r"
                              % (share,))
    measured = None
    if segments is not None:
        measured = measure_share(segments)
        if abs(measured["share"] - share) > 1e-6:
            return {
                "verdict": "FAIL",
                "share": share,
                "measured_share": measured["share"],
                "floor": target["floor"],
                "cap": target["cap"],
                "target": target["target"],
                "style_id": target["style_id"],
                "length_seconds": target["length_seconds"],
                "reasons": ["share %s disagrees with the timing measurement "
                            "%s (rap included)" % (share, measured["share"])],
                "measurement": measured,
                "checker_version": TOOL_VERSION,
            }
    reasons = []
    if share < 0.0 or share > 1.0:
        reasons.append("share %r is not a fraction in 0..1" % share)
    if share < target["floor"]:
        reasons.append("spoken share %.1f%% below the D15 floor %.0f%%"
                       % (share_pct(share), share_pct(target["floor"])))
    if share > target["cap"]:
        if target["target_mode"] == "d15-upper":
            reasons.append("spoken share %.1f%% above the R&B cap %.0f%% "
                           "(rap counts as spoken-style delivery)"
                           % (share_pct(share), share_pct(target["cap"])))
        else:
            reasons.append("spoken share %.1f%% above the D15 cap %.0f%% "
                           "(target %.0f%%, rap counts as spoken-style "
                           "delivery)"
                           % (share_pct(share), share_pct(target["cap"]),
                              share_pct(target["target"])))
    target_met = target["d15_min"] <= share <= target["d15_max"]
    return {
        "verdict": "FAIL" if reasons else "PASS",
        "share": share,
        "share_pct": share_pct(share),
        "floor": target["floor"],
        "cap": target["cap"],
        "target": target["target"],
        "target_range": [target["d15_min"], target["d15_max"]],
        "target_met": target_met,
        "style_id": target["style_id"],
        "length_seconds": target["length_seconds"],
        "rap_counts_as_spoken": True,
        "reasons": reasons,
        "measurement": measured,
        "checker_version": TOOL_VERSION,
    }


def refusal(style_id, length, share, segments=None):
    """Compact refusal text for a FAILED share; empty string when it passes.

    Lets a caller refuse early with one readable sentence instead of
    re-deriving the reason list.
    """
    result = check_share(style_id, length, share, segments)
    if result["verdict"] == "PASS":
        return ""
    return "REFUSED %s at %ss: %s" % (result["style_id"],
                                      result["length_seconds"],
                                      "; ".join(result["reasons"]))
