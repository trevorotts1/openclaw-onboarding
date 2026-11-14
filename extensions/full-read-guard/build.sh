#!/usr/bin/env bash
# Build src/*.ts to dist/*.js. Builders run this; a client box never builds
# (it receives the committed dist/). Needs a TypeScript compiler (tsc) and the
# Node type definitions. Set FRG_TYPES_ROOT to a node_modules directory that
# contains @types/node if it is not found automatically.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"
TSC="${TSC:-$(command -v tsc || true)}"
[ -n "$TSC" ] || { echo "build.sh: tsc not found (set TSC=/path/to/tsc)" >&2; exit 2; }
roots=()
[ -n "${FRG_TYPES_ROOT:-}" ] && roots+=("$FRG_TYPES_ROOT")
roots+=("$(dirname "$TSC")/../lib/node_modules/openclaw/node_modules" "$here/node_modules" "$(npm config get prefix 2>/dev/null)/lib/node_modules/openclaw/node_modules" "$(npm root -g 2>/dev/null)/openclaw/node_modules" "$(npm root -g 2>/dev/null)")
types_root=""
for r in "${roots[@]}"; do
  [ -d "$r/@types/node" ] && { types_root="$r/@types"; break; }
done
[ -n "$types_root" ] || { echo "build.sh: @types/node not found (set FRG_TYPES_ROOT)" >&2; exit 2; }
OUT="${FRG_OUT_DIR:-dist}"
rm -rf "$OUT"
"$TSC" -p tsconfig.json --outDir "$OUT" --typeRoots "$types_root"
echo "build.sh: built $(ls "$OUT"/*.js | wc -l | tr -d ' ') files into $OUT/"
