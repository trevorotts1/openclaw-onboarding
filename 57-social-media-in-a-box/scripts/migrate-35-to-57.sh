#!/usr/bin/env bash
# 57-social-media-in-a-box/scripts/migrate-35-to-57.sh
#
# THE mechanized per-box 35 -> 57 migration (merge plan §8, steps 2-6), built so
# the fleet roll of Skill 57 carries ZERO double-post risk. One box, one command.
# =============================================================================
# WHAT IT DOES (each step is check-then-act, so a re-run is always safe):
#   GATE   client-config gate (fail-closed, exit 8): the box must hold the
#          client's OWN GHL PIT + locationId + OpenRouter model/key + Kie +
#          Gemini config (the SAME required-fields + secrets-SET check the
#          preflight gate enforces, imported from preflight_gate.py). A box
#          that fails the gate is cleanly SKIPPED — nothing is touched, the
#          live Skill-35 cron stays authoritative, and the exit code + message
#          flag it for the operator. NEVER a half-migrated box.
#   SNAP   pre-change snapshot (gateway cron list + crontab + the Skill-35 week
#          marker + a sha256 of the client config — never the config itself, so
#          no secret value is ever duplicated) into
#          <openclaw-dir>/data/skill57/migration-backup-<UTC>/
#   CARRY  re-point state BEFORE any cron changes:
#            * Skill 35's weekly-theme-last-run.json (weekISO) -> Skill 57's
#              marker, so the transition week can never run twice;
#            * themeOfWeek from the 35 marker -> client config (if absent);
#            * plannerSheetId from --sheet-id / $SKILL35_CONTENT_SHEET_ID /
#              $CONTENT_SHEET_ID -> client config (if absent) — adopt-existing,
#              never duplicate (merge plan §5.2). Not carried = recorded in the
#              receipt; the planner module adopts/creates on the first plan run.
#   FLIP   retire-then-register via register-social-cron.sh --apply (gateway
#          store): the legacy skill35-weekly-theme gateway cron is deleted and
#          CONFIRMED gone BEFORE social-media-weekly-theme is registered, and
#          legacy crontab lines (weekly-batch / skill35 / stale oc-skill57) are
#          swept — so there is never a moment with BOTH weekly triggers armed.
#          A Saturday 07:45-08:15 fire-window guard (exit 9) keeps the swap off
#          the fire instant, closing the only gap where "neither armed" could
#          drop a fire.
#   QC     cross-store invariant assert (register-social-cron.sh --check):
#          exactly ONE weekly-theme trigger on the box, zero legacy anywhere.
#   RCPT   machine-readable receipt -> <openclaw-dir>/data/skill57/
#          migration-35-to-57.json (state MIGRATED / FAILED_NEEDS_RERUN /
#          ROLLED_BACK, what was carried, invariant result, notes).
#
# WHAT IT DOES NOT DO (by design):
#   * NEVER posts, probes a live endpoint, or messages the client — SILENT.
#   * NEVER prints a secret value (field names only; config is hashed, not copied).
#   * NEVER archives the 35-social-media-planner directory — per the ratified
#     plan, 35 archives per-client only AFTER 57 proves parity end-to-end
#     (independent live-GHL verify), an operator step outside this script.
#   * NEVER runs automatically — fleet rolls only refresh files; THIS script is
#     the explicit per-box operator trigger for the 35->57 flip.
#
# MODES:
#   (none)      dry-run PLAN — read-only, prints current state + what would happen
#   --apply     perform the migration (idempotent; re-run until exit 0)
#   --check     assert the migrated invariant + show the receipt state
#   --rollback  re-arm Skill 35: delete 57's cron, re-register skill35-weekly-theme
#               via 35's own registrar (35's marker/state were never deleted)
#
# EXIT: 0 ok / 2 invariant violated or a store write failed / 3 usage /
#       6 deps missing / 8 config gate: box skipped, nothing changed /
#       9 fire-window guard refused.
# USAGE:
#   bash migrate-35-to-57.sh [--apply|--check|--rollback] [--config PATH]
#                            [--sheet-id ID] [--agent ID] [--force-window]
# TEST SEAMS (never needed in production): $OPENCLAW_BIN, $SMIB_TEST_NOW_U,
# $SMIB_TEST_NOW_HM (same seams as register-social-cron.sh).
# =============================================================================
set -uo pipefail
PROG="migrate-35-to-57.sh"

