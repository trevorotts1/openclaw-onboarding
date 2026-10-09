#!/usr/bin/env bash
# test-batch-prep.sh — proves scripts/batch-prep.sh on a throwaway git repo:
#   (a) skill change without a bump gets bumped (skill-version.txt + SKILL.md frontmatter, newline kept)
#   (b) a SOP change gets the content manifest re-stamped
#   (c) a second run is a no-op (git status byte-identical)
#   (d) an already-bumped skill, and the 23 blueprint / ARCHIVED dirs, are left alone
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd "$T"; git init -q -b main .; git config user.email t@t; git config user.name t
mkdir -p scripts 23-ai-workforce-blueprint/scripts 23-ai-workforce-blueprint/sops 80-demo 81-bumped 99-old-ARCHIVED
cp "$SRC/scripts/batch-prep.sh" scripts/
# fake stamper: manifest holds the sha of the sop file; --check fails when stale
cat > 23-ai-workforce-blueprint/scripts/hash-content-manifest.py <<'PY'
import hashlib, sys
sop = open('23-ai-workforce-blueprint/sops/a.md','rb').read()
sha = hashlib.sha256(sop).hexdigest()
m = '23-ai-workforce-blueprint/manifest.txt'
if '--check' in sys.argv:
    sys.exit(0 if open(m).read().strip() == sha else 1)
open(m,'w').write(sha + '\n')
PY
printf 'sop v1\n' > 23-ai-workforce-blueprint/sops/a.md
python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py
for d in 80-demo 81-bumped 99-old-ARCHIVED; do
  printf 'v1.2.3\n' > $d/skill-version.txt
  printf -- '---\nname: x\nversion: v1.2.3\n---\nbody\n' > $d/SKILL.md
  echo base > $d/f.txt
done
echo 16.0.0 > 23-ai-workforce-blueprint/skill-version.txt
git add -A; git commit -qm base; git update-ref refs/remotes/origin/main HEAD
git checkout -qb work

echo changed > 80-demo/f.txt                      # skill change, no bump
echo changed > 81-bumped/f.txt; printf 'v1.2.4\n' > 81-bumped/skill-version.txt  # already bumped by hand
sed -i.bak 's/v1.2.3/v1.2.4/' 81-bumped/SKILL.md; rm 81-bumped/SKILL.md.bak
echo changed > 99-old-ARCHIVED/f.txt              # archived: ignored
echo changed > 23-ai-workforce-blueprint/x.txt    # blueprint: ignored
printf 'sop v2\n' > 23-ai-workforce-blueprint/sops/a.md   # SOP change, stale manifest
git add -A; git commit -qm work

bash scripts/batch-prep.sh >"$T.out1" 2>&1 || { cat "$T.out1"; echo "FAIL: first run"; exit 1; }
[ "$(cat 80-demo/skill-version.txt)" = v1.2.4 ] || { echo "FAIL: 80-demo not bumped"; exit 1; }
grep -q '^version: v1.2.4$' 80-demo/SKILL.md || { echo "FAIL: frontmatter not synced"; exit 1; }
[ -z "$(tail -c1 80-demo/skill-version.txt)" ] || { echo "FAIL: no trailing newline"; exit 1; }
[ "$(cat 81-bumped/skill-version.txt)" = v1.2.4 ] || { echo "FAIL: 81 double-bumped"; exit 1; }
[ "$(cat 99-old-ARCHIVED/skill-version.txt)" = v1.2.3 ] || { echo "FAIL: ARCHIVED touched"; exit 1; }
[ "$(cat 23-ai-workforce-blueprint/skill-version.txt)" = 16.0.0 ] || { echo "FAIL: blueprint touched"; exit 1; }
python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py --check || { echo "FAIL: SOP not re-stamped"; exit 1; }
git add -A; git commit -qm prep1   # a real batch commits the prep; the base diff stays vs origin/main
before="$(git status --porcelain; git rev-parse HEAD:80-demo)"
bash scripts/batch-prep.sh >"$T.out2" 2>&1 || { cat "$T.out2"; echo "FAIL: second run"; exit 1; }
rm -f "$T.out1" "$T.out2"
after="$(git status --porcelain; git rev-parse HEAD:80-demo)"
[ "$before" = "$after" ] && [ -z "$(git status --porcelain)" ] || { echo "FAIL: second run not a no-op"; git status --porcelain; exit 1; }
echo "PASS: bump, SOP re-stamp, archived/blueprint ignored, second run no-op"
