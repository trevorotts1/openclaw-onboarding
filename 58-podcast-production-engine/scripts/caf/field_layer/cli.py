#!/usr/bin/env python3
"""
Command line entry point for the Convert and Flow field layer.

Runtime pipeline usage (design Section 9, Steps 14 to 17):
  resolve     - prove the client's own PIT and Location ID resolve, print an
                audit with no values (design Sections 2.3 and 7.3).
  build-map   - build or refresh the field-key to field-id map and cache it.
  write-back  - Step 16 link-back: batch first, URL alone and last, read-back.
  verify      - byte-for-byte read-back only.

Secrecy: nothing this CLI prints ever contains a token value. Exit codes:
  0 success, 2 credential not resolved, 3 location mismatch (isolation),
  4 required custom fields missing, 5 rate limit, 1 other error.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import constants
from .field_map import MissingRequiredFieldError, get_or_build_field_map
from .resolver import resolve_credentials
from .state import GhlState
from .transport import CafRestDataPlane, RateLimited
from .writer import ReadBackMismatch, ValueHygieneError, verify_read_back, write_link_back


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        for key, value in payload.items():
            sys.stdout.write(f"{key}: {value}\n")


def _resolve_or_exit(args) -> tuple[str, str]:
    """Return (location_id, pit) or exit with the right code. Never prints a value."""
    resolution = resolve_credentials(
        payload_location_id=getattr(args, "payload_location_id", None),
        gateway_pid=getattr(args, "gateway_pid", None),
        gateway_container=getattr(args, "gateway_container", None),
    )
    if resolution.payload_location_mismatch:
        _emit({"status": "isolation-violation",
               "detail": "webhook location_id does not match the environment"},
              getattr(args, "json", False))
        sys.exit(3)
    if not resolution.pit_found or not resolution.prefix_ok:
        _emit({"status": "credential-not-resolved",
               "audit": resolution.audit,
               "sweep_paths": resolution.sweep_paths},
              getattr(args, "json", False))
        sys.exit(2)
    location_id = args.location_id or resolution.location_id
    if not location_id:
        _emit({"status": "location-not-resolved"}, getattr(args, "json", False))
        sys.exit(2)
    return location_id, resolution.pit()


def cmd_resolve(args) -> int:
    resolution = resolve_credentials(
        payload_location_id=args.payload_location_id,
        gateway_pid=args.gateway_pid,
        gateway_container=args.gateway_container,
    )
    _emit(resolution.to_public_dict(), args.json)
    if resolution.payload_location_mismatch:
        return 3
    if not resolution.pit_found or not resolution.prefix_ok:
        return 2
    return 0


def cmd_build_map(args) -> int:
    location_id, pit = _resolve_or_exit(args)
    state = GhlState(args.state_dir)
    dataplane = CafRestDataPlane(location_id, pit)
    try:
        result = get_or_build_field_map(dataplane, state, refresh=args.refresh)
    except MissingRequiredFieldError as exc:
        _emit({"status": "required-fields-missing", "missing": exc.missing,
               "message": ("the custom fields are missing; contact support to "
                           "have them created via the snapshot")}, args.json)
        return 4
    except RateLimited:
        _emit({"status": "rate-limited"}, args.json)
        return 5
    _emit({"status": "ok", **result.public_summary()}, args.json)
    return 0


def cmd_write_back(args) -> int:
    location_id, pit = _resolve_or_exit(args)
    state = GhlState(args.state_dir)
    dataplane = CafRestDataPlane(location_id, pit)
    try:
        with open(args.values_file, "r", encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, ValueError) as exc:
        _emit({"status": "bad-values-file", "detail": str(exc)}, args.json)
        return 1
    try:
        field_result = get_or_build_field_map(dataplane, state, refresh=args.refresh)
        result = write_link_back(dataplane, args.contact_id, values, field_result)
    except MissingRequiredFieldError as exc:
        _emit({"status": "required-fields-missing", "missing": exc.missing}, args.json)
        return 4
    except ValueHygieneError as exc:
        _emit({"status": "value-hygiene", "detail": str(exc)}, args.json)
        return 1
    except RateLimited:
        _emit({"status": "rate-limited"}, args.json)
        return 5
    except ReadBackMismatch as exc:
        _emit({"status": "read-back-mismatch", "mismatched": exc.mismatched_keys}, args.json)
        return 1
    _emit({"status": "ok", **result.public_summary()}, args.json)
    return 0


def cmd_verify(args) -> int:
    location_id, pit = _resolve_or_exit(args)
    state = GhlState(args.state_dir)
    dataplane = CafRestDataPlane(location_id, pit)
    try:
        with open(args.values_file, "r", encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, ValueError) as exc:
        _emit({"status": "bad-values-file", "detail": str(exc)}, args.json)
        return 1
    field_map = state.get_field_map()
    if not field_map:
        _emit({"status": "no-field-map", "detail": "run build-map first"}, args.json)
        return 1
    ok, mismatched = verify_read_back(dataplane, args.contact_id, field_map, values)
    _emit({"status": "ok" if ok else "mismatch", "read_back_pass": ok,
           "mismatched": mismatched}, args.json)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="caf-field-layer",
        description="Convert and Flow field layer (Tier 0 caf + Tier 3 REST only)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--state-dir", default=constants.default_state_dir(),
                        help="per-client state directory")
    parser.add_argument("--location-id", default=None, help="Location ID override")
    parser.add_argument("--payload-location-id", default=None,
                        help="webhook location_id to match against the environment")
    parser.add_argument("--gateway-pid", default=None, help="live gateway pid probe")
    parser.add_argument("--gateway-container", default=None, help="live gateway container probe")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("resolve", help="ENV-CHECK-BEFORE-FAIL credential audit")

    p_map = sub.add_parser("build-map", help="build or refresh the field map")
    p_map.add_argument("--refresh", action="store_true", help="force a rebuild")

    p_write = sub.add_parser("write-back", help="Step 16 link-back write")
    p_write.add_argument("--contact-id", required=True)
    p_write.add_argument("--values-file", required=True, help="JSON of field key to value")
    p_write.add_argument("--refresh", action="store_true", help="force a map rebuild first")

    p_verify = sub.add_parser("verify", help="byte-for-byte read-back only")
    p_verify.add_argument("--contact-id", required=True)
    p_verify.add_argument("--values-file", required=True, help="JSON of field key to value")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dispatch = {
        "resolve": cmd_resolve,
        "build-map": cmd_build_map,
        "write-back": cmd_write_back,
        "verify": cmd_verify,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
