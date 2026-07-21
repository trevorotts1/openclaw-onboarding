#!/usr/bin/env bash
# Regression suite for the podcast engine's silent-failure paths (T0-19, T0-20,
# T0-22). Each was a place the engine continued past a genuine error and reported
# success.
#
#   T0-19 — podbean_publish.sh's isolation guard had exactly ONE hard stop (the
#     configured channel not appearing on the account) and THREE paths that
#     logged a warning and carried on holding the ACCOUNT-WIDE token: the channel
#     listing call failing, the identifier list parsing empty, and the
#     scoped-token request failing or returning nothing. On a shared account
#     hosting several channels, any of the three could place a client-facing
#     episode on a channel that was never proven to be the target.
#
#   T0-20 — generate_podcast_audio.sh ran the EBU R128 measurement with `|| true`
#     and treated an unparseable summary as a warning, then logged
#     "SUCCESS, mastered audio verified" and exited 0. An UNMEASURED master was
#     released to a client feed with a success record behind it.
#
#   T0-22 — podcast_state.py could not tell "no ledger configured" from "the
#     linkage is broken". Both returned None, no warning was emitted, and the
#     advance reported success while the atomic-claim record was never updated.
#
# Hermetic: a fake `curl` on PATH that answers from a scripted table (no network,
# no Podbean account, no client data), a scratch HOME/TMPDIR, and a temp SQLite
# database. Nothing outside the temp directory is read or written.
#
# Run: bash tests/unit/podcast-engine-fail-closed.test.sh

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/58-podcast-production-engine/scripts"
PUBLISH="$SCRIPTS/podbean_publish.sh"
AUDIO_SH="$SCRIPTS/generate_podcast_audio.sh"
STATE_PY="$SCRIPTS/podcast_state.py"
for f in "$PUBLISH" "$AUDIO_SH" "$STATE_PY"; do
  [ -f "$f" ] || { echo "FATAL: missing $f" >&2; exit 1; }
done

PASS=0; FAIL=0
ok()   { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/podcast-suite.XXXXXX")"
trap 'rm -rf "$ROOT"' EXIT

# ── fake curl ─────────────────────────────────────────────────────────────────
# podbean_publish.sh invokes `curl -K <(cfg_lines ...) ... -w $'\n%{http_code}'`,
# so the URL lives inside the config file, not argv. The double reads the config,
# matches the url against a scripted table in $CURL_SCRIPT (one `pattern|code|body`
# per line, first match wins) and emits body, newline, status — exactly the shape
# http_request() parses.
mkfakecurl() {
  local bindir="$1"
  mkdir -p "$bindir"
  cat > "$bindir/curl" <<'FAKE'
#!/usr/bin/env bash
cfg=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-K" ]; then cfg="$a"; fi
  prev="$a"
done
url=""
if [ -n "$cfg" ] && [ -r "$cfg" ]; then
  url="$(sed -n 's/^url = "\(.*\)"$/\1/p' "$cfg" | head -1)"
fi
printf '%s\n' "$url" >> "${CURL_CALLLOG:-/dev/null}"
code=200
body='{}'
if [ -n "${CURL_SCRIPT:-}" ] && [ -r "$CURL_SCRIPT" ]; then
  while IFS='|' read -r pat c b; do
    [ -z "$pat" ] && continue
    case "$url" in
      *"$pat"*) code="$c"; body="$b"; break ;;
    esac
  done < "$CURL_SCRIPT"
fi
printf '%s\n%s' "$body" "$code"
exit 0
FAKE
  chmod +x "$bindir/curl"
}

run_publish() {
  local name="$1"; shift
  local sb="$ROOT/$name"
  mkdir -p "$sb/bin" "$sb/home" "$sb/tmp"
  mkfakecurl "$sb/bin"
  printf 'not really an mp3' > "$sb/master.mp3"
  env -i \
    PATH="$sb/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    HOME="$sb/home" TMPDIR="$sb/tmp" \
    CURL_SCRIPT="$sb/curl.script" CURL_CALLLOG="$sb/curl.log" \
    PODBEAN_PODCAST_ID="chan-target" \
    PODBEAN_CLIENT_ID="test-client-id" \
    PODBEAN_CLIENT_SECRET="test-client-secret" \
    bash "$PUBLISH" --audio "$sb/master.mp3" --title "A Test Episode" 2>&1
}

