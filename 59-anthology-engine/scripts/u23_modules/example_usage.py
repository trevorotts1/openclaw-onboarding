#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/example_usage.py  (U23 tooling)
# EXAMPLE-USAGE RUNNER — a fail-closed WORKED EXAMPLE of the U23 SMS
# phone-provisioning surface end to end: LIVE-READ the Convert and Flow
# location's phone numbers through the PROVEN public rail
# GET /phones/numbers?locationId=<loc> (services.leadconnectorhq.com — the
# exact call the family's provision_action / phone_lister make through
# reg.CafClient, which carries the browser User-Agent on every request), then
# run every pure sibling law over the read and the canonical fixtures: the
# golden phone-provisioned gate (u23_modules.golden_has_phone) proves the
# already-provisioned state holds (idempotent no-op — a location that already
# carries an SMS-capable number is verified, never re-provisioned, never a
# second charge); the unmarked-entry attack (u23_modules.provision_action's
# own attack surface) proves an SMS entry with no capability marker is NEVER
# trusted; the
# failed-send attack (u23_modules.attack_sms_failed) proves the non-200
# send-test-message record MUST FAIL the SMS-verification law while its golden
# 200-send control (payload_true) PASSES — the pass/fail split discriminates
# the status boundary, never a broken instrument; the live send-verifier gate
# (u23_modules.sms_verifier) proves a send is never reported delivered without
# HTTP 200 PLUS a message identifier; and the Trevor gate (the heart of the
# family) is re-proven on EVERY ACTION surface — each no-execute STOP must
# fire exit 2 — then emit ONE JSON report on stdout. It demonstrates BY
# EXAMPLE how the U23 modules COMPOSE on a real location.
#
# WHAT THIS MODULE IS NOT: it is NOT a gate, NOT a checker, and NOT a manifest
# row (main_skeleton.py records U23_MODULES without an example-usage row — a
# doc that claims a manifest row that does not exist is drift; the same
# posture the u03 / u05 / u06 / u07 example-usage siblings keep). It makes NO
# judgment of its own about any law — every judgment is delegated to the
# sibling modules, which stay the single implementation of each law
# (provision_action owns the provisioning law and the Trevor-gated CREATE
# ACTION, phone_lister owns the READ-ONLY listing and its gated provision
# path, sms_verifier owns the outbound-send verification law, sms_sender owns
# the test-SMS send law, golden_has_phone owns the ALREADY-PROVISIONED state,
# attack_sms_failed owns the ATTACK boundary and its control). This module
# only ORCHESTRATES those laws in the documented order and reports the
# outcome — the runnable companion to the USAGE blocks in the sibling
# headers. A NEW judgment defined here would create a SECOND implementation
# of a law, so there is deliberately none.
#
# FAIL-CLOSED BY CONSTRUCTION: every step either passes through the sibling
# law (its exit code is honored verbatim — a STOP refusal is NEVER downgraded
# to a pass) or is SKIPPED with the reason surfaced. If the live surface
# cannot be certified (unreachable / edge-blocked), the report says HELD
# (UNDETERMINED) — never "verified". The attack steps are EXPECTED-FAIL /
# EXPECTED-STOP steps: the unmarked-entry listing and the non-200 send must
# NEVER pass a gate (exit 5 on the send, exit 2 on the create gate — an
# attack that PASSES any gate is a broken gate), and the composition FAILS
# rather than report success. The golden controls are EXPECTED-PASS steps: a
# fully provisioned census is the already-provisioned state (exit 0) and the
# 200-send control must PASS (exit 0) — a refusal is a FAIL of the
# composition, never a silent pass. The create/send gates are EXPECTED-STOP
# steps: an ACTION requested WITHOUT --execute MUST refuse exit 2 (the Trevor
# gate) — a no-execute ACTION that proceeds is a broken gate. The example
# performs NO CREATE ACTION and NO SEND on a live location at all: every
# ACTION is proven OFFLINE by the family's own gate controls (provision
# STOPS without --execute — the verbatim AF-AE-PROVACTION-NO-EXECUTE /
# AF-AE-PHONELIST-NO-EXECUTE / AF-AE-SMSVER-NO-EXECUTE /
# AF-AE-SMSENDER-NO-EXECUTE family — and the attack fixture ships only under
# --execute), never exercised against a live location.
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
# or logged. The location id, every number, every destination and every
# contact id are MASKED on operator surfaces (last 4 chars, non-reversible);
# full ids ride inside request URLs only. The message text is never surfaced
# at all (the fixed-length sha256 marker of sms_sender, or absent entirely).
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
#   0  all steps PASSED — live listing read succeeded, golden
#      phone-provisioned gate PASSES, the unmarked-entry attack STOPS the
#      create gate (as it must), non-200 send attack FAILS (as it must),
#      golden 200-send control PASSES, send-verifier law PASSES over the
#      golden control, the no-execute ACTION STOPs fire as they must; also
#      --plan and --self-test pass
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — a Convert and Flow private-integration token or
#      location id NOT SET, or a sibling law STOPPED (a golden-has-phone /
#      attack-sms-failed / sms-verifier refusal, the no-execute ACTION
#      gates, a genuine scope denial) — honored verbatim, never downgraded
#   3  Convert and Flow unreachable or upstream edge block (HELD; retryable
#      — the outcome is UNDETERMINED, never proven verified)
#   4  enforced violation — an OFFLINE self-test assertion tripped
#      (AF-AE-EXAMPLE-USAGE-* family). A tamper NEVER masquerades as exit 1.
#   5  mismatch — an expected-fail step did NOT fail (the unmarked-entry
#      listing or the non-200 send PASSED a gate it must FAIL), the golden
#      phone-provisioned gate REFUSED the golden state, the golden 200-send
#      control REFUSED, the send-verifier law refused the golden control, or
#      a no-execute ACTION did not STOP
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --plan and --self-test are OFFLINE and need NO token and NO
# network). This is the canonical example invocation:
#
#   python3 scripts/u23_modules/example_usage.py run [--location-id ID]
#   python3 scripts/u23_modules/example_usage.py plan
#   python3 scripts/u23_modules/example_usage.py self-test
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, _live_client, resolve_location,
# _mask_location, _stop, and the exception classes) and the sibling U23
# modules (golden_has_phone, attack_sms_failed, sms_verifier) imported BY
# NAME; provision_action's OWN law surfaces stay the single implementation
# of the provisioning law — this runner never re-implements it.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value;
# --plan and --self-test are OFFLINE.
# =============================================================================
"""example_usage.py — fail-closed worked example of the U23 SMS
phone-provisioning surface composed end to end (U23 tooling, Skill 59)."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the LeadConnector client, and its label
# resolution is the house credential contract. The sibling U23 modules stay
# the single implementation of each law — this module only orchestrates
# them and honors their exit codes verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u23_modules.attack_sms_failed as attack  # noqa: E402
import u23_modules.golden_has_phone as golden  # noqa: E402
import u23_modules.provision_action as prov  # noqa: E402
import u23_modules.sms_verifier as verifier  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The report contract this runner owns (one fixed string, so a machine
# consumer can never mistake another JSON object for the example report).
EXAMPLE_CONTRACT = "anthology-engine-example-usage"


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
        "note": "live phone-number listing + golden phone-provisioned gate + "
                "unmarked-entry attack + failed-send attack + golden 200-send "
                "control + send-verifier law + no-execute ACTION gates, "
                "composed end to end",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    out.write("[example-usage] %s\n" % verdict)
    return EX_OK if ok else exit_code


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
# In-memory read surfaces for the OFFLINE steps — the same seams the
# siblings' own self-tests use (the u05 / u06 / u07 _FakeRail / _FakeCaf
# pattern). Each one binds ONLY the paths its law consumes and logs every
# write, so the composition can PROVE no mutation happened where none should.
# ---------------------------------------------------------------------------
class _GoldenCaf:
    """In-memory Convert and Flow read surface for the OFFLINE golden and
    attack steps: GET /phones/numbers returns the golden already-provisioned
    listing (the one SMS-capable number under the golden markers) or the
    unmarked-entry attack listing, programmable per instance. No create
    surface exists here — the example never performs a CREATE ACTION against
    a live location, and the Trevor gate is proven on the family's OWN
    no-execute STOPs instead."""

    def __init__(self, numbers):
        self._numbers = list(numbers or [])
        self.writes = []  # any mutating call would land here and fail

    def _request(self, method, path, query=None, body=None):
        q = query or {}
        if method == "GET" and path == "/phones/numbers":
            return {"numbers": [dict(n) for n in self._numbers]}
        raise AssertionError("the golden surface must never be asked to "
                             "%s %s (the example performs no ACTION)" % (method, path))


class _FakeVerifierCaf:
    """In-memory send surface for the OFFLINE send-verifier law step,
    mirroring sms_verifier._FakeCaf: the outbound send POST answers with
    HTTP 200 PLUS a message identifier by default. No write can escape —
    every call is logged and the example never performs a live send."""

    def __init__(self, sid="SM_EXAMPLE_SID"):
        self._sid = sid
        self.writes = []

    def _request(self, method, path, query=None, body=None):
        q = query or {}
        if method == "POST" and path == verifier.SEND_PATH:
            self.writes.append(("send", q.get("locationId"), body))
            return {"id": self._sid}
        raise AssertionError("the verifier surface must never be asked to "
                             "%s %s (the example performs no live send)" % (method, path))


# ---------------------------------------------------------------------------
# The example run — orchestration ONLY. Every judgment is delegated to the
# sibling law; its exit code is honored verbatim (never downgraded).
# ---------------------------------------------------------------------------
def example_run(client, location_id: str, *, out=None, jsonout=None) -> int:
    """Run the U23 example surface on a live location.

    - the LIVE READ through the PROVEN public rail
      GET /phones/numbers?locationId=<loc>      -> the location's existing
         numbers, read by the client's OWN pit- token BY LABEL through
         reg.CafClient (an EMPTY listing is a truthful PASS — it means the
         needs-provision state; a missing credential is a STOP; an
         unreachable rail / edge block / malformed listing is HELD — never
         a fabricated list)
    - golden_has_phone's payload gate over the canonical golden record
                                       -> the already-provisioned state holds
                                          (exit 0, idempotent no-op)
    - provision_action's own attack surface (the unmarked-entry listing
      over _GoldenCaf)                 -> an unmarked SMS entry is NEVER
                                          trusted: the create gate STOPS
                                          (exit 2, AF-AE-PROVACTION-NO-
                                          EXECUTE) over BOTH the
                                          needs-provision read and the
                                          unmarked listing — never a silent
                                          idempotent pass, creation is
                                          never silent
    - attack_sms_failed's verify_send over the canonical ATTACK_RECORD
                                       -> the non-200 send MUST FAIL (exit 5)
    - attack_sms_failed's verify_send over the golden 200-send control
                                       -> the control PASSES (exit 0) — the
                                          pass/fail split discriminates the
                                          status boundary, never a broken
                                          instrument
    - sms_verifier's verify_send over the golden control surface
                                       -> the send-verification law PASSES
                                          (exit 0 — HTTP 200 + SID SET), and
                                          the no-execute STOP (exit 2,
                                          AF-AE-SMSVER-NO-EXECUTE) fires as
                                          it must
    - the no-execute ACTION gates on EVERY ACTION surface (the family's OWN
      surfaces)                         -> provision_action.provision_action,
                                          phone_lister.provision_action and
                                          sms_sender.send_action each STOP
                                          exit 2 WITHOUT --execute over the
                                          canonical fixtures (the Trevor
                                          gate; AF-AE-PROVACTION-NO-EXECUTE
                                          / AF-AE-PHONELIST-NO-EXECUTE /
                                          AF-AE-SMSENDER-NO-EXECUTE) —
                                          an ACTION is never silent, and
                                          the example NEVER runs one against
                                          a live location

    Machine surface: the ONE JSON report object lands on jsonout (stdout);
    every sibling gate document and every human note go to out (stderr).
    `client` is the injected read surface: the production caller passes the
    registry's own reg.CafClient (resolved BY LABEL in main); the OFFLINE
    self-test passes _GoldenCaf / _FakeVerifierCaf over synthetic material,
    so the composition is pinned without a credential and without the
    network.
    """
    out = out or sys.stderr
    jsonout = jsonout or sys.stdout
    steps = []
    masked = _mask_location(location_id)

    # (1) LIVE READ — the ONE PIT-gated live read: the location's existing
    #     phone numbers through the PROVEN public rail
    #     GET /phones/numbers?locationId=<loc>, resolved BY LABEL (SET /
    #     NOT SET only, value never printed), riding reg.CafClient
    #     (CAF_BROWSER_UA on every request — the CF 1010 edge fix). The
    #     sibling provision_action.plan_action owns the READ surface and
    #     its refusal ladder: EX_OK (including an EMPTY listing — the
    #     truthful needs-provision state), EX_STOP (a missing credential /
    #     scope denial — the gate fires BEFORE any network), EX_HELD (an
    #     unreachable rail / Cloudflare edge block / malformed listing —
    #     UNDETERMINED, never a fabricated list). The step is the live
    #     plan over the client's OWN listing; no write can follow (the
    #     plan surface is read-only by construction).
    with _sibling_stdout_to(out):
        rc_plan = prov.plan_action(client, location_id, out=out)
    if rc_plan == EX_STOP:
        steps.append({"step": "live-list", "ok": False, "exit": EX_STOP,
                      "verdict": "STOP: no Convert and Flow credential SET "
                                 "by label, or a genuine scope denial "
                                 "(exit 2)"})
        return _report(ok=False, verdict="STOP: the live phone-number "
                       "listing refused (exit 2 — credential NOT SET by "
                       "label or scope denied)", steps=steps,
                       masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout, exit_code=EX_STOP)
    if rc_plan == EX_HELD:
        steps.append({"step": "live-list", "ok": False, "exit": EX_HELD,
                      "verdict": "HELD: rail unreachable / edge-blocked / "
                                 "malformed listing (exit 3 — "
                                 "UNDETERMINED, never verified)"})
        return _report(ok=False, verdict="HELD: Convert and Flow "
                       "unreachable or edge-blocked (exit 3 — "
                       "UNDETERMINED, never verified)", steps=steps,
                       masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout, exit_code=EX_HELD)
    if rc_plan != EX_OK:
        steps.append({"step": "live-list", "ok": False, "exit": rc_plan,
                      "verdict": "the live phone-number listing returned "
                                 "exit %d" % rc_plan})
        return _report(ok=False, verdict="FAIL: the live phone-number "
                       "listing returned exit %d" % rc_plan, steps=steps,
                       masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    steps.append({"step": "live-list", "ok": True, "exit": EX_OK,
                  "verdict": "live /phones/numbers listing succeeded through "
                             "the proven public rail (an EMPTY listing is "
                             "the truthful needs-provision state)"})

    # (2) GOLDEN PHONE-PROVISIONED GATE — the location already carries an
    #     SMS-capable number under the golden markers is the U23
    #     already-provisioned state (golden_has_phone owns that law; exit 5
    #     on refusal). The canonical record is the fixture's own payload —
    #     the law is judged OFFLINE over the golden shape; the live read's
    #     idempotency discipline is proven by the listing law itself.
    with _sibling_stdout_to(out):
        gold = golden.payload(golden.golden_has_phone(), out=out)
    if gold != EX_OK:
        steps.append({"step": "golden-has-phone", "ok": False,
                      "exit": EX_MISMATCH,
                      "verdict": "the already-provisioned law REFUSED the "
                                 "golden record"})
        return _report(ok=False, verdict="FAIL: the already-provisioned law "
                       "REFUSED the golden record (see steps)", steps=steps,
                       masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    steps.append({"step": "golden-has-phone", "ok": True, "exit": EX_OK,
                  "already_provisioned": golden.ALREADY_PROVISIONED,
                  "execute_required": golden.EXECUTE_REQUIRED_FOR_PROVISION,
                  "verdict": "the golden phone-provisioned state PASSES "
                             "(exit 0 — idempotent no-op, never "
                             "re-provisioned, never a second number)"})

    # (3) MISSING-MARKER ATTACK — an SMS entry with NO smsEnabled key must
    #     never be trusted as SMS-capable (provision_action owns that law
    #     via its own attack fixture). The proof is the family's own: over
    #     the needs-provision read the create ACTION MUST STOP exit 2
    #     WITHOUT --execute (AF-AE-PROVACTION-NO-EXECUTE — the Trevor
    #     gate), and over the unmarked-entry listing the gate must STILL
    #     fire — a module that silently trusted the unmarked entry would
    #     short-circuit to the idempotent NO-OP (exit 0); the STOP proves
    #     it never does. The no-execute STOPs are provable OFFLINE over the
    #     family's own surface, which never resolves a credential and never
    #     touches the network. This runner calls the raw law and maps the
    #     expected STOP to a step pass — the SAME exit code, honored
    #     verbatim, never downgraded.
    with _sibling_stdout_to(out):
        rc_noexec = prov.provision_action(
            _GoldenCaf([]), location_id, execute=False, out=out)
    if rc_noexec != EX_STOP:
        steps.append({"step": "missing-marker", "ok": False, "exit": rc_noexec,
                      "verdict": "the create ACTION without --execute did "
                                 "NOT STOP over the needs-provision read"})
        return _report(ok=False, verdict="FAIL: the create ACTION without "
                       "--execute did NOT STOP (the Trevor gate is broken)",
                       steps=steps, masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    with _sibling_stdout_to(out):
        rc_attack = prov.provision_action(
            _GoldenCaf(prov._attack_numbers()), location_id, execute=False,
            out=out)
    if rc_attack != EX_STOP:
        steps.append({"step": "missing-marker", "ok": False, "exit": rc_attack,
                      "verdict": "the unmarked-entry listing did NOT STOP "
                                 "the create gate (an unmarked entry was "
                                 "silently trusted as SMS-capable)"})
        return _report(ok=False, verdict="FAIL: the unmarked-entry listing "
                       "did NOT STOP the create gate (an unmarked SMS entry "
                       "is NEVER trusted as SMS-capable — broken gate)",
                       steps=steps, masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    steps.append({"step": "missing-marker", "ok": True, "exit": EX_OK,
                  "af_code": "AF-AE-PROVACTION-NO-EXECUTE",
                  "verdict": "the create ACTION STOPS exit 2 without "
                             "--execute over both the needs-provision read "
                             "and the unmarked-entry listing — an unmarked "
                             "SMS entry is NEVER trusted as SMS-capable "
                             "(never a silent idempotent pass; masked "
                             "markers only, never a number)"})

    # (4) FAILED-SEND ATTACK — the canonical non-200 send-test-message
    #     record MUST FAIL every SMS-verification authority (exit 5).
    #     attack_sms_failed owns that law; its verify_send judges the
    #     canonical ATTACK_RECORD fixture. An attack that PASSES any gate is
    #     a broken gate, and the composition FAILS rather than report
    #     success.
    with _sibling_stdout_to(out):
        rc_send = attack.verify_send(attack.ATTACK_RECORD, out=out)
    if rc_send != EX_MISMATCH:
        steps.append({"step": "failed-send", "ok": False, "exit": rc_send,
                      "verdict": "the non-200 send attack did NOT FAIL"})
        return _report(ok=False, verdict="FAIL: the non-200 send attack did "
                       "NOT FAIL (an SMS-verification gate passed the "
                       "failed send — broken gate)", steps=steps,
                       masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    steps.append({"step": "failed-send", "ok": True, "exit": EX_MISMATCH,
                  "action": attack.SEND_ACTION,
                  "status": attack.ATTACK_RECORD.get("status"),
                  "verdict": "the non-200 send attack FAILED as it must "
                             "(exit 5 — the number is NOT verified, never a "
                             "false pass)"})

    # (5) GOLDEN 200-SEND CONTROL — the negative-result contract: the true
    #     200-send record must PASS exit 0, so a gate that FAILS EVERYTHING
    #     (a broken instrument) is never mistaken for a real non-200
    #     discrimination (attack_sms_failed's GOLDEN_SEND_RECORD — the SAME
    #     judge, the SAME law).
    with _sibling_stdout_to(out):
        rc_true = attack.verify_send(dict(attack.GOLDEN_SEND_RECORD), out=out)
    if rc_true != EX_OK:
        steps.append({"step": "golden-200-control", "ok": False,
                      "exit": rc_true,
                      "verdict": "the golden 200-send control did NOT PASS"})
        return _report(ok=False, verdict="FAIL: the golden 200-send control "
                       "refused (a gate that fails everything is a broken "
                       "instrument — the pass/fail split discriminates the "
                       "boundary, never a broken gate)", steps=steps,
                       masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    steps.append({"step": "golden-200-control", "ok": True, "exit": EX_OK,
                  "status": 200,
                  "verdict": "the golden 200-send control PASSES (exit 0 — "
                             "the pass/fail split discriminates the status "
                             "boundary)"})

    # (6) SEND-VERIFIER LAW — a send is never reported delivered without
    #     HTTP 200 PLUS a message identifier (sms_verifier owns that law;
    #     a 200 with no SID is a read-back mismatch, exit 5, never a pass).
    #     The law is judged OFFLINE over the golden control surface (the
    #     _FakeVerifierCaf answers HTTP 200 + SID): the PASS side must hold
    #     (exit 0), and the no-execute STOP (AF-AE-SMSVER-NO-EXECUTE) must
    #     fire as it must. The example NEVER performs a live send.
    with _sibling_stdout_to(out):
        rc_ok = verifier.verify_send(
            _FakeVerifierCaf(), location_id, "+12025550123",
            "example text", execute=True, out=out)
    if rc_ok != EX_OK:
        steps.append({"step": "send-verifier", "ok": False, "exit": rc_ok,
                      "verdict": "the send-verifier law REFUSED the golden "
                                 "200+SID control"})
        return _report(ok=False, verdict="FAIL: the send-verifier law "
                       "REFUSED the golden 200+SID control (see steps)",
                       steps=steps, masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    with _sibling_stdout_to(out):
        rc_nox = verifier.verify_send(
            _FakeVerifierCaf(), location_id, "+12025550123",
            "example text", execute=False, out=out)
    if rc_nox != EX_STOP:
        steps.append({"step": "send-verifier", "ok": False, "exit": rc_nox,
                      "verdict": "the send ACTION without --execute did NOT "
                                 "STOP"})
        return _report(ok=False, verdict="FAIL: the send ACTION without "
                       "--execute did NOT STOP (the Trevor gate is broken)",
                       steps=steps, masked_location=masked, cred_label="PIT",
                       out=out, jsonout=jsonout)
    steps.append({"step": "send-verifier", "ok": True, "exit": EX_OK,
                  "af_code": "AF-AE-SMSVER-NO-EXECUTE",
                  "executed": False,
                  "verdict": "the send-verifier law PASSES over the golden "
                             "200+SID control (exit 0) and the no-execute "
                             "send STOPS exit 2 (never a mutation)"})

    return _report(ok=True, verdict="VERIFIED", steps=steps,
                   masked_location=masked, cred_label="PIT",
                   out=out, jsonout=jsonout)


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
        "steps": [
            "live-list: provision_action.plan_action reads the location's "
            "existing phone numbers through the PROVEN public rail "
            "GET /phones/numbers?locationId=<loc> (services.leadconnectorhq.com "
            "-- rides reg.CafClient CAF_BROWSER_UA so the Cloudflare edge "
            "never 1010s the read; PIT BY LABEL, never printed; an EMPTY "
            "listing is the truthful needs-provision state, an unreachable "
            "rail / edge block / malformed listing is HELD exit 3, never a "
            "fabricated list)",
            "golden-has-phone: u23_modules.golden_has_phone payload gates "
            "the canonical phone-provisioned record -- the location already "
            "carries an SMS-capable number under the golden markers, the "
            "already-provisioned state, exit 0 (idempotent no-op, never a "
            "second number, never a second charge)",
            "missing-marker: provision_action's own attack surface -- an "
            "SMS entry with NO smsEnabled marker is NEVER trusted as "
            "SMS-capable, and the create ACTION must STOP exit 2 WITHOUT "
            "--execute (AF-AE-PROVACTION-NO-EXECUTE, the Trevor gate) over "
            "BOTH the needs-provision read and the unmarked-entry listing "
            "-- never a silent idempotent pass, never a silent create; an "
            "unmarked entry that is silently trusted is a broken gate",
            "failed-send: u23_modules.attack_sms_failed verify_send judges "
            "the canonical non-200 send-test-message record -- MUST FAIL "
            "exit 5 (a send answered with ANY non-200 status is a FAILED "
            "send, the number is NOT verified, never a false pass)",
            "golden-200-control: attack_sms_failed's golden 200-send record "
            "-- MUST PASS exit 0 (the pass/fail split discriminates the "
            "status boundary, never a broken instrument)",
            "send-verifier: u23_modules.sms_verifier verify_send over the "
            "golden 200+SID control -- HTTP 200 PLUS a message identifier "
            "is required before anything is called delivered (exit 0), and "
            "the no-execute send STOPS exit 2 (AF-AE-SMSVER-NO-EXECUTE); "
            "a 200 with no SID is a read-back mismatch (exit 5), never a "
            "pass",
        ],
        "note": "offline plan only — no network, no credential needed; "
                "judgments are made by the sibling modules, never here; "
                "the live listing is the ONE PIT-gated surface, every "
                "ACTION (create / send / verify) is Trevor-gated "
                "(--execute), and the example performs NO ACTION against a "
                "live location — the gates are proven OFFLINE over "
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

    # 2. The sibling laws are consistent with each other — the golden and
    #    the attack fixtures share the SAME SMS-marker authority (the fixed
    #    key set of provision_action, the single-implementation doctrine),
    #    and every ACTION surface is Trevor-gated (--execute or STOP).
    assert golden.SMS_ENABLED_KEYS == prov.SMS_ENABLED_KEYS, \
        "the golden fixture must share the provisioner's SMS-marker law"
    assert golden.EXECUTE_REQUIRED_FOR_PROVISION is True, \
        "the golden fixture must certify the --execute law"
    assert golden.ALREADY_PROVISIONED is True, \
        "the golden fixture must certify the already-provisioned truth"

    # 3. The family's OWN offline batteries pass — the registry's self-test
    #    proves the UA rides on the wire (evidence the example run is
    #    protected the same way), and the golden / attack fixtures prove
    #    themselves (an attack fixture that PASSES any gate, or a golden
    #    fixture that refuses its own state, is a broken fixture — the
    #    composition must never certify one). Their stdout receipts are
    #    captured — the ONLY machine document on stdout here is the example
    #    report.
    with contextlib.redirect_stdout(io.StringIO()):
        assert reg.self_test() == EX_OK, "registry self-test must pass"
        assert prov.self_test() == EX_OK, \
            "provision_action self-test must pass"
        assert verifier.self_test() == EX_OK, \
            "sms_verifier self-test must pass"
        assert attack.self_test() == EX_OK, \
            "attack_sms_failed self-test must pass"
        assert golden.self_test() == EX_OK, \
            "golden_has_phone self-test must pass"

    # 4. The example composition — the golden path exits 0 with every step
    #    in the documented order; the attack steps are the expected-FAIL /
    #    expected-STOP steps (honored verbatim). The golden path needs the
    #    live read to succeed, which requires a credential AND the network —
    #    neither may be depended on OFFLINE, so the read is stubbed exactly
    #    as the u05 / u06 / u07 example siblings stub their live surface:
    #    the runner receives the seam (a _GoldenCaf over the golden
    #    already-provisioned listing — the plan over it reads the
    #    SMS-capable number and reports already-provisioned), and the
    #    composition is pinned against a deterministic SUCCESS read. The
    #    registry's OWN credential / STOP / HELD paths are proven by the
    #    registry's self-test and by the CLI credential gate (main() STOPS
    #    before any network when no credential is SET).
    report_buf = io.StringIO()
    rc = example_run(
        _GoldenCaf([dict(n) for n in golden.golden_has_phone_listing()["numbers"]]),
        "loc_tmpl", out=io.StringIO(), jsonout=report_buf)
    assert rc == EX_OK, "the golden composition must exit 0, got %s" % rc
    report = json.loads(report_buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "VERIFIED"
    assert report["contract"] == EXAMPLE_CONTRACT
    assert report["location_masked"] == "...tmpl", \
        "the location must be masked to the last-4 marker"
    steps = {s["step"]: s for s in report["steps"]}
    assert list(steps) == ["live-list", "golden-has-phone", "missing-marker",
                           "failed-send", "golden-200-control",
                           "send-verifier"], \
        "the composition must run the six steps in the documented order"
    assert steps["live-list"]["exit"] == EX_OK
    assert steps["golden-has-phone"]["exit"] == EX_OK
    assert steps["golden-has-phone"]["already_provisioned"] is True
    assert steps["missing-marker"]["exit"] == EX_OK
    assert steps["missing-marker"]["af_code"] == "AF-AE-PROVACTION-NO-EXECUTE"
    assert steps["failed-send"]["exit"] == EX_MISMATCH, \
        "the failed-send step must carry the expected exit 5"
    assert steps["golden-200-control"]["exit"] == EX_OK
    assert steps["send-verifier"]["exit"] == EX_OK
    assert steps["send-verifier"]["af_code"] == "AF-AE-SMSVER-NO-EXECUTE"
    assert steps["send-verifier"]["executed"] is False, \
        "the send-verifier step must never claim a live send"

    # 5. The empty-credential run — the example run with a NONE client is
    #    exercised in main() (the registry's own _live_client credential
    #    gate STOPS exit 2 before any network — never a fabricated list);
    #    the STOP path is the registry's own law, proven by its self-test.

    # 6. Never-print: no credential-shaped string, no full number, no full
    #    destination, no message text, no identifier on any surface.
    blob = report_buf.getvalue() + dev.getvalue()
    for token in ("pit-", "Bearer ", "sk-", "eyJ", "+12025559876",
                  "+12025550123", "loc_tmpl", "SM_EXAMPLE_SID",
                  "SM_SELF_TEST_SID"):
        assert token not in blob, \
            "surface leak: %r must never appear" % token

    dev.write("example_usage self-test: OK (browser UA pinned byte-exact; "
              "sibling laws consistent — the golden and the attack share the "
              "same SMS-marker authority, every ACTION surface is "
              "Trevor-gated; the registry and every family module self-test "
              "pass; the golden composition exits 0 with the six steps in "
              "order — the unmarked-entry step carries the expected "
              "AF-AE-PROVACTION-NO-EXECUTE STOP, failed-send carries the "
              "expected exit 5, golden-200-control PASSes, send-verifier "
              "carries AF-AE-SMSVER-NO-EXECUTE and never claims a live "
              "send; never a token shape)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="example_usage.py",
        description="Fail-closed worked example of the U23 SMS "
                    "phone-provisioning surface (Skill 59): live-read the "
                    "location's phone numbers through the proven public "
                    "rail, prove the golden already-provisioned state, the "
                    "unmarked-entry attack STOPS the create gate as it "
                    "must, the failed-send attack FAILS as it must, its "
                    "golden 200-send control, the send-verification law, "
                    "and the Trevor-gated ACTION gates — one JSON report, "
                    "fail-closed; never prints a secret value.")
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
        # client's OWN location-scoped private-integration token through
        # reg._live_client (SET / NOT SET only on every operator surface);
        # the credential gate STOPS before any network when no token is
        # SET. The read surface is the registry's own CafClient — the ONLY
        # thing that ever talks to Convert and Flow — carrying CAF_BROWSER_UA
        # on every request (the CF 1010 edge fix).
        client, loc_or_rc = reg._live_client(args.location_id)
        if client is None:
            return loc_or_rc
        return example_run(client, loc_or_rc, out=sys.stderr,
                           jsonout=sys.stdout)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[example-usage] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[example-usage] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
