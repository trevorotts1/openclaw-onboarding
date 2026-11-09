#!/usr/bin/env bash
# tests/unit/shared-core-entries-sync.test.sh
# -----------------------------------------------------------------------------
# ONE RULEBOOK. Every agent on a box uses the box's ONE master AGENTS.md /
# TOOLS.md / USER.md (N29), as REAL-FILE copies refreshed on every roll.
#
# THE DEFECT THIS LOCKS. link_shared_core_files() built its primary candidate
# list from agents.list[] only. A box on the current config shape keeps its
# agents in agents.entries{} (an object keyed by agent id), so those workspaces
# were reached only by a directory scan that (a) descended into backup trees
# and vendored skill folders it must never rewrite, (b) never reached the
# company tree Skill 23 builds (<company>/departments/<dept>/<role>) and (c)
# left a registered agent's missing AGENTS.md / USER.md absent forever.
# Measured on a real client box (OpenClaw 2026.10.5, 49 agents in
# agents.entries): 718 AGENTS.md copies (669 identical), 830 TOOLS.md, 785
# USER.md, spread over department role folders, command-center folders,
# <dept>.bak-* and .floor-backups trees.
#
# WHAT THIS PROVES (behavioral: it runs the REAL function extracted from BOTH
# install.sh and update-skills.sh, against a fixture box):
#   S1  every registered workspace (agents.entries, agents.list, agents.defaults)
#       ends byte-identical to the master, including the command-center folder
#       and workspaces that sit outside every scan root
#   S2  a registered workspace missing a core file gets it created
#   S3  a department's unique AGENTS.md block survives in that department's
#       own IDENTITY.md
#   S4  backup trees, hidden dirs, departments-archive, node_modules, a codex-home
#       folder, another company's tree and the vendored skill / onboarding /
#       template trees of an agent workspace are left byte-untouched
#   S5  a department ROLE folder never gains an AGENTS.md (U053) but is kept in
#       step on TOOLS.md / USER.md; an unregistered folder never gains a file
#   S6  a symlink relic is migrated to a real file; the only symlink left is
#       the fixture's own symlinked scan root
#   S7  a second run changes nothing (no rewrite, no new backup)
#   S8  fail-open: an empty master file is never copied over anything
#   S9  the two department-specific role-library TOOLS.md files (presentations,
#       rescue-rangers) end identical to the master with every one of their
#       unique blocks preserved in the department's IDENTITY.md
#   S10 THIS box's own company tree (build-state companyRoot, master-files
#       zero-human-company/<slug>, workspace-local zero-human-company/<slug>) is
#       synced down to the role folders; another company's tree is not touched
#   S11 a later, DIFFERENT unique block is appended to IDENTITY.md too, and a
#       repeat of an already preserved block is not appended twice
#   S12 a CREATE failure in a workspace that never had the file warns loudly but
#       does not fail the function (so it cannot block the version stamp)
#   S13 a symlinked scan root is walked
#   S14 registered workspaces are never filtered by name (skills, onboarding, a
#       hidden folder, a folder inside a skipped templates/ tree)
#   S15 an unregistered real department NAMED templates / onboarding / skills
#       (not inside an agent workspace) is synced
#   S16 no company slug known: no company tree is read (fail closed); a slug
#       given by COMPANY_SLUG scopes the scan to that company only
#   P1  install.sh and update-skills.sh carry a byte-identical candidate block
#   P2  the python scan function is byte-identical in both scripts and in QC 9.9
#   Q1  QC check 9.9 FAILS on drift (entries, command-center, company tree, a
#       missing registered file) and PASSES after sync
#   M*  MUTATION PROOF: each rule above is broken in a COPY of the function and
#       the matching check must go red, so this test cannot pass vacuously
#
# Hermetic: mktemp sandbox, HOME redirected into it, no network, no box.
# bash 3.2 safe: no associative arrays, no mapfile.
# Exit 0 = all pass, 1 = at least one failure.
# -----------------------------------------------------------------------------
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }
skp() { printf '  skip %s\n' "$1"; }
hdr() { printf '\n== %s ==\n' "$1"; }

if [ -d /data/.openclaw ]; then
  echo "SKIP: /data/.openclaw exists on this host, so the function would read the real box (not hermetic)"
  exit 0
fi
unset COMPANY_SLUG MASTER_FILES_DIR OPENCLAW_MASTER_FILES_DIR OPENCLAW_WORKSPACE_PATH

SANDBOX="$(mktemp -d)"
trap 'chmod -R u+w "$SANDBOX" 2>/dev/null; rm -rf "$SANDBOX"' EXIT

_sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

# snap DIR -> one line per file/symlink: "<sha> <relpath>" or "L <relpath>"
snap() {
  ( cd "$1" && find . \( -type f -o -type l \) | LC_ALL=C sort | while IFS= read -r p; do
      if [ -L "$p" ]; then echo "L $p"; else echo "$(_sha "$p") $p"; fi
    done )
}

# emit OUT 0|1 NAME -> "ok NAME" / "bad NAME" line
emit() { if [ "$2" = 0 ]; then echo "ok $3" >> "$1"; else echo "bad $3" >> "$1"; fi; }

