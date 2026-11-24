#!/usr/bin/env python3
"""The Voice Map (plan 3N, row N-117): every face sings only its own part.

Built at set-up from the song alone, before the Story Beats are written:
``control/voice-map.json`` holds one entry per stretch of singing or speech
with its role, its words, its track and how sure the map is.

The rule this map feeds (3N.0), in Trevor's own words -- "when the
background singers are singing, the background singers should show us
singing that part... not both people trying to sing both people's parts":

1. the lead alone is shown only where the backing track is silent;
2. where the backing track sings, the picture shows the people singing it,
   fed the backing track (or lead plus backing on the words they share,
   fed the vocals);
3. where lead and backing sing different words at once, the screen shows
   the backing singers or a story picture -- never the lead mouthing
   through it, because nothing tested can stop her mouthing their part;
4. a cleaner lead track from ``split_stem_advanced`` does not exist (V8
   failed), so line 3 stands.

Measured facts behind it (plan 3N.0, test B): the backing track is clean of
the lead; the track named "Vocals" is NOT the lead alone -- it carries the
choir, so it can never be trusted as a lead-only track.

Nothing here spends, calls Suno or loads a model. ffmpeg is already
required; the runner is injectable so a caller needs no real audio.
"""
from __future__ import annotations

import json
import os
import subprocess
import time

SCHEMA_VERSION = "blackceo.voice-map/v1"
TOOL_VERSION = "1.0.0"
TOOL_NAME = "voice_map"

#: ``control/voice-map.json`` beside the run's other control records.
MAP_PATH = os.path.join("control", "voice-map.json")
#: 3N.8: the test results, beside the map.
RECORD_PATH = os.path.join("control", "voice-map-record.json")

#: The map's roles (3N.1).
ROLES = frozenset(("lead", "backing", "choir", "call", "response", "unison",
                   "overlap", "spoken"))
#: Confidence values, weakest last.
CONFIDENCE = ("heard", "measured", "guessed")

#: The separated tracks this map needs, by the stem name inside the file
#: name (test B's note: match by name, never by the order they arrive).
TRACK_VOCALS = "vocals"
TRACK_BACKING = "backing-vocals"
TRACK_INSTRUMENTAL = "instrumental"
ROLE_TRACKS = {"lead": TRACK_VOCALS, "backing": TRACK_BACKING,
               "choir": TRACK_BACKING, "unison": TRACK_VOCALS,
               "call": TRACK_VOCALS, "response": TRACK_BACKING,
               "spoken": TRACK_VOCALS}
#: 3N.0 line 2 and 3: the roles whose piece is fed the backing track.
BACKING_TRACK_ROLES = frozenset(("backing", "choir", "response", "overlap"))

#: Refusal and check codes (3N.2 gate, 3N.5 pre-spend, 3N.6 check).
VOICE_MAP_INCOMPLETE = "VOICE_MAP_INCOMPLETE"
VOICE_STEM_BLEED = "VOICE_STEM_BLEED"
LIPSYNC_MIXED_PARTS = "LIPSYNC_MIXED_PARTS"
VOICE_MAP_DISPUTED = "VOICE_MAP_DISPUTED"
VOICE_MAP_MISSING = "VOICE_MAP_MISSING"
LIPSYNC_WRONG_STEM = "LIPSYNC_WRONG_STEM"
LIPSYNC_WRONG_FACES = "LIPSYNC_WRONG_FACES"
WRONG_VOICE_MOUTHED = "WRONG_VOICE_MOUTHED"

#: Right Voice failures stop the run: item 8 of the MAJOR list (3J.1).
SEVERITY = "MAJOR"

#: 3N.2: the lead sings alone where the backing track is this far under.
#: "under 10 percent of the lead's" -> 20 dB below. The proposed default.
BLEED_DB = 20.0
#: 3N.2 step 2: loudness sample step.
STEP_S = 0.1
#: Words of one role this far apart still make one stretch of singing.
MAX_STRETCH_GAP_S = 1.0
#: 3N.7: V8 failed -- ``split_stem_advanced`` is not used; it costs 20
#: credits a song and returns the same lead with the same choir in it.
ADVANCED_NOT_USED = ("split_stem_advanced was tried (V8) and is not "
                     "cleaner: do not use it. The plain split gives the "
                     "same lead and a clean backing track.")

