#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/example_usage.py  (U07 tooling)
# EXAMPLE-USAGE RUNNER — a fail-closed WORKED EXAMPLE of the U07 FIELD-CENSUS
# surface end to end: READ the location's contact custom fields through the
# PROVEN public rail GET /locations/{locationId}/customFields
# (services.leadconnectorhq.com — the W0.5-verified surface this repo has
# PROVEN live; the exact call anthology_registry.CafClient.list_custom_fields
# makes, the same read the U02 fields_check gate and the provision path
# exercise), then run every pure sibling law over the read and the canonical
# fixtures: the field-map contract gate (u07_modules.fieldmap_loader) proves
# config/field-map.json loads against its own 38-key contract; the golden
# all-present gate (u07_modules.golden_all_present) proves ALL 38 contact
# custom fields present byte-exact by the golden keys is the all-present
# state; the missing-19 attack (u07_modules.attack_missing_14) proves the
# 19-of-38 deep strict-subset census FAILS the byte-exact field census while
# its golden 38-key control PASSES; and the type law (u07_modules.type_checker)
# proves the 36 LARGE_TEXT + TWO SINGLE_OPTIONS shape with the four named
# cover styles and the two gate actions byte-exact in order — then emit ONE
# JSON report on stdout. It
# demonstrates BY EXAMPLE how the U07 modules COMPOSE on a real location.
#
# WHAT THIS MODULE IS NOT: it is NOT a gate, NOT a checker, and NOT a manifest
# row (docs_u07.py records its inventory without an example-usage row — a doc
# that claims a manifest row that does not exist is drift; the same posture
# the u05 / u06 example-usage siblings keep). It makes NO judgment of its own
# about any law — every judgment is delegated to the sibling modules, which
# stay the single implementation of each law (fieldmap_loader owns the
# field-map load-and-verify law, golden_all_present owns the ALL-PRESENT
# state, attack_missing_14 owns the ATTACK boundary and its control,
# live_fields_reader owns the LIVE READ, missing_finder owns the presence
# law and the Trevor-gated CREATE ACTION, type_checker owns the type law and
# the Trevor-gated create-only-missing provision). This module only
# ORCHESTRATES those laws in the documented order and reports the outcome —
# the runnable companion to the USAGE blocks in the sibling headers. A NEW
# judgment defined here would create a SECOND implementation of a law, so
# there is deliberately none.
#
# FAIL-CLOSED BY CONSTRUCTION: every step either passes through the sibling
# law (its exit code is honored verbatim — a STOP refusal is NEVER downgraded
# to a pass) or is SKIPPED with the reason surfaced. If the live surface
# cannot be certified (unreachable / edge-blocked), the report says HELD
# (UNDETERMINED) — never "verified". The attack step is an EXPECTED-FAIL
# step: the 19-of-38 attack MUST FAIL the byte-exact census (exit 5) — an
# attack that PASSES any field gate is a broken gate, and the composition
# FAILS rather than report success. The golden all-present gate is an
# EXPECTED-PASS step: a fully provisioned census is the all-present state
# (exit 0) — a refusal is a FAIL of the composition. The create gate is an
# EXPECTED-STOP step: a CREATE ACTION requested WITHOUT --execute MUST refuse
# exit 2 (the Trevor gate) — a no-execute ACTION that proceeds is a broken
# gate. The type-law step is judged over the canonical 38-key golden
# listing: it must PASS exit 0 (a wrong-type live field is a MISMATCH,
# exit 5, never a silent pass). The example performs NO CREATE ACTION on a
# live location at all: creation is proven OFFLINE by the family's own gate
# controls (missing_finder / type_checker STOPS without --execute — the
# verbatim AF-AE-U07-CREATE-NO-EXECUTE family), never exercised against a
# live location.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The live read rides the client's
# OWN location-scoped private-integration token, resolved via
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env
# first, then the three canonical client env stores, with the pit- prefix
# validated so a placeholder is refused), and the location id resolved the
# same way (CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID /
# GHL_LOCATION_ID), overridable with --location-id. Every credential is
# reported as LABEL + SET / NOT-SET only — a value is NEVER printed, echoed,
# or logged. The location id and every field id are MASKED on operator
# surfaces (last 4 chars, non-reversible); full ids ride inside request URLs
# only.
#
# BROWSER UA: the live read rides reg.CafClient, whose every request carries
# CAF_BROWSER_UA — the Cloudflare edge fronting services.leadconnectorhq.com
# 403s urllib's default "Python-urllib/x.y" User-Agent at the WAF edge (CF
# error 1010) before the request ever reaches Convert and Flow (GK-09; the
# proven-live Podcast gate string, ported byte-for-byte in
# anthology_registry.py). Scope-vs-edge-block discrimination is the
# registry's own: a bare 401/403 whose body does NOT match the genuine
# scope-denial signature raises UpstreamBlockedError -> HELD, never a scope
# STOP. The offline self-test PROVES the request carries the browser UA by
# asserting reg.CAF_BROWSER_UA byte-for-byte against the Podcast gate's
# proven-live string — the same pin the registry's own self-test enforces —
# so a drift in the wiring is caught OFFLINE, never first seen as a 1010.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  all steps PASSED — field-map contract gate PASSES, live custom-field
#      read succeeded, golden all-present gate PASSES, missing-19 attack
#      FAILS (as it must), golden 38-key control PASSES, type law PASSES,
#      no-execute CREATE ACTION STOPs (as it must); also --plan and
#      --self-test pass
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — a Convert and Flow private-integration token or
#      location id NOT SET, or a sibling law STOPPED (a FieldMapError in the
#      loader, a MissingFinderError / TypeCheckError / StyleImportError in
#      the law modules, the no-execute CREATE ACTION, a genuine scope
#      denial) — honored verbatim, never downgraded
#   3  Convert and Flow unreachable or upstream edge block (HELD; retryable
#      — the outcome is UNDETERMINED, never proven verified)
#   4  enforced violation — an OFFLINE self-test assertion tripped
#      (AF-AE-EXAMPLE-USAGE-* family). A tamper NEVER masquerades as exit 1.
#   5  mismatch — an expected-fail step did NOT fail (the missing-19 attack
#      PASSED a field gate), the golden all-present gate REFUSED the census,
#      the golden 38-key control REFUSED, the type law FAILED a golden
#      listing, or the no-execute CREATE ACTION did not STOP
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --plan and --self-test are OFFLINE and need NO token and NO
# network). This is the canonical example invocation:
#
#   python3 scripts/u07_modules/example_usage.py run [--location-id ID]
#   python3 scripts/u07_modules/example_usage.py plan
#   python3 scripts/u07_modules/example_usage.py self-test
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, resolve_pit, resolve_location,
# _mask_location, _stop, and the exception classes) and the sibling U07
# modules (fieldmap_loader, live_fields_reader, golden_all_present,
# attack_missing_14, missing_finder, type_checker) imported BY NAME.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value;
# --plan and --self-test are OFFLINE.
# =============================================================================
"""example_usage.py — fail-closed worked example of the U07 field-census
surface composed end to end (U07 tooling, Skill 59)."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the LeadConnector client, and its label
# resolution is the house credential contract. The sibling U07 modules stay
# the single implementation of each law — this module only orchestrates
# them and honors their exit codes verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u07_modules.attack_missing_14 as attack  # noqa: E402
import u07_modules.fieldmap_loader as loader  # noqa: E402
import u07_modules.golden_all_present as golden  # noqa: E402
import u07_modules.live_fields_reader as reader  # noqa: E402
import u07_modules.missing_finder as finder  # noqa: E402
import u07_modules.type_checker as checker  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "field-map.json"

# The report contract this runner owns (one fixed string, so a machine
# consumer can never mistake another JSON object for the example report).
EXAMPLE_CONTRACT = "anthology-engine-example-usage"

# The field-census authority this example demonstrates — the 38-key
# contract total, read ONCE from the field-map's own law (never a
# hardcoded list; the sibling loaders stay the single implementation).
CONTRACT_TOTAL = loader.CONTRACT_TOTAL


def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)


# ---------------------------------------------------------------------------
# Report builder — ONE JSON object on stdout (jsonout); human notes go to
# out (stderr) only. Secret VALUES never appear: the credential is
# reported by LABEL + SET/NOT-SET and the location id as a masked marker.
# The exit code is THREADED THROUGH: a STOP (2) or HELD (3) never
# masquerades as a mismatch (5) — the sibling's code is honored verbatim.
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
        "note": "field-map contract gate + live custom-field read + golden "
                "all-present gate + missing-14 attack + type law + "
                "no-execute create gate, composed end to end",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    out.write("[example-usage] %s\n" % verdict)
    return EX_OK if ok else exit_code


# ---------------------------------------------------------------------------
# The example run — orchestration ONLY. Every judgment is delegated to the
# sibling law; its exit code is honored verbatim (never downgraded).
# ---------------------------------------------------------------------------
def example_run(location_id: str, *, out=None, jsonout=None,
                environ=None, live_read=None) -> int:
    """Run the U07 example surface on a live location.

    - fieldmap_loader's contract gate over config/field-map.json (the
      SINGLE SOURCE OF TRUTH)       -> the 38-key load law holds (exit 0)
    - live_fields_reader's LIVE READ (the PROVEN public rail
      GET /locations/{id}/customFields) -> the location's fields, read by
      the client's OWN pit- token BY LABEL (an EMPTY field set is a
      truthful PASS; a missing credential is a STOP; an unreachable rail /
      edge block / malformed listing is HELD — never a fabricated list)
    - golden_all_present's payload gate over the canonical all-38 listing
                                      -> the ALL-PRESENT state holds (exit 0)
    - attack_missing_14's FAIL over the canonical 19-of-38 attack
                                      -> the deep strict-subset census MUST
                                         FAIL (exit 5) — a broken gate FAILS
                                         the composition
    - attack_missing_14's golden 38-key control
                                      -> the true census PASSES (exit 0) —
                                         the pass/fail split discriminates
                                         the boundary, never a broken gate
    - type_checker's type law over the canonical 38-key golden listing
                                      -> 36 LARGE_TEXT + the TWO
                                         SINGLE_OPTIONS picklist fields
                                         (cover choice with the four named
                                         styles, review decision with the
                                         two gate actions) byte-exact in
                                         order (exit 0)
    - the no-execute CREATE ACTION gate (the family's OWN surfaces)
                                      -> missing_finder's run_check and
                                         type_checker's verify_live each
                                         STOP exit 2 WITHOUT --execute over
                                         the canonical 19-of-38 attack
                                         census (the Trevor gate;
                                         AF-AE-U07-CREATE-NO-EXECUTE) —
                                         creation is never silent; with
                                         --execute it is
                                         create-only-missing with a
                                         byte-exact read-back

    Machine surface: the ONE JSON report object lands on jsonout (stdout);
    every sibling gate document and every human note go to out (stderr).
    `environ` is the live-read credential injection point (an explicit env
    dict blocks the canonical-store fallback, so the STOP credential gate
    is deterministic OFFLINE — the same seam live_fields_reader exposes).
    `live_read` is the read seam for the OFFLINE self-test only: the same
    shape as live_fields_reader.live_list_command (the u05 / u06 siblings'
    _FakeRail pattern), so the golden composition is pinned against a
    deterministic SUCCESS read without a credential and without the
    network; the production caller never passes it and the reader's OWN
    credential / STOP / HELD paths are exercised verbatim.
    """
    out = out or sys.stderr
    jsonout = jsonout or sys.stdout
    steps = []

    # (1) FIELD-MAP CONTRACT GATE — config/field-map.json is the SINGLE
    #     SOURCE OF TRUTH; fieldmap_loader owns the load-and-verify law
    #     (38-key count, total_keys byte-match, derivation law, type law,
    #     key law) and raises FieldMapError (STOP family, exit 2) on any
    #     drift — never a partial load. OFFLINE: no network, no credential.
    try:
        with _sibling_stdout_to(out):
            rc_load = loader.load_command(CONTRACT_PATH, out=io.StringIO())
    except loader.FieldMapError as exc:
        steps.append({"step": "field-map", "ok": False, "exit": EX_STOP,
                      "verdict": "STOP: %s" % exc})
        return _report(ok=False, verdict="STOP: the field-map contract gate "
                       "refused (exit 2)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout,
                       exit_code=EX_STOP)
    if rc_load != EX_OK:
        steps.append({"step": "field-map", "ok": False, "exit": rc_load,
                      "verdict": "the field-map contract gate returned "
                                 "exit %d" % rc_load})
        return _report(ok=False, verdict="FAIL: the field-map contract gate "
                       "refused (exit %d)" % rc_load, steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout)
    steps.append({"step": "field-map", "ok": True, "exit": EX_OK,
                  "contract_total": CONTRACT_TOTAL,
                  "verdict": "field-map.json loaded and verified against "
                             "its own %d-key contract (the load law holds)"
                             % CONTRACT_TOTAL})

    # (2) LIVE READ — the ONE PIT-gated live read. live_fields_reader owns
    #     the read surface: the location's contact custom fields through
    #     the PROVEN public rail, resolved BY LABEL (SET / NOT SET only,
    #     value never printed). The reader's return code is honored
    #     VERBATIM: EX_OK (including an EMPTY field set — a truthful
    #     answer), EX_STOP (a missing credential — the gate fires BEFORE
    #     any network), EX_HELD (an unreachable rail / Cloudflare edge
    #     block / malformed listing — UNDETERMINED, never a fabricated
    #     list). The report the reader prints to stdout is captured into
    #     the human channel — the ONE machine document on stdout is this
    #     runner's report.
    _read = live_read if live_read is not None else reader
    rc_read = _read.live_list_command(location_id, out=out,
                                      jsonout=None, environ=environ)
    if rc_read == EX_STOP:
        steps.append({"step": "live-read", "ok": False, "exit": EX_STOP,
                      "verdict": "STOP: no Convert and Flow credential SET "
                                 "by label (exit 2)"})
        return _report(ok=False, verdict="STOP: the live custom-field read "
                       "refused (exit 2 — credential NOT SET by label)",
                       steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout,
                       exit_code=EX_STOP)
    if rc_read == EX_HELD:
        steps.append({"step": "live-read", "ok": False, "exit": EX_HELD,
                      "verdict": "HELD: rail unreachable / edge-blocked / "
                                 "malformed listing (exit 3 — "
                                 "UNDETERMINED, never verified)"})
        return _report(ok=False, verdict="HELD: Convert and Flow "
                       "unreachable or edge-blocked (exit 3 — "
                       "UNDETERMINED, never verified)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout,
                       exit_code=EX_HELD)
    if rc_read != EX_OK:
        steps.append({"step": "live-read", "ok": False, "exit": rc_read,
                      "verdict": "the live custom-field read returned "
                                 "exit %d" % rc_read})
        return _report(ok=False, verdict="FAIL: the live custom-field read "
                       "returned exit %d" % rc_read, steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout)
    steps.append({"step": "live-read", "ok": True, "exit": EX_OK,
                  "verdict": "live customFields read succeeded through the "
                             "proven public rail (an EMPTY field set is a "
                             "truthful PASS)"})

    # (3) GOLDEN ALL-PRESENT GATE — ALL 38 contract fields on the listing
    #     byte-exact by the golden keys is the U07 all-present state
    #     (golden_all_present owns that law; exit 5 on refusal). The
    #     canonical listing is the fixture's own payload — the law is
    #     judged OFFLINE over the synthetic all-38 shape; the live read's
    #     byte-exact discipline is proven by the reader's own listing.
    with _sibling_stdout_to(out):
        gold = golden.payload(golden.golden_fields_payload(), out=out)
    if not isinstance(gold, dict) or gold.get("ok") is not True:
        steps.append({"step": "golden-all-present", "ok": False,
                      "exit": EX_MISMATCH,
                      "af_code": gold.get("af_code") if isinstance(gold, dict) else None,
                      "verdict": "all-present law REFUSED the golden census"})
        return _report(ok=False, verdict="FAIL: all-present law REFUSED the "
                       "golden census (see steps)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout)
    steps.append({"step": "golden-all-present", "ok": True, "exit": EX_OK,
                  "count": gold.get("count"),
                  "af_code": gold.get("af_code"),
                  "verdict": "golden all-present state PASSES (exit 0, "
                             "af_code %s)" % gold.get("af_code")})

    # (4) MISSING-19 ATTACK — the 19-of-38 deep strict-subset census MUST
    #     FAIL the byte-exact field census (exit 5). attack_missing_14 owns
    #     that law; its verify_live judges the canonical attack fixture.
    #     This runner calls the raw law and maps the expected FAIL to a
    #     step pass — the SAME exit code, honored verbatim, never
    #     downgraded: a gate that the attack PASSES is a broken gate, and
    #     the composition FAILS. The missing keys ride the report by
    #     MASKED MARKER only — never a full contract key surface.
    with _sibling_stdout_to(out):
        rc_attack = attack.verify_live(None, location_id,
                                       reg.load_field_map(CONTRACT_PATH),
                                       out=out)
    if rc_attack != EX_MISMATCH:
        steps.append({"step": "missing-14", "ok": False, "exit": rc_attack,
                      "verdict": "missing-14 attack did NOT FAIL"})
        return _report(ok=False, verdict="FAIL: missing-14 attack did NOT "
                       "FAIL (a field gate passed the deep strict-subset "
                       "census — broken gate)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout)
    steps.append({"step": "missing-14", "ok": True, "exit": EX_MISMATCH,
                  "missing_count": attack.MISSING_COUNT,
                  "verdict": "missing-14 attack FAILED as it must (exit 5, "
                             "%d of %d contract fields missing — by masked "
                             "marker only)"
                             % (attack.MISSING_COUNT, CONTRACT_TOTAL)})

    # (5) GOLDEN 38-KEY CONTROL — the negative-result contract: the true
    #     all-38 census must PASS exit 0, so a field gate that FAILS
    #     EVERYTHING (a broken instrument) is never mistaken for a real
    #     19/38 discrimination (attack_missing_14's payload_true owns the
    #     control — the SAME judge, the SAME law).
    with _sibling_stdout_to(out):
        rc_true = attack.payload_true(out=out)
    if rc_true != EX_OK:
        steps.append({"step": "golden-control", "ok": False, "exit": rc_true,
                      "verdict": "golden 38-key control did NOT PASS"})
        return _report(ok=False, verdict="FAIL: the golden 38-key control "
                       "refused (a gate that fails everything is a broken "
                       "instrument — the pass/fail split discriminates the "
                       "boundary, never a broken gate)",
                       steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout)
    steps.append({"step": "golden-control", "ok": True, "exit": EX_OK,
                  "verdict": "golden 38-key control PASSES (exit 0 — the "
                             "pass/fail split discriminates the boundary)"})

    # (6) TYPE LAW — every free-text field live LARGE_TEXT (the 36-key
    #     multi-line law) and the TWO SINGLE_OPTIONS picklist fields live
    #     with their own exact picklists byte-exact in order (type_checker
    #     owns that law: the cover choice with the four named styles, the
    #     review decision with the two gate actions). The canonical all-38
    #     golden listing is the fixture's own payload — the law is judged
    #     OFFLINE over the golden shape; the live read's type discipline is
    #     proven by the checker's own verify surface. A wrong-type live
    #     field is a MISMATCH (exit 5), never a silent pass.
    with _sibling_stdout_to(out):
        types = checker.check_types_live(
            _GoldenCaf(), location_id, reg.load_field_map(CONTRACT_PATH),
            execute=False)
    if not isinstance(types, dict) or types.get("ok") is not True:
        steps.append({"step": "type-law", "ok": False, "exit": EX_MISMATCH,
                      "verdict": "type law REFUSED the golden census%s"
                                 % ((": %s" % types.get("detail"))
                                    if isinstance(types, dict) else "")})
        return _report(ok=False, verdict="FAIL: the type law REFUSED the "
                       "golden census (see steps)", steps=steps,
                       masked_location=_mask_location(location_id),
                       cred_label="PIT", out=out, jsonout=jsonout)
    steps.append({"step": "type-law", "ok": True, "exit": EX_OK,
                  "text_keys": types.get("text_keys"),
                  "choice_key": types.get("choice_key"),
                  "choice_options": types.get("choice_options"),
                  "decision_key": types.get("decision_key"),
                  "verdict": "type law PASSES (exit 0 — %d LARGE_TEXT keys + "
                             "the TWO SINGLE_OPTIONS picklists with their "
                             "own exact options byte-exact in order)"
                             % types.get("text_keys")})

    # (7) THE CREATE GATE — Trevor-gated, proven on the family's OWN
    #     surfaces (main_skeleton.py: "a check module is exercised ONLY
    #     through this CLI"). A CREATE ACTION requested WITHOUT --execute
    #     MUST refuse exit 2 on every create-capable surface — the
    #     verbatim AF-AE-U07-CREATE-NO-EXECUTE family: creation is never
    #     silent. The gate is judged over the canonical 19-of-38 attack
    #     census (attack_missing_14's OWN deep-frozen fixture — the deep
    #     strict subset of the field LAW), so the no-execute STOPs are
    #     provable OFFLINE: the family's raw gate surfaces
    #     (missing_finder.run_check / type_checker.verify_live) never
    #     resolve a credential and never touch the network — the refusal
    #     fires before any write. The example NEVER runs a CREATE ACTION
    #     against a live location: with --execute creation is
    #     create-only-missing with a byte-exact read-back, and the live
    #     path must not be performed until a surface is proven live (Skill
    #     44 endpoint doctrine). A no-execute ACTION that proceeds is a
    #     broken gate, and the composition FAILS.
    field_map = reg.load_field_map(CONTRACT_PATH)
    for _probe in (("missing_finder", "run_check"),
                   ("type_checker", "verify_live")):
        _name, _surface = _probe
        with _sibling_stdout_to(out):
            if _surface == "run_check":
                rc_gate = finder.run_check(_AttackCaf(), location_id,
                                           field_map, execute=False, out=out)
            else:
                rc_gate = checker.verify_live(_AttackCaf(), location_id,
                                              field_map, execute=False,
                                              out=out)
        if rc_gate != EX_STOP:
            steps.append({"step": "create-gate", "ok": False, "exit": rc_gate,
                          "surface": "%s %s" % (_name, _surface),
                          "verdict": "a CREATE ACTION without --execute did "
                                     "NOT STOP on %s %s"
                                     % (_name, _surface)})
            return _report(ok=False, verdict="FAIL: a CREATE ACTION without "
                           "--execute did NOT STOP (the Trevor gate is "
                           "broken)", steps=steps,
                           masked_location=_mask_location(location_id),
                           cred_label="PIT", out=out, jsonout=jsonout)
    steps.append({"step": "create-gate", "ok": True, "exit": EX_OK,
                  "af_code": "AF-AE-U07-CREATE-NO-EXECUTE",
                  "surfaces": ["missing_finder run_check",
                               "type_checker verify_live"],
                  "execute_gate": "without --execute STOP (exit 2) on every "
                                  "create-capable surface (judged over the "
                                  "canonical 19-of-38 attack census); with "
                                  "--execute create-only-missing with a "
                                  "byte-exact read-back — never a silent "
                                  "write",
                  "applied": False,
                  "verdict": "the CREATE ACTION is Trevor-gated: the "
                             "no-execute STOPs fire as they must (never a "
                             "mutation)"})

    return _report(ok=True, verdict="VERIFIED", steps=steps,
                   masked_location=_mask_location(location_id),
                   cred_label="PIT", out=out, jsonout=jsonout)


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
# Golden read surface for the OFFLINE type-law step — the canonical all-38
# listing, derived from the field-map (the single source of truth; never a
# hardcoded list) and served through the SAME list_custom_fields seam the
# checker's own _FakeCaf implements. READ-ONLY: it only lists; the checker
# owns every judgment.
# ---------------------------------------------------------------------------
class _AttackCaf:
    """In-memory Convert and Flow read surface for the create-gate probes:
    list_custom_fields returns the canonical 19-of-38 attack census (the
    deep strict subset of the field LAW) — the read surface on which every
    create-capable family law MUST refuse without --execute. No create
    surface exists here — the example never performs a CREATE ACTION, and
    the gate is proven by the family's OWN no-execute STOPs."""

    def list_custom_fields(self, location_id):
        del location_id  # the attack surface never routes to a live location
        return [dict(f) for f in attack.ATTACK_FIELDS]


class _GoldenCaf:
    """In-memory Convert and Flow read surface: list_custom_fields returns
    the canonical all-38 golden listing (every intended key byte-exact by
    its derived fieldKey, each at its declared data_type, the TWO
    SINGLE_OPTIONS choice fields carrying the four named cover styles and
    the two gate-engine decision actions in order). No create surface exists here — the example never performs a
    CREATE ACTION, and the create gate is proven on the family's OWN
    surfaces instead."""

    def list_custom_fields(self, location_id):
        del location_id  # the golden surface never routes to a live location
        field_map = reg.load_field_map(CONTRACT_PATH)
        inventory = (field_map.get("provisioning") or {}).get("fields") or []
        rows = []
        for i, item in enumerate(inventory):
            intended = item.get("intended_key")
            if not intended:
                continue
            row = {
                "fieldKey": intended,
                "name": item.get("create_name") or reg.create_name_of(intended),
                "dataType": item.get("data_type", "LARGE_TEXT"),
                "id": "fld_golden_%03d" % i,
            }
            if (item.get("data_type") or "") == "SINGLE_OPTIONS":
                row["options"] = list(item.get("options") or ())
            rows.append(row)
        return rows


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
        "contract_total": CONTRACT_TOTAL,
        "steps": [
            "field-map: u07_modules.fieldmap_loader loads and verifies "
            "config/field-map.json (the SINGLE SOURCE OF TRUTH) against "
            "its own 38-key contract -- the load law, exit 0; a map that "
            "drifted is a STOP (exit 2, never a partial load)",
            "live-read: u07_modules.live_fields_reader reads the location's "
            "contact custom fields through the PROVEN public rail "
            "GET /locations/{id}/customFields (services.leadconnectorhq.com "
            "-- rides reg.CafClient CAF_BROWSER_UA so the Cloudflare edge "
            "never 1010s the read; PIT BY LABEL, never printed; an EMPTY "
            "field set is a truthful PASS, an unreachable rail / edge "
            "block / malformed listing is HELD exit 3, never a fabricated "
            "list)",
            "golden-all-present: u07_modules.golden_all_present gates the "
            "canonical all-38 listing -- ALL 38 contract fields present "
            "byte-exact by the golden keys, the all-present state, exit 0",
            "missing-14: u07_modules.attack_missing_14 verify_live judges "
            "the canonical 19-of-38 deep strict-subset census -- MUST FAIL "
            "exit 5 (a field gate that passes the attack is a broken gate)",
            "golden-control: u07_modules.attack_missing_14 payload_true "
            "judges the true 38-key golden census -- MUST PASS exit 0 (the "
            "pass/fail split discriminates the boundary, never a broken "
            "instrument)",
            "type-law: u07_modules.type_checker check_types_live judges the "
            "canonical all-38 golden listing -- 36 LARGE_TEXT keys + the "
            "TWO SINGLE_OPTIONS choice fields with the four named cover "
            "styles and the two gate-engine decision actions byte-exact in "
            "order, exit 0",
            "create-gate: the family's OWN create-capable gate surfaces "
            "(missing_finder run_check / type_checker verify_live) judged "
            "over the canonical 19-of-38 attack census -- each MUST STOP "
            "exit 2 WITHOUT --execute (AF-AE-U07-CREATE-NO-EXECUTE, the "
            "Trevor gate); creation is never silent and never performed "
            "against a live location here",
        ],
        "note": "offline plan only — no network, no credential needed; "
                "judgments are made by the sibling modules, never here; "
                "the live read is the ONE PIT-gated surface and creation "
                "is Trevor-gated (--execute), performed ONLY against "
                "synthetic material",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the orchestration
# never downgrades a refusal and the browser UA never drifts.
# ---------------------------------------------------------------------------
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

    # 2. The sibling laws are consistent with each other — the missing-14
    #    attack and the golden fixtures share the SAME field authority
    #    (the field-map; the delta_reporter.py single-implementation
    #    doctrine), and the CREATE ACTION is Trevor-gated on every
    #    create-capable surface. The sibling's judge report prints to
    #    stdout by contract, so it is captured here — the self-test leaves
    #    stdout clean.
    assert golden.GOLDEN_EXECUTE_REQUIRED is True, \
        "the all-present authority must assert the --execute law"
    assert attack.CONTRACT_TOTAL == golden.CONTRACT_TOTAL == CONTRACT_TOTAL, \
        "the golden and the attack must share the SAME 38-key contract"
    with contextlib.redirect_stdout(io.StringIO()):
        assert attack.payload_true(out=io.StringIO()) == EX_OK, \
            "the golden 38-key control must PASS"

    # 3. The field-map contract gate: the committed config load passes
    #    (the loader's own self-test proves the loader; here we pin the
    #    composition seam), and the golden all-present gate accepts the
    #    golden census (a refusal means the all-present state law drifted,
    #    which is a FAIL of the composition, never a silent pass).
    with contextlib.redirect_stdout(io.StringIO()):
        assert loader.load_command(CONTRACT_PATH,
                                   out=io.StringIO()) == EX_OK, \
            "the field-map contract gate must pass over the committed map"
        gold = golden.payload(golden.golden_fields_payload(),
                              out=io.StringIO())
    assert isinstance(gold, dict) and gold.get("ok") is True, \
        "the golden all-present gate must accept the golden census: %r" % gold

    # 4. The registry's OWN self-test proves the UA rides on the wire —
    #    evidence the example run is protected the same way (its stdout
    #    receipt is captured — the ONLY machine document on stdout here is
    #    the example report).
    with contextlib.redirect_stdout(io.StringIO()):
        assert reg.self_test() == EX_OK, "registry self-test must pass"

    # 5. The example composition — the golden path exits 0 with every step
    #    in the documented order; the missing-14 step is the expected-FAIL
    #    step (it must exit 5) and the create-gate step is the
    #    expected-STOP step (the family's own no-execute refusals, exit 2,
    #    honored verbatim). The golden path needs the live read to succeed,
    #    which requires a credential AND the network — neither may be
    #    depended on OFFLINE, so the read is stubbed exactly as the u05 /
    #    u06 example siblings stub their live surface (_FakeRail): the
    #    runner receives the seam, and the composition is pinned against a
    #    deterministic SUCCESS read. The reader's OWN credential / STOP /
    #    HELD paths are proven by the reader's self-test and by the
    #    empty-environ run below.
    class _FakeReader:
        def live_list_command(self, location_id, *, out=None, jsonout=None,
                              environ=None):
            out.write("[live-fields-reader] LIVE customFields (marker "
                      "...tmpl): golden read stub\n")
            return EX_OK

    report_buf = io.StringIO()
    rc = example_run("loc_tmpl", out=io.StringIO(),
                     jsonout=report_buf, environ={},
                     live_read=_FakeReader())
    assert rc == EX_OK, "the golden composition must exit 0, got %s" % rc
    report = json.loads(report_buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "VERIFIED"
    assert report["contract"] == EXAMPLE_CONTRACT
    assert report["location_masked"] == "...tmpl", \
        "the location must be masked to the last-4 marker"
    steps = {s["step"]: s for s in report["steps"]}
    assert list(steps) == ["field-map", "live-read", "golden-all-present",
                           "missing-14", "golden-control", "type-law",
                           "create-gate"], \
        "the composition must run the seven steps in the documented order"
    assert steps["field-map"]["exit"] == EX_OK
    assert steps["live-read"]["exit"] == EX_OK
    assert steps["golden-all-present"]["exit"] == EX_OK
    assert steps["golden-all-present"]["af_code"] == "FIELDS-ALL-PRESENT"
    assert steps["missing-14"]["exit"] == EX_MISMATCH, \
        "the missing-14 step must carry the expected exit 5"
    assert steps["missing-14"]["missing_count"] == 19
    assert steps["golden-control"]["exit"] == EX_OK
    assert steps["type-law"]["exit"] == EX_OK
    assert steps["type-law"]["text_keys"] == 36, \
        "the type law must count 36 LARGE_TEXT keys"
    assert steps["create-gate"]["exit"] == EX_OK, \
        "the create-gate step must exit 0"
    assert steps["create-gate"]["af_code"] == "AF-AE-U07-CREATE-NO-EXECUTE"
    assert steps["create-gate"]["applied"] is False, \
        "the create-gate step must never claim a mutation"

    # 6. The empty-environ run — an explicit EMPTY environ makes the
    #    live-read credential gate deterministic OFFLINE: the read STOPS
    #    before any network (exit 2, never a fabricated list). The STOP
    #    path is exercised here, the live-network happy path is not
    #    (self-tests never depend on live state).
    report_buf2 = io.StringIO()
    rc = example_run("loc_tmpl", out=io.StringIO(),
                     jsonout=report_buf2, environ={})
    assert rc == EX_STOP, \
        "the empty-environ run must STOP (exit 2 — no credential SET by " \
        "label), got %s" % rc
    assert "VERIFIED" not in report_buf2.getvalue(), \
        "the empty-environ run must never report VERIFIED"

    # 7. Never-print: no credential-shaped string on any surface.
    blob = report_buf.getvalue() + report_buf2.getvalue()
    for token in ("pit-", "Bearer ", "sk-", "eyJ"):
        assert token not in blob, \
            "surface leak: %r must never appear" % token

    dev.write("example_usage self-test: OK (browser UA pinned byte-exact; "
              "sibling laws consistent — the golden and the attack share "
              "the same 38-key contract, golden 38-key control PASSes; the "
              "field-map contract gate passes over the committed map and "
              "the golden all-present gate accepts the golden census; "
              "registry self-test passes; the golden composition exits 0 "
              "with the seven steps in order — missing-14 carries the "
              "expected exit 5, type-law counts 36 LARGE_TEXT keys, "
              "create-gate carries AF-AE-U07-CREATE-NO-EXECUTE and never "
              "claims a mutation; the empty-environ run STOPS before any "
              "network — the credential gate is deterministic OFFLINE and "
              "never reports VERIFIED; never a token shape)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="example_usage.py",
        description="Fail-closed worked example of the U07 field-census "
                    "surface (Skill 59): read the location's contact custom "
                    "fields through the proven public rail, prove the "
                    "field-map contract, the golden all-present state, the "
                    "missing-14 attack FAILS as it must, its golden 38-key "
                    "control, the type law, and the Trevor-gated CREATE "
                    "ACTION gate — one JSON report, fail-closed; never "
                    "prints a secret value.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id "
                         "(default: the CLIENT-standard location labels "
                         "CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID; "
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
        # Credential BY LABEL, NEVER BY VALUE. The live read rides the
        # client's OWN location-scoped private-integration token, resolved
        # by live_fields_reader's own label machinery (SET / NOT SET only
        # on every operator surface); the credential gate STOPS before any
        # network when no token is SET.
        loc_label, loc = reg.resolve_location(args.location_id)
        if not loc:
            reg._stop(sys.stderr, "No Convert and Flow Location id is SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.LOCATION_LABELS),
                       "Set the client's OWN location id and re-run."])
            return EX_STOP
        sys.stderr.write("[example-usage] location via %s (marker %s).\n"
                         % (loc_label, reg._mask_location(loc)))
        return example_run(loc, out=sys.stderr, jsonout=sys.stdout)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[example-usage] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
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


if __name__ == "__main__":
    sys.exit(main())
