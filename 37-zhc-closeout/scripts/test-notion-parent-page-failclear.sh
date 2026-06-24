#!/usr/bin/env bash
# test-notion-parent-page-failclear.sh
#
# Guards the PERMANENT fix for the recurring ZHC closeout blocker
# "root-page-create-failed". Asserts that when NO Notion page is shared with the
# internal "ZHC" integration, the system degrades GRACEFULLY:
#   - it NEVER fabricates a Notion page,
#   - it emits the PRECISE, copy-paste client instruction,
#   - it STAGES the full closeout booklet locally (resumable), and
#   - it exits NON-FATAL to the overall closeout (the leg soft-fails, it never
#     aborts the run), while still flagging the leg as failed.
# And that onboarding's parent-page provisioner PINS an accessible page when one
# exists.
#
# Pure-bash, hermetic (temp HOME with workspace/, gateway + curl PATH-shimmed).
# Mirrors the test-closeout-watchdog.sh harness. Uses ONLY fictional placeholder
# names so qc-assert-no-client-names.sh stays green.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

CREATE_NOTION="$SKILL_DIR/scripts/create-notion-closeout.sh"
ENSURE_PARENT="$SKILL_DIR/scripts/ensure-notion-parent-page.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

# ── Hermetic environment ─────────────────────────────────────────────────────
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_HOME="$TMP_DIR/home"
FAKE_OC_ROOT="$FAKE_HOME/.openclaw"
FAKE_WS="$FAKE_OC_ROOT/workspace"
mkdir -p "$FAKE_WS"
FIXTURE_STATE="$FAKE_WS/.workforce-build-state.json"
ENV_FILE="$FAKE_WS/.env"

FAKE_BIN="$TMP_DIR/bin"
mkdir -p "$FAKE_BIN"

# Fake `openclaw` — escalation must be a no-op in tests.
cat > "$FAKE_BIN/openclaw" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$FAKE_BIN/openclaw"

# A baseline fixture state with a department (so create-notion-closeout.sh gets
# past placeholder gathering and reaches parent resolution). Fictional only.
write_baseline_state() {
  cat > "$FIXTURE_STATE" <<'JSON'
{
  "version": 1,
  "companyName": "Sample Holdings",
  "ownerName": "the Owner",
  "agentName": "TestAgent",
  "commandCenterUrl": "https://example.invalid/cc",
  "departments": [
    {"slug":"sales","name":"Sales","rolesDone":3,"sopCount":5}
  ]
}
JSON
}

read_state() { jq -r "$1 // empty" "$FIXTURE_STATE" 2>/dev/null; }

# install a curl stub from a mode keyword
install_curl_stub() {
  local mode="$1"
  cat > "$FAKE_BIN/curl" <<SH
#!/usr/bin/env bash
# Decide by the request body / URL present in the args.
ARGS="\$*"
if printf '%s' "\$ARGS" | grep -q "/v1/search"; then
  case "$mode" in
    no-shared-page)
      # Integration has nothing shared with it.
      printf '{"object":"list","results":[],"has_more":false}\n' ;;
    has-page)
      printf '{"object":"list","results":[{"id":"shared-page-id-9999","object":"page","properties":{"title":{"title":[{"plain_text":"Workspace Home"}]}}}],"has_more":false}\n' ;;
  esac
  exit 0
fi
if printf '%s' "\$ARGS" | grep -q "/v1/pages"; then
  case "$mode" in
    no-shared-page)
      # Internal integration creating at workspace root -> Notion rejects, no id.
      printf '{"object":"error","status":400,"code":"validation_error","message":"body failed validation: parent workspace not permitted for this integration"}\n' ;;
    has-page)
      printf '{"id":"created-page-id-1234","object":"page"}\n' ;;
  esac
  exit 0
fi
if printf '%s' "\$ARGS" | grep -q "/v1/blocks/"; then
  printf '{"object":"list","results":[],"has_more":false}\n'
  exit 0
fi
printf '{}\n'
exit 0
SH
  chmod +x "$FAKE_BIN/curl"
}

run_in_env() {
  HOME="$FAKE_HOME" \
  ZHC_STATE_FILE="$FIXTURE_STATE" \
  ZHC_NOTION_ENV_FILE="$ENV_FILE" \
  PATH="$FAKE_BIN:$PATH" \
  NOTION_API_TOKEN="ntn_TESTTOKEN0000000000000000000000000000000000" \
  ZHC_SKIP_TG_PREFLIGHT=1 \
    "$@"
}

