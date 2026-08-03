#!/usr/bin/env bash
# tests/unit/podcast-activation-install-path.test.sh
#
# roll-3-install-path: install.sh must GUARANTEE that the Podcast Production
# Engine (skill 58) activation layer lands in the skills dir on every fresh
# install, so a client box can never silently end up without the activation
# scripts (the Leanne-ticket failure class).
#
# Contract (act-8 gate alignment): the activation layer is NO-DAEMON. Exactly
# three build files are guaranteed: register-podcast-hook.sh,
# webhook/intake_handler.py (the deterministic first step of the route's
# controllerId runbook), and install-podcast-department.sh. There is NO
# podcast_controller.py and NO podcast_scheduler.py: the design has no
# controller daemon and no poller scheduler, and the only recurring podcast
# cron is the daily smoke test (podcast-smoke-test.py via openclaw cron).
#
# The terminal installer has NO per-skill file manifest: Step 5 copies every
# numbered skill directory wholesale, and the roll-3 block (inserted after
# the Skill 57 wiring, before the Step 6 banner) is the belt-and-suspenders
# per-file presence guarantee on top of that wholesale copy. This test
# extracts the REAL roll-3 block out of install.sh BY MARKER (so it survives
# future edits elsewhere in the file) and exercises it against fixture
# onboarding trees, plus static assertions on the direct-to-agent and
# mac-mini-onboarding install paths.
#
# Proves, against the REAL extracted code:
#   A. Fresh full source tree: all three activation files present at the
#      skills-dir destination afterwards, .sh files executable, zero warns.
#   B. Pre-existing complete copy (Step 5 wholesale copy already landed):
#      files left byte-identical, success reported, zero warns.
#   C. Partial copy (dest skill dir exists, intake handler missing): the
#      handler is repaired (copied in), existing files left intact, the
#      repair is announced, zero warns.
#   D. Source file missing from the onboarding package: warn emitted, exit
#      status stays 0 (a wiring hiccup never aborts the install), the
#      not-complete summary warn fires, no phantom file fabricated.
#   E. The block NEVER activates: it ensures delivery only, it invokes no
#      activation script (activation is per-client, owned by provision).
#   5. install.sh carries no per-skill FILE_LIST manifest that could exclude
#      the activation scripts (the installer is directory-enumeration based;
#      MAC_ENV_FILE_LIST is env-file discovery, not a skill manifest).
#   6. direct-to-agent-install.md names the three activation files, documents
#      the guard-activation-health.py verification, and keeps the delivery vs
#      per-client activation boundary.
#   7. mac-mini-onboarding/ has no podcast step (verified, not skipped; this
#      assertion flips if a podcast step is ever added there, at which point
#      the activation call must be wired).
#   8. Convention: zero em dashes in every line this unit added (the roll-3
#      block and the activation sections of direct-to-agent-install.md).
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
DTA_MD="$REPO_ROOT/direct-to-agent-install.md"
MAC_DIR="$REPO_ROOT/mac-mini-onboarding"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo "=== podcast-activation-install-path.test.sh ==="

[ -f "$INSTALL_SH" ] || { echo "FAIL: install.sh not found at $INSTALL_SH"; exit 1; }
[ -f "$DTA_MD" ] || { echo "FAIL: direct-to-agent-install.md not found at $DTA_MD"; exit 1; }
[ -d "$MAC_DIR" ] || { echo "FAIL: mac-mini-onboarding/ not found at $MAC_DIR"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- extraction (by marker, not line number) --------------------------------
# The block starts at the roll-3 marker comment and ends at the unset line
# that releases its scratch variables.
awk '
    /^# roll-3 \(podcast activation layer install guarantee\):/ { grab = 1 }
    grab { print }
    grab && /^unset _PODCAST_ACTIVATION_SKILL _PODCAST_ACTIVATION_FILES _ACT_FILE _ACT_SRC _ACT_DEST$/ { exit }
' "$INSTALL_SH" > "$WORK/block.sh"

if [ ! -s "$WORK/block.sh" ]; then
    echo "FAIL: could not extract the roll-3 activation block from install.sh (marker moved or block removed)"
    exit 1
fi
case "$(cat "$WORK/block.sh")" in
    *register-podcast-hook.sh*webhook/intake_handler.py*install-podcast-department.sh*) : ;;
    *) echo "FAIL: extracted roll-3 block does not name all three activation files; extraction or the block itself is broken"; exit 1 ;;
