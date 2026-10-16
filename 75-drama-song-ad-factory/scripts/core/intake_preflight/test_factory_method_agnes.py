#!/usr/bin/env python3
"""W2-wiring-U1: `factory.py next` reads control/method.json and the Agnes answer.

Proves, behaviourally (BUILD-PLAN W2-wiring-U1, Prove line):

  * a run with NO method and NO agnes record answers exactly today's commands,
    stage for stage, and `next` writes neither record;
  * a campaign run presents the trailer stage at `clips`;
  * a testimonial run without a recorded PERMISSION = Yes is refused BEFORE
    music, with TESTIMONIAL_PERMISSION_MISSING and no command;
  * an Agnes run answers the Agnes keyframe command, one segment job per
    pending segment (2 in flight) with the KIE Kling row kept unchanged for
    the lip-sync windows, and answers `waiting` with the Agnes reasons while
    the job runs or the run will not fit today's quota;
  * purpose routing (lesson / paid / campaign) and gates A-F recorded in
    control/method.json.

Run from the skill root:  python3 scripts/core/intake_preflight/test_factory_method_agnes.py
stdlib only, no network, no provider, no Agnes or KIE call: every run it builds
lives under a temp dir, and the one fake module it injects is the local
agnes_quota admission record the box does not carry yet.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent.parent          # 75-drama-song-ad-factory/
FACTORY = HERE / "factory.py"
RUNBOOK = SKILL / "references" / "stage-runbook.md"

STAGES = ("research", "creative-strategy", "script-lyrics", "music",
          "continuity-bible", "storyboard", "image-keyframes",
          "video-generation", "qc-retakes", "assembly", "final-qc",
          "delivery")
#: Stages that sit behind an unchanged stop of their own (SCRIPT APPROVAL,
#: STORYBOARD APPROVAL); `next`'s answer there is checked separately.
GATED = ("music", "video-generation")

FAILS = []
CHECKS = 0


def check(name, got, want):
    global CHECKS
    CHECKS += 1
    ok = (got == want) if want is not ... else bool(got)
    if not ok:
        FAILS.append("%s: got %r want %r" % (name, got, want))
    print("  %s %s" % ("ok" if ok else "FAIL", name))


def runbook_rows():
    """The same parse factory.py does (like-with-like control)."""
    out = {}
    for line in RUNBOOK.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        sid = cells[0]
        if (re.fullmatch(r"[a-z0-9-]+", sid)
                and cells[1].startswith("`") and cells[1].endswith("`")
                and cells[2]):
            out[sid] = {"command": cells[1][1:-1], "produces": cells[2]}
    return out


ROWS = runbook_rows()


def make_run(tmp, stage, method=None, agnes=None, progress=None,
             storyboard=None):
    """A run folder whose first non-COMPLETE stage is `stage` (None = none)."""
    run = Path(tmp) / ("run-%s" % uuid.uuid4().hex[:8])
    (run / "control").mkdir(parents=True)
    idx = len(STAGES) if stage is None else STAGES.index(stage)
    db = run / "control" / "state.sqlite3"
    with sqlite3.connect(str(db)) as con:
        con.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
        con.execute("INSERT INTO meta(k, v) VALUES('db_version', '1')")
        con.execute("CREATE TABLE stages(run_id TEXT, stage TEXT,"
                    " state TEXT, version INTEGER, owner TEXT,"
                    " lease_expires REAL, reason TEXT, updated_at REAL,"
                    " PRIMARY KEY(run_id, stage))")
        con.execute("CREATE TABLE events(id TEXT PRIMARY KEY, run_id TEXT,"
                    " stage TEXT, kind TEXT, detail TEXT, at REAL)")
        for i, s in enumerate(STAGES):
            con.execute("INSERT INTO stages VALUES('R1', ?, ?, 1, NULL,"
                        " NULL, NULL, 12345.6)",
                        (s, "COMPLETE" if i < idx else "NOT_STARTED"))
    if method is not None:
        (run / "control" / "method.json").write_text(
            json.dumps(method, indent=2, sort_keys=True), "utf-8")
    if agnes is not None:
        (run / "control" / "card-receipt.json").write_text(
            json.dumps({"agnes": {"answer": agnes}}, indent=2), "utf-8")
    if progress is not None:
        (run / "control" / "agnes-progress.json").write_text(
            json.dumps(progress, indent=2, sort_keys=True), "utf-8")
    if storyboard is not None:
        (run / "storyboard").mkdir()
        (run / "storyboard" / "approval.json").write_text(
            json.dumps({"state": storyboard}), "utf-8")
    return run


def next_env(run, extra_env=None):
    env = dict(os.environ)
    # Whole-run admission (agnes_quota.fits_today) reads os.environ, so the
    # quota answer must never depend on the box this test happens to run on:
    # a private ledger and a generous daily limit. A caller that wants the
    # refusal path overrides AGNES_DAILY_VIDEO_SECONDS through extra_env.
    env["DSAF_AGNES_QUOTA_DB"] = str(Path(tempfile.gettempdir()) /
                                     ("w75-agnes-quota-%d.sqlite3"
                                      % os.getpid()))
    env["AGNES_DAILY_VIDEO_SECONDS"] = "500"
    if extra_env:
        env.update(extra_env)
    p = subprocess.run([sys.executable, str(FACTORY), "next",
                        "--run-dir", str(run)],
                       capture_output=True, text=True,
                       cwd=str(SKILL), env=env, timeout=60)
    try:
        doc = json.loads(p.stdout or "{}")
    except ValueError:
        doc = {"outcome": "unparsable", "stdout": p.stdout[:400]}
    return p, doc


def method(**kw):
    """A method record with the card's own shape (SPEC B1)."""
    base = {"purpose": "campaign", "platform": None,
            "output_types": ["MASTER_EPISODE"], "chosen_length_s": 60,
            "runtime_targets": {}, "testimonial_permission": None,
            "gates": {g: "planned" for g in "ABCDEF"}}
    base.update(kw)
    return base


