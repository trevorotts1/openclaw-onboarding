#!/usr/bin/env bash
# hook-mapping-contract.test.sh — the fixture matrix for the ONE inbound-mapping
# contract (scripts/lib-hook-mapping-contract.sh).
#
# WHAT IT PROVES
#   G-03  a mapping with no `model` is refused (the installer never wrote one, so
#         a fresh install could never pass its own readiness gate)
#   G-04  qc-backend-ready.sh fails the SAME mapping 24-self-test-hook.sh fails,
#         even when a DIFFERENT mapping in the same file carries a model — the
#         exact case its whole-file grep used to pass
#   G-05  the two gates emit byte-identical verdicts on every fixture, positive
#         and negative
#
# The known-good control exists so that "both fail everything" can never be
# mistaken for agreement: if the control does not PASS in both gates, the
# instruments are broken and the matrix proves nothing.
#
# It also asserts the three surfaces share the contract:
#   * scripts/15-configure-hooks-mappings.sh emits every key the contract
#     requires (and names `model` when T-09's writer adds it)
#   * the writer's fail-closed directive needles equal the contract's needles
#
# Hermetic: fixtures only, no gateway, no network, no live openclaw.json.
# Bash + POSIX awk. Exit 0 = all rows agree and match expectation.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$(cd "$HERE/../scripts" && pwd)"
SELFTEST="$SCRIPTS/24-self-test-hook.sh"
QC="$SCRIPTS/qc-backend-ready.sh"
WRITER="$SCRIPTS/15-configure-hooks-mappings.sh"
LIB="$SCRIPTS/lib-hook-mapping-contract.sh"

TMP="${TMPDIR:-/tmp}/hook-mapping-contract.test.$$"
mkdir -p "$TMP" || { echo "FAIL cannot make $TMP"; exit 1; }
trap 'rm -rf "$TMP"' EXIT

FAIL=0
ROWS=0
ok()   { printf 'ok   %s\n' "$*"; }
bad()  { printf 'FAIL %s\n' "$*"; FAIL=1; }

# ---------------------------------------------------------------- fixtures --
# The directive text is the twelve needles the writer's guard enforces. The
# needle-list equality assertion below is what keeps this honest.
MT='MANDATORY SEND GHL Conversations API drafting NOT sending messageId SAME channel do NOT hardcode SMS conversations/search conversational-logs read append'

# base_mapping <body-override> -> the full hooks.mappings element
base_mapping() {
  printf '%s' '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-a","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:x","messageTemplate":"'"$MT"'","model":"client-model","deliver":false,"timeoutSeconds":300}'
}

# fixture <name> <mappings-json> <enabled>
fixture() {
  printf '{\n  "hooks": {\n    "enabled": %s,\n    "token": "t",\n    "allowedAgentIds": ["agent-a"],\n    "mappings": [%s]\n  }\n}\n' "$3" "$2" > "$TMP/$1.json"
}

m="$(base_mapping)"
fixture "known-good-control"   "$m" true
fixture "t09-upgraded"         '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-a","deliver":false,"model":"client-model","messageTemplate":"'"$MT"'","sessionKey":"hook:ghl:x","name":"GHL Inbound","wakeMode":"now","timeoutSeconds":300}' true
fixture "fresh-installer-today" '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-a","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:x","messageTemplate":"'"$MT"'","deliver":false,"timeoutSeconds":300}' true
fixture "missing-model"        '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-a","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:x","messageTemplate":"'"$MT"'","model":"","deliver":false,"timeoutSeconds":300}' true
fixture "stale-agentId"        '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-GONE","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:x","messageTemplate":"'"$MT"'","model":"client-model","deliver":false,"timeoutSeconds":300}' true
fixture "missing-directive"    '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-a","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:x","messageTemplate":"MANDATORY SEND GHL Conversations API drafting NOT sending messageId do NOT hardcode SMS conversations/search conversational-logs read append","model":"client-model","deliver":false,"timeoutSeconds":300}' true
fixture "wrong-shape"          '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-a","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:x","messageTemplate":"'"$MT"'","model":"client-model","deliver":false,"timeoutSeconds":300,"fallbacks":["m2"]}' true
fixture "hooks-disabled"       "$m" false
# G-04: a decoy mapping that carries a model must NOT launder the target that has none.
fixture "decoy-model-elsewhere" '{"id":"r1","match":{"path":"r1"},"action":"agent","agentId":"agent-a","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:x","messageTemplate":"'"$MT"'","deliver":false,"timeoutSeconds":300},{"id":"r2","match":{"path":"r2"},"action":"agent","agentId":"agent-a","wakeMode":"now","name":"GHL Inbound","sessionKey":"hook:ghl:y","messageTemplate":"'"$MT"'","model":"decoy-model","deliver":false,"timeoutSeconds":300}' true

