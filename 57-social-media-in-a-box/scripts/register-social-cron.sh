#!/usr/bin/env bash
# 57-social-media-in-a-box/scripts/register-social-cron.sh
#
# PORTED weekly-theme cron registrar (merge plan §5.1) — v2, GATEWAY-STORE.
# Registers exactly ONE weekly-theme cron that fires 57's entry, retires the
# legacy Skill-35 cron, and QC-asserts exactly one. Idempotent, dedup,
# furnace-safe, persistent marker, CLIENT-CONFIG-GATED, silent (registers a
# trigger; never posts, never probes a live endpoint, never messages anyone).
# =============================================================================
#   cron name  : social-media-weekly-theme    (renamed from skill35-weekly-theme)
#   schedule   : 0 8 * * 6                     (Saturday 08:00, same as 35)
#   store      : the OpenClaw GATEWAY cron store (`openclaw cron add`) — the
#                SAME store Skill 35's registrar used. NOT the system crontab:
#                fleet VPS boxes run in Docker containers with NO cron daemon,
#                so a crontab line would never fire there, and — the double-post
#                hole this v2 closes — the live skill35-weekly-theme cron LIVES
#                in the gateway store, so only a gateway-store sweep can retire
#                it. (The v1 of this script swept only the crontab: applying it
#                left Skill 35's real cron armed → both engines fire Saturday
#                08:00 → DOUBLE-POSTING to the client's connected accounts.)
#   retires    : gateway store: skill35-weekly-theme (any entry, by name/id)
#                system crontab: any line matching skill35-weekly-theme /
#                weekly-batch / oc-skill35, PLUS any stale `# oc-skill57` line
#                installed by v1 of this script (self-heal)
#   carries    : Skill 35's persistent same-week idempotency marker
#                (~/.openclaw/data/skill35/weekly-theme-last-run.json →
#                 ~/.openclaw/data/skill57/weekly-theme-last-run.json), so the
#                first 57 fire after a migration cannot re-run a week Skill 35
#                already ran (the transition-week double-post).
#
# CLIENT-CONFIG GATE (fail-closed): --apply refuses (exit 8, NOTHING changed)
# unless the client config JSON exists and passes the SAME required-fields +
# secrets-SET check the preflight gate enforces (imported from
# preflight_gate.py — one source of truth, no drift). Field NAMES only are
# printed on failure, never values. A box without the client's own GHL /
# OpenRouter / Kie / Gemini config is cleanly SKIPPED, never half-migrated.
#   config resolution: --config PATH > $SMIB_CLIENT_CONFIG >
#                      <openclaw-dir>/data/skill57/client-config.json
#   (<openclaw-dir> = $HOME/.openclaw, else /data/.openclaw — VPS pattern)
#
# DE-DUP LAW (merge plan §5): two of anything double-fires or splits state, so
# this guarantees EXACTLY ONE weekly-theme cron per box, across BOTH stores.
# Re-running is a no-op (check-then-act at every step).
#
# FIRE-WINDOW GUARD: --apply refuses (exit 9) during Saturday 07:45–08:15
# box-local time unless --force-window is given, so the retire→register swap
# can never straddle the weekly fire instant and drop (or double) a fire.
#
# SAFE BY DEFAULT: prints the plan (dry-run) unless --apply is given. --check
# asserts the invariant (exactly one weekly-theme cron in the gateway store,
# zero legacy in either store) and exits non-zero if not.
#
# For a box migrating FROM a live Skill 35, prefer scripts/migrate-35-to-57.sh
# (it wraps this registrar and ADDS the state re-point, a pre-change snapshot,
# a machine-readable receipt, and --rollback).
#
# EXIT: 0 ok / 2 invariant violated or store write failed / 3 usage /
#       6 deps missing (openclaw CLI or python3) / 8 config gate: box skipped /
#       9 fire-window guard.
# USAGE:
#   bash register-social-cron.sh [--apply] [--check] [--config PATH]
#                                [--agent ID] [--force-window] [--marker-dir DIR]
# TEST SEAMS (never needed in production): $OPENCLAW_BIN overrides the CLI
# binary; $SMIB_TEST_NOW_U / $SMIB_TEST_NOW_HM override the guard clock.
# =============================================================================
set -uo pipefail
PROG="register-social-cron.sh"

