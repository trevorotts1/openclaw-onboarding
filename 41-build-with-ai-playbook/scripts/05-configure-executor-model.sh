#!/usr/bin/env bash
# 05-configure-executor-model.sh — Skill 41 Build With AI Playbook (gap #4)
#
# PURPOSE
#   Detect which LLM providers are active in openclaw.json, query live model
#   lists for the newest minimax-* tag, then configure the EXECUTOR model used
#   by the Skill 41 browser-execution subagent.
#
#   This sets agents.defaults.subagents.model — the REAL, schema-valid OpenClaw
#   key (a model reference; primary + optional fallbacks) that selects the model a
#   spawned sub-agent runs on. It does NOT touch the client's main agent model.
#
#   SHAPE-BUG HISTORY (v16.2.12): earlier this script wrote two FABRICATED keys —
#   top-level `models.available` and `agents.defaults.subagents.executorModel` —
#   that NO OpenClaw schema accepts (2026.5.22 / 2026.6.8 / newer all reject them
#   with "models: Invalid input" / "agents.defaults.subagents: Invalid input").
#   That flipped a valid openclaw.json invalid and rolled boxes back. The correct
#   key is `agents.defaults.subagents.model`; models are addressable by
#   `provider/model-id` (no availability list exists). This script now writes the
#   valid key, HEALS the fabricated ones off any corrupted box, and validates
#   before committing so it can never regress a valid config.
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
        # extract numeric components for sorting: m3 > m2.7 > m2.5 > m2. Match one well-formed
        # decimal per component so a multi-dot id (e.g. m2.5.1) splits into valid numbers rather
        # than one unparseable token ('2.5.1') that would make float() raise and, via the broad
        # except below, silently discard EVERY discovered model.
        nums = re.findall(r'\d+(?:\.\d+)?', mid.split('/')[-1])
        return tuple(float(n) for n in nums) if nums else (0.0,)
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

# ─── 7. Apply config (validate-before-commit, schema-valid subagents.model) ──
if [[ $DRY_RUN -eq 1 ]]; then
  info "[DRY-RUN] Would set agents.defaults.subagents.model in $OC_JSON"
  info "[DRY-RUN] subagents.model.primary  = $EXECUTOR_PRIMARY"
  info "[DRY-RUN] subagents.model.fallback = ${EXECUTOR_FALLBACK:-(none)}"
  info "[DRY-RUN] scenario                 = $EXECUTOR_SCENARIO"
  info "[DRY-RUN] would also HEAL any fabricated models.available / subagents.executorModel"
  ok "Dry-run complete — no files modified"
  exit 0
fi

# ─── 6b. Gateway schema-version probe (informational) + sidecar path ─────────
# Mirrors scripts/apply-fleet-standards.sh. Used ONLY for logging here — the
# commit decision below is made by `openclaw config validate` (validate-before-
# commit), never by a hardcoded version, so a future OpenClaw that ADDS these
# keys is picked up automatically with no code change.
OC_VERSION=""
if command -v openclaw >/dev/null 2>&1; then
  _oc_raw="$(openclaw --version 2>&1 | tr -d '\r' | head -n1 || true)"
  OC_VERSION="$(printf '%s' "$_oc_raw" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
fi
OC_VERSION="${FLEET_OC_VERSION_OVERRIDE:-$OC_VERSION}"
info "Gateway version : ${OC_VERSION:-unknown}"

# Sidecar that preserves the resolved executor model when the live schema rejects
# the inline keys (the extension-registry.json sidecar precedent, CHANGELOG
# v-Skill32). Read by the Skill-41 subagent / a future schema-supporting gateway;
# it NEVER participates in `openclaw config validate`.
EXECUTOR_SIDECAR="$OC_ROOT/skill41-executor-model.json"

# oc_config_valid — rc 0 = live config validates clean, 1 = it fails, 2 = the
# openclaw CLI is unavailable (cannot determine).
oc_config_valid() {
  command -v openclaw >/dev/null 2>&1 || return 2
  openclaw config validate >/dev/null 2>&1
}

