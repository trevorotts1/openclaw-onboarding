#!/usr/bin/env bash
# R18: oc_fill_from_env_stores reads ~/.openclaw/.env and openclaw.json env.vars, not only secrets/.env.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
run(){ HOME="$1" bash -c 'set -u; source "$2" 2>/dev/null; KIE_API_KEY=""; oc_fill_from_env_stores KIE_API_KEY; [ "$KIE_API_KEY" = "$3" ] && echo yes' _ "$1" "$REPO/lib-shared.sh" "$2"; }
mkdir -p "$T/a/.openclaw/secrets"; echo "KIE_API_KEY='k-dotenv'" > "$T/a/.openclaw/.env"
[ "$(run "$T/a" k-dotenv)" = yes ] && ok "reads ~/.openclaw/.env" || bad ".env"
mkdir -p "$T/b/.openclaw"; echo '{"env":{"vars":{"KIE_API_KEY":"k-json"}}}' > "$T/b/.openclaw/openclaw.json"
[ "$(run "$T/b" k-json)" = yes ] && ok "reads openclaw.json env.vars" || bad "json"
mkdir -p "$T/c/.openclaw/secrets"; echo "KIE_API_KEY=k-sec" > "$T/c/.openclaw/secrets/.env"
[ "$(run "$T/c" k-sec)" = yes ] && ok "reads secrets/.env" || bad "secrets"
mkdir -p "$T/d/.openclaw"; [ "$(run "$T/d" "")" != yes ] || true; out="$(HOME="$T/d" bash -c 'source "$1" 2>/dev/null; KIE_API_KEY=""; oc_fill_from_env_stores KIE_API_KEY; echo "[${KIE_API_KEY}]"' _ "$REPO/lib-shared.sh")"
[ "$out" = "[]" ] && ok "absent everywhere stays empty" || bad "absent: $out"
exit $fail
