#!/usr/bin/env bash
# scripts/ensure-burn-guard.sh — keep OpenClaw's weekly skill-collection-review crons OFF.
#
# WHY: OpenClaw 2026.9.x defaults skills.workshop.autonomous.mode to "auto". In auto the
# gateway projects one SYSTEM-OWNED weekly agentTurn cron per agent
# ("skill-collection-review-<agent>", src/cron/skill-collection-review-monitor.ts) with
# exec/read/write tools and no turn cap. Measured 2026-09-29: one run = 127 LLM calls /
# 30M tokens; >=374M tokens/week fleet-wide with no owner activity behind it.
#
# HOW (the method proven on 35 live boxes): `openclaw cron edit --disable` is REFUSED for
# system-owned jobs ("system-owned monitor jobs cannot be edited by cron clients") and the
# reconciler re-projects them on every reload. The supported switch is the config key:
# `openclaw config set skills.workshop.autonomous.mode propose` hot-reloads (no gateway
# restart) and the reconciler flips every review job to enabled:false — KEPT, never
# deleted. This script sets the key when it is unset or "auto", leaves an explicit
# "propose"/"off" alone, then reads the review jobs back and reports:
#   burn-guard: mode=<propose|off>, review crons disabled N (already off M)
#
# THE VALUE IS CHOSEN BY THE INSTALLED BUILD'S OWN SCHEMA, never hard-coded. OpenClaw
# 2026.10.5 retired Skill Workshop proposals: the key accepts only "off" | "auto", and a
# config still holding "propose" is REJECTED — every openclaw CLI command then exits 1
# ("Invalid config ... skills.workshop.autonomous.mode"). So: builds that still accept
# "propose" (2026.10.1-2026.10.4) get "propose"; 2026.10.5+ get "off" (the vendor's own
# `doctor --fix` maps propose -> off; "off" disables the background review, which is the
# burn-guard intent). A box already holding "propose" on a build that rejects it is
# migrated IN THE FILE first (the CLI cannot read or write a config it rejects), via
# `oc-schema-migrate.py workshop-migrate`; that is the only time this writes without
# `config set`, and it takes the same backup. Report line then reads:
#   burn-guard: mode=off, review crons disabled 0 (already off 0); migrated: ... backup ...
#
# CONTRACT: idempotent; backs up openclaw.json ONLY when it writes; never restarts the
# gateway; any failure (no CLI, key unknown on this build, write rejected, cron list
# unreadable) is an ADVISORY on the burn-guard line and the script ALWAYS exits 0 — it can
# never fail or roll back an install/update. Runs as the gateway user on Mac, Hostinger
# Docker and Contabo (update-skills.sh / install.sh already run as that user there).
#
# Env: BURN_GUARD_WAIT_S (default 60) — how long to wait for the reconciler to flip jobs.
set -uo pipefail

P="burn-guard:"
OC_JSON="$HOME/.openclaw/openclaw.json"
[ -f /data/.openclaw/openclaw.json ] && OC_JSON=/data/.openclaw/openclaw.json
WAIT_S="${BURN_GUARD_WAIT_S:-60}"

if ! command -v openclaw >/dev/null 2>&1; then
  echo "$P ADVISORY openclaw CLI not on PATH — mode not checked, crons not checked"; exit 0
fi

# review_counts -> "<total> <enabled>" of skill-collection-review jobs, or nothing if unreadable.
review_counts() {
  local raw
  raw="$(openclaw cron list --all --json 2>/dev/null)" || raw=""
  [ -n "$raw" ] || raw="$(openclaw cron list --json 2>/dev/null)" || raw=""
  OC_CRON_RAW="$raw" python3 - <<'PYEOF' 2>/dev/null
import json, os
raw = os.environ.get("OC_CRON_RAW", "")
try:
    data = json.loads(raw[raw.index("{"):])
except Exception:
    raise SystemExit(1)
jobs = [j for j in data.get("jobs", []) if str(j.get("declarationKey") or "").startswith("skill-collection-review:")]
print(len(jobs), sum(1 for j in jobs if j.get("enabled") is not False))
PYEOF
}

