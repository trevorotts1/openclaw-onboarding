#!/usr/bin/env bash
# Skill 77 wire.sh public-origin probe: a fake curl on PATH proves the candidate
# is kept only for a 302/303 to *.cloudflareaccess.com. Runs wire.sh's section 6
# in isolation (no service, no network). bash 3.2 safe.
#   bash 77-council-of-wise-elders/scripts/tests/wire-public-probe.test.sh
set -u
WIRE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)/wire.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/wpp.XXXXXX")" || exit 2
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
printf '#!/bin/sh\nprintf "%%s" "$FAKE_CURL_OUT"\n[ "${FAKE_CURL_RC:-0}" = 0 ]\n' >"$T/bin/curl"; chmod +x "$T/bin/curl"
# section 6 only, plus the helpers it uses
{ echo 'say() { printf "COUNCIL_WIRE: %s\n" "$*"; }'
  echo 'jget() { :; }; OC=/nonexistent; P=/nonexistent'
  sed -n '/^# -* 6\. public origin/,/^# -* 7\. generated/p' "$WIRE" | sed '$d'
  echo 'echo "PUBLIC=[$PUBLIC]"'; } >"$T/sec6.sh"
FAILS=0
run() { # <name> <curl output> <curl rc> <expected PUBLIC> <expect UNVERIFIED line yes|no> [env...]
  local n="$1" o="$2" rc="$3" want="$4" unv="$5"; shift 5
  local out; out="$(env PATH="$T/bin:$PATH" CC_PUBLIC_URL="https://trevor.zerohumanworkforce.com" FAKE_CURL_OUT="$o" FAKE_CURL_RC="$rc" "$@" bash "$T/sec6.sh" 2>&1)"
  local got="PUBLIC=[$want]" u=no
  case "$out" in *PUBLIC_ORIGIN_UNVERIFIED*) u=yes ;; esac
  if case "$out" in *"$got"*) true ;; *) false ;; esac && [ "$u" = "$unv" ]; then echo "PASS $n"; else echo "FAIL $n: $out"; FAILS=$((FAILS+1)); fi
}
C="https://trevor-council.zerohumanworkforce.com"
run "302 to cloudflareaccess kept" "302 https://x.cloudflareaccess.com/cdn-cgi/access/login/y" 0 "$C" no
run "303 to cloudflareaccess kept" "303 https://x.cloudflareaccess.com/login" 0 "$C" no
run "000 dropped" "000 " 7 "" yes
run "200 dropped" "200 " 0 "" yes
run "302 to non-Access host dropped" "302 https://evil.example.com/login" 0 "" yes
run "302 to lookalike dropped" "302 https://cloudflareaccess.com.evil.net/x" 0 "" yes
run "skip env keeps candidate" "000 " 7 "$C" no COUNCIL_PUBLIC_ORIGIN_SKIP_PROBE=1
echo "wire-public-probe: $FAILS failed"; [ "$FAILS" = 0 ]
