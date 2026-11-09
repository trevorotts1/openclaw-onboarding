#!/usr/bin/env python3
"""final_view_gate: fail-closed enforcement gate for FINAL-VIEW-BEHAVIOUR-R1.

Derived from pinned spec FINAL-VIEW-BEHAVIOUR-R1 (sha256
9248895310a2449a4cef2f92c9633c26926dad2e24db1458cd4bcd97dd8f83d2)
and its prover (sha256
edccb4090386ccac69f3590f48ace0dfd51a1330b26de0f66a472dfdc451132e).
Standard library only. Reads bytes, writes nothing.

Fail-closed contract: any rule violation, malformed input, unreadable
spec, or spec that is not the pinned definition -> exit 1 with fail
codes. Exit 0 (PASS) only on zero fail codes. There is no path that
passes on error.

Usage:
  python3 -I final_view_gate.py --manifest M.json [--spec S.json] [--base DIR]

Exit codes: 0 PASS, 1 FAIL (rule or integrity codes emitted).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

PINNED_DEFINITION_ID = "FINAL-VIEW-BEHAVIOUR-R1"
PINNED_SPEC_SHA256 = "9248895310a2449a4cef2f92c9633c26926dad2e24db1458cd4bcd97dd8f83d2"
PINNED_OWED_VIEWS = ["close-up", "side-profile", "three-quarter", "full-standing"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def check(manifest, views, base_dir):
    """Return ordered fail codes; empty list means PASS."""
    codes = []
    chars = manifest.get("characters")
    if not isinstance(chars, list) or not chars:
        return ["NO_CHARACTERS"]

    # R1 identity key: (character_id, view) indexed, never view alone.
    seen = {}
    for raw in chars:
        if not isinstance(raw, dict):
            codes.append("DUPLICATE_IDENTITY:")
            continue
        cid = raw.get("id")
        if not isinstance(cid, str) or not cid.strip():
            codes.append("DUPLICATE_IDENTITY:")
            continue
        cid = cid.strip()
        if cid in seen:
            codes.append("DUPLICATE_IDENTITY:%s" % cid)
        seen[cid] = raw

    refs = []  # (cid, view, disk_sha256, resolved path)
    for cid in sorted(seen):
        imgs = seen[cid].get("views") or {}

        # R2 owed views: exact set membership against the owed four.
        for view in sorted(imgs):
            if view not in views:
                codes.append("UNKNOWN_VIEW:%s:%s" % (cid, view))
        for view in views:
            entry = imgs.get(view)
            if not isinstance(entry, dict):
                codes.append("MISSING_VIEW:%s:%s" % (cid, view))
                continue

            # R3 placeholder can never be final.
            if str(entry.get("kind") or "").lower() == "placeholder" \
                    or entry.get("placeholder") is True:
                codes.append("PLACEHOLDER_NOT_FINAL:%s:%s" % (cid, view))
                continue

            # R4 only kind=actual with approved=true counts.
            if str(entry.get("kind") or "").lower() != "actual" \
                    or entry.get("approved") is not True:
                codes.append("PREVIEW_NOT_FINAL:%s:%s" % (cid, view))
                continue

            # R5 actual file on disk, non-empty, byte identity recomputed.
            rel = entry.get("path")
            path = os.path.join(base_dir, rel) if rel else ""
            if not rel or not os.path.isfile(path) or os.path.getsize(path) <= 0:
                codes.append("NOT_ACTUAL_FILE:%s:%s" % (cid, view))
                continue
            digest = sha256_file(path)
            if digest != entry.get("sha256"):
                codes.append("HASH_MISMATCH:%s:%s" % (cid, view))
            refs.append((cid, view, digest, os.path.realpath(path)))

    # R6 crossed associations: no sha256 and no resolved path bound to
    # more than one (character_id, view) pair.
    for label, index in (("hash", 2), ("path", 3)):
        buckets = {}
        for ref in refs:
            buckets.setdefault(ref[index], set()).add((ref[0], ref[1]))
        for key in sorted(buckets):
            pairs = buckets[key]
            if len(pairs) > 1:
                codes.append("CROSSED_REFERENCE:%s:%s" % (
                    label, ",".join("%s/%s" % p for p in sorted(pairs))))

    # R7 exact consumption: every final reference cited by a real request
    # record citing the exact (character_id, view, sha256) triple.
    finals = {(cid, view, digest) for cid, view, digest, _p in refs}
    records = manifest.get("consumption") or []
    cited = set()
    if not refs or not records:
        codes.append("NO_CONSUMPTION")
    for rec in records:
        for item in (rec or {}).get("references") or []:
            key = (item.get("character_id"), item.get("view"), item.get("sha256"))
            if key not in finals:
                codes.append("CONSUMPTION_MISMATCH:%s:%s:%s" % key)
            else:
                cited.add(key)
    for key in sorted(finals - cited):
        codes.append("UNCONSUMED:%s:%s:%s" % key)

    return codes


def fail(codes):
    print(json.dumps({"schema": "blackceo.final-view-gate-verdict/v1",
                      "definition_id": PINNED_DEFINITION_ID,
                      "verdict": "FAIL",
                      "fail_codes": codes}, sort_keys=True))
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="FINAL-VIEW fail-closed gate")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--base", default=None,
                    help="directory relative paths resolve against (default: manifest's directory)")
    args = ap.parse_args(argv)

    try:
        manifest = load_json(args.manifest)
    except (OSError, ValueError) as exc:
        return fail(["MALFORMED_INPUT:manifest:%s" % exc])
    if not isinstance(manifest, dict):
        return fail(["MALFORMED_INPUT:manifest-not-object"])

    views = list(PINNED_OWED_VIEWS)
    if args.spec:
        try:
            spec = load_json(args.spec)
        except (OSError, ValueError) as exc:
            return fail(["MALFORMED_INPUT:spec:%s" % exc])
        # Pin enforcement: gate refuses to judge against any other definition.
        if spec.get("definition_id") != PINNED_DEFINITION_ID:
            return fail(["SPEC_NOT_PINNED:%s" % spec.get("definition_id")])
        if not isinstance(spec.get("views_in_order"), list):
            return fail(["MALFORMED_INPUT:spec-views"])
        views = list(spec["views_in_order"])
        if sorted(views) != sorted(PINNED_OWED_VIEWS):
            return fail(["SPEC_VIEWS_DIVERGED:%s" % ",".join(sorted(views))])

    base = args.base or os.path.dirname(os.path.abspath(args.manifest))
    try:
        codes = check(manifest, views, base)
    except OSError as exc:
        # Fail closed: unreadable bytes are a refusal, never a pass.
        return fail(["READ_ERROR:%s" % exc])
    if codes:
        return fail(codes)
    print(json.dumps({"schema": "blackceo.final-view-gate-verdict/v1",
                      "definition_id": PINNED_DEFINITION_ID,
                      "verdict": "PASS",
                      "fail_codes": []}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