# --------------------------------------------------------------------------
# Fixture box. Layout (every path lives under $1):
#   home/.openclaw/openclaw.json    agents.entries + agents.list + defaults
#   home/.openclaw/workspace        the MASTER (canonical) workspace
#   home/Downloads/openclaw-master-files/zero-human-company/<co>   company trees
# --------------------------------------------------------------------------
build_box() {
  local D="$1"
  rm -rf "$D"; mkdir -p "$D/home/.openclaw"
  local OCR="$D/home/.openclaw" WS="$D/home/.openclaw/workspace"
  local ZHC1="$D/home/Downloads/openclaw-master-files/zero-human-company"
  local ZHC0="$D/outside/co-root/acme-co" ZHC3="$WS/zero-human-company/acme-co"
  mkdir -p "$WS/departments" "$OCR/workspaces/command-center" "$D/outside"

  # the MASTER
  printf 'MASTER AGENTS\n\nrule one\n\nrule two\n'   > "$WS/AGENTS.md"
  printf 'MASTER TOOLS\n\ntool one\n'                  > "$WS/TOOLS.md"
  printf 'MASTER USER\n\nthe owner\n'                  > "$WS/USER.md"

  # registered department (entries): drifted AGENTS.md with a unique block,
  # drifted USER.md, TOOLS.md missing
  mkdir -p "$WS/departments/sales"
  printf 'MASTER AGENTS\n\nrule one\n\nSALES-ONLY RULE: always cc the closer\n' > "$WS/departments/sales/AGENTS.md"
  printf 'sales owner notes\n' > "$WS/departments/sales/USER.md"
  printf '# sales identity\n' > "$WS/departments/sales/IDENTITY.md"
  # unregistered role folder (scan-found): drifted TOOLS.md, no AGENTS.md
  mkdir -p "$WS/departments/sales/closer"
  printf '# closer\n' > "$WS/departments/sales/closer/IDENTITY.md"
  printf 'closer tools drift\n' > "$WS/departments/sales/closer/TOOLS.md"
  # REGISTERED role folder: only IDENTITY.md
  mkdir -p "$WS/departments/sales/setter"
  printf '# setter\n' > "$WS/departments/sales/setter/IDENTITY.md"
  # registered dept whose AGENTS.md is a symlink relic
  mkdir -p "$WS/departments/legal" "$D/outside/relic"
  printf '# legal\n' > "$WS/departments/legal/IDENTITY.md"
  printf 'relic target\n' > "$D/outside/relic/AGENTS.md"
  ln -s "$D/outside/relic/AGENTS.md" "$WS/departments/legal/AGENTS.md"

  # command-center folders: one registered (entries), one found by the scan only
  mkdir -p "$OCR/workspaces/command-center/support" "$OCR/workspaces/command-center/billing"
  printf 'MASTER AGENTS\n\nSUPPORT-ONLY RULE: tag every ticket\n' > "$OCR/workspaces/command-center/support/AGENTS.md"
  printf '# support\n' > "$OCR/workspaces/command-center/support/IDENTITY.md"
  printf 'billing drift\n' > "$OCR/workspaces/command-center/billing/AGENTS.md"
  printf '# billing\n' > "$OCR/workspaces/command-center/billing/IDENTITY.md"
  # REAL departments that merely carry a vendored-tree NAME (their parent, the
  # command-center container, is not an agent workspace): they must be synced
  local n
  for n in templates onboarding skills; do
    mkdir -p "$OCR/workspaces/command-center/$n"
    printf 'real dept %s drift\n' "$n" > "$OCR/workspaces/command-center/$n/AGENTS.md"
    printf '# %s\n' "$n" > "$OCR/workspaces/command-center/$n/IDENTITY.md"
  done

  # registered, outside every scan root, empty: must be CREATED
  mkdir -p "$D/outside/ext" "$D/outside/dflt" "$D/outside/legacy"
  # legacy agents.list agent with a unique block
  printf 'MASTER AGENTS\n\nLEGACY-ONLY RULE: page the owner\n' > "$D/outside/legacy/AGENTS.md"
  printf '# legacy\n' > "$D/outside/legacy/IDENTITY.md"
  # registered workspaces whose NAME looks like a skipped tree (never filtered)
  mkdir -p "$D/outside/reg/skills" "$D/outside/reg/onboarding" "$D/outside/.hidden-reg/agent" \
           "$OCR/workspaces/command-center/support/templates/regtpl"
  printf '# regtpl\n' > "$OCR/workspaces/command-center/support/templates/regtpl/IDENTITY.md"

  # unregistered folder with only IDENTITY.md: must stay without core files
  mkdir -p "$OCR/workspaces/orphan"
  printf '# orphan\n' > "$OCR/workspaces/orphan/IDENTITY.md"

  # symlinked scan root: <workspace>/agents is a symlink to a folder elsewhere
  mkdir -p "$D/outside/agents-store/helper"
  printf '# helper\n' > "$D/outside/agents-store/helper/IDENTITY.md"
  printf 'helper drift\n' > "$D/outside/agents-store/helper/AGENTS.md"
  ln -s "$D/outside/agents-store" "$WS/agents"

  # THIS box's own company tree, three places (build-state root, master-files, workspace-local)
  printf '{"companySlug":"acme-co","companyRoot":"%s","interviewComplete":true}\n' "$ZHC0" > "$WS/.workforce-build-state.json"
  mkdir -p "$ZHC0/departments/ops/planner" "$ZHC1/acme-co/departments/marketing/copywriter" "$ZHC3/departments/finance/analyst"
  printf '# ops\n' > "$ZHC0/departments/ops/IDENTITY.md"
  printf 'MASTER AGENTS\n\nOPS-ONLY RULE: close the loop\n' > "$ZHC0/departments/ops/AGENTS.md"
  printf '# planner\n' > "$ZHC0/departments/ops/planner/IDENTITY.md"
  printf 'planner tools drift\n' > "$ZHC0/departments/ops/planner/TOOLS.md"
  printf 'planner leftover agents\n' > "$ZHC0/departments/ops/planner/AGENTS.md"
  printf '# copywriter\n' > "$ZHC1/acme-co/departments/marketing/copywriter/IDENTITY.md"
  printf 'copywriter tools drift\n' > "$ZHC1/acme-co/departments/marketing/copywriter/TOOLS.md"
  printf '# analyst\n' > "$ZHC3/departments/finance/analyst/IDENTITY.md"
  printf 'analyst user drift\n' > "$ZHC3/departments/finance/analyst/USER.md"

  # ---- TRAPS: none of these may be touched ----
  mkdir -p "$WS/departments/sales.bak-20261001" "$WS/departments/.floor-backups/sales" \
           "$OCR/workspaces/command-center/support.bak-x" "$OCR/workspaces/departments-archive/old" \
           "$OCR/workspaces/command-center/support/skills/vendored" "$WS/departments/sales/node_modules/pkg" \
           "$OCR/workspaces/onboarding" "$WS/departments/sales/templates/x" "$OCR/workspaces/fleet-refresh/y" \
           "$OCR/workspaces/codex-home/.tmp/z" \
           "$ZHC1/other-co/departments/sales/closer"
  local t
  for t in $(trap_dirs "$D"); do
    printf 'TRAP agents file that belongs to something else\n' > "$t/AGENTS.md"
    printf '# trap identity\n' > "$t/IDENTITY.md"
    printf 'TRAP tools\n' > "$t/TOOLS.md"
  done
  # another company's tree on the same box: never this box's own, never touched
  printf 'OTHER COMPANY dept agents\n' > "$ZHC1/other-co/departments/sales/AGENTS.md"
  printf '# other dept\n' > "$ZHC1/other-co/departments/sales/IDENTITY.md"
  printf 'OTHER COMPANY user\n' > "$ZHC1/other-co/departments/sales/closer/USER.md"

  cat > "$OCR/openclaw.json" <<JSON
{"agents":{"defaults":{"workspace":"$D/outside/dflt"},
 "entries":{"main":{"workspace":"$WS"},
            "dept-sales":{"workspace":"$WS/departments/sales"},
            "dept-setter":{"workspace":"$WS/departments/sales/setter"},
            "dept-legal":{"workspace":"$WS/departments/legal"},
            "dept-support":{"workspace":"$OCR/workspaces/command-center/support"},
            "dept-regtpl":{"workspace":"$OCR/workspaces/command-center/support/templates/regtpl"},
            "dept-skills":{"workspace":"$D/outside/reg/skills"},
            "dept-onboarding":{"workspace":"$D/outside/reg/onboarding"},
            "dept-hidden":{"workspace":"$D/outside/.hidden-reg/agent"},
            "dept-ext":{"workspace":"$D/outside/ext"}},
 "list":[{"id":"legacy","workspace":"$D/outside/legacy"}]}}
JSON
}

