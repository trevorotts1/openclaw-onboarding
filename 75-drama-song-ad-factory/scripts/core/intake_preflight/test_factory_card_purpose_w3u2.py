#!/usr/bin/env python3
"""S75X-W3-U2: a NEW run enters the Drama-to-Demand strategy through every
supported launcher, and a resumed run is untouched.

Before this unit the purpose card was a `--purpose-flow` flag no launcher ever
passed, so `_method_record` answered None for every new run and the method
guard was inert. What is proved here, behaviourally:

  * a NEW run through `factory.py card --step --run-dir` (Claude Code chat) is
    asked the purpose card and ends with control/method.json on disk;
  * the same run through `--format telegram-json` (the Telegram launcher);
  * unreceipted bulk orders through `studio_bridge._replay` fail closed;
    a Studio marker does not authorize invented or unseen question answers;
  * a RESUMED run (stage work recorded, answers saved) keeps the card it
    started on: the legacy list, byte-identical answers, no method.json;
  * `--no-purpose-flow` still asks the pre-method card on a new run;
  * the method record is derived from the run's own saved answers when the file
    is missing, and never invented for a run with no PURPOSE answer.

Run from the skill root:
    python3 scripts/core/intake_preflight/test_factory_card_purpose_w3u2.py
Stdlib only, no network, no provider, no paid call.
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
SKILL = CORE.parent.parent
for p in (str(CORE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import factory as F                                             # noqa: E402
from state_store import Store                                  # noqa: E402
from choice_card.intake_card import intake_card as IC           # noqa: E402

STAGES = ("research", "creative-strategy", "script-lyrics", "music",
          "continuity-bible", "storyboard", "image-keyframes",
          "video-generation", "qc-retakes", "assembly", "final-qc", "delivery")

FAILS = []
CHECKS = 0


def check(name, got, want):
    global CHECKS
    CHECKS += 1
    ok = (got == want)
    if not ok:
        FAILS.append("%s: got %r want %r" % (name, got, want))
    print("  %s %s" % ("ok" if ok else "FAIL", name))


def check_true(name, got):
    check(name, bool(got), True)


def make_run(tmp, advanced=0):
    """A run folder: `advanced` stages past NOT_STARTED (0 = a NEW run)."""
    run = Path(tmp) / "run"
    (run / "control").mkdir(parents=True, exist_ok=True)
    with Store(run / "control" / "state.sqlite3") as store:
        store.init_run("R", STAGES)
        for stage in STAGES[:advanced]:
            store.transition("R", stage, "READY", "fixture")
            store.claim("R", stage, "fixture")
            store.transition("R", stage, "COMPLETE", "fixture")
    return run


def purpose_replies():
    """Every reply the purpose card asks for, in its own order, then yes.

    Walked through the card's OWN `_shaped`, so the list follows the question
    order the run is actually asked (a campaign's EPISODE LENGTH takes LENGTH's
    slot; a testimonial gains PERMISSION) instead of a hard-coded count."""
    answers, replies = [], []
    for _ in range(60):
        qs = IC._shaped(IC.QUESTIONS, answers)
        if len(answers) >= len(qs):
            return replies + ["yes"]
        q = qs[len(answers)]
        if q["id"] == "spend":
            reply = "$25"
        elif q.get("free_text"):
            reply = "Sweet Details Cookie-Decorating Class"
        elif q.get("recommended") is None:
            reply = "1"
        else:
            reply = "recommended"
        a = IC._parse(reply, q)
        assert a and "error" not in a, (q["id"], reply, a)
        replies.append(reply)
        answers.append(a)
    raise AssertionError("the card never reached its recap")


def legacy_replies():
    """The pre-method card's replies (one per question of IC.QUESTIONS)."""
    return IC.example_replies()[:-1] + ["1", "yes"]


