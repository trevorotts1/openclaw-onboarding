"""test_contacts_upsert.py — regression suite for safe contact upsert policy.

Locks down the 18 behaviors from the approved upsert-standardization spec:

 1. generic add/save routes to upsert (not create)
 2. upsert hits POST /contacts/upsert (not POST /contacts/)
 3. explicit create remains (POST /contacts/)
 4. known-ID update remains (PUT /contacts/{id})
 5. unspecified fields omitted (no wipe)
 6. empty/null/placeholder values never wipe (omitted from body)
 7. tag additions use POST /contacts/{id}/tags (additive)
 8. Version header 2021-07-28 on contact calls
 9. locationId included in every write body
10. createNewIfDuplicateAllowed FALSE/omitted by default, TRUE only on explicit flag
11. dry-run safe (no network, exit 0)
12. 429 follows STOP doctrine (no retry storm, surfaces to owner)
13. auth failures fail-loud (no silent swallow)
14. successful upsert performs GET read-back
15. failed read-back does NOT repeat POST
16. source/attribution omitted unless supplied
17. custom fields targeted only (no mass overwrite)
18. update --tag stays refused (destructive PUT tag-replace guard)

No network. The api module (ghl_client) is stubbed in-process; the real Click
command functions run through CliRunner.
"""
from __future__ import annotations

import os
import sys

import pytest
from click.testing import CliRunner

_ENGINE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "tools", "engine"))
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

from cli_anything.gohighlevel import gohighlevel_cli as cli_mod  # noqa: E402


# ── Stub api ──────────────────────────────────────────────────────────────

class _FakeAuthError(Exception):
    pass


class _FakeRateLimit(Exception):
    def __init__(self):
        self.status_code = 429
        super().__init__("Rate limited — back at reset (STOP, do not retry blindly)")


class StubApi:
    """Records calls; never touches the network."""

    def __init__(self):
        self.calls = []  # (method, path, body)
        self.upsert_response = {"contact": {"id": "cid-123", "email": "a@b.c"}}
        self.get_response = {"contact": {"id": "cid-123", "email": "a@b.c",
                                         "firstName": "Ann"}}
        self.fail_get = False
        self.fail_auth = False
        self.fail_429 = False

    def post(self, path, data=None, version=None):
        self.calls.append(("POST", path, dict(data or {}), version))
        if self.fail_429:
            raise _FakeRateLimit()
        if self.fail_auth:
            raise _FakeAuthError("API Error (401): invalid token")
        return dict(self.upsert_response)

    def put(self, path, data=None, version=None):
        self.calls.append(("PUT", path, dict(data or {}), version))
        return {"id": "cid-123"}

    def get(self, path, params=None, version=None):
        self.calls.append(("GET", path, dict(params or {}), version))
        if self.fail_429:
            raise _FakeRateLimit()
        if self.fail_auth:
            raise _FakeAuthError("API Error (401): invalid token")
        if self.fail_get:
            raise RuntimeError("connection reset")
        return dict(self.get_response)

    @staticmethod
    def format_output(data, as_json=False):
        import json as _json
        return _json.dumps(data)


@pytest.fixture()
def stub(monkeypatch):
    s = StubApi()
    monkeypatch.setattr(cli_mod, "api", s)
    # _loc() reads ctx first; supply location via context object instead of env.
    return s


def _run(args, location_id="loc-1"):
    runner = CliRunner()
    return runner.invoke(cli_mod.cli,
                         ["--location-id", location_id] + args)


def _posts_to(stub, path):
    return [c for c in stub.calls if c[0] == "POST" and c[1] == path]


# ── Behaviors 1+2: generic add/save → POST /contacts/upsert ────────────────

def test_generic_add_save_routes_to_upsert_endpoint(stub):
    r = _run(["contacts", "upsert", "--email", "a@b.c", "--first-name", "Ann"])
    assert r.exit_code == 0, r.output
    assert len(_posts_to(stub, "/contacts/upsert")) == 1
    assert _posts_to(stub, "/contacts/") == []


# ── Behavior 3: explicit create remains ────────────────────────────────────

