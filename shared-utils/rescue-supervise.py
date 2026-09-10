#!/usr/bin/env python3
"""rescue-supervise.py — portability core for RR-026 (bound real processes,
fence local locks).  Stdlib only.  Python 3.6+ (Mac + Linux containers).

WHY THIS FILE EXISTS
--------------------
`65-rescue-receiver/rescue-poll.sh` used to bound its work by delegating to the
OpenClaw CLI's own `--timeout` flag and by an *age-only* mkdir lock ("a lock
older than 20 minutes is stale").  Both are unsound on a real box:

  * A CLI that ignores, mis-parses, or hangs before honouring its own timeout
    runs forever; a child that spawns a grandchild leaves the grandchild behind
    when only the direct child is signalled.  Nothing in the shell could prove
    the child actually exited — `exit 0` after a kill is not proof.
  * Age is not ownership.  A still-running previous poll outlives the 20-minute
    age threshold and had its lock directory removed underneath it; a PID that
    was recycled by an unrelated process looked like the original owner.  The
    lock had no owner token and no process-start identity to compare, so
    "release" could remove a *newer* holder's lock.

This module is the one portable implementation of both.  It is a *shared
runtime adapter*: the receiver poll imports it, and the operator executor path
uses the same lock-record shape so two transports cannot each keep a private
idea of "who holds this box" (see the target/resource fence contract).

SUBCOMMANDS
-----------
  run     Escape-proof process-group supervision with a monotonic total
          deadline: TERM the whole group, grace, KILL the whole group, reap,
          and VERIFY the group is gone.  Never reports success it did not see.
  lock    acquire | renew | release | inspect.  The lock RECORD carries the
          owner token, the owning process's start identity, the target/resource
          fence fields (target_key, generation, attempt_id, operation_id) and
          the lease deadline.  Takeover reconciles a RUNNING incumbent first
          and is never age-based.
  lease   check — "is there still enough measured budget left to finish and
          send the ACK with margin?"  The receiver computes its agent timeout
          from the LIVE lease, not from a stale constant.

EXIT CODES (stable, so the shell can branch on them)
  0  ok / child exited within budget
  2  usage or environment error
  3  refused: contended / not_owner / lease_expired / stale_generation
  4  timeout or cancellation of the supervised child (result JSON on stdout)
"""

import argparse
import errno
import json
import os
import signal
import subprocess
import sys
import time

SCHEMA_VERSION = 1
DEFAULT_GRACE_MS = 5000
DEFAULT_LEASE_SECONDS = 900
POLL_INTERVAL_S = 0.05

EX_OK = 0
EX_USAGE = 2
EX_REFUSED = 3
EX_TIMEOUT = 4


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _emit(doc, stream=None):
    (stream or sys.stdout).write(json.dumps(doc, sort_keys=True) + "\n")
    (stream or sys.stdout).flush()


