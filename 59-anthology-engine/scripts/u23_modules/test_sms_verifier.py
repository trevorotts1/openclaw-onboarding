#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/test_sms_verifier.py
# UNIT TESTS for the U23 SMS SEND VERIFIER (scripts/u23_modules/sms_verifier.py
# — fail-closed outbound-SMS verification for the Convert and Flow client
# location: POST /conversations/messages/outbound under --execute and require
# HTTP 200 PLUS a message identifier (SID) before anything is called
# delivered). The one law this file exists to enforce: AN UNCONFIRMED SEND IS
# NEVER CALLED DELIVERED — HTTP 200 without a message identifier is a
# read-back mismatch (exit 5), never a pass — and the outbound POST is a
# GHL-gated ACTION that NEVER happens without --execute.
#
# COVERAGE (offline, hermetic, no network, no credentials, no tokens):
#   * the ACTION gate: verification without --execute STOPS (exit 2,
#     AF-AE-SMSVER-NO-EXECUTE) and the outbound POST is proven absent — a
#     stub client that RECORDS every write and fails the test the moment a
#     send is attempted
#   * the fail-closed argument ladder: an empty destination or an empty
#     message STOPS (exit 2, AF-AE-SMSVER-REFUSED) before any network, with
#     no write
#   * the golden send under --execute: EXACTLY ONE POST to SEND_PATH with
#     query locationId and the documented body (to / message / channel sms);
#     HTTP 200 + SID -> exit 0, VERIFIED, and the identifier is surfaced as
#     SET ONLY — its value never rides any surface
#   * the read-back law: HTTP 200 whose body carries NO message identifier is
#     EXIT 5 (AF-AE-SMSVER-NO-SID) — never a pass, never a "delivered"
#   * the SID extractor: exact-key, presence-only, read in the fixed key
#     ORDER (id / messageId / message_id / sid / messageSid); a whitespace
#     value, a non-mapping body, and a foreign key are NEVER read
#   * the refusal ladder: scope denial and validation refusal STOP (exit 2);
#     an edge block / transport failure is HELD (exit 3) — a bare 401/403
#     that does not match the scope signature is NEVER mislabeled as a scope
#     problem
#   * never-a-secret: the pit- credential shape, the full location id, the
#     full destination number, the message text, and Bearer NEVER reach any
#     surface (markers are last-2 / last-4 digit suffixes only; the message
#     text is never echoed)
#   * the browser-UA law (CF 1010): the constant surface is pinned against
#     reg.CAF_BROWSER_UA — a browser User-Agent with a Chrome segment, and
#     urllib's default "Python-urllib/x.y" is 1010'd at the Cloudflare edge
#     fronting services.leadconnectorhq.com before it ever reaches Convert
#     and Flow (the send rides reg.CafClient, which carries the UA on every
#     request)
#   * the CLI surface: verify without --execute STOPS after credential
#     resolution with ZERO writes; verify --dry-run and plan are OFFLINE (no
#     token resolution, no network); a missing destination or message STOPS
#     before any credential is resolved; self-test is OFFLINE
#   * the module's own OFFLINE self-test battery runs as a process (the
#     house self-test convention — a tamper NEVER masquerades as exit 1),
#     and the U23 sibling battery (provision_sms_phone.py) stays green
#
# HERMETIC BY DESIGN — OFFLINE: no network, no credentials, no browser.
# Every verify_send invocation runs against the in-memory _FakeCaf — an
# INDEPENDENT stub (distinct from the module's own self-test seam, with a
# mutation log and a hard-fail on any unexpected write) so a shared-stub
# blind spot cannot green both batteries.
#
# Run: python3 -m pytest scripts/u23_modules/test_sms_verifier.py -q
#  or: python3 scripts/u23_modules/test_sms_verifier.py
# =============================================================================
"""test_sms_verifier.py -- the U23 SMS send-verification law: an unconfirmed
send is NEVER called delivered, and the outbound POST is --execute-gated."""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: F401  (house style: pytest with plain asserts)

# Import bootstrap (house convention): the registry lives one directory up.
SCRIPTS = Path(__file__).resolve().parent.parent
U23 = SCRIPTS / "u23_modules"

for _p in (SCRIPTS, U23):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import anthology_registry as reg  # noqa: E402

# The module under test — imported BY NAME exactly as the engine imports it
# (import u23_modules.sms_verifier). A missing module is a FAILED test,
# never a silent skip.
import u23_modules.sms_verifier as smsv  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

