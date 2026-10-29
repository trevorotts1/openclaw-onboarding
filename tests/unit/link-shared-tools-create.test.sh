#!/usr/bin/env bash
# link-shared-tools-create.test.sh (RRS001, widened 2026-10-29 "one rulebook") --
# link_shared_core_files must CREATE the missing AGENTS.md / TOOLS.md / USER.md
# of a registered agents.entries{} / agents.list[] workspace.
#
# RRS001 first covered TOOLS.md only and left AGENTS.md / USER.md "absent stays
# absent". The owner-approved one-rulebook rule (docs/SHARED-CORE-FILES.md)
# creates all three for a REGISTERED workspace; an UNREGISTERED folder still
# gains nothing. The full fixture box lives in shared-core-entries-sync.test.sh.
#
# THE LIVE BUG: "absent stays absent". OpenClaw 2026.10.x no longer seeds TOOLS.md,
# so an agent created after that change got a workspace with no TOOLS.md and the
# unify step never gave it one: it never saw the box's tool notes (for example the
# Gmail send path) and told an operator the box had no way to send.
#
# Runs the REAL function extracted from BOTH install.sh and update-skills.sh.
# Hermetic: mktemp sandbox, no box, no network. bash 3.2 safe.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL+1)); }
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT

run_one() {
  local SRC="$1" LABEL="$2"
  local D="$SANDBOX/$LABEL"; mkdir -p "$D"
  awk '/^link_shared_core_files\(\) \{/{f=1} f{print} f && /^\}$/{exit}' "$ROOT/$SRC" > "$D/fn.sh"
  bash -n "$D/fn.sh" || { bad "$LABEL: extracted function does not parse"; return; }
  grep -q 'registered agent had none' "$D/fn.sh" || { bad "$LABEL: no create-missing pass in $SRC (fix missing?)"; return; }

  (
    set +e
    note() { :; }; warn() { :; }
    . "$D/fn.sh"
    export HOME="$D/home"; mkdir -p "$HOME/.openclaw"
    CANON="$D/ws"; REG="$D/ws-registered"; REG2="$D/ws-has-tools"; REG3="$D/ws-legacy-list"; UNREG="$D/ws-unregistered"
    mkdir -p "$CANON" "$REG" "$REG2" "$REG3" "$UNREG"
    printf 'canon agents\n' > "$CANON/AGENTS.md"; printf 'canon user\n' > "$CANON/USER.md"
    printf 'BOX TOOLS: gmail send via service account\n' > "$CANON/TOOLS.md"
    printf 'agent own tools\n' > "$REG2/TOOLS.md"
    cat > "$HOME/.openclaw/openclaw.json" <<JSON
{"agents":{"defaults":{"workspace":"$CANON"},
 "entries":{"main":{"workspace":"$CANON"},"newagent":{"workspace":"$REG"},"hastools":{"workspace":"$REG2"}},
 "list":[{"id":"oldagent","workspace":"$REG3"}]}}
JSON
    OC_JSON="$HOME/.openclaw/openclaw.json"; OC_WORKSPACE_DEFAULT="$CANON"
    link_shared_core_files "$CANON" >/dev/null 2>&1
    R=0
    cmp -s "$CANON/TOOLS.md" "$REG/TOOLS.md" || { echo "no-create-entries"; R=1; }
    cmp -s "$CANON/TOOLS.md" "$REG3/TOOLS.md" || { echo "no-create-list"; R=1; }
    # one rulebook: a registered workspace's divergent TOOLS.md is now refreshed like any
    # other -- master wins, the original is backed up, its unique text goes to IDENTITY.md
    cmp -s "$CANON/TOOLS.md" "$REG2/TOOLS.md" || { echo "divergent-tools-not-refreshed"; R=1; }
    grep -qF "agent own tools" "$REG2"/TOOLS.md.bak-unify-* 2>/dev/null || { echo "no-backup-of-original"; R=1; }
    grep -qF "agent own tools" "$REG2/IDENTITY.md" 2>/dev/null || { echo "unique-text-not-preserved"; R=1; }
    [ -e "$UNREG/TOOLS.md" ] && { echo "unregistered-touched"; R=1; }
    cmp -s "$CANON/AGENTS.md" "$REG/AGENTS.md" || { echo "agents-not-created"; R=1; }
    cmp -s "$CANON/USER.md" "$REG/USER.md" || { echo "user-not-created"; R=1; }
    cmp -s "$CANON/AGENTS.md" "$REG3/AGENTS.md" || { echo "agents-not-created-list"; R=1; }
    [ -e "$UNREG/AGENTS.md" ] || [ -e "$UNREG/USER.md" ] && { echo "unregistered-touched"; R=1; }
    exit $R
  ) > "$D/out.txt" 2>&1
  local RC=$?
  if [ $RC -eq 0 ]; then ok "$LABEL: AGENTS/TOOLS/USER created for entries{} and list[] workspaces; divergent TOOLS.md refreshed (backup + preserved); unregistered dir untouched"
  else bad "$LABEL: $(tr '\n' ' ' < "$D/out.txt")"; fi

  # fail-open: an empty canonical TOOLS.md creates nothing
  (
    set +e; note() { :; }; warn() { :; }; . "$D/fn.sh"
    export HOME="$D/home"; OC_JSON="$HOME/.openclaw/openclaw.json"; OC_WORKSPACE_DEFAULT="$D/ws"
    : > "$D/ws/TOOLS.md"; rm -f "$D/ws-registered/TOOLS.md"
    link_shared_core_files "$D/ws" >/dev/null 2>&1
    [ ! -e "$D/ws-registered/TOOLS.md" ]
  )
  [ $? -eq 0 ] && ok "$LABEL: empty canonical TOOLS.md creates nothing (fail-open)" || bad "$LABEL: created TOOLS.md from an empty canonical"

  # a skill-15-seeded AGENTS.md is replaced by canonical WITHOUT being appended into IDENTITY.md
  (
    set +e; note() { :; }; warn() { :; }; . "$D/fn.sh"
    export HOME="$D/home"; OC_JSON="$HOME/.openclaw/openclaw.json"; OC_WORKSPACE_DEFAULT="$D/ws"
    W="$HOME/.openclaw/workspaces/seeded"; mkdir -p "$W"
    printf '<!-- rr-operator-support:v1 -->\nseeded agents text\n' > "$W/AGENTS.md"
    printf 'IDENTITY ONLY\n' > "$W/IDENTITY.md"
    printf 'canon agents v2\n' > "$D/ws/AGENTS.md"; printf 'BOX TOOLS\n' > "$D/ws/TOOLS.md"
    link_shared_core_files "$D/ws" >/dev/null 2>&1
    [ "$(cat "$W/IDENTITY.md")" = "IDENTITY ONLY" ] && cmp -s "$D/ws/AGENTS.md" "$W/AGENTS.md"
  )
  [ $? -eq 0 ] && ok "$LABEL: seeded AGENTS.md is unified without polluting IDENTITY.md" || bad "$LABEL: seeded AGENTS.md was appended into IDENTITY.md (or not unified)"
}

run_one install.sh install
run_one update-skills.sh updater

echo ""
echo "=== link-shared-tools-create: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
