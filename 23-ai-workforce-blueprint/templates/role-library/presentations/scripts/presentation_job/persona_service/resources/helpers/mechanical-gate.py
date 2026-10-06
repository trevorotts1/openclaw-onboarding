#!/usr/bin/env python3
"""
mechanical-gate.py — SINGLE SOURCE OF TRUTH for the "no persona required"
mechanical-task classifier and the no-persona fallback constants.

WHY THIS FILE EXISTS (F3.7 sub-gap 3, dead-key reconciliation follow-up):
    The mechanical gate used to be copied byte-for-byte in TWO places —
    persona-selector-v2.py main() (whole-task gate) and decompose-task.py
    (per-subtask gate). The copies had ALREADY diverged: the decomposer added
    delivery/plumbing verbs ("send it", "deploy", ...) the selector lacked, so
    the SAME text could be "mechanical" as a sub-task but "craft" as a whole
    task. This module is the ONE gate both import, so the shell-command contract
    can never drift again. The decomposition-only delivery-verb extension is a
    PARAMETER (delivery_verbs=...), not a fork of the rule.

BASE RULE (identical for every caller — do NOT change without updating the
mirror note in persona-selector-v2.py and the decompose docstring):
    - multi-word substrings:  "check disk", "check memory"
    - single-word \\b-anchored: restart, reboot, ping, ls, chmod, chown
    Word-boundary anchoring on the single tokens is load-bearing (BUG-FIX
    v11.6.0): it stops false hits inside "emails" (ls), "shipping" (ping),
    "controls"/"tools" (ls). Multi-word phrases are specific enough for a plain
    substring test.

Hyphenated filename (mechanical-gate.py) → import BY PATH, exactly the way the
selector loads infer-task-category.py and decompose-task.py loads the selector.
Both consumers ship a tiny inline fallback that mirrors the BASE rule so a box
missing this file still gates identically (never-to-zero resilience) — this
module stays authoritative whenever it is present.
"""
import re

# ── Base gate — the canonical shell-command contract ────────────────────────
MECH_MULTIWORD = ("check disk", "check memory")
MECH_SINGLEWORD = ("restart", "reboot", "ping", "ls", "chmod", "chown")

# ── Decomposition-only extension ────────────────────────────────────────────
# Genuinely-mechanical delivery/plumbing verbs a decomposed "sending/sequencing"
# step adds (spec §6 worked example: the send/sequence part is mechanical). These
# are dispatch, not craft. Passed as delivery_verbs= by decompose-task.py; the
# whole-task selector deliberately does NOT apply them (a whole task that merely
# mentions "deploy" is not automatically persona-free).
DELIVERY_VERBS = (
    "send it", "send the", "schedule the send", "deploy", "publish to",
    "push to", "upload", "queue the", "sequence the send", "blast",
)

# ── No-persona fallback constants (Q1 / Q2 governance decisions) ─────────────
# GOVERNANCE_PERSONA_FALLBACK (Q1): a mechanical task keeps no_persona_required
#   = True (truthful, feeds reporting) but ALSO carries this governance persona
#   id so the dispatch gate has a persona for EVERY task — "at least one persona"
#   without pretending a `chmod` needs a craft persona. covey-7-habits is a
#   shipped seed persona (principle-centered governance), a safe neutral default.
# DEFAULT_PERSONA_FALLBACK (Q2): the last-resort default when selection finds no
#   confident match (empty universe, or a REQUIRED SOP slot that came back empty
#   — F3.9). blackceo-house-voice is the dedicated fallback persona
#   (fallback:true, excluded from normal competition) provisioned by the persona
#   pipeline; referencing the id here does not require it to exist yet — it is a
#   constant, resolved at dispatch. Never hardcode an operator-preference persona
#   over a client's configured default; a client `default_persona_id` (resolved
#   upstream in the CC) always wins over this constant.
GOVERNANCE_PERSONA_FALLBACK = "covey-7-habits"
DEFAULT_PERSONA_FALLBACK = "blackceo-house-voice"


def is_mechanical(text, *, delivery_verbs=()):
    """Return True if *text* is an operational/mechanical task needing no persona.

    Args:
        text: the task (or sub-task) description.
        delivery_verbs: optional iterable of extra multi-word phrases treated as
            mechanical via plain substring match. decompose-task.py passes
            DELIVERY_VERBS for its per-subtask gate; the selector passes nothing
            so the base rule is identical across callers.

    The base rule (multi-word substrings + word-boundary single tokens) is
    applied for EVERY caller; delivery_verbs only ADD to it, never replace it.
    """
    if not text:
        return False
    t = text.lower()
    if any(m in t for m in MECH_MULTIWORD):
        return True
    if any(re.search(r"\b" + re.escape(m) + r"\b", t) for m in MECH_SINGLEWORD):
        return True
    if delivery_verbs and any(m in t for m in delivery_verbs):
        return True
    return False


if __name__ == "__main__":
    # Quick self-test — run as: python3 mechanical-gate.py
    import sys
    base_true = ["please restart the server", "reboot the box", "ping the host",
                 "ls the directory", "chmod +x it", "chown the file",
                 "check disk usage", "check memory pressure"]
    base_false = ["write the sales emails", "plan the shipping strategy",
                  "review the controls", "build the tools page",
                  "design the hero image"]
    deliver_true = ["send the sequence", "deploy the funnel", "publish to the blog",
                    "upload the assets", "blast the list"]
    ok = True
    for t in base_true:
        if not is_mechanical(t):
            ok = False; print(f"  [FAIL] base should be mechanical: {t!r}")
    for t in base_false:
        if is_mechanical(t):
            ok = False; print(f"  [FAIL] base should NOT be mechanical: {t!r}")
        # base_false must also stay non-mechanical for the WHOLE-TASK selector
        # (no delivery verbs) — the decompose gate may treat some as delivery.
    for t in deliver_true:
        if is_mechanical(t):
            ok = False; print(f"  [FAIL] delivery verb must NOT hit base gate: {t!r}")
        if not is_mechanical(t, delivery_verbs=DELIVERY_VERBS):
            ok = False; print(f"  [FAIL] delivery verb should be mechanical for decompose: {t!r}")
    print("All tests PASSED" if ok else "SOME TESTS FAILED")
    sys.exit(0 if ok else 1)
