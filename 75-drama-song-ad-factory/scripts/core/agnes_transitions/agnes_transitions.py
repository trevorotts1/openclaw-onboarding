"""agnes_transitions: one continuous video out of separately generated Agnes clips.

SPEC A5.2a (Trevor 2026-10-13): trial A joined independently made scenes with hard
cuts and each clip's own Agnes sound, and it felt like three separate videos. This
module is the fix, in six pieces:

  1. chain_plan()   groups consecutive segments of one scene into a CHAIN, where
                    segment N+1's first_frame is segment N's last frame, and lets
                    a scene change happen only on a Story Beat Blueprint story beat
                    or music cue (an off-beat change is refused).
  2. submit_order() runs the chains in parallel (MAX_CHAINS_IN_FLIGHT at a time)
                    and the segments of ONE chain strictly in order, so the frame
                    chain is never scrambled.
  3. last_frame()   extracts the final frame of a clip (PNG) for the next segment's
                    first_frame (agnes-video-2.5-flash keyframe mode; video-to-video
                    is not available on this path - HTTP 400).
  4. join_argv()    builds the FFmpeg argv: an xfade chain over every join (fade
                    inside a scene, a directional push at a scene change), `-an` on
                    every Agnes input so no clip's own audio survives, the crop-in
                    fill to the chosen shape at 24 fps, and the song as the single
                    audio map.
  5. lipsync_offsets() shifts a lip-sync window earlier by the crossfade overlaps
                    before it, so the mouth stays on the song.
  6. check_joins()  measures the delivered file and returns per-join evidence: no
                    black frame, no intra-scene jump above the cut threshold, audio
                    continuous.

Crossfade length is NOT invented here. Test D (trial-oct13/test-d-30s-music-video,
2026-10-13, the live measurement of this design) found that frame chaining alone
made the hard-cut version nearly seamless and that a 0.5 s crossfade on top added
brief eye ghosting during blinks. So: an intra-scene join takes a very short
XFADE_INTRA_S (0.2 s) fade, and the XFADE_SCENE_S (0.4 s, band 0.3-0.5) crossfade is
kept for scene changes. No live trial is repeated to re-decide this.

Inert until wired: nothing in skill 75 calls this module yet. The caller that wires
it in (the Agnes assembly stage) runs only when the run's agnes.answer is "yes"
(SPEC A2-A3); this module itself makes no network call, no Agnes call and no KIE
call, and ships no key handling.

Stdlib only. FFmpeg/FFprobe are invoked with argument arrays, never shell strings.
"""
import array
import math
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

# --- the shared shape paths (never a second copy of them) --------------------

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)
import delivery_audio  # noqa: E402  (AAC + faststart on every delivered MP4)

