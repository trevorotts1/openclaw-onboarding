#!/usr/bin/env python3
"""media_gate.py: real-media QC gate, Plan 9.4 (V2 lesson from W4-07). stdlib only.

A stage that is meant to produce media cannot pass unless the media file
exists, is the right duration and format, and the checker inspected it
(multiple frames for video, a listening check for audio). W4-07 passed QC
having produced no song, image or video; this gate makes that structurally
impossible to repeat.

Fail-closed, never optimistic:
- missing path, non-file, zero bytes            -> FAIL
- container bytes that do not match the spec    -> FAIL
- duration outside tolerance of the target      -> FAIL
- format or duration that cannot be determined  -> UNAVAILABLE (evidence
  gap: never counts as PASS, so delivery stays blocked until probed)
- missing frame refs / listening check / reviewer identity -> FAIL

Duration is probed from the real bytes on disk (WAV via the wave module,
MP4/MOV/M4A via the moov/mvhd box); a caller-supplied number is never
trusted as the file's duration. Frame extraction and audio listening belong
to the checker (ffmpeg / ears); this gate only refuses to pass when the
inspector recorded no receipt for the inspection it claims to have done.

ponytail: duration tolerance defaults to 1.0 s (Suno/MP4 container drift);
replace with the profile value the moment directive 17.8 names one.
ponytail: mp4 probe reads only box headers plus moov; add ftyp brands and
codec-level checks when the provider contract names them.
"""
from __future__ import annotations

import os
import wave

PASS = "PASS"
FAIL = "FAIL"
UNAVAILABLE = "UNAVAILABLE"

KINDS = ("video", "audio", "image")
DEFAULT_TOLERANCE_S = 1.0
MAX_MOOV_BYTES = 33554432  # 32 MiB guard when reading the moov box

#: container -> family (m4a/mov are mp4-family for sniff comparison)
_MP4_FAMILY = frozenset(("mp4", "m4a", "mov"))

KIND_CONTAINERS = {
    "video": frozenset(("mp4",)),
    "audio": frozenset(("wav", "mp4", "m4a")),
    "image": frozenset(("png", "jpg", "webp")),
}


class MediaError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def sniff_container(path):
    """Identify the container from magic bytes. None when unrecognised."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return None
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "mp4"
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(head) >= 3 and head[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


def _probe_wav(path):
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        frames = w.getnframes()
    if rate <= 0:
        return None
    return frames / float(rate)


def _probe_mp4(path):
    """Duration in seconds from moov/mvhd (version 0 or 1), else None."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        total = f.tell()
        off = 0
        while off + 8 <= total:
            f.seek(off)
            hdr = f.read(8)
            if len(hdr) < 8:
                return None
            size = int.from_bytes(hdr[:4], "big")
            typ = hdr[4:8]
            hdr_len = 8
            if size == 1:
                ext = f.read(8)
                if len(ext) < 8:
                    return None
                size = int.from_bytes(ext, "big")
                hdr_len = 16
            elif size == 0:
                size = total - off
            if size < hdr_len or off + size > total:
                return None
            if typ == b"moov":
                payload_len = size - hdr_len
                if payload_len <= 0 or payload_len > MAX_MOOV_BYTES:
                    return None
                f.seek(off + hdr_len)
                payload = f.read(payload_len)
                return _mvhd_seconds(payload)
            off += size
    return None


def _mvhd_seconds(moov_payload):
    """mvhd box payload -> seconds. mvhd is commonly the moov's first child,
    so its 4cc can sit at offset 0 of the payload: locate the tag, then read
    from the version byte that follows it."""
    idx = moov_payload.find(b"mvhd")
    if idx < 0:
        return None
    payload = moov_payload[idx + 4:]
    if not payload:
        return None
    version = payload[0]
    try:
        if version == 1:
            # v1: version(1) flags(3) creation(8) modification(8)
            #     timescale(4) duration(8)
            if len(payload) < 32:
                return None
            timescale = int.from_bytes(payload[20:24], "big")
            duration = int.from_bytes(payload[24:32], "big")
        else:
            # v0: version(1) flags(3) creation(4) modification(4)
            #     timescale(4) duration(4)
            if len(payload) < 20:
                return None
            timescale = int.from_bytes(payload[12:16], "big")
            duration = int.from_bytes(payload[16:20], "big")
    except (IndexError, ValueError):
        return None
    if timescale <= 0:
        return None
    return duration / float(timescale)


def probe_duration(path, container):
    """Real duration in seconds, or None when it cannot be determined."""
    if container in ("wav",):
        try:
            return _probe_wav(path)
        except (OSError, EOFError, wave.Error):
            return None
    if container in _MP4_FAMILY:
        try:
            return _probe_mp4(path)
        except OSError:
            return None
    return None  # images have no duration


def _fail(failures, code, detail):
    failures.append({"code": code, "detail": detail, "verdict": FAIL})


def _unavailable(failures, code, detail):
    failures.append({"code": code, "detail": detail, "verdict": UNAVAILABLE})


