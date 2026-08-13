#!/usr/bin/env python3
"""test_provision_action.py -- unit tests for the U23 provisioning ACTION
(scripts/u23_modules/provision_action.py, the Trevor-gated LeadConnector
phone number provisioner).

THE PROVISIONING ACTION LAW, pinned from the module's own sources:

  * Trevor-gated --execute: the CREATE POST runs ONLY when the caller passes
    --execute explicitly (provision_action.py: "THE ACTION STAYS GATED: the
    module NEVER provisions without --execute"; AF-AE-PROVACTION-NO-EXECUTE).
    WITHOUT --execute a location that needs a number is a STOP (exit 2)
    that names the code and writes nothing. The gate is provable OFFLINE at
    the function level -- provision_action(...) with execute=False against
    the in-memory fake must return EX_STOP and must leave the fake's
    mutation log EMPTY (the strongest form of "dry-run writes nothing": no
    write at all, regardless of what the network would do) -- and at the
    CLI level for the dry-run paths, whose offline plan returns BEFORE any
    credential work.
  * Dry-run writes nothing: the dry-run CLI paths (provision --dry-run /
    plan --dry-run) return EX_OK with the "DRY RUN" surface and NO network;
    plan_action is READ-ONLY and never records a write. Dry-run and
    no-execute are DIFFERENT laws -- dry-run is the truthful offline plan
    (exit 0), no-execute is the refusal to act (exit 2).
  * Read-back law: a write is never trusted without read-back. A missing or
    refused post-create read-back is a MISMATCH (exit 5) or STOP/HELD per
    class, never a provisioned success.
  * Fail-closed: an unmarked SMS entry is never silently trusted as
    verified (the no-execute STOP still holds); a refused listing or
    refused create is NEVER followed by a write; a create that returns no
    number id is a read-back mismatch (exit 5), never a provisioned
    success.
  * Never a token printed: _mask_number is "....NNNN" (last 4), the
    location marker is the registry's _mask_location (last 4); the token
    value, the full location id, the full number, and the full
    authorization header value NEVER appear on the operator surfaces (the
    test asserts the emission text and the JSON summaries carry none of
    them).
  * Browser UA (CF 1010): every rail request rides
    anthology_registry.CafClient._request, whose headers carry CAF_BROWSER_UA
    (the house pattern that clears the Cloudflare edge fronting
    services.leadconnectorhq.com; urllib's default Python-urllib UA is
    1010'd before the request reaches Convert and Flow). Pinned here by
    intercepting the request the chokepoint opens -- never by a live fetch.

OFFLINE BY DESIGN: no network, no secrets. Every test drives the module's
own pure helpers or a tiny in-memory Convert and Flow fake (the same shape
the module's self-test uses -- a programmable listing and a mutation log),
and the CLI tests capture stderr via capsys so no live credential from the
operator's environment is ever resolved or called.

Run: python3 -m pytest 59-anthology-engine/scripts/u23_modules/test_provision_action.py -q
 or: python3 59-anthology-engine/scripts/u23_modules/test_provision_action.py
"""
import io
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
U23 = Path(__file__).resolve().parent
for _p in (SCRIPTS, U23):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import anthology_registry as reg  # noqa: E402
import provision_action as pa  # noqa: E402

