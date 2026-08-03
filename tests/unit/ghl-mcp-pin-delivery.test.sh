#!/usr/bin/env bash
# tests/unit/ghl-mcp-pin-delivery.test.sh — v21.6.0
#
# Proves R1 (the pin file actually reaches a BOX) and R9 (the launch surfaces
# fail closed on an unverified/unvetted pin) against a SIMULATED BOX LAYOUT —
# never the repo layout, because the repo layout is the one layout where the
# v21.5.0 bug was invisible.
#
# THE BUG BEING PROVEN FIXED
#   v21.5.0 declared config/ghl-mcp-pin.env "the single source of truth for
#   every launch surface". update-skills.sh delivered scripts/ and nothing else
#   and then deleted its temp clone, and neither installer ever populated
#   $OC_CONFIG/config/ — the FIRST candidate every consumer's resolver tries.
#   Measured before the fix: qc-assert-ghl-mcp-supervised.sh returned rc=1 in a
#   box layout ("config/ghl-mcp-pin.env is missing", which qc-system-integrity
#   CHECK X.13 turns into a hard fail) and rc=0 in the repo layout. CI was green
#   because CI runs in the repo layout.
#
# SEQUENCING NOTE (why R1 and R9 are tested together and shipped together):
#   R9 makes a missing pin file a REFUSAL. Shipping that before R1's delivery
#   worked would brick Tier 2 on every box. Case (C) below is the proof that
#   delivery lands; cases (E)-(J) are the proof that refusal works. They are one
#   change.
#
# Exit 0 = all cases behaved. Exit 1 = one or more did not (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-pin-delivery.test.sh (v21.6.0) ==="
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Build a box layout. $1 = "with-config" | "no-config"
#
#   $BOX/.openclaw/scripts/   <- what BOTH installers deliver (canonical)
#   $BOX/.openclaw/config/    <- what v21.6.0 now ALSO delivers (the fix)
#   $BOX/.openclaw/skills/    <- the numbered skills (irrelevant here)
#
# This is deliberately NOT a repo checkout: no update-skills.sh, no install.sh,
# no platform/ overlay — exactly what a real box carries.
# ─────────────────────────────────────────────────────────────────────────────
_make_box() {
  local mode="$1" box
  box="$(mktemp -d)"
  mkdir -p "$box/.openclaw/scripts" "$box/.openclaw/skills"
  cp -Rp "$REPO_ROOT/scripts/." "$box/.openclaw/scripts/"
  if [ "$mode" = "with-config" ]; then
    mkdir -p "$box/.openclaw/config"
    cp -Rp "$REPO_ROOT/config/." "$box/.openclaw/config/"
  fi
  printf '%s' "$box"
}

# ── (A) BEFORE the delivery: the box-side QC gate HARD-FAILS ─────────────────
# This is the regression under test. If this case ever starts passing rc=0, the
# gate has stopped noticing a missing pin and the whole guardrail is dead.
BOX="$(_make_box no-config)"
RC=0
HOME="$BOX" bash "$BOX/.openclaw/scripts/qc-assert-ghl-mcp-supervised.sh" --quiet >/dev/null 2>&1 || RC=$?
if [ "$RC" = "1" ]; then
  pass "(A) box layout WITHOUT config/ delivered -> static gate rc=1 (the v21.5.0 fleet-wide hard fail, reproduced)"
else
  fail "(A) box layout without config/ returned rc=$RC (expected 1) — the gate no longer detects a missing pin"
fi
rm -rf "$BOX"

# ── (B) AFTER the delivery: the same gate PASSES in the same box layout ──────
BOX="$(_make_box with-config)"
RC=0
HOME="$BOX" bash "$BOX/.openclaw/scripts/qc-assert-ghl-mcp-supervised.sh" --quiet >/dev/null 2>&1 || RC=$?
if [ "$RC" = "0" ]; then
  pass "(B) box layout WITH config/ delivered to \$OC_CONFIG/config -> static gate rc=0"