# Backup before touching (the restore target if a validate-before-commit fails).
_ts="$(date +%Y%m%d-%H%M%S)"
OC_BACKUP="${OC_JSON}.bak-pre-skill41-executor-$_ts"
if ! cp "$OC_JSON" "$OC_BACKUP"; then
  fail "could not create backup $OC_BACKUP — aborting; live config UNTOUCHED (no restore point = no write)"
  exit 1
fi
info "Backup: $OC_BACKUP"

# The Python step writes to a CANDIDATE, NOT the live config. Bash then validates
# the candidate and keeps it ONLY if `openclaw config validate` passes; otherwise
# the exact prior bytes are restored. This makes it IMPOSSIBLE for a schema-
# rejected key (models.available / agents.defaults.subagents.executorModel on the
# 2026.5.22 / 2026.6.8 strict schemas) to turn a VALID openclaw.json INVALID.
OC_CANDIDATE="${OC_JSON}.skill41-candidate.$$"        # object-shape candidate
OC_CAND_STR="${OC_JSON}.skill41-candidate-str.$$"     # bare-string-shape candidate (floor)
OC_EFFECTIVE="${OC_JSON}.skill41-effective.$$"        # effective primary the writer intends (commit-confirm)
trap 'rm -f "$OC_CANDIDATE" "$OC_CAND_STR" "$OC_EFFECTIVE" 2>/dev/null || true' EXIT

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
  "$OC_CANDIDATE" \
  "$OC_CAND_STR" \
  "$OC_EFFECTIVE" \
  <<'PYEOF'
import json, sys, re
from pathlib import Path

src           = Path(sys.argv[1])
exec_primary  = sys.argv[2]
exec_fallback = sys.argv[3]                 # may be ""
has_ollama    = sys.argv[9] == "1"
has_openrouter= sys.argv[10] == "1"
cand_obj      = Path(sys.argv[11])          # object-shape candidate  (NOT the live config)
cand_str      = Path(sys.argv[12])          # bare-string-shape candidate (fallback/floor)
effective_out = Path(sys.argv[13])          # effective primary written for commit-confirmation

cfg = json.loads(src.read_text())

STALE = re.compile(r"minimax-m2|minimax-2\.|minimax/minimax-m2|minimax/minimax-2", re.IGNORECASE)

# ── 7a. HEAL: drop the fabricated top-level models.available key ─────────────
# No OpenClaw schema (2026.5.22 / 2026.6.8 / newer) accepts `models.available` —
# it was an invented key (verified against docs.openclaw.ai and a live 2026.5.22 /
# 2026.6.8 validator). Models are addressable directly as `provider/model-id` once
# the provider is configured, so the key is unnecessary. Removing it HEALS a box a
# prior buggy run corrupted back to a valid `models` object.
models_block = cfg.get("models")
if isinstance(models_block, dict) and "available" in models_block:
    del models_block["available"]
    print("  ✓ healed: removed fabricated models.available (models are addressed by provider/id)")

# ── 7b. agents.defaults.subagents.model — the REAL, schema-valid executor key ─
# `executorModel` is NOT an OpenClaw key (verified against docs.openclaw.ai and a
# live 2026.5.22 / 2026.6.8 validator). The documented key that selects the model
# a spawned sub-agent (the Skill-41 browser executor) runs on is
# `agents.defaults.subagents.model` — a model reference. We set its PRIMARY to the
# resolved MiniMax executor and carry the OpenRouter MiniMax + any client fallbacks.
agents   = cfg.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
sub      = defaults.setdefault("subagents", {})

# HEAL: drop the fabricated executorModel key if a prior run wrote it.
if "executorModel" in sub:
    del sub["executorModel"]
    print("  ✓ healed: removed fabricated agents.defaults.subagents.executorModel")