CREDENTIAL_SHAPE = re.compile(r"pit-\S+")
LOCATION_ID = "loc_tmpl4loc00"
DESTINATION = "+12025550123"
MESSAGE_TEXT = "hello from the battery"
SID_VALUE = "SM_BATTERY_1A2B"

# ---------------------------------------------------------------------------
# The hermetic seam: an INDEPENDENT in-memory Convert and Flow for the
# battery. Serves the ONE surface the module uses (the outbound send POST),
# records every request, and fails the moment a write is attempted where
# none should be. NEVER a network call.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow for the battery. Programmable send
    behavior; every call is recorded so the tests can prove exactly which
    request rode the wire and that no write happened when none should."""

    def __init__(self, send_behavior=None, sid=None, http_ok=True):
        self.send_behavior = send_behavior  # None | scope | validation | edge | transport | no-sid
        self.sid = sid                      # the identifier the fake returns on success
        self.http_ok = http_ok              # False -> HTTP 200-with-no-id (no-sid) surface
        self.calls = []                     # every mutating call, in order

    def _request(self, method, path, query=None, body=None):
        self.calls.append({"method": method, "path": path,
                           "query": dict(query or {}), "body": body})
        if method == "POST" and path == smsv.SEND_PATH:
            if self.send_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.send_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.send_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.send_behavior == "no-sid":
                return {"ok": True}  # HTTP 200 but NO identifier — never a pass
            if not self.http_ok:
                return {}            # HTTP 200 with an empty body — no id either
            return {"id": self.sid or "SM_FAKE_SID"}
        raise AssertionError("unexpected call: %s %s" % (method, path))

    @property
    def writes(self):
        return [c for c in self.calls if c["method"] == "POST"]

# ---------------------------------------------------------------------------
# Cross-cutting house doctrine: the exit-code convention, the fail-closed
# empty package init, the surface contract, and the CF 1010 browser-UA law.
# ---------------------------------------------------------------------------
def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """The module pins the house exit-code convention (0/1/2/3/4/5) —
    asserted through the exported constants, never re-typed."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert (smsv.EX_OK, smsv.EX_ERR, smsv.EX_STOP, smsv.EX_HELD,
            smsv.EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4 and EX_VIOLATION not in (0, 1, 2, 3, 5)
    assert smsv.EX_VIOLATION == 4

def test_u23_package_init_is_fail_closed_empty():
    """The u23_modules package init is a pure namespace container — no
    runtime code, no secret surface (fail-closed empty init)."""
    import u23_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()

def test_sms_verifier_is_importable_by_name_with_the_contract_surface():
    """The module ships importable by NAME (the engine's import law) and
    carries the documented contract surface: the outbound SEND_PATH, the
    fixed SID key set, the fail-closed extractor, the gated verify entry,
    the offline self-test, and the CLI main."""
    module_path = U23 / "sms_verifier.py"
    assert module_path.is_file(), "missing owned file: %s" % module_path
    for symbol in ("verify_send", "_extract_sid", "_mask_destination",
                   "self_test", "main", "SEND_PATH", "SID_KEYS"):
        assert hasattr(smsv, symbol), "missing module surface: %s" % symbol

