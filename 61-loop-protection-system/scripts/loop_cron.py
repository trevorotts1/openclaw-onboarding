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
    """The survivor of a collapse. Preference order, most decisive first:
       1. enabled over disabled (a live job's run history is worth keeping)
       2. an EXACT name match
       3. a payload that already matches what we want (zero repair needed)
       4. the OLDEST - it owns the longest run history, and churn is the enemy
    Deterministic: ties break on createdAtMs then id, so two runs pick the same
    job and the second run is a no-op."""
    def rank(j):
        payload = j.get("payload") or {}
        cwd_ok = (not desired_cwd) or (payload.get("cwd") == desired_cwd)
        exact = (job_command_text(j).find(desired_cmd) >= 0) and cwd_ok \
            and _sched_expr(j) == desired_expr
        return (0 if j.get("enabled") else 1,
                0 if str(j.get("name") or "") == desired_name else 1,
                0 if exact else 1,
                _created(j),
                str(j.get("id") or ""))
    return sorted(candidates, key=rank)[0]


def _drift(job, desired_name, desired_cmd, desired_cwd, desired_expr):
    """What about the keeper disagrees with what this version wants."""
    out = []
    if str(job.get("name") or "") != desired_name:
        out.append("name")
    if _sched_expr(job) != desired_expr:
        out.append("schedule")
    if job_command_text(job).find(desired_cmd) < 0:
        out.append("command")
    payload = job.get("payload") or {}
    if desired_cwd and payload.get("cwd") != desired_cwd:
        out.append("cwd")
    if not job.get("enabled"):
        out.append("disabled")
    return out


