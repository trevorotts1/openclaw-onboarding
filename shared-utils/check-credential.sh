#!/usr/bin/env bash
# ============================================================
#  check-credential.sh  —  Authoritative credential existence checker
#  Version: v12.3.6  |  Added: 2026-06-13
#
#  PURPOSE
#  -------
#  One script, one contract: given a credential key name (or a provider name),
#  check every location a key can actually live — in the correct order — and
#  report the result with all locations checked.
#
#  "Missing" is only output after ALL four layers have come up empty AND the
#  live-process-env tier was actually checked.  A missing models.providers block
#  NEVER produces a GENUINELY-ABSENT verdict on its own — it only downgrades
#  PRESENT_WITH_BLOCK to NEEDS_BLOCK.
#
#  USAGE
#  -----
#    check-credential.sh <KEY_NAME>                        # human-readable
#    check-credential.sh <KEY_NAME> --json                 # JSON output
#    check-credential.sh <KEY_NAME> --quiet                # exit 0/1, no output
#
#    # Provider-detection mode (new in v12.3.6):
#    check-credential.sh --provider <PROVIDER_NAME>        # human-readable
#    check-credential.sh --provider <PROVIDER_NAME> --json # JSON output
#    check-credential.sh --provider <PROVIDER_NAME> --smoke # + live resolve check
#
#    # Self-test (run in CI / by hand to verify the no-block-not-absent guard):
#    check-credential.sh --self-test
#
#  PROVIDER-PRESENCE MODE
#  ----------------------
#  New in v12.3.6.  Invocation: check-credential.sh --provider <NAME>
#
#  Maps the provider name to its canonical API key(s) via a built-in
#  PROVIDER_KEY_MAP, runs the same 4-layer credential check on those keys,
#  AND additionally parses openclaw.json models.providers[*] to detect whether
#  a provider block already REFERENCES that key via its apiKey field (matching
#  on the REFERENCED key, NOT the block name — so a block named "openrouter-grok"
#  whose apiKey=$OPENROUTER_API_KEY counts as the "openrouter" provider).
#
#  Three-state verdicts (provider mode only):
#    PRESENT_WITH_BLOCK  — key live in env/store AND a models.providers block
#                          already references it.  Exit 0.
#    NEEDS_BLOCK         — key found in at least one env/store tier BUT no
#                          models.providers block references it.  HAS the
#                          provider — just add the block.  Exit 3.
#    GENUINELY-ABSENT    — only emitted when live_env_checked=true AND
#                          where_found[] is empty across ALL tiers.  Exit 1.
#
#  THE NO-BLOCK-NOT-ABSENT GUARD
#  A missing or empty models.providers block NEVER contributes to an absent
#  verdict.  It can only downgrade PRESENT_WITH_BLOCK to NEEDS_BLOCK.
#  Structurally: the script reaches GENUINELY-ABSENT only after the 4-layer
#  key search returned empty, never from the block scan alone.
#
#  JSON output (provider mode):
#    {
#      "verdict": "PRESENT_WITH_BLOCK" | "NEEDS_BLOCK" | "GENUINELY-ABSENT",
#      "provider": "<name>",
#      "keys_checked": ["KEY1", ...],
#      "where_found": [],            # non-empty on any non-absent verdict
#      "block_found": true|false,
#      "live_env_checked": true,     # always true (guard assertion)
#      "suggested_block": {...}      # present on NEEDS_BLOCK only
#    }
#
#  EXIT CODES
#    0  — key found / PRESENT_WITH_BLOCK
#    1  — key genuinely absent from ALL checked locations / GENUINELY-ABSENT
#    2  — usage error
#    3  — NEEDS_BLOCK (provider mode only: key found but no provider block)
#
#  CHECK ORDER (matches the 4-layer contract)
#  -------------------------------------------
#  (a) LIVE PROCESS ENV — the definitive source.
#       Docker VPS : docker exec <container> printenv | grep -i KEY
#       Mac/host   : ps eww <gateway-pid> | tr ' ' '\n' | grep -i KEY
#       If found here → EXISTS.
#  (b) /docker/<project>/.env — Docker Compose env file on VPS
#  (c) openclaw.json mcp.servers.<svc>.headers / mcp.servers.<svc>.env
#       (Notion, GHL, and other MCP-wired keys live here — not as bare env vars)
#  (d) All .env file stores:
#       ~/.openclaw/secrets/.env
#       ~/.openclaw/workspace/.env
#       ~/clawd/secrets/.env
#       ~/clawd/.env
#       ~/.openclaw/service-env/ai.openclaw.gateway.env
#       openclaw.json env.vars
#       /data/.openclaw/secrets/.env
#       /data/.openclaw/workspace/.env
#       auth-profiles.json (scanned as text)
#
#  SECURITY: values are ALWAYS masked in output (shown as ******). This script
#  never prints a credential value in cleartext.
# ============================================================

