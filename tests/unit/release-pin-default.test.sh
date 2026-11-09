#!/usr/bin/env bash
# Regression: the release-pin gate must follow latest main when NO pin is
# configured (the 2026-11-01 "enforce" default froze every box's Sunday update
# with RELEASE_PIN_UNCONFIGURED, since nothing ever writes release-pin.json),
# and must still enforce a configured pin or an explicit enforce mode.
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0
check() { # label expected-rc expected-ref
  out=$(env -i HOME="$T" PATH=/usr/bin:/bin OPENCLAW_ROOT="$T" bash -c 'source "$1"; _release_pin_require >/dev/null 2>&1; echo "$? ${RELEASE_REF:-none} ${OC_RELEASE_PIN_REASON:-ok}"' _ "$T/blk.sh")
  set -- "$1" "$2" "$3" $out
  if [ "$4" = "$2" ] && [ "$5" = "$3" ]; then echo "  PASS $1 -> rc=$4 ref=$5"; else echo "  FAIL $1 -> rc=$4 ref=$5 reason=$6 (want rc=$2 ref=$3)"; fail=1; fi
}
for f in update-skills.sh scripts/weekly-full-update.sh scripts/fleet-refresh.sh scripts/setup-weekly-update.sh; do
  echo "== $f"
  sed -n '/>>> RELEASE-PIN BEGIN/,/<<< RELEASE-PIN END/p' "$REPO/$f" > "$T/blk.sh"
  [ -s "$T/blk.sh" ] || { echo "  FAIL no RELEASE-PIN block found"; fail=1; continue; }
  mkdir -p "$T/fleet-refresh"; rm -f "$T/fleet-refresh/release-pin.json"
  check "no pin file (every client box)" 0 main
  echo '{"approved_ref":"v27.1.68"}' > "$T/fleet-refresh/release-pin.json"
  check "pin set, no mode" 0 v27.1.68
  echo '{"mode":"enforce"}' > "$T/fleet-refresh/release-pin.json"
  check "explicit enforce, no pin" 78 none
  echo '{"mode":"enforce","approved_ref":"main"}' > "$T/fleet-refresh/release-pin.json"
  check "enforce + moving main pin" 78 none
  rm -f "$T/fleet-refresh/release-pin.json"
done
exit $fail
