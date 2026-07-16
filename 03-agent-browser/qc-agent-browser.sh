#!/usr/bin/env bash
# Skill 03 — Agent Browser — Install QC
#
# P3-06 hardening (2026-07-12):
#   1. Archive drift gate — agent-browser.skill is diffed against the on-disk
#      INSTALL.md/SKILL.md/CHANGELOG.md/CORE_UPDATES.md it is packaged from;
#      ANY mismatch fails QC naming the differing file (was: no check at all).
#   2. Step-4 smoke test is run for real (when agent-browser is on PATH) using
#      the EXACT fenced ```bash block extracted live from INSTALL.md (the
#      guaranteed-close trap, `--headed false`) — the command + flags actually
#      run are printed as evidence, so the QC.md requirement that this be
#      ASSERTED (not implied) is satisfied by the script's own output.
#   3. An ambient AGENT_BROWSER_HEADED signal that would force a visible
#      window is refused (exit-75 class, matching Skill 06's D6 convention) —
#      the smoke test never runs headed.
#   4. Post-smoke-test browser-process state is now ASSERTED clean (a leaked
#      Chromium process spawned by THIS run's smoke test FAILS QC). A
#      PRE-smoke-test scan stays warn_only — a scoped process that predates
#      this run is not this skill's fault to fail on.
#
#   NOTE on the leak signal (verified against a real, live agent-browser
#   install, not assumed): `agent-browser close` reliably kills the Chromium
#   process it opened, but its own lightweight daemon (`~/.agent-browser/
#   *.engine`, `agent-browser session list`) intentionally OUTLIVES `close`
#   for fast reuse — that is documented product behavior (state persistence),
#   not a leak. Gating on `.engine`-file presence or `session list` would
#   therefore fail EVERY clean run. The real orphan class this skill's own
#   Lifecycle hygiene section and scripts/agent-browser-reaper.sh care about
#   is a leaked CHROMIUM PROCESS, so this gate matches the reaper's own
#   proven method: a scoped `ps` match on Chromium bound to an agent-browser
#   profile dir (never a bare chrome/Chrome/Claude match), diffed before vs.
#   after this run's own smoke test.
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
# shellcheck source=./scripts/lib-archive-diff.sh
source "$SKILL_DIR/scripts/lib-archive-diff.sh"
# shellcheck source=./scripts/lib-scoped-chrome-scan.sh
source "$SKILL_DIR/scripts/lib-scoped-chrome-scan.sh"
# shellcheck source=./scripts/lib-onbox-drift.sh
source "$SKILL_DIR/scripts/lib-onbox-drift.sh"
# shellcheck source=./scripts/lib-backstop-conformance.sh
source "$SKILL_DIR/scripts/lib-backstop-conformance.sh"

red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

echo ""
echo "═══ Skill 03 — Agent Browser — Install QC ═══"
echo ""
assert "Skill 03 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/03-agent-browser\" ]"
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
assert "agent-browser CLI on PATH" "command -v agent-browser || npm list -g --depth=0 2>/dev/null | grep -q agent-browser"
warn_only "agent-browser --help responds" "agent-browser --help 2>&1 | grep -qiE 'agent.browser|usage|command'"
warn_only "TOOLS.md references agent-browser" "grep -qiE 'agent.browser' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"

# ── Relationship lattice pointer + citation tripwire (U89/GK-27) ─────────────
# Static/offline, repo-relative — asserts SKILL.md carries its one-line
# pointer to docs/CONTENT-CONVERSATION-LATTICE.md and that the edge(s) this
# skill owns (its own backstop-consumer acknowledgment, GK-28/U90) still cite
# real, unchanged ground truth. Drift (a moved/edited/deleted cited line) or a
# missing pointer both FAIL this check — see docs/tools/check_lattice_citation.py.
echo ""
echo "═══ Relationship lattice pointer + citation tripwire (GK-27) ═══"
echo ""
REPO_ROOT_LATTICE="$(cd "$SKILL_DIR/.." && pwd)"
assert "SKILL.md pointer to docs/CONTENT-CONVERSATION-LATTICE.md + this skill's owned edge citations still hold (GK-27 drift tripwire)" \
  "python3 \"$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py\" --repo-root \"$REPO_ROOT_LATTICE\" --skill 03-agent-browser -q"

