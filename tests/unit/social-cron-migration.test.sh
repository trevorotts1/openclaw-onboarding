#!/usr/bin/env bash
# tests/unit/social-cron-migration.test.sh
#
# Hermetic regression lock for the 35 -> 57 weekly-social cron migration
# (57-social-media-in-a-box/scripts/register-social-cron.sh +
#  scripts/migrate-35-to-57.sh).
#
# Proves, against a sandboxed HOME with a stubbed `openclaw` CLI and a stubbed
# `crontab` (every store MUTATION appends a timestamped snapshot of BOTH stores
# to a timeline log):
#   T1  CONFIG GATE — no client config => --apply exits 8 and NOTHING changes
#       (the live Skill-35 cron stays armed; no receipt; never half-migrated).
#   T2  HAPPY PATH — a box with a live skill35-weekly-theme gateway cron, a
#       legacy weekly-batch crontab line, a stale v1 `# oc-skill57` crontab
#       line, and a Skill-35 week marker migrates to EXACTLY ONE
#       social-media-weekly-theme gateway cron, zero legacy in either store,
#       the weekISO marker + themeOfWeek carried, and a MIGRATED receipt.
#   T3  ATOMICITY (no double-post window) — replaying the store timeline, NO
#       snapshot ever shows a Skill-57 weekly trigger armed at the same time
#       as ANY Skill-35 trigger (gateway or crontab).
#   T4  IDEMPOTENCY — re-running --apply (migration and registrar) exits 0,
#       keeps exactly one entry, and the timeline stays double-post-free.
#   T5  FIRE-WINDOW GUARD — Saturday 08:00 refuses (exit 9), stores untouched.
#   T6  INVARIANT + SELF-HEAL — a re-injected legacy cron flips --check to
#       exit 2; a re-run of --apply heals it back to exactly one.
#   T7  ROLLBACK — --rollback re-arms exactly one skill35-weekly-theme and
#       removes the 57 cron (still never both at once); --apply re-migrates.
#
# No network, no live client, no real OpenClaw install is touched.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTRAR="$REPO_ROOT/57-social-media-in-a-box/scripts/register-social-cron.sh"
MIGRATE="$REPO_ROOT/57-social-media-in-a-box/scripts/migrate-35-to-57.sh"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok  - $*"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL - $*" >&2; }
assert_eq() { # assert_eq <label> <want> <got>
    if [ "$2" = "$3" ]; then ok "$1"; else fail "$1 (want '$2', got '$3')"; fi
}

# ── static: both scripts parse ───────────────────────────────────────────────
echo "== static =="
bash -n "$REGISTRAR" && ok "register-social-cron.sh parses (bash -n)" || fail "register-social-cron.sh does not parse"
bash -n "$MIGRATE"   && ok "migrate-35-to-57.sh parses (bash -n)"      || fail "migrate-35-to-57.sh does not parse"

# ── sandbox ──────────────────────────────────────────────────────────────────
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX/home"
mkdir -p "$HOME"
STATE="$SANDBOX/state"; mkdir -p "$STATE"
: > "$STATE/gateway.txt"      # one cron per line: <name>|<schedule>|<target>
: > "$STATE/crontab.txt"
: > "$STATE/timeline.log"     # snapshot of BOTH stores after every mutation

MOCKBIN="$SANDBOX/bin"; mkdir -p "$MOCKBIN"

# Shared snapshot helper (sourced by both mocks): records which weekly-social
# triggers are ARMED in each store right now.
cat > "$MOCKBIN/snapshot-stores.sh" <<'SNAP'
#!/usr/bin/env bash
STATE_DIR="$(dirname "$0")/../state"
g=""
while IFS='|' read -r name _rest; do
    [ -n "$name" ] && g="$g,$name"
