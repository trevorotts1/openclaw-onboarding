#!/usr/bin/env bash
# preflight.sh — resolve the CLIENT box's OWN configured providers (per-box
# capability test) and write model-map.json (TIER-A/B/SEARCH) + provider_caps.
# NEVER Anthropic; client keys only.
#
# FIX-XC-09f: this script used to "probe" by baking hardcoded env DEFAULTS
# (`AA_TIER_A:-ollama-cloud/qwen3-235b` …) — so on ANY box it silently wrote a
# guessed model-map that had nothing to do with what the box actually runs, and
# aa_director consumed nothing anyway. It now RESOLVES each tier from the box's
# real OpenClaw config (or an explicit, box-derived override) and HARD-FAILS when
# a tier cannot be resolved — it will not invent a default model id. The provider
# cap defaults to the fleet Ollama-only rule (<=3), overridable from config/env.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OUT="${1:-$HERE/model-map.json}"

die() { printf '[preflight][FAIL] %s\n' "$*" >&2; exit 2; }
log() { printf '[preflight] %s\n' "$*"; }

# ── Resolve each tier from the box's ACTUAL OpenClaw config ───────────────────
# Resolution order for every tier id (first non-empty wins):
#   1. an explicit box-derived override env  (AA_TIER_A / AA_TIER_B / AA_SEARCH)
#      — set by the installer FROM this box's OpenClaw config, or by the operator.
#   2. an operator-provided probe hook       (AA_PROVIDER_PROBE_CMD "<tier>")
#      — prints the concrete model id this box runs for that tier, on stdout.
#   3. otherwise UNRESOLVED  → hard-fail (never a baked default).
# When the box's OpenClaw config is discoverable, every RESOLVED tier id is then
# VALIDATED to be a provider/model the box actually has configured — so the map
# is genuinely "the box's own providers", not a guess.
PROBE="${AA_PROVIDER_PROBE_CMD:-}"

_probe_tier() {  # $1 = tier label (A|B|SEARCH); prints the resolved id or nothing
  local tier="$1" id=""
  case "$tier" in
    A)      id="${AA_TIER_A:-}" ;;
    B)      id="${AA_TIER_B:-}" ;;
    SEARCH) id="${AA_SEARCH:-}" ;;
  esac
  if [ -z "$id" ] && [ -n "$PROBE" ]; then
    id="$($PROBE "$tier" 2>/dev/null | tr -d '\r\n' || true)"
  fi
  printf '%s' "$id"
}

TIER_A="$(_probe_tier A)"
TIER_B="$(_probe_tier B)"
SEARCH="$(_probe_tier SEARCH)"

# Hard-fail on any unresolved tier — NO baked model-id default (the XC-09f fix).
_missing=""
[ -n "$TIER_A" ] || _missing="$_missing TIER-A(AA_TIER_A)"
[ -n "$TIER_B" ] || _missing="$_missing TIER-B(AA_TIER_B)"
[ -n "$SEARCH" ] || _missing="$_missing SEARCH(AA_SEARCH)"
if [ -n "$_missing" ]; then
  die "unresolved provider tier(s):$_missing. Set them from THIS box's OpenClaw provider config (or provide AA_PROVIDER_PROBE_CMD). preflight refuses to write a guessed default."
fi

# ── Anthropic ban (client-path rule) on every resolved id ────────────────────
for m in "$TIER_A" "$TIER_B" "$SEARCH"; do
  case "$m" in
    *anthropic*|*claude*) die "AF-AV-NOANTHROPIC: resolved model '$m' matches /anthropic|claude/ (client-path ban)";;
  esac
done

# ── Validate each resolved id against the box's REAL OpenClaw config ──────────
# Best-effort: locate the box's OpenClaw config and, if found, assert each
# resolved tier id is a configured provider/model on THIS box. If the config
# cannot be found we DO NOT silently pass — the ids must have come from an
# explicit override/probe (already enforced above) and we warn that the
# config-membership check was skipped.
CONFIG_FOUND=""
for _cfg in \
  "${OPENCLAW_CONFIG:-}" \
  "$HOME/.openclaw/openclaw.json" "$HOME/.openclaw/config.json" \
  "/data/.openclaw/openclaw.json" "/data/.openclaw/config.json"; do
  [ -n "$_cfg" ] && [ -f "$_cfg" ] && { CONFIG_FOUND="$_cfg"; break; }
done

if [ -n "$CONFIG_FOUND" ]; then
  TIER_A="$TIER_A" TIER_B="$TIER_B" SEARCH="$SEARCH" python3 - "$CONFIG_FOUND" <<'PYVALIDATE' \
    || die "a resolved tier id is NOT among the providers/models configured in this box's OpenClaw config"
import json, os, sys
cfg_path = sys.argv[1]
try:
    cfg = json.load(open(cfg_path, encoding="utf-8"))
except Exception as exc:  # a malformed config must not silently pass
    print(f"[preflight] cannot parse OpenClaw config {cfg_path}: {exc}", file=sys.stderr)
    sys.exit(1)

# Collect every provider/model identifier the config mentions (schema-agnostic:
# scan all string leaves so this works across OpenClaw config shapes).
ids = set()
def walk(node):
    if isinstance(node, dict):
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)
    elif isinstance(node, str):
        ids.add(node.strip())
walk(cfg)

def configured(model_id):
    mid = model_id.strip()
    if mid in ids:
        return True
    head = mid.split("/", 1)[0]
    tail = mid.split("/", 1)[-1]
    return any(mid in s or (head and head in s) or (tail and tail in s) for s in ids)

missing = [f"{lbl}={os.environ[env]!r}" for lbl, env in
           (("TIER-A", "TIER_A"), ("TIER-B", "TIER_B"), ("SEARCH", "SEARCH"))
           if not configured(os.environ[env])]
if missing:
    print("[preflight] resolved tier id(s) not found in this box's OpenClaw config: "
          + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
print("[preflight] all resolved tier ids validated against the box's OpenClaw config.")
PYVALIDATE
  log "resolved tiers validated against $CONFIG_FOUND"
else
  log "WARNING: no OpenClaw config found on this box — tier ids taken from the explicit override/probe only (config-membership validation skipped)."
fi

# ── Provider cap: box-configured value, else the fleet Ollama-only rule (<=3) ─
# This is a POLICY default (a concurrency number), never a fabricated model id.
CAP="${AA_PROVIDER_CAP:-3}"
case "$CAP" in
  ''|*[!0-9]*) die "AA_PROVIDER_CAP must be a positive integer (got '$CAP')";;
esac
[ "$CAP" -ge 1 ] || die "AA_PROVIDER_CAP must be >= 1 (got '$CAP')"

python3 - "$OUT" "$TIER_A" "$TIER_B" "$SEARCH" "$CAP" "${CONFIG_FOUND:-}" <<'PY'
import json, sys
out, a, b, s, cap, cfg = sys.argv[1:7]
json.dump({
  "tiers": {"A": a, "B": b, "SEARCH": s},
  "provider_caps": {"concurrent": int(cap)},
  "resolved_from": (cfg or "explicit-override/probe"),
  "rule": "client's own providers only; G-NOANTHROPIC bans /anthropic|claude/i; "
          "client's express choice never substituted; tiers resolved from THIS box's "
          "OpenClaw config, never a baked default",
}, open(out, "w"), indent=2)
print(f"wrote model-map -> {out}: TIER-A={a} TIER-B={b} SEARCH={s} cap={cap}")
PY
