#!/usr/bin/env python3
"""S75-072: one Studio storyboard answer may carry several shot notes.

The page sends the client's changes as ONE answer, one line per shot:

    shot 2: tighter close-up
    shot 3: brighter light

Proves, behaviourally, in this folder only:
  * a two-line answer marks TWO shots for revision -- each note lands in its
    own shot's contract, and the invalidation history records both shots,
    instead of the second line being folded into the first shot's change;
  * a two-line answer whose stills are NOT made yet loses nothing: the first
    note stops at its still, every note stays queued on the run, and the next
    `next` after each still lands applies the rest -- a client's second note is
    never dropped;
  * a one-line answer still produces the one `storyboard --reply` command it
    always did, and changes nothing on disk (the command path is unchanged);
  * a plain GO answer is untouched (still `storyboard --reply GO`).

stdlib only: no pytest import (CI runs every test_*.py under scripts/core with
bare python3 and a fresh empty HOME). Every test is a zero-argument `test_*`
function with plain asserts, so the SAME file runs both ways:

  python3 75-drama-song-ad-factory/scripts/core/intake_preflight/test_studio_multi_shot_s75_072.py
  python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/intake_preflight

No network, no provider, no openclaw binary; writes only under a temp dir.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent

for _p in (str(CORE), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import factory as F                                   # noqa: E402
import test_factory_studio as TS                      # noqa: E402

STAGE = "video-generation"
TWO_NOTES = "shot 2: tighter close-up\nshot 3: brighter light"


def presented_run(tmp):
    """A three-shot studio run already shown once (round one on the page)."""
    run = TS.make_storyboard_run(tmp, studio=True)
    with TS.bridge():
        TS.F.cmd_storyboard(TS.ns(run_dir=str(run)))
    return run


def clear_redos(run, shot_ids):
    """The runner's own redo contract: a redone still lands before the reply."""
    redo = Path(run) / "storyboard" / "redo"
    redo.mkdir(exist_ok=True)
    for sid in shot_ids:
        (redo / (sid + ".png")).write_bytes(b"png")


def contracts(run):
    return json.loads((Path(run) / "storyboard" / "contracts.json")
                      .read_text(encoding="utf-8"))


def test_two_line_answer_marks_two_shots_for_revision():
    with TS.tmpdir("ds-shot-") as tmp:
        run = presented_run(tmp)
        clear_redos(run, ("s2", "s3"))
        with TS.bridge():
            env = F._studio_apply("next", Path(run).name, run, STAGE,
                                  "storyboard", TWO_NOTES)
        assert env["outcome"] == "ok", env
        assert env["data"]["shot_ids"] == ["s2", "s3"], env
        assert [row["action"] for row in env["data"]["applied"]] == \
            ["revised", "revised"], env
        got = contracts(run)
        # each note landed on ITS OWN shot -- never both on the first one
        assert got["s2"]["character_action"] == "tighter close-up", got["s2"]
        assert got["s3"]["character_action"] == "brighter light", got["s3"]
        assert got["s1"]["character_action"] == "sitting at table 1", got["s1"]
        approval = json.loads((Path(run) / "storyboard" / "approval.json")
                              .read_text(encoding="utf-8"))
        revised = [i["shots"] for i in approval.get("invalidations") or []]
        assert ["s2"] in revised and ["s3"] in revised, revised


def test_two_line_answer_without_a_redone_still_keeps_every_note():
    """The real path: nothing is made yet, so the first note stops at its still."""
    with TS.tmpdir("ds-shot-") as tmp:
        run = presented_run(tmp)                      # NO redo/<sid>.png written
        with TS.bridge():
            env = F._studio_apply("next", Path(run).name, run, STAGE,
                                  "storyboard", TWO_NOTES)
        assert env["outcome"] == "waiting", env
        assert env["reason_code"] == "regenerate_still", env
        assert env["data"]["shot_ids"] == ["s2"], env
        queued = json.loads((Path(run) / "control" / "studio-shot-notes.json")
                            .read_text(encoding="utf-8"))
        assert queued == ["shot 2: tighter close-up", "shot 3: brighter light"], queued
        got = contracts(run)
        assert got["s2"]["character_action"] == "sitting at table 2", got["s2"]
        assert got["s3"]["character_action"] == "sitting at table 3", got["s3"]


