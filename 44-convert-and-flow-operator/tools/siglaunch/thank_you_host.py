#!/usr/bin/env python3
"""Skill 44 runtime host for Skill 82's thank-you resolver (harmony issue 6).

Skill 44 owns production payment truth (the normalizer and the durable store).
Skill 82 owns the purchase-time resolver but ships no process that runs it, so
the translator in Skill 49 (translate_thank_you_result.py, non-design mode)
waited on two files nothing produced. This module is that producer:

    python3 thank_you_host.py --snapshot EVENTS.json --map FULFILLMENT.json \
        --out-dir WORK_DIR [--offer-catalog C.json] [--request PAGE_REQUEST.json] \
        [--review REVIEW.json] [--s44-db STORE.sqlite]

--snapshot is the normalizer purchase event (one event object, or a list of
events for one order). The host turns it into the verified snapshot with
Skill 82's own adapter, resolves the order view with Skill 82's own resolver,
then re-runs Skill 82's validators and the no-pitch scan before it writes
anything. --map is the fulfillment-map envelope that
fulfillment_map.build_fulfillment_map returns (a bare map has no
entitlement_version and is refused).

Files written into --out-dir, all-or-nothing (a refusal writes none of them):

    thank-you-result.json         the result document the translator reads
    thank-you-run-manifest.json   its companion run manifest
    purchase-snapshot.json        the snapshot, sha256 bound in the manifest
    fulfillment-map.json          the map, sha256 bound in the manifest
    thank-you-render.html         the rendered page, listed as the artifact

Exit 0 written, 2 refused (reasons on stderr), 3 usage.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 2, 3

RESULT_NAME = "thank-you-result.json"
MANIFEST_NAME = "thank-you-run-manifest.json"
SNAPSHOT_NAME = "purchase-snapshot.json"
MAP_NAME = "fulfillment-map.json"
RENDER_NAME = "thank-you-render.html"

_HERE = Path(__file__).resolve().parent


class HostRefused(ValueError):
    """No honest result/manifest pair can be written; nothing was written."""


def _s82_scripts() -> Path:
    """Skill 82's scripts dir under the repo layout or the 999 package layout."""
    for root in _HERE.parents:
        for rel in ("82-signature-thank-you", "signature-thank-you",
                    ".claude/skills/signature-thank-you",
                    ".claude/skills/82-signature-thank-you"):
            d = root / rel / "scripts"
            if (d / "thank_you_resolver.py").is_file():
                return d
    raise HostRefused("Skill 82's scripts were not found beside this skill; "
                      "the host has nothing to run")


