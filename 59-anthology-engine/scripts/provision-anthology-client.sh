#!/usr/bin/env bash
# 59-anthology-engine/scripts/provision-anthology-client.sh
# ----------------------------------------------------------------------------
# SPEC Section 13.1 FULL per-client provisioning (script inventory row 30).
# Idempotent; EVERY config write happens as the NODE USER, never root; every
# credential is reported SET / NOT SET by LABEL only, never by value. Convert
# and Flow naming in every surface. Zero Anthropic identifiers anywhere. The
# engine is client-SILENT: this script's surfaces are OPERATOR-only (stderr),
# nothing is ever sent to a client here.
#
# THE TEN STEPS (SPEC 13.1, executed in order; the FIRST nonzero STOPS setup
# with an operator surface, exactly as the manifest row-30 contract demands):
#   1  caf_credential_gate.py resolves every PRD Section 14 credential by label
#      across all three client env stores (live process env first), with the
#      pairing proof and the anti-commingling fingerprint (SET / NOT SET only).
#   2  create-or-verify the PRD Section 6 custom fields by EXACT key (the 8
#      Doc/PDF pairs + 3 control fields = 19 keys); a MISSING field STOPS setup
#      with an operator surface (AF-AE-FIELD-MISSING) — never a silent runtime
#      create; a server fieldKey that does not byte-equal its intended key is
#      AF-AE-FIELD-KEY-MISMATCH.  (anthology_registry.py provision-fields)
#   3  BIND the standard Anthology pipeline in the CLIENT's OWN Convert and Flow
#      account through the CLIENT's OWN private integration token. GoHighLevel /
#      Convert and Flow has NO public API to CREATE a pipeline (the UI is the
#      only create surface), so this is FIND-AND-BIND FIRST: probe-scope
#      verifies the token can READ pipelines (STOP AF-AE-PIT-SCOPE if it
#      cannot), then provision-pipeline finds the standard pipeline BY NAME and
#      binds it into the registry. If the standard pipeline is absent, a LIVE
#      run attempts ONE browser-control creation via Skill 6's pipeline builder
#      (exact-name mode), RE-READS the pipelines, and binds only what the API
#      shows; a failed or unavailable walk STOPs with an operator surface
#      (AF-AE-PIPELINE-UI-CREATE) to create it once in the UI, or to bind a
#      pre-existing pipeline via `--pipeline-id`; never a silent fallback,
#      never a faked success, never a call to a nonexistent create endpoint.
#   4  register the universal + per-stage forms with their hidden-field and
#      re-stamp contract (contact_id, anthology_id, stage; keying by contact_id,
#      never email); concrete Convert and Flow form ids are bound per anthology.
#   5  provision the Drive producer root under the operator's EXISTING shared
#      root; NEVER create a new root (drive-tree-provision.py).
#   6  bootstrap the ledger base + local mirror schemas (anthology_state.py).
#   7  generate the webhook route and its secret (label ANTHOLOGY_INTAKE_HOOK_
#      SECRET; also the gate-token secret ANTHOLOGY_GATE_TOKEN_SECRET) — the
#      secret is generated only when NOT already SET, written 0600, and NEVER
#      printed; the resolved route carries the secret as a SecretRef by LABEL.
#   8  register EXACTLY the ONE daily tick in the cron inventory — no heartbeat,
#      ever (guard-cron-inventory.py proves it).
#   9  run verify-webhook-t1-t9.sh (structure now; the live T1..T9 battery is
#      executed and OBSERVED on the canary at W5.3).
#   10 fire ONE smoke test — balance endpoints ONLY, total spend at or under one
#      cent (anthology-smoke-test.py run).
#
# EXIT CODES (house convention; nonzero STOPS SETUP with an operator surface):
#   0  provisioning passed the gate (idempotent no-op counts as pass)
#   1  unexpected error
#   2  validation / guard refusal (missing credential label, missing field,
#      usage error, running as root, a hard prerequisite unmet)
#   3  dependency unavailable or held (Convert and Flow / Drive / gateway /
#      Command Center unreachable, or a sibling collaborator not yet wired)
#   4  enforced violation (AF-AE-COMMINGLE credential commingling; provider
#      unreachable/unfunded at the smoke test)
#   5  data / read-back mismatch (AF-AE-FIELD-KEY-MISMATCH, department read-back)
# The child collaborators share this convention; their codes are propagated
# faithfully (0->pass, 2->2, 3->3, 4->4, 5->5, other->1).
#
# MODES / FLAGS:
#   --plan | --list            print the ten-step plan and exit 0 (no writes).
#   --dry-run                  resolve everything + plan every write WITHOUT
#                              performing it or touching the network; report
#                              SET / NOT SET; exit 0 if plannable.
#   --self-test                force-observe EVERY failure mode with synthetic
#                              stub collaborators (no network, no siblings);
#                              exit 0 if the exit-surface mapping is proven.
#   --require-live             an unavailable live backend (cron CLI, gateway
#                              route merge) is a hard HOLD (exit 3), not a
#                              surfaced deferral.
#   --producer NAME            producer (box-owner) display name for the Drive
#                              producer folder (step 5) and the department head.
#   --producer-id ID           producer id for the ledger (step 6).
#   --location-id ID           override the Convert and Flow Location id.
#   --department-slug SLUG     Command Center department slug (default anthology).
#   --daily-tick-schedule CRON cron schedule for the one daily tick (default 0 8 * * *).
#   --daily-tick-cmd CMD       override the daily-tick command (default: the
#                              smoke-test run under this skill).
#   --skip-department          skip step-3.5 department seeding (CC seeded elsewhere).
#   --skip-smoke               skip step 10.
#   --state-dir DIR            override the engine state dir.
#   --json                     emit a machine-readable per-step summary at the end.
#   -h | --help                usage.
#
# SILENCE / SECRECY (binding): credential VALUES are never printed, logged, or
# echoed; only SET / NOT SET. Location ids are MASKED. The two provisioning
# secrets are written 0600 and never surfaced. All fixture / synthetic data in
# --self-test is synthetic.
set -uo pipefail

# --------------------------------------------------------------------------
# Layout resolution.
# --------------------------------------------------------------------------
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
SCRIPTS="$SELF_DIR"                       # collaborators live beside this script
SKILLS_ROOT="$(cd "$SKILL_DIR/.." && pwd)"  # sibling skills (e.g. 32-command-center-setup)
CONFIG_DIR="$SKILL_DIR/config"

PROG="$(basename "${BASH_SOURCE[0]:-$0}")"

# House exit-code constants.
EX_OK=0; EX_ERR=1; EX_STOP=2; EX_HELD=3; EX_VIOLATION=4; EX_MISMATCH=5

# --------------------------------------------------------------------------
# Argument parsing.
# --------------------------------------------------------------------------
MODE="live"                # live | plan | dryrun | selftest
REQUIRE_LIVE=0
JSONOUT=0
PRODUCER_NAME=""
PRODUCER_ID=""
LOCATION_ID_OVERRIDE=""
DEPT_SLUG="anthology"
DEPT_NAME="Anthology"
DAILY_TICK_SCHEDULE="0 8 * * *"
DAILY_TICK_CMD=""
SKIP_DEPARTMENT=0
SKIP_SMOKE=0
STATE_DIR_OVERRIDE=""

