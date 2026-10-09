#!/usr/bin/env python3
"""script_approval.stage: the automatic wiring. `factory.py next` calls run_stage
when the `music` stage is next; `factory.py script-reply` calls it with the client's reply.

run_stage(run_dir, deliver, reply=None, apply_edit=None, checks=None) -> {"outcome", ...}
  outcome "go"      : not asked for (card answer No / no card file), or approved for these lyrics.
  outcome "waiting" : script sent (once) and the run is paused; no song generation may start.
  outcome "blocked" : story or lyric checks failed (nothing sent) or the client edit did not re-check.
The card answers live in `$RUN/card-answers.json` (the `answers` list of intake_card.conversation).
The script lives in `$RUN/creative/script.json`: {"title", "story": [[act, [lines]]],
"sheet": [{"tag", "lines"}], "lyrics": "<exact text sent to the music request>"}.
`deliver(text)` is the client-delivery sink; it raises if the message did not go out.
Stdlib only; no network here (the sink does the sending).
"""
from __future__ import annotations

import json
import os

try:
    from . import script_approval as SA
except ImportError:  # loaded as a plain module
    import script_approval as SA  # type: ignore

ANSWERS = "card-answers.json"
SCRIPT = os.path.join("creative", "script.json")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _questions():
    import sys
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    from choice_card.intake_card import intake_card as IC  # noqa: PLC0415
    return IC.QUESTIONS


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
    r = SARC.validate_story(story)
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
    return d.get("title") or "Your song", [tuple(a) for a in d.get("story") or []], d["sheet"], lyr


def _send(run_dir, deliver, msgs):
    for m in msgs:
        deliver(m)
    SA.mark_sent(run_dir)


def run_stage(run_dir, deliver, reply=None, apply_edit=None, checks=None):
    answers = _load(os.path.join(run_dir, ANSWERS))
    if not isinstance(answers, list) or not SA.wants_approval(answers, _questions()):
        return {"outcome": "go", "reason": "script-approval-not-asked", "messages": []}
    doc = _doc(run_dir)
    if doc is None:
        return {"outcome": "blocked", "problems": ["creative/script.json is missing or has no sheet"]}
    title, story, sheet, lyrics = doc
    check = checks or (lambda s, h: _problems(run_dir))
    rec = SA.record_for(run_dir)
    if rec and rec.get("status") == "approved" and SA.check_script_approval(rec, lyrics) is None:
        return {"outcome": "go", "reason": "approved", "messages": []}
    if rec is None:                                       # first time: checks, record, send, pause
        problems = list(check(story, sheet))
        if problems:
            return {"outcome": "blocked", "problems": problems}
        msgs = SA.request_approval(run_dir, title, story, sheet, lyrics)
        _send(run_dir, deliver, msgs)
        return {"outcome": "waiting", "reason": "script-sent", "messages": msgs}
    if reply is None:                                     # resume: stay paused; re-send only if never delivered
        if not rec.get("sent"):
            msgs = SA.request_approval(run_dir, title, story, sheet, lyrics)
            _send(run_dir, deliver, msgs)
            return {"outcome": "waiting", "reason": "script-sent", "messages": msgs}
        return {"outcome": "waiting", "reason": "awaiting-client-reply", "messages": []}
    r = SA.handle_reply(run_dir, reply, title, story, sheet, lyrics,
                        apply_edit or (lambda rp, s, h: _no_edit(run_dir, rp, s, h)), check)
    if r["status"] == "approved":
        return {"outcome": "go", "reason": "approved", "messages": r["messages"]}
    if r["problems"]:
        return {"outcome": "blocked", "problems": r["problems"]}
    d = _load(os.path.join(run_dir, SCRIPT))               # edit applied: keep it on disk, re-send
    d.update(story=[list(a) for a in r["story"]], sheet=r["sheet"], lyrics=r["lyrics"])
    with open(os.path.join(run_dir, SCRIPT), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    _send(run_dir, deliver, r["messages"])
    return {"outcome": "waiting", "reason": "edit-resent", "messages": r["messages"]}


def _no_edit(run_dir, reply, story, sheet):
    """CLI default: the agent applies the client's edit to creative/script.json, then re-runs."""
    d = _doc(run_dir)
    return d[1], d[2], d[3]
