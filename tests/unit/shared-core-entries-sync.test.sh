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
# and vendored skill folders it must never rewrite and (b) left a registered
# agent's missing AGENTS.md / USER.md absent forever. Measured on a real client
# box (OpenClaw 2026.10.5, 49 agents in agents.entries): 718 AGENTS.md copies
# (669 identical), 830 TOOLS.md, 785 USER.md, spread over department role
# folders, command-center folders, <dept>.bak-* and .floor-backups trees.
#
# WHAT THIS PROVES (behavioral: it runs the REAL function extracted from BOTH
# install.sh and update-skills.sh, against a fixture box):
#   S1  every registered workspace (agents.entries, agents.list, agents.defaults)
#       ends byte-identical to the master, including the command-center folder
#       and workspaces that sit outside every scan root
#   S2  a registered workspace missing a core file gets it created
#   S3  a department's unique AGENTS.md block survives in that department's
#       own IDENTITY.md
#   S4  backup trees, hidden dirs, departments-archive, node_modules and
#       vendored skill / onboarding / template trees are left byte-untouched
#   S5  a department ROLE folder never gains an AGENTS.md (U053) but is kept in
#       step on TOOLS.md / USER.md; an unregistered folder never gains a file
#   S6  a symlink relic is migrated to a real file; no symlink exists after
#   S7  a second run changes nothing (no rewrite, no new backup)
#   S8  fail-open: an empty master file is never copied over anything
#   S9  the two department-specific role-library TOOLS.md files (presentations,
#       rescue-rangers) end identical to the master with every one of their
#       unique blocks preserved in the department's IDENTITY.md
#   P1  install.sh and update-skills.sh carry a byte-identical candidate block
#   P2  the skip list is the same in both scripts and in QC check 9.9
#   Q1  QC check 9.9 FAILS on the drifted fixture (it sees entries + the
#       command-center folder + a missing registered file) and PASSES after sync
#   M*  MUTATION PROOF: each rule above is broken in a COPY of the function and
#       the battery must go red, so this test cannot pass vacuously
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
hdr() { printf '\n== %s ==\n' "$1"; }

if [ -d /data/.openclaw ]; then
  echo "SKIP: /data/.openclaw exists on this host, so the function would read the real box (not hermetic)"
  exit 0
fi

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

_sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

# snap DIR -> one line per file/symlink: "<sha> <relpath>" or "L <relpath>"
snap() {
  ( cd "$1" && find . \( -type f -o -type l \) | LC_ALL=C sort | while IFS= read -r p; do
      if [ -L "$p" ]; then echo "L $p"; else echo "$(_sha "$p") $p"; fi
    done )
}