# ---------------------------------------------------------------------------
# Process-start identity — the PID-reuse answer.
#
# A bare PID is not an identity: the kernel recycles it.  `ps -o lstart=` is
# present on macOS and on every Linux with procps, so this stays portable; on
# Linux we additionally fold in the kernel's own field-22 starttime from
# /proc/<pid>/stat, which cannot be influenced by the process itself.
# ---------------------------------------------------------------------------
def process_start_identity(pid):
    """Return (identity_string, alive:bool).  identity is '' when not alive."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return "", False
    if pid <= 0:
        return "", False

    parts = []
    try:
        out = subprocess.check_output(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", "replace").strip()
    except Exception:
        return "", False
    if not out:
        return "", False
    parts.append(out)

    try:
        with open("/proc/%d/stat" % pid, "rb") as fh:
            raw = fh.read().decode("utf-8", "replace")
        close = raw.rfind(")")
        if close > 0:
            fields = raw[close + 2:].split()
            if len(fields) > 19:
                parts.append("starttime=%s" % fields[19])
    except Exception:
        pass  # macOS: no /proc.  lstart alone is sufficient.

    try:
        with open("/proc/%d/boot_id" % pid, "r") as fh:
            parts.append("boot_id=%s" % fh.read().strip())
    except Exception:
        pass

    return "|".join(parts), True


def pid_alive(pid):
    return process_start_identity(pid)[1]


# ---------------------------------------------------------------------------
# run — process-group supervision
# ---------------------------------------------------------------------------
def _group_gone(pgid, timeout_s):
    """Wait until no process remains in pgid, bounded.  Returns True if gone."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                return True
            if exc.errno == errno.EPERM:
                return False
        time.sleep(POLL_INTERVAL_S)
    try:
        os.killpg(pgid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return True
    return False


def cmd_run(args):
    if not args.command:
        _emit({"ok": False, "error": "no_command"})
        return EX_USAGE

    out_fh = open(args.out, "wb") if args.out else subprocess.DEVNULL
    err_fh = open(args.err, "wb") if args.err else subprocess.DEVNULL

    started = time.monotonic()
    deadline = started + (args.deadline_ms / 1000.0)

    try:
        proc = subprocess.Popen(
            args.command,
            stdout=out_fh,
            stderr=err_fh,
            stdin=subprocess.DEVNULL,
            preexec_fn=os.setsid,   # child becomes its own process-group leader
            close_fds=True,
        )
    except Exception as exc:
        if args.out:
            out_fh.close()
        if args.err:
            err_fh.close()
        res = {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "outcome": "spawn_failed",
            "error": exc.__class__.__name__,
            "exit_code": None,
            "duration_ms": 0,
            "group_terminated": False,
        }
        _write_result(args, res)
        _emit(res)
        return EX_USAGE

    pgid = proc.pid  # setsid => pgid == child pid
    cancelled = {"sig": None}

    def _on_signal(signum, _frame):
        cancelled["sig"] = signum

    old_term = signal.signal(signal.SIGTERM, _on_signal)
    old_int = signal.signal(signal.SIGINT, _on_signal)

    outcome = "exited"
    killed_hard = False
    try:
        while True:
            if proc.poll() is not None:
                outcome = "exited"
                break
            if cancelled["sig"] is not None:
                outcome = "cancelled"
                break
            if time.monotonic() >= deadline:
                outcome = "timeout"
                break
            time.sleep(POLL_INTERVAL_S)

        if outcome != "exited":
            # TERM the whole GROUP — a grandchild that outlived its parent would
            # otherwise keep running and the box would execute twice.
            try:
                os.killpg(pgid, signal.SIGTERM)
            except OSError:
                pass
            grace_until = time.monotonic() + (args.grace_ms / 1000.0)
            while time.monotonic() < grace_until:
                if proc.poll() is not None and _group_gone(pgid, 0.0):
                    break
                time.sleep(POLL_INTERVAL_S)
            # Escalate only if the group is still alive after the grace window.
            try:
                os.killpg(pgid, 0)
                try:
                    os.killpg(pgid, signal.SIGKILL)
                    killed_hard = True
                except OSError:
                    pass
            except OSError:
                pass

        try:
            rc = proc.wait(timeout=max(2.0, args.grace_ms / 1000.0 + 2.0))
        except subprocess.TimeoutExpired:
            rc = None

        group_terminated = _group_gone(pgid, max(2.0, args.grace_ms / 1000.0 + 2.0))
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
        if args.out:
            out_fh.close()
        if args.err:
            err_fh.close()

    duration_ms = int((time.monotonic() - started) * 1000)
    res = {
        "ok": outcome == "exited" and rc == 0,
        "schema_version": SCHEMA_VERSION,
        "outcome": outcome,
        "exit_code": rc,
        "signal_killed": killed_hard,
        "group_terminated": bool(group_terminated),
        "duration_ms": duration_ms,
        "deadline_ms": args.deadline_ms,
        # A supervised child that had to be killed did NOT deliver; the caller
        # must not read "we exited" as success.  This is the receipt RR-026
        # requires: timeout/cancel outcome, persisted, with the next owner.
        "next_owner": "operator" if outcome != "exited" else "none",
    }
    _write_result(args, res)
    _emit(res)
    if outcome == "exited":
        return EX_OK
    return EX_TIMEOUT


def _write_result(args, res):
    path = getattr(args, "result_json", None)
    if not path:
        return
    tmp = "%s.tmp.%d" % (path, os.getpid())
    try:
        with open(tmp, "w") as fh:
            json.dump(res, fh, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# lock — same-box mutual exclusion with a real owner identity
# ---------------------------------------------------------------------------
def _lock_path(lock_dir):
    return os.path.join(lock_dir, "lock.json")


def _read_record(lock_dir):
    try:
        with open(_lock_path(lock_dir)) as fh:
            return json.load(fh)
    except Exception:
        return None


def _write_record(lock_dir, record):
    # Create the lock directory on demand. `cmd_lock_release` rmdir's it on a
    # clean release (so a released lock leaves no empty directory behind), so
    # every acquire that follows a release arrives at a directory that is not
    # there. Without this, acquire dies with FileNotFoundError on every fire
    # after the first clean one -- and the poller, seeing no lock, would treat
    # itself as contended and silently stop delivering.
    try:
        os.makedirs(lock_dir, exist_ok=True)
    except OSError:
        pass
    path = _lock_path(lock_dir)
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as fh:
        json.dump(record, fh, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _incumbent_state(record):
    """Classify the recorded owner.  Returns (state, identity_now).

    state is one of:
      absent     — no usable record (or no pid): cannot be reconciled
      running    — the recorded pid is alive AND its start identity matches
                   (the ORIGINAL process is genuinely still there)
      reused     — the recorded pid is alive but its start identity DIFFERS:
                   the kernel recycled the pid; the original owner is gone
      dead       — the recorded pid is not alive at all
    """
    if not record:
        return "absent", ""
    pid = record.get("pid")
    recorded = record.get("process_start_identity") or ""
    now, alive = process_start_identity(pid)
    if not alive:
        return "dead", ""
    if recorded and now == recorded:
        return "running", now
    return "reused", now


def _call_fence_adapter(path, payload):
    """Ask the shared target/resource fence.  Fail CLOSED on any error."""
    if not path:
        return None
    try:
        proc = subprocess.run(
            [path],
            input=json.dumps(payload).encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": "fence_adapter_failed",
                    "reason": "exit_%d" % proc.returncode}
        return json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    except Exception as exc:
        return {"ok": False, "error": "fence_adapter_unavailable",
                "reason": exc.__class__.__name__}


def cmd_lock_acquire(args):
    record = _read_record(args.dir)
    # The lock is held by the CALLER's long-lived process, never by this
    # short-lived helper: a record naming a pid that is already gone makes
    # "reconcile the incumbent" vacuous, which is the defect RR-026 names.
    # The shell therefore passes its own `$$`; refusing an unknown/dead owner
    # here is what keeps the record falsifiable.
    owner_pid = int(args.owner_pid) if args.owner_pid else os.getpid()
    my_identity, owner_alive = process_start_identity(owner_pid)
    if not owner_alive:
        _emit({"ok": False, "error": "owner_pid_not_alive",
               "reason": "refusing to write a lock record whose owner is "
                         "already gone (reconciliation would be vacuous)"})
        return EX_USAGE
    state, _now_identity = _incumbent_state(record)

    takeover = False
    prior = {}
    if record:
        prior = {
            "prior_owner_token": record.get("owner_token", ""),
            "prior_generation": record.get("generation"),
            "prior_attempt_id": record.get("attempt_id", ""),
            "prior_operation_id": record.get("operation_id", ""),
            "prior_state": state,
        }

    if state == "running":
        # A genuinely live owner is NEVER taken over, however old its lock is.
        # This is the whole defect RR-026 names ("a still-running old owner can
        # outlive lock age"); age is deliberately not consulted here at all.
        _emit({"ok": False, "error": "lock_held", "reason": "owner_running",
               "holder_owner_token": record.get("owner_token", ""),
               "holder_generation": record.get("generation"),
               "holder_pid": record.get("pid")})
        return EX_REFUSED

    if record and not args.allow_takeover:
        # Lapsed/reused/dead is NOT free.  Default answer is to refuse and let
        # the caller present reconciliation evidence.
        _emit({"ok": False, "error": "lock_held",
               "reason": "lapsed_without_reconciliation", "prior_state": state})
        return EX_REFUSED

    if record and args.allow_takeover:
        if not args.takeover_note:
            _emit({"ok": False, "error": "takeover_note_required"})
            return EX_REFUSED
        if args.takeover_generation is None:
            _emit({"ok": False, "error": "lock_held",
                   "reason": "takeover_generation_required"})
            return EX_REFUSED
        if str(args.takeover_generation) != str(record.get("generation")):
            _emit({"ok": False, "error": "lock_held",
                   "reason": "takeover_generation_mismatch",
                   "observed_generation": record.get("generation")})
            return EX_REFUSED
        # The authoritative cross-transport fence is consulted when this box
        # has the adapter.  Fail closed when it is configured but unhappy.
        verdict = _call_fence_adapter(args.fence_adapter, {
            "op": "acquireTargetFence",
            "targetKind": args.target_kind,
            "resourceId": args.resource_id,
            "targetKey": args.target_key,
            "generation": args.generation,
            "attemptId": args.attempt_id,
            "operationId": args.operation_id,
            "allowTakeover": True,
            "takeoverGeneration": args.takeover_generation,
            "takeoverNote": args.takeover_note,
        })
        if verdict is not None and not verdict.get("ok"):
            _emit({"ok": False, "error": "fence_refused",
                   "reason": verdict.get("reason") or verdict.get("error")})
            return EX_REFUSED
        takeover = True

    now_ms = int(time.time() * 1000)
    rec = {
        "schema_version": SCHEMA_VERSION,
        "owner_token": args.owner_token,
        "owner_kind": "receiver",
        "pid": owner_pid,
        "process_start_identity": my_identity,
        "target_key": args.target_key,
        "target_kind": args.target_kind,
        "resource_id": args.resource_id,
        "generation": args.generation,
        "attempt_id": args.attempt_id,
        "operation_id": args.operation_id,
        "acquired_at": _now_iso(),
        "acquired_monotonic_s": time.monotonic(),
        "lease_expires_at_ms": now_ms + int(args.lease_seconds * 1000),
        "takeover": takeover,
    }
    rec.update(prior)
    try:
        _write_record(args.dir, rec)
    except Exception as exc:
        _emit({"ok": False, "error": "lock_write_failed",
               "reason": exc.__class__.__name__})
        return EX_USAGE

    _emit({"ok": True, "takeover": takeover, "generation": args.generation,
           "owner_token": args.owner_token, "lease_expires_at_ms":
           rec["lease_expires_at_ms"], "prior_state": prior.get("prior_state", "")})
    return EX_OK


def cmd_lock_renew(args):
    record = _read_record(args.dir)
    if not record:
        _emit({"ok": False, "error": "not_owner", "reason": "no_record"})
        return EX_REFUSED
    if record.get("owner_token") != args.owner_token:
        _emit({"ok": False, "error": "not_owner", "reason": "owner_token_mismatch"})
        return EX_REFUSED
    if args.generation is not None and str(record.get("generation")) != str(args.generation):
        _emit({"ok": False, "error": "conflict", "reason": "stale_generation"})
        return EX_REFUSED
    now_ms = int(time.time() * 1000)
    if now_ms > int(record.get("lease_expires_at_ms") or 0):
        _emit({"ok": False, "error": "lease_expired",
               "reason": "renew_after_expiry"})
        return EX_REFUSED
    record["lease_expires_at_ms"] = now_ms + int(args.lease_seconds * 1000)
    record["renewed_at"] = _now_iso()
    _write_record(args.dir, record)
    _emit({"ok": True, "lease_expires_at_ms": record["lease_expires_at_ms"]})
    return EX_OK


def cmd_lock_release(args):
    record = _read_record(args.dir)
    if not record:
        _emit({"ok": True, "released": False, "reason": "no_record"})
        return EX_OK
    # A stale owner can never release a newer holder's lock: identity first,
    # process start identity second.
    if args.owner_token and record.get("owner_token") != args.owner_token:
        _emit({"ok": False, "error": "not_owner", "reason": "stale_generation",
               "holder_generation": record.get("generation")})
        return EX_REFUSED
    state, _ = _incumbent_state(record)
    if state == "running" and not args.owner_token:
        _emit({"ok": False, "error": "not_owner",
               "reason": "owner_running_untokened_release"})
        return EX_REFUSED
    try:
        os.unlink(_lock_path(args.dir))
    except OSError:
        pass
    try:
        os.rmdir(args.dir)
    except OSError:
        pass
    _emit({"ok": True, "released": True, "prior_state": state})
    return EX_OK


def cmd_lock_inspect(args):
    record = _read_record(args.dir)
    if not record:
        _emit({"ok": False, "error": "no_record"})
        return EX_REFUSED
    state, now_identity = _incumbent_state(record)
    _emit({"ok": True, "state": state, "record": record,
           "live_identity": now_identity})
    return EX_OK


# ---------------------------------------------------------------------------
# lease — negotiate the deadline, or stop before losing it with ACK margin
# ---------------------------------------------------------------------------
def cmd_lease_check(args):
    """Is there still measured budget for the work plus the ACK, with margin?

    Takes the lease the SERVER actually granted (the live RR-07 value is 900s;
    the 600 in this script's old `--timeout 600` was a stale constant) and the
    monotonic time already spent, and answers with the remaining budget so the
    caller can size the child's deadline instead of guessing.
    """
    elapsed = args.elapsed_ms / 1000.0
    remaining = args.lease_seconds - elapsed
    usable = remaining - args.ack_margin_s - args.reserve_s
    budget_ms = int(max(0.0, usable) * 1000)
    ok = usable > 0
    _emit({
        "ok": ok,
        "lease_seconds": args.lease_seconds,
        "elapsed_s": round(elapsed, 3),
        "remaining_s": round(remaining, 3),
        "ack_margin_s": args.ack_margin_s,
        "reserve_s": args.reserve_s,
        "budget_ms": budget_ms,
        "reason": "" if ok else "insufficient_budget_for_ack_margin",
    })
    return EX_OK if ok else EX_REFUSED


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(prog="rescue-supervise.py")
    sub = parser.add_subparsers(dest="group")

    run = sub.add_parser("run")
    run.add_argument("--deadline-ms", type=int, default=600000)
    run.add_argument("--grace-ms", type=int, default=DEFAULT_GRACE_MS)
    run.add_argument("--out", default=None)
    run.add_argument("--err", default=None)
    run.add_argument("--result-json", dest="result_json", default=None)
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=cmd_run)

    lock = sub.add_parser("lock")
    lock_sub = lock.add_subparsers(dest="action")

    acq = lock_sub.add_parser("acquire")
    acq.add_argument("--dir", required=True)
    acq.add_argument("--owner-token", dest="owner_token", required=True)
    acq.add_argument("--target-key", dest="target_key", default="")
    acq.add_argument("--target-kind", dest="target_kind", default="box")
    acq.add_argument("--resource-id", dest="resource_id", default="")
    acq.add_argument("--generation", default="")
    acq.add_argument("--attempt-id", dest="attempt_id", default="")
    acq.add_argument("--operation-id", dest="operation_id", default="")
    acq.add_argument("--lease-seconds", dest="lease_seconds", type=float,
                     default=DEFAULT_LEASE_SECONDS)
    acq.add_argument("--owner-pid", dest="owner_pid", default=None)
    acq.add_argument("--allow-takeover", dest="allow_takeover", action="store_true")
    acq.add_argument("--takeover-generation", dest="takeover_generation", default=None)
    acq.add_argument("--takeover-note", dest="takeover_note", default="")
    acq.add_argument("--fence-adapter", dest="fence_adapter", default=None)
    acq.set_defaults(func=cmd_lock_acquire)

    ren = lock_sub.add_parser("renew")
    ren.add_argument("--dir", required=True)
    ren.add_argument("--owner-token", dest="owner_token", required=True)
    ren.add_argument("--generation", default=None)
    ren.add_argument("--lease-seconds", dest="lease_seconds", type=float,
                     default=DEFAULT_LEASE_SECONDS)
    ren.set_defaults(func=cmd_lock_renew)

    rel = lock_sub.add_parser("release")
    rel.add_argument("--dir", required=True)
    rel.add_argument("--owner-token", dest="owner_token", default="")
    rel.set_defaults(func=cmd_lock_release)

    ins = lock_sub.add_parser("inspect")
    ins.add_argument("--dir", required=True)
    ins.set_defaults(func=cmd_lock_inspect)

    lease = sub.add_parser("lease")
    lease_sub = lease.add_subparsers(dest="action")
    chk = lease_sub.add_parser("check")
    chk.add_argument("--lease-seconds", dest="lease_seconds", type=float, required=True)
    chk.add_argument("--elapsed-ms", dest="elapsed_ms", type=float, default=0.0)
    chk.add_argument("--ack-margin-s", dest="ack_margin_s", type=float, default=30.0)
    chk.add_argument("--reserve-s", dest="reserve_s", type=float, default=15.0)
    chk.set_defaults(func=cmd_lease_check)

    return parser


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return EX_USAGE
    if args.func is cmd_run and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