done < "$STATE_DIR/gateway.txt"
c=""
grep -q "skill35-weekly-theme" "$STATE_DIR/crontab.txt" && c="$c,ct:skill35-weekly-theme"
grep -q "weekly-batch"         "$STATE_DIR/crontab.txt" && c="$c,ct:weekly-batch"
grep -q "oc-skill57"           "$STATE_DIR/crontab.txt" && c="$c,ct:oc-skill57"
echo "G=[${g#,}] C=[${c#,}]" >> "$STATE_DIR/timeline.log"
SNAP
chmod +x "$MOCKBIN/snapshot-stores.sh"

# Stub openclaw CLI: cron list / cron add / cron delete (--name | --id)
cat > "$MOCKBIN/openclaw" <<'MOCK'
#!/usr/bin/env bash
STATE_DIR="$(dirname "$0")/../state"
GW="$STATE_DIR/gateway.txt"
snap() { bash "$(dirname "$0")/snapshot-stores.sh"; }
case "${1:-} ${2:-}" in
  "cron list")
      i=0
      while IFS='|' read -r name sched target; do
          [ -z "$name" ] && continue
          i=$((i+1))
          printf '%08d-1111-2222-3333-%012d  %s  "%s"  sessionTarget=%s\n' "$i" "$i" "$name" "$sched" "$target"
      done < "$GW"
      exit 0 ;;
  "cron add")
      shift 2
      name="" sched="" target=""
      while [ $# -gt 0 ]; do
          case "$1" in
              --name) name="$2"; shift 2 ;;
              --cron) sched="$2"; shift 2 ;;
              --session-target) target="$2"; shift 2 ;;
              --agent|--message) shift 2 ;;
              *) shift ;;
          esac
      done
      [ -n "$name" ] || exit 1
      echo "$name|$sched|$target" >> "$GW"
      snap; exit 0 ;;
  "cron delete")
      shift 2
      byname="" byid=""
      while [ $# -gt 0 ]; do
          case "$1" in
              --name) byname="$2"; shift 2 ;;
              --id) byid="$2"; shift 2 ;;
              *) shift ;;
          esac
      done
      tmp="$GW.tmp"; : > "$tmp"
      i=0
      while IFS='|' read -r name sched target; do
          [ -z "$name" ] && continue
          i=$((i+1))
          id="$(printf '%08d-1111-2222-3333-%012d' "$i" "$i")"
          if [ -n "$byname" ] && [ "$name" = "$byname" ]; then continue; fi
          if [ -n "$byid" ] && [ "$id" = "$byid" ]; then continue; fi
          echo "$name|$sched|$target" >> "$tmp"
      done < "$GW"
      mv "$tmp" "$GW"
      snap; exit 0 ;;
  "config validate")
      exit 0 ;;
  *)
      exit 0 ;;
esac
MOCK
chmod +x "$MOCKBIN/openclaw"

# Stub crontab: -l prints, '-' (stdin) replaces
cat > "$MOCKBIN/crontab" <<'MOCK'
#!/usr/bin/env bash
STATE_DIR="$(dirname "$0")/../state"
CT="$STATE_DIR/crontab.txt"
case "${1:-}" in
  -l) cat "$CT"; exit 0 ;;
  -)  cat > "$CT"; bash "$(dirname "$0")/snapshot-stores.sh"; exit 0 ;;
  *)  cat > "$CT"; bash "$(dirname "$0")/snapshot-stores.sh"; exit 0 ;;
esac
MOCK
chmod +x "$MOCKBIN/crontab"

export PATH="$MOCKBIN:$PATH"
export OPENCLAW_BIN="openclaw"
unset SMIB_CLIENT_CONFIG SKILL35_CONTENT_SHEET_ID CONTENT_SHEET_ID 2>/dev/null || true

STATE_DIR_57="$HOME/.openclaw/data/skill57"
STATE_DIR_35="$HOME/.openclaw/data/skill35"
CONFIG="$STATE_DIR_57/client-config.json"
RECEIPT="$STATE_DIR_57/migration-35-to-57.json"
MARKER_57="$STATE_DIR_57/weekly-theme-last-run.json"
mkdir -p "$STATE_DIR_35" "$STATE_DIR_57"