_SCRIPTS = os.path.dirname(_CORE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
try:
    import video_still_fill as _VSF  # noqa: E402  (DEL-14 crop-in fill)
except ImportError as _exc:          # pragma: no cover - packaging defect
    raise ImportError(
        "STILL_FILL_PATH_MISSING: agnes_transitions needs "
        "scripts/video_still_fill/ (DEL-14 crop-in fill path); the skill "
        "package is incomplete (%s)" % (_exc,)) from _exc

# --- decided constants (SPEC A5.2a; lengths from Test D 2026-10-13) ---------

#: Scene-change crossfade length. SPEC A5.2a band is 0.3-0.5 s, default 0.4 s.
XFADE_SCENE_S = 0.4

#: Intra-scene crossfade length. Test D: chaining alone is nearly seamless and a
#: 0.5 s crossfade on top ghosted the eyes during a blink -> 0.2 s, and a caller
#: may pass 0.0 for a plain cut.
XFADE_INTRA_S = 0.2

#: ffmpeg's xfade filter has no "push*" transition name; slideleft is the
#: directional push (the incoming scene slides in from the right over the old one).
SCENE_TRANSITION = "slideleft"
INTRA_TRANSITION = "fade"

#: Delivered shape and frame rate (Test D rendered 720x1280 at 24 fps).
DEFAULT_SIZE = (720, 1280)
DEFAULT_FPS = 24

#: At most this many chains render at the same time (SPEC A5.2a trade-off:
#: chained segments run one after another; separate scenes still run 2 at a time).
MAX_CHAINS_IN_FLIGHT = 2

#: Story Beat Blueprint beats a scene change is allowed on (SPEC A5.2a item 2).
#: Keys are the normalised beat names, values the canonical name.
BOUNDARY_BEATS = {
    "erm": "erm_drop", "erm_drop": "erm_drop", "erm_apex": "erm_drop",
    "hero_shift": "hero_shift",
    "breakthrough": "breakthrough", "the_rise": "breakthrough",
    "first_breakthrough": "breakthrough",
    "hook": "hook", "first_hook": "hook",
    "commercial": "commercial", "cta": "commercial", "call_to_action": "commercial",
}

#: How far a segment start may sit from a blueprint beat and still count as being
#: ON that beat (a frame or two of rounding, never a whole shot).
BOUNDARY_TOLERANCE_S = 0.05

#: Join evidence floors (check_joins). A join window frame whose mean luma is
#: under this (0-255 grey) is a black frame. A join whose two sides differ by more
#: than this mean absolute difference is a visible jump; a motivated scene change
#: is allowed to jump, an intra-scene join is not.
BLACK_LUMA = 16.0
JOIN_JUMP_LIMIT = 0.25
AUDIO_FLOOR_DB = -50.0            # same floor delivery_audio gates delivered audio on
JOIN_SAMPLE_W = 32                # grey sample size in pixels, per frame
JOIN_MIN_SAMPLE_S = 0.5


def _fail(reason_code, **kw):
    out = {"ok": False, "reason_code": reason_code}
    out.update(kw)
    return out


# --- 1. chain_plan -----------------------------------------------------------

def _beat_key(name):
    """Normalise a beat name: "Hero Shift" / "hero-shift" / "the_rise" -> key."""
    key = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    return BOUNDARY_BEATS.get(key, key)


def _beats(blueprint):
    """The blueprint's beats as [{"beat", "start_s", "end_s", "music_cue"}]."""
    if blueprint is None:
        return []
    beats = blueprint.get("beats") if isinstance(blueprint, dict) else blueprint
    out = []
    for raw in beats or []:
        start = raw.get("start_s", raw.get("start", 0.0))
        out.append({
            "beat": _beat_key(raw.get("beat", raw.get("name", raw.get("id", "")))),
            "start_s": float(start),
            "end_s": float(raw.get("end_s", start)),
            "music_cue": bool(raw.get("music_cue", False)),
        })
    out.sort(key=lambda b: b["start_s"])
    return out


def _boundary_at(beats, at_s):
    """The beat that STARTS a scene at/at_s (or None). A music cue is a boundary."""
    for b in beats:
        if abs(b["start_s"] - at_s) <= BOUNDARY_TOLERANCE_S:
            if b["beat"] in BOUNDARY_BEATS.values() or b["music_cue"]:
                return b
    return None


def _scene_at(beats, at_s):
    """Which scene covers at_s: the name of the last boundary beat at/before it."""
    scene, at = "scene_open", None
    for b in beats:
        if b["start_s"] <= at_s + BOUNDARY_TOLERANCE_S and (
                b["beat"] in BOUNDARY_BEATS.values() or b["music_cue"]):
            scene, at = b["beat"], b["start_s"]
    return scene, at


def _seg_start(seg):
    return float(seg.get("start_s", seg.get("start", 0.0)))


def _seg_end(seg):
    if seg.get("end_s") is not None:
        return float(seg["end_s"])
    return _seg_start(seg) + float(seg.get("dur", seg.get("duration", 0.0)))


def chain_plan(segments, blueprint):
    """Group segments into chains and describe every join between them.

    segments : [{"segment_id", "start_s", "end_s", "clip"? , "first_frame"?,
                 "scene"?}] in timeline order. An explicit "scene" wins; otherwise
    the scene comes from the blueprint.
    blueprint: {"beats": [{"beat": "hero_shift", "start_s": 30.0, "end_s": 40.0,
                 "music_cue": false}]} (a bare list of beats is accepted too).

    Returns {"ok": True, "chains": [...], "joins": [...]} or a refusal
    {"ok": False, "reason_code": ...}: an explicit scene change that does not sit
    on a blueprint story beat or music cue is refused (SPEC A5.2a item 2), and so
    is a timeline whose segments run backwards or overlap.
    """
    if not segments:
        return _fail("AGNES_NO_SEGMENTS")
    beats = _beats(blueprint)
    prev_end = None
    for seg in segments:
        if _seg_end(seg) < _seg_start(seg) or (prev_end is not None
                                               and _seg_start(seg) < prev_end - 1e-6):
            return _fail("AGNES_SEGMENTS_NOT_MONOTONIC",
                         segment_id=seg.get("segment_id"))
        prev_end = _seg_end(seg)

    chains, joins = [], []
    for i, seg in enumerate(segments):
        start = _seg_start(seg)
        scene = seg.get("scene") or _scene_at(beats, start)[0]
        starts_chain = not chains or scene != chains[-1]["scene"]
        if starts_chain and chains:
            if _boundary_at(beats, start) is None and seg.get("scene"):
                # an explicit scene change off every beat and music cue
                return _fail("AGNES_SCENE_CHANGE_OFF_BEAT",
                             segment_id=seg.get("segment_id"), at_s=start)
            joins.append({
                "at_s": _seg_end(segments[i - 1]),
                "scene_change": True,
                "xfade_s": XFADE_SCENE_S,
                "transition": SCENE_TRANSITION,
                "from_scene": chains[-1]["scene"], "to_scene": scene,
            })
        elif chains:
            joins.append({
                "at_s": _seg_end(segments[i - 1]),
                "scene_change": False,
                "xfade_s": XFADE_INTRA_S,
                "transition": INTRA_TRANSITION,
                "from_scene": scene, "to_scene": scene,
            })
        if starts_chain:
            chains.append({
                "chain_id": "chain%d" % (len(chains) + 1),
                "scene": scene,
                "start_s": start,
                "end_s": _seg_end(seg),
                "segments": [seg],
            })
        else:
            chains[-1]["segments"].append(seg)
            chains[-1]["end_s"] = _seg_end(seg)
    return {"ok": True, "chains": chains, "joins": joins}


# --- 2. submit_order ---------------------------------------------------------

def submit_order(chains, runner, max_chains=MAX_CHAINS_IN_FLIGHT):
    """Run the chains: up to max_chains in parallel, one chain's segments in order.

    runner(segment) -> whatever the caller wants back for that segment (the Agnes
    submit/poll call is the caller's; this module never makes one). Returns one row
    per chain, in chain order. A chain that raises is reported after the other
    in-flight chains have finished, never swallowed.
    """
    if max_chains < 1:
        raise ValueError("max_chains must be >= 1")
    if not chains:
        return []
    rows, errors = [None] * len(chains), []

    def _work(idx, chain):
        done = []
        try:
            for seg in chain["segments"]:
                done.append(runner(seg))
        except Exception as exc:                        # noqa: BLE001
            errors.append((chain.get("chain_id"), exc))
            return
        rows[idx] = {"chain_id": chain.get("chain_id"),
                     "scene": chain.get("scene"), "segments": done}

    workers = min(int(max_chains), len(chains))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_work, i, c) for i, c in enumerate(chains)]
        for f in futures:
            f.result()
    if errors:
        chain_id, exc = errors[0]
        raise RuntimeError("AGNES_CHAIN_FAILED: %s: %r" % (chain_id, exc)) from exc
    return rows