def check_media(spec, kind_hint=None):
    """Inspect the real media file behind a QC claim.

    spec: {kind, path, target_seconds, container?, tolerance_seconds?,
           inspection?, reviewer?}. Returns a dict with verdict, code,
    failures, container, duration_seconds.
    """
    if not isinstance(spec, dict):
        raise MediaError("BAD_SPEC", "media spec must be an object")
    failures = []
    kind = spec.get("kind") or kind_hint
    if kind not in KINDS:
        _fail(failures, "MEDIA_KIND_UNKNOWN",
              "kind %r not in %s" % (kind, list(KINDS)))
        return {"verdict": FAIL, "code": "MEDIA_KIND_UNKNOWN",
                "failures": failures, "container": None,
                "duration_seconds": None}
    # A song stage may not be waved through on a video file even when that
    # file is itself perfect: the stage names the kind it must produce.
    if kind_hint is not None and kind != kind_hint:
        _fail(failures, "MEDIA_KIND_MISMATCH",
              "media kind %r != stage kind %r" % (kind, kind_hint))
        return {"verdict": FAIL, "code": "MEDIA_KIND_MISMATCH",
                "failures": failures, "container": None,
                "duration_seconds": None}

    path = spec.get("path")
    if not isinstance(path, str) or not path.strip():
        _fail(failures, "MEDIA_FILE_MISSING", "no media path recorded")
        return {"verdict": FAIL, "code": "MEDIA_FILE_MISSING",
                "failures": failures, "container": None,
                "duration_seconds": None}
    if not os.path.exists(path):
        _fail(failures, "MEDIA_FILE_MISSING",
              "media file does not exist: %s" % path)
        return {"verdict": FAIL, "code": "MEDIA_FILE_MISSING",
                "failures": failures, "container": None,
                "duration_seconds": None}
    if not os.path.isfile(path):
        _fail(failures, "MEDIA_NOT_A_FILE", "%s is not a regular file" % path)
        return {"verdict": FAIL, "code": "MEDIA_NOT_A_FILE",
                "failures": failures, "container": None,
                "duration_seconds": None}
    if os.path.getsize(path) == 0:
        _fail(failures, "MEDIA_FILE_EMPTY", "%s is zero bytes" % path)
        return {"verdict": FAIL, "code": "MEDIA_FILE_EMPTY",
                "failures": failures, "container": None,
                "duration_seconds": None}

    container = sniff_container(path)
    if container is None:
        _unavailable(failures, "MEDIA_FORMAT_UNKNOWN",
                     "cannot identify container of %s" % path)
    else:
        allowed = KIND_CONTAINERS[kind]
        if container not in allowed:
            _fail(failures, "MEDIA_FORMAT_MISMATCH",
                  "container %r not allowed for %s (allowed: %s)"
                  % (container, kind, sorted(allowed)))
        want = spec.get("container")
        if want and container != want and not (
                want in _MP4_FAMILY and container in _MP4_FAMILY):
            _fail(failures, "MEDIA_FORMAT_MISMATCH",
                  "container %r != declared %r" % (container, want))

    duration = None
    if kind in ("video", "audio"):
        if container is None:
            _unavailable(failures, "MEDIA_DURATION_UNKNOWN",
                         "no container, duration not provable")
        else:
            duration = probe_duration(path, container)
            if duration is None:
                _unavailable(failures, "MEDIA_DURATION_UNKNOWN",
                             "duration not probeable in %s" % path)
            else:
                target = spec.get("target_seconds")
                if target is None:
                    _fail(failures, "MEDIA_NO_TARGET",
                          "no target duration recorded for this stage")
                else:
                    try:
                        target = float(target)
                    except (TypeError, ValueError):
                        _fail(failures, "MEDIA_NO_TARGET",
                              "target_seconds not a number: %r"
                              % (spec.get("target_seconds"),))
                    else:
                        tol = float(spec.get("tolerance_seconds",
                                             DEFAULT_TOLERANCE_S))
                        if abs(duration - target) > tol:
                            _fail(failures, "MEDIA_DURATION_MISMATCH",
                                  "duration %.3fs outside %.3fs of target %.3fs"
                                  % (duration, tol, target))

    inspection = spec.get("inspection")
    if not isinstance(inspection, dict):
        inspection = {}
    if kind == "video":
        frames = inspection.get("frames")
        if not isinstance(frames, list):
            frames = []
        distinct = {str(f).strip() for f in frames if str(f).strip()}
        if len(distinct) < 2:
            _fail(failures, "MEDIA_NO_FRAMES",
                  "video requires inspected frames (>=2 distinct refs), got %d"
                  % len(distinct))
    elif kind == "audio":
        listening = inspection.get("listening")
        if not isinstance(listening, dict):
            _fail(failures, "MEDIA_NO_LISTENING",
                  "audio requires a listening check receipt")
        else:
            method = listening.get("method")
            if not isinstance(method, str) or not method.strip():
                _fail(failures, "MEDIA_NO_LISTENING",
                      "listening.method must record how the audio was heard")
            try:
                listened = float(listening.get("listened_seconds"))
            except (TypeError, ValueError):
                listened = 0.0
            if listened <= 0:
                _fail(failures, "MEDIA_NO_LISTENING",
                      "listening.listened_seconds must be > 0")
    else:  # image: the frame itself is the inspection target
        refs = inspection.get("frames")
        if not isinstance(refs, list) or not [r for r in refs if str(r).strip()]:
            _fail(failures, "MEDIA_NO_FRAMES",
                  "image requires the inspected frame ref")

    reviewer = spec.get("reviewer")
    identity = reviewer.get("identity") if isinstance(reviewer, dict) else None
    if not isinstance(identity, str) or not identity.strip():
        _fail(failures, "MEDIA_NO_REVIEWER",
              "no checker identity inspected this media")

    if not failures:
        return {"verdict": PASS, "code": None, "failures": [],
                "container": container, "duration_seconds": duration}
    verdict = UNAVAILABLE if all(f["verdict"] == UNAVAILABLE
                                 for f in failures) else FAIL
    return {"verdict": verdict, "code": failures[0]["code"],
            "failures": failures, "container": container,
            "duration_seconds": duration}
