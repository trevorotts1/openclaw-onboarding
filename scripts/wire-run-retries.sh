#!/usr/bin/env bash
# scripts/wire-run-retries.sh — FLEET-FIX Area 3 / C.2–C.4
#
# Seeds `agents.defaults.runRetries.{base,perProfile,min,max}` into openclaw.json
# with SET-IF-ABSENT semantics, gated behind a PER-BOX SCHEMA GREP of the
# runtime that is actually installed on THIS box.
#
# ── C.1 SEMANTICS VERDICT (recorded; do not re-derive) ───────────────────────
# `runRetries` counts OUTER-RUN-LOOP RETRY ITERATIONS — *not* tool cycles.
# Read from the installed 2026.6.11 runtime:
#   types.openclaw-*.d.ts : "Outer run loop retry iteration boundaries."
#   runtime-schema-*.js   : "Outer run loop retry iteration boundaries for the
#                            embedded OpenClaw runner to prevent infinite
#                            execution loops during failure recovery."
# Resolver (selection-*.js):
#   resolveMaxRunRetryIterations(profileCandidateCount, cfg, agentId)
#   BASE_RUN_RETRY_ITERATIONS        = 24
#   RUN_RETRY_ITERATIONS_PER_PROFILE = 8
#   MIN_RUN_RETRY_ITERATIONS         = 32
#   MAX_RUN_RETRY_ITERATIONS         = 160
#   ceiling = clamp(base + perProfile * profileCandidateCount, min, max)
#
# ── WHY WE SEED THE RUNTIME'S OWN DEFAULTS (24/8/32/160) ─────────────────────
# Making the ceiling EXPLICIT in config is the point: it is auditable, it is
# greppable by the per-box ledger, and an operator can raise it without
# reverse-engineering the runtime. Seeding the runtime's *own* documented
# defaults is behaviour-NEUTRAL — no box changes behaviour on the day this
# lands. Inventing a higher ceiling with no evidence is exactly the guessing
# C.1 exists to prevent.
#
# ── TWO REAL SCHEMA HAZARDS THIS SCRIPT GUARDS (from AgentRunRetriesConfigSchema) ──
#   base: int().positive()   perProfile: int().nonnegative()
#   min:  int().positive()   max:        int().positive()
#   }).strict().refine(max >= min)
#
#   HAZARD 1 — .strict(): ANY extra key under runRetries makes the schema
#     validator reject the WHOLE config → `openclaw doctor --fix` reverts it →
#     reload skipped. This is the identical failure class as the v11.3.1
#     `agents.defaults.tools.exec` defect already documented in install.sh.
#     => We write ONLY the four permitted keys. Never a marker/comment key.
#
#   HAZARD 2 — .refine(max >= min): a NAIVE set-if-absent fill can CREATE an
#     invalid config out of a valid one. If an operator set `min: 200` and left
#     `max` absent (valid — both are .optional()), filling our default max=160
#     yields 160 >= 200 == FALSE → the box's entire config is now rejected.
#     => We never fill a key whose fill would violate the refine. The operator's
#        value always wins and we drop the conflicting fill instead.
#
# ── FAIL-CLOSED ──────────────────────────────────────────────────────────────
# If the runtime cannot be located, or its dist/ cannot be read, or the
# `runRetries` token is absent from it, we DO NOT WRITE. We report
# `CEILING_NOT_SUPPORTED@<version>` and skip. Writing a key an older runtime's
# strict schema does not know is precisely how you take a box's config down.
#
# Exit code is ALWAYS 0: this is advisory config seeding and must never abort an
# install. The machine-readable verdict is the `RUNRETRIES_STATUS=` line on
# stdout, one of:
#   RUNRETRIES_STATUS=SEEDED                       — one or more keys written
#   RUNRETRIES_STATUS=PRESERVED                    — all four already present; nothing written
#   RUNRETRIES_STATUS=CEILING_NOT_SUPPORTED@<ver>  — runtime lacks the key; skipped
#   RUNRETRIES_STATUS=CONFLICT_SKIPPED             — runRetries present but not an object; untouched
#   RUNRETRIES_STATUS=NO_CONFIG                    — openclaw.json absent; nothing to do
#
# Env overrides (used by tests/unit/run-retries-ceiling-wiring.test.sh):
#   OC_JSON         — path to openclaw.json
#   OC_RUNTIME_DIR  — path to the installed openclaw package dir (has package.json + dist/)