echo ""
echo "========================================================"
echo " test-notion-parent-page-failclear.sh"
echo "========================================================"
echo ""

# ════════════════════════════════════════════════════════════
# T1: ensure-notion-parent-page.sh PINS an accessible page
# ════════════════════════════════════════════════════════════
echo "T1: provisioner pins an accessible page as NOTION_CLOSEOUT_PARENT_PAGE_ID"
write_baseline_state
rm -f "$ENV_FILE"
install_curl_stub has-page
run_in_env bash "$ENSURE_PARENT" >/dev/null 2>&1
T1_RC=$?
if [[ $T1_RC -eq 0 ]]; then pass "provisioner exited 0 (non-fatal)"; else fail "provisioner rc=$T1_RC (want 0)"; fi
if grep -qE '^NOTION_CLOSEOUT_PARENT_PAGE_ID=shared-page-id-9999$' "$ENV_FILE" 2>/dev/null; then
  pass "pinned NOTION_CLOSEOUT_PARENT_PAGE_ID=shared-page-id-9999 in workspace .env"
else
  fail "did NOT pin the accessible page id in .env"
  echo "    .env contents: $(cat "$ENV_FILE" 2>/dev/null)"
fi

# ════════════════════════════════════════════════════════════
# T2: ensure-notion-parent-page.sh degrades cleanly (no page shared)
# ════════════════════════════════════════════════════════════
echo "T2: provisioner emits the one-time instruction (no shared page), non-fatal"
write_baseline_state
rm -f "$ENV_FILE"
install_curl_stub no-shared-page
OUT=$(run_in_env bash "$ENSURE_PARENT" 2>&1)
T2_RC=$?
if [[ $T2_RC -eq 0 ]]; then pass "provisioner exited 0 (non-fatal) when nothing shared"; else fail "provisioner rc=$T2_RC (want 0)"; fi
if [[ ! -f "$ENV_FILE" ]] || ! grep -q 'NOTION_CLOSEOUT_PARENT_PAGE_ID=' "$ENV_FILE" 2>/dev/null; then
  pass "did NOT pin a bogus page id when nothing shared"
else
  fail "pinned a page id even though nothing was shared (.env: $(cat "$ENV_FILE"))"
fi
if printf '%s' "$OUT" | grep -q "Connections -> add ZHC"; then
  pass "emitted the precise client share instruction"
else
  fail "did not emit the share instruction. Output: $(printf '%s' "$OUT" | tr '\n' ' ' | head -c 300)"
fi
if [[ "$(read_state '.notionParentPagePending')" == "true" ]]; then
  pass "set notionParentPagePending=true marker for the resume loop"
else
  fail "notionParentPagePending not set (got: $(read_state '.notionParentPagePending'))"
fi

# ════════════════════════════════════════════════════════════
# T3: create-notion-closeout.sh — no-shared-page degrades gracefully
# ════════════════════════════════════════════════════════════
echo "T3: closeout builder fails CLEAR + stages content when no page is shared"
write_baseline_state
rm -f "$ENV_FILE"
install_curl_stub no-shared-page
OUT=$(run_in_env bash "$CREATE_NOTION" 2>&1)
T3_RC=$?
if [[ $T3_RC -ne 0 ]]; then
  pass "builder exited non-zero (leg soft-fails; does not falsely report success)"
else
  fail "builder exited 0 with no real page — would falsely mark notion ok"
fi
# No fabricated page:
if [[ -z "$(read_state '.notionRootPageUrl')" ]]; then
  pass "no fabricated Notion page (notionRootPageUrl empty)"
else
  fail "fabricated a page url: $(read_state '.notionRootPageUrl')"
fi
# Staged locally:
if [[ "$(read_state '.notionCloseoutStaged')" == "true" ]] && [[ -f "$FAKE_WS/.zhc-closeout-notion-staged.md" ]]; then
  pass "staged the full closeout booklet locally (resumable)"
else
  fail "did NOT stage content (staged=$(read_state '.notionCloseoutStaged'), file present=$([[ -f "$FAKE_WS/.zhc-closeout-notion-staged.md" ]] && echo yes || echo no))"