def drive(run, replies, fmt="text", extra=()):
    """Render before each explicit reply through the supported CLI launcher."""
    argv = ["card", "--step", "--run-dir", str(run), "--format", fmt]
    argv.extend(extra)
    out = io.StringIO()
    with redirect_stdout(out):
        code = F.main(argv)
    for reply in replies:
        out = io.StringIO()
        with redirect_stdout(out):
            code = F.main(argv + ["--reply", reply])
    return code, out.getvalue()


def main():
    replies = purpose_replies()
    with tempfile.TemporaryDirectory(prefix="w3u2-card-") as tmp:
        # -- 1: Claude Code chat launcher, a NEW run --------------------------
        print("[1] a NEW run through the Claude Code chat launcher")
        run = make_run(tmp)
        check("launcher chooses the purpose card for a new run",
              F._purpose_flow_for(str(run), None), True)
        code, text = drive(run, replies)
        check("exit 0", code, 0)
        check_true("the recap locked in", "Locked in" in text)
        method_path = run / "control" / "method.json"
        check_true("control/method.json written", method_path.exists())
        record = json.loads(method_path.read_text(encoding="utf-8"))
        check("purpose recorded", record.get("purpose"), "campaign")
        check("gates A-F planned", record.get("gates"),
              {g: "planned" for g in "ABCDEF"})
        check("factory reads it back", F._method_record(str(run)).get("purpose"),
              "campaign")
        # ...and the run ENTERS the upgraded strategy: `next` now answers with
        # the purpose block and the gate levels instead of the bare command.
        out = io.StringIO()
        with redirect_stdout(out):
            next_code = F.main(["next", "--run-dir", str(run)])
        nxt = json.loads(out.getvalue())
        check("next exits 0", next_code, 0)
        check("next hands out the purpose block",
              (nxt.get("data", {}).get("method") or {}).get("purpose"), "campaign")
        check("the gates were synced into the record",
              sorted(json.loads(method_path.read_text(encoding="utf-8"))["gates"]),
              list("ABCDEF"))

        # -- 2: the Telegram launcher, a NEW run ------------------------------
        print("[2] a NEW run through the Telegram launcher")
        run = make_run(Path(tmp) / "tg")
        code, payload = drive(run, replies, fmt="telegram-json")
        check("exit 0", code, 0)
        sent = json.loads(payload)
        check_true("the one message was built", isinstance(sent, dict) and "send" in sent)
        check_true("control/method.json written",
                   (run / "control" / "method.json").exists())

        # -- 3: the Studio launcher (what `studio_bridge.py poll` runs) -------
        print("[3] a NEW Studio order through studio_bridge._replay")
        bridge_dir = SKILL / "shared-bridge"
        if str(bridge_dir) not in sys.path:
            sys.path.insert(0, str(bridge_dir))
        import studio_bridge as SB                               # noqa: PLC0415
        run = make_run(Path(tmp) / "studio")
        # poll writes the order marker BEFORE it replays the answers.
        (run / "control" / "studio-order.json").write_text(
            json.dumps({"order_id": "ord-w3u2", "client_id": "c1", "title": "t"}),
            encoding="utf-8")
        capture = io.StringIO()
        with redirect_stdout(capture):
            code, factory_path = SB._replay(str(SKILL), run, replies)
        check("unreceipted bulk Studio order refused", code, SB.EXIT["error"])
        check("bridge exposes a named replay refusal",
              json.loads(capture.getvalue()).get("code"), "REPLAY_FAILED")
        check("the launcher it shelled out to is factory.py",
              Path(factory_path).resolve(), Path(F.__file__).resolve())
        check("no method record claimed without accepted replies",
              (run / "control" / "method.json").exists(), False)
        stored = json.loads((run / "control" / "intake-session.json").read_text())
        check("no bulk answer was silently consumed", stored["answered_count"], 0)

        # -- 4: a RESUMED run is untouched -----------------------------------
        print("[4] a RESUMED run keeps the card it started on")
        run = make_run(Path(tmp) / "resumed", advanced=3)
        # The approved artifacts a resumed run already carries.
        (run / "storyboard").mkdir()
        approved = json.dumps({"state": "approved", "shots": ["s1", "s2"]},
                              indent=2, sort_keys=True)
        (run / "storyboard" / "approval.json").write_text(approved, encoding="utf-8")
        (run / "storyboard" / "gate.json").write_text(approved, encoding="utf-8")
        saved = json.dumps([{"id": "song", "n": 1, "text": "Yes"}], indent=2)
        (run / "card-answers.json").write_text(saved, encoding="utf-8")
        check("launcher keeps the legacy card for a resumed run",
              F._purpose_flow_for(str(run), None), False)
        code, text = drive(run, legacy_replies())
        check("exit 0", code, 0)
        check_true("the legacy recap locked in", "Locked in" in text)
        check("no method.json invented",
              (run / "control" / "method.json").exists(), False)
        check("the approved storyboard artifacts are byte-identical",
              [(run / "storyboard" / n).read_text(encoding="utf-8")
               for n in ("approval.json", "gate.json")], [approved, approved])
        rows = json.loads((run / "card-answers.json").read_text(encoding="utf-8"))
        rows = rows.get("answers") if isinstance(rows, dict) else rows
        check("the resumed run stayed on the legacy list",
              [r["id"] for r in rows], [q["id"] for q in IC.QUESTIONS])

        # -- 5: the explicit switches still win ------------------------------
        print("[5] the explicit switches still win")
        run = make_run(Path(tmp) / "forced-off")
        code, text = drive(run, legacy_replies(), extra=["--no-purpose-flow"])
        check("exit 0", code, 0)
        check("--no-purpose-flow keeps the legacy card",
              (run / "control" / "method.json").exists(), False)
        run = make_run(Path(tmp) / "forced-on", advanced=3)
        code, text = drive(run, replies, extra=["--purpose-flow"])
        check("exit 0", code, 0)
        check_true("--purpose-flow asks the purpose card on a resumed run",
                   (run / "control" / "method.json").exists())
        # A run that already ANSWERED the purpose card stays on it, even when
        # the record itself has not landed yet (its answers carry the id).
        run = make_run(Path(tmp) / "answered", advanced=2)
        (run / "card-answers.json").write_text(json.dumps({"schema_version": 2, "answers": [
            {"id": "purpose", "n": 1, "text": "Grow my business"}]}), encoding="utf-8")
        check("a purpose-answered run resumes on the purpose card",
              F._purpose_flow_for(str(run), None), True)

        # -- 6: the record is derived from the run's OWN answers -------------
        print("[6] derived once from the run's own answers, never invented")
        run = make_run(Path(tmp) / "derived")
        drive(run, replies)
        (run / "control" / "method.json").unlink()
        check("a missing record is rebuilt from card-answers.json",
              F._method_record(str(run)).get("purpose"), "campaign")
        check_true("and written back", (run / "control" / "method.json").exists())
        legacy = make_run(Path(tmp) / "legacy-answers", advanced=1)
        (legacy / "card-answers.json").write_text(json.dumps(
            {"schema_version": 2,
             "answers": [{"id": "length", "n": 1, "text": "60 seconds"}]}),
            encoding="utf-8")
        check("no PURPOSE answer -> no record",
              F._method_record(str(legacy)), None)
        check("and nothing is written",
              (legacy / "control" / "method.json").exists(), False)
        bare = make_run(Path(tmp) / "bare")
        check("a run with no answers has no record",
              F._method_record(str(bare)), None)
        check("and nothing is written",
              (bare / "control" / "method.json").exists(), False)

    print("\ntest_factory_card_purpose_w3u2: %d checks, %d failures"
          % (CHECKS, len(FAILS)))
    for f in FAILS:
        print("  FAIL %s" % f)
    if FAILS:
        return 1
    print("PASS")
    return 0


def test_factory_card_purpose_w3u2():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
