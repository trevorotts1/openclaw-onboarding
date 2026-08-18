#!/usr/bin/env python3
"""test_webinar_builder.py — Feature L2-G (webinar video creator) unit tests.

Covers the offline, deterministic surfaces of the webinar builder:

  1. TIMING DERIVATION (webinar_timing.py):
       * parse_slides splits the speech markdown into per-slide spoken text.
       * chunk_to_slide re-runs the EXACT chunk_text accumulation tagged per
         slide and matches the flat rechunk (fail-loud guard).
       * seconds_proportional_fallback is the documented deterministic fallback
         when the rechunk-count guard trips.
       * derive_timing produces contiguous 1..N entries whose total equals the
         real chunk durations; a chunk-count mismatch falls back loud.
       * list_chunk_files rejects a gap in chunk indices (a dropped chunk).

  2. FFMpeg COMMAND CONSTRUCTION (webinar_ffmpeg.py):
       * build_clip_filter emits the Ken Burns zoompan chain (and the static
         scale+crop variant), with the 6% push-in + center crop.
       * build_xfade_chain emits the exact xfade filtergraph with the documented
         offset formula offset_k = sum(dur_1..dur_k) - k*fade, and a passthrough
         for a single clip.
       * load_timing accepts BOTH the webinar_timing.py object schema and a bare
         list, and rejects non-contiguous / non-positive durations.
       * render_webinar's subprocess calls are mocked: the final mux command
         carries -map 0:v -map N:a -shortest and the -movflags +faststart flag.

  3. BUNDLE-GATE for webinar_mp4 (fix_bundle_complete.py):
       * webinar_mp4 is a REQUIRED deliverable named {deck_slug}-WEBINAR.mp4.
       * a bundle missing the webinar video FAILS and enumerates exactly
         webinar_mp4 as missing (never a false "done").
       * a full bundle including the webinar video PASSES and writes
         bundle_complete.json recording all ten deliverables.
       * the gate is fail-closed: a zero-byte WEBINAR.mp4 counts as missing.

NO network, NO ffmpeg render spend, NO GHL calls. The ffmpeg-side tests stub the
subprocess boundary so the command-shape assertions run in milliseconds.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import fix_bundle_complete as fbc  # noqa: E402
import webinar_ffmpeg as wf  # noqa: E402
import webinar_timing as wt  # noqa: E402


# ---------------------------------------------------------------------------
# 1) Timing derivation (webinar_timing.py)
# ---------------------------------------------------------------------------

_SAMPLE_SPEECH = """# Front matter
> how-to blockquote — dropped

# Title

## Slide 1
**Label only**

Hello world. This is sentence two.

## Slide 2
Second slide text here. Another sentence.

## Slide 3
Third slide.
"""


def test_parse_slides_splits_by_slide_header():
    slides = wt.parse_slides(_SAMPLE_SPEECH)
    nums = [n for n, _ in slides]
    assert nums == [1, 2, 3], f"expected slides 1..3, got {nums}"
    # front matter / headings / bold-only labels must be dropped.
    assert "Label only" not in slides[0][1]
    assert "Hello world" in slides[0][1]


def test_chunk_to_slide_tags_last_unit_slide():
    chunks = wt.chunk_to_slide(_SAMPLE_SPEECH, 280)
    assert chunks, "expected at least one chunk"
    for idx, slide, text in chunks:
        assert slide in (1, 2, 3), f"chunk {idx} tagged with slide {slide}"
    # The flat rechunk guard must not trip on the sample (same accumulation).
    flat = __import__("synthesize_full_speech").chunk_text(
        __import__("synthesize_full_speech").extract_spoken(_SAMPLE_SPEECH), 280)
    flat = [c for c in flat if c.strip()]
    assert len(flat) == len(chunks)


def test_chunk_to_slide_small_chunk_chars_produces_more_chunks():
    chunks_big = wt.chunk_to_slide(_SAMPLE_SPEECH, 280)
    chunks_small = wt.chunk_to_slide(_SAMPLE_SPEECH, 8)
    assert len(chunks_small) > len(chunks_big)


def test_seconds_proportional_fallback_scales_to_real_total():
    md = """## Slide 1