# the folders that must come out of a roll byte-identical (printed, one per line)
trap_dirs() {
  local D="$1" OCR="$1/home/.openclaw" WS="$1/home/.openclaw/workspace"
  local ZHC1="$1/home/Downloads/openclaw-master-files/zero-human-company"
  echo "$WS/departments/sales.bak-20261001"; echo "$WS/departments/.floor-backups/sales"
  echo "$OCR/workspaces/command-center/support.bak-x"; echo "$OCR/workspaces/departments-archive/old"
  echo "$OCR/workspaces/command-center/support/skills/vendored"; echo "$WS/departments/sales/node_modules/pkg"
  echo "$OCR/workspaces/onboarding"; echo "$WS/departments/sales/templates/x"; echo "$OCR/workspaces/fleet-refresh/y"
  echo "$OCR/workspaces/codex-home/.tmp/z"; echo "$OCR/workspaces/codex-home"
  echo "$ZHC1/other-co/departments/sales/closer"
}
trap_files() {
  local t
  for t in $(trap_dirs "$1"); do echo "$t/AGENTS.md"; echo "$t/IDENTITY.md"; echo "$t/TOOLS.md"; done
  local ZHC1="$1/home/Downloads/openclaw-master-files/zero-human-company"
  echo "$ZHC1/other-co/departments/sales/AGENTS.md"; echo "$ZHC1/other-co/departments/sales/IDENTITY.md"
  echo "$ZHC1/other-co/departments/sales/closer/USER.md"
}

# run_fn FNFILE BOXDIR -> run the extracted function once; rc in BOXDIR.rc
run_fn() {
  local FN="$1" D="$2"
  ( set +e
    note() { echo "  $*"; }; warn() { echo "  WARN $*" >&2; }
    # shellcheck disable=SC1090
    . "$FN"
    export HOME="$D/home"
    # shellcheck disable=SC2034  # read by the sourced function (install.sh form)
    OC_JSON="$HOME/.openclaw/openclaw.json"
    # shellcheck disable=SC2034
    OC_WORKSPACE_DEFAULT="$HOME/.openclaw/workspace"
    link_shared_core_files "$HOME/.openclaw/workspace"
    echo "$?" > "$D.rc" ) > "$D.run.log" 2>&1
}