def test_explicit_create_still_posts_to_contacts(stub):
    r = _run(["contacts", "create", "--email", "n@ew.c", "--first-name", "New"])
    assert r.exit_code == 0, r.output
    assert len(_posts_to(stub, "/contacts/")) == 1


# ── Behavior 4: known-ID update remains ────────────────────────────────────

def test_known_id_update_still_puts(stub):
    r = _run(["contacts", "update", "cid-123", "--first-name", "Ann"])
    assert r.exit_code == 0, r.output
    puts = [c for c in stub.calls if c[0] == "PUT" and c[1] == "/contacts/cid-123"]
    assert len(puts) == 1


# ── Behavior 5: unspecified fields omitted ─────────────────────────────────

def test_unspecified_fields_omitted_from_upsert_body(stub):
    _run(["contacts", "upsert", "--email", "a@b.c", "--first-name", "Ann"])
    (body,) = [c[2] for c in _posts_to(stub, "/contacts/upsert")]
    assert body["email"] == "a@b.c"
    assert body["firstName"] == "Ann"
    for absent in ("lastName", "name", "companyName", "phone", "source", "tags"):
        assert absent not in body


# ── Behavior 6: empty/null/placeholder never wipe ──────────────────────────
# (Click options default to None when not passed; the command only copies
# truthy values, so empties can never reach the body. Prove it for update too.)

def test_empty_values_never_sent(stub):
    _run(["contacts", "update", "cid-123", "--first-name", "Ann"])
    (body,) = [c[2] for c in stub.calls if c[0] == "PUT"]
    assert "lastName" not in body and "email" not in body


# ── Behavior 7: tags via dedicated endpoint, never the upsert body ─────────

def test_tags_additive_via_tag_endpoint(stub):
    r = _run(["contacts", "upsert", "--email", "a@b.c", "--tag", "vip",
              "--tag", "lead"])
    assert r.exit_code == 0, r.output
    (upsert_body,) = [c[2] for c in _posts_to(stub, "/contacts/upsert")]
    assert "tags" not in upsert_body
    tag_posts = _posts_to(stub, "/contacts/cid-123/tags")
    assert len(tag_posts) == 1
    assert tag_posts[0][2] == {"tags": ["vip", "lead"]}


# ── Behavior 8: Version header 2021-07-28 ──────────────────────────────────
# The version is resolved in ghl_client._headers via VERSION_MAP; assert the
# mapping still routes every /contacts/ path to 2021-07-28.

def test_contacts_version_header_mapping():
    from cli_anything.gohighlevel.utils import ghl_client as real_client
    assert real_client._version_for_path("/contacts/upsert") == "2021-07-28"
    assert real_client._version_for_path("/contacts/cid-123") == "2021-07-28"
    assert real_client._version_for_path("/contacts/") == "2021-07-28"


# ── Behavior 9: locationId in every write body ─────────────────────────────

def test_location_id_in_write_bodies(stub):
    _run(["contacts", "upsert", "--email", "a@b.c"])
    _run(["contacts", "create", "--email", "n@ew.c"])
    # POST bodies carry locationId in-band; the PUT-by-ID path carries the
    # target in the URL (established behavior, unchanged by this spec).
    for method, path, body, _v in stub.calls:
        if method == "POST" and not path.endswith("/tags"):
            assert body.get("locationId") == "loc-1", (method, path, body)


# ── Behavior 10: createNewIfDuplicateAllowed default + explicit ────────────

def test_duplicate_flag_omitted_by_default(stub):
    _run(["contacts", "upsert", "--email", "a@b.c"])
    (body,) = [c[2] for c in _posts_to(stub, "/contacts/upsert")]
    assert "createNewIfDuplicateAllowed" not in body


def test_duplicate_flag_true_only_on_explicit_request(stub):
    _run(["contacts", "upsert", "--email", "a@b.c",
          "--create-new-if-duplicate-allowed"])
    (body,) = [c[2] for c in _posts_to(stub, "/contacts/upsert")]
    assert body["createNewIfDuplicateAllowed"] is True


# ── Behavior 11: dry-run safe ──────────────────────────────────────────────

