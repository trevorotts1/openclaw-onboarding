#!/usr/bin/env python3
"""script_approval.stage: the automatic wiring. `factory.py next` calls run_stage
when the `music` stage is next; `factory.py script-reply` calls it with the client's reply.

run_stage(run_dir, deliver, reply=None, apply_edit=None, checks=None, context=None)
  -> {"outcome", ...}
  outcome "go"      : recorded card answer No, or approved for these lyrics.
  outcome "waiting" : presentation sent (once) and the run is paused; no song
                      generation may start. A question or an acknowledgement for
                      the conversation rides in "messages".
  outcome "blocked" : story or lyric checks failed (nothing sent), the client
                      edit did not re-check, or the saved approval data is
                      missing/corrupt -- an explicit recoverable UNKNOWN
                      (approval_state "unknown", reason APPROVAL_STATE_UNKNOWN),
                      never permission. Its "problems" carry the one concrete
                      question that recovers it; a reply to that question records
                      the missing decision by stable id and the run continues.
The card answers live in `$RUN/card-answers.json`, read by STABLE QUESTION ID
with a schema version (D17): reordering the questions can never turn a saved
Yes into a No, and missing/corrupt data is unknown, never "not asked".
The story check reads the run's recorded purpose from `$RUN/control/method.json`
(the intake card writes it) and hands it to the story validator, so a lesson,
testimonial or sales run is judged by its own purpose's rules. The purpose is
never inferred from the script's text, and a run with no readable purpose is
judged exactly as before.
The script lives in `$RUN/creative/script.json`: {"title", "story": [[act, [lines]]],
"sheet": [{"tag", "lines"}], "lyrics": "<exact text sent to the music request>"}.
`deliver(text)` is the client-delivery sink; it raises if the message did not go out.
Stdlib only; no network here (the sink does the sending).
"""
from __future__ import annotations

import json
import os

try:
    from . import approval_events as AE
    from . import card_answers
    from . import script_approval as SA
except ImportError:  # loaded as a plain module
    import approval_events as AE  # type: ignore
    import card_answers  # type: ignore
    import script_approval as SA  # type: ignore

ANSWERS = card_answers.ANSWERS
SCRIPT = os.path.join("creative", "script.json")
METHOD = os.path.join("control", "method.json")     # the run's recorded purpose


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _purpose(run_dir, SARC):
    """The ONE purpose this run recorded in ``control/method.json``, validated
    against the story validator's own accepted set; None otherwise.

    Only a recorded purpose is ever used. A run with no method record, an
    unreadable one, or a value the validator does not know carries no purpose
    and is judged exactly as before -- the purpose is never guessed from the
    script's text, so a lesson, testimonial or sales variant gets its rules
    solely because the card recorded what the run is for.
    """
    method = _load(os.path.join(run_dir, METHOD))
    value = method.get("purpose") if isinstance(method, dict) else None
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if value in SARC.METHOD_PURPOSES else None


def _problems(run_dir):
    """The story and lyric checks the runbook runs (story_arc, lyric_writer); [] = both pass."""
    import sys
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    out = []
    story = _load(os.path.join(run_dir, "creative", "story.json"))
    lyr = _load(os.path.join(run_dir, "creative", "lyrics.json"))
    if story is None or lyr is None:
        return ["creative/story.json and creative/lyrics.json must exist and be readable"]
    from story_arc import story_arc as SARC  # noqa: PLC0415
    from lyric_writer import lyric_writer as LW  # noqa: PLC0415
    r = SARC.validate_story(story, purpose=_purpose(run_dir, SARC))
    if r["outcome"] != "ok":
        out.append("story: %s" % r["reason_code"])
    brief = _load(os.path.join(run_dir, "brief.json"))
    if isinstance(lyr, dict) and isinstance(lyr.get("brief"), dict) and "lines" not in lyr \
            and isinstance(lyr.get("lyrics"), list):
        r = LW.validate_campaign(lyr)
    elif isinstance(lyr, dict) and "lines" in lyr:
        r = LW.validate_lyrics(lyr.get("lines"), lyr.get("brief") or brief)
    else:
        r = LW.validate_lyrics(lyr if isinstance(lyr, list) else None, brief)
    if r["outcome"] != "ok":
        out.append("lyrics: %s" % r["reason_code"])
    return out


def _doc(run_dir):
    d = _load(os.path.join(run_dir, SCRIPT))
    if not isinstance(d, dict) or not d.get("sheet"):
        return None
    lyr = d.get("lyrics") or "\n".join(l for s in d["sheet"] for l in s.get("lines") or [])
    return d.get("title") or "Your song", [tuple(a) for a in d.get("story") or []], \
        d["sheet"], lyr, d.get("elements") or {
            k: d.get(k) for k in ("opening_spoken_hook", "earned_song_hook", "song_hook",
                                  "hook_true_at", "becomes_true_at", "true_at_beat",
                                  "erm_drop", "hero_shift", "cta") if d.get(k)}


