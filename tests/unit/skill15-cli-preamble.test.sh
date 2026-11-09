#!/usr/bin/env bash
# skill15-cli-preamble.test.sh -- skill 15's Remote Rescue installer must read the
# REAL `openclaw config validate --json` verdict and find the installed OpenClaw
# resolver, on a Mac whose first node on PATH is below the OpenClaw floor.
#
# THE LIVE BUG (Nicole Hill's Mac, Big Fleet Roll 20261029, OpenClaw 2026.10.8):
#   1. With a below-floor node first on PATH every `openclaw` call prints
#        openclaw: Retrying with "<cli-node>/node" (cached OpenClaw runtime;
#        current Node failed runtime admission).
#      on stderr before its output. rr-validate-candidate.sh ran the validator
#      with `2>&1` and handed the WHOLE text to json.loads, so a VALID candidate
#      ({"valid":true,...,"warnings":[]}) parsed as "not JSON", was classified
#      candidate-invalid and refused (state: refused, installer exit 4), and
#      update-skills.sh withheld skill 15's .wired sentinel.
#   2. "Routing acceptance BLOCKED: no installed OpenClaw resolver found": the
#      resolver search used `npm root -g`, which answers for the node first on
#      PATH. With the private node first it named a global root that holds no
#      openclaw, while routing.js sat under the prefix the openclaw binary lives in.
#
# Cases 1, 2, 4, 6 and 7 fail on the pre-fix scripts (6 and 7 are end to end); the rest
# are controls that must keep passing.
set -uo pipefail
P="[skill15-cli-preamble]"; PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }
skip() { SKIP=$((SKIP+1)); echo "$P SKIP: $*"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$ROOT/15-blackceo-team-management/scripts"
VALIDATE="$SKILL/lib/rr-validate-candidate.sh"
INST="$SKILL/install-remote-rescue.sh"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/s15preamble.XXXXXX")"; trap 'rm -rf "$TMP"' EXIT
PRE='openclaw: Retrying with "/private/cli-node/bin/node" (cached OpenClaw runtime; current Node failed runtime admission).'
CAND="$TMP/candidate.json"; echo '{"agents":{"main":{}}}' > "$CAND"

# Fake openclaw. FAKE_PRE = stderr|stdout|none (where the retry line goes),
# FAKE_OUT = valid|invalid|validrc1|nojson (what `config validate --json` prints).
mkfake() {
  cat > "$1" <<'FAKE'
#!/usr/bin/env bash
case "${FAKE_PRE:-none}" in
  stderr) printf '%s\n\n' "$PRE" >&2 ;;
  stdout) printf '%s\n' "$PRE" ;;
esac
[ "${1:-}" = "config" ] && [ "${2:-}" = "validate" ] || exit 0
case "${FAKE_OUT:-valid}" in
  valid)   printf '{"valid":true,"path":"%s","warnings":[{"path":"plugins.entries.x","message":"plugin disabled but config is present"}]}\n' "${OPENCLAW_CONFIG_PATH:-}" ;;
  invalid) printf '{"valid":false,"issues":[{"path":"telegram","message":"Unrecognized key: telegram"}]}\n'; exit 1 ;;
  validrc1) printf '{"valid":true,"warnings":[]}\n'; exit 1 ;;
  nojson)  echo 'boom: no verdict' ;;
esac
FAKE
  chmod +x "$1"
}
mkdir -p "$TMP/bin"; mkfake "$TMP/bin/openclaw"; export PRE

verdict() { # <FAKE_PRE> <FAKE_OUT> -> validator JSON line
  FAKE_PRE="$1" FAKE_OUT="$2" OPENCLAW_BIN="$TMP/bin/openclaw" bash "$VALIDATE" "$CAND"
}
field() { python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2]))' "$1" "$2"; }

# --- 1. the live case: retry line on stderr, valid JSON on stdout -------------
V="$(verdict stderr valid)"
[ "$(field "$V" valid)" = "True" ] \
  && pass "1 retry line on stderr + valid JSON on stdout => valid" \
  || fail "1 a VALID candidate was rejected because of the retry line: $V"

# --- 2. same line on stdout ahead of the JSON (other CLI builds) --------------
V="$(verdict stdout valid)"
[ "$(field "$V" valid)" = "True" ] \
  && pass "2 retry line on stdout ahead of the JSON => valid" \
  || fail "2 retry line on stdout hid the verdict: $V"

# --- 3. a real rejection still rejects, and names the issue, not the retry line
V="$(verdict stderr invalid)"
if [ "$(field "$V" valid)" = "False" ] && [[ "$(field "$V" detail)" == *"Unrecognized key: telegram"* ]]; then
  pass "3 invalid candidate is still refused and the detail is the issue"
else
  fail "3 invalid candidate not refused with its issue: $V"
fi

# --- 4. no verdict at all: refused, detail is not the retry line ---------------
V="$(verdict stderr nojson)"
if [ "$(field "$V" valid)" = "False" ] && [[ "$(field "$V" detail)" != *"Retrying with"* ]] \
   && [[ "$(field "$V" detail)" == *"boom: no verdict"* ]]; then
  pass "4 no JSON verdict is refused (fail-closed), detail skips the retry line"
else
  fail "4 no-verdict case wrong: $V"
fi

# --- 5. controls: the verdict still obeys the exit code; no openclaw => refused
V="$(verdict none valid)"
[ "$(field "$V" valid)" = "True" ] \
  && pass "5a control: no retry line, valid JSON => valid (baseline unchanged)" \
  || fail "5a control broke the plain case: $V"