def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: every Convert and Flow request rides a browser
    User-Agent — urllib's default Python-urllib/x.y is 403'd at the
    Cloudflare WAF edge (CF error 1010) before it ever reaches the API.
    The constant surface is pinned against the registry's OWN authority
    (the send rides reg.CafClient, which carries the UA on every request):
    a drift in the registry breaks THIS battery first."""
    ua = reg.CAF_BROWSER_UA
    assert ua.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r" % ua[:40])
    assert "Chrome/" in ua, "CAF_BROWSER_UA must carry a Chrome segment"
    assert "Python-urllib" not in ua, (
        "urllib's default UA is 1010'd at the Cloudflare edge")

def test_send_surface_is_the_documented_outbound_rail():
    """The module sends on the ONE documented public rail — the outbound
    conversation-message surface — never a guessed path."""
    assert smsv.SEND_PATH == "/conversations/messages/outbound"

def test_sid_key_set_is_the_fixed_contract_in_order():
    """The message-identifier key set is fixed and ordered (id first, then
    messageId / message_id / sid / messageSid) — the ORDER is the law (a
    response carrying several spellings is read by preference, never by
    chance)."""
    assert smsv.SID_KEYS == ("id", "messageId", "message_id", "sid",
                             "messageSid")
    assert len(smsv.SID_KEYS) == 5 and len(set(smsv.SID_KEYS)) == 5

def test_mask_destination_is_a_non_reversible_marker():
    """The destination marker is non-reversible — last 2 digits only — and
    never echoes the full number."""
    assert smsv._mask_destination(DESTINATION) == "...23"
    assert smsv._mask_destination("") == "(short number)"
    assert DESTINATION not in smsv._mask_destination(DESTINATION)

# ---------------------------------------------------------------------------
# The SID extractor: exact-key, presence-only, fixed order; a whitespace
# value, a non-mapping body, and a foreign key are NEVER read.
# ---------------------------------------------------------------------------
def test_extract_sid_reads_by_fixed_key_order():
    """The extractor reads the identifier by the fixed key ORDER — a body
    carrying several spellings resolves to the FIRST in contract order."""
    assert smsv._extract_sid({"id": "SM_A", "messageId": "SM_B"}) == "SM_A"
    assert smsv._extract_sid({"messageId": "SM_B"}) == "SM_B"
    assert smsv._extract_sid({"message_id": "SM_C"}) == "SM_C"
    assert smsv._extract_sid({"sid": "SM_D"}) == "SM_D"
    assert smsv._extract_sid({"messageSid": "SM_E"}) == "SM_E"

def test_extract_sid_refuses_whitespace_non_mapping_and_foreign_keys():
    """A whitespace-only value, a non-mapping body, and a foreign key are
    NEVER read — the extractor is presence-only and exact-key, and never
    trusts any other field of the response body."""
    assert smsv._extract_sid({"id": "", "messageId": "  "}) == ""
    assert smsv._extract_sid({"ok": True}) == ""
    assert smsv._extract_sid({"sms": "SM_X"}) == "", (
        "foreign keys are NEVER read")
    assert smsv._extract_sid([]) == ""
    assert smsv._extract_sid(None) == ""
    assert smsv._extract_sid("SM_RAW") == ""

# ---------------------------------------------------------------------------
# The ACTION gate: verification without --execute STOPS — nothing is ever
# sent. --execute is the ONLY key that opens the outbound POST.
# ---------------------------------------------------------------------------
def test_verify_without_execute_stops_and_never_sends():
    """Verification (the outbound SMS ACTION) without --execute STOPS
    (exit 2, AF-AE-SMSVER-NO-EXECUTE) — and the send POST is proven absent:
    the stub records every write and the test fails the moment one is
    attempted."""
    dev = io.StringIO()
    client = _FakeCaf()
    rc = smsv.verify_send(client, LOCATION_ID, DESTINATION, MESSAGE_TEXT,
                          out=dev)
    assert rc == EX_STOP, "verify without --execute must STOP (exit 2), got %s" % rc
    assert client.writes == [], "without --execute nothing may be sent"
    assert "AF-AE-SMSVER-NO-EXECUTE" in dev.getvalue()

def test_empty_destination_or_message_stops_before_any_network():
    """A missing destination or a missing message STOPS (exit 2,
    AF-AE-SMSVER-REFUSED) BEFORE any network — even with --execute — and
    no write is ever attempted."""
    for kwargs in ({"destination": "  ", "message": MESSAGE_TEXT},
                   {"destination": DESTINATION, "message": "  "}):
        dev = io.StringIO()
        client = _FakeCaf()
        rc = smsv.verify_send(client, LOCATION_ID, execute=True, out=dev,
                              **kwargs)
        assert rc == EX_STOP, "a refused send must STOP (exit 2), got %s" % rc
        assert client.writes == [], "a refused send must never reach the wire"
        assert "AF-AE-SMSVER-REFUSED" in dev.getvalue()

# ---------------------------------------------------------------------------
# The golden send under --execute: EXACTLY ONE POST to SEND_PATH with the
# documented body; HTTP 200 + SID -> exit 0, and the identifier is surfaced
# as SET ONLY — its value never rides any surface.
# ---------------------------------------------------------------------------
def test_golden_send_confirms_with_one_post_and_sid_set_only():
    """The golden verification: under --execute exactly ONE outbound POST
    rides — query locationId, body to/message/channel sms — and HTTP 200
    with a message identifier reports VERIFIED (exit 0). The identifier
    value never appears on any surface: the report says SET."""
    dev = io.StringIO()
    client = _FakeCaf(sid=SID_VALUE)
    rc = smsv.verify_send(client, LOCATION_ID, DESTINATION, MESSAGE_TEXT,
                          execute=True, out=dev)
    assert rc == EX_OK, "a confirmed send must exit 0, got %s" % rc
    assert len(client.writes) == 1, (
        "the golden send must perform EXACTLY ONE POST, got %r" % client.writes)
    sent = client.writes[0]
    assert sent["path"] == smsv.SEND_PATH
    assert sent["query"] == {"locationId": LOCATION_ID}
    assert sent["body"] == {"to": DESTINATION, "message": MESSAGE_TEXT,
                            "channel": "sms"}, (
        "the POST body must carry the documented to/message/channel contract")
    assert "VERIFIED" in dev.getvalue()
    assert "message identifier SET" in dev.getvalue()
    assert SID_VALUE not in dev.getvalue(), (
        "the identifier must be surfaced as SET only, never its value")

def test_golden_json_surface_reports_sid_set_only():
    """The machine-readable JSON surface reports the identifier as the
    string SET — never the identifier value — with the masked location and
    the verified/sms flags."""
    out = io.StringIO()
    client = _FakeCaf(sid=SID_VALUE)
    rc = smsv.verify_send(client, LOCATION_ID, DESTINATION, MESSAGE_TEXT,
                          execute=True, jsonout=out)
    assert rc == EX_OK
    blob = out.getvalue()
    assert '"sid": "SET"' in blob
    assert SID_VALUE not in blob
    payload = json.loads(blob)
    assert payload["ok"] is True and payload["verified"] is True
    assert payload["sms"] is True
    assert payload["location"] == reg._mask_location(LOCATION_ID)

# ---------------------------------------------------------------------------
# The read-back law: HTTP 200 whose body carries NO message identifier is
# EXIT 5 — an unconfirmed send is NEVER called delivered.
# ---------------------------------------------------------------------------
def test_http_200_without_sid_is_a_mismatch_never_a_pass():
    """A send that returns HTTP 200 but whose body carries no message
    identifier is a read-back mismatch (exit 5, AF-AE-SMSVER-NO-SID) —
    NEVER a pass, never a "delivered", and the JSON surface reports
    verified False."""
    for behavior in ("no-sid", None):
        dev = io.StringIO()
        out = io.StringIO()
        client = _FakeCaf(send_behavior=behavior,
                          http_ok=(behavior == "no-sid"))
        # no-sid: a 200 whose body carries only {"ok": True}; http_ok
        # False: a 200 with an EMPTY body — both carry no identifier
        rc = smsv.verify_send(client, LOCATION_ID, DESTINATION, MESSAGE_TEXT,
                              execute=True, out=dev, jsonout=out)
        assert rc == EX_MISMATCH, "200-without-SID must exit 5, got %s" % rc
        assert "AF-AE-SMSVER-NO-SID" in dev.getvalue()
        assert "VERIFIED" not in dev.getvalue(), (
            "a SID-less response must never read as verified")
        assert '"verified": false' in out.getvalue()
        assert '"reason": "no-sid"' in out.getvalue()

# ---------------------------------------------------------------------------
# The refusal ladder: scope denial and validation refusal STOP (exit 2); an
# edge block / transport failure is HELD (exit 3) — a bare 401/403 that does
# not match the scope signature is NEVER mislabeled as a scope problem.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("behavior, want", [
    ("scope", EX_STOP), ("validation", EX_STOP),
    ("edge", EX_HELD), ("transport", EX_HELD),
])
def test_send_refusal_ladder(behavior, want):
    """Every send refusal lands in its own class — never a silent skip,
    never a false delivered: scope and validation STOP (exit 2), edge and
    transport HELD (exit 3), and an edge block is NEVER mislabeled as a
    scope problem."""
    dev = io.StringIO()
    client = _FakeCaf(send_behavior=behavior)
    rc = smsv.verify_send(client, LOCATION_ID, DESTINATION, MESSAGE_TEXT,
                          execute=True, out=dev)
    assert rc == want, "send_behavior %r: want %s, got %s" % (behavior, want, rc)
    if behavior == "edge":
        assert "never a scope problem" in dev.getvalue(), (
            "an edge block must NEVER be mislabeled as a scope problem")

# ---------------------------------------------------------------------------
# Never-a-secret: the pit- credential shape, the full location id, the full
# destination number, the message text, and Bearer NEVER reach any surface
# — the markers (last-2 / last-4 digit suffixes) are the only shapes that
# ride; the message text is never echoed.
# ---------------------------------------------------------------------------
def test_no_full_values_on_any_captured_surface():
    """Every surface this battery captures — the verify reports, the JSON
    summaries, the dry-run surfaces — is scanned against the credential
    shape, the full location id, the full destination, the message text,
    and the Bearer shape. The masked markers are expected and never
    confused with the full values."""
    surfaces = []
    for execute in (False, True):
        dev = io.StringIO()
        out = io.StringIO()
        smsv.verify_send(_FakeCaf(sid=SID_VALUE), LOCATION_ID, DESTINATION,
                         MESSAGE_TEXT, execute=execute, out=dev, jsonout=out)
        surfaces.append(dev.getvalue())
        surfaces.append(out.getvalue())
    for blob in surfaces:
        assert CREDENTIAL_SHAPE.search(blob) is None, (
            "a captured surface leaked a credential-shaped string")
        for banned in (LOCATION_ID, DESTINATION, MESSAGE_TEXT, SID_VALUE,
                       "Bearer "):
            assert banned not in blob, (
                "a captured surface leaked %r" % banned)

def test_verify_send_never_echoes_the_message_text():
    """The message text is never echoed on any surface — not in the plan,
    not in the send report, not in the JSON — even under --execute."""
    dev = io.StringIO()
    out = io.StringIO()
    rc = smsv.verify_send(_FakeCaf(sid=SID_VALUE), LOCATION_ID, DESTINATION,
                          MESSAGE_TEXT, execute=True, out=dev, jsonout=out)
    assert rc == EX_OK
    assert MESSAGE_TEXT not in dev.getvalue()
    assert MESSAGE_TEXT not in out.getvalue()

# ---------------------------------------------------------------------------
# The CLI surface: verify without --execute STOPS after credential
# resolution with ZERO writes; verify --dry-run and plan are OFFLINE (no
# token resolution, no network); a missing destination or message STOPS
# before any credential is resolved; self-test is OFFLINE.
# ---------------------------------------------------------------------------
def _stub_live(monkeypatch, client):
    """Wire the CLI's live seams (resolve_pit / resolve_location / CafClient)
    to hermetic stubs — the credential VALUE is passed to the stub factory
    and never printed."""
    monkeypatch.setattr(reg, "resolve_pit",
                        lambda: ("CONVERT_AND_FLOW_PIT", "pit-clitok00"))
    monkeypatch.setattr(reg, "resolve_location",
                        lambda _override: ("CONVERT_AND_FLOW_LOCATION_ID",
                                           LOCATION_ID))
    monkeypatch.setattr(reg, "CafClient", lambda token: client)
    return client

def test_verify_cli_without_execute_stops_after_resolution_and_never_sends(
        monkeypatch, capsys):
    """The verify CLI without --execute STOPS (exit 2) after credential
    resolution — the token is resolved (the ACTION is attempted) but the
    outbound POST never rides the wire."""
    client = _stub_live(monkeypatch, _FakeCaf())
    rc = smsv.main(["verify", "--destination", DESTINATION,
                    "--message", MESSAGE_TEXT])
    assert rc == EX_STOP, "verify without --execute must STOP (exit 2), got %s" % rc
    assert client.writes == [], "a refused verify must never send"
    assert "AF-AE-SMSVER-NO-EXECUTE" in capsys.readouterr().err

def test_verify_cli_golden_send_under_execute(monkeypatch, capsys):
    """The verify CLI with --execute rides the golden send: exactly ONE
    POST, exit 0, and the JSON surface reports sid SET."""
    client = _stub_live(monkeypatch, _FakeCaf(sid=SID_VALUE))
    rc = smsv.main(["verify", "--destination", DESTINATION,
                    "--message", MESSAGE_TEXT, "--execute", "--json"])
    assert rc == EX_OK, "a confirmed send must exit 0, got %s" % rc
    assert len(client.writes) == 1
    out = capsys.readouterr()
    assert '"sid": "SET"' in out.out
    assert SID_VALUE not in out.out

def test_verify_cli_missing_message_stops_before_pit(monkeypatch):
    """The verify CLI without --message STOPS (exit 2) BEFORE any
    credential is resolved — a resolve_pit that would raise is never
    touched (fail-closed argument validation, never an unplanned send)."""
    def _forbidden_pit():
        raise AssertionError("a refused verify must never resolve a token")
    monkeypatch.setattr(reg, "resolve_pit", _forbidden_pit)
    rc = smsv.main(["verify", "--destination", DESTINATION])
    assert rc == EX_STOP, "verify without --message must STOP (exit 2)"

def test_verify_cli_missing_destination_stops_before_pit(monkeypatch):
    """The verify CLI without --destination STOPS (exit 2) before any
    credential is resolved."""
    def _forbidden_pit():
        raise AssertionError("a refused verify must never resolve a token")
    monkeypatch.setattr(reg, "resolve_pit", _forbidden_pit)
    rc = smsv.main(["verify", "--message", MESSAGE_TEXT])
    assert rc == EX_STOP, "verify without --destination must STOP (exit 2)"

def test_verify_cli_dry_run_is_offline(monkeypatch, capsys):
    """verify --dry-run is OFFLINE: no token resolution (a resolve_pit that
    would raise is never touched), no network, exit 0, plan surface only."""
    def _forbidden_pit():
        raise AssertionError("offline commands must never resolve a token")
    monkeypatch.setattr(reg, "resolve_pit", _forbidden_pit)
    rc = smsv.main(["verify", "--destination", DESTINATION,
                    "--message", MESSAGE_TEXT, "--dry-run"])
    assert rc == EX_OK, "verify --dry-run must exit 0, got %s" % rc
    assert "DRY RUN" in capsys.readouterr().err

def test_plan_cli_is_offline_and_read_only(monkeypatch, capsys):
    """plan is OFFLINE: no token resolution, no network, exit 0, and the
    plan surface names the send path and the masked destination only."""
    def _forbidden_pit():
        raise AssertionError("offline commands must never resolve a token")
    monkeypatch.setattr(reg, "resolve_pit", _forbidden_pit)
    rc = smsv.main(["plan", "--destination", DESTINATION,
                    "--message", MESSAGE_TEXT])
    assert rc == EX_OK, "plan must exit 0, got %s" % rc
    err = capsys.readouterr().err
    assert "DRY RUN" in err
    assert smsv.SEND_PATH in err
    assert "...23" in err
    assert DESTINATION not in err
    assert MESSAGE_TEXT not in err

def test_plan_cli_missing_destination_stops(monkeypatch):
    """plan without --destination STOPS (exit 2) — a plan never names an
    empty send."""
    def _forbidden_pit():
        raise AssertionError("offline commands must never resolve a token")
    monkeypatch.setattr(reg, "resolve_pit", _forbidden_pit)
    rc = smsv.main(["plan", "--message", MESSAGE_TEXT])
    assert rc == EX_STOP, "plan without --destination must STOP (exit 2)"

def test_self_test_cli_is_offline(monkeypatch):
    """self-test needs NO token and NO network — it runs with a resolve_pit
    that would raise if touched."""
    def _forbidden_pit():
        raise AssertionError("offline commands must never resolve a token")
    monkeypatch.setattr(reg, "resolve_pit", _forbidden_pit)
    assert smsv.main(["self-test"]) == EX_OK

# ---------------------------------------------------------------------------
# The module's own OFFLINE self-test battery (the house self-test
# convention: run as a process so a tamper never masquerades as exit 1),
# and the U23 sibling family stays green.
# ---------------------------------------------------------------------------
def test_module_self_test_battery_passes():
    """The module's own offline golden/attack battery must pass — the
    send-verification law is enforced HERE first, and a tamper never
    masquerades as exit 1."""
    proc = subprocess.run(
        [sys.executable, str(U23 / "sms_verifier.py"), "self-test"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == EX_OK, (
        "sms_verifier self-test FAILED (exit %d):\n%s\n%s"
        % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))

def test_self_test_is_offline_with_empty_environment():
    """The self-test must not touch the network — an EMPTY environment (no
    secrets, no proxy state) must still pass (it is pure)."""
    import os
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "SYSTEMROOT", "HOME", "PYTHONPATH")}
    proc = subprocess.run(
        [sys.executable, str(U23 / "sms_verifier.py"), "self-test"],
        capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == EX_OK, (
        "self-test must pass with an empty environment (exit %d):\n%s\n%s"
        % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))

def test_sibling_family_self_tests_stay_green():
    """The U23 sibling battery — the SMS phone provisioner — stays green,
    so the verifier is tested against a green family (a red sibling is
    caught HERE first)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "provision_sms_phone.py"), "self-test"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == EX_OK, (
        "provision_sms_phone self-test FAILED (exit %d):\n%s\n%s"
        % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
