#!/usr/bin/env python3
"""rap_check: the rap-versus-sung gate. FAIL-CLOSED, no invented threshold.

The failed run measured `controls.rap_control` as UNMEASURED with the reason
recorded: "no independently labelled rap audio control available; non-sung !=
rap". The existing detector (song_contract) is sung / not-sung only. Non-sung
alone must NEVER earn a rap PASS.

So this module does NOT prescribe a cadence number and does NOT ship an
automatic rap classifier. It requires a LABELLED fixture set -- a POSITIVE real
rap control plus a sung negative and a spoken-over-beat negative -- and returns
UNMEASURED until that fixture exists. UNMEASURED blocks a take PASS (QC 17.8: no
evidence supplied; cannot pass). Nothing here is calibrated.

Fixture: point ``SONG_RAP_CONTROL`` at a JSON file
{"rap": <path>, "sung": <path>, "spoken_over_beat": <path>} of local audio
clips. Absent or incomplete -> UNMEASURED, never a pass.

WW-06: this module ALSO carries the ONE route that can ACCEPT a real rap
measurement -- a bounded TIMED LISTENING REVIEW by a reviewer who is NOT the
maker:

  * the reviewer labels specific, bounded windows of the DELIVERED audio as
    "rap", "sung" or "spoken_over_beat", each recorded with its start and end
    seconds;
  * the record is bound to the audio (``sha256`` of the delivered file), to the
    reviewer's identity, to the session and to the timestamp; a record whose
    binding does not match the take is REFUSED and never counted;
  * the measured rap union is the review's rap windows intersected with the
    measured VOICE, judged against the plan's PER-VERSE and TOTAL rap budget;
  * maker self-approval is refused by name;
  * the automatic classifier stays UNMEASURED and can never be the thing that
    grants PASS: fixture existence, sheet tags, word counts, a rate estimate or
    a maker's own verdict can never upgrade it.

stdlib only; no network, no provider, no spend, no speech-to-text.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

#: WW-01's numbers live on the length_formula MODULE (the package __init__
#: re-exports only a subset), so the floors are read from one place and never
#: copied here. The literals below are only the fail-closed fallback.
try:
    from length_formula import length_formula as _LF   # noqa: E402
except ImportError:                                     # pragma: no cover
    _LF = None

TOOL_NAME = "rap_check"
TOOL_VERSION = "1.0.0"

CONTROL_ENV = "SONG_RAP_CONTROL"
REQUIRED = ("rap", "sung", "spoken_over_beat")

#: The timed listening review contract.
REVIEW_SCHEMA = "blackceo.rap-timed-review/v1"
REVIEW_LABELS = ("rap", "sung", "spoken_over_beat")
#: Every field the record must be bound to: audio, reviewer, session, time.
BINDING_FIELDS = ("audio_sha256", "reviewer", "session", "timestamp")

RAP_VERSE_MIN_S = getattr(_LF, "RAP_VERSE_MIN_S", 8.0)
MIN_RAP_VERSES = getattr(_LF, "MIN_RAP_VERSES", 2)


class RapControlError(ValueError):
    """A malformed control fixture: loud, never a silent pass."""


class RapReviewError(ValueError):
    """A malformed or unbound timed listening review: loud, never counted."""


# ---------------------------------------------------------------------------
# The automatic classifier: permanently UNMEASURED until a labelled control set
# exists AND a classifier is calibrated against it.

def control_paths(env=None):
    """The labelled fixture paths, or {} when unavailable (fail closed)."""
    p = (env if env is not None else os.environ).get(CONTROL_ENV)
    if not p or not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(rows, dict):
        return {}
    for k in REQUIRED:
        v = rows.get(k)
        if not v or not os.path.isfile(str(v)):
            return {}
    return {k: str(rows[k]) for k in REQUIRED}


def control_ready(env=None):
    """True only when all three labelled controls are present on disk."""
    return len(control_paths(env)) == len(REQUIRED)


def classify(segments, env=None):
    """The automatic rap classifier for one take. ``segments`` = the detector's
    measured segments. Returns {verdict, reason, rap_seconds, controls}:
      * no labelled control      -> UNMEASURED (never PASS)
      * control present          -> the labelled control decides; until a
        classifier is calibrated against one this stays UNMEASURED too.
    """
    ctrl = control_paths(env)
    rap_s = sum(float(s.get("end", 0)) - float(s.get("start", 0))
                for s in (segments or [])
                if isinstance(s, dict) and s.get("delivery") == "rap")
    if not ctrl:
        return {"verdict": "UNMEASURED", "rap_seconds": rap_s, "controls": [],
                "reason": "no labelled rap control (rap >= sung >= spoken-over-beat); "
                          "non-sung is not rap, so this cannot pass"}
    return {"verdict": "UNMEASURED", "rap_seconds": rap_s, "controls": sorted(ctrl),
            "reason": "labelled controls present but no calibrated rap classifier "
                      "ships yet; UNMEASURED blocks PASS (QC 17.8)"}


# ---------------------------------------------------------------------------
# WW-06: the bounded TIMED LISTENING REVIEW (the only route that can ACCEPT).

def sha256_of_audio(path):
    """The delivered segment's sha256, read in chunks (never the whole file)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_review(*, audio_sha256, reviewer, session, timestamp, windows, maker=None,
                style_id=None):
    """Build a TIMED LISTENING REVIEW record for a file that has already been
    listened to. ``windows`` = [{"start_s", "end_s", "label", "verse"?}, ...].
    The reviewer must not be the maker (enforced again at judge time)."""
    return {"schema": REVIEW_SCHEMA,
            "audio_sha256": str(audio_sha256 or ""),
            "reviewer": str(reviewer or ""),
            "maker": None if maker is None else str(maker),
            "session": str(session or ""),
            "timestamp": str(timestamp or ""),
            "style_id": None if style_id is None else str(style_id),
            "windows": [_window(w) for w in (windows or [])]}