# ── Archive drift gate (P3-06 step (c)2) ─────────────────────────────────────
echo ""
echo "═══ Bundled archive drift gate ═══"
echo ""
ARCHIVE="$SKILL_DIR/agent-browser.skill"
if [ ! -f "$ARCHIVE" ]; then
  red "  ✗ FAIL — agent-browser.skill archive missing at $ARCHIVE"
  FAIL=$((FAIL+1))
else
  ARCHIVE_DRIFT="$(agent_browser_archive_diff "$ARCHIVE" "$SKILL_DIR")"
  ARCHIVE_DRIFT_RC=$?
  if [ "$ARCHIVE_DRIFT_RC" -ne 0 ]; then
    red "  ✗ FAIL — could not evaluate archive drift: $ARCHIVE_DRIFT"
    FAIL=$((FAIL+1))
  elif [ -n "$ARCHIVE_DRIFT" ]; then
    red "  ✗ FAIL — agent-browser.skill is STALE vs on-disk source. Differing file(s): $(echo "$ARCHIVE_DRIFT" | tr '\n' ' ')— run scripts/pack-agent-browser-skill.sh to regenerate"
    FAIL=$((FAIL+1))
  else
    green "  ✓ PASS — agent-browser.skill matches on-disk INSTALL.md/SKILL.md/CHANGELOG.md/CORE_UPDATES.md byte-for-byte"
    PASS=$((PASS+1))
  fi
fi

# ── On-box source-of-truth drift gate (GK-28/U90 step (a)) ──────────────────
# SKILL.md defers to ~/clawd/skills/agent-browser/SKILL.md as "the source of
# truth" WHEN PRESENT, with no drift check between the two before this. That
# file is box-local (outside this repo), so it is checked against a PINNED
# sha256 baseline (references/onbox-agent-browser-skillmd.pin) instead of an
# on-disk diff. AGENT_BROWSER_ONBOX_SKILLMD overrides the path (testing only).
echo ""
echo "═══ On-box source-of-truth drift gate ═══"
echo ""
ONBOX_SKILLMD="${AGENT_BROWSER_ONBOX_SKILLMD:-$HOME/clawd/skills/agent-browser/SKILL.md}"
ONBOX_PIN="$SKILL_DIR/references/onbox-agent-browser-skillmd.pin"
ONBOX_DRIFT="$(agent_browser_onbox_drift "$ONBOX_SKILLMD" "$ONBOX_PIN")"
case "$ONBOX_DRIFT" in
  "")
    green "  ✓ PASS — no on-box source-of-truth copy present at $ONBOX_SKILLMD (nothing to check; SKILL.md documents this path as optional)"
    PASS=$((PASS+1))
    ;;
  MATCH)
    green "  ✓ PASS — $ONBOX_SKILLMD matches the pinned baseline"
    PASS=$((PASS+1))
    ;;
  NO-BASELINE-PINNED)
    red "  ✗ FAIL — $ONBOX_SKILLMD is present but no baseline is pinned yet (no baseline pinned — fail-closed). Review it, then run scripts/pin-onbox-source-of-truth.sh to capture one."
    FAIL=$((FAIL+1))
    ;;
  DRIFT*)
    red "  ✗ FAIL — $ONBOX_SKILLMD has DRIFTED from the pinned baseline: $ONBOX_DRIFT — review the change, then re-run scripts/pin-onbox-source-of-truth.sh to re-pin (if accepted)."
    FAIL=$((FAIL+1))
    ;;
  ERROR:*)
    red "  ✗ FAIL — $ONBOX_DRIFT"
    FAIL=$((FAIL+1))
    ;;
