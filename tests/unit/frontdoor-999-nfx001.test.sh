#!/usr/bin/env bash
# NFX001: frontdoor_update_999 gives EVERY box a clean, current 999-setup and links
# its skills (B1 Documents copy, B2 dirty copy untouched, B3 clone when absent,
# B4 link step from an unrelated cwd, B5 per-skill hand-managed skip).
# Hermetic: fake origin via git insteadOf, HOME=mktemp, no network.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
O="$T/origin"; SD="$O/.claude/skills/nine-router-setup/scripts"
mkdir -p "$O/CONTROL" "$SD/common"
echo x > "$O/AGENT_INSTALL.md"; printf 'nine-router-setup\nkaizen\neli5\n' > "$O/CONTROL/bundled-skills.txt"
for s in nine-router-setup kaizen eli5; do mkdir -p "$O/.claude/skills/$s"; echo "# $s" > "$O/.claude/skills/$s/SKILL.md"; done
echo ': settings-lock stub' > "$SD/common/settings-lock.sh"
# Stub installer keeps the real script's $0-derived layout (the B4 trap) and a main()
# that would leave INSTALLER_RAN if the full installer were ever run.
cat > "$SD/setup-macos.sh" <<'SEOF'
#!/bin/bash
set -euo pipefail
_D="$(cd "$(dirname "$0")" && pwd)"
. "$_D/common/settings-lock.sh"
bundled_skills() { grep -v '^#' "$REPO_ROOT/CONTROL/bundled-skills.txt"; }
resolve_skill_source() { (cd "$REPO_SKILL_DIR/../$1" 2>/dev/null && pwd -P) || true; }
link_one_skill() { ln -sfn "$1" "$2" && echo "skill linked: $3"; }
main() { touch "$HOME/INSTALLER_RAN"; }
main "$@"
SEOF
git -C "$O" init -q && git -C "$O" add -A && git -C "$O" -c user.email=a@b -c user.name=t commit -qm i
GITENV=(GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="url.$O.insteadOf" GIT_CONFIG_VALUE_0="https://github.com/trevorotts1/999-setup.git")
run(){ (cd / && env HOME="$1" NINEROUTER_PORT=1 "${GITENV[@]}" bash -c 'source "$1"; frontdoor_update_999' _ "$REPO/shared-utils/lib-frontdoor.sh" 2>&1); }
clone(){ env "${GITENV[@]}" git clone -q https://github.com/trevorotts1/999-setup.git "$1"; }
phys(){ (cd "$1" && pwd -P); }

# B1: Documents copy found and fast-forwarded (no extra clone made)
mkdir -p "$T/h1/Documents"; clone "$T/h1/Documents/999-setup"
echo new > "$O/new.txt"; git -C "$O" add -A; git -C "$O" -c user.email=a@b -c user.name=t commit -qm n
out="$(run "$T/h1")"
[ "$(git -C "$T/h1/Documents/999-setup" rev-parse HEAD)" = "$(git -C "$O" rev-parse HEAD)" ] && ok "B1 Documents copy fast-forwarded" || bad "B1 not ff'd: $out"
[ ! -e "$T/h1/999-setup" ] && ok "B1 no needless clone" || bad "B1 cloned anyway"

# B2 + B5 + repoint: dirty Documents copy untouched, clean ~/999-setup made, links point to it
mkdir -p "$T/h2/Documents" "$T/h2/.claude/skills"; clone "$T/h2/Documents/999-setup"
echo owner-edit >> "$T/h2/Documents/999-setup/AGENT_INSTALL.md"
ln -s "$T/h2/Documents/999-setup/.claude/skills/kaizen" "$T/h2/.claude/skills/kaizen"   # stale link into the dirty copy
mkdir -p "$T/h2/.claude/skills/eli5"; echo hand > "$T/h2/.claude/skills/eli5/mine.txt"   # B5 hand-managed
out="$(run "$T/h2")"
[ "$(tail -n1 "$T/h2/Documents/999-setup/AGENT_INSTALL.md")" = owner-edit ] && ok "B2 dirty copy untouched" || bad "B2 dirty copy changed"
[ -d "$T/h2/999-setup/.git" ] && ok "B2 clean ~/999-setup created" || bad "B2 no clean copy: $out"
echo "$out" | grep -q "UNTOUCHED.*Documents/999-setup" && ok "B2 untouched copy named in log" || bad "B2 no log line: $out"
[ "$(phys "$T/h2/.claude/skills/kaizen")" = "$(phys "$T/h2/999-setup/.claude/skills/kaizen")" ] && ok "B2 stale link repointed to clean copy" || bad "B2 link not repointed"
[ "$(phys "$T/h2/.claude/skills/nine-router-setup")" = "$(phys "$T/h2/999-setup/.claude/skills/nine-router-setup")" ] && ok "B2 other skills linked" || bad "B5 others not linked: $out"
[ -d "$T/h2/.claude/skills/eli5" ] && [ ! -L "$T/h2/.claude/skills/eli5" ] && [ -f "$T/h2/.claude/skills/eli5/mine.txt" ] && ok "B5 real dir skipped and untouched" || bad "B5 real dir touched"
echo "$out" | grep -q "HAND-MANAGED, skipped: eli5" && ok "B5 skip logged" || bad "B5 skip not logged"

# B3 + B4: no checkout anywhere -> cloned + linked from cwd=/ ; installer never run; no 9Router files
mkdir -p "$T/h3"; out="$(run "$T/h3")"
[ -d "$T/h3/999-setup/.git" ] && [ -L "$T/h3/.claude/skills/kaizen" ] && ok "B3 cloned and linked" || bad "B3: $out"
[ ! -e "$T/h3/INSTALLER_RAN" ] && [ ! -e "$T/h3/.9router" ] && [ ! -e "$T/h3/.local" ] && ok "B3 installer/9Router untouched" || bad "B3 installer ran"
echo "$out" | grep -q "No such file" && bad "B4 path error: $out" || ok "B4 link step works from unrelated cwd"
exit $fail
