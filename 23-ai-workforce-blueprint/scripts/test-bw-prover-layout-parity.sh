#!/usr/bin/env bash
# test-bw-prover-layout-parity.sh — CI guard: build-workforce.py layout parity with prove-floor.
#
# WHAT IT TESTS:
#   Proves that role folders emitted by build-workforce.py's create_role_workspace()
#   produce slugs that PASS prove-floor.py --local / _normalize_role_name matching
#   against floor-manifest role slugs.
#
#   The core fix (v10.16.26 chore/floor-build-prover-alignment) changes:
#     1. Explicit roster slug used VERBATIM (not through _clean_role_slug), so
#        'ai-voice-specialist-11-labs-play.ht' is not corrupted to '...-play-ht'.
#     2. No-explicit-slug fallback uses _engine_slugify() (mirrors create_role_workspaces.slugify()),
#        so decorated names like "Devil's Advocate -- Presentations" produce
#        'devils-advocate-presentations' (matching manifest), not "devil's-advocate-presentations".
#
# APPROACH:
#   Feed floor-manifest.json role slugs through both sides — build-workforce's
#   role_folder_basename() derivation (when the slug IS the explicit slug, as it
#   would be from a roster **Slug:** line) and prove-floor's _normalize_role_name() —
#   and assert zero mismatches.
#   Also verify the _engine_slugify fallback for decorated role names that historically
#   diverged from prover-expected slugs.
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FLEET_PROVER="$(cd "$SCRIPT_DIR/../../../fleet-prover" 2>/dev/null && pwd || true)"

PASS=0; FAIL=0
ok()   { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

python3 - "$SCRIPT_DIR" "$FLEET_PROVER" <<'PYEOF'
import sys, os, re, importlib.util, json

scripts_dir = sys.argv[1]
fleet_prover = sys.argv[2] if len(sys.argv) > 2 else ""

fail = 0
def check(cond, msg):
    global fail
    status = "PASS" if cond else "FAIL"
    print(f"  {status}: {msg}")
    if not cond:
        fail = 1

# ── Load build-workforce helpers ──────────────────────────────────────────────
spec = importlib.util.spec_from_file_location("bw", os.path.join(scripts_dir, "build-workforce.py"))
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)

# ── Load prove-floor._normalize_role_name ────────────────────────────────────
pf_path = os.path.join(fleet_prover, "prove-floor.py") if fleet_prover else ""
pf = None
if os.path.isfile(pf_path):
    spec2 = importlib.util.spec_from_file_location("pf", pf_path)
    pf = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(pf)

def prover_normalize(slug):
    """Mirror prove-floor._normalize_role_name logic."""
    n = re.sub(r'^\d+[-_]', '', slug)    # strip NN- prefix
    n = re.sub(r'^(?:ROLE|role)--', '', n)  # strip ROLE-- prefix
    if n.endswith('.md'):
        n = n[:-3]
    return re.sub(r'-{2,}', '-', n)      # collapse -- to -

if pf and hasattr(pf, '_normalize_role_name'):
    prover_normalize = pf._normalize_role_name

# ── Test 1: Explicit slug VERBATIM — no _clean_role_slug corruption ───────────
print("== T1: explicit roster slug used VERBATIM (no _clean_role_slug corruption) ==")

# The historically failing case: 'play.ht' must NOT become 'play-ht'.
slug_with_dot = "ai-voice-specialist-11-labs-play.ht"
role = {"slug": slug_with_dot, "name": "AI Voice Specialist", "number": 1}
folder = bw.role_folder_basename(role)
# folder should be "01-ai-voice-specialist-11-labs-play.ht"
slug_part = folder.split("-", 1)[1] if "-" in folder else folder
check(slug_part == slug_with_dot,
      f"explicit slug '{slug_with_dot}' used verbatim in folder (got '{slug_part}')")

# Prover normalizes folder -> slug_with_dot; manifest slug is slug_with_dot.
# Check they match after normalization.
prover_sees_folder = prover_normalize(folder)
prover_sees_manifest = prover_normalize(slug_with_dot)
check(prover_sees_folder == prover_sees_manifest,
      f"prover normalize(folder)={prover_sees_folder!r} == normalize(manifest)={prover_sees_manifest!r}")

