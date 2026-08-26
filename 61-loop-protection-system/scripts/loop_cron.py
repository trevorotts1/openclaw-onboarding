#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_cron.py
# THE ONE WRITER OF THIS SKILL'S WATCHDOG CRON JOB (v0.6.5).
# -----------------------------------------------------------------------------
# THE BUG THIS EXISTS TO KILL. install.sh called `openclaw cron add` with NO
# prior listing, so EVERY re-run added ANOTHER job. Measured 2026-08-26 across
# 34 running boxes: 25 carried 2-12 duplicate loop-tick jobs, every one enabled,
# every one on */15. The operator box itself held THREE identical
# `loop-tick-<host>` jobs (createdAtMs from three separate install runs) whose
# lastRunAtMs values were 4 seconds apart - the watchdog was firing 3x per
# window, and the same finding was processed three times over.
#
# `openclaw cron add` has no upsert. Idempotency has to be built here:
#   LIST (--all) -> DECIDE -> ACT -> LIST AGAIN AND PROVE IT.
#
# --all IS MANDATORY, NOT DEFENSIVE. `openclaw cron list` hides DISABLED jobs
# (2026.7.1-2: "--all  Include disabled jobs (default: false)"). Without it a
# disabled loop-tick job is invisible, the reconciler concludes "none exist",
# and adds a duplicate of a job that is already there. The self-test asserts the
# instrument itself: it proves the non---all listing HIDES the seeded disabled
# job, so dropping --all makes that case FAIL rather than silently pass.
#
# NEGATIVE-RESULT CONTRACT. A failed listing is NEVER "no jobs". Every path that
# cannot SEE the truth returns UNDETERMINED (exit 3) and names what it probed -
# a non-zero CLI exit, unparsable output, a `hasMore` page this CLI has no flag
# to fetch (`cron list` offers no --limit/--offset), or an openclaw binary we
# could not find. Nothing is ever added on an UNDETERMINED listing, because
# "I could not look" plus "add one" is exactly how 12 duplicates accumulate.
#
# BLAST RADIUS. Only a job that is BOTH named loop-tick-* AND recognisable as
# OURS (a command payload invoking loop-companion.sh tick) is ever removed. A
# loop-tick-* job we do not recognise is left untouched and reported as
# NEEDS-OPERATOR (exit 4). We never touch a job with any other name.
#
# PATH. openclaw is NOT on a bare-ssh Mac PATH (/usr/bin:/bin:/usr/sbin:/sbin).
# Measured install locations: /opt/homebrew/bin (Apple Silicon),
# /usr/local/bin (Intel), ~/.local/bin (measured on the operator box), plus the
# usual npm global prefixes. $LOOP_OPENCLAW_BIN overrides everything and is what
# makes the self-test hermetic (it points at a stub, never a real gateway).
#
# EXIT: 0 exactly-one PROVEN | 1 error | 2 usage | 3 UNDETERMINED | 4 needs operator
# =============================================================================
"""loop_cron.py - idempotent reconciliation of the watchdog's cron job."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

EX_OK = 0
EX_ERR = 1
EX_USAGE = 2
EX_UNDETERMINED = 3
EX_NEEDS_OPERATOR = 4

JOB_NAME_PREFIX = "loop-tick-"
DEFAULT_CRON_EXPR = "*/15 * * * *"

# A job is OURS when its command payload invokes this skill's entry point. The
# pattern is deliberately loose about the leading path so a job registered by an
# OLDER version (different install root, no --command-cwd) is still recognised
# and REPAIRED rather than duplicated.
_OURS_RE = re.compile(r"loop-companion\.sh['\"]?\s+tick\b")

# Probed in order. The first entry that exists AND is executable wins; the whole
# list is reported verbatim when none of them do, so "not found" always names
# its sources.
_CANDIDATE_DIRS = (
    "/opt/homebrew/bin",          # Mac, Apple Silicon
    "/usr/local/bin",             # Mac, Intel
    "~/.local/bin",               # measured on the operator box
    "~/.npm-global/bin",
    "~/node_modules/.bin",
    "/usr/bin",
    "/usr/local/lib/node_modules/.bin",
)

# The gateway call is a WebSocket round trip. Both budgets are generous and
# BOUNDED: a hung gateway must surface as UNDETERMINED, never as a wedged
# installer (this skill exists because things hang).
_CLI_TIMEOUT_MS = "30000"
_PROC_TIMEOUT_S = 60


class Undetermined(Exception):
    """We could not SEE the truth. Never downgraded to 'nothing is there'."""


def _expand(p: str) -> str:
    return os.path.expanduser(p)


def find_openclaw():
    """(path, probed) - path is None when nothing resolved. `probed` always
    lists every source consulted, so the caller can print a NAMED negative."""
    probed = []
    env = os.environ.get("LOOP_OPENCLAW_BIN", "").strip()
    if env:
        probed.append("$LOOP_OPENCLAW_BIN=%s" % env)
        if os.path.isfile(env) and os.access(env, os.X_OK):
            return env, probed
        # NO FALLBACK. An explicit override that does not resolve is an error, not
        # an invitation to go hunting - and a hermetic test that pointed here must
        # NEVER be able to reach a real gateway because its stub path was wrong.
        return None, probed
    probed.append("PATH=%s" % os.environ.get("PATH", ""))
    which = shutil.which("openclaw")
    if which:
        return which, probed
    # A LOGIN SHELL, which is where a Mac box's PATH actually gets set. This finds
    # openclaw wherever THAT box's own profile puts it - nvm, asdf, a custom npm
    # prefix - none of which a hardcoded list can anticipate. It runs before the
    # fixed candidates for exactly that reason.
    #
    # NOT A REPLACEMENT FOR THE FIXED LIST, and measured, not assumed: on the
    # operator Mac this probe comes back EMPTY even though openclaw is right there
    # in ~/.local/bin, because `bash -lc` sources the bash profile and that PATH
    # entry lives in the zsh config. The fixed candidates below are what actually
    # resolve it there. Each path catches what the other cannot.
    #
    # LOOP_NO_PROBES=1 skips it - the same seam the rest of the skill uses to stay
    # hermetic, so a self-test can never reach a real shell or a real gateway.
    if os.environ.get("LOOP_NO_PROBES", "") == "1":
        probed.append("bash -lc 'command -v openclaw' (SKIPPED: LOOP_NO_PROBES=1)")
    else:
        probed.append("bash -lc 'command -v openclaw'")
        try:
            proc = subprocess.run(["bash", "-lc", "command -v openclaw"],
                                  capture_output=True, text=True, timeout=20)
            cand = (proc.stdout or "").strip().splitlines()
            cand = cand[-1].strip() if cand else ""
            if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand, probed
        except (OSError, subprocess.SubprocessError):
            pass  # a login shell that will not run is one more probe that missed
    for d in _CANDIDATE_DIRS:
        cand = os.path.join(_expand(d), "openclaw")
        probed.append(cand)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand, probed
    return None, probed


def _run(binary, args, timeout=_PROC_TIMEOUT_S):
    """(rc, stdout, stderr). rc 127 = the binary itself did not execute, which
    is a SHELL ABORT and never a statement about cron contents."""
    try:
        p = subprocess.run([binary] + list(args), capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError as exc:
        return 127, "", "%s" % exc
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ss" % timeout
    except OSError as exc:  # noqa: BLE001 - reported, never swallowed
        return 126, "", "%s: %s" % (type(exc).__name__, exc)


def _parse_json_object(raw):
    """The gateway CLI prints config warnings on STDERR, but a stray banner on
    stdout has been seen from other subcommands, so fall back to the first line
    that opens an object. Unparsable output is UNDETERMINED, never empty."""
    raw = (raw or "").strip()
    if not raw:
        raise Undetermined("`cron list` produced EMPTY stdout")
    try:
        return json.loads(raw)
    except ValueError:
        pass
    start = raw.find("{")
    if start >= 0:
        try:
            return json.loads(raw[start:])
        except ValueError:
            pass
    raise Undetermined("`cron list --json` output did not parse as JSON (%d bytes)"
                       % len(raw))


def schedule_flag(binary):
    """Which flag THIS CLI takes a cron expression on. Probed, never assumed.

    `--schedule` was removed from this installer in v0.4.0 (2e2766c77) because
    2026.7.1-2 has no such flag - it offers --cron/--every/--at. A box still
    invoking --schedule is running an install.sh older than that. Emitting a flag
    the CLI will reject is how cron registration became structurally impossible
    while the installer reported success, so the flag is READ off `cron add --help`
    and, when neither candidate is present, we REFUSE rather than emit something
    that cannot work. The next rename surfaces here instead of silently no-opping.
    """
    rc, out, err = _run(binary, ["cron", "add", "--help"], timeout=30)
    text = (out or "") + (err or "")
    if rc != 0 and not text.strip():
        raise Undetermined("`openclaw cron add --help` exited %d with no output, so the "
                           "schedule flag could not be determined" % rc)
    for flag in ("--cron", "--schedule"):
        if re.search(r"(^|\s)%s(\s|,|=|$)" % re.escape(flag), text, re.M):
            return flag
    raise Undetermined(
        "`openclaw cron add --help` offers NEITHER --cron NOR --schedule (%d bytes of "
        "help read). REFUSING to emit a schedule flag this CLI does not accept - that "
        "is exactly how registration failed silently before v0.4.0." % len(text))


def list_jobs(binary):
    """Every cron job the gateway holds, DISABLED ONES INCLUDED. Raises
    Undetermined on any failure to see. Returns (jobs, meta)."""
    rc, out, err = _run(binary, ["cron", "list", "--all", "--json",
                                 "--timeout", _CLI_TIMEOUT_MS])
    if rc != 0:
        raise Undetermined("`openclaw cron list --all --json` exited %d (stderr: %s)"
                           % (rc, (err or "").strip().splitlines()[-1] if err.strip() else "<empty>"))
    doc = _parse_json_object(out)
    if isinstance(doc, list):
        return doc, {}
    if not isinstance(doc, dict):
        raise Undetermined("`cron list` returned %s, expected an object" % type(doc).__name__)
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise Undetermined("`cron list` payload has no `jobs` array (keys: %s)"
                           % sorted(doc.keys()))
    meta = {k: doc.get(k) for k in ("total", "hasMore", "limit", "offset", "nextOffset")}
    return jobs, meta


def job_command_text(job):
    """The shell text of a command job, however this gateway version stored it."""
    payload = job.get("payload") or {}
    if not isinstance(payload, dict):
        return ""
    if payload.get("kind") not in (None, "command"):
        return ""
    argv = payload.get("argv")
    if isinstance(argv, list):
        return " ".join(str(a) for a in argv)
    for key in ("command", "shell", "text"):
        v = payload.get(key)
        if isinstance(v, str):
            return v
    return ""


def is_ours(job):
    """True only for a command job that invokes THIS skill's tick entry point."""
    payload = job.get("payload") or {}
    if isinstance(payload, dict) and payload.get("kind") not in (None, "command"):
        return False
    return bool(_OURS_RE.search(job_command_text(job)))


