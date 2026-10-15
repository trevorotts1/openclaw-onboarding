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
  scripts/assemble.sh scripts/qc.sh scripts/qc.py scripts/sweep-chromium.sh \
  references/qc-schema.json references/technical-qc.md \
  references/vsl-handoff-schema.json \
  references/vsl-desktop-handoff.md \
  references/delivery-receipt-schema.json \
  references/status-and-delivery.md \
  scripts/check_authority.py \
  scripts/vsl_handoff.py \
  references/vsl-mobile-schema.json \
  references/vsl-mobile-mode.json \
  references/vsl-mobile-handoff.md \
  scripts/vsl_mobile.py \
  scripts/vsl-compile.mjs scripts/vsl-render.mjs scripts/vsl-proof.mjs \
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

# em dash check: the repo forbids them in authored text. Scope the scan
# to git-tracked files so untracked build state (runtime/node_modules,
# runtime/dist, shared-runtime .runtime, test work dirs) can neither
# fail the check nor mask a real hit. Outside a git work tree, fall
# back to a find that prunes those same build directories. Binary files
# are ignored (-I): the rule governs authored text, not rendered pixels.
em_dash_hits=""
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  while IFS= read -r -d '' rel; do
    case "$rel" in ../*|/*) continue ;; esac
    if grep -Ilq $'\xe2\x80\x94' "$ROOT/$rel" 2>/dev/null; then
      em_dash_hits="$em_dash_hits $rel"
    fi
  done < <(git -C "$ROOT" ls-files -z)
else
  em_dash_hits="$(find "$ROOT" \( -name node_modules -o -name dist -o -name .runtime -o -name .git -o -name work \) -prune -o -type f -print0 2>/dev/null | xargs -0 grep -Il $'\xe2\x80\x94' 2>/dev/null)"
fi
if [ -n "$em_dash_hits" ]; then
  echo "[FAIL] em dash found in skill files:$em_dash_hits" >&2
  fail=1
else
  echo "[PASS] no em dashes in tracked files"
fi

for f in "$ROOT"/scripts/*.js; do
  if command -v node >/dev/null && node --check "$f" 2>/dev/null; then
    echo "[PASS] node syntax $(basename "$f")"
  else
    echo "[FAIL] node syntax $(basename "$f")" >&2
    fail=1
  fi
done

for f in "$ROOT"/scripts/*.mjs; do
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

for f in "$ROOT"/references/manifest-schema.json "$ROOT"/references/beats-schema.json "$ROOT"/references/qc-schema.json "$ROOT"/assets/example-manifest.json "$ROOT"/repo-integration/skill-department-map-entry.json; do
  if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
    echo "[PASS] json valid $(basename "$f")"
  else
    echo "[FAIL] json invalid $(basename "$f")" >&2
    fail=1
  fi
done

# QC report schema check (MG-034). references/qc-schema.json is the
# versioned contract for the report scripts/qc.py emits; it must be a
# well-formed Draft 2020-12 schema (the validator family
# scripts/motion_contracts.py uses), not merely valid JSON.
if python3 -c "
import json, sys
from jsonschema import Draft202012Validator
schema = json.load(open('$ROOT/references/qc-schema.json'))
Draft202012Validator.check_schema(schema)
need = {'schema_version', 'item', 'tool', 'verdict', 'exit_code',
        'artifact_path', 'artifact_sha256', 'checks', 'summary'}
missing = need - set(schema.get('required', []))
sys.exit(1 if missing else 0)
" 2>/dev/null; then
  echo "[PASS] qc schema structure (Draft 2020-12, report fields required)"
else
  echo "[FAIL] qc schema structure" >&2
  fail=1
fi

# Manifest schema structure check. Since MG-007, references/manifest-schema.json
# is a thin entrypoint: it carries no fields of its own, only a $ref into
# references/contracts-v2.schema.json. Validate against the schema's ACTUAL
# structure: (1) the wrapper's $ref resolves to a real contracts $def that has
# a required list; (2) the shipped example manifest, which is a V1 manifest,
# carries the fields the preserved V1 schema (legacy-manifest-schema.json)
# requires, per scene as well; (3) every shipped V2 mode fixture manifest
# carries every key the resolved V2 manifest $def requires. Full V2 semantic
# validation lives in scripts/motion_contracts.py and the corpus suites;
# this check is the install-level structural guard.
python3 - "$ROOT" <<'PY'
import glob, json, sys
root = sys.argv[1]

wrapper = json.load(open(root + "/references/manifest-schema.json"))
ref = wrapper.get("$ref", "")
prefix = "contracts-v2.schema.json#/$defs/"
if not ref.startswith(prefix):
    print("manifest-schema.json does not $ref a contracts-v2 $def: %r" % ref); sys.exit(1)
def_name = ref[len(prefix):]
contracts = json.load(open(root + "/references/contracts-v2.schema.json"))
target = contracts.get("$defs", {}).get(def_name)
if not isinstance(target, dict) or not target.get("required"):
    print("contracts $defs/%s missing or has no required list" % def_name); sys.exit(1)

legacy = json.load(open(root + "/references/legacy-manifest-schema.json"))
ex = json.load(open(root + "/assets/example-manifest.json"))
missing = [k for k in legacy["required"] if k not in ex]
if missing:
    print("example manifest missing: %s" % missing); sys.exit(1)
for s in ex["scenes"]:
    sm = [k for k in legacy["properties"]["scenes"]["items"]["required"] if k not in s]
    if sm:
        print("scene %s missing: %s" % (s.get("id"), sm)); sys.exit(1)

v2_fixtures = sorted(glob.glob(root + "/tests/fixtures/modes/*/manifest.json"))
if not v2_fixtures:
    print("no V2 mode fixture manifests found"); sys.exit(1)
