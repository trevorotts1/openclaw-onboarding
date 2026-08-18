#!/usr/bin/env python3
"""trust_boundary_prefixes.py — the ONE place the "TRUST-BOUNDARY-PREFLIGHT-*"
stderr line prefixes are spelled out as literal strings.

WHY THIS FILE EXISTS: presentation_job/preflight_shadow.py (the emitter) and
trust_boundary_observability.py (the parser) each need the exact same four
strings. Before this file existed they were hardcoded twice — once in each
module — and the two copies drifted: the emitter's prefixes carry the
`-PREFLIGHT-` infix (`TRUST-BOUNDARY-PREFLIGHT-DIVERGENCE`, `...-WOULD-BLOCK`,
`...-SHADOW-ERROR`, `...-SUMMARY`) but the parser's `KNOWN_KINDS` only ever
listed the three OLDER, differently-shaped prefixes from
presentation_job/runfacts.py (`TRUST-BOUNDARY-DIVERGENCE`,
`TRUST-BOUNDARY-SEAL-FINDING`, `TRUST-BOUNDARY-SHADOW-ERROR` — no
`-PREFLIGHT-` infix). Because `parse_line()` gated entry on
`line.startswith(p) for p in KNOWN_KINDS`, and
`"TRUST-BOUNDARY-PREFLIGHT-DIVERGENCE".startswith("TRUST-BOUNDARY-DIVERGENCE")`
is False (the infix sits in the middle, not the end), every line the wrapper
actually printed silently returned None — the monitor was blind to the exact
system it was built to watch. See CONTROL/TRUST-BOUNDARY-STATUS.md and the
`fix/trust-parser` branch for the incident.

Both sides now import from here instead of hardcoding. A future rename of
any of these four strings requires editing exactly one file; the emitter and
the parser can no longer independently drift.

Deliberately NOT included here: the three older `presentation_job.runfacts`
prefixes (`TRUST-BOUNDARY-DIVERGENCE` / `-SEAL-FINDING` / `-SHADOW-ERROR`,
no infix). Those already have a working single-owner pattern —
`verifier_registry.py` imports them from `runfacts.py` directly
(`DIVERGENCE_PREFIX = _rf.DIVERGENCE_PREFIX`) — and
`trust_boundary_observability.py` deliberately keeps its own literal copies
of those three (see that module's docstring: "zero import dependency on the
files it observes", so a broken runfacts.py can never break this observer).
That decision predates this file and is untouched by it; this file only
closes the gap that had NO working single-source pattern at all.

ZERO third-party deps, ZERO imports of any other project module (including
presentation_job.runfacts) — this file must never be the reason an import
of it can fail or cycle.
"""

from __future__ import annotations

# presentation_job/preflight_shadow.py — Phase 1 surface A (the
# PREFLIGHT_REQUIRED dispatch-loop wrapper around build_deck.run_preflight()).
PREFLIGHT_DIVERGENCE_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-DIVERGENCE"
PREFLIGHT_WOULD_BLOCK_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-WOULD-BLOCK"
PREFLIGHT_ERROR_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-SHADOW-ERROR"
PREFLIGHT_SUMMARY_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-SUMMARY"

PREFLIGHT_KNOWN_KINDS = (
    PREFLIGHT_DIVERGENCE_PREFIX,
    PREFLIGHT_WOULD_BLOCK_PREFIX,
    PREFLIGHT_ERROR_PREFIX,
    PREFLIGHT_SUMMARY_PREFIX,
)
