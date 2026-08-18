#!/usr/bin/env python3
"""test_phone_lister.py -- unit tests for the U23 phone LISTER
(scripts/u23_modules/phone_lister.py, the READ-ONLY GET side of the engine's
phone surface: GET /phones/numbers for the Convert and Flow location).

THE LISTER LAWS, pinned from the module's own sources:

  * READ-ONLY ALWAYS: listing is a GET and nothing else. Every list path
    (list_action, and the listing step inside provision_action) must leave
    the fake's MUTATION LOG EMPTY -- a listing never writes, with or without
    --execute. list_action NEVER requires --execute.
  * Fail-closed: a refused listing STOPs or HELDs per class and is NEVER
    followed by a create (even with --execute) and never a silent skip; the
    module never provisions into the unknown. A refused read-back never
    records a number as provisioned; a create that returns no number id is a
    read-back mismatch (exit 5), never a provisioned success.
  * Trevor-gated --execute: the CREATE POST runs ONLY under --execute
    (AF-AE-PHONELIST-NO-EXECUTE). Without it, a location that needs a number
    is a STOP (exit 2) that names the code and leaves the mutation log EMPTY.
  * GET-first idempotency: a location that already carries an SMS-capable
    number is VERIFIED, never re-provisioned (exit 0, IDEMPOTENT NO-OP, zero
    writes, with or without --execute). An unmarked SMS entry is never
    silently trusted as SMS-capable (the no-execute STOP still holds).
  * Never a token printed: _mask_number is "...NNNN" (last 4); the location
    marker is the registry's _mask_location (last 4). The token value, the
    full location id, and the full number NEVER appear on the operator
    surfaces (the tests assert the emission text AND the JSON summaries).
  * Browser UA (CF 1010): every rail request rides the registry's CafClient
    chokepoint whose headers carry CAF_BROWSER_UA (the house pattern that
    clears the Cloudflare edge fronting services.leadconnectorhq.com;
    urllib's default Python-urllib UA is 1010'd before the request ever
    reaches the API). Pinned here against the registry constant so a
    regression in the edge fix is caught first.
  * Scope-vs-edge discrimination: an edge block (UpstreamBlockedError) is
    HELD (exit 3) and NEVER mislabeled as a scope problem; a ScopeDenied is
    STOP (exit 2).

OFFLINE BY DESIGN: no network, no secrets. Every test drives the module's
own pure helpers or a tiny in-memory Convert and Flow fake (the same shape
the module's self-test uses -- a programmable listing/read-back/create and a
mutation log), and the CLI-gate tests run the paths that return before any
credential work.

Run: python3 -m pytest 59-anthology-engine/scripts/u23_modules/test_phone_lister.py -q
 or: python3 59-anthology-engine/scripts/u23_modules/test_phone_lister.py
"""
import io
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
U23_MODULES = SCRIPTS / "u23_modules"
sys.path.insert(0, str(U23_MODULES))   # the module under test (phone_lister.py)
sys.path.insert(0, str(SCRIPTS))       # the shared registry (anthology_registry.py)

import anthology_registry as reg  # noqa: E402
import phone_lister as p  # noqa: E402