# --- 3. last_frame -----------------------------------------------------------

def clip_duration(path, ffprobe="ffprobe"):
    """Duration of one clip in seconds (ffprobe JSON-free plain read)."""
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=nw=1:nk=1", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError("AGNES_CLIP_UNREADABLE: %s: %r" % (path, exc)) from exc


def last_frame(clip, out_png, runner=None, fps=DEFAULT_FPS, probe=None):
    """Extract the LAST frame of clip as a PNG (the next segment's first_frame).

    One frame before the end at the clip's own frame rate, so the frame is the
    clip's own last one and not a black tail frame. Returns out_png.
    """
    dur = (probe or clip_duration)(clip)
    start = max(0.0, float(dur) - 1.0 / float(fps))
    argv = ["ffmpeg", "-y", "-ss", "%.3f" % start, "-i", str(clip),
            "-frames:v", "1", "-update", "1", str(out_png)]
    (runner or _run_argv)(argv)
    return out_png


def _run_argv(argv, timeout=None):
    try:
        subprocess.run(argv, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError("FFMPEG_UNAVAILABLE: %s" % (argv[0],)) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("FFMPEG_FAILED: %s: %s" % (exc.cmd[0],
                           (exc.stderr or b"")[-400:].decode("utf-8", "replace"))) from exc


# --- 4. join_argv ------------------------------------------------------------

def _clip_src_dur(clip):
    """(src, dur|None) for a path string or a {"src","dur"} record."""
    if isinstance(clip, dict):
        return clip["src"], clip.get("dur")
    return clip, None


def _join_spec(style, xfade_s):
    """Normalise one join's style into (xfade_s, transition, scene_change)."""
    if style is None:
        return xfade_s, (INTRA_TRANSITION if xfade_s <= XFADE_INTRA_S else SCENE_TRANSITION), \
            xfade_s > XFADE_INTRA_S
    if isinstance(style, (int, float)):
        xfade_s = float(style)
        return xfade_s, (INTRA_TRANSITION if xfade_s <= XFADE_INTRA_S else SCENE_TRANSITION), \
            xfade_s > XFADE_INTRA_S
    if isinstance(style, str):
        style = {"transition": style}
    dur = float(style.get("xfade_s", xfade_s))
    trans = style.get("transition") or (SCENE_TRANSITION if style.get("scene_change")
                                        else INTRA_TRANSITION)
    return dur, trans, bool(style.get("scene_change"))


def join_argv(clips, xfade_s=XFADE_SCENE_S, styles=None, song=None,
              size=DEFAULT_SIZE, fps=DEFAULT_FPS, output="joined.mp4",
              ffmpeg="ffmpeg", probe=None):
    """FFmpeg argv (an argument array, never a shell string) joining the clips.

    clips : paths or {"src": path, "dur": seconds} records, in timeline order.
            A record that carries "dur" is not probed; anything else is.
    styles: one entry per join (len(clips) - 1) - the "joins" chain_plan returned,
            or a transition name / a number. Nothing means the caller's xfade_s.
    song  : the one audio track. Every Agnes input is dropped with `-an` so no
            clip's own sound survives, and the song is the single audio map.

    Joins consume their crossfade: the output is shorter than the sum of the
    inputs by exactly one overlap per join, which is what lipsync_offsets shifts
    the lip-sync windows by.
    """
    if not clips:
        raise ValueError("join_argv needs at least one clip")
    if styles is not None and len(styles) != len(clips) - 1:
        raise ValueError("styles needs one entry per join (%d joins, %d given)"
                         % (len(clips) - 1, len(styles)))
    if len(clips) > 1 and xfade_s < 0:
        raise ValueError("xfade_s must be >= 0")
    w, h = size
    filt = _VSF.cover_crop_filter(w, h)
    srcs, durs = [], []
    for clip in clips:
        src, dur = _clip_src_dur(clip)
        srcs.append(str(src))
        durs.append(None if dur is None else float(dur))

    cmd = [ffmpeg, "-y"]
    for i, src in enumerate(srcs):
        # `-an` immediately BEFORE each Agnes `-i`: ffmpeg reads it as an option
        # of the input that follows, so that clip's own audio track is never
        # decoded or mapped (SPEC A5.2a item 4 - every clip's sound is stripped).
        # After an `-i` it would belong to the NEXT input, which would mute the
        # song - verified: "Cannot decode a disabled input stream".
        cmd += ["-an", "-i", src]
    song_idx = None
    if song is not None:
        song_idx = len(srcs)
        cmd += ["-i", str(song)]

    fc = []
    for i in range(len(srcs)):
        step = "fps=%d,%s,settb=1/%d" % (int(fps), filt, int(fps))
        if durs[i] is not None:
            step = "trim=duration=%.6f,setpts=PTS-STARTPTS,%s" % (durs[i], step)
        fc.append("[%d:v]%s[v%d]" % (i, step, i))

    probe_fn = probe or clip_duration
    pos = 0.0                                   # current output end, seconds
    if len(srcs) == 1:
        vlast = "[v0]"
        if durs[0] is not None:
            pos = durs[0]
    else:
        prev, i = "[v0]", 1
        pos = durs[0] if durs[0] is not None else probe_fn(srcs[0])
        while i < len(srcs):
            dur = durs[i] if durs[i] is not None else probe_fn(srcs[i])
            spec = _join_spec(None if styles is None else styles[i - 1], xfade_s)
            overlap, trans, _scene_change = spec
            if overlap > 0:
                offset = max(0.0, pos - overlap)
                fc.append("%s[v%d]xfade=transition=%s:duration=%.6f:offset=%.6f[x%d]"
                          % (prev, i, trans, overlap, offset, i))
                pos = offset + dur
            else:
                # a plain cut: no overlap, no lost frames
                fc.append("%s[v%d]concat=n=2:v=1:a=0[x%d]" % (prev, i, i))
                pos = pos + dur
            prev = "[x%d]" % (i,)
            i += 1
        fc.append("%snull[vout]" % (prev,))
        vlast = "[vout]"

    audio_map = []
    if song_idx is not None:
        # one audio map, and it is the song: trimmed/padded to the joined video
        # so the audio ends with the picture and never with a clip's own track.
        fc.append("[%d:a]atrim=duration=%.6f,apad=whole_dur=%.6f,"
                  "aresample=48000,aformat=channel_layouts=stereo[aout]"
                  % (song_idx, pos, pos))
        audio_map = ["-map", "[aout]"] + delivery_audio.AUDIO_OUT_ARGS \
            + delivery_audio.FASTSTART_ARGS
    else:
        audio_map = ["-an"]
    cmd += ["-filter_complex", ";".join(fc), "-map", vlast] + audio_map
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "%d" % int(fps),
            str(output)]
    return cmd