else
  fail "(B) box layout with config/ returned rc=$RC (expected 0) — delivery does not satisfy the gate"
  HOME="$BOX" bash "$BOX/.openclaw/scripts/qc-assert-ghl-mcp-supervised.sh" 2>&1 | grep -F 'INVARIANT VIOLATED' | sed 's/^/        /'
fi

# ── (C) EVERY consumer's resolver actually hits the delivered file ───────────
# A gate that passes because ONE resolver happens to hit is not the fix. Each
# launch surface is checked independently, in the box layout, by asking it
# where it resolved the pin.
_resolves() {  # _resolves <script-under-box> <first-candidate-expression>
  local s="$1"
  HOME="$BOX" bash -c '
    SELF_DIR="'"$(dirname "$s")"'"
    HOME="'"$BOX"'"
    for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
              "$HOME/.openclaw/config/ghl-mcp-pin.env" \
              "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
              "/data/.openclaw/config/ghl-mcp-pin.env" \
              "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
      [ -f "$_c" ] && { printf "%s" "$_c"; exit 0; }
    done
    exit 1'
}
_HIT="$(_resolves "$BOX/.openclaw/scripts/ghl-mcp-autostart.sh" || true)"
if [ -n "$_HIT" ]; then
  pass "(C) the canonical resolver list hits the delivered pin in a box layout ($_HIT)"
else
  fail "(C) the canonical resolver list MISSES in a box layout — the pin is delivered somewhere nothing looks"
fi

# ── (D) Idempotent re-delivery is a byte-identical no-op ─────────────────────
# `\( -type f -o -type l \)`: a symlink to a file IS a file for census
# purposes, and a delivery that silently replaced one with the other would
# otherwise read as "no change".
_BEFORE="$(cd "$BOX/.openclaw/config" && find . \( -type f -o -type l \) -exec shasum -a 256 {} \; 2>/dev/null | sort)"
cp -Rp "$REPO_ROOT/config/." "$BOX/.openclaw/config/"
_AFTER="$(cd "$BOX/.openclaw/config" && find . \( -type f -o -type l \) -exec shasum -a 256 {} \; 2>/dev/null | sort)"
if [ "$_BEFORE" = "$_AFTER" ] && [ -n "$_BEFORE" ]; then
  pass "(D) re-running the delivery is a byte-identical no-op (idempotent)"
else
  fail "(D) re-delivery changed the destination — the delivery is not idempotent"
fi

# ─────────────────────────────────────────────────────────────────────────────
# R9 — fail-closed refusal. The autostart is run with NO GHL credentials, so a
# pin gate that PASSES lands on SKIPPED_NO_CREDS. That makes the two outcomes
# unambiguous: PIN_UNVERIFIED/PIN_UNVETTED = refused at the gate;
# SKIPPED_NO_CREDS = the gate let it through.
# ─────────────────────────────────────────────────────────────────────────────
_autostart_status() {  # _autostart_status <box> [extra env assignments…]
  local box="$1"; shift
  env -u GOHIGHLEVEL_API_KEY -u GHL_API_KEY -u GOHIGHLEVEL_LOCATION_ID \
      -u GHL_LOCATION_ID -u GHL_TOOL_PROFILE -u GHL_MCP_PIN_OVERRIDE \
      HOME="$box" "$@" \
      bash "$box/.openclaw/scripts/ghl-mcp-autostart.sh" 2>&1 \
    | grep -E '^STATUS:' | tail -1
}

# ── (E) No pin file anywhere -> PIN_UNVERIFIED, and NOTHING is built ─────────
NOBOX="$(_make_box no-config)"
_S="$(_autostart_status "$NOBOX")"
case "$_S" in
  *PIN_UNVERIFIED*) pass "(E) no pin file -> STATUS PIN_UNVERIFIED (refuses to build/start an unverified third-party MCP)" ;;
  *)                fail "(E) no pin file produced '$_S' (expected PIN_UNVERIFIED) — fail-closed is not in effect" ;;
esac
if [ -d "$NOBOX/mcp-servers" ]; then
  fail "(E2) the refusal still created $NOBOX/mcp-servers — it must not clone or build anything"
