#!/usr/bin/env python3
"""Mocked tests for core/smp/weekly_step (Owner D27 / plan 6.15 / decision 35).

Covered, one test per acceptance rule:
  Skill 74 mode precedence (env > conf > shadow; unknown -> shadow) | active
  only dispatches | off / shadow / unknown-mode / style-disabled all write
  drama-song-skipped.json, exit 0, plain-English client reason | skip reason
  never offers another provider or a private client | one 9:16 brief per week
  from the Theme of the Week | style defaults Lifelike 3D / Soul Ballad /
  All Suno / 60 | 59.0 s hard cap (62.5 fails, 59.0 passes) | 90-second
  window 88-95 s | every connected channel accepted or rejected with a
  reason (7-channel 60 route; 90 never on Shorts or the Instagram feed;
  Google Business Profile never; Stories take the teaser only) | injected
  router wins | dispatch is exactly one mocked Skill 75 intake call, argv
  carries no key and no KIE host | --dry-run never dispatches | CLI exit
  codes | envelope shape.

Manual C4 honesty (one check per step): the WHOLE multi-line factory reply
  is parsed, never the last line | the factory `outcome` maps straight
  through -- `waiting` keeps its reason_code and questions, and no other
  outcome is ever `ok` | `ok` requires video_path AND the file on disk,
  otherwise `pending-production` (exit 2) plus the B1 stage-hook hand-off |
  the weekly brief carries offer, audience, action, budget_minor and
  budget_currency | manual L2: no local ROUTE / NEVER / channel_acceptance
  body, no "Threads" literal, and a missing length_routing refuses by name.

Zero paid calls / no transport / no operator paths / no media files: the
module is scanned statically and every dispatch goes through an injected
mock runner; the module directory is walked for media extensions.

Run: python3 core/smp/weekly_step/test_weekly_step.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                      # core/smp/weekly_step/

try:                                   # pytest imports the weekly_step PACKAGE
    from weekly_step import weekly_step as V       # noqa: E402
except ImportError:                    # script run gets the module file
    import weekly_step as V                        # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if not cond else ""))
    if not cond:
        FAILS.append(name)


# --- helpers ---------------------------------------------------------------

def tmp_env(home, mode=None, oc=None):
    env = {"HOME": str(home)}
    if mode is not None:
        env["KIE_LIVE_ADAPTER_MODE"] = mode
    if oc is not None:
        env["OC_CONFIG"] = str(oc)
    return env


def run(env=None, **kw):
    kw.setdefault("theme", "Stack the offer before the cart closes")
    with tempfile.TemporaryDirectory() as d:
        kw.setdefault("out_dir", d)
        kw.setdefault("env", env if env is not None else {"HOME": d})
        res, _ = V.run_weekly(**kw)
        files = sorted(p.name for p in Path(d).iterdir())
        blob = {}
        for name in files:
            blob[name] = json.loads((Path(d) / name).read_text())
        return res, files, blob


_VID_DIR = tempfile.TemporaryDirectory()      # media never lands in the module


def touch_video(name="wk-video.mp4"):
    """A real file on disk: `ok` now requires video_path AND the file."""
    path = Path(_VID_DIR.name) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return str(path)


def pretty(payload):
    """Skill 75 prints indented, multi-line JSON (factory.py json.dump)."""
    return json.dumps(payload, indent=2, sort_keys=True)


class FakeRunner:
    """Injected dispatch: records argv, returns a Skill 75 style envelope."""

    def __init__(self, rc=0, payload=None, raw=None):
        self.calls = []
        self.rc = rc
        self.payload = payload if payload is not None else {
            "outcome": "ok", "reason_code": "complete-brief-zero-questions",
            "duration_s": 58.4, "video_path": touch_video(),
            "cost_cents": 475,
        }
        self.raw = raw

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        if self.raw is not None:
            return self.rc, self.raw, ""
        return self.rc, pretty(self.payload), ""


def write_style(path, **fields):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fields))
    return str(p)


def fake_factory(path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# fake Skill 75 entrypoint\n")
    return str(p)


# --- 1. Skill 74 mode gate -------------------------------------------------

with tempfile.TemporaryDirectory() as H:
    home = Path(H)
    check("mode defaults to shadow (nothing set)",
          V.resolve_kie_mode(env=tmp_env(home)) == "shadow")
    check("mode env wins", V.resolve_kie_mode(env=tmp_env(home, "active")) == "active")
    check("mode off read from env", V.resolve_kie_mode(env=tmp_env(home, "off")) == "off")
    check("unknown mode falls back to shadow",
          V.resolve_kie_mode(env=tmp_env(home, "live")) == "shadow")

    conf_dir = home / "oc"
    conf_dir.mkdir()
    (conf_dir / "kie-live-adapter-mode.conf").write_text("active\n")
    check("mode conf read when env unset",
          V.resolve_kie_mode(env=tmp_env(home, oc=conf_dir)) == "active")
    check("env beats conf",
          V.resolve_kie_mode(env=tmp_env(home, "off", oc=conf_dir)) == "off")
    check("json OC_CONFIG resolves to its directory",
          V.resolve_kie_mode(env=tmp_env(home, oc=conf_dir / "config.json")) == "active")

    check("kie_is_active only on active",
          V.kie_is_active(env=tmp_env(home, "active")) is True
          and V.kie_is_active(env=tmp_env(home, "shadow")) is False
          and V.kie_is_active(env=tmp_env(home)) is False)

# --- 2. skip paths (active mode only) --------------------------------------

reason = V.client_skip_reason("shadow")
check("client reason is plain English and says skipped + why",
      "skipped" in reason and "KIE connection" in reason
      and "Every other scheduled post still publishes" in reason)
check("client reason never offers another provider or a private client",
      not any(w in reason for w in (
          "fallback", "instead", "alternative provider", "direct client",
          "private", "OpenAI", "Google", "Anthropic", "run it yourself")))

off_reason = V.client_skip_reason(turned_off=True)
check("style-disabled reason is its own client-facing text",
      "switched off in your planner setup" in off_reason
      and "Every other scheduled post still publishes" in off_reason)

res, files, blob = run(env=tmp_env("/nonexistent-home-default"))
check("shadow mode writes drama-song-skipped.json and nothing else",
      res["status"] == "skipped" and files == ["drama-song-skipped.json"])
check("skip envelope is exit 0", V.exit_code_for(res["status"]) == 0)
check("skip reason reaches the file",
      blob["drama-song-skipped.json"]["reason"] == V.client_skip_reason("shadow"))
check("skip carries no video or cost",
      res.get("video") is None and res.get("cost_cents") is None)

res_off, files_off, _ = run(env=tmp_env("/x", "off"))
check("off mode skips with exit 0",
      res_off["status"] == "skipped" and V.exit_code_for(res_off["status"]) == 0
      and files_off == ["drama-song-skipped.json"])

with tempfile.TemporaryDirectory() as H:
    style = write_style(Path(H) / "style.json", enabled=False)
    res_dis, files_dis, blob_dis = run(
        env=tmp_env(H, "active"), style_file=style)
    check("style disabled skips without dispatch",
          res_dis["status"] == "skipped"
          and files_dis == ["drama-song-skipped.json"]
          and "planner setup" in blob_dis["drama-song-skipped.json"]["reason"])

res_bad, files_bad, _ = run(env=tmp_env("/x"), length=45)
check("bad length is rejected even while KIE is off (validation first)",
      res_bad["status"] == "rejected" and files_bad == []
      and V.exit_code_for(res_bad["status"]) == 4)

# --- 3. style defaults -----------------------------------------------------

style = V.load_style(path="/nonexistent/drama-song-style.json", env={"HOME": "/x"})
check("style defaults Lifelike 3D / Soul Ballad / All Suno / 60",
      style["look"] == "Lifelike 3D" and style["music"] == "Soul Ballad"
      and style["voice"] == "All Suno" and style["length"] == 60
      and style["enabled"] is True)

with tempfile.TemporaryDirectory() as H:
    p = write_style(Path(H) / "s.json", look="Sketch to Life",
                    music="R&B Flow", voice="Velvet Voiceover", length=90,
                    cta_text="Book the call", cta_link="https://example.test/cta")
    got = V.load_style(path=p, env={"HOME": H})
    check("saved style overrides every default",
          got["look"] == "Sketch to Life" and got["music"] == "R&B Flow"
          and got["voice"] == "Velvet Voiceover" and got["length"] == 90
          and got["cta_text"] == "Book the call"
          and got["cta_link"] == "https://example.test/cta")

with tempfile.TemporaryDirectory() as H:
    bad = Path(H) / "s.json"
    bad.write_text("{not json")
    got = V.load_style(path=str(bad), env={"HOME": H})
    check("unreadable style file falls back to defaults, never errors",
          got["look"] == "Lifelike 3D" and got["length"] == 60)

# --- 4. brief: one 9:16 ad from the Theme of the Week ----------------------

brief = V.build_brief("Stack the offer", style, length=60)
check("brief carries the theme verbatim",
      brief["theme"] == "Stack the offer" and brief["title"].endswith("Stack the offer"))
check("brief is 9:16 and one-per-week",
      brief["shape"] == "9:16" and brief["weekly"] is True
      and brief["one_per_week"] is True)
check("brief carries the client's style and CTA",
      brief["look"] == style["look"] and brief["music"] == style["music"]
      and brief["voice"] == style["voice"])
check("brief names its source planner step",
      brief["source"] == "35-social-media-planner/weekly-step")

# --- 5. hard cap and 90-second window --------------------------------------

ok, why = V.validate_duration(62.5, 60)
check("62.5 s fails the 59.0 cap (the approved ads run 62-63 s)",
      not ok and "59.0" in why,
      why)
check("59.0 s passes the cap exactly", V.validate_duration(59.0, 60)[0] is True)
check("58.9 s passes the cap", V.validate_duration(58.9, 60)[0] is True)
check("90-window accepts 88.0", V.validate_duration(88.0, 90)[0] is True)
check("90-window accepts 95.0", V.validate_duration(95.0, 90)[0] is True)
ok90, why90 = V.validate_duration(80.0, 90)
check("80 s fails the 90-second window",
      not ok90 and "88.0 to 95.0" in why90)
check("missing duration cannot pass",
      V.validate_duration(None, 60)[0] is False)

# --- 6. per-channel acceptance: length_routing is the only table -----------

LR = V._load_router()
check("sibling length_routing loads", LR is not None
      and callable(getattr(LR, "route_channels", None)))

SIXTY = list(LR.CHANNEL_LIMITS)           # 60 s reaches every destination
NINETY = list(LR.OPTION_90_CHANNELS)      # owner allow-list (SMP-W1-U4)

check("the default connected list comes from length_routing",
      list(V.default_connected()) == SIXTY,
      str(V.default_connected()))

connected = SIXTY + ["Google Business Profile", "Instagram Stories"]
plan60 = V.channel_acceptance(60, connected)
by = {row["channel"]: row for row in plan60}
check("60 route accepts every connected feed surface",
      all(by[c]["allowed"] for c in SIXTY),
      str([c for c in SIXTY if not by[c]["allowed"]]))
check("60 route covers seven channels", len(SIXTY) == 7)
check("Google Business Profile never accepted, with the verified-limit reason",
      by["Google Business Profile"]["allowed"] is False
      and "not verified" in by["Google Business Profile"]["reason"])
check("Stories carry the teaser only",
      by["Instagram Stories"]["allowed"] is False
      and "teaser" in by["Instagram Stories"]["reason"])
check("every row carries a reason",
      all(row.get("reason") for row in plan60))

plan90 = {row["channel"]: row for row in V.channel_acceptance(90, SIXTY)}
check("90 never posts to YouTube Shorts",
      plan90["YouTube Shorts"]["allowed"] is False
      and "60 seconds or less" in plan90["YouTube Shorts"]["reason"])
check("90 never posts to the Instagram feed",
      plan90["Instagram feed"]["allowed"] is False)
check("90 posts only to Facebook Reels, Instagram Reels, TikTok, LinkedIn",
      all(plan90[c]["allowed"] for c in NINETY),
      str([c for c in NINETY if not plan90[c]["allowed"]]))
check("90 never posts to Threads (owner allow-list, SMP-W1-U4)",
      plan90["Threads"]["allowed"] is False
      and plan90["Threads"]["reason"])
check("unknown channel rejected with a reason",
      V.channel_acceptance(60, ["MySpace"])[0]["allowed"] is False
      and V.channel_acceptance(60, ["MySpace"])[0]["reason"])


def fake_router(length, connected):
    return [{"channel": c, "allowed": c == "TikTok", "reason": "router wins"}
            for c in connected]


injected = V.channel_acceptance(60, ["TikTok", "Threads"], router=fake_router)
check("injected router wins over the loaded table",
      injected[0]["allowed"] is True and injected[1]["allowed"] is False
      and injected[0]["reason"] == "router wins")

# Manual L2: no local fallback ROUTE / NEVER / channel_acceptance body.
check("module keeps no local route table (L2)",
      not any(hasattr(V, name) for name in ("ROUTE", "NEVER", "STORIES_SUFFIX",
                                            "TEASER_REASON")))
check("the word Threads never appears in the weekly step source (L2)",
      "Threads" not in (HERE / "weekly_step.py").read_text(encoding="utf-8"))

# Without the sibling there is no second opinion: refuse by name.
_real_load = V._load_router
V._load_router = lambda: None
try:
    raised = False
    try:
        V.channel_acceptance(60, ["TikTok"])
    except RuntimeError:
        raised = True
    check("missing length_routing refuses by name, never a guessed plan",
          raised)
    ok_missing, why_missing = V.validate_duration(59.0, 60)
    check("missing length_routing cannot validate a duration",
          ok_missing is False and "length_routing" in why_missing)
    raised_default = False
    try:
        V.default_connected()
    except RuntimeError:
        raised_default = True
    check("missing length_routing refuses the default channel list too",
          raised_default)
finally:
    V._load_router = _real_load

# The duration gate itself is length_routing's, not a local copy.
ok_lr, why_lr = V.validate_duration(62.5, 60)
check("duration gate comes from length_routing (over-cap fails)",
      ok_lr is False and "59.0" in why_lr)
check("duration gate passes 59.0 exactly", V.validate_duration(59.0, 60)[0])
check("90 window comes from length_routing (88 and 95 pass, 80 fails)",
      V.validate_duration(88.0, 90)[0] and V.validate_duration(95.0, 90)[0]
      and V.validate_duration(80.0, 90)[0] is False)

# --- 7. dispatch: one mocked Skill 75 intake, no key, no KIE host ----------

with tempfile.TemporaryDirectory() as H:
    runner = FakeRunner()
    entry = fake_factory(Path(H) / "factory.py")
    style_file = write_style(Path(H) / "style.json", enabled=True)
    res, files, blob = run(env=tmp_env(H, "active"), style_file=style_file,
                           factory_entry=entry, runner=runner,
                           connected=["TikTok", "YouTube Shorts"])
    check("active mode dispatches exactly once", len(runner.calls) == 1)
    argv = runner.calls[0]
    check("argv is Skill 75 intake --brief-file",
          argv[1] == entry and argv[2] == "intake" and argv[3] == "--brief-file")
    check("brief file is written before dispatch",
          "drama-song-brief.json" in files and argv[4].endswith("drama-song-brief.json"))
    check("argv carries no key, no host, no mode override",
          not any("KEY" in a.upper() or "kie" in a.lower() or "http" in a.lower()
                  for a in argv[1:]))
    check("result file written with the video contract fields",
          "drama-song-result.json" in files
          and all(k in res for k in ("video_path", "stories_teaser_path",
                                     "duration_s", "cost_cents", "style",
                                     "channels")))
    check("duration under the cap and the file on disk keep status ok",
          res["status"] == "ok" and res["duration_s"] == 58.4
          and res.get("video_exists") is True,
          str(res.get("status")))
    check("cost recorded from the factory, never invented",
          res["cost_cents"] == 475)
    check("channels recorded for the planner schedule",
          [c["channel"] for c in res["channels"]] == ["TikTok", "YouTube Shorts"])
    on_disk = blob["drama-song-brief.json"]
    check("brief on disk is the dispatched 9:16 weekly brief",
          on_disk["theme"] == "Stack the offer before the cart closes"
          and on_disk["shape"] == "9:16" and on_disk["weekly"] is True
          and on_disk["length_option"] == 60)
    check("brief carries offer, audience, action and the weekly budget "
          "(manual C4 step 4)",
          all(k in on_disk for k in ("offer", "audience", "action",
                                     "budget_minor", "budget_currency")),
          str(sorted(on_disk)))
    check("brief carries the planner's own shape facts, so intake stops "
          "asking about placement",
          on_disk["placement"] == "9:16 vertical"
          and on_disk["aspect_ratio"] == "9:16"
          and on_disk["target_length_s"] == 60)
    check("a blank setup never invents an offer or a budget",
          on_disk["offer"] == "" and on_disk["budget_minor"] == 0
          and on_disk["budget_currency"] == "")
    check("result envelope carries the shared schema_version",
          res["schema_version"] == V.SCHEMA_VERSION
          and res["command"] == "weekly")

# (1) the WHOLE stdout is parsed -- Skill 75 prints indented multi-line JSON.
with tempfile.TemporaryDirectory() as H:
    waiting = {
        "schema_version": "blackceo.intake-preflight/envelope/v1",
        "command": "intake",
        "outcome": "waiting",
        "reason_code": "missing-essentials",
        "next_action": "Answer the bundled questions in one reply; "
                       "nothing else is asked.",
        "data": {
            "questions": [{"id": "offer", "question": "What is the offer?"},
                          {"id": "audience_action", "question": "Who is it for?"},
                          {"id": "spending_authority",
                           "question": "What is the weekly budget?"}],
            "question_message": "1. What is the offer?\n2. Who is it for?\n"
                                "3. What is the weekly budget?",
        },
        "evidence": [],
        "run_id": "abc123",
    }
    runner = FakeRunner(rc=2, payload=waiting)
    entry = fake_factory(Path(H) / "factory.py")
    res, _, blob = run(env=tmp_env(H, "active"), factory_entry=entry,
                       runner=runner)
    check("indented multi-line factory JSON is parsed whole (manual C4.1)",
          blob["drama-song-result.json"]["status"] == "waiting",
          str(blob.get("drama-song-result.json", {}).get("status")))
    check("waiting maps straight through with the factory reason_code",
          res["status"] == "waiting"
          and res["reason_code"] == "missing-essentials")
    check("waiting carries the factory questions",
          len(res["questions"]) == 3
          and "What is the offer?" in res["question_message"])
    check("waiting is exit 2 and never reported as ok",
          V.exit_code_for(res["status"]) == 2 and res["status"] != "ok")
    check("no 'intake failed' wording on a waiting week",
          "intake failed" not in json.dumps(res).lower())

# the run_factory seam itself: whole text, not the last line.
with tempfile.TemporaryDirectory() as H:
    entry = fake_factory(Path(H) / "factory.py")
    payload = {"outcome": "waiting", "reason_code": "missing-essentials",
               "data": {"questions": [], "question_message": "1. Q"}}
    call = V.run_factory(entry, Path(H) / "brief.json",
                         runner=lambda cmd: (2, pretty(payload), ""))
    check("run_factory parses the whole output, not the last line",
          isinstance(call["envelope"], dict)
          and call["envelope"]["outcome"] == "waiting",
          str(call["envelope"])[:80])
    call_bad = V.run_factory(entry, Path(H) / "brief.json",
                             runner=lambda cmd: (0, "line1\nline2\nnot json", ""))
    check("unparseable output yields no envelope (never an implicit ok)",
          call_bad["envelope"] is None)

# (3) ok only when video_path is set AND the file exists.
with tempfile.TemporaryDirectory() as H:
    runner = FakeRunner(payload={"outcome": "ok",
                                 "reason_code": "complete-brief-zero-questions",
                                 "duration_s": 58.4,
                                 "video_path": str(Path(H) / "gone.mp4"),
                                 "cost_cents": 100})
    entry = fake_factory(Path(H) / "factory.py")
    res, _, _ = run(env=tmp_env(H, "active"), factory_entry=entry,
                    runner=runner)
    check("factory ok but no file on disk is never reported as ok",
          res["status"] == "pending-production",
          str(res.get("status")))
    check("pending-production is exit 2 (waiting), not a silent success",
          V.exit_code_for(res["status"]) == 2)
    check("pending-production still carries the brief and the path",
          res["brief"]["theme"] and res["video_path"]
          and res["video_exists"] is False)

# no video_path at all -> pending-production too.
with tempfile.TemporaryDirectory() as H:
    runner = FakeRunner(payload={"outcome": "ok", "duration_s": None,
                                 "video_path": None})
    entry = fake_factory(Path(H) / "factory.py")
    res, _, _ = run(env=tmp_env(H, "active"), factory_entry=entry,
                    runner=runner)
    check("factory ok with no video_path is pending-production",
          res["status"] == "pending-production")

# the B1 stage hook is optional; when present it reports, never invents ok.
with tempfile.TemporaryDirectory() as H:
    hook = Path(H) / "stage_runner.py"
    hook.write_text(
        "import json, sys\n"
        "payload = json.load(sys.stdin)\n"
        "print(payload['brief']['theme'])\n", encoding="utf-8")
    runner = FakeRunner(payload={"outcome": "ok", "duration_s": 58.4,
                                 "video_path": str(Path(H) / "gone.mp4")})
    entry = fake_factory(Path(H) / "factory.py")
    res, _, _ = run(env=tmp_env(H, "active"), factory_entry=entry,
                    runner=runner, stage_hook=str(hook))
    hand = res.get("handoff") or {}
    check("stage hook runs and reports back",
          hand.get("attempted") is True and hand.get("ok") is True,
          str(hand))
    check("handoff never turns pending-production into ok",
          res["status"] == "pending-production")

# (2) anything other than ok is never reported as ok.
for bad_outcome in ("parked", "rejected", "failed", "error"):
    with tempfile.TemporaryDirectory() as H:
        runner = FakeRunner(payload={"outcome": bad_outcome,
                                     "reason_code": "x"})
        entry = fake_factory(Path(H) / "factory.py")
        res, _, _ = run(env=tmp_env(H, "active"), factory_entry=entry,
                        runner=runner)
        check("factory outcome %r is never reported as ok" % bad_outcome,
              res["status"] in ("error", "failed")
              and V.exit_code_for(res["status"]) != 0,
              str(res.get("status")))

# over-cap from the factory -> failed
with tempfile.TemporaryDirectory() as H:
    runner = FakeRunner(payload={"outcome": "ok", "duration_s": 62.6,
                                 "video_path": "v.mp4", "cost_cents": 500})
    entry = fake_factory(Path(H) / "factory.py")
    res, _, _ = run(env=tmp_env(H, "active"), factory_entry=entry, runner=runner)
    check("factory over-cap result fails the week",
          res["status"] == "failed" and "59.0" in res["reason"])
    check("failure is exit 4 (rejected), not a silent ok",
          V.exit_code_for(res["status"]) == 4)

# factory failure
with tempfile.TemporaryDirectory() as H:
    def failing(cmd):
        failing.calls.append(list(cmd))
        return 1, "", "boom"
    failing.calls = []
    entry = fake_factory(Path(H) / "factory.py")
    res, _, _ = run(env=tmp_env(H, "active"), factory_entry=entry, runner=failing)
    check("factory failure surfaces as error, exit 1",
          res["status"] == "error" and V.exit_code_for(res["status"]) == 1
          and len(failing.calls) == 1)
    check("an unreadable reply is never reported as ok",
          "no readable envelope" in res.get("error", ""))

# missing entry
with tempfile.TemporaryDirectory() as H:
    env = tmp_env(H, "active")
    env.pop("DRAMA_SONG_FACTORY_ENTRY", None)
    res, _, _ = run(env=env)
    check("missing Skill 75 entry is an error, never a private-client retry",
          res["status"] == "error" and "Skill 75" in res["error"])

# --- 8. dry run never dispatches -------------------------------------------

with tempfile.TemporaryDirectory() as H:
    runner = FakeRunner()
    entry = fake_factory(Path(H) / "factory.py")
    res, files, _ = run(env=tmp_env(H, "active"), dry_run=True,
                        factory_entry=entry, runner=runner)
    check("dry-run dispatches nothing", runner.calls == [])
    check("dry-run still writes the result and the channel plan",
          res["status"] == "dry-run" and "drama-song-result.json" in files
          and res["channels"])
    check("dry-run is exit 0", V.exit_code_for(res["status"]) == 0)

# --- 9. CLI ----------------------------------------------------------------

with tempfile.TemporaryDirectory() as H:
    out = Path(H) / "week"
    env_backup = dict(os.environ)
    os.environ["KIE_LIVE_ADAPTER_MODE"] = "active"
    try:
        rc = V.main(["--theme", "Theme A", "--out-dir", str(out),
                     "--dry-run", "--connected", "TikTok"])
    finally:
        os.environ.clear()
        os.environ.update(env_backup)
    check("CLI dry-run (active KIE) exits 0 and writes the result",
          rc == 0 and (out / "drama-song-result.json").is_file())

with tempfile.TemporaryDirectory() as H:
    out = Path(H) / "week"
    env_backup = dict(os.environ)
    os.environ["KIE_LIVE_ADAPTER_MODE"] = "shadow"
    try:
        rc = V.main(["--theme", "Theme A", "--out-dir", str(out)])
    finally:
        os.environ.clear()
        os.environ.update(env_backup)
    check("CLI skip path exits 0 and writes drama-song-skipped.json",
          rc == 0 and (out / "drama-song-skipped.json").is_file()
          and not (out / "drama-song-result.json").exists())

with tempfile.TemporaryDirectory() as H:
    env_backup = dict(os.environ)
    os.environ["KIE_LIVE_ADAPTER_MODE"] = "active"
    try:
        rc = V.main(["--theme", "T", "--out-dir", H, "--length", "45"])
    finally:
        os.environ.clear()
        os.environ.update(env_backup)
    check("CLI rejects a length outside 60/90 with exit 4", rc == 4)

# --- 10. static gates: no paid calls, no transport, no paths, no media -----

source = (HERE / "weekly_step.py").read_text() + (HERE / "__init__.py").read_text()
low = source.lower()
forbidden = {
    "operator path": "/users/",
    "KIE API host": "kie.ai",
    "KIE key": "kie_api_key",
    "network client (urllib)": "urllib",
    "network client (requests)": "requests",
    "network client (http.client)": "http.client",
    "raw socket": "socket",
    "bare http scheme": "http://",
    "media muxer": "ffmpeg",
}
for label, token in forbidden.items():
    check("static: module carries no %s" % label, token not in low, token)

check("static: only the Skill 74 mode store is read",
      "kie-live-adapter-mode.conf" in source
      and "KIE_LIVE_ADAPTER_MODE" in source)
check("static: dispatch target is Skill 75's control entrypoint only",
      '"intake"' in source and "--brief-file" in source)

media_ext = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".png", ".jpg", ".jpeg",
             ".gif", ".wav", ".mp3", ".m4a", ".srt"}
stray = [p.name for p in HERE.iterdir() if p.suffix.lower() in media_ext]
check("module ships no media files", stray == [], str(stray))

# exactly the three module files (plus caches) — nothing else staged here
shipped = sorted(p.name for p in HERE.iterdir()
                 if p.is_file() and p.suffix in (".py", ".md", ".json"))
check("module ships only the weekly_step sources",
      shipped == ["__init__.py", "test_weekly_step.py", "weekly_step.py"],
      str(shipped))

# --- result ----------------------------------------------------------------

def test_suite_checks_pass():
    assert not FAILS, FAILS


if __name__ == "__main__":
    print()
    if FAILS:
        print("FAILURES (%d): %s" % (len(FAILS), "; ".join(FAILS)))
        sys.exit(1)
    print("all checks passed")
    sys.exit(0)