reached_episode_create() {
  /usr/bin/grep -q '/episodes?access_token' "$ROOT/$1/curl.log" 2>/dev/null
}

echo ""
echo "═══ podbean_publish.sh — channel scoping fails closed (T0-19) ═══"

# ── 1. The channel listing call fails ─────────────────────────────────────────
mkdir -p "$ROOT/list-fail"
cat > "$ROOT/list-fail/curl.script" <<'SCRIPT'
oauth/token|200|{"access_token":"base-token"}
/podcasts|503|{"error":"service unavailable"}
SCRIPT
OUT="$(run_publish list-fail)"; RC=$?
if [ "$RC" -ne 0 ]; then ok "listing failure -> non-zero exit"; else bad "listing failure -> exit 0"; fi
case "$OUT" in
  *"isolation guard"*) ok "listing failure names the isolation guard" ;;
  *) bad "listing failure gave no isolation-guard reason (got: ${OUT: -200})" ;;
esac
if reached_episode_create list-fail; then
  bad "an episode-create request was sent after a failed channel listing"
else
  ok "no episode-create request was sent after a failed channel listing"
fi

# ── 2. The listing parses to no identifiers ───────────────────────────────────
mkdir -p "$ROOT/list-empty"
cat > "$ROOT/list-empty/curl.script" <<'SCRIPT'
oauth/token|200|{"access_token":"base-token"}
/podcasts|200|{"podcasts":[]}
SCRIPT
OUT="$(run_publish list-empty)"; RC=$?
if [ "$RC" -ne 0 ]; then ok "empty identifier list -> non-zero exit"; else bad "empty identifier list -> exit 0"; fi
if reached_episode_create list-empty; then
  bad "an episode-create request was sent with no confirmed channel"
else
  ok "no episode-create request was sent with no confirmed channel"
fi

# ── 3. Multi-channel account, scoped-token request fails ──────────────────────
mkdir -p "$ROOT/scope-fail"
cat > "$ROOT/scope-fail/curl.script" <<'SCRIPT'
multiplePodcastsToken|500|{"error":"nope"}
oauth/token|200|{"access_token":"base-token"}
/podcasts|200|{"podcasts":[{"id":"chan-target"},{"id":"chan-other-client"}]}
SCRIPT
OUT="$(run_publish scope-fail)"; RC=$?
if [ "$RC" -ne 0 ]; then ok "scoped-token failure on a multi-channel account -> non-zero exit"; else bad "scoped-token failure -> exit 0"; fi
case "$OUT" in
  *"account-wide token"*) ok "scoped-token failure refuses the account-wide token by name" ;;
  *) bad "scoped-token failure did not name the account-wide token (got: ${OUT: -200})" ;;
esac
if reached_episode_create scope-fail; then
  bad "an episode-create request was sent on an unscoped token (multi-channel account)"
else
  ok "no episode-create request was sent on an unscoped token"
fi

# ── 4. Multi-channel account, scoped-token response carries no token ──────────
mkdir -p "$ROOT/scope-empty"
cat > "$ROOT/scope-empty/curl.script" <<'SCRIPT'
multiplePodcastsToken|200|{"podcasts":[]}
oauth/token|200|{"access_token":"base-token"}
/podcasts|200|{"podcasts":[{"id":"chan-target"},{"id":"chan-other-client"}]}
SCRIPT
OUT="$(run_publish scope-empty)"; RC=$?
if [ "$RC" -ne 0 ]; then ok "empty scoped-token response -> non-zero exit"; else bad "empty scoped-token response -> exit 0"; fi
if reached_episode_create scope-empty; then
  bad "an episode-create request was sent after an empty scoped-token response"
else
  ok "no episode-create request was sent after an empty scoped-token response"
fi

