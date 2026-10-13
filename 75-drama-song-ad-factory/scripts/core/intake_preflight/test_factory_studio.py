#!/usr/bin/env python3
"""W1-box-bridge-U3: factory.py + the studio (SPEC §5, §6). stdlib only.

Proves, behaviourally:
  * `card --format studio-json` prints the studio export (the same envelope
    intake_card.studio_json builds: format, version, question_count, questions);
  * `storyboard` on a run with NO target and NO studio order hands the cards
    and still paths back in data — no error, nothing sent;
  * `storyboard` on a run WITH control/studio-order.json calls the (stubbed)
    approvals_bridge.publish once, with the cards text, every still, and the
    stage "storyboard";
  * `next` turns a (stubbed) studio ANSWER into the EXISTING apply command:
    storyboard -> `storyboard --reply`, song pick -> `song_choices.py pick`,
    script -> `script-reply`;
  * a chat run (no studio order) answers nothing: the storyboard gate still
    waits, the song gate still refuses — the studio never opens a gate by
    being absent.

Run: python3 -m pytest -q scripts/core/intake_preflight/test_factory_studio.py
No network, no provider, no openclaw binary; writes only under a temp dir.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
SKILL = CORE.parent.parent                 # 75-drama-song-ad-factory/
FACTORY = HERE / "factory.py"

for _p in (str(CORE), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import factory as F   # noqa: E402

STAGES = ("research", "creative-strategy", "script-lyrics", "music",
          "continuity-bible", "storyboard", "image-keyframes",
          "video-generation", "qc-retakes", "assembly", "final-qc", "delivery")


# ── fixtures ─────────────────────────────────────────────────────────────────

def make_storyboard_run(tmp, studio=False):
    """A run with three shots, contracts and stills (the approval_runner
    fixture shape), optionally claiming a studio order."""
    run = Path(tempfile.mkdtemp(dir=str(tmp), prefix="ds-studio-"))
    sb = run / "storyboard"
    (run / "control").mkdir()
    sb.mkdir()
    shots, contracts, stills = [], {}, {}
    for i in range(3):
        sid = "s%d" % (i + 1)
        shots.append({"shot_id": sid, "song_start": i * 8.0, "song_end": i * 8.0 + 8.0,
                      "story_stage": "frozen", "location_id": "kitchen"})
        contracts[sid] = {"lyric_text": "line %d" % (i + 1),
                          "viewer_understanding": "she is stuck %d" % (i + 1),
                          "character_action": "sitting at table %d" % (i + 1),
                          "visible_emotion": "stuck"}
        stills[sid] = str(sb / (sid + ".png"))
        Path(stills[sid]).write_bytes(b"png")
    (sb / "shot-list.json").write_text(json.dumps({"shots": shots}), "utf-8")
    (sb / "contracts.json").write_text(json.dumps(contracts), "utf-8")
    (sb / "stills.json").write_text(json.dumps(stills), "utf-8")
    (run / "control" / "card-receipt.json").write_text(
        json.dumps({"storyboard_approval": "yes"}), "utf-8")
    if studio:
        (run / "control" / "studio-order.json").write_text(json.dumps(
            {"order_id": "o-1", "client_id": "c-1", "title": "T",
             "base_url": "https://studio.example"}), "utf-8")
    return run


def make_state_run(tmp, upto):
    """A run whose control/state.sqlite3 marks every stage before `upto`
    COMPLETE and `upto` itself NOT_STARTED."""
    run = Path(tempfile.mkdtemp(dir=str(tmp), prefix="ds-state-"))
    (run / "control").mkdir()
    with sqlite3.connect(str(run / "control" / "state.sqlite3")) as con:
        con.execute("CREATE TABLE stages(run_id TEXT, stage TEXT, state TEXT)")
        for s in STAGES:
            con.execute("INSERT INTO stages VALUES('R',?,?)",
                        (s, "COMPLETE" if STAGES.index(s) < STAGES.index(upto)
                         else "NOT_STARTED"))
    return run


class FakeBridge:
    """The approvals_bridge seam, stubbed: records publish, answers what it is
    told to answer, never touches the network."""

    def __init__(self, answer=None):
        self.published = []
        self.answered = []
        self._answer = answer

    def publish(self, base_url, key, order_id, stage, version, text, choices, files):
        self.published.append({"base_url": base_url, "key": key, "order_id": order_id,
                               "stage": stage, "version": version, "text": text,
                               "choices": choices, "files": list(files)})
        return {"stage": stage, "version": version}

    def answer(self, base_url, key, order_id, stage, version):
        self.answered.append({"base_url": base_url, "key": key, "order_id": order_id,
                              "stage": stage, "version": version})
        return self._answer


@pytest.fixture
def bridge(monkeypatch):
    """Install a FakeBridge as factory's approvals seam + a fixed key."""
    fb = FakeBridge()
    monkeypatch.setattr(F, "_approvals_bridge", lambda: fb)
    monkeypatch.setattr(F, "_studio_key", lambda: "test-key")
    return fb


