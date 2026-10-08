"""lip_gate.py: measured lip-sync gate (Part H H2; looser sung-aware check LSL002).

The measurement is sync_check.py (a faithful port of the fixer window's validated
lipsync_check_v2): mouth opening vs the voice envelope, lag +-10 frames, clip cut
to the audio length, chance test by rolls of the same audio, lookalike other lines
dropped, corr floor 0.40, margin floor 0, SYNCED at margin >= 0.05, WEAK between.

Trevor's looser verdicts ("loosen the checks so it's not as strict"):
  SYNCED     -> PASS
  WEAK       -> ACCEPT_WITH_FLAG (accepted and USED; the flag goes in the receipt)
  NOT_SYNCED -> FAIL on a SPOKEN line
  On a SUNG line WEAK and NOT_SYNCED -> UNDETERMINED: held for a person to look
  at a mouth strip, NO automatic paid redo (diagnosis: 1 of 99 redos ever passed).
  UNMEASURABLE -> reported, never a pass.
Trevor's 2-try rule: at most 2 paid lip-sync jobs per segment, then keep the
best-measured take. Providers are injected so tests run at $0.
"""
from __future__ import annotations

import array
import subprocess

try:                                   # package import
    from . import image_gate
    from . import sync_check as SC
except ImportError:                    # script import (tests run from here)
    import image_gate
    import sync_check as SC
# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..', '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

TOOL_NAME = "lip_gate"
SCHEMA_VERSION = "3.0.0"
MAX_TRIES = 2                # Trevor's 2-try rule: paid lip-sync jobs per segment

PASS, FLAG, FAIL, UNDETERMINED = SC.PASS, SC.FLAG, SC.FAIL, SC.UNDETERMINED
UNMEASURABLE = SC.UNMEASURABLE
UNMEASURED = UNMEASURABLE    # old name
LIP_UNMEASURED = "LIP_UNMEASURED"
LIP_HELD_FOR_PERSON = "LIP_HELD_FOR_PERSON"   # UNDETERMINED: a person looks at a mouth strip

# What "better input" means on the regenerate attempt (spoken lines only).
IMPROVED_INPUT = {
    "line": "single clean line (no internal pause > 0.5 s)",
    "crop": "front-facing tight face crop",
    "image": "still image, relaxed slightly open mouth",
    "lead_in_s": 0.35,
    "tail_s": 0.2,
}

measure = SC.measure_sync


def judge(m, sung=False):
    """Adds verdict (PASS / ACCEPT_WITH_FLAG / FAIL / UNDETERMINED / UNMEASURABLE),
    grade (SYNCED / WEAK / NOT_SYNCED / UNMEASURABLE), reasons (FAIL or
    UNDETERMINED causes) and flags (ACCEPT_WITH_FLAG notes for the receipt)."""
    g, v = SC.grade(m), SC.verdict(m, sung)
    why = ["LIP_%s" % t.upper() for t in SC.fail_tests(m)] if g == SC.NOT_SYNCED else []
    if g == SC.UNMEASURABLE:
        why = [LIP_UNMEASURED]
    flags = []
    if v == FLAG:
        flags.append("LIP_WEAK: margin %.3f over the best other line (< %s); no distinct "
                     "proof, look by eye" % (m["margin"], SC.SYNCED_MARGIN))
    if v == UNDETERMINED:
        why = why or ["LIP_WEAK"]
        why.append(LIP_HELD_FOR_PERSON)
    return dict(m, grade=g, verdict=v, reasons=why, flags=flags, sung=bool(sung))


def unmeasured(why):
    """Judged row for a clip that could not be measured (no mediapipe, no model,
    silent audio...). Reported; never a pass."""
    return dict(SC.unmeasurable(str(why)), verdict=UNMEASURABLE,
                reasons=[LIP_UNMEASURED], flags=[], why=str(why), sung=False)


_RANK = {PASS: 3, FLAG: 2, UNDETERMINED: 1, FAIL: 0, UNMEASURABLE: -1}


