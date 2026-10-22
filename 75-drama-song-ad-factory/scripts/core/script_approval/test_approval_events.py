#!/usr/bin/env python3
"""Revision-aware approval events -- the acceptance regressions
(spec 5.1/5.2, findings D07/D17):

  1. question-reorder regression preserves saved decisions, migrated schemas too
  2. missing/corrupt approval data is an explicit recoverable unknown -- no paid
     generation, and recovery works from the client's own reply
  3. an approval round trip in the originating conversation persists ONCE, with
     one continuation, and a replay re-acknowledges without duplicate work
  4. partial invalidation matrix: a script edit keeps character approvals and
     must not silently reuse the previous lyrics approval; a lyric line change
     keeps character (and script) approvals
  5. an ambiguous reply asks exactly one concrete question, and only when the
     reply context cannot resolve the pending approval

Zero paid calls, zero network. Run: python3 core/script_approval/test_approval_events.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, HERE)   # carried fix: bare `import approval_events` needs the test's own dir
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "kie_dispatch"))
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))
sys.path.insert(0, os.path.join(CORE, "song_dispatch"))
from choice_card.intake_card import intake_card as IC  # noqa: E402
import approval_events as AE  # noqa: E402
import card_answers  # noqa: E402
import script_approval as SA  # noqa: E402
from script_approval import stage  # noqa: E402

TITLE = "The Climb"
STORY = [("The world", ["She runs a small shop.", "Nobody knows her name."]),
         ("The turn", ["One seed of truth changes it."])]
STORY_EDIT = [("The world", ["She runs a small bakery.", "Nobody knows her name."]),
              ("The turn", ["One seed of truth changes it."])]
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_EDIT = ["I am not sma-a-all", "I no longer hide"]
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["Get the book. Link below."]},
         {"tag": "End", "delivery": None, "lines": []}]
LYRICS = "\n".join(l for s in SHEET for l in s["lines"])
CTX = {"tenant_id": "T1", "run_id": "R1", "conversation_id": "C1", "thread_id": "TH1",
       "account_id": "A1", "channel": "app"}
SAMPLES = os.path.join(CORE, "story_arc", "fixtures", "valid.json"), \
    os.path.join(CORE, "lyric_writer", "fixtures", "campaign.json")


def ctx(**over):
    c = dict(CTX)
    c.update(over)
    return c


def make_run(yes=True):
    run = tempfile.mkdtemp(prefix="sa-events-")
    os.makedirs(os.path.join(run, "creative"))
    shutil.copy(SAMPLES[0], os.path.join(run, "creative", "story.json"))
    shutil.copy(SAMPLES[1], os.path.join(run, "creative", "lyrics.json"))
    json.dump({"title": TITLE, "story": [list(a) for a in STORY], "sheet": SHEET,
               "lyrics": LYRICS}, open(os.path.join(run, "creative", "script.json"), "w"))
    rows = [{"id": "script", "n": 1 if yes else 2, "text": "", "value": None}]
    json.dump({"schema_version": 2, "answers": rows},
              open(os.path.join(run, "card-answers.json"), "w"))
    return run


def reply(run, text, approved_by="client-alice", context=None, sheet=SHEET,
          story=STORY, lyrics=LYRICS):
    return SA.handle_reply(run, text, TITLE, story, sheet, lyrics,
                           lambda rp, s, h: (story, sheet, lyrics),
                           lambda s, h: [], approved_by=approved_by,
                           context=context or ctx())


def decisions_of(run):
    return AE.decisions(AE.ensure_record(SA.record_for(run)))


# --------------------------------------------------------------------------- #
# 1. saved decisions survive question reordering, migrated schemas included
# --------------------------------------------------------------------------- #

def test_question_reorder_preserves_saved_decisions_including_migrated_schemas():
    run = make_run()
    # a saved list whose row order is NOT the question order: the stored ids
    # decide, so reordering the questions cannot turn a saved Yes into a No
    rows = [{"id": "spend", "n": 2, "text": "up to $25"}, {"id": "script", "n": 1, "text": "Yes"}]
    card_answers.write(run, rows, IC.QUESTIONS)
    st = card_answers.load(run)
    assert card_answers.decision(st, "script")["state"] == card_answers.YES
    assert SA.wants_approval(st, IC.QUESTIONS) is True
    assert SA.wants_approval(st, list(reversed(IC.QUESTIONS))) is True   # reordered
    # legacy v1 list (no envelope): migrated by its stored ids, still Yes after reorder
    path = os.path.join(run, card_answers.ANSWERS)
    json.dump([{"id": "script", "n": 1, "text": "Yes"}], open(path, "w"))
    st = card_answers.migrate(run)
    assert st["schema_version"] == 2
    assert card_answers.decision(st, "script")["state"] == card_answers.YES
    assert SA.wants_approval(st, list(reversed(IC.QUESTIONS))) is True
    # a saved row with no stored id is an explicit unknown -- never re-read by position
    json.dump([{"n": 1}], open(path, "w"))
    st = card_answers.load(run)
    assert card_answers.decision(st, "script")["state"] == card_answers.UNKNOWN
    assert SA.wants_approval(st, list(reversed(IC.QUESTIONS))) is False   # unknown is not Yes
    # a recorded No stays a No under any order
    json.dump([{"id": "script", "n": 2}], open(path, "w"))
    assert SA.wants_approval(card_answers.load(run), list(reversed(IC.QUESTIONS))) is False


# --------------------------------------------------------------------------- #
# 2. missing/corrupt approval data: explicit recoverable unknown, no paid work
# --------------------------------------------------------------------------- #

def test_missing_or_corrupt_approval_is_recoverable_unknown_with_no_paid_generation():
    delivered = []
    run = make_run()
    os.remove(os.path.join(run, "card-answers.json"))         # missing answers
    env = stage.run_stage(run, delivered.append)
    assert env["outcome"] == "blocked" and env["approval_state"] == "unknown", env
    assert env.get("recoverable") is True and env["reason_code"] == AE.UNKNOWN_REASON
    assert delivered == [] and not os.path.exists(AE.record_path(run))   # nothing sent, no record
    assert len(env["problems"]) == 1 and env["problems"][0].count("?") == 1  # one question

    open(os.path.join(run, "card-answers.json"), "w").write("{corrupt")   # corrupt answers
    env = stage.run_stage(run, delivered.append)
    assert env["outcome"] == "blocked" and env["approval_state"] == "unknown", env

    run2 = make_run()
    open(os.path.join(run2, "creative", "script-approval.json"), "w").write("[not a record]")
    rec = SA.record_for(run2)
    assert AE.is_unknown_record(rec)
    refusal = SA.check_script_approval(rec, LYRICS)
    assert refusal["reason_code"] == AE.UNKNOWN_REASON, refusal       # unknown, never permission

    # no paid generation: the music dispatch refuses on the unknown record
    import length_formula as LF
    import song_dispatch as SD
    import suno_recipe as R
    full = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
            {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
            {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
            {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
            {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
            {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
            {"tag": "Outro", "delivery": "spoken",
             "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
    req = R.build_request("soul-ballad", full, LYRICS, "T", 58,
                          hook_plan={"true_at_beat": "the_world"})
    calls = []
    try:
        SD.run_takes(req, LF.plan(60, (15, 20)), lambda rq: calls.append(1) or [],
                     lambda t: {}, lambda t, r: None, "", "", run_dir=run2,
                     kie=lambda fn, label, generation=False: fn())
    except SD.DispatchError as e:
        assert AE.UNKNOWN_REASON in str(e), e
    else:
        raise AssertionError("generation ran on unknown approval data")
    assert calls == []

    # recoverable: the client's own reply answers the one question by stable id
    run3 = make_run()
    os.remove(os.path.join(run3, "card-answers.json"))
    env = stage.run_stage(run3, delivered.append, reply="yes, show me first")
    assert env["outcome"] == "waiting" and env["reason"] == "script-sent", env
    st = card_answers.load(run3)
    assert card_answers.decision(st, "script")["state"] == card_answers.YES
    env = stage.run_stage(run3, delivered.append, reply="approve", context=ctx())
    assert env["outcome"] == "go" and env["reason"] == "approved", env


# --------------------------------------------------------------------------- #
# 3. one decision, one continuation, replay-safe, same run resumed
# --------------------------------------------------------------------------- #

def test_round_trip_persists_once_with_one_continuation_on_replay():
    run = make_run()
    SA.request_approval(run, TITLE, STORY, SHEET, LYRICS, context=ctx(), message_id="pres-1")
    c = ctx(approved_by="client-alice", reply_to_message_id="msg-77")
    r1 = reply(run, "approve", context=c)
    assert r1["status"] == "approved" and not r1.get("duplicate"), r1
    rec = SA.record_for(run)
    assert len(AE.decisions(rec)) == 1                          # persisted once
    cont = [o for o in rec["outbox"] if o["kind"] == "continuation"]
    acks = [o for o in rec["outbox"] if o["kind"] == "ack"]
    assert len(cont) == 1 and len(acks) == 1                    # one continuation, one ack
    did, events = AE.decisions(rec)[0]
    assert cont[0]["decision_id"] == acks[0]["decision_id"] == did  # same transaction boundary
    assert len(events) == 2                                     # script + lyrics events
    for ev in events:
        for field in ("tenant_id", "run_id", "kind", "revision", "sha256",
                      "conversation_id", "approved_by", "timestamp"):
            assert ev.get(field) is not None, field              # full binding
        assert ev["tenant_id"] == "T1" and ev["run_id"] == "R1"
        assert ev["requesting_conversation_id"] == "C1"
    assert cont[0]["payload"] == {"action": "continue", "run_id": "R1",
                                  "kinds": ["script", "lyrics"], "decision_id": did}

    # replay of the same message: acknowledge the existing decision, do no
    # duplicate work -- still one decision and one continuation
    r2 = reply(run, "approve", context=c)
    assert r2.get("duplicate") is True and "Already recorded" in " ".join(r2["messages"])
    rec = SA.record_for(run)
    assert len(AE.decisions(rec)) == 1
    assert [o for o in rec["outbox"] if o["kind"] == "continuation"] == cont
    assert [o for o in rec["outbox"] if o["kind"] == "ack"] == acks
    # resume: the same run continues -- no new campaign, task card or paid attempt
    assert rec["run"] == {"run_id": "R1", "tenant_id": "T1"}
    assert {ev["run_id"] for _, evs in AE.decisions(rec) for ev in evs} == {"R1"}
    assert AE.pending_continuations(rec) == cont


# --------------------------------------------------------------------------- #
# 4. partial invalidation matrix
# --------------------------------------------------------------------------- #

def test_partial_invalidation_matrix_script_edit_keeps_character_approvals():
    run = make_run()
    SA.request_approval(run, TITLE, STORY, SHEET, LYRICS, context=ctx(), message_id="pres-1")
    reply(run, "approve", context=ctx(reply_to_message_id="msg-77"))
    # character images land and get their own approval at their own revision
    rec = AE.ensure_record(SA.record_for(run))
    AE.register_artifact(rec, "character_images", "img-sha-1")
    AE.open_ask(rec, ["character_images"], message_id="pres-chars")
    AE.save_record(run, rec)
    reply(run, "looks good", context=ctx(reply_to_message_id="msg-88"))
    rec = SA.record_for(run)
    assert AE.active_approval(rec, "character_images", "img-sha-1") is not None

    # a lyric line change: the sung line moves, the spoken script does not
    sheet2 = [dict(s, lines=(HOOK_EDIT if s["tag"] == "Hook 1" else s["lines"])) for s in SHEET]
    lyrics2 = "\n".join(l for s in sheet2 for l in s["lines"])
    SA.request_approval(run, TITLE, STORY, sheet2, lyrics2, context=ctx(), message_id="pres-2")
    rec = SA.record_for(run)
    # unchanged character images keep approval when a lyric line changes
    assert AE.active_approval(rec, "character_images", "img-sha-1") is not None
    assert AE.active_approval(rec, "script", SA.script_sha(TITLE, STORY, sheet2)) is not None
    # the lyrics moved on: its approval is gone, and the music gate refuses
    assert AE.active_approval(rec, "lyrics") is None
    assert SA.check_script_approval(rec, lyrics2) is not None
    reply(run, "approve lyrics", context=ctx(reply_to_message_id="msg-79"))

    # a revised script must not silently reuse the previous lyrics approval --
    # even when the lyrics text itself is unchanged
    SA.request_approval(run, TITLE, STORY_EDIT, sheet2, lyrics2, context=ctx(), message_id="pres-3")
    rec = SA.record_for(run)
    assert AE.active_approval(rec, "lyrics") is None, "revised script silently reused lyrics approval"
    assert SA.check_script_approval(rec, lyrics2) is not None
    # a script edit keeps character approvals
    assert AE.active_approval(rec, "character_images", "img-sha-1") is not None
    # and re-approving both releases the music gate again
    r = reply(run, "approve both", context=ctx(reply_to_message_id="msg-80"))
    assert r["status"] == "approved"
    assert SA.check_script_approval(SA.record_for(run), lyrics2) is None


# --------------------------------------------------------------------------- #
# 5. ambiguity: exactly one concrete question, only when context cannot resolve
# --------------------------------------------------------------------------- #

def test_ambiguous_reply_asks_exactly_one_concrete_question_only_when_unresolvable():
    run = make_run()
    SA.request_approval(run, TITLE, STORY, SHEET, LYRICS, context=ctx(), kinds=("script",),
                        message_id="pres-script")
    # a revised script: same lyrics, script revision 2 (the displayed labels differ)
    SA.request_approval(run, TITLE, STORY_EDIT, SHEET, LYRICS, context=ctx(), kinds=("script",),
                        message_id="pres-script2")
    SA.request_approval(run, TITLE, STORY_EDIT, SHEET, LYRICS, context=ctx(), kinds=("lyrics",),
                        message_id="pres-lyrics")
    rec = SA.record_for(run)
    by_msg = {a["message_id"]: a for a in AE.open_asks(rec)}
    assert by_msg["pres-script2"]["revisions"]["script"] == 2     # displayed revision labels
    assert by_msg["pres-lyrics"]["revisions"]["lyrics"] == 1

    # two distinct pending approvals, bare yes, no reply context -> exactly ONE
    # concrete question, and no decision is recorded
    r = reply(run, "yes", context=ctx(), story=STORY_EDIT)
    assert r["status"] == "pending" and r.get("asked"), r
    assert r["messages"] == [r["asked"]] and r["asked"].count("?") == 1
    assert AE.decisions(AE.ensure_record(SA.record_for(run))) == []

    # replied-to message ids disambiguate before any question is asked
    r = reply(run, "yes", context=ctx(reply_to_message_id="pres-lyrics"), story=STORY_EDIT)
    assert not r.get("asked"), r
    rec = SA.record_for(run)
    assert AE.active_approval(rec, "lyrics") is not None
    assert AE.active_approval(rec, "script") is None

    # displayed revision labels disambiguate before any question is asked
    r = reply(run, "yes, rev 2", context=ctx(), story=STORY_EDIT)
    assert not r.get("asked"), r
    rec = SA.record_for(run)
    assert AE.active_approval(rec, "script") is not None

    # a label that names no presented revision gets one concrete question
    run2 = make_run()
    SA.request_approval(run2, TITLE, STORY, SHEET, LYRICS, context=ctx(),
                        message_id="pres-script")
    r = reply(run2, "approve rev 9", context=ctx())
    assert r["status"] == "pending" and r.get("asked", "").count("?") == 1, r
    assert AE.decisions(AE.ensure_record(SA.record_for(run2))) == []

    # a single pending approval needs no disambiguation at all
    run3 = make_run()
    SA.request_approval(run3, TITLE, STORY, SHEET, LYRICS, context=ctx(),
                        message_id="pres-joint")
    r = reply(run3, "looks good", context=ctx())
    assert r["status"] == "approved" and not r.get("asked"), r


# --------------------------------------------------------------------------- #
# a generic yes cannot approve the unseen, a stale revision, or another run
# --------------------------------------------------------------------------- #

def test_generic_yes_cannot_approve_unseen_artifact_or_another_runs_revision():
    run = make_run()
    SA.request_approval(run, TITLE, STORY, SHEET, LYRICS, context=ctx(), kinds=("script",),
                        message_id="pres-script")
    r = reply(run, "approve lyrics", context=ctx())                # never presented
    assert r.get("asked") and AE.decisions(AE.ensure_record(SA.record_for(run))) == [], r

    # another run's revision: refused, nothing recorded
    r = reply(run, "approve", context=ctx(run_id="R2"))
    assert AE.decisions(AE.ensure_record(SA.record_for(run))) == []
    assert "R2" in " ".join(r["messages"])

    # an old message id never approves the newer revision
    SA.request_approval(run, TITLE, STORY, SHEET, LYRICS, context=ctx(), kinds=("script",),
                        message_id="pres-script")
    reply(run, "approve", context=ctx(reply_to_message_id="msg-1"))      # rev 1 approved
    sheet2 = [dict(s, lines=[l + " v2" for l in s["lines"]]) for s in SHEET]
    lyrics2 = "\n".join(l for s in sheet2 for l in s["lines"])
    SA.request_approval(run, TITLE, STORY, sheet2, lyrics2, context=ctx(), kinds=("script",),
                        message_id="pres-script2")
    r = reply(run, "approve", context=ctx(reply_to_message_id="msg-1"))  # replay of the old message
    assert r.get("duplicate") is True, r
    rec = SA.record_for(run)
    assert AE.active_approval(rec, "script") is None                     # rev 2 still needs approval


# --------------------------------------------------------------------------- #
# the presentation itself: every element, three approval actions, revisions
# --------------------------------------------------------------------------- #

def test_presentation_shows_every_element_and_three_approval_actions():
    run = make_run()
    msgs = SA.request_approval(run, TITLE, STORY, SHEET, LYRICS, context=ctx(),
                               message_id="pres-1")
    text = "\n".join(msgs)
    for marker in ("OPENING SPOKEN HOOK", "THE STORY", "THE SCRIPT", "THE SONG LYRICS",
                   "EARNED SONG HOOK", "Where it becomes true", "ERM DROP", "HERO SHIFT",
                   "CALL TO ACTION", '"approve script"', '"approve lyrics"', "approve both",
                   "One closed door.", "I am not sma-a-all", "Get the book. Link below."):
        assert marker in text, marker
    assert "Script revision 1 (" in text and "Lyrics revision 1 (" in text
    # the elements are derived from the script's own lines, never invented
    assert "One closed door." in text.split("OPENING SPOKEN HOOK")[1].split("THE STORY")[0]
    assert "the story turn" in text.lower() or "The turn" in text


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