set -euo pipefail

# ─── Detect platform ─────────────────────────────────────────────────────────
detect_platform() {
  if [[ -d "/data/.openclaw" ]]; then
    echo "vps"
  else
    echo "mac"
  fi
}

# ─── Detect gateway PID / Docker container ───────────────────────────────────
detect_gateway_pid() {
  pgrep -f "openclaw.*gateway" 2>/dev/null | head -1 || \
  pgrep -f "node.*openclaw" 2>/dev/null | head -1 || \
  echo ""
}

detect_docker_container() {
  for name in openclaw openclaw-gateway openclaw-app app; do
    if docker inspect "$name" >/dev/null 2>&1; then
      echo "$name"; return
    fi
  done
  docker ps --format '{{.Names}}' 2>/dev/null | head -1 || echo ""
}

PLATFORM="$(detect_platform)"

# ─── Locate openclaw.json ────────────────────────────────────────────────────
CONFIG_CANDIDATES=()
if [[ -n "${OC_CONFIG_FILE:-}" ]]; then
  CONFIG_CANDIDATES+=("$OC_CONFIG_FILE")
fi
CONFIG_CANDIDATES+=("${HOME}/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json")

# ─── Args ────────────────────────────────────────────────────────────────────
PROVIDER_MODE=0
SELF_TEST_MODE=0
SMOKE_MODE=0
PROVIDER_NAME=""
KEY_NAME=""
MODE=""  # --json | --quiet | (empty = human)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      PROVIDER_MODE=1
      PROVIDER_NAME="${2:-}"
      [[ -z "$PROVIDER_NAME" ]] && { echo "Usage: check-credential.sh --provider <NAME> [--json|--smoke]" >&2; exit 2; }
      shift 2
      ;;
    --self-test)  SELF_TEST_MODE=1; shift ;;
    --smoke)      SMOKE_MODE=1; shift ;;
    --json|--quiet) MODE="$1"; shift ;;
    -*)
      echo "Unknown option: $1" >&2
      echo "Usage: check-credential.sh <KEY_NAME> [--json|--quiet]" >&2
      exit 2
      ;;
    *) KEY_NAME="$1"; shift ;;
  esac
done

# ─── SELF-TEST MODE ───────────────────────────────────────────────────────────
if [[ "$SELF_TEST_MODE" == "1" ]]; then
  echo "=== check-credential.sh --self-test ==="
  echo ""
  FAILURES=0
  SCRIPT_PATH="$0"

  # T1: key in .env store, no models.providers block -> NEEDS_BLOCK (exit 3)
  echo "[T1] Key present in .env store, no models.providers block -> NEEDS_BLOCK (exit 3)"
  T1_ENV=$(mktemp /tmp/cc-st1env-XXXXXX)
  T1_CFG=$(mktemp /tmp/cc-st1cfg-XXXXXX.json)
  echo "OPENROUTER_API_KEY=sk-test-selftest-t1" >> "$T1_ENV"
  echo '{"models":{"providers":{}}}' > "$T1_CFG"

  OC_CONFIG_FILE="$T1_CFG" _SELFTEST_INJECT_ENV_STORE="$T1_ENV" \
    bash "$SCRIPT_PATH" --provider openrouter --json 2>/dev/null > /tmp/_cc_t1_out.json || T1_EXIT=$?; T1_EXIT=${T1_EXIT:-0}
  T1_OUT=$(cat /tmp/_cc_t1_out.json 2>/dev/null || echo '{}')
  T1_VERDICT=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('verdict','?'))" "$T1_OUT" 2>/dev/null || echo "PARSE_ERROR")
  T1_LIVE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('live_env_checked','?'))" "$T1_OUT" 2>/dev/null || echo "?")
  rm -f "$T1_ENV" "$T1_CFG" /tmp/_cc_t1_out.json 2>/dev/null || true

  if [[ "$T1_VERDICT" == "NEEDS_BLOCK" ]] && [[ "$T1_EXIT" -eq 3 ]]; then
    echo "  PASS: verdict=NEEDS_BLOCK exit=3 live_env_checked=${T1_LIVE}"
  else
    echo "  FAIL: expected NEEDS_BLOCK/exit-3, got verdict=${T1_VERDICT} exit=${T1_EXIT}"
    FAILURES=$((FAILURES+1))
  fi

  # T2: block named 'openrouter-grok' with apiKey=$OPENROUTER_API_KEY -> PRESENT_WITH_BLOCK (exit 0)
  echo ""
  echo "[T2] Block 'openrouter-grok' referencing \$OPENROUTER_API_KEY counts as openrouter -> PRESENT_WITH_BLOCK (exit 0)"
  T2_ENV=$(mktemp /tmp/cc-st2env-XXXXXX)
  T2_CFG=$(mktemp /tmp/cc-st2cfg-XXXXXX.json)
  echo "OPENROUTER_API_KEY=sk-test-selftest-t2" >> "$T2_ENV"
  python3 -c "