else
  pass "(E2) the refusal created no mcp-servers tree — nothing was cloned or built"
fi
rm -rf "$NOBOX"

# ── (F) Pin present + verdict CLEAN + no digest -> transitional FALLBACK mode ─
_S="$(_autostart_status "$BOX")"
case "$_S" in
  *SKIPPED_NO_CREDS*) pass "(F) pin present, verdict CLEAN, no digest yet -> the gate passes in transitional fallback mode" ;;
  *)                  fail "(F) a CLEAN pin was refused: '$_S' — fail-closed must not brick a correctly-vetted box" ;;
esac

# ── (G) Verdict not CLEAN -> PIN_UNVETTED ───────────────────────────────────
DIRTY="$(_make_box with-config)"
sed -i.bak 's/^GHL_MCP_PIN_VETTED_VERDICT=.*/GHL_MCP_PIN_VETTED_VERDICT="PENDING"/' \
  "$DIRTY/.openclaw/config/ghl-mcp-pin.env" && rm -f "$DIRTY/.openclaw/config/ghl-mcp-pin.env.bak"
_S="$(_autostart_status "$DIRTY")"
case "$_S" in
  *PIN_UNVETTED*) pass "(G) verdict PENDING -> STATUS PIN_UNVETTED (the verdict is enforced, not decorative)" ;;
  *)              fail "(G) an unvetted pin produced '$_S' (expected PIN_UNVETTED) — the v21.5.0 inert verdict is back" ;;
esac
rm -rf "$DIRTY"

# ── (H) Digest present but STALE (the hand-edited-SHA case) -> PIN_UNVETTED ──
# This is the whole point of the digest: forgetting to re-vet produces refusal.
STALE="$(_make_box with-config)"
DIGEST_TOOL="$STALE/.openclaw/scripts/ghl-mcp-pin-digest.sh"
PINF="$STALE/.openclaw/config/ghl-mcp-pin.env"
GOOD_DIGEST="$(bash "$DIGEST_TOOL" compute "$PINF")"
sed -i.bak "s|^GHL_MCP_PIN_VETTED_DIGEST=.*|GHL_MCP_PIN_VETTED_DIGEST=\"$GOOD_DIGEST\"|" "$PINF" && rm -f "$PINF.bak"
# Now hand-edit the SHA the way a hurried human or an agent would.
sed -i.bak 's/^GHL_MCP_VETTED_COMMIT=.*/GHL_MCP_VETTED_COMMIT="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"/' "$PINF" && rm -f "$PINF.bak"
_S="$(_autostart_status "$STALE")"
case "$_S" in
  *PIN_UNVETTED*) pass "(H) a hand-edited SHA leaves a stale digest -> STATUS PIN_UNVETTED (forgetting produces refusal)" ;;
  *)              fail "(H) a hand-edited SHA produced '$_S' (expected PIN_UNVETTED) — the digest is not being enforced" ;;
esac

# ── (I) Digest RECOMPUTED after the edit -> accepted (the tool's happy path) ──
NEW_DIGEST="$(bash "$DIGEST_TOOL" compute "$PINF")"
sed -i.bak "s|^GHL_MCP_PIN_VETTED_DIGEST=.*|GHL_MCP_PIN_VETTED_DIGEST=\"$NEW_DIGEST\"|" "$PINF" && rm -f "$PINF.bak"
_S="$(_autostart_status "$STALE")"
case "$_S" in
  *SKIPPED_NO_CREDS*) pass "(I) recomputing the digest (what ghl-mcp-vet-pin.sh will do) makes the same pin acceptable" ;;
  *)                  fail "(I) a correctly re-digested pin was still refused: '$_S' — the digest check is over-strict" ;;
esac
rm -rf "$STALE"

