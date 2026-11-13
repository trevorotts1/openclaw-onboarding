#!/usr/bin/env python3
"""S75-037 (U-A11): the two Studio publish paths a chat run never exercised.

Proves, behaviourally:
  * a Studio publish that RAISES no longer silences the chat: with a chat target
    the storyboard copy is still sent and the stage waits with reason
    `studio-publish-failed` in data; with NO chat target the error is kept;
  * a Studio order sees the delivered songs as stage `song` on its page: the
    client message as the text, the presented audio files, and one choice per
    OFFERED number (a failed take is listening-only and never a choice);
  * the song publish happens ONCE per run (the client's answer binds the
    version the page showed);
  * the song answer `2` becomes `factory.py music --run-dir <run> --reply 2`,
    a number the run never offered is refused, and that exact command form is
    accepted by the CLI parser.

Stdlib only: no pytest import (CI runs every test_*.py under scripts/core with
bare python3 and a fresh empty HOME), and every test is a zero-argument
`test_*` function with plain asserts, so the SAME file runs both ways:

  python3 -B scripts/core/intake_preflight/test_studio_publish_paths_s75_037.py
  python3 -m pytest -q scripts/core/intake_preflight

No network, no provider, no openclaw binary; writes only under a temp dir.
"""
import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent

for _p in (str(CORE), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import factory as F   # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────

@contextmanager
def tmpdir(prefix="ds-studio-pub-"):
    """A private temp dir for one test (CI gives no pytest tmp_path here)."""
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield tmp
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


@contextmanager
def patched(attr, value):
    """monkeypatch.setattr(F, attr, value), stdlib: restore on exit."""
    saved = getattr(F, attr)
    setattr(F, attr, value)
    try:
        yield
    finally:
        setattr(F, attr, saved)


class FakeBridge:
    """The approvals_bridge seam, stubbed: records every publish, answers what
    it is told to answer, never touches the network."""

    def __init__(self, answer=None):
        self.published = []
        self.answered = []
        self._answer = answer

    def publish(self, base_url, key, order_id, stage, version, text, choices, files):
        self.published.append({"stage": stage, "version": version, "text": text,
                               "choices": list(choices), "files": list(files)})
        return {"stage": stage, "version": version}

    def answer(self, base_url, key, order_id, stage, version):
        self.answered.append({"stage": stage, "version": version})
        return self._answer


@contextmanager
def bridge(answer=None):
    fb = FakeBridge(answer)
    with patched("_approvals_bridge", lambda: fb), patched("_studio_key", lambda: "test-key"):
        yield fb


class FakeRunner:
    """The approval_runner seam, stubbed: one send carrying a text and one
    still, then the waiting action."""

    def __init__(self, target="chat-1"):
        self.target = target
        self.sent = []

    def receipt_target(self, run_dir):
        return self.target

    def openclaw_sender(self, target):
        def send(message, images):
            self.sent.append({"target": target, "message": message,
                              "stills": [str(p) for _n, p in images]})
        return send

    def run(self, run_dir, send, reply=None):
        send("Storyboard: 1 shot", [("s1", str(Path(run_dir) / "s1.png"))])
        return {"action": "waiting"}


def make_run(tmp, studio=True):
    """A run folder that claims a Studio order (or a chat-only run)."""
    run = Path(tempfile.mkdtemp(dir=str(tmp), prefix="run-"))
    (run / "control").mkdir()
    if studio:
        (run / "control" / "studio-order.json").write_text(json.dumps(
            {"order_id": "o-1", "client_id": "c-1", "title": "T",
             "base_url": "https://studio.example"}), "utf-8")
    return run


def song_state(run, numbers=(1, 2, 3), failed=(), concerns=None):
    """The record `deliver_choices` leaves behind: offered numbers + presented
    audio files (the same shape the real client message is built from)."""
    sc = run / "song-choices"
    sc.mkdir(parents=True, exist_ok=True)
    offered, presented = {}, []
    for n in numbers:
        f = sc / ("%d.mp3" % n)
        f.write_bytes(b"mp3")
        presented.append(str(f))
        offered[str(n)] = {"label": "%d - take %d (short)" % (n, n),
                           "file": str(f), "duration": "0:30",
                           "take": {"audio_path": str(f)}, "receipt": {}}
    doc = {"required": True, "offered": offered, "presented": presented,
           "concerns": dict(concerns or {}), "failure_fork": bool(failed)}
    for n in failed:
        doc["concerns"][str(n)] = ["hook missing"]
    (sc / "state.json").write_text(json.dumps(doc), "utf-8")
    return doc


def ns(**kw):
    kw.setdefault("target", "")
    kw.setdefault("reply", None)
    return argparse.Namespace(**kw)


def boom(*args, **kwargs):
    raise RuntimeError("studio 502")


# ── storyboard: a studio outage must not silence the chat ───────────────────

def test_studio_publish_failure_still_sends_the_chat_copy():
    with tmpdir() as tmp:
        run = make_run(tmp, studio=True)
        fr = FakeRunner(target="chat-1")
        with patched("_approval_runner", lambda: fr), patched("_studio_publish", boom):
            env = F.cmd_storyboard(ns(run_dir=str(run)))
        assert env["outcome"] == "waiting", env
        assert len(fr.sent) == 1 and fr.sent[0]["target"] == "chat-1", fr.sent
        assert fr.sent[0]["message"].startswith("Storyboard"), fr.sent
        assert env["reason_code"] == "studio-publish-failed", env
        assert env["data"]["reason"] == "studio-publish-failed", env
        assert env["data"]["studio_publish"]["outcome"] == "failed", env
        # the failure is reported, not invented: the chat copy really went
        assert "messages" not in env["data"], env


def test_studio_publish_failure_without_a_chat_target_is_still_an_error():
    with tmpdir() as tmp:
        run = make_run(tmp, studio=True)
        fr = FakeRunner(target="")
        with patched("_approval_runner", lambda: fr), patched("_studio_publish", boom):
            env = F.cmd_storyboard(ns(run_dir=str(run)))
        assert env["outcome"] == "error", env
        assert env["reason_code"] == "storyboard-failed", env
        assert fr.sent == [], fr.sent


# ── song: a Studio order sees the three songs on its page ───────────────────

def test_studio_order_publishes_the_delivered_songs():
    with tmpdir() as tmp, bridge() as fb:
        run = make_run(tmp, studio=True)
        song_state(run)
        sc = F._song_choices_next(run)
        assert sc is not None
        pubs = [p for p in fb.published if p["stage"] == "song"]
        assert len(pubs) == 1, fb.published
        pub = pubs[0]
        assert [c["n"] for c in pub["choices"]] == [1, 2, 3], pub
        assert [os.path.basename(f) for f in pub["files"]] == \
            ["1.mp3", "2.mp3", "3.mp3"], pub
        # the client message the chat delivery built, word for word
        assert "Reply 1, 2 or 3 to pick your song" in pub["text"], pub


def test_a_failed_take_is_listening_only_and_never_a_choice():
    with tmpdir() as tmp, bridge() as fb:
        run = make_run(tmp, studio=True)
        song_state(run, failed=(3,))
        F._song_choices_next(run)
        pub = [p for p in fb.published if p["stage"] == "song"][0]
        assert [c["n"] for c in pub["choices"]] == [1, 2], pub
        assert "Version 3 did not pass" in pub["text"], pub


def test_the_song_publish_is_one_round_per_run():
    with tmpdir() as tmp, bridge() as fb:
        run = make_run(tmp, studio=True)
        song_state(run)
        F._song_choices_next(run)
        F._song_choices_next(run)
        versions = [p["version"] for p in fb.published if p["stage"] == "song"]
        assert versions == [1], fb.published


def test_a_chat_run_publishes_no_songs():
    with tmpdir() as tmp, bridge() as fb:
        run = make_run(tmp, studio=False)
        song_state(run)
        F._song_choices_next(run)
        assert [p for p in fb.published if p["stage"] == "song"] == [], fb.published


# ── song answer: the existing music reply path, never a second one ──────────

def test_a_studio_song_answer_becomes_the_music_reply():
    with tmpdir() as tmp:
        run = make_run(tmp, studio=True)
        song_state(run)
        env = F._studio_apply("next", "r", run, "continuity-bible", "song",
                              {"stage": "song", "version": 1, "value": "2",
                               "digest": None})
        assert env["outcome"] == "ok", env
        cmd = env["data"]["command"]
        assert "factory.py music" in cmd, env
        assert "--run-dir" in cmd and "--reply 2" in cmd, env


def test_a_song_number_never_offered_is_refused():
    with tmpdir() as tmp:
        run = make_run(tmp, studio=True)
        song_state(run)
        env = F._studio_apply("next", "r", run, "continuity-bible", "song",
                              {"stage": "song", "version": 1, "value": "9",
                               "digest": None})
        assert env["outcome"] == "rejected", env
        assert env["reason_code"] == "studio-song-choice-unknown", env
        assert env["data"]["offered"] == ["1", "2", "3"], env


def test_the_music_reply_command_form_is_accepted_by_the_cli():
    with tmpdir() as tmp:
        run = make_run(tmp, studio=False)          # no song state: a refusal
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            F.main(["music", "--run-dir", str(run), "--reply", "2"])
        env = json.loads(buf.getvalue())
        assert env["outcome"] == "error", env
        assert env["reason_code"] == "SONG_PICK_REFUSED", env


TESTS = [
    test_studio_publish_failure_still_sends_the_chat_copy,
    test_studio_publish_failure_without_a_chat_target_is_still_an_error,
    test_studio_order_publishes_the_delivered_songs,
    test_a_failed_take_is_listening_only_and_never_a_choice,
    test_the_song_publish_is_one_round_per_run,
    test_a_chat_run_publishes_no_songs,
    test_a_studio_song_answer_becomes_the_music_reply,
    test_a_song_number_never_offered_is_refused,
    test_the_music_reply_command_form_is_accepted_by_the_cli,
]


def main():
    fails = []
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            fails.append("%s: %s: %s" % (t.__name__, type(e).__name__, e))
    print("\ntest_studio_publish_paths_s75_037: %s (%d tests, %d failures)"
          % ("PASS" if not fails else "FAIL", len(TESTS), len(fails)))
    for f in fails:
        print(" - FAILED: %s" % f)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