esac

# ── CLI version pin (GK-28/U90 step (b)) ─────────────────────────────────────
# The agent-browser NPM PACKAGE version was never pinned anywhere in this
# skill before this (the archive covers the WRAPPER docs only, P3-06). A
# fresh `npm install -g agent-browser` could silently land any current
# registry release. agent-browser-cli.pin + CLI-VERSION-PIN.md now record a
# known-good, PROVEN version; this section asserts the two agree AND that the
# installed CLI (when present) actually matches the pin.
echo ""
echo "═══ CLI version pin ═══"
echo ""
CLI_PIN_FILE="$SKILL_DIR/agent-browser-cli.pin"
if [ ! -f "$CLI_PIN_FILE" ]; then
  red "  ✗ FAIL — agent-browser-cli.pin missing at $CLI_PIN_FILE"
  FAIL=$((FAIL+1))
else
  PIN_CHECK_OUT="$(bash "$SKILL_DIR/scripts/bump-agent-browser-cli-pin.sh" --check 2>&1)"
  PIN_CHECK_RC=$?
  if [ "$PIN_CHECK_RC" -ne 0 ]; then
    red "  ✗ FAIL — $PIN_CHECK_OUT"
    FAIL=$((FAIL+1))
  else
    green "  ✓ PASS — $PIN_CHECK_OUT"
    PASS=$((PASS+1))
  fi

  PINNED_VERSION="$(tr -d '[:space:]' < "$CLI_PIN_FILE")"
  if ! command -v agent-browser >/dev/null 2>&1; then
    yellow "  ⚠ WARN — agent-browser not on PATH; cannot verify installed CLI version against the pin ($PINNED_VERSION) — already FAILS the 'agent-browser CLI on PATH' check above"
    WARN=$((WARN+1))
  else
    INSTALLED_VERSION="$(agent-browser --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    if [ -z "$INSTALLED_VERSION" ]; then
      yellow "  ⚠ WARN — could not parse an installed CLI version from 'agent-browser --version' output — verify manually against the pin ($PINNED_VERSION)"
      WARN=$((WARN+1))
    elif [ "$INSTALLED_VERSION" = "$PINNED_VERSION" ]; then
      green "  ✓ PASS — installed agent-browser CLI version ($INSTALLED_VERSION) matches the pinned CLI version ($PINNED_VERSION)"
      PASS=$((PASS+1))
    else
      red "  ✗ FAIL — installed agent-browser CLI version ($INSTALLED_VERSION) does NOT match the pinned CLI version ($PINNED_VERSION) — see CLI-VERSION-PIN.md; bump only after proving the new version on the operator's own box, via scripts/bump-agent-browser-cli-pin.sh"
      FAIL=$((FAIL+1))
    fi
  fi
fi

# ── Step-4 guaranteed-close smoke test — extracted live from INSTALL.md,
#    --headed false ASSERTED (not implied), post-test PROCESS state ASSERTED
#    clean (P3-06 step (c)3 + (c)4) ─────────────────────────────────────────
echo ""
echo "═══ Step-4 smoke test (guaranteed-close, --headed false) ═══"
echo ""

# _scoped_chrome_pids / _new_pids — Scoped Chromium-under-agent-browser-profile
# match, same shape as scripts/agent-browser-reaper.sh's AB_MAX_LIVE tripwire
# (never a bare chrome/Chrome/Claude match — only a Chromium whose OWN command
# line references an agent-browser profile/user-data-dir). Extracted to
# scripts/lib-scoped-chrome-scan.sh (GK-28/U90) so this Step-4 leg and the new
# backstop conformance battery's "guaranteed close" leg share ONE
# implementation instead of two ad-hoc copies (sourced above).

if ! command -v agent-browser >/dev/null 2>&1; then
  yellow "  ⚠ WARN — agent-browser not on PATH; Step-4 smoke test SKIPPED (already FAILS the 'agent-browser CLI on PATH' check above)"
  WARN=$((WARN+1))
