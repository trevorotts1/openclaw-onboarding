#!/usr/bin/env python3
"""End-to-end: the live run sends card + still for every shot BEFORE any video
submit, waits, GO continues, an edit re-sends one shot, No auto-approves
silently, resume never duplicates. Providers and the delivery sink are mocked.

Run: python3 core/storyboard_director/test_approval_runner.py  (stdlib, no spend)
"""
import importlib
import json
import os
import sys
import tempfile

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import state_store as SS                                  # noqa: E402
import storyboard_director.approval_runner as AR          # noqa: E402
import kie_dispatch.model_lock as ML                      # noqa: E402
from batch_mode import batch as BATCH                     # noqa: E402

sys.path.insert(0, os.path.join(CORE, "intake_preflight"))
import factory as FACTORY                                 # noqa: E402

KD = importlib.import_module("kie_dispatch.kie_dispatch")
VIDEO_MODEL = "kling-3.0/video"
FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name, "" if cond else " (%s)" % (detail,)))
    if not cond:
        FAILS.append(name)


def make_run(choice="yes"):
    run = os.path.join(tempfile.mkdtemp(prefix="sbrun-"), "run1")
    sb = os.path.join(run, "storyboard")
    os.makedirs(sb)
    os.makedirs(os.path.join(run, "control"))
    shots, contracts, stills = [], {}, {}
    for i in range(3):
        sid = "s%d" % (i + 1)
        shots.append({"shot_id": sid, "song_start": i * 8.0, "song_end": i * 8.0 + 8.0,
                      "story_stage": "frozen", "location_id": "kitchen"})
        contracts[sid] = {"lyric_text": "line %d" % (i + 1),
                          "viewer_understanding": "she is stuck %d" % (i + 1),
                          "character_action": "sitting at table %d" % (i + 1),
                          "visible_emotion": "stuck"}
        stills[sid] = os.path.join(sb, sid + ".png")
        open(stills[sid], "wb").write(b"png")
    json.dump({"shots": shots}, open(os.path.join(sb, "shot-list.json"), "w"))
    json.dump(contracts, open(os.path.join(sb, "contracts.json"), "w"))
    json.dump(stills, open(os.path.join(sb, "stills.json"), "w"))
    if choice:
        json.dump({"storyboard_approval": choice}, open(os.path.join(run, "control", "card-receipt.json"), "w"))
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        st.init_run("run1", [s for s, _ in BATCH.STAGES])
    return run


class World:
    """Mocked delivery sink + mocked video provider sharing one event log."""
    def __init__(self):
        self.events = []

    def send(self, message, images):
        self.events.append(("message", message))
        for n, img in images:
            self.events.append(("image", n, img))

    def video_submit(self, run):
        gate = json.load(open(os.path.join(run, "storyboard", "gate.json")))
        db = os.path.join(tempfile.mkdtemp(), "state.db")
        ML.lock_run_model(db, "r1", VIDEO_MODEL)

        def runner(*a, **k):
            self.events.append(("video_submit",))
            raise RuntimeError("stop after first submit")   # provider mocked: no spend
        req = {"model": VIDEO_MODEL, "request_kind": "video", "input": {"prompt": "p" * 200},
               "card_receipt": {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                                            "length": 60, "video_model": "MiniMax H3 768P"},
                                "who": "t", "at": "2026-10-09T09:00:00Z"},
               "storyboard": {"shots": gate["shots"], "review": {"outcome": "pass"}}}
        led = os.path.join(tempfile.mkdtemp(), "l.db")
        import spend_ledger as L
        L.init_run(led, "r1", 10_000_000)
        return KD.dispatch(model=VIDEO_MODEL, request=req, save_dir=tempfile.mkdtemp(),
                           ledger_db=led, run_id="r1",
                           logical_key="k", attempt_id="a", estimated_cost=100,
                           runner=runner, state_store=db)

    def kinds(self):
        return [e[0] for e in self.events]


def nxt(run):
    class A:
        run_dir = run
    return FACTORY.cmd_next(A)


