#!/usr/bin/env bash
# verify-routing.sh G1 counts the ROLE_DISCIPLINE_V1 MARKER, not every mention of
# its name. A Lean Core pointer line ("**Full text:** ... §ROLE_DISCIPLINE_V1")
# after the marker made G1 report a false "appears 2 times -- de-dup needed" and
# fail the Command Center refresh advisory on a box with exactly one block.
set -uo pipefail
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
[ -f /data/.openclaw/openclaw.json ] && { echo "SKIP: /data/.openclaw exists on this machine"; exit 0; }
mkdir -p "$T/.openclaw/workspace"
printf '{"agents":{"defaults":{"workspace":"%s/.openclaw/workspace"}}}\n' "$T" > "$T/.openclaw/openclaw.json"
fail=0
g1() { HOME="$T" PATH="/usr/bin:/bin" bash "$HERE/scripts/verify-routing.sh" 2>&1 | grep "G1:" | grep -v "INFO"; }

printf '# A\n<!-- ROLE_DISCIPLINE_V1 -->\n## Role discipline\n**Full text:** /x/AGENTS.md §ROLE_DISCIPLINE_V1 — read it first\n' > "$T/.openclaw/workspace/AGENTS.md"
out="$(g1)"; case "$out" in *"PASS  G1"*) echo "ok: marker + pointer = one block";; *) echo "FAIL: marker + pointer: $out"; fail=1;; esac

printf '<!-- ROLE_DISCIPLINE_V1 -->\nx\n<!-- ROLE_DISCIPLINE_V1 -->\n' > "$T/.openclaw/workspace/AGENTS.md"
out="$(g1)"; case "$out" in *"appears 2 times"*) echo "ok: a real duplicate still fails";; *) echo "FAIL: duplicate: $out"; fail=1;; esac

printf '# nothing here\n' > "$T/.openclaw/workspace/AGENTS.md"
out="$(g1)"; case "$out" in *"MISSING"*) echo "ok: missing still fails";; *) echo "FAIL: missing: $out"; fail=1;; esac

exit $fail
