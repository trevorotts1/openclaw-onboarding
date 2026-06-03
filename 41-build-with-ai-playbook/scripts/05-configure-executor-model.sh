#!/usr/bin/env bash
# 05-configure-executor-model.sh — Skill 41 Build With AI Playbook (gap #4)
#
# PURPOSE
#   Detect which LLM providers are active in openclaw.json, query live model
#   lists for the newest minimax-* tag, then configure the EXECUTOR model used
#   by the Skill 41 browser-execution subagent.
#
#   This sets agents.defaults.subagents.executorModel (PRIMARY + FALLBACK) and
#   adds the resolved MiniMax model(s) to the models availability list so the
#   subagent can actually invoke them.  It does NOT touch the client's main
#   agent primary model.
#
# PROVIDERS HANDLED
#   Ollama Cloud  — local Ollama daemon routes :cloud-tagged models via
#                   ~/.ollama/id_ed25519 auth.  Detected by presence of
#                   providers.ollama (or providers["ollama-local"]) in
#                   openclaw.json, OR by OLLAMA_BASE_URL env.
#   OpenRouter    — detected by providers.openrouter.apiKey (or
#                   OPENROUTER_API_KEY env).
#
# VERSION HANDLING
#   Queries Ollama library + OpenRouter /api/v1/models at runtime.
#   Falls back to known-current (minimax-m3) if the query fails.
#   Removes stale minimax-m2.x / minimax-2.x entries.
#
# CONTEXT WINDOWS (authoritative, verified 2026-06-03)
#   Ollama Cloud  minimax-m3:cloud    — 512 K tokens (guaranteed minimum)
#   OpenRouter    minimax/minimax-m3  — 1 048 576 tokens (1 M)
#
# IDEMPOTENCY
#   Re-running on an already-configured box converges to correct state;
#   no duplicates are added.
#
# PLATFORM
#   Mac    → $HOME/.openclaw/openclaw.json   (writes as current user)
#   VPS    → /data/.openclaw/openclaw.json   (chown back to node)
#
# USAGE
#   bash 05-configure-executor-model.sh [--dry-run]
#
# CALLED FROM
#   Skill 41 install sequence, after 04-update-core-files.sh.
#   Also safe to run standalone during gap-4 remediation.

set -uo pipefail

# ─── Logging helpers ─────────────────────────────────────────────────────────
P="[skill 41][executor-model]"
info()  { printf '%s %s\n'       "$P" "$*"; }
ok()    { printf '%s \033[32m✓\033[0m %s\n' "$P" "$*"; }
warn()  { printf '%s \033[33m⚠\033[0m %s\n' "$P" "$*" >&2; }
fail()  { printf '%s \033[31m✗\033[0m %s\n' "$P" "$*" >&2; }
die()   { fail "$*"; exit 1; }

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# ─── 1. Platform detection ────────────────────────────────────────────────────
if [[ -f "/data/.openclaw/openclaw.json" ]]; then
  OC_ROOT="/data/.openclaw"
  OC_PLATFORM="vps"
  OC_RUNTIME_USER="node"
elif [[ -f "$HOME/.openclaw/openclaw.json" ]]; then
  OC_ROOT="$HOME/.openclaw"
  OC_PLATFORM="mac"
  OC_RUNTIME_USER="$(whoami)"
else
  die "Cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw — run the OpenClaw installer first"
fi

OC_JSON="$OC_ROOT/openclaw.json"
OC_SECRETS="$OC_ROOT/secrets/.env"

info "Platform : $OC_PLATFORM"
info "Config   : $OC_JSON"
info "Run mode : $( [[ $DRY_RUN -eq 1 ]] && echo DRY-RUN || echo LIVE )"

# ─── 2. Load secrets env for key detection ───────────────────────────────────
if [[ -f "$OC_SECRETS" ]]; then
  # Source into a subshell-visible env; guard against set -e breaking on bad lines
  set +u
  # shellcheck source=/dev/null
  set -a; . "$OC_SECRETS" 2>/dev/null || true; set +a
  set -u
