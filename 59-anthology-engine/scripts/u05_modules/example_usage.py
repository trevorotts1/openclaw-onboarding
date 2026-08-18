#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/example_usage.py  (U05 tooling)
# EXAMPLE-USAGE RUNNER — a fail-closed WORKED EXAMPLE of the U05 live surface
# end to end: READ the Intake Fire front-door workflow on a Convert and Flow
# location through the internal rail (the ONLY workflow surface this repo has
# PROVEN live — Skill 58 verify-podcast-ghl-workflows.py), then run every
# pure sibling law over the read and the canonical fixtures: the golden
# scoped-read gate (u05_modules.golden_scoped) proves a single-subject read
# sees EXACTLY its own subject; the empty-anthology-filter attack
# (u05_modules.attack_unscoped) proves an UNFILTERED read FAILS; the
# wrong-form-on-the-filter attack (u05_modules.attack_wrong_form) proves a
# rule naming any other form is REFUSED at the intake filter; and the
# negative verifier (u05_modules.negative_verifier) certifies the
# universal-review submission does NOT fire Intake Fire — then emit ONE JSON
# report on stdout. It demonstrates BY EXAMPLE how the U05 modules COMPOSE
# on a real location.
#
# WHAT THIS MODULE IS NOT: it is NOT a gate, NOT a checker, and NOT a
# manifest row (docs_u05.py records U05_MODULES = None — a doc that claims a
# manifest row that does not exist is drift). It makes NO judgment of its
# own about any law — every judgment is delegated to the sibling modules,
# which stay the single implementation of each law (golden_scoped owns the
# SCOPED-READ law, attack_unscoped owns the EMPTY-FILTER refusal,
# attack_wrong_form owns the WRONG-FORM refusal, negative_verifier owns the
# DOES-NOT-FIRE certification, workflow_reader owns the LIVE READ). This
# module only ORCHESTRATES those laws in the documented order and reports
# the outcome — the runnable companion to the USAGE blocks in the sibling
# headers. A NEW judgment defined here would create a SECOND implementation
# of a law, so there is deliberately none.
#
# FAIL-CLOSED BY CONSTRUCTION: every step either passes through the sibling
# law (its exit code is honored verbatim — a STOP refusal is NEVER downgraded
# to a pass) or is SKIPPED with the reason surfaced. If the live surface
# cannot be certified (unreachable / edge-blocked), the report says HELD
# (UNDETERMINED) — never "verified". The two attack steps are EXPECTED-FAIL
# steps: the empty-filter read and the wrong-form rule MUST FAIL (exit 5) —
# an attack that PASSES any gate is a broken gate, and the composition FAILS
# rather than report success. The negative verifier is an EXPECTED-CERTIFY
# step: the review form MUST certify does-not-fire (exit 0) — a fires-intake
# verdict or an INDETERMINATE refusal is a FAIL of the composition, never a
# silent pass.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The live read rides the internal
# rail credential, resolved via anthology_registry (ANTHOLOGY_GHL_FIREBASE_*
# / GOHIGHLEVEL_FIREBASE_* refresh token + the Firebase API-key label, or
# the PIT fallback — live process env first, then the three canonical client
# env stores; SET / NOT SET only on every operator surface; a value is NEVER
# printed). The location id is the contract's template location
# (source_template_location.template_location_id — operator infrastructure
# config, not a secret), overridable with --location-id; it is masked to its
# LAST 4 characters (reg._mask_location) on every operator surface.
#
# BROWSER UA: every request rides reg.InternalRailClient / reg.CafClient,
# which apply CAF_BROWSER_UA on EVERY request — the Cloudflare edge fronting
# services.leadconnectorhq.com and backend.leadconnectorhq.com 403s urllib's
# default "Python-urllib/x.y" User-Agent at the WAF edge (CF error 1010)
# before the request ever reaches Convert and Flow (GK-09; the proven-live
# Podcast gate string, ported byte-for-byte in anthology_registry.py).
# Scope-vs-edge-block discrimination is the registry's own: a bare 401/403
# whose body does NOT match the genuine scope-denial signature raises
# UpstreamBlockedError -> HELD, never a scope STOP. The offline self-test
# PROVES the request carries the browser UA by asserting
# reg.CAF_BROWSER_UA byte-for-byte against the Podcast gate's proven-live
# string — the same pin the registry's own self-test enforces — so a drift
# in the wiring is caught OFFLINE, never first seen as a 1010.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  all steps PASSED — front door found, golden scoped read PASSES,
#      empty-filter attack FAILS (as it must), wrong-form attack FAILS (as
#      it must), negative verifier CERTIFIES does-not-fire; also --plan and
#      --self-test pass
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — rail credential labels NOT SET, location id NOT SET,
#      or a sibling law STOPPED (an empty/malformed scope policy in the
#      negative verifier, a WorkflowReadError in the reader) — honored
#      verbatim, never downgraded
#   3  Convert and Flow / internal rail unreachable or upstream edge block
#      (HELD; retryable — the outcome is UNDETERMINED, never proven verified)
#   4  enforced violation — an OFFLINE self-test assertion tripped
#      (AF-AE-EXAMPLE-USAGE-* family). A tamper NEVER masquerades as exit 1.
#   5  mismatch — an expected-fail step did NOT fail (the empty-filter or
#      wrong-form attack PASSED a gate it must FAIL), the golden scoped gate
#      REFUSED the read, or the negative verifier FAILED / went
#      INDETERMINATE (the review form fires Intake Fire)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --plan and --self-test are OFFLINE and need NO token and NO
# network). This is the canonical example invocation:
#
#   python3 scripts/u05_modules/example_usage.py run [--location-id ID]
#   python3 scripts/u05_modules/example_usage.py plan
#   python3 scripts/u05_modules/example_usage.py self-test
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (InternalRailClient, CafClient, resolve_pit,
# resolve_firebase_refresh_token, _resolve_firebase_api_key,
# _mask_location, _stop, and the exception classes) and the sibling U05
# modules (workflow_reader, golden_scoped, attack_unscoped,
# attack_wrong_form, negative_verifier) imported BY NAME.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value;
# --plan and --self-test are OFFLINE.
# =============================================================================
"""example_usage.py — fail-closed worked example of the U05 live surface
composed end to end (U05 tooling, Skill 59)."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the internal-rail / LeadConnector clients,
# and its label resolution is the house credential contract. The sibling U05
# modules stay the single implementation of each law — this module only
# orchestrates them and honors their exit codes verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u05_modules.attack_unscoped as unscoped  # noqa: E402
import u05_modules.attack_wrong_form as wrongform  # noqa: E402
import u05_modules.golden_scoped as golden  # noqa: E402
import u05_modules.negative_verifier as neg  # noqa: E402
import u05_modules.workflow_reader as reader  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The report contract this runner owns (one fixed string, so a machine
# consumer can never mistake another JSON object for the example report).
EXAMPLE_CONTRACT = "anthology-engine-example-usage"

# The front-door workflow name — the SAME name law workflow_reader finds by
# (never re-implemented here; the reader's own constant is the authority).
FRONT_DOOR_NAME = reader.WORKFLOW_NAME

def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)

# ---------------------------------------------------------------------------
# Report builder — ONE JSON object on stdout (jsonout); human notes go to
# out (stderr) only. Secret VALUES never appear: the rail credential is
# reported by LABEL + SET/NOT-SET and the location id as a masked marker. A
# shape-fail in the contract is a STOP refusal, never a blind report. The
# exit code is THREADED THROUGH: a STOP (2) or HELD (3) never masquerades
# as a mismatch (5) — the sibling's code is honored verbatim.
# ---------------------------------------------------------------------------
def _report(*, ok: bool, verdict: str, steps, masked_location: str,
            cred_label: str, out, jsonout, exit_code: int = EX_MISMATCH) -> int:
    jsonout.write(json.dumps({
        "contract": EXAMPLE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": verdict,
        "exit_code": exit_code,
        "credential": cred_label + " (SET)",   # by LABEL, never by value
        "location_masked": masked_location,  # last 4 chars only, never full
        "steps": steps,
        "note": "front-door read + golden scoped gate + empty-filter attack "
                "+ wrong-form attack + negative verifier, composed end to end",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    out.write("[example-usage] %s\n" % verdict)
    return EX_OK if ok else exit_code

# ---------------------------------------------------------------------------
# The example run — orchestration ONLY. Every judgment is delegated to the
# sibling law; its exit code is honored verbatim (never downgraded).
# ---------------------------------------------------------------------------
def example_run(rail, location_id: str, *, out=None, jsonout=None) -> int:
    """Run the U05 example surface on a live location.

    - workflow_reader's live read (internal rail GET /workflow/<loc>/list)
      against the front-door name law     -> the ONE workflow id (found=false
                                             carries NO id — no id, no pass)
    - golden_scoped's payload gate over the canonical single-subject listing
                                          -> the SCOPED-READ law holds
    - attack_unscoped's empty-filter read -> the UNFILTERED read FAILS
    - attack_wrong_form's wrong-form rule -> a rule naming any other form
                                             is REFUSED at the intake filter
    - negative_verifier's certification over the universal-review shape
                                          -> does-not-fire CERTIFIED

    Machine surface: the ONE JSON report object lands on jsonout (stdout);
    every sibling gate document and every human note go to out (stderr).
    """
    out = out or sys.stderr
    jsonout = jsonout or sys.stdout
    steps = []

    # (1) LIVE READ — the front door. workflow_reader owns the read and the
    #     name law; its return is the ONE result dict {ok, found,
    #     workflow_id, af_code, ...} — found=false carries NO workflow_id
    #     (no id, no pass) and a named af_code (WORKFLOWS-NOT-FOUND /
    #     WORKFLOWS-EMPTY / PIN-MISSING). A broken listing shape raises
    #     WorkflowReadError (STOP family, exit 2), a scope denial raises
    #     reg.ScopeDenied (STOP), and an edge block / transport failure
    #     raises reg.UpstreamBlockedError / reg.CafUnreachable /
    #     reg.InternalRailUnavailable (HELD, exit 3) — every code honored
    #     verbatim, never downgraded. The result's own report prints to
    #     stdout, so it is captured into the human channel here — the ONE
    #     machine document on stdout is this runner's report.
    try:
        with _sibling_stdout_to(out):
            result = reader.read_workflows(rail, location_id)
    except reader.WorkflowReadError as exc:
        steps.append({"step": "front-door", "ok": False, "exit": EX_STOP,
                      "verdict": "STOP: %s" % exc})
        return _report(ok=False, verdict="STOP: front door unreadable "
                       "(exit 2)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout,
                       exit_code=EX_STOP)
    except reg.ScopeDenied as exc:
        steps.append({"step": "front-door", "ok": False, "exit": EX_STOP,
                      "verdict": "STOP: %s" % exc})
        return _report(ok=False, verdict="STOP: token not authorized for "
                       "this scope (exit 2)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout,
                       exit_code=EX_STOP)
    except (reg.UpstreamBlockedError, reg.CafUnreachable,
            reg.InternalRailUnavailable) as exc:
        steps.append({"step": "front-door", "ok": False, "exit": EX_HELD,
                      "verdict": "HELD: %s" % exc})
        return _report(ok=False, verdict="HELD: Convert and Flow / rail "
                       "unreachable or edge-blocked (exit 3 — UNDETERMINED, "
                       "never verified)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout,
                       exit_code=EX_HELD)
    if not isinstance(result, dict) or result.get("ok") is not True:
        rc = EX_MISMATCH
        steps.append({"step": "front-door", "ok": False, "exit": rc,
                      "af_code": result.get("af_code") if isinstance(result, dict) else None,
                      "verdict": "Intake Fire front door not verified "
                                 "(af_code %s)"
                                 % (result.get("af_code") if isinstance(result, dict) else "?"),
                      "detail": "found=false carries NO workflow id — no id, "
                                "no pass"})
        return _report(ok=False,
                       verdict="FAIL: front door not verified (af_code %s)"
                               % (result.get("af_code") if isinstance(result, dict) else "?"),
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "front-door", "ok": True, "exit": EX_OK,
                  "matched_by": result.get("matched_by"),
                  "workflow_id_masked": result.get("workflow_id_masked"),
                  "verdict": "Intake Fire workflow found on the location "
                             "(matched by %s)" % result.get("matched_by")})

    # (2) GOLDEN SCOPED READ — a single-subject read sees EXACTLY its own
    #     subject (golden_scoped owns that law; exit 5 on refusal). The
    #     canonical listing is the fixture's own payload — the law is judged
    #     OFFLINE over the synthetic single-subject shape; the live read's
    #     scope discipline is proven by the reader's own parameterized
    #     WHERE-bound read (never a table sweep).
    with _sibling_stdout_to(out):
        rc = golden.payload(golden.golden_listing_payload(), out=out)
    if rc != EX_OK:
        steps.append({"step": "golden-scoped", "ok": False, "exit": rc,
                      "verdict": "scoped-read law REFUSED the golden listing"})
        return _report(ok=False, verdict="FAIL: scoped-read law REFUSED the "
                       "golden listing (see steps)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "golden-scoped", "ok": True, "exit": EX_OK,
                  "verdict": "golden single-subject read PASSES (exit 0)"})

    # (3) EMPTY-FILTER ATTACK — the UNFILTERED read (the ONE anthology
    #     filter dropped to empty, reaching every ledger row across ALL
    #     anthologies) MUST FAIL every unscoped-read gate. attack_unscoped
    #     owns that law; its payload gate ships the attack read and
    #     verify_live judges it FAIL (exit 5). This runner calls the raw law
    #     and maps the expected FAIL to a step pass — the SAME exit code,
    #     honored verbatim, never downgraded: a gate that the attack PASSES
    #     is a broken gate, and the composition FAILS.
    with _sibling_stdout_to(out):
        rc = unscoped.verify_live("", unscoped.ATTACK_LEDGER, out=out)
    if rc != EX_MISMATCH:
        steps.append({"step": "empty-filter", "ok": False, "exit": rc,
                      "verdict": "empty-filter attack did NOT FAIL"})
        return _report(ok=False, verdict="FAIL: empty-filter attack did NOT "
                       "FAIL (a gate passed an unscoped read — broken gate)",
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "empty-filter", "ok": True, "exit": EX_MISMATCH,
                  "verdict": "empty-filter attack FAILED as it must (exit 5)"})

    # (4) WRONG-FORM ATTACK — a rule whose filter names ANY form other than
    #     the byte-exact universal-intake form must be REFUSED at the intake
    #     filter (attack_wrong_form owns that law; verify_rule exits 5 on
    #     the wrong-form rule, 0 on the golden control). Same expected-fail
    #     composition as (3): an attack that PASSES any scope gate is a
    #     broken filter.
    with _sibling_stdout_to(out):
        rc = wrongform.verify_rule(wrongform.ATTACK_RULE, out=out)
    if rc != EX_MISMATCH:
        steps.append({"step": "wrong-form", "ok": False, "exit": rc,
                      "verdict": "wrong-form attack did NOT FAIL"})
        return _report(ok=False, verdict="FAIL: wrong-form attack did NOT "
                       "FAIL (a filter passed a foreign form — broken gate)",
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "wrong-form", "ok": True, "exit": EX_MISMATCH,
                  "verdict": "wrong-form attack FAILED as it must (exit 5)"})

    # (5) NEGATIVE VERIFIER — the universal-review decision form must NEVER
    #     re-enter the intake front door. negative_verifier owns the
    #     certification (check() -> one report dict, verify_exit() maps it
    #     onto the house exit codes). The certified does-not-fire shape is
    #     the review submission: it carries the "universal-review" form
    #     token, which is NOT an intake alias — the trigger's own gate
    #     refuses it (basis form_token_unrecognized), so it cannot fire.
    #     The report NEVER echoes the payload; only the verbatim form token
    #     (a form NAME, never a credential) rides the report.
    nonintake = {"form": "universal-review", "stage": "u8_decision"}
    report = neg.check(nonintake)
    rc = neg.verify_exit(report)
    if rc != EX_OK:
        steps.append({"step": "negative", "ok": False, "exit": rc,
                      "basis": report.get("basis"),
                      "verdict": "does-not-fire NOT certified (exit %d)" % rc})
        return _report(ok=False, verdict="FAIL: does-not-fire NOT certified "
                       "(exit %d — the review form fires Intake Fire, or the "
                       "certification went INDETERMINATE)" % rc,
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "negative", "ok": True, "exit": EX_OK,
                  "basis": report.get("basis"),
                  "verdict": "does-not-fire CERTIFIED (basis %s)"
                             % report.get("basis")})

    return _report(ok=True, verdict="VERIFIED", steps=steps,
                   masked_location=_mask_location(location_id),
                   cred_label="RAIL", out=out, jsonout=jsonout)

# ---------------------------------------------------------------------------
# Sibling-output guard — the sibling modules print their gate documents to
# stdout by contract. During composition this runner captures that stdout
# into the human channel so the ONE machine document on stdout is the
# report. Fail-closed: any stdout loss is an enforced violation, never a
# silent pass.
# ---------------------------------------------------------------------------
class _sibling_stdout_to:
    """Context manager: divert the sibling modules' stdout prints into out
    (the human channel) for the duration of the block."""

    def __init__(self, out):
        self._out = out
        self._old = None

    def __enter__(self):
        self._old = sys.stdout
        sys.stdout = self._out
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.stdout = self._old
        return False  # never swallow an exception; propagates fail-closed

# ---------------------------------------------------------------------------
# Offline plan (no network, no credentials) — the surface with sources.
# ONE JSON object on stdout (jsonout); no stderr notes.
# ---------------------------------------------------------------------------
def plan(*, out=None, jsonout=None) -> int:
    out = out or sys.stderr
    jsonout = jsonout or sys.stdout
    jsonout.write(json.dumps({
        "contract": EXAMPLE_CONTRACT + "-plan",
        "schema_version": 1,
        "front_door": FRONT_DOOR_NAME,
        "steps": [
            "front-door: workflow_reader reads the internal rail "
            "GET /workflow/<loc>/list?limit=200 (backend.leadconnectorhq.com "
            "-- the ONLY proven workflow surface) and finds the Intake Fire "
            "workflow by the name law (rides reg.InternalRailClient / "
            "reg.CafClient CAF_BROWSER_UA so the Cloudflare edge never "
            "1010s the read)",
            "golden-scoped: u05_modules.golden_scoped gates the canonical "
            "single-subject listing (filter key anthology_id, subject key "
            "contact_id::anthology_id) -- a scoped read sees EXACTLY its "
            "own subject, exit 0",
            "empty-filter: u05_modules.attack_unscoped verify_live judges "
            "the empty-filter read over the synthetic two-anthology ledger "
            "-- MUST FAIL exit 5 (an unfiltered read reaches every ledger "
            "row across ALL anthologies)",
            "wrong-form: u05_modules.attack_wrong_form verify_rule judges "
            "the wrong-form rule -- MUST FAIL exit 5 (a rule naming any "
            "form other than universal-intake is refused at the intake "
            "filter)",
            "negative: u05_modules.negative_verifier certifies the "
            "universal-review shape does NOT fire Intake Fire (basis "
            "form_token_unrecognized -- the review form token is not an "
            "intake alias, so the trigger's own gate refuses the payload "
            "and it cannot fire), exit 0",
        ],
        "note": "offline plan only — no network, no credential needed; "
                "judgments are made by the sibling modules, never here",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    return EX_OK

# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the orchestration
# never downgrades a refusal and the browser UA never drifts.
# ---------------------------------------------------------------------------
class _FakeRail:
    """Deterministic front-door workflow listing stub (mirrors
    workflow_reader's _FakeClient seam): 'rows' fixture, 'behavior' for
    scope/edge/transport."""

    def __init__(self, rows=None, behavior="ok"):
        self._rows = list(rows or [])
        self._behavior = behavior
        self.calls = []

    def _get(self, path):
        self.calls.append(path)
        if self._behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        return {"rows": list(self._rows)}


def _golden_rows():
    """The golden front-door listing: exactly the Intake Fire workflow row
    (the same shape workflow_reader's self-test golden rows carry)."""
    return [{"type": "workflow", "name": FRONT_DOOR_NAME, "id": "wf_golden"}]


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[example-usage] SELF-TEST FAILED "
                         "(AF-AE-EXAMPLE-USAGE-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK

def _self_test_body(dev) -> None:
    import contextlib

    # 1. The browser UA — a drift in the wiring is caught OFFLINE, never
    #    first seen as a CF 1010. Same pin as the registry's own self-test.
    assert reg.CAF_BROWSER_UA == (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ), "CAF_BROWSER_UA drifted from the Podcast gate's proven-live string"

    # 2. The sibling laws are consistent with each other — the empty-filter
    #    attack and the wrong-form attack share the SAME scope authority,
    #    and the negative verifier certifies exactly what the front door
    #    gates (delta_reporter.py single-implementation doctrine). The
    #    sibling's judge report prints to stdout by contract, so it is
    #    captured here — the self-test leaves stdout clean.
    assert wrongform.ATTACK_FORM != wrongform.u05scope.UNIVERSAL_INTAKE_FORM, \
        "the wrong-form attack must name a FOREIGN form"
    with contextlib.redirect_stdout(io.StringIO()):
        assert unscoped.verify_live(unscoped.SCOPED_BOOK_ID,
                                    unscoped.ATTACK_LEDGER,
                                    out=io.StringIO()) == EX_OK, \
            "the golden one-anthology scoped control must PASS"

    # 3. The front-door read: found on the golden listing (the reader's own
    #    self-test proves the reader; here we pin the composition seam).
    fake = _FakeRail(_golden_rows())
    result = reader.read_workflows(fake, "loc_tmpl")
    assert result.get("ok") is True and result.get("found") is True, \
        "the golden front-door listing must be found: %r" % result
    assert result.get("workflow_id") == "wf_golden", \
        "the golden front-door id must be returned"

    # 4. The registry's OWN self-test proves the UA rides on the wire —
    #    evidence the example run is protected the same way (its stdout
    #    receipt is captured — the ONLY machine document on stdout here is
    #    the example report).
    with contextlib.redirect_stdout(io.StringIO()):
        assert reg.self_test() == EX_OK, "registry self-test must pass"

    # 5. The example composition — the golden path exits 0 with every step
    #    in the documented order; the empty-filter and wrong-form steps are
    #    the expected-FAIL steps (they must exit 5).
    report_buf = io.StringIO()
    rc = example_run(_FakeRail(_golden_rows()), "loc_tmpl",
                     out=io.StringIO(), jsonout=report_buf)
    assert rc == EX_OK, "the golden composition must exit 0, got %s" % rc
    report = json.loads(report_buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "VERIFIED"
    assert report["contract"] == EXAMPLE_CONTRACT
    assert report["location_masked"] == "...tmpl", \
        "the location must be masked to the last-4 marker"
    steps = {s["step"]: s for s in report["steps"]}
    assert list(steps) == ["front-door", "golden-scoped", "empty-filter",
                           "wrong-form", "negative"], \
        "the composition must run the five steps in the documented order"
    assert steps["front-door"]["exit"] == EX_OK
    assert steps["front-door"]["matched_by"] in ("name", "alias"), \
        "the front-door step must report how the workflow matched"
    assert steps["golden-scoped"]["exit"] == EX_OK
    assert steps["empty-filter"]["exit"] == EX_MISMATCH, \
        "the empty-filter step must carry the expected exit 5"
    assert steps["wrong-form"]["exit"] == EX_MISMATCH, \
        "the wrong-form step must carry the expected exit 5"
    assert steps["negative"]["exit"] == EX_OK
    assert steps["negative"]["basis"] == "form_token_unrecognized", \
        "the negative step must certify with the named basis"

    # 6. A STOP by a sibling law is honored verbatim — never downgraded.
    rc = example_run(_FakeRail([], behavior="scope"), "loc_tmpl",
                     out=io.StringIO(), jsonout=io.StringIO())
    assert rc == EX_STOP, "a sibling STOP must exit 2, got %s" % rc

    # 7. A HELD by a sibling law (edge block) is honored verbatim — the
    #    outcome is UNDETERMINED, never reported verified.
    rc = example_run(_FakeRail([], behavior="edge"), "loc_tmpl",
                     out=io.StringIO(), jsonout=io.StringIO())
    assert rc == EX_HELD, "an edge block must HELD exit 3, got %s" % rc

    # 8. Never-print: no credential-shaped string on any surface.
    blob = report_buf.getvalue()
    for token in ("pit-", "Bearer ", "sk-", "eyJ"):
        assert token not in blob, \
            "surface leak: %r must never appear" % token

    dev.write("example_usage self-test: OK (browser UA pinned byte-exact; "
              "sibling laws consistent (wrong-form names a foreign form, "
              "golden scoped control PASSes); front-door read found on the "
              "golden listing; golden composition exits 0 with the five "
              "steps in order — empty-filter and wrong-form carry the "
              "expected exit 5, negative certifies with basis "
              "form_token_unrecognized; a sibling STOP is honored verbatim "
              "as exit 2; registry self-test passes; never a token shape)\n")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="example_usage.py",
        description="Fail-closed worked example of the U05 live surface "
                    "(Skill 59): read the Intake Fire front-door workflow, "
                    "prove the scoped-read law with the golden fixture, "
                    "prove the empty-filter and wrong-form attacks FAIL as "
                    "they must, certify the review form does NOT fire Intake "
                    "Fire — one JSON report, fail-closed; never prints a "
                    "secret value.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow template location id "
                         "(default: the contract's "
                         "source_template_location.template_location_id; "
                         "masked on every surface)")
    ap.add_argument("cmd", nargs="?", choices=["run", "plan", "self-test"],
                    default="run")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the sibling modules use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan(out=sys.stderr, jsonout=sys.stdout)

        # ---- live run ----
        # Credential BY LABEL, NEVER BY VALUE. The internal rail is the ONLY
        # proven workflow surface, so the refresh token is resolved first;
        # the PIT is resolved as a second rail credential when no refresh
        # token is SET (the same order workflow_reader.main uses).
        refresh_label, refresh = reg.resolve_firebase_refresh_token()
        rail = None
        if refresh:
            api_label, api_key = reg._resolve_firebase_api_key()
            if not api_key:
                reg._stop(sys.stderr,
                          "The Firebase refresh token is SET but the Firebase "
                          "API key is NOT SET.",
                          ["Checked (in order): %s — all NOT SET."
                           % ", ".join(reg.FIREBASE_API_KEY_LABELS),
                           "The internal rail cannot mint an id_token without "
                           "both labels. Set the API-key label and re-run."])
                return EX_STOP
            rail = reg.InternalRailClient(refresh, api_key)
            cred_label = refresh_label or "RAIL"
        else:
            pit_label, token = reg.resolve_pit()
            if not token:
                checked = ", ".join(reg.PIT_LABELS)
                reg._stop(sys.stderr,
                          "No Convert and Flow credential is SET.",
                          ["Checked (in order): refresh-token labels %s — "
                           "all NOT SET; PIT labels %s — all NOT SET."
                           % (", ".join(reg.FIREBASE_REFRESH_LABELS), checked),
                           "The example run reads the Intake Fire front door "
                           "against the operator's OWN template location; set "
                           "the template refresh token (preferred, the proven "
                           "workflow surface) or the template PIT and re-run."])
                return EX_STOP
            rail = _PitRailClient(token)
            cred_label = pit_label or "RAIL"
        loc_label, loc = reg.resolve_location(args.location_id)
        if not loc:
            reg._stop(sys.stderr, "No Convert and Flow Location id is SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.LOCATION_LABELS),
                       "Set the client's OWN location id and re-run."])
            return EX_STOP
        sys.stderr.write("[example-usage] rail credential resolved via %s "
                         "(SET). Location via %s (marker %s).\n"
                         % (cred_label, loc_label, reg._mask_location(loc)))
        return example_run(rail, loc, out=sys.stderr, jsonout=sys.stdout)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[example-usage] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except FileNotFoundError as exc:
        sys.stderr.write("[example-usage] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[example-usage] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


class _PitRailClient:
    """The PIT rides a plain urllib request with the same CAF_BROWSER_UA on
    the internal base — the same fallback workflow_reader.main builds (the
    refresh token IS the browser-session credential; the PIT carries the
    Authorization header instead, exactly as reg.CafClient sends it)."""

    def __init__(self, token):
        self._token = token

    def _get(self, path):
        import urllib.request
        req = urllib.request.Request(
            reg.INTERNAL_API_BASE + path,
            headers={"Authorization": "Bearer %s" % self._token,
                     "version": reg.INTERNAL_VERSION_HEADER,
                     "Accept": "application/json",
                     "User-Agent": reg.CAF_BROWSER_UA})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                body = b""
                try:
                    body = exc.read()
                except Exception:
                    body = b""
                kind = reg._auth_denial_kind(body)
                if kind == "scope":
                    raise reg.ScopeDenied(
                        "token not authorized for this scope (HTTP %s)"
                        % exc.code)
                raise reg.UpstreamBlockedError(
                    "HTTP %s did NOT match a Convert and Flow scope-denial "
                    "signature — likely a Cloudflare/WAF edge block, NOT a "
                    "token-scope problem (HTTP %s)" % (exc.code, exc.code))
            raise reg.CafUnreachable("Convert and Flow HTTP %s on %s"
                                     % (exc.code, path))
        except (urllib.error.URLError, TimeoutError, OSError,
                ValueError) as exc:
            raise reg.CafUnreachable("Convert and Flow transport error: %s"
                                     % type(exc).__name__)


if __name__ == "__main__":
    sys.exit(main())