def score(j):
    """Higher is better: PASS > ACCEPT_WITH_FLAG > UNDETERMINED > FAIL >
    UNMEASURABLE, then the lead over the other lines and the correlation."""
    return _RANK[j["verdict"]] * 10 + j["margin"] + j["corr"]


def run_gate(line_id, generate, measure_clip, ab_state=None, source_image=None,
             image_check=None, sung=False):
    """Orchestrate at most MAX_TRIES (2) paid lip-sync jobs. Injected, so mocked
    providers work at $0.

    generate(provider, input_spec) -> clip
    measure_clip(clip) -> measurement from measure(), or the Unmeasured
        exception from mouth_landmarks (turned into an UNMEASURABLE verdict)
    sung: this line is SUNG. A sung line that is not PASS is UNDETERMINED and
        stops there (held for a person, no automatic paid redo).
    ab_state: kept for callers; the InfiniTalk third job is gone (2-try rule).
    source_image / image_check: the picture gate, runs BEFORE any generate()
    call; no picture, no checker, or a failing picture raises
    image_gate.LipsyncImageRefused with every reason; nothing is spent.

    Stops at the first take that is not a FAIL (PASS, ACCEPT_WITH_FLAG,
    UNDETERMINED and UNMEASURABLE all stop: a second paid job would not change
    them). After two FAILs keeps the best-measured take. Returns the receipt row.
    """
    if not source_image:
        raise image_gate.LipsyncImageRefused(
            [(image_gate.IMAGE_MISSING, "no lip-sync source picture")], line_id)
    if image_check is None:
        raise image_gate.LipsyncImageRefused(
            [(image_gate.IMAGE_UNCHECKED, "no image check supplied")], line_id)
    res = image_check(source_image)
    if not isinstance(res, dict) or res.get("pass") is not True:
        raise image_gate.LipsyncImageRefused(
            (res or {}).get("reasons") or [(image_gate.UNMEASURED,
                                            "image check gave no verdict")],
            line_id)
    src = {"source_image": source_image}
    plan = [("kling", src), ("kling", dict(IMPROVED_INPUT, **src))][:MAX_TRIES]
    attempts = []
    for provider, spec in plan:
        attempts.append(_attempt(provider, spec, generate, measure_clip, sung))
        if attempts[-1]["judge"]["verdict"] != FAIL:
            break
    return _row(line_id, attempts)


def _attempt(provider, spec, generate, measure_clip, sung):
    clip = generate(provider, spec)
    try:
        j = judge(measure_clip(clip), sung)
    except Exception as e:          # Unmeasured from mouth_landmarks, bad input
        if str(e).startswith(LIP_UNMEASURED) or isinstance(e, ValueError):
            j = unmeasured(e)
        else:
            raise
    return {"provider": provider, "input": spec or "base", "clip": clip,
            "judge": j}


def _row(line_id, attempts):
    kept = max(attempts, key=lambda a: score(a["judge"]))
    j = kept["judge"]
    verdict = j["verdict"] if j["verdict"] != FAIL else "FAIL_REPLACE"
    return {"tool": TOOL_NAME, "line_id": line_id, "attempts": attempts,
            "paid_jobs": len(attempts), "infinitalk_ab": False,
            "kept": kept["provider"], "kept_clip": kept["clip"],
            "verdict": verdict, "grade": j["grade"], "sung": j["sung"],
            "flags": j.get("flags", []), "reasons": j.get("reasons", []),
            "numbers": {k: j[k] for k in (
                "offset_s", "lag_frames", "corr", "control_corr", "margin", "pct")}}


LIPSYNC_VIEW = "lipsync-closeup"
LIPSYNC_REF_MISSING = "LIPSYNC_CLOSEUP_MISSING"
LIPSYNC_MOUTH_BAD = "LIPSYNC_CLOSEUP_MOUTH_NOT_CLEAR"


