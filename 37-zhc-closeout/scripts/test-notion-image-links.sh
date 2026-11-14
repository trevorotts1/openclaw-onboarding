#!/usr/bin/env bash
# test-notion-image-links.sh -- BU-78 acceptance fixture (WF-095).
#
# The permanent Notion document must embed pictures that do not expire.
# create-notion-closeout.sh is run against a stub `curl` that records every
# Notion request body; nothing leaves this machine and no live Notion API runs.
#
# Fixture state carries BOTH a temporary generator link and a durable public
# link for each infographic, plus a non-durable visualIntelligenceUrls list.
# Asserts every image block in the recorded bodies uses a durable link and none
# uses a temporary one.
#
# EXIT: 0 all PASS, 1 any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bu78-notion-image-links.XXXXXX")"
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

# Durable public links (what the GHL media upload writes) vs temporary
# generator links (what generate-visual-intelligence.sh writes).
DUR1="https://storage.googleapis.com/msgsndr/fixture/org-chart-public.png"
DUR2="https://storage.googleapis.com/msgsndr/fixture/flow-public.png"
TMP1="https://temp.example.invalid/generated/org-chart-temp.png"
TMP2="https://temp.example.invalid/generated/flow-temp.png"
TMP3="https://temp.example.invalid/generated/extra-set-3.png"

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
jq -n \
  --arg dur1 "$DUR1" --arg dur2 "$DUR2" \
  --arg tmp1 "$TMP1" --arg tmp2 "$TMP2" --arg tmp3 "$TMP3" \
  '{
  "version": 1,
  "companyId": "fixture-co",
  "companySlug": "fixture-co",
  "companyName": "Fixture Co",
  "ownerName": "Test Owner",
  "agentName": "TestCEO",
  "interviewComplete": true,
  "commandCenterUrl": "https://cc.example.test/",
  "departments": [],
  "infographic1Url": $tmp1,
  "infographic2Url": $tmp2,
  "visualIntelligenceUrls": [$tmp1, $tmp2, $tmp3],
  "ghlInfographic1PublicUrl": $dur1,
  "ghlInfographic2PublicUrl": $dur2,
  "ghlMediaUploaded": true
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

# ---- collect every image block URL from the recorded bodies --------------
img_urls=()
for f in "${bodies[@]}"; do
  [[ -e "$f" ]] || continue
  while IFS= read -r u; do
    [[ -z "$u" ]] && continue
    img_urls+=("$u")
  done < <(jq -r '.. | objects | select(.type? == "image") | .image.external.url // empty' "$f" 2>/dev/null)
done

if [[ "${#img_urls[@]}" -ge 2 ]]; then
  pass "recorded bodies carry image blocks (${#img_urls[@]} image URLs)"
else
  fail "expected at least 2 image blocks in the recorded bodies, got ${#img_urls[@]}"
fi

# ---- the assertions the unit names --------------------------------------
non_durable=0
for u in "${img_urls[@]}"; do
  if [[ "$u" != "$DUR1" && "$u" != "$DUR2" ]]; then
    non_durable=$((non_durable + 1))
    fail "image block uses a non-durable link: $u"
  fi
done
if [[ "$non_durable" -eq 0 && "${#img_urls[@]}" -gt 0 ]]; then
  pass "every image block uses a durable public link"
fi

for pair in "infographic-1:$DUR1" "infographic-2:$DUR2"; do
  label="${pair%%:*}"; want="${pair#*:}"
  found=0
  for u in "${img_urls[@]}"; do
    [[ "$u" == "$want" ]] && found=1
  done
  if [[ "$found" -eq 1 ]]; then
    pass "$label is embedded from its durable public link"
  else
    fail "$label durable public link was never embedded: $want"
  fi
done

# A temporary generator link must appear in no body at all -- this covers both
# the infographic fallbacks and anything from visualIntelligenceUrls.
temp_hits=0
for f in "${bodies[@]}"; do
  [[ -e "$f" ]] || continue
  text="$(cat "$f")"
  [[ "$text" == *"temp.example.invalid"* ]] && temp_hits=$((temp_hits + 1))
done
if [[ "$temp_hits" -eq 0 ]]; then
  pass "no Notion body contains a temporary generator link"
else
  fail "$temp_hits Notion body/bodies still contain a temporary generator link"
fi

# The media-library sentence is sent only when the upload is recorded as done.
para_hits=0
for f in "${bodies[@]}"; do
  [[ -e "$f" ]] || continue
  text="$(cat "$f")"
  [[ "$text" == *"Your full picture set was sent to you in Telegram and saved to your media library."* ]] && para_hits=$((para_hits + 1))
done
if [[ "$para_hits" -eq 1 ]]; then
  pass "the media-library sentence is sent once when ghlMediaUploaded is true"
else
  fail "expected the media-library sentence in exactly 1 body when ghlMediaUploaded is true, got $para_hits"
fi

printf '\nTotal: %d passed, %d failed\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then exit 0; else exit 1; fi