CRON_NAME="social-media-weekly-theme"
LEGACY_GATEWAY_NAME="skill35-weekly-theme"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(cd "$SELF_DIR/.." && pwd)"
SKILLS_ROOT="$(cd "$ENGINE_DIR/.." && pwd)"
REGISTRAR="$SELF_DIR/register-social-cron.sh"
SKILL35_REGISTRAR="$SKILLS_ROOT/35-social-media-planner/scripts/register-weekly-cron.sh"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

HOME_DIR="${HOME:-/data}"
OPENCLAW_DIR="$HOME_DIR/.openclaw"
[ ! -d "$OPENCLAW_DIR" ] && [ -d "/data/.openclaw" ] && OPENCLAW_DIR="/data/.openclaw"

STATE_DIR="$OPENCLAW_DIR/data/skill57"
MARKER_JSON="$STATE_DIR/weekly-theme-last-run.json"
LEGACY_MARKER_JSON="$OPENCLAW_DIR/data/skill35/weekly-theme-last-run.json"
RECEIPT="$STATE_DIR/migration-35-to-57.json"

MODE="plan" CONFIG="${SMIB_CLIENT_CONFIG:-$STATE_DIR/client-config.json}"
SHEET_ID="${SKILL35_CONTENT_SHEET_ID:-${CONTENT_SHEET_ID:-}}"
AGENT_ID="${SKILL57_CRON_AGENT:-main}"
FORCE_WINDOW=0
while [ $# -gt 0 ]; do
    case "$1" in
        --apply) MODE="apply"; shift ;;
        --check) MODE="check"; shift ;;
        --rollback) MODE="rollback"; shift ;;
        --config) CONFIG="${2:-}"; shift 2 ;;
        --sheet-id) SHEET_ID="${2:-}"; shift 2 ;;
        --agent) AGENT_ID="${2:-}"; shift 2 ;;
        --force-window) FORCE_WINDOW=1; shift ;;
        -h|--help) sed -n '2,66p' "$0"; exit 3 ;;
        *) echo "FATAL [$PROG]: unknown arg $1" >&2; exit 3 ;;
    esac
done

have() { command -v "$1" >/dev/null 2>&1; }
gateway_list() { "$OPENCLAW_BIN" cron list 2>/dev/null || true; }
count_in() {
    local n
    n="$(printf '%s\n' "$2" | grep -c "$1" 2>/dev/null || true)"
    n="${n//[^0-9]/}"; echo "${n:-0}"
}
now_utc() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

write_receipt() {  # write_receipt <state> <notes...>
    local state="$1"; shift
    have python3 || return 0
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    RECEIPT_PATH="$RECEIPT" R_STATE="$state" R_NOW="$(now_utc)" \
    R_WEEKISO="${CARRIED_WEEKISO:-}" R_THEME_CARRIED="${THEME_CARRIED:-no}" \
    R_SHEET_CARRIED="${SHEET_CARRIED:-no}" R_BACKUP="${BACKUP_DIR:-}" \
    R_CFG_SHA="${CONFIG_SHA:-}" R_INVARIANT="${INVARIANT:-unknown}" R_NOTES="$*" \
    python3 - <<'PY' 2>/dev/null || true
import json, os
p = os.environ["RECEIPT_PATH"]
try:
    prev = json.load(open(p))
except Exception:
    prev = {}
rec = {
    "schemaVersion": 1,
    "state": os.environ["R_STATE"],
    "firstMigratedAt": prev.get("firstMigratedAt")
        or (os.environ["R_NOW"] if os.environ["R_STATE"] == "MIGRATED" else None),
    "lastRunAt": os.environ["R_NOW"],
    "carried": {
        "weekISO": os.environ["R_WEEKISO"] or None,
        "themeOfWeek": os.environ["R_THEME_CARRIED"] == "yes",
        "plannerSheetId": os.environ["R_SHEET_CARRIED"] == "yes",
    },
    "backupDir": os.environ["R_BACKUP"] or None,
    "clientConfigSha256": os.environ["R_CFG_SHA"] or None,
    "invariant": os.environ["R_INVARIANT"],
    "notes": [n for n in os.environ["R_NOTES"].split("|") if n],
}
with open(p, "w") as f:
    json.dump(rec, f, indent=2)
    f.write("\n")
PY
}

