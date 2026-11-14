#!/usr/bin/env bash
# qc-no-direct-kie.sh — F14 static check (manual Part F F14, Critical).
# Fails when a non-test file under scripts/core/ contacts KIE endpoints
# outside kie_dispatch/. Builders may never call KIE directly: all paid
# jobs go through the skill's dispatcher (a hand-written request file is
# a QC fail). Scope: this skill tree (onboarding). The 999 copy is
# W3-A's — run this script there is their unit's job, not ours.
#
# "Endpoint" means a KIE host occurrence in a string literal of a Python
# file — kie.ai, api.kie.ai, or any other subdomain, including ones nobody
# has thought of yet. Markdown and other prose files name KIE.ai in user
# words (client copy); prose is never an endpoint. The ONE exception is the
# documentation host docs.kie.ai (a docs URL is a citation, not an API
# call), and it is applied per host OCCURRENCE:
# a line carrying both a docs URL and a real api URL still fails on the
# api host. A line-level exemption would let the real direct call escape.
#
# Env: DRAMA75_CORE=<scripts/core dir> (default: resolve from this file).
# Exit 0 = clean; exit 2 = direct-KIE call found (paths printed); exit 1 =
# usage error.
#
# The decision itself is made by qc_static_checks.py, which opens and parses
# every file instead of reading grep output (S75-013): a file it cannot read
# or parse is a failure (exit 1), never a silent "clean".
set -u

here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
core="${DRAMA75_CORE:-$here/core}"
if [ ! -d "$core" ]; then
  echo "qc-no-direct-kie: no core dir at $core (set DRAMA75_CORE)" >&2
  exit 1
fi

exec python3 -I "$here/qc_static_checks.py" no-direct-kie --core "$core"
