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
# section 6 only, plus the real helpers it uses (jget, envget) from wire.sh
NODE="$(command -v node)" || { echo "SKIP: node not found"; exit 0; }
{ echo 'say() { printf "COUNCIL_WIRE: %s\n" "$*"; }'
  echo "NODE='$NODE'; OC=\"\${TEST_OC:-/nonexistent}\"; P=/nonexistent"
  sed -n '/^jget() {/,/^}/p;/^envget() {/,/^}/p' "$WIRE"
  sed -n '/^# -* 6\. public origin/,/^# -* 7\. generated/p' "$WIRE" | sed '$d'
  echo 'echo "PUBLIC=[$PUBLIC] CANDIDATE=[$CANDIDATE]"'; } >"$T/sec6.sh"
FAILS=0
run() { # <name> <curl output> <curl rc> <expected PUBLIC> <expect UNVERIFIED line yes|no> [env...]
  # the candidate is baked even when the probe fails: expected CANDIDATE is always $C
  local n="$1" o="$2" rc="$3" want="$4" unv="$5"; shift 5
  local out; out="$(env PATH="$T/bin:$PATH" CC_PUBLIC_URL="https://trevor.zerohumanworkforce.com" FAKE_CURL_OUT="$o" FAKE_CURL_RC="$rc" "$@" bash "$T/sec6.sh" 2>&1)"
  local got="PUBLIC=[$want] CANDIDATE=[$C]" u=no
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
# Candidate sources that exist before the interview: no CC_PUBLIC_URL / build state.
export TEST_OC="$T/oc"; mkdir -p "$T/app" "$TEST_OC"
src() { # <name> <expected CANDIDATE> [env...]
  local n="$1" want="$2"; shift 2
  local out; out="$(env -u CC_PUBLIC_URL -u MC_TENANT_PUBLIC_URL PATH="$T/bin:$PATH" FAKE_CURL_OUT="000 " FAKE_CURL_RC=7 CC_APP_DIR="$T/app" "$@" bash "$T/sec6.sh" 2>&1)"
  case "$out" in *"CANDIDATE=[$want]"*) echo "PASS $n" ;; *) echo "FAIL $n: $out"; FAILS=$((FAILS+1)) ;; esac
}
printf 'OTHER=x\nMC_TENANT_PUBLIC_URL="https://ann.zerohumanworkforce.com"\n' >"$T/app/.env.local"
src ".env.local MC_TENANT_PUBLIC_URL" "https://ann-council.zerohumanworkforce.com"
printf 'CC_PUBLIC_URL=https://bob.zerohumanworkforce.com\nMC_TENANT_PUBLIC_URL=https://ann.zerohumanworkforce.com\n' >"$T/app/.env.local"
src ".env.local CC_PUBLIC_URL wins" "https://bob-council.zerohumanworkforce.com"
rm -f "$T/app/.env.local"
src "no source at all: no candidate" ""
printf '{"commandCenterUrl":"https://cy.zerohumanworkforce.com"}' >"$TEST_OC/.workforce-build-state.json"; mkdir -p "$TEST_OC/workspace"; mv "$TEST_OC/.workforce-build-state.json" "$TEST_OC/workspace/"
src "build-state commandCenterUrl last resort" "https://cy-council.zerohumanworkforce.com"
src "IP literal never a candidate" "" CC_PUBLIC_URL=http://203.0.113.9:3000
src "localhost never a candidate" "" CC_PUBLIC_URL=http://localhost:3000
# COUNCIL_PUBLIC_ORIGIN is the operator's direct answer, and an origin no client
# can open is refused instead of baked (the operator box carried
# https://fixed.example.com in service.json on 2026-10-29).
named() { # <name> <expected PUBLIC> <expected CANDIDATE> <none|rejected|unverified> [env...]
  local n="$1" wpub="$2" wcand="$3" wline="$4" line=no okline=0; shift 4
  local out; out="$(env PATH="$T/bin:$PATH" CC_PUBLIC_URL="https://trevor.zerohumanworkforce.com" FAKE_CURL_OUT="302 https://x.cloudflareaccess.com/login" FAKE_CURL_RC=0 "$@" bash "$T/sec6.sh" 2>&1)"
  case "$out" in *PUBLIC_ORIGIN_UNVERIFIED*) line=unverified ;; *PUBLIC_ORIGIN_REJECTED*) line=rejected ;; esac
  if [ "$wline" = none ]; then [ "$line" = no ] && okline=1; else [ "$line" = "$wline" ] && okline=1; fi
  if case "$out" in *"PUBLIC=[$wpub] CANDIDATE=[$wcand]"*) true ;; *) false ;; esac && [ "$okline" = 1 ]; then
    echo "PASS $n"
  else
    echo "FAIL $n: $out"; FAILS=$((FAILS+1))
  fi
}
named "COUNCIL_PUBLIC_ORIGIN wins over the command center host" "https://named.zerohumanworkforce.com" "https://named.zerohumanworkforce.com" none COUNCIL_PUBLIC_ORIGIN=https://named.zerohumanworkforce.com
named "a documentation host is rejected, never baked" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://fixed.example.com
named "a loopback origin is rejected, never baked" "" "" rejected COUNCIL_PUBLIC_ORIGIN=http://127.0.0.1:8787
named "a documentation host is rejected even with the probe skipped" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://fixed.example.com COUNCIL_PUBLIC_ORIGIN_SKIP_PROBE=1
# APEX documentation hosts: the reserved TLDs are fixtures at the apex too, and
# the probe does not always catch them (probe skipped, or a host that answers).
named "apex example.com is rejected" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://example.com
named "apex example.net is rejected" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://example.net
named "apex example.org is rejected" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://example.org
named "apex example is rejected" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://example
named "apex test is rejected" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://test
named "apex invalid is rejected" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://invalid
named "apex example.com is rejected even with the probe skipped" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://example.com COUNCIL_PUBLIC_ORIGIN_SKIP_PROBE=1
named "a .invalid subdomain is rejected" "" "" rejected COUNCIL_PUBLIC_ORIGIN=https://council.invalid
echo "wire-public-probe: $FAILS failed"; [ "$FAILS" = 0 ]