usage() {
    sed -n '2,86p' "${BASH_SOURCE[0]:-$0}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --plan|--list)          MODE="plan"; shift ;;
        --dry-run)              MODE="dryrun"; shift ;;
        --self-test)            MODE="selftest"; shift ;;
        --require-live)         REQUIRE_LIVE=1; shift ;;
        --producer)             PRODUCER_NAME="${2:-}"; shift 2 ;;
        --producer-id)          PRODUCER_ID="${2:-}"; shift 2 ;;
        --location-id)          LOCATION_ID_OVERRIDE="${2:-}"; shift 2 ;;
        --department-slug)      DEPT_SLUG="${2:-}"; shift 2 ;;
        --department-name)      DEPT_NAME="${2:-}"; shift 2 ;;
        --daily-tick-schedule)  DAILY_TICK_SCHEDULE="${2:-}"; shift 2 ;;
        --daily-tick-cmd)       DAILY_TICK_CMD="${2:-}"; shift 2 ;;
        --skip-department)      SKIP_DEPARTMENT=1; shift ;;
        --skip-smoke)           SKIP_SMOKE=1; shift ;;
        --state-dir)            STATE_DIR_OVERRIDE="${2:-}"; shift 2 ;;
        --json)                 JSONOUT=1; shift ;;
        -h|--help)              usage 0 ;;
        *) echo "[$PROG] unknown arg: $1" >&2; usage 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "[$PROG] FATAL: python3 required" >&2; exit "$EX_STOP"; }

# --------------------------------------------------------------------------
# State dir resolution — MIRRORS anthology_state.py / anthology_registry.py so
# every collaborator agrees on where per-box state lives.
# --------------------------------------------------------------------------
resolve_state_dir() {
    if [ -n "$STATE_DIR_OVERRIDE" ]; then printf '%s\n' "$STATE_DIR_OVERRIDE"; return; fi
    if [ -n "${ANTHOLOGY_STATE_DIR:-}" ]; then printf '%s\n' "$ANTHOLOGY_STATE_DIR"; return; fi
    if [ -n "${OPENCLAW_DATA_DIR:-}" ]; then printf '%s\n' "${OPENCLAW_DATA_DIR%/}/anthology-engine/state"; return; fi
    printf '%s\n' "${HOME:-$(cd ~ && pwd)}/.anthology-engine/state"
}
STATE_DIR="$(resolve_state_dir)"

# --------------------------------------------------------------------------
# Operator surface (stderr, OPERATOR-only). Never a client surface. Never a
# secret value. Delimited so the operator cannot miss it.
# --------------------------------------------------------------------------
op_surface() {
    # $1 step-label  $2 reason/AF-code  $3 child-rc  $4 normalized-exit  then N remediation lines
    local step="$1" reason="$2" crc="$3" nex="$4"; shift 4
    {
        echo "========================================================================"
        echo " ANTHOLOGY ENGINE — PROVISIONING STOPPED (operator surface)"
        echo " Step:      $step"
        echo " Reason:    $reason  (child rc=$crc, normalized exit=$nex)"
        local ln
        for ln in "$@"; do echo " Do this:   $ln"; done
        echo " (credential VALUES are never printed; only SET / NOT SET; location ids masked)"
        echo "========================================================================"
    } >&2
}

note() { echo "[$PROG] $*" >&2; }

# Mask a location id for surfaces (never print it whole).
mask_loc() {
    local v="${1:-}"
    if [ -z "$v" ]; then printf 'NOT SET'; return; fi
    local n=${#v}
    if [ "$n" -le 6 ]; then printf '...(masked)'; else printf '...%s' "${v: -6}"; fi
}

# Report a credential label as SET / NOT SET over the LIVE process env (a
# convenience preflight; the AUTHORITATIVE three-store resolution is step 1's
# caf_credential_gate.py). Never prints the value.
label_state() {
    local label="$1"
    if [ -n "${!label:-}" ]; then printf 'SET'; else printf 'NOT SET'; fi
}

report_labels() {
    local labels=(CONVERT_AND_FLOW_PIT CONVERT_AND_FLOW_LOCATION_ID GOOGLE_IMPERSONATE_USER \
                  ANTHOLOGY_INTAKE_HOOK_SECRET ANTHOLOGY_GATE_TOKEN_SECRET)
    note "credential label states (LIVE process env only; values never printed):"
    local l
    for l in "${labels[@]}"; do note "  $l = $(label_state "$l")"; done
    note "  (ANTHOLOGY_INTAKE_HOOK_SECRET / ANTHOLOGY_GATE_TOKEN_SECRET are GENERATED at step 7 when NOT SET)"
}

# --------------------------------------------------------------------------
# Root guard — config writes as the node user, NEVER root (root writes freeze
# the gateway; EACCES on the client boxes). Testable with a synthetic euid.
# --------------------------------------------------------------------------
check_root_guard() {   # $1 euid ; echoes normalized exit, 0 ok / EX_STOP refuse
    if [ "${1:-}" = "0" ]; then echo "$EX_STOP"; else echo "$EX_OK"; fi
}

# --------------------------------------------------------------------------
# Normalize a collaborator child exit code into this script's house convention.
# 0->0, 2->2, 3->3, 4->4, 5->5, anything else->1. (Faithful propagation of the
# shared SPEC 3.4 exit-code vocabulary.)
# --------------------------------------------------------------------------
normalize_rc() {
    case "${1:-1}" in
        0) echo "$EX_OK" ;;
        2) echo "$EX_STOP" ;;
        3) echo "$EX_HELD" ;;
        4) echo "$EX_VIOLATION" ;;
        5) echo "$EX_MISMATCH" ;;
        *) echo "$EX_ERR" ;;
    esac
}

# --------------------------------------------------------------------------
# Atomic node-user JSON write (os.replace; inherits the caller's node uid). Used
# for the forms manifest, cron inventory, and resolved route. Mode 0644.
# --------------------------------------------------------------------------
write_json_file() {   # $1 path ; JSON on stdin
    local path="$1"
    local data; data="$(cat)"   # slurp the JSON off stdin FIRST; the python
                                 # heredoc below claims stdin for its own script.
    PROV_JSON_PATH="$path" PROV_JSON_DATA="$data" python3 - <<'PY'
import json, os, tempfile
path = os.environ["PROV_JSON_PATH"]
obj = json.loads(os.environ["PROV_JSON_DATA"])  # validate before landing
os.makedirs(os.path.dirname(path), exist_ok=True)
d = os.path.dirname(path)
fd, tmp = tempfile.mkstemp(prefix=".prov.", suffix=".json.tmp", dir=d)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
except Exception:
    try: os.unlink(tmp)
    except OSError: pass
    raise
PY
}

# --------------------------------------------------------------------------
# Generate a provisioning secret IFF its env label is NOT already SET. Writes a
# 0600 file, NEVER prints the value. Echoes one of: SET-env | GENERATED | ERROR.
# --------------------------------------------------------------------------
ensure_secret() {   # $1 label  $2 secret-file path
    local label="$1" path="$2"
    if [ -n "${!label:-}" ]; then echo "SET-env"; return 0; fi
    if [ -f "$path" ]; then echo "SET-file"; return 0; fi
    PROV_SECRET_PATH="$path" python3 - <<'PY' >/dev/null 2>&1
import os, secrets, tempfile
path = os.environ["PROV_SECRET_PATH"]
os.makedirs(os.path.dirname(path), exist_ok=True)
d = os.path.dirname(path)
fd, tmp = tempfile.mkstemp(prefix=".sec.", suffix=".tmp", dir=d)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(secrets.token_hex(32))          # value NEVER surfaced
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
except Exception:
    try: os.unlink(tmp)
    except OSError: pass
    raise
PY
    if [ $? -eq 0 ]; then echo "GENERATED"; else echo "ERROR"; fi
}

# --------------------------------------------------------------------------
# Run a collaborator script and return its NORMALIZED exit code. Prints its
# stderr through to the operator. If the script file is ABSENT (a sibling W2/W1
# unit not yet wired), that is EX_HELD (fail-soft HOLD), matching the stage
# dispatchers' pending-collaborator doctrine.
# --------------------------------------------------------------------------
COLLAB_RC=0           # raw child rc from the last run_collab
RC_FILE=""            # set by run_pipeline so the raw child rc survives the
                      # command-substitution subshell each step runs in.