def ns(**kw):
    kw.setdefault("target", "")
    kw.setdefault("reply", None)
    return argparse.Namespace(**kw)


# ── card --format studio-json ────────────────────────────────────────────────

def test_card_studio_json_prints_the_export():
    p = subprocess.run([sys.executable, str(FACTORY), "card", "--format", "studio-json"],
                       capture_output=True, text=True, cwd=str(SKILL), timeout=60)
    assert p.returncode == 0, p.stderr
    env = json.loads(p.stdout)
    assert env["format"] == "studio-json" and env["version"] == 0
    assert env["question_count"] == len(env["questions"]) > 0
    q = env["questions"][0]
    assert q["question"] and q["example"] and q["options"]


def test_card_studio_json_is_a_real_choice():
    p = subprocess.run([sys.executable, str(FACTORY), "card", "--format", "nonsense"],
                       capture_output=True, text=True, cwd=str(SKILL), timeout=60)
    assert p.returncode != 0                      # the parser still refuses junk


# ── storyboard: hand-back and studio publish ─────────────────────────────────

def test_storyboard_no_target_no_studio_hands_the_cards_back(tmp_path):
    run = make_storyboard_run(tmp_path, studio=False)
    env = F.cmd_storyboard(ns(run_dir=str(run)))
    assert env["outcome"] == "waiting", env
    assert len(env["data"]["messages"]) == 1 and "Storyboard: 3 shots" in env["data"]["messages"][0]
    assert [os.path.basename(p) for p in env["data"]["stills"]] == \
        ["s1.png", "s2.png", "s3.png"]
    # nothing was published anywhere
    assert not (run / "control" / "studio-versions.json").exists()


def test_storyboard_studio_run_publishes_once(tmp_path, bridge):
    run = make_storyboard_run(tmp_path, studio=True)
    env = F.cmd_storyboard(ns(run_dir=str(run)))
    assert env["outcome"] == "waiting", env
    assert len(bridge.published) == 1
    pub = bridge.published[0]
    assert pub["stage"] == "storyboard" and pub["version"] == 1
    assert pub["order_id"] == "o-1" and pub["base_url"] == "https://studio.example"
    assert pub["key"] == "test-key" and pub["choices"] == ["GO"]
    assert "Storyboard: 3 shots" in pub["text"]
    assert [os.path.basename(f) for f in pub["files"]] == ["s1.png", "s2.png", "s3.png"]
    assert all(os.path.isfile(f) for f in pub["files"])
    # the version ledger records the round the page now shows
    got = json.loads((run / "control" / "studio-versions.json").read_text("utf-8"))
    assert got == {"storyboard": 1}


def test_storyboard_second_send_is_a_new_version(tmp_path, bridge):
    run = make_storyboard_run(tmp_path, studio=True)
    F.cmd_storyboard(ns(run_dir=str(run)))
    # the client asks for a change; the redone still lands on disk first
    # (the runner's own _redo_still contract) and the re-send is round two.
    redo = run / "storyboard" / "redo"
    redo.mkdir()
    (redo / "s2.png").write_bytes(b"png")
    F.cmd_storyboard(ns(run_dir=str(run), reply="shot 2: change the table"))
    assert [p["version"] for p in bridge.published] == [1, 2]


# ── next: a studio answer becomes the existing apply command ─────────────────

