#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/scope_checker.py
# PIPELINE RULE SCOPE CHECK — the U05 pipeline rule "Form is
# universal-intake" (filter == "Form is universal-intake") must gate ONLY the
# universal author-intake form. This module is the fail-closed scope gate for
# that rule: it returns (ok, filter_set) and NEVER emits the filter string,
# the payload, or any part of either.
#
# WHY THIS EXISTS (U05 tooling; the U05 engine-manifest row's empty-filter
# doctrine): the intake front door is a WEBHOOK-TO-ROUTE — the gateway hooks
# surface (config/route-template.json /hooks/anthology-intake, match.source
# 'anthology-intake') answers ONLY through the box route. The U05 pipeline
# rule rides that same front door: a pipeline rule whose filter is EXACTLY
# "Form is universal-intake" (form == "universal-intake", byte-exact, one
# space around "is", nothing else) is in intake scope and may fire; anything
# else — an EMPTY filter, a wildcard, a renamed form token, a byte-drifted
# spelling — is OUT of scope and must not be accepted as the intake gate.
# Fail-closed by design: a missing / malformed / unrecognized filter is NOT
# in scope and returns ok=False with a typed reason. The caller decides the
# consequence (refuse, route elsewhere, or re-check against a stage policy) —
# this module NEVER fabricates a pass.
#
# FAIL-CLOSED BY DESIGN: this module is a pure, side-effect-free predicate:
# no network, no writes, no imports beyond the stdlib, and it never prints
# the filter string or the payload (no secret, PII, or client identifier can
# leak through it). It also NEVER prints a token of any kind — the filter
# string itself is a configuration surface, and the rule here is that it is
# only ever compared, never echoed.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py):
#   - Move in silence; operator-verbose only.
#   - Never print a secret value. This module prints NOTHING from the
#     payload, and NOTHING of the filter string beyond a reason code.
#   - Nothing Anthropic in any runtime file.
#   - Any module in this package that talks to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). This
#     module makes NO HTTP requests, so it needs no User-Agent; the rule is
#     recorded here so a future caller that adds a live read keeps the
#     browser UA discipline.
#
# RETURN CONTRACT: always a 2-tuple.
#   (True,  {"filter": <byte-exact filter>, "form": "universal-intake"})
#   (False, {"filter": <value-or-None>, "reason": <short code>})
# The value returned in the filter_set is the RAW filter string, verbatim,
# so a caller can log or compare it; it is a rule name, never a credential.
# No other field of the payload is ever surfaced.
# =============================================================================
"""scope_checker.py — U05 pipeline-rule scope check (filter == "Form is universal-intake")."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The ONE filter expression the U05 pipeline rule is scoped to gate — the
# universal author-intake form rule, BYTE-EXACT (capital "Form", single
# spaces around "is", the form slug lowercase with a hyphen). The engine's
# fixtures carry exactly this value; the U05 empty-filter doctrine is that
# an EMPTY filter (and any other expression) is out of intake scope. The
# filter is the independent identity signal; anything else must not be
# accepted as the intake gate.
UNIVERSAL_INTAKE_FILTER = "Form is universal-intake"

# The form token the filter names (the universal author-intake form). A
# filter that says "Form is <token>" is in scope ONLY when <token> is this
# byte-exact slug — mirrored from the u02 scope gate
# (u02_modules/scope_check.py UNIVERSAL_INTAKE_FORM); the two gates must
# agree, so the token lives here in one place and is never re-typed.
UNIVERSAL_INTAKE_FORM = "universal-intake"

# Candidate paths for the filter expression inside the payload, in priority
# order. The canonical surface is the top-level `filter` field; the
# workflows/trigger surfaces (workflow.trigger.filters, trigger.filters,
# pipeline.rules) are covered the same way the u02 scope gate covers its
# field candidates — first non-empty wins, never a guess.
FILTER_CANDIDATE_PATHS = (
    "filter",
    "workflow.trigger.filters",
    "trigger.filters",
    "pipeline.rules",
)


def get_by_path(payload, dotted: str):
    """Descend a dotted path through dicts. A non-dict node anywhere along the
    path stops the walk (None), never raises. A list-of-dicts node is walked
    element-wise so a workflow-trigger filters list reads the same as a flat
    dict; a list-of-{key,value} node is resolved to its dict of key -> value
    first (the Convert and Flow / Flow customData shape)."""
    node = payload
    for part in dotted.split("."):
        if isinstance(node, list):
            if not node:
                return None
            if all(isinstance(e, dict) for e in node):
                node = [e.get(part) for e in node]
            else:
                node = {str((e.get("key") or "")).strip(): e.get("value")
                        for e in node if isinstance(e, dict) and e.get("key")}
                if not node:
                    return None
                node = node.get(part)
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _scalar(v):
    """A scalar string candidate, or None. Never prints anything."""
    if isinstance(v, str):
        s = v.strip()
        return s or None
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return None


def _flatten(value):
    """Reduce a walked node to a list of scalar strings. A scalar stays a
    one-element list; a list of dicts contributes the scalar value of its
    named expression key — 'value' for the workflow-trigger filter shape (a
    filters array of {operator, value} rows) and 'filter' for a pipeline
    rules array of {filter, ...} rows; anything else is dropped. Never
    raises, never prints."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        out = []
        for e in value:
            if isinstance(e, dict):
                v = e.get("value")
                if v is None:
                    v = e.get("filter")
                if v is not None:
                    out.append(str(v))
            elif isinstance(e, str):
                out.append(e)
        return out
    return []