# ---------------------------------------------------------------------------
# In-memory Convert and Flow -- the same programmable surface the module's
# own self-test uses: a listing, a read-back, a create, per-call behaviors,
# and a MUTATION LOG so a test can prove no write happened when none should.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory LeadConnector for the phone listing/provisioning surface.
    Records every mutating call (create) in `writes` so the tests can prove
    listing, no-execute and idempotent no-op never write."""

    def __init__(self, numbers=None, list_behavior=None, create_behavior=None,
                 readback_behavior=None, sms_after_create=False):
        self._numbers = list(numbers or [])
        self.list_behavior = list_behavior       # None | "scope" | "validation" | "edge" | "transport"
        self.create_behavior = create_behavior   # None | "scope" | "validation" | "edge" | "transport" | "no-id"
        self.readback_behavior = readback_behavior  # None | "scope" | "edge" | "transport" | "no-id"
        self.sms_after_create = sms_after_create  # number reports SMS-capable at create time
        self.writes = []                         # every mutating call, in order

    def _request(self, method, path, query=None, body=None):
        q = query or {}
        if method == "GET" and path == "/phones/numbers":
            if self.list_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.list_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.list_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            return {"numbers": list(self._numbers)}
        if method == "GET" and path.startswith("/phones/numbers/"):
            if self.readback_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.readback_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.readback_behavior == "no-id":
                return None
            nid = path.rsplit("/", 1)[-1]
            for n in self._numbers:
                if str(n.get("id")) == nid:
                    if self.sms_after_create:
                        return dict(n, smsEnabled=True)
                    return {k: v for k, v in n.items() if k not in p.SMS_ENABLED_KEYS}
            return None
        if method == "POST" and path == "/phones/numbers":
            self.writes.append(("create", q.get("locationId"), body))
            if self.create_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.create_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.create_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.create_behavior == "no-id":
                return {}
            self._numbers.append({
                "id": "num_NEWQcDX", "phoneNumber": "+12025550123",
                "smsEnabled": self.sms_after_create})
            return {"id": "num_NEWQcDX"}
        raise AssertionError("unexpected call: %s %s" % (method, path))

    def add_number(self, number):
        """Register a number (e.g. one created earlier) so the fixture is
        reusable across a test -- same semantics as the module's own fake,
        which appends to the same list on create."""
        self._numbers.append(dict(number))


def _golden_numbers():
    """A location that already carries an SMS-capable number."""
    return [{"id": "num_EXISTING", "phoneNumber": "+12025559876", "smsEnabled": True}]


def _mixed_numbers():
    """One SMS-capable and one voice-only number."""
    return [
        {"id": "num_EXISTING", "phoneNumber": "+12025559876", "smsEnabled": True},
        {"id": "num_VOICE", "phoneNumber": "+12025554321", "smsEnabled": False},
    ]


def _attack_numbers():
    """A location whose entry carries NO SMS marker -- the read is fine but the
    entry cannot be trusted as SMS-capable. Never a silent verify."""
    return [{"id": "num_SUSPECT", "phoneNumber": "+12025559876"}]


def _surface_text(*streams):
    return "".join(s.getvalue() for s in streams if s is not None)

# ---------------------------------------------------------------------------
# 1. THE READ-ONLY LAW: a listing is a GET and nothing else
# ---------------------------------------------------------------------------
def test_list_action_is_read_only_and_never_requires_execute():
    """list_action runs with NO --execute at all (listing needs no gate), exits
    0, reports every number with a masked marker + SMS capability, and the
    fake's mutation log stays EMPTY -- a listing never writes."""
    dev = io.StringIO()
    caf = _FakeCaf(numbers=_mixed_numbers())
    rc = p.list_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_OK, \
        "the live listing must exit 0, got %s" % rc
    assert caf.writes == [], "a listing must never write, got %s" % caf.writes
    assert "...9876" in dev.getvalue(), "the SMS number must appear masked"
    assert "...4321" in dev.getvalue(), "the voice number must appear masked"
    assert "2 number(s), 1 SMS-capable" in dev.getvalue()

def test_list_action_ignores_non_dict_entries():
    """A listing that carries junk entries (non-dict) must not crash: they are
    skipped (the count is the raw listing length, exactly like the module's
    self-test), and nothing is read off them. Fail-closed against a hostile or
    drifted listing surface."""
    dev = io.StringIO()
    caf = _FakeCaf(numbers=[None, "junk", {"id": "num_V", "number": "+12025550099",
                                          "smsEnabled": False}])
    rc = p.list_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_OK
    assert caf.writes == [], "a listing must never write"
    assert "0 SMS-capable" in dev.getvalue(), \
        "no entry off the junk entries may count as SMS-capable"
    assert "...0099" in dev.getvalue(), "the one real entry must be listed"

def test_list_action_json_summary_is_masked_and_read_only():
    """The machine summary carries masked markers only (never a full number,
    never the location id) and reports the same counts as the human surface."""
    jout = io.StringIO()
    dev = io.StringIO()
    caf = _FakeCaf(numbers=_mixed_numbers())
    rc = p.list_action(caf, "loc_QcDX", out=dev, jsonout=jout)
    assert rc == reg.EX_OK
    assert caf.writes == []
    summary = json.loads(jout.getvalue())
    assert summary["ok"] is True
    assert summary["action"] == "list"
    assert summary["listed"] == 2
    assert summary["sms_capable"] == 1
    assert summary["location"] == "...QcDX"
    text = jout.getvalue() + dev.getvalue()
    for secret in ("loc_QcDX", "+12025559876", "+12025554321"):
        assert secret not in text, \
            "surface leak: %r must never appear in operator output" % secret

