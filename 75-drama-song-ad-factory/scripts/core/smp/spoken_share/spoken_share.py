#!/usr/bin/env python3
"""spoken_share.py: the spoken-share limit the SMP weekly ad runs under.

Owner unit AF-SMP-U2 — Decision log 36-37 applied to Skill 35 (owner
2026-10-07), plan 6.15. stdlib only, zero paid calls.

The rule (owner words, one place only):

  * target **45 percent** of the runtime;
  * hard band: never more than **55 percent**, never less than **40
    percent**, for every length and every music style;
  * **rap counts as spoken** — it is talking over a beat, so a rap-heavy
    weekly ad cannot measure under the floor by accident;
  * the spoken opener stays short and the **first sung line starts within
    about 10 seconds**.

This module is the single authority inside ``core/smp/``: ``weekly_ad_limits``
is the one dict the planner reads, and ``scan_smp_modules`` names any other
spoken-share limit that still sits in an SMP module, so the retarget really
does replace every earlier one instead of racing it.

The module builds and judges plans only. It carries no transport of its own:
Skill 74 is the only permitted KIE path, so nothing here becomes a provider
client or spends money. stdlib only.

Deliberate scope (ponytail): a line is measured by its ``duration_s`` and
starts either at ``start_s`` or, when that is absent, at the running cursor
of the lines before it. No audio is read; the planner hands the numbers in.

Run: python3 core/smp/spoken_share/test_spoken_share.py
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "blackceo.smp.spoken-share/v1"
TOOL_VERSION = "0.1.0"
TOOL_NAME = "smp.spoken_share"
RULE_ID = "D15"

#: The step this rule rides on.
STEP = "smp-weekly-drama-song"
#: The only permitted KIE path; this module never becomes one.
KIE_PATH = "Skill 74"

SOURCE = ("Decision log 36-37 applied to Skill 35 (owner 2026-10-07); "
          "plan 6.15")

# ---- canonical numbers (owner D15 retarget on the SMP weekly ad) ----------
SPOKEN_TARGET_PCT = 45          # the target, every length, every style
SPOKEN_MAX_PCT = 55             # hard ceiling: never more than this
SPOKEN_MIN_PCT = 40             # hard floor: never less than this
FIRST_SUNG_WITHIN_SECONDS = 10  # music arrives sooner; opener stays short

#: The band the weekly ad is measured against, floor first.
SPOKEN_BAND_PCT = (SPOKEN_MIN_PCT, SPOKEN_MAX_PCT)

#: Deliveries counted toward the spoken share. Rap is spoken-style delivery
#: (D18 R&B Flow note): it counts, or a rap-heavy cut measures under the
#: floor by accident.
SPOKEN_DELIVERIES = frozenset({"spoken", "rap"})
SUNG_DELIVERIES = frozenset({"sung"})
DELIVERIES = ("spoken", "rap", "sung")

#: The limits this unit retires — the earlier hard band and the earlier
#: softer floor. Tuples only: the phrases themselves are built at import so
#: no retired band is stored here as one literal that a reader could mistake
#: for a live rule.
RETIRED_BAND_PCT: Tuple[Tuple[int, int], ...] = ((40, 70), (35, 40))

#: Per-length target tables the retarget replaces (one band for every length).
RETIRED_TABLE_NAMES = ("D15_TARGETS", "SHARE_TARGETS_BY_LENGTH")

#: The same three numbers as fractions, under the names the canonical
#: ``core/spoken_share`` package exports. Two packages answer to the top-level
#: name ``spoken_share`` -- this one under ``core/smp/``, the planner one
#: under ``core/`` -- and pytest puts ``core/smp`` on ``sys.path``, so this
#: package can be the one an ``import spoken_share`` resolves to. Carrying
#: the canonical names here keeps every reader on the identical rule (45,
#: 40, 55) whichever package wins the import, instead of an
#: ``AttributeError`` in ``core/music_styles``.
TARGET = SPOKEN_TARGET_PCT / 100.0
FLOOR = SPOKEN_MIN_PCT / 100.0
CAP = SPOKEN_MAX_PCT / 100.0

#: The one dict the planner reads. Nothing else in core/smp/ carries a limit.
def weekly_ad_limits() -> Dict[str, Any]:
    """The spoken-share limits of the SMP weekly ad — the only copy."""
    return {
        "step": STEP,
        "rule": RULE_ID,
        "target_pct": SPOKEN_TARGET_PCT,
        "min_pct": SPOKEN_MIN_PCT,
        "max_pct": SPOKEN_MAX_PCT,
        "band_pct": list(SPOKEN_BAND_PCT),
        "rap_counts_as_spoken": True,
        "first_sung_within_seconds": FIRST_SUNG_WITHIN_SECONDS,
        "source": SOURCE,
    }


#: The planner line this unit prints (plan 6.15 weekly step).
def planner_line() -> str:
    """One line the weekly ad step carries; ``check_planner_text`` reads it."""
    return (
        "Spoken share: target %d%% of the runtime, never more than %d%%, "
        "never less than %d%% — rap counts as spoken; short spoken opener; "
        "first sung line within about %d seconds"
        % (SPOKEN_TARGET_PCT, SPOKEN_MAX_PCT, SPOKEN_MIN_PCT,
           FIRST_SUNG_WITHIN_SECONDS)
    )


class SpokenShareError(Exception):
    """A refusal this block owns: an unknown delivery or a bad measurement."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__("%s: %s" % (code, message))
        self.code = code


