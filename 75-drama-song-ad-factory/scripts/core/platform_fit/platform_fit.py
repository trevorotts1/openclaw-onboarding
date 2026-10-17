#!/usr/bin/env python3
"""platform_fit.py: researched platform specs with a re-verify clock, and the
delivered-file checker that reads them (SPEC B3 / B3a; method 8.2 and Step 17).

Why the limits live in one JSON file instead of constants: the method says a
platform's specification is verified at execution time, never assumed. So every
limit the factory knows sits in ``platform-specs.json`` as a *reading*: the
placement, seconds, bytes, formats, availability, aspect ratios, frame-rate
note and safe zones, each with ``source``, ``source_url``, ``read_utc``,
``reverify_after_days`` (30) and ``status`` (VERIFIED | SECONDARY |
UNDETERMINED). Two clocks, one table:

  * paid ad rows come from RESEARCH.md section 7.1 (the platforms' own pages,
    read 2026-10-13);
  * organic rows come from the BlackCEO GHL publishing guide (SPEC B3a,
    2026-10-13). Where GHL's own documents disagree the LARGER documented
    limit is stored -- Trevor's rule, never conservative; a real upload refusal
    is the only signal that lowers a row.

``check(file_probe, placement, today)`` answers PASS / FLAG / UNDETERMINED /
NOT_AVAILABLE and carries one sub-check per documented limit -- length, file
size, container, codec, aspect ratio, frame rate, plus the Facebook Stories
rule that a video over 15 s is split into cards. A limit the row does not
document is never invented: that sub-check is not run, and ``checks`` says
exactly what was measured. Three laws, all fail closed:

  * a row past its re-verify window answers FLAG ``STALE_SPEC`` naming the
    source to re-read -- never PASS;
  * a row whose ``status`` is UNDETERMINED never PASSes: FLAG "verify by hand";
  * a placement that is not available (X/Twitter, the discontinued Stories
    rows) answers NOT_AVAILABLE and is never offered as a destination.

``fits(file_probe)`` runs the same evaluation over the GHL rows only and
returns the destinations a file provably fits -- a destination whose limit the
probe cannot measure is not claimed.

stdlib only. The probe is one ffprobe read routed through ``core/load_governor``.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import sys
from pathlib import Path

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import load_governor as _LG  # noqa: E402

SPECS_PATH = Path(__file__).resolve().parent / "platform-specs.json"
DEFAULT_REVERIFY_DAYS = 30

PASS, FLAG, UNDETERMINED, NOT_AVAILABLE = "PASS", "FLAG", "UNDETERMINED", "NOT_AVAILABLE"
STALE_SPEC = "STALE_SPEC"
UNDETERMINED_SPEC = "UNDETERMINED_SPEC"
UNKNOWN_PLACEMENT = "UNKNOWN_PLACEMENT"

#: the only aspect tolerance any read page documents (Meta: "1% tolerance").
ASPECT_TOLERANCE_PCT = 1.0

#: every row carries these keys; platform-specs.json is judged against them.
ROW_FIELDS = (
    "placement", "label", "kind", "availability", "min_seconds", "max_seconds",
    "max_bytes", "formats", "video_codecs", "aspect_ratios", "aspect_required",
    "aspect_note", "full_playback_seconds", "fps_max_exclusive", "fps_note",
    "safe_zones", "source", "source_url", "read_utc", "reverify_after_days",
    "status", "note",
)


def load_specs(path=None):
    """The researched rows, straight from disk (no cache: a re-read is the point)."""
    p = Path(path) if path else SPECS_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data["rows"] if isinstance(data, dict) else data
    return list(rows)


def row_for(placement, rows=None):
    """The row for a placement id, or None when nobody researched that name."""
    for r in (rows if rows is not None else load_specs()):
        if r.get("placement") == placement:
            return r
    return None


def _as_date(value):
    if value is None:
        return datetime.date.today()
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _stale(row, today):
    """(is_past_the_window, days_since_read) for this row and this day."""
    try:
        read = _as_date(row.get("read_utc"))
    except (TypeError, ValueError):
        return True, None
    days = (_as_date(today) - read).days
    window = int(row.get("reverify_after_days") or DEFAULT_REVERIFY_DAYS)
    return days > window, days


def _ck(name, verdict, reason):
    return {"name": name, "verdict": verdict, "reason": reason}


def _interval(lo, hi, unit):
    if lo is not None and hi is not None:
        return "%g-%g %s" % (lo, hi, unit)
    if hi is not None:
        return "%g %s maximum" % (hi, unit)
    return "%g %s minimum" % (lo, unit)


def _range(name, value, lo, hi, unit, text=None):
    """One numeric limit: PASS inside it, FLAG outside it, UNDETERMINED unmeasured."""
    limit = text or _interval(lo, hi, unit)
    if value is None:
        return _ck(name, UNDETERMINED, "the probe did not measure %s" % name)
    if lo is not None and value < lo:
        return _ck(name, FLAG, "%s is under the documented %s" % (value, limit))
    if hi is not None and value > hi:
        return _ck(name, FLAG, "%s is over the documented %s" % (value, limit))
    return _ck(name, PASS, "%s is inside the documented %s" % (value, limit))


def _ratio(width, height):
    if not width or not height:
        return None
    w, h = int(width), int(height)
    g = math.gcd(w, h)
    return "%d:%d" % (w // g, h // g)


def _aspect_ok(width, height, ratios):
    """True inside a listed ratio (exact or within the documented tolerance)."""
    if not width or not height:
        return None
    exact = _ratio(width, height)
    if exact in ratios:
        return True
    got = float(width) / float(height)
    for spec in ratios:
        try:
            num, den = str(spec).split(":", 1)
            want = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            continue
        if want and abs(got - want) / want * 100.0 <= ASPECT_TOLERANCE_PCT:
            return True
    return False


def _frame_rate(value):
    """ffprobe ``24/1`` / ``30000/1001`` / ``24`` -> float, or None."""
    if value in (None, "", "0/0"):
        return None
    s = str(value)
    try:
        if "/" in s:
            num, _, den = s.partition("/")
            num, den = float(num), float(den)
            return num / den if den else None
        return float(s)
    except ValueError:
        return None


def _size_text(n):
    """A byte limit as a person reads it, with the exact byte count behind it."""
    units = ((1024 ** 3, "GB"), (1024 ** 2, "MB"), (1024, "KB"))
    for base, label in units:
        if n >= base and n % base == 0:
            return "%d %s (%d bytes)" % (n // base, label, n)
    return "%d bytes" % n


def probe_file(path, ffprobe="ffprobe", runner=None):
    """One ffprobe read -> the probe dict ``check``/``fits`` take.

    Keys: path, duration_s, size_bytes, container, format_name, video_codec,
    audio_codec, width, height, fps. The command runs through
    ``load_governor.run_heavy`` so it is counted with every other local job.
    """
    argv = [ffprobe, "-v", "error",
            "-show_entries", "format=duration,size,format_name",
            "-show_entries", "stream=codec_type,codec_name,width,height,avg_frame_rate",
            "-of", "json", str(path)]
    run = runner or (lambda a: _LG.run_heavy(
        a, "platform-fit-probe", capture_output=True, text=True, timeout=60))
    proc = run(argv)
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError as exc:
        raise ValueError("ffprobe gave no JSON for %s: %s" % (path, exc))
    if getattr(proc, "returncode", 0) not in (0, None):
        raise ValueError("ffprobe failed on %s: %s"
                         % (path, (proc.stderr or "").strip()[-200:]))
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    def _num(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    suffix = Path(str(path)).suffix.lstrip(".").lower()
    container = suffix or str(fmt.get("format_name") or "").split(",")[0]
    size = _num(fmt.get("size"))
    if size is None:
        try:
            size = float(os.path.getsize(path))
        except OSError:
            size = None
    return {
        "path": str(path),
        "duration_s": _num(fmt.get("duration")),
        "size_bytes": int(size) if size is not None else None,
        "container": container or None,
        "format_name": fmt.get("format_name"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": _frame_rate(video.get("avg_frame_rate")),
    }


def _subchecks(row, probe, checks):
    """Every limit this row documents; a limit nobody read is simply not asked."""
    lo, hi = row.get("min_seconds"), row.get("max_seconds")
    if lo is not None or hi is not None:
        checks.append(_range("length", probe.get("duration_s"), lo, hi, "seconds"))

    fp = row.get("full_playback_seconds")
    if fp is not None:
        d = probe.get("duration_s")
        if d is None:
            checks.append(_ck("full_playback", UNDETERMINED,
                              "the probe did not measure length"))
        elif d > fp:
            checks.append(_ck(
                "full_playback", FLAG,
                "%g s only plays its first %g s and is split into cards here"
                % (d, fp)))
        else:
            checks.append(_ck("full_playback", PASS,
                              "%g s plays in full (card split starts at %g s)"
                              % (d, fp)))

    if row.get("max_bytes") is not None:
        checks.append(_range(
            "file_size", probe.get("size_bytes"), None, row["max_bytes"], "bytes",
            text=_size_text(row["max_bytes"])))

    if row.get("formats"):
        got = probe.get("container")
        if not got:
            checks.append(_ck("container", UNDETERMINED,
                              "the probe did not report a container"))
        elif str(got).lower() in [str(f).lower() for f in row["formats"]]:
            checks.append(_ck("container", PASS, "%s container is accepted" % got))
        else:
            checks.append(_ck(
                "container", FLAG,
                "%s container is not in the accepted formats %s"
                % (got, ", ".join(row["formats"]))))

    if row.get("video_codecs"):
        got = probe.get("video_codec")
        if not got:
            checks.append(_ck("codec", UNDETERMINED,
                              "the probe did not report a video codec"))
        else:
            wanted = {str(c).lower() for c in row["video_codecs"]}
            same = {str(got).lower()}
            if "h265" in wanted:            # h265 and hevc are one codec, two names
                wanted.add("hevc")
            if "hevc" in wanted:
                wanted.add("h265")
            if same & wanted:
                checks.append(_ck("codec", PASS, "%s codec is accepted" % got))
            else:
                checks.append(_ck(
                    "codec", FLAG,
                    "%s codec is not in the accepted codecs %s"
                    % (got, ", ".join(sorted(wanted)))))

    if row.get("aspect_ratios") and row.get("aspect_required"):
        ok = _aspect_ok(probe.get("width"), probe.get("height"), row["aspect_ratios"])
        if ok is None:
            checks.append(_ck("aspect", UNDETERMINED,
                              "the probe did not measure the frame"))
        elif ok:
            checks.append(_ck("aspect", PASS, "%s frame is accepted (%s)"
                              % (_ratio(probe.get("width"), probe.get("height")),
                                 ", ".join(row["aspect_ratios"]))))
        else:
            checks.append(_ck(
                "aspect", FLAG,
                "%s frame is outside the accepted shapes %s%s"
                % (_ratio(probe.get("width"), probe.get("height")),
                   ", ".join(row["aspect_ratios"]),
                   "; " + row["aspect_note"] if row.get("aspect_note") else "")))

    if row.get("fps_max_exclusive") is not None:
        fps = probe.get("fps")
        cap = row["fps_max_exclusive"]
        if fps is None:
            checks.append(_ck("fps", UNDETERMINED,
                              "the probe did not measure a frame rate"))
        elif fps >= cap:
            checks.append(_ck(
                "fps", FLAG,
                "%g fps is not under the documented %g fps ceiling%s"
                % (fps, cap,
                   " (%s)" % row["fps_note"] if row.get("fps_note") else "")))
        else:
            checks.append(_ck("fps", PASS, "%g fps is under the documented %g fps ceiling"
                              % (fps, cap)))
    return checks


def evaluate(row, probe, today=None):
    """The verdict for one row and one probe. ``today=None`` skips the clock
    (``fits`` has no date to judge staleness with; ``check`` always passes one)."""
    if row.get("availability") == "NOT_AVAILABLE":
        return {"placement": row.get("placement"), "label": row.get("label"),
                "verdict": NOT_AVAILABLE, "code": None, "checks": [],
                "reason": "not available: %s" % row.get("note", "discontinued destination"),
                "stale": False, "days_since_read": None, "row": row}

    checks = _subchecks(row, probe, [])
    stale, days = (False, None) if today is None else _stale(row, today)
    status = row.get("status")
    reason = None
    code = None

    if status == "UNDETERMINED":
        verdict, code = FLAG, UNDETERMINED_SPEC
        reason = ("spec status UNDETERMINED -- verify by hand before publishing "
                  "to %s (%s)" % (row.get("label"), row.get("source")))
    elif stale:
        verdict, code = FLAG, STALE_SPEC
        reason = ("STALE_SPEC: read %s day(s) ago, past the %s day re-verify "
                  "window -- re-read %s before trusting it"
                  % (days, row.get("reverify_after_days") or DEFAULT_REVERIFY_DAYS,
                     row.get("source_url") or row.get("source")))
    else:
        verdict = PASS
        for c in checks:
            if c["verdict"] == FLAG:
                verdict, reason = FLAG, c["reason"]
                break
        if verdict == PASS:
            for c in checks:
                if c["verdict"] == UNDETERMINED:
                    verdict, reason = UNDETERMINED, c["reason"]
                    break
        if verdict == PASS:
            reason = "%d documented limit(s) checked, all inside the spec" % len(checks)

    return {"placement": row.get("placement"), "label": row.get("label"),
            "verdict": verdict, "code": code, "reason": reason, "checks": checks,
            "stale": stale, "days_since_read": days, "row": row}


def check(file_probe, placement, today=None, rows=None):
    """PASS / FLAG / UNDETERMINED / NOT_AVAILABLE for this file and placement.

    ``today`` is the day the specs are being judged on (a date or an ISO string;
    defaults to today), which is what turns an old row into a STALE_SPEC flag.
    """
    row = row_for(placement, rows)
    if row is None:
        return {"placement": placement, "label": None, "verdict": UNDETERMINED,
                "code": UNKNOWN_PLACEMENT,
                "reason": "no researched spec row named %r -- nothing to check "
                          "against, so it cannot PASS" % placement,
                "checks": [], "stale": False, "days_since_read": None, "row": None}
    return evaluate(row, file_probe, _as_date(today))


def fits(file_probe, rows=None):
    """The GHL destinations this file provably fits, in table order."""
    out = []
    for row in (rows if rows is not None else load_specs()):
        if row.get("kind") != "ghl" or row.get("availability") != "AVAILABLE":
            continue
        if evaluate(row, file_probe, None)["verdict"] == PASS:
            out.append(row["placement"])
    return out


