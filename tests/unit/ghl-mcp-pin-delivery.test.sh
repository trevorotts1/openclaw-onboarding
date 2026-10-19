#!/usr/bin/env bash
# tests/unit/ghl-mcp-pin-delivery.test.sh — v22.0.0
#
# Proves R1 (config/ reaches a BOX at $OC_CONFIG/config, the FIRST candidate
# every consumer's resolver tries) and R9 (the launch surfaces fail closed on an
# unverified/unvetted pin) against a SIMULATED BOX LAYOUT — never the repo
# layout, because the repo layout is the one layout where the v21.5.0 bug was
# invisible. v22.0.0 adds the retirement contract on top: the community pin
# itself must NOT be delivered any more (see the v22.0.0 note below).
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
# v22.0.0 (W07/GU-019) — THE COMMUNITY MCP IS RETIRED, and this file now proves
# the retirement contract around the same primitives:
#   (B)  a RETIRED box — supervision surfaces pruned, community pin NOT
#        delivered — passes the box-layout gate rc=0.
#   (M)  install.sh's config/ block still delivers config/, deliberately does
#        NOT deliver config/ghl-mcp-pin.env, and says so.
#   (M2) a pin that survives the removal is condemned loudly (a surviving pin
#        is an active resurrection trigger), never passed over.
#   (F)/(I)/(J2) SKIPPED_NO_CREDS is gone. The legacy pin gate still runs first
#        (no pin -> PIN_UNVERIFIED, bad verdict/digest -> PIN_UNVETTED), and a
#        pin that CLEARS it now earns START_REFUSED_RETIRED: nothing is built,
#        cloned or started. Cases (E)/(G)/(H)/(J)/(J3)/(J4) are unchanged.
#
# Exit 0 = all cases behaved. Exit 1 = one or more did not (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-pin-delivery.test.sh (v22.0.0) ==="
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

# ── (A) A NOT-yet-retired box HARD-FAILS the box-layout gate ─────────────────
# This is the regression under test. A box that still carries the retired
# lifecycle scripts is an armed box: the gate must return rc=1. If this case
# ever starts passing rc=0, the gate has stopped noticing armed boxes and the
# whole guardrail is dead. (v21.6.0 asserted the same rc=1 for the missing pin;
# v22.0.0's box branch asserts the delivered tree, not config/.)
BOX="$(_make_box no-config)"
# GHL-101 (B2): the RETIREMENT TOOL is now retained on the box by design, and it
# carries the retirement marker, so the gate correctly treats it as inert. To
# still prove the gate NOTICES an armed box, strip the marker from the planted
# copy: without it the same file is a live launcher and must hard-fail. The
# retained-tombstone path is covered by case (B) below.
python3 - "$BOX/.openclaw/scripts/ghl-mcp-autostart.sh" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p).read()
t = re.sub(r'.*(GHL_MCP_RETIRED|RETIRED_VERIFIED_OFF|START_REFUSED_RETIRED).*\n?', '', t)
open(p, 'w').write(t)
PY
RC=0
HOME="$BOX" bash "$BOX/.openclaw/scripts/qc-assert-ghl-mcp-supervised.sh" --quiet >/dev/null 2>&1 || RC=$?
if [ "$RC" = "1" ]; then
  pass "(A) box layout still carrying the retired lifecycle scripts -> static gate rc=1 (an armed box is a hard fail)"
else
  fail "(A) an armed box layout returned rc=$RC (expected 1) — the gate no longer notices a box that still ships the retired launcher"
fi
rm -rf "$BOX"

# ── (B) AFTER the retirement transaction: a RETIRED box passes the gate ──────
# v22.0.0 (W07/GU-019). The community MCP is RETIRED, so "the delivery satisfies
# the gate" now means: the two shipped installer blocks have run and left a box
# with NO lifecycle script and NO community pin.
#   1. GHL-MCP-RETIREMENT-SCRIPTS prunes the supervision surfaces (cp is
#      additive, so every roll would otherwise re-deliver them).
#   2. CANONICAL-CONFIG-DELIVERY lands config/ but deliberately does NOT
#      deliver config/ghl-mcp-pin.env, and deletes a copy an earlier release
#      left behind (a surviving pin is a resurrection trigger).
# Both blocks are extracted verbatim from install.sh, so this case goes red if
# either stops doing its half.
RBOX="$(_make_box with-config)"
mkdir -p "$RBOX/.openclaw/onboarding"
cp -Rp "$REPO_ROOT/config" "$RBOX/.openclaw/onboarding/"
PRUNEBLK="$(mktemp)"
CNFBLOCK="$(mktemp)"
awk '/^# >>> GHL-MCP-RETIREMENT-SCRIPTS-BEGIN/,/^# <<< GHL-MCP-RETIREMENT-SCRIPTS-END/' "$REPO_ROOT/install.sh" > "$PRUNEBLK"
awk '/^# >>> CANONICAL-CONFIG-DELIVERY-BEGIN/,/^# <<< CANONICAL-CONFIG-DELIVERY-END/' "$REPO_ROOT/install.sh" > "$CNFBLOCK"
if [ ! -s "$PRUNEBLK" ] || [ ! -s "$CNFBLOCK" ]; then
  fail "(B) could not extract install.sh's retirement-prune + config-delivery blocks — an anchor comment moved"