def matches_name(job, desired_name):
    name = str(job.get("name") or "")
    return name == desired_name or name.startswith(JOB_NAME_PREFIX)


def _sched_expr(job):
    s = job.get("schedule")
    if isinstance(s, dict):
        return s.get("expr")
    return None


def _created(job):
    v = job.get("createdAtMs")
    return v if isinstance(v, (int, float)) else 0


def pick_keeper(candidates, desired_name, desired_cmd, desired_cwd, desired_expr):
    """The survivor of a collapse: the OLDEST job, which owns the longest run
    history. Deterministic - ties break on createdAtMs then id, so two runs pick the
    same job and the second run is a no-op. Churn is the enemy here; a job that has
    been ticking for weeks is worth more than one that matches today's spelling."""
    return sorted(candidates, key=lambda j: (_created(j), str(j.get("id") or "")))[0]


def _drift(job, desired_name, desired_cmd, desired_cwd, desired_expr):
    """What about the keeper disagrees with what this version would register.

    ONLY `schedule` is ever acted on. The rest is reported and left alone:

      name     `BOX` comes from `hostname`, which drifts (Mac.lan -> Mac). The
               question is "does THIS BOX have a watchdog tick scheduled", not
               "does one exist under the name I would pick today". Renaming a
               working job on every hostname flap is pure churn.
      command  rewriting the payload of a job that is ticking fine risks breaking
               the one thing that works, on a box we cannot see.
      cwd      same.
      disabled NEVER touched. A disabled cron is a DECISION somebody made, quite
               possibly to stop a runaway. An installer that quietly undoes a human
               decision is a worse failure than the one it is fixing.
    """
    out = []
    if _sched_expr(job) != desired_expr:
        out.append("schedule")
    noted = []
    if str(job.get("name") or "") != desired_name:
        noted.append("name")
    if job_command_text(job).find(desired_cmd) < 0:
        noted.append("command")
    payload = job.get("payload") or {}
    if desired_cwd and payload.get("cwd") != desired_cwd:
        noted.append("cwd")
    return out, noted


