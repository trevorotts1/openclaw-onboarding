#!/usr/bin/env bash
# D04/D05/D06: on Contabo the container $HOME is a throwaway layer and ONLY the
# OpenClaw root (~/.openclaw) is a mounted volume. Master files, skills-rollback
# backups and the 999-setup checkout must land under that root, the Skill 41
# core-file writer must edit the CONFIGURED workspace (not $HOME/clawd), and Mac
# and Hostinger ($HOME itself is the volume) must keep their old paths.
# Hermetic: stubbed `mountpoint` and `uname`, temp HOME and OpenClaw root, fake
# git origin via insteadOf, no network, no box touched.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
eq(){ [ "$2" = "$3" ] && ok "$1" || bad "$1: got [$2] want [$3]"; }

# --- stubs: mountpoint answers true only for the dirs listed in $FAKE_MOUNTS
# (colon separated); uname -s answers $FAKE_UNAME (default Linux).
B="$T/bin"; mkdir -p "$B"
cat > "$B/mountpoint" <<'EOF'
#!/bin/sh
[ "$1" = "-q" ] && shift
case "$(printf '%s' "$FAKE_MOUNTS" | tr ':' '\n' | grep -Fx -- "${1%/}")" in "") exit 1 ;; *) exit 0 ;; esac
EOF
cat > "$B/uname" <<'EOF'
#!/bin/sh
[ "$1" = "-s" ] && { echo "${FAKE_UNAME:-Linux}"; exit 0; }
exec /usr/bin/uname "$@"
EOF
chmod +x "$B/mountpoint" "$B/uname"
# A throwaway "box": $1=name -> HOME=$T/$1/home, OpenClaw root=$HOME/.openclaw
mkbox(){ mkdir -p "$T/$1/home/.openclaw/workspace" "$T/$1/home/clawd"; }

# runbox <name> <FAKE_MOUNTS> <FAKE_UNAME> cmd... : run cmd with the stubs on that box
runbox(){
  local name="$1" mounts="$2" un="$3"; shift 3
  ( cd / && env -u OPENCLAW_MASTER_FILES_DIR -u MASTER_FILES_DIR -u OPENCLAW_BACKUP_DIR \
      -u OPENCLAW_WORKSPACE -u WORKSPACE_ROOT -u OC_ROOT -u OC_CONFIG \
      PATH="$B:$PATH" HOME="$T/$name/home" FAKE_MOUNTS="$mounts" FAKE_UNAME="$un" \
      OPENCLAW_ROOT="$T/$name/home/.openclaw" OPENCLAW_ROOT_DIR="$T/$name/home/.openclaw" "$@" )
}
paths_of(){ # bp | pr_master | pr_backup | lmf
  runbox "$1" "$2" "$3" bash -c '
    . "$0/scripts/lib-bootstrap-pointer.sh"; . "$0/70-lean-core-file-system/scripts/lib-paths.sh"
    . "$0/41-build-with-ai-playbook/scripts/lib-master-files.sh"
    echo "$(bp_master_files_dir)|$(pr_master_files)|$(pr_backup_root)|$(resolve_master_files_dir)"' "$REPO"
}
common_of(){ # OC_DOWNLOADS|OC_BACKUPS
  runbox "$1" "$2" "$3" bash -c '. "$0/platform/common.sh"; oc_set_platform_paths >/dev/null 2>&1; echo "$OC_DOWNLOADS|$OC_BACKUPS"' "$REPO"
}

# update-skills.sh: the backup root and the CORE_UPDATES master-files variable (blocks extracted, run as-is)
US="$REPO/update-skills.sh"
awk '/if _SKILLS_BACKUP_ROOT="\$\(oc_persist_root/{p=1} p{print} p&&/^  fi$/{exit}' "$US" > "$T/us-backup.sh"
awk '/local _cu_proot=""/{p=1} p{print} p&&/^    fi$/{exit}' "$US" > "$T/us-cu.sh"
[ -s "$T/us-backup.sh" ] && [ -s "$T/us-cu.sh" ] && ok "update-skills.sh blocks extracted" || bad "could not extract update-skills.sh blocks"
us(){ runbox "$1" "$2" "$3" bash -c '. "$0/platform/common.sh"; f(){ . "$1"; echo "$_SKILLS_BACKUP_ROOT"; }; g(){ . "$1"; echo "$CU_MASTER_FILES_DIR"; }; echo "$(f "$1")|$(g "$2")"' "$REPO" "$T/us-backup.sh" "$T/us-cu.sh"; }

