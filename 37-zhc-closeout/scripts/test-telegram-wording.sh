#!/usr/bin/env bash
# test-telegram-wording.sh -- BU-71 (closes WF-090, WF-096): the celebration
# messages stop promising what is not sent.
#
# No network, no Telegram, no live OpenClaw, no live state. A stub `openclaw`
# on PATH records every message it is asked to send and answers with a real
# messageId (the script's anti-faking gate needs one); a stub `sleep` keeps the
# paced delivery instant. Every run gets its own temp HOME / OpenClaw root and
# its own ZHC_STATE_FILE.
#
# Asserts:
#   A. ZHC_VIDEO_STATUS=failed -> the recorded deferred notice says
#      "not ready yet" and never "automatically"; it goes out on slot 40 while
#      slot 4 stays OPEN (recorded send-failed, reason video-deferred).
#   B. A second run with a video present sends the real celebration video on
#      slot 4 (a recorded messageId for n=4).
#   C. With no public Command Center link, no recorded message says "just above".
#   D. No recorded message carries the media-library address ("gohighlevel"),
#      even when the state holds one and the Command Center message is sent.
#
# Exits non-zero on any failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CELEB="$SCRIPT_DIR/send-telegram-celebration.sh"

fail() { echo "  ✗ $1" >&2; exit 1; }
ok()   { echo "  ✓ $1"; }

command -v jq >/dev/null 2>&1 || fail "jq is required for this test"
[[ -f "$CELEB" ]] || fail "missing $CELEB"
bash -n "$CELEB" || fail "syntax: $CELEB"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

HOME_DIR="$WORK/home"
mkdir -p "$HOME_DIR/.openclaw/workspace"

STUB_BIN="$WORK/bin"
mkdir -p "$STUB_BIN"

# stub openclaw: record the send args (one file per message) and return a real
# messageId so send_confirmed records a delivery.
cat > "$STUB_BIN/openclaw" <<'STUB'
#!/usr/bin/env bash
rec="${TELEGRAM_STUB_RECORDS:?TELEGRAM_STUB_RECORDS not set}"
n=$(/bin/ls -1 "$rec" 2>/dev/null | wc -l | tr -d ' ')
n=$((n + 1))
printf '%s\n' "$*" > "$rec/$(printf '%04d' "$n")"
printf '{"ok":true,"messageId":"stub-%s"}\n' "$n"
STUB
chmod +x "$STUB_BIN/openclaw"

# stub sleep: the paced delivery is irrelevant to wording.
cat > "$STUB_BIN/sleep" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$STUB_BIN/sleep"

# run_celebration <records-dir> <state-file> [VAR=value ...]
run_celebration() {
  local rec="$1" state="$2"; shift 2
  mkdir -p "$rec"
  env -i HOME="$HOME_DIR" PATH="$STUB_BIN:$PATH" \
    TELEGRAM_STUB_RECORDS="$rec" \
    ZHC_STATE_FILE="$state" \
    "$@" bash "$CELEB" >/dev/null 2>&1
}

