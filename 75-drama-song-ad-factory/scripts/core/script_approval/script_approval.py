#!/usr/bin/env python3
"""script_approval: SCRIPT APPROVAL card question, the script message, and the gate.

The script is the written story plus the full song lyrics. When the client
answers Yes to the SCRIPT APPROVAL question, the run (1) sends the presentation
once the story and lyric sheet have passed their checks, (2) PAUSES: the song
generation (Suno, music spend) refuses until the client approves, (3) applies a
client edit, re-checks, re-sends. No: nothing here is called, behaviour is as
before.

The presentation shows the opening spoken hook, the story, the script, the full
lyrics, the earned song hook and where it becomes true, the ERM Drop, the Hero
Shift and the CTA, each labelled with its displayed revision, and offers
separate script/lyrics approvals plus the combined "Approve both". Decisions are
revision-aware events (see approval_events): every approval binds to tenant,
run, artifact kind, revision/hash, requesting conversation, approving identity
and timestamp; a change invalidates only the affected approvals and their
descendants; missing or corrupt approval data is an explicit UNKNOWN, never
permission; replayed replies re-acknowledge the existing decision without
duplicate work. Ordinary unambiguous language approves -- no magic words --
while an ambiguous reply asks exactly one concrete question, and the system
never answers the client's creative approval on their behalf.

The record lives in the run (``$RUN/creative/script-approval.json``) and rides
the music request as ``request["script_approval"]``:
    {"required": true, "status": "pending"|"approved", "lyrics_sha": "<sha256>",
     "sent": true once the script message reached the client}
``check_script_approval`` is the gate, called by kie_dispatch.dispatch (music
jobs) and song_dispatch.run_takes. Required and not approved for THESE lyrics =
refuse.

Stdlib only. No network: this module builds text and records; it never sends.
"""
from __future__ import annotations

import hashlib
import json
import os

try:
    from . import approval_events as AE
    from . import card_answers
except ImportError:  # loaded as a plain module
    import approval_events as AE  # type: ignore
    import card_answers  # type: ignore

TELEGRAM_LIMIT = 4000
REASON = "SCRIPT_NOT_APPROVED"
#: WW-28: the maker may not approve their own script. An approval whose
#: approver is the same person as the maker is refused -- the review is
#: independent or it did not happen.
SELF_APPROVAL = "SELF_APPROVAL"
RECORD_NAME = AE.RECORD_NAME
QUESTION_ID = "script"                      #: the card question's stable id
INSTRUCTION = ('Reply "approve" to approve both, "approve script" or '
               '"approve lyrics" - or tell me what to change and I will fix it '
               'and send it again.')

UNKNOWN_QUESTION = (
    "The saved approval information is missing or unreadable, so I cannot tell "
    "whether you asked to approve the script before the song is made. I will "
    "not guess. Please answer this one question: do you want to read and "
    "approve the script before the song is made?")


# --------------------------------------------------------------------------- #
# hashes: what an approval is bound to
# --------------------------------------------------------------------------- #

def lyrics_sha(lyrics):
    return hashlib.sha256((lyrics or "").strip().encode("utf-8")).hexdigest()


def _spoken(section):
    return str(section.get("delivery") or "spoken").strip().lower() != "sung"


def script_sha(title, story, sheet):
    """The script artifact: the title, the story and the spoken script. Sung
    lyric lines belong to the lyrics artifact, so a lyric line change never
    moves this hash (and never costs the script its approval)."""
    spoken = [{"tag": s.get("tag"), "delivery": s.get("delivery"),
               "lines": list(s.get("lines") or [])}
              for s in sheet if _spoken(s) and str(s.get("tag") or "").strip().lower() != "end"]
    payload = {"title": title, "story": [list(a) for a in story], "sheet": spoken}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# the card question (by stable id -- never by position)
# --------------------------------------------------------------------------- #

def wants_approval(answers, questions=None):
    """True when the client picked option 1 (Yes) on the SCRIPT APPROVAL
    question. The saved answer is read by its STABLE QUESTION ID; a reordered
    question list cannot change the decision (D17). ``questions`` only pairs
    fresh conversation rows with the ids of the very questions that produced
    them; saved rows are never re-read through a positional order."""
    st = answers if (isinstance(answers, dict) and "state" in answers) \
        else card_answers.normalize(answers)
    if st.get("state") != card_answers.OK and questions and isinstance(answers, list):
        rows = card_answers.pair_rows(answers, questions)
        if rows is not None:
            st = card_answers.normalize(rows)
    return card_answers.decision(st, QUESTION_ID)["state"] == card_answers.YES


