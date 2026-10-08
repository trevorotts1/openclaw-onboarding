#!/usr/bin/env bash
# test-wire.sh - proves wire.sh against a throwaway workspace: blocks land once
# with the master-files path resolved, a re-run is byte-identical (idempotent),
# an existing index is never overwritten, a stale block is healed in place,
# other content is preserved, backups are taken only on change, and the
# resulting workspace passes the pointer audit.
# Usage: bash tests/test-wire.sh   (exit 0 = every case passed)

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
ROOT="$(mktemp -d 2>/dev/null || mktemp -d -t pointerwiretest)"
trap 'rm -rf "$ROOT"' EXIT
export OPENCLAW_WORKSPACE="$ROOT/ws" OPENCLAW_MASTER_FILES_DIR="$ROOT/mf" \
       OPENCLAW_BACKUP_DIR="$ROOT/bk" OPENCLAW_ROOT_DIR="$ROOT/oc"
PASS=0 FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  ok   $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL $*"; }

echo "wire.sh battery"
mkdir -p "$ROOT/ws"
printf '# Agent rules\n\n## Hard rules\n- Never share credentials.\n' > "$ROOT/ws/AGENTS.md"
printf '# Memory\n\n- The owner prefers short answers.\n' > "$ROOT/ws/MEMORY.md"

bash "$SKILL/wire.sh" --no-cron >/dev/null 2>&1 && ok "first run exits 0" || bad "first run failed"
[ "$(grep -c 'BEGIN skill:70-lean-core-file-system:agents' "$ROOT/ws/AGENTS.md")" = "1" ] && ok "AGENTS.md block present once" || bad "AGENTS.md block count wrong"
[ "$(grep -c 'BEGIN skill:70-lean-core-file-system:memory' "$ROOT/ws/MEMORY.md")" = "1" ] && ok "MEMORY.md block present once" || bad "MEMORY.md block count wrong"
grep -q "$ROOT/mf/70-lean-core-file-system/lean-core-file-system-full.md" "$ROOT/ws/AGENTS.md" && ok "pointer path resolved to the absolute master files path" || bad "pointer path not resolved"
grep -q 'MASTER_FILES_FOLDER' "$ROOT/ws/AGENTS.md" "$ROOT/ws/MEMORY.md" && bad "placeholder left unresolved" || ok "no placeholder left"
grep -q 'Never share credentials' "$ROOT/ws/AGENTS.md" && grep -q 'short answers' "$ROOT/ws/MEMORY.md" && ok "existing content preserved" || bad "existing content lost"
grep -qF '<!-- skill:70-lean-core-file-system:core-update-applied -->' "$ROOT/ws/AGENTS.md" && ok "sentinel stamped" || bad "sentinel missing"
[ -f "$ROOT/mf/70-lean-core-file-system/lean-core-file-system-full.md" ] && ok "playbook installed where the pointer says" || bad "playbook not installed"
[ -f "$ROOT/mf/playbooks/README.md" ] && ok "master index created" || bad "master index missing"
nb="$(find "$ROOT/bk" -type f | wc -l | tr -d ' ')"; [ "$nb" -ge 2 ] && ok "backups taken before the first change ($nb files)" || bad "no backups taken"

a1="$(cksum < "$ROOT/ws/AGENTS.md")"; m1="$(cksum < "$ROOT/ws/MEMORY.md")"
bash "$SKILL/wire.sh" --no-cron >/dev/null 2>&1
[ "$a1" = "$(cksum < "$ROOT/ws/AGENTS.md")" ] && [ "$m1" = "$(cksum < "$ROOT/ws/MEMORY.md")" ] && ok "re-run is byte-identical" || bad "re-run changed a file"
nb2="$(find "$ROOT/bk" -type f | wc -l | tr -d ' ')"; [ "$nb2" = "$nb" ] && ok "no backup on an unchanged re-run" || bad "backup taken on a no-op run"

printf -- '- [My system](my-system.md) - operator entry\n' >> "$ROOT/mf/playbooks/README.md"
bash "$SKILL/wire.sh" --no-cron >/dev/null 2>&1
grep -q 'My system' "$ROOT/mf/playbooks/README.md" && ok "existing index never overwritten" || bad "index overwritten"