SECONDS: 30s
text

## Slide 2
SECONDS: 60s
more text
"""
    out = wt.seconds_proportional_fallback(md, [10.0, 20.0], 2)
    assert [r["slide"] for r in out] == [1, 2]
    assert sum(r["duration"] for r in out) == pytest.approx(30.0)
    assert out[0]["audio_start"] == 0.0
    assert out[0]["audio_end"] == pytest.approx(10.0)
    assert out[1]["audio_start"] == pytest.approx(10.0)
    assert out[1]["fallback_proportional"] is True


def test_seconds_proportional_fallback_requires_all_seconds():
    md = "## Slide 1\nSECONDS: 30s\ntext\n## Slide 2\nno seconds here\n"
    with pytest.raises(wt.TimingError):
        wt.seconds_proportional_fallback(md, [10.0, 20.0], 2)


def test_list_chunk_files_orders_and_rejects_gap():
    import os
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for n in ("chunk_000.mp3", "chunk_001.mp3", "chunk_002.mp3"):
            (d / n).write_bytes(b"x")
        paths = wt.list_chunk_files(str(d))
        assert [os.path.basename(p) for p in paths] == \
            ["chunk_000.mp3", "chunk_001.mp3", "chunk_002.mp3"]
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "chunk_000.mp3").write_bytes(b"x")
        (d / "chunk_002.mp3").write_bytes(b"x")  # gap at 001
        with pytest.raises(wt.TimingError, match="not contiguous"):
            wt.list_chunk_files(str(d))


_DERIVE_SPEECH = """# Front matter
> how-to blockquote — dropped

# Title

## Slide 1
Slide one has a fairly long single sentence that fills up some chunk room here.

## Slide 2
Slide two continues the presentation with its own longer spoken sentence block.

## Slide 3
Slide three wraps it all up with a final concluding spoken sentence right here.
"""


def test_derive_timing_primary_path_sums_real_chunk_durations(monkeypatch, tmp_path):
    speech = tmp_path / "PRESENTERS-SPEECH.md"
    speech.write_text(_DERIVE_SPEECH)
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    # chunk_chars=80 makes each slide its own chunk -> the primary path maps
    # chunk i -> slide i+1 exactly (verified above).
    for n in ("chunk_000.mp3", "chunk_001.mp3", "chunk_002.mp3"):
        (chunks / n).write_bytes(b"x")
    # Stub ffprobe so the test needs no real audio files.
    real_durations = iter([4.0, 6.0, 5.0])
    def _fake_ffprobe(path):
        return next(real_durations)
    monkeypatch.setattr(wt, "ffprobe_duration", _fake_ffprobe)

    result = wt.derive_timing(str(speech), str(chunks), chunk_chars=80,
                              audio_path="audio.mp3", deck_slug="demo")
    assert result["n_chunks"] == 3
    assert result["n_slides"] == 3
    assert result["fallback"] is None
    assert [t["slide"] for t in result["timing"]] == [1, 2, 3]
    assert [t["chunks"] for t in result["timing"]] == [[0], [1], [2]]
    assert sum(t["duration"] for t in result["timing"]) == pytest.approx(15.0)
    # The track is contiguous with non-decreasing audio_start.
    for i, t in enumerate(result["timing"]):
        assert t["audio_start"] == pytest.approx(sum(
            result["timing"][j]["duration"] for j in range(i)))
        assert t["duration"] > 0


def test_derive_timing_falls_back_when_chunk_count_mismatches(monkeypatch, tmp_path, capsys):
    # A speech WITH SECONDS: entries so the documented proportional fallback can
    # actually run when the rechunk-count guard trips.
    speech_md = """## Slide 1
SECONDS: 30s
Slide one is the opener.

