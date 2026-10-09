#!/usr/bin/env bash
# batch-prep.sh — do the mechanical bookkeeping that otherwise fails a batch's
# first CI run (then costs a whole second CI cycle). Idempotent: a second run
# changes nothing. Run from anywhere; bump-version.sh calls it on every bump.
#
#   1. G3 (version-consistency.yml): every skill dir (NN-name, not *-ARCHIVED,
#      not 23-ai-workforce-blueprint) whose content differs from the base but
#      whose skill-version.txt does not -> patch-bump skill-version.txt, keep
#      the SKILL.md frontmatter `version:` equal to it (skill-frontmatter-version
#      guard) and keep the trailing newline (skill-version-newline guard).
#   2. Library lockstep: register-library-additions.py, hash-content-manifest.py
#      and hash-universal-sops-manifest.py are re-run ONLY when their --check
#      fails (the stampers rewrite timestamps, so unconditional runs are not
#      idempotent).
#   3. Finish: bump-version.sh --check, then the same guard scripts CI runs
#      when fast_guards.py selects them for this diff (library-lockstep, skill-frontmatter-version-guard,
#      skill-version-newline-guard, kie-prompt-enforcer-guard).
#
# Env: BASE_REF (default origin/main)   BATCH_PREP_NO_GUARDS=1 (skip step 3 guards)
set -euo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"
BASE_REF="${BASE_REF:-origin/main}"
git rev-parse --verify -q "$BASE_REF^{commit}" >/dev/null \
  || { echo "batch-prep: base ref $BASE_REF not found (git fetch origin main)" >&2; exit 1; }
MB="$(git merge-base HEAD "$BASE_REF" 2>/dev/null || git rev-parse "$BASE_REF")"

# 1. skills ------------------------------------------------------------------
changed="$( { git diff --name-only --diff-filter=ACMR "$MB"; git ls-files -o --exclude-standard; } | sort -u)"
skills="$(printf '%s\n' "$changed" | awk -F/ 'NF>1 && $1 ~ /^[0-9]+-[A-Za-z]/ && $1 !~ /-ARCHIVED$/ && $1 != "23-ai-workforce-blueprint" && $NF != "skill-version.txt" {print $1}' | sort -u)"
bumped=0
for s in $skills; do
  vf="$s/skill-version.txt"
  [ -f "$vf" ] || continue
  # already bumped vs base (or brand-new file): nothing to do
  if ! git diff --quiet "$MB" -- "$vf" 2>/dev/null || git ls-files -o --exclude-standard -- "$vf" | grep -q .; then
    continue
  fi
  old="$(head -1 "$vf" | tr -d '[:space:]')"
  new="$(python3 - "$old" <<'PY'
import re, sys
m = re.fullmatch(r'(v?)(\d+)\.(\d+)\.(\d+)', sys.argv[1])
if not m: sys.exit("batch-prep: cannot parse version %r" % sys.argv[1])
print("%s%s.%s.%d" % (m[1], m[2], m[3], int(m[4]) + 1))
PY
)"
  printf '%s\n' "$new" > "$vf"
  if [ -f "$s/SKILL.md" ]; then
    python3 - "$s/SKILL.md" "$new" <<'PY'
import re, sys
p, new = sys.argv[1], sys.argv[2].lstrip('vV')
t = open(p, newline='').read()
m = re.match(r'---\r?\n', t)
if m:
    end = re.search(r'\r?\n---[ \t]*(\r?\n|$)', t[m.end():])
    fm_end = m.end() + (end.start() if end else 0)
    head = t[:fm_end]
    # keep the existing v-prefix / quote style, swap only the number
    head2 = re.sub(r'(?m)^(version:[ \t]*)(["\']?[vV]?)(\d+\.\d+\.\d+)(["\']?)', lambda mm: mm[1] + mm[2] + new + mm[4], head, count=1)
    if head2 != head:
        open(p, 'w', newline='').write(head2 + t[fm_end:])
PY
  fi
  echo "batch-prep: $s skill-version $old -> $new"
  bumped=$((bumped + 1))
done
[ "$bumped" -gt 0 ] || echo "batch-prep: no skill needed a bump"

# 2. library / SOP manifests ---------------------------------------------------
LIB=23-ai-workforce-blueprint/scripts
heal() { # heal <label> <check cmd> <fix cmd>
  [ -e "$(echo "$2" | awk '{print $2}')" ] || { echo "batch-prep: $1 skipped (script absent)"; return 0; }
  if eval "$2" >/dev/null 2>&1; then echo "batch-prep: $1 current"; else eval "$3" >/dev/null && echo "batch-prep: $1 re-stamped"; fi
}
heal library-register "python3 $LIB/register-library-additions.py --check" "python3 $LIB/register-library-additions.py --apply"
heal content-manifest "python3 $LIB/hash-content-manifest.py --check" "python3 $LIB/hash-content-manifest.py"
heal universal-sops "python3 scripts/hash-universal-sops-manifest.py --check" "python3 scripts/hash-universal-sops-manifest.py"

# 3. finish --------------------------------------------------------------------
[ -f scripts/bump-version.sh ] && bash scripts/bump-version.sh --check
if [ "${BATCH_PREP_NO_GUARDS:-0}" != 1 ]; then
  # run only the guards CI itself would select for this diff (fast_guards.py --list)
  now="$( { git diff --name-only "$MB"; git ls-files -o --exclude-standard; } | sort -u)"
  if [ -f scripts/ci/fast_guards.py ]; then
    sel="$(printf '%s\n' "$now" | python3 scripts/ci/fast_guards.py --list pull_request)"
  else sel=""; fi
  for g in library-lockstep skill-frontmatter-version-guard skill-version-newline-guard kie-prompt-enforcer-guard; do
    f="scripts/ci/fast-guards.d/$g.sh"
    [ -f "$f" ] || { echo "batch-prep: guard $g skipped (absent)"; continue; }
    grep -qx "$g" <<<"$sel" || { echo "batch-prep: guard $g not selected for this diff"; continue; }
    GITHUB_WORKSPACE="$R" bash "$f" >/dev/null 2>&1 && echo "batch-prep: guard $g PASS" \
      || { echo "batch-prep: guard $g FAIL (run: GITHUB_WORKSPACE=$R bash $f)" >&2; exit 1; }
  done
fi
echo "batch-prep: done"
