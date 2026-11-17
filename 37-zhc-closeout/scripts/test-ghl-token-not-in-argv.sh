#!/usr/bin/env bash
# test-ghl-token-not-in-argv.sh
#
# BU-79 (WF-096) -- upload-ghl-media.sh: the LOCATION PIT must never reach a
# curl command line. Both curl calls (the PIT verify and the media upload) now
# pass their headers through a mode-600 curl --config file with -K, so the token
# lives in the file and not in argv, where any `ps`/`ps -eww` could read it.
#
# Strategy: a stub `curl` records every argument it is handed and answers the two
# calls the script makes (200 for the PIT verify, a fileId body for the upload).
# The script runs against a throwaway HOME and a throwaway state file, so nothing
# outside the temporary directory is read or written.
#
# EXIT CODES: 0 = all PASS, 1 = any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/upload-ghl-media.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }

[[ -f "$TARGET" ]] || { fail "upload-ghl-media.sh not found at $TARGET"; exit 1; }

# The script prefers /data/.openclaw when it exists. That is a live box root and
# this test never touches one, so state plainly that it cannot run here.
if [[ -d /data/.openclaw ]]; then
  printf 'SKIP: /data/.openclaw exists on this host; this test refuses to run against a live box root.\n'
  exit 0
fi

command -v jq >/dev/null 2>&1 || { fail "jq not found (the script needs it to read state)"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ARGV_FILE="$WORK/curl-argv.txt"
TOKEN="tok-123"
: > "$ARGV_FILE"

# ---- stub curl: record argv, answer the two calls -------------------------
mkdir -p "$WORK/bin"
cat > "$WORK/bin/curl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" >> "$ARGV_FILE"
printf -- '===CALL-END===\n' >> "$ARGV_FILE"
case "$*" in
  *medias/upload-file*) printf '%s' '{"fileId":"file-1","url":"https://media.example.test/inf1.png"}' ;;
  *) printf '200' ;;
esac
STUB
chmod 755 "$WORK/bin/curl"
export ARGV_FILE

# ---- throwaway OpenClaw root: workspace + a GHL skill directory ------------
mkdir -p "$WORK/home/.openclaw/workspace"
mkdir -p "$WORK/home/.openclaw/skills/29-ghl-convert-and-flow"

# ---- real local media file so there is something to upload ----------------
printf 'PNG' > "$WORK/inf1.png"

STATE_FILE="$WORK/state.json"
printf '{"ghlMediaUploaded": false, "ghlLocationId": "loc-1", "companyName": "Test Co", "infographic1LocalPath": "%s"}\n' \
  "$WORK/inf1.png" > "$STATE_FILE"

# ---- run the script ------------------------------------------------------
HOME="$WORK/home" \
PATH="$WORK/bin:$PATH" \
TMPDIR="$WORK" \
ZHC_STATE_FILE="$STATE_FILE" \
GOHIGHLEVEL_API_KEY="$TOKEN" \
GOHIGHLEVEL_LOCATION_ID="loc-1" \
ZHC_GHL_UPLOAD_MAX_ATTEMPTS=1 \
  bash "$TARGET" >/dev/null 2>"$WORK/stderr.txt"
RC=$?

# ---- assertions ----------------------------------------------------------
if [[ -f "$ARGV_FILE" ]]; then
  pass "curl was invoked"
else
  fail "curl was never invoked; the script exited $RC before any call"
fi

CALLS=0
while IFS= read -r line; do
  [[ "$line" == "===CALL-END===" ]] && CALLS=$((CALLS+1))
done < "$ARGV_FILE"
if [[ "$CALLS" -eq 2 ]]; then
  pass "both curl calls ran (2 of 2)"
else
  fail "expected 2 curl calls, recorded $CALLS"
fi

ARGV="$(cat "$ARGV_FILE")"
if [[ "$ARGV" == *"$TOKEN"* ]]; then
  fail "the token $TOKEN appears in curl's arguments"
else
  pass "the token $TOKEN does not appear in curl's arguments"
fi

K_COUNT=0
while IFS= read -r line; do
  [[ "$line" == "-K" ]] && K_COUNT=$((K_COUNT+1))
done < "$ARGV_FILE"
if [[ "$K_COUNT" -ge 1 ]]; then
  pass "curl receives -K (header config file)"
else
  fail "curl receives no -K argument"
fi
if [[ "$K_COUNT" -eq 2 ]]; then
  pass "both curl calls use -K (2 of 2)"
else
  fail "expected -K on both curl calls, saw it $K_COUNT time(s)"
fi

AUTH_ARGS=0
while IFS= read -r line; do
  [[ "$line" == "Authorization: Bearer"* ]] && AUTH_ARGS=$((AUTH_ARGS+1))
done < "$ARGV_FILE"
if [[ "$AUTH_ARGS" -eq 0 ]]; then
  pass "no Authorization header argument on any curl command line"
else
  fail "$AUTH_ARGS Authorization header argument(s) still on a curl command line"
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