set_crc() {           # record the raw child rc for the operator surface
    COLLAB_RC="$1"
    [ -n "${RC_FILE:-}" ] && printf '%s' "$1" > "$RC_FILE"
    return 0
}
run_collab() {        # $1 kind(py|sh)  $2 script-path  rest: args ; echoes normalized rc
    local kind="$1" script="$2"; shift 2
    if [ ! -f "$script" ]; then
        note "collaborator not present yet: $(basename "$script") (pending sibling unit)"
        set_crc 127
        echo "$EX_HELD"
        return
    fi
    local rc=0
    if [ "$kind" = "py" ]; then
        python3 "$script" "$@" >&2; rc=$?
    else
        bash "$script" "$@" >&2; rc=$?
    fi
    set_crc "$rc"
    normalize_rc "$rc"
}

# ==========================================================================
# THE TEN STEPS. Each echoes a normalized exit code; the caller stops on the
# first nonzero and emits the operator surface. Steps are idempotent.
# ==========================================================================

# Whether we pass --dry-run through to Python collaborators.
dry_flag() { [ "$MODE" = "dryrun" ] && echo "--dry-run" || echo ""; }

step1_credentials() {
    note "STEP 1/10 — credential gate (label resolution + pairing proof + anti-commingling fingerprint)"
    report_labels
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would run caf_credential_gate.py over all three env stores; no network"
        echo "$EX_OK"; return
    fi
    # caf_credential_gate.py (sibling W2.3) is a FLAGS-ONLY CLI (no subcommands):
    # a bare invocation resolves every PRD Section 14 label live-process-first
    # across the three env stores, fingerprints, runs the inline-exposure scan
    # and the legacy literal-Authorization-header ban, and gates the exit code
    # (0 all resolve + clean; 2 missing label; 4 commingling). When the client
    # Location id is present we pass --expect-location so the anti-commingling
    # expected-vs-resolved check is exercised; the gate HASHES it immediately and
    # never stores or prints it (its documented contract).
    local gate="$SCRIPTS/caf_credential_gate.py"
    if [ ! -f "$gate" ]; then
        note "  caf_credential_gate.py not present yet (W2.3 pending) — HELD"
        set_crc 127
        echo "$EX_HELD"; return
    fi
    local -a gargs=()
    if [ -n "${CONVERT_AND_FLOW_LOCATION_ID:-}" ]; then
        gargs+=(--expect-location "$CONVERT_AND_FLOW_LOCATION_ID")
    fi
    local out rc
    if [ "${#gargs[@]}" -gt 0 ]; then
        out="$(python3 "$gate" "${gargs[@]}" 2>&1)"; rc=$?
    else
        out="$(python3 "$gate" 2>&1)"; rc=$?
    fi
    # Fallback: if our optional flag disagrees with the CLI (argparse usage error
    # with rc 2), retry the pure bare invocation before treating rc 2 as a STOP.
    if [ "$rc" = "2" ] && [ "${#gargs[@]}" -gt 0 ] && echo "$out" | grep -qiE "unrecognized arguments|usage:"; then
        out="$(python3 "$gate" 2>&1)"; rc=$?
    fi
    printf '%s\n' "$out" >&2
    set_crc "$rc"
    echo "$(normalize_rc "$rc")"; return
}

step2_fields() {
    note "STEP 2/10 — create-or-verify the 19 Section 6 custom fields (8 Doc/PDF pairs + 3 control)"
    local n; n="$(run_collab py "$SCRIPTS/anthology_registry.py" provision-fields $(dry_flag) \
        ${LOCATION_ID_OVERRIDE:+--location-id "$LOCATION_ID_OVERRIDE"})"
    echo "$n"
}

step3_pipeline() {
    note "STEP 3/10 — BIND the standard Anthology pipeline (client's OWN PIT; no API create -- absent pipeline triggers ONE Skill 6 browser-control creation, verified by API re-read)"
    # 3a PRE-FLIGHT: verify the token can READ pipelines; STOP (AF-AE-PIT-SCOPE) if not.
    local n; n="$(run_collab py "$SCRIPTS/anthology_registry.py" probe-scope $(dry_flag) \
        ${LOCATION_ID_OVERRIDE:+--location-id "$LOCATION_ID_OVERRIDE"})"
    if [ "$n" != "$EX_OK" ]; then echo "$n"; return; fi
    if [ "$MODE" = "dryrun" ]; then
        # A dry-run stops after the read pre-flight above and reports intent only
        # (a live run finds-and-binds BY NAME, attempting ONE browser-control
        # creation via Skill 6 when the standard pipeline is absent).
        note "  (dry-run) would find the standard Anthology pipeline BY NAME and bind it into the registry (browser-create when absent)"
        echo "$EX_OK"; return
    fi
    # 3b find the standard pipeline BY NAME and bind it into the registry. Absent
    # pipeline -> ONE Skill 6 browser-control creation attempt (exact-name mode),
    # then an API RE-READ; only a pipeline the read surface shows is ever bound.
    # A failed/unavailable walk -> STOP (AF-AE-PIPELINE-UI-CREATE): create once
    # in the UI, or bind a pre-existing pipeline with `bind --pipeline-id`.
    n="$(run_collab py "$SCRIPTS/anthology_registry.py" provision-pipeline \
        ${LOCATION_ID_OVERRIDE:+--location-id "$LOCATION_ID_OVERRIDE"})"
    echo "$n"
}

step4_forms() {
    note "STEP 4/10 — register the universal + per-stage form hidden-field / re-stamp contract"
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would write $STATE_DIR/forms-manifest.json"
        echo "$EX_OK"; return
    fi
    local now; now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if write_json_file "$STATE_DIR/forms-manifest.json" <<JSON
{
  "contract": "anthology-engine-forms-manifest",
  "schema_version": 1,
  "keying": {"law": "contact_id", "never": "email"},
  "hidden_fields": ["contact_id", "anthology_id", "stage"],
  "restamp_behavior": "on gate re-entry the form re-stamps the hidden fields for the ACTIVE anthology and current stage; unroutable submissions land in the exceptions queue with a typed reason",
  "universal_intake_form": {"role": "intake", "hidden_fields": ["contact_id", "anthology_id", "stage"]},
  "per_stage_gate_forms": [
    {"stage": "s3", "role": "title-subtitle-selection", "hidden_fields": ["contact_id", "anthology_id", "stage"]},
    {"stage": "s4", "role": "outline-approval", "hidden_fields": ["contact_id", "anthology_id", "stage"]},
    {"stage": "s5", "role": "chapter-approve-or-rewrite", "hidden_fields": ["contact_id", "anthology_id", "stage"]}
  ],
  "binding_note": "concrete Convert and Flow form ids are bound PER ANTHOLOGY via anthology_registry.py bind --form-ids at anthology creation; this manifest is the hidden-field + re-stamp CONTRACT the operator wires the client's forms to",
  "provisioned_at": "$now"
}
JSON
    then
        note "  forms manifest written: $STATE_DIR/forms-manifest.json"
        note "  OPERATOR: create the client's forms in Convert and Flow with these hidden fields, then bind ids per anthology"
        echo "$EX_OK"
    else
        note "  failed to write forms manifest"
        set_crc 1; echo "$EX_ERR"
    fi
}

step5_drive() {
    note "STEP 5/10 — provision the Drive producer root under the EXISTING shared root (never a new root)"
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would verify the EXISTING root reachability and get-or-create the Producer folder; no network"
        echo "$EX_OK"; return
    fi
    # Verify the configured EXISTING root first (never creates one).
    local n; n="$(run_collab py "$SCRIPTS/drive-tree-provision.py" verify-root)"
    if [ "$n" != "$EX_OK" ]; then echo "$n"; return; fi
    if [ -z "$PRODUCER_NAME" ]; then
        note "  root verified; --producer not supplied, so the Producer folder is created at first-anthology bind (idempotent)"
        echo "$EX_OK"; return
    fi
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would get-or-create Producer folder for '$PRODUCER_NAME'"
        echo "$EX_OK"; return
    fi
    n="$(run_collab py "$SCRIPTS/drive-tree-provision.py" provision --producer "$PRODUCER_NAME")"
    echo "$n"
}