V="$(verdict stderr validrc1)"
[ "$(field "$V" valid)" = "False" ] \
  && pass "5b control: valid:true with a non-zero exit is still refused" \
  || fail "5b control: a non-zero validator exit was trusted: $V"
V="$(env -u OPENCLAW_BIN PATH="/usr/bin:/bin" bash "$VALIDATE" "$CAND")"
[ "$(field "$V" valid)" = "False" ] && [ "$(field "$V" rc)" = "127" ] \
  && pass "5c control: no openclaw on PATH => refused rc 127" \
  || fail "5c control: absent openclaw was not refused: $V"

# --- end-to-end fixtures -------------------------------------------------------
# A config the installer must change (operators sit in groupAllowFrom), so the
# transaction writes a candidate and runs the validator before promoting it.
mkhome() {
  rm -rf "$1"; mkdir -p "$1/.openclaw"
  printf '{"agents":{"main":{}},"channels":{"telegram":{"allowFrom":[],"groupAllowFrom":["5252140759"]}}}\n' \
    > "$1/.openclaw/openclaw.json"
}

# --- 6. installer end to end: promoted, not refused ----------------------------
mkhome "$TMP/h6"
OUT="$(FAKE_PRE=stderr FAKE_OUT=valid HOME="$TMP/h6" PATH="$TMP/bin:$PATH" bash "$INST" --idempotent 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && [[ "$OUT" == *"candidate       : valid"* ]] && [[ "$OUT" == *"promote         : promoted"* ]] \
   && [[ "$OUT" != *"candidate-invalid"* ]]; then
  pass "6 installer promotes a valid candidate when the CLI prints the retry line (rc=0)"
else
  fail "6 installer refused a valid candidate (rc=$RC): $(printf '%s' "$OUT" | grep -E 'candidate|promote|state' | head -4 | tr '\n' ' ')"
fi

# --- 7. resolver: found through the openclaw binary's own package -------------
# Layout of a real prefix install: bin/openclaw -> ../lib/node_modules/openclaw/openclaw.mjs.
# `npm root -g` (fake npm, first on PATH like the private node) names ANOTHER root.
# No retry line here: this case isolates the resolver search from the validator fix.
if ! command -v node >/dev/null 2>&1; then
  skip "7 node not available; resolver discovery not asserted"
else
  PKG="$TMP/prefix/lib/node_modules/openclaw"
  mkdir -p "$PKG/dist/plugin-sdk" "$TMP/prefix/bin" "$TMP/other/lib/node_modules" "$TMP/pbin"
  mkfake "$PKG/openclaw.mjs"
  ln -s ../lib/node_modules/openclaw/openclaw.mjs "$TMP/prefix/bin/openclaw"
  cat > "$PKG/dist/plugin-sdk/routing.js" <<'ROUTING'
export function resolveAgentRoute({ peer, defaultAgentId }) {
  const bound = peer && peer.id;
  return bound && bound !== "111222333"
    ? { agentId: "remote-rescue", sessionKey: `agent:remote-rescue:direct:${bound}`, matchedBy: "binding.peer" }
    : { agentId: defaultAgentId, sessionKey: "agent:main:main", matchedBy: "default" };
}
ROUTING
  printf '#!/usr/bin/env bash\n[ "$1 $2" = "root -g" ] && echo "%s" && exit 0\nexit 0\n' "$TMP/other/lib/node_modules" > "$TMP/pbin/npm"
  chmod +x "$TMP/pbin/npm"
  mkhome "$TMP/h7"
  OUT="$(env -u OPENCLAW_ROUTING_MODULE FAKE_PRE=none FAKE_OUT=valid HOME="$TMP/h7" \
         PATH="$TMP/pbin:$TMP/prefix/bin:$PATH" bash "$INST" --idempotent 2>&1)"; RC=$?
  if [ "$RC" -eq 0 ] && [[ "$OUT" == *"routing verdict: PASS"* ]] && [[ "$OUT" != *"Routing acceptance BLOCKED"* ]]; then
    pass "7 resolver found via the openclaw binary's package although npm root -g names another root"
  else
    fail "7 resolver not found / routing not accepted (rc=$RC): $(printf '%s' "$OUT" | grep -E 'routing|Routing' | head -3 | tr '\n' ' ')"
  fi

  # 7b control: nothing locates a package -> still BLOCKED (the gate is live).
  # Only valid on a machine with no fixed-location install for the fallbacks.
  if ls /opt/homebrew/lib/node_modules/openclaw/dist/plugin-sdk/routing.js \
        /usr/local/lib/node_modules/openclaw/dist/plugin-sdk/routing.js \
        /usr/lib/node_modules/openclaw/dist/plugin-sdk/routing.js >/dev/null 2>&1; then
    skip "7b this machine has a fixed-location OpenClaw install; BLOCKED control not asserted"
  else
    mkdir -p "$TMP/loose"; mkfake "$TMP/loose/openclaw"; mkhome "$TMP/h7b"
    OUT="$(env -u OPENCLAW_ROUTING_MODULE FAKE_PRE=none FAKE_OUT=valid HOME="$TMP/h7b" \
           PATH="$TMP/pbin:$TMP/loose:$PATH" bash "$INST" --idempotent 2>&1)"
    [[ "$OUT" == *"Routing acceptance BLOCKED"* ]] \
      && pass "7b control: no package anywhere => routing acceptance is still BLOCKED, not faked" \
      || fail "7b control: BLOCKED not reported without a resolver"
  fi
fi

echo "$P Results: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ]
