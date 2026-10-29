#!/usr/bin/env bash
# tests/unit/client-skills-untouched.test.sh
#
# Standing rule: when a client has extra skills, the weekly update never deletes, moves or
# modifies them (the client may have built the skill themselves). A "client-made" skill is a
# numbered folder in the live skills dir that the repo does not ship.
#
# This plants two client-made skill folders (with nested files, an executable, a hidden file
# and a preflight.sh that the wiring loop would run) beside shipped ones, then drives every
# weekly-path step that counts, moves, archives, snapshots, restores, wires or verifies skill
# folders, and proves the client folders are byte-identical afterwards:
#   1. update-skills.sh: the client-made test + count (FLEET-PREFLIGHT-V1 block)
#   2. update-skills.sh: the three loops over the live skills dir carry the guard, and the
#      install loop (the only deleting loop) walks the REPO's folders, never the live ones
#   3. update-skills.sh: archived-skill retirement (moves only tombstoned, repo-shipped names)
#   4. fleet_refresh_runner: snapshot and rollback (managed entries only)
#   5. onboarding-state.sh: the gate's installed-vs-expected comparison
# Hermetic; nothing touches a real box.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }

SK="$T/oc/skills"; SRC="$T/src"
mkdir -p "$SK" "$SRC"
for s in 01-alpha 23-beta 11-old-ARCHIVED; do mkdir -p "$SRC/$s"; echo "shipped $s" > "$SRC/$s/SKILL.md"; done
mkdir -p "$SRC/docs"; echo '{"archived":{"11-old-ARCHIVED":{}}}' > "$SRC/docs/archived-skill-tombstones.json"
for s in 01-alpha 23-beta 11-old; do mkdir -p "$SK/$s"; echo "old $s" > "$SK/$s/SKILL.md"; done
mkdir -p "$SK/01-alpha.bak-roll-20261001"; echo b > "$SK/01-alpha.bak-roll-20261001/f"
for c in 58-ghl-page-rebuild 44-video-overlay-playbook; do
  mkdir -p "$SK/$c/scripts/deep" "$SK/$c/config"
  echo "client work in $c" > "$SK/$c/SKILL.md"
  printf '#!/bin/sh\necho CLIENT-PREFLIGHT-RAN > "%s/ran-$$"\n' "$T" > "$SK/$c/preflight.sh"; chmod +x "$SK/$c/preflight.sh"
  echo '{}' > "$SK/$c/config/model-map.template.json"
  echo secret-ish > "$SK/$c/.hidden"; echo deep > "$SK/$c/scripts/deep/x.py"
done
echo 1.0 > "$SK/.onboarding-version"
chash(){ (cd "$SK" && find 58-ghl-page-rebuild 44-video-overlay-playbook -print0 | sort -z | xargs -0 shasum 2>/dev/null | shasum | cut -d' ' -f1; \
          find 58-ghl-page-rebuild 44-video-overlay-playbook -type f -exec stat -f '%Sp %z' {} + 2>/dev/null | sort | shasum | cut -d' ' -f1); }
BEFORE="$(chash)"; [ -n "$BEFORE" ] || { bad "could not hash the fixture"; exit 1; }

# ---- 1. the client-made test and the count --------------------------------------------------
awk '/^#=== BEGIN FLEET-PREFLIGHT-V1 ===$/,/^#=== END FLEET-PREFLIGHT-V1 ===$/' "$REPO/update-skills.sh" | grep -v '^fleet_preflight_checks$' > "$T/pf.sh"
[ -s "$T/pf.sh" ] && bash -n "$T/pf.sh" && ok "extracted the FLEET-PREFLIGHT-V1 block" || { bad "block missing"; exit 1; }
res="$(EXTRACTED_DIR="$SRC" bash -c 'source "$1"
  for n in 58-ghl-page-rebuild 44-video-overlay-playbook; do oc_skill_is_client_made $n && echo "client:$n"; done
  for n in 01-alpha 23-beta 11-old 01-alpha.bak-roll-20261001; do oc_skill_is_client_made $n || echo "repo:$n"; done
  echo "count:$(oc_count_client_skills "$2")"' _ "$T/pf.sh" "$SK")"
[[ "$res" == *"client:58-ghl-page-rebuild"* && "$res" == *"client:44-video-overlay-playbook"* ]] && ok "client-made skills recognised" || bad "client skills not recognised: $res"
[[ "$res" == *"repo:01-alpha"* && "$res" == *"repo:23-beta"* && "$res" == *"repo:11-old"* && "$res" == *"repo:01-alpha.bak-roll-20261001"* ]] && ok "shipped, archived-tombstone and updater-backup folders keep today's handling" || bad "wrongly classified: $res"
[[ "$res" == *"count:2"* ]] && ok "skills_client_extra counts exactly the two client skills" || bad "count wrong: $res"
r2="$(EXTRACTED_DIR="" bash -c 'source "$1"; oc_skill_is_client_made 58-ghl-page-rebuild && echo client || echo unknown' _ "$T/pf.sh")"
[ "$r2" = unknown ] && ok "no source bundle known: nothing is classified (today's behaviour)" || bad "classified without a bundle"

# ---- 2. every loop over the live skills dir is guarded; the deleting loop walks the repo ----
python3 - "$REPO/update-skills.sh" <<'PY' && ok "wiring, wired-sentinel and verification loops skip client-made skills; install loop walks the repo's folders" || bad "loop guards missing"
import re, sys
s = open(sys.argv[1]).read()
for loop in (r'for _wskill_dir in "\$SKILLS_DIR"/\[0-9\]\*/; do', r'for SKILL_DIR in "\$SKILLS_DIR"/\[0-9\]\*/; do', r'for _gskill in "\$SKILLS_DIR"/\[0-9\]\*/; do'):
    m = re.search(loop, s); assert m, loop
    assert "oc_skill_is_client_made" in s[m.end():m.end() + 900], loop