# battery FNFILE BOXDIR OUT [quick] -> the behavioural battery, appending
# "ok <name>" / "bad <name>" lines to OUT. "quick" stops after one roll (the
# mutation proof uses it because each function run costs seconds).
battery() {
  local FN="$1" D="$2" OUT="$3" MODE="${4:-full}"
  local OCR="$D/home/.openclaw" WS="$D/home/.openclaw/workspace" f
  local ZHC1="$D/home/Downloads/openclaw-master-files/zero-human-company"
  local ZHC0="$D/outside/co-root/acme-co" ZHC3="$WS/zero-human-company/acme-co"
  local A="$WS/AGENTS.md" T="$WS/TOOLS.md" U="$WS/USER.md"
  local META="$D.meta"; rm -rf "$META"; mkdir -p "$META"
  : > "$OUT"

  build_box "$D"
  local before_traps="$META/traps.before" after_traps="$META/traps.after"
  trap_files "$D" | while IFS= read -r p; do echo "$(_sha "$p") $p"; done > "$before_traps"

  run_fn "$FN" "$D"

  # S1 registered + command-center workspaces end identical to master
  local w ws_ok=0
  for w in "$WS/departments/sales" "$WS/departments/legal" "$OCR/workspaces/command-center/support" \
           "$D/outside/ext" "$D/outside/dflt" "$D/outside/legacy"; do
    for f in AGENTS.md TOOLS.md USER.md; do
      cmp -s "$WS/$f" "$w/$f" || { ws_ok=1; echo "   S1 differs: $w/$f" >> "$META/detail.log"; }
    done
  done
  # a command-center folder found by the scan only (not registered) has an AGENTS.md: refreshed, nothing added
  cmp -s "$A" "$OCR/workspaces/command-center/billing/AGENTS.md" || { ws_ok=1; echo "   S1 differs: command-center/billing/AGENTS.md" >> "$META/detail.log"; }
  [ ! -e "$OCR/workspaces/command-center/billing/TOOLS.md" ] && [ ! -e "$OCR/workspaces/command-center/billing/USER.md" ] \
    || { ws_ok=1; echo "   S1 scan-only command-center/billing gained a file" >> "$META/detail.log"; }
  emit "$OUT" "$ws_ok" "S1 registered/command-center/defaults/legacy workspaces identical to master"

  # S2 a registered workspace missing files got them (entries outside scan roots, defaults)
  local cr=0
  for f in AGENTS.md TOOLS.md USER.md; do
    [ -f "$D/outside/ext/$f" ] && [ ! -L "$D/outside/ext/$f" ] || cr=1
    [ -f "$D/outside/dflt/$f" ] && [ ! -L "$D/outside/dflt/$f" ] || cr=1
  done
  [ -f "$WS/departments/sales/TOOLS.md" ] || cr=1
  emit "$OUT" "$cr" "S2 registered workspaces missing a core file were given the master copy"

  # S3 unique blocks preserved in the department's OWN IDENTITY.md
  local pr=0
  grep -qF 'SALES-ONLY RULE: always cc the closer' "$WS/departments/sales/IDENTITY.md" || pr=1
  grep -qF 'PRESERVED FROM sales AGENTS.md' "$WS/departments/sales/IDENTITY.md" || pr=1
  grep -qF 'SUPPORT-ONLY RULE: tag every ticket' "$OCR/workspaces/command-center/support/IDENTITY.md" || pr=1
  grep -qF 'LEGACY-ONLY RULE: page the owner' "$D/outside/legacy/IDENTITY.md" || pr=1
  grep -qF 'OPS-ONLY RULE: close the loop' "$ZHC0/departments/ops/IDENTITY.md" || pr=1
  grep -qF '# sales identity' "$WS/departments/sales/IDENTITY.md" || pr=1
  emit "$OUT" "$pr" "S3 department-specific content preserved in that department's IDENTITY.md"

  # S4 traps untouched (backup, hidden, archive, node_modules, skills, codex-home, other company)
  local tr=0
  trap_files "$D" | while IFS= read -r p; do echo "$(_sha "$p") $p"; done > "$after_traps"
  cmp -s "$before_traps" "$after_traps" || { tr=1; diff "$before_traps" "$after_traps" | sed 's/^/   S4 /' >> "$META/detail.log"; }
  emit "$OUT" "$tr" "S4 backup, hidden, archive, node_modules, codex-home, skill/template and other-company trees untouched"

  # S5 role folders: no AGENTS.md ever, TOOLS.md kept in step, unregistered stays empty
  local rf=0
  [ ! -e "$WS/departments/sales/closer/AGENTS.md" ] || rf=1
  [ ! -e "$WS/departments/sales/setter/AGENTS.md" ] || rf=1
  cmp -s "$T" "$WS/departments/sales/closer/TOOLS.md" || rf=1
  cmp -s "$T" "$WS/departments/sales/setter/TOOLS.md" || rf=1
  cmp -s "$U" "$WS/departments/sales/setter/USER.md" || rf=1
  [ ! -e "$OCR/workspaces/orphan/AGENTS.md" ] && [ ! -e "$OCR/workspaces/orphan/TOOLS.md" ] \
    && [ ! -e "$OCR/workspaces/orphan/USER.md" ] || rf=1
  emit "$OUT" "$rf" "S5 role folders keep no AGENTS.md (U053); unregistered folders gain no file"

  # S6 the relic became a real file; the ONLY symlink left is the fixture's symlinked scan root
  local sl=0
  [ "$(find "$D" -type l | wc -l | tr -d ' ')" = "1" ] || sl=1
  [ -L "$WS/agents" ] || sl=1
  [ -f "$WS/departments/legal/AGENTS.md" ] && [ ! -L "$WS/departments/legal/AGENTS.md" ] && cmp -s "$A" "$WS/departments/legal/AGENTS.md" || sl=1
  emit "$OUT" "$sl" "S6 symlink relic migrated to a real file; no symlink was created"

  # S10 this box's own company tree, three places, down to the role folders
  local co=0
  cmp -s "$A" "$ZHC0/departments/ops/AGENTS.md" || { co=1; echo "   S10 ops/AGENTS.md" >> "$META/detail.log"; }
  cmp -s "$T" "$ZHC0/departments/ops/planner/TOOLS.md" || { co=1; echo "   S10 planner/TOOLS.md" >> "$META/detail.log"; }
  cmp -s "$A" "$ZHC0/departments/ops/planner/AGENTS.md" || { co=1; echo "   S10 planner/AGENTS.md" >> "$META/detail.log"; }
  cmp -s "$T" "$ZHC1/acme-co/departments/marketing/copywriter/TOOLS.md" || { co=1; echo "   S10 copywriter/TOOLS.md" >> "$META/detail.log"; }
  cmp -s "$U" "$ZHC3/departments/finance/analyst/USER.md" || { co=1; echo "   S10 analyst/USER.md" >> "$META/detail.log"; }
  [ ! -e "$ZHC1/acme-co/departments/marketing/copywriter/AGENTS.md" ] && [ ! -e "$ZHC3/departments/finance/analyst/AGENTS.md" ] \
    && [ ! -e "$ZHC1/acme-co/departments/marketing/copywriter/USER.md" ] || { co=1; echo "   S10 role folder gained a file" >> "$META/detail.log"; }
  [ "$(cat "$ZHC1/other-co/departments/sales/AGENTS.md")" = "OTHER COMPANY dept agents" ] || co=1
  emit "$OUT" "$co" "S10 this box's own company tree synced down to role folders; another company's tree untouched"

  # S13 a symlinked scan root (<workspace>/agents -> elsewhere) is walked
  cmp -s "$A" "$D/outside/agents-store/helper/AGENTS.md"; emit "$OUT" "$?" "S13 symlinked scan root is walked"

  # S14 registered workspaces are never filtered by name
  local nm=0
  for w in "$D/outside/reg/skills" "$D/outside/reg/onboarding" "$D/outside/.hidden-reg/agent" \
           "$OCR/workspaces/command-center/support/templates/regtpl"; do
    for f in AGENTS.md TOOLS.md USER.md; do
      cmp -s "$WS/$f" "$w/$f" || { nm=1; echo "   S14 $w/$f" >> "$META/detail.log"; }
    done
  done
  emit "$OUT" "$nm" "S14 registered workspaces (skills, onboarding, hidden, inside templates/) are never filtered by name"

  # S15 an unregistered real department NAMED like a vendored tree is synced
  local rd=0 n
  for n in templates onboarding skills; do
    cmp -s "$A" "$OCR/workspaces/command-center/$n/AGENTS.md" || { rd=1; echo "   S15 command-center/$n" >> "$META/detail.log"; }
    [ ! -e "$OCR/workspaces/command-center/$n/TOOLS.md" ] || rd=1
  done
  emit "$OUT" "$rd" "S15 real departments named templates / onboarding / skills (outside an agent workspace) are synced"

  [ "$MODE" = quick ] && return 0

  # S7 idempotent second run
  snap "$D" > "$META/snap.1"
  run_fn "$FN" "$D"
  snap "$D" > "$META/snap.2"
  local id=0
  cmp -s "$META/snap.1" "$META/snap.2" || { id=1; diff "$META/snap.1" "$META/snap.2" >> "$META/detail.log"; }
  emit "$OUT" "$id" "S7 second run changes nothing (no rewrite, no new backup, no new file)"

  # S8 fail-open: empty master USER.md copies nothing, destroys nothing
  : > "$WS/USER.md"
  printf 'ext user keep me\n' > "$D/outside/ext/USER.md"
  printf 'dflt user keep me\n' > "$D/outside/dflt/USER.md"
  rm -f "$WS/departments/sales/USER.md"
  run_fn "$FN" "$D"
  local fo=0
  [ "$(cat "$D/outside/ext/USER.md")" = "ext user keep me" ] || fo=1
  [ "$(cat "$D/outside/dflt/USER.md")" = "dflt user keep me" ] || fo=1
  [ ! -e "$WS/departments/sales/USER.md" ] || fo=1
  emit "$OUT" "$fo" "S8 empty master file is never copied over anything (fail-open)"
}

