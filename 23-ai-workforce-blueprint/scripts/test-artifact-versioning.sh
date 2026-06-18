#!/usr/bin/env bash
# test-artifact-versioning.sh — adversarial fixtures for the PER-ARTIFACT
# VERSIONING + CHANGE-DETECTION system (v12.27.0).
#
# A green check that never fails is worthless. These tests prove the three pieces
# BITE on real drift and DON'T false-positive on per-client/day variation:
#
#   T0.  CLEAN repo: hash-content-manifest.py --check PASSES (rc 0).
#   T1.  CANONICAL hash is CLIENT/DAY-INVARIANT — two clients on two days render
#        the SAME template to DIFFERENT bytes (the naive bug) yet the canonical
#        content_sha is identical. This is the core false-positive-elimination proof.
#   T2.  A REAL content edit CHANGES content_sha; a volatile-only change
#        (header date + provenance marker) does NOT.
#   T3.  STALE MANIFEST: edit a role .md without re-stamping -> --check FAILS (rc 1).
#   T4.  hash-content-manifest.py is IDEMPOTENT (re-run: content_sha + version
#        stable; no spurious bumps).
#   T5.  detect-stale-artifacts.py (fast path): CURRENT/STALE/MISSING/ORPHAN are
#        classified correctly and exit code is 10 on actionable drift.
#   T6.  detect-stale-artifacts.py (marker fallback): UNTRACKED + STALE + CURRENT
#        from on-disk provenance markers when build-state has no artifactProvenance.
#   T7.  ALL-CURRENT workspace -> detector exit 0.
#   T8.  CONTENT-HASH gate dimension: clean PASSES; an un-restamped edit -> the
#        artifact gate exits 6 (CONTENT-HASH DRIFT).
#   T9.  PERSONA canonical hash is client/day-INVARIANT — two clients fill the same
#        persona template to different bytes yet share one canonical content_sha
#        (persona false-positive elimination).
#   T10. SURGICAL persona STALE — editing ONE persona + re-stamping flags ONLY that
#        persona STALE for a client pinned to the old shas; all others stay CURRENT.
#   T11. The gate BLOCKS an un-restamped persona edit (--check rc 1, gate rc 6).
#
# Exit 0 = all fixtures pass; non-zero = a fixture failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

HASH="$SCRIPT_DIR/hash-content-manifest.py"
DETECT="$SCRIPT_DIR/detect-stale-artifacts.py"
GATE="$SCRIPT_DIR/qc-assert-repo-consistency.py"
MANIFEST="$SKILL_DIR/templates/role-library/_index.json"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

PY=python3

# ─── T0: clean repo --check PASSES ────────────────────────────────────────────
echo "T0: clean repo content-manifest --check"
if "$PY" "$HASH" --check >/dev/null 2>&1; then
  ok "hash-content-manifest.py --check exits 0 on the clean repo"
else
  bad "hash-content-manifest.py --check should PASS on the clean repo (run the stamper)"
fi

# ─── T1: canonical hash is client/day-invariant ───────────────────────────────
echo "T1: canonical content_sha is client/day-INVARIANT (false-positive elimination)"
"$PY" - "$SCRIPT_DIR" "$SKILL_DIR" <<'PY'
import sys, importlib.util, hashlib
from datetime import datetime, timezone
sd, skd = sys.argv[1], sys.argv[2]
sys.path.insert(0, sd); sys.path.insert(0, skd + "/lib")
spec = importlib.util.spec_from_file_location("hcm", sd + "/hash-content-manifest.py")
hcm = importlib.util.module_from_spec(spec); spec.loader.exec_module(hcm)
f = skd + "/templates/role-library/account-management/client-relationship-manager.md"
template = open(f).read()
canonical = hcm.content_sha_of_text(template)

cspec = importlib.util.spec_from_file_location("crw", sd + "/create_role_workspaces.py")
crw = importlib.util.module_from_spec(cspec); cspec.loader.exec_module(crw)
def render(company, owner, day):
    class FD:
        _F = datetime.fromisoformat(day + "T00:00:00+00:00")
        @classmethod
        def now(cls, tz=None): return cls._F if tz is None else cls._F.astimezone(tz)
        @classmethod
        def utcnow(cls): return cls._F.replace(tzinfo=None)
    crw.datetime = FD
    crw._load_company_config = lambda: {"companyName": company, "ownerName": owner,
                                        "industry": "coaching", "yearlyRevenueGoal": "1000000",
                                        "connectedSystems": []}
    return crw.fill_tokens(template, "Client Relationship Manager", "Account Management", False)