## Slide 2
SECONDS: 60s
Slide two is the meat.
"""
    speech = tmp_path / "PRESENTERS-SPEECH.md"
    speech.write_text(speech_md)
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    # 4 on-disk chunks but the rechunk (both slides under 280 chars) = 1 -> guard trips.
    for n in ("chunk_000.mp3", "chunk_001.mp3", "chunk_002.mp3", "chunk_003.mp3"):
        (chunks / n).write_bytes(b"x")

    def _fake_ffprobe(path):
        return 2.0
    monkeypatch.setattr(wt, "ffprobe_duration", _fake_ffprobe)

    result = wt.derive_timing(str(speech), str(chunks), deck_slug="demo")
    assert result["fallback"] == "seconds_proportional"
    assert result["n_chunks"] == 4
    assert result["n_slides"] == 2
    assert [t["slide"] for t in result["timing"]] == [1, 2]
    # Proportional split: 30s/(30+60)=1/3 of the 8s real total -> 2.667s, 5.333s.
    assert result["timing"][0]["duration"] == pytest.approx(8.0 * 30.0 / 90.0)
    assert result["timing"][1]["duration"] == pytest.approx(8.0 * 60.0 / 90.0)
    assert capsys.readouterr().err  # the loud warning was emitted


def test_derive_timing_fails_loud_when_fallback_impossible(monkeypatch, tmp_path):
    # No SECONDS: entries -> the fallback cannot run -> derive_timing must RAISE
    # (never silently emit a wrong mapping).
    speech = tmp_path / "PRESENTERS-SPEECH.md"
    speech.write_text(_SAMPLE_SPEECH)  # rechunks to 1, no SECONDS: metadata
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    for n in ("chunk_000.mp3", "chunk_001.mp3", "chunk_002.mp3", "chunk_003.mp3"):
        (chunks / n).write_bytes(b"x")

    monkeypatch.setattr(wt, "ffprobe_duration", lambda p: 2.0)
    with pytest.raises(wt.TimingError, match="SECONDS"):
        wt.derive_timing(str(speech), str(chunks), deck_slug="demo")


def test_verify_timing_cross_checks_total(monkeypatch, tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"x")  # verify_timing requires the file to exist on disk
    result = {
        "timing": [
            {"slide": 1, "duration": 4.0},
            {"slide": 2, "duration": 6.0},
            {"slide": 3, "duration": 5.0},
        ]
    }
    monkeypatch.setattr(wt, "ffprobe_duration", lambda p: 15.0)
    verdict = wt.verify_timing(result, str(audio))
    assert "PASS" in verdict, verdict
    monkeypatch.setattr(wt, "ffprobe_duration", lambda p: 30.0)
    verdict_drift = wt.verify_timing(result, str(audio))
    assert "DRIFT" in verdict_drift, verdict_drift


def test_verify_timing_no_audio_is_best_effort():
    result = {"timing": [{"slide": 1, "duration": 4.0}]}
    verdict = wt.verify_timing(result, None)
    assert "timing total" in verdict and "no audio" in verdict


# ---------------------------------------------------------------------------
# 2) ffmpeg command construction (webinar_ffmpeg.py)
# ---------------------------------------------------------------------------

def test_build_clip_filter_kenburns_centers_and_zooms():
    f = wf.build_clip_filter(4.0, 30, "kenburns")
    assert "scale=1920:1080:force_original_aspect_ratio=increase" in f
    assert "crop=1920:1080" in f
    # 4s at 30fps = 120 frames; the push-in goes 1 -> 1.06.
    assert "1+(1.06-1)*on/120" in f
    assert "d=120" in f
    assert "fps=30" in f


def test_build_clip_filter_static_is_scale_crop_only():
    f = wf.build_clip_filter(4.0, 30, "static")
    assert "zoompan" not in f
    assert "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080" in f


def test_build_xfade_chain_offsets_follow_documented_formula():
    clips = ["c0.mp4", "c1.mp4", "c2.mp4"]
    durs = [4.0, 3.0, 5.0]
    fg, inputs, label = wf.build_xfade_chain(clips, durs, 0.5)
    assert fg == (
        "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=3.500000[v0];"
        "[v0][2:v]xfade=transition=fade:duration=0.5:offset=6.000000[v1]"
    ), fg
    assert inputs == ["-i", "c0.mp4", "-i", "c1.mp4", "-i", "c2.mp4"]
    assert label == "[v1]"


def test_build_xfade_chain_single_clip_is_passthrough():
    fg, inputs, label = wf.build_xfade_chain(["c0.mp4"], [4.0], 0.5)
    assert fg is None
    assert inputs == ["-i", "c0.mp4"]
    assert label == "0:v"


def test_build_xfade_chain_count_mismatch_raises():
    with pytest.raises(wf.WebinarError):
        wf.build_xfade_chain(["c0.mp4", "c1.mp4"], [4.0], 0.5)


def test_load_timing_accepts_object_and_bare_list(tmp_path):
    obj = {"timing": [
        {"slide": 1, "duration": 4.0, "audio_start": 0.0, "audio_end": 4.0},
        {"slide": 2, "duration": 6.0},
    ]}
    p1 = tmp_path / "obj.json"
    p1.write_text(json.dumps(obj))
    segs = wf.load_timing(str(p1))
    assert [s["slide"] for s in segs] == [1, 2]
    assert segs[0]["duration"] == 4.0

    bare = [{"slide": 1, "duration": 5.0}, {"slide": 2, "duration": 7.0}]
    p2 = tmp_path / "bare.json"
    p2.write_text(json.dumps(bare))
    segs2 = wf.load_timing(str(p2))
    assert [s["duration"] for s in segs2] == [5.0, 7.0]


def test_load_timing_rejects_gap_and_non_positive_duration(tmp_path):
    gap = [{"slide": 1, "duration": 4.0}, {"slide": 3, "duration": 5.0}]
    p = tmp_path / "gap.json"
    p.write_text(json.dumps(gap))
    with pytest.raises(wf.WebinarError, match="contiguous"):
        wf.load_timing(str(p))

    zero = [{"slide": 1, "duration": 0.0}]
    p2 = tmp_path / "zero.json"
    p2.write_text(json.dumps(zero))
    with pytest.raises(wf.WebinarError, match="duration"):
        wf.load_timing(str(p2))


def test_render_webinar_final_mux_command_shape(monkeypatch, tmp_path):
    """The final mux must carry -map 0:v -map N:a -shortest + faststart, and the
    whole pipeline must run with NO real ffmpeg (subprocess is stubbed)."""
    slides = tmp_path / "renders"
    slides.mkdir()
    (slides / "slide-01.png").write_bytes(b"x" * 128)
    (slides / "slide-02.png").write_bytes(b"x" * 128)
    timing = tmp_path / "webinar_timing.json"
    timing.write_text(json.dumps({"timing": [
        {"slide": 1, "duration": 2.0}, {"slide": 2, "duration": 3.0}]}))
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"x" * 128)
    out = tmp_path / "out" / "demo-WEBINAR.mp4"

    calls = []
    fake_results = {
        ("ffmpeg", "-y", "-v", "error"): lambda cmd: (
            type("CP", (), {"returncode": 0, "stdout": "", "stderr": ""})()),
    }

    class _CP:
        def __init__(self, rc=0, stdout="", stderr=""):
            self.returncode, self.stdout, self.stderr = rc, stdout, stderr

    def fake_run(cmd, timeout=600):
        calls.append(list(cmd))
        joined = " ".join(cmd)
        if cmd[0] == "ffmpeg" and "-filter_complex" not in joined:
            # Per-slide clip render succeeds.
            return _CP()
        if cmd[0] == "ffmpeg" and "-filter_complex" in joined:
            # Final mux succeeds; it is the command shape we assert.
            return _CP()
        if cmd[0] == "ffprobe":
            # The output-verification probe asks for -of json FIRST (it also carries
            # stream=... and format=duration,size, so it must be matched before the
            # plain duration branch below).
            if "-of" in joined and "json" in joined:
                return _CP(stdout=json.dumps({
                    "streams": [
                        {"codec_type": "video", "codec_name": "h264",
                         "width": 1920, "height": 1080},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                    "format": {"duration": "5.0", "size": "4096"},
                }))
            # resolve_slides probes dimensions.
            if "-show_entries" in joined and "stream=width,height" in joined:
                return _CP(stdout="2048,1152")
            # Per-clip / audio duration probes (plain csv).
            if "-show_entries" in joined and "format=duration" in joined:
                return _CP(stdout="2.0\n")
        return _CP()

    monkeypatch.setattr(wf, "run", fake_run)
    monkeypatch.setattr(wf.subprocess, "run", fake_run)

    probe = wf.render_webinar(str(slides), str(timing), str(audio), str(out),
                              fps=30.0, fade=0.5, crf=22, preset="veryfast",
                              bitrate="192k", motion_static=[], keep_clips=False,
                              workdir=None, verbose=False)

    mux_cmd = next(c for c in calls
                   if c[0] == "ffmpeg" and "-filter_complex" in c)
    assert "-filter_complex" in mux_cmd
    assert "-shortest" in mux_cmd
    assert "-movflags" in mux_cmd and "+faststart" in mux_cmd
    # The xfade filtergraph merges the clip inputs; the final video label [v0] is
    # what -map references (NOT a bare 0:v — the clips are the filter inputs).
    assert "-map" in mux_cmd and "[v0]" in mux_cmd
    # The audio is sliced with atrim inside the filtergraph and mapped as [aout].
    assert "-map" in mux_cmd and "[aout]" in mux_cmd
    assert any("atrim" in a for a in mux_cmd)
    assert mux_cmd.count("-i") == 3  # 2 clips + 1 audio
    assert "-pix_fmt" in mux_cmd and "yuv420p" in mux_cmd
    assert probe["has_video"] is True and probe["has_audio"] is True
    assert probe["width"] == 1920 and probe["height"] == 1080


# ---------------------------------------------------------------------------
# 3) Bundle-gate for webinar_mp4 (fix_bundle_complete.py)
# ---------------------------------------------------------------------------

def test_webinar_mp4_is_a_required_deliverable():
    keys = fbc.REQUIRED_KEYS
    assert "webinar_mp4" in keys, (
        "webinar_mp4 must be a REQUIRED deliverable — a build without the webinar "
        "video can never be reported done (L2-G)")
    spec = next(d for d in fbc.REQUIRED_DELIVERABLES if d["key"] == "webinar_mp4")
    assert spec["filename"] == "{deck_slug}-WEBINAR.mp4"


def test_bundle_without_webinar_mp4_fails_and_enumerates_it(tmp_path):
    base = tmp_path / "no-webinar"
    base.mkdir(parents=True)
    # Everything except the webinar video.
    for spec in fbc.REQUIRED_DELIVERABLES:
        if spec["key"] == "webinar_mp4":
            continue
        (base / fbc._expand_filename(spec["filename"], "deck")).write_bytes(b"x" * 2048)

    missing = fbc.check_bundle_complete(base, deck_slug="deck")
    assert "webinar_mp4" in missing, (
        f"a bundle missing the webinar video must report webinar_mp4 missing; got {missing}")
    ok, missing_run, gate = fbc.run_bundle_gate(base, deck_slug="deck")
    assert ok is False
    assert "webinar_mp4" in missing_run
    assert gate is None, "no bundle_complete.json may be written when the webinar is missing"


def test_full_bundle_including_webinar_mp4_passes(tmp_path):
    base = tmp_path / "full"
    base.mkdir(parents=True)
    for spec in fbc.REQUIRED_DELIVERABLES:
        (base / fbc._expand_filename(spec["filename"], "deck")).write_bytes(b"x" * 2048)

    ok, missing, gate = fbc.run_bundle_gate(base, deck_slug="deck")
    assert ok is True, f"full 10-deliverable bundle must pass; got missing={sorted(missing)}"
    assert gate is not None and gate.is_file()
    rec = json.loads(gate.read_text())
    assert rec["complete"] is True
    assert rec["deliverable_count"] == len(fbc.REQUIRED_KEYS) == 10
    assert "webinar_mp4" in rec["deliverables"]
    assert rec["deliverables"]["webinar_mp4"] == "deck-WEBINAR.mp4"


def test_zero_byte_webinar_mp4_counts_as_missing(tmp_path):
    base = tmp_path / "zero-webinar"
    base.mkdir(parents=True)
    for spec in fbc.REQUIRED_DELIVERABLES:
        (base / fbc._expand_filename(spec["filename"], "deck")).write_bytes(b"x" * 2048)
    (base / "deck-WEBINAR.mp4").write_bytes(b"")  # zero-byte -> NOT done

    missing = fbc.check_bundle_complete(base, deck_slug="deck")
    assert "webinar_mp4" in missing, (
        "a zero-byte WEBINAR.mp4 must count as missing (fail-closed: non-empty is required)")


def test_webinar_mp4_deck_slug_templating(tmp_path):
    base = tmp_path / "slug"
    base.mkdir(parents=True)
    for spec in fbc.REQUIRED_DELIVERABLES:
        (base / fbc._expand_filename(spec["filename"], "acme-q1")).write_bytes(b"x" * 2048)
    ok, missing, gate = fbc.run_bundle_gate(base, deck_slug="acme-q1")
    assert ok is True, f"slugged full bundle must pass; got missing={sorted(missing)}"
    rec = json.loads(gate.read_text())
    assert rec["deliverables"]["webinar_mp4"] == "acme-q1-WEBINAR.mp4"


def test_manifest_lockstep_includes_webinar_mp4():
    """PIPELINE-MANIFEST.build_bundle_files must include webinar_mp4 — the bundle
    gate's REQUIRED_KEYS and the manifest must never drift apart."""
    manifest_path = _resolve_manifest_path()
    assert manifest_path is not None, "PIPELINE-MANIFEST.json not found"
    man = json.loads(manifest_path.read_text())
    assert "webinar_mp4" in man.get("build_bundle_files", []), (
        "PIPELINE-MANIFEST.build_bundle_files must include webinar_mp4 (L2-G)")
    # AF-WEBINAR-SIZE must be a registered autofail code.
    codes = {a["code"] for a in man.get("autofails", [])}
    assert "AF-WEBINAR-SIZE" in codes, (
        "AF-WEBINAR-SIZE must be registered in PIPELINE-MANIFEST.autofails")