CRON_NAME="social-media-weekly-theme"
SCHEDULE="0 8 * * 6"
LEGACY_GATEWAY_NAME="skill35-weekly-theme"
LEGACY_CRONTAB_RE='skill35-weekly-theme|weekly-batch|oc-skill35|# oc-skill57'
SESSION_TARGET="main"   # isolated + channel-deliver is rejected by the gateway
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRY="$SELF_DIR/social-media-entry.sh"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

# openclaw dir resolution (same HOME-else-/data pattern as Skill 35's scripts)
HOME_DIR="${HOME:-/data}"
OPENCLAW_DIR="$HOME_DIR/.openclaw"
[ ! -d "$OPENCLAW_DIR" ] && [ -d "/data/.openclaw" ] && OPENCLAW_DIR="/data/.openclaw"

STATE_DIR="$OPENCLAW_DIR/data/skill57"
MARKER_JSON="$STATE_DIR/weekly-theme-last-run.json"
LEGACY_MARKER_JSON="$OPENCLAW_DIR/data/skill35/weekly-theme-last-run.json"

APPLY=0 CHECK=0 FORCE_WINDOW=0
CONFIG="${SMIB_CLIENT_CONFIG:-$STATE_DIR/client-config.json}"
AGENT_ID="${SKILL57_CRON_AGENT:-main}"
MARKER_DIR="$STATE_DIR"
while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1; shift ;;
        --check) CHECK=1; shift ;;
        --config) CONFIG="${2:-}"; shift 2 ;;
        --agent) AGENT_ID="${2:-}"; shift 2 ;;
        --force-window) FORCE_WINDOW=1; shift ;;
        --marker-dir) MARKER_DIR="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,69p' "$0"; exit 3 ;;
        *) echo "FATAL [$PROG]: unknown arg $1" >&2; exit 3 ;;
    esac
done

# ── helpers ──────────────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }

gateway_list() { "$OPENCLAW_BIN" cron list 2>/dev/null || true; }

count_in() {  # count_in <needle> <text>
    local n
    n="$(printf '%s\n' "$2" | grep -c "$1" 2>/dev/null || true)"
    n="${n//[^0-9]/}"; echo "${n:-0}"
}

crontab_text() {
    have crontab || { echo ""; return 0; }
    crontab -l 2>/dev/null || true
}

count_crontab_legacy() {
    local n
    n="$(crontab_text | grep -Ec "$LEGACY_CRONTAB_RE" 2>/dev/null || true)"
    n="${n//[^0-9]/}"; echo "${n:-0}"
}

# ── FIRE-WINDOW GUARD (shared by --apply here and by migrate-35-to-57.sh) ────
in_fire_window() {
    local u hm
    u="${SMIB_TEST_NOW_U:-$(date +%u)}"        # 6 = Saturday
    hm="${SMIB_TEST_NOW_HM:-$(date +%H%M)}"
    hm="${hm#0}"; hm="${hm:-0}"                 # strip leading zero for arithmetic
    [ "$u" = "6" ] || return 1
    [ "$hm" -ge 745 ] && [ "$hm" -le 815 ]
}