# 999-setup fixture: fake origin served through git insteadOf
O="$T/origin"; SD="$O/.claude/skills/nine-router-setup/scripts"
mkdir -p "$O/CONTROL" "$SD/common"; echo x > "$O/AGENT_INSTALL.md"
printf 'nine-router-setup\n' > "$O/CONTROL/bundled-skills.txt"
mkdir -p "$O/.claude/skills/nine-router-setup"; echo "# s" > "$O/.claude/skills/nine-router-setup/SKILL.md"
echo ': stub' > "$SD/common/settings-lock.sh"
printf '#!/bin/bash\nset -euo pipefail\nbundled_skills(){ grep -v "^#" "$REPO_ROOT/CONTROL/bundled-skills.txt"; }\nresolve_skill_source(){ (cd "$REPO_SKILL_DIR/../$1" 2>/dev/null && pwd -P) || true; }\nlink_one_skill(){ ln -sfn "$1" "$2" && echo "skill linked: $3"; }\nmain(){ touch "$HOME/INSTALLER_RAN"; }\nmain "$@"\n' > "$SD/setup-macos.sh"
git -C "$O" init -q && git -C "$O" add -A && git -C "$O" -c user.email=a@b -c user.name=t commit -qm i
fd(){ runbox "$1" "$2" "$3" env NINEROUTER_PORT=1 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="url.$O.insteadOf" \
      GIT_CONFIG_VALUE_0="https://github.com/trevorotts1/999-setup.git" \
      bash -c 'source "$0/shared-utils/lib-frontdoor.sh"; frontdoor_update_999' "$REPO" 2>&1; }

# ===== Contabo: the OpenClaw root is the only mount =====
mkbox c; H="$T/c/home"; R="$H/.openclaw"
got="$(paths_of c "$R" Linux)"
eq "D04 Contabo bp_master_files_dir under the root" "$(echo "$got" | cut -d'|' -f1)" "$R/openclaw-master-files"
eq "D04 Contabo pr_master_files under the root" "$(echo "$got" | cut -d'|' -f2)" "$R/openclaw-master-files"
eq "D04 Contabo pr_backup_root under the root" "$(echo "$got" | cut -d'|' -f3)" "$R/backups"
eq "D05 Contabo resolve_master_files_dir under the root" "$(echo "$got" | cut -d'|' -f4)" "$R/openclaw-master-files"
eq "D04 Contabo OC_DOWNLOADS is the root, OC_BACKUPS under it" "$(common_of c "$R" Linux)" "$R|$R/backups"
got="$(us c "$R" Linux)"
eq "D04 Contabo update-skills.sh rollback backups under the root" "${got%%|*}" "$R/backups"
eq "D04 Contabo update-skills.sh CORE_UPDATES master files under the root" "${got##*|}" "$R/openclaw-master-files"

# explicit env wins, OPENCLAW_MASTER_FILES_DIR before MASTER_FILES_DIR, over the mount rule
e1="$(runbox c "$R" Linux env MASTER_FILES_DIR=/explicit/b bash -c '. "$0/scripts/lib-bootstrap-pointer.sh"; bp_master_files_dir' "$REPO")"
e2="$(runbox c "$R" Linux env MASTER_FILES_DIR=/explicit/b OPENCLAW_MASTER_FILES_DIR=/explicit/a bash -c '. "$0/scripts/lib-bootstrap-pointer.sh"; bp_master_files_dir' "$REPO")"
e3="$(runbox c "$R" Linux env MASTER_FILES_DIR=/explicit/b bash -c '. "$0/70-lean-core-file-system/scripts/lib-paths.sh"; pr_master_files' "$REPO")"
eq "D04 MASTER_FILES_DIR (the name the Contabo template exports) is honoured" "$e1" "/explicit/b"
eq "D04 OPENCLAW_MASTER_FILES_DIR beats MASTER_FILES_DIR" "$e2" "/explicit/a"
eq "D04 skill 70 honours MASTER_FILES_DIR" "$e3" "/explicit/b"

# D06: 999-setup cloned under <root>/persist-home, $HOME/999-setup is a symlink, relinked after a recreate
fd c "$R" Linux >/dev/null
[ -d "$R/persist-home/999-setup/.git" ] && ok "D06 Contabo 999-setup cloned under <root>/persist-home" || bad "D06 no clone under persist-home"
[ -L "$H/999-setup" ] && [ "$(cd "$H/999-setup" && pwd -P)" = "$(cd "$R/persist-home/999-setup" && pwd -P)" ] \
  && ok "D06 Contabo \$HOME/999-setup is a symlink to the persistent checkout" || bad "D06 no \$HOME symlink"
[ -L "$H/.claude/skills/nine-router-setup" ] && ok "D06 skills linked" || bad "D06 skills not linked"
rm -f "$H/999-setup"; rm -rf "$H/.claude"            # a container recreate: $HOME is gone, the volume is not
out="$(fd c "$R" Linux)"
[ -L "$H/999-setup" ] && ok "D06 symlink restored after a recreate" || bad "D06 symlink not restored: $out"
[ ! -e "$H/INSTALLER_RAN" ] && ok "D06 installer never run" || bad "D06 installer ran"