# ── --check ──────────────────────────────────────────────────────────────────
if [ "$MODE" = "check" ]; then
    rc=0
    bash "$REGISTRAR" --check || rc=$?
    if [ -f "$RECEIPT" ] && have python3; then
        st="$(python3 -c "import json;print(json.load(open('$RECEIPT')).get('state','?'))" 2>/dev/null || echo '?')"
        echo "  receipt: $RECEIPT (state=$st)"
    else
        echo "  receipt: none on this box (migration has not applied here)"
    fi
    exit "$rc"
fi

# ── dry-run plan ─────────────────────────────────────────────────────────────
if [ "$MODE" = "plan" ]; then
    echo "=== [$PROG] 35 -> 57 migration plan (dry-run; nothing changes) ==="
    echo "  gate    : client config $CONFIG (required fields + secrets SET; fail-closed)"
    echo "  carry   : $LEGACY_MARKER_JSON -> $MARKER_JSON ; themeOfWeek -> config ; plannerSheetId (--sheet-id) -> config"
    echo "  retire  : gateway '$LEGACY_GATEWAY_NAME' + legacy crontab lines (confirmed gone BEFORE 57 registers)"
    echo "  register: '$CRON_NAME' 0 8 * * 6 in the gateway store via $REGISTRAR"
    echo "  assert  : exactly one weekly-theme trigger on the box, zero legacy in either store"
    echo "  receipt : $RECEIPT"
    if have "$OPENCLAW_BIN"; then
        GW="$(gateway_list)"
        echo "  current : gateway legacy-35=$(count_in "$LEGACY_GATEWAY_NAME" "$GW"), gateway 57=$(count_in "$CRON_NAME" "$GW")"
    else
        echo "  current : (openclaw CLI not on PATH — gateway state unknown in this dry-run)"
    fi
    [ -f "$CONFIG" ] && echo "  config  : present" || echo "  config  : MISSING (an --apply would SKIP this box, exit 8)"
    echo "  (re-run with --apply to migrate.)"
    exit 0
fi

# ── shared deps for apply/rollback ───────────────────────────────────────────
have "$OPENCLAW_BIN" || { echo "FATAL [$PROG]: openclaw CLI not on PATH." >&2; exit 6; }
have python3 || { echo "FATAL [$PROG]: python3 not found." >&2; exit 6; }

# ── --rollback ───────────────────────────────────────────────────────────────
if [ "$MODE" = "rollback" ]; then
    echo "=== [$PROG] ROLLBACK: re-arming Skill 35 as the weekly trigger ==="
    [ -f "$SKILL35_REGISTRAR" ] || { echo "FATAL [$PROG]: Skill 35 registrar not found at $SKILL35_REGISTRAR — cannot roll back." >&2; exit 2; }
    "$OPENCLAW_BIN" cron delete --name "$CRON_NAME" 2>/dev/null || true
    left="$(count_in "$CRON_NAME" "$(gateway_list)")"
    [ "$left" = "0" ] || { echo "FATAL [$PROG]: '$CRON_NAME' still present after delete — refusing to re-register Skill 35 (both would be armed = double-post)." >&2; exit 2; }
    if ! bash "$SKILL35_REGISTRAR"; then
        echo "FATAL [$PROG]: Skill 35 registrar failed — this box currently has NO weekly trigger. Re-run --rollback (or --apply to go forward)." >&2
        INVARIANT="FAIL"; write_receipt "FAILED_NEEDS_RERUN" "rollback: skill35 registrar failed at $(now_utc)"
        exit 2
    fi
    GW="$(gateway_list)"
    if [ "$(count_in "$LEGACY_GATEWAY_NAME" "$GW")" = "1" ] && [ "$(count_in "$CRON_NAME" "$GW")" = "0" ]; then
        INVARIANT="PASS"; write_receipt "ROLLED_BACK" "rolled back to Skill 35 at $(now_utc)"
        echo "  OK: rolled back — exactly one '$LEGACY_GATEWAY_NAME', zero '$CRON_NAME'. Receipt updated."
        exit 0
    fi
    INVARIANT="FAIL"; write_receipt "FAILED_NEEDS_RERUN" "rollback: post-assert failed at $(now_utc)"
    echo "FATAL [$PROG]: rollback post-assert failed — inspect 'openclaw cron list'." >&2
    exit 2