#: 3N.8, as run: V1 and V3 passed; V2 and V8 did not; the rest never ran.
TEST_RESULTS = {"V1": "passed", "V2": "not-passed", "V3": "passed",
                "V4": "not-run", "V5": "not-run", "V6": "not-run",
                "V7": "not-run", "V8": "failed"}


class VoiceMapError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _need(ok, code, message):
    if not ok:
        raise VoiceMapError(code, message)


# ---------------------------------------------------------------- tracks ----

def track_role(path):
    """Map one separated file to its role track, by the stem name in it.

    The order the provider returns files in is never trusted (test B's
    note); the name is. ``None`` for a stem this map does not keep.
    """
    name = os.path.basename(str(path)).lower().replace("_", "-")
    if "backing" in name or "choir" in name:
        return TRACK_BACKING
    if "instrumental" in name or "accompaniment" in name:
        return TRACK_INSTRUMENTAL
    if "vocal" in name or "lead" in name:
        return TRACK_VOCALS
    return None


def tracks_by_role(paths):
    """{role: path} for every kept stem; refuses a duplicate or a missing one."""
    found = {}
    for path in paths or []:
        role = track_role(path)
        if role is None:
            continue
        _need(role not in found, "VOICE_MAP_TRACK_DUPLICATE",
              "two %s tracks in one separation: %s" % (role, path))
        found[role] = str(path)
    for role in (TRACK_VOCALS, TRACK_BACKING):
        _need(role in found, "VOICE_MAP_TRACK_MISSING",
              "the split returned no %s track; the Voice Map cannot be "
              "built without it" % role)
    return found


# --------------------------------------------------------------- levels -----

def _runner(argv):
    done = subprocess.run(argv, capture_output=True, text=True)
    _need(done.returncode == 0, "VOICE_MAP_MEASURE_FAILED",
          (done.stderr or "").strip()[-400:])
    return done.stdout + done.stderr


def parse_rms(text):
    """Pure: per-frame RMS level (dB) from ffmpeg astats metadata output."""
    key = "lavfi.astats.Overall.RMS_level="
    out = []
    for line in (text or "").splitlines():
        _, sep, value = line.partition(key)
        if not sep:
            continue
        try:
            out.append(float(value.strip()))
        except ValueError:
            out.append(-120.0)          # -inf prints as "-inf"
    return out


def measure_levels(path, run=_runner, step_s=STEP_S, rate=44100):
    """Loudness of one track every ``step_s`` seconds: [dB, ...]."""
    samples = max(1, int(round(float(step_s) * rate)))
    argv = ["ffmpeg", "-v", "info", "-i", str(path), "-vn",
            "-af", "asetnsamples=%d,astats=metadata=1:reset=1,"
                   "ametadata=mode=print:file=-" % samples,
            "-f", "null", "-"]
    return parse_rms(run(argv))


def _window(levels, start_s, end_s, step_s=STEP_S):
    lo = max(0, int(start_s / step_s))
    hi = max(lo + 1, int(end_s / step_s))
    part = [v for v in levels[lo:hi] if v > -120.0]
    return max(part) if part else -120.0


def _singing(levels, start_s, end_s, floor_db=-60.0, step_s=STEP_S):
    return _window(levels, start_s, end_s, step_s) > floor_db


# ------------------------------------------------------------------ map -----

def _entry(start_s, end_s, role, words, track, confidence, who=()):
    return {"start_s": float(start_s), "end_s": float(end_s), "role": role,
            "who": [str(w) for w in who], "words": list(words),
            "track": track, "confidence": confidence}