def extract_filter_string(payload, candidates=FILTER_CANDIDATE_PATHS):
    """The FIRST non-empty filter string along the candidate paths, or None.
    Pure: never raises, never prints. Returns the verbatim value (a rule
    name, never a credential)."""
    if not isinstance(payload, dict):
        return None
    for path in candidates:
        for v in _flatten(get_by_path(payload, path)):
            s = _scalar(v)
            if s:
                return s
    return None


def check(payload, *, filter_candidates=FILTER_CANDIDATE_PATHS,
          expected_filter=UNIVERSAL_INTAKE_FILTER,
          expected_form=UNIVERSAL_INTAKE_FORM):
    """U05 pipeline-rule scope check. Returns (ok, filter_set):

      (True,  {"filter": <byte-exact filter>, "form": "universal-intake"})
              -- the rule's filter is EXACTLY "Form is universal-intake" (in
                 scope; the rule may fire as the intake gate).
      (False, {"filter": <value-or-None>, "reason": <code>}) -- NOT in scope.
              reason is one of:
                "not_a_dict"            payload is not a JSON object
                "filter_missing"        no filter along the candidate paths
                "filter_unrecognized"   the filter is not the byte-exact
                                        intake expression (includes an EMPTY
                                        filter, a wildcard, and any drift)
                "filter_malformed"      the filter is a valid expression but
                                        names a form other than
                                        universal-intake
              "unknown" if the caller-supplied expected_filter is empty.

    FAIL-CLOSED: any ambiguity returns (False, ...) with a typed reason; the
    check NEVER fabricates a pass and never prints the payload or any part of
    it (the filter_set carries only the filter string — a rule NAME, never a
    credential — plus the form token the rule gates)."""
    if not isinstance(payload, dict):
        return False, {"filter": None, "reason": "not_a_dict"}

    want = (expected_filter or "").strip()
    if not want:
        return False, {"filter": None, "reason": "unknown"}
    want_form = (expected_form or "").strip() or "universal-intake"

    flt = extract_filter_string(payload, filter_candidates)
    if flt is None:
        return False, {"filter": None, "reason": "filter_missing"}

    if flt == want:
        return True, {"filter": flt, "form": want_form}

    # An empty filter is the U05 attack (empty-filter doctrine): never a pass.
    if not flt.strip():
        return False, {"filter": None, "reason": "filter_missing"}

    # A byte-drifted expression ("Form is universal intake", "form is
    # universal-intake", "universal-intake", "*", ...) is never the gate.
    if flt.strip().lower() != want.lower():
        return False, {"filter": flt, "reason": "filter_unrecognized"}

    # Same words, different bytes: a case or spacing drift (a rule that would
    # silently NOT match the form the engine's fixtures carry) — out of scope,
    # never folded into the canonical expression.
    return False, {"filter": flt, "reason": "filter_unrecognized"}


# ---------------------------------------------------------------------------
# CLI surface (tiny, deterministic; used by the sibling scripts and tests).
# ---------------------------------------------------------------------------
def main(argv=None):
    """Read ONE JSON payload from stdin (the same seam the gateway transform
    uses: it pipes the form JSON on stdin) and print ONE line to stdout:
    'IN_SCOPE' or 'OUT_OF_SCOPE <reason>'. stderr stays silent on the happy
    path. Never echoes the payload or the filter string."""
    if argv is None:
        argv = sys.argv[1:]
    if "--self-test" in argv:
        return self_test()
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(
            "scope_checker.py -- U05 pipeline-rule scope check (Skill 59 "
            "U05)\n"
            "  reads ONE JSON payload on stdin; prints 'IN_SCOPE' or\n"
            "  'OUT_OF_SCOPE <reason>' on stdout. Fail-closed. Never echoes\n"
            "  the payload or the filter string. --self-test runs the offline\n"
            "  battery.\n")
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 -- an unparseable body is typed, never a crash
        sys.stdout.write("OUT_OF_SCOPE not_a_dict\n")
        return 0
    ok, flt = check(payload)
    if ok:
        sys.stdout.write("IN_SCOPE\n")
        return 0
    sys.stdout.write("OUT_OF_SCOPE %s\n" % (flt.get("reason") or "unknown"))
    return 0