# ── --check: cross-store invariant ───────────────────────────────────────────
if [ "$CHECK" -eq 1 ]; then
    have "$OPENCLAW_BIN" || { echo "FATAL [$PROG]: openclaw CLI not on PATH — cannot check the gateway cron store." >&2; exit 6; }
    GW="$(gateway_list)"
    n="$(count_in "$CRON_NAME" "$GW")"
    legacy_gw="$(count_in "$LEGACY_GATEWAY_NAME" "$GW")"
    legacy_ct="$(count_crontab_legacy)"
    echo "=== [$PROG] QC: gateway weekly-theme=$n (want 1), gateway legacy-35=$legacy_gw (want 0), crontab legacy/stale lines=$legacy_ct (want 0) ==="
    if [ "$n" = "1" ] && [ "$legacy_gw" = "0" ] && [ "$legacy_ct" = "0" ]; then
        echo "  OK: exactly one weekly-theme cron (gateway store); no legacy Skill-35 trigger in either store"
        exit 0
    fi
    echo "  INVARIANT VIOLATED (want exactly one gateway weekly-theme cron and zero legacy anywhere). Re-run with --apply to heal." >&2
    exit 2
fi

# ── The cron MESSAGE the gateway job delivers to the agent on fire ───────────
# Mirrors Skill 35's proven message shape (idempotency marker first, owner
# theme question, then the run, then the marker write) but drives 57's ONE
# sanctioned entry. sessionTarget=main + --light-context, cheap-model guidance:
# same furnace-safe pattern as Skill 35 and Skill 38.
CRON_MESSAGE="Skill 57 weekly theme trigger (Saturday 8 AM). \
Before doing anything, check the idempotency marker: ${MARKER_JSON}. \
If it exists and its 'weekISO' field matches the current ISO week \
(date +%G-W%V), skip gracefully — this week's social run already happened \
(this also prevents a double-run in the week a box migrates from Skill 35). \
Otherwise: \
(1) Ask the owner: 'What is the content theme for this week's social media content? \
If you do not reply by noon I will use the evergreen theme.' \
Wait up to 1 hour for a reply. If no reply by 12:00 PM ask once more. \
If no reply by 6:00 PM, use the evergreen theme. \
(2) After the theme is confirmed or defaulted, run the weekly engine through the ONE \
sanctioned entry: create a fresh run directory and run \
bash ${ENTRY} --run-dir <run-dir> --mode week \
(client config: ${CONFIG}). \
(3) Write ${MARKER_JSON} with \
{\"weekISO\": \"<current ISO week from date +%G-W%V>\", \"theme\": \"<chosen theme>\", \"firedAt\": \"<UTC now>\"} \
so re-fires this week are skipped. \
Model guidance: use the cheapest available CLIENT model (flash tier or a free \
OpenRouter fallback) for the weekly question — never a metered pro model, and \
client providers ONLY."

# ── Dry-run (default): print the plan, change NOTHING ────────────────────────
echo "=== [$PROG] weekly-theme cron plan (gateway store) ==="
echo "  cron name : $CRON_NAME"
echo "  schedule  : $SCHEDULE  (Saturday 08:00)"
echo "  store     : OpenClaw gateway cron store (openclaw cron add; sessionTarget=$SESSION_TARGET, agent=$AGENT_ID, light-context)"
echo "  fires     : agent message -> marker check -> owner theme question -> bash $ENTRY --mode week"
echo "  retires   : gateway '$LEGACY_GATEWAY_NAME' + crontab lines matching /$LEGACY_CRONTAB_RE/"
echo "  carries   : $LEGACY_MARKER_JSON -> $MARKER_JSON (same-week de-dup)"
echo "  config    : $CONFIG (fail-closed gate on --apply)"

if [ "$APPLY" -eq 0 ]; then
    if have "$OPENCLAW_BIN"; then
        GW="$(gateway_list)"
        echo "  current   : gateway weekly-theme=$(count_in "$CRON_NAME" "$GW"), gateway legacy-35=$(count_in "$LEGACY_GATEWAY_NAME" "$GW"), crontab legacy/stale=$(count_crontab_legacy)"
    else
        echo "  current   : (openclaw CLI not on PATH — gateway state unknown in this dry-run)"
    fi
    echo "  (dry-run — re-run with --apply to install. Nothing changed.)"
    exit 0