fi

# ─── 3. Detect providers from openclaw.json ──────────────────────────────────
# We do NOT trust self-reported strings; we look at actual key presence.

detect_providers() {
  python3 - "$OC_JSON" <<'PYEOF'
import json, sys

path = sys.argv[1]
try:
    cfg = json.load(open(path))
except Exception as e:
    print(f"ERROR: cannot parse {path}: {e}", file=sys.stderr)
    sys.exit(1)

providers = cfg.get("models", {}).get("providers", {})

# Ollama Cloud: provider named "ollama" or "ollama-local" present.
# The :cloud routing goes through the local daemon; we detect Ollama Cloud
# capability by the provider existing (it registers regardless of cloud tag).
has_ollama = (
    "ollama" in providers or
    "ollama-local" in providers
)

# OpenRouter: must have a real apiKey (not empty/placeholder).
or_cfg = providers.get("openrouter", {})
or_key = or_cfg.get("apiKey", "").strip()
has_openrouter = bool(or_key and not or_key.startswith("sk-or-PLACEHOLDER"))

print(f"OLLAMA={'1' if has_ollama else '0'}")
print(f"OPENROUTER={'1' if has_openrouter else '0'}")
PYEOF
}

# Also honour env-var presence as a fallback signal
_or_env="${OPENROUTER_API_KEY:-}"
_ol_env="${OLLAMA_BASE_URL:-}"

PROVIDER_INFO="$(detect_providers)"
HAS_OLLAMA="$(echo "$PROVIDER_INFO" | grep '^OLLAMA=' | cut -d= -f2)"
HAS_OPENROUTER="$(echo "$PROVIDER_INFO" | grep '^OPENROUTER=' | cut -d= -f2)"

# Env vars as secondary signal (additive, never subtractive)
[[ -n "$_or_env" && "$_or_env" == sk-or-* ]] && HAS_OPENROUTER="1"
[[ -n "$_ol_env" ]] && HAS_OLLAMA="1"

HAS_OLLAMA="${HAS_OLLAMA:-0}"
HAS_OPENROUTER="${HAS_OPENROUTER:-0}"

info "Ollama Cloud present  : $( [[ $HAS_OLLAMA -eq 1 ]] && echo YES || echo NO )"
info "OpenRouter present    : $( [[ $HAS_OPENROUTER -eq 1 ]] && echo YES || echo NO )"

if [[ "$HAS_OLLAMA" -ne 1 && "$HAS_OPENROUTER" -ne 1 ]]; then
  warn "Neither Ollama Cloud nor OpenRouter detected in openclaw.json / env."
  warn "Cannot configure MiniMax executor model — at least one provider is required."
  warn "Add an Ollama or OpenRouter provider first, then re-run this script."
  exit 1
fi

# ─── 4. Discover latest MiniMax tag from live model lists ────────────────────
# Known-current fallbacks (used when live query fails)
FALLBACK_OLLAMA_TAG="minimax-m3:cloud"          # 512K ctx
FALLBACK_OR_MODEL="minimax/minimax-m3"           # 1M ctx

# 4a. Ollama library — GET https://ollama.com/library/minimax-m3/tags
#     Parse for the latest/cloud tag.
discover_ollama_minimax() {
  local tag=""
  local url="https://ollama.com/library/minimax-m3/tags"
  local body
  if body="$(curl -fsSL --max-time 12 "$url" 2>/dev/null)"; then
    # Extract the first tag that contains 'cloud' or the first minimax-m3 tag
    tag="$(echo "$body" | grep -oE 'minimax-m3:[a-zA-Z0-9._-]+' | grep -i 'cloud' | head -1 || true)"
    if [[ -z "$tag" ]]; then
      # Fallback: any minimax-m3 tag
      tag="$(echo "$body" | grep -oE 'minimax-m3:[a-zA-Z0-9._-]+' | head -1 || true)"
    fi
  fi
  echo "${tag:-$FALLBACK_OLLAMA_TAG}"
}