# --------------------------------------------------------------------------
# Fixture box. Layout (every path lives under $1):
#   home/.openclaw/openclaw.json    agents.entries + agents.list + defaults
#   home/.openclaw/workspace        the MASTER (canonical) workspace
# --------------------------------------------------------------------------
build_box() {
  local D="$1"
  rm -rf "$D"; mkdir -p "$D/home/.openclaw"
  local OCR="$D/home/.openclaw" WS="$D/home/.openclaw/workspace"
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

  # registered, outside every scan root, empty: must be CREATED
  mkdir -p "$D/outside/ext" "$D/outside/dflt" "$D/outside/legacy"
  # legacy agents.list agent with a unique block
  printf 'MASTER AGENTS\n\nLEGACY-ONLY RULE: page the owner\n' > "$D/outside/legacy/AGENTS.md"
  printf '# legacy\n' > "$D/outside/legacy/IDENTITY.md"

  # unregistered folder with only IDENTITY.md: must stay without core files
  mkdir -p "$OCR/workspaces/orphan"
  printf '# orphan\n' > "$OCR/workspaces/orphan/IDENTITY.md"

  # ---- TRAPS: none of these may be touched ----
  mkdir -p "$WS/departments/sales.bak-20261001" "$WS/departments/.floor-backups/sales" \
           "$OCR/workspaces/command-center/support.bak-x" "$OCR/workspaces/departments-archive/old" \
           "$OCR/workspaces/command-center/support/skills/vendored" "$WS/departments/sales/node_modules/pkg" \
           "$OCR/workspaces/onboarding" "$WS/departments/sales/templates/x" "$OCR/workspaces/fleet-refresh/y" \
           "$OCR/workspaces/codex-home/.tmp/z"
  local t
  for t in "$WS/departments/sales.bak-20261001" "$WS/departments/.floor-backups/sales" \
           "$OCR/workspaces/command-center/support.bak-x" "$OCR/workspaces/departments-archive/old" \
           "$OCR/workspaces/command-center/support/skills/vendored" "$WS/departments/sales/node_modules/pkg" \
           "$OCR/workspaces/onboarding" "$WS/departments/sales/templates/x" "$OCR/workspaces/fleet-refresh/y" \
           "$OCR/workspaces/codex-home/.tmp/z"; do
    printf 'TRAP agents file that belongs to something else\n' > "$t/AGENTS.md"
    printf '# trap identity\n' > "$t/IDENTITY.md"
    printf 'TRAP tools\n' > "$t/TOOLS.md"
  done

  cat > "$OCR/openclaw.json" <<JSON
{"agents":{"defaults":{"workspace":"$D/outside/dflt"},
 "entries":{"main":{"workspace":"$WS"},
            "dept-sales":{"workspace":"$WS/departments/sales"},
            "dept-setter":{"workspace":"$WS/departments/sales/setter"},
            "dept-legal":{"workspace":"$WS/departments/legal"},
            "dept-support":{"workspace":"$OCR/workspaces/command-center/support"},
            "dept-ext":{"workspace":"$D/outside/ext"}},
 "list":[{"id":"legacy","workspace":"$D/outside/legacy"}]}}
JSON
}

# trap list (for the untouched assertions)
trap_files() {
  local D="$1" OCR="$1/home/.openclaw" WS="$1/home/.openclaw/workspace"
  local t
  for t in "$WS/departments/sales.bak-20261001" "$WS/departments/.floor-backups/sales" \
           "$OCR/workspaces/command-center/support.bak-x" "$OCR/workspaces/departments-archive/old" \
           "$OCR/workspaces/command-center/support/skills/vendored" "$WS/departments/sales/node_modules/pkg" \
           "$OCR/workspaces/onboarding" "$WS/departments/sales/templates/x" "$OCR/workspaces/fleet-refresh/y" \
           "$OCR/workspaces/codex-home/.tmp/z"; do
    echo "$t/AGENTS.md"; echo "$t/IDENTITY.md"; echo "$t/TOOLS.md"
  done
}

# run_fn FNFILE BOXDIR [UNIFY_BAK_KEEP...] -> run the extracted function once
run_fn() {
  local FN="$1" D="$2"
  ( set +e
    note() { :; }; warn() { :; }
    # shellcheck disable=SC1090
    . "$FN"
    export HOME="$D/home"
    # shellcheck disable=SC2034  # read by the sourced function (install.sh form)
    OC_JSON="$HOME/.openclaw/openclaw.json"
    # shellcheck disable=SC2034
    OC_WORKSPACE_DEFAULT="$HOME/.openclaw/workspace"
    link_shared_core_files "$HOME/.openclaw/workspace" ) > "$D.run.log" 2>&1
}