# drift_check FNFILE BOXDIR OUT -> S11: a later, different unique block is appended; a repeat is not
drift_check() {
  local FN="$1" D="$2" OUT="$3" WS="$2/home/.openclaw/workspace"
  local S="$WS/departments/sales" r=0
  : > "$OUT"
  build_box "$D"
  run_fn "$FN" "$D"
  { cat "$WS/AGENTS.md"; printf '\nSECOND-DRIFT RULE: use the new CRM\n'; } > "$S/AGENTS.md"
  run_fn "$FN" "$D"
  [ "$(grep -cF 'SECOND-DRIFT RULE: use the new CRM' "$S/IDENTITY.md")" = 1 ] || { r=1; echo "   S11 second drift not appended" >&2; }
  [ "$(grep -cF 'SALES-ONLY RULE: always cc the closer' "$S/IDENTITY.md")" = 1 ] || r=1
  { cat "$WS/AGENTS.md"; printf '\nSECOND-DRIFT RULE: use the new CRM\n'; } > "$S/AGENTS.md"
  run_fn "$FN" "$D"
  [ "$(grep -cF 'SECOND-DRIFT RULE: use the new CRM' "$S/IDENTITY.md")" = 1 ] || { r=1; echo "   S11 repeat duplicated" >&2; }
  [ "$(grep -cF 'SALES-ONLY RULE: always cc the closer' "$S/IDENTITY.md")" = 1 ] || r=1
  cmp -s "$WS/AGENTS.md" "$S/AGENTS.md" || r=1
  emit "$OUT" "$r" "S11 a later different unique block is appended to IDENTITY.md; a repeated block is not duplicated"
}

# create_fail_check FNFILE BOXDIR OUT -> S12
create_fail_check() {
  local FN="$1" D="$2" OUT="$3" WS="$2/home/.openclaw/workspace" r=0
  : > "$OUT"
  build_box "$D"
  if [ "$(id -u)" = 0 ]; then echo "skip S12 (root can write into a read-only directory)" >> "$OUT"; return 0; fi
  chmod 555 "$D/outside/ext"
  run_fn "$FN" "$D"
  chmod 755 "$D/outside/ext"
  [ "$(cat "$D.rc" 2>/dev/null)" = 0 ] || { r=1; echo "   S12 function returned non-zero" >&2; }
  grep -q 'verified create FAILED' "$D.run.log" || { r=1; echo "   S12 no loud WARN" >&2; }
  grep -q 'create-failed=3' "$D.run.log" || { r=1; echo "   S12 summary does not count the 3 failed creates" >&2; }
  [ ! -e "$D/outside/ext/AGENTS.md" ] || { r=1; echo "   S12 the directory was not actually unwritable" >&2; }
  cmp -s "$WS/AGENTS.md" "$D/outside/dflt/AGENTS.md" || { r=1; echo "   S12 other workspaces were not synced" >&2; }
  emit "$OUT" "$r" "S12 a create failure in a workspace that never had the file warns loudly but does not fail the roll"
}

