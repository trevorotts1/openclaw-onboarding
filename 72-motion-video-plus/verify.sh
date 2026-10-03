#!/usr/bin/env bash
# Skill 72 install/update verifier. NOT a normal runtime video-build step.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0

need_file() {
  if [ -f "$ROOT/$1" ]; then
    printf '[PASS] %s\n' "$1"
  else
    printf '[FAIL] missing %s\n' "$1" >&2
    fail=1
  fi
}

for f in \
  SKILL.md skill-version.txt MASTERDOC.md INSTRUCTIONS.md INSTALL.md QC.md REPO-INTEGRATION.md CORE_UPDATES.md \
  references/authority-map.md \
  references/animation-contract.md \
  references/motion-grammar.md \
  references/critique-protocol.md \
  references/directors-brief-template.md \
  references/manifest-schema.json \
  references/beats-schema.json \
  references/brand-bible-template.md \
  references/fish-audio-tts.md \
  references/untested-alternatives.md \
  references/pre-production/01-studio-setup.md \
  references/pre-production/02-house-rules.md \
  references/pre-production/03-brand-assets.md \
  references/pre-production/04-the-one-liner.md \
  references/pre-production/05-steal-the-grammar.md \
  references/pre-production/06-directors-brief.md \
  assets/example-manifest.json \
  scripts/render.js scripts/preflight.js scripts/tts.py \
  scripts/verify-determinism.js scripts/lint-grammar.py \
  scripts/synth-score.py scripts/beat-grid.py scripts/synth-sfx.py \
  scripts/critique-bundle.sh \
  scripts/assemble.sh scripts/qc.sh scripts/sweep-chromium.sh \
  repo-integration/skill-department-map-entry.json; do
  need_file "$f"
done

front_ver="$(awk 'BEGIN{x=0} /^---$/{x++; next} x==1 && /^version:/{sub(/^version:[[:space:]]*/,""); print; exit}' "$ROOT/SKILL.md" | tr -d '"\r')"
file_ver="$(tr -d 'vV\r[:space:]' < "$ROOT/skill-version.txt")"
front_ver="${front_ver#v}"
if [ "$front_ver" = "$file_ver" ] && [ -n "$front_ver" ]; then
  echo "[PASS] version lockstep $front_ver"
else
  echo "[FAIL] SKILL.md version '$front_ver' != skill-version.txt '$file_ver'" >&2
  fail=1
fi

# em dash check: the repo forbids them
if grep -r --include='*' -l $'\xe2\x80\x94' "$ROOT" >/dev/null 2>&1; then
  echo "[FAIL] em dash found in skill files" >&2
  grep -r --include='*' -l $'\xe2\x80\x94' "$ROOT" >&2
  fail=1
else
  echo "[PASS] no em dashes"
fi

for f in "$ROOT"/scripts/*.js; do
  if command -v node >/dev/null && node --check "$f" 2>/dev/null; then
    echo "[PASS] node syntax $(basename "$f")"
  else
    echo "[FAIL] node syntax $(basename "$f")" >&2
    fail=1
  fi
done

for f in "$ROOT"/scripts/*.sh "$ROOT"/verify.sh; do
  if bash -n "$f" 2>/dev/null; then
    echo "[PASS] bash syntax $(basename "$f")"
  else
    echo "[FAIL] bash syntax $(basename "$f")" >&2
    fail=1
  fi
done

for f in "$ROOT"/scripts/*.py; do
  if python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
    echo "[PASS] python syntax $(basename "$f")"
  else
    echo "[FAIL] python syntax $(basename "$f")" >&2
    fail=1
  fi
done

for f in "$ROOT"/references/manifest-schema.json "$ROOT"/references/beats-schema.json "$ROOT"/assets/example-manifest.json "$ROOT"/repo-integration/skill-department-map-entry.json; do
  if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
    echo "[PASS] json valid $(basename "$f")"
  else
    echo "[FAIL] json invalid $(basename "$f")" >&2
    fail=1
  fi
done

# example manifest validates against the schema (required fields present)
python3 - "$ROOT" <<'PY'
import json, sys
root = sys.argv[1]
schema = json.load(open(root + "/references/manifest-schema.json"))
ex = json.load(open(root + "/assets/example-manifest.json"))
missing = [k for k in schema["required"] if k not in ex]
if missing:
    print("example manifest missing: %s" % missing); sys.exit(1)
for s in ex["scenes"]:
    sm = [k for k in schema["properties"]["scenes"]["items"]["required"] if k not in s]
    if sm:
        print("scene %s missing: %s" % (s.get("id"), sm)); sys.exit(1)
print("example manifest matches schema")
PY
if [ $? -eq 0 ]; then echo "[PASS] example manifest matches schema"; else echo "[FAIL] example manifest schema mismatch" >&2; fail=1; fi

if [ "$fail" -eq 0 ]; then
  echo "SKILL 72 VERIFY PASS"
  exit 0
fi

echo "SKILL 72 VERIFY FAIL" >&2
exit 1