gw_count() { grep -c "^$1|" "$STATE/gateway.txt" 2>/dev/null || true; }

seed_legacy_box() {
    # a live pre-migration box: 35's gateway cron + legacy crontab lines + week marker
    printf '%s|%s|%s\n' "skill35-weekly-theme" "0 8 * * 6" "main" > "$STATE/gateway.txt"
    {
        echo '0 9 * * 1 bash /fake/35-social-media-planner/scripts/weekly-batch.sh'
        echo '0 8 * * 6 bash /fake/entry.sh --mode plan --plan # oc-skill57 social-media-weekly-theme'
    } > "$STATE/crontab.txt"
    printf '{"weekISO": "2026-W27", "theme": "sandbox test theme", "firedAt": "2026-07-04T08:00:00Z"}\n' \
        > "$STATE_DIR_35/weekly-theme-last-run.json"
}

write_valid_config() {
    # dummy, non-secret-shaped values (short on purpose: no real key shapes)
    cat > "$CONFIG" <<'JSON'
{
  "brandName": "Sandbox Brand",
  "pit": "pit-test",
  "locationId": "loc-test",
  "userId": "user-test",
  "openrouterKey": "sk-or-test",
  "openrouterModel": "test/model-one",
  "openrouterFallbacks": ["test/model-two", "test/model-three"],
  "kieKey": "kie-test",
  "geminiKey": "gm-test",
  "platforms": ["facebook"],
  "postTypes": ["post"],
  "timezone": "America/New_York",
  "status": "Paid"
}
JSON
}

# ═════ T1 — CONFIG GATE: no config => exit 8, nothing changed, no receipt ════
echo "== T1 config gate (skip, never half-migrate) =="
seed_legacy_box
rm -f "$CONFIG" "$RECEIPT" "$MARKER_57"
before_gw="$(cat "$STATE/gateway.txt")"; before_ct="$(cat "$STATE/crontab.txt")"

set +e; bash "$REGISTRAR" --apply --force-window >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "registrar --apply without config exits 8" "8" "$rc"
set +e; bash "$MIGRATE" --apply --force-window >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "migrate --apply without config exits 8" "8" "$rc"
assert_eq "gateway store untouched on gate-skip" "$before_gw" "$(cat "$STATE/gateway.txt")"
assert_eq "crontab untouched on gate-skip" "$before_ct" "$(cat "$STATE/crontab.txt")"
[ ! -f "$RECEIPT" ] && ok "no receipt written on gate-skip" || fail "receipt written on gate-skip"
assert_eq "skill35 cron still armed after skip" "1" "$(gw_count skill35-weekly-theme)"

# gate must also fail CLOSED on an INCOMPLETE config (missing secret)
python3 - "$CONFIG" <<'PY'
import json, sys
cfg = {"brandName": "Sandbox Brand", "locationId": "loc-test", "status": "Paid"}
json.dump(cfg, open(sys.argv[1], "w"))
PY
set +e; bash "$MIGRATE" --apply --force-window >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "migrate --apply with incomplete config exits 8" "8" "$rc"
assert_eq "skill35 cron still armed after incomplete-config skip" "1" "$(gw_count skill35-weekly-theme)"

# ═════ T2 — HAPPY PATH ═══════════════════════════════════════════════════════
echo "== T2 happy path =="
seed_legacy_box
write_valid_config
rm -f "$RECEIPT" "$MARKER_57"
: > "$STATE/timeline.log"

set +e; bash "$MIGRATE" --apply --force-window >"$SANDBOX/t2.out" 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "migrate --apply exits 0" "0" "$rc"
assert_eq "exactly one social-media-weekly-theme in gateway" "1" "$(gw_count social-media-weekly-theme)"
assert_eq "zero skill35-weekly-theme in gateway" "0" "$(gw_count skill35-weekly-theme)"
if grep -Eq 'skill35-weekly-theme|weekly-batch|oc-skill35|# oc-skill57' "$STATE/crontab.txt"; then
    fail "legacy/stale lines remain in crontab"