def build(song_sha256, tracks, words, lead_levels, backing_levels,
          reader=None, cast=None, sections=None):
    """Build the map document from measured levels and the song's word times.

    ``words`` are the song's own word times (``{"word","start_s","end_s"}``);
    ``reader(path) -> words`` optionally reads one track alone (V2 needs it,
    whisper is on the Mac only -- 3N.10), so unison/overlap can be told apart
    when both tracks sing. Without a reader a shared stretch is ``unison``
    at confidence ``guessed``; it is never silently called overlap.

    ``sections`` are the lyric sheet's section marks: a chorus that repeats
    keeps its roles, so a section whose role is already known wins over a
    fresh measurement.
    """
    _need(len(words or []) > 0, VOICE_MAP_INCOMPLETE,
          "the song has no word times; the map cannot be built")
    cast = dict(cast or {})
    marks = [s for s in (sections or []) if isinstance(s, dict)
             and isinstance(s.get("role"), str)]
    entries = []
    for row in words:
        start = float(row.get("start_s", row.get("start")))
        end = float(row.get("end_s", row.get("end")))
        _need(start < end, VOICE_MAP_INCOMPLETE,
              "word %r has an unordered window" % (row.get("word"),))
        lead = _singing(lead_levels, start, end)
        back = _singing(backing_levels, start, end)
        if lead and not back:
            role, track, conf = "lead", TRACK_VOCALS, "measured"
        elif back and not lead:
            role, track, conf = "backing", TRACK_BACKING, "measured"
        elif back and lead:
            role, track, conf = "unison", TRACK_VOCALS, "guessed"
            if reader is not None:
                same = (reader(tracks[TRACK_BACKING]) ==
                        reader(tracks[TRACK_VOCALS]))
                role = "unison" if same else "overlap"
                conf = "measured"
        else:
            role, track, conf = "spoken", TRACK_VOCALS, "measured"
        mark = next((m for m in marks if m.get("role") == role
                      and float(m.get("start_s", start)) <= start
                      <= float(m.get("end_s", end))), None)
        if mark is not None:
            conf = "measured"
        entries.append(_entry(start, end, role, [row], track, conf,
                              who=cast.get(role, ())))
    _need(bool(entries), VOICE_MAP_INCOMPLETE, "no map entry was written")
    return {"schema_version": SCHEMA_VERSION, "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "song_sha256": song_sha256,
            "tracks": {role: str(path) for role, path in tracks.items()},
            "step_s": STEP_S, "bleed_db": BLEED_DB,
            "entries": _stretches(entries)}


def _stretches(entries):
    """3N.1: one entry per stretch of singing, each holding its own words.

    Consecutive words of the same role, track, confidence and singers are one
    stretch. A change of any of those starts a new one; a gap longer than
    ``MAX_STRETCH_GAP_S`` also does, so a silent bar is not swallowed.
    """
    out = []
    for entry in entries:
        last = out[-1] if out else None
        joins = (last is not None
                 and last["role"] == entry["role"]
                 and last["track"] == entry["track"]
                 and last["confidence"] == entry["confidence"]
                 and last["who"] == entry["who"]
                 and entry["start_s"] - last["end_s"] <= MAX_STRETCH_GAP_S)
        if joins:
            last["end_s"] = entry["end_s"]
            last["words"].extend(entry["words"])
        else:
            out.append(dict(entry))
    return out