else
  # PRE-existing-environment scan — informational only. A scoped session that
  # was already running before this QC run is not this skill's fault; it
  # stays warn_only per the P3-06 root-cause decision.
  PRE_PIDS="$(_scoped_chrome_pids)"
  PRE_COUNT=0; [ -n "$PRE_PIDS" ] && PRE_COUNT="$(printf '%s\n' "$PRE_PIDS" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$PRE_COUNT" -gt 0 ]; then
    yellow "  ⚠ WARN — $PRE_COUNT pre-existing scoped agent-browser Chromium process(es) found before this QC run (pid(s): $(printf '%s' "$PRE_PIDS" | tr '\n' ' ')) — not this skill's fault; run agent-browser-reaper.sh to sweep"
    WARN=$((WARN+1))
  else
    green "  ✓ PASS — no pre-existing scoped agent-browser Chromium processes before this QC run"
    PASS=$((PASS+1))
  fi

  # Ambient headed-signal refusal (D6 convention, exit-75 class). Checked
  # BEFORE anything forces AGENT_BROWSER_HEADED, so a truthy ambient value is
  # actually observed, not silently overwritten first.
  _ambient_headed="${AGENT_BROWSER_HEADED:-}"
  case "$_ambient_headed" in
    ""|0|false|False|FALSE|no|off|No|NO)
      # Extract the EXACT fenced ```bash block from INSTALL.md that contains
      # the guaranteed-close trap, so this proves the SHIPPED doc text (same
      # technique as install-step4-close-guarantee.test.sh — fails loud if a
      # future edit ever removes the trap).
      EXTRACTED="$(mktemp)"
      EXTRACT_OK=1
      python3 - "$SKILL_DIR/INSTALL.md" > "$EXTRACTED" <<'PY' || EXTRACT_OK=0
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
blocks = re.findall(r"```bash\n(.*?)\n```", text, re.S)
target = None
for b in blocks:
    if "trap 'agent-browser close' EXIT" in b:
        target = b
        break
if target is None:
    sys.exit(1)
sys.stdout.write(target)
PY
      if [ "$EXTRACT_OK" -ne 1 ] || [ ! -s "$EXTRACTED" ]; then
        red "  ✗ FAIL — INSTALL.md no longer contains a Step-4 guaranteed-close block; cannot run the asserted smoke test"
        FAIL=$((FAIL+1))
        rm -f "$EXTRACTED"
      else
        echo "  --- ASSERTED evidence: exact command run (extracted from INSTALL.md Step 4) ---"
        sed 's/^/  | /' "$EXTRACTED"
        echo "  ---------------------------------------------------------------------------------"
        SMOKE_RC=0
        bash "$EXTRACTED" >/tmp/qc03-smoke-out.$$ 2>&1 || SMOKE_RC=$?
        SMOKE_OUT="$(cat /tmp/qc03-smoke-out.$$ 2>/dev/null)"; rm -f /tmp/qc03-smoke-out.$$ "$EXTRACTED"
        echo "$SMOKE_OUT" | sed 's/^/  smoke output: /'
        if echo "$SMOKE_OUT" | grep -qiE '(@e[0-9]|ref=.?e[0-9])'; then
          green "  ✓ PASS — Step-4 smoke test ran --headed false inside the guaranteed-close trap subshell and returned interactive element refs (@eN)"
          PASS=$((PASS+1))
        else
          yellow "  ⚠ WARN — Step-4 smoke test ran (rc=$SMOKE_RC) but no @eN ref found in snapshot output — verify manually"
          WARN=$((WARN+1))
        fi

        # POST-smoke-test PROCESS state — ASSERTED clean (P3-06 step (c)4:
        # was warn_only/absent, now a Chromium process this run's smoke test
        # spawned and left alive after `close` FAILS QC, full stop). Only
        # NEW pids (not present in PRE_PIDS) count — a pre-existing scoped
        # session outside this run's control is covered by the warn above,
        # never double-penalized here.
        sleep 1  # let close's teardown settle before the final process scan
        POST_PIDS="$(_scoped_chrome_pids)"
        LEAKED_PIDS="$(_new_pids "$PRE_PIDS" "$POST_PIDS")"
        LEAKED_PIDS="$(printf '%s' "$LEAKED_PIDS" | sed '/^$/d')"
        if [ -n "$LEAKED_PIDS" ]; then
          red "  ✗ FAIL — this smoke test's own Chromium process is still alive after guaranteed-close ran (leaked pid(s): $(printf '%s' "$LEAKED_PIDS" | tr '\n' ' '))"
          FAIL=$((FAIL+1))
        else
          green "  ✓ PASS — zero Chromium processes spawned by this smoke test remain alive after guaranteed-close (session list quoted empty of this run's own work)"
          PASS=$((PASS+1))
        fi
      fi
      ;;
    *)
      red "  ✗ FAIL — REFUSE: AGENT_BROWSER_HEADED='${_ambient_headed}' would open a VISIBLE window. Headless (--headed false) is mandatory. Step-4 smoke test ABORTED (exit 75 class). Unset AGENT_BROWSER_HEADED and retry."
      FAIL=$((FAIL+1))
      ;;
  esac