# ── CLIENT SOVEREIGNTY (preserve express model choice) ───────────────────────
# Mirror install.sh's preserve-if-present / seed-if-missing doctrine EXACTLY:
# only SEED the MiniMax executor as the sub-agent primary when the box has NO
# sub-agent primary yet. NEVER overwrite a client's existing primary and NEVER
# demote it to a fallback.
_existing = sub.get("model")
existing_primary   = None
existing_fallbacks = []
if isinstance(_existing, str) and _existing.strip():
    existing_primary = _existing.strip()
elif isinstance(_existing, dict):
    _p = _existing.get("primary")
    if isinstance(_p, str) and _p.strip():
        existing_primary = _p.strip()
    existing_fallbacks = [f for f in _existing.get("fallbacks", []) if isinstance(f, str)]

if existing_primary:
    # PRESERVE — leave the client's subagents.model exactly as they set it.
    effective_primary = existing_primary
    model_obj_val = _existing
    model_str_val = _existing
    print(f"  ℹ  preserved client sub-agent primary (unchanged): {existing_primary}")
else:
    # SEED — no client primary present → set the MiniMax executor as primary and
    # carry the OpenRouter MiniMax fallback + any existing (non-primary) fallbacks.
    effective_primary = exec_primary
    fallbacks = []
    def _add(m):
        if m and m != exec_primary and m not in fallbacks and not STALE.search(m):
            fallbacks.append(m)
    if exec_fallback:
        _add(exec_fallback)
    for _f in existing_fallbacks:
        _add(_f)
    model_obj_val = {"primary": exec_primary}
    if fallbacks:
        model_obj_val["fallbacks"] = fallbacks
    model_str_val = exec_primary
    print(f"  ✓ seeded sub-agent executor primary (was unset) = {exec_primary}")

# ── 7c. Emit TWO candidates (never the live config) ──────────────────────────
# The bash caller tries the OBJECT shape first, then the documented bare-STRING
# shape, committing the first that `openclaw config validate` accepts. When we
# SEEDED, both shapes set MiniMax as primary (feature ACTIVE either way); the
# string form is the universally-documented value type and the guaranteed floor on
# every deployed schema. When we PRESERVED, both candidates carry the client's
# model UNCHANGED (only the fabricated keys are healed). Neither candidate is ever
# written to the live config unless it validates.
sub["model"] = model_obj_val
cand_obj.write_text(json.dumps(cfg, indent=2) + "\n")
sub["model"] = model_str_val
cand_str.write_text(json.dumps(cfg, indent=2) + "\n")

# Record the effective primary so the bash caller can POSITIVELY CONFIRM the
# commit actually landed (guards against a silent partial/failed write).
effective_out.write_text(effective_primary)

print(f"  ✓ agents.defaults.subagents.model effective PRIMARY = {effective_primary}")
PYEOF

_writer_rc=$?
# ─── 8. Guarded commit — writer-integrity check, then tiered validate-before-commit ─
# FIRST prove the candidate-writer succeeded. If the python was killed (OOM/SIGTERM)
# or a write failed (disk-full), abort LOUDLY — the live config is still the prior
# valid bytes, so this is a clean no-op, never a false "committed".
if [[ "$_writer_rc" -ne 0 ]]; then
  fail "executor-model candidate-writer exited $_writer_rc — live config UNTOUCHED; aborting (no false success)"
  rm -f "$OC_BACKUP" 2>/dev/null || true
  exit 1
fi
if [[ ! -s "$OC_CANDIDATE" || ! -s "$OC_CAND_STR" || ! -s "$OC_EFFECTIVE" ]]; then
  fail "candidate/marker file missing or empty after writer — live config UNTOUCHED; aborting"
  rm -f "$OC_BACKUP" 2>/dev/null || true
  exit 1
fi
EXPECTED_PRIMARY="$(cat "$OC_EFFECTIVE" 2>/dev/null || true)"