# --- 5. lipsync_offsets ------------------------------------------------------

def _join_at(join):
    return float(join.get("at_s", join)) if isinstance(join, dict) else float(join)


def _join_overlap(join, default):
    if not isinstance(join, dict):
        return float(default)
    return float(join.get("xfade_s", default))


def lipsync_offsets(windows, joins, xfade_s=XFADE_SCENE_S):
    """Shift every lip-sync window earlier by the crossfade overlaps before it.

    windows: [{"line_id", "start_s", "end_s"}] (or (start, end) pairs) in SONG
    time - the timeline the join compresses, since each crossfade eats one overlap
    of picture. joins: the chain_plan joins (a join carries its own "xfade_s"; a
    bare number takes `xfade_s`). Returns the same shape, each row shifted and
    carrying "shift_s".
    """
    out = []
    for win in windows:
        if isinstance(win, dict):
            start, end, keep = float(win["start_s"]), float(win["end_s"]), dict(win)
        else:
            start, end, keep = float(win[0]), float(win[1]), {}
        shift = sum(_join_overlap(j, xfade_s) for j in joins
                    if _join_at(j) <= start + 1e-9)
        keep.update({"start_s": start - shift, "end_s": end - shift,
                     "shift_s": shift})
        out.append(keep)
    return out


