#!/usr/bin/env bash
# qc-assert-ollama-provider-platform.sh — v12.21.0
#
# STATIC QC INVARIANT: enforces the CLIENT ONBOARDING STANDARD for the Ollama
# provider, branched by box type (Mac vs VPS). This is the single-source-of-truth
# logic; scripts/qc-system-integrity.sh CHECK X.9 delegates to it.
#
# THE STANDARD (verified against docs.openclaw.ai/providers/ollama — "Cloud + Local"):
#
#   MAC CLIENT (Mac mini / Mac laptop / any macOS box):
#     The LOCAL Ollama daemon is signed in (`ollama signin` against the client's
#     OWN ollama.com account). ONE `ollama` provider points at the local daemon:
#         baseUrl  = "http://127.0.0.1:11434"
#         api      = "ollama"
#         apiKey   = "ollama-local"
#     A signed-in daemon serves BOTH local models AND :cloud models through that
#     ONE endpoint (the hybrid "Cloud + Local" flow). Local + :cloud model ids may
#     be mixed in that one provider.
#
#   VPS CLIENT (Hostinger Docker / any Linux container — no local daemon):
#     ONE `ollama` provider, CLOUD-DIRECT:
#         baseUrl  = "https://ollama.com"
#         apiKey   = "{{OLLAMA_API_KEY}}"  (the client's OWN Ollama Cloud key)
#         api      = "ollama"
#
#   ALL boxes:
#     Every :cloud-tagged model MUST carry maxTokens <= 64000 (Ollama Cloud caps
#     output at 65536; we ship 64000 for headroom). A 384k maxTokens returns HTTP
#     400 on every call and silently breaks the primary model.
#
# WHY PLATFORM-BRANCHED (corrects the pre-v12.21 VPS-only assumption):
#   The legacy rule (AGENTS.md N30) said "Client boxes do NOT run a local Ollama
#   daemon; 127.0.0.1:11434 is a HARD VIOLATION for inference." That is TRUE for
#   VPS but WRONG for Mac. A Mac client with a signed-in local daemon routes BOTH
#   local and :cloud inference through 127.0.0.1:11434 — the daemon brokers the
#   cloud calls. Forcing a Mac onto https://ollama.com discards the local-model
#   capability and the free local path. So the loopback rule is now branched:
#     - Mac  : loopback baseUrl is REQUIRED (HARD-FAIL if it is ollama.com).
#     - VPS  : loopback baseUrl is FORBIDDEN (HARD-FAIL — ECONNREFUSED, no daemon).
#
# Checks openclaw.json at the canonical location (or SMOKE_OC_CONFIG override).
# Part of the same gate family as qc-assert-provider-capability-invariants.sh
# (same exit-code contract).
#
# Exit codes:
#   0  — Ollama provider matches the platform standard (or no ollama provider
#        is configured — nothing to enforce)
#   1  — one or more invariants VIOLATED (FATAL — block the build/QC)
#
# Usage:
#   bash qc-assert-ollama-provider-platform.sh
#   bash qc-assert-ollama-provider-platform.sh --quiet
#   SMOKE_OC_CONFIG=/path/to/openclaw.json bash qc-assert-ollama-provider-platform.sh
#   OPENCLAW_PLATFORM=mac bash qc-assert-ollama-provider-platform.sh   # force platform
#
# Wired in:
#   scripts/qc-system-integrity.sh  (CHECK X.9: Ollama provider platform standard)

set -euo pipefail

QUIET=0
for _arg in "$@"; do
  [[ "$_arg" == "--quiet" ]] && QUIET=1
done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-ollama-platform] PASS  %s\n' "$*"; }
_fail() { printf '[qc-ollama-platform] FATAL %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-ollama-platform] INFO  %s\n' "$*"; }

FAILURES=0