def reconcile(binary, name, expr, command, cwd, prune=True, log=print):
    """LIST -> DECIDE -> ACT -> LIST AGAIN AND PROVE IT.

    Mutates only jobs that are BOTH named loop-tick-* AND recognisably ours, and
    among those only ENABLED duplicates (removed) and a wrong schedule (edited).
    Returns (exit_code, result_dict)."""
    result = {"name": name, "action": None, "kept": None, "removed": [],
              "repaired": [], "noted": [], "disabled": [], "foreign": [],
              "final_count": None, "undetermined": None}

    jobs, meta = list_jobs(binary)             # may raise Undetermined
    candidates = [j for j in jobs if matches_name(j, name)]
    ours = [j for j in candidates if is_ours(j)]
    foreign = [j for j in candidates if not is_ours(j)]
    enabled_ours = [j for j in ours if j.get("enabled")]
    disabled_ours = [j for j in ours if not j.get("enabled")]
    result["foreign"] = [str(j.get("id")) for j in foreign]
    result["disabled"] = [str(j.get("id")) for j in disabled_ours]

    if not candidates:
        # A truncated page is the one way an empty candidate list can LIE, and this
        # CLI has no --offset to chase it with.
        if meta.get("hasMore"):
            raise Undetermined(
                "`cron list` reported hasMore=true (total=%s, returned=%d) and this CLI "
                "has NO --limit/--offset flag: an existing loop-tick job may be on an "
                "unfetchable page. REFUSING to add - that is how duplicates are born."
                % (meta.get("total"), len(jobs)))
        sched = schedule_flag(binary)          # may raise Undetermined
        log("  no loop-tick job present -> adding one (%s %r)" % (sched, expr))
        rc, out, err = _run(binary, ["cron", "add", "--name", name, sched, expr,
                                     "--no-deliver", "--command-cwd", cwd,
                                     "--command", command,
                                     "--timeout", _CLI_TIMEOUT_MS])
        if rc != 0:
            result["action"] = "add-failed"
            log("  ERROR: `openclaw cron add` exited %d" % rc)
            for line in (err or out or "").strip().splitlines()[-4:]:
                log("    %s" % line)
            return EX_ERR, result
        result["action"] = "added"

    elif not enabled_ours:
        # Jobs exist under our name, and NOT ONE of ours is running.
        result["action"] = "not-enabled"
        if disabled_ours:
            log("  LOUD: this box has %d loop-tick registration(s) and EVERY ONE IS "
                "DISABLED. No watchdog tick is running here." % len(disabled_ours))
            log("  NOT re-enabling and NOT adding a duplicate: a disabled cron is a")
            log("  DECISION somebody made. An operator re-enables it deliberately:")
            log("    openclaw cron list --all   # find the id")
            log("    openclaw cron enable <id>")
        if foreign:
            log("  LOUD: %d job(s) named %s* are NOT recognisable as this skill's tick "
                "(left untouched, by id: %s)"
                % (len(foreign), JOB_NAME_PREFIX, ", ".join(result["foreign"])))
        return EX_NEEDS_OPERATOR, result

    else:
        keeper = pick_keeper(enabled_ours, name, command, cwd, expr)
        result["kept"] = str(keeper.get("id"))
        result["action"] = "kept"
        drift, noted = _drift(keeper, name, command, cwd, expr)
        result["noted"] = noted
        if noted:
            log("  NOTED on the surviving job (%s), deliberately NOT changed: %s"
                % (result["kept"], ", ".join(noted)))
        if drift:
            sched = schedule_flag(binary)      # may raise Undetermined
            log("  repairing the surviving job IN PLACE (%s): schedule %r -> %r"
                % (result["kept"], _sched_expr(keeper), expr))
            rc, out, err = _run(binary, ["cron", "edit", result["kept"], sched, expr,
                                         "--timeout", _CLI_TIMEOUT_MS])
            if rc != 0:
                result["action"] = "repair-failed"
                log("  ERROR: `openclaw cron edit` exited %d" % rc)
                for line in (err or out or "").strip().splitlines()[-4:]:
                    log("    %s" % line)
                return EX_ERR, result
            result["repaired"] = drift
            result["action"] = "repaired"

        extras = [j for j in enabled_ours if str(j.get("id")) != result["kept"]]
        if extras:
            log("  LOUD: %d DUPLICATE enabled loop-tick job(s) on this box - the "
                "watchdog has been firing %dx per window"
                % (len(extras), len(extras) + 1))
            if not prune:
                log("  pruning DISABLED (--no-prune / LOOP_CRON_NO_PRUNE=1); the "
                    "duplicates are LEFT IN PLACE and this box is NOT reconciled")
                result["action"] = "duplicates-left"
                result["final_count"] = len(candidates)
                return EX_NEEDS_OPERATOR, result
            for j in extras:
                jid = str(j.get("id"))
                rc, out, err = _run(binary, ["cron", "rm", jid,
                                             "--timeout", _CLI_TIMEOUT_MS])
                if rc != 0:
                    log("  ERROR: `openclaw cron rm %s` exited %d" % (jid, rc))
                    for line in (err or out or "").strip().splitlines()[-3:]:
                        log("    %s" % line)
                    result["action"] = "prune-failed"
                    return EX_ERR, result
                result["removed"].append(jid)
                log("  removed duplicate job %s" % jid)
            result["action"] = "collapsed"

    # ---- THE PROOF. An action that is not re-observed is a claim. ------------
    jobs2, _meta2 = list_jobs(binary)          # may raise Undetermined
    final = [j for j in jobs2 if matches_name(j, name)]
    result["final_count"] = len(final)

    if foreign or disabled_ours:
        log("  NEEDS OPERATOR: %d unrecognised and %d DISABLED loop-tick job(s) remain "
            "beside the live one. Left untouched on purpose; a human decides."
            % (len(foreign), len(disabled_ours)))
        return EX_NEEDS_OPERATOR, result

    if len(final) != 1:
        log("  ERROR: after reconciling, %d loop-tick job(s) exist - expected exactly 1"
            % len(final))
        return EX_ERR, result
    only = final[0]
    if not only.get("enabled"):
        log("  ERROR: the surviving loop-tick job is DISABLED - nothing will tick")
        return EX_ERR, result
    if not is_ours(only):
        log("  ERROR: the surviving loop-tick job does not invoke this skill's tick")
        return EX_ERR, result
    if _sched_expr(only) != expr:
        log("  ERROR: the surviving loop-tick job runs on %r, expected %r"
            % (_sched_expr(only), expr))
        return EX_ERR, result
    return EX_OK, result