# scope_check FNFILE BOXDIR OUT -> S16: no slug, no company tree; COMPANY_SLUG scopes the scan
scope_check() {
  local FN="$1" D="$2" OUT="$3" WS="$2/home/.openclaw/workspace" r=0
  local ZHC1="$2/home/Downloads/openclaw-master-files/zero-human-company"
  local ZHC0="$2/outside/co-root/acme-co" ZHC3="$2/home/.openclaw/workspace/zero-human-company/acme-co"
  : > "$OUT"
  build_box "$D"
  rm -f "$WS/.workforce-build-state.json"
  run_fn "$FN" "$D"
  [ "$(cat "$ZHC1/acme-co/departments/marketing/copywriter/TOOLS.md")" = "copywriter tools drift" ] || { r=1; echo "   S16 company tree read without a slug" >&2; }
  [ "$(cat "$ZHC0/departments/ops/planner/TOOLS.md")" = "planner tools drift" ] || r=1
  [ "$(cat "$ZHC3/departments/finance/analyst/USER.md")" = "analyst user drift" ] || r=1
  [ "$(cat "$ZHC1/other-co/departments/sales/AGENTS.md")" = "OTHER COMPANY dept agents" ] || r=1
  COMPANY_SLUG=acme-co run_fn "$FN" "$D"
  cmp -s "$WS/TOOLS.md" "$ZHC1/acme-co/departments/marketing/copywriter/TOOLS.md" || { r=1; echo "   S16 COMPANY_SLUG did not scope the scan" >&2; }
  cmp -s "$WS/USER.md" "$ZHC3/departments/finance/analyst/USER.md" || r=1
  [ "$(cat "$ZHC1/other-co/departments/sales/AGENTS.md")" = "OTHER COMPANY dept agents" ] || { r=1; echo "   S16 another company was touched" >&2; }
  [ "$(cat "$ZHC1/other-co/departments/sales/closer/USER.md")" = "OTHER COMPANY user" ] || r=1
  emit "$OUT" "$r" "S16 no company slug: no company tree is read; COMPANY_SLUG scopes the scan to that company only"
}

# extract the function out of SRC into DEST
extract_fn() {
  awk '/^link_shared_core_files\(\) \{/{f=1} f{print} f && /^\}$/{exit}' "$ROOT/$1" > "$2"
}

# report OUT LABEL BOXDIR -> print each line of OUT as ok/FAIL
report() {
  local OUT="$1" LBL="$2" D="$3" line
  while IFS= read -r line; do
    case "$line" in
      ok\ *)   ok "$LBL: ${line#ok }" ;;
      bad\ *)  bad "$LBL: ${line#bad }"; [ -f "$D.meta/detail.log" ] && sed 's/^/        /' "$D.meta/detail.log" ;;
      skip\ *) skp "$LBL: ${line#skip }" ;;
    esac
  done < "$OUT"
}

# ------------------------------------------------------------------------------
hdr "behavioural battery, the REAL function from each script"
for SRC in install.sh update-skills.sh; do
  LBL="${SRC%.sh}"
  FN="$SANDBOX/fn-$LBL.sh"
  extract_fn "$SRC" "$FN"
  if ! bash -n "$FN" 2>/dev/null || ! grep -q 'LSC-CANDIDATES-BEGIN' "$FN"; then
    bad "$LBL: extracted function missing or does not parse (fix absent from $SRC?)"; continue
  fi
  D="$SANDBOX/box-$LBL"; OUT="$SANDBOX/out-$LBL.txt"
  battery "$FN" "$D" "$OUT"; report "$OUT" "$LBL" "$D"
  for CHK in drift_check create_fail_check scope_check; do
    D2="$SANDBOX/box-$LBL-$CHK"; OUT2="$SANDBOX/out-$LBL-$CHK.txt"
    $CHK "$FN" "$D2" "$OUT2" 2>"$SANDBOX/err-$LBL-$CHK.txt"
    report "$OUT2" "$LBL" "$D2"
    grep -q 'bad ' "$OUT2" && sed 's/^/        /' "$SANDBOX/err-$LBL-$CHK.txt"
  done
done

# ------------------------------------------------------------------------------
hdr "S9 real role-library TOOLS.md files: master wins, unique content kept in IDENTITY.md"
FN="$SANDBOX/fn-update-skills.sh"
for DEPT in presentations rescue-rangers; do
  TPL="$ROOT/23-ai-workforce-blueprint/templates/role-library/$DEPT/TOOLS.md"
  if [ ! -s "$TPL" ]; then bad "S9 $DEPT: template TOOLS.md missing at $TPL"; continue; fi
  D="$SANDBOX/s9-$DEPT"; build_box "$D"
  WS="$D/home/.openclaw/workspace"
  mkdir -p "$WS/departments/$DEPT"
  cp "$TPL" "$WS/departments/$DEPT/TOOLS.md"
  printf '# %s identity\n' "$DEPT" > "$WS/departments/$DEPT/IDENTITY.md"
  run_fn "$FN" "$D"
  R=0
  cmp -s "$WS/TOOLS.md" "$WS/departments/$DEPT/TOOLS.md" || { R=1; echo "   $DEPT TOOLS.md not master" >&2; }
  # every blank-line-delimited block of the template that the master lacks must be in IDENTITY.md
  MISSING="$(TPL="$TPL" CANON="$WS/TOOLS.md" IDF="$WS/departments/$DEPT/IDENTITY.md" python3 - <<'PYEOF'