# ─── Platform / config location ──────────────────────────────────────────────
# Detection mirrors lib-shared.sh detect_platform() and qc-system-integrity.sh:
# presence of /data/.openclaw → VPS, otherwise Mac. Overridable via
# OPENCLAW_PLATFORM (mac|vps) so the operator can force a path on an ambiguous box.

OC_CONFIG="${SMOKE_OC_CONFIG:-}"
PLATFORM="${OPENCLAW_PLATFORM:-}"

if [ -z "$OC_CONFIG" ]; then
  if [ -f /data/.openclaw/openclaw.json ]; then
    OC_CONFIG="/data/.openclaw/openclaw.json"
    [ -z "$PLATFORM" ] && PLATFORM="vps"
  elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
    OC_CONFIG="$HOME/.openclaw/openclaw.json"
    [ -z "$PLATFORM" ] && PLATFORM="mac"
  else
    _fail "cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw"
    exit 1
  fi
fi

if [ ! -f "$OC_CONFIG" ]; then
  _fail "openclaw.json not found at: $OC_CONFIG"
  exit 1
fi

# If platform still unknown (SMOKE_OC_CONFIG given, no env override), derive it
# from the config path, then fall back to uname.
if [ -z "$PLATFORM" ]; then
  case "$OC_CONFIG" in
    /data/.openclaw/*) PLATFORM="vps" ;;
    *)
      if [ "$(uname -s 2>/dev/null)" = "Darwin" ]; then PLATFORM="mac"; else PLATFORM="vps"; fi
      ;;
  esac
fi

_info "platform: $PLATFORM   config: $OC_CONFIG"

# ─── Invariant evaluation (python3, no jq dependency) ────────────────────────
# The python helper prints one VERDICT line per finding:
#   OK <code> <detail>            — pass (informational)
#   VIOLATED <code> <detail>      — hard-fail
#   SKIP <code> <detail>          — nothing to enforce (e.g. no ollama provider)
EVAL_OUT="$(OC_CONFIG="$OC_CONFIG" PLATFORM="$PLATFORM" python3 - <<'PYEOF'
import json, os, sys

cfg_path = os.environ["OC_CONFIG"]
platform = os.environ["PLATFORM"]

try:
    with open(cfg_path) as f:
        cfg = json.load(f)
except Exception as e:
    print(f"VIOLATED PARSE could not read/parse {cfg_path}: {e}")
    sys.exit(1)

providers = (cfg.get("models", {}) or {}).get("providers", {}) or {}

# The standard mandates exactly ONE ollama provider keyed "ollama". A stray
# "ollama-local" / "ollama-cloud" split is legacy drift we flag (warn-level OK,
# not fatal — but we surface it).
ollama = providers.get("ollama")
if ollama is None:
    # Some legacy boxes used a different key. Surface it, but if there is truly no
    # ollama provider at all there is nothing to enforce.
    alt = next((k for k in ("ollama-cloud", "ollama-local") if k in providers), None)
    if alt:
        print(f"OK SPLIT no canonical 'ollama' provider; found legacy '{alt}' (consider consolidating to a single 'ollama' provider)")
        ollama = providers.get(alt)
    else:
        print("SKIP NOPROVIDER no ollama provider configured — nothing to enforce")
        sys.exit(0)

base = (ollama.get("baseUrl") or ollama.get("base_url") or "").strip()
api  = (ollama.get("api") or "").strip()
key  = (ollama.get("apiKey") or ollama.get("api_key") or "").strip()

base_l = base.lower()
# M1: 0.0.0.0 is NOT treated as loopback — on VPS it must fail the same as loopback;
# on Mac 0.0.0.0 is also not the canonical signed-in-daemon address (127.0.0.1).
is_loopback = ("127.0.0.1" in base_l) or ("localhost" in base_l)
is_cloud    = "ollama.com" in base_l

# ── Invariant P1: baseUrl matches platform ────────────────────────────────
if platform == "mac":
    if is_loopback:
        print(f"OK P1 mac ollama baseUrl is local daemon ({base})")
    elif is_cloud:
        print(f"VIOLATED P1 MAC ollama provider is CLOUD-DIRECT ({base}); the standard requires the signed-in LOCAL daemon http://127.0.0.1:11434 (serves both local + :cloud). MIGRATION: sign in the local daemon (ollama signin) and repoint baseUrl to 127.0.0.1:11434.")
    elif base:
        print(f"VIOLATED P1 MAC ollama baseUrl is neither loopback nor ollama.com ({base}); expected http://127.0.0.1:11434")
    else:
        print("VIOLATED P1 MAC ollama provider has no baseUrl; expected http://127.0.0.1:11434")
else:  # vps
    if is_cloud:
        print(f"OK P1 vps ollama baseUrl is cloud-direct ({base})")
    elif is_loopback or "0.0.0.0" in base_l:
        print(f"VIOLATED P1 VPS ollama baseUrl is a loopback/any-interface address ({base}); no local daemon runs in the container → ECONNREFUSED on every call. The standard requires baseUrl https://ollama.com + the client's OLLAMA_API_KEY.")
    elif base:
        print(f"VIOLATED P1 VPS ollama baseUrl is neither ollama.com nor loopback ({base}); expected https://ollama.com")
    else:
        print("VIOLATED P1 VPS ollama provider has no baseUrl; expected https://ollama.com")

# ── Invariant P2: api type ────────────────────────────────────────────────
if api and api != "ollama":
    print(f"VIOLATED P2 ollama provider api is '{api}'; expected api: \"ollama\"")
else:
    print(f"OK P2 ollama provider api ok ({api or 'ollama (implicit)'})")

# ── Invariant P3: apiKey shape per platform ───────────────────────────────
if platform == "mac":
    if key == "ollama-local":
        print("OK P3 mac apiKey is the canonical local sentinel (ollama-local)")
    elif not key:
        print("VIOLATED P3 MAC ollama provider has no apiKey; the standard uses apiKey \"ollama-local\" for the local daemon")
    else:
        # A non-sentinel key on a signed-in local daemon is not fatal (the daemon
        # auths via ~/.ollama/id_ed25519), but the standard pins the sentinel.
        print(f"OK P3 mac apiKey is '{key}' (standard pins \"ollama-local\"; local daemon auths via ~/.ollama key regardless)")
else:  # vps
    if not key:
        print("VIOLATED P3 VPS ollama provider has no apiKey; cloud-direct requires the client's OLLAMA_API_KEY")
    elif key in ("ollama-local",):
        print("VIOLATED P3 VPS ollama apiKey is the local sentinel 'ollama-local'; cloud-direct requires the client's real OLLAMA_API_KEY")
    else:
        print(f"OK P3 vps apiKey present ({'<placeholder>' if key.startswith('{{') else '<set>'})")

# ── Invariant P4: every :cloud model caps output at <= 32768 on ALL THREE keys ──
# Lowered from 64000 -> 32768 on 2026-08-05. WHY: the output reservation is
# subtracted from the context window to get the usable PROMPT budget:
#     promptBudget = contextWindow - outputReserve      (verified in the OpenClaw
#     bundle, run/preemptive-compaction.ts -> buildPrePromptContextBudgetStatus)
# while the compaction TRIGGER is a separate formula with NO output term:
#     trigger = contextWindow - reserveTokensFloor - softThresholdTokens
# On the operator box (kimi-k2.6:cloud, 262144 window) a 65536 reserve put the
# provider wall at 196608 and the compaction trigger at 196144 -- a 464-token
# gap. A single tool result jumps that, so sessions blew past the wall before
# compaction could fire, and then compaction ITSELF was rejected by the same
# precheck: "Context overflow: prompt too large for the model (precheck)",
# 28 occurrences in one day at prompts of 212253 and 226744 tokens.
# 32768 moves the wall to 229376 -> ~33k of margin, which clears the largest
# observed overshoot (30136).
#
# ⛔ ALL THREE KEYS. OpenClaw configs carry max_tokens, maxTokens AND num_predict.
# NOTE: no apostrophes in this heredoc -- it sits inside a $( ) command
# substitution and bash tracks quotes through it even though PYEOF is quoted.
# The native Ollama path honours num_predict; the OpenAI-compatible path honours
# max_tokens. Checking only one lets the others drift and the effective cap stays
# high -- a SILENT no-op. Real drift found on the operator box 2026-08-05:
# minimax-m3 had max_tokens=32768 but num_predict=65536, and nemotron-3-super
# had max_tokens=131072 (HALF its 262144 window) while maxTokens read 65536.
CLOUD_OUTPUT_CAP = 32768
TOKEN_KEYS = ("max_tokens", "maxTokens", "num_predict")

def walk_models(obj, path):
    found = []
    if isinstance(obj, dict):
        mid = obj.get("id") or obj.get("model") or obj.get("name")
        if isinstance(mid, str) and mid.endswith(":cloud"):
            # Caps may sit on the model object or one level down in .params
            src = obj.get("params") if isinstance(obj.get("params"), dict) else obj
            vals = {k: src.get(k, obj.get(k)) for k in TOKEN_KEYS}
            found.append((path, mid, vals))
        for k, v in obj.items():
            found += walk_models(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += walk_models(v, f"{path}[{i}]")
    return found

cloud_hits = walk_models(cfg.get("models", {}), "models")
# C2/P4: a :cloud model with NO cap key at all is also a violation — the caller
# would hit the Ollama Cloud default (unbounded → HTTP 400 on long outputs).
bad_tokens = []
missing_tokens = []
for (p, m, vals) in cloud_hits:
    present = {k: v for k, v in vals.items() if isinstance(v, int)}
    if not present:
        missing_tokens.append((p, m))
        continue
    over = {k: v for k, v in present.items() if v > CLOUD_OUTPUT_CAP}
    if over:
        bad_tokens.append((p, m, over))
if bad_tokens or missing_tokens:
    for (p, m, over) in bad_tokens:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(over.items()))
        print(f"VIOLATED P4 :cloud model {m} at {p} has {detail} > {CLOUD_OUTPUT_CAP} (output reserve is subtracted from the context window; too large collapses the gap between the provider wall and the compaction trigger → 'prompt too large (precheck)')")
    for (p, m) in missing_tokens:
        print(f"VIOLATED P4 :cloud model {m} at {p} has NONE of {TOKEN_KEYS} (Ollama Cloud hard-cap is 65536; omitting these risks HTTP 400 on long outputs). Set all three to {CLOUD_OUTPUT_CAP}.")
else:
    n = len(cloud_hits)
    print(f"OK P4 all :cloud models cap output at <= {CLOUD_OUTPUT_CAP} on {'/'.join(TOKEN_KEYS)} ({n} :cloud model entr{'y' if n==1 else 'ies'} inspected)")
PYEOF
)" || { _fail "python3 evaluator failed (parse error or unexpected exit)"; exit 1; }

# ─── Report findings ─────────────────────────────────────────────────────────
while IFS= read -r line; do
  [ -z "$line" ] && continue
  verdict="${line%% *}"
  rest="${line#* }"
  case "$verdict" in
    OK)        _pass "$rest" ;;
    SKIP)      _info "$rest" ;;
    VIOLATED)  _fail "INVARIANT VIOLATED — $rest"; FAILURES=$((FAILURES+1)) ;;
    *)         _info "$line" ;;
  esac
done <<< "$EVAL_OUT"

if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES Ollama-provider platform invariant(s) violated — see lines above."
  exit 1
fi

_pass "Ollama provider matches the $PLATFORM platform standard."
exit 0