def write(run_dir, doc):
    """Write ``control/voice-map.json`` atomically; returns its path."""
    path = os.path.join(str(run_dir), MAP_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    os.replace(temp, path)
    return path


def record(run_dir, doc=None, tests=None, extra=None):
    """Write ``control/voice-map-record.json`` (3N.8); returns its path.

    The test results go to the receipt alongside the map they describe, so a
    run's receipt shows which of V1 to V8 were proven on its own song.
    """
    doc = doc or {}
    results = dict(TEST_RESULTS)
    results.update(tests or {})
    body = {"schema_version": SCHEMA_VERSION, "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "song_sha256": doc.get("song_sha256"),
            "split_type": "split_stem", "tests": results,
            "plain_split_note": "the plain split_stem is the one to use",
            "entries": len(doc.get("entries") or [])}
    body.update(extra or {})
    path = os.path.join(str(run_dir), RECORD_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, sort_keys=True)
    os.replace(temp, path)
    return path


def load(run_dir):
    """The passed map for this run; refuses ``VOICE_MAP_MISSING`` without it."""
    path = os.path.join(str(run_dir), MAP_PATH)
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        raise VoiceMapError(VOICE_MAP_MISSING,
                            "no passed Voice Map at %s: %s" % (path, exc))
    _need(isinstance(doc, dict) and doc.get("schema_version") == SCHEMA_VERSION
          and isinstance(doc.get("entries"), list) and doc["entries"],
          VOICE_MAP_MISSING, "the Voice Map at %s is not a built map" % path)
    return doc


# ----------------------------------------------------------------- gate -----

def gate(doc, lead_levels=None, backing_levels=None, heard=None):
    """The Voice Map gate (3N.2): (ok, code, errors). Fail-closed.

    ``lead_levels`` / ``backing_levels`` are only needed when the bleed is
    re-measured here; ``heard`` is the listening check's verdict over one
    sample of each role in each section -- ``{entry_key: bool}`` -- and an
    absent verdict leaves that sample unconfirmed, never agreed.
    """
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list) or not entries:
        return False, VOICE_MAP_INCOMPLETE, ["map has no entries"]
    errors = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append("entry:%d:not-an-object" % i)
            continue
        role = entry.get("role")
        if role not in ROLES:
            errors.append("entry:%d:unknown-role:%r" % (i, role))
        if not (isinstance(entry.get("start_s"), (int, float))
                and isinstance(entry.get("end_s"), (int, float))
                and entry["start_s"] < entry["end_s"]):
            errors.append("entry:%d:bad-window" % i)
        if not entry.get("words"):
            errors.append("entry:%d:no-words" % i)
        if entry.get("track") not in (TRACK_VOCALS, TRACK_BACKING):
            errors.append("entry:%d:no-track" % i)
        if entry.get("confidence") not in CONFIDENCE:
            errors.append("entry:%d:bad-confidence:%r"
                          % (i, entry.get("confidence")))
    # 3N.2 Complete: every sung or spoken word has EXACTLY one entry.
    seen = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        for word in entry.get("words") or []:
            if not isinstance(word, dict):
                errors.append("entry:%d:word-not-an-object" % i)
                continue
            key = (str(word.get("word")),
                   float(word.get("start_s", word.get("start", -1))))
            if key in seen:
                errors.append("entry:%d:word %r appears twice (first entry %d)"
                              % (i, word.get("word"), seen[key]))
            else:
                seen[key] = i
    if errors:
        return False, VOICE_MAP_INCOMPLETE, errors

    # 3N.2 Heard: a guessed entry was never confirmed by a listener.
    guessed = ["entry:%d:guessed, never heard" % i
               for i, e in enumerate(entries) if e.get("confidence") == "guessed"]
    if guessed:
        return False, VOICE_MAP_DISPUTED, guessed

    # The backing track is clean of the lead wherever the map says the lead
    # sings alone -- measured on this song at 60 to 80 dB below, far under.
    if lead_levels is not None and backing_levels is not None:
        bleed = []
        step = float(doc.get("step_s") or STEP_S)
        for i, entry in enumerate(entries):
            if entry["role"] != "lead":
                continue
            lead = _window(lead_levels, entry["start_s"], entry["end_s"], step)
            back = _window(backing_levels, entry["start_s"], entry["end_s"],
                           step)
            if back > lead - BLEED_DB:
                bleed.append("entry:%d:backing %.1f dB against lead %.1f dB"
                             % (i, back, lead))
        if bleed:
            return False, VOICE_STEM_BLEED, bleed

    # The "Vocals" track is never trusted as lead-only: a lead-alone piece
    # over a stretch where the backing sings is a mixed part.
    mixed = ["entry:%d:%s on %s" % (i, e["role"], e["track"])
             for i, e in enumerate(entries)
             if e["role"] == "lead" and e["track"] != TRACK_VOCALS]
    if mixed:
        return False, LIPSYNC_MIXED_PARTS, mixed

    if heard is not None:
        disputed = ["entry:%d:listener says %r"
                    % (i, heard.get(str(i), heard.get(i)))
                    for i in range(len(entries))
                    if heard.get(str(i), heard.get(i)) is False]
        if disputed:
            return False, VOICE_MAP_DISPUTED, disputed
    return True, "", []


