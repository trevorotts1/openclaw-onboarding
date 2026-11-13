#!/usr/bin/env python3
"""S75-072: one Studio storyboard answer may carry several shot notes.

The page sends the client's changes as ONE answer, one line per shot:

    shot 2: tighter close-up
    shot 3: brighter light

Proves, behaviourally, in this folder only:
  * a two-line answer marks TWO shots for revision -- each note lands in its
    own shot's contract, and the invalidation history records both shots,
    instead of the second line being folded into the first shot's change;
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