# --------------------------------------------------------------------------- #
# presentation
# --------------------------------------------------------------------------- #

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


def _first(story, pattern):
    for act, lines in story:
        if pattern.search(str(act)):
            return act, list(lines)
    return None


def _elements(title, story, sheet, elements=None):
    """The named creative elements of the presentation. Explicit script fields
    win; otherwise each element is derived from the actual script lines it
    carries -- never invented. Nothing derivable is shown as explicitly not
    named, never as approval."""
    e = dict(elements or {})
    spoken = [s for s in sheet if _spoken(s) and str(s.get("tag") or "").strip().lower() != "end"]
    sung = [s for s in sheet if not _spoken(s) and str(s.get("tag") or "").strip().lower() != "end"]
    opening = e.get("opening_spoken_hook") or (spoken[0].get("lines") if spoken else None)
    hook = (e.get("earned_song_hook") or e.get("song_hook")
            or next((s.get("lines") for s in sheet
                     if "hook" in str(s.get("tag") or "").lower()), None))
    turn = _first(story, __import__("re").compile(r"turn|change|shift|truth|break|rise|win|found|real|power", __import__("re").I))
    true_at = e.get("hook_true_at") or e.get("becomes_true_at") or e.get("true_at_beat")
    if not true_at and turn:
        true_at = "the story turn \"%s\": %s" % (turn[0], (turn[1] or [""])[0])
    erm = e.get("erm_drop")
    if not erm:
        first_sung = sung[0].get("tag") if sung else None
        erm = ("the first sung line enters exactly as the groove drops, in [%s]" % first_sung
               if first_sung else None)
    hero = e.get("hero_shift")
    if not hero and turn:
        hero = "the turn \"%s\" where the hero changes direction" % turn[0]
    cta = e.get("cta") or (spoken[-1].get("lines") if spoken else None)
    return {"opening": opening, "hook": hook, "true_at": true_at,
            "erm": erm, "hero": hero, "cta": cta}


def _lines_block(label, value):
    if not value:
        return [label, "(not named in this script)"]
    if isinstance(value, (list, tuple)):
        return [label] + list(value)
    return [label, str(value)]


def render_presentation(title, story, sheet, lyrics, elements=None, labels=None):
    """The full approval presentation (spec 5.1 step 5): story, script, lyrics,
    opening spoken hook, earned song hook with where it becomes true, ERM Drop,
    Hero Shift and CTA, the displayed revision labels, and the three approval
    actions (script / lyrics / both)."""
    e = _elements(title, story, sheet, elements)
    out = ["Here is the script for \"%s\". Nothing is made until you approve it." % title, ""]
    out += _lines_block("OPENING SPOKEN HOOK", e["opening"])
    out += ["", "THE STORY"]
    for act, lines in story:
        out += ["", str(act).upper()] + list(lines)
    out += ["", "THE SCRIPT"]
    for s in sheet:
        if str(s.get("tag") or "").strip().lower() == "end" or not _spoken(s):
            continue
        out += ["", "[%s] (spoken)" % str(s["tag"]).strip("[] ")] + list(s.get("lines") or [])
    out += ["", "THE SONG LYRICS"]
    for s in sheet:
        if str(s.get("tag") or "").strip().lower() == "end":
            continue
        out += ["", "[%s] (%s)" % (str(s["tag"]).strip("[] "),
                                   "spoken" if _spoken(s) else "sung")] + list(s.get("lines") or [])
    out += ["", "EARNED SONG HOOK"] + _lines_block("", e["hook"])[1:] \
        + ["Where it becomes true: %s" % (e["true_at"] or "(not named in this script)")]
    out += ["", "ERM DROP"] + _lines_block("", e["erm"])[1:]
    out += ["", "HERO SHIFT"] + _lines_block("", e["hero"])[1:]
    out += ["", "CALL TO ACTION"] + _lines_block("", e["cta"])[1:]
    if labels:
        out += ["", " ".join("%s revision %s (%s)" % (name, rev, sha8)
                             for name, rev, sha8 in labels)]
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


# --------------------------------------------------------------------------- #
# the record
# --------------------------------------------------------------------------- #

def _path(run_dir):
    return AE.record_path(run_dir)


def _save(run_dir, rec):
    return AE.save_record(run_dir, AE.project(rec))


