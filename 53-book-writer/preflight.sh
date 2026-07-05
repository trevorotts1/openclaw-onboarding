#!/usr/bin/env bash
# 53-book-writer/preflight.sh — per-box provider capability probe (idempotent).
# ============================================================================
# PROBES the CLIENT's actually-configured model providers (never assumes) and
# resolves each capability tier (HEAVY-WRITER / MID-WRITER / FORMATTER /
# RESEARCHER / IMAGE) to the client's OWN providers — NEVER Anthropic, NEVER
# operator keys. It writes model-map.json next to this script and FAILS LOUD when
# a REQUIRED tier is unresolved (an unconfigured box must not silently ship empty
# tiers). Re-running is safe: it preserves any operator-filled tier values and
# overwrites the probe block in place.
#
# The probe is by CAPABILITY + NAME only — it lists local Ollama model ids
# (`ollama list`) and records which provider API-KEY *names* are present in the
# env (NEVER the secret values). It hardcodes NO model id and never substitutes a
# client's express model choice (client-sovereignty rule).
#
# REQUIRED tiers (a book cannot be written without them): HEAVY-WRITER, MID-WRITER,
# FORMATTER. RESEARCHER + IMAGE are optional (their stages degrade gracefully).
#
# OPTIONS
#   --run-dir DIR   also cross-check the resolved tier->model map into
#                   <DIR>/run/RUN-LEDGER.json (preflight_tier_map) so the
#                   no-Anthropic gate (prove_bw_noanthropic) re-scans the resolved
#                   tier model ids on the run.
#
# EXIT CODES
#   0  probe complete; every REQUIRED tier resolved to a non-Anthropic client model
#   6  python3 missing (BW_DEPS_MISSING)
#   7  a REQUIRED tier is unresolved OR resolves to an Anthropic/claude id
#      (BW_PREFLIGHT_UNCONFIGURED — fix model-map.json and re-run)
# ============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OUT="$SELF_DIR/model-map.json"

RUN_DIR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) RUN_DIR="${2:-}"; shift 2 ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "preflight: unknown argument: $1" >&2; exit 2 ;;
    esac
done

note() { echo "=== [preflight] $* ==="; }

command -v python3 >/dev/null 2>&1 || { echo "preflight: python3 required" >&2; exit 6; }

# concurrency cap heuristic: min(16, cores-2); local-Ollama-only boxes cap at 3
# (set by the operator via OC_PROVIDER_CAP).
CORES="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
SLOTS=$(( CORES - 2 )); [ "$SLOTS" -lt 1 ] && SLOTS=1; [ "$SLOTS" -gt 16 ] && SLOTS=16
PROVIDER_CAP="${OC_PROVIDER_CAP:-$SLOTS}"

# --- REAL PROBE (capability + NAMES only) -----------------------------------
# Bound any external probe so an unresponsive daemon can never hang preflight.
PROBE_TIMEOUT="${OC_PREFLIGHT_PROBE_TIMEOUT:-5}"
_bounded() {  # _bounded <secs> <cmd...>  — best-effort timeout; runs bare if none available
    local secs="$1"; shift
    if command -v timeout >/dev/null 2>&1; then timeout "$secs" "$@" 2>/dev/null
    elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$secs" "$@" 2>/dev/null
    else
        "$@" 2>/dev/null & local pid=$!
        ( sleep "$secs"; kill -9 "$pid" 2>/dev/null ) 2>/dev/null & local w=$!
        wait "$pid" 2>/dev/null; kill -9 "$w" 2>/dev/null || true
    fi
}
# Local Ollama model ids (empty if the daemon/CLI is absent or unresponsive). NAMES only.
OLLAMA_MODELS=""
if command -v ollama >/dev/null 2>&1; then
    OLLAMA_MODELS="$(_bounded "$PROBE_TIMEOUT" ollama list | awk 'NR>1{print $1}' | paste -sd, - 2>/dev/null || true)"
fi
# Provider API-KEY *names* present in the env (names only — never the value).
PROVIDER_KEY_NAMES="$(env | grep -oiE '^[A-Z0-9_]*(OPENROUTER|OLLAMA|TOGETHER|GROQ|MISTRAL|DEEPSEEK|FIREWORKS|GEMINI|GOOGLE|OPENAI|XAI|PERPLEXITY)[A-Z0-9_]*=' 2>/dev/null | sed 's/=.*//' | sort -u | paste -sd, - 2>/dev/null || true)"

note "probing providers (cores=$CORES slots=$SLOTS provider_cap=$PROVIDER_CAP)"
note "ollama models: ${OLLAMA_MODELS:-<none>}"
note "provider key names present: ${PROVIDER_KEY_NAMES:-<none>}"