# ---------------------------------------------------------------------------
# Self-test — OFFLINE golden + attack fixtures, no network, no secrets.
# ---------------------------------------------------------------------------
def self_test():
    """Offline acceptance battery. Any failure prints a one-line note to
    stderr and returns 1; the happy path prints 'scope_checker self-test: OK'
    to stderr and returns 0. Never touches the network; never prints the
    filter string or any value from the fixtures."""
    import io

    dev = io.StringIO()

    # -- the golden U05 pipeline-rule payload (canonical surface) -------------
    golden = {"source": "anthology-intake", "location": "LOC-synthetic-AAA",
              "filter": "Form is universal-intake"}
    ok, flt = check(golden)
    assert ok, "golden U05 filter must be IN scope: %s" % flt
    assert flt.get("filter") == "Form is universal-intake", \
        "filter_set must carry the verbatim filter string"
    assert flt.get("form") == "universal-intake", \
        "filter_set must carry the gated form token"

    # -- the workflow-trigger filters shape (filters array of rows) -----------
    trigger = {"workflow": {"trigger": {"filters": [
        {"operator": "is", "value": "Form is universal-intake"}]}}}
    ok, _ = check(trigger)
    assert ok, "workflow.trigger.filters shape must be IN scope"

    # -- the trigger.filters shape --------------------------------------------
    ok, _ = check({"trigger": {"filters": [
        {"key": "form", "value": "Form is universal-intake"}]}})
    assert ok, "trigger.filters shape must be IN scope"

    # -- the pipeline.rules shape ---------------------------------------------
    ok, _ = check({"pipeline": {"rules": [
        {"filter": "Form is universal-intake"}]}})
    assert ok, "pipeline.rules shape must be IN scope"

    # -- ATTACK fixtures: every mutation REFUSED (fail-closed) -----------------
    # 1. the U05 empty-filter attack: a present-but-EMPTY filter is never a
    #    pass (an empty filter matches EVERYTHING — exactly the U05 doctrine
    #    that a rule with no filter must not be the intake gate)
    ok, flt = check({"filter": ""})
    assert not ok and flt.get("reason") == "filter_missing", \
        "an empty filter must refuse: %s" % flt
    # 2. whitespace-only filter (looks empty to the eye, not to the gate)
    ok, flt = check({"filter": "   "})
    assert not ok and flt.get("reason") == "filter_missing", \
        "a whitespace-only filter must refuse: %s" % flt
    # 3. filter missing entirely
    ok, flt = check({"source": "anthology-intake"})
    assert not ok and flt.get("reason") == "filter_missing", \
        "a missing filter must refuse: %s" % flt
    # 4. a DIFFERENT form token is never accepted as the intake gate
    ok, flt = check({"filter": "Form is contact-info-form"})
    assert not ok and flt.get("reason") == "filter_unrecognized", \
        "an unrelated filter must refuse: %s" % flt
    # 5. a wildcard filter is never the gate
    ok, flt = check({"filter": "*"})
    assert not ok and flt.get("reason") == "filter_unrecognized", \
        "a wildcard filter must refuse: %s" % flt
    # 6. byte drift in the same words — case (a rule that would silently not
    #    match the engine's fixtures) is out of scope, never folded in
    ok, flt = check({"filter": "form is universal-intake"})
    assert not ok and flt.get("reason") == "filter_unrecognized", \
        "a case-drifted filter must refuse: %s" % flt
    # 7. byte drift in the spacing — the same class of silent no-match
    ok, flt = check({"filter": "Form is  universal-intake"})
    assert not ok and flt.get("reason") == "filter_unrecognized", \
        "a spacing-drifted filter must refuse: %s" % flt
    # 8. a bare form token without the "Form is" expression
    ok, flt = check({"filter": "universal-intake"})
    assert not ok and flt.get("reason") == "filter_unrecognized", \
        "a bare form token must refuse: %s" % flt
    # 9. non-dict payload
    ok, flt = check(["not", "a", "dict"])
    assert not ok and flt.get("reason") == "not_a_dict", "a non-dict must refuse"
    ok, flt = check(None)
    assert not ok and flt.get("reason") == "not_a_dict", "None must refuse"
    # 10. malformed caller-supplied expectation -> unknown, never a pass
    ok, flt = check(golden, expected_filter="")
    assert not ok and flt.get("reason") == "unknown", \
        "an empty expectation must refuse as unknown, never pass"

    sys.stderr.write("scope_checker self-test: OK "
                     "(golden U05 filter IN_SCOPE, canonical surfaces, 10 "
                     "attack fixtures refused fail-closed: empty-filter / "
                     "whitespace-filter / filter-missing / unrelated-form / "
                     "wildcard / case-drift / spacing-drift / bare-token / "
                     "non-dict / malformed-expectation)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