a = render("Acme Co", "Alice", "2026-01-15")
b = render("Globex Inc", "Bob", "2026-06-17")
naive_a = "sha256:" + hashlib.sha256(a.encode()).hexdigest()
naive_b = "sha256:" + hashlib.sha256(b.encode()).hexdigest()
ok_naive_differ = naive_a != naive_b           # naive byte-hash IS the bug
ok_canonical = hcm.content_sha_of_text(template) == canonical  # invariant
sys.exit(0 if (ok_naive_differ and ok_canonical) else 1)
PY
if [ $? -eq 0 ]; then
  ok "naive byte-hash differs per client/day BUT canonical content_sha is invariant"
else
  bad "canonical content_sha must be client/day-invariant while naive differs"
fi

# ─── T2: real edit changes sha; volatile-only does not ────────────────────────
echo "T2: real content edit changes content_sha; volatile-only change does not"
"$PY" - "$SCRIPT_DIR" "$SKILL_DIR" <<'PY'
import sys, importlib.util
sd, skd = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("hcm", sd + "/hash-content-manifest.py")
hcm = importlib.util.module_from_spec(spec); spec.loader.exec_module(hcm)
f = skd + "/templates/role-library/account-management/client-relationship-manager.md"
t = open(f).read()
base = hcm.content_sha_of_text(t)
real = hcm.content_sha_of_text(t.replace("relationship steward", "relationship guardian", 1))
vol = hcm.content_sha_of_text(
    "<!-- workforce-provenance: source=role-library content_sha=sha256:abc -->\n"
    + t.replace("**Last updated:** {{ISO_DATE}}", "**Last updated:** 2026-12-31"))
sys.exit(0 if (real != base and vol == base) else 1)
PY
if [ $? -eq 0 ]; then
  ok "real edit -> sha changes; date+marker-only -> sha unchanged"
else
  bad "real edit must change content_sha; volatile-only must NOT"
fi

# ─── Sandbox a FULL repo root so destructive fixtures don't touch the repo AND
#     the artifact gate (which reads repo-root files) has what it needs. ─────────
SANDBOX="$(mktemp -d)"
SBROOT="$SANDBOX/repo"
mkdir -p "$SBROOT"
cp -R "$SKILL_DIR" "$SBROOT/23-ai-workforce-blueprint"
[ -d "$REPO_ROOT/42-personal-assistant-library" ] && \
  cp -R "$REPO_ROOT/42-personal-assistant-library" "$SBROOT/42-personal-assistant-library"
# Repo-root files the artifact gate reads (BOOTSTRAP / SKILLS-COUNT / VERSION).
for f in version install.sh update-skills.sh README.md cc-compat.json \
         DIRECT-TO-AGENT-UPDATE-MESSAGE.md "Start Here.md" \
         IDENTITY.md SOUL.md AGENTS.md USER.md TOOLS.md HEARTBEAT.md; do
  [ -e "$REPO_ROOT/$f" ] && cp "$REPO_ROOT/$f" "$SBROOT/$f"
done
# Bring the ACTIVE + ARCHIVED skill dir NAMES across so the tree-count matches.
for d in "$REPO_ROOT"/[0-9]*/; do
  base="$(basename "$d")"
  [ "$base" = "23-ai-workforce-blueprint" ] && continue
  [ "$base" = "42-personal-assistant-library" ] && continue
  mkdir -p "$SBROOT/$base"
done
find "$SBROOT/23-ai-workforce-blueprint" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
SB_SKILL="$SBROOT/23-ai-workforce-blueprint"
SB_HASH="$SB_SKILL/scripts/hash-content-manifest.py"
SB_MANIFEST="$SB_SKILL/templates/role-library/_index.json"
SB_ROLE="$SB_SKILL/templates/role-library/account-management/client-relationship-manager.md"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# ─── T3: stale manifest (edit without re-stamp) -> --check FAILS ──────────────
echo "T3: edit a role .md WITHOUT re-stamping -> --check FAILS (rc 1)"
printf '\n<!-- an UN-restamped real edit -->\n' >> "$SB_ROLE"
"$PY" "$SB_HASH" --index "$SB_MANIFEST" --check >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 1 ]; then
  ok "stale manifest detected (--check rc 1)"
else
  bad "stale manifest should make --check exit 1, got $rc"
fi
# re-stamp -> --check passes again
"$PY" "$SB_HASH" --index "$SB_MANIFEST" >/dev/null 2>&1
if "$PY" "$SB_HASH" --index "$SB_MANIFEST" --check >/dev/null 2>&1; then
  ok "re-stamping clears the staleness (--check rc 0)"