# battery FNFILE BOXDIR OUT [quick] -> run the behavioural battery, appending
# "ok <name>" / "bad <name>" lines to OUT. "quick" stops after one roll (S1-S6);
# the mutation proof uses it because each function run costs seconds.
battery() {
  local FN="$1" D="$2" OUT="$3" MODE="${4:-full}"
  local OCR="$D/home/.openclaw" WS="$D/home/.openclaw/workspace" f
  local A="$WS/AGENTS.md" T="$WS/TOOLS.md" U="$WS/USER.md"
  local META="$D.meta"; rm -rf "$META"; mkdir -p "$META"
  : > "$OUT"
  _r() { if [ "$1" = 0 ]; then echo "ok $2" >> "$OUT"; else echo "bad $2" >> "$OUT"; fi; }

  build_box "$D"
  local before_traps
  before_traps="$META/traps.before"; : > "$before_traps"
  trap_files "$D" | while IFS= read -r p; do echo "$(_sha "$p") $p"; done > "$before_traps"

  run_fn "$FN" "$D"

  # S1 registered + command-center + scan-found workspaces end identical to master
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
  _r "$ws_ok" "S1 registered/command-center/defaults/legacy workspaces identical to master"

  # S2 a registered workspace missing files got them (entries outside scan roots, defaults)
  local cr=0
  for f in AGENTS.md TOOLS.md USER.md; do
    [ -f "$D/outside/ext/$f" ] && [ ! -L "$D/outside/ext/$f" ] || cr=1
    [ -f "$D/outside/dflt/$f" ] && [ ! -L "$D/outside/dflt/$f" ] || cr=1
  done
  [ -f "$WS/departments/sales/TOOLS.md" ] || cr=1
  _r "$cr" "S2 registered workspaces missing a core file were given the master copy"

  # S3 unique blocks preserved in the department's OWN IDENTITY.md
  local pr=0
  grep -qF 'SALES-ONLY RULE: always cc the closer' "$WS/departments/sales/IDENTITY.md" || pr=1
  grep -qF 'PRESERVED FROM sales AGENTS.md' "$WS/departments/sales/IDENTITY.md" || pr=1
  grep -qF 'SUPPORT-ONLY RULE: tag every ticket' "$OCR/workspaces/command-center/support/IDENTITY.md" || pr=1
  grep -qF 'LEGACY-ONLY RULE: page the owner' "$D/outside/legacy/IDENTITY.md" || pr=1
  grep -qF '# sales identity' "$WS/departments/sales/IDENTITY.md" || pr=1
  _r "$pr" "S3 department-specific content preserved in that department's IDENTITY.md"

  # S4 traps untouched
  local after_traps tr=0
  after_traps="$META/traps.after"; : > "$after_traps"
  trap_files "$D" | while IFS= read -r p; do echo "$(_sha "$p") $p"; done > "$after_traps"
  cmp -s "$before_traps" "$after_traps" || tr=1
  _r "$tr" "S4 backup, hidden, archive, node_modules, skill, onboarding and template trees untouched"

  # S5 role folders: no AGENTS.md ever, TOOLS.md kept in step, unregistered stays empty
  local rf=0
  [ ! -e "$WS/departments/sales/closer/AGENTS.md" ] || rf=1
  [ ! -e "$WS/departments/sales/setter/AGENTS.md" ] || rf=1
  cmp -s "$T" "$WS/departments/sales/closer/TOOLS.md" || rf=1
  cmp -s "$T" "$WS/departments/sales/setter/TOOLS.md" || rf=1
  cmp -s "$U" "$WS/departments/sales/setter/USER.md" || rf=1
  [ ! -e "$OCR/workspaces/orphan/AGENTS.md" ] && [ ! -e "$OCR/workspaces/orphan/TOOLS.md" ] \
    && [ ! -e "$OCR/workspaces/orphan/USER.md" ] || rf=1
  _r "$rf" "S5 role folders keep no AGENTS.md (U053); unregistered folders gain no file"

  # S6 no symlink left, the relic became a real copy
  local sl=0
  [ "$(find "$D" -type l | wc -l | tr -d ' ')" = "0" ] || sl=1
  [ -f "$WS/departments/legal/AGENTS.md" ] && cmp -s "$A" "$WS/departments/legal/AGENTS.md" || sl=1
  _r "$sl" "S6 symlink relic migrated to a real file; no symlink exists afterwards"
  [ "$MODE" = quick ] && return 0

  # S7 idempotent second run
  snap "$D" > "$META/snap.1"
  run_fn "$FN" "$D"
  snap "$D" > "$META/snap.2"
  local id=0
  cmp -s "$META/snap.1" "$META/snap.2" || { id=1; diff "$META/snap.1" "$META/snap.2" >> "$META/detail.log"; }
  _r "$id" "S7 second run changes nothing (no rewrite, no new backup, no new file)"

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
  _r "$fo" "S8 empty master file is never copied over anything (fail-open)"
}