python3 - "$ROOT/ws/AGENTS.md" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace("governs keeping", "OLD STALE WORDING governs keeping")
open(p, "w").write(s)
PY
bash "$SKILL/wire.sh" --no-cron >/dev/null 2>&1
grep -q 'OLD STALE WORDING' "$ROOT/ws/AGENTS.md" && bad "stale block not healed" || ok "stale block healed in place"
[ "$(grep -c 'BEGIN skill:70-lean-core-file-system:agents' "$ROOT/ws/AGENTS.md")" = "1" ] && ok "still one block after healing" || bad "healing duplicated the block"

rm -f "$ROOT/mf/playbooks/README.md.bak"; sed -i.bak '/My system/d' "$ROOT/mf/playbooks/README.md"; rm -f "$ROOT/mf/playbooks/README.md.bak"
out="$(bash "$SKILL/scripts/pointer-audit.sh" --dry-run 2>&1)"; rc=$?
[ "$rc" = "0" ] && ok "wired workspace passes the audit (exit 0)" || { bad "audit of wired workspace exit $rc"; printf '%s\n' "$out" | sed -n '/## Findings/,/## Candidate/p' | sed 's/^/       | /'; }

# workspace resolution follows the OpenClaw 2026.9 agents.entries roster
mkdir -p "$ROOT/oc2"
printf '{"agents":{"defaults":{"workspace":"/wrong"},"entries":{"main":{"workspace":"/right"}}}}' > "$ROOT/oc2/openclaw.json"
got="$(env -u OPENCLAW_WORKSPACE OPENCLAW_ROOT_DIR="$ROOT/oc2" bash -c '. "$1/scripts/lib-paths.sh"; pr_workspace' _ "$SKILL")"
[ "$got" = "/right" ] && ok "workspace resolves from agents.entries.main" || bad "workspace resolved to '$got'"

# with the cron step: a refused job makes wire.sh exit non-zero (so the next
# fleet update retries) AFTER the core files are wired; a provable job exits 0
mkdir -p "$ROOT/bin"
printf '#!/bin/sh\nexec python3 "%s/fake-openclaw.py" "$@"\n' "$HERE" > "$ROOT/bin/openclaw"; chmod +x "$ROOT/bin/openclaw"
export OPENCLAW_BIN="$ROOT/bin/openclaw" FAKE_JOBS_FILE="$ROOT/jobs.json" FAKE_MODELS_FILE="$ROOT/models.json"
echo '[]' > "$FAKE_JOBS_FILE"
echo '{"models":[{"key":"openrouter/deepseek/deepseek-v4.1-flash"}]}' > "$FAKE_MODELS_FILE"
rm -rf "$ROOT/ws3"; mkdir -p "$ROOT/ws3"; echo '# rules' > "$ROOT/ws3/AGENTS.md"
OPENCLAW_WORKSPACE="$ROOT/ws3" bash "$SKILL/wire.sh" --idempotent >/dev/null 2>&1; rc=$?
[ "$rc" = "4" ] && grep -q 'BEGIN skill:70-lean-core-file-system:agents' "$ROOT/ws3/AGENTS.md" \
  && ok "refused cron job: wire.sh exits 4 after wiring the core files (retried next update)" || bad "refused cron path (exit $rc)"
echo '{"models":[{"key":"ollama/deepseek-v4.1-flash:cloud"},{"key":"openrouter/deepseek/deepseek-v4.1-flash"}]}' > "$FAKE_MODELS_FILE"
OPENCLAW_WORKSPACE="$ROOT/ws3" bash "$SKILL/wire.sh" --idempotent >/dev/null 2>&1; rc=$?
[ "$rc" = "0" ] && [ "$(grep -c lean-core-file-system-weekly "$FAKE_JOBS_FILE")" = "1" ] && ok "provable models: wire.sh creates the job and exits 0" || bad "cron path (exit $rc)"

# UPF002/U3: a client box with its own default model (no DeepSeek pair) wires its cron in a sandbox HOME
echo '[]' > "$FAKE_JOBS_FILE"
echo '{"models":[{"key":"agnes/agnes-2.5","tags":["default"]}]}' > "$FAKE_MODELS_FILE"
mkdir -p "$ROOT/home"
HOME="$ROOT/home" OPENCLAW_WORKSPACE="$ROOT/ws3" bash "$SKILL/wire.sh" --idempotent >/dev/null 2>&1; rc=$?
[ "$rc" = "0" ] && [ "$(grep -c lean-core-file-system-weekly "$FAKE_JOBS_FILE")" = "1" ] && ok "non-DeepSeek box: wire.sh wires its weekly cron and exits 0" || bad "non-DeepSeek cron path (exit $rc)"

echo "wire.sh battery: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
