#!/usr/bin/env bash
# D04/D05/D06: Contabo durable paths (master files, backups, 999-setup, skill 41 workspace) land on the volume; Mac/Hostinger unchanged.
# Plus the D2 boot-relink rule: the Contabo boot template must relink all five persist-home
# entries and must prove content equality before deleting a live folder (never `cp -an` +
# existence check + `rm -rf`, which is how the 2026-10-12 master-files wipe happened).
set -e
cd "${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../../.." && pwd)}"

( # step: Contabo durable-path suite
set -e
bash tests/unit/persistent-paths-contabo.test.sh
)

( # step: Contabo boot relink is conflict-preserving and covers all five entries
set -e -o pipefail
set -euo pipefail
CT=platform/vps/contabo/container-startup.sh
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
[ -f "$CT" ] || fail "the Contabo boot template is gone: $CT"

# 1. all five persist-home entries the skill requires, including the nested Downloads path.
for e in 999-setup .claude .local .agent-browser Downloads/openclaw-master-files; do
  grep -qF -- "$e" "$CT" || fail "the relink set no longer names '$e' (SKILL.md D2 requires five entries)."
done
grep -qE '^PERSIST_HOME_ENTRIES=' "$CT" || fail "no PERSIST_HOME_ENTRIES list; the five-entry relink set is not declared once."

# 2. the destructive shape must never come back: cp -an, an existence-only check, then rm -rf.
if grep -qE 'cp -an[[:space:]]+"\$_p"' "$CT"; then
  fail "cp -an is back in the relink: it silently skips a differing destination file, which a later rm -rf then destroys."
fi
# 3. rm -rf of a live folder is allowed only through a content-verified _safe_merge.
grep -qE 'if _safe_merge "\$_p" "\$_d"; then' "$CT" \
  || fail "rm -rf is no longer gated on _safe_merge (content-verified merge)."
grep -q 'cmp -s' "$CT" || fail "_relink_conflicts lost its byte comparison (cmp -s); existence checks are not preservation proof."
# 4. a conflict refuses that folder's relink and keeps both copies (fail-soft, no exit).
grep -q 'RELINK-REFUSED' "$CT" || fail "a conflict no longer refuses the relink explicitly."
grep -q 'persist-home-conflict.log' "$CT" || fail "conflicts are no longer written to <root>/logs/persist-home-conflict.log."
if awk '/^_safe_merge\(\)/,/^}/' "$CT" | grep -qE '^[[:space:]]*exit 1'; then
  fail "_safe_merge exits 1 on mismatch: that kills the boot script and the gateway never starts (crash loop)."
fi
# 5. the nested entry must create its parents before linking.
grep -qE 'mkdir -p "\$\(dirname "\$_p"\)"' "$CT" || fail "the nested Downloads entry no longer creates its parent folder."
printf 'PASS: Contabo boot relink is content-verified, five-entry and fail-soft.\n'
)