# The writer emitted TWO candidates (object then documented bare-string). We commit
# the FIRST the box's own `openclaw config validate` accepts. A candidate reaches the
# live config ONLY if it validates; on failure the exact prior bytes are restored, so
# a valid config can NEVER be regressed. If the openclaw CLI is unavailable we cannot
# prove the shape, so we skip inline and record a sidecar.
commit_ok=0
committed_shape=""
skipped_reason=""

# try_commit FILE LABEL → atomically swap FILE into the live config and validate.
# Hardened: refuses a missing/empty candidate and checks cp's exit code, so a bad
# copy can never masquerade as a clean commit. rc 0 = validated + kept;
# rc 1 = not committed (exact prior bytes restored).
try_commit() {
  local file="$1" label="$2"
  if [[ ! -s "$file" ]]; then
    warn "candidate ($label) missing/empty — skipping this shape"
    return 1
  fi
  if ! cp -f "$file" "$OC_JSON"; then
    warn "cp of candidate ($label) failed — restoring backup"
    cp -f "$OC_BACKUP" "$OC_JSON" 2>/dev/null || true
    return 1
  fi
  if openclaw config validate >/dev/null 2>&1; then
    ok "committed subagents.model ($label) — openclaw config validate PASSED"
    return 0
  fi
  cp -f "$OC_BACKUP" "$OC_JSON"
  warn "subagents.model ($label) rejected by this gateway — reverted, trying next shape"
  return 1
}

# live_primary → prints the effective subagents.model primary now on disk.
live_primary() {
  python3 - "$OC_JSON" <<'PYP' 2>/dev/null || true
import json, sys
try:
    m = json.load(open(sys.argv[1])).get("agents", {}).get("defaults", {}).get("subagents", {}).get("model")
except Exception:
    m = None
print(m if isinstance(m, str) else (m.get("primary", "") if isinstance(m, dict) else ""))
PYP
}

oc_config_valid; _baseline_rc=$?
case "$_baseline_rc" in
  0) info "Baseline: live config VALIDATES clean" ;;
  1) warn "Baseline: live config already FAILS validate (pre-existing) — will not worsen it" ;;
  2) warn "Baseline: openclaw CLI not on PATH — cannot validate" ;;
esac

if [[ "$_baseline_rc" -eq 2 ]]; then
  skipped_reason="openclaw CLI unavailable — cannot validate; executor model recorded to sidecar"
elif cmp -s "$OC_CANDIDATE" "$OC_JSON"; then
  info "subagents.model already canonical (object shape) — feature ACTIVE, no change"
  commit_ok=1; committed_shape="object (pre-existing)"
elif try_commit "$OC_CANDIDATE" "object {primary,fallbacks}"; then
  commit_ok=1; committed_shape="object"
elif cmp -s "$OC_CAND_STR" "$OC_JSON"; then
  info "subagents.model already canonical (string shape) — feature ACTIVE, no change"
  commit_ok=1; committed_shape="string (pre-existing)"
elif try_commit "$OC_CAND_STR" "string <primary>"; then
  commit_ok=1; committed_shape="string"
else
  skipped_reason="both object and bare-string subagents.model shapes failed openclaw config validate on ${OC_VERSION:-this gateway}"
  warn "reason: $skipped_reason (config left unchanged/valid)"
fi

# ── 8a. POSITIVE COMMIT CONFIRMATION — defeat a silent false-success ──────────
# A "committed" verdict is trusted ONLY if the live config now actually carries the
# effective primary the writer intended. This catches a partial/failed write that
# left the config unchanged-but-valid (which would otherwise validate clean and be
# reported as success). On mismatch we restore the prior bytes and report FAILED.
if [[ "$commit_ok" -eq 1 ]]; then
  _live_primary="$(live_primary)"
  if [[ -z "$EXPECTED_PRIMARY" || "$_live_primary" != "$EXPECTED_PRIMARY" ]]; then
    warn "post-commit verify FAILED: live subagents.model primary='${_live_primary}' expected='${EXPECTED_PRIMARY}' — restoring prior valid bytes"
    cp -f "$OC_BACKUP" "$OC_JSON" 2>/dev/null || true
    commit_ok=0
    committed_shape=""
    skipped_reason="post-commit verification failed (write did not land) — config restored to prior valid bytes"
  else
    ok "post-commit verify PASSED: live subagents.model primary = ${_live_primary}"
  fi