def _canon(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def host(events_doc, map_doc, out_dir, *, offer_catalog=None, revision=1,
         request=None, expected_identity=None, review=None,
         evidence_store=None, brand=None,
         author_session="44-thank-you-host") -> dict:
    """Run Skill 82 over one purchase and write the two files the translator
    expects (plus the three it binds by sha256). Returns {name: path}."""
    sys.path.insert(0, str(_s82_scripts()))
    import purchase_event_adapter as adapter
    import run_manifest
    import semantic_scan
    import thank_you_resolver
    import validate_thank_you
    from render_thank_you import render_order_view

    # 1. the fulfillment map must be the S44 producer envelope
    if not (isinstance(map_doc, dict)
            and isinstance(map_doc.get("entitlements"), dict)
            and isinstance(map_doc.get("entitlement_version"), str)):
        raise HostRefused(
            "map: expected the fulfillment-map envelope "
            "(entitlements + entitlement_version) from build_fulfillment_map")

    # 2. events -> verified snapshot (or an adapter-stamped snapshot as given)
    try:
        if (isinstance(events_doc, dict)
                and events_doc.get("source") == adapter.SNAPSHOT_SOURCE):
            snapshot = copy.deepcopy(events_doc)
        else:
            events = events_doc if isinstance(events_doc, list) else [events_doc]
            snapshot = adapter.build_snapshot(
                events, offer_catalog=offer_catalog, revision=revision,
                evidence_store=evidence_store)
    except adapter.AdapterError as exc:
        raise HostRefused(f"snapshot: {exc}")

    # 3. identity: the page-request (when given) and explicit flags are the
    # authority for who this page is for; the snapshot never vouches for itself
    ident = {}
    if request is not None:
        ident = {k: request.get(k) for k in
                 ("tenant_id", "location_id", "launch_id")}
        if request.get("test_only") != snapshot.get("test_only"):
            raise HostRefused(
                f"identity: page-request test_only={request.get('test_only')!r}"
                f" but the snapshot's is {snapshot.get('test_only')!r}")
    ident.update({k: v for k, v in (expected_identity or {}).items() if v})

    # 4. resolve (Skill 82 refuses unstamped/edited snapshots and foreign maps)
    try:
        view = thank_you_resolver.resolve_order_view(
            snapshot, map_doc, expected_identity=ident or None)
    except thank_you_resolver.ResolverError as exc:
        raise HostRefused(f"resolver: {exc}")

    # 5. the map the translator will replay: only entitlements this purchase paid
    paid = {e for line in snapshot["line_items"]
            if line.get("payment_status") == "succeeded"
            for e in line.get("entitlement_ids") or []}
    mapping = {k: v for k, v in map_doc["entitlements"].items() if k in paid}

    # 6. refuse on A13/A14 violations and on any pitch in the rendered page
    errors = list(validate_thank_you.validate_thank_you(view, snapshot, mapping))
    html = render_order_view(view, brand)
    errors += [f"no_pitch_scan: line {f['line']} [{f['reason']}] "
               f"{f['match']!r}" for f in semantic_scan.scan_text(html)]
    if errors:
        raise HostRefused("; ".join(errors))

    # 7. build every document in memory, then write
    snap_text = _canon(snapshot)
    out_map = {"version": map_doc["entitlement_version"],
               "tenant_id": snapshot["tenant_id"],
               "launch_id": snapshot["launch_id"],
               "revision": snapshot["revision"],
               "entitlement_version": map_doc["entitlement_version"],
               "entitlements": mapping}
    map_text = _canon(out_map)
    input_hash = _sha(snap_text)
    result = {
        "schema_version": "1.0",
        "tenant_id": snapshot["tenant_id"],
        "location_id": snapshot["location_id"],
        "launch_id": snapshot["launch_id"],
        "revision": snapshot["revision"],
        "request_id": f"s82-host-{input_hash[:16]}",
        "input_hash": input_hash,
        "status": "authored",
        "order_view": view,
        "validation": {"no_pitch_pass": True, "entitlements_match": True},
        "errors": [],
        "blockers": [],
        "artifacts": [{"path": RENDER_NAME, "sha256": _sha(html)}],
        "author_session": author_session,
        "reviewer_session": None,
        "proof_class": "L2",
        "test_only": bool(snapshot["test_only"]),
    }
    try:
        manifest = run_manifest.build_run_manifest(
            view, snapshot, map_doc, independent_review=review,
            envelope_ref=MAP_NAME, snapshot_ref=SNAPSHOT_NAME, map_ref=MAP_NAME,
            snapshot_sha256=_sha(snap_text), result_ref=RESULT_NAME)
    except run_manifest.ManifestError as exc:
        raise HostRefused(f"manifest: {exc}")
    manifest["provenance"]["map_sha256"] = _sha(map_text)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {SNAPSHOT_NAME: snap_text, MAP_NAME: map_text, RENDER_NAME: html,
             RESULT_NAME: _canon(result), MANIFEST_NAME: _canon(manifest)}
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
    return {name: str(out / name) for name in files}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--snapshot", required=True,
                    help="normalizer purchase event JSON (object, or list for one order)")
    ap.add_argument("--map", required=True, help="fulfillment-map envelope JSON")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--offer-catalog", help="{offer_id: offer} JSON for display names")
    ap.add_argument("--request", help="S49 thank_you page-request JSON (identity authority)")
    ap.add_argument("--review", help="independent review facts JSON, when one exists")
    ap.add_argument("--brand", help="brand JSON for the rendered page")
    ap.add_argument("--revision", type=int, default=1)
    ap.add_argument("--s44-db", help="S44 store proving each live event's evidence_ref")
    ap.add_argument("--author-session", default="44-thank-you-host")
    args = ap.parse_args(argv)
    try:
        store = None
        if args.s44_db:
            sys.path.insert(0, str(_HERE / "store"))
            from store import Store
            store = Store(args.s44_db)
        written = host(
            _load(args.snapshot), _load(args.map), args.out_dir,
            offer_catalog=_load(args.offer_catalog) if args.offer_catalog else None,
            revision=args.revision,
            request=_load(args.request) if args.request else None,
            review=_load(args.review) if args.review else None,
            brand=_load(args.brand) if args.brand else None,
            evidence_store=store, author_session=args.author_session)
    except HostRefused as exc:
        print(f"THANK-YOU HOST REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except (OSError, ValueError) as exc:
        print(f"USAGE ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps({"written": written}, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