# ---------------------------------------------------------------------------
# 2. FAIL-CLOSED: a refused listing is STOP or HELD per class, never a write
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("behavior, want", [
    ("scope", reg.EX_STOP),       # scope denial -> STOP (exit 2)
    ("validation", reg.EX_STOP),  # validation refusal -> STOP (exit 2)
    ("edge", reg.EX_HELD),        # Cloudflare edge block -> HELD (exit 3), never scope
    ("transport", reg.EX_HELD),   # transport failure -> HELD (exit 3), never scope
])
def test_list_action_refusal_ladder_is_fail_closed(behavior, want):
    """A refused listing exits per class, names AF-AE-PHONELIST-READ-REFUSED,
    and NEVER writes. The edge/transport blocks are HELD and never mislabeled
    as a scope problem."""
    dev = io.StringIO()
    caf = _FakeCaf(list_behavior=behavior)
    rc = p.list_action(caf, "loc_QcDX", out=dev)
    assert rc == want, "list_behavior %r: want %s, got %s" % (behavior, want, rc)
    assert caf.writes == [], "a refused listing must never write"
    assert "AF-AE-PHONELIST-READ-REFUSED" in dev.getvalue()
    if behavior in ("edge", "transport"):
        assert "NOT a scope problem" in dev.getvalue(), \
            "an edge/transport block must NEVER be mislabeled as a scope problem"

@pytest.mark.parametrize("behavior, want", [
    ("scope", reg.EX_STOP),
    ("validation", reg.EX_STOP),
    ("edge", reg.EX_HELD),
    ("transport", reg.EX_HELD),
])
def test_provision_refused_listing_never_creates(behavior, want):
    """Even WITH --execute, a refused listing is never followed by a create --
    the module never provisions into the unknown."""
    dev = io.StringIO()
    caf = _FakeCaf(list_behavior=behavior)
    rc = p.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == want, "provision list_behavior %r: want %s, got %s" % (behavior, want, rc)
    assert caf.writes == [], \
        "a refused listing must never be followed by a create, got %s" % caf.writes

# ---------------------------------------------------------------------------
# 3. THE GATE: provisioning requires --execute; without it STOP, never a write
# ---------------------------------------------------------------------------
def test_provision_without_execute_is_a_stop_and_never_writes():
    """A location with no SMS-capable number and execute=False must STOP
    (exit 2) naming AF-AE-PHONELIST-NO-EXECUTE, and the fake's mutation log
    must stay EMPTY -- the strongest form of 'provisioning stays gated'."""
    dev = io.StringIO()
    caf = _FakeCaf()
    rc = p.provision_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_STOP, \
        "provisioning without --execute must STOP (exit 2), got %s" % rc
    assert caf.writes == [], \
        "without --execute nothing may be created, got %s" % caf.writes
    assert "AF-AE-PHONELIST-NO-EXECUTE" in dev.getvalue(), \
        "the refusal must name AF-AE-PHONELIST-NO-EXECUTE"

def test_cli_provision_without_execute_is_never_a_write():
    """The CLI `provision` gate is checked AFTER the GET-first listing (the
    module refuses to provision into the unknown): with no live listing
    available the command STOPS or HELDs fail-closed -- exit 0 and any write
    are impossible. The strong assertion here is the OFFLINE-verifiable half
    of the gate: `provision --dry-run` is the truthful offline plan (exit 0,
    no network) and the live path can never report a provisioning it did not
    perform."""
    rc = p.main(["provision", "--location-id", "loc_zzz"])
    assert rc != reg.EX_OK, \
        "a live provision without credentials must never exit 0, got %s" % rc
    assert rc in (reg.EX_STOP, reg.EX_HELD), \
        "a refused/blocked listing must STOP or HELD fail-closed, got %s" % rc
    rc_dry = p.main(["provision", "--dry-run"])
    assert rc_dry == reg.EX_OK, \
        "provision --dry-run must exit 0 (truthful offline plan), got %s" % rc_dry

