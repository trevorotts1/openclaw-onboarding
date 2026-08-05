#!/usr/bin/env bash
# test-prebuild-standard.sh — PHASE 2 verification gate (AI Workforce
# standard-first redesign, master plan 2026-08-04).
#
# Exercises scripts/prebuild-standard-workforce.{sh,py} (the standard prebuild
# driver) end-to-end in a HERMETIC sandbox: sandboxed $HOME, scratch company
# dir, scratch build-state, scratch Command Center database. Writes NOTHING
# under the real ~/.openclaw, ~/clawd, or any live Command Center db — the
# operator box is itself a built client, so every path is pinned explicitly
# (the same explicit-signal-only discipline materialize-missing-departments.py
# was built under after its own live incident).
#
# Assertions:
#   T1  refuses without an operator consent record          (exit 2)
#   T2  refuses a malformed consent record                  (exit 2)
#   T3  refuses when interviewComplete is already true      (exit 4)
#   T4  refuses a box frozen buildType=legacy               (exit 5)
#   T5  dry-run computes the live floor, mutates NOTHING    (exit 0)
#   T6  --apply: floor met, state shape correct, departments status=prebuilt,
#       chosen artifact seeded, billing-finance/legal NOT empty (alias trap),
#       CC board join PROVEN (chosen == provisioned == displayed), and the
#       run is IDEMPOTENT + ADDITIVE-ONLY (sentinel file untouched)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DRIVER="$REPO_ROOT/scripts/prebuild-standard-workforce.sh"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

if [ ! -f "$DRIVER" ]; then
  bad "driver not found at $DRIVER"
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SANDBOX_HOME="$TMP/home"
COMPANY="$SANDBOX_HOME/clawd/zero-human-company/scratch-canary"
STATE="$TMP/state.json"
DB="$TMP/mission-control.db"
CONSENT="$TMP/consent.json"
mkdir -p "$COMPANY/departments"
printf '{"decision":"prebuild","source":"operator-prebuild","decidedAt":"2026-08-04T12:00:00Z","decidedBy":"test-operator","sessionId":"sess-test"}\n' > "$CONSENT"
echo '{}' > "$STATE"

run_driver() {
  HOME="$SANDBOX_HOME" bash "$DRIVER" "$@"
}

# ── T1: consent gate — no consent record ─────────────────────────────────────
echo '{}' > "$STATE"
run_driver --departments-dir "$COMPANY/departments" --build-state-file "$STATE" --json \
  > "$TMP/t1.json" 2>"$TMP/t1.err"
RC=$?
if [ "$RC" -eq 2 ]; then good "T1: refuses without operator consent (rc=2)"; else bad "T1: expected rc=2, got $RC"; fi

# ── T2: consent gate — malformed record (missing sessionId) ─────────────────
printf '{"decision":"prebuild","source":"operator-prebuild","decidedAt":"2026-08-04T12:00:00Z","decidedBy":"test-operator"}\n' > "$TMP/consent-bad.json"
run_driver --operator-consent-file "$TMP/consent-bad.json" \
  --departments-dir "$COMPANY/departments" --build-state-file "$STATE" --json \
  > "$TMP/t2.json" 2>"$TMP/t2.err"
RC=$?
if [ "$RC" -eq 2 ]; then good "T2: refuses malformed consent record (rc=2)"; else bad "T2: expected rc=2, got $RC"; fi

# ── T3: interviewComplete already true ───────────────────────────────────────
echo '{"interviewComplete":true}' > "$STATE"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --build-state-file "$STATE" --json \
  > "$TMP/t3.json" 2>"$TMP/t3.err"
RC=$?
if [ "$RC" -eq 4 ]; then good "T3: refuses when interviewComplete=true (rc=4)"; else bad "T3: expected rc=4, got $RC"; fi

# ── T4: box frozen buildType=legacy ──────────────────────────────────────────
echo '{"buildType":"legacy"}' > "$STATE"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --build-state-file "$STATE" --json \
  > "$TMP/t4.json" 2>"$TMP/t4.err"
RC=$?
if [ "$RC" -eq 5 ]; then good "T4: refuses a frozen legacy box (rc=5)"; else bad "T4: expected rc=5, got $RC"; fi

# ── T5: dry-run — live floor computed, NOTHING mutated ──────────────────────
echo '{}' > "$STATE"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --company-slug "scratch-canary" \
  --build-state-file "$STATE" --json > "$TMP/t5.json" 2>"$TMP/t5.err"
