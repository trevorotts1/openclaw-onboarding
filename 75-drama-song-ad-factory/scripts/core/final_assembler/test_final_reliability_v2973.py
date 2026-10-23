#!/usr/bin/env python3
"""RL1 tests (skill 75 v2.9.73): reliability fixes proven by the Voyage To
Virtue run (spec ~/scratch/dsf-stall-fix/RELIABILITY-SPEC.md, L1).

  1. MISSING LIP-SYNC EVIDENCE — zero markers and zero speaker lines
     fails closed with coverage evidence. Declared short coverage still fails.
     Numeric policy changes are outside this regression test.
  2. HOLD CLIP TO SLOT — a clip SHORTER than its planned slot is held
     (tpad clone) to the slot; the rendered master duration equals the
     planned total within one frame (live ffmpeg render, no spend).
  3. LANE_SIZE_BROKEN — the lane_size.py call matches size()'s current
     signature; ZERO LANE_SIZE_BROKEN warnings on a normal assemble.
  4. ERROR RECEIPT BESIDE OUTPUT — every assemble() outcome (errors
     included) writes <output>.receipt.json; assembly stays headless.

stdlib only, zero paid calls, no network, no browser (local ffmpeg only).
Run: python3 core/final_assembler/test_final_reliability_v2973.py
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A          # noqa: E402
from final_assembler.lipsync_coverage import (  # noqa: E402
    COVERAGE_SHORT, LINES_TOO_FEW,
)
FAILS = []
FPS = 30


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _faceless_plan(total_s=65.0):
    return {"fps": FPS, "width": 1920, "height": 1080, "song_path": None,
            "total_dur": total_s, "total_frames": 1950, "lines": [],
            "segments": [{"src": "clip%d.mp4" % i, "frames": 300,
                          "snapped_dur": 10.0, "transition": "none",
                          "xfade_dur": 0.0, "offset_frames": 300 * i}
                         for i in range(13)]}


def test_faceless_plan_fails_closed():
    """Deleting both metadata sources cannot turn a failure into exemption."""
    plan = _faceless_plan()
    rec = A.lipsync_gate(plan)
    check("missing metadata blocks", rec and rec.get("outcome") == "error", rec)
    check("missing metadata names the evidence failure",
          rec.get("reason_code") == "LIPSYNC_EVIDENCE_MISSING", rec)
    ev = rec.get("evidence") or {}
    check("failure retains the coverage numbers",
          ev.get("ad_length_s") == 65.0 and ev.get("lipsync_lines_count") == 0
          and ev.get("lipsync_total_s") == 0, ev)
    check("failure states the required recovery", bool(rec.get("next_action")))


def test_partial_metadata_loss_fails_closed():
    """A marker alone, a missing line ID or an unknown line is not evidence."""
    plan = _faceless_plan(30)
    plan["segments"] = [dict(s, lip_sync=True, lip_sync_line_ids=["L1"])
                        for s in plan["segments"][:6]]
    for label, lines in (("speaker metadata removed", []),
                         ("speaker field removed", [{"line_id": "L1"}]),
                         ("line identity changed", [{"line_id": "other", "speaker": "lead"}])):
        plan["lines"] = lines
        rec = A.lipsync_gate(plan)
        check(label + " blocks", rec and rec.get("reason_code") ==
              "LIPSYNC_EVIDENCE_MISSING", rec)
    plan["lines"] = [{"line_id": "L1", "speaker": "lead"}]
    for seg in plan["segments"]:
        seg.pop("lip_sync_line_ids")
    rec = A.lipsync_gate(plan)
    check("boolean markers alone block", rec and rec.get("reason_code") ==
          "LIPSYNC_EVIDENCE_MISSING", rec)
    # An arbitrary flag is not an approval bound to this plan.
    plan["lipsync_exception"] = {"approved": True}
    rec = A.lipsync_gate(plan)
    check("unbound exception flag cannot bypass", rec and rec.get("outcome") == "error", rec)


def test_declared_lines_keep_the_hard_gate():
    """A plan that DECLARES lip-sync lines still refuses when coverage is
    short — unchanged hard gate."""
    plan = _faceless_plan()
    plan["segments"] = [
        dict(s, lip_sync_line_ids=["L%d" % (i + 1)], lip_sync=True)
        if i < 4 else s
        for i, s in enumerate(plan["segments"])]
    plan["lines"] = [{"line_id": "L%d" % (i + 1), "speaker": "lead",
                      "start_s": 10.0, "end_s": 12.0} for i in range(4)]
    rec = A.lipsync_gate(plan)
    check("declared short coverage still refuses",
          rec and rec.get("outcome") == "error", rec)
    check("refusal carries the measured codes",
          rec and any(c in rec["reason_code"]
                      for c in (COVERAGE_SHORT, LINES_TOO_FEW)),
          (rec or {}).get("reason_code"))
    check("refusal carries coverage numbers",
          (rec.get("evidence") or {}).get("lipsync_lines_count") == 4,
          json.dumps(rec.get("evidence")))


def _fixture(tmp, clip_s=2.0, slot_s=3.34, speakers=None):
    """Three moving 30 fps clips + a timeline whose middle slot is LONGER
    than its clip (the Voyage shape: 6 s slots from ~5.3 s clips). When
    `speakers` is given, the timeline declares speaker lines with NO
    lip_sync markers (short coverage -> the unchanged hard gate)."""
    def ff(*a):
        A._LG.run_ffmpeg(["ffmpeg", "-v", "error", "-y"] + list(a),
                         "synthetic-rl1-fixture", check=True, capture_output=True)
    for i in range(3):
        ff("-f", "lavfi", "-i",
           "testsrc2=size=320x240:rate=30:duration=%g" % clip_s,
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           os.path.join(tmp, "clip%d.mp4" % i))
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "json",
                        os.path.join(tmp, "clip1.mp4")],
                       capture_output=True, text=True)
    real = float(json.loads(p.stdout)["format"]["duration"])
    tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": FPS,
          "width": 320, "height": 240, "song_path": None,
          "segments": [{"src": "clip%d.mp4" % i, "dur": slot_s,
                        "transition": "none", "beat_cut": True,
                        "motion_score": {"score": 0.5}}
                       for i in range(3)]}
    if speakers:
        tl["lines"] = [{"line_id": "L%d" % (i + 1), "speaker": speak,
                        "start_s": 10.0, "end_s": 12.0}
                       for i, speak in enumerate(speakers)]
    path = os.path.join(tmp, "timeline.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(tl, fh)
    return path, real


def test_hold_command_preserved_offline():
    """No render required: the same command still pads a short ordinary clip."""
    plan = _faceless_plan(10)
    plan["segments"] = [dict(plan["segments"][0], source_dur=2.0, hold=True)]
    argv = A.build_argv(plan, "synthetic-output.mp4")
    command = " ".join(argv)
    check("hold-to-slot keeps clone padding", "tpad=stop_mode=clone:stop=-1" in command)
    check("hold-to-slot trims to the requested slot", "trim=duration=10.000000" in command)


def test_missing_metadata_writes_receipt_offline(tmp_root):
    """Offline assembly refusal writes evidence and never reaches rendering."""
    tmp = tempfile.mkdtemp(prefix="w75-missing-evidence-", dir=tmp_root)
    src, timeline, output = (os.path.join(tmp, n) for n in
                             ("synthetic.mp4", "timeline.json", "out.mp4"))
    with open(src, "wb") as f:
        f.write(b"synthetic media: probe is stubbed, render must not run")
    with open(timeline, "w", encoding="utf-8") as f:
        json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": FPS,
                   "width": 320, "height": 240, "song_path": None,
                   "segments": [{"src": src, "dur": 5,
                                 "motion_score": {"score": 0.5}}]}, f)
    with mock.patch.object(A, "probe_duration", return_value=5), \
            mock.patch.object(A, "_run") as render:
        rec = A.assemble(timeline, output)
    check("metadata-free assembly refuses offline", rec["outcome"] == "error"
          and rec["reason_code"] == "LIPSYNC_EVIDENCE_MISSING", rec)
    check("metadata-free assembly never calls renderer", not render.called)
    with open(output + ".receipt.json", encoding="utf-8") as f:
        saved = json.load(f)
    check("offline failure receipt retains exact evidence", saved == rec)
    check("offline refusal creates no master", not os.path.exists(output))


def test_short_clip_held_to_slot(tmp_root):
    """A short clip in a longer slot renders the PLANNED total within one
    frame (live render; BEFORE the fix the file was trimmed to EOF)."""
    tmp = tempfile.mkdtemp(prefix="w75-RL1-slot-", dir=tmp_root)
    tl_path, real = _fixture(tmp)
    proc = A.plan_timeline(A.load_timeline(tl_path), tmp,
                           probe=lambda s: A.probe_duration(s))
    planned = proc["total_dur"]
    check("planned total is the sum of the declared slots",
          abs(planned - 3 * 100 / FPS) < 1e-6, planned)
    # sanity: the slot is genuinely longer than the clip
    check("fixture is the short-clip/longer-slot shape",
          any(real + 1.0 / FPS < s["snapped_dur"]
              for s in proc["segments"]),
          "real=%s slots=%s" % (real, [s["snapped_dur"]
                                       for s in proc["segments"]]))
    # This is a renderer unit test, not a lip-sync approval fixture. Exercise
    # the hold-to-slot command directly; production assembly now requires the
    # approved storyboard and generated-media identity chain.
    for seg in proc["segments"]:
        seg["src"] = os.path.join(tmp, seg["src"])
        seg["source_dur"] = real
        seg["hold"] = True
    output = os.path.join(tmp, "out.mp4")
    argv = A.build_argv(proc, output)
    check("short clips retain deliberate hold instructions",
          "tpad=stop_mode=clone" in " ".join(argv))
    rendered = A._run(argv, timeout=120)
    check("hold-to-slot command renders", rendered.returncode == 0,
          rendered.stderr[-300:])
    vdur = A.probe_duration(output) if rendered.returncode == 0 else None
    check("rendered == planned within one frame",
          vdur is not None and abs(vdur - planned) <= 1.0 / FPS + 1e-3,
          "planned=%.4f output=%r" % (planned, vdur))


def test_no_lane_size_warnings(tmp_root):
    """The four LANE_SIZE_BROKEN warnings are gone on a normal assembly."""
    import lane_size
    tmp = tempfile.mkdtemp(prefix="w75-RL1-lane-", dir=tmp_root)
    tl_path, _real = _fixture(tmp)
    buf = io.StringIO()
    plan = A.plan_timeline(A.load_timeline(tl_path), tmp,
                           probe=lambda s: A.probe_duration(s))
    with contextlib.redirect_stderr(buf):
        A.size_ffmpeg(plan["total_dur"], 320, 240)   # assemble's timeout path
        t2 = A._lane_size_threads()                  # the fixed path
        A.build_argv(plan, os.path.join(tmp, "out.mp4"))
    n = buf.getvalue().count("LANE_SIZE_BROKEN")
    check("zero LANE_SIZE_BROKEN warnings on a normal assembly",
          n == 0, "got %d: %s" % (n, buf.getvalue()[:200]))
    check("the fixed call returns machine-sized threads",
          isinstance(t2, int) and t2 >= 1, t2)
    check("lane_size.ffmpeg_lines matches lane_size.size's own pool",
          A._lane_size_threads() == lane_size.size(
              "claude-code", "openrouter", units=999)["ffmpeg_threads"])


def test_error_receipt_beside_output(tmp_root):
    """Every assemble() outcome writes <output>.receipt.json (headless:
    the file is the deliverable, not stdout). Error receipt carries the
    refusal + numbers."""
    tmp = tempfile.mkdtemp(prefix="w75-RL1-err-", dir=tmp_root)
    tmp2 = tempfile.mkdtemp(prefix="w75-RL1-err2-", dir=tmp_root)
    # (a) error before any render: gate refusal writes beside output
    tl_path, _real = _fixture(tmp, speakers=3 * ["lead"])
    rec = A.assemble(tl_path, os.path.join(tmp2, "gone.mp4"))
    check("speaker-declared short coverage refuses",
          rec["outcome"] == "error"
          and COVERAGE_SHORT in rec["reason_code"], rec.get("reason_code"))
    p = os.path.join(tmp2, "gone.mp4.receipt.json")
    check("error receipt written beside the (never rendered) output",
          os.path.isfile(p), p)
    if os.path.isfile(p):
        saved = json.load(open(p, encoding="utf-8"))
        ev = saved.get("evidence") or {}
        check("saved receipt is the same refusal with numbers",
              saved["reason_code"] == rec["reason_code"] and
              ev.get("lipsync_lines_count") == 0            # zero planned clips
              and ev.get("lipsync_total_s") == 0
              and ev.get("required_lines_min", 0) >= 3      # the floor it missed
              and ev.get("required_total_s", 0) > 0,        # the seconds it missed
              json.dumps(ev)[:200])
    # (b) structural error before the gates: TIMELINE_BAD_* also writes
    bad = os.path.join(tmp, "bad.json")
    with open(bad, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                   "width": 320, "height": 240, "song_path": None,
                   "transition": "none", "segments": []}, fh)
    rec2 = A.assemble(bad, os.path.join(tmp2, "gone2.mp4"))
    check("structural refusal writes its receipt too",
          rec2["outcome"] == "error" and os.path.isfile(
              os.path.join(tmp2, "gone2.mp4.receipt.json")),
          rec2.get("reason_code"))


def test_assembly_is_headless(tmp_root):
    """RL1 item 4: assemble drivable with no prompt/no browser — the CLI
    main() refuses a metadata-free timeline without stdin and writes the
    failure receipt; it must not render that timeline."""
    tmp = tempfile.mkdtemp(prefix="w75-RL1-head-", dir=tmp_root)
    tl_path, _real = _fixture(tmp)
    out = os.path.join(tmp, "master.mp4")
    argv = [sys.executable, os.path.join(HERE, "assembler.py"), tl_path, out]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=300)
    rec = json.loads(proc.stdout)
    check("headless CLI refuses missing lip-sync evidence",
          rec["outcome"] == "error"
          and rec["reason_code"] == "LIPSYNC_EVIDENCE_MISSING",
          rec.get("reason_code"))
    check("headless refusal never renders a master", not os.path.exists(out))
    check("headless CLI wrote the receipt beside the output",
          os.path.isfile(out + ".receipt.json"))


def main():
    tmp_root = tempfile.mkdtemp(prefix="/tmp/w75-RL1-tests-")
    try:
        test_faceless_plan_fails_closed()
        test_partial_metadata_loss_fails_closed()
        test_declared_lines_keep_the_hard_gate()
        test_hold_command_preserved_offline()
        test_missing_metadata_writes_receipt_offline(tmp_root)
        test_short_clip_held_to_slot(tmp_root)
        test_no_lane_size_warnings(tmp_root)
        test_error_receipt_beside_output(tmp_root)
        test_assembly_is_headless(tmp_root)
    finally:
        import shutil
        shutil.rmtree(tmp_root, ignore_errors=True)
    print("%s" % ("%d check(s) failed" % len(FAILS) if FAILS
                  else "all RL1 checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())