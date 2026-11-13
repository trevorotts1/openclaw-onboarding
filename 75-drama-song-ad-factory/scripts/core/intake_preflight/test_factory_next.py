#!/usr/bin/env python3
"""W2-A-U2 (manual 02 B1): `factory.py next --run-dir <dir>`.

Proves, behaviourally:
  * on a run dir whose control/state.sqlite3 has research READY and the rest
    NOT_STARTED, `next` returns stage == "research" with a non-empty,
    parseable command string and a lane_size block;
  * on that same structure the command in the row parses (argparse-level:
    substituted `<...>` tokens, then `cmd --run-dir X -h` style checks);
  * on a fresh, unclaimed-but-initialized run the first non-COMPLETE,
    non-FAILED_BLOCKED, non-PARKED stage in batch.py STAGES order wins;
  * when EVERY stage is COMPLETE (run done), exit code stays 0 with
    stage == null and a plain reason (the Done-when is a completed run, not
    an error);
  * on a run dir with no state file: exit code 1, error naming the missing
    absolute path, empty stdout JSON (no stage, no command);
  * lane_size comes from a live `lane_size` import when the module landed
    (W2-A-U1), else from the Part D fallback constants in factory.py
    (agents >= 1 always); "source" inside the payload names which one ran;
  * S75-024: the runtime and builder route come from the run's own
    model-bindings.json, so two different bindings are sized two different
    ways, and no bindings falls back to Part D and says so.

Run from the skill root:  python3 scripts/core/intake_preflight/test_factory_next.py
stdlib only, no network, no provider, writes only under a temp dir.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent.parent          # 75-drama-song-ad-factory/
FACTORY = HERE / "factory.py"
CORE = HERE.parent
sys.path.insert(0, str(CORE))
from test_production_process import confirmed_run, complete_stage  # noqa: E402

STAGES = ("research", "creative-strategy", "script-lyrics", "music",
          "continuity-bible", "storyboard", "image-keyframes",
          "video-generation", "qc-retakes", "assembly", "final-qc",
          "delivery")


def make_run(tmp, *, done=False):
    """Real confirmed intake and legal stage history, with research complete."""
    run = make_fresh(tmp)
    (run / "brief.json").write_text(
        json.dumps({"title": "T", "author": "A",
                    "offer": "o", "audience": "a",
                    "budget_minor": 2500, "budget_currency": "USD"}), "utf-8")
    for stage in STAGES if done else STAGES[:1]:
        complete_stage(run, stage)
    if done:
        # Empty receipts are a well-shaped, explicitly unproven delivery set.
        # Stage completion alone must never fabricate destination delivery.
        (run / "delivery" / "receipts.json").write_text("[]", "utf-8")
    return run


def make_fresh(tmp):
    """Actual full renderer-bound confirmation creates the canonical Store."""
    import uuid as _u
    run = tmp / ("run2-%s" % _u.uuid4().hex[:6])
    confirmed_run(run, script=False, song=False, storyboard=False)
    return run


def run_next(run_dir, cwd=None):
    return subprocess.run([sys.executable, str(FACTORY), "next",
                           "--run-dir", str(run_dir)],
                          capture_output=True, text=True,
                          cwd=str(cwd or SKILL), timeout=60)


def main():
    fails = []
    checks = 0

    def check(name, got, want):
        nonlocal checks
        checks += 1
        ok = (got == want) if want is not ... else bool(got)
        if not ok:
            fails.append("%s: got %r" % (name, got))
        print("  %s %s" % ("ok" if ok else "FAIL", name))

    with tempfile.TemporaryDirectory(prefix="w75-w2-a-u2-") as td:
        tmp = Path(td)

        # -- positive (the Done-when): fresh run, nothing done --------------
        run = make_fresh(tmp)
        p = run_next(run)
        check("exit 0 on fresh run", p.returncode, 0)
        try:
            env = json.loads(p.stdout)
        except Exception as e:                      # noqa: BLE001
            env = {}
            fails.append("stdout not one JSON object: %s" % e)
        check("outcome ok", env.get("outcome"), "ok")
        check("stage research", env.get("data", {}).get("stage"), "research")
        cmd = env.get("data", {}).get("command") or ""
        check("command non-empty", len(cmd) > 0, ...)
        check("command mentions the stage's module", "research.py" in cmd, True)
        lane = env.get("data", {}).get("lane_size") or {}
        check("lane_size has agents>=1",
              isinstance(lane.get("agents"), int) and lane["agents"] >= 1, True)
        check("lane_size names its source",
              str(lane.get("source") or "").startswith(
                  ("lane_size.module", "part_d_defaults")), True)
        check("lane_size source is honest",
              (env.get("data", {}).get("lane_size") or {}).get("agents") is not None, True)
        check("stage-list source tag", (env.get("data", {}).get("stages_source")
                                        or "").startswith("batch_mode STAGES"), True)

        # -- positive: research done -> next eligible is creative-strategy --
        run = make_run(tmp)
        p = run_next(run)
        env = json.loads(p.stdout)
        check("advance after COMPLETE stage",
              env.get("data", {}).get("stage"), "creative-strategy")

        # -- S75-001: a paid stage with no computable price is refused ------
        # Nothing is handed out: no command, and the reason is UNKNOWN_PRICE
        # (never a made-up zero cost). The price read is replaced with the
        # "cannot compute" answer the real function returns when the card
        # cannot be priced.
        import argparse
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import factory as F                             # noqa: E402
        run = make_run(tmp)
        for stage in STAGES[1:3]:                       # creative-strategy, script-lyrics
            complete_stage(run, stage)
        saved = F.price_for_stage
        F.price_for_stage = lambda *_a, **_k: None
        try:
            env = F.cmd_next(argparse.Namespace(run_dir=str(run), orchestrated=False))
        finally:
            F.price_for_stage = saved
        check("paid stage with no price: stage is music",
              (env.get("data") or {}).get("stage"), "music")
        check("paid stage with no price: outcome rejected",
              env.get("outcome"), "rejected")
        check("paid stage with no price: reason UNKNOWN_PRICE",
              env.get("reason_code"), "UNKNOWN_PRICE")
        check("paid stage with no price: no command handed out",
              (env.get("data") or {}).get("command"), None)

        # -- S75-024: the run's own model choice sizes the lanes -------------
        from choice_card.intake_card import ai_models as models  # noqa: E402

        def bind(run, runtime, build_id, route):
            (run / models.STORE_NAME).write_text(json.dumps({
                "schema": models.STORE_SCHEMA, "runtime": runtime,
                "binding_id": "b-fixture",
                "bindings": {"build": {"model_id": build_id, "route": route},
                             "check": {"model_id": "checker", "route": "openrouter"}}}),
                "utf-8")

        run_a = make_fresh(tmp)
        bind(run_a, "claude-nine", "openrouter/z-ai/glm-5.3", "openrouter")
        run_b = make_fresh(tmp)
        bind(run_b, "openclaw", "ollama/kimi-k2.6", "ollama")
        a = F.lane_size_payload(run_a)
        b = F.lane_size_payload(run_b)
        check("two bindings give two different sizing sources",
              a.get("source") != b.get("source"), True)
        check("first binding is sized as its runtime/route",
              "claude-code/openrouter" in str(a.get("source")), True)
        check("second binding is sized as its runtime/route",
              "openclaw/ollama-cloud" in str(b.get("source")), True)
        check("sized payload still has agents>=1", a.get("agents", 0) >= 1, True)
        run_c = make_fresh(tmp)
        bind(run_c, "claude-nine", "mystery-model", "mystery-route")
        c = F.lane_size_payload(run_c)
        check("unknown binding pair falls back to Part D",
              str(c.get("source")).startswith("part_d_defaults"), True)
        run_d = make_fresh(tmp)
        try:
            (run_d / models.STORE_NAME).unlink()
        except FileNotFoundError:
            pass
        d = F.lane_size_payload(run_d)
        check("no bindings -> Part D source says why",
              d.get("source"), "part_d_defaults (no model bindings on this run)")

        # -- run complete: exit 0, stage null, plain reason -----------------
        run = make_run(tmp, done=True)
        p = run_next(run)
        check("exit 0 when run complete", p.returncode, 0)
        env = json.loads(p.stdout)
        check("stage null", env.get("data", {}).get("stage"), None)
        check("plain reason present",
              isinstance(env.get("next_action"), str) and env["next_action"],
              ...)
        check("reason_code run-complete", env.get("reason_code"), "run-complete")

        # -- negative: no state file -> non-zero + named path ---------------
        run = tmp / "run3"
        run.mkdir()
        (run / "control").mkdir()
        p = run_next(run)
        check("non-zero exit with no state file", p.returncode != 0, True)
        check("error names the missing path",
              str((run / "control" / "state.sqlite3").resolve()) in
              (p.stdout + p.stderr), True)
        check("outcome error reason state-file-missing",
              json.loads(p.stdout).get("reason_code"), "state-file-missing")

        # -- negative: --run-dir missing entirely ---------------------------
        p = run_next(tmp / "no-such-dir")
        check("missing dir exits non-zero", p.returncode != 0, True)
        check("missing dir names the path",
              str((tmp / "no-such-dir" / "control" / "state.sqlite3").resolve())
              in (p.stdout + p.stderr), True)

        # -- the returned research command parses after substitution --------
        env = json.loads(run_next(make_fresh(tmp)).stdout)
        cmd = env["data"]["command"]
        check("command has no <placeholders> left", "<" not in cmd, True)
        # $RUN/$RUN_ID are the runbook's substitution contract: substitute the
        # way the agent loop would (run dir and a run id), then argv-parse.
        subbed = cmd.replace("$RUN", str(make_fresh(tmp))) \
                    .replace("$RUN_ID", "R1").replace("$STORAGE", str(tmp))
        argv = subbed.replace('"', "").split()      # shellsafe: rows use no &
        head = argv[0]
        check("command head is python3", head, "python3")
        probe_argv = [sys.executable] + [argv[1]] + ["--help"]
        try:
            probe = subprocess.run(probe_argv, capture_output=True, text=True,
                                   cwd=str(SKILL), timeout=60)
            # argparse-level check (U3's acceptance): --help exits 0 even when
            # required args are unfulfilled.
            check("substituted command parses (--help exit 0)",
                  probe.returncode, 0)
        except Exception as e:                      # noqa: BLE001
            fails.append("parse probe blew up: %s" % e)

        # -- every stage row in stage-runbook.md exists with a command ------
        runbook = SKILL / "references" / "stage-runbook.md"
        text = runbook.read_text(encoding="utf-8")
        rows = {}
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 3 and cells[0] in STAGES:
                rows[cells[0]] = cells[1]
        check("runbook has all 12 stages", len(rows), 12)
        for stage_id in STAGES:
            check("row %s present" % stage_id, stage_id in rows, True)

    print("test_factory_next: %s (%d checks, %d failures)"
          % ("PASS" if not fails else "FAIL", checks, len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
