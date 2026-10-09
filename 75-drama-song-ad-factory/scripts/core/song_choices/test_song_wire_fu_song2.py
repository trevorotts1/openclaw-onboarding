#!/usr/bin/env python3
"""FU-SONG-APPROVAL wiring: the card's answer reaches the run, the gate follows it,
and the 3-song message + files reach the client sink before any video stage.

Run: python3 core/song_choices/test_song_wire_fu_song2.py   (needs ffmpeg + ffprobe)
"""
import io
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_song_choices_fu_song as T                           # noqa: E402  (fixtures)
from choice_card.intake_card import intake_card as IC           # noqa: E402
from song_choices import song_choices as SC                     # noqa: E402
import factory as F                                             # noqa: E402

YES = ["1"] * 7 + ["yes"]                 # all recommended; SONG APPROVAL = Yes
NO = ["1"] * 6 + ["2", "yes"]             # SONG APPROVAL = No


def _gate(run):
    env = F.cmd_next(T._A(run))
    return env["reason_code"] if env["outcome"] == "error" else "open"


def _offer(tmp, run, target=None, send=None):
    res, _, _ = T._pipeline(tmp)
    return SC.deliver_choices(res, os.path.join(tmp, "D"), run, target=target, send=send)


def test_yes_card_to_gate_closed_until_pick_then_open():
    with tempfile.TemporaryDirectory() as tmp:
        run = T._stage_run(tmp)
        assert _gate(run) == "open"                                  # nothing recorded yet
        IC.conversation(["1"] * 7, run_dir=run)                      # recap shown, not confirmed
        assert SC._state(run) is None and _gate(run) == "open"
        st = IC.conversation(YES, run_dir=run)
        assert st["done"] and SC._state(run)["required"] is True
        assert _gate(run) == "SONG_PICK_MISSING"                     # closed before any song is even offered
        _offer(tmp, run)
        assert _gate(run) == "SONG_PICK_MISSING"
        SC.record_pick(run, "3")
        assert _gate(run) == "open" and SC.refusal(run) is None


def test_no_card_records_no_and_no_gate():
    with tempfile.TemporaryDirectory() as tmp:
        run = T._stage_run(tmp)
        IC.conversation(NO, run_dir=run)
        assert SC._state(run)["required"] is False and _gate(run) == "open"


def test_recap_change_updates_the_recorded_answer():
    with tempfile.TemporaryDirectory() as tmp:
        run = T._stage_run(tmp)
        IC.conversation(NO, run_dir=run)
        assert _gate(run) == "open"
        IC.conversation(["1"] * 6 + ["2", "7", "1", "yes"], run_dir=run)   # changed 7 to Yes
        assert SC._state(run)["required"] is True and _gate(run) == "SONG_PICK_MISSING"
        IC.conversation(["1"] * 7 + ["7", "2", "yes"], run_dir=run)         # and back to No
        assert SC._state(run)["required"] is False and _gate(run) == "open"


def test_resume_keeps_the_answer_offered_songs_and_pick():
    with tempfile.TemporaryDirectory() as tmp:
        run = T._stage_run(tmp)
        IC.conversation(YES, run_dir=run)
        _offer(tmp, run)
        before = SC._state(run)
        assert before["offered"]
        IC.conversation(YES, run_dir=run)                            # resume replays the card
        IC.conversation(NO, run_dir=run)                             # even a stray replay cannot wipe it
        assert SC._state(run) == before and _gate(run) == "SONG_PICK_MISSING"
        SC.record_pick(run, "1")
        IC.conversation(YES, run_dir=run)
        assert _gate(run) == "open"


def test_cli_card_step_with_run_dir_records_the_answer():
    with tempfile.TemporaryDirectory() as tmp:
        run = T._stage_run(tmp)
        with redirect_stdout(io.StringIO()):
            F.main(["card", "--step", "--run-dir", run] + [x for r in YES for x in ("--reply", r)])
        assert SC._state(run)["required"] is True


def test_message_and_three_files_reach_the_sink_in_order_before_any_video_stage():
    with tempfile.TemporaryDirectory() as tmp:
        run = T._stage_run(tmp)
        IC.conversation(YES, run_dir=run)
        sent = []

        def sink(argv):
            sent.append((argv, _gate(run)))                          # gate state AT delivery time

        msg = _offer(tmp, run, target="555", send=sink)
        assert len(sent) == 1
        argv, gate = sent[0]
        assert gate == "SONG_PICK_MISSING"                           # no video stage can have started
        assert argv[:7] == ["openclaw", "message", "send", "--channel", "telegram", "--target", "555"]
        assert argv[argv.index("--message") + 1] == msg and msg.count("Reply 1, 2 or 3 to pick your song.") == 1
        media = [argv[i + 1] for i, a in enumerate(argv) if a == "--media"]
        assert [os.path.basename(m)[:4] for m in media] == ["1 - ", "2 - ", "3 - "]
        assert all(os.path.isfile(m) for m in media)
        assert SC.send_choices(run, "555", lambda a: None) == argv   # the CLI/resend path builds the same argv
        try:
            SC.send_choices(T._stage_run(tempfile.mkdtemp()), "555", lambda a: None)
        except SC.ChoiceError:
            pass
        else:
            raise AssertionError("sending with nothing offered must fail loud")


if __name__ == "__main__":
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        sys.exit("ffmpeg and ffprobe are required for this suite")
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