# row name | expected GATEVERDICT | a reason the mapping must carry (or "-" for none)
MATRIX='known-good-control|OK|-
t09-upgraded|OK|-
fresh-installer-today|ERR|missing-key:model
missing-model|ERR|no-model
stale-agentId|ERR|agentId-not-allowed
missing-directive|ERR|missing-directive:SAME channel
wrong-shape|ERR|unexpected-key:fallbacks
decoy-model-elsewhere|ERR|missing-key:model
hooks-disabled|ERR|hooks-disabled'

# ------------------------------------------------------- run both gates -----
gate_report() {  # gate_report <script> <config>  -> the machine-comparable lines
  case "$1" in
    selftest) OPENCLAW_CONFIG="$2" HOOK_NAME=r1 bash "$SELFTEST" --mapping-only 2>/dev/null ;;
    qc)       bash "$QC" --config "$2" --healthz "" 2>/dev/null ;;
  esac | grep -E '^(MAPCONTRACT|MAPENABLED|MAPSELECT|GATEVERDICT)\|' | LC_ALL=C sort
}

echo "=== hook-mapping-contract fixture matrix ==="

while IFS='|' read -r name want reason; do
  [ -n "$name" ] || continue
  ROWS=$((ROWS + 1))
  cfg="$TMP/$name.json"
  a="$(gate_report selftest "$cfg")"
  b="$(gate_report qc "$cfg")"

  if [ "$a" = "$b" ]; then
    ok "row $name: 24-self-test-hook.sh and qc-backend-ready.sh report IDENTICAL verdicts"
  else
    bad "row $name: the two gates disagree"
    diff <(printf '%s\n' "$a") <(printf '%s\n' "$b") | sed 's/^/        /'
  fi

  got="$(printf '%s\n' "$a" | grep '^GATEVERDICT|' | head -n1 | cut -d'|' -f2)"
  if [ "$got" = "$want" ]; then
    ok "row $name: GATEVERDICT=$got (expected $want)"
  else
    bad "row $name: GATEVERDICT=$got, expected $want"
    printf '%s\n' "$a" | sed 's/^/        /'
  fi

  if [ "$reason" != "-" ]; then
    if printf '%s\n' "$a" | grep -F "$reason" >/dev/null; then
      ok "row $name: reports '$reason'"
    else
      bad "row $name: expected reason '$reason' not reported"
    fi
  fi

  # both gates must also agree on the process-level verdict
  rc_a=0; OPENCLAW_CONFIG="$cfg" HOOK_NAME=r1 bash "$SELFTEST" --mapping-only >/dev/null 2>&1 || rc_a=$?
  rc_b=0; bash "$QC" --config "$cfg" --healthz "" >/dev/null 2>&1 || rc_b=$?
  want_rc=0; [ "$want" = "OK" ] || want_rc=1
  if [ "$rc_a" -eq "$want_rc" ] && [ "$rc_b" -eq "$want_rc" ]; then
    ok "row $name: both gates exit $want_rc"
  else
    bad "row $name: exit codes self-test=$rc_a qc-backend-ready=$rc_b, expected $want_rc/$want_rc"
  fi
done <<EOF
$MATRIX
EOF