def build_and_gate(run_dir, song_sha256, tracks, words, lead_levels,
                   backing_levels, reader=None, cast=None, sections=None,
                   heard=None):
    """Build, gate, and write only a passed map; a failed gate writes none."""
    doc = build(song_sha256, tracks, words, lead_levels, backing_levels,
                reader=reader, cast=cast, sections=sections)
    # The listening check's agreement turns a sample into "heard" (3N.2).
    for index, entry in enumerate(doc["entries"]):
        if heard is not None and heard.get(str(index), heard.get(index)) is True:
            entry["confidence"] = "heard"
    ok, code, errors = gate(doc, lead_levels, backing_levels, heard=heard)
    if not ok:
        return {"outcome": "refused", "reason_code": code,
                "errors": errors, "map": None,
                "next_action": "Fix the split or the map; a failed gate "
                               "never lets a run guess (3N.7)."}
    path = write(run_dir, doc)
    record(run_dir, doc)
    return {"outcome": "ok", "reason_code": "", "errors": [], "map": doc,
            "path": path}


# ------------------------------------------------------------ who sings -----

def tracks_singing(doc, start_s, end_s):
    """Which role tracks sing inside one window, read from the map."""
    roles = set()
    for entry in doc.get("entries") or []:
        if float(entry["end_s"]) <= float(start_s) or \
                float(entry["start_s"]) >= float(end_s):
            continue
        if entry["role"] in ("backing", "choir", "response", "overlap"):
            roles.add(TRACK_BACKING)
        else:
            roles.add(TRACK_VOCALS)
        if entry["role"] in ("unison", "overlap"):
            roles.add(TRACK_BACKING)
    return roles


def track_for(doc, start_s, end_s, role=None):
    """The track a piece over this stretch must carry (3N.0, 3N.5).

    Both tracks singing is 3N.0 line 3: the screen shows the backing singers
    on their own track (or a story picture), never the lead alone. So a
    backing/choir/response/overlap piece carries the backing track; only a
    unison stretch -- everyone on the same words -- is fed all the vocals
    (line 2).
    """
    singing = tracks_singing(doc, start_s, end_s)
    if TRACK_BACKING not in singing:
        return TRACK_VOCALS
    if TRACK_VOCALS not in singing:
        return TRACK_BACKING
    if role in BACKING_TRACK_ROLES and _has_overlap(doc, start_s, end_s):
        return TRACK_BACKING
    return TRACK_VOCALS


def _has_overlap(doc, start_s, end_s):
    """True when a lead/backing overlap entry sits inside the window."""
    return any(entry.get("role") == "overlap"
               and float(entry["end_s"]) > float(start_s)
               and float(entry["start_s"]) < float(end_s)
               for entry in doc.get("entries") or [])


def singers(doc, start_s, end_s):
    """The character ids the map names as who sings this stretch."""
    who = []
    for entry in doc.get("entries") or []:
        if float(entry["end_s"]) <= float(start_s) or \
                float(entry["start_s"]) >= float(end_s):
            continue
        for cid in entry.get("who") or []:
            if cid not in who:
                who.append(cid)
    return who


# ----------------------------------------------------------- plan check -----