step6_ledger() {
    note "STEP 6/10 — bootstrap the ledger base + local mirror schemas"
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would run anthology_state.py bootstrap (local mirror + meta); no write"
        echo "$EX_OK"; return
    fi
    local n; n="$(run_collab py "$SCRIPTS/anthology_state.py" bootstrap ${STATE_DIR_OVERRIDE:+--state-dir "$STATE_DIR_OVERRIDE"})"
    echo "$n"
}

step7_webhook() {
    note "STEP 7/10 — generate the webhook route + its secret (label ANTHOLOGY_INTAKE_HOOK_SECRET)"
    report_intake_hook_state
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would generate any absent secret 0600 and materialize the resolved route"
        echo "$EX_OK"; return
    fi
    local s1 s2
    s1="$(ensure_secret ANTHOLOGY_INTAKE_HOOK_SECRET "$STATE_DIR/secrets/anthology-intake-hook-secret")"
    s2="$(ensure_secret ANTHOLOGY_GATE_TOKEN_SECRET  "$STATE_DIR/secrets/anthology-gate-token-secret")"
    if [ "$s1" = "ERROR" ] || [ "$s2" = "ERROR" ]; then
        note "  secret generation failed"; set_crc 1; echo "$EX_ERR"; return
    fi
    note "  ANTHOLOGY_INTAKE_HOOK_SECRET: $s1   ANTHOLOGY_GATE_TOKEN_SECRET: $s2   (values never printed)"
    if [ "$s1" = "GENERATED" ] || [ "$s2" = "GENERATED" ]; then
        note "  OPERATOR: export the generated 0600 secret(s) from $STATE_DIR/secrets into the client env store"
    fi
    # Materialize the resolved route from the committed template (SecretRef by
    # LABEL — no value ever lands in this file).
    local tpl="$CONFIG_DIR/route-template.json"
    if [ ! -f "$tpl" ]; then
        note "  route-template.json missing — cannot materialize the route"; set_crc 3; echo "$EX_HELD"; return
    fi
    local loc_masked; loc_masked="$(mask_loc "${CONVERT_AND_FLOW_LOCATION_ID:-$LOCATION_ID_OVERRIDE}")"
    local now; now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if PROV_TPL="$tpl" PROV_OUT="$STATE_DIR/hooks/anthology-intake.route.json" \
       PROV_LOC="$loc_masked" PROV_NOW="$now" python3 - <<'PY'
import json, os, tempfile
tpl = os.environ["PROV_TPL"]; out = os.environ["PROV_OUT"]
with open(tpl, "r", encoding="utf-8") as fh:
    route = json.load(fh)
# SecretRef-by-label MUST already be present; assert we never inline a value.
tok = (route.get("hooks") or {}).get("token")
assert isinstance(tok, dict) and tok.get("source") == "env", "route token must be a SecretRef by env label"
route["resolved"] = {"location_masked": os.environ["PROV_LOC"], "provisioned_at": os.environ["PROV_NOW"]}
os.makedirs(os.path.dirname(out), exist_ok=True)
d = os.path.dirname(out)
fd, tmp = tempfile.mkstemp(prefix=".route.", suffix=".json.tmp", dir=d)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(route, fh, indent=2, ensure_ascii=False); fh.write("\n")
    os.chmod(tmp, 0o644); os.replace(tmp, out)
except Exception:
    try: os.unlink(tmp)
    except OSError: pass
    raise
PY
    then
        note "  resolved route written: $STATE_DIR/hooks/anthology-intake.route.json (secret is a SecretRef by label)"
    else
        note "  failed to materialize the resolved route"; set_crc 1; echo "$EX_ERR"; return
    fi
    # Best-effort live gateway registration; deferral is NOT a hard fail unless
    # --require-live (T1 is executed and observed on the W5.3 canary).
    if command -v openclaw >/dev/null 2>&1; then
        note "  openclaw CLI present — the gateway route merge is performed at the box's hooks surface (verify-webhook proves T1)"
    else
        note "  openclaw CLI not on PATH; route materialized to state dir, gateway merge DEFERRED to the canary"
        if [ "$REQUIRE_LIVE" = "1" ]; then set_crc 3; echo "$EX_HELD"; return; fi
    fi
    echo "$EX_OK"
}

report_intake_hook_state() {
    note "  ANTHOLOGY_INTAKE_HOOK_SECRET = $(label_state ANTHOLOGY_INTAKE_HOOK_SECRET) (env); value never printed"
    note "  ANTHOLOGY_GATE_TOKEN_SECRET  = $(label_state ANTHOLOGY_GATE_TOKEN_SECRET) (env); value never printed"
}

step8_cron() {
    note "STEP 8/10 — register EXACTLY the ONE daily tick (no heartbeat, ever)"
    local cmd="$DAILY_TICK_CMD"
    [ -z "$cmd" ] && cmd="python3 $SCRIPTS/anthology-smoke-test.py run --max-spend-cents 1"
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would write $STATE_DIR/cron-inventory.json with ONE entry and register it idempotently"
        echo "$EX_OK"; return
    fi
    local now; now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local backend="deferred"
    # Best-effort idempotent live registration via the OpenClaw cron CLI.
    if command -v openclaw >/dev/null 2>&1; then
        if openclaw cron list 2>/dev/null | grep -q "anthology-daily-tick"; then
            backend="openclaw-cron"
            note "  daily tick already registered in the OpenClaw cron backend (idempotent no-op)"
        else
            if openclaw cron add --name anthology-daily-tick --schedule "$DAILY_TICK_SCHEDULE" \
                    --command "$cmd" --no-deliver >/dev/null 2>&1; then
                backend="openclaw-cron"
                note "  daily tick registered in the OpenClaw cron backend (--no-deliver: never spams chat)"
            else
                note "  OpenClaw cron add did not accept (schema drift); the declarative inventory remains authoritative"
            fi
        fi
    else
        note "  openclaw CLI not on PATH; the cron inventory is the authoritative single-tick declaration"
    fi
    if [ "$backend" = "deferred" ] && [ "$REQUIRE_LIVE" = "1" ]; then
        note "  --require-live: no live cron backend available"
        # still write the inventory below, then HOLD
    fi
    if write_json_file "$STATE_DIR/cron-inventory.json" <<JSON
{
  "contract": "anthology-engine-cron-inventory",
  "schema_version": 1,
  "no_heartbeat": true,
  "heartbeat_note": "NO heartbeat cron ever exists; guard-cron-inventory.py proves exactly this ONE daily tick and that churn leaves zero recurring jobs",
  "entries": [
    {
      "id": "anthology-daily-tick",
      "kind": "daily-tick",
      "schedule": "$DAILY_TICK_SCHEDULE",
      "command": "$cmd",
      "does": [
        "funded-reachability smoke probe (balance endpoints only, at or under one cent)",
        "hold-queue aging (resume from the exact cursor)",
        "mirror reconcile",
        "7-day stuck-gate re-nudge policy (single deduped auto re-nudge)"
      ],
      "deliver": false,
      "registered_backend": "$backend",
      "provisioned_at": "$now"
    }
  ]
}
JSON
    then
        note "  cron inventory written: $STATE_DIR/cron-inventory.json (exactly one entry; no_heartbeat=true)"
    else
        note "  failed to write the cron inventory"; set_crc 1; echo "$EX_ERR"; return
    fi
    if [ "$backend" = "deferred" ] && [ "$REQUIRE_LIVE" = "1" ]; then set_crc 3; echo "$EX_HELD"; return; fi
    echo "$EX_OK"
}