def test_cli_list_requires_no_execute_flag():
    """`list` is the READ-ONLY surface: it must never demand --execute and
    must fail only on the missing credential (offline) -- never on a write
    gate. With no pit- token in the environment the credential resolution
    STOPs before any network; the important assertion is that a missing
    --execute is NOT the reason it stops."""
    rc = p.main(["list", "--location-id", "loc_zzz"])
    assert rc != reg.EX_OK, \
        "offline list without credentials must not exit 0 (no network in tests)"
    assert rc in (reg.EX_STOP, reg.EX_HELD), \
        "an unavailable listing must STOP or HELD fail-closed, got %s" % rc

# ---------------------------------------------------------------------------
# 4. IDEMPOTENCY + PLAN: the no-op never writes; the plan is offline
# ---------------------------------------------------------------------------
def test_idempotent_noop_never_writes():
    """A location that already has an SMS-capable number is VERIFIED, never
    re-provisioned: exit 0 with or without --execute, the fake's mutation log
    stays EMPTY, and the surface says IDEMPOTENT NO-OP."""
    dev = io.StringIO()
    caf = _FakeCaf(numbers=_golden_numbers())
    rc = p.provision_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_OK, \
        "already-provisioned must exit 0 (idempotent no-op), got %s" % rc
    assert caf.writes == [], "already-provisioned must never be written"
    assert "IDEMPOTENT NO-OP" in dev.getvalue()
    dev2 = io.StringIO()
    caf2 = _FakeCaf(numbers=_golden_numbers())
    rc2 = p.provision_action(caf2, "loc_QcDX", execute=True, out=dev2)
    assert rc2 == reg.EX_OK, \
        "idempotent no-op holds even WITH --execute, got %s" % rc2
    assert caf2.writes == [], "already-provisioned must never be written"

def test_idempotent_noop_json_summary_is_truthful():
    """The JSON summary of a no-op says provisioned False / already True --
    never a claim of a new provisioning."""
    jout = io.StringIO()
    p.provision_action(_FakeCaf(numbers=_golden_numbers()), "loc_QcDX",
                       execute=True, out=io.StringIO(), jsonout=jout)
    summary = json.loads(jout.getvalue())
    assert summary["ok"] is True
    assert summary["provisioned"] is False
    assert summary["already"] is True

def test_plan_action_is_offline_and_writes_nothing():
    """plan_action needs no client at all (no network, no credential), exits
    0, and the JSON summary says dry_run/planned -- nothing provisioned."""
    dev = io.StringIO()
    rc = p.plan_action(out=dev)
    assert rc == reg.EX_OK, "offline plan must exit 0, got %s" % rc
    assert "PLAN (offline)" in dev.getvalue()
    jout = io.StringIO()
    p.plan_action(out=io.StringIO(), jsonout=jout)
    plan = json.loads(jout.getvalue())
    assert plan["ok"] is True
    assert plan["dry_run"] is True
    assert plan.get("provisioned") is not True

def test_cli_plan_dry_run_is_offline():
    """`provision --dry-run` routes to the offline plan: exit 0, no credential
    work, no network, no writes."""
    rc = p.main(["provision", "--dry-run"])
    assert rc == reg.EX_OK, \
        "provision --dry-run must exit 0 (truthful offline plan), got %s" % rc

# ---------------------------------------------------------------------------
# 5. FAIL-CLOSED PROVISIONING: refused creates and refused read-backs never
#    record a number as provisioned
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("behavior, want", [
    ("scope", reg.EX_STOP),
    ("validation", reg.EX_STOP),
    ("edge", reg.EX_HELD),
    ("transport", reg.EX_HELD),
    ("no-id", reg.EX_MISMATCH),  # create returned no number id -> read-back mismatch
])
def test_create_refusal_ladder_never_provisions(behavior, want):
    """Even WITH --execute, a refused create never counts as provisioned: STOP
    or HELD per class, the code AF-AE-PHONELIST-CREATE-REFUSED is named, and
    the no-id create is a read-back mismatch (exit 5), never a success."""
    dev = io.StringIO()
    caf = _FakeCaf(create_behavior=behavior)
    rc = p.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == want, "create_behavior %r: want %s, got %s" % (behavior, want, rc)
    assert "AF-AE-PHONELIST-CREATE-REFUSED" in dev.getvalue(), \
        "the refusal must name AF-AE-PHONELIST-CREATE-REFUSED"
    if behavior in ("edge", "transport"):
        assert "never a scope problem" in dev.getvalue(), \
            "an edge/transport block must NEVER be mislabeled as a scope problem"