def reconcile(binary, name, expr, command, cwd, prune=True, log=print):
    """LIST -> DECIDE -> ACT -> LIST AGAIN AND PROVE IT.
    Returns (exit_code, result_dict). Mutates only jobs that are BOTH named
    loop-tick-* AND recognisably ours."""
    result = {"name": name, "action": None, "kept": None, "removed": [],
              "repaired": [], "foreign": [], "final_count": None,
              "undetermined": None}

    jobs, meta = list_jobs(binary)             # may raise Undetermined
    candidates = [j for j in jobs if matches_name(j, name)]
    ours = [j for j in candidates if is_ours(j)]
    foreign = [j for j in candidates if not is_ours(j)]
    result["foreign"] = [str(j.get("id")) for j in foreign]

    if not candidates:
        # A truncated page is the one way an empty candidate list can LIE, and
        # this CLI has no --offset to chase it with.
        if meta.get("hasMore"):
            raise Undetermined(
                "`cron list` reported hasMore=true (total=%s, returned=%d) and this CLI "
                "has NO --limit/--offset flag: an existing loop-tick job may be on an "
                "unfetchable page. REFUSING to add - that is how duplicates are born."
                % (meta.get("total"), len(jobs)))
        log("  no loop-tick job present -> adding one")
        rc, out, err = _run(binary, ["cron", "add", "--name", name, "--cron", expr,
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
    else:
        keeper = pick_keeper(ours or candidates, name, command, cwd, expr)
        result["kept"] = str(keeper.get("id"))
        result["action"] = "kept"
        if is_ours(keeper):
            drift = _drift(keeper, name, command, cwd, expr)
            if drift:
                log("  repairing the surviving job IN PLACE (%s): %s"
                    % (result["kept"], ", ".join(drift)))
                args = ["cron", "edit", result["kept"], "--name", name,
                        "--cron", expr, "--no-deliver", "--command-cwd", cwd,
                        "--command", command, "--timeout", _CLI_TIMEOUT_MS]
                if "disabled" in drift:
                    args.append("--enable")
                rc, out, err = _run(binary, args)
                if rc != 0:
                    result["action"] = "repair-failed"
                    log("  ERROR: `openclaw cron edit` exited %d" % rc)
                    for line in (err or out or "").strip().splitlines()[-4:]:
                        log("    %s" % line)
                    return EX_ERR, result
                result["repaired"] = drift
                result["action"] = "repaired"
        extras = [j for j in ours if str(j.get("id")) != result["kept"]]
        if extras:
            log("  LOUD: %d DUPLICATE loop-tick job(s) on this box - the watchdog has "
                "been firing %dx per window" % (len(extras), len(extras) + 1))
            if not prune:
                log("  pruning DISABLED (--no-prune / LOOP_CRON_NO_PRUNE=1); "
                    "the duplicates are LEFT IN PLACE and this box is NOT reconciled")
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

    if foreign:
        log("  NEEDS OPERATOR: %d job(s) named %s* are NOT recognisable as this "
            "skill's tick (left untouched, by id: %s)"
            % (len(foreign), JOB_NAME_PREFIX, ", ".join(result["foreign"])))
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
    return EX_OK, result


def status(binary, name_prefix=JOB_NAME_PREFIX):
    """Read-only: what loop-tick jobs does this box actually carry?
    (exit_code, dict). Exactly one enabled job of ours = EX_OK."""
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
    if len(found) == 1 and out["enabled"] == 1 and out["ours"] == 1:
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
    jobs.append({"id": str(uuid.uuid4()), "name": flag("--name"), "enabled": True,
                 "createdAtMs": 1000 + len(jobs),
                 "schedule": {"kind": "cron", "expr": flag("--cron")},
                 "payload": {"kind": "command", "cwd": flag("--command-cwd"),
                             "argv": ["sh", "-lc", flag("--command")]}})
    save(); print(json.dumps({"ok": True})); sys.exit(0)
if cmd in ("rm", "remove"):
    jid = rest[0]
    keep = [j for j in jobs if j["id"] != jid]
    if len(keep) == len(jobs):
        sys.stderr.write("stub: no such job\n"); sys.exit(1)
    jobs = keep; save(); sys.exit(0)
if cmd == "edit":
    jid = rest[0]
    for j in jobs:
        if j["id"] == jid:
            if "--name" in rest: j["name"] = flag("--name")
            if "--cron" in rest: j["schedule"] = {"kind": "cron", "expr": flag("--cron")}
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

    # ---- 4. --all IS the fix: a DISABLED job must be found, not duplicated -
    seed([ours_row(7, enabled=False)])
    # Prove the instrument first: without --all the stub HIDES it, so a
    # reconciler that dropped --all would see zero and add a duplicate.
    rc_h, out_h, _ = _run(stub, ["cron", "list", "--json"])
    assert rc_h == 0 and json.loads(out_h)["jobs"] == [], \
        "control failed: the stub did not hide the disabled job, so this drill proves nothing"
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    rows = load()
    assert rc == EX_OK and len(rows) == 1, (rc, res, rows)
    assert rows[0]["id"] == "seed-7" and rows[0]["enabled"], rows
    assert "disabled" in res["repaired"], res
    print("  disabled-job case: PASS (a job INVISIBLE without --all is found and "
          "re-enabled in place, NOT duplicated - control proves the stub hides it)")

    # ---- 5. drift repaired in place, never re-added -----------------------
    seed([ours_row(8, nm="loop-tick-oldhostname", sched="*/5 * * * *",
                   cmdtext="bash /old/path/loop-companion.sh tick")])
    rc, res = reconcile(stub, name, expr, command, cwd, log=quiet)
    rows = load()
    assert rc == EX_OK and len(rows) == 1 and rows[0]["id"] == "seed-8", (rc, rows)
    assert rows[0]["name"] == name and rows[0]["schedule"]["expr"] == expr
    assert sorted(res["repaired"]) == ["command", "name", "schedule"], res
    print("  drift case: PASS (a renamed/re-scheduled/moved job is edited IN PLACE)")

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
    globals_ref["_CANDIDATE_DIRS"] = tuple(os.path.join(td, "nowhere-%d" % i)
                                           for i in range(len(real_dirs)))
    try:
        found, probed = find_openclaw()
        assert found is None, "resolution succeeded against dirs that do not exist"
        assert probed[0].startswith("PATH="), probed
        assert len(probed) == 1 + len(real_dirs), probed
    finally:
        globals_ref["_CANDIDATE_DIRS"] = real_dirs
        os.environ["PATH"] = old_path
        if old:
            os.environ["LOOP_OPENCLAW_BIN"] = old
    assert all(d.startswith(("/", "~")) for d in _CANDIDATE_DIRS), _CANDIDATE_DIRS
    print("  named-negative case: PASS (a resolution failure returns None and names "
          "every probed source: PATH + %d candidate dirs, never a bare 'not installed')"
          % len(_CANDIDATE_DIRS))

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
