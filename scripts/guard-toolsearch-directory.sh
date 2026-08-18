#!/usr/bin/env bash
# guard-toolsearch-directory.sh — tools.toolSearch drift guard (fleet-wide).
#
# THE PROBLEM (measured on boxes):
#   tools.toolSearch must be the explicit object {"enabled": true, "mode": "directory"}.
#   scripts/apply-fleet-standards.sh writes exactly that — and it is still found
#   knocked off "directory" afterwards.
#
#   THE WRITER IS NOT A FLEET SCRIPT. OpenClaw's own config persistence rewrites
#   openclaw.json during the container boot window (writeConfigFile, whose
#   merge-patch guard is conditional), and the value is lost. That is why
#   apply-fleet-standards.sh's post-merge assertion cannot catch it: that check
#   is a WRITE-TIME assertion, true at the instant that script persists the file,
#   and by construction blind to a third-party writer acting BETWEEN passes.
#   Detecting this requires a PERIODIC observer. That is this script.
#
#   UPSTREAM, DELIBERATELY NOT ATTEMPTED HERE: the real root-cause fix is making
#   that merge-patch guard unconditional in OpenClaw itself. That change is
#   UPSTREAM and is NOT ours. This guard is the fleet-side mitigation that holds
#   the value until upstream lands; it is not a substitute for it and should be
#   revisited (not silently kept forever) once it does.
#
# WHY THE VALUE MATTERS:
#   A scalar `tools.toolSearch` (e.g. a bare `true`) selects a prompt surface
#   with NO hydration path: every tool call returns "Tool not found", the model
#   starts guessing, and loop-detection blocks the tool without ending the turn —
#   an unbounded, paid, self-sustaining loop. Wrong `mode` ("code"/"tools")
#   silently reintroduces the full-schema per-turn token burn that directory mode
#   exists to eliminate.
#
# WHAT THIS DOES, every fire:
#   1. Reads the config. If it cannot be read or parsed → EXIT 2, WRITE NOTHING.
#   2. Compares tools.toolSearch against {"enabled": true, "mode": "directory"}.
#   3. If it already matches → logs OK and exits 0 having written NOTHING (no
#      backup, no rewrite — a guard that churns on every fire is its own problem).
#   4. If it drifted (wrong mode, enabled=false, scalar, missing, or the key
#      absent entirely) → BACKS UP the config first, then surgically restores
#      just enabled+mode, preserving every other key including any per-box
#      toolSearch tuning (codeTimeoutMs / searchDefaultLimit / maxSearchLimit).
#
# FAIL-SAFE BY CONSTRUCTION: a guard that cannot READ the config never WRITES it.
#   Unreadable, unparseable, or missing config are all non-zero exits with the
#   file untouched. It never fabricates a config for a box that has none.
#
# SURVIVING CONTAINER RECREATION: this script is copied into the persistent
#   scripts dir by install.sh / update-skills.sh (which live on the mounted
#   volume, not the container filesystem), and its cron is (re-)registered by
#   scripts/ensure-pipeline-crons.sh on every roll via _ensure_health_cron. A
#   recreated container therefore gets both the script and the schedule back on
#   the next pass without manual intervention. It is registered as a COMMAND
#   cron: it runs the shell directly and never involves the model, so it cannot
#   burn tokens and cannot message anyone.
#
#   NOTE the cron store here is the GATEWAY's own (`openclaw cron`), not system
#   crontab — fleet VPS containers have no cron daemon, so a crontab entry would
#   silently never fire inside one. Both this script and the gateway's cron store
#   live under the mounted config volume, so both persist across recreation.
#
# RELATION TO THE ONE-BOX REFERENCE IMPLEMENTATION (read before "fixing" this):
#   A host-resident variant was test-deployed on a single VPS, running from the
#   Docker HOST's root crontab and reaching in via `docker exec`. This script is
#   the fleet-wide generalisation of it, deliberately NOT a copy:
#     - that one hardcodes its container name, so it cannot be rolled by
#       update-skills.sh to any other box; this one has no container identity at
#       all because it already runs where the config is;
#     - it repairs via `openclaw config patch --replace-path`, this one edits the
#       JSON directly and atomically — the same approach apply-fleet-standards.sh
#       already uses to write this very key, so the two writers agree;
#     - its verdict is LENIENT (treats a missing `enabled` as healthy) because
#       the old CANONICAL block omitted that key. Now that CANONICAL writes both
#       keys, this guard is STRICT and repairs the missing-`enabled` shape, so
#       writer and guard converge on one shape instead of two.
#
#   HONEST LIMITATION, stated rather than papered over: a gateway-registered cron
#   cannot fire while the gateway itself is down, whereas a host cron can. This
#   guard therefore protects against the config being REWRITTEN, which is the
#   observed failure, but not against a box whose gateway never comes up at all.
#   That case is already covered by the host-level service-selfheal watchdog
#   (platform/vps/service-selfheal/), which is where it belongs — not here.
#
# EXIT CODES:
#   0  config already correct (nothing written), OR drift detected and RESTORED
#   2  could not run — no OpenClaw root, no python3, config missing/unreadable/
#      unparseable. Nothing was written.
#   3  drift detected but the RESTORE FAILED (config left as it was found, or
#      recoverable from the backup path named in the log)
#
# ENV OVERRIDES (all optional; used by tests/unit/toolsearch-directory-shape.test.sh):
#   TOOLSEARCH_GUARD_CONFIG      explicit config path (default: $OC_ROOT/openclaw.json)
#   TOOLSEARCH_GUARD_BACKUP_DIR  backup dir        (default: $OC_ROOT/backups/toolsearch-guard)
#   TOOLSEARCH_GUARD_LOG         log file          (default: $OC_ROOT/toolsearch-drift.log)
#   TOOLSEARCH_GUARD_DRY_RUN=1   detect + log only; never back up or write
#
# bash-not-zsh. Runs under STOCK /bin/bash 3.2.57 (the fleet's Macs) as well as
# bash 5 — no associative arrays, no ${var^^}, no heredoc inside a command
# substitution.
#
# Version marker (kept in sync by scripts/bump-version.sh):
GUARD_TOOLSEARCH_DIRECTORY_VERSION="v22.0.7"

