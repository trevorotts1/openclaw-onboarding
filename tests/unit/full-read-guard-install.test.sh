#!/usr/bin/env bash
# full-read-guard installer: scripts/install-full-read-guard.sh and its wiring.
# Hermetic: every box is a mktemp fixture (HOME is redirected too); no real ~/.openclaw is touched.
# QC runs this. Override hook (to prove the test can fail): FRG_INSTALLER=<path to a mutated copy>.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
INST="${FRG_INSTALLER:-$REPO/scripts/install-full-read-guard.sh}"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
jq_py(){ python3 -I -c "import json,sys;d=json.load(open(sys.argv[1]));print(eval(sys.argv[2]))" "$@"; }

# fixture plugin source (stands in for the folder the plugin builder ships)
SRC="$T/stage"; mkdir -p "$SRC/full-read-guard/dist"
echo '{"id":"full-read-guard","version":"1.0.0","main":"./dist/index.js"}' > "$SRC/full-read-guard/openclaw.plugin.json"
echo 'export default {}' > "$SRC/full-read-guard/dist/index.js"

mkbox(){ # <root> [allow-json]
  rm -rf "$1"; mkdir -p "$1"
  printf '{"agents":{"keep":"me"},"plugins":{"entries":{"other":{"enabled":true}}%s}}\n' "${2:+,\"allow\":$2}" > "$1/openclaw.json"
}
run(){ # <root> args... ; HOME deliberately different from root
  local root="$1"; shift
  env -i PATH="$PATH" HOME="$T/home-elsewhere" bash "$INST" --root "$root" "$@" 2>&1
}
mkdir -p "$T/home-elsewhere"

bash -n "$INST" && ok "installer parses" || { bad "installer has a syntax error"; exit 1; }

# 1. fresh install on a root that is NOT $HOME/.openclaw (Docker VPS / Contabo layouts)
for layout in data/.openclaw home/node/.openclaw; do
  R="$T/$layout"; mkbox "$R"
  out="$(run "$R" --install --source "$SRC")"
  [ -f "$R/extensions/full-read-guard/openclaw.plugin.json" ] && ok "[$layout] plugin copied into the resolved root" || bad "[$layout] plugin not in resolved root: $out"
  [ ! -e "$T/home-elsewhere/.openclaw" ] && ok "[$layout] nothing written under HOME/.openclaw" || bad "[$layout] wrote under HOME/.openclaw"
  [ "$(jq_py "$R/openclaw.json" "d['plugins']['entries']['full-read-guard']['enabled']")" = "True" ] && ok "[$layout] enabled" || bad "[$layout] not enabled"
  [ "$(jq_py "$R/openclaw.json" "'$R/extensions' in d['plugins']['load']['paths']")" = "True" ] && ok "[$layout] load path is the resolved root" || bad "[$layout] load path wrong"
  [ "$(jq_py "$R/openclaw.json" "d['plugins']['entries']['full-read-guard']['config']['mode']")" = "enforce" ] && ok "[$layout] default mode enforce" || bad "[$layout] mode"
  [ "$(jq_py "$R/openclaw.json" "'hooks' in d['plugins']['entries']['full-read-guard']")" = "False" ] && ok "[$layout] no hooks key" || bad "[$layout] hooks key written"
  [ "$(jq_py "$R/openclaw.json" "d['agents']['keep']+str(d['plugins']['entries']['other']['enabled'])")" = "meTrue" ] && ok "[$layout] unrelated config untouched" || bad "[$layout] clobbered other config"
  echo "$out" | grep -q '^full-read-guard: installed 1.0.0' && ok "[$layout] logs installed 1.0.0" || bad "[$layout] log line: $out"
  ls "$R"/openclaw.json.bak* >/dev/null 2>&1 && bad "[$layout] created a backup file" || ok "[$layout] no backup file created"
  [ "$(run "$R" --verify | cut -c1-24)" = "full-read-guard: PASS 1." ] && ok "[$layout] verify PASS" || bad "[$layout] verify: $(run "$R" --verify)"
done

# 2. idempotent: second run changes nothing, no nested copy
R="$T/idem"; mkbox "$R"; run "$R" --install --source "$SRC" >/dev/null
h1="$(shasum "$R/openclaw.json" | cut -d' ' -f1)"
out="$(run "$R" --install --source "$SRC")"
h2="$(shasum "$R/openclaw.json" | cut -d' ' -f1)"
[ "$h1" = "$h2" ] && ok "re-run leaves openclaw.json byte-identical" || bad "re-run changed openclaw.json"
[ ! -d "$R/extensions/full-read-guard/full-read-guard" ] && ok "re-run does not nest a copy" || bad "nested copy created"
echo "$out" | grep -q 'already 1.0.0' && ok "re-run logs already 1.0.0" || bad "re-run log: $out"
[ "$(jq_py "$R/openclaw.json" "d['plugins']['load']['paths'].count('$R/extensions')")" = "1" ] && ok "load path not duplicated" || bad "load path duplicated"