def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise RapReviewError("RAP_REVIEW_WINDOW_INVALID: %s must be a number, got %r"
                             % (what, v))
    return float(v)


def _window(w):
    if not isinstance(w, dict):
        raise RapReviewError("RAP_REVIEW_WINDOW_INVALID: a window must be an object")
    start, end = _num(w.get("start_s"), "start_s"), _num(w.get("end_s"), "end_s")
    label = str(w.get("label") or "").strip().lower()
    out = {"start_s": start, "end_s": end, "label": label}
    if w.get("verse") is not None:
        out["verse"] = int(w["verse"])
    return out


def validate_review(record, audio_sha256=None, reviewer=None, maker=None, session=None,
                    duration_s=None):
    """The binding check for one review. Never raises on a bad record: returns
    {"ok": bool, "reason_code", "detail"} and REFUSES the record.

    Reason codes: RAP_REVIEW_UNBOUND (a binding field is missing/empty),
    RAP_REVIEW_BINDING_MISMATCH (the record names another audio / reviewer /
    session), RAP_REVIEW_MAKER_SELF (the reviewer is the maker),
    RAP_REVIEW_WINDOW_INVALID (an unbounded, reversed or out-of-range window, or
    a label that is not rap / sung / spoken_over_beat).
    """
    if not isinstance(record, dict):
        return _bad("RAP_REVIEW_UNBOUND", "no review record was supplied")
    if record.get("schema") != REVIEW_SCHEMA:
        return _bad("RAP_REVIEW_UNBOUND",
                    "review schema %r is not %r" % (record.get("schema"), REVIEW_SCHEMA))
    for f in BINDING_FIELDS:
        if not str(record.get(f) or "").strip():
            return _bad("RAP_REVIEW_UNBOUND", "the review records no %s" % f)
    if audio_sha256 is not None and str(record.get("audio_sha256")) != str(audio_sha256):
        return _bad("RAP_REVIEW_BINDING_MISMATCH",
                    "the review is bound to audio %s, the take is %s"
                    % (record.get("audio_sha256"), audio_sha256))
    if reviewer is not None and str(record.get("reviewer")) != str(reviewer):
        return _bad("RAP_REVIEW_BINDING_MISMATCH",
                    "the review names reviewer %r, the take expects %r"
                    % (record.get("reviewer"), reviewer))
    if session is not None and str(record.get("session")) != str(session):
        return _bad("RAP_REVIEW_BINDING_MISMATCH",
                    "the review names session %r, the take expects %r"
                    % (record.get("session"), session))
    # maker self-approval is refused BY NAME
    maker_id = str(record.get("maker") or "").strip()
    if maker is not None and str(maker).strip():
        maker_id = str(maker).strip()
    if maker_id and maker_id == str(record.get("reviewer")).strip():
        return _bad("RAP_REVIEW_MAKER_SELF",
                    "reviewer %r is the maker: a maker's own verdict is refused"
                    % (record.get("reviewer"),))
    windows = record.get("windows")
    if not isinstance(windows, list) or not windows:
        return _bad("RAP_REVIEW_WINDOW_INVALID", "the review records no windows")
    for w in windows:
        if not isinstance(w, dict):
            return _bad("RAP_REVIEW_WINDOW_INVALID", "a window is not an object")
        try:
            start, end = _num(w.get("start_s"), "start_s"), _num(w.get("end_s"), "end_s")
        except RapReviewError as e:
            return _bad("RAP_REVIEW_WINDOW_INVALID", str(e))
        label = str(w.get("label") or "").strip().lower()
        if label not in REVIEW_LABELS:
            return _bad("RAP_REVIEW_WINDOW_INVALID",
                        "window label %r is not one of %s" % (w.get("label"),
                                                              ", ".join(REVIEW_LABELS)))
        if end <= start:
            return _bad("RAP_REVIEW_WINDOW_INVALID",
                        "window [%g, %g] is not bounded and forward" % (start, end))
        if start < 0 or (duration_s is not None and end > float(duration_s) + 1e-6):
            return _bad("RAP_REVIEW_WINDOW_INVALID",
                        "window [%g, %g] is outside [0, %s]" % (start, end, duration_s))
    return {"ok": True, "reason_code": "RAP_REVIEW_BOUND",
            "detail": "review by %s, session %s, %d window(s), bound to audio %s"
                      % (record.get("reviewer"), record.get("session"), len(windows),
                         str(record.get("audio_sha256"))[:12]),
            "reviewer": record.get("reviewer"), "session": record.get("session")}