fi

# ── --apply ──────────────────────────────────────────────────────────────────
# GATE A: deps
have "$OPENCLAW_BIN" || { echo "FATAL [$PROG]: openclaw CLI not on PATH — cannot register in the gateway cron store. Do NOT fall back to the system crontab (no cron daemon on fleet VPS containers)." >&2; exit 6; }
have python3 || { echo "FATAL [$PROG]: python3 not found — cannot run the client-config gate." >&2; exit 6; }

# GATE B: fire window
if in_fire_window && [ "$FORCE_WINDOW" -eq 0 ]; then
    echo "REFUSED [$PROG]: inside the Saturday 07:45-08:15 fire window — a cron swap now could drop or double this week's fire. Re-run outside the window (or --force-window)." >&2
    exit 9
fi

# GATE C: CLIENT-CONFIG GATE (fail-closed; field names only, never values)
if [ ! -f "$CONFIG" ]; then
    echo "SKIPPED [$PROG]: client config not found at $CONFIG — this box lacks the client's own GHL/OpenRouter/Kie/Gemini config. NOTHING changed (any live Skill-35 cron stays authoritative). Provision the config, then re-run." >&2
    exit 8
fi
if ! CONFIG="$CONFIG" SCRIPTS_DIR="$SELF_DIR/scripts" python3 - <<'PY'
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
sys.exit(1 if fails else 0)
PY
then
    echo "SKIPPED [$PROG]: client-config gate failed (see field names above; values are never printed). NOTHING changed (any live Skill-35 cron stays authoritative). Fix the config, then re-run." >&2
    exit 8
fi
echo "  OK: client-config gate passed ($CONFIG)"

# STEP 1 — carry Skill 35's same-week marker (check-then-act; transition-week de-dup)
mkdir -p "$MARKER_DIR" "$STATE_DIR" 2>/dev/null || true
if [ -f "$LEGACY_MARKER_JSON" ] && [ ! -f "$MARKER_JSON" ]; then
    cp "$LEGACY_MARKER_JSON" "$MARKER_JSON" 2>/dev/null \
        && echo "  OK: carried Skill-35 week marker -> $MARKER_JSON (same-week double-run prevented)" \
        || echo "  WARN: could not carry $LEGACY_MARKER_JSON (continuing; first fire may re-ask the theme)" >&2
fi

# STEP 2 — sweep legacy/stale lines from the system crontab (both v1-installed
# `# oc-skill57` lines and any hand-added skill35/weekly-batch lines)
if have crontab; then
    CT="$(crontab_text)"
    if printf '%s\n' "$CT" | grep -Eq "$LEGACY_CRONTAB_RE"; then
        NEW_CT="$(printf '%s\n' "$CT" | grep -Ev "$LEGACY_CRONTAB_RE" | grep -v '^[[:space:]]*$' || true)"
        if printf '%s\n' "$NEW_CT" | crontab -; then
            echo "  OK: swept legacy/stale weekly-social lines from the system crontab"
        else
            echo "FATAL [$PROG]: crontab write failed while sweeping legacy lines" >&2; exit 2
        fi
    else
        echo "  OK: system crontab already clean of legacy/stale weekly-social lines"
    fi
else
    echo "  OK: no crontab binary on this box (VPS container) — nothing to sweep there"
fi

# STEP 3 — RETIRE the legacy Skill-35 gateway cron, and CONFIRM it is gone
# BEFORE registering 57's (retire-then-register: there is never a moment with
# both weekly-theme triggers armed).
GW="$(gateway_list)"
legacy_n="$(count_in "$LEGACY_GATEWAY_NAME" "$GW")"
if [ "$legacy_n" != "0" ]; then
    echo "  retiring $legacy_n legacy '$LEGACY_GATEWAY_NAME' gateway cron(s)..."
    if ! "$OPENCLAW_BIN" cron delete --name "$LEGACY_GATEWAY_NAME" 2>/dev/null; then
        _ids="$(printf '%s\n' "$GW" | grep "$LEGACY_GATEWAY_NAME" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' || true)"
        if [ -n "$_ids" ]; then
            while IFS= read -r _id; do
                [ -z "$_id" ] && continue
                "$OPENCLAW_BIN" cron delete --id "$_id" 2>/dev/null || echo "  WARN: could not delete cron id $_id" >&2
            done <<EOF
