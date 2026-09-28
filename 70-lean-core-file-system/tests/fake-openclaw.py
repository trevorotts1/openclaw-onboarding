#!/usr/bin/env python3
"""fake-openclaw.py - a minimal stand-in for the `openclaw` command line, used
only by tests/test-install-weekly-cron.sh. It never talks to a gateway.

Surface (only what install-weekly-cron.sh calls):
  cron add --help | cron list --help | cron edit --help   (flag lists copied
      from OpenClaw 2026.9.4 help text, trimmed to the flags that matter)
  models list --json      -> $FAKE_MODELS_FILE contents (exit 1 if $FAKE_MODELS_FAIL)
  cron list --json [--all]-> {"jobs": [...]} from $FAKE_JOBS_FILE
  cron add ... / cron edit <id> ...  -> mutate $FAKE_JOBS_FILE
Knobs: $FAKE_DROP_FLAG removes one flag from `cron add --help` (feature-
detection test). Every call is appended to $FAKE_CALLS_FILE.
"""
import json
import os
import sys

ADD_FLAGS = ["--agent <id>", "--announce", "--cron <expr>", "--description <text>",
             "--fallbacks <list>", "--message <text>", "--model <model>", "--name <name>",
             "--no-deliver", "--session <target>", "--thinking <level>",
             "--timeout-seconds <n>", "--tz <iana>"]
EDIT_FLAGS = ADD_FLAGS + ["--enable", "--disable", "--clear-fallbacks"]
LIST_FLAGS = ["--agent <id>", "--all", "--json"]


def jobs_path():
    return os.environ["FAKE_JOBS_FILE"]


def load():
    try:
        with open(jobs_path()) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def save(jobs):
    with open(jobs_path(), "w") as fh:
        json.dump(jobs, fh)


def opts(argv):
    out, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a in ("--no-deliver", "--enable", "--disable", "--json", "--all", "--announce"):
            out[a] = True
            i += 1
        else:
            out[a] = argv[i + 1]
            i += 2
    return out


def apply(job, o):
    p = job.setdefault("payload", {"kind": "agentTurn"})
    if "--name" in o: job["name"] = o["--name"]
    if "--description" in o: job["description"] = o["--description"]
    if "--agent" in o: job["agentId"] = o["--agent"]
    if "--cron" in o: job["schedule"] = {"kind": "cron", "expr": o["--cron"]}
    if "--session" in o: job["sessionTarget"] = o["--session"]
    if "--message" in o: p["message"] = o["--message"]
    if "--model" in o: p["model"] = o["--model"]
    if "--fallbacks" in o: p["fallbacks"] = [x for x in o["--fallbacks"].split(",") if x]
    if "--thinking" in o: p["thinking"] = o["--thinking"]
    if "--timeout-seconds" in o: p["timeoutSeconds"] = int(o["--timeout-seconds"])
    if o.get("--no-deliver"): job["delivery"] = {"mode": "none"}
    if o.get("--enable"): job["enabled"] = True


def main(argv):
    calls = os.environ.get("FAKE_CALLS_FILE")
    if calls:
        with open(calls, "a") as fh:
            fh.write(json.dumps(argv) + "\n")
    if argv[:2] == ["models", "list"]:
        if os.environ.get("FAKE_MODELS_FAIL"):
            print("Gateway not reachable", file=sys.stderr)
            return 1
        with open(os.environ["FAKE_MODELS_FILE"]) as fh:
            sys.stdout.write(fh.read())
        return 0
    if len(argv) >= 3 and argv[0] == "cron" and argv[2] == "--help":
        flags = {"add": ADD_FLAGS, "edit": EDIT_FLAGS, "list": LIST_FLAGS}[argv[1]]
        drop = os.environ.get("FAKE_DROP_FLAG", "")
        print("Usage: openclaw cron %s [options]\n\nOptions:" % argv[1])
        for f in flags:
            if argv[1] == "add" and drop and f.split()[0] == drop:
                continue
            print("  %s" % f)
        return 0
    if argv[:2] == ["cron", "list"]:
        print(json.dumps({"jobs": load()}))
        return 0
    if argv[:2] == ["cron", "add"]:
        jobs = load()
        job = {"id": "job-%d" % (len(jobs) + 1), "enabled": True, "delivery": {"mode": "announce"}}
        apply(job, opts(argv[2:]))
        jobs.append(job)
        save(jobs)
        print(json.dumps({"id": job["id"]}))
        return 0
    if argv[:2] == ["cron", "edit"]:
        jobs = load()
        for j in jobs:
            if j.get("id") == argv[2]:
                apply(j, opts(argv[3:]))
                save(jobs)
                return 0
        print("no such job", file=sys.stderr)
        return 1
    print("fake-openclaw: unsupported call %s" % argv, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
