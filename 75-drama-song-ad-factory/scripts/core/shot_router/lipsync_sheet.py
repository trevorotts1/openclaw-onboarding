"""lipsync_sheet.py: splitting a two-emotion lip-sync piece (3G.5).

The expression sheet mapping and the pre-paid-job refusal live in
``expression.py`` (``sheet_for_emotion``, ``assign_sheet``,
``check_before_paid_job``, ``LIPSYNC_EXPRESSION_MISMATCH``); this module holds
the one decision that file does not: when a single lip-sync passage crosses
two emotions, it is split ONLY at a sentence boundary, and only when both
halves are whole sentences of 5 seconds or more. Otherwise the picture uses
the emotion the piece spends longer in, and the beat sheet says which.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

from .common import ShotRouterError

#: A split half must be a whole sentence of at least this many seconds (3G.5).
SPLIT_MIN_S = 5.0


def _word(value):
    return str(value or "").strip().lower()


def plan_emotion_split(piece, first_emotion, second_emotion, *, split_seconds,
                       boundary_is_sentence):
    """3G.5: split a two-emotion piece only at a whole-sentence boundary.

    Returns ``{"split": True, "first", "second"}`` when both halves are whole
    sentences of 5 s or more; otherwise ``{"split": False, "emotion": ...}``
    with the emotion the piece spends longer in.
    """
    if not isinstance(piece, dict):
        raise ShotRouterError("PIECE_INVALID", "a piece must be an object")
    length = piece.get("length_seconds")
    if isinstance(length, bool) or not isinstance(length, (int, float)):
        raise ShotRouterError(
            "PIECE_INVALID",
            "piece %r needs a numeric length_seconds" % piece.get("id"))
    if isinstance(split_seconds, bool) or not isinstance(split_seconds, (int, float)):
        raise ShotRouterError("PIECE_INVALID", "split_seconds must be a number")
    if not boundary_is_sentence:
        return _no_split(length, first_emotion, second_emotion, split_seconds,
                         "the split is not at a sentence boundary")
    if split_seconds < SPLIT_MIN_S:
        return _no_split(length, first_emotion, second_emotion, split_seconds,
                         "the first half is under %.0f s" % SPLIT_MIN_S)
    if (length - split_seconds) < SPLIT_MIN_S:
        return _no_split(length, first_emotion, second_emotion, split_seconds,
                         "the second half is under %.0f s" % SPLIT_MIN_S)
    return {
        "split": True,
        "first": {"emotion": _word(first_emotion), "seconds": float(split_seconds)},
        "second": {"emotion": _word(second_emotion),
                   "seconds": round(float(length) - split_seconds, 3)},
        "reason": "both halves are whole sentences of at least %.0f s" % SPLIT_MIN_S,
    }


def _no_split(length, first, second, split_seconds, reason):
    longer = first if split_seconds >= length - split_seconds else second
    return {
        "split": False,
        "emotion": _word(longer),
        "reason": reason + "; the picture uses the emotion the piece spends "
                  "longer in",
    }
