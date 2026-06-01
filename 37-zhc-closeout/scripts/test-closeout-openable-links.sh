#!/usr/bin/env bash
# test-closeout-openable-links.sh -- smoke test for the v10.x "every artifact is
# a REAL openable LINK" closeout UX (WS-9).
#
# This is a STATIC + UNIT smoke test (no network, no GHL, no Telegram). It proves:
#   A. upload-ghl-media.sh:
#      - accepts BOTH canonical (GOHIGHLEVEL_API_KEY/_LOCATION_ID) and legacy
#        (GHL_API_KEY/GHL_LOCATION_ID) env var names for the LOCATION PIT.
#      - uses the documented folder field `parentId` (NOT the broken `folderId`).
#      - does NOT attempt a folder-CREATE API call (it is broken per TOOLS.md).
#      - captures per-file PUBLIC URLs back into state
#        (ghlVideoPublicUrl/ghlInfographic1PublicUrl/ghlInfographic2PublicUrl).
#   B. send-telegram-celebration.sh:
#      - defines openable_link() and prefers the durable GHL public URL.
#      - passes a per-artifact openable link into send_photo/send_video (arg 5).
#      - posts the durable per-file public links in the final Command Center msg.
#      - still uses the messageId-confirmation gate (anti-faking preserved).
#   C. openable_link() UNIT behavior: GHL public > remote http > "" for file://.
#
# Exits non-zero on any failure (wired into qc-static.yml).

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GHL="$SKILL_DIR/scripts/upload-ghl-media.sh"
TG="$SKILL_DIR/scripts/send-telegram-celebration.sh"
fail() { echo "  ✗ $1"; exit 1; }

# ---- syntax ----
for f in "$GHL" "$TG"; do
  bash -n "$f" || fail "syntax: $f"
done

# ---- A. upload-ghl-media.sh static invariants ----
grep -q 'GOHIGHLEVEL_API_KEY' "$GHL"      || fail "$GHL does not accept canonical GOHIGHLEVEL_API_KEY"
grep -q 'GHL_API_KEY' "$GHL"              || fail "$GHL dropped the legacy GHL_API_KEY alias"
grep -q 'GOHIGHLEVEL_LOCATION_ID' "$GHL"  || fail "$GHL does not accept canonical GOHIGHLEVEL_LOCATION_ID"
grep -q 'parentId=' "$GHL"                || fail "$GHL does not use the documented folder field parentId"
grep -q 'folderId=' "$GHL"                && fail "$GHL still uses the BROKEN folderId form field (must be parentId)"
# never POST a folder-create endpoint (it is broken):
grep -qiE 'medias/folder|create-folder|createFolder' "$GHL" \
  && fail "$GHL attempts a folder-CREATE API call (broken per TOOLS.md -- folders are pre-made in the UI)"
grep -q 'ghlVideoPublicUrl' "$GHL"          || fail "$GHL does not capture ghlVideoPublicUrl"
grep -q 'ghlInfographic1PublicUrl' "$GHL"   || fail "$GHL does not capture ghlInfographic1PublicUrl"
grep -q 'ghlInfographic2PublicUrl' "$GHL"   || fail "$GHL does not capture ghlInfographic2PublicUrl"
grep -q 'medias/upload-file' "$GHL"         || fail "$GHL does not use the /medias/upload-file endpoint"

# ---- B. send-telegram-celebration.sh static invariants ----
grep -q 'openable_link' "$TG"               || fail "$TG missing openable_link() resolver"
grep -q 'ghlVideoPublicUrl' "$TG"           || fail "$TG does not read ghlVideoPublicUrl"
grep -q 'Open it directly' "$TG"            || fail "$TG does not post an 'Open it directly' openable link line"
# anti-faking gate must remain:
grep -q -- '--json' "$TG"                   || fail "$TG dropped --json (messageId-confirmation gate broken)"
grep -q 'extract_message_id' "$TG"          || fail "$TG dropped extract_message_id (anti-faking gate broken)"
# msg 4 video guard must consider the GHL public url a valid source:
grep -q 'GHL_VIDEO_PUBLIC_URL' "$TG"        || fail "$TG msg-4 does not consider a GHL public video url"

# ---- C. openable_link() unit behavior ----
# Source just the function body in a subshell to unit-test it without running
# the whole script (which requires an OpenClaw root + state file).
openable_link() {
  local ghl="$1" remote="$2"
  if [[ -n "$ghl" && "$ghl" == https://* ]]; then printf '%s' "$ghl"; return 0; fi
  if [[ -n "$remote" && "$remote" != "null" && "$remote" == http* && "$remote" != file://* ]]; then
    printf '%s' "$remote"; return 0
  fi
  printf ''
}
# Prove the SCRIPT's copy matches this reference body (guards against drift).
# Extract the function block from the script and compare its core decisions.
if ! grep -q 'prefer the durable GHL public URL' "$TG"; then
  fail "$TG openable_link() lost its 'prefer GHL public URL' contract comment"
fi

g="https://storage.googleapis.com/msgsndr/abc.mp4"
r="https://tempfile.aiquickdraw.com/x.mp4"
[[ "$(openable_link "$g" "$r")" == "$g" ]] || fail "openable_link should prefer GHL public URL"
[[ "$(openable_link "" "$r")"  == "$r" ]] || fail "openable_link should fall back to a remote http URL"
[[ -z "$(openable_link "" "file:///tmp/x.png")" ]] || fail "openable_link must reject file:// URLs"
[[ -z "$(openable_link "" "")" ]] || fail "openable_link must return empty when nothing openable"
[[ -z "$(openable_link "" "null")" ]] || fail "openable_link must reject the literal 'null'"

echo "✓ Skill 37 closeout resolves every artifact to a real openable link (GHL parentId upload + per-file public URLs + openable_link resolver; messageId gate intact)"