# 3. operator's own values win
R="$T/opval"; mkbox "$R"
python3 -I - "$R/openclaw.json" <<'PY'
import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["plugins"]["entries"]["full-read-guard"]={"enabled":False,"config":{"mode":"audit"}}; json.dump(d,open(p,"w"))
PY
run "$R" --install --source "$SRC" >/dev/null
[ "$(jq_py "$R/openclaw.json" "d['plugins']['entries']['full-read-guard']['config']['mode']")" = "audit" ] && ok "operator mode audit preserved" || bad "operator mode overwritten"

# 4. plugins.allow present -> extended ; absent -> NOT created
R="$T/allow-yes"; mkbox "$R" '["other"]'; run "$R" --install --source "$SRC" >/dev/null
[ "$(jq_py "$R/openclaw.json" "d['plugins']['allow']")" = "['other', 'full-read-guard']" ] && ok "existing allowlist extended" || bad "allowlist not extended"
R="$T/allow-no"; mkbox "$R"; run "$R" --install --source "$SRC" >/dev/null
[ "$(jq_py "$R/openclaw.json" "'allow' in d['plugins']")" = "False" ] && ok "no allowlist created where none existed" || bad "allowlist created"

# 5. apply-fleet-standards rewrites the allowlist after hook A -> repair-config + verify
R="$T/allow-drift"; mkbox "$R" '["other"]'; run "$R" --install --source "$SRC" >/dev/null
python3 -I - "$R/openclaw.json" <<'PY'
import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["plugins"]["allow"]=["other"]; json.dump(d,open(p,"w"))
PY
run "$R" --verify | grep -q '^full-read-guard: FAIL config missing allow' && ok "verify FAILs when allowlist dropped the plugin" || bad "verify did not catch dropped allowlist"
run "$R" --repair-config >/dev/null
run "$R" --verify | grep -q '^full-read-guard: PASS' && ok "repair-config restores PASS" || bad "repair did not restore"

# 6. missing plugin folder -> clear no-op, exit 0, config untouched
R="$T/nofolder"; mkbox "$R"; h1="$(shasum "$R/openclaw.json" | cut -d' ' -f1)"
mkdir -p "$T/emptysrc"
out="$(run "$R" --install --source "$T/emptysrc")"; rc=$?
[ "$rc" = 0 ] && ok "missing folder: exit 0" || bad "missing folder: rc=$rc"
echo "$out" | grep -q '^full-read-guard: no-op, extensions/full-read-guard not found' && ok "missing folder: clear log line" || bad "missing folder log: $out"
[ "$h1" = "$(shasum "$R/openclaw.json" | cut -d' ' -f1)" ] && [ ! -d "$R/extensions/full-read-guard" ] && ok "missing folder: nothing written" || bad "missing folder wrote something"
run "$R" --verify | grep -q '^full-read-guard: SKIP' && ok "verify SKIPs (exit 0) when not shipped" || bad "verify on not-shipped"

# 7. invalid config after edit -> original restored (fake CLI that rejects any config naming the plugin)
R="$T/rollback"; mkbox "$R"; h1="$(shasum "$R/openclaw.json" | cut -d' ' -f1)"
mkdir -p "$T/fakebin"; cat > "$T/fakebin/openclaw" <<'SH'
#!/bin/sh
[ "$1 $2" = "config validate" ] || exit 0
grep -q full-read-guard "$OPENCLAW_CONFIG_PATH" && exit 1
exit 0
SH
chmod +x "$T/fakebin/openclaw"
out="$(env -i PATH="$T/fakebin:$PATH" HOME="$T/home-elsewhere" bash "$INST" --install --root "$R" --source "$SRC" 2>&1)"; rc=$?
[ "$rc" = 0 ] && ok "validate failure: roll not failed (exit 0)" || bad "validate failure rc=$rc"
[ "$h1" = "$(shasum "$R/openclaw.json" | cut -d' ' -f1)" ] && ok "validate failure: original bytes restored" || bad "config not restored"
echo "$out" | grep -q 'config-restored-after-validate-failure' && ok "validate failure: logged" || bad "no restore log: $out"
ls "$R"/openclaw.json.* >/dev/null 2>&1 && bad "leftover temp/backup file" || ok "validate failure: no leftover files"