set -uo pipefail

OC_JSON="${OC_JSON:-$HOME/.openclaw/openclaw.json}"

# ---------------------------------------------------------------------------
# Resolve the openclaw runtime package dir actually installed on THIS box.
# ---------------------------------------------------------------------------
resolve_runtime_dir() {
    # Explicit override wins (fixtures / non-standard installs).
    if [ -n "${OC_RUNTIME_DIR:-}" ]; then
        printf '%s\n' "$OC_RUNTIME_DIR"
        return 0
    fi

    # Preferred: ask node to resolve the real package location.
    local d
    d="$(node -e 'try{const p=require.resolve("openclaw/package.json");console.log(require("path").dirname(p))}catch(e){}' 2>/dev/null)"
    if [ -n "$d" ] && [ -d "$d" ]; then
        printf '%s\n' "$d"
        return 0
    fi

    # Fallback: global npm root.
    local root
    root="$(npm root -g 2>/dev/null)"
    if [ -n "$root" ] && [ -d "$root/openclaw" ]; then
        printf '%s\n' "$root/openclaw"
        return 0
    fi

    # Fallback: follow the `openclaw` shim on PATH back to its package dir.
    local bin real
    bin="$(command -v openclaw 2>/dev/null)"
    if [ -n "$bin" ]; then
        real="$(cd "$(dirname "$bin")" 2>/dev/null && pwd)"
        # npm bin shim -> ../lib/node_modules/openclaw
        if [ -d "$real/../lib/node_modules/openclaw" ]; then
            (cd "$real/../lib/node_modules/openclaw" && pwd)
            return 0
        fi
    fi

    return 1
}

# Version of the runtime we ACTUALLY inspected — read from that same package.json,
# never from a stray `openclaw --version` that might resolve elsewhere. The tag in
# CEILING_NOT_SUPPORTED@<version> must describe the runtime that was grepped.
runtime_version() {
    local dir="$1" v=""
    if [ -n "$dir" ] && [ -f "$dir/package.json" ]; then
        v="$(node -e "try{console.log(require('$dir/package.json').version||'')}catch(e){}" 2>/dev/null)"
    fi
    [ -n "$v" ] || v="$(openclaw --version 2>/dev/null | head -1 | tr -d '[:space:]')"
    [ -n "$v" ] || v="unknown"
    printf '%s\n' "$v"
}

# ---------------------------------------------------------------------------
# C.3/C.4 — PER-BOX SCHEMA GREP.
# The `runRetries` token must be present in the installed runtime's dist/.
# dist filenames are content-hashed per build (selection-CVIPXpKT.js etc), so we
# grep the TREE, never a pinned filename.
# ---------------------------------------------------------------------------
runtime_supports_runretries() {
    local dir="$1"
    [ -n "$dir" ] || return 1
    [ -d "$dir/dist" ] || return 1
    grep -rq "runRetries" "$dir/dist" 2>/dev/null
}

RUNTIME_DIR="$(resolve_runtime_dir || true)"
VERSION="$(runtime_version "${RUNTIME_DIR:-}")"

if ! runtime_supports_runretries "${RUNTIME_DIR:-}"; then
    echo "  ⚠️  runRetries ceiling NOT supported by the runtime installed on this box."
    echo "      runtime dir : ${RUNTIME_DIR:-<unresolved>}"
    echo "      version     : ${VERSION}"
    echo "      Skipping the seed — writing a key this runtime's strict schema does not"
    echo "      know would get the whole config rejected. Upgrade the runtime, then re-run."
    echo "RUNRETRIES_STATUS=CEILING_NOT_SUPPORTED@${VERSION}"
    exit 0
fi

if [ ! -f "$OC_JSON" ]; then
    echo "  ℹ️  $OC_JSON does not exist yet — runRetries seed deferred."
    echo "RUNRETRIES_STATUS=NO_CONFIG"
    exit 0
fi

echo "  ✓ runtime ${VERSION} supports agents.defaults.runRetries (schema-grep hit in ${RUNTIME_DIR}/dist)"

OC_JSON="$OC_JSON" OC_RUNTIME_VERSION="$VERSION" python3 <<'PYEOF'
import json, os, sys

path    = os.environ["OC_JSON"]
version = os.environ.get("OC_RUNTIME_VERSION", "unknown")