else
  SKILLS_DIR="$RBOX/.openclaw/skills" ONBOARDING_DIR="$RBOX/.openclaw/onboarding" \
    bash -c 'note(){ printf "NOTE %s\n" "$*"; }; success(){ printf "SUCCESS %s\n" "$*"; }; warn(){ printf "WARN %s\n" "$*"; }; . "$1"; . "$2"' \
    _ "$PRUNEBLK" "$CNFBLOCK" >/dev/null 2>&1
  # The gate is pruned off the box along with the rest, so run a copy that sits
  # OUTSIDE the delivered tree — the running gate's own parent decides whether
  # it is looking at a repo layout or a box layout.
  GATECOPY="$(mktemp -d)/bin"
  mkdir -p "$GATECOPY"
  cp "$REPO_ROOT/scripts/qc-assert-ghl-mcp-supervised.sh" "$GATECOPY/"
  RC=0
  HOME="$RBOX" bash "$GATECOPY/qc-assert-ghl-mcp-supervised.sh" --quiet >/dev/null 2>&1 || RC=$?
  _B_PROBLEMS=""
  [ "$RC" = "0" ] || _B_PROBLEMS="$_B_PROBLEMS gate rc=$RC"
  [ -e "$RBOX/.openclaw/config/ghl-mcp-pin.env" ] \
    && _B_PROBLEMS="$_B_PROBLEMS (the pin was delivered — a stale pin is an active resurrection trigger)"
  # GHL-101 (B2) INVERTED THIS ASSERTION DELIBERATELY. The retirement tool must
  # SURVIVE on the box: the updater deletes its own source checkout, so pruning
  # ghl-mcp-autostart.sh would leave the box unable to ever run --retire again.
  # The contract is no longer "the launcher is gone"; it is "the launcher is
  # retained AND inert". A retained launcher without the retirement marker is
  # an armed box and still fails here.
  if [ ! -e "$RBOX/.openclaw/scripts/ghl-mcp-autostart.sh" ]; then
    _B_PROBLEMS="$_B_PROBLEMS (the retirement tool was pruned — the box can no longer run --retire)"
  elif ! grep -qE 'GHL_MCP_RETIRED|RETIRED_VERIFIED_OFF|START_REFUSED_RETIRED' \
       "$RBOX/.openclaw/scripts/ghl-mcp-autostart.sh" 2>/dev/null; then
    _B_PROBLEMS="$_B_PROBLEMS (the retained launcher carries no retirement marker — it is an armed box)"
  fi
  if [ -z "$_B_PROBLEMS" ]; then
    pass "(B) a retired box — supervision surfaces pruned, community pin NOT delivered — passes the static gate rc=0"
  else
    fail "(B) the retired-box contract is broken:$_B_PROBLEMS"
    HOME="$RBOX" bash "$GATECOPY/qc-assert-ghl-mcp-supervised.sh" 2>&1 | grep -F 'INVARIANT VIOLATED' | sed 's/^/        /'
  fi
fi
rm -f "$PRUNEBLK" "$CNFBLOCK"
rm -rf "$RBOX"

# ── (C) EVERY consumer's resolver actually hits the delivered file ───────────
# A gate that passes because ONE resolver happens to hit is not the fix. Each
# launch surface is checked independently, in the box layout, by asking it
# where it resolved the pin.
# (This box is the PRE-retirement layout on purpose: R1 is about where a pin
# that IS present is found, and (B)/(M) above prove the pin is no longer
# delivered.)
BOX="$(_make_box with-config)"
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

# ── (F) A correctly-vetted box still gets START_REFUSED_RETIRED ──────────────
# v22.0.0: SKIPPED_NO_CREDS is gone — nothing is ever started. The legacy pin
# gate still runs FIRST (a box with no pin already refused above with
# PIN_UNVERIFIED), and only a pin that PASSES it reaches the retirement
# refusal. So START_REFUSED_RETIRED here proves both halves: the pin was
# accepted AND the start path is retired.
_S="$(_autostart_status "$BOX")"
case "$_S" in
  *START_REFUSED_RETIRED*) pass "(F) pin present + verdict CLEAN -> the legacy pin gate passes and the start path then refuses with START_REFUSED_RETIRED (nothing is built or started)" ;;
  *)                       fail "(F) a CLEAN pin produced '$_S' (expected START_REFUSED_RETIRED) — either the pin gate bricked a correctly-vetted box or the retired start path is reachable again" ;;