def test_queued_notes_apply_once_each_still_lands():
    with TS.tmpdir("ds-shot-") as tmp:
        run = presented_run(tmp)
        with TS.bridge():
            F._studio_apply("next", Path(run).name, run, STAGE, "storyboard", TWO_NOTES)
        clear_redos(run, ("s2",))
        with TS.bridge():
            env = F._studio_notes_drain("next", Path(run).name, run, STAGE)
        assert env["outcome"] == "waiting", env          # shot 3 still owes a still
        assert env["data"]["shot_ids"] == ["s2", "s3"], env
        got = contracts(run)
        assert got["s2"]["character_action"] == "tighter close-up", got["s2"]
        assert got["s3"]["character_action"] == "sitting at table 3", got["s3"]
        clear_redos(run, ("s3",))
        with TS.bridge():
            env = F._studio_notes_drain("next", Path(run).name, run, STAGE)
        assert env["outcome"] == "ok", env
        got = contracts(run)
        assert got["s2"]["character_action"] == "tighter close-up", got["s2"]
        assert got["s3"]["character_action"] == "brighter light", got["s3"]
        assert got["s1"]["character_action"] == "sitting at table 1", got["s1"]
        assert not (Path(run) / "control" / "studio-shot-notes.json").exists()


def test_next_drains_the_queued_notes_after_the_stills_land():
    """`next` itself resumes the queue -- no new client answer is needed."""
    with TS.tmpdir("ds-state-") as tmp:
        run = TS.make_state_run(tmp, "video-generation")
        (Path(run) / "control" / "studio-order.json").write_text(json.dumps(
            {"order_id": "o-1", "base_url": "https://studio.example"}), "utf-8")
        with TS.bridge():
            TS.F.cmd_storyboard(TS.ns(run_dir=str(run)))
        with TS.bridge(answer=TWO_NOTES):
            TS.F.cmd_next(TS.ns(run_dir=str(run)))
        queued = json.loads((Path(run) / "control" / "studio-shot-notes.json")
                            .read_text(encoding="utf-8"))
        assert queued[0] == "shot 2: tighter close-up", queued
        clear_redos(run, ("s2", "s3"))
        with TS.bridge():                       # no new answer: the run owes these
            TS.F.cmd_next(TS.ns(run_dir=str(run)))
        got = json.loads((Path(run) / "storyboard" / "contracts.json")
                         .read_text(encoding="utf-8"))
        assert got["s2"]["character_action"] == "tighter close-up", got["s2"]
        assert got["s3"]["character_action"] == "brighter light", got["s3"]
        assert not (Path(run) / "control" / "studio-shot-notes.json").exists()


def test_one_line_answer_keeps_the_single_command():
    with TS.tmpdir("ds-shot-") as tmp:
        run = presented_run(tmp)
        before = contracts(run)
        with TS.bridge():
            env = F._studio_apply("next", Path(run).name, run, STAGE,
                                  "storyboard", "shot 2: tighter close-up")
        assert env["outcome"] == "ok", env
        cmd = env["data"]["command"]
        assert "factory.py storyboard" in cmd and "--reply" in cmd, env
        assert "tighter close-up" in cmd, env
        assert contracts(run) == before            # a command changes nothing


def test_plain_go_answer_is_unchanged():
    with TS.tmpdir("ds-shot-") as tmp:
        run = presented_run(tmp)
        with TS.bridge():
            env = F._studio_apply("next", Path(run).name, run, STAGE,
                                  "storyboard", "GO")
        assert env["outcome"] == "ok", env
        assert "--reply GO" in env["data"]["command"], env


TESTS = [
    test_two_line_answer_marks_two_shots_for_revision,
    test_two_line_answer_without_a_redone_still_keeps_every_note,
    test_queued_notes_apply_once_each_still_lands,
    test_next_drains_the_queued_notes_after_the_stills_land,
    test_one_line_answer_keeps_the_single_command,
    test_plain_go_answer_is_unchanged,
]


def main():
    fails = []
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            fails.append("%s: %s: %s" % (t.__name__, type(e).__name__, e))
    print("\ntest_studio_multi_shot_s75_072: %s (%d tests, %d failures)"
          % ("PASS" if not fails else "FAIL", len(TESTS), len(fails)))
    for f in fails:
        print(" - FAILED: %s" % f)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