# The runtime's OWN documented defaults. Behaviour-neutral to seed.
# ONLY these four keys may ever be written: AgentRunRetriesConfigSchema is
# .strict() and rejects the entire config on any extra key.
DEFAULTS = [
    ("base",        24),   # BASE_RUN_RETRY_ITERATIONS
    ("perProfile",   8),   # RUN_RETRY_ITERATIONS_PER_PROFILE
    ("min",         32),   # MIN_RUN_RETRY_ITERATIONS
    ("max",        160),   # MAX_RUN_RETRY_ITERATIONS
]
ALLOWED = {k for k, _ in DEFAULTS}

try:
    with open(path) as f:
        cfg = json.load(f)
except (OSError, ValueError) as e:
    print(f"  ⚠️  could not read {path} ({e}) — runRetries seed skipped")
    print("RUNRETRIES_STATUS=NO_CONFIG")
    sys.exit(0)

agents   = cfg.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
existing = defaults.get("runRetries", None)

# runRetries present but NOT an object → someone/something else owns this key.
# Never coerce it. Report and leave it exactly as-is.
if existing is not None and not isinstance(existing, dict):
    print(f"  ⚠️  agents.defaults.runRetries is {type(existing).__name__}, not an object — left untouched.")
    print("RUNRETRIES_STATUS=CONFLICT_SKIPPED")
    sys.exit(0)

block = dict(existing) if isinstance(existing, dict) else {}

# ── SET-IF-ABSENT ────────────────────────────────────────────────────────────
# Per-subkey. Filling an ABSENT sibling is not overwriting; an operator value
# that EXISTS is never touched, at any key, ever.
filled, preserved = [], []
for key, val in DEFAULTS:
    if key in block:
        preserved.append(f"{key}={block[key]}")
    else:
        block[key] = val
        filled.append(key)

# ── HAZARD 2 GUARD — .refine(max >= min) ─────────────────────────────────────
# A fill must never turn a VALID operator config into an INVALID one.
# If our default fill contradicts an operator-set sibling, drop OUR fill.
# The operator's value always wins.
def violates(b):
    return "min" in b and "max" in b and b["max"] < b["min"]

dropped = []
if violates(block):
    # Only a key WE filled may be dropped — never an operator's.
    for key in ("max", "min"):
        if key in filled and violates(block):
            del block[key]
            filled.remove(key)
            dropped.append(key)
    if violates(block):
        # Both were operator-set and already contradict each other. Their config
        # was invalid before we arrived. Not ours to silently "fix".
        print("  ⚠️  operator-set runRetries already violates max >= min — left untouched.")
        print("RUNRETRIES_STATUS=CONFLICT_SKIPPED")
        sys.exit(0)

# Defensive: .strict() means an unknown key rejects the whole config. If some
# other writer left a stray key in there, we must not be the one who ships it
# back to disk — bail rather than write a config we know the validator kills.
stray = sorted(set(block) - ALLOWED)
if stray:
    print(f"  ⚠️  unknown key(s) under runRetries {stray} — schema is .strict(); left untouched.")
    print("RUNRETRIES_STATUS=CONFLICT_SKIPPED")
    sys.exit(0)

if not filled:
    for p in preserved:
        print(f"  ℹ️  runRetries.{p} preserved (operator-set)")
    print("  ℹ️  agents.defaults.runRetries fully present — nothing to seed.")
    print("RUNRETRIES_STATUS=PRESERVED")
    sys.exit(0)

defaults["runRetries"] = block
agents["defaults"] = defaults
cfg["agents"] = agents

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)

for p in preserved:
    print(f"  ℹ️  runRetries.{p} preserved (operator-set, NOT overwritten)")
for key in filled:
    print(f"  ✓ runRetries.{key} → {block[key]} (seeded, was absent)")
for key in dropped:
    print(f"  ⚠️  runRetries.{key} fill DROPPED — would have violated max >= min against an operator-set value")

ceiling_lo = block["base"] + block["perProfile"] * 0
print(f"  ✓ ceiling = clamp(base + perProfile*profiles, min, max) "
      f"= clamp({block['base']}+{block['perProfile']}*n, {block['min']}, {block['max']}) "
      f"→ {max(ceiling_lo, block['min'])}..{block['max']} outer-run-loop retry iterations")
print("RUNRETRIES_STATUS=SEEDED")
PYEOF

exit 0
