#!/usr/bin/env python3
"""F1 one-track soundtrack: ONE Suno generation makes the whole ad audio.

Owner order 2026-10-08, manual Part F item F1 (Critical), ADDENDUM 3 + PASTE
ADDENDUM 3+4. stdlib only, zero paid calls.

``generate_soundtrack_request(package)`` builds ONE Suno generate request in
the Skill 68 current envelope (the same shape ``music_director.
build_generate_request`` produces: endpoint / model / callBackUrl / input),
whose lyrics carry the spoken passages INSIDE the song, tagged as spoken
(``[Spoken]`` section marker plus the repo's directive-12 per-character voice
tag from ``core/audio_c3/voice_casting.voice_tag``), so Suno performs the
spoken words over the music in the same track. **No separate spoken takes,
no gaps, no added bed** — the E8 music-bed mixer, the E9 dip numbers and the
E10 9 dB / 0.3 s gate are superseded and must never merge.

Spoken-source routing: every line's spoken words route here, into the one
track's lyrics (``SPOKEN_SOURCE``). The ``voice_packs`` spoken-only pack
route is a SUPERSEDED, record-only path — nothing routes spoken lines to
separate packs any more.

``record_soundtrack(receipt, generation_id, retakes=[])`` stamps the delivery
receipt proving the final audio came from exactly ONE Suno generation id, the
only retakes being whole-track retakes; each retake must carry
``"kind": "whole-track"`` or the record is refused. ``verify_soundtrack``
re-reads the receipt fail-closed: a second generation id in
``receipt["audio_jobs"]`` without a whole-track retake marker fails the
receipt; a retake without the marker fails at record time.

Transport stays out of this module (Skill 74 is the only KIE path): the
payload goes to the caller's dispatcher. stdlib only.

Run: python3 core/audio_c3/test_soundtrack_f1.py
"""
from __future__ import annotations

import json
from pathlib import Path

try:  # package import (audio_c3.soundtrack) and flat script import both work
    from .no_echo import check as no_echo_check, stamp as no_echo_stamp
    from .voice_casting import render_lyrics  # validated tagging + delivery
except ImportError:  # pragma: no cover - flat test path
    from no_echo.no_echo import (  # type: ignore
        check as no_echo_check, stamp as no_echo_stamp)
    from voice_casting import render_lyrics  # type: ignore

SCHEMA_VERSION = "blackceo.audio-c3/soundtrack/v1"
TOOL_VERSION = "0.1.0"

PROVIDER = "suno"
#: F1: the whole soundtrack comes from exactly ONE Suno generation.
TRACK_MODE = "one-generation"
#: Suno's own spoken section marker, inside the song lyrics.
SPOKEN_TAG = "[Spoken]"

#: Retakes of the one track are always whole-track.
RETAKE_KIND = "whole-track"

#: Routing note -- where audio_c3 picks spoken sources. Spoken words are
#: performed inside the one Suno track's lyrics; spoken-only voice packs are
#: superseded (voice_packs.py docstring, owner order 2026-10-08).
SPOKEN_SOURCE = "in-song-lyrics"
AUDIO_C3_SPOKEN_ROUTING = (
    "Spoken sources: every spoken line is routed into the one Suno track's "
    "lyrics (audio_c3/soundtrack.py, SPOKEN_SOURCE in-song-lyrics). The "
    "voice_packs spoken-only separate-take path is SUPERSEDED and record-only."
)

#: Current Skill 68 envelope, read from the work copy at runtime; static
#: fallback mirrors it. ponytail: if the work copy moves, fix the fallback
#: constants and re-run the F14 drift test pattern.
_DEFAULTS = {"route": "ai-music-api/generate",
             "endpoint": "/api/v1/jobs/createTask",
             "version": "V6"}
