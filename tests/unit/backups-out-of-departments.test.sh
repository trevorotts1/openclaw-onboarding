#!/usr/bin/env bash
# tests/unit/backups-out-of-departments.test.sh
# -----------------------------------------------------------------------------
# Locks the "backups leave the department folders" contract:
#   shared-utils/central_backup.py (the mover + the keep-last-3 pruner),
#   update-skills.sh migrate_backups_out_of_departments() (runs every roll),
#   and the writers that used to drop backup folders inside the department tree
#   (apply-u004-phase2.sh; reconcile-legacy-tree.py is locked by
#   23-ai-workforce-blueprint/scripts/test-phantom-dept-collision-gate.sh T8).
#
# THE DEFECT THIS LOCKS. A real client box held workspace/departments/<dept>.bak-prover-fix-<stamp>/,
# workspace/.floor-backups/<stamp>/ and similar folders, months old, with hundreds of duplicate
# AGENTS.md / TOOLS.md copies that scanners and refreshers kept walking. Repair tools must save
# backups in ONE separate folder (outside every workspace) and keep only the last few.
#
# WHAT THIS PROVES (behavioral: it runs the REAL module on a fixture box):
#   A  --dry-run names every move and changes nothing
#   B  every backup folder leaves the live trees and arrives intact in the central folder
#   C  REAL departments are untouched (byte-identical), and so are the decoys: a symlink named
#      like a backup, a backup file, a folder openclaw.json still names, back-office, feedback
#   D  only the last 3 runs of a tool are kept centrally (5 made, 3 kept, the newest 3)
#   E  one repair that backed up 5 departments seconds apart is ONE run: kept whole, never cut
#   F  a second run is a no-op (nothing moved, central folder byte-identical)
#   G  OPENCLAW_BACKUP_KEEP overrides the count
#   H  update-skills.sh carries the step, runs it from the end of the roll AND the content-current
#      exit, outside the .wired loop; the shipped function really moves the folders
#   I  the backup root follows the platform rule; root is refused
#   J  apply-u004-phase2.sh writes its backups to the central folder, not into the department
#   K  FAILABLE: five mutants of the module (guard widened, pruner disabled, mover disabled,
#      run-grouping off, move turned into delete) are each caught by the same checks
#
# Hermetic: mktemp -d sandbox, HOME redirected into it, no real ~/.openclaw, no network.
# bash 3.2 safe: no associative arrays, no mapfile. Exit 0 = all pass, 1 = a failure.
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CB_REAL="$REPO_ROOT/shared-utils/central_backup.py"
PASS=0; FAIL=0; QUIET=0
ok()  { PASS=$((PASS + 1)); [ "$QUIET" = 1 ] || printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); [ "$QUIET" = 1 ] || printf '  FAIL %s\n' "$1"; }
hdr() { [ "$QUIET" = 1 ] || printf '\n== %s ==\n' "$1"; }

if [ "$(id -u)" = "0" ]; then
  echo "SKIP: running as root; central_backup.py refuses root by design, so the fixture run is meaningless here"
  exit 0
fi

unset OPENCLAW_ROOT OC_ROOT OPENCLAW_BACKUP_DIR OPENCLAW_BACKUP_KEEP OPENCLAW_WORKSPACE_PATH
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

mk_bak() { mkdir -p "$1/sub"; echo "copy of $(basename "$1")" > "$1/AGENTS.md"; echo t > "$1/sub/TOOLS.md"; }
snap_all() { ( cd "$1" && find . | LC_ALL=C sort && find . -type f -exec cksum {} + 2>/dev/null | LC_ALL=C sort ); }
LIVE="marketing sales video paid-advertisement back-office feedback"
snap_live() {  # the real departments, minus the known backup folders that live inside two of them
  ( cd "$1/oc/workspace/departments" && for d in $LIVE; do
      find "$d" ! -path '*/bak-archive-2026*' ! -path '*/.backfill-backup-*' | LC_ALL=C sort
      find "$d" -type f ! -path '*/bak-archive-2026*' ! -path '*/.backfill-backup-*' -exec cksum {} + | LC_ALL=C sort
    done )
}
count_dirs() { find "$1" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' '; }

