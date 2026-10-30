#!/usr/bin/env bash
# Acceptance cases for scripts/chamber-visual.sh (W73). Everything runs against
# stub `open`, `uname` and `launchctl` on PATH and temp config files - no real
# browser, window server or box config is touched.
#   bash scripts/tests/chamber-visual.test.sh      (exit 0 = all PASS)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../chamber-visual.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/chamber-visual-test.XXXXXX")"
STUB="$WORK/stub"
OPEN_LOG="$WORK/open.log"
FAILS=0; N=0
trap 'rm -rf "$WORK"' EXIT

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
check() { local d="$1"; shift; N=$((N + 1)); if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }

mkdir -p "$STUB"
# Stubs: `open` logs its arguments; `uname`/`launchctl` fake the GUI probe.
cat > "$STUB/open" <<'SH'
#!/bin/bash
printf '%s\n' "$*" >> "$OPEN_LOG"
SH
cat > "$STUB/uname" <<'SH'
#!/bin/bash
echo Darwin
SH
cat > "$STUB/launchctl" <<'SH'
#!/bin/bash
# FAKE_GUI_RC models `launchctl print gui/<uid>`: 0 = this user has a GUI
# session, 1 = none. Every other subcommand (managername) echoes the manager.
if [ "${1:-}" = "print" ]; then exit "${FAKE_GUI_RC:-0}"; fi
echo "${FAKE_MANAGER:-Aqua}"
SH
chmod +x "$STUB/open" "$STUB/uname" "$STUB/launchctl"
export OPEN_LOG
export PATH="$STUB:$PATH"

# 1. GUI present -> `open` invoked exactly once with the right URL.
: > "$OPEN_LOG"
OUT="$(env COUNCIL_CHAMBER_GUI=1 COUNCIL_PUBLIC_URL="https://demo-council.example.com" bash "$SCRIPT" --session abc123 2>"$WORK/err")"
sleep 0.3
check "GUI present: link line emitted" \
  grep -qxF 'Chamber link: https://demo-council.example.com/chamber/#session=abc123' <<<"$OUT"
check "GUI present: open invoked exactly once" \
  test "$(wc -l < "$OPEN_LOG" | tr -d ' ')" = 1
check "GUI present: open got the exact chamber URL" \
  grep -qxF 'https://demo-council.example.com/chamber/#session=abc123' "$OPEN_LOG"

# 2. Headless -> zero pop, link still emitted.
: > "$OPEN_LOG"
OUT="$(env COUNCIL_CHAMBER_GUI=0 COUNCIL_PUBLIC_URL="https://demo-council.example.com" bash "$SCRIPT" --session abc123 2>"$WORK/err")"
sleep 0.3
check "headless: link still emitted" \
  grep -qxF 'Chamber link: https://demo-council.example.com/chamber/#session=abc123' <<<"$OUT"
check "headless: open never invoked" test ! -s "$OPEN_LOG"

# 3. Auto GUI probe: Aqua pops directly; a non-Aqua gateway still delivers
#    through the user's own GUI session (the CTR-103 fix - the old rule made the
#    pop depend on THIS process being Aqua, so a gateway silently skipped it);
#    with no GUI session at all it never claims a pop.
: > "$OPEN_LOG"
OUT="$(env -u COUNCIL_CHAMBER_GUI FAKE_MANAGER=Aqua COUNCIL_PUBLIC_URL="https://demo-council.example.com" bash "$SCRIPT" 2>"$WORK/err")"
sleep 0.3
check "auto probe Aqua: open invoked once" test "$(wc -l < "$OPEN_LOG" | tr -d ' ')" = 1
check "auto probe Aqua: no session anchor without --session" \
  grep -qxF 'Chamber link: https://demo-council.example.com/chamber/' <<<"$OUT"
: > "$OPEN_LOG"
OUT="$(env -u COUNCIL_CHAMBER_GUI FAKE_MANAGER=Background FAKE_GUI_RC=0 COUNCIL_PUBLIC_URL="https://demo-council.example.com" bash "$SCRIPT" 2>"$WORK/err")"
sleep 0.3
check "auto probe Background with a GUI session: exactly one pop" \
  test "$(wc -l < "$OPEN_LOG" | tr -d ' ')" = 1
check "auto probe Background with a GUI session: reports opened" \
  grep -q '^pop: opened' "$WORK/err"