fi

# ── --apply ──────────────────────────────────────────────────────────────────
echo "=== [$PROG] APPLY: migrating this box from Skill 35 to Skill 57 ==="

# STEP 0 — fire-window guard (delegated logic kept identical to the registrar)
_u="${SMIB_TEST_NOW_U:-$(date +%u)}"; _hm="${SMIB_TEST_NOW_HM:-$(date +%H%M)}"
_hm="${_hm#0}"; _hm="${_hm:-0}"
if [ "$_u" = "6" ] && [ "$_hm" -ge 745 ] && [ "$_hm" -le 815 ] && [ "$FORCE_WINDOW" -eq 0 ]; then
    echo "REFUSED [$PROG]: inside the Saturday 07:45-08:15 fire window — migrating now could drop or double this week's fire. Re-run outside the window (or --force-window)." >&2
    exit 9
fi

# STEP 1 — CLIENT-CONFIG GATE (fail-closed; nothing has been touched yet)
if [ ! -f "$CONFIG" ]; then
    echo "SKIPPED [$PROG]: client config not found at $CONFIG. This box is NOT migrated; the live Skill-35 cron stays authoritative. Provision the client's own config, then re-run." >&2
    exit 8
fi
if ! CONFIG="$CONFIG" SCRIPTS_DIR="$SELF_DIR" python3 - <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["SCRIPTS_DIR"])
import preflight_gate  # ONE source of truth for required fields + secrets-SET
try:
    cfg = json.load(open(os.environ["CONFIG"]))
except Exception as exc:
    print("  GATE FAIL [AF-SM-PREFLIGHT-CONFIG] cannot read/parse config JSON: %s" % exc)
    sys.exit(1)
fails = preflight_gate.check_required_fields(cfg)
for code, msg in fails:
    print("  GATE FAIL [%s] %s" % (code, msg))   # field NAMES only, never values
status = cfg.get("status")
if status != "Paid":
    print("  GATE NOTE: client status is %r (preflight will block runs until it is 'Paid'; the cron flip itself proceeds)" % status)
sys.exit(1 if fails else 0)
PY
then
    echo "SKIPPED [$PROG]: client-config gate failed (field names above; values never printed). This box is NOT migrated; the live Skill-35 cron stays authoritative. Fix the config, then re-run." >&2
    exit 8
fi
echo "  OK: client-config gate passed"
CONFIG_SHA="$( (shasum -a 256 "$CONFIG" 2>/dev/null || sha256sum "$CONFIG" 2>/dev/null) | awk '{print $1}' )"

# STEP 2 — SNAPSHOT (cron stores + the 35 marker + config sha; NEVER the config
# itself — no secret value is ever duplicated by this script)
BACKUP_DIR="$STATE_DIR/migration-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR" 2>/dev/null || true
gateway_list > "$BACKUP_DIR/gateway-cron-list.txt" 2>/dev/null || true
(crontab -l 2>/dev/null || true) > "$BACKUP_DIR/crontab.txt"
[ -f "$LEGACY_MARKER_JSON" ] && cp "$LEGACY_MARKER_JSON" "$BACKUP_DIR/skill35-weekly-theme-last-run.json" 2>/dev/null || true
printf '%s  %s\n' "${CONFIG_SHA:-unknown}" "$CONFIG" > "$BACKUP_DIR/client-config.sha256"
echo "  OK: snapshot -> $BACKUP_DIR"

# STEP 3 — CARRY STATE (before any cron change; each item check-then-act)
CARRIED_WEEKISO="" THEME_CARRIED="no" SHEET_CARRIED="no"
mkdir -p "$STATE_DIR" 2>/dev/null || true
if [ -f "$LEGACY_MARKER_JSON" ]; then
    if [ ! -f "$MARKER_JSON" ]; then
        cp "$LEGACY_MARKER_JSON" "$MARKER_JSON" && echo "  OK: carried the Skill-35 week marker (same-week double-run prevented)"
    else
        echo "  OK: Skill-57 week marker already present (carry is check-then-act)"
    fi
    CARRIED_WEEKISO="$(python3 -c "import json;print(json.load(open('$MARKER_JSON')).get('weekISO',''))" 2>/dev/null || echo '')"