# ----- the fixture box: live departments, backup folders, decoys ---------------
build_fixture() {
  local sb="$1" W D d day sec
  W="$sb/oc/workspace"; D="$W/departments"
  for d in $LIVE; do
    mkdir -p "$D/$d/01-role/sops"
    echo "live $d" > "$D/$d/AGENTS.md"; echo "role $d" > "$D/$d/01-role/AGENTS.md"
  done
  # backup folders INSIDE two real departments, plus decoys that must stay
  mk_bak "$D/marketing/working/bak-archive-20260601T000000Z"
  mkdir -p "$D/marketing/working/bak-archive-notes"; echo keep > "$D/marketing/working/bak-archive-notes/n.md"
  echo keep > "$D/marketing/working/notes.md"
  mk_bak "$D/sales/.backfill-backup-20260501T010101Z"
  # the three shapes seen on a real client box
  mk_bak "$D/paid-advertisement.bak-prover-fix-20260628T120608Z"
  mk_bak "$D/video.bak-prover-fix-20260628T120611Z"
  mk_bak "$W/.floor-backups/20260623T182141Z"
  mk_bak "$W/departments-archive/20260101T000000Z/billing"
  # a Command Center workspace whose children are departments
  mkdir -p "$sb/oc/workspaces/command-center/marketing"; echo cc > "$sb/oc/workspaces/command-center/marketing/AGENTS.md"
  mk_bak "$sb/oc/workspaces/command-center/marketing.bak-20260601-010101"
  # five backups of ONE tool on five different days -> only the last 3 may survive
  for day in 01 02 03 04 05; do mk_bak "$D/marketing.bak-repair-x-202606${day}T100000Z"; done
  # a tool with four older single-folder runs plus ONE repair that backed up 5 depts seconds apart
  for day in 01 02 03 04; do mk_bak "$D/sales.bak-burst-202607${day}T100000Z"; done
  for sec in 0 1 2 3 4; do mk_bak "$D/dept$sec.bak-burst-20260710T10000${sec}Z"; done
  # decoys that are NOT backup folders in a live tree, or must not be moved
  ln -s "$D/marketing" "$D/marketing.bak-link-20260101T000000Z"
  echo file > "$D/AGENTS.md.bak-unify-20261001-000000"
  mk_bak "$D/pinned.bak-keepme-20260101T000000Z"
  printf '{"agents":{"defaults":{"workspace":"%s"},"list":[{"id":"x","workspace":"%s"}]}}\n' \
    "$W" "$D/pinned.bak-keepme-20260101T000000Z" > "$sb/oc/openclaw.json"
}