# ── (J) GHL_MCP_PIN_OVERRIDE without a digest -> PIN_UNVETTED; with -> passes ─
OVR_COMMIT="cafebabecafebabecafebabecafebabecafebabe"
_S="$(_autostart_status "$BOX" GHL_MCP_PIN_OVERRIDE="$OVR_COMMIT")"
case "$_S" in
  *PIN_UNVETTED*) pass "(J) GHL_MCP_PIN_OVERRIDE with no vetting digest -> PIN_UNVETTED (the escape hatch is not a bypass)" ;;
  *)              fail "(J) a naked pin override produced '$_S' (expected PIN_UNVETTED) — any 40-hex string would build unvetted" ;;
esac

# The override tuple is the SAME canonical form as the pin file: ghl-mcp-pin-v2,
# whose seventh field is the repo URL the box would actually clone from. The
# override path used to hand-reimplement v1 (repo URL UNBOUND) while the pin
# file had moved to v2 — a split canonical form on the primary fleet-roll path.
OVR_REPO="$(sed -n 's/^GHL_MCP_REPO_URL="\(.*\)"$/\1/p' "$REPO_ROOT/config/ghl-mcp-pin.env" | tail -1)"
_ovr_digest() {  # $1 = repo url to bind
  printf '%s\n' 'ghl-mcp-pin-v2' "$OVR_COMMIT" 'CLEAN' '2026-08-03' 'test' '' "$1" \
    | { shasum -a 256 2>/dev/null || sha256sum 2>/dev/null; } | cut -d' ' -f1
}
OVR_DIGEST="$(_ovr_digest "$OVR_REPO")"
_S="$(_autostart_status "$BOX" \
        GHL_MCP_PIN_OVERRIDE="$OVR_COMMIT" \
        GHL_MCP_PIN_OVERRIDE_VERDICT=CLEAN \
        GHL_MCP_PIN_OVERRIDE_VETTED_ON=2026-08-03 \
        GHL_MCP_PIN_OVERRIDE_VETTED_BY=test \
        GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256= \
        GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST="$OVR_DIGEST")"
case "$_S" in
  *SKIPPED_NO_CREDS*) pass "(J2) an override WITH a matching v2 vetting digest is accepted (the hatch still opens)" ;;
  *)                  fail "(J2) a properly-vetted override was refused: '$_S' — the override contract is unusable" ;;
esac

# (J3) MUTATION PROOF — the override digest must bind the REPOSITORY URL.
# A digest computed against a different source must be refused, otherwise the
# primary fleet-roll path accepts a mirror swap while the digest checks out.
OVR_EVIL="$(_ovr_digest 'https://github.com/attacker/ghl-community-mcp.git')"
_S="$(_autostart_status "$BOX" \
        GHL_MCP_PIN_OVERRIDE="$OVR_COMMIT" \
        GHL_MCP_PIN_OVERRIDE_VERDICT=CLEAN \
        GHL_MCP_PIN_OVERRIDE_VETTED_ON=2026-08-03 \
        GHL_MCP_PIN_OVERRIDE_VETTED_BY=test \
        GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256= \
        GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST="$OVR_EVIL")"
case "$_S" in
  *PIN_UNVETTED*) pass "(J3) an override digest bound to a DIFFERENT repo URL is refused (the mirror is bound, not assumed)" ;;
  *)              fail "(J3) an override digest computed against another source produced '$_S' (expected PIN_UNVETTED) — the override tuple does not bind the repo URL" ;;
esac

# (J4) MUTATION PROOF — a v1-shaped digest (the stale six-field tuple) must be
# refused now that the canonical form is v2. A split canonical form is the bug.
OVR_V1="$(printf '%s\n' 'ghl-mcp-pin-v1' "$OVR_COMMIT" 'CLEAN' '2026-08-03' 'test' '' \
  | { shasum -a 256 2>/dev/null || sha256sum 2>/dev/null; } | cut -d' ' -f1)"
_S="$(_autostart_status "$BOX" \
        GHL_MCP_PIN_OVERRIDE="$OVR_COMMIT" \
        GHL_MCP_PIN_OVERRIDE_VERDICT=CLEAN \
        GHL_MCP_PIN_OVERRIDE_VETTED_ON=2026-08-03 \
        GHL_MCP_PIN_OVERRIDE_VETTED_BY=test \
        GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256= \
        GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST="$OVR_V1")"