# Another explicit slug that _clean_role_slug would have cleaned: dots preserved.
slug_dots = "fpanda--forecasting-analyst"
role2 = {"slug": slug_dots, "name": "FP&A -- Forecasting Analyst", "number": 3}
folder2 = bw.role_folder_basename(role2)
slug_part2 = folder2.split("-", 1)[1] if "-" in folder2 else folder2
# Engine uses VERBATIM: fpanda--forecasting-analyst (note double dash preserved)
# Prover collapses -- to - so both normalize to same key.
pn_folder2 = prover_normalize(folder2)
pn_manifest2 = prover_normalize(slug_dots)
check(pn_folder2 == pn_manifest2,
      f"fpanda slug: prover_normalize(folder)={pn_folder2!r} == normalize(manifest)={pn_manifest2!r}")

# ── Test 2: No-explicit-slug fallback uses _engine_slugify (prover-aligned) ──
print("== T2: no-explicit-slug fallback: _engine_slugify strips apostrophes and '&' ==")

# NOTE: roles with explicit **Slug:** lines (like fpanda--forecasting-analyst,
# subscription--recurring-revenue-specialist, devils-advocate--billing) go through
# the VERBATIM path (T1). The no-explicit-slug fallback is for roles that lack a
# **Slug:** line. We test that _engine_slugify produces CLEAN slugs (no apostrophes,
# no '&', no '.') and that the prover can match them consistently.

# Historically _legacy_naive_slug kept apostrophes: "Devil's" -> "devil's-..."
# _engine_slugify fixes this: the apostrophe becomes a dash (collapsed), so
# "Devil's Advocate" -> "devil-s-advocate" — clean and ASCII-safe.
cases_no_slug = [
    # (role_name, banned_chars_check)
    ("Devil's Advocate -- Generic", ["'"]),
    ("Research & Development Lead", ["&"]),
    ("Social.Media Manager", ["."]),
    ("Brand Manager (Influencer)", ["(", ")"]),
]
for name, banned in cases_no_slug:
    role_ns = {"slug": "", "name": name, "number": 2}
    folder_ns = bw.role_folder_basename(role_ns)
    slug_ns = folder_ns.split("-", 1)[1] if "-" in folder_ns else folder_ns
    for ch in banned:
        check(ch not in slug_ns,
              f"'{name}': no {ch!r} in _engine_slugify fallback slug '{slug_ns}'")

# ── Test 3: floor-manifest slugs survive verbatim round-trip ─────────────────
print("== T3: floor-manifest slugs survive build-workforce verbatim round-trip ==")

manifest_path = os.path.join(fleet_prover, "floor-manifest.json") if fleet_prover else ""
if not os.path.isfile(manifest_path):
    print("  SKIP: floor-manifest.json not found at expected fleet-prover path — skipping manifest round-trip")
else:
    with open(manifest_path) as f:
        manifest = json.load(f)
    mismatches = []
    total = 0
    for dept, spec in manifest["departments"].items():
        for manifest_slug in spec.get("role_slugs", []):
            total += 1
            # Simulate an explicit **Slug:** roster entry using the manifest slug verbatim.
            role_sim = {"slug": manifest_slug, "name": manifest_slug.replace("-", " ").title(), "number": 1}
            folder_sim = bw.role_folder_basename(role_sim)
            slug_sim = folder_sim.split("-", 1)[1] if "-" in folder_sim else folder_sim
            pn_folder = prover_normalize(folder_sim)
            pn_manifest = prover_normalize(manifest_slug)
            if pn_folder != pn_manifest:
                mismatches.append(
                    f"{dept}/{manifest_slug}: folder_slug={slug_sim!r} "
                    f"pn_folder={pn_folder!r} != pn_manifest={pn_manifest!r}")
    check(len(mismatches) == 0,
          f"all {total} manifest slugs survive verbatim round-trip "
          f"(0 prover mismatches; got {len(mismatches)})")
    if mismatches:
        for m in mismatches[:10]:
            print(f"    MISMATCH: {m}")

print()
if fail:
    print("RESULT: FAIL")
    sys.exit(1)
print("RESULT: PASS")
PYEOF

status=$?
echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ $status -eq 0 ] && { echo "ALL LAYOUT-PARITY TESTS PASSED"; exit 0; } || { echo "LAYOUT-PARITY TEST FAILURES"; exit 1; }