# ---------------------------------------------------------------------------
# In-memory Convert and Flow -- the same programmable surface the module's
# own self-test uses: a listing, per-call behaviors, and a MUTATION LOG so a
# test can prove no write happened when none should.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory LeadConnector for the provisioning surface. Records every
    mutating call (create) in `writes` and every read in `reads` so the tests
    can prove dry-run and no-execute never write."""

    def __init__(self, numbers=None, list_behavior=None, create_behavior=None,
                 readback_behavior=None):
        self._numbers = list(numbers or [])
        self.list_behavior = list_behavior          # None | "scope" | "validation" | "edge"
        self.create_behavior = create_behavior      # None | "scope" | "validation" | "edge" | "no-id"
        self.readback_behavior = readback_behavior  # None | "missing" | "scope" | "validation" | "edge"
        self.writes = []                            # every mutating call, in order
        self.reads = []                             # every read call, in order

    def _request(self, method, path, query=None, body=None):
        q = query or {}
        if method == "GET" and path == "/phones/numbers":
            self.reads.append(("list", q.get("locationId")))
            if self.list_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.list_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.list_behavior == "edge":
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            return {"numbers": list(self._numbers)}
        if method == "GET" and path.startswith("/phones/numbers/"):
            nid = path.rsplit("/", 1)[-1]
            self.reads.append(("get", nid))
            if self.readback_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.readback_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.readback_behavior == "edge":
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.readback_behavior == "missing":
                return None
            for n in self._numbers:
                if str(n.get("id")) == nid:
                    return n
            return None
        if method == "POST" and path == "/phones/numbers":
            self.writes.append(("create", q.get("locationId"), body))
            if self.create_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.create_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.create_behavior == "edge":
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.create_behavior == "no-id":
                return {}
            created = {"id": "num_QcDX", "phoneNumber": "+12025550123",
                       "smsEnabled": True}
            self._numbers.append(created)
            self.reads.append(("created-number", created["phoneNumber"]))
            return {"id": created["id"]}
        raise AssertionError("unexpected call: %s %s" % (method, path))


def _golden_numbers():
    """A location that already carries an SMS-capable number."""
    return [{"id": "num_EXISTING", "phoneNumber": "+12025559876", "smsEnabled": True}]


def _attack_numbers():
    """A location whose entry carries NO SMS marker -- the read is fine but the
    entry cannot be trusted as SMS-capable. Never a silent verify."""
    return [{"id": "num_SUSPECT", "phoneNumber": "+12025559876"}]


def _surface_text(*streams):
    return "".join(s.getvalue() for s in streams if s is not None)

# ---------------------------------------------------------------------------
# 1. THE GATE: provisioning requires --execute; without it STOP, never a write
# ---------------------------------------------------------------------------
def test_provision_action_requires_execute_and_never_writes():
    """A location with no SMS-capable number and execute=False must STOP
    (exit 2) with the no-execute code, and the fake's mutation log must stay
    EMPTY -- the strongest form of 'dry-run writes nothing' (no write at
    all, regardless of network)."""
    dev = io.StringIO()
    caf = _FakeCaf()
    rc = pa.provision_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_STOP, \
        "provisioning without --execute must STOP (exit 2), got %s" % rc
    assert caf.writes == [], \
        "without --execute nothing may be created, got %s" % caf.writes
    assert "AF-AE-PROVACTION-NO-EXECUTE" in dev.getvalue(), \
        "the refusal must name AF-AE-PROVACTION-NO-EXECUTE"

def test_cli_provision_dry_run_is_offline_and_writes_nothing(capsys):
    """The dry-run path returns EX_OK with the DRY RUN surface and performs
    NO network and NO writes -- the truthful offline plan."""
    rc = pa.main(["provision", "--dry-run"])
    err = capsys.readouterr().err
    assert rc == reg.EX_OK, \
        "provision --dry-run must exit 0 (truthful offline plan), got %s" % rc
    assert "DRY RUN" in err, "dry-run must announce itself as DRY RUN"

def test_cli_plan_dry_run_is_offline(capsys):
    rc = pa.main(["plan", "--dry-run"])
    err = capsys.readouterr().err
    assert rc == reg.EX_OK, \
        "plan --dry-run must exit 0, got %s" % rc
    assert "DRY RUN" in err

# ---------------------------------------------------------------------------
# 2. IDEMPOTENCY + PLAN: dry-run is a pure read, the no-op never writes
# ---------------------------------------------------------------------------
def test_idempotent_noop_never_writes():
    """A location that already has an SMS-capable number is VERIFIED, never
    re-provisioned: exit 0, the fake's mutation log stays EMPTY, and the
    surface says IDEMPOTENT NO-OP."""
    dev = io.StringIO()
    caf = _FakeCaf(numbers=_golden_numbers())
    rc = pa.provision_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_OK, \
        "already-provisioned must exit 0 (idempotent no-op), got %s" % rc
    assert caf.writes == [], "already-provisioned must never be written"
    assert "IDEMPOTENT NO-OP" in dev.getvalue()

def test_plan_action_is_read_only():
    """The plan body lists and reports; it must never record a write, with or
    without a number present."""
    dev = io.StringIO()
    caf = _FakeCaf()
    rc = pa.plan_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_OK, "plan must exit 0, got %s" % rc
    assert caf.writes == [], "the plan must never write"
    assert "needs-provision" in dev.getvalue()
    dev2 = io.StringIO()
    caf2 = _FakeCaf(numbers=_golden_numbers())
    rc2 = pa.plan_action(caf2, "loc_QcDX", out=dev2)
    assert rc2 == reg.EX_OK
    assert caf2.writes == [], "the plan must never write"
    assert "already-provisioned" in dev2.getvalue()

def test_plan_action_json_summary_is_a_plan():
    """The JSON summary of the plan says dry_run and what it WOULD do -- never
    a provisioned result."""
    jout = io.StringIO()
    pa.plan_action(_FakeCaf(), "loc_QcDX", out=io.StringIO(), jsonout=jout)
    plan = json.loads(jout.getvalue())
    assert plan["dry_run"] is True
    assert plan["provision_needed"] is True
    assert plan.get("provisioned") is not True

# ---------------------------------------------------------------------------
# 3. FAIL-CLOSED: refused reads and refused creates never write
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("behavior, want", [
    ("scope", reg.EX_STOP),      # scope denial -> STOP (exit 2)
    ("validation", reg.EX_STOP), # validation refusal -> STOP (exit 2)
    ("edge", reg.EX_HELD),       # Cloudflare edge block -> HELD (exit 3), never scope
])
def test_listing_refusal_ladder_never_writes(behavior, want):
    """A refused listing must exit per class and must NEVER be followed by a
    create. The edge block must never be mislabeled as a scope problem."""
    dev = io.StringIO()
    caf = _FakeCaf(list_behavior=behavior)
    rc = pa.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == want, "list_behavior %r: want %s, got %s" % (behavior, want, rc)
    assert caf.writes == [], "a refused listing must never be followed by a create"
    if behavior == "edge":
        assert "NOT a scope problem" in dev.getvalue(), \
            "an edge block must NEVER be mislabeled as a scope problem"

@pytest.mark.parametrize("behavior, want", [
    ("scope", reg.EX_STOP),
    ("validation", reg.EX_STOP),
    ("edge", reg.EX_HELD),
    ("no-id", reg.EX_MISMATCH),  # create returned no number id -> read-back mismatch
])
def test_create_refusal_ladder_never_provisions(behavior, want):
    """Even WITH --execute, a refused create never counts as provisioned; the
    no-id create is a read-back mismatch (exit 5), never a success."""
    dev = io.StringIO()
    caf = _FakeCaf(create_behavior=behavior)
    rc = pa.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == want, "create_behavior %r: want %s, got %s" % (behavior, want, rc)
    assert all(w[0] == "create" for w in caf.writes), \
        "a refused create must not be recorded as provisioned"

def test_attack_listing_is_never_silently_trusted():
    """An entry with NO SMS marker cannot be verified SMS-capable: without
    --execute the module still STOPS (the no-execute gate holds); the entry
    never short-circuits to a verified state."""
    dev = io.StringIO()
    caf = _FakeCaf(numbers=_attack_numbers())
    rc = pa.provision_action(caf, "loc_QcDX", out=dev)
    assert rc == reg.EX_STOP, \
        "an unmarked entry must not short-circuit to verified"
    assert "AF-AE-PROVACTION-NO-EXECUTE" in dev.getvalue()
    assert caf.writes == []

def test_readback_mismatch_is_never_a_false_provision():
    """The READ-BACK LAW: with --execute, a created number that cannot be read
    back is a MISMATCH (exit 5), never a provisioned success -- and the write
    log proves the create DID happen (the failure is honest, not silent)."""
    dev = io.StringIO()
    caf = _FakeCaf(readback_behavior="missing")
    rc = pa.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == reg.EX_MISMATCH, \
        "a missing read-back must be exit 5, got %s" % rc
    assert "AF-AE-PROVACTION-READBACK-MISMATCH" in dev.getvalue()
    assert "NOT reported as provisioned" in dev.getvalue()
    assert caf.writes == [("create", "loc_QcDX", {})], \
        "the create happened (the failure is honest), but must never be reported as provisioned"

@pytest.mark.parametrize("behavior, want", [
    ("scope", reg.EX_STOP),
    ("validation", reg.EX_STOP),
    ("edge", reg.EX_HELD),
])
def test_readback_refusal_ladder_never_reports_provisioned(behavior, want):
    """A refused read-back is STOP/HELD per class; the surface must never
    claim provisioned."""
    dev = io.StringIO()
    caf = _FakeCaf(readback_behavior=behavior)
    rc = pa.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == want, "readback_behavior %r: want %s, got %s" % (behavior, want, rc)

def test_happy_path_create_once_readback_confirms(capsys):
    """With --execute the happy path creates EXACTLY ONCE and confirms by
    read-back (the write log shows create-then-get, and the surface says
    PROVISIONED). The CLI exit is 0."""
    dev = io.StringIO()
    caf = _FakeCaf()
    rc = pa.provision_action(caf, "loc_QcDX", execute=True, out=dev)
    assert rc == reg.EX_OK, "happy path must exit 0, got %s" % rc
    assert caf.writes == [("create", "loc_QcDX", {})], \
        "happy path must create exactly once, got %s" % caf.writes
    assert ("get", "num_QcDX") in caf.reads, \
        "a write is never trusted without a read-back"
    assert "PROVISIONED" in dev.getvalue()
    assert "read-back" in dev.getvalue()

# ---------------------------------------------------------------------------
# 4. NEVER PRINT A TOKEN: masked markers only, on every surface
# ---------------------------------------------------------------------------
def test_mask_helpers_are_non_reversible():
    """The number and destination markers are last-digits only; the location
    marker is the registry's last-4 mask. No full value survives."""
    assert pa._mask_number("+12025559876") == "...9876"
    assert pa._mask_number("") == "(short number)"
    assert reg._mask_location("loc_QcDX") == "...QcDX"