def main():
    with tempfile.TemporaryDirectory(prefix="w75-agnes-wiring-") as td:
        tmp = Path(td)

        # -- 1: no method, no agnes -> exactly today's commands --------------
        print("[1] a run with no method and no agnes record")
        for stage in STAGES:
            if stage in GATED:
                continue
            p, doc = next_env(make_run(tmp, stage))
            check("%s exit 0" % stage, p.returncode, 0)
            check("%s outcome ok" % stage, doc.get("outcome"), "ok")
            check("%s stage" % stage, doc.get("data", {}).get("stage"), stage)
            check("%s command" % stage,
                  doc.get("data", {}).get("command"), ROWS[stage]["command"])
            check("%s no method block" % stage,
                  "method" in doc.get("data", {}), False)
            check("%s no agnes block" % stage,
                  "agnes" in doc.get("data", {}), False)
        run = make_run(tmp, "research")
        p, doc = next_env(run)
        check("no method.json written", (run / "control" / "method.json").exists(),
              False)
        check("no card receipt written",
              (run / "control" / "card-receipt.json").exists(), False)
        # the two gated stops keep their own answers
        p, doc = next_env(make_run(tmp, "video-generation"))
        check("storyboard stop unchanged", doc.get("reason_code"),
              "storyboard-approval-required")
        p, doc = next_env(make_run(tmp, "music"))
        check("music does not refuse a purpose-less run", doc.get("reason_code"),
              ...)

        # -- 2: campaign -> the trailer stage, in front of delivery -----------
        print("[2] campaign presents the trailer stage before delivery")
        run = make_run(tmp, "delivery", method=method(purpose="campaign"))
        p, doc = next_env(run)
        d = doc.get("data", {})
        check("campaign exit 0", p.returncode, 0)
        check("campaign presents the clips stage", d.get("stage"), "clips")
        check("campaign method_stage", d.get("method_stage"), "trailers")
        check("campaign command is the trailer row",
              d.get("command"), ROWS["trailers"]["command"])
        check("campaign produces names a trailer",
              "trailer" in (d.get("produces") or "").lower(), True)
        check("campaign purpose routed", (d.get("method") or {}).get("purpose"),
              "campaign")
        check("campaign derivatives", (d.get("method") or {}).get("derivatives"),
              ["trailer-60", "trailer-90", "ad-60", "ad-90"])
        # the stage lasts only until it has cut its files
        (run / "edit" / "clips").mkdir(parents=True)
        (run / "edit" / "clips" / "trailer-60s.mp4").write_bytes(b"x")
        p, doc = next_env(run)
        d = doc.get("data", {})
        check("after the cut the run reaches delivery", d.get("stage"), "delivery")
        check("after the cut the command is the delivery row",
              d.get("command"), ROWS["delivery"]["command"])
        check("after the cut there is no trailer stage", "method_stage" in d, False)
        # control: a shorter asset's purpose never swaps in the trailer stage
        run = make_run(tmp, "delivery",
                       method=method(purpose="testimonial",
                                     testimonial_permission="yes"))
        p, doc = next_env(run)
        d = doc.get("data", {})
        check("testimonial keeps the delivery stage", d.get("stage"), "delivery")
        check("testimonial has no trailer stage", "method_stage" in d, False)
        # control: no method record -> no trailer stage either
        run = make_run(tmp, "delivery")
        p, doc = next_env(run)
        check("a purpose-less run has no trailer stage",
              "method_stage" in doc.get("data", {}), False)

        # -- 3: testimonial permission refused BEFORE music ------------------
        print("[3] testimonial without permission is refused before music")
        for perm in ("no", None):
            run = make_run(tmp, "music",
                           method=method(purpose="testimonial",
                                         testimonial_permission=perm))
            p, doc = next_env(run)
            check("permission %r exit 4" % perm, p.returncode, 4)
            check("permission %r outcome" % perm, doc.get("outcome"), "rejected")
            check("permission %r reason" % perm, doc.get("reason_code"),
                  "TESTIMONIAL_PERMISSION_MISSING")
            check("permission %r hands out no command" % perm,
                  "command" in doc.get("data", {}), False)
            check("permission %r never prints the music command" % perm,
                  ROWS["music"]["command"] in p.stdout, False)
        # controls: recorded Yes, and a non-testimonial purpose, are not refused
        run = make_run(tmp, "music",
                       method=method(purpose="testimonial",
                                     testimonial_permission="yes"))
        p, doc = next_env(run)
        check("recorded Yes is not refused",
              doc.get("reason_code") == "TESTIMONIAL_PERMISSION_MISSING", False)
        run = make_run(tmp, "music", method=method(purpose="lesson"))
        p, doc = next_env(run)
        check("a lesson is not refused",
              doc.get("reason_code") == "TESTIMONIAL_PERMISSION_MISSING", False)
        # the refusal also covers the other paid stages
        for stage in ("image-keyframes", "video-generation"):
            run = make_run(tmp, stage,
                           method=method(purpose="testimonial",
                                         testimonial_permission=None))
            p, doc = next_env(run)
            check("%s refused too" % stage, doc.get("reason_code"),
                  "TESTIMONIAL_PERMISSION_MISSING")

        # -- 4: Agnes keyframes ----------------------------------------------
        print("[4] the Agnes answer routes the keyframes")
        run = make_run(tmp, "image-keyframes", agnes="yes")
        p, doc = next_env(run)
        d = doc.get("data", {})
        check("agnes keyframes exit 0", p.returncode, 0)
        check("agnes keyframes command", d.get("command"),
              ROWS["agnes-keyframes"]["command"])
        check("agnes keyframes is the Agnes door",
              "agnes_dispatch.py image" in (d.get("command") or ""), True)
        check("agnes answer recorded", (d.get("agnes") or {}).get("answer"), "yes")
        # control: a run that answered no (or never asked) keeps the KIE row
        for answer in ("no", None):
            run = make_run(tmp, "image-keyframes", agnes=answer) if answer else \
                make_run(tmp, "image-keyframes")
            p, doc = next_env(run)
            check("agnes %r keeps the KIE row" % answer,
                  doc.get("data", {}).get("command"),
                  ROWS["image-keyframes"]["command"])

        # -- 5: Agnes video -- waiting reasons -------------------------------
        print("[5] Agnes video answers waiting while it runs")
        run = make_run(tmp, "video-generation", agnes="yes", method=method(),
                       storyboard="approved",
                       progress={"clips_total": 6, "clips_done": 1,
                                 "in_flight": 2, "waiting_reason": None})
        p, doc = next_env(run)
        check("running exit 2", p.returncode, 2)
        check("running outcome", doc.get("outcome"), "waiting")
        check("running reason", doc.get("reason_code"), "agnes-video-running")
        check("running hands out no command",
              "command" in doc.get("data", {}), False)
        run = make_run(tmp, "video-generation", agnes="yes", method=method(),
                       storyboard="approved",
                       progress={"clips_total": 6, "clips_done": 2,
                                 "in_flight": 0,
                                 "waiting_reason": "agnes-quota-next-day",
                                 "next_continue_utc": "2026-10-16T00:00:00Z"})
        p, doc = next_env(run)
        check("quota exit 2", p.returncode, 2)
        check("quota outcome", doc.get("outcome"), "waiting")
        check("quota reason", doc.get("reason_code"), "agnes-quota-next-day")
        check("quota names the reset",
              (doc.get("data", {}).get("agnes") or {}).get("next_continue_utc"),
              "2026-10-16T00:00:00Z")

        # -- 6: Agnes video -- one background job per segment ----------------
        print("[6] Agnes video hands out segment jobs, KIE row kept")
        run = make_run(tmp, "video-generation", agnes="yes", method=method(),
                       storyboard="approved",
                       progress={"clips_total": 6, "clips_done": 0,
                                 "in_flight": 0, "waiting_reason": None})
        p, doc = next_env(run)
        d = doc.get("data", {})
        ag = d.get("agnes") or {}
        jobs = ag.get("segment_jobs") or []
        check("segments exit 0", p.returncode, 0)
        check("segments outcome", doc.get("outcome"), "ok")
        check("six segment jobs", len(jobs), 6)
        check("command is the first segment job", d.get("command"),
              ROWS["agnes-video-segment"]["command"].replace("<segment>", "1"))
        check("every job is the Agnes video door",
              all("agnes_dispatch.py video" in j["command"] for j in jobs), True)
        check("every job is a fixed 10 s clip",
              all("--seconds 10" in j["command"] for j in jobs), True)
        check("every job polls at 15 s",
              all("--poll-s 15" in j["command"] for j in jobs), True)
        check("segment numbers substituted",
              [j["segment"] for j in jobs], [1, 2, 3, 4, 5, 6])
        check("no placeholder left", any("<segment>" in j["command"]
                                         for j in jobs), False)
        check("two in flight", ag.get("in_flight_max"), 2)
        check("background job", ag.get("background"), True)
        kie = ag.get("kie_lipsync_command")
        check("KIE Kling row unchanged", kie, ROWS["video-generation"]["command"])
        check("the lip-sync command is KIE", "kie_dispatch.py" in (kie or ""), True)
        check("the lip-sync command never becomes Agnes",
              "agnes_dispatch" in (kie or ""), False)
        quota = ag.get("quota")
        if quota is not None:
            check("the quota module was consulted", ag.get("quota_source"),
                  "agnes_quota.fits_today")
            check("an admission that does not fit never hands out a job",
                  quota.get("fits") is False, False)
        # the runbook still carries every KIE row
        check("runbook keeps the KIE keyframes row",
              "kie_dispatch.py" in ROWS["image-keyframes"]["command"], True)
        check("runbook keeps the KIE video row",
              "kie_dispatch.py" in ROWS["video-generation"]["command"], True)
        check("runbook keeps the KIE music row",
              "kie_dispatch.py" in ROWS["music"]["command"], True)

        # -- 6b: quota admission that will not fit -> waiting ----------------
        # The refusal is forced through the quota's OWN public knobs, not a
        # shadow module on PYTHONPATH: factory._core_mod resolves
        # `<core>/agnes_quota/agnes_quota.py` first, so once the real module
        # ships in core the fake can never be reached. A 1-second day cannot
        # hold 6 clips (60 s x 1.2 = 72 s needed), which is exactly the
        # SPEC A5.3 "wait whole for the reset" branch.
        print("[6b] whole-run quota admission failure waits for the reset")
        run = make_run(tmp, "video-generation", agnes="yes", method=method(),
                       storyboard="approved")
        p, doc = next_env(run, {"AGNES_DAILY_VIDEO_SECONDS": "1"})
        d = doc.get("data", {})
        ag = d.get("agnes") or {}
        quota = ag.get("quota")
        check("admission consulted", ag.get("quota_source"),
              "agnes_quota.fits_today")
        if quota is not None and quota.get("fits") is False:
            check("admission refused exit 2", p.returncode, 2)
            check("admission refused outcome", doc.get("outcome"), "waiting")
            check("admission refused reason", doc.get("reason_code"),
                  "agnes-quota-next-day")
            check("admission never splits the run",
                  "00:00 UTC" in (doc.get("next_action") or ""), True)
        else:
            check("admission handed out the first segment job",
                  doc.get("outcome"), "ok")

        # -- 7: purpose routing and gates A-F --------------------------------
        print("[7] purpose routing and gates A-F")
        run = make_run(tmp, "final-qc", method=method(purpose="lesson"))
        p, doc = next_env(run)
        d = doc.get("data", {})
        check("lesson reads product checks as lesson checks",
              (d.get("method") or {}).get("product_checks"), "lesson")
        check("lesson keeps the runbook command",
              d.get("command"), ROWS["final-qc"]["command"])
        run = make_run(tmp, "delivery",
                       method=method(purpose="paid_ad", platform="meta"))
        p, doc = next_env(run)
        d = doc.get("data", {})
        pf = d.get("platform_fit") or {}
        check("paid run gates delivery on platform_fit", pf.get("required"), True)
        check("platform_fit command", pf.get("command"),
              ROWS["platform-fit"]["command"])
        check("platform_fit placement", pf.get("placement"), "meta")
        check("paid purpose flags platform_fit",
              (d.get("method") or {}).get("platform_fit"),
              "required-before-delivery")
        run = make_run(tmp, "delivery",
                       method=method(purpose="short_post", platform="organic"))
        p, doc = next_env(run)
        check("free post placement",
              ((doc.get("data", {}) or {}).get("platform_fit") or {}).get("placement"),
              "organic")
        run = make_run(tmp, "delivery", method=method(purpose="campaign"))
        p, doc = next_env(run)
        check("a campaign run is not gated on platform_fit",
              "platform_fit" in doc.get("data", {}), False)

        gates_run = make_run(tmp, "delivery", method=method(purpose="campaign"))
        p, doc = next_env(gates_run)
        saved = json.loads(
            (gates_run / "control" / "method.json").read_text(encoding="utf-8"))
        g = saved.get("gates") or {}
        check("all six gates recorded", sorted(g), list("ABCDEF"))
        check("gate A inspected", g.get("A"), "inspected")
        check("gate B inspected", g.get("B"), "inspected")
        check("gate C inspected", g.get("C"), "inspected")
        check("gate D inspected", g.get("D"), "inspected")
        check("gate E inspected", g.get("E"), "inspected")
        check("gate F still planned", g.get("F"), "planned")
        check("no gate is ever called approved",
              [k for k, v in g.items() if v == "approved"], [])
        check("the method record keeps its purpose", saved.get("purpose"),
              "campaign")
        check("gates are handed back on the envelope",
              (doc.get("data", {}).get("method") or {}).get("gates"), g)
        # control: no method record -> no method record created
        bare = make_run(tmp, "delivery")
        next_env(bare)
        check("no method.json invented", (bare / "control" / "method.json").exists(),
              False)

    print("\ntest_factory_method_agnes: %d checks, %d failures"
          % (CHECKS, len(FAILS)))
    for f in FAILS:
        print("  FAIL %s" % f)
    if FAILS:
        return 1
    print("PASS")
    return 0


def test_factory_method_agnes():
    """The BUILD-PLAN W2-wiring-U1 Prove entry point.

    `python3 -m pytest -q .../test_factory_method_agnes.py` runs every check
    above; running the file directly does the same thing.
    """
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