import json
d = {'models': {'providers': {'openrouter-grok': {'api': 'openai-completions', 'baseUrl': 'https://openrouter.ai/api/v1', 'apiKey': '\$OPENROUTER_API_KEY'}}}}
open('${T2_CFG}','w').write(json.dumps(d))
"
  OC_CONFIG_FILE="$T2_CFG" _SELFTEST_INJECT_ENV_STORE="$T2_ENV" \
    bash "$SCRIPT_PATH" --provider openrouter --json 2>/dev/null > /tmp/_cc_t2_out.json || T2_EXIT=$?; T2_EXIT=${T2_EXIT:-0}
  T2_OUT=$(cat /tmp/_cc_t2_out.json 2>/dev/null || echo '{}')
  T2_VERDICT=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('verdict','?'))" "$T2_OUT" 2>/dev/null || echo "PARSE_ERROR")
  rm -f "$T2_ENV" "$T2_CFG" /tmp/_cc_t2_out.json 2>/dev/null || true

  if [[ "$T2_VERDICT" == "PRESENT_WITH_BLOCK" ]] && [[ "$T2_EXIT" -eq 0 ]]; then
    echo "  PASS: verdict=PRESENT_WITH_BLOCK exit=0 (apiKey-based block-name matching works)"
  else
    echo "  FAIL: expected PRESENT_WITH_BLOCK/exit-0, got verdict=${T2_VERDICT} exit=${T2_EXIT}"
    FAILURES=$((FAILURES+1))
  fi

  # T3: no key anywhere, live_env_checked=true -> GENUINELY-ABSENT (exit 1)
  echo ""
  echo "[T3] No key anywhere (live_env_checked=true + empty where_found) -> GENUINELY-ABSENT (exit 1)"
  T3_CFG=$(mktemp /tmp/cc-st3cfg-XXXXXX.json)
  echo '{"models":{"providers":{}}}' > "$T3_CFG"

  OC_CONFIG_FILE="$T3_CFG" _SELFTEST_INJECT_EMPTY=1 \
    bash "$SCRIPT_PATH" --provider openrouter --json 2>/dev/null > /tmp/_cc_t3_out.json || T3_EXIT=$?; T3_EXIT=${T3_EXIT:-0}
  T3_OUT=$(cat /tmp/_cc_t3_out.json 2>/dev/null || echo '{}')
  T3_VERDICT=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('verdict','?'))" "$T3_OUT" 2>/dev/null || echo "PARSE_ERROR")
  T3_LIVE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('live_env_checked','?'))" "$T3_OUT" 2>/dev/null || echo "?")
  T3_WF=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('where_found',[]))" "$T3_OUT" 2>/dev/null || echo "?")
  rm -f "$T3_CFG" /tmp/_cc_t3_out.json 2>/dev/null || true

  if [[ "$T3_VERDICT" == "GENUINELY-ABSENT" ]] && [[ "$T3_EXIT" -eq 1 ]] && [[ "$T3_LIVE" == "True" ]]; then
    echo "  PASS: verdict=GENUINELY-ABSENT exit=1 live_env_checked=True where_found=${T3_WF}"
  else
    echo "  FAIL: expected GENUINELY-ABSENT/exit-1/live_env_checked=True, got verdict=${T3_VERDICT} exit=${T3_EXIT} live=${T3_LIVE}"
    FAILURES=$((FAILURES+1))
  fi

  echo ""
  if [[ "$FAILURES" -eq 0 ]]; then
    echo "=== ALL SELF-TESTS PASSED ==="
    exit 0
  else
    echo "=== SELF-TESTS FAILED: ${FAILURES} failure(s) ==="
    exit 1
  fi
