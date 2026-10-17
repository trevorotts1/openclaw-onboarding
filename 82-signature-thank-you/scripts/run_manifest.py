"""Build the S82 run manifest for one thank-you resolution (v0.3.0).

CR-S49-004 Path B: S49 owns the page-request -> page-result
translation layer; S82 guarantees the exact input it translates
from. That input is two documents per fulfilled purchase resolution:

1. the thank-you result document (schemas/thank-you-result.schema.json)
   — identity, order view, validation, errors; and
2. this companion run manifest (schemas/run-manifest.schema.json),
   carrying the two result-side facts the result document does not:
   the run's independent-review facts and the native bindings the
   resolution consumed, plus provenance for both inputs.

The manifest is a SEPARATE document emitted alongside the result. It
is never embedded in the result or the order view, and building it
never mutates any of its inputs.

Honesty rules (fail closed; this manifest exists so a downstream
translator never has to guess):

- `independent_review`: with no review supplied, status is "none"
  and reviewer/verdict/record_ref are null — stated, never
  fabricated. A review claiming status "recorded" must carry all
  three facts (reviewer, verdict, record_ref); a partial or
  self-contradictory review record is rejected, not emitted.
- `native_bindings_ref.entitlement_version`: taken only from the
  S44 fulfillment-map producer envelope the run actually consumed
  (or, equivalently, the version the resolver carried into the
  view). It must be a well-formed ev1 value (CR-S82-002 item 5);
  any other shape is rejected. With no envelope consumed it is
  null — a version is never derived, guessed, or invented here
  (deriving a fingerprint version is the confirmation
  observation's job, a different record with a different purpose).
- `envelope_ref` / `provenance.snapshot_ref` / `provenance.map_ref`:
  references are facts of the caller's run (where the inputs were
  loaded from), supplied explicitly by the caller. Absent a
  supplied reference the field is null; this module never invents
  a path.
- An envelope or snapshot naming a different tenant/launch than
  the resolved view is another buyer's run and is rejected.
- Raw payment credential fields anywhere in the inputs are
  rejected, exactly as in the resolver.

Stdlib only. Deterministic: no clock, no randomness, no network.
"""

import json

from thank_you_resolver import ENTITLEMENT_VERSION_PATTERN, FORBIDDEN_KEYS

MANIFEST_VERSION = "1.0"

# The name of the companion result document when the caller does not
# state another one (the committed CR-S49-004 example value).
DEFAULT_RESULT_REF = "thank-you-result.json"

REVIEW_STATUSES = ("none", "recorded")
REVIEW_FIELDS = ("reviewer", "verdict", "record_ref")

IDENTITY_KEYS = ("tenant_id", "location_id", "launch_id")


class ManifestError(ValueError):
    """Raised when no honest run manifest can be built from the input."""