def status(binary, name_prefix=JOB_NAME_PREFIX, expect_expr=DEFAULT_CRON_EXPR):
    """Read-only: what loop-tick jobs does this box actually carry?

    (exit_code, dict). EX_OK requires EXACTLY ONE job, enabled, ours, on
    `expect_expr`. Exactly one - never ">= 1". That is the verified correct
    post-state across all 25 boxes remediated on 2026-08-26, and a ">= 1" check is
    precisely what let 2-12 duplicates per box pass for healthy."""
    jobs, meta = list_jobs(binary)             # may raise Undetermined
    found = [j for j in jobs if str(j.get("name") or "").startswith(name_prefix)]
    out = {"count": len(found),
           "enabled": sum(1 for j in found if j.get("enabled")),
           "ours": sum(1 for j in found if is_ours(j)),
           "ids": [str(j.get("id")) for j in found],
           "names": sorted({str(j.get("name")) for j in found}),
           "schedules": sorted({str(_sched_expr(j)) for j in found}),
           "last_run_at_ms": [j.get("lastRunAtMs") for j in found],
           "hasMore": meta.get("hasMore"), "total": meta.get("total")}
    out["expect_schedule"] = expect_expr
    if (len(found) == 1 and out["enabled"] == 1 and out["ours"] == 1
            and out["schedules"] == [expect_expr]):
        return EX_OK, out
    if not found and meta.get("hasMore"):
        raise Undetermined("no loop-tick job on this page and hasMore=true")
    return EX_ERR, out