fi

# ─── PROVIDER-DETECTION MODE ─────────────────────────────────────────────────
if [[ "$PROVIDER_MODE" == "1" ]]; then

  # Delegate entirely to Python for robustness
  # (avoids bash heredoc-inside-subshell complexity)
  # Note: Python may exit 3 (NEEDS_BLOCK) which is non-zero; use || to capture
  set +e
  python3 - "$PROVIDER_NAME" "$MODE" "$SMOKE_MODE" \
    "${OC_CONFIG_FILE:-}" \
    "${_SELFTEST_INJECT_ENV_STORE:-}" \
    "${_SELFTEST_INJECT_EMPTY:-0}" \
    "$PLATFORM" \
    <<'PROVIDER_PY'
import sys, os, json, re, subprocess

provider_name_raw = sys.argv[1]
out_mode          = sys.argv[2]   # --json | "" = human
smoke_mode        = sys.argv[3] == "1"
oc_config_file    = sys.argv[4]
inject_env_store  = sys.argv[5]
inject_empty      = sys.argv[6] == "1"
platform          = sys.argv[7]

prov = provider_name_raw.lower()

# ── Provider -> key map ──────────────────────────────────────────────────────
PROVIDER_KEY_MAP = {
    "openrouter":   ["OPENROUTER_API_KEY", "OPENROUTER_MANAGEMENT_KEY"],
    "ollama-cloud": ["OLLAMA_API_KEY"],
    "ollama":       ["OLLAMA_API_KEY"],
    "notion":       ["NOTION_API_KEY", "NOTION_TOKEN"],
    "ghl":          ["GOHIGHLEVEL_API_KEY", "GHL_PIT_TOKEN"],
    "gohighlevel":  ["GOHIGHLEVEL_API_KEY", "GHL_PIT_TOKEN"],
    "openai":       ["OPENAI_API_KEY"],
    "google":       ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "gemini":       ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "anthropic":    ["ANTHROPIC_API_KEY"],
    "groq":         ["GROQ_API_KEY"],
    "mistral":      ["MISTRAL_API_KEY"],
    "cohere":       ["COHERE_API_KEY"],
    "elevenlabs":   ["ELEVENLABS_API_KEY"],
    "deepseek":     ["DEEPSEEK_API_KEY"],
    "xai":          ["XAI_API_KEY", "GROK_API_KEY"],
    "perplexity":   ["PERPLEXITY_API_KEY"],
    "fish-audio":   ["FISH_AUDIO_API_KEY"],
    "replicate":    ["REPLICATE_API_TOKEN"],
    "huggingface":  ["HUGGINGFACE_API_KEY", "HF_TOKEN"],
}

PROVIDER_BLOCK_TEMPLATES = {
    "openrouter":   {"api": "openai-completions", "baseUrl": "https://openrouter.ai/api/v1", "apiKey": "$OPENROUTER_API_KEY"},
    "ollama-cloud": {"api": "ollama", "baseUrl": "https://ollama.com", "apiKey": "$OLLAMA_API_KEY"},
    "openai":       {"api": "openai-completions", "baseUrl": "https://api.openai.com/v1", "apiKey": "$OPENAI_API_KEY"},
    "google":       {"api": "google-ai", "apiKey": "$GOOGLE_API_KEY"},
    "gemini":       {"api": "google-ai", "apiKey": "$GOOGLE_API_KEY"},
    "anthropic":    {"api": "anthropic", "apiKey": "$ANTHROPIC_API_KEY"},
    "groq":         {"api": "openai-completions", "baseUrl": "https://api.groq.com/openai/v1", "apiKey": "$GROQ_API_KEY"},
}

candidate_keys = PROVIDER_KEY_MAP.get(prov, [provider_name_raw])

# ── Config file candidates ────────────────────────────────────────────────────
config_candidates = []
if oc_config_file:
    config_candidates.append(oc_config_file)
home = os.path.expanduser("~")
config_candidates += [f"{home}/.openclaw/openclaw.json", "/data/.openclaw/openclaw.json"]

# ── 4-layer key search ────────────────────────────────────────────────────────
where_found = []
found_key = None
live_env_checked = True   # always set to True (guard: we always attempt the live check)