CALLBACK_URL = "https://example.invalid/cb"


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def _workcopy():
    """(route, version) for suno-generate from the repo's work copy, or None."""
    root = Path(__file__).resolve().parents[4]
    doc = root / "68-kie-audio" / "models.json"
    try:
        entries = json.loads(doc.read_text(encoding="utf-8")).get("entries", [])
        for e in entries:
            if e.get("canonical_model_id") == "suno-generate":
                route = e["route_models"]["current"].split()[0]
                return str(route), str(e["model_default"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _loud("warn", "SUNO_ROUTE_UNREADABLE", "%s: %r" % (doc, exc))
    return None


def _errors_for_package(package):
    """Error-code list for a soundtrack package (empty = buildable)."""
    if not isinstance(package, dict):
        return ["PACKAGE_INVALID:not a dict"]
    errs = []
    for field in ("title", "style_text"):
        v = package.get(field)
        if not isinstance(v, str) or not v.strip():
            errs.append("MISSING:%s" % field)
    lines = package.get("lines")
    if not isinstance(lines, list) or not lines:
        errs.append("MISSING:lines")
    profiles = package.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        errs.append("MISSING:profiles")
    for extra in sorted(package):
        if extra not in ("title", "style_text", "lines", "profiles",
                         "vocal_gender", "duration"):
            errs.append("UNKNOWN_FIELD:%s" % extra)
    return errs


def build_lyrics_text(lines, profiles):
    """The song's own lyrics, spoken passages tagged [Spoken] inside it.

    ``lines`` and ``profiles`` are the packet shapes; ``voice_casting.
    render_lyrics`` does the fail-closed tagging, then each spoken line is
    written as ``[Spoken]`` + the character's directive-12 voice tag + the
    verbatim words, so Suno speaks them over the music in the same track.
    Raises ValueError with the render's error codes on any invalid line.
    """
    env = render_lyrics(lines, profiles)
    if env["outcome"] != "ok":
        raise ValueError("LYRICS_RENDER_REFUSED:" + "; ".join(env["errors"]))
    blocks = []
    for tagged in env["lines"]:
        if tagged["delivery"] == "spoken":
            blocks.append("\n".join((SPOKEN_TAG, tagged["tag"],
                                     tagged["text"])))
        else:
            blocks.append("\n".join((tagged["tag"], tagged["text"])))
    return "\n\n".join(blocks) + "\n"


def generate_soundtrack_request(package):
    """ONE Suno generate request: the whole soundtrack, spoken in the lyrics.

    Verbatim words, one track. The payload is D22a-stamped by ``no_echo`` so
    it carries the dry close-microphone rule and the seven negative tags.
    Raises ValueError with code list on any package error.
    """
    errs = _errors_for_package(package)
    if errs:
        raise ValueError("; ".join(errs))
    lyrics = build_lyrics_text(package["lines"], package["profiles"])
    picked = _workcopy() or (_DEFAULTS["route"], _DEFAULTS["version"])
    request = {
        "endpoint": _DEFAULTS["endpoint"],
        "model": picked[0],
        "callBackUrl": CALLBACK_URL,
        "input": {"custom_mode": True, "instrumental": False,
                  "model": picked[1], "style": package["style_text"],
                  "title": package["title"], "lyrics": lyrics},
    }
    if package.get("vocal_gender") is not None:
        request["input"]["vocal_gender"] = package["vocal_gender"]
    if package.get("duration") is not None:
        request["input"]["duration"] = package["duration"]
    stamped = no_echo_stamp(request, kind="song")
    stamped["soundtrack"] = {
        "mode": TRACK_MODE,
        "spoken_in_lyrics": True,
        "spoken_source": SPOKEN_SOURCE,
        "spoken_line_ids": [ln["line_id"] for ln in package["lines"]
                            if ln["delivery"] == "spoken"],
        "no_separate_spoken_takes": True,
        "no_added_bed": True,
    }
    verdict = no_echo_check(stamped)
    if verdict["outcome"] != "ok":
        raise ValueError("NO_ECHO_CHECK_FAILED:" +
                         "; ".join(verdict["errors"]))
    return stamped


# ---------------------------------------------------------------- receipt ---

def record_soundtrack(receipt, generation_id, retakes=()):
    """Stamp the receipt: final audio from exactly ONE Suno generation id.

    ``retakes`` is the whole-track retake list; every entry needs a non-empty
    ``generation_id`` AND ``"kind": "whole-track"`` (the whole-track retake
    marker from manual F2) or the record is refused -- a split retake can
    never masquerade as a track. Returns the receipt.
    """
    if not isinstance(receipt, dict):
        raise ValueError("RECEIPT_INVALID:not a dict")
    if not isinstance(generation_id, str) or not generation_id.strip():
        raise ValueError("GENERATION_ID_INVALID:empty")
    if retakes is None:
        retakes = ()
    if isinstance(retakes, dict) or not isinstance(retakes, (list, tuple)):
        raise ValueError("RETAKE_LIST_INVALID:not a list")
    rows = []
    for retake in retakes:
        if not isinstance(retake, dict):
            raise ValueError("RETAKE_INVALID:entry is not a dict")
        rid = retake.get("generation_id")
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError("RETAKE_GENERATION_ID_INVALID:empty")
        if retake.get("kind") != RETAKE_KIND:
            raise ValueError("RETAKE_NOT_WHOLE_TRACK:%s (retakes are always "
                             "whole-track; a split piece is refused)"
                             % rid)
        rows.append({"generation_id": rid, "kind": RETAKE_KIND,
                     "reason": str(retake.get("reason", ""))})
    receipt["soundtrack"] = {
        "mode": TRACK_MODE,
        "primary_generation_id": generation_id,
        "generation_count": 1 + len(rows),
        "spoken_in_lyrics": True,
        "spoken_source": SPOKEN_SOURCE,
        "retakes": rows,
    }
    return receipt


def verify_soundtrack(receipt):
    """Error list re-reading the receipt. Empty list = F1 provable.

    Fail-closed: a second generation id in ``receipt["audio_jobs"]`` without
    the whole-track retake marker fails the receipt, as does any missing or
    malformed soundtrack stamp. ``verify_soundtrack(None)`` and any non-dict
    receipt return the RECEIPT_INVALID error list.
    """
    if not isinstance(receipt, dict):
        return ["RECEIPT_INVALID:not a dict"]
    block = receipt.get("soundtrack")
    if not isinstance(block, dict):
        return ["SOUNDTRACK_NOT_RECORDED"]
    errs = []
    if block.get("mode") != TRACK_MODE:
        errs.append("SOUNDTRACK_MODE_NOT_ONE_GENERATION:%r" % (block.get("mode"),))
    if block.get("primary_generation_id") is None:
        errs.append("SOUNDTRACK_NO_GENERATION_ID")
    retakes = block.get("retakes")
    if retakes is None:
        errs.append("SOUNDTRACK_RETAKE_LIST_MISSING")
    elif isinstance(retakes, list):
        for retake in retakes:
            if not isinstance(retake, dict) or \
                    retake.get("kind") != RETAKE_KIND:
                gid = retake.get("generation_id") if isinstance(retake, dict) \
                    else retake
                errs.append("RETAKE_NOT_WHOLE_TRACK:%s" % gid)
    count = block.get("generation_count")
    retake_rows = retakes if isinstance(retakes, list) else []
    if count != 1 + len(retake_rows):
        errs.append("SOUNDTRACK_COUNT_MISMATCH:%r" % (count,))
    jobs = receipt.get("audio_jobs")
    if jobs is not None:
        if isinstance(jobs, list):
            for job in jobs:
                gid = job.get("generation_id") if isinstance(job, dict) else None
                if gid is not None and \
                        gid != block.get("primary_generation_id") and \
                        (not isinstance(job, dict) or
                         job.get("kind") != RETAKE_KIND):
                    errs.append("SOUNDTRACK_MULTI_GENERATION:%s (a second "
                                "generation id needs a whole-track retake "
                                "marker)" % gid)
        else:
            errs.append("AUDIO_JOBS_INVALID:not a list")
    return errs

# ------------------------------------------------- F2 whole-track intake ---

#: F2 reason code (manual Part F item F2, High): a run in F1 mode that asks
#: for a partial Suno job is refused. Only two shapes ever pass -- the ONE
#: full-track generation itself, or ONE whole-track retake of a failed take.
PARTIAL_SUNO_JOB = "PARTIAL_SUNO_JOB"

#: The only job kinds F1 mode accepts at intake. Anything else (a per-line
#: slice, a patch of one spoken take, a second bed, an unlabelled row) is a
#: partial Suno job.
FULL_TRACK_KIND = "full-track"
WHOLE_TRACK_RETAKE_KIND = "whole-track-retake"

def _job_row(job):
    """The job as a dict, or None when malformed. JSON string rows parse."""
    if isinstance(job, dict):
        return job
    if isinstance(job, str):
        try:
            parsed = json.loads(job)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None

def refuse_partial_suno_job(run_receipt, job):
    """Refuse a partial Suno job in F1 mode. [] = allowed, else [reason, ...].

    ``run_receipt`` is the run's receipt carrying a ``soundtrack`` block --
    the recorded stamp (``record_soundtrack`` output) or the run's own
    generated F1 request (``generate_soundtrack_request`` stamps the same
    block, minus the generation id until one is submitted). ``mode`` must be
    ``TRACK_MODE``; anything else (no block, another mode) refuses, fail
    closed. ``job`` is the job-intake row: a dict (or JSON-object string)
    with ``kind`` and the retake links when it is a retake. Only two shapes
    pass:

      * ``kind == "full-track"`` -- the ONE Suno generation itself. Its own
        ``generation_id`` does not exist yet at intake; if one is carried it
        must be non-empty.
      * ``kind == "whole-track-retake"`` -- one whole-track retake of a
        FAILED take: ``retake_of`` must name a take, match the run's
        recorded primary generation id, and the run must not already carry
        a succeeded retake or this same retake.

    Anything else -- a slice, a spoken-take patch, a second bed, an
    unlabelled or malformed row -- refuses ``PARTIAL_SUNO_JOB``.
    """
    row = _job_row(job)
    if row is None:
        return ["%s:job is not a job object" % PARTIAL_SUNO_JOB]

    block = (run_receipt or {}).get("soundtrack") \
        if isinstance(run_receipt, dict) else None
    if not isinstance(block, dict):
        return ["%s:run has no soundtrack record; F1 mode unproven"
                % PARTIAL_SUNO_JOB]
    if block.get("mode") != TRACK_MODE:
        return ["%s:run soundtrack mode %r is not %r"
                % (PARTIAL_SUNO_JOB, block.get("mode"), TRACK_MODE)]

    kind = row.get("kind")
    if kind == FULL_TRACK_KIND:
        gid = row.get("generation_id")
        if gid is not None and (not isinstance(gid, str) or not gid.strip()):
            return ["%s:full-track job carries an empty generation_id"
                    % PARTIAL_SUNO_JOB]
        return []
    if kind == WHOLE_TRACK_RETAKE_KIND:
        gid = row.get("generation_id")
        if gid is not None and (not isinstance(gid, str) or not gid.strip()):
            return ["%s:retake job carries an empty generation_id"
                    % PARTIAL_SUNO_JOB]
        primary = block.get("primary_generation_id")
        if not isinstance(primary, str) or not primary.strip():
            return ["%s:run records no primary generation id; a whole-track "
                    "retake must replace a failed take" % PARTIAL_SUNO_JOB]
        retake_of = row.get("retake_of")
        if not isinstance(retake_of, str) or not retake_of.strip():
            return ["%s:whole-track retake must name retake_of (the failed "
                    "take it replaces)" % PARTIAL_SUNO_JOB]
        if retake_of != primary:
            return ["%s:retake_of %r is not this run's primary generation id"
                    % (PARTIAL_SUNO_JOB, retake_of)]
        prior = block.get("retakes") if isinstance(block.get("retakes"),
                                                   list) else []
        for recorded in prior:
            if not isinstance(recorded, dict):
                continue
            if gid is not None and recorded.get("generation_id") == gid:
                return ["%s:retake %s already recorded; a take is retaken once"
                        % (PARTIAL_SUNO_JOB, gid)]
            if str(recorded.get("reason", "")).strip().lower() == "succeeded":
                return ["%s:a retake of this track already succeeded; retakes "
                        "replace a failed take only" % PARTIAL_SUNO_JOB]
        return []
    label = kind if isinstance(kind, str) and kind.strip() else "unlabelled"
    return ["%s:job kind %r is neither a full-track generation nor one "
            "whole-track retake (retakes are whole-track only in F1 mode)"
            % (PARTIAL_SUNO_JOB, label)]

def job_intake(run_receipt, jobs):
    """F2 intake seam: split the dispatcher's Suno jobs into legal shapes.

    Called where the dispatcher reads a run's job list, before any submit.
    Returns ``(allowed, refused)``: each refused row is the job dict plus
    ``intake_errors`` (the ``PARTIAL_SUNO_JOB`` reasons). Non-dict rows are
    refused, never a crash -- the reason rides on a fresh row.
    """
    allowed, refused = [], []
    for job in (jobs or []):
        errs = refuse_partial_suno_job(run_receipt, job)
        if errs:
            row = job if isinstance(job, dict) else {"job": job}
            refused.append(dict(row, intake_errors=errs))
        else:
            allowed.append(job)
    return allowed, refused