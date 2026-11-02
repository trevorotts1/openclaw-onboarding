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

Products (S44-20) are keyed by (location, logical id), never by name
alone. A product manifest item is {"logical_id", "name", "price":
{"amount_minor", "currency"}}; it counts as provisioned only when a LIVE
read of the native object (get_product) shows the same location, name and
price, and the ledger then records the native product and price ids from
that read-back under "product_native". A same-name product with another
price (last year's $297 bundle for this year's $197 offer) is never
adopted. A bare-name product item keeps the old name-only behavior, is
flagged price-unverified and is never recorded in "product_native", so the
executor does not accept it for a product dependency.

S44-19: this module is not a production purchase path. The Black Friday
2026 purchase path is native GHL post-sale workflows; siglaunch has no
production runner or catalog yet.

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
    # S44-20 priced-product surface. A native product object is normalized to
    # {"native_product_id", "location_id", "name", "prices": [{"native_price_id",
    # "amount_minor", "currency"}]}.
    def list_product_objects(self, location_id: str) -> list[dict]: ...
    def get_product(self, location_id: str,
                    native_product_id: str) -> dict | None: ...
    def create_product_with_price(self, location_id: str, name: str,
                                  price: dict) -> str: ...


_LIST = {"tags": "list_tags", "fields": "list_fields",
         "products": "list_products"}
_CREATE = {"tags": "create_tag", "fields": "create_field",
           "products": "create_product"}


def _live_match(obj, location_id: str, name: str, price: dict):
    """The native price read-back that satisfies (location, name, price), or None."""
    if not obj or obj.get("location_id") != location_id \
            or obj.get("name") != name:
        return None
    for p in obj.get("prices") or []:
        if p.get("amount_minor") == price["amount_minor"] \
                and p.get("currency") == price["currency"]:
            return p
    return None


def _provision_product(catalog, location_id: str, item: dict, recorded,
                       entry: dict, native: dict) -> bool:
    """Priced product by (location, logical id) with native id read-back.
    Returns True when verified; fills entry["state"] and native."""
    logical, name, price = item["logical_id"], item["name"], item["price"]
    entry["logical_id"] = logical
    state, found = "existed", None
    if recorded:  # the ledger is only a hint: always re-read the native object
        live = catalog.get_product(location_id, recorded["native_product_id"])
        if _live_match(live, location_id, name, price):
            found = live
    if found is None:
        hits = [o for o in catalog.list_product_objects(location_id)
                if _live_match(o, location_id, name, price)]
        if len(hits) > 1:
            entry["state"] = "ambiguous"
            entry["note"] = (f"{len(hits)} products match name and price; "
                             "refusing to guess; NOT recorded as provisioned")
            return False
        if hits:
            found = hits[0]
        else:
            state = "created"
            new_id = catalog.create_product_with_price(location_id, name, price)
            found = catalog.get_product(location_id, new_id)  # read-back
            if not _live_match(found, location_id, name, price):
                entry["state"] = "unverified"
                entry["note"] = ("create returned but the read-back does not "
                                 "show this product at this price; NOT "
                                 "recorded as provisioned")
                return False
    entry["state"] = state
    native[logical] = {
        "native_product_id": found["native_product_id"],
        "native_price_id": _live_match(found, location_id, name,
                                       price)["native_price_id"],
        "name": name, "amount_minor": price["amount_minor"],
        "currency": price["currency"]}
    entry["native"] = native[logical]
    return True


def provision(catalog: Catalog, location_id: str, manifest: dict,
              ledger_path: str | Path) -> dict:
    """Ensure every manifest item exists at the location. manifest:
    {"tags": [name...], "fields": [{"name","type"}...],
     "products": [{"logical_id","name","price":{"amount_minor",
     "currency"}} ... or bare names (legacy, name-only)]}. Returns the provisioning receipt; also
    writes the ledger of VERIFIED-present items."""
    receipt = {"location_id": location_id, "items": [], "ledger": {}}
    ledger_path = Path(ledger_path)
    ledger = {}
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text())
    prior = ledger.get(location_id, {}).get("product_native", {})
    native: dict[str, dict] = {}
    verified: dict = {"tags": [], "fields": [], "products": [],
                      "product_native": native}
    for kind in ("tags", "fields", "products"):
        wanted = manifest.get(kind, [])
        existing = None  # listed lazily: priced products never use it
        for item in wanted:
            name = item["name"] if isinstance(item, dict) else item
            entry = {"kind": kind, "name": name}
            if kind == "products" and isinstance(item, dict) \
                    and "logical_id" in item:
                if _provision_product(catalog, location_id, item,
                                      prior.get(item["logical_id"]),
                                      entry, native):
                    verified[kind].append(item["logical_id"])
                receipt["items"].append(entry)
                continue
            if kind == "products":
                entry["price_unverified"] = True
                entry["note"] = ("name-only match: no native id or price "
                                 "read-back; the executor will not accept it")
            if existing is None:
                existing = getattr(catalog, _LIST[kind])(location_id)
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
    ledger[location_id] = verified
    ledger_path.write_text(json.dumps(ledger, indent=1, sort_keys=True))
    receipt["complete"] = all(
        e["state"] in ("existed", "created") for e in receipt["items"])
    return receipt
