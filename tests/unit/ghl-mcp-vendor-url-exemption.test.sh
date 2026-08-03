#!/usr/bin/env bash
# ghl-mcp-vendor-url-exemption.test.sh
#
# Guards the VENDOR URL PATH exemption added to the qc-static.yml step
# "No banned model tokens in GHL skill markdown prose (M2 / Anthropic / non-Ollama Kimi)"
# on 2026-08-03.
#
# WHY THIS EXISTS
#   HighLevel's official MCP orchestrator is published at
#       https://services.leadconnectorhq.com/mcp/anthropic/v2
#   `anthropic` there is a PATH SEGMENT naming the MCP client the endpoint serves.
#   It is a vendor's URL, not a model slug, and skill 36 must document it.
#
#   The guard's Anthropic alternative is `anthropic/[a-z0-9-]+`, which matched
#   `anthropic/v2` inside that URL and turned qc-static red on main. The fix is a
#   negative lookbehind `(?<!/mcp/)` anchored to that exact token position.
#
# WHAT THIS TEST PROVES (mutation proof, both directions)
#   NEGATIVE (must now PASS the guard): the vendor URL in its documented forms.
#   POSITIVE (must STILL FAIL the guard): real Anthropic model slugs — including one
#       sharing a line WITH the exempt URL, so the carve-out cannot be used to smuggle
#       a slug past the guard.
#
#   The pattern under test is re-derived FROM qc-static.yml rather than hardcoded, so
#   widening the exemption to a blanket `anthropic` allow fails this test.
#
# PORTABILITY: matching runs through python3's `re`, NOT `grep -P`. BSD grep (macOS
#   default) has no -P, so a grep -P test would error out locally while passing in CI.
#   The pattern uses only fixed-width lookbehind and lookahead, which python `re`
#   evaluates identically to PCRE for these inputs. CI still runs the real grep -P.
#
# Exit 0 = invariant holds. Exit 1 = violated.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 - "$REPO_ROOT" <<'PYEOF'
import os, re, sys

repo = sys.argv[1]
wf = os.path.join(repo, ".github", "workflows", "qc-static.yml")
fail = 0

def ok(m):  print("  ✓ PASS — %s" % m)
def bad(m):
    global fail
    print("  ✗ FAIL — %s" % m); fail = 1

print("=== GHL MCP vendor-URL exemption (qc-static Anthropic guard) ===")

if not os.path.isfile(wf):
    print("  ✗ FAIL — qc-static.yml not found at %s" % wf); sys.exit(1)

src = open(wf, encoding="utf-8").read()

# Pull the LIVE Anthropic pattern out of the workflow (single-quoted grep arg).
m = re.search(r"'(claude-\(\?!desktop.*?)'", src, re.S)
if not m:
    bad("could not extract the Anthropic pattern from qc-static.yml (step changed shape?)")
    sys.exit(1)
pattern = m.group(1)
ok("extracted the live pattern from qc-static.yml")

# The exemption must be the narrow lookbehind, not a blanket allow.
if "(?<!/mcp/)anthropic/" in pattern:
    ok("exemption is the narrow (?<!/mcp/) lookbehind")
else:
    bad("expected a (?<!/mcp/) lookbehind on the anthropic/ alternative; got: %s" % pattern)

if re.search(r"anthropic/\[a-z0-9-\]\+", pattern):
    ok("the anthropic/<slug> alternative is still present (guard not gutted)")
else:
    bad("the anthropic/<slug> alternative was removed — guard no longer catches model slugs")

try:
    rx = re.compile(pattern, re.IGNORECASE)
except re.error as e:
    bad("pattern does not compile: %s" % e); sys.exit(1)

def hits(text):
    return [l for l in text.splitlines() if rx.search(l)]

# ---- NEGATIVE: the vendor URL must NOT trip the guard ----------------------
vendor = """| URL | `https://services.leadconnectorhq.com/mcp/anthropic/v2` (Claude, live today) |
Use `/mcp/anthropic/v2` as the default Tier 1 for this fleet.
claude mcp add --transport http leadconnector https://services.leadconnectorhq.com/mcp/anthropic/v2
The per-client endpoint pattern is https://services.leadconnectorhq.com/mcp/{client}/v2.
Also available: the original endpoint (/mcp/).
"""
h = hits(vendor)
if h:
    for l in h: print("      unexpected hit: %s" % l.strip()[:100])
    bad("vendor URL /mcp/anthropic/v2 still trips the guard (CI would stay red)")
else:
    ok("vendor URL /mcp/anthropic/v2 does NOT trip the guard")

# ---- POSITIVE: real model slugs must STILL trip the guard ------------------
for slug in [
    "model: anthropic/claude-opus-4",
    "pin the agent to claude-opus-4-5 for this run",
    "bedrock id us.anthropic.claude-sonnet-4",
    "fallback: anthropic/claude-haiku-4",
]:
    if hits(slug):
        ok("still caught: %s" % slug)
    else:
        bad("NOT caught (guard regressed): %s" % slug)

# ---- The smuggling case: a slug co-located with the exempt URL -------------
smuggle = ("Point it at https://services.leadconnectorhq.com/mcp/anthropic/v2 "
           "and set model anthropic/claude-opus-4.")
if hits(smuggle):
    ok("a real slug sharing a line with the exempt URL is STILL caught")
else:
    bad("smuggling hole: a model slug co-located with the vendor URL slipped through")

# ---- Regression: the docs that turned CI red must now be clean -------------
for rel in ["36-ghl-mcp-setup/SKILL.md", "36-ghl-mcp-setup/CHANGELOG.md"]:
    p = os.path.join(repo, rel)
    if not os.path.isfile(p):
        continue
    h = hits(open(p, encoding="utf-8").read())
    if h:
        for l in h[:5]: print("      hit: %s" % l.strip()[:110])
        bad("%s trips the Anthropic guard" % rel)
    else:
        ok("%s is clean under the live guard pattern" % rel)

print()
print("RESULT: PASS — vendor URL exempt, real Anthropic model slugs still blocked."
      if fail == 0 else "RESULT: FAIL — see above.")
sys.exit(fail)
PYEOF
