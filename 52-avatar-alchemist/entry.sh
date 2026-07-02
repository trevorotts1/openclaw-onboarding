#!/usr/bin/env bash
# entry.sh — the ONLY sanctioned front door for an Avatar-Alchemist run (Skill 52).
# Fail-closed sequence:  deps  ->  bypass-scan  ->  hash-pin  ->  nonce.
# Nothing dispatches an LLM until all four legs pass and a one-time nonce is minted.
# Tested under both `bash -c` and `zsh -c`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
RUN_DIR="${1:-${OC_WORKSPACE:-$HOME/.avatar-alchemist}/runs/run-$(date +%Y%m%d-%H%M%S)}"

log() { printf '[entry] %s\n' "$*"; }
die() { printf '[entry][FAIL] %s\n' "$*" >&2; exit 2; }

# --- 1) deps: python3 + stdlib-only (no forbidden external runtime deps) ------
log "1/4 deps"
command -v python3 >/dev/null 2>&1 || die "python3 not found"
if grep -REl 'import[[:space:]]+(requests|openai|anthropic|httpx|aiohttp)\b' "$HERE/scripts" >/dev/null 2>&1; then
  die "a prover imports a forbidden external runtime dep (must be stdlib-only)"
fi
log "    python3 present; provers stdlib-only"

# --- 2) bypass-scan: no Anthropic model ids, no ungoverned run path -----------
log "2/4 bypass-scan"
if grep -REn 'anthropic/|claude-[0-9]|claude-sonnet|claude-opus|claude-haiku' \
     "$HERE/prompts" "$HERE"/*.json 2>/dev/null | grep -v '/anthropic|claude/i' >/dev/null; then
  die "an Anthropic/claude model id is baked into a prompt or manifest (client-path ban, G-NOANTHROPIC)"
fi
log "    zero Anthropic model ids in prompts/manifests"

# --- 3) hash-pin: gates match their pinned sha256 (anti-lie LIVE-gate) --------
log "3/4 hash-pin"
python3 "$HERE/scripts/aa_gate_integrity_check.py" --check >/dev/null || die "gate-integrity drift — modified gate refused"
log "    gates match pinned hashes"

# --- 4) nonce: mint a one-time front-door token for the foreman ---------------
log "4/4 nonce"
mkdir -p "$RUN_DIR"
NONCE_FILE="$RUN_DIR/.entry-nonce"
python3 - "$NONCE_FILE" <<'PY'
import secrets, sys
open(sys.argv[1], "w").write(secrets.token_hex(24))
PY
log "    nonce minted -> $NONCE_FILE"

log "READY. Dispatch the pipeline with:"
log "  python3 $HERE/scripts/aa_director.py --run-dir '$RUN_DIR' --nonce '$NONCE_FILE' --plan"
printf '%s\n' "$RUN_DIR"