# ----- the whole suite, run against one copy of the module --------------------
suite() {
  local CB="$1" SB; SB="$(mktemp -d "$SANDBOX/box.XXXXXX")"
  mkdir -p "$SB/home"
  build_fixture "$SB"
  local W="$SB/oc/workspace" D="$SB/oc/workspace/departments" CEN="$SB/central" out rc
  local S_HOME="$HOME"
  export HOME="$SB/home" OPENCLAW_ROOT="$SB/oc" OPENCLAW_BACKUP_DIR="$CEN"

  hdr "A: --dry-run names every move and changes nothing"
  local before; before="$(snap_all "$SB/oc")"
  out="$(python3 "$CB" migrate --dry-run 2>&1)"; rc=$?
  [ "$rc" = 0 ] && ok "A1 dry run exits 0" || bad "A1 dry run exit $rc"
  [ "$(printf '%s\n' "$out" | grep -c 'WOULD MOVE')" = 21 ] && ok "A2 dry run lists all 21 moves" || bad "A2 dry run lists $(printf '%s\n' "$out" | grep -c 'WOULD MOVE') moves, wanted 21"
  [ "$(snap_all "$SB/oc")" = "$before" ] && ok "A3 dry run changed nothing on disk" || bad "A3 dry run changed the box"
  [ ! -e "$CEN" ] && ok "A4 dry run created no central folder" || bad "A4 dry run created the central folder"

  hdr "B/C: backups move out intact; real departments and decoys untouched"
  local live_before; live_before="$(snap_live "$SB")"
  out="$(python3 "$CB" migrate 2>&1)"; rc=$?
  [ "$rc" = 0 ] && ok "B1 migrate exits 0" || bad "B1 migrate exit $rc: $out"
  local left; left="$(find "$D" "$W/.floor-backups" "$W/departments-archive" "$SB/oc/workspaces" \
        \( -name '*.bak-prover-fix-*' -o -name '*.bak-repair-x-*' -o -name '*.bak-burst-*' \
           -o -name '.floor-backups' -o -name 'departments-archive' -o -name 'bak-archive-2026*' \
           -o -name '.backfill-backup-*' -o -name 'marketing.bak-2026*' \) 2>/dev/null \
        | grep -v -e 'bak-link' -e 'pinned' | wc -l | tr -d ' ')"
  [ "$left" = 0 ] && ok "B2 no backup folder is left in the live trees" || bad "B2 $left backup folder(s) still in the live trees"
  [ -f "$CEN/prover-fix/20260628T120608Z/paid-advertisement.bak-prover-fix-20260628T120608Z/AGENTS.md" ] \
    && [ "$(cat "$CEN/prover-fix/20260628T120611Z/video.bak-prover-fix-20260628T120611Z/AGENTS.md" 2>/dev/null)" = "copy of video.bak-prover-fix-20260628T120611Z" ] \
    && [ -f "$CEN/prover-fix/20260628T120611Z/video.bak-prover-fix-20260628T120611Z/sub/TOOLS.md" ] \
    && ok "B3 the prover-fix backups arrived with their contents" || bad "B3 prover-fix backups missing or altered"
  [ -f "$CEN/floor-backups/20260623T182141Z/AGENTS.md" ] && ok "B4 .floor-backups/<stamp> arrived" || bad "B4 .floor-backups not in the central folder"
  [ -f "$CEN/departments-archive/20260101T000000Z/billing/AGENTS.md" ] && ok "B5 departments-archive/<stamp> arrived" || bad "B5 departments-archive not in the central folder"
  [ -f "$CEN/bak-archive/20260601T000000Z/marketing.bak-archive-20260601T000000Z/AGENTS.md" ] \
    && [ -f "$CEN/backfill-dept-personalization/20260501T010101Z/sales.backfill-backup-20260501T010101Z/AGENTS.md" ] \
    && ok "B6 the folders inside real departments arrived" || bad "B6 inner backup folders not moved"
  [ -f "$CEN/bak/20260601T010101Z/marketing.bak-20260601-010101/AGENTS.md" ] && ok "B7 the Command Center workspace backup arrived" || bad "B7 workspaces/command-center backup not moved"
  grep -q "$D/paid-advertisement.bak-prover-fix-20260628T120608Z" "$CEN/prover-fix/20260628T120608Z/MOVED-FROM.txt" 2>/dev/null \
    && ok "B8 the move is logged (MOVED-FROM.txt names the old path)" || bad "B8 no MOVED-FROM.txt record"
  [ ! -e "$W/.floor-backups" ] && ok "B9 the emptied .floor-backups husk is gone" || bad "B9 empty .floor-backups left behind"
  [ "$(snap_live "$SB")" = "$live_before" ] && ok "C1 every real department is byte-identical" || bad "C1 a real department changed"
  [ -d "$D/back-office" ] && [ -d "$D/feedback" ] && [ -f "$D/marketing/working/notes.md" ] \
    && [ -f "$D/marketing/working/bak-archive-notes/n.md" ] && ok "C2 look-alike names (back-office, feedback, bak-archive-notes) stay" || bad "C2 a look-alike was moved"
  [ -L "$D/marketing.bak-link-20260101T000000Z" ] && [ -f "$D/marketing/AGENTS.md" ] && ok "C3 a symlink named like a backup is never moved" || bad "C3 symlink moved"
  [ -f "$D/AGENTS.md.bak-unify-20261001-000000" ] && ok "C4 a backup FILE is left to its own pruner" || bad "C4 a backup file was moved"
  [ -d "$D/pinned.bak-keepme-20260101T000000Z" ] && printf '%s\n' "$out" | grep -q 'SKIP .*pinned.bak-keepme' \
    && ok "C5 a folder openclaw.json names stays, and says why" || bad "C5 a referenced folder was moved"

  hdr "D/E: keep only the last 3 runs per tool; one repair is one run"
  local rx; rx="$(ls "$CEN/repair-x" | tr '\n' ' ')"
  [ "$rx" = "20260603T100000Z 20260604T100000Z 20260605T100000Z " ] && ok "D1 5 backups made, the newest 3 kept, the oldest 2 pruned" || bad "D1 repair-x holds: $rx"
  [ ! -e "$CEN/repair-x/20260601T100000Z" ] && [ -f "$CEN/repair-x/20260605T100000Z/marketing.bak-repair-x-20260605T100000Z/AGENTS.md" ] \
    && ok "D2 the kept backups are intact" || bad "D2 a kept backup is missing"
  [ ! -e "$CEN/burst/20260701T100000Z" ] && [ ! -e "$CEN/burst/20260702T100000Z" ] && [ -d "$CEN/burst/20260703T100000Z" ] && [ -d "$CEN/burst/20260704T100000Z" ] \
    && ok "E1 the two oldest single runs of the burst tool are pruned" || bad "E1 burst runs: $(ls "$CEN/burst" | tr '\n' ' ')"
  [ "$(count_dirs "$CEN/burst")" = 7 ] && ok "E2 the 5-department repair (seconds apart) is kept WHOLE as one run" || bad "E2 burst tool holds $(count_dirs "$CEN/burst") folders, wanted 7"

  hdr "F: a second run is a no-op"
  local cen_before live_after_1; cen_before="$(snap_all "$CEN")"; live_after_1="$(snap_all "$SB/oc")"
  out="$(python3 "$CB" migrate 2>&1)"; rc=$?
  [ "$rc" = 0 ] && printf '%s\n' "$out" | grep -q 'moved 0 backup folder' && ok "F1 second run moves nothing" || bad "F1 second run: rc=$rc $out"
  [ "$(snap_all "$CEN")" = "$cen_before" ] && [ "$(snap_all "$SB/oc")" = "$live_after_1" ] && ok "F2 second run changed nothing, central or live" || bad "F2 second run changed the box"

  hdr "G: OPENCLAW_BACKUP_KEEP overrides the count"
  OPENCLAW_BACKUP_KEEP=2 python3 "$CB" prune --tool repair-x >/dev/null 2>&1
  [ "$(count_dirs "$CEN/repair-x")" = 2 ] && [ -d "$CEN/repair-x/20260605T100000Z" ] && [ -d "$CEN/repair-x/20260604T100000Z" ] \
    && ok "G1 keep=2 leaves the newest 2" || bad "G1 keep=2 left: $(ls "$CEN/repair-x" | tr '\n' ' ')"
  OPENCLAW_BACKUP_KEEP=banana python3 "$CB" prune --tool repair-x >/dev/null 2>&1
  [ "$(count_dirs "$CEN/repair-x")" = 2 ] && ok "G2 a junk value falls back to the default 3 (nothing more is pruned)" || bad "G2 junk keep value pruned"
  export HOME="$S_HOME"; unset OPENCLAW_ROOT OPENCLAW_BACKUP_DIR
}