# extract the function out of SRC into DEST
extract_fn() {
  awk '/^link_shared_core_files\(\) \{/{f=1} f{print} f && /^\}$/{exit}' "$ROOT/$1" > "$2"
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
  D="$SANDBOX/box-$LBL"; OUT="$SANDBOX/out-$LBL.txt"; mkdir -p "$D"
  battery "$FN" "$D" "$OUT"
  while IFS= read -r line; do
    case "$line" in
      ok\ *)  ok "$LBL: ${line#ok }" ;;
      bad\ *) bad "$LBL: ${line#bad }"; [ -f "$D.meta/detail.log" ] && sed 's/^/        /' "$D.meta/detail.log" ;;
    esac
  done < "$OUT"
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
  # the unique content must still be there after another roll
  cp "$WS/departments/$DEPT/IDENTITY.md" "$D.id.1"
  run_fn "$FN" "$D"
  cmp -s "$D.id.1" "$WS/departments/$DEPT/IDENTITY.md" && ok "S9 $DEPT: IDENTITY.md stable on the next roll" \
    || bad "S9 $DEPT: IDENTITY.md changed on a second roll"
done

# ------------------------------------------------------------------------------
hdr "P1/P2 install.sh and update-skills.sh stay in step"
blk() { sed -n '/LSC-CANDIDATES-BEGIN/,/LSC-CANDIDATES-END/p' "$ROOT/$1"; }
if [ -n "$(blk install.sh)" ] && [ "$(blk install.sh)" = "$(blk update-skills.sh)" ]; then
  ok "P1 candidate block is byte-identical in install.sh and update-skills.sh"
else
  bad "P1 candidate block differs between install.sh and update-skills.sh (or is missing)"
fi
skip_of() { blk "$1" | grep -E "_LSC_SKIP=" | grep -oE "\-name '[^']*'" | sed "s/-name '//; s/'\$//" | LC_ALL=C sort | tr '\n' ' '; }
qc_skip() { python3 - "$ROOT/scripts/qc-system-integrity.sh" <<'PYEOF'
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'UNIFY_SKIP_DIRS = \(([^)]*)\)', t)
print(" ".join(sorted(re.findall(r'"([^"]*)"', m.group(1)))) + " " if m else "")
PYEOF
}
S_INS="$(skip_of install.sh)"; S_UPD="$(skip_of update-skills.sh)"; S_QC="$(qc_skip)"
if [ -n "$S_UPD" ] && [ "$S_INS" = "$S_UPD" ] && [ "$S_UPD" = "$S_QC" ]; then
  ok "P2 skip list is identical in install.sh, update-skills.sh and QC check 9.9 ($S_UPD)"
else
  bad "P2 skip lists differ: install=[$S_INS] updater=[$S_UPD] qc=[$S_QC]"
fi