records_text() { cat "$1"/* 2>/dev/null; }

# ---------------------------------------------------------------------------
# Scenario A + B: video not ready, no public Command Center link.
# ---------------------------------------------------------------------------
STATE_A="$WORK/state-a.json"
cat > "$STATE_A" <<'JSON'
{
  "ownerChat": "123456789",
  "ownerName": "Test Owner",
  "companyName": "Test Company",
  "agentName": "Test CEO Agent",
  "closeoutStatus": "pending"
}
JSON

REC_A="$WORK/records-a"
run_celebration "$REC_A" "$STATE_A" ZHC_VIDEO_STATUS=failed
[[ -n "$(records_text "$REC_A")" ]] || fail "scenario A recorded no messages (harness broken)"

ALL_A="$(records_text "$REC_A")"

grep -qF '🎬 Your celebration video is not ready yet. Everything else below is ready to go.' <<< "$ALL_A" \
  || fail "deferred notice does not carry the exact 'not ready yet' wording"
ok "deferred video notice says 'not ready yet' (exact wording)"

if grep -qi 'automatically' <<< "$ALL_A"; then
  fail "a recorded message still promises something will arrive 'automatically'"
fi
ok "no message promises an automatic arrival"

grep -qF '🔖 Your Command Center link is not ready yet. Message me any time and I will send it as soon as it is.' <<< "$ALL_A" \
  || fail "message 7 else-branch does not carry the exact 'link is not ready yet' wording"
ok "message 7 else-branch says 'link is not ready yet' (exact wording)"

if grep -qi 'just above' <<< "$ALL_A"; then
  fail "a recorded message still points at a link 'just above' when none was sent"
fi
ok "no message says 'just above' (no public Command Center link)"

# Slot 4 must stay OPEN for the real video; the notice went out on slot 40.
[[ "$(jq -r '[.messagesDelivered // [] | .[] | select(.n == 4) | .status] | join(",")' "$STATE_A" 2>/dev/null)" == "send-failed" ]] \
  || fail "slot 4 was not left open as send-failed after the deferred notice"
[[ "$(jq -r '[.messagesDelivered // [] | .[] | select(.n == 4) | .reason] | join(",")' "$STATE_A" 2>/dev/null)" == "video-deferred" ]] \
  || fail "slot 4 send-failed record does not carry reason video-deferred"
[[ "$(jq -r '[.messagesDelivered // [] | .[] | select(.n == 40) | select(((.messageId // "") | length) > 0)] | length' "$STATE_A" 2>/dev/null)" == "1" ]] \
  || fail "the deferred notice was not delivered on slot 40"
ok "slot 4 stays open (send-failed, video-deferred) and the notice used slot 40"

# Second run: a real video is present now -> slot 4 sends.
VIDEO="$WORK/celebration.mp4"
printf 'stub video bytes\n' > "$VIDEO"
jq --arg v "$VIDEO" '.celebrationVideoLocalPath = $v' "$STATE_A" > "$STATE_A.tmp" && mv "$STATE_A.tmp" "$STATE_A" \
  || fail "could not stage the video-present state"

REC_B="$WORK/records-b"
run_celebration "$REC_B" "$STATE_A"
[[ -n "$(records_text "$REC_B")" ]] || fail "second run recorded no messages (harness broken)"
[[ "$(jq -r '[.messagesDelivered // [] | .[] | select(.n == 4) | select(((.messageId // "") | length) > 0)] | length' "$STATE_A" 2>/dev/null)" == "1" ]] \
  || fail "second run with a video present did not deliver slot 4"
ok "second run with a video present delivers the real celebration video on slot 4"

# ---------------------------------------------------------------------------
# Scenario C: media-library address in state must never reach a message.
# ---------------------------------------------------------------------------
STATE_C="$WORK/state-c.json"
cat > "$STATE_C" <<JSON
{
  "ownerChat": "123456789",
  "ownerName": "Test Owner",
  "companyName": "Test Company",
  "agentName": "Test CEO Agent",
  "commandCenterUrl": "https://dashboard.example.com",
  "ghlMediaLibraryUrl": "https://app.gohighlevel.com/v2/location/abc123/media",
  "ghlVideoPublicUrl": "https://storage.googleapis.com/msgsndr/abc123/video.mp4",
  "ghlInfographic1PublicUrl": "https://storage.googleapis.com/msgsndr/abc123/org.png",
  "ghlInfographic2PublicUrl": "https://storage.googleapis.com/msgsndr/abc123/flow.png",
  "celebrationVideoLocalPath": "$VIDEO",
  "infographic1Url": "https://storage.googleapis.com/msgsndr/abc123/org.png",
  "infographic2Url": "https://storage.googleapis.com/msgsndr/abc123/flow.png",
  "notionRootPageUrl": "https://notion.example.com/page"
}
JSON

REC_C="$WORK/records-c"
run_celebration "$REC_C" "$STATE_C"
ALL_C="$(records_text "$REC_C")"
[[ -n "$ALL_C" ]] || fail "scenario C recorded no messages (harness broken)"

# Control: the Command Center message (with the media block) really was sent, so
# the negative assertions below are not vacuous.
grep -qF 'Your celebration media is also saved in your Convert and Flow media library' <<< "$ALL_C" \
  || fail "the Command Center media block was not sent (harness broken)"

if grep -qi 'gohighlevel' <<< "$ALL_C"; then
  fail "a recorded message carries the media-library address"
fi
ok "no message carries the media-library address (gohighlevel)"

if grep -qi 'Browse them all in your account' <<< "$ALL_C"; then
  fail "a recorded message still offers the media-library 'Browse them all' line"
fi
ok "the media-library 'Browse them all' line is gone"

echo "✓ Skill 37 celebration messages promise only what is sent (deferred video and link wording; no media-library address)"
