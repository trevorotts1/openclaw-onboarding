#!/usr/bin/env bash
# Skill 72 end-of-run sweep: ownership-aware process cleanup (MG-029).
#
# This script terminates leftover render processes, and ONLY processes
# the motion runtime recorded as its own. It replaces the previous
# pattern-matching sweep, which killed any headless Chromium whose
# command line contained a marker substring: that could kill another
# job's browser (every run shared the default marker), an unrelated
# process that happened to carry the string, and it could never prove
# the processes it killed were the pipeline's.
#
# How ownership works now: every render child the runtime launches is
# recorded in a per-job registry file (see
# runtime/src/isolation/processes.ts) with the job's ownership token,
# the child pid, its process group, and the pid's kernel start-time.
# This sweep reads those records and signals a process only when
# ownership is proven at signal time:
#   - a recorded pid whose current start-time still equals the
#     recorded start-time (a recycled pid fails and is left alone), or
#   - a live pid whose /proc/<pid>/environ carries the job's token
#     (descendants inherit it, which is how orphaned browser children
#     of a dead engine process are still found).
# SIGTERM first, a grace second, then SIGKILL for survivors, each
# re-verified before the kill signal. Anything unverifiable is left
# running and reported. A visible browser, an unrecorded headless
# browser, and every other process on the machine are invisible to
# this script by construction.
#
# Usage:
#   bash scripts/sweep-chromium.sh [registry-dir-or-file]
# The registry location defaults to $MOTION_PROCESS_REGISTRY_DIR, else
# ~/.local/state/motion-render/processes. A legacy marker argument
# (the old calling convention) is accepted and ignored with a notice:
# markers are no longer how processes are chosen.
set -u

ARG="${1:-}"
REGISTRY_DIR=""
if [ -n "$ARG" ] && { [ -d "$ARG" ] || [ -f "$ARG" ]; }; then
  REGISTRY_DIR="$ARG"
elif [ -n "${MOTION_PROCESS_REGISTRY_DIR:-}" ]; then
  REGISTRY_DIR="$MOTION_PROCESS_REGISTRY_DIR"
else
  REGISTRY_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/motion-render/processes"
fi
if [ -n "$ARG" ] && [ "$ARG" != "$REGISTRY_DIR" ] && [ ! -e "$ARG" ]; then
  echo "sweep: note: marker argument '$ARG' ignored; cleanup is ownership-based now (MG-029)"
fi

if [ ! -e "$REGISTRY_DIR" ]; then
  echo "sweep: no process registry at $REGISTRY_DIR; no recorded render processes to clean"
  exit 0
fi

python3 - "$REGISTRY_DIR" <<'PYEOF'
import json
import os
import signal
import sys
import time

registry_path = sys.argv[1]


def read_stat(pid):
    """(state, pgid, starttime) from /proc/<pid>/stat, or None."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as fh:
            raw = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    fields = raw[close + 2:].split(" ")
    try:
        return fields[0], int(fields[2]), int(fields[19])
    except (ValueError, IndexError):
        return None


def alive(pid):
    stat = read_stat(pid)
    return stat is not None and stat[0] not in ("Z", "X")


def environ_token(pid):
    try:
        with open("/proc/%d/environ" % pid, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    for entry in raw.split(b"\0"):
        if entry.startswith(b"MOTION_JOB_TOKEN="):
            return entry.split(b"=", 1)[1].decode("utf-8", "replace")
    return None


def own_pgid():
    stat = read_stat(os.getpid())
    return stat[1] if stat else None


def load_registry_files(path):
    files = []
    if os.path.isfile(path):
        files.append(path)
    elif os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if name.endswith(".json"):
                files.append(os.path.join(path, name))
    out = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("processes"), list):
            out.append((f, doc))
    return out


def save_registry(path, doc):
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=2) + "\n")
    os.replace(tmp, path)


terminated = 0
already_gone = 0
refused = 0
jobs_touched = 0

for path, doc in load_registry_files(registry_path):
    token = doc.get("token")
    running = [p for p in doc["processes"] if p.get("state") == "running"]
    if not running:
        continue
    jobs_touched += 1
    targets = {}  # pid -> record or None (token-proven descendant)
    groups = {}   # pgid -> leader pid, only for identity-verified roots
    for rec in running:
        pid = rec.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            continue
        if not alive(pid):
            already_gone += 1
            rec["state"] = "exited"
            continue
        stat = read_stat(pid)
        recorded_start = rec.get("startTimeTicks")
        if recorded_start is not None:
            verified = stat is not None and stat[2] == recorded_start
        else:
            verified = environ_token(pid) == token
        if not verified:
            refused += 1
            continue
        targets[pid] = rec
        pgid = rec.get("pgid")
        if isinstance(pgid, int) and pgid > 0:
            groups[pgid] = pid
    # Descendants carrying the job token (browser children of a dead
    # engine process are the case this exists for).
    if token:
        try:
            names = os.listdir("/proc")
        except OSError:
            names = []
        for name in names:
            if not name.isdigit():
                continue
            pid = int(name)
            if pid == os.getpid() or pid in targets:
                continue
            if alive(pid) and environ_token(pid) == token:
                targets[pid] = None
    if not targets:
        save_registry(path, doc)
        continue

    def signal_targets(sig, recheck):
        for pid, rec in list(targets.items()):
            if not alive(pid):
                continue
            if recheck:
                if rec is not None and rec.get("startTimeTicks") is not None:
                    stat = read_stat(pid)
                    if stat is None or stat[2] != rec["startTimeTicks"]:
                        refused_local.append(pid)
                        del targets[pid]
                        continue
                elif environ_token(pid) != token:
                    refused_local.append(pid)
                    del targets[pid]
                    continue
            pgid = rec.get("pgid") if rec else None
            sent = False
            if isinstance(pgid, int) and pgid > 0 and pgid != own_pgid():
                try:
                    os.killpg(pgid, sig)
                    sent = True
                except OSError:
                    sent = False
            if not sent:
                try:
                    os.kill(pid, sig)
                except OSError:
                    pass

    refused_local = []
    signal_targets(signal.SIGTERM, recheck=False)
    for pgid, leader in groups.items():
        if leader in targets and pgid != own_pgid():
            try:
                os.killpg(pgid, signal.SIGTERM)
            except OSError:
                pass
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if all(not alive(pid) for pid in targets):
            break
        time.sleep(0.05)
    signal_targets(signal.SIGKILL, recheck=True)
    refused += len(refused_local)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if all(not alive(pid) for pid in targets):
            break
        time.sleep(0.05)
    for pid, rec in list(targets.items()):
        if alive(pid):
            refused += 1
            continue
        terminated += 1
        if rec is not None:
            rec["state"] = "terminated"
    save_registry(path, doc)

print(
    "sweep: terminated %d recorded render process(es) across %d job(s); "
    "%d already exited; %d left running (ownership not provable)"
    % (terminated, jobs_touched, already_gone, refused)
)
PYEOF