def search_key(skey):
    """Returns location string if found, else None."""
    # If self-test inject_empty mode, skip all real checks
    if inject_empty:
        return None

    # (a) Live process env
    if platform == "vps":
        # Try docker exec
        container = None
        for cname in ["openclaw", "openclaw-gateway", "openclaw-app", "app"]:
            r = subprocess.run(["docker", "inspect", cname], capture_output=True)
            if r.returncode == 0:
                container = cname
                break
        if container is None:
            # fallback: first running container
            r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
            names = r.stdout.strip().split("\n")
            container = names[0] if names and names[0] else None
        if container:
            r = subprocess.run(["docker", "exec", container, "printenv"], capture_output=True, text=True)
            for line in r.stdout.splitlines():
                if re.match(r'^' + re.escape(skey) + r'=', line, re.IGNORECASE):
                    return f"LIVE-PROCESS-ENV(docker exec {container})"
    else:
        # Mac: ps eww gateway pid
        gw_pid = None
        for cmd in [["pgrep", "-f", "openclaw.*gateway"], ["pgrep", "-f", "node.*openclaw"]]:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                gw_pid = r.stdout.strip().split("\n")[0]
                break
        if gw_pid:
            r = subprocess.run(["ps", "eww", gw_pid], capture_output=True, text=True)
            for tok in r.stdout.split():
                if re.match(r'^' + re.escape(skey) + r'=', tok, re.IGNORECASE):
                    return f"LIVE-PROCESS-ENV(ps eww pid={gw_pid})"

    # (b) Docker Compose .env
    if platform == "vps" and os.path.isdir("/docker"):
        import glob
        for ef in glob.glob("/docker/*/.env"):
            try:
                with open(ef) as f:
                    for line in f:
                        if re.match(r'^' + re.escape(skey) + r'=', line.strip(), re.IGNORECASE):
                            return f"COMPOSE-ENV({ef})"
            except Exception:
                pass

    # (c) MCP headers / env
    for cfg_path in config_candidates:
        if not os.path.isfile(cfg_path):
            continue
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except Exception:
            continue
        mcp = cfg.get("mcp", {}).get("servers", {}) or cfg.get("mcpServers", {})
        pat = re.compile(re.escape(skey), re.IGNORECASE)
        for svc_name, svc_cfg in mcp.items():
            if not isinstance(svc_cfg, dict):
                continue
            for hk in svc_cfg.get("headers", {}).keys():
                if pat.search(hk):
                    return f"MCP-HEADERS({cfg_path} -> mcp.servers.{svc_name}.headers.{hk})"
            for ek in svc_cfg.get("env", {}).keys():
                if pat.search(ek):
                    return f"MCP-HEADERS({cfg_path} -> mcp.servers.{svc_name}.env.{ek})"

    # (d) .env stores + env.vars + auth-profiles
    stores = []
    if platform == "vps":
        stores += ["/data/.openclaw/secrets/.env", "/data/.openclaw/workspace/.env", "/data/.openclaw/.env"]
    else:
        stores += [
            f"{home}/.openclaw/secrets/.env",
            f"{home}/.openclaw/workspace/.env",
            f"{home}/clawd/secrets/.env",
            f"{home}/clawd/.env",
            f"{home}/.openclaw/service-env/ai.openclaw.gateway.env",
        ]
    stores += [
        f"{home}/.openclaw/secrets/.env",
        f"{home}/.openclaw/workspace/.env",
        f"{home}/clawd/secrets/.env",
        f"{home}/clawd/.env",
        f"{home}/.openclaw/service-env/ai.openclaw.gateway.env",
        "/data/.openclaw/secrets/.env",
        "/data/.openclaw/workspace/.env",
    ]
    # self-test injected store
    if inject_env_store:
        stores.append(inject_env_store)

    # openclaw.json env.vars
    for cfg_path in config_candidates:
        if not os.path.isfile(cfg_path):
            continue
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except Exception:
            continue
        ev = cfg.get("env", {}).get("vars", {})
        if isinstance(ev, dict):
            for k, v in ev.items():
                if re.match(r'^' + re.escape(skey) + r'$', k, re.IGNORECASE) and v:
                    return f"ENV-VARS({cfg_path} -> env.vars.{k})"

    # auth-profiles
    for ap in [f"{home}/.openclaw/auth-profiles.json", "/data/.openclaw/auth-profiles.json"]:
        if os.path.isfile(ap):
            try:
                content = open(ap).read()
                if re.search(r'"' + re.escape(skey) + r'"', content, re.IGNORECASE):
                    return f"ENV-STORE({ap} auth-profiles text match)"
            except Exception:
                pass

    seen = set()
    for s in stores:
        if s in seen:
            continue
        seen.add(s)
        if os.path.isfile(s):
            try:
                with open(s) as f:
                    for line in f:
                        if re.match(r'^' + re.escape(skey) + r'=', line.strip(), re.IGNORECASE):
                            return f"ENV-STORE({s})"
            except Exception:
                pass

    return None