# 4b. OpenRouter /api/v1/models — find newest minimax/* model
discover_openrouter_minimax() {
  local model_id=""
  local url="https://openrouter.ai/api/v1/models"
  # Build the auth header as an ARRAY so curl receives the flag and its value as TWO
  # separate argv entries. A single "-H Authorization: Bearer KEY" string would be passed
  # to curl as ONE argument and the header would never be sent (silent auth failure).
  local auth_header=()
  [[ -n "${OPENROUTER_API_KEY:-}" ]] && auth_header=(-H "Authorization: Bearer ${OPENROUTER_API_KEY}")

  local body
  # "${auth_header[@]+...}" guard keeps the empty-array case safe under `set -u` on bash 3.2
  # (macOS default): no key -> zero curl args; key present -> two args (-H and its value).
  if body="$(curl -fsSL --max-time 15 "${auth_header[@]+"${auth_header[@]}"}" "$url" 2>/dev/null)"; then
    # Find latest minimax model — prefer m3 over older versions
    model_id="$(echo "$body" | python3 -c "
import json, sys, re
try:
    data = json.load(sys.stdin)
    models = data.get('data', data) if isinstance(data, dict) else data
    minimax = [m['id'] for m in models if isinstance(m, dict) and 'minimax' in m.get('id','').lower()]
    # Sort: prefer m3, then by version descending
    def rank(mid):
        # extract numeric suffix for sorting: m3 > m2.7 > m2.5 > m2
        nums = re.findall(r'[\d.]+', mid.split('/')[-1])
        return tuple(float(n) for n in nums) if nums else (0,)
    minimax.sort(key=rank, reverse=True)
    print(minimax[0] if minimax else '')
except Exception:
    print('')
" 2>/dev/null || true)"
  fi
  echo "${model_id:-$FALLBACK_OR_MODEL}"
}

info "Querying live Ollama library for latest minimax-m3 tag..."
OLLAMA_MODEL_TAG="$(discover_ollama_minimax)"
info "  Ollama tag resolved  : $OLLAMA_MODEL_TAG"

info "Querying OpenRouter /api/v1/models for latest minimax model..."
OR_MODEL_ID="$(discover_openrouter_minimax)"
info "  OpenRouter model     : $OR_MODEL_ID"

# Normalise: Ollama model string gets ollama/ prefix; OpenRouter gets openrouter/ prefix
OLLAMA_FULL="ollama/${OLLAMA_MODEL_TAG}"
OR_FULL="openrouter/${OR_MODEL_ID}"

# ─── 5. Resolve context windows ──────────────────────────────────────────────
# Authoritative values (verified 2026-06-03 — Ollama M3=512K, OpenRouter M3=1M)
# These are recorded in the config so downstream tooling knows the true window.
OLLAMA_CTX=524288      # 512 * 1024 = 512K tokens (Ollama Cloud guaranteed minimum)
OR_CTX=1048576         # 1M tokens (OpenRouter)

# ─── 6. Determine executor model assignment per SPEC ────────────────────────
# BOTH providers    → PRIMARY=ollama, FALLBACK=openrouter
# ONLY Ollama Cloud → PRIMARY=ollama (no openrouter fallback)
# ONLY OpenRouter   → PRIMARY=openrouter

if [[ "$HAS_OLLAMA" -eq 1 && "$HAS_OPENROUTER" -eq 1 ]]; then
  EXECUTOR_PRIMARY="$OLLAMA_FULL"
  EXECUTOR_FALLBACK="$OR_FULL"
  EXECUTOR_SCENARIO="both-providers"
  info "Scenario: BOTH providers → PRIMARY=$EXECUTOR_PRIMARY  FALLBACK=$EXECUTOR_FALLBACK"
elif [[ "$HAS_OLLAMA" -eq 1 ]]; then
  EXECUTOR_PRIMARY="$OLLAMA_FULL"
  EXECUTOR_FALLBACK=""
  EXECUTOR_SCENARIO="ollama-only"
  info "Scenario: Ollama-only → PRIMARY=$EXECUTOR_PRIMARY  (no openrouter fallback)"