# --------------------------------------------------------------------------- #
# self-test - hermetic, against a STUB gateway. No network, no real cron.
# --------------------------------------------------------------------------- #
_STUB = r'''#!/usr/bin/env python3
"""A fake `openclaw` for the loop_cron self-test. State lives in $FAKE_CRON_DB.
It reproduces the two behaviours that matter: `cron list` HIDES disabled jobs
unless --all, and `cron add` has NO upsert (it appends, every time).
$FAKE_CRON_FAIL=<rc> makes `cron list` exit non-zero, which is how the
UNDETERMINED path is proven."""
import json, os, sys, uuid

db = os.environ["FAKE_CRON_DB"]
jobs = json.load(open(db)) if os.path.exists(db) else []
a = sys.argv[1:]
if not a or a[0] != "cron":
    sys.exit(2)
cmd = a[1] if len(a) > 1 else ""
rest = a[2:]

def flag(name, default=None):
    return rest[rest.index(name) + 1] if name in rest else default

def save():
    json.dump(jobs, open(db, "w"))

if cmd == "add" and "--help" in rest:
    # $FAKE_CRON_HELP: "cron" (default), "schedule" (a legacy CLI), "none".
    mode = os.environ.get("FAKE_CRON_HELP", "cron")
    print("Usage: openclaw cron add [options]")
    if mode == "cron":
        print("  --cron <expr>       Cron expression (5-field or 6-field with seconds)")
    elif mode == "schedule":
        print("  --schedule <expr>   Schedule string")
    print("  --name <name>       Job name")
    sys.exit(0)
if cmd == "list":
    fail = os.environ.get("FAKE_CRON_FAIL", "")
    if fail:
        sys.stderr.write("stub: forced failure\n")
        sys.exit(int(fail))
    vis = jobs if "--all" in rest else [j for j in jobs if j["enabled"]]
    print(json.dumps({"jobs": vis, "total": len(vis), "hasMore": False,
                      "limit": len(vis), "offset": 0, "nextOffset": None}))
    sys.exit(0)
if cmd == "add":
    _expr = flag("--cron", flag("--schedule"))
    if _expr is None:
        sys.stderr.write("stub: no schedule flag given\n"); sys.exit(2)
    jobs.append({"id": str(uuid.uuid4()), "name": flag("--name"), "enabled": True,
                 "createdAtMs": 1000 + len(jobs),
                 "schedule": {"kind": "cron", "expr": _expr},
                 "payload": {"kind": "command", "cwd": flag("--command-cwd"),
                             "argv": ["sh", "-lc", flag("--command")]}})
    save(); print(json.dumps({"ok": True})); sys.exit(0)
if cmd == "enable":
    open(os.path.join(os.path.dirname(db), "enable-called"), "w").close()
    sys.exit(0)
if cmd in ("rm", "remove"):
    jid = rest[0]
    keep = [j for j in jobs if j["id"] != jid]
    if len(keep) == len(jobs):
        sys.stderr.write("stub: no such job\n"); sys.exit(1)
    jobs = keep; save(); sys.exit(0)
if cmd == "edit":
    open(os.path.join(os.path.dirname(db), "edit-called"), "w").close()
    jid = rest[0]
    for j in jobs:
        if j["id"] == jid:
            if "--name" in rest: j["name"] = flag("--name")
            if "--cron" in rest: j["schedule"] = {"kind": "cron", "expr": flag("--cron")}
            if "--schedule" in rest:
                j["schedule"] = {"kind": "cron", "expr": flag("--schedule")}
            if "--command" in rest:
                j["payload"] = {"kind": "command", "cwd": flag("--command-cwd"),
                                "argv": ["sh", "-lc", flag("--command")]}
            if "--enable" in rest: j["enabled"] = True
            save(); sys.exit(0)
    sys.stderr.write("stub: no such job\n"); sys.exit(1)
sys.exit(2)
'''