def test_next_storyboard_answer_becomes_storyboard_reply(tmp_path, bridge):
    bridge._answer = "GO"
    run = make_state_run(tmp_path, "video-generation")
    (run / "control" / "studio-order.json").write_text(json.dumps(
        {"order_id": "o-1", "base_url": "https://studio.example"}), "utf-8")
    env = F.cmd_next(ns(run_dir=str(run)))
    assert env["outcome"] == "ok" and env["data"]["approval"] == "storyboard", env
    cmd = env["data"]["command"]
    assert "factory.py storyboard" in cmd and "--reply GO" in cmd
    assert bridge.answered[-1]["stage"] == "storyboard" and \
        bridge.answered[-1]["order_id"] == "o-1"


def test_next_storyboard_gate_still_waits_without_an_answer(tmp_path, bridge):
    run = make_state_run(tmp_path, "video-generation")     # no studio order at all
    env = F.cmd_next(ns(run_dir=str(run)))
    assert env["outcome"] == "waiting" and \
        env["reason_code"] == "storyboard-approval-required", env
    assert bridge.answered == []                           # never even asked


def test_next_song_pick_answer_becomes_song_pick(tmp_path, bridge):
    bridge._answer = "2"
    run = make_state_run(tmp_path, "continuity-bible")
    (run / "song-choices").mkdir()
    (run / "song-choices" / "state.json").write_text(
        json.dumps({"required": True, "offered": {}}), "utf-8")
    (run / "control" / "studio-order.json").write_text(json.dumps(
        {"order_id": "o-1", "base_url": "https://studio.example"}), "utf-8")
    env = F.cmd_next(ns(run_dir=str(run)))
    assert env["outcome"] == "ok" and env["data"]["approval"] == "song", env
    assert "song_choices.py pick" in env["data"]["command"]
    assert "--reply 2" in env["data"]["command"]


def test_next_song_gate_still_refuses_without_an_answer(tmp_path, bridge):
    run = make_state_run(tmp_path, "continuity-bible")
    (run / "song-choices").mkdir()
    (run / "song-choices" / "state.json").write_text(
        json.dumps({"required": True, "offered": {}}), "utf-8")
    env = F.cmd_next(ns(run_dir=str(run)))
    assert env["outcome"] == "error" and env["reason_code"] == "SONG_PICK_MISSING", env


def test_next_script_answer_becomes_script_reply(tmp_path, bridge, monkeypatch):
    bridge._answer = "approve, love it"
    run = make_state_run(tmp_path, "music")
    (run / "control" / "studio-order.json").write_text(json.dumps(
        {"order_id": "o-1", "base_url": "https://studio.example"}), "utf-8")
    monkeypatch.setattr(F, "_script_gate",
                        lambda rd, a, reply=None: {"outcome": "waiting",
                                                   "reason": "script-sent",
                                                   "messages": [], "delivered": []})
    env = F.cmd_next(ns(run_dir=str(run)))
    assert env["outcome"] == "ok" and env["data"]["approval"] == "script", env
    cmd = env["data"]["command"]
    assert "factory.py script-reply" in cmd and "--reply 'approve, love it'" in cmd


def test_next_script_waiting_without_studio_stays_waiting(tmp_path, bridge, monkeypatch):
    run = make_state_run(tmp_path, "music")
    monkeypatch.setattr(F, "_script_gate",
                        lambda rd, a, reply=None: {"outcome": "waiting",
                                                   "reason": "script-sent",
                                                   "messages": [], "delivered": []})
    env = F.cmd_next(ns(run_dir=str(run)))
    assert env["outcome"] == "waiting" and \
        env["reason_code"] == "SCRIPT_AWAITING_APPROVAL", env


def test_studio_order_without_bridge_never_opens_a_gate(tmp_path, monkeypatch):
    """A studio run on a box that has no approvals_bridge (U2 not landed):
    publish is skipped, answers are None, every gate stays exactly as before."""
    monkeypatch.setattr(F, "_approvals_bridge", lambda: None)
    run = make_storyboard_run(tmp_path, studio=True)
    env = F.cmd_storyboard(ns(run_dir=str(run)))
    assert env["outcome"] == "waiting" and len(env["data"]["messages"]) == 1  # hand-back
    assert not (run / "control" / "studio-versions.json").exists()


def test_factory_module_still_imports_clean():
    """The card CLI's other formats and the storyboard hand-back shape did not
    move: text still renders, envelope keys stay put."""
    env = F.envelope("x", "r", "ok", "c", "n")
    assert set(env) >= {"schema_version", "command", "outcome", "data", "evidence"}