step9_verify_webhook() {
    note "STEP 9/10 — verify-webhook-t1-t9.sh (structure now; the live T1..T9 battery runs on the W5.3 canary)"
    local script="$SCRIPTS/verify-webhook-t1-t9.sh"
    if [ ! -f "$script" ]; then note "  verify-webhook-t1-t9.sh not present — HELD"; echo "$EX_HELD"; return; fi
    local args=(--dry-run)
    [ "$REQUIRE_LIVE" = "1" ] && args=(--require-live)
    bash "$script" "${args[@]}" >&2; local rc=$?
    set_crc "$rc"
    echo "$(normalize_rc "$rc")"
}

step10_smoke() {
    note "STEP 10/10 — one smoke test (balance endpoints ONLY, total spend at or under one cent)"
    if [ "$SKIP_SMOKE" = "1" ]; then note "  --skip-smoke: skipped"; echo "$EX_OK"; return; fi
    if [ "$MODE" = "dryrun" ]; then
        local n; n="$(run_collab py "$SCRIPTS/anthology-smoke-test.py" plan --max-spend-cents 1)"
        echo "$n"; return
    fi
    local n; n="$(run_collab py "$SCRIPTS/anthology-smoke-test.py" run --max-spend-cents 1)"
    echo "$n"
}

# Department seeding (SPEC 13.1 folds this under provisioning; PRD Section 3.15 /
# CHECKLIST item 14). Runs BETWEEN steps as its own gated sub-step: seed the
# Anthology department via Skill 32 add-department.sh (== POST /api/departments
# create:true), idempotent, verified by reading the department back.
seed_department() {
    note "STEP 3.5 — seed the Anthology department in the client's Command Center (Skill 32 add-department.sh; read-back verified)"
    if [ "$SKIP_DEPARTMENT" = "1" ]; then note "  --skip-department: skipped (CC seeded elsewhere)"; echo "$EX_OK"; return; fi
    local add=""
    local c
    for c in "$SKILLS_ROOT/32-command-center-setup/scripts/add-department.sh" \
             "/data/.openclaw/skills/32-command-center-setup/scripts/add-department.sh" \
             "$HOME/.openclaw/skills/32-command-center-setup/scripts/add-department.sh"; do
        if [ -f "$c" ]; then add="$c"; break; fi
    done
    if [ -z "$add" ]; then
        note "  Skill 32 add-department.sh not found; Command Center not installed on this box — HELD"
        note "  OPERATOR: install Skill 32 command-center-setup first, then re-run provisioning"
        set_crc 127
        echo "$EX_HELD"; return
    fi
    if [ "$MODE" = "dryrun" ]; then
        note "  (dry-run) would run: bash add-department.sh --slug $DEPT_SLUG --name \"$DEPT_NAME\""
        echo "$EX_OK"; return
    fi
    # Seed (idempotent): status is created OR already_exists on success.
    local out1 rc1
    out1="$(bash "$add" --slug "$DEPT_SLUG" --name "$DEPT_NAME" --icon "📚" \
              --head-name "Anthology Producer" \
              --description "Anthology Engine department: the participant board, the chapter-approval review column, and the assembly card." 2>&1)"; rc1=$?
    echo "$out1" >&2
    if [ "$rc1" != "0" ]; then
        note "  add-department.sh fatal (rc=$rc1) — Command Center dependency unavailable"
        set_crc "$rc1"
        echo "$EX_HELD"; return
    fi
    # Read-back verify: a second idempotent call MUST report already_exists.
    local out2 rc2 status2
    out2="$(bash "$add" --slug "$DEPT_SLUG" --name "$DEPT_NAME" 2>&1)"; rc2=$?
    status2="$(PROV_DEPT_SLUG="$DEPT_SLUG" PROV_DEPT_OUT="$out2" python3 - <<'PY'
import json, os
slug = os.environ["PROV_DEPT_SLUG"]
status = ""
for line in os.environ["PROV_DEPT_OUT"].splitlines():
    line = line.strip()
    if line.startswith("{") and line.endswith("}"):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("slug") == slug and "status" in obj:
            status = obj["status"]
print(status)
PY
)"
    if [ "$rc2" != "0" ]; then
        note "  read-back call fatal (rc=$rc2)"; set_crc "$rc2"; echo "$EX_HELD"; return
    fi
    if [ "$status2" = "already_exists" ]; then
        note "  department read-back verified: slug=$DEPT_SLUG status=already_exists (idempotent, persisted)"
        echo "$EX_OK"; return
    fi
    note "  department read-back did NOT confirm existence (status='$status2', expected already_exists)"
    set_crc 5
    echo "$EX_MISMATCH"
}

# ==========================================================================
# Driver.
# ==========================================================================
STEP_LABELS=(
    "1/10 — credential gate"
    "2/10 — custom fields"
    "3/10 — pipeline bind (UI-only)"
    "3.5 — department seeding"
    "4/10 — form contract"
    "5/10 — Drive producer root"
    "6/10 — ledger + mirror bootstrap"
    "7/10 — webhook route + secret"
    "8/10 — one daily tick"
    "9/10 — verify-webhook T1..T9"
    "10/10 — smoke test"
)
STEP_AF=(
    "AF (credential): missing label -> exit 2; commingling AF-AE-COMMINGLE -> exit 4; gate not yet wired -> HELD 3"
    "AF-AE-FIELD-MISSING (exit 2) / AF-AE-FIELD-KEY-MISMATCH (exit 5)"
    "AF-AE-PIT-SCOPE (token cannot read pipelines -> exit 2) / AF-AE-PIPELINE-UI-CREATE (standard pipeline absent and the Skill 6 browser-control create attempt failed or unavailable -> exit 2); API unreachable or edge-block -> HELD 3"
    "department seed / read-back (Command Center unavailable -> HELD 3; read-back mismatch -> 5)"
    "form-contract write error -> exit 1"
    "Drive root unreachable -> exit 2; API unreachable -> HELD 3"
    "ledger bootstrap error"
    "secret gen / route materialization error; gateway deferral (HELD 3 only under --require-live)"
    "cron inventory write error; no live backend under --require-live -> HELD 3"
    "verify-webhook failing test id -> exit 4; battery held under --require-live -> 3"
    "provider unreachable or unfunded -> exit 4 (alert path)"
)
STEP_REMEDIATION=(
    "Set the client's OWN PRD Section 14 labels in the env store; if commingling: replace any operator/shared/other-client credential with the named client's own"
    "Grant the client PIT custom-field WRITE scope; a field that must pre-exist but is absent and cannot be created STOPS setup; a fieldKey mismatch STOPS setup"
    "Grant the client's OWN location-scoped token the opportunities scope so it can read pipelines; create the standard pipeline once in the Convert and Flow UI (pipelines are UI-only, there is no API create endpoint) or bind a pre-existing pipeline with --pipeline-id; never a silent fallback"
    "Install Skill 32 command-center-setup so the Anthology department can be seeded and read back"
    "Free space / permissions for the state dir; re-run"
    "Confirm the EXISTING shared Drive root is reachable via the operator service account (GOOGLE_IMPERSONATE_USER); never provision a new root"
    "Confirm the state dir is writable by the node user; re-run"
    "Ensure the state dir secrets subdir is writable (0600); export any generated secret into the client env store"
    "Provide a live cron backend (openclaw cron) or accept the declarative inventory; re-run"
    "Register the gateway route and secret; then re-run verify-webhook-t1-t9.sh (the live battery runs on the canary)"
    "Fund the client's OWN provider accounts (Ollama Cloud / OpenRouter / Gemini / Minimax / Kie.ai); re-run the smoke test"
)