def record_for(run_dir):
    """The run's record, or None when there is none. A record that is present
    but unreadable comes back as an explicit UNKNOWN sentinel (status
    "unknown") -- corrupt data is never 'approval not asked', never permission.
    Pass the result as request["script_approval"]."""
    _state, rec = AE.load_record(run_dir)
    return rec


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
    state, rec = AE.load_record(run_dir)
    if state == "corrupt":
        return rec                                   # unknown stays unknown
    rec = AE.ensure_record(rec)
    rec["sent"] = True
    return _save(run_dir, rec)


def _reply_contract(run_dir):
    """Read current intake provenance; never seed or rewrite the owner run."""
    path = os.path.join(run_dir, "control", "intake-session.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as stream:
        intake = json.load(stream)
    if (not isinstance(intake, dict) or intake.get("schema") != "blackceo.intake-session/v1" or
            not isinstance(intake.get("run_id"), str) or not intake["run_id"]):
        raise ValueError("The modern intake run/source identity cannot be verified.")
    records = list((intake.get("answer_records") or {}).values()) + list(intake.get("events") or [])
    records.append(intake.get("confirmation") or {})
    refs = sorted({r["source_ref"] for r in records if isinstance(r, dict) and
                   isinstance(r.get("source_ref"), str) and r["source_ref"]})
    return {"schema": "blackceo.artifact-reply/v1", "run_id": intake["run_id"], "intake_source_refs": refs}


def reply_provenance(run_dir, record=None, context=None, reply=None):
    """Read-only modern reply admission; actual decisions remain in AE.

    The source reference identifies a NEW client message; presentation_ask_id
    identifies the outgoing whole-package ask. Neither is an intake choice.
    This application protocol does not authenticate unrestricted file writers.
    """
    rec = record if isinstance(record, dict) else (record_for(run_dir) or {})
    ctx = dict(context or {})
    if reply is not None:
        ctx["reply_text_sha"] = hashlib.sha256(str(reply).strip().lower().encode("utf-8")).hexdigest()
    try:
        contract = _reply_contract(run_dir)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"ok": False, "required": True, "reason_code": "ARTIFACT_REPLY_INTAKE_UNREADABLE", "detail": str(exc)}
    if contract:
        rec = dict(rec, reply_contract=contract)
    provenance = AE.reply_context_status(rec, ctx)
    if provenance["ok"] and reply is not None and AE.is_preference_reply(reply):
        return {"ok": False, "required": provenance["required"], "reason_code": "ARTIFACT_REPLY_IS_PREFERENCE",
                "detail": "Choosing to see the work first or giving an intake option is not approval of the presented whole script and lyrics."}
    intent = AE.interpret_reply(reply, rec, ctx).get("intent") if provenance["ok"] else None
    if provenance["ok"] and provenance["required"] and intent in ("approve", "already-approved"):
        # Approval binds the bytes already presented. A provenanced edit is
        # allowed through the existing recheck/re-presentation path instead.
        try:
            with open(os.path.join(run_dir, "creative", "script.json"), encoding="utf-8") as stream:
                doc = json.load(stream)
            sheet = doc["sheet"]
            lyrics = doc.get("lyrics") or "\n".join(line for section in sheet for line in section.get("lines") or [])
            current = {"script": script_sha(doc.get("title") or "Your song", doc.get("story") or [], sheet),
                       "lyrics": lyrics_sha(lyrics)}
            if not sheet or any((rec.get("artifacts", {}).get(kind) or {}).get("sha256") != sha
                                for kind, sha in current.items()):
                raise ValueError("The script or lyrics changed after the presentation.")
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            return {"ok": False, "required": True, "reason_code": "ARTIFACT_REPLY_ARTIFACT_CHANGED",
                    "detail": "Present the current whole script and lyrics before approving them: " + str(exc)}
    return provenance