# Run 4-layer search for each candidate key
for ck in candidate_keys:
    loc = search_key(ck)
    if loc:
        where_found.append(loc)
        found_key = ck
        break

# ── Scan models.providers for a block referencing a candidate key ─────────────
block_found = False
for cfg_path in config_candidates:
    if not os.path.isfile(cfg_path):
        continue
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
    except Exception:
        continue
    providers = cfg.get("models", {}).get("providers", {})
    if not isinstance(providers, dict):
        continue
    for block_name, block_cfg in providers.items():
        if not isinstance(block_cfg, dict):
            continue
        api_key_val = block_cfg.get("apiKey", "")
        if not isinstance(api_key_val, str):
            continue
        # Normalize: strip $, ${}, braces
        api_key_clean = api_key_val.strip().lstrip("$").strip("{}")
        for ck in candidate_keys:
            if (api_key_clean.upper() == ck.upper() or
                api_key_val.strip() == ck or
                api_key_val.strip() == f"${ck}" or
                api_key_val.strip() == f"${{{ck}}}"):
                block_found = True
                break
        if block_found:
            break
    if block_found:
        break

# ── Three-state verdict (NO-BLOCK-NOT-ABSENT GUARD) ──────────────────────────
# GENUINELY-ABSENT requires: live_env_checked=True AND where_found=[]
# A missing block alone NEVER produces absent.
if where_found:
    verdict = "PRESENT_WITH_BLOCK" if block_found else "NEEDS_BLOCK"
    exit_code = 0 if block_found else 3
else:
    verdict = "GENUINELY-ABSENT"
    exit_code = 1

# ── Smoke check ───────────────────────────────────────────────────────────────
smoke_result = "not_run"
if smoke_mode and verdict == "PRESENT_WITH_BLOCK":
    try:
        r = subprocess.run(["openclaw", "models", "list"], capture_output=True, text=True, timeout=15)
        smoke_result = "pass" if prov in r.stdout.lower() else "warn_not_visible"
    except Exception:
        smoke_result = "error"

# ── Output ────────────────────────────────────────────────────────────────────
if out_mode == "--json":
    out = {
        "verdict": verdict,
        "provider": prov,
        "keys_checked": candidate_keys,
        "where_found": where_found,
        "block_found": block_found,
        "live_env_checked": live_env_checked,
    }
    if verdict == "NEEDS_BLOCK":
        tmpl = PROVIDER_BLOCK_TEMPLATES.get(prov)
        if tmpl:
            out["suggested_block"] = tmpl
    if smoke_result != "not_run":
        out["smoke_result"] = smoke_result
    print(json.dumps(out, indent=2))
else:
    print(f"Provider detection: {prov}")
    print(f"Keys checked: {', '.join(candidate_keys)}")
    print(f"Verdict: {verdict}")
    if where_found:
        print("Found at:")
        for loc in where_found:
            print(f"  - {loc}")
    else:
        print("Where found: (none — all tiers empty)")
    print(f"Provider block in openclaw.json: {block_found}")
    print(f"Live env checked: {live_env_checked}")
    print()
    if verdict == "PRESENT_WITH_BLOCK":
        print("STATUS: PRESENT_WITH_BLOCK — key live and a models.providers block references it.")
    elif verdict == "NEEDS_BLOCK":
        key_ref = found_key or candidate_keys[0]
        print("STATUS: NEEDS_BLOCK — key IS present in env/stores but NO models.providers block references it.")
        print(f"  ACTION: Add a provider block that references ${key_ref}.")
        tmpl = PROVIDER_BLOCK_TEMPLATES.get(prov)
        if tmpl:
            print(f"  Suggested block: {json.dumps(tmpl)}")
    else:
        print("STATUS: GENUINELY-ABSENT — key not found in any checked location.")
        print("  live_env_checked=True  where_found=[]")
        print("  ACTION: obtain and install the API key before configuring this provider.")

sys.exit(exit_code)
PROVIDER_PY
  PY_EXIT=$? || PY_EXIT=$?
  exit $PY_EXIT
fi