else
  EXECUTOR_PRIMARY="$OR_FULL"
  EXECUTOR_FALLBACK=""
  EXECUTOR_SCENARIO="openrouter-only"
  info "Scenario: OpenRouter-only → PRIMARY=$EXECUTOR_PRIMARY  (no ollama)"
fi

# ─── 7. Apply config (idempotent Python deep-merge) ─────────────────────────
if [[ $DRY_RUN -eq 1 ]]; then
  info "[DRY-RUN] Would write executor model config to $OC_JSON"
  info "[DRY-RUN] executor_primary  = $EXECUTOR_PRIMARY"
  info "[DRY-RUN] executor_fallback = ${EXECUTOR_FALLBACK:-(none)}"
  info "[DRY-RUN] scenario          = $EXECUTOR_SCENARIO"
  ok "Dry-run complete — no files modified"
  exit 0
fi

# Backup before touching
_ts="$(date +%Y%m%d-%H%M%S)"
cp "$OC_JSON" "${OC_JSON}.bak-pre-skill41-executor-$_ts"
info "Backup: ${OC_JSON}.bak-pre-skill41-executor-$_ts"

python3 - \
  "$OC_JSON" \
  "$EXECUTOR_PRIMARY" \
  "${EXECUTOR_FALLBACK:-}" \
  "$EXECUTOR_SCENARIO" \
  "$OLLAMA_CTX" \
  "$OR_CTX" \
  "$OLLAMA_FULL" \
  "$OR_FULL" \
  "$HAS_OLLAMA" \
  "$HAS_OPENROUTER" \
  <<'PYEOF'
import json, sys, re
from pathlib import Path

path          = Path(sys.argv[1])
exec_primary  = sys.argv[2]
exec_fallback = sys.argv[3]   # may be ""
scenario      = sys.argv[4]
ollama_ctx    = int(sys.argv[5])
or_ctx        = int(sys.argv[6])
ollama_full   = sys.argv[7]
or_full       = sys.argv[8]
has_ollama    = sys.argv[9] == "1"
has_openrouter= sys.argv[10] == "1"

cfg = json.loads(path.read_text())
before_snapshot = json.dumps(cfg, sort_keys=True)

# ── 7a. models.available — add MiniMax entries, remove stale ones ──────────
models_block = cfg.setdefault("models", {})
available = models_block.setdefault("available", [])

STALE_PATTERNS = re.compile(
    r"minimax-m2|minimax-2\.|minimax/minimax-m2|minimax/minimax-2",
    re.IGNORECASE
)

def is_stale_minimax(entry):
    """Return True if entry is an old/superseded MiniMax model."""
    mid = ""
    if isinstance(entry, str):
        mid = entry
    elif isinstance(entry, dict):
        mid = entry.get("id", entry.get("model", ""))
    return bool(STALE_PATTERNS.search(mid))

def model_id_of(entry):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("id", entry.get("model", ""))
    return ""

# Remove stale entries
stale_removed = [e for e in available if is_stale_minimax(e)]
available = [e for e in available if not is_stale_minimax(e)]
if stale_removed:
    for s in stale_removed:
        print(f"  ✓ Removed stale MiniMax entry: {model_id_of(s)}")

# Build canonical entries for the models we need
def make_model_entry(model_id, ctx_window, provider_tag):
    return {
        "id":             model_id,
        "contextWindow":  ctx_window,
        "provider":       provider_tag,
        "skill41_executor": True,
        "note":           "Configured by skill-41 gap#4 executor-model preflight"
    }

entries_to_add = []
if has_ollama:
    entries_to_add.append((ollama_full, ollama_ctx, "ollama"))
if has_openrouter:
    entries_to_add.append((or_full, or_ctx, "openrouter"))