$_ids
EOF
        fi
    fi
    legacy_after="$(count_in "$LEGACY_GATEWAY_NAME" "$(gateway_list)")"
    if [ "$legacy_after" != "0" ]; then
        echo "FATAL [$PROG]: legacy '$LEGACY_GATEWAY_NAME' still present after delete ($legacy_after) — REFUSING to register '$CRON_NAME' (that would arm BOTH weekly triggers = double-post). Fix the gateway store and re-run." >&2
        exit 2
    fi
    echo "  OK: legacy '$LEGACY_GATEWAY_NAME' retired and confirmed gone"
else
    echo "  OK: no legacy '$LEGACY_GATEWAY_NAME' in the gateway store"
fi

# STEP 4 — dedup + register 57's cron (idempotent: one healthy entry = no-op)
GW="$(gateway_list)"
own_n="$(count_in "$CRON_NAME" "$GW")"
if [ "$own_n" = "1" ]; then
    _is_err="$(printf '%s\n' "$GW" | grep "$CRON_NAME" | grep -c "error" 2>/dev/null || true)"; _is_err="${_is_err//[^0-9]/}"; _is_err="${_is_err:-0}"
    if [ "$_is_err" = "0" ]; then
        echo "  OK: '$CRON_NAME' already registered with a healthy entry — nothing to do."
        own_n="KEEP"
    fi
fi
if [ "$own_n" != "KEEP" ]; then
    if [ "$own_n" != "0" ]; then
        echo "  removing $own_n stale/duplicate '$CRON_NAME' entr(y/ies) before clean registration..."
        "$OPENCLAW_BIN" cron delete --name "$CRON_NAME" 2>/dev/null || true
    fi
    echo "  registering '$CRON_NAME' ($SCHEDULE, sessionTarget=$SESSION_TARGET, agent=$AGENT_ID)..."
    if ! "$OPENCLAW_BIN" cron add \
        --name "$CRON_NAME" \
        --cron "$SCHEDULE" \
        --agent "$AGENT_ID" \
        --session-target "$SESSION_TARGET" \
        --message "$CRON_MESSAGE" \
        --light-context; then
        echo "FATAL [$PROG]: 'openclaw cron add' failed — '$CRON_NAME' NOT registered. If a legacy Skill-35 cron was just retired, this box currently has NO weekly trigger: RE-RUN this script (idempotent) until it exits 0." >&2
        exit 2
    fi
fi

# STEP 5 — persistent marker + cross-store QC self-assert
date -u +"%Y-%m-%dT%H:%M:%SZ registered ${CRON_NAME}" > "$MARKER_DIR/${CRON_NAME}.marker" 2>/dev/null || true

GW="$(gateway_list)"
n="$(count_in "$CRON_NAME" "$GW")"
legacy_gw="$(count_in "$LEGACY_GATEWAY_NAME" "$GW")"
legacy_ct="$(count_crontab_legacy)"
if [ "$n" = "1" ] && [ "$legacy_gw" = "0" ] && [ "$legacy_ct" = "0" ]; then
    echo "  APPLIED + QC OK: exactly one '$CRON_NAME' gateway cron; zero legacy in either store."
    exit 0
fi
echo "  QC FAIL: gateway weekly-theme=$n (want 1), gateway legacy-35=$legacy_gw (want 0), crontab legacy/stale=$legacy_ct (want 0)" >&2
exit 2