m = re.search(r'for SKILL_DIR in "\$EXTRACTED_DIR"/\[0-9\]\*/; do', s); assert m
rm = [x.start() for x in re.finditer(r'oc_remove_tree_guarded "\$SKILLS_DIR/\$SKILL_NAME"', s)]
assert len(rm) == 1 and 0 < rm[0] - m.end() < 20000, rm   # the only skill-tree removal sits in the repo-folder loop
# every tree removal in the updater names a folder the repo ships; the old hand-installed
# 70-diagnose-explain-fix removal is gone (report-only now)
targets = sorted(set(re.findall(r'oc_remove_tree_guarded "([^"]+)"', s)))
assert targets == ['$SKILLS_DIR/$SKILL_NAME', '$SKILLS_DIR/32-command-center-setup', '$SKILLS_DIR/universal-sops', '$_dir'] or \
       targets == ['$SKILLS_DIR/$SKILL_NAME', '$SKILLS_DIR/32-command-center-setup', '$SKILLS_DIR/universal-sops'], targets
assert '_STRAY_DEF" "skill"' not in s
PY

# ---- 3. archived-skill retirement ----------------------------------------------------------
awk '/^    python3 - "\$_TOMB_JSON"/{f=1;next} /^PYEOF/{f=0} f' "$REPO/update-skills.sh" > "$T/retire.py"
python3 "$T/retire.py" "$SRC/docs/archived-skill-tombstones.json" "$SK" "$T/oc/retired-skills" >/dev/null
[ ! -e "$SK/11-old" ] && [ -d "$T/oc/retired-skills/11-old" ] && ok "the tombstoned (repo-shipped) skill was retired" || bad "retirement did not run"
[ "$(chash)" = "$BEFORE" ] && ok "retirement left the client skills byte-identical" || bad "retirement changed a client skill"

# ---- 4. runner snapshot, simulated update, rollback ----------------------------------------
python3 -I - "$REPO" "$T" "$SK" "$SRC" <<'PY' && ok "snapshot/rollback manage only shipped entries; client skills stay in place" || bad "runner snapshot/rollback touched client skills"
import sys, os, tarfile, shutil
from pathlib import Path
repo, t, sk, src = sys.argv[1:5]
sys.path.insert(0, repo + "/shared-utils")
import fleet_refresh_runner as r
sk, src = Path(sk), Path(src)
ents = r._managed_skill_entries(sk, src)
assert "58-ghl-page-rebuild" not in ents and "44-video-overlay-playbook" not in ents, ents
assert {"01-alpha", "23-beta"} <= set(ents), ents
paths = {"root": str(Path(t) / "oc"), "skills": str(sk), "cc_dir": None}
res = r.BoxResult("b", False)
assert r.take_snapshot(paths, src, res), res.snapshot
with tarfile.open(res.snapshot["skills_archive"]) as tf:
    names = tf.getnames()
assert not any(n.startswith(("58-", "44-")) for n in names), names
# a bad update: shipped skills replaced, then rolled back
for e in ("01-alpha", "23-beta"):
    shutil.rmtree(sk / e); (sk / e).mkdir(); (sk / e / "SKILL.md").write_text("NEW")
ok = r.rollback_box(paths, src, res, ["test"])
assert ok, res.rollback
assert (sk / "01-alpha" / "SKILL.md").read_text().startswith("old"), "shipped skill restored"
assert (sk / "58-ghl-page-rebuild").is_dir() and (sk / "44-video-overlay-playbook").is_dir()
assert r._client_extra_skills(sk, src) == ["44-video-overlay-playbook", "58-ghl-page-rebuild"]
PY
[ "$(chash)" = "$BEFORE" ] && ok "snapshot + rollback left the client skills byte-identical" || bad "snapshot/rollback changed a client skill"

# ---- 5. the gate's installed-vs-expected comparison ----------------------------------------
cat > "$T/ws.json" <<'JSON'
{"version":"1.0","discoveredSkills":["01-alpha","23-beta"],
 "skills":{"01-alpha":{"status":"qc-passed"},"23-beta":{"status":"qc-passed"},
           "58-ghl-page-rebuild":{"status":"qc-failed"},"44-video-overlay-playbook":{"status":"pending"}}}
JSON
mkdir -p "$T/h"
out="$(env -i HOME="$T/h" PATH="$PATH" OPENCLAW_ROOT="$T/h/.openclaw" bash -c 'source "$1" 2>/dev/null; OBS_STATE_FILE="$2"; obs_gate_summary "$3"' _ "$REPO/scripts/onboarding-state.sh" "$T/ws.json" "$SK" 2>&1)"; rc=$?
[ "$rc" = 0 ] && [[ "$out" == *'"ok": true'* && "$out" == *'"total": 2'* && "$out" == *'"skills_client_extra": 2'* ]] \
  && ok "client skills do not fail installed-vs-expected and are reported as skills_client_extra" || bad "gate summary wrong (rc=$rc): $out"
python3 -c "import json;d=json.load(open('$T/ws.json'))['skills'];assert '58-ghl-page-rebuild' in d" && ok "the gate never removes the client skills from the state file" || bad "state entry removed"

! compgen -G "$T/ran-*" >/dev/null && ok "no client script was executed by any step" || bad "a client preflight.sh was run"
[ "$(chash)" = "$BEFORE" ] && ok "FINAL: both client skill folders byte-identical (content, names, modes)" || bad "FINAL: a client skill changed"
exit $fail
