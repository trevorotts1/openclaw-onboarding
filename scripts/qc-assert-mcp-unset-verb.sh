#!/usr/bin/env bash
# qc-assert-mcp-unset-verb.sh — v21.7.3
#
# STATIC GATE: no file in this repo may de-register an MCP server using ONLY
# `openclaw mcp remove`.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS EXISTS (BLOCKER 2, proven live on OpenClaw 2026.7.1-2)
#
# `openclaw mcp remove <name>` IS NOT A COMMAND. It exits 1 with:
#     Too many arguments for this command.
# The verb is `unset`.
#
# This repo carried EIGHT occurrences of `remove` and ZERO of `unset`:
#     update-skills.sh                      the fleet-roll de-registration
#     scripts/ghl-mcp-autostart.sh          deregister_tier2()
#     36-ghl-mcp-setup/wire.sh              migration M2
#     scripts/ghl-mcp-assert-runtime.sh     the remediation text it prints
#     36-ghl-mcp-setup/INSTALL.md           operator instructions
#     36-ghl-mcp-setup/ghl-mcp-setup-full.md
#     (+ two explanatory comments)
#
# EVERY executable call was swallowed by `|| true`. So Tier 2 was never actually
# de-registered on ANY box, check 10 of ghl-mcp-assert-runtime.sh
# ("ghl-community-mcp ABSENT from mcp.servers") could never pass anywhere, and
# it was the last remaining FATAL on the pilot box. Worse, wire.sh's failure
# message blamed "the gateway can rewrite openclaw.json from memory", which sent
# every investigation after a phantom.
#
# A wrong verb behind `|| true` is invisible forever. This gate makes it visible
# at the PR boundary.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE INVARIANT
#
# Any file mentioning `openclaw mcp remove` must ALSO mention
# `openclaw mcp unset`. That permits the correct, defensive shape
#     openclaw mcp unset X || openclaw mcp remove X
# (unset first, `remove` retained only as a fallback for an older CLI) and the
# documentation that explains the difference, while making a regression to
# remove-only impossible.
#
# Exit codes:
#   0  no remove-only site
#   1  INVARIANT VIOLATED — at least one file de-registers with `remove` alone
#
# Usage: bash scripts/qc-assert-mcp-unset-verb.sh [--quiet]
#
# Wired in: .github/workflows/ghl-mcp-supervised-guard.yml

set -uo pipefail

QUIET=0
for _arg in "$@"; do [ "$_arg" = "--quiet" ] && QUIET=1; done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-mcp-unset-verb] PASS  %s\n' "$*"; return 0; }
_fail() { printf '[qc-mcp-unset-verb] FATAL INVARIANT VIOLATED — %s\n' "$*" >&2; return 0; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-mcp-unset-verb] INFO  %s\n' "$*"; return 0; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1

FAILURES=0
CHECKED=0

# Tracked files only. CHANGELOG.md is excluded: it is an append-only historical
# record, and rewriting history to match a present-day invariant is exactly the
# kind of evidence-forging this repo forbids elsewhere (see the _qc-summary.md
# removal note in scripts/version-markers.json).
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in
    CHANGELOG.md|scripts/qc-assert-mcp-unset-verb.sh|tests/unit/ghl-mcp-unset-verb.test.sh) continue ;;
  esac
  grep -qF 'openclaw mcp remove' "$f" 2>/dev/null || continue
  CHECKED=$((CHECKED+1))
  if grep -qF 'openclaw mcp unset' "$f" 2>/dev/null; then
    _pass "$f mentions 'openclaw mcp remove' but also 'openclaw mcp unset' (correct verb present)"
  else
    _fail "$f uses 'openclaw mcp remove' and NEVER 'openclaw mcp unset'. 'mcp remove' is not a command on OpenClaw 2026.7.1-2 — it exits 1 with 'Too many arguments for this command'. Use 'openclaw mcp unset <name>' (keeping 'remove' only as an explicit fallback for an older CLI). Behind a '|| true' this failure is silent forever, which is why Tier 2 was never de-registered on any box."
    FAILURES=$((FAILURES+1))
  fi
done <<EOF
$(git ls-files 2>/dev/null)
EOF

# ANTI-VACUITY. If nobody references either verb, this gate is asserting nothing
# and would go green forever after an innocent-looking refactor. The
# de-registration path is load-bearing (an un-de-registered Tier 2 taxes every
# agent init), so its absence is itself a failure.
# NOTE the plain loop rather than `git ls-files -z | xargs -0 grep -l …`: under
# `set -o pipefail` that pipeline reports failure whenever ANY xargs batch has no
# match, which is almost always — the check then fired on a perfectly healthy
# repo. Counting matches directly has no such trap.
_UNSET_REFS=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in scripts/qc-assert-mcp-unset-verb.sh) continue ;; esac
  if grep -qF 'openclaw mcp unset' "$f" 2>/dev/null; then
    _UNSET_REFS=$((_UNSET_REFS+1))
  fi
done <<EOF
$(git ls-files 2>/dev/null)
EOF

if [ "$_UNSET_REFS" -eq 0 ]; then
  _fail "NOTHING in this repo references 'openclaw mcp unset'. The Tier 2 de-registration path has been removed or renamed — an un-de-registered ghl-community-mcp puts its tool schemas into every agent init and makes a down/deaf server cost the full connectionTimeoutMs per init."
  FAILURES=$((FAILURES+1))
else
  _pass "the correct verb 'openclaw mcp unset' is referenced in $_UNSET_REFS tracked file(s) — gate is not vacuous"
fi

if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES file(s) de-register an MCP server with a verb the installed CLI rejects."
  exit 1
fi
_info "checked $CHECKED file(s) mentioning 'openclaw mcp remove'; every one also carries the correct 'unset' verb."
exit 0
