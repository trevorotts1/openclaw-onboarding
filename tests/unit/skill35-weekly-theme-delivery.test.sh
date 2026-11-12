#!/usr/bin/env bash
# Skill 35 register-weekly-cron.sh: two same-named entries on different agents collapse to ONE,
# and the new entry declares delivery explicitly (--no-deliver), never --channel/--to/--announce.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
cat > "$T/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
echo "$@" >> "$STUB_LOG"
case "$1 $2" in
  "cron list") cat "$STUB_LIST" ;;
  "cron add") if [ "${3:-}" = "--help" ]; then echo "  --no-deliver"; else echo "skill35-weekly-theme 0 8 * * 6 main active" > "$STUB_LIST"; fi ;;
esac
exit 0
STUB
chmod +x "$T/bin/openclaw"
export STUB_LOG="$T/log" STUB_LIST="$T/list" HOME="$T/home"; mkdir -p "$HOME"
printf 'skill35-weekly-theme 0 8 * * 6 main active\nskill35-weekly-theme 0 8 * * 6 dept-master-orchestrator active\n' > "$STUB_LIST"
PATH="$T/bin:$PATH" bash "$ROOT/35-social-media-planner/scripts/register-weekly-cron.sh" >/dev/null 2>&1; rc=$?
fail=0
chk() { if [ "$2" = "$3" ]; then echo "  ok  - $1"; else echo "  FAIL- $1 (got $2, want $3)"; fail=$((fail+1)); fi; }
chk "script exits 0" "$rc" 0
chk "old same-name entries deleted once" "$(grep -c 'cron delete --name skill35-weekly-theme' "$STUB_LOG")" 1
chk "exactly one cron add" "$(grep -c '^cron add --name' "$STUB_LOG")" 1
chk "add declares --no-deliver" "$(grep '^cron add --name' "$STUB_LOG" | grep -c -- '--no-deliver')" 1
chk "add has no --channel/--to/--announce" "$(grep '^cron add --name' "$STUB_LOG" | grep -cE -- '--channel|--to |--announce')" 0
echo "== skill35-weekly-theme-delivery: $((5-fail)) passed, $fail failed =="
[ "$fail" -eq 0 ]