set -u

# ─── Platform detection (VPS /data first, Mac fallback) ───────────────────────
OC_ROOT=""
if [ -d /data/.openclaw ]; then
  OC_ROOT=/data/.openclaw
elif [ -d "$HOME/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"
fi

CONFIG_FILE="${TOOLSEARCH_GUARD_CONFIG:-${OC_ROOT:+$OC_ROOT/openclaw.json}}"
BACKUP_DIR="${TOOLSEARCH_GUARD_BACKUP_DIR:-${OC_ROOT:+$OC_ROOT/backups/toolsearch-guard}}"
LOG_FILE="${TOOLSEARCH_GUARD_LOG:-${OC_ROOT:+$OC_ROOT/toolsearch-drift.log}}"
DRY_RUN="${TOOLSEARCH_GUARD_DRY_RUN:-0}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  _line="$(ts) [$1] $2"
  if [ -n "${LOG_FILE:-}" ]; then
    printf '%s\n' "$_line" >> "$LOG_FILE" 2>/dev/null || true
  fi
  printf '%s\n' "$_line"
}

# ─── Log bounding ─────────────────────────────────────────────────────────────
# This guard fires every 20 minutes and logs one line per fire even when nothing
# is wrong: 72 lines/day, ~26,000 lines/year, growing without limit on a box
# nobody is watching. A monitoring script that quietly becomes a disk problem is
# its own incident. Truncate to the most recent LOG_KEEP lines once the file
# exceeds LOG_MAX. Best-effort throughout: a failure to trim must never abort a
# run or prevent the actual repair.
LOG_MAX="${TOOLSEARCH_GUARD_LOG_MAX:-5000}"
LOG_KEEP="${TOOLSEARCH_GUARD_LOG_KEEP:-2000}"
bound_log() {
  [ -n "${LOG_FILE:-}" ] || return 0
  [ -f "$LOG_FILE" ] || return 0
  _n="$(wc -l < "$LOG_FILE" 2>/dev/null | tr -dc '0-9')"
  [ -n "$_n" ] || return 0
  [ "$_n" -gt "$LOG_MAX" ] 2>/dev/null || return 0
  _tmp="${LOG_FILE}.trim.$$"
  # Copy the tail out, then write it BACK INTO the original file rather than
  # mv'ing the temp over it. This keeps the log's existing inode, mode and
  # ownership — no chmod needed, and nothing GNU-specific (`chmod --reference`
  # does not exist on the fleet's macOS boxes).
  if tail -n "$LOG_KEEP" "$LOG_FILE" > "$_tmp" 2>/dev/null; then
    cat "$_tmp" > "$LOG_FILE" 2>/dev/null || true
  fi
  rm -f "$_tmp" 2>/dev/null || true
}
# Trim on EVERY exit path, including the early fail-safe returns below.
trap bound_log EXIT