# ---- measurement ----------------------------------------------------------
def normalize_delivery(value: Any) -> str:
    """Lower-cased, trimmed delivery label. Empty is refused, not guessed."""
    if not isinstance(value, str) or not value.strip():
        raise SpokenShareError("delivery_invalid",
                               "delivery must be a non-empty string, got %r"
                               % (value,))
    return value.strip().lower()


def counts_as_spoken(delivery: Any) -> bool:
    """True when a delivery counts toward the spoken share (rap does)."""
    return normalize_delivery(delivery) in SPOKEN_DELIVERIES


def _duration(duration_s: Any) -> float:
    """The ad's runtime as a float, refused as a named refusal not a crash."""
    try:
        return float(duration_s)
    except (TypeError, ValueError):
        raise SpokenShareError("duration_invalid",
                               "ad duration %r must be a number"
                               % (duration_s,)) from None

def _line_duration(line: Dict[str, Any]) -> float:
    if "duration_s" in line:
        value = line["duration_s"]
    elif "start_s" in line and "end_s" in line:
        value = float(line["end_s"]) - float(line["start_s"])
    else:
        raise SpokenShareError("line_duration_missing",
                               "line %r carries neither duration_s nor "
                               "start_s/end_s" % (line.get("line_id"),))
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise SpokenShareError("line_duration_invalid",
                               "line %r duration %r is not a number"
                               % (line.get("line_id"), value)) from None
    if seconds < 0:
        raise SpokenShareError("line_duration_negative",
                               "line %r duration %.3f is negative"
                               % (line.get("line_id"), seconds))
    return seconds


def spoken_seconds(lines: Iterable[Dict[str, Any]]) -> float:
    """Seconds of spoken-style delivery — spoken and rap both."""
    total = 0.0
    for line in lines:
        if not isinstance(line, dict):
            raise SpokenShareError("line_invalid",
                                   "line %r is not an object" % (line,))
        if counts_as_spoken(line.get("delivery", "spoken")):
            total += _line_duration(line)
    return total


def spoken_share_pct(lines: Iterable[Dict[str, Any]],
                     duration_s: float) -> float:
    """Spoken-style seconds as a percent of the ad's runtime (1 dp)."""
    duration = _duration(duration_s)
    if not duration > 0:
        raise SpokenShareError("duration_invalid",
                               "ad duration %r must be above zero"
                               % (duration_s,))
    return round(100.0 * spoken_seconds(list(lines)) / duration, 1)


