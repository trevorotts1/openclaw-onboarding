#!/usr/bin/env bash
# test-bw-prover-build-roundtrip.sh — CI REGRESSION GUARD (v13.8.14)
#
# WHAT IT PROVES (build → prove integration, not just slug derivation):
#   Builds representative departments END-TO-END via build-workforce.py's
#   create_role_workspace() into a throwaway workspace, then asserts that EVERY
#   canonical role slug — INCLUDING the historically-divergent ones
#   (apostrophe/'&'/'.'/'--' slugs) — is COUNTED by the floor prover's role
#   matcher. A future slug divergence between build-workforce's folder writer and
#   the create_role_workspaces engine (or the role-library .md filenames) makes
#   this test FAIL, so the regression can never silently ship again.
#
#   Divergent slugs specifically asserted present-and-counted:
#       audio:   ai-voice-specialist-11-labs-play.ht, devils-advocate--audio
#       billing: fpanda--forecasting-analyst, subscription--recurring-revenue-specialist,
#                devils-advocate--billing
#
# APPROACH (self-contained — runs in GitHub Actions with NO fleet-prover present):
#   1. Build the dept roster via build-workforce.create_role_workspace (the path
#      under test — now rerouted through the engine, single source of truth).
#   2. Fill any remaining role-library role slugs for the dept via the SAME engine
#      create_role_workspaces.create_role_workspace() — exactly as the live
#      floor-fill-driver.py does. The expected slug set comes from the repo's own
#      templates/role-library/_index.json (in-repo source of truth, kept lockstep
#      with the fleet floor-manifest by the library-lockstep gate).
#   3. Match every expected slug against the built folders using the floor prover's
#      EXACT _normalize_role_name() + role_present() algorithm (vendored inline,
#      kept byte-aligned with fleet-prover/prove-floor.py). Assert zero missing.
#   4. BONUS: if the real fleet-prover is present (operator box / local dev), ALSO
#      run prove-floor.py --local for a true end-to-end overall_pass receipt.
#
# Exit 0 = all guards pass; non-zero = a guard failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
FLEET_PROVER="$(cd "$SCRIPT_DIR/../../../fleet-prover" 2>/dev/null && pwd || true)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Representative departments: cover per-role-how-to-style content AND every
# divergent-slug family (apostrophe-derived, '&'-derived '--', '.'-bearing slug).
DEPTS="audio,billing"

python3 - "$REPO_ROOT" "$SKILL_DIR" "$TMP" "$DEPTS" <<'PYEOF'
import sys, os, re, json, importlib.util
from pathlib import Path

repo_root = Path(sys.argv[1])
skill_dir = Path(sys.argv[2])
tmp = Path(sys.argv[3])
depts = sys.argv[4].split(",")

scripts = skill_dir / "scripts"
sys.path.insert(0, str(scripts))
# In-repo role-library is the source of truth for this test (no operator tree).
os.environ["ROLE_LIBRARY_PATH"] = str(skill_dir)

fail = 0
def check(cond, msg):
    global fail
    print(f"  {'PASS' if cond else 'FAIL'}: {msg}")
    if not cond:
        fail = 1

# ── Load build-workforce + engine ─────────────────────────────────────────────
spec = importlib.util.spec_from_file_location("build_workforce", str(scripts / "build-workforce.py"))
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)
import create_role_workspaces as crw  # noqa: E402

# Assert the reroute wiring is actually in place (guards against silent revert).
check(getattr(bw, "_ENGINE_ROLE_WRITER_AVAILABLE", False),
      "build-workforce imports the engine create_role_workspace (single source of truth)")

# ── Floor-prover role matcher (vendored from fleet-prover/prove-floor.py) ──────
_NUM_PREFIX_RE = re.compile(r'^\d+[-_]')
_ROLE_PREFIX_RE = re.compile(r'^(?:ROLE|role)--')
def _normalize_role_name(name):
    n = _NUM_PREFIX_RE.sub('', name)
    n = _ROLE_PREFIX_RE.sub('', n)
    if n.endswith('.md'):
        n = n[:-3]
    return re.sub(r'-{2,}', '-', n)

def role_present(dept_dir, slug, entries):
    if os.path.isfile(os.path.join(dept_dir, f"{slug}.md")):
        return True
    sub = os.path.join(dept_dir, slug)
    if os.path.isfile(os.path.join(sub, "IDENTITY.md")) or os.path.isfile(os.path.join(sub, "how-to.md")):
        return True
    nslug = _normalize_role_name(slug)
    for e in entries:
        if _normalize_role_name(e) != nslug:
            continue
        full = os.path.join(dept_dir, e)
        if e.endswith('.md') and os.path.isfile(full):
            return True
        if os.path.isfile(os.path.join(full, "IDENTITY.md")) or os.path.isfile(os.path.join(full, "how-to.md")):
            return True
    return False