esac
if grep -q "podcast_controller.py\|podcast_scheduler.py" "$WORK/block.sh"; then
    echo "FAIL: the roll-3 block still references the excluded daemon files (podcast_controller.py / podcast_scheduler.py); the no-daemon contract is broken"
    exit 1
fi
bash -n "$WORK/block.sh" || { echo "FAIL: extracted roll-3 block is not valid bash"; exit 1; }
pass "roll-3 block extracted from install.sh by marker and parses as bash"

# --- fixture helpers ---------------------------------------------------------
ACT_FILES="scripts/register-podcast-hook.sh scripts/webhook/intake_handler.py scripts/install-podcast-department.sh"

make_src_tree() { # $1 = tree root; creates the three activation files under it
    local root="$1" f
    for f in $ACT_FILES; do
        mkdir -p "$root/58-podcast-production-engine/$(dirname "$f")"
        printf '#!/usr/bin/env bash\n# fixture %s\n' "$f" > "$root/58-podcast-production-engine/$f"
    done
}

run_block() { # $1 = onboarding dir, $2 = skills dir, $3 = tag
              # Runs the extracted block ONCE with stubbed warn/success and
              # the installer's own ONBOARDING_DIR/SKILLS_DIR/LOG_FILE
              # contract; output goes to $WORK/out-<tag>.txt, rc to
              # $WORK/rc-<tag>.
    local onb="$1" skd="$2" tag="$3" rc=0
    {
        cat <<EOF
set -euo pipefail
ONBOARDING_DIR="$onb"
SKILLS_DIR="$skd"
LOG_FILE="$WORK/$tag.log"
WARN_COUNT=0
warn() { printf "WARN: %s\n" "\$*"; WARN_COUNT=\$((WARN_COUNT + 1)); }
success() { printf "SUCCESS: %s\n" "\$*"; }
mkdir -p "\$SKILLS_DIR"
EOF
        cat "$WORK/block.sh"
        cat <<'EOF'
printf 'WARN_COUNT=%s\n' "$WARN_COUNT"
EOF
    } > "$WORK/run-$tag.sh"
    bash "$WORK/run-$tag.sh" > "$WORK/out-$tag.txt" 2>&1 || rc=$?
    echo "$rc" > "$WORK/rc-$tag"
}

# --- scenario A: fresh full source tree --------------------------------------
ONB_A="$WORK/src-a"; SKD_A="$WORK/skills-a"
mkdir -p "$ONB_A" "$SKD_A"
make_src_tree "$ONB_A"
run_block "$ONB_A" "$SKD_A" a
[ "$(cat "$WORK/rc-a")" = "0" ] && pass "scenario A: block exits 0 on a fresh full source tree" \
                                || fail "scenario A: block exited $(cat "$WORK/rc-a") (want 0)"
MISSING_A=0
for f in $ACT_FILES; do
    [ -f "$SKD_A/58-podcast-production-engine/$f" ] || { MISSING_A=1; fail "scenario A: $f not present at the skills-dir destination"; }
done
[ "$MISSING_A" = "0" ] && pass "scenario A: all three activation files delivered to the skills dir"
if [ -x "$SKD_A/58-podcast-production-engine/scripts/register-podcast-hook.sh" ] \
   && [ -x "$SKD_A/58-podcast-production-engine/scripts/install-podcast-department.sh" ]; then
    pass "scenario A: the two .sh activation scripts are executable at the destination"
else
    fail "scenario A: a .sh activation script is not executable at the destination"
fi
grep -q "^WARN_COUNT=0$" "$WORK/out-a.txt" \
    && pass "scenario A: zero warns when the source tree is complete" \
    || fail "scenario A: unexpected warns on a complete source tree"