fi
# Clear, precise instruction surfaced:
if printf '%s' "$OUT" | grep -q "Connections -> add ZHC" && printf '%s' "$OUT" | grep -q "auto-completes on the next run"; then
  pass "surfaced the precise, resumable client one-liner"
else
  fail "did not surface the precise instruction. Output tail: $(printf '%s' "$OUT" | tr '\n' ' ' | tail -c 300)"
fi
# Blocker recorded as resumable:
if [[ "$(jq -r '.closeoutBlockers[]? | select(.class=="notion-no-shared-page") | .resumable' "$FIXTURE_STATE" 2>/dev/null)" == "true" ]]; then
  pass "recorded a resumable notion-no-shared-page blocker"
else
  fail "did not record a resumable notion-no-shared-page blocker"
fi

# ════════════════════════════════════════════════════════════
# T4: create-notion-closeout.sh — root-create-failed via workspace-root
#     (a page IS seen by search, so it falls to workspace-root create, which an
#      internal integration cannot do -> no id). Must stage, not fabricate.
# ════════════════════════════════════════════════════════════
echo "T4: closeout builder stages + fails clear on root-page-create-failed (no fake page)"
write_baseline_state
rm -f "$ENV_FILE"
# Custom stub: search returns a page (so SHARED_PAGE_SEEN=1 but no NAMED match),
# pushing the run to a workspace-root create that returns no id.
cat > "$FAKE_BIN/curl" <<'SH'
#!/usr/bin/env bash
ARGS="$*"
if printf '%s' "$ARGS" | grep -q "/v1/search"; then
  # A page exists but its title won't match BlackCEO/OpenClaw/ZHC named queries,
  # and there's no env parent -> resolves to PARENT_KIND=workspace-root.
  printf '{"object":"list","results":[{"id":"unrelated-page-id","object":"page","properties":{"title":{"title":[{"plain_text":"Random Notes"}]}}}],"has_more":false}\n'
  exit 0
fi
if printf '%s' "$ARGS" | grep -q "/v1/pages"; then
  printf '{"object":"error","status":400,"code":"validation_error","message":"parent workspace not permitted for this integration"}\n'
  exit 0
fi
printf '{"object":"list","results":[],"has_more":false}\n'
exit 0
SH
chmod +x "$FAKE_BIN/curl"
# Allow the workspace-root path (a named match wasn't found); the create then fails.
OUT=$(HOME="$FAKE_HOME" ZHC_STATE_FILE="$FIXTURE_STATE" ZHC_NOTION_ENV_FILE="$ENV_FILE" \
  PATH="$FAKE_BIN:$PATH" NOTION_API_TOKEN="ntn_TESTTOKEN0000000000000000000000000000000000" \
  ZHC_SKIP_TG_PREFLIGHT=1 ZHC_NOTION_ALLOW_WORKSPACE_ROOT=1 \
  bash "$CREATE_NOTION" 2>&1)
T4_RC=$?
if [[ $T4_RC -ne 0 ]]; then
  pass "builder exited non-zero on root-page-create-failed (leg soft-fails)"
else
  fail "builder exited 0 despite a failed root create"
fi
if [[ -z "$(read_state '.notionRootPageUrl')" ]]; then
  pass "no fabricated page on root-create-failed"
else
  fail "fabricated a page url on root-create-failed: $(read_state '.notionRootPageUrl')"
fi
if [[ "$(read_state '.notionCloseoutStaged')" == "true" ]] && [[ -f "$FAKE_WS/.zhc-closeout-notion-staged.md" ]]; then
  pass "staged the closeout booklet locally on root-create-failed (resumable)"
else
  fail "did NOT stage content on root-create-failed"
fi
if printf '%s' "$OUT" | grep -q "Connections -> add ZHC"; then
  pass "surfaced the precise client instruction on root-create-failed"
else
  fail "no precise instruction on root-create-failed. Output tail: $(printf '%s' "$OUT" | tr '\n' ' ' | tail -c 300)"
fi

