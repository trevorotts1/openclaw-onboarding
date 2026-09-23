#!/usr/bin/env bash
# platform-detection-parity.test.sh — class G: scripts that label the platform
# must agree with the canonical helper, platform/common.sh (oc_detect_platform
# for the label, oc_set_platform_paths for the root) that install.sh and
# update-skills.sh use.
#
# THE MISMATCH: several scripts keyed the LABEL on whether /data/.openclaw
# exists, so a Linux box whose root is ~/.openclaw (native VPS, or a container
# without /data/.openclaw) was called "mac" — check-credential.sh then skipped
# its live-process / Docker env sources and reported a false "not found".
# 06-verify-agent-browser.sh did the reverse: every Linux box got root
# /data/.openclaw even when only ~/.openclaw exists.
#
# Each script's real detection block runs under a `uname` shim (Linux, Darwin)
# with HOME = a temp dir holding only ~/.openclaw. Skipped per-OS case when a
# real /data/.openclaw exists on the machine running the test.
set -uo pipefail
P="[platform-parity]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [[ -d /data/.openclaw ]]; then
  echo "$P SKIP: this machine has a real /data/.openclaw — the ~/.openclaw-only fixture cannot be built"
  exit 0
fi
mkdir -p "$TMP/home/.openclaw"

awk '/^detect_platform\(\)/{p=1} p{print} p&&/^}$/{exit}' "$ROOT/shared-utils/check-credential.sh" > "$TMP/cc.sh"
for s in u126-remediate fleet-audit-remediate; do
  awk '/^FLEET_AUDIT_VERSION=/{p=1;next} /^WORKSPACE=/{exit} p' "$ROOT/scripts/$s.sh" > "$TMP/$s.sh"
done
awk '/^OS="\$\(uname -s\)"/{p=1} p{print} p&&/^esac/{exit}' \
  "$ROOT/41-build-with-ai-playbook/scripts/06-verify-agent-browser.sh" > "$TMP/ab.sh"
for f in cc u126-remediate fleet-audit-remediate ab; do
  [[ -s "$TMP/$f.sh" ]] || { echo "$P FATAL: could not extract the detection block ($f)" >&2; exit 1; }
done

for os in Linux Darwin; do
  mkdir -p "$TMP/bin-$os"
  printf '#!/bin/sh\necho %s\n' "$os" > "$TMP/bin-$os/uname"; chmod +x "$TMP/bin-$os/uname"
  run_os() { HOME="$TMP/home" PATH="$TMP/bin-$os:$PATH" bash -c "$1" _ "${@:2}" 2>/dev/null; }

  want="$(run_os 'source "$1"; oc_detect_platform' "$ROOT/platform/common.sh")"
  want_root="$(run_os 'unset OPENCLAW_ROOT OC_ROOT OC_CONFIG OPENCLAW_PLATFORM; source "$1"; oc_set_platform_paths >/dev/null && echo "$OC_ROOT"' "$ROOT/platform/common.sh")"
  [[ -n "$want" && -n "$want_root" ]] || { fail "$os: canonical helper gave no answer"; continue; }

  got="$(run_os 'source "$1"; detect_platform' "$TMP/cc.sh")"
  [[ "$got" == "$want" ]] && pass "$os: check-credential.sh label=$got" \
    || fail "$os: check-credential.sh label=$got, canonical=$want"

  for s in u126-remediate fleet-audit-remediate; do
    got="$(run_os 'source "$1"; echo "$PLATFORM|$OC_ROOT"' "$TMP/$s.sh")"
    [[ "$got" == "$want|$want_root" ]] && pass "$os: $s.sh label|root=$got" \
      || fail "$os: $s.sh label|root=$got, canonical=$want|$want_root"
  done

  got="$(run_os 'SKILL_TAG=x; _flag_loudly() { :; }; source "$1"; echo "$PLATFORM|$OC_HOME"' "$TMP/ab.sh")"
  [[ "$got" == "$want|$want_root" ]] && pass "$os: 06-verify-agent-browser.sh label|root=$got" \
    || fail "$os: 06-verify-agent-browser.sh label|root=$got, canonical=$want|$want_root"
done

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