def _send(run_dir, deliver, msgs):
    for m in msgs:
        deliver(m)
    SA.mark_sent(run_dir)


def _unknown(state_detail):
    return {"outcome": "blocked", "reason": "approval-state-unknown",
            "reason_code": AE.UNKNOWN_REASON, "approval_state": "unknown",
            "unknown": {"detail": state_detail}, "recoverable": True,
            "problems": [SA.UNKNOWN_QUESTION], "messages": []}


def _recover_answer(reply):
    """The reply to the one recovery question: option 1 (approve first) or
    option 2 (just make it). Only the client's own words can record it."""
    if AE.is_affirmative(reply):
        return 1
    import re
    if re.search(r"\b(no|nope|dont|don't|skip|make it|just make)\b", str(reply or "").lower()):
        return 2
    return None


def run_stage(run_dir, deliver, reply=None, apply_edit=None, checks=None, context=None):
    st = card_answers.load(run_dir)
    dec = card_answers.decision(st, SA.QUESTION_ID)
    if dec["state"] == card_answers.UNKNOWN:
        if reply is None:
            return _unknown(dec.get("detail"))
        n = _recover_answer(reply)          # the client answered the one question
        if n is None:
            return _unknown(dec.get("detail"))
        st = card_answers.repair_decision(run_dir, SA.QUESTION_ID, n, text=str(reply))
        dec = card_answers.decision(st, SA.QUESTION_ID)
        if dec["state"] == card_answers.UNKNOWN:
            return _unknown(dec.get("detail"))
    if dec["state"] != card_answers.YES:
        return {"outcome": "go", "reason": "script-approval-not-asked", "messages": []}

    rec = SA.record_for(run_dir)
    if AE.is_unknown_record(rec):
        return _unknown(rec.get("unknown_detail"))
    doc = _doc(run_dir)
    if doc is None:
        return {"outcome": "blocked", "problems": ["creative/script.json is missing or has no sheet"]}
    title, story, sheet, lyrics, elements = doc
    check = checks or (lambda s, h: _problems(run_dir))
    if rec and rec.get("status") == "approved" and SA.check_script_approval(rec, lyrics) is None:
        return {"outcome": "go", "reason": "approved", "messages": []}
    if rec is None:                                       # first time: checks, record, send, pause
        problems = list(check(story, sheet))
        if problems:
            return {"outcome": "blocked", "problems": problems}
        msgs = SA.request_approval(run_dir, title, story, sheet, lyrics,
                                   context=context, elements=elements)
        _send(run_dir, deliver, msgs)
        return {"outcome": "waiting", "reason": "script-sent", "messages": msgs}
    if reply is None:                                     # resume: stay paused; re-send only if never delivered
        if not rec.get("sent"):
            msgs = SA.request_approval(run_dir, title, story, sheet, lyrics,
                                       maker=rec.get("maker"), context=context,
                                       elements=elements)
            _send(run_dir, deliver, msgs)
            return {"outcome": "waiting", "reason": "script-sent", "messages": msgs}
        return {"outcome": "waiting", "reason": "awaiting-client-reply", "messages": []}
    r = SA.handle_reply(run_dir, reply, title, story, sheet, lyrics,
                        apply_edit or (lambda rp, s, h: _no_edit(run_dir, rp, s, h)),
                        check, context=context)
    if r.get("approval_state") == "unknown":
        return _unknown("the approval record is missing or corrupt")
    if r["status"] == "approved":
        return {"outcome": "go", "reason": "approved", "messages": r["messages"]}
    if r["problems"]:
        return {"outcome": "blocked", "problems": r["problems"]}
    if r.get("edited"):                    # edit applied: keep it on disk, re-send
        d = _load(os.path.join(run_dir, SCRIPT))
        d.update(story=[list(a) for a in r["story"]], sheet=r["sheet"], lyrics=r["lyrics"])
        with open(os.path.join(run_dir, SCRIPT), "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        _send(run_dir, deliver, r["messages"])
        return {"outcome": "waiting", "reason": "edit-resent", "messages": r["messages"]}
    msgs = r["messages"]                   # one concrete question, or an acknowledgement
    for m in msgs:
        deliver(m)
    return {"outcome": "waiting",
            "reason": "awaiting-client-reply" if not r.get("asked") else "question-asked",
            "messages": msgs}


def _no_edit(run_dir, reply, story, sheet):
    """CLI default: the agent applies the client's edit to creative/script.json, then re-runs."""
    d = _doc(run_dir)
    return d[1], d[2], d[3]
