#!/usr/bin/env bash
# lib-scoped-chrome-scan.sh — Skill 03 (agent-browser) — GK-28/U90 extraction.
#
# WHY: qc-agent-browser.sh's Step-4 smoke test (P3-06) already had a scoped
# Chromium-process-liveness scan (_scoped_chrome_pids / _new_pids) inlined in
# its own body. GK-28/U90's conformance battery (lib-backstop-conformance.sh)
# needs the EXACT SAME "guaranteed close" read-back mechanism to verify its
# own close leg — duplicating it a second time would be exactly the kind of
# drift-prone copy the P3-06 CHANGELOG already warns about (one shared
# lib-archive-diff.sh instead of two ad-hoc diff implementations). This file
# is the single source of truth for BOTH callers.
#
# CONTRACT
#   _scoped_chrome_pids
#     Prints one pid per line for every LIVE Chromium/headless_shell process
#     whose OWN command line references an agent-browser profile/user-data-dir
#     (never a bare chrome/Chrome/Claude match). Empty output = none found.
#   _new_pids <before-list> <after-list>
#     Prints pids present in <after-list> but NOT in <before-list> (newly
#     appeared since the "before" snapshot was taken).
set -u

_scoped_chrome_pids() {
  ps -axww -o pid=,command= 2>/dev/null \
    | grep -E "(--user-data-dir|--profile|profile-directory)[= ]?[^ ]*agent-browser" \
    | grep -Ei 'chrom|headless_shell' \
    | grep -vi 'grep' \
    | awk '{print $1}' \
    | sort -u
}

_new_pids() {
  comm -13 <(printf '%s\n' "$1" | sed '/^$/d' | sort -u) <(printf '%s\n' "$2" | sed '/^$/d' | sort -u)
}
