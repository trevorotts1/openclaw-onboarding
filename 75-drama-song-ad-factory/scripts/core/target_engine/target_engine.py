#!/usr/bin/env python3
"""target_engine.py — G4: every share/length target steers generation.

Owner order (2026-10-08 11:35, Part G, G4), verbatim: "It's not an absolute
55% or 20% ... it creates it as a target. If the target is not hit, it
doesn't cancel out the flow or the work. As long as it's within about 5
percentage points of any other targets, it should be accepted."

What the engine does, in the order the flow asks it:

1. **Closest-of-N per round.** Every round carries several WHOLE-TRACK
   candidates; each is measured (unit W-G-003's singing_detector when it is
   on the train, otherwise the spoken_share timing map) and scored against
   every target; the candidate CLOSEST to every target wins the round.

2. **The grace band is the accept line.** Within about GRACE_PCT
   percentage points of every target = ACCEPT. The grace number itself is
   owned by the spoken-grace unit (W-F-U16) in core/spoken_share; this
   module reads it from there and defines no second grace constant.

3. **Outside the band steers, it does not stop.** A miss produces
   adjustment knobs (lyric structure, style text, spoken budget, length)
   and a regenerate instruction -- bounded by MAX_ROUNDS.

4. **Bounded, then continue anyway.** When the rounds run out, the CLOSEST
   take is kept WITH A WARNING and the flow continues. The engine NEVER
   raises on a missed target and NEVER cancels the work.

5. **One exception, and it is still not a cancel.** Singing was chosen and
   the measurement finds NO real singing at all (all-spoken take) -> that
   candidate is rejected and the round regenerates; it counts as far
   outside target. Exhausting the rounds still ends in keep-closest-with-
   warning, never a raise.

Dependencies (train resolve wires both):
  - core/spoken_share is on main: the target constants (22.5 target, 12.5 / 32.5 redo edges) and
    the timing-map measurement come from it. GRACE_PCT lands there with the
    W-F-U16 spoken-grace branch; until it resolves, ``getattr`` supplies 5.
  - core/singing_detector is unit W-G-003's planned module: imported
    lazily at measurement time, so this module runs green before that
    branch lands and switches to it automatically after.

stdlib only: no network, no provider, no spend, no media file, no absolute
operator path (the engine measures whatever the caller hands it and never
opens a file itself).

Run: python3 core/target_engine/test_target_engine.py
"""
from __future__ import annotations

from math import isfinite

try:
    import spoken_share as _SS                      # core/ on sys.path
except ImportError:                                 # imported as core.*
    from .. import spoken_share as _SS

TOOL_NAME = "target_engine"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.target-engine/v1"
SOURCE = ("Owner order 2026-10-08 11:35 (Part G, G4); grace from the "
          "W-F-U16 spoken-grace constants in core/spoken_share; targets "
          "from core/spoken_share (D15 retarget).")

# ---- the one constants module ---------------------------------------------
# The numbers live in core/spoken_share and are read, never copied. G4 adds
# no second grace constant and no second band.
SPOKEN_TARGET_PCT = _SS.SPOKEN_TARGET_PCT   # 22.5
SPOKEN_MIN_PCT = _SS.SPOKEN_MIN_PCT         # 12.5
SPOKEN_MAX_PCT = _SS.SPOKEN_MAX_PCT         # 32.5
TARGET = _SS.TARGET
FLOOR = _SS.FLOOR
CAP = _SS.CAP

# ponytail: GRACE_PCT is owned by the spoken-grace unit (W-F-U16) in
# spoken_share.py. This getattr default stands only until that branch
# resolves onto the train; the resolve drops the fallback and this line
# becomes a plain read. Ceiling: a second 5 here would let the two drift.
GRACE_PCT = getattr(_SS, "GRACE_PCT", 5)

#: Bounded regeneration: adjust and regenerate at most this many rounds,
#: then keep the CLOSEST take WITH A WARNING and continue. Never cancel.
MAX_ROUNDS = 3

#: "Generate several WHOLE-TRACK candidates per round" -- a thinner batch
#: still scores, but the verdict carries a thin-batch warning.
MIN_CANDIDATES_PER_ROUND = 2

#: Metric keys the engine scores. Everything else a measurement carries is
#: passed through untouched.
TARGET_KEYS = ("spoken_share", "length_s")

VERDICT_ACCEPT = "ACCEPT"
VERDICT_ADJUST = "ADJUST"
VERDICT_REGENERATE = "REGENERATE"
VERDICT_CONTINUE = "CONTINUE_WITH_WARNING"


