#!/usr/bin/env bash
# R19: no retired Ollama deepseek-v4-flash id (retired 2026-09-25, HTTP 410) in shipped files;
# run-full-install resolves a retired id to THIS box's configured default model (never a
# prescribed successor); with no usable configured default the retired id resolves to
# nothing and env values are left untouched as retired-unresolved. DeepSeek Direct ids
# stay untouched. Hermetic.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
cd "$REPO"
# 1. repo-wide guard (history files and the deprecation table itself are exempt)
hits="$(git grep -nIE '(ollama(-cloud)?/|_oll\}/)deepseek-v4-flash|deepseek-v4-flash(:0731|:cloud)' -- . \
  ':!CHANGELOG.md' ':!*/CHANGELOG.md' ':!QUALITY-CONTROL' ':!evidence' ':!ledgers' ':!scripts/deprecated-models.json' \
  ':!tests/unit/retired-ollama-deepseek-flash.test.sh' 2>/dev/null | grep -v 'deepseek/deepseek-v4-flash' || true)"
[ -z "$hits" ] && ok "no retired Ollama deepseek-v4-flash id in shipped files" || { bad "retired ids found:"; echo "$hits" | head -20; }
python3 - <<'PY' && ok "deprecated-models.json replacements are not themselves retired" || bad "replacement retired"
import json,re,sys
d=json.load(open('scripts/deprecated-models.json'))['deprecated']
retired=[x['model'] for x in d if 'deepseek-v4-flash' in x['model']]
assert retired
assert all('v4-flash' not in x['replacement'] for x in d), "a replacement is a retired id"
PY
# 2. run-full-install resolution + correction (functions extracted verbatim)
SCRIPT="$REPO/32-command-center-setup/scripts/run-full-install.sh"
for fn in _cc_is_retired_ollama_flash _cc_box_default_model _cc_live_model_id cc_env_has_nonempty cc_env_set_if_absent cc_env_get cc_env_correct_retired; do
  awk -v f="$fn" '$0 ~ "^"f"\\(\\) \\{"{p=1} p{print} p&&/^}/{exit}' "$SCRIPT" >> "$T/fns.sh"
done
export SKILL_DIR="$REPO/32-command-center-setup/scripts/.." DASHBOARD_DIR="$T"
. "$T/fns.sh"
chk(){ local got; got="$(_cc_live_model_id "$1")"; [ "$got" = "$2" ] && ok "$1 -> ${2:-(empty)}" || bad "$1 -> ${got:-(empty)} (want ${2:-(empty)})"; }
# Phase A: the box configures NO default model -> a retired id resolves to
# nothing (no successor is prescribed by name); live ids pass through.
export OC_CONFIG="$T/absent-openclaw.json"
chk ollama/deepseek-v4-flash:0731-cloud ""
chk ollama-cloud/deepseek-v4-flash:0731 ""
chk deepseek-v4-flash:cloud ""
chk ds/deepseek-v4-flash ds/deepseek-v4-flash
chk deepseek/deepseek-v4-flash deepseek/deepseek-v4-flash
chk ollama/deepseek-v4.1-flash:cloud ollama/deepseek-v4.1-flash:cloud
printf "QC_JUDGE_MODEL='deepseek-v4-flash:0731-cloud'\nOTHER='x'\n" > "$T/.env.local"
out="$(cc_env_correct_retired "$T/.env.local" QC_JUDGE_MODEL)"
[ "$(cc_env_get "$T/.env.local" QC_JUDGE_MODEL)" = "deepseek-v4-flash:0731-cloud" ] && [ "$(cc_env_get "$T/.env.local" OTHER)" = "x" ] && [ "$out" = "retired-unresolved(deepseek-v4-flash:0731-cloud)" ] && ok "no configured default: retired value left untouched as retired-unresolved, others kept" || bad "unresolved handling failed (out=$out)"
# Phase B: the box configures a default model (object form) -> every retired
# form resolves to THAT default, whatever provider prefix the retired id had.
printf '%s' '{"agents":{"defaults":{"model":{"primary":"ollama/deepseek-v4.1-flash:cloud"}}}}' > "$T/openclaw.json"
export OC_CONFIG="$T/openclaw.json"
chk ollama/deepseek-v4-flash:0731-cloud ollama/deepseek-v4.1-flash:cloud
chk ollama-cloud/deepseek-v4-flash:0731 ollama/deepseek-v4.1-flash:cloud
chk deepseek-v4-flash:cloud ollama/deepseek-v4.1-flash:cloud
printf "QC_JUDGE_MODEL='deepseek-v4-flash:0731-cloud'\nOTHER='x'\n" > "$T/.env.local"
cc_env_correct_retired "$T/.env.local" QC_JUDGE_MODEL >/dev/null
[ "$(cc_env_get "$T/.env.local" QC_JUDGE_MODEL)" = "ollama/deepseek-v4.1-flash:cloud" ] && [ "$(cc_env_get "$T/.env.local" OTHER)" = "x" ] && ok "existing retired value corrected to the configured default, others kept" || bad "correction failed"
# Phase C: plain-string form of agents.defaults.model is honored the same way.
printf '%s' '{"agents":{"defaults":{"model":"ollama/deepseek-v4.1-flash:cloud"}}}' > "$T/openclaw.json"
chk ollama/deepseek-v4-flash:0731-cloud ollama/deepseek-v4.1-flash:cloud
# Phase D: a configured default that is itself retired is not usable.
printf '%s' '{"agents":{"defaults":{"model":{"primary":"ollama/deepseek-v4-flash:cloud"}}}}' > "$T/openclaw.json"
chk ollama/deepseek-v4-flash:0731-cloud ""
printf "QC_JUDGE_MODEL='glm-5.2:cloud'\n" > "$T/.env.local"; cc_env_correct_retired "$T/.env.local" QC_JUDGE_MODEL >/dev/null
[ "$(cc_env_get "$T/.env.local" QC_JUDGE_MODEL)" = "glm-5.2:cloud" ] && ok "live value untouched" || bad "live value changed"
exit $fail
