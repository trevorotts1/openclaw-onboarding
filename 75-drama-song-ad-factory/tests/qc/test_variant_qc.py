#!/usr/bin/env python3
"""V2-W2-R-U1 tests: per-variant QC + creative-fidelity + lyric sign-off
(Plan 9.3, 9.4). stdlib only.

Green fixtures must PASS, red fixtures must FAIL with their named code.
The headline rule (Plan 9.4, the W4-07 lesson): a media stage cannot pass
without a real media file inspected by a checker, and no variant's verdict
can carry another variant.

Run (exit 0 only when every fixture behaves as named):
  python3 75-drama-song-ad-factory/tests/qc/test_variant_qc.py  # in-repo
  python3 tests/qc/test_variant_qc.py                           # in-lane

DSAF_QC_CORE pins one core directory and disables the search path, so a
run can be proved against a single tree with no fallback.
"""
import os
import struct
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # lane/, or skill 75-.../

def _core_paths():
    """Core dirs on sys.path, first match wins.

    DSAF_QC_CORE is an os.pathsep list and is EXCLUSIVE: every entry must
    hold qc_gate.py, and nothing is appended, so a pinned run proves one
    tree with no fallback. Without it the layout is derived from this
    file's own location (no absolute machine paths in the repo), plus
    $DRAMA_SONG_BUILD_ROOT/core when the caller exports it.
    """
    pinned = os.environ.get("DSAF_QC_CORE")
    if pinned:
        paths = [p for p in pinned.split(os.pathsep) if p]
        if not paths:
            raise SystemExit("DSAF_QC_CORE is set but empty")
        for p in paths:
            if not os.path.isfile(os.path.join(p, "qc_gate.py")):
                raise SystemExit("DSAF_QC_CORE entry has no qc_gate.py: %s" % p)
        return paths
    build = os.environ.get("DRAMA_SONG_BUILD_ROOT")
    cands = [os.path.join(ROOT, "core"),
             os.path.join(ROOT, "scripts", "core"),
             os.path.join(ROOT, "75-drama-song-ad-factory", "scripts", "core"),
             os.path.join(build, "core") if build else None]
    paths = [p for p in cands if p and os.path.isdir(p)]
    if not any(os.path.isfile(os.path.join(p, "qc_gate.py")) for p in paths):
        raise SystemExit(
            "no core dir holding qc_gate.py; tried %r -- set DSAF_QC_CORE "
            "or DRAMA_SONG_BUILD_ROOT" % (cands,))
    return paths

sys.path[:0] = _core_paths()

import qc  # noqa: E402
from qc import (  # noqa: E402
    check_creative, check_media, check_signoff, evaluate_variant,
    evaluate_variants, lyrics_digest, sniff_container, stage_for,
    variant_key,
)
from qc.media_gate import probe_duration  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if not cond else ""))
    if not cond:
        FAILS.append(name)
        # Raise so the pytest runner reports red instead of collecting a
        # green run: a printed FAIL with no assertion is a false pass.
        raise AssertionError("FAILED: %s%s"
                             % (name, (" (%s)" % detail) if detail else ""))


def codes(res):
    return {f["code"] for f in res["failures"]}


# ---------------------------------------------------------------- media
TMP = tempfile.mkdtemp(prefix="TrevelynsMini2-V2-W2-R-U1-media-")