import os
canon = open(os.environ["CANON"], encoding="utf-8", errors="replace").read()
idt = open(os.environ["IDF"], encoding="utf-8", errors="replace").read()
blocks, cur = [], []
for line in open(os.environ["TPL"], encoding="utf-8", errors="replace").read().splitlines():
    if line.strip() == "":
        if cur: blocks.append("\n".join(cur)); cur = []
    else:
        cur.append(line)
if cur: blocks.append("\n".join(cur))
unique = [b for b in blocks if b.strip() and b.strip() not in canon]
lost = [b for b in unique if b not in idt]
print(len(unique), len(lost))
PYEOF
)"
  UNIQ="${MISSING% *}"; LOST="${MISSING#* }"
  if [ "$R" = 0 ] && [ "${UNIQ:-0}" -gt 0 ] && [ "${LOST:-1}" = "0" ]; then
    ok "S9 $DEPT: TOOLS.md == master, all $UNIQ unique blocks preserved in IDENTITY.md"
  else
    bad "S9 $DEPT: tools-is-master=$([ $R = 0 ] && echo yes || echo no) unique=$UNIQ lost=$LOST"
  fi
  cp "$WS/departments/$DEPT/IDENTITY.md" "$D.id.1"
  run_fn "$FN" "$D"
  cmp -s "$D.id.1" "$WS/departments/$DEPT/IDENTITY.md" && ok "S9 $DEPT: IDENTITY.md stable on the next roll" \
    || bad "S9 $DEPT: IDENTITY.md changed on a second roll"
done

# ------------------------------------------------------------------------------
hdr "P1/P2 install.sh, update-skills.sh and QC 9.9 stay in step"
blk() { sed -n '/LSC-CANDIDATES-BEGIN/,/LSC-CANDIDATES-END/p' "$ROOT/$1"; }
if [ -n "$(blk install.sh)" ] && [ "$(blk install.sh)" = "$(blk update-skills.sh)" ]; then
  ok "P1 candidate block is byte-identical in install.sh and update-skills.sh"
else
  bad "P1 candidate block differs between install.sh and update-skills.sh (or is missing)"
fi
pyfn() { sed -n '/# >>> LSC-PY-BEGIN/,/# <<< LSC-PY-END/p' "$ROOT/$1"; }
if [ -n "$(pyfn update-skills.sh)" ] && [ "$(pyfn install.sh)" = "$(pyfn update-skills.sh)" ] \
   && [ "$(pyfn scripts/qc-system-integrity.sh)" = "$(pyfn update-skills.sh)" ]; then
  ok "P2 the python scan function (skip rules, company roots) is byte-identical in install.sh, update-skills.sh and QC 9.9"
else
  bad "P2 the python scan function differs between install.sh, update-skills.sh and QC 9.9 (or is missing)"
fi

# ------------------------------------------------------------------------------
hdr "Q1 QC check 9.9 covers entries, command-center and the company tree; red on drift, green after sync"
QCPY="$SANDBOX/qc99.py"
awk '/^UNIFY_BAD=\$\(OCJSON=/{f=1; next} f && /^PYEOF$/{exit} f{print}' "$ROOT/scripts/qc-system-integrity.sh" > "$QCPY"
if python3 -c "import ast; ast.parse(open('$QCPY').read())" 2>/dev/null && grep -q 'LSC-PY-BEGIN' "$QCPY"; then
  D="$SANDBOX/qc-box"; build_box "$D"
  qc_run() { OCJSON="$D/home/.openclaw/openclaw.json" HOME="$D/home" python3 "${1:-$QCPY}" 2>&1; }
  qc_first() { qc_run "${1:-$QCPY}" | head -1; }
  OCR="$D/home/.openclaw"; WS="$OCR/workspace"
  ZHC1="$D/home/Downloads/openclaw-master-files/zero-human-company"
  N0="$(qc_first)"
  [ "${N0:-0}" -gt 0 ] 2>/dev/null && ok "Q1 unsynced fixture box: QC 9.9 is red ($N0 problems)" || bad "Q1 unsynced fixture box was not flagged (count=$N0)"
  run_fn "$SANDBOX/fn-update-skills.sh" "$D"
  [ "$(qc_first)" = "0" ] && ok "Q1 synced box: QC 9.9 is green (backup, vendored and other-company trees, which differ from master, are ignored)" \
    || { bad "Q1 synced box: QC 9.9 still red"; qc_run | sed 's/^/        /'; }
  # one drift at a time, each in a place the old check never looked
  printf 'x\n' >> "$OCR/workspaces/command-center/support/AGENTS.md"
  [ "$(qc_first)" = "1" ] && qc_run | grep -q 'command-center/support/AGENTS.md' \
    && ok "Q1 drift in a command-center workspace is caught" || bad "Q1 command-center drift not caught"
  run_fn "$SANDBOX/fn-update-skills.sh" "$D"
  rm -f "$D/outside/ext/USER.md"
  [ "$(qc_first)" = "1" ] && qc_run | grep -q 'outside/ext/USER.md is MISSING' \
    && ok "Q1 a registered (agents.entries) workspace missing a core file is caught" || bad "Q1 missing file in entries workspace not caught"
  run_fn "$SANDBOX/fn-update-skills.sh" "$D"
  printf 'x\n' >> "$D/outside/ext/TOOLS.md"
  [ "$(qc_first)" = "1" ] && ok "Q1 drift in an agents.entries workspace outside every scan root is caught" || bad "Q1 entries drift not caught"
  run_fn "$SANDBOX/fn-update-skills.sh" "$D"
  printf 'x\n' >> "$ZHC1/acme-co/departments/marketing/copywriter/TOOLS.md"
  [ "$(qc_first)" = "1" ] && qc_run | grep -q 'copywriter/TOOLS.md' \
    && ok "Q1 drift in a role folder of this box's company tree is caught" || bad "Q1 company-tree role-folder drift not caught"
  # mutations: a QC that ignores agents.entries, or the company tree, must go blind to exactly that drift
  sed 's/for e in list(ent.values()) + lst + \[dfl\]:/for e in lst:/' "$QCPY" > "$SANDBOX/qc99.mut1.py"
  sed 's/^    if slug:$/    if False:/' "$QCPY" > "$SANDBOX/qc99.mut2.py"
  run_fn "$SANDBOX/fn-update-skills.sh" "$D"
  printf 'x\n' >> "$D/outside/ext/TOOLS.md"
  if cmp -s "$QCPY" "$SANDBOX/qc99.mut1.py"; then bad "M qc-no-entries: mutation did not apply"
  elif [ "$(qc_first "$SANDBOX/qc99.mut1.py")" = "0" ]; then ok "M qc-no-entries: a QC without agents.entries coverage misses that drift (so Q1 is not vacuous)"
  else bad "M qc-no-entries: mutated QC still caught the drift"; fi
  run_fn "$SANDBOX/fn-update-skills.sh" "$D"
  printf 'x\n' >> "$ZHC1/acme-co/departments/marketing/copywriter/TOOLS.md"
  if cmp -s "$QCPY" "$SANDBOX/qc99.mut2.py"; then bad "M qc-no-company: mutation did not apply"
  elif [ "$(qc_first "$SANDBOX/qc99.mut2.py")" = "0" ]; then ok "M qc-no-company: a QC without the company tree misses that drift (so Q1 is not vacuous)"
  else bad "M qc-no-company: mutated QC still caught the drift"; fi
