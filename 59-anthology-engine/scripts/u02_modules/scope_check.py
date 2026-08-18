#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/scope_check.py
# INTAKE FIRE TRIGGER SCOPE CHECK — the Intake Fire trigger (the tag -> intake
# hook automation: contact_tag trigger + a Custom Webhook action whose URL comes
# from the {{ custom_values.anthology_webhook_url }} merge) must fire ONLY the
# UNIVERSAL author-intake form (form == "universal-intake"). This module is the
# fail-closed scope gate for that front door: it returns (ok, filter_set) and
# NEVER emits the payload or any part of it.
#
# WHY THIS EXISTS (U02 tooling; MASTER-SPEC U02 item 5 "Intake Fire trigger
# scope"): the intake front door is a WEBHOOK-TO-ROUTE — the gateway hooks
# surface (config/route-template.json /hooks/anthology-intake, match.source
# 'anthology-intake') answers ONLY through the box route, and the snapshot's
# tag->notification workflow POSTs the intake hook from the
# {{ custom_values.anthology_webhook_url }} merge (never an inlined URL —
# AF-AE-TEMPLATE-INTAKE-FIRE; never-a-real-token). live_verify_template.py
# checks that TEMPLATE side structurally. THIS module checks the PAYLOAD side:
# the router's own stage-form policy already routes on the hidden `stage`
# field (intake_stage_tokens: intake / s0 / s0_intake), so the form token is
# the independent second signal — the submission must identify itself as the
# universal author-intake form, and the CHECK FIRES ONLY WHEN THAT TOKEN IS
# PRESENT. Anything else is out of scope for the Intake Fire trigger and must
# not be accepted as one.
#
# FAIL-CLOSED BY DESIGN: a missing / malformed / unrecognized form token is
# NOT in scope and returns ok=False with a reason. The caller decides the
# consequence (refuse, route elsewhere, or re-check against a stage policy) —
# this module NEVER fabricates a pass. It is a pure, side-effect-free
# predicate: no network, no writes, no imports beyond the stdlib, and it never
# prints the payload or any field value (no secret, PII, or client identifier
# can leak through it).
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py):
#   - Move in silence; operator-verbose only.
#   - Never print a secret value. This module prints NOTHING from the payload.
#   - Nothing Anthropic in any runtime file.
#   - Any module in this package that talks to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). This
#     module makes NO HTTP requests, so it needs no User-Agent; the rule is
#     recorded here so a future caller that adds a live read keeps the browser
#     UA discipline.
#
# RETURN CONTRACT: always a 2-tuple.
#   (True,  {"form": "universal-intake", "stage_tokens": [...]})  in scope
#   (False, {"form": <value-or-None>, "reason": <short code>})     out of scope
# The value returned in the filter_set is the RAW form token, verbatim, so a
# caller can log or compare it; it is a form name, never a credential. No
# other payload field is ever surfaced.
# =============================================================================
"""scope_check.py — Intake Fire trigger scope check (form == universal-intake)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The ONE form token the Intake Fire trigger is scoped to fire (the universal
# author-intake form, byte-exact). The engine's fixtures carry exactly this
# value (fixtures/webhook/t4-valid-intake.json etc.); the router classifies the
# hidden `stage` token separately (intake_router.py intake_stage_tokens:
# intake / s0 / s0_intake). The form token is the independent identity signal;
# both must agree for a submission to be in intake scope.
UNIVERSAL_INTAKE_FORM = "universal-intake"

# The stage tokens the router treats as the universal intake form (mirrors
# intake_router.py BUILTIN_DEFAULTS intake_stage_tokens). Exposed in the
# filter_set so a caller can cross-check the payload's stage signal without
# re-deriving the policy. If the router's policy drifts, a caller can pass its
# own via check(..., stage_tokens=[...]); the default here is the engine's.
DEFAULT_INTAKE_STAGE_TOKENS = ("intake", "s0", "s0_intake")

# Candidate paths for the form token inside the payload, in priority order.
# The canonical surface is the top-level `form` field (the fixture shape);
# the Convert and Flow / Flow customData list-of-{key,value} shape and the
# `data` envelope are covered the same way intake_router.py's field_candidates
# covers its fields — first non-empty wins, never a guess.
FORM_CANDIDATE_PATHS = (
    "form",
    "customData.form",
    "data.form",
)

# Recognized-by-convention aliases a client-facing gateway transform might
# forward instead of the canonical token (the route-template transform pipes
# the form JSON through untouched; these cover a forwarded or renamed shape).
_KNOWN_FORM_ALIASES = ("universal-intake", "universal_intake", "intake")


def get_by_path(payload, dotted: str):
    """Descend a dotted path through dicts. A non-dict node anywhere along the
    path stops the walk (None), never raises. List-of-{key,value} nodes are
    resolved to their dict of key -> value first, so the Convert and Flow /
    Flow customData shape reads the same as a flat dict."""
    node = payload
    for part in dotted.split("."):
        if isinstance(node, list):
            if not node or not all(isinstance(e, dict) for e in node):
                return None
            node = {str((e.get("key") or "")).strip(): e.get("value") for e in node if e.get("key")}
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


def extract_form_token(payload, candidates=FORM_CANDIDATE_PATHS):
    """The FIRST non-empty form token along the candidate paths, or None.
    Pure: never raises, never prints. Returns the verbatim value (a form name,
    never a credential)."""
    if not isinstance(payload, dict):
        return None
    for path in candidates:
        val = _scalar(get_by_path(payload, path))
        if val:
            return val
    return None


def _as_set(value):
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, (list, tuple, set)):
        return {str(v).strip().lower() for v in value if str(v).strip()}
    return set()


def check(payload, *, stage_tokens=DEFAULT_INTAKE_STAGE_TOKENS,
          form_candidates=FORM_CANDIDATE_PATHS):
    """Intake Fire trigger scope check. Returns (ok, filter_set):

      (True,  {"form": <token>, "stage_tokens": [...]})  -- the submission
              identifies as the universal author-intake form (in scope; the
              trigger may fire for it).
      (False, {"form": <token-or-None>, "reason": <code>}) -- NOT in scope.
              reason is one of:
                "not_a_dict"            payload is not a JSON object
                "form_token_missing"    no form token along the candidate paths
                "form_token_unrecognized" the token is not a known intake alias
                "stage_token_mismatch"  the payload's stage token is present but
                                        is not one of the intake stage tokens
                                        (form token and stage token disagree)
              "unknown" if the caller-supplied stage_tokens is malformed.

    FAIL-CLOSED: any ambiguity returns (False, ...) with a typed reason; the
    check NEVER fabricates a pass and never prints the payload or any part of
    it (the filter_set carries only the form token — a form NAME, not a
    credential — plus the stage-token policy, never the payload's own stage
    value)."""
    if not isinstance(payload, dict):
        return False, {"form": None, "reason": "not_a_dict"}

    stage_tok = _as_set(stage_tokens)
    if not stage_tok:
        return False, {"form": None, "reason": "unknown"}

    form = extract_form_token(payload, form_candidates)
    if form is None:
        return False, {"form": None, "reason": "form_token_missing"}

    form_l = form.strip().lower()
    if form_l not in _KNOWN_FORM_ALIASES:
        return False, {"form": form, "reason": "form_token_unrecognized"}

    # The stage signal is the router's OWN routing key (intake_router.py
    # classify_stage). The form token says "universal intake", the stage token
    # must agree that this is the intake stage. Present-but-disagreeing means
    # the submission is a per-stage form claiming the intake front door — out
    # of scope for the Intake Fire trigger, never accepted by alias alone.
    stage = _scalar(get_by_path(payload, "stage")) or _scalar(get_by_path(payload, "form_stage")) \
        or _scalar(get_by_path(payload, "customData.stage")) or _scalar(get_by_path(payload, "customData.form_stage"))
    if stage is not None and stage.strip().lower() not in stage_tok:
        return False, {"form": form, "reason": "stage_token_mismatch"}

    return True, {"form": form, "stage_tokens": sorted(stage_tok)}


# ---------------------------------------------------------------------------
# CLI surface (tiny, deterministic; used by the sibling scripts and tests).
# ---------------------------------------------------------------------------
def main(argv=None):
    """Read ONE JSON payload from stdin (the same seam the gateway transform
    uses: it pipes the form JSON on stdin) and print ONE line to stdout:
    'IN_SCOPE' or 'OUT_OF_SCOPE <reason>'. stderr stays silent on the happy
    path. Never echoes the payload."""
    if argv is None:
        argv = sys.argv[1:]
    if "--self-test" in argv:
        return self_test()
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(
            "scope_check.py -- Intake Fire trigger scope check (Skill 59 U02)\n"
            "  reads ONE JSON payload on stdin; prints 'IN_SCOPE' or\n"
            "  'OUT_OF_SCOPE <reason>' on stdout. Fail-closed. Never echoes\n"
            "  the payload. --self-test runs the offline battery.\n")
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
    stderr and returns 1; the happy path prints 'scope_check self-test: OK'
    to stderr and returns 0. Never touches the network; never prints a value
    from the fixtures beyond the form token."""
    import io

    dev = io.StringIO()

    # -- the golden universal-intake submission (fixture shape) ---------------
    golden = {"source": "anthology-intake", "location": "LOC-synthetic-AAA",
              "form": "universal-intake", "contact_id": "C-0001",
              "anthology_id": "A-0001", "stage": "s0_intake"}
    ok, flt = check(golden)
    assert ok, "golden universal-intake must be IN scope: %s" % flt
    assert flt.get("form") == "universal-intake", "filter_set must carry the verbatim form token"
    assert "s0_intake" in (flt.get("stage_tokens") or []), "filter_set must carry the stage policy"

    # -- the canonical stage token variants all pass --------------------------
    for stage in ("intake", "s0", "s0_intake"):
        ok, _ = check(dict(golden, stage=stage))
        assert ok, "stage token %r must be IN scope" % stage

    # -- known aliases resolve (never a guess) ---------------------------------
    for alias in ("universal_intake", "intake"):
        ok, _ = check(dict(golden, form=alias))
        assert ok, "alias %r must be IN scope" % alias

    # -- the Convert and Flow / Flow customData shape --------------------------
    custom = {"source": "anthology-intake",
              "customData": [{"key": "form", "value": "universal-intake"},
                             {"key": "stage", "value": "s0_intake"}]}
    ok, _ = check(custom)
    assert ok, "customData list-of-{key,value} shape must be IN scope"

    # -- ATTACK fixtures: every mutation REFUSED (fail-closed) -----------------
    # 1. a per-stage form claiming the intake front door by stage token
    stage_form = dict(golden, form="outline-approval", stage="s4_blurb_outline")
    ok, flt = check(stage_form)
    assert not ok and flt.get("reason") == "form_token_unrecognized", \
        "a per-stage form must NOT be in Intake Fire scope: %s" % flt
    # 2. form token present but the stage token disagrees (t7 shape mutated)
    liar = dict(golden, stage="s4_blurb_outline")
    ok, flt = check(liar)
    assert not ok and flt.get("reason") == "stage_token_mismatch", \
        "disagreeing stage token must refuse: %s" % flt
    # 3. form token missing entirely
    missing = {k: v for k, v in golden.items() if k != "form"}
    ok, flt = check(missing)
    assert not ok and flt.get("reason") == "form_token_missing", \
        "a missing form token must refuse: %s" % flt
    # 4. form token empty / whitespace only
    ok, flt = check(dict(golden, form="   "))
    assert not ok and flt.get("reason") == "form_token_missing", \
        "an empty form token must refuse: %s" % flt
    # 5. a different form token is never accepted by alias
    ok, flt = check(dict(golden, form="contact-info-form"))
    assert not ok and flt.get("reason") == "form_token_unrecognized", \
        "an unrelated form token must refuse: %s" % flt
    # 6. non-dict payload
    ok, flt = check(["not", "a", "dict"])
    assert not ok and flt.get("reason") == "not_a_dict", "a non-dict must refuse"
    ok, flt = check(None)
    assert not ok and flt.get("reason") == "not_a_dict", "None must refuse"
    # 7. malformed caller-supplied stage policy -> unknown, never a pass
    ok, flt = check(golden, stage_tokens=[])
    assert not ok and flt.get("reason") == "unknown", \
        "an empty stage policy must refuse as unknown, never pass"

    sys.stderr.write("scope_check self-test: OK "
                     "(golden universal-intake IN_SCOPE, canonical stage tokens, "
                     "known aliases, customData shape, 7 attack fixtures refused "
                     "fail-closed: per-stage-form / stage-token-mismatch / "
                     "form-missing / form-empty / unrelated-form / non-dict / "
                     "malformed-policy)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