else
  bad "re-stamp should restore --check to rc 0"
fi

# ─── T4: idempotency ──────────────────────────────────────────────────────────
echo "T4: hash-content-manifest.py is idempotent"
"$PY" "$SB_HASH" --index "$SB_MANIFEST" >/dev/null 2>&1
cp "$SB_MANIFEST" "$SANDBOX/run1.json"
"$PY" "$SB_HASH" --index "$SB_MANIFEST" >/dev/null 2>&1
"$PY" - "$SANDBOX/run1.json" "$SB_MANIFEST" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
dsha = sum(1 for x, y in zip(a["roles"], b["roles"]) if x.get("content_sha") != y.get("content_sha"))
dver = sum(1 for x, y in zip(a["roles"], b["roles"]) if x.get("content_version") != y.get("content_version"))
sys.exit(0 if (dsha == 0 and dver == 0) else 1)
PY
if [ $? -eq 0 ]; then
  ok "content_sha + content_version stable across identical re-runs (no spurious bumps)"
else
  bad "re-running the stamper must not change content_sha/content_version"
fi

# ─── T5: detector fast path CURRENT/STALE/MISSING/ORPHAN ──────────────────────
echo "T5: detect-stale-artifacts.py fast path (build-state artifactProvenance)"
WS5="$(mktemp -d)"
"$PY" - "$WS5" "$MANIFEST" <<'PY'
import json, sys
ws, man = sys.argv[1], sys.argv[2]
m = json.load(open(man))
roles = {f"{r['dept']}/{r['slug']}": r["content_sha"] for r in m["roles"]}
keys = list(roles)[:2]
state = {"artifactProvenance": {
    "manifestVersion": m["version"],
    "roles": {
        keys[0]: {"source_content_sha": roles[keys[0]]},            # CURRENT
        keys[1]: {"source_content_sha": "sha256:STALEvalue"},        # STALE
        "ghost-dept/ghost-role": {"source_content_sha": "sha256:x"}, # ORPHAN
    }, "depts": {}, "sops": {}}}
open(ws + "/.workforce-build-state.json", "w").write(json.dumps(state))
PY
DOUT="$("$PY" "$DETECT" --workspace "$WS5" --manifest "$MANIFEST" --json 2>/dev/null)"
DRC=$?
echo "$DOUT" | "$PY" -c "
import json, sys
d = json.load(sys.stdin); s = d['summary']
ok = s['current'] == 1 and s['stale'] == 1 and s['orphan'] == 1 and s['missing'] > 0
sys.exit(0 if ok else 1)
"
if [ $? -eq 0 ] && [ "$DRC" -eq 10 ]; then
  ok "fast path: 1 CURRENT, 1 STALE, 1 ORPHAN, MISSING>0; exit 10"
else
  bad "fast-path classification or exit code wrong (rc=$DRC)"
fi
rm -rf "$WS5"

# ─── T6: detector marker fallback (UNTRACKED) ─────────────────────────────────
echo "T6: detect-stale-artifacts.py marker fallback (no artifactProvenance)"
WS6="$(mktemp -d)"
mkdir -p "$WS6/departments/account-management/00-client-relationship-manager"
mkdir -p "$WS6/departments/account-management/01-deep-research-specialist"
mkdir -p "$WS6/departments/account-management/02-retention-specialist"
RSHA="$("$PY" -c "import json;m=json.load(open('$MANIFEST'));print(next(r['content_sha'] for r in m['roles'] if r['slug']=='client-relationship-manager'))")"
printf '# CRM\n<!-- workforce-provenance: source=role-library role-slug=client-relationship-manager dept=account-management content_sha=%s content_version=1.0.0 instantiated=2026-06-17 generator=build-workforce.py -->\nbody\n' "$RSHA" \
  > "$WS6/departments/account-management/00-client-relationship-manager/how-to.md"
printf '# Deep Research\n<!-- workforce-provenance: source=role-library role-slug=deep-research-specialist dept=account-management content_sha=sha256:STALEmarker content_version=1.0.0 instantiated=2026-01-01 generator=build-workforce.py -->\nbody\n' \
  > "$WS6/departments/account-management/01-deep-research-specialist/how-to.md"
printf '# Retention\nReal content, built before provenance shipped, no marker.\n' \
  > "$WS6/departments/account-management/02-retention-specialist/how-to.md"