# ------------------------------------------------- known-good control ------
# If this does not PASS in both, every "identical" row above is worthless.
# (Capture first, then grep: `grep -q` closes a pipe early and `set -o pipefail`
# would then fail the check on SIGPIPE rather than on the verdict.)
ctl_a="$(OPENCLAW_CONFIG="$TMP/known-good-control.json" HOOK_NAME=r1 bash "$SELFTEST" --mapping-only 2>/dev/null)"
ctl_b="$(bash "$QC" --config "$TMP/known-good-control.json" --healthz "" 2>/dev/null)"
if printf '%s\n' "$ctl_a" | grep '^GATEVERDICT|OK|' >/dev/null && printf '%s\n' "$ctl_b" | grep '^GATEVERDICT|OK|' >/dev/null; then
  ok "known-good control PASSES in both gates (identical failure cannot masquerade as agreement)"
else
  bad "known-good control does not PASS in both gates — the matrix above proves nothing"
  printf '%s\n' "$ctl_a" | sed 's/^/        self-test: /'
  printf '%s\n' "$ctl_b" | sed 's/^/        qc:       /'
fi

# ------------------------------------------ the three surfaces agree -------
. "$LIB"

# (1) the writer emits every key the contract requires
if [ -f "$WRITER" ]; then
  NEWBLOCK="$(awk '/NEW_MAPPING="\$\(jq -n/{f=1} f{print} f && /\}'"'"'\)"/{exit}' "$WRITER")"
  MISSING=""
  for k in id match action agentId deliver messageTemplate; do
    printf '%s' "$NEWBLOCK" | grep -E "(^|[[:space:],{])${k}[[:space:]]*:" >/dev/null || MISSING="$MISSING $k"
  done
  if [ -z "$MISSING" ]; then
    ok "writer emits every contract key except the ones below"
  else
    bad "15-configure-hooks-mappings.sh does not emit:$MISSING"
  fi
  if printf '%s' "$NEWBLOCK" | grep -E '(^|[[:space:],{])model[[:space:]]*:' >/dev/null; then
    ok "writer emits 'model' — G-03 is closed on the writer side too"
  else
    ok "writer does NOT emit 'model' yet (G-03, T-09 lane owns that write) — the contract refuses the fresh mapping until it does"
  fi
else
  bad "writer not found at $WRITER"
fi

