"""RFX-016: caf product/price creates accept a Command Center automation_write record.

Command Center mints ``scope`` as the JSON string {location_id, action, object_key}
(approval-requests.ts decideApprovalRequest). approval_record splits a scope string on
commas, so verifying with ``[action]`` refused every such record APPROVAL-SCOPE before
any POST. A loopback stand-in for Command Center serves the records; the REAL
shared-utils approval_record verifies them. No network beyond 127.0.0.1.

Run: python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_caf_approval_action.py -q
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel import gohighlevel_cli as cli_mod  # noqa: E402
from cli_anything.gohighlevel.gohighlevel_cli import cli  # noqa: E402

LOC = "LOC1"
PLAN = "a" * 64
AID = "appr_12345678"
RECORDS = {}


class _CommandCenter(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        rec = RECORDS.get(self.path.rsplit("/", 1)[-1])
        ok = self.headers.get("Authorization") == "Bearer test-token" and rec is not None
        body = json.dumps({"approval": rec} if ok else {"error": "not_found"}).encode()
        self.send_response(200 if ok else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def cc_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CommandCenter)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path, cc_url):
    for key, value in {"MISSION_CONTROL_URL": cc_url, "MC_API_TOKEN": "test-token",
                       "COMPANY_SLUG": "t1", "CAF_DATA_DIR": str(tmp_path),
                       "CAF_ALLOWED_LOCATION_IDS": LOC, "GHL_API_KEY": "fake-pit-token",
                       "GHL_LOCATION_ID": LOC}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CAF_DRY_RUN", raising=False)
    RECORDS.clear()


def _cc(action="products.create,products.prices.create", location=LOC, object_key="Seat", **over):
    """A launch_approvals row exactly as Command Center's owner decision mints it."""
    rec = {"approval_id": AID, "tenant_id": "t1", "kind": "automation_write",
           "client_identity_ref": "owner@client", "plan_hash": "sha256:" + PLAN,
           "scope": json.dumps({"location_id": location, "action": action, "object_key": object_key}),
           "cap_minor": None, "currency": None, "source_message_ref": "owner-request:req1",
           "revoked": False, "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    rec.update(over)
    RECORDS[AID] = rec
    return rec


def _refused(action, location=LOC):
    with pytest.raises(cli_mod._approval_record().ApprovalRefused) as err:
        cli_mod._verify_automation_write(AID, PLAN, action, location)
    return err.value.code


@pytest.mark.parametrize("action", ["products.create", "products.prices.create"])
def test_a_command_center_record_listing_both_actions_verifies_each(action):
    _cc()
    result = cli_mod._verify_automation_write(AID, PLAN, action, LOC)
    assert result["ok"] is True and result["kind"] == "automation_write"
    assert result["binding"]["location_id"] == LOC


def test_a_record_scoped_to_one_action_verifies_that_action_only():
    _cc(action="products.create")
    assert cli_mod._verify_automation_write(AID, PLAN, "products.create", LOC)["ok"] is True
    assert _refused("products.prices.create") == "APPROVAL-ACTION"


def test_wrong_action_refused():
    _cc(action="contacts.create")
    assert _refused("products.create") == "APPROVAL-ACTION"


def test_an_action_is_matched_whole_never_as_a_substring():
    _cc(action="products.create.extra")
    assert _refused("products.create") == "APPROVAL-ACTION"


def test_wrong_location_refused():
    _cc(location="OTHER")
    assert _refused("products.create") == "APPROVAL-LOCATION"


def test_missing_object_key_refused():
    _cc(object_key="")
    # a shared verifier that reads the binding itself refuses the half binding first
    assert _refused("products.create") in ("APPROVAL-OBJECT", "APPROVAL-NOT-FROM-AUTHORITY")


def test_wrong_kind_refused():
    _cc(kind="publish")
    assert _refused("products.create") == "APPROVAL-KIND"


def test_wrong_plan_hash_refused():
    _cc(plan_hash="sha256:" + "b" * 64)
    assert _refused("products.create") == "APPROVAL-HASH"


def test_revoked_and_expired_refused():
    _cc(revoked=True)
    assert _refused("products.create") == "APPROVAL-REVOKED"
    _cc(expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    assert _refused("products.create") == "APPROVAL-EXPIRED"


def _legacy(scope):
    RECORDS[AID] = {"schema_version": "1.0", "approval_id": AID, "kind": "automation_write",
                    "plan_hash": PLAN, "client_identity": "t1", "source_message_ref": "msg-1",
                    "scope": scope, "revoked": False,
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}


def test_a_legacy_list_scope_record_still_behaves_as_before():
    _legacy(["products.create"])
    assert cli_mod._verify_automation_write(AID, PLAN, "products.create", LOC)["ok"] is True
    assert _refused("products.prices.create") == "APPROVAL-SCOPE"


def test_a_free_text_scope_string_still_splits_on_commas():
    _legacy("products.create, products.prices.create")
    assert cli_mod._verify_automation_write(AID, PLAN, "products.prices.create", LOC)["ok"] is True
    assert _refused("contacts.create") == "APPROVAL-SCOPE"


# ---- end to end: the CLI command against the loopback Command Center --------------

class _Catalog:
    def __init__(self):
        self.posts = []

    def post(self, path, data=None, version=None):
        self.posts.append(path)
        return {"_id": "PR1"} if path.endswith("/price") else {"_id": "P1"}

    def get(self, path, params=None, version=None):
        route = path.split("?")[0]
        if route == "/products/":
            return {"products": [], "total": 0}
        if route == "/products/P1/price":
            return {"prices": [], "total": 0}
        if route == "/products/P1":
            return {"_id": "P1", "name": "Seat", "productType": "SERVICE", "locationId": LOC}
        return {"_id": "PR1", "product": "P1", "amount": 49.0, "currency": "USD", "type": "one_time"}


def _run(catalog, *args):
    with patch.object(cli_mod.api, "post", catalog.post), patch.object(cli_mod.api, "get", catalog.get):
        return CliRunner().invoke(cli, ["--json", "--location-id", LOC, "payments", *args,
                                        "--approval-id", AID, "--plan-sha256", PLAN])


def test_cli_creates_product_and_price_with_a_command_center_record():
    _cc()
    catalog = _Catalog()
    product = _run(catalog, "create-product", "--name", "Seat")
    price = _run(catalog, "create-price", "--product-id", "P1", "--name", "Seat", "--amount", "4900")
    assert product.exit_code == 0 and price.exit_code == 0, product.output + price.output
    assert catalog.posts == ["/products/", "/products/P1/price"]


def test_cli_wrong_action_record_posts_nothing():
    _cc(action="contacts.create")
    catalog = _Catalog()
    result = _run(catalog, "create-product", "--name", "Seat")
    assert result.exit_code != 0 and "APPROVAL-ACTION" in result.output
    assert catalog.posts == []


# ---- installed-engine shared-utils lookup -------------------------------------------

def _plant(root):
    target = root / "ghl" / "products_prices.py"
    target.parent.mkdir(parents=True)
    target.write_text("")
    return target


def test_caf_engine_copy_finds_shared_utils_in_the_skills_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("CAF_SHARED_UTILS_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    engine = tmp_path / "root" / "tools" / "convert-and-flow-cli" / "engine"
    monkeypatch.setattr(cli_mod, "__file__", str(engine / "cli_anything" / "gohighlevel" / "gohighlevel_cli.py"))
    want = _plant(tmp_path / "root" / "skills" / "shared-utils")
    assert cli_mod._shared_utils_file("ghl", "products_prices.py") == str(want)


def test_standard_home_location_is_the_last_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("CAF_SHARED_UTILS_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli_mod, "__file__", str(tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "cli.py"))
    want = _plant(tmp_path / "home" / ".openclaw" / "skills" / "shared-utils")
    assert cli_mod._shared_utils_file("ghl", "products_prices.py") == str(want)


def test_nothing_found_names_the_override(monkeypatch, tmp_path):
    monkeypatch.delenv("CAF_SHARED_UTILS_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli_mod, "__file__", str(tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "cli.py"))
    with pytest.raises(RuntimeError, match="CAF_SHARED_UTILS_DIR"):
        cli_mod._shared_utils_file("ghl", "products_prices.py")