# --- scenario B: dest already complete (Step 5 wholesale copy landed) --------
ONB_B="$WORK/src-b"; SKD_B="$WORK/skills-b"
mkdir -p "$ONB_B"
make_src_tree "$ONB_B"
make_src_tree "$SKD_B"
BEFORE_SUM="$(find "$SKD_B/58-podcast-production-engine" -type f | sort | xargs shasum -a 256 | shasum -a 256)"
run_block "$ONB_B" "$SKD_B" b
[ "$(cat "$WORK/rc-b")" = "0" ] && pass "scenario B: block exits 0 when the dest copy is already complete" \
                                || fail "scenario B: block exited $(cat "$WORK/rc-b") (want 0)"
AFTER_SUM="$(find "$SKD_B/58-podcast-production-engine" -type f | sort | xargs shasum -a 256 | shasum -a 256)"
[ "$BEFORE_SUM" = "$AFTER_SUM" ] \
    && pass "scenario B: a complete dest copy is left byte-identical (never clobbered)" \
    || fail "scenario B: a complete dest copy was modified by the block"
grep -q "^WARN_COUNT=0$" "$WORK/out-b.txt" \
    && pass "scenario B: zero warns when the dest copy is already complete" \
    || fail "scenario B: unexpected warns on an already-complete dest"

# --- scenario C: partial dest copy (the silent-missing failure class) --------
ONB_C="$WORK/src-c"; SKD_C="$WORK/skills-c"
mkdir -p "$ONB_C"
make_src_tree "$ONB_C"
mkdir -p "$SKD_C/58-podcast-production-engine/scripts"
for f in scripts/register-podcast-hook.sh scripts/install-podcast-department.sh; do
    printf '#!/usr/bin/env bash\n# fixture %s\n' "$f" > "$SKD_C/58-podcast-production-engine/$f"
done
# webhook/intake_handler.py deliberately absent from the dest (partial copy)
SUM_C_HOOK_BEFORE="$(shasum -a 256 "$SKD_C/58-podcast-production-engine/scripts/register-podcast-hook.sh" | awk '{print $1}')"
run_block "$ONB_C" "$SKD_C" c
[ "$(cat "$WORK/rc-c")" = "0" ] && pass "scenario C: block exits 0 while repairing a partial dest copy" \
                                || fail "scenario C: block exited $(cat "$WORK/rc-c") (want 0)"
[ -f "$SKD_C/58-podcast-production-engine/scripts/webhook/intake_handler.py" ] \
    && pass "scenario C: the missing webhook/intake_handler.py is repaired (copied in)" \
    || fail "scenario C: the missing webhook/intake_handler.py was NOT repaired"
SUM_C_HOOK_AFTER="$(shasum -a 256 "$SKD_C/58-podcast-production-engine/scripts/register-podcast-hook.sh" | awk '{print $1}')"
[ "$SUM_C_HOOK_BEFORE" = "$SUM_C_HOOK_AFTER" ] \
    && pass "scenario C: existing dest files stay byte-identical during the repair" \
    || fail "scenario C: the repair corrupted an existing dest file"
grep -q "repaired missing" "$WORK/out-c.txt" \
    && pass "scenario C: the repair is announced so the install log shows what happened" \
    || fail "scenario C: the repair was silent in the install output"
grep -q "^WARN_COUNT=0$" "$WORK/out-c.txt" \
    && pass "scenario C: the repair path emits zero warns (repair is a success, not a warning)" \
    || fail "scenario C: unexpected warns while repairing the partial dest copy"

# --- scenario D: activation file missing from the source package -------------
ONB_D="$WORK/src-d"; SKD_D="$WORK/skills-d"
mkdir -p "$ONB_D"
make_src_tree "$ONB_D"
rm "$ONB_D/58-podcast-production-engine/scripts/webhook/intake_handler.py"
run_block "$ONB_D" "$SKD_D" d
[ "$(cat "$WORK/rc-d")" = "0" ] \
    && pass "scenario D: block exits 0 even when a source activation file is missing (install never aborts)" \
    || fail "scenario D: block exited $(cat "$WORK/rc-d") (want 0; a wiring hiccup must never abort the install)"