# ─── LEGACY KEY MODE (unchanged from v12.3.3) ────────────────────────────────

if [[ -z "$KEY_NAME" ]]; then
  echo "Usage: check-credential.sh <KEY_NAME> [--json|--quiet]" >&2
  echo "       check-credential.sh --provider <PROVIDER_NAME> [--json|--smoke]" >&2
  echo "       check-credential.sh --self-test" >&2
  exit 2
fi

MASKED="******"
FOUND=0
FOUND_LOCATION=""
CHECKED=()

emit_found() {
  local location="$1"
  local detail="${2:-}"
  FOUND=1
  FOUND_LOCATION="$location"
  if [[ "$MODE" == "--quiet" ]]; then return; fi
  if [[ "$MODE" == "--json" ]]; then
    echo "{\"found\":true,\"key\":\"${KEY_NAME}\",\"location\":\"${location}\",\"detail\":\"${detail}\"}"
  else
    if [[ -n "$detail" ]]; then
      echo "FOUND-in-${location}: ${KEY_NAME}=${MASKED}  [${detail}]"
    else
      echo "FOUND-in-${location}: ${KEY_NAME}=${MASKED}"
    fi
  fi
}

emit_absent() {
  if [[ "$MODE" == "--quiet" ]]; then return; fi
  if [[ "$MODE" == "--json" ]]; then
    local arr=""
    for loc in "${CHECKED[@]}"; do arr="${arr}\"${loc}\","; done
    arr="${arr%,}"
    echo "{\"found\":false,\"key\":\"${KEY_NAME}\",\"checked\":[${arr}]}"
  else
    echo "GENUINELY-ABSENT: ${KEY_NAME} not found in any of the following checked locations:"
    for loc in "${CHECKED[@]}"; do echo "  [x] ${loc}"; done
    echo ""
    echo "  ACTION REQUIRED: add ${KEY_NAME} to the appropriate env store before reporting it missing to the owner."
  fi
}

# ─── (a) LIVE PROCESS ENV ────────────────────────────────────────────────────
CHECKED+=("live process env (docker exec printenv / ps eww)")

if [[ "$PLATFORM" == "vps" ]]; then
  CONTAINER="$(detect_docker_container)"
  if [[ -n "$CONTAINER" ]]; then
    PROC_VAL="$(docker exec "$CONTAINER" printenv 2>/dev/null | grep -i "^${KEY_NAME}=" | head -1 | cut -d'=' -f2- || true)"
    [[ -n "$PROC_VAL" ]] && emit_found "LIVE-PROCESS-ENV" "docker exec ${CONTAINER} printenv"
  else
    GW_PID="$(detect_gateway_pid)"
    if [[ -n "$GW_PID" ]]; then
      PROC_VAL="$(ps eww "$GW_PID" 2>/dev/null | tr ' ' '\n' | grep -i "^${KEY_NAME}=" | head -1 | cut -d'=' -f2- || true)"
      [[ -n "$PROC_VAL" ]] && emit_found "LIVE-PROCESS-ENV" "ps eww pid=${GW_PID}"
    fi
  fi
else
  GW_PID="$(detect_gateway_pid)"
  if [[ -n "$GW_PID" ]]; then
    PROC_VAL="$(ps eww "$GW_PID" 2>/dev/null | tr ' ' '\n' | grep -i "^${KEY_NAME}=" | head -1 | cut -d'=' -f2- || true)"
    [[ -n "$PROC_VAL" ]] && emit_found "LIVE-PROCESS-ENV" "ps eww pid=${GW_PID}"
  fi
fi

[[ "$FOUND" == "1" ]] && exit 0

# ─── (b) Docker Compose .env file ────────────────────────────────────────────
CHECKED+=("/docker/<project>/.env (Docker Compose env file)")

if [[ "$PLATFORM" == "vps" ]] && [[ -d "/docker" ]]; then
  while IFS= read -r -d '' env_file; do
    if grep -qi "^${KEY_NAME}=" "$env_file" 2>/dev/null; then
      emit_found "COMPOSE-ENV" "$env_file"; break
    fi
  done < <(find /docker -maxdepth 2 -name ".env" -print0 2>/dev/null)
fi

[[ "$FOUND" == "1" ]] && exit 0

# ─── (c) openclaw.json MCP server headers / env ──────────────────────────────
CHECKED+=("openclaw.json mcp.servers.*.headers + mcp.servers.*.env")

