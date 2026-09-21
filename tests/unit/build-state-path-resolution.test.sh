#!/usr/bin/env bash
# tests/unit/build-state-path-resolution.test.sh
# ---------------------------------------------------------------------------
# Verified on the operator canary: `run-full-install.sh --update-only` built
# STATE_FILE from OPENCLAW_WORKSPACE_PATH, which oc_set_platform_paths sets
# from openclaw.json's agents.defaults.workspace (there: ~/clawd). The real
# file lives at ~/.openclaw/workspace/.workforce-build-state.json. With no
# state file found, interview-launch.py's inspector returned
# requiresInitialization:true / companySlug:null and the run exited 8,
# demanding an interactive interview on a fully built box. Exporting
# OPENCLAW_WORKSPACE_PATH by hand fixed that one run.
#
# A configured path is a hint, not evidence. resolve_build_state_workspace()
# picks the first candidate that ACTUALLY holds the file, and records every
# path it tried so a caller that finds nothing can NAME what it checked.
#
# Extracts the function VERBATIM from shared-utils/resolve-oc-root.sh, so a
# rename fails loudly (exit 2) instead of testing nothing. Fully offline.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOLVER="$REPO_ROOT/shared-utils/resolve-oc-root.sh"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $*"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $*"; }

[ -f "$RESOLVER" ] || { echo "FATAL: $RESOLVER not found"; exit 2; }
grep -q '^resolve_build_state_workspace() {' "$RESOLVER" \
  || { echo "FATAL: resolve_build_state_workspace() not found in resolve-oc-root.sh — renamed?"; exit 2; }
bash -n "$RESOLVER" || { echo "FATAL: resolver does not parse"; exit 2; }
# shellcheck disable=SC1090
. "$RESOLVER"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== (1) the canary: openclaw.json points elsewhere, real file under OC_ROOT/workspace =="
mkdir -p "$WORK/clawd" "$WORK/oc/workspace" "$WORK/home/.openclaw/workspace"
: > "$WORK/oc/workspace/.workforce-build-state.json"
got="$(OPENCLAW_WORKSPACE_PATH="$WORK/clawd" OC_ROOT="$WORK/oc" HOME="$WORK/home" \
       resolve_build_state_workspace)"; rc=$?
[ "$rc" = "0" ] && [ "$got" = "$WORK/oc/workspace" ] \
  && ok "(1) resolved to the workspace that HAS the file, not the configured one" \
  || bad "(1) rc=$rc got='$got', expected $WORK/oc/workspace"

echo "== (2) the configured path wins when it really holds the file =="
: > "$WORK/clawd/.workforce-build-state.json"
got="$(OPENCLAW_WORKSPACE_PATH="$WORK/clawd" OC_ROOT="$WORK/oc" HOME="$WORK/home" \
       resolve_build_state_workspace)"
[ "$got" = "$WORK/clawd" ] \
  && ok "(2) OPENCLAW_WORKSPACE_PATH is still first when it has the file" \
  || bad "(2) got '$got', expected $WORK/clawd"
rm -f "$WORK/clawd/.workforce-build-state.json"

echo "== (3) the HOME fallback is reached =="
: > "$WORK/home/.openclaw/workspace/.workforce-build-state.json"
rm -f "$WORK/oc/workspace/.workforce-build-state.json"
got="$(OPENCLAW_WORKSPACE_PATH="$WORK/clawd" OC_ROOT="$WORK/oc" HOME="$WORK/home" \
       resolve_build_state_workspace)"
[ "$got" = "$WORK/home/.openclaw/workspace" ] \
  && ok "(3) ~/.openclaw/workspace is searched after the configured path" \
  || bad "(3) got '$got', expected $WORK/home/.openclaw/workspace"

echo "== (4) nothing anywhere: refuse, and NAME every path searched =="
E="$WORK/empty"; mkdir -p "$E/oc" "$E/home"
got="$(OPENCLAW_WORKSPACE_PATH="$E/cfg" OC_ROOT="$E/oc" HOME="$E/home" \
       resolve_build_state_workspace)"; rc=$?
[ "$rc" != "0" ] && ok "(4) returns non-zero when no candidate has the file" \
                 || bad "(4) returned 0 with no file anywhere (got '$got')"
# shellcheck disable=SC2034
OPENCLAW_WORKSPACE_PATH="$E/cfg" OC_ROOT="$E/oc" HOME="$E/home" resolve_build_state_workspace >/dev/null
for expect in "$E/cfg" "$E/oc/workspace" "$E/home/.openclaw/workspace" "/data/.openclaw/workspace"; do
  case " $OC_BUILD_STATE_SEARCHED " in
    *" $expect "*) ok "(4) searched path is reported: $expect" ;;
    *) bad "(4) searched path NOT reported: $expect (got: $OC_BUILD_STATE_SEARCHED)" ;;
  esac
done

echo "== (5) a duplicate candidate is not searched twice =="
D="$WORK/dup"; mkdir -p "$D/workspace"
OPENCLAW_WORKSPACE_PATH="$D/workspace" OC_ROOT="$D" HOME="$D/h" resolve_build_state_workspace >/dev/null
n=$(printf '%s\n' $OC_BUILD_STATE_SEARCHED | grep -c "^$D/workspace$")
[ "$n" = "1" ] && ok "(5) the same path appears once, not twice" \
               || bad "(5) '$D/workspace' appears $n times"

echo "== (6) every shell reader of the build state routes through the resolver =="
for f in 32-command-center-setup/scripts/run-full-install.sh \
         32-command-center-setup/scripts/materialize-dept-agents.sh \
         32-command-center-setup/scripts/backfill-per-dept-healer.sh; do
  if grep -q 'resolve_build_state_workspace' "$REPO_ROOT/$f"; then
    ok "(6) $(basename "$f") uses the resolver"
  else
    bad "(6) $(basename "$f") still builds the build-state path on its own"
  fi
done

echo "== (7) a fresh install still has a write target =="
# When nothing has the file the installer must fall back to the configured
# path, not refuse: that is the correct write target for a first install.
grep -q 'STATE_FILE="${OPENCLAW_WORKSPACE_PATH:-$OC_ROOT/workspace}/.workforce-build-state.json"' \
     "$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh" \
  && ok "(7) run-full-install.sh keeps the configured path as the fresh-install fallback" \
  || bad "(7) the fresh-install fallback is gone — a first install has nowhere to write"
grep -q 'searched: \$OC_BUILD_STATE_SEARCHED' \
     "$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh" \
  && ok "(7) the not-found message names every path searched" \
  || bad "(7) the not-found message does not name the searched paths"

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