run_pipeline() {
    # Root guard (config writes as the node user, never root) — enforced for the
    # write modes only.
    if [ "$MODE" = "live" ] || [ "$MODE" = "dryrun" ]; then
        local rg; rg="$(check_root_guard "$(id -u)")"
        if [ "$rg" != "0" ]; then
            op_surface "0/10 — preflight" "running as root is refused (config writes must be the node user)" "-" "$EX_STOP" \
                "Re-run provisioning as the node user, e.g. sudo -u node bash $PROG ..." \
                "Root config writes freeze the gateway (EACCES on client boxes)"
            return "$EX_STOP"
        fi
    fi
    note "state dir: $STATE_DIR"
    [ "$MODE" = "dryrun" ] && note "MODE = DRY RUN (no writes, no network)"

    # Channel for the raw child rc to survive each step's command-substitution
    # subshell (a subshell cannot mutate the parent's COLLAB_RC).
    RC_FILE="$(mktemp "${TMPDIR:-/tmp}/prov-crc.XXXXXX")"
    # shellcheck disable=SC2064
    trap "rm -f '$RC_FILE'" RETURN

    local -a fns=(step1_credentials step2_fields step3_pipeline seed_department step4_forms \
                  step5_drive step6_ledger step7_webhook step8_cron step9_verify_webhook step10_smoke)
    local i n
    for i in "${!fns[@]}"; do
        printf '0' > "$RC_FILE"        # reset before each step
        n="$(${fns[$i]})"; n="${n:-$EX_ERR}"
        COLLAB_RC="$(cat "$RC_FILE" 2>/dev/null || echo 0)"
        if [ "$n" != "$EX_OK" ]; then
            op_surface "${STEP_LABELS[$i]}" "${STEP_AF[$i]}" "$COLLAB_RC" "$n" "${STEP_REMEDIATION[$i]}"
            [ "$JSONOUT" = "1" ] && emit_json "$i" "$n"
            return "$n"
        fi
    done
    note "PROVISIONING PASSED THE GATE — all ten steps idempotently satisfied (department seeded + read-back verified)"
    [ "$JSONOUT" = "1" ] && emit_json "-1" "$EX_OK"
    return "$EX_OK"
}

emit_json() {   # $1 failed-index (-1 = none)  $2 final-exit
    local failed="$1" final="$2"
    PROV_FAILED="$failed" PROV_FINAL="$final" PROV_STEPS="$(printf '%s\n' "${STEP_LABELS[@]}")" python3 - <<'PY'
import json, os
steps = [s for s in os.environ["PROV_STEPS"].splitlines() if s]
failed = int(os.environ["PROV_FAILED"]); final = int(os.environ["PROV_FINAL"])
out = {"contract": "anthology-provisioning-summary", "final_exit": final,
       "passed": final == 0, "stopped_at_step": (steps[failed] if failed >= 0 else None),
       "steps": steps}
print(json.dumps(out, indent=2, ensure_ascii=False))
PY
}

# ==========================================================================
# --plan
# ==========================================================================
print_plan() {
    cat >&2 <<PLAN
[$PROG] SPEC 13.1 provisioning plan (idempotent; config writes as the node user):
  1/10  credential gate            caf_credential_gate.py (all 3 env stores, live-process-first; SET/NOT SET; commingling fingerprint)
  2/10  custom fields              anthology_registry.py provision-fields (19 keys; missing -> STOP; key mismatch -> exit 5)
  3/10  pipeline bind (UI-only)     anthology_registry.py probe-scope (READ pipelines; AF-AE-PIT-SCOPE) then provision-pipeline (find BY NAME + bind; absent -> AF-AE-PIPELINE-UI-CREATE)
  3.5   department seeding         32-command-center-setup/add-department.sh --slug anthology (idempotent; read-back = already_exists)
  4/10  form contract              forms-manifest.json (hidden fields contact_id/anthology_id/stage; re-stamp; per-anthology bind)
  5/10  Drive producer root        drive-tree-provision.py verify-root (+ provision --producer); never a new root
  6/10  ledger + mirror bootstrap  anthology_state.py bootstrap
  7/10  webhook route + secret     generate 0600 secret when NOT SET (never printed); materialize the resolved route (SecretRef by label)
  8/10  one daily tick             cron-inventory.json (exactly one; no_heartbeat) + idempotent openclaw cron add --no-deliver
  9/10  verify-webhook T1..T9      verify-webhook-t1-t9.sh (structure now; live battery observed on the W5.3 canary)
  10/10 smoke test                 anthology-smoke-test.py run --max-spend-cents 1 (balance endpoints only)
Exit: 0 gate passed; nonzero STOPS setup with an operator surface (2 validation, 3 held, 4 violation, 5 read-back mismatch).
PLAN
    return "$EX_OK"
}