# --- 6. check_joins ----------------------------------------------------------

def _sample_window(path, start_s, dur_s, ffmpeg="ffmpeg"):
    """Raw grey frames (32x32, one byte per pixel) + s16le mono audio over a window.

    Injected in tests; the real one only shells to ffmpeg with argument arrays.
    """
    size = JOIN_SAMPLE_W * JOIN_SAMPLE_W
    vcmd = [ffmpeg, "-v", "error", "-ss", "%.3f" % start_s, "-t", "%.3f" % dur_s,
            "-i", str(path), "-an", "-vf", "scale=%d:%d,format=gray"
            % (JOIN_SAMPLE_W, JOIN_SAMPLE_W), "-f", "rawvideo", "-"]
    acmd = [ffmpeg, "-v", "error", "-ss", "%.3f" % start_s, "-t", "%.3f" % dur_s,
            "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]

    def _out(cmd):
        try:
            return subprocess.run(cmd, check=True, capture_output=True).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("JOIN_SAMPLE_FAILED: %s: %r" % (cmd[0], exc)) from exc

    video = _out(vcmd)
    return {"video": video[:len(video) // size * size], "audio": _out(acmd)}


def _means(video):
    size = JOIN_SAMPLE_W * JOIN_SAMPLE_W
    return [sum(video[i:i + size]) / float(size)
            for i in range(0, len(video), size)]


def _db(audio):
    if len(audio) < 4:
        return None
    samples = array.array("h")
    samples.frombytes(audio[:len(audio) // 2 * 2])
    if not samples:
        return None
    rms = math.sqrt(sum(float(s) * s for s in samples) / len(samples))
    if rms <= 0.0:
        return -120.0
    return 20.0 * math.log10(rms / 32768.0)


def check_joins(final, joins, probe=None, black_luma=BLACK_LUMA,
                jump_limit=JOIN_JUMP_LIMIT, audio_floor_db=AUDIO_FLOOR_DB):
    """Per-join evidence on the delivered file: black frame, jump, audio, in order.

    final : the joined MP4.
    joins : the chain_plan joins (a join carries "at_s" in the SOURCE timeline and
            its "xfade_s"; a bare number takes the 0.4 s default).

    Returns {"ok": bool, "joins": [{"join", "at_s", "ok", "reasons", ...}]}.
    Reason codes: JOIN_BLACK_FRAME (a sampled frame is black), JOIN_JUMP (an
    intra-scene join jumps harder than the cut threshold), JOIN_AUDIO_GAP (no or
    too little audio over the join), JOIN_AUDIO_SILENT (the song stops there).
    A scene change is allowed to jump - it is motivated - and is only held to the
    black-frame and audio checks.
    """
    probe_fn = probe or _sample_window
    rows = []
    for i, join in enumerate(joins):
        at = _join_at(join)
        overlap = _join_overlap(join, XFADE_SCENE_S)
        scene_change = bool(join.get("scene_change")) if isinstance(join, dict) else False
        dur = max(2.0 * overlap, JOIN_MIN_SAMPLE_S)
        sample = probe_fn(final, max(0.0, at - dur / 2.0), dur)
        frames, audio = _means(sample.get("video", b"")), sample.get("audio", b"")
        reasons, stats = [], {"min_luma": None, "jump_max": None, "audio_db": None}
        if not frames:
            reasons.append("JOIN_NO_FRAMES")
        else:
            stats["min_luma"] = min(frames)
            if stats["min_luma"] < black_luma:
                reasons.append("JOIN_BLACK_FRAME")
            if len(frames) > 1:
                diffs = [abs(frames[k + 1] - frames[k]) / 255.0
                         for k in range(len(frames) - 1)]
                stats["jump_max"] = max(diffs)
                if not scene_change and stats["jump_max"] > jump_limit:
                    reasons.append("JOIN_JUMP")
        db = _db(audio)
        stats["audio_db"] = db
        if db is None or len(audio) < 800:              # 0.1 s at 8 kHz
            reasons.append("JOIN_AUDIO_GAP")
        elif db < audio_floor_db:
            reasons.append("JOIN_AUDIO_SILENT")
        rows.append(dict({"join": i, "at_s": at, "xfade_s": overlap,
                          "scene_change": scene_change, "ok": not reasons,
                          "reasons": reasons}, **stats))
    return {"ok": all(r["ok"] for r in rows), "joins": rows}