# ── Expected role slugs per dept = repo role-library _index.json (source of truth) ──
index = json.loads((skill_dir / "templates" / "role-library" / "_index.json").read_text())
expected = {}
for r in index.get("roles", []):
    d = r.get("dept", "")
    s = r.get("slug", "")
    if d and s:
        expected.setdefault(d, set()).add(s)

# ── Set up a throwaway workspace ──────────────────────────────────────────────
company_dir = tmp / "test-corp"
departments_dir = company_dir / "departments"
departments_dir.mkdir(parents=True, exist_ok=True)
for f in ("AGENTS.md", "TOOLS.md", "USER.md"):
    (company_dir / f).write_text(f"# {f} (test fixture)\n", encoding="utf-8")

bw.COMPANY_DIR = str(company_dir)
bw.DEPARTMENTS_DIR = str(departments_dir)
bw.COMPANY_SLUG = "test-corp"
bw.MASTER_FILES = ""           # force in-repo roster (no stale operator master-files)
bw.WORKSPACE_ROOT = str(skill_dir)

interview = {
    "company_name": "Test Corp", "industry": "Professional Services",
    "department_tools": "Slack, Notion", "department_kpis": "Revenue",
    "department_challenges": "Scaling",
}

def norm(name):
    return _normalize_role_name(name.strip()).lower()

def present_keys(dept_dir):
    keys = set()
    if not dept_dir.is_dir():
        return keys
    for e in dept_dir.iterdir():
        if e.is_dir() and ((e / "IDENTITY.md").exists() or (e / "how-to.md").exists()):
            keys.add(norm(e.name))
        elif e.is_file() and e.suffix == ".md":
            keys.add(norm(e.name))
    return keys

# ── PHASE 1: build the roster via build-workforce (path under test) ──
for dept_id in depts:
    dept_info = bw.RECOMMENDED_DEPARTMENTS.get(dept_id) or {
        "name": dept_id.replace("-", " ").title(), "emoji": "", "head": "Head", "description": ""}
    (departments_dir / dept_id).mkdir(parents=True, exist_ok=True)
    bw.create_role_workspace(dept_id, dept_info, interview)

# ── PHASE 1 ASSERTION (the actual regression guard): build-workforce's OWN
# roster output — BEFORE any engine gap-fill — must already produce the
# historically-divergent ROSTER slugs byte-correct and prover-countable. These
# slugs are emitted by build-workforce.create_role_workspace itself, so a slug
# regression there fails HERE even though PHASE 2 would later backfill them.
ROSTER_DIVERGENT = {
    "audio": ["ai-voice-specialist-11-labs-play.ht"],
    "billing": ["fpanda--forecasting-analyst", "subscription--recurring-revenue-specialist"],
}
for dept_id in depts:
    dept_dir = str(departments_dir / dept_id)
    entries = sorted(os.listdir(dept_dir)) if os.path.isdir(dept_dir) else []
    for s in ROSTER_DIVERGENT.get(dept_id, []):
        check(role_present(dept_dir, s, entries),
              f"{dept_id}: PHASE-1 build-workforce roster emits '{s}' prover-countable "
              f"(no gap-fill yet)")

# ── PHASE 2: fill remaining library role slugs via the SAME engine (floor-fill parity) ──
for dept_id in depts:
    dept_dir = departments_dir / dept_id
    have = present_keys(dept_dir)
    n = 80
    for slug in sorted(expected.get(dept_id, set())):
        if norm(slug) in have:
            continue
        name = slug.replace("--", " ").replace("-", " ").title()
        crw.create_role_workspace(str(dept_dir), name, str(company_dir),
                                  {"slug": slug, "number": n})
        n += 1

# ── PHASE 3: prove every expected slug is COUNTED (prover matcher) ──
DIVERGENT = {
    "audio": ["ai-voice-specialist-11-labs-play.ht", "devils-advocate--audio"],
    "billing": ["fpanda--forecasting-analyst",
                "subscription--recurring-revenue-specialist",
                "devils-advocate--billing"],
}
total_missing = 0
for dept_id in depts:
    dept_dir = str(departments_dir / dept_id)
    entries = sorted(os.listdir(dept_dir)) if os.path.isdir(dept_dir) else []
    exp = sorted(expected.get(dept_id, set()))
    missing = [s for s in exp if not role_present(dept_dir, s, entries)]
    total_missing += len(missing)
    check(not missing,
          f"{dept_id}: all {len(exp)} library role slugs COUNTED by prover matcher "
          f"(missing={missing})")
    # Explicitly assert the historically-divergent slugs are counted.
    for s in DIVERGENT.get(dept_id, []):
        check(role_present(dept_dir, s, entries),
              f"{dept_id}: divergent slug '{s}' present-and-counted")