def write_wav(path, seconds, rate=8000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


def write_mp4(path, seconds, timescale=1000, mvhd_first=True):
    ftyp = struct.pack(">I", 16) + b"ftyp" + b"isom" + struct.pack(">I", 0)
    mvhd = (b"mvhd" + bytes(4) + struct.pack(">III", 0, 0, timescale)
            + struct.pack(">I", int(timescale * seconds)))
    if mvhd_first:
        payload = mvhd
    else:  # mvhd nested after a free box
        free_body = b"\x00" * 8
        payload = (struct.pack(">I", 8 + len(free_body)) + b"free"
                   + free_body + mvhd)
    moov = struct.pack(">I", 8 + len(payload)) + b"moov" + payload
    with open(path, "wb") as f:
        f.write(ftyp + moov)
    return path


def write_png(path):
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return path


WAV_OK = write_wav(os.path.join(TMP, "song_ok.wav"), 2.0)
WAV_WRONG_LEN = write_wav(os.path.join(TMP, "song_short.wav"), 1.0)
MP4_OK = write_mp4(os.path.join(TMP, "video_ok.mp4"), 6.0)
MP4_MVHD_LATE = write_mp4(os.path.join(TMP, "video_late.mp4"), 6.0,
                           mvhd_first=False)
PNG_OK = write_png(os.path.join(TMP, "frame.png"))
EMPTY = os.path.join(TMP, "empty.mp4")
open(EMPTY, "wb").close()
MISSING = os.path.join(TMP, "does_not_exist.mp4")

REVIEWER = {"identity": "qc-bob", "session": "sess-1", "authority": "dept-qc"}


def audio_spec(path, target, **kw):
    base = {"kind": "audio", "path": path, "target_seconds": target,
            "tolerance_seconds": 1.0, "reviewer": dict(REVIEWER),
            "inspection": {"listening": {"method": "headphones, full listen",
                                         "listened_seconds": target}}}
    base.update(kw)
    return base


def video_spec(path, target, **kw):
    base = {"kind": "video", "path": path, "target_seconds": target,
            "tolerance_seconds": 1.0, "reviewer": dict(REVIEWER),
            "inspection": {"frames": ["f000", "f015", "f030"]}}
    base.update(kw)
    return base


def image_spec(path, **kw):
    base = {"kind": "image", "path": path, "reviewer": dict(REVIEWER),
            "inspection": {"frames": ["frame.png"]}}
    base.update(kw)
    return base


class TestMediaGate:
    def test_green_real_media_pass(self):
        a = check_media(audio_spec(WAV_OK, 2.0), kind_hint="audio")
        check("green: real wav with listening passes",
              a["verdict"] == "PASS" and a["duration_seconds"] == 2.0,
              repr(a))
        v = check_media(video_spec(MP4_OK, 6.0), kind_hint="video")
        check("green: real mp4 with frames passes",
              v["verdict"] == "PASS" and v["duration_seconds"] == 6.0,
              repr(v))
        v2 = check_media(video_spec(MP4_MVHD_LATE, 6.0), kind_hint="video")
        check("green: mvhd not first child still probes",
              v2["verdict"] == "PASS", repr(v2))
        i = check_media(image_spec(PNG_OK), kind_hint="image")
        check("green: png with inspected frame passes", i["verdict"] == "PASS",
              repr(i))

    def test_red_no_media_file(self):
        r = check_media(audio_spec(MISSING, 2.0), kind_hint="audio")
        check("red: path does not exist FAILs",
              r["verdict"] == "FAIL" and "MEDIA_FILE_MISSING" in codes(r),
              repr(r))
        r = check_media(audio_spec(None, 2.0), kind_hint="audio")
        check("red: no path recorded FAILs",
              r["verdict"] == "FAIL" and "MEDIA_FILE_MISSING" in codes(r),
              repr(r))
        r = check_media(audio_spec(EMPTY, 2.0), kind_hint="audio")
        check("red: zero-byte file FAILs",
              r["verdict"] == "FAIL" and "MEDIA_FILE_EMPTY" in codes(r),
              repr(r))

    def test_red_duration(self):
        r = check_media(audio_spec(WAV_WRONG_LEN, 2.0,
                                   tolerance_seconds=0.5), kind_hint="audio")
        check("red: duration off target FAILs",
              r["verdict"] == "FAIL" and "MEDIA_DURATION_MISMATCH" in codes(r),
              repr(r))
        # boundary: delta exactly equal to the tolerance passes; only a
        # delta strictly larger than the tolerance fails (documented rule).
        r = check_media(audio_spec(WAV_WRONG_LEN, 2.0), kind_hint="audio")
        check("red: delta == tolerance is within tolerance",
              r["verdict"] == "PASS", repr(r))
        r = check_media(audio_spec(WAV_OK, 2.0, target_seconds=None),
                        kind_hint="audio")
        check("red: no target duration FAILs",
              r["verdict"] == "FAIL" and "MEDIA_NO_TARGET" in codes(r),
              repr(r))

    def test_red_format(self):
        r = check_media(video_spec(WAV_OK, 6.0), kind_hint="video")
        check("red: wav waved as video FAILs format",
              r["verdict"] == "FAIL" and "MEDIA_FORMAT_MISMATCH" in codes(r),
              repr(r))
        r = check_media(audio_spec(MP4_OK, 6.0), kind_hint="video")
        check("red: kind mismatch FAILs",
              r["verdict"] == "FAIL" and "MEDIA_KIND_MISMATCH" in codes(r),
              repr(r))

    def test_red_unprovable_is_not_pass(self):
        # valid ftyp header but no moov: duration unprovable -> UNAVAILABLE,
        # which never counts as PASS (17.8 / 9.4).
        broken = os.path.join(TMP, "header_only.mp4")
        open(broken, "wb").write(
            struct.pack(">I", 16) + b"ftyp" + b"isom" + struct.pack(">I", 0))
        r = check_media(video_spec(broken, 6.0), kind_hint="video")
        check("red: unprobeable duration is UNAVAILABLE not PASS",
              r["verdict"] == "UNAVAILABLE"
              and "MEDIA_DURATION_UNKNOWN" in codes(r), repr(r))
        check("red: unrecognised container never passes",
              check_media(video_spec(MISSING.replace("x", "y"), 6.0),
                          kind_hint="video")["verdict"] == "FAIL")
        junk = os.path.join(TMP, "junk.bin")
        open(junk, "wb").write(b"NOT-A-MEDIA-FILE" * 4)
        r = check_media(audio_spec(junk, 2.0), kind_hint="audio")
        check("red: junk bytes UNAVAILABLE (format undetermined)",
              r["verdict"] == "UNAVAILABLE"
              and "MEDIA_FORMAT_UNKNOWN" in codes(r), repr(r))

    def test_red_inspection_receipts(self):
        r = check_media(video_spec(MP4_OK, 6.0,
                                   inspection={"frames": ["only-one"]}),
                        kind_hint="video")
        check("red: fewer than 2 frames FAILs",
              r["verdict"] == "FAIL" and "MEDIA_NO_FRAMES" in codes(r),
              repr(r))
        r = check_media(audio_spec(WAV_OK, 2.0, inspection={}),
                        kind_hint="audio")
        check("red: no listening receipt FAILs",
              r["verdict"] == "FAIL" and "MEDIA_NO_LISTENING" in codes(r),
              repr(r))
        r = check_media(audio_spec(WAV_OK, 2.0, reviewer=None),
                        kind_hint="audio")
        check("red: no checker identity FAILs",
              r["verdict"] == "FAIL" and "MEDIA_NO_REVIEWER" in codes(r),
              repr(r))


# ------------------------------------------------------------ creative
from qc.creative_fidelity import check_creative  # noqa: E402
from story_arc import story_arc as _story_arc  # noqa: E402

# Canonical green/red arc fixtures live in core/story_arc/fixtures; reuse
# them instead of a second copy of the same stories.
STORY_OK = _story_arc.load_fixture("valid.json")
STORY_MISSING_MENTOR = _story_arc.load_fixture("missing-mentor.json")
STORY_EARLY = _story_arc.load_fixture("reveal-early.json")


def compiled_prompt(shot):
    # What style_bible_integration.compile_visual emits for the default
    # animated Resilia style: the mark the consumption gate requires.
    return ("[compiled:style=resilia-animated-01 model=gpt-image-2-5-sunburst "
            "aspect=9:16]\n[STYLE]\naesthetic: animated Resilia-like look\n"
            "[/STYLE]\n[CHARACTER_REFS] c1=asset1 [/CHARACTER_REFS]\n"
            "[PRODUCT_REFS] asset9 [/PRODUCT_REFS]\n"
            "[TEXT_ALLOWLIST] (none)\n"
            "[SHOT:%s] %s [/SHOT]" % (shot["shot_id"], shot["base_prompt"]))


STORY_OK = {"story_id": "green-arc", "beats": [
    "ordinary_world", "humiliation", "wound_deepens", "frozen",
    "seeing_it_too", "failed_solutions", "mentor", "product_intro",
    "doubt", "climb", "vindication", "return_cta"], "product_reveal": 8}


class TestCreativeGate:
    def test_green(self):
        shots = [{"shot_id": "s01", "base_prompt": "hero freezes"},
                 {"shot_id": "s02", "base_prompt": "mentor speaks"},
                 {"shot_id": "s08", "base_prompt": "bottle reveal"}]
        r = check_creative({"story": STORY_OK,
                            "visual_prompts": [compiled_prompt(s) for s in
                                               shots]})
        check("green: valid arc + compiled prompts PASS",
              r["verdict"] == "PASS", repr(r))

    def test_red_style_not_injected(self):
        r = check_creative({"story": STORY_OK,
                            "visual_prompts": ["hero freezes, hand typed",
                                               compiled_prompt({"shot_id": "s02",
                                                                "base_prompt": "x"})]})
        check("red: hand-typed prompt FAILs STYLE_NOT_INJECTED",
              r["verdict"] == "FAIL" and "STYLE_NOT_INJECTED" in codes(r),
              repr(r))
        r = check_creative({"story": STORY_OK, "visual_prompts": []})
        check("red: no prompts FAILs CREATIVE_NO_PROMPTS",
              r["verdict"] == "FAIL" and "CREATIVE_NO_PROMPTS" in codes(r),
              repr(r))

    def test_red_arc(self):
        prompt = compiled_prompt({"shot_id": "s01", "base_prompt": "x"})
        r = check_creative({"story": STORY_MISSING_MENTOR,
                            "visual_prompts": [prompt]})
        check("red: missing mentor FAILs CREATIVE_STORY_ARC",
              r["verdict"] == "FAIL" and "CREATIVE_STORY_ARC" in codes(r),
              repr(r))
        r = check_creative({"story": STORY_EARLY,
                            "visual_prompts": [prompt]})
        check("red: reveal before mentor FAILs",
              r["verdict"] == "FAIL" and "CREATIVE_STORY_ARC" in codes(r),
              repr(r))
        r = check_creative({"visual_prompts": [prompt]})
        check("red: no story FAILs CREATIVE_STORY_MISSING",
              r["verdict"] == "FAIL"
              and "CREATIVE_STORY_MISSING" in codes(r), repr(r))


# ------------------------------------------------------------ sign-off
LYRICS = [{"line_id": "l1", "text": "I was lost", "critical": True},
          {"line_id": "l2", "text": "Try the amber bottle", "critical": True}]
DIGEST = lyrics_digest(LYRICS)


class TestSignoffGate:
    def test_green(self):
        r = check_signoff({
            "status": "approved", "approved_at": "2026-10-07T12:00:00Z",
            "lyrics_digest": DIGEST,
            "approver": {"identity": "Trevor", "kind": "human"}},
            expected_digest=DIGEST,
            song_started_at="2026-10-07T13:00:00Z", maker="lyric-writer")
        check("green: recorded human approval PASSes", r["verdict"] == "PASS",
              repr(r))
        r = check_signoff({
            "status": "declined", "approved_at": "2026-10-07T12:00:00Z",
            "lyrics_digest": DIGEST,
            "approver": {"identity": "Trevor", "kind": "human"}},
            expected_digest=DIGEST)
        check("green: recorded decline unblocks (plan 4.0 optional step)",
              r["verdict"] == "PASS" and r["status"] == "declined",
              repr(r))

    def test_red(self):
        r = check_signoff(None, expected_digest=DIGEST)
        check("red: no sign-off FAILs (W4-07)",
              r["verdict"] == "FAIL"
              and "LYRIC_SIGNOFF_MISSING" in codes(r), repr(r))
        r = check_signoff({
            "status": "approved", "approved_at": "2026-10-07T12:00:00Z",
            "lyrics_digest": DIGEST,
            "approver": {"identity": "qc-bot", "kind": "model"}},
            expected_digest=DIGEST)
        check("red: model approver FAILs",
              r["verdict"] == "FAIL"
              and "LYRIC_SIGNOFF_NOT_HUMAN" in codes(r), repr(r))
        stale = lyrics_digest([{"line_id": "l1", "text": "changed words"}])
        r = check_signoff({
            "status": "approved", "approved_at": "2026-10-07T12:00:00Z",
            "lyrics_digest": stale,
            "approver": {"identity": "Trevor", "kind": "human"}},
            expected_digest=DIGEST)
        check("red: digest mismatch FAILs as stale",
              r["verdict"] == "FAIL"
              and "LYRIC_SIGNOFF_STALE" in codes(r), repr(r))
        r = check_signoff({
            "status": "approved", "approved_at": "2026-10-07T14:00:00Z",
            "lyrics_digest": DIGEST,
            "approver": {"identity": "Trevor", "kind": "human"}},
            expected_digest=DIGEST,
            song_started_at="2026-10-07T13:00:00Z")
        check("red: sign-off after song start FAILs",
              r["verdict"] == "FAIL"
              and "LYRIC_SIGNOFF_AFTER_SONG" in codes(r), repr(r))
        r = check_signoff({
            "status": "approved", "approved_at": "2026-10-07T12:00:00Z",
            "lyrics_digest": DIGEST,
            "approver": {"identity": "lyric-writer", "kind": "human"}},
            expected_digest=DIGEST, maker="lyric-writer")
        check("red: maker self-approval FAILs",
              r["verdict"] == "FAIL"
              and "LYRIC_SIGNOFF_NOT_INDEPENDENT" in codes(r), repr(r))


# -------------------------------------------------------- variant gates
def rec(cid, check_name, verdict="PASS", stage=None, run="run-qc-1",
        reviewer=None, summary="inspected real output"):
    return {"schema_version": "1.0.0", "check_id": cid, "run_id": run,
            "stage": stage or "@BOUND@", "check": check_name,
            "verdict": verdict, "evidence": {"summary": summary},
            "checker_version": "checker-1.0",
            "reviewer": dict(reviewer or REVIEWER)}


def bind(records, stage_key):
    return [dict(r, stage=stage_key) for r in records]


VIDEO_CHECKS = ["video", "creative"]
MAKERS = {"v1": "maker-video", "v2": "maker-video"}


def video_case(length_s, shape, with_media=True):
    key = variant_key(length_s, shape)
    bound = stage_for("video", key)
    case = {
        "records": bind([rec("v1", "video"), rec("v2", "creative")], bound),
        "makers": MAKERS,
        "required_checks": VIDEO_CHECKS,
        "creative": {"story": STORY_OK,
                     "visual_prompts": [compiled_prompt({"shot_id": "s01",
                                                         "base_prompt": "x"})]},
    }
    if with_media:
        case["media"] = video_spec(MP4_OK, 6.0)
    return case


def song_case(length_s, shape, with_media=True, with_signoff=True):
    key = variant_key(length_s, shape)
    bound = stage_for("song", key)
    case = {
        "records": bind([rec("s1", "song"), rec("s2", "lyrics"),
                         rec("s3", "audio")], bound),
        "makers": {"s1": "maker-song", "s2": "maker-song",
                   "s3": "maker-song"},
        "required_checks": ["song", "lyrics", "audio"],
        "approved_lyrics": LYRICS,
        "lyrics_maker": "lyric-writer",
        "song_started_at": "2026-10-07T13:00:00Z",
    }
    if with_media:
        case["media"] = audio_spec(WAV_OK, 2.0)
    if with_signoff:
        case["signoff"] = {"status": "approved",
                           "approved_at": "2026-10-07T12:00:00Z",
                           "lyrics_digest": DIGEST,
                           "approver": {"identity": "Trevor",
                                        "kind": "human"}}
    return case


class TestPerVariantQC:
    def test_green_full(self):
        res = evaluate_variant("run-qc-1", "video", 60, "9:16",
                               video_case(60, "9:16"))
        check("green: full video variant PASSes",
              res["gate"] == "PASS" and res["variant"] == "60s@9:16",
              repr(res["reason_codes"]))
        res = evaluate_variant("run-qc-1", "song", 60, "9:16",
                               song_case(60, "9:16"))
        check("green: full song variant PASSes (media + sign-off)",
              res["gate"] == "PASS", repr(res["reason_codes"]))

    def test_red_no_media_file_blocks_stage(self):
        # Plan 9.4 headline: records all PASS, but no media file -> FAIL.
        res = evaluate_variant("run-qc-1", "video", 60, "9:16",
                               video_case(60, "9:16", with_media=False))
        check("red: media stage without media file FAILs",
              res["gate"] == "FAIL" and "MEDIA_REQUIRED" in
              set(res["reason_codes"]), repr(res["reason_codes"]))
        res = evaluate_variant("run-qc-1", "video", 60, "9:16",
                               video_case(60, "9:16", with_media=False)
                               | {"media": video_spec(MISSING, 6.0)})
        check("red: media file missing on disk FAILs",
              res["gate"] == "FAIL" and "MEDIA_FILE_MISSING" in
              set(res["reason_codes"]), repr(res["reason_codes"]))
        res = evaluate_variant("run-qc-1", "video", 60, "9:16",
                               video_case(60, "9:16", with_media=False)
                               | {"media": video_spec(WAV_OK, 6.0)})
        check("red: wrong container FAILs",
              res["gate"] == "FAIL" and "MEDIA_FORMAT_MISMATCH" in
              set(res["reason_codes"]), repr(res["reason_codes"]))
        res = evaluate_variant("run-qc-1", "video", 60, "9:16",
                               video_case(60, "9:16", with_media=False)
                               | {"media": video_spec(MP4_OK, 6.0,
                                                      inspection={"frames": []})})
        check("red: video not frame-inspected FAILs",
              res["gate"] == "FAIL" and "MEDIA_NO_FRAMES" in
              set(res["reason_codes"]), repr(res["reason_codes"]))
        # unprovable duration: UNAVAILABLE -> still not PASS
        broken = os.path.join(TMP, "header_only.mp4")
        open(broken, "wb").write(
            struct.pack(">I", 16) + b"ftyp" + b"isom" + struct.pack(">I", 0))
        res = evaluate_variant("run-qc-1", "video", 60, "9:16",
                               video_case(60, "9:16", with_media=False)
                               | {"media": video_spec(broken, 6.0)})
        check("red: unprovable duration does not pass",
              res["gate"] == "FAIL"
              and "MEDIA_DURATION_UNKNOWN" in set(res["reason_codes"]),
              repr(res["reason_codes"]))

    def test_red_song_needs_signoff(self):
        res = evaluate_variant("run-qc-1", "song", 60, "9:16",
                               song_case(60, "9:16", with_signoff=False))
        check("red: song without lyric sign-off FAILs",
              res["gate"] == "FAIL" and "LYRIC_SIGNOFF_MISSING" in
              set(res["reason_codes"]), repr(res["reason_codes"]))
        stale = song_case(60, "9:16")
        stale["signoff"] = dict(stale["signoff"], lyrics_digest="deadbeef")
        res = evaluate_variant("run-qc-1", "song", 60, "9:16", stale)
        check("red: stale sign-off FAILs",
              res["gate"] == "FAIL" and "LYRIC_SIGNOFF_STALE" in
              set(res["reason_codes"]), repr(res["reason_codes"]))

    def test_red_creative_fidelity_enforced(self):
        case = video_case(60, "9:16")
        case["creative"] = {"story": STORY_OK,
                            "visual_prompts": ["hand typed prompt"]}
        res = evaluate_variant("run-qc-1", "video", 60, "9:16", case)
        check("red: uncompiled visual prompt FAILs gate",
              res["gate"] == "FAIL" and "STYLE_NOT_INJECTED" in
              set(res["reason_codes"]), repr(res["reason_codes"]))

    def test_red_records_stay_in_their_variant(self):
        # Records bound to 60s@9:16 offered to 90s@9:16 must not pass.
        # qc_gate reports STALE_BINDING as structural -> BLOCKED: same
        # records can never pass this variant, new ones are required.
        case60 = video_case(60, "9:16")
        case90 = video_case(90, "9:16")
        case90["records"] = case60["records"]  # try to cross variants
        res = evaluate_variant("run-qc-1", "video", 90, "9:16", case90)
        check("red: foreign variant records never PASS",
              res["gate"] == "BLOCKED" and "STALE_BINDING" in
              set(res["reason_codes"]), repr(res))

    def test_per_variant_separate_verdicts(self):
        cases = {"60s@9:16": video_case(60, "9:16"),
                 "90s@9:16": video_case(90, "9:16")}
        agg = evaluate_variants("run-qc-1", "video", cases,
                                required_variants=[(60, "9:16"),
                                                   (90, "9:16")])
        check("green: both variants pass their own gate",
              agg["gate"] == "PASS"
              and agg["passing_variants"] == ["60s@9:16", "90s@9:16"],
              repr(agg["failing_variants"]))
        # break only one variant: the other keeps its PASS
        cases["90s@9:16"] = video_case(90, "9:16", with_media=False)
        agg = evaluate_variants("run-qc-1", "video", cases,
                                required_variants=[(60, "9:16"),
                                                   (90, "9:16")])
        check("red: one broken variant fails the run",
              agg["gate"] == "FAIL"
              and agg["passing_variants"] == ["60s@9:16"]
              and agg["failing_variants"] == ["90s@9:16"],
              repr(agg))
        # a required variant nobody QC'd fails the run
        agg = evaluate_variants("run-qc-1", "video",
                                {"60s@9:16": video_case(60, "9:16")},
                                required_variants=[(60, "9:16"),
                                                   (180, "16:9")])
        check("red: un-QCed required variant FAILs as MISSING_VARIANT_QC",
              agg["gate"] == "FAIL"
              and "MISSING_VARIANT_QC" in agg["reason_codes"]
              and agg["failing_variants"] == ["180s@16:9"], repr(agg))

    def test_shape_length_validation(self):
        for bad in (61, "60", None, True, 3000):
            try:
                variant_key(bad, "9:16")
            except qc.VariantQCError:
                ok = True
            else:
                ok = False
            check("reject length %r" % (bad,), ok)
        try:
            variant_key(60, "4:3")
        except qc.VariantQCError:
            ok = True
        else:
            ok = False
        check("reject unknown shape", ok)


def main():
    suites = [TestMediaGate(), TestCreativeGate(),
              TestSignoffGate(), TestPerVariantQC()]
    tests = [(s, n) for s in suites for n in dir(s)
             if n.startswith("test_")]
    failed_tests = 0
    for suite, name in tests:
        # check() raises AssertionError on a red fixture; record the test
        # as failed and keep running so the log shows every red case.
        try:
            getattr(suite, name)()
        except AssertionError:
            failed_tests += 1
    ran = len(tests)
    print("%s test_variant_qc: %d passed, %d failed, %d total"
          % ("OK" if failed_tests == 0 else "FAIL",
             ran - failed_tests, failed_tests, ran))
    for f in FAILS:
        print(" - %s" % f)
    return 0 if failed_tests == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