RC=$?
N_DEPTS=$(find "$COMPANY/departments" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
STATE_AFTER=$(cat "$STATE")
FLOOR_COUNT=$(python3 -c "import json;d=json.load(open('$TMP/t5.json'));print(d.get('expected_floor_count',0))")
if [ "$RC" -eq 0 ] && [ "$N_DEPTS" -eq 0 ] && [ "$STATE_AFTER" = "{}" ] && [ "$FLOOR_COUNT" -ge 29 ]; then
  good "T5: dry-run rc=0, zero dirs created, state untouched, live floor=$FLOOR_COUNT"
else
  bad "T5: dry-run broke hermeticity or floor (rc=$RC dirs=$N_DEPTS state=$STATE_AFTER floor=$FLOOR_COUNT)"
fi

# ── T6: --apply full pipeline ────────────────────────────────────────────────
echo '{}' > "$STATE"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" \
  --company-name "Scratch Canary Co" --company-slug "scratch-canary" \
  --build-state-file "$STATE" --db "$DB" --apply --json \
  > "$TMP/t6.json" 2>"$TMP/t6.err"
RC=$?
if [ "$RC" -eq 0 ]; then good "T6a: --apply succeeds (rc=0)"; else bad "T6a: --apply rc=$RC (see $TMP/t6.err)"; fi

python3 - "$TMP/t6.json" "$STATE" "$COMPANY" "$DB" <<'PY'
import json, sqlite3, sys
result_path, state_path, company, db = sys.argv[1:5]
ok, bad = [], []
d = json.load(open(result_path))
state = json.load(open(state_path))

# state shape
if state.get("buildType") == "standard-first": ok.append("buildType=standard-first")
else: bad.append(f"buildType={state.get('buildType')}")
sp = state.get("standardPrebuild") or {}
if sp.get("status") == "done": ok.append("standardPrebuild.status=done")
else: bad.append(f"standardPrebuild.status={sp.get('status')}")
if sp.get("agentRegistration") == "deferred": ok.append("agentRegistration=deferred")
else: bad.append("agentRegistration wrong")
if sp.get("operatorConsentRef") and "operator-prebuild" in sp["operatorConsentRef"]:
    ok.append("operatorConsentRef provenanced")
else: bad.append("operatorConsentRef missing/wrong")
if sp.get("floorVersion") and "@" in str(sp.get("floorVersion")):
    ok.append(f"floorVersion={sp['floorVersion']}")
else: bad.append("floorVersion missing/malformed")

# departments[] all prebuilt, NEVER pending
depts = state.get("departments") or []
statuses = {e.get("status") for e in depts if isinstance(e, dict)}
if depts and statuses == {"prebuilt"}: ok.append(f"{len(depts)} departments all status=prebuilt")
else: bad.append(f"departments statuses={statuses} count={len(depts)}")

# anti-fabrication: no interview fields, interviewComplete false
if state.get("interviewComplete") is False and "interviewProgress" not in state \
   and "interviewQc" not in state and "verticalPacks" not in state:
    ok.append("no interview fields; interviewComplete=false")
else: bad.append("interview field leak or interviewComplete not false")

# chosen artifact seeded (CEO column + every floor dept)
artifact = json.load(open(f"{company}/departments.json"))
slugs = {e.get("slug") for e in artifact}
if "ceo" in slugs and "billing-finance" in slugs and len(artifact) >= 29:
    ok.append(f"chosen artifact: {len(artifact)} entries incl. ceo + billing-finance")
else: bad.append(f"chosen artifact wrong ({len(artifact)} entries)")

# alias trap: billing-finance + legal materialized with ROLES (not empty)
import pathlib
for dept in ("billing-finance", "legal"):
    p = pathlib.Path(company) / "departments" / dept
    subdirs = [x for x in p.iterdir() if x.is_dir()] if p.is_dir() else []
    if len(subdirs) >= 1: ok.append(f"{dept} NOT empty ({len(subdirs)} entries)")
    else: bad.append(f"{dept} EMPTY — alias trap fired")

# CC board join proven
cs = d.get("cc_seeding") or {}
if cs.get("status") == "OK" and cs.get("join_rc") == 0:
    ok.append("board join OK (chosen==provisioned==displayed)")
else: bad.append(f"board join {cs.get('status')} rc={cs.get('join_rc')}")
conn = sqlite3.connect(db)
rows = [r[0] for r in conn.execute("SELECT slug FROM workspaces")]
if "billing-finance" in rows and "legal" in rows:
    ok.append("workspaces rows include billing-finance + legal")
else: bad.append("workspaces rows missing alias-trap depts")

# self-disable proof
sd = d.get("selfDisable") or {}
if sd.get("cronRegistered") is False: ok.append("self-disable: no cron registered")
else: bad.append("selfDisable.cronRegistered not false")

for line in ok: print(f"PASS: T6 {line}")
for line in bad: print(f"FAIL: T6 {line}")
raise SystemExit(1 if bad else 0)
PY
if [ $? -eq 0 ]; then good "T6b: apply state shape + alias trap + join + self-disable all hold"
else bad "T6b: one or more apply assertions failed"; fi

# ── T6c: idempotent re-run ───────────────────────────────────────────────────
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --company-slug "scratch-canary" \
  --build-state-file "$STATE" --db "$DB" --apply --json \
  > "$TMP/t6c.json" 2>"$TMP/t6c.err"
RC=$?
RERUN_STATUS=$(python3 -c "import json;print(json.load(open('$TMP/t6c.json')).get('standardPrebuildStatus'))")
if [ "$RC" -eq 0 ] && [ "$RERUN_STATUS" = "done" ]; then
  good "T6c: re-run is idempotent (rc=0, status stays done)"
else
  bad "T6c: re-run rc=$RC status=$RERUN_STATUS"
fi

# ── T6d: additive-only — a foreign sentinel file survives a re-run ──────────
echo "SENTINEL-DO-NOT-TOUCH" > "$COMPANY/departments/sales/SENTINEL.md"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --company-slug "scratch-canary" \
  --build-state-file "$STATE" --db "$DB" --apply --json \
  > "$TMP/t6d.json" 2>"$TMP/t6d.err"
if grep -q "SENTINEL-DO-NOT-TOUCH" "$COMPANY/departments/sales/SENTINEL.md" 2>/dev/null; then
  good "T6d: additive-only — sentinel file untouched by re-run"
else
  bad "T6d: sentinel file clobbered — prebuild is NOT additive-only"
fi

echo "=============================================="
echo "test-prebuild-standard.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
