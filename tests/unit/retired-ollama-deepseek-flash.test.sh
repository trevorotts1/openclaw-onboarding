#!/usr/bin/env bash
# R19: no retired Ollama deepseek-v4-flash id (retired 2026-09-25, HTTP 410) in shipped files;
# run-full-install resolves retired ids to the client's configured default model
# (never a prescribed successor) and corrects stored values to it; with no default
# configured it leaves them unresolved. DeepSeek Direct ids stay untouched. Hermetic.
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
# 2. run-full-install mapping + correction (functions extracted verbatim)
SCRIPT="$REPO/32-command-center-setup/scripts/run-full-install.sh"
for fn in _cc_is_retired_ollama_flash _cc_box_default_model _cc_live_model_id cc_env_has_nonempty cc_env_set_if_absent cc_env_get cc_env_correct_retired; do
  awk -v f="$fn" '$0 ~ "^"f"\\(\\) \\{"{p=1} p{print} p&&/^}/{exit}' "$SCRIPT" >> "$T/fns.sh"
done
export SKILL_DIR="$REPO/32-command-center-setup/scripts/.." DASHBOARD_DIR="$T"
. "$T/fns.sh"
chk(){ [ "$(_cc_live_model_id "$1")" = "$2" ] && ok "$1 -> $2" || bad "$1 -> $(_cc_live_model_id "$1") (want $2)"; }
# Doctrine (2026-10-13 ruling): a retired id resolves to the client's
# configured default model, never to a prescribed successor. With no
# default configured the resolution is empty; the caller must ask.
unset OC_CONFIG
chk ollama/deepseek-v4-flash:0731-cloud ''
chk ollama-cloud/deepseek-v4-flash:0731 ''
chk deepseek-v4-flash:cloud ''
chk ds/deepseek-v4-flash ds/deepseek-v4-flash
chk deepseek/deepseek-v4-flash deepseek/deepseek-v4-flash
chk ollama/deepseek-v4.1-flash:cloud ollama/deepseek-v4.1-flash:cloud
# With a configured default (fixture openclaw.json), retired ids resolve to it.
printf '{"agents":{"defaults":{"model":{"primary":"ollama/deepseek-v4.1-flash:cloud"}}}}\n' > "$T/openclaw.json"
export OC_CONFIG="$T/openclaw.json"
chk ollama/deepseek-v4-flash:0731-cloud ollama/deepseek-v4.1-flash:cloud
chk ollama-cloud/deepseek-v4-flash:0731 ollama/deepseek-v4.1-flash:cloud
chk deepseek-v4-flash:cloud ollama/deepseek-v4.1-flash:cloud
printf "QC_JUDGE_MODEL='deepseek-v4-flash:0731-cloud'\nOTHER='x'\n" > "$T/.env.local"
cc_env_correct_retired "$T/.env.local" QC_JUDGE_MODEL >/dev/null
[ "$(cc_env_get "$T/.env.local" QC_JUDGE_MODEL)" = "ollama/deepseek-v4.1-flash:cloud" ] && [ "$(cc_env_get "$T/.env.local" OTHER)" = "x" ] && ok "retired value corrected to the configured default, others kept" || bad "correction to default failed"
unset OC_CONFIG
# With no default configured, a retired stored value is left in place and
# reported unresolved, never silently replaced with a prescribed model.
printf "QC_JUDGE_MODEL='deepseek-v4-flash:0731-cloud'\nOTHER='x'\n" > "$T/.env.local"
out="$(cc_env_correct_retired "$T/.env.local" QC_JUDGE_MODEL)"
[ "$(cc_env_get "$T/.env.local" QC_JUDGE_MODEL)" = "deepseek-v4-flash:0731-cloud" ] && [ "${out#retired-unresolved}" != "$out" ] && ok "retired value without a default left unresolved, never substituted" || bad "unresolved handling failed"
printf "QC_JUDGE_MODEL='glm-5.2:cloud'\n" > "$T/.env.local"; cc_env_correct_retired "$T/.env.local" QC_JUDGE_MODEL >/dev/null
[ "$(cc_env_get "$T/.env.local" QC_JUDGE_MODEL)" = "glm-5.2:cloud" ] && ok "live value untouched" || bad "live value changed"
exit $fail