def request_approval(run_dir, title, story, sheet, lyrics, maker=None,
                     context=None, kinds=("script", "lyrics"), message_id=None,
                     elements=None):
    """Call AFTER the story and lyric sheet pass their checks. Registers the
    presented revisions (a changed revision invalidates only the affected
    approvals and their descendants), records pending (the pause) and returns
    the messages to send the client in the originating conversation.

    WW-28: ``maker`` is the party who authored the script. It is recorded so an
    approval that names the maker as its own approver is refused by the gate."""
    state, rec = AE.load_record(run_dir)
    rec = AE.ensure_record(rec if state == "ok" else None)
    if maker is not None:
        rec["maker"] = str(maker)
    ctx = dict(context or {})
    contract = _reply_contract(run_dir)
    if contract:
        rec["reply_contract"] = contract
    if ctx.get("run_id") or ctx.get("tenant_id"):
        rec["run"] = {"run_id": ctx.get("run_id"), "tenant_id": ctx.get("tenant_id")}
    if ctx.get("conversation_id") or ctx.get("channel"):
        rec["conversation"] = {"conversation_id": ctx.get("conversation_id"),
                               "thread_id": ctx.get("thread_id"),
                               "account_id": ctx.get("account_id"),
                               "channel": ctx.get("channel")}
    AE.register_artifact(rec, "script", script_sha(title, story, sheet))
    AE.register_artifact(rec, "lyrics", lyrics_sha(lyrics))
    AE.open_ask(rec, list(kinds), message_id=message_id)
    rec["status"] = "pending"
    rec["sent"] = False
    AE.project(rec, lyrics_sha(lyrics))
    _save(run_dir, rec)
    labels = []
    for name, kind in (("Script", "script"), ("Lyrics", "lyrics")):
        art = rec["artifacts"].get(kind) or {}
        labels.append((name, art.get("revision"), str(art.get("sha256") or "")[:8]))
    return _split(render_presentation(title, story, sheet, lyrics,
                                      elements=elements, labels=labels))


def _ack_messages(rec, ctx=None):
    """One honest line for the conversation: what is approved, what still waits."""
    approved = AE.approved_kinds(rec)
    art = rec.get("artifacts") or {}
    waiting = [k for k, a in art.items()
               if not AE.active_approval(rec, k, a.get("sha256"))]
    if not waiting:
        return ["Approved. Making the song now."]
    out = []
    if approved:
        out.append("Approved: %s." % _list_words(approved))
    out.append("Still waiting on your approval: %s (revision %s). Reply "
               "\"approve\" for both, or tell me what to change."
               % (_list_words(waiting),
                  ", ".join("%s rev %s" % (k, (art.get(k) or {}).get("revision"))
                            for k in waiting)))
    return out


def _list_words(kinds):
    return ", ".join(str(k).replace("_", " ") for k in kinds)


def _replay_messages(rec, decision):
    """A replayed reply re-acknowledges the existing decision and does no
    duplicate work: no second event, no second continuation."""
    out = ["Already recorded: you approved %s at %s."
           % (_list_words(decision.get("kinds") or []), decision.get("timestamp"))]
    art = rec.get("artifacts") or {}
    waiting = [k for k, a in art.items()
               if AE.active_approval(rec, k, a.get("sha256")) is None]
    if waiting:
        out.append("Still waiting on your approval: %s (revision %s). Reply "
                   "\"approve\" for both, or tell me what to change."
                   % (_list_words(waiting),
                      ", ".join("%s rev %s" % (k, (art.get(k) or {}).get("revision"))
                                for k in waiting)))
    return out


