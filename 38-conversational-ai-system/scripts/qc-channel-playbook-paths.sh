#!/usr/bin/env bash
# Proves runtime/scaffolder channel-set agreement, eight-channel cardinality,
# and scaffolder output-path conventions. Does not prove runtime behavior,
# file existence, or successful playbook generation.
set -euo pipefail

unverified() {
  printf 'UNVERIFIED: %s\n' "$1" >&2
  exit 2
}

[ "$#" -eq 0 ] || unverified "arguments are not supported"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_FILE="$SKILL_ROOT/references/agents-runtime-rules.md"
SCAFFOLD_FILE="$SKILL_ROOT/scripts/12-scaffold-channel-playbooks.sh"

[ -f "$RUNTIME_FILE" ] && [ -r "$RUNTIME_FILE" ] ||
  unverified "runtime source missing or unreadable: references/agents-runtime-rules.md"
[ -f "$SCAFFOLD_FILE" ] && [ -r "$SCAFFOLD_FILE" ] ||
  unverified "scaffolder source missing or unreadable: scripts/12-scaffold-channel-playbooks.sh"

runtime_channels=()
runtime_count=0
while IFS= read -r line; do
  if [ -n "$line" ]; then
    runtime_channels+=("$line")
    runtime_count=$((runtime_count + 1))
  fi
done < <(
  grep -oE 'communication-playbooks/[a-z0-9-]+-communication\.md' "$RUNTIME_FILE" |
    sed -E 's#^communication-playbooks/##; s#-communication\.md$##' |
    sort -u || true
)

[ "$runtime_count" -gt 0 ] ||
  unverified "runtime channel extraction yielded zero channels"

array_block="$(sed -n '/^[[:space:]]*CHANNELS=([[:space:]]*$/,/^[[:space:]]*)[[:space:]]*$/p' "$SCAFFOLD_FILE")"
[ -n "$array_block" ] ||
  unverified "could not locate complete CHANNELS array"

scaffold_channels=()
scaffold_count=0
while IFS= read -r line; do
  if [ -n "$line" ]; then
    scaffold_channels+=("$line")
    scaffold_count=$((scaffold_count + 1))
  fi
done < <(
  printf '%s\n' "$array_block" |
    grep -oE '"[^"]+"' |
    tr -d '"' |
    tr '[:upper:]' '[:lower:]' |
    sort -u || true
)

[ "$scaffold_count" -gt 0 ] ||
  unverified "scaffolder channel extraction yielded zero channels"

missing="$(comm -23 \
  <(printf '%s\n' "${scaffold_channels[@]}") \
  <(printf '%s\n' "${runtime_channels[@]}") |
  tr '\n' ' ' | sed 's/ $//')"

extra="$(comm -13 \
  <(printf '%s\n' "${scaffold_channels[@]}") \
  <(printf '%s\n' "${runtime_channels[@]}") |
  tr '\n' ' ' | sed 's/ $//')"

set_mismatch=0
if [ -n "$missing" ] || [ -n "$extra" ]; then
  printf 'MISSING at runtime (scaffolder writes, runtime never reads): %s\n' "$missing"
  printf 'EXTRA at runtime (runtime reads, scaffolder never writes): %s\n' "$extra"
  set_mismatch=1
fi

path_mismatch=0
if ! grep -Eq '^[[:space:]]*OUT_DIR=.*communication-playbooks' "$SCAFFOLD_FILE"; then
  printf 'MISMATCH: scaffolder OUT_DIR must target communication-playbooks\n' >&2
  path_mismatch=1
fi

if ! grep -Fq '${ch}-communication.md' "$SCAFFOLD_FILE"; then
  printf 'MISMATCH: scaffolder must write ${ch}-communication.md paths\n' >&2
  path_mismatch=1
fi

[ "$runtime_count" -eq 8 ] ||
  { printf 'MISMATCH: runtime has %s distinct channels; expected 8\n' "$runtime_count" >&2; path_mismatch=1; }

[ "$scaffold_count" -eq 8 ] ||
  { printf 'MISMATCH: scaffolder has %s distinct channels; expected 8\n' "$scaffold_count" >&2; path_mismatch=1; }

if [ "$set_mismatch" -ne 0 ] || [ "$path_mismatch" -ne 0 ]; then
  exit 1
fi

printf 'PASS: 8 channels, scaffolder and runtime agree\n'