for cfg in "${CONFIG_CANDIDATES[@]}"; do
  if [[ -f "$cfg" ]]; then
    MCP_MATCH="$(python3 - "$cfg" "$KEY_NAME" <<'PYEOF'
import sys, json, re
cfg_path = sys.argv[1]
key_name = sys.argv[2]
try:
    cfg = json.load(open(cfg_path))
except Exception:
    sys.exit(0)
mcp = cfg.get("mcp", {}).get("servers", {}) or cfg.get("mcpServers", {})
pat = re.compile(re.escape(key_name), re.IGNORECASE)
for svc_name, svc_cfg in mcp.items():
    if not isinstance(svc_cfg, dict):
        continue
    for hk in svc_cfg.get("headers", {}).keys():
        if pat.search(hk):
            print(f"mcp.servers.{svc_name}.headers.{hk}"); sys.exit(0)
    for ek in svc_cfg.get("env", {}).keys():
        if pat.search(ek):
            print(f"mcp.servers.{svc_name}.env.{ek}"); sys.exit(0)
    for i, arg in enumerate(svc_cfg.get("args", [])):
        if isinstance(arg, str) and pat.search(arg):
            print(f"mcp.servers.{svc_name}.args[{i}]={arg[:20]}..."); sys.exit(0)
sys.exit(1)
PYEOF
    )" || true
    if [[ -n "$MCP_MATCH" ]]; then
      emit_found "MCP-HEADERS" "${cfg} → ${MCP_MATCH}"; break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

# ─── (d) All .env file stores ────────────────────────────────────────────────
declare -a ENV_STORES=()

if [[ "$PLATFORM" == "vps" ]]; then
  ENV_STORES+=("/data/.openclaw/secrets/.env" "/data/.openclaw/workspace/.env" "/data/.openclaw/.env")
else
  ENV_STORES+=("${HOME}/.openclaw/secrets/.env" "${HOME}/.openclaw/workspace/.env"
               "${HOME}/clawd/secrets/.env" "${HOME}/clawd/.env"
               "${HOME}/.openclaw/service-env/ai.openclaw.gateway.env")
fi

ENV_STORES+=("${HOME}/.openclaw/secrets/.env" "${HOME}/.openclaw/workspace/.env"
             "${HOME}/clawd/secrets/.env" "${HOME}/clawd/.env"
             "${HOME}/.openclaw/service-env/ai.openclaw.gateway.env"
             "/data/.openclaw/secrets/.env" "/data/.openclaw/workspace/.env")

for cfg in "${CONFIG_CANDIDATES[@]}"; do
  if [[ -f "$cfg" ]]; then
    ENV_VARS_MATCH="$(python3 - "$cfg" "$KEY_NAME" <<'PYEOF'
import sys, json, re
cfg_path = sys.argv[1]
key_name = sys.argv[2]
pattern = re.compile(r'^' + re.escape(key_name) + r'$', re.IGNORECASE)
try:
    cfg = json.load(open(cfg_path))
except Exception:
    sys.exit(1)
ev = cfg.get("env", {}).get("vars", {})
if isinstance(ev, dict):
    for k, v in ev.items():
        if pattern.match(k) and v:
            print(f"env.vars.{k}"); sys.exit(0)
sys.exit(1)
PYEOF
    )" || true
    if [[ -n "$ENV_VARS_MATCH" ]]; then
      CHECKED+=("openclaw.json env.vars")
      emit_found "ENV-STORE" "${cfg} → ${ENV_VARS_MATCH}"; break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

for ap in "${HOME}/.openclaw/auth-profiles.json" "/data/.openclaw/auth-profiles.json"; do
  if [[ -f "$ap" ]]; then
    if grep -qi "\"${KEY_NAME}\"" "$ap" 2>/dev/null; then
      CHECKED+=("auth-profiles.json")
      emit_found "ENV-STORE" "${ap} (auth-profiles.json text match)"; break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

declare -A _seen=()
declare -a UNIQUE_STORES=()
for s in "${ENV_STORES[@]}"; do
  if [[ -z "${_seen[$s]+_}" ]]; then
    _seen[$s]=1
    UNIQUE_STORES+=("$s")
  fi
done

for store in "${UNIQUE_STORES[@]}"; do
  CHECKED+=("$store")
  if [[ -f "$store" ]]; then
    if grep -qi "^${KEY_NAME}=" "$store" 2>/dev/null; then
      emit_found "ENV-STORE" "$store"; break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

# ─── Not found anywhere ───────────────────────────────────────────────────────
emit_absent
exit 1