else
    echo "  OK: no Skill-35 week marker on this box (nothing to carry; first fire is a fresh week)"
fi
# themeOfWeek + plannerSheetId -> client config (adopt-existing, never overwrite)
_carry_out="$(CONFIG="$CONFIG" LEGACY_MARKER="$LEGACY_MARKER_JSON" SHEET_ID="$SHEET_ID" python3 - <<'PY'
import json, os
cfg_path = os.environ["CONFIG"]
cfg = json.load(open(cfg_path))
changed = False
theme_carried = sheet_carried = "no"
try:
    marker = json.load(open(os.environ["LEGACY_MARKER"]))
except Exception:
    marker = {}
theme = (marker.get("theme") or "").strip()
if theme and not (cfg.get("themeOfWeek") or "").strip():
    cfg["themeOfWeek"] = theme
    theme_carried = "yes"; changed = True
sheet = (os.environ.get("SHEET_ID") or "").strip()
if sheet and not (cfg.get("plannerSheetId") or "").strip():
    cfg["plannerSheetId"] = sheet   # adopt-existing, never duplicate (merge plan 5.2)
    sheet_carried = "yes"; changed = True
if changed:
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
print("%s %s" % (theme_carried, sheet_carried))
PY
)" || _carry_out="no no"
THEME_CARRIED="${_carry_out%% *}"; SHEET_CARRIED="${_carry_out##* }"
echo "  OK: state re-point — weekISO='${CARRIED_WEEKISO:-none}', themeOfWeek carried=$THEME_CARRIED, plannerSheetId carried=$SHEET_CARRIED"
[ "$SHEET_CARRIED" = "no" ] && echo "  NOTE: plannerSheetId not carried — the planner module ADOPTS the existing sheet (or creates one) on the first plan run; pass --sheet-id to pin it explicitly."

# STEP 4 — FLIP: retire-35-then-register-57, atomically ordered, via the ONE
# registrar (it retires the gateway legacy, sweeps the crontab, dedups, and
# self-asserts; its config gate re-runs harmlessly).
FLIP_ARGS=(--apply --config "$CONFIG" --agent "$AGENT_ID")
[ "$FORCE_WINDOW" -eq 1 ] && FLIP_ARGS+=(--force-window)
if ! bash "$REGISTRAR" "${FLIP_ARGS[@]}"; then
    rc=$?
    INVARIANT="FAIL"
    write_receipt "FAILED_NEEDS_RERUN" "registrar exited $rc at $(now_utc) — if the legacy cron was already retired this box has NO weekly trigger until a re-run succeeds"
    echo "FATAL [$PROG]: registrar failed (exit $rc). RE-RUN this migration (idempotent) until it exits 0 — the receipt is marked FAILED_NEEDS_RERUN." >&2
    exit 2
fi

# STEP 5 — cross-store QC assert (independent re-check, not the registrar's own claim)
if bash "$REGISTRAR" --check; then
    INVARIANT="PASS"
else
    INVARIANT="FAIL"
    write_receipt "FAILED_NEEDS_RERUN" "post-flip invariant check failed at $(now_utc)"
    echo "FATAL [$PROG]: post-flip invariant check failed — re-run this migration." >&2
    exit 2
fi

# STEP 6 — missed-fire note (only possible when migrating on a Saturday after
# 08:00 with no run recorded for the current week)
NOTES="migrated at $(now_utc)"
cur_week="$(date +%G-W%V)"
if [ "$_u" = "6" ] && [ "$_hm" -gt 815 ] && [ "$CARRIED_WEEKISO" != "$cur_week" ]; then
    NOTES="$NOTES|WARN: migrated on Saturday after the 08:00 fire with no run recorded for $cur_week — trigger this week manually (owner theme question + --mode week) if the client expects it"
    echo "  WARN: this Saturday's fire predates the migration and no $cur_week run is recorded — trigger the week manually if expected."
fi

write_receipt "MIGRATED" "$NOTES"
echo "  DONE: box migrated 35 -> 57. Receipt: $RECEIPT"
echo "  Skill 35 files/state were NOT deleted (rollback stays possible via --rollback; per-client archive of 35 happens only after the independent live parity verify)."
exit 0
