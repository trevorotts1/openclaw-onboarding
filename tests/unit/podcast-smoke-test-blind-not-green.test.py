#!/usr/bin/env python3
"""T0-23 - the daily podcast smoke test may not report success while blind.

The defect this guards, as recorded on a live client box: the daily
podcast-smoke cron ran at 06:00, its stale-job sweep printed

    smoke-test: stale-job sweep could not read .../podcast-engine.db
                (unable to open database file)

to stderr, then returned {"stale_count": 0, "stale_jobs": []} and exited 0, and
the scheduler stored the run as status ok. An episode job died the same day and
no check ever noticed. Three separate mechanisms had to line up for that:

  1. find_stale_jobs() caught sqlite3.Error and returned []. An unreadable
     database became "zero stale jobs". "Checked and found none" and "could not
     check" rendered identically.
  2. do_run() wrapped the sweep in `except Exception` and substituted
     {"stale_count": 0}, so even a raise would have become a clean zero.
  3. load_endpoints() ended in `data.get("providers", data)`. The shipped
     config/smoke-endpoints.json has no "providers" key, so the WHOLE FILE was
     used as the provider map; its only dict-valued top-level key is the config
     wrapper "podcast_engine", so every run probed one imaginary provider by that
     name, marked it UNKNOWN, and exited 0. The five real pinned providers were
     never probed on any box on any day. That is the
     `"services": {"podcast_engine": "UNKNOWN"}` in the stored diagnostic.

And the gap that made the specific failure invisible even with a working sweep:
a job that has ALREADY died carries status 'failed', which is in
_JOB_TERMINAL_STATES, so the stale sweep skips it at ANY threshold. Nothing in
the script looked at failed jobs at all.

Hermetic: temp HOME, temp databases, no network (every run is --offline), no
client data, no secret ever read or printed.

NOT asserted here, and deliberately so: nothing in this file claims anything
about any live box. It proves the shipped source behaves correctly.
"""

import datetime as _dt
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO, "58-podcast-production-engine", "scripts",
                      "podcast-smoke-test.py")

_passed = []
_failed = []


def check(name, cond):
    (_passed if cond else _failed).append(name)
    print("%s  %s" % ("PASS" if cond else "FAIL", name))


class _Missing(Exception):
    """Stand-in so a symbol the fix introduces cannot abort the whole suite when
    this file is run against pre-fix source. Every case must be able to report
    its own red; a suite that dies on the first missing name proves less."""


def load_module():
    spec = importlib.util.spec_from_file_location("podcast_smoke_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("EXIT_BLIND", "PodcastDbUnreadable", "find_failed_jobs",
                 "DEFAULT_FAILED_JOB_LOOKBACK_HOURS"):
        if not hasattr(mod, name):
            print("NOTE  source does not define %s" % name)
            setattr(mod, name, _Missing if name == "PodcastDbUnreadable" else None)
    return mod


def safe(fn, *a, **kw):
    """Call fn; an exception becomes a sentinel so the check reports red."""
    try:
        return fn(*a, **kw)
    except Exception as exc:  # noqa: BLE001 - a raise here IS the result
        return exc