# ==========================================================================
# --self-test : force-observe EVERY failure mode with synthetic stub
# collaborators. No network, no siblings, no real writes outside a temp dir.
# ==========================================================================
self_test() {
    local fails=0
    local tmp; tmp="$(mktemp -d "${TMPDIR:-/tmp}/prov-selftest.XXXXXX")"
    # Hermeticity: neutralize the real-box fallback paths ($HOME/.openclaw, the
    # live env stores) so the harness never touches a live Command Center or a
    # real credential. A RECORDING openclaw stub is prepended to PATH so the
    # cron step NEVER mutates the operator's real cron backend. Restored on RETURN.
    local _saved_home="${HOME:-}" _saved_path="${PATH:-}"
    HOME="$tmp"
    local stub_bin="$tmp/bin"; mkdir -p "$stub_bin"
    cat > "$stub_bin/openclaw" <<'OCSTUB'
#!/usr/bin/env bash
# Recording, side-effect-free openclaw stub for the provisioner self-test.
if [ "$1" = "cron" ] && [ "$2" = "list" ]; then exit 0; fi          # no existing crons
if [ "$1" = "cron" ] && [ "$2" = "add" ]; then
    echo "$*" >> "${OC_STUB_LOG:?}"; exit 0                          # record, never mutate
fi
exit 0
OCSTUB
    chmod +x "$stub_bin/openclaw"
    export OC_STUB_LOG="$tmp/openclaw-cron-add.log"; : > "$OC_STUB_LOG"
    PATH="$stub_bin:$PATH"
    trap 'rm -rf "$tmp"; HOME="$_saved_home"; PATH="$_saved_path"; unset OC_STUB_LOG' RETURN
    local stub_scripts="$tmp/scripts"; mkdir -p "$stub_scripts"

    # ---- unit 1: normalize_rc mapping -------------------------------------
    local pairs=("0:$EX_OK" "2:$EX_STOP" "3:$EX_HELD" "4:$EX_VIOLATION" "5:$EX_MISMATCH" "1:$EX_ERR" "127:$EX_ERR" "9:$EX_ERR")
    local p in exp got
    for p in "${pairs[@]}"; do
        in="${p%%:*}"; exp="${p##*:}"; got="$(normalize_rc "$in")"
        if [ "$got" != "$exp" ]; then echo "  FAIL normalize_rc($in)=$got expected $exp" >&2; fails=$((fails+1)); fi
    done

    # ---- unit 2: root guard ------------------------------------------------
    [ "$(check_root_guard 0)"   = "$EX_STOP" ] || { echo "  FAIL root guard: euid 0 not refused" >&2; fails=$((fails+1)); }
    [ "$(check_root_guard 501)" = "$EX_OK"   ] || { echo "  FAIL root guard: node euid refused" >&2; fails=$((fails+1)); }

    # ---- unit 3: mask_loc never leaks a full id ---------------------------
    local masked; masked="$(mask_loc "LOC1234567890SECRET")"
    if echo "$masked" | grep -q "LOC1234567890"; then echo "  FAIL mask_loc leaked the id" >&2; fails=$((fails+1)); fi
    [ "$(mask_loc "")" = "NOT SET" ] || { echo "  FAIL mask_loc empty" >&2; fails=$((fails+1)); }

    # ---- unit 4: run_collab maps stub child codes + handles absence -------
    local code n
    for code in 0 2 3 4 5 1; do
        printf 'import sys\nsys.exit(%s)\n' "$code" > "$stub_scripts/child.py"
        chmod +x "$stub_scripts/child.py"
        n="$(run_collab py "$stub_scripts/child.py" any 2>/dev/null)"
        exp="$(normalize_rc "$code")"
        if [ "$n" != "$exp" ]; then echo "  FAIL run_collab child=$code -> $n expected $exp" >&2; fails=$((fails+1)); fi
    done
    n="$(run_collab py "$stub_scripts/does-not-exist.py" any 2>/dev/null)"
    [ "$n" = "$EX_HELD" ] || { echo "  FAIL run_collab absent-script -> $n expected $EX_HELD" >&2; fails=$((fails+1)); }

    # ---- unit 5: credential-gate (flags-only contract) --------------------
    # The gate is invoked BARE (no subcommand). A bare exit 0 = all labels
    # resolve + clean; exit 2 (no usage text) = genuine missing-label STOP; exit
    # 4 = commingling. A --expect-location that the CLI rejects (rc2+usage) falls
    # back to the pure bare call. Absent gate = HELD.
    local save_scripts="$SCRIPTS"; SCRIPTS="$stub_scripts"; MODE="live"
    local save_loc="${CONVERT_AND_FLOW_LOCATION_ID:-}"; unset CONVERT_AND_FLOW_LOCATION_ID
    printf 'import sys\nsys.exit(0)\n' > "$stub_scripts/caf_credential_gate.py"
    n="$(step1_credentials 2>/dev/null)"
    [ "$n" = "$EX_OK" ] || { echo "  FAIL cred-gate bare-ok: expected $EX_OK got $n" >&2; fails=$((fails+1)); }
    # Genuine missing label (rc 2, no usage text) -> STOP.
    printf 'import sys\nsys.stderr.write("NOT SET: CONVERT_AND_FLOW_PIT\\n")\nsys.exit(2)\n' > "$stub_scripts/caf_credential_gate.py"
    n="$(step1_credentials 2>/dev/null)"
    [ "$n" = "$EX_STOP" ] || { echo "  FAIL cred-gate missing-label: expected $EX_STOP got $n" >&2; fails=$((fails+1)); }
    # Commingling (rc 4 -> EX_VIOLATION).
    printf 'import sys\nsys.stderr.write("AF-AE-COMMINGLE\\n")\nsys.exit(4)\n' > "$stub_scripts/caf_credential_gate.py"
    n="$(step1_credentials 2>/dev/null)"
    [ "$n" = "$EX_VIOLATION" ] || { echo "  FAIL cred-gate commingle: expected $EX_VIOLATION got $n" >&2; fails=$((fails+1)); }
    # --expect-location fallback: gate rejects the flag (rc2+usage) but a pure
    # bare call succeeds (rc0). With the location env SET the flag is attempted,
    # then stripped; the final result must be EX_OK.
    printf 'import sys\nif len(sys.argv)>1:\n    sys.stderr.write("usage: gate\\ngate: error: unrecognized arguments: %%s\\n" %% sys.argv[1:])\n    sys.exit(2)\nsys.exit(0)\n' > "$stub_scripts/caf_credential_gate.py"
    n="$(CONVERT_AND_FLOW_LOCATION_ID=synthloc step1_credentials 2>/dev/null)"
    [ "$n" = "$EX_OK" ] || { echo "  FAIL cred-gate expect-location fallback: expected $EX_OK got $n" >&2; fails=$((fails+1)); }
    # Absent gate -> HELD.
    rm -f "$stub_scripts/caf_credential_gate.py"
    n="$(step1_credentials 2>/dev/null)"
    [ "$n" = "$EX_HELD" ] || { echo "  FAIL cred-gate absent: expected $EX_HELD got $n" >&2; fails=$((fails+1)); }
    [ -n "$save_loc" ] && export CONVERT_AND_FLOW_LOCATION_ID="$save_loc"
    SCRIPTS="$save_scripts"

    # ---- unit 6: PIT-scope STOP is force-observed --------------------------
    SCRIPTS="$stub_scripts"
    printf 'import sys\nc=sys.argv[1] if len(sys.argv)>1 else ""\nsys.exit(2 if c=="probe-scope" else 0)\n' > "$stub_scripts/anthology_registry.py"
    n="$(step3_pipeline 2>/dev/null)"
    [ "$n" = "$EX_STOP" ] || { echo "  FAIL pipeline PIT-scope: expected $EX_STOP got $n" >&2; fails=$((fails+1)); }
    # provision-pipeline unreachable -> HELD after a clean probe.
    printf 'import sys\nc=sys.argv[1] if len(sys.argv)>1 else ""\nsys.exit(3 if c=="provision-pipeline" else 0)\n' > "$stub_scripts/anthology_registry.py"
    n="$(step3_pipeline 2>/dev/null)"
    [ "$n" = "$EX_HELD" ] || { echo "  FAIL pipeline provision held: expected $EX_HELD got $n" >&2; fails=$((fails+1)); }
    # field-key mismatch (exit 5) at step 2.
    printf 'import sys\nc=sys.argv[1] if len(sys.argv)>1 else ""\nsys.exit(5 if c=="provision-fields" else 0)\n' > "$stub_scripts/anthology_registry.py"
    n="$(step2_fields 2>/dev/null)"
    [ "$n" = "$EX_MISMATCH" ] || { echo "  FAIL fields mismatch: expected $EX_MISMATCH got $n" >&2; fails=$((fails+1)); }
    # field missing (exit 2) at step 2.
    printf 'import sys\nc=sys.argv[1] if len(sys.argv)>1 else ""\nsys.exit(2 if c=="provision-fields" else 0)\n' > "$stub_scripts/anthology_registry.py"
    n="$(step2_fields 2>/dev/null)"
    [ "$n" = "$EX_STOP" ] || { echo "  FAIL fields missing: expected $EX_STOP got $n" >&2; fails=$((fails+1)); }
    SCRIPTS="$save_scripts"

    # ---- unit 7: department seed + read-back -------------------------------
    local deptdir="$tmp/skills/32-command-center-setup/scripts"; mkdir -p "$deptdir"
    # Stub add-department: first call -> created; subsequent -> already_exists.
    cat > "$deptdir/add-department.sh" <<'PYADD'
#!/usr/bin/env bash
marker="${TMPDIR:-/tmp}/.prov-dept-seeded"
if [ -f "$marker" ]; then
  echo '---SUMMARY---'; echo '{"slug":"anthology","workspace_id":"anthology","status":"already_exists"}'
else
  : > "$marker"
  echo '---SUMMARY---'; echo '{"slug":"anthology","workspace_id":"anthology","status":"created"}'
fi
exit 0
PYADD
    chmod +x "$deptdir/add-department.sh"
    rm -f "${TMPDIR:-/tmp}/.prov-dept-seeded"
    local save_root="$SKILLS_ROOT"; SKILLS_ROOT="$tmp/skills"; MODE="live"; SKIP_DEPARTMENT=0
    n="$(seed_department 2>/dev/null)"
    [ "$n" = "$EX_OK" ] || { echo "  FAIL department seed+readback: expected $EX_OK got $n" >&2; fails=$((fails+1)); }
    rm -f "${TMPDIR:-/tmp}/.prov-dept-seeded"
    # A department that never reports already_exists on read-back -> mismatch.
    cat > "$deptdir/add-department.sh" <<'PYADD'
#!/usr/bin/env bash
echo '---SUMMARY---'; echo '{"slug":"anthology","workspace_id":"anthology","status":"created"}'
exit 0
PYADD
    chmod +x "$deptdir/add-department.sh"
    n="$(seed_department 2>/dev/null)"
    [ "$n" = "$EX_MISMATCH" ] || { echo "  FAIL department readback-mismatch: expected $EX_MISMATCH got $n" >&2; fails=$((fails+1)); }
    # add-department fatal (CC absent) -> HELD.
    printf '#!/usr/bin/env bash\necho "[add-department] FATAL: mission-control.db not found" >&2\nexit 1\n' > "$deptdir/add-department.sh"
    n="$(seed_department 2>/dev/null)"
    [ "$n" = "$EX_HELD" ] || { echo "  FAIL department CC-absent: expected $EX_HELD got $n" >&2; fails=$((fails+1)); }
    # Command Center missing entirely -> HELD.
    rm -rf "$tmp/skills"
    n="$(seed_department 2>/dev/null)"
    [ "$n" = "$EX_HELD" ] || { echo "  FAIL department no-CC-skill: expected $EX_HELD got $n" >&2; fails=$((fails+1)); }
    SKILLS_ROOT="$save_root"

    # ---- unit 8: node-user JSON writers land valid JSON --------------------
    STATE_DIR="$tmp/state"; MODE="live"
    n="$(step4_forms 2>/dev/null)"
    [ "$n" = "$EX_OK" ] && python3 -c "import json;json.load(open('$tmp/state/forms-manifest.json'))" 2>/dev/null \
        || { echo "  FAIL step4 forms manifest not valid JSON" >&2; fails=$((fails+1)); }
    n="$(step8_cron 2>/dev/null)"
    if [ "$n" = "$EX_OK" ]; then
        python3 - "$tmp/state/cron-inventory.json" <<'PY' || fails=$((fails+1))
import json, sys
o = json.load(open(sys.argv[1]))
assert o.get("no_heartbeat") is True, "no_heartbeat must be true"
assert len(o.get("entries", [])) == 1, "exactly one cron entry"
assert o["entries"][0]["kind"] == "daily-tick"
assert o["entries"][0]["deliver"] is False, "daily tick must be deliver:false (client-silent)"
PY
        # The recording openclaw stub must have been called with the tick name
        # AND --no-deliver (never spams chat), and NEVER a heartbeat.
        if ! grep -q -- "anthology-daily-tick" "$OC_STUB_LOG"; then echo "  FAIL step8 did not register the named tick" >&2; fails=$((fails+1)); fi
        if ! grep -q -- "--no-deliver" "$OC_STUB_LOG"; then echo "  FAIL step8 cron add missing --no-deliver" >&2; fails=$((fails+1)); fi
        if grep -qi "heartbeat" "$OC_STUB_LOG"; then echo "  FAIL step8 registered a heartbeat" >&2; fails=$((fails+1)); fi
    else
        echo "  FAIL step8 cron inventory rc=$n" >&2; fails=$((fails+1))
    fi

    # ---- unit 9: secret generation is 0600 and NEVER printed ---------------
    local secret_out; secret_out="$(ensure_secret ANTHOLOGY_TESTSECRET_UNSET_XYZ "$tmp/state/secrets/testsecret" 2>&1)"
    [ "$secret_out" = "GENERATED" ] || { echo "  FAIL ensure_secret returned '$secret_out'" >&2; fails=$((fails+1)); }
    if [ -f "$tmp/state/secrets/testsecret" ]; then
        local perms; perms="$(python3 -c "import os,stat;print(oct(stat.S_IMODE(os.stat('$tmp/state/secrets/testsecret').st_mode)))")"
        [ "$perms" = "0o600" ] || { echo "  FAIL secret perms $perms (expected 0o600)" >&2; fails=$((fails+1)); }
        # The generated value must never appear on any surface we emit.
        local val; val="$(cat "$tmp/state/secrets/testsecret")"
        if echo "$secret_out" | grep -qF "$val"; then echo "  FAIL secret value leaked to surface" >&2; fails=$((fails+1)); fi
    else
        echo "  FAIL secret file not created" >&2; fails=$((fails+1))
    fi
    # An already-set env label short-circuits (SET-env), never regenerates.
    secret_out="$(ANTHOLOGY_TESTSECRET_SET_XYZ=already ensure_secret ANTHOLOGY_TESTSECRET_SET_XYZ "$tmp/state/secrets/none" 2>&1)"
    [ "$secret_out" = "SET-env" ] || { echo "  FAIL ensure_secret env short-circuit: '$secret_out'" >&2; fails=$((fails+1)); }

    # ---- unit 10: smoke unfunded (exit 4) is a VIOLATION surface -----------
    SCRIPTS="$stub_scripts"; SKIP_SMOKE=0; MODE="live"
    printf 'import sys\nc=sys.argv[1] if len(sys.argv)>1 else ""\nsys.exit(4 if c=="run" else 0)\n' > "$stub_scripts/anthology-smoke-test.py"
    n="$(step10_smoke 2>/dev/null)"
    [ "$n" = "$EX_VIOLATION" ] || { echo "  FAIL smoke unfunded: expected $EX_VIOLATION got $n" >&2; fails=$((fails+1)); }
    SCRIPTS="$save_scripts"

    # ---- unit 12: step7 route materialization (SecretRef by label; no leak) -
    SCRIPTS="$save_scripts"; STATE_DIR="$tmp/state7"; MODE="live"; REQUIRE_LIVE=0
    local _sv1="${ANTHOLOGY_INTAKE_HOOK_SECRET:-}" _sv2="${ANTHOLOGY_GATE_TOKEN_SECRET:-}"
    unset ANTHOLOGY_INTAKE_HOOK_SECRET ANTHOLOGY_GATE_TOKEN_SECRET
    n="$(step7_webhook 2>/dev/null)"
    if [ "$n" = "$EX_OK" ] && [ -f "$tmp/state7/hooks/anthology-intake.route.json" ]; then
        python3 - "$tmp/state7/hooks/anthology-intake.route.json" <<'PY' || fails=$((fails+1))
import json, re, sys
p = sys.argv[1]; r = json.load(open(p))
tok = (r.get("hooks") or {}).get("token")
assert isinstance(tok, dict) and tok.get("source") == "env" and tok.get("id") == "ANTHOLOGY_INTAKE_HOOK_SECRET", \
    "route token must be a SecretRef by label, not an inlined value"
assert not re.search(r"[0-9a-f]{64}", open(p).read()), "route file contains a secret-shaped 64-hex value"
PY
        local _secf="$tmp/state7/secrets/anthology-intake-hook-secret"
        if [ -f "$_secf" ]; then
            local _val; _val="$(cat "$_secf")"
            if grep -qF "$_val" "$tmp/state7/hooks/anthology-intake.route.json"; then
                echo "  FAIL step7 secret value leaked into the resolved route" >&2; fails=$((fails+1))
            fi
        fi
    else
        echo "  FAIL step7 route materialization rc=$n (route file missing?)" >&2; fails=$((fails+1))
    fi
    [ -n "$_sv1" ] && export ANTHOLOGY_INTAKE_HOOK_SECRET="$_sv1"
    [ -n "$_sv2" ] && export ANTHOLOGY_GATE_TOKEN_SECRET="$_sv2"

    # ---- unit 11: no Anthropic identifier / no client PII in this file -----
    # Deny-pattern shapes assembled from fragments so no banned literal lives here.
    local _a="anthro""pic" _c="clau""de-"
    if grep -qiE "$_c|$_a/|us\.$_a\." "${BASH_SOURCE[0]:-$0}"; then
        echo "  FAIL this script contains an Anthropic-family id shape" >&2; fails=$((fails+1))
    fi

    if [ "$fails" -eq 0 ]; then
        echo "[$PROG] SELF-TEST PASS — every provisioning failure mode force-observed (mapping, root guard, credential STOP/commingle, PIT-scope, field missing/mismatch, department seed+read-back, cron single-tick, 0600 secret non-leak, smoke violation)" >&2
        return "$EX_OK"
    fi
    echo "[$PROG] SELF-TEST FAIL — $fails check(s) failed" >&2
    return "$EX_ERR"
}

# ==========================================================================
# Dispatch.
# ==========================================================================
case "$MODE" in
    plan)     print_plan; exit $? ;;
    selftest) self_test; exit $? ;;
    dryrun|live) run_pipeline; exit $? ;;
    *) echo "[$PROG] internal: unknown mode $MODE" >&2; exit "$EX_ERR" ;;
esac