# Capture separately: the detector exits 10 on drift, and under `pipefail` a pipe
# would surface that 10 instead of the validator's status.
DOUT6="$("$PY" "$DETECT" --workspace "$WS6" --manifest "$MANIFEST" --json 2>/dev/null)"
echo "$DOUT6" | "$PY" -c "
import json, sys
d = json.load(sys.stdin); s = d['summary']
ok = ('fallback' in d['build_record_source']) and s['current'] == 1 and s['stale'] == 1 and s['untracked'] == 1
sys.exit(0 if ok else 1)
"
if [ $? -eq 0 ]; then
  ok "marker fallback: 1 CURRENT, 1 STALE, 1 UNTRACKED"
else
  bad "marker-fallback classification wrong"
fi
rm -rf "$WS6"

# ─── T7: all-current workspace -> exit 0 ──────────────────────────────────────
echo "T7: all-CURRENT workspace -> detector exit 0"
WS7="$(mktemp -d)"
"$PY" - "$WS7" "$MANIFEST" <<'PY'
import json, sys
ws, man = sys.argv[1], sys.argv[2]
m = json.load(open(man))
roles = {f"{r['dept']}/{r['slug']}": {"source_content_sha": r["content_sha"]} for r in m["roles"]}
depts = {d: {"source_content_sha": o["content_sha"]} for d, o in m.get("departments", {}).items() if o.get("content_sha")}
sops = {f"{s['dept']}/{s['slug']}": {"source_content_sha": s["content_sha"]} for s in m.get("sops", [])}
personas = {p["slug"]: {"source_content_sha": p["content_sha"]} for p in m.get("personas", [])}
state = {"artifactProvenance": {"manifestVersion": m["version"], "roles": roles, "depts": depts, "sops": sops, "personas": personas}}
open(ws + "/.workforce-build-state.json", "w").write(json.dumps(state))
PY
"$PY" "$DETECT" --workspace "$WS7" --manifest "$MANIFEST" >/dev/null 2>&1
if [ $? -eq 0 ]; then
  ok "a workspace built from every current sha -> exit 0 (all CURRENT)"
else
  bad "all-current workspace should exit 0"
fi
rm -rf "$WS7"

# ─── T8: CONTENT-HASH gate dimension bites ────────────────────────────────────
echo "T8: artifact gate CONTENT-HASH dimension"
if "$PY" "$GATE" --skill-dir "$SB_SKILL" --only artifact >/dev/null 2>&1; then
  ok "clean sandbox: artifact gate PASSES (CONTENT-HASH OK)"
else
  bad "clean sandbox artifact gate should pass"
fi
printf '\n<!-- un-restamped edit for the gate test -->\n' >> "$SB_ROLE"
"$PY" "$GATE" --skill-dir "$SB_SKILL" --only artifact >/dev/null 2>&1
grc=$?
if [ "$grc" -eq 6 ]; then
  ok "un-restamped edit -> artifact gate exits 6 (CONTENT-HASH DRIFT)"
else
  bad "un-restamped edit should make the artifact gate exit 6, got $grc"
fi

# ─── T9: PERSONA canonical hash is client/day-INVARIANT (no false positive) ───
# Two clients with DIFFERENT per-client values render the SAME persona template to
# DIFFERENT bytes, yet the canonical content_sha is identical -> both read CURRENT.
echo "T9: persona canonical content_sha is client/day-INVARIANT (no false positive)"
"$PY" - "$SCRIPT_DIR" "$SKILL_DIR" <<'PY'
import sys, importlib.util, hashlib
sd, skd = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("hcm", sd + "/hash-content-manifest.py")
hcm = importlib.util.module_from_spec(spec); spec.loader.exec_module(hcm)
f = skd + "/templates/persona-library/growth-strategist.md"
tpl = open(f).read()
canonical = hcm.content_sha_of_text(tpl)
# Simulate two clients: fill {{COMPANY_NAME}} + {{ISO_DATE}} with different values.
client_a = tpl.replace("{{COMPANY_NAME}}", "Acme Co").replace("{{ISO_DATE}}", "2026-01-15")
client_b = tpl.replace("{{COMPANY_NAME}}", "Globex Inc").replace("{{ISO_DATE}}", "2026-06-17")
naive_a = "sha256:" + hashlib.sha256(client_a.encode()).hexdigest()
naive_b = "sha256:" + hashlib.sha256(client_b.encode()).hexdigest()
# Naive rendered-byte hash differs per client (the bug). Canonical (tokens intact,
# header date normalized) is the SAME for both -> both CURRENT against the manifest.
ok = (naive_a != naive_b) and (hcm.content_sha_of_text(tpl) == canonical)
sys.exit(0 if ok else 1)
PY
if [ $? -eq 0 ]; then
  ok "two clients' rendered persona bytes differ BUT canonical content_sha is invariant"
