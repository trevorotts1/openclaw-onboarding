"""lip_gate.py: measured lip-sync gate (Part H H2; looser sung-aware check LSL002;
best-practice rules LSR001 folded in by LSC001).

The measurement is sync_check.py (a faithful port of the fixer window's validated
lipsync_check_v2): mouth opening vs the voice envelope, lag +-10 frames, clip cut
to the audio length, chance test by rolls of the same audio, lookalike other lines
dropped, corr floor 0.40 (0.35 on a cartoon look, approved by Trevor 2026-10-13),
margin floor 0, SYNCED at margin >= 0.05, WEAK between.

Trevor's looser verdicts ("loosen the checks so it's not as strict"):
  SYNCED     -> PASS
  WEAK       -> ACCEPT_WITH_FLAG (accepted and USED; the flag goes in the receipt)
  NOT_SYNCED -> FAIL on a SPOKEN line
  On a SUNG line WEAK and NOT_SYNCED -> UNDETERMINED: held for a person to look
  at a mouth strip, NO automatic paid redo (diagnosis: 1 of 99 redos ever passed).
  UNMEASURABLE -> reported, never a pass.
Trevor's 2-try rule (2026-10-08: "only allow 2 try twice per thing it creates
after that it goes with whatever is the best one"), in code:
  * omnihuman-2-0 is THE lip-sync model (S-42). No other model, no backup, no
    third job.
  * at most 2 paid jobs per segment, every name variant counted (`prior_jobs`);
  * try 1 already uses the padded cut (0.30 s lead-in, 0.20 s tail);
  * try 2 (LSP001) runs ONLY on a PERSON'S call: `person_verdict="DEFECT"` or a
    defect a person saw (`hard_defects` on the measurement), with fewer than 2
    jobs and a CHANGED input (`retry_input`, e.g. the next-best choose_window
    window). NEVER on a checker verdict, FAIL included (lip_process.retry_allowed);
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
    from . import lip_process as LP
    from . import sync_check as SC
except ImportError:                    # script import (tests run from here)
    import image_gate
    import lip_process as LP
    import sync_check as SC
# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..', '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402
import prompt_templates as _PT  # noqa: E402  (U15e: the avatar template)
from kie_dispatch import model_lock as _ML  # noqa: E402

TOOL_NAME = "lip_gate"
SCHEMA_VERSION = "4.0.0"
MAX_TRIES = 2                # Trevor's 2-try rule: paid lip-sync jobs per segment
KEPT = "KEPT_BEST_OF_2"      # receipt verdict: two tries made, the best take kept
LIP_TRY_LIMIT = "LIP_TRY_LIMIT"
LIP_HARD_DEFECT = "LIP_HARD_DEFECT"
# F-LIP-2: ONE source of truth. The model id lives in kie_dispatch.model_lock
# (S-42: OmniHuman 2.0 replaces Kling on every run); this module follows it so
# the route the gate drives can never drift from the route the join verifies.
LIP_MODEL = _ML.LOCKED_LIPSYNC_MODEL
PROVIDER = LIP_MODEL.split("/")[0] if "/" in LIP_MODEL else LIP_MODEL
# F-LIP-2 third-job rule (plan 06 tries section): after two lettered tries the
# third job is a remake of the SAME model with a fixed prompt (letters and decor
# removed), never a silent model switch. run_gate enforces the cap (MAX_TRIES);
# this string is the rule the receipt carries.
THIRD_JOB_RULE = ("after two lettered tries the third job is a remake of the "
                  "same locked model with a fixed prompt; never a silent model "
                  "switch (refused LIPSYNC_ROUTE_CHANGED at the evidence join)")

PASS, FLAG, FAIL, UNDETERMINED = SC.PASS, SC.FLAG, SC.FAIL, SC.UNDETERMINED
UNMEASURABLE = SC.UNMEASURABLE
UNMEASURED = UNMEASURABLE    # old name
LIP_UNMEASURED = "LIP_UNMEASURED"
LIP_HELD_FOR_PERSON = "LIP_HELD_FOR_PERSON"   # UNDETERMINED: a person looks at a mouth strip

# The DEFAULT input for try 1 (it used to be redo-only): padded cut, clean line.
IMPROVED_INPUT = {
    "line": "single clean line (no internal pause > 0.5 s)",
    "crop": "front-facing tight face crop",
    "image": "front-facing head-and-shoulders, lips gently closed or slightly "
             "parted, no teeth showing, nothing over the mouth",
    "lead_in_s": 0.30,
    "tail_s": 0.20,
}

class LipTryLimit(Exception):
    """A third paid lip-sync job was asked for. Nothing was spent."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def kling_prompt(kind, who="woman", emotion=None, mode="lifelike-3d"):
    """RETIRED (S-42, N-08; Trevor, November 23, about 2:25 PM).

    The lip-sync model is OmniHuman 2.0 (`omnihuman-2-0`), it runs on one
    picture plus the audio, and it takes NO prompt. There is no lip-sync model
    to pick and no backup, so nothing assembles a lip-sync prompt any more.

    Kept as a name so an older caller still resolves, and so the refusal is
    one named code rather than an AttributeError. A call raises
    LIPSYNC_PROMPT_PRESENT (or LIPSYNC_MODEL_MISMATCH), never a prompt: the old
    builder it forwards to is retired in prompt_templates for the same reason.
    """
    if kind == "sung":
        verb, default_emo = "sings", "calm"
    elif kind == "spoken":
        verb, default_emo = "says", "calm"
    else:
        raise ValueError("kind must be 'sung' or 'spoken', not %r" % (kind,))
    emo = (emotion or default_emo).strip()
    noun = who.strip()
    poss = "His" if noun.lower() in ("man", "boy", "father", "dad") else "Her"
    return _PT.assemble_kling_avatar(mode, noun, verb, emo, poss)