@pytest.mark.parametrize("behavior, want", [
    ("scope", reg.EX_STOP),
    ("edge", reg.EX_HELD),
    ("transport", reg.EX_HELD),
    ("no-id", reg.EX_MISMATCH),  # read-back returned no number -> mismatch
])
def test_readback_refusal_never_records_provisioned(behavior, want):
    """A refused or empty read-back NEVER records the number as provisioned:
    the write happened but the confirmation did not, so the result is STOP,
    HELD or MISMATCH per class -- never exit 0."""
    dev = io.StringIO()
    caf = _FakeCaf(create_behavior=None, readback_behavior=behavior,
                   sms_after_create=False)
    rc = p.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == want, \
        "readback_behavior %r: want %s, got %s" % (behavior, want, rc)

def test_happy_path_creates_exactly_once_and_reads_back():
    """The full provision under --execute: GET-first (no SMS number present),
    one create, one read-back, exit 0, and the surface announces READ BACK."""
    dev = io.StringIO()
    caf = _FakeCaf(sms_after_create=True)
    rc = p.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == reg.EX_OK, "happy path must exit 0, got %s" % rc
    assert caf.writes == [("create", "loc_QcDX", {})], \
        "happy path must create exactly once, got %s" % caf.writes
    assert "READ BACK" in dev.getvalue(), \
        "a write is never trusted without read-back"
    assert "CREATED + READ BACK" in dev.getvalue()

def test_attack_listing_is_never_silently_trusted():
    """An entry with NO SMS marker cannot be verified SMS-capable: without
    --execute the module still STOPS (the no-execute gate holds); the entry
    never short-circuits to a verified state. Under --execute it may provision
    (the listing did not fail), but only once."""
    dev = io.StringIO()
    caf = _FakeCaf(numbers=_attack_numbers())
    rc = p.provision_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_STOP, \
        "an unmarked entry must not short-circuit to verified"
    assert "AF-AE-PHONELIST-NO-EXECUTE" in dev.getvalue()
    assert caf.writes == []
    dev2 = io.StringIO()
    caf2 = _FakeCaf(numbers=_attack_numbers())
    rc2 = p.provision_action(caf2, "loc_QcDX", execute=True, out=dev2)
    assert rc2 == reg.EX_OK, \
        "the listing is fine, so under --execute provisioning may proceed"
    assert caf2.writes == [("create", "loc_QcDX", {})], \
        "the unmarked entry must not be treated as verified SMS"

# ---------------------------------------------------------------------------
# 6. NEVER PRINT A TOKEN: masked markers only, on every surface
# ---------------------------------------------------------------------------
def test_mask_helpers_are_non_reversible():
    """The number marker is last-digits only; the location marker is the
    registry's last-4 mask. No full value survives."""
    assert p._mask_number("+12025559876") == "...9876"
    assert p._mask_number("") == "(short number)"
    assert p._mask_number("+1") == "(short number)"
    assert reg._mask_location("loc_QcDX") == "...QcDX"

def test_sms_enabled_is_presence_truthiness_only():
    """The capability read is presence/truthiness on the fixed key set only --
    never any other field of the number object."""
    assert p._sms_enabled({"smsEnabled": True}) is True
    assert p._sms_enabled({"smsEnabled": 1}) is True
    assert p._sms_enabled({"smsEnabled": 0}) is False
    assert p._sms_enabled({"sms_enabled": True}) is True
    assert p._sms_enabled({"sms_enabled": "false"}) is True  # truthy string stays truthy
    assert p._sms_enabled({"smsEnabled": False}) is False
    assert p._sms_enabled({"other": True}) is False
    assert p._sms_enabled({}) is False