def utc(hours_ago):
    return (_dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


def make_db(path, wal=True, rows=()):
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE podcast_jobs (job_id TEXT, client_id TEXT, "
                 "status TEXT, updated_at TEXT)")
    for row in rows:
        conn.execute("INSERT INTO podcast_jobs VALUES (?,?,?,?)", row)
    conn.commit()
    conn.close()
    # Drop the sidecars so the next open is a cold one, the way a daily cron
    # finds the file when no engine process is running.
    for suffix in ("-wal", "-shm"):
        side = path + suffix
        if os.path.exists(side):
            os.remove(side)


def run_cli(tmp, db_path, name):
    """Drive the REAL CLI the cron drives. Returns (exit_code, summary_dict)."""
    state = os.path.join(tmp, "state-" + name)
    os.makedirs(state, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = tmp  # never touch the invoking user's ~/.openclaw
    proc = subprocess.run(
        [sys.executable, SCRIPT, "--offline", "--state-dir", state,
         "--client", "t023", "--db-path", db_path,
         # Force every provider to a known status so provider blindness cannot
         # be confused with job-sweep blindness in these assertions.
         "--force-status", "ollama_cloud=PASS", "--force-status", "openrouter=PASS",
         "--force-status", "kie_ai=PASS", "--force-status", "fish_audio=PASS",
         "--force-status", "perplexity=PASS"],
        capture_output=True, text=True, timeout=120, env=env)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except ValueError:
        return proc.returncode, {"_stdout": proc.stdout, "_stderr": proc.stderr}


def main():
    mod = load_module()
    tmp = tempfile.mkdtemp(prefix="t023-")

    # -- 1. A healthy WAL database that EXISTS and holds rows must be READ. -----
    # Regression control: if the sweep ever silently stops reading a real
    # database, this is the case that catches it, and its non-empty result is
    # what proves the "unreadable" case below is testing a real difference.
    healthy = os.path.join(tmp, "healthy.db")
    make_db(healthy, wal=True, rows=[
        ("j-stuck", "t023", "writing", utc(30)),
        ("j-fresh", "t023", "writing", utc(0.1)),
        ("j-dead", "t023", "failed", utc(1.6)),
        ("j-done", "t023", "complete", utc(1.0)),
    ])
    check("WAL journal mode really is in effect on the fixture",
          sqlite3.connect(healthy).execute(
              "PRAGMA journal_mode").fetchone()[0].lower() == "wal")

    stale = {f["job_id"] for f in mod.find_stale_jobs(healthy, 24)}
    check("[1] existing WAL DB with rows is read, not reported as zero",
          stale == {"j-stuck"})

    rc, out = run_cli(tmp, healthy, "healthy")
    check("[1] full run over a readable DB records checked=true",
          out.get("stale_jobs", {}).get("checked") is True)
    check("[1] full run over a readable DB is not blind on the job sweep",
          not any(b["check"] == "job_sweep" for b in out.get("blind_spots", [])))

    # -- 2. A DB that EXISTS and will not open must FAIL LOUDLY, never zero. ----
    unreadable = os.path.join(tmp, "unreadable.db")
    make_db(unreadable, wal=True, rows=[("j-hidden", "t023", "writing", utc(30))])
    os.chmod(unreadable, 0o000)
    if os.access(unreadable, os.R_OK):
        # chmod does not restrain root. Skipping beats faking a pass.
        check("[2] SKIPPED, running as root (cannot make a file unreadable)", True)
    else:
        raised = False
        try:
            mod.find_stale_jobs(unreadable, 24)
        except mod.PodcastDbUnreadable:
            raised = True
        except Exception:  # noqa: BLE001 - some other raise is still not a pass
            raised = False
        check("[2] existing unreadable DB raises PodcastDbUnreadable", raised)

        rc, out = run_cli(tmp, unreadable, "unreadable")
        check("[2] the run does NOT report zero stale jobs",
              out.get("stale_jobs", {}).get("stale_count") != 0)
        check("[2] the run records checked=false",
              out.get("stale_jobs", {}).get("checked") is False)
        check("[2] overall is BLIND, never PASS", out.get("overall") == "BLIND")
        check("[2] the job sweep is named as a blind spot",
              any(b["check"] == "job_sweep" for b in out.get("blind_spots", [])))
        check("[2] exit status is non-zero so the scheduler cannot record ok",
              rc != 0)
        check("[2] exit status is specifically EXIT_BLIND", rc == mod.EXIT_BLIND)

        # KNOWN-GOOD CONTROL on the instrument, not just the target: the very
        # same file, same process, same helper, opened after the permission is
        # restored. If this came back empty too, the test would be broken rather
        # than the target.
        os.chmod(unreadable, 0o644)
        control = {f["job_id"] for f in mod.find_stale_jobs(unreadable, 24)}
        check("[2] CONTROL: the same DB, made readable, yields its row",
              control == {"j-hidden"})

    # -- 3. A job that DIED is reported. --------------------------------------
    dead = (set() if mod.find_failed_jobs is None
            else {f["job_id"] for f in mod.find_failed_jobs(healthy, 48)})
    check("[3] a failed job is reported by the failed-job sweep",
          dead == {"j-dead"})
    check("[3] a failed job is still terminal for the stale sweep",
          "j-dead" not in stale)
    rc, out = run_cli(tmp, healthy, "dead")
    check("[3] the run surfaces the failed job in its summary",
          out.get("stale_jobs", {}).get("failed_jobs") == ["j-dead"])
    old_dead = os.path.join(tmp, "old-dead.db")
    make_db(old_dead, wal=True, rows=[("j-ancient", "t023", "failed", utc(500))])
    check("[3] a long-dead job stops re-alerting after the lookback window",
          mod.find_failed_jobs is not None
          and mod.find_failed_jobs(old_dead, 48) == [])

    # -- 4. The 24h threshold could not have caught a 1.6h-old failure. --------
    # Both halves matter: the stale sweep cannot see a failed row at ANY
    # threshold, and 24h is far longer than any machine-driven step.
    check("[4] default stale threshold is no longer 24h",
          mod.DEFAULT_STALE_JOB_ALERT_HOURS < 24)
    recent_stuck = os.path.join(tmp, "recent.db")
    make_db(recent_stuck, wal=True,
            rows=[("j-hung", "t023", "producing_audio", utc(5))])
    check("[4] a 5h-hung machine-driven step is now caught",
          {f["job_id"] for f in mod.find_stale_jobs(
              recent_stuck, mod.DEFAULT_STALE_JOB_ALERT_HOURS)} == {"j-hung"})
    check("[4] it was NOT caught at the old 24h threshold",
          mod.find_stale_jobs(recent_stuck, 24) == [])

    # -- 5. The shipped endpoint file parses into real providers. --------------
    shipped = os.path.join(REPO, "58-podcast-production-engine", "config",
                           "smoke-endpoints.json")
    pinned, _path = mod.load_endpoints(shipped)
    pinned = pinned or {}
    names = set(pinned)
    check("[5] the config wrapper key is not treated as a provider",
          "podcast_engine" not in names)
    check("[5] the five pinned providers are all loaded",
          {"ollama_cloud", "openrouter", "kie_ai", "fish_audio",
           "perplexity"}.issubset(names))
    check("[5] openrouter resolves to its free balance GET",
          pinned.get("openrouter", {}).get("url")
          == "https://openrouter.ai/api/v1/key"
          and pinned.get("openrouter", {}).get("method") == "GET")
    # The run must never be able to spend. ollama_cloud's only method 2 is a
    # BILLED POST; it must not become a probe.
    check("[5] ollama_cloud maps to no free probe rather than a billed turn",
          pinned.get("ollama_cloud", {}).get("no_free_probe") is True)
    for name in sorted(pinned):
        spec = pinned[name]
        # Pre-fix, `pinned` is the raw JSON file and its values include strings.
        # A non-dict here is itself the bug, so report it rather than crash.
        if not isinstance(spec, dict):
            check("[5] %s is a provider spec, not a raw config value" % name, False)
            continue
        if spec.get("no_free_probe"):
            continue
        check("[5] %s probes with a free GET or HEAD only" % name,
              spec.get("method") in ("GET", "HEAD"))

    # -- 6. UNKNOWN does not coexist with a pass. ------------------------------
    # But an UNKNOWN the config itself declares unprobe-able is not blindness.
    check("[6] a provider with no free endpoint is UNKNOWN and NOT blind",
          mod.probe_provider("ollama_cloud", pinned.get("ollama_cloud", {}),
                             offline=True).get("blind") is False)
    kie = dict(pinned.get("kie_ai", {"auth": "bearer", "url": "https://x"}),
               key_env=["T023_DEFINITELY_UNSET"])
    required_unset = mod.probe_provider("kie_ai", kie, offline=True)
    check("[6] a required provider with no key is UNKNOWN and IS blind",
          required_unset["status"] == "UNKNOWN"
          and required_unset.get("blind") is True)
    optional_unset = mod.probe_provider("opt", dict(kie, optional=True),
                                        offline=True)
    check("[6] an optional provider the client never wired is NOT blind",
          optional_unset.get("blind") is False)

    # -- 8. Same pattern, two more places the audit turned up. ----------------
    # 8a. self_meter() returned 0.0 on EVERY failure path, and the caller computes
    #     overspend = run_cost > max_cost -- so a broken or absent cost ledger
    #     silently disarmed the one guard that catches a paid call wired into the
    #     free health check. An unmeasurable cost is not a zero cost.
    import shutil as _shutil
    scripts_dir = os.path.join(REPO, "58-podcast-production-engine", "scripts")
    fake_scripts = os.path.join(tmp, "scripts")
    _shutil.copytree(scripts_dir, fake_scripts)
    os.remove(os.path.join(fake_scripts, "podcast-cost-ledger.py"))
    state_nm = os.path.join(tmp, "state-nometer")
    os.makedirs(state_nm, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = tmp
    proc = subprocess.run(
        [sys.executable, os.path.join(fake_scripts, "podcast-smoke-test.py"),
         "--offline", "--state-dir", state_nm, "--client", "t023",
         "--db-path", os.path.join(tmp, "absent.db")],
        capture_output=True, text=True, timeout=120, env=env)
    try:
        nm = json.loads(proc.stdout)
    except ValueError:
        nm = {}
    check("[8a] an unmeasurable run cost is not reported as a measured zero",
          nm.get("run_cost_measured") is False
          and nm.get("run_cost_usd_estimate") is None)
    check("[8a] an unmeasurable run cost is named as a blind spot",
          any(b["check"] == "run_cost" for b in nm.get("blind_spots", [])))
    check("[8a] the run does not pass while its own cost is unknown",
          nm.get("overall") == "BLIND" and proc.returncode != 0)

    # 8b. A config file that EXISTS and will not parse silently fell back to the
    #     embedded defaults, so the run used thresholds nobody chose while looking
    #     exactly like a healthy one.
    bad_cfg = os.path.join(tmp, "broken-config.json")
    with open(bad_cfg, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json")
    cfg = mod.load_run_config(bad_cfg)
    check("[8b] an unparseable config file is reported, not silently defaulted",
          cfg.get("config_unreadable") == bad_cfg)
    check("[8b] an ABSENT config file is still a clean default, not a blind spot",
          mod.load_run_config(os.path.join(tmp, "no-such-config.json"))
          .get("config_unreadable") is None)

    # -- 7. The source may not regrow the swallow. -----------------------------
    src = open(SCRIPT, encoding="utf-8").read()
    check("[7] no handler turns a sqlite error into an empty job list",
          "except sqlite3.Error as exc:\n        _eprint" not in src)
    check("[7] the sweep failure path no longer substitutes stale_count 0",
          '{"stale_count": 0, "stale_jobs": [], "error": str(exc)}' not in src)
    check("[7] self_meter no longer reports 0.0 for an unmeasurable cost",
          'could not self-meter (%s)" % exc)\n        return 0.0' not in src)
    # Behavioural, not textual: the old fallback is quoted in this file's own
    # docstring, so a grep would match the explanation as well as the bug.
    weird = os.path.join(tmp, "weird-endpoints.json")
    with open(weird, "w", encoding="utf-8") as fh:
        json.dump({"some_wrapper": {"nested": {"url": "https://x"}},
                   "note": "a shape the loader does not know"}, fh)
    loaded, _ = mod.load_endpoints(weird)
    check("[7] an unrecognised endpoint shape yields None, not fake providers",
          loaded is None)

    print("\n%d/%d checks passed" % (len(_passed), len(_passed) + len(_failed)))
    if _failed:
        print("FAILED:")
        for name in _failed:
            print("  - " + name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