else
    ok "crontab swept of legacy + stale v1 lines"
fi
if [ -f "$MARKER_57" ] && grep -q '2026-W27' "$MARKER_57"; then
    ok "Skill-35 weekISO marker carried to Skill 57 (2026-W27)"
else
    fail "weekISO marker not carried"
fi
if python3 -c "import json,sys;cfg=json.load(open('$CONFIG'));sys.exit(0 if cfg.get('themeOfWeek')=='sandbox test theme' else 1)"; then
    ok "themeOfWeek re-pointed into the client config"
else
    fail "themeOfWeek not carried into the client config"
fi
if python3 -c "import json,sys;r=json.load(open('$RECEIPT'));sys.exit(0 if r.get('state')=='MIGRATED' and r.get('invariant')=='PASS' else 1)"; then
    ok "receipt state=MIGRATED, invariant=PASS"
else
    fail "receipt missing or not MIGRATED/PASS"
fi
set +e; bash "$REGISTRAR" --check >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "registrar --check passes post-migration" "0" "$rc"
set +e; bash "$MIGRATE" --check >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "migrate --check passes post-migration" "0" "$rc"

# ═════ T3 — ATOMICITY: replay the store timeline ═════════════════════════════
echo "== T3 atomicity (no snapshot with both triggers armed) =="
if python3 - "$STATE/timeline.log" <<'PY'
import re, sys
bad = []
for i, line in enumerate(open(sys.argv[1]), 1):
    m = re.match(r"G=\[(.*?)\] C=\[(.*?)\]", line.strip())
    if not m:
        continue
    gw = [x for x in m.group(1).split(",") if x]
    ct = [x for x in m.group(2).split(",") if x]
    has57 = "social-media-weekly-theme" in gw or any("oc-skill57" in x for x in ct)
    has35 = "skill35-weekly-theme" in gw or any(
        "skill35-weekly-theme" in x or "weekly-batch" in x or "oc-skill35" in x for x in ct)
    if has57 and has35:
        bad.append((i, line.strip()))
for i, line in bad:
    print("  DOUBLE-ARMED at mutation %d: %s" % (i, line))
sys.exit(1 if bad else 0)
PY
then
    ok "no store snapshot ever had a 57 trigger and a 35 trigger armed together"
else
    fail "a snapshot had BOTH weekly triggers armed (double-post window)"
fi

# ═════ T4 — IDEMPOTENCY ══════════════════════════════════════════════════════
echo "== T4 idempotency =="
set +e; bash "$MIGRATE" --apply --force-window >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "second migrate --apply exits 0" "0" "$rc"
assert_eq "still exactly one 57 cron after re-run" "1" "$(gw_count social-media-weekly-theme)"
set +e; bash "$REGISTRAR" --apply --force-window >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "standalone registrar re-apply exits 0" "0" "$rc"
assert_eq "still exactly one 57 cron after registrar re-run" "1" "$(gw_count social-media-weekly-theme)"
if python3 -c "import json,sys;r=json.load(open('$RECEIPT'));sys.exit(0 if r.get('firstMigratedAt') and r.get('state')=='MIGRATED' else 1)"; then
    ok "receipt keeps firstMigratedAt across re-runs"
else
    fail "receipt lost state on re-run"
fi
# timeline must STILL be double-post-free after the re-runs
if python3 - "$STATE/timeline.log" <<'PY'
import re, sys
for line in open(sys.argv[1]):
    m = re.match(r"G=\[(.*?)\] C=\[(.*?)\]", line.strip())
    if not m:
        continue
    gw = [x for x in m.group(1).split(",") if x]
    ct = [x for x in m.group(2).split(",") if x]
    has57 = "social-media-weekly-theme" in gw or any("oc-skill57" in x for x in ct)
    has35 = "skill35-weekly-theme" in gw or any(
        "skill35-weekly-theme" in x or "weekly-batch" in x or "oc-skill35" in x for x in ct)
    if has57 and has35:
        sys.exit(1)