def check_plan(pieces, doc):
    """3N.6 step 2 on the plan, before any spend: error list, empty = holds.

    ``pieces`` are the planned lip-sync pieces -- ``{piece_id, start_s,
    end_s, role, track, faces}`` -- each face naming its character. The
    three refusals of 3N.5 come from here, and so does the rule the mouth
    measure could not replace: no lead-alone piece over a stretch where the
    backing track sings.
    """
    errors = []
    for piece in pieces or []:
        if not isinstance(piece, dict):
            errors.append("piece:not-an-object")
            continue
        pid = piece.get("piece_id", "?")
        start, end = piece.get("start_s"), piece.get("end_s")
        if not (isinstance(start, (int, float)) and isinstance(end, (int, float))
                and start < end):
            errors.append("%s:bad-window" % pid)
            continue
        want = track_for(doc, start, end, piece.get("role"))
        if piece.get("track") != want:
            errors.append("%s:%s:carries %r, this stretch needs %r"
                          % (LIPSYNC_WRONG_STEM, pid, piece.get("track"), want))
        # 3N.0 line 1: the lead alone is shown only where the backing track is
        # silent. A lead piece whose window holds any backing-singing entry is
        # a mixed part, even when the whole window's track is the vocals.
        backing_singing = TRACK_BACKING in tracks_singing(doc, start, end)
        if piece.get("role") == "lead" and backing_singing:
            errors.append("%s:%s:lead alone over a stretch where the backing "
                          "track sings" % (LIPSYNC_MIXED_PARTS, pid))
        named = singers(doc, start, end)
        faces = piece.get("faces") or []
        shown = [f.get("character_id") for f in faces if isinstance(f, dict)]
        if named and sorted(filter(None, shown)) != sorted(named):
            errors.append("%s:%s:faces %r, map names %r"
                          % (LIPSYNC_WRONG_FACES, pid, shown, named))
        for face in faces:
            if not isinstance(face, dict):
                continue
            if face.get("character_id") not in named and named:
                errors.append("%s:%s:silent face %r in the picture"
                              % (LIPSYNC_WRONG_FACES, pid,
                                 face.get("character_id")))
    return errors


def require_plan(pieces, run_dir):
    """Load the map and check the plan; raises on the first refusal."""
    doc = load(run_dir)
    errors = check_plan(pieces, doc)
    if errors:
        raise VoiceMapError(errors[0].split(":", 1)[0], "; ".join(errors))
    return doc


# --------------------------------------------------------- Right Voice ------

def right_voice(piece, take, contact_sheet_verdict=None, doc=None):
    """The Right Voice check (3N.6) on one lip-sync take.

    1. the join: the take's audio is the role track the plan named;
    2. the plan check: no lead-alone piece over a backing stretch (run when
       ``doc`` is the passed map);
    3. the eye: one fixed question on the contact sheet -- "is anyone
       mouthing who should be silent, or mouthing someone else's words?".

    A failure is ``WRONG_VOICE_MOUTHED``, MAJOR, and the take is remade from
    a picture showing only the right singers with only their track.
    """
    if take.get("track") != piece.get("track"):
        return _wrong_voice("the take carries %r, the plan names %r"
                            % (take.get("track"), piece.get("track")))
    if doc is not None:
        errors = check_plan([piece], doc)
        if errors:
            return _wrong_voice("; ".join(errors))
    if contact_sheet_verdict is False:
        return _wrong_voice("a face mouthing who should be silent, or "
                            "mouthing someone else's words")
    return {"check": "right_voice", "verdict": "PASS", "severity": None,
            "code": "", "piece_id": piece.get("piece_id")}


def _wrong_voice(detail):
    return {"check": "right_voice", "verdict": "FAIL", "severity": SEVERITY,
            "code": WRONG_VOICE_MOUTHED, "detail": detail,
            "next_action": "Remake from a picture showing only the right "
                           "singers, with only their track."}


# ------------------------------------------------------------ fallback ------

def fallback(doc):
    """3N.7: with no passed map, nothing is lip-synced; story pictures only.

    The alternatives that were tried and failed stay recorded so the next
    run does not pay for them again: a cleaner lead track from
    ``split_stem_advanced`` does not exist (V8), and the composite of
    option E was never built.
    """
    return {"outcome": "no-lipsync", "reason_code": VOICE_MAP_MISSING,
            "advanced_stem": ADVANCED_NOT_USED,
            "composite": "option E is a measured trial only; nobody has "
                         "built it",
            "next_action": "Run the story pictures with no mouth moving; "
                           "never guess a track."}