for path in v2_fixtures:
    doc = json.load(open(path))
    miss = [k for k in target["required"] if k not in doc]
    if miss:
        print("V2 fixture %s missing required keys: %s" % (path, miss)); sys.exit(1)
print("example manifest matches legacy schema; V2 wrapper resolves to $defs/%s; %d V2 fixture manifests carry its required keys" % (def_name, len(v2_fixtures)))
PY
if [ $? -eq 0 ]; then echo "[PASS] manifest schema structure (legacy example + V2 wrapper + mode fixtures)"; else echo "[FAIL] manifest schema structure mismatch" >&2; fail=1; fi

# VSL handoff schema structure check (MG-037). The handoff layer's
# own schema must parse as Draft 2020-12 and carry its three record
# definitions, each with a required list; the acceptance handoff
# fixture must carry every key the vsl_handoff definition requires.
# Full semantic validation lives in scripts/vsl_handoff.py; this is
# the install-level structural guard.
python3 - "$ROOT" <<'PY'
import json, sys
root = sys.argv[1]
schema = json.load(open(root + "/references/vsl-handoff-schema.json"))
defs = schema.get("$defs", {})
for name in ("vsl_handoff", "return_package", "assembly_report"):
    target = defs.get(name)
    if not isinstance(target, dict) or not target.get("required"):
        print("vsl-handoff $defs/%s missing or has no required list" % name); sys.exit(1)
fixture = json.load(open(root + "/tests/fixtures/vsl/handoff-desktop.json"))
miss = [k for k in defs["vsl_handoff"]["required"] if k not in fixture]
if miss:
    print("VSL handoff fixture missing required keys: %s" % miss); sys.exit(1)
print("vsl-handoff schema carries vsl_handoff, return_package, assembly_report; the acceptance fixture carries its required keys")
PY
if [ $? -eq 0 ]; then echo "[PASS] vsl handoff schema structure (defs + acceptance fixture)"; else echo "[FAIL] vsl handoff schema structure mismatch" >&2; fail=1; fi