OUT="$OUT" SLOTS="$SLOTS" PROVIDER_CAP="$PROVIDER_CAP" \
OLLAMA_MODELS="$OLLAMA_MODELS" PROVIDER_KEY_NAMES="$PROVIDER_KEY_NAMES" \
RUN_DIR="$RUN_DIR" python3 - <<'PY'
import json, os, re, sys, datetime

out = os.environ["OUT"]
existing = {}
if os.path.exists(out):
    try:
        existing = json.load(open(out))
    except Exception:
        existing = {}

etiers = existing.get("tiers", {}) if isinstance(existing.get("tiers"), dict) else {}
ollama_models = [m for m in os.environ.get("OLLAMA_MODELS", "").split(",") if m.strip()]
key_names = [k for k in os.environ.get("PROVIDER_KEY_NAMES", "").split(",") if k.strip()]

REQUIRED = ("HEAVY-WRITER", "MID-WRITER", "FORMATTER")
OPTIONAL = ("RESEARCHER", "IMAGE")
ANTH = re.compile(r"anthropic|claude", re.IGNORECASE)

tiers = {t: (etiers.get(t) or "").strip() for t in (*REQUIRED, *OPTIONAL)}

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
model_map = {
    "$note": "CLIENT providers only. Fill each REQUIRED tier with the client's OWN model id. "
             "NEVER an Anthropic/claude-* id (AF-BK-ANTHROPIC hard-fails). A client's express "
             "choice is never substituted. preflight.sh probes capabilities + key NAMES only.",
    "tiers": tiers,
    "provider_caps": {"slots": int(os.environ["SLOTS"]), "provider_cap": int(os.environ["PROVIDER_CAP"])},
    "probe": {
        "ollama_models": ollama_models,
        "provider_key_names": key_names,
        "probed_at": now,
    },
    "search_capability": existing.get("search_capability", "unknown"),
    "image_capability": existing.get("image_capability", "unknown"),
    "resolved_at": now,
}
json.dump(model_map, open(out, "w"), indent=2)
print("wrote", out)

# --- enforcement: REQUIRED tiers must resolve to a non-Anthropic client model ---
problems = []
for t in REQUIRED:
    v = tiers.get(t, "")
    if not v:
        problems.append("REQUIRED tier %s is UNRESOLVED — fill model-map.json with the client's "
                        "OWN model id (never Anthropic). Probed ollama models: %s; provider key "
                        "names: %s" % (t, ollama_models or "<none>", key_names or "<none>"))
    elif ANTH.search(v):
        problems.append("REQUIRED tier %s resolves to an Anthropic/claude id %r — client boxes "
                        "NEVER run Anthropic (AF-BK-ANTHROPIC)" % (t, v))
for t in OPTIONAL:
    v = tiers.get(t, "")
    if v and ANTH.search(v):
        problems.append("tier %s resolves to an Anthropic/claude id %r — forbidden" % (t, v))

# --- optional cross-check into the run ledger --------------------------------
run_dir = os.environ.get("RUN_DIR", "").strip()
if run_dir:
    ledger_path = os.path.join(run_dir, "run", "RUN-LEDGER.json")
    try:
        led = {}
        if os.path.isfile(ledger_path):
            led = json.load(open(ledger_path))
        if not isinstance(led, dict):
            led = {}
        led["preflight_tier_map"] = {t: tiers.get(t, "") for t in (*REQUIRED, *OPTIONAL)}
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        json.dump(led, open(ledger_path, "w"), indent=2)
        print("cross-checked resolved tier->model map into", ledger_path)
    except Exception as exc:  # fail-soft: the ledger cross-check must not abort preflight
        print("[preflight] ledger cross-check skipped (%s)" % exc, file=sys.stderr)

if problems:
    print("PREFLIGHT FAIL — the box is not configured for a book run:", file=sys.stderr)
    for p in problems:
        print("  - %s" % p, file=sys.stderr)
    sys.exit(7)
print("all REQUIRED tiers resolved to non-Anthropic client models.")
PY
RC=$?

# optional PDF toolchain note (never fails the run; manuscript .md always delivers)
if command -v pandoc >/dev/null 2>&1 && python3 -c 'import weasyprint' >/dev/null 2>&1; then
    note "PDF toolchain present (pandoc + weasyprint)"
else
    note "PDF toolchain optional/absent — install with: brew install pandoc && pip3 install weasyprint (manuscript .md still delivers)"
fi

if [ "$RC" -ne 0 ]; then
    note "preflight INCOMPLETE (exit $RC) — resolve the REQUIRED tiers in model-map.json and re-run"
    exit "$RC"
fi
note "preflight complete (idempotent)"