def _self_test():
    import tempfile
    print("[loop_cron] self-test: idempotent cron reconciliation (stub gateway)")
    td = tempfile.mkdtemp(prefix="loopcron-")
    stub = os.path.join(td, "openclaw")
    with open(stub, "w") as fh:
        fh.write(_STUB)
    os.chmod(stub, 0o755)
    dbp = os.path.join(td, "cron.json")
    os.environ["FAKE_CRON_DB"] = dbp
    os.environ.pop("FAKE_CRON_FAIL", None)

    name = "loop-tick-selftest-box-example"
    expr = DEFAULT_CRON_EXPR
    cwd = os.path.join(td, "skill")
    command = "bash %s/loop-companion.sh tick" % cwd
    quiet = lambda *a, **k: None  # noqa: E731 - the drills assert state, not prose

    def load():
        return json.load(open(dbp)) if os.path.exists(dbp) else []

    def seed(rows):
        json.dump(rows, open(dbp, "w"))

    def _mark(nm):
        return os.path.exists(os.path.join(td, nm))

    def _clear_marks():
        for nm in ("add-called", "edit-called", "enable-called"):
            try:
                os.remove(os.path.join(td, nm))
            except OSError:
                pass

    def ours_row(i, enabled=True, nm=name, cmdtext=None, sched=expr):
        return {"id": "seed-%d" % i, "name": nm, "enabled": enabled,
                "createdAtMs": 100 + i,
                "schedule": {"kind": "cron", "expr": sched},
                "payload": {"kind": "command", "cwd": cwd,
                            "argv": ["sh", "-lc", cmdtext or command]}}

    # ---- 1. fresh box: none -> exactly one --------------------------------
    seed([])
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    assert rc == EX_OK and res["action"] == "added", (rc, res)
    assert len(load()) == 1, load()
    print("  fresh case: PASS (0 jobs -> exactly 1, action=added)")

    # ---- 2. THE ACCEPTANCE CRITERION: ten runs, one job -------------------
    for _ in range(9):
        rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
        assert rc == EX_OK, (rc, res)
    rows = load()
    assert len(rows) == 1, "10 installs left %d jobs" % len(rows)
    assert rows[0]["enabled"] and rows[0]["schedule"]["expr"] == expr
    print("  idempotency case: PASS (10 consecutive installs -> exactly 1 job)")

    # ---- 3. the MEASURED field state: 3 duplicates collapse to 1 ----------
    seed([ours_row(1), ours_row(2), ours_row(3)])
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    rows = load()
    assert rc == EX_OK and len(rows) == 1, (rc, res, rows)
    assert res["action"] == "collapsed" and len(res["removed"]) == 2, res
    assert rows[0]["id"] == "seed-1", "collapse did not keep the OLDEST job"
    print("  duplicate-collapse case: PASS (3 enabled duplicates -> 1, oldest kept, "
          "2 removed by id)")

    # ---- 4. --all IS the fix: a DISABLED job must be SEEN, never duplicated,
    #         and never silently switched back on ---------------------------
    seed([ours_row(7, enabled=False)])
    # Prove the instrument first: without --all the stub HIDES it, so a
    # reconciler that dropped --all would see zero and add a duplicate.
    rc_h, out_h, _ = _run(stub, ["cron", "list", "--json"])
    assert rc_h == 0 and json.loads(out_h)["jobs"] == [], \
        "control failed: the stub did not hide the disabled job, so this drill proves nothing"
    _clear_marks()
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    rows = load()
    assert rc == EX_NEEDS_OPERATOR, (rc, res)
    assert len(rows) == 1 and rows[0]["id"] == "seed-7", rows
    assert rows[0]["enabled"] is False, "a deliberately DISABLED cron was switched on"
    assert not _mark("enable-called"), "called `cron enable` on a human's disabled job"
    assert not _mark("add-called"), "added a duplicate alongside a disabled registration"
    print("  disabled-job case: PASS (a job INVISIBLE without --all is FOUND - control "
          "proves the stub hides it - then left disabled, not duplicated, exit 4)")

    # ---- 5. schedule drift is repaired; name/command/cwd are NOT ----------
    # A wrong schedule is a functional defect (the fleet's correct post-state is
    # exactly */15). A drifted NAME is not: BOX comes from `hostname`, which
    # flaps Mac.lan -> Mac, and renaming a working job on every flap is churn.
    seed([ours_row(8, nm="loop-tick-oldhostname", sched="*/5 * * * *",
                   cmdtext="bash /old/path/loop-companion.sh tick")])
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    rows = load()
    assert rc == EX_OK and len(rows) == 1 and rows[0]["id"] == "seed-8", (rc, rows)
    assert rows[0]["schedule"]["expr"] == expr, rows
    assert rows[0]["name"] == "loop-tick-oldhostname", "the job was RENAMED"
    assert res["repaired"] == ["schedule"], res
    assert sorted(res["noted"]) == ["command", "name"], res
    print("  drift case: PASS (a wrong SCHEDULE is fixed in place; a drifted name and "
          "command are reported and deliberately left alone)")

    # ---- 5b. ALREADY CORRECT: touch nothing at all ------------------------
    # THE REGRESSION GUARD THAT MATTERS MOST. If this ever fails, the skill has
    # started rewriting a working cron job on every roll across the whole fleet.
    seed([ours_row(20)])
    _clear_marks()
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    assert rc == EX_OK and len(load()) == 1, (rc, load())
    assert res["action"] == "kept" and not res["repaired"], res
    assert not _mark("add-called") and not _mark("edit-called"), \
        "a correctly-scheduled box was mutated anyway"
    print("  already-correct case: PASS (rc=0, and NOT ONE of add/edit/rm was called)")

    # ---- 5c. the schedule flag is PROBED, never assumed -------------------
    os.environ["FAKE_CRON_HELP"] = "schedule"
    assert schedule_flag(stub) == "--schedule", "did not honour a legacy CLI's flag"
    os.environ["FAKE_CRON_HELP"] = "cron"
    assert schedule_flag(stub) == "--cron"
    os.environ["FAKE_CRON_HELP"] = "none"
    try:
        schedule_flag(stub)
        raise AssertionError("a CLI offering NEITHER flag did not raise Undetermined")
    except Undetermined as exc:
        assert "NEITHER" in str(exc), str(exc)
    finally:
        os.environ["FAKE_CRON_HELP"] = "cron"
    # ...and a CLI offering neither must not be able to register anything at all.
    seed([])
    os.environ["FAKE_CRON_HELP"] = "none"
    try:
        reconcile(stub, name, expr, command, cwd, log=quiet)
        raise AssertionError("registered against a CLI with no usable schedule flag")
    except Undetermined:
        pass
    finally:
        os.environ["FAKE_CRON_HELP"] = "cron"
    assert load() == [], "something was added despite an unusable schedule flag"
    print("  schedule-flag case: PASS (--cron / --schedule read off `cron add --help`; "
          "a CLI offering neither is UNDETERMINED and registers NOTHING)")

    # ---- 6. a loop-tick-* job that is NOT ours is NEVER removed -----------
    foreign = {"id": "foreign-1", "name": "loop-tick-something-else", "enabled": True,
               "createdAtMs": 5, "schedule": {"kind": "cron", "expr": "*/30 * * * *"},
               "payload": {"kind": "agentTurn", "message": "not ours"}}
    seed([foreign, ours_row(9)])
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    rows = load()
    assert rc == EX_NEEDS_OPERATOR, (rc, res)
    assert any(r["id"] == "foreign-1" for r in rows), "a job we do not own was REMOVED"
    print("  blast-radius case: PASS (an unrecognised loop-tick-* job is left "
          "untouched and reported NEEDS-OPERATOR, exit 4)")

    # ---- 7. a BROKEN listing is UNDETERMINED, never 'none' ----------------
    seed([ours_row(10)])
    os.environ["FAKE_CRON_FAIL"] = "7"
    try:
        reconcile(stub, name, expr, command, cwd, log=quiet)
        raise AssertionError("a failing `cron list` did not raise Undetermined")
    except Undetermined as exc:
        assert "exited 7" in str(exc), str(exc)
    finally:
        os.environ.pop("FAKE_CRON_FAIL", None)
    assert len(load()) == 1, "an UNDETERMINED listing still mutated the cron table"
    print("  undetermined case: PASS (`cron list` rc=7 raises UNDETERMINED naming the "
          "exit code, and adds NOTHING)")

    # ---- 8. a missing binary names every path it probed -------------------
    # HERMETIC ON PURPOSE: the shipped candidate list is swapped for dirs that
    # cannot exist, so this case exercises the NOT-FOUND branch on every box -
    # including the ones that really do have openclaw in /opt/homebrew/bin.
    # Without the swap the drill short-circuits on the real binary and proves
    # nothing, which is how a negative-result path rots untested.
    globals_ref = globals()
    real_dirs = globals_ref["_CANDIDATE_DIRS"]
    old = os.environ.pop("LOOP_OPENCLAW_BIN", None)
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.path.join(td, "empty-bin")
    os.environ["LOOP_NO_PROBES"] = "1"   # the login-shell probe is real; pin it off
    globals_ref["_CANDIDATE_DIRS"] = tuple(os.path.join(td, "nowhere-%d" % i)
                                           for i in range(len(real_dirs)))
    try:
        found, probed = find_openclaw()
        assert found is None, "resolution succeeded against dirs that do not exist"
        assert probed[0].startswith("PATH="), probed
        assert "SKIPPED" in probed[1], probed
        assert len(probed) == 2 + len(real_dirs), probed
    finally:
        globals_ref["_CANDIDATE_DIRS"] = real_dirs
        os.environ["PATH"] = old_path
        os.environ.pop("LOOP_NO_PROBES", None)
        if old:
            os.environ["LOOP_OPENCLAW_BIN"] = old
    assert all(d.startswith(("/", "~")) for d in _CANDIDATE_DIRS), _CANDIDATE_DIRS
    print("  named-negative case: PASS (a resolution failure returns None and names "
          "every probed source: PATH + a login shell + %d candidate dirs, never a "
          "bare 'not installed')" % len(_CANDIDATE_DIRS))

    # ---- 8b. an explicit override that does not resolve NEVER falls back --
    # This is a safety property, not a nicety: install.sh's self-test points
    # LOOP_OPENCLAW_BIN at a path that does not exist to force UNDETERMINED. If
    # resolution fell through to PATH, that "hermetic" test would find the REAL
    # openclaw and reconcile the REAL box's cron table.
    os.environ["LOOP_OPENCLAW_BIN"] = os.path.join(td, "no-such-openclaw")
    try:
        found, probed = find_openclaw()
        assert found is None, "a bad LOOP_OPENCLAW_BIN fell back to %s" % found
        assert len(probed) == 1 and probed[0].startswith("$LOOP_OPENCLAW_BIN="), probed
    finally:
        os.environ.pop("LOOP_OPENCLAW_BIN", None)
    print("  override-no-fallback case: PASS (an unresolvable LOOP_OPENCLAW_BIN "
          "returns None immediately - a stub-based test can never reach a real gateway)")

    # ---- 9. --no-prune reports instead of converging ----------------------
    seed([ours_row(11), ours_row(12)])
    rc, res = reconcile(stub, name, expr, command, cwd, prune=False, log=quiet)
    assert rc == EX_NEEDS_OPERATOR and len(load()) == 2, (rc, load())
    print("  no-prune case: PASS (duplicates left in place, exit 4, nothing removed)")

    shutil.rmtree(td, ignore_errors=True)
    os.environ.pop("FAKE_CRON_DB", None)
    print("[loop_cron] self-test: PASS")
    return EX_OK