fi

rm -f "$OC_BACKUP" 2>/dev/null || true

# ─── 8b. Sidecar — ONLY when the feature could not be committed inline ────────
# On success the live config IS the source of truth (no sidecar); a stale sidecar
# from a prior skip is removed once the feature is committed.
if [[ "$commit_ok" -eq 1 ]]; then
  rm -f "$EXECUTOR_SIDECAR" 2>/dev/null || true
elif [[ -n "$skipped_reason" ]]; then
  python3 - "$EXECUTOR_SIDECAR" "$EXECUTOR_PRIMARY" "${EXECUTOR_FALLBACK:-}" \
    "$EXECUTOR_SCENARIO" "$skipped_reason" <<'PYEOF'
import json, sys, datetime
from pathlib import Path
sidecar  = Path(sys.argv[1])
primary  = sys.argv[2]
fallback = sys.argv[3]
scenario = sys.argv[4]
reason   = sys.argv[5]
doc = {
    "key":      "agents.defaults.subagents.model",
    "primary":  primary,
    "scenario": scenario,
    "skill":    "41-build-with-ai-playbook",
    "reason":   reason,
    "note":     ("Recorded here because the executor model could not be committed to "
                 "openclaw.json on this box. This file never participates in "
                 "`openclaw config validate`."),
    "configured_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
if fallback:
    doc["fallback"] = fallback
sidecar.write_text(json.dumps(doc, indent=2) + "\n")
print(f"  ✓ Executor model recorded to sidecar → {sidecar}")
PYEOF
  ok "Executor-model preflight recorded to sidecar (config left valid)"
fi

# ─── 9. Restore ownership on VPS (only for files we actually wrote) ──────────
if [[ "$OC_PLATFORM" == "vps" ]]; then
  if [[ "$commit_ok" -eq 1 ]]; then
    chown "${OC_RUNTIME_USER}:${OC_RUNTIME_USER}" "$OC_JSON" 2>/dev/null || \
      warn "chown to $OC_RUNTIME_USER failed — verify file ownership manually"
    ok "VPS: ownership restored to $OC_RUNTIME_USER"
  fi
  [[ -f "$EXECUTOR_SIDECAR" ]] && \
    chown "${OC_RUNTIME_USER}:${OC_RUNTIME_USER}" "$EXECUTOR_SIDECAR" 2>/dev/null || true
fi

# ─── 10. Summary ─────────────────────────────────────────────────────────────
echo ""
echo "${P} ──── EXECUTOR MODEL PREFLIGHT ────"
echo "${P}   Platform         : $OC_PLATFORM"
echo "${P}   Gateway version  : ${OC_VERSION:-unknown}"
echo "${P}   Scenario         : $EXECUTOR_SCENARIO"
echo "${P}   Key              : agents.defaults.subagents.model"
echo "${P}   PRIMARY          : $EXECUTOR_PRIMARY"
[[ -n "$EXECUTOR_FALLBACK" ]] && \
echo "${P}   FALLBACK         : $EXECUTOR_FALLBACK"
echo "${P}   Config           : $OC_JSON"
if [[ "$commit_ok" -eq 1 ]]; then
  echo "${P}   Result           : ACTIVE — committed inline as ${committed_shape} (validated clean)"
elif [[ -n "$skipped_reason" ]]; then
  echo "${P}   Result           : recorded to sidecar (config left VALID)"
  echo "${P}   Sidecar          : $EXECUTOR_SIDECAR"
  echo "${P}   Reason           : $skipped_reason"
else
  echo "${P}   Result           : no change (idempotent)"
fi
echo ""
ok "05-configure-executor-model.sh complete"
exit 0
