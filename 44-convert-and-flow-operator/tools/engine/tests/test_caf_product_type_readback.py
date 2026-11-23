"""RFX-017: caf payments create-product survives GHL's DIGITAL/PHYSICAL read-back split.

Measured live 2026-11-23 (read-only GETs): after POST /products/ with productType
DIGITAL, GET /products/{id} answers PHYSICAL while GET /products/ lists DIGITAL. The
read-back confirms the type from the product's own list row only for that case, and an
exact-name product of the requested type is reused with no POST. Mocked HTTP only.

Run: python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_caf_product_type_readback.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel import gohighlevel_cli as cli_mod  # noqa: E402
from cli_anything.gohighlevel.gohighlevel_cli import cli  # noqa: E402

LOC = "LOC1"
LIST_ROUTE = "GET /products/?locationId={locationId}&search={search}&limit=100"
# Test-only stand-in for a verified record; no approval authority is contacted.
APPROVAL = ["--approval-id", "TEST-ONLY-APPROVAL", "--plan-sha256", "0" * 64]


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for key, value in {"CAF_DATA_DIR": str(tmp_path), "CAF_ALLOWED_LOCATION_IDS": LOC,
                       "CAF_APPROVAL_TOKEN": "t", "GHL_API_KEY": "fake-pit-token",
                       "GHL_LOCATION_ID": LOC}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CAF_DRY_RUN", raising=False)
    monkeypatch.setattr(cli_mod, "_verify_automation_write", lambda *a: {
        "ok": True, "approval_id": "TEST-ONLY-APPROVAL", "kind": "automation_write",
        "client_identity": "test-only-client", "expires_at": "2999-01-01T00:00:00+00:00"})


class SplitCatalog:
    """GHL products API whose single-product GET reports ``single_type``."""

    def __init__(self, single_type="PHYSICAL", list_type=None, existing=()):
        self.single_type, self.list_type = single_type, list_type
        self.products = [dict(p) for p in existing]
        self.calls = []

    def post(self, path, data=None, version=None):
        self.calls.append(("POST", path))
        self.products.append({"_id": "P1", "name": data["name"], "productType": data["productType"],
                              "locationId": data["locationId"]})
        return {"_id": "P1"}

    def get(self, path, params=None, version=None):
        route = path.split("?")[0]
        self.calls.append(("GET", route))
        if route == "/products/":
            rows = [dict(p, productType=self.list_type or p["productType"]) for p in self.products]
            return {"products": rows, "total": [{"total": len(rows)}]}
        row = next(p for p in self.products if p["_id"] == route.rsplit("/", 1)[-1])
        return dict(row, productType=self.single_type)

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def create(catalog, ptype="DIGITAL"):
    with patch.object(cli_mod.api, "post", catalog.post), patch.object(cli_mod.api, "get", catalog.get):
        return CliRunner().invoke(cli, ["--json", "--location-id", LOC, "payments", "create-product",
                                        "--name", "Workbook", "--type", ptype, *APPROVAL])


def test_digital_read_back_physical_is_confirmed_by_the_list():
    catalog = SplitCatalog()
    result = create(catalog)
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["product_type"] == "DIGITAL" and out["type_confirmed_by"] == LIST_ROUTE
    assert out["action"] == "created" and out["readback"] == "verified"
    assert catalog.calls == [("GET", "/products/"), ("POST", "/products/"),
                             ("GET", "/products/P1"), ("GET", "/products/")]


def test_list_also_physical_fails():
    catalog = SplitCatalog(list_type="PHYSICAL")
    result = create(catalog)
    assert result.exit_code == 1 and "type readback 'PHYSICAL' != 'DIGITAL'" in result.output


def test_service_mismatch_still_fails():
    catalog = SplitCatalog(single_type="DIGITAL")
    result = create(catalog, "SERVICE")
    assert result.exit_code == 1 and "type readback 'DIGITAL' != 'SERVICE'" in result.output
    assert catalog.calls[-1] == ("GET", "/products/P1")  # no list lookup for a SERVICE request


def test_existing_exact_name_digital_product_is_reused_with_no_post():
    catalog = SplitCatalog(existing=[{"_id": "P7", "name": "Workbook", "productType": "DIGITAL",
                                      "locationId": LOC}])
    result = create(catalog)
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert catalog.posts() == []
    assert out["native_product_id"] == "P7" and out["action"] == "reused"
    assert out["type_confirmed_by"] == LIST_ROUTE