def handle_reply(run_dir, reply, title, story, sheet, lyrics, apply_edit, recheck,
                 approved_by=None, context=None):
    """Client reply -> {"status", "messages", "problems", ...}.

    Ordinary unambiguous language approves (script / lyrics / both); the
    decision is persisted transactionally with its acknowledgement and one
    continuation, and a replayed reply re-acknowledges the existing decision
    without duplicate work or a new run. Anything else is an edit: apply_edit
    (reply, story, sheet) -> (story, sheet, lyrics); recheck(story, sheet) ->
    [problems]. Clean -> re-sent, still pending. Problems -> nothing sent, still
    pending (the caller fixes and calls again). An ambiguous reply asks exactly
    one concrete question; missing/corrupt data is an explicit unknown."""
    ctx = dict(context or {})
    if approved_by is not None:
        ctx["approved_by"] = str(approved_by)
    ctx["reply_text"] = str(reply or "")
    ctx["reply_text_sha"] = hashlib.sha256(
        str(reply or "").strip().lower().encode("utf-8")).hexdigest()
    state, rec = AE.load_record(run_dir)
    if state == "corrupt":
        return {"status": "unknown", "approval_state": "unknown",
                "reason_code": AE.UNKNOWN_REASON, "messages": [UNKNOWN_QUESTION],
                "problems": [], "asked": UNKNOWN_QUESTION}
    rec = AE.ensure_record(rec)
    prior_sent = bool(rec.get("sent"))
    provenance = reply_provenance(run_dir, rec, ctx, reply)
    intent = AE.interpret_reply(reply, rec, ctx).get("intent") if provenance["ok"] else None
    if provenance["ok"] and provenance["required"] and intent in ("approve", "already-approved"):
        actual = {"script": script_sha(title, story, sheet), "lyrics": lyrics_sha(lyrics)}
        if any((rec.get("artifacts", {}).get(k) or {}).get("sha256") != sha for k, sha in actual.items()):
            provenance = {"ok": False, "required": True, "reason_code": "ARTIFACT_REPLY_ARTIFACT_CHANGED",
                          "detail": "The reply payload differs from the whole script and lyrics that were presented."}
    if not provenance["ok"] or AE.is_preference_reply(reply):
        detail = (provenance["detail"] if not provenance["ok"] else
                  "Choosing to see the work first is an approval preference, not approval of this whole script and lyrics.")
        return {"status": "pending", "approval_state": "unknown",
                "reason_code": provenance["reason_code"] if not provenance["ok"] else "ARTIFACT_REPLY_IS_PREFERENCE",
                "messages": [detail], "problems": [], "asked": detail}

    replay = AE.find_replay(rec, ctx)
    if replay is not None:
        AE.project(rec, lyrics_sha(lyrics))
        _save(run_dir, rec)
        return {"status": rec["status"], "duplicate": True, "decision": replay,
                "messages": _replay_messages(rec, replay), "problems": []}

    verdict = AE.interpret_reply(reply, rec, ctx)
    if verdict["intent"] == "approve":
        res = AE.record_decision(rec, verdict["kinds"], ctx)
        AE.close_decided_asks(rec, verdict["kinds"])
        AE.project(rec, lyrics_sha(lyrics))
        _save(run_dir, rec)
        return {"status": rec["status"], "decision": res, "duplicate": res["duplicate"],
                "messages": _ack_messages(rec, ctx), "problems": []}
    if verdict["intent"] == "already-approved":
        AE.project(rec, lyrics_sha(lyrics))
        _save(run_dir, rec)
        return {"status": rec["status"], "messages": _ack_messages(rec, ctx),
                "problems": []}
    if verdict["intent"] in ("ambiguous", "unseen", "foreign", "preference", "unproven"):
        return {"status": "pending", "messages": [verdict["question"]], "problems": [],
                "asked": verdict["question"]}

    # not an approval: the words are an edit request (legacy behaviour)
    story, sheet, lyrics = apply_edit(reply, story, sheet)
    problems = list(recheck(story, sheet))
    if problems:
        rec["sent"] = prior_sent
        AE.project(rec, lyrics_sha(lyrics))
        _save(run_dir, rec)
        return {"status": "pending", "messages": [], "problems": problems,
                "story": story, "sheet": sheet, "lyrics": lyrics}
    msgs = request_approval(run_dir, title, story, sheet, lyrics,
                            maker=rec.get("maker"), context=context)
    return {"status": "pending", "problems": [], "edited": True,
            "story": story, "sheet": sheet, "lyrics": lyrics, "messages": msgs}


def check_script_approval(record, lyrics):
    """The gate. None = go; else the refusal dict. No record, or required false
    = not asked for = today's behaviour. Required: approved for THESE lyrics
    only. Missing or corrupt approval data is an explicit UNKNOWN refusal --
    never permission, never a silent go."""
    if record is None:
        return None
    if not isinstance(record, dict):
        return {"reason_code": AE.UNKNOWN_REASON,
                "detail": "the approval record is not readable data; refusing to treat "
                          "it as permission"}
    if not record.get("required"):
        return None
    if AE.is_unknown_record(record):
        return {"reason_code": AE.UNKNOWN_REASON,
                "detail": record.get("unknown_detail")
                or "the approval record is missing or corrupt; this is an explicit "
                   "unknown, not permission"}
    # WW-28: maker self-approval is refused -- an approval by the script's own
    # author is not an independent review.
    maker = str(record.get("maker") or "").strip().lower()
    approver = str(record.get("approved_by") or "").strip().lower()
    if record.get("status") == "approved" and maker and approver and maker == approver:
        return {"reason_code": SELF_APPROVAL,
                "detail": "the maker %r approved their own script; an independent reviewer must "
                          "approve before the song is made" % maker}
    if record.get("status") == "approved":
        if "approvals" in record:
            ev = AE.active_approval(record, "lyrics", lyrics_sha(lyrics))
            if ev is not None:
                return None
        elif record.get("lyrics_sha") == lyrics_sha(lyrics):
            return None                          # legacy record shape
    return {"reason_code": REASON,
            "detail": "the client chose to approve the script first and has not approved "
                      "these lyrics; nothing was sent to the music generator"}
