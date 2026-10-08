"""lip_gate.py: measured lip-sync gate (Part H H2; looser sung-aware check LSL002;
best-practice rules LSR001 folded in by LSC001).

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
Trevor's 2-try rule (2026-10-08: "only allow 2 try twice per thing it creates
after that it goes with whatever is the best one"), in code:
  * kling/ai-avatar-standard is THE lip-sync model. No other model, no third job.
  * at most 2 paid jobs per segment, every name variant counted (`prior_jobs`);
  * try 1 already uses the padded cut (0.30 s lead-in, 0.20 s tail);
  * try 2 runs ONLY on a hard defect (a FAIL verdict, or a defect a person saw:
    `hard_defects` on the measurement) and ONLY with a CHANGED input
    (`retry_input`, e.g. the next-best choose_window window); never on
    ACCEPT_WITH_FLAG, UNDETERMINED or UNMEASURABLE;
  * then the best take is kept: receipt row `KEPT_BEST_OF_2` with numbers, flag
    and the mouth-strip path;
  * every paid submit goes through load_governor.kie_request; landmark work goes
    through heavy_slot (mouth_landmarks).
The sync gate is sync_check (calibrated on real controls). event_sync.py is an
ADVISORY extra recorded in the row as `advisory_event_sync`; it never gates.
Providers are injected so tests run at $0.
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
SCHEMA_VERSION = "4.0.0"
MAX_TRIES = 2                # Trevor's 2-try rule: paid lip-sync jobs per segment
KEPT = "KEPT_BEST_OF_2"      # receipt verdict: two tries made, the best take kept
LIP_TRY_LIMIT = "LIP_TRY_LIMIT"
LIP_HARD_DEFECT = "LIP_HARD_DEFECT"
LIP_MODEL = "kling/ai-avatar-standard"   # THE lip-sync model; InfiniTalk is manual backup only

PASS, FLAG, FAIL, UNDETERMINED = SC.PASS, SC.FLAG, SC.FAIL, SC.UNDETERMINED
UNMEASURABLE = SC.UNMEASURABLE
UNMEASURED = UNMEASURABLE    # old name
LIP_UNMEASURED = "LIP_UNMEASURED"
LIP_HELD_FOR_PERSON = "LIP_HELD_FOR_PERSON"   # UNDETERMINED: a person looks at a mouth strip

# The DEFAULT input for try 1 (it used to be redo-only): padded cut, clean line.
IMPROVED_INPUT = {
    "line": "single clean line (no internal pause > 0.5 s)",
    "crop": "front-facing tight face crop",
    "image": "still image, lips relaxed and very slightly parted",
    "lead_in_s": 0.30,
    "tail_s": 0.20,
}

_PROMPT = {
    "sung": "A 3D animated {who} sings this line to the camera with a {emo} "
            "expression. Minimal head movement, steady locked camera, natural "
            "blinks, relaxed shoulders. {Poss} whole face and mouth stay fully "
            "visible. No text, captions or watermark.",
    "spoken": "A 3D animated {who} says this line to the camera, {emo}. "
              "Minimal head movement, steady locked camera, natural blinks. "
              "{Poss} whole face and mouth stay fully visible. No text, "
              "captions or watermark.",
}


class LipTryLimit(Exception):
    """A third paid lip-sync job was asked for. Nothing was spent."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def kling_prompt(kind, who="woman", emotion=None):
    """Kling prompt: 'sings' on sung lines, 'says' on spoken ones, ONE emotion,
    minimal head movement, steady camera. Mouth timing comes from the audio, so
    it never says 'lips open and close in time'."""
    if kind not in _PROMPT:
        raise ValueError("kind must be 'sung' or 'spoken'")
    emo = (emotion or ("calm, earnest" if kind == "sung" else "calm and sincere")).strip()
    poss = "His" if who.strip().lower() in ("man", "boy", "father", "dad") else "Her"
    return _PROMPT[kind].format(who=who.strip(), emo=emo, Poss=poss)


measure = SC.measure_sync