def first_sung_start(lines: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Start of the first sung line, or None when nothing is sung.

    Rap is spoken-style, so a rap line never satisfies this rule.
    """
    cursor = 0.0
    starts: List[float] = []
    for line in lines:
        if not isinstance(line, dict):
            raise SpokenShareError("line_invalid",
                                   "line %r is not an object" % (line,))
        start = line.get("start_s", cursor)
        try:
            start = float(start)
        except (TypeError, ValueError):
            raise SpokenShareError("line_start_invalid",
                                   "line %r start %r is not a number"
                                   % (line.get("line_id"), start)) from None
        if normalize_delivery(line.get("delivery", "spoken")) in SUNG_DELIVERIES:
            starts.append(start)
        cursor = start + _line_duration(line)
    return min(starts) if starts else None


# ---- the shadow-safe read of the same rule --------------------------------
def _segment_number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise SpokenShareError("BAD_SEGMENT",
                               "segment %s %r is not a number"
                               % (field, value)) from None


def _segment_as_line(seg: Any, cursor: float) -> Dict[str, Any]:
    """One planner timing segment in this module's own line shape.

    Accepts the canonical shapes -- ``{"delivery", "seconds"}`` or
    ``{"delivery", "start", "end"}`` -- so a caller holding the canonical
    ``core/spoken_share`` record type is served by whichever package the
    interpreter resolved.
    """
    if not isinstance(seg, dict):
        raise SpokenShareError("BAD_SEGMENT",
                               "segment must be a record, got %r"
                               % (type(seg).__name__,))
    raw = seg.get("delivery")
    if (not isinstance(raw, str)
            or raw.strip().lower() not in DELIVERIES):
        raise SpokenShareError("BAD_DELIVERY",
                               "delivery must be one of %s, got %r"
                               % (list(DELIVERIES), raw))
    delivery = raw.strip().lower()
    if "seconds" in seg:
        seconds = _segment_number(seg["seconds"], "seconds")
        if seconds < 0:
            raise SpokenShareError("BAD_SEGMENT",
                                   "segment seconds must be >= 0")
        start = (_segment_number(seg["start"], "start")
                 if "start" in seg else cursor)
        if start < 0:
            raise SpokenShareError("BAD_SEGMENT",
                                   "segment start must be >= 0")
    elif "start" in seg and "end" in seg:
        start = _segment_number(seg["start"], "start")
        end = _segment_number(seg["end"], "end")
        if end < start:
            raise SpokenShareError("BAD_SEGMENT",
                                   "segment end must be >= start")
        seconds = end - start
    else:
        raise SpokenShareError("BAD_SEGMENT",
                               "segment needs seconds, or start and end")
    return {"delivery": delivery, "start_s": start, "duration_s": seconds}


def check_first_sung(segments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The first-sung-line rule as the canonical package returns it.

    ``{"verdict": PASS|FAIL, "first_sung_start_s", "opener_seconds",
    "limit_s", "reasons": [...]}``. No sung line fails -- an ad with no
    singing is what the retarget was ordered against -- and rap never
    satisfies the rule.
    """
    if not isinstance(segments, list) or not segments:
        raise SpokenShareError("BAD_SEGMENTS",
                               "segments must be a non-empty list")
    cursor = 0.0
    lines: List[Dict[str, Any]] = []
    for seg in segments:
        parsed = _segment_as_line(seg, cursor)
        lines.append(parsed)
        cursor = parsed["start_s"] + parsed["duration_s"]
    first = first_sung_start(lines)
    if first is None:
        return {
            "verdict": "FAIL",
            "first_sung_start_s": None,
            "opener_seconds": None,
            "limit_s": FIRST_SUNG_WITHIN_SECONDS,
            "reasons": ["no sung line anywhere in the plan; an ad with no "
                        "singing is rebuilt"],
        }
    reasons: List[str] = []
    if first > FIRST_SUNG_WITHIN_SECONDS:
        reasons.append("first sung line starts at %.1f s, after the %.0f s "
                       "limit (the spoken opener must stay short)"
                       % (first, FIRST_SUNG_WITHIN_SECONDS))
    return {
        "verdict": "FAIL" if reasons else "PASS",
        "first_sung_start_s": round(first, 6),
        "opener_seconds": round(first, 6),
        "limit_s": FIRST_SUNG_WITHIN_SECONDS,
        "reasons": reasons,
    }


# ---- the gate -------------------------------------------------------------
def evaluate(lines: Sequence[Dict[str, Any]],
             duration_s: float) -> Dict[str, Any]:
    """Judge one weekly ad: band, first sung line, and the reasons if not.

    Never raises on a measurement that is merely out of band — out of band
    is a *result* (``outcome`` ``fail`` with reasons), not an exception.
    """
    pct = spoken_share_pct(lines, duration_s)
    first_sung = first_sung_start(lines)
    reasons: List[str] = []
    if pct < SPOKEN_MIN_PCT:
        reasons.append("spoken share %.1f%% below the %d%% floor"
                       % (pct, SPOKEN_MIN_PCT))
    elif pct > SPOKEN_MAX_PCT:
        reasons.append("spoken share %.1f%% above the %d%% ceiling"
                       % (pct, SPOKEN_MAX_PCT))
    if first_sung is None:
        reasons.append("no sung line: the first sung line must start within "
                       "about %d seconds" % FIRST_SUNG_WITHIN_SECONDS)
    elif first_sung > FIRST_SUNG_WITHIN_SECONDS:
        reasons.append("first sung line at %.1fs, after the %d second limit"
                       % (first_sung, FIRST_SUNG_WITHIN_SECONDS))
    return {
        "step": STEP,
        "outcome": "ok" if not reasons else "fail",
        "spoken_pct": pct,
        "band_pct": list(SPOKEN_BAND_PCT),
        "target_pct": SPOKEN_TARGET_PCT,
        "first_sung_at_s": first_sung,
        "first_sung_within_seconds": FIRST_SUNG_WITHIN_SECONDS,
        "rap_counts_as_spoken": True,
        "reasons": reasons,
        "source": SOURCE,
    }


def spoken_budget(duration_s: float) -> Dict[str, float]:
    """The spoken seconds the weekly ad plans to, and the band around it."""
    duration = _duration(duration_s)
    if not duration > 0:
        raise SpokenShareError("duration_invalid",
                               "ad duration %r must be above zero"
                               % (duration_s,))
    return {
        "duration_s": duration,
        "target_s": round(duration * SPOKEN_TARGET_PCT / 100.0, 2),
        "min_s": round(duration * SPOKEN_MIN_PCT / 100.0, 2),
        "max_s": round(duration * SPOKEN_MAX_PCT / 100.0, 2),
        "first_sung_by_s": float(FIRST_SUNG_WITHIN_SECONDS),
    }


# ---- fail-closed readers: this rule replaces every other one --------------
def _retired_phrases() -> Tuple[str, ...]:
    """The retired wording, built from the tuples so it is never stored.

    Only the *ceiling* side of each retired band becomes a phrase: the floor
    side would spell the new ``never less than 40%`` wording and mark the
    live rule stale.
    """
    out: List[str] = []
    for _low, high in RETIRED_BAND_PCT:
        out.extend([
            "%d-%d" % (_low, high),
            "%d – %d" % (_low, high),
            "%d to %d" % (_low, high),
            "%d%%..%d%%" % (_low, high),
            "%d%%-%d%%" % (_low, high),
            "0.%02d..0.%02d" % (_low, high),
            "0.%02d-0.%02d" % (_low, high),
            "never above %d%%" % high,
            "never more than %d%%" % high,
        ])
    out.extend([
        "targets by length",
        "target range for one length",
        "per %s by length" % RULE_ID,
        "upper end of %s" % RULE_ID,
        RETIRED_TABLE_NAMES[0],
        RETIRED_TABLE_NAMES[1],
    ])
    return tuple(out)


#: Retired-band and per-length-table wording no SMP module may carry on.
STALE_PHRASES: Tuple[str, ...] = _retired_phrases()

#: The requirements any planner text that carries this rule must state.
_TEXT_REQUIRED = (
    ("target %d%%" % SPOKEN_TARGET_PCT, "states the 45 percent target"),
    ("never more than %d%%" % SPOKEN_MAX_PCT, "states the 55 percent ceiling"),
    ("never less than %d%%" % SPOKEN_MIN_PCT, "states the 40 percent floor"),
    ("rap counts as spoken", "counts rap as spoken"),
    ("first sung line within about %d seconds" % FIRST_SUNG_WITHIN_SECONDS,
     "first sung line within about 10 seconds"),
)

#: Any module-level constant that could be carrying a spoken-share limit.
_LIMIT_ASSIGNMENT = re.compile(
    r"^[ \t]*([A-Z][A-Z0-9_]{2,})[ \t]*=[ \t]*(.+?)[ \t]*(?:#.*)?$", re.M)

#: Name parts that make a constant *about* the share, not about, say, the
#: banned style words a spoken part must avoid.
_NAME_HINTS = ("SPOKEN", "SHARE", "D15", "SUNG")
_NAME_TOKENS = ("PCT", "MIN", "MAX", "TARGET", "BAND", "LIMIT", "SECONDS")

#: Constants this package owns; their value IS the limit.
_OWN_LIMIT_NAMES = frozenset({
    "SPOKEN_TARGET_PCT", "SPOKEN_MIN_PCT", "SPOKEN_MAX_PCT",
    "SPOKEN_BAND_PCT", "FIRST_SUNG_WITHIN_SECONDS", "RETIRED_BAND_PCT",
})


def _is_limit_name(name: str) -> bool:
    """True when the constant's name says it carries a spoken-share limit."""
    if any(table in name for table in RETIRED_TABLE_NAMES):
        return True                      # a by-length table is always one
    if not any(hint in name for hint in _NAME_HINTS):
        return False
    return any(token in name for token in _NAME_TOKENS)


def _number(value: str) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None                      # no inline value: an alias, not a limit
    try:
        return float(match.group(0))
    except ValueError:                   # pragma: no cover - regex guarantees
        return None


def find_competing_limits(text: str) -> List[str]:
    """Limit values written inline outside this package.

    A constant whose value is written out is another copy of the limit, even
    when the number happens to match: the retarget wants exactly one inside
    ``core/smp/``. An alias of this module's constant carries no inline value
    and is left alone.
    """
    if not isinstance(text, str):
        raise TypeError("find_competing_limits expects text, got %s"
                        % type(text).__name__)
    found: List[str] = []
    for name, value in _LIMIT_ASSIGNMENT.findall(text):
        if name in _OWN_LIMIT_NAMES or not _is_limit_name(name):
            continue
        if _number(value) is None:
            continue
        found.append("%s = %s" % (name, value.strip()))
    return found


def find_stale_limits(text: str) -> List[str]:
    """Retired-band and per-length wording found in text (empty = clean)."""
    if not isinstance(text, str):
        raise TypeError("find_stale_limits expects text, got %s"
                        % type(text).__name__)
    return [phrase for phrase in STALE_PHRASES if phrase in text]


def check_planner_text(text: str) -> List[str]:
    """Requirements a planner text is missing (empty = it carries D15)."""
    if not isinstance(text, str):
        raise TypeError("check_planner_text expects text, got %s"
                        % type(text).__name__)
    haystack = text.lower()
    reasons = [why for needle, why in _TEXT_REQUIRED
               if needle.lower() not in haystack]
    reasons += ["retired limit wording present: %r" % phrase
                for phrase in find_stale_limits(text)]
    return reasons


def scan_smp_modules(root: Optional[str] = None) -> Dict[str, List[str]]:
    """Every other spoken-share limit still sitting in an SMP module.

    Walks ``core/smp/`` and returns ``{path: findings}``; empty means this
    module is the only limit left. This package's own directory is skipped:
    it is the file that names the retired bands in order to detect them.
    """
    if root is None:
        root = os.path.join(build_root(), "core", "smp")
    own_dir = os.path.dirname(os.path.abspath(__file__))
    findings: Dict[str, List[str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if not name.endswith((".py", ".md")):
                continue
            path = os.path.join(dirpath, name)
            if os.path.dirname(os.path.abspath(path)) == own_dir:
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeDecodeError) as exc:
                findings[path] = ["unreadable: %s" % exc]
                continue
            hits = find_stale_limits(text) + find_competing_limits(text)
            if hits:
                findings[path] = hits
    return findings


def build_root() -> str:
    """Directory that owns core/ — found by walking up, never hard-coded."""
    parent = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(parent, "core")):
            return parent
        up = os.path.dirname(parent)
        if up == parent:
            break
        parent = up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


__all__ = [
    "CAP",
    "DELIVERIES",
    "FIRST_SUNG_WITHIN_SECONDS",
    "FLOOR",
    "KIE_PATH",
    "RETIRED_BAND_PCT",
    "RETIRED_TABLE_NAMES",
    "RULE_ID",
    "SCHEMA_VERSION",
    "SOURCE",
    "SPOKEN_BAND_PCT",
    "SPOKEN_DELIVERIES",
    "SPOKEN_MAX_PCT",
    "SPOKEN_MIN_PCT",
    "SPOKEN_TARGET_PCT",
    "STEP",
    "STALE_PHRASES",
    "SUNG_DELIVERIES",
    "SpokenShareError",
    "TARGET",
    "TOOL_NAME",
    "TOOL_VERSION",
    "build_root",
    "check_first_sung",
    "check_planner_text",
    "counts_as_spoken",
    "evaluate",
    "find_competing_limits",
    "find_stale_limits",
    "first_sung_start",
    "normalize_delivery",
    "planner_line",
    "scan_smp_modules",
    "spoken_budget",
    "spoken_seconds",
    "spoken_share_pct",
    "weekly_ad_limits",
]