# Ask the installed build what it accepts. A missing helper/schema falls back to the
# pre-2026.10.5 behaviour ("propose"); `config set` below is validated by the build itself,
# so a wrong guess is rejected (ADVISORY), never written.
MIGRATOR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/oc-schema-migrate.py"
TARGET="propose"; mig_note=""
schema_f="$(mktemp "${TMPDIR:-/tmp}/burn-guard-schema.XXXXXX" 2>/dev/null)" || schema_f=""
if [ -n "$schema_f" ] && [ -f "$MIGRATOR" ] && command -v python3 >/dev/null 2>&1 \
   && openclaw config schema > "$schema_f" 2>/dev/null; then
  # No answer (unparseable schema, or a build with no such key) = no migration: skip to the old path.
  t="$(python3 "$MIGRATOR" workshop-target "$schema_f" 2>/dev/null)" && [ -n "$t" ] && TARGET="$t" || t=""
  staged="$OC_JSON.burn-guard-staged.$$"
  if [ -z "$t" ]; then
    :
  elif mig="$(python3 "$MIGRATOR" workshop-migrate "$schema_f" "$OC_JSON" "$staged" 2>&1)"; then
    case "$mig" in
      migrated:*)
        bk="$OC_JSON.burn-guard-$(date +%Y%m%dT%H%M%S)"
        cp -p "$OC_JSON" "$bk" 2>/dev/null || bk=""
        # `cat >` writes THROUGH the existing inode: owner/group/mode survive (see oc-atomic-upgrade.sh).
        if [ -n "$bk" ] && cat "$staged" > "$OC_JSON" 2>/dev/null; then
          mig_note="; $mig, backup $bk"
        else
          [ -n "$bk" ] && rm -f "$bk"
          rm -f "$staged" "$schema_f"
          echo "$P ADVISORY this build rejects the workshop mode in openclaw.json but the file could not be migrated — left unchanged"; exit 0
        fi ;;
    esac
  else
    rm -f "$staged" "$schema_f"
    echo "$P ADVISORY this build rejects the workshop mode in openclaw.json and it could not be migrated (${mig:0:120}) — left unchanged"; exit 0
  fi
  rm -f "$staged"
fi
[ -n "$schema_f" ] && rm -f "$schema_f"

cur="$(openclaw config get skills.workshop.autonomous.mode 2>&1 | tr -d '\r')"
case "$cur" in
  *"valid but unset"*) prior="unset" ;;
  *"Unknown config path"*) echo "$P ADVISORY this OpenClaw build has no skills.workshop.autonomous.mode — nothing to guard"; exit 0 ;;
  *) prior="$(printf '%s' "$cur" | tail -n 1 | tr -d '[:space:]"')" ;;
esac

before="$(review_counts)"
mode="$prior"; note="$mig_note"
case "$prior" in
  unset|auto)
    bk="$OC_JSON.burn-guard-$(date +%Y%m%dT%H%M%S)"
    cp -p "$OC_JSON" "$bk" 2>/dev/null || bk=""
    if openclaw config set skills.workshop.autonomous.mode "$TARGET" >/dev/null 2>&1; then
      # A root-run write must hand openclaw.json back to the gateway user (uid 1000 on VPS).
      [ "$(id -u)" = "0" ] && [ -f /data/.openclaw/openclaw.json ] && chown 1000:1000 /data/.openclaw/openclaw.json 2>/dev/null
      mode="$TARGET"; note="; set from $prior, backup ${bk:-FAILED}"
    else
      [ -n "$bk" ] && rm -f "$bk"   # nothing changed, so no backup to keep
      echo "$P ADVISORY could not set skills.workshop.autonomous.mode (still $prior) — review crons stay ON until it is set"; exit 0
    fi ;;
  propose|off) ;;
  *) echo "$P ADVISORY could not read skills.workshop.autonomous.mode (${cur:0:80}) — left unchanged"; exit 0 ;;
esac

if [ -z "$before" ]; then
  echo "$P mode=$mode, review crons ADVISORY: cron list unreadable — not verified$note"; exit 0
fi
read -r total0 en0 <<EOF
$before
EOF
en1="$en0"; waited=0
# The reconciler flips the jobs on the hot reload; re-read now, then give it a bounded moment.
while :; do
  now="$(review_counts)" && [ -n "$now" ] && read -r _ en1 <<EOF
$now
EOF
  [ "$en1" -gt 0 ] && [ "$waited" -lt "$WAIT_S" ] || break
  sleep 5; waited=$((waited + 5))
done
line="$P mode=$mode, review crons disabled $((en0 - en1)) (already off $((total0 - en0)))$note"
[ "$en1" -gt 0 ] && line="$line ADVISORY $en1 still enabled after ${WAIT_S}s — the gateway disables them on its next config reload/start"
echo "$line"
exit 0