: > "$OPEN_LOG"
OUT="$(env -u COUNCIL_CHAMBER_GUI FAKE_MANAGER=Background FAKE_GUI_RC=1 COUNCIL_PUBLIC_URL="https://demo-council.example.com" bash "$SCRIPT" 2>"$WORK/err")"
sleep 0.3
check "auto probe Background, no GUI session: zero pop" test ! -s "$OPEN_LOG"
check "auto probe Background, no GUI session: link still emitted" \
  grep -qxF 'Chamber link: https://demo-council.example.com/chamber/' <<<"$OUT"
check "auto probe Background, no GUI session: reports skipped" \
  grep -q '^pop: skipped (no GUI session' "$WORK/err"

# 4. URL source order: COUNCIL_PUBLIC_URL > WISE_ELDERS_PUBLIC_ORIGIN >
#    service.json public_origin > loopback fallback.
OUT="$(env COUNCIL_PUBLIC_URL="https://env-council.example.com" WISE_ELDERS_PUBLIC_ORIGIN="https://wire-council.example.com" bash "$SCRIPT" 2>"$WORK/err")"
check "source order: COUNCIL_PUBLIC_URL wins" \
  grep -qxF 'Chamber link: https://env-council.example.com/chamber/' <<<"$OUT"
OUT="$(env -u COUNCIL_PUBLIC_URL WISE_ELDERS_PUBLIC_ORIGIN="https://wire-council.example.com" bash "$SCRIPT" 2>"$WORK/err")"
check "source order: WISE_ELDERS_PUBLIC_ORIGIN next" \
  grep -qxF 'Chamber link: https://wire-council.example.com/chamber/' <<<"$OUT"

cat > "$WORK/service.json" <<'JSON'
{
  "schema": "council-service/v1",
  "port": 8787,
  "origin": "http://127.0.0.1:8787",
  "public_origin": "https://svc-council.example.com",
  "manager": "launchd"
}
JSON
OUT="$(env -u COUNCIL_PUBLIC_URL -u WISE_ELDERS_PUBLIC_ORIGIN WISE_ELDERS_SERVICE_JSON="$WORK/service.json" bash "$SCRIPT" 2>"$WORK/err")"
check "source order: service.json public_origin next" \
  grep -qxF 'Chamber link: https://svc-council.example.com/chamber/' <<<"$OUT"

cat > "$WORK/service-null.json" <<'JSON'
{"public_origin": null}
JSON
OUT="$(env -u COUNCIL_PUBLIC_URL -u WISE_ELDERS_PUBLIC_ORIGIN WISE_ELDERS_SERVICE_JSON="$WORK/service-null.json" WISE_ELDERS_SERVICE_ORIGIN="http://127.0.0.1:8787" bash "$SCRIPT" --session abc123 2>"$WORK/err")"
check "loopback fallback when public_origin is null" \
  grep -qxF 'Chamber link: http://127.0.0.1:8787/chamber/#session=abc123' <<<"$OUT"

# 5. The link is ALWAYS in the output (every case above asserted a Chamber
#    link line) and the skill instructions make it ALWAYS land in the reply.
check "link always in the reply: every run printed exactly one Chamber link line" \
  test "$(printf '%s\n' "$OUT" | grep -c '^Chamber link: ')" = 1
SKILL="$HERE/../../SKILL.md"
check "SKILL.md: ALWAYS copy the Chamber link line into the reply" \
  grep -q 'ALWAYS copy that exact `Chamber link:` line into your reply' "$SKILL"
check "SKILL.md: helper is run on every convene" \
  grep -q 'chamber-visual.sh --session' "$SKILL"

# 6. A failing pop never breaks the run: exit 0 and the link survives.
cat > "$STUB/open" <<'SH'
#!/bin/bash
exit 1
SH
chmod +x "$STUB/open"
OUT="$(env COUNCIL_CHAMBER_GUI=1 COUNCIL_PUBLIC_URL="https://demo-council.example.com" bash "$SCRIPT" --session abc123 2>"$WORK/err"; echo "rc=$?")"
check "open failure: exit code still 0" grep -qxF 'rc=0' <<<"$OUT"
check "open failure: link still emitted" \
  grep -q '^Chamber link: https://demo-council.example.com/chamber/#session=abc123' <<<"$OUT"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "chamber-visual.test.sh: $N/$N PASS"
  exit 0
fi
echo "chamber-visual.test.sh: $FAILS FAIL of $N"
exit 1