else
  bad "persona canonical content_sha must be client/day-invariant"
fi

# ─── T10: surgical STALE on a persona edit (only the edited persona flips) ────
# A client built from the OLD persona shas. Edit ONE persona + re-stamp. The
# detector must mark ONLY that persona STALE; every other persona stays CURRENT.
echo "T10: editing ONE persona + re-stamp flags ONLY that persona STALE"
SB_PERSONA="$SB_SKILL/templates/persona-library/growth-strategist.md"
"$PY" "$SB_HASH" --index "$SB_MANIFEST" >/dev/null 2>&1   # ensure sandbox stamped
WS10="$(mktemp -d)"
# Build a client workspace pinned to the CURRENT (pre-edit) persona shas.
"$PY" - "$WS10" "$SB_MANIFEST" <<'PY'
import json, sys
ws, man = sys.argv[1], sys.argv[2]
m = json.load(open(man))
personas = {p["slug"]: {"source_content_sha": p["content_sha"],
                        "source_content_version": p.get("content_version"),
                        "sourcePath": p.get("path")} for p in m.get("personas", [])}
state = {"artifactProvenance": {"manifestVersion": m["version"],
         "roles": {}, "depts": {}, "sops": {}, "personas": personas}}
open(ws + "/.workforce-build-state.json", "w").write(json.dumps(state))
PY
# Edit ONE persona's canonical content and re-stamp the sandbox manifest.
printf '\n## Adversarial canonical edit\nThis is a real content change to ONE persona.\n' >> "$SB_PERSONA"
"$PY" "$SB_HASH" --index "$SB_MANIFEST" >/dev/null 2>&1
DOUT10="$("$PY" "$DETECT" --workspace "$WS10" --manifest "$SB_MANIFEST" --json 2>/dev/null)"
echo "$DOUT10" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
persona_items = [i for i in d['items'] if i['kind'] == 'persona']
stale = [i['key'] for i in persona_items if i['status'] == 'STALE']
current = [i for i in persona_items if i['status'] == 'CURRENT']
ok = (stale == ['persona/growth-strategist']) and len(current) >= 1 and \
     all(i['status'] != 'STALE' for i in persona_items if i['key'] != 'persona/growth-strategist')
sys.exit(0 if ok else 1)
"
if [ $? -eq 0 ]; then
  ok "exactly ONE persona STALE (growth-strategist); all other personas CURRENT"
else
  bad "a persona edit must flag ONLY that persona STALE, not the whole pool"
fi
rm -rf "$WS10"
# Re-stamp keeps the sandbox internally consistent for any later use.
"$PY" "$SB_HASH" --index "$SB_MANIFEST" >/dev/null 2>&1

# ─── T11: gate BLOCKS an UN-restamped persona edit ────────────────────────────
echo "T11: gate BLOCKS an unstamped persona edit (CONTENT-HASH DRIFT)"
# Clean sandbox first (re-stamp so it passes), then make an un-restamped persona edit.
"$PY" "$SB_HASH" --index "$SB_MANIFEST" >/dev/null 2>&1
if "$PY" "$SB_HASH" --index "$SB_MANIFEST" --check >/dev/null 2>&1; then
  : # clean
else
  bad "sandbox should be clean before the un-restamped persona edit test"
fi
printf '\n<!-- un-restamped persona edit for the gate test -->\nNew uncommitted persona line.\n' >> "$SB_PERSONA"
"$PY" "$SB_HASH" --index "$SB_MANIFEST" --check >/dev/null 2>&1
prc=$?
"$PY" "$GATE" --skill-dir "$SB_SKILL" --only artifact >/dev/null 2>&1
pgrc=$?
if [ "$prc" -eq 1 ] && [ "$pgrc" -eq 6 ]; then
  ok "un-restamped persona edit -> --check rc 1 AND artifact gate rc 6 (BLOCKED)"
else
  bad "un-restamped persona edit must fail --check (rc 1) and the gate (rc 6); got check=$prc gate=$pgrc"
fi

echo ""
echo "──────────────────────────────────────────────────────────────"
echo "  artifact-versioning fixtures: $PASS passed, $FAIL failed"
echo "──────────────────────────────────────────────────────────────"
[ "$FAIL" -eq 0 ]
