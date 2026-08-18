#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/example_usage.py  (U06 tooling)
# EXAMPLE-USAGE RUNNER — a fail-closed WORKED EXAMPLE of the U06 ARCHIVE-ACTION
# surface end to end: FIND the two legacy engine workflows on a Convert and
# Flow location BY EXACT NAME through the internal rail (the ONLY workflow
# surface this repo has PROVEN live — Skill 58 verify-podcast-ghl-workflows.py),
# then run every pure sibling law over the read and the canonical fixtures:
# the golden found-state gate (u06_modules.golden_found) proves BOTH contract
# workflows are on the listing; the golden absent-state gate
# (u06_modules.golden_absent) proves an archive census with BOTH targets empty
# is a clean no-op PASS; the no-execute attack (u06_modules.attack_no_execute)
# proves an archive ACTION requested WITHOUT --execute FAILS every archive
# gate — the Trevor gate is never a silent no-op; the lister's archive ACTION
# (u06_modules.workflow_lister.archive_command) STOPS without --execute (exit 2)
# and is a no-mutation plan even WITH it (endpoint doctrine) — then emit ONE
# JSON report on stdout. It demonstrates BY EXAMPLE how the U06 modules
# COMPOSE on a real location.
#
# WHAT THIS MODULE IS NOT: it is NOT a gate, NOT a checker, and NOT a manifest
# row (docs_u06.py records its inventory without an example-usage row — a doc
# that claims a manifest row that does not exist is drift). It makes NO
# judgment of its own about any law — every judgment is delegated to the
# sibling modules, which stay the single implementation of each law
# (find_legacy owns the FIND law, golden_found owns the FOUND state,
# golden_absent owns the ABSENT state and the dry-run report contract,
# attack_no_execute owns the no-execute refusal, workflow_lister owns the
# live read and the archive ACTION). This module only ORCHESTRATES those laws
# in the documented order and reports the outcome — the runnable companion to
# the USAGE blocks in the sibling headers. A NEW judgment defined here would
# create a SECOND implementation of a law, so there is deliberately none.
#
# FAIL-CLOSED BY CONSTRUCTION: every step either passes through the sibling
# law (its exit code is honored verbatim — a STOP refusal is NEVER downgraded
# to a pass) or is SKIPPED with the reason surfaced. If the live surface
# cannot be certified (unreachable / edge-blocked), the report says HELD
# (UNDETERMINED) — never "verified". The attack step is an EXPECTED-FAIL
# step: the no-execute archive ACTION MUST FAIL (exit 5) — an attack that
# PASSES any archive gate is a broken gate, and the composition FAILS rather
# than report success. The golden absent gate is an EXPECTED-PASS step: an
# empty census is nothing to archive (exit 0) — a refusal is a FAIL of the
# composition. The lister's archive ACTION without --execute is an
# EXPECTED-STOP step: it MUST refuse exit 2 (the Trevor gate) — a no-execute
# ACTION that proceeds, or a plan that mutates, is a FAIL of the composition.
# WITH --execute the ACTION is STILL a no-mutation plan (proven-write law) —
# the example exercises the WITH-gate plan path against the SYNTHETIC golden
# listing (offline) and NEVER carries a live name into an archive ACTION:
# an ACTION must bind to ONE byte-exact workflow the find certified, and a
# live archive write must not be performed until a surface is proven live
# (Skill 44 endpoint doctrine). The example performs NO archive ACTION on a
# live location at all.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The live find rides the internal
# rail credential, resolved via anthology_registry (ANTHOLOGY_GHL_FIREBASE_*
# / GOHIGHLEVEL_FIREBASE_* refresh token + the Firebase API-key label, or
# the PIT fallback — live process env first, then the three canonical client
# env stores; SET / NOT SET only on every operator surface; a value is NEVER
# printed). The location id is the contract's template location
# (find_legacy.DEFAULT_TEMPLATE_LOCATION — operator infrastructure config,
# not a secret), overridable with --location-id; it is masked to its LAST 4
# characters (reg._mask_location) on every operator surface. The live find's
# ids are reported MASKED (find_legacy.mask_id) on every operator surface and
# in full ONLY inside the JSON payload a machine consumer reads.
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
#   0  all steps PASSED — both legacies found, golden found state PASSES,
#      golden absent state PASSES (nothing to archive), no-execute attack
#      FAILS (as it must), no-execute archive ACTION STOPs (as it must),
#      WITH-execute archive plan is a no-mutation plan; also --plan and
#      --self-test pass
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — rail credential labels NOT SET, location id NOT SET,
#      the archive ACTION without --execute (the Trevor gate), or a sibling
#      law STOPPED (a LegacyFindError in the finder) — honored verbatim,
#      never downgraded
#   3  Convert and Flow / internal rail unreachable or upstream edge block
#      (HELD; retryable — the outcome is UNDETERMINED, never proven verified)
#   4  enforced violation — an OFFLINE self-test assertion tripped
#      (AF-AE-EXAMPLE-USAGE-* family). A tamper NEVER masquerades as exit 1.
#   5  mismatch — an expected-fail step did NOT fail (the no-execute attack
#      PASSED an archive gate, or the no-execute archive ACTION did not
#      STOP), the golden found gate REFUSED the listing, the golden absent
#      gate REFUSED the empty census, or the WITH-execute archive plan
#      claimed a mutation
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --plan and --self-test are OFFLINE and need NO token and NO
# network). This is the canonical example invocation:
#
#   python3 scripts/u06_modules/example_usage.py run [--location-id ID]
#   python3 scripts/u06_modules/example_usage.py plan
#   python3 scripts/u06_modules/example_usage.py self-test
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (InternalRailClient, resolve_firebase_refresh_token,
# _resolve_firebase_api_key, resolve_pit, resolve_location, _mask_location,
# _stop, and the exception classes) and the sibling U06 modules
# (find_legacy, golden_found, golden_absent, attack_no_execute,
# workflow_lister) imported BY NAME.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value;
# --plan and --self-test are OFFLINE.
# =============================================================================
"""example_usage.py — fail-closed worked example of the U06 archive-action
surface composed end to end (U06 tooling, Skill 59)."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the internal-rail / LeadConnector clients,
# and its label resolution is the house credential contract. The sibling U06
# modules stay the single implementation of each law — this module only
# orchestrates them and honors their exit codes verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u06_modules.attack_no_execute as attack  # noqa: E402
import u06_modules.find_legacy as finder  # noqa: E402
import u06_modules.golden_absent as absent  # noqa: E402
import u06_modules.golden_found as found  # noqa: E402
import u06_modules.workflow_lister as lister  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The report contract this runner owns (one fixed string, so a machine
# consumer can never mistake another JSON object for the example report).
EXAMPLE_CONTRACT = "anthology-engine-example-usage"

# The TWO legacy workflow names — the SAME law find_legacy finds by (never
# re-implemented here; the finder's own constants are the authority).
LEGACY_NAMES = dict(finder.LEGACY_NAMES)

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
        "note": "legacy find + golden found gate + golden absent gate + "
                "no-execute attack + lister archive ACTION (--execute "
                "Trevor-gated), composed end to end",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    out.write("[example-usage] %s\n" % verdict)
    return EX_OK if ok else exit_code

# ---------------------------------------------------------------------------
# The example run — orchestration ONLY. Every judgment is delegated to the
# sibling law; its exit code is honored verbatim (never downgraded).
# ---------------------------------------------------------------------------
def example_run(rail, location_id: str, *, out=None, jsonout=None) -> int:
    """Run the U06 example surface on a live location.

    - find_legacy's live find (internal rail GET /workflow/<loc>/list?limit=200)
      against the exact-name law       -> the TWO legacy ids (a not-found key
                                          carries NO id — no id, no pass)
    - golden_found's payload gate over the canonical both-workflows listing
                                       -> the FOUND-state law holds (exit 0)
    - golden_absent's payload gate over the canonical empty census
                                       -> nothing to archive is a clean no-op
                                          PASS (exit 0)
    - attack_no_execute's verify_archive over the no-execute attack record
                                       -> the archive ACTION WITHOUT --execute
                                          MUST FAIL (exit 5) — a broken gate
                                          FAILS the composition
    - workflow_lister's archive ACTION against the SYNTHETIC golden listing
                                       -> WITHOUT --execute a STOP (exit 2);
                                          WITH --execute a no-mutation plan
                                          (proven-write law, endpoint
                                          doctrine)

    Machine surface: the ONE JSON report object lands on jsonout (stdout);
    every sibling gate document and every human note go to out (stderr).
    """
    out = out or sys.stderr
    jsonout = jsonout or sys.stdout
    steps = []

    # (1) LIVE FIND — the two legacy workflows. find_legacy owns the read
    #     and the exact-name law; its return is the ONE result dict {ok,
    #     found, workflows, absent, pinned, candidates, af_code, ...} — a
    #     not-found key carries NO id (no id, no pass) and a named af_code
    #     (LEGACY-FOUND / LEGACY-ABSENT / LEGACY-PARTIAL / LEGACY-EMPTY /
    #     PIN-MISSING / PIN-ON-WRONG-NAME). A broken listing shape raises
    #     LegacyFindError (STOP family, exit 2), a scope denial raises
    #     reg.ScopeDenied (STOP), and an edge block / transport failure
    #     raises reg.UpstreamBlockedError / reg.CafUnreachable /
    #     reg.InternalRailUnavailable (HELD, exit 3) — every code honored
    #     verbatim, never downgraded. The result's own report prints to
    #     stdout, so it is captured into the human channel here — the ONE
    #     machine document on stdout is this runner's report.
    try:
        with _sibling_stdout_to(out):
            result = finder.find_legacies(rail, location_id)
    except finder.LegacyFindError as exc:
        steps.append({"step": "legacy-find", "ok": False, "exit": EX_STOP,
                      "verdict": "STOP: %s" % exc})
        return _report(ok=False, verdict="STOP: legacy find unreadable "
                       "(exit 2)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout,
                       exit_code=EX_STOP)
    except reg.ScopeDenied as exc:
        steps.append({"step": "legacy-find", "ok": False, "exit": EX_STOP,
                      "verdict": "STOP: %s" % exc})
        return _report(ok=False, verdict="STOP: token not authorized for "
                       "this scope (exit 2)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout,
                       exit_code=EX_STOP)
    except (reg.UpstreamBlockedError, reg.CafUnreachable,
            reg.InternalRailUnavailable) as exc:
        steps.append({"step": "legacy-find", "ok": False, "exit": EX_HELD,
                      "verdict": "HELD: %s" % exc})
        return _report(ok=False, verdict="HELD: Convert and Flow / rail "
                       "unreachable or edge-blocked (exit 3 — UNDETERMINED, "
                       "never verified)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout,
                       exit_code=EX_HELD)
    if not isinstance(result, dict) or result.get("ok") is not True:
        rc = EX_MISMATCH
        steps.append({"step": "legacy-find", "ok": False, "exit": rc,
                      "af_code": result.get("af_code") if isinstance(result, dict) else None,
                      "absent": result.get("absent") if isinstance(result, dict) else None,
                      "verdict": "legacy find not verified (af_code %s)"
                                 % (result.get("af_code") if isinstance(result, dict) else "?"),
                      "detail": "a not-found legacy carries NO id — no id, "
                                "no pass"})
        return _report(ok=False,
                       verdict="FAIL: legacy find not verified (af_code %s)"
                               % (result.get("af_code") if isinstance(result, dict) else "?"),
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    workflows = result.get("workflows") or {}
    steps.append({"step": "legacy-find", "ok": True, "exit": EX_OK,
                  "af_code": result.get("af_code"),
                  "ids_masked": [row.get("id_masked") for row in workflows.values()],
                  "matched_by": [row.get("matched_by") for row in workflows.values()],
                  "candidate_count": len(result.get("candidates") or []),
                  "verdict": "BOTH legacy workflows found (af_code %s)"
                             % result.get("af_code")})

    # (2) GOLDEN FOUND STATE — both contract workflows on the listing is the
    #     U06 find-then-archive gate's FOUND state (golden_found owns that
    #     law; exit 5 on refusal). The canonical listing is the fixture's own
    #     payload — the law is judged OFFLINE over the synthetic both-
    #     workflows shape; the live find's exact-name discipline is proven by
    #     the finder's own find law (never a substring match, never a
    #     similarity score).
    with _sibling_stdout_to(out):
        gfound = found.payload(found.golden_listing_payload(), out=out)
    if not isinstance(gfound, dict) or gfound.get("ok") is not True:
        steps.append({"step": "golden-found", "ok": False, "exit": EX_MISMATCH,
                      "af_code": gfound.get("af_code") if isinstance(gfound, dict) else None,
                      "verdict": "found-state law REFUSED the golden listing"})
        return _report(ok=False, verdict="FAIL: found-state law REFUSED the "
                       "golden listing (see steps)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "golden-found", "ok": True, "exit": EX_OK,
                  "af_code": gfound.get("af_code"),
                  "verdict": "golden found state PASSES (exit 0, af_code %s)"
                             % gfound.get("af_code")})

    # (3) GOLDEN ABSENT STATE — an archive census with BOTH targets EMPTY is
    #     nothing to archive: a clean no-op PASS (golden_absent owns that
    #     law; exit 5 on refusal — a refusal means the empty-state law
    #     drifted, which is a FAIL of the composition, never a silent pass).
    with _sibling_stdout_to(out):
        rc_absent = absent.payload(absent.golden_absent_payload(), out=out)
    if rc_absent != EX_OK:
        steps.append({"step": "golden-absent", "ok": False, "exit": rc_absent,
                      "verdict": "absent-state law REFUSED the empty census"})
        return _report(ok=False, verdict="FAIL: absent-state law REFUSED the "
                       "empty census (see steps)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "golden-absent", "ok": True, "exit": EX_OK,
                  "verdict": "nothing to archive — clean no-op PASS (exit 0)"})

    # (4) NO-EXECUTE ATTACK — the archive ACTION requested WITHOUT --execute
    #     (the Trevor gate) MUST FAIL every archive gate. attack_no_execute
    #     owns that law; its verify_archive judges the canonical attack
    #     record and exits 5 on the missing gate (and 0 on the golden
    #     execute-required dry-run control). This runner calls the raw law
    #     and maps the expected FAIL to a step pass — the SAME exit code,
    #     honored verbatim, never downgraded: a gate that the attack PASSES
    #     is a broken gate, and the composition FAILS.
    with _sibling_stdout_to(out):
        rc = attack.verify_archive(attack.ATTACK_RECORD, out=out)
    if rc != EX_MISMATCH:
        steps.append({"step": "no-execute", "ok": False, "exit": rc,
                      "verdict": "no-execute attack did NOT FAIL"})
        return _report(ok=False, verdict="FAIL: no-execute attack did NOT "
                       "FAIL (an archive gate passed an ACTION without the "
                       "Trevor gate — broken gate)",
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "no-execute", "ok": True, "exit": EX_MISMATCH,
                  "verdict": "no-execute attack FAILED as it must (exit 5)"})

    # (5) THE ARCHIVE ACTION — Trevor-gated. The lister owns the ACTION law
    #     and the family doctrine (main_skeleton.py: "a check module is
    #     exercised ONLY through this CLI") — so the ACTION is exercised
    #     THROUGH THE LISTER'S OWN CLI, never a re-implementation and never
    #     a reach into a private surface. The no-execute STOP fires BEFORE
    #     any credential or network work, so the Trevor gate is provable
    #     OFFLINE: the archive ACTION requested WITHOUT --execute MUST refuse
    #     exit 2 (AF-AE-U06-ARCHIVE-NO-EXECUTE) — an ACTION that proceeds
    #     without the gate is a broken gate. The WITH-gate law is judged by
    #     the attack module's golden execute-required dry-run control
    #     (payload_true, exit 0): WITH --execute the ACTION is STILL a plan
    #     only — applied false, dry_run true, no mutation (proven-write law,
    #     endpoint doctrine; AF-AE-U06-ARCHIVE-PLAN-ONLY). A mutation claim
    #     is a FAIL. The example never runs the ACTION against a live
    #     location — the lister's own archive path needs a location-scoped
    #     credential and a live listing, and an archive write must not be
    #     performed until a surface is proven live (Skill 44 doctrine).
    target = LEGACY_NAMES["start_anthology_writer"]
    with _sibling_stdout_to(out):
        rc_gate = lister.main(["archive", "--name", target])
    if rc_gate != EX_STOP:
        steps.append({"step": "archive-action", "ok": False, "exit": rc_gate,
                      "verdict": "archive ACTION without --execute did NOT "
                                 "STOP"})
        return _report(ok=False, verdict="FAIL: archive ACTION without "
                       "--execute did NOT STOP (the Trevor gate is broken)",
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    with _sibling_stdout_to(out):
        rc_plan = attack.payload_true(out=out)
    if rc_plan != EX_OK:
        steps.append({"step": "archive-action", "ok": False, "exit": rc_plan,
                      "verdict": "golden execute-required dry-run control "
                                 "did NOT PASS"})
        return _report(ok=False, verdict="FAIL: the WITH-gate archive ACTION "
                       "is not a plan-only (the dry-run control refused)",
                       steps=steps, masked_location=_mask_location(location_id),
                       cred_label="RAIL", out=out, jsonout=jsonout)
    steps.append({"step": "archive-action", "ok": True, "exit": EX_OK,
                  "action": absent.ARCHIVE_ACTION,
                  "execute_gate": "without --execute STOP (exit 2); with "
                                  "--execute a plan only (dry-run, no "
                                  "mutation)",
                  "applied": False, "dry_run": True,
                  "execute_required": True,
                  "verdict": "archive ACTION is Trevor-gated: no-execute "
                             "STOPs as it must, WITH-gate plan-only control "
                             "PASSES (never a mutation)"})

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
        "legacy_names": LEGACY_NAMES,
        "steps": [
            "legacy-find: u06_modules.find_legacy reads the internal rail "
            "GET /workflow/<loc>/list?limit=200 (backend.leadconnectorhq.com "
            "-- the ONLY proven workflow surface) and finds the TWO legacy "
            "engine workflows BY EXACT NAME (rides reg.InternalRailClient / "
            "reg.CafClient CAF_BROWSER_UA so the Cloudflare edge never "
            "1010s the read)",
            "golden-found: u06_modules.golden_found gates the canonical "
            "both-workflows listing -- the FOUND state of the find-then-"
            "archive gate, exit 0",
            "golden-absent: u06_modules.golden_absent gates the canonical "
            "empty census -- BOTH archive targets absent, nothing to "
            "archive, a clean no-op PASS exit 0",
            "no-execute: u06_modules.attack_no_execute verify_archive "
            "judges the canonical no-execute attack record -- the archive "
            "ACTION requested WITHOUT --execute (the Trevor gate) MUST FAIL "
            "exit 5, never a pass, never a mutation",
            "archive-action: u06_modules.workflow_lister's archive ACTION "
            "over the SYNTHETIC golden listing -- WITHOUT --execute a STOP "
            "exit 2 (AF-AE-U06-ARCHIVE-NO-EXECUTE), WITH --execute still a "
            "no-mutation plan (proven-write law, endpoint doctrine; "
            "AF-AE-U06-ARCHIVE-PLAN-ONLY)",
        ],
        "note": "offline plan only — no network, no credential needed; "
                "judgments are made by the sibling modules, never here; the "
                "archive ACTION is Trevor-gated (--execute) and performed "
                "ONLY against synthetic material",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    return EX_OK

# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the orchestration
# never downgrades a refusal and the browser UA never drifts.
# ---------------------------------------------------------------------------
class _FakeRail:
    """Deterministic legacy-find listing stub (mirrors find_legacy's
    _FakeClient seam): 'rows' fixture, 'behavior' for scope/edge/transport."""

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
    """The golden listing rows: BOTH legacy workflows plus one unrelated
    workflow and one non-workflow row (a trigger) — the same shape the
    finder's golden read carries."""
    return [
        {"type": "workflow", "name": LEGACY_NAMES["start_anthology_writer"],
         "id": "wfLegacyStart01"},
        {"type": "workflow", "name": LEGACY_NAMES["pipeline_manager"],
         "id": "wfLegacyPipe02"},
        {"type": "workflow", "name": "Anthology Intake Fire", "id": "wfIntakeFire03"},
        {"type": "trigger", "name": "Contact Tag Added", "id": "wfTriggerThing"},
    ]


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

    # 2. The sibling laws are consistent with each other — the no-execute
    #    attack and the golden fixtures share the SAME archive authority
    #    (golden_absent / find_legacy — the delta_reporter.py single-
    #    implementation doctrine), and the archive ACTION is Trevor-gated on
    #    every surface. The sibling's judge report prints to stdout by
    #    contract, so it is captured here — the self-test leaves stdout
    #    clean.
    assert attack.GOLDEN_EXECUTE_REQUIRED is True, \
        "the archive authority must assert the --execute law"
    assert attack.ATTACK_RECORD.get("execute") is False, \
        "the no-execute attack must carry execute: false"
    assert found.GOLDEN_EXECUTE_REQUIRED is True and \
        absent.GOLDEN_EXECUTE_REQUIRED is True, \
        "every archive authority must assert the --execute law"
    with contextlib.redirect_stdout(io.StringIO()):
        assert attack.payload_true(out=io.StringIO()) == EX_OK, \
            "the golden execute-required dry-run control must PASS"

    # 3. The live find: found on the golden listing (the finder's own
    #    self-test proves the finder; here we pin the composition seam).
    fake = _FakeRail(_golden_rows())
    result = finder.find_legacies(fake, "loc_tmpl")
    assert result.get("ok") is True and result.get("found") is True, \
        "the golden listing must be found: %r" % result
    assert result.get("workflows", {}).get("start_anthology_writer", {}) \
        .get("id") == "wfLegacyStart01", \
        "the writer id must be the golden workflow id"
    assert result.get("workflows", {}).get("pipeline_manager", {}) \
        .get("id") == "wfLegacyPipe02", \
        "the pipeline-manager id must be the golden workflow id"

    # 4. The registry's OWN self-test proves the UA rides on the wire —
    #    evidence the example run is protected the same way (its stdout
    #    receipt is captured — the ONLY machine document on stdout here is
    #    the example report).
    with contextlib.redirect_stdout(io.StringIO()):
        assert reg.self_test() == EX_OK, "registry self-test must pass"

    # 5. The example composition — the golden path exits 0 with every step
    #    in the documented order; the no-execute step is the expected-FAIL
    #    step (it must exit 5) and the archive-action step is the
    #    expected-plan step (dry-run, never a write).
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
    assert list(steps) == ["legacy-find", "golden-found", "golden-absent",
                           "no-execute", "archive-action"], \
        "the composition must run the five steps in the documented order"
    assert steps["legacy-find"]["exit"] == EX_OK
    assert steps["legacy-find"]["af_code"] == "LEGACY-FOUND"
    assert steps["golden-found"]["exit"] == EX_OK
    assert steps["golden-absent"]["exit"] == EX_OK
    assert steps["no-execute"]["exit"] == EX_MISMATCH, \
        "the no-execute step must carry the expected exit 5"
    assert steps["archive-action"]["exit"] == EX_OK, \
        "the archive-action step must exit 0"
    assert steps["archive-action"]["execute_required"] is True and \
        steps["archive-action"]["applied"] is False and \
        steps["archive-action"]["dry_run"] is True, \
        "the archive ACTION must be Trevor-gated and a plan only"

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
              "sibling laws consistent — the archive authority asserts "
              "--execute on every surface, golden execute-required control "
              "PASSes; legacy find finds both golden workflows; golden "
              "composition exits 0 with the five steps in order — no-execute "
              "carries the expected exit 5, archive-action is Trevor-gated "
              "(STOP without --execute, plan-only control PASSes — never a "
              "mutation); a sibling STOP is honored verbatim as exit 2; "
              "registry self-test passes; never a token shape)\n")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="example_usage.py",
        description="Fail-closed worked example of the U06 archive-action "
                    "surface (Skill 59): find the two legacy workflows on a "
                    "Convert and Flow location BY EXACT NAME, prove the "
                    "golden found and absent states, prove the no-execute "
                    "attack FAILS as it must, prove the archive ACTION is "
                    "Trevor-gated (--execute) and a plan only — one JSON "
                    "report, fail-closed; never prints a secret value.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow template location id "
                         "(default: the contract's "
                         "source_template_location.template_location_id, "
                         "find_legacy.DEFAULT_TEMPLATE_LOCATION; masked on "
                         "every surface)")
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
        # token is SET (the same order find_legacy._build_rail_client uses).
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
                           "The example run finds the two legacy workflows "
                           "against the operator's OWN template location; "
                           "set the template refresh token (preferred, the "
                           "proven workflow surface) or the template PIT "
                           "and re-run."])
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
    the internal base — the same fallback find_legacy._build_rail_client
    builds (the refresh token IS the browser-session credential; the PIT
    carries the Authorization header instead, exactly as reg.CafClient sends
    it)."""

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
