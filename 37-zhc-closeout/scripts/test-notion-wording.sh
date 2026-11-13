#!/usr/bin/env bash
# test-notion-wording.sh -- BU-72 acceptance fixture (WF-090).
#
# The permanent Notion document must not promise what nothing delivers.
# create-notion-closeout.sh is run against a stub `curl` that records every
# Notion request body; nothing leaves this machine and no live Notion API runs.
#
# Asserts no recorded body contains "three times a day", "Every Friday",
# "Telegram topic" or "every 30 seconds", and that the two replacement
# sentences the unit names are the ones that were sent.
#
# EXIT: 0 all PASS, 1 any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bu72-notion-wording.XXXXXX")"
trap 'if [[ -z "${KEEP_WORK:-}" ]]; then rm -rf "$WORK"; fi' EXIT
echo "    fixture work dir: $WORK"

BOX="$WORK/box"
OC="$BOX/.openclaw"
SK="$OC/skills/37-zhc-closeout/scripts"
CAPTURE="$WORK/bodies"
mkdir -p "$SK" "$OC/workspace" "$BOX/bin" "$CAPTURE"

cp "$SCRIPT_DIR/create-notion-closeout.sh" "$SCRIPT_DIR/closeout_facts.py" \
   "$SCRIPT_DIR/lib-closeout-state.sh" "$SK/" \
   || { echo "fixture: copy of create-notion-closeout.sh failed" >&2; exit 1; }

PARENT_PAGE_ID="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
STATE="$OC/workspace/.workforce-build-state.json"

# ---- stub curl: record every request body, answer with Notion-shaped JSON ----
cat > "$BOX/bin/curl" <<'STUB'
#!/usr/bin/env bash
set -u
method="GET"; url=""; body=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -X) method="$2"; shift 2 ;;
    -d|--data|--data-raw) body="$2"; shift 2 ;;
    -K|--config|-H|--header|-o|--output|-w) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
n=$(( $(cat "$CAPTURE_DIR/.n" 2>/dev/null || echo 0) + 1 ))
printf '%s' "$n" > "$CAPTURE_DIR/.n"
printf '%s' "$body" > "$CAPTURE_DIR/body.$n.json"
printf '%s %s\n' "$method" "$url" >> "$CAPTURE_DIR/requests.log"
case "$method|$url" in
  "POST|https://api.notion.com/v1/search")
    printf '{"object":"list","has_more":false,"results":[]}' ;;
  "POST|https://api.notion.com/v1/pages")
    printf '{"object":"page","id":"cccccccccccccccccccccccccccccccc"}' ;;
  "GET|https://api.notion.com/v1/blocks/"*"/children")
    printf '{"object":"list","has_more":false,"results":[]}' ;;
  "GET|"*)
    printf '{"object":"page","id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","archived":false,"in_trash":false}' ;;
  *)
    printf '{}' ;;
esac
exit 0
STUB
chmod +x "$BOX/bin/curl"

# ---- fixture state -------------------------------------------------------
jq -n '{
  "version": 1,
  "companyId": "fixture-co",
  "companySlug": "fixture-co",
  "companyName": "Fixture Co",
  "ownerName": "Test Owner",
  "agentName": "TestCEO",
  "interviewComplete": true,
  "commandCenterUrl": "https://cc.example.test/",
  "departments": []
}' > "$STATE" || { echo "fixture: state write failed" >&2; exit 1; }

# ---- run the real script against the stub --------------------------------
echo "--- running create-notion-closeout.sh with Notion stubbed ---"
rc=0
env -i \
  PATH="$BOX/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
  HOME="$BOX" \
  TMPDIR="${TMPDIR:-/tmp}" \
  CAPTURE_DIR="$CAPTURE" \
  NOTION_API_TOKEN=fixture-not-a-real-token \
  NOTION_CLOSEOUT_PARENT_PAGE_ID="$PARENT_PAGE_ID" \
  bash "$SK/create-notion-closeout.sh" > "$WORK/run.out" 2>&1 || rc=$?
echo "    create-notion-closeout rc=$rc (log: $WORK/run.out)"

if [[ "$rc" -eq 0 ]]; then
  pass "create-notion-closeout.sh exited 0"
else
  fail "create-notion-closeout.sh exited $rc (expected 0)"
  tail -15 "$WORK/run.out" | sed 's/^/    /'
fi

bodies=("$CAPTURE"/body.*.json)
if [[ -e "${bodies[0]}" && "${#bodies[@]}" -ge 10 ]]; then
  pass "every Notion request body was captured (${#bodies[@]} bodies)"
else
  fail "expected at least 10 recorded Notion bodies, got ${#bodies[@]}"
fi

# ---- the assertions the unit names --------------------------------------
for banned in "three times a day" "Every Friday" "Telegram topic" "every 30 seconds"; do
  hits=0
  for f in "${bodies[@]}"; do
    [[ -e "$f" ]] || continue
    text="$(cat "$f")"
    [[ "$text" == *"$banned"* ]] && hits=$((hits + 1))
  done
  if [[ "$hits" -eq 0 ]]; then
    pass "no Notion body contains \"$banned\""
  else
    fail "$hits Notion body/bodies still contain \"$banned\""
  fi
done

for heading in "The 3-Check Rhythm" "Talking to Department Heads"; do
  hits=0
  for f in "${bodies[@]}"; do
    [[ -e "$f" ]] || continue
    text="$(cat "$f")"
    [[ "$text" == *"$heading"* ]] && hits=$((hits + 1))
  done
  if [[ "$hits" -eq 0 ]]; then
    pass "heading \"$heading\" is not sent"
  else
    fail "heading \"$heading\" is still sent ($hits body/bodies)"
  fi
done

sent_replacements=0
for replacement in \
  "Ask your CEO agent to bring that department head into the conversation." \
  "For every task the agent checks five things in order: your company mission, your own values, your company goals, the department's goals, and the task itself."
do
  hit=0
  for f in "${bodies[@]}"; do
    [[ -e "$f" ]] || continue
    text="$(cat "$f")"
    [[ "$text" == *"$replacement"* ]] && hit=1
  done
  if [[ "$hit" -eq 1 ]]; then
    sent_replacements=$((sent_replacements + 1))
  else
    fail "replacement sentence was never sent: \"$replacement\""
  fi
done
if [[ "$sent_replacements" -eq 2 ]]; then
  pass "both replacement sentences are sent verbatim"
fi

printf '\nTotal: %d passed, %d failed\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then exit 0; else exit 1; fi
