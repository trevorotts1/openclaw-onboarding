#!/usr/bin/env bash
set -u
# tests/unit/test-u027-channel-scoping.test.sh
# U027 — Channel scoping isolation guard test suite.
# T1: listing API fail -> non-zero exit + "ERROR: ... refusing" + no create
# T2: scoped token empty -> non-zero + "ERROR: ... no token" + no create
# T3: AC4 source — podcast_id in create_args
# Mutation-proof: die() prepends "ERROR:", log() does not.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PUBLISH="$REPO_ROOT/58-podcast-production-engine/scripts/podbean_publish.sh"
[ -f "$PUBLISH" ] || { echo "FATAL: missing $PUBLISH" >&2; exit 1; }

PASS=0; FAIL=0
ok()   { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/u027-suite.XXXXXX")"
trap 'rm -rf "$ROOT"' EXIT

mkfakecurl() {
  local bindir="$1"; mkdir -p "$bindir"
  cat > "$bindir/curl" <<'FAKE'
#!/usr/bin/env bash
cfg=""; prev=""
for a in "$@"; do if [ "$prev" = "-K" ]; then cfg="$a"; fi; prev="$a"; done
url=""
if [ -n "$cfg" ] && [ -r "$cfg" ]; then
  url="$(sed -n 's/^url = "\(.*\)"$/\1/p' "$cfg" | head -1)"
fi
printf '%s\n' "$url" >> "${CURL_CALLLOG:-/dev/null}"
code=200; body='{}'
if [ -n "${CURL_SCRIPT:-}" ] && [ -r "$CURL_SCRIPT" ]; then
  while IFS='|' read -r pat c b; do
    [ -z "$pat" ] && continue
    case "$url" in *"$pat"*) code="$c"; body="$b"; break ;; esac
  done < "$CURL_SCRIPT"
fi
printf '%s\n%s' "$body" "$code"
exit 0
FAKE
  chmod +x "$bindir/curl"
}

run_publish() {
  local name="$1"; shift; local sb="$ROOT/$name"
  mkdir -p "$sb/bin" "$sb/home" "$sb/tmp"
  mkfakecurl "$sb/bin"
  printf 'not really an mp3' > "$sb/master.mp3"
  env -i PATH="$sb/bin:/usr/bin:/bin:/usr/sbin:/sbin" HOME="$sb/home" TMPDIR="$sb/tmp" \
    CURL_SCRIPT="$sb/curl.script" CURL_CALLLOG="$sb/curl.log" \
    PODBEAN_PODCAST_ID="chan-target" PODBEAN_CLIENT_ID="test-client-id" \
    PODBEAN_CLIENT_SECRET="test-client-secret" \
    bash "$PUBLISH" --audio "$sb/master.mp3" --title "A Test Episode" 2>&1
}

reached_episode_create() { /usr/bin/grep -q '/episodes?access_token' "$ROOT/$1/curl.log" 2>/dev/null; }

echo ""; echo "=== U027 Channel Scoping Test Suite ==="; echo ""

# T0: AC4 source check
CREATE_ARGS_BLOCK="$(awk '/^create_args=\(/,/^\)/' "$PUBLISH" 2>/dev/null)"
if echo "$CREATE_ARGS_BLOCK" | /usr/bin/grep -q 'podcast_id=${PODBEAN_PODCAST_ID}'; then
  ok "AC4: create_args block contains podcast_id data-urlencode"
else bad "AC4: create_args block does NOT contain podcast_id data-urlencode"; fi

CREATE_LINE="$(/usr/bin/grep -n 'podcast_id=${PODBEAN_PODCAST_ID}' "$PUBLISH" | /usr/bin/grep -v multiplePodcastsToken | head -1)"
if [ -n "$CREATE_LINE" ]; then ok "AC4: podcast_id data-urlencode at $CREATE_LINE"
else bad "AC4: podcast_id data-urlencode NOT found in create area"; fi

# T1: listing API fails (non-transient 401). Body carries valid data so
# if die->log, script continues past guard -> detectable.
echo ""; echo "--- T1: listing API failure (non-transient 401) ---"
mkdir -p "$ROOT/list-fail"
cat > "$ROOT/list-fail/curl.script" <<'S1'
oauth/token|200|{"access_token":"base-token"}
/podcasts|401|{"podcasts":[{"id":"chan-target"}]}
S1
OUT="$(run_publish list-fail)"; RC=$?
if [ "$RC" -ne 0 ]; then ok "T1: listing failure -> non-zero exit (rc=$RC)"
else bad "T1: listing failure -> exit 0"; fi
case "$OUT" in
  *"ERROR:"*"refusing to publish with an unscoped token"*)
    ok "T1: ERROR + refusing message (die() active)" ;;
  *"refusing to publish with an unscoped token"*)
    bad "T1: refusing message without ERROR prefix — die() weakened" ;;
  *) bad "T1: missing required message (got: ${OUT: -200})" ;;
esac
if reached_episode_create list-fail; then
  bad "T1: episode-create reached after failed listing (guard bypassed)"
else ok "T1: no episode-create after failed listing"; fi

# T2: scoped-token empty on multi-channel
echo ""; echo "--- T2: scoped token empty on multi-channel ---"
mkdir -p "$ROOT/scope-empty"
cat > "$ROOT/scope-empty/curl.script" <<'S2'
multiplePodcastsToken|200|{"podcast_tokens":[]}
oauth/token|200|{"access_token":"base-token"}
/podcasts|200|{"podcasts":[{"id":"chan-target"},{"id":"chan-other"}]}
S2
OUT="$(run_publish scope-empty)"; RC=$?
if [ "$RC" -ne 0 ]; then ok "T2: empty scoped-token -> non-zero exit (rc=$RC)"
else bad "T2: empty scoped-token -> exit 0"; fi
case "$OUT" in
  *"ERROR:"*"returned no token for the target channel"*)
    ok "T2: ERROR + 'returned no token for the target channel' (die() active)" ;;
  *"returned no token for the target channel"*)
    bad "T2: no-token message without ERROR prefix — die() weakened" ;;
  *) bad "T2: missing required message (got: ${OUT: -200})" ;;
esac
if reached_episode_create scope-empty; then
  bad "T2: episode-create reached after empty scoped-token"
else ok "T2: no episode-create after empty scoped-token"; fi

# Sanity: healthy single-channel
echo ""; echo "--- sanity: healthy single-channel ---"
mkdir -p "$ROOT/healthy"
cat > "$ROOT/healthy/curl.script" <<'S3'
oauth/token|200|{"access_token":"base-token"}
/podcasts|200|{"podcasts":[{"id":"chan-target"}]}
/episodes?access_token|200|{"count":3}
S3
OUT="$(run_publish healthy)" 2>/dev/null || true
case "$OUT" in
  *"already scoped"*) ok "sanity: healthy passes isolation guard" ;;
  *"isolation guard"*) bad "sanity: healthy hit isolation-guard refusal" ;;
  *) ok "sanity: healthy ran (no isolation-guard refusal)" ;;
esac
if reached_episode_create healthy; then ok "sanity: healthy reached episode-create"
else bad "sanity: healthy never reached episode-create"; fi

echo ""; echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1; exit 0
