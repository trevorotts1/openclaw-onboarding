#!/usr/bin/env python3
"""fake-openclaw-cron.py — a fake `openclaw` CLI for the cron-gating/idempotency
acceptance tests (fix/industry-gate-and-idempotent-crons).

Reproduces the ONE behavior these tests care about proving/disproving: `cron
list` (no --json) renders a TEXT TABLE that TRUNCATES names longer than 22
characters (appending "..."), exactly like the real `openclaw` CLI does. This
is the reproduction harness for the confirmed root cause of the Skill 39 / 38
6x-duplicate-cron bug: a positive-presence check via a text-table grep against
a name > 22 chars ALWAYS misses (false "absent"), so a text-grep-based
registrar re-adds a duplicate on every run. `cron list --json` returns the
FULL untruncated names, so a script using the JSON path detects presence
correctly. This lets tests be genuinely mutation-proof: reintroducing a
text-table grep against this fixture WILL exhibit the duplicate-add bug;
reading `--json` will not.

State: a JSON array of job objects, persisted at $FAKE_OC_JOBS_FILE.
Call log: one line per invocation (raw argv), appended to $FAKE_OC_CALLS_FILE.

Supported surface (only what the registrars under test actually call):
  cron add --name N --cron E [--agent A] [--message M] [--command C]
           [--no-deliver] [--light-context] [--best-effort-deliver]
           [--session <main|isolated>] [--system-event M] [--tz TZ] [--json]
  cron add --help          -> advertises every flag above (feature-detect)
  cron list                -> TRUNCATING text table (name col only)
  cron list --json         -> {"jobs": [...]}  (full names, never truncated)
  message send --channel telegram -t ID -m MSG
      -> succeeds unless $FAKE_OC_MESSAGE_FAIL is set, in which case it prints
         that string to stderr and exits 1 (used by the rate-limit-backoff test).
  doctor / config get ...  -> no-ops so callers that probe these don't abort.
"""
import json
import os
import sys


def jobs_file():
    return os.environ.get("FAKE_OC_JOBS_FILE")


def calls_file():
    return os.environ.get("FAKE_OC_CALLS_FILE")


def load_jobs():
    p = jobs_file()
    if p and os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_jobs(jobs):
    p = jobs_file()
    if p:
        with open(p, "w") as f:
            json.dump(jobs, f)


def log_call(argv):
    p = calls_file()
    if p:
        with open(p, "a") as f:
            f.write(" ".join(argv) + "\n")


def truncate(name, n=22):
    return name if len(name) <= n else name[:n] + "..."


HELP_TEXT = (
    "--name <name>  --cron <expr>  --agent <agent>  --message <msg>\n"
    "--command <cmd>  --no-deliver  --best-effort-deliver  --light-context\n"
    "--session <mode>  --session-target <mode>  --system-event <text>\n"
    "--tz <tz>  --json\n"
)


def cmd_cron_add(rest):
    if "--help" in rest:
        sys.stdout.write(HELP_TEXT)
        return 0
    job = {
        "name": "", "cron": "", "agent": "", "message": "", "command": "",
        "kind": "agentTurn", "id": "",
    }
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--name":
            job["name"] = rest[i + 1]; i += 2
        elif a in ("--cron",):
            job["cron"] = rest[i + 1]; i += 2
        elif a == "--agent":
            job["agent"] = rest[i + 1]; i += 2
        elif a == "--message":
            job["message"] = rest[i + 1]; job["kind"] = "agentTurn"; i += 2
        elif a == "--system-event":
            job["message"] = rest[i + 1]; job["kind"] = "agentTurn"; i += 2
        elif a == "--command":
            job["command"] = rest[i + 1]; job["kind"] = "command"; i += 2
        elif a in ("--tz", "--session", "--session-target"):
            i += 2
        elif a in ("--no-deliver", "--light-context", "--best-effort-deliver", "--json"):
            i += 1
        else:
            i += 1
    if not job["name"]:
        return 1
    jobs = load_jobs()
    job["id"] = "fake-%03d" % (len(jobs) + 1)
    jobs.append(job)
    save_jobs(jobs)
    if "--json" in rest:
        sys.stdout.write(json.dumps({"uuid": job["id"], "id": job["id"]}) + "\n")
    return 0


def cmd_cron_list(rest):
    jobs = load_jobs()
    if "--json" in rest:
        sys.stdout.write(json.dumps({"jobs": jobs}) + "\n")
    else:
        for j in jobs:
            # Mirrors the real CLI's truncating text table: name col first,
            # then id, then kind — a grep for the FULL (untruncated) name of
            # anything > 22 chars can never match this row.
            sys.stdout.write("%-25s %s %s\n" % (truncate(j["name"]), j["id"], j["kind"]))
    return 0


def cmd_cron_rm_or_delete():
    # Best-effort: not exercised by presence/idempotency assertions here.
    return 0


def main():
    argv = sys.argv[1:]
    log_call(argv)
    if not argv:
        return 0
    if argv[0] == "cron":
        sub = argv[1] if len(argv) > 1 else ""
        rest = argv[2:]
        if sub in ("add", "create"):
            return cmd_cron_add(rest)
        if sub == "list":
            return cmd_cron_list(rest)
        if sub in ("rm", "delete", "edit"):
            return cmd_cron_rm_or_delete()
        return 0
    if argv[0] == "message" and len(argv) > 1 and argv[1] == "send":
        fail_mode = os.environ.get("FAKE_OC_MESSAGE_FAIL", "")
        if fail_mode:
            sys.stderr.write(fail_mode + "\n")
            return 1
        return 0
    if argv[0] == "doctor":
        return 0
    if argv[0] == "config":
        sys.stdout.write("\n")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