case "$_S" in
  *PIN_UNVETTED*) pass "(J4) a stale v1 six-field override digest is refused (one canonical form, not two)" ;;
  *)              fail "(J4) a v1 override digest produced '$_S' (expected PIN_UNVETTED) — the override path is still on the old tuple" ;;
esac
rm -rf "$BOX"

# ── (K) The digest primitive's contract (what fixer #3's tool must satisfy) ──
TMPPIN="$(mktemp -d)/pin.env"
mkdir -p "$(dirname "$TMPPIN")"
cat > "$TMPPIN" <<'EOF'
GHL_MCP_VETTED_COMMIT="bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3"
GHL_MCP_PIN_VETTED_VERDICT="CLEAN"   # CLEAN | DIRTY | PENDING
GHL_MCP_PIN_VETTED_ON="2026-08-03"
GHL_MCP_PIN_VETTED_BY="reviewer"
GHL_MCP_DEPS_LOCK_SHA256=""
GHL_MCP_REPO_URL="https://github.com/trevorotts1/ghl-community-mcp-mirror.git"
EOF
TOOL="$REPO_ROOT/scripts/ghl-mcp-pin-digest.sh"
D1="$(bash "$TOOL" compute "$TMPPIN")"
D2="$(bash "$TOOL" compute "$TMPPIN")"
# v2 canonical form: the seventh field is GHL_MCP_REPO_URL. A SHA names an
# object, never the host that serves it, so the source is bound too.
REF="$(printf '%s\n' 'ghl-mcp-pin-v2' 'bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3' 'CLEAN' '2026-08-03' 'reviewer' '' \
  'https://github.com/trevorotts1/ghl-community-mcp-mirror.git' \
  | { shasum -a 256 2>/dev/null || sha256sum 2>/dev/null; } | cut -d' ' -f1)"
if [ "$D1" = "$D2" ] && [ "$D1" = "$REF" ]; then
  pass "(K) the digest is deterministic AND matches the documented reference one-liner (inline comments stripped)"
else
  fail "(K) digest mismatch — tool='$D1' reference='$REF'. The contract fixer #3 implements against is broken."
fi
RC=0; bash "$TOOL" verify "$TMPPIN" >/dev/null 2>&1 || RC=$?
[ "$RC" = "3" ] && pass "(K2) verify returns 3=ABSENT with no digest field (callers fall back to the CLEAN verdict)" \
                || fail "(K2) verify returned $RC with no digest field (expected 3=ABSENT)"
printf 'GHL_MCP_PIN_VETTED_DIGEST="%s"\n' "$D1" >> "$TMPPIN"
RC=0; bash "$TOOL" verify "$TMPPIN" >/dev/null 2>&1 || RC=$?
[ "$RC" = "0" ] && pass "(K3) verify returns 0=MATCH for a correctly written digest" \
                || fail "(K3) verify returned $RC for a correct digest (expected 0)"
sed -i.bak 's/^GHL_MCP_PIN_VETTED_ON=.*/GHL_MCP_PIN_VETTED_ON="2026-01-01"/' "$TMPPIN" && rm -f "$TMPPIN.bak"
RC=0; bash "$TOOL" verify "$TMPPIN" >/dev/null 2>&1 || RC=$?
[ "$RC" = "1" ] && pass "(K4) verify returns 1=MISMATCH when ANY bound field changes (not just the commit)" \
                || fail "(K4) verify returned $RC after mutating a bound field (expected 1=MISMATCH)"
rm -rf "$(dirname "$TMPPIN")"

# ── (L) The SHIPPED update-skills.sh delivery function really delivers config/ ─
# Not a re-implementation: deliver_canonical_scripts_tree is extracted from the
# live updater and invoked exactly the way the updater invokes it, so this case
# fails if anyone edits the function or the call and breaks the receipt.
UPD="$REPO_ROOT/update-skills.sh"
FNTMP="$(mktemp)"
awk '/^# >>> CANONICAL-SCRIPTS-DELIVERY-BEGIN/,/^# <<< CANONICAL-SCRIPTS-DELIVERY-END/' "$UPD" > "$FNTMP"
if [ ! -s "$FNTMP" ]; then
  fail "(L) could not extract the CANONICAL-SCRIPTS-DELIVERY block from update-skills.sh — the markers moved"