else
  bad "Q1 could not extract the QC 9.9 python block"
fi

# ------------------------------------------------------------------------------
hdr "M* mutation proof: break each rule in a COPY, the matching check must go red"
# mutate NAME SEDSCRIPT RUNNER WANT-FRAGMENT-OF-A-BAD-LINE
mutate() {
  local NAME="$1" SEDS="$2" RUNNER="$3" WANT="$4"
  local M="$SANDBOX/mut-$NAME.sh"
  sed "$SEDS" "$SANDBOX/fn-update-skills.sh" > "$M"
  if cmp -s "$M" "$SANDBOX/fn-update-skills.sh"; then bad "M $NAME: mutation did not apply (pattern drifted)"; return; fi
  bash -n "$M" 2>/dev/null || { bad "M $NAME: mutated copy does not parse"; return; }
  local D="$SANDBOX/mbox-$NAME" OUT="$SANDBOX/mout-$NAME.txt"
  case "$RUNNER" in
    battery) battery "$M" "$D" "$OUT" quick ;;
    *)       "$RUNNER" "$M" "$D" "$OUT" 2>/dev/null ;;
  esac
  if grep -q '^skip ' "$OUT"; then skp "M $NAME: '$WANT' not exercised here (see skip above)"
  elif grep -q "^bad .*$WANT" "$OUT"; then ok "M $NAME: '$WANT' went red as it must"
  else bad "M $NAME: '$WANT' stayed green (rule is not actually tested)"; fi
}
mutate no-bak-prune    's/"\*\.bak\*", //; s/"\*\.backup\*", //; s/SKIP_ANY = (".\*", /SKIP_ANY = (/' battery "S4"
mutate no-skill-prune  's/SKIP_IN_AGENT = ("skills", /SKIP_IN_AGENT = (/'                               battery "S4"
mutate no-nm-prune     's/"node_modules", "departments-archive"/"departments-archive"/'                  battery "S4"
mutate no-codex-top    's/SKIP_TOP = ("onboarding", "fleet-refresh", "codex-home")/SKIP_TOP = ("onboarding", "fleet-refresh")/' battery "S4"
mutate name-only-prune 's/SKIP_ANY = (".\*", /SKIP_ANY = (".*", "templates", "onboarding", "skills", /'   battery "S15"
mutate no-symlink-root 's/    if not os.path.isdir(root):/    if not os.path.isdir(root) or os.path.islink(root):/' battery "S13"
mutate no-entries      's/ent = ag.get("entries") if isinstance(ag.get("entries"), dict) else {}/ent = {}/' battery "S1"
mutate no-defaults     's/for e in list(ent.values()) + lst + \[dfl\]:/for e in list(ent.values()) + lst:/' battery "S1"
mutate no-create       's/\[ "\$W_IS_REG" = "yes" \] && \[ ! -e/[ "no" = "yes" ] \&\& [ ! -e/'            battery "S2"
mutate role-gets-agents 's/\[ "\$W_IS_ROLE" != "yes" \]; }; then/true; }; then/'                        battery "S5"
mutate no-preserve     's/unique = \[b for b in blocks if b.strip() and b.strip() not in canon_text\]/unique = []/' battery "S3"
mutate name-filters-registered 's/reg.append(os.path.expanduser(ws.strip()))/(reg.append(os.path.expanduser(ws.strip())) if not _lsc_match(os.path.basename(ws.strip()), SKIP_IN_AGENT + SKIP_ANY) else None)/' battery "S14"
mutate no-company-root0 's/if isinstance(croot, str) and os.path.isabs(croot)/if False and isinstance(croot, str)/' battery "S10"
mutate no-company-root1 's/^    if slug:$/    if False:/'                                           battery "S10"
mutate all-companies   's/os.path.join(mf, "zero-human-company", slug, "departments")/os.path.join(mf, "zero-human-company")/' battery "S4"
mutate old-preserve-guard 's/    if h in done or b in id_text:/    if h in done or b in id_text or "PRESERVED FROM" in id_text:/' drift_check "S11"
mutate create-fail-blocks 's/CREATE_FAILED=\$((CREATE_FAILED + 1))/FAILED=$((FAILED + 1))/'           create_fail_check "S12"
mutate slug-glob-fallback 's/^    if slug:$/    if True:/; s/os.path.join(mf, "zero-human-company", slug, "departments")/os.path.join(mf, "zero-human-company")/' scope_check "S16"

echo ""
echo "=== shared-core-entries-sync: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