# ─── Preflight ────────────────────────────────────────────────────────────────
if [ -z "${CONFIG_FILE:-}" ]; then
  log "WARN" "no OpenClaw root found (/data/.openclaw, \$HOME/.openclaw) and no TOOLSEARCH_GUARD_CONFIG — nothing to guard"
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  log "WARN" "python3 not on PATH — required to read/write JSON safely; skipping (config untouched)"
  exit 2
fi
if [ ! -f "$CONFIG_FILE" ]; then
  log "WARN" "config not found: $CONFIG_FILE — box not onboarded yet; skipping (no config fabricated)"
  exit 2
fi
if [ ! -r "$CONFIG_FILE" ]; then
  log "WARN" "config not readable: $CONFIG_FILE — FAIL-SAFE: refusing to write a config this guard cannot read"
  exit 2
fi

# ─── Inspect: is the value already correct? ───────────────────────────────────
# Prints exactly one token on stdout:
#   OK        — already {"enabled": true, "mode": "directory"}
#   DRIFT:<desc>
#   UNPARSEABLE
_STATUS="$(CONFIG_FILE="$CONFIG_FILE" python3 <<'PYEOF'
import json, os, sys

path = os.environ["CONFIG_FILE"]
try:
    with open(path) as f:
        cfg = json.load(f)
except Exception as e:
    print("UNPARSEABLE")
    sys.exit(0)

if not isinstance(cfg, dict):
    print("UNPARSEABLE")
    sys.exit(0)

tools = cfg.get("tools")
ts = tools.get("toolSearch") if isinstance(tools, dict) else None

if ts is None:
    print("DRIFT:absent")
elif not isinstance(ts, dict):
    # A scalar here is the loop-arming shape.
    print("DRIFT:scalar=%s" % json.dumps(ts))
elif ts.get("mode") != "directory" and ts.get("enabled") is not True:
    print("DRIFT:mode=%s,enabled=%s" % (json.dumps(ts.get("mode")), json.dumps(ts.get("enabled"))))
elif ts.get("mode") != "directory":
    print("DRIFT:mode=%s" % json.dumps(ts.get("mode")))
elif ts.get("enabled") is not True:
    print("DRIFT:enabled=%s" % json.dumps(ts.get("enabled")))
else:
    print("OK")
PYEOF
)"
_INSPECT_RC=$?

if [ "$_INSPECT_RC" -ne 0 ]; then
  log "WARN" "inspection failed (python3 rc=$_INSPECT_RC) — FAIL-SAFE: config untouched"
  exit 2
fi

case "$_STATUS" in
  UNPARSEABLE)
    log "ERROR" "config is not parseable JSON: $CONFIG_FILE — FAIL-SAFE: refusing to rewrite a config this guard cannot understand. Fix the file by hand."
    exit 2
    ;;
  OK)
    log "OK" "tools.toolSearch is {\"enabled\":true,\"mode\":\"directory\"} — no drift, nothing written"
    exit 0
    ;;
  DRIFT:*)
    : # fall through to repair
    ;;
  *)
    log "WARN" "unrecognised inspection result '$_STATUS' — FAIL-SAFE: config untouched"
    exit 2
    ;;
esac