def _bad(code, detail):
    return {"ok": False, "reason_code": code, "detail": detail}


def _union(intervals):
    """Union length of [start, end) intervals: each physical second counted once."""
    total, cur_s, cur_e = 0.0, None, None
    for s, e in sorted((float(a), float(b)) for a, b in intervals if b > a):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def _voice_intervals(voice_segments, duration_s):
    """The measured VOICE as [start, end) intervals (source == "measured")."""
    out = []
    for s in (voice_segments or []):
        if not isinstance(s, dict):
            continue
        try:
            a, b = float(s.get("start")), float(s.get("end"))
        except (TypeError, ValueError):
            continue
        if b > a:
            out.append((max(a, 0.0), b if duration_s is None else min(b, float(duration_s))))
    return out


def _clip(a, b, intervals):
    """[a, b) intersected with a list of intervals."""
    out = []
    for s, e in intervals:
        lo, hi = max(a, s), min(b, e)
        if hi > lo:
            out.append((lo, hi))
    return out


def rap_union(record, audio_sha256=None, duration_s=None, reviewer=None, maker=None,
              session=None, voice_segments=None):
    """The measured RAP UNION: the review's rap windows intersected with the
    measured voice, on ONE physical timeline.

    Refuses (never counts) on any binding mismatch, a maker-authored review, or
    an unbounded/invalid window. The measured voice must be supplied -- with no
    detector voice map there is nothing to intersect and the read stays
    UNMEASURED."""
    v = validate_review(record, audio_sha256=audio_sha256, reviewer=reviewer,
                        maker=maker, session=session, duration_s=duration_s)
    if not v["ok"]:
        return dict(v, rap_seconds=0.0, per_verse={}, windows=0, voice_seconds=None)
    voice = _voice_intervals(voice_segments, duration_s)
    if not voice:
        return _bad("RAP_VOICE_UNMEASURED",
                    "no detector-measured voice segments to intersect the review with")
    rap_ivs, per_verse = [], {}
    for w in record["windows"]:
        if w["label"] != "rap":
            continue
        for seg in _clip(w["start_s"], w["end_s"], voice):
            rap_ivs.append(seg)
            if w.get("verse") is not None:
                per_verse.setdefault(w["verse"], []).append(seg)
    return {"ok": True, "reason_code": "RAP_REVIEW_BOUND",
            "rap_seconds": round(_union(rap_ivs), 4),
            "per_verse": {k: round(_union(v2), 4) for k, v2 in sorted(per_verse.items())},
            "voice_seconds": round(_union(voice), 4), "windows": len(record["windows"]),
            "reviewer": record.get("reviewer"), "session": record.get("session"),
            "detail": "measured rap union %.4f s over one physical voice timeline"
                      % _union(rap_ivs)}