# D05: Skill 41 writes the CONFIGURED workspace, not $HOME/clawd; the rule reference lands under the root
mkdir -p "$R/ws-real"; printf '# AGENTS\n' > "$R/ws-real/AGENTS.md"; printf '# MEMORY\n' > "$R/ws-real/MEMORY.md"; printf '# TOOLS\n' > "$R/ws-real/TOOLS.md"
printf '# stray\n' > "$H/clawd/AGENTS.md"
printf '{"agents":{"defaults":{"workspace":"%s"}}}\n' "$R/ws-real" > "$R/openclaw.json"
stray_before="$(cat "$H/clawd/AGENTS.md")"
runbox c "$R" Linux bash "$REPO/41-build-with-ai-playbook/scripts/04-update-core-files.sh" >/dev/null 2>&1
grep -q "BEGIN skill-41 build-with-ai" "$R/ws-real/AGENTS.md" && ok "D05 block landed in the configured workspace AGENTS.md" || bad "D05 block missing from configured workspace"
eq "D05 stray \$HOME/clawd/AGENTS.md unchanged" "$(cat "$H/clawd/AGENTS.md")" "$stray_before"
[ ! -e "$H/clawd/AGENTS.md.skill41.bak" ] && ok "D05 no .skill41.bak in the stray folder" || bad "D05 backup written to stray folder"
[ -f "$R/openclaw-master-files/41-build-with-ai-playbook/references/memory-design-rules.md" ] && ok "D05 rule reference installed under <root>/openclaw-master-files" || bad "D05 rule reference not under the root"
mkdir -p "$T/ws-x"; printf '# X\n' > "$T/ws-x/AGENTS.md"
runbox c "$R" Linux env WORKSPACE_ROOT="$T/ws-x" bash "$REPO/41-build-with-ai-playbook/scripts/04-update-core-files.sh" >/dev/null 2>&1
grep -q "BEGIN skill-41 build-with-ai" "$T/ws-x/AGENTS.md" && ok "D05 explicit WORKSPACE_ROOT still wins" || bad "D05 explicit WORKSPACE_ROOT ignored"

# ===== Mac: unchanged (no mountpoint on a Mac; even a mounted root must not move anything) =====
mkbox m; MH="$T/m/home"; MR="$MH/.openclaw"
got="$(paths_of m "$MR" Darwin)"
eq "Mac bp_master_files_dir unchanged" "$(echo "$got" | cut -d'|' -f1)" "$MH/Downloads/openclaw-master-files"
eq "Mac pr_master_files unchanged" "$(echo "$got" | cut -d'|' -f2)" "$MH/Downloads/openclaw-master-files"
eq "Mac pr_backup_root unchanged" "$(echo "$got" | cut -d'|' -f3)" "$MH/Downloads/openclaw-backups"
eq "Mac resolve_master_files_dir unchanged" "$(echo "$got" | cut -d'|' -f4)" "$MH/Downloads/OpenClaw Master Files"
eq "Mac OC_DOWNLOADS/OC_BACKUPS unchanged" "$(common_of m "$MR" Darwin)" "$MH/Downloads|$MH/Downloads/openclaw-backups"
got="$(us m "$MR" Darwin)"
eq "Mac update-skills.sh backups unchanged" "${got%%|*}" "$MH/Downloads/openclaw-backups"
eq "Mac update-skills.sh CORE_UPDATES dir unchanged" "${got##*|}" "$MH/Downloads/openclaw-master-files"
fd m "$MR" Darwin >/dev/null
[ -d "$MH/999-setup/.git" ] && [ ! -L "$MH/999-setup" ] && [ ! -e "$MR/persist-home" ] && ok "Mac 999-setup cloned to \$HOME/999-setup, no persist-home" || bad "Mac 999-setup moved"

# ===== Hostinger: $HOME is itself the volume (only HOME mounted, or HOME and root both) =====
for mnt in hh both; do
  mkbox "h$mnt"; HH="$T/h$mnt/home"; HR="$HH/.openclaw"
  m="$HH"; [ "$mnt" = both ] && m="$HH:$HR"
  got="$(paths_of "h$mnt" "$m" Linux)"
  eq "Hostinger($mnt) bp_master_files_dir unchanged" "$(echo "$got" | cut -d'|' -f1)" "$HH/Downloads/openclaw-master-files"
  eq "Hostinger($mnt) pr_backup_root unchanged" "$(echo "$got" | cut -d'|' -f3)" "$HH/Downloads/openclaw-backups"
  eq "Hostinger($mnt) resolve_master_files_dir unchanged" "$(echo "$got" | cut -d'|' -f4)" "/data/openclaw-master-files"
  eq "Hostinger($mnt) OC_DOWNLOADS/OC_BACKUPS unchanged" "$(common_of "h$mnt" "$m" Linux)" "$HH/Downloads|$HR/backups"
  got="$(us "h$mnt" "$m" Linux)"
  eq "Hostinger($mnt) update-skills.sh backups unchanged" "${got%%|*}" "$HH/Downloads/openclaw-backups"
  fd "h$mnt" "$m" Linux >/dev/null
  [ -d "$HH/999-setup/.git" ] && [ ! -L "$HH/999-setup" ] && [ ! -e "$HR/persist-home" ] && ok "Hostinger($mnt) 999-setup cloned to \$HOME/999-setup" || bad "Hostinger($mnt) 999-setup moved"
done
exit $fail