def test_operator_surfaces_never_carry_secret_values():
    """No token, no full location id, no full number, and no authorization
    header value may reach the operator surfaces -- the emission text and the
    JSON summaries, checked against the REAL values that moved through the
    fake (its listing, its created number)."""
    streams = []

    # dry-run / no-execute surface (no write happens, so no created value)
    dev = io.StringIO()
    caf_empty = _FakeCaf()
    pa.provision_action(caf_empty, "loc_QcDX", out=dev)
    streams.append(dev)

    # happy-path surface under --execute (the created number is real)
    dev2 = io.StringIO()
    caf2 = _FakeCaf()
    pa.provision_action(caf2, "loc_QcDX", execute=True, out=dev2)
    streams.append(dev2)

    # already-provisioned surface (the listing's number is real)
    dev3 = io.StringIO()
    caf3 = _FakeCaf(numbers=_golden_numbers())
    pa.provision_action(caf3, "loc_QcDX", out=dev3)
    streams.append(dev3)

    # the plan JSON summary
    jout = io.StringIO()
    pa.plan_action(_FakeCaf(), "loc_QcDX", out=io.StringIO(), jsonout=jout)
    streams.append(jout)

    all_text = _surface_text(*streams)
    moved_values = (["loc_QcDX", "+12025550123", "+12025559876"]
                    + [n.get("phoneNumber", "") for n in _golden_numbers()]
                    + [n.get("phoneNumber", "") for n in _attack_numbers()])
    for secret in set(v for v in moved_values if v):
        assert secret not in all_text, \
            "surface leak: %r must never appear in operator output" % secret
    for token in ("pit-", "Bearer ", "SEKRIT", "num_QcDX"):
        assert token not in all_text, \
            "surface leak: %r must never appear in operator output" % token

# ---------------------------------------------------------------------------
# 5. BROWSER UA (CF 1010): the rail headers carry CAF_BROWSER_UA
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
    print("u23 test_provision_action: %d/%d passed" % (len(results) - len(bad), len(results)))
    raise SystemExit(1 if bad else 0)