# (2) the writer's fail-closed directive needles equal the contract's needles
if [ -f "$WRITER" ]; then
  writer_needles="$(grep -E '^[[:space:]]*for needle in ' "$WRITER" | grep -oE '"[^"]+"' | tr -d '"' | tr 'A-Z' 'a-z' | LC_ALL=C sort -u)"
  lib_needles="$(printf '%s\n' "$HOOK_MAPPING_DIRECTIVE_NEEDLES" | tr 'A-Z' 'a-z' | grep -v '^$' | LC_ALL=C sort -u)"
  if [ -n "$writer_needles" ] && [ "$writer_needles" = "$lib_needles" ]; then
    ok "writer directive needles == contract needles ($(printf '%s\n' "$lib_needles" | wc -l | tr -d ' ') needles)"
  else
    bad "writer directive needles and contract needles differ"
    diff <(printf '%s\n' "$lib_needles") <(printf '%s\n' "$writer_needles") | sed 's/^/        /'
  fi
fi

# ------------------------------------- install.sh: content verify + receipt --
# install_skill_38_conversational_ai_system used to skip the copy on a matching
# skill-version.txt STRING ALONE, so a dest wearing the right version with wrong
# content was never refreshed. It must now verify content AND emit a receipt.
# The function is extracted and run with stubs — no 10k-line installer, no box.
INSTALLER="$HERE/../../install.sh"
if [ -f "$INSTALLER" ]; then
  awk '/^install_skill_38_conversational_ai_system\(\) \{/{f=1} f{print} f && /^\}/{exit}' "$INSTALLER" > "$TMP/s38-fn.sh"
fi

if [ -s "$TMP/s38-fn.sh" ]; then
  cat > "$TMP/run-s38.sh" <<'RUNNER'
set -uo pipefail
warn()   { printf 'warn   %s\n' "$*"; }
success(){ printf 'succ   %s\n' "$*"; }
note()   { printf 'note   %s\n' "$*"; }
oc_ghl_mcp_json_str() {
  local _s="${1:-}"
  _s="${_s//\\/\\\\}"; _s="${_s//\"/\\\"}"
  _s="${_s//$'\n'/ }"; _s="${_s//$'\r'/ }"; _s="${_s//$'\t'/ }"
  printf '"%s"' "$_s"
}
LOG_FILE="$SANDBOX/install.log"; : > "$LOG_FILE"
ONBOARDING_DIR="$SANDBOX/src"; SKILLS_DIR="$SANDBOX/dest"
mkdir -p "$ONBOARDING_DIR" "$SKILLS_DIR"
. "$S38_FN"
install_skill_38_conversational_ai_system > "$SANDBOX/out.$RUN_LABEL" 2>&1
RUNNER

  # seed a source tree carrying the four contract-carrying scripts
  mkdir -p "$TMP/src-seed/scripts" "$TMP/src-seed/protocols"
  printf 'v9.9.9\n' > "$TMP/src-seed/skill-version.txt"
  for f in lib-hook-mapping-contract.sh 24-self-test-hook.sh qc-backend-ready.sh 15-configure-hooks-mappings.sh; do
    printf '# %s source body\n' "$f" > "$TMP/src-seed/scripts/$f"
  done

  # Every run targets the SAME sandbox — the label only names the captured
  # output. The point is repeat installs against one dest.
  s38() {
    SANDBOX="$TMP/s38-fresh" RUN_LABEL="$1" S38_FN="$TMP/s38-fn.sh" bash "$TMP/run-s38.sh" >/dev/null 2>&1
  }
  receipt() { cat "$TMP/s38-fresh/dest/38-conversational-ai-system/provisioning-receipt.json" 2>/dev/null; }

  # 1. fresh install
  mkdir -p "$TMP/s38-fresh/src/38-conversational-ai-system"; cp -R "$TMP/src-seed/." "$TMP/s38-fresh/src/38-conversational-ai-system/"
  s38 fresh
  if receipt | grep '"action": "installed"' >/dev/null && receipt | grep '"content_verified": true' >/dev/null; then
    ok "install: fresh install copies content and writes a receipt (action=installed, content_verified=true)"
  else
    bad "install: fresh install did not write the expected receipt"; receipt | sed 's/^/        /'
  fi

  # 2. unchanged re-run -> already-current, still receipted
  s38 rerun
  if receipt | grep '"action": "already-current"' >/dev/null; then
    ok "install: unchanged re-run is idempotent (action=already-current)"
  else
    bad "install: unchanged re-run was not recognised as already-current"; receipt | sed 's/^/        /'
  fi

  # 3. version string matches but CONTENT drifted -> must refresh, not skip
  printf '# TAMPERED\n' > "$TMP/s38-fresh/dest/38-conversational-ai-system/scripts/24-self-test-hook.sh"
  s38 drift
  if receipt | grep '"action": "refreshed-content-drift"' >/dev/null \
     && receipt | grep '"content_verified": true' >/dev/null \
     && ! grep 'TAMPERED' "$TMP/s38-fresh/dest/38-conversational-ai-system/scripts/24-self-test-hook.sh" >/dev/null; then
    ok "install: content drift under a matching version string is REFRESHED (the old string-only check skipped it)"
  else
    bad "install: content drift was not refreshed — the string-only skip is still live"; receipt | sed 's/^/        /'
  fi

  # 4. version moved -> refreshed-version
  printf 'v9.9.8\n' > "$TMP/s38-fresh/dest/38-conversational-ai-system/skill-version.txt"
  s38 ver
  if receipt | grep '"action": "refreshed-version"' >/dev/null; then
    ok "install: a version change is reported as refreshed-version"
  else
    bad "install: a version change was not reported as refreshed-version"; receipt | sed 's/^/        /'
  fi

  # 5. the receipt is secret-free
  if receipt | grep -iE 'token|secret|apikey|api_key|password' >/dev/null; then
    bad "install: the provisioning receipt mentions a credential-shaped key"
  else
    ok "install: provisioning receipt is secret-free"
  fi
else
  bad "could not extract install_skill_38_conversational_ai_system from ${INSTALLER:-install.sh}"
fi

if [ "$FAIL" -eq 0 ]; then
  echo "hook-mapping-contract.test.sh: $ROWS rows, both gates agree on every one, expectations met."
  exit 0
fi
echo "hook-mapping-contract.test.sh: FAILED"
exit 1
