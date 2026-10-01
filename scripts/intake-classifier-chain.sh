#!/usr/bin/env bash
# intake-classifier-chain.sh — resolve WHICH model answers the intake classifier
# call (v25.2.23, order item A: the onboarding half).
#
# The intake classifier is a SEPARATE SMALL CALL carrying ONLY the policy text
# (shared-utils/intake_classifier_policy.txt) plus the owner's message
# (~2,000 tokens in). It decides question (conversation) / new work /
# existing work and does NOT pick a department. THIS script resolves only the
# chain step; it performs NO live model call and prints NO key value.
#
# CHAIN (per box; first available step wins):
#   1. openrouter-gpt-6-luna   OpenRouter `openai/gpt-6-luna`, STANDARD tier
#   2. ollama-minimax-3        Minimax 3 on Ollama Cloud — ONLY if the box has
#                              the Ollama provider configured
#   3. agnes-3-0-flash         Agnes 3.0 Flash — ONLY if the box has the Agnes
#                              provider configured
#   4. box-main                none of the three: the box keeps deciding with
#                              its own main model
# A step is skipped — never an error — on a missing key; at runtime the caller
# likewise advances on timeout or error.
#
# OUTPUT (the ONLY thing on stdout, exactly one line):
#   CHAIN_STEP=<openrouter-gpt-6-luna|ollama-minimax-3|agnes-3-0-flash|box-main> REASON=<available|missing-key|no-provider>
#   REASON=available    the named step will run (its credential is present)
#   REASON=missing-key  box-main because a provider WAS configured but its
#                       credential is missing
#   REASON=no-provider  box-main because no gated provider is configured
#
# STANCE
#   * Secrets: resolved from the SAME six stores scripts/mc-route.sh reads
#     (identical list and order; identical dotenv parse semantics), then the
#     live process env as the last resort. A resolved value only EVER flows
#     into a `[ -n ... ]` test inside this process — it is never printed,
#     logged, or placed on any command line. tests/unit/
#     test_intake_classifier_chain.py asserts no fixture value appears in the
#     output.
#   * No network. python3 runs for dotenv/config parsing only.
#   * Provider presence: read from models.providers in the openclaw.json of the
#     SAME installation shared-utils/llm_score.py selects — a
#     OC_CONFIG/OPENCLAW_ROOT/OC_ROOT pin is the ONLY root searched; unpinned,
#     /data/.openclaw then $HOME/.openclaw. A provider counts as present when a
#     provider NAME or a baseUrl names the host — never guessed from a key name.
#
# Exit: 0 whenever it can answer (a missing key is a SKIP, not a failure).
set -uo pipefail

PYTHON="${WORKFORCE_PYTHON:-python3}"

# ── Env stores: IDENTICAL list and order to scripts/mc-route.sh (_ENV_STORES).
# tests/unit/test_intake_classifier_chain.py fails if the two lists drift.
_ENV_STORES=(
  "$HOME/projects/command-center/.env.local"
  "$HOME/projects/command-center/.env"
  "/data/projects/command-center/.env.local"
  "/data/projects/command-center/.env"
  "$HOME/.openclaw/secrets/.env"
  "/data/.openclaw/secrets/.env"
)

_resolve_key() {
  # $@ = candidate key names (aliases, best first). Prints ONLY the value; prints
  # nothing when no name resolves. Same semantics as mc-route.sh's `_resolve`:
  # per store in order, skip blanks and `#` comments, strip `export `, split on
  # the FIRST `=`, strip one matching quote pair; the live process env is the
  # last resort.
  RP_KEYS="$*" "$PYTHON" - "${_ENV_STORES[@]}" <<'PYRESOLVE'
import os, sys
keys = os.environ.get("RP_KEYS", "").split()
stores = sys.argv[1:]

def parse(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    s = s[len("export "):]
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip(); v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                out[k] = v
    except Exception:
        return {}
    return out

for path in stores:
    kv = parse(path)
    for k in keys:
        if kv.get(k):
            sys.stdout.write(kv[k]); sys.exit(0)
for k in keys:
    v = os.environ.get(k)
    if v:
        sys.stdout.write(v); sys.exit(0)
PYRESOLVE
}

_provider_present() {
  # $1 = host fragment naming the provider (e.g. ollama.com). Prints yes|no only.
  # Reads models.providers from the openclaw.json of the pinned-or-resolved
  # installation (same root selection as shared-utils/llm_score.py). A missing
  # or unreadable config reads as "no" — presence is never guessed.
  OC_FRAGMENT="$1" "$PYTHON" - <<'PYPROVIDER'
import json, os, sys

fragment = os.environ.get("OC_FRAGMENT", "").lower()

def roots():
    view = os.environ
    for name in ("OC_CONFIG", "OPENCLAW_ROOT", "OC_ROOT"):
        pinned = str(view.get(name) or "").strip()
        if pinned and os.path.isabs(pinned) and pinned.rstrip(os.sep):
            return [pinned]
    home = str(view.get("HOME") or "").strip() or os.path.expanduser("~")
    return ["/data/.openclaw", os.path.join(home, ".openclaw")]

for root in roots():
    path = os.path.join(root, "openclaw.json")
    if not os.path.isfile(path):
        continue
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        continue
    providers = ((data.get("models") or {}).get("providers") or {})
    if not isinstance(providers, (dict, list)):
        continue
    entries = providers.values() if isinstance(providers, dict) else providers
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        base = str(entry.get("baseUrl") or entry.get("base_url") or "").lower()
        if fragment in base:
            print("yes"); sys.exit(0)
    if isinstance(providers, dict):
        for name in providers:
            if fragment in str(name).lower():
                print("yes"); sys.exit(0)
print("no")
PYPROVIDER
}

# ── Chain resolution. Secret values live only inside `[ -n "$( ... )" ]` tests.
CHAIN_STEP=""
CHAIN_REASON=""
_CONF_NOTE="no-provider"   # flips to missing-key once a configured step lacks its key

if [ -n "$(_resolve_key OPENROUTER_API_KEY OPENROUTER_KEY OR_API_KEY OPEN_ROUTER_API_KEY)" ]; then
  CHAIN_STEP="openrouter-gpt-6-luna"; CHAIN_REASON="available"
else
  if [ "$(_provider_present "ollama.com")" = "yes" ]; then
    if [ -n "$(_resolve_key OLLAMA_API_KEY OLLAMA_CLOUD_API_KEY OLLAMA_KEY OLLAMA_TOKEN)" ]; then
      CHAIN_STEP="ollama-minimax-3"; CHAIN_REASON="available"
    else
      _CONF_NOTE="missing-key"
    fi
  fi
  if [ -z "$CHAIN_STEP" ] && [ "$(_provider_present "agnes-ai.com")" = "yes" ]; then
    if [ -n "$(_resolve_key AGNES_API_KEY AGNES_AI_API_KEY AGNES_KEY)" ]; then
      CHAIN_STEP="agnes-3-0-flash"; CHAIN_REASON="available"
    else
      _CONF_NOTE="missing-key"
    fi
  fi
  if [ -z "$CHAIN_STEP" ]; then
    CHAIN_STEP="box-main"
    if [ "$_CONF_NOTE" = "missing-key" ]; then CHAIN_REASON="missing-key"; else CHAIN_REASON="no-provider"; fi
  fi
fi

printf 'CHAIN_STEP=%s REASON=%s\n' "$CHAIN_STEP" "$CHAIN_REASON"
