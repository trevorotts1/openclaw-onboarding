#!/usr/bin/env bash
# test-install-weekly-cron.sh - proves scripts/install-weekly-cron.sh against a
# fake `openclaw` (tests/fake-openclaw.py). No gateway, no real cron store.
#
# Cases: model discovery picks Ollama Cloud primary + OpenRouter fallback;
# refuses (exit 4) when a model id is missing or an Anthropic id is forced;
# refuses (exit 5) when the command line lacks a flag; dry run changes nothing;
# apply creates exactly one job with the right shape; re-apply is a no-op
# (idempotent); a drifted job is edited in place, never duplicated; duplicates
# are reported (exit 1) and never deleted; a gateway failure is exit 2.
#
# Usage: bash tests/test-install-weekly-cron.sh   (exit 0 = every case passed)

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
INST="$HERE/../scripts/install-weekly-cron.sh"
ROOT="$(mktemp -d 2>/dev/null || mktemp -d -t pointercrontest)"
trap 'rm -rf "$ROOT"' EXIT
export OPENCLAW_MASTER_FILES_DIR="$ROOT/mf" OPENCLAW_ROOT_DIR="$ROOT/oc" OPENCLAW_WORKSPACE="$ROOT/ws"
mkdir -p "$ROOT/bin"
printf '#!/bin/sh\nexec python3 "%s/fake-openclaw.py" "$@"\n' "$HERE" > "$ROOT/bin/openclaw"
chmod +x "$ROOT/bin/openclaw"
export OPENCLAW_BIN="$ROOT/bin/openclaw"
export FAKE_JOBS_FILE="$ROOT/jobs.json" FAKE_MODELS_FILE="$ROOT/models.json" FAKE_CALLS_FILE="$ROOT/calls.log"
PASS=0 FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  ok   $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL $*"; }

reset() { echo '[]' > "$FAKE_JOBS_FILE"; : > "$FAKE_CALLS_FILE"; unset FAKE_DROP_FLAG FAKE_MODELS_FAIL; }
models() { # models <json>
  printf '%s\n' "$1" > "$FAKE_MODELS_FILE"
}
GOOD_MODELS='{"models":[{"key":"deepseek/deepseek-flash"},{"key":"ollama/deepseek-v4.1-flash:cloud"},{"key":"openrouter/deepseek/deepseek-v4.1-flash"},{"key":"9router/ollama/deepseek-v4.1-flash"},{"key":"anthropic/claude-opus-4"}]}'

expect() { # expect <name> <want-exit> <needle> -- args
  local name="$1" want="$2" needle="$3"; shift 4
  local out rc; out="$(bash "$INST" "$@" 2>&1)"; rc=$?
  if [ "$rc" != "$want" ]; then bad "$name (exit $rc, wanted $want)"; printf '%s\n' "$out" | sed 's/^/       | /' | head -20; return; fi
  if [ -n "$needle" ] && ! printf '%s\n' "$out" | grep -qF -- "$needle"; then bad "$name (lacks: $needle)"; printf '%s\n' "$out" | sed 's/^/       | /' | head -20; return; fi
  ok "$name (exit $rc)"
}
job_field() { # job_field count | job_field <dotted.path> (from the first matching job)
  python3 - "$FAKE_JOBS_FILE" "$1" <<'PY'
import json, sys
jobs = [x for x in json.load(open(sys.argv[1])) if x.get("name") == "pointer-references-weekly"]
if sys.argv[2] == "count":
    print(len(jobs)); sys.exit(0)
v = jobs[0]
for k in sys.argv[2].split("."):
    v = v[k]
print(v)
PY
}

echo "install-weekly-cron battery"

reset; models "$GOOD_MODELS"
expect "dry run plans an add" 0 "would ADD the job" -- --dry-run
[ "$(job_field count)" = "0" ] && ok "dry run created nothing" || bad "dry run created a job"
expect "discovers the Ollama Cloud primary" 0 "primary model:  ollama/deepseek-v4.1-flash:cloud" -- --dry-run
expect "discovers the OpenRouter fallback" 0 "fallback model: openrouter/deepseek/deepseek-v4.1-flash" -- --dry-run