def _budget(plan, style_id, delivered_s):
    """The plan's PER-VERSE and TOTAL rap budget (WW-01). Falls back to the
    length_formula floors when no plan is supplied."""
    D = delivered_s
    if isinstance(plan, dict):
        D = plan.get("delivered_s", D)
    total = None
    if isinstance(plan, dict) and isinstance(plan.get("rap_s"), (int, float)):
        total = float(plan["rap_s"])
    per_verse = RAP_VERSE_MIN_S
    if _LF is not None:
        if total is None:
            total = _LF.rap_verse_budget_s(D)
        if isinstance(plan, dict) and isinstance(plan.get("rap_verse_floor"), dict):
            per_verse = plan["rap_verse_floor"].get("min_s", per_verse)
    else:                                            # pragma: no cover
        total = max(total or 0.0, MIN_RAP_VERSES * per_verse)
    return {"total_s": round(float(total), 3), "per_verse_s": float(per_verse),
            "min_verses": MIN_RAP_VERSES, "delivered_s": D}


def judge_rap_delivery(record, *, style_id=None, delivered_s=None, duration_s=None,
                       audio_sha256=None, voice_segments=None, plan=None, reviewer=None,
                       maker=None, session=None):
    """The rap gate for ONE take, from the timed listening review.

    verdict: PASS | FAIL | UNMEASURED.
      * no review at all  -> UNMEASURED: the automatic classifier cannot grant
        PASS, and UNMEASURED blocks acceptance (QC 17.8);
      * a refused binding (wrong audio/reviewer/session, maker self-approval,
        an invalid window) -> FAIL, refused and never counted;
      * measured rap below the plan's per-verse or total budget -> FAIL;
      * an independent, correctly bound review whose measured rap union meets
        the per-verse AND total budget -> PASS.

    No threshold here is invented: the budgets come from WW-01
    (length_formula), never from a cadence guess."""
    if record is None:
        return {"verdict": "UNMEASURED", "reason_code": "RAP_REVIEW_MISSING",
                "rap_seconds": None, "budget": None,
                "reason": "no timed listening review and no calibrated classifier: "
                          "rap on the audio is UNMEASURED and cannot pass"}
    D = delivered_s if delivered_s is not None else (plan or {}).get("delivered_s")
    union = rap_union(record, audio_sha256=audio_sha256, duration_s=duration_s,
                      reviewer=reviewer, maker=maker, session=session,
                      voice_segments=voice_segments)
    if not union["ok"]:
        return {"verdict": "FAIL", "reason_code": union["reason_code"],
                "rap_seconds": None, "budget": None, "detail": union["detail"],
                "reason": "the review is refused and never counted (%s)" % union["reason_code"]}
    budget = _budget(plan, style_id, D)
    per = union["per_verse"]
    if len(per) < budget["min_verses"]:
        return {"verdict": "FAIL", "reason_code": "RAP_MEASURED_VERSES_BELOW_MIN",
                "rap_seconds": union["rap_seconds"], "per_verse": per, "budget": budget,
                "detail": "the review labels %d rap verse(s); the floor is %d"
                          % (len(per), budget["min_verses"])}
    short = {k: v for k, v in per.items() if v + 1e-9 < budget["per_verse_s"]}
    if short:
        return {"verdict": "FAIL", "reason_code": "RAP_MEASURED_VERSE_BELOW_FLOOR",
                "rap_seconds": union["rap_seconds"], "per_verse": per, "budget": budget,
                "detail": "measured rap verse(s) %s are below the %.1f s per-verse floor"
                          % (sorted(short), budget["per_verse_s"])}
    if union["rap_seconds"] + 1e-9 < budget["total_s"]:
        return {"verdict": "FAIL", "reason_code": "RAP_MEASURED_BELOW_FLOOR",
                "rap_seconds": union["rap_seconds"], "per_verse": per, "budget": budget,
                "detail": "measured rap union %.4f s is below the %.1f s total floor"
                          % (union["rap_seconds"], budget["total_s"])}
    return {"verdict": "PASS", "reason_code": "RAP_MEASURED_MET",
            "rap_seconds": union["rap_seconds"], "per_verse": per, "budget": budget,
            "reviewer": union["reviewer"], "session": union["session"],
            "detail": "independent timed review: measured rap union %.4f s meets the "
                      "%.1f s total and the %.1f s per-verse floor"
                      % (union["rap_seconds"], budget["total_s"], budget["per_verse_s"])}