grep -q "not in this onboarding package" "$WORK/out-d.txt" \
    && pass "scenario D: a missing source activation file is surfaced as a warn" \
    || fail "scenario D: a missing source activation file was NOT surfaced"
grep -q "NOT complete" "$WORK/out-d.txt" \
    && pass "scenario D: the not-complete summary warn fires when the layer is missing" \
    || fail "scenario D: the not-complete summary warn did not fire"
[ ! -f "$SKD_D/58-podcast-production-engine/scripts/webhook/intake_handler.py" ] \
    && pass "scenario D: no phantom handler file is fabricated at the destination" \
    || fail "scenario D: a handler file appeared at the destination despite a missing source"

# --- scenario E: the block NEVER activates ------------------------------------
# A fresh install ships the scripts but must not run them: activation is
# per-client and requires a slug, session binding, and an intake hook token.
# Comment lines are stripped first so the documented intent text (which names
# the activators) can never false-positive.
# The check: no non-comment line RUNS an interpreter or sources a script as a
# command (bash/sh/source/./python3 at command position). The block may only
# use file operations (cp, chmod, mkdir, case/test). Matching command position
# (not "anywhere in the line") avoids false-positives from the file list
# itself, whose ".sh scripts/" boundary looks like a bare "sh" token.
if grep -v '^[[:space:]]*#' "$WORK/block.sh" \
     | grep -Eq "^[[:space:]]*(bash|sh|source|\.|python3)[[:space:]]"; then
    fail "scenario E: the install block RUNS an interpreter or sources a script (it must only ensure delivery)"
else
    pass "scenario E: the install block only ensures delivery (no interpreter run, no activation invocation)"
fi

# --- static assertion 5: no per-skill FILE_LIST manifest in install.sh -------
if grep -qE "^(SKILL_FILES|FILES_TO_COPY|SKILL_FILE_MANIFEST)=" "$INSTALL_SH"; then
    fail "static: install.sh grew a per-skill file-list variable; the activation files must be added to it"
else
    pass "static: install.sh has no per-skill file-list manifest (directory enumeration carries the activation scripts)"
fi

# --- static assertion 6: direct-to-agent-install.md --------------------------
DTA_OK=1
for f in register-podcast-hook.sh install-podcast-department.sh webhook/intake_handler.py; do
    if ! grep -q "$f" "$DTA_MD"; then
        DTA_OK=0
        fail "static: direct-to-agent-install.md does not name $f"
    fi
done
[ "$DTA_OK" = "1" ] && pass "static: direct-to-agent-install.md names all three activation files"
grep -q "guard-activation-health.py" "$DTA_MD" \
    && pass "static: direct-to-agent-install.md documents the guard-activation-health.py verification" \
    || fail "static: direct-to-agent-install.md does not document guard-activation-health.py"
grep -q "provision-podcast-client.sh" "$DTA_MD" \
    && pass "static: direct-to-agent-install.md keeps the delivery vs per-client activation boundary" \
    || fail "static: direct-to-agent-install.md does not state the delivery vs activation boundary"

# --- static assertion 7: mac-mini-onboarding has no podcast step -------------
if grep -Ril "podcast" "$MAC_DIR" 2>/dev/null | grep -q .; then
    fail "static: mac-mini-onboarding/ gained a podcast reference; wire it to the activation layer (install-podcast-department.sh)"
else
    pass "static: mac-mini-onboarding/ has no podcast step (nothing to wire; verified, not skipped)"
fi

# --- convention 8: zero em dashes in every line this unit added --------------
EMDASH=$'\xe2\x80\x94'
if grep -q "$EMDASH" "$WORK/block.sh"; then
    fail "convention: em dash found in the roll-3 block of install.sh"
else
    pass "convention: zero em dashes in the roll-3 block of install.sh"
fi
if grep -E "register-podcast-hook|install-podcast-department|podcast_controller|podcast_scheduler|guard-activation-health|activation layer|audit-podcast-activation" "$DTA_MD" | grep -q "$EMDASH"; then
    fail "convention: em dash found on an activation line of direct-to-agent-install.md"
else
    pass "convention: zero em dashes on the activation lines of direct-to-agent-install.md"
fi

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