# Mobile VSL schema structure check (MG-038). The mobile layer's
# own schema must parse as Draft 2020-12 and carry its three record
# definitions, each with a required list; the mobile mode
# configuration must declare the 1080x1920 canvas; the acceptance
# handoff fixture must carry every key the vsl_mobile_handoff
# definition requires. Full semantic validation lives in
# scripts/vsl_mobile.py; this is the install-level guard.
python3 - "$ROOT" <<'PY'
import json, sys
root = sys.argv[1]
schema = json.load(open(root + "/references/vsl-mobile-schema.json"))
defs = schema.get("$defs", {})
for name in ("vsl_mobile_handoff", "mobile_fit_report", "mobile_delivery_record"):
    target = defs.get(name)
    if not isinstance(target, dict) or not target.get("required"):
        print("vsl-mobile $defs/%s missing or has no required list" % name); sys.exit(1)
mode_cfg = json.load(open(root + "/references/vsl-mobile-mode.json"))
if mode_cfg.get("mode") != "vsl_mobile" or mode_cfg.get("canvas") != {"width": 1080, "height": 1920, "aspect": "9:16"}:
    print("vsl-mobile mode configuration does not declare the 1080x1920 canvas"); sys.exit(1)
fixture = json.load(open(root + "/tests/fixtures/vsl/handoff-mobile.json"))
miss = [k for k in defs["vsl_mobile_handoff"]["required"] if k not in fixture]
if miss:
    print("Mobile VSL handoff fixture missing required keys: %s" % miss); sys.exit(1)
print("vsl-mobile schema carries vsl_mobile_handoff, mobile_fit_report, mobile_delivery_record; the mode configuration declares 1080x1920; the acceptance fixture carries its required keys")
PY
if [ $? -eq 0 ]; then echo "[PASS] vsl mobile schema structure (defs + mode config + acceptance fixture)"; else echo "[FAIL] vsl mobile schema structure mismatch" >&2; fail=1; fi

# Delivery receipt schema structure check (MG-046). The status
# layer's own schema must parse as Draft 2020-12 and carry its three
# record definitions, each with a required list; the receipt
# definition must pin production_status to DELIVERED and cap
# missing_mandatory at zero items, so a receipt can never smuggle a
# release status or an incomplete delivery. Full validation lives
# in runtime/src/status/receipt.ts and tests/unit/
# test_delivery_receipt.py; this is the install-level guard.
python3 - "$ROOT" <<'PY'
import json, sys
root = sys.argv[1]
schema = json.load(open(root + "/references/delivery-receipt-schema.json"))
if "2020-12" not in str(schema.get("$schema", "")):
    print("delivery-receipt schema is not Draft 2020-12"); sys.exit(1)
defs = schema.get("$defs", {})
for name in ("delivery_receipt", "production_approval", "artifact"):
    target = defs.get(name)
    if not isinstance(target, dict) or not target.get("required"):
        print("delivery-receipt $defs/%s missing or has no required list" % name); sys.exit(1)
receipt = defs["delivery_receipt"]
props = receipt.get("properties", {})
if props.get("production_status", {}).get("const") != "DELIVERED":
    print("delivery_receipt production_status is not pinned to DELIVERED"); sys.exit(1)
if props.get("missing_mandatory", {}).get("maxItems") != 0:
    print("delivery_receipt missing_mandatory is not capped at zero"); sys.exit(1)
approval = defs["production_approval"]
if approval.get("properties", {}).get("kind", {}).get("const") != "production_approval":
    print("production_approval kind is not pinned"); sys.exit(1)
print("delivery-receipt schema carries delivery_receipt, production_approval, artifact; status pinned, missing capped at zero")
PY
if [ $? -eq 0 ]; then echo "[PASS] delivery receipt schema structure (defs + pinned status)"; else echo "[FAIL] delivery receipt schema structure mismatch" >&2; fail=1; fi

# References and authority check (MG-042). The reconciled documents
# must name no dead paths, carry no obsolete production promises,
# name the four modes and the status-and-delivery layer where they
# belong, state PowerPoint playback as UNVERIFIED wherever playback
# is discussed, and keep the department-map mirrors identical.
if python3 "$ROOT/scripts/check_authority.py" --root "$ROOT"; then
  echo "[PASS] references and authority check (MG-042)"
else
  echo "[FAIL] references and authority check (MG-042)" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "SKILL 72 VERIFY PASS"
  exit 0
fi

echo "SKILL 72 VERIFY FAIL" >&2
exit 1
