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
  cron list --help         -> advertises `--agent`/`--json` only by default —
      matching docs.openclaw.ai/cli/cron, which documents NO disabled-job
      visibility flag. Set $FAKE_OC_ADVERTISE_STATUS_FLAG=1 to ALSO advertise
      `--status <mode>`, simulating a hypothetical future CLI that supports
      one (used to test the best-effort feature-detection layer works WHEN a
      flag exists, without this fixture ever claiming one exists by default).
  A job may carry "hidden": true (simulating the live-VPS finding that
      `cron list --json` returned only ENABLED jobs — 16 of 31 rows on one
      box). By default, `cron list --json` (and the text table) EXCLUDE
      hidden jobs entirely. They are INCLUDED only if the request passes
      `--status <anything>` / `--all` / `--include-disabled` /
      `--show-disabled` (mirrors oc_cron_list_json_flags' candidate list) —
      and even then ONLY if $FAKE_OC_ADVERTISE_STATUS_FLAG=1 (a flag the CLI
      never advertised cannot be feature-detected, by design).
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
    # DELIVERY DEFAULT — mirrors the real CLI (verified against OpenClaw
    # 2026.9.4, `openclaw cron add --help`): a new job is born with fallback
    # delivery ENABLED (mode "announce", channel "last"). Omitting the delivery
    # flags does NOT create a silent cron. --no-deliver is what silences it.
    # Modelling this is the whole point: a registrar that forgets the flag ships
    # a cron that fail-closes on 2026.9.x and cannot report its own failure.
    delivery = {"mode": "announce", "channel": "last", "to": None}
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
        elif a == "--no-deliver":
            delivery = {"mode": "none", "channel": "last", "to": None}
            i += 1
        elif a == "--announce":
            delivery["mode"] = "announce"; i += 1
        elif a == "--channel":
            delivery["channel"] = rest[i + 1]; i += 2
        elif a in ("--to", "--target"):
            delivery["to"] = rest[i + 1]; i += 2
        elif a in ("--light-context", "--best-effort-deliver", "--json"):
            i += 1
        else:
            i += 1
    if not job["name"]:
        return 1
    jobs = load_jobs()
    job["id"] = "fake-%03d" % (len(jobs) + 1)
    job["delivery"] = delivery
    # Nested shapes the real `cron list --json` emits and that the reconcile
    # pass reads (payload.kind / schedule.expr). The flat "kind"/"cron" keys
    # above are kept verbatim so existing consumers of this fixture are
    # unaffected.
    job["payload"] = {"kind": job["kind"]}
    job["schedule"] = {"expr": job["cron"]}
    jobs.append(job)
    save_jobs(jobs)
    if "--json" in rest:
        sys.stdout.write(json.dumps({"uuid": job["id"], "id": job["id"]}) + "\n")
    return 0


LIST_HELP_BASE = "--agent <id>  --json\n"
LIST_HELP_WITH_STATUS = "--agent <id>  --json  --status <mode>\n"

STATUS_FLAG_CANDIDATES = ("--all", "--include-disabled", "--show-disabled", "--status")


def _wants_full_visibility(rest):
    return any(c in rest for c in STATUS_FLAG_CANDIDATES)


def cmd_cron_list(rest):
    if "--help" in rest:
        advertise_status = os.environ.get("FAKE_OC_ADVERTISE_STATUS_FLAG", "") == "1"
        sys.stdout.write(LIST_HELP_WITH_STATUS if advertise_status else LIST_HELP_BASE)
        return 0

    jobs = load_jobs()
    # Simulate the live-VPS finding: a "hidden" (disabled) job is excluded
    # from the default listing. It is included ONLY when the caller passed a
    # full-visibility flag AND the CLI was configured (env) to actually honor
    # one — a flag never advertised in --help cannot be feature-detected, so
    # passing it here with FAKE_OC_ADVERTISE_STATUS_FLAG unset still hides it
    # (a real CLI wouldn't magically start honoring an unadvertised flag either).
    advertise_status = os.environ.get("FAKE_OC_ADVERTISE_STATUS_FLAG", "") == "1"
    reveal_hidden = advertise_status and _wants_full_visibility(rest)
    visible_jobs = [j for j in jobs if reveal_hidden or not j.get("hidden")]

    if "--json" in rest:
        sys.stdout.write(json.dumps({"jobs": visible_jobs}) + "\n")
    else:
        for j in visible_jobs:
            # Mirrors the real CLI's truncating text table: name col first,
            # then id, then kind — a grep for the FULL (untruncated) name of
            # anything > 22 chars can never match this row.
            sys.stdout.write("%-25s %s %s\n" % (truncate(j["name"]), j["id"], j["kind"]))
    return 0


def cmd_cron_edit(rest):
    """`cron edit <id> [--no-deliver] [--command <c>] [--cron <expr>]`.

    Only the dimensions the reconcile pass actually edits are applied. An id
    that matches nothing is an error (rc 1) — the real CLI fails too, and a
    silent success here would let a broken reconcile look green.
    """
    if not rest:
        return 1
    job_id, flags = rest[0], rest[1:]
    jobs = load_jobs()
    target = next((j for j in jobs if j.get("id") == job_id), None)
    if target is None:
        return 1
    i = 0
    while i < len(flags):
        a = flags[i]
        if a == "--no-deliver":
            d = target.setdefault("delivery", {})
            # Mirrors the real CLI: mode goes to none, the vestigial channel
            # string is LEFT BEHIND. Harmless (nothing is delivered at mode
            # none) but reconcile must stay convergent in its presence.
            d["mode"] = "none"
            d["to"] = None
            i += 1
        elif a == "--command":
            target["command"] = flags[i + 1]
            target["kind"] = "command"
            target["payload"] = {"kind": "command"}
            i += 2
        elif a == "--cron":
            target["cron"] = flags[i + 1]
            target["schedule"] = {"expr": flags[i + 1]}
            i += 2
        else:
            i += 1
    save_jobs(jobs)
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
        if sub == "edit":
            return cmd_cron_edit(rest)
        if sub in ("rm", "delete"):
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