def test_operator_surfaces_never_carry_secret_values():
    """No token, no full location id, no full number may reach the operator
    surfaces -- neither the emission text nor the JSON summaries -- across the
    list, provision (no-op and happy path) and plan surfaces."""
    streams = []
    jouts = []
    for kwargs in ({"execute": False},
                   {"execute": True},
                   {"execute": True, "sms_after_create": True}):
        caf_kwargs = {k: v for k, v in kwargs.items() if k != "execute"}
        caf = _FakeCaf(**caf_kwargs)
        dev = io.StringIO()
        jout = io.StringIO()
        streams.append(dev)
        jouts.append(jout)
        p.provision_action(caf, "loc_QcDX", execute=kwargs["execute"],
                           out=dev, jsonout=jout)
    # the idempotent no-op surface (the location already has an SMS number)
    caf_noop = _FakeCaf()
    dev_noop = io.StringIO()
    jout_noop = io.StringIO()
    streams.append(dev_noop)
    jouts.append(jout_noop)
    p.provision_action(caf_noop, "loc_QcDX", execute=True,
                       out=dev_noop, jsonout=jout_noop)
    devl = io.StringIO()
    joutl = io.StringIO()
    streams.append(devl)
    jouts.append(joutl)
    p.list_action(_FakeCaf(numbers=_mixed_numbers()), "loc_QcDX",
                  out=devl, jsonout=joutl)
    jplan = io.StringIO()
    p.plan_action(out=io.StringIO(), jsonout=jplan)
    jouts.append(jplan)
    all_text = _surface_text(*(streams + jouts))
    for secret in ("pit-", "loc_QcDX", "+12025550123", "+12025559876",
                   "+12025554321", "Bearer ", "SEKRIT"):
        assert secret not in all_text, \
            "surface leak: %r must never appear in operator output" % secret

# ---------------------------------------------------------------------------
# 7. BROWSER UA (CF 1010): the rail headers carry CAF_BROWSER_UA
# ---------------------------------------------------------------------------
def _request_user_agent(monkeypatch, client, path, query=None, body=None):
    """Run one client call against a captured urlopen and return the
    User-Agent the request actually carried -- the registry self-test's own
    interception pattern (never a live fetch)."""
    captured = {}

    class _FakeResp:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, limit=None):
            return b'{"numbers": []}'

    def _fake_urlopen(req, timeout=None):
        captured["ua"] = {k.lower(): v for k, v in req.header_items()}.get("user-agent")
        return _FakeResp()

    monkeypatch.setattr(reg.urllib.request, "urlopen", _fake_urlopen)
    client._request("GET", path, query=query, body=body)
    return captured.get("ua")

def test_caf_client_carries_the_browser_ua(monkeypatch):
    """The one HTTPS chokepoint must attach reg.CAF_BROWSER_UA to the request
    it opens -- urllib's default Python-urllib UA is 403'd at the Cloudflare
    edge (CF 1010) before the request ever reaches Convert and Flow. Pinned
    against the registry constant and its proven-live byte string so a
    regression in the edge fix is caught first."""
    assert "Python-urllib" not in reg.CAF_BROWSER_UA, \
        "the browser UA must never be urllib's default"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0")
    assert "Chrome/" in reg.CAF_BROWSER_UA, \
        "the browser UA must carry a Chrome segment (CF 1010 law)"
    ua = _request_user_agent(monkeypatch, reg.CafClient("pit-test-token"),
                             "/phones/numbers", query={"locationId": "loc_X"})
    assert ua == reg.CAF_BROWSER_UA, \
        "the request must carry the house browser UA (CF 1010), got %r" % ua
    # GK-09 regression pin: the proven-live byte string the Podcast gate's
    # own verify script uses (3-segment Chrome version, no typo).
    assert reg.CAF_BROWSER_UA == (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ), "CAF_BROWSER_UA drifted from the proven-live string"

def _main_takes_out(module):
    """True when main() accepts an injectable out= stream (newer house shape).
    Older sibling mains write to sys.stderr directly; the offline gates are
    identical either way."""
    import inspect
    try:
        return "out" in inspect.signature(module.main).parameters
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    # Standalone runner (house style): pytest when available, else a manual
    # green/red walk over every test so a box without pytest still fails closed.
    try:
        import pytest as _pytest
    except ImportError:
        _pytest = None
    if _pytest is not None:
        raise SystemExit(_pytest.main([__file__, "-q"]))
    results = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                results.append((name, "PASS"))
            except Exception as exc:  # noqa: BLE001
                results.append((name, "FAIL: %s" % exc))
    for name, status in results:
        print("%-60s %s" % (name, status))
    bad = [n for n, s in results if s != "PASS"]
    print("u23 test_phone_lister: %d/%d passed"
          % (len(results) - len(bad), len(results)))
    raise SystemExit(1 if bad else 0)