_DESC="${_STATUS#DRIFT:}"
log "DRIFT" "tools.toolSearch drifted ($_DESC) in $CONFIG_FILE — this is the OpenClaw config-persistence overwrite, not a fleet script"

if [ "$DRY_RUN" = "1" ]; then
  log "INFO" "TOOLSEARCH_GUARD_DRY_RUN=1 — detected only; no backup, no write"
  exit 0
fi

# ─── Back up BEFORE mutating ──────────────────────────────────────────────────
_BACKUP=""
if [ -n "${BACKUP_DIR:-}" ]; then
  mkdir -p "$BACKUP_DIR" 2>/dev/null || true
  if [ -d "$BACKUP_DIR" ]; then
    _BACKUP="$BACKUP_DIR/openclaw.json.$(date -u +%Y%m%dT%H%M%SZ).$$"
    if cp -p "$CONFIG_FILE" "$_BACKUP" 2>/dev/null; then
      log "INFO" "backup written: $_BACKUP"
    else
      _BACKUP=""
      log "WARN" "could not write a backup into $BACKUP_DIR"
    fi
  else
    log "WARN" "could not create backup dir $BACKUP_DIR"
  fi
fi
if [ -z "$_BACKUP" ]; then
  log "ERROR" "no backup could be written — refusing to mutate the config without one"
  exit 3
fi

# ─── Restore: surgical, atomic, everything else preserved ─────────────────────
# Only tools.toolSearch.enabled and .mode are set. Every other key in the file,
# and every other key INSIDE toolSearch (per-box tuning), is carried through
# untouched. Written to a temp file in the SAME directory and mv'd into place so
# a crash mid-write can never leave a truncated config.
CONFIG_FILE="$CONFIG_FILE" python3 <<'PYEOF'
import json, os, sys, tempfile

path = os.environ["CONFIG_FILE"]
try:
    with open(path) as f:
        cfg = json.load(f)
except Exception as e:
    sys.stderr.write("re-read failed: %s\n" % e)
    sys.exit(1)

tools = cfg.get("tools")
if not isinstance(tools, dict):
    tools = {}
    cfg["tools"] = tools

ts = tools.get("toolSearch")
if not isinstance(ts, dict):
    # Scalar / absent / null -> replace wholesale with the explicit object.
    ts = {}
    tools["toolSearch"] = ts

ts["enabled"] = True
ts["mode"] = "directory"

d = os.path.dirname(os.path.abspath(path)) or "."
fd, tmp = tempfile.mkstemp(prefix=".openclaw.json.toolsearch-guard.", dir=d)
try:
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        st = os.stat(path)
        os.chmod(tmp, st.st_mode & 0o7777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except (PermissionError, OSError):
            pass
    except OSError:
        pass
    os.replace(tmp, path)
except Exception as e:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    sys.stderr.write("write failed: %s\n" % e)
    sys.exit(1)
PYEOF
_WRITE_RC=$?

if [ "$_WRITE_RC" -ne 0 ]; then
  log "ERROR" "restore FAILED (python3 rc=$_WRITE_RC). Config left as found. Backup: $_BACKUP"
  exit 3
fi

# ─── Verify the restore actually landed (never trust the write's own success) ──
_VERIFY="$(CONFIG_FILE="$CONFIG_FILE" python3 <<'PYEOF'
import json, os
path = os.environ["CONFIG_FILE"]
try:
    with open(path) as f:
        cfg = json.load(f)
    ts = (cfg.get("tools") or {}).get("toolSearch")
    if isinstance(ts, dict) and ts.get("mode") == "directory" and ts.get("enabled") is True:
        print("OK")
    else:
        print("STILL_WRONG")
except Exception:
    print("STILL_WRONG")
PYEOF
)"

if [ "$_VERIFY" = "OK" ]; then
  log "FIXED" "tools.toolSearch restored to {\"enabled\":true,\"mode\":\"directory\"} (was: $_DESC). Backup: $_BACKUP"
  exit 0
fi

log "ERROR" "post-write verification says the value is STILL wrong — restore did not take. Backup: $_BACKUP"
exit 3