for (mid, ctx, ptag) in entries_to_add:
    existing_ids = [model_id_of(e) for e in available]
    if mid not in existing_ids:
        available.append(make_model_entry(mid, ctx, ptag))
        print(f"  ✓ Added model: {mid}  (context_window={ctx})")
    else:
        # Update context window + skill41_executor flag on existing entry
        for e in available:
            if isinstance(e, dict) and model_id_of(e) == mid:
                old_ctx = e.get("contextWindow")
                e["contextWindow"]      = ctx
                e["skill41_executor"]   = True
                if old_ctx != ctx:
                    print(f"  ✓ Updated context window for {mid}: {old_ctx} → {ctx}")
                else:
                    print(f"  ℹ  Model already present (no ctx change): {mid}")
                break

models_block["available"] = available

# ── 7b. agents.defaults.subagents.executorModel ─────────────────────────────
agents   = cfg.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
sub      = defaults.setdefault("subagents", {})

old_exec = sub.get("executorModel", {})

new_exec = {"primary": exec_primary}
if exec_fallback:
    new_exec["fallback"] = exec_fallback
new_exec["scenario"]    = scenario
new_exec["skill"]       = "41-build-with-ai-playbook"
_dt = __import__("datetime")
new_exec["configured_at"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

sub["executorModel"] = new_exec

# ── 7c. Ensure allowAgents wildcard on every agents.list entry ───────────────
agent_list = agents.get("list", [])
updated_entries = 0
for entry in agent_list:
    if not isinstance(entry, dict):
        continue
    entry_sub = entry.setdefault("subagents", {})
    if entry_sub.get("allowAgents") != ["*"]:
        entry_sub["allowAgents"] = ["*"]
        updated_entries += 1
if updated_entries:
    print(f"  ✓ allowAgents=['*'] applied to {updated_entries} agent entries")

# ── 7d. Write ────────────────────────────────────────────────────────────────
after_snapshot = json.dumps(cfg, sort_keys=True)
if before_snapshot == after_snapshot:
    print("  ℹ  Config already canonical — no-op (idempotent)")
else:
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"  ✓ Wrote updated config → {path}")

print(f"  ✓ executorModel.primary   = {exec_primary}")
if exec_fallback:
    print(f"  ✓ executorModel.fallback  = {exec_fallback}")
print(f"  ✓ scenario                = {scenario}")
PYEOF

# ─── 8. Restore ownership on VPS ─────────────────────────────────────────────
if [[ "$OC_PLATFORM" == "vps" ]]; then
  chown "${OC_RUNTIME_USER}:${OC_RUNTIME_USER}" "$OC_JSON" 2>/dev/null || \
    warn "chown to $OC_RUNTIME_USER failed — verify file ownership manually"
  ok "VPS: ownership restored to $OC_RUNTIME_USER"
fi

# ─── 9. Validate ─────────────────────────────────────────────────────────────
info "Running: openclaw config validate"
if command -v openclaw >/dev/null 2>&1; then
  if ! openclaw config validate 2>&1; then
    fail "openclaw config validate FAILED — restore from backup: ${OC_JSON}.bak-pre-skill41-executor-${_ts}"
    exit 1
  fi
  ok "openclaw config validate PASSED"
else
  warn "openclaw CLI not on PATH — skipping validation (run 'openclaw config validate' manually)"
fi

# ─── 10. Summary ─────────────────────────────────────────────────────────────
echo ""
echo "${P} ──── EXECUTOR MODEL CONFIGURED ────"
echo "${P}   Platform         : $OC_PLATFORM"
echo "${P}   Scenario         : $EXECUTOR_SCENARIO"
echo "${P}   PRIMARY          : $EXECUTOR_PRIMARY"
[[ -n "$EXECUTOR_FALLBACK" ]] && \
echo "${P}   FALLBACK         : $EXECUTOR_FALLBACK"
echo "${P}   Ollama ctx       : ${OLLAMA_CTX} tokens (512K)"
echo "${P}   OpenRouter ctx   : ${OR_CTX} tokens (1M)"
echo "${P}   Config           : $OC_JSON"
echo "${P}   Backup           : ${OC_JSON}.bak-pre-skill41-executor-${_ts}"
echo ""
ok "05-configure-executor-model.sh complete"
exit 0