esac
if [ -d "$BOX/mcp-servers" ]; then
  fail "(F2) the retirement refusal still created $BOX/mcp-servers — it must not clone or build anything"
else
  pass "(F2) the retirement refusal created no mcp-servers tree — nothing was cloned or built"
fi

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

# ── (I) Digest RECOMPUTED -> the pin gate passes, then retirement refuses ────
# The tool's happy path still has to get PAST the pin gate: the refusal it
# earns must be START_REFUSED_RETIRED (retired service), never PIN_UNVETTED
# (a stale digest).
NEW_DIGEST="$(bash "$DIGEST_TOOL" compute "$PINF")"
sed -i.bak "s|^GHL_MCP_PIN_VETTED_DIGEST=.*|GHL_MCP_PIN_VETTED_DIGEST=\"$NEW_DIGEST\"|" "$PINF" && rm -f "$PINF.bak"
_S="$(_autostart_status "$STALE")"
case "$_S" in
  *START_REFUSED_RETIRED*) pass "(I) a correctly re-digested pin clears the digest check (no PIN_UNVETTED) and is then refused as RETIRED" ;;
  *PIN_UNVETTED*)         fail "(I) a correctly re-digested pin still produced '$_S' — the digest check is over-strict" ;;
  *)                      fail "(I) a correctly re-digested pin produced '$_S' (expected START_REFUSED_RETIRED) — the retired start path is reachable again" ;;
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
  *START_REFUSED_RETIRED*) pass "(J2) an override WITH a matching v2 vetting digest clears the pin gate and is then refused as RETIRED (the escape hatch still vets; it never starts anything)" ;;
  *PIN_UNVETTED*)         fail "(J2) a properly-vetted override was refused at the pin gate: '$_S' — the override contract is unusable" ;;
  *)                      fail "(J2) a properly-vetted override produced '$_S' (expected START_REFUSED_RETIRED) — the retired start path is reachable again" ;;
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

# ── (M) The SHIPPED install.sh config block delivers config/ WITHOUT the pin ──
# v22.0.0 (W07/GU-019): the config/ DELIVERY CONTRACT stays (cron.d, the
# bootstrap examples and the sovereignty denylist are still read from this
# destination) but the community pin is removed right after the copy — the
# launch surfaces were fail-closed on it, so a delivered pin is a resurrection
# trigger. Extracted from the live installer and run with stubbed reporters, so
# a future edit that drops the copy, the removal, or the assertion fails here.
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
  if [ ! -e "$SIM/config/ghl-mcp-pin.env" ] \
     && [ -e "$SIM/config/cron.d" ] \
     && printf '%s' "$OUT" | grep -q 'deliberately NOT delivered'; then
    pass "(M) install.sh's config/ block delivers config/ next to scripts/, delivers NO ghl-mcp-pin.env, and reports that fact (RETIRED)"
  else
    fail "(M) install.sh's config/ block broke the retirement contract (pin present? $([ -e "$SIM/config/ghl-mcp-pin.env" ] && echo yes || echo no); cron.d present? $([ -e "$SIM/config/cron.d" ] && echo yes || echo no)). Output: $OUT"
  fi
  # Negative: a pin that SURVIVES the removal must be condemned loudly, never
  # passed over. A directory of that name cannot be removed by `rm -f`, which
  # is exactly the "check ownership/permissions" case the block warns about.
  SIM2="$(mktemp -d)"; mkdir -p "$SIM2/skills" "$SIM2/onboarding" "$SIM2/config/ghl-mcp-pin.env"
  cp -Rp "$REPO_ROOT/config" "$SIM2/onboarding/"
  OUT2="$( SKILLS_DIR="$SIM2/skills" ONBOARDING_DIR="$SIM2/onboarding"            bash -c 'success(){ printf "SUCCESS %s\n" "$*"; }; warn(){ printf "WARN %s\n" "$*"; }; . "$1"' _ "$BLKTMP" 2>&1 )"
  if printf '%s' "$OUT2" | grep -q 'WARN' \
     && printf '%s' "$OUT2" | grep -q 'resurrection trigger' \
     && ! printf '%s' "$OUT2" | grep -q '^SUCCESS'; then
    pass "(M2) a pin that survives the removal WARNS loudly and names the resurrection-trigger consequence (no silent continue, no false SUCCESS)"
  else
    fail "(M2) a surviving pin was not condemned loudly. Output: $OUT2"
  fi
  rm -rf "$SIM" "$SIM2"
fi
rm -f "$BLKTMP"

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