def gate(segments, env=None, review=None, **ctx):
    """Alias used by the take judge. With NO review the classifier is the only
    evidence and it is permanently UNMEASURED (fail closed). With a review the
    bounded timed-listening route decides, and the review's own binding must
    match the take or the record is refused and never counted."""
    if review is None:
        return classify(segments, env=env)
    return judge_rap_delivery(review, **ctx)


# ---------------------------------------------------------------------------
# Runnable self-check: the route that accepts, and every refusal, asserted.
# python3 core/music_qc/rap_check.py

def _selftest():
    D = 88.0
    voice = [{"start": 0.0, "end": 88.0, "delivery": "spoken", "source": "measured"}]
    windows = [{"start_s": 10.0, "end_s": 20.0, "label": "rap", "verse": 1},
               {"start_s": 30.0, "end_s": 40.0, "label": "rap", "verse": 2},
               {"start_s": 50.0, "end_s": 55.0, "label": "sung"}]
    rec = make_review(audio_sha256="a" * 64, reviewer="r1", maker="m1",
                      session="s1", timestamp="2026-10-11T00:00:00Z", windows=windows)
    assert gate([], review=rec, audio_sha256="a" * 64, duration_s=D,
                voice_segments=voice, delivered_s=D)["verdict"] == "PASS"
    assert gate([])["verdict"] == "UNMEASURED"
    assert gate([], review=rec, audio_sha256="b" * 64, duration_s=D,
                voice_segments=voice, delivered_s=D)["reason_code"] \
        == "RAP_REVIEW_BINDING_MISMATCH"
    assert gate([], review=dict(rec, reviewer="m1"), audio_sha256="a" * 64,
                duration_s=D, voice_segments=voice, delivered_s=D)["reason_code"] \
        == "RAP_REVIEW_MAKER_SELF"
    thin = make_review(audio_sha256="a" * 64, reviewer="r1", session="s1",
                       timestamp="t", windows=[{"start_s": 0.0, "end_s": 4.0,
                                                "label": "rap", "verse": 1},
                                               {"start_s": 10.0, "end_s": 14.0,
                                                "label": "rap", "verse": 2}])
    assert gate([], review=thin, audio_sha256="a" * 64, duration_s=D,
                voice_segments=voice, delivered_s=D)["verdict"] == "FAIL"
    assert classify([])["verdict"] == "UNMEASURED"
    assert control_ready({CONTROL_ENV: ""}) is False
    print("ok: rap_check")


if __name__ == "__main__":
    _selftest()