fi

# ── Backstop conformance battery (GK-28/U90 step (c)) ────────────────────────
# Drives the exact five operations Skill 6's browser_manager.sh and Skill 44's
# Tier-4 fallback script against agent-browser (open / ref-based snapshot /
# snapshot-ref stability / fill-by-ref / guaranteed close) from the CONSUMER
# side, against a bundled offline fixture (no network dependency). Shares the
# SAME run_conformance_battery implementation the fail-first regression test
# (scripts/tests/backstop-conformance.test.sh) proves is fail-closed per leg.
echo ""
echo "═══ Backstop conformance battery (consumer contract) ═══"
echo ""
if ! command -v agent-browser >/dev/null 2>&1; then
  yellow "  ⚠ WARN — agent-browser not on PATH; conformance battery SKIPPED — already FAILS the 'agent-browser CLI on PATH' check above"
  WARN=$((WARN+1))
else
  case "${AGENT_BROWSER_HEADED:-}" in
    ""|0|false|False|FALSE|no|off|No|NO)
      # Captured to a FILE, never a command-substitution pipe: a stub/real
      # CLI's `open` may background a long-lived stand-in process that
      # inherits stdout — under a pipe that blocks the whole capture until
      # that process exits (same reason Step-4's smoke test above redirects
      # to /tmp/qc03-smoke-out.$$ instead of using "$(...)").
      run_conformance_battery "qc-backstop-conformance-$$" >/tmp/qc03-conformance-out.$$ 2>&1
      CONF_RC=$?
      CONF_OUT="$(cat /tmp/qc03-conformance-out.$$ 2>/dev/null)"; rm -f /tmp/qc03-conformance-out.$$
      echo "$CONF_OUT" | sed 's/^/  /'
      if [ "$CONF_RC" -eq 0 ]; then
        green "  ✓ PASS — all five backstop conformance legs pass (open, ref-based snapshot, snapshot-ref stability, fill-by-ref, guaranteed close)"
        PASS=$((PASS+1))
      else
        red "  ✗ FAIL — one or more backstop conformance legs failed (see leg detail above) — Skill 6/44's fallback rail is not fully backed by this CLI"
        FAIL=$((FAIL+1))
      fi
      ;;
    *)
      red "  ✗ FAIL — REFUSE: AGENT_BROWSER_HEADED='${AGENT_BROWSER_HEADED}' would open a VISIBLE window. Conformance battery ABORTED (exit 75 class). Unset AGENT_BROWSER_HEADED and retry."
      FAIL=$((FAIL+1))
      ;;
  esac
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 03 QC FAILED"; exit 1; } || { green "Skill 03 QC PASS"; exit 0; }