class TargetEngineError(ValueError):
    """Malformed input -- a caller bug, never a domain verdict. A missed
    target is a domain verdict and never raises."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# ------------------------------------------------------------ targets ----

def targets(spoken_target=None, length_target_s=None, extra=None):
    """The target set for one run. The share target defaults to the
    spoken_share target (22.5%, SPK001); the length target is optional. Extra
    numeric targets are allowed; keys ending in ``_share`` must be
    fractions 0..1 like the built-ins. Malformed input raises (caller bug).
    """
    tg = {}
    st = TARGET if spoken_target is None else spoken_target
    if isinstance(st, bool) or not isinstance(st, (int, float)) \
            or not isfinite(float(st)) or not 0.0 <= float(st) <= 1.0:
        raise TargetEngineError(
            "BAD_TARGET", "spoken_target must be a fraction 0..1, got %r"
            % (st,))
    tg["spoken_share"] = float(st)
    if length_target_s is not None:
        lt = length_target_s
        if isinstance(lt, bool) or not isinstance(lt, (int, float)) \
                or not isfinite(float(lt)) or float(lt) <= 0:
            raise TargetEngineError(
                "BAD_TARGET", "length_target_s must be positive finite "
                "seconds, got %r" % (lt,))
        tg["length_s"] = float(lt)
    if extra:
        if not isinstance(extra, dict):
            raise TargetEngineError("BAD_TARGET", "extra must be a dict")
        for name, value in extra.items():
            if not isinstance(name, str) or not name:
                raise TargetEngineError("BAD_TARGET", "extra key %r" % (name,))
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not isfinite(float(value)):
                raise TargetEngineError(
                    "BAD_TARGET", "extra target %s must be a finite number, "
                    "got %r" % (name, value))
            if name.endswith("_share") and not 0.0 <= float(value) <= 1.0:
                raise TargetEngineError(
                    "BAD_TARGET", "extra target %s is a share and must be "
                    "a fraction 0..1, got %r" % (name, value))
            tg[name] = float(value)
    return tg


def _validated_targets(tg):
    """Validate a caller-supplied target dict -- the raw-dict path of
    ``score(tg=...)`` and ``steer(targets=...)``. Same rules as
    ``targets()``: numeric finite values, share targets are fractions
    0..1, every other target positive (a ratio-metric deviation divides
    by the target, so 0 is malformed, not zero-error). Raises a
    TargetEngineError (caller bug); the built ``targets()`` output
    re-validates idempotently."""
    if not isinstance(tg, dict) or not tg:
        raise TargetEngineError("BAD_TARGETS",
                                "targets must be a non-empty dict")
    out = {}
    for name, value in tg.items():
        if not isinstance(name, str) or not name:
            raise TargetEngineError("BAD_TARGET", "target key %r" % (name,))
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not isfinite(float(value)):
            raise TargetEngineError(
                "BAD_TARGET", "target %s must be a finite number, got %r"
                % (name, value))
        if name.endswith("_share") and not 0.0 <= float(value) <= 1.0:
            raise TargetEngineError(
                "BAD_TARGET", "target %s is a share and must be a fraction "
                "0..1, got %r" % (name, value))
        if not name.endswith("_share") and float(value) <= 0:
            raise TargetEngineError(
                "BAD_TARGET", "target %s must be positive, got %r"
                % (name, value))
        out[name] = float(value)
    return out


# ---------------------------------------------------------- measuring ----

def _finite(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and isfinite(float(value)))


def normalize_metrics(raw, detector=None, confidence=None):
    """One measurement -> the metrics dict the engine scores. Malformed
    numbers are refused (caller bug); absences are allowed and simply leave
    that axis unjudgeable."""
    if not isinstance(raw, dict):
        raise TargetEngineError(
            "BAD_METRICS", "measurement must be a dict, got %r" % (raw,))
    metrics = {
        "spoken_share": None,
        "sung_share": None,
        "length_s": None,
    }
    for key in metrics:
        if key in raw:
            if not _finite(raw[key]):
                raise TargetEngineError(
                    "BAD_METRICS", "metric %s must be a finite number, "
                    "got %r" % (key, raw[key]))
            metrics[key] = float(raw[key])
    for key, value in metrics.items():
        if key.endswith("_share") and value is not None \
                and not 0.0 <= value <= 1.0:
            raise TargetEngineError(
                "BAD_METRICS", "metric %s must be a fraction 0..1, got %r"
                % (key, value))
    metrics["detector"] = detector
    metrics["confidence"] = (float(confidence)
                             if confidence is not None and _finite(confidence)
                             else None)
    sung = metrics["sung_share"]
    metrics["all_spoken"] = sung is not None and sung <= 0.0
    return metrics


def _detector_share(master_path):
    """The planned G3 detector (unit W-G-003, core/singing_detector/),
    imported lazily so this module runs green before that branch resolves
    and switches to it automatically after. Its planned share API is
    ``share(path) -> {"sung_share", "spoken_share", ...}`` (or a bare
    sung-share number); the train resolve wires any drift. Returns None
    when the module or its share API is not usable."""
    import importlib
    try:
        det = importlib.import_module("singing_detector")
    except ImportError:
        return None
    fn = (getattr(det, "share", None) or getattr(det, "sung_share", None)
          or getattr(det, "measure", None))
    if not callable(fn):
        return None
    try:
        out = fn(master_path)
    except Exception:
        return None
    if isinstance(out, dict) and "spoken_share" in out:
        return out
    if _finite(out):
        return {"sung_share": float(out)}
    return None


def measure_candidate(candidate, measure=None):
    """One candidate -> metrics. Order of the measurement chain:

    1. Precomputed ``candidate["metrics"]`` (the caller already measured).
    2. The injected ``measure`` callable (the production wiring passes the
       G3 detector wrapper here).
    3. The planned G3 detector module, lazily imported (see above).
    4. The spoken_share timing map (on main today) -- planner-side
       measurement, tagged as such.

    No usable source -> TargetEngineError (caller bug). A measurement that
    is merely BAD (all-spoken, out of grace) is a domain verdict and never
    raises.
    """
    if not isinstance(candidate, dict):
        raise TargetEngineError(
            "BAD_CANDIDATE", "candidate must be a dict, got %r"
            % (type(candidate).__name__,))
    pre = candidate.get("metrics")
    if pre is not None:
        return normalize_metrics(pre)
    if measure is not None:
        if not callable(measure):
            raise TargetEngineError(
                "BAD_MEASURE", "measure must be callable, got %r" % (measure,))
        return normalize_metrics(measure(candidate))
    path = candidate.get("master_path")
    if path:
        out = _detector_share(path)
        if out is not None:
            return normalize_metrics(out, detector="singing_detector",
                                     confidence=out.get("confidence"))
    timing = candidate.get("timing")
    if isinstance(timing, list) and timing:
        measured = _SS.measure_share(timing)
        return normalize_metrics(
            {"spoken_share": measured["share"],
             "sung_share": measured["sung_share"],
             "length_s": measured["total_seconds"]},
            detector="spoken_share.timing")
    raise TargetEngineError(
        "NO_MEASUREMENT", "candidate %r has no metrics, no measure callable, "
        "no usable detector and no timing map" % (candidate.get("id"),))


# ------------------------------------------------------------ scoring ----

def score(metrics, tg, grace_pct=GRACE_PCT):
    """One candidate's metrics against every target. Deviations are in
    percentage points: a share is compared in points directly; a length
    target is compared as percent of the target ("about 5 percentage
    points", one interpretation for seconds). ``worst`` is the largest
    deviation over the grace band (<= 1.0 = within grace). An axis the
    measurement cannot judge scores worst (inf) -- it can never pass on an
    unmeasured target. Malformed targets raise a TargetEngineError
    (caller bug), never a ZeroDivisionError/TypeError from the arithmetic
    below."""
    tg = _validated_targets(tg)
    if not isinstance(grace_pct, (int, float)) or isinstance(grace_pct, bool) \
            or grace_pct <= 0:
        raise TargetEngineError("BAD_GRACE", "grace_pct must be positive")
    devs, norm, unmeasured = {}, {}, []
    for name, t in tg.items():
        m = metrics.get(name)
        if m is None:
            norm[name] = float("inf")
            unmeasured.append(name)
            continue
        dev_pct = (abs(m - t) * 100.0 if name.endswith("_share")
                   else abs(m - t) / abs(t) * 100.0)
        devs[name] = round(dev_pct, 4)
        norm[name] = dev_pct / float(grace_pct)
    worst = max(norm.values())
    return {
        "deviations_pct": devs,
        "normalized": norm,
        "worst": worst,
        "within_grace": worst <= 1.0,
        "grace_pct": grace_pct,
        "unmeasured": unmeasured,
    }


def adjustment_for(metrics, tg, grace_pct=GRACE_PCT):
    """Steering knobs for a candidate that missed: which way each miss went
    and what the regenerating side changes (lyric structure, style text,
    spoken budget, length). Never a cancel instruction."""
    knobs = {}
    t_share = tg.get("spoken_share")
    m_share = metrics.get("spoken_share")
    if t_share is not None and m_share is not None:
        if m_share > t_share:
            knobs["spoken_budget"] = (
                "reduce spoken budget: tighten the opener, drop mid-track "
                "spoken blocks (at most 3 for 60-150 s)")
        else:
            knobs["spoken_budget"] = (
                "raise spoken budget: re-add opener / turn / call-to-action "
                "spoken blocks within the cap")
        knobs["style_text"] = (
            "sung delivery wording only; no spoken word / speech / narration "
            "/ rap / talk markers")
    t_len, m_len = tg.get("length_s"), metrics.get("length_s")
    if t_len is not None and m_len is not None:
        knobs["length"] = ("trim sung lines (keep meter and rhyme)"
                           if m_len > t_len
                           else "extend sung lines within the length cap")
    if metrics.get("all_spoken"):
        knobs["lyric_structure"] = (
            "all-spoken take: rebuild sung lines as metered, rhymed lines "
            "from the client's own words and re-set spoken blocks")
    return knobs


# ------------------------------------------------------- closest-of-N ----

def best(candidates, tg, measure=None, grace_pct=GRACE_PCT,
         singing_chosen=True):
    """The CLOSEST take of one round. Every candidate is measured and
    scored; an all-spoken candidate (singing chosen, no real singing) or an
    unmeasurable one is rejected and ranks behind every measurable take --
    it counts as far outside target, never as a raise."""
    if not isinstance(candidates, list) or not candidates:
        raise TargetEngineError(
            "BAD_BATCH", "candidates must be a non-empty list, got %r"
            % (candidates,))
    ranked, all_rejected, rejected_ids = [], True, []
    for cand in candidates:
        record = {"candidate": cand, "metrics": None, "score": None,
                  "rejected": False, "reasons": []}
        try:
            record["metrics"] = m = measure_candidate(cand, measure)
            record["score"] = score(m, tg, grace_pct)
        except Exception as exc:                    # noqa: BLE001
            # ponytail: every failure mode of one candidate's measurement
            # chain (TargetEngineError and a raising production wrapper
            # alike) rejects ONE candidate as unmeasurable; a corrupt clip
            # loses its take, never the round. Revisit if a caller wants a
            # wider stop-list.
            record["rejected"] = True
            record["reasons"].append("unmeasurable: %s: %s"
                                     % (type(exc).__name__, exc))
            ranked.append(record)
            rejected_ids.append(cand.get("id") if isinstance(cand, dict) else None)
            continue
        if singing_chosen and m["all_spoken"]:
            record["rejected"] = True
            record["reasons"].append(
                "all-spoken take: the detector finds no real singing at all "
                "(far outside target)")
            rejected_ids.append(cand.get("id"))
        else:
            all_rejected = False
        ranked.append(record)
    pool = [r for r in ranked if not r["rejected"]] or ranked
    winner = min(pool, key=lambda r: (float("inf") if r["score"] is None
                                      else r["score"]["worst"],))
    winner.update({
        "all_rejected": all(w["rejected"] for w in ranked),
        "rejected_ids": rejected_ids,
        "thin_batch": len(candidates) < MIN_CANDIDATES_PER_ROUND,
    })
    winner["ranked"] = ranked
    return winner


# --------------------------------------------------------- the loop ----

def steer(rounds, targets=None, measure=None, singing_chosen=True,
          max_rounds=MAX_ROUNDS, grace_pct=GRACE_PCT):
    """The bounded loop. ``rounds(round_index, instruction)`` yields the
    candidate batch for one round (the caller's generator side; the
    instruction carries the previous round's adjustment knobs). Verdicts:

    - ACCEPT            best candidate within grace of every target
    - CONTINUE_WITH_WARNING  rounds exhausted -> keep the CLOSEST take,
                          warn, continue. NEVER cancel, NEVER raise on a
                          missed target. (A caller bug -- malformed
                          targets, a raising generator -- still raises.)
    """
    if not callable(rounds):
        raise TargetEngineError("BAD_ROUNDS", "rounds must be callable")
    tg = _validated_targets(targets) if targets else {"spoken_share": TARGET}
    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) \
            or max_rounds < 1:
        raise TargetEngineError("BAD_MAX_ROUNDS", "max_rounds must be >= 1")

    history, warnings, adjustment, last = [], [], None, None
    for round_index in range(1, max_rounds + 1):
        batch = rounds(round_index, adjustment)
        if not isinstance(batch, list) or not batch:
            history.append({"round": round_index, "batch_size": 0,
                            "verdict": VERDICT_REGENERATE,
                            "reasons": ["empty round: regenerate"]})
            adjustment = adjustment_for({}, tg, grace_pct)
            warnings.append("round %d produced no candidates; regenerated"
                            % round_index)
            continue
        win = best(batch, tg, measure, grace_pct, singing_chosen)
        last = win
        record = {
            "round": round_index,
            "batch_size": len(batch),
            "best": {"id": (win["candidate"].get("id")
                            if isinstance(win["candidate"], dict) else None),
                     "metrics": win["metrics"],
                     "score": win["score"],
                     "all_spoken": (win["metrics"] or {}).get("all_spoken"),
                     "detector": (win["metrics"] or {}).get("detector"),
                     "confidence": (win["metrics"] or {}).get("confidence")},
            "rejected_ids": win["rejected_ids"],
        }
        if win["thin_batch"]:
            warnings.append(
                "round %d carried %d candidate(s); several are expected"
                % (round_index, len(batch)))
        if win["all_rejected"]:
            record["verdict"] = VERDICT_REGENERATE
            record["reasons"] = win["ranked"][0]["reasons"]
            adjustment = adjustment_for(win["metrics"] or {}, tg, grace_pct)
            history.append(record)
            continue
        if win["score"]["within_grace"]:
            record["verdict"] = VERDICT_ACCEPT
            history.append(record)
            return {
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                "schema": SCHEMA_VERSION, "source": SOURCE,
                "verdict": VERDICT_ACCEPT,
                "candidate": win["candidate"],
                "metrics": win["metrics"],
                "score": win["score"],
                "rounds_used": round_index,
                "max_rounds": max_rounds,
                "grace_pct": grace_pct,
                "targets": tg,
                "warnings": warnings,
                "all_spoken_final": False,
                "history": history,
            }
        record["verdict"] = VERDICT_ADJUST
        record["reasons"] = [
            "%s %s vs target %s (%s points off the %s-point grace)"
            % (name, _fmt(_axis(win["metrics"], name)), _fmt(value),
               _fmt(win["score"]["deviations_pct"].get(name, float("inf"))),
               _fmt(grace_pct))
            for name, value in tg.items()
            if win["score"]["normalized"].get(name, float("inf")) > 1.0]
        record["unmeasured"] = win["score"]["unmeasured"]
        adjustment = adjustment_for(win["metrics"] or {}, tg, grace_pct)
        history.append(record)

    # Rounds exhausted: keep the CLOSEST take WITH A WARNING and continue.
    miss_lines = []
    if last is not None and last.get("score") is not None:
        for name, value in tg.items():
            if last["score"]["normalized"].get(name, float("inf")) > 1.0:
                miss_lines.append(
                    "%s %s vs target %s (%s points off)"
                    % (name, _fmt(_axis(last["metrics"], name)), _fmt(value),
                       _fmt(last["score"]["deviations_pct"].get(
                           name, float("inf")))))
    else:
        miss_lines.append("no measurable candidate in any round")
    warnings.append(
        "target not reached after %d rounds: keep the closest take and "
        "continue -- never cancel (reinforce the closer take at the next "
        "cut: %s)" % (max_rounds, "; ".join(miss_lines)))
    return {
        "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
        "schema": SCHEMA_VERSION, "source": SOURCE,
        "verdict": VERDICT_CONTINUE,
        "candidate": last["candidate"] if last else None,
        "metrics": last["metrics"] if last else None,
        "score": last["score"] if last else None,
        "rounds_used": max_rounds,
        "max_rounds": max_rounds,
        "grace_pct": grace_pct,
        "targets": tg,
        "warnings": warnings,
        "all_spoken_final": bool(last and last.get("metrics")
                                 and last["metrics"].get("all_spoken")),
        "history": history,
    }


def _axis(metrics, name):
    """Human value of one target axis from a metrics dict (for verdict
    text); 'n/a' when the axis was never measured."""
    if not metrics:
        return "n/a"
    value = metrics.get(name)
    return value if isinstance(value, (int, float)) else "n/a"


def _fmt(value):
    """Numeric-or-text formatting for miss lines: %.4g only ever sees a
    real number; 'n/a' (an unmeasured axis) and the target value pass
    through as text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "%.4g" % (value,)
    return str(value)
