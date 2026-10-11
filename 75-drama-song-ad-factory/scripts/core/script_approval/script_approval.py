#!/usr/bin/env python3
"""script_approval: SCRIPT APPROVAL card question, the script message, and the gate.

The script is the written story plus the full song lyrics. When the client
answers Yes to the SCRIPT APPROVAL question, the run (1) sends this message once
the story and lyric sheet have passed their checks, (2) PAUSES: the song
generation (Suno, music spend) refuses until the client approves, (3) applies a
client edit, re-checks, re-sends. No: nothing here is called, behaviour is as before.

The record lives in the run (``$RUN/creative/script-approval.json``) and rides the
music request as ``request["script_approval"]``:
    {"required": true, "status": "pending"|"approved", "lyrics_sha": "<sha256>",
     "sent": true once the script message reached the client}
``check_script_approval`` is the gate, called by kie_dispatch.dispatch (music jobs)
and song_dispatch.run_takes. Required and not approved for THESE lyrics = refuse.

Stdlib only. No network: this module builds text and records; it never sends.
"""
from __future__ import annotations

import hashlib
import json
import os

TELEGRAM_LIMIT = 4000
REASON = "SCRIPT_NOT_APPROVED"
#: WW-28: the maker may not approve their own script. An approval whose
#: approver is the same person as the maker is refused -- the review is
#: independent or it did not happen.
SELF_APPROVAL = "SELF_APPROVAL"
_APPROVE = ("yes", "y", "approve", "approved", "go", "ok", "okay", "looks good", "start")
RECORD_NAME = os.path.join("creative", "script-approval.json")
INSTRUCTION = ('Reply "approve" to make the song, or tell me what to change '
               'and I will fix it and send it again.')


def lyrics_sha(lyrics):
    return hashlib.sha256((lyrics or "").strip().encode("utf-8")).hexdigest()


def wants_approval(answers, questions):
    """True when the client picked option 1 (Yes) on the SCRIPT APPROVAL question."""
    for q, a in zip(questions, answers):
        if q.get("id") == "script":
            return a.get("n") == 1
    return False


def render_script(title, story, sheet):
    """Readable plain text: title, the story a few lines per act, then the full
    lyrics with section labels. story = [(act name, [lines])]; sheet =
    [{"tag", "lines"}] (the lyric sheet). No Markdown, so no sender strips it."""
    out = ["Here is the script for \"%s\". Nothing is made until you approve it." % title, "",
           "THE STORY"]
    for act, lines in story:
        out += ["", act.upper()] + list(lines)
    out += ["", "THE SONG LYRICS"]
    for s in sheet:
        if str(s["tag"]).strip().lower() == "end":
            continue
        out += ["", "[%s]" % str(s["tag"]).strip("[] ")] + list(s.get("lines") or [])
    out += ["", INSTRUCTION]
    return "\n".join(out)


def _split(text, limit=TELEGRAM_LIMIT):
    """Pack blank-line blocks into messages <= limit (a block never splits)."""
    msgs, cur = [], ""
    for b in text.split("\n\n"):
        cand = cur + "\n\n" + b if cur else b
        if len(cand) > limit and cur:
            msgs.append(cur)
            cur = b
        else:
            cur = cand
    return msgs + ([cur] if cur else [])


def _path(run_dir):
    return os.path.join(run_dir, RECORD_NAME)


def _save(run_dir, rec):
    p = _path(run_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
    return rec


def record_for(run_dir):
    """The run's record, or None. Pass it as request["script_approval"]."""
    try:
        with open(_path(run_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def record_near(*dirs):
    """First record found among the given run folders (and each folder's parent,
    so a `$RUN/music` save dir finds `$RUN`). Lets the gates find the record
    themselves; nothing passes it by hand."""
    for d in dirs:
        for c in ((d, os.path.dirname(os.path.abspath(d))) if d else ()):
            rec = record_for(c)
            if rec is not None:
                return rec
    return None


def mark_sent(run_dir):
    """The script message reached the client: a resume must not send it again."""
    rec = record_for(run_dir) or {}
    return _save(run_dir, dict(rec, sent=True))


def request_approval(run_dir, title, story, sheet, lyrics, maker=None):
    """Call AFTER the story and lyric sheet pass their checks. Records
    pending (the pause) and returns the messages to send the client.

    WW-28: ``maker`` is the party who authored the script. It is recorded so an
    approval that names the maker as its own approver is refused by the gate."""
    rec = {"required": True, "status": "pending", "lyrics_sha": lyrics_sha(lyrics),
           "sent": False}
    if maker is not None:
        rec["maker"] = str(maker)
    _save(run_dir, rec)
    return _split(render_script(title, story, sheet))


def handle_reply(run_dir, reply, title, story, sheet, lyrics, apply_edit, recheck,
                 approved_by=None):
    """Client reply -> {"status", "messages", "problems", ...}.

    approve -> status approved, bound to the current lyrics.
    anything else is an edit: apply_edit(reply, story, sheet) -> (story, sheet,
    lyrics); recheck(story, sheet) -> [problems]. Clean -> re-sent, still pending.
    Problems -> nothing sent, still pending (the caller fixes and calls again)."""
    sent = bool((record_for(run_dir) or {}).get("sent"))
    if reply.strip().lower() in _APPROVE:
        # WW-28: record who approved, and keep the maker, so the gate can refuse
        # an approval the maker gave their own script.
        prior = record_for(run_dir) or {}
        rec = {"required": True, "status": "approved", "lyrics_sha": lyrics_sha(lyrics)}
        if prior.get("maker") is not None:
            rec["maker"] = prior["maker"]           # keep the maker the request recorded
        if approved_by is not None:
            rec["approved_by"] = str(approved_by)
        _save(run_dir, rec)
        return {"status": "approved", "messages": ["Approved. Making the song now."], "problems": []}
    story, sheet, lyrics = apply_edit(reply, story, sheet)
    problems = list(recheck(story, sheet))
    if problems:
        _save(run_dir, {"required": True, "status": "pending", "lyrics_sha": lyrics_sha(lyrics),
                        "sent": sent})
        return {"status": "pending", "messages": [], "problems": problems,
                "story": story, "sheet": sheet, "lyrics": lyrics}
    return {"status": "pending", "problems": [], "story": story, "sheet": sheet, "lyrics": lyrics,
            "messages": request_approval(run_dir, title, story, sheet, lyrics)}


def check_script_approval(record, lyrics):
    """The gate. None = go; else the refusal dict. No record, or required false
    = not asked for = today's behaviour. Required: approved for THESE lyrics only."""
    if not isinstance(record, dict) or not record.get("required"):
        return None
    # WW-28: maker self-approval is refused -- an approval by the script's own
    # author is not an independent review.
    maker = str(record.get("maker") or "").strip().lower()
    approver = str(record.get("approved_by") or "").strip().lower()
    if record.get("status") == "approved" and maker and approver and maker == approver:
        return {"reason_code": SELF_APPROVAL,
                "detail": "the maker %r approved their own script; an independent reviewer must "
                          "approve before the song is made" % maker}
    if record.get("status") == "approved" and record.get("lyrics_sha") == lyrics_sha(lyrics):
        return None
    return {"reason_code": REASON,
            "detail": "the client chose to approve the script first and has not approved "
                      "these lyrics; nothing was sent to the music generator"}