# =============================== real run ====================================
echo "== backups-out-of-departments =="
suite "$CB_REAL"

# ----- H: update-skills.sh wiring -------------------------------------------------
hdr "H: update-skills.sh runs the step every roll, and the shipped function works"
US="$REPO_ROOT/update-skills.sh"
FN_FILE="$SANDBOX/fn.sh"
awk '/^migrate_backups_out_of_departments\(\) \{/{f=1} f{print} f && /^\}$/{exit}' "$US" > "$FN_FILE"
[ -s "$FN_FILE" ] && ok "H1 update-skills.sh defines migrate_backups_out_of_departments" || bad "H1 function missing from update-skills.sh"
CALLS="$(grep -n '^  migrate_backups_out_of_departments || true' "$US" | cut -d: -f1 | tr '\n' ' ')"
RECLAIM_LINE="$(grep -n '^  reclaim_unify_backups || true' "$US" | head -1 | cut -d: -f1)"
WIRED_DONE="$(grep -n 'Wiring complete:' "$US" | head -1 | cut -d: -f1)"
CCE_LINE="$(grep -n '^_content_current_exit() {' "$US" | cut -d: -f1)"
set -- $CALLS
if [ "$#" = 2 ] && [ "$1" -gt "$CCE_LINE" ] && [ "$1" -lt "$(awk -v s="$CCE_LINE" 'NR>s && /^}/ {print NR; exit}' "$US")" ]; then
  ok "H2 the content-current exit (no-change roll) runs the step"
else bad "H2 _content_current_exit does not call the step (calls at: $CALLS)"; fi
if [ "$#" = 2 ] && [ "${2:-0}" -gt "$RECLAIM_LINE" ] && [ "${2:-0}" -gt "$WIRED_DONE" ]; then
  ok "H3 the end-of-roll call sits after the wiring loop (outside the .wired sentinel)"
