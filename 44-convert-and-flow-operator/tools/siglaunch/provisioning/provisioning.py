"""S44-03 Phase-A provisioning (DESIGN-S44-02-03-05-v1.md section 2).

Provisions the dependencies S06's Phase B and the receiver's wiring
depend on — tags, custom fields, products — through the supported
adapter surface, GET-first and idempotently:

- read the existing set first; create only what is missing;
- after any create, read back: an item enters the provisioning ledger
  ONLY when the read-back shows it present (write-succeeded /
  verification-incomplete doctrine — an unverified create is reported
  as such and never recorded as provisioned);
- tag strings are carried VERBATIM from the launch manifest (the
  "course purchase" vs "course-purchase" drift hazard is a verbatim-
  string problem, DESIGN-S44-04 section 9);
- the ledger written here is exactly the file the receiver's
  CafExecutor dependency precheck reads:
  {location_id: {"tags": [...], "fields": [...], "products": [...]}}.

The catalog surface is injected (the engine adapter in production, a
fake in tests); this module invents no native calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class Catalog(Protocol):
    def list_tags(self, location_id: str) -> list[str]: ...
    def create_tag(self, location_id: str, name: str) -> None: ...
    def list_fields(self, location_id: str) -> list[str]: ...
    def create_field(self, location_id: str, name: str,
                     field_type: str) -> None: ...
    def list_products(self, location_id: str) -> list[str]: ...
    def create_product(self, location_id: str, name: str) -> None: ...


_LIST = {"tags": "list_tags", "fields": "list_fields",
         "products": "list_products"}
_CREATE = {"tags": "create_tag", "fields": "create_field",
           "products": "create_product"}


def provision(catalog: Catalog, location_id: str, manifest: dict,
              ledger_path: str | Path) -> dict:
    """Ensure every manifest item exists at the location. manifest:
    {"tags": [name...], "fields": [{"name","type"}...],
     "products": [name...]}. Returns the provisioning receipt; also
    writes the ledger of VERIFIED-present items."""
    receipt = {"location_id": location_id, "items": [], "ledger": {}}
    verified: dict[str, list[str]] = {"tags": [], "fields": [],
                                      "products": []}
    for kind in ("tags", "fields", "products"):
        wanted = manifest.get(kind, [])
        existing = getattr(catalog, _LIST[kind])(location_id)
        for item in wanted:
            name = item["name"] if isinstance(item, dict) else item
            entry = {"kind": kind, "name": name}
            if name in existing:
                entry["state"] = "existed"
                verified[kind].append(name)
            else:
                if kind == "fields":
                    catalog.create_field(location_id, name,
                                         item.get("type", "TEXT"))
                else:
                    getattr(catalog, _CREATE[kind])(location_id, name)
                # verify by read-back; only verified items are provisioned
                after = getattr(catalog, _LIST[kind])(location_id)
                if name in after:
                    entry["state"] = "created"
                    verified[kind].append(name)
                else:
                    entry["state"] = "unverified"
                    entry["note"] = ("create returned but the read-back "
                                      "does not show the item; NOT "
                                      "recorded as provisioned")
            receipt["items"].append(entry)
    receipt["ledger"] = verified
    ledger_path = Path(ledger_path)
    ledger = {}
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text())
    ledger[location_id] = verified
    ledger_path.write_text(json.dumps(ledger, indent=1, sort_keys=True))
    receipt["complete"] = all(
        e["state"] in ("existed", "created") for e in receipt["items"])
    return receipt