def _cli(argv=None):
    ap = argparse.ArgumentParser(
        prog="loop_cron.py",
        description="Idempotent reconciliation of the Loop Protection watchdog cron job.")
    ap.add_argument("--self-test", action="store_true")
    # TEST-ONLY. Writes the stub gateway this module's own self-test uses, so
    # install.sh's self-test can be hermetic against the SAME fake instead of
    # carrying a second copy that drifts. Never used at runtime.
    ap.add_argument("--emit-stub", metavar="PATH",
                    help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=False)

    sp = sub.add_parser("reconcile", help="leave EXACTLY ONE loop-tick job, proven")
    sp.add_argument("--name", required=True)
    sp.add_argument("--cron", default=DEFAULT_CRON_EXPR)
    sp.add_argument("--command", required=True)
    sp.add_argument("--cwd", required=True)
    sp.add_argument("--no-prune", action="store_true",
                    help="report duplicates instead of collapsing them (exit 4)")
    sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("status", help="read-only: how many loop-tick jobs exist")
    sp.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    if a.emit_stub:
        with open(a.emit_stub, "w") as fh:
            fh.write(_STUB)
        os.chmod(a.emit_stub, 0o755)
        return EX_OK
    if a.self_test:
        return _self_test()
    if not a.cmd:
        ap.error("a subcommand is required (or use --self-test)")

    binary, probed = find_openclaw()
    if binary is None:
        sys.stderr.write(
            "UNDETERMINED [loop_cron]: no `openclaw` binary resolved. Probed, in order:\n")
        for p in probed:
            sys.stderr.write("  - %s\n" % p)
        sys.stderr.write(
            "  This is a RESOLUTION failure, NOT a statement that openclaw is absent "
            "or that this box has no cron job. Set LOOP_OPENCLAW_BIN to the real path.\n")
        if getattr(a, "json", False):
            print(json.dumps({"undetermined": "openclaw binary not resolved",
                              "probed": probed}, sort_keys=True))
        return EX_UNDETERMINED

    prune = not (getattr(a, "no_prune", False)
                 or os.environ.get("LOOP_CRON_NO_PRUNE", "") == "1")
    try:
        if a.cmd == "reconcile":
            rc, res = reconcile(binary, a.name, a.cron, a.command, a.cwd, prune=prune)
        else:
            rc, res = status(binary)
    except Undetermined as exc:
        sys.stderr.write("UNDETERMINED [loop_cron]: %s\n" % exc)
        sys.stderr.write("  openclaw resolved to: %s\n" % binary)
        sys.stderr.write("  Nothing was added, edited or removed.\n")
        if getattr(a, "json", False):
            print(json.dumps({"undetermined": str(exc), "openclaw": binary},
                             sort_keys=True))
        return EX_UNDETERMINED
    if getattr(a, "json", False):
        print(json.dumps(res, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(_cli())