else bad "H3 end-of-roll call not after the wiring loop (calls: $CALLS, wiring done at $WIRED_DONE)"; fi
SB="$SANDBOX/h"; mkdir -p "$SB/home" "$SB/skills/shared-utils"
cp "$CB_REAL" "$SB/skills/shared-utils/central_backup.py"
build_fixture "$SB"
OUT="$(HOME="$SB/home" OPENCLAW_ROOT="$SB/oc" OPENCLAW_BACKUP_DIR="$SB/central" SKILLS_DIR="$SB/skills" OC_WS_RESOLVED="$SB/oc/workspace" \
      bash -c 'set -euo pipefail; . "$1"; migrate_backups_out_of_departments; echo "rc=$?"' _ "$FN_FILE" 2>&1)"
printf '%s\n' "$OUT" | grep -q '^rc=0$' && [ -f "$SB/central/floor-backups/20260623T182141Z/AGENTS.md" ] \
  && [ ! -e "$SB/oc/workspace/.floor-backups" ] && [ -d "$SB/oc/workspace/departments/back-office" ] \
  && ok "H4 the shipped function (under set -euo pipefail) moves the folders and returns 0" || bad "H4 shipped function: $OUT"
OUT="$(HOME="$SB/home" OPENCLAW_ROOT="$SB/oc" SKILLS_DIR="$SB/nowhere" EXTRACTED_DIR="$SB/nowhere" _SCRIPT_DIR="$SB/nowhere" \
      bash -c 'set -euo pipefail; . "$1"; migrate_backups_out_of_departments; echo "rc=$?"' _ "$FN_FILE" 2>&1)"
printf '%s\n' "$OUT" | grep -q 'SKIP: shared-utils/central_backup.py not found' && printf '%s\n' "$OUT" | grep -q '^rc=0$' \
  && ok "H5 a bundle without the tool skips and never fails the roll" || bad "H5 missing-tool path: $OUT"

# ----- I: platform rule + root refusal ---------------------------------------------
hdr "I: backup root follows the platform rule; root is refused"
if [ "$(uname -s)" = Darwin ]; then WANT="$SANDBOX/ih/Downloads/openclaw-backups"; else WANT="$SANDBOX/ir/backups"; fi
mkdir -p "$SANDBOX/ir"
W1="$(HOME="$SANDBOX/ih" OPENCLAW_ROOT="$SANDBOX/ir" env -u OPENCLAW_BACKUP_DIR python3 "$CB_REAL" where)"
[ "$W1" = "$WANT" ] && ok "I1 default backup root follows the platform rule (macOS: Downloads/openclaw-backups; Linux, both Docker layouts: <OpenClaw root>/backups)" || bad "I1 backup root '$W1', wanted '$WANT'"
[ "$(OPENCLAW_BACKUP_DIR=/x/y python3 "$CB_REAL" where)" = /x/y ] && ok "I2 OPENCLAW_BACKUP_DIR pins the root" || bad "I2 OPENCLAW_BACKUP_DIR ignored"
mkdir -p "$SANDBOX/root/oc/workspace/departments/a.bak-x-20260101T000000Z"
RC="$(cd "$REPO_ROOT/shared-utils" && HOME="$SANDBOX/root" OPENCLAW_ROOT="$SANDBOX/root/oc" OPENCLAW_BACKUP_DIR="$SANDBOX/root/central" \
      python3 -c 'import os, central_backup as c; os.geteuid = lambda: 0; print(c.main(["migrate"]))' 2>&1 | tail -1)"
[ "$RC" = 4 ] && [ -d "$SANDBOX/root/oc/workspace/departments/a.bak-x-20260101T000000Z" ] && [ ! -e "$SANDBOX/root/central" ] \
  && ok "I3 as root: exit 4 REFUSED and nothing moved" || bad "I3 root guard returned '$RC'"
python3 "$CB_REAL" run-dir --tool '../evil' >/dev/null 2>&1; [ "$?" = 2 ] && ok "I4 an unsafe tool name is refused" || bad "I4 unsafe tool name accepted"