# 8. root resolution order: OPENCLAW_ROOT env beats HOME; --root beats env
R="$T/envroot"; mkbox "$R"
env -i PATH="$PATH" HOME="$T/home-elsewhere" OPENCLAW_ROOT="$R" bash "$INST" --install --source "$SRC" >/dev/null 2>&1
[ -f "$R/extensions/full-read-guard/openclaw.plugin.json" ] && ok "OPENCLAW_ROOT pin honored (Contabo layout)" || bad "OPENCLAW_ROOT ignored"

# 9. broken openclaw.json is left untouched
R="$T/badjson"; mkdir -p "$R"; echo '{not json' > "$R/openclaw.json"
run "$R" --install --source "$SRC" | grep -q 'config-unreadable-left-untouched' && [ "$(cat "$R/openclaw.json")" = '{not json' ] && ok "unparseable config left untouched" || bad "unparseable config mishandled"

# 10. wiring: hook A above the content-recheck exit, hook B verify, install.sh call, allow-lists
US="$REPO/update-skills.sh"
la="$(grep -n 'install-full-read-guard.sh" --install\|--install --root' "$US" | head -1 | cut -d: -f1)"
stage="$(grep -n '_OC_EXT_STAGE="\$OC_CONFIG/.extensions-stage"' "$US" | head -1 | cut -d: -f1)"
burn="$(grep -n '^  _BURN_GUARD=' "$US" | head -1 | cut -d: -f1)"
rm_stage="$(grep -n 'rm -rf "${_OC_EXT_STAGE:-}"' "$US" | tail -1 | cut -d: -f1)"
verify="$(grep -n -- '--verify --root' "$US" | head -1 | cut -d: -f1)"
[ -n "$la" ] && [ -n "$stage" ] && [ "$la" -gt "$stage" ] && [ "$la" -lt "$burn" ] && ok "hook A sits between the extensions stage copy and the burn guard" || bad "hook A misplaced (a=$la stage=$stage burn=$burn)"
exit_line="$(grep -n -E '^[[:space:]]*_content_current_exit[[:space:]]*$' "$US" | head -1 | cut -d: -f1)"
[ -n "$la" ] && [ -n "$exit_line" ] && [ "$la" -lt "$exit_line" ] && ok "hook A is above the first _content_current_exit call site" || bad "hook A not above content-current exit (a=$la exit=$exit_line)"
[ -n "$verify" ] && [ "$verify" -gt "$rm_stage" ] 2>/dev/null && ok "hook B verify present after the telemetry block" || bad "hook B missing/misplaced"
grep -q 'install-full-read-guard.sh' "$REPO/install.sh" && ok "install.sh calls the installer" || bad "install.sh does not call the installer"
bash -n "$US" && bash -n "$REPO/install.sh" && ok "update-skills.sh and install.sh parse" || bad "syntax error in a wired script"
for f in scripts/apply-fleet-standards.sh scripts/apply-routing-fix.sh hooks/lib-ceo-tool-gate.sh 23-ai-workforce-blueprint/scripts/build-workforce.py; do
  grep -q '"read_skill"' "$REPO/$f" && ok "read_skill in $f" || bad "read_skill missing from $f"
done

# 11. one-line full-read rule: stamped once through the managed-block writer, additive
D="$T/doctrine"; mkdir -p "$D"; printf '# Agents\nkeep this line\n' > "$D/AGENTS.md"
( . "$REPO/shared-utils/agents-doctrine-blocks.sh"; stamp_full_read_guard "$D/AGENTS.md" >/dev/null; stamp_full_read_guard "$D/AGENTS.md" >/dev/null )
[ "$(grep -c 'FULL_READ_GUARD_V1' "$D/AGENTS.md")" = 1 ] && ok "rule stamped exactly once (idempotent)" || bad "rule stamped $(grep -c FULL_READ_GUARD_V1 "$D/AGENTS.md") times"
grep -q 'keep this line' "$D/AGENTS.md" && grep -q 'call `read_skill <skill-name>`' "$D/AGENTS.md" && ok "existing text kept, rule text present" || bad "rule text or existing text missing"
grep -q 'stamp_full_read_guard' "$REPO/scripts/apply-fleet-standards.sh" && ok "apply-fleet-standards.sh stamps the rule" || bad "apply-fleet-standards.sh does not stamp the rule"

[ "$fail" = 0 ] && echo "ALL PASS" || { echo "SOME FAILED"; exit 1; }