def judge(m, sung=False):
    """Adds verdict (PASS / ACCEPT_WITH_FLAG / FAIL / UNDETERMINED / UNMEASURABLE),
    grade (SYNCED / WEAK / NOT_SYNCED / UNMEASURABLE), reasons (FAIL or
    UNDETERMINED causes) and flags (ACCEPT_WITH_FLAG notes for the receipt)."""
    g, v = SC.grade(m), SC.verdict(m, sung)
    hard = list(m.get("hard_defects") or [])      # defects a person saw: garbled face, hand over mouth
    if hard and g != SC.UNMEASURABLE:
        v = FAIL
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
    if hard:
        why = why + [LIP_HARD_DEFECT] + hard
    return dict(m, grade=g, verdict=v, reasons=why, flags=flags, sung=bool(sung),
                hard_defects=hard)


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


def run_gate(line_id, generate, measure_clip, source_image=None, image_check=None,
             sung=False, retry_input=None, prior_jobs=0, make_strip=None,
             advisory=None, acquire=None):
    """Orchestrate at most MAX_TRIES (2) paid kling/ai-avatar-standard jobs for
    one segment. Injected providers, so mocked runs cost $0.

    generate("kling", input_spec) -> clip
    measure_clip(clip) -> measurement from measure(), or the Unmeasured
        exception from mouth_landmarks (turned into an UNMEASURABLE verdict).
        The measurement may carry `hard_defects` (a person saw a garbled face,
        text across the chest, a hand over the mouth): that makes it a FAIL.
    sung: this line is SUNG. A sung line that is not PASS is UNDETERMINED and
        stops there (held for a person, no automatic paid redo).
    prior_jobs: paid lip-sync jobs already made for this segment under ANY name
        variant (lipsync_clips.count_jobs). Tries left = 2 - prior_jobs; none
        left raises LipTryLimit before anything is spent.
    retry_input: the CHANGED input for try 2 (next-best choose_window window, or
        the padded cut). Missing or identical = try 2 is refused, try 1 is kept.
    make_strip(clip) -> path of the 8-frame mouth strip of the kept take.
    advisory(clip) -> event_sync result, recorded as `advisory_event_sync`;
        never gates and never decides anything.
    source_image / image_check: the picture gate, runs BEFORE any generate()
        call; no picture, no checker, or a failing picture raises
        image_gate.LipsyncImageRefused with every reason; nothing is spent.

    Try 2 runs ONLY when try 1 is a hard defect (FAIL). PASS, ACCEPT_WITH_FLAG,
    UNDETERMINED and UNMEASURABLE all stop: a second paid job would not change
    them. Returns the receipt row.
    """
    left = MAX_TRIES - int(prior_jobs)
    if left <= 0:
        raise LipTryLimit(LIP_TRY_LIMIT, "segment %s already has %d paid lip-sync "
                          "job(s); the limit is %d. Keep the best-measured take, "
                          "mark it KEPT_BEST_OF_2, move on." % (line_id, prior_jobs, MAX_TRIES))
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
    spec1 = dict(IMPROVED_INPUT, source_image=source_image, **{"try": 1})
    attempts = [_attempt(spec1, generate, measure_clip, sung, advisory, acquire, line_id)]
    flag = None
    if attempts[0]["judge"]["verdict"] == FAIL and left >= 2:
        spec2 = dict(retry_input or {}, source_image=source_image, **{"try": 2})
        if retry_input and not _same(spec2, spec1):
            attempts.append(_attempt(spec2, generate, measure_clip, sung, advisory,
                                     acquire, line_id))
        else:
            flag = "RETRY_REFUSED: try 2 needs a changed input; kept try 1"
    return _row(line_id, attempts, flag, make_strip, prior_jobs)


def _same(a, b):
    return {k: v for k, v in a.items() if k != "try"} == {k: v for k, v in b.items() if k != "try"}


