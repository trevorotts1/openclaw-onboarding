#!/usr/bin/env bash
# skill77-council-complete-install.test.sh: CWE-039 complete-install fixtures.
#
# WHAT THIS PROVES (directive tests T109, T110, T111 for CWE-039)
#   FRESH: a clean box discovers the complete Skill 77 through the real
#     installer discovery functions and installs it through the real
#     install.sh Step 5 copy loop (extracted verbatim, anchors asserted),
#     next to an untouched Skill 76. The installed tree is byte-identical
#     to the source tree; the skill doctor passes from the installed
#     location; the real CORE_UPDATES merger (extracted from
#     update-skills.sh) wires the council payload into the box workspace;
#     the real wave verification gate (lib-onboarding-state.sh
#     oc_gate_skill) is then run against the installed tree; and the
#     installed runtime is built in place and run from the installed
#     location, reproducing the labeled sample session with the Section
#     32.2 golden values (WAIT, recommended B, A 6.0 / B 7.6 / C 6.6)
#     with council state landing OUTSIDE the skill folder.
#   UPDATE: an existing box whose installed 77 folder is the scaffold-era
#     tree (git archive of the accepted scaffold commit) plus planted
#     stale files is updated through the real update-skills.sh per-skill
#     copy loop (extracted verbatim): guarded wholesale removal, box-state
#     save/restore, fresh copy. The updated tree is byte-identical to the
#     current source, every planted file is gone, the council data file
#     outside the folder is byte-identical across the update, and the
#     updated installed runtime reads the pre-existing session back with
#     the same verdict.
#   T111: the shipped wave-concurrency gate honors the VPS cap of 5
#     (5 allowed, 6 rejected) and the Mac cap of 10; the extracted
#     install/update/wire code contains no gateway restart invocation,
#     and the openclaw stub log proves the fixtures only ever asked the
#     registry for skill info (master-only restart discipline).
#
# HONESTY NOTES
#   * Machinery is EXTRACTED from the real install.sh / update-skills.sh /
#     lib-onboarding-state.sh at run time, with anchor greps that fail
#     loudly if the upstream shape changes. Nothing is re-implemented.
#   * Disclosed stubs: install.sh progress helpers (note/success/step/
#     add_to_list/send_telegram_progress) are no-ops; obs_set_status is
#     a no-op (the updater sources the real one from
#     scripts/onboarding-state.sh; it only records state transitions);
#     `openclaw` is a fixture stub that answers `skills info <name>`
#     from the fixture skills dir, the way the real CLI answers from its
#     registry (same pattern as tests/unit/box-fixes-gates.test.sh).
#   * The update fixture's pre-existing council state is created by the
#     complete build (the scaffold-era runtime was never runnable, so
#     no older build could have created state). What is proven is the
#     B11 mechanism: wholesale folder replacement, zero leakage from the
#     old tree, and state outside the folder surviving untouched and
#     readable by the updated install.
#   * The CLI build inside the installed copy needs the npm registry
#     (isolated dependency install, directive Section 26.3). Pins match
#     runtime/package.json exactly.
#   * Fixture roots live under ${TMPDIR:-/tmp}, never inside a git
#     checkout, matching a real installed box: the QC script's
#     source-checkout section and the doctor's Skill 76 git check skip
#     there by design, and Skill 76 integrity is asserted directly by
#     byte-equality instead (stronger, and shape-independent).
#
# KNOWN TREE DEFECT THIS FIXTURE EXPOSES (found 2026-10-14, CWE-039
# fixtures stream): advisors/michelle-obama/sources.json (CWE-018 pack)
# contains 10 em dash characters, so the skill QC fails on the current
# tree and the gate's QC leg fails with it. The QC and gate assertions
# below therefore FAIL until that one file is fixed by its owner and
# the manifest is regenerated. Every other assertion passes. A fixture
# that hid this would be a defect, not a pass.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCAFFOLD_SHA="2f46e4edbc88c09f8f99038003e218bb4c180c14"
PASS=0; FAIL=0
ok()   { PASS=$((PASS + 1)); printf '  ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$1"; }
check(){ if eval "$2"; then ok "$1"; else bad "$1"; fi }
info() { printf '  ..   %s\n' "$1"; }

command -v node    >/dev/null 2>&1 || { echo "FATAL: node not on PATH"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 not on PATH"; exit 1; }
command -v npm     >/dev/null 2>&1 || { echo "FATAL: npm not on PATH"; exit 1; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/skill77-complete-install.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export npm_config_cache="$WORK/.npm-cache"

# Source trees come from `git archive HEAD` (tracked release content
# only), never from the live worktree, so untracked debris in a checkout
# can neither leak into a fixture bundle nor fake a tree difference.
mkdir -p "$WORK/pristine"
git -C "$ROOT" archive HEAD -- 76-local-embedder 77-council-of-wise-elders \
  | tar -x -C "$WORK/pristine" || { echo "FATAL: git archive of HEAD failed"; exit 1; }
SK77_SRC="$WORK/pristine/77-council-of-wise-elders"
SK76_SRC="$WORK/pristine/76-local-embedder"
NPM_PINS="zod@4.4.3 tsx@4.22.4 typescript@5.9.3 @types/node@20.19.42 esbuild@0.28.2"

tree_file_count() { find "$1" -type f | wc -l | tr -d ' '; }
tree_identical()  { diff -rq "$1" "$2" >/dev/null 2>&1; }

sha_of() { python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"; }

# ---------------------------------------------------------------------------
echo "=== extraction anchors (fail loudly if upstream shape moved) ==="
# ---------------------------------------------------------------------------
EXT="$WORK/extract"; mkdir -p "$EXT"

awk '/^discover_skills_dir\(\) \{/{p=1} p{print} p&&/^\}/{exit}' "$ROOT/install.sh" > "$EXT/discovery.sh"
awk '/^discover_skills\(\) \{/{p=1} p{print} p&&/^\}/{exit}'    "$ROOT/install.sh" >> "$EXT/discovery.sh"
check "install.sh discovery functions extracted" \
  "grep -q '^discover_skills()' '$EXT/discovery.sh' && grep -q '^discover_skills_dir()' '$EXT/discovery.sh' && bash -n '$EXT/discovery.sh'"

awk '/^for SKILL_DIR in "\$ONBOARDING_DIR"\/\[0-9\]\*\/; do/{p=1} p{print} p&&/^done$/{exit}' \
  "$ROOT/install.sh" > "$EXT/step5.sh"
check "install.sh Step 5 copy loop extracted" \
  "grep -q 'cp -r \"\$ITEM\"' '$EXT/step5.sh' && grep -q 'ARCHIVED' '$EXT/step5.sh' && bash -n '$EXT/step5.sh'"

awk '/^_ocwp_owner\(\) \{/{p=1} p{print} /^# <<< SKILL-BOX-STATE-END/{exit}' \
  "$ROOT/update-skills.sh" > "$EXT/upd-helpers.sh"
check "update-skills.sh guarded-removal and box-state helpers extracted" \
  "grep -q '^oc_remove_tree_guarded()' '$EXT/upd-helpers.sh' && grep -q '^oc_skill_box_state_save()' '$EXT/upd-helpers.sh' && grep -q '^oc_skill_box_state_restore()' '$EXT/upd-helpers.sh' && bash -n '$EXT/upd-helpers.sh'"

{ echo 'NEW_SKILLS_CSV=""; SKIPPED_COUNT=0'
  sed -n '/^  for SKILL_DIR in "\$EXTRACTED_DIR"\/\[0-9\]\*\/; do/,/^  done$/p' "$ROOT/update-skills.sh"
} > "$EXT/upd-loop.sh"
check "update-skills.sh per-skill copy loop extracted" \
  "grep -q 'oc_remove_tree_guarded' '$EXT/upd-loop.sh' && grep -q 'cp -r \"\${SKILL_DIR%/}\"' '$EXT/upd-loop.sh' && bash -n '$EXT/upd-loop.sh'"

awk '/^  wire_core_updates\(\) \{/{p=1} p{print} p&&/^  \}$/{exit}' \
  "$ROOT/update-skills.sh" > "$EXT/wire.sh"
check "update-skills.sh wire_core_updates merger extracted" \
  "grep -q 'CORE-UPDATES-PY-BEGIN' '$EXT/wire.sh' && grep -q 'CORE-UPDATES-PY-END' '$EXT/wire.sh' && bash -n '$EXT/wire.sh'"

check "no gateway restart invocation in the extracted install/update/wire code" \
  "! grep -qiE 'openclaw +gateway|gateway +restart|systemctl +restart|pm2 +restart' '$EXT/step5.sh' '$EXT/upd-loop.sh' '$EXT/wire.sh'"

# Disclosed stubs for progress/state helpers the real scripts define or
# source elsewhere; they do not touch the filesystem semantics under test.
helpers_stub() {
  note() { :; }; success() { :; }; step() { :; }
  add_to_list() { :; }; send_telegram_progress() { :; }
  obs_set_status() { :; }
}

# Per-box openclaw registry stub (disclosed in the header).
make_openclaw_stub() { # $1 = bin dir receiving the stub
  mkdir -p "$1"
  cat > "$1/openclaw" <<'EOF'
#!/usr/bin/env bash
echo "openclaw $*" >> "${OPENCLAW_STUB_LOG:-/dev/null}"
if [ "$1" = "skills" ] && [ "$2" = "info" ] && [ -n "${3:-}" ]; then
  want="$3"
  for md in "$OC_SKILLS_DIR"/*/SKILL.md; do
    [ -f "$md" ] || continue
    nm="$(awk -F': ' '/^name:/{gsub(/[[:space:]]/,"",$2);print $2;exit}' "$md")"
    if [ "$nm" = "$want" ]; then
      echo "Skill: $nm"
      echo "Status: Ready"
      exit 0
    fi
  done
  echo "Skill not found: $want" >&2
  exit 1
fi
echo "stub openclaw: unsupported invocation: $*" >&2
exit 1
EOF
  chmod +x "$1/openclaw"
}

# A fixture client config whose model defaults and client state must
# survive every fixture untouched (T109).
plant_client_config() { # $1 = OC_CONFIG dir
  mkdir -p "$1"
  cat > "$1/openclaw.json" <<'EOF'
{
  "agents": {
    "defaults": {
      "model": { "primary": "deepseek/deepseek-flash", "fallbacks": ["agnes/agnes-3.0-flash"] }
    }
  },
  "clientStateMarker": "cwe039-fixture-do-not-touch"
}
EOF
}

# Builds the installed runtime in place (isolated dependency install +
# bundle). $1 = box env file, $2 = installed 77 dir, $3 = log prefix
build_installed() {
  local envf="$1" sk77="$2" tag="$3"
  ( source "$envf"
    cd "$sk77/runtime" || exit 1
    npm install --no-save --no-audit --no-fund $NPM_PINS > "$WORK/$tag-npm.log" 2>&1 || exit 1
    npm run build > "$WORK/$tag-build.log" 2>&1 || exit 1
  )
}

# Runs the labeled sample from the installed location.
# $1 = box env file, $2 = installed 77 dir, $3 = data dir, $4 = log prefix
run_sample() {
  local envf="$1" sk77="$2" data="$3" tag="$4"
  ( source "$envf"
    HOME="$BOX_HOME" BLACKCEO_COUNCIL_DATA_DIR="$data" \
      node "$sk77/runtime/dist/blackceo-council.mjs" sample run \
      > "$WORK/$tag-sample.out" 2>&1
  )
}

sample_values_ok() { # $1 = sample output file
  grep -q "SAMPLE SESSION (synthetic fixture data, not a real council run)" "$1" \
    && grep -q "Verdict for session sess-fixture-1: WAIT" "$1" \
    && grep -q "Recommended option: B" "$1" \
    && grep -q "Option A: 6.0" "$1" \
    && grep -q "Option B: 7.6" "$1" \
    && grep -q "Option C: 6.6" "$1"
}

# ---------------------------------------------------------------------------
echo "=== differences: scaffold-era tree vs current tree (recorded) ==="
# ---------------------------------------------------------------------------
SCAFFOLD_FILES="$(git -C "$ROOT" ls-tree -r --name-only "$SCAFFOLD_SHA" -- 77-council-of-wise-elders | wc -l | tr -d ' ')"
CURRENT_FILES="$(tree_file_count "$SK77_SRC")"
SCAFFOLD_RUNTIME_TS="$(git -C "$ROOT" ls-tree -r --name-only "$SCAFFOLD_SHA" -- 77-council-of-wise-elders/runtime/src | grep -c '\.ts$' || true)"
CURRENT_RUNTIME_TS="$(find "$SK77_SRC/runtime/src" -name '*.ts' | wc -l | tr -d ' ')"
info "scaffold tree files: $SCAFFOLD_FILES; current tree files: $CURRENT_FILES"
info "runtime TypeScript sources: scaffold $SCAFFOLD_RUNTIME_TS, current $CURRENT_RUNTIME_TS"
check "the complete tree is larger than the scaffold tree (runtime and packs landed)" \
  "[ '$CURRENT_FILES' -gt '$SCAFFOLD_FILES' ] && [ '$CURRENT_RUNTIME_TS' -gt '$SCAFFOLD_RUNTIME_TS' ]"
PACK_STATUSES="$(python3 -c "
import json
cfg=json.load(open('$SK77_SRC/config/advisors.json'))
print(','.join(sorted({s['pack_status'] for s in cfg['seats']})))")"
info "config/advisors.json pack_status values on the current tree: $PACK_STATUSES (packs are built; recorded as a staleness difference for final packaging, not edited here)"

# ---------------------------------------------------------------------------
echo "=== FRESH fixture (T110 fresh, T109) ==="
# ---------------------------------------------------------------------------
FB="$WORK/fresh"
ONB="$FB/onboarding"; mkdir -p "$ONB"
cp -r "$SK76_SRC" "$SK77_SRC" "$ONB/"
export BOX_HOME="$FB/home"; mkdir -p "$BOX_HOME"
F_CONFIG="$FB/.openclaw"; plant_client_config "$F_CONFIG"
F_SKILLS="$F_CONFIG/skills"; F_WS="$F_CONFIG/workspace"; mkdir -p "$F_WS"
printf '# Client memory\n\nFixture-owned memory content. Must not change.\n' > "$F_WS/MEMORY.md"
CFG_SHA_BEFORE="$(sha_of "$F_CONFIG/openclaw.json")"
MEM_SHA_BEFORE="$(sha_of "$F_WS/MEMORY.md")"
cat > "$FB/env.sh" <<EOF
export HOME="$BOX_HOME"
export OC_CONFIG="$F_CONFIG"
export OC_SKILLS_DIR="$F_SKILLS"
export OPENCLAW_ROOT="$F_CONFIG"
export OC_WORKSPACE_DEFAULT="$F_WS"
export OPENCLAW_MASTER_FILES_DIR="$FB/master-files"
export OPENCLAW_STUB_LOG="$FB/openclaw-stub.log"
EOF
mkdir -p "$FB/master-files"
make_openclaw_stub "$FB/bin"

FRESH_DISC="$( ( source "$FB/env.sh"; helpers_stub; source "$EXT/discovery.sh"
                 echo "DIR=$(discover_skills_dir)"; echo "COUNT=$(discover_skills "$ONB")" ) 2>/dev/null )"
info "discovery: $FRESH_DISC"
check "discover_skills_dir resolves to the fixture client skills dir" \
  "grep -q '^DIR=$F_SKILLS\$' <<<\"\$FRESH_DISC\""
check "discover_skills counts the complete bundle (76 and 77)" \
  "grep -q '^COUNT=2\$' <<<\"\$FRESH_DISC\""

# The Step 5 loop needs SKILL_COUNT/SKILLS_DIR/ONBOARDING_DIR in scope:
( source "$FB/env.sh"; helpers_stub; source "$EXT/discovery.sh"
  ONBOARDING_DIR="$ONB" SKILLS_DIR="$(discover_skills_dir)" SKILL_COUNT="$(discover_skills "$ONB")"
  source "$EXT/step5.sh" ) > "$FB/step5.out" 2>&1
check "real Step 5 loop installed both skills" \
  "[ -d '$F_SKILLS/77-council-of-wise-elders' ] && [ -d '$F_SKILLS/76-local-embedder' ]"
check "installed 77 tree is byte-identical to the source tree" \
  "tree_identical '$SK77_SRC' '$F_SKILLS/77-council-of-wise-elders'"
check "installed 76 tree is byte-identical to the source tree (T109: Skill 76 untouched)" \
  "tree_identical '$SK76_SRC' '$F_SKILLS/76-local-embedder'"

node "$F_SKILLS/77-council-of-wise-elders/scripts/doctor.mjs" \
  --root "$F_SKILLS/77-council-of-wise-elders" > "$FB/doctor.out" 2>&1
check "doctor passes from the installed location" "grep -q 'DOCTOR: PASS' '$FB/doctor.out'"

bash "$F_SKILLS/77-council-of-wise-elders/qc-council-of-wise-elders.sh" > "$FB/qc.out" 2>&1
check "skill QC passes from the installed location" "grep -q 'QC: PASS' '$FB/qc.out'"
grep -q "QC: FAIL" "$FB/qc.out" && info "QC failure detail: $(grep 'FAIL' "$FB/qc.out" | head -2)"

( source "$FB/env.sh"; export SKILLS_DIR="$F_SKILLS" WIRE_WORKSPACE_DIR="$F_WS" WIRE_AGENT_DIR=""
  source "$EXT/wire.sh"; wire_core_updates "77-council-of-wise-elders" ) > "$FB/wire.out" 2>&1
check "real CORE_UPDATES merger wired the council payload into the workspace" \
  "grep -q 'BEGIN skill:77-council-of-wise-elders' '$F_WS/AGENTS.md' && grep -q 'skill:77-council-of-wise-elders:core-update-applied' '$F_WS/AGENTS.md'"
check "client MEMORY.md content unchanged by wiring" "[ '$(sha_of "$F_WS/MEMORY.md")' = '$MEM_SHA_BEFORE' ]"

( source "$FB/env.sh"; export PATH="$FB/bin:$PATH"
  source "$ROOT/lib-onboarding-state.sh"; oc_gate_skill 77-council-of-wise-elders ) > "$FB/gate.out" 2>&1
GATE_RC=$?
check "wave verification gate passes for the installed 77 (registered + sentinel + QC)" "[ '$GATE_RC' = '0' ]"
check "gate recorded qc-passed in the onboarding state file" \
  "python3 -c \"import json;s=json.load(open('$F_CONFIG/.onboarding-state.json'));assert s['skills']['77-council-of-wise-elders']['status']=='qc-passed'\""
check "the box only ever asked the registry for skill info (no restart, T111)" \
  "[ -s '$FB/openclaw-stub.log' ] && ! grep -vqE '^openclaw skills info council-of-wise-elders\$' '$FB/openclaw-stub.log'"

F_DATA="$FB/data"; mkdir -p "$F_DATA"
build_installed "$FB/env.sh" "$F_SKILLS/77-council-of-wise-elders" fresh
check "installed runtime builds in place (isolated dependency install + bundle)" "[ '$?' = '0' ]"
run_sample "$FB/env.sh" "$F_SKILLS/77-council-of-wise-elders" "$F_DATA" fresh
check "sample run from the installed location exits 0" "[ '$?' = '0' ]"
check "sample run from the installed location reproduces the golden values" \
  "sample_values_ok '$WORK/fresh-sample.out'"
check "council state landed in the data dir OUTSIDE the skill folder" \
  "[ -f '$F_DATA/council.db' ] && ! find '$F_SKILLS/77-council-of-wise-elders' -name 'council.db' | grep -q ."
( source "$FB/env.sh"; HOME="$BOX_HOME" BLACKCEO_COUNCIL_DATA_DIR="$F_DATA" \
    node "$F_SKILLS/77-council-of-wise-elders/runtime/dist/blackceo-council.mjs" \
    status sess-fixture-1 ) > "$FB/status.out" 2>&1
check "installed CLI reads the sample session back (state COMPLETED, 0 provider requests)" \
  "grep -q 'state: COMPLETED' '$FB/status.out' && grep -q 'provider requests consumed: 0 of 50' '$FB/status.out'"
( source "$FB/env.sh"; HOME="$BOX_HOME" BLACKCEO_COUNCIL_DATA_DIR="$F_SKILLS/77-council-of-wise-elders/data" \
    node "$F_SKILLS/77-council-of-wise-elders/runtime/dist/blackceo-council.mjs" \
    sample run ) > "$FB/inside.out" 2>&1
INSIDE_RC=$?
check "a data dir inside the skill folder is refused (Section 16.1)" \
  "[ '$INSIDE_RC' != '0' ] && grep -q 'inside the skill folder' '$FB/inside.out'"

rm -rf "$F_SKILLS/77-council-of-wise-elders/runtime/node_modules" \
       "$F_SKILLS/77-council-of-wise-elders/runtime/dist"
check "installed tree returns to byte-identity after build cleanup" \
  "tree_identical '$SK77_SRC' '$F_SKILLS/77-council-of-wise-elders'"
node "$F_SKILLS/77-council-of-wise-elders/scripts/doctor.mjs" \
  --root "$F_SKILLS/77-council-of-wise-elders" > "$FB/doctor2.out" 2>&1
check "doctor passes again on the cleaned installed tree" "grep -q 'DOCTOR: PASS' '$FB/doctor2.out'"
check "client config (model defaults, client state) byte-identical after the fresh install" \
  "[ '$(sha_of "$F_CONFIG/openclaw.json")' = '$CFG_SHA_BEFORE' ]"

# ---------------------------------------------------------------------------
echo "=== UPDATE fixture (T110 update, B11 wholesale replacement) ==="
# ---------------------------------------------------------------------------
UB="$WORK/update"
export BOX_HOME="$UB/home"; mkdir -p "$BOX_HOME"
U_CONFIG="$UB/.openclaw"; plant_client_config "$U_CONFIG"
U_SKILLS="$U_CONFIG/skills"; U_WS="$U_CONFIG/workspace"; mkdir -p "$U_SKILLS" "$U_WS"
printf '# Client memory\n\nFixture-owned memory content. Must not change.\n' > "$U_WS/MEMORY.md"
U_CFG_SHA="$(sha_of "$U_CONFIG/openclaw.json")"; U_MEM_SHA="$(sha_of "$U_WS/MEMORY.md")"
U_DATA="$UB/data"; mkdir -p "$U_DATA"
cat > "$UB/env.sh" <<EOF
export HOME="$BOX_HOME"
export OC_CONFIG="$U_CONFIG"
export OC_SKILLS_DIR="$U_SKILLS"
export OPENCLAW_ROOT="$U_CONFIG"
export OC_WORKSPACE_DEFAULT="$U_WS"
export OPENCLAW_MASTER_FILES_DIR="$UB/master-files"
export OPENCLAW_STUB_LOG="$UB/openclaw-stub.log"
EOF
mkdir -p "$UB/master-files"
make_openclaw_stub "$UB/bin"

# Phase 1: the complete build is installed (fresh path) and creates state.
( source "$UB/env.sh"; helpers_stub; source "$EXT/discovery.sh"
  ONBOARDING_DIR="$ONB" SKILLS_DIR="$U_SKILLS" SKILL_COUNT=2
  source "$EXT/step5.sh" ) > "$UB/phase1.out" 2>&1
build_installed "$UB/env.sh" "$U_SKILLS/77-council-of-wise-elders" upd1
run_sample "$UB/env.sh" "$U_SKILLS/77-council-of-wise-elders" "$U_DATA" upd1
check "pre-update installed sample created the council state" \
  "sample_values_ok '$WORK/upd1-sample.out' && [ -f '$U_DATA/council.db' ]"
rm -rf "$U_SKILLS/77-council-of-wise-elders/runtime/node_modules" \
       "$U_SKILLS/77-council-of-wise-elders/runtime/dist"
DB_SHA_BEFORE="$(sha_of "$U_DATA/council.db")"

# Phase 2: the box's installed folder is the older (scaffold-era) release,
# plus planted stale material that no release ships.
rm -rf "$U_SKILLS/77-council-of-wise-elders"
mkdir -p "$UB/scaffold-src"
git -C "$ROOT" archive "$SCAFFOLD_SHA" -- 77-council-of-wise-elders | tar -x -C "$UB/scaffold-src"
cp -r "$UB/scaffold-src/77-council-of-wise-elders" "$U_SKILLS/"
printf 'stale operator file\n' > "$U_SKILLS/77-council-of-wise-elders/zz-cwe039-stale.txt"
printf '{"planted":true}\n'  > "$U_SKILLS/77-council-of-wise-elders/sessions.json"
mkdir -p "$U_SKILLS/77-council-of-wise-elders/runtime/dist"
printf 'stale build\n' > "$U_SKILLS/77-council-of-wise-elders/runtime/dist/stale-build.mjs"
check "old install is the scaffold-era tree (file count differs from current)" \
  "[ '$(tree_file_count "$U_SKILLS/77-council-of-wise-elders")' != '$CURRENT_FILES' ]"

# Phase 3: the real update loop over a bundle carrying the current trees.
BUNDLE="$UB/bundle"; mkdir -p "$BUNDLE"; cp -r "$SK76_SRC" "$SK77_SRC" "$BUNDLE/"
( source "$UB/env.sh"; helpers_stub; source "$EXT/upd-helpers.sh"
  EXTRACTED_DIR="$BUNDLE" SKILLS_DIR="$U_SKILLS" ONLY_SKILLS="" LOG_FILE="$UB/update.log"
  source "$EXT/upd-loop.sh" ) > "$UB/update.out" 2>&1
check "real update loop replaced both skills" \
  "grep -q 'Updated: 77-council-of-wise-elders' '$UB/update.out' && grep -q 'Updated: 76-local-embedder' '$UB/update.out'"
check "updated 77 tree is byte-identical to the current source (nothing of the old tree leaks)" \
  "tree_identical '$SK77_SRC' '$U_SKILLS/77-council-of-wise-elders'"
check "updated 76 tree is byte-identical to the source (T109)" \
  "tree_identical '$SK76_SRC' '$U_SKILLS/76-local-embedder'"
check "planted stale files are gone after the wholesale replacement" \
  "[ ! -e '$U_SKILLS/77-council-of-wise-elders/zz-cwe039-stale.txt' ] && [ ! -e '$U_SKILLS/77-council-of-wise-elders/sessions.json' ] && [ ! -e '$U_SKILLS/77-council-of-wise-elders/runtime/dist/stale-build.mjs' ]"
check "box-state allow-list for skill 77 is empty (in-folder state cannot survive by design)" \
  "( source '$EXT/upd-helpers.sh'; [ -z \"\$(oc_skill_box_state_paths 77-council-of-wise-elders)\" ] )"
check "council data file outside the folder is byte-identical across the update" \
  "[ '$(sha_of "$U_DATA/council.db")' = '$DB_SHA_BEFORE' ]"

node "$U_SKILLS/77-council-of-wise-elders/scripts/doctor.mjs" \
  --root "$U_SKILLS/77-council-of-wise-elders" > "$UB/doctor.out" 2>&1
check "doctor passes from the updated installed location" "grep -q 'DOCTOR: PASS' '$UB/doctor.out'"
bash "$U_SKILLS/77-council-of-wise-elders/qc-council-of-wise-elders.sh" > "$UB/qc.out" 2>&1
check "skill QC passes from the updated installed location" "grep -q 'QC: PASS' '$UB/qc.out'"

build_installed "$UB/env.sh" "$U_SKILLS/77-council-of-wise-elders" upd2
check "updated installed runtime builds in place" "[ '$?' = '0' ]"
( source "$UB/env.sh"; HOME="$BOX_HOME" BLACKCEO_COUNCIL_DATA_DIR="$U_DATA" \
    node "$U_SKILLS/77-council-of-wise-elders/runtime/dist/blackceo-council.mjs" \
    verdict sess-fixture-1 ) > "$UB/verdict.out" 2>&1
check "updated installed runtime reads the pre-existing session verdict (WAIT, B, golden scores)" \
  "sample_values_ok '$UB/verdict.out'"
rm -rf "$U_SKILLS/77-council-of-wise-elders/runtime/node_modules" \
       "$U_SKILLS/77-council-of-wise-elders/runtime/dist"
check "updated tree returns to byte-identity after build cleanup" \
  "tree_identical '$SK77_SRC' '$U_SKILLS/77-council-of-wise-elders'"
check "client config and memory byte-identical across the whole update lifecycle" \
  "[ '$(sha_of "$U_CONFIG/openclaw.json")' = '$U_CFG_SHA' ] && [ '$(sha_of "$U_WS/MEMORY.md")' = '$U_MEM_SHA' ]"

# Skill 76 functional surface on the installed copy: identical bytes plus a
# parseable entry script (its hermetic suite is repo-shaped; see report).
check "installed 76 entry script parses (bash -n wire.sh)" "bash -n '$U_SKILLS/76-local-embedder/wire.sh'"

# ---------------------------------------------------------------------------
echo "=== T111: wave caps and persistent paths ==="
# ---------------------------------------------------------------------------
bash "$ROOT/scripts/check-wave-concurrency.sh" --platform vps --proposed 5 >/dev/null 2>&1
check "VPS wave cap allows 5" "[ '$?' = '0' ]"
bash "$ROOT/scripts/check-wave-concurrency.sh" --platform vps --proposed 6 >/dev/null 2>&1
check "VPS wave cap rejects 6" "[ '$?' = '1' ]"
bash "$ROOT/scripts/check-wave-concurrency.sh" --platform mac --proposed 10 >/dev/null 2>&1
check "Mac wave cap allows 10" "[ '$?' = '0' ]"
bash "$ROOT/scripts/check-wave-concurrency.sh" --platform mac --proposed 11 >/dev/null 2>&1
check "Mac wave cap rejects 11" "[ '$?' = '1' ]"
info "persistent data paths: proven by the update fixture (state outside the folder, byte-identical, readable after replacement)"

# ---------------------------------------------------------------------------
echo "=== distribution hygiene: Brunson private_scope strip list ==="
# ---------------------------------------------------------------------------
python3 - "$SK77_SRC" "$WORK" <<'PY'
import json, os, sys
src, work = sys.argv[1], sys.argv[2]
fails = []
def expect(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond: fails.append(label)

strip = []   # (relative file, item id) pairs carrying scope private_scope
for rel in ("advisors/russell-brunson/frameworks.json",
            "advisors/russell-brunson/failure-patterns.json"):
    data = json.load(open(os.path.join(src, rel)))
    for item in data["items"]:
        if item.get("scope") == "private_scope":
            strip.append((rel, item["id"]))
expect(sorted(i for _, i in strip) ==
       ["fp-technobabble", "fw-epiphany-bridge-and-demo", "fw-one-client-one-funnel"],
       f"strip list is exactly the three recorded private_scope items: {[i for _, i in strip]}")

profile = json.load(open(os.path.join(src, "advisors/russell-brunson/profile.json")))
expect(profile["distribution"]["contains_private_scope_material"] is True
       and profile["distribution"]["distribution_ready"] is False,
       "Brunson profile records contains_private_scope_material true, distribution_ready false")

hits = []
for dirpath, dirnames, filenames in os.walk(src):
    dirnames[:] = [d for d in dirnames if d != "node_modules"]
    for fn in filenames:
        if fn == "source-text.txt":
            hits.append(os.path.join(dirpath, fn))
expect(not hits, "no Skill 22 source text file exists anywhere in the 77 tree")

embedded = []
for seat in os.listdir(os.path.join(src, "advisors")):
    sp = os.path.join(src, "advisors", seat, "sources.json")
    if not os.path.isfile(sp):
        continue
    for unit in json.load(open(sp)).get("evidence_units", []):
        if str(unit.get("id", "")).startswith("ev-russell-brunson-network-marketing-secrets-"):
            embedded.append(unit["id"])
expect(not embedded, "no private-set evidence unit is embedded in any pack sources.json")

manifest = json.load(open(os.path.join(src, "manifest.json")))
archive_path = os.path.join(src, "council-of-wise-elders.skill")
archive_ok = (manifest["archive"]["status"] == "generated"
              and os.path.isfile(archive_path))
if archive_ok:
    import zipfile
    names = zipfile.ZipFile(archive_path).namelist()
    archive_ok = ("council-of-wise-elders/manifest.json" in names
                  and "council-of-wise-elders/SKILL.md" in names)
expect(archive_ok,
       "distributable archive generated at CWE-039 final packaging: manifest records it and council-of-wise-elders.skill is present with the portable root")

# Demonstration of the strip mechanism on a scratch copy (the committed
# tree is never modified). The mechanism has TWO parts, both proven:
# (1) drop the private_scope items from their home files; (2) scrub
# prose references to the stripped items / private evidence IDs from
# the remaining pack files (decision-rules.json and failure-patterns.json
# carry such mentions in note/correction fields of shared items; an
# item-only strip would leave them, including one raw private evidence
# ID, in a distributable artifact).
import re, shutil
strip_ids = sorted({i for _, i in strip})
PREFIX = "ev-russell-brunson-network-marketing-secrets-"
demo = os.path.join(work, "strip-demo")
shutil.copytree(src, demo)
removed = {}
for rel in sorted({r for r, _ in strip}):
    p = os.path.join(demo, rel)
    data = json.load(open(p))
    before = [i["id"] for i in data["items"]]
    data["items"] = [i for i in data["items"] if i.get("scope") != "private_scope"]
    json.dump(data, open(p, "w"), indent=2)
    after = [i["id"] for i in data["items"]]
    removed[rel] = len(before) - len(after)
    expect(after == [x for x in before if x not in strip_ids],
           f"strip of {rel} removed exactly its private_scope items ({removed[rel]}), kept the rest")
scrubbed = []
def scrub_value(v, path, fname):
    if isinstance(v, str):
        if any(t in v for t in strip_ids) or PREFIX in v:
            parts = [s for s in re.split(r"(?<=[.!?])\s+", v)
                     if not (any(t in s for t in strip_ids) or PREFIX in s)]
            scrubbed.append(f"{fname}:{path}")
            return " ".join(parts).strip()
        return v
    if isinstance(v, list):
        return [scrub_value(x, f"{path}[{n}]", fname) for n, x in enumerate(v)]
    if isinstance(v, dict):
        return {k: scrub_value(x, f"{path}.{k}", fname) for k, x in v.items()}
    return v
pack_dir = os.path.join(demo, "advisors/russell-brunson")
for fn in sorted(os.listdir(pack_dir)):
    if not fn.endswith(".json"):
        continue
    p = os.path.join(pack_dir, fn)
    data = json.load(open(p))
    data = scrub_value(data, "$", fn)
    json.dump(data, open(p, "w"), indent=2)
print("  ..   reference scrub touched: " + (", ".join(scrubbed) if scrubbed else "nothing"))
expect(any(s.startswith("decision-rules.json") for s in scrubbed)
       and any(s.startswith("failure-patterns.json") for s in scrubbed),
       "reference scrub reached the recorded prose mentions in decision-rules.json and failure-patterns.json")
demo_text = ""
json_ok = True
for dirpath, dirnames, filenames in os.walk(demo):
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        try: demo_text += open(p, encoding="utf-8", errors="ignore").read()
        except Exception: pass
        if fn.endswith(".json"):
            try: json.load(open(p))
            except Exception: json_ok = False
expect(json_ok, "every JSON file in the stripped demonstration tree still parses")
expect(PREFIX not in demo_text,
       "stripped demonstration tree contains no private-set evidence reference")
expect(all(i not in demo_text for i in strip_ids),
       "stripped demonstration tree contains none of the three private_scope item ids")
survivors = {}
for rel in ("advisors/russell-brunson/frameworks.json",
            "advisors/russell-brunson/failure-patterns.json",
            "advisors/russell-brunson/decision-rules.json"):
    src_ids = [i["id"] for i in json.load(open(os.path.join(src, rel)))["items"]]
    demo_ids = [i["id"] for i in json.load(open(os.path.join(demo, rel)))["items"]]
    survivors[rel] = demo_ids == [x for x in src_ids if x not in strip_ids]
expect(all(survivors.values()),
       "every non-private item survives the strip in order (frameworks, failure-patterns, decision-rules)")
sys.exit(1 if fails else 0)
PY
check "distribution hygiene block (strip list, no private source, strip demonstration)" "[ '$?' = '0' ]"

WAVE_COUNT="$(awk '/^OC_WAVE6_SKILLS=/{p=1} p{print} p&&/"$/{exit}' "$ROOT/lib-onboarding-state.sh" | grep -c '77-council-of-wise-elders' || true)"
check "wave roster carries 77-council-of-wise-elders exactly once (T109 discovery registration)" \
  "[ '$WAVE_COUNT' = '1' ]"
python3 "$ROOT/scripts/qc-assert-wave-list-integrity.py" > "$WORK/wave-integrity.out" 2>&1
check "wave-list integrity gate passes on the repo (all waves resolve, no duplicates)" "[ '$?' = '0' ]"

echo ""
echo "skill77-council-complete-install: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