# ── 5. THE OTHER DIRECTION: a healthy single-channel account still proceeds ───
# This is the check that proves the fix is not simply "refuse everything".
mkdir -p "$ROOT/healthy"
cat > "$ROOT/healthy/curl.script" <<'SCRIPT'
oauth/token|200|{"access_token":"base-token"}
/podcasts|200|{"podcasts":[{"id":"chan-target"}]}
/episodes?access_token|200|{"count":3}
files/uploadAuthorize|200|{"presigned_url":"https://upload.example/put","file_key":"key-1"}
SCRIPT
OUT="$(run_publish healthy)"
case "$OUT" in
  *"already scoped"*) ok "healthy single-channel account passes the isolation guard" ;;
  *) bad "healthy single-channel account was blocked by the isolation guard (got: ${OUT: -240})" ;;
esac
case "$OUT" in
  *"isolation guard"*) bad "healthy single-channel account hit an isolation-guard refusal" ;;
  *) ok "healthy single-channel account produced no isolation-guard refusal" ;;
esac
# The behavioural half of the same claim: the healthy run must actually REACH
# the episode-create call. Every refusal case above asserts the opposite, so
# without this one the suite could be satisfied by a script that refuses always.
if reached_episode_create healthy; then
  ok "healthy single-channel account reached the episode-create call"
else
  bad "healthy single-channel account never reached the episode-create call"
fi

echo ""
echo "═══ generate_podcast_audio.sh — an unmeasured master is not verified (T0-20) ═══"

# Running the whole generator needs a paid TTS provider and a client reference,
# so the block is proven in two parts.
#
# PART 1 — BEHAVIOURAL: the two conditions the fix keys on are real and
# reachable. A status that is always zero, or a branch nothing can enter, would
# make the source assertions in PART 2 meaningless.
if command -v ffmpeg >/dev/null 2>&1; then
  NOT_AUDIO="$ROOT/not-audio.mp3"
  printf 'this is not audio' > "$NOT_AUDIO"
  R128_RC=0
  ffmpeg -hide_banner -nostats -i "$NOT_AUDIO" -af ebur128 -f null - </dev/null \
    >/dev/null 2>"$ROOT/r128.log" || R128_RC=$?
  if [ "$R128_RC" -ne 0 ]; then
    ok "ffmpeg -af ebur128 really exits non-zero on an unmeasurable master (rc=$R128_RC)"
  else
    bad "ffmpeg -af ebur128 exited 0 on a non-audio file — the propagated status would be meaningless"
  fi
else
  echo "  SKIP — ffmpeg not on PATH; the measurement-status half is NOT covered on this runner"
fi
: > "$ROOT/empty-r128.log"
PARSED="$(python3 - "$ROOT/empty-r128.log" <<'PYEOF'
import re, sys
raw = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
m = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", raw)
print(m[-1] if m else "NA")
PYEOF
)"
if [ "$PARSED" = "NA" ]; then
  ok "an empty measurement log really parses to NA, so the NA branch is reachable"
else
  bad "an empty measurement log did not parse to NA (got '$PARSED')"
fi

# PART 2 — SOURCE: neither escape hatch survives, and each failure branch exits.
if /usr/bin/grep -q 'ebur128 -f null - </dev/null 2>"\$R128_LOG" || true' "$AUDIO_SH"; then
  bad "the loudness measurement still discards its exit status with || true"
else
  ok "the loudness measurement no longer discards its exit status"
fi
if /usr/bin/grep -q 'could not measure integrated loudness of the master; ffprobe duration check passed' "$AUDIO_SH"; then
  bad "an unmeasurable master is still only a warning"
else
  ok "an unmeasurable master is no longer only a warning"
fi
R128_FAIL_EXITS="$(/usr/bin/awk '/loudness measurement failed/{found=1} found && /exit 1/{print "yes"; exit}' "$AUDIO_SH")"
if [ "$R128_FAIL_EXITS" = "yes" ]; then
  ok "a failed measurement exits non-zero"
else
  bad "a failed measurement does not exit non-zero"
fi
NA_EXITS="$(/usr/bin/awk '/could not parse an integrated-loudness summary/{found=1} found && /exit 1/{print "yes"; exit}' "$AUDIO_SH")"
if [ "$NA_EXITS" = "yes" ]; then
  ok "an unparseable summary exits non-zero"
else
  bad "an unparseable summary does not exit non-zero"
fi

echo ""
echo "  (T0-22, the ledger linkage, is covered by"
echo "   tests/unit/podcast-state-ledger-linkage.test.py — run it too.)"

echo ""
echo "═══ Result: $PASS passed | $FAIL failed ═══"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