def _resolve_manifest_path():
    """Deployed layout first (scripts/../sops/PIPELINE-MANIFEST.json), repo
    walk-up fallback (universal-sops/presentation-slide-craft/) — mirrors
    manifest_source.resolve_manifest's installed-then-cluster tiering."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


# ---------------------------------------------------------------------------
# 4) Runner produces_artifact {deck_slug} expansion (attestation path)
# ---------------------------------------------------------------------------

def test_runner_expands_deck_slug_in_artifact_present(tmp_path):
    """The runner's _artifact_present must expand '{deck_slug}' in a produces_artifact
    spec to the run's deck slug, or a P9.6-WEBINAR-VIDEO / P8.25-WORKBOOK phase could
    never attest (the raw '{deck_slug}-WEBINAR.mp4' string never matches on disk)."""
    import run_signature_deck as rsd
    rd = tmp_path / "run"
    (rd / "working" / "delivery").mkdir(parents=True)
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"deck_slug": "demo"}))
    (rd / "working" / "delivery" / "demo-WEBINAR.mp4").write_bytes(b"x" * 100)

    # Raw templated spec must now resolve to the actual deck-slugged file.
    assert rsd._artifact_present(rd, "working/delivery/{deck_slug}-WEBINAR.mp4") is True
    # The sha computation must also resolve (not 'not-found').
    assert rsd._compute_artifact_sha(rd, "working/delivery/{deck_slug}-WEBINAR.mp4") != "not-found"
    # A genuinely-missing slugged file still fails closed.
    assert rsd._artifact_present(rd, "working/delivery/{deck_slug}-MISSING.mp4") is False
    # Non-templated specs are unaffected.
    assert rsd._artifact_present(rd, "working/copy/intake.json") is True