expect "apply creates and reads back" 0 "PASS [install-weekly-cron.sh]: read-back confirms" -- --apply
[ "$(job_field count)" = "1" ] && ok "exactly one job" || bad "job count $(job_field count)"
[ "$(job_field payload.model)" = "ollama/deepseek-v4.1-flash:cloud" ] && ok "primary model stored" || bad "primary model wrong"
[ "$(job_field payload.fallbacks)" = "['openrouter/deepseek/deepseek-v4.1-flash']" ] && ok "fallback stored" || bad "fallbacks wrong"
[ "$(job_field payload.thinking)" = "high" ] && ok "thinking high" || bad "thinking wrong"
[ "$(job_field sessionTarget)" = "isolated" ] && ok "isolated session" || bad "session wrong"
[ "$(job_field delivery.mode)" = "none" ] && ok "quiet delivery (none)" || bad "delivery wrong"
[ "$(job_field schedule.expr)" = "30 5 * * 0" ] && ok "weekly schedule stored exactly" || bad "schedule wrong: $(job_field schedule.expr)"
job_field payload.message | grep -q "pointer-references-full.md" && ok "message names the playbook" || bad "message lacks playbook path"
job_field payload.message | grep -q "{{" && bad "message has an unfilled placeholder" || ok "message placeholders all filled"

: > "$FAKE_CALLS_FILE"
expect "re-apply is a no-op" 0 "job is current; nothing changed" -- --apply
grep -qE '"add", "--name"|"edit", "job-' "$FAKE_CALLS_FILE" && bad "re-apply called add/edit" || ok "re-apply made no add or edit call"
expect "check passes on a current job" 0 "PASS [install-weekly-cron.sh]: exactly one job and it matches" -- --check

python3 -c "import json;p='$FAKE_JOBS_FILE';j=json.load(open(p));j[0]['payload']['model']='ollama/other:cloud';j[0]['payload']['thinking']='low';json.dump(j,open(p,'w'))"
expect "check fails on a drifted job" 1 "job missing or drifted" -- --check
expect "apply edits the drifted job in place" 0 "edited job job-1 in place (model,thinking)" -- --apply
[ "$(job_field count)" = "1" ] && ok "still exactly one job after edit" || bad "edit duplicated the job"

python3 -c "import json;p='$FAKE_JOBS_FILE';j=json.load(open(p));k=dict(j[0]);k['id']='job-2';j.append(k);json.dump(j,open(p,'w'))"
expect "duplicates are reported, never deleted" 1 "2 jobs named 'pointer-references-weekly'" -- --apply
[ "$(job_field count)" = "2" ] && ok "no job was deleted" || bad "a job was deleted"

reset; models '{"models":[{"key":"ollama/deepseek-v4.1-flash:cloud"}]}'
expect "missing OpenRouter fallback refuses" 4 "MISSING_FALLBACK" -- --apply
[ "$(job_field count)" = "0" ] && ok "refusal created nothing" || bad "refusal created a job"

reset; models '{"models":[{"key":"openrouter/deepseek/deepseek-v4.1-flash"}]}'
expect "missing Ollama primary refuses" 4 "MISSING_PRIMARY" -- --apply

reset; models '{"models":[{"provider":"ollama-cloud","id":"deepseek-v4.1-flash:cloud"},{"provider":"openrouter","id":"deepseek/deepseek-v4.1-flash"}]}'
expect "provider+id shape and ollama-cloud provider are discovered" 0 "primary model:  ollama-cloud/deepseek-v4.1-flash:cloud" -- --dry-run

reset; models '{"models":[{"key":"ollama/deepseek-v4.1-flash:cloud"},{"key":"ollama-cloud/deepseek-v4.1-flash:cloud"},{"key":"openrouter/deepseek/deepseek-v4.1-flash"}]}'
expect "ambiguous primary refuses" 4 "AMBIGUOUS_PRIMARY" -- --apply
expect "explicit --primary resolves the ambiguity" 0 "primary model:  ollama-cloud/deepseek-v4.1-flash:cloud" -- --dry-run --primary ollama-cloud/deepseek-v4.1-flash:cloud

reset; models "$GOOD_MODELS"
expect "forcing an Anthropic model refuses" 4 "REFUSED_PRIMARY" -- --apply --primary anthropic/claude-opus-4
expect "forcing an id not on the list refuses" 4 "not on this box's configured model list" -- --apply --fallback openrouter/deepseek/made-up

reset; models "$GOOD_MODELS"; export FAKE_DROP_FLAG=--fallbacks
expect "a command line without --fallbacks refuses" 5 "does not offer: --fallbacks" -- --apply
unset FAKE_DROP_FLAG

reset; models "$GOOD_MODELS"; export FAKE_MODELS_FAIL=1
expect "gateway failure is a tooling error" 2 "TOOLING ERROR" -- --apply
unset FAKE_MODELS_FAIL

expect "unknown argument is a usage error" 3 "USAGE" -- --bogus

echo "install-weekly-cron battery: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
