#!/usr/bin/env bash
# R17: prune keeps openclaw.json, .last-good, 3 newest other copies; deletes the rest. Hermetic.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
echo '{}' > "$T/openclaw.json"; echo '{}' > "$T/openclaw.json.last-good"; echo l > "$T/openclaw.json.lock"
i=0; for kind in bak-routing-fix bak-operator-tg clobbered bak-fleet bak.xet; do for n in 1 2 3 4; do
  i=$((i+1)); f="$T/openclaw.json.$kind-$n"; echo x > "$f"; touch -t "2026010100$(printf %02d $i)" "$f"; done; done
bash "$REPO/scripts/prune-openclaw-json-backups.sh" "$T" >/dev/null
left=$(ls "$T"/openclaw.json.* | grep -vc 'last-good\|lock')
[ "$left" -eq 3 ] && ok "3 newest copies kept ($left)" || bad "kept $left"
[ -f "$T/openclaw.json" ] && [ -f "$T/openclaw.json.last-good" ] && [ -f "$T/openclaw.json.lock" ] && ok "config, last-good, lock untouched" || bad "protected file removed"
[ -f "$T/openclaw.json.bak.xet-4" ] && ok "newest copy survived" || bad "newest deleted"
exit $fail