# ----- J: the writer apply-u004-phase2.sh --------------------------------------------
hdr "J: apply-u004-phase2.sh keeps its backups out of the department"
JB="$SANDBOX/j"; mkdir -p "$JB/home/.openclaw/skills/shared-utils" "$JB/bk" "$JB/home/.openclaw/skills/universal-sops/presentation-slide-craft" \
  "$JB/home/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/presentations/sops"
cp "$CB_REAL" "$JB/home/.openclaw/skills/shared-utils/central_backup.py"
S="$JB/home/.openclaw/skills"
echo '{}' > "$S/universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
echo r > "$S/universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md"
echo r > "$S/23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md"
( cd "$JB/bk" && echo payload > p.txt && tar czf Presentations-FULL.tar.gz p.txt && shasum -a 256 Presentations-FULL.tar.gz > Presentations-FULL.tar.gz.sha256 ) 2>/dev/null
DEPT="$JB/home/.openclaw/workspace/departments/Presentations"
mkdir -p "$DEPT/sops" "$DEPT/scripts"
echo scaffold > "$DEPT/sops/AGENTS.md"
echo old > "$DEPT/scripts/build_deck.py.bak-reconcile-20260616-120021"
OUT="$(HOME="$JB/home" SKILLS_DIR="$S" BK="$JB/bk" OPENCLAW_ROOT="$JB/home/.openclaw" OPENCLAW_BACKUP_DIR="$JB/central" \
      bash "$REPO_ROOT/scripts/apply-u004-phase2.sh" 2>&1)"; RC=$?
RUN="$(ls -d "$JB"/central/apply-u004-phase2/*/ 2>/dev/null | head -1)"
[ "$RC" = 0 ] && [ -n "$RUN" ] && [ -f "${RUN}misfiled-scaffold/sops/AGENTS.md" ] && [ -f "${RUN}bak-archive/scripts/build_deck.py.bak-reconcile-20260616-120021" ] \
  && ok "J1 the misfiled scaffold file and the .bak file land in the central folder" || bad "J1 writer run rc=$RC, run dir '$RUN': $(printf '%s' "$OUT" | tail -3)"
[ -z "$(find "$DEPT" -name 'misfiled-scaffold-*' -o -name 'bak-archive-*' 2>/dev/null)" ] && [ -f "$DEPT/sops/PIPELINE-MANIFEST.json" ] \
  && ok "J2 nothing was written into the department tree (and the rulebook did install)" || bad "J2 backup folder written inside the department"

# ----- K: mutants -------------------------------------------------------------------
hdr "K: the same checks catch five broken copies of the module (failability)"
mutant() {  # name, python snippet that edits the copy
  local name="$1" snip="$2" m="$SANDBOX/mut-$1.py" pf pf2
  cp "$CB_REAL" "$m"
  python3 - "$m" "$snip" <<'PY'
import re, sys
p, which = sys.argv[1], sys.argv[2]
s = open(p).read()
edits = {
  "widen":  (r'^BAK_DIR_RE = .*$', 'BAK_DIR_RE = re.compile(r"ba", re.IGNORECASE)'),
  "noprune": (r'return max\(n, 1\)', 'return 99'),
  "nomove": (r'shutil\.move\(str\(src\), str\(dest\)\)', 'pass'),
  "nogroup": (r'^RUN_GAP = 120.*$', 'RUN_GAP = 0'),
  "delete": (r'shutil\.move\(str\(src\), str\(dest\)\)', 'shutil.rmtree(str(src)); os.makedirs(str(dest))'),
}
pat, rep = edits[which]
new, n = re.subn(pat, rep, s, flags=re.M)
if n != 1:
    sys.exit("mutation %s matched %d places" % (which, n))
open(p, "w").write(new)
PY
  [ $? = 0 ] || { bad "K mutant '$name' could not be built"; return; }
  pf=$FAIL; pf2=$PASS; QUIET=1; suite "$m" >/dev/null 2>&1; QUIET=0
  local caught=$((FAIL - pf)); FAIL=$pf; PASS=$pf2   # the mutant's failures are the point, not ours
  [ "$caught" -gt 0 ] && ok "K mutant '$name' is caught ($caught check(s) went red)" || bad "K mutant '$name' SURVIVED: the checks cannot see it"
}
mutant widen widen
mutant noprune noprune
mutant nomove nomove
mutant nogroup nogroup
mutant delete delete

echo ""
echo "=== backups-out-of-departments: $PASS passed, $FAIL failed ==="
[ "$FAIL" = 0 ]