def _scan_forbidden(obj, path="$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ManifestError(
                    "forbidden_field: raw payment credential field "
                    f"'{key}' at {path} must never enter a run manifest"
                )
            _scan_forbidden(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _scan_forbidden(value, f"{path}[{i}]")


def _review_block(independent_review):
    """Normalize the run's review facts, failing closed on invention.

    None (no review supplied for this run) -> status "none", all
    facts null: the honest statement that no review exists. A
    supplied record must be complete and self-consistent; anything
    half-stated is rejected rather than padded.
    """
    if independent_review is None:
        return {"status": "none", "reviewer": None,
                "verdict": None, "record_ref": None}
    if not isinstance(independent_review, dict):
        raise ManifestError(
            "invalid_independent_review: review facts must be an object "
            "with status/reviewer/verdict/record_ref, or None"
        )
    unknown = sorted(set(independent_review)
                     - {"status", *REVIEW_FIELDS})
    if unknown:
        raise ManifestError(
            f"invalid_independent_review: unknown field(s) {unknown}; "
            "the committed shape is status/reviewer/verdict/record_ref"
        )
    facts = {field: independent_review.get(field) for field in REVIEW_FIELDS}
    status = independent_review.get("status")
    if status is None:
        status = "recorded" if any(
            value not in (None, "") for value in facts.values()) else "none"
    if status not in REVIEW_STATUSES:
        raise ManifestError(
            f"invalid_independent_review: status {status!r} is not one "
            f"of {list(REVIEW_STATUSES)}"
        )
    if status == "none":
        if any(value not in (None, "") for value in facts.values()):
            raise ManifestError(
                "invalid_independent_review: status 'none' contradicts "
                "supplied review facts; a run either has a recorded "
                "review or it does not"
            )
        return {"status": "none", "reviewer": None,
                "verdict": None, "record_ref": None}
    missing = [field for field, value in facts.items()
               if value in (None, "")]
    if missing:
        raise ManifestError(
            "invalid_independent_review: status 'recorded' requires "
            f"reviewer, verdict and record_ref; missing {missing}; "
            "a recorded review is never emitted half-stated"
        )
    return {"status": "recorded", **facts}


def _envelope_of(fulfillment_map):
    """Return the S44 producer envelope in `fulfillment_map`, or None.

    Same shape test as the resolver: an "entitlements" dict paired
    with a string "entitlement_version". A bare entitlement map can
    never satisfy it.
    """
    if (isinstance(fulfillment_map, dict)
            and isinstance(fulfillment_map.get("entitlements"), dict)
            and isinstance(fulfillment_map.get("entitlement_version"), str)):
        return fulfillment_map
    return None


def build_run_manifest(view, snapshot=None, fulfillment_map=None, *,
                       independent_review=None,
                       envelope_ref=None, snapshot_ref=None, map_ref=None,
                       result_ref=DEFAULT_RESULT_REF):
    """Build the run manifest for one completed resolver run.

    view: the order view the run produced (resolve_order_view's
        output). Required; the manifest's identity and test_only
        facts are the run's own, read from it.
    snapshot: the verified purchase snapshot the run consumed, when
        the caller still holds it; identity-checked against the view
        when supplied.
    fulfillment_map: the fulfillment map (or S44 producer envelope)
        the run consumed, when the caller still holds it. The
        envelope's ev1 entitlement_version is the version the
        manifest binds to; with no envelope, the version the
        resolver carried into the view is used; with neither, the
        field is null.
    independent_review: the run's review facts
        {status, reviewer, verdict, record_ref}, or None when no
        review applies to this run.
    envelope_ref / snapshot_ref / map_ref: caller-supplied
        references to the inputs as loaded; null when not supplied.
    result_ref: reference to the companion thank-you result
        document this manifest accompanies.
    """
    if not isinstance(view, dict):
        raise ManifestError("view must be an order-view object")
    for key in IDENTITY_KEYS:
        if view.get(key) in (None, ""):
            raise ManifestError(f"view is missing required field {key!r}")
    if not isinstance(result_ref, str) or not result_ref:
        raise ManifestError("result_ref must name the result document")

    _scan_forbidden(view)
    if snapshot is not None:
        _scan_forbidden(snapshot)
    if fulfillment_map is not None:
        _scan_forbidden(fulfillment_map)
    if independent_review is not None:
        _scan_forbidden(independent_review)

    if snapshot is not None:
        if not isinstance(snapshot, dict):
            raise ManifestError("snapshot must be an object when supplied")
        for key in IDENTITY_KEYS:
            named = snapshot.get(key)
            if named is not None and named != view.get(key):
                raise ManifestError(
                    f"identity_mismatch: snapshot {key}={named!r} does "
                    f"not match view {view.get(key)!r} (wrong_scope)"
                )

    envelope = _envelope_of(fulfillment_map)
    entitlement_version = None
    if envelope is not None:
        for key in ("tenant_id", "launch_id"):
            named = envelope.get(key)
            if named is not None and named != view.get(key):
                raise ManifestError(
                    f"identity_mismatch: fulfillment envelope {key}="
                    f"{named!r} does not match view {view.get(key)!r} "
                    "(wrong_scope)"
                )
        entitlement_version = envelope["entitlement_version"]
    elif view.get("entitlement_version") not in (None, ""):
        # The resolver carried S44's version into the view; that is
        # the version this run consumed, stated by the run itself.
        entitlement_version = view["entitlement_version"]
    if entitlement_version is not None and (
            not isinstance(entitlement_version, str)
            or not ENTITLEMENT_VERSION_PATTERN.match(entitlement_version)):
        raise ManifestError(
            "invalid_entitlement_version: "
            f"{entitlement_version!r} is not a well-formed ev1 value "
            "('ev1:' + 64 lowercase hex); refusing to bind a "
            "mismatched or forged version into the manifest"
        )

    for name, ref in (("envelope_ref", envelope_ref),
                      ("snapshot_ref", snapshot_ref),
                      ("map_ref", map_ref)):
        if ref is not None and (not isinstance(ref, str) or not ref):
            raise ManifestError(f"{name} must be a non-empty string or None")

    return {
        "manifest_version": MANIFEST_VERSION,
        "tenant_id": view["tenant_id"],
        "location_id": view["location_id"],
        "launch_id": view["launch_id"],
        "test_only": bool(view.get("test_only", False)),
        "result_ref": result_ref,
        "independent_review": _review_block(independent_review),
        "native_bindings_ref": {
            "envelope_ref": envelope_ref,
            "entitlement_version": entitlement_version,
        },
        "provenance": {
            "snapshot_ref": snapshot_ref,
            "map_ref": map_ref,
        },
    }


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", required=True,
                        help="order view JSON the run produced")
    parser.add_argument("--snapshot",
                        help="verified purchase snapshot JSON consumed")
    parser.add_argument("--fulfillment",
                        help="fulfillment map / S44 envelope JSON consumed")
    parser.add_argument("--review",
                        help="independent review facts JSON, when a "
                             "review applies to this run")
    parser.add_argument("--envelope-ref")
    parser.add_argument("--snapshot-ref")
    parser.add_argument("--map-ref")
    parser.add_argument("--result-ref", default=DEFAULT_RESULT_REF)
    parser.add_argument("--out",
                        help="also write the manifest to this path "
                             "(it is printed to stdout either way)")
    args = parser.parse_args(argv)
    manifest = build_run_manifest(
        _load(args.view),
        snapshot=_load(args.snapshot) if args.snapshot else None,
        fulfillment_map=_load(args.fulfillment) if args.fulfillment else None,
        independent_review=_load(args.review) if args.review else None,
        envelope_ref=args.envelope_ref,
        snapshot_ref=args.snapshot_ref,
        map_ref=args.map_ref,
        result_ref=args.result_ref,
    )
    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