sys.exit(0)
PY
then ok "timeline still double-post-free after re-runs"; else fail "re-run created a double-armed snapshot"; fi

# ═════ T5 — FIRE-WINDOW GUARD ════════════════════════════════════════════════
echo "== T5 fire-window guard =="
before_gw="$(cat "$STATE/gateway.txt")"
set +e; SMIB_TEST_NOW_U=6 SMIB_TEST_NOW_HM=0800 bash "$MIGRATE" --apply >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "migrate inside Saturday 08:00 window exits 9" "9" "$rc"
set +e; SMIB_TEST_NOW_U=6 SMIB_TEST_NOW_HM=0800 bash "$REGISTRAR" --apply >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "registrar inside Saturday 08:00 window exits 9" "9" "$rc"
assert_eq "stores untouched by window refusal" "$before_gw" "$(cat "$STATE/gateway.txt")"
set +e; SMIB_TEST_NOW_U=3 SMIB_TEST_NOW_HM=0800 bash "$MIGRATE" --apply >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "Wednesday 08:00 is outside the guard window" "0" "$rc"

# ═════ T6 — INVARIANT + SELF-HEAL ════════════════════════════════════════════
echo "== T6 invariant violation detection + self-heal =="
printf '%s|%s|%s\n' "skill35-weekly-theme" "0 8 * * 6" "main" >> "$STATE/gateway.txt"
set +e; bash "$REGISTRAR" --check >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "re-injected legacy cron flips --check to 2" "2" "$rc"
set +e; bash "$MIGRATE" --check >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "migrate --check also reports the violation" "2" "$rc"
set +e; bash "$MIGRATE" --apply --force-window >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "re-running --apply heals the violation" "0" "$rc"
assert_eq "healed: zero legacy" "0" "$(gw_count skill35-weekly-theme)"
assert_eq "healed: exactly one 57 cron" "1" "$(gw_count social-media-weekly-theme)"

# ═════ T7 — ROLLBACK (uses the REAL Skill-35 registrar against the stubs) ════
echo "== T7 rollback + re-migrate =="
set +e; bash "$MIGRATE" --rollback >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "rollback exits 0" "0" "$rc"
assert_eq "rollback: exactly one skill35 cron re-armed" "1" "$(gw_count skill35-weekly-theme)"
assert_eq "rollback: zero 57 crons" "0" "$(gw_count social-media-weekly-theme)"
if python3 -c "import json,sys;r=json.load(open('$RECEIPT'));sys.exit(0 if r.get('state')=='ROLLED_BACK' else 1)"; then
    ok "receipt state=ROLLED_BACK"
else
    fail "receipt not ROLLED_BACK"
fi
set +e; bash "$MIGRATE" --apply --force-window >/dev/null 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "re-migrate after rollback exits 0" "0" "$rc"
assert_eq "re-migrated: exactly one 57 cron" "1" "$(gw_count social-media-weekly-theme)"
assert_eq "re-migrated: zero legacy" "0" "$(gw_count skill35-weekly-theme)"
# final full-timeline atomicity sweep (covers rollback + re-migrate too)
if python3 - "$STATE/timeline.log" <<'PY'
import re, sys
for line in open(sys.argv[1]):
    m = re.match(r"G=\[(.*?)\] C=\[(.*?)\]", line.strip())
    if not m:
        continue
    gw = [x for x in m.group(1).split(",") if x]
    ct = [x for x in m.group(2).split(",") if x]
    has57 = "social-media-weekly-theme" in gw or any("oc-skill57" in x for x in ct)
    has35 = "skill35-weekly-theme" in gw or any(
        "skill35-weekly-theme" in x or "weekly-batch" in x or "oc-skill35" in x for x in ct)
    if has57 and has35:
        sys.exit(1)
sys.exit(0)
PY
then ok "full timeline (incl. rollback + re-migrate) is double-post-free"; else fail "rollback/re-migrate created a double-armed snapshot"; fi

# ── summary ──────────────────────────────────────────────────────────────────
echo ""
echo "== social-cron-migration: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