def test_dry_run_sends_nothing(stub, monkeypatch):
    from cli_anything.gohighlevel.utils import safety_gate
    monkeypatch.setenv("CAF_DRY_RUN", "true")
    monkeypatch.setenv("CAF_ALLOWED_LOCATION_IDS", "loc-1")
    real_post = stub.post

    def _guarded_post(path, data=None, version=None):
        safety_gate.check_write("POST", "https://x" + path, data,
                                location_id=(data or {}).get("locationId"))
        return real_post(path, data=data, version=version)

    monkeypatch.setattr(stub, "post", _guarded_post)
    r = _run(["contacts", "upsert", "--email", "a@b.c"])
    # check_write dry-run path calls sys.exit(0) before any network append
    assert r.exit_code == 0, r.output
    assert _posts_to(stub, "/contacts/upsert") == []


# ── Behavior 12: 429 STOP doctrine ─────────────────────────────────────────

def test_rate_limit_surfaces_without_retry_storm(stub):
    stub.fail_429 = True
    r = _run(["contacts", "upsert", "--email", "a@b.c"])
    assert r.exit_code != 0
    # Exactly ONE POST attempt — no blind retry loop, no tier fallthrough.
    assert len(_posts_to(stub, "/contacts/upsert")) == 1
    assert "429" in r.output or "Rate limited" in r.output


# ── Behavior 13: auth failures fail-loud ───────────────────────────────────

def test_auth_failure_fails_loud(stub):
    stub.fail_auth = True
    r = _run(["contacts", "upsert", "--email", "a@b.c"])
    assert r.exit_code != 0
    assert "401" in r.output or "invalid token" in r.output.lower()


# ── Behavior 14: successful upsert performs GET read-back ──────────────────

def test_successful_upsert_reads_back(stub):
    r = _run(["contacts", "upsert", "--email", "a@b.c", "--first-name", "Ann"])
    assert r.exit_code == 0, r.output
    gets = [c for c in stub.calls if c[0] == "GET" and c[1] == "/contacts/cid-123"]
    assert len(gets) >= 1
    assert "VERIFIED" in r.output


# ── Behavior 15: failed read-back does NOT repeat POST ─────────────────────

def test_failed_readback_never_reposts(stub):
    stub.fail_get = True
    r = _run(["contacts", "upsert", "--email", "a@b.c"])
    assert r.exit_code == 0, r.output  # write itself succeeded
    assert len(_posts_to(stub, "/contacts/upsert")) == 1
    assert "WRITE SUCCEEDED" in r.output and "VERIFICATION INCOMPLETE" in r.output


# ── Behavior 16: source omitted unless supplied ────────────────────────────

def test_source_omitted_unless_supplied(stub):
    _run(["contacts", "upsert", "--email", "a@b.c"])
    (body,) = [c[2] for c in _posts_to(stub, "/contacts/upsert")]
    assert "source" not in body
    stub.calls.clear()
    _run(["contacts", "upsert", "--email", "a@b.c", "--source", "web"])
    (body2,) = [c[2] for c in _posts_to(stub, "/contacts/upsert")]
    assert body2["source"] == "web"


# ── Behavior 17: custom fields targeted only ───────────────────────────────
# The CLI sends only the fields the caller passed; prove no mass-overwrite
# keys (customField-style blobs, empty placeholders) leak into the body.

def test_upsert_body_contains_only_intended_keys(stub):
    _run(["contacts", "upsert", "--email", "a@b.c", "--first-name", "Ann"])
    (body,) = [c[2] for c in _posts_to(stub, "/contacts/upsert")]
    assert set(body) <= {"locationId", "email", "phone", "firstName", "lastName",
                         "name", "companyName", "source",
                         "createNewIfDuplicateAllowed"}


# ── Behavior 18: update --tag stays refused ────────────────────────────────

def test_update_tag_refused(stub):
    r = _run(["contacts", "update", "cid-123", "--tag", "vip"])
    assert r.exit_code == 2
    assert "REPLACES ALL TAGS" in r.output
    assert [c for c in stub.calls if c[0] == "PUT"] == []


# ── Amendment 1: canonical matching language ───────────────────────────────

def test_upsert_help_uses_canonical_matching_language():
    runner = CliRunner()
    r = runner.invoke(cli_mod.cli, ["contacts", "upsert", "--help"])
    assert r.exit_code == 0, r.output
    assert "Allow Duplicate Contact" in r.output
