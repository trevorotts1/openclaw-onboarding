#!/usr/bin/env bash
# validate-provider-status.sh — Skill 39 (T2-32).
#
# Validates a provider-status artifact against references/provider-status-contract.md
# (`provider-status/v1`). Both the producer (02-configure-providers.sh, after
# writing) and the consumer (property-lookup.sh, before reading) call this, so the
# two halves of the skill can never drift apart again without something failing.
#
# EXIT: 0 conforms · 1 violates the contract · 2 COULD NOT RUN (absent/unreadable).
#   Exit 2 is reported by the caller as a blocker. It is never counted as a pass
#   and never converted into "no providers available" — an unresolvable or absent
#   contract artifact is a different problem from an operator who configured
#   nothing, and the two must not produce the same message.
#
# Usage: validate-provider-status.sh <path-to-status-json> [--quiet]

set -uo pipefail

FILE="${1:-}"
QUIET=0
[ "${2:-}" = "--quiet" ] && QUIET=1

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$1"; }

if [ -z "$FILE" ]; then
  echo "validate-provider-status.sh: COULD NOT RUN — no file argument" >&2
  exit 2
fi
if [ ! -f "$FILE" ]; then
  echo "validate-provider-status.sh: COULD NOT RUN — no status file at '$FILE'" >&2
  echo "  Run 02-configure-providers.sh. Do NOT treat this as 'no providers configured'." >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "validate-provider-status.sh: COULD NOT RUN — python3 not available" >&2
  exit 2
fi

python3 - "$FILE" "$QUIET" <<'PY'
import json, sys

path, quiet = sys.argv[1], sys.argv[2] == "1"
CAPS = ("geocode", "property_lookup", "street_view", "comps")
STATES = ("AVAILABLE", "HONEST_GAP")
# The pre-contract names. Naming one of these is a schema violation, not an
# unknown capability to be quietly ignored.
RETIRED = {"lookup": "property_lookup", "streetview": "street_view"}

try:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
except json.JSONDecodeError as exc:
    print(f"  x {path}: not valid JSON ({exc})")
    sys.exit(1)
except OSError as exc:
    print(f"  x {path}: COULD NOT RUN ({exc})", file=sys.stderr)
    sys.exit(2)

problems = []
if not isinstance(doc, dict):
    problems.append(f"top level is {type(doc).__name__}, expected an object")
    doc = {}

if doc.get("schema") != "provider-status/v1":
    problems.append(f"schema is {doc.get('schema')!r}, expected 'provider-status/v1'")
if not isinstance(doc.get("generated_at"), str) or not doc.get("generated_at"):
    problems.append("generated_at is missing or is not a non-empty string")

caps = doc.get("capabilities")
if not isinstance(caps, dict):
    problems.append("'capabilities' is missing or is not an object")
    caps = {}

for retired, replacement in RETIRED.items():
    if retired in caps:
        problems.append(
            f"capabilities.{retired} uses the retired name — the contract name is {replacement!r}"
        )

for cap in CAPS:
    if cap not in caps:
        problems.append(f"capabilities.{cap} is missing")
        continue
    entry = caps[cap]
    if not isinstance(entry, dict):
        problems.append(f"capabilities.{cap} is {type(entry).__name__}, expected an object")
        continue
    state = entry.get("state")
    if state not in STATES:
        problems.append(f"capabilities.{cap}.state is {state!r}, expected one of {STATES}")
    providers = entry.get("providers")
    if not isinstance(providers, list) or not all(isinstance(p, str) for p in providers):
        problems.append(f"capabilities.{cap}.providers is not an array of strings")
    elif state == "HONEST_GAP" and providers:
        problems.append(
            f"capabilities.{cap} is HONEST_GAP but lists providers {providers} — "
            "a gap has no provider"
        )
    elif state == "AVAILABLE" and not providers:
        problems.append(
            f"capabilities.{cap} is AVAILABLE but names no provider — "
            "an availability claim must say what makes it available"
        )

unknown = sorted(set(caps) - set(CAPS) - set(RETIRED))
for name in unknown:
    problems.append(f"capabilities.{name} is not a contract capability name")

# No credential value may ever reach this file. Provider NAMES only.
flat = json.dumps(doc)
for marker in ("API_KEY", "api_key", "TOKEN", "token", "secret", "SECRET"):
    if marker in flat:
        problems.append(
            f"the artifact contains {marker!r} — this file carries provider NAMES only, never keys"
        )
        break

if problems:
    print(f"  x {path}: {len(problems)} contract violation(s)")
    for prob in problems:
        print(f"      {prob}")
    sys.exit(1)
if not quiet:
    print(f"  v {path}: conforms to provider-status/v1")
sys.exit(0)
PY