# ------------------------------------------------------------------------------
hdr "Q1 QC check 9.9 covers entries + command-center, red on drift, green after sync"
QCPY="$SANDBOX/qc99.py"
awk '/^UNIFY_BAD=\$\(OCJSON=/{f=1; next} f && /^PYEOF$/{exit} f{print}' "$ROOT/scripts/qc-system-integrity.sh" > "$QCPY"
if python3 -c "import ast; ast.parse(open('$QCPY').read())" 2>/dev/null && grep -q 'UNIFY_SKIP_DIRS' "$QCPY"; then
  D="$SANDBOX/qc-box"; build_box "$D"
  qc_run() { OCJSON="$D/home/.openclaw/openclaw.json" HOME="$D/home" python3 "${1:-$QCPY}" 2>&1; }
  qc_first() { qc_run "${1:-$QCPY}" | head -1; }
  OCR="$D/home/.openclaw"; WS="$OCR/workspace"
  N0="$(qc_first)"
  [ "${N0:-0}" -gt 0 ] 2>/dev/null && ok "Q1 unsynced fixture box: QC 9.9 is red ($N0 problems)" || bad "Q1 unsynced fixture box was not flagged (count=$N0)"
  run_fn "$SANDBOX/fn-update-skills.sh" "$D"
  [ "$(qc_first)" = "0" ] && ok "Q1 synced box: QC 9.9 is green (backup and vendored trees, which differ from master, are ignored)" \
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
  # mutation: a QC that ignores agents.entries must go blind to exactly that drift
  sed 's/for e in list(ent.values()) + lst + \[dfl\]:/for e in lst:/' "$QCPY" > "$SANDBOX/qc99.mut.py"
  if cmp -s "$QCPY" "$SANDBOX/qc99.mut.py"; then bad "M qc-no-entries: mutation did not apply"
  elif [ "$(qc_first "$SANDBOX/qc99.mut.py")" = "0" ]; then ok "M qc-no-entries: a QC without agents.entries coverage misses that drift (so Q1 is not vacuous)"
  else bad "M qc-no-entries: mutated QC still caught the drift"; fi
else
  bad "Q1 could not extract the QC 9.9 python block"
fi

# ------------------------------------------------------------------------------
hdr "M* mutation proof: break each rule in a COPY, the battery must go red"
mutate() { # NAME SEDSCRIPT EXPECT-BAD-FRAGMENT
  local NAME="$1" SEDS="$2" WANT="$3"
  local M="$SANDBOX/mut-$NAME.sh"
  sed "$SEDS" "$SANDBOX/fn-update-skills.sh" > "$M"
  if cmp -s "$M" "$SANDBOX/fn-update-skills.sh"; then bad "M $NAME: mutation did not apply (pattern drifted)"; return; fi
  bash -n "$M" 2>/dev/null || { bad "M $NAME: mutated copy does not parse"; return; }
  local D="$SANDBOX/mbox-$NAME" OUT="$SANDBOX/mout-$NAME.txt"; mkdir -p "$D"
  battery "$M" "$D" "$OUT" quick
  if grep -q "^bad .*$WANT" "$OUT"; then ok "M $NAME: battery went red on '$WANT' as it must"
  else bad "M $NAME: battery stayed green on '$WANT' (rule is not actually tested)"; fi
}
mutate no-bak-prune   "s/ -o -name '\*\.bak\*'//; s/ -o -name '\*\.backup\*'//; s/-name '\.\*' -o //" "S4"
mutate no-skill-prune "s/ -o -name 'skills'//"                                              "S4"
mutate no-nm-prune    "s/ -o -name 'node_modules'//"                                        "S4"
mutate no-entries     's/ent = ag.get("entries") if isinstance(ag.get("entries"), dict) else {}/ent = {}/' "S1"
mutate no-defaults    's/for e in list(ent.values()) + lst + \[dfl\]:/for e in list(ent.values()) + lst:/' "S1"
mutate no-create      's/\[ "\$W_IS_REG" = "yes" \] && \[ ! -e/[ "no" = "yes" ] \&\& [ ! -e/' "S2"
mutate role-gets-agents 's/\[ "\$W_IS_ROLE" != "yes" \]; }; then/true; }; then/'          "S5"
mutate no-preserve    's/unique = \[b for b in blocks if b.strip() and b.strip() not in canon_text\]/unique = []/' "S3"

echo ""
echo "=== shared-core-entries-sync: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