measure = SC.measure_sync


def judge(m, sung=False, look=None):
    """Adds verdict (PASS / ACCEPT_WITH_FLAG / FAIL / UNDETERMINED / UNMEASURABLE),
    grade (SYNCED / WEAK / NOT_SYNCED / UNMEASURABLE), reasons (FAIL or
    UNDETERMINED causes) and flags (ACCEPT_WITH_FLAG notes for the receipt).

    `look` is the run's look: a cartoon look grades the corr test against
    sync_check.CARTOON_CORR_FLOOR (0.35) instead of 0.40. Nothing else moves,
    so wrong audio and the trial B take still FAIL for a cartoon look."""
    g, v = SC.grade(m, look), SC.verdict(m, sung, look)
    hard = list(m.get("hard_defects") or [])      # defects a person saw: garbled face, hand over mouth
    if hard and g != SC.UNMEASURABLE:
        v = FAIL
    # N-117: a face that mouths someone else's part fails the Right Voice check.
    wrong_voice = m.get("wrong_voice_mouthed") is True
    if wrong_voice and g != SC.UNMEASURABLE:
        v = FAIL
    why = ["LIP_%s" % t.upper() for t in SC.fail_tests(m, look)] if g == SC.NOT_SYNCED else []
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
    if wrong_voice:
        why = why + [WRONG_VOICE_MOUTHED]
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
             advisory=None, acquire=None, person_verdict=None, look=None,
             eye_record=None, landed=None, emotion=None, intensity=2,
             emotion_check=None):
    """Orchestrate at most MAX_TRIES (2) paid omnihuman-2-0 jobs for
    one segment. Injected providers, so mocked runs cost $0.

    generate(PROVIDER, input_spec) -> clip
    measure_clip(clip) -> measurement from measure(), or the Unmeasured
        exception from mouth_landmarks (turned into an UNMEASURABLE verdict).
        The measurement may carry `hard_defects` (a person saw a garbled face,
        text across the chest, a hand over the mouth): that makes it a FAIL.
    sung: this line is SUNG. A sung line that is not PASS is UNDETERMINED and
        stops there (held for a person, no automatic paid redo).
    look: the run's look, passed to judge: a cartoon look grades the corr test
        against CARTOON_CORR_FLOOR (0.35). Omitted = today's 0.40 everywhere.
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

    person_verdict: "DEFECT" when a person marked a visible defect on this
        segment (defects file or receipt field). Without it, or a person-seen
        `hard_defects` entry, NO try 2 runs, whatever the checker said.
    eye_record: N-113's record {sheet, who, verdict} for the kept take (a
        4-frame-per-second contact sheet a reader looked at). A PASS with no
        record is refused by qc_check, so the row carries it.
    landed: G-WIDE-01's landed facts {max_face_h_pct, camera_move_px}; a take
        whose singer never comes close refuses LIPSYNC_NO_CLOSEUP at qc_check.
    Every verdict stops after try 1 unless a person called a defect: a second
    paid job would not change a checker verdict. Returns the receipt row.
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
    attempts = [_attempt(spec1, generate, measure_clip, sung, advisory, acquire,
                         line_id, look=look)]
    flag = None
    # N-118: the Emotion Hold runs after the take; on a pain line at intensity
    # 2 or 3 a drift is a person-level defect, so the second take is bought
    # inside the two-try rule (lever 3: two takes of every pain-line piece).
    hold = None
    if callable(emotion_check):
        try:
            hold = emotion_check(attempts[0]["clip"])
        except Exception as exc:          # a check that cannot run is reported
            hold = {"verdict": "UNMEASURABLE", "detail": str(exc)}
    elif emotion:
        # N-118: a tagged line with no supplier has NOT had its Emotion Hold.
        # A check that could not run is never a pass; the row says so and the
        # join refuses a take that claims one it never had.
        hold = {"verdict": "UNMEASURABLE",
                "detail": "no Emotion Hold supplier for a %r line at intensity "
                          "%s; no take enters the timeline unchecked" % (emotion, intensity)}
    drifted = isinstance(hold, dict) and hold.get("verdict") not in (None, "PASS", "OK")
    pain = emotion in PAIN_EMOTIONS and int(intensity or 1) >= PAIN_DRIFT_MAJOR_INTENSITY
    person = (person_verdict
              or ("DEFECT" if attempts[0]["judge"].get("hard_defects") else None)
              or ("DEFECT" if (drifted and pain) else None))
    if person:
        spec2 = dict(retry_input or {}, source_image=source_image, **{"try": 2})
        ok, why = LP.retry_allowed(
            usable_take=False, person_verdict=person, jobs=int(prior_jobs) + 1,
            input_fingerprint=_fp(spec2), prior_fingerprints=[_fp(spec1)])
        if ok and retry_input:
            attempts.append(_attempt(spec2, generate, measure_clip, sung, advisory,
                                     acquire, line_id, look=look))
        else:
            flag = "RETRY_REFUSED (%s): try 2 needs a changed input; kept try 1" % (why or LP.SAME_INPUT)
    row = _row(line_id, attempts, flag, make_strip, prior_jobs,
               eye_record=eye_record, landed=landed)
    row["emotion_hold"] = hold
    if drifted:
        row["reasons"] = list(row.get("reasons") or []) + [EMOTION_DRIFT]
        if pain or isinstance(hold, dict) and hold.get("severity") == "MAJOR":
            row["verdict"] = FAIL if row.get("verdict") != KEPT else KEPT
    return row


def _fp(spec):
    return repr(sorted((k, repr(v)) for k, v in spec.items() if k != "try"))


def _attempt(spec, generate, measure_clip, sung, advisory, acquire, line_id, look=None):
    # every paid submit goes through the KIE pacing bucket (20 new jobs / 10 s)
    clip = _LG.kie_request(lambda: generate(PROVIDER, spec),
                           "lipsync %s try %s" % (line_id, spec.get("try")),
                           generation=True, acquire=acquire)
    try:
        j = judge(measure_clip(clip), sung, look)
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
    return {"provider": PROVIDER, "model": LIP_MODEL, "input": spec, "clip": clip,
            "judge": j, "advisory_event_sync": adv}


def _row(line_id, attempts, flag, make_strip, prior_jobs=0,
         eye_record=None, landed=None):
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
            # N-113: the take's eye record (sheet, who looked, verdict). A take
            # with no record does not enter the timeline (qc_check refuses).
            "eye_record": eye_record,
            # G-WIDE-01: the landed close-up facts a reader recorded.
            "landed": landed,
            "numbers": {k: j[k] for k in (
                "offset_s", "lag_frames", "corr", "control_corr", "margin", "pct")}}


LIPSYNC_VIEW = "lipsync-closeup"
LIPSYNC_REF_MISSING = "LIPSYNC_CLOSEUP_MISSING"
LIPSYNC_MOUTH_BAD = "LIPSYNC_CLOSEUP_MOUTH_NOT_CLEAR"

# --- G-WIDE-01: the singer must be seen close, or the take refuses -------------
LIPSYNC_NO_CLOSEUP = "LIPSYNC_NO_CLOSEUP"
CLOSEUP_FACE_H_PCT = 25.0       # of frame height, at some point in the take
WIDE_CAMERA_MOVE = 0.0          # camera_move_px/frame above this = not "left the wide"
EYE_RECORD_FIELDS = ("sheet", "who", "verdict")
LIP_TAKE_NOT_EYE_CHECKED = "LIP_TAKE_NOT_EYE_CHECKED"

# --- N-117: the Right Voice check; N-118: the Emotion Hold ---------------------
WRONG_VOICE_MOUTHED = "WRONG_VOICE_MOUTHED"
EMOTION_DRIFT = "EMOTION_DRIFT"
PAIN_EMOTIONS = frozenset({"pain", "worry", "exhaustion", "resolve"})
PAIN_DRIFT_MAJOR_INTENSITY = 2


def closeup_landed(take):
    """G-WIDE-01: did the landed take ever show the singer close?

    ``take`` is the per-take facts a reader recorded from the contact sheet:
    ``max_face_h_pct`` (largest singer face over the whole take, percent of
    frame height) and ``camera_move_px`` (largest per-frame camera displacement).
    A take whose face never reaches CLOSEUP_FACE_H_PCT, or whose camera never
    leaves the wide, is a wide take. Missing numbers are a refusal, never a pass.
    """
    take = take if isinstance(take, dict) else {}
    h = take.get("max_face_h_pct")
    move = take.get("camera_move_px")
    if not (_num(h) and _num(move)):
        return {"pass": False, "reason_code": LIPSYNC_NO_CLOSEUP,
                "detail": "no measured face height and camera move on this take"}
    close = float(h) >= CLOSEUP_FACE_H_PCT
    moved = float(move) > WIDE_CAMERA_MOVE
    return {"pass": close or moved, "reason_code": "LIPSYNC_CLOSEUP_OK" if close or moved
            else LIPSYNC_NO_CLOSEUP,
            "max_face_h_pct": float(h), "camera_move_px": float(move),
            "detail": "" if close or moved else
            "singer face peaks at %.1f%% of frame height (< %.0f%%) and the "
            "camera never leaves the wide; one close-up job per sung line, "
            "never one wide job for many faces" % (float(h), CLOSEUP_FACE_H_PCT)}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


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


def eye_recorded(row):
    """N-113: is this take's eye record complete? A sheet at 4 frames per second
    that a reader looked at, who looked, and the verdict. A scan is never one."""
    rec = row.get("eye_record") if isinstance(row, dict) else None
    if not isinstance(rec, dict):
        return False
    return all(isinstance(rec.get(k), str) and rec[k].strip() for k in EYE_RECORD_FIELDS)


def qc_check(rows):
    """Receipt-level check: every lip clip has a PASS or ACCEPT_WITH_FLAG row
    with numbers; or a flagged KEPT_BEST_OF_2 row (Trevor's keep-best-of-2 rule)
    that carries numbers, the flag text and a mouth-strip path. More than 2 paid
    jobs on a segment always fails. An UNDETERMINED or UNMEASURABLE row (a sung
    line) clears only when a person looked at a mouth strip and wrote
    person_verdict = "PASS" on the row. A KEPT_BEST row (lip_process: reuse-first
    take, "KEPT_BEST (UNDETERMINED, sung)" or a flagged spoken row) passes when
    it carries numbers and a mouth-strip path.

    N-113: a lip-sync take enters the timeline only with an eye record (a
    4-frame-per-second contact sheet, who looked, the verdict). G-WIDE-01: a
    take whose singer never comes close refuses LIPSYNC_NO_CLOSEUP."""
    def ok(r):
        if not eye_recorded(r):
            return False
        landed = r.get("landed")
        if isinstance(landed, dict) and not closeup_landed(landed)["pass"]:
            return False
        if str(r.get("tag", "")).startswith(LP.KEPT_BEST):   # LSP001 reuse-first row
            return not LP.qc_rows([r])["failed"]
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
    no_eye = [r.get("line_id") for r in rows if not eye_recorded(r)]
    no_close = [r.get("line_id") for r in rows
                if isinstance(r.get("landed"), dict)
                and not closeup_landed(r["landed"])["pass"]]
    # The specific refusal wins over the generic one (N-113 / G-WIDE-01): a
    # take with no eye record is LIP_TAKE_NOT_EYE_CHECKED, not LIP_SYNC_GATE_FAILED.
    code = (LIP_TAKE_NOT_EYE_CHECKED if no_eye else
            LIPSYNC_NO_CLOSEUP if no_close else
            "LIP_SYNC_GATE_FAILED" if bad else None)
    return {"pass": not bad and not no_eye and not no_close, "failed_lines": bad,
            "held_for_person": held, "no_eye_record": no_eye,
            "no_closeup": no_close, "reason_code": code}


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
