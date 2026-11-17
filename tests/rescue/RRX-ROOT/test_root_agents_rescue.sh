#!/usr/bin/env bash
# tests/rescue/RRX-ROOT/test_root_agents_rescue.sh
# ─────────────────────────────────────────────────────────────────────────────
# RRX-100 — the root AGENTS.md carries ONE set of escalation instructions.
#
# Roots cause this covers: the repository root `AGENTS.md` kept a retired
# escalation block (a hand-built curl POST, a `returnTo` field guide, hostname
# guidance, a 25-exchange cap and the old resolution phrases) that every box
# copies as a SECOND AGENTS.md. An agent that reads it is told to escalate a
# way that no longer exists.
#
# The Rescue Rangers resolution protocol lives in this file's own section —
# the heading below and everything up to the next `## ` heading. Other sections
# of this file are owned by nobody in this lane and legitimately mention
# `printenv` elsewhere (credential-check protocol), so the wording checks are
# scoped to the rescue section and the heading check is repo-wide.
#
# Fully offline. No network, no openclaw, no client box. Exit 0 = pass.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
AGENTS="$REPO_ROOT/AGENTS.md"

if [ ! -f "$AGENTS" ]; then
  printf 'FAIL: root AGENTS.md exists at %s\n' "AGENTS.md"
  exit 1
fi

python3 -I - "$AGENTS" <<'PY'
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    lines = fh.read().split("\n")

HEADING = "## \U0001F534 Rescue Rangers — how to escalate + resolution / loop-stop"

fails = 0


def check(ok, label):
    global fails
    if ok:
        print("  PASS: " + label)
    else:
        fails += 1
        print("  FAIL: " + label)


# --- repo-wide: the heading survives, exactly once -------------------------
n_heading = lines.count(HEADING)
check(n_heading == 1, "the Rescue Rangers heading is present exactly once (found %d)" % n_heading)

start = None
for i, line in enumerate(lines):
    if line == HEADING:
        start = i
        break
end = len(lines)
if start is not None:
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
section = lines[start:end] if start is not None else []

# --- repo-wide: the retired field-guide row is gone ------------------------
check(
    not any('"returnTo"' in line and "must be posted" in line for line in lines),
    'no line carries the retired "returnTo" ... must be posted row',
)

# --- inside the rescue section -------------------------------------------
check(
    not any("Hostname or compose-project label" in line for line in section),
    'the rescue section carries no "Hostname or compose-project label" guidance',
)
check(
    not any("printenv" in line for line in section),
    "the rescue section contains no line with printenv",
)

print("RESULT: %d failure(s)" % fails)
sys.exit(0 if fails == 0 else 1)
PY