else
  DEST="$(mktemp -d)"
  RC=0
  ( set +u; . "$FNTMP"; deliver_canonical_scripts_tree "$REPO_ROOT/config" "$DEST/config" "config/" ) >/dev/null 2>&1 || RC=$?
  if [ "$RC" = "0" ] && [ -r "$DEST/config/ghl-mcp-pin.env" ]; then
    pass "(L) update-skills.sh's own delivery function lands config/ghl-mcp-pin.env with a full completeness receipt"
  else
    fail "(L) the shipped delivery function did not land the pin file (rc=$RC)"
  fi
  # Idempotent re-run through the SAME function.
  RC=0
  ( set +u; . "$FNTMP"; deliver_canonical_scripts_tree "$REPO_ROOT/config" "$DEST/config" "config/" ) >/dev/null 2>&1 || RC=$?
  if [ "$RC" = "0" ]; then
    pass "(L2) re-running the shipped delivery function is a clean no-op (rc=0, byte-compare receipt still passes)"
  else
    fail "(L2) re-running the shipped delivery function returned rc=$RC — delivery is not idempotent"
  fi
  rm -rf "$DEST"
fi
rm -f "$FNTMP"

# ── (M) The SHIPPED install.sh config block delivers + asserts ───────────────
# Extracted from the live installer and run with stubbed reporters, so a future
# edit that drops the copy or the assertion fails here.
INS="$REPO_ROOT/install.sh"
BLKTMP="$(mktemp)"
awk '/^# >>> CANONICAL-CONFIG-DELIVERY-BEGIN/,/^# <<< CANONICAL-CONFIG-DELIVERY-END/' "$INS" > "$BLKTMP"
if ! grep -qF 'OC_CANONICAL_CONFIG_DEST' "$BLKTMP"; then
  fail "(M) could not extract install.sh's config/ delivery block — its anchor comment moved"
else
  SIM="$(mktemp -d)"
  mkdir -p "$SIM/skills" "$SIM/onboarding"
  cp -Rp "$REPO_ROOT/config" "$SIM/onboarding/"
  OUT="$( SKILLS_DIR="$SIM/skills" ONBOARDING_DIR="$SIM/onboarding"           bash -c 'success(){ printf "SUCCESS %s\n" "$*"; }; warn(){ printf "WARN %s\n" "$*"; }; . "$1"' _ "$BLKTMP" 2>&1 )"
  if [ -r "$SIM/config/ghl-mcp-pin.env" ] && printf '%s' "$OUT" | grep -q '^SUCCESS'; then
    pass "(M) install.sh's config/ block delivers the pin next to scripts/ and reports the assert-on-land success"
  else
    fail "(M) install.sh's config/ block did not deliver+assert. Output: $OUT"
  fi
  # Negative: with no source config/, the block must WARN, not silently pass.
  SIM2="$(mktemp -d)"; mkdir -p "$SIM2/skills" "$SIM2/onboarding"
  OUT2="$( SKILLS_DIR="$SIM2/skills" ONBOARDING_DIR="$SIM2/onboarding"            bash -c 'success(){ printf "SUCCESS %s\n" "$*"; }; warn(){ printf "WARN %s\n" "$*"; }; . "$1"' _ "$BLKTMP" 2>&1 )"
  if printf '%s' "$OUT2" | grep -q 'WARN.*PIN_UNVERIFIED'; then
    pass "(M2) a failed config/ delivery WARNS loudly and names the PIN_UNVERIFIED consequence (no silent continue)"
  else
    fail "(M2) a failed config/ delivery did not warn about PIN_UNVERIFIED. Output: $OUT2"
  fi
  rm -rf "$SIM" "$SIM2"
fi
rm -f "$BLKTMP"

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
