#!/usr/bin/env bash
# entry.sh — the ONLY sanctioned front door for an Avatar-Alchemist run (Skill 52).
# Fail-closed sequence:  deps -> bypass-scan (imports+egress+anthropic ids+env
# credential names) -> hash-pin -> nonce + foreman-key.
# Nothing dispatches an LLM until every leg passes and a one-time nonce +
# per-run signing key are minted. aa_director.py does NOT trust that this
# script ran — it RE-VERIFIES gate-integrity + deps + bypass-scan itself at
# dispatch (see aa_director.py's `_front_door_reverify`), so a hand-written
# nonce file alone can never skip these checks.
# Tested under both `bash -c` and `zsh -c`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
RUN_DIR="${1:-${OC_WORKSPACE:-$HOME/.avatar-alchemist}/runs/run-$(date +%Y%m%d-%H%M%S)}"

log() { printf '[entry] %s\n' "$*"; }
die() { printf '[entry][FAIL] %s\n' "$*" >&2; exit 2; }

# --- 1) deps: python3 + stdlib-only (no forbidden external runtime deps) ------
log "1/5 deps"
command -v python3 >/dev/null 2>&1 || die "python3 not found"
if grep -REl 'import[[:space:]]+(requests|openai|anthropic|httpx|aiohttp)\b' "$HERE/scripts" >/dev/null 2>&1; then
  die "a prover imports a forbidden external runtime dep (must be stdlib-only)"
fi
log "    python3 present; provers stdlib-only"

# --- 2) bypass-scan: no Anthropic model ids, no ungoverned egress -------------
log "2/5 bypass-scan"
if grep -REn 'anthropic/|claude-[0-9]|claude-sonnet|claude-opus|claude-haiku' \
     "$HERE/prompts" "$HERE"/*.json 2>/dev/null | grep -v '/anthropic|claude/i' >/dev/null; then
  die "an Anthropic/claude model id is baked into a prompt or manifest (client-path ban, G-NOANTHROPIC)"
fi
python3 "$HERE/scripts/aa_egress_gate.py" --scripts-dir "$HERE/scripts" >/dev/null \
  || die "AF-AV-EGRESS: an ungoverned egress path (n8n/Airtable/Slack/Gmail/urllib/requests POST) was found"
log "    zero Anthropic model ids in prompts/manifests; egress-clean (AF-AV-EGRESS)"

# --- 2b) env-credential-name scan: no operator/anthropic credential NAMES in
#     the live process env (NAMES only, never values — this is the LIVE half
#     of G-NOANTHROPIC's credential-name ban; aa_build_check.py's env_names
#     loop can only see what a caller reports, so this is the real enforcement
#     point where the process env is actually visible). ------------------------
log "    2b/5 env credential-name scan"
if env | cut -d= -f1 | grep -iE 'anthropic|operator|blackceo' >/dev/null 2>&1; then
  die "AF-AV-NOANTHROPIC: an operator/anthropic-named credential env var is present in this process env"
fi
log "    no operator/anthropic credential NAMES in env"

# --- 3) hash-pin: gates match their pinned sha256 (anti-lie LIVE-gate) --------
log "3/5 hash-pin"
python3 "$HERE/scripts/aa_gate_integrity_check.py" --check >/dev/null || die "gate-integrity drift — modified gate refused"
log "    gates match pinned hashes"

# --- 4) nonce + foreman-key: mint one-time front-door tokens for this run -----
log "4/5 nonce + foreman-key"
mkdir -p "$RUN_DIR"
NONCE_FILE="$RUN_DIR/.entry-nonce"
KEY_FILE="$RUN_DIR/.foreman-key"
python3 - "$NONCE_FILE" "$KEY_FILE" <<'PY'
import secrets, sys
open(sys.argv[1], "w").write(secrets.token_hex(24))   # 192-bit front-door nonce (single use)
open(sys.argv[2], "w").write(secrets.token_bytes(32).hex())  # 256-bit HMAC signing key (this run only)
PY
chmod 600 "$NONCE_FILE" "$KEY_FILE" 2>/dev/null || true
log "    nonce minted -> $NONCE_FILE"
log "    foreman signing key minted -> $KEY_FILE (never embedded in the certificate)"

# --- 5) intake gate: version/book-brand routing checked at the front door too
#     (aa_director.py enforces this again, in-process, before ANY dispatch —
#     this leg exists so a bad intake is visible at entry.sh time as well). --
log "5/5 intake gate (if intake.json is already present in RUN_DIR)"
if [ -f "$RUN_DIR/intake.json" ]; then
  BOOK_FLAG=""
  if [ -d "$HERE/../53-avatar-alchemist-book" ]; then BOOK_FLAG="--book-skill-present"; fi
  python3 "$HERE/scripts/aa_intake_gate.py" --intake "$RUN_DIR/intake.json" $BOOK_FLAG >/dev/null \
    || die "intake/version gate failed — see: python3 scripts/aa_intake_gate.py --intake '$RUN_DIR/intake.json'"
  log "    intake.json present and clears G0-INTAKE + G0-VERSION"
else
  log "    no intake.json in RUN_DIR yet — aa_director.py will refuse dispatch until one is placed there"
fi

log "READY. Dispatch the pipeline with:"
log "  python3 $HERE/scripts/aa_director.py --run-dir '$RUN_DIR' --nonce '$NONCE_FILE' --plan"
printf '%s\n' "$RUN_DIR"