def _attempt(spec, generate, measure_clip, sung, advisory, acquire, line_id):
    # every paid submit goes through the KIE pacing bucket (20 new jobs / 10 s)
    clip = _LG.kie_request(lambda: generate("kling", spec),
                           "lipsync %s try %s" % (line_id, spec.get("try")),
                           generation=True, acquire=acquire)
    try:
        j = judge(measure_clip(clip), sung)
    except Exception as e:          # Unmeasured from mouth_landmarks, bad input
        if str(e).startswith(LIP_UNMEASURED) or isinstance(e, ValueError):
            j = unmeasured(e)
        else:
            raise
    adv = None
    if advisory is not None:
        try:
            adv = advisory(clip)
        except Exception as e:      # advisory only: its failure changes nothing
            adv = {"verdict": "UNMEASURABLE", "reason": str(e)}
    return {"provider": "kling", "model": LIP_MODEL, "input": spec, "clip": clip,
            "judge": j, "advisory_event_sync": adv}


def _row(line_id, attempts, flag, make_strip, prior_jobs=0):
    kept = max(attempts, key=lambda a: score(a["judge"]))
    j = kept["judge"]
    v = j["verdict"]
    row_verdict = KEPT if v == FAIL else v
    why = list(j.get("reasons", []))
    if v == FAIL and flag is None:
        flag = "%s (corr %.2f, margin %.3f)" % (",".join(why) or "FAIL", j["corr"], j["margin"])
    return {"tool": TOOL_NAME, "line_id": line_id, "attempts": attempts,
            "paid_jobs": len(attempts), "jobs_used": len(attempts),
            "jobs_total": int(prior_jobs) + len(attempts),
            "kept": kept["provider"], "kept_try": kept["input"].get("try"),
            "kept_clip": kept["clip"], "verdict": row_verdict,
            "grade": j["grade"], "sung": j["sung"],
            "flag": flag if v == FAIL else None,
            "flags": j.get("flags", []), "reasons": why,
            "receipt": None if v != FAIL else "KEPT_BEST_OF_2 (t%s), %s, %s" % (
                kept["input"].get("try"), j["grade"], flag),
            "mouth_strip": make_strip(kept["clip"]) if make_strip else None,
            "advisory_event_sync": kept.get("advisory_event_sync"),
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
    """Receipt-level check: every lip clip has a PASS or ACCEPT_WITH_FLAG row
    with numbers; or a flagged KEPT_BEST_OF_2 row (Trevor's keep-best-of-2 rule)
    that carries numbers, the flag text and a mouth-strip path. More than 2 paid
    jobs on a segment always fails. An UNDETERMINED or UNMEASURABLE row (a sung
    line) clears only when a person looked at a mouth strip and wrote
    person_verdict = "PASS" on the row."""
    def ok(r):
        v = r.get("verdict")
        if "numbers" not in r or r.get("jobs_total", r.get("jobs_used", 1)) > MAX_TRIES:
            return False
        if v in (PASS, FLAG):
            return True
        if v == KEPT:
            return bool(r.get("flag") and r.get("mouth_strip"))
        return v in (UNDETERMINED, UNMEASURABLE) and r.get("person_verdict") == PASS
    bad = [r.get("line_id") for r in rows if not ok(r)]
    held = [r.get("line_id") for r in rows
            if r.get("verdict") in (UNDETERMINED, UNMEASURABLE) and not ok(r)]
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


def advisory_file(clip, audio, words=(), others=(), ffmpeg="ffmpeg"):
    """ADVISORY event_sync of a real clip against the lead-vocal span `audio`
    (word stamps relative to the span start; others = the chapter's other lines'
    audio). Recorded in the receipt, never gates. Raises Unmeasured like
    measure_file."""
    try:
        from . import mouth_landmarks as ML
        from . import event_sync as ES
    except ImportError:
        import mouth_landmarks as ML
        import event_sync as ES
    s = ML.mouth_series(clip)
    fps = s["fps"]
    dur = len(s["opening"]) / float(fps)
    op = [float("nan") if v is None else v for v in s["opening"]]

    def ev(a, w=()):
        return ES.events(ES.voiced_runs(envelope(a, fps=int(round(fps)), ffmpeg=ffmpeg),
                                        int(round(fps))), w, None)
    base = ev(audio, words)
    base["dur"] = max(base["dur"], dur)
    return ES.event_sync(op, base, [ev(o) for o in others], fps)


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