def test_yes_sends_card_and_three_images_before_any_video():
    run, w = make_run("yes"), World()
    # advance state store so video-generation is the next stage
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        for s, _ in BATCH.STAGES:
            if s == "video-generation":
                break
            st.transition("run1", s, "READY", "t")
            st.claim("run1", s, "t")
            st.transition("run1", s, "COMPLETE", "t")
    env = nxt(run)
    check("next refuses the video command before approval",
          env["outcome"] == "waiting" and env["reason_code"] == "storyboard-approval-required", env)
    r = AR.run(run, w.send)
    check("message then 3 images, in shot order", w.kinds() == ["message", "image", "image", "image"]
          and [e[1] for e in w.events[1:]] == [1, 2, 3], w.events)
    check("message carries every card", all(("line %d" % i) in w.events[0][1] for i in (1, 2, 3)))
    check("run recorded as waiting", r["action"] == "waiting" and not AR.gate_open(run)
          and json.load(open(os.path.join(run, "storyboard", "approval.json")))["state"] == "pending")
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        check("state store says WAITING_APPROVAL", st.get("run1", "video-generation")["state"] == "WAITING_APPROVAL")
    # resume: no reply, nothing re-sent
    n = len(w.events)
    AR.run(run, w.send)
    AR.run(run, w.send)
    check("resume does not duplicate", len(w.events) == n, w.events[n:])
    check("still blocked while pending", nxt(run)["outcome"] == "waiting")
    # edit one shot
    def make_still(sid, card):
        p = os.path.join(run, "storyboard", sid + ".v2.png")
        open(p, "wb").write(b"png2")
        return p
    n = len(w.events)
    r = AR.run(run, w.send, reply="shot 2: change standing at the sink", make_still=make_still)
    sent = w.events[n:]
    check("edit re-sends exactly one shot: 1 message + 1 image", [e[0] for e in sent] == ["message", "image"]
          and sent[1][1] == 2 and "standing at the sink" in sent[0][1] and "Shot 1 " not in sent[0][1], sent)
    check("still pending after edit", not AR.gate_open(run))
    # GO
    r = AR.run(run, w.send, reply="GO")
    check("GO approves", r["action"] == "approved" and AR.gate_open(run))
    nv = nxt(run)
    check("next now hands out the video command", nv["outcome"] == "ok" and nv["data"]["stage"] == "video-generation", nv)
    before = w.kinds().count("video_submit")
    w.video_submit(run)
    check("video submit happens only after the message + images",
          w.kinds().index("video_submit") > max(i for i, k in enumerate(w.kinds()) if k in ("message", "image")))
    check("exactly one submit attempt", w.kinds().count("video_submit") == before + 1)
    n = len(w.events)
    AR.run(run, w.send, reply="GO")
    check("second GO sends nothing", len(w.events) == n)


def test_unapproved_video_is_blocked():
    run, w = make_run("yes"), World()
    AR.run(run, w.send)                        # pending, shots in gate.json do not exist yet
    check("no gate.json while pending", not os.path.exists(os.path.join(run, "storyboard", "gate.json")))


def test_no_auto_approves_silently():
    run, w = make_run("no"), World()
    r = AR.run(run, w.send)
    check("No: approved, nothing sent", r["action"] == "approved" and w.events == [] and AR.gate_open(run), (r, w.events))
    w.video_submit(run)
    check("No: video submit proceeds", w.kinds() == ["video_submit"])
    os.remove(json.load(open(os.path.join(run, "storyboard", "stills.json")))["s1"])
    run2 = make_run("no")
    os.remove(os.path.join(run2, "storyboard", "s1.png"))
    try:
        AR.run(run2, w.send)
        check("No: missing still still blocks", False)
    except Exception as e:
        check("No: missing still still blocks", getattr(e, "code", "") == "STORYBOARD_STILL_MISSING" and not AR.gate_open(run2), e)


def card_then_run(storyboard_reply):
    """Real intake card, answered end to end, then the runner on the same run dir."""
    from choice_card.intake_card import intake_card as IC
    run, w = make_run(None), World()
    replies = ["recommended"] * (len(IC.QUESTIONS) - 1) + [storyboard_reply, "yes"]
    st = IC.conversation(replies, IC.QUESTIONS, run, "555")
    check("card done (%s)" % storyboard_reply, st["done"])
    return run, w, AR.run(run, w.send)


def test_card_answer_reaches_runner():
    run, w, r = card_then_run("2")
    rec = json.load(open(os.path.join(run, "control", "card-receipt.json")))
    check("card No -> receipt false + target", rec == {"storyboard_approval": False, "target": "555"}, rec)
    check("card No -> runner sends nothing, gate open", w.events == [] and AR.gate_open(run), (r, w.events))
    run, w, r = card_then_run("1")
    rec = json.load(open(os.path.join(run, "control", "card-receipt.json")))
    check("card Yes -> receipt true", rec["storyboard_approval"] is True, rec)
    check("card Yes -> message + 3 stills, gate closed", w.kinds() == ["message", "image", "image", "image"]
          and not AR.gate_open(run), w.events)
    run = make_run(None)
    AR.run(run, w.send)
    check("no receipt (old run) = Yes", not AR.gate_open(run))


def test_default_sender_uses_openclaw_message_send():
    run, calls = make_run("yes"), []
    real = AR.subprocess.run
    AR.subprocess.run = lambda argv, **k: calls.append(argv)
    try:
        AR.run(run, AR.openclaw_sender("123"))
    finally:
        AR.subprocess.run = real
    check("argv: 1 text send then 3 --media sends, shell-free lists",
          len(calls) == 4 and all(c[:5] == ["openclaw", "message", "send", "--channel", "telegram"] for c in calls)
          and "--media" not in calls[0] and [c[c.index("--media") + 1] for c in calls[1:]]
          == [os.path.join(run, "storyboard", "s%d.png" % i) for i in (1, 2, 3)], calls)


if __name__ == "__main__":
    test_default_sender_uses_openclaw_message_send()
    test_yes_sends_card_and_three_images_before_any_video()
    test_unapproved_video_is_blocked()
    test_no_auto_approves_silently()
    test_card_answer_reaches_runner()
    print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)) if FAILS else "ALL PASS")
    sys.exit(1 if FAILS else 0)