def lipsync_closeup(reference_set, character):
    """The character's lip-sync close-up entry (the default source image), or None."""
    for r in reference_set:
        if r.get("character") == character and r.get("view") == LIPSYNC_VIEW:
            return r
    return None


def check_reference_set(reference_set, characters, mouth_clear):
    """Owner order 2026-10-08: every speaking/singing character needs a lip-sync
    close-up whose mouth is sharp and unobstructed. mouth_clear(entry) -> bool is
    the injected face/mouth detection or vision check. A set without it FAILS."""
    bad = []
    for c in characters:
        e = lipsync_closeup(reference_set, c)
        if e is None:
            bad.append({"character": c, "reason_code": LIPSYNC_REF_MISSING})
        elif not mouth_clear(e):
            bad.append({"character": c, "reason_code": LIPSYNC_MOUTH_BAD})
    return {"pass": not bad, "failed": bad}


def qc_check(rows):
    """Receipt-level check: every lip clip has a PASS or ACCEPT_WITH_FLAG row with
    numbers. FAIL_REPLACE, UNMEASURABLE and UNDETERMINED rows fail the check; an
    UNDETERMINED row clears only when a person looked at a mouth strip and wrote
    person_verdict = "PASS" on the row."""
    def ok(r):
        v = r.get("verdict")
        return "numbers" in r and (v in (PASS, FLAG) or (
            v == UNDETERMINED and r.get("person_verdict") == PASS))
    bad = [r.get("line_id") for r in rows if not ok(r)]
    held = [r.get("line_id") for r in rows
            if r.get("verdict") == UNDETERMINED and not ok(r)]
    return {"pass": not bad, "failed_lines": bad, "held_for_person": held,
            "reason_code": None if not bad else "LIP_SYNC_GATE_FAILED"}


# ------------------------------------------------ optional ffmpeg helpers ----

def _run_raw(argv):
    p = _LG.run_ffmpeg(argv, "lip-gate-measure", stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("%s: %s" % (LIP_UNMEASURED, p.stderr[-300:]))
    return p.stdout


def envelope(audio, fps=30, ffmpeg="ffmpeg", start=0.0):
    """RMS loudness per 1/fps window of the FINAL MIX (fps may be fractional);
    natural length of the audio, not smoothed (sync_check smooths)."""
    sr = 16000
    raw = _run_raw([ffmpeg, "-v", "error", "-threads", "4", "-ss",
                    str(start), "-i", audio, "-ac", "1", "-ar", str(sr),
                    "-f", "s16le", "-"])
    s = array.array("h")
    s.frombytes(raw[:len(raw) // 2 * 2])
    h, out, i = sr / float(fps), [], 0
    while int(i * h) < len(s):
        a, b = int(i * h), int((i + 1) * h)
        if b > a:
            seg = s[a:b]
            out.append((sum(v * v for v in seg) / len(seg)) ** 0.5 / 32768.0)
        i += 1
    return out


def measure_file(clip, audio=None, others=(), ffmpeg="ffmpeg"):
    """Measure a real clip: landmark mouth opening vs the voice envelope.
    audio = the audio span the clip should follow (default: the clip's own
    track); others = the chapter's other lines' audio (>= 2). Raises
    mouth_landmarks.Unmeasured when mediapipe / the model is missing: run_gate
    turns it into an UNMEASURABLE verdict, never a pass."""
    try:
        from . import mouth_landmarks as ML
    except ImportError:
        import mouth_landmarks as ML
    s = ML.mouth_series(clip)
    fps = s["fps"]
    filled, why = ML.usable(s)
    if why:                       # no face / not human: cannot be measured
        return dict(SC.unmeasurable(why), fps=fps, face_found=s["face_found"])
    voice = envelope(audio or clip, fps=fps, ffmpeg=ffmpeg)
    ctrl = [envelope(o, fps=fps, ffmpeg=ffmpeg) for o in others]
    return SC.measure_sync(filled, voice, ctrl, fps, s["face_found"], s["mouth_pos"])