check(total_missing == 0, f"zero missing role slugs across {depts} (got {total_missing})")

# ── PHASE 4: REAL CONTENT, NOT STUBS (ROLE_LIBRARY_PATH-misconfig guard) ──
# A prover-passing-LOOKING folder full of "PENDING - FILL FROM LIBRARY" stubs is
# WORSE than the slug bug: it counts as present but carries no real SOPs. The
# library is resolved (by both build-workforce._instantiate_role_from_library and
# create_role_workspaces._resolve_skill_dir) via ROLE_LIBRARY_PATH → skill-dir
# root; if that root is gutted/empty the role gets a PENDING stub. These roles
# (the entire audio+billing floor) ALL have a pre-written role-library template,
# so EVERY built how-to.md MUST carry real library provenance and ZERO PENDING
# markers. Assert it. This makes the guard bite on a future ROLE_LIBRARY_PATH
# misconfiguration, not just a slug divergence.
PENDING_MARKERS = ("PENDING - FILL FROM LIBRARY", "PENDING — FILL FROM LIBRARY",
                   "how-to.md (stub)")
MIN_HOWTO_BYTES = 1500  # a real library how-to is multi-KB; a stub is < this
stub_roles = []
no_provenance = []
for dept_id in depts:
    dept_dir = departments_dir / dept_id
    if not dept_dir.is_dir():
        continue
    for sub in sorted(dept_dir.iterdir()):
        ht = sub / "how-to.md"
        if not ht.is_file():
            continue
        txt = ht.read_text(encoding="utf-8", errors="replace")
        if any(m in txt for m in PENDING_MARKERS):
            stub_roles.append(f"{dept_id}/{sub.name}")
            continue
        # real library content carries the workforce-provenance source marker
        # AND is comfortably larger than a stub.
        if "source=role-library" not in txt or len(txt.encode("utf-8")) < MIN_HOWTO_BYTES:
            no_provenance.append(f"{dept_id}/{sub.name} (bytes={len(txt.encode('utf-8'))})")

check(not stub_roles,
      f"NO 'PENDING - FILL FROM LIBRARY' stub how-to.md (would mean a gutted "
      f"ROLE_LIBRARY_PATH); offenders={stub_roles[:8]}")
check(not no_provenance,
      f"every built how-to.md carries real library provenance "
      f"(source=role-library, >= {MIN_HOWTO_BYTES}B); offenders={no_provenance[:8]}")

# Record the built workspace path for the optional real-prover phase.
(tmp / "ws-path.txt").write_text(str(departments_dir), encoding="utf-8")

print()
if fail:
    print("RESULT: FAIL")
    sys.exit(1)
print("RESULT: PASS")
PYEOF
PY_STATUS=$?

echo "--------------------------------------------"

# ── BONUS: real fleet-prover end-to-end (operator box / local dev only) ──
if [ -n "$FLEET_PROVER" ] && [ -f "$FLEET_PROVER/prove-floor.py" ] && [ -f "$FLEET_PROVER/floor-manifest.json" ]; then
  WS_PATH="$(cat "$TMP/ws-path.txt" 2>/dev/null || true)"
  if [ -n "$WS_PATH" ] && [ -d "$WS_PATH" ]; then
    echo "BONUS: real fleet-prover present — running prove-floor.py --local for end-to-end overall_pass"
    if python3 "$FLEET_PROVER/prove-floor.py" --local "$WS_PATH" 2>&1 | tee "$TMP/prove.out" | grep -q "^OVERALL: PASS"; then
      echo "  PASS: real prove-floor.py --local reports OVERALL: PASS"
    else
      echo "  FAIL: real prove-floor.py --local did NOT report OVERALL: PASS"
      grep -E "FAIL|missing|OVERALL" "$TMP/prove.out" | head -20
      PY_STATUS=1
    fi
  fi
else
  echo "NOTE: fleet-prover not present (expected in CI) — self-contained matcher used above."
fi

echo "--------------------------------------------"
if [ "$PY_STATUS" -eq 0 ]; then
  echo "ALL BUILD-ROUNDTRIP GUARDS PASSED"
  exit 0
else
  echo "BUILD-ROUNDTRIP GUARD FAILURES"
  exit 1
fi