# ════════════════════════════════════════════════════════════
# T5: TIER 2 agency fallback builds a subpage under the agency parent and
#     returns a VIEW-ONLY public link (mocked Notion API). Client has no Notion.
# ════════════════════════════════════════════════════════════
echo "T5: Tier 2 agency fallback -> view-only subpage under the agency parent"
write_baseline_state
rm -f "$ENV_FILE"
# Fictional fixture id only -- the real agency parent id is operator config,
# supplied via ZHC_AGENCY_NOTION_PARENT_PAGE_ID, never committed.
AGENCY_PARENT="00000000-0000-0000-0000-000000000000"
# Tier 2 stub: client search empty (no own page) -> Tier 2 selected; the agency
# create returns an id; child-page listings empty (sections build); page GET
# returns a public_url (parent is web-published, child inherits view-only).
cat > "$FAKE_BIN/curl" <<'SH'
#!/usr/bin/env bash
ARGS="$*"
if printf '%s' "$ARGS" | grep -q "/v1/search"; then
  printf '{"object":"list","results":[],"has_more":false}\n'; exit 0
fi
if printf '%s' "$ARGS" | grep -q -- "-X GET" && printf '%s' "$ARGS" | grep -Eq "/v1/pages/[0-9a-fA-F-]+"; then
  # Read-back of the created subpage: inherited view-only public link present.
  printf '{"id":"agency-subpage-id-7777","object":"page","public_url":"https://example.notion.site/Sample-Holdings-ZHC-Closeout-agencysubpageid7777"}\n'; exit 0
fi
if printf '%s' "$ARGS" | grep -q "/v1/pages"; then
  # Any page CREATE (root subpage + every section child) returns a fresh id.
  printf '{"id":"agency-subpage-id-7777","object":"page"}\n'; exit 0
fi
if printf '%s' "$ARGS" | grep -q "/v1/blocks/"; then
  printf '{"object":"list","results":[],"has_more":false}\n'; exit 0
fi
printf '{"object":"list","results":[],"has_more":false}\n'; exit 0
SH
chmod +x "$FAKE_BIN/curl"
OUT=$(HOME="$FAKE_HOME" ZHC_STATE_FILE="$FIXTURE_STATE" ZHC_NOTION_ENV_FILE="$ENV_FILE" \
  PATH="$FAKE_BIN:$PATH" NOTION_API_TOKEN="ntn_CLIENTTOKEN000000000000000000000000000000000" \
  ZHC_AGENCY_NOTION_TOKEN="ntn_AGENCYTOKEN000000000000000000000000000000000" \
  ZHC_AGENCY_NOTION_PARENT_PAGE_ID="$AGENCY_PARENT" \
  ZHC_SKIP_TG_PREFLIGHT=1 \
  bash "$CREATE_NOTION" 2>&1)
T5_RC=$?
if [[ $T5_RC -eq 0 ]]; then
  pass "Tier 2 completed successfully (rc 0 -- closeout leg passes)"
else
  fail "Tier 2 did not complete (rc=$T5_RC). Output tail: $(printf '%s' "$OUT" | tr '\n' ' ' | tail -c 300)"
fi
if [[ "$(read_state '.notionTier')" == "2" ]]; then
  pass "recorded notionTier=2 (agency fallback used)"
else
  fail "notionTier not 2 (got: $(read_state '.notionTier'))"
fi
if [[ "$(read_state '.notionRootPageUrl')" == *"notion.site"* ]]; then
  pass "delivered the VIEW-ONLY public subpage url (public_url)"
else
  fail "did not deliver the view-only public_url (got: $(read_state '.notionRootPageUrl'))"
fi
if [[ "$(read_state '.notionTier2ShareState')" == "view-only-public" ]]; then
  pass "share state recorded as view-only-public"
else
  fail "share state not view-only-public (got: $(read_state '.notionTier2ShareState'))"
fi

# ════════════════════════════════════════════════════════════
# T6: no client name or agency token committed in the source files we ship.
# ════════════════════════════════════════════════════════════
echo "T6: shipped source carries no real token / no committed agency secret"
SRC_FILES=("$CREATE_NOTION" "$ENSURE_PARENT" "$SKILL_DIR/scripts/run-closeout.sh")
LEAK=0
for f in "${SRC_FILES[@]}"; do
  # Real Notion integration tokens look like ntn_<40+ alnum>. The placeholders in
  # docs/code must NOT be a concrete secret value. Assert no ntn_ token literal.
  if grep -nE 'ntn_[A-Za-z0-9]{40,}' "$f" >/dev/null 2>&1; then
    fail "possible committed Notion token in $(basename "$f")"; LEAK=1
  fi
done
[[ $LEAK -eq 0 ]] && pass "no concrete Notion token literal committed in shipped scripts"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo " RESULT: $PASS passed, $FAIL failed"
echo "--------------------------------------------------------"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
